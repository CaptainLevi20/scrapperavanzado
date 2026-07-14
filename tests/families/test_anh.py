import responses

from core.scrapers.families.anh import ScrapANH, _LIST_URL
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


def test_anh_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["anh"] is ScrapANH
