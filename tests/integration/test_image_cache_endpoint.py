"""
Tests de integración para la deduplicación de imágenes entre jobs.

Verifica que el campo imagenes_cache_hit se propaga correctamente
desde el pipeline hasta el JobStatus almacenado en Redis.

:author: BenjaminDTS
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "clave-de-prueba-super-segura-32c")
os.environ.setdefault("BROWSER_BINARY_PATH", "/usr/bin/google-chrome")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

from api.core.config import get_settings  # noqa: E402
get_settings.cache_clear()

from api.v1.schemas.job import EstadoJob, JobStatus  # noqa: E402
from workers.tasks import ejecutar_scraping  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_csv(n: int = 2) -> str:
    """CSV mínimo con n productos."""
    lines = ["codigo,nombre,marca,ean"]
    for i in range(1, n + 1):
        lines.append(f"P{i:03d},Producto {i},Marca{i},{i:013d}")
    return "\n".join(lines)


def _make_config_dict() -> dict:
    return {
        "tipo_job": "fotos",
        "modo": "nombre_marca",
        "imagenes_por_producto": 1,
        "select_photos": False,
        "validate_brands": False,
        "target_languages": [],
    }


def _job_status_with_cache_hit(job_id: str, hits: int) -> str:
    status = JobStatus(
        job_id=uuid.UUID(job_id),
        estado=EstadoJob.COMPLETADO,
        total_productos=2,
        productos_procesados=2,
        imagenes_descargadas=2,
        imagenes_cache_hit=hits,
    )
    return status.model_dump_json()


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestImageCacheHitCounting:
    def test_imagenes_cache_hit_is_zero_for_first_job_with_new_products(self, tmp_path):
        """
        En el primer job, sin caché previa, imagenes_cache_hit debe ser 0.
        El pipeline corre con ImageCacheService que no devuelve hits.
        """
        job_id = str(uuid.uuid4())
        redis_data: dict[str, str] = {}

        mock_redis = MagicMock()
        mock_redis.get.side_effect = lambda key: redis_data.get(key)
        mock_redis.set.side_effect = lambda key, val, **kw: redis_data.update({key: val})
        mock_redis.zadd.return_value = None
        mock_redis.delete.return_value = None
        mock_redis.close.return_value = None

        # Imagen descargada real para que la copia funcione
        fake_img = tmp_path / "fake.jpg"
        fake_img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        from services.scraper.consumer import ResultadoDescarga
        mock_resultados = [
            ResultadoDescarga(url="http://test/1.jpg", exitoso=True, ruta_guardada=str(fake_img))
        ]

        image_cache = MagicMock()
        image_cache.lookup.return_value = None  # sin hits

        with patch("workers.tasks._get_redis_client", return_value=mock_redis), \
             patch("services.scraper.pipeline.buscar_urls_imagenes", return_value=["http://test/1.jpg"]), \
             patch("services.scraper.pipeline.descargar_imagenes_producto", return_value=mock_resultados), \
             patch("services.scraper.pipeline.get_storage_service") as mock_storage_factory, \
             patch("services.scraper.image_cache.ImageCacheService", return_value=image_cache), \
             patch("api.core.config.get_settings") as mock_settings:

            settings = MagicMock()
            settings.image_cache_enabled = True
            settings.image_cache_db = tmp_path / "cache.db"
            settings.file_ttl_seconds = 3600
            settings.redis_url = "redis://localhost:6379/0"
            mock_settings.return_value = settings

            storage = MagicMock()
            storage.create_zip.return_value = tmp_path / f"{job_id}.zip"
            mock_storage_factory.return_value = storage

            ejecutar_scraping(job_id, _make_csv(2), _make_config_dict())

        # Verificar que el JobStatus en Redis tiene imagenes_cache_hit=0
        job_key = f"job:{job_id}"
        assert job_key in redis_data
        status = JobStatus.model_validate_json(redis_data[job_key])
        assert status.imagenes_cache_hit == 0

    def test_imagenes_cache_hit_is_greater_than_zero_when_same_eans_reprocessed(self, tmp_path):
        """
        Cuando hay cache hits (lookup devuelve paths válidos), el contador
        imagenes_cache_hit debe ser mayor que 0 en el JobStatus final.
        """
        job_id = str(uuid.uuid4())
        redis_data: dict[str, str] = {}

        mock_redis = MagicMock()
        mock_redis.get.side_effect = lambda key: redis_data.get(key)
        mock_redis.set.side_effect = lambda key, val, **kw: redis_data.update({key: val})
        mock_redis.zadd.return_value = None
        mock_redis.delete.return_value = None
        mock_redis.close.return_value = None

        # Imagen cacheada real en disco
        cached_img = tmp_path / "cached.jpg"
        cached_img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        copied_img = tmp_path / "dest.jpg"
        copied_img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        image_cache = MagicMock()
        image_cache.lookup.return_value = cached_img  # todos son hits

        with patch("workers.tasks._get_redis_client", return_value=mock_redis), \
             patch("services.scraper.pipeline.buscar_urls_imagenes") as mock_prod, \
             patch("services.scraper.pipeline.get_storage_service") as mock_storage_factory, \
             patch("services.scraper.image_cache.ImageCacheService", return_value=image_cache), \
             patch("api.core.config.get_settings") as mock_settings:

            settings = MagicMock()
            settings.image_cache_enabled = True
            settings.image_cache_db = tmp_path / "cache.db"
            settings.file_ttl_seconds = 3600
            settings.redis_url = "redis://localhost:6379/0"
            mock_settings.return_value = settings

            storage = MagicMock()
            storage.copy_from_cache.return_value = copied_img
            storage.create_zip.return_value = tmp_path / f"{job_id}.zip"
            mock_storage_factory.return_value = storage

            ejecutar_scraping(job_id, _make_csv(2), _make_config_dict())

        # Selenium no debe haber sido llamado
        mock_prod.assert_not_called()

        job_key = f"job:{job_id}"
        assert job_key in redis_data
        status = JobStatus.model_validate_json(redis_data[job_key])
        assert status.imagenes_cache_hit == 2

    def test_job_with_disabled_cache_always_downloads_all_images(self, tmp_path):
        """
        Con IMAGE_CACHE_ENABLED=false, el pipeline no consulta la caché y
        imagenes_cache_hit queda en 0.
        """
        job_id = str(uuid.uuid4())
        redis_data: dict[str, str] = {}

        mock_redis = MagicMock()
        mock_redis.get.side_effect = lambda key: redis_data.get(key)
        mock_redis.set.side_effect = lambda key, val, **kw: redis_data.update({key: val})
        mock_redis.zadd.return_value = None
        mock_redis.delete.return_value = None
        mock_redis.close.return_value = None

        fake_img = tmp_path / "fake.jpg"
        fake_img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        from services.scraper.consumer import ResultadoDescarga
        mock_resultados = [
            ResultadoDescarga(url="http://test/1.jpg", exitoso=True, ruta_guardada=str(fake_img))
        ]

        settings = MagicMock()
        settings.image_cache_enabled = False  # caché deshabilitada
        settings.file_ttl_seconds = 3600
        settings.redis_url = "redis://localhost:6379/0"

        storage = MagicMock()
        storage.create_zip.return_value = tmp_path / f"{job_id}.zip"

        with patch("workers.tasks._get_redis_client", return_value=mock_redis), \
             patch("services.scraper.pipeline.buscar_urls_imagenes", return_value=["http://test/1.jpg"]) as mock_prod, \
             patch("services.scraper.pipeline.descargar_imagenes_producto", return_value=mock_resultados), \
             patch("services.scraper.pipeline.get_storage_service", return_value=storage), \
             patch("services.scraper.pipeline.get_settings", return_value=settings), \
             patch("workers.tasks.get_settings", return_value=settings):

            ejecutar_scraping(job_id, _make_csv(2), _make_config_dict())

        # Selenium debe haberse llamado (sin caché)
        assert mock_prod.call_count == 2

        job_key = f"job:{job_id}"
        assert job_key in redis_data
        status = JobStatus.model_validate_json(redis_data[job_key])
        assert status.imagenes_cache_hit == 0
