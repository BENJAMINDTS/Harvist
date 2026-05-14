"""
Módulo de gestión de categorías en Dolibarr.
Soporta categorías de producto, cliente y proveedor.

:author: Carlitos6712
:version: 1.0.0
"""

import json
from typing import Literal

import aiomysql
import redis.asyncio as aioredis
from loguru import logger

from api.core.config import get_settings
from services.integrations.base import IntegrationError
from services.integrations.dolibarr.client import DolibarrClient

_REDIS_DB_CONFIG_KEY = "integration:dolibarr:db_config"


CATEGORY_TYPES = Literal["product", "customer", "supplier", "member"]
_DOLIBARR_CATEGORIES_RESOURCE = "categories"
_DOLIBARR_CATEGORY_OBJECTS_RESOURCE = "objects"


class DolibarrCategoryService:
    """
    Servicio de categorías para Dolibarr.
    Maneja CRUD, árbol jerárquico y asignación de productos.

    :author: Carlitos6712
    """

    def __init__(self, client: DolibarrClient) -> None:
        """
        Inicializa servicio con cliente Dolibarr.

        Args:
            client: Cliente Dolibarr configurado.
        """
        self._client = client

    async def list_categories(
        self,
        type: str = "product",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """
        Lista categorías filtrando por tipo.
        Dolibarr endpoint: GET /categories?type={type}

        Args:
            type: Tipo de categoría (product, customer, supplier, member).
            limit: Resultados por página.
            offset: Offset para paginación.

        Returns:
            Lista de categorías.
        """
        filters = {"type": type}
        return await self._client.list(
            _DOLIBARR_CATEGORIES_RESOURCE,
            limit=limit,
            offset=offset,
            filters=filters,
        )

    async def get_category(self, category_id: int) -> dict:
        """
        Obtiene una categoría por ID.

        Args:
            category_id: ID de la categoría.

        Returns:
            Datos de la categoría.
        """
        return await self._client.get(_DOLIBARR_CATEGORIES_RESOURCE, category_id)

    async def get_tree(self, type: str = "product") -> list[dict]:
        """
        Construye el árbol completo de categorías.
        Hace paginación automática hasta obtener todas las categorías,
        luego las organiza en estructura padre-hijo en memoria.

        Args:
            type: Tipo de categoría.

        Returns:
            Lista de nodos raíz con estructura anidada.
            Cada nodo: { id, label, parent_id, children: list[dict] }
        """
        all_categories = []
        offset = 0
        limit = 50

        while True:
            batch = await self.list_categories(type=type, limit=limit, offset=offset)
            if not batch:
                break
            all_categories.extend(batch)
            if len(batch) < limit:
                break
            offset += limit

        # Dolibarr returns id as string, fk_parent as int — normalize both to int for lookup.
        categories_by_id: dict[int, dict] = {
            int(cat["id"]): {**cat, "children": []} for cat in all_categories
        }
        roots = []

        for cat in all_categories:
            raw_parent = cat.get("fk_parent", None)
            try:
                parent_id = int(raw_parent) if raw_parent is not None else None
            except (ValueError, TypeError):
                parent_id = None
            node_id = int(cat["id"])
            if parent_id is None or parent_id == 0 or parent_id not in categories_by_id:
                roots.append(categories_by_id[node_id])
            else:
                categories_by_id[parent_id]["children"].append(categories_by_id[node_id])

        return roots

    async def create_category(
        self,
        label: str,
        type: str = "product",
        parent_id: int | None = None,
        description: str = "",
    ) -> dict:
        """
        Crea una nueva categoría.

        Args:
            label: Nombre de la categoría.
            type: Tipo de categoría.
            parent_id: ID de la categoría padre (opcional).
            description: Descripción (opcional).

        Returns:
            Datos de la categoría creada.
        """
        data = {
            "label": label,
            "type": type,
            "description": description,
        }
        if parent_id is not None:
            data["fk_parent"] = parent_id

        return await self._client.create(_DOLIBARR_CATEGORIES_RESOURCE, data)

    async def update_category(
        self,
        category_id: int,
        data: dict,
    ) -> dict:
        """
        Actualiza una categoría existente.

        Args:
            category_id: ID de la categoría.
            data: Campos a actualizar.

        Returns:
            Datos actualizados de la categoría.
        """
        return await self._client.update(_DOLIBARR_CATEGORIES_RESOURCE, category_id, data)

    async def delete_category(self, category_id: int) -> bool:
        """
        Elimina una categoría.

        Args:
            category_id: ID de la categoría a eliminar.

        Returns:
            True si éxito.
        """
        return await self._client.delete(_DOLIBARR_CATEGORIES_RESOURCE, category_id)

    async def assign_product(
        self,
        category_id: int,
        product_id: int,
    ) -> bool:
        """
        Asigna un producto a una categoría.
        Dolibarr endpoint: POST /categories/{id}/objects/{objectid}?type=product

        Args:
            category_id: ID de la categoría.
            product_id: ID del producto a asignar.

        Returns:
            True si éxito.

        Raises:
            IntegrationError: si Dolibarr devuelve un error al asignar.
        """
        # Intentar vía REST API primero.
        try:
            response = await self._client._request(
                "POST",
                f"{_DOLIBARR_CATEGORIES_RESOURCE}/{category_id}/{_DOLIBARR_CATEGORY_OBJECTS_RESOURCE}/{product_id}",
                params={"type": "product"},
            )
            if response.status_code < 400:
                logger.info(
                    "Categoría asignada via REST",
                    extra={"category_id": category_id, "product_id": product_id},
                )
                return True
            logger.warning(
                "REST assign_product falló, intentando DB directa",
                extra={
                    "category_id": category_id,
                    "product_id": product_id,
                    "http_status": response.status_code,
                    "dolibarr_response": response.text[:300],
                },
            )
        except Exception as exc:
            logger.warning(
                "REST assign_product excepción, intentando DB directa",
                exc_info=exc,
                extra={"category_id": category_id, "product_id": product_id},
            )

        # Fallback: INSERT directo en llx_categorie_product.
        return await self._assign_product_db(category_id, product_id)

    async def _assign_product_db(self, category_id: int, product_id: int) -> bool:
        """
        Inserta la relación categoría-producto directamente en la BD.

        Fallback cuando el endpoint REST no funciona en la versión de Dolibarr.
        Lee las credenciales de BD desde Redis (config UI) con fallback a .env.

        Args:
            category_id: ID de la categoría.
            product_id:  ID del producto.

        Returns:
            True si la inserción fue exitosa.

        Raises:
            IntegrationError: si la BD no está configurada o falla la inserción.
        """
        settings = get_settings()
        host = db_name = user = password = prefix = ""
        port = 3306

        # Leer config desde Redis primero (configurada via UI), luego .env.
        redis_client: aioredis.Redis | None = None
        try:
            redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
            stored = await redis_client.get(_REDIS_DB_CONFIG_KEY)
            if stored:
                cfg = json.loads(stored)
                host = cfg.get("host", "").strip()
                port = int(cfg.get("port") or 3306)
                db_name = cfg.get("db_name", "").strip()
                user = cfg.get("user", "").strip()
                password = cfg.get("password", "")
                prefix = cfg.get("prefix", "llx_").strip()
        except Exception:
            pass
        finally:
            if redis_client:
                await redis_client.aclose()

        # Fallback a variables de entorno si Redis no tenía config.
        if not host:
            host = settings.dolibarr_db_host or ""
            port = settings.dolibarr_db_port
            db_name = settings.dolibarr_db_name or ""
            user = settings.dolibarr_db_user or ""
            password = settings.dolibarr_db_pass or ""
            prefix = settings.dolibarr_db_prefix or "llx_"

        if not host or not db_name or not user:
            raise IntegrationError(
                "REST falló y BD de Dolibarr no configurada. "
                "Configura DOLIBARR_DB_* en .env o en la interfaz gráfica.",
                platform="dolibarr",
            )

        table = f"{prefix.strip()}categorie_product"

        conn: aiomysql.Connection = await aiomysql.connect(
            host=host,
            port=port,
            db=db_name,
            user=user,
            password=password,
            autocommit=True,
            charset="utf8mb4",
        )
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"INSERT IGNORE INTO `{table}` (fk_categorie, fk_product) VALUES (%s, %s)",
                    (category_id, product_id),
                )
            logger.info(
                "Categoría asignada via BD directa",
                extra={"category_id": category_id, "product_id": product_id, "table": table},
            )
            return True
        except Exception as exc:
            raise IntegrationError(
                f"Error asignando categoría {category_id} a producto {product_id} via BD: {exc}",
                platform="dolibarr",
            ) from exc
        finally:
            conn.close()

    async def remove_product(
        self,
        category_id: int,
        product_id: int,
    ) -> bool:
        """
        Elimina un producto de una categoría.
        Dolibarr endpoint: DELETE /categories/{id}/objects/{product_id}?type=product

        Args:
            category_id: ID de la categoría.
            product_id: ID del producto a remover.

        Returns:
            True si éxito.

        Raises:
            IntegrationError: si Dolibarr devuelve un error al eliminar.
        """
        response = await self._client._request(
            "DELETE",
            f"{_DOLIBARR_CATEGORIES_RESOURCE}/{category_id}/{_DOLIBARR_CATEGORY_OBJECTS_RESOURCE}/{product_id}",
            params={"type": "product"},
        )
        if response.status_code in (200, 204):
            return True
        raise IntegrationError(
            f"Error eliminando producto {product_id} de categoría {category_id}: HTTP {response.status_code}",
            platform="dolibarr",
            status_code=response.status_code,
        )

    async def find_category_by_name(
        self,
        name: str,
        type: str = "product",
    ) -> dict | None:
        """
        Busca una categoría por nombre exacto paginando hasta agotarlas.

        Args:
            name: Nombre exacto de la categoría (sensible a mayúsculas).
            type: Tipo de categoría.

        Returns:
            Dict de la categoría si existe, None si no se encuentra.
        """
        offset = 0
        limit = 100
        while True:
            batch = await self.list_categories(type=type, limit=limit, offset=offset)
            if not batch:
                return None
            for cat in batch:
                if str(cat.get("label", "")) == name:
                    return cat
            if len(batch) < limit:
                return None
            offset += limit

    async def find_category_by_name_and_parent(
        self,
        name: str,
        parent_id: int,
        type: str = "product",
    ) -> dict | None:
        """
        Busca categoría por nombre exacto bajo un padre específico.

        Args:
            name:      nombre exacto de la categoría (sensible a mayúsculas).
            parent_id: ID de la categoría padre.
            type:      tipo de categoría Dolibarr.

        Returns:
            Dict de la categoría si existe, None si no.
        """
        offset = 0
        limit = 100
        while True:
            batch = await self.list_categories(type=type, limit=limit, offset=offset)
            if not batch:
                return None
            for cat in batch:
                try:
                    cat_parent_id = int(cat.get("fk_parent") or 0)
                except (ValueError, TypeError):
                    cat_parent_id = 0
                if str(cat.get("label", "")) == name and cat_parent_id == parent_id:
                    return cat
            if len(batch) < limit:
                return None
            offset += limit

    async def find_or_create_subcategory(
        self,
        parent_name: str,
        subcat_name: str,
        type: str = "product",
    ) -> dict:
        """
        Busca subcategoría bajo un padre por nombre, o la crea automáticamente si no existe.

        Args:
            parent_name: nombre exacto de la categoría padre.
            subcat_name: nombre exacto de la subcategoría.
            type:        tipo de categoría Dolibarr.

        Returns:
            Dict con id, label de la subcategoría.

        Raises:
            IntegrationError: si el padre no existe o falla la creación.
        """
        parent = await self.find_category_by_name(parent_name, type=type)
        if not parent:
            raise IntegrationError(
                f"Categoría padre '{parent_name}' no existe en Dolibarr. Créala primero.",
                platform="dolibarr",
            )
        parent_id = int(parent["id"])
        existing = await self.find_category_by_name_and_parent(subcat_name, parent_id, type=type)
        if existing:
            logger.debug(
                "Subcategoría Dolibarr encontrada",
                extra={"name": subcat_name, "parent_id": parent_id},
            )
            return existing
        created = await self.create_category(subcat_name, type=type, parent_id=parent_id)
        logger.info(
            "Subcategoría Dolibarr creada automáticamente",
            extra={"name": subcat_name, "parent_name": parent_name},
        )
        return created

    async def list_products_in_category(
        self,
        category_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """
        Lista los productos asignados a una categoría.
        Dolibarr endpoint: GET /categories/{id}/objects?type=product

        Args:
            category_id: ID de la categoría.
            limit: Resultados por página.
            offset: Offset para paginación.

        Returns:
            Lista de productos en la categoría.
        """
        resource = f"{_DOLIBARR_CATEGORIES_RESOURCE}/{category_id}/{_DOLIBARR_CATEGORY_OBJECTS_RESOURCE}"
        filters = {"type": "product"}
        return await self._client.list(resource, limit=limit, offset=offset, filters=filters)
