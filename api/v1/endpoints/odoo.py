"""
Endpoints de la integración Odoo.

Rutas bajo /api/v1/odoo:
  GET  /odoo/status                    — Estado y configuración
  POST /odoo/config                    — Guardar credenciales en Redis
  GET  /odoo/config                    — Leer credenciales actuales

Rutas bajo /api/v1/odoo/products:
  GET    /odoo/products                — Listar productos (paginado)
  GET    /odoo/products/{id}           — Obtener producto
  POST   /odoo/products                — Crear producto
  PUT    /odoo/products/{id}           — Actualizar producto
  DELETE /odoo/products/{id}           — Eliminar producto

Rutas bajo /api/v1/odoo/categories:
  GET    /odoo/categories              — Listar categorías (paginado)
  GET    /odoo/categories/{id}         — Obtener categoría
  POST   /odoo/categories              — Crear categoría
  PUT    /odoo/categories/{id}         — Actualizar categoría
  DELETE /odoo/categories/{id}         — Eliminar categoría

Rutas bajo /api/v1/odoo/partners:
  GET    /odoo/partners                — Listar partners (customer|supplier|all)
  GET    /odoo/partners/{id}           — Obtener partner
  POST   /odoo/partners                — Crear partner
  PUT    /odoo/partners/{id}           — Actualizar partner
  DELETE /odoo/partners/{id}           — Eliminar partner

Rutas bajo /api/v1/odoo/purchases:
  GET    /odoo/purchases               — Listar pedidos de compra
  GET    /odoo/purchases/{id}          — Obtener pedido de compra
  POST   /odoo/purchases               — Crear pedido de compra
  POST   /odoo/purchases/{id}/confirm  — Confirmar pedido
  POST   /odoo/purchases/{id}/cancel   — Cancelar pedido

Rutas bajo /api/v1/odoo/sales:
  GET    /odoo/sales                   — Listar pedidos de venta
  GET    /odoo/sales/{id}              — Obtener pedido de venta
  POST   /odoo/sales                   — Crear pedido de venta
  POST   /odoo/sales/{id}/confirm      — Confirmar pedido
  POST   /odoo/sales/{id}/cancel       — Cancelar pedido

Rutas bajo /api/v1/odoo/invoices:
  GET    /odoo/invoices                — Listar facturas (customer|supplier)
  GET    /odoo/invoices/{id}           — Obtener factura
  POST   /odoo/invoices                — Crear factura
  POST   /odoo/invoices/{id}/validate  — Validar factura
  POST   /odoo/invoices/{id}/cancel    — Cancelar factura

Rutas bajo /api/v1/odoo/inventory:
  GET    /odoo/inventory               — Listar stock
  GET    /odoo/inventory/locations     — Listar ubicaciones
  GET    /odoo/inventory/products/{id} — Stock de un producto

Todos los endpoints devuelven 503 si Odoo no está configurado.

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from loguru import logger

from api.core.config import get_settings
from api.v1.schemas.integrations import (
    IntegrationStatus,
    OdooConfigRequest,
    OdooConfigResponse,
    PaginatedResponse,
)
from services.integrations.base import IntegrationError, IntegrationNotConfiguredError
from services.integrations.odoo.categories import OooCategoryService
from services.integrations.odoo.client import OdooClient
from services.integrations.odoo.inventory import OdooInventoryService
from services.integrations.odoo.invoices import OdooInvoiceService
from services.integrations.odoo.partners import OdooPartnerService
from services.integrations.odoo.products import OdooProductService
from services.integrations.odoo.purchases import OooPurchaseService
from services.integrations.odoo.sales import OdooSaleService

router_main = APIRouter(prefix="/odoo", tags=["odoo"])
router_products = APIRouter(prefix="/odoo/products", tags=["odoo-products"])
router_categories = APIRouter(prefix="/odoo/categories", tags=["odoo-categories"])
router_partners = APIRouter(prefix="/odoo/partners", tags=["odoo-partners"])
router_purchases = APIRouter(prefix="/odoo/purchases", tags=["odoo-purchases"])
router_sales = APIRouter(prefix="/odoo/sales", tags=["odoo-sales"])
router_invoices = APIRouter(prefix="/odoo/invoices", tags=["odoo-invoices"])
router_inventory = APIRouter(prefix="/odoo/inventory", tags=["odoo-inventory"])

_NOT_CONFIGURED_MSG = (
    "Odoo no está configurado. "
    "Define ODOO_URL, ODOO_DB, ODOO_USER y ODOO_PASSWORD en tu archivo .env "
    "o configúralos en la interfaz gráfica."
)


# ── Credenciales helpers ─────────────────────────────────────────────────────


async def _get_odoo_credentials() -> tuple[str, str, str, str]:
    """
    Obtiene credenciales de Odoo desde Redis o .env.

    Returns:
        Tupla (url, db, user, password).

    Raises:
        IntegrationNotConfiguredError: si no hay credenciales configuradas.
    """
    settings = get_settings()
    redis_client: aioredis.Redis | None = None

    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        stored = await redis_client.get("integration:odoo:config")
        if stored:
            config = json.loads(stored)
            url = config.get("url", "").strip()
            db = config.get("db", "").strip()
            user = config.get("user", "").strip()
            password = config.get("password", "").strip()
            if url and db and user and password:
                return url, db, user, password
    except Exception as exc:
        logger.debug("Redis no disponible para config Odoo", exc_info=exc)
    finally:
        if redis_client:
            await redis_client.aclose()

    if settings.odoo_configured:
        return settings.odoo_url, settings.odoo_db, settings.odoo_user, settings.odoo_password

    raise IntegrationNotConfiguredError(
        "Odoo no configurado: define ODOO_URL, ODOO_DB, ODOO_USER y ODOO_PASSWORD en .env "
        "o configúralos en la interfaz gráfica."
    )


async def _build_client() -> OdooClient:
    """
    Construye OdooClient con credenciales de Redis o .env.

    Raises:
        HTTPException 503: si Odoo no está configurado.
    """
    settings = get_settings()
    try:
        url, db, user, password = await _get_odoo_credentials()
        return OdooClient(settings, override_url=url, override_db=db, override_user=user, override_password=password)
    except IntegrationNotConfiguredError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NOT_CONFIGURED_MSG)


def _ok(data: Any, message: str = "OK") -> dict[str, Any]:
    """Envuelve data en la respuesta estándar Harvist."""
    return {"success": True, "data": data, "message": message}


def _paginated(items: list, total: int, limit: int, offset: int) -> PaginatedResponse:
    """Construye respuesta paginada."""
    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + limit) < total,
    )


# ── Status / Config ──────────────────────────────────────────────────────────


@router_main.get("/status", response_model=IntegrationStatus)
async def get_status() -> IntegrationStatus:
    """
    Verifica estado de configuración y salud de la integración Odoo.

    Siempre devuelve HTTP 200. El estado se comunica en el body.

    Returns:
        IntegrationStatus con platform, configured, healthy y message.
    """
    settings = get_settings()
    redis_client: aioredis.Redis | None = None
    override: dict = {}

    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        stored = await redis_client.get("integration:odoo:config")
        if stored:
            override = json.loads(stored)
    except Exception as exc:
        logger.debug("Redis no disponible para config Odoo", exc_info=exc)
    finally:
        if redis_client:
            await redis_client.aclose()

    has_config = (
        (override.get("url") and override.get("db") and override.get("user") and override.get("password"))
        or settings.odoo_configured
    )

    if not has_config:
        return IntegrationStatus(
            platform="odoo",
            configured=False,
            healthy=None,
            message="ODOO_URL, ODOO_DB, ODOO_USER o ODOO_PASSWORD no están definidos.",
        )

    try:
        client = OdooClient(
            settings,
            override_url=override.get("url", ""),
            override_db=override.get("db", ""),
            override_user=override.get("user", ""),
            override_password=override.get("password", ""),
        )
        healthy = await client.health_check()
    except IntegrationNotConfiguredError:
        return IntegrationStatus(platform="odoo", configured=False, healthy=None, message="Configuración incompleta.")
    except Exception as exc:
        return IntegrationStatus(platform="odoo", configured=True, healthy=False, message=str(exc))

    return IntegrationStatus(
        platform="odoo",
        configured=True,
        healthy=healthy,
        message="Odoo operativo." if healthy else "Odoo no responde.",
    )


@router_main.post("/config")
async def save_config(body: OdooConfigRequest) -> dict[str, Any]:
    """
    Guarda credenciales de Odoo en Redis.

    Args:
        body: url, db, user y password de Odoo.

    Returns:
        Respuesta estándar confirmando el guardado.
    """
    settings = get_settings()
    redis_client: aioredis.Redis | None = None
    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await redis_client.set(
            "integration:odoo:config",
            json.dumps({"url": body.url, "db": body.db, "user": body.user, "password": body.password}),
        )
        logger.info("Configuración Odoo guardada en Redis")
    except Exception as exc:
        logger.error("Error guardando config Odoo en Redis", exc_info=exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error guardando configuración.")
    finally:
        if redis_client:
            await redis_client.aclose()

    return _ok({"url": body.url, "db": body.db, "user": body.user}, "Configuración Odoo guardada.")


@router_main.get("/config", response_model=OdooConfigResponse)
async def get_config() -> OdooConfigResponse:
    """
    Devuelve la configuración actual de Odoo (Redis o .env).

    Returns:
        OdooConfigResponse con los valores actuales.
    """
    settings = get_settings()
    redis_client: aioredis.Redis | None = None
    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        stored = await redis_client.get("integration:odoo:config")
        if stored:
            config = json.loads(stored)
            return OdooConfigResponse(
                url=config.get("url", ""),
                db=config.get("db", ""),
                user=config.get("user", ""),
                password=config.get("password", ""),
                configured=True,
            )
    except Exception as exc:
        logger.debug("Redis no disponible para leer config Odoo", exc_info=exc)
    finally:
        if redis_client:
            await redis_client.aclose()

    return OdooConfigResponse(
        url=settings.odoo_url,
        db=settings.odoo_db,
        user=settings.odoo_user,
        password=settings.odoo_password,
        configured=settings.odoo_configured,
    )


# ── Productos ────────────────────────────────────────────────────────────────


@router_products.get("", response_model=dict)
async def list_products(
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default=""),
) -> dict[str, Any]:
    """Lista productos Odoo con paginación."""
    client = await _build_client()
    svc = OdooProductService(client)
    try:
        items = await svc.list_products(limit=limit, offset=offset, search=search)
        total = await svc.count_products()
        return _ok(_paginated(items, total, limit, offset).model_dump())
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_products.post("/csv/preview", response_model=dict)
async def csv_preview_products(file: UploadFile = File(...)) -> dict[str, Any]:
    """
    Parsea un CSV (delimitador auto-detectado) y devuelve cabeceras + 5 filas de previsualización.

    Returns:
        Dict con headers, preview y row_count.
    """
    raw_bytes = await file.read()
    try:
        content = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw_bytes.decode("latin-1")

    try:
        dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(content), dialect=dialect)
    headers: list[str] = list(reader.fieldnames or [])
    preview: list[dict] = []
    row_count = 0
    for row in reader:
        row_count += 1
        if len(preview) < 5:
            preview.append(dict(row))

    return _ok({
        "headers": headers,
        "preview": preview,
        "row_count": row_count,
        "odoo_fields": list(OdooProductService._CSV_FIELD_TYPES.keys()),
    })


@router_products.post("/csv/import", response_model=dict, status_code=status.HTTP_200_OK)
async def csv_import_products(
    file: UploadFile = File(...),
    mapping: str = Form(...),
) -> dict[str, Any]:
    """
    Importa productos masivamente desde CSV.

    El parámetro ``mapping`` es un JSON ``{columna_csv: campo_odoo}``.
    Columnas mapeadas a cadena vacía se ignoran.

    Returns:
        Dict con created, failed y errors.
    """
    raw_bytes = await file.read()
    try:
        content = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw_bytes.decode("latin-1")

    try:
        col_mapping: dict[str, str] = json.loads(mapping)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El parámetro 'mapping' no es JSON válido.",
        ) from exc

    try:
        dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(content), dialect=dialect)
    rows = [dict(row) for row in reader]

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El CSV no contiene filas de datos.",
        )

    client = await _build_client()
    svc = OdooProductService(client)
    try:
        result = await svc.bulk_create_products(rows, col_mapping)
        return _ok(result, f"{result['created']} productos creados, {result['failed']} fallidos.")
    except Exception as exc:
        logger.error("Error en importación CSV Odoo", exc_info=exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_products.get("/{product_id}", response_model=dict)
async def get_product(product_id: int) -> dict[str, Any]:
    """Obtiene un producto Odoo por ID."""
    client = await _build_client()
    svc = OdooProductService(client)
    try:
        return _ok(await svc.get_product(product_id))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router_products.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_product(body: dict) -> dict[str, Any]:
    """Crea un producto en Odoo."""
    client = await _build_client()
    svc = OdooProductService(client)
    try:
        return _ok(await svc.create_product(body), "Producto creado.")
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_products.put("/{product_id}", response_model=dict)
async def update_product(product_id: int, body: dict) -> dict[str, Any]:
    """Actualiza un producto Odoo."""
    client = await _build_client()
    svc = OdooProductService(client)
    try:
        return _ok(await svc.update_product(product_id, body), "Producto actualizado.")
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_products.delete("/{product_id}", response_model=dict)
async def delete_product(product_id: int) -> dict[str, Any]:
    """Elimina un producto Odoo."""
    client = await _build_client()
    svc = OdooProductService(client)
    try:
        await svc.delete_product(product_id)
        return _ok(None, "Producto eliminado.")
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


# ── Categorías ───────────────────────────────────────────────────────────────


@router_categories.get("", response_model=dict)
async def list_categories(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Lista categorías Odoo con paginación."""
    client = await _build_client()
    svc = OooCategoryService(client)
    try:
        items = await svc.list_categories(limit=limit, offset=offset)
        total = await svc.count_categories()
        return _ok(_paginated(items, total, limit, offset).model_dump())
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_categories.get("/{category_id}", response_model=dict)
async def get_category(category_id: int) -> dict[str, Any]:
    """Obtiene una categoría Odoo por ID."""
    client = await _build_client()
    svc = OooCategoryService(client)
    try:
        return _ok(await svc.get_category(category_id))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router_categories.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_category(body: dict) -> dict[str, Any]:
    """Crea una categoría en Odoo."""
    client = await _build_client()
    svc = OooCategoryService(client)
    try:
        return _ok(
            await svc.create_category(body.get("name", ""), body.get("parent_id")),
            "Categoría creada.",
        )
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_categories.put("/{category_id}", response_model=dict)
async def update_category(category_id: int, body: dict) -> dict[str, Any]:
    """Actualiza una categoría Odoo."""
    client = await _build_client()
    svc = OooCategoryService(client)
    try:
        return _ok(await svc.update_category(category_id, body), "Categoría actualizada.")
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_categories.delete("/{category_id}", response_model=dict)
async def delete_category(category_id: int) -> dict[str, Any]:
    """Elimina una categoría Odoo."""
    client = await _build_client()
    svc = OooCategoryService(client)
    try:
        await svc.delete_category(category_id)
        return _ok(None, "Categoría eliminada.")
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


