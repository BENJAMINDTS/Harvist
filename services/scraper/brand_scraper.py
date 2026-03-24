"""
Resolución de EAN a marca de producto mediante búsqueda exacta en Bing.

Estrategia (dos pasos, el segundo es fallback):
  1. Busca el EAN entre comillas ("EAN") en Bing Web para forzar coincidencia exacta.
  2. Extrae los snippets de descripción de los primeros N resultados y busca el
     patrón explícito "Marca: X" / "Fabricante: X" → fuente más precisa.
  3. Si no hay patrón explícito, vota por la palabra más frecuente en los títulos
     (unigramas filtrados por stopwords y palabras comerciales).

:author: BenjaminDTS
:version: 3.0.0
"""

from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import quote_plus

from loguru import logger
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from api.core.config import get_settings

# ── Palabras que se descartan en el fallback de frecuencia de títulos ─────────

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
    "or", "in", "of", "to", "a", "by", "at", "from", "cm", "ml", "kg",
    "gr", "mg", "lt", "pcs", "uds", "ud", "ref", "cod", "ean", "upc",
})

_MIN_LONGITUD_PALABRA = 3

# Número de resultados de Bing a analizar
_NUM_RESULTADOS = 6

# Patrón para extraer la marca del campo explícito en los snippets de Bing.
# Captura el valor después de "Marca:", "Fabricante:", "Brand:", etc.
# Soporta marcas de varias palabras hasta 30 caracteres.
_PATRON_MARCA: re.Pattern[str] = re.compile(
    r'(?:marca|fabricante|manufacturer|brand|marque|hersteller)\s*[:\s·]\s*'
    r'([\w][\w\s\-&\'\.]{0,28}?)'
    r'(?=\s*[|·,;\n\r]|\s{2,}|$)',
    re.IGNORECASE | re.UNICODE,
)


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


class EanBrandResolver:
    """
    Resuelve EAN a nombre de marca mediante búsqueda exacta en Bing.

    Estrategia primaria: detectar el patrón "Marca: X" en los snippets de
    descripción de los resultados de Bing. Es la fuente más precisa porque
    muchas páginas de producto (Amazon, tiendas especializadas) incluyen este
    campo de forma estructurada.

    Estrategia fallback: frecuencia de palabras en títulos (unigramas).

    :author: BenjaminDTS
    """

    _URL_BUSQUEDA: str = "https://www.bing.com/search?q={query}"
    _SELECTOR_RESULTADOS: str = "#b_results"
    _SELECTOR_TITULOS: str = "li.b_algo h2"
    _SELECTOR_SNIPPETS: str = "li.b_algo .b_caption p"
    _SELECTOR_COOKIES: str = "#bnp_btn_accept, .bnp_btn_accept, button[id*='accept']"

    def inicializar_sesion(self, driver: WebDriver) -> None:
        """
        Navega a la página principal de Bing y acepta el consentimiento de cookies.

        Debe llamarse UNA VEZ antes del loop de productos para que las búsquedas
        posteriores no se encuentren con la página de consentimiento GDPR.

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

    def resolver(self, codigo: str, ean: str, driver: WebDriver) -> ResultadoMarca:
        """
        Busca el EAN en Bing y extrae la marca del producto.

        Intenta primero detectar "Marca: X" en los snippets de descripción.
        Si no lo encuentra, aplica el fallback de frecuencia de palabras en títulos.

        Args:
            codigo: código interno del producto.
            ean: código de barras EAN/UPC del producto.
            driver: WebDriver con sesión de Bing activa.

        Returns:
            ResultadoMarca con la marca detectada.
        """
        resultado = ResultadoMarca(codigo=codigo, ean=ean)
        settings = get_settings()
        wait = WebDriverWait(driver, settings.browser_timeout)

        try:
            url = self._URL_BUSQUEDA.format(query=quote_plus(f'"{ean}"'))
            driver.get(url)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, self._SELECTOR_RESULTADOS)))
            time.sleep(0.4)

            # ── Extraer títulos ───────────────────────────────────────────────
            titulos: list[str] = [
                el.text.strip()
                for el in driver.find_elements(By.CSS_SELECTOR, self._SELECTOR_TITULOS)[:_NUM_RESULTADOS]
                if el.text.strip()
            ]
            resultado.titulos_analizados = titulos

            if not titulos:
                resultado.error = "No se encontraron resultados para este EAN."
                logger.debug("Sin resultados para EAN", extra={"codigo": codigo, "ean": ean})
                return resultado

            # ── Extraer snippets de descripción ───────────────────────────────
            snippets: list[str] = [
                el.text.strip()
                for el in driver.find_elements(By.CSS_SELECTOR, self._SELECTOR_SNIPPETS)[:_NUM_RESULTADOS]
                if el.text.strip()
            ]

            # ── Estrategia 1: patrón explícito "Marca: X" en snippets ─────────
            marca = self._extraer_de_snippets(snippets)

            # ── Estrategia 2: fallback — frecuencia de palabras en títulos ────
            if not marca:
                marca = self._extraer_de_titulos(titulos)

            if marca:
                resultado.marca_detectada = marca
                resultado.exitoso = True
                logger.info(
                    "Marca resuelta por EAN",
                    extra={"codigo": codigo, "ean": ean, "marca": marca},
                )
            else:
                resultado.error = (
                    f"No se pudo identificar la marca. "
                    f"Títulos: {' | '.join(titulos[:3])}"
                )
                logger.debug(
                    "No se pudo identificar marca",
                    extra={"codigo": codigo, "ean": ean, "titulos": titulos},
                )

        except Exception as exc:
            resultado.error = str(exc)
            logger.warning(
                "Error resolviendo EAN a marca",
                exc_info=exc,
                extra={"codigo": codigo, "ean": ean},
            )

        return resultado

    @staticmethod
    def _extraer_de_snippets(snippets: list[str]) -> str:
        """
        Busca el patrón explícito "Marca: X" / "Fabricante: X" en los snippets.

        Esta es la estrategia más precisa: muchas páginas de producto incluyen
        el campo de marca de forma estructurada en su meta descripción.

        Args:
            snippets: textos de los snippets de descripción de los resultados.

        Returns:
            La marca detectada en Title Case, o cadena vacía si no hay coincidencia.
        """
        marcas: list[str] = []
        for snippet in snippets:
            for match in _PATRON_MARCA.finditer(snippet):
                valor = match.group(1).strip()
                # Descartar valores que parezcan nombres de producto (muy largos
                # o con números de modelo) en lugar de nombres de marca
                palabras = valor.split()
                if 1 <= len(palabras) <= 4 and not any(p.isdigit() for p in palabras):
                    marcas.append(valor.title())

        if not marcas:
            return ""

        # La marca que aparece más veces en diferentes snippets gana
        return Counter(marcas).most_common(1)[0][0]

    @staticmethod
    def _extraer_de_titulos(titulos: list[str]) -> str:
        """
        Fallback: extrae la marca más probable por frecuencia de unigramas en títulos.

        Usado cuando ningún snippet contiene el patrón "Marca: X".

        Args:
            titulos: títulos de los resultados de Bing.

        Returns:
            La marca detectada en Title Case, o cadena vacía si no hay candidato.
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
