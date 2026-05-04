"""
Módulo de gestión de facturas de cliente y proveedor en Dolibarr.

Facturas cliente  → endpoint /invoices
Facturas proveedor → endpoint /supplierinvoices

Estados factura cliente:
  0 = Borrador    1 = Validada (no pagada)
  2 = Pagada      3 = Abandonada (uncollectable)

Estados factura proveedor:
  0 = Borrador    1 = Aprobada
  2 = Pagada

:author: Carlitos6712
:version: 1.0.0
"""

from typing import Literal

from loguru import logger

from services.integrations.base import IntegrationClient, IntegrationError

InvoiceType = Literal["customer", "supplier"]


class DolibarrInvoiceService:
    """Servicio de gestión de facturas en Dolibarr."""

    def __init__(self, client: IntegrationClient) -> None:
        """
        Inicializa el servicio.

        Args:
            client: Cliente HTTP autenticado de Dolibarr.
        """
        self._client = client

    async def list_invoices(
        self,
        type: InvoiceType = "customer",
        limit: int = 50,
        offset: int = 0,
        status: int | None = None,
        thirdparty_id: int | None = None,
    ) -> list[dict]:
        """
        Lista facturas por tipo, estado y tercero.

        Args:
            type: "customer" o "supplier".
            limit: Máximo de resultados.
            offset: Desplazamiento.
            status: Filtro por estado (opcional).
            thirdparty_id: Filtro por ID tercero (opcional).

        Returns:
            Lista de facturas.

        Raises:
            IntegrationError: Si Dolibarr falla.
        """
        endpoint = "invoices" if type == "customer" else "supplierinvoices"
        filters = []
        if status is not None:
            filters.append(f"status={status}")
        if thirdparty_id is not None:
            filters.append(f"socid={thirdparty_id}")

        filter_str = " AND ".join(filters) if filters else ""
        params = {"limit": limit, "page": offset // limit if limit > 0 else 0}
        if filter_str:
            params["sqlfilters"] = filter_str

        try:
            response = await self._client.get(f"/{endpoint}", params=params)
            return response if isinstance(response, list) else [response]
        except Exception as exc:
            logger.error(
                "Error listando facturas",
                exc_info=exc,
                extra={"type": type, "status": status},
            )
            raise IntegrationError(f"Fallo listando facturas {type}") from exc

    async def get_invoice(
        self, invoice_id: int, type: InvoiceType = "customer"
    ) -> dict:
        """
        Obtiene una factura por ID.

        Args:
            invoice_id: ID de la factura.
            type: "customer" o "supplier".

        Returns:
            Datos de la factura.

        Raises:
            IntegrationError: Si no existe o falla.
        """
        endpoint = "invoices" if type == "customer" else "supplierinvoices"
        try:
            return await self._client.get(f"/{endpoint}/{invoice_id}")
        except Exception as exc:
            logger.error(
                "Error obteniendo factura",
                exc_info=exc,
                extra={"invoice_id": invoice_id, "type": type},
            )
            raise IntegrationError(
                f"404 not found: Factura {invoice_id} no encontrada"
            ) from exc

    async def create_invoice(
        self, data: dict, type: InvoiceType = "customer"
    ) -> dict:
        """
        Crea una factura en estado borrador.

        Args:
            data: Datos de la factura (socid, date mínimo).
            type: "customer" o "supplier".

        Returns:
            Factura creada.

        Raises:
            IntegrationError: Si falla la creación.
        """
        endpoint = "invoices" if type == "customer" else "supplierinvoices"
        try:
            response = await self._client.post(f"/{endpoint}", json=data)
            logger.info(
                "Factura creada",
                extra={"invoice_id": response.get("id"), "type": type},
            )
            return response
        except Exception as exc:
            logger.error(
                "Error creando factura",
                exc_info=exc,
                extra={"type": type},
            )
            raise IntegrationError(f"Fallo creando factura {type}") from exc

    async def add_invoice_line(
        self, invoice_id: int, line_data: dict, type: InvoiceType = "customer"
    ) -> dict:
        """
        Añade una línea a una factura en borrador.

        Args:
            invoice_id: ID de la factura.
            line_data: Datos de la línea (desc/fk_product, qty, subprice, tva_tx).
            type: "customer" o "supplier".

        Returns:
            Línea añadida.

        Raises:
            IntegrationError: Si falla.
        """
        endpoint = "invoices" if type == "customer" else "supplierinvoices"
        try:
            response = await self._client.post(
                f"/{endpoint}/{invoice_id}/lines", json=line_data
            )
            logger.info(
                "Línea de factura añadida",
                extra={"invoice_id": invoice_id, "type": type},
            )
            return response
        except Exception as exc:
            logger.error(
                "Error añadiendo línea a factura",
                exc_info=exc,
                extra={"invoice_id": invoice_id, "type": type},
            )
            raise IntegrationError(
                f"Fallo añadiendo línea a factura {invoice_id}"
            ) from exc

    async def validate_invoice(
        self, invoice_id: int, type: InvoiceType = "customer"
    ) -> dict:
        """
        Valida una factura (pasa de borrador a validada).

        Args:
            invoice_id: ID de la factura.
            type: "customer" o "supplier".

        Returns:
            Factura validada.

        Raises:
            ValueError: Si no está en borrador (estado 0).
            IntegrationError: Si falla la validación.
        """
        try:
            invoice = await self.get_invoice(invoice_id, type)
            if invoice.get("status") != 0:
                raise ValueError(
                    f"Factura {invoice_id} no está en borrador (estado {invoice.get('status')})"
                )
        except IntegrationError:
            raise
        except Exception as exc:
            raise ValueError(str(exc)) from exc

        endpoint = "invoices" if type == "customer" else "supplierinvoices"
        try:
            response = await self._client.post(f"/{endpoint}/{invoice_id}/validate")
            logger.info(
                "Factura validada",
                extra={"invoice_id": invoice_id, "type": type},
            )
            return response
        except Exception as exc:
            logger.error(
                "Error validando factura",
                exc_info=exc,
                extra={"invoice_id": invoice_id, "type": type},
            )
            raise IntegrationError(f"Fallo validando factura {invoice_id}") from exc

    async def send_by_email(
        self,
        invoice_id: int,
        email: str,
        type: InvoiceType = "customer",
        subject: str = "",
        message: str = "",
    ) -> bool:
        """
        Envía la factura por email desde Dolibarr.

        Args:
            invoice_id: ID de la factura.
            email: Email destinatario.
            type: "customer" o "supplier".
            subject: Asunto (opcional).
            message: Mensaje (opcional).

        Returns:
            True si Dolibarr acepta el envío.

        Raises:
            ValueError: Si la factura no está validada.
            IntegrationError: Si Dolibarr falla.
        """
        try:
            invoice = await self.get_invoice(invoice_id, type)
            if invoice.get("status", 0) < 1:
                raise ValueError(
                    f"Factura {invoice_id} no está validada (estado {invoice.get('status')})"
                )
        except IntegrationError:
            raise
        except Exception as exc:
            raise ValueError(str(exc)) from exc

        endpoint = "invoices" if type == "customer" else "supplierinvoices"
        body = {"sendto": email}
        if subject:
            body["subject"] = subject
        if message:
            body["message"] = message

        try:
            await self._client.post(f"/{endpoint}/{invoice_id}/sendbymail", json=body)
            logger.info(
                "Factura enviada",
                extra={"invoice_id": invoice_id, "email": email, "type": type},
            )
            return True
        except Exception as exc:
            logger.error(
                "Error enviando factura",
                exc_info=exc,
                extra={"invoice_id": invoice_id, "email": email},
            )
            raise IntegrationError(f"Fallo enviando factura {invoice_id}") from exc

    async def mark_as_paid(
        self,
        invoice_id: int,
        payment_date: int,
        payment_type_id: int,
        bank_account_id: int,
        amount: float | None = None,
        type: InvoiceType = "customer",
    ) -> dict:
        """
        Registra el pago de una factura.

        Args:
            invoice_id: ID de la factura.
            payment_date: Timestamp del pago.
            payment_type_id: ID del tipo de pago.
            bank_account_id: ID de la cuenta bancaria.
            amount: Monto pagado (opcional, usa total si no se indica).
            type: "customer" o "supplier".

        Returns:
            Registro de pago.

        Raises:
            IntegrationError: Si falla.
        """
        endpoint = "invoices" if type == "customer" else "supplierinvoices"
        body = {
            "datepaye": payment_date,
            "paiementid": payment_type_id,
            "accountid": bank_account_id,
        }
        if amount is not None:
            body["amount"] = amount

        try:
            response = await self._client.post(
                f"/{endpoint}/{invoice_id}/payments", json=body
            )
            logger.info(
                "Pago registrado",
                extra={"invoice_id": invoice_id, "amount": amount, "type": type},
            )
            return response
        except Exception as exc:
            logger.error(
                "Error registrando pago",
                exc_info=exc,
                extra={"invoice_id": invoice_id, "type": type},
            )
            raise IntegrationError(f"Fallo registrando pago de factura {invoice_id}") from exc

    async def delete_invoice(
        self, invoice_id: int, type: InvoiceType = "customer"
    ) -> bool:
        """
        Elimina una factura en borrador.

        Args:
            invoice_id: ID de la factura.
            type: "customer" o "supplier".

        Returns:
            True si se eliminó.

        Raises:
            ValueError: Si no está en borrador (estado 0).
            IntegrationError: Si falla.
        """
        try:
            invoice = await self.get_invoice(invoice_id, type)
            if invoice.get("status") != 0:
                raise ValueError(
                    f"Factura {invoice_id} no está en borrador (estado {invoice.get('status')})"
                )
        except IntegrationError:
            raise
        except Exception as exc:
            raise ValueError(str(exc)) from exc

        endpoint = "invoices" if type == "customer" else "supplierinvoices"
        try:
            await self._client.delete(f"/{endpoint}/{invoice_id}")
            logger.info(
                "Factura eliminada",
                extra={"invoice_id": invoice_id, "type": type},
            )
            return True
        except Exception as exc:
            logger.error(
                "Error eliminando factura",
                exc_info=exc,
                extra={"invoice_id": invoice_id, "type": type},
            )
            raise IntegrationError(f"Fallo eliminando factura {invoice_id}") from exc
