from core.scrapers.families.supersalud import (
    _es_anexo,
    _fecha_publicacion,
    _fila_a_doc,
    _parse_numero,
    _safe_title,
    _titulo,
)


# ---- _es_anexo ----
def test_es_anexo_true_for_accented_uppercase_prefix():
    assert _es_anexo("Anexo resolución número 2024910010006782-6 de 2024") is True
    assert _es_anexo("ANEXO RESOLUCION No. 2022910010007513-6 de 2022") is True


def test_es_anexo_false_for_normal_title():
    assert _es_anexo("Resolución número 2024910010006787-6 de 2024") is False
    assert _es_anexo("") is False
    assert _es_anexo(None) is False


# ---- _parse_numero ----
def test_parse_numero_radicado_form_takes_last_six_of_twelve_block():
    assert _parse_numero("2026151000000002-5", "") == 2
    assert _parse_numero("2022130000000054-5", "") == 54
    assert _parse_numero("2024910010006787-6", "") == 6787


def test_parse_numero_radicado_form_without_dash():
    assert _parse_numero("20221300000000545", "") == 54


def test_parse_numero_radicado_found_inside_anexo_title():
    assert _parse_numero(None, "Anexo resolución número 2024910010006782-6 de 2024") == 6782


def test_parse_numero_classic_form_strips_leading_zeros_and_trailing_year():
    assert _parse_numero("047", "") == 47
    assert _parse_numero("003 de 2019", "") == 3
    assert _parse_numero("10924 de 2018", "") == 10924


def test_parse_numero_falls_back_to_title_when_numero_raw_blank():
    assert _parse_numero("  ", "Circular Externa 006 de 2016") == 6


def test_parse_numero_returns_none_for_unparseable():
    assert _parse_numero("", "Por medio de la cual se ordena la toma de posesión") is None
    assert _parse_numero("010 de 2017     010 de 2017", "") is None
    assert _parse_numero(None, None) is None


def test_parse_numero_none_for_bare_non_radicado_long_digit_run():
    # 12 dígitos sueltos (no es radicado: _RADICADO_RE exige >=16) y excede el
    # tope clásico de 5 dígitos -> ambiguo -> None (no un título "verificado" con basura)
    assert _parse_numero("910010006787", "") is None


def test_parse_numero_none_when_two_number_runs_in_title_fallback():
    assert _parse_numero("", "Circular 5 modifica Circular 47 de 2016") is None


# ---- _safe_title ----
def test_safe_title_replaces_path_invalid_chars_and_trims():
    assert _safe_title('Doc/con "raros": x|y*') == "Doc-con -raros-- x-y-"
    assert _safe_title("  x.  ") == "x"


def test_safe_title_truncates_to_120():
    assert len(_safe_title("z" * 300)) == 120


# ---- _titulo ----
def test_titulo_verified_canonical_code():
    assert _titulo("C", "2026151000000002-5", "irrelevante", "2026", False) == ("C_SNS_0002_2026", False)
    assert _titulo("R", "2024910010006787-6", "irrelevante", "2024", False) == ("R_SNS_6787_2024", False)


def test_titulo_verified_anexo_gets_fixed_a01_suffix():
    assert _titulo(
        "R", None, "Anexo resolución número 2024910010006782-6 de 2024", "2024", True
    ) == ("R_SNS_6782_2024_A01", False)


def test_titulo_unverified_keeps_raw_title_trimmed_to_120():
    title, unv = _titulo("R", "", "Por medio de la cual se ordena la toma de posesión", "2013", False)
    assert unv is True
    assert title == "Por medio de la cual se ordena la toma de posesión"


def test_titulo_unverified_anexo_has_no_suffix():
    title, unv = _titulo("C", "", "Anexo - Tablas de referencia - CE", "2026", True)
    assert unv is True
    assert title == "Anexo - Tablas de referencia - CE"
    assert not title.endswith("_A01")


