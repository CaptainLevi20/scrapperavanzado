import json
import re

import responses

from core.scrapers.families.corte_suprema import ScrapCorteSuprema
from core.scrapers.registry import FAMILY_REGISTRY

_URL = "https://consultaprovidenciasbk.cortesuprema.gov.co/api"


def _item(
    title="1. Sentencia SC1234-2024. Radicado 11001",
    fecha="2024-02-01T00:00:00Z",
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


def _callback_factory(item_fecha="2024-02-01T00:00:00Z"):
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
    assert {d.title for d in docs} == {"Sentencia SC1234-2024"}
    assert {d.f_public for d in docs} == {"2024-02-01"}
    save_path_suffixes = {d.save_path.split("/")[1] for d in docs}
    assert save_path_suffixes == {"SCT", "SCL", "SCC", "SCP"}
    assert docs[0].link == {
        "url": "https://consultaprovidenciasbk.cortesuprema.gov.co/downloadFile/",
        "body": {"path": "path/to/file"},
        "method": "POST",
    }


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
    # from autoSentencia ("AUTO"/"SENTENCIA") instead, capitalized; null falls
    # back to "Desconocido".
    def _callback(request):
        body = json.loads(request.body)
        query = body["query"]
        start = int(re.search(r"start:\s*(\d+)", query).group(1))
        tipo_query = re.search(r'typeOfQuery: "(\w+)"', query).group(1)
        if start != 0:
            return (200, {}, json.dumps({"data": {"getSearchResult": {"searchResults": []}}}))
        auto_sentencia = {"Tutelas": "AUTO", "Laboral": "SENTENCIA", "Civil": None}.get(tipo_query, "SENTENCIA")
        payload = {"data": {"getSearchResult": {"searchResults": [_item(auto_sentencia=auto_sentencia)]}}}
        return (200, {"Content-Type": "application/json"}, json.dumps(payload))

    responses.add_callback(responses.POST, _URL, callback=_callback, content_type="application/json")

    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    tipo_by_source_tipo = {d.save_path.split("/")[1]: d.tipo for d in docs}
    assert tipo_by_source_tipo["SCT"] == "Auto"  # Tutelas -> AUTO
    assert tipo_by_source_tipo["SCL"] == "Sentencia"  # Laboral -> SENTENCIA
    assert tipo_by_source_tipo["SCC"] == "Desconocido"  # Civil -> null


@responses.activate
def test_scrap_derives_especialidad_from_online_path():
    # Tutela wins over the internal sala segment (e.g. ".../TUTELAS/PENAL/...")
    # since that segment only names who resolved the tutela, not its nature.
    paths_by_tipo_query = {
        "Civil": "/var/www/html/Index/CIVIL/2026/Dr. X/Autos/AC1-2026.pdf",
        "Laboral": "/var/www/html/Index/LABORAL/PERMANENTE/2026/Dr. Y/Autos/AL1-2026.docx",
        "Penal": "/var/www/html/Index/PENAL/2026/CP1-2026.docx",
        "Tutelas": "/var/www/html/Index/TUTELAS/PENAL/2026/Reservadas/STP1-2026.docx",
    }

    def _callback(request):
        body = json.loads(request.body)
        query = body["query"]
        start = int(re.search(r"start:\s*(\d+)", query).group(1))
        if start != 0:
            return (200, {}, json.dumps({"data": {"getSearchResult": {"searchResults": []}}}))
        tipo_query = re.search(r'typeOfQuery: "(\w+)"', query).group(1)
        payload = {
            "data": {"getSearchResult": {"searchResults": [_item(online_path=paths_by_tipo_query[tipo_query])]}}
        }
        return (200, {"Content-Type": "application/json"}, json.dumps(payload))

    responses.add_callback(responses.POST, _URL, callback=_callback, content_type="application/json")

    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    especialidad_by_source_tipo = {d.save_path.split("/")[1]: d.especialidad for d in docs}
    assert especialidad_by_source_tipo["SCC"] == "Civil"
    assert especialidad_by_source_tipo["SCL"] == "Laboral"
    assert especialidad_by_source_tipo["SCP"] == "Penal"
    assert especialidad_by_source_tipo["SCT"] == "Tutela"  # /TUTELAS/PENAL/... -> Tutela, not Penal


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
            valid = _item(title="1. Sentencia SC9999-2024. Radicado 22002")
            payload = {"data": {"getSearchResult": {"searchResults": [malformed, valid]}}}
        else:
            payload = {"data": {"getSearchResult": {"searchResults": []}}}
        return (200, {"Content-Type": "application/json"}, json.dumps(payload))

    responses.add_callback(responses.POST, _URL, callback=_callback, content_type="application/json")

    scraper = ScrapCorteSuprema()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    assert len(docs) == 4  # el item malformado se salta, uno válido por cada uno de los 4 tipos
    assert {d.title for d in docs} == {"Sentencia SC9999-2024"}
