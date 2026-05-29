"""
Tareas Celery del Proyecto Scraping.

Este módulo envuelve los servicios de negocio en tareas asíncronas Celery.
Contiene _JobProgressReporter, adaptador Redis que desacopla la lógica de
persistencia de progreso de los pipelines de servicio.

:author: BenjaminDTS
:author: Carlitos6712
:version: 1.0.0
"""

import asyncio
import base64
import json
import uuid
from datetime import datetime

import redis as sync_redis
from celery.utils.log import get_task_logger
from loguru import logger

from api.core.config import get_settings
from api.v1.schemas.job import EstadoJob, JobStatus, RetryJobRequest, SearchConfig, TipoJob
from services.csv_parser import CsvParserError
from services.scraper.pipeline import ScrapingPipeline
from workers.celery_app import celery_app

# Logger de Celery (no sustituye a loguru — es complementario para el worker)
task_logger = get_task_logger(__name__)

_JOB_KEY = "job:{job_id}"
_BRANDS_PENDING_KEY = "job:{job_id}:brands_pending"
_PHOTOS_PENDING_KEY = "job:{job_id}:photos_pending"
_FAILED_PRODUCTS_KEY = "job:{job_id}:failed_products"


class JobCancelledError(Exception):
    """Se lanza cuando el job ha sido cancelado externamente vía Redis."""
# Sorted set donde se registran todos los job_ids para el panel de historial.
# Score = timestamp UTC en segundos (ZREVRANGE devuelve los más recientes primero).
_HISTORY_KEY = "jobs:history"


def _get_redis_client() -> sync_redis.Redis:
    """
    Crea un cliente Redis síncrono para actualizar el estado del job.

    Returns:
        Cliente Redis configurado con decode_responses=True.
    """
    settings = get_settings()
    return sync_redis.from_url(settings.redis_url, decode_responses=True)


def _actualizar_estado(
    redis_client: sync_redis.Redis,
    job_status: JobStatus,
) -> None:
    """
    Serializa y persiste el JobStatus en Redis.

    Args:
        redis_client: cliente Redis síncrono.
        job_status: estado actualizado del job.
    """
    settings = get_settings()
    redis_client.set(
        _JOB_KEY.format(job_id=str(job_status.job_id)),
        job_status.model_dump_json(),
        ex=settings.file_ttl_seconds,
    )


