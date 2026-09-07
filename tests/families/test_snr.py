from core.scrapers.families.snr import (
    _parse_codigo,
    _resultados_total,
    _safe_title,
    _titulo,
)


# ---- _parse_codigo ----
def test_parse_codigo_circular():
    assert _parse_codigo('CIR-2026-000348-4 del 03 de septiembre del 2026 "x"') == ("C", 348, 2026)


def test_parse_codigo_resolucion_five_digit_consecutive():
    assert _parse_codigo('RES-2026-021492-6 del 20 de agosto de 2026 "x"') == ("R", 21492, 2026)


def test_parse_codigo_none_for_old_format():
    assert _parse_codigo("RES.445-2019EXPTE.407-2017") is None
    assert _parse_codigo("Circular informativa sin código") is None
    assert _parse_codigo("") is None


# ---- _titulo ----
def test_titulo_verified_circular():
    assert _titulo(("C", 348, 2026), "irrelevante") == ("C_SNR_0348_2026", False)


def test_titulo_verified_resolucion_keeps_five_digits():
    assert _titulo(("R", 21492, 2026), "irrelevante") == ("R_SNR_21492_2026", False)


def test_titulo_unverified_keeps_raw_trimmed():
    title, unv = _titulo(None, "RES.445-2019 texto libre del sitio")
    assert unv is True
    assert title == "RES.445-2019 texto libre del sitio"


def test_titulo_unverified_empty_falls_back_to_documento():
    assert _titulo(None, "   ") == ("documento", True)


# ---- _resultados_total ----
def test_resultados_total_reads_and_strips_separators():
    assert _resultados_total("<div>Resultados 355</div>") == 355
    assert _resultados_total("Resultados 10.901 circulares") == 10901
    assert _resultados_total("Resultados 2,634") == 2634


def test_resultados_total_minus_one_when_absent():
    assert _resultados_total("<html>sin conteo</html>") == -1


# ---- _safe_title ----
def test_safe_title_sanitizes_and_trims():
    assert _safe_title('Doc/con "raros": x|y*  .') == "Doc-con -raros-- x-y-"
    assert len(_safe_title("z" * 300)) == 120
