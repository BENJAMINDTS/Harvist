"""
Servicio de gestión de facturas en Odoo (account.move).

Tipos:
  out_invoice  → Factura de venta (cliente)
  in_invoice   → Factura de compra (proveedor)
  out_refund   → Nota de crédito cliente
  in_refund    → Nota de crédito proveedor

Estados:
  draft  → Borrador
  posted → Validada
  cancel → Cancelada

:author: Carlitos6712
:version: 1.0.0
"""

from typing import Literal

from loguru import logger

from services.integrations.base import IntegrationClient, IntegrationError

InvoiceType = Literal["customer", "supplier"]
_MOVE_TYPE: dict[str, str] = {
    "customer": "out_invoice",
    "supplier": "in_invoice",
}


class OdooInvoiceService:
    """
    Servicio de gestión de facturas en Odoo.

    :author: Carlitos6712
    """

    _FIELDS = [
        "id", "name", "partner_id", "invoice_date", "invoice_date_due",
        "move_type", "state", "amount_untaxed", "amount_tax", "amount_total",
        "amount_residual", "currency_id", "invoice_line_ids", "payment_state",
    ]

    def __init__(self, client: IntegrationClient) -> None:
        """
        Args:
            client: cliente Odoo autenticado.
        """
        self._client = client

    async def list_invoices(
        self,
        type: InvoiceType = "customer",
        limit: int = 50,
        offset: int = 0,
        state: str | None = None,
        partner_id: int | None = None,
    ) -> list[dict]:
        """
        Lista facturas por tipo, estado y partner.

        Args:
            type:       "customer" o "supplier".
            limit:      máximo de resultados.
            offset:     desplazamiento.
            state:      filtro por estado (draft|posted|cancel).
            partner_id: filtro por ID de partner.

        Returns:
            Lista de dicts de account.move.

        Raises:
            IntegrationError: si Odoo falla.
        """
        move_type = _MOVE_TYPE[type]
        domain: list = [("move_type", "=", move_type)]
        if state:
            domain.append(("state", "=", state))
        if partner_id is not None:
            domain.append(("partner_id", "=", partner_id))
        try:
            return await self._client.list(
                "account.move",
                limit=limit,
                offset=offset,
                filters={"domain": domain, "fields": self._FIELDS, "order": "invoice_date desc"},
            )
        except Exception as exc:
            logger.error("Error listando facturas Odoo", exc_info=exc, extra={"type": type})
            raise IntegrationError(f"Fallo listando facturas Odoo ({type})") from exc

    async def get_invoice(self, invoice_id: int) -> dict:
        """
        Obtiene una factura por ID.

        Args:
            invoice_id: ID de account.move.

        Returns:
            Dict con datos de la factura.

        Raises:
            IntegrationError: si no existe o falla.
        """
        try:
            return await self._client.get("account.move", invoice_id)
        except Exception as exc:
            logger.error("Error obteniendo factura Odoo", exc_info=exc, extra={"id": invoice_id})
            raise IntegrationError(f"Factura Odoo {invoice_id} no encontrada") from exc

    async def create_invoice(self, data: dict, type: InvoiceType = "customer") -> dict:
        """
        Crea una factura en borrador.

        Args:
            data: datos de la factura (partner_id obligatorio).
            type: "customer" o "supplier".

        Returns:
            Factura creada.

        Raises:
            IntegrationError: si falla.
        """
        data.setdefault("move_type", _MOVE_TYPE[type])
        try:
            result = await self._client.create("account.move", data)
            logger.info("Factura Odoo creada", extra={"id": result.get("id"), "type": type})
            return result
        except Exception as exc:
            logger.error("Error creando factura Odoo", exc_info=exc, extra={"type": type})
            raise IntegrationError(f"Fallo creando factura Odoo ({type})") from exc

    async def validate_invoice(self, invoice_id: int) -> dict:
        """
        Valida (publica) una factura en borrador.

        Args:
            invoice_id: ID de la factura.

        Returns:
            Factura validada.

        Raises:
            IntegrationError: si falla.
        """
        from services.integrations.odoo.client import OdooClient
        if not isinstance(self._client, OdooClient):
            raise IntegrationError("OdooClient requerido para validar facturas")
        try:
            await self._client._execute("account.move", "action_post", [[invoice_id]])
            logger.info("Factura Odoo validada", extra={"id": invoice_id})
            return await self.get_invoice(invoice_id)
        except IntegrationError:
            raise
        except Exception as exc:
            logger.error("Error validando factura Odoo", exc_info=exc, extra={"id": invoice_id})
            raise IntegrationError(f"Fallo validando factura Odoo {invoice_id}") from exc

    async def cancel_invoice(self, invoice_id: int) -> dict:
        """
        Cancela una factura.

        Args:
            invoice_id: ID de la factura.

        Returns:
            Factura cancelada.

        Raises:
            IntegrationError: si falla.
        """
        from services.integrations.odoo.client import OdooClient
        if not isinstance(self._client, OdooClient):
            raise IntegrationError("OdooClient requerido para cancelar facturas")
        try:
            await self._client._execute("account.move", "button_cancel", [[invoice_id]])
            logger.info("Factura Odoo cancelada", extra={"id": invoice_id})
            return await self.get_invoice(invoice_id)
        except IntegrationError:
            raise
        except Exception as exc:
            logger.error("Error cancelando factura Odoo", exc_info=exc, extra={"id": invoice_id})
            raise IntegrationError(f"Fallo cancelando factura Odoo {invoice_id}") from exc

    async def count_invoices(self, type: InvoiceType = "customer", state: str | None = None) -> int:
        """
        Cuenta facturas por tipo y estado.

        Args:
            type:  "customer" o "supplier".
            state: filtro por estado (opcional).

        Returns:
            Número de facturas.
        """
        from services.integrations.odoo.client import OdooClient
        if not isinstance(self._client, OdooClient):
            return 0
        domain: list = [("move_type", "=", _MOVE_TYPE[type])]
        if state:
            domain.append(("state", "=", state))
        return await self._client.search_count("account.move", domain)
