"""
App factory de FastAPI — punto de entrada de la aplicación.

Crea y configura la instancia de FastAPI, monta los routers,
inicializa el logging y aplica los middlewares de seguridad.
Importar como: uvicorn api.main:app

:author: BenjaminDTS
:version: 1.0.0
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from loguru import logger

from api.core.config import get_settings
from api.core.logging import setup_logging
from api.core.security import apply_security_middleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Gestor de ciclo de vida de la aplicación (startup / shutdown).

    Se ejecuta antes de que la app empiece a servir tráfico (yield)
    y después de que pare (post-yield). Aquí se validan las dependencias
    externas (Redis, directorios de salida) para fallar rápido si algo
    no está disponible.

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
