import responses
from responses import matchers

import core.scrapers.families.jep as jep_module
from core.scrapers.families.jep import ScrapJEP
from core.scrapers.registry import FAMILY_REGISTRY

_URL = "https://relatoria.jep.gov.co/searchadv"


def _hit(
    providencia_id,
    radicado_documento="SRVR-003",
    expediente="1501296-69.2023.0.00.0001",
    nombre_providencia="Auto_SRVR-003_06-julio-2024",
    tipo_documento="Auto",
    sala_seccion="S - Sala de Amnistía o Indulto",
    fecha_documento="2024-07-06",
    fecha_publicacion="2024-08-01T05:00:00.000000Z",
    hipervinculo="documentos/providencias/1/1/Auto_SRVR-003_06-julio-2024.pdf",
):
    return {
        "_source": {
            "providencia_id": providencia_id,
            "radicado_documento": radicado_documento,
            "expediente": expediente,
            "nombre_providencia": nombre_providencia,
            "tipo_documento": tipo_documento,
            "sala_seccion": sala_seccion,
            "fecha_documento": fecha_documento,
            "fecha_publicacion": fecha_publicacion,
            "hipervinculo": hipervinculo,
        }
    }


def _response(hits, total=None):
    return {"reponse": {"hits": {"total": {"value": total if total is not None else len(hits)}, "hits": hits}}}


def _body_matcher(anio, page=1, per_page=200):
    return matchers.json_params_matcher(
        {
            "alguna_palabra": "",
            "todas_palabras": "",
            "frase_exacta": "",
            "ninguna_palabra": "",
            "anio": anio,
            "sala_seccion": "",
            "tipo_documento": "",
            "page": page,
            "per_page": per_page,
        }
    )


@responses.activate
def test_scrap_maps_fields_correctly():
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(1)]),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "SRVR-003_2024"
    assert doc.tipo == "Auto"
    assert doc.seccion == "S - Sala de Amnistía o Indulto"
    assert doc.seccion_en_carpeta is False
    assert doc.f_public == "2024-08-01"
    assert doc.f_providencia == "2024-07-06"
    assert doc.link == {
        "url": "https://relatoria.jep.gov.co/documentos/providencias/1/1/Auto_SRVR-003_06-julio-2024.pdf",
        "method": "GET",
    }
    assert doc.save_path == "JEP/2024-08-01/Auto/SRVR-003_2024_1(extension)"


@responses.activate
def test_scrap_falls_back_to_expediente_when_radicado_missing():
    """El radicado puede venir vacío en la fuente — en ese caso el número de
    expediente del proceso judicial sirve de respaldo tanto para el título como
    para el nombre de archivo."""
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(1, radicado_documento=None, expediente="1501296-69.2023.0.00.0001", nombre_providencia=None)]),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert docs[0].title == "1501296-69.2023.0.00.0001_2024"
    assert docs[0].save_path == "JEP/2024-08-01/Auto/1501296-69.2023.0.00.0001_2024_1(extension)"


@responses.activate
def test_scrap_recovers_a_real_code_from_nombre_providencia_when_radicado_is_a_bare_number():
    """radicado_documento is sometimes just the raw case number instead of a real
    document code (e.g. "1842") — nombre_providencia embeds the actual code
    ("SDSJ-1842") alongside its type and date, so that's used instead."""
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(
            1,
            radicado_documento="1842",
            nombre_providencia="Resolución_SDSJ-1842_2-marzo-2026",
            tipo_documento="Resolución",
            fecha_documento="2026-03-02",
            fecha_publicacion="2026-03-05T05:00:00.000000Z",
        )]),
        match=[_body_matcher("2026")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert docs[0].title == "R_SDSJ-1842_2026"
    assert docs[0].save_path == "JEP/2026-03-05/Resolución/R_SDSJ-1842_2026_1(extension)"


@responses.activate
def test_scrap_keeps_bare_number_when_nombre_providencia_has_no_usable_code():
    """If nombre_providencia doesn't yield anything better (no letters, e.g. for
    a boletín), the original bare number is kept rather than making it worse —
    it still gets its year appended and dashes normalized like every record."""
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(
            1,
            radicado_documento="03",
            nombre_providencia="Boletín Jurisprudencial 2024-03",
            tipo_documento="Boletín",
            fecha_documento="2024-03-01",
            fecha_publicacion="2024-03-01T05:00:00.000000Z",
        )]),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert docs[0].title == "03_2024"


