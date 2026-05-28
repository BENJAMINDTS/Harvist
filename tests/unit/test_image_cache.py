"""
Tests unitarios para ImageCacheService.

Usan tmp_path de pytest para todos los ficheros SQLite y de imagen.
Nunca tocan data/image_cache.db real del proyecto.

:author: BenjaminDTS
"""

import pytest

from services.scraper.image_cache import ImageCacheService

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def cache(tmp_path):
    """ImageCacheService sobre un SQLite temporal."""
    return ImageCacheService(tmp_path / "test_cache.db")


@pytest.fixture()
def imagen_real(tmp_path):
    """Crea un archivo de imagen real en disco y devuelve su Path."""
    p = tmp_path / "img" / "TEST001_001.jpg"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # JPEG mínimo
    return p


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestImageCacheServiceInit:
    def test_creates_table_on_init_if_not_exists(self, tmp_path):
        """La tabla se crea en el primer __init__; el segundo __init__ no falla."""
        db = tmp_path / "cache.db"
        ImageCacheService(db)
        # Segunda inicialización sobre el mismo fichero no debe lanzar excepción
        svc = ImageCacheService(db)
        assert svc.stats()["total_entries"] == 0


class TestLookup:
    def test_lookup_returns_none_when_cache_is_empty(self, cache):
        result = cache.lookup(ean="1234567890123", codigo="TEST001")
        assert result is None

    def test_lookup_returns_path_when_ean_matches(self, cache, imagen_real):
        cache.register(
            ean="1234567890123",
            codigo="TEST001",
            path=imagen_real,
            job_id="job-abc",
            width=800,
            height=800,
        )
        result = cache.lookup(ean="1234567890123", codigo="TEST001")
        assert result == imagen_real

    def test_lookup_returns_path_when_codigo_matches_and_no_ean(self, cache, imagen_real):
        cache.register(
            ean=None,
            codigo="TEST001",
            path=imagen_real,
            job_id="job-abc",
            width=800,
            height=800,
        )
        result = cache.lookup(ean=None, codigo="TEST001")
        assert result == imagen_real

    def test_lookup_prioritizes_ean_over_codigo(self, cache, tmp_path):
        """Si hay dos entradas distintas, EAN tiene prioridad."""
        img_by_ean = tmp_path / "by_ean.jpg"
        img_by_ean.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        img_by_codigo = tmp_path / "by_codigo.jpg"
        img_by_codigo.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        cache.register(ean="1234567890123", codigo="OTHER", path=img_by_ean, job_id="j1", width=800, height=800)
        cache.register(ean=None, codigo="TEST001", path=img_by_codigo, job_id="j2", width=800, height=800)

        result = cache.lookup(ean="1234567890123", codigo="TEST001")
        assert result == img_by_ean

    def test_lookup_returns_none_and_removes_entry_when_file_deleted(self, cache, tmp_path):
        """Imagen huérfana: se elimina la entrada y se devuelve None."""
        img = tmp_path / "ghost.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        cache.register(ean="1111111111111", codigo="GHOST", path=img, job_id="j1", width=100, height=100)

        # Borrar el archivo del disco
        img.unlink()

        result = cache.lookup(ean="1111111111111", codigo="GHOST")
        assert result is None
        # La entrada debe haber sido eliminada del índice
        assert cache.stats()["total_entries"] == 0


class TestRegister:
    def test_register_stores_entry_correctly(self, cache, imagen_real):
        cache.register(ean="9999999999999", codigo="P001", path=imagen_real, job_id="jX", width=800, height=600)
        assert cache.stats()["total_entries"] == 1
        result = cache.lookup(ean="9999999999999", codigo="P001")
        assert result == imagen_real

    def test_register_overwrites_existing_entry_for_same_ean(self, cache, tmp_path):
        img_old = tmp_path / "old.jpg"
        img_old.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        img_new = tmp_path / "new.jpg"
        img_new.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        cache.register(ean="5555555555555", codigo="P002", path=img_old, job_id="j1", width=800, height=800)
        cache.register(ean="5555555555555", codigo="P002", path=img_new, job_id="j2", width=800, height=800)

        assert cache.stats()["total_entries"] == 1
        result = cache.lookup(ean="5555555555555", codigo="P002")
        assert result == img_new


class TestInvalidate:
    def test_invalidate_removes_entry_from_index(self, cache, imagen_real):
        cache.register(ean="4444444444444", codigo="DEL001", path=imagen_real, job_id="j1", width=800, height=800)
        assert cache.stats()["total_entries"] == 1

        cache.invalidate(ean="4444444444444", codigo="DEL001")
        assert cache.stats()["total_entries"] == 0


class TestCleanupOrphans:
    def test_cleanup_orphans_removes_entries_with_missing_files(self, cache, tmp_path):
        img = tmp_path / "orphan.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        cache.register(ean="2222222222222", codigo="ORF001", path=img, job_id="j1", width=800, height=800)

        img.unlink()
        removed = cache.cleanup_orphans()

        assert removed == 1
        assert cache.stats()["total_entries"] == 0

    def test_cleanup_orphans_returns_count_of_removed_entries(self, cache, tmp_path):
        imgs = []
        for i in range(3):
            img = tmp_path / f"orphan_{i}.jpg"
            img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
            imgs.append(img)
            cache.register(ean=None, codigo=f"ORP{i:03d}", path=img, job_id="j1", width=100, height=100)

        # Borrar solo 2 de 3
        imgs[0].unlink()
        imgs[1].unlink()

        removed = cache.cleanup_orphans()
        assert removed == 2
        assert cache.stats()["total_entries"] == 1


class TestStats:
    def test_stats_returns_correct_total_entries_count(self, cache, tmp_path):
        assert cache.stats()["total_entries"] == 0

        for i in range(4):
            img = tmp_path / f"img_{i}.jpg"
            img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
            cache.register(ean=f"{i:013d}", codigo=f"P{i:03d}", path=img, job_id="j1", width=800, height=800)

        stats = cache.stats()
        assert stats["total_entries"] == 4
        assert stats["unique_eans"] == 4
        assert stats["oldest_entry"] is not None
        assert stats["newest_entry"] is not None
