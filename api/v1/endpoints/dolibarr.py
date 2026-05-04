"""
Endpoints de la integración Dolibarr.

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

Todos los endpoints devuelven 503 si Dolibarr no está configurado.

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from loguru import logger

from api.core.config import get_settings
from api.v1.schemas.integrations import PaginatedResponse, SyncFromJobRequest
from services.integrations.base import IntegrationError, IntegrationNotConfiguredError
from services.integrations.dolibarr.categories import DolibarrCategoryService
from services.integrations.dolibarr.client import DolibarrClient
from services.integrations.dolibarr.orders import DolibarrOrderService
from services.integrations.dolibarr.products import DolibarrProductService
from services.integrations.dolibarr.thirdparties import DolibarrThirdpartyService
from services.storage_service import get_storage_service

router = APIRouter(prefix="/dolibarr/products", tags=["dolibarr"])

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
_NOT_CONFIGURED_MSG = (
    "Dolibarr no está configurado. "
    "Define DOLIBARR_URL y DOLIBARR_API_KEY en tu archivo .env."
)


def _get_service() -> DolibarrProductService:
    """
    Construye y devuelve una instancia de DolibarrProductService.

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


@router.get("", response_model=PaginatedResponse)
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
    svc = _get_service()
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


@router.get("/{product_id}")
async def get_product(product_id: int) -> JSONResponse:
    """
    Obtiene un producto de Dolibarr por su ID.

    Args:
        product_id: ID del producto en Dolibarr.

    Returns:
        Respuesta estándar con los datos del producto.
    """
    svc = _get_service()
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


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_product(data: dict) -> JSONResponse:
    """
    Crea un producto en Dolibarr.

    Args:
        data: campos del producto (ref, label, price, description, type, status).

    Returns:
        Respuesta estándar (201) con el producto creado.
    """
    svc = _get_service()
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


@router.put("/{product_id}")
async def update_product(product_id: int, data: dict) -> JSONResponse:
    """
    Actualiza un producto existente en Dolibarr.

    Args:
        product_id: ID del producto en Dolibarr.
        data:       campos a actualizar.

    Returns:
        Respuesta estándar con el producto actualizado.
    """
    svc = _get_service()
    try:
        updated = await svc.update_product(product_id, data)
    except IntegrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content=_ok(updated, "Producto actualizado."))


@router.delete("/{product_id}")
async def delete_product(product_id: int) -> JSONResponse:
    """
    Elimina un producto de Dolibarr.

    Args:
        product_id: ID del producto a eliminar.

    Returns:
        Respuesta estándar con confirmación de eliminación.
    """
    svc = _get_service()
    try:
        await svc.delete_product(product_id)
    except IntegrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return JSONResponse(content={"success": True, "message": "Producto eliminado."})


@router.post("/{product_id}/image")
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
    svc = _get_service()

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


@router.post("/sync")
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
    svc = _get_service()
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


def _get_category_service() -> DolibarrCategoryService:
    """
    Construye y devuelve una instancia de DolibarrCategoryService.

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
    svc = _get_category_service()
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
    svc = _get_category_service()
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
    svc = _get_category_service()
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
    svc = _get_category_service()
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
    svc = _get_category_service()
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
    svc = _get_category_service()
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
    svc = _get_category_service()
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
    svc = _get_category_service()
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
    svc = _get_category_service()
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


def _get_order_service() -> DolibarrOrderService:
    """
    Construye y devuelve una instancia de DolibarrOrderService.

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
    svc = _get_order_service()
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
    svc = _get_order_service()
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
    svc = _get_order_service()
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
    svc = _get_order_service()
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
    svc = _get_order_service()
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
    svc = _get_order_service()
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
