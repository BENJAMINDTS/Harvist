"""
Tests de integración para el panel de revisión manual de descripciones (Fase 7.3).

Cubre:
  PATCH  /api/v1/jobs/{job_id}/descriptions/{codigo}  — Revisar una descripción
  GET    /api/v1/jobs/{job_id}/descriptions/review     — Estado paginado de revisiones
  GET    /api/v1/files/{job_id}/csv?only_approved=true — Exportar solo aprobadas

Redis y Celery se mockean. El storage se simula con archivos temporales (tmp_path).

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

import csv
import io
import json
import os
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ── Variables de entorno antes de importar la app ────────────────────────────
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "clave-de-prueba-super-segura-32c")
os.environ.setdefault("BROWSER_BINARY_PATH", "/usr/bin/google-chrome")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

from api.core.config import get_settings  # noqa: E402
get_settings.cache_clear()

from api.main import app  # noqa: E402
from api.v1.schemas.job import (  # noqa: E402
    DescriptionReviewState,
    EstadoJob,
    JobStatus,
    ReviewStatus,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

_CSV_FIELDNAMES = [
    "codigo", "nombre", "marca", "categoria",
    "corta", "larga", "keywords", "meta_description", "exitoso", "error",
]

_SAMPLE_PRODUCTS = [
    {
        "codigo": "PROD001",
        "nombre": "Pienso Gato Adulto",
        "marca": "Royal Canin",
        "categoria": "Alimentación",
        "corta": "Descripción corta generada.",
        "larga": "Descripción larga generada.",
        "keywords": "gato,pienso",
        "meta_description": "Meta descripción.",
        "exitoso": "True",
        "error": "",
    },
    {
        "codigo": "PROD002",
        "nombre": "Cama Perro Grande",
        "marca": "Ferplast",
        "categoria": "Descanso",
        "corta": "Cama cómoda.",
        "larga": "Cama ortopédica para perros grandes.",
        "keywords": "cama,perro",
        "meta_description": "Cama para perros.",
        "exitoso": "True",
        "error": "",
    },
]


def _build_descriptions_csv(products: list[dict] | None = None) -> bytes:
    """Serializa productos a CSV UTF-8 BOM (mismo formato que el pipeline)."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDNAMES)
    writer.writeheader()
    for p in (products or _SAMPLE_PRODUCTS):
        writer.writerow(p)
    return buf.getvalue().encode("utf-8-sig")


def _build_job_status(
    job_id: str,
    estado: EstadoJob = EstadoJob.COMPLETADO,
    descripciones_generadas: int = 2,
    revisiones_pendientes: int = 2,
    revisiones_aprobadas: int = 0,
    revisiones_rechazadas: int = 0,
) -> JobStatus:
    """Construye un JobStatus de prueba para un job de descripciones."""
    return JobStatus(
        job_id=uuid.UUID(job_id),
        estado=estado,
        total_productos=2,
        productos_procesados=2,
        descripciones_generadas=descripciones_generadas,
        revisiones_pendientes=revisiones_pendientes,
        revisiones_aprobadas=revisiones_aprobadas,
        revisiones_rechazadas=revisiones_rechazadas,
        mensaje="Estado de prueba.",
    )


def _build_redis_mock(
    job_status_json: str | None,
    review_states: dict[str, str] | None = None,
    captured_sets: list | None = None,
) -> AsyncMock:
    """
    Construye un mock de aioredis.

    Args:
        job_status_json: JSON serializado del JobStatus, o None si no existe.
        review_states:   Mapa de review_key → JSON serializado de DescriptionReviewState.
        captured_sets:   Lista mutable donde se acumularán las llamadas a redis.set.

    Returns:
        AsyncMock de la conexión Redis.
    """
    if review_states is None:
        review_states = {}
    if captured_sets is None:
        captured_sets = []

    async def get_side_effect(key: str) -> str | None:
        if ":review:" in key:
            return review_states.get(key)
        return job_status_json

    async def set_side_effect(key: str, value: str, ex: int | None = None) -> bool:  # noqa: ARG001
        captured_sets.append((key, value))
        return True

    mock = AsyncMock()
    mock.get = AsyncMock(side_effect=get_side_effect)
    mock.set = AsyncMock(side_effect=set_side_effect)
    mock.aclose = AsyncMock()
    return mock


