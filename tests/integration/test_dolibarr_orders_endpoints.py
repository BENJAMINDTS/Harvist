"""
Tests de integración para endpoints de pedidos Dolibarr.

:author: BenjaminDTS
:version: 1.0.0
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from api.main import app
from services.integrations.base import IntegrationError, IntegrationNotConfiguredError


@pytest.fixture
def client() -> TestClient:
    """Fixture con cliente HTTP de test."""
    return TestClient(app)


@pytest.fixture
def _mock_settings_not_configured() -> None:
    """Mock settings no configurado."""
    with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
        settings = mock_settings.return_value
        settings.dolibarr_configured = False
        yield


@pytest.fixture
def _mock_settings_configured() -> None:
    """Mock settings configurado."""
    with patch("api.v1.endpoints.dolibarr.get_settings") as mock_settings:
        settings = mock_settings.return_value
        settings.dolibarr_configured = True
        yield


# ── NotConfigured ───────────────────────────────────────────────────


class TestNotConfigured:
    """Tests para endpoints cuando Dolibarr no está configurado."""

    def test_list_returns_503_when_not_configured(
        self, client: TestClient, _mock_settings_not_configured
    ) -> None:
        """Verifica que list retorna 503 si no configurado."""
        response = client.get("/api/v1/dolibarr/orders")
        assert response.status_code == 503

    def test_get_returns_503_when_not_configured(
        self, client: TestClient, _mock_settings_not_configured
    ) -> None:
        """Verifica que get retorna 503 si no configurado."""
        response = client.get("/api/v1/dolibarr/orders/1")
        assert response.status_code == 503

    def test_create_returns_503_when_not_configured(
        self, client: TestClient, _mock_settings_not_configured
    ) -> None:
        """Verifica que create retorna 503 si no configurado."""
        response = client.post("/api/v1/dolibarr/orders", json={"socid": 42})
        assert response.status_code == 503

    def test_add_line_returns_503_when_not_configured(
        self, client: TestClient, _mock_settings_not_configured
    ) -> None:
        """Verifica que add_line retorna 503 si no configurado."""
        response = client.post(
            "/api/v1/dolibarr/orders/1/lines",
            json={"fk_product": 10, "qty": 5},
        )
        assert response.status_code == 503

    def test_patch_status_returns_503_when_not_configured(
        self, client: TestClient, _mock_settings_not_configured
    ) -> None:
        """Verifica que patch status retorna 503 si no configurado."""
        response = client.patch(
            "/api/v1/dolibarr/orders/1/status",
            json={"status": 1},
        )
        assert response.status_code == 503

    def test_delete_returns_503_when_not_configured(
        self, client: TestClient, _mock_settings_not_configured
    ) -> None:
        """Verifica que delete retorna 503 si no configurado."""
        response = client.delete("/api/v1/dolibarr/orders/1")
        assert response.status_code == 503


# ── ListOrders ──────────────────────────────────────────────────────


class TestListOrders:
    """Tests para list_orders endpoint."""

    def test_list_customer_orders_returns_paginated_response(
        self, client: TestClient, _mock_settings_configured
    ) -> None:
        """Verifica que list customer retorna respuesta paginada."""
        with patch(
            "api.v1.endpoints.dolibarr._get_order_service"
        ) as mock_service_factory:
            mock_svc = AsyncMock()
            mock_svc.list_orders.return_value = [{"id": 1, "ref": "C001"}]
            mock_service_factory.return_value = mock_svc

            response = client.get("/api/v1/dolibarr/orders?type=customer")

            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert "total" in data
            assert "limit" in data
            assert "offset" in data
            assert "has_more" in data

    def test_list_supplier_orders_calls_correct_service_method(
        self, client: TestClient, _mock_settings_configured
    ) -> None:
        """Verifica que list supplier llama al servicio con type=supplier."""
        with patch(
            "api.v1.endpoints.dolibarr._get_order_service"
        ) as mock_service_factory:
            mock_svc = AsyncMock()
            mock_svc.list_orders.return_value = []
            mock_service_factory.return_value = mock_svc

            client.get("/api/v1/dolibarr/orders?type=supplier")

            call_kwargs = mock_svc.list_orders.call_args[1]
            assert call_kwargs["type"] == "supplier"

    def test_list_with_filters_passes_them_to_service(
        self, client: TestClient, _mock_settings_configured
    ) -> None:
        """Verifica que status y thirdparty_id se pasan al servicio."""
        with patch(
            "api.v1.endpoints.dolibarr._get_order_service"
        ) as mock_service_factory:
            mock_svc = AsyncMock()
            mock_svc.list_orders.return_value = []
            mock_service_factory.return_value = mock_svc

            client.get("/api/v1/dolibarr/orders?status=1&thirdparty_id=42")

            call_kwargs = mock_svc.list_orders.call_args[1]
            assert call_kwargs["status"] == 1
            assert call_kwargs["thirdparty_id"] == 42


# ── GetOrder ────────────────────────────────────────────────────────


class TestGetOrder:
    """Tests para get_order endpoint."""

    def test_get_returns_order_data(
        self, client: TestClient, _mock_settings_configured
    ) -> None:
        """Verifica que get retorna datos del pedido."""
        with patch(
            "api.v1.endpoints.dolibarr._get_order_service"
        ) as mock_service_factory:
            mock_svc = AsyncMock()
            mock_svc.get_order.return_value = {"id": 1, "ref": "C001"}
            mock_service_factory.return_value = mock_svc

            response = client.get("/api/v1/dolibarr/orders/1")

            assert response.status_code == 200
            assert response.json()["data"]["id"] == 1

    def test_get_nonexistent_returns_404(
        self, client: TestClient, _mock_settings_configured
    ) -> None:
        """Verifica que get nonexistent retorna 404."""
        with patch(
            "api.v1.endpoints.dolibarr._get_order_service"
        ) as mock_service_factory:
            mock_svc = AsyncMock()
            mock_svc.get_order.side_effect = IntegrationError("404: not found")
            mock_service_factory.return_value = mock_svc

            response = client.get("/api/v1/dolibarr/orders/999")

            assert response.status_code == 404


# ── CreateOrder ─────────────────────────────────────────────────────


class TestCreateOrder:
    """Tests para create_order endpoint."""

    def test_create_returns_201(
        self, client: TestClient, _mock_settings_configured
    ) -> None:
        """Verifica que create retorna 201."""
        with patch(
            "api.v1.endpoints.dolibarr._get_order_service"
        ) as mock_service_factory:
            mock_svc = AsyncMock()
            mock_svc.create_order.return_value = {"id": 1, "ref": "C001", "socid": 42}
            mock_service_factory.return_value = mock_svc

            response = client.post(
                "/api/v1/dolibarr/orders",
                json={"socid": 42, "date": 1234567890},
            )

            assert response.status_code == 201
            assert response.json()["data"]["id"] == 1


# ── AddOrderLine ────────────────────────────────────────────────────


class TestAddOrderLine:
    """Tests para add_order_line endpoint."""

    def test_add_line_returns_created_line(
        self, client: TestClient, _mock_settings_configured
    ) -> None:
        """Verifica que add_line retorna la línea creada."""
        with patch(
            "api.v1.endpoints.dolibarr._get_order_service"
        ) as mock_service_factory:
            mock_svc = AsyncMock()
            mock_svc.add_order_line.return_value = {
                "id": 1,
                "fk_order": 1,
                "fk_product": 10,
            }
            mock_service_factory.return_value = mock_svc

            response = client.post(
                "/api/v1/dolibarr/orders/1/lines",
                json={"fk_product": 10, "qty": 5, "subprice": 99.99},
            )

            assert response.status_code == 201
            assert response.json()["data"]["id"] == 1


# ── UpdateOrderStatus ───────────────────────────────────────────────


class TestUpdateOrderStatus:
    """Tests para update_order_status endpoint."""

    def test_patch_status_returns_updated_order(
        self, client: TestClient, _mock_settings_configured
    ) -> None:
        """Verifica que patch status retorna pedido actualizado."""
        with patch(
            "api.v1.endpoints.dolibarr._get_order_service"
        ) as mock_service_factory:
            mock_svc = AsyncMock()
            mock_svc.update_order_status.return_value = {"id": 1, "status": 1}
            mock_service_factory.return_value = mock_svc

            response = client.patch(
                "/api/v1/dolibarr/orders/1/status",
                json={"status": 1},
            )

            assert response.status_code == 200
            assert response.json()["data"]["status"] == 1

    def test_patch_status_invalid_returns_400(
        self, client: TestClient, _mock_settings_configured
    ) -> None:
        """Verifica que patch con status inválido retorna 400."""
        with patch(
            "api.v1.endpoints.dolibarr._get_order_service"
        ) as mock_service_factory:
            mock_svc = AsyncMock()
            mock_svc.update_order_status.side_effect = ValueError("Invalid status 99")
            mock_service_factory.return_value = mock_svc

            response = client.patch(
                "/api/v1/dolibarr/orders/1/status",
                json={"status": 99},
            )

            assert response.status_code == 400

    def test_patch_status_missing_field_returns_422(
        self, client: TestClient, _mock_settings_configured
    ) -> None:
        """Verifica que patch sin status retorna 422."""
        with patch("api.v1.endpoints.dolibarr._get_order_service"):
            response = client.patch(
                "/api/v1/dolibarr/orders/1/status",
                json={},
            )

            assert response.status_code == 422


# ── DeleteOrder ─────────────────────────────────────────────────────


class TestDeleteOrder:
    """Tests para delete_order endpoint."""

    def test_delete_in_draft_returns_success(
        self, client: TestClient, _mock_settings_configured
    ) -> None:
        """Verifica que delete en estado borrador retorna éxito."""
        with patch(
            "api.v1.endpoints.dolibarr._get_order_service"
        ) as mock_service_factory:
            mock_svc = AsyncMock()
            mock_svc.delete_order.return_value = True
            mock_service_factory.return_value = mock_svc

            response = client.delete("/api/v1/dolibarr/orders/1")

            assert response.status_code == 200
            assert response.json()["data"]["deleted"] is True

    def test_delete_not_in_draft_returns_409(
        self, client: TestClient, _mock_settings_configured
    ) -> None:
        """Verifica que delete no en borrador retorna 409."""
        with patch(
            "api.v1.endpoints.dolibarr._get_order_service"
        ) as mock_service_factory:
            mock_svc = AsyncMock()
            mock_svc.delete_order.return_value = False
            mock_service_factory.return_value = mock_svc

            response = client.delete("/api/v1/dolibarr/orders/1")

            assert response.status_code == 409
