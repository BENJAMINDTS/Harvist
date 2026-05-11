"""
Cliente HTTP async para la API REST de WordPress / WooCommerce.

Autenticación: cabecera ``Authorization: Bearer <api_key>``.

Documentación API:
  WC  → {WP_URL}/wp-json/wc/v3/
  WP  → {WP_URL}/wp-json/wp/v2/

:author: Carlitos6712
:version: 1.1.0
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

import httpx
from loguru import logger

from api.core.config import Settings
from services.integrations.base import (
    IntegrationClient,
    IntegrationError,
    IntegrationNotConfiguredError,
)

_MAX_RETRIES = 3
_WC_PREFIX = "wp-json/wc/v3"
_WP_PREFIX = "wp-json/wp/v2"


class WordPressClient(IntegrationClient):
    """
    Cliente HTTP async para WordPress/WooCommerce.

    Implementa el contrato ``IntegrationClient`` con autenticación via
    cabecera ``Authorization: Bearer <api_key>``, reintentos exponenciales
    ante errores de red o 5xx, y paginación mediante ``per_page`` / ``page``.

    :author: Carlitos6712
    """

    def __init__(
        self,
        settings: Settings,
        override_url: str = "",
        override_consumer_key: str = "",
        override_consumer_secret: str = "",
    ) -> None:
        """
        Inicializa el cliente verificando que WordPress esté configurado.

        Prioridad:
          1. override_url / override_consumer_key / override_consumer_secret (parámetros)
          2. WORDPRESS_URL / WORDPRESS_CONSUMER_KEY / WORDPRESS_CONSUMER_SECRET (Settings)

        Auth: Basic base64(consumer_key:consumer_secret) sobre HTTPS.

        Args:
            settings: instancia de Settings con las variables de entorno.
            override_url: URL base de WordPress (opcional, sobreescribe .env).
            override_consumer_key: Consumer Key de WooCommerce (opcional).
            override_consumer_secret: Consumer Secret de WooCommerce (opcional).

        Raises:
            IntegrationNotConfiguredError: si URL, consumer_key o consumer_secret están vacíos.
        """
        url = (override_url or settings.wordpress_url or "").strip().rstrip("/")
        consumer_key = (override_consumer_key or settings.wordpress_consumer_key or "").strip()
        consumer_secret = (override_consumer_secret or settings.wordpress_consumer_secret or "").strip()

        if not url or not consumer_key or not consumer_secret:
            raise IntegrationNotConfiguredError(
                "WordPress no configurado: define WORDPRESS_URL, WORDPRESS_CONSUMER_KEY "
                "y WORDPRESS_CONSUMER_SECRET en .env o configúralos en la interfaz gráfica."
            )

        self._base_url = url
        self._consumer_key = consumer_key

        _basic = base64.b64encode(f"{consumer_key}:{consumer_secret}".encode()).decode()
        _shared_headers = {
            "Authorization": f"Basic {_basic}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        self._wc_client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=f"{url}/{_WC_PREFIX}/",
            headers=_shared_headers,
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0),
        )

        self._wp_client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=f"{url}/{_WP_PREFIX}/",
            headers=_shared_headers,
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0),
        )

        logger.info("WordPressClient inicializado", extra={"base_url": self._base_url})

    # ------------------------------------------------------------------
    # Métodos privados
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        use_wp_api: bool = False,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Ejecuta una petición HTTP con reintentos exponenciales.

        Args:
            method: verbo HTTP en mayúsculas (GET, POST, PUT, DELETE).
            path: ruta relativa al prefijo de la API.
            use_wp_api: True para usar WP REST API, False para WooCommerce API.
            **kwargs: argumentos adicionales para ``httpx.AsyncClient.request``.

        Returns:
            Respuesta HTTP de httpx.

        Raises:
            IntegrationError: si se agotan todos los reintentos.
        """
        client = self._wp_client if use_wp_api else self._wc_client
        last_exc: Exception | None = None
        last_status: int | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                response = await client.request(method, path, **kwargs)

                if response.status_code >= 500 and response.status_code != 501:
                    last_status = response.status_code
                    logger.warning(
                        f"Reintentando WordPress [{method} {path}] intento {attempt+1}/{_MAX_RETRIES} "
                        f"HTTP {response.status_code}: {response.text[:400]}",
                    )
                    await asyncio.sleep(2 ** attempt)
                    continue

                return response

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                logger.warning(
                    "Reintentando WordPress",
                    extra={"attempt": attempt, "path": path},
                )
                await asyncio.sleep(2 ** attempt)

        logger.error("WordPress no responde", extra={"path": path, "attempts": _MAX_RETRIES})

        if last_exc is not None:
            error_summary = type(last_exc).__name__
        else:
            error_summary = f"HTTP {last_status}"

        raise IntegrationError(
            f"WordPress no responde tras {_MAX_RETRIES} intentos: {error_summary}",
            platform="wordpress",
            status_code=last_status,
        )

    async def _wc_request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Alias para peticiones WooCommerce REST API."""
        return await self._request(method, path, use_wp_api=False, **kwargs)

    async def _wp_request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Alias para peticiones WordPress REST API (wp/v2)."""
        return await self._request(method, path, use_wp_api=True, **kwargs)

    # ------------------------------------------------------------------
    # Implementación del contrato IntegrationClient
    # ------------------------------------------------------------------

    async def list(
        self,
        resource: str,
        limit: int = 50,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Lista recursos paginados de WooCommerce.

        WooCommerce usa ``per_page`` y ``page`` (1-based).

        Args:
            resource: nombre del recurso (ej: "products", "orders").
            limit: número máximo de elementos por página.
            offset: desplazamiento absoluto desde el inicio.
            filters: filtros adicionales como query params.

        Returns:
            Lista de dicts con los recursos devueltos por WooCommerce.
        """
        page = (offset // limit) + 1
        params: dict[str, Any] = {"per_page": limit, "page": page}
        if filters:
            params.update(filters)

        response = await self._wc_request("GET", resource, params=params)
        if response.status_code >= 400:
            raise IntegrationError(
                f"WordPress {resource} devolvió error",
                platform="wordpress",
                status_code=response.status_code,
            )
        result: list[dict[str, Any]] = response.json()
        return result

    async def get(self, resource: str, resource_id: int | str) -> dict[str, Any]:
        """
        Obtiene un recurso por su ID.

        Args:
            resource: nombre del recurso (ej: "products").
            resource_id: identificador único del recurso.

        Returns:
            Dict con los datos del recurso.

        Raises:
            IntegrationError: si el recurso no existe (404) o hay error de red.
        """
        response = await self._wc_request("GET", f"{resource}/{resource_id}")

        if response.status_code == 404:
            raise IntegrationError(
                f"{resource} {resource_id} no encontrado",
                platform="wordpress",
                status_code=404,
            )
        if response.status_code >= 400:
            raise IntegrationError(
                f"WordPress {resource}/{resource_id} devolvió error",
                platform="wordpress",
                status_code=response.status_code,
            )
        result: dict[str, Any] = response.json()
        return result

    async def create(self, resource: str, data: dict[str, Any]) -> dict[str, Any]:
        """
        Crea un nuevo recurso en WooCommerce.

        Args:
            resource: nombre del recurso (ej: "products").
            data: datos del recurso a crear.

        Returns:
            Dict con el recurso creado, incluyendo el ID asignado.
        """
        response = await self._wc_request("POST", resource, json=data)
        if response.status_code >= 400:
            raise IntegrationError(
                f"Error al crear {resource} en WordPress",
                platform="wordpress",
                status_code=response.status_code,
            )
        result: dict[str, Any] = response.json()
        return result

    async def update(
        self,
        resource: str,
        resource_id: int | str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Actualiza un recurso existente en WooCommerce.

        Args:
            resource: nombre del recurso.
            resource_id: identificador del recurso a actualizar.
            data: campos a actualizar.

        Returns:
            Dict con el recurso actualizado.
        """
        response = await self._wc_request("PUT", f"{resource}/{resource_id}", json=data)
        if response.status_code >= 400:
            raise IntegrationError(
                f"Error al actualizar {resource}/{resource_id} en WordPress",
                platform="wordpress",
                status_code=response.status_code,
            )
        result: dict[str, Any] = response.json()
        return result

    async def delete(self, resource: str, resource_id: int | str) -> bool:
        """
        Elimina un recurso de WooCommerce (force=true para omitir papelera).

        Args:
            resource: nombre del recurso.
            resource_id: identificador del recurso a eliminar.

        Returns:
            True si el recurso se eliminó correctamente.

        Raises:
            IntegrationError: si WooCommerce devuelve un error inesperado.
        """
        response = await self._wc_request(
            "DELETE",
            f"{resource}/{resource_id}",
            params={"force": "true"},
        )
        if response.status_code in (200, 204):
            return True

        raise IntegrationError(
            f"Error al eliminar {resource} {resource_id}",
            platform="wordpress",
            status_code=response.status_code,
        )

    async def health_check(self) -> bool:
        """
        Verifica que la conexión con WordPress/WooCommerce es correcta.

        Consulta el endpoint raíz de WooCommerce REST API.
        Nunca lanza excepciones — devuelve False ante cualquier fallo.

        Returns:
            True si WooCommerce responde con HTTP 200; False en cualquier otro caso.
        """
        try:
            response = await self._wc_request("GET", "system_status")
            if response.status_code == 200:
                logger.debug("WordPress health OK", extra={"base_url": self._base_url})
                return True
            logger.warning("WordPress health falló", extra={"base_url": self._base_url})
            return False
        except Exception:
            logger.warning(
                "WordPress health falló",
                extra={"base_url": self._base_url},
                exc_info=True,
            )
            return False

    # ------------------------------------------------------------------
    # Métodos extra para WP REST API (media, settings)
    # ------------------------------------------------------------------

    async def upload_media(self, filename: str, content_type: str, data: bytes) -> dict[str, Any]:
        """
        Sube un archivo al Media Library de WordPress.

        Args:
            filename: nombre del archivo (ej: "producto_001.jpg").
            content_type: MIME type (ej: "image/jpeg").
            data: bytes del archivo.

        Returns:
            Dict con el media item creado (id, source_url, etc.).

        Raises:
            IntegrationError: si la subida falla.
        """
        response = await self._wp_client.request(
            "POST",
            "media",
            content=data,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": content_type,
            },
        )
        if response.status_code >= 400:
            raise IntegrationError(
                f"Error al subir media {filename} a WordPress",
                platform="wordpress",
                status_code=response.status_code,
            )
        result: dict[str, Any] = response.json()
        return result

    async def list_media(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """
        Lista archivos del Media Library de WordPress.

        Args:
            limit: elementos por página.
            offset: desplazamiento.

        Returns:
            Lista de media items.
        """
        page = (offset // limit) + 1
        response = await self._wp_request(
            "GET", "media", params={"per_page": limit, "page": page}
        )
        if response.status_code >= 400:
            raise IntegrationError(
                "Error al listar media de WordPress",
                platform="wordpress",
                status_code=response.status_code,
            )
        result: list[dict[str, Any]] = response.json()
        return result

    # ------------------------------------------------------------------
    # Context manager y cierre de sesión
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Cierra los clientes HTTP liberando las conexiones del pool."""
        await self._wc_client.aclose()
        await self._wp_client.aclose()

    async def __aenter__(self) -> "WordPressClient":
        """Soporte para uso como context manager async."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Cierra los clientes al salir del bloque async with."""
        await self.close()
