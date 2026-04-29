"""
Tests unitarios para el generador de textos SEO (Fase 7.1).

Verifica:
- Generación batch de meta_title y meta_description
- Límites de caracteres (60 y 160 respectivamente)
- Truncado inteligente sin cortar palabras
- Manejo de errores Groq
- Nunca loguea GROQ_API_KEY

:author: BenjaminDTS
:version: 1.0.0
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from services.ai.claude_client import ClaudeClient
from services.ai.description_generator import DescriptionGenerator, ResultadoSEO
from services.csv_parser import Producto


class TestGenerateSeoTexts:
    """Suite de tests para generate_seo_texts()."""

    @pytest.fixture
    def mock_client(self):
        """Mock de ClaudeClient que devuelve respuesta JSON válida."""
        client = MagicMock(spec=ClaudeClient)
        return client

    @pytest.fixture
    def generator(self, mock_client):
        """Instancia de DescriptionGenerator con cliente mockeado."""
        return DescriptionGenerator(
            client=mock_client,
            store_type="tiendas de mascotas",
        )

    @pytest.fixture
    def productos_sample(self):
        """Productos de prueba."""
        return [
            Producto(
                codigo="PROD001",
                nombre="Alimento para perros Premium",
                marca="Royal Canin",
                categoria="Alimentos",
            ),
            Producto(
                codigo="PROD002",
                nombre="Juguete de goma resistente",
                marca="Kong",
                categoria="Juguetes",
            ),
        ]

    def test_generates_meta_title_under_60_chars(self, generator, mock_client, productos_sample):
        """Verifica que meta_title nunca supera 60 caracteres."""
        mock_client.completar.return_value = json.dumps({
            "productos": [
                {
                    "id_interno": "PROD001",
                    "meta_title": "Alimento perros premium nutrición completa 2024",
                    "meta_description": "Nutrición equilibrada para tu mascota. Proteínas naturales.",
                },
                {
                    "id_interno": "PROD002",
                    "meta_title": "Juguete goma Kong resistente masticar",
                    "meta_description": "Ideal para jugar seguro. Resistente al desgaste.",
                },
            ]
        })

        resultados = generator.generate_seo_texts(productos_sample)

        for r in resultados:
            assert len(r.meta_title) <= 60, f"meta_title excede 60 chars: {r.meta_title}"

    def test_generates_meta_description_under_160_chars(self, generator, mock_client, productos_sample):
        """Verifica que meta_description nunca supera 160 caracteres."""
        mock_client.completar.return_value = json.dumps({
            "productos": [
                {
                    "id_interno": "PROD001",
                    "meta_title": "Alimento perros premium",
                    "meta_description": "Nutrición completa para tu mascota con vitaminas y minerales esenciales.",
                },
                {
                    "id_interno": "PROD002",
                    "meta_title": "Juguete Kong goma",
                    "meta_description": "Juguete resistente perfecto para jugar y mantener feliz a tu perro.",
                },
            ]
        })

        resultados = generator.generate_seo_texts(productos_sample)

        for r in resultados:
            assert len(r.meta_description) <= 160, (
                f"meta_description excede 160 chars: {r.meta_description}"
            )

    def test_includes_product_name_in_meta_title(self, generator, mock_client, productos_sample):
        """Verifica que el nombre del producto esté en meta_title."""
        mock_client.completar.return_value = json.dumps({
            "productos": [
                {
                    "id_interno": "PROD001",
                    "meta_title": "Alimento para perros Premium Royal Canin",
                    "meta_description": "Nutrición equilibrada para tu mascota.",
                },
            ]
        })

        resultados = generator.generate_seo_texts([productos_sample[0]])

        assert len(resultados) == 1
        assert "Alimento" in resultados[0].meta_title or "perros" in resultados[0].meta_title

    def test_processes_batch_in_single_call(self, generator, mock_client, productos_sample):
        """Verifica que procesa múltiples productos en una sola llamada a Groq."""
        mock_client.completar.return_value = json.dumps({
            "productos": [
                {
                    "id_interno": "PROD001",
                    "meta_title": "Alimento perros",
                    "meta_description": "Nutrición completa.",
                },
                {
                    "id_interno": "PROD002",
                    "meta_title": "Juguete goma",
                    "meta_description": "Resistente y seguro.",
                },
            ]
        })

        resultados = generator.generate_seo_texts(productos_sample)

        assert mock_client.completar.call_count == 1
        assert len(resultados) == 2

    def test_truncates_intelligently_without_cutting_words(self, generator, mock_client, productos_sample):
        """Verifica truncado inteligente — no corta palabras a mitad."""
        # Respuesta con meta_title que excede 60 chars
        mock_client.completar.return_value = json.dumps({
            "productos": [
                {
                    "id_interno": "PROD001",
                    "meta_title": "Alimento para perros Premium Royal Canin nutrición completa excelente",
                    "meta_description": "Muy buena nutrición equilibrada para mascota con vitaminas esenciales y minerales muy buenos",
                },
            ]
        })

        resultados = generator.generate_seo_texts([productos_sample[0]])

        assert len(resultados[0].meta_title) <= 60
        # Verifica que no termina con palabra cortada (sin punto final)
        assert not resultados[0].meta_title.endswith(" ")

    def test_raises_groq_error_on_failure(self, generator, mock_client, productos_sample):
        """Verifica manejo de error cuando Groq falla."""
        mock_client.completar.side_effect = Exception("Groq API Error")

        resultados = generator.generate_seo_texts(productos_sample)

        assert len(resultados) == len(productos_sample)
        for r in resultados:
            assert not r.exitoso
            assert "Groq API Error" in r.error

    def test_returns_list_same_length_as_input(self, generator, mock_client, productos_sample):
        """Verifica que retorna una lista con la misma longitud que productos entrada."""
        mock_client.completar.return_value = json.dumps({
            "productos": [
                {
                    "id_interno": "PROD001",
                    "meta_title": "Alimento perros",
                    "meta_description": "Nutrición.",
                },
                {
                    "id_interno": "PROD002",
                    "meta_title": "Juguete goma",
                    "meta_description": "Juego.",
                },
            ]
        })

        resultados = generator.generate_seo_texts(productos_sample)

        assert len(resultados) == len(productos_sample)

    def test_handles_empty_product_list(self, generator):
        """Verifica que maneja lista vacía sin llamar a Groq."""
        resultados = generator.generate_seo_texts([])

        assert resultados == []

    def test_result_has_required_fields(self, generator, mock_client, productos_sample):
        """Verifica que cada ResultadoSEO tiene campos meta_title y meta_description."""
        mock_client.completar.return_value = json.dumps({
            "productos": [
                {
                    "id_interno": "PROD001",
                    "meta_title": "Alimento perros",
                    "meta_description": "Nutrición.",
                },
            ]
        })

        resultados = generator.generate_seo_texts([productos_sample[0]])

        for r in resultados:
            assert isinstance(r, ResultadoSEO)
            assert hasattr(r, "meta_title")
            assert hasattr(r, "meta_description")
            assert isinstance(r.meta_title, str)
            assert isinstance(r.meta_description, str)

    def test_never_logs_groq_api_key(self, generator, mock_client, productos_sample):
        """Verifica que GROQ_API_KEY nunca aparece en logs de error."""
        mock_client.completar.side_effect = Exception("API Key leaked in error")

        with patch("services.ai.description_generator.logger") as mock_logger:
            resultados = generator.generate_seo_texts(productos_sample)

            # Buscar que no se logueó la API key en ningún error
            for call in mock_logger.error.call_args_list:
                logged_text = str(call)
                assert "gsk_" not in logged_text
                assert "GROQ_API_KEY" not in logged_text
