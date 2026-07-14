import responses

from core.scrapers.families.cndj import ScrapCNDJ, _format_radicado
from core.scrapers.registry import FAMILY_REGISTRY

_BASE = "https://relatoria.cndj.gov.co/"

_INDEX_HTML = """
<html><body>
<input name="__RequestVerificationToken" type="hidden" value="TOK1" />
<select id="ddlMagistrado">
  <option value="">Seleccione</option>
  <option value="Juan Perez">Juan Perez</option>
</select>
</body></html>
"""

_RESULTS_HTML = """
<html><body>
<input name="__RequestVerificationToken" type="hidden" value="TOK2" />
<table id="tablaResultados"><tbody>
<tr><td>0</td><td>Juan Perez</td><td>2</td><td>SENTENCIA DEL 15 DE ENERO DE 2024</td>
    <td>05001250200020210021501</td><td>3</td></tr>
</tbody></table>
</body></html>
"""


@responses.activate
def test_scrap_full_flow_returns_expected_document():
    responses.add(responses.GET, _BASE + "Index", body=_INDEX_HTML, status=200)
    responses.add(responses.POST, _BASE + "Resultados?handler=RecibirBusqueda", json={"success": True}, status=200)
    responses.add(responses.GET, _BASE + "Resultados", body=_RESULTS_HTML, status=200)
    responses.add(
        responses.POST,
        _BASE + "Resultados?handler=RecibirDataResumen",
        json={"archivo": "ALGO_ADJUNTA20240120103000"},
        status=200,
    )

    scraper = ScrapCNDJ()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "05001250200020210021501 - Juan Perez"
    assert doc.magistrado == "Juan Perez"
    assert doc.f_public == "2024-01-20"
    assert doc.f_providencia == "2024-01-15"
    assert doc.convert_to == "rtf"
    assert doc.link["url"] == "https://relatoria.cndj.gov.co/docs_relatoria/ALGO_ADJUNTA20240120103000.pdf"
    assert doc.link["body"] == {"path": "05001250200020210021501_3"}
    assert doc.save_path == (
        "Consejo Nacional de Disciplina Judicial/Juan Perez/2024-01-20/"
        "F05001-25-02-000-2021-00215-01_2024(extension)"
    )


def test_format_radicado_matches_docstring_example():
    assert _format_radicado("05001250200020210021501") == "05001-25-02-000-2021-00215-01"


def test_cndj_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["cndj"] is ScrapCNDJ
