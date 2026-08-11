from datetime import date

from core.fecha_es import parse_fecha_providencia_es


def test_dia_en_digitos():
    assert parse_fecha_providencia_es("Bogotá, 8 de mayo de 2026") == date(2026, 5, 8)


def test_dia_en_digitos_con_cero():
    assert parse_fecha_providencia_es("05 de marzo de 2026") == date(2026, 3, 5)


def test_dia_en_letras_con_numero_entre_parentesis():
    txt = "Bogotá, diez (10) de agosto de dos mil veintiséis (2026)"
    assert parse_fecha_providencia_es(txt) == date(2026, 8, 10)


def test_con_salto_de_linea():
    assert parse_fecha_providencia_es("6 de agosto \n de 2026") == date(2026, 8, 6)


def test_toma_la_primera_fecha_valida():
    txt = "Auto del 2 de junio de 2026 que confirma el del 3 de octubre de 2025"
    assert parse_fecha_providencia_es(txt) == date(2026, 6, 2)


def test_sin_fecha_devuelve_none():
    assert parse_fecha_providencia_es("No hay fecha aquí") is None


def test_mes_invalido_devuelve_none():
    assert parse_fecha_providencia_es("32 de mayo de 2026") is None
