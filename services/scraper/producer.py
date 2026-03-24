"""
Productor del pipeline de scraping: búsqueda de URLs de imágenes vía múltiples motores.

Implementa el patrón Estrategia mediante la abstracción ``MotorBusqueda`` (ABC).
Los motores disponibles son Bing Images, Google Images y DuckDuckGo Images.
La fábrica de navegadores ``_crear_driver`` soporta 5 tipos configurables
mediante la variable de entorno ``BROWSER_TYPE`` (chrome | chromium | edge | brave | opera).

El motor de búsqueda activo se selecciona a través de ``SEARCH_ENGINE``
(bing | google | duckduckgo). Ninguna URL, selector ni credencial se hardcodea
fuera de las clases de motor o de la capa de Settings.

Cuando el modo de búsqueda es EAN y ``EAN_ENRICHMENT_ENABLED=true``, se
ejecuta una cadena de enriquecimiento de 3 niveles para resolver el EAN
a un nombre de producto semántico antes de buscar imágenes:

  1. ``BarcodeApiLookup`` — petición HTTP a UPC Item DB (sin Selenium,
     sin riesgo de bot detection). Cubre la mayoría de EANs globales.
  2. ``GoogleEANEnricher`` — búsqueda web exacta (``"EAN"``) via Selenium
     para EANs no presentes en la base de datos de barras.
  3. EAN desnudo en el motor configurado — último recurso.

:author: BenjaminDTS
:version: 2.2.0
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections import Counter
from typing import Callable
from urllib.parse import quote_plus

import requests as _requests

from loguru import logger
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from api.core.config import get_settings
from services.csv_parser import Producto


# ---------------------------------------------------------------------------
# Utilidades de módulo
# ---------------------------------------------------------------------------


def _codificar_query(query: str) -> str:
    """
    Codifica la query para incluirla de forma segura en cualquier URL de búsqueda.

    Usa ``quote_plus`` para que los espacios se conviertan en ``+`` y los
    caracteres especiales sean escapados según RFC 3986, compatible con todos
    los motores soportados.

    Args:
        query: string de búsqueda ya sanitizado (sin codificar para URL).

    Returns:
        Query codificada para URL en formato ``application/x-www-form-urlencoded``.
    """
    return quote_plus(query)


# ---------------------------------------------------------------------------
# Abstracción base — Motor de búsqueda
# ---------------------------------------------------------------------------


class MotorBusqueda(ABC):
    """
    Interfaz abstracta para los motores de búsqueda de imágenes.

    Cada implementación concreta encapsula la URL de búsqueda, los selectores
    CSS y la lógica de extracción de URLs propias de ese motor. El driver
    se recibe como parámetro para que el ciclo de vida del navegador sea
    responsabilidad exclusiva del pipeline (principio de inversión de dependencias).

    :author: BenjaminDTS
    """

    @abstractmethod
    def buscar_urls(self, query: str, cantidad: int, driver: WebDriver) -> list[str]:
        """
        Navega al motor de búsqueda y extrae URLs de imágenes originales.

        Args:
            query: término de búsqueda ya sanitizado (sin codificar para URL).
            cantidad: número máximo de URLs a devolver.
            driver: instancia de WebDriver ya iniciada y configurada.

        Returns:
            Lista de URLs de imágenes encontradas. Puede contener menos
            elementos que ``cantidad`` si el motor devuelve menos resultados.

        Raises:
            TimeoutException: si los thumbnails no cargan en el tiempo configurado.
            WebDriverException: si la navegación falla por un error del driver.
        """


# ---------------------------------------------------------------------------
# Implementaciones concretas
# ---------------------------------------------------------------------------


class BingMotor(MotorBusqueda):
    """
    Motor de búsqueda de imágenes para Bing Images.

    Navega a ``https://www.bing.com/images/search`` y extrae la URL original
    de cada imagen desde el atributo JSON ``m`` del elemento ``a.iusc``.
    El campo ``murl`` dentro de ese JSON contiene la URL de alta resolución.

    :author: BenjaminDTS
    """

    _URL_BASE: str = "https://www.bing.com/images/search?q={query}&form=HDRSC2"
    _SELECTOR_THUMBNAIL: str = "a.iusc"
    _ATRIBUTO_JSON: str = "m"

    def buscar_urls(self, query: str, cantidad: int, driver: WebDriver) -> list[str]:
        """
        Extrae URLs de imágenes en alta resolución desde Bing Images.

        Navega a la URL de búsqueda, espera a que aparezcan los thumbnails
        ``a.iusc`` y parsea el atributo JSON ``m`` de cada uno para obtener
        el campo ``murl`` con la URL original de la imagen.

        Args:
            query: término de búsqueda sin codificar.
            cantidad: número máximo de URLs a devolver.
            driver: instancia de WebDriver activa.

        Returns:
            Lista de URLs originales en alta resolución extraídas de ``murl``.

        Raises:
            TimeoutException: si los thumbnails no aparecen en el tiempo límite.
            WebDriverException: si la navegación falla.
        """
        settings = get_settings()
        url = self._URL_BASE.format(query=_codificar_query(query))

        driver.get(url)

        try:
            WebDriverWait(driver, settings.browser_timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, self._SELECTOR_THUMBNAIL)
                )
            )
        except TimeoutException:
            logger.warning(
                "Timeout esperando thumbnails de Bing",
                extra={"query": query, "motor": "bing"},
            )
            return []

        elementos: list[WebElement] = driver.find_elements(
            By.CSS_SELECTOR, self._SELECTOR_THUMBNAIL
        )

        urls: list[str] = []
        for elemento in elementos[: cantidad * 2]:
            if len(urls) >= cantidad:
                break
            url_imagen = self._extraer_url_original(elemento)
            if url_imagen:
                urls.append(url_imagen)

        return urls

    def _extraer_url_original(self, elemento: WebElement) -> str | None:
        """
        Extrae la URL original desde el atributo JSON ``m`` del thumbnail de Bing.

        Bing almacena los metadatos de cada imagen en el atributo ``m`` como JSON.
        Parseamos únicamente el campo ``murl`` (media URL) que apunta a la imagen
        original en alta resolución.

        Args:
            elemento: WebElement del thumbnail ``a.iusc`` de Bing Images.

        Returns:
            URL de la imagen original, o None si no se puede extraer.
        """
        try:
            datos_raw = elemento.get_attribute(self._ATRIBUTO_JSON)
            if not datos_raw:
                return None
            datos: dict[str, str] = json.loads(datos_raw)
            url = datos.get("murl", "")
            if url and url.startswith("http"):
                return url
        except Exception as exc:
            logger.debug(
                "No se pudo extraer URL del thumbnail de Bing",
                exc_info=exc,
            )

        return None


class GoogleMotor(MotorBusqueda):
    """
    Motor de búsqueda de imágenes para Google Images.

    Navega a ``https://www.google.com/search?tbm=isch`` y extrae el atributo
    ``src`` de los elementos ``img.YQ4gaf`` (thumbnails de la cuadrícula de
    resultados). Los ``src`` pueden ser Data URIs o URLs de proxy de Google;
    se filtran los valores vacíos automáticamente.

    :author: BenjaminDTS
    """

    _URL_BASE: str = "https://www.google.com/search?tbm=isch&q={query}"
    _SELECTOR_THUMBNAIL: str = "img.YQ4gaf"

    def buscar_urls(self, query: str, cantidad: int, driver: WebDriver) -> list[str]:
        """
        Extrae URLs de thumbnails desde Google Images.

        Navega a la URL de búsqueda de imágenes de Google, espera a que carguen
        los elementos ``img.YQ4gaf`` y extrae el atributo ``src`` de cada uno.

        Args:
            query: término de búsqueda sin codificar.
            cantidad: número máximo de URLs a devolver.
            driver: instancia de WebDriver activa.

        Returns:
            Lista de valores ``src`` de los elementos ``img.YQ4gaf`` encontrados.

        Raises:
            TimeoutException: si los thumbnails no aparecen en el tiempo límite.
            WebDriverException: si la navegación falla.
        """
        settings = get_settings()
        url = self._URL_BASE.format(query=_codificar_query(query))

        driver.get(url)

        try:
            WebDriverWait(driver, settings.browser_timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, self._SELECTOR_THUMBNAIL)
                )
            )
        except TimeoutException:
            logger.warning(
                "Timeout esperando thumbnails de Google Images",
                extra={"query": query, "motor": "google"},
            )
            return []

        elementos: list[WebElement] = driver.find_elements(
            By.CSS_SELECTOR, self._SELECTOR_THUMBNAIL
        )

        urls: list[str] = []
        for elemento in elementos[: cantidad * 2]:
            if len(urls) >= cantidad:
                break
            src = self._extraer_src(elemento)
            if src:
                urls.append(src)

        return urls

    def _extraer_src(self, elemento: WebElement) -> str | None:
        """
        Extrae el atributo ``src`` de un elemento ``img`` de Google Images.

        Args:
            elemento: WebElement ``img.YQ4gaf`` de la cuadrícula de resultados.

        Returns:
            Valor del atributo ``src`` limpio, o None si está vacío o ausente.
        """
        try:
            src = elemento.get_attribute("src")
            if src and src.strip():
                return src.strip()
        except Exception as exc:
            logger.debug(
                "No se pudo extraer src del thumbnail de Google",
                exc_info=exc,
            )

        return None


class DuckDuckGoMotor(MotorBusqueda):
    """
    Motor de búsqueda de imágenes para DuckDuckGo Images.

    Navega a ``https://duckduckgo.com/?iax=images&ia=images`` y extrae el
    atributo ``src`` de los elementos ``img.tile--img__img`` (thumbnails de la
    cuadrícula de resultados de DuckDuckGo).

    :author: BenjaminDTS
    """

    _URL_BASE: str = "https://duckduckgo.com/?q={query}&iax=images&ia=images"
    _SELECTOR_THUMBNAIL: str = "img.tile--img__img"

    def buscar_urls(self, query: str, cantidad: int, driver: WebDriver) -> list[str]:
        """
        Extrae URLs de thumbnails desde DuckDuckGo Images.

        Navega a la URL de búsqueda, espera a que carguen los elementos
        ``img.tile--img__img`` y extrae el atributo ``src`` de cada uno.

        Args:
            query: término de búsqueda sin codificar.
            cantidad: número máximo de URLs a devolver.
            driver: instancia de WebDriver activa.

        Returns:
            Lista de valores ``src`` de los elementos ``img.tile--img__img``.

        Raises:
            TimeoutException: si los thumbnails no aparecen en el tiempo límite.
            WebDriverException: si la navegación falla.
        """
        settings = get_settings()
        url = self._URL_BASE.format(query=_codificar_query(query))

        driver.get(url)

        try:
            WebDriverWait(driver, settings.browser_timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, self._SELECTOR_THUMBNAIL)
                )
            )
        except TimeoutException:
            logger.warning(
                "Timeout esperando thumbnails de DuckDuckGo",
                extra={"query": query, "motor": "duckduckgo"},
            )
            return []

        elementos: list[WebElement] = driver.find_elements(
            By.CSS_SELECTOR, self._SELECTOR_THUMBNAIL
        )

        urls: list[str] = []
        for elemento in elementos[: cantidad * 2]:
            if len(urls) >= cantidad:
                break
            src = self._extraer_src(elemento)
            if src:
                urls.append(src)

        return urls

    def _extraer_src(self, elemento: WebElement) -> str | None:
        """
        Extrae el atributo ``src`` de un elemento ``img`` de DuckDuckGo Images.

        Args:
            elemento: WebElement ``img.tile--img__img`` de la cuadrícula.

        Returns:
            Valor del atributo ``src`` limpio, o None si está vacío o ausente.
        """
        try:
            src = elemento.get_attribute("src")
            if src and src.strip():
                return src.strip()
        except Exception as exc:
            logger.debug(
                "No se pudo extraer src del thumbnail de DuckDuckGo",
                exc_info=exc,
            )

        return None


# ---------------------------------------------------------------------------
# Tier 1 — Lookup EAN vía API de códigos de barras (HTTP puro, sin Selenium)
# ---------------------------------------------------------------------------


class BarcodeApiLookup:
    """
    Resuelve un EAN a nombre de producto mediante la API pública de UPC Item DB.

    No requiere WebDriver: usa una petición HTTP directa, sin riesgo de
    detección de bot ni consumo de tiempo de navegador. Cubre la mayoría de
    EANs de consumo global (alimentación, hogar, mascotas, cosmética, etc.).

    Límite gratuito: 100 peticiones / día. Para volúmenes mayores, configurar
    una clave en ``BARCODE_API_KEY`` y usar el endpoint de producción.

    :author: BenjaminDTS
    """

    _URL_TRIAL: str = "https://api.upcitemdb.com/prod/trial/lookup?upc={ean}"
    _TIMEOUT: int = 5
    _HEADERS: dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (compatible; HarvistScraper/1.0)",
        "Accept": "application/json",
    }

    def lookup(self, ean: str) -> str | None:
        """
        Consulta UPC Item DB y devuelve marca + título del producto.

        Args:
            ean: código EAN/UPC a buscar (solo dígitos).

        Returns:
            String con ``"marca título"`` listo para usar como query de imagen,
            o ``None`` si el EAN no está en la base de datos o la petición falla.
        """
        url = self._URL_TRIAL.format(ean=ean)

        try:
            respuesta = _requests.get(url, headers=self._HEADERS, timeout=self._TIMEOUT)
            respuesta.raise_for_status()
            datos: dict = respuesta.json()

            items: list[dict] = datos.get("items", [])
            if not items:
                logger.debug(
                    "EAN no encontrado en UPC Item DB",
                    extra={"ean": ean},
                )
                return None

            item = items[0]
            brand: str = item.get("brand", "").strip()
            title: str = item.get("title", "").strip()

            # Evitar duplicar la marca si el título ya la incluye al inicio
            if brand and not title.lower().startswith(brand.lower()):
                query = f"{brand} {title}"
            else:
                query = title

            query = query[:120].strip()
            if not query:
                return None

            logger.info(
                "EAN resuelto vía UPC Item DB",
                extra={"ean": ean, "query": query},
            )
            return query

        except _requests.exceptions.RequestException as exc:
            logger.warning(
                "Error en UPC Item DB lookup",
                exc_info=exc,
                extra={"ean": ean},
            )
            return None


# ---------------------------------------------------------------------------
# Tier 2 — Enricher EAN vía Google web dork (Selenium)
# ---------------------------------------------------------------------------


class GoogleEANEnricher:
    """
    Resuelve un EAN a nombre de producto mediante búsqueda web exacta en Google.

    Navega a ``https://www.google.com/search?q=%22EAN%22`` (búsqueda web, no
    imágenes), extrae el texto de los primeros ``h3`` de resultados, filtra
    palabras de ruido comercial y devuelve las palabras más repetidas como
    query enriquecida para el motor de imágenes.

    Se reutiliza el mismo ``WebDriver`` del pipeline para no abrir un
    navegador extra por producto.

    :author: BenjaminDTS
    """

    _URL_BUSQUEDA: str = "https://www.google.com/search?q=%22{ean}%22"
    # #rso = Google Results Section Organizer: selector estable que acota
    # los h3 a los títulos de resultados reales, evitando los tabs de
    # navegación ("Imágenes", "Vídeos"...) que también son h3.
    _SELECTOR_ESPERAR: str = "#rso"
    _SELECTOR_TITULOS: str = "#rso h3"
    _NUM_RESULTADOS: int = 4
    _NUM_PALABRAS_QUERY: int = 5

    _PALABRAS_RUIDO: frozenset[str] = frozenset({
        # Artículos y conectores
        "de", "la", "el", "los", "las", "un", "una", "y", "a", "en", "con",
        "por", "del", "al", "o", "e", "ni", "pero", "sin", "para", "su",
        "sus", "que", "es", "se", "le", "lo", "nos", "mas", "si",
        # Términos comerciales
        "comprar", "precio", "barato", "oferta", "descuento", "online",
        "entrega", "gratis", "stock", "disponible", "compra", "venta",
        "vender", "tienda", "producto", "articulo", "pack", "caja",
        "unidad", "unidades", "envio", "envío",
        # Plataformas de e-commerce
        "amazon", "ebay", "aliexpress", "carrefour", "mercadona",
        "walmart", "fnac", "pccomponentes", "mediamarkt",
        # Unidades de medida
        "kg", "gr", "g", "ml", "l", "lt", "cm", "mm",
    })

    def enriquecer(self, ean: str, driver: WebDriver) -> str | None:
        """
        Busca el EAN en Google web y extrae el nombre del producto de los h3.

        Args:
            ean: código EAN sin codificar (solo dígitos).
            driver: instancia de WebDriver activa, reutilizada del pipeline.

        Returns:
            String con las palabras más representativas del producto extraídas
            de los títulos de resultados, o ``None`` si no se pudo enriquecer.
        """
        settings = get_settings()
        url = self._URL_BUSQUEDA.format(ean=ean)

        try:
            driver.get(url)
            # Esperar a #rso (Results Section Organizer) garantiza que los
            # resultados reales están cargados, no solo los tabs de navegación.
            WebDriverWait(driver, settings.browser_timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, self._SELECTOR_ESPERAR)
                )
            )
        except TimeoutException:
            logger.warning(
                "Timeout en Google web al enriquecer EAN",
                extra={"ean": ean},
            )
            return None

        elementos: list[WebElement] = driver.find_elements(
            By.CSS_SELECTOR, self._SELECTOR_TITULOS
        )[: self._NUM_RESULTADOS]

        textos = [e.text.strip() for e in elementos if e.text.strip()]
        if not textos:
            logger.debug(
                "Sin títulos h3 en resultados Google web",
                extra={"ean": ean},
            )
            return None

        frecuencia: Counter[str] = Counter()
        for titulo in textos:
            for palabra_raw in titulo.lower().split():
                # re.UNICODE preserva letras de cualquier idioma europeo
                # (polaco ą/ę/ż, alemán ä/ö/ü, etc.) evitando mutilar
                # nombres de producto que vengan en idioma del fabricante.
                palabra = re.sub(r"[^\w]", "", palabra_raw, flags=re.UNICODE)
                if (
                    len(palabra) > 2
                    and palabra not in self._PALABRAS_RUIDO
                    and not palabra.isdigit()
                ):
                    frecuencia[palabra] += 1

        if not frecuencia:
            logger.debug(
                "Sin palabras útiles tras filtrar ruido",
                extra={"ean": ean, "titulos": textos},
            )
            return None

        top = [p for p, _ in frecuencia.most_common(self._NUM_PALABRAS_QUERY)]
        query_enriquecida = " ".join(top)

        logger.info(
            "EAN enriquecido con nombre de producto",
            extra={"ean": ean, "query": query_enriquecida, "titulos": textos},
        )
        return query_enriquecida


# ---------------------------------------------------------------------------
# Factory de motores
# ---------------------------------------------------------------------------


def _crear_motor(search_engine: str) -> MotorBusqueda:
    """
    Devuelve la implementación de ``MotorBusqueda`` correspondiente al motor indicado.

    Actúa como factory centralizada para que el resto del código no dependa
    directamente de las clases concretas de motor.

    Args:
        search_engine: identificador del motor de búsqueda.
            Valores válidos: ``"bing"``, ``"google"``, ``"duckduckgo"``.

    Returns:
        Instancia concreta de ``MotorBusqueda`` lista para usar.

    Raises:
        ValueError: si ``search_engine`` no corresponde a ningún motor soportado.
    """
    motores: dict[str, type[MotorBusqueda]] = {
        "bing": BingMotor,
        "google": GoogleMotor,
        "duckduckgo": DuckDuckGoMotor,
    }

    clase_motor = motores.get(search_engine.lower())
    if clase_motor is None:
        raise ValueError(
            f"SEARCH_ENGINE '{search_engine}' no soportado. "
            "Valores válidos: bing | google | duckduckgo"
        )

    return clase_motor()


# ---------------------------------------------------------------------------
# Fábrica de navegadores (conservada intacta)
# ---------------------------------------------------------------------------


def _crear_driver(settings) -> WebDriver:
    """
    Instancia el WebDriver correspondiente al BROWSER_TYPE configurado.

    El driver se crea sin gestión de contexto porque su ciclo de vida
    está controlado por el pipeline (se cierra explícitamente en finally).

    Args:
        settings: instancia de Settings con la configuración de navegador.

    Returns:
        WebDriver configurado y listo para usar.

    Raises:
        ValueError: si BROWSER_TYPE no está soportado.
        WebDriverException: si el ejecutable no se encuentra o falla al iniciar.
    """
    browser_type = settings.browser_type
    binary_path = settings.browser_binary_path
    headless = settings.browser_headless

    if browser_type == "chrome":
        import undetected_chromedriver as uc
        options = uc.ChromeOptions()
        if binary_path:
            options.binary_location = binary_path
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        return uc.Chrome(options=options)

    if browser_type == "chromium":
        import undetected_chromedriver as uc
        options = uc.ChromeOptions()
        if binary_path:
            options.binary_location = binary_path
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        return uc.Chrome(options=options)

    if browser_type == "edge":
        from selenium import webdriver
        from selenium.webdriver.edge.options import Options
        options = Options()
        options.binary_location = binary_path
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        return webdriver.Edge(options=options)

    if browser_type == "brave":
        import undetected_chromedriver as uc
        options = uc.ChromeOptions()
        options.binary_location = binary_path
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        return uc.Chrome(options=options)

    if browser_type == "opera":
        # Opera GX es Chromium-based. Se necesita version_main para que uc descargue
        # el chromedriver correcto. Se lee de BROWSER_VERSION_MAIN (opcional).
        import undetected_chromedriver as uc
        options = uc.ChromeOptions()
        options.binary_location = binary_path
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        # headless no funciona bien con Opera GX — forzar modo visible
        version_main = getattr(settings, "browser_version_main", None)
        return uc.Chrome(options=options, version_main=version_main)

    raise ValueError(
        f"BROWSER_TYPE '{browser_type}' no soportado. "
        "Valores válidos: chrome | chromium | edge | brave | opera"
    )


# ---------------------------------------------------------------------------
# Función pública — contrato sin cambios
# ---------------------------------------------------------------------------


def buscar_urls_imagenes(
    producto: Producto,
    cantidad: int,
    callback_progreso: Callable[[str, int, int], None] | None = None,
) -> list[str]:
    """
    Busca en el motor configurado las URLs de imágenes para un producto.

    Abre el navegador, delega la extracción de URLs al ``MotorBusqueda``
    seleccionado por ``settings.search_engine`` y cierra el navegador al
    terminar, incluso si hay errores.

    El motor de búsqueda se lee de ``settings.search_engine`` (variable de
    entorno ``SEARCH_ENGINE``). Los valores válidos son:
    ``bing``, ``google``, ``duckduckgo``.

    Args:
        producto: producto con la query ya construida.
        cantidad: número máximo de URLs a extraer.
        callback_progreso: función opcional invocada con ``(codigo, encontradas, total)``
                           para actualizar el progreso del job en Redis.

    Returns:
        Lista de URLs de imágenes encontradas. Puede contener menos elementos
        que ``cantidad`` si el motor devuelve menos resultados.

    Raises:
        ValueError: si ``SEARCH_ENGINE`` no corresponde a ningún motor soportado.
        WebDriverException: si el driver no puede iniciarse o la navegación falla.
    """
    settings = get_settings()
    driver: WebDriver | None = None
    urls: list[str] = []

    try:
        motor = _crear_motor(settings.search_engine)
        driver = _crear_driver(settings)
        driver.set_page_load_timeout(settings.browser_timeout)

        # ── EAN enrichment — cadena de 3 niveles ─────────────────────────────
        # Los motores de imágenes no indexan EANs — indexan imágenes.
        # Buscar un EAN directamente devuelve resultados aleatorios.
        # La solución es resolver el EAN a un nombre de producto semántico
        # antes de lanzar la búsqueda de imágenes.
        #
        # Tier 1 — BarcodeApiLookup (HTTP puro, sin bot detection, más fiable)
        # Tier 2 — GoogleEANEnricher (Selenium, por si el EAN no está en la DB)
        # Tier 3 — EAN desnudo en el motor configurado (último recurso)
        query_efectiva = producto.query
        es_modo_ean = bool(
            producto.ean and producto.query == f'"{producto.ean}"'
        )
        if es_modo_ean and settings.ean_enrichment_enabled:
            nombre_producto: str | None = None

            # Tier 1: API de códigos de barras (HTTP, sin Selenium)
            nombre_producto = BarcodeApiLookup().lookup(producto.ean)

            # Tier 2: Google web dork (Selenium) si la API no tiene el EAN
            if not nombre_producto:
                logger.debug(
                    "Tier 1 sin resultado, intentando Google web enricher",
                    extra={"codigo": producto.codigo, "ean": producto.ean},
                )
                nombre_producto = GoogleEANEnricher().enriquecer(
                    producto.ean, driver
                )

            if nombre_producto:
                query_efectiva = nombre_producto
            else:
                # Tier 3: EAN desnudo — Bing lo ignora pero es el último recurso
                query_efectiva = producto.ean
                logger.warning(
                    "Todos los enrichers fallaron, usando EAN desnudo como fallback",
                    extra={"codigo": producto.codigo, "ean": producto.ean},
                )

        logger.debug(
            "Iniciando búsqueda",
            extra={
                "codigo": producto.codigo,
                "query": query_efectiva,
                "motor": settings.search_engine,
                "enriquecido": es_modo_ean and query_efectiva != producto.query,
            },
        )

        urls = motor.buscar_urls(query_efectiva, cantidad, driver)

        if callback_progreso is not None:
            try:
                callback_progreso(producto.codigo, len(urls), cantidad)
            except Exception as exc:
                logger.warning(
                    "Error al invocar callback de progreso",
                    exc_info=exc,
                    extra={"codigo": producto.codigo},
                )

        logger.info(
            "Búsqueda completada",
            extra={
                "codigo": producto.codigo,
                "urls_encontradas": len(urls),
                "motor": settings.search_engine,
            },
        )

    except ValueError:
        raise

    except WebDriverException as exc:
        logger.error(
            "Error del WebDriver durante la búsqueda",
            exc_info=exc,
            extra={"codigo": producto.codigo, "motor": settings.search_engine},
        )
        raise

    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception as exc:
                logger.warning(
                    "Error al cerrar el WebDriver",
                    exc_info=exc,
                    extra={"codigo": producto.codigo},
                )

    return urls
