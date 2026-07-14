import responses

from core.scrapers.families.rama_judicial import (
    JUZGADOS_ENTIDADES,
    SUPERIORES_DEPTS,
    ScrapRamaJudicial,
)
from core.scrapers.registry import FAMILY_REGISTRY

_BASE_DOMAIN = "https://publicacionesprocesales.ramajudicial.gov.co"

_DETAIL_HTML = """
<table id="tabla-docs-1"><tbody>
<tr><td><a href="/descargas/archivo.pdf?uuid=abc-123">Auto_2024.pdf</a></td></tr>
</tbody></table>
"""

_LISTING_HTML = """
<html><body>
<span>Página 1 de 1</span>
<tbody class="table-data">
<tr>
  <div class="titulo-publicacion"><a href="https://publicacionesprocesales.ramajudicial.gov.co/detalle/1">Ver</a></div>
  <p class="publish-date">Fecha: 15/06/2024</p>
  <span class="categoria-ep">Tipo de publicación: Sentencias</span>
  <span class="categoria-ep">Especialidad: Civil</span>
  <span class="categoria-ep">Despacho: Juzgado 1 Civil del Circuito</span>
</tr>
</tbody>
</body></html>
"""


def test_superiores_depts_and_juzgados_entidades_counts():
    # NOTE: the task brief's prose/test claimed 32 entries, but the verbatim
    # dict it also specifies actually contains 33 unique DIVIPOLA-coded
    # judicial districts: the 32 official Colombian departamentos plus
    # Bogotá D.C. (code "11"), which has its own Tribunal Superior distinct
    # from Cundinamarca's (code "25"). All 33 values are unique real
    # tribunals with no duplicate/typo, so this assertion was corrected to
    # match the real data rather than dropping a legitimate source to force
    # the count to 32. See task-8-report.md for details; this affects Task
    # 9's downstream fan-out assumption (39 sources, not 38).
    assert len(SUPERIORES_DEPTS) == 33
    assert SUPERIORES_DEPTS["05"] == "Tribunal Superior de Antioquia"
    assert len(JUZGADOS_ENTIDADES) == 6
    assert JUZGADOS_ENTIDADES["31"] == "Juzgado de Circuito"


@responses.activate
def test_fetch_detail_parses_file_table():
    responses.add(responses.GET, _BASE_DOMAIN + "/detalle/1", body=_DETAIL_HTML, status=200)

    scraper = ScrapRamaJudicial(dept_code="05", dept_name="Tribunal Superior de Antioquia", entidad_id="22")
    files = scraper._fetch_detail({"User-Agent": "test"}, _BASE_DOMAIN + "/detalle/1")

    assert files == [("Auto_2024.pdf", _BASE_DOMAIN + "/descargas/archivo.pdf?uuid=abc-123", "abc-123")]


@responses.activate
def test_scrap_builds_docs_from_listing_and_detail(monkeypatch):
    responses.add(
        responses.GET,
        "https://publicacionesprocesales.ramajudicial.gov.co/web/publicaciones-procesales/inicio",
        body=_LISTING_HTML,
        status=200,
    )

    scraper = ScrapRamaJudicial(dept_code="05", dept_name="Tribunal Superior de Antioquia", entidad_id="22")
    monkeypatch.setattr(scraper, "_get_instance_id", lambda session, headers: "XYZ")
    monkeypatch.setattr(
        scraper,
        "_fetch_detail",
        lambda headers, url: [("Auto_2024.pdf", _BASE_DOMAIN + "/descargas/archivo.pdf?uuid=abc-123", "abc-123")],
    )

    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "Auto_2024"
    assert doc.tipo == "Sentencias"
    assert doc.especialidad == "Civil"
    assert doc.seccion == "Juzgado 1 Civil del Circuito"
    assert doc.f_public == "2024-06-15"
    assert doc.convert_to == "rtf"
    assert doc.link == {
        "url": _BASE_DOMAIN + "/descargas/archivo.pdf?uuid=abc-123",
        "method": "GET",
        "body": {"path": "abc-123"},
    }
    assert doc.save_path == (
        "Tribunal Superior de Antioquia/Civil/Juzgado 1 Civil del Circuito/2024-06-15/Sentencias/Auto_2024(extension)"
    )


@responses.activate
def test_scrap_accepts_already_iso_formatted_dates(monkeypatch):
    # Live validation against the real site found it currently publishes
    # "Fecha de Publicación: 2026-07-14" (already YYYY-MM-DD, no slashes),
    # not "DD/MM/YYYY" as originally assumed. The parser must handle both.
    listing_html = _LISTING_HTML.replace(
        '<p class="publish-date">Fecha: 15/06/2024</p>',
        '<p class="publish-date">Fecha de Publicación: 2026-07-14</p>',
    )
    responses.add(
        responses.GET,
        "https://publicacionesprocesales.ramajudicial.gov.co/web/publicaciones-procesales/inicio",
        body=listing_html,
        status=200,
    )

    scraper = ScrapRamaJudicial(dept_code="05", dept_name="Tribunal Superior de Antioquia", entidad_id="22")
    monkeypatch.setattr(scraper, "_get_instance_id", lambda session, headers: "XYZ")
    monkeypatch.setattr(
        scraper,
        "_fetch_detail",
        lambda headers, url: [("Auto_2024.pdf", _BASE_DOMAIN + "/descargas/archivo.pdf?uuid=abc-123", "abc-123")],
    )

    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert len(docs) == 1
    assert docs[0].f_public == "2026-07-14"


def test_rama_judicial_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["rama_judicial"] is ScrapRamaJudicial
