"""
Servicio de generación de descripciones SEO de producto usando Claude API.

Procesa los productos en batch (varios por llamada) para reducir latencia y coste.
La respuesta de Claude es JSON estructurado con: corta, larga, keywords y meta_description.

El prompt es configurable por tipo de tienda (CLAUDE_STORE_TYPE) o mediante un archivo
de plantilla externo (CLAUDE_PROMPT_FILE) con los placeholders {store_type} y {productos_json}.

:author: Carlitos6712
:version: 2.0.0
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from services.ai.claude_client import ClaudeClient
from services.csv_parser import Producto


# ---------------------------------------------------------------------------
# Prompt por defecto (configurable vía CLAUDE_STORE_TYPE o CLAUDE_PROMPT_FILE)
# ---------------------------------------------------------------------------

_PROMPT_DEFAULT = (
    "Actúa como un copywriter experto en SEO y {store_type}. "
    "Genera descripciones optimizadas para buscadores (SEO) para los siguientes productos, "
    "teniendo muy en cuenta su 'categoria':\n\n"
    "{productos_json}\n\n"
    "REGLAS POR PRODUCTO:\n"
    "1. Corta: Gancho comercial de máximo 10 palabras. Debe incluir de forma natural "
    "   la keyword principal de alto volumen de búsqueda para el producto.\n"
    "2. Larga: Texto persuasivo de más de 60 palabras. Debe incluir de forma natural "
    "   entre 2 y 3 keywords secundarias (términos long-tail relacionados), "
    "   explicar los beneficios reales del producto, resolver una necesidad del cliente "
    "   e incluir una llamada a la acción implícita al final. "
    "   El texto completo debe estar optimizado para posicionar en Google.\n"
    "3. Si la categoría es '- Sin Departamento -', dedúcela por el nombre o descripción del producto.\n\n"
    "RESPONDE EXCLUSIVAMENTE EN JSON con esta estructura exacta, sin texto adicional:\n"
    "{{\"productos\": [{{"
    "\"id_interno\": \"...\", "
    "\"corta\": \"...\", "
    "\"larga\": \"...\""
    "}}]}}"
)


# ---------------------------------------------------------------------------
# Modelos de datos
# ---------------------------------------------------------------------------


@dataclass
class ResultadoDescripcion:
    """
    Resultado de la generación SEO para un producto.

    :author: Carlitos6712
    """

    codigo: str
    nombre: str
    marca: str
    categoria: str
    corta: str = ""
    larga: str = ""
    exitoso: bool = True
    error: str = ""


# ---------------------------------------------------------------------------
# Generador
# ---------------------------------------------------------------------------


class DescriptionGenerator:
    """
    Genera descripciones SEO de producto en batch usando la API de Claude.

    Envía varios productos por llamada para reducir latencia y coste de API.
    Parsea la respuesta JSON y mapea cada resultado a su producto por id_interno.

    :author: Carlitos6712
    """

    def __init__(
        self,
        client: ClaudeClient,
        store_type: str = "tiendas de mascotas",
        prompt_file: str = "",
        prompt_inline: str = "",
    ) -> None:
        """
        Inicializa el generador con el cliente Claude y la configuración de prompt.

        La prioridad de carga del template es:
        1. prompt_inline (enviado por el usuario desde el formulario)
        2. prompt_file (ruta a archivo .txt en el servidor)
        3. _PROMPT_DEFAULT (prompt SEO por defecto)

        Args:
            client: instancia de ClaudeClient lista para usar.
            store_type: tipo de tienda inyectado en el prompt.
            prompt_file: ruta a un archivo .txt con plantilla personalizada.
            prompt_inline: plantilla de prompt enviada directamente como string.
                           Tiene prioridad sobre prompt_file y el prompt por defecto.
        """
        self._client = client
        self._store_type = store_type

        if prompt_inline and "{productos_json}" in prompt_inline:
            self._prompt_template = prompt_inline
            logger.info("Prompt cargado desde el formulario del usuario")
        else:
            if prompt_inline:
                logger.warning(
                    "El prompt del usuario no contiene {productos_json}, usando prompt por defecto"
                )
            self._prompt_template = self._cargar_template(prompt_file)

    def generar_batch(self, productos: list[Producto]) -> list[ResultadoDescripcion]:
        """
        Genera descripciones SEO para un lote de productos en una sola llamada a Claude.

        Args:
            productos: lista de productos a procesar en este batch.

        Returns:
            Lista de ResultadoDescripcion en el mismo orden que los productos de entrada.
            Los productos para los que Claude no devuelva resultado se marcan con error.
        """
        if not productos:
            return []

        productos_input = [
            {
                "id_interno": p.codigo,
                "nombre": p.nombre or p.codigo,
                "marca": p.marca or "—",
                "categoria": p.categoria or "- Sin Departamento -",
            }
            for p in productos
        ]

        prompt = self._prompt_template.format(
            store_type=self._store_type,
            productos_json=json.dumps(productos_input, ensure_ascii=False, indent=2),
        )

        try:
            respuesta_raw = self._client.completar(prompt)
            resultados_claude = self._parsear_respuesta(respuesta_raw)
        except Exception as exc:
            logger.error(
                "Error en llamada batch a Claude",
                exc_info=exc,
                extra={"batch_size": len(productos)},
            )
            return [
                ResultadoDescripcion(
                    codigo=p.codigo,
                    nombre=p.nombre,
                    marca=p.marca,
                    categoria=p.categoria,
                    exitoso=False,
                    error=str(exc),
                )
                for p in productos
            ]

        # Mapear resultados por id_interno para preservar orden y detectar ausentes
        mapa: dict[str, dict] = {r["id_interno"]: r for r in resultados_claude}

        resultados: list[ResultadoDescripcion] = []
        for producto in productos:
            datos = mapa.get(producto.codigo)
            if datos is None:
                logger.warning(
                    "Claude no devolvió resultado para el producto",
                    extra={"codigo": producto.codigo},
                )
                resultados.append(
                    ResultadoDescripcion(
                        codigo=producto.codigo,
                        nombre=producto.nombre,
                        marca=producto.marca,
                        categoria=producto.categoria,
                        exitoso=False,
                        error="Sin resultado en la respuesta de Claude.",
                    )
                )
            else:
                resultados.append(
                    ResultadoDescripcion(
                        codigo=producto.codigo,
                        nombre=producto.nombre,
                        marca=producto.marca,
                        categoria=producto.categoria,
                        corta=datos.get("corta", ""),
                        larga=datos.get("larga", ""),
                        exitoso=True,
                    )
                )

        logger.info(
            "Batch de descripciones generado",
            extra={
                "batch_size": len(productos),
                "exitosos": sum(1 for r in resultados if r.exitoso),
            },
        )
        return resultados

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _cargar_template(self, prompt_file: str) -> str:
        """
        Carga el template de prompt desde archivo o devuelve el template por defecto.

        Args:
            prompt_file: ruta al archivo de template. Vacío = usar el por defecto.

        Returns:
            String del template con placeholders {store_type} y {productos_json}.
        """
        if not prompt_file:
            return _PROMPT_DEFAULT

        ruta = Path(prompt_file)
        if not ruta.exists():
            logger.warning(
                "CLAUDE_PROMPT_FILE no existe, usando prompt por defecto",
                extra={"path": prompt_file},
            )
            return _PROMPT_DEFAULT

        template = ruta.read_text(encoding="utf-8")
        if "{productos_json}" not in template:
            logger.warning(
                "El prompt file no contiene el placeholder {productos_json}, usando por defecto",
                extra={"path": prompt_file},
            )
            return _PROMPT_DEFAULT

        logger.info("Prompt cargado desde archivo", extra={"path": prompt_file})
        return template

    def _parsear_respuesta(self, respuesta_raw: str) -> list[dict]:
        """
        Parsea la respuesta JSON de Claude y extrae la lista de productos.

        Maneja el caso en que Claude envuelva el JSON en bloques de código markdown.

        Args:
            respuesta_raw: string de respuesta de Claude.

        Returns:
            Lista de dicts con los campos SEO por producto.

        Raises:
            ValueError: si la respuesta no es JSON válido o no tiene la estructura esperada.
        """
        texto = respuesta_raw.strip()

        # Limpiar bloques de código markdown si Claude los incluye
        if texto.startswith("```"):
            lineas = texto.splitlines()
            texto = "\n".join(
                l for l in lineas if not l.startswith("```")
            ).strip()

        try:
            datos = json.loads(texto)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Respuesta de Claude no es JSON válido: {exc}") from exc

        productos = datos.get("productos")
        if not isinstance(productos, list):
            raise ValueError(
                f"La respuesta JSON no contiene la clave 'productos' como lista. "
                f"Claves encontradas: {list(datos.keys())}"
            )

        return productos
