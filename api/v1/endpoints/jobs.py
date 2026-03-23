"""
Endpoints HTTP y WebSocket para la gestión de trabajos de scraping.

Rutas expuestas:
  POST   /api/v1/jobs          — Crear un nuevo job con CSV + configuración
  GET    /api/v1/jobs/{job_id} — Consultar el estado de un job
  WS     /api/v1/jobs/{job_id}/ws — Stream de progreso en tiempo real

Este módulo solo maneja HTTP: valida, delega a workers y devuelve respuesta.
Ninguna lógica de negocio vive aquí.

:author: BenjaminDTS
:version: 1.0.0
"""

import json
import uuid
from datetime import datetime
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse
from loguru import logger

from api.core.config import get_settings
from api.core.security import limiter
from api.v1.schemas.job import (
    ColumnMapping,
    EstadoJob,
    JobCreate,
    JobProgressEvent,
    JobResponse,
    JobStatus,
    ModosBusqueda,
    SearchConfig,
)

router = APIRouter(prefix="/jobs", tags=["Jobs"])
settings = get_settings()

# Clave Redis donde se almacena el estado del job: job:{job_id}
_JOB_KEY = "job:{job_id}"
# Tiempo de vida de la clave en Redis (igual al TTL de archivos)
_KEY_TTL = settings.file_ttl_seconds


async def _get_redis() -> aioredis.Redis:
    """
    Crea una conexión asíncrona a Redis.

    Returns:
        Cliente Redis asíncrono.

    Raises:
        HTTPException 503: si Redis no está disponible.
    """
    try:
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await client.ping()
        return client
    except Exception as exc:
        logger.error("No se pudo conectar a Redis", exc_info=exc)
        raise HTTPException(status_code=503, detail="Servicio no disponible temporalmente.")


async def _get_job_status(redis: aioredis.Redis, job_id: str) -> JobStatus:
    """
    Recupera el estado de un job desde Redis.

    Args:
        redis: cliente Redis asíncrono.
        job_id: identificador del job como string.

    Returns:
        JobStatus deserializado.

    Raises:
        HTTPException 404: si el job no existe en Redis.
    """
    raw = await redis.get(_JOB_KEY.format(job_id=job_id))
    if raw is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' no encontrado.")
    return JobStatus.model_validate_json(raw)


