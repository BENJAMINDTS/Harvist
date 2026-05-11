"""
Servicio de gestión de clientes WooCommerce.

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from services.integrations.wordpress.client import WordPressClient


class WordPressCustomerService:
    """
    Servicio CRUD para clientes WooCommerce.

    :author: Carlitos6712
    """

    _RESOURCE = "customers"

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
        search: str = "",
        role: str = "customer",
    ) -> list[dict[str, Any]]:
        """
        Lista clientes WooCommerce.

        Args:
            limit: elementos por página.
            offset: desplazamiento.
            search: término de búsqueda por nombre/email.
            role: rol de usuario ("customer", "subscriber", "all").

        Returns:
            Lista de dicts con los clientes.
        """
        filters: dict[str, Any] = {"role": role}
        if search:
            filters["search"] = search
        return await self._client.list(self._RESOURCE, limit=limit, offset=offset, filters=filters)

    async def get(self, customer_id: int) -> dict[str, Any]:
        """
        Obtiene un cliente por su ID.

        Args:
            customer_id: ID del cliente.

        Returns:
            Dict con los datos del cliente.
        """
        return await self._client.get(self._RESOURCE, customer_id)

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Crea un cliente en WooCommerce.

        Args:
            data: campos del cliente (email, first_name, last_name, username, password).

        Returns:
            Dict con el cliente creado.
        """
        result = await self._client.create(self._RESOURCE, data)
        logger.info(
            "Cliente WooCommerce creado",
            extra={"wc_id": result.get("id"), "email": result.get("email")},
        )
        return result

    async def update(self, customer_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """
        Actualiza un cliente existente.

        Args:
            customer_id: ID del cliente.
            data: campos a actualizar.

        Returns:
            Dict con el cliente actualizado.
        """
        return await self._client.update(self._RESOURCE, customer_id, data)

    async def delete(self, customer_id: int) -> bool:
        """
        Elimina un cliente de WooCommerce.

        Args:
            customer_id: ID del cliente.

        Returns:
            True si se eliminó correctamente.
        """
        return await self._client.delete(self._RESOURCE, customer_id)

    async def get_orders(self, customer_id: int) -> list[dict[str, Any]]:
        """
        Lista los pedidos de un cliente.

        Args:
            customer_id: ID del cliente.

        Returns:
            Lista de pedidos del cliente.
        """
        return await self._client.list("orders", filters={"customer": customer_id})
