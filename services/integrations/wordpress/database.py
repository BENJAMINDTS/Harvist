"""
Acceso directo a la base de datos MySQL de WordPress.

Permite ejecutar consultas SQL de solo lectura y listar tablas.
Equivalente phpMyAdmin integrado en Harvist para inspeccionar
y gestionar la BD de WordPress sin salir de la aplicación.

Solo operaciones de lectura por defecto. Escritura solo via métodos explícitos.

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

from typing import Any

import aiomysql
from loguru import logger

from api.core.config import Settings
from services.integrations.base import IntegrationError

_FORBIDDEN_KEYWORDS = {"drop", "truncate", "delete", "update", "insert", "alter", "create"}


class WordPressDBService:
    """
    Servicio de acceso directo a MySQL/MariaDB de WordPress.

    Usado para operaciones de inspección que la REST API no expone:
    estadísticas de tablas, queries avanzadas, gestión directa de registros.

    :author: Carlitos6712
    """

    def __init__(
        self,
        host: str,
        port: int,
        db_name: str,
        user: str,
        password: str,
        prefix: str = "wp_",
    ) -> None:
        """
        Args:
            host: host MySQL.
            port: puerto MySQL.
            db_name: nombre de la base de datos.
            user: usuario MySQL.
            password: contraseña MySQL.
            prefix: prefijo de tablas WordPress (por defecto "wp_").
        """
        self._host = host
        self._port = port
        self._db_name = db_name
        self._user = user
        self._password = password
        self._prefix = prefix

    @classmethod
    def from_settings(cls, settings: Settings) -> "WordPressDBService":
        """
        Crea instancia desde Settings de la aplicación.

        Args:
            settings: instancia de Settings con las variables de entorno.

        Returns:
            Instancia de WordPressDBService.

        Raises:
            IntegrationError: si las credenciales de BD no están configuradas.
        """
        if not settings.wordpress_db_configured:
            raise IntegrationError(
                "BD WordPress no configurada: define WORDPRESS_DB_HOST, "
                "WORDPRESS_DB_NAME y WORDPRESS_DB_USER en .env.",
                platform="wordpress",
            )
        return cls(
            host=settings.wordpress_db_host,
            port=settings.wordpress_db_port,
            db_name=settings.wordpress_db_name,
            user=settings.wordpress_db_user,
            password=settings.wordpress_db_pass,
            prefix=settings.wordpress_db_prefix,
        )

    async def _connect(self) -> aiomysql.Connection:
        """Abre una conexión MySQL. El caller debe cerrarla."""
        try:
            conn = await aiomysql.connect(
                host=self._host,
                port=self._port,
                db=self._db_name,
                user=self._user,
                password=self._password,
                charset="utf8mb4",
                autocommit=True,
            )
            return conn
        except Exception as exc:
            logger.error(
                "Error conectando a BD WordPress",
                exc_info=exc,
                extra={"host": self._host, "db": self._db_name},
            )
            raise IntegrationError(
                f"No se pudo conectar a la BD WordPress: {exc}",
                platform="wordpress",
            ) from exc

    async def test_connection(self) -> bool:
        """
        Verifica que la conexión a MySQL sea correcta.

        Returns:
            True si la conexión es exitosa; False en caso contrario.
        """
        try:
            conn = await self._connect()
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
            conn.close()
            return True
        except Exception:
            return False

    async def list_tables(self) -> list[dict[str, Any]]:
        """
        Lista las tablas de la BD de WordPress con estadísticas básicas.

        Returns:
            Lista de dicts: {name, rows, size_mb, engine, collation}.
        """
        conn = await self._connect()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """
                    SELECT
                        TABLE_NAME          AS `name`,
                        TABLE_ROWS          AS `rows`,
                        ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 3) AS `size_mb`,
                        ENGINE              AS `engine`,
                        TABLE_COLLATION     AS `collation`
                    FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = %s
                    ORDER BY TABLE_NAME
                    """,
                    (self._db_name,),
                )
                rows = await cur.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    async def query(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
        read_only: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Ejecuta una consulta SQL y devuelve los resultados.

        Por defecto solo permite SELECT. Pasar read_only=False para operaciones
        de escritura (actualización de opciones, limpieza, etc.).

        Args:
            sql: consulta SQL a ejecutar.
            params: parámetros parametrizados (evita SQL injection).
            read_only: si True, rechaza queries de escritura.

        Returns:
            Lista de dicts con los resultados.

        Raises:
            ValueError: si la query contiene palabras clave prohibidas en modo read_only.
            IntegrationError: si la consulta falla.
        """
        if read_only:
            sql_lower = sql.strip().lower()
            for kw in _FORBIDDEN_KEYWORDS:
                if sql_lower.startswith(kw) or f" {kw} " in sql_lower:
                    raise ValueError(
                        f"Query contiene operación prohibida '{kw.upper()}'. "
                        "Usar read_only=False para operaciones de escritura."
                    )

        conn = await self._connect()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.error(
                "Error ejecutando query WordPress DB",
                exc_info=exc,
                extra={"sql_preview": sql[:200]},
            )
            raise IntegrationError(
                f"Error en query BD WordPress: {exc}",
                platform="wordpress",
            ) from exc
        finally:
            conn.close()

    async def get_option(self, option_name: str) -> str | None:
        """
        Lee una opción de WordPress desde wp_options.

        Args:
            option_name: nombre de la opción (ej: "siteurl", "blogname").

        Returns:
            Valor de la opción o None si no existe.
        """
        rows = await self.query(
            f"SELECT option_value FROM `{self._prefix}options` WHERE option_name = %s LIMIT 1",
            (option_name,),
        )
        if rows:
            return str(rows[0]["option_value"])
        return None

    async def get_site_info(self) -> dict[str, Any]:
        """
        Obtiene información básica del sitio WordPress.

        Returns:
            Dict con siteurl, blogname, admin_email, wp_version, etc.
        """
        keys = ["siteurl", "blogname", "blogdescription", "admin_email", "db_version"]
        result: dict[str, Any] = {}
        for key in keys:
            result[key] = await self.get_option(key)
        return result

    async def get_product_meta(
        self, product_id: int, meta_key: str
    ) -> str | None:
        """
        Lee el valor de un post_meta de un producto WordPress.

        Args:
            product_id: ID del producto (post ID).
            meta_key: clave del meta (ej: "_price", "_sku", "_stock").

        Returns:
            Valor del meta o None si no existe.
        """
        rows = await self.query(
            f"SELECT meta_value FROM `{self._prefix}postmeta` "
            "WHERE post_id = %s AND meta_key = %s LIMIT 1",
            (product_id, meta_key),
        )
        if rows:
            return str(rows[0]["meta_value"])
        return None
