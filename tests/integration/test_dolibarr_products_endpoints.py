"""
Tests de integración para los endpoints /api/v1/dolibarr/products.

Verifica:
- 503 cuando Dolibarr no está configurado
- Listado paginado de productos
- GET por ID con 404 para ID inexistente
- Creación con 201
- Actualización
- Eliminación con mensaje de éxito
- Subida de imagen: rechazo de archivos > 5 MB
- Subida de imagen: rechazo de tipo MIME no permitido
- Sincronización desde job: lista de resultados por producto

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

import io
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ── Variables de entorno mínimas ─────────────────────────────────────────────
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-32-chars-long-enough")
os.environ.setdefault("BROWSER_BINARY_PATH", "/usr/bin/google-chrome")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

from api.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from api.main import app  # noqa: E402

_BASE = "/api/v1/dolibarr/products"


def _mock_settings(configured: bool = True) -> MagicMock:
    """Crea un mock de Settings con Dolibarr configurado o no."""
    s = MagicMock()
    s.dolibarr_configured = configured
    s.dolibarr_url = "https://dolibarr.test" if configured else ""
    s.dolibarr_api_key = "test-key" if configured else ""
    return s


def _mock_svc(
    list_return=None,
    get_return=None,
    create_return=None,
    update_return=None,
    delete_return=True,
    sync_return=None,
    upload_return=None,
    get_exc=None,
) -> MagicMock:
    """Construye un mock completo de DolibarrProductService."""
    svc = MagicMock()
    svc.list_products = AsyncMock(return_value=list_return or [])
    svc.get_product = AsyncMock(return_value=get_return or {"id": 1})
    svc.create_product = AsyncMock(return_value=create_return or {"id": 1})
    svc.update_product = AsyncMock(return_value=update_return or {"id": 1})
    svc.delete_product = AsyncMock(return_value=delete_return)
    svc.sync_from_job = AsyncMock(return_value=sync_return or [])
    svc.upload_image = AsyncMock(return_value=upload_return or {"success": 1})
    if get_exc:
        svc.get_product = AsyncMock(side_effect=get_exc)
    return svc


@pytest_asyncio.fixture
async def http_client() -> AsyncClient:
    """Cliente HTTP async para la app FastAPI."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# 503 — Dolibarr no configurado
# ---------------------------------------------------------------------------


class TestNotConfigured:
    """503 cuando Dolibarr no está configurado."""

    @pytest.mark.asyncio
    async def test_returns_503_when_dolibarr_not_configured(
        self, http_client: AsyncClient
    ):
        """GET /dolibarr/products devuelve 503 si Dolibarr no está configurado."""
        with patch(
            "api.v1.endpoints.dolibarr.get_settings",
            return_value=_mock_settings(configured=False),
        ):
            response = await http_client.get(_BASE)

        assert response.status_code == 503
        assert "DOLIBARR_URL" in response.text or "configurado" in response.text.lower()


# ---------------------------------------------------------------------------
# GET /dolibarr/products
# ---------------------------------------------------------------------------


class TestListProducts:
    """Tests para GET /api/v1/dolibarr/products."""

    @pytest.mark.asyncio
    async def test_list_products_returns_paginated_response(
        self, http_client: AsyncClient
    ):
        """GET /dolibarr/products devuelve PaginatedResponse con items."""
        products = [{"id": 1, "ref": "PROD-1"}, {"id": 2, "ref": "PROD-2"}]
        svc = _mock_svc(list_return=products)

        with (
            patch(
                "api.v1.endpoints.dolibarr.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "api.v1.endpoints.dolibarr._get_service",
                return_value=svc,
            ),
        ):
            response = await http_client.get(_BASE)

        assert response.status_code == 200
        body = response.json()
        assert "items" in body
        assert len(body["items"]) == 2
        assert body["limit"] == 50
        assert body["offset"] == 0


# ---------------------------------------------------------------------------
# GET /dolibarr/products/{id}
# ---------------------------------------------------------------------------


class TestGetProduct:
    """Tests para GET /api/v1/dolibarr/products/{product_id}."""

    @pytest.mark.asyncio
    async def test_get_product_returns_404_for_nonexistent_id(
        self, http_client: AsyncClient
    ):
        """GET /dolibarr/products/{id} devuelve 404 si el producto no existe."""
        from services.integrations.base import IntegrationError

        svc = _mock_svc(
            get_exc=IntegrationError("no encontrado", platform="dolibarr", status_code=404)
        )

        with (
            patch(
                "api.v1.endpoints.dolibarr.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "api.v1.endpoints.dolibarr._get_service",
                return_value=svc,
            ),
        ):
            response = await http_client.get(f"{_BASE}/9999")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /dolibarr/products
# ---------------------------------------------------------------------------