@router.post(
    "",
    response_model=JobResponse,
    status_code=202,
    summary="Crear un nuevo trabajo de scraping",
)
@limiter.limit("10/minute")
async def crear_job(
    request: Request,  # requerido por slowapi para extraer la IP
    file: Annotated[UploadFile, File(description="Archivo CSV con el inventario de productos.")],
    modo: Annotated[
        ModosBusqueda,
        Form(description="Modo de búsqueda de imágenes."),
    ] = ModosBusqueda.NOMBRE_MARCA,
    imagenes_por_producto: Annotated[
        int,
        Form(ge=1, le=20, description="Imágenes a descargar por producto."),
    ] = 5,
    generar_descripciones: Annotated[
        bool,
        Form(description="Activar generación de descripciones con IA (Fase 5)."),
    ] = False,
    columna_codigo: Annotated[
        str,
        Form(description="Columna del CSV que contiene el código único del producto."),
    ] = "codigo",
    columna_ean: Annotated[
        str,
        Form(description="Columna del CSV que contiene el EAN/código de barras."),
    ] = "ean",
    columna_nombre: Annotated[
        str,
        Form(description="Columna del CSV que contiene el nombre del producto."),
    ] = "nombre",
    columna_marca: Annotated[
        str,
        Form(description="Columna del CSV que contiene la marca del producto."),
    ] = "marca",
    columna_categoria: Annotated[
        str,
        Form(description="Columna del CSV que contiene la categoría del producto (opcional)."),
    ] = "categoria",
    columna_nombre_foto: Annotated[
        str,
        Form(
            description=(
                "Columna del CSV cuyo valor se usa para nombrar los archivos de imagen. "
                "Vacío = usar columna de código."
            )
        ),
    ] = "",
    query_personalizada: Annotated[
        str,
        Form(description="Plantilla de query para el modo personalizado (con {nombre}, {marca}, etc.)."),
    ] = "",
) -> JSONResponse:
    """
    Recibe un CSV de inventario, encola el trabajo de scraping y devuelve el job_id.

    El procesamiento es asíncrono: la respuesta 202 incluye el job_id para
    consultar el progreso vía GET /jobs/{job_id} o WS /jobs/{job_id}/ws.

    Args:
        request: objeto Request de FastAPI (requerido por slowapi).
        file: archivo CSV multipart con los productos a procesar.
        modo: modo de construcción de la query de búsqueda.
        imagenes_por_producto: número de imágenes a descargar por producto.
        generar_descripciones: activa el pipeline de IA de la Fase 5.
        columna_codigo: columna del CSV que actúa como código único.
        columna_ean: columna del CSV con el EAN del producto.
        columna_nombre: columna del CSV con el nombre del producto.
        columna_marca: columna del CSV con la marca del producto.

    Returns:
        JSONResponse 202 con job_id y URL de seguimiento.

    Raises:
        HTTPException 400: si el archivo no es CSV o está vacío.
        HTTPException 503: si Redis o Celery no están disponibles.
    """
    # Validar tipo MIME del CSV en la frontera de entrada
    if file.content_type not in (
        "text/csv",
        "application/csv",
        "text/plain",
        "application/vnd.ms-excel",
        "application/octet-stream",
    ):
        raise HTTPException(
            status_code=400,
            detail="El archivo debe ser un CSV (text/csv).",
        )

    contenido = await file.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo CSV está vacío.")

    job_id = str(uuid.uuid4())

    config = SearchConfig(
        modo=modo,
        imagenes_por_producto=imagenes_por_producto,
        generar_descripciones=generar_descripciones,
        query_personalizada=query_personalizada or None,
        column_mapping=ColumnMapping(
            columna_codigo=columna_codigo,
            columna_ean=columna_ean,
            columna_nombre=columna_nombre,
            columna_marca=columna_marca,
            columna_categoria=columna_categoria,
            columna_nombre_foto=columna_nombre_foto,
        ),
    )

    # Crear estado inicial del job en Redis
    job_status = JobStatus(
        job_id=uuid.UUID(job_id),  # type: ignore[arg-type]
        estado=EstadoJob.PENDIENTE,
        mensaje="Trabajo recibido, en cola de procesamiento.",
    )
    redis = await _get_redis()
    await redis.set(
        _JOB_KEY.format(job_id=job_id),
        job_status.model_dump_json(),
        ex=_KEY_TTL,
    )
    await redis.aclose()

    # Encolar tarea Celery
    try:
        from workers.tasks import ejecutar_scraping
        ejecutar_scraping.apply_async(
            args=[job_id, contenido.decode("utf-8-sig", errors="replace"), config.model_dump()],
            task_id=job_id,
        )
    except Exception as exc:
        logger.error("Error al encolar el job en Celery", exc_info=exc, extra={"job_id": job_id})
        raise HTTPException(status_code=503, detail="No se pudo encolar el trabajo.") from exc

    logger.info("Job encolado", extra={"job_id": job_id, "modo": modo.value})

    return JSONResponse(
        status_code=202,
        content={
            "success": True,
            "data": {
                "job_id": job_id,
                "estado": EstadoJob.PENDIENTE.value,
                "ws_url": f"/api/v1/jobs/{job_id}/ws",
            },
            "message": "Trabajo encolado correctamente.",
        },
    )


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Consultar el estado de un trabajo",
)
async def obtener_estado_job(job_id: str) -> JSONResponse:
    """
    Devuelve el estado actual de un trabajo de scraping.

    Args:
        job_id: identificador UUID del trabajo.

    Returns:
        JSONResponse con el estado completo del job.

    Raises:
        HTTPException 404: si el job no existe o ha expirado.
    """
    redis = await _get_redis()
    try:
        status = await _get_job_status(redis, job_id)
    finally:
        await redis.aclose()

    return JSONResponse(
        content={
            "success": True,
            "data": json.loads(status.model_dump_json()),
            "message": status.mensaje,
        }
    )


