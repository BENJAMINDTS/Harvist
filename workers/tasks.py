"""
Tareas Celery del Proyecto Scraping.

Este módulo envuelve los servicios de negocio en tareas asíncronas Celery.
No contiene lógica de dominio — solo integración con Celery y actualización
del estado del job en Redis.

:author: BenjaminDTS
:author: Carlitos6712
:version: 1.0.0
"""

import json
import uuid
from datetime import datetime

import redis as sync_redis
from celery.utils.log import get_task_logger
from loguru import logger

from api.core.config import get_settings
from api.v1.schemas.job import EstadoJob, JobStatus, SearchConfig, TipoJob
from services.csv_parser import CsvParserError
from services.scraper.pipeline import ScrapingPipeline
from workers.celery_app import celery_app

# Logger de Celery (no sustituye a loguru — es complementario para el worker)
task_logger = get_task_logger(__name__)

_JOB_KEY = "job:{job_id}"
_BRANDS_PENDING_KEY = "job:{job_id}:brands_pending"
_PHOTOS_PENDING_KEY = "job:{job_id}:photos_pending"


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

    def _callback_fotos(
        jid: str,
        procesados: int,
        total: int,
        img_ok: int,
        img_fail: int,
    ) -> None:
        """
        Actualiza el estado del job de fotos en Redis tras procesar cada producto.

        Args:
            jid: job_id.
            procesados: productos procesados hasta ahora.
            total: total de productos del CSV.
            img_ok: imágenes descargadas exitosamente.
            img_fail: imágenes que fallaron.

        Raises:
            JobCancelledError: si el job fue cancelado desde la API.
        """
        raw = redis_client.get(_JOB_KEY.format(job_id=jid))
        if raw:
            current = JobStatus.model_validate_json(raw)
            if current.estado == EstadoJob.CANCELADO:
                raise JobCancelledError(f"Job {jid} cancelado por el usuario.")

        job_status.total_productos = total
        job_status.productos_procesados = procesados
        job_status.imagenes_descargadas = img_ok
        job_status.imagenes_fallidas = img_fail
        job_status.actualizado_en = datetime.utcnow()
        job_status.mensaje = (
            f"Procesando producto {procesados}/{total} — "
            f"{img_ok} imágenes descargadas."
        )
        _actualizar_estado(redis_client, job_status)

    def _callback_descripciones(
        jid: str,
        procesados: int,
        total: int,
        descripciones_ok: int,
    ) -> None:
        """
        Actualiza el estado del job de descripciones en Redis tras cada producto.

        Args:
            jid: job_id.
            procesados: productos procesados hasta ahora.
            total: total de productos del CSV.
            descripciones_ok: descripciones generadas exitosamente.

        Raises:
            JobCancelledError: si el job fue cancelado desde la API.
        """
        raw = redis_client.get(_JOB_KEY.format(job_id=jid))
        if raw:
            current = JobStatus.model_validate_json(raw)
            if current.estado == EstadoJob.CANCELADO:
                raise JobCancelledError(f"Job {jid} cancelado por el usuario.")

        job_status.total_productos = total
        job_status.productos_procesados = procesados
        job_status.descripciones_generadas = descripciones_ok
        job_status.actualizado_en = datetime.utcnow()
        job_status.mensaje = (
            f"Generando descripción {procesados}/{total} — "
            f"{descripciones_ok} completadas."
        )
        _actualizar_estado(redis_client, job_status)

    def _callback_marcas(
        jid: str,
        procesadas: int,
        total: int,
        exitosas: int,
    ) -> None:
        """
        Actualiza el estado del job de marcas en Redis tras procesar cada marca.

        Args:
            jid: job_id.
            procesadas: marcas procesadas hasta ahora.
            total: total de marcas únicas extraídas del CSV.
            exitosas: marcas procesadas con éxito.

        Raises:
            JobCancelledError: si el job fue cancelado desde la API.
        """
        raw = redis_client.get(_JOB_KEY.format(job_id=jid))
        if raw:
            current = JobStatus.model_validate_json(raw)
            if current.estado == EstadoJob.CANCELADO:
                raise JobCancelledError(f"Job {jid} cancelado por el usuario.")

        job_status.total_productos = total
        job_status.productos_procesados = procesadas
        job_status.marcas_procesadas = exitosas
        job_status.actualizado_en = datetime.utcnow()
        job_status.mensaje = (
            f"Procesando marca {procesadas}/{total} — "
            f"{exitosas} completadas."
        )
        _actualizar_estado(redis_client, job_status)

    def _callback_traducciones(
        jid: str,
        idioma: str,
        total: int,
        traducciones_ok: int,
    ) -> None:
        """
        Actualiza el estado del job de traducciones en Redis tras procesar cada idioma.

        Args:
            jid: job_id.
            idioma: código ISO 639-1 del idioma destino.
            total: total de productos a traducir.
            traducciones_ok: traducciones generadas exitosamente en este idioma.

        Raises:
            JobCancelledError: si el job fue cancelado desde la API.
        """
        raw = redis_client.get(_JOB_KEY.format(job_id=jid))
        if raw:
            current = JobStatus.model_validate_json(raw)
            if current.estado == EstadoJob.CANCELADO:
                raise JobCancelledError(f"Job {jid} cancelado por el usuario.")

        job_status.traducciones_generadas[idioma] = traducciones_ok
        job_status.actualizado_en = datetime.utcnow()
        job_status.mensaje = (
            f"Traduciendo al {idioma}: {traducciones_ok}/{total} completadas."
        )
        _actualizar_estado(redis_client, job_status)

    def _callback_seo(
        jid: str,
        procesados: int,
        total: int,
        seo_ok: int,
    ) -> None:
        """
        Actualiza el estado del job de SEO en Redis tras procesar cada producto.

        Args:
            jid: job_id.
            procesados: productos procesados hasta ahora.
            total: total de productos del CSV.
            seo_ok: textos SEO generados exitosamente.

        Raises:
            JobCancelledError: si el job fue cancelado desde la API.
        """
        raw = redis_client.get(_JOB_KEY.format(job_id=jid))
        if raw:
            current = JobStatus.model_validate_json(raw)
            if current.estado == EstadoJob.CANCELADO:
                raise JobCancelledError(f"Job {jid} cancelado por el usuario.")

        job_status.total_productos = total
        job_status.productos_procesados = procesados
        job_status.seo_generados = seo_ok
        job_status.actualizado_en = datetime.utcnow()
        job_status.mensaje = (
            f"Generando SEO {procesados}/{total} — "
            f"{seo_ok} completados."
        )
        _actualizar_estado(redis_client, job_status)

    try:
        if config.tipo_job == TipoJob.DESCRIPCIONES:
            from services.ai.description_pipeline import DescripcionPipeline  # noqa: PLC0415
            pipeline_desc = DescripcionPipeline(job_id=job_id, config=config, carpeta_job_id=carpeta_job_id)
            resumen = pipeline_desc.ejecutar(
                contenido_csv=contenido_csv,
                callback=_callback_descripciones,
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
                    _callback_traducciones(
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
                callback=_callback_seo,
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
                callback=_callback_marcas,
                offset_productos=offset_productos,
            )
        else:
            pipeline_fotos = ScrapingPipeline(job_id=job_id, config=config, carpeta_job_id=carpeta_job_id)
            resumen = pipeline_fotos.ejecutar(
                contenido_csv=contenido_csv,
                callback=_callback_fotos,
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
                        "estado": EstadoJob.PENDIENTE_SELECCION_FOTOS,
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
            job_status.mensaje = (
                f"Completado: {resumen.get('imagenes_descargadas', 0)} imágenes descargadas "
                f"de {resumen['total_productos']} productos."
            )
        _actualizar_estado(redis_client, job_status)

        logger.info(
            "Tarea Celery completada",
            extra={"job_id": job_id, **{k: v for k, v in resumen.items() if k != "errores_csv"}},
        )
        return resumen

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
