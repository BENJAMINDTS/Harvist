"""
Endpoints de la integración WordPress / WooCommerce.

Rutas bajo /api/v1/wordpress:
  GET  /wordpress/status                     — Estado y configuración
  GET  /wordpress/config                     — Leer credenciales actuales
  POST /wordpress/config                     — Guardar credenciales en Redis
  GET  /wordpress/db/config                  — Leer config BD MySQL
  POST /wordpress/db/config                  — Guardar config BD MySQL en Redis

Rutas bajo /api/v1/wordpress/products:
  GET    /wordpress/products                 — Listar productos (paginado)
  GET    /wordpress/products/{id}            — Obtener producto
  POST   /wordpress/products                 — Crear producto
  PUT    /wordpress/products/{id}            — Actualizar producto
  DELETE /wordpress/products/{id}            — Eliminar producto
  POST   /wordpress/products/sync            — Sincronizar desde job Harvist

Rutas bajo /api/v1/wordpress/categories:
  GET    /wordpress/categories               — Listar categorías
  GET    /wordpress/categories/tree          — Árbol jerárquico
  GET    /wordpress/categories/{id}          — Obtener categoría
  POST   /wordpress/categories               — Crear categoría
  PUT    /wordpress/categories/{id}          — Actualizar categoría
  DELETE /wordpress/categories/{id}          — Eliminar categoría

Rutas bajo /api/v1/wordpress/orders:
  GET    /wordpress/orders                   — Listar pedidos
  GET    /wordpress/orders/{id}              — Obtener pedido
  PUT    /wordpress/orders/{id}/status       — Cambiar estado
  POST   /wordpress/orders/{id}/notes        — Añadir nota

Rutas bajo /api/v1/wordpress/customers:
  GET    /wordpress/customers                — Listar clientes
  GET    /wordpress/customers/{id}           — Obtener cliente
  POST   /wordpress/customers                — Crear cliente
  PUT    /wordpress/customers/{id}           — Actualizar cliente
  DELETE /wordpress/customers/{id}           — Eliminar cliente

Rutas bajo /api/v1/wordpress/media:
  GET    /wordpress/media                    — Listar media
  POST   /wordpress/media                    — Subir archivo

Rutas bajo /api/v1/wordpress/db:
  GET    /wordpress/db/tables                — Listar tablas MySQL
  GET    /wordpress/db/site-info             — Info del sitio WordPress
  POST   /wordpress/db/query                 — Ejecutar query SELECT
  GET    /wordpress/db/options/{option_name} — Leer wp_option

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Body, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse
from loguru import logger

from api.core.config import get_settings
from api.v1.schemas.integrations import (
    CsvImportPreview,
    IntegrationStatus,
    PaginatedResponse,
    SyncFromJobRequest,
    WordPressConfigRequest,
    WordPressConfigResponse,
    WordPressDBConfigRequest,
    WordPressDBConfigResponse,
)
from services.integrations.base import IntegrationError, IntegrationNotConfiguredError
from services.integrations.dolibarr.categories import DolibarrCategoryService
from services.integrations.dolibarr.client import DolibarrClient
from services.integrations.dolibarr.products import DolibarrProductService
from services.integrations.dolibarr.stocks import DolibarrStockService
from services.integrations.wordpress.brands import WordPressBrandService
from services.integrations.wordpress.categories import WordPressCategoryService
from services.integrations.wordpress.client import WordPressClient
from services.integrations.wordpress.customers import WordPressCustomerService
from services.integrations.wordpress.database import WordPressDBService
from services.integrations.wordpress.media import WordPressMediaService
from services.integrations.wordpress.orders import WordPressOrderService
from services.integrations.wordpress.products import WordPressProductService
from services.storage_service import get_storage_service

router_main = APIRouter(prefix="/wordpress", tags=["wordpress"])
router_products = APIRouter(prefix="/wordpress/products", tags=["wordpress-products"])
router_categories = APIRouter(prefix="/wordpress/categories", tags=["wordpress-categories"])
router_brands = APIRouter(prefix="/wordpress/brands", tags=["wordpress-brands"])
router_orders = APIRouter(prefix="/wordpress/orders", tags=["wordpress-orders"])
router_customers = APIRouter(prefix="/wordpress/customers", tags=["wordpress-customers"])
router_media = APIRouter(prefix="/wordpress/media", tags=["wordpress-media"])
router_db = APIRouter(prefix="/wordpress/db", tags=["wordpress-db"])
router_webhooks = APIRouter(prefix="/wordpress/webhooks", tags=["wordpress-webhooks"])

_ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_MEDIA_BYTES = 5 * 1024 * 1024  # 5 MB
_NOT_CONFIGURED_MSG = (
    "WordPress no está configurado. "
    "Define WORDPRESS_URL, WORDPRESS_CONSUMER_KEY y WORDPRESS_CONSUMER_SECRET "
    "en tu archivo .env o configúralos en la interfaz."
)
_DB_NOT_CONFIGURED_MSG = (
    "BD MySQL de WordPress no configurada. "
    "Define WORDPRESS_DB_HOST, WORDPRESS_DB_NAME y WORDPRESS_DB_USER."
)


# ── Helpers de credenciales ─────────────────────────────────────────────────


async def _get_wp_credentials() -> dict[str, str]:
    """
    Obtiene credenciales de WordPress desde Redis, archivo JSON o .env.

    Prioridad: Redis → data/wp_config.json → variables de entorno.

    Returns:
        Dict con url, consumer_key y consumer_secret.

    Raises:
        IntegrationNotConfiguredError: si no hay credenciales configuradas.
    """
    settings = get_settings()
    redis_client: aioredis.Redis | None = None

    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        stored = await redis_client.get("integration:wordpress:config")
        if stored:
            config: dict[str, str] = json.loads(stored)
            if config.get("url") and config.get("consumer_key") and config.get("consumer_secret"):
                return config
    except Exception as exc:
        logger.debug("Redis no disponible para config WordPress", exc_info=exc)
    finally:
        if redis_client:
            await redis_client.aclose()

    file_config = _load_config_file(settings.wp_config_path)
    if file_config.get("url") and file_config.get("consumer_key") and file_config.get("consumer_secret"):
        return file_config

    if settings.wordpress_configured:
        return {
            "url": settings.wordpress_url,
            "consumer_key": settings.wordpress_consumer_key,
            "consumer_secret": settings.wordpress_consumer_secret,
        }

    raise IntegrationNotConfiguredError(
        "WordPress no configurado: define las variables en .env o en la interfaz gráfica."
    )


async def _get_db_credentials() -> dict[str, Any]:
    """
    Obtiene credenciales de BD de WordPress desde Redis, archivo JSON o .env.

    Prioridad: Redis → data/wp_db_config.json → variables de entorno.

    Returns:
        Dict con host, port, db_name, user, password, prefix.

    Raises:
        IntegrationNotConfiguredError: si no hay credenciales de BD configuradas.
    """
    settings = get_settings()
    redis_client: aioredis.Redis | None = None

    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        stored = await redis_client.get("integration:wordpress:db_config")
        if stored:
            config: dict[str, Any] = json.loads(stored)
            if config.get("host") and config.get("db_name") and config.get("user"):
                return config
    except Exception as exc:
        logger.debug("Redis no disponible para config BD WordPress", exc_info=exc)
    finally:
        if redis_client:
            await redis_client.aclose()

    file_config = _load_config_file(settings.wp_db_config_path)
    if file_config.get("host") and file_config.get("db_name") and file_config.get("user"):
        return file_config

    if settings.wordpress_db_configured:
        return {
            "host": settings.wordpress_db_host,
            "port": settings.wordpress_db_port,
            "db_name": settings.wordpress_db_name,
            "user": settings.wordpress_db_user,
            "password": settings.wordpress_db_pass,
            "prefix": settings.wordpress_db_prefix,
        }

    raise IntegrationNotConfiguredError(
        "BD WordPress no configurada: define WORDPRESS_DB_* en .env o en la interfaz gráfica."
    )


async def _get_dolibarr_client_for_sync() -> DolibarrClient | None:
    """
    Construye DolibarrClient desde Redis o .env para uso en sync.

    Returns:
        DolibarrClient si Dolibarr está configurado, None si no.
    """
    settings = get_settings()
    redis_client: aioredis.Redis | None = None
    url: str = ""
    api_key: str = ""
    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        stored = await redis_client.get("integration:dolibarr:config")
        if stored:
            config = json.loads(stored)
            url = config.get("url", "").strip()
            api_key = config.get("api_key", "").strip()
    except Exception as exc:
        logger.debug("Redis no disponible para config Dolibarr en sync WP", exc_info=exc)
    finally:
        if redis_client:
            await redis_client.aclose()

    if not url or not api_key:
        if settings.dolibarr_configured:
            url = settings.dolibarr_url
            api_key = settings.dolibarr_api_key
        else:
            return None

    return DolibarrClient(settings, override_url=url, override_api_key=api_key)


async def _get_dolibarr_product_service() -> DolibarrProductService | None:
    """
    Construye DolibarrProductService desde Redis o .env.

    Returns:
        DolibarrProductService si Dolibarr está configurado, None si no.
    """
    doli_client = await _get_dolibarr_client_for_sync()
    if doli_client is None:
        return None
    return DolibarrProductService(doli_client)


async def _get_dolibarr_services_for_sync() -> (
    tuple[DolibarrProductService, DolibarrCategoryService] | None
):
    """
    Construye DolibarrProductService y DolibarrCategoryService desde Redis o .env.

    Returns:
        Tupla (DolibarrProductService, DolibarrCategoryService) o None si no configurado.
    """
    doli_client = await _get_dolibarr_client_for_sync()
    if doli_client is None:
        return None
    return DolibarrProductService(doli_client), DolibarrCategoryService(doli_client)


def _map_wc_to_dolibarr(wc_product: dict[str, Any]) -> dict[str, Any]:
    """
    Mapea campos WooCommerce → Dolibarr para actualización.

    Mapeo:
      name             → label
      description      → description
      regular_price    → price
      weight           → weight

    Args:
        wc_product: dict del producto WooCommerce actualizado.

    Returns:
        Dict con campos Dolibarr a actualizar (solo los presentes en wc_product).
    """
    mapping: dict[str, Any] = {}
    if "name" in wc_product:
        mapping["label"] = wc_product["name"]
    if "description" in wc_product:
        mapping["description"] = wc_product["description"]
    if "regular_price" in wc_product and wc_product["regular_price"] not in (None, ""):
        try:
            mapping["price"] = float(wc_product["regular_price"])
        except (ValueError, TypeError):
            pass
    if "weight" in wc_product and wc_product["weight"] not in (None, ""):
        try:
            mapping["weight"] = float(wc_product["weight"])
        except (ValueError, TypeError):
            pass
    return mapping


def _extract_wc_brand_name(wc_product: dict[str, Any]) -> str:
    """
    Extrae el nombre de marca de un producto WooCommerce.

    Soporta modo nativo (campo brands[]) y modo atributo (pa_brand / brand).

    Args:
        wc_product: dict del producto WooCommerce.

    Returns:
        Nombre de la marca o cadena vacía si no hay marca asignada.
    """
    brands = wc_product.get("brands", [])
    if brands:
        return (brands[0].get("name") or "").strip()
    for attr in wc_product.get("attributes", []):
        if attr.get("slug") in ("pa_brand", "brand", "pa_marca", "marca"):
            opts = attr.get("options", [])
            if opts:
                return opts[0].strip()
    return ""


async def _sync_wc_stock_to_dolibarr(
    sku: str,
    wc_stock: int | float,
    doli_svc: DolibarrProductService,
) -> dict[str, Any]:
    """
    Sincroniza el stock de un producto de WooCommerce a Dolibarr.

    Busca el producto en Dolibarr por ref=SKU, calcula el delta respecto al
    stock actual y crea un movimiento de corrección de inventario (tipo 2).

    Args:
        sku:       referencia del producto (SKU WC = ref Dolibarr).
        wc_stock:  cantidad actual en WooCommerce.
        doli_svc:  DolibarrProductService ya inicializado.

    Returns:
        Dict con synced (bool), delta, new_qty o reason.
    """
    existing = await doli_svc._find_product_by_ref(sku)
    if not existing:
        return {"synced": False, "reason": f"SKU '{sku}' no encontrado en Dolibarr"}

    doli_id = int(existing["id"])
    stock_svc = DolibarrStockService(doli_svc._client)
    doli_stock_info = await stock_svc.get_product_stock(doli_id)
    current_qty = float(doli_stock_info.get("stock_total", 0))
    delta = float(wc_stock) - current_qty

    if delta == 0:
        return {"synced": True, "reason": "Stock ya sincronizado", "delta": 0, "new_qty": int(wc_stock)}

    warehouses = await stock_svc.list_warehouses(limit=1)
    if not warehouses:
        return {"synced": False, "reason": "Sin almacenes configurados en Dolibarr"}

    warehouse_id = int(warehouses[0]["id"])
    await stock_svc.add_stock_movement(
        product_id=doli_id,
        warehouse_id=warehouse_id,
        qty=delta,
        movement_type=2,
        label=f"Sync WooCommerce (SKU {sku})",
    )
    logger.info(
        "Stock sincronizado WP→Dolibarr",
        extra={"sku": sku, "delta": delta, "new_qty": wc_stock, "dolibarr_id": doli_id},
    )
    return {"synced": True, "delta": delta, "new_qty": int(wc_stock), "dolibarr_id": doli_id}


async def _get_brand_attr_id_override() -> int | None:
    """
    Lee el override de atributo de marca desde Redis, si existe.

    Returns:
        ID del atributo configurado manualmente, o None si no hay override.
    """
    settings = get_settings()
    redis_client: aioredis.Redis | None = None
    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        stored = await redis_client.get("integration:wordpress:brand_attr_id")
        if stored:
            return int(stored)
    except Exception as exc:
        logger.debug("No se pudo leer brand_attr_id de Redis", exc_info=exc)
    finally:
        if redis_client:
            await redis_client.aclose()
    return None


async def _get_brand_service(client: WordPressClient) -> WordPressBrandService:
    """
    Construye WordPressBrandService respetando el override de atributo en Redis.

    Args:
        client: WordPressClient ya inicializado.

    Returns:
        WordPressBrandService con override si fue configurado manualmente.
    """
    override = await _get_brand_attr_id_override()
    return WordPressBrandService(client, attr_id_override=override)


async def _get_client() -> WordPressClient:
    """
    Construye WordPressClient con credenciales de Redis o .env.

    Raises:
        HTTPException 503: si WordPress no está configurado.
    """
    settings = get_settings()
    try:
        creds = await _get_wp_credentials()
        return WordPressClient(
            settings,
            override_url=creds["url"],
            override_consumer_key=creds["consumer_key"],
            override_consumer_secret=creds["consumer_secret"],
        )
    except IntegrationNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_NOT_CONFIGURED_MSG,
        )


async def _get_db_service() -> WordPressDBService:
    """
    Construye WordPressDBService con credenciales de Redis o .env.

    Raises:
        HTTPException 503: si la BD no está configurada.
    """
    try:
        creds = await _get_db_credentials()
        return WordPressDBService(
            host=creds["host"],
            port=int(creds.get("port", 3306)),
            db_name=creds["db_name"],
            user=creds["user"],
            password=creds.get("password", ""),
            prefix=creds.get("prefix", "wp_"),
        )
    except IntegrationNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_DB_NOT_CONFIGURED_MSG,
        )


def _ok(data: Any, message: str = "OK") -> dict[str, Any]:
    """Envuelve data en la respuesta estándar Harvist."""
    return {"success": True, "data": data, "message": message}


def _load_config_file(path: str) -> dict[str, Any]:
    """
    Lee un archivo JSON de configuración desde disco.

    Args:
        path: ruta relativa o absoluta al archivo JSON.

    Returns:
        Dict con el contenido del archivo, o dict vacío si no existe o hay error.
    """
    try:
        p = Path(path)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug("No se pudo leer config file", exc_info=exc, extra={"path": path})
    return {}


def _save_config_file(path: str, data: dict[str, Any]) -> None:
    """
    Escribe un dict de configuración en disco como JSON.

    Args:
        path: ruta relativa o absoluta al archivo destino.
        data: datos a serializar.
    """
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("Config file guardado", extra={"path": path})
    except Exception as exc:
        logger.warning("No se pudo escribir config file", exc_info=exc, extra={"path": path})


# ── Status & Config ─────────────────────────────────────────────────────────


@router_main.get("/status", response_model=IntegrationStatus)
async def get_status() -> IntegrationStatus:
    """
    Verifica estado de configuración y salud de la integración WordPress.

    Prioridad: Redis config > variables de entorno.

    Returns:
        IntegrationStatus con platform, configured, healthy y message.
    """
    settings = get_settings()
    redis_client: aioredis.Redis | None = None
    override: dict[str, str] = {}

    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        stored = await redis_client.get("integration:wordpress:config")
        if stored:
            override = json.loads(stored)
    except Exception as exc:
        logger.debug("Redis no disponible para status WordPress", exc_info=exc)
    finally:
        if redis_client:
            await redis_client.aclose()

    url = override.get("url", "") or settings.wordpress_url
    consumer_key = override.get("consumer_key", "") or settings.wordpress_consumer_key
    consumer_secret = override.get("consumer_secret", "") or settings.wordpress_consumer_secret

    configured = bool(url and consumer_key and consumer_secret)
    if not configured:
        return IntegrationStatus(
            platform="wordpress",
            configured=False,
            healthy=None,
            message="WordPress no configurado.",
        )

    try:
        client = WordPressClient(
            settings,
            override_url=url,
            override_consumer_key=consumer_key,
            override_consumer_secret=consumer_secret,
        )
        healthy = await client.health_check()
        await client.close()
    except Exception:
        healthy = False

    return IntegrationStatus(
        platform="wordpress",
        configured=True,
        healthy=healthy,
        message="WordPress configurado y accesible." if healthy else "WordPress configurado pero no responde.",
    )


@router_main.get("/config", response_model=WordPressConfigResponse)
async def get_config() -> WordPressConfigResponse:
    """
    Lee la configuración actual de WordPress.

    Returns:
        WordPressConfigResponse con las credenciales actuales (enmascaradas).
    """
    settings = get_settings()
    redis_client: aioredis.Redis | None = None
    config: dict[str, str] = {}

    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        stored = await redis_client.get("integration:wordpress:config")
        if stored:
            config = json.loads(stored)
    except Exception as exc:
        logger.debug("Redis no disponible para leer config WordPress", exc_info=exc)
    finally:
        if redis_client:
            await redis_client.aclose()

    url = config.get("url", settings.wordpress_url)
    consumer_key = config.get("consumer_key", settings.wordpress_consumer_key)
    consumer_secret = config.get("consumer_secret", settings.wordpress_consumer_secret)

    return WordPressConfigResponse(
        url=url,
        consumer_key="***" if consumer_key else "",
        consumer_secret="***" if consumer_secret else "",
        configured=bool(url and consumer_key and consumer_secret),
    )


@router_main.post("/config")
async def save_config(body: WordPressConfigRequest) -> dict[str, Any]:
    """
    Guarda configuración de WordPress en Redis.

    Args:
        body: URL, consumer_key, consumer_secret y credenciales opcionales de Application Password.

    Returns:
        Respuesta estándar confirmando el guardado.
    """
    settings = get_settings()
    redis_client: aioredis.Redis | None = None

    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        existing: dict[str, str] = {}
        stored = await redis_client.get("integration:wordpress:config")
        if stored:
            existing = json.loads(stored)

        payload = {
            "url": body.url.strip().rstrip("/"),
            "consumer_key": body.consumer_key.strip() or existing.get("consumer_key", ""),
            "consumer_secret": body.consumer_secret.strip() or existing.get("consumer_secret", ""),
        }
        await redis_client.set("integration:wordpress:config", json.dumps(payload))
        _save_config_file(settings.wp_config_path, payload)
        logger.info("Config WordPress guardada", extra={"url": body.url})
    except Exception as exc:
        logger.error("Error guardando config WordPress en Redis", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo guardar la configuración de WordPress.",
        ) from exc
    finally:
        if redis_client:
            await redis_client.aclose()

    return _ok({}, "Configuración de WordPress guardada correctamente.")


@router_main.get("/db/config", response_model=WordPressDBConfigResponse)
async def get_db_config() -> WordPressDBConfigResponse:
    """
    Lee la configuración de BD MySQL de WordPress.

    Returns:
        WordPressDBConfigResponse con las credenciales actuales (contraseña enmascarada).
    """
    settings = get_settings()
    redis_client: aioredis.Redis | None = None
    config: dict[str, Any] = {}

    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        stored = await redis_client.get("integration:wordpress:db_config")
        if stored:
            config = json.loads(stored)
    except Exception as exc:
        logger.debug("Redis no disponible para leer config BD WordPress", exc_info=exc)
    finally:
        if redis_client:
            await redis_client.aclose()

    host = config.get("host", settings.wordpress_db_host)
    return WordPressDBConfigResponse(
        host=host,
        port=int(config.get("port", settings.wordpress_db_port)),
        db_name=config.get("db_name", settings.wordpress_db_name),
        user=config.get("user", settings.wordpress_db_user),
        password="***" if config.get("password") else "",
        prefix=config.get("prefix", settings.wordpress_db_prefix),
        configured=settings.wordpress_db_configured or bool(host),
    )


@router_main.post("/db/config")
async def save_db_config(body: WordPressDBConfigRequest) -> dict[str, Any]:
    """
    Guarda configuración de BD MySQL de WordPress en Redis.

    Args:
        body: host, port, db_name, user, password, prefix.

    Returns:
        Respuesta estándar confirmando el guardado.
    """
    settings = get_settings()
    redis_client: aioredis.Redis | None = None

    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        payload = {
            "host": body.host.strip(),
            "port": body.port,
            "db_name": body.db_name.strip(),
            "user": body.user.strip(),
            "password": body.password,
            "prefix": body.prefix.strip(),
        }
        await redis_client.set("integration:wordpress:db_config", json.dumps(payload))
        _save_config_file(settings.wp_db_config_path, payload)
        logger.info("Config BD WordPress guardada", extra={"host": body.host})
    except Exception as exc:
        logger.error("Error guardando config BD WordPress en Redis", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo guardar la configuración de BD WordPress.",
        ) from exc
    finally:
        if redis_client:
            await redis_client.aclose()

    return _ok({}, "Configuración de BD WordPress guardada correctamente.")


# ── Products ────────────────────────────────────────────────────────────────


@router_products.get("")
async def list_products(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: str = Query(default="any", alias="status"),
    category: int | None = Query(default=None),
    search: str = Query(default=""),
) -> dict[str, Any]:
    """
    Lista productos WooCommerce con paginación y filtros.

    Args:
        limit: elementos por página.
        offset: desplazamiento.
        status_filter: filtro de estado (any, publish, draft, private).
        category: ID de categoría.
        search: búsqueda por nombre/SKU.

    Returns:
        PaginatedResponse con los productos.
    """
    client = await _get_client()
    try:
        filters: dict[str, Any] = {"status": status_filter}
        if category is not None:
            filters["category"] = category
        if search:
            filters["search"] = search
        items, total = await client.list_paged("products", limit=limit, offset=offset, filters=filters)
        return _ok(
            PaginatedResponse(
                items=items,
                total=total,
                limit=limit,
                offset=offset,
                has_more=(offset + len(items)) < total,
            ).model_dump(),
            "Productos obtenidos.",
        )
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_products.get("/{product_id}")
async def get_product(product_id: int) -> dict[str, Any]:
    """
    Obtiene un producto WooCommerce por ID.

    Args:
        product_id: ID del producto.

    Returns:
        Dict con los datos del producto.
    """
    client = await _get_client()
    try:
        svc = WordPressProductService(client)
        item = await svc.get(product_id)
        return _ok(item)
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_products.post("", status_code=status.HTTP_201_CREATED)
async def create_product(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """
    Crea un producto en WooCommerce y propaga la creación a Dolibarr si está configurado.

    El producto se busca en Dolibarr por ref = SKU. Si existe se actualiza;
    si no existe se crea. La operación WooCommerce se completa igualmente aunque
    Dolibarr no esté configurado o el sync falle.

    Args:
        body: campos del producto (name, type, regular_price, sku, etc.).

    Returns:
        Dict con el producto creado e información del sync a Dolibarr.
    """
    client = await _get_client()
    try:
        svc = WordPressProductService(client)
        item = await svc.create(body)
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()

    dolibarr_sync: dict[str, Any] = {"synced": False, "reason": "Dolibarr no configurado"}
    sku: str = item.get("sku", "").strip()

    if sku:
        doli_services = await _get_dolibarr_services_for_sync()
        if doli_services is not None:
            doli_svc, doli_cat_svc = doli_services
            try:
                doli_payload = _map_wc_to_dolibarr(item)
                doli_payload["ref"] = sku
                doli_payload.setdefault("label", item.get("name", sku))
                doli_payload.setdefault("tosell", 1)
                doli_payload.setdefault("tobuy", 1)

                existing = await doli_svc._find_product_by_ref(sku)
                if existing:
                    doli_id = int(existing["id"])
                    await doli_svc.update_product(doli_id, doli_payload)
                    dolibarr_sync = {"synced": True, "action": "updated", "dolibarr_id": doli_id}
                    logger.info(
                        "Producto actualizado en Dolibarr (sync desde creación WP)",
                        extra={"wc_id": item.get("id"), "sku": sku, "dolibarr_id": doli_id},
                    )
                else:
                    doli_created = await doli_svc.create_product(doli_payload)
                    doli_id = int(doli_created["id"])
                    dolibarr_sync = {"synced": True, "action": "created", "dolibarr_id": doli_id}
                    logger.info(
                        "Producto creado en Dolibarr (sync desde creación WP)",
                        extra={"wc_id": item.get("id"), "sku": sku, "dolibarr_id": doli_id},
                    )

                # ── Categoría WC → Dolibarr ───────────────────────────────────
                wc_categories = item.get("categories", [])
                if wc_categories:
                    cat_name = (wc_categories[0].get("name") or "").strip()
                    if cat_name:
                        try:
                            doli_cat = await doli_cat_svc.find_category_by_name(cat_name)
                            if doli_cat:
                                await doli_cat_svc.assign_product(int(doli_cat["id"]), doli_id)
                        except Exception as exc:
                            logger.warning(
                                "Sync categoría WP→Dolibarr (create) falló",
                                exc_info=exc,
                                extra={"sku": sku},
                            )

                # ── Marca WC → Dolibarr ───────────────────────────────────────
                brand_name = _extract_wc_brand_name(item)
                if brand_name:
                    try:
                        doli_brand = await doli_cat_svc.find_or_create_brand(brand_name)
                        await doli_cat_svc.assign_product(int(doli_brand["id"]), doli_id)
                    except Exception as exc:
                        logger.warning(
                            "Sync marca WP→Dolibarr (create) falló",
                            exc_info=exc,
                            extra={"sku": sku},
                        )

            except Exception as exc:
                dolibarr_sync = {"synced": False, "reason": str(exc)}
                logger.warning("Sync WP→Dolibarr (create) falló", exc_info=exc, extra={"sku": sku})

    return _ok({**item, "dolibarr_sync": dolibarr_sync}, "Producto creado en WooCommerce.")


@router_products.put("/{product_id}")
async def update_product(product_id: int, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """
    Actualiza un producto en WooCommerce y propaga el cambio a Dolibarr si está configurado.

    El producto se busca en Dolibarr por ref = SKU del producto WooCommerce.
    Si Dolibarr no está configurado o el producto no existe allí, la operación
    WooCommerce se completa igualmente y se registra un aviso.

    Args:
        product_id: ID del producto en WooCommerce.
        body: campos a actualizar.

    Returns:
        Dict con el producto actualizado e información del sync a Dolibarr.
    """
    client = await _get_client()
    try:
        svc = WordPressProductService(client)
        item = await svc.update(product_id, body)
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()

    dolibarr_sync: dict[str, Any] = {"synced": False, "reason": "Dolibarr no configurado"}
    sku: str = item.get("sku", "").strip()

    if sku:
        doli_services = await _get_dolibarr_services_for_sync()
        if doli_services is not None:
            doli_svc, doli_cat_svc = doli_services
            try:
                existing = await doli_svc._find_product_by_ref(sku)
                if existing:
                    doli_id = int(existing["id"])
                    dolibarr_payload = _map_wc_to_dolibarr(item)
                    dolibarr_payload.setdefault("ref", sku)
                    dolibarr_payload.setdefault("label", item.get("name", sku))
                    await doli_svc.update_product(doli_id, dolibarr_payload)
                    dolibarr_sync = {"synced": True, "dolibarr_id": existing["id"]}
                    logger.info(
                        "Producto sincronizado WP→Dolibarr",
                        extra={"wc_id": product_id, "sku": sku, "dolibarr_id": doli_id},
                    )

                    # ── Stock WC → Dolibarr ───────────────────────────────────
                    wc_stock = item.get("stock_quantity")
                    if wc_stock is not None and item.get("manage_stock"):
                        try:
                            await _sync_wc_stock_to_dolibarr(sku, wc_stock, doli_svc)
                        except Exception as exc:
                            logger.warning(
                                "Sync stock WP→Dolibarr falló",
                                exc_info=exc,
                                extra={"sku": sku},
                            )

                    # ── Categoría WC → Dolibarr ───────────────────────────────
                    wc_categories = item.get("categories", [])
                    if wc_categories:
                        cat_name = (wc_categories[0].get("name") or "").strip()
                        if cat_name:
                            try:
                                doli_cat = await doli_cat_svc.find_category_by_name(cat_name)
                                if doli_cat:
                                    await doli_cat_svc.assign_product(int(doli_cat["id"]), doli_id)
                                    logger.info(
                                        "Categoría sincronizada WP→Dolibarr",
                                        extra={"sku": sku, "category": cat_name},
                                    )
                            except Exception as exc:
                                logger.warning(
                                    "Sync categoría WP→Dolibarr falló",
                                    exc_info=exc,
                                    extra={"sku": sku, "category": cat_name},
                                )

                    # ── Marca WC → Dolibarr ───────────────────────────────────
                    brand_name = _extract_wc_brand_name(item)
                    if brand_name:
                        try:
                            doli_brand = await doli_cat_svc.find_or_create_brand(brand_name)
                            await doli_cat_svc.assign_product(int(doli_brand["id"]), doli_id)
                            logger.info(
                                "Marca sincronizada WP→Dolibarr",
                                extra={"sku": sku, "brand": brand_name},
                            )
                        except Exception as exc:
                            logger.warning(
                                "Sync marca WP→Dolibarr falló",
                                exc_info=exc,
                                extra={"sku": sku, "brand": brand_name},
                            )
                else:
                    dolibarr_sync = {"synced": False, "reason": f"SKU '{sku}' no encontrado en Dolibarr"}
                    logger.warning("Sync WP→Dolibarr: SKU no encontrado", extra={"sku": sku})
            except Exception as exc:
                dolibarr_sync = {"synced": False, "reason": str(exc)}
                logger.warning("Sync WP→Dolibarr falló", exc_info=exc, extra={"sku": sku})
    else:
        dolibarr_sync = {"synced": False, "reason": "Producto sin SKU, no se puede buscar en Dolibarr"}

    result = {**item, "dolibarr_sync": dolibarr_sync}
    return _ok(result, "Producto actualizado en WooCommerce.")


@router_products.put("/{product_id}/brand")
async def set_product_brand(product_id: int, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """
    Asigna o elimina la marca de un producto WooCommerce de forma atómica.

    Detecta automáticamente si el sitio usa el endpoint nativo de marcas
    (WooCommerce Brands / 8.6+) o el modo de atributo global (pa_brand).

    Modo nativo:   actualiza el campo ``brands`` del producto.
    Modo atributo: preserva atributos no-brand y reemplaza el atributo de marca.

    Args:
        product_id: ID del producto WooCommerce.
        body: ``{"brand_term_id": 5}`` para asignar, ``{"brand_term_id": null}`` para quitar.

    Returns:
        Dict con el producto actualizado.
    """
    client = await _get_client()
    try:
        brand_svc = await _get_brand_service(client)
        product_svc = WordPressProductService(client)

        brand_term_id = body.get("brand_term_id")
        use_native = await brand_svc._native_available()

        if use_native:
            # Native brands: update product.brands field
            brands_payload: list[dict[str, Any]] = (
                [{"id": int(brand_term_id)}] if brand_term_id is not None else []
            )
            updated = await product_svc.update(product_id, {"brands": brands_payload})
        else:
            # Attribute mode: get product, rebuild attributes array preserving non-brand attrs
            product = await product_svc.get(product_id)
            existing_attrs: list[dict[str, Any]] = product.get("attributes", [])
            non_brand_attrs = [
                a for a in existing_attrs
                if a.get("slug") not in ("pa_brand", "brand", "pa_marca", "marca")
            ]
            new_attrs: list[dict[str, Any]] = list(non_brand_attrs)
            if brand_term_id is not None:
                brand_term = await brand_svc.get(int(brand_term_id))
                attr_id = await brand_svc._get_attribute_id()
                new_attrs.append({
                    "id": attr_id,
                    "options": [brand_term["name"]],
                    "visible": True,
                    "variation": False,
                })
            updated = await product_svc.update(product_id, {"attributes": new_attrs})

        logger.info(
            "Marca de producto actualizada",
            extra={"product_id": product_id, "brand_term_id": brand_term_id, "native": use_native},
        )
        return _ok(updated, "Marca del producto actualizada.")
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_products.delete("/{product_id}")
async def delete_product(product_id: int) -> dict[str, Any]:
    """
    Elimina un producto de WooCommerce (force=true).

    Args:
        product_id: ID del producto.

    Returns:
        Respuesta estándar de éxito.
    """
    client = await _get_client()
    try:
        svc = WordPressProductService(client)
        await svc.delete(product_id)
        return _ok({}, "Producto eliminado de WooCommerce.")
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_products.delete("")
async def bulk_delete_products(ids: list[int] = Body(...)) -> dict[str, Any]:
    """
    Elimina múltiples productos de WooCommerce en una sola operación batch.

    Args:
        ids: lista de IDs de productos a eliminar.

    Returns:
        Respuesta estándar con el número de productos eliminados.
    """
    if not ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La lista de IDs no puede estar vacía.",
        )
    client = await _get_client()
    try:
        result = await client.batch_delete("products", ids)
        deleted_count = len(result.get("delete", []))
        logger.info(
            "Batch delete WordPress completado",
            extra={"ids": ids, "deleted": deleted_count},
        )
        return _ok({"deleted": deleted_count}, f"{deleted_count} productos eliminados de WooCommerce.")
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_products.post("/sync")
async def sync_from_job(body: SyncFromJobRequest) -> dict[str, Any]:
    """
    Sincroniza productos de un job Harvist a WooCommerce.

    Flujo por producto:
      1. Lee datos del job (CSV enriquecido).
      2. Si existe imagen, la sube al Media Library.
      3. Crea o actualiza producto por SKU.

    Args:
        body: job_id, product_codes, overwrite.

    Returns:
        Resumen de la sincronización.
    """
    settings = get_settings()
    client = await _get_client()

    try:
        storage = get_storage_service(settings)
        svc_products = WordPressProductService(client)
        svc_media = WordPressMediaService(client)

        created = updated = skipped = errors = 0
        results: list[dict[str, Any]] = []

        for codigo in body.product_codes:
            try:
                harvist_data: dict[str, Any] = {"codigo": codigo}

                media_id: int | None = None
                try:
                    img_path = storage.get_image_path(body.job_id, codigo)
                    if img_path and img_path.exists():
                        media_item = await svc_media.upload_from_path(img_path)
                        media_id = media_item.get("id")
                except Exception as exc_img:
                    logger.warning(
                        "No se pudo subir imagen a WordPress",
                        exc_info=exc_img,
                        extra={"job_id": body.job_id, "codigo": codigo},
                    )

                existing = await svc_products.find_by_sku(codigo)
                if existing and not body.overwrite:
                    skipped += 1
                    results.append({"codigo": codigo, "action": "skipped", "wc_id": existing["id"]})
                    continue

                result = await svc_products.sync_from_harvist(
                    harvist_data, overwrite=body.overwrite, media_id=media_id
                )
                if existing:
                    updated += 1
                    results.append({"codigo": codigo, "action": "updated", "wc_id": result["id"]})
                else:
                    created += 1
                    results.append({"codigo": codigo, "action": "created", "wc_id": result["id"]})

            except Exception as exc:
                errors += 1
                results.append({"codigo": codigo, "action": "error", "error": str(exc)})
                logger.error(
                    "Error sincronizando producto a WordPress",
                    exc_info=exc,
                    extra={"job_id": body.job_id, "codigo": codigo},
                )

        return _ok(
            {
                "total": len(body.product_codes),
                "created": created,
                "updated": updated,
                "skipped": skipped,
                "errors": errors,
                "results": results,
            },
            f"Sincronización completada: {created} creados, {updated} actualizados.",
        )
    finally:
        await client.close()


# ── CSV Import ──────────────────────────────────────────────────────────────

_MAX_CSV_BYTES = 10 * 1024 * 1024  # 10 MB
_WP_IMPORT_KEY = "wordpress_import:{task_id}"
_WP_IMPORT_TTL = 86400  # 24 horas


@router_products.get("/csv/fields")
async def get_csv_import_fields() -> JSONResponse:
    """
    Devuelve la lista de campos WooCommerce disponibles para el mapeo CSV.

    No requiere conexión a WordPress.

    Returns:
        Lista de {key, label} para construir el selector de mapeo en el frontend.
    """
    from services.integrations.wordpress.products import WC_IMPORT_FIELDS  # noqa: PLC0415

    return JSONResponse(content=_ok(WC_IMPORT_FIELDS, "Campos WooCommerce disponibles."))


@router_products.post("/csv/preview")
async def csv_preview(file: UploadFile) -> JSONResponse:
    """
    Pre-analiza un CSV y devuelve cabeceras + filas de muestra.

    No requiere conexión a WordPress. Sirve para construir la UI de mapeo
    antes de lanzar la importación real.

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

    svc = WordPressProductService.__new__(WordPressProductService)
    try:
        preview_data = svc.parse_csv_preview(content, preview_rows=5)
    except Exception as exc:
        logger.error("Error pre-analizando CSV para WordPress", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No se pudo parsear el CSV: {exc}",
        )

    result = CsvImportPreview(**preview_data)
    return JSONResponse(content=_ok(result.model_dump(), "CSV analizado."))


