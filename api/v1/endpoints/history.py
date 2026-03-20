"""
Endpoint HTTP para el historial paginado de trabajos de scraping.

Rutas expuestas:
  GET /api/v1/jobs — Lista paginada y filtrable de todos los jobs registrados.

Lee el sorted set ``jobs:history`` de Redis (insertado por el worker al crear
cada job) y recupera el estado completo de cada job desde ``job:{job_id}``.
No contiene lógica de negocio: solo orquesta la lectura desde Redis y
devuelve la respuesta paginada con el contrato estándar.

:author: BenjaminDTS
:version: 1.0.0
"""

import json
from datetime import datetime
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel

from api.core.config import get_settings
from api.core.security import limiter
from api.v1.schemas.job import EstadoJob, JobStatus

router = APIRouter(prefix="/jobs", tags=["History"])
settings = get_settings()

# ── Claves Redis ───────────────────────────────────────────────────────────────

# Sorted set con todos los job_ids ordenados por timestamp de creación
_HISTORY_KEY = "jobs:history"
# Clave de estado individual de cada job
_JOB_KEY = "job:{job_id}"


# ── Schemas locales de respuesta ───────────────────────────────────────────────


class JobHistoryItem(BaseModel):
    """
    Subconjunto de JobStatus expuesto en el listado de historial.

    Incluye solo los campos necesarios para la vista de tabla, evitando
    serializar información interna no relevante para el cliente.

    :author: BenjaminDTS
    """

    job_id: str
    estado: EstadoJob
    total_productos: int
    imagenes_descargadas: int
    porcentaje: float
    creado_en: datetime
    completado_en: datetime | None
    mensaje: str


class JobHistoryResponse(BaseModel):
    """
    Respuesta estándar del endpoint de historial.

    Sigue el contrato: { success, data, message }.
    ``data`` contiene los items paginados y los metadatos de paginación.

    :author: BenjaminDTS
    """

    success: bool
    data: dict  # { items: list[JobHistoryItem], total: int, limit: int, offset: int }
    message: str


# ── Helpers privados ───────────────────────────────────────────────────────────


async def _get_redis() -> aioredis.Redis:
    """
    Crea y verifica una conexión asíncrona a Redis.

    Returns:
        Cliente Redis asíncrono listo para usarse.

    Raises:
        HTTPException 503: si Redis no responde al ping inicial.
    """
    try:
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await client.ping()
        return client
    except Exception as exc:
        logger.error("No se pudo conectar a Redis en el historial", exc_info=exc)
        raise HTTPException(
            status_code=503,
            detail="Servicio no disponible temporalmente.",
        ) from exc


def _job_status_to_history_item(status: JobStatus) -> JobHistoryItem:
    """
    Convierte un JobStatus completo en un JobHistoryItem resumido.

    ``porcentaje`` se obtiene del property calculado de JobStatus para
    mantener la consistencia con el resto de la API.

    Args:
        status: estado completo del job recuperado desde Redis.

    Returns:
        JobHistoryItem con los campos necesarios para el listado.
    """
    return JobHistoryItem(
        job_id=str(status.job_id),
        estado=status.estado,
        total_productos=status.total_productos,
        imagenes_descargadas=status.imagenes_descargadas,
        porcentaje=status.porcentaje,
        creado_en=status.creado_en,
        completado_en=status.completado_en,
        mensaje=status.mensaje,
    )