def _build_storage_mock(tmp_path: Path, job_id: str, csv_bytes: bytes | None = None) -> MagicMock:
    """
    Mock de StorageService que crea un directorio temporal con descripciones.csv.

    Args:
        tmp_path:  Directorio temporal de pytest.
        job_id:    Identificador del job.
        csv_bytes: Contenido del CSV; si None, no crea el archivo.

    Returns:
        MagicMock que expone get_job_dir.
    """
    job_dir = tmp_path / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    if csv_bytes is not None:
        (job_dir / "descripciones.csv").write_bytes(csv_bytes)

    mock = MagicMock()
    mock.get_job_dir.return_value = job_dir
    return mock


# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def async_client() -> AsyncClient:
    """
    Cliente HTTPX asíncrono con ASGITransport para llamar a la app sin servidor real.

    Yields:
        AsyncClient listo para enviar peticiones a la app de test.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ── PATCH /api/v1/jobs/{job_id}/descriptions/{codigo} ─────────────────────────


class TestRevisarDescripcion:
    """Suite de tests para PATCH .../descriptions/{codigo}."""

    @pytest.mark.asyncio
    async def test_404_cuando_job_no_existe(self, async_client: AsyncClient) -> None:
        """
        Verifica 404 cuando el job no existe en Redis.
        """
        redis = _build_redis_mock(job_status_json=None)
        with patch("api.v1.endpoints.jobs._get_redis", return_value=redis):
            response = await async_client.patch(
                f"/api/v1/jobs/{uuid.uuid4()}/descriptions/PROD001",
                json={"action": "approve"},
            )
        assert response.status_code == 404
        assert "detail" in response.json()

    @pytest.mark.asyncio
    async def test_404_cuando_producto_no_existe_en_csv(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica 404 cuando el producto no está en descripciones.csv.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id)
        redis = _build_redis_mock(status.model_dump_json())
        storage = _build_storage_mock(tmp_path, job_id, _build_descriptions_csv())

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
            patch("api.v1.endpoints.jobs.get_storage_service", return_value=storage),
        ):
            response = await async_client.patch(
                f"/api/v1/jobs/{job_id}/descriptions/NO_EXISTE",
                json={"action": "approve"},
            )
        assert response.status_code == 404
        assert "NO_EXISTE" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_409_cuando_job_no_completado(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica 409 cuando el job está EN_PROCESO y no permite revisión.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id, estado=EstadoJob.EN_PROCESO)
        redis = _build_redis_mock(status.model_dump_json())
        storage = _build_storage_mock(tmp_path, job_id, _build_descriptions_csv())

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
            patch("api.v1.endpoints.jobs.get_storage_service", return_value=storage),
        ):
            response = await async_client.patch(
                f"/api/v1/jobs/{job_id}/descriptions/PROD001",
                json={"action": "approve"},
            )
        assert response.status_code == 409
        assert "COMPLETADO" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_422_edit_sin_edited_text(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica 422 cuando action='edit' pero edited_text está ausente.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id)
        redis = _build_redis_mock(status.model_dump_json())
        storage = _build_storage_mock(tmp_path, job_id, _build_descriptions_csv())

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
            patch("api.v1.endpoints.jobs.get_storage_service", return_value=storage),
        ):
            response = await async_client.patch(
                f"/api/v1/jobs/{job_id}/descriptions/PROD001",
                json={"action": "edit"},
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_approve_devuelve_status_approved(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que approve devuelve status='approved' en la respuesta.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id)
        redis = _build_redis_mock(status.model_dump_json())
        storage = _build_storage_mock(tmp_path, job_id, _build_descriptions_csv())

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
            patch("api.v1.endpoints.jobs.get_storage_service", return_value=storage),
        ):
            response = await async_client.patch(
                f"/api/v1/jobs/{job_id}/descriptions/PROD001",
                json={"action": "approve"},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["status"] == "approved"
        assert body["data"]["codigo"] == "PROD001"

    @pytest.mark.asyncio
    async def test_reject_devuelve_status_rejected(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que reject devuelve status='rejected' en la respuesta.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id)
        redis = _build_redis_mock(status.model_dump_json())
        storage = _build_storage_mock(tmp_path, job_id, _build_descriptions_csv())

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
            patch("api.v1.endpoints.jobs.get_storage_service", return_value=storage),
        ):
            response = await async_client.patch(
                f"/api/v1/jobs/{job_id}/descriptions/PROD001",
                json={"action": "reject"},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_edit_guarda_edited_text_y_devuelve_approved(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que edit guarda edited_text y devuelve status='approved'.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id)
        redis = _build_redis_mock(status.model_dump_json())
        storage = _build_storage_mock(tmp_path, job_id, _build_descriptions_csv())
        texto_editado = "Descripción corta editada por el usuario."

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
            patch("api.v1.endpoints.jobs.get_storage_service", return_value=storage),
        ):
            response = await async_client.patch(
                f"/api/v1/jobs/{job_id}/descriptions/PROD001",
                json={"action": "edit", "edited_text": texto_editado},
            )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "approved"
        assert data["edited_text"] == texto_editado

    @pytest.mark.asyncio
    async def test_estado_revisado_persistido_en_redis(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que redis.set es llamado con la clave de revisión correcta
        y que el estado serializado contiene status=approved.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id)
        captured_sets: list = []
        redis = _build_redis_mock(status.model_dump_json(), captured_sets=captured_sets)
        storage = _build_storage_mock(tmp_path, job_id, _build_descriptions_csv())

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
            patch("api.v1.endpoints.jobs.get_storage_service", return_value=storage),
        ):
            await async_client.patch(
                f"/api/v1/jobs/{job_id}/descriptions/PROD001",
                json={"action": "approve"},
            )

        review_key = f"job:{job_id}:review:PROD001"
        keys_written = [k for k, _ in captured_sets]
        assert review_key in keys_written

        review_value = next(v for k, v in captured_sets if k == review_key)
        persisted = json.loads(review_value)
        assert persisted["status"] == "approved"

    @pytest.mark.asyncio
    async def test_approve_incrementa_contador_revisiones_aprobadas(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que al aprobar, revisiones_aprobadas en JobStatus incrementa en 1.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id, revisiones_pendientes=2, revisiones_aprobadas=0)
        captured_sets: list = []
        redis = _build_redis_mock(status.model_dump_json(), captured_sets=captured_sets)
        storage = _build_storage_mock(tmp_path, job_id, _build_descriptions_csv())

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
            patch("api.v1.endpoints.jobs.get_storage_service", return_value=storage),
        ):
            response = await async_client.patch(
                f"/api/v1/jobs/{job_id}/descriptions/PROD001",
                json={"action": "approve"},
            )
        assert response.status_code == 200

        job_key = f"job:{job_id}"
        job_set_value = next((v for k, v in captured_sets if k == job_key), None)
        assert job_set_value is not None
        updated_status = json.loads(job_set_value)
        assert updated_status["revisiones_aprobadas"] == 1

    @pytest.mark.asyncio
    async def test_reject_incrementa_contador_revisiones_rechazadas(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que al rechazar, revisiones_rechazadas en JobStatus incrementa en 1.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id, revisiones_pendientes=2, revisiones_rechazadas=0)
        captured_sets: list = []
        redis = _build_redis_mock(status.model_dump_json(), captured_sets=captured_sets)
        storage = _build_storage_mock(tmp_path, job_id, _build_descriptions_csv())

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
            patch("api.v1.endpoints.jobs.get_storage_service", return_value=storage),
        ):
            response = await async_client.patch(
                f"/api/v1/jobs/{job_id}/descriptions/PROD001",
                json={"action": "reject"},
            )
        assert response.status_code == 200

        job_key = f"job:{job_id}"
        job_set_value = next((v for k, v in captured_sets if k == job_key), None)
        assert job_set_value is not None
        updated_status = json.loads(job_set_value)
        assert updated_status["revisiones_rechazadas"] == 1


# ── GET /api/v1/jobs/{job_id}/descriptions/review ─────────────────────────────


class TestObtenerEstadoRevisiones:
    """Suite de tests para GET .../descriptions/review."""

    @pytest.mark.asyncio
    async def test_retorna_lista_paginada_con_estado_revisiones(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que el endpoint devuelve 200 con items paginados y metadatos de total.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id)
        redis = _build_redis_mock(status.model_dump_json())
        storage = _build_storage_mock(tmp_path, job_id, _build_descriptions_csv())

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
            patch("api.v1.endpoints.jobs.get_storage_service", return_value=storage),
        ):
            response = await async_client.get(
                f"/api/v1/jobs/{job_id}/descriptions/review",
                params={"limit": 10, "offset": 0},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert "items" in data
        assert "total" in data
        assert data["total"] == len(_SAMPLE_PRODUCTS)
        assert len(data["items"]) == len(_SAMPLE_PRODUCTS)

    @pytest.mark.asyncio
    async def test_descripcion_sin_revisar_tiene_status_pending(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que las descripciones sin entrada en Redis se devuelven con status='pending'.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id)
        # Sin review_states → todas pending
        redis = _build_redis_mock(status.model_dump_json(), review_states={})
        storage = _build_storage_mock(tmp_path, job_id, _build_descriptions_csv())

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
            patch("api.v1.endpoints.jobs.get_storage_service", return_value=storage),
        ):
            response = await async_client.get(
                f"/api/v1/jobs/{job_id}/descriptions/review",
            )
        assert response.status_code == 200
        items = response.json()["data"]["items"]
        for item in items:
            assert item["status"] == "pending"

    @pytest.mark.asyncio
    async def test_descripcion_con_estado_en_redis_devuelve_estado_correcto(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que las descripciones con entrada en Redis devuelven su estado real.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id, revisiones_aprobadas=1)
        review_key = f"job:{job_id}:review:PROD001"
        approved_state = DescriptionReviewState(
            codigo="PROD001", status=ReviewStatus.APPROVED
        )
        redis = _build_redis_mock(
            status.model_dump_json(),
            review_states={review_key: approved_state.model_dump_json()},
        )
        storage = _build_storage_mock(tmp_path, job_id, _build_descriptions_csv())

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
            patch("api.v1.endpoints.jobs.get_storage_service", return_value=storage),
        ):
            response = await async_client.get(
                f"/api/v1/jobs/{job_id}/descriptions/review",
            )
        assert response.status_code == 200
        items = response.json()["data"]["items"]
        prod1 = next(i for i in items if i["codigo"] == "PROD001")
        assert prod1["status"] == "approved"

    @pytest.mark.asyncio
    async def test_400_cuando_limit_supera_100(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica 400 cuando limit > 100 (fuera del rango permitido).
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id)
        redis = _build_redis_mock(status.model_dump_json())
        storage = _build_storage_mock(tmp_path, job_id, _build_descriptions_csv())

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
            patch("api.v1.endpoints.jobs.get_storage_service", return_value=storage),
        ):
            response = await async_client.get(
                f"/api/v1/jobs/{job_id}/descriptions/review",
                params={"limit": 200},
            )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_404_cuando_no_existe_descripciones_csv_en_get_review(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica 404 cuando el job existe pero no hay descripciones.csv.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id)
        redis = _build_redis_mock(status.model_dump_json())
        # storage sin CSV (csv_bytes=None)
        storage = _build_storage_mock(tmp_path, job_id, csv_bytes=None)

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
            patch("api.v1.endpoints.jobs.get_storage_service", return_value=storage),
        ):
            response = await async_client.get(
                f"/api/v1/jobs/{job_id}/descriptions/review",
            )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_rerevisar_approved_a_rejected_actualiza_contadores(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que al cambiar una descripción de approved a rejected los
        contadores se actualizan correctamente (revert approved + increment rejected).
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(
            job_id, revisiones_pendientes=0, revisiones_aprobadas=1, revisiones_rechazadas=0
        )
        # La descripción ya estaba aprobada en Redis
        review_key = f"job:{job_id}:review:PROD001"
        old_approved = DescriptionReviewState(codigo="PROD001", status=ReviewStatus.APPROVED)
        captured_sets: list = []
        redis = _build_redis_mock(
            status.model_dump_json(),
            review_states={review_key: old_approved.model_dump_json()},
            captured_sets=captured_sets,
        )
        storage = _build_storage_mock(tmp_path, job_id, _build_descriptions_csv())

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
            patch("api.v1.endpoints.jobs.get_storage_service", return_value=storage),
        ):
            response = await async_client.patch(
                f"/api/v1/jobs/{job_id}/descriptions/PROD001",
                json={"action": "reject"},
            )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "rejected"

        job_key = f"job:{job_id}"
        job_set_value = next((v for k, v in captured_sets if k == job_key), None)
        assert job_set_value is not None
        updated = json.loads(job_set_value)
        assert updated["revisiones_aprobadas"] == 0
        assert updated["revisiones_rechazadas"] == 1


# ── GET /api/v1/files/{job_id}/csv ────────────────────────────────────────────


class TestDescargarCsvAprobadas:
    """Suite de tests para GET /api/v1/files/{job_id}/csv con only_approved."""

    @pytest.mark.asyncio
    async def test_only_approved_devuelve_solo_filas_aprobadas(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que ?only_approved=true filtra y devuelve solo las filas aprobadas.
        """
        job_id = str(uuid.uuid4())
        csv_bytes = _build_descriptions_csv()

        review_key_prod1 = f"job:{job_id}:review:PROD001"
        approved_state = DescriptionReviewState(
            codigo="PROD001", status=ReviewStatus.APPROVED
        )
        review_states = {review_key_prod1: approved_state.model_dump_json()}

        async def redis_get(key: str) -> str | None:
            return review_states.get(key)

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(side_effect=redis_get)
        redis_mock.aclose = AsyncMock()

        storage = _build_storage_mock(tmp_path, job_id, csv_bytes)

        with (
            patch("api.v1.endpoints.files.aioredis.from_url", return_value=redis_mock),
            patch("api.v1.endpoints.files.get_storage_service", return_value=storage),
        ):
            response = await async_client.get(
                f"/api/v1/files/{job_id}/csv",
                params={"only_approved": "true"},
            )
        assert response.status_code == 200
        content = response.content.decode("utf-8-sig")
        assert "PROD001" in content
        assert "PROD002" not in content

    @pytest.mark.asyncio
    async def test_only_approved_devuelve_204_si_ninguna_aprobada(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que ?only_approved=true devuelve 204 cuando ninguna descripción
        tiene estado 'approved' en Redis.
        """
        job_id = str(uuid.uuid4())
        csv_bytes = _build_descriptions_csv()

        async def redis_get(key: str) -> None:  # noqa: ARG001
            return None  # ninguna aprobada

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(side_effect=redis_get)
        redis_mock.aclose = AsyncMock()

        storage = _build_storage_mock(tmp_path, job_id, csv_bytes)

        with (
            patch("api.v1.endpoints.files.aioredis.from_url", return_value=redis_mock),
            patch("api.v1.endpoints.files.get_storage_service", return_value=storage),
        ):
            response = await async_client.get(
                f"/api/v1/files/{job_id}/csv",
                params={"only_approved": "true"},
            )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_sin_only_approved_devuelve_csv_completo(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que sin el parámetro only_approved el CSV original se devuelve
        sin filtrar (comportamiento original).
        """
        job_id = str(uuid.uuid4())
        csv_bytes = _build_descriptions_csv()
        storage = _build_storage_mock(tmp_path, job_id, csv_bytes)

        with patch("api.v1.endpoints.files.get_storage_service", return_value=storage):
            response = await async_client.get(f"/api/v1/files/{job_id}/csv")

        assert response.status_code == 200
        content = response.content.decode("utf-8-sig")
        assert "PROD001" in content
        assert "PROD002" in content
