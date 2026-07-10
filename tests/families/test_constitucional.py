import threading

import responses

from core.scrapers.families.constitucional import ScrapConstitucional
from core.scrapers.registry import FAMILY_REGISTRY


def _fixture_response():
    return {
        "data": {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "rutahtml": "t-065-24.htm",
                            "prov_sentencia": "T-065/24",
                            "prov_tipo": "Sentencia",
                            "prov_f_public": "2024-02-01",
                            "prov_f_sentencia": "2024-01-25",
                        }
                    }
                ]
            }
        }
    }


@responses.activate
def test_scrap_returns_expected_rawdocmodel():
    responses.add(
        responses.GET,
        "https://www.corteconstitucional.gov.co/relatoria/buscador_new/",
        json=_fixture_response(),
        status=200,
    )
    scraper = ScrapConstitucional()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "T-065/24"
    assert doc.tipo == "Sentencia"
    assert doc.f_public == "2024-02-01"
    assert doc.f_providencia == "2024-01-25"
    assert doc.link["url"] == "https://www.corteconstitucional.gov.co/sentencias/t-065-24.rtf"
    assert doc.link["body"] == {"path": "T-065/24"}
    assert doc.save_path == "Corte Constitucional/2024-02-01/Sentencia/T-065-24(extension)"


def test_constitucional_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401 — triggers registration

    assert FAMILY_REGISTRY["constitucional"] is ScrapConstitucional


@responses.activate
def test_scrap_stops_early_when_stop_event_is_already_set():
    stop_event = threading.Event()
    stop_event.set()

    scraper = ScrapConstitucional()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01", stop_event=stop_event)

    assert docs == []
    assert len(responses.calls) == 0
