"""
Módulo de gestión de campos extra (extrafields) en Dolibarr.

Permite crear, listar y eliminar atributos personalizados para
cualquier tipo de elemento (producto, tercero, factura, etc.).
Los campos creados aquí aparecen de inmediato en la interfaz de Dolibarr.

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from services.integrations.base import IntegrationError
from services.integrations.dolibarr.client import DolibarrClient

if TYPE_CHECKING:
    from services.integrations.dolibarr.extrafields_db import DolibarrExtraFieldDB

_EXTRA_TYPE_MAP: dict[str, str] = {
    "varchar": "text",
    "char": "text",
    "phone": "text",
    "mail": "text",
    "url": "text",
    "int": "number",
    "double": "number",
    "price": "number",
    "date": "date",
    "datetime": "date",
    "select": "select",
    "radio": "select",
    "boolean": "boolean",
    "chkbxlst": "boolean",
    "text": "textarea",
    "html": "textarea",
}

SUPPORTED_TYPES: list[str] = [
    "varchar",
    "int",
    "double",
    "price",
    "date",
    "datetime",
    "select",
    "boolean",
    "text",
    "html",
    "phone",
    "mail",
    "url",
]


class DolibarrExtraFieldService:
    """
    Servicio para gestión de campos extra (extrafields) en Dolibarr.

    Encapsula las operaciones de listado, creación y eliminación de
    atributos personalizados. Los cambios son inmediatamente visibles
    en la interfaz web de Dolibarr.

    :author: Carlitos6712
    """

    def __init__(
        self,
        client: DolibarrClient,
        db_fallback: "DolibarrExtraFieldDB | None" = None,
    ) -> None:
        """
        Args:
            client:      instancia de DolibarrClient configurada y lista para usar.
            db_fallback: instancia de DolibarrExtraFieldDB para usar como fallback
                         cuando la REST API devuelve 501 Not Implemented.
        """
        self._client = client
        self._db = db_fallback

    async def list_extrafields(self, elementtype: str = "product") -> list[dict[str, Any]]:
        """
        Lista los campos extra configurados para un tipo de elemento.

        Cuando la BD directa está configurada, se usa como fuente primaria porque
        los campos creados via ALTER TABLE + INSERT directo no siempre aparecen
        en la REST API de Dolibarr. Solo se recurre a la API si no hay BD configurada.

        Args:
            elementtype: tipo de elemento Dolibarr (product, societe, facture, etc.).

        Returns:
            Lista de dicts normalizados con la definición de cada campo extra.

        Raises:
            IntegrationError: si no hay BD configurada y Dolibarr devuelve error.
        """
        if self._db:
            try:
                db_fields = await self._db.list_extrafields(elementtype=elementtype)
                logger.info(
                    "Extrafields listados via BD directa",
                    extra={"elementtype": elementtype, "count": len(db_fields)},
                )
                return db_fields
            except Exception as db_exc:
                raise IntegrationError(
                    f"Error al conectar con la BD de Dolibarr: {db_exc}",
                    platform="dolibarr",
                    status_code=503,
                ) from db_exc

        # Sin BD configurada: intentar REST API
        response = await self._client._request(
            "GET", "extrafields", params={"attrname": elementtype}
        )

        if response.status_code in (404, 501):
            return []
        if response.status_code >= 400:
            raise IntegrationError(
                f"Error listando extrafields de '{elementtype}'",
                platform="dolibarr",
                status_code=response.status_code,
            )

        raw = response.json()
        fields: list[dict[str, Any]] = []

        if isinstance(raw, dict):
            for key, field_def in raw.items():
                if isinstance(field_def, dict):
                    fields.append(self._normalize(key, field_def))
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and "attrname" in item:
                    fields.append(self._normalize(str(item["attrname"]), item))

        logger.info(
            "Extrafields listados via API REST",
            extra={"elementtype": elementtype, "count": len(fields)},
        )
        return fields

    async def create_extrafield(
        self,
        attrname: str,
        label: str,
        field_type: str = "varchar",
        elementtype: str = "product",
        size: str = "255",
        required: bool = False,
        field_default: str = "",
        param: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Crea un nuevo campo extra en Dolibarr.

        Cuando la BD directa está configurada se usa como fuente primaria (igual
        que list_extrafields), porque la REST API de extrafields no está disponible
        en todas las instalaciones de Dolibarr. Solo se recurre a la API REST si
        no hay BD configurada.

        El campo queda disponible de inmediato en la interfaz de Dolibarr
        y aparece en el formulario dinámico de productos de Harvist.

        Args:
            attrname:      nombre interno del campo (solo minúsculas, sin espacios ni caracteres especiales).
            label:         etiqueta visible en la interfaz.
            field_type:    tipo de campo Dolibarr (varchar, int, double, date, select, boolean, text, html, ...).
            elementtype:   tipo de elemento al que se asocia (product, societe, facture, etc.).
            size:          tamaño del campo (relevante para varchar).
            required:      si el campo es obligatorio.
            field_default: valor por defecto.
            param:         parámetros adicionales, principalmente opciones para tipo select.

        Returns:
            Dict normalizado con la definición del campo recién creado.

        Raises:
            ValueError:        si attrname contiene caracteres inválidos.
            IntegrationError:  si Dolibarr rechaza la creación.
        """
        if not attrname or not attrname.replace("_", "").isalnum():
            raise ValueError(
                f"attrname '{attrname}' inválido: solo letras, números y guión bajo."
            )

        # BD configurada → primaria (mismo comportamiento que list_extrafields)
        if self._db:
            try:
                return await self._db.create_extrafield(
                    attrname=attrname.lower(),
                    label=label,
                    field_type=field_type,
                    elementtype=elementtype,
                    size=size,
                    required=required,
                    field_default=field_default,
                )
            except Exception as db_exc:
                raise IntegrationError(
                    f"Error al crear campo extra en la BD de Dolibarr: {db_exc}",
                    platform="dolibarr",
                    status_code=503,
                ) from db_exc

        # Sin BD configurada → intentar REST API
        payload: dict[str, Any] = {
            "attrname": attrname.lower(),
            "label": label,
            "type": field_type,
            "size": size,
            "elementtype": elementtype,
            "fieldrequired": "1" if required else "0",
            "fieldunique": "0",
            "fielddefault": field_default,
            "param": param or {},
        }

        response = await self._client._request("POST", "extrafields", json=payload)

        if response.status_code == 501:
            raise IntegrationError(
                "Esta versión de Dolibarr no soporta la gestión de campos extra via API REST. "
                "Configura el acceso directo a BD en la pestaña Configuración → BD Dolibarr.",
                platform="dolibarr",
                status_code=501,
            )
        if response.status_code >= 400:
            raise IntegrationError(
                f"Error creando extrafield '{attrname}': {response.text}",
                platform="dolibarr",
                status_code=response.status_code,
            )

        logger.info(
            "Extrafield creado via API REST",
            extra={"attrname": attrname, "elementtype": elementtype, "type": field_type},
        )

        return {
            "attrname": attrname.lower(),
            "label": label,
            "type": field_type,
            "type_normalized": _EXTRA_TYPE_MAP.get(field_type, "text"),
            "elementtype": elementtype,
            "size": size,
            "required": required,
            "fielddefault": field_default,
        }

    async def delete_extrafield(self, attrname: str, elementtype: str = "product") -> bool:
        """
        Elimina un campo extra de Dolibarr.

        Cuando la BD directa está configurada se usa como fuente primaria (mismo
        patrón que list_extrafields y create_extrafield). Solo se recurre a la
        API REST si no hay BD configurada.

        Args:
            attrname:    nombre interno del campo a eliminar.
            elementtype: tipo de elemento al que pertenece el campo.

        Returns:
            True si se eliminó correctamente.

        Raises:
            IntegrationError: si Dolibarr devuelve error al eliminar.
        """
        # BD configurada → primaria
        if self._db:
            try:
                return await self._db.delete_extrafield(attrname=attrname, elementtype=elementtype)
            except Exception as db_exc:
                raise IntegrationError(
                    f"Error al eliminar campo extra en la BD de Dolibarr: {db_exc}",
                    platform="dolibarr",
                    status_code=503,
                ) from db_exc

        # Sin BD → intentar REST API
        response = await self._client._request(
            "DELETE",
            f"extrafields/{attrname}",
            params={"attrname": elementtype},
        )

        if response.status_code in (200, 204):
            logger.info(
                "Extrafield eliminado via API REST",
                extra={"attrname": attrname, "elementtype": elementtype},
            )
            return True

        if response.status_code == 501:
            raise IntegrationError(
                "Esta versión de Dolibarr no soporta la gestión de campos extra via API REST. "
                "Configura el acceso directo a BD en la pestaña Configuración → BD Dolibarr.",
                platform="dolibarr",
                status_code=501,
            )

        raise IntegrationError(
            f"Error eliminando extrafield '{attrname}'",
            platform="dolibarr",
            status_code=response.status_code,
        )

    def _normalize(self, key: str, field_def: dict[str, Any]) -> dict[str, Any]:
        """Normaliza la definición bruta de un extrafield devuelta por Dolibarr."""
        raw_type = str(field_def.get("type", "varchar"))
        return {
            "attrname": key,
            "label": str(field_def.get("label", key)),
            "type": raw_type,
            "type_normalized": _EXTRA_TYPE_MAP.get(raw_type, "text"),
            "elementtype": str(field_def.get("elementtype", "")),
            "size": str(field_def.get("size", "")),
            "required": str(field_def.get("required", "0")) == "1",
            "fielddefault": str(field_def.get("fielddefault", "") or ""),
            "param": field_def.get("param", {}),
        }
