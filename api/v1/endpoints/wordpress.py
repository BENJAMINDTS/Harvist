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

import json
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Body, File, HTTPException, Query, UploadFile, status
from loguru import logger

from api.core.config import get_settings
from api.v1.schemas.integrations import (
    IntegrationStatus,
    PaginatedResponse,
    SyncFromJobRequest,
    WordPressConfigRequest,
    WordPressConfigResponse,
    WordPressDBConfigRequest,
    WordPressDBConfigResponse,
)
from services.integrations.base import IntegrationError, IntegrationNotConfiguredError
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
router_orders = APIRouter(prefix="/wordpress/orders", tags=["wordpress-orders"])
router_customers = APIRouter(prefix="/wordpress/customers", tags=["wordpress-customers"])
router_media = APIRouter(prefix="/wordpress/media", tags=["wordpress-media"])
router_db = APIRouter(prefix="/wordpress/db", tags=["wordpress-db"])

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
    Obtiene credenciales de WordPress desde Redis o .env.

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
    Obtiene credenciales de BD de WordPress desde Redis o .env.

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
        logger.info("Config WordPress guardada en Redis", extra={"url": body.url})
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
        logger.info("Config BD WordPress guardada en Redis", extra={"host": body.host})
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
        svc = WordPressProductService(client)
        items = await svc.list(
            limit=limit,
            offset=offset,
            status=status_filter,
            category=category,
            search=search,
        )
        return _ok(
            PaginatedResponse(
                items=items,
                total=len(items),
                limit=limit,
                offset=offset,
                has_more=len(items) == limit,
            ).model_dump(),
            "Productos obtenidos.",
        )
    except IntegrationError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
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
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_products.post("", status_code=status.HTTP_201_CREATED)
async def create_product(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """
    Crea un producto en WooCommerce.

    Args:
        body: campos del producto (name, type, regular_price, sku, etc.).

    Returns:
        Dict con el producto creado.
    """
    client = await _get_client()
    try:
        svc = WordPressProductService(client)
        item = await svc.create(body)
        return _ok(item, "Producto creado en WooCommerce.")
    except IntegrationError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
    finally:
        await client.close()


@router_products.put("/{product_id}")
async def update_product(product_id: int, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """
    Actualiza un producto en WooCommerce.

    Args:
        product_id: ID del producto.
        body: campos a actualizar.

    Returns:
        Dict con el producto actualizado.
    """
    client = await _get_client()
    try:
        svc = WordPressProductService(client)
        item = await svc.update(product_id, body)
        return _ok(item, "Producto actualizado en WooCommerce.")
    except IntegrationError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
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
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
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
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
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
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
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
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
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
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
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
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
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
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
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
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
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
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
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
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
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
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
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
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
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
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
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
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
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
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
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
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
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
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc
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
