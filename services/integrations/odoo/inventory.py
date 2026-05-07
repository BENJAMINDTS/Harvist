"""
Servicio de gestión de inventario en Odoo (stock.quant).

:author: Carlitos6712
:version: 1.0.0
"""

from loguru import logger

from services.integrations.base import IntegrationClient, IntegrationError


class OdooInventoryService:
    """
    Servicio de consulta de stock en Odoo via stock.quant.

    :author: Carlitos6712
    """

    _QUANT_FIELDS = [
        "id", "product_id", "location_id", "quantity", "reserved_quantity",
        "lot_id", "package_id",
    ]

    def __init__(self, client: IntegrationClient) -> None:
        """
        Args:
            client: cliente Odoo autenticado.
        """
        self._client = client

    async def list_stock(
        self,
        limit: int = 50,
        offset: int = 0,
        product_id: int | None = None,
        location_id: int | None = None,
    ) -> list[dict]:
        """
        Lista registros de stock con paginación y filtros opcionales.

        Args:
            limit:       máximo de resultados.
            offset:      desplazamiento.
            product_id:  filtro por ID de producto (opcional).
            location_id: filtro por ID de ubicación (opcional).

        Returns:
            Lista de dicts de stock.quant.

        Raises:
            IntegrationError: si Odoo falla.
        """
        domain: list = [("location_id.usage", "=", "internal")]
        if product_id is not None:
            domain.append(("product_id", "=", product_id))
        if location_id is not None:
            domain.append(("location_id", "=", location_id))
        try:
            return await self._client.list(
                "stock.quant",
                limit=limit,
                offset=offset,
                filters={"domain": domain, "fields": self._QUANT_FIELDS},
            )
        except Exception as exc:
            logger.error("Error listando stock Odoo", exc_info=exc)
            raise IntegrationError("Fallo listando stock Odoo") from exc

    async def get_product_stock(self, product_id: int) -> list[dict]:
        """
        Obtiene todo el stock de un producto en todas las ubicaciones.

        Args:
            product_id: ID del producto (product.template).

        Returns:
            Lista de stock.quant por ubicación.

        Raises:
            IntegrationError: si falla.
        """
        domain: list = [
            ("product_id.product_tmpl_id", "=", product_id),
            ("location_id.usage", "=", "internal"),
        ]
        try:
            return await self._client.list(
                "stock.quant",
                limit=200,
                offset=0,
                filters={"domain": domain, "fields": self._QUANT_FIELDS},
            )
        except Exception as exc:
            logger.error("Error obteniendo stock de producto Odoo", exc_info=exc, extra={"product_id": product_id})
            raise IntegrationError(f"Fallo obteniendo stock del producto Odoo {product_id}") from exc

    async def list_locations(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """
        Lista ubicaciones de stock internas.

        Args:
            limit:  máximo de resultados.
            offset: desplazamiento.

        Returns:
            Lista de dicts de stock.location.

        Raises:
            IntegrationError: si falla.
        """
        domain: list = [("usage", "=", "internal"), ("active", "=", True)]
        try:
            return await self._client.list(
                "stock.location",
                limit=limit,
                offset=offset,
                filters={
                    "domain": domain,
                    "fields": ["id", "name", "complete_name", "usage", "active"],
                    "order": "complete_name asc",
                },
            )
        except Exception as exc:
            logger.error("Error listando ubicaciones Odoo", exc_info=exc)
            raise IntegrationError("Fallo listando ubicaciones Odoo") from exc

    async def count_stock_lines(self) -> int:
        """
        Cuenta líneas de stock internas.

        Returns:
            Número de registros en stock.quant.
        """
        from services.integrations.odoo.client import OdooClient
        if not isinstance(self._client, OdooClient):
            return 0
        domain: list = [("location_id.usage", "=", "internal")]
        return await self._client.search_count("stock.quant", domain)
