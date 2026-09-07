import datetime

from core.scrapers.families.ssf import (
    _fecha_corta,
    _fecha_slash,
    _num_circular,
    _num_resolucion,
    _safe_title,
    _titulo,
)


# ---- fechas ----
def test_fecha_corta_ddmmyy_to_20yy():
    assert _fecha_corta("RESOLUCIÓN RES. 0789 DE 15-09-26") == datetime.date(2026, 9, 15)


def test_fecha_corta_none_when_absent_or_invalid():
    assert _fecha_corta("RESOLUCIÓN 1617 del 30 de diciembre de 2025") is None
    assert _fecha_corta("32-13-26") is None


def test_fecha_slash_ddmmyyyy():
    assert _fecha_slash("17/12/2025") == datetime.date(2025, 12, 17)
    assert _fecha_slash("6/10/2003") == datetime.date(2003, 10, 6)


def test_fecha_slash_none_when_absent_or_invalid():
    assert _fecha_slash("sin fecha") is None
    assert _fecha_slash("30/02/2025") is None


# ---- número circular ----
def test_num_circular_with_ce_prefix():
    assert _num_circular("CE 00011") == ("11", "")


def test_num_circular_without_ce_prefix():
    assert _num_circular("00002") == ("2", "")


def test_num_circular_letter_suffix_uppercased():
    assert _num_circular("CE 0003A") == ("3", "A")


def test_num_circular_none_when_no_digits():
    assert _num_circular("") is None
    assert _num_circular("circular externa") is None


# ---- número resolución ----
def test_num_resolucion_from_asunto_first():
    assert _num_resolucion('Resolución 0789 del 15 de Agosto de 2026 "x"', "RESOLUCIÓN RES. 0789 DE 15-09-26") == "0789"


def test_num_resolucion_falls_back_to_documento():
    assert _num_resolucion("texto sin numero de resolucion", "RESOLUCIÓN RES. 0612 DE 03-08-26") == "0612"
    assert _num_resolucion("", "RESOLUCIÓN 1617 del 30 de diciembre de 2025") == "1617"


def test_num_resolucion_none_when_unparseable():
    assert _num_resolucion("por la cual se hace algo", "documento raro") is None


# ---- título ----
def test_titulo_verified_resolucion():
    assert _titulo("R", "0789", "", 2026, "irrelevante") == ("R_SSF_0789_2026", False)


def test_titulo_verified_circular_with_letter_suffix():
    assert _titulo("C", "3", "A", 2024, "irrelevante") == ("C_SSF_0003A_2024", False)


def test_titulo_unverified_keeps_raw_trimmed():
    title, unv = _titulo("R", None, "", 2025, "RESOLUCIÓN 99 rara del sitio")
    assert unv is True
    assert title == "RESOLUCIÓN 99 rara del sitio"


def test_titulo_unverified_empty_raw_falls_back_to_documento():
    assert _titulo("C", None, "", 2025, "") == ("documento", True)


# ---- safe_title ----
def test_safe_title_replaces_invalid_and_trims():
    assert _safe_title('Doc/con "raros": x|y*  .') == "Doc-con -raros-- x-y-"
    assert len(_safe_title("z" * 300)) == 120
