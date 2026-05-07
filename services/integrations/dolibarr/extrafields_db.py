"""
GestiÃ³n de campos extra de Dolibarr via acceso directo a base de datos.

Fallback cuando el endpoint REST /extrafields no estÃ¡ disponible en la
versiÃ³n instalada de Dolibarr. Replica exactamente el comportamiento
del admin de Dolibarr: INSERT en llx_extrafields + ALTER TABLE en la
tabla de datos del elemento.

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

from typing import Any

import aiomysql
from loguru import logger

from api.core.config import Settings

_ELEMENT_TABLE_MAP: dict[str, str] = {
    "product": "product_extrafields",
    "societe": "societe_extrafields",
    "facture": "facture_extrafields",
    "facture_fourn": "facture_fourn_det_extrafields",
    "commande": "commande_extrafields",
    "commande_fournisseur": "commande_fournisseur_det_extrafields",
    "propal": "propal_extrafields",
    "contrat": "contrat_extrafields",
    "user": "user_extrafields",
    "contact": "socpeople_extrafields",
}

_DOLIBARR_TYPE_TO_SQL: dict[str, str] = {
    "varchar": "VARCHAR({size})",
    "char": "VARCHAR({size})",
    "phone": "VARCHAR(20)",
    "mail": "VARCHAR(128)",
    "url": "VARCHAR(255)",
    "int": "INT",
    "double": "DOUBLE",
    "price": "DOUBLE(24,8)",
    "date": "DATE",
    "datetime": "DATETIME",
    "select": "VARCHAR(255)",
    "radio": "VARCHAR(255)",
    "boolean": "SMALLINT",
    "chkbxlst": "VARCHAR(255)",
    "text": "TEXT",
    "html": "TEXT",
}


class DolibarrExtraFieldDB:
    """
    Servicio de gestiÃ³n de campos extra de Dolibarr via MySQL directo.

    Usado como fallback cuando el endpoint REST /extrafields devuelve 501.
    Requiere DOLIBARR_DB_* configurado en .env.

    :author: Carlitos6712
    """

    def __init__(
        self,
        settings: Settings,
        override_host: str = "",
        override_port: int | None = None,
        override_db: str = "",
        override_user: str = "",
        override_pass: str = "",
        override_prefix: str = "",
    ) -> None:
        """
        Prioridad de credenciales: override_* > Settings > error.

        Args:
            settings:        instancia de Settings con credenciales de BD.
            override_host:   host MySQL (sobreescribe .env).
            override_port:   puerto MySQL (sobreescribe .env).
            override_db:     nombre de BD (sobreescribe .env).
            override_user:   usuario MySQL (sobreescribe .env).
            override_pass:   contraseÃ±a MySQL (sobreescribe .env).
            override_prefix: prefijo de tablas (sobreescribe .env).

        Raises:
            ValueError: si no hay credenciales suficientes (host + db + user).
        """
        self._host = (override_host or settings.dolibarr_db_host or "").strip()
        self._port = override_port if override_port is not None else settings.dolibarr_db_port
        self._db = (override_db or settings.dolibarr_db_name or "").strip()
        self._user = (override_user or settings.dolibarr_db_user or "").strip()
        self._pass = (override_pass or settings.dolibarr_db_pass or "").strip()
        self._prefix = (override_prefix or settings.dolibarr_db_prefix or "llx_").strip()

        if not self._host or not self._db or not self._user:
            raise ValueError(
                "BD de Dolibarr no configurada. "
                "Define DOLIBARR_DB_HOST, DOLIBARR_DB_NAME y DOLIBARR_DB_USER en .env "
                "o configÃºralos en la interfaz grÃ¡fica."
            )

    async def _connect(self) -> aiomysql.Connection:
        """Abre una conexiÃ³n MySQL asÃ­ncrona."""
        return await aiomysql.connect(
            host=self._host,
            port=self._port,
            db=self._db,
            user=self._user,
            password=self._pass,
            autocommit=False,
            charset="utf8mb4",
        )

    async def _repair_null_defaults(self, conn: "aiomysql.Connection", data_table: str) -> None:
        """
        Hace nullable todas las columnas NOT NULL sin default en la tabla de datos.

        Usa MODIFY COLUMN (compatible MySQL 5.7+) en lugar de ALTER COLUMN SET DEFAULT NULL,
        que falla para columnas TEXT/BLOB en MySQL 5.7.

        Args:
            conn:       conexiÃ³n MySQL activa.
            data_table: nombre completo de la tabla (p. ej. llx_product_extrafields).
        """
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT COLUMN_NAME, COLUMN_TYPE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = %s
                      AND IS_NULLABLE = 'NO'
                      AND COLUMN_DEFAULT IS NULL
                      AND COLUMN_NAME NOT IN ('rowid', 'fk_object')
                    """,
                    (data_table,),
                )
                bad_cols = [(row[0], row[1]) for row in await cur.fetchall()]

            for col_name, col_type in bad_cols:
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"ALTER TABLE `{data_table}` MODIFY COLUMN `{col_name}` {col_type} NULL"
                    )
                logger.info(
                    "Columna extrafield hecha nullable",
                    extra={"table": data_table, "column": col_name, "type": col_type},
                )
        except Exception:
            logger.opt(exception=True).warning(
                "No se pudo hacer nullable columna extrafield â€” table={}",
                data_table,
            )

    async def list_extrafields(self, elementtype: str = "product") -> list[dict[str, Any]]:
        """
        Lista los campos extra de un elemento desde llx_extrafields.

        TambiÃ©n repara columnas sin DEFAULT NULL en la tabla de datos para
        evitar errores MySQL al actualizar productos con extrafields via REST.

        Args:
            elementtype: tipo de elemento Dolibarr.

        Returns:
            Lista de dicts con la definiciÃ³n de cada campo.
        """
        data_table_key = _ELEMENT_TABLE_MAP.get(elementtype)

        conn = await self._connect()
        try:
            if data_table_key:
                await self._repair_null_defaults(conn, f"{self._prefix}{data_table_key}")

            async with conn.cursor(aiomysql.DictCursor) as cur:
                table = f"{self._prefix}extrafields"
                await cur.execute(
                    f"SELECT * FROM `{table}` WHERE elementtype = %s ORDER BY pos ASC",
                    (elementtype,),
                )
                rows = await cur.fetchall()
                return [self._normalize(r) for r in rows]
        finally:
            conn.close()

    async def create_extrafield(
        self,
        attrname: str,
        label: str,
        field_type: str = "varchar",
        elementtype: str = "product",
        size: str = "255",
        required: bool = False,
        field_default: str = "",
    ) -> dict[str, Any]:
        """
        Crea un campo extra en Dolibarr via BD directa.

        Ejecuta dos operaciones en transacciÃ³n:
          1. INSERT en llx_extrafields (definiciÃ³n del campo)
          2. ALTER TABLE en llx_{element}_extrafields (columna de datos)

        Args:
            attrname:      nombre interno del campo (minÃºsculas, sin espacios).
            label:         etiqueta visible.
            field_type:    tipo Dolibarr (varchar, int, date, select, boolean, text...).
            elementtype:   tipo de elemento (product, societe, etc.).
            size:          tamaÃ±o para tipos varchar.
            required:      si el campo es obligatorio.
            field_default: valor por defecto.

        Returns:
            Dict con la definiciÃ³n del campo creado.

        Raises:
            ValueError: si el tipo no estÃ¡ soportado o el elemento no tiene tabla mapeada.
            RuntimeError: si la transacciÃ³n falla.
        """
        if field_type not in _DOLIBARR_TYPE_TO_SQL:
            raise ValueError(f"Tipo '{field_type}' no soportado. Tipos vÃ¡lidos: {list(_DOLIBARR_TYPE_TO_SQL)}")

        data_table_key = _ELEMENT_TABLE_MAP.get(elementtype)
        if not data_table_key:
            raise ValueError(
                f"Elemento '{elementtype}' no tiene tabla de datos mapeada. "
                f"Elementos soportados: {list(_ELEMENT_TABLE_MAP)}"
            )

        sql_type = _DOLIBARR_TYPE_TO_SQL[field_type].replace("{size}", size)
        def_table = f"{self._prefix}extrafields"
        data_table = f"{self._prefix}{data_table_key}"

        conn = await self._connect()
        try:
            # Repair columns without DEFAULT NULL before any write operation.
            await self._repair_null_defaults(conn, data_table)

            async with conn.cursor() as cur:
                # Some Dolibarr installations have a trigger referencing `hidden`.
                # Ensure the column exists before the INSERT to avoid error 1054.
                await cur.execute(
                    f"ALTER TABLE `{def_table}` ADD COLUMN IF NOT EXISTS `hidden` INT DEFAULT 0"
                )

                await cur.execute(
                    f"""
                    INSERT IGNORE INTO `{def_table}`
                      (name, label, type, size, elementtype,
                       fieldrequired, fieldunique, fielddefault,
                       pos, alwayseditable, entity, enabled, list)
                    VALUES
                      (%s, %s, %s, %s, %s,
                       %s, 0, %s,
                       0, 0, 1, '1', '0')
                    """,
                    (
                        attrname, label, field_type, size, elementtype,
                        1 if required else 0, field_default,
                    ),
                )

                await cur.execute(
                    f"ALTER TABLE `{data_table}` ADD COLUMN IF NOT EXISTS `{attrname}` {sql_type} DEFAULT NULL"
                )

            await conn.commit()

            logger.info(
                "Extrafield creado via BD",
                extra={"attrname": attrname, "elementtype": elementtype, "type": field_type},
            )

            from services.integrations.dolibarr.extrafields import _EXTRA_TYPE_MAP
            return {
                "attrname": attrname,
                "label": label,
                "type": field_type,
                "type_normalized": _EXTRA_TYPE_MAP.get(field_type, "text"),
                "elementtype": elementtype,
                "size": size,
                "required": required,
                "fielddefault": field_default,
            }

        except Exception as exc:
            await conn.rollback()
            logger.error(
                "Error creando extrafield via BD â€” rollback ejecutado",
                exc_info=exc,
                extra={"attrname": attrname, "elementtype": elementtype},
            )
            raise RuntimeError(f"Error creando campo extra '{attrname}': {exc}") from exc
        finally:
            conn.close()

    async def delete_extrafield(self, attrname: str, elementtype: str = "product") -> bool:
        """
        Elimina un campo extra de Dolibarr via BD directa.

        Ejecuta dos operaciones en transacciÃ³n:
          1. DELETE de llx_extrafields
          2. ALTER TABLE DROP COLUMN en llx_{element}_extrafields

        Args:
            attrname:    nombre interno del campo.
            elementtype: tipo de elemento.

        Returns:
            True si se eliminÃ³ correctamente.

        Raises:
            RuntimeError: si la transacciÃ³n falla.
        """
        data_table_key = _ELEMENT_TABLE_MAP.get(elementtype)
        if not data_table_key:
            raise ValueError(f"Elemento '{elementtype}' no tiene tabla de datos mapeada.")

        def_table = f"{self._prefix}extrafields"
        data_table = f"{self._prefix}{data_table_key}"

        conn = await self._connect()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"DELETE FROM `{def_table}` WHERE name = %s AND elementtype = %s",
                    (attrname, elementtype),
                )
                await cur.execute(
                    f"ALTER TABLE `{data_table}` DROP COLUMN IF EXISTS `{attrname}`"
                )

            await conn.commit()

            logger.info(
                "Extrafield eliminado via BD",
                extra={"attrname": attrname, "elementtype": elementtype},
            )
            return True

        except Exception as exc:
            await conn.rollback()
            logger.error(
                "Error eliminando extrafield via BD â€” rollback ejecutado",
                exc_info=exc,
                extra={"attrname": attrname},
            )
            raise RuntimeError(f"Error eliminando campo extra '{attrname}': {exc}") from exc
        finally:
            conn.close()

    async def update_product_extrafields(
        self,
        product_id: int,
        array_options: dict[str, Any],
        elementtype: str = "product",
    ) -> None:
        """
        Actualiza los extrafields de un producto via BD directa.

        Usa UPSERT directo en llx_{element}_extrafields en lugar del endpoint
        REST de Dolibarr, que falla cuando alguna columna no tiene DEFAULT NULL.
        Aplica ``_repair_null_defaults`` antes de escribir.

        Los keys de ``array_options`` pueden venir con o sin el prefijo ``options_``
        que usa Dolibarr en su REST API.

        Args:
            product_id:    ID del producto en Dolibarr.
            array_options: dict de extrafields a guardar.
            elementtype:   tipo de elemento (product por defecto).

        Raises:
            RuntimeError: si la operaciÃ³n de BD falla.
        """
        data_table_key = _ELEMENT_TABLE_MAP.get(elementtype)
        if not data_table_key:
            return

        data_table = f"{self._prefix}{data_table_key}"

        # Strip "options_" prefix: REST API uses it, column names don't
        clean: dict[str, Any] = {
            (k[8:] if k.startswith("options_") else k): v
            for k, v in array_options.items()
            if v is not None and v != ""
        }
        if not clean:
            return

        conn = await self._connect()
        try:
            await self._repair_null_defaults(conn, data_table)

            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT rowid FROM `{data_table}` WHERE fk_object = %s LIMIT 1",
                    (product_id,),
                )
                existing = await cur.fetchone()

            async with conn.cursor() as cur:
                if existing:
                    set_clause = ", ".join(f"`{col}` = %s" for col in clean)
                    await cur.execute(
                        f"UPDATE `{data_table}` SET {set_clause} WHERE fk_object = %s",
                        (*clean.values(), product_id),
                    )
                else:
                    cols = list(clean.keys())
                    col_clause = ", ".join(f"`{c}`" for c in cols) + ", fk_object"
                    val_clause = ", ".join(["%s"] * (len(cols) + 1))
                    await cur.execute(
                        f"INSERT INTO `{data_table}` ({col_clause}) VALUES ({val_clause})",
                        (*clean.values(), product_id),
                    )

            await conn.commit()
            logger.info(
                "Extrafields de producto actualizados via BD",
                extra={"product_id": product_id, "elementtype": elementtype, "fields": list(clean)},
            )

        except Exception as exc:
            await conn.rollback()
            logger.opt(exception=True).error(
                "Error actualizando extrafields via BD â€” product_id={} fields={}",
                product_id,
                list(clean),
            )
            raise RuntimeError(f"Error actualizando extrafields de producto {product_id}: {exc}") from exc
        finally:
            conn.close()

    def _normalize(self, row: dict[str, Any]) -> dict[str, Any]:
        """Normaliza una fila de llx_extrafields al formato estÃ¡ndar de Harvist."""
        from services.integrations.dolibarr.extrafields import _EXTRA_TYPE_MAP
        raw_type = str(row.get("type", "varchar"))
        return {
            "attrname": str(row.get("name", "")),
            "label": str(row.get("label", "")),
            "type": raw_type,
            "type_normalized": _EXTRA_TYPE_MAP.get(raw_type, "text"),
            "elementtype": str(row.get("elementtype", "")),
            "size": str(row.get("size", "")),
            "required": bool(row.get("fieldrequired", 0)),
            "fielddefault": str(row.get("fielddefault", "") or ""),
            "param": row.get("param", {}),
        }

