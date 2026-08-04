from pathlib import Path

from bs4 import BeautifulSoup

import core.scrapers.families.samai as samai_module
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

    # Tribunal Administrativo (no Consejo de Estado): título tipo Tribunal
    # Superior, "T_{CÓDIGO}_{radicado}" — nunca el bare radicado o el formato
    # con acrónimo de Consejo de Estado.
    assert doc.title == "T_CUND_25001233300020260001200"
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


_CONSEJO_ESTADO = "1100103"


def test_normalizar_titulo_appends_acronym_for_known_clase():
    assert _normalizar_titulo("11001-03-28-000-2026-00329-00", "ACCIONES DE CUMPLIMIENTO", _CONSEJO_ESTADO) == (
        "11001-03-28-000-2026-00329-00(ACU)"
    )


def test_normalizar_titulo_strips_ley_prefix_before_matching():
    # "LEY 1437 NULIDAD" y "Nulidad" son la misma clase — deben caer en el mismo
    # acrónimo aunque una traiga el código de ley y la otra no.
    assert _normalizar_titulo("11001-03-24-000-2015-00065-00", "LEY 1437 NULIDAD", _CONSEJO_ESTADO) == (
        "11001-03-24-000-2015-00065-00(N)"
    )
    assert _normalizar_titulo("11001-03-24-000-2015-00065-00", "Nulidad", _CONSEJO_ESTADO) == (
        "11001-03-24-000-2015-00065-00(N)"
    )


def test_normalizar_titulo_strips_accion_de_prefix_before_matching():
    # "ACCION DE NULIDAD" debe caer en el mismo acrónimo que "Nulidad", no
    # quedarse como una clase aparte solo por el prefijo "Acción de".
    assert _normalizar_clase("ACCION DE NULIDAD") == _normalizar_clase("Nulidad")
    assert _normalizar_titulo("05001-23-33-000-2026-00810-01", "ACCION DE NULIDAD", _CONSEJO_ESTADO) == (
        "05001-23-33-000-2026-00810-01(N)"
    )


def test_normalizar_titulo_strips_articulo_decision_reference():
    assert _normalizar_titulo(
        "11001-03-24-000-2020-00002-00", "NULIDAD RELATIVA ARTÍCULO 172 DECISION 486", _CONSEJO_ESTADO
    ) == "11001-03-24-000-2020-00002-00(NR)"
    assert _normalizar_titulo(
        "11001-03-24-000-2020-00002-00", "NULIDAD ABSOLUTA ARTÍCULO 172 DECISION 486", _CONSEJO_ESTADO
    ) == "11001-03-24-000-2020-00002-00(NA)"


def test_normalizar_titulo_is_accent_and_case_insensitive():
    assert _normalizar_titulo("r1", "reparación directa", _CONSEJO_ESTADO) == "r1(RD)"
    assert _normalizar_titulo("r1", "REPARACION DIRECTA", _CONSEJO_ESTADO) == "r1(RD)"


def test_normalizar_titulo_merges_clases_the_user_confirmed_are_the_same():
    # Confirmado con el usuario: aunque el texto es distinto, son la misma clase.
    assert _normalizar_titulo("r1", "CONFLICTOS DE COMPETENCIA JUDICIAL", _CONSEJO_ESTADO) == "r1(CCO)"
    assert _normalizar_titulo("r1", "Protección de los derechos e intereses colectivos", _CONSEJO_ESTADO) == "r1(PDIC)"
    # "Acción de grupo" y "reparación de perjuicios causados a un grupo" son
    # clases distintas (confirmado con el usuario) — no deben compartir sigla.
    assert _normalizar_titulo("r1", "Acción de grupo", _CONSEJO_ESTADO) == "r1(AG)"
    assert _normalizar_titulo(
        "r1", "LEY 1437 REPARACION DE PERJUICIOS CAUSADOS A UN GRUPO", _CONSEJO_ESTADO
    ) == "r1(RPAG)"


