"""
Endpoints HTTP y WebSocket para la gestión de trabajos de scraping.

Rutas expuestas:
  POST   /api/v1/jobs                                          — Crear un nuevo job con CSV + configuración
  GET    /api/v1/jobs/{job_id}                                 — Consultar el estado de un job
  GET    /api/v1/jobs/{job_id}/brands                          — Obtener marcas resueltas como JSON (Fase 6.4)
  GET    /api/v1/jobs/{job_id}/brands/pending                  — Obtener marcas pendientes de validación (Fase 7.4)
  POST   /api/v1/jobs/{job_id}/brands/validate                 — Validar marcas nuevas (Fase 7.4)
  GET    /api/v1/jobs/{job_id}/photos                          — Obtener productos con fotos candidatas (Fase 7.5)
  POST   /api/v1/jobs/{job_id}/photos/confirm                  — Confirmar selección de fotos y generar ZIP (Fase 7.5)
  POST   /api/v1/jobs/{job_id}/cancel                          — Cancelar un job en curso
  POST   /api/v1/jobs/{job_id}/resume                          — Reanudar un job cancelado o fallido
  PATCH  /api/v1/jobs/{job_id}/descriptions/{codigo}           — Revisar (aprobar/rechazar/editar) una descripción (Fase 7.3)
  GET    /api/v1/jobs/{job_id}/descriptions/review             — Estado de revisión de todas las descripciones (Fase 7.3)
  WS     /api/v1/jobs/{job_id}/ws                              — Stream de progreso en tiempo real

Este módulo solo maneja HTTP: valida, delega a workers y devuelve respuesta.
Ninguna lógica de negocio vive aquí.

:author: BenjaminDTS
:author: Carlitos6712
:version: 1.5.0
"""

import csv
import io
import json
import threading as _threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse
from loguru import logger

from api.core.config import get_settings
from api.core.security import limiter
from services.storage_service import get_storage_service
from api.v1.schemas.job import (
    BrandValidationAction,
    BrandValidationRequest,
    CandidateInfo,
    ColumnMapping,
    DescriptionReviewEntry,
    DescriptionReviewRequest,
    DescriptionReviewState,
    EstadoJob,
    JobCreate,
    JobProgressEvent,
    JobResponse,
    JobStatus,
    ModosBusqueda,
    PhotoSelectionItem,
    PhotoSelectionRequest,
    ProductPhotos,
    ReviewAction,
    ReviewStatus,
    SearchConfig,
    TipoJob,
)

router = APIRouter(prefix="/jobs", tags=["Jobs"])
settings = get_settings()

