"""
Tests unitarios para services/scraper/brand_validator.py.

Cubre validate_ean_checksum() y longest_prefix_match() sin dependencias
externas. Todos los EANs de prueba se generan con el helper _compute_check_digit
definido en este mismo módulo para garantizar que el dígito de control es
siempre correcto y nunca producto de un cálculo manual erróneo.

:author: BenjaminDTS
:version: 1.0.0
"""

from __future__ import annotations

import pytest

from services.scraper.brand_validator import longest_prefix_match, validate_ean_checksum


# ── Helper de generación de EANs válidos ──────────────────────────────────────


def _compute_check_digit(digits_without_check: str) -> str:
    """
    Calcula el dígito de control GS1 Módulo 10 para un cuerpo de EAN.

    Aplica el mismo algoritmo que validate_ean_checksum: posición par (0-indexed)
    recibe peso 1, posición impar recibe peso 3. Útil para construir EANs de
    prueba con checksum correcto sin depender de valores hardcodeados externos.

    Args:
        digits_without_check: cadena de dígitos sin el dígito de control final.

    Returns:
        Un único carácter con el dígito de control calculado ('0'–'9').
    """
    weights = [1, 3] * len(digits_without_check)
    total = sum(int(d) * w for d, w in zip(digits_without_check, weights))
    return str((10 - total % 10) % 10)


def _make_ean(body: str) -> str:
    """
    Construye un EAN completo y válido añadiendo el dígito de control.

    Args:
        body: cuerpo del EAN sin el último dígito (ej. 12 dígitos para EAN-13).

    Returns:
        EAN completo con dígito de control correcto.
    """
    return body + _compute_check_digit(body)


# ── EANs de prueba usados en múltiples tests ──────────────────────────────────

# EAN-13 real de producto Amanova (usado en pruebas de caché y prefijos GS1)
_EAN13_AMANOVA = "8413037335779"

# EAN-13 generado para tests de "no encontrado"
_EAN13_NO_PREFIX = _make_ean("999999999999")   # 13 dígitos
_EAN13_ALT       = _make_ean("540058515241")   # prefijo diferente al de Amanova

# EAN-8 generado
_EAN8_VALID = _make_ean("1234567")             # 8 dígitos

# UPC-A generado (12 dígitos)
_UPC_A_VALID = _make_ean("01234567890")        # 12 dígitos → UPC-A


# ══════════════════════════════════════════════════════════════════════════════
# validate_ean_checksum
# ══════════════════════════════════════════════════════════════════════════════


