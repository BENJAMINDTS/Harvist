"""
Tests unitarios para el generador de traducciones (Fase 7.2).

Verifica:
- Traducción batch en una sola llamada a Claude
- Mapeo correcto de resultados por id_interno
- Manejo de productos con descripción fallida (no se traduce, se marca error)
- Manejo de errores cuando Claude falla
- Preservación del orden original de productos
- Lista vacía de entrada
- Campos requeridos en ResultadoTraduccion
- Nunca loguea GROQ_API_KEY

:author: BenjaminDTS
:version: 1.0.0
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from services.ai.claude_client import ClaudeClient
from services.ai.description_generator import (
    DescriptionGenerator,
    ResultadoDescripcion,
    ResultadoTraduccion,
)
from services.csv_parser import Producto


class TestTranslateDescriptions:
    """Suite de tests para translate_descriptions()."""

    @pytest.fixture
    def mock_client(self):
        """Mock de ClaudeClient que devuelve respuesta JSON válida."""
        return MagicMock(spec=ClaudeClient)

    @pytest.fixture
    def generator(self, mock_client):
        """Instancia de DescriptionGenerator con cliente mockeado."""
        return DescriptionGenerator(
            client=mock_client,
            store_type="tiendas de mascotas",
        )

    @pytest.fixture
    def productos_sample(self):
        """Productos de prueba con dos entradas."""
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

    @pytest.fixture
    def descripciones_exitosas(self):
        """Descripciones generadas exitosamente para ambos productos."""
        return [
            ResultadoDescripcion(
                codigo="PROD001",
                nombre="Alimento para perros Premium",
                marca="Royal Canin",
                categoria="Alimentos",
                corta="Nutrición premium para tu perro.",
                larga="Alimento completo y equilibrado para perros adultos.",
                exitoso=True,
            ),
            ResultadoDescripcion(
                codigo="PROD002",
                nombre="Juguete de goma resistente",
                marca="Kong",
                categoria="Juguetes",
                corta="Juguete resistente para masticar.",
                larga="Juguete de goma natural ideal para perros activos.",
                exitoso=True,
            ),
        ]

    def test_translates_batch_in_single_call(
        self, generator, mock_client, productos_sample, descripciones_exitosas
    ):
        """Verifica que procesa todos los productos en una sola llamada a Claude."""
        mock_client.completar.return_value = json.dumps({
            "productos": [
                {
                    "id_interno": "PROD001",
                    "descripcion_corta": "Premium nutrition for your dog.",
                    "descripcion_larga": "Complete balanced food for adult dogs.",
                    "keywords": "dog food, premium, nutrition",
                    "meta_description": "Premium dog food for adult dogs.",
                },
                {
                    "id_interno": "PROD002",
                    "descripcion_corta": "Resistant chew toy.",
                    "descripcion_larga": "Natural rubber toy ideal for active dogs.",
                    "keywords": "dog toy, chew, rubber",
                    "meta_description": "Durable chew toy for active dogs.",
                },
            ]
        })

        resultados = generator.translate_descriptions(
            productos=productos_sample,
            descripciones=descripciones_exitosas,
            idioma_destino="en",
        )

        assert mock_client.completar.call_count == 1
        assert len(resultados) == 2

    def test_returns_list_same_length_as_input(
        self, generator, mock_client, productos_sample, descripciones_exitosas
    ):
        """Verifica que la lista resultado tiene la misma longitud que la entrada."""
        mock_client.completar.return_value = json.dumps({
            "productos": [
                {
                    "id_interno": "PROD001",
                    "descripcion_corta": "Premium nutrition.",
                    "descripcion_larga": "Complete food.",
                    "keywords": "dog food",
                    "meta_description": "Dog food.",
                },
                {
                    "id_interno": "PROD002",
                    "descripcion_corta": "Chew toy.",
                    "descripcion_larga": "Rubber toy.",
                    "keywords": "toy",
                    "meta_description": "Toy.",
                },
            ]
        })

        resultados = generator.translate_descriptions(
            productos=productos_sample,
            descripciones=descripciones_exitosas,
            idioma_destino="fr",
        )

        assert len(resultados) == len(productos_sample)

    def test_result_has_required_fields(
        self, generator, mock_client, productos_sample, descripciones_exitosas
    ):
        """Verifica que cada ResultadoTraduccion tiene todos los campos requeridos."""
        mock_client.completar.return_value = json.dumps({
            "productos": [
                {
                    "id_interno": "PROD001",
                    "descripcion_corta": "Nutrition.",
                    "descripcion_larga": "Complete food.",
                    "keywords": "food",
                    "meta_description": "Dog food.",
                },
            ]
        })

        resultados = generator.translate_descriptions(
            productos=[productos_sample[0]],
            descripciones=[descripciones_exitosas[0]],
            idioma_destino="en",
        )

        r = resultados[0]
        assert isinstance(r, ResultadoTraduccion)
        assert hasattr(r, "codigo")
        assert hasattr(r, "descripcion_corta")
        assert hasattr(r, "descripcion_larga")
        assert hasattr(r, "keywords")
        assert hasattr(r, "meta_description")
        assert hasattr(r, "idioma")
        assert r.idioma == "en"

    def test_skips_failed_descriptions(
        self, generator, mock_client, productos_sample
    ):
        """Verifica que productos con descripción fallida se marcan como fallidos sin llamar a Claude."""
        descripciones_fallidas = [
            ResultadoDescripcion(
                codigo="PROD001",
                nombre="Alimento para perros Premium",
                marca="Royal Canin",
                categoria="Alimentos",
                exitoso=False,
                error="Error en Claude.",
            ),
            ResultadoDescripcion(
                codigo="PROD002",
                nombre="Juguete de goma resistente",
                marca="Kong",
                categoria="Juguetes",
                exitoso=False,
                error="Timeout.",
            ),
        ]

        resultados = generator.translate_descriptions(
            productos=productos_sample,
            descripciones=descripciones_fallidas,
            idioma_destino="en",
        )

        assert mock_client.completar.call_count == 0
        assert len(resultados) == 2
        for r in resultados:
            assert not r.exitoso

    def test_mixed_success_failure_preserves_order(
        self, generator, mock_client, productos_sample
    ):
        """Verifica que el orden original se preserva con productos mixtos (exitosos y fallidos)."""
        descripciones_mixtas = [
            ResultadoDescripcion(
                codigo="PROD001",
                nombre="Alimento para perros Premium",
                marca="Royal Canin",
                categoria="Alimentos",
                corta="Gancho.",
                larga="Texto largo.",
                exitoso=True,
            ),
            ResultadoDescripcion(
                codigo="PROD002",
                nombre="Juguete de goma resistente",
                marca="Kong",
                categoria="Juguetes",
                exitoso=False,
                error="Descripción fallida.",
            ),
        ]
        mock_client.completar.return_value = json.dumps({
            "productos": [
                {
                    "id_interno": "PROD001",
                    "descripcion_corta": "Premium hook.",
                    "descripcion_larga": "Long text.",
                    "keywords": "food",
                    "meta_description": "Dog food.",
                },
            ]
        })

        resultados = generator.translate_descriptions(
            productos=productos_sample,
            descripciones=descripciones_mixtas,
            idioma_destino="en",
        )

        assert len(resultados) == 2
        assert resultados[0].codigo == "PROD001"
        assert resultados[0].exitoso
        assert resultados[1].codigo == "PROD002"
        assert not resultados[1].exitoso

    def test_handles_empty_product_list(self, generator):
        """Verifica que maneja lista vacía sin llamar a Claude."""
        resultados = generator.translate_descriptions(
            productos=[],
            descripciones=[],
            idioma_destino="en",
        )

        assert resultados == []

    def test_raises_error_on_claude_failure(
        self, generator, mock_client, productos_sample, descripciones_exitosas
    ):
        """Verifica que cuando Claude falla, todos los productos se marcan con exitoso=False."""
        mock_client.completar.side_effect = Exception("Claude API Error")

        resultados = generator.translate_descriptions(
            productos=productos_sample,
            descripciones=descripciones_exitosas,
            idioma_destino="en",
        )

        assert len(resultados) == len(productos_sample)
        for r in resultados:
            assert not r.exitoso
            assert "Claude API Error" in r.error

    def test_missing_product_in_claude_response_marked_failed(
        self, generator, mock_client, productos_sample, descripciones_exitosas
    ):
        """Verifica que si Claude no devuelve un producto, se marca como fallido."""
        mock_client.completar.return_value = json.dumps({
            "productos": [
                {
                    "id_interno": "PROD001",
                    "descripcion_corta": "Premium nutrition.",
                    "descripcion_larga": "Complete food.",
                    "keywords": "dog",
                    "meta_description": "Dog food.",
                },
            ]
        })

        resultados = generator.translate_descriptions(
            productos=productos_sample,
            descripciones=descripciones_exitosas,
            idioma_destino="de",
        )

        assert len(resultados) == 2
        assert resultados[0].codigo == "PROD001"
        assert resultados[0].exitoso
        assert resultados[1].codigo == "PROD002"
        assert not resultados[1].exitoso

    def test_idioma_stored_in_resultado(
        self, generator, mock_client, productos_sample, descripciones_exitosas
    ):
        """Verifica que el idioma destino se almacena en cada ResultadoTraduccion."""
        mock_client.completar.return_value = json.dumps({
            "productos": [
                {
                    "id_interno": "PROD001",
                    "descripcion_corta": "Nutrition de qualité.",
                    "descripcion_larga": "Aliment complet pour chiens.",
                    "keywords": "nourriture chien",
                    "meta_description": "Nourriture premium pour chien.",
                },
                {
                    "id_interno": "PROD002",
                    "descripcion_corta": "Jouet résistant.",
                    "descripcion_larga": "Jouet en caoutchouc naturel.",
                    "keywords": "jouet chien",
                    "meta_description": "Jouet pour chien actif.",
                },
            ]
        })

        resultados = generator.translate_descriptions(
            productos=productos_sample,
            descripciones=descripciones_exitosas,
            idioma_destino="fr",
        )

        for r in resultados:
            assert r.idioma == "fr"

    def test_never_logs_api_key(
        self, generator, mock_client, productos_sample, descripciones_exitosas
    ):
        """Verifica que GROQ_API_KEY nunca aparece en logs de error."""
        mock_client.completar.side_effect = Exception("API Key leaked in error")

        with patch("services.ai.description_generator.logger") as mock_logger:
            generator.translate_descriptions(
                productos=productos_sample,
                descripciones=descripciones_exitosas,
                idioma_destino="en",
            )

            for call in mock_logger.error.call_args_list:
                logged_text = str(call)
                assert "gsk_" not in logged_text
                assert "GROQ_API_KEY" not in logged_text

    def test_successful_result_has_translated_content(
        self, generator, mock_client, productos_sample, descripciones_exitosas
    ):
        """Verifica que el contenido traducido se asigna correctamente a los campos."""
        mock_client.completar.return_value = json.dumps({
            "productos": [
                {
                    "id_interno": "PROD001",
                    "descripcion_corta": "Premium nutrition for your dog.",
                    "descripcion_larga": "Complete and balanced food for adult dogs.",
                    "keywords": "dog food, premium, adult",
                    "meta_description": "Premium dog food Royal Canin.",
                },
            ]
        })

        resultados = generator.translate_descriptions(
            productos=[productos_sample[0]],
            descripciones=[descripciones_exitosas[0]],
            idioma_destino="en",
        )

        r = resultados[0]
        assert r.exitoso
        assert r.descripcion_corta == "Premium nutrition for your dog."
        assert r.descripcion_larga == "Complete and balanced food for adult dogs."
        assert r.keywords == "dog food, premium, adult"
        assert r.meta_description == "Premium dog food Royal Canin."
