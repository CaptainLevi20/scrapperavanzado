import json
import re
from pathlib import Path

import responses

import core.scrapers.families.corte_suprema as csj_module
from core.scrapers.families.corte_suprema import ScrapCorteSuprema
from core.scrapers.registry import FAMILY_REGISTRY

_URL = "https://consultaprovidenciasbk.cortesuprema.gov.co/api"


def _item(
    title="SC1234-2024.pdf",
    fecha="2024-02-01T15:00:00Z",  # 10:00 COT — solidly Feb 1 in both UTC and Colombia time
    auto_sentencia="SENTENCIA",
    online_path="path/to/file",
):
    # typeOfDocument always comes back null from the real API — tipo is
    # derived from autoSentencia instead (see ScrapCorteSuprema.scrap).
    return {
        "typeOfDocument": None,
        "autoSentencia": auto_sentencia,
        "title": title,
        "id": online_path,
        "onlinePath": online_path,
        "fechaCreacion": fecha,
    }


def _callback_factory(item_fecha="2024-02-01T15:00:00Z"):
    def _callback(request):
        body = json.loads(request.body)
        query = body["query"]
        start = int(re.search(r"start:\s*(\d+)", query).group(1))
        if start == 0:
            payload = {"data": {"getSearchResult": {"searchResults": [_item(fecha=item_fecha)]}}}
        else:
            payload = {"data": {"getSearchResult": {"searchResults": []}}}
        return (200, {"Content-Type": "application/json"}, json.dumps(payload))

    return _callback


@responses.activate
def test_scrap_returns_one_doc_per_tipo_within_range():
    responses.add_callback(responses.POST, _URL, callback=_callback_factory(), content_type="application/json")

    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    assert len(docs) == 4  # uno por cada tipo: Tutelas, Laboral, Civil, Penal
    assert {d.tipo for d in docs} == {"Sentencia"}
    assert {d.f_public for d in docs} == {"2024-02-01"}
    title_by_bucket = {d.save_path.split("/")[1]: d.title for d in docs}
    assert title_by_bucket == {
        "SCT": "SC1234-2024",
        "SCL": "SC1234-2024",
        "SCC": "SC1234-2024",
        "SCP": "SC1234-2024",
    }
    assert docs[0].link == {
        "url": "https://consultaprovidenciasbk.cortesuprema.gov.co/downloadFile/",
        "body": {"path": "path/to/file"},
        "method": "POST",
    }


@responses.activate
def test_scrap_attributes_a_late_evening_colombia_document_to_the_correct_local_day():
    """Regression test: fechaCreacion comes back as a UTC instant. A document
    published at 8pm Colombia time (COT, UTC-5) lands after midnight UTC — the
    old code compared the raw UTC .date() against the requested Colombia
    calendar day and excluded it, even though a fini=ffin request for exactly
    that day should have included it."""
    # 2026-07-28 20:00 COT == 2026-07-29 01:00 UTC
    responses.add_callback(
        responses.POST,
        _URL,
        callback=_callback_factory(item_fecha="2026-07-29T01:00:00Z"),
        content_type="application/json",
    )

    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2026-07-28", ffin="2026-07-28")

    assert len(docs) == 4  # uno por cada tipo: Tutelas, Laboral, Civil, Penal
    assert {d.f_public for d in docs} == {"2026-07-28"}


@responses.activate
def test_scrap_does_not_include_the_previous_colombia_day_via_a_pre_midnight_utc_instant():
    """The mirror image of the test above: a document published just before
    midnight UTC on day D+1 is actually still day D in Colombia (UTC-5) — but
    one published at, say, 11pm UTC on day D+1 is genuinely day D+1 in
    Colombia too (23:00 UTC - 5h = 18:00 COT, same calendar day). This pins
    down that the conversion doesn't overcorrect and start including the WRONG
    extra day instead."""
    # 2026-07-29 23:00 UTC == 2026-07-29 18:00 COT — genuinely the 29th in Colombia too.
    responses.add_callback(
        responses.POST,
        _URL,
        callback=_callback_factory(item_fecha="2026-07-29T23:00:00Z"),
        content_type="application/json",
    )

    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2026-07-28", ffin="2026-07-28")

    assert docs == []


