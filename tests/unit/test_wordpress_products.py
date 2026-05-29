"""
Tests unitarios para WordPressProductService.

Verifica:
- list: delega a client con filtros correctos
- get: delega a client
- create / update / delete: delegan correctamente
- find_by_sku: retorna None si no existe, dict si existe
- set_image: llama update con images payload
- sync_from_harvist: crea cuando no existe, actualiza si overwrite, omite si no
- parse_csv_preview: detecta headers y retorna preview
- detect_delimiter (services.utils.csv_utils): detecta ; , \t

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.integrations.wordpress.products import WordPressProductService
from services.utils.csv_utils import decode_csv as _decode_csv, detect_delimiter as _detect_delimiter


def _make_client() -> MagicMock:
    c = MagicMock()
    c.list = AsyncMock(return_value=[])
    c.get = AsyncMock(return_value={"id": 1})
    c.create = AsyncMock(return_value={"id": 1})
    c.update = AsyncMock(return_value={"id": 1})
    c.delete = AsyncMock(return_value=True)
    return c


def _make_service(client=None) -> WordPressProductService:
    return WordPressProductService(client or _make_client())


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


class TestList:
    @pytest.mark.asyncio
    async def test_passes_status_filter(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list(status="publish")

        call_args = client.list.call_args
        assert call_args[1]["filters"]["status"] == "publish"

    @pytest.mark.asyncio
    async def test_adds_category_filter_when_provided(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list(category=5)

        filters = client.list.call_args[1]["filters"]
        assert filters["category"] == 5

    @pytest.mark.asyncio
    async def test_adds_search_filter_when_provided(self):
        client = _make_client()
        svc = _make_service(client)

        await svc.list(search="laptop")

        assert "search" in client.list.call_args[1]["filters"]


# ---------------------------------------------------------------------------
# get / create / update / delete
# ---------------------------------------------------------------------------


class TestCRUD:
    @pytest.mark.asyncio
    async def test_get_delegates(self):
        client = _make_client()
        client.get = AsyncMock(return_value={"id": 5, "name": "TV"})
        svc = _make_service(client)

        result = await svc.get(5)
        client.get.assert_called_once_with("products", 5)
        assert result["id"] == 5

    @pytest.mark.asyncio
    async def test_create_delegates(self):
        client = _make_client()
        client.create = AsyncMock(return_value={"id": 10})
        svc = _make_service(client)

        result = await svc.create({"name": "Nuevo"})
        assert client.create.call_args[0][0] == "products"
        assert result["id"] == 10

    @pytest.mark.asyncio
    async def test_update_delegates(self):
        client = _make_client()
        client.update = AsyncMock(return_value={"id": 5})
        svc = _make_service(client)

        result = await svc.update(5, {"name": "Upd"})
        assert client.update.call_args[0][1] == 5
        assert result["id"] == 5

    @pytest.mark.asyncio
    async def test_delete_delegates(self):
        client = _make_client()
        svc = _make_service(client)

        result = await svc.delete(3)
        client.delete.assert_called_once_with("products", 3)
        assert result is True


# ---------------------------------------------------------------------------
# find_by_sku
# ---------------------------------------------------------------------------


class TestFindBySku:
    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[])
        svc = _make_service(client)

        result = await svc.find_by_sku("SKU-MISSING")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_first_product(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[{"id": 7, "sku": "SKU-1"}])
        svc = _make_service(client)

        result = await svc.find_by_sku("SKU-1")

        assert result["id"] == 7


# ---------------------------------------------------------------------------
# set_image
# ---------------------------------------------------------------------------


class TestSetImage:
    @pytest.mark.asyncio
    async def test_calls_update_with_images_payload(self):
        client = _make_client()
        client.update = AsyncMock(return_value={"id": 5, "images": [{"id": 99}]})
        svc = _make_service(client)

        await svc.set_image(5, 99)

        call_args = client.update.call_args
        assert call_args[0][2] == {"images": [{"id": 99}]}


# ---------------------------------------------------------------------------
# sync_from_harvist
# ---------------------------------------------------------------------------


class TestSyncFromHarvist:
    @pytest.mark.asyncio
    async def test_creates_when_not_exists(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[])
        client.create = AsyncMock(return_value={"id": 10, "sku": "REF-A"})
        svc = _make_service(client)

        result = await svc.sync_from_harvist({"codigo": "REF-A", "nombre": "Prod A"})

        client.create.assert_called_once()
        assert result["id"] == 10

    @pytest.mark.asyncio
    async def test_skips_when_exists_and_no_overwrite(self):
        client = _make_client()
        existing = {"id": 5, "sku": "REF-B"}
        client.list = AsyncMock(return_value=[existing])
        svc = _make_service(client)

        result = await svc.sync_from_harvist({"codigo": "REF-B", "nombre": "Prod B"}, overwrite=False)

        client.update.assert_not_called()
        assert result["id"] == 5

    @pytest.mark.asyncio
    async def test_updates_when_exists_and_overwrite(self):
        client = _make_client()
        existing = {"id": 5, "sku": "REF-C"}
        client.list = AsyncMock(return_value=[existing])
        client.update = AsyncMock(return_value={"id": 5, "sku": "REF-C"})
        svc = _make_service(client)

        result = await svc.sync_from_harvist({"codigo": "REF-C", "nombre": "Prod C"}, overwrite=True)

        client.update.assert_called_once()
        assert result["id"] == 5

    @pytest.mark.asyncio
    async def test_includes_media_in_payload_when_provided(self):
        client = _make_client()
        client.list = AsyncMock(return_value=[])
        client.create = AsyncMock(return_value={"id": 11})
        svc = _make_service(client)

        await svc.sync_from_harvist({"codigo": "REF-D", "nombre": "Prod D"}, media_id=42)

        payload = client.create.call_args[0][1]
        assert payload["images"] == [{"id": 42}]


# ---------------------------------------------------------------------------
# parse_csv_preview
# ---------------------------------------------------------------------------


class TestParseCsvPreview:
    def test_detects_headers(self):
        csv_bytes = b"name;sku;price\nProd A;REF-1;9.99\nProd B;REF-2;14.99\n"
        result = WordPressProductService.parse_csv_preview(csv_bytes)

        assert "name" in result["headers"]
        assert "sku" in result["headers"]
        assert result["total_rows"] == 2

    def test_limits_preview_rows(self):
        rows = "\n".join([f"name{i};ref{i}" for i in range(10)])
        csv_bytes = f"name;sku\n{rows}\n".encode()
        result = WordPressProductService.parse_csv_preview(csv_bytes, preview_rows=3)

        assert len(result["preview"]) == 3
        assert result["total_rows"] == 10


# ---------------------------------------------------------------------------
# _detect_delimiter
# ---------------------------------------------------------------------------


class TestDetectDelimiter:
    def test_detects_semicolon(self):
        assert _detect_delimiter("a;b;c\n1;2;3") == ";"

    def test_detects_comma(self):
        assert _detect_delimiter("a,b,c\n1,2,3") == ","

    def test_detects_tab(self):
        assert _detect_delimiter("a\tb\tc\n1\t2\t3") == "\t"