@responses.activate
def test_scrap_does_not_duplicate_a_year_already_present_in_the_code():
    """When nombre_providencia's code segment already ends in the providencia's
    own year (e.g. "SAI-AOI-R-DVL-008-2026"), it must not get a second year
    appended — only the dash right before the year becomes an underscore, the
    rest of the code's own dashes are left alone."""
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(
            1,
            radicado_documento="SAI-AOI-R-DVL-008-2026",
            nombre_providencia="Resolución_SAI-AOI-R-DVL-008-2026_15-enero-2026",
            tipo_documento="Resolución",
            fecha_documento="2026-01-15",
            fecha_publicacion="2026-01-16T05:00:00.000000Z",
        )]),
        match=[_body_matcher("2026")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert docs[0].title == "R_SAI-AOI-R-DVL-008_2026"


@responses.activate
def test_scrap_does_not_mistake_a_case_number_ending_in_4_digits_for_a_year():
    """A code recovered from nombre_providencia can coincidentally end in 4
    digits that are part of the case number, not a year (e.g. "SDSJ-1139") —
    that must still get the real year appended, not be mistaken as already
    having one."""
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(
            1,
            radicado_documento="1139",
            nombre_providencia="Resolución_SDSJ-1139_08-abril-2026",
            tipo_documento="Resolución",
            fecha_documento="2026-04-08",
            fecha_publicacion="2026-04-09T05:00:00.000000Z",
        )]),
        match=[_body_matcher("2026")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert docs[0].title == "R_SDSJ-1139_2026"


@responses.activate
def test_scrap_does_not_mistake_a_case_number_in_the_2000s_for_the_real_year():
    """JEP's own SDSJ sequence has passed 2000 (e.g. "SDSJ-2015"), so a code
    ending in a 2000s-looking number is not necessarily already the document's
    real year — compare against the actual providencia year, not a generic
    "-20XX" pattern, or the true year never gets appended for these."""
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(
            1,
            radicado_documento="1500000-00.2023.0.00.0001",
            nombre_providencia="Resolución_SDSJ-2015_16-junio-2025",
            tipo_documento="Resolución",
            fecha_documento="2025-06-16",
            fecha_publicacion="2025-06-20T05:00:00.000000Z",
        )]),
        match=[_body_matcher("2025")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2025-01-01", ffin="2025-12-31")

    assert docs[0].title == "R_SDSJ-2015_2025"


@responses.activate
def test_scrap_prefixes_title_by_tipo_documento():
    """Resolución -> "R_", Sentencia -> "S_", Salvamento de Voto de Auto -> "SV_",
    Aclaración de Voto (de Auto o de Resolución) -> "AV_". Auto (and anything
    else unlisted) gets no prefix."""
    hits = [
        _hit(1, radicado_documento="SDSJ-08", nombre_providencia="Resolución_SDSJ-08_06-enero-2026", tipo_documento="Resolución"),
        _hit(2, radicado_documento="C-1234", nombre_providencia="Sentencia_C-1234_06-enero-2026", tipo_documento="Sentencia"),
        _hit(3, radicado_documento="TP-SA-630", nombre_providencia="Auto_TP-SA-630_06-enero-2026", tipo_documento="Salvamento de Voto de Auto"),
        _hit(4, radicado_documento="TP-SA-2245", nombre_providencia="Auto_TP-SA-2245_06-enero-2026", tipo_documento="Aclaración de Voto de Auto"),
        _hit(5, radicado_documento="SRVR-003", nombre_providencia="Auto_SRVR-003_06-enero-2026", tipo_documento="Auto"),
    ]
    responses.add(
        responses.POST, _URL,
        json=_response(hits),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 5
    titulos = {doc.title for doc in docs}
    assert titulos == {
        "R_SDSJ-08_2024",
        "S_C-1234_2024",
        "SV_TP-SA-630_2024",
        "AV_TP-SA-2245_2024",
        "SRVR-003_2024",
    }


@responses.activate
def test_scrap_recovers_the_real_code_from_a_compound_voto_radicado():
    """radicado_documento for Aclaración/Salvamento de Voto de Resolución can come
    back as the whole filing name — magistrado's name and the tipo word mixed in
    with the radicado — instead of just the code. Real example from the JEP API:
    "AV_Dra-Sandra-Castro_Resolución_SDSJ-RPP-1881"."""
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(
            1,
            radicado_documento="AV_Dra-Sandra-Castro_Resolución_SDSJ-RPP-1881",
            nombre_providencia="AV_Dra-Sandra-Castro_Resolución_SDSJ-RPP-1881_04-junio-2026",
            tipo_documento="Aclaración de Voto de Resolución",
            fecha_documento="2026-06-04",
            fecha_publicacion="2026-06-18T05:00:00.000000Z",
        )]),
        match=[_body_matcher("2026")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert docs[0].title == "AV_SDSJ-RPP-1881_2026"


@responses.activate
def test_scrap_recovers_the_real_code_from_a_compound_salvamento_de_voto_radicado():
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(
            1,
            radicado_documento="SV_Dr-Juan-Cantillo_Resolución_SAI-SUBB-AOI-D-036-2025",
            nombre_providencia="SV_Dr-Juan-Cantillo_Resolución_SAI-SUBB-AOI-D-036-2025_23-diciembre-2025",
            tipo_documento="Salvamento de Voto de Resolución",
            fecha_documento="2025-12-23",
            fecha_publicacion="2026-01-05T05:00:00.000000Z",
        )]),
        match=[_body_matcher("2026")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert docs[0].title == "SV_SAI-SUBB-AOI-D-036_2025"


@responses.activate
def test_scrap_prefers_voto_marker_in_nombre_providencia_over_tipo_documento():
    """A providencia's Aclaración/Salvamento de Voto is sometimes filed as its
    own separate document under the SAME radicado_documento as the base Auto/
    Sentencia, with tipo_documento left as plain "Auto"/"Sentencia" — only
    nombre_providencia's own "AV_"/"SV_" lead-in (with either "_" or "-" as the
    separator) reveals it's actually the vote annotation, not the base ruling.
    Real example from the JEP API: two providencias both radicado_documento=
    "TP-SA-2241"/tipo_documento="Auto", one of them nombre_providencia=
    "AV_Dra-Sandra-Gamboa_Auto_TP-SA-2241_29-abril-2026" — without checking
    nombre_providencia, both would collide on the same title."""
    responses.add(
        responses.POST, _URL,
        json=_response([
            _hit(
                1,
                radicado_documento="TP-SA-2241",
                nombre_providencia="AV_Dra-Sandra-Gamboa_Auto_TP-SA-2241_29-abril-2026",
                tipo_documento="Auto",
                fecha_documento="2026-04-29",
            ),
            _hit(
                2,
                radicado_documento="TP-SA-2241",
                nombre_providencia="Auto_TP-SA-2241_29-abril-2026",
                tipo_documento="Auto",
                fecha_documento="2026-04-29",
            ),
        ]),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert {doc.title for doc in docs} == {"AV_TP-SA-2241_2026", "TP-SA-2241_2026"}
    tipos_por_titulo = {doc.title: doc.tipo for doc in docs}
    assert tipos_por_titulo["AV_TP-SA-2241_2026"] == "Aclaración de Voto de Auto"
    assert tipos_por_titulo["TP-SA-2241_2026"] == "Auto"


@responses.activate
def test_scrap_corrects_tipo_when_it_conflicts_with_the_voto_marker():
    """JEP's own tipo_documento can even disagree with nombre_providencia's own
    marker (real example: tipo_documento="Salvamento de Voto de Auto" but
    nombre_providencia starts with "AV_") — the marker wins, replacing the
    wrong qualifier rather than stacking both."""
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(
            1,
            radicado_documento="TP-SA-630",
            nombre_providencia="AV_Dra-Sandra-Gamboa_Auto_TP-SA-630_18-junio-2026",
            tipo_documento="Salvamento de Voto de Auto",
            fecha_documento="2026-06-18",
        )]),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert docs[0].tipo == "Aclaración de Voto de Auto"
    assert docs[0].title == "AV_TP-SA-630_2026"


