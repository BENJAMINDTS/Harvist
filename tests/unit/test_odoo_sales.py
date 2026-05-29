"""
Tests unitarios para OdooSaleService.

Verifica:
- list_sales: usa model sale.order
- list_sales: filtra por state cuando se pasa
- get_sale / create_sale / delete_sale: delegan correctamente

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.integrations.base import IntegrationError
from services.integrations.odoo.sales import OdooSaleService


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


def _make_service(client=None) -> OdooSaleService:
    return OdooSaleService(client or _make_client())


class TestListSales:
    @pytest.mark.asyncio
    async def test_uses_sale_order_model(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list_sales()

        assert client.list.call_args[0][0] == "sale.order"

    @pytest.mark.asyncio
    async def test_adds_state_filter_when_provided(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list_sales(state="sale")

        domain = client.list.call_args[1]["filters"]["domain"]
        assert any("sale" in str(t) for t in domain)

    @pytest.mark.asyncio
    async def test_raises_on_failure(self):
        client = _make_client()
        client.list = AsyncMock(side_effect=Exception("err"))
        svc = _make_service(client)

        with pytest.raises(IntegrationError):
            await svc.list_sales()


class TestSaleCRUD:
    @pytest.mark.asyncio
    async def test_get_delegates(self):
        client = _make_client()
        client.get = AsyncMock(return_value={"id": 3, "name": "SO/001"})
        svc = _make_service(client)

        result = await svc.get_sale(3)
        assert result["name"] == "SO/001"

    @pytest.mark.asyncio
    async def test_create_delegates(self):
        client = _make_client()
        client.create = AsyncMock(return_value={"id": 10})
        svc = _make_service(client)

        result = await svc.create_sale({"partner_id": 1})
        assert client.create.call_args[0][0] == "sale.order"
        assert result["id"] == 10

    @pytest.mark.asyncio
    async def test_confirm_calls_action_confirm(self):
        client = _make_client()
        client._execute = AsyncMock(return_value=True)
        client.get = AsyncMock(return_value={"id": 5, "state": "sale"})
        svc = _make_service(client)

        result = await svc.confirm_sale(5)

        assert client._execute.call_count >= 1
        assert result["state"] == "sale"
