"""
Cliente XML-RPC async para la API de Odoo.
Usa la biblioteca estándar ``xmlrpc.client`` + ``asyncio.to_thread``
para mantener compatibilidad con FastAPI sin añadir dependencias externas.

Documentación API: https://www.odoo.com/documentation/17.0/developer/reference/external_api.html

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

import asyncio
import xmlrpc.client
from typing import Any

from loguru import logger

from api.core.config import Settings
from services.integrations.base import (
    IntegrationClient,
    IntegrationError,
    IntegrationNotConfiguredError,
)


class OdooClient(IntegrationClient):
    """
    Cliente XML-RPC async para Odoo.

    Implementa el contrato ``IntegrationClient`` usando los endpoints estándar
    de Odoo: ``/xmlrpc/2/common`` (autenticación) y ``/xmlrpc/2/object``
    (operaciones sobre modelos). La autenticación es lazy: se realiza en el
    primer uso y el uid se reutiliza en las llamadas siguientes.

    :author: Carlitos6712
    """

    def __init__(
        self,
        settings: Settings,
        override_url: str = "",
        override_db: str = "",
        override_user: str = "",
        override_password: str = "",
    ) -> None:
        """
        Inicializa el cliente verificando que Odoo esté configurado.

        Prioridad:
          1. override_* (parámetros)
          2. ODOO_URL / ODOO_DB / ODOO_USER / ODOO_PASSWORD (Settings)

        Args:
            settings: instancia de Settings con las variables de entorno.
            override_url: URL base de Odoo (opcional).
            override_db: nombre de la base de datos (opcional).
            override_user: email/login de usuario (opcional).
            override_password: contraseña del usuario (opcional).

        Raises:
            IntegrationNotConfiguredError: si algún dato obligatorio está vacío.
        """
        url = (override_url or settings.odoo_url or "").strip().rstrip("/")
        db = (override_db or settings.odoo_db or "").strip()
        user = (override_user or settings.odoo_user or "").strip()
        password = (override_password or settings.odoo_password or "").strip()

        if not url or not db or not user or not password:
            raise IntegrationNotConfiguredError(
                "Odoo no configurado: define ODOO_URL, ODOO_DB, ODOO_USER y ODOO_PASSWORD en .env "
                "o configúralos en la interfaz gráfica."
            )

        self._url = url
        self._db = db
        self._user = user
        self._password = password
        self._uid: int | None = None

        logger.info("OdooClient inicializado", extra={"url": self._url, "db": self._db})

    # ------------------------------------------------------------------
    # Autenticación lazy
    # ------------------------------------------------------------------

    async def _get_uid(self) -> int:
        """
        Obtiene el UID de sesión autenticando contra Odoo.

        La autenticación se realiza solo una vez; el resultado se cachea en ``_uid``.

        Returns:
            UID del usuario autenticado.

        Raises:
            IntegrationError: si las credenciales son incorrectas o Odoo no responde.
        """
        if self._uid is not None:
            return self._uid

        def _authenticate() -> int:
            proxy = xmlrpc.client.ServerProxy(f"{self._url}/xmlrpc/2/common")
            uid = proxy.authenticate(self._db, self._user, self._password, {})
            if not uid:
                raise IntegrationError(
                    "Credenciales Odoo incorrectas.",
                    platform="odoo",
                )
            return uid

        try:
            self._uid = await asyncio.to_thread(_authenticate)
            logger.info("Odoo autenticado", extra={"uid": self._uid})
            return self._uid
        except IntegrationError:
            raise
        except Exception as exc:
            logger.error("Error autenticando en Odoo", exc_info=exc)
            raise IntegrationError(
                f"Error autenticando en Odoo: {exc}",
                platform="odoo",
            ) from exc

    # ------------------------------------------------------------------
    # Llamada genérica execute_kw
    # ------------------------------------------------------------------

    async def _execute(
        self,
        model: str,
        method: str,
        args: list[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """
        Ejecuta una llamada ``execute_kw`` contra el endpoint de objeto de Odoo.

        Args:
            model:  nombre del modelo Odoo (ej: "product.template").
            method: método a invocar (ej: "search_read", "create", "write").
            args:   argumentos posicionales del método.
            kwargs: argumentos nombrados del método (opcional).

        Returns:
            Resultado de la llamada XML-RPC.

        Raises:
            IntegrationError: si Odoo devuelve un fallo.
        """
        uid = await self._get_uid()
        kw = kwargs or {}

        def _call() -> Any:
            proxy = xmlrpc.client.ServerProxy(f"{self._url}/xmlrpc/2/object")
            return proxy.execute_kw(self._db, uid, self._password, model, method, args, kw)

        try:
            return await asyncio.to_thread(_call)
        except xmlrpc.client.Fault as exc:
            logger.error(
                "Odoo XML-RPC fault",
                exc_info=exc,
                extra={"model": model, "method": method, "fault": exc.faultString},
            )
            raise IntegrationError(
                f"Odoo error en {model}.{method}: {exc.faultString}",
                platform="odoo",
            ) from exc
        except Exception as exc:
            logger.error(
                "Error llamando a Odoo",
                exc_info=exc,
                extra={"model": model, "method": method},
            )
            raise IntegrationError(
                f"Error llamando a Odoo {model}.{method}: {exc}",
                platform="odoo",
            ) from exc

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
        Lista registros de un modelo Odoo con paginación.

        Args:
            resource: nombre del modelo Odoo (ej: "product.template").
            limit:    número máximo de registros a devolver.
            offset:   desplazamiento desde el inicio.
            filters:  dict opcional con claves:
                      - ``domain``: lista de tuplas Odoo domain (default: [])
                      - ``fields``: lista de campos a retornar
                      - ``order``:  string de ordenación (ej: "id desc")

        Returns:
            Lista de dicts con los registros.
        """
        domain: list[Any] = (filters or {}).get("domain", [])
        fields: list[str] = (filters or {}).get("fields", [])
        order: str = (filters or {}).get("order", "id desc")

        kwargs: dict[str, Any] = {"limit": limit, "offset": offset, "order": order}
        if fields:
            kwargs["fields"] = fields

        result = await self._execute(resource, "search_read", [domain], kwargs)
        return result or []

    async def get(
        self,
        resource: str,
        resource_id: int | str,
    ) -> dict[str, Any]:
        """
        Obtiene un registro por su ID.

        Args:
            resource:    nombre del modelo Odoo.
            resource_id: ID del registro.

        Returns:
            Dict con los datos del registro.

        Raises:
            IntegrationError: si no existe o hay error.
        """
        records = await self._execute(resource, "read", [[int(resource_id)]])
        if not records:
            raise IntegrationError(
                f"{resource} {resource_id} no encontrado",
                platform="odoo",
                status_code=404,
            )
        return records[0]

    async def create(
        self,
        resource: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Crea un nuevo registro en Odoo.

        Args:
            resource: nombre del modelo.
            data:     datos del registro a crear.

        Returns:
            Dict con el registro creado incluyendo su ID.
        """
        new_id: int = await self._execute(resource, "create", [data])
        return await self.get(resource, new_id)

    async def update(
        self,
        resource: str,
        resource_id: int | str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Actualiza un registro existente en Odoo.

        Args:
            resource:    nombre del modelo.
            resource_id: ID del registro a actualizar.
            data:        campos a actualizar.

        Returns:
            Dict con el registro actualizado.
        """
        await self._execute(resource, "write", [[int(resource_id)], data])
        return await self.get(resource, resource_id)

    async def bulk_create(
        self,
        resource: str,
        data_list: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Crea múltiples registros en una sola llamada XML-RPC (Odoo 14+).

        Args:
            resource:  nombre del modelo.
            data_list: lista de dicts con los datos de cada registro.

        Returns:
            Lista de dicts con los registros creados (incluyendo ID).
        """
        new_ids: list[int] = await self._execute(resource, "create", [data_list])
        if not isinstance(new_ids, list):
            new_ids = [new_ids]
        records = await self._execute(resource, "read", [new_ids])
        return records or []

    async def delete(
        self,
        resource: str,
        resource_id: int | str,
    ) -> bool:
        """
        Elimina un registro de Odoo.

        Args:
            resource:    nombre del modelo.
            resource_id: ID del registro.

        Returns:
            True si se eliminó correctamente.
        """
        result: bool = await self._execute(resource, "unlink", [[int(resource_id)]])
        return bool(result)

    async def search_count(
        self,
        resource: str,
        domain: list[Any] | None = None,
    ) -> int:
        """
        Cuenta registros que cumplen el dominio dado.

        Args:
            resource: nombre del modelo.
            domain:   lista de tuplas de filtro Odoo (default: []).

        Returns:
            Número entero de registros.
        """
        count: int = await self._execute(resource, "search_count", [domain or []])
        return count

    async def health_check(self) -> bool:
        """
        Verifica que la conexión con Odoo es correcta.

        Intenta autenticar; devuelve False si falla sin lanzar excepción.

        Returns:
            True si Odoo responde y las credenciales son válidas.
        """
        try:
            def _version() -> dict:
                proxy = xmlrpc.client.ServerProxy(f"{self._url}/xmlrpc/2/common")
                return proxy.version()

            info = await asyncio.to_thread(_version)
            logger.debug("Odoo health OK", extra={"url": self._url, "info": info})
            return True
        except Exception:
            logger.warning("Odoo health falló", extra={"url": self._url}, exc_info=True)
            return False
