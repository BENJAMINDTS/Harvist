"""
Tests de integración para endpoints de terceros de Dolibarr.

:author: Carlitos6712
:version: 1.0.0
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from api.main import create_app
from services.integrations.base import IntegrationError


@pytest.fixture
def app():
    """FastAPI app para testing."""
    return create_app()


@pytest.fixture
def client(app):
    """Cliente HTTP para testing."""
    return TestClient(app)


class TestNotConfigured:
    """Tests para endpoints cuando Dolibarr no está configurado."""

    def test_list_returns_503_when_not_configured(self, client):
        """GET /dolibarr/thirdparties devuelve 503 si no configurado."""
        with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
            mock_settings.return_value.dolibarr_configured = False
            response = client.get("/api/v1/dolibarr/thirdparties")
            assert response.status_code == 503

    def test_search_returns_503_when_not_configured(self, client):
        """GET /dolibarr/thirdparties/search devuelve 503 si no configurado."""
        with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
            mock_settings.return_value.dolibarr_configured = False
            response = client.get("/api/v1/dolibarr/thirdparties/search?name=test")
            assert response.status_code == 503

    def test_get_returns_503_when_not_configured(self, client):
        """GET /dolibarr/thirdparties/{id} devuelve 503 si no configurado."""
        with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
            mock_settings.return_value.dolibarr_configured = False
            response = client.get("/api/v1/dolibarr/thirdparties/1")
            assert response.status_code == 503

    def test_create_returns_503_when_not_configured(self, client):
        """POST /dolibarr/thirdparties devuelve 503 si no configurado."""
        with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
            mock_settings.return_value.dolibarr_configured = False
            response = client.post("/api/v1/dolibarr/thirdparties", json={"name": "Test"})
            assert response.status_code == 503

    def test_update_returns_503_when_not_configured(self, client):
        """PUT /dolibarr/thirdparties/{id} devuelve 503 si no configurado."""
        with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
            mock_settings.return_value.dolibarr_configured = False
            response = client.put(
                "/api/v1/dolibarr/thirdparties/1", json={"name": "Updated"}
            )
            assert response.status_code == 503

    def test_delete_returns_503_when_not_configured(self, client):
        """DELETE /dolibarr/thirdparties/{id} devuelve 503 si no configurado."""
        with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
            mock_settings.return_value.dolibarr_configured = False
            response = client.delete("/api/v1/dolibarr/thirdparties/1")
            assert response.status_code == 503

    def test_get_invoices_returns_503_when_not_configured(self, client):
        """GET /dolibarr/thirdparties/{id}/invoices devuelve 503 si no configurado."""
        with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
            mock_settings.return_value.dolibarr_configured = False
            response = client.get("/api/v1/dolibarr/thirdparties/1/invoices")
            assert response.status_code == 503

    def test_get_orders_returns_503_when_not_configured(self, client):
        """GET /dolibarr/thirdparties/{id}/orders devuelve 503 si no configurado."""
        with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
            mock_settings.return_value.dolibarr_configured = False
            response = client.get("/api/v1/dolibarr/thirdparties/1/orders")
            assert response.status_code == 503


class TestListThirdparties:
    """Tests para listar terceros."""

    def test_list_all_sends_no_filter(self, client):
        """GET /dolibarr/thirdparties con mode=all no envía filtro."""
        with patch("api.v1.endpoints.dolibarr.DolibarrThirdpartyService") as MockService:
            mock_service_instance = AsyncMock()
            MockService.return_value = mock_service_instance
            mock_service_instance.list_thirdparties.return_value = [
                {"id": 1, "nom": "Empresa 1"}
            ]

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                response = client.get("/api/v1/dolibarr/thirdparties?mode=all")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert len(data["data"]["items"]) == 1

    def test_list_customers_filters_correctly(self, client):
        """GET /dolibarr/thirdparties con mode=customers filtra por clientes."""
        with patch("api.v1.endpoints.dolibarr.DolibarrThirdpartyService") as MockService:
            mock_service_instance = AsyncMock()
            MockService.return_value = mock_service_instance
            mock_service_instance.list_thirdparties.return_value = [
                {"id": 2, "nom": "Cliente A", "client": 1}
            ]

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                response = client.get("/api/v1/dolibarr/thirdparties?mode=customers")

            assert response.status_code == 200
            call_kwargs = mock_service_instance.list_thirdparties.call_args.kwargs
            assert call_kwargs.get("mode") == "customers"

    def test_list_suppliers_filters_correctly(self, client):
        """GET /dolibarr/thirdparties con mode=suppliers filtra por proveedores."""
        with patch("api.v1.endpoints.dolibarr.DolibarrThirdpartyService") as MockService:
            mock_service_instance = AsyncMock()
            MockService.return_value = mock_service_instance
            mock_service_instance.list_thirdparties.return_value = [
                {"id": 3, "nom": "Proveedor X", "supplier": 1}
            ]

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                response = client.get("/api/v1/dolibarr/thirdparties?mode=suppliers")

            assert response.status_code == 200
            call_kwargs = mock_service_instance.list_thirdparties.call_args.kwargs
            assert call_kwargs.get("mode") == "suppliers"


class TestSearchThirdparties:
    """Tests para búsqueda de terceros."""

    def test_search_returns_matching_thirdparties(self, client):
        """GET /dolibarr/thirdparties/search devuelve terceros coincidentes."""
        with patch("api.v1.endpoints.dolibarr.DolibarrThirdpartyService") as MockService:
            mock_service_instance = AsyncMock()
            MockService.return_value = mock_service_instance
            mock_service_instance.search_thirdparty.return_value = [
                {"id": 4, "nom": "Test Company"}
            ]

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                response = client.get("/api/v1/dolibarr/thirdparties/search?name=Test")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert len(data["data"]) == 1


class TestGetThirdparty:
    """Tests para obtener un tercero."""

    def test_get_returns_thirdparty_data(self, client):
        """GET /dolibarr/thirdparties/{id} devuelve los datos del tercero."""
        with patch("api.v1.endpoints.dolibarr.DolibarrThirdpartyService") as MockService:
            mock_service_instance = AsyncMock()
            MockService.return_value = mock_service_instance
            mock_service_instance.get_thirdparty.return_value = {
                "id": 5,
                "nom": "Empresa A",
                "client": 1,
            }

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                response = client.get("/api/v1/dolibarr/thirdparties/5")

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["id"] == 5

    def test_get_returns_404_for_nonexistent(self, client):
        """GET /dolibarr/thirdparties/{id} devuelve 404 si no existe."""
        with patch("api.v1.endpoints.dolibarr.DolibarrThirdpartyService") as MockService:
            mock_service_instance = AsyncMock()
            MockService.return_value = mock_service_instance
            mock_service_instance.get_thirdparty.side_effect = IntegrationError(
                "No encontrado", status_code=404
            )

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                response = client.get("/api/v1/dolibarr/thirdparties/999")

            assert response.status_code == 404


class TestCreateThirdparty:
    """Tests para crear un tercero."""

    def test_create_customer_sets_client_flag(self, client):
        """POST /dolibarr/thirdparties con client=1 crea cliente."""
        with patch("api.v1.endpoints.dolibarr.DolibarrThirdpartyService") as MockService:
            mock_service_instance = AsyncMock()
            MockService.return_value = mock_service_instance
            mock_service_instance.create_thirdparty.return_value = {
                "id": 6,
                "nom": "Nuevo Cliente",
                "client": 1,
                "supplier": 0,
            }

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                response = client.post(
                    "/api/v1/dolibarr/thirdparties",
                    json={"name": "Nuevo Cliente", "client": 1},
                )

            assert response.status_code == 201
            data = response.json()
            assert data["data"]["client"] == 1

    def test_create_supplier_sets_supplier_flag(self, client):
        """POST /dolibarr/thirdparties con supplier=1 crea proveedor."""
        with patch("api.v1.endpoints.dolibarr.DolibarrThirdpartyService") as MockService:
            mock_service_instance = AsyncMock()
            MockService.return_value = mock_service_instance
            mock_service_instance.create_thirdparty.return_value = {
                "id": 7,
                "nom": "Nuevo Proveedor",
                "client": 0,
                "supplier": 1,
            }

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                response = client.post(
                    "/api/v1/dolibarr/thirdparties",
                    json={"name": "Nuevo Proveedor", "supplier": 1},
                )

            assert response.status_code == 201
            data = response.json()
            assert data["data"]["supplier"] == 1

    def test_create_both_client_and_supplier(self, client):
        """POST /dolibarr/thirdparties puede crear cliente Y proveedor simultáneamente."""
        with patch("api.v1.endpoints.dolibarr.DolibarrThirdpartyService") as MockService:
            mock_service_instance = AsyncMock()
            MockService.return_value = mock_service_instance
            mock_service_instance.create_thirdparty.return_value = {
                "id": 8,
                "nom": "Empresa Híbrida",
                "client": 1,
                "supplier": 1,
            }

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                response = client.post(
                    "/api/v1/dolibarr/thirdparties",
                    json={"name": "Empresa Híbrida", "client": 1, "supplier": 1},
                )

            assert response.status_code == 201
            data = response.json()
            assert data["data"]["client"] == 1
            assert data["data"]["supplier"] == 1


class TestUpdateThirdparty:
    """Tests para actualizar un tercero."""

    def test_update_returns_updated_data(self, client):
        """PUT /dolibarr/thirdparties/{id} devuelve los datos actualizados."""
        with patch("api.v1.endpoints.dolibarr.DolibarrThirdpartyService") as MockService:
            mock_service_instance = AsyncMock()
            MockService.return_value = mock_service_instance
            mock_service_instance.update_thirdparty.return_value = {
                "id": 9,
                "nom": "Empresa Actualizada",
            }

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                response = client.put(
                    "/api/v1/dolibarr/thirdparties/9",
                    json={"nom": "Empresa Actualizada"},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["data"]["nom"] == "Empresa Actualizada"


class TestDeleteThirdparty:
    """Tests para eliminar un tercero."""

    def test_delete_returns_success_message(self, client):
        """DELETE /dolibarr/thirdparties/{id} devuelve mensaje de éxito."""
        with patch("api.v1.endpoints.dolibarr.DolibarrThirdpartyService") as MockService:
            mock_service_instance = AsyncMock()
            MockService.return_value = mock_service_instance
            mock_service_instance.delete_thirdparty.return_value = True

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                response = client.delete("/api/v1/dolibarr/thirdparties/10")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "eliminado" in data["message"].lower()

    def test_delete_returns_409_when_has_associated_records(self, client):
        """DELETE /dolibarr/thirdparties/{id} devuelve 409 con registros asociados."""
        with patch("api.v1.endpoints.dolibarr.DolibarrThirdpartyService") as MockService:
            mock_service_instance = AsyncMock()
            MockService.return_value = mock_service_instance
            mock_service_instance.delete_thirdparty.return_value = False

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                response = client.delete("/api/v1/dolibarr/thirdparties/11")

            assert response.status_code == 409
            data = response.json()
            assert "registros asociados" in data["detail"].lower()


class TestGetThirdpartyInvoices:
    """Tests para obtener facturas de un tercero."""

    def test_get_invoices_for_customer(self, client):
        """GET /dolibarr/thirdparties/{id}/invoices devuelve facturas de cliente."""
        with patch("api.v1.endpoints.dolibarr.DolibarrThirdpartyService") as MockService:
            mock_service_instance = AsyncMock()
            MockService.return_value = mock_service_instance
            mock_service_instance.get_thirdparty_invoices.return_value = [
                {"id": 101, "type": "customer"}
            ]

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                response = client.get(
                    "/api/v1/dolibarr/thirdparties/12/invoices?type=customer"
                )

            assert response.status_code == 200
            call_kwargs = mock_service_instance.get_thirdparty_invoices.call_args.kwargs
            assert call_kwargs.get("type") == "customer"

    def test_get_invoices_for_supplier(self, client):
        """GET /dolibarr/thirdparties/{id}/invoices devuelve facturas de proveedor."""
        with patch("api.v1.endpoints.dolibarr.DolibarrThirdpartyService") as MockService:
            mock_service_instance = AsyncMock()
            MockService.return_value = mock_service_instance
            mock_service_instance.get_thirdparty_invoices.return_value = [
                {"id": 102, "type": "supplier"}
            ]

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                response = client.get(
                    "/api/v1/dolibarr/thirdparties/13/invoices?type=supplier"
                )

            assert response.status_code == 200
            call_kwargs = mock_service_instance.get_thirdparty_invoices.call_args.kwargs
            assert call_kwargs.get("type") == "supplier"


class TestGetThirdpartyOrders:
    """Tests para obtener pedidos de un tercero."""

    def test_get_orders_for_customer(self, client):
        """GET /dolibarr/thirdparties/{id}/orders devuelve pedidos de cliente."""
        with patch("api.v1.endpoints.dolibarr.DolibarrThirdpartyService") as MockService:
            mock_service_instance = AsyncMock()
            MockService.return_value = mock_service_instance
            mock_service_instance.get_thirdparty_orders.return_value = [
                {"id": 201, "type": "customer"}
            ]

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                response = client.get(
                    "/api/v1/dolibarr/thirdparties/14/orders?type=customer"
                )

            assert response.status_code == 200
            call_kwargs = mock_service_instance.get_thirdparty_orders.call_args.kwargs
            assert call_kwargs.get("type") == "customer"

    def test_get_orders_for_supplier(self, client):
        """GET /dolibarr/thirdparties/{id}/orders devuelve pedidos de proveedor."""
        with patch("api.v1.endpoints.dolibarr.DolibarrThirdpartyService") as MockService:
            mock_service_instance = AsyncMock()
            MockService.return_value = mock_service_instance
            mock_service_instance.get_thirdparty_orders.return_value = [
                {"id": 202, "type": "supplier"}
            ]

            with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
                mock_settings.return_value.dolibarr_configured = True
                response = client.get(
                    "/api/v1/dolibarr/thirdparties/15/orders?type=supplier"
                )

            assert response.status_code == 200
            call_kwargs = mock_service_instance.get_thirdparty_orders.call_args.kwargs
            assert call_kwargs.get("type") == "supplier"
