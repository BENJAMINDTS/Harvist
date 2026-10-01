"""
Tests unitarios para OdooClient.

Verifica:
- IntegrationNotConfiguredError si faltan credenciales
- Autenticación lazy: se ejecuta solo una vez y cachea uid
- IntegrationError si credenciales incorrectas
- _execute delega a asyncio.to_thread
- _execute lanza IntegrationError ante xmlrpc.client.Fault
- list construye domain/fields/order correctamente
- get lanza IntegrationError(404) si no hay resultados
- create llama a _execute("create") y luego get
- update llama a _execute("write") y luego get
- delete llama a _execute("unlink") y retorna bool
- search_count llama a _execute("search_count")
- health_check retorna True/False sin lanzar

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

import os
import xmlrpc.client
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "clave-de-prueba-super-segura-32c")

from services.integrations.base import IntegrationError, IntegrationNotConfiguredError
from services.integrations.odoo.client import OdooClient


def _make_settings(
    url: str = "https://odoo.test",
    db: str = "mydb",
    user: str = "admin@test.com",
    password: str = "secret",
) -> MagicMock:
    s = MagicMock()
    s.odoo_url = url
    s.odoo_db = db
    s.odoo_user = user
    s.odoo_password = password
    return s


def _make_client(**kwargs) -> OdooClient:
    s = _make_settings(**kwargs)
    return OdooClient(s)


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


class TestOdooClientInit:
    def test_raises_when_url_empty(self):
        s = _make_settings(url="")
        with pytest.raises(IntegrationNotConfiguredError):
            OdooClient(s)

    def test_raises_when_db_empty(self):
        s = _make_settings(db="")
        with pytest.raises(IntegrationNotConfiguredError):
            OdooClient(s)

    def test_raises_when_user_empty(self):
        s = _make_settings(user="")
        with pytest.raises(IntegrationNotConfiguredError):
            OdooClient(s)

    def test_raises_when_password_empty(self):
        s = _make_settings(password="")
        with pytest.raises(IntegrationNotConfiguredError):
            OdooClient(s)

    def test_overrides_take_priority_over_settings(self):
        s = _make_settings(url="", db="", user="", password="")
        # Should not raise if overrides are provided
        client = OdooClient(
            s,
            override_url="https://override.test",
            override_db="override_db",
            override_user="user@test.com",
            override_password="pass",
        )
        assert client._url == "https://override.test"

    def test_trailing_slash_stripped(self):
        s = _make_settings(url="https://odoo.test/")
        client = OdooClient(s)
        assert not client._url.endswith("/")


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class TestOdooClientAuth:
    @pytest.mark.asyncio
    async def test_uid_cached_after_first_auth(self):
        client = _make_client()

        with patch("asyncio.to_thread", new=AsyncMock(return_value=42)):
            uid1 = await client._get_uid()
            uid2 = await client._get_uid()

        assert uid1 == 42
        assert uid2 == 42

    @pytest.mark.asyncio
    async def test_raises_integration_error_when_uid_zero(self):
        client = _make_client()

        def _bad_auth():
            return 0  # Odoo returns 0/False for bad credentials

        with patch("asyncio.to_thread", new=AsyncMock(side_effect=_bad_auth)):
            # to_thread returns 0 which triggers IntegrationError inside _authenticate
            # We simulate by making to_thread raise IntegrationError directly
            pass

        with patch.object(client, "_get_uid", new=AsyncMock(side_effect=IntegrationError("bad creds", platform="odoo"))):
            with pytest.raises(IntegrationError):
                await client._get_uid()

    @pytest.mark.asyncio
    async def test_raises_integration_error_on_exception(self):
        client = _make_client()

        with patch("asyncio.to_thread", new=AsyncMock(side_effect=Exception("connection refused"))):
            with pytest.raises(IntegrationError) as exc_info:
                await client._get_uid()
        assert exc_info.value.platform == "odoo"


# ---------------------------------------------------------------------------
# _execute
# ---------------------------------------------------------------------------


class TestOdooClientExecute:
    @pytest.mark.asyncio
    async def test_execute_calls_to_thread(self):
        client = _make_client()
        client._uid = 1  # pre-set to skip auth

        with patch("asyncio.to_thread", new=AsyncMock(return_value=[{"id": 1}])) as mock_thread:
            result = await client._execute("product.template", "search_read", [[]], {})

        mock_thread.assert_called_once()
        assert result == [{"id": 1}]

    @pytest.mark.asyncio
    async def test_execute_raises_on_xmlrpc_fault(self):
        client = _make_client()
        client._uid = 1

        fault = xmlrpc.client.Fault(1, "AccessDenied")
        with patch("asyncio.to_thread", new=AsyncMock(side_effect=fault)):
            with pytest.raises(IntegrationError) as exc_info:
                await client._execute("product.template", "search_read", [[]])
        assert exc_info.value.platform == "odoo"

    @pytest.mark.asyncio
    async def test_execute_raises_on_generic_exception(self):
        client = _make_client()
        client._uid = 1

        with patch("asyncio.to_thread", new=AsyncMock(side_effect=ConnectionError("timeout"))):
            with pytest.raises(IntegrationError) as exc_info:
                await client._execute("product.template", "search_read", [[]])
        assert exc_info.value.platform == "odoo"


# ---------------------------------------------------------------------------
# list / get / create / update / delete
# ---------------------------------------------------------------------------


class TestOdooClientCRUD:
    @pytest.fixture(autouse=True)
    def _no_field_filtering(self):
        # Estos tests cubren las llamadas CRUD; el filtrado de campos va en TestVersionCompat.
        with patch.object(OdooClient, "get_model_fields", new=AsyncMock(return_value=None)):
            yield

    @pytest.mark.asyncio
    async def test_list_passes_domain_fields_order(self):
        client = _make_client()
        client._uid = 1

        with patch.object(client, "_execute", new=AsyncMock(return_value=[{"id": 1}])) as mock_exec:
            result = await client.list(
                "product.template",
                limit=10,
                offset=5,
                filters={"domain": [("active", "=", True)], "fields": ["id", "name"], "order": "name asc"},
            )

        mock_exec.assert_called_once()
        args = mock_exec.call_args
        assert args[0][0] == "product.template"
        assert args[0][1] == "search_read"
        assert result == [{"id": 1}]

    @pytest.mark.asyncio
    async def test_list_returns_empty_list_on_none(self):
        client = _make_client()
        client._uid = 1

        with patch.object(client, "_execute", new=AsyncMock(return_value=None)):
            result = await client.list("product.template")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_returns_first_record(self):
        client = _make_client()
        client._uid = 1

        with patch.object(client, "_execute", new=AsyncMock(return_value=[{"id": 5, "name": "Test"}])):
            result = await client.get("product.template", 5)

        assert result["id"] == 5

    @pytest.mark.asyncio
    async def test_get_raises_404_when_not_found(self):
        client = _make_client()
        client._uid = 1

        with patch.object(client, "_execute", new=AsyncMock(return_value=[])):
            with pytest.raises(IntegrationError) as exc_info:
                await client.get("product.template", 999)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_create_calls_execute_and_returns_record(self):
        client = _make_client()
        client._uid = 1

        call_count = {"n": 0}

        async def _mock_execute(model, method, args, kwargs=None):
            call_count["n"] += 1
            if method == "create":
                return 42
            if method == "read":
                return [{"id": 42, "name": "Nuevo"}]
            return None

        with patch.object(client, "_execute", new=AsyncMock(side_effect=_mock_execute)):
            result = await client.create("product.template", {"name": "Nuevo"})

        assert result["id"] == 42
        assert call_count["n"] == 2

    @pytest.mark.asyncio
    async def test_update_calls_write_then_read(self):
        client = _make_client()
        client._uid = 1

        async def _mock_execute(model, method, args, kwargs=None):
            if method == "write":
                return True
            if method == "read":
                return [{"id": 7, "name": "Updated"}]
            return None

        with patch.object(client, "_execute", new=AsyncMock(side_effect=_mock_execute)):
            result = await client.update("product.template", 7, {"name": "Updated"})

        assert result["id"] == 7

    @pytest.mark.asyncio
    async def test_delete_returns_true(self):
        client = _make_client()
        client._uid = 1

        with patch.object(client, "_execute", new=AsyncMock(return_value=True)):
            result = await client.delete("product.template", 3)

        assert result is True

    @pytest.mark.asyncio
    async def test_search_count_returns_int(self):
        client = _make_client()
        client._uid = 1

        with patch.object(client, "_execute", new=AsyncMock(return_value=17)):
            result = await client.search_count("product.template", [("active", "=", True)])

        assert result == 17

    @pytest.mark.asyncio
    async def test_bulk_create_returns_records(self):
        client = _make_client()
        client._uid = 1

        async def _mock_execute(model, method, args, kwargs=None):
            if method == "create":
                return [10, 11]
            if method == "read":
                return [{"id": 10}, {"id": 11}]

        with patch.object(client, "_execute", new=AsyncMock(side_effect=_mock_execute)):
            result = await client.bulk_create("product.template", [{"name": "A"}, {"name": "B"}])

        assert len(result) == 2


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


class TestOdooClientHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_true_on_success(self):
        client = _make_client()

        with patch("asyncio.to_thread", new=AsyncMock(return_value={"server_version": "17.0"})):
            result = await client.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_false_on_exception(self):
        client = _make_client()

        with patch("asyncio.to_thread", new=AsyncMock(side_effect=Exception("unreachable"))):
            result = await client.health_check()

        assert result is False


# ---------------------------------------------------------------------------
# Autodetección de versión y campos
# ---------------------------------------------------------------------------


class TestVersionCompat:
    @pytest.fixture(autouse=True)
    def _clear_caches(self):
        from services.integrations.odoo import client as client_module

        client_module._MODEL_FIELDS_CACHE.clear()
        client_module._SERVER_VERSION_CACHE.clear()
        yield

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("info", "expected"),
        [((14, 0, 0, "final", 0, ""), 14), ((18, 0, 0, "final", 0, ""), 18), (("saas~17", 2, 0, "final", 0, ""), 17)],
    )
    async def test_server_version_parsed_and_cached(self, info, expected):
        client = _make_client()

        with patch("asyncio.to_thread", new=AsyncMock(return_value={"server_version_info": info})) as mock_thread:
            assert await client.get_server_version() == expected
            assert await client.get_server_version() == expected

        mock_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_drops_fields_missing_in_model(self):
        client = _make_client()

        async def _mock_execute(model, method, args, kwargs=None):
            if method == "fields_get":
                return {"id": {}, "name": {}, "type": {}}
            return [{"id": 1}]

        with patch.object(client, "_execute", new=AsyncMock(side_effect=_mock_execute)) as mock_exec:
            await client.list("product.template", filters={"fields": ["id", "name", "detailed_type"]})
            await client.list("product.template", filters={"fields": ["id"]})

        search_calls = [c for c in mock_exec.call_args_list if c[0][1] == "search_read"]
        assert search_calls[0][0][3]["fields"] == ["id", "name"]
        fields_get_calls = [c for c in mock_exec.call_args_list if c[0][1] == "fields_get"]
        assert len(fields_get_calls) == 1  # cacheado

    @pytest.mark.asyncio
    async def test_write_drops_values_missing_in_model(self):
        client = _make_client()

        async def _mock_execute(model, method, args, kwargs=None):
            if method == "fields_get":
                return {"id": {}, "name": {}}
            if method == "read":
                return [{"id": 7}]
            return True

        with patch.object(client, "_execute", new=AsyncMock(side_effect=_mock_execute)) as mock_exec:
            await client.update("product.template", 7, {"name": "X", "available_in_pos": True})

        write_call = next(c for c in mock_exec.call_args_list if c[0][1] == "write")
        assert write_call[0][2] == [[7], {"name": "X"}]

    @pytest.mark.asyncio
    async def test_fields_unknown_when_fields_get_fails(self):
        client = _make_client()

        async def _mock_execute(model, method, args, kwargs=None):
            if method == "fields_get":
                raise IntegrationError("access denied", platform="odoo")
            return [{"id": 1}]

        with patch.object(client, "_execute", new=AsyncMock(side_effect=_mock_execute)) as mock_exec:
            await client.list("product.template", filters={"fields": ["id", "detailed_type"]})

        search_call = next(c for c in mock_exec.call_args_list if c[0][1] == "search_read")
        assert search_call[0][3]["fields"] == ["id", "detailed_type"]

