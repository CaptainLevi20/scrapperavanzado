import responses

from core.scrapers.families.rama_judicial import (
    JUZGADOS_ENTIDADES,
    SUPERIORES_DEPTS,
    TRIBUNAL_CODES,
    ScrapRamaJudicial,
    _extract_detalle,
    _normalize_title,
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

# Real-world case found while piloting Tribunal Superior de Bogotá (June 2026):
# an unclaimed "estado" notification reappears in the next day's listing
# pointing at the exact same underlying file (identical download uuid), just
# under a different listing row/date.
_LISTING_HTML_REPUBLISHED = """
<html><body>
<span>Página 1 de 1</span>
<tbody class="table-data">
<tr>
  <div class="titulo-publicacion"><a href="https://publicacionesprocesales.ramajudicial.gov.co/detalle/1">Ver</a></div>
  <p class="publish-date">Fecha: 10/06/2026</p>
  <span class="categoria-ep">Tipo de publicación: Sentencias</span>
  <span class="categoria-ep">Especialidad: Civil</span>
  <span class="categoria-ep">Despacho: Juzgado 1 Civil del Circuito</span>
</tr>
<tr>
  <div class="titulo-publicacion"><a href="https://publicacionesprocesales.ramajudicial.gov.co/detalle/2">Ver</a></div>
  <p class="publish-date">Fecha: 11/06/2026</p>
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


def test_tribunal_codes_has_one_entry_per_superiores_dept():
    assert set(TRIBUNAL_CODES.keys()) == set(SUPERIORES_DEPTS.keys())
    assert TRIBUNAL_CODES["11"] == "BTA"
    assert TRIBUNAL_CODES["76"] == "VALL"
    assert TRIBUNAL_CODES["54"] == "NSAN"
    assert TRIBUNAL_CODES["68"] == "SANT"


def test_normalize_title_builds_prefix_from_23_digit_radicado():
    assert _normalize_title("11001310302020220015001_DraGonzalezAutoAdmiteRecurso", "11") == (
        "T_BTA_11001_31_03_020_2022_00150_01"
    )


def test_normalize_title_ignores_everything_after_the_radicado():
    # el juez y la acción se descartan por completo, no se guardan en ningún lado
    assert _normalize_title("11001310302020220015001_ AnythingElseHere123", "11") == (
        "T_BTA_11001_31_03_020_2022_00150_01"
    )


def test_normalize_title_tolerates_missing_dr_prefix():
    # caso real: el despacho subió el archivo sin "Dr"/"Dra" — la condición de
    # disparo es solo el prefijo de 23 dígitos, no depende de "Dr"/"Dra"
    assert _normalize_title("11001310303320170034203_ValenzuelaSentenciaSegundaInstancia", "11") == (
        "T_BTA_11001_31_03_033_2017_00342_03"
    )


def test_normalize_title_leaves_person_name_titles_unchanged():
    original = "033-2025-00417-01 PAOLA ANDREA NARANJO QUINTANA"
    assert _normalize_title(original, "11") == original


def test_normalize_title_leaves_generic_estado_titles_unchanged():
    original = "ESTADO E-0109 DEL 26 DE JUNIO DE 2026"
    assert _normalize_title(original, "11") == original


def test_normalize_title_leaves_titles_unchanged_when_dept_code_has_no_tribunal_code():
    # Juzgados no tienen dept_code (family_params usa dept_code="", ver core/seed.py)
    original = "11001310302020220015001_DraGonzalezAutoAdmiteRecurso"
    assert _normalize_title(original, "") == original


def test_normalize_title_leaves_titles_unchanged_when_digit_prefix_is_not_23_long():
    original = "1234567890123456789012_DraGonzalezAutoAdmiteRecurso"  # 22 dígitos, no 23
    assert _normalize_title(original, "11") == original


def test_normalize_title_builds_prefix_when_radicado_is_followed_by_a_space():
    # caso real de Tribunal Superior de Antioquia (18% de sus documentos):
    # el despacho separa el radicado de la acción con un espacio, no "_".
    assert _normalize_title("05001310300220250025101 AutoResuelveRecursoDeApelacion", "05") == (
        "T_ANTI_05001_31_03_002_2025_00251_01"
    )


def test_normalize_title_builds_prefix_for_a_bare_radicado_with_nothing_after():
    # caso real de Tribunal Superior de Antioquia (35% de sus documentos): el
    # nombre de archivo es solo el radicado, sin acción ni separador después.
    assert _normalize_title("05579310300120250001701", "05") == (
        "T_ANTI_05579_31_03_001_2025_00017_01"
    )


def test_normalize_title_builds_prefix_when_radicado_is_preceded_by_a_date():
    # caso real de Tribunal Superior de Antioquia (Acciones de Tutela): el
    # nombre de archivo empieza con "DD-MM-YYYY " antes del radicado.
    assert _normalize_title("01-06-2026 05000222100020261001900", "05") == (
        "T_ANTI_05000_22_21_000_2026_10019_00"
    )


def test_extract_detalle_strips_judge_prefix_and_splits_camel_case():
    assert _extract_detalle("11001310302020220015001_DraGonzalezAutoAdmiteRecurso") == (
        "Auto Admite Recurso"
    )


def test_extract_detalle_splits_the_whole_suffix_when_there_is_no_judge_prefix():
    # caso real: el despacho subió el archivo sin "Dr"/"Dra" antes del apellido
    assert _extract_detalle("11001310303320170034203_ValenzuelaSentenciaSegundaInstancia") == (
        "Valenzuela Sentencia Segunda Instancia"
    )


def test_extract_detalle_treats_underscore_as_a_word_boundary():
    assert _extract_detalle("11001310301620170055608_DrAtshanAutoOrdenaRemitir_Cumplase") == (
        "Auto Ordena Remitir Cumplase"
    )


def test_extract_detalle_tolerates_a_stray_space_after_the_radicado():
    # caso real: espacio extra antes de "Dr"
    assert _extract_detalle("11001310300220230031101_ DrZamudioAutoResuelevApelacion") == (
        "Auto Resuelev Apelacion"
    )


def test_extract_detalle_returns_none_for_person_name_titles():
    assert _extract_detalle("033-2025-00417-01 PAOLA ANDREA NARANJO QUINTANA") is None


def test_extract_detalle_returns_none_for_generic_estado_titles():
    assert _extract_detalle("ESTADO E-0109 DEL 26 DE JUNIO DE 2026") is None


def test_extract_detalle_returns_none_when_digit_prefix_is_not_23_long():
    assert _extract_detalle("1234567890123456789012_DraGonzalezAutoAdmiteRecurso") is None  # 22 dígitos


def test_extract_detalle_splits_action_when_radicado_is_followed_by_a_space():
    # caso real de Tribunal Superior de Antioquia (ver test_normalize_title
    # equivalente arriba)
    assert _extract_detalle("05001310302120220029802 AutoDeclaraInadmisibleRecursoDeApelacion") == (
        "Auto Declara Inadmisible Recurso De Apelacion"
    )


def test_extract_detalle_returns_none_for_a_bare_radicado_with_nothing_after():
    # caso real: sin acción que extraer, no debe devolver "" sino None
    assert _extract_detalle("05579310300120250001701") is None


def test_extract_detalle_returns_none_when_radicado_is_preceded_by_a_date_and_nothing_follows():
    assert _extract_detalle("01-06-2026 05000222100020261001900") is None


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
    assert doc.link == {
        "url": _BASE_DOMAIN + "/descargas/archivo.pdf?uuid=abc-123",
        "method": "GET",
        "body": {"path": "abc-123"},
    }
    assert doc.save_path == (
        "Tribunal Superior de Antioquia/Civil/Juzgado 1 Civil del Circuito/2024-06-15/Sentencias/Auto_2024(extension)"
    )


@responses.activate
def test_scrap_normalizes_title_for_documents_with_a_23_digit_radicado(monkeypatch):
    responses.add(
        responses.GET,
        "https://publicacionesprocesales.ramajudicial.gov.co/web/publicaciones-procesales/inicio",
        body=_LISTING_HTML,
        status=200,
    )

    scraper = ScrapRamaJudicial(dept_code="11", dept_name="Tribunal Superior de Bogotá", entidad_id="22")
    monkeypatch.setattr(scraper, "_get_instance_id", lambda session, headers: "XYZ")
    monkeypatch.setattr(
        scraper,
        "_fetch_detail",
        lambda headers, url: [
            (
                "11001310302020220015001_DraGonzalezAutoAdmiteRecurso.pdf",
                _BASE_DOMAIN + "/descargas/archivo.pdf?uuid=abc-999",
                "abc-999",
            )
        ],
    )

    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1
    assert docs[0].title == "T_BTA_11001_31_03_020_2022_00150_01"


@responses.activate
def test_scrap_populates_detalle_for_documents_with_a_23_digit_radicado(monkeypatch):
    responses.add(
        responses.GET,
        "https://publicacionesprocesales.ramajudicial.gov.co/web/publicaciones-procesales/inicio",
        body=_LISTING_HTML,
        status=200,
    )

    scraper = ScrapRamaJudicial(dept_code="11", dept_name="Tribunal Superior de Bogotá", entidad_id="22")
    monkeypatch.setattr(scraper, "_get_instance_id", lambda session, headers: "XYZ")
    monkeypatch.setattr(
        scraper,
        "_fetch_detail",
        lambda headers, url: [
            (
                "11001310302020220015001_DraGonzalezAutoAdmiteRecurso.pdf",
                _BASE_DOMAIN + "/descargas/archivo.pdf?uuid=abc-999",
                "abc-999",
            )
        ],
    )

    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1
    assert docs[0].detalle == "Auto Admite Recurso"


@responses.activate
def test_scrap_leaves_detalle_none_for_a_non_matching_title(monkeypatch):
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
    assert docs[0].detalle is None


@responses.activate
def test_scrap_does_not_normalize_title_for_a_source_without_a_tribunal_code(monkeypatch):
    responses.add(
        responses.GET,
        "https://publicacionesprocesales.ramajudicial.gov.co/web/publicaciones-procesales/inicio",
        body=_LISTING_HTML,
        status=200,
    )

    # dept_code="" es como se instancia un Juzgado (ver core/seed.py) — no tiene
    # código de tribunal, así que el título nunca se normaliza.
    scraper = ScrapRamaJudicial(dept_code="", dept_name="Juzgado de Circuito", entidad_id="31")
    monkeypatch.setattr(scraper, "_get_instance_id", lambda session, headers: "XYZ")
    monkeypatch.setattr(
        scraper,
        "_fetch_detail",
        lambda headers, url: [
            (
                "11001310302020220015001_DraGonzalezAutoAdmiteRecurso.pdf",
                _BASE_DOMAIN + "/descargas/archivo.pdf?uuid=abc-999",
                "abc-999",
            )
        ],
    )

    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1
    assert docs[0].title == "11001310302020220015001_DraGonzalezAutoAdmiteRecurso"


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


@responses.activate
def test_scrap_does_not_truncate_especialidad_and_seccion_metadata_for_long_despacho_names(monkeypatch):
    # Real case found piloting Tribunal Superior de Bogotá (June 2026): the
    # despacho "110012220000 - SECRETARÍA SALA EXTINCIÓN DE DOMINIO DEL
    # TRIBUNAL SUPERIOR DE BOGOTÁ" (84 chars) was getting stored as "...DEL
    # TRIB" — cut off mid-word — because the save_path's 60-char folder-safe
    # truncation was reused as the seccion/especialidad metadata field too.
    despacho_completo = "110012220000 - SECRETARÍA SALA EXTINCIÓN DE DOMINIO DEL TRIBUNAL SUPERIOR DE BOGOTÁ"
    listing_html = _LISTING_HTML.replace(
        "Despacho: Juzgado 1 Civil del Circuito", f"Despacho: {despacho_completo}"
    )
    responses.add(
        responses.GET,
        "https://publicacionesprocesales.ramajudicial.gov.co/web/publicaciones-procesales/inicio",
        body=listing_html,
        status=200,
    )

    scraper = ScrapRamaJudicial(dept_code="11", dept_name="Tribunal Superior de Bogotá", entidad_id="22")
    monkeypatch.setattr(scraper, "_get_instance_id", lambda session, headers: "XYZ")
    monkeypatch.setattr(
        scraper,
        "_fetch_detail",
        lambda headers, url: [("Auto_2024.pdf", _BASE_DOMAIN + "/descargas/archivo.pdf?uuid=abc-123", "abc-123")],
    )

    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1
    assert docs[0].seccion == despacho_completo
    # el segmento de carpeta sigue acotado a 60 caracteres (límites de ruta)
    assert "110012220000 - SECRETARÍA SALA EXTINCIÓN DE DOMINIO DEL TRIB/" in docs[0].save_path


@responses.activate
def test_scrap_logs_and_skips_a_malformed_row_without_aborting_the_rest(monkeypatch, caplog):
    # A publish-date with an unexpected "DD/MM" (no year) makes the
    # `dia, mes, anio = fecha_p_raw.split("/")` unpacking raise ValueError;
    # that must only skip this one row, not abort the whole page.
    listing_html = _LISTING_HTML_REPUBLISHED.replace(
        '<p class="publish-date">Fecha: 10/06/2026</p>', '<p class="publish-date">Fecha: 10/06</p>'
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

    with caplog.at_level("WARNING", logger="core.scrapers.families.rama_judicial"):
        docs = scraper.scrap(fini="2026-06-01", ffin="2026-06-30")

    assert len(docs) == 1  # la fila malformada se salta, la válida se conserva
    assert docs[0].f_public == "2026-06-11"
    # Regression test: this used to be a bare print(), invisible to server logs —
    # now it must go through the logging module like the rest of the project.
    assert any("Error procesando fila" in r.message for r in caplog.records)


def test_rama_judicial_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["rama_judicial"] is ScrapRamaJudicial


@responses.activate
def test_scrap_deduplicates_the_same_file_republished_under_a_later_date(monkeypatch):
    responses.add(
        responses.GET,
        "https://publicacionesprocesales.ramajudicial.gov.co/web/publicaciones-procesales/inicio",
        body=_LISTING_HTML_REPUBLISHED,
        status=200,
    )

    scraper = ScrapRamaJudicial(dept_code="05", dept_name="Tribunal Superior de Antioquia", entidad_id="22")
    monkeypatch.setattr(scraper, "_get_instance_id", lambda session, headers: "XYZ")
    monkeypatch.setattr(
        scraper,
        "_fetch_detail",
        lambda headers, url: [("Auto_2024.pdf", _BASE_DOMAIN + "/descargas/archivo.pdf?uuid=same-uuid", "same-uuid")],
    )
    # confirms it's genuinely the same file (same size) rather than assuming from uuid alone
    monkeypatch.setattr(
        "core.scrapers.families.rama_judicial.check_remote_content_length", lambda url, timeout=15: 1024
    )

    docs = scraper.scrap(fini="2026-06-01", ffin="2026-06-30")

    assert len(docs) == 1


@responses.activate
def test_scrap_keeps_first_occurrence_even_when_the_size_check_is_inconclusive(monkeypatch):
    # A HEAD that fails or lacks Content-Length can't confirm anything either
    # way; still only one RawDocModel per file_uuid is ever returned (a second
    # one would collide on doc_id and violate the DB's unique constraint).
    responses.add(
        responses.GET,
        "https://publicacionesprocesales.ramajudicial.gov.co/web/publicaciones-procesales/inicio",
        body=_LISTING_HTML_REPUBLISHED,
        status=200,
    )

    scraper = ScrapRamaJudicial(dept_code="05", dept_name="Tribunal Superior de Antioquia", entidad_id="22")
    monkeypatch.setattr(scraper, "_get_instance_id", lambda session, headers: "XYZ")
    monkeypatch.setattr(
        scraper,
        "_fetch_detail",
        lambda headers, url: [("Auto_2024.pdf", _BASE_DOMAIN + "/descargas/archivo.pdf?uuid=same-uuid", "same-uuid")],
    )
    monkeypatch.setattr(
        "core.scrapers.families.rama_judicial.check_remote_content_length", lambda url, timeout=15: None
    )

    docs = scraper.scrap(fini="2026-06-01", ffin="2026-06-30")

    assert len(docs) == 1
    assert docs[0].f_public == "2026-06-10"  # se conserva la primera aparición


@responses.activate
def test_scrap_keeps_first_occurrence_even_when_the_size_check_disagrees(monkeypatch, caplog):
    # Sizes genuinely differing despite an identical uuid would be surprising
    # (the whole point of using uuid as doc_id is that it IS the file's stable
    # identity) but must not crash the run or return two docs for one uuid.
    responses.add(
        responses.GET,
        "https://publicacionesprocesales.ramajudicial.gov.co/web/publicaciones-procesales/inicio",
        body=_LISTING_HTML_REPUBLISHED,
        status=200,
    )

    scraper = ScrapRamaJudicial(dept_code="05", dept_name="Tribunal Superior de Antioquia", entidad_id="22")
    monkeypatch.setattr(scraper, "_get_instance_id", lambda session, headers: "XYZ")
    monkeypatch.setattr(
        scraper,
        "_fetch_detail",
        lambda headers, url: [("Auto_2024.pdf", _BASE_DOMAIN + "/descargas/archivo.pdf?uuid=same-uuid", "same-uuid")],
    )
    sizes = iter([1024, 2048])
    monkeypatch.setattr(
        "core.scrapers.families.rama_judicial.check_remote_content_length",
        lambda url, timeout=15: next(sizes),
    )

    with caplog.at_level("WARNING", logger="core.scrapers.families.rama_judicial"):
        docs = scraper.scrap(fini="2026-06-01", ffin="2026-06-30")

    assert len(docs) == 1
    assert docs[0].f_public == "2026-06-10"
    # Regression test: this used to be a bare print(), invisible to server logs —
    # now it must go through the logging module like the rest of the project.
    assert any("cambió de tamaño" in r.message for r in caplog.records)
