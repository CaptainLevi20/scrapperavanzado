from core.scrapers.families.supersalud import (
    _es_anexo,
    _fecha_publicacion,
    _parse_numero,
    _safe_title,
    _titulo,
)


# ---- _es_anexo ----
def test_es_anexo_true_for_accented_uppercase_prefix():
    assert _es_anexo("Anexo resolución número 2024910010006782-6 de 2024") is True
    assert _es_anexo("ANEXO RESOLUCION No. 2022910010007513-6 de 2022") is True


def test_es_anexo_false_for_normal_title():
    assert _es_anexo("Resolución número 2024910010006787-6 de 2024") is False
    assert _es_anexo("") is False
    assert _es_anexo(None) is False


# ---- _parse_numero ----
def test_parse_numero_radicado_form_takes_last_six_of_twelve_block():
    assert _parse_numero("2026151000000002-5", "") == 2
    assert _parse_numero("2022130000000054-5", "") == 54
    assert _parse_numero("2024910010006787-6", "") == 6787


def test_parse_numero_radicado_form_without_dash():
    assert _parse_numero("20221300000000545", "") == 54


def test_parse_numero_radicado_found_inside_anexo_title():
    assert _parse_numero(None, "Anexo resolución número 2024910010006782-6 de 2024") == 6782


def test_parse_numero_classic_form_strips_leading_zeros_and_trailing_year():
    assert _parse_numero("047", "") == 47
    assert _parse_numero("003 de 2019", "") == 3
    assert _parse_numero("10924 de 2018", "") == 10924


def test_parse_numero_falls_back_to_title_when_numero_raw_blank():
    assert _parse_numero("  ", "Circular Externa 006 de 2016") == 6


def test_parse_numero_returns_none_for_unparseable():
    assert _parse_numero("", "Por medio de la cual se ordena la toma de posesión") is None
    assert _parse_numero("010 de 2017     010 de 2017", "") is None
    assert _parse_numero(None, None) is None


def test_parse_numero_none_for_bare_non_radicado_long_digit_run():
    # 12 dígitos sueltos (no es radicado: _RADICADO_RE exige >=16) y excede el
    # tope clásico de 5 dígitos -> ambiguo -> None (no un título "verificado" con basura)
    assert _parse_numero("910010006787", "") is None


def test_parse_numero_none_when_two_number_runs_in_title_fallback():
    assert _parse_numero("", "Circular 5 modifica Circular 47 de 2016") is None


# ---- _safe_title ----
def test_safe_title_replaces_path_invalid_chars_and_trims():
    assert _safe_title('Doc/con "raros": x|y*') == "Doc-con -raros-- x-y-"
    assert _safe_title("  x.  ") == "x"


def test_safe_title_truncates_to_120():
    assert len(_safe_title("z" * 300)) == 120


# ---- _titulo ----
def test_titulo_verified_canonical_code():
    assert _titulo("C", "2026151000000002-5", "irrelevante", "2026", False) == ("C_SNS_0002_2026", False)
    assert _titulo("R", "2024910010006787-6", "irrelevante", "2024", False) == ("R_SNS_6787_2024", False)


def test_titulo_verified_anexo_gets_fixed_a01_suffix():
    assert _titulo(
        "R", None, "Anexo resolución número 2024910010006782-6 de 2024", "2024", True
    ) == ("R_SNS_6782_2024_A01", False)


def test_titulo_unverified_keeps_raw_title_trimmed_to_120():
    title, unv = _titulo("R", "", "Por medio de la cual se ordena la toma de posesión", "2013", False)
    assert unv is True
    assert title == "Por medio de la cual se ordena la toma de posesión"


def test_titulo_unverified_anexo_has_no_suffix():
    title, unv = _titulo("C", "", "Anexo - Tablas de referencia - CE", "2026", True)
    assert unv is True
    assert title == "Anexo - Tablas de referencia - CE"
    assert not title.endswith("_A01")


# ---- _fecha_publicacion ----
def test_fecha_publicacion_takes_first_half_of_doubled_value():
    raw = "2026-09-04T05:00:00Z\n\n2026-09-04T05:00:00.0000000Z"
    assert _fecha_publicacion(raw) == "2026-09-04"


def test_fecha_publicacion_single_value():
    assert _fecha_publicacion("2021-08-18T05:00:00.0000000Z") == "2021-08-18"


def test_fecha_publicacion_none_when_missing_or_unparseable():
    assert _fecha_publicacion(None) is None
    assert _fecha_publicacion("") is None
    assert _fecha_publicacion("sin fecha") is None
