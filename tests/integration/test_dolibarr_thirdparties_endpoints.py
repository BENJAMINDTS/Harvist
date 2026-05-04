"""
Tests de integración para endpoints de terceros de Dolibarr.

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ── Variables de entorno mínimas ─────────────────────────────────────────────
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-32-chars-long-enough")
os.environ.setdefault("BROWSER_BINARY_PATH", "/usr/bin/google-chrome")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

from api.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from api.main import app  # noqa: E402
from services.integrations.base import IntegrationError

_BASE = "/api/v1/dolibarr/thirdparties"


def _mock_settings(configured: bool = True) -> MagicMock:
    """Crea un mock de Settings con Dolibarr configurado o no."""
    s = MagicMock()
    s.dolibarr_configured = configured
    s.dolibarr_url = "https://dolibarr.test" if configured else ""
    s.dolibarr_api_key = "test-key" if configured else ""
    return s


def _mock_svc(
    list_return=None,
    get_return=None,
    search_return=None,
    create_return=None,
    update_return=None,
    delete_return=True,
    get_invoices_return=None,
    get_orders_return=None,
    get_exc=None,
) -> MagicMock:
    """Construye un mock completo de DolibarrThirdpartyService."""
    svc = MagicMock()
    svc.list_thirdparties = AsyncMock(return_value=list_return or [])
    svc.get_thirdparty = AsyncMock(return_value=get_return or {"id": 1})
    svc.search_thirdparty = AsyncMock(return_value=search_return or [])
    svc.create_thirdparty = AsyncMock(return_value=create_return or {"id": 1})
    svc.update_thirdparty = AsyncMock(return_value=update_return or {"id": 1})
    svc.delete_thirdparty = AsyncMock(return_value=delete_return)
    svc.get_thirdparty_invoices = AsyncMock(return_value=get_invoices_return or [])
    svc.get_thirdparty_orders = AsyncMock(return_value=get_orders_return or [])
    if get_exc:
        svc.get_thirdparty = AsyncMock(side_effect=get_exc)
    return svc


@pytest_asyncio.fixture
async def http_client() -> AsyncClient:
    """Cliente HTTP async para la app FastAPI."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# 503 — Dolibarr no configurado
# ---------------------------------------------------------------------------


class TestNotConfigured:
    """503 cuando Dolibarr no está configurado — todos los endpoints."""

    def _not_configured_patch(self):
        return patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(configured=False),
        )

    async def test_list_returns_503_when_not_configured(self, http_client):
        """GET /dolibarr/thirdparties devuelve 503 si no configurado."""
        with self._not_configured_patch():
            response = await http_client.get(f"{_BASE}")
            assert response.status_code == 503

    async def test_search_returns_503_when_not_configured(self, http_client):
        """GET /dolibarr/thirdparties/search devuelve 503 si no configurado."""
        with self._not_configured_patch():
            response = await http_client.get(f"{_BASE}/search?name=test")
            assert response.status_code == 503

    async def test_get_returns_503_when_not_configured(self, http_client):
        """GET /dolibarr/thirdparties/{id} devuelve 503 si no configurado."""
        with self._not_configured_patch():
            response = await http_client.get(f"{_BASE}/1")
            assert response.status_code == 503

    async def test_create_returns_503_when_not_configured(self, http_client):
        """POST /dolibarr/thirdparties devuelve 503 si no configurado."""
        with self._not_configured_patch():
            response = await http_client.post(f"{_BASE}", json={"name": "Test"})
            assert response.status_code == 503

    async def test_update_returns_503_when_not_configured(self, http_client):
        """PUT /dolibarr/thirdparties/{id} devuelve 503 si no configurado."""
        with self._not_configured_patch():
            response = await http_client.put(
                f"{_BASE}/1", json={"name": "Updated"}
            )
            assert response.status_code == 503

    async def test_delete_returns_503_when_not_configured(self, http_client):
        """DELETE /dolibarr/thirdparties/{id} devuelve 503 si no configurado."""
        with self._not_configured_patch():
            response = await http_client.delete(f"{_BASE}/1")
            assert response.status_code == 503

    async def test_get_invoices_returns_503_when_not_configured(self, http_client):
        """GET /dolibarr/thirdparties/{id}/invoices devuelve 503 si no configurado."""
        with self._not_configured_patch():
            response = await http_client.get(f"{_BASE}/1/invoices")
            assert response.status_code == 503

    async def test_get_orders_returns_503_when_not_configured(self, http_client):
        """GET /dolibarr/thirdparties/{id}/orders devuelve 503 si no configurado."""
        with self._not_configured_patch():
            response = await http_client.get(f"{_BASE}/1/orders")
            assert response.status_code == 503