@responses.activate
def test_scrap_limit_is_per_tipo_not_shared_across_all_four():
    # Regression guard: `limit` used to be checked against the cumulative doc
    # count across ALL FOUR tipos combined, so once "Tutelas" (processed
    # first, per self.tipos' iteration order) filled the whole shared budget,
    # Laboral/Civil/Penal each got stuck with just 1 document apiece no
    # matter how many were really available — exactly what was observed in
    # production over a wide date range (1000 Tutelas + 1 each of the rest).
    tutelas_items = [_item(title=f"STL{i}-2024.pdf", online_path=f"path/stl{i}") for i in range(5)]
    otros_items = {
        "Laboral": [_item(title=f"AL{i}-2024.pdf", online_path=f"path/al{i}") for i in range(2)],
        "Civil": [_item(title=f"AC{i}-2024.pdf", online_path=f"path/ac{i}") for i in range(2)],
        "Penal": [_item(title=f"SP{i}-2024.pdf", online_path=f"path/sp{i}") for i in range(2)],
    }

    def _callback(request):
        body = json.loads(request.body)
        query = body["query"]
        start = int(re.search(r"start:\s*(\d+)", query).group(1))
        tipo_query = re.search(r'typeOfQuery: "(\w+)"', query).group(1)
        items = tutelas_items[start : start + 10] if tipo_query == "Tutelas" else (
            otros_items[tipo_query] if start == 0 else []
        )
        payload = {"data": {"getSearchResult": {"searchResults": items}}}
        return (200, {"Content-Type": "application/json"}, json.dumps(payload))

    responses.add_callback(responses.POST, _URL, callback=_callback, content_type="application/json")

    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01", limit=3)

    count_by_bucket: dict[str, int] = {}
    for d in docs:
        bucket = d.save_path.split("/")[1]
        count_by_bucket[bucket] = count_by_bucket.get(bucket, 0) + 1

    assert count_by_bucket["SCT"] == 3  # tope de 3 alcanzado (había 5 disponibles)
    assert count_by_bucket["SCL"] == 2  # los 2 disponibles, no se queda en 1
    assert count_by_bucket["SCC"] == 2
    assert count_by_bucket["SCP"] == 2


@responses.activate
def test_scrap_excludes_items_older_than_fini():
    responses.add_callback(
        responses.POST,
        _URL,
        callback=_callback_factory(item_fecha="2020-01-01T00:00:00Z"),
        content_type="application/json",
    )

    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    assert docs == []
    # cada uno de los 4 tipos debe detenerse tras su primera petición (un item más
    # viejo que fini dispara `stop=True` antes de llegar a pedir "start=10")
    assert len(responses.calls) == 4


@responses.activate
def test_scrap_derives_tipo_from_auto_sentencia():
    # typeOfDocument is always null in the real API response, so tipo comes
    # from autoSentencia ("AUTO"/"SENTENCIA") instead, capitalized; when both
    # autoSentencia AND the title's own code prefix are unreadable, it falls
    # back to "Desconocido" (title "25632(...)" starts with a digit, not S/A).
    def _callback(request):
        body = json.loads(request.body)
        query = body["query"]
        start = int(re.search(r"start:\s*(\d+)", query).group(1))
        tipo_query = re.search(r'typeOfQuery: "(\w+)"', query).group(1)
        if start != 0:
            return (200, {}, json.dumps({"data": {"getSearchResult": {"searchResults": []}}}))
        auto_sentencia = {"Tutelas": "AUTO", "Laboral": "SENTENCIA", "Civil": None}.get(tipo_query, "SENTENCIA")
        title = "25632(27-01-10)EDITADA.doc" if tipo_query == "Civil" else _item()["title"]
        payload = {"data": {"getSearchResult": {"searchResults": [_item(title=title, auto_sentencia=auto_sentencia)]}}}
        return (200, {"Content-Type": "application/json"}, json.dumps(payload))

    responses.add_callback(responses.POST, _URL, callback=_callback, content_type="application/json")

    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    tipo_by_source_tipo = {d.save_path.split("/")[1]: d.tipo for d in docs}
    assert tipo_by_source_tipo["SCT"] == "Auto"  # Tutelas -> AUTO
    assert tipo_by_source_tipo["SCL"] == "Sentencia"  # Laboral -> SENTENCIA
    assert tipo_by_source_tipo["SCC"] == "Desconocido"  # Civil -> null, y el título no empieza en S/A


