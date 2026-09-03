import responses

from core.scrapers.families.mineducacion import (
    ScrapMineducacion,
    _clasificar_tipo,
    _elegir_adjunto,
    _extraer_numero,
    _limpiar_titulo,
    _normalize_title,
    _parse_fecha,
    _resto_tras_numero,
)
from core.scrapers.registry import FAMILY_REGISTRY


def test_mineducacion_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["mineducacion"].__name__ == "ScrapMineducacion"


def test_filters_by_publication_date_stays_at_default_false():
    assert ScrapMineducacion.filters_by_publication_date is False


def test_doc_id_uses_publication_date_stays_at_default_true():
    # A diferencia de minambiente/minvivienda (donde f_public es un
    # timestamp del sitio que puede re-fecharse por reindexado del CMS),
    # aquí f_public es la fecha real de la norma, parseada del propio
    # título -- intrínseca al documento, nunca cambia para el mismo archivo.
    assert ScrapMineducacion.doc_id_uses_publication_date is True


def test_limpiar_titulo_strips_zero_width_space():
    assert _limpiar_titulo("​Resolución 018741 del 06 de octubre de 2023") == (
        "Resolución 018741 del 06 de octubre de 2023"
    )


def test_limpiar_titulo_strips_surrounding_whitespace():
    assert _limpiar_titulo("  Circular 040 del 28 de julio de 2026  ") == "Circular 040 del 28 de julio de 2026"


def test_clasificar_tipo_resolucion_con_tilde():
    assert _clasificar_tipo("Resolución N° 020664 del 4 de agosto de 2026") == ("Resolución", "R")


def test_clasificar_tipo_resolucion_sin_tilde():
    assert _clasificar_tipo("Resolucion No. 010295 de 16 de abril 2026") == ("Resolución", "R")


def test_clasificar_tipo_is_case_insensitive():
    assert _clasificar_tipo("RESOLUCIÓN No.011223 25 Oct 2019") == ("Resolución", "R")


def test_clasificar_tipo_decreto():
    assert _clasificar_tipo("Decreto NO.0617 del 17 de junio de 2026") == ("Decreto", "D")


def test_clasificar_tipo_ley():
    assert _clasificar_tipo("Ley 2167 del 22 de diciembre de 2021") == ("Ley", "L")


def test_clasificar_tipo_circular():
    assert _clasificar_tipo("Circular N° 033 del 18 de junio de 2026") == ("Circular", "C")


def test_clasificar_tipo_directiva_uses_literal_letra():
    assert _clasificar_tipo("Directiva 005 del 24 de julio de 2026") == ("Directiva", "DIRECTIVA")


def test_clasificar_tipo_acuerdo():
    assert _clasificar_tipo("Acuerdo 01 del 23 de diciembre de 2020") == ("Acuerdo", "A")


def test_clasificar_tipo_excludes_proyecto_de_decreto():
    # "Proyecto de Decreto/Resolución" es un borrador en consulta pública,
    # no una norma vigente -- se excluye a propósito, junto con cualquier
    # otro documento que no encaje en un tipo de norma reconocido (ej.
    # "Guía...", "Manual...", "Reglamento Operativo...").
    assert _clasificar_tipo("Proyecto de Decreto") is None
    assert _clasificar_tipo("Proyecto de Resolución") is None


def test_clasificar_tipo_excludes_unrecognized_documents():
    assert _clasificar_tipo("Guía de orientaciones oferta basada cualificaciones MNC - Agosto de 2021") is None
    assert _clasificar_tipo("Manual de Identidad Visual") is None
    assert _clasificar_tipo("Reglamento Operativo del 18 de enero de 2022") is None


def test_extraer_numero_finds_first_digit_run():
    assert _extraer_numero("Resolución N° 020664 del 4 de agosto de 2026") == "020664"


def test_extraer_numero_skips_no_marker_without_digits():
    assert _extraer_numero("Circular N.037 del 7 de julio 2026") == "037"


def test_extraer_numero_returns_none_when_no_digits():
    assert _extraer_numero("Directiva sin número reconocible") is None


def test_resto_tras_numero_strips_everything_up_to_and_including_the_number():
    assert _resto_tras_numero("020664 del 4 de agosto de 2026", "020664") == " del 4 de agosto de 2026"


def test_resto_tras_numero_returns_full_text_when_number_not_found():
    assert _resto_tras_numero("sin número", "9999") == "sin número"


def test_normalize_title_builds_canonical_code():
    assert _normalize_title("R", "020664", "2026") == "R_ME_20664_2026"


def test_normalize_title_pads_short_numbers_to_four_digits():
    assert _normalize_title("A", "01", "2020") == "A_ME_0001_2020"


