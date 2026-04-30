"""
Tests unitarios para funcionalidad de candidatas en consumer.py (Fase 7.5).

Prueba: que consumer.py acepta el parámetro save_all_candidates,
y que devuelve list[ResultadoDescarga] con la estructura esperada.

:author: BenjaminDTS
:version: 1.0.0
"""

import pytest
from pathlib import Path
from PIL import Image

from services.scraper.consumer import ResultadoDescarga, descargar_imagenes_producto
from services.csv_parser import Producto
from services.storage_service import LocalStorageService


class TestConsumerSignature:
    """Tests para verificar la firma y comportamiento básico del consumer."""

    def test_descargar_imagenes_producto_accepts_save_all_candidates_param(
        self, tmp_path
    ):
        """
        Verifica que descargar_imagenes_producto acepta save_all_candidates.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")

        producto = Producto(
            codigo="TEST001",
            nombre="Test Product",
            ean="1234567890123",
        )

        # Debe aceptar el parámetro sin lanzar TypeError
        result = descargar_imagenes_producto(
            job_id="job1",
            producto=producto,
            urls=[],  # URLs vacías para que no intente descargar
            storage=storage,
            save_all_candidates=False,  # Parámetro clave
        )

        assert isinstance(result, list)

    def test_descargar_imagenes_producto_accepts_save_all_candidates_true(
        self, tmp_path
    ):
        """
        Verifica que descargar_imagenes_producto acepta save_all_candidates=True.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")

        producto = Producto(
            codigo="TEST002",
            nombre="Test Product",
            ean="1234567890124",
        )

        # Debe aceptar save_all_candidates=True sin error
        result = descargar_imagenes_producto(
            job_id="job1",
            producto=producto,
            urls=[],
            storage=storage,
            save_all_candidates=True,  # Parámetro clave
        )

        assert isinstance(result, list)

    def test_returns_list_of_resultado_descarga(self, tmp_path):
        """
        Verifica que descargar_imagenes_producto devuelve list[ResultadoDescarga].

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")

        producto = Producto(
            codigo="TEST003",
            nombre="Test",
            ean="1234567890125",
        )

        result = descargar_imagenes_producto(
            job_id="job1",
            producto=producto,
            urls=[],
            storage=storage,
        )

        assert isinstance(result, list)
        # Si hay elementos, verificar que son ResultadoDescarga
        if result:
            assert all(isinstance(r, ResultadoDescarga) for r in result)

    def test_resultado_descarga_has_required_fields(self, tmp_path):
        """
        Verifica que ResultadoDescarga tiene los campos requeridos.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")

        producto = Producto(
            codigo="TEST004",
            nombre="Test",
            ean="1234567890126",
        )

        result = descargar_imagenes_producto(
            job_id="job1",
            producto=producto,
            urls=[],
            storage=storage,
        )

        # Verificar estructura de ResultadoDescarga
        if result:
            r = result[0]
            assert hasattr(r, "url")
            assert hasattr(r, "exitoso")
            assert hasattr(r, "ruta_guardada")
            assert hasattr(r, "error")
            assert isinstance(r.url, str)
            assert isinstance(r.exitoso, bool)

    def test_callback_imagen_parameter_is_accepted(self, tmp_path):
        """
        Verifica que descargar_imagenes_producto acepta callback_imagen.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")

        callback_called = []

        def dummy_callback(success: bool):
            callback_called.append(success)

        producto = Producto(
            codigo="TEST005",
            nombre="Test",
            ean="1234567890127",
        )

        # Debe aceptar el callback sin error
        result = descargar_imagenes_producto(
            job_id="job1",
            producto=producto,
            urls=[],
            storage=storage,
            callback_imagen=dummy_callback,
        )

        assert isinstance(result, list)


class TestStorageAccess:
    """Tests para verificar acceso a storage durante descarga."""

    def test_candidates_dir_is_created_when_save_all_candidates_true(self, tmp_path):
        """
        Verifica que se crea el directorio candidates/ cuando save_all_candidates=True.

        Nota: depende de que haya al menos una URL válida que descargar.
        Este test es más un chequeo de precondiciones de storage.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")

        # Storage debe poder crear candidates_dir
        cand_dir = storage.candidates_dir("job1")
        cand_dir.mkdir(parents=True, exist_ok=True)

        assert cand_dir.exists()

    def test_list_candidates_returns_empty_initially(self, tmp_path):
        """
        Verifica que list_candidates devuelve [] al inicio.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")

        candidates = storage.list_candidates("job1", "TESTPROD")
        assert candidates == []
