"""
Tests unitarios para AmazonBrandClient.

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.utils.amazon_brand_client import AmazonBrandClient, _clean_brand
from services.scraper.brand_validator import BrandResult


# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def client() -> AmazonBrandClient:
    """
    AmazonBrandClient con settings mockeados.

    El proxy y el timeout se leen de un mock de get_settings para aislar los
    tests del archivo .env.
    """
    mock_settings = MagicMock()
    mock_settings.rotating_proxy_url = ""
    mock_settings.amazon_http_timeout = 10
    with patch("services.utils.amazon_brand_client.get_settings", return_value=mock_settings):
        return AmazonBrandClient(timeout=10, max_retries=1)


# ── Helpers ───────────────────────────────────────────────────────────────────

_EAN_TEST = "8413037335779"

_LISTING_HTML_WITH_ASIN = (
    'data-asin="B0CX123456" data-component-type="s-search-result"'
    '<span class="a-size-base-plus a-color-base">Amanova</span>'
)

_PRODUCT_HTML_BYLINE = '<a id="bylineInfo">Amanova</a>'
_PRODUCT_HTML_PO_BRAND = (
    '<tr class="po-brand">'
    '<td class="po-break-word">Flamingo</td>'
    '</tr>'
)
_PRODUCT_HTML_SINGLE_CHAR = '<a id="bylineInfo">X</a>'
_PRODUCT_HTML_NUMERIC = '<a id="bylineInfo">12345</a>'

_LISTING_HTML_BRAND_MEDIUM = (
    'data-asin="B0CX999999" '
    '<span class="a-size-base-plus a-color-base">Trixie</span>'
)

_LISTING_HTML_NO_BRAND = (
    '<div class="no-result">Sin resultados</div>'
)


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestExtractBrandFromProductPage:
    """Extracción de marca desde la ficha de producto (/dp/{ASIN})."""

    def test_extract_brand_from_product_page_bylineinfo(self, client: AmazonBrandClient) -> None:
        """bylineInfo en la ficha de producto produce confidence=high y source=amazon."""
        with patch.object(client, "_get_listing_html", return_value=_LISTING_HTML_WITH_ASIN), \
             patch.object(client, "_get_product_html", return_value=_PRODUCT_HTML_BYLINE):
            result = client.lookup(_EAN_TEST)

        assert result is not None
        assert result.brand_name == "Amanova"
        assert result.confidence == "high"
        assert result.source == "amazon"

    def test_extract_brand_from_product_page_po_brand_table(self, client: AmazonBrandClient) -> None:
        """La tabla po-brand en la ficha de producto produce confidence=high."""
        with patch.object(client, "_get_listing_html", return_value=_LISTING_HTML_WITH_ASIN), \
             patch.object(client, "_get_product_html", return_value=_PRODUCT_HTML_PO_BRAND):
            result = client.lookup(_EAN_TEST)

        assert result is not None
        assert result.brand_name == "Flamingo"
        assert result.confidence == "high"

    def test_brand_single_char_returns_none(self, client: AmazonBrandClient) -> None:
        """Marca de un solo carácter se descarta — lookup devuelve None."""
        # Listing HTML without any brand span so STEP C also fails
        listing_html_no_brand_span = 'data-asin="B0CX123456" data-component-type="s-search-result"'
        with patch.object(client, "_get_listing_html", return_value=listing_html_no_brand_span), \
             patch.object(client, "_get_product_html", return_value=_PRODUCT_HTML_SINGLE_CHAR):
            result = client.lookup(_EAN_TEST)

        assert result is None

    def test_brand_numeric_returns_none(self, client: AmazonBrandClient) -> None:
        """Marca totalmente numérica se descarta — lookup devuelve None."""
        # Listing HTML without any brand span so STEP C also fails
        listing_html_no_brand_span = 'data-asin="B0CX123456" data-component-type="s-search-result"'
        with patch.object(client, "_get_listing_html", return_value=listing_html_no_brand_span), \
             patch.object(client, "_get_product_html", return_value=_PRODUCT_HTML_NUMERIC):
            result = client.lookup(_EAN_TEST)

        assert result is None


class TestFallbackListingBrand:
    """Extracción de marca desde el listado cuando no hay ASIN disponible."""

    def test_extract_brand_from_listing_fallback_medium_confidence(self, client: AmazonBrandClient) -> None:
        """Sin data-asin, la marca se extrae del span del listado con confidence=medium."""
        # Listado sin ASIN válido (no se puede extraer un ASIN no patrocinado),
        # pero con un span de marca del primer resultado.
        listing_html = (
            'data-asin="B0CX999999" '
            '<span class="a-size-base-plus a-color-base">Trixie</span>'
        )
        with patch.object(client, "_get_listing_html", return_value=listing_html), \
             patch.object(client, "_get_product_html", return_value="<html></html>"):
            result = client.lookup(_EAN_TEST)

        assert result is not None
        assert result.brand_name == "Trixie"
        assert result.confidence == "medium"
        assert result.source == "amazon"


class TestNoResultCases:
    """Casos en que lookup devuelve None."""

    def test_no_brand_found_returns_none(self, client: AmazonBrandClient) -> None:
        """HTML sin selectores de marca reconocibles en ningún paso → None."""
        with patch.object(client, "_get_listing_html", return_value=_LISTING_HTML_NO_BRAND), \
             patch.object(client, "_get_product_html", return_value="<html></html>"):
            result = client.lookup(_EAN_TEST)

        assert result is None

    def test_no_results_page_with_sponsored_products_returns_none(
        self, client: AmazonBrandClient
    ) -> None:
        """Página 'sin resultados' con patrocinados visibles → None (falso positivo evitado)."""
        no_results_html = (
            "<html><body>"
            "<span>No hay resultados para tu consulta de búsqueda.</span>"
            '<div data-component-type="sp-sponsored-result" data-asin="B0CX999999">'
            '<span class="a-size-base-plus a-color-base">Ruisun</span>'
            "</div>"
            "</body></html>"
        )
        with patch.object(client, "_get_listing_html", return_value=no_results_html):
            result = client.lookup(_EAN_TEST)
        assert result is None

    def test_network_error_all_retries_returns_none(self, client: AmazonBrandClient) -> None:
        """Errores de red en todos los reintentos → lookup devuelve None sin propagar excepción."""
        import httpx

        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(side_effect=httpx.ConnectError("timeout"))
        mock_client_instance.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_client_instance):
            result = client.lookup(_EAN_TEST)

        assert result is None


class TestCleanBrand:
    """Limpieza y normalización de nombres de marca."""

    def test_clean_brand_visita_la_tienda_prefix(self) -> None:
        """El prefijo 'Visita la tienda de' se elimina y el resto queda en title-case."""
        result = _clean_brand("Visita la tienda de Amanova")
        assert result == "Amanova"

    def test_clean_brand_by_prefix(self) -> None:
        """El prefijo 'by ' se elimina y se aplica title-case al resto."""
        result = _clean_brand("by Nestlé España")
        assert result == "Nestlé España"