def test_normalizar_titulo_falls_back_to_bare_radicado_for_unknown_clase():
    # Clase que no está en el catálogo (todavía no vista en los datos reales) —
    # se deja el radicado solo, sin acrónimo, hasta que se defina su sigla.
    assert _normalizar_titulo("11001-03-24-000-2026-99999-00", "Una clase nunca vista", _CONSEJO_ESTADO) == (
        "11001-03-24-000-2026-99999-00"
    )


# --- título de Tribunal Administrativo: T_{CÓDIGO}_{radicado segmentado} ------
#
# A diferencia de Consejo de Estado, un Tribunal Administrativo NUNCA lleva el
# acrónimo de la clase — su título debe imitar el de Tribunales Superiores
# (rama_judicial), no el de Consejo de Estado.


def test_normalizar_titulo_for_tribunal_administrativo_mirrors_tribunal_superior_format():
    titulo = _normalizar_titulo(
        "05001-23-33-000-2018-01895-00", "Nulidad y restablecimiento del derecho", "0500123"
    )
    assert titulo == "T_ANTI_05001_23_33_000_2018_01895_00"


def test_normalizar_titulo_for_tribunal_administrativo_ignores_the_clase_entirely():
    # La clase no debe afectar en nada el título de un Tribunal Administrativo,
    # a diferencia de Consejo de Estado — ni siquiera para agregar un acrónimo.
    sin_acronimo = _normalizar_titulo("13001-23-33-000-2026-00400-00", "Una clase nunca vista", "1300123")
    con_acronimo = _normalizar_titulo("13001-23-33-000-2026-00400-00", "Nulidad", "1300123")
    assert sin_acronimo == con_acronimo == "T_BOLI_13001_23_33_000_2026_00400_00"


def test_normalizar_titulo_for_tribunal_administrativo_never_matches_consejo_de_estado_format():
    # Requisito del usuario: el nombre de un Tribunal Administrativo no debe
    # parecerse al de Consejo de Estado (radicado(ACRÓNIMO)).
    from core.utils import is_samai_case_title

    titulo = _normalizar_titulo("05001-23-33-000-2018-01895-00", "Nulidad", "0500123")
    assert is_samai_case_title(titulo) is False


def test_normalizar_titulo_for_tribunal_administrativo_matches_tribunal_superior_pattern():
    from core.utils import is_radicado_title

    titulo = _normalizar_titulo("05001-23-33-000-2018-01895-00", "Nulidad", "0500123")
    assert is_radicado_title(titulo) is True


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


# --- número extra entre paréntesis (primera página del PDF) -----------------
#
# Algunos documentos de Consejo de Estado traen, junto al radicado en su
# primera página, un número entre paréntesis que no aparece en la tabla de
# resultados de SAMAI (ej. "Radicación  25000-...-01 (30146)"). Cuando
# aparece, se añade al título entre el radicado y la sigla de clase.

from core.scrapers.families.samai import (
    _TITULO_CE_RE,
    _numero_extra_desde_texto,
    _complementar_titulo_con_numero,
)


def test_titulo_ce_re_splits_radicado_and_acronimo():
    match = _TITULO_CE_RE.match("25000-23-37-000-2021-00423-01(NRD)")
    assert match.group(1) == "25000-23-37-000-2021-00423-01"
    assert match.group(2) == "(NRD)"


def test_titulo_ce_re_handles_title_without_acronimo():
    match = _TITULO_CE_RE.match("11001-03-24-000-2026-99999-00")
    assert match.group(1) == "11001-03-24-000-2026-99999-00"
    assert match.group(2) is None


def test_titulo_ce_re_does_not_match_tribunal_administrativo_titles():
    assert _TITULO_CE_RE.match("T_CUND_25001233300020260001200") is None


def test_numero_extra_desde_texto_finds_number_right_after_radicado():
    texto = "Radicación  25000-23-37-000-2021-00423-01 (30146)\nDemandante..."
    assert _numero_extra_desde_texto(texto, "25000-23-37-000-2021-00423-01") == "30146"


