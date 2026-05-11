"""
Servicio de gestión de pedidos WooCommerce.

Cubre listado, detalle y cambios de estado de pedidos.

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from services.integrations.wordpress.client import WordPressClient

_VALID_STATUSES = {
    "pending", "processing", "on-hold", "completed",
    "cancelled", "refunded", "failed", "trash",
}


class WordPressOrderService:
    """
    Servicio de pedidos WooCommerce.

    :author: Carlitos6712
    """

    _RESOURCE = "orders"

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
        customer: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Lista pedidos WooCommerce con paginación y filtros.

        Args:
            limit: elementos por página.
            offset: desplazamiento.
            status: filtro de estado del pedido.
            customer: ID de cliente para filtrar.

        Returns:
            Lista de dicts con los pedidos.
        """
        filters: dict[str, Any] = {"status": status}
        if customer is not None:
            filters["customer"] = customer
        return await self._client.list(self._RESOURCE, limit=limit, offset=offset, filters=filters)

    async def get(self, order_id: int) -> dict[str, Any]:
        """
        Obtiene un pedido por su ID.

        Args:
            order_id: ID del pedido.

        Returns:
            Dict con los datos del pedido.
        """
        return await self._client.get(self._RESOURCE, order_id)

    async def update_status(self, order_id: int, new_status: str, note: str = "") -> dict[str, Any]:
        """
        Cambia el estado de un pedido.

        Args:
            order_id: ID del pedido.
            new_status: nuevo estado (completed, cancelled, processing, etc.).
            note: nota interna opcional.

        Returns:
            Dict con el pedido actualizado.

        Raises:
            ValueError: si el estado no es válido.
        """
        if new_status not in _VALID_STATUSES:
            raise ValueError(
                f"Estado '{new_status}' no válido. Valores permitidos: {_VALID_STATUSES}"
            )
        data: dict[str, Any] = {"status": new_status}
        if note:
            data["customer_note"] = note
        result = await self._client.update(self._RESOURCE, order_id, data)
        logger.info(
            "Estado pedido WooCommerce actualizado",
            extra={"order_id": order_id, "status": new_status},
        )
        return result

    async def add_note(self, order_id: int, note: str, customer_note: bool = False) -> dict[str, Any]:
        """
        Añade una nota a un pedido.

        Args:
            order_id: ID del pedido.
            note: texto de la nota.
            customer_note: True si la nota es visible para el cliente.

        Returns:
            Dict con la nota creada.
        """
        return await self._client.create(
            f"{self._RESOURCE}/{order_id}/notes",
            {"note": note, "customer_note": customer_note},
        )

    async def list_line_items(self, order_id: int) -> list[dict[str, Any]]:
        """
        Lista las líneas de producto de un pedido.

        Args:
            order_id: ID del pedido.

        Returns:
            Lista de line_items del pedido.
        """
        order = await self.get(order_id)
        return order.get("line_items", [])
