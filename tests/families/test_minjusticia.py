import json

import requests
import responses

from core.scrapers.families.minjusticia import (
    ScrapMinJusticia,
    _extraer_items,
    _normalize_title,
)
from core.scrapers.registry import FAMILY_REGISTRY

_SITE_URL = "https://www.minjusticia.gov.co/normatividad-co"


def test_minjusticia_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["minjusticia"].__name__ == "ScrapMinJusticia"


def test_normalize_title_builds_canonical_code_for_decreto():
    assert _normalize_title("D", "254", "2025") == "D0254025"


def test_normalize_title_builds_canonical_code_for_resolucion():
    assert _normalize_title("R", "1510", "2026") == "R_MJ_1510_2026"


def test_normalize_title_keeps_circular_code_as_is_without_padding():
    assert _normalize_title("C", "CIR26-0000002", "2026") == "C_MJ_CIR26-0000002_2026"


def _sp_response(results, next_url=None):
    d = {"results": results}
    if next_url:
        d["__next"] = next_url
    return json.dumps({"d": d})


def _decreto_item(title, fecha_iso, pdf_name, descripcion="."):
    return {
        "Title": title,
        "MJDescripcion": descripcion,
        "MJFechaExpedicion": fecha_iso,
        "File": {
            "Name": pdf_name,
            "ServerRelativeUrl": f"/normatividad-co/Decretos/{pdf_name}",
        },
    }


def test_extraer_items_parses_decreto_and_builds_canonical_title():
    session = requests.Session()
    item = _decreto_item("0254 de 4 marzo", "2025-03-04T05:00:00Z", "DECRETO 0254 DEL 4 DE MARZO DE 2025.pdf")
    body = _sp_response([item])

    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, f"{_SITE_URL}/_api/web/lists/getbytitle('Decretos')/items", body=body)
        docs = _extraer_items(
            session, "Decretos", "Decreto", "D", "2025-01-01", "2025-12-31", "Ministerio de Justicia y del Derecho"
        )

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "D0254025"
    assert doc.title_unverified is False
    assert doc.tipo == "Decreto"
    assert doc.f_public == "2025-03-04"
    assert doc.f_providencia == "2025-03-04"
    assert doc.detalle is None  # "." se trata como ausente
    assert doc.link["url"] == "https://www.minjusticia.gov.co/normatividad-co/Decretos/DECRETO 0254 DEL 4 DE MARZO DE 2025.pdf"
    assert doc.save_path == "Ministerio de Justicia y del Derecho/2025-03-04/Decreto/D0254025(extension)"


def test_extraer_items_keeps_real_descripcion_when_present():
    session = requests.Session()
    item = _decreto_item(
        "0311 de 19 de marzo", "2025-03-19T05:00:00Z", "DECRETO 0311.pdf", descripcion="Por el cual se reglamenta X"
    )
    body = _sp_response([item])

    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, f"{_SITE_URL}/_api/web/lists/getbytitle('Decretos')/items", body=body)
        docs = _extraer_items(
            session, "Decretos", "Decreto", "D", "2025-01-01", "2025-12-31", "Ministerio de Justicia y del Derecho"
        )

    assert docs[0].detalle == "Por el cual se reglamenta X"


def test_extraer_items_skips_item_without_file():
    session = requests.Session()
    item = {
        "Title": "0999 de 1 enero",
        "MJDescripcion": ".",
        "MJFechaExpedicion": "2025-01-01T05:00:00Z",
        "File": None,
    }
    body = _sp_response([item])

    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, f"{_SITE_URL}/_api/web/lists/getbytitle('Decretos')/items", body=body)
        docs = _extraer_items(
            session, "Decretos", "Decreto", "D", "2025-01-01", "2025-12-31", "Ministerio de Justicia y del Derecho"
        )

    assert docs == []


def test_extraer_items_resolucion_outlier_still_extracts_a_number():
    # Caso real: "002 11 de agosto (2026)" -- número extraíble (002) aunque
    # el archivo real sea un manual mal clasificado; no es responsabilidad
    # del scraper detectar/corregir errores de datos del propio sitio.
    session = requests.Session()
    item = _decreto_item(
        "002 11 de agosto (2026)", "2026-06-02T05:00:00Z", "Res-No-0002-del-11-08-2011-MANUAL.pdf"
    )
    body = _sp_response([item])

    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, f"{_SITE_URL}/_api/web/lists/getbytitle('Resoluciones')/items", body=body)
        docs = _extraer_items(
            session, "Resoluciones", "Resolucion", "R", "2026-01-01", "2026-12-31",
            "Ministerio de Justicia y del Derecho",
        )

    assert len(docs) == 1
    assert docs[0].title == "R_MJ_0002_2026"


