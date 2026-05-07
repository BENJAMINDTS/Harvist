"""
Servicio de gestión de inventario en Odoo (stock.quant).

:author: Carlitos6712
:version: 1.0.0
"""

from loguru import logger

from services.integrations.base import IntegrationClient, IntegrationError


class OdooInventoryService:
    """
    Servicio de consulta de stock en Odoo via stock.quant.

    :author: Carlitos6712
    """

    _QUANT_FIELDS = [
        "id", "product_id", "location_id", "quantity", "reserved_quantity",
        "inventory_quantity", "inventory_diff_quantity", "inventory_date",
        "lot_id", "package_id", "owner_id", "user_id", "in_date",
    ]

    def __init__(self, client: IntegrationClient) -> None:
        """
        Args:
            client: cliente Odoo autenticado.
        """
        self._client = client

    async def list_stock(
        self,
        limit: int = 50,
        offset: int = 0,
        product_id: int | None = None,
        location_id: int | None = None,
    ) -> list[dict]:
        """
        Lista registros de stock con paginación y filtros opcionales.

        Args:
            limit:       máximo de resultados.
            offset:      desplazamiento.
            product_id:  filtro por ID de producto (opcional).
            location_id: filtro por ID de ubicación (opcional).

        Returns:
            Lista de dicts de stock.quant.

        Raises:
            IntegrationError: si Odoo falla.
        """
        domain: list = [("location_id.usage", "=", "internal")]
        if product_id is not None:
            domain.append(("product_id", "=", product_id))
        if location_id is not None:
            domain.append(("location_id", "=", location_id))
        try:
            return await self._client.list(
                "stock.quant",
                limit=limit,
                offset=offset,
                filters={"domain": domain, "fields": self._QUANT_FIELDS},
            )
        except Exception as exc:
            logger.error("Error listando stock Odoo", exc_info=exc)
            raise IntegrationError("Fallo listando stock Odoo") from exc

    async def get_product_stock(self, product_id: int) -> list[dict]:
        """
        Obtiene todo el stock de un producto en todas las ubicaciones.

        Args:
            product_id: ID del producto (product.template).

        Returns:
            Lista de stock.quant por ubicación.

        Raises:
            IntegrationError: si falla.
        """
        domain: list = [
            ("product_id.product_tmpl_id", "=", product_id),
            ("location_id.usage", "=", "internal"),
        ]
        try:
            return await self._client.list(
                "stock.quant",
                limit=200,
                offset=0,
                filters={"domain": domain, "fields": self._QUANT_FIELDS},
            )
        except Exception as exc:
            logger.error("Error obteniendo stock de producto Odoo", exc_info=exc, extra={"product_id": product_id})
            raise IntegrationError(f"Fallo obteniendo stock del producto Odoo {product_id}") from exc

    async def list_locations(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """
        Lista ubicaciones de stock internas.

        Args:
            limit:  máximo de resultados.
            offset: desplazamiento.

        Returns:
            Lista de dicts de stock.location.

        Raises:
            IntegrationError: si falla.
        """
        domain: list = [("usage", "=", "internal"), ("active", "=", True)]
        try:
            return await self._client.list(
                "stock.location",
                limit=limit,
                offset=offset,
                filters={
                    "domain": domain,
                    "fields": ["id", "name", "complete_name", "usage", "active"],
                    "order": "complete_name asc",
                },
            )
        except Exception as exc:
            logger.error("Error listando ubicaciones Odoo", exc_info=exc)
            raise IntegrationError("Fallo listando ubicaciones Odoo") from exc

    async def update_quant(self, quant_id: int, data: dict) -> bool:
        """
        Actualiza campos de un stock.quant. Si incluye inventory_quantity,
        aplica el ajuste de inventario automáticamente.

        Args:
            quant_id: ID del stock.quant.
            data:     campos a actualizar.

        Returns:
            True si la operación tuvo éxito.

        Raises:
            IntegrationError: si Odoo falla.
        """
        from services.integrations.odoo.client import OdooClient
        if not isinstance(self._client, OdooClient):
            raise IntegrationError("Cliente Odoo no disponible")
        try:
            await self._client.update("stock.quant", quant_id, data)
            if "inventory_quantity" in data:
                await self._client._execute("stock.quant", "action_apply_inventory", [[quant_id]])
            logger.info("stock.quant actualizado", extra={"quant_id": quant_id})
            return True
        except Exception as exc:
            logger.error("Error actualizando stock.quant", exc_info=exc, extra={"quant_id": quant_id})
            raise IntegrationError(f"Fallo actualizando quant {quant_id}") from exc

    async def delete_quant(self, quant_id: int) -> bool:
        """
        Elimina un stock.quant. Solo funciona si el quant tiene cantidad 0
        o si el usuario tiene permisos de administración de inventario.

        Args:
            quant_id: ID del stock.quant.

        Returns:
            True si se eliminó.

        Raises:
            IntegrationError: si Odoo falla o no hay permisos.
        """
        from services.integrations.odoo.client import OdooClient
        if not isinstance(self._client, OdooClient):
            raise IntegrationError("Cliente Odoo no disponible")
        try:
            await self._client._execute("stock.quant", "unlink", [[quant_id]])
            logger.info("stock.quant eliminado", extra={"quant_id": quant_id})
            return True
        except Exception as exc:
            logger.error("Error eliminando stock.quant", exc_info=exc, extra={"quant_id": quant_id})
            raise IntegrationError(f"Fallo eliminando quant {quant_id}") from exc

    async def adjust_stock(self, quant_id: int, inventory_quantity: float) -> bool:
        """
        Ajusta la cantidad inventariada de un quant y aplica el ajuste.

        Args:
            quant_id:            ID del stock.quant.
            inventory_quantity:  nueva cantidad a fijar.

        Returns:
            True si el ajuste se aplicó correctamente.

        Raises:
            IntegrationError: si Odoo falla.
        """
        from services.integrations.odoo.client import OdooClient
        if not isinstance(self._client, OdooClient):
            raise IntegrationError("Cliente Odoo no disponible")
        try:
            await self._client.update("stock.quant", quant_id, {"inventory_quantity": inventory_quantity})
            await self._client._execute("stock.quant", "action_apply_inventory", [[quant_id]])
            logger.info("Stock ajustado en Odoo", extra={"quant_id": quant_id, "qty": inventory_quantity})
            return True
        except Exception as exc:
            logger.error("Error ajustando stock Odoo", exc_info=exc, extra={"quant_id": quant_id})
            raise IntegrationError(f"Fallo ajustando stock quant {quant_id}") from exc

    async def count_stock_lines(self) -> int:
        """
        Cuenta líneas de stock internas.

        Returns:
            Número de registros en stock.quant.
        """
        from services.integrations.odoo.client import OdooClient
        if not isinstance(self._client, OdooClient):
            return 0
        domain: list = [("location_id.usage", "=", "internal")]
        return await self._client.search_count("stock.quant", domain)