@responses.activate
def test_scrap_filters_by_publication_date_not_providencia_date():
    """The user explicitly asked for JEP runs to be filtered by fecha de publicación
    rather than fecha de providencia. Both hits below have a providencia date
    (fecha_documento) OUTSIDE the requested range — only the one whose publication
    date (fecha_publicacion) falls inside it should survive."""
    responses.add(
        responses.POST, _URL,
        json=_response([
            _hit(1, radicado_documento="EN-RANGO-POR-PUBLICACION", fecha_documento="2024-01-05", fecha_publicacion="2024-06-15T05:00:00.000000Z"),
            _hit(2, radicado_documento="FUERA-DE-RANGO", fecha_documento="2024-06-20", fecha_publicacion="2024-01-05T05:00:00.000000Z"),
        ]),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-06-01", ffin="2024-06-30")

    assert len(docs) == 1
    assert docs[0].title == "EN-RANGO-POR-PUBLICACION_2024"


def test_filters_by_publication_date_is_declared_on_the_scraper():
    assert ScrapJEP.filters_by_publication_date is True


@responses.activate
def test_scrap_normalizes_hipervinculo_with_and_without_leading_slash():
    responses.add(
        responses.POST, _URL,
        json=_response([
            _hit(1, radicado_documento="CON-SLASH", hipervinculo="/documentos/providencias/1/1/a.pdf"),
            _hit(2, radicado_documento="SIN-SLASH", hipervinculo="documentos/providencias/1/1/b.pdf"),
        ]),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    links = {doc.title: doc.link["url"] for doc in docs}
    assert links["CON-SLASH_2024"] == "https://relatoria.jep.gov.co/documentos/providencias/1/1/a.pdf"
    assert links["SIN-SLASH_2024"] == "https://relatoria.jep.gov.co/documentos/providencias/1/1/b.pdf"


@responses.activate
def test_scrap_paginates_until_total_exhausted(monkeypatch):
    monkeypatch.setattr(jep_module, "_PER_PAGE", 2)
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(1, radicado_documento="UNO"), _hit(2, radicado_documento="DOS")], total=3),
        match=[_body_matcher("2024", page=1, per_page=2)],
        status=200,
    )
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(3, radicado_documento="TRES")], total=3),
        match=[_body_matcher("2024", page=2, per_page=2)],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert {doc.title for doc in docs} == {"UNO_2024", "DOS_2024", "TRES_2024"}


