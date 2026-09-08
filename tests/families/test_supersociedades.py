from core.scrapers.families.supersociedades import (
    _TIPO_CONTABLE,
    _TIPO_JURIDICO,
    _anio,
    _fecha_de_periodo,
    _items_de_lista,
    _mes_a_sigla,
    _nombre_archivo_pdf,
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


def test_anio_pegado_al_mes_o_a_la_extension():
    # títulos y nombres de archivo reales del sitio: el año viene pegado al mes
    assert _anio("Boletín Jurídico Septiembre2024") == 2024
    assert _anio("BoletinJuridico-Octubre2021.pdf") == 2021
    assert _anio("BOLETIN-CONCEPTOS-JURIDICOS-OCTUBRE2020.pdf") == 2020
    # pero un año embebido en una cadena más larga de dígitos NO cuenta
    assert _anio("BOLETIN-CONCEPTOS-JURIDICOS-JULIO-13082020.pdf") is None
    assert _anio("BOLETIN-CONCEPTOS -JURIDICOS-ABRIL-200520.pdf") is None


def test_periodo_juridico_con_anio_pegado():
    assert _periodo_juridico("Boletín Jurídico Septiembre2024") == ("SEP", 2024)


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


def test_constantes_de_tipo_son_las_que_usa_fecha_de_periodo():
    assert _TIPO_JURIDICO == "Boletín Jurídico"
    assert _TIPO_CONTABLE == "Boletín Contable"
    assert _fecha_de_periodo(_TIPO_JURIDICO, ("AGO", 2026)) == "2026-08-01"
    assert _fecha_de_periodo(_TIPO_CONTABLE, ("SII", 2025)) == "2025-12-31"


def test_titulo_verificado_y_fallback():
    assert _titulo("Boletín Jurídico", ("AGO", 2026), "irrelevante") == ("BOL_SS_AGO_2026", False)
    assert _titulo("Boletín Contable", ("SI", 2026), "irrelevante") == ("BOL_SS_SI_2026", False)
    t, unv = _titulo("Boletín Contable", None, "Boletín Informativo Contable 2017")
    assert unv is True and t == "Boletín Informativo Contable 2017"
    assert _titulo("Boletín Jurídico", None, "   ") == ("documento", True)


def test_titulo_fallback_nunca_devuelve_cadena_vacia():
    # ".strip(' .')" sobre un título que sólo tiene puntos lo vaciaba
    assert _titulo("Boletín Jurídico", None, "...") == ("documento", True)
    assert _titulo("Boletín Jurídico", None, " . . ") == ("documento", True)


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


# --- hrefs reales del sitio (verificados en vivo 2026-09-08) ---------------

_HREF_ENERO_2026 = (
    "/documents/20122/9476810/Bolet%C3%ADn+enero+2026+2.pdf"
    "/3f1c8a10-0000-1111-2222-333344445555?t=1770000000000"
)
_HREF_ABSOLUTO = (
    "https://www.supersociedades.gov.co:443/documents/20122/460462/"
    "BOLET%C3%8DN-JUR%C3%8DDICO-JUNIO.pdf/aaaa-bbbb-cccc?t=1720000000000"
)
_HREF_BANNER = (
    "/documents/20122/9476810/Banner-Boletin-juridico-septiembre.jpg.pdf"
    "/9999-8888-7777?t=1"
)
_HREF_DECRETO = (
    "/documents/107391/897146/Decreto-Unico-Reglamentario-Sectorial-1074-de-2015.pdf"
)


def _articulo_con(*hrefs):
    enlaces = "".join(f'<a href="{h}">x</a>' for h in hrefs)
    return f"<html><body><div class='journal-content-article'>{enlaces}</div></body></html>"


def test_pdf_del_articulo_encuentra_href_percent_encoded_y_acentuado():
    # C1: "Bolet%C3%ADn..." no contiene la subcadena "boletin" sin decodificar
    assert _pdf_del_articulo(_articulo_con(_HREF_DECRETO, _HREF_ENERO_2026)) == _HREF_ENERO_2026


def test_pdf_del_articulo_devuelve_el_href_crudo_completo_si_es_absoluto():
    # el href absoluto (con :443 y esquema) debe volver verbatim, no el trozo que casa
    assert _pdf_del_articulo(_articulo_con(_HREF_DECRETO, _HREF_ABSOLUTO)) == _HREF_ABSOLUTO


def test_pdf_del_articulo_ignora_el_banner_que_solo_contiene_boletin():
    # I6: "Banner-Boletin-juridico-septiembre.jpg.pdf" contiene "Boletin" pero no empieza por él
    assert _pdf_del_articulo(_articulo_con(_HREF_DECRETO, _HREF_BANNER)) is None


def test_pdf_del_articulo_ignora_publicaciones_que_no_son_boletines():
    otros = [
        "/documents/20122/1/guia-administradores.pdf/u?t=1",
        "/documents/20122/1/Libro+Pronunciamientos+Administrativos.pdf/u?t=1",
        "/documents/20122/1/revista_supersociedades_V10.pdf/u?t=1",
        "/documents/20122/1/GFIN-M-001_Manual_Cobro_Persuasivo_y_Coactivo.pdf/u?t=1",
    ]
    assert _pdf_del_articulo(_articulo_con(_HREF_DECRETO, *otros)) is None


def test_pdf_del_articulo_acepta_los_conceptos_juridicos_de_2019_como_respaldo():
    # los boletines de 2019 se publicaron como "CONCEPTOS-JURIDICOS-*.pdf",
    # sin la palabra "Boletín" en el nombre del archivo
    href = "/documents/20122/1/CONCEPTOS-JURIDICOS-JULIO-2019.pdf/uuid?t=1"
    assert _pdf_del_articulo(_articulo_con(_HREF_DECRETO, href)) == href
    href2 = "/documents/20122/1/B-CONCEPTOS-JURIDICOS-ENERO-2020.pdf/uuid?t=1"
    assert _pdf_del_articulo(_articulo_con(_HREF_DECRETO, href2)) == href2


def test_pdf_del_articulo_prefiere_el_boletin_sobre_el_respaldo():
    # el respaldo sólo se usa si no hay ningún archivo que empiece por "Bolet"
    conceptos = "/documents/20122/1/CONCEPTOS-JURIDICOS-JULIO-2019.pdf/u1?t=1"
    boletin = "/documents/20122/1/Boletin_julio_2019.pdf/u2?t=1"
    assert _pdf_del_articulo(_articulo_con(_HREF_DECRETO, conceptos, boletin)) == boletin


def test_nombre_archivo_pdf():
    assert _nombre_archivo_pdf(_HREF_ENERO_2026) == "Boletín enero 2026 2.pdf"
    assert _nombre_archivo_pdf(_HREF_ABSOLUTO) == "BOLETÍN-JURÍDICO-JUNIO.pdf"
    assert _nombre_archivo_pdf(
        "/documents/20122/1/BoletinJuridico-Octubre2021.pdf/uuid?t=17"
    ) == "BoletinJuridico-Octubre2021.pdf"
    assert _nombre_archivo_pdf(
        "/documents/20122/1/BOLETIN-CONCEPTOS-JURIDICOS-MARZO-2020.pdf/uuid"
    ) == "BOLETIN-CONCEPTOS-JURIDICOS-MARZO-2020.pdf"
    assert _nombre_archivo_pdf("/documents/20122/1/sin-extension/uuid") == ""
    assert _nombre_archivo_pdf("") == ""


import threading

import responses

from core.scrapers.registry import FAMILY_REGISTRY
from core.scrapers.families.supersociedades import ScrapSupersociedades

_JURI_URL = "https://www.supersociedades.gov.co/boletines-conceptos-juridicos"
_CONT_URL = "https://www.supersociedades.gov.co/boletines-de-conceptos-contables"


def _lista(seccion_slug, link_class, items):
    # items: [(title, article_url)]
    filas = "".join(
        f'<div class="journal-content-article" data-analytics-asset-title="{t}">'
        f'<a class="{link_class}" title="{t}" href="{u}">x</a></div>'
        for t, u in items
    )
    return f"<html><body>{filas}</body></html>"


def _articulo(pdf_href):
    return (
        f'<html><body><div class="journal-content-article">'
        f'<a class="boton-super" href="{pdf_href}">PDF</a></div>'
        f'<footer><a href="/documents/107391/897146/Decreto-Unico-Reglamentario-Sectorial-1074-de-2015.pdf">d</a></footer>'
        f'</body></html>'
    )


def test_supersociedades_registrada():
    import core.scrapers.families  # noqa: F401
    assert FAMILY_REGISTRY["supersociedades"].__name__ == "ScrapSupersociedades"


def test_filters_by_publication_date_activo():
    assert ScrapSupersociedades.filters_by_publication_date is True


@responses.activate
def test_scrap_arma_un_doc_por_boletin_en_ambas_secciones():
    art_juri = _JURI_URL + "/-/asset_publisher/atwl/content/juri-ago-2026"
    art_cont = _CONT_URL + "/-/asset_publisher/atwl/content/cont-2026-si"
    responses.add(responses.GET, _JURI_URL,
                  body=_lista("j", "tituloBolConJuriHistorico", [("Boletín Jurídico Agosto 2026", art_juri)]))
    responses.add(responses.GET, art_juri,
                  body=_articulo("/documents/20122/9476810/Boletin_agosto_2026.pdf/uuid?t=1"))
    responses.add(responses.GET, _CONT_URL,
                  body=_lista("c", "tituloBol_ConContHistorico", [("Boletín Informativo Contable 2026 - Semestre I", art_cont)]))
    responses.add(responses.GET, art_cont,
                  body=_articulo("/documents/20122/460462/Boletin-Contable-2026-Semestre-1.pdf/uuid?t=2"))

    docs = ScrapSupersociedades().scrap(fini="2026-01-01", ffin="2026-12-31")
    porss = {d.title: d for d in docs}
    assert set(porss) == {"BOL_SS_AGO_2026", "BOL_SS_SI_2026"}
    j = porss["BOL_SS_AGO_2026"]
    assert j.tipo == "Boletín Jurídico"
    assert j.source == "Superintendencia de Sociedades"
    assert j.f_public == "2026-08-01" and j.f_providencia == "2026-08-01"
    # I1: la query "?t=<mtime>" NO se guarda (cambia en cada republicación y
    # arrastraría el doc_id), pero el segmento <uuid> de la ruta sí se conserva
    assert j.link == {"url": "https://www.supersociedades.gov.co/documents/20122/9476810/Boletin_agosto_2026.pdf/uuid", "method": "GET"}
    assert "verify" not in j.link
    assert j.detalle == "Boletín Jurídico Agosto 2026"
    assert j.save_path == "Superintendencia de Sociedades/2026-08-01/Boletín Jurídico/BOL_SS_AGO_2026(extension)"
    c = porss["BOL_SS_SI_2026"]
    assert c.f_public == "2026-06-30" and c.tipo == "Boletín Contable"


@responses.activate
def test_scrap_filtra_por_rango_sin_abrir_el_articulo():
    art_in = _JURI_URL + "/-/asset_publisher/atwl/content/ago"
    art_out = _JURI_URL + "/-/asset_publisher/atwl/content/ene"
    responses.add(responses.GET, _JURI_URL, body=_lista("j", "tituloBolConJuriHistorico", [
        ("Boletín Jurídico Agosto 2026", art_in),
        ("Boletín Jurídico Enero 2026", art_out),
    ]))
    responses.add(responses.GET, art_in, body=_articulo("/documents/1/2/Boletin_agosto_2026.pdf/u?t=1"))
    responses.add(responses.GET, _CONT_URL, body=_lista("c", "tituloBol_ConContHistorico", []))

    docs = ScrapSupersociedades().scrap(fini="2026-07-01", ffin="2026-09-30")
    assert [d.title for d in docs] == ["BOL_SS_AGO_2026"]
    # el artículo de enero NUNCA se solicitó
    urls = [c.request.url for c in responses.calls]
    assert art_out not in urls


@responses.activate
def test_scrap_omite_y_avisa_si_no_hay_pdf():
    art = _JURI_URL + "/-/asset_publisher/atwl/content/ago"
    responses.add(responses.GET, _JURI_URL,
                  body=_lista("j", "tituloBolConJuriHistorico", [("Boletín Jurídico Agosto 2026", art)]))
    responses.add(responses.GET, art, body="<html><body><div class='journal-content-article'>sin pdf</div></body></html>")
    responses.add(responses.GET, _CONT_URL, body=_lista("c", "tituloBol_ConContHistorico", []))

    avisos = []
    docs = ScrapSupersociedades().scrap(fini="2026-01-01", ffin="2026-12-31", on_progress=avisos.append)
    assert docs == []
    assert any("sin PDF" in m or "sin pdf" in m.lower() for m in avisos)


@responses.activate
def test_scrap_omite_y_avisa_si_no_hay_periodo_ni_en_titulo_ni_en_el_pdf():
    art = _CONT_URL + "/-/asset_publisher/atwl/content/2017"
    responses.add(responses.GET, _JURI_URL, body=_lista("j", "tituloBolConJuriHistorico", []))
    responses.add(responses.GET, _CONT_URL,
                  body=_lista("c", "tituloBol_ConContHistorico", [("Boletín Informativo Contable", art)]))
    responses.add(responses.GET, art, body=_articulo("/documents/1/2/BoletinInformativoContable.pdf/u?t=1"))

    avisos = []
    docs = ScrapSupersociedades().scrap(fini="2010-01-01", ffin="2026-12-31", on_progress=avisos.append)
    assert docs == []
    # ahora sí se abre el artículo para intentar sacar el período del nombre del PDF
    assert art in [c.request.url for c in responses.calls]
    assert any("ni en el título ni en el PDF" in m for m in avisos)


@responses.activate
def test_scrap_recupera_el_periodo_del_nombre_del_pdf_cuando_el_titulo_no_lo_trae():
    # caso real: "Boletín Conceptos Jurídicos – Octubre" -> BoletinJuridico-Octubre2021.pdf
    a1 = _JURI_URL + "/-/asset_publisher/atwl/content/boletin-octubre-2"
    a2 = _JURI_URL + "/-/asset_publisher/atwl/content/boletin-marzo-1"
    responses.add(responses.GET, _JURI_URL, body=_lista("j", "tituloBolConJuriHistorico", [
        ("Boletín Conceptos Jurídicos – Octubre", a1),
        ("Boletín Conceptos Jurídicos - Marzo", a2),
    ]))
    responses.add(responses.GET, a1,
                  body=_articulo("/documents/20122/1/BoletinJuridico-Octubre2021.pdf/uuid1?t=1"))
    responses.add(responses.GET, a2,
                  body=_articulo("/documents/20122/1/BOLETIN-CONCEPTOS-JURIDICOS-MARZO-2020.pdf/uuid2?t=2"))
    responses.add(responses.GET, _CONT_URL, body=_lista("c", "tituloBol_ConContHistorico", []))

    docs = ScrapSupersociedades().scrap(fini="2015-01-01", ffin="2026-12-31")
    assert sorted(d.title for d in docs) == ["BOL_SS_MAR_2020", "BOL_SS_OCT_2021"]
    oct21 = [d for d in docs if d.title == "BOL_SS_OCT_2021"][0]
    assert oct21.f_public == "2021-10-01" and oct21.title_unverified is False
    assert oct21.detalle == "Boletín Conceptos Jurídicos – Octubre"


@responses.activate
def test_scrap_aplica_el_rango_tambien_al_periodo_sacado_del_pdf():
    a1 = _JURI_URL + "/-/asset_publisher/atwl/content/boletin-octubre-2"
    responses.add(responses.GET, _JURI_URL, body=_lista("j", "tituloBolConJuriHistorico", [
        ("Boletín Conceptos Jurídicos – Octubre", a1),
    ]))
    responses.add(responses.GET, a1,
                  body=_articulo("/documents/20122/1/BoletinJuridico-Octubre2021.pdf/uuid1?t=1"))
    responses.add(responses.GET, _CONT_URL, body=_lista("c", "tituloBol_ConContHistorico", []))

    docs = ScrapSupersociedades().scrap(fini="2024-01-01", ffin="2026-12-31")
    assert docs == []


@responses.activate
def test_scrap_resume_en_una_linea_las_entradas_que_no_son_boletines():
    # guías, libros, "Revista..." — sin PDF de boletín: ni documento ni aviso por ítem
    a1 = _JURI_URL + "/-/asset_publisher/atwl/content/guia-administradores"
    a2 = _JURI_URL + "/-/asset_publisher/atwl/content/insol-world"
    responses.add(responses.GET, _JURI_URL, body=_lista("j", "tituloBolConJuriHistorico", [
        ("Guía práctica para administradores", a1),
        ("Insol World", a2),
    ]))
    responses.add(responses.GET, a1, body=_articulo("/documents/20122/1/guia-administradores.pdf/u?t=1"))
    responses.add(responses.GET, a2, body=_articulo("/documents/20122/1/INSOL_World_1st_Quarter_2013.pdf/u?t=2"))
    responses.add(responses.GET, _CONT_URL, body=_lista("c", "tituloBol_ConContHistorico", []))

    avisos = []
    docs = ScrapSupersociedades().scrap(fini="2010-01-01", ffin="2026-12-31", on_progress=avisos.append)
    assert docs == []
    assert not any("Guía práctica" in m or "Insol" in m for m in avisos)
    assert sum(1 for m in avisos if "2 entradas de Boletín Jurídico sin PDF de boletín, omitidas" in m) == 1


@responses.activate
def test_scrap_dos_boletines_del_mismo_periodo_no_comparten_save_path():
    # caso real 2014: "Boletín Jurídico Marzo-Mayo 2014" y
    # "Boletín grupo de reorganización Marzo 2014" -> ambos BOL_SS_MAR_2014
    a1 = _JURI_URL + "/-/asset_publisher/atwl/content/juri-marzo-mayo-2014"
    a2 = _JURI_URL + "/-/asset_publisher/atwl/content/reorganizacion-marzo-2014"
    responses.add(responses.GET, _JURI_URL, body=_lista("j", "tituloBolConJuriHistorico", [
        ("Boletín Jurídico Marzo-Mayo 2014", a1),
        ("Boletín grupo de reorganización Marzo 2014", a2),
    ]))
    responses.add(responses.GET, a1,
                  body=_articulo("/documents/20122/1/boletin+juridico+marzo-mayo+2014.pdf/uuid1?t=1"))
    responses.add(responses.GET, a2,
                  body=_articulo("/documents/20122/1/Boletin-registro-especialistas-marzo2014.pdf/uuid2?t=2"))
    responses.add(responses.GET, _CONT_URL, body=_lista("c", "tituloBol_ConContHistorico", []))

    docs = ScrapSupersociedades().scrap(fini="2014-01-01", ffin="2014-12-31")
    assert len(docs) == 2
    assert len({d.save_path for d in docs}) == 2
    primero, segundo = docs
    assert primero.title == "BOL_SS_MAR_2014" and primero.title_unverified is False
    assert segundo.title == "Boletín grupo de reorganización Marzo 2014"
    assert segundo.title_unverified is True


@responses.activate
def test_scrap_url_de_articulo_relativa_se_resuelve_contra_el_dominio():
    responses.add(responses.GET, _JURI_URL, body=_lista("j", "tituloBolConJuriHistorico", [
        ("Boletín Jurídico Agosto 2026", "/boletines-conceptos-juridicos/-/x/ago"),
    ]))
    responses.add(responses.GET, "https://www.supersociedades.gov.co/boletines-conceptos-juridicos/-/x/ago",
                  body=_articulo("/documents/1/2/Boletin_agosto_2026.pdf/u?t=1"))
    responses.add(responses.GET, _CONT_URL, body=_lista("c", "tituloBol_ConContHistorico", []))

    docs = ScrapSupersociedades().scrap(fini="2026-01-01", ffin="2026-12-31")
    assert [d.title for d in docs] == ["BOL_SS_AGO_2026"]


@responses.activate
def test_scrap_continua_si_una_seccion_falla():
    art = _CONT_URL + "/-/asset_publisher/atwl/content/cont"
    responses.add(responses.GET, _JURI_URL, status=500)
    responses.add(responses.GET, _CONT_URL,
                  body=_lista("c", "tituloBol_ConContHistorico", [("Boletín Informativo Contable 2026 - Semestre I", art)]))
    responses.add(responses.GET, art, body=_articulo("/documents/1/2/Boletin-Contable-2026-Semestre-1.pdf/u?t=1"))

    avisos = []
    docs = ScrapSupersociedades().scrap(fini="2026-01-01", ffin="2026-12-31", on_progress=avisos.append)
    assert [d.title for d in docs] == ["BOL_SS_SI_2026"]
    assert any("Error" in m and "Jurídico" in m for m in avisos)


@responses.activate
def test_scrap_avisa_si_la_lista_viene_vacia():
    responses.add(responses.GET, _JURI_URL, body="<html><body>sin articulos</body></html>")
    responses.add(responses.GET, _CONT_URL, body="<html><body>sin articulos</body></html>")
    avisos = []
    ScrapSupersociedades().scrap(fini="2026-01-01", ffin="2026-12-31", on_progress=avisos.append)
    assert sum(1 for m in avisos if "no se encontró ningún boletín" in m) == 2


@responses.activate
def test_scrap_respeta_stop_event():
    responses.add(responses.GET, _JURI_URL, body=_lista("j", "tituloBolConJuriHistorico", []))
    responses.add(responses.GET, _CONT_URL, body=_lista("c", "tituloBol_ConContHistorico", []))
    ev = threading.Event()
    ev.set()
    docs = ScrapSupersociedades().scrap(fini="2026-01-01", ffin="2026-12-31", stop_event=ev)
    assert docs == []
    assert len(responses.calls) == 0


@responses.activate
def test_scrap_respeta_limit():
    a1 = _JURI_URL + "/a1"
    a2 = _JURI_URL + "/a2"
    responses.add(responses.GET, _JURI_URL, body=_lista("j", "tituloBolConJuriHistorico", [
        ("Boletín Jurídico Julio 2026", a1),
        ("Boletín Jurídico Agosto 2026", a2),
    ]))
    responses.add(responses.GET, a1, body=_articulo("/documents/1/2/Boletin_julio_2026.pdf/u?t=1"))
    responses.add(responses.GET, a2, body=_articulo("/documents/1/2/Boletin_agosto_2026.pdf/u?t=2"))

    docs = ScrapSupersociedades().scrap(fini="2026-01-01", ffin="2026-12-31", limit=1)
    assert len(docs) == 1
