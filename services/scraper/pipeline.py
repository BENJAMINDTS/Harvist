"""
Orquestador del pipeline Productor/Consumidor de scraping.

Coordina:
  1. CsvParser → lista de productos con sus queries
  2. Producer (Selenium) → URLs de imágenes por producto
  3. Consumer (ThreadPool) → descarga, validación y guardado de imágenes
  4. StorageService → compresión final en ZIP
  5. Callback de progreso → actualización del JobStatus en Redis
  6. ImageCacheService → deduplicación de imágenes entre jobs (opcional)

El pipeline se ejecuta dentro de la tarea Celery. Este módulo no importa
nada de api/ ni de workers/ — es lógica de negocio pura.

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from loguru import logger

from api.core.config import get_settings
from api.v1.schemas.job import SearchConfig
from services.csv_parser import CsvParser, CsvParserError, Producto
from services.scraper.consumer import descargar_imagenes_producto
from services.scraper.producer import buscar_urls_imagenes
from services.storage_service import StorageService, get_storage_service

# Tipo del callback de progreso que recibe el pipeline del worker
# Firma: (job_id, productos_procesados, total, imagenes_ok, imagenes_fail) -> None
ProgressCallback = Callable[[str, int, int, int, int], None]

# Sentinel para distinguir "image_cache no pasado" de "image_cache=None explícito"
_CACHE_UNSET = object()


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
        image_cache=_CACHE_UNSET,
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
            image_cache: ImageCacheService explícito o None para deshabilitar caché.
                Si no se pasa (sentinel), se construye uno automáticamente según
                IMAGE_CACHE_ENABLED. Pasar None desactiva el caché sin leer settings.

        :author: BenjaminDTS
        """
        self._job_id = job_id
        self._carpeta_id = carpeta_job_id or job_id
        self._config = config
        self._storage = storage or get_storage_service()
        self._cache_hits = 0

        # Inicializar caché de imágenes
        if image_cache is _CACHE_UNSET:
            # No pasado explícitamente: leer de settings
            settings = get_settings()
            if settings.image_cache_enabled:
                from services.scraper.image_cache import ImageCacheService  # noqa: PLC0415
                self._image_cache = ImageCacheService(settings.image_cache_db)
            else:
                self._image_cache = None
        else:
            # Valor explícito (incluido None para deshabilitar en tests)
            self._image_cache = image_cache

    def ejecutar(
        self,
        contenido_csv: str,
        callback: ProgressCallback | None = None,
        offset_productos: int = 0,
        save_all_candidates: bool = False,
        codigos_filtro: set[str] | None = None,
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
                principio). Ignorado cuando codigos_filtro está definido.
            save_all_candidates: si True, descarga TODAS las candidatas válidas
                                sin límite al directorio candidates/. Si False,
                                comportamiento por defecto (hasta max_imagenes).
            codigos_filtro: conjunto de códigos de producto a procesar. Si se
                proporciona, solo se procesan los productos cuyos códigos estén
                en este conjunto (modo retry parcial). Tiene prioridad sobre
                offset_productos.

        Returns:
            Diccionario con el resumen: total_productos, imagenes_descargadas,
            imagenes_fallidas, errores_csv, ruta_zip, _productos,
            _productos_fallidos.

        Raises:
            CsvParserError: si el CSV es inválido estructuralmente.

        :author: BenjaminDTS
        """
        logger.info(
            "Pipeline iniciado",
            extra={
                "job_id": self._job_id,
                "offset_productos": offset_productos,
                "codigos_filtro": len(codigos_filtro) if codigos_filtro is not None else None,
            },
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
        total_original = len(productos)

        if codigos_filtro is not None:
            # Modo retry: procesar solo los productos con código en el filtro
            productos_pendientes = [p for p in productos if p.codigo in codigos_filtro]
            total = len(productos_pendientes)
            idx_start = 1
            logger.info(
                "Filtro de códigos aplicado (modo retry)",
                extra={
                    "job_id": self._job_id,
                    "codigos_filtro": len(codigos_filtro),
                    "productos_a_reintentar": total,
                },
            )
        elif offset_productos > 0:
            productos_pendientes = productos[offset_productos:]
            total = total_original
            idx_start = offset_productos + 1
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
            total = total_original
            idx_start = 1

        logger.info(
            "CSV parseado, iniciando scraping",
            extra={
                "job_id": self._job_id,
                "total_productos": total_original,
                "errores_csv": len(resultado_csv.errores),
            },
        )

        # ── Paso 2: Procesar cada producto (Productor → Consumidor) ───────────
        imagenes_ok = 0
        imagenes_fail = 0
        _productos_fallidos: list[dict] = []

        for idx, producto in enumerate(productos_pendientes, start=idx_start):
            producto_ok, producto_fail = self._procesar_producto(
                producto,
                save_all_candidates=save_all_candidates,
            )
            imagenes_ok += producto_ok
            imagenes_fail += producto_fail

            # Registrar productos sin imágenes descargadas como fallidos
            if producto_ok == 0 and producto_fail > 0:
                _productos_fallidos.append({
                    "codigo": producto.codigo,
                    "nombre": producto.nombre,
                    "razon": "imagen",
                })

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

        # ── Paso 3: Comprimir en ZIP (solo si NO se está en modo candidatos) ───
        # En modo candidatos el ZIP se genera tras la selección del usuario.
        if save_all_candidates:
            ruta_zip = ""
        else:
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
            "total_productos": total_original,
            "imagenes_descargadas": imagenes_ok,
            "imagenes_fallidas": imagenes_fail,
            "imagenes_cache_hit": self._cache_hits,
            "errores_csv": resultado_csv.errores,
            "ruta_zip": ruta_zip,
            "_productos": productos,  # Lista de productos para acceso posterior (Fase 7.5)
            "_productos_fallidos": _productos_fallidos,  # Fallos por producto para retry
        }

        logger.info(
            "Pipeline completado",
            extra={"job_id": self._job_id, **{k: v for k, v in resumen.items() if k not in ("errores_csv", "_productos", "_productos_fallidos")}},
        )
        return resumen

    def _procesar_producto(self, producto: Producto, save_all_candidates: bool = False) -> tuple[int, int]:
        """
        Ejecuta el ciclo Productor→Consumidor para un producto individual.

        Si IMAGE_CACHE_ENABLED está activo, comprueba si el producto ya fue
        descargado en un job anterior antes de lanzar Selenium. En caso de
        cache hit, copia la imagen directamente y omite el scraping.
        Tras una descarga exitosa, registra la imagen en el índice de caché.

        Args:
            producto: producto con su query ya construida.
            save_all_candidates: si True, descarga TODAS las candidatas válidas
                                sin límite al directorio candidates/. Si False,
                                comportamiento por defecto (hasta max_imagenes).

        Returns:
            Tupla (imagenes_ok, imagenes_fail) para el producto.

        :author: BenjaminDTS
        """
        # ── Cache lookup: evitar Selenium si la imagen ya existe ──────────────
        if self._image_cache is not None and not save_all_candidates:
            ean = producto.ean if producto.ean and producto.ean.strip() else None
            try:
                cached_path = self._image_cache.lookup(ean, producto.codigo)
                if cached_path is not None:
                    dest = self._storage.copy_from_cache(
                        cached_path,
                        self._carpeta_id,
                        producto.codigo,
                    )
                    self._cache_hits += 1
                    logger.info(
                        "Cache hit — imagen reutilizada sin Selenium",
                        extra={
                            "job_id": self._job_id,
                            "codigo": producto.codigo,
                            "ean": ean,
                            "cached_path": str(cached_path),
                            "dest": str(dest),
                        },
                    )
                    return 1, 0
            except Exception as exc:
                # Fallback: si copy_from_cache falla, continuar con descarga normal
                logger.error(
                    "Error al reutilizar imagen de caché, descargando de nuevo",
                    exc_info=exc,
                    extra={"job_id": self._job_id, "codigo": producto.codigo},
                )

        # ── Productor: obtener URLs de Bing ───────────────────────────────────
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

        # ── Consumidor: descargar, validar y guardar ──────────────────────────
        resultados = descargar_imagenes_producto(
            job_id=self._carpeta_id,
            producto=producto,
            urls=urls,
            storage=self._storage,
            max_imagenes=self._config.imagenes_por_producto,
            save_all_candidates=save_all_candidates,
        )

        ok = sum(1 for r in resultados if r.exitoso)
        fail = sum(1 for r in resultados if not r.exitoso)

        # ── Registrar en caché la primera imagen válida descargada ────────────
        # Solo después de validación Pillow exitosa (resultados exitosos ya pasaron Pillow).
        if ok > 0 and self._image_cache is not None and not save_all_candidates:
            primera_exitosa = next((r for r in resultados if r.exitoso), None)
            if primera_exitosa and primera_exitosa.ruta_guardada:
                ean = producto.ean if producto.ean and producto.ean.strip() else None
                ruta_imagen = Path(primera_exitosa.ruta_guardada)
                try:
                    from PIL import Image as _PilImage  # noqa: PLC0415
                    with _PilImage.open(ruta_imagen) as img:
                        width, height = img.size
                except Exception as exc:
                    logger.debug(
                        "No se pudo leer dimensiones de imagen para caché",
                        exc_info=exc,
                        extra={"path": str(ruta_imagen)},
                    )
                    width, height = 0, 0
                try:
                    self._image_cache.register(
                        ean=ean,
                        codigo=producto.codigo,
                        path=ruta_imagen,
                        job_id=self._carpeta_id,
                        width=width,
                        height=height,
                    )
                except Exception as exc:
                    logger.warning(
                        "No se pudo registrar imagen en caché",
                        exc_info=exc,
                        extra={"job_id": self._job_id, "codigo": producto.codigo},
                    )

        return ok, fail