# Clave Redis donde se almacena el estado del job: job:{job_id}
_JOB_KEY = "job:{job_id}"
# Clave Redis donde se almacena el CSV original para poder reanudar el job
_JOB_CSV_KEY = "job:{job_id}:csv"
# Clave Redis donde se almacena la configuración original del job (JSON)
_JOB_CONFIG_KEY = "job:{job_id}:config"
# Tiempo de vida de la clave en Redis (igual al TTL de archivos)
_KEY_TTL = settings.file_ttl_seconds
# Clave Redis donde se almacena el estado de revisión de una descripción individual
_JOB_REVIEW_KEY = "job:{job_id}:review:{codigo}"
# Clave Redis donde se almacenan las marcas pendientes de validación (Fase 7.4)
_BRANDS_PENDING_KEY = "job:{job_id}:brands_pending"
# Lock a nivel de módulo para proteger escrituras concurrentes en brand_cache.json
_BRAND_CACHE_WRITE_LOCK: _threading.Lock = _threading.Lock()


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
    tipo_job: Annotated[
        TipoJob,
        Form(description="Tipo de trabajo: 'fotos' (scraping) o 'descripciones' (Claude API). Mutuamente excluyentes."),
    ] = TipoJob.FOTOS,
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
    groq_api_key_usuario: Annotated[
        str,
        Form(description="API key de Groq del usuario. Tiene prioridad sobre GROQ_API_KEY del .env."),
    ] = "",
    store_type_usuario: Annotated[
        str,
        Form(description="Tipo de tienda para el prompt de IA (ej: 'tiendas de mascotas'). Vacío = usa el del .env."),
    ] = "",
    target_languages: Annotated[
        list[str],
        Form(
            description=(
                "Idiomas destino para traducción automática (Fase 7.2). "
                "Enviar un valor por idioma. Valores permitidos: es, en, fr, de, it, pt."
            )
        ),
    ] = None,
    validate_brands: Annotated[
        str,
        Form(
            description=(
                "Si true/1, el job espera validación manual de marcas nuevas antes de escribirlas "
                "en brand_cache.json (Fase 7.4). Solo aplica con tipo_job=marcas."
            )
        ),
    ] = "false",
    select_photos: Annotated[
        str,
        Form(
            description=(
                "Si true/1, el job descarga todas las candidatas por producto y espera selección "
                "manual del usuario antes de generar el ZIP (Fase 7.5). Solo aplica con tipo_job=fotos."
            )
        ),
    ] = "false",
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
    ):
        raise HTTPException(
            status_code=400,
            detail="El archivo debe ser un CSV (text/csv).",
        )

    contenido = await file.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo CSV está vacío.")

    job_id = str(uuid.uuid4())

    # Form fields send strings; coerce explicitly to bool
    if isinstance(select_photos, bool):
        _select_photos = select_photos
        _validate_brands = validate_brands if isinstance(validate_brands, bool) else False
    else:
        _select_photos = str(select_photos).lower().strip() in ("true", "1", "yes", "on")
        _validate_brands = str(validate_brands).lower().strip() in ("true", "1", "yes", "on")

    logger.debug(
        "Parámetros recibidos en crear_job",
        extra={
            "select_photos_raw": select_photos,
            "select_photos_bool": _select_photos,
            "validate_brands_raw": validate_brands,
            "validate_brands_bool": _validate_brands,
        },
    )

    config = SearchConfig(
        tipo_job=tipo_job,
        modo=modo,
        imagenes_por_producto=imagenes_por_producto,
        query_personalizada=query_personalizada or None,
        groq_api_key_usuario=groq_api_key_usuario,
        store_type_usuario=store_type_usuario,
        target_languages=target_languages or [],
        validate_brands=_validate_brands,
        select_photos=_select_photos,
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
    csv_str = contenido.decode("utf-8-sig", errors="replace")
    redis = await _get_redis()
    await redis.set(
        _JOB_KEY.format(job_id=job_id),
        job_status.model_dump_json(),
        ex=_KEY_TTL,
    )
    # Persistir CSV y config para permitir reanudar el job más adelante
    await redis.set(
        _JOB_CSV_KEY.format(job_id=job_id),
        csv_str,
        ex=_KEY_TTL,
    )
    await redis.set(
        _JOB_CONFIG_KEY.format(job_id=job_id),
        json.dumps(config.model_dump()),
        ex=_KEY_TTL,
    )
    await redis.aclose()

    # Encolar tarea Celery
    try:
        from workers.tasks import ejecutar_scraping
        ejecutar_scraping.apply_async(
            args=[job_id, csv_str, config.model_dump()],
            task_id=job_id,
        )
    except Exception as exc:
        logger.error("Error al encolar el job en Celery", exc_info=exc, extra={"job_id": job_id})
        raise HTTPException(status_code=503, detail="No se pudo encolar el trabajo.") from exc

    logger.info("Job encolado", extra={"job_id": job_id, "tipo_job": tipo_job.value, "modo": modo.value})

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


@router.get(
    "/{job_id}/brands",
    response_model=JobResponse,
    summary="(Fase 6.4) Obtener marcas resueltas como JSON",
)
async def obtener_marcas_job(job_id: str) -> JSONResponse:
    """
    Devuelve el listado de marcas resueltas para un job completado.

    Lee marcas.csv del storage y lo serializa como JSON, incluyendo contadores
    de marcas resueltas y sin resolver para el panel de visualización.

    Args:
        job_id: identificador UUID del trabajo.

    Returns:
        JSONResponse con brands (list), brands_resolved (int) y brands_not_found (int).

    Raises:
        HTTPException 404: si el job no existe en Redis.
        HTTPException 409: si el job no ha completado aún.
        HTTPException 404: si marcas.csv no existe en storage.
    """
    redis = await _get_redis()
    try:
        status = await _get_job_status(redis, job_id)
    finally:
        await redis.aclose()

    if status.estado != EstadoJob.COMPLETADO:
        raise HTTPException(
            status_code=409,
            detail=(
                f"El job aún no ha completado (estado: '{status.estado.value}'). "
                "Las marcas solo están disponibles cuando el job está COMPLETADO."
            ),
        )

    storage = get_storage_service()
    marcas_path = storage.get_job_dir(job_id) / "marcas.csv"

    if not marcas_path.exists():
        logger.warning("marcas.csv no encontrado para job", extra={"job_id": job_id})
        raise HTTPException(
            status_code=404,
            detail="El archivo de marcas no existe. El job puede no haber procesado marcas.",
        )

    try:
        raw = marcas_path.read_bytes().decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(raw))
        brands: list[dict[str, str | None]] = []
        brands_resolved = 0
        brands_not_found = 0

        for row in reader:
            brands.append({
                "codigo": row.get("codigo", ""),
                "ean": row.get("ean", ""),
                "brand_name": row.get("brand_name") or None,
                "manufacturer": row.get("manufacturer") or None,
                "source": row.get("source", "not_found"),
                "confidence": row.get("confidence", "low"),
            })
            if row.get("source") not in ("not_found", "ean_invalido"):
                brands_resolved += 1
            else:
                brands_not_found += 1

    except Exception as exc:
        logger.error(
            "Error leyendo marcas.csv",
            exc_info=exc,
            extra={"job_id": job_id},
        )
        raise HTTPException(
            status_code=500,
            detail="Error interno al leer el archivo de marcas.",
        ) from exc

    logger.info(
        "Marcas leídas",
        extra={"job_id": job_id, "total": len(brands), "resolved": brands_resolved},
    )

    return JSONResponse(
        content={
            "success": True,
            "data": {
                "brands": brands,
                "brands_resolved": brands_resolved,
                "brands_not_found": brands_not_found,
            },
            "message": f"{len(brands)} marcas procesadas: {brands_resolved} resueltas, {brands_not_found} sin resolver.",
        }
    )


