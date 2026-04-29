"""
Pipeline de generación de textos SEO (meta_title + meta_description) con Groq.

Módulo independiente para procesar productos y generar metadatos SEO optimizados
para búsqueda orgánica (SERP). Similar a description_pipeline.py pero con output
específico para SEO: meta_title (≤60 chars) y meta_description (≤160 chars).

Flujo:
  1. CsvParser → lista de productos validados
  2. DescriptionGenerator.generate_seo_texts() → textos SEO en lotes
  3. Exportar seo.csv al storage del job
  4. (No genera ZIP — el ZIP ya fue generado en scraping)

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

import csv
import io
from typing import Callable

from loguru import logger

from api.core.config import get_settings
from api.v1.schemas.job import SearchConfig
from services.ai.claude_client import ClaudeClient
from services.ai.description_generator import DescriptionGenerator, ResultadoSEO
from services.csv_parser import CsvParser, CsvParserError
from services.storage_service import StorageService, get_storage_service

# Firma: (job_id, procesados, total, seo_ok) -> None
SeoProgressCallback = Callable[[str, int, int, int], None]


class SeoPipeline:
    """
    Orquestador del proceso de generación de textos SEO para un job.

    Independiente del ScrapingPipeline: no realiza scraping ni descarga imágenes.
    Procesa los productos en batches para reducir llamadas a la API de Groq.
    El resultado es un archivo ``seo.csv`` guardado en el almacenamiento del job.

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
        Inicializa el pipeline de SEO para un job concreto.

        Args:
            job_id: identificador del job (usado para progreso y logs).
            config: configuración del job (solo se usan column_mapping).
            storage: servicio de almacenamiento. Si None, usa el factory por defecto.
            carpeta_job_id: job_id cuya carpeta de almacenamiento se reutiliza.
                Al reanudar un job se pasa el job_id original para que el CSV
                de SEO se escriba en la misma carpeta. Si None usa job_id.
        """
        self._job_id = job_id
        self._carpeta_id = carpeta_job_id or job_id
        self._config = config
        self._storage = storage or get_storage_service()

    def ejecutar(
        self,
        contenido_csv: str,
        callback: SeoProgressCallback | None = None,
        offset_productos: int = 0,
    ) -> dict:
        """
        Ejecuta el pipeline completo de generación SEO y devuelve un resumen.

        Args:
            contenido_csv: contenido del CSV como string (ya decodificado).
            callback: función de progreso invocada tras procesar cada batch.
                      Firma: (job_id, procesados, total, seo_ok)
            offset_productos: número de productos a saltar desde el inicio de
                la lista antes de comenzar a generar SEO. Se usa al reanudar
                un job. Por defecto 0 (procesar desde el principio).

        Returns:
            Diccionario con: total_productos, seo_generados, seo_errores, errores_csv.

        Raises:
            CsvParserError: si el CSV es inválido estructuralmente.
        """
        logger.info(
            "Pipeline de SEO iniciado",
            extra={"job_id": self._job_id, "offset_productos": offset_productos},
        )

        # ── Paso 1: Parsear CSV ───────────────────────────────────────────────
        parser = CsvParser(self._config)
        resultado_csv = parser.parsear(contenido_csv)

        if not resultado_csv.productos:
            raise CsvParserError(
                "El CSV no contiene productos válidos. "
                f"Errores: {'; '.join(resultado_csv.errores[:5])}"
            )

        productos = resultado_csv.productos
        total = len(productos)

        # Aplicar offset para reanudar desde donde se dejó
        if offset_productos > 0:
            productos = productos[offset_productos:]
            logger.info(
                "Offset aplicado, saltando productos ya procesados",
                extra={
                    "job_id": self._job_id,
                    "offset_productos": offset_productos,
                    "productos_pendientes": len(productos),
                },
            )

        logger.info(
            "CSV parseado, iniciando generación de SEO",
            extra={"job_id": self._job_id, "total_productos": total},
        )

        # ── Paso 2: Inicializar cliente IA ────────────────────────────────────
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
            prompt_file=settings.claude_prompt_file,
        )

        # ── Paso 3: Generar textos SEO en batches ─────────────────────────────
        textos_seo: list[ResultadoSEO] = []
        seo_ok = 0
        seo_fail = 0
        batch_size = settings.claude_batch_size
        procesados = offset_productos

        for batch_inicio in range(0, len(productos), batch_size):
            batch = productos[batch_inicio:batch_inicio + batch_size]
            resultados_batch = generator.generate_seo_texts(batch)

            for resultado in resultados_batch:
                textos_seo.append(resultado)
                procesados += 1

                if resultado.exitoso:
                    seo_ok += 1
                else:
                    seo_fail += 1

            if callback:
                callback(self._job_id, procesados, total, seo_ok)

            logger.debug(
                "Batch de SEO procesado",
                extra={
                    "job_id": self._job_id,
                    "batch_inicio": batch_inicio,
                    "batch_size": len(batch),
                    "progreso": f"{procesados}/{total}",
                },
            )

        # ── Paso 4: Guardar seo.csv ──────────────────────────────────────────
        self._guardar_csv(textos_seo)

        resumen = {
            "total_productos": total,
            "seo_generados": seo_ok,
            "seo_errores": seo_fail,
            "errores_csv": resultado_csv.errores,
        }

        logger.info(
            "Pipeline de SEO completado",
            extra={
                "job_id": self._job_id,
                "total_productos": total,
                "seo_generados": seo_ok,
                "seo_errores": seo_fail,
            },
        )
        return resumen

    def _guardar_csv(self, textos_seo: list[ResultadoSEO]) -> None:
        """
        Serializa los textos SEO a CSV y los guarda en el storage del job.

        Args:
            textos_seo: lista de resultados de generación SEO.
        """
        fieldnames = [
            "codigo",
            "nombre",
            "meta_title",
            "meta_description",
        ]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for r in textos_seo:
            writer.writerow({
                "codigo": r.codigo,
                "nombre": r.nombre,
                "meta_title": r.meta_title,
                "meta_description": r.meta_description,
            })

        try:
            self._storage.save_image(
                self._carpeta_id,
                "seo.csv",
                buffer.getvalue().encode("utf-8-sig"),
            )
            logger.info(
                "seo.csv guardado",
                extra={"job_id": self._job_id, "filas": len(textos_seo)},
            )
        except Exception as exc:
            logger.error(
                "Error al guardar seo.csv",
                exc_info=exc,
                extra={"job_id": self._carpeta_id},
            )
