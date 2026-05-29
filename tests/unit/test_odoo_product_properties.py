"""
Tests unitarios para OdooProductPropertiesService.

Verifica:
- _generate_prop_name: genera hex de 16 chars
- _require_odoo_client: lanza si client no es OdooClient
- get_category_properties: lee definiciones de product.category via _execute
- get_product_properties: lee valores de product.template via _execute
- add_category_property: añade nueva propiedad con name hex generado

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.integrations.base import IntegrationError
from services.integrations.odoo.product_properties import OdooProductPropertiesService


def _make_odoo_client() -> MagicMock:
    """Client que pasa isinstance OdooClient."""
    from services.integrations.odoo.client import OdooClient
    client = MagicMock(spec=OdooClient)
    client._execute = AsyncMock(return_value=[
        {"product_properties_definition": [], "product_properties": []}
    ])
    return client


def _make_plain_client() -> MagicMock:
    """Client genérico que NO pasa isinstance OdooClient."""
    c = MagicMock()
    return c


def _make_service(client=None) -> OdooProductPropertiesService:
    return OdooProductPropertiesService(client or _make_odoo_client())


# ---------------------------------------------------------------------------
# _generate_prop_name
# ---------------------------------------------------------------------------


class TestGeneratePropName:
    def test_returns_hex_16_chars(self):
        name = OdooProductPropertiesService._generate_prop_name()
        assert len(name) == 16
        int(name, 16)  # must be valid hex

    def test_generates_unique_names(self):
        names = {OdooProductPropertiesService._generate_prop_name() for _ in range(10)}
        assert len(names) == 10


# ---------------------------------------------------------------------------
# _require_odoo_client
# ---------------------------------------------------------------------------


class TestRequireOdooClient:
    def test_raises_for_non_odoo_client(self):
        svc = _make_service(_make_plain_client())
        with pytest.raises(IntegrationError):
            svc._require_odoo_client()

    def test_does_not_raise_for_odoo_client(self):
        svc = _make_service(_make_odoo_client())
        svc._require_odoo_client()  # should not raise


# ---------------------------------------------------------------------------
# get_category_properties
# ---------------------------------------------------------------------------


class TestGetCategoryProperties:
    @pytest.mark.asyncio
    async def test_reads_from_product_category(self):
        client = _make_odoo_client()
        definitions = [{"name": "aabbccdd11223344", "string": "Color", "type": "char"}]
        client._execute = AsyncMock(return_value=[
            {"product_properties_definition": definitions}
        ])
        svc = _make_service(client)

        result = await svc.get_category_properties(category_id=1)

        assert result[0]["string"] == "Color"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_definitions(self):
        client = _make_odoo_client()
        client._execute = AsyncMock(return_value=[
            {"product_properties_definition": []}
        ])
        svc = _make_service(client)

        result = await svc.get_category_properties(category_id=1)

        assert result == []

    @pytest.mark.asyncio
    async def test_raises_when_category_not_found(self):
        client = _make_odoo_client()
        client._execute = AsyncMock(return_value=[])  # empty = not found
        svc = _make_service(client)

        with pytest.raises(IntegrationError) as exc_info:
            await svc.get_category_properties(category_id=999)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# get_product_properties
# ---------------------------------------------------------------------------


class TestGetProductProperties:
    @pytest.mark.asyncio
    async def test_reads_from_product_template(self):
        client = _make_odoo_client()
        props = [{"name": "abc", "string": "Color", "value": "Rojo", "type": "char"}]
        client._execute = AsyncMock(return_value=[{"product_properties": props}])
        svc = _make_service(client)

        result = await svc.get_product_properties(product_id=5)

        assert result[0]["value"] == "Rojo"

    @pytest.mark.asyncio
    async def test_raises_when_product_not_found(self):
        client = _make_odoo_client()
        client._execute = AsyncMock(return_value=[])
        svc = _make_service(client)

        with pytest.raises(IntegrationError) as exc_info:
            await svc.get_product_properties(product_id=999)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# add_category_property
# ---------------------------------------------------------------------------


class TestAddCategoryProperty:
    @pytest.mark.asyncio
    async def test_adds_property_with_generated_hex_name(self):
        client = _make_odoo_client()
        # First _execute call reads existing defs, second writes
        client._execute = AsyncMock(side_effect=[
            [{"product_properties_definition": []}],  # read
            None,  # write
        ])
        svc = _make_service(client)

        with patch.object(
            OdooProductPropertiesService, "_generate_prop_name", return_value="aabb11223344ccdd"
        ):
            result = await svc.add_category_property(
                category_id=1,
                prop_type="char",
                string="Talla",
            )

        assert result["string"] == "Talla"
        assert result["name"] == "aabb11223344ccdd"
        assert result["type"] == "char"

    @pytest.mark.asyncio
    async def test_raises_for_plain_client(self):
        svc = _make_service(_make_plain_client())

        with pytest.raises(IntegrationError):
            await svc.add_category_property(1, "char", "Color")