def test_numero_extra_desde_texto_returns_none_when_absent():
    texto = "Radicación  25000-23-37-000-2021-00423-01\nDemandante..."
    assert _numero_extra_desde_texto(texto, "25000-23-37-000-2021-00423-01") is None


def test_numero_extra_desde_texto_ignores_unrelated_parenthetical_numbers():
    # El (30146) aparece en el texto pero NO justo después del radicado —
    # no debe confundirse con el dato que buscamos.
    texto = "Ver más en (30146) — Radicación 25000-23-37-000-2021-00423-01 sin número"
    assert _numero_extra_desde_texto(texto, "25000-23-37-000-2021-00423-01") is None


def test_numero_extra_desde_texto_finds_numero_ano_format():
    # Confirmado con datos reales: no siempre es solo dígitos — a veces trae
    # un año pegado con guion (ej. "66001-...-01 (3104-2023)").
    texto = "Radicación:  66001-23-33-000-2017-00141-01 (3104-2023) \nDemandante..."
    assert _numero_extra_desde_texto(texto, "66001-23-33-000-2017-00141-01") == "3104-2023"


def test_numero_extra_desde_texto_finds_digits_with_dot_format():
    # Confirmado con datos reales: algunos documentos usan un punto como
    # separador de miles (ej. "(74.604)").
    texto = "Radicación:  11001-03-15-000-2025-04868-00 (74.604) \nDemandante..."
    assert _numero_extra_desde_texto(texto, "11001-03-15-000-2025-04868-00") == "74.604"


def test_numero_extra_desde_texto_ignores_content_without_any_digit():
    # Confirmado con datos reales: a veces lo que aparece entre paréntesis es
    # "(principal)" — indica "cuaderno principal", no es un número de caso, y
    # no debe agregarse al título.
    texto = "Radicación:  11001-03-28-000-2026-00085-00 (principal) \nDemandante..."
    assert _numero_extra_desde_texto(texto, "11001-03-28-000-2026-00085-00") is None


def test_complementar_titulo_con_numero_inserts_between_radicado_and_acronimo():
    assert _complementar_titulo_con_numero("25000-23-37-000-2021-00423-01(NRD)", "30146") == (
        "25000-23-37-000-2021-00423-01(30146)(NRD)"
    )


def test_complementar_titulo_con_numero_appends_when_no_acronimo():
    assert _complementar_titulo_con_numero("11001-03-24-000-2026-99999-00", "30146") == (
        "11001-03-24-000-2026-99999-00(30146)"
    )


def test_complementar_titulo_con_numero_is_idempotent_with_acronimo():
    # Calling it twice (e.g. if resolve_unverified_document ever ran on an
    # already-complemented title) must not double-append the number.
    ya_complementado = "25000-23-37-000-2021-00423-01(30146)(NRD)"
    assert _complementar_titulo_con_numero(ya_complementado, "30146") == ya_complementado


def test_complementar_titulo_con_numero_is_idempotent_without_acronimo():
    ya_complementado = "11001-03-24-000-2026-99999-00(30146)"
    assert _complementar_titulo_con_numero(ya_complementado, "30146") == ya_complementado


def test_complementar_titulo_con_numero_is_idempotent_for_numero_ano_format():
    # El guard de "ya complementado" debe reconocer también los formatos
    # número-año y dígitos-con-punto, no solo dígitos puros.
    ya_complementado = "66001-23-33-000-2017-00141-01(3104-2023)(NRD)"
    assert _complementar_titulo_con_numero(ya_complementado, "3104-2023") == ya_complementado


def test_complementar_titulo_con_numero_inserts_numero_ano_format_verbatim():
    assert _complementar_titulo_con_numero("66001-23-33-000-2017-00141-01(NRD)", "3104-2023") == (
        "66001-23-33-000-2017-00141-01(3104-2023)(NRD)"
    )


# --- title_unverified flag y resolve_unverified_document ----------------------