@responses.activate
def test_scrap_infers_tipo_from_titulo_when_auto_sentencia_is_missing():
    # Real-world example: autoSentencia comes back null, but the document's own
    # code makes the type unambiguous — "S..." is always a Sentencia, "A..."
    # is always an Auto, regardless of sala (SP, STC, AC, ATC, AHC, etc.).
    titles_by_tipo_query = {
        "Civil": "AC2794-2026 [2024-00858-00].pdf",
        "Laboral": "AL10187-2026.docx",
        "Penal": "SP592-2022(50621)EDITADA.docx",
        "Tutelas": "STC9010-2026.docx",
    }

    def _callback(request):
        body = json.loads(request.body)
        query = body["query"]
        start = int(re.search(r"start:\s*(\d+)", query).group(1))
        if start != 0:
            return (200, {}, json.dumps({"data": {"getSearchResult": {"searchResults": []}}}))
        tipo_query = re.search(r'typeOfQuery: "(\w+)"', query).group(1)
        payload = {
            "data": {
                "getSearchResult": {
                    "searchResults": [_item(title=titles_by_tipo_query[tipo_query], auto_sentencia=None)]
                }
            }
        }
        return (200, {"Content-Type": "application/json"}, json.dumps(payload))

    responses.add_callback(responses.POST, _URL, callback=_callback, content_type="application/json")

    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    tipo_by_source_tipo = {d.save_path.split("/")[1]: d.tipo for d in docs}
    assert tipo_by_source_tipo["SCC"] == "Auto"  # AC... -> Auto
    assert tipo_by_source_tipo["SCL"] == "Auto"  # AL... -> Auto
    assert tipo_by_source_tipo["SCP"] == "Sentencia"  # SP... -> Sentencia
    assert tipo_by_source_tipo["SCT"] == "Sentencia"  # STC... -> Sentencia


@responses.activate
def test_scrap_infers_concepto_from_cp_prefix():
    # Real-world example: "CP098-2026(68539)" is a Concepto de extradición
    # issued by the Sala de Casación Penal — confirmed by downloading a real
    # one, whose own first page reads "La Sala procede a emitir concepto...".
    # autoSentencia is null for these, same as Auto/Sentencia when missing.
    def _callback(request):
        body = json.loads(request.body)
        start = int(re.search(r"start:\s*(\d+)", body["query"]).group(1))
        tipo_query = re.search(r'typeOfQuery: "(\w+)"', body["query"]).group(1)
        if start != 0 or tipo_query != "Penal":
            return (200, {}, json.dumps({"data": {"getSearchResult": {"searchResults": []}}}))
        payload = {
            "data": {
                "getSearchResult": {
                    "searchResults": [_item(title="CP098-2026(68539).docx", auto_sentencia=None)]
                }
            }
        }
        return (200, {"Content-Type": "application/json"}, json.dumps(payload))

    responses.add_callback(responses.POST, _URL, callback=_callback, content_type="application/json")

    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    [doc] = [d for d in docs if d.save_path.split("/")[1] == "SCP"]
    assert doc.tipo == "Concepto"
    assert doc.title == "CP098-2026(68539)"


