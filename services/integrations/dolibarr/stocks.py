"""
Módulo de gestión de stock y almacenes en Dolibarr.

Tipos de movimiento de stock:
  0 = Entrada (recepción de mercancía)
  1 = Salida  (entrega, venta)
  2 = Corrección de inventario (positiva o negativa)
  3 = Transferencia entre almacenes

:author: BenjaminDTS
:version: 1.0.0
"""

from typing import Any, Literal

from loguru import logger

from services.integrations.base import IntegrationClient

StockMovementType = Literal[0, 1, 2, 3]


class DolibarrStockService:
    """
    Servicio para gestión de stock y almacenes en Dolibarr.

    :author: BenjaminDTS
    """

    def __init__(self, client: IntegrationClient) -> None:
        """
        Inicializa el servicio.

        Args:
            client: Cliente Dolibarr configurado.
        """
        self.client = client

    async def list_warehouses(
        self, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """
        Lista todos los almacenes de Dolibarr.

        Args:
            limit: Cantidad máxima (default 50).
            offset: Desplazamiento (default 0).

        Returns:
            Lista de almacenes.
        """
        logger.debug(f"Listing warehouses with limit={limit}, offset={offset}")
        return await self.client.list("warehouses", limit=limit, offset=offset)

    async def get_warehouse(self, warehouse_id: int) -> dict[str, Any]:
        """
        Obtiene un almacén por ID.

        Args:
            warehouse_id: ID del almacén.

        Returns:
            Diccionario con los datos del almacén.

        Raises:
            Exception: Si el almacén no existe.
        """
        logger.debug(f"Getting warehouse {warehouse_id}")
        return await self.client.get("warehouses", warehouse_id)

    async def get_product_stock(self, product_id: int) -> dict[str, Any]:
        """
        Obtiene el stock actual de un producto desglosado por almacén.

        Args:
            product_id: ID del producto.

        Returns:
            Diccionario con:
              - stock_total: float (suma de todos los almacenes)
              - warehouses: list de { warehouse_id, warehouse_label, qty }

        Raises:
            Exception: Si el producto no existe.
        """
        logger.debug(f"Getting stock for product {product_id}")
        response = await self.client.get("products", product_id)

        stock_info = response.get("stock", 0)
        warehouses_raw = response.get("warehouses", [])

        warehouses = [
            {
                "warehouse_id": w.get("id"),
                "warehouse_label": w.get("label"),
                "qty": w.get("qty", 0),
            }
            for w in warehouses_raw
        ]

        stock_total = sum(w["qty"] for w in warehouses)

        return {"stock_total": stock_total, "warehouses": warehouses}

    async def get_stock_for_products(
        self, product_ids: list[int]
    ) -> dict[int, dict[str, Any]]:
        """
        Obtiene el stock de múltiples productos de forma eficiente.

        Args:
            product_ids: Lista de IDs de productos.

        Returns:
            Diccionario { product_id: stock_info }.
        """
        logger.debug(f"Getting stock for {len(product_ids)} products")
        result = {}
        for product_id in product_ids:
            try:
                result[product_id] = await self.get_product_stock(product_id)
            except Exception as exc:
                logger.warning(
                    f"Could not fetch stock for product {product_id}",
                    extra={"product_id": product_id},
                    exc_info=exc,
                )
        return result

    async def add_stock_movement(
        self,
        product_id: int,
        warehouse_id: int,
        qty: float,
        movement_type: StockMovementType,
        label: str = "",
        price: float = 0.0,
    ) -> dict[str, Any]:
        """
        Registra un movimiento de stock.

        Args:
            product_id: ID del producto.
            warehouse_id: ID del almacén.
            qty: Cantidad (puede ser negativa para salidas).
            movement_type: Tipo de movimiento (0-3).
            label: Etiqueta / descripción (opcional).
            price: Precio unitario (opcional).

        Returns:
            Diccionario del movimiento creado.

        Raises:
            ValueError: Si qty es 0 o movement_type es inválido.
            Exception: Si la API de Dolibarr falla.
        """
        if qty == 0:
            raise ValueError("qty cannot be zero")
        if movement_type not in (0, 1, 2, 3):
            raise ValueError(
                f"movement_type must be 0, 1, 2, or 3, got {movement_type}"
            )

        data = {
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "qty": qty,
            "type": movement_type,
            "label": label,
            "price": price,
        }

        logger.info(
            "Creating stock movement",
            extra={
                "product_id": product_id,
                "warehouse_id": warehouse_id,
                "qty": qty,
                "movement_type": movement_type,
            },
        )

        return await self.client.create("stockmovements", data)

    async def get_stock_movements(
        self,
        product_id: int | None = None,
        warehouse_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Lista movimientos de stock con filtros opcionales.

        Args:
            product_id: Filtrar por producto (opcional).
            warehouse_id: Filtrar por almacén (opcional).
            limit: Cantidad máxima (default 50).
            offset: Desplazamiento (default 0).

        Returns:
            Lista de movimientos.
        """
        filters = {}
        if product_id is not None:
            filters["fk_product"] = product_id
        if warehouse_id is not None:
            filters["fk_warehouse"] = warehouse_id

        logger.debug(
            f"Listing stock movements with filters={filters}, limit={limit}, offset={offset}"
        )

        return await self.client.list(
            "stockmovements", limit=limit, offset=offset, filters=filters
        )

    async def transfer_stock(
        self,
        product_id: int,
        from_warehouse_id: int,
        to_warehouse_id: int,
        qty: float,
        label: str = "",
    ) -> dict[str, Any]:
        """
        Transfiere stock entre almacenes.

        Implementado como dos movimientos: salida del origen
        y entrada en el destino.

        Args:
            product_id: ID del producto.
            from_warehouse_id: ID del almacén de origen.
            to_warehouse_id: ID del almacén de destino.
            qty: Cantidad a transferir.
            label: Descripción (opcional).

        Returns:
            Diccionario con los dos movimientos creados.

        Raises:
            ValueError: Si warehouses son iguales o qty <= 0.
            Exception: Si la API de Dolibarr falla.
        """
        if from_warehouse_id == to_warehouse_id:
            raise ValueError(
                "from_warehouse_id and to_warehouse_id cannot be the same"
            )
        if qty <= 0:
            raise ValueError("qty must be greater than 0 for transfers")

        logger.info(
            "Transferring stock between warehouses",
            extra={
                "product_id": product_id,
                "from": from_warehouse_id,
                "to": to_warehouse_id,
                "qty": qty,
            },
        )

        # Salida del almacén origen (type=1: salida)
        out_movement = await self.add_stock_movement(
            product_id=product_id,
            warehouse_id=from_warehouse_id,
            qty=-qty,
            movement_type=1,
            label=f"Transfer out to warehouse {to_warehouse_id}: {label}",
        )

        # Entrada al almacén destino (type=0: entrada)
        in_movement = await self.add_stock_movement(
            product_id=product_id,
            warehouse_id=to_warehouse_id,
            qty=qty,
            movement_type=0,
            label=f"Transfer in from warehouse {from_warehouse_id}: {label}",
        )

        return {"out_movement": out_movement, "in_movement": in_movement}
