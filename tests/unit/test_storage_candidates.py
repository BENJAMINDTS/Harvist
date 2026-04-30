"""
Tests unitarios para funcionalidad de candidatas en storage_service.py (Fase 7.5).

Prueba: creación de rutas de candidatas, listado de índices, lectura de metadatos,
confirmación de selección y limpieza de directorios temporales.

:author: BenjaminDTS
:version: 1.0.0
"""

import pytest
from pathlib import Path
from PIL import Image

from services.storage_service import LocalStorageService


class TestStorageCandidatesDir:
    """Tests para manejo de directorios de candidatas."""

    def test_candidates_dir_returns_correct_path(self, tmp_path):
        """
        Verifica que candidates_dir devuelve la ruta esperada.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        result = storage.candidates_dir("job1")
        assert result == tmp_path / "job1" / "candidates"

    def test_candidates_dir_does_not_create_directory(self, tmp_path):
        """
        Verifica que candidates_dir NO crea el directorio (lazy evaluation).

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        cand_dir = storage.candidates_dir("job1")
        assert not cand_dir.exists()

    def test_candidate_path_returns_correct_filename(self, tmp_path):
        """
        Verifica que candidate_path devuelve la ruta con nombre correcto.

        Nombre esperado: {codigo}_candidate_{n}.jpg

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        result = storage.candidate_path("job1", "prod1", 0)
        assert result == tmp_path / "job1" / "candidates" / "prod1_candidate_0.jpg"

    def test_candidate_path_with_different_indices(self, tmp_path):
        """
        Verifica que candidate_path usa los índices correctamente.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        assert storage.candidate_path("job1", "p1", 0).name == "p1_candidate_0.jpg"
        assert storage.candidate_path("job1", "p1", 5).name == "p1_candidate_5.jpg"
        assert storage.candidate_path("job1", "p1", 99).name == "p1_candidate_99.jpg"


class TestListCandidates:
    """Tests para listado de candidatas disponibles."""

    def test_list_candidates_returns_empty_when_dir_not_exists(self, tmp_path):
        """
        Verifica que list_candidates devuelve [] si el directorio no existe.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        result = storage.list_candidates("job1", "prod")
        assert result == []

    def test_list_candidates_returns_sorted_list(self, tmp_path):
        """
        Verifica que list_candidates devuelve índices ordenados.

        Escenario: crear candidatas en desorden.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")
        cand_dir = tmp_path / "job1" / "candidates"
        cand_dir.mkdir(exist_ok=True)

        # Crear archivos en desorden intencional
        (cand_dir / "prod_candidate_2.jpg").touch()
        (cand_dir / "prod_candidate_0.jpg").touch()
        (cand_dir / "prod_candidate_1.jpg").touch()

        result = storage.list_candidates("job1", "prod")
        assert result == [0, 1, 2]

    def test_list_candidates_ignores_non_matching_files(self, tmp_path):
        """
        Verifica que list_candidates ignora archivos que no coinciden el patrón.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")
        cand_dir = tmp_path / "job1" / "candidates"
        cand_dir.mkdir(exist_ok=True)

        # Crear mixto: candidatas válidas + basura
        (cand_dir / "prod_candidate_0.jpg").touch()
        (cand_dir / "prod_candidate_1.jpg").touch()
        (cand_dir / "prod.jpg").touch()  # Final, no candidata
        (cand_dir / "other_candidate_0.jpg").touch()  # Otro producto
        (cand_dir / "readme.txt").touch()  # No jpg

        result = storage.list_candidates("job1", "prod")
        assert result == [0, 1]

    def test_list_candidates_handles_non_numeric_indices(self, tmp_path):
        """
        Verifica que list_candidates ignora archivos con índices no numéricos.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")
        cand_dir = tmp_path / "job1" / "candidates"
        cand_dir.mkdir(exist_ok=True)

        # Crear candidatas válidas e inválidas
        (cand_dir / "prod_candidate_0.jpg").touch()
        (cand_dir / "prod_candidate_1.jpg").touch()
        (cand_dir / "prod_candidate_abc.jpg").touch()  # Índice no numérico

        result = storage.list_candidates("job1", "prod")
        assert result == [0, 1]


