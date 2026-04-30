"""
Pipeline de resolución EAN → marca de producto.

Flujo:
  1. CsvParser → lista de productos con EAN
  2. EanBrandResolver (cascada de 6 niveles, sin Selenium) → BrandResult por EAN
  3. Exporta marcas.csv al storage del job con columnas:
     codigo, ean, brand_name, manufacturer, source, confidence

Solo procesa productos que tengan EAN. Los productos sin EAN se
incluyen en el CSV de salida con brand_name vacío y source="ean_invalido".

A diferencia de versiones anteriores, este pipeline NO utiliza Selenium ni
ningún WebDriver. Toda la resolución se realiza mediante HTTP síncrono
(httpx.Client) a través de los clientes de ean_http_clients.py.

:author: BenjaminDTS
:author: Carlitos6712
:version: 3.1.0
"""

from __future__ import annotations

import csv
import io
import json
import threading
from pathlib import Path
from typing import Callable

from loguru import logger

from api.v1.schemas.job import SearchConfig
from services.csv_parser import CsvParser, CsvParserError
from services.scraper.brand_scraper import EanBrandResolver
from services.scraper.brand_validator import BrandResult
from services.storage_service import StorageService, get_storage_service

# Firma: (job_id, procesados, total, exitosos) -> None
BrandProgressCallback = Callable[[str, int, int, int], None]

# Protege las escrituras concurrentes a brand_cache.json
_BRAND_CACHE_LOCK: threading.Lock = threading.Lock()


