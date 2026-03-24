"""
Scraper de información de marca usando Bing.

Para cada marca: busca el logo en Bing Images y extrae el sitio web
y descripción del primer resultado de Bing Web.

Mismo patrón que producer.py: recibe un driver Selenium activo y lo reutiliza.

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

import json as _json
import time
from dataclasses import dataclass, field
from urllib.parse import quote_plus

from loguru import logger
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from api.core.config import get_settings


@dataclass
class FichaMarca:
    """
    Datos de una marca extraídos por el scraper.

    :author: BenjaminDTS
    """

    marca: str
    logo_url: str = field(default="")
    website: str = field(default="")
    descripcion: str = field(default="")
    exitoso: bool = field(default=False)
    error: str = field(default="")


class BrandScraper:
    """
    Scraper de información de marca.

    Para cada marca busca en Bing Images el logo y en Bing Web el sitio oficial
    y una descripción breve. Reutiliza el WebDriver activo del productor de imágenes.

    :author: BenjaminDTS
    """

    _URL_LOGO: str = "https://www.bing.com/images/search?q={marca}+logo+marca&first=1"
    _URL_WEB: str = "https://www.bing.com/search?q={marca}+sitio+oficial+marca"

    def scrape(self, marca: str, driver: WebDriver) -> FichaMarca:
        """
        Extrae logo URL, website y descripción de una marca.

        Args:
            marca: nombre de la marca a buscar.
            driver: instancia de WebDriver con sesión de Bing activa.

        Returns:
            FichaMarca con los datos encontrados. exitoso=False si hubo error.
        """
        ficha = FichaMarca(marca=marca)
        settings = get_settings()
        wait = WebDriverWait(driver, settings.browser_timeout)

        try:
            # ── Logo: Bing Images ──────────────────────────────────────────────
            url_logo = self._URL_LOGO.format(marca=quote_plus(marca))
            driver.get(url_logo)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.iusc")))
            time.sleep(0.5)

            elementos = driver.find_elements(By.CSS_SELECTOR, "a.iusc")
            for el in elementos[:5]:
                m_attr = el.get_attribute("m") or ""
                try:
                    data = _json.loads(m_attr)
                    murl = data.get("murl", "")
                    if murl and murl.startswith("http"):
                        ficha.logo_url = murl
                        break
                except Exception:
                    continue

            # ── Web: Bing Search ───────────────────────────────────────────────
            url_web = self._URL_WEB.format(marca=quote_plus(marca))
            driver.get(url_web)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#b_results")))
            time.sleep(0.3)

            # Primer resultado web: URL del sitio
            titulos = driver.find_elements(By.CSS_SELECTOR, "li.b_algo h2 a")
            if titulos:
                ficha.website = titulos[0].get_attribute("href") or ""

            # Snippet/descripción del primer resultado
            snippets = driver.find_elements(By.CSS_SELECTOR, "li.b_algo .b_caption p")
            if snippets:
                ficha.descripcion = snippets[0].text.strip()[:300]

            ficha.exitoso = True
            logger.info(
                "Marca scrapeada",
                extra={"marca": marca, "website": ficha.website},
            )

        except Exception as exc:
            ficha.error = str(exc)
            logger.warning(
                "Error scrapeando marca",
                exc_info=exc,
                extra={"marca": marca},
            )

        return ficha
