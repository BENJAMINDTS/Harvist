"""
Módulo de gestión de pedidos de cliente y proveedor en Dolibarr.

Pedidos de cliente  → endpoint /orders
Pedidos de proveedor → endpoint /supplierorders

Estados pedido cliente:
  0 = Borrador      1 = Validado
  2 = Entregado     3 = Cancelado

Estados pedido proveedor:
  0 = Borrador      1 = Validado
  2 = Pedido        3 = Recibido parcialmente
  4 = Recibido      5 = Cancelado

:author: BenjaminDTS
:version: 1.0.0
"""

from typing import Literal

from services.integrations.dolibarr.client import DolibarrClient

OrderType = Literal["customer", "supplier"]


class DolibarrOrderService:
    """
    Servicio para gestionar pedidos de cliente y proveedor en Dolibarr.

    :author: BenjaminDTS
    """

    def __init__(self, client: DolibarrClient) -> None:
        """
        Inicializa el servicio.

        Args:
            client: cliente HTTP autenticado de Dolibarr.
        """
        self.client = client

    async def list_orders(
        self,
        type: OrderType = "customer",
        limit: int = 50,
        offset: int = 0,
        status: int | None = None,
        thirdparty_id: int | None = None,
    ) -> list[dict]:
        """
        Lista pedidos filtrando por tipo, estado y tercero.

        Args:
            type: "customer" para pedidos de cliente, "supplier" para pedidos de proveedor.
            limit: máximo de registros por página.
            offset: desplazamiento de paginación (0-based).
            status: filtro opcional por estado del pedido.
            thirdparty_id: filtro opcional por ID del tercero (cliente o proveedor).

        Returns:
            Lista de diccionarios con datos de los pedidos.
        """
        endpoint = "orders" if type == "customer" else "supplierorders"

        filters = None
        if status is not None or thirdparty_id is not None:
            sqlfilters = []
            if status is not None:
                sqlfilters.append(f"(status:{status})")
            if thirdparty_id is not None:
                sqlfilters.append(f"(socid:{thirdparty_id})")
            filters = " AND ".join(sqlfilters)

        return await self.client.list(endpoint, limit=limit, offset=offset, filters=filters)

    async def get_order(self, order_id: int, type: OrderType = "customer") -> dict:
        """
        Obtiene un pedido por ID.

        Args:
            order_id: identificador del pedido.
            type: "customer" o "supplier".

        Returns:
            Diccionario con datos del pedido.

        Raises:
            IntegrationError: si el pedido no existe (404).
        """
        endpoint = "orders" if type == "customer" else "supplierorders"
        return await self.client.get(endpoint, order_id)

    async def create_order(self, data: dict, type: OrderType = "customer") -> dict:
        """
        Crea un pedido.

        Campos mínimos en data:
          - socid: ID del tercero (cliente o proveedor)
          - date: timestamp del pedido

        Args:
            data: diccionario con los datos del pedido.
            type: "customer" o "supplier".

        Returns:
            Diccionario con el pedido creado (incluye ID asignado).

        Raises:
            IntegrationError: si la creación falla.
        """
        endpoint = "orders" if type == "customer" else "supplierorders"
        return await self.client.create(endpoint, data)

    async def add_order_line(
        self, order_id: int, line_data: dict, type: OrderType = "customer"
    ) -> dict:
        """
        Añade una línea a un pedido existente.

        Campos mínimos en line_data:
          - fk_product: ID del producto (o desc si no hay producto)
          - qty: cantidad
          - subprice: precio unitario

        Args:
            order_id: ID del pedido.
            line_data: diccionario con datos de la línea.
            type: "customer" o "supplier".

        Returns:
            Diccionario con la línea creada.

        Raises:
            IntegrationError: si la línea no se crea.
        """
        if type == "customer":
            endpoint = f"orders/{order_id}/lines"
        else:
            endpoint = f"supplierorders/{order_id}/lines"

        return await self.client.create(endpoint, line_data)

    async def update_order_status(
        self, order_id: int, status: int, type: OrderType = "customer"
    ) -> dict:
        """
        Cambia el estado de un pedido.

        Mapeo customer:
          1 → POST /orders/{id}/validate
          2 → POST /orders/{id}/close
          3 → POST /orders/{id}/cancel

        Mapeo supplier:
          1 → POST /supplierorders/{id}/validate
          4 → POST /supplierorders/{id}/reception
          5 → POST /supplierorders/{id}/cancel

        Args:
            order_id: ID del pedido.
            status: estado destino.
            type: "customer" o "supplier".

        Returns:
            Diccionario con el pedido actualizado.

        Raises:
            ValueError: si el status no es válido para el tipo de pedido.
            IntegrationError: si la operación falla en Dolibarr.
        """
        if type == "customer":
            if status == 1:
                action_endpoint = f"orders/{order_id}/validate"
            elif status == 2:
                action_endpoint = f"orders/{order_id}/close"
            elif status == 3:
                action_endpoint = f"orders/{order_id}/cancel"
            else:
                raise ValueError(f"Invalid status {status} for customer order")
        else:
            if status == 1:
                action_endpoint = f"supplierorders/{order_id}/validate"
            elif status == 4:
                action_endpoint = f"supplierorders/{order_id}/reception"
            elif status == 5:
                action_endpoint = f"supplierorders/{order_id}/cancel"
            else:
                raise ValueError(f"Invalid status {status} for supplier order")

        return await self.client.create(action_endpoint, {})

    async def delete_order(self, order_id: int, type: OrderType = "customer") -> bool:
        """
        Elimina un pedido en estado borrador.

        Args:
            order_id: ID del pedido.
            type: "customer" o "supplier".

        Returns:
            True si la eliminación fue exitosa.

        Raises:
            IntegrationError: si no se puede eliminar (ej: estado no es borrador).
        """
        endpoint = "orders" if type == "customer" else "supplierorders"
        return await self.client.delete(endpoint, order_id)
