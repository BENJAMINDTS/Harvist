"""
Tests de integración para selección de fotos (Fase 7.5).

Estos tests verifican el comportamiento de las funciones de storage y consumer
relacionadas con candidatas de fotos, sin necesidad de levantar servidor HTTP.

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image
from io import BytesIO

from api.v1.schemas.job import PhotoSelectionItem, PhotoSelectionRequest
from services.storage_service import LocalStorageService


# ── Helpers ───────────────────────────────────────────────────────────────────


def _create_test_image(width: int = 640, height: int = 480) -> bytes:
    """
    Crea una imagen JPEG mínima para testing.

    Args:
        width: ancho de la imagen.
        height: alto de la imagen.

    Returns:
        Bytes de imagen JPEG válida.
    """
    img = Image.new("RGB", (width, height), color="red")
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestPhotoSelectionStorageWorkflow:
    """Tests de integración para workflow de selección de fotos."""

    def test_complete_workflow_create_candidates_confirm_selection(self, tmp_path):
        """
        Verifica el workflow completo: crear candidatas, listarlas, confirmar selección.

        Escenario:
        1. Crear directorio de candidatas
        2. Guardar múltiples candidatas por producto
        3. Listar candidatas disponibles
        4. Confirmar selección (renombrar)
        5. Verificar que candidates/ se eliminó

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        job_id = str(uuid4())
        storage.ensure_job_dir(job_id)

        # Step 1: Crear directorio de candidatas manualmente
        cand_dir = storage.candidates_dir(job_id)
        cand_dir.mkdir(parents=True, exist_ok=True)

        # Step 2: Guardar 3 candidatas para PROD001
        for i in range(3):
            img_data = _create_test_image(640 + i * 50, 480 + i * 30)
            cand_path = cand_dir / f"PROD001_candidate_{i}.jpg"
            cand_path.write_bytes(img_data)

        # Step 3: Listar candidatas
        candidates = storage.list_candidates(job_id, "PROD001")
        assert candidates == [0, 1, 2]

        # Step 4: Obtener info de una candidata
        info = storage.get_candidate_info(job_id, "PROD001", 1)
        assert info["width"] >= 640
        assert info["height"] >= 480
        assert info["size_bytes"] > 0

        # Step 5: Confirmar selección del índice 1
        storage.confirm_selection(job_id, {"PROD001": 1})

        # Step 6: Verificar que PROD001.jpg existe y candidates/ se eliminó
        assert (tmp_path / job_id / "PROD001.jpg").exists()
        assert not cand_dir.exists()

    def test_multiple_products_workflow(self, tmp_path):
        """
        Verifica workflow con múltiples productos en mismo job.

        Escenario:
        - PROD001: 3 candidatas
        - PROD002: 2 candidatas
        - PROD003: 1 candidata

        Confirmar selecciones para los 3 productos simultáneamente.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        job_id = str(uuid4())
        storage.ensure_job_dir(job_id)

        cand_dir = storage.candidates_dir(job_id)
        cand_dir.mkdir(parents=True, exist_ok=True)

        # Crear candidatas para 3 productos
        products_candidates = {
            "PROD001": 3,
            "PROD002": 2,
            "PROD003": 1,
        }

        for prod, count in products_candidates.items():
            for i in range(count):
                img_data = _create_test_image()
                (cand_dir / f"{prod}_candidate_{i}.jpg").write_bytes(img_data)

        # Verificar listados
        assert storage.list_candidates(job_id, "PROD001") == [0, 1, 2]
        assert storage.list_candidates(job_id, "PROD002") == [0, 1]
        assert storage.list_candidates(job_id, "PROD003") == [0]

        # Confirmar selecciones para los 3
        storage.confirm_selection(
            job_id,
            {"PROD001": 1, "PROD002": 0, "PROD003": 0}
        )

        # Verificar que los 3 archivos finales existen
        job_dir = tmp_path / job_id
        assert (job_dir / "PROD001.jpg").exists()
        assert (job_dir / "PROD002.jpg").exists()
        assert (job_dir / "PROD003.jpg").exists()

        # Verificar que candidates/ fue eliminado
        assert not cand_dir.exists()

    def test_cleanup_stale_candidates(self, tmp_path):
        """
        Verifica limpieza de candidatas no confirmadas (TTL/stale).

        Escenario:
        1. Crear candidatas
        2. NO confirmar selección
        3. Llamar cleanup_candidates
        4. Verificar que todas se eliminaron

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        job_id = str(uuid4())
        storage.ensure_job_dir(job_id)

        cand_dir = storage.candidates_dir(job_id)
        cand_dir.mkdir(parents=True, exist_ok=True)

        # Crear candidatas
        for prod in ["P1", "P2", "P3"]:
            for i in range(2):
                img_data = _create_test_image()
                (cand_dir / f"{prod}_candidate_{i}.jpg").write_bytes(img_data)

        # Verificar que hay 6 candidatas (3 productos * 2 cada uno)
        assert len(list(cand_dir.glob("*_candidate_*.jpg"))) == 6

        # Llamar cleanup
        deleted_count = storage.cleanup_candidates(job_id)

        # Verificar resultados
        assert deleted_count >= 6
        assert not cand_dir.exists()

    def test_photo_selection_request_schema(self):
        """
        Verifica que PhotoSelectionRequest tiene la estructura correcta.

        Args:
            None
        """
        # Crear request válido
        request = PhotoSelectionRequest(
            selections=[
                PhotoSelectionItem(codigo="PROD001", selected_index=0),
                PhotoSelectionItem(codigo="PROD002", selected_index=2),
            ]
        )

        assert len(request.selections) == 2
        assert request.selections[0].codigo == "PROD001"
        assert request.selections[0].selected_index == 0

    def test_photo_selection_request_validation(self):
        """
        Verifica validación de PhotoSelectionRequest.

        Args:
            None
        """
        # Debe rechazar lista vacía
        with pytest.raises(ValueError):
            PhotoSelectionRequest(selections=[])

        # Debe rechazar índice negativo
        with pytest.raises(ValueError):
            PhotoSelectionRequest(
                selections=[PhotoSelectionItem(codigo="P1", selected_index=-1)]
            )

    def test_candidate_path_naming_convention(self, tmp_path):
        """
        Verifica la convención de nombres para candidatas.

        Patrón esperado: {codigo}_candidate_{index}.jpg

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        job_id = str(uuid4())

        # Verificar rutas
        path_0 = storage.candidate_path(job_id, "MYPROD", 0)
        path_5 = storage.candidate_path(job_id, "MYPROD", 5)
        path_99 = storage.candidate_path(job_id, "MYPROD", 99)

        assert path_0.name == "MYPROD_candidate_0.jpg"
        assert path_5.name == "MYPROD_candidate_5.jpg"
        assert path_99.name == "MYPROD_candidate_99.jpg"

    def test_final_photo_naming_convention(self, tmp_path):
        """
        Verifica que la foto final se nombra {codigo}.jpg.

        Args:
            tmp_path: fixture pytest con directorio temporal.
        """
        storage = LocalStorageService(str(tmp_path))
        job_id = str(uuid4())
        storage.ensure_job_dir(job_id)

        cand_dir = storage.candidates_dir(job_id)
        cand_dir.mkdir(parents=True, exist_ok=True)

        # Crear una candidata
        img_data = _create_test_image()
        (cand_dir / "MYPROD_candidate_0.jpg").write_bytes(img_data)

        # Confirmar selección
        storage.confirm_selection(job_id, {"MYPROD": 0})

        # Verificar nombre final
        job_dir = tmp_path / job_id
        assert (job_dir / "MYPROD.jpg").exists()
        assert not (cand_dir / "MYPROD_candidate_0.jpg").exists()
