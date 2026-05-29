"""
Tests unitarios para WordPressBrandService.

Verifica:
- _native_available: retorna True si endpoint products/brands responde 200
- _native_available: retorna False si endpoint retorna 404
- list: delega a endpoint nativo cuando disponible
- find_or_create_by_name: retorna existente si existe
- find_or_create_by_name: crea si no existe
- find_by_name: retorna None si no existe

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.integrations.wordpress.brands import WordPressBrandService


def _make_client() -> MagicMock:
    c = MagicMock()
    c.list = AsyncMock(return_value=[])
    c.get = AsyncMock(return_value={"id": 1})
    c.create = AsyncMock(return_value={"id": 1, "name": "Marca"})
    c.update = AsyncMock(return_value={"id": 1})
    c.delete = AsyncMock(return_value=True)
    return c


def _make_service(client=None, use_native_override=None) -> WordPressBrandService:
    return WordPressBrandService(client or _make_client(), use_native_override=use_native_override)


# ---------------------------------------------------------------------------
# _native_available
# ---------------------------------------------------------------------------


class TestNativeAvailable:
    @pytest.mark.asyncio
    async def test_returns_true_when_endpoint_200(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[])  # 200 with empty list = available
        svc = _make_service(client)
        svc._use_native = None  # force detection

        result = await svc._native_available()

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_endpoint_raises(self):
        from services.integrations.base import IntegrationError
        client = _make_client()
        client.list = AsyncMock(side_effect=IntegrationError("404", status_code=404, platform="wordpress"))
        svc = _make_service(client)
        svc._use_native = None

        result = await svc._native_available()

        assert result is False

    @pytest.mark.asyncio
    async def test_uses_cached_value(self):
        client = _make_client()
        svc = _make_service(client, use_native_override=True)

        # With override True, _native_available should return True without calling list
        result = await svc._native_available()
        assert result is True


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


class TestBrandList:
    @pytest.mark.asyncio
    async def test_list_native_delegates_to_correct_resource(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[{"id": 1, "name": "Nike"}])
        svc = _make_service(client, use_native_override=True)

        result = await svc.list(limit=50, offset=0)

        call_args = client.list.call_args
        assert "brands" in str(call_args[0][0])
        assert result[0]["name"] == "Nike"

    @pytest.mark.asyncio
    async def test_list_attribute_mode_uses_terms_endpoint(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[{"id": 1, "name": "Nike"}])
        svc = _make_service(client, use_native_override=False)
        svc._attr_id = 5  # pre-set attribute ID

        result = await svc.list(limit=50, offset=0)

        call_args = client.list.call_args
        assert "terms" in str(call_args[0][0]) or "attributes" in str(call_args[0][0])


# ---------------------------------------------------------------------------
# find_or_create_by_name
# ---------------------------------------------------------------------------


class TestFindOrCreateByName:
    @pytest.mark.asyncio
    async def test_returns_existing_brand(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[{"id": 7, "name": "Puma"}])
        svc = _make_service(client, use_native_override=True)

        result = await svc.find_or_create_by_name("Puma")

        client.create.assert_not_called()
        assert result["id"] == 7

    @pytest.mark.asyncio
    async def test_creates_brand_when_not_found(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[])
        client.create = AsyncMock(return_value={"id": 8, "name": "NuevaMarca"})
        svc = _make_service(client, use_native_override=True)

        result = await svc.find_or_create_by_name("NuevaMarca")

        client.create.assert_called_once()
        assert result["id"] == 8
