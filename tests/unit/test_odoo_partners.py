"""
Tests unitarios para OdooPartnerService.

Verifica:
- _build_domain: customer/supplier/all modos
- _build_domain: agrega filtro de nombre cuando search presente
- list_partners: delega a client con dominio correcto
- get_partner: delega a client
- create_partner / update_partner / delete_partner: delegan correctamente

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.integrations.base import IntegrationError
from services.integrations.odoo.partners import OdooPartnerService


def _make_client() -> MagicMock:
    c = MagicMock()
    c.list = AsyncMock(return_value=[])
    c.get = AsyncMock(return_value={"id": 1})
    c.create = AsyncMock(return_value={"id": 1})
    c.update = AsyncMock(return_value={"id": 1})
    c.delete = AsyncMock(return_value=True)
    return c


def _make_service(client=None) -> OdooPartnerService:
    return OdooPartnerService(client or _make_client())


# ---------------------------------------------------------------------------
# _build_domain
# ---------------------------------------------------------------------------


class TestBuildDomain:
    def test_customer_mode_adds_customer_rank(self):
        svc = _make_service()
        domain = svc._build_domain("customer")
        assert ("customer_rank", ">", 0) in domain

    def test_supplier_mode_adds_supplier_rank(self):
        svc = _make_service()
        domain = svc._build_domain("supplier")
        assert ("supplier_rank", ">", 0) in domain

    def test_all_mode_no_rank_filter(self):
        svc = _make_service()
        domain = svc._build_domain("all")
        assert not any("rank" in str(t) for t in domain)

    def test_search_adds_name_filter(self):
        svc = _make_service()
        domain = svc._build_domain("all", search="Acme")
        assert any("name" in str(t) for t in domain)

    def test_always_includes_active_filter(self):
        svc = _make_service()
        domain = svc._build_domain("all")
        assert ("active", "=", True) in domain


# ---------------------------------------------------------------------------
# list_partners
# ---------------------------------------------------------------------------


class TestListPartners:
    @pytest.mark.asyncio
    async def test_uses_res_partner_model(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[{"id": 1}])
        svc = _make_service(client)

        await svc.list_partners(mode="all")

        call_args = client.list.call_args
        assert call_args[0][0] == "res.partner"

    @pytest.mark.asyncio
    async def test_raises_on_client_failure(self):
        client = _make_client()
        client.list = AsyncMock(side_effect=Exception("error"))
        svc = _make_service(client)

        with pytest.raises(IntegrationError):
            await svc.list_partners()


# ---------------------------------------------------------------------------
# get / create / update / delete
# ---------------------------------------------------------------------------


class TestPartnerCRUD:
    @pytest.mark.asyncio
    async def test_get_delegates(self):
        client = _make_client()
        client.get = AsyncMock(return_value={"id": 5, "name": "Acme"})
        svc = _make_service(client)

        result = await svc.get_partner(5)

        client.get.assert_called_once_with("res.partner", 5)
        assert result["name"] == "Acme"

    @pytest.mark.asyncio
    async def test_create_sends_data_to_client(self):
        client = _make_client()
        client.create = AsyncMock(return_value={"id": 10, "name": "Nuevo"})
        svc = _make_service(client)

        result = await svc.create_partner({"name": "Nuevo", "email": "n@test.com"})

        call_args = client.create.call_args
        assert call_args[0][0] == "res.partner"
        assert result["id"] == 10

    @pytest.mark.asyncio
    async def test_update_delegates(self):
        client = _make_client()
        client.update = AsyncMock(return_value={"id": 1, "name": "Updated"})
        svc = _make_service(client)

        result = await svc.update_partner(1, {"name": "Updated"})

        client.update.assert_called_once_with("res.partner", 1, {"name": "Updated"})
        assert result["name"] == "Updated"

    @pytest.mark.asyncio
    async def test_delete_returns_true(self):
        client = _make_client()
        client.delete = AsyncMock(return_value=True)
        svc = _make_service(client)

        result = await svc.delete_partner(3)

        client.delete.assert_called_once_with("res.partner", 3)
        assert result is True
