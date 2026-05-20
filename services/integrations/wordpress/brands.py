"""
Servicio de gestión de marcas WooCommerce via atributo global de producto.

Las marcas se modelan como términos de un atributo de producto WooCommerce.
El atributo se detecta automáticamente buscando por slug conocidos (brand,
pa_brand, marca, pa_marca, …) o por nombre que contenga "brand"/"marca".
Si no existe ninguno se crea un atributo "brand" (pa_brand).

El ID del atributo puede fijarse externamente mediante set_attribute_override()
para sobrescribir la detección automática.

:author: BenjaminDTS
:version: 1.1.0
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from services.integrations.wordpress.client import WordPressClient

_BRAND_ATTR_SLUG = "brand"
_BRAND_ATTR_NAME = "Marca"

# Slugs comunes para el atributo de marca en WooCommerce (con y sin prefijo pa_)
_BRAND_SLUG_CANDIDATES: frozenset[str] = frozenset({
    "brand", "pa_brand",
    "marca", "pa_marca",
    "brands", "pa_brands",
    "marcas", "pa_marcas",
})

# Palabras clave para detección por nombre del atributo (case-insensitive)
_BRAND_NAME_KEYWORDS: frozenset[str] = frozenset({"brand", "marca"})


class WordPressBrandService:
    """
    Servicio CRUD para marcas WooCommerce (términos del atributo de marca).

    Detecta automáticamente el atributo de marca existente en WooCommerce
    buscando por slug o por nombre. Soporta override manual del ID de atributo.

    :author: BenjaminDTS
    """

    def __init__(self, client: WordPressClient, attr_id_override: int | None = None) -> None:
        """
        Args:
            client:           instancia de WordPressClient ya configurada.
            attr_id_override: ID de atributo forzado externamente (omite detección automática).
        """
        self._client = client
        self._attr_id: int | None = attr_id_override

    async def _get_attribute_id(self) -> int:
        """
        Detecta o crea el atributo de marca en WooCommerce.

        Estrategia de detección (por orden de prioridad):
          1. Override externo via constructor.
          2. Slug exacto en ``_BRAND_SLUG_CANDIDATES``.
          3. Nombre del atributo contiene "brand" o "marca" (case-insensitive);
             si hay varios candidatos, se elige el que más términos tenga.
          4. Creación de un nuevo atributo "brand" (pa_brand).

        Returns:
            ID del atributo de producto para marcas.
        """
        if self._attr_id is not None:
            return self._attr_id

        attrs: list[dict[str, Any]] = await self._client.list("products/attributes", limit=100)

        # Paso 1: coincidencia exacta de slug
        for attr in attrs:
            if attr.get("slug", "").lower() in _BRAND_SLUG_CANDIDATES:
                self._attr_id = int(attr["id"])
                logger.debug(
                    "Atributo marca detectado por slug",
                    extra={"attr_id": self._attr_id, "slug": attr.get("slug")},
                )
                return self._attr_id

        # Paso 2: nombre contiene keyword "brand"/"marca"; preferir mayor term_count
        name_candidates = [
            a for a in attrs
            if any(kw in a.get("name", "").lower() for kw in _BRAND_NAME_KEYWORDS)
        ]
        if name_candidates:
            best = max(name_candidates, key=lambda a: int(a.get("term_count", 0)))
            self._attr_id = int(best["id"])
            logger.debug(
                "Atributo marca detectado por nombre",
                extra={"attr_id": self._attr_id, "name": best.get("name")},
            )
            return self._attr_id

        # Paso 3: crear atributo nuevo
        created = await self._client.create(
            "products/attributes",
            {
                "name": _BRAND_ATTR_NAME,
                "slug": _BRAND_ATTR_SLUG,
                "type": "select",
                "order_by": "name",
                "has_archives": True,
            },
        )
        self._attr_id = int(created["id"])
        logger.info("Atributo marca creado en WooCommerce", extra={"attr_id": self._attr_id})
        return self._attr_id

    def _terms_resource(self, attr_id: int) -> str:
        return f"products/attributes/{attr_id}/terms"

    async def list(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """
        Lista todos los términos de marca (pa_brand).

        Args:
            limit: máximo de términos a retornar.
            offset: desplazamiento para paginación.

        Returns:
            Lista de dicts con id, name, slug, count, description.
        """
        attr_id = await self._get_attribute_id()
        return await self._client.list(self._terms_resource(attr_id), limit=limit, offset=offset)

    async def get(self, term_id: int) -> dict[str, Any]:
        """
        Obtiene un término de marca por su ID.

        Args:
            term_id: ID del término WooCommerce.

        Returns:
            Dict con los datos del término.
        """
        attr_id = await self._get_attribute_id()
        return await self._client.get(self._terms_resource(attr_id), term_id)

    async def create(self, name: str, description: str = "") -> dict[str, Any]:
        """
        Crea un nuevo término de marca en WooCommerce.

        Args:
            name: nombre de la marca.
            description: descripción opcional.

        Returns:
            Dict con el término creado.

        Raises:
            IntegrationError: si la creación falla en WooCommerce.
        """
        attr_id = await self._get_attribute_id()
        data: dict[str, Any] = {"name": name}
        if description:
            data["description"] = description
        result = await self._client.create(self._terms_resource(attr_id), data)
        logger.info("Marca WooCommerce creada", extra={"term_id": result.get("id"), "name": name})
        return result

    async def update(self, term_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """
        Actualiza un término de marca existente.

        Args:
            term_id: ID del término.
            data: campos a actualizar (name, description, slug).

        Returns:
            Dict con el término actualizado.
        """
        attr_id = await self._get_attribute_id()
        result = await self._client.update(self._terms_resource(attr_id), term_id, data)
        logger.info("Marca WooCommerce actualizada", extra={"term_id": term_id})
        return result

    async def delete(self, term_id: int) -> bool:
        """
        Elimina un término de marca de WooCommerce.

        Args:
            term_id: ID del término a eliminar.

        Returns:
            True si se eliminó correctamente.
        """
        attr_id = await self._get_attribute_id()
        result = await self._client.delete(self._terms_resource(attr_id), term_id)
        logger.info("Marca WooCommerce eliminada", extra={"term_id": term_id})
        return result

    async def list_all_attributes(self) -> list[dict[str, Any]]:
        """
        Lista todos los atributos de producto globales de WooCommerce.

        Útil para que el usuario identifique cuál de sus atributos corresponde
        a las marcas y pueda configurar el override.

        Returns:
            Lista de atributos con id, name, slug, term_count.
        """
        return await self._client.list("products/attributes", limit=100)

    async def get_attribute_info(self) -> dict[str, Any]:
        """
        Devuelve los metadatos del atributo global pa_brand.

        Útil para que el frontend conozca el ID del atributo y pueda
        construir el payload de ``attributes`` al crear o actualizar productos.

        Returns:
            Dict con id, slug y name del atributo pa_brand.
        """
        attr_id = await self._get_attribute_id()
        attrs: list[dict[str, Any]] = await self._client.list("products/attributes", limit=100)
        for attr in attrs:
            if int(attr["id"]) == attr_id:
                return attr
        return {"id": attr_id, "slug": f"pa_{_BRAND_ATTR_SLUG}", "name": _BRAND_ATTR_NAME}

    async def get_products(
        self,
        term_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Lista los productos que tienen asignada una marca concreta.

        Args:
            term_id: ID del término de marca.
            limit: máximo de productos a retornar.
            offset: desplazamiento para paginación.

        Returns:
            Lista de productos WooCommerce con la marca especificada.
        """
        attr_id = await self._get_attribute_id()
        return await self._client.list(
            "products",
            limit=limit,
            offset=offset,
            filters={
                "attribute": f"pa_{_BRAND_ATTR_SLUG}",
                "attribute_term": term_id,
            },
        )
