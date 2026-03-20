"""
Configuración de seguridad HTTP: CORS, rate limiting y cabeceras de seguridad.

Este módulo expone apply_security_middleware() que debe llamarse
desde api/main.py inmediatamente después de crear la instancia FastAPI.

:author: BenjaminDTS
:version: 1.0.0
"""

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api.core.config import get_settings

# Instancia global del rate limiter — se importa en los endpoints que lo necesiten
limiter = Limiter(key_func=get_remote_address)


def apply_security_middleware(app: FastAPI) -> None:
    """
    Aplica todos los middlewares y cabeceras de seguridad a la instancia FastAPI.

    Incluye:
    - CORS con lista blanca explícita (nunca *)
    - Rate limiting global via slowapi
    - Cabeceras HTTP de seguridad estándar

    Args:
        app: instancia FastAPI a la que se aplica el middleware.
    """
    settings = get_settings()

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Lista blanca explícita. En producción, solo los dominios reales.
    # Nunca allow_origins=["*"] en producción.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    # ── Rate limiting ─────────────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── Cabeceras de seguridad ────────────────────────────────────────────────
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next) -> Response:
        """
        Middleware que añade cabeceras de seguridad a todas las respuestas HTTP.

        Args:
            request: objeto Request de FastAPI/Starlette.
            call_next: callable que ejecuta el siguiente middleware o endpoint.

        Returns:
            Response con las cabeceras de seguridad añadidas.
        """
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=()"

        # Strict-Transport-Security solo en producción (requiere HTTPS)
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )

        return response
