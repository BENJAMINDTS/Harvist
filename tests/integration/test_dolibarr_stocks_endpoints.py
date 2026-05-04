"""
Tests de integración para los endpoints /api/v1/dolibarr/stocks.

Verifica:
- 503 cuando Dolibarr no está configurado
- Listado paginado de almacenes
- GET almacén por ID con 404 para ID inexistente
- GET stock de producto con desglose
- Listado de movimientos con filtros
- POST movimiento: validación qty=0 → 422
- POST movimiento: validación movement_type inválido → 422
- POST movimiento: creación exitosa
- POST transferencia: validación warehouses iguales → 422
- POST transferencia: validación qty <= 0 → 422
- POST transferencia: creación exitosa con dos movimientos

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-32-chars-long-enough")
os.environ.setdefault("BROWSER_BINARY_PATH", "/usr/bin/google-chrome")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

from api.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from api.main import app  # noqa: E402
from services.integrations.base import IntegrationError  # noqa: E402

_BASE = "/api/v1/dolibarr/stocks"


def _mock_settings(configured: bool = True) -> MagicMock:
    """Crea un mock de Settings con Dolibarr configurado o no."""
    s = MagicMock()
    s.dolibarr_configured = configured
    s.dolibarr_url = "https://dolibarr.test" if configured else ""
    s.dolibarr_api_key = "test-key" if configured else ""
    return s


def _mock_stock_svc(
    list_warehouses_return=None,
    get_warehouse_return=None,
    get_stock_return=None,
    get_movements_return=None,
    add_movement_return=None,
    transfer_return=None,
    add_movement_exc=None,
    transfer_exc=None,
) -> MagicMock:
    """Construye un mock completo de DolibarrStockService."""
    svc = MagicMock()
    svc.list_warehouses = AsyncMock(return_value=list_warehouses_return or [])
    svc.get_warehouse = AsyncMock(return_value=get_warehouse_return or {"id": 1})
    svc.get_product_stock = AsyncMock(
        return_value=get_stock_return or {"stock_total": 100.0, "warehouses": []}
    )
    svc.get_stock_movements = AsyncMock(return_value=get_movements_return or [])
    svc.add_stock_movement = AsyncMock(return_value=add_movement_return or {"id": 1})
    svc.transfer_stock = AsyncMock(return_value=transfer_return or {})

    if add_movement_exc:
        svc.add_stock_movement = AsyncMock(side_effect=add_movement_exc)
    if transfer_exc:
        svc.transfer_stock = AsyncMock(side_effect=transfer_exc)

    return svc


@pytest_asyncio.fixture
async def http_client() -> AsyncClient:
    """Cliente HTTP async para la app FastAPI."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


class TestNotConfigured:
    """503 cuando Dolibarr no está configurado."""

    def _not_configured_patch(self):
        return patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(configured=False),
        )

    @pytest.mark.asyncio
    async def test_list_warehouses_503(self, http_client: AsyncClient):
        """GET /warehouses retorna 503 cuando no configurado."""
        with self._not_configured_patch():
            resp = await http_client.get(f"{_BASE}/warehouses")
            assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_get_product_stock_503(self, http_client: AsyncClient):
        """GET /products/{id} retorna 503 cuando no configurado."""
        with self._not_configured_patch():
            resp = await http_client.get(f"{_BASE}/products/1")
            assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_list_movements_503(self, http_client: AsyncClient):
        """GET /movements retorna 503 cuando no configurado."""
        with self._not_configured_patch():
            resp = await http_client.get(f"{_BASE}/movements")
            assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_add_movement_503(self, http_client: AsyncClient):
        """POST /movements retorna 503 cuando no configurado."""
        with self._not_configured_patch():
            resp = await http_client.post(
                f"{_BASE}/movements",
                json={
                    "product_id": 1,
                    "warehouse_id": 1,
                    "qty": 10,
                    "movement_type": 0,
                },
            )
            assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_transfer_503(self, http_client: AsyncClient):
        """POST /transfer retorna 503 cuando no configurado."""
        with self._not_configured_patch():
            resp = await http_client.post(
                f"{_BASE}/transfer",
                json={
                    "product_id": 1,
                    "from_warehouse_id": 1,
                    "to_warehouse_id": 2,
                    "qty": 10,
                },
            )
            assert resp.status_code == 503


