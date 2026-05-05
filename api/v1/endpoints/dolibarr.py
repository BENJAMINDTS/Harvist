"""
Endpoints de la integración Dolibarr.

Rutas expuestas bajo /api/v1/dolibarr:
  GET    /dolibarr/status                             — Verificar estado y configuración

Rutas expuestas bajo /api/v1/dolibarr/products:
  GET    /dolibarr/products                        — Listar productos (paginado)
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

import json
import tempfile
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from loguru import logger

from api.core.config import get_settings
from api.v1.schemas.integrations import (
    DolibarrConfigRequest,
    DolibarrConfigResponse,
    IntegrationStatus,
    PaginatedResponse,
    SyncFromJobRequest,
)
from services.integrations.base import IntegrationError, IntegrationNotConfiguredError
from services.integrations.dolibarr.categories import DolibarrCategoryService
from services.integrations.dolibarr.client import DolibarrClient
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


# ── Productos ────────────────────────────────────────────────────────────


@router_products.get("", response_model=PaginatedResponse)
async def list_products(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse:
    """
    Lista productos de Dolibarr con paginación.

    Args:
        limit:  máximo de productos por página.
        offset: desplazamiento desde el inicio.

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
        items = await svc.list_products(limit=limit, offset=offset)
    except IntegrationError as exc:
        logger.error("Error listando productos Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return PaginatedResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    )


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


@router_products.post("", status_code=status.HTTP_201_CREATED)
async def create_product(data: dict) -> JSONResponse:
    """
    Crea un producto en Dolibarr.

    Args:
        data: campos del producto (ref, label, price, description, type, status).

    Returns:
        Respuesta estándar (201) con el producto creado.
    """
    svc = await _get_service_async()
    try:
        created = await svc.create_product(data)
    except IntegrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(
        content=_ok(created, "Producto creado."),
        status_code=status.HTTP_201_CREATED,
    )


@router_products.put("/{product_id}")
async def update_product(product_id: int, data: dict) -> JSONResponse:
    """
    Actualiza un producto existente en Dolibarr.

    Args:
        product_id: ID del producto en Dolibarr.
        data:       campos a actualizar.

    Returns:
        Respuesta estándar con el producto actualizado.
    """
    svc = await _get_service_async()
    try:
        updated = await svc.update_product(product_id, data)
    except IntegrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
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


@categories_router.get("", response_model=PaginatedResponse)
async def list_categories(
    type: str = Query(default="product"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse:
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
    return PaginatedResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    )


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


@categories_router.get("/{category_id}/products", response_model=PaginatedResponse)
async def list_products_in_category(
    category_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse:
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
    return PaginatedResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    )


# ── Terceros ─────────────────────────────────────────────────────


thirdparties_router = APIRouter(prefix="/dolibarr/thirdparties", tags=["dolibarr-thirdparties"])


def _get_thirdparty_service() -> DolibarrThirdpartyService:
    """
    Construye y devuelve una instancia de DolibarrThirdpartyService.

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
    return DolibarrThirdpartyService(client)


@thirdparties_router.get("", response_model=PaginatedResponse)
async def list_thirdparties(
    mode: str = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse:
    """
    Lista terceros de Dolibarr con paginación y filtro por modo.

    Args:
        mode:   "all" para todos, "customers" para clientes, "suppliers" para proveedores.
        limit:  máximo de terceros por página.
        offset: desplazamiento desde el inicio.

    Returns:
        PaginatedResponse con los terceros encontrados.
    """
    svc = _get_thirdparty_service()
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
    return PaginatedResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    )


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
    svc = _get_thirdparty_service()
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
    svc = _get_thirdparty_service()
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
    svc = _get_thirdparty_service()
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
    svc = _get_thirdparty_service()
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
    svc = _get_thirdparty_service()
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


@thirdparties_router.get("/{thirdparty_id}/invoices", response_model=PaginatedResponse)
async def get_thirdparty_invoices(
    thirdparty_id: int,
    type: str = Query(default="customer"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse:
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
    svc = _get_thirdparty_service()
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
    return PaginatedResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    )


@thirdparties_router.get("/{thirdparty_id}/orders", response_model=PaginatedResponse)
async def get_thirdparty_orders(
    thirdparty_id: int,
    type: str = Query(default="customer"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse:
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
    svc = _get_thirdparty_service()
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
    return PaginatedResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    )


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


@orders_router.get("", response_model=PaginatedResponse)
async def list_orders(
    type: str = Query(default="customer"),
    status: int | None = Query(default=None),
    thirdparty_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse:
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
    return PaginatedResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    )


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


@invoices_router.get("", response_model=PaginatedResponse)
async def list_invoices(
    type: str = Query(default="customer"),
    status: int | None = Query(default=None),
    thirdparty_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse:
    """
    Lista facturas de cliente o proveedor.

    Args:
        type: "customer" (facturas cliente) o "supplier" (facturas proveedor).
        status: filtro opcional por estado de la factura.
        thirdparty_id: filtro opcional por ID del tercero.
        limit: máximo de facturas por página.
        offset: desplazamiento desde el inicio.

    Returns:
        PaginatedResponse con las facturas encontradas.
    """
    svc = await _get_invoice_service()
    try:
        items = await svc.list_invoices(
            type=type, limit=limit, offset=offset, status=status, thirdparty_id=thirdparty_id
        )
    except IntegrationError as exc:
        logger.error("Error listando facturas Dolibarr", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return PaginatedResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    )


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


@stocks_router.get("/warehouses", response_model=PaginatedResponse)
async def list_warehouses(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse:
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
    return PaginatedResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    )


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


@stocks_router.get("/movements", response_model=PaginatedResponse)
async def list_movements(
    product_id: int | None = Query(default=None),
    warehouse_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse:
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
    return PaginatedResponse(
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
        has_more=len(items) == limit,
    )


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
