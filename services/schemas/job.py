"""
Schemas de dominio compartidos entre la capa de servicios y la capa HTTP.

Contiene los tipos que definen el comportamiento del pipeline de scraping:
enums de estado/tipo, configuración de búsqueda y mapeo de columnas CSV.

Estos tipos NO son exclusivos de la API HTTP — los servicios los usan
directamente sin depender de api/.

:author: BenjaminDTS
:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator

SUPPORTED_LANGUAGES = ("es", "en", "fr", "de", "it", "pt")


# ── Enums de dominio ──────────────────────────────────────────────────────────

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

    EAN = "ean"
    NOMBRE_MARCA = "nombre_marca"
    PERSONALIZADO = "personalizado"


class TipoJob(str, Enum):
    """
    Tipo de trabajo a ejecutar: descarga de fotos, generación de descripciones con IA,
    generación de textos SEO o scraping de información de marca.

    Son mutuamente excluyentes: un job solo puede hacer uno de los tipos.

    :author: Carlitos6712
    :author: BenjaminDTS
    """

    FOTOS = "fotos"
    DESCRIPCIONES = "descripciones"
    SEO = "seo"
    MARCAS = "marcas"


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