class _JobProgressReporter:
    """
    Adaptador Redis para los callbacks de progreso de los pipelines.

    Encapsula la lógica de comprobación de cancelación y actualización
    de estado en Redis. Los pipelines reciben métodos enlazados de esta
    clase como callables genéricos — no saben nada de Redis.

    :author: BenjaminDTS
    """

    def __init__(
        self,
        redis_client: sync_redis.Redis,
        job_status: JobStatus,
    ) -> None:
        """
        Inicializa el reporter con el cliente Redis y el estado del job.

        Args:
            redis_client: cliente Redis síncrono compartido con la tarea.
            job_status: instancia mutable de JobStatus que se persiste en Redis.
        """
        self._redis = redis_client
        self._status = job_status

    def _check_cancelled(self, job_id: str) -> None:
        """
        Lanza JobCancelledError si el job fue cancelado externamente.

        Args:
            job_id: identificador del job a comprobar.

        Raises:
            JobCancelledError: si el estado en Redis es CANCELADO.
        """
        raw = self._redis.get(_JOB_KEY.format(job_id=job_id))
        if raw:
            current = JobStatus.model_validate_json(raw)
            if current.estado == EstadoJob.CANCELADO:
                raise JobCancelledError(f"Job {job_id} cancelado por el usuario.")

    def _save(self) -> None:
        """Persiste el estado actual en Redis."""
        self._status.actualizado_en = datetime.utcnow()
        _actualizar_estado(self._redis, self._status)

    def fotos(
        self,
        jid: str,
        procesados: int,
        total: int,
        img_ok: int,
        img_fail: int,
    ) -> None:
        """
        Callback de progreso para el pipeline de descarga de fotos.

        Args:
            jid: job_id.
            procesados: productos procesados hasta ahora.
            total: total de productos del CSV.
            img_ok: imágenes descargadas exitosamente.
            img_fail: imágenes que fallaron.

        Raises:
            JobCancelledError: si el job fue cancelado desde la API.
        """
        self._check_cancelled(jid)
        self._status.total_productos = total
        self._status.productos_procesados = procesados
        self._status.imagenes_descargadas = img_ok
        self._status.imagenes_fallidas = img_fail
        self._status.mensaje = (
            f"Procesando producto {procesados}/{total} — "
            f"{img_ok} imágenes descargadas."
        )
        self._save()

    def descripciones(
        self,
        jid: str,
        procesados: int,
        total: int,
        descripciones_ok: int,
    ) -> None:
        """
        Callback de progreso para el pipeline de generación de descripciones.

        Args:
            jid: job_id.
            procesados: productos procesados hasta ahora.
            total: total de productos del CSV.
            descripciones_ok: descripciones generadas exitosamente.

        Raises:
            JobCancelledError: si el job fue cancelado desde la API.
        """
        self._check_cancelled(jid)
        self._status.total_productos = total
        self._status.productos_procesados = procesados
        self._status.descripciones_generadas = descripciones_ok
        self._status.mensaje = (
            f"Generando descripción {procesados}/{total} — "
            f"{descripciones_ok} completadas."
        )
        self._save()

    def marcas(
        self,
        jid: str,
        procesadas: int,
        total: int,
        exitosas: int,
    ) -> None:
        """
        Callback de progreso para el pipeline de resolución de marcas.

        Args:
            jid: job_id.
            procesadas: marcas procesadas hasta ahora.
            total: total de marcas únicas extraídas del CSV.
            exitosas: marcas procesadas con éxito.

        Raises:
            JobCancelledError: si el job fue cancelado desde la API.
        """
        self._check_cancelled(jid)
        self._status.total_productos = total
        self._status.productos_procesados = procesadas
        self._status.marcas_procesadas = exitosas
        self._status.mensaje = (
            f"Procesando marca {procesadas}/{total} — "
            f"{exitosas} completadas."
        )
        self._save()

    def traducciones(
        self,
        jid: str,
        idioma: str,
        total: int,
        traducciones_ok: int,
    ) -> None:
        """
        Callback de progreso para el pipeline de traducción automática.

        Args:
            jid: job_id.
            idioma: código ISO 639-1 del idioma destino.
            total: total de productos a traducir.
            traducciones_ok: traducciones generadas exitosamente en este idioma.

        Raises:
            JobCancelledError: si el job fue cancelado desde la API.
        """
        self._check_cancelled(jid)
        self._status.traducciones_generadas[idioma] = traducciones_ok
        self._status.mensaje = (
            f"Traduciendo al {idioma}: {traducciones_ok}/{total} completadas."
        )
        self._save()

    def seo(
        self,
        jid: str,
        procesados: int,
        total: int,
        seo_ok: int,
    ) -> None:
        """
        Callback de progreso para el pipeline de generación de textos SEO.

        Args:
            jid: job_id.
            procesados: productos procesados hasta ahora.
            total: total de productos del CSV.
            seo_ok: textos SEO generados exitosamente.

        Raises:
            JobCancelledError: si el job fue cancelado desde la API.
        """
        self._check_cancelled(jid)
        self._status.total_productos = total
        self._status.productos_procesados = procesados
        self._status.seo_generados = seo_ok
        self._status.mensaje = (
            f"Generando SEO {procesados}/{total} — "
            f"{seo_ok} completados."
        )
        self._save()

    def retry(
        self,
        jid: str,
        procesados: int,
        total: int,
        _img_ok: int,
        _img_fail: int,
    ) -> None:
        """
        Callback de progreso para el pipeline de reintento de fotos fallidas.

        Los contadores de imágenes se actualizan fuera del callback tras completar
        el pipeline, por lo que aquí solo se persiste el mensaje de progreso.

        Args:
            jid: job_id.
            procesados: productos reintentados hasta ahora.
            total: total de productos a reintentar.
            _img_ok: ignorado — los contadores se calculan al finalizar.
            _img_fail: ignorado — los contadores se calculan al finalizar.

        Raises:
            JobCancelledError: si el job fue cancelado externamente.
        """
        self._check_cancelled(jid)
        self._status.mensaje = f"Reintentando: {procesados}/{total} productos procesados."
        self._save()


