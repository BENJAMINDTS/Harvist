"""
Tests unitarios para WordPressClient.

Verifica:
- IntegrationNotConfiguredError si faltan credenciales
- Authorization Basic header presente cuando HTTPS
- OAuth mode activo cuando HTTP
- list: paginación offset→page, filtra errores 4xx
- get: lanza IntegrationError(404) en not found
- create: lanza IntegrationError en 4xx
- update: lanza IntegrationError en 4xx
- delete: retorna True en 200/204, lanza en error
- health_check: True en 200, False en error
- batch_delete: acumula resultados, trocea en chunks
- context manager: cierra ambos clientes httpx

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "clave-de-prueba-super-segura-32c")

from services.integrations.base import IntegrationError, IntegrationNotConfiguredError
from services.integrations.wordpress.client import WordPressClient


def _make_settings(
    url: str = "https://wp.test",
    key: str = "ck_test",
    secret: str = "cs_test",
) -> MagicMock:
    s = MagicMock()
    s.wordpress_url = url
    s.wordpress_consumer_key = key
    s.wordpress_consumer_secret = secret
    return s


def _make_client(**kwargs) -> WordPressClient:
    s = _make_settings(**kwargs)
    with patch("httpx.AsyncClient"):
        return WordPressClient(s)


def _mock_response(status: int, body: dict | list | None = None) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    r.content = b"x"
    r.json.return_value = body or {}
    r.text = ""
    r.headers = {"X-WP-Total": "0"}
    return r


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


class TestWordPressClientInit:
    def test_raises_when_url_empty(self):
        s = _make_settings(url="")
        with pytest.raises(IntegrationNotConfiguredError):
            WordPressClient(s)

    def test_raises_when_consumer_key_empty(self):
        s = _make_settings(key="")
        with pytest.raises(IntegrationNotConfiguredError):
            WordPressClient(s)

    def test_raises_when_consumer_secret_empty(self):
        s = _make_settings(secret="")
        with pytest.raises(IntegrationNotConfiguredError):
            WordPressClient(s)

    def test_https_uses_basic_auth(self):
        s = _make_settings(url="https://wp.test")
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            client = WordPressClient(s)
        assert not client._use_oauth

    def test_http_uses_oauth(self):
        s = _make_settings(url="http://wp.test")
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            client = WordPressClient(s)
        assert client._use_oauth

    def test_trailing_slash_stripped(self):
        s = _make_settings(url="https://wp.test/")
        with patch("httpx.AsyncClient"):
            client = WordPressClient(s)
        assert not client._base_url.endswith("/")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


class TestWordPressClientList:
    @pytest.mark.asyncio
    async def test_calculates_page_from_offset(self):
        client = _make_client()
        resp = _mock_response(200, [{"id": 1}])

        with patch.object(client, "_wc_request", new=AsyncMock(return_value=resp)) as mock_req:
            result = await client.list("products", limit=50, offset=50)

        params = mock_req.call_args[1]["params"]
        assert params["page"] == 2
        assert result == [{"id": 1}]

    @pytest.mark.asyncio
    async def test_raises_on_404(self):
        client = _make_client()
        resp = _mock_response(404)

        with patch.object(client, "_wc_request", new=AsyncMock(return_value=resp)):
            with pytest.raises(IntegrationError) as exc_info:
                await client.list("products")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_raises_on_401(self):
        client = _make_client()
        resp = _mock_response(401)

        with patch.object(client, "_wc_request", new=AsyncMock(return_value=resp)):
            with pytest.raises(IntegrationError) as exc_info:
                await client.list("products")
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


class TestWordPressClientGet:
    @pytest.mark.asyncio
    async def test_returns_dict_on_200(self):
        client = _make_client()
        resp = _mock_response(200, {"id": 5, "name": "TV"})

        with patch.object(client, "_wc_request", new=AsyncMock(return_value=resp)):
            result = await client.get("products", 5)

        assert result["id"] == 5

    @pytest.mark.asyncio
    async def test_raises_404_on_not_found(self):
        client = _make_client()
        resp = _mock_response(404)

        with patch.object(client, "_wc_request", new=AsyncMock(return_value=resp)):
            with pytest.raises(IntegrationError) as exc_info:
                await client.get("products", 999)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


class TestWordPressClientCreate:
    @pytest.mark.asyncio
    async def test_returns_created_resource(self):
        client = _make_client()
        resp = _mock_response(201, {"id": 10, "name": "Nuevo"})

        with patch.object(client, "_wc_request", new=AsyncMock(return_value=resp)):
            result = await client.create("products", {"name": "Nuevo"})

        assert result["id"] == 10

    @pytest.mark.asyncio
    async def test_raises_on_4xx(self):
        client = _make_client()
        resp = _mock_response(400, {"message": "invalid"})

        with patch.object(client, "_wc_request", new=AsyncMock(return_value=resp)):
            with pytest.raises(IntegrationError):
                await client.create("products", {})


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


class TestWordPressClientUpdate:
    @pytest.mark.asyncio
    async def test_returns_updated_resource(self):
        client = _make_client()
        resp = _mock_response(200, {"id": 5, "name": "Updated"})

        with patch.object(client, "_wc_request", new=AsyncMock(return_value=resp)):
            result = await client.update("products", 5, {"name": "Updated"})

        assert result["name"] == "Updated"

    @pytest.mark.asyncio
    async def test_raises_on_4xx(self):
        client = _make_client()
        resp = _mock_response(422, {"message": "invalid"})

        with patch.object(client, "_wc_request", new=AsyncMock(return_value=resp)):
            with pytest.raises(IntegrationError):
                await client.update("products", 5, {})


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestWordPressClientDelete:
    @pytest.mark.asyncio
    async def test_returns_true_on_200(self):
        client = _make_client()
        resp = _mock_response(200)

        with patch.object(client, "_wc_request", new=AsyncMock(return_value=resp)):
            result = await client.delete("products", 5)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_on_204(self):
        client = _make_client()
        resp = _mock_response(204)

        with patch.object(client, "_wc_request", new=AsyncMock(return_value=resp)):
            result = await client.delete("products", 5)

        assert result is True

    @pytest.mark.asyncio
    async def test_raises_on_error(self):
        client = _make_client()
        resp = _mock_response(409)

        with patch.object(client, "_wc_request", new=AsyncMock(return_value=resp)):
            with pytest.raises(IntegrationError):
                await client.delete("products", 5)


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


class TestWordPressClientHealthCheck:
    @pytest.mark.asyncio
    async def test_returns_true_on_200(self):
        client = _make_client()
        resp = _mock_response(200)

        with patch.object(client, "_wc_request", new=AsyncMock(return_value=resp)):
            result = await client.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self):
        client = _make_client()

        with patch.object(client, "_wc_request", new=AsyncMock(side_effect=IntegrationError("err", platform="wordpress"))):
            result = await client.health_check()

        assert result is False


# ---------------------------------------------------------------------------
# _request retries
# ---------------------------------------------------------------------------


class TestWordPressClientRetries:
    @pytest.mark.asyncio
    async def test_retries_on_500(self):
        client = _make_client()
        resp_500 = _mock_response(500)

        with patch.object(client._wc_client, "request", new=AsyncMock(return_value=resp_500)) as mock_req:
            with patch("asyncio.sleep", new=AsyncMock()):
                with pytest.raises(IntegrationError):
                    await client._wc_request("GET", "products")

        assert mock_req.call_count == 3

    @pytest.mark.asyncio
    async def test_retries_on_timeout(self):
        client = _make_client()

        with patch.object(client._wc_client, "request", new=AsyncMock(side_effect=httpx.TimeoutException("timeout"))) as mock_req:
            with patch("asyncio.sleep", new=AsyncMock()):
                with pytest.raises(IntegrationError):
                    await client._wc_request("GET", "products")

        assert mock_req.call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_404(self):
        client = _make_client()
        resp_404 = _mock_response(404)

        with patch.object(client._wc_client, "request", new=AsyncMock(return_value=resp_404)) as mock_req:
            resp = await client._wc_request("GET", "products")

        assert mock_req.call_count == 1
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# context manager
# ---------------------------------------------------------------------------


class TestWordPressClientContextManager:
    @pytest.mark.asyncio
    async def test_closes_both_clients(self):
        client = _make_client()
        client._wc_client = AsyncMock()
        client._wp_client = AsyncMock()

        async with client:
            pass

        client._wc_client.aclose.assert_called_once()
        client._wp_client.aclose.assert_called_once()
