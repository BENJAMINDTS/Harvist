"""
Tests de integración para los endpoints de jobs y files de la API Harvist.

Cubre los contratos HTTP de:
  POST   /api/v1/jobs          — Crear un nuevo trabajo de scraping
  GET    /api/v1/jobs/{job_id} — Consultar el estado de un trabajo
  DELETE /api/v1/files/{job_id} — Eliminar archivos de un trabajo

Redis y Celery se mockean completamente; no se requieren servicios externos.

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ── Configuración de variables de entorno antes de importar la app ────────────
# Se inyectan aquí para que Pydantic Settings las recoja sin necesitar .env real.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "clave-de-prueba-super-segura-32c")
os.environ.setdefault("BROWSER_BINARY_PATH", "/usr/bin/google-chrome")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

# Limpiar la caché de settings para que tome las vars de entorno de test
from api.core.config import get_settings  # noqa: E402
get_settings.cache_clear()

from api.main import app  # noqa: E402
from api.v1.schemas.job import EstadoJob, JobStatus  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def csv_content() -> bytes:
    """
    Devuelve el contenido en bytes de un CSV mínimo y válido con cabeceras
    y una fila de producto de ejemplo.

    Returns:
        bytes con un CSV UTF-8 válido.
    """
    lineas = [
        "codigo,nombre,marca,ean",
        "001,Camiseta Básica,Zara,1234567890123",
    ]
    return "\n".join(lineas).encode("utf-8")


@pytest_asyncio.fixture
async def async_client() -> AsyncClient:
    """
    Cliente HTTPX asíncrono configurado con ASGITransport para llamar
    a la app FastAPI sin levantar un servidor real.

    Yields:
        AsyncClient listo para enviar peticiones a la app de test.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_job_status(job_id: str, estado: EstadoJob = EstadoJob.PENDIENTE) -> JobStatus:
    """
    Construye un JobStatus de prueba con valores neutros.

    Args:
        job_id: identificador UUID del job como string.
        estado: estado del job a simular.

    Returns:
        Instancia de JobStatus lista para serializar y devolver desde el mock Redis.
    """
    return JobStatus(
        job_id=uuid.UUID(job_id),
        estado=estado,
        mensaje="Estado de prueba.",
    )


def _redis_mock(job_status_json: str | None) -> AsyncMock:
    """
    Crea un cliente Redis falso que devuelve el JSON de JobStatus proporcionado.

    Args:
        job_status_json: JSON serializado del JobStatus, o None si el job no existe.

    Returns:
        AsyncMock que simula un cliente aioredis con los métodos mínimos necesarios.
    """
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=job_status_json)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.aclose = AsyncMock()
    return mock_redis


# ── Tests POST /api/v1/jobs ───────────────────────────────────────────────────


class TestCrearJob:
    """
    Tests de integración para el endpoint POST /api/v1/jobs.

    Verifica que el endpoint valida correctamente el tipo MIME del CSV,
    rechaza archivos vacíos y devuelve 202 con los campos esperados
    cuando la entrada es válida.

    :author: BenjaminDTS
    """

    @pytest.mark.asyncio
    async def test_crear_job_devuelve_202_con_job_id(
        self, async_client: AsyncClient, csv_content: bytes
    ) -> None:
        """
        Verifica que un CSV válido con modo nombre_marca produce una respuesta
        202 con job_id, estado y ws_url correctos.

        Args:
            async_client: cliente HTTPX de prueba.
            csv_content: bytes de un CSV mínimo válido.
        """
        job_id_fake = str(uuid.uuid4())
        mock_redis = _redis_mock(None)

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=mock_redis),
            patch("workers.tasks.ejecutar_scraping") as mock_task,
        ):
            mock_task.apply_async = MagicMock()

            response = await async_client.post(
                "/api/v1/jobs",
                files={"file": ("productos.csv", BytesIO(csv_content), "text/csv")},
                data={
                    "modo": "nombre_marca",
                    "imagenes_por_producto": "3",
                    "generar_descripciones": "false",
                },
            )

        assert response.status_code == 202, response.text
        body = response.json()
        assert body["success"] is True
        assert "job_id" in body["data"]
        assert "ws_url" in body["data"]
        assert body["data"]["estado"] == EstadoJob.PENDIENTE.value
        # El ws_url debe referenciar el job_id devuelto
        assert body["data"]["job_id"] in body["data"]["ws_url"]

    @pytest.mark.asyncio
    async def test_crear_job_rechaza_mime_invalido(
        self, async_client: AsyncClient
    ) -> None:
        """
        Verifica que se devuelve 400 cuando el archivo enviado no tiene
        tipo MIME de CSV (por ejemplo, un archivo de texto plano genérico).

        Args:
            async_client: cliente HTTPX de prueba.
        """
        contenido = b"esto no es un csv valido"

        response = await async_client.post(
            "/api/v1/jobs",
            files={"file": ("datos.txt", BytesIO(contenido), "application/octet-stream")},
            data={
                "modo": "nombre_marca",
                "imagenes_por_producto": "5",
                "generar_descripciones": "false",
            },
        )

        assert response.status_code == 400
        body = response.json()
        assert "detail" in body

    @pytest.mark.asyncio
    async def test_crear_job_rechaza_csv_vacio(
        self, async_client: AsyncClient
    ) -> None:
        """
        Verifica que se devuelve 400 cuando el archivo CSV enviado está vacío.

        Args:
            async_client: cliente HTTPX de prueba.
        """
        mock_redis = _redis_mock(None)

        with patch("api.v1.endpoints.jobs._get_redis", return_value=mock_redis):
            response = await async_client.post(
                "/api/v1/jobs",
                files={"file": ("vacio.csv", BytesIO(b""), "text/csv")},
                data={
                    "modo": "nombre_marca",
                    "imagenes_por_producto": "5",
                    "generar_descripciones": "false",
                },
            )

        assert response.status_code == 400
        body = response.json()
        assert "detail" in body


