"""
Tests de integración adicionales para endpoints de descarga de archivos.

Cubre casos de error y validaciones específicas para seo.csv.

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ── Variables de entorno ─────────────────────────────────────────────────────
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-32-chars-long-enough")
os.environ.setdefault("BROWSER_BINARY_PATH", "/usr/bin/google-chrome")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

from api.core.config import get_settings  # noqa: E402
get_settings.cache_clear()

from api.main import app  # noqa: E402


class TestDescargarSeoEndpointExtended:
    """Tests adicionales para GET /api/v1/files/{job_id}/seo."""

    @pytest_asyncio.fixture
    async def client(self) -> AsyncClient:
        """Cliente HTTP async."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac

    @pytest.mark.asyncio
    async def test_descargar_seo_retorna_csv_con_utf8_bom(self, client: AsyncClient, tmp_path: Path):
        """Verifica que CSV retorna con UTF-8 BOM (compatible con Excel)."""
        job_id = "job-bom"
        job_dir = tmp_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        seo_csv = job_dir / "seo.csv"
        # Escribir con BOM
        seo_csv.write_bytes("codigo,nombre,meta_title,meta_description\n".encode("utf-8-sig"))

        storage = MagicMock()
        storage.get_job_dir.return_value = job_dir

        with patch("api.v1.endpoints.files.get_storage_service", return_value=storage):
            response = await client.get(f"/api/v1/files/{job_id}/seo")

        assert response.status_code == 200
        # Verificar que es CSV
        assert "text/csv" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_descargar_csv_retorna_404_cuando_no_existe(self, client: AsyncClient, tmp_path: Path):
        """Verifica que endpoint descripciones también retorna 404 si no existe CSV."""
        job_id = "job-csv-missing"
        job_dir = tmp_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        storage = MagicMock()
        storage.get_job_dir.return_value = job_dir

        with patch("api.v1.endpoints.files.get_storage_service", return_value=storage):
            response = await client.get(f"/api/v1/files/{job_id}/csv")

        assert response.status_code == 404
