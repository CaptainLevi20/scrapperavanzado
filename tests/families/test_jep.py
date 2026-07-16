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
    assert doc.title == "1501296-69.2023.0.00.0001"
    assert doc.tipo == "Auto"
    assert doc.seccion == "S - Sala de Amnistía o Indulto"
    assert doc.seccion_en_carpeta is False
    assert doc.f_public == "2024-08-01"
    assert doc.f_providencia == "2024-07-06"
    assert doc.link == {
        "url": "https://relatoria.jep.gov.co/documentos/providencias/1/1/Auto_SRVR-003_06-julio-2024.pdf",
        "method": "GET",
    }
    assert doc.save_path == "JEP/2024-08-01/Auto/1501296-69.2023.0.00.0001-1(extension)"
    assert doc.convert_to is None


@responses.activate
def test_scrap_falls_back_to_radicado_when_expediente_missing():
    """El expediente puede venir vacío en la fuente — en ese caso el radicado del
    documento (siempre presente) sirve de respaldo tanto para el título como para
    el nombre de archivo."""
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(1, radicado_documento="SRVR-003", expediente=None)]),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert docs[0].title == "SRVR-003"
    assert docs[0].save_path == "JEP/2024-08-01/Auto/SRVR-003-1(extension)"


@responses.activate
def test_scrap_filters_by_publication_date_not_providencia_date():
    """The user explicitly asked for JEP runs to be filtered by fecha de publicación
    rather than fecha de providencia. Both hits below have a providencia date
    (fecha_documento) OUTSIDE the requested range — only the one whose publication
    date (fecha_publicacion) falls inside it should survive."""
    responses.add(
        responses.POST, _URL,
        json=_response([
            _hit(1, expediente="EN-RANGO-POR-PUBLICACION", fecha_documento="2024-01-05", fecha_publicacion="2024-06-15T05:00:00.000000Z"),
            _hit(2, expediente="FUERA-DE-RANGO", fecha_documento="2024-06-20", fecha_publicacion="2024-01-05T05:00:00.000000Z"),
        ]),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-06-01", ffin="2024-06-30")

    assert len(docs) == 1
    assert docs[0].title == "EN-RANGO-POR-PUBLICACION"


def test_filters_by_publication_date_is_declared_on_the_scraper():
    assert ScrapJEP.filters_by_publication_date is True


@responses.activate
def test_scrap_normalizes_hipervinculo_with_and_without_leading_slash():
    responses.add(
        responses.POST, _URL,
        json=_response([
            _hit(1, expediente="CON-SLASH", hipervinculo="/documentos/providencias/1/1/a.pdf"),
            _hit(2, expediente="SIN-SLASH", hipervinculo="documentos/providencias/1/1/b.pdf"),
        ]),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    links = {doc.title: doc.link["url"] for doc in docs}
    assert links["CON-SLASH"] == "https://relatoria.jep.gov.co/documentos/providencias/1/1/a.pdf"
    assert links["SIN-SLASH"] == "https://relatoria.jep.gov.co/documentos/providencias/1/1/b.pdf"


@responses.activate
def test_scrap_paginates_until_total_exhausted(monkeypatch):
    monkeypatch.setattr(jep_module, "_PER_PAGE", 2)
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(1, expediente="UNO"), _hit(2, expediente="DOS")], total=3),
        match=[_body_matcher("2024", page=1, per_page=2)],
        status=200,
    )
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(3, expediente="TRES")], total=3),
        match=[_body_matcher("2024", page=2, per_page=2)],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert {doc.title for doc in docs} == {"UNO", "DOS", "TRES"}


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
        json=_response([_hit(1, fecha_documento=None), _hit(2, expediente="VALIDO")]),
        match=[_body_matcher("2024")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1
    assert docs[0].title == "VALIDO"


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
        json=_response([_hit(1, expediente="DE-2025", fecha_publicacion="2025-12-20T05:00:00.000000Z")]),
        match=[_body_matcher("2025")],
        status=200,
    )
    responses.add(
        responses.POST, _URL,
        json=_response([_hit(2, expediente="DE-2026", fecha_publicacion="2026-01-10T05:00:00.000000Z")]),
        match=[_body_matcher("2026")],
        status=200,
    )

    scraper = ScrapJEP()
    docs = scraper.scrap(fini="2025-12-15", ffin="2026-01-15")

    assert {doc.title for doc in docs} == {"DE-2025", "DE-2026"}


def test_jep_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["jep"] is ScrapJEP