@celery_app.task(
    bind=True,
    name="workers.tasks.ejecutar_scraping",
    max_retries=2,
    default_retry_delay=30,
)
def ejecutar_scraping(
    self,
    job_id: str,
    contenido_csv: str,
    config_dict: dict,
    offset_productos: int = 0,
    carpeta_job_id: str | None = None,
) -> dict:
    """
    Tarea Celery que ejecuta el pipeline completo de scraping para un job.

    Persiste el estado del job en Redis en cada etapa para que el WebSocket
    pueda emitir actualizaciones en tiempo real al frontend.

    Args:
        self: instancia de la tarea (bind=True, requerido para self.retry).
        job_id: identificador UUID del job.
        contenido_csv: contenido del CSV como string UTF-8.
        config_dict: SearchConfig serializado como diccionario.
        offset_productos: número de productos a saltar desde el inicio del CSV.
            Se usa al reanudar un job cancelado o fallido para no reprocesar
            los productos que ya fueron completados. Por defecto 0 (sin salto).
        carpeta_job_id: job_id original cuya carpeta de almacenamiento se
            reutiliza al reanudar. Si None, se usa job_id (comportamiento normal).

    Returns:
        Diccionario con el resumen del pipeline (total, ok, fail, ruta_zip).

    Raises:
        CsvParserError: si el CSV es inválido estructuralmente (no se reintenta).
        Exception: cualquier otro error hace que Celery reintente la tarea.
    """
    settings = get_settings()
    redis_client = _get_redis_client()
    config = SearchConfig.model_validate(config_dict)

    job_status = JobStatus(
        job_id=uuid.UUID(job_id),
        estado=EstadoJob.EN_PROCESO,
        mensaje="Iniciando pipeline de scraping...",
    )
    _actualizar_estado(redis_client, job_status)

    # Registrar en el historial con score = timestamp UTC para ordenación cronológica
    redis_client.zadd(_HISTORY_KEY, {job_id: datetime.utcnow().timestamp()})

    logger.info("Tarea Celery iniciada", extra={"job_id": job_id})

    reporter = _JobProgressReporter(redis_client, job_status)

    try:
        if config.tipo_job == TipoJob.DESCRIPCIONES:
            from services.ai.description_pipeline import DescripcionPipeline  # noqa: PLC0415
            pipeline_desc = DescripcionPipeline(job_id=job_id, config=config, carpeta_job_id=carpeta_job_id)
            resumen = pipeline_desc.ejecutar(
                contenido_csv=contenido_csv,
                callback=reporter.descripciones,
                offset_productos=offset_productos,
            )

            # ── Fase 7.2: traducciones automáticas ───────────────────────────
            if config.target_languages:
                from services.ai.translation_pipeline import TranslationPipeline  # noqa: PLC0415
                _productos_desc = resumen.get("_productos", [])
                _resultados_desc = resumen.get("_resultados", [])

                for idioma in config.target_languages:
                    pipeline_trad = TranslationPipeline(
                        job_id=job_id,
                        config=config,
                        carpeta_job_id=carpeta_job_id,
                    )
                    resumen_trad = pipeline_trad.ejecutar(
                        productos=_productos_desc,
                        descripciones=_resultados_desc,
                        idioma_destino=idioma,
                    )
                    reporter.traducciones(
                        job_id,
                        idioma,
                        resumen_trad["total_productos"],
                        resumen_trad["traducciones_generadas"],
                    )
        elif config.tipo_job == TipoJob.SEO:
            from services.ai.seo_pipeline import SeoPipeline  # noqa: PLC0415
            pipeline_seo = SeoPipeline(job_id=job_id, config=config, carpeta_job_id=carpeta_job_id)
            resumen = pipeline_seo.ejecutar(
                contenido_csv=contenido_csv,
                callback=reporter.seo,
                offset_productos=offset_productos,
            )
        elif config.tipo_job == TipoJob.MARCAS:
            from services.scraper.brand_pipeline import BrandPipeline  # noqa: PLC0415
            pipeline_marcas = BrandPipeline(
                job_id=job_id,
                config=config,
                carpeta_job_id=carpeta_job_id,
                write_cache=not config.validate_brands,
            )
            resumen = pipeline_marcas.ejecutar(
                contenido_csv=contenido_csv,
                callback=reporter.marcas,
                offset_productos=offset_productos,
            )
        else:
            pipeline_fotos = ScrapingPipeline(job_id=job_id, config=config, carpeta_job_id=carpeta_job_id)
            resumen = pipeline_fotos.ejecutar(
                contenido_csv=contenido_csv,
                callback=reporter.fotos,
                offset_productos=offset_productos,
                save_all_candidates=config.select_photos,
            )

            # ── Fase 7.5: Pausa si select_photos=True ────────────────────────────
            if config.select_photos:
                from services.storage_service import get_storage_service  # noqa: PLC0415
                storage = get_storage_service()
                productos = resumen.get("_productos", [])

                # Contar candidatas por producto
                photos_pending: dict[str, int] = {}
                productos_con_candidatas = 0

                for producto in productos:
                    candidates = storage.list_candidates(
                        carpeta_job_id or job_id,
                        producto.codigo
                    )
                    if candidates:
                        photos_pending[producto.codigo] = len(candidates)
                        productos_con_candidatas += 1

                if productos_con_candidatas > 0:
                    # Guardar en Redis las fotos pendientes
                    redis_client.set(
                        _PHOTOS_PENDING_KEY.format(job_id=job_id),
                        json.dumps(photos_pending, ensure_ascii=False),
                        ex=settings.file_ttl_seconds,
                    )

                    job_status.estado = EstadoJob.PENDIENTE_SELECCION_FOTOS
                    job_status.fotos_pendientes_seleccion = productos_con_candidatas
                    job_status.actualizado_en = datetime.utcnow()
                    job_status.mensaje = (
                        f"Imágenes descargadas: {resumen.get('imagenes_descargadas', 0)} de "
                        f"{resumen['total_productos']}. "
                        f"{productos_con_candidatas} productos pendientes de seleccionar foto."
                    )
                    _actualizar_estado(redis_client, job_status)

                    logger.info(
                        "Job pausado en PENDIENTE_SELECCION_FOTOS",
                        extra={
                            "job_id": job_id,
                            "productos_con_candidatas": productos_con_candidatas,
                        },
                    )
                    logger.info(
                        "Fotos pendientes guardadas en Redis",
                        extra={
                            "job_id": job_id,
                            "fotos_por_producto": photos_pending,
                        },
                    )

                    return {
                        "total_productos": resumen["total_productos"],
                        "imagenes_descargadas": resumen.get("imagenes_descargadas", 0),
                        "imagenes_fallidas": resumen.get("imagenes_fallidas", 0),
                        "fotos_pendientes_seleccion": productos_con_candidatas,
                        "estado": EstadoJob.PENDIENTE_SELECCION_FOTOS.value,
                    }

        # Actualizar estado final: COMPLETADO
        job_status.estado = EstadoJob.COMPLETADO
        job_status.completado_en = datetime.utcnow()
        job_status.actualizado_en = datetime.utcnow()
        if config.tipo_job == TipoJob.DESCRIPCIONES:
            job_status.total_productos = resumen["total_productos"]
            job_status.descripciones_generadas = resumen.get("descripciones_generadas", 0)
            job_status.revisiones_pendientes = resumen.get("descripciones_generadas", 0)
            if config.target_languages:
                job_status.mensaje = (
                    f"Completado: {resumen.get('descripciones_generadas', 0)} descripciones generadas "
                    f"de {resumen['total_productos']} productos. "
                    f"Idiomas traducidos: {', '.join(config.target_languages)}."
                )
            else:
                job_status.mensaje = (
                    f"Completado: {resumen.get('descripciones_generadas', 0)} descripciones generadas "
                    f"de {resumen['total_productos']} productos."
                )
        elif config.tipo_job == TipoJob.SEO:
            job_status.total_productos = resumen["total_productos"]
            job_status.productos_procesados = resumen["total_productos"]
            job_status.seo_generados = resumen.get("seo_generados", 0)
            job_status.seo_errores = resumen.get("seo_errores", 0)
            job_status.mensaje = (
                f"Completado: {resumen.get('seo_generados', 0)} textos SEO generados "
                f"de {resumen['total_productos']} productos."
            )
        elif config.tipo_job == TipoJob.MARCAS:
            job_status.total_productos = resumen["total_productos"]
            job_status.productos_procesados = resumen["total_productos"]
            job_status.marcas_procesadas = resumen.get("marcas_exitosas", 0)

            new_entries: dict[str, str] = resumen.get("new_cache_entries", {})

            if config.validate_brands and new_entries:
                # Hay marcas nuevas pendientes de validación: guardar en Redis y
                # dejar el job en estado intermedio (no COMPLETADO todavía).
                redis_client.set(
                    _BRANDS_PENDING_KEY.format(job_id=job_id),
                    json.dumps(new_entries, ensure_ascii=False),
                    ex=settings.file_ttl_seconds,
                )
                job_status.estado = EstadoJob.PENDIENTE_VALIDACION_MARCAS
                job_status.completado_en = None  # No completado aún
                job_status.marcas_pendientes_validacion = len(new_entries)
                job_status.mensaje = (
                    f"Marcas procesadas: {resumen.get('marcas_exitosas', 0)} de "
                    f"{resumen['total_productos']}. "
                    f"{len(new_entries)} marcas nuevas pendientes de validación."
                )
                logger.info(
                    "Job en espera de validación de marcas",
                    extra={
                        "job_id": job_id,
                        "marcas_nuevas": len(new_entries),
                    },
                )
            elif config.validate_brands and not new_entries:
                # validate_brands=True pero no hay marcas nuevas: completar directamente
                job_status.estado = EstadoJob.COMPLETADO
                job_status.completado_en = datetime.utcnow()
                job_status.mensaje = (
                    f"Completado: {resumen.get('marcas_exitosas', 0)} marcas procesadas "
                    f"de {resumen['total_productos']}. Sin marcas nuevas para validar."
                )
            else:
                # validate_brands=False (comportamiento por defecto)
                job_status.estado = EstadoJob.COMPLETADO
                job_status.completado_en = datetime.utcnow()
                job_status.mensaje = (
                    f"Completado: {resumen.get('marcas_exitosas', 0)} marcas procesadas "
                    f"de {resumen['total_productos']}."
                )
        else:
            job_status.total_productos = resumen["total_productos"]
            job_status.imagenes_descargadas = resumen.get("imagenes_descargadas", 0)
            job_status.imagenes_fallidas = resumen.get("imagenes_fallidas", 0)
            job_status.imagenes_cache_hit = resumen.get("imagenes_cache_hit", 0)
            cache_hit_txt = (
                f" ({job_status.imagenes_cache_hit} desde caché)"
                if job_status.imagenes_cache_hit > 0
                else ""
            )
            job_status.mensaje = (
                f"Completado: {resumen.get('imagenes_descargadas', 0)} imágenes descargadas"
                f"{cache_hit_txt} de {resumen['total_productos']} productos."
            )
            # Registrar productos fallidos en Redis para permitir retry parcial
            _productos_fallidos = resumen.get("_productos_fallidos", [])
            if _productos_fallidos:
                redis_client.set(
                    _FAILED_PRODUCTS_KEY.format(job_id=job_id),
                    json.dumps(_productos_fallidos, ensure_ascii=False),
                    ex=settings.file_ttl_seconds,
                )
                job_status.productos_fallidos = [fp["codigo"] for fp in _productos_fallidos]
                logger.info(
                    "Productos fallidos registrados en Redis",
                    extra={"job_id": job_id, "n_fallidos": len(_productos_fallidos)},
                )
        _actualizar_estado(redis_client, job_status)

        resumen_retorno = {k: v for k, v in resumen.items() if k not in ("errores_csv", "_productos", "_resultados")}
        logger.info(
            "Tarea Celery completada",
            extra={"job_id": job_id, **resumen_retorno},
        )
        return resumen_retorno

    except JobCancelledError:
        # El job fue cancelado externamente — no reintenta, no es un error
        logger.info("Tarea cancelada por el usuario", extra={"job_id": job_id})
        return {"cancelado": True}

    except CsvParserError as exc:
        # Error irrecuperable — no reintenta
        logger.error(
            "CSV inválido, tarea no reintentable",
            exc_info=exc,
            extra={"job_id": job_id},
        )
        job_status.estado = EstadoJob.FALLIDO
        job_status.error = str(exc)
        job_status.mensaje = "El archivo CSV es inválido."
        job_status.actualizado_en = datetime.utcnow()
        _actualizar_estado(redis_client, job_status)
        return {"error": str(exc)}

    except Exception as exc:
        logger.error(
            "Error inesperado en el pipeline, reintentando",
            exc_info=exc,
            extra={"job_id": job_id, "intento": self.request.retries},
        )

        # Si aún hay reintentos disponibles, marcar como EN_PROCESO y reintentar
        if self.request.retries < self.max_retries:
            job_status.mensaje = (
                f"Error temporal, reintentando... ({self.request.retries + 1}/{self.max_retries})"
            )
            _actualizar_estado(redis_client, job_status)
            raise self.retry(exc=exc)

        # Sin más reintentos — marcar como FALLIDO
        job_status.estado = EstadoJob.FALLIDO
        job_status.error = str(exc)
        job_status.mensaje = "El trabajo falló tras varios intentos."
        job_status.actualizado_en = datetime.utcnow()
        _actualizar_estado(redis_client, job_status)
        return {"error": str(exc)}

    finally:
        redis_client.close()


