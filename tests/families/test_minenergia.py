import responses

from core.scrapers.families.minenergia import (
    ScrapMinEnergia,
    _extraer_pdf_de_detalle,
    _filas_de_pagina,
    _normalize_title,
)
from core.scrapers.registry import FAMILY_REGISTRY

_BASE = "https://normativame.minenergia.gov.co"
_LOADER = f"{_BASE}/loader.php"


def test_minenergia_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["minenergia"].__name__ == "ScrapMinEnergia"


def test_normalize_title_builds_canonical_code():
    assert _normalize_title("R", "01529", "2026") == "R_MME_1529_2026"


def test_normalize_title_pads_short_numbers_to_four_digits():
    assert _normalize_title("D", "6", "2026") == "D_MME_0006_2026"


def test_normalize_title_keeps_longer_numbers_unpadded():
    assert _normalize_title("C", "40040", "2026") == "C_MME_40040_2026"


_TABLA_HTML = """
<table id="date_table" class="tablaGen table table-striped table-condensed table-hover">
    <thead>
        <tr><th>Nombre estandar</th><th>Tipo de Norma</th><th>Vigencia</th><th>Resumen</th></tr>
    </thead>
    <tbody>
        <tr>
            <td><a target="_blank" href="https://normativame.minenergia.gov.co/normatividad/7788/norma/">01529</a></td>
            <td> Resolución </td>
            <td> 18/08/2026</td>
            <td> Por la cual se designa la coordinación de un grupo interno de trabajo </td>
        </tr>
        <tr>
            <td><a target="_blank" href="https://normativame.minenergia.gov.co/normatividad/7784/norma/">1187</a></td>
            <td> Decreto </td>
            <td> 12/08/2026</td>
            <td> Por el cual se hace un nombramiento ordinario </td>
        </tr>
        <tr>
            <td><a target="_blank" href="https://normativame.minenergia.gov.co/normatividad/7773/norma/">40040</a></td>
            <td> Circular </td>
            <td> 10/08/2026</td>
            <td> Lineamientos de aplicación </td>
        </tr>
    </tbody>
</table>
"""

_TABLA_VACIA_HTML = """
<table id="date_table" class="tablaGen table table-striped table-condensed table-hover">
    <thead><tr><th>Nombre estandar</th><th>Tipo de Norma</th><th>Vigencia</th><th>Resumen</th></tr></thead>
    <tbody></tbody>
</table>
"""


def test_filas_de_pagina_parses_all_rows():
    filas = _filas_de_pagina(_TABLA_HTML)

    assert len(filas) == 3
    assert filas[0] == {
        "numero": "01529", "tipo": "Resolución", "fecha": "2026-08-18",
        "resumen": "Por la cual se designa la coordinación de un grupo interno de trabajo",
        "detalle_url": "https://normativame.minenergia.gov.co/normatividad/7788/norma/",
    }
    assert filas[1]["tipo"] == "Decreto"
    assert filas[2]["tipo"] == "Circular"


def test_filas_de_pagina_returns_empty_when_table_has_no_rows():
    assert _filas_de_pagina(_TABLA_VACIA_HTML) == []


def test_filas_de_pagina_returns_empty_when_table_missing():
    assert _filas_de_pagina("<div>sin tabla</div>") == []


_DETALLE_HTML = """
<html><body>
<iframe title="Resolucion-01529-18082026.pdf" src="public_html/info/minergia/media/tmp/Resolucion-01529-18082026_99586.pdf" frameborder="0" width="100%" height="700px"></iframe>
<!-- <iframe title="8437" src="https://normativame.minenergia.gov.co/loader.php?lServicio=Tools2&lTipo=viewpdf&id=8437" frameborder="0"> eeee -->
</body></html>
"""

_DETALLE_SIN_PDF_HTML = "<html><body><p>Sin archivo adjunto</p></body></html>"


def test_extraer_pdf_de_detalle_resolves_relative_iframe_src():
    url = _extraer_pdf_de_detalle(_DETALLE_HTML)
    assert url == (
        "https://normativame.minenergia.gov.co/public_html/info/minergia/media/tmp/"
        "Resolucion-01529-18082026_99586.pdf"
    )


