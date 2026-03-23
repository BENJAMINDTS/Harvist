"""
Cliente de IA para generación de descripciones con rotación automática de modelos.

Soporta dos proveedores configurables mediante AI_PROVIDER:
  - 'anthropic': Claude API (requiere créditos en platform.anthropic.com)
  - 'groq': API gratuita (console.groq.com) con rotación automática de modelos
            si uno es retirado (400/404) o agota su cuota diaria (TPD).

:author: Carlitos6712
:version: 3.0.0
"""

from __future__ import annotations

import time

from loguru import logger

# Modelos Groq gratuitos en orden de preferencia.
# Si el modelo activo falla por TPD o deprecación, se rota al siguiente.
GROQ_MODELOS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
    "deepseek-r1-distill-llama-70b",
]

# Palabras clave en el mensaje de error que indican que hay que rotar de modelo
_PALABRAS_ROTACION = {"tpd", "tokens per day", "decommissioned", "model_not_found"}


class ClaudeClient:
    """
    Cliente unificado para generación de texto con IA.

    Cuando el proveedor es 'groq', implementa rotación automática de modelos:
    - Error 400/404 o modelo retirado → cambia al siguiente modelo de la lista.
    - Error 429 (rate limit por minuto) → espera 15 s y reintenta mismo modelo.
    - Todos los modelos agotados → lanza RuntimeError.

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
            model: modelo inicial. Para Groq actúa como primer candidato de la lista.
            max_tokens: límite de tokens de respuesta por llamada.
            timeout: segundos máximos de espera por llamada HTTP.
            max_retries: número máximo de reintentos ante errores transitorios.
            provider: 'anthropic' o 'groq'.
        """
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

            # Construir lista con el modelo configurado primero, luego los demás
            lista = [model] + [m for m in GROQ_MODELOS if m != model]
            self._modelos_groq: list[str] = lista
            self._indice_modelo: int = 0

            self._client = OpenAI(
                api_key=api_key,
                base_url="https://api.groq.com/openai/v1",
                timeout=float(timeout),
                max_retries=0,  # Los reintentos los gestionamos nosotros
            )
            logger.debug(
                "ClaudeClient (Groq) inicializado",
                extra={"model": model, "max_tokens": max_tokens,
                       "modelos_disponibles": len(self._modelos_groq)},
            )

        else:
            try:
                import anthropic  # noqa: PLC0415
            except ImportError as exc:
                raise ImportError(
                    f"No se pudo importar 'anthropic': {exc}. "
                    "Ejecuta: pip install anthropic==0.49.0"
                ) from exc

            self._model = model
            self._client = anthropic.Anthropic(
                api_key=api_key,
                timeout=float(timeout),
                max_retries=max_retries,
            )
            logger.debug(
                "ClaudeClient (Anthropic) inicializado",
                extra={"model": model, "max_tokens": max_tokens},
            )

    def completar(self, prompt: str) -> str:
        """
        Envía un prompt al modelo y devuelve el texto generado.

        Args:
            prompt: texto del mensaje a enviar al modelo.

        Returns:
            Texto de respuesta generado por el modelo.

        Raises:
            RuntimeError: si Groq agota todos los modelos disponibles.
            Exception: si Anthropic devuelve un error no recuperable.
        """
        if self._provider == "groq":
            return self._completar_groq(prompt)
        return self._completar_anthropic(prompt)

    # ------------------------------------------------------------------
    # Helpers privados por proveedor
    # ------------------------------------------------------------------

    def _completar_groq(self, prompt: str) -> str:
        """
        Llama a Groq con rotación automática de modelos ante fallos.

        Lógica de rotación (igual que en el pipeline de referencia):
        - TPD / modelo retirado (400/404) → siguiente modelo de la lista.
        - Rate limit (429) → espera 15 s, reintenta mismo modelo (máx 3 veces).
        - Error desconocido → propaga la excepción.

        Args:
            prompt: texto del mensaje.

        Returns:
            Texto JSON de respuesta.
        """
        while self._indice_modelo < len(self._modelos_groq):
            modelo_actual = self._modelos_groq[self._indice_modelo]
            intentos_rate = 0
            max_intentos_rate = 3

            while intentos_rate < max_intentos_rate:
                try:
                    respuesta = self._client.chat.completions.create(
                        model=modelo_actual,
                        max_tokens=self._max_tokens,
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"},
                        temperature=0.3,
                    )
                    texto: str = respuesta.choices[0].message.content or ""
                    logger.debug(
                        "Respuesta de Groq recibida",
                        extra={
                            "model": modelo_actual,
                            "input_tokens": getattr(respuesta.usage, "prompt_tokens", 0),
                            "output_tokens": getattr(respuesta.usage, "completion_tokens", 0),
                        },
                    )
                    return texto.strip()

                except Exception as exc:
                    error_msg = str(exc).lower()

                    # Rotación: modelo retirado o cuota diaria agotada
                    if (
                        any(k in error_msg for k in _PALABRAS_ROTACION)
                        or "400" in error_msg
                        or "404" in error_msg
                    ):
                        self._indice_modelo += 1
                        siguiente = (
                            self._modelos_groq[self._indice_modelo]
                            if self._indice_modelo < len(self._modelos_groq)
                            else "ninguno"
                        )
                        logger.warning(
                            "Modelo Groq no disponible, rotando",
                            extra={"modelo_caído": modelo_actual, "siguiente": siguiente},
                        )
                        break  # sale del bucle rate-limit y prueba el siguiente modelo

                    # Rate limit por minuto: esperar y reintentar
                    elif "429" in error_msg or "rate_limit" in error_msg:
                        intentos_rate += 1
                        logger.warning(
                            "Rate limit Groq, esperando 15 s",
                            extra={"modelo": modelo_actual, "intento": intentos_rate},
                        )
                        time.sleep(15)

                    # Error desconocido: propagar
                    else:
                        logger.error(
                            "Error desconocido en llamada a Groq",
                            exc_info=exc,
                            extra={"model": modelo_actual, "error": str(exc)},
                        )
                        raise

        raise RuntimeError(
            "Se agotaron todos los modelos de Groq disponibles. "
            "Cuotas diarias (TPD) alcanzadas. Inténtalo mañana o añade créditos en Anthropic."
        )

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
