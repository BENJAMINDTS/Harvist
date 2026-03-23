"""
Configuración centralizada de la aplicación mediante Pydantic Settings v2.

Todas las variables se leen exclusivamente desde variables de entorno o archivo .env.
NUNCA hardcodear valores aquí — usar siempre get_settings().

:author: BenjaminDTS
:version: 1.0.0
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuración global de la aplicación.

    Valida y expone todas las variables de entorno al arranque.
    Si alguna variable obligatoria falta o tiene un valor inválido,
    Pydantic lanzará un ValidationError antes de que la app sirva tráfico.

    :author: BenjaminDTS
    """

    model_config = SettingsConfigDict(
        env_file=".env.development",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Entorno ──────────────────────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Entorno de ejecución de la aplicación.",
    )
    app_debug: bool = Field(default=False)
    secret_key: str = Field(..., min_length=16)

    # ── API ───────────────────────────────────────────────────────────────────
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_prefix: str = Field(default="/api/v1")
    allowed_origins: list[str] = Field(default=["http://localhost:5173"])

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: str | list[str]) -> list[str]:
        """Convierte un string CSV de orígenes en lista si viene del .env."""
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value

    # ── Redis / Celery ────────────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0")
    celery_broker_url: str = Field(default="redis://localhost:6379/0")
    celery_result_backend: str = Field(default="redis://localhost:6379/1")

    # ── Navegador ─────────────────────────────────────────────────────────────
    browser_type: Literal["chrome", "opera", "edge", "brave", "chromium"] = Field(
        default="chrome"
    )
    browser_binary_path: str = Field(
        default="",
        description=(
            "Ruta al ejecutable del navegador. "
            "Dejar vacío para Chrome/Chromium (auto-detección). "
            "Obligatoria para opera | brave | edge."
        ),
    )
    browser_headless: bool = Field(default=True)
    browser_version_main: int | None = Field(
        default=None,
        description="Versión principal de Chromium del navegador (requerida para Opera/Brave).",
    )
    browser_timeout: int = Field(default=15, ge=5, le=120)

    @field_validator("browser_binary_path", mode="after")
    @classmethod
    def _validate_binary_path(cls, value: str, info) -> str:
        """Valida que la ruta al binario esté presente cuando el navegador la requiere."""
        browser_type = info.data.get("browser_type", "chrome")
        requires_path = {"opera", "brave", "edge"}
        if browser_type in requires_path and not value:
            raise ValueError(
                f"BROWSER_BINARY_PATH es obligatoria cuando BROWSER_TYPE={browser_type}."
            )
        return value

    # ── Scraper / Búsqueda ────────────────────────────────────────────────────
    images_per_product: int = Field(default=5, ge=1, le=20)
    image_min_width: int = Field(default=200, ge=1)
    image_min_height: int = Field(default=200, ge=1)
    image_resize_width: int = Field(default=800, ge=1)
    image_resize_height: int = Field(default=800, ge=1)
    download_workers: int = Field(default=4, ge=1, le=32)
    download_timeout: int = Field(default=10, ge=1, le=60)

    # ── Scraper — motor de búsqueda ───────────────────────────────────────────
    search_engine: Literal["bing", "google", "duckduckgo"] = Field(
        default="bing",
        description="Motor de búsqueda de imágenes: bing | google | duckduckgo.",
    )

    # ── Almacenamiento ────────────────────────────────────────────────────────
    storage_backend: Literal["local", "s3", "azure"] = Field(
        default="local",
        description="Backend de almacenamiento: local | s3 | azure.",
    )
    output_dir: str = Field(default="imagenes_descargadas")
    file_ttl_seconds: int = Field(default=86400, ge=60)

    # ── AWS S3 (solo si storage_backend=s3) ──────────────────────────────────
    aws_s3_bucket: str = Field(default="")
    aws_s3_prefix: str = Field(default="harvist")
    aws_region: str = Field(default="eu-west-1")
    aws_access_key_id: str = Field(default="")
    aws_secret_access_key: str = Field(default="")

    # ── Azure Blob (solo si storage_backend=azure) ───────────────────────────
    azure_container: str = Field(default="")
    azure_blob_prefix: str = Field(default="harvist")
    azure_connection_string: str = Field(default="")

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: Literal["ERROR", "WARN", "INFO", "DEBUG"] = Field(default="INFO")
    log_dir: str = Field(default="logs")
    log_rotation: str = Field(default="100 MB")
    log_retention: str = Field(default="7 days")

    # ── IA — Fase 5 (Claude API) ──────────────────────────────────────────────
    enable_ai_descriptions: bool = Field(default=False)
    claude_api_key: str = Field(
        default="",
        description="API key de Anthropic Claude. Obligatoria si ENABLE_AI_DESCRIPTIONS=true.",
    )
    claude_model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Modelo Claude a usar para generar descripciones.",
    )
    claude_max_tokens: int = Field(
        default=300,
        ge=50,
        le=4096,
        description="Máximo de tokens por descripción generada.",
    )
    claude_timeout: int = Field(default=30, ge=5)
    claude_max_retries: int = Field(default=3, ge=1)
    claude_store_type: str = Field(
        default="tiendas de mascotas",
        description=(
            "Tipo de tienda inyectado en el prompt de descripciones. "
            "Ejemplos: 'tiendas de mascotas', 'tiendas de ropa deportiva', 'ferreterías'."
        ),
    )
    claude_batch_size: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Número de productos enviados a Claude por llamada (procesamiento en batch).",
    )
    claude_prompt_file: str = Field(
        default="",
        description=(
            "Ruta a un archivo .txt con una plantilla de prompt personalizada. "
            "Debe contener los placeholders {store_type} y {productos_json}. "
            "Si está vacío se usa el prompt SEO por defecto."
        ),
    )

    @field_validator("claude_api_key", mode="after")
    @classmethod
    def _validate_claude_key(cls, value: str, info) -> str:
        """Valida que la API key de Claude esté presente si la IA está habilitada."""
        enable = info.data.get("enable_ai_descriptions", False)
        if enable and not value:
            raise ValueError(
                "CLAUDE_API_KEY es obligatoria cuando ENABLE_AI_DESCRIPTIONS=true"
            )
        return value

    @property
    def is_production(self) -> bool:
        """Devuelve True si el entorno es producción."""
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        """Devuelve True si el entorno es desarrollo."""
        return self.app_env == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Devuelve la instancia singleton de Settings.

    Usa lru_cache para que Pydantic no vuelva a leer el .env en cada llamada.
    En tests, llama a get_settings.cache_clear() antes de sobreescribir vars.

    Returns:
        Settings: instancia validada con todas las variables de entorno.

    Raises:
        ValidationError: si alguna variable obligatoria falta o es inválida.
    """
    return Settings()
