"""
Clientes HTTP síncronos para resolución EAN → marca de producto.

Provee dos grupos de clientes:
  · Open Data (Nivel 3): consultan bases de datos públicas de EAN (Open*Facts, UPC Item DB).
  · Buscadores (Niveles 4 y 5): realizan búsquedas web exactas y extraen la marca
    de los títulos de los resultados mediante análisis estadístico de n-gramas.

Todos los clientes son síncronos (httpx.Client) para compatibilidad con Celery.
Ninguno usa Selenium ni ningún navegador.

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

import random
import re
import time
from typing import Literal
from urllib.parse import quote_plus

import httpx
from loguru import logger

from api.core.config import get_settings
from services.scraper.brand_validator import BrandResult

# ── User-Agents rotativos ─────────────────────────────────────────────────────

_USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

# ── Stopwords para el análisis de títulos de SERP ────────────────────────────

_STOPWORDS_COMERCIALES: frozenset[str] = frozenset({
    "comprar", "precio", "barato", "online", "oferta", "envío", "gratis",
    "descuento", "amazon", "ebay", "tienda", "shop", "store", "venta",
    "compra", "oferta", "ofertas", "zooplus", "aliexpress",
    "producto", "productos", "marca", "marcas", "de", "el", "la", "los",
    "las", "un", "una", "del", "al", "se", "the", "and", "for",
})


# ── Helper privado de extracción ──────────────────────────────────────────────


def _extraer_marca_de_titulos(
    titulos: list[str],
) -> tuple[str | None, Literal["medium", "low"]]:
    """
    Extrae la marca más frecuente en los títulos de búsqueda.

    El algoritmo:
      1. Limpia cada título eliminando stopwords y puntuación.
      2. Tokeniza en unigramas.
      3. Cuenta cuántos títulos *distintos* contienen cada unigrama.
      4. El unigrama con mayor presencia (≥1 aparición) es el candidato a marca.
      5. La confianza es "medium" si aparece en ≥2 títulos distintos, "low" si
         solo aparece en 1.

    Args:
        titulos: textos de los h3 extraídos de la SERP.

    Returns:
        Tupla (brand_name, confidence) donde confidence es "medium" si la marca
        aparece en ≥2 títulos distintos o "low" si aparece en solo 1.
        Si no se puede extraer ninguna marca, devuelve (None, "low").
    """
    # Cuenta en cuántos títulos distintos aparece cada token
    presencia: dict[str, int] = {}

    for titulo in titulos:
        # Tokenizar: separar por espacios y puntuación
        tokens_brutos = re.split(r"[\s\-|/,.:;()\"']+", titulo)
        tokens_del_titulo: set[str] = set()

        for token in tokens_brutos:
            # Eliminar caracteres no alfanuméricos
            limpio = re.sub(r"[^\w]", "", token, flags=re.UNICODE).strip()
            tok_lower = limpio.lower()

            if (
                len(limpio) >= 3
                and not limpio.isdigit()
                and tok_lower not in _STOPWORDS_COMERCIALES
            ):
                tokens_del_titulo.add(tok_lower)

        # Sumar presencia por título (cada token cuenta una sola vez por título)
        for tok in tokens_del_titulo:
            presencia[tok] = presencia.get(tok, 0) + 1

    if not presencia:
        return None, "low"

    # El token con mayor número de títulos en los que aparece es el candidato
    candidato = max(presencia, key=lambda t: presencia[t])
    conteo = presencia[candidato]

    confidence: Literal["medium", "low"] = "medium" if conteo >= 2 else "low"
    return candidato.title(), confidence


# ── Clientes Open Data ────────────────────────────────────────────────────────


class OpenPetFoodFactsClient:
    """
    Cliente HTTP síncrono para la API de Open Pet Food Facts.

    Consulta https://world.openpetfoodfacts.org para obtener el campo
    ``brands`` / ``brand_owner`` de un EAN dado.  Orientado a productos de
    alimentación animal, aunque la base de datos también contiene otros artículos
    de mascotas.

    Reintentos con backoff exponencial: espera 2^attempt segundos entre intentos
    (1 s, 2 s, 4 s para max_retries=3).

    :author: BenjaminDTS
    """

    # Open*Facts recomienda un User-Agent descriptivo para sus APIs públicas.
    _OPENFACTS_UA: str = "Harvist/1.0 (brand-resolver)"
    _BASE_URL: str = "https://world.openpetfoodfacts.org/api/v0/product/{ean}.json"

    def __init__(self, timeout: int = 8, max_retries: int = 3) -> None:
        """
        Inicializa el cliente con timeout y número máximo de reintentos.

        Args:
            timeout: segundos máximos de espera por petición HTTP.
            max_retries: número máximo de intentos ante fallos transitorios.
        """
        self._timeout = timeout
        self._max_retries = max_retries

    def lookup(self, ean: str) -> BrandResult | None:
        """
        Consulta Open Pet Food Facts por EAN y devuelve la marca si la encuentra.

        Args:
            ean: código EAN/UPC del producto (8–14 dígitos).

        Returns:
            BrandResult con confidence="high" y source="open_data_api" si se
            resuelve la marca, o None si el EAN no está en la base de datos o
            todos los reintentos fallan.

        Raises:
            No lanza excepciones al llamador; los errores se registran y se
            devuelve None.
        """
        url = self._BASE_URL.format(ean=ean)
        headers = {"User-Agent": self._OPENFACTS_UA}

        for attempt in range(self._max_retries):
            logger.debug(
                "OpenPetFoodFacts lookup intento",
                extra={"ean": ean, "attempt": attempt + 1, "max": self._max_retries},
            )
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.get(url, headers=headers)

                if response.status_code != 200:
                    logger.debug(
                        "OpenPetFoodFacts respuesta no 200",
                        extra={"ean": ean, "status": response.status_code},
                    )
                    # No tiene sentido reintentar un 404
                    if response.status_code == 404:
                        return None
                    raise httpx.HTTPStatusError(
                        f"HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )

                data = response.json()

                # Open*Facts devuelve status=0 cuando el EAN no existe en su BD
                if data.get("status") != 1:
                    logger.debug(
                        "OpenPetFoodFacts: producto no encontrado",
                        extra={"ean": ean},
                    )
                    return None

                product = data.get("product", {})
                brands_raw: str = product.get("brands", "").strip()
                brand_owner_raw: str = product.get("brand_owner", "").strip()

                # El primer campo no vacío gana para brand_name
                brand_name: str | None = None
                manufacturer: str | None = None

                if brands_raw:
                    brand_name = brands_raw.split(",")[0].strip().title() or None
                    if brand_owner_raw:
                        manufacturer = brand_owner_raw.split(",")[0].strip().title() or None
                elif brand_owner_raw:
                    brand_name = brand_owner_raw.split(",")[0].strip().title() or None

                if not brand_name:
                    logger.debug(
                        "OpenPetFoodFacts: campos brands y brand_owner vacíos",
                        extra={"ean": ean},
                    )
                    return None

                logger.info(
                    "OpenPetFoodFacts: marca resuelta",
                    extra={"ean": ean, "brand": brand_name},
                )
                return BrandResult(
                    ean_code=ean,
                    brand_name=brand_name,
                    manufacturer=manufacturer,
                    source="open_data_api",
                    confidence="high",
                )

            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                wait = 2 ** attempt
                logger.warning(
                    "OpenPetFoodFacts: error de red, reintentando",
                    exc_info=exc,
                    extra={"ean": ean, "attempt": attempt + 1, "wait_s": wait},
                )
                if attempt < self._max_retries - 1:
                    time.sleep(wait)

        logger.warning(
            "OpenPetFoodFacts: todos los reintentos fallaron",
            extra={"ean": ean},
        )
        return None


class OpenFoodFactsClient:
    """
    Cliente HTTP síncrono para la API de Open Food Facts.

    Consulta https://world.openfoodfacts.org para obtener el campo
    ``brands`` / ``brand_owner`` de un EAN dado.  Orientado principalmente a
    alimentos y bebidas para consumo humano.

    Reintentos con backoff exponencial: espera 2^attempt segundos entre intentos
    (1 s, 2 s, 4 s para max_retries=3).

    :author: BenjaminDTS
    """

    _OPENFACTS_UA: str = "Harvist/1.0 (brand-resolver)"
    _BASE_URL: str = "https://world.openfoodfacts.org/api/v0/product/{ean}.json"

    def __init__(self, timeout: int = 8, max_retries: int = 3) -> None:
        """
        Inicializa el cliente con timeout y número máximo de reintentos.

        Args:
            timeout: segundos máximos de espera por petición HTTP.
            max_retries: número máximo de intentos ante fallos transitorios.
        """
        self._timeout = timeout
        self._max_retries = max_retries

    def lookup(self, ean: str) -> BrandResult | None:
        """
        Consulta Open Food Facts por EAN y devuelve la marca si la encuentra.

        Args:
            ean: código EAN/UPC del producto (8–14 dígitos).

        Returns:
            BrandResult con confidence="high" y source="open_data_api" si se
            resuelve la marca, o None si el EAN no está en la base de datos o
            todos los reintentos fallan.

        Raises:
            No lanza excepciones al llamador; los errores se registran y se
            devuelve None.
        """
        url = self._BASE_URL.format(ean=ean)
        headers = {"User-Agent": self._OPENFACTS_UA}

        for attempt in range(self._max_retries):
            logger.debug(
                "OpenFoodFacts lookup intento",
                extra={"ean": ean, "attempt": attempt + 1, "max": self._max_retries},
            )
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.get(url, headers=headers)

                if response.status_code != 200:
                    logger.debug(
                        "OpenFoodFacts respuesta no 200",
                        extra={"ean": ean, "status": response.status_code},
                    )
                    if response.status_code == 404:
                        return None
                    raise httpx.HTTPStatusError(
                        f"HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )

                data = response.json()

                if data.get("status") != 1:
                    logger.debug(
                        "OpenFoodFacts: producto no encontrado",
                        extra={"ean": ean},
                    )
                    return None

                product = data.get("product", {})
                brands_raw: str = product.get("brands", "").strip()
                brand_owner_raw: str = product.get("brand_owner", "").strip()

                brand_name: str | None = None
                manufacturer: str | None = None

                if brands_raw:
                    brand_name = brands_raw.split(",")[0].strip().title() or None
                    if brand_owner_raw:
                        manufacturer = brand_owner_raw.split(",")[0].strip().title() or None
                elif brand_owner_raw:
                    brand_name = brand_owner_raw.split(",")[0].strip().title() or None

                if not brand_name:
                    logger.debug(
                        "OpenFoodFacts: campos brands y brand_owner vacíos",
                        extra={"ean": ean},
                    )
                    return None

                logger.info(
                    "OpenFoodFacts: marca resuelta",
                    extra={"ean": ean, "brand": brand_name},
                )
                return BrandResult(
                    ean_code=ean,
                    brand_name=brand_name,
                    manufacturer=manufacturer,
                    source="open_data_api",
                    confidence="high",
                )

            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                wait = 2 ** attempt
                logger.warning(
                    "OpenFoodFacts: error de red, reintentando",
                    exc_info=exc,
                    extra={"ean": ean, "attempt": attempt + 1, "wait_s": wait},
                )
                if attempt < self._max_retries - 1:
                    time.sleep(wait)

        logger.warning(
            "OpenFoodFacts: todos los reintentos fallaron",
            extra={"ean": ean},
        )
        return None


class UPCItemDbClient:
    """
    Cliente HTTP síncrono para la API de UPC Item DB.

    Consulta https://api.upcitemdb.com para obtener el campo ``brand`` /
    ``manufacturer`` de un UPC/EAN dado.  Base de datos generalista; cubre bien
    electrónica, hogar, mascotas y productos que no están en Open*Facts.

    Reintentos con backoff exponencial: espera 2^attempt segundos entre intentos
    (1 s, 2 s, 4 s para max_retries=3).

    :author: BenjaminDTS
    """

    _BASE_URL: str = "https://api.upcitemdb.com/prod/trial/lookup?upc={ean}"

    def __init__(self, timeout: int = 8, max_retries: int = 3) -> None:
        """
        Inicializa el cliente con timeout y número máximo de reintentos.

        Args:
            timeout: segundos máximos de espera por petición HTTP.
            max_retries: número máximo de intentos ante fallos transitorios.
        """
        self._timeout = timeout
        self._max_retries = max_retries

    def lookup(self, ean: str) -> BrandResult | None:
        """
        Consulta UPC Item DB por EAN y devuelve la marca si la encuentra.

        Args:
            ean: código EAN/UPC del producto (8–14 dígitos).

        Returns:
            BrandResult con confidence="high" y source="open_data_api" si se
            resuelve la marca, o None si el EAN no está en la base de datos o
            todos los reintentos fallan.

        Raises:
            No lanza excepciones al llamador; los errores se registran y se
            devuelve None.
        """
        url = self._BASE_URL.format(ean=ean)

        for attempt in range(self._max_retries):
            # User-Agent rotativo para UPC Item DB
            headers = {"User-Agent": random.choice(_USER_AGENTS)}

            logger.debug(
                "UPCItemDb lookup intento",
                extra={"ean": ean, "attempt": attempt + 1, "max": self._max_retries},
            )
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.get(url, headers=headers)

                if response.status_code != 200:
                    logger.debug(
                        "UPCItemDb respuesta no 200",
                        extra={"ean": ean, "status": response.status_code},
                    )
                    if response.status_code == 404:
                        return None
                    raise httpx.HTTPStatusError(
                        f"HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )

                data = response.json()
                items: list[dict] = data.get("items", [])

                if not items:
                    logger.debug(
                        "UPCItemDb: sin resultados para EAN",
                        extra={"ean": ean},
                    )
                    return None

                first_item = items[0]
                brand_raw: str = first_item.get("brand", "").strip()
                manufacturer_raw: str = first_item.get("manufacturer", "").strip()

                # El primer campo no vacío gana para brand_name
                brand_name: str | None = None
                manufacturer: str | None = None

                if brand_raw:
                    brand_name = brand_raw.title()
                    manufacturer = manufacturer_raw.title() if manufacturer_raw else None
                elif manufacturer_raw:
                    brand_name = manufacturer_raw.title()

                if not brand_name:
                    logger.debug(
                        "UPCItemDb: campos brand y manufacturer vacíos",
                        extra={"ean": ean},
                    )
                    return None

                logger.info(
                    "UPCItemDb: marca resuelta",
                    extra={"ean": ean, "brand": brand_name},
                )
                return BrandResult(
                    ean_code=ean,
                    brand_name=brand_name,
                    manufacturer=manufacturer,
                    source="open_data_api",
                    confidence="high",
                )

            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                wait = 2 ** attempt
                logger.warning(
                    "UPCItemDb: error de red, reintentando",
                    exc_info=exc,
                    extra={"ean": ean, "attempt": attempt + 1, "wait_s": wait},
                )
                if attempt < self._max_retries - 1:
                    time.sleep(wait)

        logger.warning(
            "UPCItemDb: todos los reintentos fallaron",
            extra={"ean": ean},
        )
        return None


# ── Clientes de búsqueda web ──────────────────────────────────────────────────


class GoogleDorkClient:
    """
    Cliente HTTP síncrono que extrae la marca de un EAN buscando en Google.

    Realiza una búsqueda exacta ``"EAN"`` en Google (dork), descarga el HTML
    de la SERP y extrae los títulos ``<h3>`` para inferir la marca por
    frecuencia de unigramas.

    Introduce un retraso aleatorio de 2–5 s antes de cada petición para
    reducir la probabilidad de bloqueo anti-bot.  Soporta proxy rotativo
    configurable mediante ``ROTATING_PROXY_URL`` en Settings.

    Reintentos con backoff exponencial: espera 2^attempt segundos entre intentos.

    :author: BenjaminDTS
    """

    _SEARCH_URL: str = "https://www.google.com/search?q=%22{ean}%22&hl=es"
    _H3_PATTERN: re.Pattern[str] = re.compile(r'<h3[^>]*>([^<]{3,100})</h3>')

    def __init__(self, timeout: int = 10, max_retries: int = 3) -> None:
        """
        Inicializa el cliente con timeout y número máximo de reintentos.

        Args:
            timeout: segundos máximos de espera por petición HTTP.
            max_retries: número máximo de intentos ante fallos transitorios.
        """
        self._timeout = timeout
        self._max_retries = max_retries

    def lookup(self, ean: str) -> BrandResult | None:
        """
        Busca el EAN en Google y extrae la marca de los títulos de resultados.

        Args:
            ean: código EAN/UPC del producto (8–14 dígitos).

        Returns:
            BrandResult con source="google_dorking" si se extrae una marca,
            o None si no hay resultados aprovechables o todos los reintentos fallan.

        Raises:
            No lanza excepciones al llamador; los errores se registran y se
            devuelve None.
        """
        settings = get_settings()
        url = self._SEARCH_URL.format(ean=quote_plus(ean))

        for attempt in range(self._max_retries):
            # Retraso anti-bot ANTES de cada petición (incluido el primer intento)
            delay = random.uniform(2.0, 5.0)
            logger.debug(
                "GoogleDork: esperando antes de petición",
                extra={"ean": ean, "delay_s": round(delay, 2), "attempt": attempt + 1},
            )
            time.sleep(delay)

            ua = random.choice(_USER_AGENTS)
            headers = {
                "User-Agent": ua,
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
                "Referer": "https://www.google.com/",
            }

            try:
                # Configurar proxy si está disponible
                proxy_url = settings.rotating_proxy_url or None
                client_kwargs: dict = {"timeout": self._timeout}
                if proxy_url:
                    client_kwargs["proxy"] = proxy_url

                logger.debug(
                    "GoogleDork lookup intento",
                    extra={
                        "ean": ean,
                        "attempt": attempt + 1,
                        "max": self._max_retries,
                        "proxy": bool(proxy_url),
                    },
                )

                with httpx.Client(**client_kwargs) as client:
                    response = client.get(url, headers=headers, follow_redirects=True)

                if response.status_code != 200:
                    logger.debug(
                        "GoogleDork: respuesta no 200",
                        extra={"ean": ean, "status": response.status_code},
                    )
                    raise httpx.HTTPStatusError(
                        f"HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )

                titulos = self._H3_PATTERN.findall(response.text)

                if not titulos:
                    logger.debug(
                        "GoogleDork: sin títulos h3 en SERP",
                        extra={"ean": ean},
                    )
                    return None

                brand_name, confidence = _extraer_marca_de_titulos(titulos)

                if not brand_name:
                    logger.debug(
                        "GoogleDork: no se pudo extraer marca de títulos",
                        extra={"ean": ean, "titulos_count": len(titulos)},
                    )
                    return None

                logger.info(
                    "GoogleDork: marca extraída",
                    extra={"ean": ean, "brand": brand_name, "confidence": confidence},
                )
                return BrandResult(
                    ean_code=ean,
                    brand_name=brand_name,
                    source="google_dorking",
                    confidence=confidence,
                )

            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                wait = 2 ** attempt
                logger.warning(
                    "GoogleDork: error de red, reintentando",
                    exc_info=exc,
                    extra={"ean": ean, "attempt": attempt + 1, "wait_s": wait},
                )
                if attempt < self._max_retries - 1:
                    time.sleep(wait)

        logger.warning(
            "GoogleDork: todos los reintentos fallaron",
            extra={"ean": ean},
        )
        return None


class BingSearchClient:
    """
    Cliente HTTP síncrono que extrae la marca de un EAN buscando en Bing.

    Realiza una búsqueda exacta ``"EAN"`` en Bing, descarga el HTML de la SERP
    y extrae los títulos ``<h3>`` para inferir la marca por frecuencia de
    unigramas.

    Introduce un retraso aleatorio de 2–5 s antes de cada petición para
    reducir la probabilidad de bloqueo anti-bot.  Soporta proxy rotativo
    configurable mediante ``ROTATING_PROXY_URL`` en Settings.

    A diferencia de ``EanBrandResolver`` (que usa Selenium), este cliente trabaja
    exclusivamente con HTTP plano, por lo que es más rápido pero puede obtener
    menos resultados si Bing devuelve JavaScript dinámico.

    Reintentos con backoff exponencial: espera 2^attempt segundos entre intentos.

    :author: BenjaminDTS
    """

    _SEARCH_URL: str = "https://www.bing.com/search?q=%22{ean}%22&setlang=es"
    _H3_PATTERN: re.Pattern[str] = re.compile(r'<h3[^>]*>([^<]{3,100})</h3>')

    def __init__(self, timeout: int = 10, max_retries: int = 3) -> None:
        """
        Inicializa el cliente con timeout y número máximo de reintentos.

        Args:
            timeout: segundos máximos de espera por petición HTTP.
            max_retries: número máximo de intentos ante fallos transitorios.
        """
        self._timeout = timeout
        self._max_retries = max_retries

    def lookup(self, ean: str) -> BrandResult | None:
        """
        Busca el EAN en Bing y extrae la marca de los títulos de resultados.

        Args:
            ean: código EAN/UPC del producto (8–14 dígitos).

        Returns:
            BrandResult con source="bing_search" si se extrae una marca,
            o None si no hay resultados aprovechables o todos los reintentos fallan.

        Raises:
            No lanza excepciones al llamador; los errores se registran y se
            devuelve None.
        """
        settings = get_settings()
        url = self._SEARCH_URL.format(ean=quote_plus(ean))

        for attempt in range(self._max_retries):
            # Retraso anti-bot ANTES de cada petición
            delay = random.uniform(2.0, 5.0)
            logger.debug(
                "BingSearch: esperando antes de petición",
                extra={"ean": ean, "delay_s": round(delay, 2), "attempt": attempt + 1},
            )
            time.sleep(delay)

            ua = random.choice(_USER_AGENTS)
            headers = {
                "User-Agent": ua,
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
                "Referer": "https://www.bing.com/",
            }

            try:
                proxy_url = settings.rotating_proxy_url or None
                client_kwargs: dict = {"timeout": self._timeout}
                if proxy_url:
                    client_kwargs["proxy"] = proxy_url

                logger.debug(
                    "BingSearch lookup intento",
                    extra={
                        "ean": ean,
                        "attempt": attempt + 1,
                        "max": self._max_retries,
                        "proxy": bool(proxy_url),
                    },
                )

                with httpx.Client(**client_kwargs) as client:
                    response = client.get(url, headers=headers, follow_redirects=True)

                if response.status_code != 200:
                    logger.debug(
                        "BingSearch: respuesta no 200",
                        extra={"ean": ean, "status": response.status_code},
                    )
                    raise httpx.HTTPStatusError(
                        f"HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )

                titulos = self._H3_PATTERN.findall(response.text)

                if not titulos:
                    logger.debug(
                        "BingSearch: sin títulos h3 en SERP",
                        extra={"ean": ean},
                    )
                    return None

                brand_name, confidence = _extraer_marca_de_titulos(titulos)

                if not brand_name:
                    logger.debug(
                        "BingSearch: no se pudo extraer marca de títulos",
                        extra={"ean": ean, "titulos_count": len(titulos)},
                    )
                    return None

                logger.info(
                    "BingSearch: marca extraída",
                    extra={"ean": ean, "brand": brand_name, "confidence": confidence},
                )
                return BrandResult(
                    ean_code=ean,
                    brand_name=brand_name,
                    source="bing_search",
                    confidence=confidence,
                )

            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                wait = 2 ** attempt
                logger.warning(
                    "BingSearch: error de red, reintentando",
                    exc_info=exc,
                    extra={"ean": ean, "attempt": attempt + 1, "wait_s": wait},
                )
                if attempt < self._max_retries - 1:
                    time.sleep(wait)

        logger.warning(
            "BingSearch: todos los reintentos fallaron",
            extra={"ean": ean},
        )
        return None