@router.get(
    "/{job_id}/brands/pending",
    response_model=JobResponse,
    summary="Obtener marcas pendientes de validación (Fase 7.4)",
)
async def obtener_marcas_pendientes(job_id: str) -> JSONResponse:
    """
    Devuelve la lista de marcas nuevas pendientes de validación para un job.

    Args:
        job_id: identificador UUID del job en estado PENDIENTE_VALIDACION_MARCAS.

    Returns:
        JSONResponse con la lista de marcas pendientes.

    Raises:
        HTTPException 404: si el job no existe o no tiene marcas pendientes.
        HTTPException 409: si el job no está en PENDIENTE_VALIDACION_MARCAS.
    """
    redis = await _get_redis()
    try:
        job_status = await _get_job_status(redis, job_id)

        if job_status.estado != EstadoJob.PENDIENTE_VALIDACION_MARCAS:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"El job '{job_id}' no está en estado "
                    f"'{EstadoJob.PENDIENTE_VALIDACION_MARCAS.value}'."
                ),
            )

        pending_raw = await redis.get(_BRANDS_PENDING_KEY.format(job_id=job_id))
        if pending_raw is None:
            return JSONResponse(
                content={
                    "success": True,
                    "data": {"items": []},
                    "message": "Sin marcas pendientes.",
                }
            )

        # brands_pending is dict[str, dict[str, str]] = {prefijo: {brand_name, ean, source, confidence}}
        pending: dict[str, dict[str, str]] = json.loads(pending_raw)

        items = [
            {
                "prefijo": prefijo,
                "brand_name": entry.get("brand_name", ""),
                "ean": entry.get("ean", prefijo),
                "source": entry.get("source", ""),
                "confidence": entry.get("confidence", "low"),
            }
            for prefijo, entry in pending.items()
        ]

        return JSONResponse(
            content={
                "success": True,
                "data": {"items": items},
                "message": f"{len(items)} marcas pendientes de validación.",
            }
        )
    finally:
        await redis.aclose()


