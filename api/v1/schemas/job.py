"""
Schemas Pydantic para la entidad Job (trabajo de scraping).

Define los contratos de entrada/salida de la API y los estados internos
del pipeline. Estos tipos son el único punto de verdad compartido entre
la capa HTTP (api/) y la capa de servicios (services/).

:author: BenjaminDTS
:version: 1.0.0
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


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
    Tipo de trabajo a ejecutar: descarga de fotos o generación de descripciones con IA.

    Son mutuamente excluyentes: un job solo puede hacer uno de los dos.

    :author: Carlitos6712
    """

    FOTOS = "fotos"                         # Scraping y descarga de imágenes
    DESCRIPCIONES = "descripciones"         # Generación de descripciones con Claude API


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
    column_mapping: ColumnMapping = Field(
        default_factory=ColumnMapping,
        description="Mapeo de columnas del CSV del usuario a los campos internos del parser.",
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
    mensaje: str
    error: str | None = None
