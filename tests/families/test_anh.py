from urllib.parse import parse_qs, urlparse

import responses

from core.scrapers.families.anh import ScrapANH, _LIST_URL, _MAX_PAGINAS
from core.scrapers.registry import FAMILY_REGISTRY

_PAGE_HTML = """
<table>
<tr><th>Tipo</th><th>Tipo</th><th>Numero</th><th>Fecha</th><th>Descripcion</th><th>Accion</th></tr>
<tr>
  <td>x</td><td>Resolución</td><td>500</td><td>10 de mayo de 2024</td><td>Descripción de prueba</td>
  <td><a href="/files/resolucion-500.pdf">Descargar</a></td>
</tr>
</table>
"""

_PAGE1_HTML_WITH_PAGINATION = """
<table>
<tr><th>Tipo</th><th>Tipo</th><th>Numero</th><th>Fecha</th><th>Descripcion</th><th>Accion</th></tr>
<tr>
  <td>x</td><td>Resolución</td><td>500</td><td>10 de mayo de 2024</td><td>Descripción de prueba</td>
  <td><a href="/files/resolucion-500.pdf">Descargar</a></td>
</tr>
</table>
<ul class="pagination">
  <li><a class="page-link">1</a></li>
  <li><a class="page-link">2</a></li>
</ul>
"""

_PAGE2_HTML_WITH_PAGINATION = """
<table>
<tr><th>Tipo</th><th>Tipo</th><th>Numero</th><th>Fecha</th><th>Descripcion</th><th>Accion</th></tr>
<tr>
  <td>x</td><td>Resolución</td><td>501</td><td>11 de mayo de 2024</td><td>Descripción de prueba 2</td>
  <td><a href="/files/resolucion-501.pdf">Descargar</a></td>
</tr>
</table>
<ul class="pagination">
  <li><a class="page-link">1</a></li>
  <li><a class="page-link">2</a></li>
</ul>
"""


@responses.activate
def test_scrap_parses_table_and_stops_without_pagination():
    responses.add(responses.GET, _LIST_URL, body=_PAGE_HTML, status=200)

    scraper = ScrapANH()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1
    assert docs[0].title == "Resolución 500 de 2024"
    assert docs[0].f_public == "2024-05-10"
    assert docs[0].tipo == "Resolución"
    assert docs[0].link["url"] == "https://www.anh.gov.co/files/resolucion-500.pdf"
    assert len(responses.calls) == 1  # sin bloque de paginación, no debe pedir una página 2


@responses.activate
def test_scrap_follows_pagination_and_stops_at_last_page():
    def _callback(request):
        page = parse_qs(urlparse(request.url).query).get("page", ["1"])[0]
        body = _PAGE2_HTML_WITH_PAGINATION if page == "2" else _PAGE1_HTML_WITH_PAGINATION
        headers = {"Content-Type": "text/html; charset=utf-8"}
        return 200, headers, body.encode("utf-8")

    responses.add_callback(responses.GET, _LIST_URL, callback=_callback)

    scraper = ScrapANH()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 2
    assert docs[0].title == "Resolución 500 de 2024"
    assert docs[0].link["url"] == "https://www.anh.gov.co/files/resolucion-500.pdf"
    assert docs[1].title == "Resolución 501 de 2024"
    assert docs[1].link["url"] == "https://www.anh.gov.co/files/resolucion-501.pdf"
    # pagina (2) >= max(paginas_disponibles) (2) -> debe detenerse tras la página 2
    assert len(responses.calls) == 2


@responses.activate
def test_scrap_reports_when_the_page_cap_is_reached_with_more_results_pending():
    """Regression test: hitting the _MAX_PAGINAS cap while more pages still
    existed used to just silently stop — no signal that any documents were
    left uncollected. Now reported via on_progress so worker/tasks.py can
    surface it as a visible RunError (see _ScrapProgressCollector)."""

    def _callback(request):
        page = parse_qs(urlparse(request.url).query).get("page", ["1"])[0]
        body = f"""
<table>
<tr><th>Tipo</th><th>Tipo</th><th>Numero</th><th>Fecha</th><th>Descripcion</th><th>Accion</th></tr>
<tr>
  <td>x</td><td>Resolución</td><td>{page}</td><td>10 de mayo de 2024</td><td>Descripción</td>
  <td><a href="/files/resolucion-{page}.pdf">Descargar</a></td>
</tr>
</table>
<ul class="pagination">
  <li><a class="page-link">1</a></li>
  <li><a class="page-link">999</a></li>
</ul>
"""
        headers = {"Content-Type": "text/html; charset=utf-8"}
        return 200, headers, body.encode("utf-8")

    responses.add_callback(responses.GET, _LIST_URL, callback=_callback)

    progress_messages = []
    scraper = ScrapANH()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31", on_progress=progress_messages.append)

    assert len(docs) == _MAX_PAGINAS  # se leyeron exactamente las páginas permitidas, ni una más
    assert any("Error" in m and "tope" in m for m in progress_messages)


def test_anh_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["anh"] is ScrapANH
