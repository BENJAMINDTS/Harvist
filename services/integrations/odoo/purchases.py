"""
Servicio de gestión de pedidos de compra en Odoo (purchase.order).

Estados: draft → sent → purchase (confirmado) → done → cancel

:author: Carlitos6712
:version: 1.0.0
"""

from loguru import logger

from services.integrations.base import IntegrationClient, IntegrationError


class OooPurchaseService:
    """
    Servicio de gestión de pedidos de compra en Odoo.

    :author: Carlitos6712
    """

    _FIELDS = [
        "id", "name", "partner_id", "date_order", "date_approve",
        "state", "amount_total", "currency_id", "order_line",
        "notes", "user_id",
    ]

    def __init__(self, client: IntegrationClient) -> None:
        """
        Args:
            client: cliente Odoo autenticado.
        """
        self._client = client

    async def list_purchases(
        self,
        limit: int = 50,
        offset: int = 0,
        state: str | None = None,
    ) -> list[dict]:
        """
        Lista pedidos de compra con paginación.

        Args:
            limit:  máximo de resultados.
            offset: desplazamiento.
            state:  filtro por estado (draft|sent|purchase|done|cancel).

        Returns:
            Lista de dicts de purchase.order.

        Raises:
            IntegrationError: si Odoo falla.
        """
        domain: list = []
        if state:
            domain.append(("state", "=", state))
        try:
            return await self._client.list(
                "purchase.order",
                limit=limit,
                offset=offset,
                filters={"domain": domain, "fields": self._FIELDS, "order": "date_order desc"},
            )
        except Exception as exc:
            logger.error("Error listando compras Odoo", exc_info=exc)
            raise IntegrationError("Fallo listando pedidos de compra Odoo") from exc

    async def get_purchase(self, purchase_id: int) -> dict:
        """
        Obtiene un pedido de compra por ID.

        Args:
            purchase_id: ID de purchase.order.

        Returns:
            Dict con datos del pedido.

        Raises:
            IntegrationError: si no existe o falla.
        """
        try:
            return await self._client.get("purchase.order", purchase_id)
        except Exception as exc:
            logger.error("Error obteniendo compra Odoo", exc_info=exc, extra={"id": purchase_id})
            raise IntegrationError(f"Pedido de compra Odoo {purchase_id} no encontrado") from exc

    async def create_purchase(self, data: dict) -> dict:
        """
        Crea un pedido de compra en borrador.

        Args:
            data: datos del pedido (partner_id obligatorio).

        Returns:
            Pedido creado.

        Raises:
            IntegrationError: si falla.
        """
        try:
            result = await self._client.create("purchase.order", data)
            logger.info("Compra Odoo creada", extra={"id": result.get("id")})
            return result
        except Exception as exc:
            logger.error("Error creando compra Odoo", exc_info=exc)
            raise IntegrationError("Fallo creando pedido de compra Odoo") from exc

    async def confirm_purchase(self, purchase_id: int) -> dict:
        """
        Confirma un pedido de compra (draft → purchase).

        Args:
            purchase_id: ID del pedido.

        Returns:
            Pedido confirmado.

        Raises:
            IntegrationError: si falla.
        """
        from services.integrations.odoo.client import OdooClient
        if not isinstance(self._client, OdooClient):
            raise IntegrationError("OdooClient requerido para confirmar pedidos")
        try:
            await self._client._execute("purchase.order", "button_confirm", [[purchase_id]])
            logger.info("Compra Odoo confirmada", extra={"id": purchase_id})
            return await self.get_purchase(purchase_id)
        except IntegrationError:
            raise
        except Exception as exc:
            logger.error("Error confirmando compra Odoo", exc_info=exc, extra={"id": purchase_id})
            raise IntegrationError(f"Fallo confirmando compra Odoo {purchase_id}") from exc

    async def cancel_purchase(self, purchase_id: int) -> dict:
        """
        Cancela un pedido de compra.

        Args:
            purchase_id: ID del pedido.

        Returns:
            Pedido cancelado.

        Raises:
            IntegrationError: si falla.
        """
        from services.integrations.odoo.client import OdooClient
        if not isinstance(self._client, OdooClient):
            raise IntegrationError("OdooClient requerido para cancelar pedidos")
        try:
            await self._client._execute("purchase.order", "button_cancel", [[purchase_id]])
            logger.info("Compra Odoo cancelada", extra={"id": purchase_id})
            return await self.get_purchase(purchase_id)
        except IntegrationError:
            raise
        except Exception as exc:
            logger.error("Error cancelando compra Odoo", exc_info=exc, extra={"id": purchase_id})
            raise IntegrationError(f"Fallo cancelando compra Odoo {purchase_id}") from exc

    async def count_purchases(self, state: str | None = None) -> int:
        """
        Cuenta pedidos de compra.

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
        return await self._client.search_count("purchase.order", domain)
