"""
Router principal de la versión 1 de la API.

Monta los sub-routers de jobs, files, history, todos los módulos Dolibarr,
Odoo (incluyendo Properties) y WordPress/WooCommerce bajo el prefijo /api/v1.
Cualquier nuevo recurso de v1 se registra aquí.

:author: BenjaminDTS
:author: Carlitos6712
:version: 1.2.0
"""

from fastapi import APIRouter

from api.v1.endpoints.dolibarr import (
    categories_router,
    extrafields_router,
    invoices_router,
    orders_router,
    router_main as dolibarr_router_main,
    router_products as dolibarr_router_products,
    stocks_router,
    thirdparties_router,
)
from api.v1.endpoints.files import router as files_router
from api.v1.endpoints.history import router as history_router
from api.v1.endpoints.jobs import router as jobs_router
from api.v1.endpoints.odoo import (
    router_main as odoo_router_main,
    router_products as odoo_router_products,
    router_categories as odoo_router_categories,
    router_partners as odoo_router_partners,
    router_purchases as odoo_router_purchases,
    router_sales as odoo_router_sales,
    router_invoices as odoo_router_invoices,
    router_inventory as odoo_router_inventory,
    router_properties as odoo_router_properties,
)
from api.v1.endpoints.wordpress import (
    router_main as wordpress_router_main,
    router_products as wordpress_router_products,
    router_categories as wordpress_router_categories,
    router_orders as wordpress_router_orders,
    router_customers as wordpress_router_customers,
    router_media as wordpress_router_media,
    router_db as wordpress_router_db,
)

router = APIRouter()

router.include_router(jobs_router)
router.include_router(files_router)
router.include_router(history_router)
router.include_router(dolibarr_router_main)
router.include_router(dolibarr_router_products)
router.include_router(categories_router)
router.include_router(thirdparties_router)
router.include_router(orders_router)
router.include_router(invoices_router)
router.include_router(stocks_router)
router.include_router(extrafields_router)
router.include_router(odoo_router_main)
router.include_router(odoo_router_products)
router.include_router(odoo_router_categories)
router.include_router(odoo_router_partners)
router.include_router(odoo_router_purchases)
router.include_router(odoo_router_sales)
router.include_router(odoo_router_invoices)
router.include_router(odoo_router_inventory)
router.include_router(odoo_router_properties)
router.include_router(wordpress_router_main)
router.include_router(wordpress_router_products)
router.include_router(wordpress_router_categories)
router.include_router(wordpress_router_orders)
router.include_router(wordpress_router_customers)
router.include_router(wordpress_router_media)
router.include_router(wordpress_router_db)
