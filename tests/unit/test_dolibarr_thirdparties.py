"""
Tests unitarios para DolibarrThirdpartyService.

:author: Carlitos6712
:version: 1.0.0
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.integrations.base import IntegrationError
from services.integrations.dolibarr.thirdparties import DolibarrThirdpartyService


@pytest.fixture
def mock_client():
    """Mock de DolibarrClient."""
    return AsyncMock()


@pytest.fixture
def service(mock_client):
    """Instancia de DolibarrThirdpartyService con cliente mockeado."""
    return DolibarrThirdpartyService(mock_client)


class TestListThirdparties:
    """Tests para list_thirdparties."""

    async def test_list_all_sends_no_mode_filter(self, service, mock_client):
        """list_thirdparties con mode='all' no envía parámetro de filtro."""
        mock_client.list.return_value = [{"id": 1, "nom": "Tercero 1"}]

        result = await service.list_thirdparties(mode="all")

        mock_client.list.assert_called_once()
        call_kwargs = mock_client.list.call_args.kwargs
        assert call_kwargs.get("filters") is None
        assert result == [{"id": 1, "nom": "Tercero 1"}]

    async def test_list_customers_sends_mode_customer_param(self, service, mock_client):
        """list_thirdparties con mode='customers' envía mode=customer."""
        mock_client.list.return_value = [{"id": 2, "nom": "Cliente A"}]

        result = await service.list_thirdparties(mode="customers")

        mock_client.list.assert_called_once()
        call_kwargs = mock_client.list.call_args.kwargs
        assert call_kwargs.get("filters") == {"mode": "customer"}
        assert result == [{"id": 2, "nom": "Cliente A"}]

    async def test_list_suppliers_sends_mode_supplier_param(self, service, mock_client):
        """list_thirdparties con mode='suppliers' envía mode=supplier."""
        mock_client.list.return_value = [{"id": 3, "nom": "Proveedor X"}]

        result = await service.list_thirdparties(mode="suppliers")

        mock_client.list.assert_called_once()
        call_kwargs = mock_client.list.call_args.kwargs
        assert call_kwargs.get("filters") == {"mode": "supplier"}
        assert result == [{"id": 3, "nom": "Proveedor X"}]

    async def test_list_respects_limit_and_offset(self, service, mock_client):
        """list_thirdparties pasa limit y offset al cliente."""
        mock_client.list.return_value = []

        await service.list_thirdparties(mode="all", limit=100, offset=50)

        call_kwargs = mock_client.list.call_args.kwargs
        assert call_kwargs.get("limit") == 100
        assert call_kwargs.get("offset") == 50


class TestSearchThirdparty:
    """Tests para search_thirdparty."""

    async def test_search_uses_sqlfilters_with_like_operator(self, service, mock_client):
        """search_thirdparty usa sqlfilters con operador LIKE."""
        mock_client.list.return_value = [{"id": 4, "nom": "Test Company"}]

        result = await service.search_thirdparty(name="Test")

        call_kwargs = mock_client.list.call_args.kwargs
        filters = call_kwargs.get("filters", {})
        sqlfilters = filters.get("sqlfilters", "")
        assert "like" in sqlfilters.lower()
        assert "Test" in sqlfilters
        assert result == [{"id": 4, "nom": "Test Company"}]

    async def test_search_respects_limit(self, service, mock_client):
        """search_thirdparty respeta el parámetro limit."""
        mock_client.list.return_value = []

        await service.search_thirdparty(name="Company", limit=20)

        call_kwargs = mock_client.list.call_args.kwargs
        assert call_kwargs.get("limit") == 20


class TestCreateThirdparty:
    """Tests para create_thirdparty."""

    async def test_create_sends_all_provided_fields(self, service, mock_client):
        """create_thirdparty envía todos los campos proporcionados."""
        data = {
            "name": "Nueva Empresa",
            "client": 1,
            "supplier": 0,
            "address": "Calle 123",
        }
        mock_client.create.return_value = {
            "id": 5,
            **data,
        }

        result = await service.create_thirdparty(data)

        mock_client.create.assert_called_once_with("thirdparties", data)
        assert result["id"] == 5

    async def test_create_defaults_client_and_supplier_to_0(self, service, mock_client):
        """create_thirdparty establece client y supplier a 0 si no se proporcionan."""
        data = {"name": "Empresa Genérica"}
        mock_client.create.return_value = {"id": 6, **data, "client": 0, "supplier": 0}

        await service.create_thirdparty(data)

        call_args = mock_client.create.call_args
        called_data = call_args[0][1]
        assert called_data["client"] == 0
        assert called_data["supplier"] == 0

    async def test_create_preserves_existing_flags(self, service, mock_client):
        """create_thirdparty preserva flags client y supplier si ya existen."""
        data = {"name": "Empresa", "client": 1, "supplier": 1}
        mock_client.create.return_value = {"id": 7, **data}

        await service.create_thirdparty(data)

        call_args = mock_client.create.call_args
        called_data = call_args[0][1]
        assert called_data["client"] == 1
        assert called_data["supplier"] == 1


class TestUpdateThirdparty:
    """Tests para update_thirdparty."""

    async def test_update_delegates_to_client(self, service, mock_client):
        """update_thirdparty delega al cliente."""
        data = {"name": "Nombre Actualizado"}
        mock_client.update.return_value = {"id": 8, **data}

        result = await service.update_thirdparty(8, data)

        mock_client.update.assert_called_once_with("thirdparties", 8, data)
        assert result["id"] == 8


class TestDeleteThirdparty:
    """Tests para delete_thirdparty."""

    async def test_delete_returns_true_on_success(self, service, mock_client):
        """delete_thirdparty devuelve True si la eliminación es exitosa."""
        mock_client.delete.return_value = True

        result = await service.delete_thirdparty(9)

        assert result is True

    async def test_delete_returns_false_on_400_error(self, service, mock_client):
        """delete_thirdparty devuelve False si Dolibarr rechaza con 400."""
        mock_client.delete.side_effect = IntegrationError(
            "Registros asociados",
            platform="dolibarr",
            status_code=400,
        )

        result = await service.delete_thirdparty(10)

        assert result is False

    async def test_delete_returns_false_on_403_error(self, service, mock_client):
        """delete_thirdparty devuelve False si Dolibarr rechaza con 403."""
        mock_client.delete.side_effect = IntegrationError(
            "Prohibido",
            platform="dolibarr",
            status_code=403,
        )

        result = await service.delete_thirdparty(11)

        assert result is False

    async def test_delete_reraises_other_errors(self, service, mock_client):
        """delete_thirdparty reintenta otros errores."""
        mock_client.delete.side_effect = IntegrationError(
            "Error de conexión",
            platform="dolibarr",
            status_code=500,
        )

        with pytest.raises(IntegrationError):
            await service.delete_thirdparty(12)


class TestGetThirdpartyInvoices:
    """Tests para get_thirdparty_invoices."""

    async def test_get_invoices_uses_correct_endpoint_for_customer(
        self, service, mock_client
    ):
        """get_thirdparty_invoices usa endpoint correcto para cliente."""
        mock_client.list.return_value = [{"id": 101, "type": "invoice"}]

        result = await service.get_thirdparty_invoices(
            thirdparty_id=13, type="customer"
        )

        call_args = mock_client.list.call_args
        endpoint = call_args[0][0]
        assert "thirdparties" in endpoint
        assert "13" in endpoint
        assert "invoices" in endpoint
        assert "supplierinvoices" not in endpoint

    async def test_get_invoices_uses_correct_endpoint_for_supplier(
        self, service, mock_client
    ):
        """get_thirdparty_invoices usa endpoint correcto para proveedor."""
        mock_client.list.return_value = [{"id": 102, "type": "supplier_invoice"}]

        result = await service.get_thirdparty_invoices(
            thirdparty_id=14, type="supplier"
        )

        call_args = mock_client.list.call_args
        endpoint = call_args[0][0]
        assert "thirdparties" in endpoint
        assert "14" in endpoint
        assert "supplierinvoices" in endpoint


class TestGetThirdpartyOrders:
    """Tests para get_thirdparty_orders."""

    async def test_get_orders_uses_correct_endpoint_for_customer(
        self, service, mock_client
    ):
        """get_thirdparty_orders usa endpoint correcto para cliente."""
        mock_client.list.return_value = [{"id": 201, "type": "order"}]

        result = await service.get_thirdparty_orders(thirdparty_id=15, type="customer")

        call_args = mock_client.list.call_args
        endpoint = call_args[0][0]
        assert "thirdparties" in endpoint
        assert "15" in endpoint
        assert "orders" in endpoint
        assert "supplierorders" not in endpoint

    async def test_get_orders_uses_correct_endpoint_for_supplier(
        self, service, mock_client
    ):
        """get_thirdparty_orders usa endpoint correcto para proveedor."""
        mock_client.list.return_value = [{"id": 202, "type": "supplier_order"}]

        result = await service.get_thirdparty_orders(
            thirdparty_id=16, type="supplier"
        )

        call_args = mock_client.list.call_args
        endpoint = call_args[0][0]
        assert "thirdparties" in endpoint
        assert "16" in endpoint
        assert "supplierorders" in endpoint
