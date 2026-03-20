"""
Servicio de lectura, validación y normalización del CSV de inventario.

Responsabilidades:
  - Validar tipo MIME y extensión del archivo
  - Detectar y validar las columnas requeridas
  - Normalizar y sanitizar los valores de cada fila
  - Construir la query de búsqueda según el ModosBusqueda configurado

Este módulo no importa nada de api/ — es lógica de negocio pura.

:author: BenjaminDTS
:version: 1.0.0
"""

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Iterator

from loguru import logger

from api.v1.schemas.job import ModosBusqueda, SearchConfig

# Columnas mínimas requeridas según el modo de búsqueda
_COLUMNAS_NOMBRE_MARCA = {"nombre", "marca"}
_COLUMNAS_EAN = {"ean"}
_COLUMNAS_COMUNES = {"codigo"}  # Requerida siempre para nombrar los archivos

# Caracteres prohibidos en los valores de búsqueda (previene injection en queries)
_PATRON_CARACTERES_INSEGUROS = re.compile(r'[<>"\'\\;]')

# Límites de seguridad
_MAX_FILAS = 10_000
_MAX_LONGITUD_CAMPO = 500


@dataclass
class Producto:
    """
    Representa un producto del CSV ya validado y normalizado.

    :author: BenjaminDTS
    """

    codigo: str
    nombre: str = ""
    marca: str = ""
    ean: str = ""
    query: str = ""          # Calculado por CsvParser según el modo
    fila_original: int = 0   # Número de fila del CSV (para trazabilidad de errores)
    datos_extra: dict[str, str] = field(default_factory=dict)


@dataclass
class ResultadoParseo:
    """
    Resultado devuelto por CsvParser.parsear().

    Contiene los productos válidos y los errores encontrados para
    que el caller pueda decidir si abortar o continuar con los válidos.

    :author: BenjaminDTS
    """

    productos: list[Producto] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)


class CsvParserError(Exception):
    """Excepción base para errores irrecuperables del parser (CSV inválido estructuralmente)."""


