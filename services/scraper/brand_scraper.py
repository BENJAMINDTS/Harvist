"""
Resolución de EAN a marca de producto.

Estrategia en cascada (se detiene en cuanto encuentra la marca):

  1. Open*Facts APIs (sin Selenium) — bases de datos públicas de productos
     con campo `brands` estructurado. Cubre alimentación, mascotas, cosmética
     y productos genéricos. Rápido (~100 ms), sin riesgo de CAPTCHA.

  1b. UPC Item DB API (sin Selenium) — base de datos generalista de códigos
     de barras. Complementa a Open*Facts para productos no alimenticios.

  Si el EAN no es numérico (p. ej. "LECHUGA ICEBERG") ninguna de las dos
  puede ayudar y el producto se devuelve inmediatamente como no resoluble.
  No tiene sentido buscar en Bing un código que no es un EAN real.

  2. Visita Selenium de las primeras URLs de Bing — usa el mismo driver ya
     abierto para visitar la página del producto. Al ser un navegador real
     evita el bloqueo anti-bot que sufre `requests`. Extrae la marca de:
       a) JSON-LD Schema.org  `{"@type":"Product","brand":{"name":"X"}}`
       b) `itemprop="brand"` (microdata)
       c) `og:site_name` (meta Open Graph)
       d) Título de página  "Nombre producto - Marca"
       e) Patrón "Marca: X" en el HTML

  3. Patrón "Marca: X" en snippets de Bing — campo explícito en descripciones.

  4. Frecuencia de unigramas en títulos de Bing — último recurso estadístico.

:author: BenjaminDTS
:version: 7.0.0
"""

from __future__ import annotations

import html as _html_lib
import json
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

_NUM_RESULTADOS = 6
_MAX_URLS_PASO2 = 2          # URLs a visitar con Selenium en el paso 2
_MIN_LONGITUD_PALABRA = 3
_HTTP_TIMEOUT_S = 6
_SELENIUM_PAGE_TIMEOUT_S = 8

# APIs Open*Facts — misma estructura, distintas bases de datos.
_OPEN_FACTS_APIS: tuple[str, ...] = (
    "https://world.openpetfoodfacts.org/api/v0/product/{ean}.json",
    "https://world.openfoodfacts.org/api/v0/product/{ean}.json",
    "https://world.openproductsfacts.org/api/v0/product/{ean}.json",
    "https://world.openbeautyfacts.org/api/v0/product/{ean}.json",
)

# UPC Item DB — base de datos generalista de códigos de barras (tier gratuito)
_UPC_ITEM_DB_URL = "https://api.upcitemdb.com/prod/trial/lookup?upc={ean}"

# URL de búsqueda en Bing
_BING_URL = "https://www.bing.com/search?q={query}&setlang=es"

# Selectores Bing
_SEL_RESULTADOS = "#b_results"
_SEL_TITULOS = "li.b_algo h2"
_SEL_ENLACES_ORGANICOS = "li.b_algo h2 a"
_SEL_SNIPPETS = "li.b_algo .b_caption p"
_SEL_COOKIES = "#bnp_btn_accept, .bnp_btn_accept, button[id*='accept']"

# Dominios de Bing/Microsoft que hay que excluir al buscar URLs de producto
_DOMINIOS_EXCLUIDOS = ("bing.com", "microsoft.com", "msn.com", "live.com")

# Cabeceras HTTP para las llamadas a APIs (Open*Facts, UPC Item DB)
_HEADERS_API = {"User-Agent": "Harvist/1.0"}

# Separadores "Nombre producto <sep> Marca" en títulos de página de e-commerce
_SEPARADORES_TITULO: tuple[str, ...] = (" - ", " | ", " – ", " · ", " — ")

# Patrón para "Marca: X" en snippets y HTML (paso 3 / fallback paso 2)
_PATRON_MARCA: re.Pattern[str] = re.compile(
    r'(?:marca|fabricante|manufacturer|brand)\s*[:\s·]\s*'
    r'([\w\u00C0-\u024F][\w\u00C0-\u024F\s\-&]{1,30}?)'
    r'(?=\s*[|·,;\n\r]|\s{2,}|$)',
    re.IGNORECASE,
)