def test_normalize_title_uses_directiva_literal_instead_of_a_single_letter():
    assert _normalize_title("DIRECTIVA", "005", "2026") == "DIRECTIVA_ME_0005_2026"


def test_parse_fecha_dia_de_mes_de_anio():
    assert _parse_fecha(" del 4 de agosto de 2026") == "2026-08-04"


def test_parse_fecha_dia_de_mes_sin_conector_antes_del_anio():
    # Real: "Circular N.037 del 7 de julio 2026" -- sin "de" antes del año.
    assert _parse_fecha(" del 7 de julio 2026") == "2026-07-07"


def test_parse_fecha_dia_sin_de_antes_del_mes():
    # Real: "RESOLUCIÓN No. 019316 28 de Julio de  2026" (doble espacio antes
    # del año, "28" pegado directo al mes sin "de" intermedio en el resto).
    assert _parse_fecha(" 28 de Julio de  2026") == "2026-07-28"


def test_parse_fecha_mes_completo_sin_dia():
    assert _parse_fecha(" de agosto de 2026") == "2026-08-01"


def test_parse_fecha_solo_anio():
    assert _parse_fecha(" de 2026") == "2026-01-01"


def test_parse_fecha_numerica_dia_mes_anio():
    # Real: "Circular CONJUNTA 001 del 15-3-2022".
    assert _parse_fecha(" del 15-3-2022") == "2022-03-15"


def test_parse_fecha_mes_abreviado_mayusculas():
    # Real: "Resolución 012410 26 NOV 2019".
    assert _parse_fecha(" 26 NOV 2019") == "2019-11-26"


def test_parse_fecha_mes_abreviado_con_punto():
    assert _parse_fecha(" 04 FEB. 2026") == "2026-02-04"


def test_parse_fecha_returns_none_when_no_date_found():
    assert _parse_fecha(" Ministerial No 37") is None


def test_parse_fecha_falls_back_to_month_start_on_calendar_impossible_date():
    assert _parse_fecha(" del 31 de abril de 2024") == "2024-04-01"


def test_parse_fecha_is_case_insensitive():
    assert _parse_fecha(" DEL 27 DE MAYO DEL 2016") == "2016-05-27"


def _figura(href: str, texto: str) -> str:
    return (
        f'<div class="figure bajardoc cid-956"><a href="{href}" title="Ir a {texto}">'
        f'<img src="x.png"></a><a href="{href}" title="Ir a {texto}">{texto}</a></div>'
    )


def test_elegir_adjunto_prefers_pdf_over_earlier_non_pdf():
    from bs4 import BeautifulSoup

    # Real ejemplo: un .docx (formulario anexo) listado ANTES que el PDF de
    # la circular misma -- tomar el primero a secas elegiría el anexo.
    html = (
        _figura("anexo.docx", "Formato Préstamo Bicicletas")
        + _figura("circular.pdf", "Circular No. 21 de marzo 4")
    )
    soup = BeautifulSoup(html, "html.parser")
    figuras = soup.select("div.figure.bajardoc")

    enlace = _elegir_adjunto(figuras)
    assert enlace["href"] == "circular.pdf"


def test_elegir_adjunto_takes_first_pdf_among_several():
    from bs4 import BeautifulSoup

    html = (
        _figura("norma.pdf", "Resolución N° 020664 del 4 de agosto de 2026")
        + _figura("anexo1.pdf", "Documento Técnico de Soporte")
        + _figura("anexo2.pdf", "Marco Jurídico e Institucional")
    )
    soup = BeautifulSoup(html, "html.parser")
    figuras = soup.select("div.figure.bajardoc")

    enlace = _elegir_adjunto(figuras)
    assert enlace["href"] == "norma.pdf"


def test_elegir_adjunto_falls_back_to_first_when_no_pdf_at_all():
    from bs4 import BeautifulSoup

    html = _figura("solo.docx", "Único adjunto, sin PDF")
    soup = BeautifulSoup(html, "html.parser")
    figuras = soup.select("div.figure.bajardoc")

    enlace = _elegir_adjunto(figuras)
    assert enlace["href"] == "solo.docx"


def test_elegir_adjunto_returns_none_when_no_figures():
    assert _elegir_adjunto([]) is None


def _recuadro(titulo: str, figuras_html: str, abstract: str = "Descripción de prueba.") -> str:
    return f"""
    <div class="recuadro my-5">
      <h3 class="h4 titulo aid-1">{titulo}</h3>
      <p class="fecha">Actualizado: 05 de agosto de 2026</p>
      <p class="abstract">{abstract}</p>
      {figuras_html}
    </div>
    """


