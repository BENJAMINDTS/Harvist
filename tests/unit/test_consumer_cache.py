"""
Tests unitarios para la integración de caché en el pipeline de scraping.

Verifica que el lookup de caché ocurre antes de Selenium y que el registro
ocurre después de la validación Pillow exitosa.

:author: BenjaminDTS
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from api.v1.schemas.job import ModosBusqueda, SearchConfig
from services.csv_parser import Producto
from services.scraper.image_cache import ImageCacheService
from services.scraper.pipeline import ScrapingPipeline

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_producto(codigo: str = "P001", ean: str = "1234567890123") -> Producto:
    return Producto(
        codigo=codigo,
        nombre="Producto Test",
        ean=ean,
        query=f"{codigo} test",
    )


def _make_config() -> SearchConfig:
    return SearchConfig(modo=ModosBusqueda.NOMBRE_MARCA, imagenes_por_producto=1)


def _make_pipeline(image_cache, storage=None) -> ScrapingPipeline:
    if storage is None:
        storage = MagicMock()
    return ScrapingPipeline(
        job_id="job-test",
        config=_make_config(),
        storage=storage,
        image_cache=image_cache,
    )


# ── Tests: cache hit ──────────────────────────────────────────────────────────


class TestCacheHit:
    def test_skips_selenium_when_cache_hit_found(self, tmp_path):
        """Cuando hay cache hit, buscar_urls_imagenes no debe llamarse."""
        cached_img = tmp_path / "cached.jpg"
        cached_img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        image_cache = MagicMock(spec=ImageCacheService)
        image_cache.lookup.return_value = cached_img

        storage = MagicMock()
        storage.copy_from_cache.return_value = tmp_path / "dest.jpg"

        pipeline = _make_pipeline(image_cache, storage)

        with patch("services.scraper.pipeline.buscar_urls_imagenes") as mock_producer:
            ok, fail = pipeline._procesar_producto(_make_producto())

        mock_producer.assert_not_called()
        assert ok == 1
        assert fail == 0

    def test_copies_from_cache_when_cache_hit_found(self, tmp_path):
        """Cuando hay cache hit, se llama copy_from_cache con los args correctos."""
        cached_img = tmp_path / "cached.jpg"
        cached_img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        image_cache = MagicMock(spec=ImageCacheService)
        image_cache.lookup.return_value = cached_img

        storage = MagicMock()
        storage.copy_from_cache.return_value = tmp_path / "dest.jpg"

        pipeline = _make_pipeline(image_cache, storage)
        producto = _make_producto(codigo="P001", ean="1234567890123")

        with patch("services.scraper.pipeline.buscar_urls_imagenes"):
            pipeline._procesar_producto(producto)

        storage.copy_from_cache.assert_called_once_with(
            cached_img,
            "job-test",  # carpeta_id
            "P001",
        )

    def test_increments_cache_hit_counter_on_cache_hit(self, tmp_path):
        """El contador _cache_hits del pipeline se incrementa en cada hit."""
        cached_img = tmp_path / "cached.jpg"
        cached_img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        image_cache = MagicMock(spec=ImageCacheService)
        image_cache.lookup.return_value = cached_img

        storage = MagicMock()
        storage.copy_from_cache.return_value = tmp_path / "dest.jpg"

        pipeline = _make_pipeline(image_cache, storage)
        assert pipeline._cache_hits == 0

        with patch("services.scraper.pipeline.buscar_urls_imagenes"):
            pipeline._procesar_producto(_make_producto(codigo="P001"))
            pipeline._procesar_producto(_make_producto(codigo="P002"))

        assert pipeline._cache_hits == 2


# ── Tests: cache miss → register after download ───────────────────────────────


class TestCacheMiss:
    def test_registers_image_in_cache_after_successful_download(self, tmp_path):
        """Tras descarga exitosa, register() se llama con la ruta de la imagen."""
        saved_img = tmp_path / "job-test" / "P001_001.jpg"
        saved_img.parent.mkdir(parents=True, exist_ok=True)
        # Crear una imagen JPEG real con Pillow para que Image.open funcione
        from PIL import Image as PilImage
        img = PilImage.new("RGB", (100, 100), color=(255, 0, 0))
        img.save(str(saved_img), format="JPEG")

        image_cache = MagicMock(spec=ImageCacheService)
        image_cache.lookup.return_value = None  # cache miss

        storage = MagicMock()

        from services.scraper.consumer import ResultadoDescarga
        mock_resultados = [
            ResultadoDescarga(url="http://img.test/1.jpg", exitoso=True, ruta_guardada=str(saved_img))
        ]

        pipeline = _make_pipeline(image_cache, storage)

        with patch("services.scraper.pipeline.buscar_urls_imagenes", return_value=["http://img.test/1.jpg"]), \
             patch("services.scraper.pipeline.descargar_imagenes_producto", return_value=mock_resultados):
            pipeline._procesar_producto(_make_producto())

        image_cache.register.assert_called_once()
        call_kwargs = image_cache.register.call_args
        assert call_kwargs.kwargs["codigo"] == "P001"
        assert call_kwargs.kwargs["path"] == saved_img

    def test_does_not_register_in_cache_if_no_successful_download(self, tmp_path):
        """Si la descarga falla (ok=0), no se llama a register()."""
        image_cache = MagicMock(spec=ImageCacheService)
        image_cache.lookup.return_value = None

        storage = MagicMock()

        from services.scraper.consumer import ResultadoDescarga
        mock_resultados = [
            ResultadoDescarga(url="http://img.test/bad.jpg", exitoso=False, error="timeout")
        ]

        pipeline = _make_pipeline(image_cache, storage)

        with patch("services.scraper.pipeline.buscar_urls_imagenes", return_value=["http://img.test/bad.jpg"]), \
             patch("services.scraper.pipeline.descargar_imagenes_producto", return_value=mock_resultados):
            pipeline._procesar_producto(_make_producto())

        image_cache.register.assert_not_called()

    def test_falls_back_to_selenium_when_cache_lookup_returns_none(self, tmp_path):
        """Si lookup devuelve None, se llama a buscar_urls_imagenes."""
        image_cache = MagicMock(spec=ImageCacheService)
        image_cache.lookup.return_value = None

        storage = MagicMock()

        from services.scraper.consumer import ResultadoDescarga
        mock_resultados = [
            ResultadoDescarga(url="http://img.test/1.jpg", exitoso=True, ruta_guardada=str(tmp_path / "img.jpg"))
        ]

        pipeline = _make_pipeline(image_cache, storage)

        with patch("services.scraper.pipeline.buscar_urls_imagenes", return_value=["http://img.test/1.jpg"]) as mock_prod, \
             patch("services.scraper.pipeline.descargar_imagenes_producto", return_value=mock_resultados):
            pipeline._procesar_producto(_make_producto())

        mock_prod.assert_called_once()

    def test_falls_back_to_selenium_when_copy_from_cache_raises_error(self, tmp_path):
        """Si copy_from_cache lanza excepción, se procede con descarga normal."""
        cached_img = tmp_path / "cached.jpg"
        cached_img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        image_cache = MagicMock(spec=ImageCacheService)
        image_cache.lookup.return_value = cached_img

        storage = MagicMock()
        storage.copy_from_cache.side_effect = OSError("disco lleno")

        from services.scraper.consumer import ResultadoDescarga
        mock_resultados = [
            ResultadoDescarga(url="http://img.test/1.jpg", exitoso=True, ruta_guardada=str(tmp_path / "img.jpg"))
        ]

        pipeline = _make_pipeline(image_cache, storage)

        with patch("services.scraper.pipeline.buscar_urls_imagenes", return_value=["http://img.test/1.jpg"]) as mock_prod, \
             patch("services.scraper.pipeline.descargar_imagenes_producto", return_value=mock_resultados):
            ok, fail = pipeline._procesar_producto(_make_producto())

        # Debe haber caído en el flujo normal de Selenium
        mock_prod.assert_called_once()
        assert ok == 1


# ── Tests: cache disabled ─────────────────────────────────────────────────────


class TestCacheDisabled:
    def test_skips_all_cache_logic_when_image_cache_is_none(self, tmp_path):
        """Con image_cache=None, nunca se llama al caché."""
        storage = MagicMock()

        from services.scraper.consumer import ResultadoDescarga
        mock_resultados = [
            ResultadoDescarga(url="http://img.test/1.jpg", exitoso=True, ruta_guardada=str(tmp_path / "img.jpg"))
        ]

        # Pasar None como image_cache explícitamente (como si IMAGE_CACHE_ENABLED=false)
        pipeline = ScrapingPipeline(
            job_id="job-test",
            config=_make_config(),
            storage=storage,
            image_cache=None,
        )

        with patch("services.scraper.pipeline.buscar_urls_imagenes", return_value=["http://img.test/1.jpg"]) as mock_prod, \
             patch("services.scraper.pipeline.descargar_imagenes_producto", return_value=mock_resultados):
            ok, fail = pipeline._procesar_producto(_make_producto())

        mock_prod.assert_called_once()
        assert pipeline._cache_hits == 0
        assert ok == 1
