"""
Tests unitarios para WordPressOrderService.

Verifica:
- list: delega con filtros status/customer correctos
- get / update: delegan correctamente
- update_status: valida estado inválido, delega update en válido

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.integrations.base import IntegrationError
from services.integrations.wordpress.orders import WordPressOrderService


def _make_client() -> MagicMock:
    c = MagicMock()
    c.list = AsyncMock(return_value=[])
    c.get = AsyncMock(return_value={"id": 1})
    c.update = AsyncMock(return_value={"id": 1})
    return c


def _make_service(client=None) -> WordPressOrderService:
    return WordPressOrderService(client or _make_client())


class TestListOrders:
    @pytest.mark.asyncio
    async def test_uses_orders_resource(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list()

        assert client.list.call_args[0][0] == "orders"

    @pytest.mark.asyncio
    async def test_adds_customer_filter_when_provided(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list(customer=5)

        filters = client.list.call_args[1]["filters"]
        assert filters["customer"] == 5

    @pytest.mark.asyncio
    async def test_status_filter_always_present(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list(status="completed")

        filters = client.list.call_args[1]["filters"]
        assert filters["status"] == "completed"


class TestGetOrder:
    @pytest.mark.asyncio
    async def test_delegates_to_client(self):
        client = _make_client()
        client.get = AsyncMock(return_value={"id": 10, "status": "processing"})
        svc = _make_service(client)

        result = await svc.get(10)

        client.get.assert_called_once_with("orders", 10)
        assert result["id"] == 10


class TestUpdateStatus:
    @pytest.mark.asyncio
    async def test_raises_on_invalid_status(self):
        svc = _make_service()

        with pytest.raises((IntegrationError, ValueError)):
            await svc.update_status(1, "invalid_status")

    @pytest.mark.asyncio
    async def test_updates_with_valid_status(self):
        client = _make_client()
        client.update = AsyncMock(return_value={"id": 1, "status": "completed"})
        svc = _make_service(client)

        result = await svc.update_status(1, "completed")

        client.update.assert_called_once()
        call_data = client.update.call_args[0][2]
        assert call_data["status"] == "completed"
