"""
Tests unitarios para DolibarrProductService.

Verifica:
- CRUD delegado correctamente al DolibarrClient
- upload_image: lectura del archivo y envío en base64
- upload_image: FileNotFoundError para ruta inexistente
- sync_from_job: crea / actualiza / omite según overwrite
- sync_from_job: sube imagen cuando existe
- sync_from_job: omite imagen cuando no existe
- sync_from_job: acción "skipped" para producto existente sin overwrite
- sync_from_job: resiliente a errores parciales (un fallo no detiene el resto)

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.integrations.base import IntegrationError
from services.integrations.dolibarr.products import DolibarrProductService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client() -> MagicMock:
    """Construye un mock de DolibarrClient con todos los métodos async."""
    client = MagicMock()
    client.list = AsyncMock(return_value=[])
    client.get = AsyncMock(return_value={"id": 1})
    client.create = AsyncMock(return_value={"id": 1})
    client.update = AsyncMock(return_value={"id": 1})
    client.delete = AsyncMock(return_value=True)
    return client


def _make_service(client: MagicMock | None = None) -> DolibarrProductService:
    """Construye DolibarrProductService con un client mock."""
    return DolibarrProductService(client or _make_client())


# ---------------------------------------------------------------------------
# list_products
# ---------------------------------------------------------------------------


class TestListProducts:
    """Tests para DolibarrProductService.list_products."""

    @pytest.mark.asyncio
    async def test_calls_client_list_with_correct_resource(self):
        """list_products llama a client.list con resource='products'."""
        client = _make_client()
        client.list = AsyncMock(return_value=[{"id": 1}])
        svc = _make_service(client)

        result = await svc.list_products(limit=10, offset=5)

        client.list.assert_called_once_with("products", limit=10, offset=5, filters=None)
        assert result == [{"id": 1}]

    @pytest.mark.asyncio
    async def test_passes_filters_to_client(self):
        """list_products pasa filters al client."""
        client = _make_client()
        svc = _make_service(client)
        filters = {"sqlfilters": "(ref:=:'ABC')"}

        await svc.list_products(filters=filters)

        client.list.assert_called_once_with("products", limit=50, offset=0, filters=filters)


# ---------------------------------------------------------------------------
# create_product
# ---------------------------------------------------------------------------


class TestCreateProduct:
    """Tests para DolibarrProductService.create_product."""

    @pytest.mark.asyncio
    async def test_calls_client_create_with_correct_data(self):
        """create_product llama a client.create con resource='products' y los datos."""
        client = _make_client()
        client.create = AsyncMock(return_value={"id": 42, "ref": "PROD-1"})
        svc = _make_service(client)
        data = {"ref": "PROD-1", "label": "Producto 1", "price": 9.99}

        result = await svc.create_product(data)

        client.create.assert_called_once_with("products", data)
        assert result["id"] == 42


# ---------------------------------------------------------------------------
# update_product
# ---------------------------------------------------------------------------


class TestUpdateProduct:
    """Tests para DolibarrProductService.update_product."""

    @pytest.mark.asyncio
    async def test_calls_client_update_with_correct_id_and_data(self):
        """update_product llama a client.update con el id y los datos correctos."""
        client = _make_client()
        client.update = AsyncMock(return_value={"id": 7, "ref": "REF-7"})
        svc = _make_service(client)
        data = {"label": "Nuevo nombre"}

        result = await svc.update_product(7, data)

        client.update.assert_called_once_with("products", 7, data)
        assert result["id"] == 7


# ---------------------------------------------------------------------------
# delete_product
# ---------------------------------------------------------------------------


class TestDeleteProduct:
    """Tests para DolibarrProductService.delete_product."""

    @pytest.mark.asyncio
    async def test_calls_client_delete_and_returns_bool(self):
        """delete_product llama a client.delete y devuelve el bool resultante."""
        client = _make_client()
        client.delete = AsyncMock(return_value=True)
        svc = _make_service(client)

        result = await svc.delete_product(3)

        client.delete.assert_called_once_with("products", 3)
        assert result is True


# ---------------------------------------------------------------------------
# upload_image
# ---------------------------------------------------------------------------


class TestUploadImage:
    """Tests para DolibarrProductService.upload_image."""

    @pytest.mark.asyncio
    async def test_reads_file_and_sends_base64_content(self, tmp_path: Path):
        """upload_image lee el archivo y envía su contenido codificado en base64."""
        image_data = b"\xff\xd8\xff\xe0fake_jpeg_bytes"
        image_file = tmp_path / "producto.jpg"
        image_file.write_bytes(image_data)

        client = _make_client()
        client.create = AsyncMock(return_value={"success": 1})
        svc = _make_service(client)

        await svc.upload_image(42, image_file)

        call_args = client.create.call_args
        resource, payload = call_args[0]
        assert resource == "documents"
        assert payload["modulepart"] == "product"
        assert payload["id"] == 42
        assert payload["filename"] == "producto.jpg"
        assert payload["fileencoding"] == "base64"
        assert payload["filecontent"] == base64.b64encode(image_data).decode("ascii")

    @pytest.mark.asyncio
    async def test_raises_filenotfounderror_for_missing_path(self):
        """upload_image lanza FileNotFoundError si image_path no existe."""
        svc = _make_service()
        missing = Path("/tmp/no_existe_en_absoluto_12345.jpg")

        with pytest.raises(FileNotFoundError):
            await svc.upload_image(1, missing)


# ---------------------------------------------------------------------------
# sync_from_job
# ---------------------------------------------------------------------------


class TestSyncFromJob:
    """Tests para DolibarrProductService.sync_from_job."""

    @pytest.mark.asyncio
    async def test_creates_product_when_not_exists(self):
        """sync_from_job crea el producto cuando no existe en Dolibarr."""
        client = _make_client()
        # _find_product_by_ref → list devuelve vacío → no existe
        client.list = AsyncMock(return_value=[])
        client.create = AsyncMock(return_value={"id": 10})
        svc = _make_service(client)

        results = await svc.sync_from_job("job-1", ["PROD-A"])

        assert len(results) == 1
        assert results[0]["codigo"] == "PROD-A"
        assert results[0]["action"] == "created"
        assert results[0]["dolibarr_id"] == 10
        assert results[0]["error"] is None

    @pytest.mark.asyncio
    async def test_skips_product_when_exists_and_overwrite_false(self):
        """sync_from_job omite el producto si ya existe y overwrite=False."""
        client = _make_client()
        client.list = AsyncMock(return_value=[{"id": 5, "ref": "PROD-B"}])
        svc = _make_service(client)

        results = await svc.sync_from_job("job-1", ["PROD-B"], overwrite=False)

        assert results[0]["action"] == "skipped"
        assert results[0]["dolibarr_id"] == 5
        client.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_updates_product_when_exists_and_overwrite_true(self):
        """sync_from_job actualiza el producto si ya existe y overwrite=True."""
        client = _make_client()
        client.list = AsyncMock(return_value=[{"id": 7, "ref": "PROD-C"}])
        client.update = AsyncMock(return_value={"id": 7})
        svc = _make_service(client)

        results = await svc.sync_from_job("job-1", ["PROD-C"], overwrite=True)

        assert results[0]["action"] == "updated"
        assert results[0]["dolibarr_id"] == 7
        client.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_uploads_image_when_image_file_exists(self, tmp_path: Path):
        """sync_from_job sube la imagen cuando existe el archivo para el producto."""
        client = _make_client()
        client.list = AsyncMock(return_value=[])
        client.create = AsyncMock(side_effect=[{"id": 20}, {"success": 1}])
        svc = _make_service(client)

        storage = MagicMock()
        job_dir = tmp_path / "job-img"
        job_dir.mkdir()
        image_file = job_dir / "PROD-D.jpg"
        image_file.write_bytes(b"\xff\xd8fake")
        storage.get_job_dir = MagicMock(return_value=job_dir)

        results = await svc.sync_from_job("job-img", ["PROD-D"], storage=storage)

        assert results[0]["action"] == "created"
        assert client.create.call_count == 2
        docs_call = client.create.call_args_list[1]
        assert docs_call[0][0] == "documents"

    @pytest.mark.asyncio
    async def test_skips_image_upload_when_no_image_for_product(self, tmp_path: Path):
        """sync_from_job no llama upload_image si no hay imagen para el producto."""
        client = _make_client()
        client.list = AsyncMock(return_value=[])
        client.create = AsyncMock(return_value={"id": 30})
        svc = _make_service(client)

        storage = MagicMock()
        storage.get_job_dir = MagicMock(return_value=tmp_path)

        results = await svc.sync_from_job("job-no-img", ["PROD-E"], storage=storage)

        assert results[0]["action"] == "created"
        assert client.create.call_count == 1

    @pytest.mark.asyncio
    async def test_returns_skipped_action_for_existing_no_overwrite(self):
        """sync_from_job retorna action='skipped' para producto existente sin overwrite."""
        client = _make_client()
        client.list = AsyncMock(return_value=[{"id": 99, "ref": "PROD-F"}])
        svc = _make_service(client)

        results = await svc.sync_from_job("job-1", ["PROD-F"], overwrite=False)

        assert results[0]["action"] == "skipped"
        assert results[0]["dolibarr_id"] == 99

    @pytest.mark.asyncio
    async def test_resilient_to_partial_errors(self):
        """sync_from_job continúa con los demás productos cuando uno falla."""
        client = _make_client()
        call_count = 0

        # list siempre devuelve vacío → ningún producto existe
        client.list = AsyncMock(return_value=[])

        async def _create_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise IntegrationError("fallo de red", platform="dolibarr")
            return {"id": 55}

        client.create = AsyncMock(side_effect=_create_side_effect)
        svc = _make_service(client)

        results = await svc.sync_from_job("job-1", ["PROD-FAIL", "PROD-OK"])

        assert len(results) == 2
        fail = next(r for r in results if r["codigo"] == "PROD-FAIL")
        ok = next(r for r in results if r["codigo"] == "PROD-OK")
        assert fail["error"] is not None
        assert ok["action"] == "created"
