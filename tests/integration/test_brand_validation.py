"""
Tests de integración para la validación de marcas nuevas (Fase 7.4).

Cubre:
  POST /api/v1/jobs/{job_id}/brands/validate  — Confirmar marcas pendientes
  GET  /api/v1/jobs/{job_id}/brands/pending   — Obtener marcas pendientes

Redis y Celery se mockean. brand_cache.json se aísla con tmp_path.

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

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

# ── Helpers ───────────────────────────────────────────────────────────────────

_PREFIJO_A = "1234567"
_PREFIJO_B = "9876543"
_EAN_A     = "1234567890123"
_EAN_B     = "9876543210987"


def _job_status(
    job_id: str,
    estado: EstadoJob = EstadoJob.PENDIENTE_VALIDACION_MARCAS,
    marcas_pendientes_validacion: int = 2,
) -> JobStatus:
    """
    Construye un JobStatus de prueba para un job de validación de marcas.

    Args:
        job_id: UUID del job como string.
        estado: estado del job (por defecto PENDIENTE_VALIDACION_MARCAS).
        marcas_pendientes_validacion: número de marcas pendientes de validar.

    Returns:
        JobStatus listo para serializar y cargar en el mock de Redis.
    """
    return JobStatus(
        job_id=uuid.UUID(job_id),
        estado=estado,
        total_productos=5,
        productos_procesados=5,
        marcas_procesadas=5,
        marcas_pendientes_validacion=marcas_pendientes_validacion,
        mensaje="Esperando validación de marcas.",
    )


def _brands_pending_payload(
    prefijos: dict[str, tuple[str, str, str]] | None = None,
) -> str:
    """
    Serializa un dict de marcas pendientes al formato Redis brands_pending.

    Args:
        prefijos: dict con forma {prefijo: (brand_name, ean, source)}.
            Si None, usa dos marcas de ejemplo con _PREFIJO_A y _PREFIJO_B.

    Returns:
        JSON serializado listo para devolver desde redis.get().
    """
    if prefijos is None:
        prefijos = {
            _PREFIJO_A: ("BrandA", _EAN_A, "amazon"),
            _PREFIJO_B: ("BrandB", _EAN_B, "cache_gs1"),
        }
    data = {
        pref: {"brand_name": bn, "ean": ean, "source": src, "confidence": "high"}
        for pref, (bn, ean, src) in prefijos.items()
    }
    return json.dumps(data)


def _redis_mock(
    job_id: str,
    job_status: JobStatus,
    brands_pending_json: str | None = None,
    captured_sets: list | None = None,
    captured_deletes: list | None = None,
) -> AsyncMock:
    """
    Construye un mock de aioredis para los endpoints de validación.

    Args:
        job_id: UUID del job como string.
        job_status: estado del job a devolver desde redis.get().
        brands_pending_json: JSON de marcas pendientes o None si no hay.
        captured_sets: lista mutable donde se acumulan las llamadas a redis.set().
        captured_deletes: lista mutable donde se acumulan las llamadas a redis.delete().

    Returns:
        AsyncMock que implementa get / set / delete / ping / aclose.
    """
    if captured_sets is None:
        captured_sets = []
    if captured_deletes is None:
        captured_deletes = []

    job_key = f"job:{job_id}"
    brands_key = f"job:{job_id}:brands_pending"
    job_json = job_status.model_dump_json()

    async def get_side(key: str) -> str | None:
        if key == job_key:
            return job_json
        if key == brands_key:
            return brands_pending_json
        return None

    async def set_side(key: str, value: str, ex: int | None = None) -> bool:  # noqa: ARG001
        captured_sets.append((key, value))
        return True

    async def delete_side(*keys: str) -> int:
        captured_deletes.extend(keys)
        return len(keys)

    mock = AsyncMock()
    mock.get = AsyncMock(side_effect=get_side)
    mock.set = AsyncMock(side_effect=set_side)
    mock.delete = AsyncMock(side_effect=delete_side)
    mock.ping = AsyncMock(return_value=True)
    mock.aclose = AsyncMock()
    return mock


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """
    Cliente HTTPX asíncrono con ASGITransport para llamar a la app sin servidor real.

    Yields:
        AsyncClient listo para enviar peticiones a la app de test.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Tests POST /brands/validate ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validate_returns_404_for_nonexistent_job(client: AsyncClient) -> None:
    """Devuelve 404 si el job no existe en Redis."""
    job_id = str(uuid.uuid4())

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.ping = AsyncMock(return_value=True)
    redis.aclose = AsyncMock()

    with patch("api.v1.endpoints.jobs._get_redis", return_value=redis):
        resp = await client.post(
            f"/api/v1/jobs/{job_id}/brands/validate",
            json={"items": [{"ean": _EAN_A, "brand_name": "BrandA", "action": "accept"}]},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_validate_returns_409_if_job_not_pending_validation(client: AsyncClient) -> None:
    """Devuelve 409 si el job no está en PENDIENTE_VALIDACION_MARCAS."""
    job_id = str(uuid.uuid4())
    status = _job_status(job_id, estado=EstadoJob.COMPLETADO)
    redis = _redis_mock(job_id, status)

    with patch("api.v1.endpoints.jobs._get_redis", return_value=redis):
        resp = await client.post(
            f"/api/v1/jobs/{job_id}/brands/validate",
            json={"items": [{"ean": _EAN_A, "brand_name": "BrandA", "action": "accept"}]},
        )

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_validate_returns_422_when_edit_action_missing_edited_name(client: AsyncClient) -> None:
    """Devuelve 422 cuando action=edit pero edited_name no está presente."""
    job_id = str(uuid.uuid4())
    status = _job_status(job_id)
    redis = _redis_mock(job_id, status, _brands_pending_payload())

    with patch("api.v1.endpoints.jobs._get_redis", return_value=redis):
        resp = await client.post(
            f"/api/v1/jobs/{job_id}/brands/validate",
            json={"items": [{"ean": _EAN_A, "brand_name": "BrandA", "action": "edit"}]},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_validate_accept_writes_to_brand_cache_json(
    client: AsyncClient, tmp_path: Path
) -> None:
    """action=accept escribe el prefijo y brand_name en brand_cache.json."""
    job_id = str(uuid.uuid4())
    brand_cache = tmp_path / "brand_cache.json"
    status = _job_status(job_id)
    pending = _brands_pending_payload({_PREFIJO_A: ("BrandA", _EAN_A, "amazon")})
    redis = _redis_mock(job_id, status, pending)

    with (
        patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
        patch("api.v1.endpoints.jobs.settings") as mock_settings,
    ):
        mock_settings.brand_cache_path = str(brand_cache)
        mock_settings.file_ttl_seconds = 86400

        resp = await client.post(
            f"/api/v1/jobs/{job_id}/brands/validate",
            json={"items": [{"ean": _EAN_A, "brand_name": "BrandA", "action": "accept"}]},
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["accepted"] == 1
    assert data["rejected"] == 0
    assert brand_cache.exists()
    cache_contents = json.loads(brand_cache.read_text())
    assert cache_contents.get(_PREFIJO_A) == "BrandA"


@pytest.mark.asyncio
async def test_validate_edit_writes_edited_name_to_brand_cache_json(
    client: AsyncClient, tmp_path: Path
) -> None:
    """action=edit escribe el edited_name (no el brand_name original) en brand_cache.json."""
    job_id = str(uuid.uuid4())
    brand_cache = tmp_path / "brand_cache.json"
    status = _job_status(job_id)
    pending = _brands_pending_payload({_PREFIJO_A: ("BrandA", _EAN_A, "amazon")})
    redis = _redis_mock(job_id, status, pending)

    with (
        patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
        patch("api.v1.endpoints.jobs.settings") as mock_settings,
    ):
        mock_settings.brand_cache_path = str(brand_cache)
        mock_settings.file_ttl_seconds = 86400

        resp = await client.post(
            f"/api/v1/jobs/{job_id}/brands/validate",
            json={"items": [{"ean": _EAN_A, "brand_name": "BrandA", "action": "edit", "edited_name": "BrandA Edited"}]},
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["edited"] == 1
    cache_contents = json.loads(brand_cache.read_text())
    assert cache_contents.get(_PREFIJO_A) == "BrandA Edited"


@pytest.mark.asyncio
async def test_validate_reject_does_not_write_to_brand_cache_json(
    client: AsyncClient, tmp_path: Path
) -> None:
    """action=reject no escribe ningún prefijo en brand_cache.json."""
    job_id = str(uuid.uuid4())
    brand_cache = tmp_path / "brand_cache.json"
    status = _job_status(job_id)
    pending = _brands_pending_payload({_PREFIJO_A: ("BrandA", _EAN_A, "amazon")})
    redis = _redis_mock(job_id, status, pending)

    with (
        patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
        patch("api.v1.endpoints.jobs.settings") as mock_settings,
    ):
        mock_settings.brand_cache_path = str(brand_cache)
        mock_settings.file_ttl_seconds = 86400

        resp = await client.post(
            f"/api/v1/jobs/{job_id}/brands/validate",
            json={"items": [{"ean": _EAN_A, "brand_name": "BrandA", "action": "reject"}]},
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["rejected"] == 1
    assert data["accepted"] == 0
    # brand_cache.json should not exist (no writes happened)
    assert not brand_cache.exists()


@pytest.mark.asyncio
async def test_validate_mixed_actions_write_only_accepted_and_edited(
    client: AsyncClient, tmp_path: Path
) -> None:
    """Solo los items con action accept/edit se escriben; reject no."""
    job_id = str(uuid.uuid4())
    brand_cache = tmp_path / "brand_cache.json"
    status = _job_status(job_id)
    pending = _brands_pending_payload({
        _PREFIJO_A: ("BrandA", _EAN_A, "amazon"),
        _PREFIJO_B: ("BrandB", _EAN_B, "cache_gs1"),
    })
    redis = _redis_mock(job_id, status, pending)

    with (
        patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
        patch("api.v1.endpoints.jobs.settings") as mock_settings,
    ):
        mock_settings.brand_cache_path = str(brand_cache)
        mock_settings.file_ttl_seconds = 86400

        resp = await client.post(
            f"/api/v1/jobs/{job_id}/brands/validate",
            json={"items": [
                {"ean": _EAN_A, "brand_name": "BrandA", "action": "accept"},
                {"ean": _EAN_B, "brand_name": "BrandB", "action": "reject"},
            ]},
        )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["accepted"] == 1
    assert data["rejected"] == 1
    cache = json.loads(brand_cache.read_text())
    assert _PREFIJO_A in cache
    assert _PREFIJO_B not in cache


@pytest.mark.asyncio
async def test_validate_job_status_changes_to_completado(
    client: AsyncClient, tmp_path: Path
) -> None:
    """Tras validar, el job pasa a estado COMPLETADO en Redis."""
    job_id = str(uuid.uuid4())
    brand_cache = tmp_path / "brand_cache.json"
    status = _job_status(job_id)
    pending = _brands_pending_payload({_PREFIJO_A: ("BrandA", _EAN_A, "amazon")})
    captured_sets: list = []
    redis = _redis_mock(job_id, status, pending, captured_sets=captured_sets)

    with (
        patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
        patch("api.v1.endpoints.jobs.settings") as mock_settings,
    ):
        mock_settings.brand_cache_path = str(brand_cache)
        mock_settings.file_ttl_seconds = 86400

        await client.post(
            f"/api/v1/jobs/{job_id}/brands/validate",
            json={"items": [{"ean": _EAN_A, "brand_name": "BrandA", "action": "accept"}]},
        )

    # Find the job status update in captured_sets
    job_key = f"job:{job_id}"
    job_updates = [json.loads(v) for k, v in captured_sets if k == job_key]
    assert job_updates, "Job status was not updated in Redis"
    assert job_updates[-1]["estado"] == EstadoJob.COMPLETADO.value


@pytest.mark.asyncio
async def test_validate_brands_pending_key_removed_from_redis(
    client: AsyncClient, tmp_path: Path
) -> None:
    """Después de validar, la clave brands_pending se elimina de Redis."""
    job_id = str(uuid.uuid4())
    brand_cache = tmp_path / "brand_cache.json"
    status = _job_status(job_id)
    pending = _brands_pending_payload({_PREFIJO_A: ("BrandA", _EAN_A, "amazon")})
    captured_deletes: list = []
    redis = _redis_mock(job_id, status, pending, captured_deletes=captured_deletes)

    with (
        patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
        patch("api.v1.endpoints.jobs.settings") as mock_settings,
    ):
        mock_settings.brand_cache_path = str(brand_cache)
        mock_settings.file_ttl_seconds = 86400

        await client.post(
            f"/api/v1/jobs/{job_id}/brands/validate",
            json={"items": [{"ean": _EAN_A, "brand_name": "BrandA", "action": "accept"}]},
        )

    brands_pending_key = f"job:{job_id}:brands_pending"
    assert brands_pending_key in captured_deletes


@pytest.mark.asyncio
async def test_validate_returns_correct_counts(client: AsyncClient, tmp_path: Path) -> None:
    """El endpoint devuelve los contadores correctos de accepted/rejected/edited."""
    job_id = str(uuid.uuid4())
    brand_cache = tmp_path / "brand_cache.json"
    status = _job_status(job_id, marcas_pendientes_validacion=3)
    prefijos = {
        "1111111": ("BrandX", "1111111000001", "amazon"),
        "2222222": ("BrandY", "2222222000002", "cache_gs1"),
        "3333333": ("BrandZ", "3333333000003", "bing_search"),
    }
    pending = _brands_pending_payload(prefijos)
    redis = _redis_mock(job_id, status, pending)

    with (
        patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
        patch("api.v1.endpoints.jobs.settings") as mock_settings,
    ):
        mock_settings.brand_cache_path = str(brand_cache)
        mock_settings.file_ttl_seconds = 86400

        resp = await client.post(
            f"/api/v1/jobs/{job_id}/brands/validate",
            json={"items": [
                {"ean": "1111111000001", "brand_name": "BrandX", "action": "accept"},
                {"ean": "2222222000002", "brand_name": "BrandY", "action": "reject"},
                {"ean": "3333333000003", "brand_name": "BrandZ", "action": "edit", "edited_name": "BrandZ Fixed"},
            ]},
        )

    data = resp.json()["data"]
    assert data["accepted"] == 1
    assert data["rejected"] == 1
    assert data["edited"] == 1


# ── Tests GET /brands/pending ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_brands_pending_returns_409_if_wrong_state(client: AsyncClient) -> None:
    """GET /brands/pending devuelve 409 si el job no está en PENDIENTE_VALIDACION_MARCAS."""
    job_id = str(uuid.uuid4())
    status = _job_status(job_id, estado=EstadoJob.COMPLETADO)
    redis = _redis_mock(job_id, status)

    with patch("api.v1.endpoints.jobs._get_redis", return_value=redis):
        resp = await client.get(f"/api/v1/jobs/{job_id}/brands/pending")

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_brands_pending_returns_items(client: AsyncClient) -> None:
    """GET /brands/pending devuelve la lista de marcas pendientes."""
    job_id = str(uuid.uuid4())
    status = _job_status(job_id)
    pending = _brands_pending_payload({_PREFIJO_A: ("BrandA", _EAN_A, "amazon")})
    redis = _redis_mock(job_id, status, pending)

    with patch("api.v1.endpoints.jobs._get_redis", return_value=redis):
        resp = await client.get(f"/api/v1/jobs/{job_id}/brands/pending")

    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["prefijo"] == _PREFIJO_A
    assert items[0]["brand_name"] == "BrandA"