# ── Partners ─────────────────────────────────────────────────────────────────


@router_partners.get("", response_model=dict)
async def list_partners(
    mode: str = Query(default="all", pattern="^(customer|supplier|all)$"),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default=""),
) -> dict[str, Any]:
    """Lista partners Odoo filtrados por modo."""
    client = await _build_client()
    svc = OdooPartnerService(client)
    try:
        items = await svc.list_partners(mode=mode, limit=limit, offset=offset, search=search)  # type: ignore[arg-type]
        total = await svc.count_partners(mode=mode)  # type: ignore[arg-type]
        return _ok(_paginated(items, total, limit, offset).model_dump())
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_partners.get("/{partner_id}", response_model=dict)
async def get_partner(partner_id: int) -> dict[str, Any]:
    """Obtiene un partner Odoo por ID."""
    client = await _build_client()
    svc = OdooPartnerService(client)
    try:
        return _ok(await svc.get_partner(partner_id))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router_partners.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_partner(body: dict) -> dict[str, Any]:
    """Crea un partner en Odoo."""
    client = await _build_client()
    svc = OdooPartnerService(client)
    try:
        return _ok(await svc.create_partner(body), "Partner creado.")
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_partners.put("/{partner_id}", response_model=dict)
async def update_partner(partner_id: int, body: dict) -> dict[str, Any]:
    """Actualiza un partner Odoo."""
    client = await _build_client()
    svc = OdooPartnerService(client)
    try:
        return _ok(await svc.update_partner(partner_id, body), "Partner actualizado.")
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_partners.delete("/{partner_id}", response_model=dict)
async def delete_partner(partner_id: int) -> dict[str, Any]:
    """Elimina un partner Odoo."""
    client = await _build_client()
    svc = OdooPartnerService(client)
    try:
        await svc.delete_partner(partner_id)
        return _ok(None, "Partner eliminado.")
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


