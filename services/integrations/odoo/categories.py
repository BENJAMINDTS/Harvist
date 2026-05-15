"""
Servicio de gestión de categorías de producto en Odoo (product.category).

:author: Carlitos6712
:version: 1.0.0
"""

from loguru import logger

from services.integrations.base import IntegrationClient, IntegrationError


class OooCategoryService:
    """
    Servicio CRUD de categorías de producto en Odoo.

    :author: Carlitos6712
    """

    _FIELDS = ["id", "name", "complete_name", "parent_id", "child_id"]

    def __init__(self, client: IntegrationClient) -> None:
        """
        Args:
            client: cliente Odoo autenticado.
        """
        self._client = client

    async def list_categories(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """
        Lista categorías con paginación.

        Args:
            limit:  máximo de resultados.
            offset: desplazamiento.

        Returns:
            Lista de dicts de product.category.

        Raises:
            IntegrationError: si Odoo falla.
        """
        try:
            return await self._client.list(
                "product.category",
                limit=limit,
                offset=offset,
                filters={"domain": [], "fields": self._FIELDS, "order": "complete_name asc"},
            )
        except Exception as exc:
            logger.error("Error listando categorías Odoo", exc_info=exc)
            raise IntegrationError("Fallo listando categorías Odoo") from exc

    async def get_category(self, category_id: int) -> dict:
        """
        Obtiene una categoría por ID.

        Args:
            category_id: ID de product.category.

        Returns:
            Dict con datos de la categoría.

        Raises:
            IntegrationError: si no existe o falla.
        """
        try:
            return await self._client.get("product.category", category_id)
        except Exception as exc:
            logger.error("Error obteniendo categoría Odoo", exc_info=exc, extra={"id": category_id})
            raise IntegrationError(f"Categoría Odoo {category_id} no encontrada") from exc

    async def create_category(self, name: str, parent_id: int | None = None) -> dict:
        """
        Crea una categoría en Odoo.

        Args:
            name:      nombre de la categoría.
            parent_id: ID de la categoría padre (opcional).

        Returns:
            Categoría creada.

        Raises:
            IntegrationError: si falla.
        """
        data: dict = {"name": name}
        if parent_id is not None:
            data["parent_id"] = parent_id
        try:
            result = await self._client.create("product.category", data)
            logger.info("Categoría Odoo creada", extra={"id": result.get("id"), "name": name})
            return result
        except Exception as exc:
            logger.error("Error creando categoría Odoo", exc_info=exc)
            raise IntegrationError("Fallo creando categoría Odoo") from exc

    async def update_category(self, category_id: int, data: dict) -> dict:
        """
        Actualiza una categoría existente.

        Args:
            category_id: ID de la categoría.
            data:        campos a actualizar.

        Returns:
            Categoría actualizada.

        Raises:
            IntegrationError: si falla.
        """
        try:
            result = await self._client.update("product.category", category_id, data)
            logger.info("Categoría Odoo actualizada", extra={"id": category_id})
            return result
        except Exception as exc:
            logger.error("Error actualizando categoría Odoo", exc_info=exc, extra={"id": category_id})
            raise IntegrationError(f"Fallo actualizando categoría Odoo {category_id}") from exc

    async def delete_category(self, category_id: int) -> bool:
        """
        Elimina una categoría.

        Args:
            category_id: ID de la categoría.

        Returns:
            True si se eliminó.

        Raises:
            IntegrationError: si falla.
        """
        try:
            result = await self._client.delete("product.category", category_id)
            logger.info("Categoría Odoo eliminada", extra={"id": category_id})
            return result
        except Exception as exc:
            logger.error("Error eliminando categoría Odoo", exc_info=exc, extra={"id": category_id})
            raise IntegrationError(f"Fallo eliminando categoría Odoo {category_id}") from exc

    async def get_tree(self) -> list[dict]:
        """
        Construye árbol jerárquico de product.category.
        Pagina hasta obtener todas las categorías y organiza la
        relación padre-hijo en memoria usando parent_id y child_id de Odoo.

        Returns:
            Lista de nodos raíz con estructura children anidada.

        Raises:
            IntegrationError: si Odoo falla durante la paginación.
        """
        all_categories: list[dict] = []
        offset = 0
        limit = 100

        try:
            while True:
                batch = await self.list_categories(limit=limit, offset=offset)
                if not batch:
                    break
                all_categories.extend(batch)
                if len(batch) < limit:
                    break
                offset += limit
        except IntegrationError:
            raise

        categories_by_id: dict[int, dict] = {
            cat["id"]: {**cat, "children": []} for cat in all_categories
        }
        roots: list[dict] = []

        for cat in all_categories:
            raw_parent = cat.get("parent_id")
            # Odoo devuelve parent_id como [id, display_name] o False
            if raw_parent and isinstance(raw_parent, list) and len(raw_parent) >= 1:
                parent_id = raw_parent[0]
                if parent_id in categories_by_id:
                    categories_by_id[parent_id]["children"].append(categories_by_id[cat["id"]])
                else:
                    roots.append(categories_by_id[cat["id"]])
            else:
                roots.append(categories_by_id[cat["id"]])

        logger.debug("Árbol Odoo construido", extra={"roots": len(roots), "total": len(all_categories)})
        return roots

    async def find_category_by_name(self, name: str) -> dict | None:
        """
        Busca una categoría por nombre exacto (campo name, sin ruta completa).

        Args:
            name: nombre de la categoría a buscar.

        Returns:
            Dict con id, name y complete_name si existe, None si no se encuentra.
        """
        try:
            results = await self._client.list(
                "product.category",
                limit=1,
                filters={"domain": [("name", "=", name)], "fields": ["id", "name"]},
            )
            return results[0] if results else None
        except Exception as exc:
            logger.warning("Error buscando categoría Odoo por nombre", exc_info=exc, extra={"name": name})
            return None

    async def count_categories(self) -> int:
        """
        Cuenta el total de categorías.

        Returns:
            Número de categorías.
        """
        from services.integrations.odoo.client import OdooClient
        if not isinstance(self._client, OdooClient):
            return 0
        return await self._client.search_count("product.category")

    async def find_category_by_name_and_parent(self, name: str, parent_id: int) -> dict | None:
        """
        Busca categoría por nombre exacto bajo un padre específico.

        Args:
            name:      nombre exacto de la categoría.
            parent_id: ID de la categoría padre.

        Returns:
            Dict de la categoría si existe, None si no.
        """
        try:
            results = await self._client.list(
                "product.category",
                limit=1,
                filters={
                    "domain": [("name", "=", name), ("parent_id", "=", parent_id)],
                    "fields": ["id", "name"],
                },
            )
            return results[0] if results else None
        except Exception as exc:
            logger.warning(
                "Error buscando subcategoría Odoo por nombre y padre",
                exc_info=exc,
                extra={"name": name, "parent_id": parent_id},
            )
            return None

    async def find_or_create_subcategory(self, parent_name: str, subcat_name: str) -> dict:
        """
        Busca subcategoría bajo un padre por nombre, o la crea automáticamente si no existe.

        Args:
            parent_name: nombre exacto de la categoría padre.
            subcat_name: nombre exacto de la subcategoría.

        Returns:
            Dict con id, name, complete_name de la subcategoría.

        Raises:
            IntegrationError: si el padre no existe en Odoo o falla la creación.
        """
        parent = await self.find_category_by_name(parent_name)
        if not parent:
            raise IntegrationError(
                f"Categoría padre '{parent_name}' no existe en Odoo. Créala primero."
            )
        parent_id = int(parent["id"])
        existing = await self.find_category_by_name_and_parent(subcat_name, parent_id)
        if existing:
            logger.debug(
                "Subcategoría Odoo encontrada",
                extra={"name": subcat_name, "parent_id": parent_id},
            )
            return existing
        created = await self.create_category(subcat_name, parent_id=parent_id)
        logger.info(
            "Subcategoría Odoo creada automáticamente",
            extra={"name": subcat_name, "parent_name": parent_name, "id": created.get("id")},
        )
        return created

    async def list_brands(
        self,
        brands_parent: str = "Marcas",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """
        Lista las marcas (subcategorías bajo la categoría padre ``brands_parent``).

        Args:
            brands_parent: nombre exacto de la categoría padre de marcas.
            limit:         máximo de resultados.
            offset:        desplazamiento para paginación.

        Returns:
            Lista de dicts de subcategorías (marcas). Vacía si el padre no existe.
        """
        parent = await self.find_category_by_name(brands_parent)
        if not parent:
            return []
        parent_id = int(parent["id"])
        all_cats = await self.list_categories(limit=500, offset=0)
        brands = [
            c for c in all_cats
            if c.get("parent_id") and (
                (isinstance(c["parent_id"], list) and c["parent_id"][0] == parent_id)
                or c["parent_id"] == parent_id
            )
        ]
        return brands[offset: offset + limit]

    async def find_or_create_brand(
        self,
        brand_name: str,
        brands_parent: str = "Marcas",
    ) -> dict:
        """
        Busca una marca bajo ``brands_parent``, o la crea si no existe.

        Args:
            brand_name:    nombre exacto de la marca (subcategoría).
            brands_parent: nombre exacto de la categoría padre de marcas.

        Returns:
            Dict de la subcategoría (marca) resuelta o creada.

        Raises:
            IntegrationError: si la categoría padre no existe en Odoo.
        """
        return await self.find_or_create_subcategory(brands_parent, brand_name)

    # ── product.public.category (eCommerce) ──────────────────────────────────

    _PUBLIC_CAT_FIELDS = ["id", "name", "parent_id", "child_id"]

    async def _find_public_category_by_name(self, name: str) -> dict | None:
        """
        Busca una categoría pública (product.public.category) por nombre exacto.

        Args:
            name: nombre de la categoría a buscar.

        Returns:
            Dict con id y name si existe, None si no.
        """
        try:
            results = await self._client.list(
                "product.public.category",
                limit=1,
                filters={"domain": [("name", "=", name)], "fields": ["id", "name"]},
            )
            return results[0] if results else None
        except Exception as exc:
            logger.warning(
                "Error buscando product.public.category por nombre",
                exc_info=exc,
                extra={"name": name},
            )
            return None

    async def _find_public_category_by_name_and_parent(
        self, name: str, parent_id: int
    ) -> dict | None:
        """
        Busca categoría pública por nombre bajo un padre específico.

        Args:
            name:      nombre exacto.
            parent_id: ID del padre en product.public.category.

        Returns:
            Dict si existe, None si no.
        """
        try:
            results = await self._client.list(
                "product.public.category",
                limit=1,
                filters={
                    "domain": [("name", "=", name), ("parent_id", "=", parent_id)],
                    "fields": ["id", "name"],
                },
            )
            return results[0] if results else None
        except Exception as exc:
            logger.warning(
                "Error buscando product.public.category por nombre y padre",
                exc_info=exc,
                extra={"name": name, "parent_id": parent_id},
            )
            return None

    async def _ensure_brands_parent(self, brands_parent: str) -> dict:
        """
        Devuelve la categoría padre de marcas en product.public.category, creándola si no existe.

        Args:
            brands_parent: nombre exacto de la categoría raíz de marcas.

        Returns:
            Dict de la categoría padre (id, name, complete_name).

        Raises:
            IntegrationError: si falla la creación.
        """
        parent = await self._find_public_category_by_name(brands_parent)
        if parent:
            return parent
        try:
            created = await self._client.create(
                "product.public.category",
                {"name": brands_parent},
            )
            logger.info(
                "Categoría padre de marcas creada automáticamente en product.public.category",
                extra={"name": brands_parent, "id": created.get("id")},
            )
            return created
        except Exception as exc:
            logger.error("Error creando categoría padre de marcas Odoo", exc_info=exc)
            raise IntegrationError(
                f"Fallo creando categoría padre '{brands_parent}' en product.public.category"
            ) from exc

    async def list_brands_public(
        self,
        brands_parent: str = "Marcas",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """
        Lista marcas como subcategorías bajo ``brands_parent`` en product.public.category.
        Si el padre no existe, lo crea automáticamente.

        Args:
            brands_parent: nombre exacto de la categoría padre de marcas.
            limit:         máximo de resultados.
            offset:        desplazamiento para paginación.

        Returns:
            Lista de dicts.
        """
        parent = await self._ensure_brands_parent(brands_parent)
        parent_id = int(parent["id"])
        try:
            results = await self._client.list(
                "product.public.category",
                limit=500,
                filters={
                    "domain": [("parent_id", "=", parent_id)],
                    "fields": self._PUBLIC_CAT_FIELDS,
                    "order": "name asc",
                },
            )
            return results[offset: offset + limit]
        except Exception as exc:
            logger.error("Error listando marcas públicas Odoo", exc_info=exc)
            raise IntegrationError("Fallo listando marcas en product.public.category") from exc

    async def find_or_create_brand_public(
        self,
        brand_name: str,
        brands_parent: str = "Marcas",
    ) -> dict:
        """
        Busca marca en product.public.category bajo ``brands_parent``, o la crea si no existe.
        Si el padre tampoco existe, lo crea automáticamente.

        Args:
            brand_name:    nombre exacto de la marca.
            brands_parent: nombre exacto de la categoría padre de marcas públicas.

        Returns:
            Dict de la marca (product.public.category) resuelta o creada.

        Raises:
            IntegrationError: si falla la creación en Odoo.
        """
        parent = await self._ensure_brands_parent(brands_parent)
        parent_id = int(parent["id"])
        existing = await self._find_public_category_by_name_and_parent(brand_name, parent_id)
        if existing:
            logger.debug(
                "Marca pública Odoo encontrada",
                extra={"name": brand_name, "parent_id": parent_id},
            )
            return existing
        try:
            created = await self._client.create(
                "product.public.category",
                {"name": brand_name, "parent_id": parent_id},
            )
            logger.info(
                "Marca pública Odoo creada",
                extra={"name": brand_name, "parent": brands_parent, "id": created.get("id")},
            )
            return created
        except Exception as exc:
            logger.error("Error creando marca pública Odoo", exc_info=exc)
            raise IntegrationError(f"Fallo creando marca '{brand_name}' en Odoo") from exc

    async def delete_brand_public(self, brand_id: int) -> bool:
        """
        Elimina una marca de product.public.category.

        Args:
            brand_id: ID de la marca en product.public.category.

        Returns:
            True si se eliminó.

        Raises:
            IntegrationError: si falla.
        """
        try:
            result = await self._client.delete("product.public.category", brand_id)
            logger.info("Marca pública Odoo eliminada", extra={"id": brand_id})
            return result
        except Exception as exc:
            logger.error("Error eliminando marca pública Odoo", exc_info=exc, extra={"id": brand_id})
            raise IntegrationError(f"Fallo eliminando marca Odoo {brand_id}") from exc

    # ── product.public.category — CRUD completo (eCommerce) ──────────────────

    async def list_public_categories(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """
        Lista todas las categorías de eCommerce (product.public.category) con paginación.

        Args:
            limit:  máximo de resultados.
            offset: desplazamiento.

        Returns:
            Lista de dicts de product.public.category.

        Raises:
            IntegrationError: si Odoo falla.
        """
        try:
            return await self._client.list(
                "product.public.category",
                limit=limit,
                offset=offset,
                filters={"domain": [], "fields": self._PUBLIC_CAT_FIELDS, "order": "name asc"},
            )
        except Exception as exc:
            logger.error("Error listando categorías públicas Odoo", exc_info=exc)
            raise IntegrationError("Fallo listando categorías eCommerce Odoo") from exc

    async def get_public_category_tree(self) -> list[dict]:
        """
        Construye árbol jerárquico completo de product.public.category.
        Pagina hasta obtener todas y organiza la relación padre-hijo en memoria.

        Returns:
            Lista de nodos raíz con estructura children anidada.

        Raises:
            IntegrationError: si Odoo falla durante la paginación.
        """
        all_cats: list[dict] = []
        offset = 0
        limit = 100
        try:
            while True:
                batch = await self.list_public_categories(limit=limit, offset=offset)
                if not batch:
                    break
                all_cats.extend(batch)
                if len(batch) < limit:
                    break
                offset += limit
        except IntegrationError:
            raise

        cats_by_id: dict[int, dict] = {c["id"]: {**c, "children": []} for c in all_cats}
        roots: list[dict] = []
        for cat in all_cats:
            raw_parent = cat.get("parent_id")
            if raw_parent and isinstance(raw_parent, list) and len(raw_parent) >= 1:
                parent_id = raw_parent[0]
                if parent_id in cats_by_id:
                    cats_by_id[parent_id]["children"].append(cats_by_id[cat["id"]])
                else:
                    roots.append(cats_by_id[cat["id"]])
            else:
                roots.append(cats_by_id[cat["id"]])

        logger.debug("Árbol eCommerce Odoo construido", extra={"roots": len(roots), "total": len(all_cats)})
        return roots

    async def create_public_category(self, name: str, parent_id: int | None = None) -> dict:
        """
        Crea una categoría de eCommerce en product.public.category.

        Args:
            name:      nombre de la categoría.
            parent_id: ID del padre (opcional).

        Returns:
            Categoría creada.

        Raises:
            IntegrationError: si falla.
        """
        data: dict = {"name": name}
        if parent_id is not None:
            data["parent_id"] = parent_id
        try:
            result = await self._client.create("product.public.category", data)
            logger.info("Categoría eCommerce Odoo creada", extra={"id": result.get("id"), "name": name})
            return result
        except Exception as exc:
            logger.error("Error creando categoría eCommerce Odoo", exc_info=exc)
            raise IntegrationError("Fallo creando categoría eCommerce Odoo") from exc

    async def update_public_category(self, category_id: int, data: dict) -> dict:
        """
        Actualiza una categoría de eCommerce existente.

        Args:
            category_id: ID de la categoría en product.public.category.
            data:        campos a actualizar.

        Returns:
            Categoría actualizada.

        Raises:
            IntegrationError: si falla.
        """
        try:
            result = await self._client.update("product.public.category", category_id, data)
            logger.info("Categoría eCommerce Odoo actualizada", extra={"id": category_id})
            return result
        except Exception as exc:
            logger.error("Error actualizando categoría eCommerce Odoo", exc_info=exc, extra={"id": category_id})
            raise IntegrationError(f"Fallo actualizando categoría eCommerce Odoo {category_id}") from exc

    async def delete_public_category(self, category_id: int) -> bool:
        """
        Elimina una categoría de eCommerce.

        Args:
            category_id: ID de la categoría en product.public.category.

        Returns:
            True si se eliminó.

        Raises:
            IntegrationError: si falla.
        """
        try:
            result = await self._client.delete("product.public.category", category_id)
            logger.info("Categoría eCommerce Odoo eliminada", extra={"id": category_id})
            return result
        except Exception as exc:
            logger.error("Error eliminando categoría eCommerce Odoo", exc_info=exc, extra={"id": category_id})
            raise IntegrationError(f"Fallo eliminando categoría eCommerce Odoo {category_id}") from exc

    async def count_public_categories(self) -> int:
        """
        Cuenta el total de categorías de eCommerce.

        Returns:
            Número de categorías en product.public.category.
        """
        from services.integrations.odoo.client import OdooClient
        if not isinstance(self._client, OdooClient):
            return 0
        return await self._client.search_count("product.public.category")

    async def find_or_create_public_subcategory(
        self,
        parent_name: str,
        subcat_name: str,
    ) -> dict:
        """
        Busca subcategoría de eCommerce bajo un padre por nombre, o la crea si no existe.
        Usado durante importación CSV para resolver categorías eCommerce con subcategoría.

        Args:
            parent_name: nombre exacto de la categoría padre en product.public.category.
            subcat_name: nombre exacto de la subcategoría.

        Returns:
            Dict de la subcategoría resuelta o creada.

        Raises:
            IntegrationError: si el padre no existe o falla la creación.
        """
        parent = await self._find_public_category_by_name(parent_name)
        if not parent:
            raise IntegrationError(
                f"Categoría eCommerce padre '{parent_name}' no existe en Odoo. Créala primero."
            )
        parent_id = int(parent["id"])
        existing = await self._find_public_category_by_name_and_parent(subcat_name, parent_id)
        if existing:
            logger.debug(
                "Subcategoría eCommerce Odoo encontrada",
                extra={"name": subcat_name, "parent_id": parent_id},
            )
            return existing
        created = await self.create_public_category(subcat_name, parent_id=parent_id)
        logger.info(
            "Subcategoría eCommerce Odoo creada automáticamente",
            extra={"name": subcat_name, "parent_name": parent_name, "id": created.get("id")},
        )
        return created
