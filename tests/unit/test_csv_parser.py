"""
Tests unitarios para services/csv_parser.py.

Cubre todos los caminos de parsear(), _construir_query(), _sanitizar()
y _validar_columnas() sin necesidad de mocks, ya que el parser es pure Python.

:author: BenjaminDTS
:version: 1.0.0
"""

import pytest

from api.v1.schemas.job import ModosBusqueda, SearchConfig
from services.csv_parser import (
    CsvParser,
    CsvParserError,
    Producto,
    ResultadoParseo,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _config(modo: ModosBusqueda, query_personalizada: str | None = None) -> SearchConfig:
    """
    Crea un SearchConfig mínimo para los tests.

    Args:
        modo: Modo de búsqueda a usar.
        query_personalizada: Plantilla opcional para el modo PERSONALIZADO.

    Returns:
        Instancia de SearchConfig lista para usar en el parser.
    """
    return SearchConfig(modo=modo, query_personalizada=query_personalizada)


def _parser(modo: ModosBusqueda, query_personalizada: str | None = None) -> CsvParser:
    """
    Construye un CsvParser con la configuración indicada.

    Args:
        modo: Modo de búsqueda a usar.
        query_personalizada: Plantilla opcional para el modo PERSONALIZADO.

    Returns:
        Instancia de CsvParser lista para usar.
    """
    return CsvParser(_config(modo, query_personalizada))


# ── Helpers de CSV inline ──────────────────────────────────────────────────────

_CSV_NOMBRE_MARCA = (
    "codigo,nombre,marca\n"
    "001,Producto A,Marca X\n"
    "002,Producto B,Marca Y\n"
)

_CSV_EAN = (
    "codigo,nombre,marca,ean\n"
    "001,Producto A,Marca X,1234567890123\n"
)

_CSV_SOLO_CABECERA_NOMBRE_MARCA = "codigo,nombre,marca\n"

_CSV_SIN_COLUMNA_CODIGO = "nombre,marca\nProducto A,Marca X\n"

_CSV_CODIGO_VACIO = (
    "codigo,nombre,marca\n"
    ",Producto Sin Codigo,Marca Z\n"
    "002,Producto Valido,Marca Y\n"
)

_CSV_PUNTO_Y_COMA = (
    "codigo;nombre;marca\n"
    "001;Producto A;Marca X\n"
)

_CSV_COLUMNAS_EXTRA = (
    "codigo,nombre,marca,categoria,precio\n"
    "001,Producto A,Marca X,Electronica,99.99\n"
)

_CSV_EAN_CAMPO_VACIO = (
    "codigo,nombre,marca,ean\n"
    "001,Producto A,Marca X,\n"
)

_CSV_NOMBRE_MARCA_SIN_MARCA = (
    "codigo,nombre,marca\n"
    "001,Producto Solo Nombre,\n"
)


# ══════════════════════════════════════════════════════════════════════════════
# parsear()
# ══════════════════════════════════════════════════════════════════════════════

class TestParsear:
    """
    Tests sobre el método público parsear() de CsvParser.

    Verifica el comportamiento completo del flujo de parseo, incluyendo
    detección de errores, generación de productos y tolerancia a CSVs
    con diferentes formatos y delimitadores.

    :author: BenjaminDTS
    """

    def test_csv_vacio_lanza_error(self) -> None:
        """CSV vacío (cadena vacía) debe lanzar CsvParserError."""
        parser = _parser(ModosBusqueda.NOMBRE_MARCA)

        with pytest.raises(CsvParserError, match="vacío"):
            parser.parsear("")

    def test_csv_solo_espacios_lanza_error(self) -> None:
        """CSV con solo espacios en blanco debe lanzar CsvParserError."""
        parser = _parser(ModosBusqueda.NOMBRE_MARCA)

        with pytest.raises(CsvParserError, match="vacío"):
            parser.parsear("   \n  ")

    def test_csv_solo_cabecera_devuelve_resultado_vacio(self) -> None:
        """CSV con cabecera pero sin filas de datos devuelve lista vacía sin errores."""
        parser = _parser(ModosBusqueda.NOMBRE_MARCA)

        resultado = parser.parsear(_CSV_SOLO_CABECERA_NOMBRE_MARCA)

        assert isinstance(resultado, ResultadoParseo)
        assert resultado.productos == []
        assert resultado.errores == []

    def test_csv_sin_columna_codigo_lanza_error(self) -> None:
        """CSV sin la columna 'codigo' debe lanzar CsvParserError."""
        parser = _parser(ModosBusqueda.NOMBRE_MARCA)

        with pytest.raises(CsvParserError, match="codigo"):
            parser.parsear(_CSV_SIN_COLUMNA_CODIGO)

    def test_csv_valido_modo_nombre_marca_genera_productos(self) -> None:
        """CSV válido en modo NOMBRE_MARCA produce productos con query 'nombre marca'."""
        parser = _parser(ModosBusqueda.NOMBRE_MARCA)

        resultado = parser.parsear(_CSV_NOMBRE_MARCA)

        assert len(resultado.productos) == 2
        assert resultado.errores == []

        p1 = resultado.productos[0]
        assert p1.codigo == "001"
        assert p1.nombre == "Producto A"
        assert p1.marca == "Marca X"
        assert p1.query == "Producto A Marca X"

    def test_csv_valido_modo_ean_genera_productos(self) -> None:
        """CSV válido en modo EAN produce productos con query en formato exacto ("EAN")."""
        parser = _parser(ModosBusqueda.EAN)

        resultado = parser.parsear(_CSV_EAN)

        assert len(resultado.productos) == 1
        assert resultado.errores == []

        p = resultado.productos[0]
        assert p.ean == "1234567890123"
        assert p.query == '"1234567890123"'

    def test_fila_con_codigo_vacio_va_a_errores(self) -> None:
        """Fila con campo 'codigo' vacío se registra en errores y no en productos."""
        parser = _parser(ModosBusqueda.NOMBRE_MARCA)

        resultado = parser.parsear(_CSV_CODIGO_VACIO)

        assert len(resultado.productos) == 1
        assert resultado.productos[0].codigo == "002"
        assert len(resultado.errores) == 1
        assert "codigo" in resultado.errores[0].lower()

    def test_delimitador_punto_y_coma_se_detecta_automaticamente(self) -> None:
        """CSV con delimitador ';' debe detectarse y parsearse correctamente."""
        parser = _parser(ModosBusqueda.NOMBRE_MARCA)

        resultado = parser.parsear(_CSV_PUNTO_Y_COMA)

        assert len(resultado.productos) == 1
        assert resultado.productos[0].codigo == "001"
        assert resultado.productos[0].nombre == "Producto A"

    def test_columnas_extra_se_preservan_en_datos_extra(self) -> None:
        """Columnas no reconocidas deben guardarse en el dict datos_extra del Producto."""
        parser = _parser(ModosBusqueda.NOMBRE_MARCA)

        resultado = parser.parsear(_CSV_COLUMNAS_EXTRA)

        assert len(resultado.productos) == 1
        p = resultado.productos[0]
        assert "categoria" in p.datos_extra
        assert p.datos_extra["categoria"] == "Electronica"
        assert "precio" in p.datos_extra
        assert p.datos_extra["precio"] == "99.99"

    def test_modo_ean_sin_columna_ean_lanza_error(self) -> None:
        """Modo EAN con CSV que carece de columna 'ean' debe lanzar CsvParserError."""
        parser = _parser(ModosBusqueda.EAN)

        with pytest.raises(CsvParserError, match="ean"):
            parser.parsear(_CSV_NOMBRE_MARCA)

    def test_modo_nombre_marca_sin_columnas_requeridas_lanza_error(self) -> None:
        """Modo NOMBRE_MARCA con CSV sin columna 'nombre' o 'marca' lanza CsvParserError."""
        csv_sin_marca = "codigo,nombre\n001,Producto A\n"
        parser = _parser(ModosBusqueda.NOMBRE_MARCA)

        with pytest.raises(CsvParserError, match="marca"):
            parser.parsear(csv_sin_marca)

    def test_numero_fila_original_es_correcto(self) -> None:
        """El campo fila_original del Producto debe reflejar la línea real del CSV."""
        parser = _parser(ModosBusqueda.NOMBRE_MARCA)

        resultado = parser.parsear(_CSV_NOMBRE_MARCA)

        assert resultado.productos[0].fila_original == 2
        assert resultado.productos[1].fila_original == 3


# ══════════════════════════════════════════════════════════════════════════════
# _construir_query()
# ══════════════════════════════════════════════════════════════════════════════

class TestConstruirQuery:
    """
    Tests directos sobre _construir_query() a través del flujo de parsear().

    Se ejerce cada rama de la lógica de construcción de query verificando
    el campo .query del Producto resultante.

    :author: BenjaminDTS
    """

    def test_nombre_marca_con_ambos_campos(self) -> None:
        """Modo NOMBRE_MARCA con nombre y marca produce 'nombre marca'."""
        parser = _parser(ModosBusqueda.NOMBRE_MARCA)
        resultado = parser.parsear(_CSV_NOMBRE_MARCA)

        assert resultado.productos[0].query == "Producto A Marca X"

    def test_nombre_marca_solo_nombre_sin_marca(self) -> None:
        """Modo NOMBRE_MARCA con marca vacía produce solo el nombre."""
        parser = _parser(ModosBusqueda.NOMBRE_MARCA)
        resultado = parser.parsear(_CSV_NOMBRE_MARCA_SIN_MARCA)

        assert resultado.productos[0].query == "Producto Solo Nombre"

    def test_ean_devuelve_el_ean_entre_comillas(self) -> None:
        """Modo EAN devuelve el EAN envuelto en comillas dobles para búsqueda exacta."""
        parser = _parser(ModosBusqueda.EAN)
        resultado = parser.parsear(_CSV_EAN)

        assert resultado.productos[0].query == '"1234567890123"'

    def test_ean_vacio_registra_error(self) -> None:
        """Modo EAN con campo ean vacío genera un error en la fila correspondiente."""
        parser = _parser(ModosBusqueda.EAN)
        resultado = parser.parsear(_CSV_EAN_CAMPO_VACIO)

        assert resultado.productos == []
        assert len(resultado.errores) == 1
        assert "ean" in resultado.errores[0].lower()

    def test_personalizado_con_plantilla_expande_placeholders(self) -> None:
        """Modo PERSONALIZADO expande {nombre}, {marca}, {ean} y {codigo} en la query."""
        plantilla = "{nombre} {marca} {codigo} imagen"
        parser = _parser(ModosBusqueda.PERSONALIZADO, query_personalizada=plantilla)

        csv = "codigo,nombre,marca,ean\n001,Prod A,Marca X,9876\n"
        resultado = parser.parsear(csv)

        assert resultado.productos[0].query == "Prod A Marca X 001 imagen"

    def test_personalizado_sin_plantilla_registra_error(self) -> None:
        """Modo PERSONALIZADO con query_personalizada=None genera error en cada fila."""
        parser = _parser(ModosBusqueda.PERSONALIZADO, query_personalizada=None)

        csv = "codigo,nombre,marca\n001,Prod A,Marca X\n"
        resultado = parser.parsear(csv)

        assert resultado.productos == []
        assert len(resultado.errores) == 1
        assert "personalizado" in resultado.errores[0].lower()


# ══════════════════════════════════════════════════════════════════════════════
# _sanitizar()
# ══════════════════════════════════════════════════════════════════════════════

class TestSanitizar:
    """
    Tests directos sobre el método estático _sanitizar().

    Verifica el trimming, la eliminación de caracteres peligrosos y el
    truncado a la longitud máxima permitida.

    :author: BenjaminDTS
    """

    def test_trim_de_espacios(self) -> None:
        """Valor con espacios al inicio y al final debe ser recortado."""
        resultado = CsvParser._sanitizar("  hola mundo  ")

        assert resultado == "hola mundo"

    def test_elimina_caracter_menor_que(self) -> None:
        """El carácter '<' debe ser eliminado por ser potencialmente peligroso."""
        resultado = CsvParser._sanitizar("valor<script")

        assert "<" not in resultado
        assert resultado == "valorscript"

    def test_elimina_caracter_mayor_que(self) -> None:
        """El carácter '>' debe ser eliminado."""
        resultado = CsvParser._sanitizar("valor>script")

        assert ">" not in resultado

    def test_elimina_comilla_doble(self) -> None:
        """Las comillas dobles deben ser eliminadas."""
        resultado = CsvParser._sanitizar('valor"peligroso')

        assert '"' not in resultado

    def test_elimina_comilla_simple(self) -> None:
        """Las comillas simples deben ser eliminadas."""
        resultado = CsvParser._sanitizar("valor'peligroso")

        assert "'" not in resultado

    def test_elimina_barra_invertida(self) -> None:
        """La barra invertida debe ser eliminada."""
        resultado = CsvParser._sanitizar("valor\\peligroso")

        assert "\\" not in resultado

    def test_elimina_punto_y_coma(self) -> None:
        """El punto y coma debe ser eliminado."""
        resultado = CsvParser._sanitizar("valor;peligroso")

        assert ";" not in resultado

    def test_elimina_todos_los_caracteres_peligrosos_juntos(self) -> None:
        """Todos los caracteres peligrosos juntos deben ser eliminados de una vez."""
        resultado = CsvParser._sanitizar('<>"\'\\;texto')

        assert resultado == "texto"

    def test_trunca_a_500_caracteres(self) -> None:
        """Valor con más de 500 caracteres debe ser truncado exactamente a 500."""
        valor_largo = "a" * 600

        resultado = CsvParser._sanitizar(valor_largo)

        assert len(resultado) == 500

    def test_valor_normal_sin_cambios(self) -> None:
        """Valor sin caracteres especiales ni espacios extra no debe modificarse."""
        resultado = CsvParser._sanitizar("Producto Normal 123")

        assert resultado == "Producto Normal 123"

    def test_valor_exactamente_500_caracteres_no_se_trunca(self) -> None:
        """Valor con exactamente 500 caracteres no debe modificarse."""
        valor = "b" * 500

        resultado = CsvParser._sanitizar(valor)

        assert len(resultado) == 500
        assert resultado == valor


# ══════════════════════════════════════════════════════════════════════════════
# _validar_columnas()
# ══════════════════════════════════════════════════════════════════════════════

class TestValidarColumnas:
    """
    Tests sobre _validar_columnas() ejercidos a través de parsear().

    Verifica que se validen correctamente las columnas requeridas según el
    modo de búsqueda activo y que se lancen los errores apropiados.

    :author: BenjaminDTS
    """

    def test_modo_nombre_marca_requiere_nombre_y_marca(self) -> None:
        """Modo NOMBRE_MARCA lanza error si faltan las columnas 'nombre' o 'marca'."""
        csv_invalido = "codigo,ean\n001,1234\n"
        parser = _parser(ModosBusqueda.NOMBRE_MARCA)

        with pytest.raises(CsvParserError):
            parser.parsear(csv_invalido)

    def test_modo_ean_requiere_columna_ean(self) -> None:
        """Modo EAN lanza error si falta la columna 'ean'."""
        csv_invalido = "codigo,nombre,marca\n001,Prod A,Marca X\n"
        parser = _parser(ModosBusqueda.EAN)

        with pytest.raises(CsvParserError, match="ean"):
            parser.parsear(csv_invalido)

    def test_modo_personalizado_no_requiere_columnas_adicionales(self) -> None:
        """Modo PERSONALIZADO no valida columnas extra más allá de 'codigo'."""
        csv_minimo = "codigo,nombre,marca\n001,Prod A,Marca X\n"
        plantilla = "{codigo} producto"
        parser = _parser(ModosBusqueda.PERSONALIZADO, query_personalizada=plantilla)

        resultado = parser.parsear(csv_minimo)

        assert len(resultado.productos) == 1
        assert resultado.productos[0].query == "001 producto"

    def test_columna_codigo_siempre_obligatoria(self) -> None:
        """La columna 'codigo' es obligatoria independientemente del modo."""
        csv_sin_codigo = "nombre,marca\nProd A,Marca X\n"

        for modo in ModosBusqueda:
            parser = _parser(modo)
            with pytest.raises(CsvParserError, match="codigo"):
                parser.parsear(csv_sin_codigo)

    def test_cabeceras_con_espacios_se_normalizan(self) -> None:
        """Cabeceras con espacios antes o después deben ser normalizadas y reconocidas."""
        csv_con_espacios = " codigo , nombre , marca \n001,Prod A,Marca X\n"
        parser = _parser(ModosBusqueda.NOMBRE_MARCA)

        resultado = parser.parsear(csv_con_espacios)

        assert len(resultado.productos) == 1
        assert resultado.productos[0].codigo == "001"