# ── Compras ──────────────────────────────────────────────────────────────────


@router_purchases.get("", response_model=dict)
async def list_purchases(
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    purchase_state: str | None = Query(default=None, alias="state"),
) -> dict[str, Any]:
    """Lista pedidos de compra Odoo con paginación."""
    client = await _build_client()
    svc = OooPurchaseService(client)
    try:
        items = await svc.list_purchases(limit=limit, offset=offset, state=purchase_state)
        total = await svc.count_purchases(state=purchase_state)
        return _ok(_paginated(items, total, limit, offset).model_dump())
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_purchases.get("/{purchase_id}", response_model=dict)
async def get_purchase(purchase_id: int) -> dict[str, Any]:
    """Obtiene un pedido de compra Odoo por ID."""
    client = await _build_client()
    svc = OooPurchaseService(client)
    try:
        return _ok(await svc.get_purchase(purchase_id))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router_purchases.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_purchase(body: dict) -> dict[str, Any]:
    """Crea un pedido de compra en Odoo."""
    client = await _build_client()
    svc = OooPurchaseService(client)
    try:
        return _ok(await svc.create_purchase(body), "Pedido de compra creado.")
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_purchases.post("/{purchase_id}/confirm", response_model=dict)
async def confirm_purchase(purchase_id: int) -> dict[str, Any]:
    """Confirma un pedido de compra Odoo."""
    client = await _build_client()
    svc = OooPurchaseService(client)
    try:
        return _ok(await svc.confirm_purchase(purchase_id), "Pedido confirmado.")
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_purchases.post("/{purchase_id}/cancel", response_model=dict)
async def cancel_purchase(purchase_id: int) -> dict[str, Any]:
    """Cancela un pedido de compra Odoo."""
    client = await _build_client()
    svc = OooPurchaseService(client)
    try:
        return _ok(await svc.cancel_purchase(purchase_id), "Pedido cancelado.")
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


