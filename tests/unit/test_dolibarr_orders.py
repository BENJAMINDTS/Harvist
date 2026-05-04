"""
Tests unitarios para DolibarrOrderService.

:author: BenjaminDTS
:version: 1.0.0
"""

from unittest.mock import AsyncMock

import pytest

from services.integrations.dolibarr.orders import DolibarrOrderService


@pytest.fixture
def mock_client() -> AsyncMock:
    """Fixture con cliente Dolibarr mockeado."""
    return AsyncMock()


@pytest.fixture
def service(mock_client: AsyncMock) -> DolibarrOrderService:
    """Fixture con servicio de pedidos."""
    return DolibarrOrderService(mock_client)


# ── ListOrders ──────────────────────────────────────────────────────


class TestListOrders:
    """Tests para list_orders."""

    @pytest.mark.asyncio
    async def test_list_orders_customer_uses_orders_endpoint(
        self, service: DolibarrOrderService, mock_client: AsyncMock
    ) -> None:
        """Verifica que customer usa endpoint /orders."""
        mock_client.list.return_value = [{"id": 1, "ref": "C001"}]

        result = await service.list_orders(type="customer")

        mock_client.list.assert_called_once_with("orders", limit=50, offset=0, filters=None)
        assert result == [{"id": 1, "ref": "C001"}]

    @pytest.mark.asyncio
    async def test_list_orders_supplier_uses_supplierorders_endpoint(
        self, service: DolibarrOrderService, mock_client: AsyncMock
    ) -> None:
        """Verifica que supplier usa endpoint /supplierorders."""
        mock_client.list.return_value = [{"id": 2, "ref": "S001"}]

        result = await service.list_orders(type="supplier")

        mock_client.list.assert_called_once_with("supplierorders", limit=50, offset=0, filters=None)
        assert result == [{"id": 2, "ref": "S001"}]

    @pytest.mark.asyncio
    async def test_list_orders_with_status_adds_sqlfilters(
        self, service: DolibarrOrderService, mock_client: AsyncMock
    ) -> None:
        """Verifica que status se añade como sqlfilters."""
        mock_client.list.return_value = []

        await service.list_orders(type="customer", status=1)

        call_kwargs = mock_client.list.call_args[1]
        assert "(status:1)" in call_kwargs["filters"]

    @pytest.mark.asyncio
    async def test_list_orders_with_thirdparty_id_adds_socid_filter(
        self, service: DolibarrOrderService, mock_client: AsyncMock
    ) -> None:
        """Verifica que thirdparty_id se añade como socid filter."""
        mock_client.list.return_value = []

        await service.list_orders(type="customer", thirdparty_id=42)

        call_kwargs = mock_client.list.call_args[1]
        assert "(socid:42)" in call_kwargs["filters"]

    @pytest.mark.asyncio
    async def test_list_orders_with_both_filters_combines_them(
        self, service: DolibarrOrderService, mock_client: AsyncMock
    ) -> None:
        """Verifica que status y thirdparty_id se combinan con AND."""
        mock_client.list.return_value = []

        await service.list_orders(type="customer", status=1, thirdparty_id=42)

        call_kwargs = mock_client.list.call_args[1]
        assert "(status:1)" in call_kwargs["filters"]
        assert "(socid:42)" in call_kwargs["filters"]
        assert " AND " in call_kwargs["filters"]


# ── GetOrder ────────────────────────────────────────────────────────


class TestGetOrder:
    """Tests para get_order."""

    @pytest.mark.asyncio
    async def test_get_order_customer_calls_orders_endpoint(
        self, service: DolibarrOrderService, mock_client: AsyncMock
    ) -> None:
        """Verifica que customer usa endpoint /orders."""
        mock_client.get.return_value = {"id": 1, "ref": "C001"}

        result = await service.get_order(1, type="customer")

        mock_client.get.assert_called_once_with("orders", 1)
        assert result == {"id": 1, "ref": "C001"}

    @pytest.mark.asyncio
    async def test_get_order_supplier_calls_supplierorders_endpoint(
        self, service: DolibarrOrderService, mock_client: AsyncMock
    ) -> None:
        """Verifica que supplier usa endpoint /supplierorders."""
        mock_client.get.return_value = {"id": 2, "ref": "S001"}

        result = await service.get_order(2, type="supplier")

        mock_client.get.assert_called_once_with("supplierorders", 2)
        assert result == {"id": 2, "ref": "S001"}


# ── CreateOrder ─────────────────────────────────────────────────────


class TestCreateOrder:
    """Tests para create_order."""

    @pytest.mark.asyncio
    async def test_create_order_customer_posts_to_orders(
        self, service: DolibarrOrderService, mock_client: AsyncMock
    ) -> None:
        """Verifica que customer usa endpoint /orders."""
        data = {"socid": 42, "date": 1234567890}
        mock_client.create.return_value = {"id": 1, "ref": "C001", **data}

        result = await service.create_order(data, type="customer")

        mock_client.create.assert_called_once_with("orders", data)
        assert result["id"] == 1

    @pytest.mark.asyncio
    async def test_create_order_supplier_posts_to_supplierorders(
        self, service: DolibarrOrderService, mock_client: AsyncMock
    ) -> None:
        """Verifica que supplier usa endpoint /supplierorders."""
        data = {"socid": 42, "date": 1234567890}
        mock_client.create.return_value = {"id": 2, "ref": "S001", **data}

        result = await service.create_order(data, type="supplier")

        mock_client.create.assert_called_once_with("supplierorders", data)
        assert result["id"] == 2


# ── AddOrderLine ────────────────────────────────────────────────────