def test_extraer_pdf_de_detalle_ignores_iframe_inside_html_comment():
    url = _extraer_pdf_de_detalle(_DETALLE_HTML)
    assert "viewpdf" not in url


def test_extraer_pdf_de_detalle_returns_none_when_no_iframe():
    assert _extraer_pdf_de_detalle(_DETALLE_SIN_PDF_HTML) is None


# --- scrap(): flujo completo con responses ---------------------------------

@responses.activate
def test_scrap_parses_listing_and_fetches_detail_for_each_row():
    responses.add(
        responses.GET, _LOADER,
        body=_TABLA_HTML.replace("18/08/2026", "18/06/2026").replace("12/08/2026", "12/06/2026").replace(
            "10/08/2026", "10/06/2026"
        ),
    )
    responses.add(
        responses.GET, _LOADER, body=_TABLA_VACIA_HTML,
    )
    for norma_id in (7788, 7784, 7773):
        responses.add(
            responses.GET, f"{_BASE}/normatividad/{norma_id}/norma/",
            body=_DETALLE_HTML,
        )

    scraper = ScrapMinEnergia()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert [d.title for d in docs] == ["R_MME_1529_2026", "D_MME_1187_2026", "C_MME_40040_2026"]
    assert all(d.link["url"].endswith(".pdf") for d in docs)


@responses.activate
def test_scrap_filters_out_of_range_dates_before_fetching_detail():
    responses.add(responses.GET, _LOADER, body=_TABLA_HTML)  # todas fechas de agosto 2026
    responses.add(responses.GET, _LOADER, body=_TABLA_VACIA_HTML)

    scraper = ScrapMinEnergia()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-01-31")

    assert docs == []
    # Ninguna fila calificó -> nunca se pidió una página de detalle.
    detail_calls = [c for c in responses.calls if "/norma/" in c.request.url]
    assert detail_calls == []


@responses.activate
def test_scrap_stops_pagination_once_a_page_goes_before_fini():
    # Orden descendente real confirmado: en cuanto la fila más vieja de una
    # página ya es anterior a fini, no se pide ninguna página más para ese año.
    pagina_reciente = _TABLA_HTML  # fechas de agosto 2026
    pagina_vieja = _TABLA_HTML.replace("18/08/2026", "01/01/2026").replace(
        "12/08/2026", "01/01/2026"
    ).replace("10/08/2026", "01/01/2026")

    responses.add(responses.GET, _LOADER, body=pagina_reciente)
    responses.add(responses.GET, _LOADER, body=pagina_vieja)
    for norma_id in (7788, 7784, 7773):
        responses.add(responses.GET, f"{_BASE}/normatividad/{norma_id}/norma/", body=_DETALLE_HTML)

    scraper = ScrapMinEnergia()
    docs = scraper.scrap(fini="2026-06-01", ffin="2026-12-31")

    # Solo se pidieron 2 páginas del listado (la reciente y la vieja que activa
    # el corte), nunca una tercera.
    listing_calls = [c for c in responses.calls if "lFuncion=buscar" in c.request.url]
    assert len(listing_calls) == 2


@responses.activate
def test_scrap_stops_pagination_on_empty_table():
    responses.add(responses.GET, _LOADER, body=_TABLA_VACIA_HTML)

    scraper = ScrapMinEnergia()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert docs == []
    assert len(responses.calls) == 1  # una sola página pedida, sin más años/páginas


@responses.activate
def test_scrap_skips_row_without_pdf_in_detail():
    responses.add(responses.GET, _LOADER, body=_TABLA_HTML)
    responses.add(responses.GET, _LOADER, body=_TABLA_VACIA_HTML)
    for norma_id in (7788, 7784, 7773):
        responses.add(responses.GET, f"{_BASE}/normatividad/{norma_id}/norma/", body=_DETALLE_SIN_PDF_HTML)

    scraper = ScrapMinEnergia()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert docs == []


@responses.activate
def test_scrap_continues_when_a_page_fails():
    responses.add(responses.GET, _LOADER, status=500)

    scraper = ScrapMinEnergia()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert docs == []


@responses.activate
def test_scrap_respects_stop_event():
    import threading

    stop_event = threading.Event()
    stop_event.set()

    scraper = ScrapMinEnergia()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31", stop_event=stop_event)

    assert docs == []
    assert len(responses.calls) == 0
