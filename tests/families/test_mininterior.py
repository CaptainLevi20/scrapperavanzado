import responses

from core.scrapers.families.mininterior import (
    ScrapMininterior,
    _extraer_item,
    _normalize_title,
    _parse_fecha,
    _parse_numero,
)
from core.scrapers.registry import FAMILY_REGISTRY


def test_mininterior_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["mininterior"].__name__ == "ScrapMininterior"


def test_normalize_title_builds_canonical_code():
    assert _normalize_title("D", "1028", "2026") == "D1028026"


def test_normalize_title_pads_short_numbers_to_four_digits():
    assert _normalize_title("R", "7", "2026") == "R_MI_0007_2026"


def test_normalize_title_uses_multi_letter_literal_for_directiva():
    assert _normalize_title("DIR", "12", "2025") == "DIR_MI_0012_2025"


def test_parse_fecha_dia_sin_cero():
    assert _parse_fecha("agosto 5, 2026") == "2026-08-05"


def test_parse_fecha_dia_con_cero():
    assert _parse_fecha("agosto 04, 2026") == "2026-08-04"


def test_parse_fecha_returns_none_for_unrecognized_format():
    assert _parse_fecha("04 de agosto de 2026") is None


def test_parse_fecha_returns_none_for_unknown_month_name():
    assert _parse_fecha("mesinventado 5, 2026") is None


def test_parse_numero_extracts_digits_after_no():
    assert _parse_numero("DECRETO No. 1028 DEL 5 DE AGOSTO DE 2026") == "1028"


def test_parse_numero_is_case_insensitive_and_tolerates_typo_in_rest_of_title():
    # Ejemplo real del sitio: "Resolucin" (sin tilde ni "ó") -- el número igual
    # se reconoce porque el patrón no depende de la palabra del tipo.
    assert _parse_numero("Resolucin No. 1384 del 04 de agosto de 2026") == "1384"


def test_parse_numero_returns_none_when_no_number_pattern_found():
    assert _parse_numero("Documento sin número reconocible") is None


_ITEM_DECRETO_HTML = """
<div class="grid-col dmach-grid-item post_id_309284" data-id="309284" data-posttype="normativas">
  <p class="dmach-acf-value decreto">Decreto</p>
  <h4 itemprop="name" class="entry-title de_title_module dmach-post-title">DECRETO No. 1028 DEL 5 DE AGOSTO DE 2026</h4>
  <p class="dmach-acf-value dmach-acf-video-container"><span class="dmach-acf-label">Descripción<span class="dmach-seperator">: </span></span>Por el cual se adiciona el Título 7 de la Parte 4 del Libro 2 del Decreto 1066 de 2015.</p>
  <p class="dmach-acf-value dmach-acf-video-container"><span class="dmach-acf-label">Fecha de entrada en vigencia<span class="dmach-seperator">: </span></span>agosto 5, 2026</p>
  <a class="dmach-acf-value et_pb_button" href="https://www.mininterior.gov.co/wp-content/uploads/2026/08/decreto-no.-1028-del-5-de-agosto-de-2026.pdf" target="_blank">Documento</a>
</div>
"""


def _parse_item(html):
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "html.parser").select_one("div.dmach-grid-item")


def test_extraer_item_parses_real_markup_shape():
    doc = _extraer_item(_parse_item(_ITEM_DECRETO_HTML), source="Ministerio del Interior")

    assert doc is not None
    assert doc.title == "D1028026"
    assert doc.title_unverified is False
    assert doc.tipo == "Decreto"
    assert doc.f_public == "2026-08-05"
    assert doc.detalle == "Por el cual se adiciona el Título 7 de la Parte 4 del Libro 2 del Decreto 1066 de 2015."
    assert doc.link["url"] == (
        "https://www.mininterior.gov.co/wp-content/uploads/2026/08/decreto-no.-1028-del-5-de-agosto-de-2026.pdf"
    )
    assert doc.save_path == "Ministerio del Interior/2026-08-05/Decreto/D1028026(extension)"


def test_extraer_item_skips_when_tipo_out_of_scope():
    html = _ITEM_DECRETO_HTML.replace(
        '<p class="dmach-acf-value decreto">Decreto</p>',
        '<p class="dmach-acf-value informe">Informe</p>',
    )
    assert _extraer_item(_parse_item(html), source="Ministerio del Interior") is None