# ---- _fecha_publicacion ----
def test_fecha_publicacion_takes_first_half_of_doubled_value():
    raw = "2026-09-04T05:00:00Z\n\n2026-09-04T05:00:00.0000000Z"
    assert _fecha_publicacion(raw) == "2026-09-04"


def test_fecha_publicacion_single_value():
    assert _fecha_publicacion("2021-08-18T05:00:00.0000000Z") == "2021-08-18"


def test_fecha_publicacion_none_when_missing_or_unparseable():
    assert _fecha_publicacion(None) is None
    assert _fecha_publicacion("") is None
    assert _fecha_publicacion("sin fecha") is None


# ---- _fila_a_doc ----
_FILA_RESOLUCION = {
    "Title": "Resolución número 2024910010006787-6 de 2024",
    "Path": "https://docs.supersalud.gov.co/PortalWeb/Juridica/Resoluciones/Resolución número 2024910010006787-6 de 2024.pdf",
    "NumeroOWSTEXT": "2024910010006787-6",
    "DescripcionOWSMTXT": "Por la cual se efectúa un nombramiento en periodo de prueba.",
    "FechadePublicacionOWSDATE": "2024-07-09T05:00:00Z\n\n2024-07-09T05:00:00.0000000Z",
    "RefinableString00": "2024",
    "FileExtension": "pdf",
}


def test_fila_a_doc_maps_verified_resolucion():
    doc = _fila_a_doc(_FILA_RESOLUCION, "Resolución", "R", "2024-01-01", "2024-12-31", None)
    assert doc is not None
    assert doc.title == "R_SNS_6787_2024"
    assert doc.title_unverified is False
    assert doc.tipo == "Resolución"
    assert doc.source == "Superintendencia Nacional de Salud"
    assert doc.f_public == "2024-07-09"
    assert doc.f_providencia == "2024-07-09"
    assert doc.detalle == "Por la cual se efectúa un nombramiento en periodo de prueba."
    assert doc.link == {
        "url": _FILA_RESOLUCION["Path"],
        "method": "GET",
    }
    assert doc.save_path == (
        "Superintendencia Nacional de Salud/2024-07-09/Resolución/R_SNS_6787_2024(extension)"
    )


def test_fila_a_doc_zip_path_is_used_verbatim():
    fila = dict(_FILA_RESOLUCION)
    fila["Title"] = "Circular Externa 006 de 2016"
    fila["NumeroOWSTEXT"] = "006"
    fila["Path"] = "https://docs.supersalud.gov.co/PortalWeb/Juridica/CircularesExterna/Circular Externa 006 de 2016.zip"
    fila["FechadePublicacionOWSDATE"] = "2016-05-02T05:00:00Z"
    fila["FileExtension"] = "zip"
    doc = _fila_a_doc(fila, "Circular Externa", "C", "2015-01-01", "2016-12-31", None)
    assert doc.title == "C_SNS_0006_2016"
    assert doc.link["url"].endswith(".zip")


def test_fila_a_doc_anexo_gets_a01_suffix():
    fila = dict(_FILA_RESOLUCION)
    fila["Title"] = "Anexo resolución número 2024910010006782-6 de 2024"
    fila["NumeroOWSTEXT"] = "2024910010006782-6"
    doc = _fila_a_doc(fila, "Resolución", "R", "2024-01-01", "2024-12-31", None)
    assert doc.title == "R_SNS_6782_2024_A01"
    assert doc.title_unverified is False


def test_fila_a_doc_unverified_when_no_number():
    fila = dict(_FILA_RESOLUCION)
    fila["Title"] = "Por medio de la cual se ordena la toma de posesión"
    fila["NumeroOWSTEXT"] = ""
    doc = _fila_a_doc(fila, "Resolución", "R", "2024-01-01", "2024-12-31", None)
    assert doc.title == "Por medio de la cual se ordena la toma de posesión"
    assert doc.title_unverified is True
    # save_path saneado: exactamente 4 segmentos, sin caracteres inválidos en el archivo
    segmentos = doc.save_path.split("/")
    assert len(segmentos) == 4
    assert not any(c in segmentos[-1] for c in '\\/*?:"<>|')


