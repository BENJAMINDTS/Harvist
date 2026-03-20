"""
Instancia y configuración de Celery para el Proyecto Scraping.

Importar como: from workers.celery_app import celery_app

La configuración lee exclusivamente desde Settings para mantener
todas las variables de entorno centralizadas en api/core/config.py.

:author: BenjaminDTS
:version: 1.0.0
"""

from celery import Celery

from api.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "harvist_scraper",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["workers.tasks"],
)

celery_app.conf.update(
    # Serialización
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Zona horaria
    timezone="UTC",
    enable_utc=True,

    # Comportamiento de tareas
    task_track_started=True,        # El worker marca la tarea como STARTED al comenzar
    task_acks_late=True,            # ACK tras completar, no al recibir (evita pérdidas)
    worker_prefetch_multiplier=1,   # Un job a la vez por worker (scraping es intensivo)

    # Reintentos y timeouts
    task_soft_time_limit=3600,      # 60 minutos — tiempo blando (lanza SoftTimeLimitExceeded)
    task_time_limit=3900,           # 65 minutos — tiempo duro (mata el proceso)
    task_max_retries=3,

    # Resultados
    result_expires=settings.file_ttl_seconds,
)
