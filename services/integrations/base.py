"""
Interfaz base abstracta para todos los clientes de integración ERP/CMS.
Cada plataforma implementa este contrato con su protocolo propio.
Ninguna integración importa de otra.

:author: Carlitos6712
:version: 1.0.0
"""

from abc import ABC, abstractmethod
from typing import Any


class IntegrationNotConfiguredError(Exception):
    """
    Se lanza cuando se intenta usar una integración cuyas variables
    de entorno obligatorias no están definidas.
    """


class IntegrationError(Exception):
    """
    Se lanza cuando la plataforma externa devuelve un error irrecuperable
    tras agotar los reintentos.
    """

    def __init__(
        self,
        message: str,
        platform: str = "",
        status_code: int | None = None,
    ) -> None:
        """
        Args:
            message:     descripción del error.
            platform:    nombre de la plataforma (ej: "dolibarr", "odoo").
            status_code: código HTTP de la respuesta, si aplica.
        """
        super().__init__(message)
        self.platform = platform
        self.status_code = status_code


class IntegrationClient(ABC):
    """
    Contrato común para todos los clientes de integración de Harvist.
    Define las operaciones CRUD genéricas que cada plataforma implementa.

    :author: Carlitos6712
    """

    @abstractmethod
    async def list(
        self,
        resource: str,
        limit: int = 50,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Lista recursos paginados de la plataforma.

        Args:
            resource: nombre del recurso (ej: "products", "invoices").
            limit:    número máximo de elementos a devolver.
            offset:   desplazamiento desde el inicio.
            filters:  filtros adicionales específicos de la plataforma.

        Returns:
            Lista de dicts con los recursos.
        """

    @abstractmethod
    async def get(self, resource: str, resource_id: int | str) -> dict[str, Any]:
        """
        Obtiene un recurso por su ID.

        Args:
            resource:    nombre del recurso.
            resource_id: identificador único del recurso.

        Returns:
            Dict con los datos del recurso.

        Raises:
            IntegrationError: si el recurso no existe o hay error.
        """

    @abstractmethod
    async def create(self, resource: str, data: dict) -> dict[str, Any]:
        """
        Crea un nuevo recurso en la plataforma.

        Args:
            resource: nombre del recurso.
            data:     datos del recurso a crear.

        Returns:
            Dict con el recurso creado (incluye ID asignado).
        """

    @abstractmethod
    async def update(
        self,
        resource: str,
        resource_id: int | str,
        data: dict,
    ) -> dict[str, Any]:
        """
        Actualiza un recurso existente.

        Args:
            resource:    nombre del recurso.
            resource_id: identificador del recurso a actualizar.
            data:        campos a actualizar.

        Returns:
            Dict con el recurso actualizado.
        """

    @abstractmethod
    async def delete(self, resource: str, resource_id: int | str) -> bool:
        """
        Elimina un recurso de la plataforma.

        Args:
            resource:    nombre del recurso.
            resource_id: identificador del recurso a eliminar.

        Returns:
            True si se eliminó correctamente.

        Raises:
            IntegrationError: si el recurso no existe o hay error al eliminar.
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Verifica que la conexión con la plataforma es correcta.

        Returns:
            True si la plataforma responde correctamente.

        Note:
            Nunca lanza excepciones de red — devuelve False ante cualquier fallo de conexión.
        """
