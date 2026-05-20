"""
Servicio de gestión de productos WooCommerce.

Cubre productos simples, variables y agrupados.
Sincronización desde job Harvist → WooCommerce.

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from loguru import logger

from services.integrations.base import IntegrationError
from services.integrations.wordpress.client import WordPressClient

if TYPE_CHECKING:
    from services.integrations.wordpress.brands import WordPressBrandService
    from services.integrations.wordpress.categories import WordPressCategoryService


# ── Helpers CSV (sin dependencias externas) ───────────────────────────────────

def _decode_csv(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def _detect_delimiter(text: str) -> str:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        first_line = sample.split("\n")[0]
        counts = {d: first_line.count(d) for d in (";", ",", "\t", "|")}
        best = max(counts, key=lambda d: counts[d])
        return best if counts[best] > 0 else ","


# Campos WooCommerce soportados en la importación CSV.
WC_IMPORT_FIELDS: list[dict[str, str]] = [
    {"key": "name", "label": "Nombre del producto"},
    {"key": "sku", "label": "SKU / Referencia"},
    {"key": "slug", "label": "Slug URL"},
    {"key": "type", "label": "Tipo (simple/variable/grouped/external)"},
    {"key": "regular_price", "label": "Precio regular"},
    {"key": "sale_price", "label": "Precio de oferta"},
    {"key": "description", "label": "Descripción larga"},
    {"key": "short_description", "label": "Descripción corta"},
    {"key": "weight", "label": "Peso"},
    {"key": "status", "label": "Estado (publish/draft)"},
    {"key": "stock_quantity", "label": "Cantidad en stock"},
    {"key": "stock_status", "label": "Estado de stock (instock/outofstock/onbackorder)"},
    {"key": "dimensions_length", "label": "Longitud (cm)"},
    {"key": "dimensions_width", "label": "Anchura (cm)"},
    {"key": "dimensions_height", "label": "Altura (cm)"},
]


class WordPressProductService:
    """
    Servicio CRUD para productos WooCommerce.

    :author: Carlitos6712
    """

    _RESOURCE = "products"

    def __init__(self, client: WordPressClient) -> None:
        """
        Args:
            client: instancia de WordPressClient ya configurada.
        """
        self._client = client

    async def list(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str = "any",
        category: int | None = None,
        search: str = "",
    ) -> list[dict[str, Any]]:
        """
        Lista productos de WooCommerce con paginación y filtros opcionales.

        Args:
            limit: elementos por página.
            offset: desplazamiento.
            status: filtro de estado ("any", "publish", "draft", "private").
            category: ID de categoría para filtrar.
            search: término de búsqueda.

        Returns:
            Lista de dicts con los productos.
        """
        filters: dict[str, Any] = {"status": status}
        if category is not None:
            filters["category"] = category
        if search:
            filters["search"] = search
        return await self._client.list(self._RESOURCE, limit=limit, offset=offset, filters=filters)

    async def get(self, product_id: int) -> dict[str, Any]:
        """
        Obtiene un producto por su ID.

        Args:
            product_id: ID del producto en WooCommerce.

        Returns:
            Dict con los datos del producto.

        Raises:
            IntegrationError: si el producto no existe.
        """
        return await self._client.get(self._RESOURCE, product_id)

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Crea un producto en WooCommerce.

        Args:
            data: campos del producto (name, type, regular_price, sku, etc.).

        Returns:
            Dict con el producto creado incluyendo su ID.
        """
        result = await self._client.create(self._RESOURCE, data)
        logger.info("Producto WooCommerce creado", extra={"wc_id": result.get("id")})
        return result

    async def update(self, product_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """
        Actualiza un producto existente.

        Args:
            product_id: ID del producto.
            data: campos a actualizar.

        Returns:
            Dict con el producto actualizado.
        """
        result = await self._client.update(self._RESOURCE, product_id, data)
        logger.info("Producto WooCommerce actualizado", extra={"wc_id": product_id})
        return result

    async def delete(self, product_id: int) -> bool:
        """
        Elimina un producto de WooCommerce (force=true).

        Args:
            product_id: ID del producto.

        Returns:
            True si se eliminó correctamente.
        """
        result = await self._client.delete(self._RESOURCE, product_id)
        logger.info("Producto WooCommerce eliminado", extra={"wc_id": product_id})
        return result

    async def find_by_sku(self, sku: str) -> dict[str, Any] | None:
        """
        Busca un producto por SKU. Devuelve None si no existe.

        Args:
            sku: referencia del producto.

        Returns:
            Dict del producto o None si no se encuentra.
        """
        items = await self._client.list(self._RESOURCE, filters={"sku": sku})
        return items[0] if items else None

    async def set_image(self, product_id: int, media_id: int) -> dict[str, Any]:
        """
        Asigna una imagen como imagen destacada del producto.

        Args:
            product_id: ID del producto.
            media_id: ID del media item en WordPress Media Library.

        Returns:
            Dict con el producto actualizado.
        """
        return await self.update(product_id, {"images": [{"id": media_id}]})

    async def list_variations(self, product_id: int) -> list[dict[str, Any]]:
        """
        Lista las variantes de un producto variable.

        Args:
            product_id: ID del producto variable.

        Returns:
            Lista de dicts con las variantes.
        """
        return await self._client.list(f"{self._RESOURCE}/{product_id}/variations", limit=100)

    async def create_variation(
        self, product_id: int, data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Crea una variante en un producto variable.

        Args:
            product_id: ID del producto variable.
            data: datos de la variante (attributes, regular_price, sku, stock_quantity, etc.).

        Returns:
            Dict con la variante creada.
        """
        return await self._client.create(f"{self._RESOURCE}/{product_id}/variations", data)

    async def sync_from_harvist(
        self,
        harvist_product: dict[str, Any],
        overwrite: bool = False,
        media_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Sincroniza un producto Harvist a WooCommerce (crea o actualiza por SKU).

        Mapeo Harvist → WooCommerce:
          codigo    → sku
          nombre    → name
          descripcion → description
          precio    → regular_price
          peso      → weight
          imagen (media_id) → images

        Args:
            harvist_product: dict con datos del producto Harvist.
            overwrite: si True, sobreescribe productos existentes.
            media_id: ID del media item ya subido a WordPress.

        Returns:
            Dict del producto creado o actualizado en WooCommerce.
        """
        sku = harvist_product.get("codigo", "")
        payload: dict[str, Any] = {
            "name": harvist_product.get("nombre", ""),
            "sku": sku,
            "description": harvist_product.get("descripcion_larga", ""),
            "short_description": harvist_product.get("descripcion_corta", ""),
            "regular_price": str(harvist_product.get("precio", "")),
            "weight": str(harvist_product.get("peso", "")),
            "status": "publish",
            "type": "simple",
            "manage_stock": True,
        }
        if media_id:
            payload["images"] = [{"id": media_id}]

        existing = await self.find_by_sku(sku)
        if existing:
            if not overwrite:
                logger.info("Producto ya existe en WooCommerce, skipping", extra={"sku": sku})
                return existing
            return await self.update(existing["id"], payload)

        return await self.create(payload)

    @staticmethod
    def parse_csv_preview(content: bytes, preview_rows: int = 5) -> dict[str, Any]:
        """
        Parsea las primeras filas de un CSV para previsualización.

        Detecta delimitador automáticamente. Soporta UTF-8 y latin-1.

        Args:
            content:      contenido raw del archivo CSV.
            preview_rows: número máximo de filas de previsualización.

        Returns:
            Dict con headers, preview (list of dicts) y total_rows.
        """
        text = _decode_csv(content)
        delimiter = _detect_delimiter(text)
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        headers = list(reader.fieldnames or [])
        preview: list[dict[str, str]] = []
        total = 0

        for row in reader:
            total += 1
            if len(preview) < preview_rows:
                preview.append({k: str(v or "") for k, v in row.items() if k is not None})

        return {"headers": headers, "preview": preview, "total_rows": total}

    async def import_from_csv(
        self,
        content: bytes,
        mapping: dict[str, str],
        overwrite: bool = False,
        brand_col: str | None = None,
        brand_svc: "WordPressBrandService | None" = None,
        category_col: str | None = None,
        subcategory_col: str | None = None,
        category_svc: "WordPressCategoryService | None" = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Importa productos en masa a WooCommerce desde un CSV con mapeo de columnas.

        Upsert por SKU: si existe un producto con el mismo SKU se actualiza (si
        overwrite=True) o se omite. El campo ``name`` es obligatorio en el mapping.

        Campos especiales:
          - ``stock_quantity`` activa ``manage_stock=True`` automáticamente.
          - ``dimensions_length/width/height`` se agrupan en el objeto dimensions.
          - ``brand_col`` resuelve la marca por nombre (crea si no existe).
          - ``category_col`` resuelve la categoría raíz por nombre (crea si no existe).
          - ``subcategory_col`` resuelve una subcategoría bajo la categoría de ``category_col``
            (crea padre e hijo si no existen). Requiere que ``category_col`` esté presente.

        Args:
            content:           contenido raw del archivo CSV.
            mapping:           dict columna_csv → campo_woocommerce.
            overwrite:         si True, actualiza productos con SKU existente.
            brand_col:         nombre de la columna CSV con la marca (opcional).
            brand_svc:         servicio de marcas WordPress para resolver nombres.
            category_col:      nombre de la columna CSV con la categoría raíz (opcional).
            subcategory_col:   nombre de la columna CSV con la subcategoría (opcional).
            category_svc:      servicio de categorías WordPress para resolver nombres.
            progress_callback: función opcional (procesados, total) → None.

        Returns:
            Lista de dicts con row, sku, action, wc_id, error.
        """
        text = _decode_csv(content)
        delimiter = _detect_delimiter(text)

        total_rows = 0
        if progress_callback:
            counter_reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
            total_rows = sum(1 for _ in counter_reader)

        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        results: list[dict[str, Any]] = []
        processed_count = 0

        for row_num, row in enumerate(reader, start=2):
            payload: dict[str, Any] = {}
            dim: dict[str, str] = {}

            for csv_col, wc_field in mapping.items():
                raw_val = (row.get(csv_col) or "").strip()
                if not raw_val:
                    continue
                if wc_field.startswith("dimensions_"):
                    dim_key = wc_field.replace("dimensions_", "")
                    dim[dim_key] = raw_val
                else:
                    payload[wc_field] = raw_val

            if dim:
                payload["dimensions"] = {
                    "length": dim.get("length", ""),
                    "width": dim.get("width", ""),
                    "height": dim.get("height", ""),
                }

            if "stock_quantity" in payload:
                payload["manage_stock"] = True
                try:
                    payload["stock_quantity"] = int(float(payload["stock_quantity"]))
                except (ValueError, TypeError):
                    payload.pop("stock_quantity")

            name = str(payload.get("name", "")).strip()
            sku = str(payload.get("sku", "")).strip()

            result: dict[str, Any] = {
                "row": row_num,
                "sku": sku or name[:30],
                "action": None,
                "wc_id": None,
                "error": None,
            }

            if not name:
                result["action"] = "error"
                result["error"] = "El campo 'name' es obligatorio."
                results.append(result)
                processed_count += 1
                if progress_callback and processed_count % 10 == 0:
                    progress_callback(processed_count, total_rows)
                continue

            try:
                # Resolver marca por nombre
                if brand_col and brand_svc:
                    brand_name = (row.get(brand_col) or "").strip()
                    if brand_name:
                        try:
                            brand = await brand_svc.find_or_create_by_name(brand_name)
                            payload["brands"] = [{"id": brand["id"]}]
                        except Exception as exc:
                            logger.warning("Error resolviendo marca WP", exc_info=exc, extra={"brand": brand_name})

                # Resolver categoría / subcategoría por nombre
                if category_col and category_svc:
                    cat_name = (row.get(category_col) or "").strip()
                    subcat_name = (row.get(subcategory_col) or "").strip() if subcategory_col else ""
                    if cat_name:
                        try:
                            if subcat_name:
                                cat = await category_svc.find_or_create_subcategory(cat_name, subcat_name)
                            else:
                                cat = await category_svc.find_or_create(cat_name)
                            payload["categories"] = [{"id": cat["id"]}]
                        except Exception as exc:
                            logger.warning(
                                "Error resolviendo categoría WP",
                                exc_info=exc,
                                extra={"cat": cat_name, "subcat": subcat_name},
                            )

                if sku:
                    existing = await self.find_by_sku(sku)
                    if existing:
                        if overwrite:
                            updated = await self.update(existing["id"], payload)
                            result["action"] = "updated"
                            result["wc_id"] = updated.get("id")
                        else:
                            result["action"] = "skipped"
                            result["wc_id"] = existing.get("id")
                    else:
                        created = await self.create(payload)
                        result["action"] = "created"
                        result["wc_id"] = created.get("id")
                else:
                    created = await self.create(payload)
                    result["action"] = "created"
                    result["wc_id"] = created.get("id")

            except Exception as exc:
                logger.error("Error importando fila CSV a WooCommerce", exc_info=exc, extra={"row": row_num})
                result["action"] = "error"
                result["error"] = str(exc)

            results.append(result)
            processed_count += 1
            if progress_callback and processed_count % 10 == 0:
                progress_callback(processed_count, total_rows)

        if progress_callback:
            progress_callback(processed_count, total_rows)

        return results
