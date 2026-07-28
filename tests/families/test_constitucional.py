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


def _scrap_with(fixture):
    responses.add(
        responses.GET,
        "https://www.corteconstitucional.gov.co/relatoria/buscador_new/",
        json=fixture,
        status=200,
    )
    scraper = ScrapConstitucional()
    return scraper.scrap(fini="2024-01-01", ffin="2024-03-01")


@responses.activate
def test_scrap_returns_expected_rawdocmodel():
    docs = _scrap_with(_fixture_response())

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "ST065_24"
    assert doc.tipo == "Sentencia de Tutela"
    assert doc.f_public == "2024-02-01"
    assert doc.f_providencia == "2024-01-25"
    assert doc.link["url"] == "https://www.corteconstitucional.gov.co/sentencias/t-065-24.rtf"
    assert doc.link["body"] == {"path": "T-065/24"}
    assert doc.save_path == "Corte Constitucional/2024-02-01/Sentencia de Tutela/ST065_24(extension)"


@responses.activate
def test_scrap_classifies_t_series_as_sentencia_de_tutela_even_when_prov_tipo_says_tutela():
    """The Corte's own search API is inconsistent for T-series rulings —
    sometimes prov_tipo="Sentencia", sometimes "Tutela" — so classification
    must key off the providencia number's own "T-" prefix, not prov_tipo,
    to get the same result either way."""
    fixture = _fixture_response()
    fixture["data"]["hits"]["hits"][0]["_source"]["prov_tipo"] = "Tutela"
    docs = _scrap_with(fixture)

    assert len(docs) == 1
    doc = docs[0]
    assert doc.tipo == "Sentencia de Tutela"
    assert doc.save_path == "Corte Constitucional/2024-02-01/Sentencia de Tutela/ST065_24(extension)"


@responses.activate
def test_scrap_classifies_c_series_as_sentencia_constitucional():
    fixture = _fixture_response()
    fixture["data"]["hits"]["hits"][0]["_source"]["prov_tipo"] = "Constitucionalidad"
    fixture["data"]["hits"]["hits"][0]["_source"]["prov_sentencia"] = "C-034/26"
    docs = _scrap_with(fixture)

    assert len(docs) == 1
    doc = docs[0]
    assert doc.tipo == "Sentencia Constitucional"
    assert doc.title == "SC034_26"
    assert doc.save_path == "Corte Constitucional/2024-02-01/Sentencia Constitucional/SC034_26(extension)"


@responses.activate
def test_scrap_classifies_su_series_as_sentencia_de_unificacion():
    fixture = _fixture_response()
    fixture["data"]["hits"]["hits"][0]["_source"]["prov_tipo"] = "Sentencia de unificación"
    fixture["data"]["hits"]["hits"][0]["_source"]["prov_sentencia"] = "SU.066/26"
    docs = _scrap_with(fixture)

    assert len(docs) == 1
    doc = docs[0]
    assert doc.tipo == "Sentencia de Unificación"
    # Already starts with "S" ("SU" = Sentencia de Unificación), so it isn't
    # prefixed again — must not become "SSU066_26".
    assert doc.title == "SU066_26"
    assert doc.save_path == "Corte Constitucional/2024-02-01/Sentencia de Unificación/SU066_26(extension)"


@responses.activate
def test_scrap_normalizes_title_with_period_and_space():
    fixture = _fixture_response()
    fixture["data"]["hits"]["hits"][0]["_source"]["prov_tipo"] = "Auto"
    fixture["data"]["hits"]["hits"][0]["_source"]["prov_sentencia"] = "A. 846/26"
    docs = _scrap_with(fixture)

    assert len(docs) == 1
    doc = docs[0]
    assert doc.tipo == "Auto"
    assert doc.title == "A846_26"
    assert doc.link["body"] == {"path": "A. 846/26"}
    assert doc.save_path == "Corte Constitucional/2024-02-01/Auto/A846_26(extension)"


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


@responses.activate
def test_scrap_queries_the_remote_search_even_for_a_single_day_range():
    """Regression test: fini == ffin (exactly what the daily scheduled run and
    any single-day manual run send) used to be silently skipped because the
    loop condition was a strict `<`, so this must actually hit the search API."""
    responses.add(
        responses.GET,
        "https://www.corteconstitucional.gov.co/relatoria/buscador_new/",
        json=_fixture_response(),
        status=200,
    )
    scraper = ScrapConstitucional()
    docs = scraper.scrap(fini="2024-06-01", ffin="2024-06-01")

    assert len(responses.calls) == 1
    assert "fini=2024-06-01" in responses.calls[0].request.url
    assert "ffin=2024-06-01" in responses.calls[0].request.url
    assert len(docs) == 1


@responses.activate
def test_scrap_does_not_repeat_the_last_day_for_a_multi_day_range():
    """The chunking loop must stop as soon as it reaches ffin, not fire one
    extra single-day query for the boundary it already covered."""
    docs = _scrap_with(_fixture_response())

    assert len(responses.calls) == 1
    assert len(docs) == 1
