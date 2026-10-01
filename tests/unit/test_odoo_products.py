"""
Tests unitarios para OdooProductService.

Verifica:
- list_products: delega a client con domain/fields correctos
- get_product: delega a client
- create_product: valida default_code obligatorio
- create_product: delega a client cuando datos válidos
- update_product_by_ref: 404 si producto no existe
- update_product_by_ref: delega update cuando existe
- delete_product: delega a client
- bulk_delete_products: lista vacía retorna zeros
- bulk_delete_products: resiliente a fallos parciales
- _coerce: conversiones de tipo string→bool/float/int

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.integrations.base import IntegrationError
from services.integrations.odoo.products import OdooProductService


def _make_client() -> MagicMock:
    c = MagicMock()
    c.list = AsyncMock(return_value=[])
    c.get = AsyncMock(return_value={"id": 1})
    c.create = AsyncMock(return_value={"id": 1})
    c.update = AsyncMock(return_value={"id": 1})
    c.delete = AsyncMock(return_value=True)
    return c


def _make_service(client=None) -> OdooProductService:
    return OdooProductService(client or _make_client())


# ---------------------------------------------------------------------------
# list_products
# ---------------------------------------------------------------------------


class TestListProducts:
    @pytest.mark.asyncio
    async def test_calls_client_with_product_template_model(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[{"id": 1}])
        svc = _make_service(client)

        result = await svc.list_products(limit=10, offset=0)

        client.list.assert_called_once()
        args = client.list.call_args
        assert args[0][0] == "product.template"
        assert result[0]["id"] == 1

    @pytest.mark.asyncio
    async def test_adds_name_filter_when_search_provided(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[])
        svc = _make_service(client)

        await svc.list_products(search="laptop")

        call_args = client.list.call_args
        domain = call_args[1]["filters"]["domain"]
        assert any("name" in str(t) for t in domain)

    @pytest.mark.asyncio
    async def test_raises_integration_error_on_client_failure(self):
        client = _make_client()
        client.list = AsyncMock(side_effect=Exception("network error"))
        svc = _make_service(client)

        with pytest.raises(IntegrationError):
            await svc.list_products()


# ---------------------------------------------------------------------------
# get_product
# ---------------------------------------------------------------------------


class TestGetProduct:
    @pytest.mark.asyncio
    async def test_delegates_to_client(self):
        client = _make_client()
        client.get = AsyncMock(return_value={"id": 5, "name": "TV"})
        svc = _make_service(client)

        result = await svc.get_product(5)

        client.get.assert_called_once_with("product.template", 5)
        assert result["id"] == 5

    @pytest.mark.asyncio
    async def test_raises_integration_error_on_not_found(self):
        client = _make_client()
        client.get = AsyncMock(side_effect=IntegrationError("not found", status_code=404, platform="odoo"))
        svc = _make_service(client)

        with pytest.raises(IntegrationError):
            await svc.get_product(999)


# ---------------------------------------------------------------------------
# create_product
# ---------------------------------------------------------------------------


class TestCreateProduct:
    @pytest.mark.asyncio
    async def test_raises_when_default_code_missing(self):
        svc = _make_service()
        with pytest.raises(IntegrationError, match="default_code"):
            await svc.create_product({"name": "Producto sin ref"})

    @pytest.mark.asyncio
    async def test_raises_when_default_code_empty_string(self):
        svc = _make_service()
        with pytest.raises(IntegrationError, match="default_code"):
            await svc.create_product({"name": "Prod", "default_code": "  "})

    @pytest.mark.asyncio
    async def test_delegates_create_to_client(self):
        client = _make_client()
        client.create = AsyncMock(return_value={"id": 10, "default_code": "REF-1"})
        svc = _make_service(client)

        result = await svc.create_product({"name": "Prod", "default_code": "REF-1"})

        client.create.assert_called_once_with("product.template", {"name": "Prod", "default_code": "REF-1"})
        assert result["id"] == 10


# ---------------------------------------------------------------------------
# update_product_by_ref
# ---------------------------------------------------------------------------


class TestUpdateProductByRef:
    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[])
        svc = _make_service(client)

        with pytest.raises(IntegrationError) as exc_info:
            await svc.update_product_by_ref("REF-MISSING", {"name": "Nueva"})
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_calls_update_when_product_exists(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[{"id": 7, "default_code": "REF-7"}])
        client.update = AsyncMock(return_value={"id": 7, "name": "Updated"})
        svc = _make_service(client)

        result = await svc.update_product_by_ref("REF-7", {"name": "Updated"})

        client.update.assert_called_once_with("product.template", 7, {"name": "Updated"})
        assert result["id"] == 7


# ---------------------------------------------------------------------------
# delete_product
# ---------------------------------------------------------------------------


class TestDeleteProduct:
    @pytest.mark.asyncio
    async def test_returns_true_on_success(self):
        client = _make_client()
        client.delete = AsyncMock(return_value=True)
        svc = _make_service(client)

        result = await svc.delete_product(3)

        client.delete.assert_called_once_with("product.template", 3)
        assert result is True

    @pytest.mark.asyncio
    async def test_raises_on_client_failure(self):
        client = _make_client()
        client.delete = AsyncMock(side_effect=Exception("db locked"))
        svc = _make_service(client)

        with pytest.raises(IntegrationError):
            await svc.delete_product(3)


# ---------------------------------------------------------------------------
# bulk_delete_products
# ---------------------------------------------------------------------------


class TestBulkDeleteProducts:
    @pytest.mark.asyncio
    async def test_empty_list_returns_zeros(self):
        svc = _make_service()
        result = await svc.bulk_delete_products([])
        assert result == {"deleted": 0, "failed": 0, "errors": []}

    @pytest.mark.asyncio
    async def test_counts_deleted_correctly(self):
        client = _make_client()
        client.delete = AsyncMock(return_value=True)
        svc = _make_service(client)

        result = await svc.bulk_delete_products([1, 2, 3])

        assert result["deleted"] == 3
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_resilient_to_partial_failures(self):
        client = _make_client()
        call_n = {"n": 0}

        async def _delete_one(model, product_id):
            call_n["n"] += 1
            if call_n["n"] == 2:
                raise IntegrationError("fallo", platform="odoo")
            return True

        client.delete = AsyncMock(side_effect=_delete_one)
        svc = _make_service(client)

        result = await svc.bulk_delete_products([10, 20, 30])

        assert result["deleted"] == 2
        assert result["failed"] == 1
        assert len(result["errors"]) == 1


# ---------------------------------------------------------------------------
# _coerce
# ---------------------------------------------------------------------------


class TestCoerce:
    def test_bool_true_values(self):
        for val in ("1", "true", "True", "yes", "sí", "on", "verdadero"):
            assert OdooProductService._coerce("active", val) is True

    def test_bool_false_values(self):
        for val in ("0", "false", "no", "off"):
            assert OdooProductService._coerce("active", val) is False

    def test_float_conversion(self):
        assert OdooProductService._coerce("list_price", "9,99") == pytest.approx(9.99)
        assert OdooProductService._coerce("list_price", "9.99") == pytest.approx(9.99)

    def test_int_conversion(self):
        assert OdooProductService._coerce("sale_delay", "5") == 5

    def test_empty_string_returns_false(self):
        assert OdooProductService._coerce("name", "") is False

    def test_str_passthrough(self):
        assert OdooProductService._coerce("name", "Laptop") == "Laptop"


# ---------------------------------------------------------------------------
# Compatibilidad del tipo de producto entre versiones de Odoo
# ---------------------------------------------------------------------------


_ODOO14_FIELDS = {"id", "name", "default_code", "type"}
_ODOO17_FIELDS = {"id", "name", "default_code", "type", "detailed_type"}
_ODOO18_FIELDS = {"id", "name", "default_code", "type", "is_storable"}


def _make_odoo_client(fields: set[str], records: list[dict] | None = None) -> MagicMock:
    from services.integrations.odoo.client import OdooClient

    c = MagicMock(spec=OdooClient)
    c.get_model_fields = AsyncMock(return_value=fields)
    c.list = AsyncMock(return_value=records or [])
    c.create = AsyncMock(return_value={"id": 1})
    c.update = AsyncMock(return_value={"id": 1})
    return c


class TestProductTypeCompat:
    @pytest.mark.asyncio
    async def test_list_fills_detailed_type_on_odoo18(self):
        client = _make_odoo_client(_ODOO18_FIELDS, [
            {"id": 1, "type": "consu", "is_storable": True},
            {"id": 2, "type": "service", "is_storable": False},
            {"id": 3, "type": "combo", "is_storable": False},
        ])
        result = await _make_service(client).list_products()

        assert [r["detailed_type"] for r in result] == ["product", "service", "combo"]

    @pytest.mark.asyncio
    async def test_list_fills_detailed_type_on_odoo14(self):
        client = _make_odoo_client(_ODOO14_FIELDS, [{"id": 1, "type": "product"}])
        result = await _make_service(client).list_products()

        assert result[0]["detailed_type"] == "product"

    @pytest.mark.asyncio
    async def test_list_requests_is_storable(self):
        client = _make_odoo_client(_ODOO18_FIELDS)
        await _make_service(client).list_products()

        assert "is_storable" in client.list.call_args.kwargs["filters"]["fields"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("fields", "detailed", "expected"),
        [
            (_ODOO18_FIELDS, "product", {"type": "consu", "is_storable": True}),
            (_ODOO18_FIELDS, "consu", {"type": "consu", "is_storable": False}),
            (_ODOO18_FIELDS, "service", {"type": "service", "is_storable": False}),
            (_ODOO17_FIELDS, "product", {"detailed_type": "product"}),
            (_ODOO14_FIELDS, "product", {"type": "product"}),
        ],
    )
    async def test_write_translates_type_per_version(self, fields, detailed, expected):
        client = _make_odoo_client(fields)
        await _make_service(client).update_product(5, {"detailed_type": detailed})

        assert client.update.call_args[0][2] == expected

    @pytest.mark.asyncio
    async def test_create_translates_type(self):
        client = _make_odoo_client(_ODOO18_FIELDS)
        await _make_service(client).create_product({"name": "X", "default_code": "R1", "detailed_type": "product"})

        assert client.create.call_args[0][1] == {"name": "X", "default_code": "R1", "type": "consu", "is_storable": True}


# ---------------------------------------------------------------------------
# bulk_upsert_products — categorías y lotes
# ---------------------------------------------------------------------------


_CSV_MAPPING = {"ref": "default_code", "nombre": "name", "cat": "categ_id", "sub": "subcateg_id"}


def _csv_client() -> MagicMock:
    from services.integrations.odoo.client import OdooClient

    c = MagicMock(spec=OdooClient)
    c.get_model_fields = AsyncMock(return_value=None)
    c.list = AsyncMock(return_value=[])  # ningún producto existe todavía
    c.bulk_create = AsyncMock(return_value=[])
    c.create = AsyncMock(return_value={"id": 1})
    return c


class TestBulkUpsertCategories:
    @pytest.mark.asyncio
    async def test_rows_with_and_without_subcategory_resolve_to_ids(self):
        client = _csv_client()
        rows = [
            {"ref": "A", "nombre": "Uno", "cat": "Padre", "sub": "Hija"},
            {"ref": "B", "nombre": "Dos", "cat": "Padre", "sub": ""},
        ]
        result = await _make_service(client).bulk_upsert_products(
            rows, _CSV_MAPPING, categ_name_to_id={"Padre": 5}, subcateg_pair_to_id={"Padre||Hija": 6},
        )

        sent = client.bulk_create.call_args[0][1]
        assert [d["categ_id"] for d in sent] == [6, 5]
        assert all("subcateg_id" not in d for d in sent)
        assert result["created"] == 2 and result["failed"] == 0

    @pytest.mark.asyncio
    async def test_unresolved_category_name_is_not_sent_to_odoo(self):
        client = _csv_client()
        rows = [{"ref": "A", "nombre": "Uno", "cat": "Desconocida", "sub": ""}]
        await _make_service(client).bulk_upsert_products(rows, _CSV_MAPPING, categ_name_to_id={"Padre": 5})

        assert "categ_id" not in client.bulk_create.call_args[0][1][0]

    @pytest.mark.asyncio
    async def test_public_category_without_subcategory_uses_parent(self):
        client = _csv_client()
        mapping = {"ref": "default_code", "nombre": "name", "web": "public_categ_id", "websub": "public_subcateg_id"}
        rows = [
            {"ref": "A", "nombre": "Uno", "web": "Tienda", "websub": "Perros"},
            {"ref": "B", "nombre": "Dos", "web": "Tienda", "websub": ""},
        ]
        await _make_service(client).bulk_upsert_products(
            rows, mapping, public_categ_name_to_id={"Tienda": 7}, public_subcateg_pair_to_id={"Tienda||Perros": 8},
        )

        sent = client.bulk_create.call_args[0][1]
        assert [d["public_categ_ids"] for d in sent] == [[(4, 8)], [(4, 7)]]
        assert all("public_categ_id" not in d and "public_subcateg_id" not in d for d in sent)


class TestBulkUpsertBatchFallback:
    @pytest.mark.asyncio
    async def test_failed_batch_is_retried_row_by_row(self):
        client = _csv_client()
        client.bulk_create = AsyncMock(side_effect=IntegrationError("lote rechazado"))

        async def _create(model, data):
            if data["default_code"] == "MALO":
                raise IntegrationError("Odoo error en product.template.create: ValueError: dato inválido")
            return {"id": 1}

        client.create = AsyncMock(side_effect=_create)
        rows = [{"ref": "BIEN", "nombre": "Uno"}, {"ref": "MALO", "nombre": "Dos"}, {"ref": "BIEN2", "nombre": "Tres"}]
        result = await _make_service(client).bulk_upsert_products(rows, {"ref": "default_code", "nombre": "name"})

        assert result["created"] == 2
        assert result["failed"] == 1
        assert result["errors"] == [{"row": 2, "error": "Odoo error en product.template.create: ValueError: dato inválido"}]