_DOLIBARR_IMPORT_KEY = "dolibarr_import:{task_id}"
_DOLIBARR_IMPORT_TTL = 86400  # 24 horas


@celery_app.task(
    bind=True,
    name="workers.tasks.importar_productos_dolibarr",
)
def importar_productos_dolibarr(
    self,
    task_id: str,
    csv_b64: str,
    mapping: dict,
    overwrite: bool,
    category_column: str,
    category_name_to_id: dict,
    dolibarr_url: str,
    dolibarr_api_key: str,
    subcategory_column: str = "",
    subcateg_pair_to_id: dict | None = None,
    brand_column: str = "",
    brand_name_to_id: dict | None = None,
) -> dict:
    """
    Tarea Celery que importa productos en masa a Dolibarr desde un CSV.

    Se ejecuta de forma asíncrona para soportar importaciones que duran horas.
    Actualiza el progreso en Redis cada 10 filas para que el frontend pueda
    consultarlo mediante polling.

    Args:
        self:                 instancia de la tarea (bind=True).
        task_id:              UUID de la tarea, usado como clave Redis.
        csv_b64:              contenido del CSV codificado en base64.
        mapping:              dict columna_csv → campo_dolibarr.
        overwrite:            si True, actualiza productos existentes.
        category_column:      nombre de la columna CSV con la categoría padre.
        category_name_to_id:  mapa nombre_categoría → ID Dolibarr (ya validado).
        dolibarr_url:         URL base de la API Dolibarr.
        dolibarr_api_key:     clave API Dolibarr.
        subcategory_column:   nombre de la columna CSV con la subcategoría (opcional).
        subcateg_pair_to_id:  mapa "padre||hijo" → ID Dolibarr de la subcategoría.
        brand_column:         nombre de la columna CSV con la marca (opcional).
        brand_name_to_id:     mapa nombre_marca → ID Dolibarr de la marca ya resuelta.

    Returns:
        Dict con resumen de la importación o ``{"error": str}`` si falla.

    :author: BenjaminDTS
    """
    settings = get_settings()
    redis_client = _get_redis_client()

    def _set_state(state: dict) -> None:
        redis_client.set(
            _DOLIBARR_IMPORT_KEY.format(task_id=task_id),
            json.dumps(state, ensure_ascii=False),
            ex=_DOLIBARR_IMPORT_TTL,
        )

    def _progress(processed: int, total: int) -> None:
        _set_state({
            "task_id": task_id,
            "status": "running",
            "progress": {"processed": processed, "total": total},
            "message": f"Importando {processed} de {total} productos...",
            "results": None,
        })

    _set_state({
        "task_id": task_id,
        "status": "running",
        "progress": {"processed": 0, "total": 0},
        "message": "Iniciando importación...",
        "results": None,
    })

    logger.info("Importación Dolibarr iniciada", extra={"task_id": task_id})

    async def _run() -> list[dict]:
        from services.integrations.dolibarr.categories import DolibarrCategoryService  # noqa: PLC0415
        from services.integrations.dolibarr.client import DolibarrClient  # noqa: PLC0415
        from services.integrations.dolibarr.products import DolibarrProductService  # noqa: PLC0415

        client = DolibarrClient(settings, override_url=dolibarr_url, override_api_key=dolibarr_api_key)
        svc = DolibarrProductService(client)
        needs_cat_svc = bool(category_column or subcategory_column or brand_column)
        cat_svc = DolibarrCategoryService(client) if needs_cat_svc else None

        content = base64.b64decode(csv_b64.encode())

        return await svc.import_from_csv(
            content=content,
            mapping=mapping,
            overwrite=overwrite,
            category_col=category_column or None,
            category_svc=cat_svc,
            category_name_to_id=category_name_to_id or None,
            subcategory_col=subcategory_column or None,
            subcateg_pair_to_id=subcateg_pair_to_id or None,
            brand_col=brand_column or None,
            brand_name_to_id=brand_name_to_id or None,
            progress_callback=_progress,
        )

    try:
        rows = asyncio.run(_run())

        created = sum(1 for r in rows if r.get("action") == "created")
        updated = sum(1 for r in rows if r.get("action") == "updated")
        skipped = sum(1 for r in rows if r.get("action") == "skipped")
        errors = sum(1 for r in rows if r.get("action") == "error")

        results = {
            "total": len(rows),
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "results": rows,
        }

        _set_state({
            "task_id": task_id,
            "status": "completed",
            "progress": {"processed": len(rows), "total": len(rows)},
            "message": f"Completado: {created} creados, {updated} actualizados, {errors} errores.",
            "results": results,
        })

        logger.info(
            "Importación Dolibarr completada",
            extra={"task_id": task_id, "total": len(rows), "created": created, "errors": errors},
        )
        return results

    except Exception as exc:
        logger.error("Error en importación Dolibarr", exc_info=exc, extra={"task_id": task_id})
        _set_state({
            "task_id": task_id,
            "status": "failed",
            "progress": {"processed": 0, "total": 0},
            "message": f"Error: {exc}",
            "results": None,
        })
        return {"error": str(exc)}

    finally:
        redis_client.close()