@responses.activate
def test_scrap_derives_especialidad_from_online_path():
    # Tutela wins over the internal sala segment (e.g. ".../TUTELAS/PENAL/...")
    # since that segment only names who resolved the tutela, not its nature.
    # Note: since the Tutelas item is resolved by Sala Penal, it now shares its
    # storage bucket (SCP) with the real "Penal" query item (see _bucket_real) —
    # so results are looked up by their unique online_path, not by bucket.
    paths_by_tipo_query = {
        "Civil": "/var/www/html/Index/CIVIL/2026/Dr. X/Autos/AC1-2026.pdf",
        "Laboral": "/var/www/html/Index/LABORAL/PERMANENTE/2026/Dr. Y/Autos/AL1-2026.docx",
        "Penal": "/var/www/html/Index/PENAL/2026/CP1-2026.docx",
        "Tutelas": "/var/www/html/Index/TUTELAS/PENAL/2026/Reservadas/STP1-2026.docx",
    }
    # Distinct titles are required: the Tutelas item is resolved by Sala Penal
    # and so shares its storage bucket with the real "Penal" item — if they
    # also shared the same code+date, the docx/pdf dedup would (correctly)
    # collapse them into one, hiding the real Penal document from this test.
    titles_by_tipo_query = {
        "Civil": "AC1-2026.pdf",
        "Laboral": "AL1-2026.docx",
        "Penal": "SP1-2026.docx",
        "Tutelas": "STP1-2026.docx",
    }

    def _callback(request):
        body = json.loads(request.body)
        query = body["query"]
        start = int(re.search(r"start:\s*(\d+)", query).group(1))
        if start != 0:
            return (200, {}, json.dumps({"data": {"getSearchResult": {"searchResults": []}}}))
        tipo_query = re.search(r'typeOfQuery: "(\w+)"', query).group(1)
        payload = {
            "data": {
                "getSearchResult": {
                    "searchResults": [
                        _item(title=titles_by_tipo_query[tipo_query], online_path=paths_by_tipo_query[tipo_query])
                    ]
                }
            }
        }
        return (200, {"Content-Type": "application/json"}, json.dumps(payload))

    responses.add_callback(responses.POST, _URL, callback=_callback, content_type="application/json")

    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    especialidad_by_path = {d.link["body"]["path"]: d.especialidad for d in docs}
    assert especialidad_by_path[paths_by_tipo_query["Civil"]] == "Civil"
    assert especialidad_by_path[paths_by_tipo_query["Laboral"]] == "Laboral"
    assert especialidad_by_path[paths_by_tipo_query["Penal"]] == "Penal"
    assert especialidad_by_path[paths_by_tipo_query["Tutelas"]] == "Tutela"  # not Penal, despite same sala


@responses.activate
def test_scrap_derives_seccion_as_the_actual_sala_de_casacion_that_decided_it():
    # Unlike especialidad, a tutela does NOT get its own bucket here — seccion
    # names whichever real Sala de Casación resolved it (the segment right
    # after "TUTELAS/"), since "Tutela" alone isn't an actual sala.
    paths_by_tipo_query = {
        "Civil": "/var/www/html/Index/CIVIL/2026/Dr. X/Autos/AC1-2026.pdf",
        "Laboral": "/var/www/html/Index/LABORAL/PERMANENTE/2026/Dr. Y/Autos/AL1-2026.docx",
        "Penal": "/var/www/html/Index/PENAL/2026/CP1-2026.docx",
        "Tutelas": "/var/www/html/Index/TUTELAS/PENAL/2026/Reservadas/STP1-2026.docx",
    }
    # Distinct titles are required: the Tutelas item is resolved by Sala Penal
    # and so shares its storage bucket with the real "Penal" item — if they
    # also shared the same code+date, the docx/pdf dedup would (correctly)
    # collapse them into one, hiding the real Penal document from this test.
    titles_by_tipo_query = {
        "Civil": "AC1-2026.pdf",
        "Laboral": "AL1-2026.docx",
        "Penal": "SP1-2026.docx",
        "Tutelas": "STP1-2026.docx",
    }

    def _callback(request):
        body = json.loads(request.body)
        query = body["query"]
        start = int(re.search(r"start:\s*(\d+)", query).group(1))
        if start != 0:
            return (200, {}, json.dumps({"data": {"getSearchResult": {"searchResults": []}}}))
        tipo_query = re.search(r'typeOfQuery: "(\w+)"', query).group(1)
        payload = {
            "data": {
                "getSearchResult": {
                    "searchResults": [
                        _item(title=titles_by_tipo_query[tipo_query], online_path=paths_by_tipo_query[tipo_query])
                    ]
                }
            }
        }
        return (200, {"Content-Type": "application/json"}, json.dumps(payload))

    responses.add_callback(responses.POST, _URL, callback=_callback, content_type="application/json")

    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    seccion_by_path = {d.link["body"]["path"]: d.seccion for d in docs}
    assert seccion_by_path[paths_by_tipo_query["Civil"]] == "Sala de Casación Civil"
    assert seccion_by_path[paths_by_tipo_query["Laboral"]] == "Sala de Casación Laboral"
    assert seccion_by_path[paths_by_tipo_query["Penal"]] == "Sala de Casación Penal"
    # /TUTELAS/PENAL/... -> resolved by the Sala Penal, not a "Tutela" sala
    assert seccion_by_path[paths_by_tipo_query["Tutelas"]] == "Sala de Casación Penal"

    # And the tutela's own storage bucket must match that real sala (SCP), not
    # the generic "SCT" search bucket — see _bucket_real.
    bucket_by_path = {d.link["body"]["path"]: d.save_path.split("/")[1] for d in docs}
    assert bucket_by_path[paths_by_tipo_query["Tutelas"]] == "SCP"
    assert bucket_by_path[paths_by_tipo_query["Penal"]] == "SCP"


