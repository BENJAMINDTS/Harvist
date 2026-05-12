"""
Endpoints de la integración Dolibarr.

Rutas expuestas bajo /api/v1/dolibarr:
  GET    /dolibarr/status                             — Verificar estado y configuración

Rutas expuestas bajo /api/v1/dolibarr/products:
  GET    /dolibarr/products                        — Listar productos (paginado)
  GET    /dolibarr/products/fields                 — Schema dinámico de campos (estándar + extra)
  GET    /dolibarr/products/{product_id}           — Obtener producto por ID
  POST   /dolibarr/products                        — Crear producto
  PUT    /dolibarr/products/{product_id}           — Actualizar producto
  DELETE /dolibarr/products/{product_id}           — Eliminar producto
  POST   /dolibarr/products/{product_id}/image     — Subir imagen (multipart)
  POST   /dolibarr/products/sync                   — Sincronizar desde job Harvist

Rutas expuestas bajo /api/v1/dolibarr/categories:
  GET    /dolibarr/categories                      — Listar categorías (paginado)
  GET    /dolibarr/categories/tree                 — Obtener árbol jerárquico
  GET    /dolibarr/categories/{category_id}        — Obtener categoría por ID
  POST   /dolibarr/categories                      — Crear categoría
  PUT    /dolibarr/categories/{category_id}        — Actualizar categoría
  DELETE /dolibarr/categories/{category_id}        — Eliminar categoría
  POST   /dolibarr/categories/{category_id}/products/{product_id} — Asignar producto
  DELETE /dolibarr/categories/{category_id}/products/{product_id} — Remover producto
  GET    /dolibarr/categories/{category_id}/products — Listar productos en categoría

Rutas expuestas bajo /api/v1/dolibarr/invoices:
  GET    /dolibarr/invoices                        — Listar facturas (customer/supplier)
  GET    /dolibarr/invoices/{invoice_id}           — Obtener factura por ID
  POST   /dolibarr/invoices                        — Crear factura
  POST   /dolibarr/invoices/{invoice_id}/lines     — Añadir línea a factura
  POST   /dolibarr/invoices/{invoice_id}/validate  — Validar factura
  POST   /dolibarr/invoices/{invoice_id}/send      — Enviar factura por email
  POST   /dolibarr/invoices/{invoice_id}/pay       — Registrar pago
  DELETE /dolibarr/invoices/{invoice_id}           — Eliminar factura (borrador)

Rutas expuestas bajo /api/v1/dolibarr/stocks:
  GET    /dolibarr/stocks/warehouses               — Listar almacenes (paginado)
  GET    /dolibarr/stocks/warehouses/{warehouse_id} — Obtener almacén por ID
  GET    /dolibarr/stocks/products/{product_id}   — Obtener stock de producto
  GET    /dolibarr/stocks/movements                — Listar movimientos (paginado)
  POST   /dolibarr/stocks/movements                — Crear movimiento de stock
  POST   /dolibarr/stocks/transfer                 — Transferir entre almacenes

Todos los endpoints devuelven 503 si Dolibarr no está configurado.

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

import asyncio
import base64
import csv
import io
import json
import tempfile
import uuid
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Body, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from loguru import logger

from api.core.config import get_settings
from api.v1.schemas.integrations import (
    CsvImportPreview,
    CsvImportResponse,
    CsvImportRowResult,
    DolibarrConfigRequest,
    DolibarrConfigResponse,
    DolibarrDBConfigRequest,
    DolibarrDBConfigResponse,
    DolibarrExtraField,
    DolibarrExtraFieldCreate,
    IntegrationStatus,
    PaginatedResponse,
    SyncFromJobRequest,
)
from services.integrations.base import IntegrationError, IntegrationNotConfiguredError
from services.integrations.dolibarr.categories import DolibarrCategoryService
from services.integrations.dolibarr.client import DolibarrClient
from services.integrations.dolibarr.extrafields import DolibarrExtraFieldService
from services.integrations.dolibarr.invoices import DolibarrInvoiceService
from services.integrations.dolibarr.orders import DolibarrOrderService
from services.integrations.dolibarr.products import DolibarrProductService
from services.integrations.dolibarr.stocks import DolibarrStockService
from services.integrations.dolibarr.thirdparties import DolibarrThirdpartyService
from services.storage_service import get_storage_service

router_main = APIRouter(prefix="/dolibarr", tags=["dolibarr"])
router_products = APIRouter(prefix="/dolibarr/products", tags=["dolibarr-products"])

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
_NOT_CONFIGURED_MSG = (
    "Dolibarr no está configurado. "
    "Define DOLIBARR_URL y DOLIBARR_API_KEY en tu archivo .env."
)


async def _get_dolibarr_credentials() -> tuple[str, str]:
    """
    Obtiene credenciales de Dolibarr desde Redis o .env.

    Retorna:
        Tupla (url, api_key).

    Raises:
        IntegrationNotConfiguredError: si no hay credenciales configuradas.
    """
    settings = get_settings()
    redis_client: aioredis.Redis | None = None

    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        stored = await redis_client.get("integration:dolibarr:config")
        if stored:
            config = json.loads(stored)
            url = config.get("url", "").strip()
            api_key = config.get("api_key", "").strip()
            if url and api_key:
                return url, api_key
    except Exception as exc:
        logger.debug("Redis no disponible para config Dolibarr", exc_info=exc)
    finally:
        if redis_client:
            await redis_client.aclose()

    # Fallback a settings
    if settings.dolibarr_configured:
        return settings.dolibarr_url, settings.dolibarr_api_key

    raise IntegrationNotConfiguredError(
        "Dolibarr no configurado: define DOLIBARR_URL y DOLIBARR_API_KEY en .env "
        "o configúralas en la interfaz gráfica."
    )


async def _get_service_async() -> DolibarrProductService:
    """
    Construye y devuelve una instancia de DolibarrProductService.
    Lee credenciales desde Redis o .env.

    Raises:
        HTTPException 503: si Dolibarr no está configurado.
    """
    settings = get_settings()
    try:
        url, api_key = await _get_dolibarr_credentials()
        client = DolibarrClient(settings, override_url=url, override_api_key=api_key)
    except IntegrationNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_NOT_CONFIGURED_MSG,
        )
    return DolibarrProductService(client)


def _get_service() -> DolibarrProductService:
    """
    Construye y devuelve una instancia de DolibarrProductService.

    NOTA: Esta versión usa solo .env. Usar _get_service_async para aprovechar Redis config.

    Raises:
        HTTPException 503: si Dolibarr no está configurado.
    """
    settings = get_settings()
    if not settings.dolibarr_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_NOT_CONFIGURED_MSG,
        )
    try:
        client = DolibarrClient(settings)
    except IntegrationNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_NOT_CONFIGURED_MSG,
        )
    return DolibarrProductService(client)


async def _get_services_async() -> tuple[DolibarrProductService, DolibarrCategoryService]:
    """
    Construye y devuelve DolibarrProductService y DolibarrCategoryService compartiendo cliente.

    Raises:
        HTTPException 503: si Dolibarr no está configurado.
    """
    settings = get_settings()
    try:
        url, api_key = await _get_dolibarr_credentials()
        client = DolibarrClient(settings, override_url=url, override_api_key=api_key)
    except IntegrationNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_NOT_CONFIGURED_MSG,
        )
    return DolibarrProductService(client), DolibarrCategoryService(client)


def _ok(data: Any, message: str = "OK") -> dict[str, Any]:
    """Envuelve data en la respuesta estándar Harvist."""
    return {"success": True, "data": data, "message": message}


# ── Status endpoint ──────────────────────────────────────────────────────


@router_main.get("/status", response_model=IntegrationStatus)
async def get_status() -> IntegrationStatus:
    """
    Verifica estado de configuración y salud de la integración Dolibarr.

    Siempre devuelve HTTP 200. El estado se comunica en el body.
    Prioridad: Redis config > variables de entorno.

    Returns:
        IntegrationStatus con platform, configured, healthy y message.
    """
    settings = get_settings()
    redis_client: aioredis.Redis | None = None
    override_url = ""
    override_api_key = ""

    # Intentar leer config de Redis
    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        stored = await redis_client.get("integration:dolibarr:config")
        if stored:
            config = json.loads(stored)
            override_url = config.get("url", "")
            override_api_key = config.get("api_key", "")
    except Exception as exc:
        logger.debug("Redis no disponible para config Dolibarr", exc_info=exc)
    finally:
        if redis_client:
            await redis_client.aclose()

    # Verificar si hay configuración disponible
    has_config = (
        (override_url and override_api_key)
        or settings.dolibarr_configured
    )

    if not has_config:
        return IntegrationStatus(
            platform="dolibarr",
            configured=False,
            healthy=None,
            message="DOLIBARR_URL o DOLIBARR_API_KEY no están definidos en .env o en la GUI.",
        )

    try:
        client = DolibarrClient(settings, override_url=override_url, override_api_key=override_api_key)
    except IntegrationNotConfiguredError:
        return IntegrationStatus(
            platform="dolibarr",
            configured=False,
            healthy=None,
            message="Configuración de Dolibarr incompleta. Define URL y API Key.",
        )
    except Exception as exc:
        return IntegrationStatus(
            platform="dolibarr",
            configured=False,
            healthy=None,
            message=f"URL inválida: {exc}. Usa el formato http://host:puerto",
        )

    try:
        is_healthy = await client.health_check()
        if is_healthy:
            return IntegrationStatus(
                platform="dolibarr",
                configured=True,
                healthy=True,
                message="Conexión con Dolibarr establecida.",
            )
        else:
            return IntegrationStatus(
                platform="dolibarr",
                configured=True,
                healthy=False,
                message="Dolibarr no responde. Comprueba la URL y que el servidor esté activo.",
            )
    except Exception as exc:
        logger.warning("Error verificando salud de Dolibarr", exc_info=exc)
        return IntegrationStatus(
            platform="dolibarr",
            configured=True,
            healthy=False,
            message=f"Error al verificar conexión: {str(exc)}",
        )


# ── Stats endpoint ───────────────────────────────────────────────────────


@router_main.get("/stats")
async def get_dolibarr_stats() -> JSONResponse:
    """
    Devuelve estadísticas resumidas de terceros y facturas de Dolibarr.

    Llama en paralelo a los recursos de terceros (all) y facturas (customer/supplier)
    con limit=500. Devuelve conteos y flag has_more si existen más registros.

    Returns:
        Dict con configured, thirdparties (total/customers/suppliers) e invoices (customer/supplier).
    """
    settings = get_settings()
    try:
        url, api_key = await _get_dolibarr_credentials()
        client = DolibarrClient(settings, override_url=url, override_api_key=api_key)
    except IntegrationNotConfiguredError:
        return JSONResponse(content=_ok({
            "configured": False,
            "thirdparties": None,
            "invoices": None,
        }))

    thirdparty_svc = DolibarrThirdpartyService(client)

    try:
        all_thirds, customer_inv, supplier_inv = await asyncio.gather(
            thirdparty_svc.list_thirdparties(mode="all", limit=500),
            client.list("invoices", limit=500),
            client.list("supplierinvoices", limit=500),
        )
    except IntegrationError as exc:
        logger.error("Error obteniendo stats Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )

    customers = sum(1 for t in all_thirds if str(t.get("client", "0")) == "1")
    suppliers = sum(1 for t in all_thirds if str(t.get("supplier", "0")) == "1")

    return JSONResponse(content=_ok({
        "configured": True,
        "thirdparties": {
            "total": len(all_thirds),
            "customers": customers,
            "suppliers": suppliers,
            "has_more": len(all_thirds) >= 500,
        },
        "invoices": {
            "customer": len(customer_inv),
            "supplier": len(supplier_inv),
            "has_more_customer": len(customer_inv) >= 500,
            "has_more_supplier": len(supplier_inv) >= 500,
        },
    }))


# ── Configuración ────────────────────────────────────────────────────────


@router_main.get("/config", response_model=DolibarrConfigResponse)
async def get_config() -> DolibarrConfigResponse:
    """
    Obtiene la configuración guardada de Dolibarr (Redis) o del .env.

    Returns:
        DolibarrConfigResponse con URL, API key y estado configurado.
    """
    settings = get_settings()
    redis_client: aioredis.Redis | None = None

    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        stored = await redis_client.get("integration:dolibarr:config")
        if stored:
            config = json.loads(stored)
            return DolibarrConfigResponse(
                url=config.get("url", ""),
                api_key=config.get("api_key", ""),
                configured=bool(config.get("url") and config.get("api_key")),
            )
    except Exception as exc:
        logger.warning("Error accediendo a Redis para config Dolibarr", exc_info=exc)
    finally:
        if redis_client:
            await redis_client.aclose()

    # Fallback a variables de entorno
    return DolibarrConfigResponse(
        url=settings.dolibarr_url or "",
        api_key=settings.dolibarr_api_key or "",
        configured=settings.dolibarr_configured,
    )


@router_main.post("/config", response_model=DolibarrConfigResponse)
async def save_config(request: DolibarrConfigRequest) -> DolibarrConfigResponse:
    """
    Guarda la configuración de Dolibarr en Redis.

    Args:
        request: DolibarrConfigRequest con URL y API key.

    Returns:
        DolibarrConfigResponse confirmando los datos guardados.
    """
    settings = get_settings()
    redis_client: aioredis.Redis | None = None

    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        config = {
            "url": request.url.rstrip("/"),
            "api_key": request.api_key.strip(),
        }
        await redis_client.set(
            "integration:dolibarr:config",
            json.dumps(config),
            ex=None,
        )
        logger.info(
            "Configuración de Dolibarr guardada",
            extra={"url": config["url"]},
        )
        return DolibarrConfigResponse(
            url=config["url"],
            api_key=config["api_key"],
            configured=True,
        )
    except Exception as exc:
        logger.error("Error guardando configuración de Dolibarr en Redis", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error guardando configuración: {str(exc)}",
        )
    finally:
        if redis_client:
            await redis_client.aclose()


# ── Configuración BD ─────────────────────────────────────────────────────

_REDIS_DB_CONFIG_KEY = "integration:dolibarr:db_config"


async def _get_dolibarr_db_config() -> dict:
    """
    Lee configuración de BD de Dolibarr desde Redis.
    Fallback a variables de entorno si Redis no tiene la clave.

    Returns:
        Dict con host, port, db_name, user, password, prefix.
    """
    settings = get_settings()
    redis_client: aioredis.Redis | None = None

    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        stored = await redis_client.get(_REDIS_DB_CONFIG_KEY)
        if stored:
            return json.loads(stored)
    except Exception as exc:
        logger.debug("Redis no disponible para DB config Dolibarr", exc_info=exc)
    finally:
        if redis_client:
            await redis_client.aclose()

    return {
        "host": settings.dolibarr_db_host,
        "port": settings.dolibarr_db_port,
        "db_name": settings.dolibarr_db_name,
        "user": settings.dolibarr_db_user,
        "password": settings.dolibarr_db_pass,
        "prefix": settings.dolibarr_db_prefix,
    }


@router_main.get("/db-config", response_model=DolibarrDBConfigResponse)
async def get_db_config() -> DolibarrDBConfigResponse:
    """
    Obtiene la configuración de BD de Dolibarr guardada en Redis o .env.

    Returns:
        DolibarrDBConfigResponse con credenciales y estado.
    """
    cfg = await _get_dolibarr_db_config()
    configured = bool(
        cfg.get("host", "").strip()
        and cfg.get("db_name", "").strip()
        and cfg.get("user", "").strip()
    )
    return DolibarrDBConfigResponse(
        host=cfg.get("host", ""),
        port=cfg.get("port", 3306),
        db_name=cfg.get("db_name", ""),
        user=cfg.get("user", ""),
        password=cfg.get("password", ""),
        prefix=cfg.get("prefix", "llx_"),
        configured=configured,
    )


@router_main.post("/db-config", response_model=DolibarrDBConfigResponse)
async def save_db_config(request: DolibarrDBConfigRequest) -> DolibarrDBConfigResponse:
    """
    Guarda las credenciales de BD de Dolibarr en Redis.

    Args:
        request: DolibarrDBConfigRequest con las credenciales de acceso a MySQL.

    Returns:
        DolibarrDBConfigResponse confirmando los datos guardados.
    """
    settings = get_settings()
    redis_client: aioredis.Redis | None = None

    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        config = {
            "host": request.host.strip(),
            "port": request.port,
            "db_name": request.db_name.strip(),
            "user": request.user.strip(),
            "password": request.password,
            "prefix": request.prefix.strip() or "llx_",
        }
        await redis_client.set(_REDIS_DB_CONFIG_KEY, json.dumps(config))
        logger.info(
            "Configuración BD Dolibarr guardada",
            extra={"host": config["host"], "db_name": config["db_name"]},
        )
        return DolibarrDBConfigResponse(**config, configured=True)
    except Exception as exc:
        logger.error("Error guardando configuración BD Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error guardando configuración BD: {str(exc)}",
        )
    finally:
        if redis_client:
            await redis_client.aclose()


# ── Productos ────────────────────────────────────────────────────────────


@router_products.get("")
async def list_products(
    limit: int = Query(default=50, ge=1, le=20000),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None),
) -> JSONResponse:
    """
    Lista productos de Dolibarr con paginación.

    Args:
        limit: máximo de productos por página.
        offset: desplazamiento desde el inicio.
        search: término para filtrar por referencia o nombre.

    Returns:
        PaginatedResponse con los productos encontrados.
    """
    try:
        svc = await _get_service_async()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error creando servicio Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_NOT_CONFIGURED_MSG,
        )

    try:
        # Obtener productos y el conteo total en paralelo
        items_task = svc.list_products(limit=limit, offset=offset, search=search)
        # Asumimos que el servicio tiene un método para contar que acepta el filtro
        total_task = svc.count_products(search=search)
        items, total = await asyncio.gather(items_task, total_task)
    except IntegrationError as exc:
        logger.error("Error listando productos Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + len(items)) < total,
    ).model_dump()))


@router_products.get("/fields")
async def get_product_fields() -> JSONResponse:
    """
    Devuelve el schema de campos para productos de esta instancia Dolibarr.

    Combina campos estándar con los campos extra. Usa DolibarrExtraFieldService
    (con fallback a BD MariaDB) para obtener los extrafields, garantizando que
    los campos creados manualmente en Dolibarr se detecten aunque la API REST
    de extrafields no esté disponible.

    Returns:
        Lista de DolibarrFieldSchema con key, label, type, required, section, is_extra, options.
    """
    svc = await _get_service_async()
    extra_svc = await _get_extrafield_service()
    try:
        pre_fetched = await extra_svc.list_extrafields(elementtype="product")
        fields = await svc.get_product_fields(pre_fetched_extras=pre_fetched)
    except Exception as exc:
        logger.error("Error obteniendo schema de campos Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(fields, "Schema de campos obtenido."))


@router_products.post("", status_code=status.HTTP_201_CREATED)
async def create_product(data: dict) -> JSONResponse:
    """
    Crea un producto en Dolibarr.

    Si el payload incluye ``array_options`` (extrafields), estos se guardan via
    BD directa para evitar el error de Dolibarr "Field X doesn't have a default
    value" que afecta al endpoint REST PUT /products/{id}.

    Si el payload incluye ``category_name``, el producto se asigna a esa
    categoría tras la creación. La categoría debe existir previamente con ese
    nombre exacto; si no existe se devuelve 422.

    Args:
        data: campos del producto (ref, label, price, description, type, status,
              array_options opcional con extrafields, category_name opcional).

    Returns:
        Respuesta estándar (201) con el producto creado.
    """
    array_options: dict = data.pop("array_options", None) or {}
    category_name: str = (data.pop("category_name", None) or "").strip()

    svc, cat_svc = await _get_services_async()

    # Pre-validate category before creating the product to avoid partial state
    category_id: int | None = None
    if category_name:
        cat = await cat_svc.find_category_by_name(category_name)
        if cat is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"La categoría '{category_name}' no existe en Dolibarr. "
                    "Créala primero desde el módulo de Categorías."
                ),
            )
        category_id = int(cat["id"])

    try:
        created = await svc.create_product(data)
    except IntegrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )

    product_id: int | None = created.get("id") if isinstance(created, dict) else None

    if array_options and product_id:
        try:
            db = await _get_extrafield_db()
            await db.update_product_extrafields(
                product_id=product_id,
                array_options=array_options,
                elementtype="product",
            )
        except HTTPException:
            pass  # BD no configurada — extrafields omitidos sin romper la respuesta
        except Exception as exc:
            logger.warning(
                "Extrafields no guardados tras crear producto",
                exc_info=exc,
                extra={"product_id": product_id},
            )

    if category_id and product_id:
        try:
            await cat_svc.assign_product(category_id, product_id)
            logger.info(
                "Categoría asignada a producto creado",
                extra={"product_id": product_id, "category": category_name},
            )
        except Exception as exc:
            logger.warning(
                "Error asignando categoría tras crear producto",
                exc_info=exc,
                extra={"product_id": product_id, "category": category_name},
            )

    return JSONResponse(
        content=_ok(created, "Producto creado."),
        status_code=status.HTTP_201_CREATED,
    )


@router_products.put("/{product_id}")
async def update_product(product_id: int, data: dict) -> JSONResponse:
    """
    Actualiza un producto existente en Dolibarr.

    Separa ``array_options`` (extrafields) del payload estándar y los persiste
    via BD directa para evitar el error MySQL "Field X doesn't have a default
    value" que devuelve Dolibarr al actualizar extrafields via REST.

    Si el payload incluye ``category_name``, asigna el producto a esa categoría
    tras la actualización. La categoría debe existir previamente con ese nombre
    exacto; si no existe se devuelve 422.

    Args:
        product_id: ID del producto en Dolibarr.
        data:       campos a actualizar (puede incluir array_options y category_name).

    Returns:
        Respuesta estándar con el producto actualizado.
    """
    array_options: dict = data.pop("array_options", None) or {}
    category_name: str = (data.pop("category_name", None) or "").strip()

    svc, cat_svc = await _get_services_async()

    # Pre-validate category before updating
    category_id: int | None = None
    if category_name:
        cat = await cat_svc.find_category_by_name(category_name)
        if cat is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"La categoría '{category_name}' no existe en Dolibarr. "
                    "Créala primero desde el módulo de Categorías."
                ),
            )
        category_id = int(cat["id"])

    try:
        updated = await svc.update_product(product_id, data)
    except IntegrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )

    if array_options:
        try:
            db = await _get_extrafield_db()
            await db.update_product_extrafields(
                product_id=product_id,
                array_options=array_options,
                elementtype="product",
            )
        except HTTPException:
            pass  # BD no configurada — extrafields omitidos sin romper la respuesta
        except Exception as exc:
            logger.warning(
                "Extrafields no guardados tras actualizar producto",
                exc_info=exc,
                extra={"product_id": product_id},
            )

    if category_id:
        try:
            await cat_svc.assign_product(category_id, product_id)
            logger.info(
                "Categoría asignada a producto actualizado",
                extra={"product_id": product_id, "category": category_name},
            )
        except Exception as exc:
            logger.warning(
                "Error asignando categoría tras actualizar producto",
                exc_info=exc,
                extra={"product_id": product_id, "category": category_name},
            )

    return JSONResponse(content=_ok(updated, "Producto actualizado."))


@router_products.delete("/{product_id}")
async def delete_product(product_id: int) -> JSONResponse:
    """
    Elimina un producto de Dolibarr.

    Args:
        product_id: ID del producto a eliminar.

    Returns:
        Respuesta estándar con confirmación de eliminación.
    """
    svc = await _get_service_async()
    try:
        await svc.delete_product(product_id)
    except IntegrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content={"success": True, "message": "Producto eliminado."})


@router_products.delete("", response_model=dict, status_code=status.HTTP_200_OK)
async def delete_products_bulk(ids: list[int] = Body(...)) -> JSONResponse:
    """Elimina múltiples productos Dolibarr por sus IDs."""
    if not ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La lista de IDs no puede estar vacía.",
        )
    svc = await _get_service_async()
    errors: list[dict] = []
    semaphore = asyncio.Semaphore(10)  # Limitar concurrencia a 10

    async def _delete_one(product_id: int) -> tuple[bool, dict | None]:
        async with semaphore:
            try:
                await svc.delete_product(product_id)
                return True, None
            except Exception as exc:
                logger.warning(
                    "Fallo eliminando producto Dolibarr en bulk",
                    extra={"id": product_id, "exc": str(exc)},
                )
                return False, {"id": product_id, "error": str(exc)}

    try:
        delete_results = await asyncio.gather(*[_delete_one(pid) for pid in ids])
        deleted = sum(1 for ok, _ in delete_results if ok)
        errors.extend([err for ok, err in delete_results if not ok and err is not None])

        failed = len(errors)
        result = {"deleted": deleted, "failed": failed, "errors": errors}
        msg = (
            f"{deleted} eliminados, {failed} fallidos."
        )
        return JSONResponse(content=_ok(result, msg))
    except Exception as exc:
        logger.error("Error en eliminación masiva de productos Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc),
        )


@router_products.post("/{product_id}/image")
async def upload_image(product_id: int, file: UploadFile) -> JSONResponse:
    """
    Sube una imagen a un producto de Dolibarr.

    Valida tipo MIME (jpeg/png/webp) y tamaño (máx 5 MB) antes de enviar.

    Args:
        product_id: ID del producto en Dolibarr.
        file:       archivo de imagen (multipart).

    Returns:
        Respuesta estándar con el resultado de Dolibarr.
    """
    svc = await _get_service_async()

    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Tipo de archivo no permitido: {file.content_type}. "
                   f"Se aceptan: jpeg, png, webp.",
        )

    content = await file.read()
    if len(content) > _MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"La imagen supera el límite de 5 MB ({len(content)} bytes recibidos).",
        )

    suffix = Path(file.filename or "imagen.jpg").suffix or ".jpg"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        result = await svc.upload_image(product_id, tmp_path)
    except IntegrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    return JSONResponse(content=_ok(result, "Imagen subida correctamente."))


_MAX_CSV_BYTES = 10 * 1024 * 1024  # 10 MB


@router_products.post("/csv-preview")
async def csv_preview(file: UploadFile) -> JSONResponse:
    """
    Pre-analiza un CSV de productos y devuelve cabeceras + filas de muestra.

    No requiere conexión a Dolibarr. Sirve para que el frontend construya
    la UI de mapeo de columnas antes de lanzar la importación real.

    Args:
        file: archivo CSV (multipart).

    Returns:
        CsvImportPreview con headers, preview (≤5 filas) y total_rows.
    """
    content = await file.read()
    if len(content) > _MAX_CSV_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El CSV supera el límite de 10 MB ({len(content)} bytes).",
        )

    svc = DolibarrProductService.__new__(DolibarrProductService)
    try:
        preview_data = svc.parse_csv_preview(content, preview_rows=5)
    except Exception as exc:
        logger.error("Error pre-analizando CSV", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No se pudo parsear el CSV: {exc}",
        )

    result = CsvImportPreview(**preview_data)
    return JSONResponse(content=_ok(result.model_dump(), "CSV analizado."))


@router_products.post("/import", status_code=status.HTTP_202_ACCEPTED)
async def import_from_csv(
    file: UploadFile,
    mapping: str = Form(...),
    overwrite: bool = Form(default=False),
    category_column: str = Form(default=""),
) -> JSONResponse:
    """
    Inicia la importación masiva de productos desde CSV como tarea Celery asíncrona.

    Valida el CSV, el mapeo y las categorías de forma síncrona. Si todo es correcto,
    encola la tarea y devuelve un ``task_id`` inmediatamente (HTTP 202).
    El cliente debe hacer polling a ``GET /import/{task_id}/status`` para consultar
    el progreso y obtener los resultados cuando la tarea termine.

    Args:
        file:            CSV de productos (multipart).
        mapping:         JSON string con el mapeo columna → campo Dolibarr.
        overwrite:       si True, actualiza productos que ya existen en Dolibarr.
        category_column: nombre de la columna CSV que contiene el nombre de categoría.

    Returns:
        HTTP 202 con ``{task_id, status: "pending"}``.
    """
    from workers.tasks import importar_productos_dolibarr  # noqa: PLC0415

    content = await file.read()
    if len(content) > _MAX_CSV_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El CSV supera el límite de 10 MB ({len(content)} bytes).",
        )

    try:
        mapping_dict: dict[str, str] = json.loads(mapping)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"El campo 'mapping' no es JSON válido: {exc}",
        )

    if not any(v == "ref" for v in mapping_dict.values()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El mapeo debe incluir al menos una columna asignada al campo 'ref'.",
        )

    cat_col = category_column.strip()
    _, cat_svc = await _get_services_async()

    # Pre-validar categorías de forma síncrona antes de encolar
    category_name_to_id: dict[str, int] = {}
    if cat_col:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
            delimiter = dialect.delimiter
        except csv.Error:
            first_line = text.split("\n")[0]
            counts = {d: first_line.count(d) for d in (";", ",", "\t", "|")}
            best = max(counts, key=lambda d: counts[d])
            delimiter = best if counts[best] > 0 else ","

        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        unique_names: set[str] = set()
        for row in reader:
            name = (row.get(cat_col) or "").strip()
            if name:
                unique_names.add(name)

        missing: list[str] = []
        for name in unique_names:
            cat = await cat_svc.find_category_by_name(name)
            if cat is None:
                missing.append(name)
            else:
                category_name_to_id[name] = int(cat["id"])

        if missing:
            missing_list = ", ".join(f"'{c}'" for c in sorted(missing))
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Categorías no encontradas en Dolibarr: {missing_list}. "
                    "Créalas primero desde el módulo de Categorías con el nombre exacto."
                ),
            )

    dolibarr_url, dolibarr_api_key = await _get_dolibarr_credentials()

    task_id = str(uuid.uuid4())
    settings = get_settings()
    redis_client: aioredis.Redis | None = None
    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await redis_client.set(
            f"dolibarr_import:{task_id}",
            json.dumps({"task_id": task_id, "status": "pending", "progress": {"processed": 0, "total": 0}, "message": "En cola...", "results": None}),
            ex=86400,
        )
    finally:
        if redis_client:
            await redis_client.aclose()

    csv_b64 = base64.b64encode(content).decode()

    importar_productos_dolibarr.delay(
        task_id,
        csv_b64,
        mapping_dict,
        overwrite,
        cat_col,
        category_name_to_id,
        dolibarr_url,
        dolibarr_api_key,
    )

    logger.info(
        "Importación CSV Dolibarr encolada",
        extra={"task_id": task_id, "mapped_fields": len(mapping_dict), "overwrite": overwrite},
    )

    return JSONResponse(
        content=_ok({"task_id": task_id, "status": "pending"}, "Importación iniciada. Consulta el estado con el task_id."),
        status_code=status.HTTP_202_ACCEPTED,
    )


@router_products.get("/import/{task_id}/status")
async def get_import_status(task_id: str) -> JSONResponse:
    """
    Consulta el estado de una tarea de importación CSV en curso o completada.

    Args:
        task_id: UUID de la tarea devuelto por ``POST /import``.

    Returns:
        Dict con task_id, status, progress, message y results (cuando completed).

    Raises:
        HTTPException 404: si el task_id no existe o ha expirado (TTL 24 h).
    """
    settings = get_settings()
    redis_client: aioredis.Redis | None = None
    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        raw = await redis_client.get(f"dolibarr_import:{task_id}")
    finally:
        if redis_client:
            await redis_client.aclose()

    if not raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tarea '{task_id}' no encontrada o expirada (TTL 24 h).",
        )

    return JSONResponse(content=_ok(json.loads(raw), "Estado de importación obtenido."))


@router_products.get("/{product_id}")
async def get_product(product_id: int) -> JSONResponse:
    """
    Obtiene un producto de Dolibarr por su ID.

    Args:
        product_id: ID del producto en Dolibarr.

    Returns:
        Respuesta estándar con los datos del producto.
    """
    svc = await _get_service_async()
    try:
        product = await svc.get_product(product_id)
    except IntegrationError as exc:
        if exc.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Producto {product_id} no encontrado en Dolibarr.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(product, "Producto obtenido."))


@router_products.post("/sync")
async def sync_from_job(request: SyncFromJobRequest) -> JSONResponse:
    """
    Sincroniza productos de un job Harvist completado con Dolibarr.

    Para cada código se intenta crear o actualizar el producto y subir su imagen.
    La operación es resiliente: errores en un producto no detienen el resto.

    Args:
        request: job_id, product_codes y flag overwrite.

    Returns:
        Respuesta estándar con la lista de resultados por producto.
    """
    svc = await _get_service_async()
    storage = get_storage_service()

    logger.info(
        "Iniciando sync Dolibarr",
        extra={
            "job_id": request.job_id,
            "n_products": len(request.product_codes),
            "overwrite": request.overwrite,
        },
    )

    results = await svc.sync_from_job(
        job_id=request.job_id,
        product_codes=request.product_codes,
        overwrite=request.overwrite,
        storage=storage,
    )

    return JSONResponse(
        content=_ok(results, f"Sincronización completada: {len(results)} productos procesados.")
    )


# ── Categorías ──────────────────────────────────────────────────────


categories_router = APIRouter(prefix="/dolibarr/categories", tags=["dolibarr-categories"])


async def _get_category_service() -> DolibarrCategoryService:
    """
    Construye y devuelve una instancia de DolibarrCategoryService.

    Obtiene las credenciales desde Redis (si están configuradas) o desde .env.

    Raises:
        HTTPException 503: si Dolibarr no está configurado.
    """
    settings = get_settings()
    try:
        url, api_key = await _get_dolibarr_credentials()
        client = DolibarrClient(settings, override_url=url, override_api_key=api_key)
    except IntegrationNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_NOT_CONFIGURED_MSG,
        )
    return DolibarrCategoryService(client)


@categories_router.get("")
async def list_categories(
    type: str = Query(default="product"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    """
    Lista categorías de Dolibarr con paginación.

    Args:
        type:   tipo de categoría (product, customer, supplier, member).
        limit:  máximo de categorías por página.
        offset: desplazamiento desde el inicio.

    Returns:
        PaginatedResponse con las categorías encontradas.
    """
    svc = await _get_category_service()
    try:
        items = await svc.list_categories(type=type, limit=limit, offset=offset)
    except IntegrationError as exc:
        logger.error("Error listando categorías Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(PaginatedResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    ).model_dump()))


@categories_router.get("/tree")
async def get_tree(
    type: str = Query(default="product"),
) -> JSONResponse:
    """
    Obtiene el árbol jerárquico completo de categorías.

    Args:
        type: tipo de categoría.

    Returns:
        Respuesta estándar con lista anidada de nodos.
    """
    svc = await _get_category_service()
    try:
        tree = await svc.get_tree(type=type)
    except IntegrationError as exc:
        logger.error("Error obteniendo árbol de categorías Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(tree, "Árbol de categorías obtenido."))


@categories_router.get("/{category_id}")
async def get_category(category_id: int) -> JSONResponse:
    """
    Obtiene una categoría de Dolibarr por su ID.

    Args:
        category_id: ID de la categoría en Dolibarr.

    Returns:
        Respuesta estándar con los datos de la categoría.
    """
    svc = await _get_category_service()
    try:
        category = await svc.get_category(category_id)
    except IntegrationError as exc:
        if exc.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Categoría {category_id} no encontrada en Dolibarr.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(category, "Categoría obtenida."))


@categories_router.post("", status_code=status.HTTP_201_CREATED)
async def create_category(
    label: str = Query(...),
    type: str = Query(default="product"),
    parent_id: int | None = Query(default=None),
    description: str = Query(default=""),
) -> JSONResponse:
    """
    Crea una categoría en Dolibarr.

    Args:
        label:       nombre de la categoría.
        type:        tipo de categoría.
        parent_id:   ID de la categoría padre (opcional).
        description: descripción (opcional).

    Returns:
        Respuesta estándar (201) con la categoría creada.
    """
    svc = await _get_category_service()
    try:
        created = await svc.create_category(
            label=label,
            type=type,
            parent_id=parent_id,
            description=description,
        )
    except IntegrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(
        content=_ok(created, "Categoría creada."),
        status_code=status.HTTP_201_CREATED,
    )


@categories_router.put("/{category_id}")
async def update_category(category_id: int, data: dict) -> JSONResponse:
    """
    Actualiza una categoría existente en Dolibarr.

    Args:
        category_id: ID de la categoría en Dolibarr.
        data:        campos a actualizar.

    Returns:
        Respuesta estándar con la categoría actualizada.
    """
    svc = await _get_category_service()
    try:
        updated = await svc.update_category(category_id, data)
    except IntegrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(updated, "Categoría actualizada."))


@categories_router.delete("/{category_id}")
async def delete_category(category_id: int) -> JSONResponse:
    """
    Elimina una categoría de Dolibarr.

    Args:
        category_id: ID de la categoría a eliminar.

    Returns:
        Respuesta estándar con confirmación de eliminación.
    """
    svc = await _get_category_service()
    try:
        await svc.delete_category(category_id)
    except IntegrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content={"success": True, "message": "Categoría eliminada."})


@categories_router.post("/{category_id}/products/{product_id}")
async def assign_product(category_id: int, product_id: int) -> JSONResponse:
    """
    Asigna un producto a una categoría.

    Args:
        category_id: ID de la categoría.
        product_id:  ID del producto a asignar.

    Returns:
        Respuesta estándar con confirmación.
    """
    svc = await _get_category_service()
    try:
        await svc.assign_product(category_id, product_id)
    except IntegrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content={"success": True, "message": "Producto asignado."})


@categories_router.delete("/{category_id}/products/{product_id}")
async def remove_product(category_id: int, product_id: int) -> JSONResponse:
    """
    Elimina un producto de una categoría.

    Args:
        category_id: ID de la categoría.
        product_id:  ID del producto a remover.

    Returns:
        Respuesta estándar con confirmación.
    """
    svc = await _get_category_service()
    try:
        await svc.remove_product(category_id, product_id)
    except IntegrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content={"success": True, "message": "Producto eliminado de categoría."})


@categories_router.get("/{category_id}/products")
async def list_products_in_category(
    category_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    """
    Lista productos asignados a una categoría.

    Args:
        category_id: ID de la categoría.
        limit:       máximo de productos por página.
        offset:      desplazamiento desde el inicio.

    Returns:
        PaginatedResponse con los productos en la categoría.
    """
    svc = await _get_category_service()
    try:
        items = await svc.list_products_in_category(
            category_id=category_id,
            limit=limit,
            offset=offset,
        )
    except IntegrationError as exc:
        logger.error("Error listando productos en categoría Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(PaginatedResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    ).model_dump()))


# ── Terceros ─────────────────────────────────────────────────────


thirdparties_router = APIRouter(prefix="/dolibarr/thirdparties", tags=["dolibarr-thirdparties"])


async def _get_thirdparty_service() -> DolibarrThirdpartyService:
    """
    Construye y devuelve una instancia de DolibarrThirdpartyService.
    Lee credenciales desde Redis o .env.

    Raises:
        HTTPException 503: si Dolibarr no está configurado.
    """
    settings = get_settings()
    try:
        url, api_key = await _get_dolibarr_credentials()
        client = DolibarrClient(settings, override_url=url, override_api_key=api_key)
    except IntegrationNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_NOT_CONFIGURED_MSG,
        )
    return DolibarrThirdpartyService(client)


@thirdparties_router.get("")
async def list_thirdparties(
    mode: str = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    """
    Lista terceros de Dolibarr con paginación y filtro por modo.

    Args:
        mode:   "all" para todos, "customers" para clientes, "suppliers" para proveedores.
        limit:  máximo de terceros por página.
        offset: desplazamiento desde el inicio.

    Returns:
        PaginatedResponse con los terceros encontrados.
    """
    svc = await _get_thirdparty_service()
    try:
        items = await svc.list_thirdparties(
            mode=mode,
            limit=limit,
            offset=offset,
        )
    except IntegrationError as exc:
        logger.error("Error listando terceros en Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(PaginatedResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    ).model_dump()))


@thirdparties_router.get("/search")
async def search_thirdparties(
    name: str = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
) -> JSONResponse:
    """
    Busca terceros por nombre.

    Args:
        name:  nombre o fragmento a buscar.
        limit: máximo de resultados.

    Returns:
        Respuesta estándar con lista de terceros coincidentes.
    """
    svc = await _get_thirdparty_service()
    try:
        items = await svc.search_thirdparty(name=name, limit=limit)
    except IntegrationError as exc:
        logger.error("Error buscando terceros en Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(items, f"Se encontraron {len(items)} terceros."))


@thirdparties_router.get("/{thirdparty_id}")
async def get_thirdparty(thirdparty_id: int) -> JSONResponse:
    """
    Obtiene un tercero por ID.

    Args:
        thirdparty_id: ID del tercero en Dolibarr.

    Returns:
        Respuesta estándar con los datos del tercero.
    """
    svc = await _get_thirdparty_service()
    try:
        thirdparty = await svc.get_thirdparty(thirdparty_id)
    except IntegrationError as exc:
        if exc.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tercero {thirdparty_id} no encontrado en Dolibarr.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(thirdparty, "Tercero obtenido."))


@thirdparties_router.post("", status_code=status.HTTP_201_CREATED)
async def create_thirdparty(data: dict[str, Any]) -> JSONResponse:
    """
    Crea un tercero en Dolibarr.

    Args:
        data: datos del tercero. Campos: name (obligatorio), client, supplier,
              address, zip, town, country_id, phone, email, siret, tva_intra,
              code_client, code_fournisseur.

    Returns:
        Respuesta estándar (201) con el tercero creado.
    """
    svc = await _get_thirdparty_service()
    try:
        created = await svc.create_thirdparty(data)
    except IntegrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(
        content=_ok(created, "Tercero creado."),
        status_code=status.HTTP_201_CREATED,
    )


@thirdparties_router.put("/{thirdparty_id}")
async def update_thirdparty(
    thirdparty_id: int,
    data: dict[str, Any],
) -> JSONResponse:
    """
    Actualiza un tercero existente.

    Args:
        thirdparty_id: ID del tercero en Dolibarr.
        data:          campos a actualizar.

    Returns:
        Respuesta estándar con el tercero actualizado.
    """
    svc = await _get_thirdparty_service()
    try:
        updated = await svc.update_thirdparty(thirdparty_id, data)
    except IntegrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(updated, "Tercero actualizado."))


@thirdparties_router.delete("/{thirdparty_id}")
async def delete_thirdparty(thirdparty_id: int) -> JSONResponse:
    """
    Elimina un tercero de Dolibarr.

    Args:
        thirdparty_id: ID del tercero a eliminar.

    Returns:
        Respuesta estándar con confirmación de eliminación o error 409
        si tiene registros asociados.
    """
    svc = await _get_thirdparty_service()
    try:
        success = await svc.delete_thirdparty(thirdparty_id)
    except IntegrationError as exc:
        logger.error("Error eliminando tercero en Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No se puede eliminar el tercero porque tiene registros "
                "asociados en Dolibarr."
            ),
        )
    return JSONResponse(content={"success": True, "message": "Tercero eliminado."})


@thirdparties_router.get("/{thirdparty_id}/invoices")
async def get_thirdparty_invoices(
    thirdparty_id: int,
    type: str = Query(default="customer"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    """
    Lista facturas asociadas a un tercero.

    Args:
        thirdparty_id: ID del tercero.
        type:          "customer" para facturas de cliente, "supplier" para proveedor.
        limit:         máximo de facturas por página.
        offset:        desplazamiento desde el inicio.

    Returns:
        PaginatedResponse con las facturas del tercero.
    """
    svc = await _get_thirdparty_service()
    try:
        items = await svc.get_thirdparty_invoices(
            thirdparty_id=thirdparty_id,
            type=type,
            limit=limit,
            offset=offset,
        )
    except IntegrationError as exc:
        logger.error("Error obteniendo facturas del tercero en Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(PaginatedResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    ).model_dump()))


@thirdparties_router.get("/{thirdparty_id}/orders")
async def get_thirdparty_orders(
    thirdparty_id: int,
    type: str = Query(default="customer"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    """
    Lista pedidos asociados a un tercero.

    Args:
        thirdparty_id: ID del tercero.
        type:          "customer" para pedidos de cliente, "supplier" para proveedor.
        limit:         máximo de pedidos por página.
        offset:        desplazamiento desde el inicio.

    Returns:
        PaginatedResponse con los pedidos del tercero.
    """
    svc = await _get_thirdparty_service()
    try:
        items = await svc.get_thirdparty_orders(
            thirdparty_id=thirdparty_id,
            type=type,
            limit=limit,
            offset=offset,
        )
    except IntegrationError as exc:
        logger.error("Error obteniendo pedidos del tercero en Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(PaginatedResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    ).model_dump()))


# ── Pedidos ──────────────────────────────────────────────────────


orders_router = APIRouter(prefix="/dolibarr/orders", tags=["dolibarr-orders"])


async def _get_order_service() -> DolibarrOrderService:
    """
    Construye y devuelve una instancia de DolibarrOrderService.
    Lee credenciales desde Redis o .env.

    Raises:
        HTTPException 503: si Dolibarr no está configurado.
    """
    settings = get_settings()
    try:
        url, api_key = await _get_dolibarr_credentials()
        client = DolibarrClient(settings, override_url=url, override_api_key=api_key)
    except IntegrationNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_NOT_CONFIGURED_MSG,
        )
    return DolibarrOrderService(client)


@orders_router.get("")
async def list_orders(
    type: str = Query(default="customer"),
    status: int | None = Query(default=None),
    thirdparty_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    """
    Lista pedidos de cliente o proveedor.

    Args:
        type: "customer" (pedidos de cliente) o "supplier" (pedidos de proveedor).
        status: filtro opcional por estado del pedido.
        thirdparty_id: filtro opcional por ID del tercero.
        limit: máximo de pedidos por página.
        offset: desplazamiento desde el inicio.

    Returns:
        PaginatedResponse con los pedidos encontrados.
    """
    svc = await _get_order_service()
    try:
        items = await svc.list_orders(
            type=type, limit=limit, offset=offset, status=status, thirdparty_id=thirdparty_id
        )
    except IntegrationError as exc:
        logger.error("Error listando pedidos Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(PaginatedResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    ).model_dump()))


@orders_router.get("/{order_id}")
async def get_order(
    order_id: int,
    type: str = Query(default="customer"),
) -> dict[str, Any]:
    """
    Obtiene un pedido por ID.

    Args:
        order_id: ID del pedido.
        type: "customer" o "supplier".

    Returns:
        Diccionario con datos del pedido.
    """
    svc = await _get_order_service()
    try:
        order = await svc.get_order(order_id, type=type)
    except IntegrationError as exc:
        if "404" in str(exc) or "not found" in str(exc).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        logger.error("Error obteniendo pedido Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return _ok(order)


@orders_router.post("", status_code=status.HTTP_201_CREATED)
async def create_order(
    type: str = Query(default="customer"),
    data: dict = None,
) -> dict[str, Any]:
    """
    Crea un pedido.

    Campos mínimos en data:
      - socid: ID del tercero
      - date: timestamp del pedido

    Args:
        type: "customer" o "supplier".
        data: diccionario con los datos del pedido.

    Returns:
        Diccionario con el pedido creado (incluye ID asignado).
    """
    if not data:
        data = {}
    svc = await _get_order_service()
    try:
        order = await svc.create_order(data, type=type)
    except IntegrationError as exc:
        logger.error("Error creando pedido Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return _ok(order)


@orders_router.post("/{order_id}/lines", status_code=status.HTTP_201_CREATED)
async def add_order_line(
    order_id: int,
    type: str = Query(default="customer"),
    data: dict = None,
) -> dict[str, Any]:
    """
    Añade una línea a un pedido existente.

    Campos mínimos en data:
      - fk_product: ID del producto (o desc si no hay producto)
      - qty: cantidad
      - subprice: precio unitario

    Args:
        order_id: ID del pedido.
        type: "customer" o "supplier".
        data: diccionario con datos de la línea.

    Returns:
        Diccionario con la línea creada.
    """
    if not data:
        data = {}
    svc = await _get_order_service()
    try:
        line = await svc.add_order_line(order_id, data, type=type)
    except IntegrationError as exc:
        logger.error("Error añadiendo línea a pedido Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return _ok(line)


@orders_router.patch("/{order_id}/status")
async def update_order_status(
    order_id: int,
    type: str = Query(default="customer"),
    data: dict = None,
) -> dict[str, Any]:
    """
    Cambia el estado de un pedido.

    Mapeo customer:
      1 → Validado, 2 → Entregado, 3 → Cancelado

    Mapeo supplier:
      1 → Validado, 4 → Recibido, 5 → Cancelado

    Args:
        order_id: ID del pedido.
        type: "customer" o "supplier".
        data: diccionario con el campo "status" (int).

    Returns:
        Diccionario con el pedido actualizado.
    """
    if not data:
        data = {}
    status_value = data.get("status")
    if status_value is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Campo 'status' requerido en body",
        )
    svc = await _get_order_service()
    try:
        order = await svc.update_order_status(order_id, status_value, type=type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except IntegrationError as exc:
        logger.error("Error actualizando estado de pedido Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return _ok(order)


@orders_router.delete("/{order_id}")
async def delete_order(
    order_id: int,
    type: str = Query(default="customer"),
) -> dict[str, Any]:
    """
    Elimina un pedido en estado borrador.

    Args:
        order_id: ID del pedido.
        type: "customer" o "supplier".

    Returns:
        Mensaje de éxito.
    """
    svc = await _get_order_service()
    try:
        success = await svc.delete_order(order_id, type=type)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No se puede eliminar pedido no en estado borrador",
            )
    except IntegrationError as exc:
        if "409" in str(exc) or "conflict" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            )
        logger.error("Error eliminando pedido Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return _ok({"deleted": True}, message="Pedido eliminado exitosamente")


invoices_router = APIRouter(prefix="/dolibarr/invoices", tags=["dolibarr-invoices"])


async def _get_invoice_service() -> DolibarrInvoiceService:
    """
    Construye y devuelve una instancia de DolibarrInvoiceService.
    Lee credenciales desde Redis o .env.

    Raises:
        HTTPException 503: si Dolibarr no está configurado.
    """
    settings = get_settings()
    try:
        url, api_key = await _get_dolibarr_credentials()
        client = DolibarrClient(settings, override_url=url, override_api_key=api_key)
    except IntegrationNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_NOT_CONFIGURED_MSG,
        )
    return DolibarrInvoiceService(client)


@invoices_router.get("")
async def list_invoices(
    type: str = Query(default="customer"),
    invoice_status: int | None = Query(default=None, alias="status"),
    thirdparty_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    """
    Lista facturas de cliente o proveedor.

    Args:
        type: "customer" (facturas cliente) o "supplier" (facturas proveedor).
        invoice_status: filtro opcional por estado de la factura.
        thirdparty_id: filtro opcional por ID del tercero.
        limit: máximo de facturas por página.
        offset: desplazamiento desde el inicio.

    Returns:
        PaginatedResponse con las facturas encontradas.
    """
    svc = await _get_invoice_service()
    try:
        items = await svc.list_invoices(
            type=type, limit=limit, offset=offset, status=invoice_status, thirdparty_id=thirdparty_id
        )
    except IntegrationError as exc:
        logger.error("Error listando facturas Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(PaginatedResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    ).model_dump()))


@invoices_router.get("/{invoice_id}")
async def get_invoice(
    invoice_id: int,
    type: str = Query(default="customer"),
) -> dict[str, Any]:
    """
    Obtiene una factura por ID.

    Args:
        invoice_id: ID de la factura.
        type: "customer" o "supplier".

    Returns:
        Diccionario con datos de la factura.
    """
    svc = await _get_invoice_service()
    try:
        invoice = await svc.get_invoice(invoice_id, type=type)
    except IntegrationError as exc:
        if "404" in str(exc) or "not found" in str(exc).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        logger.error("Error obteniendo factura Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return _ok(invoice)


@invoices_router.post("", status_code=status.HTTP_201_CREATED)
async def create_invoice(
    type: str = Query(default="customer"),
    data: dict = None,
) -> dict[str, Any]:
    """
    Crea una factura.

    Campos mínimos en data:
      - socid: ID del tercero
      - date: timestamp de la factura

    Args:
        type: "customer" o "supplier".
        data: diccionario con los datos de la factura.

    Returns:
        Diccionario con la factura creada (incluye ID asignado).
    """
    if not data:
        data = {}
    svc = await _get_invoice_service()
    try:
        invoice = await svc.create_invoice(data, type=type)
    except IntegrationError as exc:
        logger.error("Error creando factura Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return _ok(invoice)


@invoices_router.post("/{invoice_id}/lines", status_code=status.HTTP_201_CREATED)
async def add_invoice_line(
    invoice_id: int,
    type: str = Query(default="customer"),
    data: dict = None,
) -> dict[str, Any]:
    """
    Añade una línea a una factura existente.

    Campos mínimos en data:
      - fk_product: ID del producto (o desc si no hay producto)
      - qty: cantidad
      - subprice: precio unitario
      - tva_tx: tasa de impuesto

    Args:
        invoice_id: ID de la factura.
        type: "customer" o "supplier".
        data: diccionario con datos de la línea.

    Returns:
        Diccionario con la línea creada.
    """
    if not data:
        data = {}
    svc = await _get_invoice_service()
    try:
        line = await svc.add_invoice_line(invoice_id, data, type=type)
    except IntegrationError as exc:
        logger.error("Error añadiendo línea a factura Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return _ok(line)


@invoices_router.post("/{invoice_id}/validate")
async def validate_invoice(
    invoice_id: int,
    type: str = Query(default="customer"),
) -> dict[str, Any]:
    """
    Valida una factura (pasa de borrador a validada).

    Args:
        invoice_id: ID de la factura.
        type: "customer" o "supplier".

    Returns:
        Diccionario con la factura validada.
    """
    svc = await _get_invoice_service()
    try:
        invoice = await svc.validate_invoice(invoice_id, type=type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except IntegrationError as exc:
        logger.error("Error validando factura Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return _ok(invoice)


@invoices_router.post("/{invoice_id}/send")
async def send_invoice_by_email(
    invoice_id: int,
    type: str = Query(default="customer"),
    data: dict = None,
) -> dict[str, Any]:
    """
    Envía una factura por email desde Dolibarr.

    Campos en data:
      - email: dirección de email (requerido)
      - subject: asunto (opcional)
      - message: mensaje (opcional)

    Args:
        invoice_id: ID de la factura.
        type: "customer" o "supplier".
        data: diccionario con email y opcionales subject/message.

    Returns:
        Mensaje de éxito.
    """
    svc = await _get_invoice_service()
    if not data:
        data = {}
    email = data.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Campo 'email' requerido en body",
        )
    try:
        success = await svc.send_by_email(
            invoice_id,
            email,
            type=type,
            subject=data.get("subject", ""),
            message=data.get("message", ""),
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Factura no puede ser enviada",
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except IntegrationError as exc:
        logger.error("Error enviando factura Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return _ok({"sent": True}, message="Factura enviada exitosamente")


@invoices_router.post("/{invoice_id}/pay")
async def mark_invoice_as_paid(
    invoice_id: int,
    type: str = Query(default="customer"),
    data: dict = None,
) -> dict[str, Any]:
    """
    Registra el pago de una factura.

    Campos en data:
      - payment_date: timestamp del pago (requerido)
      - payment_type_id: ID del tipo de pago (requerido)
      - bank_account_id: ID de la cuenta bancaria (requerido)
      - amount: monto pagado (opcional)

    Args:
        invoice_id: ID de la factura.
        type: "customer" o "supplier".
        data: diccionario con los datos del pago.

    Returns:
        Diccionario con el registro de pago.
    """
    svc = await _get_invoice_service()
    if not data:
        data = {}
    required_fields = ["payment_date", "payment_type_id", "bank_account_id"]
    if not all(f in data for f in required_fields):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Campos requeridos: {', '.join(required_fields)}",
        )
    try:
        payment = await svc.mark_as_paid(
            invoice_id,
            data["payment_date"],
            data["payment_type_id"],
            data["bank_account_id"],
            amount=data.get("amount"),
            type=type,
        )
    except IntegrationError as exc:
        logger.error("Error registrando pago Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return _ok(payment)


@invoices_router.delete("/{invoice_id}")
async def delete_invoice(
    invoice_id: int,
    type: str = Query(default="customer"),
) -> dict[str, Any]:
    """
    Elimina una factura en estado borrador.

    Args:
        invoice_id: ID de la factura.
        type: "customer" o "supplier".

    Returns:
        Mensaje de éxito.
    """
    svc = await _get_invoice_service()
    try:
        success = await svc.delete_invoice(invoice_id, type=type)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No se puede eliminar factura no en estado borrador",
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except IntegrationError as exc:
        if "409" in str(exc) or "conflict" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            )
        logger.error("Error eliminando factura Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return _ok({"deleted": True}, message="Factura eliminada exitosamente")


stocks_router = APIRouter(prefix="/dolibarr/stocks", tags=["dolibarr-stocks"])


async def _get_stock_service() -> DolibarrStockService:
    """
    Construye y devuelve una instancia de DolibarrStockService.
    Lee credenciales desde Redis o .env.

    Raises:
        HTTPException 503: si Dolibarr no está configurado.
    """
    settings = get_settings()
    try:
        url, api_key = await _get_dolibarr_credentials()
        client = DolibarrClient(settings, override_url=url, override_api_key=api_key)
    except IntegrationNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_NOT_CONFIGURED_MSG,
        )
    return DolibarrStockService(client)


@stocks_router.get("/warehouses")
async def list_warehouses(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    """
    Lista almacenes de Dolibarr con paginación.

    Args:
        limit:  máximo de almacenes por página.
        offset: desplazamiento desde el inicio.

    Returns:
        PaginatedResponse con los almacenes encontrados.
    """
    svc = await _get_stock_service()
    try:
        items = await svc.list_warehouses(limit=limit, offset=offset)
    except IntegrationError as exc:
        logger.error("Error listando almacenes Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(PaginatedResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    ).model_dump()))


@stocks_router.get("/warehouses/{warehouse_id}")
async def get_warehouse(warehouse_id: int) -> JSONResponse:
    """
    Obtiene un almacén de Dolibarr por su ID.

    Args:
        warehouse_id: ID del almacén en Dolibarr.

    Returns:
        Respuesta estándar con los datos del almacén.
    """
    svc = await _get_stock_service()
    try:
        warehouse = await svc.get_warehouse(warehouse_id)
    except IntegrationError as exc:
        if exc.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Almacén {warehouse_id} no encontrado en Dolibarr.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(warehouse, "Almacén obtenido."))


@stocks_router.get("/products/{product_id}")
async def get_product_stock(product_id: int) -> JSONResponse:
    """
    Obtiene el stock actual de un producto desglosado por almacén.

    Args:
        product_id: ID del producto en Dolibarr.

    Returns:
        Respuesta estándar con stock_total y desglose por almacén.
    """
    svc = await _get_stock_service()
    try:
        stock_info = await svc.get_product_stock(product_id)
    except IntegrationError as exc:
        if exc.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Producto {product_id} no encontrado en Dolibarr.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(stock_info, "Stock de producto obtenido."))


@stocks_router.get("/movements")
async def list_movements(
    product_id: int | None = Query(default=None),
    warehouse_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    """
    Lista movimientos de stock con filtros opcionales.

    Args:
        product_id: Filtrar por producto (opcional).
        warehouse_id: Filtrar por almacén (opcional).
        limit: máximo de movimientos por página.
        offset: desplazamiento desde el inicio.

    Returns:
        PaginatedResponse con los movimientos encontrados.
    """
    svc = await _get_stock_service()
    try:
        items = await svc.get_stock_movements(
            product_id=product_id,
            warehouse_id=warehouse_id,
            limit=limit,
            offset=offset,
        )
    except IntegrationError as exc:
        logger.error("Error listando movimientos de stock Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(PaginatedResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    ).model_dump()))


@stocks_router.post("/movements", status_code=status.HTTP_201_CREATED)
async def add_movement(data: dict) -> JSONResponse:
    """
    Registra un movimiento de stock en Dolibarr.

    Body esperado:
      - product_id: int
      - warehouse_id: int
      - qty: float (puede ser negativo)
      - movement_type: int (0=entrada, 1=salida, 2=corrección, 3=transferencia)
      - label: str (opcional)
      - price: float (opcional)

    Returns:
        Respuesta estándar (201) con el movimiento creado.
    """
    svc = await _get_stock_service()
    try:
        product_id = data.get("product_id")
        warehouse_id = data.get("warehouse_id")
        qty = data.get("qty")
        movement_type = data.get("movement_type")
        label = data.get("label", "")
        price = data.get("price", 0.0)

        movement = await svc.add_stock_movement(
            product_id=product_id,
            warehouse_id=warehouse_id,
            qty=qty,
            movement_type=movement_type,
            label=label,
            price=price,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except IntegrationError as exc:
        logger.error("Error registrando movimiento de stock", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(
        content=_ok(movement, "Movimiento de stock registrado."),
        status_code=status.HTTP_201_CREATED,
    )


@stocks_router.post("/transfer", status_code=status.HTTP_201_CREATED)
async def transfer_stock(data: dict) -> JSONResponse:
    """
    Transfiere stock entre almacenes.

    Body esperado:
      - product_id: int
      - from_warehouse_id: int
      - to_warehouse_id: int
      - qty: float (debe ser > 0)
      - label: str (opcional)

    Returns:
        Respuesta estándar (201) con los dos movimientos creados.
    """
    svc = await _get_stock_service()
    try:
        product_id = data.get("product_id")
        from_warehouse_id = data.get("from_warehouse_id")
        to_warehouse_id = data.get("to_warehouse_id")
        qty = data.get("qty")
        label = data.get("label", "")

        result = await svc.transfer_stock(
            product_id=product_id,
            from_warehouse_id=from_warehouse_id,
            to_warehouse_id=to_warehouse_id,
            qty=qty,
            label=label,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except IntegrationError as exc:
        logger.error("Error transfiriendo stock", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(
        content=_ok(result, "Transferencia de stock completada."),
        status_code=status.HTTP_201_CREATED,
    )


# ── Campos extra (extrafields) ────────────────────────────────────────────

extrafields_router = APIRouter(prefix="/dolibarr/extrafields", tags=["dolibarr-extrafields"])


async def _get_extrafield_service() -> DolibarrExtraFieldService:
    """
    Construye y devuelve una instancia de DolibarrExtraFieldService.
    Lee credenciales desde Redis o .env.
    Si DOLIBARR_DB_* está configurado, adjunta DolibarrExtraFieldDB como fallback
    para cuando la REST API devuelve 501.

    Raises:
        HTTPException 503: si Dolibarr no está configurado.
    """
    from services.integrations.dolibarr.extrafields_db import DolibarrExtraFieldDB

    settings = get_settings()
    try:
        url, api_key = await _get_dolibarr_credentials()
        client = DolibarrClient(settings, override_url=url, override_api_key=api_key)
    except IntegrationNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_NOT_CONFIGURED_MSG,
        )

    db_fallback = None
    try:
        db_cfg = await _get_dolibarr_db_config()
        if db_cfg.get("host", "").strip() and db_cfg.get("db_name", "").strip() and db_cfg.get("user", "").strip():
            db_fallback = DolibarrExtraFieldDB(
                settings,
                override_host=db_cfg.get("host", ""),
                override_port=db_cfg.get("port"),
                override_db=db_cfg.get("db_name", ""),
                override_user=db_cfg.get("user", ""),
                override_pass=db_cfg.get("password", ""),
                override_prefix=db_cfg.get("prefix", ""),
            )
    except Exception as exc:
        logger.warning("DB fallback para extrafields no disponible", exc_info=exc)

    return DolibarrExtraFieldService(client, db_fallback=db_fallback)


@extrafields_router.get("")
async def list_extrafields(
    elementtype: str = Query(default="product"),
) -> JSONResponse:
    """
    Lista los campos extra configurados para un tipo de elemento Dolibarr.

    Usa BD directa como fuente primaria (no requiere REST API configurada).
    Solo recurre a la REST API si la BD no está configurada.

    Args:
        elementtype: tipo de elemento (product, societe, facture, etc.).

    Returns:
        Respuesta estándar con lista de campos extra.
    """
    # DB-direct path — does not require Dolibarr REST API credentials
    try:
        db = await _get_extrafield_db()
        fields = await db.list_extrafields(elementtype=elementtype)
        return JSONResponse(content=_ok(fields, f"{len(fields)} campos extra encontrados."))
    except HTTPException as exc:
        if "BD_NO_CONFIGURADA" not in str(exc.detail):
            raise
    except Exception as exc:
        logger.error("Error listando extrafields via BD Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error al conectar con la BD de Dolibarr: {exc}",
        )

    # Fallback: REST API when DB is not configured
    try:
        svc = await _get_extrafield_service()
        fields = await svc.list_extrafields(elementtype=elementtype)
    except IntegrationError as exc:
        logger.error("Error listando extrafields Dolibarr via REST", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(fields, f"{len(fields)} campos extra encontrados."))


async def _get_extrafield_db() -> "DolibarrExtraFieldDB":
    """
    Construye DolibarrExtraFieldDB con credenciales desde Redis o .env.

    La lógica de creación/eliminación de campos extra siempre usa BD directa
    porque la REST API de Dolibarr no soporta este operación en todas las versiones.
    Es exactamente la misma lógica usada para crear los campos de prueba.

    Raises:
        HTTPException 400: si las credenciales de BD no están configuradas.
        HTTPException 503: si no se puede conectar a la BD.
    """
    from services.integrations.dolibarr.extrafields_db import DolibarrExtraFieldDB

    settings = get_settings()
    db_cfg = await _get_dolibarr_db_config()

    host = db_cfg.get("host", "").strip()
    db_name = db_cfg.get("db_name", "").strip()
    user = db_cfg.get("user", "").strip()

    if not host or not db_name or not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "BD_NO_CONFIGURADA: Para crear o eliminar campos extra necesitas configurar "
                "el acceso directo a la base de datos MySQL de Dolibarr. "
                "Ve a la pestaña Configuración → BD Dolibarr e introduce: "
                "host, puerto, nombre de BD, usuario y contraseña."
            ),
        )

    try:
        return DolibarrExtraFieldDB(
            settings,
            override_host=host,
            override_port=db_cfg.get("port"),
            override_db=db_name,
            override_user=user,
            override_pass=db_cfg.get("password", ""),
            override_prefix=db_cfg.get("prefix", ""),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"BD_NO_CONFIGURADA: {exc}",
        )


@extrafields_router.post("", status_code=status.HTTP_201_CREATED)
async def create_extrafield(request: DolibarrExtraFieldCreate) -> JSONResponse:
    """
    Crea un nuevo campo extra en Dolibarr via acceso directo a BD MySQL.

    Replica exactamente la lógica de los scripts de prueba:
      1. INSERT en llx_extrafields (definición del campo)
      2. ALTER TABLE llx_{element}_extrafields ADD COLUMN (columna de datos)

    El campo queda disponible de inmediato en la interfaz de Dolibarr
    y aparece automáticamente en el formulario dinámico de Harvist.

    Args:
        request: DolibarrExtraFieldCreate con los datos del nuevo campo.

    Returns:
        Respuesta estándar (201) con la definición del campo creado.
    """
    if not request.attrname or not request.attrname.replace("_", "").isalnum():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Nombre interno '{request.attrname}' inválido: solo letras, números y guión bajo.",
        )

    db = await _get_extrafield_db()

    try:
        created = await db.create_extrafield(
            attrname=request.attrname.lower(),
            label=request.label,
            field_type=request.type,
            elementtype=request.elementtype,
            size=request.size,
            required=request.required,
            field_default=request.fielddefault,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except RuntimeError as exc:
        logger.error("Error creando extrafield via BD Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Error inesperado creando extrafield: %s: %s", type(exc).__name__, exc, exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{type(exc).__name__}: {exc}",
        )

    logger.info(
        "Campo extra creado desde dashboard",
        extra={"attrname": request.attrname, "elementtype": request.elementtype, "type": request.type},
    )
    return JSONResponse(
        content=_ok(created, f"Campo extra '{request.attrname}' creado correctamente."),
        status_code=status.HTTP_201_CREATED,
    )


@extrafields_router.delete("/{attrname}")
async def delete_extrafield(
    attrname: str,
    elementtype: str = Query(default="product"),
) -> JSONResponse:
    """
    Elimina un campo extra de Dolibarr via acceso directo a BD MySQL.

    Replica exactamente la lógica de los scripts de prueba:
      1. DELETE de llx_extrafields
      2. ALTER TABLE llx_{element}_extrafields DROP COLUMN

    Args:
        attrname:    nombre interno del campo a eliminar.
        elementtype: tipo de elemento al que pertenece el campo.

    Returns:
        Respuesta estándar con confirmación de eliminación.
    """
    db = await _get_extrafield_db()

    try:
        await db.delete_extrafield(attrname=attrname, elementtype=elementtype)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except RuntimeError as exc:
        logger.error("Error eliminando extrafield via BD Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    return JSONResponse(content={"success": True, "message": f"Campo extra '{attrname}' eliminado."})
