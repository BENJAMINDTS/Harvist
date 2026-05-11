"""
Servicio de gestión del Media Library de WordPress.

Sube imágenes Harvist al Media Library y las vincula a productos.

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from loguru import logger

from services.integrations.base import IntegrationError
from services.integrations.wordpress.client import WordPressClient

_ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


class WordPressMediaService:
    """
    Servicio para el Media Library de WordPress.

    Flujo para productos: imagen Harvist → subir via upload() → obtener media_id
    → asignar a producto mediante WordPressProductService.set_image().

    :author: Carlitos6712
    """

    def __init__(self, client: WordPressClient) -> None:
        """
        Args:
            client: instancia de WordPressClient ya configurada.
        """
        self._client = client

    async def list(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """
        Lista archivos del Media Library.

        Args:
            limit: elementos por página.
            offset: desplazamiento.

        Returns:
            Lista de media items con id, source_url, title, mime_type.
        """
        return await self._client.list_media(limit=limit, offset=offset)

    async def upload(self, filename: str, data: bytes, content_type: str = "") -> dict[str, Any]:
        """
        Sube un archivo al Media Library de WordPress.

        Args:
            filename: nombre del archivo (ej: "producto_001.jpg").
            data: bytes del archivo.
            content_type: MIME type. Si está vacío se detecta por extensión.

        Returns:
            Dict con el media item creado (id, source_url, etc.).

        Raises:
            ValueError: si el MIME type no está permitido.
            IntegrationError: si la subida falla.
        """
        if not content_type:
            guessed, _ = mimetypes.guess_type(filename)
            content_type = guessed or "application/octet-stream"

        if content_type not in _ALLOWED_MIME_TYPES:
            raise ValueError(
                f"MIME type '{content_type}' no permitido. "
                f"Tipos soportados: {_ALLOWED_MIME_TYPES}"
            )

        result = await self._client.upload_media(filename, content_type, data)
        logger.info(
            "Media subido a WordPress",
            extra={"media_id": result.get("id"), "filename": filename},
        )
        return result

    async def upload_from_path(self, path: Path) -> dict[str, Any]:
        """
        Sube un archivo al Media Library desde una ruta local.

        Args:
            path: ruta al archivo en disco.

        Returns:
            Dict con el media item creado.

        Raises:
            FileNotFoundError: si el archivo no existe.
            IntegrationError: si la subida falla.
        """
        if not path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {path}")
        data = path.read_bytes()
        return await self.upload(path.name, data)

    async def delete(self, media_id: int) -> bool:
        """
        Elimina un media item del Media Library.

        Args:
            media_id: ID del media item.

        Returns:
            True si se eliminó correctamente.
        """
        response = await self._client._wp_client.request(
            "DELETE",
            f"media/{media_id}",
            params={"force": "true"},
        )
        if response.status_code in (200, 204):
            logger.info("Media eliminado de WordPress", extra={"media_id": media_id})
            return True
        raise IntegrationError(
            f"Error al eliminar media {media_id}",
            platform="wordpress",
            status_code=response.status_code,
        )
