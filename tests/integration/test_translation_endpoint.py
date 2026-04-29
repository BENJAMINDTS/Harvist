"""
Tests de integración para el endpoint de traducciones (Fase 7.2).

Cubre:
- Descarga exitosa de CSV de traducciones para idioma válido
- Respuesta 404 cuando el CSV no existe
- Respuesta 400 para idioma no soportado
- Cabecera Content-Disposition correcta
- Content-Type text/csv
- Validación de todos los idiomas soportados
- Compatibilidad UTF-8 BOM para Excel

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


class TestDescargarTraducciones:
    """Suite de tests para GET /api/v1/files/{job_id}/translations/{lang}."""

    @pytest_asyncio.fixture
    async def client(self) -> AsyncClient:
        """Cliente HTTP async."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac

    @pytest.mark.asyncio
    async def test_descarga_exitosa_csv_en(self, client: AsyncClient, tmp_path: Path):
        """Verifica descarga exitosa del CSV de traducciones al inglés."""
        job_id = "job-trad-en"
        job_dir = tmp_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        csv_content = (
            "codigo,nombre,marca,categoria,idioma,descripcion_corta,descripcion_larga,"
            "keywords,meta_description,exitoso,error\n"
            "PROD001,Dog food,Royal Canin,Food,en,Premium nutrition.,Complete food.,dog food,Dog food.,True,\n"
        )
        (job_dir / "traducciones_en.csv").write_bytes(csv_content.encode("utf-8-sig"))

        storage = MagicMock()
        storage.get_job_dir.return_value = job_dir

        with patch("api.v1.endpoints.files.get_storage_service", return_value=storage):
            response = await client.get(f"/api/v1/files/{job_id}/translations/en")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_content_type_es_csv(self, client: AsyncClient, tmp_path: Path):
        """Verifica que el Content-Type es text/csv."""
        job_id = "job-trad-ct"
        job_dir = tmp_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "traducciones_fr.csv").write_bytes(b"codigo,idioma\nPROD001,fr\n")

        storage = MagicMock()
        storage.get_job_dir.return_value = job_dir

        with patch("api.v1.endpoints.files.get_storage_service", return_value=storage):
            response = await client.get(f"/api/v1/files/{job_id}/translations/fr")

        assert "text/csv" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_content_disposition_contiene_nombre_archivo(
        self, client: AsyncClient, tmp_path: Path
    ):
        """Verifica que Content-Disposition incluye el nombre del archivo correcto."""
        job_id = "abcd1234-5678-90ef-ghij-klmnopqrstuv"
        job_dir = tmp_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "traducciones_de.csv").write_bytes(b"codigo,idioma\nPROD001,de\n")

        storage = MagicMock()
        storage.get_job_dir.return_value = job_dir

        with patch("api.v1.endpoints.files.get_storage_service", return_value=storage):
            response = await client.get(f"/api/v1/files/{job_id}/translations/de")

        disposition = response.headers.get("content-disposition", "")
        assert "descripciones_de_" in disposition
        assert ".csv" in disposition

    @pytest.mark.asyncio
    async def test_retorna_404_si_csv_no_existe(self, client: AsyncClient, tmp_path: Path):
        """Verifica que retorna 404 cuando el CSV de traducción no existe."""
        job_id = "job-trad-missing"
        job_dir = tmp_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        storage = MagicMock()
        storage.get_job_dir.return_value = job_dir

        with patch("api.v1.endpoints.files.get_storage_service", return_value=storage):
            response = await client.get(f"/api/v1/files/{job_id}/translations/en")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_retorna_400_para_idioma_no_soportado(self, client: AsyncClient):
        """Verifica que retorna 400 para idioma no en SUPPORTED_LANGUAGES."""
        response = await client.get("/api/v1/files/cualquier-job/translations/zh")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_retorna_400_para_idioma_invalido(self, client: AsyncClient):
        """Verifica que retorna 400 para código de idioma inválido."""
        response = await client.get("/api/v1/files/cualquier-job/translations/xx")
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_todos_idiomas_soportados_retornan_200(
        self, client: AsyncClient, tmp_path: Path
    ):
        """Verifica que todos los idiomas de SUPPORTED_LANGUAGES devuelven 200 si el CSV existe."""
        from api.v1.schemas.job import SUPPORTED_LANGUAGES

        job_id = "job-all-langs"
        job_dir = tmp_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        idiomas_traducibles = [l for l in SUPPORTED_LANGUAGES if l != "es"]
        for lang in idiomas_traducibles:
            (job_dir / f"traducciones_{lang}.csv").write_bytes(
                f"codigo,idioma\nPROD001,{lang}\n".encode("utf-8")
            )

        storage = MagicMock()
        storage.get_job_dir.return_value = job_dir

        with patch("api.v1.endpoints.files.get_storage_service", return_value=storage):
            for lang in idiomas_traducibles:
                response = await client.get(f"/api/v1/files/{job_id}/translations/{lang}")
                assert response.status_code == 200, f"Falló para idioma: {lang}"

    @pytest.mark.asyncio
    async def test_csv_con_utf8_bom(self, client: AsyncClient, tmp_path: Path):
        """Verifica que el CSV se retorna con UTF-8 BOM (compatible con Excel)."""
        job_id = "job-trad-bom"
        job_dir = tmp_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        header = "codigo,nombre,idioma\n"
        (job_dir / "traducciones_it.csv").write_bytes(header.encode("utf-8-sig"))

        storage = MagicMock()
        storage.get_job_dir.return_value = job_dir

        with patch("api.v1.endpoints.files.get_storage_service", return_value=storage):
            response = await client.get(f"/api/v1/files/{job_id}/translations/it")

        assert response.status_code == 200
        assert response.content[:3] == b"\xef\xbb\xbf"
