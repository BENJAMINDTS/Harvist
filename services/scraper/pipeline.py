"""
Orquestador del pipeline Productor/Consumidor de scraping.

Coordina:
  1. CsvParser → lista de productos con sus queries
  2. Producer (Selenium) → URLs de imágenes por producto
  3. Consumer (ThreadPool) → descarga, validación y guardado de imágenes
  4. StorageService → compresión final en ZIP
  5. Callback de progreso → actualización del JobStatus en Redis

El pipeline se ejecuta dentro de la tarea Celery. Este módulo no importa
nada de api/ ni de workers/ — es lógica de negocio pura.

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from typing import Callable

from loguru import logger

from api.v1.schemas.job import SearchConfig
from services.csv_parser import CsvParser, CsvParserError, Producto
from services.scraper.consumer import descargar_imagenes_producto
from services.scraper.producer import buscar_urls_imagenes
from services.storage_service import StorageService, get_storage_service

# Tipo del callback de progreso que recibe el pipeline del worker
# Firma: (job_id, productos_procesados, total, imagenes_ok, imagenes_fail) -> None
ProgressCallback = Callable[[str, int, int, int, int], None]


class ScrapingPipeline:
    """
    Orquestador del proceso completo de scraping para un job.

    Instanciar uno por job. No es thread-safe para el mismo job_id.

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
        Inicializa el pipeline para un job concreto.

        Args:
            job_id: identificador del job (usado para progreso y logs).
            config: configuración de búsqueda (modo, imágenes por producto, etc.).
            storage: servicio de almacenamiento. Si None, usa el factory por defecto.
            carpeta_job_id: job_id cuya carpeta de almacenamiento se reutiliza.
                Al reanudar un job se pasa el job_id original para que las
                imágenes se escriban en la misma carpeta. Si None se usa job_id.
        """
        self._job_id = job_id
        self._carpeta_id = carpeta_job_id or job_id
        self._config = config
        self._storage = storage or get_storage_service()

    def ejecutar(
        self,
        contenido_csv: str,
        callback: ProgressCallback | None = None,
        offset_productos: int = 0,
    ) -> dict:
        """
        Ejecuta el pipeline completo y devuelve un resumen del resultado.

        Args:
            contenido_csv: contenido del CSV como string (ya decodificado).
            callback: función de progreso invocada tras procesar cada producto.
                      Firma: (job_id, procesados, total, img_ok, img_fail)
            offset_productos: número de productos a saltar desde el inicio de
                la lista antes de comenzar a procesar. Se usa al reanudar un
                job cancelado o fallido. Por defecto 0 (procesar desde el
                principio).

        Returns:
            Diccionario con el resumen: total_productos, imagenes_descargadas,
            imagenes_fallidas, errores_csv, ruta_zip.

        Raises:
            CsvParserError: si el CSV es inválido estructuralmente.
        """
        logger.info(
            "Pipeline iniciado",
            extra={"job_id": self._job_id, "offset_productos": offset_productos},
        )

        # ── Paso 1: Parsear y validar el CSV ──────────────────────────────────
        parser = CsvParser(self._config)
        resultado_csv = parser.parsear(contenido_csv)

        if not resultado_csv.productos:
            raise CsvParserError(
                "El CSV no contiene productos válidos. "
                f"Errores encontrados: {'; '.join(resultado_csv.errores[:5])}"
            )

        productos = resultado_csv.productos
        total = len(productos)

        # Aplicar offset para reanudar desde donde se dejó
        if offset_productos > 0:
            productos_pendientes = productos[offset_productos:]
            logger.info(
                "Offset aplicado, saltando productos ya procesados",
                extra={
                    "job_id": self._job_id,
                    "offset_productos": offset_productos,
                    "productos_pendientes": len(productos_pendientes),
                },
            )
        else:
            productos_pendientes = productos

        logger.info(
            "CSV parseado, iniciando scraping",
            extra={
                "job_id": self._job_id,
                "total_productos": total,
                "errores_csv": len(resultado_csv.errores),
            },
        )

        # ── Paso 2: Procesar cada producto (Productor → Consumidor) ───────────
        imagenes_ok = 0
        imagenes_fail = 0

        for idx, producto in enumerate(productos_pendientes, start=offset_productos + 1):
            producto_ok, producto_fail = self._procesar_producto(producto)
            imagenes_ok += producto_ok
            imagenes_fail += producto_fail

            if callback:
                callback(self._job_id, idx, total, imagenes_ok, imagenes_fail)

            logger.debug(
                "Producto procesado",
                extra={
                    "job_id": self._job_id,
                    "codigo": producto.codigo,
                    "progreso": f"{idx}/{total}",
                    "imagenes_ok": producto_ok,
                    "imagenes_fail": producto_fail,
                },
            )

        # ── Paso 3: Comprimir en ZIP ───────────────────────────────────────────
        try:
            zip_path = self._storage.create_zip(self._carpeta_id)
            ruta_zip = str(zip_path)
        except Exception as exc:
            logger.error(
                "Error al crear el ZIP",
                exc_info=exc,
                extra={"job_id": self._job_id},
            )
            ruta_zip = ""

        resumen = {
            "total_productos": total,
            "imagenes_descargadas": imagenes_ok,
            "imagenes_fallidas": imagenes_fail,
            "errores_csv": resultado_csv.errores,
            "ruta_zip": ruta_zip,
        }

        logger.info(
            "Pipeline completado",
            extra={"job_id": self._job_id, **{k: v for k, v in resumen.items() if k != "errores_csv"}},
        )
        return resumen

    def _procesar_producto(self, producto: Producto) -> tuple[int, int]:
        """
        Ejecuta el ciclo Productor→Consumidor para un producto individual.

        Args:
            producto: producto con su query ya construida.

        Returns:
            Tupla (imagenes_ok, imagenes_fail) para el producto.
        """
        # Productor: obtener URLs de Bing
        try:
            urls = buscar_urls_imagenes(
                producto=producto,
                cantidad=self._config.imagenes_por_producto,
            )
        except Exception as exc:
            logger.error(
                "Error en productor para producto",
                exc_info=exc,
                extra={"job_id": self._job_id, "codigo": producto.codigo},
            )
            return 0, self._config.imagenes_por_producto

        if not urls:
            logger.warning(
                "Productor no encontró URLs para el producto",
                extra={"job_id": self._job_id, "codigo": producto.codigo},
            )
            return 0, 0

        # Consumidor: descargar, validar y guardar
        resultados = descargar_imagenes_producto(
            job_id=self._carpeta_id,
            producto=producto,
            urls=urls,
            storage=self._storage,
        )

        ok = sum(1 for r in resultados if r.exitoso)
        fail = sum(1 for r in resultados if not r.exitoso)
        return ok, fail
