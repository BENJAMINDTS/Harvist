"""
Tests unitarios para OdooInvoiceService.

Verifica:
- list_invoices: usa model account.move, mapea type a move_type
- list_invoices: filtra por state cuando se pasa
- list_invoices: filtra por partner_id cuando se pasa
- get_invoice: delega a client
- create_invoice / delete_invoice: delegan correctamente

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.integrations.base import IntegrationError
from services.integrations.odoo.invoices import OdooInvoiceService


def _make_client() -> MagicMock:
    from services.integrations.odoo.client import OdooClient
    c = MagicMock(spec=OdooClient)
    c.list = AsyncMock(return_value=[])
    c.get = AsyncMock(return_value={"id": 1})
    c.create = AsyncMock(return_value={"id": 1})
    c.update = AsyncMock(return_value={"id": 1})
    c.delete = AsyncMock(return_value=True)
    c._execute = AsyncMock(return_value=True)
    return c


def _make_service(client=None) -> OdooInvoiceService:
    return OdooInvoiceService(client or _make_client())


# ---------------------------------------------------------------------------
# list_invoices
# ---------------------------------------------------------------------------


class TestListInvoices:
    @pytest.mark.asyncio
    async def test_uses_account_move_model(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list_invoices()

        call_args = client.list.call_args
        assert call_args[0][0] == "account.move"

    @pytest.mark.asyncio
    async def test_customer_type_maps_to_out_invoice(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list_invoices(type="customer")

        domain = client.list.call_args[1]["filters"]["domain"]
        assert any("out_invoice" in str(t) for t in domain)

    @pytest.mark.asyncio
    async def test_supplier_type_maps_to_in_invoice(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list_invoices(type="supplier")

        domain = client.list.call_args[1]["filters"]["domain"]
        assert any("in_invoice" in str(t) for t in domain)

    @pytest.mark.asyncio
    async def test_adds_state_filter_when_provided(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list_invoices(state="posted")

        domain = client.list.call_args[1]["filters"]["domain"]
        assert any("posted" in str(t) for t in domain)

    @pytest.mark.asyncio
    async def test_adds_partner_filter_when_provided(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list_invoices(partner_id=7)

        domain = client.list.call_args[1]["filters"]["domain"]
        assert any("partner_id" in str(t) for t in domain)

    @pytest.mark.asyncio
    async def test_raises_on_failure(self):
        client = _make_client()
        client.list = AsyncMock(side_effect=Exception("error"))
        svc = _make_service(client)

        with pytest.raises(IntegrationError):
            await svc.list_invoices()


# ---------------------------------------------------------------------------
# get / create / delete
# ---------------------------------------------------------------------------


class TestInvoiceCRUD:
    @pytest.mark.asyncio
    async def test_get_delegates(self):
        client = _make_client()
        client.get = AsyncMock(return_value={"id": 5, "name": "INV/001"})
        svc = _make_service(client)

        result = await svc.get_invoice(5)

        client.get.assert_called_once_with("account.move", 5)
        assert result["name"] == "INV/001"

    @pytest.mark.asyncio
    async def test_create_delegates(self):
        client = _make_client()
        client.create = AsyncMock(return_value={"id": 10})
        svc = _make_service(client)

        result = await svc.create_invoice({"partner_id": 1, "move_type": "out_invoice"})

        call_args = client.create.call_args
        assert call_args[0][0] == "account.move"
        assert result["id"] == 10

    @pytest.mark.asyncio
    async def test_validate_calls_action_post(self):
        client = _make_client()
        client._execute = AsyncMock(return_value=True)
        client.get = AsyncMock(return_value={"id": 3, "state": "posted"})
        svc = _make_service(client)

        result = await svc.validate_invoice(3)

        # _execute called with action_post
        assert client._execute.call_count >= 1
        assert result["state"] == "posted"
