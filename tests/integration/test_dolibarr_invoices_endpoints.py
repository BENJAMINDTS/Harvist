"""
Tests de integración para endpoints de Dolibarr invoices.

:author: Carlitos6712
:version: 1.0.0
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client() -> TestClient:
    """Fixture con cliente de prueba FastAPI."""
    return TestClient(app)


# ── Not Configured ────────────────────────────────────────────────────


class TestNotConfigured:
    """Tests para endpoints cuando Dolibarr no está configurado."""

    @pytest.mark.asyncio
    async def test_list_returns_503_when_not_configured(
        self, client: TestClient
    ) -> None:
        """Verifica que list retorna 503 si Dolibarr no está configurado."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings"
        ) as mock_settings:
            mock_settings.return_value.dolibarr_configured = False
            response = client.get("/api/v1/dolibarr/invoices")
            assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_get_returns_503_when_not_configured(
        self, client: TestClient
    ) -> None:
        """Verifica que get retorna 503 si Dolibarr no está configurado."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings"
        ) as mock_settings:
            mock_settings.return_value.dolibarr_configured = False
            response = client.get("/api/v1/dolibarr/invoices/1")
            assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_create_returns_503_when_not_configured(
        self, client: TestClient
    ) -> None:
        """Verifica que create retorna 503 si Dolibarr no está configurado."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings"
        ) as mock_settings:
            mock_settings.return_value.dolibarr_configured = False
            response = client.post("/api/v1/dolibarr/invoices", json={})
            assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_add_line_returns_503_when_not_configured(
        self, client: TestClient
    ) -> None:
        """Verifica que add_line retorna 503 si Dolibarr no está configurado."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings"
        ) as mock_settings:
            mock_settings.return_value.dolibarr_configured = False
            response = client.post(
                "/api/v1/dolibarr/invoices/1/lines", json={}
            )
            assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_validate_returns_503_when_not_configured(
        self, client: TestClient
    ) -> None:
        """Verifica que validate retorna 503 si Dolibarr no está configurado."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings"
        ) as mock_settings:
            mock_settings.return_value.dolibarr_configured = False
            response = client.post("/api/v1/dolibarr/invoices/1/validate")
            assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_send_returns_503_when_not_configured(
        self, client: TestClient
    ) -> None:
        """Verifica que send retorna 503 si Dolibarr no está configurado."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings"
        ) as mock_settings:
            mock_settings.return_value.dolibarr_configured = False
            response = client.post(
                "/api/v1/dolibarr/invoices/1/send", json={}
            )
            assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_pay_returns_503_when_not_configured(
        self, client: TestClient
    ) -> None:
        """Verifica que pay retorna 503 si Dolibarr no está configurado."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings"
        ) as mock_settings:
            mock_settings.return_value.dolibarr_configured = False
            response = client.post(
                "/api/v1/dolibarr/invoices/1/pay", json={}
            )
            assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_delete_returns_503_when_not_configured(
        self, client: TestClient
    ) -> None:
        """Verifica que delete retorna 503 si Dolibarr no está configurado."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings"
        ) as mock_settings:
            mock_settings.return_value.dolibarr_configured = False
            response = client.delete("/api/v1/dolibarr/invoices/1")
            assert response.status_code == 503


# ── ListInvoices ────────────────────────────────────────────────────


class TestListInvoices:
    """Tests para endpoint list_invoices."""

    @pytest.mark.asyncio
    async def test_list_customer_invoices_returns_paginated_response(
        self, client: TestClient
    ) -> None:
        """Verifica que list retorna respuesta paginada para customer."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings"
        ) as mock_settings, patch(
            "api.v1.endpoints.dolibarr.DolibarrClient"
        ) as mock_client_class:
            mock_settings.return_value.dolibarr_configured = True
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.get.return_value = [
                {"id": 1, "ref": "INV001", "status": 1}
            ]

            response = client.get(
                "/api/v1/dolibarr/invoices?type=customer"
            )

            assert response.status_code == 200
            data = response.json()
            assert "items" in data

    @pytest.mark.asyncio
    async def test_list_supplier_invoices_uses_different_service_path(
        self, client: TestClient
    ) -> None:
        """Verifica que list usa diferente path para supplier."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings"
        ) as mock_settings, patch(
            "api.v1.endpoints.dolibarr.DolibarrClient"
        ) as mock_client_class:
            mock_settings.return_value.dolibarr_configured = True
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.get.return_value = [
                {"id": 2, "ref": "SINV001", "status": 1}
            ]

            response = client.get(
                "/api/v1/dolibarr/invoices?type=supplier"
            )

            assert response.status_code == 200


# ── GetInvoice ──────────────────────────────────────────────────────


class TestGetInvoice:
    """Tests para endpoint get_invoice."""

    @pytest.mark.asyncio
    async def test_get_returns_invoice_data(self, client: TestClient) -> None:
        """Verifica que get retorna datos de factura."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings"
        ) as mock_settings, patch(
            "api.v1.endpoints.dolibarr.DolibarrClient"
        ) as mock_client_class:
            mock_settings.return_value.dolibarr_configured = True
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.get.return_value = {"id": 1, "ref": "INV001"}

            response = client.get("/api/v1/dolibarr/invoices/1")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    @pytest.mark.asyncio
    async def test_get_returns_404_for_nonexistent(
        self, client: TestClient
    ) -> None:
        """Verifica que get retorna 404 si no existe."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings"
        ) as mock_settings, patch(
            "api.v1.endpoints.dolibarr.DolibarrClient"
        ) as mock_client_class:
            mock_settings.return_value.dolibarr_configured = True
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            from services.integrations.base import IntegrationError

            mock_client.get.side_effect = IntegrationError("404 not found")

            response = client.get("/api/v1/dolibarr/invoices/999")

            assert response.status_code == 404


# ── CreateInvoice ──────────────────────────────────────────────────


class TestCreateInvoice:
    """Tests para endpoint create_invoice."""

    @pytest.mark.asyncio
    async def test_create_returns_201(self, client: TestClient) -> None:
        """Verifica que create retorna 201."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings"
        ) as mock_settings, patch(
            "api.v1.endpoints.dolibarr.DolibarrClient"
        ) as mock_client_class:
            mock_settings.return_value.dolibarr_configured = True
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.post.return_value = {"id": 1, "ref": "INV001"}

            response = client.post(
                "/api/v1/dolibarr/invoices",
                json={"socid": 42, "date": 1234567890},
            )

            assert response.status_code == 201


