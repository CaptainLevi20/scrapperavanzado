from core.scrapers.registry import FAMILY_REGISTRY
from core.scrapers.families.mincit import (
    _normalize_title,
    _parse_detalle,
    _parse_fecha,
    _parse_numero,
)


def test_mincit_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["mincit"].__name__ == "ScrapMINCIT"


def test_scrap_returns_empty_list_by_default():
    from core.scrapers.families.mincit import ScrapMINCIT

    scraper = ScrapMINCIT()
    assert scraper.scrap(fini="2024-01-01", ffin="2024-12-31") == []


def test_parse_fecha_converts_ddmmyyyy_to_isoformat():
    assert _parse_fecha("30/12/2025") == "2025-12-30"


def test_parse_fecha_returns_none_when_no_date_found():
    assert _parse_fecha("sin fecha") is None


def test_parse_numero_extracts_leading_number_after_tipo():
    texto = 'Resolución 365 del 30 de diciembre de 2025, "por la cual se adopta..."'
    assert _parse_numero(texto) == "365"


def test_parse_numero_extracts_number_with_leading_zero():
    texto = "Circular 018 del 27 de diciembre de 2024: distribución y administración..."
    assert _parse_numero(texto) == "018"


def test_parse_numero_returns_none_when_no_leading_number():
    assert _parse_numero("Documento sin número al inicio") is None


def test_parse_detalle_extracts_quoted_text_after_comma():
    texto = (
        'Resolución 365 del 30 de diciembre de 2025, '
        '"por la cual se adopta la determinación final".'
    )
    assert _parse_detalle(texto) == "por la cual se adopta la determinación final"


def test_parse_detalle_extracts_text_after_colon_without_quotes():
    texto = (
        "Circular 018 del 27 de diciembre de 2024: distribución y administración "
        "del contingente de exportación de azúcar."
    )
    assert _parse_detalle(texto) == (
        "distribución y administración del contingente de exportación de azúcar"
    )


def test_parse_detalle_returns_none_without_separator():
    assert _parse_detalle("Texto sin separador de descripción") is None


def test_normalize_title_builds_canonical_code():
    assert _normalize_title("R", "365", "2025") == "R_MCIT_0365_2025"


def test_normalize_title_pads_short_numbers_to_four_digits():
    assert _normalize_title("C", "18", "2024") == "C_MCIT_0018_2024"


def test_normalize_title_uses_letter_per_tipo():
    assert _normalize_title("L", "2094", "2021") == "L_MCIT_2094_2021"
    assert _normalize_title("D", "1438", "2025") == "D_MCIT_1438_2025"


from core.scrapers.families.mincit import _anios_del_slug, _mapa_anio_a_slug

_INDICE_HTML = """
<a href="/normatividad/leyes" class="active">Leyes</a>
<a href="/normatividad/leyes/2021">2021</a>
<a href="/normatividad/leyes/1990-1994">1990-1994</a>
<a href="/normatividad/leyes/1979-1989">1979-1989</a>
"""


def test_anios_del_slug_handles_single_year():
    assert _anios_del_slug("2021") == [2021]


def test_anios_del_slug_handles_range():
    assert _anios_del_slug("1990-1994") == [1990, 1991, 1992, 1993, 1994]


def test_anios_del_slug_handles_reversed_range():
    assert _anios_del_slug("1995-1990") == [1990, 1991, 1992, 1993, 1994, 1995]


def test_anios_del_slug_returns_empty_for_non_year_slug():
    assert _anios_del_slug("circulares-conjuntas") == []


def test_mapa_anio_a_slug_maps_each_year_including_ranges():
    mapa = _mapa_anio_a_slug(_INDICE_HTML, "leyes")

    assert mapa[2021] == "2021"
    assert mapa[1990] == "1990-1994"
    assert mapa[1994] == "1990-1994"
    assert mapa[1985] == "1979-1989"


def test_mapa_anio_a_slug_ignores_other_categories():
    html = '<a href="/normatividad/decretos/2021">2021</a>'
    assert _mapa_anio_a_slug(html, "leyes") == {}