@responses.activate
def test_scrap_strips_trailing_junk_from_the_code():
    # The document's own code is always the start of the title — plain-word
    # junk trailing it (" - RESERVADO", "EDITADA") is noise from the source
    # and gets dropped, but NOT a bracketed/parenthesized reference number
    # right after the code ("(50621)", "[2024-00858-00]") — that's part of
    # the code itself and must be kept.
    titles = {
        "Civil": "ATP346-2021 - RESERVADO.docx",
        "Laboral": "AC2794-2026 [2024-00858-00].pdf",
        "Penal": "SP592-2022(50621)EDITADA.docx",
        "Tutelas": "STL5177-2026.pdf",
    }

    def _callback(request):
        body = json.loads(request.body)
        start = int(re.search(r"start:\s*(\d+)", body["query"]).group(1))
        if start != 0:
            return (200, {}, json.dumps({"data": {"getSearchResult": {"searchResults": []}}}))
        tipo_query = re.search(r'typeOfQuery: "(\w+)"', body["query"]).group(1)
        payload = {"data": {"getSearchResult": {"searchResults": [_item(title=titles[tipo_query])]}}}
        return (200, {"Content-Type": "application/json"}, json.dumps(payload))

    responses.add_callback(responses.POST, _URL, callback=_callback, content_type="application/json")

    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    title_by_bucket = {d.save_path.split("/")[1]: d.title for d in docs}
    assert title_by_bucket["SCC"] == "ATP346-2021"
    assert title_by_bucket["SCL"] == "AC2794-2026 [2024-00858-00]"
    assert title_by_bucket["SCP"] == "SP592-2022(50621)"
    assert title_by_bucket["SCT"] == "STL5177-2026"


@responses.activate
def test_scrap_falls_back_to_raw_title_when_the_code_cannot_be_identified():
    # Real-world garbage titles ("doc", "(3)") that don't start with a
    # recognizable code still get the "<relleno>_<año>" shape, even though the
    # middle part isn't the real code yet — it's flagged via title_unverified
    # so the worker checks the file's first page later
    # (see resolve_unverified_document).
    responses.add_callback(
        responses.POST,
        _URL,
        callback=lambda request: (
            200,
            {"Content-Type": "application/json"},
            json.dumps(
                {"data": {"getSearchResult": {"searchResults": [_item(title="doc.docx")]}}}
                if int(re.search(r"start:\s*(\d+)", json.loads(request.body)["query"]).group(1)) == 0
                else {"data": {"getSearchResult": {"searchResults": []}}}
            ),
        ),
        content_type="application/json",
    )

    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    title_by_bucket = {d.save_path.split("/")[1]: d.title for d in docs}
    assert title_by_bucket["SCC"] == "doc_2024"
    unverified_by_bucket = {d.save_path.split("/")[1]: d.title_unverified for d in docs}
    assert unverified_by_bucket["SCC"] is True


