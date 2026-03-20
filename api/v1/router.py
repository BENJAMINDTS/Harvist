"""
Router principal de la versión 1 de la API.

Monta los sub-routers de jobs y files bajo el prefijo /api/v1
(definido en api/main.py). Cualquier nuevo recurso de v1 se registra aquí.

:author: BenjaminDTS
:version: 1.0.0
"""

from fastapi import APIRouter

from api.v1.endpoints.files import router as files_router
from api.v1.endpoints.jobs import router as jobs_router

router = APIRouter()

router.include_router(jobs_router)
router.include_router(files_router)
