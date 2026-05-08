"""
Servicio de gestión de productos en Odoo (product.template).

:author: Carlitos6712
:version: 1.0.0
"""

import asyncio

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

    # Tipos de cada campo aceptado en importación CSV.
    _CSV_FIELD_TYPES: dict[str, str] = {
        "name": "str",
        "default_code": "str",
        "active": "bool",
        "priority": "str",
        "detailed_type": "str",
        "tracking": "str",
        "categ_id": "int",
        "list_price": "float",
        "compare_list_price": "float",
        "standard_price": "float",
        "weight": "float",
        "volume": "float",
        "sale_delay": "int",
        "hs_code": "str",
        "sale_ok": "bool",
        "invoice_policy": "str",
        "description_sale": "str",
        "purchase_ok": "bool",
        "purchase_method": "str",
        "description_purchase": "str",
        "is_published": "bool",
        "available_in_pos": "bool",
        "website_meta_title": "str",
        "website_meta_description": "str",
        "website_meta_keywords": "str",
        "description": "str",
    }

    @classmethod
    def _coerce(cls, field: str, raw: str) -> object:
        """
        Convierte string CSV al tipo correcto para el campo Odoo.

        Args:
            field: nombre del campo Odoo.
            raw:   valor crudo del CSV.

        Returns:
            Valor convertido al tipo adecuado, o False si está vacío.
        """
        kind = cls._CSV_FIELD_TYPES.get(field, "str")
        val = raw.strip()
        if not val:
            return False
        if kind == "bool":
            return val.lower() in {"1", "true", "yes", "si", "sí", "on", "verdadero"}
        if kind == "float":
            try:
                return float(val.replace(",", "."))
            except ValueError:
                return 0.0
        if kind == "int":
            try:
                return int(float(val))
            except ValueError:
                return False
        return val

    async def bulk_create_products(
        self,
        rows: list[dict[str, str]],
        mapping: dict[str, str],
        concurrency: int = 5,
    ) -> dict:
        """
        Crea múltiples productos a partir de filas CSV y un mapeo de columnas.
        Usa un semáforo para limitar llamadas concurrentes a Odoo.

        Args:
            rows:        lista de dicts {columna_csv: valor_string}.
            mapping:     dict {columna_csv: campo_odoo}. Columnas mapeadas a "" se ignoran.
            concurrency: máximo de creaciones simultáneas contra Odoo.

        Returns:
            Dict con claves: created (int), failed (int),
            errors (list[{row, error}]).
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def _create_one(idx: int, row: dict[str, str]) -> tuple[bool, dict | None]:
            product_data: dict = {}
            for csv_col, odoo_field in mapping.items():
                if not odoo_field or odoo_field not in self._CSV_FIELD_TYPES:
                    continue
                raw = row.get(csv_col, "")
                coerced = self._coerce(odoo_field, raw)
                if coerced is not False:
                    product_data[odoo_field] = coerced

            if not product_data.get("name"):
                return False, {"row": idx, "error": "Campo 'name' obligatorio y vacío."}

            async with semaphore:
                try:
                    await self.create_product(product_data)
                    return True, None
                except Exception as exc:
                    logger.warning("Fallo importando fila CSV", extra={"row": idx, "exc": str(exc)})
                    return False, {"row": idx, "error": str(exc)}

        results = await asyncio.gather(
            *[_create_one(idx, row) for idx, row in enumerate(rows, start=1)]
        )

        created = sum(1 for ok, _ in results if ok)
        failed = sum(1 for ok, _ in results if not ok)
        errors = [err for ok, err in results if not ok and err is not None]

        logger.info(
            "Importación CSV Odoo completada",
            extra={"created": created, "failed": failed},
        )
        return {"created": created, "failed": failed, "errors": errors}
