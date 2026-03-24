"""
Tareas Celery del Proyecto Scraping.

Este módulo envuelve los servicios de negocio en tareas asíncronas Celery.
No contiene lógica de dominio — solo integración con Celery y actualización
del estado del job en Redis.

:author: BenjaminDTS
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

    try:
        if config.tipo_job == TipoJob.DESCRIPCIONES:
            from services.ai.description_pipeline import DescripcionPipeline  # noqa: PLC0415
            pipeline_desc = DescripcionPipeline(job_id=job_id, config=config, carpeta_job_id=carpeta_job_id)
            resumen = pipeline_desc.ejecutar(
                contenido_csv=contenido_csv,
                callback=_callback_descripciones,
                offset_productos=offset_productos,
            )
        else:
            pipeline_fotos = ScrapingPipeline(job_id=job_id, config=config, carpeta_job_id=carpeta_job_id)
            resumen = pipeline_fotos.ejecutar(
                contenido_csv=contenido_csv,
                callback=_callback_fotos,
                offset_productos=offset_productos,
            )

        # Actualizar estado final: COMPLETADO
        job_status.estado = EstadoJob.COMPLETADO
        job_status.total_productos = resumen["total_productos"]
        job_status.imagenes_descargadas = resumen.get("imagenes_descargadas", 0)
        job_status.imagenes_fallidas = resumen.get("imagenes_fallidas", 0)
        job_status.descripciones_generadas = resumen.get("descripciones_generadas", 0)
        job_status.completado_en = datetime.utcnow()
        job_status.actualizado_en = datetime.utcnow()
        if config.tipo_job == TipoJob.DESCRIPCIONES:
            job_status.mensaje = (
                f"Completado: {resumen.get('descripciones_generadas', 0)} descripciones generadas "
                f"de {resumen['total_productos']} productos."
            )
        else:
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
