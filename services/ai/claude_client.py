"""
Cliente HTTP para la API de Anthropic Claude.

Envuelve el SDK oficial de Anthropic añadiendo logging estructurado.
Los reintentos y el timeout se configuran directamente en el cliente del SDK.

La API key nunca se loguea ni se expone en mensajes de error.

:author: Carlitos6712
:version: 1.0.0
"""

from __future__ import annotations

from loguru import logger


class ClaudeClient:
    """
    Cliente de la API de Anthropic Claude.

    Gestiona la conexión y los reintentos con el SDK oficial de Anthropic.
    El ciclo de vida del cliente (instanciación única por pipeline) es
    responsabilidad del llamador.

    :author: Carlitos6712
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int,
        timeout: int,
        max_retries: int,
    ) -> None:
        """
        Inicializa el cliente con los parámetros de configuración.

        Args:
            api_key: clave de API de Anthropic (secreto — no loguear nunca).
            model: identificador del modelo Claude a usar.
            max_tokens: límite de tokens de respuesta por llamada.
            timeout: segundos máximos de espera por llamada HTTP.
            max_retries: número máximo de reintentos ante errores transitorios.
        """
        try:
            import anthropic  # noqa: PLC0415 — import diferido intencionado
        except ImportError as exc:
            raise ImportError(
                f"No se pudo importar 'anthropic': {exc}. "
                "Ejecuta: pip install anthropic==0.49.0"
            ) from exc

        self._client = anthropic.Anthropic(
            api_key=api_key,
            timeout=float(timeout),
            max_retries=max_retries,
        )
        self._model = model
        self._max_tokens = max_tokens

        logger.debug(
            "ClaudeClient inicializado",
            extra={"model": model, "max_tokens": max_tokens, "max_retries": max_retries},
        )

    def completar(self, prompt: str) -> str:
        """
        Envía un prompt al modelo Claude y devuelve el texto generado.

        Args:
            prompt: texto del mensaje a enviar al modelo.

        Returns:
            Texto de respuesta generado por el modelo.

        Raises:
            anthropic.APIError: si la API devuelve un error no recuperable.
            anthropic.APITimeoutError: si la llamada supera el timeout configurado.
        """
        import anthropic  # noqa: PLC0415

        try:
            respuesta = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            texto: str = respuesta.content[0].text
            logger.debug(
                "Respuesta de Claude recibida",
                extra={
                    "model": self._model,
                    "input_tokens": respuesta.usage.input_tokens,
                    "output_tokens": respuesta.usage.output_tokens,
                },
            )
            return texto.strip()

        except anthropic.APITimeoutError as exc:
            logger.error(
                "Timeout en llamada a Claude API",
                exc_info=exc,
                extra={"model": self._model},
            )
            raise

        except anthropic.APIError as exc:
            logger.error(
                "Error en llamada a Claude API",
                exc_info=exc,
                extra={"model": self._model, "status_code": getattr(exc, "status_code", None)},
            )
            raise
