"""
Módulo de gestión de categorías en Dolibarr.
Soporta categorías de producto, cliente y proveedor.

:author: Carlitos6712
:version: 1.0.0
"""

from typing import Literal

from services.integrations.base import IntegrationClient


CATEGORY_TYPES = Literal["product", "customer", "supplier", "member"]
_DOLIBARR_CATEGORIES_RESOURCE = "categories"
_DOLIBARR_CATEGORY_OBJECTS_RESOURCE = "objects"


class DolibarrCategoryService:
    """
    Servicio de categorías para Dolibarr.
    Maneja CRUD, árbol jerárquico y asignación de productos.

    :author: Carlitos6712
    """

    def __init__(self, client: IntegrationClient) -> None:
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

        # Construir árbol en memoria
        categories_by_id = {cat["id"]: {**cat, "children": []} for cat in all_categories}
        roots = []

        for cat in all_categories:
            parent_id = cat.get("fk_parent", None)
            if parent_id is None or parent_id == 0 or parent_id not in categories_by_id:
                roots.append(categories_by_id[cat["id"]])
            else:
                categories_by_id[parent_id]["children"].append(categories_by_id[cat["id"]])

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
        Dolibarr endpoint: POST /categories/{id}/objects
        Body: { "type": "product", "id": product_id }

        Args:
            category_id: ID de la categoría.
            product_id: ID del producto a asignar.

        Returns:
            True si éxito.
        """
        data = {"type": "product", "id": product_id}
        result = await self._client.create(
            f"{_DOLIBARR_CATEGORIES_RESOURCE}/{category_id}/{_DOLIBARR_CATEGORY_OBJECTS_RESOURCE}",
            data,
        )
        return bool(result)

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
        """
        resource = f"{_DOLIBARR_CATEGORIES_RESOURCE}/{category_id}/{_DOLIBARR_CATEGORY_OBJECTS_RESOURCE}/{product_id}"
        return await self._client.delete(resource, None)

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
