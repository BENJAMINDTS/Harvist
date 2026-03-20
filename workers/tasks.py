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
from api.v1.schemas.job import EstadoJob, JobStatus, SearchConfig
from services.csv_parser import CsvParserError
from services.scraper.pipeline import ScrapingPipeline
from workers.celery_app import celery_app

# Logger de Celery (no sustituye a loguru — es complementario para el worker)
task_logger = get_task_logger(__name__)

_JOB_KEY = "job:{job_id}"


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

    logger.info("Tarea Celery iniciada", extra={"job_id": job_id})

    def _callback_progreso(
        jid: str,
        procesados: int,
        total: int,
        img_ok: int,
        img_fail: int,
    ) -> None:
        """
        Actualiza el estado del job en Redis tras procesar cada producto.

        Args:
            jid: job_id.
            procesados: productos procesados hasta ahora.
            total: total de productos del CSV.
            img_ok: imágenes descargadas exitosamente.
            img_fail: imágenes que fallaron.
        """
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

    try:
        pipeline = ScrapingPipeline(job_id=job_id, config=config)
        resumen = pipeline.ejecutar(
            contenido_csv=contenido_csv,
            callback=_callback_progreso,
        )

        # Actualizar estado final: COMPLETADO
        job_status.estado = EstadoJob.COMPLETADO
        job_status.total_productos = resumen["total_productos"]
        job_status.imagenes_descargadas = resumen["imagenes_descargadas"]
        job_status.imagenes_fallidas = resumen["imagenes_fallidas"]
        job_status.completado_en = datetime.utcnow()
        job_status.actualizado_en = datetime.utcnow()
        job_status.mensaje = (
            f"Completado: {resumen['imagenes_descargadas']} imágenes descargadas "
            f"de {resumen['total_productos']} productos."
        )
        _actualizar_estado(redis_client, job_status)

        logger.info(
            "Tarea Celery completada",
            extra={"job_id": job_id, **{k: v for k, v in resumen.items() if k != "errores_csv"}},
        )
        return resumen

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
