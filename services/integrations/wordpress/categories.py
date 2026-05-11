"""
Servicio de gestión de categorías WooCommerce.

Cubre árbol jerárquico, CRUD y asignación a productos.

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from services.integrations.wordpress.client import WordPressClient


class WordPressCategoryService:
    """
    Servicio CRUD para categorías WooCommerce.

    :author: Carlitos6712
    """

    _RESOURCE = "products/categories"

    def __init__(self, client: WordPressClient) -> None:
        """
        Args:
            client: instancia de WordPressClient ya configurada.
        """
        self._client = client

    async def list(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """
        Lista categorías WooCommerce.

        Args:
            limit: elementos por página.
            offset: desplazamiento.

        Returns:
            Lista de dicts con las categorías.
        """
        return await self._client.list(self._RESOURCE, limit=limit, offset=offset)

    async def get(self, category_id: int) -> dict[str, Any]:
        """
        Obtiene una categoría por su ID.

        Args:
            category_id: ID de la categoría.

        Returns:
            Dict con los datos de la categoría.
        """
        return await self._client.get(self._RESOURCE, category_id)

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Crea una categoría en WooCommerce.

        Args:
            data: campos de la categoría (name, parent, description, slug).

        Returns:
            Dict con la categoría creada.
        """
        result = await self._client.create(self._RESOURCE, data)
        logger.info("Categoría WooCommerce creada", extra={"wc_id": result.get("id")})
        return result

    async def update(self, category_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """
        Actualiza una categoría existente.

        Args:
            category_id: ID de la categoría.
            data: campos a actualizar.

        Returns:
            Dict con la categoría actualizada.
        """
        return await self._client.update(self._RESOURCE, category_id, data)

    async def delete(self, category_id: int) -> bool:
        """
        Elimina una categoría de WooCommerce.

        Args:
            category_id: ID de la categoría.

        Returns:
            True si se eliminó correctamente.
        """
        return await self._client.delete(self._RESOURCE, category_id)

    async def tree(self) -> list[dict[str, Any]]:
        """
        Devuelve las categorías organizadas en árbol jerárquico.

        Returns:
            Lista de categorías raíz, cada una con campo "children".
        """
        all_cats = await self.list(limit=100)
        by_id: dict[int, dict[str, Any]] = {}
        for cat in all_cats:
            cat["children"] = []
            by_id[cat["id"]] = cat

        roots: list[dict[str, Any]] = []
        for cat in all_cats:
            parent_id = cat.get("parent", 0)
            if parent_id and parent_id in by_id:
                by_id[parent_id]["children"].append(cat)
            else:
                roots.append(cat)

        return roots

    async def find_or_create(self, name: str, parent_id: int = 0) -> dict[str, Any]:
        """
        Busca una categoría por nombre o la crea si no existe.

        Args:
            name: nombre de la categoría.
            parent_id: ID de la categoría padre (0 para raíz).

        Returns:
            Dict de la categoría encontrada o creada.
        """
        all_cats = await self.list(limit=100)
        for cat in all_cats:
            if cat["name"].lower() == name.lower() and cat.get("parent", 0) == parent_id:
                return cat
        return await self.create({"name": name, "parent": parent_id})
