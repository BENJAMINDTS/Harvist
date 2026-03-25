"""
Tests unitarios para services/scraper/brand_cache.py.

Cubre GS1PrefixCache: carga desde JSON semillero temporal, resolución de EANs
mediante longest_prefix_match, manejo de archivo semillero inexistente, el
método register() y los campos del BrandResult devuelto.

Todos los EANs de prueba se construyen con el helper _compute_check_digit
para garantizar checksums correctos.

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.scraper.brand_cache import GS1PrefixCache
from services.scraper.brand_validator import BrandResult


# ── Helper de generación de EANs válidos ──────────────────────────────────────


def _compute_check_digit(digits_without_check: str) -> str:
    """
    Calcula el dígito de control GS1 Módulo 10 para un cuerpo de EAN.

    Args:
        digits_without_check: cuerpo del EAN sin el último dígito.

    Returns:
        Un carácter ('0'–'9') con el dígito de control calculado.
    """
    weights = [1, 3] * len(digits_without_check)
    total = sum(int(d) * w for d, w in zip(digits_without_check, weights))
    return str((10 - total % 10) % 10)


def _make_ean(body: str) -> str:
    """
    Construye un EAN completo y válido añadiendo el dígito de control.

    Args:
        body: cuerpo del EAN sin el último dígito.

    Returns:
        EAN completo con dígito de control correcto.
    """
    return body + _compute_check_digit(body)


# ── EANs de prueba ─────────────────────────────────────────────────────────────

# EAN-13 real con prefijo "8413037" (Amanova)
_EAN13_AMANOVA = "8413037335779"

# EAN-13 generado con prefijo "9999999" (sin entrada en semillero)
_EAN13_DESCONOCIDO = _make_ean("999999999999")

# EAN-13 generado con prefijo "5400585" (distinto de Amanova)
_EAN13_OTRA_MARCA = _make_ean("540058515241")


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def seed_file(tmp_path: Path) -> Path:
    """
    Crea un archivo JSON semillero temporal con 3 entradas de prueba.

    Returns:
        Ruta al archivo JSON temporal creado.
    """
    data = [
        {"prefix": "8413037", "company_name": "Amanova", "country_code": "ES"},
        {"prefix": "5400585", "company_name": "Coca-Cola", "country_code": "BE"},
        {"prefix": "123456",  "company_name": "TestBrand", "country_code": "XX"},
    ]
    path = tmp_path / "gs1_prefixes_seed.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture()
def cache_from_seed(seed_file: Path) -> GS1PrefixCache:
    """
    Inicializa un GS1PrefixCache cargado desde el semillero temporal.

    Args:
        seed_file: ruta al archivo semillero temporal (inyectada por pytest).

    Returns:
        Instancia de GS1PrefixCache lista para usar en los tests.
    """
    return GS1PrefixCache(seed_path=str(seed_file))


@pytest.fixture()
def cache_vacia(tmp_path: Path) -> GS1PrefixCache:
    """
    GS1PrefixCache inicializada apuntando a una ruta inexistente (caché vacía).

    Returns:
        Instancia de GS1PrefixCache sin ningún prefijo registrado.
    """
    ruta_inexistente = str(tmp_path / "no_existe.json")
    return GS1PrefixCache(seed_path=ruta_inexistente)


# ══════════════════════════════════════════════════════════════════════════════
# Carga desde archivo temporal
# ══════════════════════════════════════════════════════════════════════════════


class TestCargaSemillero:
    """
    Tests sobre la carga del semillero GS1 desde archivo JSON.

    Verifica que la caché se pueble correctamente al inicializarse y que
    resolve() devuelva resultados apropiados para EANs conocidos y desconocidos.

    :author: BenjaminDTS
    """

    def test_resolve_devuelve_brand_result_para_ean_conocido(
        self, cache_from_seed: GS1PrefixCache
    ) -> None:
        """EAN cuyo prefijo está en el semillero devuelve un BrandResult no nulo."""
        result = cache_from_seed.resolve(_EAN13_AMANOVA)
        assert result is not None

    def test_resolve_brand_name_correcto(self, cache_from_seed: GS1PrefixCache) -> None:
        """BrandResult devuelto contiene el brand_name del semillero."""
        result = cache_from_seed.resolve(_EAN13_AMANOVA)
        assert result is not None
        assert result.brand_name == "Amanova"

    def test_resolve_devuelve_none_para_ean_desconocido(
        self, cache_from_seed: GS1PrefixCache
    ) -> None:
        """EAN cuyo prefijo no está en el semillero devuelve None."""
        result = cache_from_seed.resolve(_EAN13_DESCONOCIDO)
        assert result is None

    def test_resolve_segunda_marca_del_semillero(
        self, cache_from_seed: GS1PrefixCache
    ) -> None:
        """Otra marca del semillero también se resuelve correctamente."""
        result = cache_from_seed.resolve(_EAN13_OTRA_MARCA)
        assert result is not None
        assert result.brand_name == "Coca-Cola"


# ══════════════════════════════════════════════════════════════════════════════
# Prioridad del prefijo más largo
# ══════════════════════════════════════════════════════════════════════════════


class TestPrioridadPrefijoMasLargo:
    """
    Tests que verifican que GS1PrefixCache resuelve al prefijo más específico
    cuando hay dos prefijos solapados registrados para el mismo EAN.

    :author: BenjaminDTS
    """

    def test_prefijo_7_gana_sobre_prefijo_6(self, tmp_path: Path) -> None:
        """
        Con prefijos solapados {"841303": "Generic", "8413037": "Specific"},
        el EAN 8413037335779 debe resolverse a "Specific" (más específico).
        """
        data = [
            {"prefix": "841303",  "company_name": "Generic",  "country_code": "XX"},
            {"prefix": "8413037", "company_name": "Specific", "country_code": "ES"},
        ]
        seed = tmp_path / "seed_overlap.json"
        seed.write_text(json.dumps(data), encoding="utf-8")
        cache = GS1PrefixCache(seed_path=str(seed))

        result = cache.resolve(_EAN13_AMANOVA)

        assert result is not None
        assert result.brand_name == "Specific"

    def test_prefijo_8_gana_sobre_7_y_6(self, tmp_path: Path) -> None:
        """Con prefijos de 6, 7 y 8 dígitos, el de 8 tiene la máxima prioridad."""
        data = [
            {"prefix": "841303",   "company_name": "Six",   "country_code": "XX"},
            {"prefix": "8413037",  "company_name": "Seven", "country_code": "XX"},
            {"prefix": "84130373", "company_name": "Eight", "country_code": "XX"},
        ]
        seed = tmp_path / "seed_three.json"
        seed.write_text(json.dumps(data), encoding="utf-8")
        cache = GS1PrefixCache(seed_path=str(seed))

        result = cache.resolve(_EAN13_AMANOVA)

        assert result is not None
        assert result.brand_name == "Eight"


# ══════════════════════════════════════════════════════════════════════════════
# Archivo semillero inexistente
# ══════════════════════════════════════════════════════════════════════════════


class TestSemilleroInexistente:
    """
    Tests que verifican el comportamiento tolerante a fallos cuando el archivo
    semillero no existe o está corrupto.

    :author: BenjaminDTS
    """

    def test_semillero_inexistente_no_lanza_excepcion(self, tmp_path: Path) -> None:
        """Inicializar GS1PrefixCache con ruta inexistente no lanza excepción."""
        ruta = str(tmp_path / "no_existe.json")
        # No debe propagarse ninguna excepción
        cache = GS1PrefixCache(seed_path=ruta)
        assert cache is not None

    def test_semillero_inexistente_cache_arranca_vacia(
        self, cache_vacia: GS1PrefixCache
    ) -> None:
        """Caché inicializada sin semillero devuelve None para cualquier EAN."""
        result = cache_vacia.resolve(_EAN13_AMANOVA)
        assert result is None

    def test_semillero_json_invalido_no_lanza_excepcion(self, tmp_path: Path) -> None:
        """Archivo semillero con JSON inválido no propaga excepción; caché arranca vacía."""
        seed = tmp_path / "corrupt.json"
        seed.write_text("esto no es JSON válido !!!{{{", encoding="utf-8")
        cache = GS1PrefixCache(seed_path=str(seed))
        assert cache.resolve(_EAN13_AMANOVA) is None

    def test_semillero_con_entradas_sin_prefijo_se_ignoran(self, tmp_path: Path) -> None:
        """Entradas del semillero sin campo 'prefix' se descartan sin error."""
        data = [
            {"company_name": "SinPrefijo", "country_code": "XX"},  # sin 'prefix'
            {"prefix": "", "company_name": "PrefijoVacio", "country_code": "XX"},
            {"prefix": "8413037", "company_name": "Amanova", "country_code": "ES"},
        ]
        seed = tmp_path / "partial.json"
        seed.write_text(json.dumps(data), encoding="utf-8")
        cache = GS1PrefixCache(seed_path=str(seed))

        # Solo la entrada válida debe haberse cargado
        result = cache.resolve(_EAN13_AMANOVA)
        assert result is not None
        assert result.brand_name == "Amanova"


# ══════════════════════════════════════════════════════════════════════════════
# register()
# ══════════════════════════════════════════════════════════════════════════════


class TestRegister:
    """
    Tests sobre el método register() que añade prefijos en caliente.

    Verifica que un prefijo recién registrado se pueda resolver de inmediato,
    que el último registro gane para el mismo prefijo y que el método no lance
    excepciones bajo ninguna circunstancia.

    :author: BenjaminDTS
    """

    def test_register_permite_resolver_prefijo_nuevo(
        self, cache_vacia: GS1PrefixCache
    ) -> None:
        """Prefijo registrado via register() se resuelve correctamente tras el registro."""
        cache_vacia.register("8413037", "TestBrand", "ES")
        result = cache_vacia.resolve(_EAN13_AMANOVA)

        assert result is not None
        assert result.brand_name == "TestBrand"

    def test_register_brand_name_coincide(self, cache_vacia: GS1PrefixCache) -> None:
        """brand_name del BrandResult devuelto tras register() coincide con el registrado."""
        cache_vacia.register("8413037", "MarcaDeTest", "ES")
        result = cache_vacia.resolve(_EAN13_AMANOVA)

        assert result is not None
        assert result.brand_name == "MarcaDeTest"

    def test_register_sobrescribe_entrada_previa(
        self, cache_vacia: GS1PrefixCache
    ) -> None:
        """El último register() para el mismo prefijo sobreescribe el anterior."""
        cache_vacia.register("8413037", "Primero",  "ES")
        cache_vacia.register("8413037", "Segundo",  "ES")

        result = cache_vacia.resolve(_EAN13_AMANOVA)

        assert result is not None
        assert result.brand_name == "Segundo"

    def test_register_multiples_prefijos_diferentes(
        self, cache_vacia: GS1PrefixCache
    ) -> None:
        """Registrar prefijos distintos no interfiere entre sí."""
        cache_vacia.register("8413037", "MarcaA", "ES")
        cache_vacia.register("5400585", "MarcaB", "BE")

        assert cache_vacia.resolve(_EAN13_AMANOVA) is not None
        assert cache_vacia.resolve(_EAN13_AMANOVA).brand_name == "MarcaA"

        assert cache_vacia.resolve(_EAN13_OTRA_MARCA) is not None
        assert cache_vacia.resolve(_EAN13_OTRA_MARCA).brand_name == "MarcaB"

    def test_register_no_afecta_a_eans_de_otro_prefijo(
        self, cache_vacia: GS1PrefixCache
    ) -> None:
        """Registrar un prefijo no hace que EANs de otro prefijo se resuelvan."""
        cache_vacia.register("8413037", "Amanova", "ES")
        result = cache_vacia.resolve(_EAN13_DESCONOCIDO)
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# Campos del BrandResult devuelto por resolve()
# ══════════════════════════════════════════════════════════════════════════════


class TestBrandResultFields:
    """
    Tests sobre los campos del BrandResult devuelto por GS1PrefixCache.resolve().

    Verifica que source, confidence, brand_name y resolved_at tengan los
    valores esperados según el contrato definido en brand_validator.BrandResult.

    :author: BenjaminDTS
    """

    def test_source_es_cache_gs1(self, cache_from_seed: GS1PrefixCache) -> None:
        """BrandResult devuelto por la caché siempre tiene source='cache_gs1'."""
        result = cache_from_seed.resolve(_EAN13_AMANOVA)
        assert result is not None
        assert result.source == "cache_gs1"

    def test_confidence_es_high(self, cache_from_seed: GS1PrefixCache) -> None:
        """BrandResult devuelto por la caché siempre tiene confidence='high'."""
        result = cache_from_seed.resolve(_EAN13_AMANOVA)
        assert result is not None
        assert result.confidence == "high"

    def test_brand_name_no_es_none(self, cache_from_seed: GS1PrefixCache) -> None:
        """brand_name del BrandResult devuelto por la caché no es None."""
        result = cache_from_seed.resolve(_EAN13_AMANOVA)
        assert result is not None
        assert result.brand_name is not None

    def test_resolved_at_no_es_none(self, cache_from_seed: GS1PrefixCache) -> None:
        """resolved_at está establecido (no None) en el BrandResult devuelto."""
        result = cache_from_seed.resolve(_EAN13_AMANOVA)
        assert result is not None
        assert result.resolved_at is not None

    def test_ean_code_coincide_con_el_consultado(
        self, cache_from_seed: GS1PrefixCache
    ) -> None:
        """ean_code del BrandResult coincide con el EAN pasado a resolve()."""
        result = cache_from_seed.resolve(_EAN13_AMANOVA)
        assert result is not None
        assert result.ean_code == _EAN13_AMANOVA

    def test_brand_result_es_instancia_correcta(
        self, cache_from_seed: GS1PrefixCache
    ) -> None:
        """resolve() devuelve una instancia de BrandResult, no un dict ni None."""
        result = cache_from_seed.resolve(_EAN13_AMANOVA)
        assert isinstance(result, BrandResult)
