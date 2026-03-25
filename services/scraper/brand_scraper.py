"""
Resolución EAN → marca de producto mediante cascada de 8 niveles.

Orden estricto de la cascada (se detiene en cuanto obtiene un resultado):

  Nivel 1 → validate_ean_checksum()     → descarta EANs inválidos (ean_invalido)
  Nivel 2 → GS1PrefixCache.resolve()    → prefijos conocidos en memoria (cache_gs1)
  Nivel 3 → AmazonBrandClient.lookup()  → ficha de producto en Amazon.es (amazon)
  Nivel 4 → OpenPetFoodFacts            → bases de datos Open*Facts (open_data_api)
  Nivel 5 → OpenFoodFacts               → bases de datos Open*Facts (open_data_api)
  Nivel 6 → UPCItemDb                   → base de datos UPC genérica (open_data_api)
  Nivel 7 → GoogleDorkClient.lookup()   → búsqueda web en Google (google_dorking)
  Nivel 8 → BingSearchClient.lookup()   → búsqueda web en Bing (bing_search)
  Nivel 9 → Resultado no encontrado     → (not_found)

Aprendizaje automático de prefijos:
  Cuando los niveles 4-8 resuelven un EAN con confianza "high" o "medium", el
  resolver extrae el prefijo (primeros 7 dígitos) y lo registra en GS1PrefixCache
  para que futuros EANs del mismo fabricante se resuelvan en el Nivel 2 sin
  peticiones HTTP adicionales.
  Para el Nivel 3 (Amazon), solo se aprende el prefijo cuando la confianza es
  "high" (ficha de producto completa); los resultados con confianza "medium" no
  se registran para evitar contaminación de la caché.

Sin Selenium:
  Esta versión elimina por completo la dependencia de Selenium/WebDriver.
  Todos los accesos a la red se realizan mediante httpx (clientes síncronos),
  lo que simplifica la gestión de recursos y el uso en entornos Celery.

:author: BenjaminDTS
:version: 7.0.0
"""

from __future__ import annotations

import re

from loguru import logger

from api.core.config import get_settings
from services.scraper.brand_cache import GS1PrefixCache
from services.scraper.brand_validator import BrandResult, validate_ean_checksum
from services.utils.amazon_brand_client import AmazonBrandClient
from services.utils.ean_http_clients import (
    BingSearchClient,
    GoogleDorkClient,
    OpenFoodFactsClient,
    OpenPetFoodFactsClient,
    UPCItemDbClient,
)

# ── Constantes ────────────────────────────────────────────────────────────────

# Longitud del prefijo GS1 que se registra al aprender desde APIs o búsqueda web.
# 7 dígitos equilibran especificidad (evita solapamiento con otras empresas) y
# cobertura (cubre todos los EANs del mismo fabricante).
_PREFIJO_APRENDIZAJE_LEN: int = 7

# Patrón para EANs numéricos de 8 a 14 dígitos (sin espacios ni guiones).
_EAN_NUMERICO: re.Pattern[str] = re.compile(r"^\d{8,14}$")


# ── Resolvedor ────────────────────────────────────────────────────────────────


