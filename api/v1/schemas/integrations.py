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


class DolibarrConfigRequest(BaseModel):
    """Petición para guardar configuración de Dolibarr."""

    url: str = Field(..., min_length=1, description="URL base de Dolibarr.")
    api_key: str = Field(..., min_length=1, description="API Key de Dolibarr.")


class DolibarrConfigResponse(BaseModel):
    """Respuesta con configuración actual de Dolibarr."""

    url: str
    api_key: str
    configured: bool


class DolibarrDBConfigRequest(BaseModel):
    """Petición para guardar credenciales de BD de Dolibarr."""

    host: str = Field(..., min_length=1, description="Host MySQL/MariaDB.")
    port: int = Field(default=3306, ge=1, le=65535)
    db_name: str = Field(..., min_length=1, description="Nombre de la base de datos.")
    user: str = Field(..., min_length=1, description="Usuario MySQL.")
    password: str = Field(default="", description="Contraseña MySQL.")
    prefix: str = Field(default="llx_", description="Prefijo de tablas Dolibarr.")


class DolibarrDBConfigResponse(BaseModel):
    """Respuesta con configuración de BD de Dolibarr."""

    host: str
    port: int
    db_name: str
    user: str
    password: str
    prefix: str
    configured: bool


class DolibarrExtraFieldCreate(BaseModel):
    """Petición para crear un campo extra en Dolibarr."""

    attrname: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Nombre interno del campo (minúsculas, sin espacios).",
    )
    label: str = Field(..., min_length=1, description="Etiqueta visible en la interfaz.")
    type: str = Field(
        default="varchar",
        description="Tipo de campo Dolibarr: varchar, int, double, price, date, select, boolean, text, html.",
    )
    elementtype: str = Field(
        default="product",
        description="Tipo de elemento Dolibarr: product, societe, facture, etc.",
    )
    size: str = Field(default="255", description="Tamaño del campo (relevante para varchar).")
    required: bool = Field(default=False, description="Si el campo es obligatorio.")
    fielddefault: str = Field(default="", description="Valor por defecto.")


class DolibarrExtraField(BaseModel):
    """Definición de un campo extra de Dolibarr."""

    attrname: str
    label: str
    type: str
    type_normalized: str
    elementtype: str
    size: str
    required: bool
    fielddefault: str


class OdooConfigRequest(BaseModel):
    """Petición para guardar configuración de Odoo."""

    url: str = Field(..., min_length=1, description="URL base de Odoo.")
    db: str = Field(..., min_length=1, description="Nombre de la base de datos.")
    user: str = Field(..., min_length=1, description="Email/login del usuario.")
    password: str = Field(..., min_length=1, description="Contraseña del usuario.")


class OdooConfigResponse(BaseModel):
    """Respuesta con configuración actual de Odoo."""

    url: str
    db: str
    user: str
    password: str
    configured: bool


class WordPressConfigRequest(BaseModel):
    """Petición para guardar configuración de WordPress/WooCommerce."""

    url: str = Field(..., min_length=1, description="URL base de la tienda WordPress.")
    consumer_key: str = Field(default="", description="Consumer Key de WooCommerce (ck_...). Vacío = mantener valor existente.")
    consumer_secret: str = Field(default="", description="Consumer Secret de WooCommerce (cs_...). Vacío = mantener valor existente.")


class WordPressConfigResponse(BaseModel):
    """Respuesta con configuración actual de WordPress."""

    url: str
    consumer_key: str
    consumer_secret: str
    configured: bool


class WordPressDBConfigRequest(BaseModel):
    """Petición para guardar credenciales de BD MySQL de WordPress."""

    host: str = Field(..., min_length=1, description="Host MySQL/MariaDB.")
    port: int = Field(default=3306, ge=1, le=65535)
    db_name: str = Field(..., min_length=1, description="Nombre de la base de datos.")
    user: str = Field(..., min_length=1, description="Usuario MySQL.")
    password: str = Field(default="", description="Contraseña MySQL.")
    prefix: str = Field(default="wp_", description="Prefijo de tablas WordPress.")


class WordPressDBConfigResponse(BaseModel):
    """Respuesta con configuración de BD de WordPress."""

    host: str
    port: int
    db_name: str
    user: str
    password: str
    prefix: str
    configured: bool


class CsvImportPreview(BaseModel):
    """Resultado del pre-análisis de un CSV de productos para importación masiva."""

    headers: list[str]
    preview: list[dict[str, str]]
    total_rows: int


class CsvImportRowResult(BaseModel):
    """Resultado de importar una fila del CSV a Dolibarr."""

    row: int
    ref: str
    action: str
    dolibarr_id: int | None = None
    error: str | None = None
    category_assigned: str | None = None


class CsvImportResponse(BaseModel):
    """Resumen completo de una importación masiva de CSV a Dolibarr."""

    total: int
    created: int
    updated: int
    skipped: int
    errors: int
    results: list[CsvImportRowResult]
