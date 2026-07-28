import re

import responses

from core.scrapers.families.adres import ScrapADRES, _MAX_PAGINAS_POR_CATEGORIA
from core.scrapers.registry import FAMILY_REGISTRY

_TABLE_HTML = """
<table>
<tr><td>Fecha</td><td>Documento</td><td>Descripción</td></tr>
<tr><td>15/01/2024</td><td><a href="/normativa/resolucion-1.pdf">Resolución 1</a></td><td>Detalle 1</td></tr>
<tr><td>15/01/2020</td><td><a href="/normativa/resolucion-vieja.pdf">Resolución vieja</a></td><td>Detalle 2</td></tr>
</table>
"""


def test_extraer_filas_filters_by_date_and_builds_absolute_urls():
    scraper = ScrapADRES()
    docs, fechas = scraper._extraer_filas(_TABLE_HTML, "Resolución", "2024-01-01", "2024-12-31", set())

    assert len(docs) == 1
    assert docs[0].title == "Resolución 1"
    assert docs[0].f_public == "2024-01-15"
    assert docs[0].link["url"] == "https://www.adres.gov.co/normativa/resolucion-1.pdf"
    assert docs[0].detalle == "Detalle 1"
    assert fechas == ["2024-01-15", "2020-01-15"]  # todas las fechas vistas, sin filtrar


def test_extraer_filas_ignores_tables_without_fecha_header():
    scraper = ScrapADRES()
    html = "<table><tr><td>Otro</td><td>Col</td></tr><tr><td>x</td><td>y</td></tr></table>"
    docs, fechas = scraper._extraer_filas(html, "Resolución", "2024-01-01", "2024-12-31", set())

    assert docs == []
    assert fechas == []


def test_extraer_next_links_finds_pagination_urls():
    scraper = ScrapADRES()
    html = '<script>RefreshPageTo(event, "/normativa/resoluciones?page=2");</script>'
    links = scraper._extraer_next_links(html)

    assert links == ["https://www.adres.gov.co/normativa/resoluciones?page=2"]


def test_adres_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["adres"] is ScrapADRES


@responses.activate
def test_scrap_aggregates_across_categories():
    page1_html = """
    <table>
    <tr><td>Fecha</td><td>Documento</td><td>Descripción</td></tr>
    <tr><td>15/01/2024</td><td><a href="/normativa/resolucion-1.pdf">Resolución 1</a></td><td>Detalle 1</td></tr>
    </table>
    <script>RefreshPageTo(event, "/normativa/resoluciones?page=2");</script>
    """
    page2_html = """
    <table>
    <tr><td>Fecha</td><td>Documento</td><td>Descripción</td></tr>
    <tr><td>10/01/2024</td><td><a href="/normativa/resolucion-2.pdf">Resolución 2</a></td><td>Detalle 2</td></tr>
    </table>
    """
    empty_html = "<p>No hay documentos disponibles.</p>"

    responses.add(
        responses.GET,
        "https://www.adres.gov.co/normativa/resoluciones",
        body=page1_html,
        status=200,
    )
    responses.add(
        responses.GET,
        "https://www.adres.gov.co/normativa/resoluciones?page=2",
        body=page2_html,
        status=200,
    )
    responses.add(
        responses.GET,
        "https://www.adres.gov.co/normativa/circulares",
        body=empty_html,
        status=200,
    )
    responses.add(
        responses.GET,
        "https://www.adres.gov.co/normativa/acuerdos",
        body=empty_html,
        status=200,
    )

    scraper = ScrapADRES()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 2
    titulos = {d.title for d in docs}
    assert titulos == {"Resolución 1", "Resolución 2"}
    assert all(d.tipo == "Resolución" for d in docs)


@responses.activate
def test_scrap_reports_and_continues_past_a_failing_category_page():
    # A failing page (network error / non-2xx) must be logged via on_progress,
    # not swallowed silently, and must not stop the other categories.
    working_html = """
    <table>
    <tr><td>Fecha</td><td>Documento</td><td>Descripción</td></tr>
    <tr><td>15/01/2024</td><td><a href="/normativa/circular-1.pdf">Circular 1</a></td><td>Detalle</td></tr>
    </table>
    """
    empty_html = "<p>No hay documentos disponibles.</p>"

    responses.add(responses.GET, "https://www.adres.gov.co/normativa/resoluciones", status=500)
    responses.add(responses.GET, "https://www.adres.gov.co/normativa/circulares", body=working_html, status=200)
    responses.add(responses.GET, "https://www.adres.gov.co/normativa/acuerdos", body=empty_html, status=200)

    messages = []
    scraper = ScrapADRES()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31", on_progress=messages.append)

    assert len(docs) == 1
    assert docs[0].title == "Circular 1"
    assert any("Error consultando página de Resolución" in m for m in messages)


@responses.activate
def test_scrap_reports_when_the_page_cap_is_reached_with_more_results_pending():
    """Regression test: hitting the _MAX_PAGINAS_POR_CATEGORIA cap while more
    pages were still queued used to just silently stop — no signal that any
    documents were left uncollected. Now reported via on_progress."""
    call_count = {"n": 0}

    def _resoluciones_callback(request):
        call_count["n"] += 1
        n = call_count["n"]
        next_page = n + 1
        body = f"""
        <table>
        <tr><td>Fecha</td><td>Documento</td><td>Descripción</td></tr>
        <tr><td>15/01/2024</td><td><a href="/normativa/resolucion-{n}.pdf">Resolución {n}</a></td><td>Detalle</td></tr>
        </table>
        <script>RefreshPageTo(event, "/normativa/resoluciones?page={next_page}");</script>
        """
        return 200, {}, body

    responses.add_callback(
        responses.GET,
        re.compile(r"https://www\.adres\.gov\.co/normativa/resoluciones.*"),
        callback=_resoluciones_callback,
    )
    empty_html = "<p>No hay documentos disponibles.</p>"
    responses.add(responses.GET, "https://www.adres.gov.co/normativa/circulares", body=empty_html, status=200)
    responses.add(responses.GET, "https://www.adres.gov.co/normativa/acuerdos", body=empty_html, status=200)

    messages = []
    scraper = ScrapADRES()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31", on_progress=messages.append)

    resoluciones = [d for d in docs if d.tipo == "Resolución"]
    assert len(resoluciones) == _MAX_PAGINAS_POR_CATEGORIA  # una fila nueva por cada página permitida
    assert any("Error" in m and "tope" in m and "Resolución" in m for m in messages)
