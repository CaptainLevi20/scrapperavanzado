import datetime

import pytest

from core.scrapers.families.minsalud import (
    _mes_boletin,
    _norm,
    _numero_norma,
    _radicado,
    _sin_extension,
)


def test_norm_quita_acentos_y_minusculas():
    # NFKD convierte el ordinal "º" en "o": "Nº" queda "no", que el marcador de número ya reconoce
    assert _norm("Resolución JURÍDICO Nº") == "resolucion juridico no"


def test_sin_extension():
    assert _sin_extension("Resolución No 1809 de 2026.pdf") == "Resolución No 1809 de 2026"
    assert _sin_extension("Circular externa No. 0015.PDF") == "Circular externa No. 0015"
    assert _sin_extension("Sin extension") == "Sin extension"


@pytest.mark.parametrize("texto,esperado", [
    # regla 1: número + año (tolerando de/del y fecha en prosa en medio)
    ("Resolución No. 1809 de 2026", 1809),
    ("Resolucion No 276 de 2019", 276),
    ("Resolución No.2722 de 2019", 2722),
    ("Resolución 1099 del 2020", 1099),
    ("Resolución No. 0304de 2015", 304),
    ("Resolución No. 001133 de 2017", 1133),
    ("Resolución Nro.00532 de 2017", 532),
    ("Resolución 013956 de 2016", 13956),
    ("Circular No. 45 del 31 de Dciiembre del 2019", 45),
    ("Circular Externa No 0031 de 2026", 31),
    ("Circualr No. 12 de 2016", 12),
    ("Modificación transitoria resolución 227 de 2020", 227),
    # regla 2: número tras el marcador No/Nº/N° (con . o _ opcional)
    ("Circular externa No. 0015", 15),
    ("Circular externa No_9 Minsalud y UNGRD", 9),
    # regla 3: número al inicio
    ("3312 Establece requisitos - condiciones para giro", 3312),
    # regla 4: último número del nombre
    ("Circular Conjunta 036", 36),
])
def test_numero_norma(texto, esperado):
    assert _numero_norma(texto) == esperado


@pytest.mark.parametrize("texto", ["Alcance a la Circular Salud   Vida", "Res", "", None])
def test_numero_norma_none(texto):
    assert _numero_norma(texto) is None


@pytest.mark.parametrize("texto,esperado", [
    ("Concepto Jurídico 201711601019341 de 2017", "201711601019341"),
    ("CONCEPTO JURÍDICO 2026423003321522 ID 2258969 7", "2026423003321522"),
    ("Concepto Jurídico No 2026424000867002", "2026424000867002"),
    ("Concepto Jurídico  202211600135321 de 2022", "202211600135321"),
])
def test_radicado(texto, esperado):
    assert _radicado(texto) == esperado


@pytest.mark.parametrize("texto", ["Decreto No. 1600 de 2022", "Concepto 12345 de 2020", "", None])
def test_radicado_none(texto):
    assert _radicado(texto) is None


@pytest.mark.parametrize("texto,fecha,esperado", [
    ("Boletín Jurídico No 5 Mayo 2016", None, 5),
    ("Boletín Jurídico No. 002 de febrero 2025", None, 2),
    ("Boletín Jurídico No 12 Diciembre de 2019", None, 12),
    ("Boletín Jurídico No 9 Setiembre 2018", None, 9),
    ("Boletin Juridico No 4 del 2015", None, 4),
    ("Boletín Jurídico No. 06  de 2026", None, 6),
    ("Boletín Jurídico especial", datetime.date(2020, 7, 31), 7),
    ("Boletín Jurídico Diciembre - Noviembre 2015", None, 12),
])
def test_mes_boletin(texto, fecha, esperado):
    assert _mes_boletin(texto, fecha) == esperado


@pytest.mark.parametrize("texto", ["Boletín Jurídico especial", "Boletín Jurídico No 15 de 2020"])
def test_mes_boletin_none(texto):
    assert _mes_boletin(texto, None) is None
