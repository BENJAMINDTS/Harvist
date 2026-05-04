"""
Módulo de gestión de terceros (clientes y proveedores) en Dolibarr.

En Dolibarr, clientes y proveedores son el mismo objeto 'societe'.
La distinción se hace con los flags client=1 y supplier=1.
Un tercero puede ser cliente Y proveedor a la vez.

:author: Carlitos6712
:version: 1.0.0
"""

from typing import Any, Literal

from loguru import logger

from services.integrations.base import IntegrationError
from services.integrations.dolibarr.client import DolibarrClient

ThirdpartyMode = Literal["all", "customers", "suppliers"]

_DOLIBARR_THIRDPARTIES_RESOURCE = "thirdparties"
_DOLIBARR_INVOICES_RESOURCE = "invoices"
_DOLIBARR_SUPPLIER_INVOICES_RESOURCE = "supplierinvoices"
_DOLIBARR_ORDERS_RESOURCE = "orders"
_DOLIBARR_SUPPLIER_ORDERS_RESOURCE = "supplierorders"


class DolibarrThirdpartyService:
    """
    Servicio de gestión de terceros (clientes y proveedores) en Dolibarr.

    Encapsula todas las operaciones CRUD sobre terceros, búsqueda,
    y consulta de facturas y pedidos asociados.

    :author: Carlitos6712
    """

    def __init__(self, client: DolibarrClient) -> None:
        """
        Args:
            client: instancia de DolibarrClient configurada y lista para usar.
        """
        self._client = client

    async def list_thirdparties(
        self,
        mode: ThirdpartyMode = "all",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Lista terceros filtrando por modo.

        Args:
            mode: Modo de filtro:
                  - "all"       → GET /thirdparties (sin filtro)
                  - "customers" → GET /thirdparties?mode=customer
                  - "suppliers" → GET /thirdparties?mode=supplier
            limit: número máximo de terceros por página.
            offset: desplazamiento desde el inicio.

        Returns:
            Lista de dicts con los terceros devueltos por Dolibarr.
        """
        filters = None
        if mode == "customers":
            filters = {"mode": "customer"}
        elif mode == "suppliers":
            filters = {"mode": "supplier"}

        return await self._client.list(
            _DOLIBARR_THIRDPARTIES_RESOURCE,
            limit=limit,
            offset=offset,
            filters=filters,
        )

    async def get_thirdparty(self, thirdparty_id: int) -> dict[str, Any]:
        """
        Obtiene un tercero por ID.

        Args:
            thirdparty_id: ID del tercero en Dolibarr.

        Returns:
            Dict con los datos del tercero.

        Raises:
            IntegrationError: si el tercero no existe o hay error de comunicación.
        """
        return await self._client.get(_DOLIBARR_THIRDPARTIES_RESOURCE, thirdparty_id)

    async def search_thirdparty(
        self,
        name: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Busca terceros por nombre (búsqueda parcial).

        Args:
            name: Nombre o fragmento del nombre a buscar.
            limit: número máximo de resultados.

        Returns:
            Lista de terceros que coinciden con la búsqueda.
        """
        # Escapar comillas simples en el nombre para evitar inyección SQL
        escaped_name = name.replace("'", "''")
        filters = {"sqlfilters": f"(t.nom:like:'%{escaped_name}%')"}
        return await self._client.list(
            _DOLIBARR_THIRDPARTIES_RESOURCE,
            limit=limit,
            offset=0,
            filters=filters,
        )

    async def create_thirdparty(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Crea un tercero en Dolibarr.

        Args:
            data: campos del tercero. Campos esperados:
                  - name (obligatorio): nombre del tercero.
                  - client (0/1): flag cliente.
                  - supplier (0/1): flag proveedor.
                  - address: dirección.
                  - zip: código postal.
                  - town: ciudad.
                  - country_id: ID del país.
                  - phone: teléfono.
                  - email: email.
                  - siret: SIRET (Francia).
                  - tva_intra: VAT intra-comunitario.
                  - code_client: código cliente.
                  - code_fournisseur: código proveedor.

        Returns:
            Dict con el tercero creado, incluyendo el ID asignado por Dolibarr.
        """
        # Dolibarr requiere que si el tercero no especifica client/supplier,
        # ambos sean 0 por defecto (tercero genérico).
        if "client" not in data:
            data["client"] = 0
        if "supplier" not in data:
            data["supplier"] = 0

        return await self._client.create(_DOLIBARR_THIRDPARTIES_RESOURCE, data)

    async def update_thirdparty(
        self,
        thirdparty_id: int,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Actualiza un tercero existente.

        Args:
            thirdparty_id: ID del tercero a actualizar.
            data: campos a actualizar.

        Returns:
            Dict con el tercero actualizado.
        """
        return await self._client.update(
            _DOLIBARR_THIRDPARTIES_RESOURCE,
            thirdparty_id,
            data,
        )

    async def delete_thirdparty(self, thirdparty_id: int) -> bool:
        """
        Elimina un tercero.

        ADVERTENCIA: Dolibarr puede rechazar la eliminación si el tercero
        tiene pedidos o facturas asociadas.

        Args:
            thirdparty_id: ID del tercero a eliminar.

        Returns:
            True si se eliminó con éxito, False si Dolibarr rechazó por
            registros asociados.
        """
        try:
            return await self._client.delete(_DOLIBARR_THIRDPARTIES_RESOURCE, thirdparty_id)
        except IntegrationError as exc:
            # Dolibarr devuelve error 400/403 si hay registros asociados
            if exc.status_code in (400, 403):
                logger.warning(
                    "Dolibarr rechazó eliminación de tercero",
                    extra={
                        "thirdparty_id": thirdparty_id,
                        "status_code": exc.status_code,
                        "reason": str(exc),
                    },
                )
                return False
            raise

    async def get_thirdparty_invoices(
        self,
        thirdparty_id: int,
        type: str = "customer",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Lista facturas asociadas a un tercero.

        Args:
            thirdparty_id: ID del tercero.
            type: "customer" → facturas de cliente, "supplier" → facturas de proveedor.
            limit: número máximo de facturas por página.
            offset: desplazamiento desde el inicio.

        Returns:
            Lista de facturas del tercero.
        """
        if type == "supplier":
            endpoint = f"{_DOLIBARR_THIRDPARTIES_RESOURCE}/{thirdparty_id}/{_DOLIBARR_SUPPLIER_INVOICES_RESOURCE}"
        else:
            endpoint = f"{_DOLIBARR_THIRDPARTIES_RESOURCE}/{thirdparty_id}/{_DOLIBARR_INVOICES_RESOURCE}"

        return await self._client.list(
            endpoint,
            limit=limit,
            offset=offset,
        )

    async def get_thirdparty_orders(
        self,
        thirdparty_id: int,
        type: str = "customer",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Lista pedidos asociados a un tercero.

        Args:
            thirdparty_id: ID del tercero.
            type: "customer" → pedidos de cliente, "supplier" → pedidos de proveedor.
            limit: número máximo de pedidos por página.
            offset: desplazamiento desde el inicio.

        Returns:
            Lista de pedidos del tercero.
        """
        if type == "supplier":
            endpoint = f"{_DOLIBARR_THIRDPARTIES_RESOURCE}/{thirdparty_id}/{_DOLIBARR_SUPPLIER_ORDERS_RESOURCE}"
        else:
            endpoint = f"{_DOLIBARR_THIRDPARTIES_RESOURCE}/{thirdparty_id}/{_DOLIBARR_ORDERS_RESOURCE}"

        return await self._client.list(
            endpoint,
            limit=limit,
            offset=offset,
        )