# ── ValidateInvoice ────────────────────────────────────────────────


class TestValidateInvoice:
    """Tests para endpoint validate_invoice."""

    @pytest.mark.asyncio
    async def test_validate_returns_updated_invoice(
        self, client: TestClient
    ) -> None:
        """Verifica que validate retorna factura validada."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings"
        ) as mock_settings, patch(
            "api.v1.endpoints.dolibarr.DolibarrClient"
        ) as mock_client_class:
            mock_settings.return_value.dolibarr_configured = True
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.get.return_value = {"id": 1, "status": 0}
            mock_client.post.return_value = {"id": 1, "status": 1}

            response = client.post("/api/v1/dolibarr/invoices/1/validate")

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_validate_returns_409_if_not_in_draft(
        self, client: TestClient
    ) -> None:
        """Verifica que validate retorna 409 si no está en borrador."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings"
        ) as mock_settings, patch(
            "api.v1.endpoints.dolibarr.DolibarrClient"
        ) as mock_client_class:
            mock_settings.return_value.dolibarr_configured = True
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.get.return_value = {"id": 1, "status": 2}

            response = client.post("/api/v1/dolibarr/invoices/1/validate")

            assert response.status_code == 409


# ── SendByEmail ────────────────────────────────────────────────────


class TestSendByEmail:
    """Tests para endpoint send_by_email."""

    @pytest.mark.asyncio
    async def test_send_returns_success_message(
        self, client: TestClient
    ) -> None:
        """Verifica que send retorna mensaje de éxito."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings"
        ) as mock_settings, patch(
            "api.v1.endpoints.dolibarr.DolibarrClient"
        ) as mock_client_class:
            mock_settings.return_value.dolibarr_configured = True
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.get.return_value = {"id": 1, "status": 1}
            mock_client.post.return_value = {}

            response = client.post(
                "/api/v1/dolibarr/invoices/1/send",
                json={"email": "test@example.com"},
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_send_returns_409_if_invoice_not_validated(
        self, client: TestClient
    ) -> None:
        """Verifica que send retorna 409 si factura no está validada."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings"
        ) as mock_settings, patch(
            "api.v1.endpoints.dolibarr.DolibarrClient"
        ) as mock_client_class:
            mock_settings.return_value.dolibarr_configured = True
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.get.return_value = {"id": 1, "status": 0}

            response = client.post(
                "/api/v1/dolibarr/invoices/1/send",
                json={"email": "test@example.com"},
            )

            assert response.status_code == 409


