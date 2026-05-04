"""
Tests de integración para endpoints de categorías Dolibarr.

:author: Carlitos6712
:version: 1.0.0
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    """Cliente de prueba para la API."""
    return TestClient(app)


@pytest.fixture
def mock_settings_not_configured():
    """Mock para settings con Dolibarr no configurado."""
    with patch("api.v1.endpoints.dolibarr.get_settings") as mock:
        mock.return_value.dolibarr_configured = False
        yield mock


@pytest.fixture
def mock_category_service():
    """Mock para DolibarrCategoryService."""
    with patch("api.v1.endpoints.dolibarr.DolibarrCategoryService") as mock:
        yield mock


class TestNotConfigured:
    """Tests cuando Dolibarr no está configurado."""

    def test_list_returns_503_when_not_configured(self, client, mock_settings_not_configured):
        """Verifica que retorna 503 cuando no está configurado."""
        response = client.get("/api/v1/dolibarr/categories")
        assert response.status_code == 503

    def test_get_tree_returns_503_when_not_configured(self, client, mock_settings_not_configured):
        """Verifica que retorna 503 en /tree."""
        response = client.get("/api/v1/dolibarr/categories/tree")
        assert response.status_code == 503

    def test_get_by_id_returns_503_when_not_configured(self, client, mock_settings_not_configured):
        """Verifica que retorna 503 en GET /{id}."""
        response = client.get("/api/v1/dolibarr/categories/1")
        assert response.status_code == 503

    def test_create_returns_503_when_not_configured(self, client, mock_settings_not_configured):
        """Verifica que retorna 503 en POST."""
        response = client.post("/api/v1/dolibarr/categories?label=Test")
        assert response.status_code == 503

    def test_update_returns_503_when_not_configured(self, client, mock_settings_not_configured):
        """Verifica que retorna 503 en PUT."""
        response = client.put("/api/v1/dolibarr/categories/1", json={})
        assert response.status_code == 503

    def test_delete_returns_503_when_not_configured(self, client, mock_settings_not_configured):
        """Verifica que retorna 503 en DELETE."""
        response = client.delete("/api/v1/dolibarr/categories/1")
        assert response.status_code == 503

    def test_assign_product_returns_503_when_not_configured(self, client, mock_settings_not_configured):
        """Verifica que retorna 503 en POST /{id}/products/{pid}."""
        response = client.post("/api/v1/dolibarr/categories/1/products/10")
        assert response.status_code == 503

    def test_remove_product_returns_503_when_not_configured(self, client, mock_settings_not_configured):
        """Verifica que retorna 503 en DELETE /{id}/products/{pid}."""
        response = client.delete("/api/v1/dolibarr/categories/1/products/10")
        assert response.status_code == 503

    def test_list_products_returns_503_when_not_configured(self, client, mock_settings_not_configured):
        """Verifica que retorna 503 en GET /{id}/products."""
        response = client.get("/api/v1/dolibarr/categories/1/products")
        assert response.status_code == 503


class TestListCategories:
    """Tests para GET /dolibarr/categories."""

    def test_returns_paginated_response_with_type_filter(self, client):
        """Verifica que retorna respuesta paginada con filtro type."""
        with patch("api.v1.endpoints.dolibarr.DolibarrCategoryService") as mock_svc_class:
            mock_svc = AsyncMock()
            mock_svc_class.return_value = mock_svc
            mock_svc.list_categories.return_value = [
                {"id": 1, "label": "Cat 1"},
                {"id": 2, "label": "Cat 2"},
            ]

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                with patch("api.v1.endpoints.dolibarr.DolibarrClient"):
                    response = client.get("/api/v1/dolibarr/categories?type=product&limit=50")

            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert len(data["items"]) == 2


class TestGetTree:
    """Tests para GET /dolibarr/categories/tree."""

    def test_returns_nested_structure(self, client):
        """Verifica que retorna estructura anidada."""
        with patch("api.v1.endpoints.dolibarr.DolibarrCategoryService") as mock_svc_class:
            mock_svc = AsyncMock()
            mock_svc_class.return_value = mock_svc
            mock_svc.get_tree.return_value = [
                {
                    "id": 1,
                    "label": "Raíz",
                    "children": [
                        {"id": 2, "label": "Hijo", "children": []},
                    ],
                }
            ]

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                with patch("api.v1.endpoints.dolibarr.DolibarrClient"):
                    response = client.get("/api/v1/dolibarr/categories/tree")

            assert response.status_code == 200
            data = response.json()
            assert "data" in data
            assert len(data["data"]) == 1
            assert data["data"][0]["id"] == 1


class TestGetCategory:
    """Tests para GET /dolibarr/categories/{category_id}."""

    def test_returns_category_data(self, client):
        """Verifica que retorna datos de categoría."""
        with patch("api.v1.endpoints.dolibarr.DolibarrCategoryService") as mock_svc_class:
            mock_svc = AsyncMock()
            mock_svc_class.return_value = mock_svc
            mock_svc.get_category.return_value = {"id": 1, "label": "Test"}

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                with patch("api.v1.endpoints.dolibarr.DolibarrClient"):
                    response = client.get("/api/v1/dolibarr/categories/1")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["id"] == 1

    def test_returns_404_for_nonexistent(self, client):
        """Verifica que retorna 404 si no existe."""
        from services.integrations.base import IntegrationError

        with patch("api.v1.endpoints.dolibarr.DolibarrCategoryService") as mock_svc_class:
            mock_svc = AsyncMock()
            mock_svc_class.return_value = mock_svc
            mock_svc.get_category.side_effect = IntegrationError(
                "Not found", "dolibarr", 404
            )

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                with patch("api.v1.endpoints.dolibarr.DolibarrClient"):
                    response = client.get("/api/v1/dolibarr/categories/999")

            assert response.status_code == 404


class TestCreateCategory:
    """Tests para POST /dolibarr/categories."""

    def test_returns_201_on_success(self, client):
        """Verifica que retorna 201 en éxito."""
        with patch("api.v1.endpoints.dolibarr.DolibarrCategoryService") as mock_svc_class:
            mock_svc = AsyncMock()
            mock_svc_class.return_value = mock_svc
            mock_svc.create_category.return_value = {"id": 1, "label": "Nueva"}

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                with patch("api.v1.endpoints.dolibarr.DolibarrClient"):
                    response = client.post("/api/v1/dolibarr/categories?label=Nueva")

            assert response.status_code == 201
            data = response.json()
            assert data["data"]["label"] == "Nueva"


class TestUpdateCategory:
    """Tests para PUT /dolibarr/categories/{category_id}."""

    def test_returns_updated_data(self, client):
        """Verifica que retorna datos actualizados."""
        with patch("api.v1.endpoints.dolibarr.DolibarrCategoryService") as mock_svc_class:
            mock_svc = AsyncMock()
            mock_svc_class.return_value = mock_svc
            mock_svc.update_category.return_value = {"id": 1, "label": "Actualizado"}

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                with patch("api.v1.endpoints.dolibarr.DolibarrClient"):
                    response = client.put(
                        "/api/v1/dolibarr/categories/1",
                        json={"label": "Actualizado"},
                    )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["label"] == "Actualizado"


class TestDeleteCategory:
    """Tests para DELETE /dolibarr/categories/{category_id}."""

    def test_returns_success_message(self, client):
        """Verifica que retorna mensaje de éxito."""
        with patch("api.v1.endpoints.dolibarr.DolibarrCategoryService") as mock_svc_class:
            mock_svc = AsyncMock()
            mock_svc_class.return_value = mock_svc
            mock_svc.delete_category.return_value = True

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                with patch("api.v1.endpoints.dolibarr.DolibarrClient"):
                    response = client.delete("/api/v1/dolibarr/categories/1")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "eliminada" in data["message"].lower()


class TestAssignProduct:
    """Tests para POST /dolibarr/categories/{category_id}/products/{product_id}."""

    def test_returns_success_message(self, client):
        """Verifica que retorna mensaje de éxito."""
        with patch("api.v1.endpoints.dolibarr.DolibarrCategoryService") as mock_svc_class:
            mock_svc = AsyncMock()
            mock_svc_class.return_value = mock_svc
            mock_svc.assign_product.return_value = True

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                with patch("api.v1.endpoints.dolibarr.DolibarrClient"):
                    response = client.post("/api/v1/dolibarr/categories/1/products/10")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "asignado" in data["message"].lower()


class TestRemoveProduct:
    """Tests para DELETE /dolibarr/categories/{category_id}/products/{product_id}."""

    def test_returns_success_message(self, client):
        """Verifica que retorna mensaje de éxito."""
        with patch("api.v1.endpoints.dolibarr.DolibarrCategoryService") as mock_svc_class:
            mock_svc = AsyncMock()
            mock_svc_class.return_value = mock_svc
            mock_svc.remove_product.return_value = True

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                with patch("api.v1.endpoints.dolibarr.DolibarrClient"):
                    response = client.delete("/api/v1/dolibarr/categories/1/products/10")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "eliminado" in data["message"].lower()


class TestListProductsInCategory:
    """Tests para GET /dolibarr/categories/{category_id}/products."""

    def test_returns_paginated_response(self, client):
        """Verifica que retorna respuesta paginada."""
        with patch("api.v1.endpoints.dolibarr.DolibarrCategoryService") as mock_svc_class:
            mock_svc = AsyncMock()
            mock_svc_class.return_value = mock_svc
            mock_svc.list_products_in_category.return_value = [
                {"id": 1, "label": "Producto 1"},
            ]

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                with patch("api.v1.endpoints.dolibarr.DolibarrClient"):
                    response = client.get("/api/v1/dolibarr/categories/1/products")

            assert response.status_code == 200
            data = response.json()
            assert "items" in data