_PAGINA_ANIO_HTML_TPL = """
<html><head><base href="https://www.mineducacion.gov.co/1780/w3-multipropertyvalues-x-x.html"></head>
<body>
{recuadros}
</body></html>
"""


def _pagina(recuadros: str) -> str:
    return _PAGINA_ANIO_HTML_TPL.format(recuadros=recuadros)


def test_scrap_parses_a_clean_resolucion_row():
    recuadro = _recuadro(
        "Resolución N° 020664 del 4 de agosto de 2026",
        _figura("articles-430163_pdf.pdf", "Resolución N° 020664 del 4 de agosto de 2026"),
        abstract="Por medio de la cual se adoptan los lineamientos.",
    )
    html = _pagina(recuadro)

    scraper = ScrapMineducacion()
    docs = scraper._extraer_anio(html, "https://www.mineducacion.gov.co/fallback/", "2026-01-01", "2026-12-31")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "R_ME_20664_2026"
    assert doc.tipo == "Resolución"
    assert doc.f_public == "2026-08-04"
    assert doc.title_unverified is False
    assert doc.detalle == "Por medio de la cual se adoptan los lineamientos."
    assert doc.link["url"] == "https://www.mineducacion.gov.co/1780/articles-430163_pdf.pdf"
    assert doc.save_path == "Ministerio de Educación Nacional/2026-08-04/Resolución/R_ME_20664_2026(extension)"


def test_scrap_resolves_relative_links_against_the_base_tag_not_the_request_url():
    # El <base href> de la plantilla Newtenberg apunta a una URL distinta de
    # la URL amigable pedida -- si se resolviera contra la URL pedida en vez
    # del <base>, el enlace de descarga quedaría mal formado.
    recuadro = _recuadro(
        "Decreto NO.0617 del 17 de junio de 2026",
        _figura("articles-429281_recurso_1.pdf", "Decreto NO.0617 del 17 de junio de 2026"),
    )
    html = _pagina(recuadro)

    scraper = ScrapMineducacion()
    docs = scraper._extraer_anio(
        html,
        "https://www.mineducacion.gov.co/portal/Normatividad/Ultimas-publicaciones;anos-normatividad/2026/",
        "2026-01-01",
        "2026-12-31",
    )

    assert docs[0].link["url"] == "https://www.mineducacion.gov.co/1780/articles-429281_recurso_1.pdf"


def test_scrap_excludes_proyecto_rows():
    recuadro = f"""
    <div class="recuadro my-5">
      <h3 class="h4 titulo aid-1">Proyecto de Decreto</h3>
      <p class="abstract">Borrador en consulta pública.</p>
    </div>
    """
    html = _pagina(recuadro)

    scraper = ScrapMineducacion()
    docs = scraper._extraer_anio(html, "https://www.mineducacion.gov.co/fallback/", "2026-01-01", "2026-12-31")

    assert docs == []


def test_scrap_skips_row_with_recognized_type_but_no_parseable_date():
    recuadro = _recuadro(
        "Directiva Ministerial No 37",
        _figura("articles-360750.pdf", "Directiva Ministerial No 37"),
    )
    html = _pagina(recuadro)

    progreso = []
    scraper = ScrapMineducacion()
    docs = scraper._extraer_anio(
        html, "https://www.mineducacion.gov.co/fallback/", "2017-01-01", "2017-12-31", on_progress=progreso.append
    )

    assert docs == []
    assert any("fecha" in m for m in progreso)


def test_scrap_skips_row_without_any_attachment():
    recuadro = """
    <div class="recuadro my-5">
      <h3 class="h4 titulo aid-1">Resolución 020664 del 4 de agosto de 2026</h3>
      <p class="abstract">Sin adjunto.</p>
    </div>
    """
    html = _pagina(recuadro)

    scraper = ScrapMineducacion()
    docs = scraper._extraer_anio(html, "https://www.mineducacion.gov.co/fallback/", "2026-01-01", "2026-12-31")

    assert docs == []


def test_scrap_filters_out_documents_outside_requested_range():
    recuadro = _recuadro(
        "Resolución 020664 del 4 de agosto de 2020",
        _figura("articles-1.pdf", "Resolución 020664 del 4 de agosto de 2020"),
    )
    html = _pagina(recuadro)

    scraper = ScrapMineducacion()
    docs = scraper._extraer_anio(html, "https://www.mineducacion.gov.co/fallback/", "2026-01-01", "2026-12-31")

    assert docs == []


