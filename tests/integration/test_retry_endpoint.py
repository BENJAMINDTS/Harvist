"""
Tests de integración para el endpoint POST /api/v1/jobs/{job_id}/retry.

Cubre todos los casos de validación y el flujo nominal:
  - 404 si el job no existe
  - 409 si el job no está en estado COMPLETADO o FALLIDO
  - 409 si reintentos >= MAX_REINTENTOS (3)
  - 400 si no hay productos fallidos registrados
  - 422 si todos los flags de retry son False
  - 202 y encola retry_job si todo es correcto
  - El campo productos_a_reintentar es correcto
  - El campo reintentos_previos es correcto

Redis y Celery se mockean completamente.

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

import json
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ── Variables de entorno de test ──────────────────────────────────────────────

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "clave-de-prueba-super-segura-32c")
os.environ.setdefault("BROWSER_BINARY_PATH", "/usr/bin/google-chrome")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

from api.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from api.main import app  # noqa: E402
from api.v1.schemas.job import EstadoJob, JobStatus  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def async_client() -> AsyncClient:
    """
    Cliente HTTPX asíncrono para la app FastAPI de test.

    Yields:
        AsyncClient listo para enviar peticiones.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_job_status(
    job_id: str,
    estado: EstadoJob = EstadoJob.COMPLETADO,
    reintentos: int = 0,
    productos_fallidos: list[str] | None = None,
) -> JobStatus:
    """
    Construye un JobStatus de prueba.

    Args:
        job_id:             UUID como string.
        estado:             estado del job.
        reintentos:         número de reintentos previos.
        productos_fallidos: lista de códigos fallidos (para productos_fallidos).

    Returns:
        Instancia de JobStatus.
    """
    return JobStatus(
        job_id=uuid.UUID(job_id),
        estado=estado,
        imagenes_descargadas=10,
        imagenes_fallidas=3,
        total_productos=13,
        reintentos=reintentos,
        productos_fallidos=productos_fallidos or [],
        mensaje="Test.",
    )


def _build_failed_products(codigos: list[str], razon: str = "imagen") -> list[dict]:
    """
    Construye la lista de productos fallidos para Redis.

    Args:
        codigos: códigos de los productos fallidos.
        razon:   razón del fallo.

    Returns:
        Lista de dicts con campos codigo, nombre y razon.
    """
    return [{"codigo": c, "nombre": f"Prod {c}", "razon": razon} for c in codigos]