_WP_IMPORT_KEY = "wordpress_import:{task_id}"
_WP_IMPORT_TTL = 86400  # 24 horas


@celery_app.task(
    bind=True,
    name="workers.tasks.importar_productos_wordpress",
)
def importar_productos_wordpress(
    self,
    task_id: str,
    csv_b64: str,
    mapping: dict,
    overwrite: bool,
    brand_column: str = "",
    category_column: str = "",
    subcategory_column: str = "",
    custom_field_columns: list | None = None,
    wp_url: str = "",
    wp_consumer_key: str = "",
    wp_consumer_secret: str = "",
) -> dict:
    """
    Tarea Celery que importa productos en masa a WooCommerce desde un CSV.

    Se ejecuta de forma asíncrona. Actualiza el progreso en Redis cada 10 filas
    para que el frontend pueda consultarlo mediante polling.

    Args:
        self:                instancia de la tarea (bind=True).
        task_id:             UUID de la tarea, usado como clave Redis.
        csv_b64:             contenido del CSV codificado en base64.
        mapping:             dict columna_csv → campo_woocommerce.
        overwrite:           si True, actualiza productos con SKU existente.
        brand_column:        nombre de la columna CSV con la marca (opcional).
        category_column:      nombre de la columna CSV con la categoría raíz (opcional).
        subcategory_column:   nombre de la columna CSV con la subcategoría (opcional).
        custom_field_columns: lista de columnas CSV a crear como atributos WC (opcional).
        wp_url:               URL base de WordPress.
        wp_consumer_key:     Consumer Key WooCommerce.
        wp_consumer_secret:  Consumer Secret WooCommerce.

    Returns:
        Dict con resumen de la importación o ``{"error": str}`` si falla.

    :author: Carlitos6712
    """
    settings = get_settings()
    redis_client = _get_redis_client()

    def _set_state(state: dict) -> None:
        redis_client.set(
            _WP_IMPORT_KEY.format(task_id=task_id),
            json.dumps(state, ensure_ascii=False),
            ex=_WP_IMPORT_TTL,
        )

    def _progress(processed: int, total: int) -> None:
        _set_state({
            "task_id": task_id,
            "status": "running",
            "progress": {"processed": processed, "total": total},
            "message": f"Importando {processed} de {total} productos...",
            "results": None,
        })

    _set_state({
        "task_id": task_id,
        "status": "running",
        "progress": {"processed": 0, "total": 0},
        "message": "Iniciando importación...",
        "results": None,
    })

    logger.info("Importación WordPress iniciada", extra={"task_id": task_id})

    async def _run() -> list[dict]:
        from services.integrations.wordpress.brands import WordPressBrandService  # noqa: PLC0415
        from services.integrations.wordpress.categories import WordPressCategoryService  # noqa: PLC0415
        from services.integrations.wordpress.client import WordPressClient  # noqa: PLC0415
        from services.integrations.wordpress.products import WordPressProductService  # noqa: PLC0415

        client = WordPressClient(
            settings,
            override_url=wp_url,
            override_consumer_key=wp_consumer_key,
            override_consumer_secret=wp_consumer_secret,
        )
        svc = WordPressProductService(client)
        brand_svc = WordPressBrandService(client) if brand_column else None
        cat_svc = WordPressCategoryService(client) if (category_column or subcategory_column) else None

        content = base64.b64decode(csv_b64.encode())

        return await svc.import_from_csv(
            content=content,
            mapping=mapping,
            overwrite=overwrite,
            brand_col=brand_column or None,
            brand_svc=brand_svc,
            category_col=category_column or None,
            subcategory_col=subcategory_column or None,
            category_svc=cat_svc,
            custom_field_cols=custom_field_columns or None,
            progress_callback=_progress,
        )

    try:
        rows = asyncio.run(_run())

        created = sum(1 for r in rows if r.get("action") == "created")
        updated = sum(1 for r in rows if r.get("action") == "updated")
        skipped = sum(1 for r in rows if r.get("action") == "skipped")
        errors = sum(1 for r in rows if r.get("action") == "error")

        results = {
            "total": len(rows),
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "results": rows,
        }

        _set_state({
            "task_id": task_id,
            "status": "completed",
            "progress": {"processed": len(rows), "total": len(rows)},
            "message": f"Completado: {created} creados, {updated} actualizados, {errors} errores.",
            "results": results,
        })

        logger.info(
            "Importación WordPress completada",
            extra={"task_id": task_id, "total": len(rows), "created": created, "errors": errors},
        )
        return results

    except Exception as exc:
        logger.error("Error en importación WordPress", exc_info=exc, extra={"task_id": task_id})
        _set_state({
            "task_id": task_id,
            "status": "failed",
            "progress": {"processed": 0, "total": 0},
            "message": f"Error: {exc}",
            "results": None,
        })
        return {"error": str(exc)}

    finally:
        redis_client.close()