@responses.activate
def test_scrap_does_not_flag_title_unverified_when_the_code_is_identified():
    responses.add_callback(responses.POST, _URL, callback=_callback_factory(), content_type="application/json")

    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    assert all(not d.title_unverified for d in docs)


def test_resolve_unverified_document_recovers_the_title_and_tipo_from_the_files_own_text(monkeypatch):
    # Real-world example: nombre_providencia said "doc", but the file's first
    # page actually names the real providencia — "ATP1800-2019" — an Auto (A).
    monkeypatch.setattr(csj_module, "_extraer_texto_primera_pagina", lambda *_a, **_k: "Radicado No. ATP1800-2019")

    class _Doc:
        title = "doc_2019"
        tipo = "Desconocido"

    doc = _Doc()
    scraper = ScrapCorteSuprema()
    scraper.resolve_unverified_document(doc, Path("fake.docx"), "application/vnd.openxmlformats")

    assert doc.title == "ATP1800-2019"
    assert doc.tipo == "Auto"


def test_resolve_unverified_document_leaves_doc_untouched_when_no_code_is_found(monkeypatch):
    monkeypatch.setattr(csj_module, "_extraer_texto_primera_pagina", lambda *_a, **_k: "sin ningún código aquí")

    class _Doc:
        title = "doc_2019"
        tipo = "Desconocido"

    doc = _Doc()
    scraper = ScrapCorteSuprema()
    scraper.resolve_unverified_document(doc, Path("fake.docx"), "application/vnd.openxmlformats")

    assert doc.title == "doc_2019"
    assert doc.tipo == "Desconocido"


def test_resolve_unverified_document_is_defensive_about_read_failures(monkeypatch, caplog):
    def _raise(*_a, **_k):
        raise RuntimeError("archivo corrupto")

    monkeypatch.setattr(csj_module, "_extraer_texto_primera_pagina", _raise)

    class _Doc:
        title = "doc_2019"
        tipo = "Desconocido"

    doc = _Doc()
    scraper = ScrapCorteSuprema()
    with caplog.at_level("WARNING", logger="core.scrapers.families.corte_suprema"):
        scraper.resolve_unverified_document(doc, Path("fake.docx"), "application/vnd.openxmlformats")  # no debe lanzar

    assert doc.title == "doc_2019"
    # Regression test: this used to be a bare print(), invisible to server logs —
    # now it must go through the logging module like the rest of the project.
    assert any("No se pudo leer la primera página" in r.message for r in caplog.records)


@responses.activate
def test_scrap_deduplicates_docx_and_pdf_of_the_same_providencia_preferring_pdf():
    # Real-world example: CSJ lists "STL4467-2026" twice in the same Tutelas
    # search — once as .docx, once as .pdf. That's not a later republication,
    # just two formats of the same submission, so only one document (the
    # pdf) should survive, not two.
    def _callback(request):
        body = json.loads(request.body)
        start = int(re.search(r"start:\s*(\d+)", body["query"]).group(1))
        tipo_query = re.search(r'typeOfQuery: "(\w+)"', body["query"]).group(1)
        if start != 0 or tipo_query != "Tutelas":
            return (200, {}, json.dumps({"data": {"getSearchResult": {"searchResults": []}}}))
        payload = {
            "data": {
                "getSearchResult": {
                    "searchResults": [
                        _item(title="STL4467-2026.docx", online_path="path/docx"),
                        _item(title="STL4467-2026.pdf", online_path="path/pdf"),
                    ]
                }
            }
        }
        return (200, {"Content-Type": "application/json"}, json.dumps(payload))

    responses.add_callback(responses.POST, _URL, callback=_callback, content_type="application/json")

    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    tutelas_docs = [d for d in docs if d.save_path.split("/")[1] == "SCT"]
    assert len(tutelas_docs) == 1
    assert tutelas_docs[0].title == "STL4467-2026"
    assert tutelas_docs[0].link["body"] == {"path": "path/pdf"}