class TestListWarehouses:
    """Tests para GET /warehouses."""

    @pytest.mark.asyncio
    async def test_list_warehouses_success(self, http_client: AsyncClient):
        """GET /warehouses retorna lista paginada."""
        svc = _mock_stock_svc(
            list_warehouses_return=[{"id": 1, "label": "Main"}]
        )
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "api.v1.endpoints.dolibarr._get_stock_service", return_value=svc
        ):
            resp = await http_client.get(f"{_BASE}/warehouses")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert len(data["data"]["items"]) == 1


class TestGetWarehouse:
    """Tests para GET /warehouses/{warehouse_id}."""

    @pytest.mark.asyncio
    async def test_get_warehouse_success(self, http_client: AsyncClient):
        """GET /warehouses/{id} retorna almacén."""
        svc = _mock_stock_svc(get_warehouse_return={"id": 5, "label": "Storage"})
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "api.v1.endpoints.dolibarr._get_stock_service", return_value=svc
        ):
            resp = await http_client.get(f"{_BASE}/warehouses/5")
            assert resp.status_code == 200
            assert resp.json()["data"]["id"] == 5

    @pytest.mark.asyncio
    async def test_get_warehouse_404(self, http_client: AsyncClient):
        """GET /warehouses/{id} retorna 404 si no existe."""
        exc = IntegrationError("Not found", status_code=404)
        svc = _mock_stock_svc()
        svc.get_warehouse = AsyncMock(side_effect=exc)
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "api.v1.endpoints.dolibarr._get_stock_service", return_value=svc
        ):
            resp = await http_client.get(f"{_BASE}/warehouses/999")
            assert resp.status_code == 404


class TestGetProductStock:
    """Tests para GET /products/{product_id}."""

    @pytest.mark.asyncio
    async def test_get_product_stock_success(self, http_client: AsyncClient):
        """GET /products/{id} retorna stock con desglose."""
        svc = _mock_stock_svc(
            get_stock_return={
                "stock_total": 100.0,
                "warehouses": [
                    {"warehouse_id": 1, "warehouse_label": "Main", "qty": 100.0},
                ],
            }
        )
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "api.v1.endpoints.dolibarr._get_stock_service", return_value=svc
        ):
            resp = await http_client.get(f"{_BASE}/products/10")
            assert resp.status_code == 200
            assert resp.json()["data"]["stock_total"] == 100.0


class TestListMovements:
    """Tests para GET /movements."""

    @pytest.mark.asyncio
    async def test_list_movements_success(self, http_client: AsyncClient):
        """GET /movements retorna lista paginada."""
        svc = _mock_stock_svc(
            get_movements_return=[{"id": 1, "qty": 10.0}]
        )
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "api.v1.endpoints.dolibarr._get_stock_service", return_value=svc
        ):
            resp = await http_client.get(f"{_BASE}/movements")
            assert resp.status_code == 200
            assert len(resp.json()["data"]["items"]) == 1

    @pytest.mark.asyncio
    async def test_list_movements_with_filters(self, http_client: AsyncClient):
        """GET /movements pasa filtros al servicio."""
        svc = _mock_stock_svc(get_movements_return=[])
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "api.v1.endpoints.dolibarr._get_stock_service", return_value=svc
        ):
            resp = await http_client.get(
                f"{_BASE}/movements?product_id=5&warehouse_id=2"
            )
            assert resp.status_code == 200
            svc.get_stock_movements.assert_called_once()
            call_args = svc.get_stock_movements.call_args
            assert call_args[1]["product_id"] == 5
            assert call_args[1]["warehouse_id"] == 2