@router.post(
    "/{job_id}/brands/validate",
    response_model=JobResponse,
    summary="Validar marcas nuevas y persistirlas en brand_cache.json (Fase 7.4)",
)
async def validar_marcas(
    job_id: str,
    body: BrandValidationRequest,
) -> JSONResponse:
    """
    Procesa la decisión del usuario sobre las marcas nuevas detectadas en el job.

    Solo los items con action != 'reject' se escriben en brand_cache.json.
    Tras la validación, el job pasa a estado COMPLETADO.

    Args:
        job_id: identificador UUID del job en estado PENDIENTE_VALIDACION_MARCAS.
        body: lista de marcas con la decisión del usuario por cada una.

    Returns:
        JSONResponse con el resumen de marcas aceptadas, rechazadas y editadas.

    Raises:
        HTTPException 404: si el job no existe.
        HTTPException 409: si el job no está en PENDIENTE_VALIDACION_MARCAS.
        HTTPException 422: si el body es inválido (validado automáticamente por FastAPI).
    """
    redis = await _get_redis()
    try:
        job_status = await _get_job_status(redis, job_id)

        if job_status.estado != EstadoJob.PENDIENTE_VALIDACION_MARCAS:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"El job '{job_id}' no está en estado "
                    f"'{EstadoJob.PENDIENTE_VALIDACION_MARCAS.value}'. "
                    f"Estado actual: '{job_status.estado.value}'."
                ),
            )

        # Leer las marcas pendientes de Redis
        pending_raw = await redis.get(_BRANDS_PENDING_KEY.format(job_id=job_id))
        pending: dict[str, str] = json.loads(pending_raw) if pending_raw else {}

        # Procesar las decisiones del usuario
        accepted = 0
        rejected = 0
        edited = 0
        entries_to_write: dict[str, str] = {}

        for item in body.items:
            prefijo = item.ean[:7] if len(item.ean) >= 7 else item.ean

            if item.action == BrandValidationAction.REJECT:
                rejected += 1
                logger.info(
                    "Marca rechazada — no se escribe en brand_cache.json",
                    extra={
                        "job_id": job_id,
                        "ean": item.ean,
                        "prefijo": prefijo,
                        "brand_name": item.brand_name,
                        "action": item.action.value,
                    },
                )
            elif item.action == BrandValidationAction.EDIT:
                nombre_final = item.edited_name or item.brand_name
                entries_to_write[prefijo] = nombre_final
                edited += 1
                logger.info(
                    "Marca editada — se escribe en brand_cache.json",
                    extra={
                        "job_id": job_id,
                        "ean": item.ean,
                        "prefijo": prefijo,
                        "brand_name_original": item.brand_name,
                        "brand_name_editado": nombre_final,
                        "action": item.action.value,
                    },
                )
            else:  # ACCEPT
                entries_to_write[prefijo] = item.brand_name
                accepted += 1
                logger.info(
                    "Marca aceptada — se escribe en brand_cache.json",
                    extra={
                        "job_id": job_id,
                        "ean": item.ean,
                        "prefijo": prefijo,
                        "brand_name": item.brand_name,
                        "action": item.action.value,
                    },
                )

        # Persistir las entradas aceptadas/editadas en brand_cache.json
        merged: dict[str, str] = {}
        if entries_to_write:
            brand_cache_path = Path(settings.brand_cache_path)

            with _BRAND_CACHE_WRITE_LOCK:
                existing: dict[str, str] = {}
                if brand_cache_path.exists():
                    try:
                        existing = json.loads(
                            brand_cache_path.read_text(encoding="utf-8")
                        )
                    except (json.JSONDecodeError, OSError) as exc:
                        logger.error(
                            "Error leyendo brand_cache.json; se sobreescribirá",
                            exc_info=exc,
                            extra={"job_id": job_id},
                        )

                merged = {**existing, **entries_to_write}
                brand_cache_path.parent.mkdir(parents=True, exist_ok=True)
                brand_cache_path.write_text(
                    json.dumps(merged, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            logger.info(
                "brand_cache.json actualizado tras validación",
                extra={
                    "job_id": job_id,
                    "entradas_nuevas": len(entries_to_write),
                    "total_en_cache": len(merged),
                },
            )

        # Eliminar la clave de marcas pendientes de Redis
        await redis.delete(_BRANDS_PENDING_KEY.format(job_id=job_id))

        # Actualizar estado del job a COMPLETADO
        job_status.estado = EstadoJob.COMPLETADO
        job_status.completado_en = datetime.utcnow()
        job_status.actualizado_en = datetime.utcnow()
        job_status.marcas_pendientes_validacion = 0
        job_status.mensaje = (
            f"Validación de marcas completada: {accepted} aceptadas, "
            f"{edited} editadas, {rejected} rechazadas."
        )
        await redis.set(
            _JOB_KEY.format(job_id=job_id),
            job_status.model_dump_json(),
            ex=_KEY_TTL,
        )

        logger.info(
            "Validación de marcas completada",
            extra={
                "job_id": job_id,
                "accepted": accepted,
                "rejected": rejected,
                "edited": edited,
            },
        )

        return JSONResponse(
            content={
                "success": True,
                "data": {
                    "accepted": accepted,
                    "rejected": rejected,
                    "edited": edited,
                },
                "message": (
                    f"Validación completada: {accepted} marcas guardadas, "
                    f"{edited} editadas, {rejected} rechazadas."
                ),
            }
        )
    finally:
        await redis.aclose()


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


@router.post(
    "/{job_id}/resume",
    response_model=JobResponse,
    status_code=202,
    summary="Reanudar un trabajo cancelado o fallido",
)
async def reanudar_job(job_id: str) -> JSONResponse:
    """
    Crea un nuevo job que continúa desde donde el job original se detuvo.

    Lee el CSV y la configuración originales almacenados en Redis, determina
    cuántos productos ya fueron procesados y encola una nueva tarea Celery
    con ese offset para no repetir trabajo ya completado.

    Solo puede reanudarse un job en estado CANCELADO o FALLIDO. Si el CSV
    original ya expiró en Redis, se devuelve 404 con instrucciones al usuario.

    Args:
        job_id: identificador UUID del job original a reanudar.

    Returns:
        JSONResponse 202 con el nuevo job_id y URL de seguimiento.

    Raises:
        HTTPException 404: si el job no existe o el CSV original ha expirado.
        HTTPException 409: si el job no está en estado CANCELADO o FALLIDO.
        HTTPException 503: si Redis o Celery no están disponibles.
    """
    redis = await _get_redis()
    try:
        # Paso 1: verificar que el job original existe y está en estado reanudable
        status = await _get_job_status(redis, job_id)

        if status.estado not in (EstadoJob.CANCELADO, EstadoJob.FALLIDO):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Solo se puede reanudar un trabajo en estado CANCELADO o FALLIDO. "
                    f"Estado actual: '{status.estado.value}'."
                ),
            )

        # Paso 2: recuperar el CSV original
        csv_raw = await redis.get(_JOB_CSV_KEY.format(job_id=job_id))
        if csv_raw is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "El CSV original ya no está disponible (expiró). "
                    "Por favor, inicia un nuevo trabajo."
                ),
            )

        # Paso 3: recuperar la configuración original
        config_raw = await redis.get(_JOB_CONFIG_KEY.format(job_id=job_id))
        config_dict: dict = json.loads(config_raw) if config_raw else {}

        # Paso 4: offset = productos ya procesados en el job original
        offset_productos: int = status.productos_procesados or 0

        # Paso 5: crear el nuevo job
        nuevo_job_id = str(uuid.uuid4())
        config = SearchConfig.model_validate(config_dict)

        nuevo_status = JobStatus(
            job_id=uuid.UUID(nuevo_job_id),  # type: ignore[arg-type]
            estado=EstadoJob.PENDIENTE,
            mensaje=(
                f"Reanudando desde el producto {offset_productos + 1} "
                f"(job original: {job_id})."
            ),
        )

        # Paso 6: persistir estado, CSV y config del nuevo job en Redis
        await redis.set(
            _JOB_KEY.format(job_id=nuevo_job_id),
            nuevo_status.model_dump_json(),
            ex=_KEY_TTL,
        )
        await redis.set(
            _JOB_CSV_KEY.format(job_id=nuevo_job_id),
            csv_raw,
            ex=_KEY_TTL,
        )
        await redis.set(
            _JOB_CONFIG_KEY.format(job_id=nuevo_job_id),
            json.dumps(config_dict),
            ex=_KEY_TTL,
        )
    finally:
        await redis.aclose()

    # Paso 7: encolar la tarea Celery con el offset
    try:
        from workers.tasks import ejecutar_scraping
        ejecutar_scraping.apply_async(
            args=[nuevo_job_id, csv_raw, config.model_dump()],
            kwargs={"offset_productos": offset_productos, "carpeta_job_id": job_id},
            task_id=nuevo_job_id,
        )
    except Exception as exc:
        logger.error(
            "Error al encolar el job reanudado en Celery",
            exc_info=exc,
            extra={"job_id": nuevo_job_id, "job_original": job_id},
        )
        raise HTTPException(status_code=503, detail="No se pudo encolar el trabajo.") from exc

    logger.info(
        "Job reanudado",
        extra={
            "job_id": nuevo_job_id,
            "job_original": job_id,
            "offset_productos": offset_productos,
        },
    )

    return JSONResponse(
        status_code=202,
        content={
            "success": True,
            "data": {
                "job_id": nuevo_job_id,
                "job_original": job_id,
                "offset_productos": offset_productos,
                "estado": EstadoJob.PENDIENTE.value,
                "ws_url": f"/api/v1/jobs/{nuevo_job_id}/ws",
            },
            "message": f"Trabajo reanudado desde el producto {offset_productos + 1}.",
        },
    )