class EanBrandResolver:
    """
    Orquestador de la cascada de 8 niveles para resolver EAN → marca.

    Instanciar una vez por pipeline/job. La caché GS1 se comparte entre
    todas las resoluciones de la misma instancia, por lo que el aprendizaje
    automático de prefijos se acumula durante el procesamiento del lote:
    si el Nivel 3 resuelve un EAN del fabricante "Nestlé", el siguiente EAN
    con el mismo prefijo se resolverá en el Nivel 2 (sin peticiones HTTP).

    :author: BenjaminDTS
    """

    def __init__(
        self,
        gs1_cache: GS1PrefixCache | None = None,
    ) -> None:
        """
        Inicializa el resolver con todos sus componentes.

        Los timeouts y reintentos se leen de Settings para evitar valores
        hardcodeados (``amazon_http_timeout`` y ``brand_http_timeout``).
        Pasar ``gs1_cache`` explícitamente es útil en tests para inyectar
        una caché pre-poblada o vacía.

        Args:
            gs1_cache: instancia de GS1PrefixCache. Si None, se crea una nueva
                con la semilla por defecto cargada desde
                ``data/gs1_prefixes_seed.json``.
        """
        settings = get_settings()
        timeout = settings.brand_http_timeout

        self._cache = gs1_cache or GS1PrefixCache()
        self._amazon = AmazonBrandClient(timeout=timeout)
        self._openpetfood = OpenPetFoodFactsClient(timeout=timeout)
        self._openfood = OpenFoodFactsClient(timeout=timeout)
        self._upcitemdb = UPCItemDbClient(timeout=timeout)
        self._google = GoogleDorkClient(timeout=timeout)
        self._bing = BingSearchClient(timeout=timeout)

    def resolver(self, codigo: str, ean: str) -> BrandResult:
        """
        Ejecuta la cascada de 8 niveles para resolver un EAN a su marca.

        La cascada se detiene en cuanto un nivel devuelve un resultado.
        Si ningún nivel tiene éxito, devuelve ``source="not_found"``.

        Args:
            codigo: código interno del producto (solo para trazabilidad en logs).
            ean: código de barras del producto. Puede no ser numérico; el
                Nivel 1 lo descartará en ese caso con ``source="ean_invalido"``.

        Returns:
            BrandResult con el resultado de la resolución. Nunca lanza
            excepción: los errores de red son absorbidos por cada cliente y
            registrados a nivel WARNING.
        """
        ean_limpio = ean.strip()

        logger.debug(
            "Iniciando resolución EAN",
            extra={"codigo": codigo, "ean": ean_limpio},
        )

        # ── Nivel 1: validación del EAN ───────────────────────────────────────
        # Rechazar EANs no numéricos (ej. "LECHUGA ICEBERG") antes de cualquier
        # llamada HTTP. Un EAN no numérico no puede aparecer en ninguna base de
        # datos ni en buscadores de forma significativa para la resolución de marca.
        if not _EAN_NUMERICO.match(ean_limpio):
            logger.debug(
                "EAN no numérico — descartado sin peticiones HTTP",
                extra={"codigo": codigo, "ean": ean_limpio},
            )
            return BrandResult(
                ean_code=ean_limpio,
                source="ean_invalido",
                confidence="low",
            )

        # Validar dígito de control GS1 Módulo 10 para detectar EANs corruptos
        if not validate_ean_checksum(ean_limpio):
            logger.debug(
                "EAN inválido (falla Módulo 10)",
                extra={"codigo": codigo, "ean": ean_limpio},
            )
            return BrandResult(
                ean_code=ean_limpio,
                source="ean_invalido",
                confidence="low",
            )

        # ── Nivel 2: caché GS1 ────────────────────────────────────────────────
        resultado = self._cache.resolve(ean_limpio)
        if resultado:
            logger.info(
                "EAN resuelto — Nivel 2 (caché GS1)",
                extra={"codigo": codigo, "ean": ean_limpio, "brand": resultado.brand_name, "confidence": resultado.confidence},
            )
            return resultado

        logger.debug("Nivel 2 sin resultado, escalando a Nivel 3 (Amazon)", extra={"ean": ean_limpio})

        # ── Nivel 3: Amazon.es ────────────────────────────────────────────────
        resultado = self._amazon.lookup(ean_limpio)
        if resultado:
            logger.info(
                "EAN resuelto — Nivel 3 (Amazon)",
                extra={"codigo": codigo, "ean": ean_limpio, "brand": resultado.brand_name, "confidence": resultado.confidence},
            )
            # Only learn prefix from high-confidence Amazon results (product page)
            if resultado.confidence == "high":
                self._aprender_prefijo(ean_limpio, resultado)
            return resultado

        logger.debug("Nivel 3 sin resultado, escalando a Nivel 4 (Open Data)", extra={"ean": ean_limpio})

        # ── Nivel 4-5-6: APIs Open Data ───────────────────────────────────────
        # Se consultan en orden de especificidad: primero la base de datos de
        # alimentos para mascotas, luego la general de alimentos, y por último
        # UPC Item DB para productos genéricos.
        for cliente in (self._openpetfood, self._openfood, self._upcitemdb):
            resultado = cliente.lookup(ean_limpio)
            if resultado:
                logger.info(
                    "EAN resuelto — Nivel 4/5/6 (Open Data API)",
                    extra={"codigo": codigo, "ean": ean_limpio, "brand": resultado.brand_name, "client": type(cliente).__name__, "confidence": resultado.confidence},
                )
                self._aprender_prefijo(ean_limpio, resultado)
                return resultado

        logger.warning("Niveles 4-6 sin resultado, escalando a Nivel 7 (Google Dorking)", extra={"ean": ean_limpio})

        # ── Nivel 7: búsqueda Google ──────────────────────────────────────────
        resultado = self._google.lookup(ean_limpio)
        if resultado:
            logger.info(
                "EAN resuelto — Nivel 7 (Google Dorking)",
                extra={"codigo": codigo, "ean": ean_limpio, "brand": resultado.brand_name, "confidence": resultado.confidence},
            )
            self._aprender_prefijo(ean_limpio, resultado)
            return resultado

        logger.warning("Nivel 7 sin resultado, escalando a Nivel 8 (Bing Search)", extra={"ean": ean_limpio})

        # ── Nivel 8: búsqueda Bing ────────────────────────────────────────────
        resultado = self._bing.lookup(ean_limpio)
        if resultado:
            logger.info(
                "EAN resuelto — Nivel 8 (Bing Search)",
                extra={"codigo": codigo, "ean": ean_limpio, "brand": resultado.brand_name, "confidence": resultado.confidence},
            )
            self._aprender_prefijo(ean_limpio, resultado)
            return resultado

        # ── Nivel 9: not_found ────────────────────────────────────────────────
        # El EAN existe y su dígito de control es válido, pero no pudo resolverse
        # en ninguna fuente disponible. Se marca como "fantasma".
        logger.info(
            "EAN marcado como fantasma — Nivel 9 (not_found)",
            extra={"codigo": codigo, "ean": ean_limpio},
        )
        return BrandResult(
            ean_code=ean_limpio,
            source="not_found",
            confidence="low",
        )

    # ── Métodos privados ──────────────────────────────────────────────────────

    def _aprender_prefijo(self, ean: str, resultado: BrandResult) -> None:
        """
        Registra en la caché GS1 el prefijo del EAN resuelto por un nivel superior.

        Solo registra si la confianza es "high" o "medium", con la excepción
        de Amazon (Nivel 3): para ese cliente solo se aprende cuando la confianza
        es "high" (ficha de producto completa); los resultados "medium" de Amazon
        no se registran para evitar contaminar la caché con inferencias ambiguas.
        Los resultados con confianza "low" nunca se registran.

        El prefijo registrado tiene ``_PREFIJO_APRENDIZAJE_LEN`` dígitos
        (7 por defecto), que es específico para distinguir fabricantes pero
        suficientemente general para cubrir todos sus EANs.

        Args:
            ean: código EAN que acaba de resolverse.
            resultado: BrandResult devuelto por el nivel resolvedor.
        """
        if resultado.confidence not in ("high", "medium"):
            logger.debug(
                "Prefijo no aprendido — confianza insuficiente",
                extra={"ean": ean, "confidence": resultado.confidence},
            )
            return

        if not resultado.brand_name:
            return

        prefijo = ean[:_PREFIJO_APRENDIZAJE_LEN]
        company_name = resultado.manufacturer or resultado.brand_name

        self._cache.register(
            prefix=prefijo,
            company_name=company_name,
            country_code="",  # Desconocido al aprender desde web/API
        )
