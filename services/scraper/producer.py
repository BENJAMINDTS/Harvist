"""
Productor del pipeline de scraping: búsqueda de URLs de imágenes via Bing Images.

Utiliza undetected-chromedriver + Selenium para evadir detección de bots.
La fábrica de navegadores soporta 5 motores configurables via BROWSER_TYPE.

NUNCA hardcodear rutas de navegadores aquí — leer siempre desde Settings.

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from loguru import logger
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from api.core.config import get_settings
from services.csv_parser import Producto

# URL base de búsqueda de Bing Images
_BING_SEARCH_URL = "https://www.bing.com/images/search?q={query}&form=HDRSC2"

# Selector CSS de los thumbnails de Bing Images
_SELECTOR_THUMBNAIL = "a.iusc"

# Atributo JSON que contiene la URL original de la imagen
_ATRIBUTO_M = "m"


@dataclass
class _BrowserProfile:
    """
    Perfil de configuración de un navegador soportado.

    :author: BenjaminDTS
    """

    nombre: str
    driver_class: type
    opciones_class: type
    binary_arg: str          # Argumento de CLI para la ruta del ejecutable


def _crear_driver(settings):
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
        options.binary_location = binary_path
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        return uc.Chrome(options=options)

    if browser_type == "edge":
        from selenium import webdriver
        from selenium.webdriver.edge.options import Options
        from selenium.webdriver.edge.service import Service
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
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        options = Options()
        options.binary_location = binary_path
        if headless:
            options.add_argument("--headless=new")
        options.add_experimental_option("w3c", True)
        return webdriver.Chrome(options=options)

    raise ValueError(
        f"BROWSER_TYPE '{browser_type}' no soportado. "
        "Valores válidos: chrome | chromium | edge | brave | opera"
    )


def buscar_urls_imagenes(
    producto: Producto,
    cantidad: int,
    callback_progreso: Callable[[str, int, int], None] | None = None,
) -> list[str]:
    """
    Busca en Bing Images las URLs de imágenes para un producto.

    Abre el navegador, navega a la página de resultados de Bing Images
    y extrae las URLs originales de los thumbnails. Cierra el navegador
    al terminar, incluso si hay errores.

    Args:
        producto: producto con la query ya construida.
        cantidad: número máximo de URLs a extraer.
        callback_progreso: función opcional invocada con (job_id, encontradas, total)
                           para actualizar el progreso del job en Redis.

    Returns:
        Lista de URLs de imágenes encontradas (puede ser menor que cantidad
        si Bing devuelve menos resultados).

    Raises:
        WebDriverException: si el driver no puede iniciarse o la navegación falla.
    """
    settings = get_settings()
    driver = None
    urls: list[str] = []

    try:
        driver = _crear_driver(settings)
        driver.set_page_load_timeout(settings.browser_timeout)

        url_busqueda = _BING_SEARCH_URL.format(
            query=_codificar_query(producto.query)
        )
        logger.debug(
            "Iniciando búsqueda",
            extra={"codigo": producto.codigo, "query": producto.query},
        )

        driver.get(url_busqueda)

        # Esperar a que carguen los thumbnails
        try:
            WebDriverWait(driver, settings.browser_timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, _SELECTOR_THUMBNAIL))
            )
        except TimeoutException:
            logger.warning(
                "Timeout esperando thumbnails de Bing",
                extra={"codigo": producto.codigo, "query": producto.query},
            )
            return []

        elementos = driver.find_elements(By.CSS_SELECTOR, _SELECTOR_THUMBNAIL)

        for elemento in elementos[:cantidad * 2]:  # buffer para filtrar inválidas
            if len(urls) >= cantidad:
                break
            url = _extraer_url_original(elemento)
            if url:
                urls.append(url)

        logger.info(
            "Búsqueda completada",
            extra={"codigo": producto.codigo, "urls_encontradas": len(urls)},
        )

    except WebDriverException as exc:
        logger.error(
            "Error del WebDriver durante la búsqueda",
            exc_info=exc,
            extra={"codigo": producto.codigo},
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


def _extraer_url_original(elemento) -> str | None:
    """
    Extrae la URL original de la imagen desde el atributo JSON del thumbnail.

    Bing almacena los metadatos de cada imagen en el atributo 'm' del elemento
    como JSON. Parseamos solo el campo 'murl' (media URL) que apunta a la imagen
    original en alta resolución.

    Args:
        elemento: WebElement del thumbnail de Bing Images.

    Returns:
        URL de la imagen original, o None si no se puede extraer.
    """
    import json as _json

    try:
        datos_raw = elemento.get_attribute(_ATRIBUTO_M)
        if not datos_raw:
            return None
        datos = _json.loads(datos_raw)
        url = datos.get("murl", "")
        if url and url.startswith("http"):
            return url
    except Exception:
        pass

    return None


def _codificar_query(query: str) -> str:
    """
    Codifica la query para incluirla en la URL de Bing Images.

    Args:
        query: string de búsqueda ya sanitizado.

    Returns:
        Query codificada para URL.
    """
    from urllib.parse import quote_plus
    return quote_plus(query)
