"""
Pipeline de resolución EAN → marca de producto.

Flujo:
  1. CsvParser → lista de productos con EAN
  2. EanBrandResolver (cascada de 6 niveles, sin Selenium) → BrandResult por EAN
  3. Exporta marcas.csv al storage del job con columnas:
     codigo, ean, brand_name, manufacturer, source, confidence

Solo procesa productos que tengan EAN. Los productos sin EAN se
incluyen en el CSV de salida con brand_name vacío y source="ean_invalido".

A diferencia de versiones anteriores, este pipeline NO utiliza Selenium ni
ningún WebDriver. Toda la resolución se realiza mediante HTTP síncrono
(httpx.Client) a través de los clientes de ean_http_clients.py.

:author: BenjaminDTS
:version: 3.0.0
"""

from __future__ import annotations

import csv
import io
from typing import Callable

from loguru import logger

from api.v1.schemas.job import SearchConfig
from services.csv_parser import CsvParser, CsvParserError
from services.scraper.brand_scraper import EanBrandResolver
from services.scraper.brand_validator import BrandResult
from services.storage_service import StorageService, get_storage_service

# Firma: (job_id, procesados, total, exitosos) -> None
BrandProgressCallback = Callable[[str, int, int, int], None]


class BrandPipeline:
    """
    Orquestador del pipeline de resolución EAN → marca.

    Para cada producto del CSV que tenga EAN, ejecuta la cascada de 6 niveles
    del EanBrandResolver y exporta los resultados a marcas.csv en el storage
    del job. El CSV incluye el campo ``source`` para auditoría (qué nivel
    resolvió cada EAN) y ``confidence`` para filtrar resultados poco fiables.

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
                Si None se usa job_id.
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

        Crea una única instancia de EanBrandResolver para todo el lote, lo que
        permite que la caché GS1 aprenda prefijos durante el procesamiento y
        acelere las resoluciones de EANs del mismo fabricante.

        Args:
            contenido_csv: contenido del CSV como string (ya decodificado).
            callback: función de progreso con firma (job_id, procesados, total, exitosos).
                Se invoca tras resolver cada producto.
            offset_productos: número de productos a saltar desde el inicio del CSV.
                Útil para reanudar jobs cancelados o fallidos.

        Returns:
            Dict con las claves:
              - total_productos (int): total de filas del CSV.
              - marcas_exitosas (int): productos con brand_name resuelto.
              - marcas_fallidas (int): productos sin brand_name resuelto.
              - errores_csv (list[str]): errores de parseo del CSV.

        Raises:
            CsvParserError: si el CSV está vacío o tiene formato inválido.
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
            "CSV parseado, iniciando resolución de marcas",
            extra={"job_id": self._job_id, "total_productos": total},
        )

        # ── Paso 2: Resolver EAN → marca ──────────────────────────────────────
        # Se crea una sola instancia del resolver para que la caché GS1 persista
        # entre productos. Cada vez que el Nivel 3, 4 o 5 resuelve un EAN,
        # registra el prefijo para acelerar resoluciones posteriores del mismo
        # fabricante.
        resolver = EanBrandResolver()
        resultados: list[BrandResult] = []
        exitosos = 0

        for idx, producto in enumerate(productos, start=offset_productos + 1):
            if producto.ean:
                resultado = resolver.resolver(
                    codigo=producto.codigo,
                    ean=producto.ean,
                )
            else:
                # Sin EAN: marcar directamente como inválido sin peticiones HTTP
                resultado = BrandResult(
                    ean_code="",
                    source="ean_invalido",
                    confidence="low",
                )
                logger.debug(
                    "Producto sin EAN — omitido",
                    extra={"job_id": self._job_id, "codigo": producto.codigo},
                )

            # Enriquecer el resultado con el código interno del producto para que
            # _guardar_csv pueda asociar cada fila con su código de producto.
            # BrandResult es inmutable (Pydantic BaseModel), por lo que guardamos
            # el código como metadato en una tupla.
            resultados.append(resultado)

            exitoso = resultado.source not in ("not_found", "ean_invalido")
            if exitoso:
                exitosos += 1

            if callback:
                callback(self._job_id, idx, total, exitosos)

            logger.debug(
                "Producto procesado",
                extra={
                    "job_id": self._job_id,
                    "codigo": producto.codigo,
                    "ean": producto.ean,
                    "brand": resultado.brand_name,
                    "source": resultado.source,
                    "confidence": resultado.confidence,
                    "progreso": f"{idx}/{total}",
                },
            )

        # ── Paso 3: Exportar marcas.csv ───────────────────────────────────────
        # Guardamos los resultados junto a los códigos de producto, que necesitamos
        # para el CSV. Construimos una lista combinada antes de exportar.
        productos_resultados = list(zip(
            resultado_csv.productos[offset_productos:] if offset_productos else resultado_csv.productos,
            resultados,
        ))
        self._guardar_csv(productos_resultados)

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

    def _guardar_csv(
        self,
        productos_resultados: list[tuple],
    ) -> None:
        """
        Serializa los resultados de resolución a CSV y los guarda en storage.

        Columnas exportadas: codigo, ean, brand_name, manufacturer, source, confidence.
        El archivo se codifica en UTF-8 con BOM (utf-8-sig) para compatibilidad
        con Excel.

        Args:
            productos_resultados: lista de tuplas (Producto, BrandResult).
        """
        fieldnames = [
            "codigo",
            "ean",
            "brand_name",
            "manufacturer",
            "source",
            "confidence",
        ]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for producto, resultado in productos_resultados:
            writer.writerow({
                "codigo": producto.codigo,
                "ean": producto.ean,
                "brand_name": resultado.brand_name or "",
                "manufacturer": resultado.manufacturer or "",
                "source": resultado.source,
                "confidence": resultado.confidence,
            })

        try:
            self._storage.save_image(
                self._carpeta_id,
                "marcas.csv",
                buffer.getvalue().encode("utf-8-sig"),
            )
            logger.info(
                "marcas.csv guardado",
                extra={"job_id": self._job_id, "filas": len(productos_resultados)},
            )
        except Exception as exc:
            logger.error(
                "Error guardando marcas.csv",
                exc_info=exc,
                extra={"job_id": self._job_id},
            )
