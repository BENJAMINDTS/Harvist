"""
Servicio de almacenamiento de imágenes y archivos generados por el scraper.

Expone una interfaz abstracta (StorageService) y una implementación local
(LocalStorageService). Para añadir almacenamiento en cloud (S3, Azure Blob),
crear una nueva clase que herede StorageService y registrarla en get_storage_service().

Los endpoints y el pipeline NUNCA escriben rutas de archivo directamente:
siempre pasan por este módulo.

:author: BenjaminDTS
:version: 1.0.0
"""

import shutil
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path

from loguru import logger

from api.core.config import get_settings


class StorageService(ABC):
    """
    Interfaz abstracta del servicio de almacenamiento.

    Define el contrato que deben cumplir todas las implementaciones
    (local, S3, Azure Blob, etc.) para que los endpoints no dependan
    de la implementación concreta.

    :author: BenjaminDTS
    """

    @abstractmethod
    def get_job_dir(self, job_id: str) -> Path:
        """
        Devuelve la ruta del directorio de trabajo para un job.

        Args:
            job_id: identificador del job.

        Returns:
            Path del directorio (puede no existir aún).
        """

    @abstractmethod
    def ensure_job_dir(self, job_id: str) -> Path:
        """
        Crea el directorio del job si no existe y lo devuelve.

        Args:
            job_id: identificador del job.

        Returns:
            Path del directorio creado o ya existente.
        """

    @abstractmethod
    def save_image(self, job_id: str, filename: str, data: bytes) -> Path:
        """
        Guarda una imagen en el directorio del job.

        Args:
            job_id: identificador del job.
            filename: nombre del archivo de imagen.
            data: contenido binario de la imagen.

        Returns:
            Path donde se guardó la imagen.
        """

    @abstractmethod
    def create_zip(self, job_id: str) -> Path:
        """
        Comprime todas las imágenes del job en un ZIP y lo devuelve.

        Args:
            job_id: identificador del job.

        Returns:
            Path del archivo ZIP generado.

        Raises:
            FileNotFoundError: si el directorio del job no existe.
        """

    @abstractmethod
    def get_zip_path(self, job_id: str) -> Path:
        """
        Devuelve la ruta del ZIP de un job.

        Args:
            job_id: identificador del job.

        Returns:
            Path del ZIP.

        Raises:
            FileNotFoundError: si el ZIP no existe.
        """

    @abstractmethod
    def delete_job_files(self, job_id: str) -> None:
        """
        Elimina todos los archivos (imágenes + ZIP) de un job.

        Args:
            job_id: identificador del job.

        Raises:
            FileNotFoundError: si no existen archivos para ese job.
        """


class LocalStorageService(StorageService):
    """
    Implementación local del servicio de almacenamiento.

    Guarda las imágenes en el sistema de archivos local bajo OUTPUT_DIR.
    Estructura de directorios:
      {output_dir}/
        {job_id}/
          producto_001_1.jpg
          producto_001_2.jpg
          ...
        {job_id}.zip

    :author: BenjaminDTS
    """

    def __init__(self, base_dir: str) -> None:
        """
        Inicializa el servicio con el directorio base de salida.

        Args:
            base_dir: ruta al directorio raíz de almacenamiento (OUTPUT_DIR).
        """
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def get_job_dir(self, job_id: str) -> Path:
        """Devuelve la ruta del directorio de trabajo para un job."""
        return self._base / job_id

    def ensure_job_dir(self, job_id: str) -> Path:
        """Crea el directorio del job si no existe y lo devuelve."""
        job_dir = self.get_job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    def save_image(self, job_id: str, filename: str, data: bytes) -> Path:
        """
        Guarda una imagen en el directorio del job.

        Args:
            job_id: identificador del job.
            filename: nombre de archivo (se sanitiza para evitar path traversal).
            data: bytes de la imagen.

        Returns:
            Path donde se guardó la imagen.
        """
        # Sanitizar el nombre de archivo para prevenir path traversal
        safe_name = Path(filename).name
        job_dir = self.ensure_job_dir(job_id)
        dest = job_dir / safe_name
        dest.write_bytes(data)
        logger.debug(
            "Imagen guardada",
            extra={"job_id": job_id, "filename": safe_name, "bytes": len(data)},
        )
        return dest

    def create_zip(self, job_id: str) -> Path:
        """
        Comprime el directorio del job en un ZIP.

        Args:
            job_id: identificador del job.

        Returns:
            Path del ZIP generado.

        Raises:
            FileNotFoundError: si el directorio del job no existe.
        """
        job_dir = self.get_job_dir(job_id)
        if not job_dir.exists():
            raise FileNotFoundError(f"Directorio del job '{job_id}' no encontrado.")

        zip_path = self._base / f"{job_id}.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for img_file in sorted(job_dir.iterdir()):
                if img_file.is_file():
                    zf.write(img_file, arcname=img_file.name)

        logger.info(
            "ZIP creado",
            extra={"job_id": job_id, "zip_path": str(zip_path), "size_bytes": zip_path.stat().st_size},
        )
        return zip_path

    def get_zip_path(self, job_id: str) -> Path:
        """
        Devuelve la ruta del ZIP de un job.

        Args:
            job_id: identificador del job.

        Returns:
            Path del ZIP existente.

        Raises:
            FileNotFoundError: si el ZIP no existe aún.
        """
        zip_path = self._base / f"{job_id}.zip"
        if not zip_path.exists():
            raise FileNotFoundError(f"ZIP del job '{job_id}' no encontrado.")
        return zip_path

    def delete_job_files(self, job_id: str) -> None:
        """
        Elimina el directorio de imágenes y el ZIP del job.

        Args:
            job_id: identificador del job.

        Raises:
            FileNotFoundError: si no existen archivos para ese job.
        """
        job_dir = self.get_job_dir(job_id)
        zip_path = self._base / f"{job_id}.zip"

        if not job_dir.exists() and not zip_path.exists():
            raise FileNotFoundError(f"No existen archivos para el job '{job_id}'.")

        if job_dir.exists():
            shutil.rmtree(job_dir)
            logger.info("Directorio de imágenes eliminado", extra={"job_id": job_id})

        if zip_path.exists():
            zip_path.unlink()
            logger.info("ZIP eliminado", extra={"job_id": job_id})


def get_storage_service() -> StorageService:
    """
    Factory que devuelve la implementación activa del servicio de almacenamiento.

    Actualmente devuelve LocalStorageService. Cuando se implemente la Fase 4.2
    (almacenamiento en cloud), añadir aquí la lógica de selección basada en
    la variable de entorno STORAGE_BACKEND.

    Returns:
        StorageService: implementación activa del servicio.
    """
    settings = get_settings()
    return LocalStorageService(base_dir=settings.output_dir)
