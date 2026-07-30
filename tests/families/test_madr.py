from core.scrapers.families.madr import _normalize_title, _parse_fecha, _resto_tras_numero


def test_resto_tras_numero_strips_everything_up_to_and_including_the_number():
    assert _resto_tras_numero("DECRETO 0765 DEL 15 DE JULIO DEL 2026", "0765") == " DEL 15 DE JULIO DEL 2026"


def test_resto_tras_numero_avoids_reading_the_act_number_as_a_day():
    # Sin este recorte, "21" (los últimos dos dígitos de "2321") se leería
    # como un día válido y produciría "2023-09-21" en vez de "2023-09-01".
    assert _resto_tras_numero("LEY 2321 DE SEPTIEMBRE DE 2023", "2321") == " DE SEPTIEMBRE DE 2023"


def test_resto_tras_numero_returns_full_text_when_number_not_found():
    assert _resto_tras_numero("Documento sin número reconocible", "9999") == "Documento sin número reconocible"


def test_normalize_title_builds_canonical_code():
    assert _normalize_title("D", "765", "2026") == "D_MADR_0765_2026"


def test_normalize_title_pads_short_numbers_to_four_digits():
    assert _normalize_title("R", "179", "2026") == "R_MADR_0179_2026"


def test_normalize_title_uses_conpes_literal_instead_of_a_single_letter():
    assert _normalize_title("CONPES", "4076", "2022") == "CONPES_MADR_4076_2022"


def test_parse_fecha_dia_de_mes_del_anio():
    assert _parse_fecha(" DEL 15 DE JULIO DEL 2026") == "2026-07-15"


def test_parse_fecha_dia_mes_sin_conector_de():
    # Variante real sin "DE" entre día y mes: "DEL 27 JULIO DE 2026".
    assert _parse_fecha(" DEL 27 JULIO DE 2026") == "2026-07-27"


def test_parse_fecha_mes_dia_anio_orden_invertido():
    # Variante real con mes antes del día: "DE MAYO 4 DE 2026".
    assert _parse_fecha(" DE MAYO 4 DE 2026") == "2026-05-04"


def test_parse_fecha_mes_anio_sin_dia():
    assert _parse_fecha(" DE OCTUBRE DE 2023") == "2023-10-01"


def test_parse_fecha_solo_anio():
    assert _parse_fecha(" DE 2023") == "2023-01-01"


def test_parse_fecha_conpes_siempre_solo_anio():
    assert _parse_fecha(" DE 2022") == "2022-01-01"


def test_parse_fecha_returns_none_when_no_date_found():
    assert _parse_fecha("texto sin fecha reconocible") is None


def test_parse_fecha_is_case_insensitive():
    assert _parse_fecha(" del 19 de mayo de 2023") == "2023-05-19"


def test_parse_fecha_does_not_misread_trailing_act_number_digits_as_a_day():
    # Regresión del caso documentado en _resto_tras_numero: si a _parse_fecha
    # se le pasara el título completo en vez del resto ya recortado, "21" (de
    # "2321") se leería como día. Aquí se prueba directamente sobre el resto
    # ya recortado, que es como _extraer_articulos debe invocarlo siempre.
    resto = _resto_tras_numero("LEY 2321 DE SEPTIEMBRE DE 2023", "2321")
    assert _parse_fecha(resto) == "2023-09-01"