class TestAddMovement:
    """Tests para POST /movements."""

    @pytest.mark.asyncio
    async def test_add_movement_success(self, http_client: AsyncClient):
        """POST /movements crea movimiento exitosamente."""
        svc = _mock_stock_svc(
            add_movement_return={"id": 100, "qty": 10.0}
        )
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "api.v1.endpoints.dolibarr._get_stock_service", return_value=svc
        ):
            resp = await http_client.post(
                f"{_BASE}/movements",
                json={
                    "product_id": 1,
                    "warehouse_id": 1,
                    "qty": 10.0,
                    "movement_type": 0,
                },
            )
            assert resp.status_code == 201
            assert resp.json()["data"]["id"] == 100

    @pytest.mark.asyncio
    async def test_add_movement_qty_zero_422(self, http_client: AsyncClient):
        """POST /movements retorna 422 si qty == 0."""
        exc = ValueError("qty cannot be zero")
        svc = _mock_stock_svc(add_movement_exc=exc)
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "api.v1.endpoints.dolibarr._get_stock_service", return_value=svc
        ):
            resp = await http_client.post(
                f"{_BASE}/movements",
                json={
                    "product_id": 1,
                    "warehouse_id": 1,
                    "qty": 0,
                    "movement_type": 0,
                },
            )
            assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_add_movement_invalid_type_422(self, http_client: AsyncClient):
        """POST /movements retorna 422 para movement_type inválido."""
        exc = ValueError("movement_type must be 0, 1, 2, or 3")
        svc = _mock_stock_svc(add_movement_exc=exc)
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "api.v1.endpoints.dolibarr._get_stock_service", return_value=svc
        ):
            resp = await http_client.post(
                f"{_BASE}/movements",
                json={
                    "product_id": 1,
                    "warehouse_id": 1,
                    "qty": 10.0,
                    "movement_type": 99,
                },
            )
            assert resp.status_code == 422


class TestTransferStock:
    """Tests para POST /transfer."""

    @pytest.mark.asyncio
    async def test_transfer_success(self, http_client: AsyncClient):
        """POST /transfer transfiere stock exitosamente."""
        svc = _mock_stock_svc(
            transfer_return={
                "out_movement": {"id": 101},
                "in_movement": {"id": 102},
            }
        )
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "api.v1.endpoints.dolibarr._get_stock_service", return_value=svc
        ):
            resp = await http_client.post(
                f"{_BASE}/transfer",
                json={
                    "product_id": 1,
                    "from_warehouse_id": 1,
                    "to_warehouse_id": 2,
                    "qty": 10.0,
                },
            )
            assert resp.status_code == 201
            assert "out_movement" in resp.json()["data"]
            assert "in_movement" in resp.json()["data"]

    @pytest.mark.asyncio
    async def test_transfer_same_warehouse_422(self, http_client: AsyncClient):
        """POST /transfer retorna 422 si from == to."""
        exc = ValueError("from_warehouse_id and to_warehouse_id cannot be the same")
        svc = _mock_stock_svc(transfer_exc=exc)
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "api.v1.endpoints.dolibarr._get_stock_service", return_value=svc
        ):
            resp = await http_client.post(
                f"{_BASE}/transfer",
                json={
                    "product_id": 1,
                    "from_warehouse_id": 1,
                    "to_warehouse_id": 1,
                    "qty": 10.0,
                },
            )
            assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_transfer_invalid_qty_422(self, http_client: AsyncClient):
        """POST /transfer retorna 422 si qty <= 0."""
        exc = ValueError("qty must be greater than 0 for transfers")
        svc = _mock_stock_svc(transfer_exc=exc)
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(),
        ), patch(
            "api.v1.endpoints.dolibarr._get_stock_service", return_value=svc
        ):
            resp = await http_client.post(
                f"{_BASE}/transfer",
                json={
                    "product_id": 1,
                    "from_warehouse_id": 1,
                    "to_warehouse_id": 2,
                    "qty": 0,
                },
            )
            assert resp.status_code == 422