# ---------------------------------------------------------------------------
# Listar terceros
# ---------------------------------------------------------------------------


class TestListThirdparties:
    """Tests para listar terceros."""

    async def test_list_all_sends_no_filter(self, http_client):
        """GET /dolibarr/thirdparties con mode=all no envía filtro."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ):
            with patch(
                "api.v1.endpoints.dolibarr.DolibarrThirdpartyService",
                return_value=_mock_svc(list_return=[{"id": 1, "nom": "Empresa 1"}]),
            ):
                response = await http_client.get(f"{_BASE}?mode=all")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    async def test_list_customers_filters_correctly(self, http_client):
        """GET /dolibarr/thirdparties con mode=customers filtra por clientes."""
        mock_svc = _mock_svc(list_return=[{"id": 2, "nom": "Cliente A", "client": 1}])
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ):
            with patch(
                "api.v1.endpoints.dolibarr.DolibarrThirdpartyService",
                return_value=mock_svc,
            ):
                response = await http_client.get(f"{_BASE}?mode=customers")

        assert response.status_code == 200
        mock_svc.list_thirdparties.assert_called()
        call_kwargs = mock_svc.list_thirdparties.call_args.kwargs
        assert call_kwargs.get("mode") == "customers"

    async def test_list_suppliers_filters_correctly(self, http_client):
        """GET /dolibarr/thirdparties con mode=suppliers filtra por proveedores."""
        mock_svc = _mock_svc(list_return=[{"id": 3, "nom": "Proveedor X", "supplier": 1}])
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ):
            with patch(
                "api.v1.endpoints.dolibarr.DolibarrThirdpartyService",
                return_value=mock_svc,
            ):
                response = await http_client.get(f"{_BASE}?mode=suppliers")

        assert response.status_code == 200
        mock_svc.list_thirdparties.assert_called()
        call_kwargs = mock_svc.list_thirdparties.call_args.kwargs
        assert call_kwargs.get("mode") == "suppliers"


# ---------------------------------------------------------------------------
# Búsqueda
# ---------------------------------------------------------------------------


class TestSearchThirdparties:
    """Tests para búsqueda de terceros."""

    async def test_search_returns_matching_thirdparties(self, http_client):
        """GET /dolibarr/thirdparties/search devuelve terceros coincidentes."""
        mock_svc = _mock_svc(search_return=[{"id": 4, "nom": "Test Company"}])
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ):
            with patch(
                "api.v1.endpoints.dolibarr.DolibarrThirdpartyService",
                return_value=mock_svc,
            ):
                response = await http_client.get(f"{_BASE}/search?name=Test")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


# ---------------------------------------------------------------------------
# Obtener un tercero
# ---------------------------------------------------------------------------


class TestGetThirdparty:
    """Tests para obtener un tercero."""

    async def test_get_returns_thirdparty_data(self, http_client):
        """GET /dolibarr/thirdparties/{id} devuelve los datos del tercero."""
        mock_svc = _mock_svc(
            get_return={"id": 5, "nom": "Empresa A", "client": 1}
        )
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ):
            with patch(
                "api.v1.endpoints.dolibarr.DolibarrThirdpartyService",
                return_value=mock_svc,
            ):
                response = await http_client.get(f"{_BASE}/5")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["id"] == 5

    async def test_get_returns_404_for_nonexistent(self, http_client):
        """GET /dolibarr/thirdparties/{id} devuelve 404 si no existe."""
        mock_svc = _mock_svc(
            get_exc=IntegrationError("No encontrado", status_code=404)
        )
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ):
            with patch(
                "api.v1.endpoints.dolibarr.DolibarrThirdpartyService",
                return_value=mock_svc,
            ):
                response = await http_client.get(f"{_BASE}/999")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Crear tercero
# ---------------------------------------------------------------------------


class TestCreateThirdparty:
    """Tests para crear un tercero."""

    async def test_create_customer_sets_client_flag(self, http_client):
        """POST /dolibarr/thirdparties con client=1 crea cliente."""
        mock_svc = _mock_svc(
            create_return={
                "id": 6,
                "nom": "Nuevo Cliente",
                "client": 1,
                "supplier": 0,
            }
        )
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ):
            with patch(
                "api.v1.endpoints.dolibarr.DolibarrThirdpartyService",
                return_value=mock_svc,
            ):
                response = await http_client.post(
                    f"{_BASE}",
                    json={"name": "Nuevo Cliente", "client": 1},
                )

        assert response.status_code == 201
        data = response.json()
        assert data["data"]["client"] == 1

    async def test_create_supplier_sets_supplier_flag(self, http_client):
        """POST /dolibarr/thirdparties con supplier=1 crea proveedor."""
        mock_svc = _mock_svc(
            create_return={
                "id": 7,
                "nom": "Nuevo Proveedor",
                "client": 0,
                "supplier": 1,
            }
        )
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ):
            with patch(
                "api.v1.endpoints.dolibarr.DolibarrThirdpartyService",
                return_value=mock_svc,
            ):
                response = await http_client.post(
                    f"{_BASE}",
                    json={"name": "Nuevo Proveedor", "supplier": 1},
                )

        assert response.status_code == 201
        data = response.json()
        assert data["data"]["supplier"] == 1

    async def test_create_both_client_and_supplier(self, http_client):
        """POST /dolibarr/thirdparties puede crear cliente Y proveedor simultáneamente."""
        mock_svc = _mock_svc(
            create_return={
                "id": 8,
                "nom": "Empresa Híbrida",
                "client": 1,
                "supplier": 1,
            }
        )
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ):
            with patch(
                "api.v1.endpoints.dolibarr.DolibarrThirdpartyService",
                return_value=mock_svc,
            ):
                response = await http_client.post(
                    f"{_BASE}",
                    json={"name": "Empresa Híbrida", "client": 1, "supplier": 1},
                )

        assert response.status_code == 201
        data = response.json()
        assert data["data"]["client"] == 1
        assert data["data"]["supplier"] == 1


# ---------------------------------------------------------------------------
# Actualizar tercero
# ---------------------------------------------------------------------------


class TestUpdateThirdparty:
    """Tests para actualizar un tercero."""

    async def test_update_returns_updated_data(self, http_client):
        """PUT /dolibarr/thirdparties/{id} devuelve los datos actualizados."""
        mock_svc = _mock_svc(
            update_return={"id": 9, "nom": "Empresa Actualizada"}
        )
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ):
            with patch(
                "api.v1.endpoints.dolibarr.DolibarrThirdpartyService",
                return_value=mock_svc,
            ):
                response = await http_client.put(
                    f"{_BASE}/9",
                    json={"nom": "Empresa Actualizada"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["nom"] == "Empresa Actualizada"


# ---------------------------------------------------------------------------
# Eliminar tercero
# ---------------------------------------------------------------------------


class TestDeleteThirdparty:
    """Tests para eliminar un tercero."""

    async def test_delete_returns_success_message(self, http_client):
        """DELETE /dolibarr/thirdparties/{id} devuelve mensaje de éxito."""
        mock_svc = _mock_svc(delete_return=True)
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ):
            with patch(
                "api.v1.endpoints.dolibarr.DolibarrThirdpartyService",
                return_value=mock_svc,
            ):
                response = await http_client.delete(f"{_BASE}/10")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "eliminado" in data["message"].lower()

    async def test_delete_returns_409_when_has_associated_records(self, http_client):
        """DELETE /dolibarr/thirdparties/{id} devuelve 409 con registros asociados."""
        mock_svc = _mock_svc(delete_return=False)
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ):
            with patch(
                "api.v1.endpoints.dolibarr.DolibarrThirdpartyService",
                return_value=mock_svc,
            ):
                response = await http_client.delete(f"{_BASE}/11")

        assert response.status_code == 409
        data = response.json()
        assert "registros asociados" in data["detail"].lower()


# ---------------------------------------------------------------------------
# Obtener facturas
# ---------------------------------------------------------------------------


class TestGetThirdpartyInvoices:
    """Tests para obtener facturas de un tercero."""

    async def test_get_invoices_for_customer(self, http_client):
        """GET /dolibarr/thirdparties/{id}/invoices devuelve facturas de cliente."""
        mock_svc = _mock_svc(get_invoices_return=[{"id": 101, "type": "customer"}])
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ):
            with patch(
                "api.v1.endpoints.dolibarr.DolibarrThirdpartyService",
                return_value=mock_svc,
            ):
                response = await http_client.get(
                    f"{_BASE}/12/invoices?type=customer"
                )

        assert response.status_code == 200
        call_kwargs = mock_svc.get_thirdparty_invoices.call_args.kwargs
        assert call_kwargs.get("type") == "customer"

    async def test_get_invoices_for_supplier(self, http_client):
        """GET /dolibarr/thirdparties/{id}/invoices devuelve facturas de proveedor."""
        mock_svc = _mock_svc(get_invoices_return=[{"id": 102, "type": "supplier"}])
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ):
            with patch(
                "api.v1.endpoints.dolibarr.DolibarrThirdpartyService",
                return_value=mock_svc,
            ):
                response = await http_client.get(
                    f"{_BASE}/13/invoices?type=supplier"
                )

        assert response.status_code == 200
        call_kwargs = mock_svc.get_thirdparty_invoices.call_args.kwargs
        assert call_kwargs.get("type") == "supplier"


# ---------------------------------------------------------------------------
# Obtener pedidos
# ---------------------------------------------------------------------------


class TestGetThirdpartyOrders:
    """Tests para obtener pedidos de un tercero."""

    async def test_get_orders_for_customer(self, http_client):
        """GET /dolibarr/thirdparties/{id}/orders devuelve pedidos de cliente."""
        mock_svc = _mock_svc(get_orders_return=[{"id": 201, "type": "customer"}])
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ):
            with patch(
                "api.v1.endpoints.dolibarr.DolibarrThirdpartyService",
                return_value=mock_svc,
            ):
                response = await http_client.get(
                    f"{_BASE}/14/orders?type=customer"
                )

        assert response.status_code == 200
        call_kwargs = mock_svc.get_thirdparty_orders.call_args.kwargs
        assert call_kwargs.get("type") == "customer"

    async def test_get_orders_for_supplier(self, http_client):
        """GET /dolibarr/thirdparties/{id}/orders devuelve pedidos de proveedor."""
        mock_svc = _mock_svc(get_orders_return=[{"id": 202, "type": "supplier"}])
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ):
            with patch(
                "api.v1.endpoints.dolibarr.DolibarrThirdpartyService",
                return_value=mock_svc,
            ):
                response = await http_client.get(
                    f"{_BASE}/15/orders?type=supplier"
                )

        assert response.status_code == 200
        call_kwargs = mock_svc.get_thirdparty_orders.call_args.kwargs
        assert call_kwargs.get("type") == "supplier"
