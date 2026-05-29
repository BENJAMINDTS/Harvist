"""
Tests unitarios para OooPurchaseService.

Verifica:
- list_purchases: usa model purchase.order
- list_purchases: filtra por state cuando se pasa
- get_purchase: delega a client
- create_purchase / delete_purchase: delegan correctamente

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.integrations.base import IntegrationError
from services.integrations.odoo.purchases import OooPurchaseService


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


def _make_service(client=None) -> OooPurchaseService:
    return OooPurchaseService(client or _make_client())


class TestListPurchases:
    @pytest.mark.asyncio
    async def test_uses_purchase_order_model(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list_purchases()

        assert client.list.call_args[0][0] == "purchase.order"

    @pytest.mark.asyncio
    async def test_adds_state_filter_when_provided(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list_purchases(state="purchase")

        domain = client.list.call_args[1]["filters"]["domain"]
        assert any("purchase" in str(t) for t in domain)

    @pytest.mark.asyncio
    async def test_raises_on_failure(self):
        client = _make_client()
        client.list = AsyncMock(side_effect=Exception("err"))
        svc = _make_service(client)

        with pytest.raises(IntegrationError):
            await svc.list_purchases()


class TestPurchaseCRUD:
    @pytest.mark.asyncio
    async def test_get_delegates(self):
        client = _make_client()
        client.get = AsyncMock(return_value={"id": 2, "name": "PO/001"})
        svc = _make_service(client)

        result = await svc.get_purchase(2)
        assert result["name"] == "PO/001"

    @pytest.mark.asyncio
    async def test_create_delegates(self):
        client = _make_client()
        client.create = AsyncMock(return_value={"id": 10})
        svc = _make_service(client)

        result = await svc.create_purchase({"partner_id": 1})
        assert client.create.call_args[0][0] == "purchase.order"
        assert result["id"] == 10

    @pytest.mark.asyncio
    async def test_confirm_calls_button_confirm(self):
        client = _make_client()
        client._execute = AsyncMock(return_value=True)
        client.get = AsyncMock(return_value={"id": 5, "state": "purchase"})
        svc = _make_service(client)

        result = await svc.confirm_purchase(5)

        assert client._execute.call_count >= 1
        assert result["state"] == "purchase"