@router.patch(
    "/{job_id}/descriptions/{codigo}",
    response_model=dict,
    summary="Revisar una descripción generada por IA (aprobar / rechazar / editar)",
)
async def revisar_descripcion(
    job_id: str,
    codigo: str,
    body: DescriptionReviewRequest,
) -> JSONResponse:
    """
    Aplica una acción de revisión (approve / reject / edit) sobre una descripción individual.

    La acción se persiste en Redis bajo job:{job_id}:review:{codigo} con el mismo TTL
    que el job. Los contadores de revisión en JobStatus se actualizan en consecuencia.

    Args:
        job_id: identificador UUID del trabajo.
        codigo: código del producto cuya descripción se revisa.
        body: acción a aplicar y, si action='edit', el texto editado.

    Returns:
        JSONResponse con el DescriptionReviewState actualizado.

    Raises:
        HTTPException 404: si el job o el producto no existen.
        HTTPException 409: si el job no está en estado COMPLETADO.

    :author: Carlitos6712
    """
    redis = await _get_redis()
    try:
        job_status = await _get_job_status(redis, job_id)

        if job_status.estado != EstadoJob.COMPLETADO:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"El job '{job_id}' no está COMPLETADO (estado actual: {job_status.estado.value}). "
                    "Solo se pueden revisar descripciones de jobs completados."
                ),
            )

        # Verificar que el producto existe en descripciones.csv
        storage = get_storage_service()
        csv_path: Path = storage.get_job_dir(job_id) / "descripciones.csv"
        if not csv_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"No se encontraron descripciones para el job '{job_id}'.",
            )

        codigos_en_csv: set[str] = set()
        with open(csv_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("codigo"):
                    codigos_en_csv.add(row["codigo"])

        if codigo not in codigos_en_csv:
            raise HTTPException(
                status_code=404,
                detail=f"Producto '{codigo}' no encontrado en las descripciones del job '{job_id}'.",
            )

        review_key = _JOB_REVIEW_KEY.format(job_id=job_id, codigo=codigo)

        # Leer estado previo para ajustar contadores
        raw_review = await redis.get(review_key)
        old_status = ReviewStatus.PENDING
        if raw_review:
            old_state = DescriptionReviewState.model_validate_json(raw_review)
            old_status = old_state.status

        # Construir nuevo estado según la acción
        if body.action == ReviewAction.APPROVE:
            new_status = ReviewStatus.APPROVED
            edited_text = None
        elif body.action == ReviewAction.REJECT:
            new_status = ReviewStatus.REJECTED
            edited_text = None
        else:  # EDIT
            new_status = ReviewStatus.APPROVED
            edited_text = body.edited_text

        new_review_state = DescriptionReviewState(
            codigo=codigo,
            status=new_status,
            edited_text=edited_text,
        )

        # Persistir en Redis con TTL
        await redis.set(review_key, new_review_state.model_dump_json(), ex=_KEY_TTL)

        # Actualizar contadores en JobStatus
        raw_job = await redis.get(_JOB_KEY.format(job_id=job_id))
        if raw_job:
            job_status = JobStatus.model_validate_json(raw_job)

            # Revertir contadores del estado anterior
            if old_status == ReviewStatus.PENDING:
                job_status.revisiones_pendientes = max(0, job_status.revisiones_pendientes - 1)
            elif old_status == ReviewStatus.APPROVED:
                job_status.revisiones_aprobadas = max(0, job_status.revisiones_aprobadas - 1)
            elif old_status == ReviewStatus.REJECTED:
                job_status.revisiones_rechazadas = max(0, job_status.revisiones_rechazadas - 1)

            # Aplicar nuevo estado
            if new_status == ReviewStatus.APPROVED:
                job_status.revisiones_aprobadas += 1
            elif new_status == ReviewStatus.REJECTED:
                job_status.revisiones_rechazadas += 1

            job_status.actualizado_en = datetime.utcnow()
            await redis.set(
                _JOB_KEY.format(job_id=job_id),
                job_status.model_dump_json(),
                ex=_KEY_TTL,
            )

        logger.info(
            "Descripción revisada",
            extra={"job_id": job_id, "codigo": codigo, "action": body.action.value},
        )

        return JSONResponse(
            content={
                "success": True,
                "data": new_review_state.model_dump(),
                "message": f"Descripción '{codigo}' marcada como {new_status.value}.",
            }
        )

    finally:
        await redis.aclose()


@router.get(
    "/{job_id}/descriptions/review",
    response_model=dict,
    summary="Obtener estado de revisión de todas las descripciones (paginado)",
)
async def obtener_estado_revisiones(
    job_id: str,
    limit: int = 25,
    offset: int = 0,
) -> JSONResponse:
    """
    Devuelve el estado de revisión de todas las descripciones de un job, paginado.

    Las descripciones sin entrada en Redis se devuelven con status=pending por defecto.
    Requiere que descripciones.csv exista en el storage del job.

    Args:
        job_id: identificador UUID del trabajo.
        limit: máximo de registros por página (1-100, por defecto 25).
        offset: número de registros a saltar (por defecto 0).

    Returns:
        JSONResponse con lista paginada de DescriptionReviewState.

    Raises:
        HTTPException 400: si limit > 100 o < 1.
        HTTPException 404: si el job no existe o no tiene descripciones.

    :author: Carlitos6712
    """
    if not (1 <= limit <= 100):
        raise HTTPException(status_code=400, detail="limit debe estar entre 1 y 100.")

    redis = await _get_redis()
    try:
        await _get_job_status(redis, job_id)  # 404 si no existe

        storage = get_storage_service()
        csv_path: Path = storage.get_job_dir(job_id) / "descripciones.csv"
        if not csv_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"No se encontraron descripciones para el job '{job_id}'.",
            )

        # Leer todos los productos del CSV (con contenido de descripción)
        filas: list[dict] = []
        with open(csv_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("codigo"):
                    filas.append(row)

        total = len(filas)
        pagina = filas[offset:offset + limit]

        # Obtener estado de revisión para cada producto de la página
        revisiones: list[dict] = []
        for fila in pagina:
            cod = fila["codigo"]
            review_key = _JOB_REVIEW_KEY.format(job_id=job_id, codigo=cod)
            raw_review = await redis.get(review_key)
            if raw_review:
                base_state = DescriptionReviewState.model_validate_json(raw_review)
            else:
                base_state = DescriptionReviewState(codigo=cod)
            entry = DescriptionReviewEntry(
                codigo=cod,
                status=base_state.status,
                edited_text=base_state.edited_text,
                nombre=fila.get("nombre", ""),
                descripcion_corta=fila.get("corta", ""),
                descripcion_larga=fila.get("larga", ""),
            )
            revisiones.append(entry.model_dump())

        return JSONResponse(
            content={
                "success": True,
                "data": {
                    "items": revisiones,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                },
                "message": f"{len(revisiones)} revisiones devueltas.",
            }
        )

    finally:
        await redis.aclose()


@router.get(
    "/{job_id}/photos",
    response_model=dict,
    status_code=200,
    summary="(Fase 7.5) Obtener lista de productos con candidatas de foto",
)
async def obtener_fotos_job(
    job_id: str,
    limit: int = Query(20, ge=1, le=100, description="Máximo de productos por página."),
    offset: int = Query(0, ge=0, description="Número de productos a saltar."),
) -> JSONResponse:
    """
    Obtiene la lista paginada de productos con sus fotos candidatas disponibles.

    Requiere que el job esté en estado PENDIENTE_SELECCION_FOTOS.
    Para cada producto devuelve las candidatas encontradas con URLs de acceso.

    Args:
        job_id: identificador UUID del trabajo.
        limit: máximo de productos en la respuesta (1-100).
        offset: número de productos a saltar para paginación.

    Returns:
        JSONResponse con lista paginada de ProductPhotos.

    Raises:
        HTTPException 404: si el job no existe.
        HTTPException 409: si el job no está en PENDIENTE_SELECCION_FOTOS.

    :author: BenjaminDTS
    """
    redis = await _get_redis()
    storage = get_storage_service()

    try:
        status = await _get_job_status(redis, job_id)

        if status.estado != EstadoJob.PENDIENTE_SELECCION_FOTOS:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"El job '{job_id}' no está en estado "
                    f"'{EstadoJob.PENDIENTE_SELECCION_FOTOS.value}'. "
                    f"Estado actual: '{status.estado.value}'."
                ),
            )

        # Leer productos del CSV original para obtener nombres
        csv_raw = await redis.get(_JOB_CSV_KEY.format(job_id=job_id))
        if not csv_raw:
            raise HTTPException(
                status_code=404,
                detail=f"CSV original no encontrado para job '{job_id}'.",
            )

        codigos: list[tuple[str, str]] = []  # (codigo, nombre)
        try:
            _primera_linea = csv_raw.split("\n")[0] if "\n" in csv_raw else csv_raw[:4096]
            _candidatos = [",", ";", "\t", "|"]
            _delimitador = max(_candidatos, key=lambda d: _primera_linea.count(d))
            if _primera_linea.count(_delimitador) == 0:
                _delimitador = ","
            reader = csv.DictReader(io.StringIO(csv_raw), delimiter=_delimitador)
            config_raw = await redis.get(_JOB_CONFIG_KEY.format(job_id=job_id))
            config_dict = json.loads(config_raw) if config_raw else {}
            col_mapping = config_dict.get("column_mapping", {})
            col_codigo = col_mapping.get("columna_codigo", "codigo")
            col_nombre = col_mapping.get("columna_nombre", "nombre")

            for row in reader:
                codigo = row.get(col_codigo, "").strip()
                nombre = row.get(col_nombre, "").strip()
                if codigo:
                    codigos.append((codigo, nombre or codigo))
        except Exception as exc:
            logger.error(
                "Error leyendo CSV para obtener códigos",
                exc_info=exc,
                extra={"job_id": job_id},
            )
            raise HTTPException(
                status_code=500,
                detail="Error interno al leer el CSV.",
            ) from exc

        # Paginar
        total = len(codigos)
        codigos_pagina = codigos[offset : offset + limit]

        # Para cada código, obtener candidatas
        productos: list[dict] = []
        for codigo, nombre in codigos_pagina:
            indices = storage.list_candidates(job_id, codigo)
            candidatas: list[dict] = []

            for idx in indices:
                try:
                    info = storage.get_candidate_info(job_id, codigo, idx)
                    candidata = CandidateInfo(
                        index=idx,
                        url=f"/api/v1/files/{job_id}/photos/{codigo}/candidates/{idx}",
                        width=info.get("width", 0),
                        height=info.get("height", 0),
                        size_bytes=info.get("size_bytes", 0),
                    )
                    candidatas.append(candidata.model_dump())
                except FileNotFoundError:
                    logger.warning(
                        "Candidata no encontrada",
                        extra={"job_id": job_id, "codigo": codigo, "n": idx},
                    )

            # Leer selección anterior si existe en Redis
            selection_key = f"job:{job_id}:photo_selection:{codigo}"
            selected_idx_raw = await redis.get(selection_key)
            selected_idx = int(selected_idx_raw) if selected_idx_raw else None

            producto = ProductPhotos(
                codigo=codigo,
                nombre=nombre,
                n_candidates=len(candidatas),
                candidates=candidatas,
                selected_index=selected_idx,
            )
            productos.append(producto.model_dump())

        logger.info(
            "Fotos del job obtenidas",
            extra={"job_id": job_id, "total": total, "pagina": len(productos)},
        )

        return JSONResponse(
            content={
                "success": True,
                "data": {
                    "productos": productos,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                },
                "message": f"{len(productos)} productos devueltos.",
            }
        )
    finally:
        await redis.aclose()


