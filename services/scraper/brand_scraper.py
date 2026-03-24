"""
Resolución de EAN a marca de producto.

Estrategia en cascada (se detiene en cuanto encuentra la marca):
  1. Open Food Facts API — base de datos pública de productos, respuesta JSON
     directa con el campo `brands`. Sin Selenium, sin Bing. Cubre la mayoría
     de productos de alimentación y mascotas indexados mundialmente.
  2. Patrón "Marca: X" en snippets de Bing — extrae el campo explícito de marca
     de las descripciones de resultados de búsqueda.
  3. Frecuencia de unigramas en títulos de Bing — fallback estadístico.

:author: BenjaminDTS
:version: 4.0.0
"""

from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import quote_plus

import requests as http_requests
from loguru import logger
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from api.core.config import get_settings

# ── Constantes ────────────────────────────────────────────────────────────────

_MIN_LONGITUD_PALABRA = 3
_NUM_RESULTADOS = 6

# APIs de la familia Open*Facts (misma estructura, distintas bases de datos).
# Se consultan en orden hasta encontrar la marca.
_OPEN_FACTS_APIS: tuple[str, ...] = (
    "https://world.openpetfoodfacts.org/api/v0/product/{ean}.json",   # comida mascotas
    "https://world.openfoodfacts.org/api/v0/product/{ean}.json",      # alimentación general
    "https://world.openproductsfacts.org/api/v0/product/{ean}.json",  # productos genéricos
    "https://world.openbeautyfacts.org/api/v0/product/{ean}.json",    # cosmética / higiene
)
_OFF_TIMEOUT_S = 5

# URL de Bing con idioma español para evitar resultados en otros idiomas
_BING_URL = "https://www.bing.com/search?q={query}&setlang=es"

# Patrón para extraer "Marca: X" de los snippets de Bing
_PATRON_MARCA: re.Pattern[str] = re.compile(
    r'(?:marca|fabricante|manufacturer|brand)\s*[:\s·]\s*'
    r'([\w\u00C0-\u024F][\w\u00C0-\u024F\s\-&]{1,30}?)'
    r'(?=\s*[|·,;\n\r]|\s{2,}|$)',
    re.IGNORECASE,
)

# ── Filtros para el fallback de títulos ───────────────────────────────────────

_PALABRAS_COMERCIALES: frozenset[str] = frozenset({
    "comprar", "compra", "compre", "compras", "precio", "precios", "barato",
    "baratos", "barata", "baratas", "online", "tienda", "tiendas", "shop",
    "store", "amazon", "ebay", "zooplus", "aliexpress", "pccomponentes",
    "envio", "envío", "envios", "gratis", "oferta", "ofertas", "descuento",
    "descuentos", "venta", "vender", "vende", "mejor", "mejores", "nuevo",
    "nuevos", "nueva", "nuevas", "pack", "packs", "set", "kit", "stock",
    "disponible", "pedido", "pedidos", "producto", "productos", "articulo",
    "articulos", "artículo", "artículos", "calidad", "original", "originales",
    "oficial", "marca", "marcas", "fabricante", "fabricantes",
})

_STOPWORDS: frozenset[str] = frozenset({
    "de", "el", "la", "los", "las", "un", "una", "unos", "unas", "del",
    "al", "se", "su", "sus", "mi", "tu", "nos", "más", "sin", "sobre",
    "entre", "bajo", "ante", "desde", "para", "con", "por", "en", "a",
    "y", "o", "e", "u", "que", "es", "son", "the", "and", "for", "with",
    "or", "in", "of", "to", "by", "at", "from", "cm", "ml", "kg",
    "gr", "mg", "lt", "pcs", "uds", "ud", "ref", "cod", "ean", "upc",
})


# ── Dataclass de resultado ────────────────────────────────────────────────────

@dataclass
class ResultadoMarca:
    """
    Resultado de la resolución EAN → marca.

    :author: BenjaminDTS
    """

    codigo: str
    ean: str
    marca_detectada: str = field(default="")
    titulos_analizados: list[str] = field(default_factory=list)
    exitoso: bool = field(default=False)
    error: str = field(default="")


