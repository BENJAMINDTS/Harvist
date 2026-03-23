"""
Pipeline de generación de descripciones de producto con Claude API.

Módulo independiente del pipeline de scraping de imágenes. Solo requiere
el CSV de productos y acceso a la API de Claude; no usa Selenium ni descarga imágenes.

Flujo:
  1. CsvParser → lista de productos validados
  2. DescriptionGenerator.generar_batch() → descripciones en lotes
  3. Exportar descripciones.csv al storage del job
  4. Comprimir en ZIP

:author: Carlitos6712
:version: 2.0.0
"""

from __future__ import annotations

import csv
import io
from typing import Callable

from loguru import logger

from api.core.config import get_settings
from api.v1.schemas.job import SearchConfig
from services.ai.claude_client import ClaudeClient
from services.ai.description_generator import DescriptionGenerator, ResultadoDescripcion
from services.csv_parser import CsvParser, CsvParserError
from services.storage_service import StorageService, get_storage_service

# Firma: (job_id, procesados, total, descripciones_ok) -> None
DescripcionProgressCallback = Callable[[str, int, int, int], None]


class DescripcionPipeline:
    """
    Orquestador del proceso de generación de descripciones con IA para un job.

    Independiente del ScrapingPipeline: no realiza scraping ni descarga imágenes.
    Procesa los productos en batches para reducir llamadas a la API de Claude.
    El resultado es un ZIP con un único archivo ``descripciones.csv``.

    :author: Carlitos6712
    """

    def __init__(
        self,
        job_id: str,
        config: SearchConfig,
        storage: StorageService | None = None,
    ) -> None:
        """
        Inicializa el pipeline de descripciones para un job concreto.

        Args:
            job_id: identificador del job.
            config: configuración del job (solo se usan column_mapping y modo).
            storage: servicio de almacenamiento. Si None, usa el factory por defecto.
        """
        self._job_id = job_id
        self._config = config
        self._storage = storage or get_storage_service()

    def ejecutar(
        self,
        contenido_csv: str,
        callback: DescripcionProgressCallback | None = None,
    ) -> dict:
        """
        Ejecuta el pipeline completo y devuelve un resumen del resultado.

        Args:
            contenido_csv: contenido del CSV como string (ya decodificado).
            callback: función de progreso invocada tras procesar cada batch.
                      Firma: (job_id, procesados, total, descripciones_ok)

        Returns:
            Diccionario con: total_productos, descripciones_generadas,
            descripciones_fallidas, errores_csv, ruta_zip.

        Raises:
            CsvParserError: si el CSV es inválido estructuralmente.
        """
        logger.info(
            "Pipeline de descripciones iniciado",
            extra={"job_id": self._job_id},
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

        logger.info(
            "CSV parseado, iniciando generación de descripciones",
            extra={"job_id": self._job_id, "total_productos": total},
        )

        # ── Paso 2: Inicializar cliente IA ────────────────────────────────────
        settings = get_settings()
        if settings.ai_provider == "groq":
            # La API key del usuario tiene prioridad sobre la del .env
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
        generator = DescriptionGenerator(
            client=claude_client,
            store_type=settings.claude_store_type,
            prompt_file=settings.claude_prompt_file,
            prompt_inline=self._config.prompt_personalizado,
        )

        # ── Paso 3: Generar descripciones en batches ──────────────────────────
        descripciones: list[ResultadoDescripcion] = []
        descripciones_ok = 0
        descripciones_fail = 0
        batch_size = settings.claude_batch_size
        procesados = 0

        for batch_inicio in range(0, total, batch_size):
            batch = productos[batch_inicio:batch_inicio + batch_size]
            resultados_batch = generator.generar_batch(batch)

            for resultado in resultados_batch:
                descripciones.append(resultado)
                procesados += 1

                if resultado.exitoso:
                    descripciones_ok += 1
                else:
                    descripciones_fail += 1

            if callback:
                callback(self._job_id, procesados, total, descripciones_ok)

            logger.debug(
                "Batch de descripciones procesado",
                extra={
                    "job_id": self._job_id,
                    "batch_inicio": batch_inicio,
                    "batch_size": len(batch),
                    "progreso": f"{procesados}/{total}",
                },
            )

        # ── Paso 4: Guardar descripciones.csv ────────────────────────────────
        self._guardar_csv(descripciones)

        # ── Paso 5: Comprimir en ZIP ──────────────────────────────────────────
        ruta_zip = ""
        try:
            zip_path = self._storage.create_zip(self._job_id)
            ruta_zip = str(zip_path)
        except Exception as exc:
            logger.error(
                "Error al crear el ZIP de descripciones",
                exc_info=exc,
                extra={"job_id": self._job_id},
            )

        resumen = {
            "total_productos": total,
            "descripciones_generadas": descripciones_ok,
            "descripciones_fallidas": descripciones_fail,
            "errores_csv": resultado_csv.errores,
            "ruta_zip": ruta_zip,
        }

        logger.info(
            "Pipeline de descripciones completado",
            extra={
                "job_id": self._job_id,
                "total_productos": total,
                "descripciones_generadas": descripciones_ok,
                "descripciones_fallidas": descripciones_fail,
            },
        )
        return resumen

    def _guardar_csv(self, descripciones: list[ResultadoDescripcion]) -> None:
        """
        Serializa las descripciones a CSV y las guarda en el storage del job.

        Los campos de keywords se serializan como listas separadas por ' | '.

        Args:
            descripciones: lista de resultados del generador de descripciones.
        """
        fieldnames = [
            "codigo",
            "nombre",
            "marca",
            "categoria",
            "corta",
            "larga",
            "keywords_principales",
            "keywords_secundarias",
            "meta_description",
            "exitoso",
            "error",
        ]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for r in descripciones:
            writer.writerow({
                "codigo": r.codigo,
                "nombre": r.nombre,
                "marca": r.marca,
                "categoria": r.categoria,
                "corta": r.corta,
                "larga": r.larga,
                "keywords_principales": " | ".join(r.keywords_principales),
                "keywords_secundarias": " | ".join(r.keywords_secundarias),
                "meta_description": r.meta_description,
                "exitoso": r.exitoso,
                "error": r.error,
            })

        try:
            self._storage.save_image(
                self._job_id,
                "descripciones.csv",
                buffer.getvalue().encode("utf-8"),
            )
            logger.info(
                "descripciones.csv guardado",
                extra={"job_id": self._job_id, "filas": len(descripciones)},
            )
        except Exception as exc:
            logger.error(
                "Error al guardar descripciones.csv",
                exc_info=exc,
                extra={"job_id": self._job_id},
            )
