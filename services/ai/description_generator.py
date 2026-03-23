"""
Servicio de generación de descripciones de producto usando Claude API.

Recibe los datos normalizados de un producto (nombre, marca, EAN, categoría)
y devuelve una descripción de catálogo lista para exportar.

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from services.ai.claude_client import ClaudeClient
from services.csv_parser import Producto


_PROMPT_TEMPLATE = """\
Eres un redactor especializado en catálogos de e-commerce en español.

Genera una descripción comercial breve (máximo 120 palabras) para el siguiente producto.
La descripción debe ser atractiva, clara e informativa para un comprador online.
Responde ÚNICAMENTE con la descripción, sin título, sin encabezado ni explicaciones adicionales.

Datos del producto:
- Nombre: {nombre}
- Marca: {marca}
- EAN: {ean}
- Categoría: {categoria}
"""


@dataclass
class ResultadoDescripcion:
    """
    Resultado de generar la descripción de un producto.

    :author: Carlitos6712
    """

    codigo: str
    nombre: str
    marca: str
    descripcion: str
    exitoso: bool
    error: str = ""


class DescriptionGenerator:
    """
    Genera descripciones de producto usando la API de Claude.

    Usa un ClaudeClient inyectado para enviar el prompt y recibir el texto.
    Los errores de API se capturan producto a producto para no interrumpir
    el pipeline completo.

    :author: Carlitos6712
    """

    def __init__(self, client: ClaudeClient) -> None:
        """
        Inicializa el generador con un cliente Claude ya configurado.

        Args:
            client: instancia de ClaudeClient lista para usar.
        """
        self._client = client

    def generar(self, producto: Producto) -> ResultadoDescripcion:
        """
        Genera la descripción de catálogo para un producto.

        Args:
            producto: producto con sus datos ya normalizados.

        Returns:
            ResultadoDescripcion con la descripción generada o el error ocurrido.
        """
        prompt = _PROMPT_TEMPLATE.format(
            nombre=producto.nombre or producto.codigo,
            marca=producto.marca or "—",
            ean=producto.ean or "—",
            categoria=producto.categoria or "—",
        )

        try:
            descripcion = self._client.completar(prompt)
            logger.info(
                "Descripción generada",
                extra={"codigo": producto.codigo, "chars": len(descripcion)},
            )
            return ResultadoDescripcion(
                codigo=producto.codigo,
                nombre=producto.nombre,
                marca=producto.marca,
                descripcion=descripcion,
                exitoso=True,
            )

        except Exception as exc:
            logger.error(
                "Error al generar descripción para producto",
                exc_info=exc,
                extra={"codigo": producto.codigo},
            )
            return ResultadoDescripcion(
                codigo=producto.codigo,
                nombre=producto.nombre,
                marca=producto.marca,
                descripcion="",
                exitoso=False,
                error=str(exc),
            )
