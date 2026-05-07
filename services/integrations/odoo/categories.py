"""
Servicio de gestión de categorías de producto en Odoo (product.category).

:author: Carlitos6712
:version: 1.0.0
"""

from loguru import logger

from services.integrations.base import IntegrationClient, IntegrationError


class OooCategoryService:
    """
    Servicio CRUD de categorías de producto en Odoo.

    :author: Carlitos6712
    """

    _FIELDS = ["id", "name", "complete_name", "parent_id", "child_id"]

    def __init__(self, client: IntegrationClient) -> None:
        """
        Args:
            client: cliente Odoo autenticado.
        """
        self._client = client

    async def list_categories(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """
        Lista categorías con paginación.

        Args:
            limit:  máximo de resultados.
            offset: desplazamiento.

        Returns:
            Lista de dicts de product.category.

        Raises:
            IntegrationError: si Odoo falla.
        """
        try:
            return await self._client.list(
                "product.category",
                limit=limit,
                offset=offset,
                filters={"domain": [], "fields": self._FIELDS, "order": "complete_name asc"},
            )
        except Exception as exc:
            logger.error("Error listando categorías Odoo", exc_info=exc)
            raise IntegrationError("Fallo listando categorías Odoo") from exc

    async def get_category(self, category_id: int) -> dict:
        """
        Obtiene una categoría por ID.

        Args:
            category_id: ID de product.category.

        Returns:
            Dict con datos de la categoría.

        Raises:
            IntegrationError: si no existe o falla.
        """
        try:
            return await self._client.get("product.category", category_id)
        except Exception as exc:
            logger.error("Error obteniendo categoría Odoo", exc_info=exc, extra={"id": category_id})
            raise IntegrationError(f"Categoría Odoo {category_id} no encontrada") from exc

    async def create_category(self, name: str, parent_id: int | None = None) -> dict:
        """
        Crea una categoría en Odoo.

        Args:
            name:      nombre de la categoría.
            parent_id: ID de la categoría padre (opcional).

        Returns:
            Categoría creada.

        Raises:
            IntegrationError: si falla.
        """
        data: dict = {"name": name}
        if parent_id is not None:
            data["parent_id"] = parent_id
        try:
            result = await self._client.create("product.category", data)
            logger.info("Categoría Odoo creada", extra={"id": result.get("id"), "name": name})
            return result
        except Exception as exc:
            logger.error("Error creando categoría Odoo", exc_info=exc)
            raise IntegrationError("Fallo creando categoría Odoo") from exc

    async def update_category(self, category_id: int, data: dict) -> dict:
        """
        Actualiza una categoría existente.

        Args:
            category_id: ID de la categoría.
            data:        campos a actualizar.

        Returns:
            Categoría actualizada.

        Raises:
            IntegrationError: si falla.
        """
        try:
            result = await self._client.update("product.category", category_id, data)
            logger.info("Categoría Odoo actualizada", extra={"id": category_id})
            return result
        except Exception as exc:
            logger.error("Error actualizando categoría Odoo", exc_info=exc, extra={"id": category_id})
            raise IntegrationError(f"Fallo actualizando categoría Odoo {category_id}") from exc

    async def delete_category(self, category_id: int) -> bool:
        """
        Elimina una categoría.

        Args:
            category_id: ID de la categoría.

        Returns:
            True si se eliminó.

        Raises:
            IntegrationError: si falla.
        """
        try:
            result = await self._client.delete("product.category", category_id)
            logger.info("Categoría Odoo eliminada", extra={"id": category_id})
            return result
        except Exception as exc:
            logger.error("Error eliminando categoría Odoo", exc_info=exc, extra={"id": category_id})
            raise IntegrationError(f"Fallo eliminando categoría Odoo {category_id}") from exc

    async def count_categories(self) -> int:
        """
        Cuenta el total de categorías.

        Returns:
            Número de categorías.
        """
        from services.integrations.odoo.client import OdooClient
        if not isinstance(self._client, OdooClient):
            return 0
        return await self._client.search_count("product.category")
