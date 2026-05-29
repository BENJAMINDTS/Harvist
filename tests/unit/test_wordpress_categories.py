"""
Tests unitarios para WordPressCategoryService.

Verifica:
- list / get / create / update / delete: delegan a client
- find_by_name: retorna None si no existe
- find_or_create: crea si no existe, retorna existente si existe
- get_tree: construye jerarquía padre-hijo (parent=0 en raíz)

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.integrations.wordpress.categories import WordPressCategoryService


def _make_client() -> MagicMock:
    c = MagicMock()
    c.list = AsyncMock(return_value=[])
    c.get = AsyncMock(return_value={"id": 1})
    c.create = AsyncMock(return_value={"id": 1})
    c.update = AsyncMock(return_value={"id": 1})
    c.delete = AsyncMock(return_value=True)
    return c


def _make_service(client=None) -> WordPressCategoryService:
    return WordPressCategoryService(client or _make_client())


# ---------------------------------------------------------------------------
# CRUD basics
# ---------------------------------------------------------------------------


class TestCategoryServiceCRUD:
    @pytest.mark.asyncio
    async def test_list_uses_correct_resource(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list(limit=50)

        call_args = client.list.call_args
        assert call_args[0][0] == "products/categories"

    @pytest.mark.asyncio
    async def test_get_delegates(self):
        client = _make_client()
        client.get = AsyncMock(return_value={"id": 3, "name": "Ropa"})
        svc = _make_service(client)

        result = await svc.get(3)
        assert result["name"] == "Ropa"

    @pytest.mark.asyncio
    async def test_create_delegates(self):
        client = _make_client()
        client.create = AsyncMock(return_value={"id": 5, "name": "Nueva"})
        svc = _make_service(client)

        result = await svc.create({"name": "Nueva"})
        assert client.create.call_args[0][0] == "products/categories"
        assert result["id"] == 5

    @pytest.mark.asyncio
    async def test_update_delegates(self):
        client = _make_client()
        client.update = AsyncMock(return_value={"id": 5, "name": "Upd"})
        svc = _make_service(client)

        result = await svc.update(5, {"name": "Upd"})
        assert client.update.call_args[0][1] == 5

    @pytest.mark.asyncio
    async def test_delete_delegates(self):
        client = _make_client()
        svc = _make_service(client)

        result = await svc.delete(5)
        client.delete.assert_called_once()
        assert result is True


# ---------------------------------------------------------------------------
# find_or_create
# ---------------------------------------------------------------------------


class TestFindOrCreate:
    @pytest.mark.asyncio
    async def test_returns_existing_category(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[{"id": 7, "name": "Hogar", "parent": 0}])
        svc = _make_service(client)

        result = await svc.find_or_create("Hogar")

        client.create.assert_not_called()
        assert result["id"] == 7

    @pytest.mark.asyncio
    async def test_creates_when_not_found(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[])
        client.create = AsyncMock(return_value={"id": 8, "name": "Nueva Cat", "parent": 0})
        svc = _make_service(client)

        result = await svc.find_or_create("Nueva Cat")

        client.create.assert_called_once()
        assert result["id"] == 8

    @pytest.mark.asyncio
    async def test_passes_parent_when_provided(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[])
        client.create = AsyncMock(return_value={"id": 9, "name": "Sub", "parent": 3})
        svc = _make_service(client)

        await svc.find_or_create("Sub", parent_id=3)

        call_data = client.create.call_args[0][1]
        assert call_data["parent"] == 3


# ---------------------------------------------------------------------------
# tree
# ---------------------------------------------------------------------------


class TestTree:
    @pytest.mark.asyncio
    async def test_builds_tree_with_nested_children(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[
            {"id": 1, "name": "Raíz", "parent": 0},
            {"id": 2, "name": "Hijo", "parent": 1},
        ])
        svc = _make_service(client)

        result = await svc.tree()

        assert len(result) == 1
        assert result[0]["id"] == 1
        assert len(result[0]["children"]) == 1

    @pytest.mark.asyncio
    async def test_multiple_roots(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[
            {"id": 1, "name": "Cat 1", "parent": 0},
            {"id": 2, "name": "Cat 2", "parent": 0},
        ])
        svc = _make_service(client)

        result = await svc.tree()

        assert len(result) == 2