@router.post(
    "/{job_id}/cancel",
    response_model=JobResponse,
    status_code=200,
    summary="Cancelar un trabajo en curso",
)
async def cancelar_job(job_id: str) -> JSONResponse:
    """
    Cancela un trabajo que esté en estado PENDIENTE o EN_PROCESO.

    Actualiza el estado a CANCELADO en Redis. El worker detectará el cambio
    en su siguiente iteración y detendrá el pipeline limpiamente.

    Args:
        job_id: identificador UUID del trabajo a cancelar.

    Returns:
        JSONResponse 200 confirmando la cancelación.

    Raises:
        HTTPException 404: si el job no existe.
        HTTPException 409: si el job ya terminó (no se puede cancelar).
    """
    redis = await _get_redis()
    try:
        status = await _get_job_status(redis, job_id)

        if status.estado not in (EstadoJob.PENDIENTE, EstadoJob.EN_PROCESO):
            raise HTTPException(
                status_code=409,
                detail=f"El trabajo ya terminó con estado '{status.estado.value}' y no puede cancelarse.",
            )

        status.estado = EstadoJob.CANCELADO
        status.mensaje = "Trabajo cancelado por el usuario."
        status.actualizado_en = datetime.utcnow()
        await redis.set(
            _JOB_KEY.format(job_id=job_id),
            status.model_dump_json(),
            ex=_KEY_TTL,
        )
    finally:
        await redis.aclose()

    logger.info("Job cancelado por el usuario", extra={"job_id": job_id})

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {"job_id": job_id, "estado": EstadoJob.CANCELADO.value},
            "message": "Trabajo cancelado correctamente.",
        },
    )


@router.websocket("/{job_id}/ws")
async def websocket_progreso(websocket: WebSocket, job_id: str) -> None:
    """
    WebSocket de progreso en tiempo real para un trabajo de scraping.

    Emite un evento JobProgressEvent cada segundo mientras el job está activo.
    Cierra la conexión automáticamente cuando el job termina (COMPLETADO / FALLIDO).

    Args:
        websocket: conexión WebSocket establecida.
        job_id: identificador UUID del trabajo a monitorizar.
    """
    import asyncio

    await websocket.accept()
    redis = await _get_redis()

    try:
        while True:
            try:
                raw = await redis.get(_JOB_KEY.format(job_id=job_id))
            except Exception as exc:
                logger.error(
                    "Error leyendo estado del job desde Redis",
                    exc_info=exc,
                    extra={"job_id": job_id},
                )
                await websocket.send_json({"error": "Error interno al leer el estado."})
                break

            if raw is None:
                await websocket.send_json({"error": f"Job '{job_id}' no encontrado."})
                break

            status = JobStatus.model_validate_json(raw)
            event = JobProgressEvent(
                job_id=job_id,
                estado=status.estado,
                porcentaje=status.porcentaje,
                productos_procesados=status.productos_procesados,
                total_productos=status.total_productos,
                imagenes_descargadas=status.imagenes_descargadas,
                imagenes_fallidas=status.imagenes_fallidas,
                descripciones_generadas=status.descripciones_generadas,
                mensaje=status.mensaje,
                error=status.error,
            )
            await websocket.send_json(event.model_dump())

            # Cerrar cuando el job ha terminado
            if status.estado in (EstadoJob.COMPLETADO, EstadoJob.FALLIDO, EstadoJob.CANCELADO):
                break

            await asyncio.sleep(1)

    except WebSocketDisconnect:
        logger.info("Cliente WebSocket desconectado", extra={"job_id": job_id})
    finally:
        await redis.aclose()
        await websocket.close()
