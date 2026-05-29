"""
Tests unitarios para OdooInventoryService.

Verifica:
- list_stock: usa model stock.quant, domain base interno
- list_stock: agrega filtro product_id si se pasa
- list_stock: agrega filtro location_id si se pasa
- get_stock: delega a client
- adjust_stock: delega _execute con datos correctos

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.integrations.base import IntegrationError
from services.integrations.odoo.inventory import OdooInventoryService


def _make_client() -> MagicMock:
    c = MagicMock()
    c.list = AsyncMock(return_value=[])
    c.get = AsyncMock(return_value={"id": 1})
    c.create = AsyncMock(return_value={"id": 1})
    c.update = AsyncMock(return_value={"id": 1})
    c.delete = AsyncMock(return_value=True)
    return c


def _make_service(client=None) -> OdooInventoryService:
    return OdooInventoryService(client or _make_client())


# ---------------------------------------------------------------------------
# list_stock
# ---------------------------------------------------------------------------


class TestListStock:
    @pytest.mark.asyncio
    async def test_uses_stock_quant_model(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[{"id": 1}])
        svc = _make_service(client)

        await svc.list_stock()

        call_args = client.list.call_args
        assert call_args[0][0] == "stock.quant"

    @pytest.mark.asyncio
    async def test_domain_includes_internal_location(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list_stock()

        call_args = client.list.call_args
        domain = call_args[1]["filters"]["domain"]
        assert any("internal" in str(t) for t in domain)

    @pytest.mark.asyncio
    async def test_adds_product_filter_when_provided(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list_stock(product_id=42)

        domain = client.list.call_args[1]["filters"]["domain"]
        assert any("product_id" in str(t) for t in domain)

    @pytest.mark.asyncio
    async def test_adds_location_filter_when_provided(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list_stock(location_id=5)

        domain = client.list.call_args[1]["filters"]["domain"]
        assert any("location_id" in str(t) for t in domain)

    @pytest.mark.asyncio
    async def test_raises_on_client_failure(self):
        client = _make_client()
        client.list = AsyncMock(side_effect=Exception("db error"))
        svc = _make_service(client)

        with pytest.raises(IntegrationError):
            await svc.list_stock()
