"""
Servicio de gestión de partners (clientes y proveedores) en Odoo (res.partner).

En Odoo, clientes y proveedores son el mismo modelo res.partner.
Diferenciados por customer_rank > 0 (cliente) y supplier_rank > 0 (proveedor).

:author: Carlitos6712
:version: 1.0.0
"""

from typing import Literal

from loguru import logger

from services.integrations.base import IntegrationClient, IntegrationError

PartnerMode = Literal["customer", "supplier", "all"]


class OdooPartnerService:
    """
    Servicio CRUD de partners en Odoo (res.partner).

    :author: Carlitos6712
    """

    _FIELDS = [
        "id", "name", "email", "phone", "mobile", "street", "city",
        "zip", "country_id", "vat", "customer_rank", "supplier_rank",
        "active", "is_company", "comment",
    ]

    def __init__(self, client: IntegrationClient) -> None:
        """
        Args:
            client: cliente Odoo autenticado.
        """
        self._client = client

    def _build_domain(self, mode: PartnerMode, search: str = "") -> list:
        """
        Construye el dominio Odoo según el modo seleccionado.

        Args:
            mode:   "customer", "supplier" o "all".
            search: filtro opcional por nombre.

        Returns:
            Lista de tuplas de dominio Odoo.
        """
        domain: list = [("active", "=", True)]
        if mode == "customer":
            domain.append(("customer_rank", ">", 0))
        elif mode == "supplier":
            domain.append(("supplier_rank", ">", 0))
        if search:
            domain.append(("name", "ilike", search))
        return domain

    async def list_partners(
        self,
        mode: PartnerMode = "all",
        limit: int = 50,
        offset: int = 0,
        search: str = "",
    ) -> list[dict]:
        """
        Lista partners filtrados por modo y búsqueda.

        Args:
            mode:    "customer", "supplier" o "all".
            limit:   máximo de resultados.
            offset:  desplazamiento.
            search:  filtro por nombre (opcional).

        Returns:
            Lista de dicts de res.partner.

        Raises:
            IntegrationError: si Odoo falla.
        """
        domain = self._build_domain(mode, search)
        try:
            return await self._client.list(
                "res.partner",
                limit=limit,
                offset=offset,
                filters={"domain": domain, "fields": self._FIELDS},
            )
        except Exception as exc:
            logger.error("Error listando partners Odoo", exc_info=exc, extra={"mode": mode})
            raise IntegrationError(f"Fallo listando partners Odoo ({mode})") from exc

    async def get_partner(self, partner_id: int) -> dict:
        """
        Obtiene un partner por ID.

        Args:
            partner_id: ID de res.partner.

        Returns:
            Dict con datos del partner.

        Raises:
            IntegrationError: si no existe o falla.
        """
        try:
            return await self._client.get("res.partner", partner_id)
        except Exception as exc:
            logger.error("Error obteniendo partner Odoo", exc_info=exc, extra={"id": partner_id})
            raise IntegrationError(f"Partner Odoo {partner_id} no encontrado") from exc

    async def create_partner(self, data: dict) -> dict:
        """
        Crea un partner en Odoo.

        Args:
            data: datos del partner (name obligatorio).

        Returns:
            Partner creado.

        Raises:
            IntegrationError: si falla.
        """
        try:
            result = await self._client.create("res.partner", data)
            logger.info("Partner Odoo creado", extra={"id": result.get("id")})
            return result
        except Exception as exc:
            logger.error("Error creando partner Odoo", exc_info=exc)
            raise IntegrationError("Fallo creando partner Odoo") from exc

    async def update_partner(self, partner_id: int, data: dict) -> dict:
        """
        Actualiza un partner existente.

        Args:
            partner_id: ID del partner.
            data:       campos a actualizar.

        Returns:
            Partner actualizado.

        Raises:
            IntegrationError: si falla.
        """
        try:
            result = await self._client.update("res.partner", partner_id, data)
            logger.info("Partner Odoo actualizado", extra={"id": partner_id})
            return result
        except Exception as exc:
            logger.error("Error actualizando partner Odoo", exc_info=exc, extra={"id": partner_id})
            raise IntegrationError(f"Fallo actualizando partner Odoo {partner_id}") from exc

    async def delete_partner(self, partner_id: int) -> bool:
        """
        Elimina (archiva) un partner.

        Args:
            partner_id: ID del partner.

        Returns:
            True si se eliminó.

        Raises:
            IntegrationError: si falla.
        """
        try:
            result = await self._client.delete("res.partner", partner_id)
            logger.info("Partner Odoo eliminado", extra={"id": partner_id})
            return result
        except Exception as exc:
            logger.error("Error eliminando partner Odoo", exc_info=exc, extra={"id": partner_id})
            raise IntegrationError(f"Fallo eliminando partner Odoo {partner_id}") from exc

    async def count_partners(self, mode: PartnerMode = "all") -> int:
        """
        Cuenta partners según el modo.

        Args:
            mode: "customer", "supplier" o "all".

        Returns:
            Número de partners.
        """
        from services.integrations.odoo.client import OdooClient
        if not isinstance(self._client, OdooClient):
            return 0
        domain = self._build_domain(mode)
        return await self._client.search_count("res.partner", domain)