# ── Resolvedor ────────────────────────────────────────────────────────────────

class EanBrandResolver:
    """
    Resuelve EAN a nombre de marca mediante una cascada de tres estrategias.

    Estrategia 1 (API): consulta Open Food Facts sin necesidad de navegador.
    Estrategias 2 y 3: scraping de resultados de Bing como fallback.

    :author: BenjaminDTS
    """

    _SELECTOR_RESULTADOS: str = "#b_results"
    _SELECTOR_TITULOS: str = "li.b_algo h2"
    _SELECTOR_SNIPPETS: str = "li.b_algo .b_caption p"
    _SELECTOR_COOKIES: str = "#bnp_btn_accept, .bnp_btn_accept, button[id*='accept']"

    def inicializar_sesion(self, driver: WebDriver) -> None:
        """
        Navega a la página principal de Bing y acepta el consentimiento de cookies.

        Debe llamarse UNA VEZ antes del loop de productos.

        Args:
            driver: WebDriver recién creado, sin cookies de Bing.
        """
        try:
            driver.get("https://www.bing.com")
            boton = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, self._SELECTOR_COOKIES))
            )
            boton.click()
            time.sleep(0.5)
            logger.info("Consentimiento de cookies de Bing aceptado")
        except Exception:
            logger.debug("Banner de cookies de Bing no detectado (ya aceptado o no presente)")

    def resolver(
        self,
        codigo: str,
        ean: str,
        driver: WebDriver,
        nombre_producto: str = "",
    ) -> ResultadoMarca:
        """
        Resuelve el EAN a una marca usando la cascada de estrategias.

        Args:
            codigo: código interno del producto.
            ean: código de barras EAN/UPC.
            driver: WebDriver con sesión de Bing activa (usado solo en steps 2-3).
            nombre_producto: nombre del producto del CSV (reservado para uso futuro).

        Returns:
            ResultadoMarca con la marca detectada y la fuente usada.
        """
        resultado = ResultadoMarca(codigo=codigo, ean=ean)

        # ── Paso 1: API Open Food Facts ───────────────────────────────────────
        if ean and self._es_ean_numerico(ean):
            marca = self._buscar_en_api(ean)
            if marca:
                resultado.marca_detectada = marca
                resultado.exitoso = True
                logger.info(
                    "Marca resuelta por API (Open Food Facts)",
                    extra={"codigo": codigo, "ean": ean, "marca": marca},
                )
                return resultado

        # ── Pasos 2 y 3: Bing scraping ────────────────────────────────────────
        settings = get_settings()
        wait = WebDriverWait(driver, settings.browser_timeout)

        try:
            url = _BING_URL.format(query=quote_plus(f'"{ean}"'))
            driver.get(url)
            wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, self._SELECTOR_RESULTADOS)
            ))
            time.sleep(0.4)

            titulos: list[str] = [
                el.text.strip()
                for el in driver.find_elements(
                    By.CSS_SELECTOR, self._SELECTOR_TITULOS
                )[:_NUM_RESULTADOS]
                if el.text.strip()
            ]
            resultado.titulos_analizados = titulos

            snippets: list[str] = [
                el.text.strip()
                for el in driver.find_elements(
                    By.CSS_SELECTOR, self._SELECTOR_SNIPPETS
                )[:_NUM_RESULTADOS]
                if el.text.strip()
            ]

            # Paso 2: patrón "Marca: X" en snippets
            marca = self._extraer_de_snippets(snippets)

            # Paso 3: frecuencia de unigramas en títulos
            if not marca:
                marca = self._extraer_de_titulos(titulos)

            if marca:
                resultado.marca_detectada = marca
                resultado.exitoso = True
                logger.info(
                    "Marca resuelta por Bing",
                    extra={"codigo": codigo, "ean": ean, "marca": marca},
                )
            else:
                titulo_muestra = " | ".join(titulos[:3]) if titulos else "sin resultados"
                resultado.error = (
                    f"No se pudo identificar la marca. Títulos: {titulo_muestra}"
                )
                logger.debug(
                    "No se pudo identificar marca",
                    extra={"codigo": codigo, "ean": ean},
                )

        except Exception as exc:
            resultado.error = str(exc)
            logger.warning(
                "Error en scraping Bing",
                exc_info=exc,
                extra={"codigo": codigo, "ean": ean},
            )

        return resultado

    # ── Paso 1: API ───────────────────────────────────────────────────────────

    @staticmethod
    def _es_ean_numerico(ean: str) -> bool:
        """Devuelve True si el EAN parece un código de barras numérico válido."""
        return bool(re.fullmatch(r"\d{8,14}", ean.strip()))

    @staticmethod
    def _buscar_en_api(ean: str) -> str:
        """
        Consulta Open Food Facts y Open Products Facts para obtener la marca.

        Consulta en orden: Open Pet Food Facts, Open Food Facts,
        Open Products Facts y Open Beauty Facts. Todas tienen el mismo esquema:
        GET /api/v0/product/{EAN}.json → `product.brands` separado por comas.
        Cubre productos genéricos, no solo alimentación.

        Args:
            ean: código EAN numérico del producto.

        Returns:
            Nombre de la marca en Title Case, o cadena vacía si no se encuentra.
        """
        for url_tpl in _OPEN_FACTS_APIS:
            try:
                resp = http_requests.get(
                    url_tpl.format(ean=ean),
                    timeout=_OFF_TIMEOUT_S,
                    headers={"User-Agent": "Harvist/1.0 (brand-resolver)"},
                )
                if not resp.ok:
                    continue
                data = resp.json()
                if data.get("status") != 1:
                    continue
                brands_raw: str = data.get("product", {}).get("brands", "")
                if brands_raw:
                    # Puede venir como "Trixie, Trixie International" — tomamos solo la primera
                    primera = brands_raw.split(",")[0].strip()
                    if primera:
                        logger.debug(
                            "Marca encontrada en API",
                            extra={"ean": ean, "marca": primera, "url": url_tpl},
                        )
                        return primera.title()
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "Error consultando API de marcas",
                    exc_info=exc,
                    extra={"ean": ean, "url": url_tpl},
                )
        return ""

    # ── Paso 2: snippets ─────────────────────────────────────────────────────

    @staticmethod
    def _extraer_de_snippets(snippets: list[str]) -> str:
        """
        Busca el patrón explícito "Marca: X" en los snippets de Bing.

        Args:
            snippets: textos de los snippets de descripción.

        Returns:
            La marca detectada en Title Case, o cadena vacía.
        """
        marcas: list[str] = []
        for snippet in snippets:
            for match in _PATRON_MARCA.finditer(snippet):
                valor = match.group(1).strip()
                palabras = valor.split()
                if 1 <= len(palabras) <= 4 and not any(p.isdigit() for p in palabras):
                    marcas.append(valor.title())

        if not marcas:
            return ""
        return Counter(marcas).most_common(1)[0][0]

    # ── Paso 3: frecuencia en títulos ─────────────────────────────────────────

    @staticmethod
    def _extraer_de_titulos(titulos: list[str]) -> str:
        """
        Extrae la marca por frecuencia de unigramas en los títulos de Bing.

        Args:
            titulos: títulos de los primeros resultados de Bing.

        Returns:
            La marca candidata en Title Case, o cadena vacía.
        """
        presencia: Counter[str] = Counter()

        for titulo in titulos:
            vistos: set[str] = set()
            for parte in re.split(r"[\s\-|/,.:;()\"']+", titulo):
                limpia = re.sub(r"[^\w]", "", parte, flags=re.UNICODE).strip()
                tok = limpia.lower()
                if (
                    len(limpia) >= _MIN_LONGITUD_PALABRA
                    and not limpia.isdigit()
                    and tok not in _PALABRAS_COMERCIALES
                    and tok not in _STOPWORDS
                    and tok not in vistos
                ):
                    vistos.add(tok)
                    presencia[tok] += 1

        if not presencia:
            return ""

        candidata, _ = presencia.most_common(1)[0]
        return candidata.title()
