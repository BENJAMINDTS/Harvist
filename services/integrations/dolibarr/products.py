"""
Módulo de gestión de productos en Dolibarr.

Wrapper sobre DolibarrClient que añade lógica de negocio específica de productos:
validación, imagen, sincronización desde job Harvist.

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from services.integrations.base import IntegrationError
from services.integrations.dolibarr.client import DolibarrClient

if TYPE_CHECKING:
    from services.storage_service import StorageService

_DOLIBARR_PRODUCTS_RESOURCE = "products"
_DOLIBARR_DOCUMENTS_RESOURCE = "documents"


class DolibarrProductService:
    """
    Servicio de gestión de productos Dolibarr.

    Encapsula todas las operaciones CRUD sobre productos, subida de imagen
    y sincronización desde jobs Harvist completados.

    :author: Carlitos6712
    """

    def __init__(self, client: DolibarrClient) -> None:
        """
        Args:
            client: instancia de DolibarrClient configurada y lista para usar.
        """
        self._client = client

    async def list_products(
        self,
        limit: int = 50,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Lista productos de Dolibarr con paginación.

        Args:
            limit:   número máximo de productos por página.
            offset:  desplazamiento desde el inicio.
            filters: filtros adicionales como query params.

        Returns:
            Lista de dicts con los productos devueltos por Dolibarr.
        """
        return await self._client.list(
            _DOLIBARR_PRODUCTS_RESOURCE,
            limit=limit,
            offset=offset,
            filters=filters,
        )

    async def get_product(self, product_id: int) -> dict[str, Any]:
        """
        Obtiene un producto por ID.

        Args:
            product_id: ID del producto en Dolibarr.

        Returns:
            Dict con los datos del producto.

        Raises:
            IntegrationError: si el producto no existe o hay error de comunicación.
        """
        return await self._client.get(_DOLIBARR_PRODUCTS_RESOURCE, product_id)

    async def create_product(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Crea un producto en Dolibarr.

        Args:
            data: campos del producto. Campos esperados: ref, label, price,
                  description, type (0=producto, 1=servicio), status (0/1).

        Returns:
            Dict con el producto creado, incluyendo el ID asignado por Dolibarr.
        """
        return await self._client.create(_DOLIBARR_PRODUCTS_RESOURCE, data)

    async def update_product(
        self,
        product_id: int,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Actualiza un producto existente.

        Args:
            product_id: ID del producto en Dolibarr.
            data:       campos a actualizar.

        Returns:
            Dict con el producto actualizado.
        """
        return await self._client.update(
            _DOLIBARR_PRODUCTS_RESOURCE,
            product_id,
            data,
        )

    async def delete_product(self, product_id: int) -> bool:
        """
        Elimina un producto.

        Args:
            product_id: ID del producto en Dolibarr.

        Returns:
            True si se eliminó correctamente.

        Raises:
            IntegrationError: si Dolibarr devuelve un error al eliminar.
        """
        return await self._client.delete(_DOLIBARR_PRODUCTS_RESOURCE, product_id)

    async def upload_image(
        self,
        product_id: int,
        image_path: Path,
    ) -> dict[str, Any]:
        """
        Sube una imagen a un producto de Dolibarr.

        Lee el archivo, lo codifica en base64 y lo envía via
        POST /documents con los campos:
          modulepart   = "product"
          id           = product_id
          filename     = image_path.name
          filecontent  = base64 del archivo
          fileencoding = "base64"

        Args:
            product_id: ID del producto en Dolibarr.
            image_path: ruta local al archivo de imagen.

        Returns:
            Dict con la respuesta de Dolibarr.

        Raises:
            FileNotFoundError: si image_path no existe.
            IntegrationError:  si Dolibarr rechaza la subida.
        """
        if not image_path.exists():
            raise FileNotFoundError(
                f"Imagen no encontrada en {image_path}"
            )

        image_bytes = image_path.read_bytes()
        encoded = base64.b64encode(image_bytes).decode("ascii")

        payload: dict[str, Any] = {
            "modulepart": "product",
            "id": product_id,
            "filename": image_path.name,
            "filecontent": encoded,
            "fileencoding": "base64",
        }

        logger.info(
            "Subiendo imagen a Dolibarr",
            extra={"product_id": product_id, "filename": image_path.name},
        )

        return await self._client.create(_DOLIBARR_DOCUMENTS_RESOURCE, payload)

    async def sync_from_job(
        self,
        job_id: str,
        product_codes: list[str],
        overwrite: bool = False,
        storage: "StorageService | None" = None,
    ) -> list[dict[str, Any]]:
        """
        Sincroniza productos de un job Harvist completado con Dolibarr.

        Para cada código en product_codes:
          1. Busca si el producto ya existe en Dolibarr por ref=codigo
          2. Si no existe → crea el producto con los datos del job
          3. Si existe y overwrite=True → actualiza
          4. Si existe y overwrite=False → salta (log info)
          5. Si hay imagen descargada → llama a upload_image()
          6. Si hay descripción generada → la incluye en el producto

        Args:
            job_id:        ID del job Harvist de origen.
            product_codes: lista de códigos a sincronizar.
            overwrite:     si True, sobreescribe productos existentes.
            storage:       servicio de almacenamiento para leer imágenes.

        Returns:
            Lista de dicts con resultado por producto:
            { "codigo": str, "action": "created"|"updated"|"skipped",
              "dolibarr_id": int | None, "error": str | None }
        """
        results: list[dict[str, Any]] = []

        for codigo in product_codes:
            result: dict[str, Any] = {
                "codigo": codigo,
                "action": None,
                "dolibarr_id": None,
                "error": None,
            }

            try:
                existing = await self._find_product_by_ref(codigo)

                if existing is not None:
                    dolibarr_id = int(existing["id"])
                    if overwrite:
                        await self.update_product(dolibarr_id, {"ref": codigo})
                        result["action"] = "updated"
                        logger.info(
                            "Producto actualizado en Dolibarr",
                            extra={"codigo": codigo, "dolibarr_id": dolibarr_id},
                        )
                    else:
                        result["action"] = "skipped"
                        result["dolibarr_id"] = dolibarr_id
                        logger.info(
                            "Producto ya existe en Dolibarr, omitido",
                            extra={"codigo": codigo, "dolibarr_id": dolibarr_id},
                        )
                        results.append(result)
                        continue
                else:
                    created = await self.create_product({"ref": codigo, "label": codigo})
                    dolibarr_id = int(created["id"]) if isinstance(created, dict) else int(created)
                    result["action"] = "created"
                    logger.info(
                        "Producto creado en Dolibarr",
                        extra={"codigo": codigo, "dolibarr_id": dolibarr_id},
                    )

                result["dolibarr_id"] = dolibarr_id

                if storage is not None:
                    image_path = storage.get_job_dir(job_id) / f"{codigo}.jpg"
                    if image_path.exists():
                        try:
                            await self.upload_image(dolibarr_id, image_path)
                            logger.info(
                                "Imagen subida a Dolibarr",
                                extra={"codigo": codigo, "dolibarr_id": dolibarr_id},
                            )
                        except (IntegrationError, OSError) as img_exc:
                            logger.error(
                                "Error al subir imagen",
                                exc_info=img_exc,
                                extra={"codigo": codigo},
                            )
                    else:
                        logger.debug(
                            "Sin imagen para producto",
                            extra={"codigo": codigo, "job_id": job_id},
                        )

            except Exception as exc:
                logger.error(
                    "Error sincronizando producto con Dolibarr",
                    exc_info=exc,
                    extra={"codigo": codigo, "job_id": job_id},
                )
                result["error"] = str(exc)

            results.append(result)

        return results

    async def _find_product_by_ref(
        self,
        ref: str,
    ) -> dict[str, Any] | None:
        """
        Busca un producto por su referencia (campo ref).

        Args:
            ref: referencia del producto (usualmente el código interno).

        Returns:
            Dict del producto si existe, None si no se encuentra.
        """
        try:
            products = await self._client.list(
                _DOLIBARR_PRODUCTS_RESOURCE,
                limit=1,
                filters={"sqlfilters": f"(ref:=:'{ref}')"},
            )
            if products:
                return products[0]
            return None
        except IntegrationError:
            return None