def test_extraer_item_marks_title_unverified_when_no_number_in_title():
    html = _ITEM_DECRETO_HTML.replace(
        "DECRETO No. 1028 DEL 5 DE AGOSTO DE 2026", "DECRETO SIN NUMERO RECONOCIBLE"
    )
    doc = _extraer_item(_parse_item(html), source="Ministerio del Interior")

    assert doc is not None
    assert doc.title == "DECRETO SIN NUMERO RECONOCIBLE"
    assert doc.title_unverified is True


def test_extraer_item_skips_when_fecha_missing():
    html = _ITEM_DECRETO_HTML.replace(
        '<p class="dmach-acf-value dmach-acf-video-container"><span class="dmach-acf-label">Fecha de entrada en vigencia<span class="dmach-seperator">: </span></span>agosto 5, 2026</p>',
        "",
    )
    assert _extraer_item(_parse_item(html), source="Ministerio del Interior") is None


def test_extraer_item_skips_when_download_link_missing():
    html = _ITEM_DECRETO_HTML.replace(
        '<a class="dmach-acf-value et_pb_button" href="https://www.mininterior.gov.co/wp-content/uploads/2026/08/decreto-no.-1028-del-5-de-agosto-de-2026.pdf" target="_blank">Documento</a>',
        "",
    )
    assert _extraer_item(_parse_item(html), source="Ministerio del Interior") is None


def test_extraer_item_handles_missing_descripcion():
    html = _ITEM_DECRETO_HTML.replace(
        '<p class="dmach-acf-value dmach-acf-video-container"><span class="dmach-acf-label">Descripción<span class="dmach-seperator">: </span></span>Por el cual se adiciona el Título 7 de la Parte 4 del Libro 2 del Decreto 1066 de 2015.</p>',
        "",
    )
    doc = _extraer_item(_parse_item(html), source="Ministerio del Interior")

    assert doc is not None
    assert doc.detalle is None


_PAGINA1_HTML = """
<div class="grid-posts">
""" + "".join(
    f"""
  <div class="grid-col dmach-grid-item post_id_{n}" data-id="{n}" data-posttype="normativas">
    <p class="dmach-acf-value resolucion">Resolución</p>
    <h4 itemprop="name" class="entry-title de_title_module dmach-post-title">Resolución No. {n} del 10 de agosto de 2026</h4>
    <p class="dmach-acf-value dmach-acf-video-container"><span class="dmach-acf-label">Fecha de entrada en vigencia<span class="dmach-seperator">: </span></span>agosto 10, 2026</p>
    <a class="dmach-acf-value et_pb_button" href="https://www.mininterior.gov.co/wp-content/uploads/2026/08/resolucion-{n}.pdf" target="_blank">Documento</a>
  </div>
"""
    for n in (100, 99)
) + """
</div>
"""

_PAGINA2_HTML = """
<div class="grid-posts">
  <div class="grid-col dmach-grid-item post_id_50" data-id="50" data-posttype="normativas">
    <p class="dmach-acf-value informe">Informe</p>
    <h4 itemprop="name" class="entry-title de_title_module dmach-post-title">Informe de gestión agosto 2026</h4>
    <p class="dmach-acf-value dmach-acf-video-container"><span class="dmach-acf-label">Fecha de entrada en vigencia<span class="dmach-seperator">: </span></span>agosto 3, 2026</p>
    <a class="dmach-acf-value et_pb_button" href="https://www.mininterior.gov.co/wp-content/uploads/2026/08/informe.pdf" target="_blank">Documento</a>
  </div>
  <div class="grid-col dmach-grid-item post_id_49" data-id="49" data-posttype="normativas">
    <p class="dmach-acf-value decreto">Decreto</p>
    <h4 itemprop="name" class="entry-title de_title_module dmach-post-title">DECRETO No. 500 DEL 2 DE AGOSTO DE 2026</h4>
    <p class="dmach-acf-value dmach-acf-video-container"><span class="dmach-acf-label">Fecha de entrada en vigencia<span class="dmach-seperator">: </span></span>agosto 2, 2026</p>
    <a class="dmach-acf-value et_pb_button" href="https://www.mininterior.gov.co/wp-content/uploads/2026/08/decreto-500.pdf" target="_blank">Documento</a>
  </div>
  <div class="grid-col dmach-grid-item post_id_48" data-id="48" data-posttype="normativas">
    <p class="dmach-acf-value decreto">Decreto</p>
    <h4 itemprop="name" class="entry-title de_title_module dmach-post-title">DECRETO No. 400 DEL 1 DE JUNIO DE 2026</h4>
    <p class="dmach-acf-value dmach-acf-video-container"><span class="dmach-acf-label">Fecha de entrada en vigencia<span class="dmach-seperator">: </span></span>junio 1, 2026</p>
    <a class="dmach-acf-value et_pb_button" href="https://www.mininterior.gov.co/wp-content/uploads/2026/06/decreto-400.pdf" target="_blank">Documento</a>
  </div>
</div>
"""

