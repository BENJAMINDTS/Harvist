"""
Tests unitarios para DolibarrInvoiceService.

:author: Carlitos6712
:version: 1.0.0
"""

from unittest.mock import AsyncMock

import pytest

from services.integrations.dolibarr.invoices import DolibarrInvoiceService


@pytest.fixture
def mock_client() -> AsyncMock:
    """Fixture con cliente Dolibarr mockeado."""
    return AsyncMock()


@pytest.fixture
def service(mock_client: AsyncMock) -> DolibarrInvoiceService:
    """Fixture con servicio de facturas."""
    return DolibarrInvoiceService(mock_client)


# ── ListInvoices ────────────────────────────────────────────────────────


class TestListInvoices:
    """Tests para list_invoices."""

    @pytest.mark.asyncio
    async def test_list_invoices_customer_uses_invoices_endpoint(
        self, service: DolibarrInvoiceService, mock_client: AsyncMock
    ) -> None:
        """Verifica que customer usa endpoint /invoices."""
        mock_client.get.return_value = [{"id": 1, "ref": "INV001"}]

        result = await service.list_invoices(type="customer")

        mock_client.get.assert_called_once()
        assert result == [{"id": 1, "ref": "INV001"}]

    @pytest.mark.asyncio
    async def test_list_invoices_supplier_uses_supplierinvoices_endpoint(
        self, service: DolibarrInvoiceService, mock_client: AsyncMock
    ) -> None:
        """Verifica que supplier usa endpoint /supplierinvoices."""
        mock_client.get.return_value = [{"id": 2, "ref": "SINV001"}]

        result = await service.list_invoices(type="supplier")

        mock_client.get.assert_called_once()
        assert result == [{"id": 2, "ref": "SINV001"}]


# ── GetInvoice ──────────────────────────────────────────────────────


class TestGetInvoice:
    """Tests para get_invoice."""

    @pytest.mark.asyncio
    async def test_get_invoice_returns_invoice_data(
        self, service: DolibarrInvoiceService, mock_client: AsyncMock
    ) -> None:
        """Verifica que get_invoice retorna datos de factura."""
        invoice_data = {"id": 1, "ref": "INV001", "status": 1}
        mock_client.get.return_value = invoice_data

        result = await service.get_invoice(1, type="customer")

        assert result == invoice_data


# ── CreateInvoice ──────────────────────────────────────────────────────


class TestCreateInvoice:
    """Tests para create_invoice."""

    @pytest.mark.asyncio
    async def test_create_invoice_posts_to_correct_endpoint_by_type(
        self, service: DolibarrInvoiceService, mock_client: AsyncMock
    ) -> None:
        """Verifica que create_invoice usa endpoint correcto por tipo."""
        invoice_data = {"socid": 42, "date": 1234567890}
        created = {"id": 1, "socid": 42}
        mock_client.post.return_value = created

        result = await service.create_invoice(invoice_data, type="customer")

        assert result == created


# ── AddInvoiceLine ──────────────────────────────────────────────────────


class TestAddInvoiceLine:
    """Tests para add_invoice_line."""

    @pytest.mark.asyncio
    async def test_add_invoice_line_posts_to_lines_subresource(
        self, service: DolibarrInvoiceService, mock_client: AsyncMock
    ) -> None:
        """Verifica que add_invoice_line usa subresource /lines."""
        line_data = {"desc": "Product", "qty": 1, "subprice": 100, "tva_tx": 0.21}
        created_line = {"id": 1, "desc": "Product"}
        mock_client.post.return_value = created_line

        result = await service.add_invoice_line(1, line_data, type="customer")

        assert result == created_line


# ── ValidateInvoice ────────────────────────────────────────────────────


class TestValidateInvoice:
    """Tests para validate_invoice."""

    @pytest.mark.asyncio
    async def test_validate_invoice_posts_to_validate_endpoint(
        self, service: DolibarrInvoiceService, mock_client: AsyncMock
    ) -> None:
        """Verifica que validate_invoice usa endpoint /validate."""
        mock_client.get.return_value = {"id": 1, "status": 0}
        validated = {"id": 1, "status": 1}
        mock_client.post.return_value = validated

        result = await service.validate_invoice(1, type="customer")

        assert result == validated

    @pytest.mark.asyncio
    async def test_validate_invoice_raises_ValueError_when_not_draft(
        self, service: DolibarrInvoiceService, mock_client: AsyncMock
    ) -> None:
        """Verifica que validate_invoice rechaza factura no en borrador."""
        mock_client.get.return_value = {"id": 1, "status": 2}

        with pytest.raises(ValueError):
            await service.validate_invoice(1, type="customer")


