"""
Modelos compartidos y utilidades de validación para el pipeline de marcas.

Este módulo es el punto de entrada único para el modelo ``BrandResult`` y para
las funciones de validación de EAN. Todos los demás módulos del pipeline de
marcas (brand_cache, brand_scraper, brand_pipeline, …) deben importar
``BrandResult`` DESDE AQUÍ para evitar importaciones circulares.

:author: BenjaminDTS
:version: 2.0.0
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class BrandResult(BaseModel):
    """
    Resultado de la resolución EAN → marca para un producto.

    Modelo Pydantic inmutable que viaja por todas las capas del pipeline de
    marcas: desde la caché GS1 hasta el fallback de búsqueda web, pasando por
    las APIs públicas de Open*Facts y UPC Item DB.

    confidence refleja cuán fiable es el dato:
      - ``"high"``   → dato estructurado de GS1 o de una base de datos pública
                        (Open*Facts, UPC Item DB).
      - ``"medium"`` → inferido de ≥2 títulos de SERP concordantes.
      - ``"low"``    → inferido de un único título de SERP.

    :author: BenjaminDTS
    """

    ean_code: str = Field(description="EAN del producto resuelto.")
    brand_name: str | None = Field(
        default=None,
        description="Nombre de la marca detectada.",
    )
    manufacturer: str | None = Field(
        default=None,
        description="Nombre del fabricante (puede diferir de la marca).",
    )
    source: Literal[
        "cache_gs1",
        "open_data_api",
        "google_dorking",
        "bing_search",
        "not_found",
        "ean_invalido",
    ] = Field(description="Fuente que resolvió el EAN.")
    confidence: Literal["high", "medium", "low"] = Field(
        default="low",
        description=(
            "Confianza en el resultado: "
            "high=GS1/API, medium=2+ títulos web, low=1 título web."
        ),
    )
    resolved_at: datetime = Field(default_factory=datetime.utcnow)


# ── Pesos del algoritmo Módulo 10 (EAN-13 / GS1) ─────────────────────────────
# Posición par (0-indexed desde la izquierda) → peso 1; posición impar → peso 3.
# Equivale al esquema estándar GS1: [1, 3, 1, 3, …] aplicado a los primeros
# N-1 dígitos, donde N es la longitud total del código de barras.
_PESO_POSICION: tuple[int, int] = (1, 3)

# Longitudes de código de barras aceptadas por el estándar GS1
_LONGITUDES_VALIDAS: frozenset[int] = frozenset({8, 12, 13, 14})


def validate_ean_checksum(ean: str) -> bool:
    """
    Valida el dígito de control de un EAN mediante el algoritmo Módulo 10 (Luhn).

    Soporta EAN-8, EAN-13, UPC-A (12 dígitos) y EAN-14. Nunca lanza excepción:
    cualquier entrada no numérica o de longitud incorrecta devuelve False.

    El algoritmo GS1 Módulo 10 calcula el dígito de control así:
      1. Para cada dígito en posición par 0-indexed desde la izquierda se
         aplica peso 1; para las posiciones impares, peso 3.
         (El último dígito —el de control— queda excluido del sumatorio.)
      2. Se suma el producto de cada dígito por su peso.
      3. El dígito de control esperado es ``(10 - (suma % 10)) % 10``.
      4. Si coincide con el último dígito del código, el EAN es válido.

    Args:
        ean: código de barras como string (puede tener espacios que se eliminan).

    Returns:
        True si el EAN es válido y su dígito de control coincide,
        False en caso contrario.
    """
    # Eliminar blancos antes de cualquier comprobación
    ean = ean.strip()

    # Rechazar entradas no numéricas o con longitud fuera del estándar GS1
    if not ean.isdigit() or len(ean) not in _LONGITUDES_VALIDAS:
        return False

    digitos = [int(c) for c in ean]
    cuerpo = digitos[:-1]           # Todos los dígitos excepto el de control
    check_digit_real = digitos[-1]

    # Sumar cada dígito del cuerpo multiplicado por su peso posicional GS1
    total = sum(d * _PESO_POSICION[i % 2] for i, d in enumerate(cuerpo))

    check_digit_esperado = (10 - (total % 10)) % 10
    return check_digit_esperado == check_digit_real


def longest_prefix_match(ean: str, prefixes: dict[str, str]) -> str | None:
    """
    Encuentra el prefijo más largo del EAN que tenga coincidencia en el diccionario.

    Prueba subcadenas de longitud 10 → 6 dígitos (de más específico a más general)
    y devuelve la primera coincidencia. Esto evita falsos positivos por solapamiento
    (p. ej. ``'841303'`` coincidiría tanto en ``'8413037'`` como en ``'841303'``,
    pero ``'8413037'`` es más específico y tiene prioridad por orden de búsqueda
    descendente).

    Args:
        ean: código EAN de 8-14 dígitos (solo dígitos, ya validado).
        prefixes: diccionario ``{prefijo: valor}`` donde las claves son
            subcadenas del EAN.

    Returns:
        El valor asociado al prefijo más largo encontrado,
        o ``None`` si no hay coincidencia.
    """
    # Recorre longitudes de prefijo de mayor a menor para priorizar coincidencias
    # más específicas: un prefijo de 10 dígitos identifica a un fabricante con
    # más precisión que uno de 6, por lo que se comprueba primero.
    for length in range(10, 5, -1):
        candidate = ean[:length]
        if candidate in prefixes:
            return prefixes[candidate]
    return None