def _redis_mock(
    job_status_json: str | None,
    failed_products_json: str | None = None,
) -> AsyncMock:
    """
    Crea un cliente Redis asíncrono falso.

    Args:
        job_status_json:      JSON del JobStatus o None si el job no existe.
        failed_products_json: JSON de la lista de failed_products o None si no existe.

    Returns:
        AsyncMock que simula aioredis.
    """
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.aclose = AsyncMock()

    async def get_side_effect(key: str) -> str | None:
        if "failed_products" in key:
            return failed_products_json
        return job_status_json

    mock_redis.get = AsyncMock(side_effect=get_side_effect)
    return mock_redis


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestRetryEndpoint:
    """
    Tests de integración para POST /api/v1/jobs/{job_id}/retry.

    :author: BenjaminDTS
    """

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent_job(self, async_client: AsyncClient) -> None:
        """
        Verifica que se devuelve 404 cuando el job no existe en Redis.

        Args:
            async_client: cliente de test.
        """
        job_id = str(uuid.uuid4())
        mock_redis = _redis_mock(None)

        with patch("api.v1.endpoints.jobs._get_redis", return_value=mock_redis):
            response = await async_client.post(
                f"/api/v1/jobs/{job_id}/retry",
                json={"retry_images": True, "retry_brands": False, "retry_descriptions": False, "retry_seo": False},
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_409_if_job_not_completed_or_error(self, async_client: AsyncClient) -> None:
        """
        Verifica que se devuelve 409 cuando el job está EN_PROCESO (no completado).

        Args:
            async_client: cliente de test.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id, estado=EstadoJob.EN_PROCESO)
        mock_redis = _redis_mock(status.model_dump_json())

        with patch("api.v1.endpoints.jobs._get_redis", return_value=mock_redis):
            response = await async_client.post(
                f"/api/v1/jobs/{job_id}/retry",
                json={"retry_images": True, "retry_brands": False, "retry_descriptions": False, "retry_seo": False},
            )

        assert response.status_code == 409
        assert "completados" in response.json()["detail"].lower() or "error" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_returns_409_when_max_reintentos_reached(self, async_client: AsyncClient) -> None:
        """
        Verifica que se devuelve 409 cuando el job ya alcanzó el límite de 3 reintentos.

        Args:
            async_client: cliente de test.
        """
        job_id = str(uuid.uuid4())
        # reintentos=3 = MAX_REINTENTOS
        status = _build_job_status(job_id, estado=EstadoJob.COMPLETADO, reintentos=3)
        mock_redis = _redis_mock(status.model_dump_json())

        with patch("api.v1.endpoints.jobs._get_redis", return_value=mock_redis):
            response = await async_client.post(
                f"/api/v1/jobs/{job_id}/retry",
                json={"retry_images": True, "retry_brands": False, "retry_descriptions": False, "retry_seo": False},
            )

        assert response.status_code == 409
        assert "límite" in response.json()["detail"] or "limite" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_returns_400_when_no_failed_products(self, async_client: AsyncClient) -> None:
        """
        Verifica que se devuelve 400 cuando no hay productos fallidos registrados.

        Args:
            async_client: cliente de test.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id, estado=EstadoJob.COMPLETADO)
        # Sin failed_products en Redis
        mock_redis = _redis_mock(status.model_dump_json(), failed_products_json=None)

        with patch("api.v1.endpoints.jobs._get_redis", return_value=mock_redis):
            response = await async_client.post(
                f"/api/v1/jobs/{job_id}/retry",
                json={"retry_images": True, "retry_brands": False, "retry_descriptions": False, "retry_seo": False},
            )

        assert response.status_code == 400
        assert "fallidos" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_returns_422_when_all_retry_flags_false(self, async_client: AsyncClient) -> None:
        """
        Verifica que se devuelve 422 cuando todos los flags son False.

        Args:
            async_client: cliente de test.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id, estado=EstadoJob.COMPLETADO)
        mock_redis = _redis_mock(status.model_dump_json())

        with patch("api.v1.endpoints.jobs._get_redis", return_value=mock_redis):
            response = await async_client.post(
                f"/api/v1/jobs/{job_id}/retry",
                json={"retry_images": False, "retry_brands": False, "retry_descriptions": False, "retry_seo": False},
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_returns_202_and_enqueues_task_when_valid(self, async_client: AsyncClient) -> None:
        """
        Verifica que se devuelve 202 y se encola retry_job cuando la petición es válida.

        Args:
            async_client: cliente de test.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id, estado=EstadoJob.COMPLETADO, reintentos=0)
        failed = _build_failed_products(["AAA", "BBB"])
        mock_redis = _redis_mock(status.model_dump_json(), json.dumps(failed))

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=mock_redis),
            patch("workers.tasks.retry_job") as mock_task,
        ):
            mock_task.apply_async = MagicMock()

            response = await async_client.post(
                f"/api/v1/jobs/{job_id}/retry",
                json={"retry_images": True, "retry_brands": False, "retry_descriptions": False, "retry_seo": False},
            )

        assert response.status_code == 202
        body = response.json()
        assert body["success"] is True
        mock_task.apply_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_response_contains_correct_productos_a_reintentar(self, async_client: AsyncClient) -> None:
        """
        Verifica que productos_a_reintentar en la respuesta coincide con los productos elegibles.

        Args:
            async_client: cliente de test.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id, estado=EstadoJob.COMPLETADO)
        # 3 productos con imagen fallida, 1 con marca fallida
        failed = (
            _build_failed_products(["AAA", "BBB", "CCC"], razon="imagen")
            + _build_failed_products(["DDD"], razon="marca")
        )
        mock_redis = _redis_mock(status.model_dump_json(), json.dumps(failed))

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=mock_redis),
            patch("workers.tasks.retry_job") as mock_task,
        ):
            mock_task.apply_async = MagicMock()

            # Solo retry_images=True → solo 3 productos
            response = await async_client.post(
                f"/api/v1/jobs/{job_id}/retry",
                json={"retry_images": True, "retry_brands": False, "retry_descriptions": False, "retry_seo": False},
            )

        assert response.status_code == 202
        data = response.json()["data"]
        assert data["productos_a_reintentar"] == 3

    @pytest.mark.asyncio
    async def test_response_contains_reintentos_previos(self, async_client: AsyncClient) -> None:
        """
        Verifica que reintentos_previos en la respuesta refleja el valor actual del job.

        Args:
            async_client: cliente de test.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id, estado=EstadoJob.COMPLETADO, reintentos=2)
        failed = _build_failed_products(["AAA"])
        mock_redis = _redis_mock(status.model_dump_json(), json.dumps(failed))

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=mock_redis),
            patch("workers.tasks.retry_job") as mock_task,
        ):
            mock_task.apply_async = MagicMock()

            response = await async_client.post(
                f"/api/v1/jobs/{job_id}/retry",
                json={"retry_images": True, "retry_brands": False, "retry_descriptions": False, "retry_seo": False},
            )

        assert response.status_code == 202
        data = response.json()["data"]
        assert data["reintentos_previos"] == 2

    @pytest.mark.asyncio
    async def test_accepts_fallido_state_as_retryable(self, async_client: AsyncClient) -> None:
        """
        Verifica que un job en estado FALLIDO también puede reintentarse.

        Args:
            async_client: cliente de test.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id, estado=EstadoJob.FALLIDO, reintentos=1)
        failed = _build_failed_products(["AAA"])
        mock_redis = _redis_mock(status.model_dump_json(), json.dumps(failed))

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=mock_redis),
            patch("workers.tasks.retry_job") as mock_task,
        ):
            mock_task.apply_async = MagicMock()

            response = await async_client.post(
                f"/api/v1/jobs/{job_id}/retry",
                json={"retry_images": True, "retry_brands": False, "retry_descriptions": False, "retry_seo": False},
            )

        assert response.status_code == 202
