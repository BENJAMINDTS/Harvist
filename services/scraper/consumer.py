"""
Consumidor del pipeline de scraping: descarga, validación y redimensionado de imágenes.

Usa un ThreadPoolExecutor para descargar imágenes en paralelo.
Cada imagen se valida con Pillow antes de guardarse: tamaño mínimo,
formato soportado y que no sea una imagen de error/placeholder.

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

import io
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable

import requests
from loguru import logger
from PIL import Image, UnidentifiedImageError

from api.core.config import get_settings
from services.csv_parser import Producto
from services.storage_service import StorageService

# Formatos de imagen aceptados (en formato Pillow)
_FORMATOS_ACEPTADOS = {"JPEG", "PNG", "WEBP", "GIF", "BMP"}

# Cabeceras HTTP para simular un navegador real y evitar bloqueos
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": "https://www.bing.com/",
}


@dataclass
class ResultadoDescarga:
    """
    Resultado de intentar descargar una imagen concreta.

    :author: BenjaminDTS
    """

    url: str
    exitoso: bool
    ruta_guardada: str = ""
    error: str = ""


def descargar_imagenes_producto(
    job_id: str,
    producto: Producto,
    urls: list[str],
    storage: StorageService,
    callback_imagen: Callable[[bool], None] | None = None,
) -> list[ResultadoDescarga]:
    """
    Descarga, valida y guarda las imágenes de un producto usando un thread pool.

    Intenta descargar todas las URLs recibidas en paralelo hasta obtener
    el número de imágenes válidas configurado en Settings. Las imágenes
    que no superen la validación de Pillow se descartan silenciosamente.

    Args:
        job_id: identificador del job (para nombrar los archivos).
        producto: producto con su código y datos para nombrar los archivos.
        urls: lista de URLs a intentar descargar.
        storage: servicio de almacenamiento donde guardar las imágenes.
        callback_imagen: función opcional invocada con (exitoso: bool)
                         tras procesar cada imagen, para actualizar contadores.

    Returns:
        Lista de ResultadoDescarga con el resultado de cada URL intentada.
    """
    settings = get_settings()
    resultados: list[ResultadoDescarga] = []
    imagenes_validas = 0

    with ThreadPoolExecutor(max_workers=settings.download_workers) as executor:
        futuros: dict[Future, str] = {
            executor.submit(
                _descargar_y_validar,
                url,
                settings.download_timeout,
                settings.image_min_width,
                settings.image_min_height,
                settings.image_resize_width,
                settings.image_resize_height,
            ): url
            for url in urls
        }

        for futuro in as_completed(futuros):
            url = futuros[futuro]

            if imagenes_validas >= settings.images_per_product:
                futuro.cancel()
                continue

            try:
                imagen_bytes, extension = futuro.result()
            except Exception as exc:
                logger.warning(
                    "Fallo al descargar imagen",
                    exc_info=exc,
                    extra={"codigo": producto.codigo, "url": url},
                )
                resultados.append(ResultadoDescarga(url=url, exitoso=False, error=str(exc)))
                if callback_imagen:
                    callback_imagen(False)
                continue

            # Generar nombre de archivo usando la columna seleccionada (o código como fallback)
            indice = imagenes_validas + 1
            nombre_base = producto.nombre_foto or producto.codigo
            # Reemplazar caracteres inválidos en nombres de archivo por guion bajo
            nombre_base = "".join(
                c if c.isalnum() or c in "-_." else "_" for c in nombre_base
            ).strip("_") or producto.codigo
            filename = f"{nombre_base}_{indice:03d}.{extension.lower()}"

            try:
                ruta = storage.save_image(job_id, filename, imagen_bytes)
                imagenes_validas += 1
                resultados.append(
                    ResultadoDescarga(url=url, exitoso=True, ruta_guardada=str(ruta))
                )
                if callback_imagen:
                    callback_imagen(True)
            except OSError as exc:
                logger.error(
                    "Error al guardar imagen en storage",
                    exc_info=exc,
                    extra={"job_id": job_id, "filename": filename},
                )
                resultados.append(ResultadoDescarga(url=url, exitoso=False, error=str(exc)))
                if callback_imagen:
                    callback_imagen(False)

    logger.info(
        "Descarga de producto completada",
        extra={
            "job_id": job_id,
            "codigo": producto.codigo,
            "validas": imagenes_validas,
            "intentadas": len(urls),
        },
    )
    return resultados


def _descargar_y_validar(
    url: str,
    timeout: int,
    min_width: int,
    min_height: int,
    resize_width: int,
    resize_height: int,
) -> tuple[bytes, str]:
    """
    Descarga una imagen HTTP y la valida con Pillow.

    Si la imagen supera las validaciones, la redimensiona al tamaño
    configurado manteniendo la relación de aspecto (LANCZOS).

    Args:
        url: URL de la imagen a descargar.
        timeout: segundos máximos de espera para la conexión HTTP.
        min_width: anchura mínima aceptable en píxeles.
        min_height: altura mínima aceptable en píxeles.
        resize_width: anchura destino del redimensionado.
        resize_height: altura destino del redimensionado.

    Returns:
        Tupla (bytes_imagen_redimensionada, extension_formato).

    Raises:
        ValueError: si la imagen no supera las validaciones.
        requests.RequestException: si falla la descarga HTTP.
        UnidentifiedImageError: si los bytes no son una imagen reconocible.
    """
    respuesta = requests.get(
        url,
        headers=_HEADERS,
        timeout=timeout,
        stream=False,
    )
    respuesta.raise_for_status()

    # Validar que el Content-Type sea una imagen
    content_type = respuesta.headers.get("Content-Type", "")
    if not content_type.startswith("image/"):
        raise ValueError(f"Content-Type no es una imagen: {content_type}")

    try:
        imagen = Image.open(io.BytesIO(respuesta.content))
        imagen.verify()  # Detecta imágenes truncadas o corruptas
        # Reabrir tras verify() porque verify() cierra el stream
        imagen = Image.open(io.BytesIO(respuesta.content))
    except UnidentifiedImageError as exc:
        raise ValueError("No se pudo identificar el formato de imagen.") from exc

    # Validar dimensiones mínimas
    ancho, alto = imagen.size
    if ancho < min_width or alto < min_height:
        raise ValueError(
            f"Imagen demasiado pequeña: {ancho}x{alto}px "
            f"(mínimo {min_width}x{min_height}px)."
        )

    # Validar formato soportado
    formato = (imagen.format or "").upper()
    if formato not in _FORMATOS_ACEPTADOS:
        raise ValueError(f"Formato de imagen no soportado: {formato}")

    # Convertir a RGB si es necesario (WEBP/PNG con alpha → JPEG)
    if imagen.mode not in ("RGB", "L"):
        imagen = imagen.convert("RGB")
        formato = "JPEG"

    # Redimensionar manteniendo relación de aspecto (thumbnail no agranda)
    imagen.thumbnail((resize_width, resize_height), Image.LANCZOS)

    # Serializar a bytes
    buffer = io.BytesIO()
    save_format = "JPEG" if formato in ("JPEG", "WEBP", "BMP") else formato
    imagen.save(buffer, format=save_format, quality=85, optimize=True)

    extension = "jpg" if save_format == "JPEG" else save_format.lower()
    return buffer.getvalue(), extension
