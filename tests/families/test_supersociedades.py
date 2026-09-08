from core.scrapers.families.supersociedades import (
    _anio,
    _fecha_de_periodo,
    _mes_a_sigla,
    _periodo_contable,
    _periodo_juridico,
    _safe_title,
    _titulo,
)


def test_mes_a_sigla_todos_los_meses():
    pares = {
        "enero": "ENE", "Febrero": "FEB", "MARZO": "MAR", "abril": "ABR",
        "mayo": "MAY", "junio": "JUN", "julio": "JUL", "Agosto": "AGO",
        "septiembre": "SEP", "Octubre": "OCT", "noviembre": "NOV", "DICIEMBRE": "DIC",
    }
    for nombre, sigla in pares.items():
        assert _mes_a_sigla(f"Boletín Jurídico {nombre} 2026") == sigla


def test_mes_a_sigla_none_sin_mes():
    assert _mes_a_sigla("Boletín Informativo Contable 2017") is None
    assert _mes_a_sigla("") is None


def test_anio_primero_valido():
    assert _anio("BOLETÍN CONCEPTOS JURÍDICOS JULIO 2026") == 2026
    assert _anio("Boletín Contable 2021 - Semestre II") == 2021
    assert _anio("sin año") is None
    assert _anio("año 1999") is None


def test_periodo_juridico_ambos_formatos_de_titulo():
    assert _periodo_juridico("Boletín Jurídico Agosto 2026") == ("AGO", 2026)
    assert _periodo_juridico("BOLETÍN CONCEPTOS JURÍDICOS JULIO 2026") == ("JUL", 2026)


def test_periodo_juridico_none_si_falta_mes_o_anio():
    assert _periodo_juridico("Boletín Jurídico 2026") is None
    assert _periodo_juridico("Boletín Jurídico Agosto") is None


def test_periodo_contable_semestre_romano_y_arabigo():
    assert _periodo_contable("Boletín Informativo Contable 2026 - Semestre I") == ("SI", 2026)
    assert _periodo_contable("Boletín Informativo Contable 2025 - Semestre II") == ("SII", 2025)
    assert _periodo_contable("Boletín Contable 2022 - Semestre 2") == ("SII", 2022)
    assert _periodo_contable("Boletín Contable 2023 - Semestre 1") == ("SI", 2023)


def test_periodo_contable_por_mes_cuando_no_dice_semestre():
    assert _periodo_contable("Boletin Contable Diciembre 2023") == ("SII", 2023)
    assert _periodo_contable("Boletin Contable Marzo 2019") == ("SI", 2019)


def test_periodo_contable_none_sin_semestre_ni_mes():
    assert _periodo_contable("Boletín Informativo Contable 2017") is None


def test_fecha_de_periodo():
    assert _fecha_de_periodo("Boletín Jurídico", ("AGO", 2026)) == "2026-08-01"
    assert _fecha_de_periodo("Boletín Jurídico", ("ENE", 2020)) == "2020-01-01"
    assert _fecha_de_periodo("Boletín Contable", ("SI", 2026)) == "2026-06-30"
    assert _fecha_de_periodo("Boletín Contable", ("SII", 2025)) == "2025-12-31"


def test_titulo_verificado_y_fallback():
    assert _titulo("Boletín Jurídico", ("AGO", 2026), "irrelevante") == ("BOL_SS_AGO_2026", False)
    assert _titulo("Boletín Contable", ("SI", 2026), "irrelevante") == ("BOL_SS_SI_2026", False)
    t, unv = _titulo("Boletín Contable", None, "Boletín Informativo Contable 2017")
    assert unv is True and t == "Boletín Informativo Contable 2017"
    assert _titulo("Boletín Jurídico", None, "   ") == ("documento", True)


def test_safe_title_sanea_y_recorta():
    assert _safe_title('a/b:c"  .') == "a-b-c-"
    assert len(_safe_title("z" * 200)) == 120
