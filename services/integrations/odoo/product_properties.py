"""
Servicio de gestión de Properties (campos extra) de productos en Odoo 17.

En Odoo 17, los campos extra de productos usan el sistema "Properties":
  - product.category.product_properties_definition: define qué propiedades existen.
    Array de objetos {name (hex 16 chars), type, string, default, view_in_cards}.
  - product.template.product_properties: valores por producto.
    Misma estructura con campo extra "value". Solo aparecen propiedades con valor.

El campo "name" hex actúa como FK lógica entre ambos JSON.

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

import secrets
from typing import Any, Literal

from loguru import logger

from services.integrations.base import IntegrationClient, IntegrationError

OdooPropertyType = Literal["char", "integer", "float", "boolean", "date", "many2one", "tags"]

_UPDATABLE_FIELDS = {"string", "default", "view_in_cards"}


class OdooProductPropertiesService:
    """
    Servicio CRUD para Properties de productos en Odoo 17.

    Gestiona las definiciones en product.category y los valores en
    product.template a través del cliente XML-RPC existente.

    :author: Carlitos6712
    """

    def __init__(self, client: IntegrationClient) -> None:
        """
        Args:
            client: cliente Odoo autenticado (debe ser OdooClient).
        """
        self._client = client

    # ── Helpers privados ────────────────────────────────────────────────────

    @staticmethod
    def _generate_prop_name() -> str:
        """Genera un identificador hex único de 16 caracteres para una propiedad."""
        return secrets.token_hex(8)

    def _require_odoo_client(self) -> None:
        """
        Raises:
            IntegrationError: si el cliente no es OdooClient.
        """
        from services.integrations.odoo.client import OdooClient
        if not isinstance(self._client, OdooClient):
            raise IntegrationError(
                "Properties solo disponible con OdooClient XML-RPC",
                platform="odoo",
            )

    async def _read_category_definitions(self, category_id: int) -> list[dict[str, Any]]:
        """
        Lee product_properties_definition de una categoría.

        Args:
            category_id: ID de product.category.

        Returns:
            Lista de definiciones (vacía si no tiene ninguna).

        Raises:
            IntegrationError: si la categoría no existe.
        """
        from services.integrations.odoo.client import OdooClient
        client: OdooClient = self._client  # type: ignore[assignment]
        result = await client._execute(
            "product.category", "read", [[category_id]],
            {"fields": ["product_properties_definition"]},
        )
        if not result:
            raise IntegrationError(
                f"Categoría Odoo {category_id} no encontrada",
                platform="odoo",
                status_code=404,
            )
        raw = result[0].get("product_properties_definition") or []
        return list(raw) if isinstance(raw, (list, tuple)) else []

    async def _write_category_definitions(
        self, category_id: int, definitions: list[dict[str, Any]]
    ) -> None:
        """
        Escribe la lista completa de definiciones en la categoría.

        Args:
            category_id: ID de product.category.
            definitions: lista de dicts de definición.
        """
        from services.integrations.odoo.client import OdooClient
        client: OdooClient = self._client  # type: ignore[assignment]
        await client._execute(
            "product.category", "write",
            [[category_id], {"product_properties_definition": definitions}],
        )

    async def _read_product_properties(self, product_id: int) -> list[dict[str, Any]]:
        """
        Lee product_properties de un producto.

        Args:
            product_id: ID de product.template.

        Returns:
            Lista de valores de propiedades.

        Raises:
            IntegrationError: si el producto no existe.
        """
        from services.integrations.odoo.client import OdooClient
        client: OdooClient = self._client  # type: ignore[assignment]
        result = await client._execute(
            "product.template", "read", [[product_id]],
            {"fields": ["product_properties"]},
        )
        if not result:
            raise IntegrationError(
                f"Producto Odoo {product_id} no encontrado",
                platform="odoo",
                status_code=404,
            )
        raw = result[0].get("product_properties") or []
        return list(raw) if isinstance(raw, (list, tuple)) else []

    async def _write_product_properties(
        self, product_id: int, properties: list[dict[str, Any]]
    ) -> None:
        """
        Escribe la lista completa de valores en el producto.

        Args:
            product_id: ID de product.template.
            properties: lista de dicts de valor.
        """
        from services.integrations.odoo.client import OdooClient
        client: OdooClient = self._client  # type: ignore[assignment]
        await client._execute(
            "product.template", "write",
            [[product_id], {"product_properties": properties}],
        )

    # ── Definiciones de categoría ───────────────────────────────────────────

    async def get_category_properties(self, category_id: int) -> list[dict[str, Any]]:
        """
        Obtiene las definiciones de propiedades de una categoría.

        Args:
            category_id: ID de product.category.

        Returns:
            Lista de definiciones ordenada por posición.

        Raises:
            IntegrationError: si la categoría no existe o Odoo falla.
        """
        self._require_odoo_client()
        try:
            defs = await self._read_category_definitions(category_id)
            logger.debug(
                "Definiciones Properties leídas",
                extra={"category_id": category_id, "count": len(defs)},
            )
            return defs
        except IntegrationError:
            raise
        except Exception as exc:
            logger.error("Error leyendo Properties de categoría", exc_info=exc, extra={"category_id": category_id})
            raise IntegrationError("Fallo leyendo Properties de categoría Odoo") from exc

    async def add_category_property(
        self,
        category_id: int,
        prop_type: OdooPropertyType,
        string: str,
        default: Any = "",
        view_in_cards: bool = False,
    ) -> dict[str, Any]:
        """
        Añade una nueva definición de propiedad a una categoría.

        Genera un identificador hex único de 16 caracteres y lo anexa
        al array product_properties_definition de la categoría.

        Args:
            category_id:   ID de product.category.
            prop_type:     tipo de dato (char/integer/float/boolean/date/many2one/tags).
            string:        etiqueta visible en la UI de Odoo.
            default:       valor por defecto.
            view_in_cards: mostrar en vistas kanban.

        Returns:
            Nueva definición con el name hex generado.

        Raises:
            IntegrationError: si la categoría no existe o falla la escritura.
        """
        self._require_odoo_client()
        try:
            defs = await self._read_category_definitions(category_id)
            new_def: dict[str, Any] = {
                "name": self._generate_prop_name(),
                "type": prop_type,
                "string": string,
                "default": default,
                "view_in_cards": view_in_cards,
            }
            defs.append(new_def)
            await self._write_category_definitions(category_id, defs)
            logger.info(
                "Propiedad añadida a categoría Odoo",
                extra={"category_id": category_id, "prop_name": new_def["name"], "type": prop_type},
            )
            return new_def
        except IntegrationError:
            raise
        except Exception as exc:
            logger.error("Error añadiendo propiedad a categoría", exc_info=exc, extra={"category_id": category_id})
            raise IntegrationError("Fallo añadiendo propiedad a categoría Odoo") from exc

    async def update_category_property(
        self,
        category_id: int,
        prop_name: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Actualiza una definición de propiedad existente en la categoría.

        Solo se permiten actualizar: string, default, view_in_cards.
        El tipo no puede cambiarse (estructura de datos en Odoo).

        Args:
            category_id: ID de product.category.
            prop_name:   identificador hex de 16 chars de la propiedad.
            updates:     campos a actualizar (string, default, view_in_cards).

        Returns:
            Definición actualizada.

        Raises:
            IntegrationError: si no existe la propiedad o falla.
        """
        self._require_odoo_client()
        try:
            defs = await self._read_category_definitions(category_id)
            for i, d in enumerate(defs):
                if d.get("name") == prop_name:
                    for k, v in updates.items():
                        if k in _UPDATABLE_FIELDS:
                            defs[i][k] = v
                    await self._write_category_definitions(category_id, defs)
                    logger.info(
                        "Propiedad de categoría actualizada",
                        extra={"category_id": category_id, "prop_name": prop_name},
                    )
                    return defs[i]
            raise IntegrationError(
                f"Propiedad '{prop_name}' no encontrada en categoría {category_id}",
                platform="odoo",
                status_code=404,
            )
        except IntegrationError:
            raise
        except Exception as exc:
            logger.error("Error actualizando propiedad de categoría", exc_info=exc)
            raise IntegrationError("Fallo actualizando propiedad de categoría Odoo") from exc

    async def delete_category_property(self, category_id: int, prop_name: str) -> None:
        """
        Elimina una definición de propiedad de la categoría.

        Esto implica que Odoo también perderá los valores de esa propiedad
        en todos los productos de la categoría (comportamiento nativo de Odoo).

        Args:
            category_id: ID de product.category.
            prop_name:   identificador hex de 16 chars.

        Raises:
            IntegrationError: si no existe la propiedad o falla.
        """
        self._require_odoo_client()
        try:
            defs = await self._read_category_definitions(category_id)
            original_count = len(defs)
            defs = [d for d in defs if d.get("name") != prop_name]
            if len(defs) == original_count:
                raise IntegrationError(
                    f"Propiedad '{prop_name}' no encontrada en categoría {category_id}",
                    platform="odoo",
                    status_code=404,
                )
            await self._write_category_definitions(category_id, defs)
            logger.info(
                "Propiedad eliminada de categoría",
                extra={"category_id": category_id, "prop_name": prop_name},
            )
        except IntegrationError:
            raise
        except Exception as exc:
            logger.error("Error eliminando propiedad de categoría", exc_info=exc)
            raise IntegrationError("Fallo eliminando propiedad de categoría Odoo") from exc

    # ── Valores de producto ─────────────────────────────────────────────────

    async def get_product_properties(
        self,
        product_id: int,
        category_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Obtiene los valores de propiedades de un producto.

        Si se proporciona category_id, fusiona los valores existentes con
        las definiciones de la categoría para incluir también propiedades
        sin valor asignado (usando el default como valor).

        Args:
            product_id:  ID de product.template.
            category_id: ID de product.category para hacer merge con definiciones.

        Returns:
            Lista de dicts {name, type, string, value}.

        Raises:
            IntegrationError: si el producto no existe o Odoo falla.
        """
        self._require_odoo_client()
        try:
            values = await self._read_product_properties(product_id)
            if category_id is None:
                return values

            defs = await self._read_category_definitions(category_id)
            values_by_name = {v["name"]: v for v in values}
            merged: list[dict[str, Any]] = []
            for d in defs:
                name = d["name"]
                if name in values_by_name:
                    merged.append(values_by_name[name])
                else:
                    merged.append({
                        "name": name,
                        "type": d["type"],
                        "string": d["string"],
                        "value": d.get("default", ""),
                    })
            return merged
        except IntegrationError:
            raise
        except Exception as exc:
            logger.error("Error leyendo Properties de producto", exc_info=exc, extra={"product_id": product_id})
            raise IntegrationError("Fallo leyendo Properties de producto Odoo") from exc

    async def set_product_properties(
        self,
        product_id: int,
        props: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Establece múltiples valores de propiedades en un producto.

        Merge sobre valores existentes: actualiza si ya existe, añade si no.
        Las propiedades no mencionadas se mantienen sin cambios.

        Args:
            product_id: ID de product.template.
            props:      lista de dicts {name, type, string, value}.

        Returns:
            Lista completa de valores actualizada.

        Raises:
            IntegrationError: si falla la escritura.
        """
        self._require_odoo_client()
        try:
            existing = await self._read_product_properties(product_id)
            existing_by_name = {p["name"]: p for p in existing}
            for prop in props:
                name = prop.get("name")
                if not name:
                    continue
                if name in existing_by_name:
                    existing_by_name[name]["value"] = prop.get("value", "")
                    if "string" in prop:
                        existing_by_name[name]["string"] = prop["string"]
                else:
                    existing_by_name[name] = {
                        "name": name,
                        "type": prop.get("type", "char"),
                        "string": prop.get("string", name),
                        "value": prop.get("value", ""),
                    }
            updated = list(existing_by_name.values())
            await self._write_product_properties(product_id, updated)
            logger.info(
                "Properties de producto actualizadas",
                extra={"product_id": product_id, "count": len(props)},
            )
            return updated
        except IntegrationError:
            raise
        except Exception as exc:
            logger.error("Error escribiendo Properties de producto", exc_info=exc, extra={"product_id": product_id})
            raise IntegrationError("Fallo escribiendo Properties de producto Odoo") from exc

    async def delete_product_property(
        self,
        product_id: int,
        prop_name: str,
    ) -> list[dict[str, Any]]:
        """
        Elimina el valor de una propiedad en un producto.

        Args:
            product_id: ID de product.template.
            prop_name:  identificador hex de 16 chars.

        Returns:
            Lista de valores actualizada.

        Raises:
            IntegrationError: si no existe el valor o falla.
        """
        self._require_odoo_client()
        try:
            existing = await self._read_product_properties(product_id)
            original_count = len(existing)
            updated = [p for p in existing if p.get("name") != prop_name]
            if len(updated) == original_count:
                raise IntegrationError(
                    f"Propiedad '{prop_name}' no tiene valor en producto {product_id}",
                    platform="odoo",
                    status_code=404,
                )
            await self._write_product_properties(product_id, updated)
            logger.info(
                "Valor de propiedad eliminado de producto",
                extra={"product_id": product_id, "prop_name": prop_name},
            )
            return updated
        except IntegrationError:
            raise
        except Exception as exc:
            logger.error("Error eliminando valor de propiedad", exc_info=exc, extra={"product_id": product_id})
            raise IntegrationError("Fallo eliminando valor de propiedad en producto Odoo") from exc