_JOB_CSV_KEY_WORKER = "job:{job_id}:csv"
_JOB_CONFIG_KEY_WORKER = "job:{job_id}:config"


@celery_app.task(
    bind=True,
    name="retry_job",
    max_retries=0,
)
def retry_job(
    self,
    job_id: str,
    retry_config: dict,
) -> dict:
    """
    Reintenta el procesamiento de los productos fallidos de un job de fotos.

    Lee la lista job:{job_id}:failed_products de Redis, filtra según los flags
    de retry_config, ejecuta el ScrapingPipeline solo con esos productos y
    actualiza los contadores del JobStatus en Redis.

    Args:
        self:         instancia de la tarea (bind=True).
        job_id:       ID del job original a reintentar.
        retry_config: dict serializado de RetryJobRequest con los flags de reintento.

    Returns:
        Dict con productos_reintentados y nuevos_ok.

    :author: BenjaminDTS
    """
    settings = get_settings()
    redis_client = _get_redis_client()

    try:
        # 1. Leer estado actual del job
        raw = redis_client.get(_JOB_KEY.format(job_id=job_id))
        if not raw:
            logger.error("Job no encontrado en Redis para retry", extra={"job_id": job_id})
            return {"error": "Job no encontrado"}

        job_status = JobStatus.model_validate_json(raw)
        config_obj = RetryJobRequest(**retry_config)

        # 2. Leer productos fallidos de Redis
        failed_raw = redis_client.get(_FAILED_PRODUCTS_KEY.format(job_id=job_id))
        all_failed: list[dict] = json.loads(failed_raw) if failed_raw else []

        # 3. Filtrar según flags de retry_config
        codigos_a_reintentar: set[str] = set()
        for fp in all_failed:
            razon = fp.get("razon", "")
            if razon == "imagen" and config_obj.retry_images:
                codigos_a_reintentar.add(fp["codigo"])
            elif razon == "descripcion" and config_obj.retry_descriptions:
                codigos_a_reintentar.add(fp["codigo"])
            elif razon == "marca" and config_obj.retry_brands:
                codigos_a_reintentar.add(fp["codigo"])
            elif razon == "seo" and config_obj.retry_seo:
                codigos_a_reintentar.add(fp["codigo"])

        if not codigos_a_reintentar:
            logger.warning("Ningún producto coincide con los flags de retry", extra={"job_id": job_id})
            return {"productos_reintentados": 0, "nuevos_ok": 0}

        n_reintentar = len(codigos_a_reintentar)

        # 4. Incrementar contador de reintentos y cambiar estado a EN_PROCESO
        job_status.reintentos += 1
        job_status.estado = EstadoJob.EN_PROCESO
        job_status.actualizado_en = datetime.utcnow()
        job_status.mensaje = f"Reintentando {n_reintentar} productos fallidos... (intento {job_status.reintentos})"
        _actualizar_estado(redis_client, job_status)

        # 5. Leer CSV y config originales
        csv_raw = redis_client.get(_JOB_CSV_KEY_WORKER.format(job_id=job_id))
        config_raw = redis_client.get(_JOB_CONFIG_KEY_WORKER.format(job_id=job_id))

        if not csv_raw:
            job_status.estado = EstadoJob.FALLIDO
            job_status.error = "CSV original expirado, no se puede reintentar."
            _actualizar_estado(redis_client, job_status)
            return {"error": "CSV expirado"}

        config = SearchConfig.model_validate(json.loads(config_raw) if config_raw else {})

        # 6. Callback de progreso para el retry
        retry_reporter = _JobProgressReporter(redis_client, job_status)

        # 7. Ejecutar pipeline solo con los productos fallidos
        pipeline = ScrapingPipeline(job_id=job_id, config=config)
        resumen = pipeline.ejecutar(
            contenido_csv=csv_raw,
            callback=retry_reporter.retry,
            codigos_filtro=codigos_a_reintentar,
        )

        nuevos_ok = resumen.get("imagenes_descargadas", 0)
        nuevos_fail = resumen.get("imagenes_fallidas", 0)

        # 8. Actualizar contadores: sumar éxitos, restar del total de fallos
        job_status.imagenes_descargadas = (job_status.imagenes_descargadas or 0) + nuevos_ok
        job_status.imagenes_fallidas = max(0, (job_status.imagenes_fallidas or 0) - nuevos_ok)

        # 9. Actualizar lista de productos que siguen fallando
        nuevos_fallidos: list[dict] = resumen.get("_productos_fallidos", [])
        # Añadir de vuelta los que no se reintentaron en este ciclo (razón diferente)
        no_reintentados = [fp for fp in all_failed if fp["codigo"] not in codigos_a_reintentar]
        fallidos_final = nuevos_fallidos + no_reintentados

        if fallidos_final:
            redis_client.set(
                _FAILED_PRODUCTS_KEY.format(job_id=job_id),
                json.dumps(fallidos_final, ensure_ascii=False),
                ex=settings.file_ttl_seconds,
            )
            job_status.productos_fallidos = [fp["codigo"] for fp in fallidos_final]
        else:
            redis_client.delete(_FAILED_PRODUCTS_KEY.format(job_id=job_id))
            job_status.productos_fallidos = []

        # 10. Estado final: COMPLETADO
        job_status.estado = EstadoJob.COMPLETADO
        job_status.completado_en = datetime.utcnow()
        job_status.actualizado_en = datetime.utcnow()
        job_status.mensaje = (
            f"Reintento completado: {nuevos_ok} productos recuperados de {n_reintentar} intentados."
        )
        _actualizar_estado(redis_client, job_status)

        logger.info(
            "retry_job completado",
            extra={
                "job_id": job_id,
                "n_reintentar": n_reintentar,
                "nuevos_ok": nuevos_ok,
                "nuevos_fail": nuevos_fail,
                "reintentos": job_status.reintentos,
            },
        )
        return {"productos_reintentados": n_reintentar, "nuevos_ok": nuevos_ok}

    except JobCancelledError:
        logger.info("retry_job cancelado por el usuario", extra={"job_id": job_id})
        return {"cancelado": True}

    except Exception as exc:
        logger.error("Error inesperado en retry_job", exc_info=exc, extra={"job_id": job_id})
        try:
            raw_err = redis_client.get(_JOB_KEY.format(job_id=job_id))
            if raw_err:
                js_err = JobStatus.model_validate_json(raw_err)
                js_err.estado = EstadoJob.FALLIDO
                js_err.error = str(exc)
                js_err.mensaje = "El reintento falló."
                js_err.actualizado_en = datetime.utcnow()
                _actualizar_estado(redis_client, js_err)
        except Exception as inner_exc:
            logger.warning(
                "No se pudo actualizar el estado FALLIDO tras error en retry_job",
                exc_info=inner_exc,
                extra={"job_id": job_id},
            )
        return {"error": str(exc)}

    finally:
        redis_client.close()


