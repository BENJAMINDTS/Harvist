"""
Schemas Pydantic para la entidad Job (trabajo de scraping).

Define los contratos de entrada/salida de la API y los estados internos
del pipeline. Los tipos de dominio compartidos con services/ se importan
desde services.schemas.job y se re-exportan para mantener compatibilidad.

:author: BenjaminDTS
:author: Carlitos6712
:version: 2.1.0
"""

from datetime import datetime
from enum import Enum
from typing import Any, ClassVar
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

# Re-export domain types from the service layer so all existing imports
# from api.v1.schemas.job continue to work unchanged.
from services.schemas.job import (  # noqa: F401
    SUPPORTED_LANGUAGES,
    ColumnMapping,
    EstadoJob,
    ModosBusqueda,
    SearchConfig,
    TipoJob,
)


# ── Revisión manual de descripciones (Fase 7.3) ──────────────────────────────

class ReviewAction(str, Enum):
    """
    Acción que el usuario aplica sobre una descripción en revisión.

    :author: Carlitos6712
    """

    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"


class ReviewStatus(str, Enum):
    """
    Estado de revisión de una descripción individual.

    :author: Carlitos6712
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class DescriptionReviewRequest(BaseModel):
    """
    Body de la petición PATCH para revisar una descripción.

    :author: Carlitos6712
    """

    action: ReviewAction = Field(description="Acción a aplicar: approve, reject o edit.")
    edited_text: str | None = Field(
        default=None,
        description="Descripción corta editada por el usuario (opcional cuando action es 'edit').",
    )
    edited_larga: str | None = Field(
        default=None,
        description="Descripción larga editada por el usuario (opcional cuando action es 'edit').",
    )

    @model_validator(mode="after")
    def edited_text_required_when_edit(self) -> "DescriptionReviewRequest":
        """
        Valida que al menos uno de edited_text o edited_larga esté presente cuando action es 'edit'.

        Returns:
            La instancia validada.

        Raises:
            ValueError: si action es 'edit' y ningún campo editado está presente.
        """
        if self.action == ReviewAction.EDIT and not self.edited_text and not self.edited_larga:
            raise ValueError(
                "Al menos uno de edited_text (corta) o edited_larga debe estar presente cuando action es 'edit'"
            )
        return self


class DescriptionReviewState(BaseModel):
    """
    Estado de revisión almacenado en Redis para cada descripción individual.

    Clave Redis: job:{job_id}:review:{codigo}

    :author: Carlitos6712
    """

    codigo: str = Field(description="Código del producto.")
    status: ReviewStatus = Field(
        default=ReviewStatus.PENDING,
        description="Estado de revisión de la descripción.",
    )
    edited_text: str | None = Field(
        default=None,
        description="Descripción corta editada por el usuario.",
    )
    edited_larga: str | None = Field(
        default=None,
        description="Descripción larga editada por el usuario.",
    )


class DescriptionReviewEntry(DescriptionReviewState):
    """
    Entrada de revisión enriquecida con el contenido de la descripción.

    Combina el estado de revisión de Redis con los datos del CSV de descripciones,
    para devolver al frontend toda la información necesaria en un solo objeto.

    :author: Carlitos6712
    """

    nombre: str = Field(default="", description="Nombre del producto.")
    descripcion_corta: str = Field(default="", description="Descripción corta generada por IA.")
    descripcion_larga: str = Field(default="", description="Descripción larga generada por IA.")


# ── Revisión de traducciones (Fase 7.2 — extensión revisión) ─────────────────


class TranslationReviewRequest(BaseModel):
    """
    Body de la petición PATCH para revisar una traducción.

    Permite aprobar, rechazar o editar descripcion_corta y/o descripcion_larga
    de la traducción de un producto en un idioma concreto.

    :author: BenjaminDTS
    """

    action: ReviewAction = Field(description="Acción a aplicar: approve, reject o edit.")
    edited_corta: str | None = Field(
        default=None,
        description="Descripción corta traducida editada (opcional cuando action es 'edit').",
    )
    edited_larga: str | None = Field(
        default=None,
        description="Descripción larga traducida editada (opcional cuando action es 'edit').",
    )

    @model_validator(mode="after")
    def validate_edit_fields(self) -> "TranslationReviewRequest":
        """
        Valida que al menos un campo editado esté presente cuando action es 'edit'.

        Returns:
            La instancia validada.

        Raises:
            ValueError: si action es 'edit' y ningún campo editado está presente.
        """
        if self.action == ReviewAction.EDIT and not self.edited_corta and not self.edited_larga:
            raise ValueError(
                "Al menos uno de edited_corta o edited_larga debe estar presente cuando action es 'edit'"
            )
        return self


class TranslationReviewState(BaseModel):
    """
    Estado de revisión de una traducción almacenado en Redis.

    Clave Redis: job:{job_id}:trad_review:{lang}:{codigo}

    :author: BenjaminDTS
    """

    codigo: str = Field(description="Código del producto.")
    lang: str = Field(description="Código ISO 639-1 del idioma (ej: 'en', 'fr').")
    status: ReviewStatus = Field(
        default=ReviewStatus.PENDING,
        description="Estado de revisión de la traducción.",
    )
    edited_corta: str | None = Field(
        default=None,
        description="Descripción corta editada por el usuario.",
    )
    edited_larga: str | None = Field(
        default=None,
        description="Descripción larga editada por el usuario.",
    )


class TranslationReviewEntry(TranslationReviewState):
    """
    Entrada de revisión de traducción enriquecida con el contenido del CSV.

    Combina el estado de revisión de Redis con los datos del CSV de traducciones
    para devolver al frontend toda la información en un solo objeto.

    :author: BenjaminDTS
    """

    nombre: str = Field(default="", description="Nombre del producto.")
    descripcion_corta: str = Field(default="", description="Descripción corta traducida por IA.")
    descripcion_larga: str = Field(default="", description="Descripción larga traducida por IA.")
    keywords: str = Field(default="", description="Keywords SEO traducidas.")
    meta_description: str = Field(default="", description="Meta description SEO traducida.")


# ── Validación de marcas (Fase 7.4) ───────────────────────────────────────────

class BrandValidationAction(str, Enum):
    """
    Acción que el usuario aplica sobre una marca pendiente de validación.

    :author: Carlitos6712
    """

    ACCEPT = "accept"
    REJECT = "reject"
    EDIT = "edit"


class BrandValidationItem(BaseModel):
    """
    Item de validación de una marca nueva antes de persistirla en brand_cache.json.

    :author: Carlitos6712
    """

    ean: str = Field(description="Código EAN del producto.")
    brand_name: str = Field(description="Nombre de marca resuelto por el scraper.")
    action: BrandValidationAction = Field(
        description="Decisión del usuario: accept, reject o edit."
    )
    edited_name: str | None = Field(
        default=None,
        description="Nombre editado por el usuario. Requerido si action es 'edit'.",
    )

    @model_validator(mode="after")
    def edited_name_required_when_edit(self) -> "BrandValidationItem":
        """
        Valida que edited_name esté presente cuando action es 'edit'.

        Returns:
            La instancia validada.

        Raises:
            ValueError: si action es 'edit' y edited_name está ausente o vacío.
        """
        if self.action == BrandValidationAction.EDIT and not self.edited_name:
            raise ValueError("edited_name es requerido cuando action es 'edit'")
        return self


class BrandValidationRequest(BaseModel):
    """
    Body de la petición POST para validar marcas nuevas de un job.

    :author: Carlitos6712
    """

    items: list[BrandValidationItem] = Field(
        min_length=1,
        description="Lista de marcas con su decisión. Mínimo 1 item.",
    )


# ── Selección de fotos (Fase 7.5) ─────────────────────────────────────────────

class PhotoSelectionItem(BaseModel):
    """
    Item de selección de foto para un producto.

    :author: BenjaminDTS
    """

    codigo: str = Field(description="Código único del producto.")
    selected_index: int = Field(
        ge=0,
        description="Índice de la candidata seleccionada (0-based)."
    )


class PhotoSelectionRequest(BaseModel):
    """
    Body de la petición POST para confirmar la selección de fotos de un job.

    :author: BenjaminDTS
    """

    selections: list[PhotoSelectionItem] = Field(
        min_length=1,
        description="Lista de productos con foto seleccionada. Mínimo 1 item."
    )


class CandidateInfo(BaseModel):
    """
    Metadatos de una imagen candidata para previsualización en el frontend.

    :author: BenjaminDTS
    """

    index: int = Field(description="Índice de la candidata (0-based).")
    url: str = Field(description="URL de endpoint para servir la candidata.")
    width: int = Field(ge=1, description="Ancho de la imagen en píxeles.")
    height: int = Field(ge=1, description="Alto de la imagen en píxeles.")
    size_bytes: int = Field(ge=1, description="Tamaño del archivo en bytes.")


class ProductPhotos(BaseModel):
    """
    Información de fotos de un producto con sus candidatas disponibles.

    :author: BenjaminDTS
    """

    codigo: str = Field(description="Código único del producto.")
    nombre: str = Field(description="Nombre del producto.")
    n_candidates: int = Field(
        ge=0,
        description="Número total de candidatas disponibles."
    )
    candidates: list[CandidateInfo] = Field(
        description="Lista de candidatas disponibles para selección."
    )
    selected_index: int | None = Field(
        default=None,
        description="Índice de la foto seleccionada (None si no seleccionada aún)."
    )


# ── Schemas de entrada ────────────────────────────────────────────────────────

class JobCreate(BaseModel):
    """
    Payload de creación de un nuevo trabajo de scraping.

    El CSV se recibe como archivo multipart/form-data en el endpoint,
    no como campo de este schema. Este modelo define los parámetros opcionales.

    :author: BenjaminDTS
    """

    config: SearchConfig = Field(
        default_factory=SearchConfig,
        description="Configuración del scraper para este trabajo.",
    )


# ── Estado interno del job (almacenado en Redis) ──────────────────────────────

class JobStatus(BaseModel):
    """
    Estado completo de un trabajo de scraping.

    Se serializa a JSON y se almacena en Redis bajo la clave job:{job_id}.
    El WebSocket de progreso emite actualizaciones de este modelo.

    :author: BenjaminDTS
    :author: Carlitos6712
    """

    job_id: UUID = Field(description="Identificador único del trabajo.")
    estado: EstadoJob = Field(default=EstadoJob.PENDIENTE)
    total_productos: int = Field(default=0, ge=0)
    productos_procesados: int = Field(default=0, ge=0)
    imagenes_descargadas: int = Field(default=0, ge=0)
    imagenes_fallidas: int = Field(default=0, ge=0)
    imagenes_cache_hit: int = Field(
        default=0,
        ge=0,
        description="Imágenes reutilizadas desde la caché de jobs anteriores.",
    )
    descripciones_generadas: int = Field(
        default=0,
        ge=0,
        description="Contador de descripciones generadas por IA (Fase 5).",
    )
    seo_generados: int = Field(
        default=0,
        ge=0,
        description="Contador de textos SEO (meta_title + meta_description) generados (Fase 7.1).",
    )
    seo_errores: int = Field(
        default=0,
        ge=0,
        description="Contador de errores durante generación SEO (Fase 7.1).",
    )
    traducciones_generadas: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Contador de traducciones generadas por idioma (Fase 7.2). "
            "Ejemplo: {'en': 42, 'fr': 42}."
        ),
    )
    marcas_procesadas: int = Field(
        default=0,
        ge=0,
        description="Contador de marcas procesadas (Fase 6).",
    )
    marcas_pendientes_validacion: int = Field(
        default=0,
        ge=0,
        description="Número de marcas nuevas pendientes de validación (Fase 7.4).",
    )
    fotos_pendientes_seleccion: int = Field(
        default=0,
        ge=0,
        description="Número de productos sin foto seleccionada (Fase 7.5).",
    )
    revisiones_pendientes: int = Field(
        default=0,
        ge=0,
        description="Contador de descripciones pendientes de revisión (Fase 7.3).",
    )
    revisiones_aprobadas: int = Field(
        default=0,
        ge=0,
        description="Contador de descripciones aprobadas por el usuario (Fase 7.3).",
    )
    revisiones_rechazadas: int = Field(
        default=0,
        ge=0,
        description="Contador de descripciones rechazadas por el usuario (Fase 7.3).",
    )
    mensaje: str = Field(default="", description="Mensaje de estado legible por humanos.")
    error: str | None = Field(default=None, description="Detalle del error si estado=FALLIDO.")
    creado_en: datetime = Field(default_factory=datetime.utcnow)
    actualizado_en: datetime = Field(default_factory=datetime.utcnow)
    completado_en: datetime | None = Field(default=None)
    productos_fallidos: list[str] = Field(
        default_factory=list,
        description="Códigos de productos que fallaron en el último procesamiento.",
    )
    reintentos: int = Field(
        default=0,
        description="Número de veces que se ha reintentado este job.",
    )
    MAX_REINTENTOS: ClassVar[int] = 3

    @property
    def porcentaje(self) -> float:
        """Calcula el porcentaje de progreso entre 0.0 y 100.0."""
        if self.total_productos == 0:
            return 0.0
        return round((self.productos_procesados / self.total_productos) * 100, 2)


# ── Schemas de respuesta (contrato HTTP) ──────────────────────────────────────

class JobResponse(BaseModel):
    """
    Respuesta estándar de la API para operaciones sobre un Job.

    Sigue el contrato: { success, data, message }.

    :author: BenjaminDTS
    """

    success: bool
    data: dict[str, Any]
    message: str


class JobProgressEvent(BaseModel):
    """
    Evento emitido por WebSocket con el progreso en tiempo real del job.

    :author: BenjaminDTS
    """

    job_id: str
    estado: EstadoJob
    porcentaje: float
    productos_procesados: int
    total_productos: int
    imagenes_descargadas: int
    imagenes_fallidas: int
    descripciones_generadas: int
    seo_generados: int = 0
    traducciones_generadas: dict[str, int] = Field(default_factory=dict)
    marcas_procesadas: int = 0
    mensaje: str
    error: str | None = None
    reintentos: int = 0
    n_productos_fallidos: int = 0


# ── Reintento parcial de productos fallidos ───────────────────────────────────

class RetryJobRequest(BaseModel):
    """
    Body de la petición POST para reintentar solo los productos fallidos de un job.

    Cada flag indica qué categoría de fallos se incluye en el reintento.
    Solo aplican las categorías compatibles con el tipo de job original.

    :author: BenjaminDTS
    """

    retry_images: bool = Field(
        default=True,
        description="Reintentar productos con imagen fallida.",
    )
    retry_brands: bool = Field(
        default=True,
        description="Reintentar productos con marca no resuelta.",
    )
    retry_descriptions: bool = Field(
        default=False,
        description="Reintentar productos con descripción fallida.",
    )
    retry_seo: bool = Field(
        default=False,
        description="Reintentar productos con SEO fallido.",
    )


class RetryJobResponse(BaseModel):
    """
    Respuesta de la petición POST de reintento parcial de productos fallidos.

    :author: BenjaminDTS
    """

    job_id: str = Field(description="ID del job sobre el que se aplica el reintento.")
    productos_a_reintentar: int = Field(description="Número de productos que se van a reprocesar.")
    reintentos_previos: int = Field(description="Número de reintentos ya realizados antes de este.")
