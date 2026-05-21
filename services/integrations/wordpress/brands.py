"""
Servicio de gestión de marcas WooCommerce.

Soporta dos backends de marcas:

**Nativo (prioritario):**
  WooCommerce 8.6+ o plugin WooCommerce Brands instala el endpoint
  ``/wc/v3/products/brands`` con taxonomía ``product_brand``.
  En este modo las marcas se gestionan directamente por ese endpoint
  y se asignan a productos via el campo ``brands: [{id}]``.

**Atributo (fallback):**
  Marcas modeladas como términos de un atributo global de producto.
  El atributo se detecta por slug (brand, pa_brand, marca, pa_marca…)
  o por nombre que contenga "brand"/"marca". Si no existe se crea.

La detección es automática: se intenta el endpoint nativo primero;
si devuelve 404 se cae al modo atributo. El resultado se cachea
por instancia.

:author: BenjaminDTS
:version: 2.0.0
"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from services.integrations.base import IntegrationError
from services.integrations.wordpress.client import WordPressClient

_BRAND_ATTR_SLUG = "brand"
_BRAND_ATTR_NAME = "Marca"

_BRAND_SLUG_CANDIDATES: frozenset[str] = frozenset({
    "brand", "pa_brand",
    "marca", "pa_marca",
    "brands", "pa_brands",
    "marcas", "pa_marcas",
})
_BRAND_NAME_KEYWORDS: frozenset[str] = frozenset({"brand", "marca"})

_NATIVE_RESOURCE = "products/brands"


class WordPressBrandService:
    """
    Servicio CRUD para marcas WooCommerce.

    Auto-detecta si el sitio usa el endpoint nativo ``products/brands``
    (WooCommerce 8.6+ / plugin Brands) y lo usa; si no existe cae al
    modo de atributo global (pa_brand / pa_marca).

    :author: BenjaminDTS
    """

    def __init__(
        self,
        client: WordPressClient,
        attr_id_override: int | None = None,
        use_native_override: bool | None = None,
    ) -> None:
        """
        Args:
            client:              WordPressClient ya configurado.
            attr_id_override:    Fuerza un ID de atributo concreto (modo atributo).
            use_native_override: True/False fuerza el modo; None = auto-detectar.
        """
        self._client = client
        self._attr_id: int | None = attr_id_override
        self._use_native: bool | None = use_native_override
        self._cache: dict[str, dict[str, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    # ── Detección de backend ─────────────────────────────────────────────────

    async def _native_available(self) -> bool:
        """
        Comprueba si el endpoint nativo de marcas está disponible.

        Cachea el resultado por instancia para no repetir la petición.

        Returns:
            True si ``/wc/v3/products/brands`` responde con 2xx.
        """
        if self._use_native is not None:
            return self._use_native
        try:
            await self._client.list(_NATIVE_RESOURCE, limit=1)
            self._use_native = True
            logger.debug("WooCommerce native brands endpoint detectado")
        except IntegrationError:
            self._use_native = False
            logger.debug("WooCommerce native brands no disponible, usando atributo")
        return self._use_native

    # ── Modo atributo: helpers ───────────────────────────────────────────────

    async def _get_attribute_id(self) -> int:
        """
        Detecta o crea el atributo global de marca en WooCommerce.

        Estrategia (en orden):
          1. Override externo.
          2. Slug exacto en ``_BRAND_SLUG_CANDIDATES``.
          3. Nombre del atributo contiene "brand"/"marca"; mayor ``term_count`` gana.
          4. Creación de nuevo atributo "brand" (pa_brand).

        Returns:
            ID del atributo de producto para marcas.
        """
        if self._attr_id is not None:
            return self._attr_id

        attrs: list[dict[str, Any]] = await self._client.list("products/attributes", limit=100)

        for attr in attrs:
            if attr.get("slug", "").lower() in _BRAND_SLUG_CANDIDATES:
                self._attr_id = int(attr["id"])
                logger.debug(
                    "Atributo marca detectado por slug",
                    extra={"attr_id": self._attr_id, "slug": attr.get("slug")},
                )
                return self._attr_id

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

    # ── CRUD público ─────────────────────────────────────────────────────────

    async def list(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """
        Lista las marcas disponibles en WooCommerce.

        Args:
            limit: máximo de marcas a retornar.
            offset: desplazamiento para paginación.

        Returns:
            Lista de dicts con id, name, slug, count/term_count, description.
        """
        if await self._native_available():
            return await self._client.list(_NATIVE_RESOURCE, limit=limit, offset=offset)
        attr_id = await self._get_attribute_id()
        return await self._client.list(self._terms_resource(attr_id), limit=limit, offset=offset)

    async def get(self, brand_id: int) -> dict[str, Any]:
        """
        Obtiene una marca por su ID.

        Args:
            brand_id: ID de la marca WooCommerce.

        Returns:
            Dict con los datos de la marca.
        """
        if await self._native_available():
            return await self._client.get(_NATIVE_RESOURCE, brand_id)
        attr_id = await self._get_attribute_id()
        return await self._client.get(self._terms_resource(attr_id), brand_id)

    async def create(self, name: str, description: str = "") -> dict[str, Any]:
        """
        Crea una nueva marca en WooCommerce.

        Args:
            name: nombre de la marca.
            description: descripción opcional.

        Returns:
            Dict con la marca creada.

        Raises:
            IntegrationError: si la creación falla.
        """
        data: dict[str, Any] = {"name": name}
        if description:
            data["description"] = description

        if await self._native_available():
            result = await self._client.create(_NATIVE_RESOURCE, data)
        else:
            attr_id = await self._get_attribute_id()
            result = await self._client.create(self._terms_resource(attr_id), data)

        logger.info("Marca WooCommerce creada", extra={"brand_id": result.get("id"), "name": name})
        return result

    async def update(self, brand_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """
        Actualiza una marca existente.

        Args:
            brand_id: ID de la marca.
            data: campos a actualizar (name, description, slug).

        Returns:
            Dict con la marca actualizada.
        """
        if await self._native_available():
            result = await self._client.update(_NATIVE_RESOURCE, brand_id, data)
        else:
            attr_id = await self._get_attribute_id()
            result = await self._client.update(self._terms_resource(attr_id), brand_id, data)

        logger.info("Marca WooCommerce actualizada", extra={"brand_id": brand_id})
        return result

    async def delete(self, brand_id: int) -> bool:
        """
        Elimina una marca de WooCommerce.

        Args:
            brand_id: ID de la marca a eliminar.

        Returns:
            True si se eliminó correctamente.
        """
        if await self._native_available():
            result = await self._client.delete(_NATIVE_RESOURCE, brand_id)
        else:
            attr_id = await self._get_attribute_id()
            result = await self._client.delete(self._terms_resource(attr_id), brand_id)

        logger.info("Marca WooCommerce eliminada", extra={"brand_id": brand_id})
        return result

    async def list_all_attributes(self) -> list[dict[str, Any]]:
        """
        Lista todos los atributos globales de WooCommerce.

        Returns:
            Lista de atributos con id, name, slug, term_count.
        """
        return await self._client.list("products/attributes", limit=100)

    async def get_attribute_info(self) -> dict[str, Any]:
        """
        Devuelve metadatos del backend de marcas activo.

        Incluye el campo ``use_native`` para que el frontend sepa qué
        campo usar al asignar marcas a productos (``brands`` vs ``attributes``).

        Returns:
            Dict con id, slug, name, use_native.
        """
        if await self._native_available():
            return {
                "id": 0,
                "slug": "product_brand",
                "name": "Brands (nativo WooCommerce)",
                "use_native": True,
            }
        attr_id = await self._get_attribute_id()
        attrs: list[dict[str, Any]] = await self._client.list("products/attributes", limit=100)
        for attr in attrs:
            if int(attr["id"]) == attr_id:
                return {**attr, "use_native": False}
        return {
            "id": attr_id,
            "slug": f"pa_{_BRAND_ATTR_SLUG}",
            "name": _BRAND_ATTR_NAME,
            "use_native": False,
        }

    async def get_products(
        self,
        brand_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Lista los productos que tienen asignada una marca concreta.

        Args:
            brand_id: ID de la marca.
            limit: máximo de productos.
            offset: desplazamiento.

        Returns:
            Lista de productos WooCommerce con la marca especificada.
        """
        if await self._native_available():
            return await self._client.list(
                "products",
                limit=limit,
                offset=offset,
                filters={"brand": brand_id},
            )
        attr_id = await self._get_attribute_id()
        return await self._client.list(
            "products",
            limit=limit,
            offset=offset,
            filters={
                "attribute": f"pa_{_BRAND_ATTR_SLUG}",
                "attribute_term": brand_id,
            },
        )

    async def find_or_create_by_name(self, name: str) -> dict[str, Any]:
        """
        Busca una marca por nombre exacto (case-insensitive) via API search. Si no existe, la crea.

        Thread-safe: usa lock por nombre para evitar duplicados en sync concurrente.

        Args:
            name: nombre de la marca a buscar o crear.

        Returns:
            Dict con los datos de la marca (id, name, slug).
        """
        key = name.lower()

        if key in self._cache:
            return self._cache[key]

        if key not in self._locks:
            self._locks[key] = asyncio.Lock()

        async with self._locks[key]:
            if key in self._cache:
                return self._cache[key]

            if await self._native_available():
                candidates = await self._client.list(
                    _NATIVE_RESOURCE, limit=10, filters={"search": name}
                )
            else:
                attr_id = await self._get_attribute_id()
                candidates = await self._client.list(
                    self._terms_resource(attr_id), limit=10, filters={"search": name}
                )

            for brand in candidates:
                if brand.get("name", "").lower() == key:
                    self._cache[key] = brand
                    return brand

            try:
                created = await self.create(name)
                self._cache[key] = created
                return created
            except IntegrationError:
                # Reintento si otra corutina la creó entre el search y el create.
                if await self._native_available():
                    candidates2 = await self._client.list(
                        _NATIVE_RESOURCE, limit=10, filters={"search": name}
                    )
                else:
                    attr_id = await self._get_attribute_id()
                    candidates2 = await self._client.list(
                        self._terms_resource(attr_id), limit=10, filters={"search": name}
                    )
                for brand in candidates2:
                    if brand.get("name", "").lower() == key:
                        self._cache[key] = brand
                        return brand
                raise