@responses.activate
def test_scrap_deduplicates_repeated_providencia_id():
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(1, radicado_documento="REPETIDO"), _hit(1, radicado_documento="REPETIDO")]),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1


@responses.activate
def test_scrap_falls_back_to_fecha_documento_when_fecha_publicacion_missing():
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(1, fecha_documento="2024-03-10", fecha_publicacion=None)]),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert docs[0].f_public == "2024-03-10"


@responses.activate
def test_scrap_skips_document_missing_fecha_documento():
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(1, fecha_documento=None), _hit(2, radicado_documento="VALIDO")]),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1
    assert docs[0].title == "VALIDO_2024"


def test_scrap_stops_early_when_stop_event_is_already_set():
    import threading

    stop_event = threading.Event()
    stop_event.set()

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31", stop_event=stop_event)

    assert docs == []


@responses.activate
def test_scrap_requests_each_year_in_a_multi_year_range():
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(1, radicado_documento="DE-25", fecha_publicacion="2025-12-20T05:00:00.000000Z")]),
        match=[_body_matcher("2025")],
        status=200,
    )
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(2, radicado_documento="DE-26", fecha_publicacion="2026-01-10T05:00:00.000000Z")]),
        match=[_body_matcher("2026")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2025-12-15", ffin="2026-01-15")

    assert {doc.title for doc in docs} == {"DE-25_2024", "DE-26_2024"}


def test_jep_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["jep"] is ScrapJEP


def test_normalizar_titulo_is_idempotent():
    """Regression guard: a data-backfill script once fed an already-normalized
    title back into _normalizar_titulo as if it were the raw radicado, and
    since the function wasn't idempotent, it silently double-appended the
    year (and, for "de Voto" records, doubled the prefix) across the entire
    JEP table. Running it twice on its own output must be a no-op."""
    from core.scrapers.families.jep import _normalizar_titulo

    cases = [
        ("SDSJ-1543", "Resolución_SDSJ-1543_08-mayo-2026", "2026", "Resolución"),
        ("TP-SA-2241", "AV_Dra-Sandra-Gamboa_Auto_TP-SA-2241_29-abril-2026", "2026", "Auto"),
        ("TP-SA-626", "SV-Dra-Sandra-Gamboa_Sentencia_TP-SA-626_11-junio-2026", "2026", "Sentencia"),
        ("SDSJ-2015", "Resolución_SDSJ-2015_16-junio-2025", "2026", "Resolución"),
        ("SRVR-003", "Auto_SRVR-003_06-julio-2024", "2024", "Auto"),
    ]
    for radicado, nombre_providencia, anio, tipo in cases:
        once = _normalizar_titulo(radicado, nombre_providencia, anio, tipo)
        twice = _normalizar_titulo(once, nombre_providencia, anio, tipo)
        assert twice == once, f"not idempotent for {radicado!r}: {once!r} -> {twice!r}"


def test_normalizar_tipo_is_idempotent():
    from core.scrapers.families.jep import _normalizar_tipo

    cases = [
        ("Auto", "AV_Dra-Sandra-Gamboa_Auto_TP-SA-2241_29-abril-2026"),
        ("Sentencia", "SV-Dra-Sandra-Gamboa_Sentencia_TP-SA-626_11-junio-2026"),
        ("Salvamento de Voto de Auto", "AV_Dra-Sandra-Gamboa_Auto_TP-SA-630_18-junio-2026"),
        ("Resolución", "Resolución_SDSJ-1543_08-mayo-2026"),
    ]
    for tipo, nombre_providencia in cases:
        once = _normalizar_tipo(tipo, nombre_providencia)
        twice = _normalizar_tipo(once, nombre_providencia)
        assert twice == once, f"not idempotent for {tipo!r}: {once!r} -> {twice!r}"