def test_extraer_items_circular_with_recognizable_code():
    session = requests.Session()
    item = {
        "Title": "CIRCULAR No MJD-CIR26-0000002-SCF-30320",
        "MJDescripcion": ".",
        "MJFechaExpedicion": "2026-01-05T05:00:00Z",
        "File": {"Name": "MJD-CIR26-0000002.pdf", "ServerRelativeUrl": "/normatividad-co/Circulares/MJD-CIR26-0000002.pdf"},
    }
    body = _sp_response([item])

    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, f"{_SITE_URL}/_api/web/lists/getbytitle('Circulares')/items", body=body)
        docs = _extraer_items(
            session, "Circulares", "Circular", "C", "2026-01-01", "2026-12-31", "Ministerio de Justicia y del Derecho"
        )

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "C_MJ_CIR26-0000002_2026"
    assert doc.title_unverified is False


def test_extraer_items_circular_uses_real_expedition_year_not_code_year():
    # Caso real: código dice CIR24 pero MJFechaExpedicion es de 2026 --
    # nunca se usa el año embebido en el código.
    session = requests.Session()
    item = {
        "Title": "CIRCULAR No MJD-CIR24-0000056-GCSQ-30320",
        "MJDescripcion": ".",
        "MJFechaExpedicion": "2026-07-09T05:00:00Z",
        "File": {"Name": "MJD-CIR26-0000056.pdf", "ServerRelativeUrl": "/normatividad-co/Circulares/MJD-CIR26-0000056.pdf"},
    }
    body = _sp_response([item])

    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, f"{_SITE_URL}/_api/web/lists/getbytitle('Circulares')/items", body=body)
        docs = _extraer_items(
            session, "Circulares", "Circular", "C", "2026-01-01", "2026-12-31", "Ministerio de Justicia y del Derecho"
        )

    assert docs[0].title == "C_MJ_CIR24-0000056_2026"


def test_extraer_items_circular_without_code_falls_back_to_raw_title():
    session = requests.Session()
    item = {
        "Title": "Entrada en vigencia del parágrafo 1 del artículo 5 de la Ley 2126 de 2021.",
        "MJDescripcion": ".",
        "MJFechaExpedicion": "2024-06-28T05:00:00Z",
        "File": {"Name": "CIRCULAR-No-MJD-CIR24-0000039-DJF-10000.pdf", "ServerRelativeUrl": "/normatividad-co/Circulares/x.pdf"},
    }
    body = _sp_response([item])

    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, f"{_SITE_URL}/_api/web/lists/getbytitle('Circulares')/items", body=body)
        docs = _extraer_items(
            session, "Circulares", "Circular", "C", "2024-01-01", "2024-12-31", "Ministerio de Justicia y del Derecho"
        )

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "Entrada en vigencia del parágrafo 1 del artículo 5 de la Ley 2126 de 2021."
    assert doc.title_unverified is True
    # La fecha real siempre está disponible aunque no haya código -- nunca
    # se descarta un item de minjusticia por falta de fecha.
    assert doc.f_providencia == "2024-06-28"


def test_extraer_items_returns_empty_on_request_error():
    session = requests.Session()
    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, f"{_SITE_URL}/_api/web/lists/getbytitle('Decretos')/items", status=500)
        docs = _extraer_items(
            session, "Decretos", "Decreto", "D", "2025-01-01", "2025-12-31", "Ministerio de Justicia y del Derecho"
        )
    assert docs == []


def test_extraer_items_follows_next_link():
    session = requests.Session()
    item1 = _decreto_item("0001 de 1 enero", "2025-01-01T05:00:00Z", "D1.pdf")
    item2 = _decreto_item("0002 de 2 enero", "2025-01-02T05:00:00Z", "D2.pdf")
    next_url = f"{_SITE_URL}/_api/web/lists/getbytitle('Decretos')/items?%24skiptoken=1"

    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET, f"{_SITE_URL}/_api/web/lists/getbytitle('Decretos')/items",
            body=_sp_response([item1], next_url=next_url),
        )
        rsps.add(responses.GET, next_url, body=_sp_response([item2]))
        docs = _extraer_items(
            session, "Decretos", "Decreto", "D", "2025-01-01", "2025-12-31", "Ministerio de Justicia y del Derecho"
        )

    assert [d.title for d in docs] == ["D0001025", "D0002025"]


# --- scrap(): flujo completo -------------------------------------------

@responses.activate
def test_scrap_queries_the_three_lists_and_continues_when_one_fails():
    responses.add(
        responses.GET, f"{_SITE_URL}/_api/web/lists/getbytitle('Decretos')/items", status=500,
    )
    responses.add(
        responses.GET, f"{_SITE_URL}/_api/web/lists/getbytitle('Resoluciones')/items",
        body=_sp_response([_decreto_item("1510 del 10 de agosto", "2026-08-10T05:00:00Z", "R1510.pdf")]),
    )
    responses.add(
        responses.GET, f"{_SITE_URL}/_api/web/lists/getbytitle('Circulares')/items",
        body=_sp_response([]),
    )

    scraper = ScrapMinJusticia()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert [d.title for d in docs] == ["R_MJ_1510_2026"]


@responses.activate
def test_scrap_respects_stop_event():
    import threading

    stop_event = threading.Event()
    stop_event.set()

    scraper = ScrapMinJusticia()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31", stop_event=stop_event)

    assert docs == []
    assert len(responses.calls) == 0