@celery_app.task(name="cleanup_stale_candidates")
def cleanup_stale_candidates() -> dict:
    """
    Limpia directorios candidates/ de jobs que han expirado por TTL.

    Se ejecuta cada hora (beat schedule).
    Busca en storage todos los directorios job_*/candidates/ y valida:
    - Si el job aún existe en Redis y no ha expirado el TTL
    - Si no, llamar storage.cleanup_candidates() para eliminar

    Returns:
        Dict con jobs_cleaned y files_deleted.

    :author: BenjaminDTS
    """
    from pathlib import Path

    from services.storage_service import get_storage_service  # noqa: PLC0415

    redis_client = _get_redis_client()
    settings = get_settings()
    storage = get_storage_service()

    jobs_cleaned = 0
    files_deleted = 0

    try:
        # Iterar directorios bajo base_dir buscando candidates/
        base = Path(settings.output_dir)
        if not base.exists():
            return {"jobs_cleaned": 0, "files_deleted": 0}

        for job_dir in base.iterdir():
            if not job_dir.is_dir():
                continue

            job_id = job_dir.name
            candidates_dir = job_dir / "candidates"

            if not candidates_dir.exists():
                continue

            # Verificar si el job aún está en Redis y en PENDIENTE_SELECCION_FOTOS
            job_key = f"job:{job_id}"
            job_json = redis_client.get(job_key)

            if job_json:
                try:
                    job_data = json.loads(job_json)
                    estado = job_data.get("estado")
                    # Si aún está en PENDIENTE_SELECCION_FOTOS, no limpiar
                    if estado == "pendiente_seleccion_fotos":
                        continue
                except Exception:
                    pass

            # Job expirado o no en state correcto — limpiar
            try:
                count = storage.cleanup_candidates(job_id)
                jobs_cleaned += 1
                files_deleted += count
                logger.info(
                    "Directorio candidates/ limpiado por TTL",
                    extra={"job_id": job_id, "files": count},
                )
            except Exception as exc:
                logger.warning(
                    "Error limpiando candidates/ del job",
                    exc_info=exc,
                    extra={"job_id": job_id},
                )

        logger.info(
            "Limpieza de candidates/ completada",
            extra={"jobs_cleaned": jobs_cleaned, "files_deleted": files_deleted},
        )
        return {"jobs_cleaned": jobs_cleaned, "files_deleted": files_deleted}

    finally:
        redis_client.close()


@celery_app.task(name="cleanup_image_cache_orphans")
def cleanup_image_cache_orphans() -> dict:
    """
    Elimina del índice SQLite las entradas cuya imagen en disco ya no existe.

    Se ejecuta semanalmente (domingos 03:00 UTC) para limpiar entradas
    de jobs limpiados o archivos borrados manualmente.

    Returns:
        Dict con orphans_removed.

    :author: BenjaminDTS
    """
    settings = get_settings()

    if not settings.image_cache_enabled:
        logger.info("Caché de imágenes deshabilitada, limpieza omitida.")
        return {"orphans_removed": 0}

    from services.scraper.image_cache import ImageCacheService  # noqa: PLC0415

    cache = ImageCacheService(settings.image_cache_db)
    removed = cache.cleanup_orphans()

    logger.info(
        "Limpieza de huérfanos del caché de imágenes completada",
        extra={"orphans_removed": removed},
    )
    return {"orphans_removed": removed}
