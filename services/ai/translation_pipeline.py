"""
Pipeline de traducción automática de descripciones de producto (Fase 7.2).

Traduce las descripciones generadas por DescripcionPipeline a uno o varios
idiomas destino usando la API de Claude/Groq. Procesa todos los productos
en un único batch por idioma para minimizar llamadas a la API.

Flujo:
  1. Recibe lista de Producto + lista de ResultadoDescripcion (ya generadas)
  2. DescriptionGenerator.translate_descriptions() → traducciones por idioma
  3. Exportar traducciones_{lang}.csv al storage del job

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

import csv
import io

from loguru import logger

from api.core.config import get_settings
from api.v1.schemas.job import SearchConfig
from services.ai.claude_client import ClaudeClient
from services.ai.description_generator import (
    DescriptionGenerator,
    ResultadoDescripcion,
    ResultadoTraduccion,
)
from services.csv_parser import Producto
from services.storage_service import StorageService, get_storage_service


class TranslationPipeline:
    """
    Orquestador del proceso de traducción de descripciones SEO para un job.

    Recibe los productos y descripciones ya generadas en memoria,
    llama a DescriptionGenerator.translate_descriptions() por cada idioma destino
    y guarda un CSV independiente por idioma en el storage del job.

    :author: BenjaminDTS
    """

    def __init__(
        self,
        job_id: str,
        config: SearchConfig,
        storage: StorageService | None = None,
        carpeta_job_id: str | None = None,
    ) -> None:
        """
        Inicializa el pipeline de traducción para un job concreto.

        Args:
            job_id: identificador del job (usado para progreso y logs).
            config: configuración del job (lee target_languages, api keys).
            storage: servicio de almacenamiento. Si None, usa el factory por defecto.
            carpeta_job_id: job_id cuya carpeta de almacenamiento se reutiliza.
                Si None usa job_id.
        """
        self._job_id = job_id
        self._carpeta_id = carpeta_job_id or job_id
        self._config = config
        self._storage = storage or get_storage_service()

    def ejecutar(
        self,
        productos: list[Producto],
        descripciones: list[ResultadoDescripcion],
        idioma_destino: str,
    ) -> dict:
        """
        Traduce las descripciones al idioma destino y guarda el CSV resultante.

        Args:
            productos: lista de productos del job (mismo orden que descripciones).
            descripciones: lista de ResultadoDescripcion generadas previamente.
            idioma_destino: código ISO 639-1 del idioma destino (ej: 'en', 'fr').

        Returns:
            Diccionario con: idioma, total_productos, traducciones_generadas,
            traducciones_fallidas.
        """
        logger.info(
            "Pipeline de traducción iniciado",
            extra={"job_id": self._job_id, "idioma": idioma_destino},
        )

        # ── Inicializar cliente IA ────────────────────────────────────────────
        settings = get_settings()
        if settings.ai_provider == "groq":
            ai_api_key = self._config.groq_api_key_usuario or settings.groq_api_key
            ai_model = settings.groq_model
        else:
            ai_api_key = settings.claude_api_key
            ai_model = settings.claude_model

        claude_client = ClaudeClient(
            api_key=ai_api_key,
            model=ai_model,
            max_tokens=settings.claude_max_tokens,
            timeout=settings.claude_timeout,
            max_retries=settings.claude_max_retries,
            provider=settings.ai_provider,
        )
        store_type = self._config.store_type_usuario or settings.claude_store_type
        generator = DescriptionGenerator(
            client=claude_client,
            store_type=store_type,
        )

        # ── Traducir en batch ─────────────────────────────────────────────────
        resultados = generator.translate_descriptions(
            productos=productos,
            descripciones=descripciones,
            idioma_destino=idioma_destino,
        )

        traducciones_ok = sum(1 for r in resultados if r.exitoso)
        traducciones_fail = sum(1 for r in resultados if not r.exitoso)

        # ── Guardar CSV ───────────────────────────────────────────────────────
        self._guardar_csv(resultados, idioma_destino)

        resumen = {
            "idioma": idioma_destino,
            "total_productos": len(productos),
            "traducciones_generadas": traducciones_ok,
            "traducciones_fallidas": traducciones_fail,
        }

        logger.info(
            "Pipeline de traducción completado",
            extra={
                "job_id": self._job_id,
                "idioma": idioma_destino,
                "traducciones_generadas": traducciones_ok,
                "traducciones_fallidas": traducciones_fail,
            },
        )
        return resumen

    def _guardar_csv(
        self,
        traducciones: list[ResultadoTraduccion],
        idioma_destino: str,
    ) -> None:
        """
        Serializa las traducciones a CSV y las guarda en el storage del job.

        El archivo se guarda como traducciones_{lang}.csv en la carpeta del job.

        Args:
            traducciones: lista de ResultadoTraduccion del generador.
            idioma_destino: código ISO 639-1 del idioma (ej: 'en').
        """
        fieldnames = [
            "codigo",
            "nombre",
            "marca",
            "categoria",
            "idioma",
            "descripcion_corta",
            "descripcion_larga",
            "keywords",
            "meta_description",
            "exitoso",
            "error",
        ]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for r in traducciones:
            writer.writerow({
                "codigo": r.codigo,
                "nombre": r.nombre,
                "marca": r.marca,
                "categoria": r.categoria,
                "idioma": r.idioma,
                "descripcion_corta": r.descripcion_corta,
                "descripcion_larga": r.descripcion_larga,
                "keywords": r.keywords,
                "meta_description": r.meta_description,
                "exitoso": r.exitoso,
                "error": r.error,
            })

        filename = f"traducciones_{idioma_destino}.csv"
        try:
            self._storage.save_image(
                self._carpeta_id,
                filename,
                buffer.getvalue().encode("utf-8-sig"),
            )
            logger.info(
                f"{filename} guardado",
                extra={"job_id": self._job_id, "filas": len(traducciones)},
            )
        except Exception as exc:
            logger.error(
                f"Error al guardar {filename}",
                exc_info=exc,
                extra={"job_id": self._carpeta_id},
            )
