from core.scrapers.families.supersociedades import (
    _anio,
    _fecha_de_periodo,
    _items_de_lista,
    _mes_a_sigla,
    _pdf_del_articulo,
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


_LISTA_JURIDICO = """
<div class="journal-content-article" data-analytics-asset-title="Boletín Jurídico Agosto 2026">
  <a class="tituloBolConJuriHistorico" id="bolConJuriTitulo" alt="Boletín Jurídico Agosto 2026"
     title="Boletín Jurídico Agosto 2026"
     href="https://www.supersociedades.gov.co:443/boletines-conceptos-juridicos/-/asset_publisher/atwl/content/boletin-juridico-agosto-2026?_x=10183496">t</a>
</div>
<div class="journal-content-article" data-analytics-asset-title="BOLETÍN CONCEPTOS JURÍDICOS JULIO 2026">
  <a class="tituloBolConJuriHistorico" title="BOLETÍN CONCEPTOS JURÍDICOS JULIO 2026"
     href="https://www.supersociedades.gov.co:443/boletines-conceptos-juridicos/-/asset_publisher/atwl/content/boletin-julio-2026?_x=1">t</a>
</div>
<div class="journal-content-article" data-analytics-asset-title="WC-Footer">
  <a class="otra-clase" title="pie" href="/algo">x</a>
</div>
"""

_LISTA_CONTABLE = """
<div class="journal-content-article">
  <a class="tituloBol_ConContHistorico" title="Boletín Informativo Contable 2026 - Semestre I"
     href="https://www.supersociedades.gov.co:443/boletines-de-conceptos-contables/-/asset_publisher/atwl/content/contable-2026-si?_x=2">t</a>
</div>
"""

_ARTICULO_CON_PDF = """
<div class="journal-content-article" data-analytics-asset-title="Boletín Jurídico Agosto 2026">
  <p>Consulte los conceptos ...</p>
  <a class="boton-super" title="Continuar"
     href="/documents/20122/9476810/Boletin_agosto_2026.pdf/63d7754c-633b-2bdd-0ea6-1884bac487d7?t=1787932667029">
     PDF Boletín Jurídico </a>
</div>
<footer>
  <a href="/documents/107391/897146/Decreto-Unico-Reglamentario-Sectorial-1074-de-2015.pdf">decreto</a>
</footer>
"""

_ARTICULO_SIN_PDF = """
<div class="journal-content-article"><p>Texto sin adjunto.</p></div>
<footer><a href="/documents/107391/897146/Decreto-Unico-Reglamentario-Sectorial-1074-de-2015.pdf">d</a></footer>
"""


def test_items_de_lista_juridico_toma_title_y_href_ignora_footer():
    items = _items_de_lista(_LISTA_JURIDICO, "tituloBolConJuriHistorico")
    assert items == [
        ("Boletín Jurídico Agosto 2026",
         "https://www.supersociedades.gov.co:443/boletines-conceptos-juridicos/-/asset_publisher/atwl/content/boletin-juridico-agosto-2026?_x=10183496"),
        ("BOLETÍN CONCEPTOS JURÍDICOS JULIO 2026",
         "https://www.supersociedades.gov.co:443/boletines-conceptos-juridicos/-/asset_publisher/atwl/content/boletin-julio-2026?_x=1"),
    ]


def test_items_de_lista_contable():
    items = _items_de_lista(_LISTA_CONTABLE, "tituloBol_ConContHistorico")
    assert items == [
        ("Boletín Informativo Contable 2026 - Semestre I",
         "https://www.supersociedades.gov.co:443/boletines-de-conceptos-contables/-/asset_publisher/atwl/content/contable-2026-si?_x=2"),
    ]


def test_items_de_lista_vacia_si_cambia_la_clase():
    assert _items_de_lista(_LISTA_JURIDICO, "clase-que-no-existe") == []


def test_pdf_del_articulo_toma_el_boletin_no_el_decreto():
    assert _pdf_del_articulo(_ARTICULO_CON_PDF) == (
        "/documents/20122/9476810/Boletin_agosto_2026.pdf/63d7754c-633b-2bdd-0ea6-1884bac487d7?t=1787932667029"
    )


def test_pdf_del_articulo_none_si_no_hay():
    assert _pdf_del_articulo(_ARTICULO_SIN_PDF) is None