class BrandPipeline:
    """
    Orquestador del pipeline de resolución EAN → marca.

    Para cada producto del CSV que tenga EAN, ejecuta la cascada de 6 niveles
    del EanBrandResolver y exporta los resultados a marcas.csv en el storage
    del job. El CSV incluye el campo ``source`` para auditoría (qué nivel
    resolvió cada EAN) y ``confidence`` para filtrar resultados poco fiables.

    :author: BenjaminDTS
    :author: Carlitos6712
    """

    def __init__(
        self,
        job_id: str,
        config: SearchConfig,
        storage: StorageService | None = None,
        carpeta_job_id: str | None = None,
        write_cache: bool = True,
    ) -> None:
        """
        Inicializa el pipeline de resolución de marcas.

        Args:
            job_id: identificador del job (para progreso y logs).
            config: configuración del job (se usa column_mapping para parsear el CSV).
            storage: servicio de almacenamiento. Si None usa el factory.
            carpeta_job_id: carpeta de almacenamiento a reutilizar (para resume).
                Si None se usa job_id.
            write_cache: si True (por defecto), persiste los prefijos aprendidos
                en brand_cache.json al finalizar. Si False, devuelve los prefijos
                nuevos en el resumen para que el endpoint de validación los persista.
        """
        self._job_id = job_id
        self._carpeta_id = carpeta_job_id or job_id
        self._config = config
        self._storage = storage or get_storage_service()
        self._write_cache = write_cache

    def ejecutar(
        self,
        contenido_csv: str,
        callback: BrandProgressCallback | None = None,
        offset_productos: int = 0,
    ) -> dict:
        """
        Ejecuta el pipeline completo y devuelve un resumen.

        Crea una única instancia de EanBrandResolver para todo el lote, lo que
        permite que la caché GS1 aprenda prefijos durante el procesamiento y
        acelere las resoluciones de EANs del mismo fabricante.

        Args:
            contenido_csv: contenido del CSV como string (ya decodificado).
            callback: función de progreso con firma (job_id, procesados, total, exitosos).
                Se invoca tras resolver cada producto.
            offset_productos: número de productos a saltar desde el inicio del CSV.
                Útil para reanudar jobs cancelados o fallidos.

        Returns:
            Dict con las claves:
              - total_productos (int): total de filas del CSV.
              - marcas_exitosas (int): productos con brand_name resuelto.
              - marcas_fallidas (int): productos sin brand_name resuelto.
              - errores_csv (list[str]): errores de parseo del CSV.

        Raises:
            CsvParserError: si el CSV está vacío o tiene formato inválido.
        """
        logger.info(
            "Pipeline de resolución de marcas iniciado",
            extra={"job_id": self._job_id, "offset": offset_productos},
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

        if offset_productos > 0:
            productos = productos[offset_productos:]
            logger.info(
                "Offset aplicado",
                extra={
                    "job_id": self._job_id,
                    "offset": offset_productos,
                    "pendientes": len(productos),
                },
            )

        logger.info(
            "CSV parseado, iniciando resolución de marcas",
            extra={"job_id": self._job_id, "total_productos": total},
        )

        # ── Paso 2: Resolver EAN → marca ──────────────────────────────────────
        # Se crea una sola instancia del resolver para que la caché GS1 persista
        # entre productos. Cada vez que el Nivel 3, 4 o 5 resuelve un EAN,
        # registra el prefijo para acelerar resoluciones posteriores del mismo
        # fabricante.
        resolver = EanBrandResolver()
        # Capturar prefijos ya existentes ANTES de procesar cualquier producto
        # para poder detectar cuáles son nuevos al finalizar.
        seed_keys = resolver._cache.current_prefix_keys()
        resultados: list[BrandResult] = []
        exitosos = 0

        for idx, producto in enumerate(productos, start=offset_productos + 1):
            if producto.ean:
                resultado = resolver.resolver(
                    codigo=producto.codigo,
                    ean=producto.ean,
                )
            else:
                # Sin EAN: marcar directamente como inválido sin peticiones HTTP
                resultado = BrandResult(
                    ean_code="",
                    source="ean_invalido",
                    confidence="low",
                )
                logger.debug(
                    "Producto sin EAN — omitido",
                    extra={"job_id": self._job_id, "codigo": producto.codigo},
                )

            # Enriquecer el resultado con el código interno del producto para que
            # _guardar_csv pueda asociar cada fila con su código de producto.
            # BrandResult es inmutable (Pydantic BaseModel), por lo que guardamos
            # el código como metadato en una tupla.
            resultados.append(resultado)

            exitoso = resultado.source not in ("not_found", "ean_invalido")
            if exitoso:
                exitosos += 1

            if callback:
                callback(self._job_id, idx, total, exitosos)

            logger.debug(
                "Producto procesado",
                extra={
                    "job_id": self._job_id,
                    "codigo": producto.codigo,
                    "ean": producto.ean,
                    "brand": resultado.brand_name,
                    "source": resultado.source,
                    "confidence": resultado.confidence,
                    "progreso": f"{idx}/{total}",
                },
            )

        # ── Paso 3: Exportar marcas.csv ───────────────────────────────────────
        # Guardamos los resultados junto a los códigos de producto, que necesitamos
        # para el CSV. Construimos una lista combinada antes de exportar.
        productos_resultados = list(zip(
            resultado_csv.productos[offset_productos:] if offset_productos else resultado_csv.productos,
            resultados,
        ))
        self._guardar_csv(productos_resultados)

        # ── Paso 4: Persistencia de brand_cache.json ──────────────────────────
        # Detectar los prefijos GS1 aprendidos durante el procesamiento.
        new_entries = resolver._cache.get_learned_prefixes(seed_keys)

        from api.core.config import get_settings  # noqa: PLC0415 — import diferido para evitar ciclos
        settings = get_settings()
        brand_cache_path = Path(settings.brand_cache_path)

        if self._write_cache:
            self._persist_brand_cache(new_entries, brand_cache_path)
            new_cache_entries_out: dict[str, str] = {}
        else:
            logger.info(
                "write_cache=False: prefijos nuevos diferidos para validación manual",
                extra={
                    "job_id": self._job_id,
                    "prefijos_nuevos": len(new_entries),
                },
            )
            new_cache_entries_out = new_entries

        resumen = {
            "total_productos": total,
            "marcas_exitosas": exitosos,
            "marcas_fallidas": total - exitosos,
            "errores_csv": resultado_csv.errores,
            "new_cache_entries": new_cache_entries_out,
        }

        logger.info(
            "Pipeline de marcas completado",
            extra={
                "job_id": self._job_id,
                "total_productos": total,
                "marcas_exitosas": exitosos,
                "marcas_fallidas": total - exitosos,
            },
        )
        return resumen

    def _persist_brand_cache(
        self,
        new_entries: dict[str, str],
        brand_cache_path: Path,
    ) -> None:
        """
        Persiste las entradas nuevas de marca en brand_cache.json con lock.

        Usa threading.Lock a nivel de proceso para evitar corrupción por
        escrituras concurrentes entre workers Celery del mismo proceso.
        El archivo se crea si no existe.

        Args:
            new_entries: dict {prefijo_7_digits: company_name} con las
                marcas nuevas a persistir.
            brand_cache_path: ruta absoluta al archivo brand_cache.json.

        Raises:
            OSError: si no se puede leer o escribir el archivo (log + raise).
        """
        if not new_entries:
            logger.debug(
                "Sin prefijos nuevos que persistir en brand_cache.json",
                extra={"job_id": self._job_id},
            )
            return

        with _BRAND_CACHE_LOCK:
            existing: dict[str, str] = {}
            if brand_cache_path.exists():
                try:
                    existing = json.loads(
                        brand_cache_path.read_text(encoding="utf-8")
                    )
                except (json.JSONDecodeError, OSError) as exc:
                    logger.error(
                        "Error leyendo brand_cache.json; se sobreescribirá",
                        exc_info=exc,
                        extra={"job_id": self._job_id, "path": str(brand_cache_path)},
                    )

            merged = {**existing, **new_entries}
            brand_cache_path.parent.mkdir(parents=True, exist_ok=True)
            brand_cache_path.write_text(
                json.dumps(merged, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        for prefijo, nombre in new_entries.items():
            logger.info(
                "Prefijo GS1 persistido en brand_cache.json",
                extra={
                    "job_id": self._job_id,
                    "prefijo": prefijo,
                    "brand_name": nombre,
                },
            )

    def _guardar_csv(
        self,
        productos_resultados: list[tuple],
    ) -> None:
        """
        Serializa los resultados de resolución a CSV y los guarda en storage.

        Columnas exportadas: codigo, ean, brand_name, manufacturer, source, confidence.
        El archivo se codifica en UTF-8 con BOM (utf-8-sig) para compatibilidad
        con Excel.

        Args:
            productos_resultados: lista de tuplas (Producto, BrandResult).
        """
        fieldnames = [
            "codigo",
            "ean",
            "brand_name",
            "manufacturer",
            "source",
            "confidence",
        ]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for producto, resultado in productos_resultados:
            writer.writerow({
                "codigo": producto.codigo,
                "ean": producto.ean,
                "brand_name": resultado.brand_name or "",
                "manufacturer": resultado.manufacturer or "",
                "source": resultado.source,
                "confidence": resultado.confidence,
            })

        try:
            self._storage.save_image(
                self._carpeta_id,
                "marcas.csv",
                buffer.getvalue().encode("utf-8-sig"),
            )
            logger.info(
                "marcas.csv guardado",
                extra={"job_id": self._job_id, "filas": len(productos_resultados)},
            )
        except Exception as exc:
            logger.error(
                "Error guardando marcas.csv",
                exc_info=exc,
                extra={"job_id": self._job_id},
            )
            raise