def test_fila_a_doc_returns_none_outside_date_range():
    doc = _fila_a_doc(_FILA_RESOLUCION, "Resolución", "R", "2025-01-01", "2025-12-31", None)
    assert doc is None


def test_fila_a_doc_returns_none_without_path():
    fila = dict(_FILA_RESOLUCION)
    fila["Path"] = None
    assert _fila_a_doc(fila, "Resolución", "R", "2024-01-01", "2024-12-31", None) is None


def test_fila_a_doc_returns_none_and_warns_without_date():
    fila = dict(_FILA_RESOLUCION)
    fila["FechadePublicacionOWSDATE"] = None
    avisos = []
    assert _fila_a_doc(fila, "Resolución", "R", "2024-01-01", "2024-12-31", avisos.append) is None
    assert any("sin fecha" in m.lower() for m in avisos)


import json

import responses

from core.scrapers.families.supersalud import _build_body, _form_digest, _process_query


def _bom(payload) -> bytes:
    return b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8")


def test_build_body_embeds_folder_year_hex_and_pagination():
    body = _build_body("CircularesExterna", 2015, 500, 500)
    assert "PortalWeb/Juridica/CircularesExterna" in body
    # 2015 -> UTF-8 hex
    assert "32303135" in body
    assert "ǂǂ" in body
    assert "<Parameter Type=\"Number\">500</Parameter>" in body  # RowLimit
    # TypeIds de KeywordQuery y SearchExecutor
    assert "80173281-fffd-47b6-9a49-312e06ff8428" in body
    assert "8d2ac302-db2f-46fe-9015-872b35f15098" in body


@responses.activate
def test_form_digest_decodes_bom_and_returns_value():
    responses.add(
        responses.POST,
        "https://www.supersalud.gov.co/es-co/_api/contextinfo",
        body=_bom({"FormDigestValue": "0xDEADBEEF"}),
        content_type="application/json",
    )
    session = __import__("requests").Session()
    assert _form_digest(session) == "0xDEADBEEF"


@responses.activate
def test_process_query_returns_result_rows_and_sends_digest_header():
    payload = [
        {"SchemaVersion": "15.0.0.0", "ErrorInfo": None},
        {
            "ResultTables": [
                {
                    "TableType": "RelevantResults",
                    "Properties": {},
                    "ResultRows": [
                        {"Title": "Circular externa número 2026151000000002-5 de 2026",
                         "Path": "https://docs.supersalud.gov.co/PortalWeb/Juridica/CircularesExterna/x.pdf",
                         "NumeroOWSTEXT": "2026151000000002-5",
                         "FechadePublicacionOWSDATE": "2026-01-10T05:00:00Z",
                         "RefinableString00": "2026"},
                    ],
                }
            ]
        },
    ]
    responses.add(
        responses.POST,
        "https://www.supersalud.gov.co/es-co/_vti_bin/client.svc/ProcessQuery",
        body=_bom(payload),
        content_type="application/json",
    )
    session = __import__("requests").Session()
    rows = _process_query(session, "0xDIGEST", "CircularesExterna", 2026, 0)
    assert len(rows) == 1
    assert rows[0]["NumeroOWSTEXT"] == "2026151000000002-5"
    assert responses.calls[0].request.headers["X-RequestDigest"] == "0xDIGEST"
    assert responses.calls[0].request.headers["Content-Type"] == "text/xml"