class TestValidateEanChecksum:
    """
    Tests sobre la función validate_ean_checksum().

    Verifica la aceptación de EANs con checksum correcto en las longitudes
    estándar GS1 (8, 12, 13 dígitos), el rechazo de checksums incorrectos y el
    manejo sin excepciones de cualquier tipo de entrada inválida.

    :author: BenjaminDTS
    """

    # ── Casos válidos ─────────────────────────────────────────────────────────

    def test_ean13_valido_amanova_devuelve_true(self) -> None:
        """EAN-13 conocido de producto real con checksum correcto devuelve True."""
        assert validate_ean_checksum(_EAN13_AMANOVA) is True

    def test_ean8_valido_devuelve_true(self) -> None:
        """EAN-8 de 8 dígitos con checksum GS1 correcto devuelve True."""
        assert validate_ean_checksum(_EAN8_VALID) is True

    def test_upca_12_digitos_valido_devuelve_true(self) -> None:
        """UPC-A de 12 dígitos con checksum correcto devuelve True."""
        assert validate_ean_checksum(_UPC_A_VALID) is True

    def test_ean13_generado_devuelve_true(self) -> None:
        """EAN-13 generado con _make_ean siempre devuelve True (valida el helper)."""
        ean = _make_ean("123456789012")
        assert validate_ean_checksum(ean) is True

    def test_ean13_con_espacios_laterales_devuelve_true(self) -> None:
        """EAN-13 con espacios al inicio y al final se limpia y se valida correctamente."""
        assert validate_ean_checksum(f"  {_EAN13_AMANOVA}  ") is True

    def test_todos_los_ceros_ean13(self) -> None:
        """
        EAN de 13 ceros: el cuerpo (12 ceros) suma 0, dígito esperado = 0,
        por lo tanto '0000000000000' es un EAN-13 válido por el algoritmo.
        """
        # Verificación explícita: _compute_check_digit("000000000000") == "0"
        assert _compute_check_digit("000000000000") == "0"
        assert validate_ean_checksum("0000000000000") is True

    # ── Casos inválidos — checksum incorrecto ─────────────────────────────────

    def test_ean13_checksum_incorrecto_devuelve_false(self) -> None:
        """EAN-13 con último dígito modificado (checksum inválido) devuelve False."""
        # _EAN13_AMANOVA termina en '9'; cambiar a '0' rompe el checksum
        ean_malo = _EAN13_AMANOVA[:-1] + "0"
        assert validate_ean_checksum(ean_malo) is False

    def test_ean13_ultimo_digito_sumado_uno_devuelve_false(self) -> None:
        """
        EAN-13 con checksum correcto +1 (mod 10) siempre falla.
        Construye el EAN base correcto y corrompe el último dígito.
        """
        valid = _make_ean("841303733577")
        check_correcto = int(valid[-1])
        check_malo = (check_correcto + 1) % 10
        assert validate_ean_checksum(valid[:-1] + str(check_malo)) is False

    # ── Casos inválidos — formato o longitud ──────────────────────────────────

    def test_cadena_vacia_devuelve_false(self) -> None:
        """Cadena vacía devuelve False sin lanzar excepción."""
        assert validate_ean_checksum("") is False

    def test_cadena_no_numerica_devuelve_false(self) -> None:
        """Cadena con letras devuelve False sin lanzar excepción."""
        assert validate_ean_checksum("LECHUGA ICEBERG") is False

    def test_cadena_alfanumerica_devuelve_false(self) -> None:
        """Cadena con mezcla de dígitos y letras devuelve False."""
        assert validate_ean_checksum("841303733577X") is False

    def test_demasiado_corta_7_digitos_devuelve_false(self) -> None:
        """EAN de 7 dígitos (fuera de las longitudes GS1 válidas) devuelve False."""
        assert validate_ean_checksum("1234567") is False

    def test_demasiado_larga_15_digitos_devuelve_false(self) -> None:
        """EAN de 15 dígitos (fuera de las longitudes GS1 válidas) devuelve False."""
        assert validate_ean_checksum("123456789012345") is False

    def test_longitud_11_devuelve_false(self) -> None:
        """EAN de 11 dígitos no es una longitud GS1 estándar y devuelve False."""
        assert validate_ean_checksum("12345678901") is False

    def test_solo_espacios_devuelve_false(self) -> None:
        """Cadena con solo espacios en blanco devuelve False sin lanzar excepción."""
        assert validate_ean_checksum("             ") is False

    # ── Garantía de no excepción con entradas basura ──────────────────────────

    @pytest.mark.parametrize("garbage", [
        "abc!@#",
        "!!!!!!!!!!!!!",
        "None",
        "null",
        "undefined",
        "   abc   ",
        "\t\n",
        "0" * 100,
        "-123456789012",
        "+8413037335779",
    ])
    def test_entradas_basura_nunca_lanzan_excepcion(self, garbage: str) -> None:
        """
        Cualquier entrada arbitraria devuelve bool sin lanzar ninguna excepción.

        Args:
            garbage: cadena arbitraria a probar.
        """
        result = validate_ean_checksum(garbage)
        assert isinstance(result, bool)


# ══════════════════════════════════════════════════════════════════════════════
# longest_prefix_match
# ══════════════════════════════════════════════════════════════════════════════


