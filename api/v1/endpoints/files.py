"""
Endpoints para la gestión de archivos generados por los trabajos de scraping.

Rutas expuestas:
  GET    /api/v1/files/{job_id}        — Descargar el ZIP de imágenes (job fotos)
  GET    /api/v1/files/{job_id}/csv    — Descargar el CSV de descripciones (job descripciones)
  DELETE /api/v1/files/{job_id}        — Eliminar los archivos de un job
  GET    /api/v1/files/{job_id}/brands — (Fase 6) Descargar fichas de marca JSON

Solo gestiona la capa HTTP. El acceso al sistema de archivos se delega
a StorageService para mantener la arquitectura limpia.

:author: BenjaminDTS
:version: 1.0.0
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from loguru import logger

from api.core.config import get_settings
from services.storage_service import get_storage_service

router = APIRouter(prefix="/files", tags=["Files"])
settings = get_settings()


@router.get(
    "/{job_id}",
    summary="Descargar el archivo ZIP de imágenes de un trabajo",
    response_class=FileResponse,
)
async def descargar_zip(job_id: str) -> FileResponse:
    """
    Devuelve el archivo ZIP con todas las imágenes descargadas para un job.

    El archivo ZIP se genera al completar el job y se elimina tras el TTL
    definido en FILE_TTL_SECONDS.

    Args:
        job_id: identificador UUID del trabajo.

    Returns:
        FileResponse con el ZIP de imágenes como adjunto descargable.

    Raises:
        HTTPException 404: si el ZIP no existe o el job no ha completado.
    """
    storage = get_storage_service()

    try:
        zip_path = storage.get_zip_path(job_id)
    except FileNotFoundError as exc:
        logger.warning(
            "ZIP solicitado no encontrado",
            exc_info=exc,
            extra={"job_id": job_id},
        )
        raise HTTPException(
            status_code=404,
            detail="El archivo ZIP no existe. El job puede no haber completado aún.",
        ) from exc

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=f"harvist_{job_id}.zip",
        headers={"Content-Disposition": f'attachment; filename="harvist_{job_id}.zip"'},
    )


@router.delete(
    "/{job_id}",
    response_model=dict,
    summary="Eliminar todos los archivos generados por un trabajo",
)
async def eliminar_archivos_job(job_id: str) -> JSONResponse:
    """
    Elimina el directorio de imágenes y el ZIP de un job.

    Útil para liberar espacio en disco manualmente antes de que expire el TTL.

    Args:
        job_id: identificador UUID del trabajo.

    Returns:
        JSONResponse confirmando la eliminación.

    Raises:
        HTTPException 404: si no existen archivos para ese job_id.
    """
    storage = get_storage_service()

    try:
        storage.delete_job_files(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontraron archivos para el job '{job_id}'.",
        ) from exc
    except OSError as exc:
        logger.error(
            "Error al eliminar archivos del job",
            exc_info=exc,
            extra={"job_id": job_id},
        )
        raise HTTPException(
            status_code=500,
            detail="Error interno al eliminar los archivos.",
        ) from exc

    logger.info("Archivos del job eliminados", extra={"job_id": job_id})

    return JSONResponse(
        content={
            "success": True,
            "data": {"job_id": job_id},
            "message": "Archivos eliminados correctamente.",
        }
    )


@router.get(
    "/{job_id}/csv",
    summary="Descargar el CSV de descripciones de un trabajo",
    response_class=FileResponse,
)
async def descargar_csv(job_id: str) -> FileResponse:
    """
    Devuelve el archivo descripciones.csv generado por el pipeline de IA.

    Args:
        job_id: identificador UUID del trabajo.

    Returns:
        FileResponse con el CSV de descripciones como adjunto descargable.

    Raises:
        HTTPException 404: si el CSV no existe o el job no ha completado.
    """
    storage = get_storage_service()
    csv_path = storage.get_job_dir(job_id) / "descripciones.csv"

    if not csv_path.exists():
        logger.warning(
            "CSV de descripciones no encontrado",
            extra={"job_id": job_id},
        )
        raise HTTPException(
            status_code=404,
            detail="El CSV no existe. El job puede no haber completado aún.",
        )

    return FileResponse(
        path=str(csv_path),
        media_type="text/csv",
        filename=f"descripciones_{job_id}.csv",
        headers={"Content-Disposition": f'attachment; filename="descripciones_{job_id}.csv"'},
    )


@router.get(
    "/{job_id}/brands",
    summary="Descargar CSV de marcas detectadas por EAN",
    response_class=FileResponse,
    include_in_schema=True,
)
async def descargar_fichas_marca(job_id: str) -> FileResponse:
    """
    Devuelve el archivo marcas.csv generado por el pipeline de resolución EAN→marca.

    El CSV contiene las columnas: codigo, ean, marca_detectada, exitoso, error.

    Args:
        job_id: identificador UUID del trabajo.

    Returns:
        FileResponse con el CSV de marcas como adjunto descargable.

    Raises:
        HTTPException 404: si el CSV no existe o el job no ha completado.
    """
    storage = get_storage_service()
    json_path = storage.get_job_dir(job_id) / "marcas.csv"

    if not json_path.exists():
        logger.warning(
            "marcas.csv no encontrado",
            extra={"job_id": job_id},
        )
        raise HTTPException(
            status_code=404,
            detail="El archivo de marcas no existe. El job puede no haber completado aún.",
        )

    return FileResponse(
        path=str(json_path),
        media_type="text/csv",
        filename=f"marcas_{job_id}.csv",
        headers={"Content-Disposition": f'attachment; filename="marcas_{job_id}.csv"'},
    )
