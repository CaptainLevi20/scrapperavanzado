from bs4 import BeautifulSoup

from core.scrapers.families.samai import (
    ScrapTribunales,
    SAMAI_CORPS,
    _especialidad_legible,
    _normalizar_clase,
    _normalizar_titulo,
)
from core.scrapers.registry import FAMILY_REGISTRY
from core.utils import compute_doc_id

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
    assert doc.especialidad == "5"  # columna "Clase" cruda (ver _ROW_HTML)
    assert doc.f_public == "2026-06-15"
    assert doc.f_providencia == "2026-06-14"
    assert doc.link["method"] == "jwt_indirect"
    assert doc.link["url"] == "https://samai.example.com/VerProvidencia?id=1"
    # Identity includes f_providencia (2026-06-14), not just the radicado —
    # the radicado alone identifies the case, not this specific actuación.
    assert doc.link["body"] == {"path": "2500023_25001233300020260001200_2026-06-14"}


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


def test_samai_checks_for_republication_like_rama_judicial():
    # SAMAI relists the same "estado" row under a new date when the
    # notification wasn't claimed — same document, same file, just published
    # again. This must be treated as a possible republication (version
    # history, previewable), not silently ignored.
    scraper = ScrapTribunales("1100103", "Consejo de Estado")
    assert scraper.checks_for_republication is True


def test_samai_doc_id_is_stable_across_relisting_dates_for_the_same_actuacion():
    # Same actuación (same f_providencia, the real decision date) relisted
    # under a different "estado" date must produce the SAME doc_id — that's a
    # true republication (notification wasn't claimed), not a new document.
    # This test only varies the listing date (estado_fecha_str); the row's
    # own f_providencia (2026-06-14, from _ROW_HTML) doesn't change.
    scraper = ScrapTribunales("1100103", "Consejo de Estado")
    row = BeautifulSoup(_ROW_HTML, "html.parser").find("tr")

    doc_first_listing = scraper._parse_row(row, "1100103", "Consejo de Estado", "Sección Primera", "2026-07-15")
    doc_relisting = scraper._parse_row(row, "1100103", "Consejo de Estado", "Sección Primera", "2026-07-28")

    doc_id_1 = compute_doc_id(doc_first_listing, include_publication_date=scraper.doc_id_uses_publication_date)
    doc_id_2 = compute_doc_id(doc_relisting, include_publication_date=scraper.doc_id_uses_publication_date)
    assert doc_id_1 == doc_id_2


def test_samai_doc_id_differs_for_distinct_actuaciones_sharing_a_radicado():
    # A radicado identifies the whole *case*, not one document — the same
    # case accumulates many distinct actuaciones over time (real cases found:
    # "Auto que rechaza demanda" on 2026-07-27 vs "Auto que inadmite demanda"
    # on 2026-07-14, same radicado). These must NOT collapse into one
    # document just because they share a radicado; f_providencia (row 6,
    # "Fecha Providencia") is what actually distinguishes them.
    scraper = ScrapTribunales("1100103", "Consejo de Estado")
    row_html_otra_actuacion = _ROW_HTML.replace("14/06/2026", "20/06/2026")
    row_1 = BeautifulSoup(_ROW_HTML, "html.parser").find("tr")
    row_2 = BeautifulSoup(row_html_otra_actuacion, "html.parser").find("tr")

    doc_1 = scraper._parse_row(row_1, "1100103", "Consejo de Estado", "Sección Primera", "2026-07-15")
    doc_2 = scraper._parse_row(row_2, "1100103", "Consejo de Estado", "Sección Primera", "2026-07-15")

    assert doc_1.f_providencia != doc_2.f_providencia
    doc_id_1 = compute_doc_id(doc_1, include_publication_date=scraper.doc_id_uses_publication_date)
    doc_id_2 = compute_doc_id(doc_2, include_publication_date=scraper.doc_id_uses_publication_date)
    assert doc_id_1 != doc_id_2


# --- título: {radicado}({acrónimo de la clase de proceso}) --------------------
#
# Catálogo y reglas de normalización dictados por el usuario a partir de datos
# reales de Consejo de Estado (ver core/scrapers/families/samai.py).


def test_normalizar_titulo_appends_acronym_for_known_clase():
    assert _normalizar_titulo("11001-03-28-000-2026-00329-00", "ACCIONES DE CUMPLIMIENTO") == (
        "11001-03-28-000-2026-00329-00(ACU)"
    )


def test_normalizar_titulo_strips_ley_prefix_before_matching():
    # "LEY 1437 NULIDAD" y "Nulidad" son la misma clase — deben caer en el mismo
    # acrónimo aunque una traiga el código de ley y la otra no.
    assert _normalizar_titulo("11001-03-24-000-2015-00065-00", "LEY 1437 NULIDAD") == (
        "11001-03-24-000-2015-00065-00(N)"
    )
    assert _normalizar_titulo("11001-03-24-000-2015-00065-00", "Nulidad") == (
        "11001-03-24-000-2015-00065-00(N)"
    )


