"""
Resolución de EAN a marca de producto mediante búsqueda exacta en Bing.

Estrategia:
  1. Busca el EAN entre comillas ("EAN") en Bing Web para forzar coincidencia exacta.
  2. Extrae los títulos de los 4 primeros resultados orgánicos (<h2> de li.b_algo).
  3. Tokeniza, filtra palabras comerciales y stopwords, y calcula la frecuencia.
  4. La palabra más frecuente que queda es la marca/fabricante del producto.

Usa el mismo WebDriver de Bing que ya está activo en el pipeline de imágenes,
por lo que no necesita abrir una sesión nueva ni enfrentarse a CAPTCHAs.

:author: BenjaminDTS
:version: 2.0.0
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

# ── Palabras que se descartan antes de votar por la marca ─────────────────────

# Palabras comerciales genéricas que no identifican marcas
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

# Stopwords en español e inglés
_STOPWORDS: frozenset[str] = frozenset({
    "de", "el", "la", "los", "las", "un", "una", "unos", "unas", "del",
    "al", "se", "su", "sus", "mi", "tu", "nos", "más", "sin", "sobre",
    "entre", "bajo", "ante", "desde", "para", "con", "por", "en", "a",
    "y", "o", "e", "u", "que", "es", "son", "the", "and", "for", "with",
    "or", "in", "of", "to", "a", "by", "at", "from", "cm", "ml", "kg",
    "gr", "mg", "lt", "pcs", "uds", "ud", "ref", "cod", "ean", "upc",
})

# Longitud mínima de palabra para ser considerada candidata a marca
_MIN_LONGITUD_PALABRA = 3

# Número de resultados de Bing a analizar
_NUM_RESULTADOS = 4


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

    Reutiliza el WebDriver activo para aprovechar la sesión de Bing ya
    establecida por el productor de imágenes, minimizando el riesgo de bloqueo.

    :author: BenjaminDTS
    """

    # Búsqueda exacta: las comillas dobles fuerzan coincidencia literal del EAN y se añade
    # "marca" para sesgar los resultados hacia páginas que mencionan el fabricante.
    _URL_BUSQUEDA: str = "https://www.bing.com/search?q={query}+marca"
    _SELECTOR_RESULTADOS: str = "#b_results"
    _SELECTOR_TITULOS: str = "li.b_algo h2"
    # Selectores del banner de consentimiento de cookies de Bing
    _SELECTOR_COOKIES: str = "#bnp_btn_accept, .bnp_btn_accept, button[id*='accept']"

    def inicializar_sesion(self, driver: WebDriver) -> None:
        """
        Navega a la página principal de Bing y acepta el consentimiento de cookies.

        Debe llamarse UNA VEZ antes del loop de productos para que las búsquedas
        posteriores no se encuentren con la página de consentimiento GDPR en lugar
        de los resultados.

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
            # El banner no apareció o ya estaba aceptado — se continúa normalmente
            logger.debug("Banner de cookies de Bing no detectado (ya aceptado o no presente)")

    def resolver(self, codigo: str, ean: str, driver: WebDriver) -> ResultadoMarca:
        """
        Busca el EAN en Bing y extrae la marca del producto a partir de los títulos.

        Args:
            codigo: código interno del producto (para identificación en el CSV).
            ean: código de barras EAN/UPC del producto.
            driver: WebDriver con sesión de Bing activa.

        Returns:
            ResultadoMarca con la marca detectada y los títulos analizados.
        """
        resultado = ResultadoMarca(codigo=codigo, ean=ean)
        settings = get_settings()
        wait = WebDriverWait(driver, settings.browser_timeout)

        try:
            url = self._URL_BUSQUEDA.format(query=quote_plus(f'"{ean}"'))
            driver.get(url)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, self._SELECTOR_RESULTADOS)))
            time.sleep(0.4)

            # Extraer títulos de los primeros N resultados orgánicos
            elementos = driver.find_elements(By.CSS_SELECTOR, self._SELECTOR_TITULOS)
            titulos: list[str] = []
            for el in elementos[:_NUM_RESULTADOS]:
                texto = el.text.strip()
                if texto:
                    titulos.append(texto)

            resultado.titulos_analizados = titulos

            if not titulos:
                resultado.error = "No se encontraron resultados para este EAN."
                logger.debug(
                    "Sin resultados para EAN",
                    extra={"codigo": codigo, "ean": ean},
                )
                return resultado

            # Votar por la marca más frecuente entre los títulos
            marca = self._extraer_marca(titulos)
            if marca:
                resultado.marca_detectada = marca
                resultado.exitoso = True
                logger.info(
                    "Marca resuelta por EAN",
                    extra={"codigo": codigo, "ean": ean, "marca": marca},
                )
            else:
                resultado.error = (
                    f"No se pudo identificar una marca. "
                    f"Títulos encontrados: {' | '.join(titulos)}"
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
    def _extraer_marca(titulos: list[str]) -> str:
        """
        Extrae la marca más probable a partir de los títulos de resultados de Bing.

        Para cada título construye un conjunto de palabras candidatas (sin repetición
        dentro del mismo título). Luego cuenta en cuántos títulos distintos aparece
        cada palabra: las marcas aparecen en todos los resultados de forma consistente,
        mientras que palabras genéricas de producto tienden a concentrarse en uno o
        pocos títulos. En caso de empate se usa la frecuencia bruta como desempate.

        Args:
            titulos: lista de títulos de resultados de Bing.

        Returns:
            La marca detectada en Title Case, o cadena vacía si no hay candidato.
        """
        # palabras_por_titulo[i] = set de palabras candidatas del título i
        palabras_por_titulo: list[set[str]] = []

        for titulo in titulos:
            palabras_titulo: set[str] = set()
            palabras_crudas = re.split(r"[\s\-|/,.:;()\"']+", titulo)
            for palabra in palabras_crudas:
                limpia = re.sub(r"[^\w]", "", palabra, flags=re.UNICODE).strip()
                if (
                    len(limpia) >= _MIN_LONGITUD_PALABRA
                    and not limpia.isdigit()
                    and limpia.lower() not in _PALABRAS_COMERCIALES
                    and limpia.lower() not in _STOPWORDS
                ):
                    palabras_titulo.add(limpia.lower())
            if palabras_titulo:
                palabras_por_titulo.append(palabras_titulo)

        if not palabras_por_titulo:
            return ""

        # Contar en cuántos títulos distintos aparece cada palabra.
        # La marca aparece de forma consistente en todos los resultados.
        presencia: Counter[str] = Counter(
            palabra
            for palabras in palabras_por_titulo
            for palabra in palabras
        )

        candidata, _ = presencia.most_common(1)[0]
        return candidata.title()
