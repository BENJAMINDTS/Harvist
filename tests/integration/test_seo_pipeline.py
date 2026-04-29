"""
Tests de integración para el pipeline de SEO (Fase 7.1) y endpoint de descarga.

Cubre:
  GET  /api/v1/files/{job_id}/seo  — Descarga de seo.csv

Redis y Celery se mockean. El storage se simula con archivos temporales.

:author: BenjaminDTS
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
from api.v1.schemas.job import EstadoJob, JobStatus  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

_SAMPLE_SEO = [
    {"codigo": "001", "nombre": "Alimento para perros", "meta_title": "Alimento perros premium", "meta_description": "Nutrición completa."},
    {"codigo": "002", "nombre": "Juguete Kong", "meta_title": "Juguete goma Kong", "meta_description": "Resistente y duradero."},
    {"codigo": "003", "nombre": "Collar antiparásito", "meta_title": "Collar antiparásito perros", "meta_description": "Protección máxima."},
]

_SEO_FIELDNAMES = ["codigo", "nombre", "meta_title", "meta_description"]


def _build_seo_csv(rows: list[dict] | None = None) -> bytes:
    """Serializa filas a CSV UTF-8 con BOM (igual que seo_pipeline)."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_SEO_FIELDNAMES)
    writer.writeheader()
    for row in (rows or _SAMPLE_SEO):
        writer.writerow(row)
    return buf.getvalue().encode("utf-8-sig")


def _build_job_status(job_id: str, estado: EstadoJob = EstadoJob.COMPLETADO) -> JobStatus:
    """Construye un JobStatus de prueba."""
    return JobStatus(
        job_id=uuid.UUID(job_id),
        estado=estado,
        total_productos=len(_SAMPLE_SEO),
        seo_generados=len(_SAMPLE_SEO),
        seo_errores=0,
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
    Mock de StorageService que devuelve un directorio temporal con seo.csv.

    Si csv_bytes es None no crea el archivo (simula job sin seo.csv).
    """
    job_dir = tmp_path / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    if csv_bytes is not None:
        (job_dir / "seo.csv").write_bytes(csv_bytes)

    mock = MagicMock()
    mock.get_job_dir.return_value = job_dir
    return mock


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestDescargarSeoCsv:
    """Suite de tests para descargar seo.csv."""

    @pytest_asyncio.fixture
    async def client(self) -> AsyncClient:
        """Cliente HTTP async para la API."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac

    @pytest.mark.asyncio
    async def test_seo_csv_returns_200_with_correct_headers(self, client: AsyncClient, tmp_path: Path):
        """Verifica que endpoint devuelve CSV con headers correctos."""
        job_id = str(uuid.uuid4())
        seo_bytes = _build_seo_csv()
        storage = _storage_mock(tmp_path, job_id, seo_bytes)

        with patch("api.v1.endpoints.files.get_storage_service", return_value=storage):
            response = await client.get(f"/api/v1/files/{job_id}/seo")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert "attachment" in response.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_seo_csv_row_count_matches_input(self, client: AsyncClient, tmp_path: Path):
        """Verifica que cantidad de filas en CSV descargado es correcta."""
        job_id = str(uuid.uuid4())
        seo_bytes = _build_seo_csv()
        storage = _storage_mock(tmp_path, job_id, seo_bytes)

        with patch("api.v1.endpoints.files.get_storage_service", return_value=storage):
            response = await client.get(f"/api/v1/files/{job_id}/seo")

        assert response.status_code == 200
        lines = response.text.strip().split("\n")
        # 1 header + 3 data rows
        assert len(lines) == 4

    @pytest.mark.asyncio
    async def test_seo_csv_has_correct_fieldnames(self, client: AsyncClient, tmp_path: Path):
        """Verifica que CSV tiene las columnas correctas."""
        job_id = str(uuid.uuid4())
        seo_bytes = _build_seo_csv()
        storage = _storage_mock(tmp_path, job_id, seo_bytes)

        with patch("api.v1.endpoints.files.get_storage_service", return_value=storage):
            response = await client.get(f"/api/v1/files/{job_id}/seo")

        assert response.status_code == 200
        # Leer manualmente para manejar BOM y line endings correctamente
        lines = response.text.strip().split("\n")
        header = [f.strip() for f in lines[0].lstrip("﻿").split(",")]
        assert header == _SEO_FIELDNAMES

    @pytest.mark.asyncio
    async def test_seo_csv_returns_404_when_file_missing(self, client: AsyncClient, tmp_path: Path):
        """Verifica que retorna 404 si seo.csv no existe."""
        job_id = str(uuid.uuid4())
        storage = _storage_mock(tmp_path, job_id, None)  # No crea CSV

        with patch("api.v1.endpoints.files.get_storage_service", return_value=storage):
            response = await client.get(f"/api/v1/files/{job_id}/seo")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_seo_csv_content_matches_source(self, client: AsyncClient, tmp_path: Path):
        """Verifica que contenido descargado coincide con lo guardado."""
        job_id = str(uuid.uuid4())
        custom_rows = [
            {"codigo": "TEST001", "nombre": "Test Producto", "meta_title": "Title", "meta_description": "Desc"},
        ]
        seo_bytes = _build_seo_csv(custom_rows)
        storage = _storage_mock(tmp_path, job_id, seo_bytes)

        with patch("api.v1.endpoints.files.get_storage_service", return_value=storage):
            response = await client.get(f"/api/v1/files/{job_id}/seo")

        assert response.status_code == 200
        # Manejar BOM correctamente
        text = response.text
        if text.startswith("﻿"):
            text = text[1:]
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["codigo"] == "TEST001"
        assert rows[0]["nombre"] == "Test Producto"
        assert rows[0]["meta_title"] == "Title"
        assert rows[0]["meta_description"] == "Desc"

    @pytest.mark.asyncio
    async def test_seo_csv_meta_titles_under_60_chars(self, client: AsyncClient, tmp_path: Path):
        """Verifica que meta_title en CSV no excede 60 caracteres."""
        job_id = str(uuid.uuid4())
        seo_bytes = _build_seo_csv()
        storage = _storage_mock(tmp_path, job_id, seo_bytes)

        with patch("api.v1.endpoints.files.get_storage_service", return_value=storage):
            response = await client.get(f"/api/v1/files/{job_id}/seo")

        assert response.status_code == 200
        reader = csv.DictReader(io.StringIO(response.text))
        for row in reader:
            assert len(row["meta_title"]) <= 60, f"meta_title exceeds 60: {row['meta_title']}"

    @pytest.mark.asyncio
    async def test_seo_csv_meta_descriptions_under_160_chars(self, client: AsyncClient, tmp_path: Path):
        """Verifica que meta_description en CSV no excede 160 caracteres."""
        job_id = str(uuid.uuid4())
        seo_bytes = _build_seo_csv()
        storage = _storage_mock(tmp_path, job_id, seo_bytes)

        with patch("api.v1.endpoints.files.get_storage_service", return_value=storage):
            response = await client.get(f"/api/v1/files/{job_id}/seo")

        assert response.status_code == 200
        reader = csv.DictReader(io.StringIO(response.text))
        for row in reader:
            assert len(row["meta_description"]) <= 160, f"meta_description exceeds 160: {row['meta_description']}"
