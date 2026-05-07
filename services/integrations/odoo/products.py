"""
Servicio de gestión de productos en Odoo (product.template).

:author: Carlitos6712
:version: 1.0.0
"""

from loguru import logger

from services.integrations.base import IntegrationClient, IntegrationError


class OdooProductService:
    """
    Servicio CRUD de productos en Odoo (product.template).

    :author: Carlitos6712
    """

    _FIELDS = [
        "id", "name", "default_code", "description", "description_sale",
        "description_purchase", "list_price", "compare_list_price",
        "standard_price", "detailed_type", "type", "categ_id",
        "uom_id", "uom_po_id", "active", "sale_ok", "purchase_ok",
        "qty_available", "volume", "weight", "tracking", "priority",
        "hs_code", "sale_delay", "invoice_policy", "purchase_method",
        "is_published", "available_in_pos",
        "website_meta_title", "website_meta_description", "website_meta_keywords",
    ]

    def __init__(self, client: IntegrationClient) -> None:
        """
        Args:
            client: cliente Odoo autenticado.
        """
        self._client = client

    async def list_products(
        self,
        limit: int = 50,
        offset: int = 0,
        search: str = "",
        active_only: bool = True,
    ) -> list[dict]:
        """
        Lista productos con paginación y filtro opcional por nombre.

        Args:
            limit:       máximo de resultados.
            offset:      desplazamiento.
            search:      filtro por nombre (opcional).
            active_only: si True, solo productos activos.

        Returns:
            Lista de dicts de product.template.

        Raises:
            IntegrationError: si Odoo falla.
        """
        domain: list = [("active", "=", active_only)]
        if search:
            domain.append(("name", "ilike", search))

        try:
            return await self._client.list(
                "product.template",
                limit=limit,
                offset=offset,
                filters={"domain": domain, "fields": self._FIELDS},
            )
        except Exception as exc:
            logger.error("Error listando productos Odoo", exc_info=exc)
            raise IntegrationError("Fallo listando productos Odoo") from exc

    async def get_product(self, product_id: int) -> dict:
        """
        Obtiene un producto por ID.

        Args:
            product_id: ID de product.template.

        Returns:
            Dict con datos del producto.

        Raises:
            IntegrationError: si no existe o falla.
        """
        try:
            return await self._client.get("product.template", product_id)
        except Exception as exc:
            logger.error("Error obteniendo producto Odoo", exc_info=exc, extra={"id": product_id})
            raise IntegrationError(f"Producto Odoo {product_id} no encontrado") from exc

    async def create_product(self, data: dict) -> dict:
        """
        Crea un producto en Odoo.

        Args:
            data: datos del producto (name obligatorio).

        Returns:
            Producto creado.

        Raises:
            IntegrationError: si falla la creación.
        """
        try:
            result = await self._client.create("product.template", data)
            logger.info("Producto Odoo creado", extra={"id": result.get("id")})
            return result
        except Exception as exc:
            logger.error("Error creando producto Odoo", exc_info=exc)
            raise IntegrationError("Fallo creando producto Odoo") from exc

    async def update_product(self, product_id: int, data: dict) -> dict:
        """
        Actualiza un producto existente.

        Args:
            product_id: ID del producto.
            data:       campos a actualizar.

        Returns:
            Producto actualizado.

        Raises:
            IntegrationError: si falla.
        """
        try:
            result = await self._client.update("product.template", product_id, data)
            logger.info("Producto Odoo actualizado", extra={"id": product_id})
            return result
        except Exception as exc:
            logger.error("Error actualizando producto Odoo", exc_info=exc, extra={"id": product_id})
            raise IntegrationError(f"Fallo actualizando producto Odoo {product_id}") from exc

    async def delete_product(self, product_id: int) -> bool:
        """
        Elimina un producto.

        Args:
            product_id: ID del producto.

        Returns:
            True si se eliminó.

        Raises:
            IntegrationError: si falla.
        """
        try:
            result = await self._client.delete("product.template", product_id)
            logger.info("Producto Odoo eliminado", extra={"id": product_id})
            return result
        except Exception as exc:
            logger.error("Error eliminando producto Odoo", exc_info=exc, extra={"id": product_id})
            raise IntegrationError(f"Fallo eliminando producto Odoo {product_id}") from exc

    async def count_products(self, active_only: bool = True) -> int:
        """
        Cuenta el total de productos.

        Args:
            active_only: si True, solo activos.

        Returns:
            Número de productos.
        """
        from services.integrations.odoo.client import OdooClient
        if not isinstance(self._client, OdooClient):
            return 0
        domain: list = [("active", "=", active_only)]
        return await self._client.search_count("product.template", domain)
