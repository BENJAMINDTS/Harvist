"""
Configuración centralizada de logging con loguru.

Este módulo debe ser importado y su función setup_logging() llamada
ÚNICAMENTE desde api/main.py, antes de montar cualquier router.

Configura dos sinks:
  - Archivo JSON rotativo en LOG_DIR (para producción y análisis)
  - Consola coloreada (solo en development)

:author: BenjaminDTS
:version: 1.0.0
"""

import sys
from pathlib import Path

from loguru import logger

from api.core.config import get_settings


def setup_logging() -> None:
    """
    Inicializa loguru eliminando el handler por defecto y añadiendo
    los sinks configurados según las variables de entorno.

    No devuelve nada — modifica el estado global del logger de loguru.
    Llamar esta función una única vez al arranque de la aplicación.
    """
    settings = get_settings()

    # Eliminar el handler por defecto de loguru (stderr sin formato)
    logger.remove()

    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # ── Sink JSON rotativo (siempre activo) ──────────────────────────────────
    # Formato JSON estructurado para ingestión por herramientas de observabilidad.
    # No incluye datos sensibles — solo metadatos del evento.
    logger.add(
        sink=str(log_dir / "app_{time:YYYY-MM-DD}.log"),
        level=settings.log_level,
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        compression="gz",
        encoding="utf-8",
        serialize=True,          # Salida en JSON
        backtrace=False,         # No exponer stack traces completos en prod
        diagnose=settings.is_development,
    )

    # ── Sink consola (solo development) ──────────────────────────────────────
    # En staging/production los logs van al archivo y al agregador de logs,
    # no a stdout, para evitar filtrado accidental de datos.
    if settings.is_development:
        logger.add(
            sink=sys.stderr,
            level=settings.log_level,
            colorize=True,
            format=(
                "<green>{time:HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
                "<level>{message}</level>"
            ),
            backtrace=True,
            diagnose=True,
        )

    logger.info(
        "Logging inicializado",
        extra={
            "env": settings.app_env,
            "log_level": settings.log_level,
            "log_dir": str(log_dir.resolve()),
        },
    )
