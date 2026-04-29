"""
Tests de integración para el servicio SeoPipeline (Fase 7.1).

Cubre:
  SeoPipeline.ejecutar() — generación batch de SEO con callback de progreso

Storage se simula con archivos temporales. ClaudeClient (Groq) se mockea.

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Variables de entorno antes de importar servicios ───────────────────────────
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "clave-de-prueba-super-segura-32c")
os.environ.setdefault("BROWSER_BINARY_PATH", "/usr/bin/google-chrome")

from api.core.config import get_settings  # noqa: E402
get_settings.cache_clear()

from services.ai.seo_pipeline import SeoPipeline  # noqa: E402
from api.v1.schemas.job import SearchConfig, TipoJob, ModosBusqueda  # noqa: E402


# ── Test helpers ──────────────────────────────────────────────────────────────

_SAMPLE_CSV_CONTENT = """codigo,nombre,marca,categoria
001,Alimento para perros,Royal Canin,Alimentos
002,Juguete Kong,Kong,Juguetes
003,Collar antiparásito,Seresto,Accesorios
"""

_GROQ_RESPONSE = json.dumps({
    "productos": [
        {
            "id_interno": "001",
            "meta_title": "Alimento perros premium nutrición",
            "meta_description": "Alimento completo y equilibrado para tu perro.",
        },
        {
            "id_interno": "002",
            "meta_title": "Juguete Kong goma resistente",
            "meta_description": "Juguete duradero perfecto para jugar.",
        },
        {
            "id_interno": "003",
            "meta_title": "Collar antiparásito perros",
            "meta_description": "Protección contra parásitos externos.",
        },
    ]
})


class TestSeoPipelineEjecutar:
    """Suite de tests para SeoPipeline.ejecutar()."""

    @pytest.fixture
    def storage_mock(self, tmp_path: Path) -> MagicMock:
        """Mock de StorageService."""
        mock = MagicMock()
        mock.get_job_dir.return_value = tmp_path / "job_001"
        (tmp_path / "job_001").mkdir(parents=True, exist_ok=True)

        def save_image_side_effect(job_id, filename, content):
            job_dir = tmp_path / str(job_id)
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / filename).write_bytes(content)

        mock.save_image.side_effect = save_image_side_effect
        return mock

    @pytest.fixture
    def config(self) -> SearchConfig:
        """Configuración de búsqueda para SEO."""
        return SearchConfig(
            store_type_usuario="tiendas de mascotas",
            tipo_job=TipoJob.SEO,
            modo_busqueda=ModosBusqueda.NOMBRE_MARCA,
            groq_api_key_usuario="",
        )

    @pytest.fixture
    def claude_client_mock(self) -> MagicMock:
        """Mock de ClaudeClient que devuelve respuesta JSON."""
        mock = MagicMock()
        mock.completar.return_value = _GROQ_RESPONSE
        return mock

    def test_ejecutar_genera_seo_csv(self, tmp_path: Path, config: SearchConfig, claude_client_mock: MagicMock):
        """Verifica que ejecutar() crea seo.csv con las filas correctas."""
        job_id = "job_001"
        job_dir = tmp_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        storage = MagicMock()
        storage.get_job_dir.return_value = job_dir

        def save_image_side_effect(job_id, filename, content):
            (job_dir / filename).write_bytes(content)

        storage.save_image.side_effect = save_image_side_effect

        pipeline = SeoPipeline(job_id=job_id, config=config, storage=storage)

        with patch("services.ai.seo_pipeline.ClaudeClient", return_value=claude_client_mock):
            resumen = pipeline.ejecutar(contenido_csv=_SAMPLE_CSV_CONTENT)

        # Verificar que seo.csv fue creado
        seo_csv = job_dir / "seo.csv"
        assert seo_csv.exists()

        # Verificar contenido
        reader = csv.DictReader(io.StringIO(seo_csv.read_text(encoding="utf-8-sig")))
        rows = list(reader)
        assert len(rows) == 3
        assert rows[0]["codigo"] == "001"
        assert rows[0]["meta_title"] == "Alimento perros premium nutrición"

    def test_ejecutar_retorna_resumen_correcto(self, tmp_path: Path, config: SearchConfig, claude_client_mock: MagicMock):
        """Verifica que ejecutar() retorna dict con total_productos, seo_generados, seo_errores."""
        job_id = "job_001"
        job_dir = tmp_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        storage = MagicMock()
        storage.get_job_dir.return_value = job_dir

        def save_image_side_effect(job_id, filename, content):
            (job_dir / filename).write_bytes(content)

        storage.save_image.side_effect = save_image_side_effect

        pipeline = SeoPipeline(job_id=job_id, config=config, storage=storage)

        with patch("services.ai.seo_pipeline.ClaudeClient", return_value=claude_client_mock):
            resumen = pipeline.ejecutar(contenido_csv=_SAMPLE_CSV_CONTENT)

        assert "total_productos" in resumen
        assert "seo_generados" in resumen
        assert "seo_errores" in resumen
        assert resumen["total_productos"] == 3
        assert resumen["seo_generados"] == 3
        assert resumen["seo_errores"] == 0

    def test_ejecutar_con_callback_de_progreso(self, tmp_path: Path, config: SearchConfig, claude_client_mock: MagicMock):
        """Verifica que callback es llamado con progreso."""
        job_id = "job_001"
        job_dir = tmp_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        storage = MagicMock()
        storage.get_job_dir.return_value = job_dir

        def save_image_side_effect(job_id, filename, content):
            (job_dir / filename).write_bytes(content)

        storage.save_image.side_effect = save_image_side_effect

        pipeline = SeoPipeline(job_id=job_id, config=config, storage=storage)

        callback_calls = []

        def callback(jid, procesados, total, seo_ok):
            callback_calls.append((jid, procesados, total, seo_ok))

        with patch("services.ai.seo_pipeline.ClaudeClient", return_value=claude_client_mock):
            resumen = pipeline.ejecutar(contenido_csv=_SAMPLE_CSV_CONTENT, callback=callback)

        # Callback debe haber sido llamado
        assert len(callback_calls) > 0
        # Último call debe tener todos los productos procesados
        assert callback_calls[-1][1] == 3  # procesados
        assert callback_calls[-1][2] == 3  # total
        assert callback_calls[-1][3] == 3  # seo_ok

    def test_ejecutar_meta_title_nunca_excede_60_chars(self, tmp_path: Path, config: SearchConfig, claude_client_mock: MagicMock):
        """Verifica que meta_title en CSV siempre <= 60 caracteres (truncado inteligente)."""
        job_id = "job_001"
        job_dir = tmp_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        storage = MagicMock()
        storage.get_job_dir.return_value = job_dir

        def save_image_side_effect(job_id, filename, content):
            (job_dir / filename).write_bytes(content)

        storage.save_image.side_effect = save_image_side_effect

        # Respuesta con meta_title que excede límite
        groq_response_long = json.dumps({
            "productos": [
                {
                    "id_interno": "001",
                    "meta_title": "Alimento para perros premium con nutrientes vitaminas minerales completo excelente",
                    "meta_description": "Descripción normal.",
                },
            ]
        })
        claude_client_mock.completar.return_value = groq_response_long

        pipeline = SeoPipeline(job_id=job_id, config=config, storage=storage)

        with patch("services.ai.seo_pipeline.ClaudeClient", return_value=claude_client_mock):
            resumen = pipeline.ejecutar(contenido_csv=_SAMPLE_CSV_CONTENT)

        seo_csv = job_dir / "seo.csv"
        reader = csv.DictReader(io.StringIO(seo_csv.read_text(encoding="utf-8-sig")))
        for row in reader:
            assert len(row["meta_title"]) <= 60

    def test_ejecutar_meta_description_nunca_excede_160_chars(self, tmp_path: Path, config: SearchConfig, claude_client_mock: MagicMock):
        """Verifica que meta_description en CSV siempre <= 160 caracteres."""
        job_id = "job_001"
        job_dir = tmp_path / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        storage = MagicMock()
        storage.get_job_dir.return_value = job_dir

        def save_image_side_effect(job_id, filename, content):
            (job_dir / filename).write_bytes(content)

        storage.save_image.side_effect = save_image_side_effect

        # Respuesta con meta_description que excede límite
        groq_response_long = json.dumps({
            "productos": [
                {
                    "id_interno": "001",
                    "meta_title": "Alimento perros",
                    "meta_description": "Alimento completo y equilibrado para tu perro con todas las vitaminas y minerales necesarios para su desarrollo óptimo. Ingredientes naturales seleccionados.",
                },
            ]
        })
        claude_client_mock.completar.return_value = groq_response_long

        pipeline = SeoPipeline(job_id=job_id, config=config, storage=storage)

        with patch("services.ai.seo_pipeline.ClaudeClient", return_value=claude_client_mock):
            resumen = pipeline.ejecutar(contenido_csv=_SAMPLE_CSV_CONTENT)

        seo_csv = job_dir / "seo.csv"
        reader = csv.DictReader(io.StringIO(seo_csv.read_text(encoding="utf-8-sig")))
        for row in reader:
            assert len(row["meta_description"]) <= 160
