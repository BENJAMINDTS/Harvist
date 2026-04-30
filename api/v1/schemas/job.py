"""
Schemas Pydantic para la entidad Job (trabajo de scraping).

Define los contratos de entrada/salida de la API y los estados internos
del pipeline. Estos tipos son el único punto de verdad compartido entre
la capa HTTP (api/) y la capa de servicios (services/).

:author: BenjaminDTS
:author: Carlitos6712
:version: 2.0.0
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


SUPPORTED_LANGUAGES = ("es", "en", "fr", "de", "it", "pt")

# ── Enums ─────────────────────────────────────────────────────────────────────

class EstadoJob(str, Enum):
    """
    Estados posibles de un trabajo de scraping a lo largo de su ciclo de vida.

    :author: BenjaminDTS
    """

    PENDIENTE = "pendiente"
    EN_PROCESO = "en_proceso"
    COMPLETADO = "completado"
    FALLIDO = "fallido"
    CANCELADO = "cancelado"
    PENDIENTE_SELECCION_FOTOS = "pendiente_seleccion_fotos"
    PENDIENTE_VALIDACION_MARCAS = "pendiente_validacion_marcas"


class ModosBusqueda(str, Enum):
    """
    Modos de construcción de la query de búsqueda de imágenes.

    :author: BenjaminDTS
    """

    EAN = "ean"                         # Busca por código de barras EAN/UPC
    NOMBRE_MARCA = "nombre_marca"       # Busca por nombre + marca del producto
    PERSONALIZADO = "personalizado"     # Query personalizada definida por el usuario


class TipoJob(str, Enum):
    """
    Tipo de trabajo a ejecutar: descarga de fotos, generación de descripciones con IA,
    generación de textos SEO o scraping de información de marca.

    Son mutuamente excluyentes: un job solo puede hacer uno de los tipos.

    :author: Carlitos6712
    :author: BenjaminDTS
    """

    FOTOS = "fotos"                         # Scraping y descarga de imágenes
    DESCRIPCIONES = "descripciones"         # Generación de descripciones con Claude API
    SEO = "seo"                             # Generación de meta_title + meta_description (Fase 7.1)
    MARCAS = "marcas"                       # Scraping de información de marca (Fase 6)


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
        description="Requerido si action es 'edit'. Texto editado por el usuario.",
    )

    @model_validator(mode="after")
    def edited_text_required_when_edit(self) -> "DescriptionReviewRequest":
        """
        Valida que edited_text esté presente cuando action es 'edit'.

        Returns:
            La instancia validada.

        Raises:
            ValueError: si action es 'edit' y edited_text está ausente o vacío.
        """
        if self.action == ReviewAction.EDIT and not self.edited_text:
            raise ValueError("edited_text es requerido cuando action es 'edit'")
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
        description="Texto editado por el usuario (solo cuando action='edit').",
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


# ── Configuración de búsqueda ─────────────────────────────────────────────────

class ColumnMapping(BaseModel):
    """
    Mapeo entre las columnas del CSV del usuario y los campos internos del parser.

    Permite que el CSV tenga cualquier nombre de columna: el usuario indica
    qué columna de su archivo corresponde a cada campo requerido, en lugar de
    obligarle a renombrar las columnas antes de subir el archivo.

    :author: BenjaminDTS
    """

    columna_codigo: str = Field(
        default="codigo",
        description="Columna del CSV que contiene el código único del producto.",
    )
    columna_ean: str = Field(
        default="ean",
        description="Columna del CSV que contiene el EAN/código de barras.",
    )
    columna_nombre: str = Field(
        default="nombre",
        description="Columna del CSV que contiene el nombre del producto.",
    )
    columna_marca: str = Field(
        default="marca",
        description="Columna del CSV que contiene la marca del producto.",
    )
    columna_categoria: str = Field(
        default="categoria",
        description="Columna del CSV que contiene la categoría del producto (opcional).",
    )
    columna_nombre_foto: str = Field(
        default="",
        description=(
            "Columna del CSV cuyo valor se usa para nombrar los archivos de imagen. "
            "Si está vacía se usa la columna de código."
        ),
    )


class SearchConfig(BaseModel):
    """
    Parámetros que controlan el comportamiento del scraper para un job concreto.

    :author: BenjaminDTS
    """

    modo: ModosBusqueda = Field(
        default=ModosBusqueda.NOMBRE_MARCA,
        description="Modo de construcción de la query de búsqueda.",
    )
    imagenes_por_producto: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Número de imágenes a intentar descargar por producto.",
    )
    tipo_job: TipoJob = Field(
        default=TipoJob.FOTOS,
        description=(
            "Tipo de trabajo: 'fotos' ejecuta el scraping de imágenes, "
            "'descripciones' genera descripciones de catálogo con Claude API. "
            "Ambos modos son mutuamente excluyentes."
        ),
    )
    query_personalizada: str | None = Field(
        default=None,
        description="Plantilla de query cuando modo=PERSONALIZADO. "
                    "Usa {nombre}, {marca}, {ean} como placeholders.",
        examples=["{nombre} {marca} imagen fondo blanco"],
    )
    groq_api_key_usuario: str = Field(
        default="",
        description="API key de Groq introducida por el usuario desde el formulario. "
                    "Si está rellena, tiene prioridad sobre la variable de entorno GROQ_API_KEY.",
    )
    store_type_usuario: str = Field(
        default="",
        description="Tipo de tienda introducido por el usuario (ej: 'tiendas de mascotas'). "
                    "Si está relleno, tiene prioridad sobre CLAUDE_STORE_TYPE del .env.",
    )
    generate_seo: bool = Field(
        default=False,
        description="Activa generación de textos SEO (meta_title + meta_description) con Groq (Fase 7.1). "
                    "Independiente de tipo_job, puede combinarse con FOTOS o DESCRIPCIONES.",
    )
    target_languages: list[str] = Field(
        default_factory=list,
        description=(
            "Idiomas destino para traducción automática (Fase 7.2). "
            f"Valores permitidos: {SUPPORTED_LANGUAGES}. "
            "Lista vacía = sin traducción."
        ),
        examples=[["en", "fr"]],
    )
    validate_brands: bool = Field(
        default=False,
        description=(
            "Si True, el job espera validación manual antes de escribir "
            "marcas nuevas en brand_cache.json (Fase 7.4). "
            "Solo aplica cuando tipo_job=MARCAS."
        ),
    )
    select_photos: bool = Field(
        default=False,
        description=(
            "Si True, el job descarga TODAS las candidatas de imagen por producto "
            "y espera selección manual de la mejor antes de generar el ZIP (Fase 7.5). "
            "Solo aplica cuando tipo_job=FOTOS."
        ),
    )
    column_mapping: ColumnMapping = Field(
        default_factory=ColumnMapping,
        description="Mapeo de columnas del CSV del usuario a los campos internos del parser.",
    )

    @field_validator("target_languages")
    @classmethod
    def validar_idiomas(cls, v: list[str]) -> list[str]:
        """
        Valida que todos los idiomas estén en SUPPORTED_LANGUAGES y elimina duplicados.

        Args:
            v: lista de códigos de idioma.

        Returns:
            Lista deduplicada de idiomas válidos.

        Raises:
            ValueError: si algún idioma no está soportado.
        """
        invalidos = [lang for lang in v if lang not in SUPPORTED_LANGUAGES]
        if invalidos:
            raise ValueError(
                f"Idiomas no soportados: {invalidos}. "
                f"Idiomas válidos: {list(SUPPORTED_LANGUAGES)}"
            )
        return list(dict.fromkeys(v))


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