@responses.activate
def test_process_query_raises_on_error_info():
    payload = [
        {"SchemaVersion": "15.0.0.0",
         "ErrorInfo": {"ErrorMessage": "La validación de seguridad de esta página no es válida"}},
    ]
    responses.add(
        responses.POST,
        "https://www.supersalud.gov.co/es-co/_vti_bin/client.svc/ProcessQuery",
        body=_bom(payload),
        content_type="application/json",
    )
    session = __import__("requests").Session()
    try:
        _process_query(session, "0xDIGEST", "Resoluciones", 2020, 0)
    except RuntimeError as e:
        assert "validación de seguridad" in str(e)
    else:
        raise AssertionError("esperaba RuntimeError")


import threading

from core.scrapers.registry import FAMILY_REGISTRY
from core.scrapers.families.supersalud import ScrapSupersalud

_CONTEXTINFO_URL = "https://www.supersalud.gov.co/es-co/_api/contextinfo"
_PQ_URL = "https://www.supersalud.gov.co/es-co/_vti_bin/client.svc/ProcessQuery"


def _rows_payload(rows):
    return [
        {"SchemaVersion": "15.0.0.0", "ErrorInfo": None},
        {"ResultTables": [{"TableType": "RelevantResults", "Properties": {}, "ResultRows": rows}]},
    ]


def _row(title, numero, fecha, path, anio):
    return {
        "Title": title, "NumeroOWSTEXT": numero, "DescripcionOWSMTXT": "desc",
        "FechadePublicacionOWSDATE": fecha, "Path": path, "RefinableString00": anio, "FileExtension": "pdf",
    }


def test_supersalud_is_registered():
    import core.scrapers.families  # noqa: F401
    assert FAMILY_REGISTRY["supersalud"].__name__ == "ScrapSupersalud"


def test_filters_by_publication_date_is_enabled():
    assert ScrapSupersalud.filters_by_publication_date is True


@responses.activate
def test_scrap_collects_both_categories_one_year():
    responses.add(responses.POST, _CONTEXTINFO_URL, body=_bom({"FormDigestValue": "0xD"}))

    def cb(request):
        body = request.body.decode("utf-8") if isinstance(request.body, bytes) else request.body
        if "Juridica/Resoluciones" in body:
            rows = [_row("Resolución número 2026910010008999-6 de 2026", "2026910010008999-6",
                         "2026-03-04T05:00:00Z", "https://docs.supersalud.gov.co/PortalWeb/Juridica/Resoluciones/a.pdf", "2026")]
        else:
            rows = [_row("Circular externa número 2026151000000002-5 de 2026", "2026151000000002-5",
                         "2026-02-10T05:00:00Z", "https://docs.supersalud.gov.co/PortalWeb/Juridica/CircularesExterna/b.pdf", "2026")]
        return (200, {}, _bom(_rows_payload(rows)))

    responses.add_callback(responses.POST, _PQ_URL, callback=cb, content_type="application/json")

    docs = ScrapSupersalud().scrap(fini="2026-01-01", ffin="2026-12-31")
    assert {d.title for d in docs} == {"R_SNS_8999_2026", "C_SNS_0002_2026"}


@responses.activate
def test_scrap_floors_start_year_at_2015():
    responses.add(responses.POST, _CONTEXTINFO_URL, body=_bom({"FormDigestValue": "0xD"}))
    seen_years = []

    def cb(request):
        body = request.body.decode("utf-8") if isinstance(request.body, bytes) else request.body
        # el año va como hex UTF-8 dentro del refiner; recuperarlo
        import re as _re
        m = _re.search(r"ǂǂ([0-9a-f]+)&quot;", body)
        year = bytes.fromhex(m.group(1)).decode("utf-8")
        seen_years.append(year)
        return (200, {}, _bom(_rows_payload([])))

    responses.add_callback(responses.POST, _PQ_URL, callback=cb, content_type="application/json")

    ScrapSupersalud().scrap(fini="2010-01-01", ffin="2015-12-31")
    assert "2010" not in seen_years
    assert "2015" in seen_years