@router.post(
    "/{job_id}/photos/confirm",
    response_model=dict,
    status_code=200,
    summary="(Fase 7.5) Confirmar selección de fotos y generar ZIP",
)
async def confirmar_seleccion_fotos(
    job_id: str,
    body: PhotoSelectionRequest,
) -> JSONResponse:
    """
    Confirma la selección de fotos por producto: renombra candidatas elegidas
    a {codigo}.jpg, elimina el resto, genera el ZIP y avanza el estado del job.

    Requiere que el job esté en PENDIENTE_SELECCION_FOTOS.
    Tras confirmación:
      - Si job.validate_brands=True → PENDIENTE_VALIDACION_MARCAS
      - Si no → COMPLETADO

    Args:
        job_id: identificador UUID del trabajo.
        body: lista de selecciones con {codigo, selected_index}.

    Returns:
        JSONResponse con confirmadas y zip_listo.

    Raises:
        HTTPException 404: si el job no existe.
        HTTPException 409: si el job no está en PENDIENTE_SELECCION_FOTOS.
        HTTPException 422: si una candidata seleccionada no existe.

    :author: BenjaminDTS
    """
    redis = await _get_redis()
    storage = get_storage_service()

    try:
        status = await _get_job_status(redis, job_id)

        if status.estado != EstadoJob.PENDIENTE_SELECCION_FOTOS:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"El job '{job_id}' no está en estado "
                    f"'{EstadoJob.PENDIENTE_SELECCION_FOTOS.value}'."
                ),
            )

        # Convertir lista de PhotoSelectionItem a dict
        selections: dict[str, int] = {item.codigo: item.selected_index for item in body.selections}

        # Validar que todas las candidatas existen
        try:
            for codigo, selected_idx in selections.items():
                candidates_list = storage.list_candidates(job_id, codigo)
                if selected_idx not in candidates_list:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            f"Candidata seleccionada para '{codigo}' (índice {selected_idx}) no existe. "
                            f"Candidatas disponibles: {candidates_list}."
                        ),
                    )
        except FileNotFoundError as exc:
            logger.error(
                "Error validando candidatas seleccionadas",
                exc_info=exc,
                extra={"job_id": job_id},
            )
            raise HTTPException(
                status_code=422,
                detail="Error al validar las candidatas seleccionadas.",
            ) from exc

        # Confirmar selecciones: renombra y elimina
        try:
            storage.confirm_selection(job_id, selections)
        except FileNotFoundError as exc:
            logger.error(
                "Error al confirmar selecciones",
                exc_info=exc,
                extra={"job_id": job_id},
            )
            raise HTTPException(
                status_code=422,
                detail="Error al confirmar las selecciones.",
            ) from exc

        # Generar ZIP con las fotos seleccionadas
        try:
            storage.create_zip(job_id)
        except Exception as exc:
            logger.error(
                "Error al generar ZIP tras selección de fotos",
                exc_info=exc,
                extra={"job_id": job_id},
            )
            raise HTTPException(
                status_code=500,
                detail="Error al generar el archivo ZIP.",
            ) from exc

        # Eliminar clave de fotos pendientes en Redis
        await redis.delete(f"job:{job_id}:photos_pending")

        # Leer config para saber si hay validación de marcas pendiente
        config_raw = await redis.get(_JOB_CONFIG_KEY.format(job_id=job_id))
        config_dict = json.loads(config_raw) if config_raw else {}
        validate_brands = config_dict.get("validate_brands", False)

        # Actualizar estado del job
        status.fotos_pendientes_seleccion = 0
        if validate_brands:
            status.estado = EstadoJob.PENDIENTE_VALIDACION_MARCAS
            status.mensaje = "Selección de fotos completada. Esperando validación de marcas."
        else:
            status.estado = EstadoJob.COMPLETADO
            status.completado_en = datetime.utcnow()
            status.mensaje = "Job completado: selección de fotos y ZIP generado."

        status.actualizado_en = datetime.utcnow()
        await redis.set(
            _JOB_KEY.format(job_id=job_id),
            status.model_dump_json(),
            ex=_KEY_TTL,
        )

        logger.info(
            "Selección de fotos confirmada",
            extra={
                "job_id": job_id,
                "confirmadas": len(selections),
                "nuevo_estado": status.estado.value,
            },
        )

        return JSONResponse(
            content={
                "success": True,
                "data": {
                    "confirmadas": len(selections),
                    "zip_listo": True,
                    "nuevo_estado": status.estado.value,
                },
                "message": (
                    f"Selección confirmada: {len(selections)} fotos guardadas. "
                    f"Nuevo estado: {status.estado.value}."
                ),
            }
        )
    finally:
        await redis.aclose()


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
                marcas_procesadas=status.marcas_procesadas,
                mensaje=status.mensaje,
                error=status.error,
            )
            await websocket.send_json(event.model_dump())

            # Cerrar cuando el job ha terminado o queda en espera de validación manual
            if status.estado in (
                EstadoJob.COMPLETADO,
                EstadoJob.FALLIDO,
                EstadoJob.CANCELADO,
                EstadoJob.PENDIENTE_VALIDACION_MARCAS,
                EstadoJob.PENDIENTE_SELECCION_FOTOS,
            ):
                break

            await asyncio.sleep(1)

    except WebSocketDisconnect:
        logger.info("Cliente WebSocket desconectado", extra={"job_id": job_id})
    finally:
        await redis.aclose()
        try:
            await websocket.close()
        except RuntimeError:
            pass