# ── SendByEmail ────────────────────────────────────────────────────────


class TestSendByEmail:
    """Tests para send_by_email."""

    @pytest.mark.asyncio
    async def test_send_by_email_posts_to_sendbymail_endpoint(
        self, service: DolibarrInvoiceService, mock_client: AsyncMock
    ) -> None:
        """Verifica que send_by_email usa endpoint /sendbymail."""
        mock_client.get.return_value = {"id": 1, "status": 1}
        mock_client.post.return_value = {}

        result = await service.send_by_email(
            1, "test@example.com", type="customer"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_send_by_email_raises_ValueError_when_invoice_not_validated(
        self, service: DolibarrInvoiceService, mock_client: AsyncMock
    ) -> None:
        """Verifica que send_by_email rechaza factura no validada."""
        mock_client.get.return_value = {"id": 1, "status": 0}

        with pytest.raises(ValueError):
            await service.send_by_email(1, "test@example.com", type="customer")


# ── MarkAsPaid ────────────────────────────────────────────────────────


class TestMarkAsPaid:
    """Tests para mark_as_paid."""

    @pytest.mark.asyncio
    async def test_mark_as_paid_posts_to_payments_endpoint(
        self, service: DolibarrInvoiceService, mock_client: AsyncMock
    ) -> None:
        """Verifica que mark_as_paid usa endpoint /payments."""
        payment = {"id": 1, "datepaye": 1234567890}
        mock_client.post.return_value = payment

        result = await service.mark_as_paid(
            1,
            payment_date=1234567890,
            payment_type_id=1,
            bank_account_id=42,
            type="customer",
        )

        assert result == payment

    @pytest.mark.asyncio
    async def test_mark_as_paid_customer_uses_invoices_payments_path(
        self, service: DolibarrInvoiceService, mock_client: AsyncMock
    ) -> None:
        """Verifica que customer usa path /invoices/{id}/payments."""
        mock_client.post.return_value = {}

        await service.mark_as_paid(
            1,
            payment_date=1234567890,
            payment_type_id=1,
            bank_account_id=42,
            type="customer",
        )

        call_args = mock_client.post.call_args
        assert "/invoices/1/payments" in str(call_args)

    @pytest.mark.asyncio
    async def test_mark_as_paid_supplier_uses_supplierinvoices_payments_path(
        self, service: DolibarrInvoiceService, mock_client: AsyncMock
    ) -> None:
        """Verifica que supplier usa path /supplierinvoices/{id}/payments."""
        mock_client.post.return_value = {}

        await service.mark_as_paid(
            1,
            payment_date=1234567890,
            payment_type_id=1,
            bank_account_id=42,
            type="supplier",
        )

        call_args = mock_client.post.call_args
        assert "/supplierinvoices/1/payments" in str(call_args)


# ── DeleteInvoice ──────────────────────────────────────────────────────


class TestDeleteInvoice:
    """Tests para delete_invoice."""

    @pytest.mark.asyncio
    async def test_delete_invoice_calls_delete_on_correct_resource(
        self, service: DolibarrInvoiceService, mock_client: AsyncMock
    ) -> None:
        """Verifica que delete_invoice usa endpoint correcto."""
        mock_client.get.return_value = {"id": 1, "status": 0}
        mock_client.delete.return_value = None

        result = await service.delete_invoice(1, type="customer")

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_invoice_raises_ValueError_when_not_draft(
        self, service: DolibarrInvoiceService, mock_client: AsyncMock
    ) -> None:
        """Verifica que delete_invoice rechaza factura no en borrador."""
        mock_client.get.return_value = {"id": 1, "status": 1}

        with pytest.raises(ValueError):
            await service.delete_invoice(1, type="customer")