class TestGetCandidateInfo:
    """Tests para lectura de metadatos de candidatas."""

    def test_get_candidate_info_returns_dimensions_and_size(self, tmp_path):
        """
        Verifica que get_candidate_info devuelve width, height y size_bytes.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")
        cand_dir = tmp_path / "job1" / "candidates"
        cand_dir.mkdir()

        # Crear imagen válida
        img = Image.new("RGB", (640, 480), color="red")
        img.save(cand_dir / "prod_candidate_0.jpg", "JPEG")

        result = storage.get_candidate_info("job1", "prod", 0)

        assert result["width"] == 640
        assert result["height"] == 480
        assert result["size_bytes"] > 0

    def test_get_candidate_info_different_dimensions(self, tmp_path):
        """
        Verifica que get_candidate_info detecta diferentes dimensiones.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")
        cand_dir = tmp_path / "job1" / "candidates"
        cand_dir.mkdir()

        # Crear imágenes de diferentes tamaños
        for width, height in [(800, 600), (400, 300), (1200, 900)]:
            img = Image.new("RGB", (width, height), color="blue")
            img.save(cand_dir / f"prod_candidate_{width}.jpg", "JPEG")

        for width, height in [(800, 600), (400, 300), (1200, 900)]:
            result = storage.get_candidate_info("job1", "prod", width)
            assert result["width"] == width
            assert result["height"] == height

    def test_get_candidate_info_raises_filenotfound_when_missing(self, tmp_path):
        """
        Verifica que get_candidate_info lanza FileNotFoundError cuando falta.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")

        with pytest.raises(FileNotFoundError):
            storage.get_candidate_info("job1", "nonexistent", 0)

    def test_get_candidate_info_size_bytes_gt_zero(self, tmp_path):
        """
        Verifica que size_bytes es siempre > 0 para imágenes válidas.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")
        cand_dir = tmp_path / "job1" / "candidates"
        cand_dir.mkdir()

        img = Image.new("RGB", (100, 100), color="green")
        img.save(cand_dir / "prod_candidate_0.jpg", "JPEG")

        result = storage.get_candidate_info("job1", "prod", 0)
        assert result["size_bytes"] > 0


class TestConfirmSelection:
    """Tests para confirmación de selección de fotos."""

    def test_confirm_selection_renames_selected_to_codigo_jpg(self, tmp_path):
        """
        Verifica que confirm_selection renombra la candidata seleccionada.

        Nombre final: {codigo}.jpg

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")
        cand_dir = tmp_path / "job1" / "candidates"
        cand_dir.mkdir()

        # Crear 2 candidatas
        img = Image.new("RGB", (640, 480), color="red")
        img.save(cand_dir / "prod_candidate_0.jpg", "JPEG")
        img.save(cand_dir / "prod_candidate_1.jpg", "JPEG")

        # Confirmar selección del índice 0
        storage.confirm_selection("job1", {"prod": 0})

        # Verificar que prod.jpg existe
        assert (tmp_path / "job1" / "prod.jpg").exists()

    def test_confirm_selection_selects_correct_candidate(self, tmp_path):
        """
        Verifica que confirm_selection copia el candidato correcto.

        Escenario: 3 candidatas, seleccionar la del índice 1.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")
        cand_dir = tmp_path / "job1" / "candidates"
        cand_dir.mkdir()

        # Crear 3 candidatas con colores distintos
        colors = ["red", "green", "blue"]
        for i, color in enumerate(colors):
            img = Image.new("RGB", (100, 100), color=color)
            img.save(cand_dir / f"prod_candidate_{i}.jpg", "JPEG")

        # Confirmar el índice 1 (verde)
        storage.confirm_selection("job1", {"prod": 1})

        # Verificar que el archivo final es el verde
        final_img = Image.open(tmp_path / "job1" / "prod.jpg")
        # Nota: JPEG con compresión puede alterar levemente los píxeles
        pixel = final_img.getpixel((0, 0))
        # Verde es (0, 128, 0), pero JPEG puede variar ligeramente
        assert pixel[0] <= 10 and 120 <= pixel[1] <= 135 and pixel[2] <= 10

    def test_confirm_selection_deletes_other_candidates(self, tmp_path):
        """
        Verifica que confirm_selection elimina candidatas no seleccionadas.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")
        cand_dir = tmp_path / "job1" / "candidates"
        cand_dir.mkdir()

        # Crear 3 candidatas
        img = Image.new("RGB", (100, 100), color="red")
        for i in range(3):
            img.save(cand_dir / f"prod_candidate_{i}.jpg", "JPEG")

        storage.confirm_selection("job1", {"prod": 1})

        # Verificar que solo la seleccionada existe (renombrada)
        assert (tmp_path / "job1" / "prod.jpg").exists()
        assert not (cand_dir / "prod_candidate_0.jpg").exists()
        assert not (cand_dir / "prod_candidate_1.jpg").exists()
        assert not (cand_dir / "prod_candidate_2.jpg").exists()

    def test_confirm_selection_removes_candidates_dir(self, tmp_path):
        """
        Verifica que confirm_selection elimina el directorio candidates/.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")
        cand_dir = tmp_path / "job1" / "candidates"
        cand_dir.mkdir()

        img = Image.new("RGB", (100, 100), color="red")
        img.save(cand_dir / "prod_candidate_0.jpg", "JPEG")

        storage.confirm_selection("job1", {"prod": 0})

        assert not cand_dir.exists()

    def test_confirm_selection_multiple_products(self, tmp_path):
        """
        Verifica que confirm_selection maneja múltiples productos.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")
        cand_dir = tmp_path / "job1" / "candidates"
        cand_dir.mkdir()

        img = Image.new("RGB", (100, 100), color="red")

        # Crear candidatas para 3 productos
        for prod in ["p1", "p2", "p3"]:
            for idx in range(2):
                img.save(cand_dir / f"{prod}_candidate_{idx}.jpg", "JPEG")

        # Confirmar selecciones
        storage.confirm_selection("job1", {"p1": 0, "p2": 1, "p3": 0})

        # Verificar que los tres archivos finales existen
        assert (tmp_path / "job1" / "p1.jpg").exists()
        assert (tmp_path / "job1" / "p2.jpg").exists()
        assert (tmp_path / "job1" / "p3.jpg").exists()

        # Verificar que candidatos fueron eliminados
        assert not cand_dir.exists()

    def test_confirm_selection_raises_filenotfound_if_missing(self, tmp_path):
        """
        Verifica que confirm_selection lanza FileNotFoundError si candidata no existe.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")
        cand_dir = tmp_path / "job1" / "candidates"
        cand_dir.mkdir()

        img = Image.new("RGB", (100, 100), color="red")
        img.save(cand_dir / "prod_candidate_0.jpg", "JPEG")

        # Intentar confirmar índice inexistente
        with pytest.raises(FileNotFoundError):
            storage.confirm_selection("job1", {"prod": 5})


