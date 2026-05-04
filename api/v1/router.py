"""
Router principal de la versión 1 de la API.

Monta los sub-routers de jobs y files bajo el prefijo /api/v1
(definido en api/main.py). Cualquier nuevo recurso de v1 se registra aquí.

:author: BenjaminDTS
:author: Carlitos6712
:version: 1.1.0
"""

from fastapi import APIRouter

from api.v1.endpoints.dolibarr import categories_router, invoices_router, orders_router, stocks_router, thirdparties_router, router as dolibarr_router
from api.v1.endpoints.files import router as files_router
from api.v1.endpoints.history import router as history_router
from api.v1.endpoints.jobs import router as jobs_router

router = APIRouter()

router.include_router(jobs_router)
router.include_router(files_router)
router.include_router(history_router)
router.include_router(dolibarr_router)
router.include_router(categories_router)
router.include_router(thirdparties_router)
router.include_router(orders_router)
router.include_router(invoices_router)
router.include_router(stocks_router)
