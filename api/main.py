"""
App factory de FastAPI — punto de entrada de la aplicación.

Crea y configura la instancia de FastAPI, monta los routers,
inicializa el logging y aplica los middlewares de seguridad.
Importar como: uvicorn api.main:app

:author: BenjaminDTS
:version: 1.1.0
"""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from loguru import logger

from api.core.config import Settings, get_settings
from api.core.logging import setup_logging
from api.core.security import apply_security_middleware

_HISTORY_KEY = "jobs:history"
_JOB_KEY = "job:{job_id}"


async def _recuperar_jobs_interrumpidos(settings: Settings) -> None:
    """
    Detecta jobs que quedaron en estado EN_PROCESO o PENDIENTE debido a un
    reinicio del servidor y los marca como FALLIDO.

    Esto permite al usuario verlos en el historial y reanudarlos manualmente.
    Si Redis no está disponible en el arranque, se omite sin bloquear el inicio.

    Args:
        settings: configuración de la aplicación con la URL de Redis.
    """
    from api.v1.schemas.job import EstadoJob, JobStatus

    redis_client: aioredis.Redis | None = None
    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await redis_client.ping()
    except Exception as exc:
        logger.warning(
            "Redis no disponible en el arranque — se omite la recuperación de jobs",
            exc_info=exc,
        )
        if redis_client is not None:
            await redis_client.aclose()
        return

    try:
        job_ids: list[str] = await redis_client.zrevrange(_HISTORY_KEY, 0, -1)
        if not job_ids:
            return

        # Leer todos los estados en un solo round-trip
        pipe_read = redis_client.pipeline()
        for job_id in job_ids:
            pipe_read.get(_JOB_KEY.format(job_id=job_id))
        raw_values: list[str | None] = await pipe_read.execute()

        # Identificar los interrumpidos y actualizarlos en otro pipeline
        pipe_write = redis_client.pipeline()
        recuperados = 0
        for job_id, raw in zip(job_ids, raw_values):
            if raw is None:
                continue
            try:
                status = JobStatus.model_validate_json(raw)
            except Exception:
                continue

            if status.estado not in (EstadoJob.EN_PROCESO, EstadoJob.PENDIENTE):
                continue

            status.estado = EstadoJob.FALLIDO
            status.error = "Servidor reiniciado durante la ejecución."
            status.mensaje = (
                "El servidor se reinició mientras este trabajo estaba en proceso. "
                "Puedes reanudarlo desde el historial."
            )
            status.actualizado_en = datetime.utcnow()
            # keepttl=True preserva el TTL original sin restablecerlo
            pipe_write.set(
                _JOB_KEY.format(job_id=job_id),
                status.model_dump_json(),
                keepttl=True,
            )
            recuperados += 1

        if recuperados:
            await pipe_write.execute()
            logger.warning(
                "Jobs interrumpidos marcados como FALLIDO al reiniciar",
                extra={"total_recuperados": recuperados},
            )
        else:
            logger.debug("Sin jobs interrumpidos detectados en el arranque")

    except Exception as exc:
        logger.error(
            "Error durante la recuperación de jobs interrumpidos",
            exc_info=exc,
        )
    finally:
        await redis_client.aclose()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Gestor de ciclo de vida de la aplicación (startup / shutdown).

    En el arranque:
      1. Crea el directorio de salida si no existe.
      2. Detecta jobs interrumpidos en Redis y los marca como FALLIDO.

    Args:
        app: instancia FastAPI gestionada.

    Yields:
        None: control a la aplicación mientras está en ejecución.
    """
    settings = get_settings()

    # Verificar que el directorio de salida existe o se puede crear
    from pathlib import Path
    output_path = Path(settings.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Marcar como FALLIDO los jobs que quedaron activos antes del reinicio
    await _recuperar_jobs_interrumpidos(settings)

    logger.info(
        "Aplicación iniciada",
        extra={
            "env": settings.app_env,
            "output_dir": str(output_path.resolve()),
            "browser": settings.browser_type,
        },
    )

    yield  # La app sirve tráfico aquí

    logger.info("Aplicación detenida correctamente")


def create_app() -> FastAPI:
    """
    Crea y configura la instancia FastAPI.

    Inicializa logging, aplica seguridad y monta los routers versionados.
    Swagger UI solo está disponible en entornos no-producción.

    Returns:
        FastAPI: instancia configurada y lista para servir tráfico.
    """
    # Inicializar logging antes de cualquier otra cosa
    setup_logging()

    settings = get_settings()

    # Deshabilitar docs en producción para no exponer el contrato interno
    docs_url = "/api/docs" if not settings.is_production else None
    redoc_url = "/api/redoc" if not settings.is_production else None
    openapi_url = "/api/openapi.json" if not settings.is_production else None

    app = FastAPI(
        title="Harvist — Scraper de Imágenes",
        description=(
            "API para la descarga masiva y automatizada de imágenes de productos "
            "a partir de un CSV de inventario."
        ),
        version="1.0.0",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )

    # Aplicar CORS, rate limiting y cabeceras de seguridad
    apply_security_middleware(app)

    # Montar routers versionados
    from api.v1.router import router as v1_router
    app.include_router(v1_router, prefix=settings.api_prefix)

    # Health check sin versionar — útil para load balancers y probes de k8s
    @app.get("/health", include_in_schema=False)
    async def health_check() -> JSONResponse:
        """Endpoint de health check para load balancers."""
        return JSONResponse({"status": "ok", "env": settings.app_env})

    return app


# Instancia global — uvicorn apunta aquí
app = create_app()