class TestCreateProduct:
    """Tests para POST /api/v1/dolibarr/products."""

    @pytest.mark.asyncio
    async def test_create_product_returns_201_with_created_data(
        self, http_client: AsyncClient
    ):
        """POST /dolibarr/products retorna 201 con los datos del producto creado."""
        created = {"id": 42, "ref": "PROD-NEW"}
        svc = _mock_svc(create_return=created)

        with (
            patch(
                "api.v1.endpoints.dolibarr.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "api.v1.endpoints.dolibarr._get_service",
                return_value=svc,
            ),
        ):
            response = await http_client.post(
                _BASE, json={"ref": "PROD-NEW", "label": "Nuevo"}
            )

        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["id"] == 42


# ---------------------------------------------------------------------------
# PUT /dolibarr/products/{id}
# ---------------------------------------------------------------------------


class TestUpdateProduct:
    """Tests para PUT /api/v1/dolibarr/products/{product_id}."""

    @pytest.mark.asyncio
    async def test_update_product_returns_updated_data(
        self, http_client: AsyncClient
    ):
        """PUT /dolibarr/products/{id} devuelve el producto actualizado."""
        updated = {"id": 5, "ref": "PROD-5", "label": "Actualizado"}
        svc = _mock_svc(update_return=updated)

        with (
            patch(
                "api.v1.endpoints.dolibarr.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "api.v1.endpoints.dolibarr._get_service",
                return_value=svc,
            ),
        ):
            response = await http_client.put(
                f"{_BASE}/5", json={"label": "Actualizado"}
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["label"] == "Actualizado"


# ---------------------------------------------------------------------------
# DELETE /dolibarr/products/{id}
# ---------------------------------------------------------------------------


class TestDeleteProduct:
    """Tests para DELETE /api/v1/dolibarr/products/{product_id}."""

    @pytest.mark.asyncio
    async def test_delete_product_returns_success_message(
        self, http_client: AsyncClient
    ):
        """DELETE /dolibarr/products/{id} devuelve success y mensaje de confirmación."""
        svc = _mock_svc(delete_return=True)

        with (
            patch(
                "api.v1.endpoints.dolibarr.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "api.v1.endpoints.dolibarr._get_service",
                return_value=svc,
            ),
        ):
            response = await http_client.delete(f"{_BASE}/3")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert "eliminado" in body["message"].lower()


# ---------------------------------------------------------------------------
# POST /dolibarr/products/{id}/image
# ---------------------------------------------------------------------------


class TestUploadImage:
    """Tests para POST /api/v1/dolibarr/products/{product_id}/image."""

    @pytest.mark.asyncio
    async def test_upload_image_rejects_file_larger_than_5mb(
        self, http_client: AsyncClient
    ):
        """upload_image retorna 413 para archivos > 5 MB."""
        big_content = b"x" * (5 * 1024 * 1024 + 1)

        with (
            patch(
                "api.v1.endpoints.dolibarr.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "api.v1.endpoints.dolibarr._get_service",
                return_value=_mock_svc(),
            ),
        ):
            response = await http_client.post(
                f"{_BASE}/1/image",
                files={"file": ("big.jpg", io.BytesIO(big_content), "image/jpeg")},
            )

        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_upload_image_rejects_non_image_mime_type(
        self, http_client: AsyncClient
    ):
        """upload_image retorna 422 para tipos MIME no permitidos."""
        with (
            patch(
                "api.v1.endpoints.dolibarr.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "api.v1.endpoints.dolibarr._get_service",
                return_value=_mock_svc(),
            ),
        ):
            response = await http_client.post(
                f"{_BASE}/1/image",
                files={
                    "file": ("document.pdf", io.BytesIO(b"pdf content"), "application/pdf")
                },
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_upload_image_success(self, http_client: AsyncClient):
        """upload_image retorna 200 con resultado de Dolibarr para imagen válida."""
        svc = _mock_svc(upload_return={"success": 1, "filename": "producto.jpg"})

        with (
            patch(
                "api.v1.endpoints.dolibarr.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "api.v1.endpoints.dolibarr._get_service",
                return_value=svc,
            ),
        ):
            response = await http_client.post(
                f"{_BASE}/1/image",
                files={"file": ("producto.jpg", io.BytesIO(b"\xff\xd8\xff fake"), "image/jpeg")},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True


# ---------------------------------------------------------------------------
# Error paths — 502 from IntegrationError
# ---------------------------------------------------------------------------


class TestErrorPaths:
    """Tests para error paths de los endpoints (502 desde IntegrationError)."""

    @pytest.mark.asyncio
    async def test_list_products_returns_502_on_integration_error(
        self, http_client: AsyncClient
    ):
        """GET /dolibarr/products retorna 502 cuando client lanza IntegrationError."""
        from services.integrations.base import IntegrationError

        svc = _mock_svc()
        svc.list_products = AsyncMock(
            side_effect=IntegrationError("timeout", platform="dolibarr")
        )

        with (
            patch("api.v1.endpoints.dolibarr.get_settings", return_value=_mock_settings()),
            patch("api.v1.endpoints.dolibarr._get_service", return_value=svc),
        ):
            response = await http_client.get(_BASE)

        assert response.status_code == 502

    @pytest.mark.asyncio
    async def test_get_product_returns_502_on_non_404_error(
        self, http_client: AsyncClient
    ):
        """GET /dolibarr/products/{id} retorna 502 para errores que no sean 404."""
        from services.integrations.base import IntegrationError

        svc = _mock_svc(
            get_exc=IntegrationError("server error", platform="dolibarr", status_code=500)
        )

        with (
            patch("api.v1.endpoints.dolibarr.get_settings", return_value=_mock_settings()),
            patch("api.v1.endpoints.dolibarr._get_service", return_value=svc),
        ):
            response = await http_client.get(f"{_BASE}/1")

        assert response.status_code == 502

    @pytest.mark.asyncio
    async def test_create_product_returns_502_on_integration_error(
        self, http_client: AsyncClient
    ):
        """POST /dolibarr/products retorna 502 cuando client lanza IntegrationError."""
        from services.integrations.base import IntegrationError

        svc = _mock_svc()
        svc.create_product = AsyncMock(
            side_effect=IntegrationError("create failed", platform="dolibarr")
        )

        with (
            patch("api.v1.endpoints.dolibarr.get_settings", return_value=_mock_settings()),
            patch("api.v1.endpoints.dolibarr._get_service", return_value=svc),
        ):
            response = await http_client.post(_BASE, json={"ref": "X"})

        assert response.status_code == 502

    @pytest.mark.asyncio
    async def test_update_product_returns_502_on_integration_error(
        self, http_client: AsyncClient
    ):
        """PUT /dolibarr/products/{id} retorna 502 cuando client lanza IntegrationError."""
        from services.integrations.base import IntegrationError

        svc = _mock_svc()
        svc.update_product = AsyncMock(
            side_effect=IntegrationError("update failed", platform="dolibarr")
        )

        with (
            patch("api.v1.endpoints.dolibarr.get_settings", return_value=_mock_settings()),
            patch("api.v1.endpoints.dolibarr._get_service", return_value=svc),
        ):
            response = await http_client.put(f"{_BASE}/1", json={"label": "X"})

        assert response.status_code == 502

    @pytest.mark.asyncio
    async def test_delete_product_returns_502_on_integration_error(
        self, http_client: AsyncClient
    ):
        """DELETE /dolibarr/products/{id} retorna 502 cuando client lanza IntegrationError."""
        from services.integrations.base import IntegrationError

        svc = _mock_svc()
        svc.delete_product = AsyncMock(
            side_effect=IntegrationError("delete failed", platform="dolibarr")
        )

        with (
            patch("api.v1.endpoints.dolibarr.get_settings", return_value=_mock_settings()),
            patch("api.v1.endpoints.dolibarr._get_service", return_value=svc),
        ):
            response = await http_client.delete(f"{_BASE}/1")

        assert response.status_code == 502


# ---------------------------------------------------------------------------
# POST /dolibarr/products/sync
# ---------------------------------------------------------------------------


class TestSyncFromJob:
    """Tests para POST /api/v1/dolibarr/products/sync."""

    @pytest.mark.asyncio
    async def test_sync_from_job_returns_list_with_action_per_product(
        self, http_client: AsyncClient
    ):
        """sync_from_job devuelve una lista con el resultado por cada producto."""
        sync_results = [
            {"codigo": "PROD-1", "action": "created", "dolibarr_id": 10, "error": None},
            {"codigo": "PROD-2", "action": "skipped", "dolibarr_id": 7, "error": None},
        ]
        svc = _mock_svc(sync_return=sync_results)
        storage = MagicMock()

        with (
            patch(
                "api.v1.endpoints.dolibarr.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "api.v1.endpoints.dolibarr._get_service",
                return_value=svc,
            ),
            patch(
                "api.v1.endpoints.dolibarr.get_storage_service",
                return_value=storage,
            ),
        ):
            response = await http_client.post(
                f"{_BASE}/sync",
                json={
                    "job_id": "job-abc",
                    "product_codes": ["PROD-1", "PROD-2"],
                    "overwrite": False,
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["data"]) == 2
        actions = {r["codigo"]: r["action"] for r in body["data"]}
        assert actions["PROD-1"] == "created"
        assert actions["PROD-2"] == "skipped"
