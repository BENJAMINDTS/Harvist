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


# ── Configuración de búsqueda ─────────────────────────────────────────────────

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
    query_personalizada: str | None = Field(
        default=None,
        description="Plantilla de query cuando modo=PERSONALIZADO. "
                    "Usa {nombre}, {marca}, {ean} como placeholders.",
        examples=["{nombre} {marca} imagen fondo blanco"],
    )
    generar_descripciones: bool = Field(
        default=False,
        description="Si True, genera descripciones con IA tras descargar las imágenes (Fase 5).",
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
