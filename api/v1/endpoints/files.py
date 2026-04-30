"""
Endpoints para la gestión de archivos generados por los trabajos de scraping.

Rutas expuestas:
  GET    /api/v1/files/{job_id}                                 — Descargar el ZIP de imágenes (job fotos)
  GET    /api/v1/files/{job_id}/csv                             — Descargar el CSV de descripciones (?only_approved=true para solo aprobadas, Fase 7.3)
  GET    /api/v1/files/{job_id}/seo                             — (Fase 7.1) Descargar CSV de textos SEO (meta_title + meta_description)
  GET    /api/v1/files/{job_id}/brands                          — (Fase 6) Descargar fichas de marca JSON
  GET    /api/v1/files/{job_id}/translations/{lang}             — (Fase 7.2) Descargar CSV de traducciones por idioma
  GET    /api/v1/files/{job_id}/photos/{codigo}/candidates/{n}  — (Fase 7.5) Servir candidata de foto para previsualización
  DELETE /api/v1/files/{job_id}                                 — Eliminar los archivos de un job

Solo gestiona la capa HTTP. El acceso al sistema de archivos se delega
a StorageService para mantener la arquitectura limpia.

:author: BenjaminDTS
:author: Carlitos6712
:version: 1.3.0
"""

import csv
import io

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from loguru import logger