# ── MarkAsPaid ────────────────────────────────────────────────────


class TestMarkAsPaid:
    """Tests para endpoint mark_as_paid."""

    @pytest.mark.asyncio
    async def test_pay_returns_payment_data(self, client: TestClient) -> None:
        """Verifica que pay retorna datos de pago."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings"
        ) as mock_settings, patch(
            "api.v1.endpoints.dolibarr.DolibarrClient"
        ) as mock_client_class:
            mock_settings.return_value.dolibarr_configured = True
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.post.return_value = {"id": 1, "datepaye": 1234567890}

            response = client.post(
                "/api/v1/dolibarr/invoices/1/pay",
                json={
                    "payment_date": 1234567890,
                    "payment_type_id": 1,
                    "bank_account_id": 42,
                },
            )

            assert response.status_code == 200


# ── DeleteInvoice ──────────────────────────────────────────────────


class TestDeleteInvoice:
    """Tests para endpoint delete_invoice."""

    @pytest.mark.asyncio
    async def test_delete_returns_success(self, client: TestClient) -> None:
        """Verifica que delete retorna mensaje de éxito."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings"
        ) as mock_settings, patch(
            "api.v1.endpoints.dolibarr.DolibarrClient"
        ) as mock_client_class:
            mock_settings.return_value.dolibarr_configured = True
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.get.return_value = {"id": 1, "status": 0}
            mock_client.delete.return_value = None

            response = client.delete("/api/v1/dolibarr/invoices/1")

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_returns_409_if_not_in_draft(
        self, client: TestClient
    ) -> None:
        """Verifica que delete retorna 409 si no está en borrador."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings"
        ) as mock_settings, patch(
            "api.v1.endpoints.dolibarr.DolibarrClient"
        ) as mock_client_class:
            mock_settings.return_value.dolibarr_configured = True
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.get.return_value = {"id": 1, "status": 1}

            response = client.delete("/api/v1/dolibarr/invoices/1")

            assert response.status_code == 409


class TestRedisConfigPath:
    """Tests que verifican que las credenciales de Redis se usan cuando .env no tiene config."""

    def test_list_invoices_uses_redis_config_when_env_not_set(self, client):
        """
        list_invoices retorna 200 usando credenciales de Redis
        aunque .env no tenga DOLIBARR_URL ni DOLIBARR_API_KEY.
        """
        mock_svc = MagicMock()
        mock_svc.list_invoices = AsyncMock(return_value=[])

        with patch(
            "api.v1.endpoints.dolibarr._get_dolibarr_credentials",
            new=AsyncMock(return_value=("https://dolibarr.test", "test-key")),
        ):
            with patch("api.v1.endpoints.dolibarr.DolibarrClient"):
                with patch(
                    "api.v1.endpoints.dolibarr.DolibarrInvoiceService",
                    return_value=mock_svc,
                ):
                    response = client.get("/api/v1/dolibarr/invoices")

        assert response.status_code == 200
        assert response.json()["items"] == []
        mock_svc.list_invoices.assert_called_once()
