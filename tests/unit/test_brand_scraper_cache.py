"""
Tests unitarios para la separación resolución/escritura en brand_scraper (Fase 7.4).

Verifica que GS1PrefixCache registra correctamente prefijos nuevos, que
get_learned_prefixes excluye los prefijos ya presentes en el semillero, y que
BrandPipeline._persist_brand_cache escribe en brand_cache.json únicamente cuando
write_cache=True.

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "clave-de-prueba-super-segura-32c")
os.environ.setdefault("BROWSER_BINARY_PATH", "/usr/bin/google-chrome")

from api.core.config import get_settings  # noqa: E402
get_settings.cache_clear()

from services.scraper.brand_cache import GS1PrefixCache  # noqa: E402


# ── Tests GS1PrefixCache ──────────────────────────────────────────────────────

def test_current_prefix_keys_empty_on_init(tmp_path: Path) -> None:
    """Una caché inicializada sin semilla no tiene prefijos."""
    cache = GS1PrefixCache(seed_path=str(tmp_path / "empty_seed.json"))
    assert cache.current_prefix_keys() == set()


def test_register_and_current_prefix_keys(tmp_path: Path) -> None:
    """Tras register(), current_prefix_keys() incluye el nuevo prefijo."""
    cache = GS1PrefixCache(seed_path=str(tmp_path / "empty_seed.json"))
    cache.register("1234567", "TestBrand", "ES", source="amazon", confidence="high", ean="1234567000000")
    assert "1234567" in cache.current_prefix_keys()


def test_get_learned_prefixes_returns_only_new_ones(tmp_path: Path) -> None:
    """get_learned_prefixes devuelve solo prefijos no presentes en seed_keys."""
    cache = GS1PrefixCache(seed_path=str(tmp_path / "empty_seed.json"))
    seed_keys = cache.current_prefix_keys()  # vacío

    cache.register("1111111", "BrandA", "ES", source="amazon", confidence="high", ean="1111111000001")
    cache.register("2222222", "BrandB", "ES", source="cache_gs1", confidence="high", ean="2222222000002")

    learned = cache.get_learned_prefixes(seed_keys)
    assert "1111111" in learned
    assert "2222222" in learned
    assert learned["1111111"]["brand_name"] == "BrandA"
    assert learned["1111111"]["ean"] == "1111111000001"
    assert learned["1111111"]["source"] == "amazon"


def test_get_learned_prefixes_excludes_seed_prefixes(tmp_path: Path) -> None:
    """Un prefijo que ya estaba en seed no aparece en get_learned_prefixes."""
    cache = GS1PrefixCache(seed_path=str(tmp_path / "empty_seed.json"))
    cache.register("9999999", "OldBrand", "ES")
    seed_keys = cache.current_prefix_keys()  # ahora contiene "9999999"

    cache.register("1111111", "NewBrand", "ES", source="bing_search", confidence="medium", ean="1111111000001")

    learned = cache.get_learned_prefixes(seed_keys)
    assert "9999999" not in learned
    assert "1111111" in learned


def test_brand_pipeline_persist_brand_cache_writes_file(tmp_path: Path) -> None:
    """
    _persist_brand_cache crea brand_cache.json con los prefijos proporcionados
    cuando write_cache=True.
    """
    from api.v1.schemas.job import ModosBusqueda, SearchConfig, TipoJob
    from services.scraper.brand_pipeline import BrandPipeline

    brand_cache = tmp_path / "brand_cache.json"
    config = SearchConfig(tipo_job=TipoJob.MARCAS, modo=ModosBusqueda.EAN)

    mock_storage = MagicMock()
    pipeline = BrandPipeline(
        job_id="test-job",
        config=config,
        storage=mock_storage,
        write_cache=True,
    )

    new_entries: dict[str, dict[str, str]] = {
        "1234567": {
            "brand_name": "TestBrand",
            "ean": "1234567000000",
            "source": "amazon",
            "confidence": "high",
        },
    }

    pipeline._persist_brand_cache(new_entries, brand_cache)

    assert brand_cache.exists()
    cache = json.loads(brand_cache.read_text())
    assert cache.get("1234567") == "TestBrand"
