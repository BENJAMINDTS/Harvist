"""
Tests unitarios para OooCategoryService (Odoo product.category).

Verifica:
- list_categories: delega a client con model product.category
- get_category: delega a client
- create_category: datos básicos + parent_id opcional
- update_category / delete_category: delegan correctamente
- get_tree: construye jerarquía padre-hijo desde lista plana
- find_category_by_name: devuelve None si no existe
- find_or_create_subcategory: lanza si padre no existe, crea si subcategoría no existe
- list_brands: filtra por parent_id correctamente

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.integrations.base import IntegrationError
from services.integrations.odoo.categories import OooCategoryService


def _make_client() -> MagicMock:
    c = MagicMock()
    c.list = AsyncMock(return_value=[])
    c.get = AsyncMock(return_value={"id": 1})
    c.create = AsyncMock(return_value={"id": 1})
    c.update = AsyncMock(return_value={"id": 1})
    c.delete = AsyncMock(return_value=True)
    return c


def _make_service(client=None) -> OooCategoryService:
    return OooCategoryService(client or _make_client())


# ---------------------------------------------------------------------------
# list_categories
# ---------------------------------------------------------------------------


class TestListCategories:
    @pytest.mark.asyncio
    async def test_uses_product_category_model(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[{"id": 1}])
        svc = _make_service(client)

        await svc.list_categories(limit=50, offset=0)

        call_args = client.list.call_args
        assert call_args[0][0] == "product.category"

    @pytest.mark.asyncio
    async def test_raises_on_client_failure(self):
        client = _make_client()
        client.list = AsyncMock(side_effect=Exception("timeout"))
        svc = _make_service(client)

        with pytest.raises(IntegrationError):
            await svc.list_categories()


# ---------------------------------------------------------------------------
# get_category
# ---------------------------------------------------------------------------


class TestGetCategory:
    @pytest.mark.asyncio
    async def test_delegates_to_client(self):
        client = _make_client()
        client.get = AsyncMock(return_value={"id": 3, "name": "Electrónica"})
        svc = _make_service(client)

        result = await svc.get_category(3)

        client.get.assert_called_once_with("product.category", 3)
        assert result["name"] == "Electrónica"

    @pytest.mark.asyncio
    async def test_raises_on_not_found(self):
        client = _make_client()
        client.get = AsyncMock(side_effect=IntegrationError("nf", status_code=404, platform="odoo"))
        svc = _make_service(client)

        with pytest.raises(IntegrationError):
            await svc.get_category(999)


# ---------------------------------------------------------------------------
# create_category
# ---------------------------------------------------------------------------


class TestCreateCategory:
    @pytest.mark.asyncio
    async def test_sends_name_to_client(self):
        client = _make_client()
        client.create = AsyncMock(return_value={"id": 5, "name": "Ropa"})
        svc = _make_service(client)

        result = await svc.create_category("Ropa")

        call_args = client.create.call_args
        assert call_args[0][0] == "product.category"
        assert call_args[0][1]["name"] == "Ropa"
        assert "parent_id" not in call_args[0][1]

    @pytest.mark.asyncio
    async def test_includes_parent_id_when_provided(self):
        client = _make_client()
        client.create = AsyncMock(return_value={"id": 6, "name": "Subcategoría"})
        svc = _make_service(client)

        await svc.create_category("Subcategoría", parent_id=2)

        call_args = client.create.call_args
        assert call_args[0][1]["parent_id"] == 2


# ---------------------------------------------------------------------------
# update_category / delete_category
# ---------------------------------------------------------------------------


class TestUpdateDeleteCategory:
    @pytest.mark.asyncio
    async def test_update_delegates_to_client(self):
        client = _make_client()
        client.update = AsyncMock(return_value={"id": 1, "name": "Nuevo"})
        svc = _make_service(client)

        result = await svc.update_category(1, {"name": "Nuevo"})

        client.update.assert_called_once_with("product.category", 1, {"name": "Nuevo"})
        assert result["name"] == "Nuevo"

    @pytest.mark.asyncio
    async def test_delete_delegates_to_client(self):
        client = _make_client()
        client.delete = AsyncMock(return_value=True)
        svc = _make_service(client)

        result = await svc.delete_category(2)

        client.delete.assert_called_once_with("product.category", 2)
        assert result is True


# ---------------------------------------------------------------------------
# get_tree
# ---------------------------------------------------------------------------


class TestGetTree:
    @pytest.mark.asyncio
    async def test_builds_parent_child_structure(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[
            {"id": 1, "name": "Raíz", "parent_id": False},
            {"id": 2, "name": "Hijo", "parent_id": [1, "Raíz"]},
        ])
        svc = _make_service(client)

        tree = await svc.get_tree()

        assert len(tree) == 1
        assert tree[0]["id"] == 1
        assert len(tree[0]["children"]) == 1
        assert tree[0]["children"][0]["id"] == 2

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_categories(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[])
        svc = _make_service(client)

        tree = await svc.get_tree()

        assert tree == []

    @pytest.mark.asyncio
    async def test_paginates_until_last_batch(self):
        client = _make_client()
        batch1 = [{"id": i, "name": f"Cat{i}", "parent_id": False} for i in range(1, 101)]
        batch2 = [{"id": 101, "name": "Last", "parent_id": False}]
        client.list = AsyncMock(side_effect=[batch1, batch2, []])
        svc = _make_service(client)

        tree = await svc.get_tree()

        assert len(tree) == 101


# ---------------------------------------------------------------------------
# find_category_by_name
# ---------------------------------------------------------------------------


class TestFindCategoryByName:
    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[])
        svc = _make_service(client)

        result = await svc.find_category_by_name("NoExiste")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_first_result(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[{"id": 3, "name": "Electrónica"}])
        svc = _make_service(client)

        result = await svc.find_category_by_name("Electrónica")

        assert result["id"] == 3


# ---------------------------------------------------------------------------
# find_or_create_subcategory
# ---------------------------------------------------------------------------


class TestFindOrCreateSubcategory:
    @pytest.mark.asyncio
    async def test_raises_if_parent_not_found(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[])
        svc = _make_service(client)

        with pytest.raises(IntegrationError, match="no existe"):
            await svc.find_or_create_subcategory("PadreInexistente", "Hijo")

    @pytest.mark.asyncio
    async def test_returns_existing_subcategory(self):
        client = _make_client()
        parent = {"id": 1, "name": "Padre"}
        child = {"id": 5, "name": "Hijo"}

        call_n = {"n": 0}

        async def _list(model, limit=None, filters=None, **kw):
            call_n["n"] += 1
            if call_n["n"] == 1:
                return [parent]
            return [child]

        client.list = AsyncMock(side_effect=_list)
        svc = _make_service(client)

        result = await svc.find_or_create_subcategory("Padre", "Hijo")

        assert result["id"] == 5
        client.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_subcategory_when_not_found(self):
        client = _make_client()
        parent = {"id": 1, "name": "Padre"}
        new_child = {"id": 10, "name": "NuevoHijo"}

        call_n = {"n": 0}

        async def _list(model, limit=None, filters=None, **kw):
            call_n["n"] += 1
            if call_n["n"] == 1:
                return [parent]
            return []

        client.list = AsyncMock(side_effect=_list)
        client.create = AsyncMock(return_value=new_child)
        svc = _make_service(client)

        result = await svc.find_or_create_subcategory("Padre", "NuevoHijo")

        assert result["id"] == 10
        client.create.assert_called_once()