class TestLongestPrefixMatch:
    """
    Tests sobre la función longest_prefix_match().

    Verifica que se devuelva el valor asociado al prefijo más largo (de hasta
    10 dígitos, mínimo 6) que coincida con el inicio del EAN, y None cuando
    no hay ninguna coincidencia. La prioridad de prefijo más específico es el
    comportamiento clave que estos tests validan.

    :author: BenjaminDTS
    """

    # ── Coincidencias simples ─────────────────────────────────────────────────

    def test_coincidencia_exacta_7_digitos(self) -> None:
        """Prefijo exacto de 7 dígitos resuelve al valor correcto."""
        result = longest_prefix_match(
            _EAN13_AMANOVA,
            {"8413037": "Amanova"},
        )
        assert result == "Amanova"

    def test_coincidencia_6_digitos(self) -> None:
        """Prefijo de 6 dígitos (mínimo soportado) resuelve al valor correcto."""
        result = longest_prefix_match(
            _EAN13_AMANOVA,
            {"841303": "GenericBrand"},
        )
        assert result == "GenericBrand"

    def test_coincidencia_10_digitos(self) -> None:
        """Prefijo de 10 dígitos (máximo soportado) resuelve al valor correcto."""
        result = longest_prefix_match(
            _EAN13_AMANOVA,
            {"8413037335": "SuperSpecific"},
        )
        assert result == "SuperSpecific"

    # ── Prioridad del prefijo más largo ───────────────────────────────────────

    def test_prefijo_mas_largo_gana_sobre_mas_corto(self) -> None:
        """
        Cuando hay dos prefijos solapados, el más largo (más específico) gana.

        El EAN 8413037335779 coincide tanto con '841303' (6 dígitos) como con
        '8413037' (7 dígitos). Debe devolverse el valor del prefijo más largo.
        """
        result = longest_prefix_match(
            _EAN13_AMANOVA,
            {
                "841303": "Generic",
                "8413037": "Specific",
            },
        )
        assert result == "Specific"

    def test_prefijo_de_8_digitos_gana_sobre_7(self) -> None:
        """Prefijo de 8 dígitos tiene mayor prioridad que uno de 7."""
        result = longest_prefix_match(
            _EAN13_AMANOVA,
            {
                "8413037": "SevenDigit",
                "84130373": "EightDigit",
            },
        )
        assert result == "EightDigit"

    def test_tres_prefijos_solapados_devuelve_mas_largo(self) -> None:
        """Con tres prefijos solapados, el de mayor longitud siempre prevalece."""
        result = longest_prefix_match(
            _EAN13_AMANOVA,
            {
                "841303": "Six",
                "8413037": "Seven",
                "84130373": "Eight",
            },
        )
        assert result == "Eight"

    # ── Sin coincidencia ──────────────────────────────────────────────────────

    def test_sin_coincidencia_devuelve_none(self) -> None:
        """EAN con prefijo no registrado devuelve None."""
        result = longest_prefix_match(
            _EAN13_NO_PREFIX,
            {"8413037": "Amanova"},
        )
        assert result is None

    def test_diccionario_vacio_devuelve_none(self) -> None:
        """Diccionario de prefijos vacío siempre devuelve None."""
        result = longest_prefix_match(_EAN13_AMANOVA, {})
        assert result is None

    def test_prefijo_mas_largo_que_ean_no_coincide(self) -> None:
        """
        Prefijo con más dígitos que el EAN no puede coincidir y devuelve None.

        El EAN-8 tiene 8 dígitos; un prefijo de 9 dígitos nunca puede ser
        una subcadena inicial válida, por lo que longest_prefix_match lo ignora.
        """
        # _EAN8_VALID tiene 8 dígitos; intentamos con prefijo de 9
        result = longest_prefix_match(
            _EAN8_VALID,
            {"123456789": "TooLong"},
        )
        assert result is None

    def test_prefijo_de_6_digitos_de_ean8(self) -> None:
        """EAN-8 puede resolverse con un prefijo de 6 dígitos (dentro del rango)."""
        # _EAN8_VALID = _make_ean("1234567") → empieza por "1234567"
        # Un prefijo de 6 dígitos "123456" debe coincidir
        result = longest_prefix_match(
            _EAN8_VALID,
            {"123456": "FoundBrand"},
        )
        assert result == "FoundBrand"

    # ── Casos límite de valores ───────────────────────────────────────────────

    def test_prefijo_exacto_igual_al_ean_completo_no_se_busca(self) -> None:
        """
        Longest_prefix_match solo busca longitudes 10 → 6, no el EAN completo.
        Un prefijo de 13 dígitos (igual que el EAN) no entra en el rango de
        búsqueda y debe devolver None (a no ser que también haya un prefijo
        de longitud 6-10 que coincida).
        """
        result = longest_prefix_match(
            _EAN13_AMANOVA,
            {_EAN13_AMANOVA: "FullMatch"},  # clave de 13 dígitos, fuera del rango
        )
        # Función busca de longitud 10 a 6; 13 dígitos queda fuera
        assert result is None

    def test_multiples_prefijos_sin_solapamiento_devuelve_correcto(self) -> None:
        """
        Con varios prefijos registrados que NO solapan con el EAN dado,
        el método devuelve None correctamente.
        """
        result = longest_prefix_match(
            _EAN13_NO_PREFIX,     # empieza por "999999..."
            {
                "8413037": "Amanova",
                "540058": "OtherBrand",
                "123456": "ThirdBrand",
            },
        )
        assert result is None
