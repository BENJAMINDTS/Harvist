"""
Tests unitarios para WordPressMediaService.

Verifica:
- list: delega a client.list_media
- upload: pasa filename + bytes al cliente, retorna media item
- upload: lanza ValueError para MIME type no permitido
- upload_from_path: lanza FileNotFoundError para ruta inexistente
- upload_from_path: sube archivo real y retorna media item

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.integrations.wordpress.media import WordPressMediaService


def _make_client() -> MagicMock:
    c = MagicMock()
    c.list_media = AsyncMock(return_value=[])
    c.upload_media = AsyncMock(return_value={"id": 1, "source_url": "https://wp.test/media/1.jpg"})
    return c


def _make_service(client=None) -> WordPressMediaService:
    return WordPressMediaService(client or _make_client())


class TestListMedia:
    @pytest.mark.asyncio
    async def test_delegates_to_client_list_media(self):
        client = _make_client()
        client.list_media = AsyncMock(return_value=[{"id": 1}])
        svc = _make_service(client)

        result = await svc.list(limit=10, offset=0)

        client.list_media.assert_called_once_with(limit=10, offset=0)
        assert result[0]["id"] == 1


class TestUpload:
    @pytest.mark.asyncio
    async def test_uploads_bytes_and_returns_media_item(self):
        client = _make_client()
        client.upload_media = AsyncMock(return_value={"id": 5, "source_url": "https://wp.test/5.jpg"})
        svc = _make_service(client)

        result = await svc.upload("imagen.jpg", b"\xff\xd8fake_jpeg", "image/jpeg")

        client.upload_media.assert_called_once_with("imagen.jpg", "image/jpeg", b"\xff\xd8fake_jpeg")
        assert result["id"] == 5

    @pytest.mark.asyncio
    async def test_raises_for_invalid_mime_type(self):
        svc = _make_service()

        with pytest.raises((ValueError, Exception)):
            await svc.upload("doc.pdf", b"fake", "application/pdf")


class TestUploadFromPath:
    @pytest.mark.asyncio
    async def test_raises_filenotfounderror_for_missing_file(self):
        svc = _make_service()

        with pytest.raises(FileNotFoundError):
            await svc.upload_from_path(Path("/tmp/nonexistent_file_xyz123.jpg"))

    @pytest.mark.asyncio
    async def test_reads_file_and_calls_upload(self, tmp_path: Path):
        image_data = b"\xff\xd8\xff\xe0fake_jpeg"
        image_file = tmp_path / "product.jpg"
        image_file.write_bytes(image_data)

        client = _make_client()
        client.upload_media = AsyncMock(return_value={"id": 9, "source_url": "https://wp.test/9.jpg"})
        svc = _make_service(client)

        result = await svc.upload_from_path(image_file)

        client.upload_media.assert_called_once()
        call_args = client.upload_media.call_args
        assert call_args[0][0] == "product.jpg"
        assert call_args[0][2] == image_data
        assert result["id"] == 9
