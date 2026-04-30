"""
Tests unitarios para DolibarrClient.

Verifica:
- Validación de configuración (URL y API key obligatorias)
- Cabecera DOLAPIKEY en cada petición
- URL base con trailing slash eliminado
- Paginación: conversión offset → page
- Reintentos exponenciales ante 5xx y TimeoutException
- Sin reintentos ante 4xx
- IntegrationError tras agotar reintentos (con atributo platform)
- API key nunca aparece en logs ni en mensajes de error
- health_check retorna True/False sin lanzar excepciones

:author: Carlitos6712
:version: 1.0.0
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "clave-de-prueba-super-segura-32c")

from api.core.config import get_settings

get_settings.cache_clear()

from services.integrations.base import IntegrationError, IntegrationNotConfiguredError
from services.integrations.dolibarr.client import DolibarrClient


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_settings(url: str = "https://dolibarr.test", api_key: str = "test-key") -> MagicMock:
    """
    Construye un mock de Settings con los campos de Dolibarr configurados.

    Args:
        url:     URL base de Dolibarr.
        api_key: API key de Dolibarr.

    Returns:
        MagicMock que simula Settings con dolibarr_url, dolibarr_api_key y
        dolibarr_configured.
    """
    s = MagicMock()
    s.dolibarr_url = url
    s.dolibarr_api_key = api_key
    s.dolibarr_configured = bool(url.strip() and api_key.strip())
    return s


# ---------------------------------------------------------------------------
# T1 — T4: Inicialización y configuración
# ---------------------------------------------------------------------------


class TestDolibarrClientInit:
    """Tests para la inicialización de DolibarrClient."""

    def test_raises_when_url_empty(self):
        """T1: lanza IntegrationNotConfiguredError si dolibarr_url está vacío."""
        s = _make_settings(url="", api_key="key")
        s.dolibarr_configured = False
        with pytest.raises(IntegrationNotConfiguredError):
            DolibarrClient(s)

    def test_raises_when_api_key_empty(self):
        """T2: lanza IntegrationNotConfiguredError si dolibarr_api_key está vacío."""
        s = _make_settings(url="https://dolibarr.test", api_key="")
        s.dolibarr_configured = False
        with pytest.raises(IntegrationNotConfiguredError):
            DolibarrClient(s)

    def test_dolapikey_header_present(self):
        """T3: la cabecera DOLAPIKEY está presente en el cliente httpx."""
        s = _make_settings()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = MagicMock()
            DolibarrClient(s)
            _, kwargs = mock_client_cls.call_args
            assert "DOLAPIKEY" in kwargs["headers"]
            assert kwargs["headers"]["DOLAPIKEY"] == "test-key"

    def test_base_url_strips_trailing_slash(self):
        """T4: base_url elimina el slash final y construye la ruta correcta."""
        s = _make_settings(url="https://dolibarr.test/")
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = MagicMock()
            DolibarrClient(s)
            _, kwargs = mock_client_cls.call_args
            assert kwargs["base_url"] == "https://dolibarr.test/api/index.php/"


# ---------------------------------------------------------------------------
# T5 — T7: Paginación — conversión offset → page
# ---------------------------------------------------------------------------


class TestDolibarrClientPagination:
    """Tests para la conversión de offset a page en list()."""

    async def test_list_offset_0_page_0(self):
        """T5: offset=0 con limit=50 produce page=0."""
        s = _make_settings()
        with patch("httpx.AsyncClient"):
            client = DolibarrClient(s)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        with patch.object(client, "_request", new=AsyncMock(return_value=mock_resp)) as mock_req:
            await client.list("products", limit=50, offset=0)
        _, kwargs = mock_req.call_args
        assert kwargs["params"]["page"] == 0

    async def test_list_offset_50_limit_50_page_1(self):
        """T6: offset=50 con limit=50 produce page=1."""
        s = _make_settings()
        with patch("httpx.AsyncClient"):
            client = DolibarrClient(s)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        with patch.object(client, "_request", new=AsyncMock(return_value=mock_resp)) as mock_req:
            await client.list("products", limit=50, offset=50)
        _, kwargs = mock_req.call_args
        assert kwargs["params"]["page"] == 1

    async def test_list_offset_100_limit_50_page_2(self):
        """T7: offset=100 con limit=50 produce page=2."""
        s = _make_settings()
        with patch("httpx.AsyncClient"):
            client = DolibarrClient(s)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        with patch.object(client, "_request", new=AsyncMock(return_value=mock_resp)) as mock_req:
            await client.list("products", limit=50, offset=100)
        _, kwargs = mock_req.call_args
        assert kwargs["params"]["page"] == 2


# ---------------------------------------------------------------------------
# T8 — T10: Reintentos ante 5xx y TimeoutException
# ---------------------------------------------------------------------------


class TestDolibarrClientRetries:
    """Tests para el mecanismo de reintentos del cliente."""

    async def test_retries_on_503(self):
        """T8: reintenta 3 veces ante respuesta 503 y luego lanza IntegrationError."""
        s = _make_settings()
        mock_resp = MagicMock()
        mock_resp.status_code = 503

        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.request = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_instance
            client = DolibarrClient(s)

        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(IntegrationError):
                await client.list("products")

        assert mock_instance.request.call_count == 3

    async def test_retries_on_500(self):
        """T9: reintenta 3 veces ante respuesta 500 y luego lanza IntegrationError."""
        s = _make_settings()
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.request = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_instance
            client = DolibarrClient(s)

        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(IntegrationError):
                await client.list("products")

        assert mock_instance.request.call_count == 3

    async def test_retries_on_timeout(self):
        """T10: reintenta 3 veces ante TimeoutException y luego lanza IntegrationError."""
        s = _make_settings()
        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.request = AsyncMock(
                side_effect=httpx.TimeoutException("timeout")
            )
            mock_cls.return_value = mock_instance
            client = DolibarrClient(s)

        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(IntegrationError):
                await client.list("products")

        assert mock_instance.request.call_count == 3


# ---------------------------------------------------------------------------
# T11 — T13: Sin reintentos ante 4xx
# ---------------------------------------------------------------------------


class TestDolibarrClientNoRetryOn4xx:
    """Tests que verifican que los errores 4xx NO producen reintentos."""

    async def test_no_retry_on_404(self):
        """T11: no reintenta ante 404 — una sola llamada a _client.request."""
        s = _make_settings()
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.request = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_instance
            client = DolibarrClient(s)

        with pytest.raises(IntegrationError):
            await client.get("products", 1)

        assert mock_instance.request.call_count == 1

    async def test_no_retry_on_422(self):
        """T12: no reintenta ante 422 — una sola llamada a _client.request."""
        s = _make_settings()
        mock_resp = MagicMock()
        mock_resp.status_code = 422

        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.request = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_instance
            client = DolibarrClient(s)

        with pytest.raises(IntegrationError):
            await client.list("products")

        assert mock_instance.request.call_count == 1

    async def test_no_retry_on_401(self):
        """T13: no reintenta ante 401 — una sola llamada a _client.request."""
        s = _make_settings()
        mock_resp = MagicMock()
        mock_resp.status_code = 401

        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.request = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_instance
            client = DolibarrClient(s)

        with pytest.raises(IntegrationError):
            await client.list("products")

        assert mock_instance.request.call_count == 1

    async def test_get_raises_on_non_404_4xx(self):
        """T27: get() raises IntegrationError on 401 without retrying."""
        s = _make_settings()
        mock_resp = MagicMock()
        mock_resp.status_code = 401

        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.request = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_instance
            client = DolibarrClient(s)

        with pytest.raises(IntegrationError) as exc_info:
            await client.get("products", 1)

        assert exc_info.value.status_code == 401
        assert mock_instance.request.call_count == 1


# ---------------------------------------------------------------------------
# T14: IntegrationError con atributo platform
# ---------------------------------------------------------------------------


class TestDolibarrClientIntegrationError:
    """Tests sobre el contenido del IntegrationError lanzado."""

    async def test_raises_integration_error_after_retries(self):
        """T14: tras agotar reintentos el error lleva platform='dolibarr'."""
        s = _make_settings()
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.request = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_instance
            client = DolibarrClient(s)

        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(IntegrationError) as exc_info:
                await client.list("products")

        assert exc_info.value.platform == "dolibarr"


# ---------------------------------------------------------------------------
# T15 — T16: Seguridad — API key no en logs ni en mensajes de error
# ---------------------------------------------------------------------------


class TestDolibarrClientApiKeySecurity:
    """Tests para verificar que la API key nunca se expone."""

    def test_api_key_not_in_log_on_init(self):
        """T15: la API key no aparece en ningún log durante la inicialización."""
        captured: list[str] = []

        def _sink(message: "loguru.Message") -> None:  # type: ignore[name-defined]
            captured.append(str(message))

        from loguru import logger

        handler_id = logger.add(_sink, level="DEBUG")
        try:
            s = _make_settings(api_key="super-secret-key-xyz")
            with patch("httpx.AsyncClient"):
                DolibarrClient(s)
        finally:
            logger.remove(handler_id)

        for msg in captured:
            assert "super-secret-key-xyz" not in msg

    async def test_api_key_not_in_error_message(self):
        """T16: la API key no aparece en el mensaje del IntegrationError."""
        s = _make_settings(api_key="super-secret-key-xyz")
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.request = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_instance
            client = DolibarrClient(s)

        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(IntegrationError) as exc_info:
                await client.list("products")

        assert "super-secret-key-xyz" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# T17 — T18: health_check
# ---------------------------------------------------------------------------


class TestDolibarrClientHealthCheck:
    """Tests para el método health_check."""

    async def test_health_check_true_on_200(self):
        """T17: health_check devuelve True cuando la API responde 200."""
        s = _make_settings()
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.request = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_instance
            client = DolibarrClient(s)

        result = await client.health_check()
        assert result is True

    async def test_health_check_false_on_timeout(self):
        """T18: health_check devuelve False ante TimeoutException sin lanzar excepción."""
        s = _make_settings()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.request = AsyncMock(
                side_effect=httpx.TimeoutException("timeout")
            )
            mock_cls.return_value = mock_instance
            client = DolibarrClient(s)

        with patch("asyncio.sleep", new=AsyncMock()):
            result = await client.health_check()

        assert result is False


# ---------------------------------------------------------------------------
# T19 — T26: CRUD completo, health_check 500 y context manager
# ---------------------------------------------------------------------------


def _make_client_with_mock_request(
    mock_response_status: int,
    mock_response_json: dict | list | None = None,
) -> tuple["DolibarrClient", AsyncMock]:
    """
    Construye un DolibarrClient cuyo método ``_request`` está mockeado.

    Args:
        mock_response_status: código HTTP que devolverá el mock de ``_request``.
        mock_response_json:   cuerpo JSON que devolverá ``response.json()``.

    Returns:
        Tupla ``(client, mock_request)`` donde ``mock_request`` es el AsyncMock
        asignado a ``client._request``.
    """
    s = _make_settings()
    with patch("httpx.AsyncClient"):
        client = DolibarrClient(s)
    mock_resp = MagicMock()
    mock_resp.status_code = mock_response_status
    mock_resp.json.return_value = mock_response_json or {}
    mock_req = AsyncMock(return_value=mock_resp)
    return client, mock_req


class TestDolibarrClientCRUD:
    """Tests de cobertura para create, update, delete y context manager."""

    async def test_create_returns_dict_on_success(self):
        """T19: create() devuelve el dict del recurso creado ante status 201."""
        client, mock_req = _make_client_with_mock_request(
            201, {"id": 42, "ref": "PROD-001"}
        )
        with patch.object(client, "_request", new=mock_req):
            result = await client.create("products", {"ref": "PROD-001"})
        assert result == {"id": 42, "ref": "PROD-001"}

    async def test_create_raises_on_4xx(self):
        """T20: create() lanza IntegrationError cuando Dolibarr devuelve 400."""
        client, mock_req = _make_client_with_mock_request(400)
        with patch.object(client, "_request", new=mock_req):
            with pytest.raises(IntegrationError):
                await client.create("products", {})

    async def test_update_returns_dict_on_success(self):
        """T21: update() devuelve el dict actualizado ante status 200."""
        client, mock_req = _make_client_with_mock_request(
            200, {"id": 1, "ref": "PROD-UPD"}
        )
        with patch.object(client, "_request", new=mock_req):
            result = await client.update("products", 1, {"ref": "PROD-UPD"})
        assert result == {"id": 1, "ref": "PROD-UPD"}

    async def test_delete_returns_true_on_200(self):
        """T22: delete() devuelve True cuando Dolibarr responde 200."""
        client, mock_req = _make_client_with_mock_request(200)
        with patch.object(client, "_request", new=mock_req):
            result = await client.delete("products", 1)
        assert result is True

    async def test_delete_returns_true_on_204(self):
        """T23: delete() devuelve True cuando Dolibarr responde 204."""
        client, mock_req = _make_client_with_mock_request(204)
        with patch.object(client, "_request", new=mock_req):
            result = await client.delete("products", 1)
        assert result is True

    async def test_delete_raises_on_error(self):
        """T24: delete() lanza IntegrationError con status_code=409 ante conflicto."""
        client, mock_req = _make_client_with_mock_request(409)
        with patch.object(client, "_request", new=mock_req):
            with pytest.raises(IntegrationError) as exc_info:
                await client.delete("products", 1)
        assert exc_info.value.status_code == 409

    async def test_health_check_false_on_500(self):
        """T25: health_check devuelve False cuando _request agota reintentos con 500."""
        s = _make_settings()
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.request = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_instance
            client = DolibarrClient(s)

        with patch("asyncio.sleep", new=AsyncMock()):
            result = await client.health_check()

        assert result is False

    async def test_context_manager(self):
        """T26: el context manager async cierra el cliente HTTP al salir del bloque."""
        s = _make_settings()
        with patch("httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance
            async with DolibarrClient(s) as client:
                assert client is not None
        mock_instance.aclose.assert_called_once()