# ── Endpoint ───────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=JobHistoryResponse,
    summary="Listar historial de trabajos con paginación y filtro opcional por estado",
)
@limiter.limit("30/minute")
async def listar_historial(
    request: Request,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Número máximo de items a devolver."),
    ] = 20,
    offset: Annotated[
        int,
        Query(ge=0, description="Número de items a saltar para la paginación."),
    ] = 0,
    estado: Annotated[
        str | None,
        Query(
            description=(
                "Filtro opcional por estado del job. "
                "Valores: pendiente | en_proceso | completado | fallido | cancelado"
            )
        ),
    ] = None,
) -> JSONResponse:
    """
    Devuelve la lista paginada de todos los trabajos de scraping registrados.

    Lee los job_ids del sorted set ``jobs:history`` ordenados por timestamp
    descendente (más recientes primero), recupera el estado de cada job
    y aplica el filtro por estado y la paginación solicitados.
    Los job_ids cuya clave ya expiró en Redis se ignoran silenciosamente.

    Args:
        request: objeto Request de FastAPI (requerido por slowapi para rate limiting).
        limit: número máximo de items a incluir en la respuesta (1–100, default 20).
        offset: número de items a omitir desde el inicio de la lista filtrada.
        estado: si se especifica, devuelve únicamente los jobs con ese estado exacto.

    Returns:
        JSONResponse con la estructura estándar:
        ``{ success, data: { items, total, limit, offset }, message }``.

    Raises:
        HTTPException 400: si ``estado`` no es un valor válido de EstadoJob.
        HTTPException 503: si Redis no está disponible.
    """
    # Validar el valor del filtro antes de abrir conexión a Redis
    estado_enum: EstadoJob | None = None
    if estado is not None:
        try:
            estado_enum = EstadoJob(estado)
        except ValueError:
            valores_validos = ", ".join(e.value for e in EstadoJob)
            raise HTTPException(
                status_code=400,
                detail=f"Estado '{estado}' no válido. Valores permitidos: {valores_validos}.",
            )

    redis = await _get_redis()
    try:
        # 1. Recuperar todos los job_ids ordenados de más reciente a más antiguo
        job_ids: list[str] = await redis.zrevrange(_HISTORY_KEY, 0, -1)

        if not job_ids:
            return JSONResponse(
                content={
                    "success": True,
                    "data": {"items": [], "total": 0, "limit": limit, "offset": offset},
                    "message": "No hay trabajos registrados aún.",
                }
            )

        # 2. Recuperar los estados en una sola ida a Redis mediante pipeline
        pipeline = redis.pipeline()
        for job_id in job_ids:
            pipeline.get(_JOB_KEY.format(job_id=job_id))
        raw_values: list[str | None] = await pipeline.execute()

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Error leyendo historial de jobs desde Redis",
            exc_info=exc,
            extra={"limit": limit, "offset": offset, "estado": estado},
        )
        raise HTTPException(
            status_code=503,
            detail="Error al recuperar el historial de trabajos.",
        ) from exc
    finally:
        await redis.aclose()

    # 3. Deserializar, descartar expirados y aplicar filtro de estado
    items: list[JobHistoryItem] = []
    for job_id, raw in zip(job_ids, raw_values):
        if raw is None:
            # El job expiró en Redis — se omite silenciosamente
            logger.debug(
                "Job expirado omitido del historial",
                extra={"job_id": job_id},
            )
            continue

        try:
            status = JobStatus.model_validate_json(raw)
        except Exception as exc:
            logger.warning(
                "No se pudo deserializar el estado del job; se omite del historial",
                exc_info=exc,
                extra={"job_id": job_id},
            )
            continue

        # Aplicar filtro por estado si se proporcionó
        if estado_enum is not None and status.estado != estado_enum:
            continue

        items.append(_job_status_to_history_item(status))

    # 4. Calcular total sobre la lista filtrada y paginar
    total = len(items)
    paginated = items[offset : offset + limit]

    logger.info(
        "Historial de jobs consultado",
        extra={"total": total, "limit": limit, "offset": offset, "estado": estado},
    )

    return JSONResponse(
        content={
            "success": True,
            "data": {
                "items": [json.loads(item.model_dump_json()) for item in paginated],
                "total": total,
                "limit": limit,
                "offset": offset,
            },
            "message": f"Se encontraron {total} trabajo(s).",
        }
    )