# ── Ventas ───────────────────────────────────────────────────────────────────


@router_sales.get("", response_model=dict)
async def list_sales(
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sale_state: str | None = Query(default=None, alias="state"),
) -> dict[str, Any]:
    """Lista pedidos de venta Odoo con paginación."""
    client = await _build_client()
    svc = OdooSaleService(client)
    try:
        items = await svc.list_sales(limit=limit, offset=offset, state=sale_state)
        total = await svc.count_sales(state=sale_state)
        return _ok(_paginated(items, total, limit, offset).model_dump())
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_sales.get("/{sale_id}", response_model=dict)
async def get_sale(sale_id: int) -> dict[str, Any]:
    """Obtiene un pedido de venta Odoo por ID."""
    client = await _build_client()
    svc = OdooSaleService(client)
    try:
        return _ok(await svc.get_sale(sale_id))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router_sales.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_sale(body: dict) -> dict[str, Any]:
    """Crea un presupuesto de venta en Odoo."""
    client = await _build_client()
    svc = OdooSaleService(client)
    try:
        return _ok(await svc.create_sale(body), "Pedido de venta creado.")
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_sales.post("/{sale_id}/confirm", response_model=dict)
async def confirm_sale(sale_id: int) -> dict[str, Any]:
    """Confirma un presupuesto de venta Odoo."""
    client = await _build_client()
    svc = OdooSaleService(client)
    try:
        return _ok(await svc.confirm_sale(sale_id), "Venta confirmada.")
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_sales.post("/{sale_id}/cancel", response_model=dict)
async def cancel_sale(sale_id: int) -> dict[str, Any]:
    """Cancela un pedido de venta Odoo."""
    client = await _build_client()
    svc = OdooSaleService(client)
    try:
        return _ok(await svc.cancel_sale(sale_id), "Venta cancelada.")
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


