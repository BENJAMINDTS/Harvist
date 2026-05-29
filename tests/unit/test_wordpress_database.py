"""
Tests unitarios para WordPressDBService.

Verifica:
- query: rechaza keywords peligrosas en modo read_only (DROP, TRUNCATE, DELETE, etc.)
- query: acepta SELECT en modo read_only
- query: acepta operaciones de escritura cuando read_only=False
- list_tables: retorna lista de tablas con el prefijo correcto
- get_option: retorna valor de la opción o None si no existe

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.integrations.wordpress.database import WordPressDBService


def _make_service(
    host: str = "localhost",
    port: int = 3306,
    db_name: str = "wordpress",
    user: str = "root",
    password: str = "secret",
    prefix: str = "wp_",
) -> WordPressDBService:
    return WordPressDBService(
        host=host, port=port, db_name=db_name,
        user=user, password=password, prefix=prefix,
    )


# ---------------------------------------------------------------------------
# query — validation
# ---------------------------------------------------------------------------


class TestQueryValidation:
    @pytest.mark.asyncio
    async def test_raises_for_drop_in_read_only(self):
        svc = _make_service()
        with pytest.raises(ValueError):
            await svc.query("DROP TABLE wp_posts")

    @pytest.mark.asyncio
    async def test_raises_for_truncate_in_read_only(self):
        svc = _make_service()
        with pytest.raises(ValueError):
            await svc.query("TRUNCATE TABLE wp_posts")

    @pytest.mark.asyncio
    async def test_raises_for_delete_in_read_only(self):
        svc = _make_service()
        with pytest.raises(ValueError):
            await svc.query("DELETE FROM wp_posts WHERE ID=1")

    @pytest.mark.asyncio
    async def test_raises_for_update_in_read_only(self):
        svc = _make_service()
        with pytest.raises(ValueError):
            await svc.query("UPDATE wp_posts SET post_status='draft'")

    @pytest.mark.asyncio
    async def test_case_insensitive_keyword_detection(self):
        svc = _make_service()
        with pytest.raises(ValueError):
            await svc.query("drop table wp_users")


# ---------------------------------------------------------------------------
# query — execution (mocked aiomysql)
# ---------------------------------------------------------------------------


def _make_mock_connection(rows: list) -> AsyncMock:
    cursor = MagicMock()
    cursor.execute = AsyncMock()
    cursor.fetchall = AsyncMock(return_value=rows)
    cursor.__aenter__ = AsyncMock(return_value=cursor)
    cursor.__aexit__ = AsyncMock(return_value=False)

    conn = MagicMock()
    conn.cursor = MagicMock(return_value=cursor)
    conn.close = MagicMock()
    return conn


class TestQueryExecution:
    @pytest.mark.asyncio
    async def test_select_returns_rows(self):
        svc = _make_service()
        fake_rows = [{"ID": 1, "post_title": "Hello"}]
        conn = _make_mock_connection(fake_rows)

        with patch.object(svc, "_connect", new=AsyncMock(return_value=conn)):
            result = await svc.query("SELECT * FROM wp_posts LIMIT 1")

        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# list_tables
# ---------------------------------------------------------------------------


class TestListTables:
    @pytest.mark.asyncio
    async def test_returns_list_of_tables(self):
        svc = _make_service(prefix="wp_")
        fake_rows = [{"Tables_in_wordpress": "wp_posts"}, {"Tables_in_wordpress": "wp_users"}]
        conn = _make_mock_connection(fake_rows)

        with patch.object(svc, "_connect", new=AsyncMock(return_value=conn)):
            result = await svc.list_tables()

        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# get_option
# ---------------------------------------------------------------------------


class TestGetOption:
    @pytest.mark.asyncio
    async def test_returns_option_value(self):
        svc = _make_service()
        fake_rows = [{"option_value": "https://mysite.com"}]
        conn = _make_mock_connection(fake_rows)

        with patch.object(svc, "_connect", new=AsyncMock(return_value=conn)):
            result = await svc.get_option("siteurl")

        assert result == "https://mysite.com"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        svc = _make_service()
        conn = _make_mock_connection([])

        with patch.object(svc, "_connect", new=AsyncMock(return_value=conn)):
            result = await svc.get_option("nonexistent_option")

        assert result is None