@responses.activate
def test_scrap_fetches_one_page_per_year_in_range():
    html_2025 = _pagina(
        _recuadro(
            "Circular 001 de 15 de enero de 2025",
            _figura("articles-1.pdf", "Circular 001 de 15 de enero de 2025"),
        )
    )
    html_2026 = _pagina(
        _recuadro(
            "Resolución 020664 del 4 de agosto de 2026",
            _figura("articles-2.pdf", "Resolución 020664 del 4 de agosto de 2026"),
        )
    )
    responses.add(
        responses.GET,
        "https://www.mineducacion.gov.co/portal/Normatividad/Ultimas-publicaciones;anos-normatividad/2025/",
        body=html_2025,
    )
    responses.add(
        responses.GET,
        "https://www.mineducacion.gov.co/portal/Normatividad/Ultimas-publicaciones;anos-normatividad/2026/",
        body=html_2026,
    )

    scraper = ScrapMineducacion()
    docs = scraper.scrap(fini="2025-01-01", ffin="2026-12-31")

    assert {d.title for d in docs} == {"C_ME_0001_2025", "R_ME_20664_2026"}


@responses.activate
def test_scrap_continues_past_a_failing_year(monkeypatch):
    import core.scrapers.families.mineducacion as mineducacion

    monkeypatch.setattr(mineducacion.time, "sleep", lambda *_a, **_k: None)

    html_2026 = _pagina(
        _recuadro(
            "Resolución 020664 del 4 de agosto de 2026",
            _figura("articles-2.pdf", "Resolución 020664 del 4 de agosto de 2026"),
        )
    )
    # Registrado una sola vez: la petición fallida se reintenta (ver
    # _get_con_reintentos) y `responses` sigue devolviendo este mismo 500 en
    # cada reintento -- este año agota los 3 intentos y se descarta.
    responses.add(
        responses.GET,
        "https://www.mineducacion.gov.co/portal/Normatividad/Ultimas-publicaciones;anos-normatividad/2025/",
        status=500,
    )
    responses.add(
        responses.GET,
        "https://www.mineducacion.gov.co/portal/Normatividad/Ultimas-publicaciones;anos-normatividad/2026/",
        body=html_2026,
    )

    progreso = []
    scraper = ScrapMineducacion()
    docs = scraper.scrap(fini="2025-01-01", ffin="2026-12-31", on_progress=progreso.append)

    assert {d.title for d in docs} == {"R_ME_20664_2026"}
    assert any("Error" in m and "2025" in m for m in progreso)


@responses.activate
def test_scrap_recovers_from_a_transient_404_on_retry(monkeypatch):
    # Regresión del caso real de producción (2026-08-25): el listado de 2026
    # devolvió 404 una sola vez y luego respondió con normalidad -- debe
    # reintentarse en vez de descartar el año entero por un fallo pasajero.
    import core.scrapers.families.mineducacion as mineducacion

    monkeypatch.setattr(mineducacion.time, "sleep", lambda *_a, **_k: None)

    html_2026 = _pagina(
        _recuadro(
            "Resolución 020664 del 4 de agosto de 2026",
            _figura("articles-2.pdf", "Resolución 020664 del 4 de agosto de 2026"),
        )
    )
    responses.add(
        responses.GET,
        "https://www.mineducacion.gov.co/portal/Normatividad/Ultimas-publicaciones;anos-normatividad/2026/",
        status=404,
    )
    responses.add(
        responses.GET,
        "https://www.mineducacion.gov.co/portal/Normatividad/Ultimas-publicaciones;anos-normatividad/2026/",
        body=html_2026,
    )

    progreso = []
    scraper = ScrapMineducacion()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31", on_progress=progreso.append)

    assert {d.title for d in docs} == {"R_ME_20664_2026"}
    assert not any("Error" in m for m in progreso)


@responses.activate
def test_scrap_respects_limit():
    html_2026 = _pagina(
        _recuadro(
            "Resolución 1 del 1 de enero de 2026",
            _figura("articles-1.pdf", "Resolución 1 del 1 de enero de 2026"),
        )
        + _recuadro(
            "Resolución 2 del 2 de enero de 2026",
            _figura("articles-2.pdf", "Resolución 2 del 2 de enero de 2026"),
        )
    )
    responses.add(
        responses.GET,
        "https://www.mineducacion.gov.co/portal/Normatividad/Ultimas-publicaciones;anos-normatividad/2026/",
        body=html_2026,
    )

    scraper = ScrapMineducacion()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31", limit=1)

    assert len(docs) == 1


@responses.activate
def test_scrap_respects_stop_event_between_years():
    import threading

    stop_event = threading.Event()
    stop_event.set()

    scraper = ScrapMineducacion()
    docs = scraper.scrap(fini="2020-01-01", ffin="2026-12-31", stop_event=stop_event)

    assert docs == []
    assert len(responses.calls) == 0