# ── Facturas ─────────────────────────────────────────────────────────────────


@router_invoices.get("", response_model=dict)
async def list_invoices(
    type: str = Query(default="customer", pattern="^(customer|supplier)$"),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    invoice_state: str | None = Query(default=None, alias="state"),
    partner_id: int | None = Query(default=None),
) -> dict[str, Any]:
    """Lista facturas Odoo con paginación."""
    client = await _build_client()
    svc = OdooInvoiceService(client)
    try:
        items = await svc.list_invoices(
            type=type,  # type: ignore[arg-type]
            limit=limit,
            offset=offset,
            state=invoice_state,
            partner_id=partner_id,
        )
        total = await svc.count_invoices(type=type, state=invoice_state)  # type: ignore[arg-type]
        return _ok(_paginated(items, total, limit, offset).model_dump())
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_invoices.get("/{invoice_id}", response_model=dict)
async def get_invoice(invoice_id: int) -> dict[str, Any]:
    """Obtiene una factura Odoo por ID."""
    client = await _build_client()
    svc = OdooInvoiceService(client)
    try:
        return _ok(await svc.get_invoice(invoice_id))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router_invoices.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    body: dict,
    type: str = Query(default="customer", pattern="^(customer|supplier)$"),
) -> dict[str, Any]:
    """Crea una factura en borrador en Odoo."""
    client = await _build_client()
    svc = OdooInvoiceService(client)
    try:
        return _ok(await svc.create_invoice(body, type=type), "Factura creada.")  # type: ignore[arg-type]
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_invoices.post("/{invoice_id}/validate", response_model=dict)
async def validate_invoice(invoice_id: int) -> dict[str, Any]:
    """Valida (publica) una factura Odoo en borrador."""
    client = await _build_client()
    svc = OdooInvoiceService(client)
    try:
        return _ok(await svc.validate_invoice(invoice_id), "Factura validada.")
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_invoices.post("/{invoice_id}/cancel", response_model=dict)
async def cancel_invoice(invoice_id: int) -> dict[str, Any]:
    """Cancela una factura Odoo."""
    client = await _build_client()
    svc = OdooInvoiceService(client)
    try:
        return _ok(await svc.cancel_invoice(invoice_id), "Factura cancelada.")
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