_PAGINA_VACIA_HTML = '<div class="grid-posts"></div>'


@responses.activate
def test_scrap_paginates_and_stops_once_a_doc_is_older_than_fini():
    responses.add(responses.GET, "https://www.mininterior.gov.co/normatividad/", body=_PAGINA1_HTML)
    responses.add(responses.GET, "https://www.mininterior.gov.co/normatividad/page/2/", body=_PAGINA2_HTML)

    scraper = ScrapMininterior()
    docs = scraper.scrap(fini="2026-08-01", ffin="2026-08-31")

    # El decreto de junio (page 2, último item) es anterior a fini: se
    # descarta y detiene la paginación ahí. El "Informe" (fuera de alcance)
    # se descarta sin detener nada.
    assert {d.title for d in docs} == {
        "R_MI_0100_2026", "R_MI_0099_2026", "D0500026",
    }
    # Nunca se pidió una tercera página.
    assert len(responses.calls) == 2


@responses.activate
def test_scrap_stops_when_a_page_has_no_items():
    responses.add(responses.GET, "https://www.mininterior.gov.co/normatividad/", body=_PAGINA1_HTML)
    responses.add(responses.GET, "https://www.mininterior.gov.co/normatividad/page/2/", body=_PAGINA_VACIA_HTML)

    scraper = ScrapMininterior()
    docs = scraper.scrap(fini="2020-01-01", ffin="2026-12-31")

    assert {d.title for d in docs} == {"R_MI_0100_2026", "R_MI_0099_2026"}
    assert len(responses.calls) == 2


@responses.activate
def test_scrap_respects_limit():
    responses.add(responses.GET, "https://www.mininterior.gov.co/normatividad/", body=_PAGINA1_HTML)

    scraper = ScrapMininterior()
    docs = scraper.scrap(fini="2026-08-01", ffin="2026-08-31", limit=1)

    assert len(docs) == 1


@responses.activate
def test_scrap_stops_on_stop_event():
    import threading

    responses.add(responses.GET, "https://www.mininterior.gov.co/normatividad/", body=_PAGINA1_HTML)

    stop_event = threading.Event()
    stop_event.set()
    scraper = ScrapMininterior()
    docs = scraper.scrap(fini="2026-08-01", ffin="2026-08-31", stop_event=stop_event)

    assert docs == []
    assert len(responses.calls) == 0


@responses.activate
def test_scrap_returns_partial_results_on_request_error():
    responses.add(responses.GET, "https://www.mininterior.gov.co/normatividad/", body=_PAGINA1_HTML)
    responses.add(responses.GET, "https://www.mininterior.gov.co/normatividad/page/2/", status=500)

    progreso = []
    scraper = ScrapMininterior()
    docs = scraper.scrap(fini="2026-08-01", ffin="2026-08-31", on_progress=progreso.append)

    assert {d.title for d in docs} == {"R_MI_0100_2026", "R_MI_0099_2026"}
    assert any("Error" in m for m in progreso)


def test_filters_by_publication_date_stays_at_default_false():
    assert ScrapMininterior.filters_by_publication_date is False


def test_checks_for_republication_stays_at_default_true():
    assert ScrapMininterior.checks_for_republication is True
