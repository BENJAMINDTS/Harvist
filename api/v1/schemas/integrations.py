"""
Schemas Pydantic compartidos para todas las integraciones ERP/CMS.

:author: Carlitos6712
:version: 1.0.0
"""

from pydantic import BaseModel, Field


class IntegrationStatus(BaseModel):
    """Estado de configuración y salud de una integración."""

    platform: str
    configured: bool
    healthy: bool | None = None
    message: str = ""


class PaginatedResponse(BaseModel):
    """Respuesta paginada genérica para listados de recursos de integración."""

    items: list[dict]
    total: int
    limit: int
    offset: int
    has_more: bool


class SyncFromJobRequest(BaseModel):
    """Petición de sincronización de productos desde un job Harvist a una plataforma ERP/CMS."""

    job_id: str
    product_codes: list[str] = Field(
        min_length=1,
        description="Códigos de producto del job Harvist a sincronizar.",
    )
    overwrite: bool = Field(
        default=False,
        description="Si True, sobreescribe productos existentes en Dolibarr.",
    )