# ── Inventario ───────────────────────────────────────────────────────────────


@router_inventory.get("", response_model=dict)
async def list_stock(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    product_id: int | None = Query(default=None),
    location_id: int | None = Query(default=None),
) -> dict[str, Any]:
    """Lista registros de stock Odoo con paginación."""
    client = await _build_client()
    svc = OdooInventoryService(client)
    try:
        items = await svc.list_stock(
            limit=limit, offset=offset, product_id=product_id, location_id=location_id
        )
        total = await svc.count_stock_lines()
        return _ok(_paginated(items, total, limit, offset).model_dump())
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_inventory.get("/locations", response_model=dict)
async def list_locations(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Lista ubicaciones de stock internas de Odoo."""
    client = await _build_client()
    svc = OdooInventoryService(client)
    try:
        items = await svc.list_locations(limit=limit, offset=offset)
        return _ok({"items": items, "total": len(items)})
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_inventory.get("/products/{product_id}", response_model=dict)
async def get_product_stock(product_id: int) -> dict[str, Any]:
    """Obtiene el stock de un producto Odoo en todas las ubicaciones."""
    client = await _build_client()
    svc = OdooInventoryService(client)
    try:
        items = await svc.get_product_stock(product_id)
        return _ok({"product_id": product_id, "stock_lines": items})
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_inventory.put("/{quant_id}", response_model=dict)
async def update_quant(quant_id: int, body: dict) -> dict[str, Any]:
    """Actualiza campos de un stock.quant. Si incluye inventory_quantity aplica el ajuste."""
    client = await _build_client()
    svc = OdooInventoryService(client)
    try:
        await svc.update_quant(quant_id, body)
        return _ok({"quant_id": quant_id})
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_inventory.delete("/{quant_id}", response_model=dict)
async def delete_quant(quant_id: int) -> dict[str, Any]:
    """Elimina un stock.quant."""
    client = await _build_client()
    svc = OdooInventoryService(client)
    try:
        await svc.delete_quant(quant_id)
        return _ok({"quant_id": quant_id})
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router_inventory.post("/{quant_id}/adjust", response_model=dict)
async def adjust_stock(quant_id: int, body: dict) -> dict[str, Any]:
    """Ajusta la cantidad inventariada de un quant de stock."""
    qty = body.get("inventory_quantity")
    if qty is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="inventory_quantity requerido")
    client = await _build_client()
    svc = OdooInventoryService(client)
    try:
        await svc.adjust_stock(quant_id, float(qty))
        return _ok({"quant_id": quant_id, "inventory_quantity": qty})
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
