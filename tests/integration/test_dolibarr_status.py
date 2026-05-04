"""
Tests de integración para el status endpoint de Dolibarr y montaje de routers.

:author: Carlitos6712
:version: 1.0.0
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from api.main import app
from api.v1.schemas.integrations import IntegrationStatus


@pytest.fixture
def client():
    """Cliente HTTP de prueba."""
    return TestClient(app)


@pytest.fixture
def mock_settings_not_configured():
    """Settings con Dolibarr no configurado."""
    mock = MagicMock()
    mock.dolibarr_configured = False
    return mock


@pytest.fixture
def mock_settings_configured():
    """Settings con Dolibarr configurado."""
    mock = MagicMock()
    mock.dolibarr_configured = True
    mock.dolibarr_url = "http://localhost/dolibarr"
    mock.dolibarr_api_key = "test_key"
    return mock


class TestGetDolibarrStatus:
    """Tests para GET /api/v1/dolibarr/status."""

    def test_status_returns_configured_false_when_env_vars_not_set(
        self, client, mock_settings_not_configured
    ):
        """Devuelve configured=False cuando env vars no están definidos."""
        with patch("api.v1.endpoints.dolibarr.get_settings", return_value=mock_settings_not_configured):
            response = client.get("/api/v1/dolibarr/status")

        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "dolibarr"
        assert data["configured"] is False
        assert data["healthy"] is None
        assert "DOLIBARR_URL" in data["message"] or "DOLIBARR_API_KEY" in data["message"]

    @pytest.mark.asyncio
    def test_status_returns_healthy_true_when_dolibarr_responds_200(
        self, client, mock_settings_configured
    ):
        """Devuelve healthy=True cuando Dolibarr responde 200."""
        with patch("api.v1.endpoints.dolibarr.get_settings", return_value=mock_settings_configured):
            with patch(
                "api.v1.endpoints.dolibarr.DolibarrClient"
            ) as mock_client_class:
                mock_client = AsyncMock()
                mock_client.health_check = AsyncMock(return_value=True)
                mock_client_class.return_value = mock_client

                response = client.get("/api/v1/dolibarr/status")

        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "dolibarr"
        assert data["configured"] is True
        assert data["healthy"] is True
        assert "establecida" in data["message"].lower()

    @pytest.mark.asyncio
    def test_status_returns_healthy_false_when_dolibarr_does_not_respond(
        self, client, mock_settings_configured
    ):
        """Devuelve healthy=False cuando Dolibarr no responde."""
        with patch("api.v1.endpoints.dolibarr.get_settings", return_value=mock_settings_configured):
            with patch(
                "api.v1.endpoints.dolibarr.DolibarrClient"
            ) as mock_client_class:
                mock_client = AsyncMock()
                mock_client.health_check = AsyncMock(return_value=False)
                mock_client_class.return_value = mock_client

                response = client.get("/api/v1/dolibarr/status")

        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "dolibarr"
        assert data["configured"] is True
        assert data["healthy"] is False

    def test_status_always_returns_http_200_even_when_unhealthy(
        self, client, mock_settings_not_configured
    ):
        """Status siempre devuelve HTTP 200, nunca 503 ni 500."""
        with patch("api.v1.endpoints.dolibarr.get_settings", return_value=mock_settings_not_configured):
            response = client.get("/api/v1/dolibarr/status")

        assert response.status_code == 200
        assert "success" not in response.json() or response.json().get("platform") == "dolibarr"

    def test_all_dolibarr_routers_are_mounted_and_reachable(self, client):
        """Todos los routers de Dolibarr están montados (no retornan 404)."""
        # Estos endpoints puede que devuelvan 503 si no está configurado,
        # pero NO deben devolver 404 (router no montado)
        endpoints = [
            "/api/v1/dolibarr/status",
            "/api/v1/dolibarr/products",
            "/api/v1/dolibarr/categories",
            "/api/v1/dolibarr/thirdparties",
            "/api/v1/dolibarr/orders",
            "/api/v1/dolibarr/invoices",
            "/api/v1/dolibarr/stocks/warehouses",
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code != 404, f"Endpoint {endpoint} returns 404 — router not mounted"
            # Puede devolver 200, 503, etc, pero nunca 404