@responses.activate
def test_scrap_paginates_when_page_is_full():
    responses.add(responses.POST, _CONTEXTINFO_URL, body=_bom({"FormDigestValue": "0xD"}))
    calls = {"n": 0}

    def cb(request):
        body = request.body.decode("utf-8") if isinstance(request.body, bytes) else request.body
        if "Juridica/CircularesExterna" not in body:
            return (200, {}, _bom(_rows_payload([])))
        calls["n"] += 1
        if calls["n"] == 1:
            rows = [_row(f"Circular Externa {i:03d} de 2016", f"{i:03d}", "2016-06-01T05:00:00Z",
                         f"https://docs.supersalud.gov.co/PortalWeb/Juridica/CircularesExterna/{i}.pdf", "2016")
                    for i in range(1, 501)]
        else:
            rows = [_row("Circular Externa 900 de 2016", "900", "2016-07-01T05:00:00Z",
                         "https://docs.supersalud.gov.co/PortalWeb/Juridica/CircularesExterna/900.pdf", "2016")]
        return (200, {}, _bom(_rows_payload(rows)))

    responses.add_callback(responses.POST, _PQ_URL, callback=cb, content_type="application/json")

    docs = ScrapSupersalud().scrap(fini="2016-01-01", ffin="2016-12-31")
    assert calls["n"] == 2
    assert any(d.title == "C_SNS_0900_2016" for d in docs)


@responses.activate
def test_scrap_continues_past_a_failing_year():
    responses.add(responses.POST, _CONTEXTINFO_URL, body=_bom({"FormDigestValue": "0xD"}))

    def cb(request):
        body = request.body.decode("utf-8") if isinstance(request.body, bytes) else request.body
        import re as _re
        m = _re.search(r"ǂǂ([0-9a-f]+)&quot;", body)
        year = bytes.fromhex(m.group(1)).decode("utf-8")
        if year == "2015":
            return (200, {}, _bom([{"ErrorInfo": {"ErrorMessage": "boom interno"}}]))
        rows = [_row("Circular externa número 2016151000000003-5 de 2016", "2016151000000003-5",
                     "2016-05-01T05:00:00Z", "https://docs.supersalud.gov.co/PortalWeb/Juridica/CircularesExterna/x.pdf", "2016")]
        return (200, {}, _bom(_rows_payload(rows)))

    responses.add_callback(responses.POST, _PQ_URL, callback=cb, content_type="application/json")

    progreso = []
    docs = ScrapSupersalud().scrap(fini="2015-01-01", ffin="2016-12-31", on_progress=progreso.append)
    assert any(d.title == "C_SNS_0003_2016" for d in docs)
    assert any("Error" in m for m in progreso)


@responses.activate
def test_scrap_stops_on_stop_event():
    responses.add(responses.POST, _CONTEXTINFO_URL, body=_bom({"FormDigestValue": "0xD"}))
    ev = threading.Event()

    def cb(request):
        ev.set()  # se dispara en la primera consulta
        rows = [_row("Circular Externa 001 de 2015", "001", "2015-01-05T05:00:00Z",
                     "https://docs.supersalud.gov.co/PortalWeb/Juridica/CircularesExterna/1.pdf", "2015")]
        return (200, {}, _bom(_rows_payload(rows)))

    responses.add_callback(responses.POST, _PQ_URL, callback=cb, content_type="application/json")

    docs = ScrapSupersalud().scrap(fini="2015-01-01", ffin="2018-12-31", stop_event=ev)
    # se permite 0..N docs de la primera página, pero no debe recorrer los 4 años x 2 categorías
    assert len(responses.calls) <= 3  # 1 contextinfo + a lo sumo 2 process_query


def test_seed_families_dict_has_supersalud_entry():
    from core.seed import _FAMILIES
    assert "supersalud" in _FAMILIES
    display_name, description = _FAMILIES["supersalud"]
    assert display_name == "Superintendencia Nacional de Salud"
    assert "esolucion" in description or "esoluciones" in description
    assert "irculares" in description