class TestCleanupCandidates:
    """Tests para limpieza de directorios de candidatas."""

    def test_cleanup_candidates_returns_zero_if_not_exists(self, tmp_path):
        """
        Verifica que cleanup_candidates devuelve 0 si el directorio no existe.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        count = storage.cleanup_candidates("nonexistent")
        assert count == 0

    def test_cleanup_candidates_deletes_all_files(self, tmp_path):
        """
        Verifica que cleanup_candidates elimina todos los archivos.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")
        cand_dir = tmp_path / "job1" / "candidates"
        cand_dir.mkdir()

        img = Image.new("RGB", (100, 100), color="red")
        for i in range(5):
            img.save(cand_dir / f"prod_candidate_{i}.jpg", "JPEG")

        count = storage.cleanup_candidates("job1")

        assert count == 5
        assert not cand_dir.exists()

    def test_cleanup_candidates_handles_multiple_products(self, tmp_path):
        """
        Verifica que cleanup_candidates elimina candidatas de todos los productos.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")
        cand_dir = tmp_path / "job1" / "candidates"
        cand_dir.mkdir()

        img = Image.new("RGB", (100, 100), color="red")

        # Crear candidatas para múltiples productos
        for prod in ["p1", "p2", "p3"]:
            for idx in range(3):
                img.save(cand_dir / f"{prod}_candidate_{idx}.jpg", "JPEG")

        count = storage.cleanup_candidates("job1")

        # 3 productos * 3 candidatas = 9 archivos
        assert count == 9
        assert not cand_dir.exists()

    def test_cleanup_candidates_counts_only_jpg_files(self, tmp_path):
        """
        Verifica que cleanup_candidates cuenta solo archivos reales.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        storage.ensure_job_dir("job1")
        cand_dir = tmp_path / "job1" / "candidates"
        cand_dir.mkdir()

        img = Image.new("RGB", (100, 100), color="red")
        img.save(cand_dir / "prod_candidate_0.jpg", "JPEG")
        img.save(cand_dir / "prod_candidate_1.jpg", "JPEG")

        # Crear archivo extra que no es candidata
        (cand_dir / "readme.txt").touch()

        count = storage.cleanup_candidates("job1")

        # Cuenta files/subdirs bajo candidates/, incluyendo readme.txt
        assert count >= 2
        assert not cand_dir.exists()
