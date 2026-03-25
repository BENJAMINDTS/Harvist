"""
Cliente HTTP para extracción de marca de producto desde Amazon.es.

Realiza dos peticiones HTTP síncronas por EAN:
  1. GET /s?k={EAN}  — obtiene el ASIN del primer resultado no patrocinado.
  2. GET /dp/{ASIN}  — extrae la marca desde la ficha de producto.

Si no hay ASIN disponible, intenta extraer la marca directamente del listado
(confidence="medium"). Usa User-Agents rotatorios y delay anti-bot.

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

import random
import re
import time

import httpx
from loguru import logger

from api.core.config import get_settings
from services.scraper.brand_validator import BrandResult

# ── User-Agents rotativos ─────────────────────────────────────────────────────

_USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# ── Prefijos a eliminar durante la limpieza de marca ─────────────────────────

_BRAND_PREFIXES: tuple[str, ...] = (
    "visita la tienda de ",
    "visita la tienda ",
    "marca: ",
    "marca ",
    "brand: ",
    "by ",
    "visit the ",
)

# ── Patrones de extracción de HTML ────────────────────────────────────────────

# Primer ASIN no patrocinado en el listado de búsqueda de Amazon
_ASIN_PATTERN: re.Pattern[str] = re.compile(r'data-asin="([A-Z0-9]{10})"')
_SPONSORED_PATTERN: re.Pattern[str] = re.compile(
    r'data-component-type="sp-sponsored-result"'
)

# Selector para extraer texto de etiquetas HTML simples
_INNER_TEXT_PATTERN: re.Pattern[str] = re.compile(r'<[^>]+>')

# Selectores para extraer la marca de la ficha de producto /dp/
_BYLINE_PATTERN: re.Pattern[str] = re.compile(
    r'<a\s[^>]*id="bylineInfo"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_PO_BRAND_ROW_PATTERN: re.Pattern[str] = re.compile(
    r'<tr[^>]*class="[^"]*po-brand[^"]*"[^>]*>(.*?)</tr>',
    re.IGNORECASE | re.DOTALL,
)
_PO_BRAND_CELL_PATTERN: re.Pattern[str] = re.compile(
    r'<(?:td|span)[^>]*class="[^"]*(?:po-break-word|a-size-base\s+po-break-word)[^"]*"[^>]*>(.*?)</(?:td|span)>',
    re.IGNORECASE | re.DOTALL,
)
_BRAND_SPAN_PATTERN: re.Pattern[str] = re.compile(
    r'<span\s[^>]*id="brand"[^>]*>(.*?)</span>',
    re.IGNORECASE | re.DOTALL,
)

# Cadenas que indican que Amazon no encontró el EAN buscado.
# En ese caso muestra productos patrocinados/sugeridos que no corresponden
# al EAN — devolver cualquier marca de esa página sería un falso positivo.
_NO_RESULTS_MARKERS: tuple[str, ...] = (
    "no hay resultados para tu consulta",
    "no results for",
    "did not match any products",
    "no coincide con ningún producto",
)

# Selector para la marca en el listado (fallback STEP C)
_LISTING_BRAND_PATTERN: re.Pattern[str] = re.compile(
    r'<span[^>]*class="[^"]*a-size-base-plus\s+a-color-base[^"]*"[^>]*>(.*?)</span>',
    re.IGNORECASE | re.DOTALL,
)


def _strip_tags(html: str) -> str:
    """
    Elimina todas las etiquetas HTML de una cadena y devuelve solo el texto.

    Args:
        html: fragmento HTML del que se quieren eliminar las etiquetas.

    Returns:
        Texto plano sin etiquetas HTML, con espacios colapsados.
    """
    return _INNER_TEXT_PATTERN.sub("", html).strip()


def _clean_brand(raw: str) -> str:
    """
    Limpia y normaliza un candidato a nombre de marca extraído del HTML.

    Elimina prefijos comerciales conocidos, aplica strip y title-case.

    Args:
        raw: texto sin etiquetas HTML extraído del DOM de Amazon.

    Returns:
        Nombre de marca normalizado con .strip().title() aplicado.
    """
    cleaned = raw.strip()
    lower = cleaned.lower()
    for prefix in _BRAND_PREFIXES:
        if lower.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    return cleaned.strip().title()


def _is_valid_brand(brand_name: str) -> bool:
    """
    Comprueba que el candidato a marca tiene al menos 2 caracteres y no es numérico.

    Args:
        brand_name: nombre de marca ya limpio.

    Returns:
        True si el nombre es usable como marca, False en caso contrario.
    """
    return len(brand_name) >= 2 and not brand_name.isnumeric()


def _extract_asin_from_listing(html: str) -> str | None:
    """
    Extrae el primer ASIN no patrocinado del HTML del listado de búsqueda.

    Divide el HTML en bloques de producto, descarta los bloques que contengan
    el atributo ``data-component-type="sp-sponsored-result"`` y devuelve el
    primer ASIN válido encontrado en el resto.

    Args:
        html: HTML completo de la página /s?k={EAN} de Amazon.

    Returns:
        ASIN de 10 caracteres alfanuméricos o None si no se encuentra ninguno.
    """
    # Dividir por bloques de producto usando data-asin como ancla
    # Cada bloque empieza con un atributo data-asin y contiene los atributos
    # del div de resultado hasta el siguiente bloque
    blocks = re.split(r'(?=data-asin="[A-Z0-9]{10}")', html)

    for block in blocks:
        asin_match = _ASIN_PATTERN.search(block)
        if not asin_match:
            continue

        asin = asin_match.group(1)

        # Ignorar ASINs que sean cadenas vacías o de solo ceros
        if not asin or asin == "0" * 10:
            continue

        # Ignorar bloques patrocinados
        if _SPONSORED_PATTERN.search(block):
            continue

        return asin

    return None


def _extract_brand_from_product_page(html: str) -> str | None:
    """
    Extrae la marca del HTML de una ficha de producto de Amazon (/dp/{ASIN}).

    Prueba tres selectores en orden de prioridad:
      b1) Enlace ``<a id="bylineInfo">``.
      b2) Celda de la fila ``<tr class="po-brand">`` de la tabla de atributos.
      b3) Span ``<span id="brand">``.

    Args:
        html: HTML completo de la página de producto de Amazon.

    Returns:
        Nombre de marca limpio con .strip().title() aplicado, o None si
        ningún selector produce un resultado válido.
    """
    # b1) bylineInfo
    byline_match = _BYLINE_PATTERN.search(html)
    if byline_match:
        candidate = _clean_brand(_strip_tags(byline_match.group(1)))
        if _is_valid_brand(candidate):
            return candidate

    # b2) po-brand table row
    row_match = _PO_BRAND_ROW_PATTERN.search(html)
    if row_match:
        cell_match = _PO_BRAND_CELL_PATTERN.search(row_match.group(1))
        if cell_match:
            candidate = _clean_brand(_strip_tags(cell_match.group(1)))
            if _is_valid_brand(candidate):
                return candidate

    # b3) span id="brand"
    span_match = _BRAND_SPAN_PATTERN.search(html)
    if span_match:
        candidate = _clean_brand(_strip_tags(span_match.group(1)))
        if _is_valid_brand(candidate):
            return candidate

    return None


def _extract_brand_from_listing(html: str) -> str | None:
    """
    Extrae la marca del primer resultado no patrocinado del listado de Amazon.

    Busca el span ``<span class="a-size-base-plus a-color-base">`` del primer
    ítem no patrocinado como alternativa cuando no hay ASIN disponible o
    la ficha de producto no contiene datos de marca.

    Args:
        html: HTML completo de la página /s?k={EAN} de Amazon.

    Returns:
        Nombre de marca limpio con .strip().title() aplicado, o None si
        el selector no produce un resultado válido.
    """
    # Dividir en bloques de producto y buscar en el primero no patrocinado
    blocks = re.split(r'(?=data-asin="[A-Z0-9]{10}")', html)

    for block in blocks:
        asin_match = _ASIN_PATTERN.search(block)
        if not asin_match:
            continue

        asin = asin_match.group(1)
        if not asin or asin == "0" * 10:
            continue

        if _SPONSORED_PATTERN.search(block):
            continue

        brand_match = _LISTING_BRAND_PATTERN.search(block)
        if brand_match:
            candidate = _clean_brand(_strip_tags(brand_match.group(1)))
            if _is_valid_brand(candidate):
                return candidate

        # Solo intentar el primer bloque no patrocinado
        break

    return None


class AmazonBrandClient:
    """
    Cliente HTTP síncrono para la extracción de marca de producto desde Amazon.es.

    Realiza hasta dos peticiones HTTP por EAN:
      1. GET https://www.amazon.es/s?k={EAN} — listado de búsqueda para obtener
         el ASIN del primer resultado no patrocinado.
      2. GET https://www.amazon.es/dp/{ASIN} — ficha de producto para extraer
         la marca desde selectores estructurados del DOM.

    Si la ficha de producto no está disponible o no contiene datos de marca,
    intenta extraer la marca directamente del bloque de listado con
    confidence="medium". En caso de éxito desde la ficha de producto devuelve
    confidence="high".

    Introduce un retraso aleatorio de 2–5 s antes de cada petición para
    reducir la probabilidad de bloqueo anti-bot. Soporta proxy rotativo
    configurable mediante ``ROTATING_PROXY_URL`` en Settings. Usa reintentos
    con backoff exponencial (2^attempt segundos) ante errores de red.

    :author: BenjaminDTS
    """

    _LISTING_URL: str = "https://www.amazon.es/s?k={ean}"
    _PRODUCT_URL: str = "https://www.amazon.es/dp/{asin}"

    def __init__(self, timeout: int = 10, max_retries: int = 3) -> None:
        """
        Inicializa el cliente con timeout y número máximo de reintentos.

        Args:
            timeout: segundos máximos de espera por petición HTTP.
            max_retries: número máximo de intentos ante fallos transitorios.
        """
        settings = get_settings()
        self._timeout = timeout
        self._max_retries = max_retries
        self._proxy = settings.rotating_proxy_url or None

    def _build_client_kwargs(self) -> dict:
        """
        Construye los kwargs para httpx.Client según la configuración de proxy.

        Returns:
            Diccionario listo para pasar a httpx.Client(**kwargs).
        """
        kwargs: dict = {
            "timeout": self._timeout,
            "follow_redirects": True,
        }
        if self._proxy:
            kwargs["proxies"] = self._proxy
        return kwargs

    def _get_listing_html(self, ean: str) -> str | None:
        """
        Descarga el HTML del listado de búsqueda de Amazon para el EAN dado.

        Introduce un retraso anti-bot de 2–5 s antes de cada intento y aplica
        reintentos con backoff exponencial ante errores de red.

        Args:
            ean: código EAN/UPC del producto.

        Returns:
            HTML de la página de listado como string, o None si todos los
            reintentos fallaron o se recibió un 404.
        """
        url = self._LISTING_URL.format(ean=ean)

        for attempt in range(self._max_retries):
            delay = random.uniform(2.0, 5.0)
            logger.debug(
                "AmazonBrandClient: esperando antes de petición de listado",
                extra={"ean": ean, "delay_s": round(delay, 2), "attempt": attempt + 1},
            )
            time.sleep(delay)

            ua = random.choice(_USER_AGENTS)
            headers = {
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
                "Referer": "https://www.amazon.es/",
            }

            try:
                logger.debug(
                    "AmazonBrandClient: GET listado intento",
                    extra={
                        "ean": ean,
                        "attempt": attempt + 1,
                        "max": self._max_retries,
                        "proxy": bool(self._proxy),
                    },
                )

                with httpx.Client(**self._build_client_kwargs()) as client:
                    resp = client.get(url, headers=headers)
                    resp.raise_for_status()

                return resp.text

            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    logger.debug(
                        "AmazonBrandClient: 404 en listado, sin reintentos",
                        extra={"ean": ean},
                    )
                    return None
                logger.debug(
                    "AmazonBrandClient: HTTP error en listado",
                    extra={"ean": ean, "attempt": attempt + 1, "status": exc.response.status_code},
                )
                if attempt < self._max_retries - 1:
                    time.sleep(2 ** attempt)

            except Exception as exc:
                logger.debug(
                    "AmazonBrandClient: error de red en listado",
                    extra={"ean": ean, "attempt": attempt + 1},
                )
                if attempt < self._max_retries - 1:
                    time.sleep(2 ** attempt)

        logger.warning(
            "AmazonBrandClient: todos los reintentos de listado fallaron",
            extra={"ean": ean},
        )
        return None

    def _get_product_html(self, asin: str, ean: str) -> str | None:
        """
        Descarga el HTML de la ficha de producto de Amazon para el ASIN dado.

        Introduce un retraso anti-bot de 2–5 s antes de cada intento y aplica
        reintentos con backoff exponencial ante errores de red.

        Args:
            asin: identificador ASIN de 10 caracteres del producto en Amazon.
            ean: código EAN original del producto (solo para logging).

        Returns:
            HTML de la ficha de producto como string, o None si todos los
            reintentos fallaron o se recibió un 404.
        """
        url = self._PRODUCT_URL.format(asin=asin)

        for attempt in range(self._max_retries):
            delay = random.uniform(2.0, 5.0)
            logger.debug(
                "AmazonBrandClient: esperando antes de petición de producto",
                extra={"ean": ean, "asin": asin, "delay_s": round(delay, 2), "attempt": attempt + 1},
            )
            time.sleep(delay)

            ua = random.choice(_USER_AGENTS)
            headers = {
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
                "Referer": "https://www.amazon.es/",
            }

            try:
                logger.debug(
                    "AmazonBrandClient: GET producto intento",
                    extra={
                        "ean": ean,
                        "asin": asin,
                        "attempt": attempt + 1,
                        "max": self._max_retries,
                        "proxy": bool(self._proxy),
                    },
                )

                with httpx.Client(**self._build_client_kwargs()) as client:
                    resp = client.get(url, headers=headers)
                    resp.raise_for_status()

                return resp.text

            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    logger.debug(
                        "AmazonBrandClient: 404 en ficha de producto, sin reintentos",
                        extra={"ean": ean, "asin": asin},
                    )
                    return None
                logger.debug(
                    "AmazonBrandClient: HTTP error en ficha de producto",
                    extra={"ean": ean, "asin": asin, "attempt": attempt + 1, "status": exc.response.status_code},
                )
                if attempt < self._max_retries - 1:
                    time.sleep(2 ** attempt)

            except Exception as exc:
                logger.debug(
                    "AmazonBrandClient: error de red en ficha de producto",
                    extra={"ean": ean, "asin": asin, "attempt": attempt + 1},
                )
                if attempt < self._max_retries - 1:
                    time.sleep(2 ** attempt)

        logger.warning(
            "AmazonBrandClient: todos los reintentos de ficha de producto fallaron",
            extra={"ean": ean, "asin": asin},
        )
        return None

    def lookup(self, ean: str) -> BrandResult | None:
        """
        Extrae la marca del producto asociado al EAN desde Amazon.es.

        Flujo de extracción:
          STEP A — Descarga el listado de búsqueda /s?k={EAN} y extrae el
                   primer ASIN no patrocinado.
          STEP B — Si hay ASIN, descarga la ficha /dp/{ASIN} y extrae la
                   marca con confidence="high".
          STEP C — Si no hay ASIN o la ficha no contiene marca, intenta
                   extraer la marca del primer resultado del listado con
                   confidence="medium".

        Args:
            ean: código EAN/UPC del producto (8–14 dígitos).

        Returns:
            BrandResult con source="amazon" y confidence="high" (ficha de
            producto) o "medium" (listado), o None si todos los pasos fallan.

        Raises:
            No lanza excepciones al llamador; los errores se registran con
            loguru y se devuelve None.
        """
        # ── STEP A: obtener listado y extraer ASIN ────────────────────────────
        listing_html = self._get_listing_html(ean)

        if listing_html is None:
            logger.warning(
                "AmazonBrandClient: no se pudo obtener el listado",
                extra={"ean": ean},
            )
            return None

        if any(m in listing_html.lower() for m in _NO_RESULTS_MARKERS):
            logger.debug(
                "AmazonBrandClient: página sin resultados — EAN no encontrado en Amazon",
                extra={"ean": ean},
            )
            return None

        asin = _extract_asin_from_listing(listing_html)

        if asin:
            logger.debug(
                "AmazonBrandClient: ASIN extraído del listado",
                extra={"ean": ean, "asin": asin},
            )

            # ── STEP B: ficha de producto ─────────────────────────────────────
            product_html = self._get_product_html(asin, ean)

            if product_html is not None:
                brand_name = _extract_brand_from_product_page(product_html)

                if brand_name:
                    logger.info(
                        "AmazonBrandClient: marca extraída de ficha de producto",
                        extra={"ean": ean, "asin": asin, "brand": brand_name},
                    )
                    return BrandResult(
                        ean_code=ean,
                        brand_name=brand_name,
                        source="amazon",
                        confidence="high",
                    )

                logger.debug(
                    "AmazonBrandClient: ficha de producto sin datos de marca, intentando fallback",
                    extra={"ean": ean, "asin": asin},
                )
            else:
                logger.debug(
                    "AmazonBrandClient: no se pudo obtener la ficha de producto, intentando fallback",
                    extra={"ean": ean, "asin": asin},
                )
        else:
            logger.warning(
                "AmazonBrandClient: no se encontró ASIN no patrocinado en el listado",
                extra={"ean": ean},
            )

        # ── STEP C: fallback desde el listado ─────────────────────────────────
        brand_name = _extract_brand_from_listing(listing_html)

        if brand_name:
            logger.info(
                "AmazonBrandClient: marca extraída del listado (fallback)",
                extra={"ean": ean, "brand": brand_name, "confidence": "medium"},
            )
            return BrandResult(
                ean_code=ean,
                brand_name=brand_name,
                source="amazon",
                confidence="medium",
            )

        logger.warning(
            "AmazonBrandClient: todos los pasos de extracción fallaron",
            extra={"ean": ean},
        )
        return None
