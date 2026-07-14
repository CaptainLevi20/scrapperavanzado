import json
from urllib.parse import parse_qs, urlparse

import responses

from core.scrapers.families.ane import ScrapANE, _LIST_API
from core.scrapers.registry import FAMILY_REGISTRY

_ROOT_ID = 711


@responses.activate
def test_scrap_recurses_tree_and_filters_by_full_date():
    def _callback(request):
        qs = parse_qs(urlparse(request.url).query)
        filtro = qs.get("$filter", [""])[0]
        if filtro == f"padre eq {_ROOT_ID}":
            value = [
                {"ID": 900, "Title": "Resoluciones", "tipoContenido": "Carpeta", "archivo": None, "vigencia": None},
            ]
        elif filtro == "padre eq 900":
            value = [
                {
                    "ID": 901,
                    "Title": "Resolución 500 del 10 de mayo de 2024",
                    "tipoContenido": "Archivo",
                    "archivo": {"Url": "https://ane.gov.co/files/resolucion-500.pdf"},
                    "vigencia": None,
                },
            ]
        else:
            value = []
        return (200, {"Content-Type": "application/json"}, json.dumps({"value": value}))

    responses.add_callback(responses.GET, _LIST_API, callback=_callback, content_type="application/json")

    scraper = ScrapANE()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1
    assert docs[0].title == "Resolución 500 del 10 de mayo de 2024"
    assert docs[0].f_public == "2024-05-10"
    assert docs[0].tipo == "Resolución"
    assert docs[0].link["url"] == "https://ane.gov.co/files/resolucion-500.pdf"


@responses.activate
def test_scrap_skips_normograma_and_foreign_domains():
    def _callback(request):
        qs = parse_qs(urlparse(request.url).query)
        filtro = qs.get("$filter", [""])[0]
        if filtro == f"padre eq {_ROOT_ID}":
            value = [
                {"ID": 902, "Title": "Normograma general", "tipoContenido": "Archivo",
                 "archivo": {"Url": "https://ane.gov.co/files/normograma.pdf"}, "vigencia": None},
                {"ID": 903, "Title": "Documento externo 2024", "tipoContenido": "Archivo",
                 "archivo": {"Url": "https://external.example.com/doc.pdf"}, "vigencia": "2024"},
            ]
        else:
            value = []
        return (200, {"Content-Type": "application/json"}, json.dumps({"value": value}))

    responses.add_callback(responses.GET, _LIST_API, callback=_callback, content_type="application/json")

    scraper = ScrapANE()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert docs == []


@responses.activate
def test_scrap_falls_back_to_year_only_when_no_full_date():
    def _callback(request):
        qs = parse_qs(urlparse(request.url).query)
        filtro = qs.get("$filter", [""])[0]
        if filtro == f"padre eq {_ROOT_ID}":
            value = [
                {
                    "ID": 950,
                    "Title": "Resolución 91 de 2023",
                    "tipoContenido": "Archivo",
                    "archivo": {"Url": "https://ane.gov.co/files/resolucion-91.pdf"},
                    "vigencia": None,
                },
            ]
        else:
            value = []
        return (200, {"Content-Type": "application/json"}, json.dumps({"value": value}))

    responses.add_callback(responses.GET, _LIST_API, callback=_callback, content_type="application/json")

    scraper = ScrapANE()
    docs = scraper.scrap(fini="2023-01-01", ffin="2023-12-31")

    assert len(docs) == 1
    assert docs[0].f_public == "2023-01-01"
    assert docs[0].tipo == "Resolución"


def test_ane_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["ane"] is ScrapANE
