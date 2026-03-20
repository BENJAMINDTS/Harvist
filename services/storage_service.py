"""
Servicio de almacenamiento de imágenes y archivos generados por el scraper.

Expone una interfaz abstracta (StorageService) con tres implementaciones:
  - LocalStorageService        → sistema de archivos local (desarrollo / staging)
  - S3StorageService           → Amazon S3 (Fase 4.2)
  - AzureBlobStorageService    → Azure Blob Storage (Fase 4.2)

Los endpoints y el pipeline NUNCA escriben rutas de archivo directamente:
siempre pasan por este módulo.

La selección de backend se controla con la variable de entorno STORAGE_BACKEND
("local" | "s3" | "azure"). Los imports de boto3 y azure-storage-blob son
diferidos para que la aplicación arranque aunque esas librerías no estén
instaladas en entornos que no las necesiten.

:author: BenjaminDTS
:version: 2.0.0
"""

import io
import shutil
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

from loguru import logger

from api.core.config import get_settings


# ---------------------------------------------------------------------------
# Interfaz abstracta
# ---------------------------------------------------------------------------


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
        Devuelve la ruta (o URI) del directorio de trabajo para un job.

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
            Path (o URI ficticio) del archivo ZIP generado.

        Raises:
            FileNotFoundError: si el directorio / prefijo del job no existe.
        """

    @abstractmethod
    def get_zip_path(self, job_id: str) -> Path:
        """
        Devuelve la ruta (o URI ficticio) del ZIP de un job.

        Args:
            job_id: identificador del job.

        Returns:
            Path del ZIP existente.

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


# ---------------------------------------------------------------------------
# Implementación local
# ---------------------------------------------------------------------------


