"""
Cliente HTTP async para la API REST de Dolibarr.
Gestiona autenticación, reintentos exponenciales y paginación.

Documentación API: {DOLIBARR_URL}/api/index.php/explorer

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

import asyncio
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


class DolibarrClient(IntegrationClient):
    """
    Cliente HTTP async para la API REST de Dolibarr.

    Implementa el contrato ``IntegrationClient`` con autenticación via
    cabecera ``DOLAPIKEY``, reintentos exponenciales ante fallos de red o
    errores 5xx, y paginación mediante parámetros ``limit`` / ``page``.

    :author: Carlitos6712
    """

    def __init__(self, settings: Settings, override_url: str = "", override_api_key: str = "") -> None:
        """
        Inicializa el cliente verificando que Dolibarr esté configurado.

        Prioridad:
          1. override_url / override_api_key (parámetros)
          2. DOLIBARR_URL / DOLIBARR_API_KEY (Settings)

        Args:
            settings: instancia de Settings con las variables de entorno.
            override_url: URL de Dolibarr (opcional, sobreescribe .env).
            override_api_key: API Key de Dolibarr (opcional, sobreescribe .env).

        Raises:
            IntegrationNotConfiguredError: si URL o API key están vacías.
        """
        url = (override_url or settings.dolibarr_url or "").strip()
        api_key = (override_api_key or settings.dolibarr_api_key or "").strip()

        if not url or not api_key:
            raise IntegrationNotConfiguredError(
                "Dolibarr no configurado: define DOLIBARR_URL y DOLIBARR_API_KEY en .env "
                "o configúralas en la interfaz gráfica."
            )

        self._base_url: str = url.rstrip("/")

        self._client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=self._base_url + "/api/index.php/",
            headers={
                "DOLAPIKEY": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0),
        )

        logger.info(
            "DolibarrClient inicializado",
            extra={"base_url": self._base_url},
        )

    # ------------------------------------------------------------------
    # Métodos privados
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Ejecuta una petición HTTP con reintentos exponenciales.

        Solo reintenta ante: ``httpx.TimeoutException``, ``httpx.ConnectError``
        y respuestas con ``status_code >= 500``. Los errores 4xx se propagan
        inmediatamente sin reintentar.

        Args:
            method: verbo HTTP en mayúsculas (GET, POST, PUT, DELETE).
            path:   ruta relativa al base_url (sin barra inicial).
            **kwargs: argumentos adicionales para ``httpx.AsyncClient.request``.

        Returns:
            Respuesta HTTP de httpx.

        Raises:
            IntegrationError: si se agotan todos los reintentos.
        """
        last_exc: Exception | None = None
        last_status: int | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                response = await self._client.request(method, path, **kwargs)

                if response.status_code >= 500 and response.status_code != 501:
                    last_status = response.status_code
                    last_exc = None
                    logger.warning(
                        f"Reintentando Dolibarr [{method} {path}] intento {attempt+1}/{_MAX_RETRIES} "
                        f"HTTP {response.status_code}: {response.text[:400]}",
                    )
                    await asyncio.sleep(2 ** attempt)
                    continue

                return response

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                logger.warning(
                    "Reintentando Dolibarr",
                    extra={"attempt": attempt, "path": path},
                )
                await asyncio.sleep(2 ** attempt)

        logger.error(
            "Dolibarr no responde",
            extra={"path": path, "attempts": _MAX_RETRIES},
        )

        if last_exc is not None:
            error_summary = type(last_exc).__name__
        else:
            error_summary = f"HTTP {last_status}"

        raise IntegrationError(
            f"Dolibarr no responde tras {_MAX_RETRIES} intentos: {error_summary}",
            platform="dolibarr",
            status_code=last_status,
        )

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
        Lista recursos paginados de Dolibarr.

        Dolibarr usa paginación 0-based por página (``page``), calculada como
        ``offset // limit``.

        Args:
            resource: nombre del recurso (ej: "products", "invoices").
            limit:    número máximo de elementos por página.
            offset:   desplazamiento absoluto desde el inicio.
            filters:  filtros adicionales añadidos como query params.

        Returns:
            Lista de dicts con los recursos devueltos por Dolibarr.
        """
        page = offset // limit
        params: dict[str, Any] = {"limit": limit, "page": page}
        if filters:
            params.update(filters)

        response = await self._request("GET", resource, params=params)
        if response.status_code >= 400:
            raise IntegrationError(
                f"Dolibarr {resource} devolvió error",
                platform="dolibarr",
                status_code=response.status_code,
            )
        result: list[dict[str, Any]] = response.json()
        return result

    async def get(
        self,
        resource: str,
        resource_id: int | str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Obtiene un recurso por su ID.

        Args:
            resource:    nombre del recurso (ej: "products").
            resource_id: identificador único del recurso.
            params:      query params adicionales (ej: {"includestockdata": 1}).

        Returns:
            Dict con los datos del recurso.

        Raises:
            IntegrationError: si el recurso no existe (404) o hay error de red.
        """
        response = await self._request("GET", f"{resource}/{resource_id}", params=params or {})

        if response.status_code == 404:
            raise IntegrationError(
                f"{resource} {resource_id} no encontrado",
                platform="dolibarr",
                status_code=404,
            )
        if response.status_code >= 400:
            raise IntegrationError(
                f"Dolibarr {resource}/{resource_id} devolvió error",
                platform="dolibarr",
                status_code=response.status_code,
            )
        result: dict[str, Any] = response.json()
        return result

    async def create(
        self,
        resource: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Crea un nuevo recurso en Dolibarr.

        Args:
            resource: nombre del recurso (ej: "products").
            data:     datos del recurso a crear.

        Returns:
            Dict con el recurso creado, incluyendo el ID asignado por Dolibarr.
        """
        response = await self._request("POST", resource, json=data)
        if response.status_code >= 400:
            raise IntegrationError(
                f"Error al crear {resource} en Dolibarr",
                platform="dolibarr",
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
        Actualiza un recurso existente en Dolibarr.

        Args:
            resource:    nombre del recurso.
            resource_id: identificador del recurso a actualizar.
            data:        campos a actualizar.

        Returns:
            Dict con el recurso actualizado.
        """
        response = await self._request("PUT", f"{resource}/{resource_id}", json=data)
        if response.status_code >= 400:
            raise IntegrationError(
                f"Error al actualizar {resource}/{resource_id} en Dolibarr",
                platform="dolibarr",
                status_code=response.status_code,
            )
        result: dict[str, Any] = response.json()
        return result

    async def delete(
        self,
        resource: str,
        resource_id: int | str,
    ) -> bool:
        """
        Elimina un recurso de Dolibarr.

        Args:
            resource:    nombre del recurso.
            resource_id: identificador del recurso a eliminar.

        Returns:
            True si el recurso se eliminó correctamente (200 o 204).

        Raises:
            IntegrationError: si Dolibarr devuelve un código de error inesperado.
        """
        response = await self._request("DELETE", f"{resource}/{resource_id}")

        if response.status_code in (200, 204):
            return True

        raise IntegrationError(
            f"Error al eliminar {resource} {resource_id}",
            platform="dolibarr",
            status_code=response.status_code,
        )

    async def health_check(self) -> bool:
        """
        Verifica que la conexión con Dolibarr es correcta.

        Consulta el endpoint ``/status`` de la API REST de Dolibarr.
        Nunca lanza excepciones — devuelve False ante cualquier fallo.

        Returns:
            True si Dolibarr responde con HTTP 200; False en cualquier otro caso.
        """
        try:
            response = await self._request("GET", "status")
            if response.status_code == 200:
                logger.debug(
                    "Dolibarr health OK",
                    extra={"base_url": self._base_url},
                )
                return True
            logger.warning(
                "Dolibarr health falló",
                extra={"base_url": self._base_url},
            )
            return False
        except Exception:
            logger.warning(
                "Dolibarr health falló",
                extra={"base_url": self._base_url},
                exc_info=True,
            )
            return False

    # ------------------------------------------------------------------
    # Context manager y cierre de sesión
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Cierra el cliente HTTP liberando las conexiones del pool."""
        await self._client.aclose()

    async def __aenter__(self) -> "DolibarrClient":
        """Soporte para uso como context manager async."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Cierra el cliente al salir del bloque async with."""
        await self.close()
