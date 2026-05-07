"""
Servicio de gestión de pedidos de venta en Odoo (sale.order).

Estados: draft (presupuesto) → sent → sale (confirmado) → done → cancel

:author: Carlitos6712
:version: 1.0.0
"""

from loguru import logger

from services.integrations.base import IntegrationClient, IntegrationError


class OdooSaleService:
    """
    Servicio de gestión de pedidos de venta en Odoo.

    :author: Carlitos6712
    """

    _FIELDS = [
        "id", "name", "partner_id", "date_order", "validity_date",
        "state", "amount_total", "currency_id", "order_line",
        "note", "user_id", "invoice_status",
    ]

    def __init__(self, client: IntegrationClient) -> None:
        """
        Args:
            client: cliente Odoo autenticado.
        """
        self._client = client

    async def list_sales(
        self,
        limit: int = 50,
        offset: int = 0,
        state: str | None = None,
    ) -> list[dict]:
        """
        Lista pedidos de venta con paginación.

        Args:
            limit:  máximo de resultados.
            offset: desplazamiento.
            state:  filtro por estado (draft|sent|sale|done|cancel).

        Returns:
            Lista de dicts de sale.order.

        Raises:
            IntegrationError: si Odoo falla.
        """
        domain: list = []
        if state:
            domain.append(("state", "=", state))
        try:
            return await self._client.list(
                "sale.order",
                limit=limit,
                offset=offset,
                filters={"domain": domain, "fields": self._FIELDS, "order": "date_order desc"},
            )
        except Exception as exc:
            logger.error("Error listando ventas Odoo", exc_info=exc)
            raise IntegrationError("Fallo listando pedidos de venta Odoo") from exc

    async def get_sale(self, sale_id: int) -> dict:
        """
        Obtiene un pedido de venta por ID.

        Args:
            sale_id: ID de sale.order.

        Returns:
            Dict con datos del pedido.

        Raises:
            IntegrationError: si no existe o falla.
        """
        try:
            return await self._client.get("sale.order", sale_id)
        except Exception as exc:
            logger.error("Error obteniendo venta Odoo", exc_info=exc, extra={"id": sale_id})
            raise IntegrationError(f"Pedido de venta Odoo {sale_id} no encontrado") from exc

    async def create_sale(self, data: dict) -> dict:
        """
        Crea un presupuesto de venta en Odoo.

        Args:
            data: datos del pedido (partner_id obligatorio).

        Returns:
            Pedido creado.

        Raises:
            IntegrationError: si falla.
        """
        try:
            result = await self._client.create("sale.order", data)
            logger.info("Venta Odoo creada", extra={"id": result.get("id")})
            return result
        except Exception as exc:
            logger.error("Error creando venta Odoo", exc_info=exc)
            raise IntegrationError("Fallo creando pedido de venta Odoo") from exc

    async def confirm_sale(self, sale_id: int) -> dict:
        """
        Confirma un presupuesto de venta (draft → sale).

        Args:
            sale_id: ID del pedido.

        Returns:
            Pedido confirmado.

        Raises:
            IntegrationError: si falla.
        """
        from services.integrations.odoo.client import OdooClient
        if not isinstance(self._client, OdooClient):
            raise IntegrationError("OdooClient requerido para confirmar ventas")
        try:
            await self._client._execute("sale.order", "action_confirm", [[sale_id]])
            logger.info("Venta Odoo confirmada", extra={"id": sale_id})
            return await self.get_sale(sale_id)
        except IntegrationError:
            raise
        except Exception as exc:
            logger.error("Error confirmando venta Odoo", exc_info=exc, extra={"id": sale_id})
            raise IntegrationError(f"Fallo confirmando venta Odoo {sale_id}") from exc

    async def cancel_sale(self, sale_id: int) -> dict:
        """
        Cancela un pedido de venta.

        Args:
            sale_id: ID del pedido.

        Returns:
            Pedido cancelado.

        Raises:
            IntegrationError: si falla.
        """
        from services.integrations.odoo.client import OdooClient
        if not isinstance(self._client, OdooClient):
            raise IntegrationError("OdooClient requerido para cancelar ventas")
        try:
            await self._client._execute("sale.order", "action_cancel", [[sale_id]])
            logger.info("Venta Odoo cancelada", extra={"id": sale_id})
            return await self.get_sale(sale_id)
        except IntegrationError:
            raise
        except Exception as exc:
            logger.error("Error cancelando venta Odoo", exc_info=exc, extra={"id": sale_id})
            raise IntegrationError(f"Fallo cancelando venta Odoo {sale_id}") from exc

    async def count_sales(self, state: str | None = None) -> int:
        """
        Cuenta pedidos de venta.

        Args:
            state: filtro por estado (opcional).

        Returns:
            Número de pedidos.
        """
        from services.integrations.odoo.client import OdooClient
        if not isinstance(self._client, OdooClient):
            return 0
        domain: list = []
        if state:
            domain.append(("state", "=", state))
        return await self._client.search_count("sale.order", domain)
