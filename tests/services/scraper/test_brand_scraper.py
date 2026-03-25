"""
Tests unitarios para services/scraper/brand_scraper.py.

Verifica la cascada de 6 niveles de EanBrandResolver mediante mocks de todos
los clientes HTTP y de la caché GS1. Ningún test realiza peticiones de red reales.

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.scraper.brand_cache import GS1PrefixCache
from services.scraper.brand_scraper import EanBrandResolver
from services.scraper.brand_validator import BrandResult


# ── Helpers ───────────────────────────────────────────────────────────────────


def _compute_check_digit(body: str) -> str:
    """Calcula el dígito de control GS1 Módulo 10 para el cuerpo de un EAN."""
    weights = [1, 3] * len(body)
    total = sum(int(d) * w for d, w in zip(body, weights))
    return str((10 - total % 10) % 10)


def _make_ean(body: str) -> str:
    """Construye un EAN válido añadiendo el dígito de control al cuerpo dado."""
    return body + _compute_check_digit(body)


# EANs de prueba
_EAN_AMANOVA = "8413037335779"          # EAN real, checksum correcto
_EAN_NO_FOUND = _make_ean("549900000001")   # EAN válido sin fabricante conocido
_EAN_INVALIDO_CHECKSUM = "8413037335770"    # Dígito de control incorrecto


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_settings():
    """Mock de get_settings para aislar EanBrandResolver del archivo .env."""
    settings = MagicMock()
    settings.brand_http_timeout = 8
    return settings


@pytest.fixture()
def resolver(mock_settings):
    """
    EanBrandResolver con caché GS1 vacía y todos los clientes HTTP mockeados.

    Los atributos _openpetfood, _openfood, _upcitemdb, _google y _bing
    son MagicMock que devuelven None por defecto. Cada test puede cambiar
    el valor de retorno de .lookup() para simular cada escenario.
    """
    empty_cache = GS1PrefixCache(seed_path="/nonexistent/empty_cache.json")
    with patch("services.scraper.brand_scraper.get_settings", return_value=mock_settings):
        r = EanBrandResolver(gs1_cache=empty_cache)
    for attr in ("_amazon", "_openpetfood", "_openfood", "_upcitemdb", "_google", "_bing"):
        m = MagicMock()
        m.lookup.return_value = None
        setattr(r, attr, m)
    return r


# ── Tests: Nivel 1 — validación de EAN ───────────────────────────────────────


class TestNivel1ValidacionEan:
    """EANs no numéricos o con checksum incorrecto se rechazan antes de HTTP."""

    def test_ean_no_numerico_es_invalido(self, resolver) -> None:
        """EAN con texto libre devuelve ean_invalido sin peticiones HTTP."""
        result = resolver.resolver("PROD001", "LECHUGA ICEBERG")
        assert result.source == "ean_invalido"
        assert result.confidence == "low"
        resolver._openpetfood.lookup.assert_not_called()
        resolver._openfood.lookup.assert_not_called()
        resolver._upcitemdb.lookup.assert_not_called()
        resolver._google.lookup.assert_not_called()
        resolver._bing.lookup.assert_not_called()

    def test_ean_checksum_incorrecto_es_invalido(self, resolver) -> None:
        """EAN numérico con dígito de control incorrecto devuelve ean_invalido."""
        result = resolver.resolver("PROD002", _EAN_INVALIDO_CHECKSUM)
        assert result.source == "ean_invalido"
        resolver._openpetfood.lookup.assert_not_called()

    def test_ean_demasiado_corto_es_invalido(self, resolver) -> None:
        """EAN con menos de 8 dígitos devuelve ean_invalido."""
        result = resolver.resolver("PROD003", "123456")
        assert result.source == "ean_invalido"
        resolver._openpetfood.lookup.assert_not_called()

    def test_ean_con_guiones_es_invalido(self, resolver) -> None:
        """EAN con guiones internos no es numérico puro y devuelve ean_invalido."""
        result = resolver.resolver("PROD004", "841-3037-33577")
        assert result.source == "ean_invalido"
        resolver._openpetfood.lookup.assert_not_called()


# ── Tests: Nivel 2 — caché GS1 ───────────────────────────────────────────────


class TestNivel2CacheGS1:
    """EANs cuyo prefijo está en la caché se resuelven sin peticiones HTTP."""

    def test_ean_en_cache_se_resuelve_sin_http(self, mock_settings) -> None:
        """EAN con prefijo registrado en caché devuelve source=cache_gs1."""
        cache = GS1PrefixCache(seed_path="/nonexistent/empty.json")
        cache.register("8413037", "Amanova", "ES")
        with patch("services.scraper.brand_scraper.get_settings", return_value=mock_settings):
            r = EanBrandResolver(gs1_cache=cache)
        for attr in ("_amazon", "_openpetfood", "_openfood", "_upcitemdb", "_google", "_bing"):
            m = MagicMock()
            m.lookup.return_value = None
            setattr(r, attr, m)

        result = r.resolver("PROD001", _EAN_AMANOVA)

        assert result.source == "cache_gs1"
        assert result.confidence == "high"
        assert result.brand_name == "Amanova"
        r._openpetfood.lookup.assert_not_called()
        r._openfood.lookup.assert_not_called()
        r._upcitemdb.lookup.assert_not_called()
        r._google.lookup.assert_not_called()
        r._bing.lookup.assert_not_called()

    def test_sin_prefijo_en_cache_escala_a_nivel_3(self, resolver) -> None:
        """EAN cuyo prefijo no está en la caché vacía escala al Nivel 3."""
        resolver.resolver("PROD002", _EAN_AMANOVA)
        resolver._openpetfood.lookup.assert_called_once_with(_EAN_AMANOVA)


# ── Tests: Nivel 3 — Amazon ───────────────────────────────────────────────────


class TestNivel3Amazon:
    """Amazon.es (Nivel 3) se consulta cuando la caché GS1 no resuelve."""

    def test_amazon_se_llama_despues_de_cache_gs1(self, resolver) -> None:
        """Amazon se consulta cuando la caché GS1 no resuelve."""
        resolver._amazon.lookup.return_value = BrandResult(
            ean_code=_EAN_AMANOVA, brand_name="Amanova", source="amazon", confidence="high"
        )
        result = resolver.resolver("1", _EAN_AMANOVA)
        resolver._amazon.lookup.assert_called_once_with(_EAN_AMANOVA)
        assert result.source == "amazon"
        assert result.brand_name == "Amanova"

    def test_amazon_high_detiene_cascada(self, resolver) -> None:
        """Amazon high confidence detiene la cascada — Open Data no se llama."""
        resolver._amazon.lookup.return_value = BrandResult(
            ean_code=_EAN_AMANOVA, brand_name="Amanova", source="amazon", confidence="high"
        )
        resolver.resolver("1", _EAN_AMANOVA)
        resolver._openpetfood.lookup.assert_not_called()
        resolver._openfood.lookup.assert_not_called()
        resolver._upcitemdb.lookup.assert_not_called()

    def test_amazon_none_escala_a_openpetfood(self, resolver) -> None:
        """Si Amazon devuelve None, la cascada escala a OpenPetFoodFacts."""
        resolver._amazon.lookup.return_value = None
        resolver._openpetfood.lookup.return_value = BrandResult(
            ean_code=_EAN_AMANOVA, brand_name="Amanova", source="open_data_api", confidence="high"
        )
        result = resolver.resolver("1", _EAN_AMANOVA)
        resolver._amazon.lookup.assert_called_once()
        resolver._openpetfood.lookup.assert_called_once()
        assert result.source == "open_data_api"

    def test_amazon_high_aprende_prefijo_en_cache(self, resolver) -> None:
        """Amazon confidence=high registra el prefijo en GS1PrefixCache."""
        resolver._amazon.lookup.return_value = BrandResult(
            ean_code=_EAN_AMANOVA, brand_name="Amanova", source="amazon", confidence="high"
        )
        resolver.resolver("1", _EAN_AMANOVA)
        prefijo = _EAN_AMANOVA[:7]
        assert prefijo in resolver._cache._prefixes

    def test_amazon_medium_no_aprende_prefijo(self, resolver) -> None:
        """Amazon confidence=medium NO registra prefijo (inferencia de listado)."""
        resolver._amazon.lookup.return_value = BrandResult(
            ean_code=_EAN_AMANOVA, brand_name="Amanova", source="amazon", confidence="medium"
        )
        resolver.resolver("1", _EAN_AMANOVA)
        prefijo = _EAN_AMANOVA[:7]
        assert prefijo not in resolver._cache._prefixes

    def test_ean_invalido_no_llama_amazon(self, resolver) -> None:
        """EAN inválido es rechazado en Nivel 1 — Amazon nunca se llama."""
        resolver.resolver("1", "NO_ES_EAN")
        resolver._amazon.lookup.assert_not_called()


# ── Tests: Nivel 4 — APIs Open Data ──────────────────────────────────────────


class TestNivel3OpenData:
    """Cascada: OpenPetFoodFacts → OpenFoodFacts → UPCItemDb."""

    def test_openpetfood_resuelve_y_detiene_cascada(self, resolver) -> None:
        """Si OpenPetFoodFacts resuelve, los demás clientes no se llaman."""
        resolver._openpetfood.lookup.return_value = BrandResult(
            ean_code=_EAN_AMANOVA,
            brand_name="Amanova",
            source="open_data_api",
            confidence="high",
        )
        result = resolver.resolver("PROD001", _EAN_AMANOVA)
        assert result.source == "open_data_api"
        assert result.brand_name == "Amanova"
        resolver._openfood.lookup.assert_not_called()
        resolver._upcitemdb.lookup.assert_not_called()
        resolver._google.lookup.assert_not_called()
        resolver._bing.lookup.assert_not_called()

    def test_fallback_a_openfood_si_openpetfood_devuelve_none(self, resolver) -> None:
        """Si OpenPetFoodFacts devuelve None, se intenta OpenFoodFacts."""
        resolver._openpetfood.lookup.return_value = None
        resolver._openfood.lookup.return_value = BrandResult(
            ean_code=_EAN_AMANOVA,
            brand_name="MarcaGeneral",
            source="open_data_api",
            confidence="high",
        )
        result = resolver.resolver("PROD001", _EAN_AMANOVA)
        assert result.brand_name == "MarcaGeneral"
        resolver._upcitemdb.lookup.assert_not_called()
        resolver._google.lookup.assert_not_called()

    def test_fallback_a_upcitemdb_si_openfacts_fallan(self, resolver) -> None:
        """Si Open*Facts devuelven None, se intenta UPC Item DB."""
        resolver._openpetfood.lookup.return_value = None
        resolver._openfood.lookup.return_value = None
        resolver._upcitemdb.lookup.return_value = BrandResult(
            ean_code=_EAN_AMANOVA,
            brand_name="MarcaUPC",
            source="open_data_api",
            confidence="high",
        )
        result = resolver.resolver("PROD001", _EAN_AMANOVA)
        assert result.brand_name == "MarcaUPC"
        resolver._google.lookup.assert_not_called()
        resolver._bing.lookup.assert_not_called()

    def test_todos_open_data_fallan_escala_a_google(self, resolver) -> None:
        """Si todos los clientes Open Data devuelven None, se intenta Google."""
        resolver._google.lookup.return_value = BrandResult(
            ean_code=_EAN_AMANOVA,
            brand_name="MarcaGoogle",
            source="google_dorking",
            confidence="medium",
        )
        result = resolver.resolver("PROD001", _EAN_AMANOVA)
        assert result.source == "google_dorking"
        resolver._bing.lookup.assert_not_called()


# ── Tests: Niveles 4 y 5 — Buscadores ────────────────────────────────────────


class TestNivel4y5Buscadores:
    """Google (Nivel 4) y Bing (Nivel 5) como último recurso antes de not_found."""

    def test_google_resuelve_nivel_4(self, resolver) -> None:
        """Si Google devuelve resultado, Bing no se llama."""
        resolver._google.lookup.return_value = BrandResult(
            ean_code=_EAN_NO_FOUND,
            brand_name="MarcaGoogle",
            source="google_dorking",
            confidence="medium",
        )
        result = resolver.resolver("PROD001", _EAN_NO_FOUND)
        assert result.source == "google_dorking"
        assert result.brand_name == "MarcaGoogle"
        resolver._bing.lookup.assert_not_called()

    def test_bing_resuelve_nivel_5_cuando_google_falla(self, resolver) -> None:
        """Si Google devuelve None, se intenta Bing como Nivel 5."""
        resolver._google.lookup.return_value = None
        resolver._bing.lookup.return_value = BrandResult(
            ean_code=_EAN_NO_FOUND,
            brand_name="MarcaBing",
            source="bing_search",
            confidence="low",
        )
        result = resolver.resolver("PROD001", _EAN_NO_FOUND)
        assert result.source == "bing_search"
        assert result.brand_name == "MarcaBing"

    def test_not_found_cuando_todos_los_niveles_fallan(self, resolver) -> None:
        """Si los 5 niveles devuelven None, el resultado es not_found."""
        result = resolver.resolver("PROD001", _EAN_NO_FOUND)
        assert result.source == "not_found"
        assert result.brand_name is None
        assert result.confidence == "low"


# ── Tests: Aprendizaje automático de prefijos ─────────────────────────────────


class TestAprendizajePrefijos:
    """Al resolver desde Nivel 3-5 con confianza alta, se aprende el prefijo GS1."""

    def test_prefijo_aprendido_desde_nivel_3_high(self, resolver) -> None:
        """Nivel 3 con confidence=high registra el prefijo en la caché."""
        resolver._openpetfood.lookup.return_value = BrandResult(
            ean_code=_EAN_AMANOVA,
            brand_name="Amanova",
            manufacturer="Visan",
            source="open_data_api",
            confidence="high",
        )
        resolver.resolver("PROD001", _EAN_AMANOVA)
        assert _EAN_AMANOVA[:7] in resolver._cache._prefixes

    def test_prefijo_aprendido_desde_nivel_4_medium(self, resolver) -> None:
        """Nivel 4 con confidence=medium registra el prefijo en la caché."""
        resolver._google.lookup.return_value = BrandResult(
            ean_code=_EAN_AMANOVA,
            brand_name="MarcaGoogle",
            source="google_dorking",
            confidence="medium",
        )
        resolver.resolver("PROD001", _EAN_AMANOVA)
        assert _EAN_AMANOVA[:7] in resolver._cache._prefixes

    def test_prefijo_NO_aprendido_con_confidence_low(self, resolver) -> None:
        """Nivel 5 con confidence=low NO registra el prefijo (evita contaminar caché)."""
        resolver._bing.lookup.return_value = BrandResult(
            ean_code=_EAN_AMANOVA,
            brand_name="MarcaBing",
            source="bing_search",
            confidence="low",
        )
        resolver.resolver("PROD001", _EAN_AMANOVA)
        assert _EAN_AMANOVA[:7] not in resolver._cache._prefixes

    def test_segundo_ean_mismo_fabricante_resuelve_desde_cache(self, mock_settings) -> None:
        """
        Después de aprender el prefijo en Nivel 3, el siguiente EAN del mismo
        fabricante debe resolverse en el Nivel 2 sin ninguna petición HTTP.
        """
        cache = GS1PrefixCache(seed_path="/nonexistent/empty.json")
        with patch("services.scraper.brand_scraper.get_settings", return_value=mock_settings):
            r = EanBrandResolver(gs1_cache=cache)
        for attr in ("_amazon", "_openpetfood", "_openfood", "_upcitemdb", "_google", "_bing"):
            m = MagicMock()
            m.lookup.return_value = None
            setattr(r, attr, m)

        # Primera resolución: OpenPetFoodFacts resuelve y registra prefijo 8413037
        r._openpetfood.lookup.return_value = BrandResult(
            ean_code=_EAN_AMANOVA,
            brand_name="Amanova",
            source="open_data_api",
            confidence="high",
        )
        r.resolver("PROD001", _EAN_AMANOVA)

        # Segunda resolución: otro EAN con el mismo prefijo 8413037
        segundo_ean = _make_ean("841303733578")
        r._openpetfood.lookup.reset_mock()
        r._openpetfood.lookup.return_value = None

        result = r.resolver("PROD002", segundo_ean)

        # Debe resolverse desde la caché (Nivel 2) sin llamadas HTTP
        assert result.source == "cache_gs1"
        r._openpetfood.lookup.assert_not_called()
