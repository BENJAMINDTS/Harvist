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

    async def _find_product_by_default_code(self, default_code: str) -> dict | None:
        """
        Busca un producto por su referencia interna (campo default_code).

        Args:
            default_code: referencia interna del producto.

        Returns:
            Dict del producto si existe, None si no se encuentra.
        """
        try:
            results = await self._client.list(
                "product.template",
                limit=1,
                filters={"domain": [("default_code", "=", default_code)], "fields": self._FIELDS},
            )
            return results[0] if results else None
        except IntegrationError:
            return None

    async def create_product(self, data: dict) -> dict:
        """
        Crea un producto en Odoo.

        Args:
            data: datos del producto (name y default_code obligatorios).

        Returns:
            Producto creado.

        Raises:
            IntegrationError: si falta default_code, o si falla la creación.
        """
        if not str(data.get("default_code", "")).strip():
            raise IntegrationError(
                "El campo 'default_code' (referencia interna) es obligatorio al crear un producto Odoo.",
                platform="odoo",
            )
        try:
            result = await self._client.create("product.template", data)
            logger.info("Producto Odoo creado", extra={"id": result.get("id"), "ref": data["default_code"]})
            return result
        except IntegrationError:
            raise
        except Exception as exc:
            logger.error("Error creando producto Odoo", exc_info=exc)
            raise IntegrationError("Fallo creando producto Odoo") from exc

    async def update_product_by_ref(self, default_code: str, data: dict) -> dict:
        """
        Actualiza un producto buscándolo por su referencia interna (default_code).

        Args:
            default_code: referencia interna del producto a actualizar.
            data:         campos a actualizar.

        Returns:
            Producto actualizado.

        Raises:
            IntegrationError: si no existe producto con esa referencia, o si falla.
        """
        existing = await self._find_product_by_default_code(default_code)
        if existing is None:
            raise IntegrationError(
                f"Producto con referencia interna '{default_code}' no encontrado en Odoo.",
                platform="odoo",
                status_code=404,
            )
        product_id = int(existing["id"])
        logger.info("Actualizando producto Odoo por referencia", extra={"ref": default_code, "id": product_id})
        return await self.update_product(product_id, data)

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

    async def bulk_delete_products(
        self,
        product_ids: list[int],
        concurrency: int = 10,
    ) -> dict:
        """
        Elimina múltiples productos de forma concurrente.

        Args:
            product_ids: lista de IDs de product.template a eliminar.
            concurrency: máximo de eliminaciones simultáneas contra Odoo.

        Returns:
            Dict con claves: deleted (int), failed (int), errors (list[{id, error}]).
        """
        if not product_ids:
            return {"deleted": 0, "failed": 0, "errors": []}

        errors: list[dict] = []
        semaphore = asyncio.Semaphore(concurrency)

        async def _delete_one(product_id: int) -> tuple[bool, dict | None]:
            async with semaphore:
                try:
                    await self.delete_product(product_id)
                    return True, None
                except Exception as exc:
                    logger.warning("Fallo eliminando producto Odoo", extra={"id": product_id, "exc": str(exc)})
                    return False, {"id": product_id, "error": str(exc)}

        delete_results = await asyncio.gather(*[_delete_one(pid) for pid in product_ids])
        deleted = sum(1 for ok, _ in delete_results if ok)
        errors.extend([err for ok, err in delete_results if not ok and err is not None])

        failed = len(errors)
        logger.info("Eliminación masiva Odoo completada", extra={"deleted": deleted, "failed": failed})
        return {"deleted": deleted, "failed": failed, "errors": errors}

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
        "categ_id": "str",
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
        # Campo virtual: nombre de subcategoría interna — resuelto antes de enviar a Odoo
        "subcateg_id": "str",
        # Campo virtual: nombre de marca (subcategoría bajo "Marcas") — resuelto antes de enviar a Odoo
        "brand_id": "str",
        # Campo virtual: categoría eCommerce (product.public.category) — resuelto antes de enviar a Odoo
        "public_categ_id": "str",
        # Campo virtual: subcategoría eCommerce — resuelto junto a public_categ_id
        "public_subcateg_id": "str",
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

    async def bulk_upsert_products(
        self,
        rows: list[dict[str, str]],
        mapping: dict[str, str],
        overwrite: bool = False,
        concurrency: int = 10,
        batch_size: int = 100,
        categ_name_to_id: dict[str, int] | None = None,
        subcateg_pair_to_id: dict[str, int] | None = None,
        brand_name_to_id: dict[str, int] | None = None,
        public_categ_name_to_id: dict[str, int] | None = None,
        public_subcateg_pair_to_id: dict[str, int] | None = None,
    ) -> dict:
        """
        Importa múltiples productos desde CSV con upsert por default_code.

        Estrategia optimizada para volúmenes grandes:
          1. Parseo y validación de todas las filas en memoria.
          2. Búsqueda masiva de existentes en lotes (1 llamada XML-RPC por lote de 500).
          3. Creación en lotes usando bulk_create (1 llamada XML-RPC por lote).
          4. Actualización concurrente de existentes (N llamadas, sin búsqueda previa).

        Args:
            rows:                     lista de dicts {columna_csv: valor_string}.
            mapping:                  dict {columna_csv: campo_odoo}. Columnas mapeadas a "" se ignoran.
            overwrite:                si True, actualiza productos existentes; si False, los omite.
            concurrency:              máximo de actualizaciones simultáneas contra Odoo.
            batch_size:               tamaño del lote para búsquedas masivas y creaciones.
            categ_name_to_id:         mapa {nombre_categoría: id_odoo} pre-validado en el endpoint.
            subcateg_pair_to_id:      mapa {"padre||hijo": id_odoo} de subcategorías internas.
                                      Si presente, sobreescribe categ_id con el ID de la subcategoría.
            brand_name_to_id:         mapa {nombre_marca: id_odoo} de marcas resueltas bajo "Marcas".
            public_categ_name_to_id:  mapa {nombre_cat_ecommerce: id_odoo} de categorías eCommerce.
            public_subcateg_pair_to_id: mapa {"padre||hijo": id_odoo} de subcategorías eCommerce.

        Returns:
            Dict con claves: created (int), updated (int), skipped (int),
            failed (int), errors (list[{row, error}]).
        """
        errors: list[dict] = []

        # ── Fase 1: parseo y validación ───────────────────────────────────────
        valid: list[tuple[int, dict, str]] = []  # (row_idx, product_data, default_code)
        for idx, row in enumerate(rows, start=1):
            product_data: dict = {}
            for csv_col, odoo_field in mapping.items():
                if not odoo_field or odoo_field not in self._CSV_FIELD_TYPES:
                    continue
                raw = row.get(csv_col, "")
                coerced = self._coerce(odoo_field, raw)
                if coerced is not False:
                    product_data[odoo_field] = coerced

            # Acumular IDs para public_categ_ids (Many2many) — marca + categoría eCommerce
            public_ids: list[int] = []

            # Marca → public_categ_ids
            if "brand_id" in product_data and brand_name_to_id:
                brand_name = str(product_data["brand_id"]).strip()
                if brand_name in brand_name_to_id:
                    public_ids.append(brand_name_to_id[brand_name])
                del product_data["brand_id"]

            # Subcategoría eCommerce (tiene prioridad sobre categoría eCommerce simple)
            if "public_subcateg_id" in product_data and public_subcateg_pair_to_id:
                pub_parent = str(product_data.get("public_categ_id", "")).strip()
                pub_sub = str(product_data["public_subcateg_id"]).strip()
                pair_key = f"{pub_parent}||{pub_sub}"
                if pair_key in public_subcateg_pair_to_id:
                    public_ids.append(public_subcateg_pair_to_id[pair_key])
                del product_data["public_subcateg_id"]
                if "public_categ_id" in product_data:
                    del product_data["public_categ_id"]
            elif "public_categ_id" in product_data and public_categ_name_to_id:
                pub_cat_name = str(product_data["public_categ_id"]).strip()
                if pub_cat_name in public_categ_name_to_id:
                    public_ids.append(public_categ_name_to_id[pub_cat_name])
                del product_data["public_categ_id"]

            if public_ids:
                product_data["public_categ_ids"] = [(4, pid) for pid in public_ids]

            # Resolver subcategoría / categoría interna (independiente de marca)
            if "subcateg_id" in product_data and subcateg_pair_to_id:
                parent_name = str(product_data.get("categ_id", "")).strip()
                subcat_name = str(product_data["subcateg_id"]).strip()
                pair_key = f"{parent_name}||{subcat_name}"
                if pair_key in subcateg_pair_to_id:
                    product_data["categ_id"] = subcateg_pair_to_id[pair_key]
                del product_data["subcateg_id"]
            elif "categ_id" in product_data and categ_name_to_id:
                cat_name = str(product_data["categ_id"]).strip()
                if cat_name in categ_name_to_id:
                    product_data["categ_id"] = categ_name_to_id[cat_name]
                else:
                    del product_data["categ_id"]

            if not product_data.get("name"):
                errors.append({"row": idx, "error": "Campo 'name' obligatorio y vacío."})
                continue
            default_code = str(product_data.get("default_code", "")).strip()
            if not default_code:
                errors.append({"row": idx, "error": "Campo 'default_code' obligatorio y vacío."})
                continue
            valid.append((idx, product_data, default_code))

        if not valid:
            return {"created": 0, "updated": 0, "skipped": 0, "failed": len(errors), "errors": errors}

        # ── Fase 2: búsqueda masiva de existentes (lotes de batch_size) ───────
        all_refs = [ref for _, _, ref in valid]
        existing_map: dict[str, int] = {}  # default_code → product.template id
        search_batch = 500  # Odoo soporta dominios grandes; 500 es seguro
        for i in range(0, len(all_refs), search_batch):
            batch_refs = all_refs[i : i + search_batch]
            try:
                found = await self._client.list(
                    "product.template",
                    limit=len(batch_refs),
                    filters={"domain": [("default_code", "in", batch_refs)], "fields": ["id", "default_code"]},
                )
                for record in found:
                    code = record.get("default_code")
                    if code:
                        existing_map[str(code)] = int(record["id"])
            except Exception as exc:
                logger.warning("Fallo en búsqueda masiva Odoo", exc_info=exc)

        # ── Fase 3: separar en crear vs actualizar/omitir ─────────────────────
        to_create: list[tuple[int, dict]] = []
        to_update: list[tuple[int, dict, int]] = []  # (row_idx, data, odoo_id)
        skipped = 0

        for idx, data, ref in valid:
            if ref in existing_map:
                if overwrite:
                    to_update.append((idx, data, existing_map[ref]))
                else:
                    skipped += 1
            else:
                to_create.append((idx, data))

        # ── Fase 4: creación en lotes ─────────────────────────────────────────
        created = 0
        for i in range(0, len(to_create), batch_size):
            batch = to_create[i : i + batch_size]
            batch_data = [data for _, data in batch]
            batch_indices = [idx for idx, _ in batch]
            try:
                from services.integrations.odoo.client import OdooClient
                if isinstance(self._client, OdooClient):
                    await self._client.bulk_create("product.template", batch_data)
                else:
                    for data in batch_data:
                        await self._client.create("product.template", data)
                created += len(batch)
                logger.info("Lote creado", extra={"lote": i // batch_size + 1, "count": len(batch)})
            except Exception as exc:
                logger.warning("Fallo en lote de creación", exc_info=exc)
                for idx, data in batch:
                    errors.append({"row": idx, "error": str(exc)})

        # ── Fase 5: actualizaciones concurrentes ──────────────────────────────
        updated = 0
        if to_update:
            semaphore = asyncio.Semaphore(concurrency)

            async def _update_one(idx: int, data: dict, product_id: int) -> tuple[bool, dict | None]:
                async with semaphore:
                    try:
                        await self.update_product(product_id, data)
                        return True, None
                    except Exception as exc:
                        logger.warning("Fallo actualizando producto Odoo", extra={"row": idx, "exc": str(exc)})
                        return False, {"row": idx, "error": str(exc)}

            update_results = await asyncio.gather(
                *[_update_one(idx, data, pid) for idx, data, pid in to_update]
            )
            updated = sum(1 for ok, _ in update_results if ok)
            errors.extend([err for ok, err in update_results if not ok and err is not None])

        failed = len(errors)
        logger.info(
            "Importación CSV Odoo completada",
            extra={"created": created, "updated": updated, "skipped": skipped, "failed": failed},
        )
        return {"created": created, "updated": updated, "skipped": skipped, "failed": failed, "errors": errors}