def test_normalizar_titulo_strips_accion_de_prefix_before_matching():
    # "ACCION DE NULIDAD" debe caer en el mismo acrónimo que "Nulidad", no
    # quedarse como una clase aparte solo por el prefijo "Acción de".
    assert _normalizar_clase("ACCION DE NULIDAD") == _normalizar_clase("Nulidad")
    assert _normalizar_titulo("05001-23-33-000-2026-00810-01", "ACCION DE NULIDAD") == (
        "05001-23-33-000-2026-00810-01(N)"
    )


def test_normalizar_titulo_strips_articulo_decision_reference():
    assert _normalizar_titulo("11001-03-24-000-2020-00002-00", "NULIDAD RELATIVA ARTÍCULO 172 DECISION 486") == (
        "11001-03-24-000-2020-00002-00(NR)"
    )
    assert _normalizar_titulo("11001-03-24-000-2020-00002-00", "NULIDAD ABSOLUTA ARTÍCULO 172 DECISION 486") == (
        "11001-03-24-000-2020-00002-00(NA)"
    )


def test_normalizar_titulo_is_accent_and_case_insensitive():
    assert _normalizar_titulo("r1", "reparación directa") == "r1(RD)"
    assert _normalizar_titulo("r1", "REPARACION DIRECTA") == "r1(RD)"


def test_normalizar_titulo_merges_clases_the_user_confirmed_are_the_same():
    # Confirmado con el usuario: aunque el texto es distinto, son la misma clase.
    assert _normalizar_titulo("r1", "CONFLICTOS DE COMPETENCIA JUDICIAL") == "r1(CCO)"
    assert _normalizar_titulo("r1", "Protección de los derechos e intereses colectivos") == "r1(PDIC)"
    # "Acción de grupo" y "reparación de perjuicios causados a un grupo" son
    # clases distintas (confirmado con el usuario) — no deben compartir sigla.
    assert _normalizar_titulo("r1", "Acción de grupo") == "r1(AG)"
    assert _normalizar_titulo("r1", "LEY 1437 REPARACION DE PERJUICIOS CAUSADOS A UN GRUPO") == "r1(RPAG)"


def test_normalizar_titulo_falls_back_to_bare_radicado_for_unknown_clase():
    # Clase que no está en el catálogo (todavía no vista en los datos reales) —
    # se deja el radicado solo, sin acrónimo, hasta que se defina su sigla.
    assert _normalizar_titulo("11001-03-24-000-2026-99999-00", "Una clase nunca vista") == (
        "11001-03-24-000-2026-99999-00"
    )


def test_normalizar_titulo_and_especialidad_are_case_law_code_insensitive():
    # "LEY 1437 NULIDAD Y RESTABLECIMIENTO DEL DERECHO" y "Nulidad y
    # restablecimiento del derecho" son la misma clase, pero el sitio no
    # siempre lo escribe igual — la columna Especialidad/Proceso debe mostrar
    # siempre la misma forma limpia, sin importar cuál trajo el sitio.
    assert _especialidad_legible("LEY 1437 NULIDAD Y RESTABLECIMIENTO DEL DERECHO") == (
        "Nulidad y restablecimiento del derecho"
    )
    assert _especialidad_legible("Nulidad y restablecimiento del derecho") == (
        "Nulidad y restablecimiento del derecho"
    )


def test_especialidad_legible_falls_back_to_raw_text_for_unknown_clase():
    # No hay forma de "limpiar" una clase que no está en el catálogo — se deja
    # el texto tal cual llegó del sitio.
    assert _especialidad_legible("Una clase nunca vista") == "Una clase nunca vista"


def test_parse_row_stores_readable_clase_de_proceso_in_especialidad():
    row_html = (
        "<tr><td>0</td><td>25001233300020260001200</td><td>Juan Pérez</td>"
        "<td>3</td><td>4</td><td>LEY 1437 NULIDAD Y RESTABLECIMIENTO DEL DERECHO</td>"
        "<td>14/06/2026</td><td>Auto que rechaza recurso de apelación</td><td>8</td>"
        '<td><a class="btn-success" onclick="CargarVentana(\'https://samai.example.com/VerProvidencia?id=1\')">Ver</a></td></tr>'
    )
    row = BeautifulSoup(row_html, "html.parser").find("tr")
    scraper = ScrapTribunales(corp_code="1100103", corp_name="Consejo de Estado")

    doc = scraper._parse_row(row, "1100103", "Consejo de Estado", "Sección Primera", "2026-06-15")

    assert doc.especialidad == "Nulidad y restablecimiento del derecho"
    assert doc.title == "25001233300020260001200(NRD)"


def test_parse_row_uses_clase_column_to_build_the_polished_title():
    row_html = (
        "<tr><td>0</td><td>25001233300020260001200</td><td>Juan Pérez</td>"
        "<td>3</td><td>4</td><td>ACCIONES DE CUMPLIMIENTO</td>"
        "<td>14/06/2026</td><td>Auto que rechaza recurso de apelación</td><td>8</td>"
        '<td><a class="btn-success" onclick="CargarVentana(\'https://samai.example.com/VerProvidencia?id=1\')">Ver</a></td></tr>'
    )
    row = BeautifulSoup(row_html, "html.parser").find("tr")
    scraper = ScrapTribunales(corp_code="1100103", corp_name="Consejo de Estado")

    doc = scraper._parse_row(row, "1100103", "Consejo de Estado", "Sección Primera", "2026-06-15")

    assert doc.title == "25001233300020260001200(ACU)"