@router_products.post("/csv/import", status_code=status.HTTP_202_ACCEPTED)
async def import_from_csv(
    file: UploadFile,
    mapping: str = Form(...),
    overwrite: bool = Form(default=False),
    brand_column: str = Form(default=""),
    category_column: str = Form(default=""),
    subcategory_column: str = Form(default=""),
) -> JSONResponse:
    """
    Inicia la importación masiva de productos desde CSV como tarea Celery asíncrona.

    Valida el CSV y el mapeo de forma síncrona. Si todo es correcto,
    encola la tarea y devuelve un ``task_id`` inmediatamente (HTTP 202).
    El cliente debe hacer polling a ``GET /csv/import/{task_id}`` para
    consultar el progreso y obtener los resultados.

    Args:
        file:                CSV de productos (multipart).
        mapping:             JSON string con el mapeo columna_csv → campo_woocommerce.
        overwrite:           si True, actualiza productos que ya existen (por SKU).
        brand_column:        nombre de la columna CSV con la marca (opcional).
        category_column:     nombre de la columna CSV con la categoría raíz (opcional).
        subcategory_column:  nombre de la columna CSV con la subcategoría (opcional).

    Returns:
        HTTP 202 con ``{task_id, status: "pending"}``.
    """
    from workers.tasks import importar_productos_wordpress  # noqa: PLC0415

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

    if not any(v == "name" for v in mapping_dict.values()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El mapeo debe incluir al menos una columna asignada al campo 'name' (Nombre).",
        )

    settings = get_settings()
    task_id = str(uuid.uuid4())
    csv_b64 = base64.b64encode(content).decode()

    creds = await _get_wp_credentials()

    importar_productos_wordpress.delay(
        task_id=task_id,
        csv_b64=csv_b64,
        mapping=mapping_dict,
        overwrite=overwrite,
        brand_column=brand_column.strip(),
        category_column=category_column.strip(),
        subcategory_column=subcategory_column.strip(),
        wp_url=creds.get("url", ""),
        wp_consumer_key=creds.get("consumer_key", ""),
        wp_consumer_secret=creds.get("consumer_secret", ""),
    )

    logger.info("Importación WordPress encolada", extra={"task_id": task_id})

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=_ok({"task_id": task_id, "status": "pending"}, "Importación iniciada."),
    )