# ── Tests GET /api/v1/jobs/{job_id} ──────────────────────────────────────────


class TestObtenerEstadoJob:
    """
    Tests de integración para el endpoint GET /api/v1/jobs/{job_id}.

    Verifica que el endpoint devuelve el estado correcto del job cuando
    existe en Redis y un 404 cuando no existe.

    :author: BenjaminDTS
    """

    @pytest.mark.asyncio
    async def test_obtener_estado_job_existente(
        self, async_client: AsyncClient
    ) -> None:
        """
        Verifica que se devuelve 200 con el JobStatus serializado cuando
        el job existe en Redis (mock devuelve JSON válido).

        Args:
            async_client: cliente HTTPX de prueba.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id, EstadoJob.EN_PROCESO)
        status_json = status.model_dump_json()

        mock_redis = _redis_mock(status_json)

        with patch("api.v1.endpoints.jobs._get_redis", return_value=mock_redis):
            response = await async_client.get(f"/api/v1/jobs/{job_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert "data" in body
        assert body["data"]["estado"] == EstadoJob.EN_PROCESO.value
        # El job_id en la respuesta debe coincidir (comparando como string)
        assert str(body["data"]["job_id"]) == job_id

    @pytest.mark.asyncio
    async def test_obtener_estado_job_inexistente(
        self, async_client: AsyncClient
    ) -> None:
        """
        Verifica que se devuelve 404 cuando el job no existe en Redis
        (mock devuelve None para la clave consultada).

        Args:
            async_client: cliente HTTPX de prueba.
        """
        job_id = str(uuid.uuid4())
        mock_redis = _redis_mock(None)  # Redis no tiene la clave

        with patch("api.v1.endpoints.jobs._get_redis", return_value=mock_redis):
            response = await async_client.get(f"/api/v1/jobs/{job_id}")

        assert response.status_code == 404
        body = response.json()
        assert "detail" in body


# ── Tests DELETE /api/v1/files/{job_id} ──────────────────────────────────────


class TestEliminarArchivosJob:
    """
    Tests de integración para el endpoint DELETE /api/v1/files/{job_id}.

    Verifica que el endpoint delega correctamente en LocalStorageService
    y devuelve 200 cuando los archivos existen o 404 cuando no existen.

    :author: BenjaminDTS
    """

    @pytest.mark.asyncio
    async def test_eliminar_archivos_existentes(
        self, async_client: AsyncClient
    ) -> None:
        """
        Verifica que se devuelve 200 con confirmación cuando LocalStorageService
        elimina los archivos del job sin lanzar excepciones.

        Args:
            async_client: cliente HTTPX de prueba.
        """
        job_id = str(uuid.uuid4())

        mock_storage = MagicMock()
        mock_storage.delete_job_files = MagicMock(return_value=None)

        with patch(
            "api.v1.endpoints.files.get_storage_service",
            return_value=mock_storage,
        ):
            response = await async_client.delete(f"/api/v1/files/{job_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["job_id"] == job_id
        mock_storage.delete_job_files.assert_called_once_with(job_id)

    @pytest.mark.asyncio
    async def test_eliminar_archivos_inexistentes(
        self, async_client: AsyncClient
    ) -> None:
        """
        Verifica que se devuelve 404 cuando LocalStorageService lanza
        FileNotFoundError porque no existen archivos para el job dado.

        Args:
            async_client: cliente HTTPX de prueba.
        """
        job_id = str(uuid.uuid4())

        mock_storage = MagicMock()
        mock_storage.delete_job_files = MagicMock(
            side_effect=FileNotFoundError(f"No existen archivos para el job '{job_id}'.")
        )

        with patch(
            "api.v1.endpoints.files.get_storage_service",
            return_value=mock_storage,
        ):
            response = await async_client.delete(f"/api/v1/files/{job_id}")

        assert response.status_code == 404
        body = response.json()
        assert "detail" in body
