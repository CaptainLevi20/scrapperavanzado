from bs4 import BeautifulSoup

from core.scrapers.families.samai import ScrapTribunales, SAMAI_CORPS
from core.scrapers.registry import FAMILY_REGISTRY

_ROW_HTML = """
<tr>
  <td>0</td>
  <td>25001233300020260001200</td>
  <td>Juan Pérez</td>
  <td>3</td><td>4</td><td>5</td>
  <td>14/06/2026</td>
  <td>Auto que rechaza recurso de apelación</td>
  <td>8</td>
  <td><a class="btn-success" onclick="CargarVentana('https://samai.example.com/VerProvidencia?id=1')">Ver</a></td>
</tr>
"""


def test_samai_has_28_registered_tribunals():
    assert len(SAMAI_CORPS) == 28
    assert SAMAI_CORPS["1100103"] == "Consejo de Estado"


def test_samai_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["samai"] is ScrapTribunales


def test_parse_row_builds_expected_rawdocmodel():
    row = BeautifulSoup(_ROW_HTML, "html.parser").find("tr")
    scraper = ScrapTribunales(corp_code="2500023", corp_name="Tribunal Administrativo de Cundinamarca")

    doc = scraper._parse_row(row, "2500023", "Tribunal Administrativo de Cundinamarca", "Sección Primera", "2026-06-15")

    assert doc.title == "25001233300020260001200"
    assert doc.tipo == "Auto"
    assert doc.detalle == "Auto que rechaza recurso de apelación"
    assert doc.f_public == "2026-06-15"
    assert doc.f_providencia == "2026-06-14"
    assert doc.link["method"] == "jwt_indirect"
    assert doc.link["url"] == "https://samai.example.com/VerProvidencia?id=1"
    assert doc.link["body"] == {"path": "2500023_25001233300020260001200"}
    assert doc.convert_to == "rtf_word"


def test_parse_row_returns_none_without_jwt_link():
    html = _ROW_HTML.replace('<a class="btn-success"', '<a class="btn-other"')
    row = BeautifulSoup(html, "html.parser").find("tr")
    scraper = ScrapTribunales(corp_code="2500023", corp_name="Tribunal Administrativo de Cundinamarca")
    assert scraper._parse_row(row, "2500023", "Tribunal Administrativo de Cundinamarca", "Sección Primera", "2026-06-15") is None


def test_scrap_section_filters_dates_outside_range(monkeypatch):
    scraper = ScrapTribunales(corp_code="2500023", corp_name="Tribunal Administrativo de Cundinamarca")

    soup3 = BeautifulSoup(
        '<select id="MainContent_LstUEstados">'
        '<option value="15/06/2026 0:00:00">15/06/2026</option>'
        '<option value="15/01/2020 0:00:00">15/01/2020</option>'
        "</select>",
        "html.parser",
    )

    monkeypatch.setattr(scraper, "_step4a_check_all", lambda *a, **k: soup3)
    monkeypatch.setattr(
        scraper,
        "_step4b_consultar",
        lambda *a, **k: f'<table id="MainContent_GvProvidencias"><tr><th>h</th></tr>{_ROW_HTML}</table>',
    )

    from datetime import datetime

    docs = scraper._scrap_section(
        session=None,
        soup3=soup3,
        corp_code="2500023",
        corp_name="Tribunal Administrativo de Cundinamarca",
        sec_code="SEC1",
        sec_name="Sección Primera",
        fini_dt=datetime(2026, 6, 1),
        ffin_dt=datetime(2026, 6, 30),
        stop_event=None,
        on_progress=None,
    )

    # only the 15/06/2026 date is in range; the 2020 one is filtered out before any HTTP call
    assert len(docs) == 1
    assert docs[0].f_public == "2026-06-15"


def test_scrap_swallows_exceptions_and_returns_empty_list(monkeypatch):
    scraper = ScrapTribunales(corp_code="2500023", corp_name="Tribunal Administrativo de Cundinamarca")
    monkeypatch.setattr(scraper, "_scrap_corp", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sitio caído")))

    messages = []
    docs = scraper.scrap(fini="2026-06-01", ffin="2026-06-30", on_progress=messages.append)

    assert docs == []
    assert any("Error en" in m for m in messages)


def test_samai_does_not_check_for_republication():
    # SAMAI's download goes through an indirect JWT hop (no direct file URL), so
    # there's nothing cheap to HEAD — republication checking is out of scope.
    scraper = ScrapTribunales("1100103", "Consejo de Estado")
    assert scraper.checks_for_republication is False
