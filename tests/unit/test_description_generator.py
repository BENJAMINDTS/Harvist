"""
Tests unitarios para el generador de descripciones SEO (Fase 6 + Fase 7).

Verifica:
- Generación batch de descripciones (corta, larga)
- Manejo de errores Groq
- Parsing JSON con/sin bloques markdown
- Nunca loguea GROQ_API_KEY

:author: BenjaminDTS
:version: 1.0.0
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from services.ai.claude_client import ClaudeClient
from services.ai.description_generator import DescriptionGenerator, ResultadoDescripcion
from services.csv_parser import Producto


class TestGenerarBatch:
    """Suite de tests para generar_batch()."""

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

    def test_generar_batch_retorna_descripciones(self, generator, mock_client, productos_sample):
        """Verifica que generar_batch retorna lista de ResultadoDescripcion."""
        mock_client.completar.return_value = json.dumps({
            "productos": [
                {
                    "id_interno": "PROD001",
                    "corta": "Alimento perros premium nutrición",
                    "larga": "Alimento completo para tu perro con vitaminas.",
                },
                {
                    "id_interno": "PROD002",
                    "corta": "Juguete Kong resistente",
                    "larga": "Juguete duradero para jugar y masticar.",
                },
            ]
        })

        resultados = generator.generar_batch(productos_sample)

        assert len(resultados) == 2
        assert all(isinstance(r, ResultadoDescripcion) for r in resultados)
        assert resultados[0].exitoso is True
        assert resultados[1].exitoso is True

    def test_generar_batch_retorna_lista_misma_longitud(self, generator, mock_client, productos_sample):
        """Verifica que retorna una lista con la misma longitud que entrada."""
        mock_client.completar.return_value = json.dumps({
            "productos": [
                {"id_interno": "PROD001", "corta": "Corta", "larga": "Larga"},
                {"id_interno": "PROD002", "corta": "Corta", "larga": "Larga"},
            ]
        })

        resultados = generator.generar_batch(productos_sample)

        assert len(resultados) == len(productos_sample)

    def test_generar_batch_maneja_lista_vacia(self, generator):
        """Verifica que maneja lista vacía sin llamar a Groq."""
        resultados = generator.generar_batch([])

        assert resultados == []

    def test_generar_batch_mapea_por_id_interno(self, generator, mock_client, productos_sample):
        """Verifica que resultados se mapean correctamente por id_interno."""
        mock_client.completar.return_value = json.dumps({
            "productos": [
                {
                    "id_interno": "PROD001",
                    "corta": "Descripción corta 001",
                    "larga": "Descripción larga 001",
                },
                {
                    "id_interno": "PROD002",
                    "corta": "Descripción corta 002",
                    "larga": "Descripción larga 002",
                },
            ]
        })

        resultados = generator.generar_batch(productos_sample)

        assert resultados[0].codigo == "PROD001"
        assert resultados[0].corta == "Descripción corta 001"
        assert resultados[1].codigo == "PROD002"
        assert resultados[1].corta == "Descripción corta 002"

    def test_generar_batch_marca_como_error_si_falta_resultado(self, generator, mock_client, productos_sample):
        """Verifica que producto sin resultado se marca con exitoso=False."""
        mock_client.completar.return_value = json.dumps({
            "productos": [
                {
                    "id_interno": "PROD001",
                    "corta": "Corta",
                    "larga": "Larga",
                },
                # PROD002 ausente
            ]
        })

        resultados = generator.generar_batch(productos_sample)

        assert resultados[0].exitoso is True
        assert resultados[1].exitoso is False
        assert "Sin resultado" in resultados[1].error

    def test_generar_batch_parsea_json_con_markdown(self, generator, mock_client, productos_sample):
        """Verifica que parsea JSON incluso si viene en bloque markdown."""
        mock_client.completar.return_value = "```json\n" + json.dumps({
            "productos": [
                {"id_interno": "PROD001", "corta": "Corta", "larga": "Larga"},
                {"id_interno": "PROD002", "corta": "Corta", "larga": "Larga"},
            ]
        }) + "\n```"

        resultados = generator.generar_batch(productos_sample)

        assert len(resultados) == 2
        assert resultados[0].exitoso is True

    def test_generar_batch_maneja_respuesta_json_invalida(self, generator, mock_client, productos_sample):
        """Verifica que errores JSON se manejan gracefully."""
        mock_client.completar.side_effect = Exception("JSON decode error")

        resultados = generator.generar_batch(productos_sample)

        assert len(resultados) == len(productos_sample)
        assert all(not r.exitoso for r in resultados)
        assert all("JSON decode error" in r.error for r in resultados)

    def test_generar_batch_preserva_datos_producto(self, generator, mock_client, productos_sample):
        """Verifica que datos de producto se preservan en resultado."""
        mock_client.completar.return_value = json.dumps({
            "productos": [
                {"id_interno": "PROD001", "corta": "Corta", "larga": "Larga"},
                {"id_interno": "PROD002", "corta": "Corta", "larga": "Larga"},
            ]
        })

        resultados = generator.generar_batch(productos_sample)

        assert resultados[0].nombre == "Alimento para perros Premium"
        assert resultados[0].marca == "Royal Canin"
        assert resultados[0].categoria == "Alimentos"
        assert resultados[1].nombre == "Juguete de goma resistente"

    def test_generar_batch_never_logs_api_key(self, generator, mock_client, productos_sample):
        """Verifica que GROQ_API_KEY nunca aparece en logs de error."""
        mock_client.completar.side_effect = Exception("API Key leaked in error")

        with patch("services.ai.description_generator.logger") as mock_logger:
            resultados = generator.generar_batch(productos_sample)

            # Buscar que no se logueó la API key en ningún error
            for call in mock_logger.error.call_args_list:
                logged_text = str(call)
                assert "gsk_" not in logged_text
                assert "GROQ_API_KEY" not in logged_text

    def test_generar_batch_llama_completar_una_vez(self, generator, mock_client, productos_sample):
        """Verifica que procesa múltiples productos en una sola llamada."""
        mock_client.completar.return_value = json.dumps({
            "productos": [
                {"id_interno": "PROD001", "corta": "Corta", "larga": "Larga"},
                {"id_interno": "PROD002", "corta": "Corta", "larga": "Larga"},
            ]
        })

        resultados = generator.generar_batch(productos_sample)

        assert mock_client.completar.call_count == 1

    def test_generar_batch_logra_batch_correcto(self, generator, mock_client):
        """Verifica que logging de batch es correcto."""
        productos = [
            Producto(codigo=f"P{i:03d}", nombre=f"Producto {i}", marca="TestMarca", categoria="Test")
            for i in range(5)
        ]

        mock_client.completar.return_value = json.dumps({
            "productos": [
                {"id_interno": f"P{i:03d}", "corta": f"Corta {i}", "larga": f"Larga {i}"}
                for i in range(5)
            ]
        })

        with patch("services.ai.description_generator.logger") as mock_logger:
            resultados = generator.generar_batch(productos)

            # Verificar que se loguea el batch size
            log_calls = mock_logger.info.call_args_list
            assert any("batch_size" in str(call) for call in log_calls)