class LocalStorageService(StorageService):
    """
    Implementación local del servicio de almacenamiento.

    Guarda las imágenes en el sistema de archivos local bajo OUTPUT_DIR.
    Estructura de directorios::

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
        """
        Devuelve la ruta del directorio de trabajo para un job.

        Args:
            job_id: identificador del job.

        Returns:
            Path del directorio del job bajo el directorio base.
        """
        return self._base / job_id

    def ensure_job_dir(self, job_id: str) -> Path:
        """
        Crea el directorio del job si no existe y lo devuelve.

        Args:
            job_id: identificador del job.

        Returns:
            Path del directorio creado o ya existente.
        """
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
            "Imagen guardada localmente",
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
            "ZIP local creado",
            extra={
                "job_id": job_id,
                "zip_path": str(zip_path),
                "size_bytes": zip_path.stat().st_size,
            },
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
            logger.info("ZIP local eliminado", extra={"job_id": job_id})


# ---------------------------------------------------------------------------
# Implementación Amazon S3
# ---------------------------------------------------------------------------


class S3StorageService(StorageService):
    """
    Implementación del servicio de almacenamiento sobre Amazon S3.

    Las imágenes se suben como objetos individuales bajo la clave
    ``{prefix}/{job_id}/{filename}`` y el ZIP se almacena en
    ``{prefix}/{job_id}.zip``.

    El import de ``boto3`` es diferido (dentro de cada método) para que la
    aplicación pueda arrancar sin la dependencia instalada si el backend
    configurado es distinto de "s3".

    Las credenciales AWS se leen del entorno (variables AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY o perfil de IAM role); nunca se loguean.

    :author: BenjaminDTS
    """

    def __init__(self, bucket: str, prefix: str, region: str) -> None:
        """
        Inicializa el servicio S3.

        Args:
            bucket: nombre del bucket S3 destino.
            prefix: prefijo de clave común para todos los objetos de este servicio.
            region: región AWS donde reside el bucket (p. ej. "eu-west-1").
        """
        self._bucket = bucket
        self._prefix = prefix
        self._region = region

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _image_key(self, job_id: str, filename: str) -> str:
        """Devuelve la clave S3 de una imagen concreta."""
        return f"{self._prefix}/{job_id}/{filename}"

    def _zip_key(self, job_id: str) -> str:
        """Devuelve la clave S3 del ZIP de un job."""
        return f"{self._prefix}/{job_id}.zip"

    def _job_prefix(self, job_id: str) -> str:
        """Devuelve el prefijo S3 de todos los objetos de un job."""
        return f"{self._prefix}/{job_id}/"

    def _get_client(self) -> object:
        """
        Crea y devuelve un cliente boto3 S3.

        El cliente se autentica con las credenciales presentes en el entorno
        (variables de entorno AWS_* o IAM role adjunto a la instancia).

        Returns:
            Cliente boto3 S3 autenticado con las credenciales del entorno.

        Raises:
            ImportError: si boto3 no está instalado.
        """
        try:
            import boto3  # noqa: PLC0415 — import diferido intencionado
        except ImportError as exc:
            raise ImportError(
                "boto3 no está instalado. Ejecuta: pip install boto3"
            ) from exc

        return boto3.client("s3", region_name=self._region)

    def _iter_image_keys(self, job_id: str) -> Iterator[str]:
        """
        Itera sobre las claves S3 de las imágenes de un job usando paginación.

        Args:
            job_id: identificador del job.

        Yields:
            Clave S3 de cada objeto de imagen bajo el prefijo del job.
        """
        s3 = self._get_client()
        paginator = s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=self._bucket, Prefix=self._job_prefix(job_id))
        for page in pages:
            for obj in page.get("Contents", []):
                yield obj["Key"]

    # ------------------------------------------------------------------
    # Implementación de la interfaz
    # ------------------------------------------------------------------

    def get_job_dir(self, job_id: str) -> Path:
        """
        Devuelve la URI ficticia del "directorio" S3 de un job.

        S3 no tiene directorios reales; este Path es solo una referencia
        para compatibilidad con la interfaz abstracta.

        Args:
            job_id: identificador del job.

        Returns:
            Path ficticio con URI s3://{bucket}/{prefix}/{job_id}.
        """
        return Path(f"s3://{self._bucket}/{self._prefix}/{job_id}")

    def ensure_job_dir(self, job_id: str) -> Path:
        """
        Devuelve la URI ficticia del "directorio" S3 (no crea nada en S3).

        S3 no requiere creación explícita de directorios: el prefijo se crea
        implícitamente al subir el primer objeto.

        Args:
            job_id: identificador del job.

        Returns:
            Path ficticio con URI s3://{bucket}/{prefix}/{job_id}.
        """
        logger.debug(
            "ensure_job_dir en S3 — no requiere acción",
            extra={"job_id": job_id, "bucket": self._bucket},
        )
        return self.get_job_dir(job_id)

    def save_image(self, job_id: str, filename: str, data: bytes) -> Path:
        """
        Sube una imagen a S3.

        Args:
            job_id: identificador del job.
            filename: nombre del archivo de imagen (se sanitiza contra path traversal).
            data: contenido binario de la imagen.

        Returns:
            Path ficticio con la URI S3 del objeto creado.

        Raises:
            ImportError: si boto3 no está instalado.
        """
        safe_name = Path(filename).name
        key = self._image_key(job_id, safe_name)
        s3 = self._get_client()
        s3.put_object(Bucket=self._bucket, Key=key, Body=data)
        logger.debug(
            "Imagen subida a S3",
            extra={"job_id": job_id, "key": key, "bytes": len(data)},
        )
        return Path(f"s3://{self._bucket}/{key}")

    def create_zip(self, job_id: str) -> Path:
        """
        Descarga todas las imágenes del job desde S3, las comprime en memoria
        y sube el ZIP resultante como un único objeto S3.

        La compresión en memoria evita escrituras temporales en disco, lo que
        es especialmente relevante en entornos serverless o con disco limitado.

        Args:
            job_id: identificador del job.

        Returns:
            Path ficticio con la URI S3 del ZIP.

        Raises:
            FileNotFoundError: si no existen imágenes para el job en S3.
            ImportError: si boto3 no está instalado.
        """
        s3 = self._get_client()
        keys = list(self._iter_image_keys(job_id))

        if not keys:
            raise FileNotFoundError(
                f"No se encontraron imágenes en S3 para el job '{job_id}'."
            )

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for key in keys:
                response = s3.get_object(Bucket=self._bucket, Key=key)
                image_data: bytes = response["Body"].read()
                arcname = key.split("/")[-1]
                zf.writestr(arcname, image_data)
                logger.debug(
                    "Imagen añadida al ZIP en memoria",
                    extra={"job_id": job_id, "key": key},
                )

        zip_key = self._zip_key(job_id)
        zip_bytes = buffer.getvalue()
        s3.put_object(
            Bucket=self._bucket,
            Key=zip_key,
            Body=zip_bytes,
            ContentType="application/zip",
        )

        zip_uri = Path(f"s3://{self._bucket}/{zip_key}")
        logger.info(
            "ZIP subido a S3",
            extra={
                "job_id": job_id,
                "zip_key": zip_key,
                "size_bytes": len(zip_bytes),
            },
        )
        return zip_uri

    def get_zip_path(self, job_id: str) -> Path:
        """
        Comprueba que el ZIP existe en S3 y devuelve su URI ficticia.

        Usa head_object para verificar existencia sin descargar el objeto.

        Args:
            job_id: identificador del job.

        Returns:
            Path ficticio con la URI S3 del ZIP.

        Raises:
            FileNotFoundError: si el ZIP no existe en el bucket.
            ImportError: si boto3 no está instalado.
        """
        import botocore.exceptions  # noqa: PLC0415 — import diferido intencionado

        s3 = self._get_client()
        zip_key = self._zip_key(job_id)

        try:
            s3.head_object(Bucket=self._bucket, Key=zip_key)
        except botocore.exceptions.ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchKey"):
                raise FileNotFoundError(
                    f"ZIP del job '{job_id}' no encontrado en S3."
                ) from exc
            logger.error(
                "Error inesperado al comprobar existencia del ZIP en S3",
                exc_info=exc,
                extra={"job_id": job_id, "zip_key": zip_key, "error_code": error_code},
            )
            raise

        logger.debug(
            "ZIP encontrado en S3",
            extra={"job_id": job_id, "zip_key": zip_key},
        )
        return Path(f"s3://{self._bucket}/{zip_key}")

    def delete_job_files(self, job_id: str) -> None:
        """
        Elimina en batch todas las imágenes y el ZIP del job en S3.

        La API delete_objects admite hasta 1 000 claves por llamada, por lo
        que las eliminaciones se procesan en lotes de ese tamaño.

        Args:
            job_id: identificador del job.

        Raises:
            FileNotFoundError: si no existen objetos para ese job en S3.
            ImportError: si boto3 no está instalado.
        """
        import botocore.exceptions  # noqa: PLC0415 — import diferido intencionado

        s3 = self._get_client()

        # Recoger claves de imágenes y, opcionalmente, la del ZIP
        keys_to_delete: list[str] = list(self._iter_image_keys(job_id))
        zip_key = self._zip_key(job_id)

        try:
            s3.head_object(Bucket=self._bucket, Key=zip_key)
            keys_to_delete.append(zip_key)
        except botocore.exceptions.ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code not in ("404", "NoSuchKey"):
                # Error inesperado al comprobar el ZIP: se loguea pero no interrumpe
                # la eliminación de las imágenes ya encontradas.
                logger.warning(
                    "No se pudo verificar existencia del ZIP en S3 antes de eliminar",
                    exc_info=exc,
                    extra={"job_id": job_id, "zip_key": zip_key},
                )
            # Si el ZIP no existe (404) es un estado válido: el job pudo no completarse.

        if not keys_to_delete:
            raise FileNotFoundError(
                f"No existen objetos en S3 para el job '{job_id}'."
            )

        # Eliminar en lotes de 1 000 (límite de la API de S3)
        _BATCH_SIZE = 1000
        for i in range(0, len(keys_to_delete), _BATCH_SIZE):
            batch = keys_to_delete[i : i + _BATCH_SIZE]
            objects = [{"Key": k} for k in batch]
            s3.delete_objects(
                Bucket=self._bucket,
                Delete={"Objects": objects, "Quiet": True},
            )
            logger.info(
                "Batch de objetos S3 eliminado",
                extra={"job_id": job_id, "count": len(batch)},
            )

        logger.info(
            "Todos los objetos S3 del job eliminados",
            extra={"job_id": job_id, "total": len(keys_to_delete)},
        )


# ---------------------------------------------------------------------------
# Implementación Azure Blob Storage
# ---------------------------------------------------------------------------


class AzureBlobStorageService(StorageService):
    """
    Implementación del servicio de almacenamiento sobre Azure Blob Storage.

    Los blobs se almacenan bajo la ruta
    ``{prefix}/{job_id}/{filename}`` y el ZIP en ``{prefix}/{job_id}.zip``.

    El import de ``azure.storage.blob`` es diferido para que la aplicación
    pueda arrancar sin la dependencia instalada si el backend configurado es
    distinto de "azure".

    La ``connection_string`` se trata como secreto: se almacena en un atributo
    privado con doble guion bajo (name-mangling) y nunca se loguea ni se
    incluye en mensajes de error.

    :author: BenjaminDTS
    """

    def __init__(
        self, container: str, prefix: str, connection_string: str
    ) -> None:
        """
        Inicializa el servicio Azure Blob Storage.

        Args:
            container: nombre del contenedor de blobs destino.
            prefix: prefijo de nombre común para todos los blobs de este servicio.
            connection_string: cadena de conexión de Azure Storage
                (se trata como secreto y nunca se loguea).
        """
        self._container = container
        self._prefix = prefix
        # Name-mangling intencional: impide acceso accidental desde subclases
        # o código externo y deja claro que es un secreto.
        self.__connection_string = connection_string

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _blob_name(self, job_id: str, filename: str) -> str:
        """Devuelve el nombre de blob de una imagen concreta."""
        return f"{self._prefix}/{job_id}/{filename}"

    def _zip_blob_name(self, job_id: str) -> str:
        """Devuelve el nombre de blob del ZIP de un job."""
        return f"{self._prefix}/{job_id}.zip"

    def _job_blob_prefix(self, job_id: str) -> str:
        """Devuelve el prefijo de blob de todos los objetos de un job."""
        return f"{self._prefix}/{job_id}/"

    def _get_service_client(self) -> object:
        """
        Crea y devuelve un BlobServiceClient de Azure.

        Returns:
            BlobServiceClient autenticado con la connection string.

        Raises:
            ImportError: si azure-storage-blob no está instalado.
        """
        try:
            from azure.storage.blob import BlobServiceClient  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "azure-storage-blob no está instalado. "
                "Ejecuta: pip install azure-storage-blob"
            ) from exc

        return BlobServiceClient.from_connection_string(self.__connection_string)

    def _iter_blob_names(self, job_id: str) -> Iterator[str]:
        """
        Itera sobre los nombres de blob de las imágenes de un job.

        Args:
            job_id: identificador del job.

        Yields:
            Nombre de cada blob de imagen bajo el prefijo del job.
        """
        service_client = self._get_service_client()
        container_client = service_client.get_container_client(self._container)
        prefix = self._job_blob_prefix(job_id)
        for blob in container_client.list_blobs(name_starts_with=prefix):
            yield blob.name

    # ------------------------------------------------------------------
    # Implementación de la interfaz
    # ------------------------------------------------------------------

    def get_job_dir(self, job_id: str) -> Path:
        """
        Devuelve la URI ficticia del "directorio" Azure Blob de un job.

        Azure Blob no tiene directorios reales; este Path es solo una
        referencia para compatibilidad con la interfaz abstracta.

        Args:
            job_id: identificador del job.

        Returns:
            Path ficticio con URI azure://{container}/{prefix}/{job_id}.
        """
        return Path(f"azure://{self._container}/{self._prefix}/{job_id}")

    def ensure_job_dir(self, job_id: str) -> Path:
        """
        Devuelve la URI ficticia del "directorio" Azure Blob (no crea nada).

        Azure Blob no requiere creación explícita de directorios: el prefijo
        se crea implícitamente al subir el primer blob.

        Args:
            job_id: identificador del job.

        Returns:
            Path ficticio con URI azure://{container}/{prefix}/{job_id}.
        """
        logger.debug(
            "ensure_job_dir en Azure Blob — no requiere acción",
            extra={"job_id": job_id, "container": self._container},
        )
        return self.get_job_dir(job_id)

    def save_image(self, job_id: str, filename: str, data: bytes) -> Path:
        """
        Sube una imagen a Azure Blob Storage.

        Args:
            job_id: identificador del job.
            filename: nombre del archivo de imagen (se sanitiza contra path traversal).
            data: contenido binario de la imagen.

        Returns:
            Path ficticio con la URI Azure del blob creado.

        Raises:
            ImportError: si azure-storage-blob no está instalado.
        """
        safe_name = Path(filename).name
        blob_name = self._blob_name(job_id, safe_name)
        service_client = self._get_service_client()
        blob_client = service_client.get_blob_client(
            container=self._container, blob=blob_name
        )
        blob_client.upload_blob(data, overwrite=True)
        logger.debug(
            "Imagen subida a Azure Blob",
            extra={"job_id": job_id, "blob": blob_name, "bytes": len(data)},
        )
        return Path(f"azure://{self._container}/{blob_name}")

    def create_zip(self, job_id: str) -> Path:
        """
        Descarga todas las imágenes del job desde Azure Blob, las comprime
        en memoria y sube el ZIP resultante como un único blob.

        La compresión en memoria evita escrituras temporales en disco.

        Args:
            job_id: identificador del job.

        Returns:
            Path ficticio con la URI Azure del ZIP.

        Raises:
            FileNotFoundError: si no existen imágenes para el job en Azure Blob.
            ImportError: si azure-storage-blob no está instalado.
        """
        service_client = self._get_service_client()
        blob_names = list(self._iter_blob_names(job_id))

        if not blob_names:
            raise FileNotFoundError(
                f"No se encontraron imágenes en Azure Blob para el job '{job_id}'."
            )

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for blob_name in blob_names:
                blob_client = service_client.get_blob_client(
                    container=self._container, blob=blob_name
                )
                download = blob_client.download_blob()
                image_data: bytes = download.readall()
                arcname = blob_name.split("/")[-1]
                zf.writestr(arcname, image_data)
                logger.debug(
                    "Blob añadido al ZIP en memoria",
                    extra={"job_id": job_id, "blob": blob_name},
                )

        zip_blob_name = self._zip_blob_name(job_id)
        zip_bytes = buffer.getvalue()
        zip_client = service_client.get_blob_client(
            container=self._container, blob=zip_blob_name
        )
        zip_client.upload_blob(zip_bytes, overwrite=True)

        zip_uri = Path(f"azure://{self._container}/{zip_blob_name}")
        logger.info(
            "ZIP subido a Azure Blob",
            extra={
                "job_id": job_id,
                "blob": zip_blob_name,
                "size_bytes": len(zip_bytes),
            },
        )
        return zip_uri

    def get_zip_path(self, job_id: str) -> Path:
        """
        Comprueba que el ZIP existe en Azure Blob y devuelve su URI ficticia.

        Usa get_blob_properties para verificar existencia sin descargar el blob.

        Args:
            job_id: identificador del job.

        Returns:
            Path ficticio con la URI Azure del ZIP.

        Raises:
            FileNotFoundError: si el ZIP no existe en el contenedor.
            ImportError: si azure-storage-blob no está instalado.
        """
        from azure.core.exceptions import ResourceNotFoundError  # noqa: PLC0415

        zip_blob_name = self._zip_blob_name(job_id)
        service_client = self._get_service_client()
        blob_client = service_client.get_blob_client(
            container=self._container, blob=zip_blob_name
        )

        try:
            blob_client.get_blob_properties()
        except ResourceNotFoundError as exc:
            raise FileNotFoundError(
                f"ZIP del job '{job_id}' no encontrado en Azure Blob."
            ) from exc

        logger.debug(
            "ZIP encontrado en Azure Blob",
            extra={"job_id": job_id, "blob": zip_blob_name},
        )
        return Path(f"azure://{self._container}/{zip_blob_name}")

    def delete_job_files(self, job_id: str) -> None:
        """
        Elimina todos los blobs de imágenes y el ZIP del job en Azure Blob.

        Args:
            job_id: identificador del job.

        Raises:
            FileNotFoundError: si no existen blobs para ese job.
            ImportError: si azure-storage-blob no está instalado.
        """
        from azure.core.exceptions import ResourceNotFoundError  # noqa: PLC0415

        service_client = self._get_service_client()
        blob_names: list[str] = list(self._iter_blob_names(job_id))

        # Intentar añadir el ZIP a la lista de blobs a eliminar
        zip_blob_name = self._zip_blob_name(job_id)
        try:
            zip_client = service_client.get_blob_client(
                container=self._container, blob=zip_blob_name
            )
            zip_client.get_blob_properties()
            blob_names.append(zip_blob_name)
        except ResourceNotFoundError:
            # El ZIP puede no existir si el job no se completó; es un estado válido.
            logger.debug(
                "ZIP no encontrado al intentar eliminar — se omite",
                extra={"job_id": job_id, "blob": zip_blob_name},
            )

        if not blob_names:
            raise FileNotFoundError(
                f"No existen blobs en Azure Blob para el job '{job_id}'."
            )

        container_client = service_client.get_container_client(self._container)
        for blob_name in blob_names:
            container_client.delete_blob(blob_name, delete_snapshots="include")
            logger.debug(
                "Blob eliminado de Azure Blob",
                extra={"job_id": job_id, "blob": blob_name},
            )

        logger.info(
            "Todos los blobs de Azure del job eliminados",
            extra={"job_id": job_id, "total": len(blob_names)},
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_storage_service() -> StorageService:
    """
    Factory que devuelve la implementación activa del servicio de almacenamiento.

    La selección se realiza en función de la variable de entorno
    ``STORAGE_BACKEND`` (valores: "local" | "s3" | "azure").

    Returns:
        StorageService: implementación activa del servicio.

    Raises:
        ValueError: si el valor de STORAGE_BACKEND no es reconocido.
    """
    settings = get_settings()
    backend: str = settings.storage_backend

    if backend == "s3":
        logger.info(
            "Backend de almacenamiento: Amazon S3",
            extra={"bucket": settings.aws_s3_bucket, "region": settings.aws_region},
        )
        return S3StorageService(
            bucket=settings.aws_s3_bucket,
            prefix=settings.aws_s3_prefix,
            region=settings.aws_region,
        )

    if backend == "azure":
        logger.info(
            "Backend de almacenamiento: Azure Blob Storage",
            extra={"container": settings.azure_container},
        )
        return AzureBlobStorageService(
            container=settings.azure_container,
            prefix=settings.azure_blob_prefix,
            connection_string=settings.azure_connection_string,
        )

    if backend == "local":
        logger.info(
            "Backend de almacenamiento: local",
            extra={"output_dir": settings.output_dir},
        )
        return LocalStorageService(base_dir=settings.output_dir)

    raise ValueError(
        f"STORAGE_BACKEND '{backend}' no reconocido. "
        "Valores válidos: 'local', 's3', 'azure'."
    )