@responses.activate
def test_scrap_deduplicates_pdf_and_docx_regardless_of_which_is_seen_first():
    def _callback(request):
        body = json.loads(request.body)
        start = int(re.search(r"start:\s*(\d+)", body["query"]).group(1))
        tipo_query = re.search(r'typeOfQuery: "(\w+)"', body["query"]).group(1)
        if start != 0 or tipo_query != "Tutelas":
            return (200, {}, json.dumps({"data": {"getSearchResult": {"searchResults": []}}}))
        payload = {
            "data": {
                "getSearchResult": {
                    "searchResults": [
                        _item(title="STL4467-2026.pdf", online_path="path/pdf"),
                        _item(title="STL4467-2026.docx", online_path="path/docx"),
                    ]
                }
            }
        }
        return (200, {"Content-Type": "application/json"}, json.dumps(payload))

    responses.add_callback(responses.POST, _URL, callback=_callback, content_type="application/json")

    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    tutelas_docs = [d for d in docs if d.save_path.split("/")[1] == "SCT"]
    assert len(tutelas_docs) == 1
    assert tutelas_docs[0].link["body"] == {"path": "path/pdf"}


def test_corte_suprema_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["corte_suprema"] is ScrapCorteSuprema


@responses.activate
def test_scrap_skips_malformed_item_without_aborting_the_rest():
    # A title with no "." separator makes `title.split(".")[-2]` raise
    # IndexError; that must only skip this one item, not abort the whole
    # tipo (and lose every other valid item on the page).
    def _callback(request):
        body = json.loads(request.body)
        start = int(re.search(r"start:\s*(\d+)", body["query"]).group(1))
        if start == 0:
            malformed = _item(title="Sin puntos aqui")
            valid = _item(title="SC9999-2024.pdf")
            payload = {"data": {"getSearchResult": {"searchResults": [malformed, valid]}}}
        else:
            payload = {"data": {"getSearchResult": {"searchResults": []}}}
        return (200, {"Content-Type": "application/json"}, json.dumps(payload))

    responses.add_callback(responses.POST, _URL, callback=_callback, content_type="application/json")

    progress_messages = []
    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01", on_progress=progress_messages.append)

    assert len(docs) == 4  # el item malformado se salta, uno válido por cada uno de los 4 tipos
    assert {d.title for d in docs} == {"SC9999-2024"}
    # Regression test: this used to be a bare print(), invisible to the worker —
    # now it must be reported via on_progress so worker/tasks.py can surface it
    # as a RunError instead of silently discarding it.
    assert any("Error" in m and "campo inesperado" in m for m in progress_messages)


@responses.activate
def test_scrap_reports_a_server_error_via_on_progress_instead_of_silently_swallowing_it():
    """Regression test: a 500/502/503/504 mid-pagination used to just print() and
    quietly stop that tipo, so the worker had no way to know a whole day's worth
    of documents for that tipo might be missing. It must now report through
    on_progress, keeping the partial results already collected."""

    def _callback(request):
        body = json.loads(request.body)
        start = int(re.search(r"start:\s*(\d+)", body["query"]).group(1))
        if start == 0:
            payload = {"data": {"getSearchResult": {"searchResults": [_item()]}}}
            return (200, {"Content-Type": "application/json"}, json.dumps(payload))
        return (503, {"Content-Type": "application/json"}, "Service Unavailable")

    responses.add_callback(responses.POST, _URL, callback=_callback, content_type="application/json")

    progress_messages = []
    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01", on_progress=progress_messages.append)

    # The first page's document is still kept even though the second page failed.
    assert len(docs) == 4
    error_messages = [m for m in progress_messages if "Error" in m]
    assert len(error_messages) == 4  # una por cada uno de los 4 tipos
    assert any("503" in m for m in error_messages)


def test_corte_suprema_does_not_check_for_republication():
    # CSJ's download is a POST to a shared endpoint (no direct file URL), so there's
    # nothing cheap to HEAD — republication checking is out of scope for this family.
    assert ScrapCorteSuprema().checks_for_republication is False
