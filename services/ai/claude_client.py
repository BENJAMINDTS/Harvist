"""
Cliente de IA para generación de descripciones.

Soporta dos proveedores configurables mediante AI_PROVIDER:
  - 'anthropic': Claude API (requiere créditos en platform.anthropic.com)
  - 'groq': API gratuita compatible con OpenAI (console.groq.com)

:author: Carlitos6712
:version: 2.0.0
"""

from __future__ import annotations

from loguru import logger


class ClaudeClient:
    """
    Cliente unificado para generación de texto con IA.

    Abstrae el proveedor subyacente (Anthropic o Groq) exponiendo
    una única interfaz `completar(prompt)` al resto del sistema.

    :author: Carlitos6712
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int,
        timeout: int,
        max_retries: int,
        provider: str = "anthropic",
    ) -> None:
        """
        Inicializa el cliente con el proveedor y parámetros indicados.

        Args:
            api_key: clave de API del proveedor (nunca loguear).
            model: identificador del modelo a usar.
            max_tokens: límite de tokens de respuesta por llamada.
            timeout: segundos máximos de espera por llamada HTTP.
            max_retries: número máximo de reintentos ante errores transitorios.
            provider: 'anthropic' o 'groq'.
        """
        self._model = model
        self._max_tokens = max_tokens
        self._provider = provider

        if provider == "groq":
            try:
                from openai import OpenAI  # noqa: PLC0415
            except ImportError as exc:
                raise ImportError(
                    "El paquete 'openai' no está instalado. "
                    "Ejecuta: pip install openai"
                ) from exc
            self._client = OpenAI(
                api_key=api_key,
                base_url="https://api.groq.com/openai/v1",
                timeout=float(timeout),
                max_retries=max_retries,
            )
        else:
            try:
                import anthropic  # noqa: PLC0415
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

        logger.debug(
            "ClaudeClient inicializado",
            extra={"provider": provider, "model": model, "max_tokens": max_tokens},
        )

    def completar(self, prompt: str) -> str:
        """
        Envía un prompt al modelo y devuelve el texto generado.

        Args:
            prompt: texto del mensaje a enviar al modelo.

        Returns:
            Texto de respuesta generado por el modelo.

        Raises:
            Exception: si la API devuelve un error no recuperable.
        """
        if self._provider == "groq":
            return self._completar_openai(prompt)
        return self._completar_anthropic(prompt)

    # ------------------------------------------------------------------
    # Helpers privados por proveedor
    # ------------------------------------------------------------------

    def _completar_openai(self, prompt: str) -> str:
        """
        Llama a la API compatible con OpenAI (Groq) y devuelve el texto.

        Args:
            prompt: texto del mensaje.

        Returns:
            Texto de respuesta del modelo.
        """
        try:
            respuesta = self._client.chat.completions.create(
                model=self._model,
                max_tokens=self._max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            texto: str = respuesta.choices[0].message.content or ""
            logger.debug(
                "Respuesta de Groq recibida",
                extra={
                    "model": self._model,
                    "input_tokens": getattr(respuesta.usage, "prompt_tokens", 0),
                    "output_tokens": getattr(respuesta.usage, "completion_tokens", 0),
                },
            )
            return texto.strip()
        except Exception as exc:
            logger.error(
                "Error en llamada a Groq API",
                exc_info=exc,
                extra={"model": self._model, "error": str(exc)},
            )
            raise

    def _completar_anthropic(self, prompt: str) -> str:
        """
        Llama a la API de Anthropic (Claude) y devuelve el texto.

        Args:
            prompt: texto del mensaje.

        Returns:
            Texto de respuesta del modelo.
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
                extra={
                    "model": self._model,
                    "status_code": getattr(exc, "status_code", None),
                    "error_body": getattr(exc, "body", None),
                    "error_message": str(exc),
                },
            )
            raise
