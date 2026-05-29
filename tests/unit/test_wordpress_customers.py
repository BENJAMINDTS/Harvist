"""
Tests unitarios para WordPressCustomerService.

Verifica:
- list: delega con filtros role/search correctos
- get / create / update / delete: delegan correctamente

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.integrations.wordpress.customers import WordPressCustomerService


def _make_client() -> MagicMock:
    c = MagicMock()
    c.list = AsyncMock(return_value=[])
    c.get = AsyncMock(return_value={"id": 1})
    c.create = AsyncMock(return_value={"id": 1})
    c.update = AsyncMock(return_value={"id": 1})
    c.delete = AsyncMock(return_value=True)
    return c


def _make_service(client=None) -> WordPressCustomerService:
    return WordPressCustomerService(client or _make_client())


class TestListCustomers:
    @pytest.mark.asyncio
    async def test_uses_customers_resource(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list()

        assert client.list.call_args[0][0] == "customers"

    @pytest.mark.asyncio
    async def test_adds_role_filter(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list(role="subscriber")

        filters = client.list.call_args[1]["filters"]
        assert filters["role"] == "subscriber"

    @pytest.mark.asyncio
    async def test_adds_search_filter_when_provided(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list(search="john")

        filters = client.list.call_args[1]["filters"]
        assert "search" in filters


class TestCustomerCRUD:
    @pytest.mark.asyncio
    async def test_get_delegates(self):
        client = _make_client()
        client.get = AsyncMock(return_value={"id": 5, "email": "j@test.com"})
        svc = _make_service(client)

        result = await svc.get(5)
        assert result["email"] == "j@test.com"

    @pytest.mark.asyncio
    async def test_create_delegates(self):
        client = _make_client()
        client.create = AsyncMock(return_value={"id": 10})
        svc = _make_service(client)

        result = await svc.create({"email": "new@test.com"})
        assert client.create.call_args[0][0] == "customers"
        assert result["id"] == 10

    @pytest.mark.asyncio
    async def test_update_delegates(self):
        client = _make_client()
        client.update = AsyncMock(return_value={"id": 5})
        svc = _make_service(client)

        await svc.update(5, {"email": "upd@test.com"})
        assert client.update.call_args[0][1] == 5

    @pytest.mark.asyncio
    async def test_delete_delegates(self):
        client = _make_client()
        svc = _make_service(client)

        result = await svc.delete(3)
        client.delete.assert_called_once()
        assert result is True
