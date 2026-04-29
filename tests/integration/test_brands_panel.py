"""
Tests de integración para el endpoint GET /api/v1/jobs/{job_id}/brands (Fase 6.4).

Cubre:
  GET  /api/v1/jobs/{job_id}/brands   — Lista de marcas como JSON
  GET  /api/v1/files/{job_id}/brands  — Descarga de marcas.csv

Redis y Celery se mockean. El storage se simula con archivos temporales.

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

import csv
import io
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
from api.v1.schemas.job import EstadoJob, JobStatus  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

_SAMPLE_BRANDS = [
    {"codigo": "001", "ean": "8410076472725", "brand_name": "Nestle",    "manufacturer": "Nestle SA",  "source": "amazon",       "confidence": "high"},
    {"codigo": "002", "ean": "8410076472726", "brand_name": "Danone",    "manufacturer": "Danone SA",  "source": "cache_gs1",    "confidence": "high"},
    {"codigo": "003", "ean": "8410076472727", "brand_name": "Ferrero",   "manufacturer": "Ferrero",    "source": "open_data_api","confidence": "medium"},
    {"codigo": "004", "ean": "8410076472728", "brand_name": "",          "manufacturer": "",           "source": "not_found",    "confidence": "low"},
    {"codigo": "005", "ean": "INVALID",       "brand_name": "",          "manufacturer": "",           "source": "ean_invalido", "confidence": "low"},
]

_CSV_FIELDNAMES = ["codigo", "ean", "brand_name", "manufacturer", "source", "confidence"]


def _build_marcas_csv(rows: list[dict] | None = None) -> bytes:
    """Serializa filas a CSV UTF-8 con BOM (igual que brand_pipeline)."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDNAMES)
    writer.writeheader()
    for row in (rows or _SAMPLE_BRANDS):
        writer.writerow(row)
    return buf.getvalue().encode("utf-8-sig")


def _build_job_status(job_id: str, estado: EstadoJob = EstadoJob.COMPLETADO) -> JobStatus:
    """Construye un JobStatus de prueba."""
    return JobStatus(
        job_id=uuid.UUID(job_id),
        estado=estado,
        marcas_procesadas=len([r for r in _SAMPLE_BRANDS if r["source"] not in ("not_found", "ean_invalido")]),
        mensaje="Estado de prueba.",
    )


def _redis_mock(job_status_json: str | None) -> AsyncMock:
    """Mock aioredis que devuelve el JSON de JobStatus o None."""
    mock = AsyncMock()
    mock.ping = AsyncMock(return_value=True)
    mock.get = AsyncMock(return_value=job_status_json)
    mock.set = AsyncMock(return_value=True)
    mock.aclose = AsyncMock()
    return mock


def _storage_mock(tmp_path: Path, job_id: str, csv_bytes: bytes | None = None) -> MagicMock:
    """
    Mock de StorageService que devuelve un directorio temporal con marcas.csv.

    Si csv_bytes es None no crea el archivo (simula job sin marcas.csv).
    """
    job_dir = tmp_path / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    if csv_bytes is not None:
        (job_dir / "marcas.csv").write_bytes(csv_bytes)

    mock = MagicMock()
    mock.get_job_dir.return_value = job_dir
    return mock


# ── Fixtures ──────────────────────────────────────────────────────────────────


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


# ── Tests GET /api/v1/jobs/{job_id}/brands ────────────────────────────────────


