"""
Tests unitarios para DolibarrStockService.

Verifica:
- list_warehouses: delegación correcta a client.list
- get_warehouse: obtiene almacén por ID
- get_product_stock: desglose de stock por almacén
- get_stock_for_products: itera sobre IDs llamando get_product_stock
- add_stock_movement: validación qty != 0 antes de API
- add_stock_movement: validación movement_type en 0-3
- get_stock_movements: filtros product_id y warehouse_id
- transfer_stock: dos movimientos (salida + entrada)
- transfer_stock: validación from == to
- transfer_stock: validación qty > 0

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.integrations.dolibarr.stocks import DolibarrStockService


def _make_client() -> MagicMock:
    """Construye un mock de DolibarrClient con métodos async."""
    client = MagicMock()
    client.list = AsyncMock(return_value=[])
    client.get = AsyncMock(return_value={"id": 1})
    client.create = AsyncMock(return_value={"id": 1})
    return client


def _make_service(client: MagicMock | None = None) -> DolibarrStockService:
    """Construye DolibarrStockService con un client mock."""
    return DolibarrStockService(client or _make_client())


class TestListWarehouses:
    """Tests para list_warehouses."""

    @pytest.mark.asyncio
    async def test_calls_client_list_warehouses(self):
        """list_warehouses llama a client.list con resource='warehouses'."""
        client = _make_client()
        client.list = AsyncMock(return_value=[{"id": 1, "label": "Main"}])
        svc = _make_service(client)

        result = await svc.list_warehouses(limit=20, offset=5)

        client.list.assert_called_once_with("warehouses", limit=20, offset=5)
        assert len(result) == 1
        assert result[0]["label"] == "Main"


class TestGetWarehouse:
    """Tests para get_warehouse."""

    @pytest.mark.asyncio
    async def test_gets_warehouse_by_id(self):
        """get_warehouse obtiene almacén por ID."""
        client = _make_client()
        client.get = AsyncMock(return_value={"id": 5, "label": "Storage"})
        svc = _make_service(client)

        result = await svc.get_warehouse(5)

        client.get.assert_called_once_with("warehouses", 5)
        assert result["id"] == 5


class TestGetProductStock:
    """Tests para get_product_stock."""

    @pytest.mark.asyncio
    async def test_returns_stock_total_and_warehouse_breakdown(self):
        """get_product_stock retorna stock_total y desglose."""
        client = _make_client()
        client.get = AsyncMock(
            return_value={
                "id": 10,
                "stock": 100.0,
                "warehouses": [
                    {"id": 1, "label": "Main", "qty": 60.0},
                    {"id": 2, "label": "Secondary", "qty": 40.0},
                ],
            }
        )
        svc = _make_service(client)

        result = await svc.get_product_stock(10)

        assert result["stock_total"] == 100.0
        assert len(result["warehouses"]) == 2
        assert result["warehouses"][0]["warehouse_label"] == "Main"


class TestGetStockForProducts:
    """Tests para get_stock_for_products."""

    @pytest.mark.asyncio
    async def test_calls_get_product_stock_for_each_id(self):
        """get_stock_for_products llama a get_product_stock para cada ID."""
        client = _make_client()
        client.get = AsyncMock(
            side_effect=[
                {"id": 1, "stock": 50.0, "warehouses": []},
                {"id": 2, "stock": 30.0, "warehouses": []},
            ]
        )
        svc = _make_service(client)

        result = await svc.get_stock_for_products([1, 2])

        assert len(result) == 2
        assert 1 in result
        assert 2 in result
        assert client.get.call_count == 2


class TestAddStockMovement:
    """Tests para add_stock_movement."""

    @pytest.mark.asyncio
    async def test_raises_valueerror_when_qty_is_zero(self):
        """add_stock_movement lanza ValueError si qty == 0."""
        svc = _make_service()

        with pytest.raises(ValueError, match="qty cannot be zero"):
            await svc.add_stock_movement(
                product_id=1,
                warehouse_id=1,
                qty=0,
                movement_type=0,
            )

    @pytest.mark.asyncio
    async def test_raises_valueerror_for_invalid_movement_type(self):
        """add_stock_movement lanza ValueError para movement_type inválido."""
        svc = _make_service()

        with pytest.raises(ValueError, match="movement_type must be"):
            await svc.add_stock_movement(
                product_id=1,
                warehouse_id=1,
                qty=10.0,
                movement_type=5,
            )

    @pytest.mark.asyncio
    async def test_creates_movement_with_valid_data(self):
        """add_stock_movement crea movimiento con datos válidos."""
        client = _make_client()
        client.create = AsyncMock(return_value={"id": 100, "qty": 10.0})
        svc = _make_service(client)

        result = await svc.add_stock_movement(
            product_id=1,
            warehouse_id=2,
            qty=10.0,
            movement_type=0,
            label="Test",
        )

        client.create.assert_called_once()
        call_args = client.create.call_args
        assert call_args[0][0] == "stockmovements"
        assert call_args[0][1]["product_id"] == 1
        assert call_args[0][1]["qty"] == 10.0


class TestGetStockMovements:
    """Tests para get_stock_movements."""

    @pytest.mark.asyncio
    async def test_passes_product_id_filter(self):
        """get_stock_movements pasa product_id como filtro."""
        client = _make_client()
        client.list = AsyncMock(return_value=[])
        svc = _make_service(client)

        await svc.get_stock_movements(product_id=5)

        call_args = client.list.call_args
        assert call_args[1]["filters"]["fk_product"] == 5

    @pytest.mark.asyncio
    async def test_passes_warehouse_id_filter(self):
        """get_stock_movements pasa warehouse_id como filtro."""
        client = _make_client()
        client.list = AsyncMock(return_value=[])
        svc = _make_service(client)

        await svc.get_stock_movements(warehouse_id=3)

        call_args = client.list.call_args
        assert call_args[1]["filters"]["fk_warehouse"] == 3


class TestTransferStock:
    """Tests para transfer_stock."""

    @pytest.mark.asyncio
    async def test_raises_valueerror_when_warehouses_equal(self):
        """transfer_stock lanza ValueError si from == to."""
        svc = _make_service()

        with pytest.raises(ValueError, match="cannot be the same"):
            await svc.transfer_stock(
                product_id=1,
                from_warehouse_id=5,
                to_warehouse_id=5,
                qty=10.0,
            )

    @pytest.mark.asyncio
    async def test_raises_valueerror_when_qty_zero_or_negative(self):
        """transfer_stock lanza ValueError si qty <= 0."""
        svc = _make_service()

        with pytest.raises(ValueError, match="qty must be greater than 0"):
            await svc.transfer_stock(
                product_id=1,
                from_warehouse_id=1,
                to_warehouse_id=2,
                qty=-5.0,
            )

    @pytest.mark.asyncio
    async def test_creates_two_movements(self):
        """transfer_stock crea dos movimientos (salida + entrada)."""
        client = _make_client()
        client.create = AsyncMock(
            side_effect=[
                {"id": 101, "qty": -10.0},  # out
                {"id": 102, "qty": 10.0},   # in
            ]
        )
        svc = _make_service(client)

        result = await svc.transfer_stock(
            product_id=1,
            from_warehouse_id=1,
            to_warehouse_id=2,
            qty=10.0,
        )

        assert "out_movement" in result
        assert "in_movement" in result
        assert client.create.call_count == 2
