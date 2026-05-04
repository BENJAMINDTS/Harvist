"""
Tests unitarios para DolibarrCategoryService.

:author: Carlitos6712
:version: 1.0.0
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.integrations.dolibarr.categories import DolibarrCategoryService


@pytest.fixture
def mock_client():
    """Mock del DolibarrClient."""
    return AsyncMock()


@pytest.fixture
def category_service(mock_client):
    """Instancia del servicio con cliente mockeado."""
    return DolibarrCategoryService(mock_client)


class TestListCategories:
    """Tests para list_categories."""

    @pytest.mark.asyncio
    async def test_passes_type_param_to_client(self, category_service, mock_client):
        """Verifica que pasa el parámetro type al cliente."""
        mock_client.list.return_value = []

        await category_service.list_categories(type="product", limit=50, offset=0)

        mock_client.list.assert_called_once()
        call_args = mock_client.list.call_args
        assert call_args.kwargs["filters"]["type"] == "product"

    @pytest.mark.asyncio
    async def test_passes_pagination_to_client(self, category_service, mock_client):
        """Verifica que pasa limit y offset."""
        mock_client.list.return_value = []

        await category_service.list_categories(type="product", limit=100, offset=50)

        call_args = mock_client.list.call_args
        assert call_args.kwargs["limit"] == 100
        assert call_args.kwargs["offset"] == 50


class TestGetCategory:
    """Tests para get_category."""

    @pytest.mark.asyncio
    async def test_delegates_to_client(self, category_service, mock_client):
        """Verifica que delega al cliente."""
        expected = {"id": 1, "label": "Electrónica"}
        mock_client.get.return_value = expected

        result = await category_service.get_category(1)

        assert result == expected
        mock_client.get.assert_called_once_with("categories", 1)


class TestGetTree:
    """Tests para get_tree."""

    @pytest.mark.asyncio
    async def test_returns_nested_parent_child_structure(self, category_service, mock_client):
        """Verifica que retorna estructura padre-hijo anidada."""
        categories = [
            {"id": 1, "label": "Raíz", "fk_parent": None},
            {"id": 2, "label": "Hijo 1", "fk_parent": 1},
            {"id": 3, "label": "Hijo 2", "fk_parent": 1},
        ]
        mock_client.list.return_value = categories

        tree = await category_service.get_tree(type="product")

        assert len(tree) == 1
        assert tree[0]["id"] == 1
        assert len(tree[0]["children"]) == 2

    @pytest.mark.asyncio
    async def test_handles_categories_with_no_parent(self, category_service, mock_client):
        """Verifica que maneja categorías sin padre (raíces)."""
        categories = [
            {"id": 1, "label": "Raíz 1", "fk_parent": None},
            {"id": 2, "label": "Raíz 2", "fk_parent": 0},
        ]
        mock_client.list.return_value = categories

        tree = await category_service.get_tree(type="product")

        assert len(tree) == 2

    @pytest.mark.asyncio
    async def test_paginates_until_all_categories_fetched(self, category_service, mock_client):
        """Verifica que pagina hasta obtener todas las categorías."""
        batch1 = [{"id": i, "label": f"Cat {i}", "fk_parent": None} for i in range(1, 51)]
        batch2 = [{"id": i, "label": f"Cat {i}", "fk_parent": None} for i in range(51, 101)]
        batch3 = [{"id": 101, "label": "Cat 101", "fk_parent": None}]

        mock_client.list.side_effect = [batch1, batch2, batch3]

        tree = await category_service.get_tree(type="product")

        assert len(tree) == 101
        assert mock_client.list.call_count == 3

    @pytest.mark.asyncio
    async def test_handles_empty_category_list(self, category_service, mock_client):
        """Verifica que maneja lista vacía."""
        mock_client.list.return_value = []

        tree = await category_service.get_tree(type="product")

        assert tree == []


class TestCreateCategory:
    """Tests para create_category."""

    @pytest.mark.asyncio
    async def test_sends_correct_fields_to_dolibarr(self, category_service, mock_client):
        """Verifica que envía campos correctos."""
        mock_client.create.return_value = {"id": 1, "label": "Nueva"}

        await category_service.create_category(
            label="Nueva",
            type="product",
            description="Descripción",
        )

        call_args = mock_client.create.call_args
        data = call_args.args[1]
        assert data["label"] == "Nueva"
        assert data["type"] == "product"
        assert data["description"] == "Descripción"

    @pytest.mark.asyncio
    async def test_maps_parent_id_to_fk_parent(self, category_service, mock_client):
        """Verifica que mapea parent_id a fk_parent."""
        mock_client.create.return_value = {"id": 2, "label": "Hijo"}

        await category_service.create_category(
            label="Hijo",
            type="product",
            parent_id=1,
        )

        call_args = mock_client.create.call_args
        data = call_args.args[1]
        assert data["fk_parent"] == 1
        assert "parent_id" not in data

    @pytest.mark.asyncio
    async def test_omits_parent_id_when_none(self, category_service, mock_client):
        """Verifica que omite fk_parent cuando parent_id es None."""
        mock_client.create.return_value = {"id": 1, "label": "Raíz"}

        await category_service.create_category(
            label="Raíz",
            type="product",
            parent_id=None,
        )

        call_args = mock_client.create.call_args
        data = call_args.args[1]
        assert "fk_parent" not in data


class TestUpdateCategory:
    """Tests para update_category."""

    @pytest.mark.asyncio
    async def test_delegates_to_client(self, category_service, mock_client):
        """Verifica que delega al cliente."""
        data = {"label": "Actualizado"}
        mock_client.update.return_value = {"id": 1, "label": "Actualizado"}

        result = await category_service.update_category(1, data)

        assert result["label"] == "Actualizado"
        mock_client.update.assert_called_once_with("categories", 1, data)


class TestDeleteCategory:
    """Tests para delete_category."""

    @pytest.mark.asyncio
    async def test_delegates_to_client(self, category_service, mock_client):
        """Verifica que delega al cliente."""
        mock_client.delete.return_value = True

        result = await category_service.delete_category(1)

        assert result is True
        mock_client.delete.assert_called_once_with("categories", 1)


class TestAssignProduct:
    """Tests para assign_product."""

    @pytest.mark.asyncio
    async def test_calls_correct_endpoint(self, category_service, mock_client):
        """Verifica que llama endpoint correcto."""
        mock_client.create.return_value = {"success": True}

        await category_service.assign_product(category_id=1, product_id=10)

        call_args = mock_client.create.call_args
        assert call_args.args[0] == "categories/1/objects"
        assert call_args.args[1] == {"type": "product", "id": 10}

    @pytest.mark.asyncio
    async def test_returns_true_on_success(self, category_service, mock_client):
        """Verifica que retorna True en éxito."""
        mock_client.create.return_value = {"success": True}

        result = await category_service.assign_product(1, 10)

        assert result is True


class TestRemoveProduct:
    """Tests para remove_product."""

    @pytest.mark.asyncio
    async def test_calls_correct_endpoint_with_product_type(self, category_service, mock_client):
        """Verifica que llama endpoint correcto con type=product."""
        mock_client.delete.return_value = True

        await category_service.remove_product(category_id=1, product_id=10)

        call_args = mock_client.delete.call_args
        assert call_args.args[0] == "categories/1/objects/10"


class TestListProductsInCategory:
    """Tests para list_products_in_category."""

    @pytest.mark.asyncio
    async def test_uses_objects_endpoint(self, category_service, mock_client):
        """Verifica que usa endpoint de objetos."""
        mock_client.list.return_value = []

        await category_service.list_products_in_category(category_id=1)

        call_args = mock_client.list.call_args
        assert call_args.args[0] == "categories/1/objects"

    @pytest.mark.asyncio
    async def test_filters_by_product_type(self, category_service, mock_client):
        """Verifica que filtra por type=product."""
        mock_client.list.return_value = []

        await category_service.list_products_in_category(category_id=1)

        call_args = mock_client.list.call_args
        assert call_args.kwargs["filters"]["type"] == "product"
