"""
Índice SQLite de imágenes descargadas para deduplicación entre jobs.

Permite reutilizar imágenes de jobs anteriores sin volver a ejecutar
Selenium si el mismo EAN o código ya fue procesado.

Estructura de la tabla image_index:
  ean        TEXT          — EAN del producto (puede ser NULL)
  codigo     TEXT NOT NULL — Código interno del producto
  path       TEXT NOT NULL — Ruta absoluta al archivo de imagen en disco
  job_id     TEXT NOT NULL — Job que generó la imagen original
  width      INTEGER       — Ancho en píxeles (de la validación Pillow)
  height     INTEGER       — Alto en píxeles
  created_at TEXT          — ISO 8601

Clave de lookup: EAN si está disponible, codigo como fallback.

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

# DDL de la tabla — WAL mode se activa en __init__
_DDL = """
CREATE TABLE IF NOT EXISTS image_index (
    ean        TEXT,
    codigo     TEXT NOT NULL,
    path       TEXT NOT NULL,
    job_id     TEXT NOT NULL,
    width      INTEGER,
    height     INTEGER,
    created_at TEXT NOT NULL,
    PRIMARY KEY (ean, codigo)
)
"""


class ImageCacheService:
    """
    Gestiona el índice SQLite de imágenes para deduplicación entre jobs.

    Instanciar una vez por proceso; la conexión se abre y cierra por operación
    para ser seguro con el acceso concurrente (WAL mode).

    :author: BenjaminDTS
    """

    def __init__(self, db_path: Path) -> None:
        """
        Inicializa el servicio y crea la tabla si no existe.

        Activa WAL mode para permitir lecturas concurrentes sin bloquear
        escrituras (múltiples workers de Celery pueden leer a la vez).

        Args:
            db_path: ruta al fichero SQLite. El directorio padre debe existir.
        """
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(_DDL)
        logger.debug("ImageCacheService inicializado", extra={"db_path": str(db_path)})

    def _connect(self) -> sqlite3.Connection:
        """Abre una conexión con row_factory para acceso por nombre de columna."""
        conn = sqlite3.connect(str(self._db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def lookup(self, ean: str | None, codigo: str) -> Path | None:
        """
        Busca una imagen en el índice.

        Prioriza búsqueda por EAN si está disponible y no es vacío.
        Si encuentra la entrada pero el archivo ya no existe en disco,
        elimina la entrada (imagen huérfana) y devuelve None.

        Args:
            ean:    EAN del producto (None o cadena vacía si no disponible).
            codigo: código interno del producto.

        Returns:
            Path a la imagen si existe en disco, None si no hay caché válida.
        """
        ean_key = ean.strip() if ean and ean.strip() else None

        with self._connect() as conn:
            if ean_key:
                row = conn.execute(
                    "SELECT path, codigo FROM image_index WHERE ean = ?",
                    (ean_key,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT path FROM image_index WHERE codigo = ? AND (ean IS NULL OR ean = '')",
                    (codigo,),
                ).fetchone()

            if row is None:
                return None

            cached_path = Path(row["path"])
            if not cached_path.exists():
                # Imagen huérfana — eliminar del índice
                self.invalidate(ean_key, codigo)
                logger.debug(
                    "Entrada huérfana eliminada del caché",
                    extra={"codigo": codigo, "path": str(cached_path)},
                )
                return None

            return cached_path

    def register(
        self,
        ean: str | None,
        codigo: str,
        path: Path,
        job_id: str,
        width: int,
        height: int,
    ) -> None:
        """
        Registra una imagen recién descargada en el índice.

        Si ya existe una entrada para ese EAN/codigo la sobreescribe
        (INSERT OR REPLACE) — la nueva imagen sustituye a la anterior.

        Args:
            ean:    EAN del producto (None o vacío si no disponible).
            codigo: código interno del producto.
            path:   ruta absoluta al archivo guardado.
            job_id: ID del job que generó la imagen.
            width:  ancho validado por Pillow.
            height: alto validado por Pillow.
        """
        ean_key = ean.strip() if ean and ean.strip() else None
        now = datetime.now(tz=UTC).isoformat()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO image_index
                    (ean, codigo, path, job_id, width, height, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (ean_key, codigo, str(path.resolve()), job_id, width, height, now),
            )

        logger.debug(
            "Imagen registrada en caché",
            extra={"codigo": codigo, "ean": ean_key, "job_id": job_id},
        )

    def invalidate(self, ean: str | None, codigo: str) -> None:
        """
        Elimina la entrada del índice para un producto.

        No elimina el archivo en disco; solo borra el registro.

        Args:
            ean:    EAN del producto (None o vacío si no disponible).
            codigo: código interno del producto.
        """
        ean_key = ean.strip() if ean and ean.strip() else None

        with self._connect() as conn:
            if ean_key:
                conn.execute(
                    "DELETE FROM image_index WHERE ean = ? OR codigo = ?",
                    (ean_key, codigo),
                )
            else:
                conn.execute(
                    "DELETE FROM image_index WHERE codigo = ? AND (ean IS NULL OR ean = '')",
                    (codigo,),
                )

    def stats(self) -> dict:
        """
        Devuelve estadísticas del índice.

        Returns:
            Dict con total_entries, unique_eans, oldest_entry, newest_entry.
        """
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM image_index").fetchone()[0]
            unique_eans = conn.execute(
                "SELECT COUNT(DISTINCT ean) FROM image_index WHERE ean IS NOT NULL AND ean != ''"
            ).fetchone()[0]
            oldest = conn.execute(
                "SELECT MIN(created_at) FROM image_index"
            ).fetchone()[0]
            newest = conn.execute(
                "SELECT MAX(created_at) FROM image_index"
            ).fetchone()[0]

        return {
            "total_entries": total,
            "unique_eans": unique_eans,
            "oldest_entry": oldest,
            "newest_entry": newest,
        }

    def cleanup_orphans(self) -> int:
        """
        Elimina entradas cuyo archivo en disco ya no existe.

        Llamar periódicamente (Celery beat semanal) para mantener
        el índice limpio sin entradas que apuntan a archivos borrados.

        Returns:
            Número de entradas eliminadas.
        """
        with self._connect() as conn:
            rows = conn.execute("SELECT ean, codigo, path FROM image_index").fetchall()

        orphan_keys: list[tuple[str | None, str]] = []
        for row in rows:
            if not Path(row["path"]).exists():
                orphan_keys.append((row["ean"], row["codigo"]))

        for ean_key, codigo in orphan_keys:
            self.invalidate(ean_key, codigo)

        if orphan_keys:
            logger.info(
                "Huérfanos eliminados del caché de imágenes",
                extra={"count": len(orphan_keys)},
            )

        return len(orphan_keys)
