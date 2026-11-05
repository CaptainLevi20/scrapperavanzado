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


def test_forma_a_los_dias_del_mes_de_con_del_anio():
    # Cierre formal frecuente en providencias colombianas.
    txt = "a los diez (10) días del mes de agosto del año dos mil veintiséis (2026)"
    assert parse_fecha_providencia_es(txt) == date(2026, 8, 10)


def test_forma_dias_del_mes_con_dia_en_digitos():
    assert parse_fecha_providencia_es("a los 5 días del mes de marzo de 2026") == date(2026, 3, 5)


def test_conector_del_entre_mes_y_anio():
    assert parse_fecha_providencia_es("8 de mayo del 2026") == date(2026, 5, 8)


def test_dias_del_mes_singular_sin_tilde():
    assert parse_fecha_providencia_es("a 1 dia del mes de enero de 2026") == date(2026, 1, 1)


def test_sin_de_entre_dia_y_mes():
    # La SSF escribe "del 31 marzo de 2026" (sin el primer "de").
    assert parse_fecha_providencia_es("Resolución 0789 del 31 marzo de 2026") == date(2026, 3, 31)
    # La forma canónica "con de" sigue funcionando.
    assert parse_fecha_providencia_es("Resolución 0789 del 31 de marzo de 2026") == date(2026, 3, 31)


def test_mes_y_anio_sin_conector():
    # Cámara de Comercio de Armenia y Corporinoquia (PR #110) escriben a veces
    # el año sin "de": cada una tenía su propia copia del lector de fechas
    # para eso. Ahora lo entiende el lector común.
    # Solo si la fuente lo pide: en general es peligroso (ver la prueba de abajo).
    assert parse_fecha_providencia_es("06 DE MARZO 2017", anio_sin_conector=True) == date(2017, 3, 6)
    assert parse_fecha_providencia_es("ACUERDO 200.3-2-26-001 DEL 05 ENERO 2026", anio_sin_conector=True) == date(2026, 1, 5)
    assert parse_fecha_providencia_es("200.3.2-25-004 08 DE ABRIL 2025", anio_sin_conector=True) == date(2025, 4, 8)


def test_sin_pedirlo_el_anio_sin_conector_no_se_acepta():
    # MinSalud: "Boletín Jurídico No 12 Diciembre 2025" — el 12 es el número
    # del boletín, no el día. Por eso el año sin "de" es una opción de cada
    # fuente y no el comportamiento general.
    assert parse_fecha_providencia_es("Boletín Jurídico No 12 Diciembre 2025") is None
    assert parse_fecha_providencia_es("06 DE MARZO 2017") is None


def test_el_dia_no_sale_del_final_de_otro_numero():
    # "-012 DE MARZO" es el número de un acuerdo, no el día 12 (protección que
    # tenía la copia de Corporinoquia).
    assert parse_fecha_providencia_es("ACUERDO 200.3-2-25-012 DE MARZO 2025", anio_sin_conector=True) is None
    assert parse_fecha_providencia_es("Acuerdo 012 de marzo de 2025") is None
    assert parse_fecha_providencia_es("2876 de 14 de octubre de 2026") == date(2026, 10, 14)
