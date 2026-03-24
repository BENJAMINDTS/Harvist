"""
Pipeline de scraping de información de marca.

Flujo:
  1. CsvParser → lista de productos → extrae marcas únicas
  2. BrandScraper (Selenium/Bing) → logo URL + website + descripción
  3. Descarga del logo como imagen vía HTTP
  4. Exporta marcas.json al storage del job

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

import io
import json
from typing import Callable

import requests as _requests
from loguru import logger
from PIL import Image

from api.core.config import get_settings
from services.csv_parser import CsvParser, CsvParserError
from services.scraper.brand_scraper import BrandScraper, FichaMarca
from services.storage_service import StorageService, get_storage_service

BrandProgressCallback = Callable[[str, int, int, int], None]
# Firma: (job_id, procesadas, total, exitosas) -> None

_LOGO_DOWNLOAD_HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "image/*,*/*;q=0.8",
}


class BrandPipeline:
    """
    Orquestador del proceso de scraping de marcas para un job.

    :author: BenjaminDTS
    """

    def __init__(
        self,
        job_id: str,
        config,
        storage: StorageService | None = None,
        carpeta_job_id: str | None = None,
    ) -> None:
        """
        Inicializa el pipeline de marcas.

        Args:
            job_id: identificador del job (para progreso y logs).
            config: configuración del job (se usa column_mapping.columna_marca).
            storage: servicio de almacenamiento. Si None usa el factory.
            carpeta_job_id: carpeta de almacenamiento a reutilizar (para resume).
        """
        self._job_id = job_id
        self._carpeta_id = carpeta_job_id or job_id
        self._config = config
        self._storage = storage or get_storage_service()

    def ejecutar(
        self,
        contenido_csv: str,
        callback: BrandProgressCallback | None = None,
        offset_productos: int = 0,
    ) -> dict:
        """
        Ejecuta el pipeline completo y devuelve un resumen.

        Args:
            contenido_csv: contenido del CSV como string.
            callback: función de progreso (job_id, procesadas, total, exitosas).
            offset_productos: número de marcas a saltar (para resume).

        Returns:
            Dict con total_marcas, marcas_exitosas, marcas_fallidas, errores_csv.

        Raises:
            CsvParserError: si el CSV es inválido.
        """
        logger.info("Pipeline de marcas iniciado", extra={"job_id": self._job_id})

        # ── Paso 1: Parsear CSV y extraer marcas únicas ───────────────────────
        parser = CsvParser(self._config)
        resultado_csv = parser.parsear(contenido_csv)

        if not resultado_csv.productos:
            raise CsvParserError(
                "El CSV no contiene productos válidos. "
                f"Errores: {'; '.join(resultado_csv.errores[:5])}"
            )

        # Deduplica manteniendo orden de aparición
        seen: set[str] = set()
        marcas: list[str] = []
        for p in resultado_csv.productos:
            m = (p.marca or "").strip()
            if m and m not in seen:
                seen.add(m)
                marcas.append(m)

        total = len(marcas)

        if offset_productos > 0:
            marcas = marcas[offset_productos:]
            logger.info(
                "Offset aplicado",
                extra={
                    "job_id": self._job_id,
                    "offset": offset_productos,
                    "pendientes": len(marcas),
                },
            )

        logger.info(
            "Marcas únicas encontradas",
            extra={"job_id": self._job_id, "total": total},
        )

        # ── Paso 2: Scrape + descarga logo para cada marca ────────────────────
        fichas: list[dict] = []
        exitosas = 0

        # Crear driver una sola vez para toda la sesión
        from services.scraper.producer import _crear_driver  # noqa: PLC0415
        settings = get_settings()
        driver = _crear_driver(settings)

        try:
            scraper = BrandScraper()
            for idx, marca in enumerate(marcas, start=offset_productos + 1):
                ficha = scraper.scrape(marca, driver)

                # Descargar logo si se encontró URL
                logo_archivo = ""
                if ficha.logo_url:
                    logo_archivo = self._descargar_logo(ficha)

                fichas.append(
                    {
                        "marca": ficha.marca,
                        "website": ficha.website,
                        "descripcion": ficha.descripcion,
                        "logo_archivo": logo_archivo,
                        "exitoso": ficha.exitoso,
                        "error": ficha.error,
                    }
                )

                if ficha.exitoso:
                    exitosas += 1

                if callback:
                    callback(self._job_id, idx, total, exitosas)

                logger.debug(
                    "Marca procesada",
                    extra={
                        "job_id": self._job_id,
                        "marca": marca,
                        "idx": f"{idx}/{total}",
                    },
                )
        finally:
            try:
                driver.quit()
            except Exception as exc:
                logger.warning(
                    "Error al cerrar el WebDriver del pipeline de marcas",
                    exc_info=exc,
                    extra={"job_id": self._job_id},
                )

        # ── Paso 3: Exportar marcas.json ──────────────────────────────────────
        self._guardar_json(fichas)

        resumen = {
            "total_marcas": total,
            "marcas_exitosas": exitosas,
            "marcas_fallidas": total - exitosas,
            "errores_csv": resultado_csv.errores,
        }

        logger.info(
            "Pipeline de marcas completado",
            extra={
                "job_id": self._job_id,
                "total_marcas": resumen["total_marcas"],
                "marcas_exitosas": resumen["marcas_exitosas"],
                "marcas_fallidas": resumen["marcas_fallidas"],
            },
        )
        return resumen

    def _descargar_logo(self, ficha: FichaMarca) -> str:
        """
        Descarga el logo de la marca y lo guarda en storage.

        Args:
            ficha: ficha de marca con logo_url.

        Returns:
            Nombre del archivo guardado, o cadena vacía si falla.
        """
        settings = get_settings()

        try:
            resp = _requests.get(
                ficha.logo_url,
                headers=_LOGO_DOWNLOAD_HEADERS,
                timeout=settings.download_timeout,
                stream=False,
            )
            resp.raise_for_status()

            img = Image.open(io.BytesIO(resp.content))
            img.verify()
            img = Image.open(io.BytesIO(resp.content))
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85, optimize=True)

            nombre_base = (
                "".join(c if c.isalnum() or c in "-_" else "_" for c in ficha.marca)
                .strip("_")
                or "marca"
            )
            filename = f"{nombre_base}_logo.jpg"
            self._storage.save_image(self._carpeta_id, filename, buf.getvalue())
            return filename

        except Exception as exc:
            logger.warning(
                "Error descargando logo",
                exc_info=exc,
                extra={"marca": ficha.marca},
            )
            return ""

    def _guardar_json(self, fichas: list[dict]) -> None:
        """
        Serializa las fichas de marca a JSON y las guarda en storage.

        Args:
            fichas: lista de dicts con datos de cada marca.
        """
        try:
            contenido = json.dumps(fichas, ensure_ascii=False, indent=2).encode("utf-8")
            self._storage.save_image(self._carpeta_id, "marcas.json", contenido)
            logger.info(
                "marcas.json guardado",
                extra={"job_id": self._job_id, "marcas": len(fichas)},
            )
        except Exception as exc:
            logger.error(
                "Error guardando marcas.json",
                exc_info=exc,
                extra={"job_id": self._job_id},
            )