class CsvParser:
    """
    Parsea y valida un CSV de inventario de productos.

    Uso:
        parser = CsvParser(config)
        resultado = parser.parsear(contenido_csv_string)

    :author: BenjaminDTS
    """

    def __init__(self, config: SearchConfig) -> None:
        """
        Inicializa el parser con la configuración de búsqueda del job.

        Args:
            config: SearchConfig con el modo y parámetros de búsqueda.
        """
        self._config = config

    def parsear(self, contenido: str) -> ResultadoParseo:
        """
        Parsea el contenido CSV y devuelve productos validados y errores.

        Args:
            contenido: string con el contenido completo del archivo CSV.

        Returns:
            ResultadoParseo con la lista de productos válidos y los errores encontrados.

        Raises:
            CsvParserError: si el CSV está vacío, tiene formato inválido o
                            faltan columnas obligatorias.
        """
        if not contenido or not contenido.strip():
            raise CsvParserError("El archivo CSV está vacío.")

        reader = self._crear_reader(contenido)

        # Leer cabeceras
        try:
            cabeceras_raw = next(reader)
        except StopIteration as exc:
            raise CsvParserError("El CSV no contiene filas.") from exc

        cabeceras = {col.strip().lower() for col in cabeceras_raw}
        self._validar_columnas(cabeceras)

        resultado = ResultadoParseo()
        col_map = {col.strip().lower(): idx for idx, col in enumerate(cabeceras_raw)}

        for num_fila, fila in enumerate(reader, start=2):
            if num_fila > _MAX_FILAS + 1:
                resultado.errores.append(
                    f"El CSV supera el límite de {_MAX_FILAS} filas. "
                    "Las filas adicionales fueron ignoradas."
                )
                break

            try:
                producto = self._parsear_fila(fila, col_map, num_fila)
                resultado.productos.append(producto)
            except ValueError as exc:
                resultado.errores.append(str(exc))
                logger.warning(
                    "Fila inválida en CSV",
                    extra={"fila": num_fila, "detalle": str(exc)},
                )

        logger.info(
            "CSV parseado",
            extra={
                "productos_validos": len(resultado.productos),
                "errores": len(resultado.errores),
                "modo": self._config.modo.value,
            },
        )
        return resultado

    # ── Métodos privados ──────────────────────────────────────────────────────

    def _crear_reader(self, contenido: str) -> Iterator[list[str]]:
        """
        Crea un csv.reader detectando automáticamente el delimitador.

        Args:
            contenido: string con el CSV completo.

        Returns:
            Iterator de filas como listas de strings.

        Raises:
            CsvParserError: si el formato no puede detectarse.
        """
        try:
            dialect = csv.Sniffer().sniff(contenido[:4096], delimiters=",;\t|")
        except csv.Error:
            # Si el sniffer falla, asumir coma como delimitador estándar
            dialect = csv.excel

        return csv.reader(io.StringIO(contenido), dialect=dialect)

    def _validar_columnas(self, cabeceras: set[str]) -> None:
        """
        Valida que el CSV contiene las columnas requeridas para el modo configurado.

        Args:
            cabeceras: conjunto de nombres de columna en minúsculas.

        Raises:
            CsvParserError: si faltan columnas obligatorias.
        """
        if not _COLUMNAS_COMUNES.issubset(cabeceras):
            faltantes = _COLUMNAS_COMUNES - cabeceras
            raise CsvParserError(
                f"Columna(s) obligatoria(s) no encontrada(s): {', '.join(faltantes)}. "
                "El CSV debe incluir la columna 'codigo' en todos los modos."
            )

        if self._config.modo == ModosBusqueda.EAN:
            if not _COLUMNAS_EAN.issubset(cabeceras):
                raise CsvParserError(
                    "El modo EAN requiere la columna 'ean' en el CSV."
                )
        elif self._config.modo == ModosBusqueda.NOMBRE_MARCA:
            if not _COLUMNAS_NOMBRE_MARCA.issubset(cabeceras):
                faltantes = _COLUMNAS_NOMBRE_MARCA - cabeceras
                raise CsvParserError(
                    f"El modo NOMBRE_MARCA requiere las columnas: "
                    f"{', '.join(faltantes)}."
                )

    def _parsear_fila(
        self,
        fila: list[str],
        col_map: dict[str, int],
        num_fila: int,
    ) -> Producto:
        """
        Convierte una fila del CSV en un objeto Producto validado.

        Args:
            fila: lista de valores de la fila.
            col_map: mapa de nombre_columna → índice.
            num_fila: número de fila en el CSV (para mensajes de error).

        Returns:
            Producto validado y normalizado.

        Raises:
            ValueError: si la fila tiene datos inválidos o el código está vacío.
        """
        def _obtener(columna: str, obligatorio: bool = False) -> str:
            idx = col_map.get(columna)
            if idx is None or idx >= len(fila):
                if obligatorio:
                    raise ValueError(
                        f"Fila {num_fila}: columna '{columna}' no encontrada."
                    )
                return ""
            return self._sanitizar(fila[idx])

        codigo = _obtener("codigo", obligatorio=True)
        if not codigo:
            raise ValueError(f"Fila {num_fila}: el campo 'codigo' no puede estar vacío.")

        nombre = _obtener("nombre")
        marca = _obtener("marca")
        ean = _obtener("ean")

        # Datos extra: cualquier columna no estándar se preserva para exportación
        columnas_conocidas = {"codigo", "nombre", "marca", "ean"}
        datos_extra = {
            col: self._sanitizar(fila[idx])
            for col, idx in col_map.items()
            if col not in columnas_conocidas and idx < len(fila)
        }

        producto = Producto(
            codigo=codigo,
            nombre=nombre,
            marca=marca,
            ean=ean,
            fila_original=num_fila,
            datos_extra=datos_extra,
        )
        producto.query = self._construir_query(producto)
        return producto

    def _construir_query(self, producto: Producto) -> str:
        """
        Construye la query de búsqueda de imágenes para un producto.

        Args:
            producto: producto con sus datos ya normalizados.

        Returns:
            String con la query lista para enviar al motor de búsqueda.

        Raises:
            ValueError: si el modo es PERSONALIZADO y no hay plantilla de query.
        """
        modo = self._config.modo

        if modo == ModosBusqueda.EAN:
            if not producto.ean:
                raise ValueError(
                    f"Fila {producto.fila_original}: modo EAN pero el campo 'ean' está vacío."
                )
            return producto.ean

        if modo == ModosBusqueda.NOMBRE_MARCA:
            partes = [p for p in [producto.nombre, producto.marca] if p]
            return " ".join(partes)

        if modo == ModosBusqueda.PERSONALIZADO:
            plantilla = self._config.query_personalizada
            if not plantilla:
                raise ValueError(
                    "Modo PERSONALIZADO activo pero query_personalizada no está definida."
                )
            return plantilla.format(
                nombre=producto.nombre,
                marca=producto.marca,
                ean=producto.ean,
                codigo=producto.codigo,
            )

        # Caso imposible si ModosBusqueda está bien definido, pero lo manejamos
        raise ValueError(f"Modo de búsqueda desconocido: {modo}")

    @staticmethod
    def _sanitizar(valor: str) -> str:
        """
        Normaliza y sanitiza un valor de celda CSV.

        Elimina espacios extra y caracteres que podrían inyectarse en queries
        o en nombres de archivo. No modifica el contenido legítimo.

        Args:
            valor: string crudo de la celda.

        Returns:
            String limpio y truncado al límite máximo.
        """
        limpio = valor.strip()
        limpio = _PATRON_CARACTERES_INSEGUROS.sub("", limpio)
        return limpio[:_MAX_LONGITUD_CAMPO]