from api.core.config import get_settings
from api.v1.schemas.job import SUPPORTED_LANGUAGES, DescriptionReviewState, ReviewStatus
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
    include_in_schema=True,
)
async def descargar_csv(
    job_id: str,
    only_approved: bool = Query(
        default=False,
        description=(
            "Si True, devuelve solo las descripciones con estado de revisión 'approved' (Fase 7.3). "
            "Devuelve 204 si no hay ninguna aprobada. "
            "Si False (por defecto), devuelve todas las descripciones sin filtrar."
        ),
    ),
) -> Response:
    """
    Devuelve el archivo descripciones.csv generado por el pipeline de IA.

    Con ?only_approved=true filtra las filas por estado de revisión en Redis,
    devolviendo solo las descripciones que el usuario ha aprobado (Fase 7.3).
    Sin el parámetro (o con only_approved=false), el comportamiento es idéntico
    al original: devuelve el CSV completo sin filtrar.

    Args:
        job_id: identificador UUID del trabajo.
        only_approved: si True, filtra por status=approved en Redis.

    Returns:
        FileResponse con el CSV completo, o Response con CSV filtrado en memoria,
        o Response 204 si only_approved=True y no hay descripciones aprobadas.

    Raises:
        HTTPException 404: si el CSV no existe o el job no ha completado.

    :author: Carlitos6712
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

    # Comportamiento original: sin filtro
    if not only_approved:
        return FileResponse(
            path=str(csv_path),
            media_type="text/csv",
            filename=f"descripciones_{job_id}.csv",
            headers={"Content-Disposition": f'attachment; filename="descripciones_{job_id}.csv"'},
        )

    # Filtrado por estado de revisión approved
    redis: aioredis.Redis | None = None
    try:
        redis = aioredis.from_url(settings.redis_url, decode_responses=True)

        rows_aprobadas: list[dict] = []
        fieldnames: list[str] = []

        with open(csv_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            for row in reader:
                codigo = row.get("codigo", "")
                if not codigo:
                    continue
                review_key = f"job:{job_id}:review:{codigo}"
                raw_review = await redis.get(review_key)
                if raw_review:
                    state = DescriptionReviewState.model_validate_json(raw_review)
                    if state.status == ReviewStatus.APPROVED:
                        if state.edited_text:
                            row["corta"] = state.edited_text
                        rows_aprobadas.append(row)

        if not rows_aprobadas:
            logger.info(
                "No hay descripciones aprobadas para exportar",
                extra={"job_id": job_id},
            )
            return Response(status_code=204)

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows_aprobadas)

        csv_bytes = buffer.getvalue().encode("utf-8-sig")
        filename = f"descripciones_aprobadas_{job_id}.csv"
        return Response(
            content=csv_bytes,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    finally:
        if redis:
            await redis.aclose()


@router.get(
    "/{job_id}/seo",
    summary="Descargar CSV de textos SEO (meta_title + meta_description)",
    response_class=FileResponse,
    include_in_schema=True,
)
async def descargar_seo(job_id: str) -> FileResponse:
    """
    Devuelve el archivo seo.csv generado por el pipeline de generación SEO (Fase 7.1).

    El CSV contiene las columnas: codigo, nombre, meta_title, meta_description.
    Meta_title máx 60 caracteres, meta_description máx 160 caracteres.

    Args:
        job_id: identificador UUID del trabajo.

    Returns:
        FileResponse con el CSV de textos SEO como adjunto descargable.

    Raises:
        HTTPException 404: si el CSV no existe o el job no ha completado.

    :author: BenjaminDTS
    """
    storage = get_storage_service()
    seo_path = storage.get_job_dir(job_id) / "seo.csv"

    if not seo_path.exists():
        logger.warning(
            "seo.csv no encontrado",
            extra={"job_id": job_id},
        )
        raise HTTPException(
            status_code=404,
            detail="El archivo de textos SEO no existe. El job puede no haber completado aún.",
        )

    return FileResponse(
        path=str(seo_path),
        media_type="text/csv",
        filename=f"seo_{job_id}.csv",
        headers={"Content-Disposition": f'attachment; filename="seo_{job_id}.csv"'},
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


@router.get(
    "/{job_id}/translations/{lang}",
    summary="Descargar CSV de traducciones de descripciones por idioma",
    response_class=FileResponse,
    include_in_schema=True,
)
async def descargar_traducciones(
    job_id: str,
    lang: str = Path(
        description=f"Código ISO 639-1 del idioma destino. Valores permitidos: {SUPPORTED_LANGUAGES}.",
        examples=["en", "fr", "de"],
    ),
) -> FileResponse:
    """
    Devuelve el CSV de traducciones para el idioma especificado (Fase 7.2).

    El CSV contiene: codigo, nombre, marca, categoria,
    descripcion_corta, descripcion_larga, keywords, meta_description.

    Args:
        job_id: identificador UUID del trabajo.
        lang: código ISO 639-1 del idioma destino (ej: 'en', 'fr', 'de', 'it', 'pt').

    Returns:
        FileResponse con el CSV de traducciones como adjunto descargable.

    Raises:
        HTTPException 400: si el idioma no está soportado.
        HTTPException 404: si el CSV no existe o el job no ha completado.

    :author: BenjaminDTS
    """
    if lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Idioma '{lang}' no soportado. "
                f"Idiomas válidos: {list(SUPPORTED_LANGUAGES)}."
            ),
        )

    storage = get_storage_service()
    csv_path = storage.get_job_dir(job_id) / f"traducciones_{lang}.csv"

    if not csv_path.exists():
        logger.warning(
            "CSV de traducciones no encontrado",
            extra={"job_id": job_id, "lang": lang},
        )
        raise HTTPException(
            status_code=404,
            detail=(
                f"El archivo de traducciones para '{lang}' no existe. "
                "El job puede no haber completado aún o no se solicitó ese idioma."
            ),
        )

    filename = f"descripciones_{lang}_{job_id[:8]}.csv"
    return FileResponse(
        path=str(csv_path),
        media_type="text/csv; charset=utf-8",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/{job_id}/photos/{codigo}/candidates/{n:int}",
    summary="(Fase 7.5) Servir una candidata de foto para previsualización",
    response_class=StreamingResponse,
    include_in_schema=True,
)
async def obtener_candidata_foto(
    job_id: str,
    codigo: str,
    n: int,
) -> StreamingResponse:
    """
    Sirve una imagen candidata como JPEG para previsualización en el navegador.

    La imagen se lee del directorio candidates/ del job y se devuelve
    como StreamingResponse con cabecera Cache-Control.

    Args:
        job_id: identificador UUID del trabajo.
        codigo: código único del producto.
        n: índice de la candidata (0-based).

    Returns:
        StreamingResponse con la imagen JPEG.

    Raises:
        HTTPException 404: si la candidata no existe.
        HTTPException 500: si hay error al leer la imagen.

    :author: BenjaminDTS
    """
    storage = get_storage_service()

    try:
        candidate_path = storage.candidate_path(job_id, codigo, n)
    except FileNotFoundError as exc:
        logger.warning(
            "Candidata no encontrada",
            exc_info=exc,
            extra={"job_id": job_id, "codigo": codigo, "n": n},
        )
        raise HTTPException(
            status_code=404,
            detail=f"Candidata no encontrada para '{codigo}' (índice {n}).",
        ) from exc

    if not candidate_path.exists():
        logger.warning(
            "Candidata no existe en disco",
            extra={"job_id": job_id, "codigo": codigo, "n": n},
        )
        raise HTTPException(
            status_code=404,
            detail=f"Candidata no existe para '{codigo}' (índice {n}).",
        )

    try:
        image_data = candidate_path.read_bytes()
    except OSError as exc:
        logger.error(
            "Error leyendo candidata del disco",
            exc_info=exc,
            extra={"job_id": job_id, "codigo": codigo, "n": n},
        )
        raise HTTPException(
            status_code=500,
            detail="Error al leer la imagen candidata.",
        ) from exc

    logger.debug(
        "Candidata servida",
        extra={"job_id": job_id, "codigo": codigo, "n": n, "bytes": len(image_data)},
    )

    return StreamingResponse(
        iter([image_data]),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "max-age=3600",
            "Content-Disposition": f'inline; filename="{codigo}_candidate_{n}.jpg"',
        },
    )
