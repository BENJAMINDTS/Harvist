"""
Pipeline de resolución EAN → marca de producto.

Flujo:
  1. CsvParser → lista de productos con EAN
  2. EanBrandResolver (Selenium/Bing exacto) → marca detectada por EAN
  3. Exporta marcas.csv al storage del job con columnas:
     codigo, ean, marca_detectada, exitoso, error

Solo procesa productos que tengan EAN. Los productos sin EAN se
incluyen en el CSV de salida con marca_detectada vacía y exitoso=False.

:author: BenjaminDTS
:version: 2.0.0
"""

from __future__ import annotations

import csv
import io
from typing import Callable

from loguru import logger

from api.core.config import get_settings
from api.v1.schemas.job import SearchConfig
from services.csv_parser import CsvParser, CsvParserError
from services.scraper.brand_scraper import EanBrandResolver, ResultadoMarca
from services.storage_service import StorageService, get_storage_service

# Firma: (job_id, procesados, total, exitosos) -> None
BrandProgressCallback = Callable[[str, int, int, int], None]


class BrandPipeline:
    """
    Orquestador del pipeline de resolución EAN → marca.

    Para cada producto del CSV que tenga EAN, busca el EAN exacto en Bing
    y extrae la marca del producto a partir de los títulos de los resultados.
    El resultado final es un CSV descargable con la marca detectada por producto.

    :author: BenjaminDTS
    """

    def __init__(
        self,
        job_id: str,
        config: SearchConfig,
        storage: StorageService | None = None,
        carpeta_job_id: str | None = None,
    ) -> None:
        """
        Inicializa el pipeline de resolución de marcas.

        Args:
            job_id: identificador del job (para progreso y logs).
            config: configuración del job (se usa column_mapping para parsear el CSV).
            storage: servicio de almacenamiento. Si None usa el factory.
            carpeta_job_id: carpeta de almacenamiento a reutilizar (para resume).
        """
        self._job_id = job_id
        self._carpeta_id = carpeta_job_id or job_id
        self._config = config
        self._storage = storage or get_storage_service()

    def ejecutar(
        self,
        contenido_csv: str,
        callback: BrandProgressCallback | None = None,
        offset_productos: int = 0,
    ) -> dict:
        """
        Ejecuta el pipeline completo y devuelve un resumen.

        Args:
            contenido_csv: contenido del CSV como string (ya decodificado).
            callback: función de progreso (job_id, procesados, total, exitosos).
            offset_productos: número de productos a saltar (para resume).

        Returns:
            Dict con total_productos, marcas_exitosas, marcas_fallidas, errores_csv.

        Raises:
            CsvParserError: si el CSV es inválido estructuralmente.
        """
        logger.info(
            "Pipeline de resolución de marcas iniciado",
            extra={"job_id": self._job_id, "offset": offset_productos},
        )

        # ── Paso 1: Parsear CSV ───────────────────────────────────────────────
        parser = CsvParser(self._config)
        resultado_csv = parser.parsear(contenido_csv)

        if not resultado_csv.productos:
            raise CsvParserError(
                "El CSV no contiene productos válidos. "
                f"Errores: {'; '.join(resultado_csv.errores[:5])}"
            )

        productos = resultado_csv.productos
        total = len(productos)

        if offset_productos > 0:
            productos = productos[offset_productos:]
            logger.info(
                "Offset aplicado",
                extra={
                    "job_id": self._job_id,
                    "offset": offset_productos,
                    "pendientes": len(productos),
                },
            )

        logger.info(
            "CSV parseado",
            extra={"job_id": self._job_id, "total_productos": total},
        )

        # ── Paso 2: Resolver EAN → marca para cada producto ───────────────────
        resultados: list[ResultadoMarca] = []
        exitosos = 0

        settings = get_settings()
        from services.scraper.producer import _crear_driver  # noqa: PLC0415

        driver = _crear_driver(settings)

        try:
            resolver = EanBrandResolver()

            # Aceptar cookies de Bing una sola vez antes del loop.
            # El driver recién creado no tiene cookies; sin este paso Bing muestra
            # la página de consentimiento GDPR en cada búsqueda y no devuelve resultados.
            resolver.inicializar_sesion(driver)

            for idx, producto in enumerate(productos, start=offset_productos + 1):
                if producto.ean:
                    resultado = resolver.resolver(
                        codigo=producto.codigo,
                        ean=producto.ean,
                        driver=driver,
                    )
                else:
                    # Sin EAN: marcar como no procesable
                    resultado = ResultadoMarca(
                        codigo=producto.codigo,
                        ean="",
                        exitoso=False,
                        error="El producto no tiene EAN.",
                    )
                    logger.debug(
                        "Producto sin EAN omitido",
                        extra={"job_id": self._job_id, "codigo": producto.codigo},
                    )

                resultados.append(resultado)

                if resultado.exitoso:
                    exitosos += 1

                if callback:
                    callback(self._job_id, idx, total, exitosos)

                logger.debug(
                    "Producto procesado",
                    extra={
                        "job_id": self._job_id,
                        "codigo": producto.codigo,
                        "ean": producto.ean,
                        "marca": resultado.marca_detectada,
                        "progreso": f"{idx}/{total}",
                    },
                )

        finally:
            try:
                driver.quit()
            except Exception as exc:
                logger.warning(
                    "Error al cerrar el WebDriver del pipeline de marcas",
                    exc_info=exc,
                    extra={"job_id": self._job_id},
                )

        # ── Paso 3: Exportar marcas.csv ───────────────────────────────────────
        self._guardar_csv(resultados)

        resumen = {
            "total_productos": total,
            "marcas_exitosas": exitosos,
            "marcas_fallidas": total - exitosos,
            "errores_csv": resultado_csv.errores,
        }

        logger.info(
            "Pipeline de marcas completado",
            extra={
                "job_id": self._job_id,
                "total_productos": total,
                "marcas_exitosas": exitosos,
                "marcas_fallidas": total - exitosos,
            },
        )
        return resumen

    def _guardar_csv(self, resultados: list[ResultadoMarca]) -> None:
        """
        Serializa los resultados de resolución a CSV y los guarda en storage.

        Columnas: codigo, ean, marca_detectada, exitoso, error.

        Args:
            resultados: lista de ResultadoMarca con los datos de cada producto.
        """
        fieldnames = ["codigo", "ean", "marca_detectada", "exitoso", "error"]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for r in resultados:
            writer.writerow({
                "codigo": r.codigo,
                "ean": r.ean,
                "marca_detectada": r.marca_detectada,
                "exitoso": r.exitoso,
                "error": r.error,
            })

        try:
            self._storage.save_image(
                self._carpeta_id,
                "marcas.csv",
                buffer.getvalue().encode("utf-8-sig"),
            )
            logger.info(
                "marcas.csv guardado",
                extra={"job_id": self._job_id, "filas": len(resultados)},
            )
        except Exception as exc:
            logger.error(
                "Error guardando marcas.csv",
                exc_info=exc,
                extra={"job_id": self._job_id},
            )
