"""
Módulo de gestión de productos en Dolibarr.

Wrapper sobre DolibarrClient que añade lógica de negocio específica de productos:
validación, imagen, sincronización desde job Harvist.

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

import base64
import csv
import io
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from services.integrations.base import IntegrationError
from services.integrations.dolibarr.client import DolibarrClient

if TYPE_CHECKING:
    from services.storage_service import StorageService

_DOLIBARR_PRODUCTS_RESOURCE = "products"
_DOLIBARR_DOCUMENTS_RESOURCE = "documents"

_EXTRA_TYPE_MAP: dict[str, str] = {
    "varchar": "text", "char": "text", "phone": "text", "mail": "text", "url": "text",
    "int": "number", "double": "number", "price": "number",
    "date": "date", "datetime": "date",
    "select": "select", "radio": "select",
    "boolean": "boolean", "chkbxlst": "boolean",
    "text": "textarea", "html": "textarea",
}

_STANDARD_FIELDS: list[dict[str, Any]] = [
    {"key": "ref", "label": "Referencia", "type": "text", "required": True, "section": "Identificación", "is_extra": False},
    {"key": "label", "label": "Nombre", "type": "text", "required": True, "section": "Identificación", "is_extra": False},
    {"key": "type", "label": "Tipo", "type": "select", "required": False, "section": "Identificación", "is_extra": False, "options": [{"value": "0", "label": "Producto"}, {"value": "1", "label": "Servicio"}]},
    {"key": "status", "label": "Estado", "type": "select", "required": False, "section": "Identificación", "is_extra": False, "options": [{"value": "1", "label": "Activo"}, {"value": "0", "label": "Inactivo"}]},
    {"key": "price", "label": "Precio (€)", "type": "number", "required": False, "section": "Identificación", "is_extra": False},
    {"key": "url", "label": "URL pública", "type": "text", "required": False, "section": "Identificación", "is_extra": False},
    {"key": "description", "label": "Descripción", "type": "textarea", "required": False, "section": "Identificación", "is_extra": False},
    {"key": "barcode_type", "label": "Tipo de código de barras", "type": "select", "required": False, "section": "Código de barras", "is_extra": False, "options": [{"value": "", "label": "— Ninguno —"}, {"value": "EAN13", "label": "EAN-13"}, {"value": "EAN8", "label": "EAN-8"}, {"value": "UPC", "label": "UPC"}, {"value": "QR", "label": "QR"}, {"value": "ISBN", "label": "ISBN"}, {"value": "CODE128", "label": "Code 128"}]},
    {"key": "barcode", "label": "Valor del código de barras", "type": "text", "required": False, "section": "Código de barras", "is_extra": False},
    {"key": "tobatch", "label": "Numeración por lotes/series", "type": "select", "required": False, "section": "Lotes y series", "is_extra": False, "options": [{"value": "", "label": "No"}, {"value": "1", "label": "Por lote"}, {"value": "2", "label": "Por serie"}]},
    {"key": "accountancy_code_sell", "label": "Código contable (ventas)", "type": "text", "required": False, "section": "Contabilidad", "is_extra": False},
    {"key": "accountancy_code_sell_export", "label": "Código contable (ventas exportación)", "type": "text", "required": False, "section": "Contabilidad", "is_extra": False},
    {"key": "accountancy_code_buy", "label": "Código contable (compras)", "type": "text", "required": False, "section": "Contabilidad", "is_extra": False},
    {"key": "accountancy_code_buy_intra", "label": "Código contable (compras importación)", "type": "text", "required": False, "section": "Contabilidad", "is_extra": False},
    {"key": "fk_default_warehouse", "label": "Almacén por defecto (ID)", "type": "number", "required": False, "section": "Logística", "is_extra": False},
    {"key": "finished", "label": "Naturaleza del producto", "type": "select", "required": False, "section": "Logística", "is_extra": False, "options": [{"value": "", "label": "— No definido —"}, {"value": "0", "label": "Materia prima / Comprado"}, {"value": "1", "label": "Producto fabricado"}]},
    {"key": "weight", "label": "Peso", "type": "number", "required": False, "section": "Dimensiones y peso", "is_extra": False},
    {"key": "weight_units", "label": "Unidad peso", "type": "select", "required": False, "section": "Dimensiones y peso", "is_extra": False, "options": [{"value": "0", "label": "kg"}, {"value": "-1", "label": "g"}, {"value": "-2", "label": "mg"}, {"value": "1", "label": "t"}, {"value": "99", "label": "oz"}, {"value": "98", "label": "lb"}]},
    {"key": "length", "label": "Longitud", "type": "number", "required": False, "section": "Dimensiones y peso", "is_extra": False},
    {"key": "width", "label": "Ancho", "type": "number", "required": False, "section": "Dimensiones y peso", "is_extra": False},
    {"key": "height", "label": "Alto", "type": "number", "required": False, "section": "Dimensiones y peso", "is_extra": False},
    {"key": "length_units", "label": "Unidad longitud", "type": "select", "required": False, "section": "Dimensiones y peso", "is_extra": False, "options": [{"value": "0", "label": "m"}, {"value": "-1", "label": "dm"}, {"value": "-2", "label": "cm"}, {"value": "-3", "label": "mm"}, {"value": "99", "label": "in"}]},
    {"key": "surface", "label": "Superficie", "type": "number", "required": False, "section": "Dimensiones y peso", "is_extra": False},
    {"key": "surface_units", "label": "Unidad superficie", "type": "select", "required": False, "section": "Dimensiones y peso", "is_extra": False, "options": [{"value": "0", "label": "m²"}, {"value": "-1", "label": "dm²"}, {"value": "-2", "label": "cm²"}, {"value": "-3", "label": "mm²"}]},
    {"key": "volume", "label": "Volumen", "type": "number", "required": False, "section": "Dimensiones y peso", "is_extra": False},
    {"key": "volume_units", "label": "Unidad volumen", "type": "select", "required": False, "section": "Dimensiones y peso", "is_extra": False, "options": [{"value": "0", "label": "m³"}, {"value": "-1", "label": "dm³ (L)"}, {"value": "-2", "label": "cm³ (mL)"}, {"value": "-3", "label": "mm³"}]},
    {"key": "customcode", "label": "Código HS", "type": "text", "required": False, "section": "Aduanas", "is_extra": False},
    {"key": "country_id", "label": "País de origen (ID Dolibarr)", "type": "number", "required": False, "section": "Aduanas", "is_extra": False},
]


def _decode_csv(content: bytes) -> str:
    """Decodifica bytes CSV intentando UTF-8 y latin-1 como fallback."""
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def _detect_delimiter(text: str) -> str:
    """Detecta el delimitador CSV priorizando ; y , sobre tabulador y pipe.

    Usa csv.Sniffer primero; si falla cuenta ocurrencias en la primera línea.
    """
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        first_line = sample.split("\n")[0]
        counts = {d: first_line.count(d) for d in (";", ",", "\t", "|")}
        best = max(counts, key=lambda d: counts[d])
        return best if counts[best] > 0 else ","


def _normalize_product(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce Dolibarr string fields to their proper Python types."""
    result: dict[str, Any] = {
        "id": int(raw.get("id", 0) or 0),
        "ref": raw.get("ref", "") or "",
        "label": raw.get("label", "") or "",
        "description": raw.get("description", "") or "",
        "price": float(raw.get("price", 0) or 0),
        "status": int(raw.get("status", 0) or 0),
        "type": int(raw.get("type", 0) or 0),
    }

    raw_array_options = raw.get("array_options")
    if isinstance(raw_array_options, dict):
        result["array_options"] = raw_array_options

    _optional_str = (
        "barcode", "barcode_type", "url", "customcode",
        "accountancy_code_sell", "accountancy_code_sell_export",
        "accountancy_code_buy", "accountancy_code_buy_intra",
    )
    _optional_int = (
        "tobatch", "fk_default_warehouse", "finished",
        "weight_units", "length_units", "surface_units", "volume_units", "country_id",
    )
    _optional_float = ("weight", "length", "width", "height", "surface", "volume")

    for key in _optional_str:
        val = raw.get(key)
        if val is not None:
            result[key] = str(val) if val else ""

    for key in _optional_int:
        val = raw.get(key)
        if val is not None and val != "":
            try:
                result[key] = int(val)
            except (ValueError, TypeError):
                pass

    for key in _optional_float:
        val = raw.get(key)
        if val is not None and val != "":
            try:
                result[key] = float(val)
            except (ValueError, TypeError):
                pass

    return result


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

    async def get_product_fields(
        self,
        pre_fetched_extras: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Devuelve el schema de campos para productos de esta instancia Dolibarr.

        Combina los campos estándar con los campos extra. Si se proveen
        ``pre_fetched_extras`` (ya normalizados por DolibarrExtraFieldService),
        se usan directamente en vez de llamar a la REST API. Esto permite que
        el endpoint use el fallback de BD sin duplicar la lógica aquí.

        Args:
            pre_fetched_extras: lista de extrafields ya normalizados, con las
                claves ``attrname``, ``label``, ``type``, ``required`` y ``param``.
                Si es None, se consulta la REST API de Dolibarr directamente.

        Returns:
            Lista de dicts con key, label, type, required, section, is_extra y options.
        """
        fields: list[dict[str, Any]] = [dict(f) for f in _STANDARD_FIELDS]

        if pre_fetched_extras is not None:
            extra_items = [
                (str(ef.get("attrname", "")), ef)
                for ef in pre_fetched_extras
                if ef.get("attrname")
            ]
        else:
            try:
                response = await self._client._request(
                    "GET", "extrafields", params={"attrname": "product"}
                )
                extra_items = []
                if response.status_code == 200:
                    raw = response.json()
                    if isinstance(raw, dict):
                        extra_items = [(k, v) for k, v in raw.items() if isinstance(v, dict)]
                    elif isinstance(raw, list):
                        extra_items = [
                            (str(item["attrname"]), item)
                            for item in raw
                            if isinstance(item, dict) and "attrname" in item
                        ]
            except Exception as exc:
                logger.warning("No se pudieron obtener extra fields de Dolibarr", exc_info=exc)
                extra_items = []

        for field_key, field_def in extra_items:
            field_type_raw = str(field_def.get("type", "varchar"))
            field_type = _EXTRA_TYPE_MAP.get(field_type_raw, "text")

            options: list[dict[str, str]] = []
            if field_type == "select":
                param = field_def.get("param") or {}
                if isinstance(param, str):
                    try:
                        param = json.loads(param)
                    except (json.JSONDecodeError, ValueError):
                        param = {}
                raw_opts = param.get("options", {}) if isinstance(param, dict) else {}
                if isinstance(raw_opts, dict):
                    options = [{"value": str(k), "label": str(v)} for k, v in raw_opts.items()]

            fields.append({
                "key": f"options_{field_key}",
                "label": str(field_def.get("label", field_key)),
                "type": field_type,
                "required": field_def.get("required", False) if isinstance(field_def.get("required"), bool) else str(field_def.get("required", "0")) == "1",
                "section": "Campos personalizados",
                "is_extra": True,
                "options": options if options else None,
            })

        return fields

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
        raw = await self._client.list(
            _DOLIBARR_PRODUCTS_RESOURCE,
            limit=limit,
            offset=offset,
            filters=filters,
        )
        return [_normalize_product(p) for p in raw]

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
        raw = await self._client.get(_DOLIBARR_PRODUCTS_RESOURCE, product_id)
        return _normalize_product(raw)

    async def create_product(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Crea un producto en Dolibarr.

        Algunas versiones de Dolibarr devuelven HTTP 500 cuando se incluyen
        ``array_options`` en la creación. Por eso se separa el proceso:
          1. Crear el producto sin extrafields.
          2. Si hay extrafields, actualizarlos con PUT en un segundo paso.

        Args:
            data: campos del producto. Campos esperados: ref, label, price,
                  description, type (0=producto, 1=servicio), status (0/1).
                  Puede incluir ``array_options`` con extrafields.

        Returns:
            Dict con el producto creado, incluyendo el ID asignado por Dolibarr.
        """
        payload = dict(data)
        array_options = payload.pop("array_options", None)

        raw = await self._client.create(_DOLIBARR_PRODUCTS_RESOURCE, payload)

        product_id: int | None = None
        if isinstance(raw, dict):
            product_id = int(raw.get("id", 0)) or None
        elif isinstance(raw, (int, str)):
            try:
                product_id = int(raw)
            except (ValueError, TypeError):
                pass

        if product_id and array_options:
            try:
                await self._client.update(
                    _DOLIBARR_PRODUCTS_RESOURCE,
                    product_id,
                    {"array_options": array_options},
                )
            except Exception as exc:
                logger.warning(
                    "Extrafields no guardados en producto creado",
                    exc_info=exc,
                    extra={"product_id": product_id},
                )

        if product_id:
            try:
                full = await self._client.get(_DOLIBARR_PRODUCTS_RESOURCE, product_id)
                return _normalize_product(full)
            except Exception:
                pass

        return _normalize_product(raw) if isinstance(raw, dict) else {"id": product_id}

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
        raw = await self._client.update(
            _DOLIBARR_PRODUCTS_RESOURCE,
            product_id,
            data,
        )
        return _normalize_product(raw) if isinstance(raw, dict) else raw

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

    @staticmethod
    def parse_csv_preview(
        content: bytes,
        preview_rows: int = 5,
    ) -> dict[str, Any]:
        """
        Parsea las primeras filas de un CSV para previsualización.

        Detecta delimitador automáticamente. Soporta UTF-8 y latin-1.

        Args:
            content:      contenido raw del archivo CSV.
            preview_rows: número máximo de filas de previsualización.

        Returns:
            Dict con headers, preview (list of dicts) y total_rows.
        """
        text = _decode_csv(content)
        delimiter = _detect_delimiter(text)
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        headers = list(reader.fieldnames or [])
        preview: list[dict[str, str]] = []
        total = 0

        for row in reader:
            total += 1
            if len(preview) < preview_rows:
                preview.append({k: str(v or "") for k, v in row.items() if k is not None})

        return {"headers": headers, "preview": preview, "total_rows": total}

    async def import_from_csv(
        self,
        content: bytes,
        mapping: dict[str, str],
        overwrite: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Importa productos en masa a Dolibarr desde un CSV con mapeo de columnas.

        Cada fila del CSV se convierte en un producto usando ``mapping``
        (clave=columna CSV, valor=campo Dolibarr). El campo ``ref`` es
        obligatorio: si no está en el mapping la fila se marca como error.

        Campos cuya clave Dolibarr empiece por ``options_`` se tratan como
        extrafields y se agrupan en ``array_options``.

        Args:
            content:  contenido raw del archivo CSV.
            mapping:  dict que mapea nombre_columna_csv → campo_dolibarr.
            overwrite: si True, actualiza productos existentes (busca por ref).

        Returns:
            Lista de dicts con row, ref, action, dolibarr_id y error.
        """
        text = _decode_csv(content)
        delimiter = _detect_delimiter(text)
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        results: list[dict[str, Any]] = []

        for row_num, row in enumerate(reader, start=2):
            payload: dict[str, Any] = {}
            array_options: dict[str, Any] = {}

            for csv_col, doli_field in mapping.items():
                raw_val = (row.get(csv_col) or "").strip()
                if not raw_val:
                    continue
                if doli_field.startswith("options_"):
                    array_options[doli_field] = raw_val
                else:
                    payload[doli_field] = raw_val

            ref = str(payload.get("ref", "")).strip()
            result: dict[str, Any] = {
                "row": row_num,
                "ref": ref,
                "action": None,
                "dolibarr_id": None,
                "error": None,
            }

            if not ref:
                result["action"] = "error"
                result["error"] = "Columna 'ref' vacía o no mapeada."
                results.append(result)
                continue

            if array_options:
                payload["array_options"] = array_options

            try:
                existing = await self._find_product_by_ref(ref)

                if existing is not None:
                    dolibarr_id = int(existing["id"])
                    if overwrite:
                        await self.update_product(dolibarr_id, payload)
                        result["action"] = "updated"
                        logger.info(
                            "Producto actualizado via CSV import",
                            extra={"ref": ref, "dolibarr_id": dolibarr_id, "row": row_num},
                        )
                    else:
                        result["action"] = "skipped"
                        result["dolibarr_id"] = dolibarr_id
                        logger.debug("Producto ya existe, omitido", extra={"ref": ref})
                        results.append(result)
                        continue
                else:
                    created = await self.create_product(payload)
                    dolibarr_id = int(created["id"]) if isinstance(created, dict) else int(created)
                    result["action"] = "created"
                    logger.info(
                        "Producto creado via CSV import",
                        extra={"ref": ref, "dolibarr_id": dolibarr_id, "row": row_num},
                    )

                result["dolibarr_id"] = dolibarr_id

            except Exception as exc:
                logger.error(
                    "Error importando fila CSV a Dolibarr",
                    exc_info=exc,
                    extra={"row": row_num, "ref": ref},
                )
                result["action"] = "error"
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