@router_products.get("/csv/import/{task_id}")
async def get_import_status(task_id: str) -> JSONResponse:
    """
    Consulta el estado de una tarea de importación CSV de WordPress.

    Args:
        task_id: UUID de la tarea devuelto por POST /csv/import.

    Returns:
        Estado actual: pending/running/completed/failed + progreso + resultados.
    """
    redis_url = get_settings().redis_url or "redis://localhost:6379/0"
    redis = aioredis.from_url(redis_url, decode_responses=True)
    try:
        raw = await redis.get(_WP_IMPORT_KEY.format(task_id=task_id))
    finally:
        await redis.aclose()

    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tarea {task_id} no encontrada o expirada.",
        )

    return JSONResponse(content=_ok(json.loads(raw), "Estado de importación."))


# ── Categories ──────────────────────────────────────────────────────────────


@router_categories.get("")
async def list_categories(
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """
    Lista categorías WooCommerce.

    Args:
        limit: elementos por página.
        offset: desplazamiento.

    Returns:
        Lista de categorías.
    """
    client = await _get_client()
    try:
        svc = WordPressCategoryService(client)
        items = await svc.list(limit=limit, offset=offset)
        return _ok(items)
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_categories.get("/tree")
async def get_categories_tree() -> dict[str, Any]:
    """
    Devuelve las categorías en árbol jerárquico.

    Returns:
        Lista de categorías raíz con campo "children".
    """
    client = await _get_client()
    try:
        svc = WordPressCategoryService(client)
        tree = await svc.tree()
        return _ok(tree)
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_categories.get("/{category_id}")
async def get_category(category_id: int) -> dict[str, Any]:
    """Obtiene una categoría por ID."""
    client = await _get_client()
    try:
        svc = WordPressCategoryService(client)
        return _ok(await svc.get(category_id))
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_categories.post("", status_code=status.HTTP_201_CREATED)
async def create_category(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Crea una categoría en WooCommerce."""
    client = await _get_client()
    try:
        svc = WordPressCategoryService(client)
        return _ok(await svc.create(body), "Categoría creada.")
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_categories.put("/{category_id}")
async def update_category(category_id: int, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Actualiza una categoría en WooCommerce."""
    client = await _get_client()
    try:
        svc = WordPressCategoryService(client)
        return _ok(await svc.update(category_id, body), "Categoría actualizada.")
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_categories.delete("/{category_id}")
async def delete_category(category_id: int) -> dict[str, Any]:
    """Elimina una categoría de WooCommerce."""
    client = await _get_client()
    try:
        svc = WordPressCategoryService(client)
        await svc.delete(category_id)
        return _ok({}, "Categoría eliminada.")
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


# ── Brands ──────────────────────────────────────────────────────────────────


@router_brands.get("")
async def list_brands(
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """
    Lista los términos de marca del atributo pa_brand de WooCommerce.

    Args:
        limit: máximo de marcas a retornar.
        offset: desplazamiento para paginación.

    Returns:
        Lista de términos de marca con id, name, slug, count, description.
    """
    client = await _get_client()
    try:
        svc = await _get_brand_service(client)
        items = await svc.list(limit=limit, offset=offset)
        return _ok({"items": items, "total": len(items), "limit": limit, "offset": offset})
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_brands.get("/all-attributes")
async def list_all_wc_attributes() -> dict[str, Any]:
    """
    Lista todos los atributos de producto globales de WooCommerce.

    Permite al usuario identificar qué atributo contiene sus marcas
    y configurar el override si la detección automática falla.

    Returns:
        Lista de atributos con id, name, slug, term_count.
    """
    client = await _get_client()
    try:
        svc = await _get_brand_service(client)
        items = await svc.list_all_attributes()
        return _ok(items)
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_brands.put("/attribute")
async def configure_brand_attribute(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """
    Configura el atributo de WooCommerce que se usará para marcas.

    Guarda el ID del atributo en Redis para que todas las llamadas
    posteriores usen ese atributo en lugar de la detección automática.

    Args:
        body: ``{"attr_id": 5}`` con el ID del atributo deseado.

    Returns:
        Info del atributo configurado.
    """
    import redis.asyncio as aioredis

    attr_id = body.get("attr_id")
    if not attr_id or not isinstance(attr_id, int):
        raise HTTPException(status_code=422, detail="El campo 'attr_id' es obligatorio y debe ser entero.")

    settings = get_settings()
    redis_client: aioredis.Redis | None = None
    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await redis_client.set("integration:wordpress:brand_attr_id", str(attr_id))
        logger.info("Brand attr ID configurado manualmente", extra={"attr_id": attr_id})
    except Exception as exc:
        logger.warning("No se pudo guardar brand_attr_id en Redis", exc_info=exc)
    finally:
        if redis_client:
            await redis_client.aclose()

    client = await _get_client()
    try:
        svc = WordPressBrandService(client, attr_id_override=attr_id)
        attr = await svc.get_attribute_info()
        return _ok(attr, f"Atributo de marca configurado a ID {attr_id}.")
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_brands.get("/attribute")
async def get_brand_attribute() -> dict[str, Any]:
    """
    Devuelve los metadatos del atributo global pa_brand de WooCommerce.

    Crea el atributo si no existe. Útil para que el frontend construya el
    payload de ``attributes`` al asignar marcas a productos.

    Returns:
        Dict con id, slug y name del atributo pa_brand.
    """
    client = await _get_client()
    try:
        svc = await _get_brand_service(client)
        attr = await svc.get_attribute_info()
        return _ok(attr)
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_brands.post("", status_code=status.HTTP_201_CREATED)
async def create_brand(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """
    Crea un nuevo término de marca en el atributo pa_brand de WooCommerce.

    Args:
        body: campos de la marca (name requerido, description opcional).

    Returns:
        Término de marca creado.
    """
    name: str = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="El campo 'name' es obligatorio.")
    description: str = body.get("description", "")
    client = await _get_client()
    try:
        svc = await _get_brand_service(client)
        result = await svc.create(name=name, description=description)
        return _ok(result, "Marca creada.")
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_brands.put("/{term_id}")
async def update_brand(term_id: int, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """
    Actualiza un término de marca en WooCommerce.

    Args:
        term_id: ID del término a actualizar.
        body: campos a modificar (name, description, slug).

    Returns:
        Término de marca actualizado.
    """
    client = await _get_client()
    try:
        svc = await _get_brand_service(client)
        result = await svc.update(term_id, body)
        return _ok(result, "Marca actualizada.")
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_brands.delete("/{term_id}")
async def delete_brand(term_id: int) -> dict[str, Any]:
    """
    Elimina un término de marca del atributo pa_brand de WooCommerce.

    Args:
        term_id: ID del término a eliminar.

    Returns:
        Confirmación de eliminación.
    """
    client = await _get_client()
    try:
        svc = await _get_brand_service(client)
        await svc.delete(term_id)
        return _ok({}, "Marca eliminada.")
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_brands.get("/{term_id}/products")
async def get_brand_products(
    term_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """
    Lista los productos que tienen asignada una marca concreta.

    Args:
        term_id: ID del término de marca.
        limit: máximo de productos a retornar.
        offset: desplazamiento para paginación.

    Returns:
        Lista de productos WooCommerce con la marca especificada.
    """
    client = await _get_client()
    try:
        svc = await _get_brand_service(client)
        items = await svc.get_products(term_id=term_id, limit=limit, offset=offset)
        return _ok(
            {"items": items, "total": len(items), "limit": limit, "offset": offset},
        )
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


# ── Orders ──────────────────────────────────────────────────────────────────


@router_orders.get("")
async def list_orders(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: str = Query(default="any", alias="status"),
    customer: int | None = Query(default=None),
) -> dict[str, Any]:
    """Lista pedidos WooCommerce."""
    client = await _get_client()
    try:
        svc = WordPressOrderService(client)
        items = await svc.list(limit=limit, offset=offset, status=status_filter, customer=customer)
        return _ok(
            PaginatedResponse(
                items=items, total=len(items), limit=limit, offset=offset, has_more=len(items) == limit
            ).model_dump()
        )
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_orders.get("/{order_id}")
async def get_order(order_id: int) -> dict[str, Any]:
    """Obtiene un pedido por ID."""
    client = await _get_client()
    try:
        svc = WordPressOrderService(client)
        return _ok(await svc.get(order_id))
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_orders.put("/{order_id}/status")
async def update_order_status(
    order_id: int,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """
    Cambia el estado de un pedido.

    Args:
        order_id: ID del pedido.
        body: {"status": "completed", "note": "..."}

    Returns:
        Dict con el pedido actualizado.
    """
    client = await _get_client()
    try:
        svc = WordPressOrderService(client)
        new_status = body.get("status", "")
        note = body.get("note", "")
        if not new_status:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="El campo 'status' es obligatorio.",
            )
        result = await svc.update_status(order_id, new_status, note)
        return _ok(result, f"Estado del pedido {order_id} cambiado a '{new_status}'.")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_orders.post("/{order_id}/notes")
async def add_order_note(order_id: int, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Añade una nota a un pedido."""
    client = await _get_client()
    try:
        svc = WordPressOrderService(client)
        note = body.get("note", "")
        customer_note = bool(body.get("customer_note", False))
        result = await svc.add_note(order_id, note, customer_note)
        return _ok(result, "Nota añadida al pedido.")
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


# ── Customers ───────────────────────────────────────────────────────────────


@router_customers.get("")
async def list_customers(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str = Query(default=""),
    role: str = Query(default="customer"),
) -> dict[str, Any]:
    """Lista clientes WooCommerce."""
    client = await _get_client()
    try:
        svc = WordPressCustomerService(client)
        items = await svc.list(limit=limit, offset=offset, search=search, role=role)
        return _ok(
            PaginatedResponse(
                items=items, total=len(items), limit=limit, offset=offset, has_more=len(items) == limit
            ).model_dump()
        )
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_customers.get("/{customer_id}")
async def get_customer(customer_id: int) -> dict[str, Any]:
    """Obtiene un cliente por ID."""
    client = await _get_client()
    try:
        svc = WordPressCustomerService(client)
        return _ok(await svc.get(customer_id))
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_customers.post("", status_code=status.HTTP_201_CREATED)
async def create_customer(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Crea un cliente en WooCommerce."""
    client = await _get_client()
    try:
        svc = WordPressCustomerService(client)
        return _ok(await svc.create(body), "Cliente creado.")
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_customers.put("/{customer_id}")
async def update_customer(customer_id: int, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Actualiza un cliente en WooCommerce."""
    client = await _get_client()
    try:
        svc = WordPressCustomerService(client)
        return _ok(await svc.update(customer_id, body), "Cliente actualizado.")
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_customers.delete("/{customer_id}")
async def delete_customer(customer_id: int) -> dict[str, Any]:
    """Elimina un cliente de WooCommerce."""
    client = await _get_client()
    try:
        svc = WordPressCustomerService(client)
        await svc.delete(customer_id)
        return _ok({}, "Cliente eliminado.")
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


# ── Media ───────────────────────────────────────────────────────────────────


@router_media.get("")
async def list_media(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Lista archivos del Media Library de WordPress."""
    client = await _get_client()
    try:
        svc = WordPressMediaService(client)
        items = await svc.list(limit=limit, offset=offset)
        return _ok(
            PaginatedResponse(
                items=items, total=len(items), limit=limit, offset=offset, has_more=len(items) == limit
            ).model_dump()
        )
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_media.post("", status_code=status.HTTP_201_CREATED)
async def upload_media(file: UploadFile = File(...)) -> dict[str, Any]:
    """
    Sube un archivo al Media Library de WordPress.

    Args:
        file: archivo multipart (image/jpeg, image/png, image/webp).

    Returns:
        Dict con el media item creado (id, source_url, etc.).
    """
    if file.content_type not in _ALLOWED_MEDIA_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Tipo de archivo no soportado: {file.content_type}. "
                   f"Tipos permitidos: {_ALLOWED_MEDIA_TYPES}",
        )

    data = await file.read()
    if len(data) > _MAX_MEDIA_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Archivo demasiado grande. Máximo: {_MAX_MEDIA_BYTES // 1024 // 1024} MB.",
        )

    client = await _get_client()
    try:
        svc = WordPressMediaService(client)
        result = await svc.upload(file.filename or "upload.jpg", data, file.content_type or "")
        return _ok(result, "Archivo subido al Media Library.")
    except (IntegrationError, ValueError) as exc:
        status_code_val = getattr(exc, "status_code", None) or 502
        raise HTTPException(status_code=status_code_val, detail=str(exc)) from exc
    finally:
        await client.close()


# ── Database (phpMyAdmin) ───────────────────────────────────────────────────


@router_db.get("/tables")
async def list_db_tables() -> dict[str, Any]:
    """
    Lista las tablas de la BD MySQL de WordPress con estadísticas.

    Returns:
        Lista de tablas con nombre, número de filas, tamaño y motor.
    """
    db = await _get_db_service()
    try:
        tables = await db.list_tables()
        return _ok(tables)
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router_db.get("/site-info")
async def get_site_info() -> dict[str, Any]:
    """
    Obtiene información básica del sitio WordPress desde wp_options.

    Returns:
        Dict con siteurl, blogname, blogdescription, admin_email, db_version.
    """
    db = await _get_db_service()
    try:
        info = await db.get_site_info()
        return _ok(info)
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router_db.post("/query")
async def execute_query(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """
    Ejecuta una consulta SQL SELECT contra la BD de WordPress.

    Solo permite SELECT. Para operaciones de escritura, usar los endpoints REST.

    Args:
        body: {"sql": "SELECT ...", "params": []}

    Returns:
        Lista de filas resultantes.
    """
    sql = body.get("sql", "").strip()
    params = tuple(body.get("params", []))

    if not sql:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El campo 'sql' es obligatorio.",
        )

    db = await _get_db_service()
    try:
        rows = await db.query(sql, params=params, read_only=True)
        return _ok({"rows": rows, "count": len(rows)})
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router_db.get("/options/{option_name}")
async def get_wp_option(option_name: str) -> dict[str, Any]:
    """
    Lee el valor de una opción de WordPress desde wp_options.

    Args:
        option_name: nombre de la opción (ej: "siteurl", "blogname").

    Returns:
        Dict con el valor de la opción.
    """
    db = await _get_db_service()
    try:
        value = await db.get_option(option_name)
        if value is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Opción '{option_name}' no encontrada.",
            )
        return _ok({"option_name": option_name, "option_value": value})
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ── Webhooks ─────────────────────────────────────────────────────────────────


@router_webhooks.post("/product")
async def webhook_product_updated(request: Request) -> dict[str, Any]:
    """
    Recibe webhooks de WooCommerce para actualizaciones de producto.

    WooCommerce dispara ``product.updated`` cuando cambia el stock de un producto,
    incluyendo al procesar un pedido. Este endpoint sincroniza el nuevo stock a Dolibarr.

    Configurar en WooCommerce → Ajustes → Avanzado → Webhooks:
      Tópico: Producto actualizado
      URL de entrega: POST /api/v1/wordpress/webhooks/product

    Args:
        request: petición HTTP con el payload JSON del producto WooCommerce.

    Returns:
        200 siempre — WooCommerce requiere 200 para marcar la entrega como exitosa.
    """
    raw_body = await request.body()
    topic = request.headers.get("X-WC-Webhook-Topic", "unknown")

    try:
        payload: dict[str, Any] = json.loads(raw_body)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Webhook WC payload inválido", extra={"topic": topic})
        return _ok({}, "Payload inválido, ignorado.")

    wc_product_id = payload.get("id")
    logger.info("Webhook WC recibido", extra={"topic": topic, "wc_product_id": wc_product_id})

    sku: str = (payload.get("sku") or "").strip()
    wc_stock = payload.get("stock_quantity")
    manage_stock = bool(payload.get("manage_stock"))

    if not sku or wc_stock is None or not manage_stock:
        return _ok({}, "Webhook recibido sin cambio de stock aplicable.")

    doli_svc = await _get_dolibarr_product_service()
    if doli_svc is None:
        logger.warning("Dolibarr no configurado, webhook ignorado", extra={"sku": sku})
        return _ok({}, "Webhook recibido (Dolibarr no configurado).")

    try:
        result = await _sync_wc_stock_to_dolibarr(sku, wc_stock, doli_svc)
        return _ok(result, "Webhook procesado.")
    except Exception as exc:
        logger.warning("Webhook stock WP→Dolibarr falló", exc_info=exc, extra={"sku": sku})
        return _ok({"error": str(exc)}, "Webhook recibido (sync falló).")
