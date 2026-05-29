"""
Utilidades CSV compartidas entre los servicios de integración.

Provee decodificación de bytes y detección automática de delimitadores
para archivos CSV con distintos encodings y formatos de separación.

:author: BenjaminDTS
:version: 1.0.0
"""

import csv


def decode_csv(content: bytes) -> str:
    """Decodifica bytes CSV intentando UTF-8 con BOM y latin-1 como fallback.

    Args:
        content: contenido binario del CSV.

    Returns:
        Cadena de texto decodificada.

    Raises:
        UnicodeDecodeError: si ningún encoding consigue decodificar el contenido.
    """
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def detect_delimiter(text: str) -> str:
    """Detecta el delimitador CSV priorizando ; y , sobre tabulador y pipe.

    Usa csv.Sniffer primero; si falla cuenta ocurrencias en la primera línea.

    Args:
        text: contenido CSV como cadena de texto.

    Returns:
        Carácter delimitador detectado. Por defecto ',' si no se puede determinar.
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