class TestAddOrderLine:
    """Tests para add_order_line."""

    @pytest.mark.asyncio
    async def test_add_order_line_customer_posts_to_correct_endpoint(
        self, service: DolibarrOrderService, mock_client: AsyncMock
    ) -> None:
        """Verifica que customer usa endpoint /orders/{id}/lines."""
        line_data = {"fk_product": 10, "qty": 5, "subprice": 99.99}
        mock_client.create.return_value = {"id": 1, "fk_order": 1, **line_data}

        result = await service.add_order_line(1, line_data, type="customer")

        mock_client.create.assert_called_once_with("orders/1/lines", line_data)
        assert result["id"] == 1

    @pytest.mark.asyncio
    async def test_add_order_line_supplier_posts_to_correct_endpoint(
        self, service: DolibarrOrderService, mock_client: AsyncMock
    ) -> None:
        """Verifica que supplier usa endpoint /supplierorders/{id}/lines."""
        line_data = {"fk_product": 10, "qty": 5, "subprice": 99.99}
        mock_client.create.return_value = {"id": 2, "fk_order": 2, **line_data}

        result = await service.add_order_line(2, line_data, type="supplier")

        mock_client.create.assert_called_once_with("supplierorders/2/lines", line_data)
        assert result["id"] == 2


# ── UpdateOrderStatus ───────────────────────────────────────────────


class TestUpdateOrderStatus:
    """Tests para update_order_status."""

    @pytest.mark.asyncio
    async def test_update_order_status_1_customer_calls_validate(
        self, service: DolibarrOrderService, mock_client: AsyncMock
    ) -> None:
        """Verifica que status 1 customer llama a /validate."""
        mock_client.create.return_value = {"id": 1, "status": 1}

        await service.update_order_status(1, 1, type="customer")

        mock_client.create.assert_called_once_with("orders/1/validate", {})

    @pytest.mark.asyncio
    async def test_update_order_status_2_customer_calls_close(
        self, service: DolibarrOrderService, mock_client: AsyncMock
    ) -> None:
        """Verifica que status 2 customer llama a /close."""
        mock_client.create.return_value = {"id": 1, "status": 2}

        await service.update_order_status(1, 2, type="customer")

        mock_client.create.assert_called_once_with("orders/1/close", {})

    @pytest.mark.asyncio
    async def test_update_order_status_3_customer_calls_cancel(
        self, service: DolibarrOrderService, mock_client: AsyncMock
    ) -> None:
        """Verifica que status 3 customer llama a /cancel."""
        mock_client.create.return_value = {"id": 1, "status": 3}

        await service.update_order_status(1, 3, type="customer")

        mock_client.create.assert_called_once_with("orders/1/cancel", {})

    @pytest.mark.asyncio
    async def test_update_order_status_1_supplier_calls_validate(
        self, service: DolibarrOrderService, mock_client: AsyncMock
    ) -> None:
        """Verifica que status 1 supplier llama a /validate."""
        mock_client.create.return_value = {"id": 2, "status": 1}

        await service.update_order_status(2, 1, type="supplier")

        mock_client.create.assert_called_once_with("supplierorders/2/validate", {})

    @pytest.mark.asyncio
    async def test_update_order_status_4_supplier_calls_reception(
        self, service: DolibarrOrderService, mock_client: AsyncMock
    ) -> None:
        """Verifica que status 4 supplier llama a /reception."""
        mock_client.create.return_value = {"id": 2, "status": 4}

        await service.update_order_status(2, 4, type="supplier")

        mock_client.create.assert_called_once_with("supplierorders/2/reception", {})

    @pytest.mark.asyncio
    async def test_update_order_status_5_supplier_calls_cancel(
        self, service: DolibarrOrderService, mock_client: AsyncMock
    ) -> None:
        """Verifica que status 5 supplier llama a /cancel."""
        mock_client.create.return_value = {"id": 2, "status": 5}

        await service.update_order_status(2, 5, type="supplier")

        mock_client.create.assert_called_once_with("supplierorders/2/cancel", {})

    @pytest.mark.asyncio
    async def test_update_order_status_invalid_customer_raises_valueerror(
        self, service: DolibarrOrderService
    ) -> None:
        """Verifica que status inválido customer lanza ValueError."""
        with pytest.raises(ValueError, match="Invalid status"):
            await service.update_order_status(1, 99, type="customer")

    @pytest.mark.asyncio
    async def test_update_order_status_invalid_supplier_raises_valueerror(
        self, service: DolibarrOrderService
    ) -> None:
        """Verifica que status inválido supplier lanza ValueError."""
        with pytest.raises(ValueError, match="Invalid status"):
            await service.update_order_status(2, 99, type="supplier")


# ── DeleteOrder ─────────────────────────────────────────────────────


class TestDeleteOrder:
    """Tests para delete_order."""

    @pytest.mark.asyncio
    async def test_delete_order_customer_calls_delete(
        self, service: DolibarrOrderService, mock_client: AsyncMock
    ) -> None:
        """Verifica que customer usa endpoint /orders."""
        mock_client.delete.return_value = True

        result = await service.delete_order(1, type="customer")

        mock_client.delete.assert_called_once_with("orders", 1)
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_order_supplier_calls_delete(
        self, service: DolibarrOrderService, mock_client: AsyncMock
    ) -> None:
        """Verifica que supplier usa endpoint /supplierorders."""
        mock_client.delete.return_value = True

        result = await service.delete_order(2, type="supplier")

        mock_client.delete.assert_called_once_with("supplierorders", 2)
        assert result is True