class TestObtenerMarcasJson:
    """Tests para el endpoint JSON de marcas (Fase 6.4)."""

    @pytest.mark.asyncio
    async def test_returns_brands_list_for_completed_job(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que el endpoint devuelve 200 con la lista de marcas cuando
        el job está COMPLETADO y marcas.csv existe.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id)
        storage = _storage_mock(tmp_path, job_id, _build_marcas_csv())
        redis = _redis_mock(status.model_dump_json())

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
            patch("api.v1.endpoints.jobs.get_storage_service", return_value=storage),
        ):
            response = await async_client.get(f"/api/v1/jobs/{job_id}/brands")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        brands = body["data"]["brands"]
        assert isinstance(brands, list)
        assert len(brands) == len(_SAMPLE_BRANDS)

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent_job(
        self, async_client: AsyncClient
    ) -> None:
        """
        Verifica que el endpoint devuelve 404 cuando el job no existe en Redis.
        """
        redis = _redis_mock(None)

        with patch("api.v1.endpoints.jobs._get_redis", return_value=redis):
            response = await async_client.get(f"/api/v1/jobs/{uuid.uuid4()}/brands")

        assert response.status_code == 404
        assert "detail" in response.json()

    @pytest.mark.asyncio
    async def test_returns_409_if_job_not_completed(
        self, async_client: AsyncClient
    ) -> None:
        """
        Verifica que el endpoint devuelve 409 cuando el job no ha completado.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id, EstadoJob.EN_PROCESO)
        redis = _redis_mock(status.model_dump_json())

        with patch("api.v1.endpoints.jobs._get_redis", return_value=redis):
            response = await async_client.get(f"/api/v1/jobs/{job_id}/brands")

        assert response.status_code == 409
        assert "detail" in response.json()

    @pytest.mark.asyncio
    async def test_response_includes_brands_resolved_and_not_found_counts(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que la respuesta incluye brands_resolved y brands_not_found.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id)
        storage = _storage_mock(tmp_path, job_id, _build_marcas_csv())
        redis = _redis_mock(status.model_dump_json())

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
            patch("api.v1.endpoints.jobs.get_storage_service", return_value=storage),
        ):
            response = await async_client.get(f"/api/v1/jobs/{job_id}/brands")

        assert response.status_code == 200
        data = response.json()["data"]
        assert "brands_resolved" in data
        assert "brands_not_found" in data
        # _SAMPLE_BRANDS: 3 resolved, 2 not_found/ean_invalido
        assert data["brands_resolved"] == 3
        assert data["brands_not_found"] == 2

    @pytest.mark.asyncio
    async def test_filters_by_source_returns_correct_subset(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que el endpoint devuelve entradas de todas las fuentes presentes
        en el CSV, sin filtrado en servidor (el filtrado es responsabilidad del frontend).
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id)
        storage = _storage_mock(tmp_path, job_id, _build_marcas_csv())
        redis = _redis_mock(status.model_dump_json())

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
            patch("api.v1.endpoints.jobs.get_storage_service", return_value=storage),
        ):
            response = await async_client.get(f"/api/v1/jobs/{job_id}/brands")

        brands = response.json()["data"]["brands"]
        sources_in_response = {b["source"] for b in brands}
        assert "amazon" in sources_in_response
        assert "cache_gs1" in sources_in_response
        assert "not_found" in sources_in_response


# ── Tests GET /api/v1/files/{job_id}/brands ───────────────────────────────────


class TestDescargarMarcasCsv:
    """Tests para el endpoint de descarga del CSV de marcas."""

    @pytest.mark.asyncio
    async def test_brands_csv_has_correct_headers(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que el CSV de marcas tiene las cabeceras esperadas:
        codigo, ean, brand_name, manufacturer, source, confidence.
        """
        job_id = str(uuid.uuid4())
        csv_bytes = _build_marcas_csv()
        storage = _storage_mock(tmp_path, job_id, csv_bytes)

        with patch("api.v1.endpoints.files.get_storage_service", return_value=storage):
            response = await async_client.get(f"/api/v1/files/{job_id}/brands")

        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")

        content = response.content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        assert reader.fieldnames is not None
        for field in _CSV_FIELDNAMES:
            assert field in reader.fieldnames, f"Falta la columna '{field}'"

    @pytest.mark.asyncio
    async def test_brands_csv_row_count_matches_resolved_brands(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que el número de filas del CSV coincide con el total de marcas.
        """
        job_id = str(uuid.uuid4())
        csv_bytes = _build_marcas_csv()
        storage = _storage_mock(tmp_path, job_id, csv_bytes)

        with patch("api.v1.endpoints.files.get_storage_service", return_value=storage):
            response = await async_client.get(f"/api/v1/files/{job_id}/brands")

        content = response.content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == len(_SAMPLE_BRANDS)

    @pytest.mark.asyncio
    async def test_brands_csv_not_found_entries_have_empty_brand_name(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que las entradas con source=not_found tienen brand_name vacío.
        """
        job_id = str(uuid.uuid4())
        csv_bytes = _build_marcas_csv()
        storage = _storage_mock(tmp_path, job_id, csv_bytes)

        with patch("api.v1.endpoints.files.get_storage_service", return_value=storage):
            response = await async_client.get(f"/api/v1/files/{job_id}/brands")

        content = response.content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            if row["source"] in ("not_found", "ean_invalido"):
                assert row["brand_name"] == "", (
                    f"brand_name debe estar vacío para source='{row['source']}', "
                    f"pero fue '{row['brand_name']}'"
                )

    @pytest.mark.asyncio
    async def test_brands_csv_returns_404_when_file_missing(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que el endpoint devuelve 404 cuando marcas.csv no existe.
        """
        job_id = str(uuid.uuid4())
        storage = _storage_mock(tmp_path, job_id, csv_bytes=None)

        with patch("api.v1.endpoints.files.get_storage_service", return_value=storage):
            response = await async_client.get(f"/api/v1/files/{job_id}/brands")

        assert response.status_code == 404
        assert "detail" in response.json()

    @pytest.mark.asyncio
    async def test_brands_json_returns_404_when_csv_missing(
        self, async_client: AsyncClient, tmp_path: Path
    ) -> None:
        """
        Verifica que el endpoint JSON devuelve 404 cuando marcas.csv no existe
        aunque el job esté COMPLETADO.
        """
        job_id = str(uuid.uuid4())
        status = _build_job_status(job_id)
        storage = _storage_mock(tmp_path, job_id, csv_bytes=None)
        redis = _redis_mock(status.model_dump_json())

        with (
            patch("api.v1.endpoints.jobs._get_redis", return_value=redis),
            patch("api.v1.endpoints.jobs.get_storage_service", return_value=storage),
        ):
            response = await async_client.get(f"/api/v1/jobs/{job_id}/brands")

        assert response.status_code == 404
        assert "detail" in response.json()