def test_parse_row_flags_title_unverified_only_for_consejo_de_estado():
    row = BeautifulSoup(_ROW_HTML, "html.parser").find("tr")

    ce_scraper = ScrapTribunales("1100103", "Consejo de Estado")
    ce_doc = ce_scraper._parse_row(row, "1100103", "Consejo de Estado", "Sección Primera", "2026-06-15")
    assert ce_doc.title_unverified is True

    tribunal_scraper = ScrapTribunales("2500023", "Tribunal Administrativo de Cundinamarca")
    tribunal_doc = tribunal_scraper._parse_row(
        row, "2500023", "Tribunal Administrativo de Cundinamarca", "Sección Primera", "2026-06-15"
    )
    assert tribunal_doc.title_unverified is False


def test_resolve_unverified_document_appends_extra_number_when_found_on_first_page(monkeypatch):
    monkeypatch.setattr(
        samai_module,
        "_extraer_texto_primera_pagina",
        lambda *_a, **_k: "Radicación  25000-23-37-000-2021-00423-01 (30146)",
    )

    class _Doc:
        title = "25000-23-37-000-2021-00423-01(NRD)"

    doc = _Doc()
    scraper = ScrapTribunales("1100103", "Consejo de Estado")
    scraper.resolve_unverified_document(doc, Path("fake.pdf"), "application/pdf")

    assert doc.title == "25000-23-37-000-2021-00423-01(30146)(NRD)"


def test_resolve_unverified_document_appends_number_when_title_has_no_acronimo(monkeypatch):
    monkeypatch.setattr(
        samai_module,
        "_extraer_texto_primera_pagina",
        lambda *_a, **_k: "Radicación  11001-03-24-000-2026-99999-00 (30146)",
    )

    class _Doc:
        title = "11001-03-24-000-2026-99999-00"

    doc = _Doc()
    scraper = ScrapTribunales("1100103", "Consejo de Estado")
    scraper.resolve_unverified_document(doc, Path("fake.pdf"), "application/pdf")

    assert doc.title == "11001-03-24-000-2026-99999-00(30146)"


def test_resolve_unverified_document_leaves_title_unchanged_when_number_not_found(monkeypatch):
    monkeypatch.setattr(
        samai_module,
        "_extraer_texto_primera_pagina",
        lambda *_a, **_k: "Radicación  25000-23-37-000-2021-00423-01",
    )

    class _Doc:
        title = "25000-23-37-000-2021-00423-01(NRD)"

    doc = _Doc()
    scraper = ScrapTribunales("1100103", "Consejo de Estado")
    scraper.resolve_unverified_document(doc, Path("fake.pdf"), "application/pdf")

    assert doc.title == "25000-23-37-000-2021-00423-01(NRD)"


def test_resolve_unverified_document_is_defensive_about_read_failures(monkeypatch, caplog):
    def _raise(*_a, **_k):
        raise RuntimeError("archivo corrupto")

    monkeypatch.setattr(samai_module, "_extraer_texto_primera_pagina", _raise)

    class _Doc:
        title = "25000-23-37-000-2021-00423-01(NRD)"

    doc = _Doc()
    scraper = ScrapTribunales("1100103", "Consejo de Estado")
    with caplog.at_level("WARNING", logger="core.scrapers.families.samai"):
        scraper.resolve_unverified_document(doc, Path("fake.pdf"), "application/pdf")  # no debe lanzar

    assert doc.title == "25000-23-37-000-2021-00423-01(NRD)"


def test_resolve_unverified_document_ignores_tribunal_administrativo_title_format(monkeypatch):
    monkeypatch.setattr(
        samai_module,
        "_extraer_texto_primera_pagina",
        lambda *_a, **_k: "cualquier texto con (30146) en la página",
    )

    class _Doc:
        title = "T_CUND_25001233300020260001200"

    doc = _Doc()
    scraper = ScrapTribunales("2500023", "Tribunal Administrativo de Cundinamarca")
    scraper.resolve_unverified_document(doc, Path("fake.pdf"), "application/pdf")

    assert doc.title == "T_CUND_25001233300020260001200"
