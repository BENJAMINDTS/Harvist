"""
Productor del pipeline de scraping: búsqueda de URLs de imágenes vía múltiples motores.

Implementa el patrón Estrategia mediante la abstracción ``MotorBusqueda`` (ABC).
Los motores disponibles son Bing Images, Google Images y DuckDuckGo Images.
La fábrica de navegadores ``_crear_driver`` soporta 5 tipos configurables
mediante la variable de entorno ``BROWSER_TYPE`` (chrome | chromium | edge | brave | opera).

El motor de búsqueda activo se selecciona a través de ``SEARCH_ENGINE``
(bing | google | duckduckgo). Ninguna URL, selector ni credencial se hardcodea
fuera de las clases de motor o de la capa de Settings.

:author: BenjaminDTS
:version: 2.0.0
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Callable
from urllib.parse import quote_plus

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
    version_main = settings.browser_version_main  # None si no está configurado

    # ── Navegadores Chromium-based (undetected_chromedriver) ──────────────────
    # Chrome y Chromium: uc auto-detecta la versión si version_main es None.
    # Brave y Opera: requieren version_main porque su versión de app ≠ versión
    # interna de Chromium. Configurar BROWSER_VERSION_MAIN en .env con el número
    # que aparece en "Acerca de" → "Versión de Chromium".
    if browser_type in ("chrome", "chromium", "brave", "opera"):
        import undetected_chromedriver as uc

        options = uc.ChromeOptions()
        options.binary_location = binary_path
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")

        # Opera y Brave en modo headless no funcionan correctamente con uc;
        # para Chrome/Chromium headless sí está soportado.
        if headless and browser_type in ("chrome", "chromium"):
            options.add_argument("--headless=new")

        return uc.Chrome(options=options, version_main=version_main)

    # ── Microsoft Edge ────────────────────────────────────────────────────────
    # Usa selenium-manager (incluido en Selenium 4.6+) para descargar
    # msedgedriver automáticamente — no requiere instalación manual del driver.
    if browser_type == "edge":
        from selenium import webdriver
        from selenium.webdriver.edge.options import Options as EdgeOptions
        from selenium.webdriver.edge.service import Service as EdgeService

        options = EdgeOptions()
        options.binary_location = binary_path
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        if headless:
            options.add_argument("--headless=new")
        # Service sin executable_path → selenium-manager descarga msedgedriver
        return webdriver.Edge(options=options, service=EdgeService())

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

        logger.debug(
            "Iniciando búsqueda",
            extra={
                "codigo": producto.codigo,
                "query": producto.query,
                "motor": settings.search_engine,
            },
        )

        urls = motor.buscar_urls(producto.query, cantidad, driver)

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
