"""
Servicio de gestión de productos WooCommerce.

Cubre productos simples, variables y agrupados.
Sincronización desde job Harvist → WooCommerce.

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from services.integrations.base import IntegrationError
from services.integrations.wordpress.client import WordPressClient


class WordPressProductService:
    """
    Servicio CRUD para productos WooCommerce.

    :author: Carlitos6712
    """

    _RESOURCE = "products"

    def __init__(self, client: WordPressClient) -> None:
        """
        Args:
            client: instancia de WordPressClient ya configurada.
        """
        self._client = client

    async def list(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str = "any",
        category: int | None = None,
        search: str = "",
    ) -> list[dict[str, Any]]:
        """
        Lista productos de WooCommerce con paginación y filtros opcionales.

        Args:
            limit: elementos por página.
            offset: desplazamiento.
            status: filtro de estado ("any", "publish", "draft", "private").
            category: ID de categoría para filtrar.
            search: término de búsqueda.

        Returns:
            Lista de dicts con los productos.
        """
        filters: dict[str, Any] = {"status": status}
        if category is not None:
            filters["category"] = category
        if search:
            filters["search"] = search
        return await self._client.list(self._RESOURCE, limit=limit, offset=offset, filters=filters)

    async def get(self, product_id: int) -> dict[str, Any]:
        """
        Obtiene un producto por su ID.

        Args:
            product_id: ID del producto en WooCommerce.

        Returns:
            Dict con los datos del producto.

        Raises:
            IntegrationError: si el producto no existe.
        """
        return await self._client.get(self._RESOURCE, product_id)

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Crea un producto en WooCommerce.

        Args:
            data: campos del producto (name, type, regular_price, sku, etc.).

        Returns:
            Dict con el producto creado incluyendo su ID.
        """
        result = await self._client.create(self._RESOURCE, data)
        logger.info("Producto WooCommerce creado", extra={"wc_id": result.get("id")})
        return result

    async def update(self, product_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """
        Actualiza un producto existente.

        Args:
            product_id: ID del producto.
            data: campos a actualizar.

        Returns:
            Dict con el producto actualizado.
        """
        result = await self._client.update(self._RESOURCE, product_id, data)
        logger.info("Producto WooCommerce actualizado", extra={"wc_id": product_id})
        return result

    async def delete(self, product_id: int) -> bool:
        """
        Elimina un producto de WooCommerce (force=true).

        Args:
            product_id: ID del producto.

        Returns:
            True si se eliminó correctamente.
        """
        result = await self._client.delete(self._RESOURCE, product_id)
        logger.info("Producto WooCommerce eliminado", extra={"wc_id": product_id})
        return result

    async def find_by_sku(self, sku: str) -> dict[str, Any] | None:
        """
        Busca un producto por SKU. Devuelve None si no existe.

        Args:
            sku: referencia del producto.

        Returns:
            Dict del producto o None si no se encuentra.
        """
        items = await self._client.list(self._RESOURCE, filters={"sku": sku})
        return items[0] if items else None

    async def set_image(self, product_id: int, media_id: int) -> dict[str, Any]:
        """
        Asigna una imagen como imagen destacada del producto.

        Args:
            product_id: ID del producto.
            media_id: ID del media item en WordPress Media Library.

        Returns:
            Dict con el producto actualizado.
        """
        return await self.update(product_id, {"images": [{"id": media_id}]})

    async def list_variations(self, product_id: int) -> list[dict[str, Any]]:
        """
        Lista las variantes de un producto variable.

        Args:
            product_id: ID del producto variable.

        Returns:
            Lista de dicts con las variantes.
        """
        return await self._client.list(f"{self._RESOURCE}/{product_id}/variations", limit=100)

    async def create_variation(
        self, product_id: int, data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Crea una variante en un producto variable.

        Args:
            product_id: ID del producto variable.
            data: datos de la variante (attributes, regular_price, sku, stock_quantity, etc.).

        Returns:
            Dict con la variante creada.
        """
        return await self._client.create(f"{self._RESOURCE}/{product_id}/variations", data)

    async def sync_from_harvist(
        self,
        harvist_product: dict[str, Any],
        overwrite: bool = False,
        media_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Sincroniza un producto Harvist a WooCommerce (crea o actualiza por SKU).

        Mapeo Harvist → WooCommerce:
          codigo    → sku
          nombre    → name
          descripcion → description
          precio    → regular_price
          peso      → weight
          imagen (media_id) → images

        Args:
            harvist_product: dict con datos del producto Harvist.
            overwrite: si True, sobreescribe productos existentes.
            media_id: ID del media item ya subido a WordPress.

        Returns:
            Dict del producto creado o actualizado en WooCommerce.
        """
        sku = harvist_product.get("codigo", "")
        payload: dict[str, Any] = {
            "name": harvist_product.get("nombre", ""),
            "sku": sku,
            "description": harvist_product.get("descripcion_larga", ""),
            "short_description": harvist_product.get("descripcion_corta", ""),
            "regular_price": str(harvist_product.get("precio", "")),
            "weight": str(harvist_product.get("peso", "")),
            "status": "publish",
            "type": "simple",
            "manage_stock": True,
        }
        if media_id:
            payload["images"] = [{"id": media_id}]

        existing = await self.find_by_sku(sku)
        if existing:
            if not overwrite:
                logger.info("Producto ya existe en WooCommerce, skipping", extra={"sku": sku})
                return existing
            return await self.update(existing["id"], payload)

        return await self.create(payload)