# Filtros para el paso 4 (frecuencia de títulos)
_PALABRAS_COMERCIALES: frozenset[str] = frozenset({
    "comprar", "compra", "precio", "precios", "barato", "online", "tienda",
    "tiendas", "shop", "store", "amazon", "ebay", "zooplus", "aliexpress",
    "gratis", "oferta", "ofertas", "descuento", "venta", "mejor", "mejores",
    "nuevo", "nuevos", "pack", "set", "kit", "stock", "disponible", "pedido",
    "producto", "productos", "articulo", "articulos", "calidad", "original",
    "oficial", "marca", "marcas", "fabricante", "fabricantes",
})
_STOPWORDS: frozenset[str] = frozenset({
    "de", "el", "la", "los", "las", "un", "una", "unos", "unas", "del",
    "al", "se", "su", "sus", "que", "es", "son", "the", "and", "for",
    "with", "or", "in", "of", "to", "by", "at", "from",
    "cm", "ml", "kg", "gr", "mg", "lt", "pcs", "uds", "ud",
})


# ── Dataclass ─────────────────────────────────────────────────────────────────

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
    Resuelve EAN a nombre de marca mediante una cascada de estrategias.

    :author: BenjaminDTS
    """

    def inicializar_sesion(self, driver: WebDriver) -> None:
        """
        Acepta las cookies de Bing una sola vez al inicio del pipeline.

        Args:
            driver: WebDriver recién creado sin cookies de Bing.
        """
        driver.get("https://www.bing.com")
        self._descartar_cookies(driver)

    @staticmethod
    def _descartar_cookies(driver: WebDriver) -> None:
        """
        Descarta el banner de consentimiento de cookies de Bing si está presente.

        Args:
            driver: WebDriver con cualquier página de Bing cargada o cargándose.
        """
        try:
            boton = WebDriverWait(driver, 4).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, _SEL_COOKIES))
            )
            boton.click()
            time.sleep(0.4)
            logger.info("Consentimiento de cookies de Bing aceptado")
        except Exception:
            logger.debug("Banner de cookies de Bing no detectado")

    def resolver(
        self,
        codigo: str,
        ean: str,
        driver: WebDriver,
        nombre_producto: str = "",
    ) -> ResultadoMarca:
        """
        Ejecuta la cascada de estrategias para resolver EAN → marca.

        Args:
            codigo: código interno del producto.
            ean: código de barras EAN/UPC.
            driver: WebDriver con sesión de Bing activa.
            nombre_producto: nombre del producto del CSV (no usado actualmente).

        Returns:
            ResultadoMarca con la marca detectada o el error correspondiente.
        """
        resultado = ResultadoMarca(codigo=codigo, ean=ean)

        # ── Guardia: EAN no numérico → no resoluble ────────────────────────────
        # Los pasos 1, 1b y 2 requieren un EAN de 8-14 dígitos. Buscar en Bing
        # un código como "LECHUGA ICEBERG" devolvería resultados del producto en
        # cuestión, no de una marca, generando falsos positivos.
        if not self._es_ean_numerico(ean):
            resultado.error = (
                "El código no es un EAN numérico válido "
                "(debe tener entre 8 y 14 dígitos)."
            )
            logger.debug(
                "EAN no numérico, omitido",
                extra={"codigo": codigo, "ean": ean},
            )
            return resultado

        # ── Paso 1: APIs Open*Facts ───────────────────────────────────────────
        marca = self._buscar_en_open_facts(ean)
        if marca:
            resultado.marca_detectada = marca
            resultado.exitoso = True
            logger.info(
                "Marca resuelta — Open*Facts",
                extra={"codigo": codigo, "ean": ean, "marca": marca},
            )
            return resultado

        # ── Paso 1b: UPC Item DB ──────────────────────────────────────────────
        marca = self._buscar_en_upc_db(ean)
        if marca:
            resultado.marca_detectada = marca
            resultado.exitoso = True
            logger.info(
                "Marca resuelta — UPC Item DB",
                extra={"codigo": codigo, "ean": ean, "marca": marca},
            )
            return resultado

        # ── Buscar en Bing (pasos 2, 3 y 4) ──────────────────────────────────
        settings = get_settings()
        wait = WebDriverWait(driver, settings.browser_timeout)

        try:
            url_busqueda = _BING_URL.format(query=quote_plus(f'"{ean}"'))
            driver.get(url_busqueda)
            self._descartar_cookies(driver)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, _SEL_RESULTADOS)))
            time.sleep(0.4)

            # Extraer URLs, títulos y snippets ANTES de navegar a otra página
            enlaces = self._obtener_enlaces_resultado(driver, n=_MAX_URLS_PASO2)

            titulos: list[str] = [
                el.text.strip()
                for el in driver.find_elements(By.CSS_SELECTOR, _SEL_TITULOS)[:_NUM_RESULTADOS]
                if el.text.strip()
            ]
            resultado.titulos_analizados = titulos

            snippets: list[str] = [
                el.text.strip()
                for el in driver.find_elements(By.CSS_SELECTOR, _SEL_SNIPPETS)[:_NUM_RESULTADOS]
                if el.text.strip()
            ]

        except Exception as exc:
            resultado.error = str(exc)
            logger.warning(
                "Error cargando Bing", exc_info=exc,
                extra={"codigo": codigo, "ean": ean},
            )
            return resultado

        # ── Paso 2: visita Selenium de las primeras URLs ──────────────────────
        # Usamos el driver (navegador real) en lugar de requests para sortear
        # la protección anti-bot de muchas tiendas online.
        for enlace in enlaces:
            marca = self._extraer_de_pagina_con_driver(enlace, driver)
            if marca:
                resultado.marca_detectada = marca
                resultado.exitoso = True
                logger.info(
                    "Marca resuelta — página producto (Selenium)",
                    extra={"codigo": codigo, "ean": ean, "marca": marca, "url": enlace},
                )
                return resultado

        # ── Paso 3: patrón "Marca: X" en snippets de Bing ────────────────────
        marca = self._extraer_de_snippets(snippets)

        # ── Paso 4: frecuencia de unigramas en títulos ────────────────────────
        if not marca:
            marca = self._extraer_de_titulos(titulos)

        if marca:
            resultado.marca_detectada = marca
            resultado.exitoso = True
            logger.info(
                "Marca resuelta — análisis Bing",
                extra={"codigo": codigo, "ean": ean, "marca": marca},
            )
        else:
            muestra = " | ".join(titulos[:3]) if titulos else "sin resultados en Bing"
            resultado.error = f"No se pudo identificar la marca. Títulos: {muestra}"
            logger.debug(
                "Marca no identificada",
                extra={"codigo": codigo, "ean": ean},
            )

        return resultado

    # ── Paso 1: Open*Facts ────────────────────────────────────────────────────

    @staticmethod
    def _es_ean_numerico(ean: str) -> bool:
        """Devuelve True si el valor es un código de barras numérico (8-14 dígitos)."""
        return bool(re.fullmatch(r"\d{8,14}", ean.strip()))

    @staticmethod
    def _buscar_en_open_facts(ean: str) -> str:
        """
        Consulta las APIs Open*Facts en cascada para obtener el campo `brands`.

        Args:
            ean: código EAN numérico del producto.

        Returns:
            Primera marca del campo `brands` en Title Case, o cadena vacía.
        """
        for url_tpl in _OPEN_FACTS_APIS:
            try:
                resp = http_requests.get(
                    url_tpl.format(ean=ean),
                    timeout=_HTTP_TIMEOUT_S,
                    headers=_HEADERS_API,
                )
                if not resp.ok:
                    continue
                data = resp.json()
                if data.get("status") != 1:
                    continue
                brands_raw: str = data.get("product", {}).get("brands", "").strip()
                if brands_raw:
                    primera = brands_raw.split(",")[0].strip()
                    if primera:
                        return primera.title()
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "Error en API Open*Facts",
                    exc_info=exc,
                    extra={"ean": ean},
                )
        return ""

    # ── Paso 1b: UPC Item DB ──────────────────────────────────────────────────

    @staticmethod
    def _buscar_en_upc_db(ean: str) -> str:
        """
        Consulta UPC Item DB para obtener la marca del producto.

        Base de datos generalista que complementa a Open*Facts para productos
        no alimenticios (electrónica, mascotas, hogar, etc.).

        Args:
            ean: código EAN numérico del producto.

        Returns:
            Marca en Title Case, o cadena vacía si no se encuentra.
        """
        try:
            resp = http_requests.get(
                _UPC_ITEM_DB_URL.format(ean=ean),
                timeout=_HTTP_TIMEOUT_S,
                headers=_HEADERS_API,
            )
            if not resp.ok:
                return ""
            data = resp.json()
            items = data.get("items", [])
            if items:
                brand: str = items[0].get("brand", "").strip()
                if brand:
                    return brand.title()
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Error en UPC Item DB",
                exc_info=exc,
                extra={"ean": ean},
            )
        return ""

    # ── Paso 2: visita Selenium de páginas de producto ────────────────────────

    @staticmethod
    def _obtener_enlaces_resultado(driver: WebDriver, n: int = 2) -> list[str]:
        """
        Extrae hasta N URLs de resultados de Bing, excluyendo dominios propios.

        Primero intenta los resultados orgánicos (`li.b_algo h2 a`). Si no hay
        ninguno (p. ej. Bing muestra solo un panel de compras), recurre a todos
        los enlaces presentes en `#b_results` que apunten a dominios externos.

        Args:
            driver: WebDriver con la página de resultados de Bing cargada.
            n: número máximo de URLs a devolver.

        Returns:
            Lista ordenada de URLs de producto (puede estar vacía).
        """
        def _es_externo(href: str) -> bool:
            return (
                bool(href)
                and href.startswith("http")
                and not any(d in href for d in _DOMINIOS_EXCLUIDOS)
            )

        hrefs: list[str] = []

        try:
            for el in driver.find_elements(By.CSS_SELECTOR, _SEL_ENLACES_ORGANICOS):
                href = el.get_attribute("href") or ""
                if _es_externo(href) and href not in hrefs:
                    hrefs.append(href)
                if len(hrefs) >= n:
                    return hrefs

            if not hrefs:
                for el in driver.find_elements(By.CSS_SELECTOR, "#b_results a[href]"):
                    href = el.get_attribute("href") or ""
                    if _es_externo(href) and href not in hrefs:
                        hrefs.append(href)
                    if len(hrefs) >= n:
                        return hrefs

        except Exception as exc:  # noqa: BLE001
            logger.debug("Error obteniendo enlaces de Bing", exc_info=exc)

        return hrefs

    @staticmethod
    def _extraer_de_pagina_con_driver(url: str, driver: WebDriver) -> str:
        """
        Navega a la URL con el driver Selenium y extrae la marca de la página.

        Usar el driver en lugar de `requests` evita el bloqueo anti-bot y
        permite obtener el HTML completo tras la ejecución de JavaScript.

        Args:
            url: URL de la página del producto.
            driver: WebDriver activo.

        Returns:
            Nombre de marca en Title Case, o cadena vacía si no se encuentra.
        """
        try:
            driver.get(url)
            WebDriverWait(driver, _SELENIUM_PAGE_TIMEOUT_S).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(0.5)   # margen para que el JS inicialice el JSON-LD
            return EanBrandResolver._extraer_marca_de_html(driver.page_source)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Error en visita Selenium de página",
                exc_info=exc,
                extra={"url": url},
            )
            return ""

    @staticmethod
    def _extraer_marca_de_html(html: str) -> str:
        """
        Extrae el nombre de marca de un HTML de página de producto.

        Orden de preferencia:
          1. JSON-LD Schema.org  ``{"@type":"Product","brand":{"name":"X"}}``
          2. ``itemprop="brand"`` (microdata)
          3. ``og:site_name`` (meta Open Graph)
          4. Título de página  "Nombre producto - Marca"
          5. Patrón "Marca: X" en el HTML

        Args:
            html: contenido HTML completo de la página.

        Returns:
            Nombre de marca en Title Case, o cadena vacía si no se encuentra.
        """
        # ── 1. JSON-LD con @type Product ──────────────────────────────────────
        for ld_raw in re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html,
            re.DOTALL | re.IGNORECASE,
        ):
            try:
                ld = json.loads(ld_raw.strip())
                items = ld if isinstance(ld, list) else [ld]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    tipo = item.get("@type", "")
                    if isinstance(tipo, list):
                        tipo = " ".join(tipo)
                    if "product" not in tipo.lower():
                        continue
                    brand = item.get("brand", {})
                    if isinstance(brand, dict):
                        nombre = brand.get("name", "")
                    elif isinstance(brand, str):
                        nombre = brand
                    else:
                        nombre = ""
                    if nombre and nombre.strip():
                        return nombre.strip().title()
            except (json.JSONDecodeError, AttributeError, TypeError):
                continue

        # ── 2. itemprop="brand" ───────────────────────────────────────────────
        m = re.search(
            r'itemprop=["\']brand["\'][^>]*>(?:<[^>]+>)*([^<]{2,40})',
            html,
            re.IGNORECASE,
        )
        if m:
            valor = m.group(1).strip()
            if valor:
                return valor.title()

        # ── 3. og:site_name ───────────────────────────────────────────────────
        for patron_og in (
            r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']{2,50})["\']',
            r'<meta[^>]+content=["\']([^"\']{2,50})["\'][^>]+property=["\']og:site_name["\']',
        ):
            m = re.search(patron_og, html, re.IGNORECASE)
            if m:
                valor = m.group(1).strip()
                palabras = valor.split()
                if 1 <= len(palabras) <= 4 and not any(p.isdigit() for p in palabras):
                    return valor.title()

        # ── 4. Título de página "Producto - Marca" ────────────────────────────
        m = re.search(r'<title[^>]*>([^<]{5,150})</title>', html, re.IGNORECASE)
        if m:
            titulo_pag = _html_lib.unescape(m.group(1)).strip()
            for sep in _SEPARADORES_TITULO:
                partes = titulo_pag.rsplit(sep, 1)
                if len(partes) == 2:
                    candidato = partes[1].strip()
                    palabras = candidato.split()
                    if 1 <= len(palabras) <= 4 and not any(
                        c.isdigit() for c in candidato
                    ):
                        return candidato.title()

        # ── 5. "Marca: X" en el HTML de la página ────────────────────────────
        m = re.search(_PATRON_MARCA, html)
        if m:
            valor = m.group(1).strip()
            palabras = valor.split()
            if 1 <= len(palabras) <= 4 and not any(p.isdigit() for p in palabras):
                return valor.title()

        return ""

    # ── Paso 3: snippets Bing ─────────────────────────────────────────────────

    @staticmethod
    def _extraer_de_snippets(snippets: list[str]) -> str:
        """
        Busca el patrón "Marca: X" en los snippets de descripción de Bing.

        Args:
            snippets: textos de los snippets de los resultados de Bing.

        Returns:
            La marca más frecuente en Title Case, o cadena vacía.
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

    # ── Paso 4: frecuencia en títulos ─────────────────────────────────────────

    @staticmethod
    def _extraer_de_titulos(titulos: list[str]) -> str:
        """
        Extrae la marca por frecuencia de unigramas en los títulos de Bing.

        Args:
            titulos: títulos de los primeros resultados de Bing.

        Returns:
            La palabra más frecuente no filtrada en Title Case, o cadena vacía.
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
        return presencia.most_common(1)[0][0].title()
