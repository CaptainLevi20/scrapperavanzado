import json
from urllib.parse import parse_qs, urlparse

import responses

from core.scrapers.families.adr import ScrapADR, _API_PAGES
from core.scrapers.registry import FAMILY_REGISTRY


def test_extraer_documentos_parses_full_date():
    scraper = ScrapADR()
    html = '<a href="/wp-content/uploads/2024/04/decreto-381.pdf">Decreto No. 0381 del 07 de abril de 2024</a>'
    docs = scraper._extraer_documentos(html, "Decreto", "2024-01-01", "2024-12-31")

    assert len(docs) == 1
    assert docs[0].f_public == "2024-04-07"
    assert docs[0].save_path == "Agencia de Desarrollo Rural/2024-04-07/Decreto/(filename)(extension)"


def test_extraer_documentos_falls_back_to_year_only():
    scraper = ScrapADR()
    html = '<a href="/wp-content/uploads/2024/06/ley-2387.pdf">LEY 2387 DE 2024</a>'
    docs = scraper._extraer_documentos(html, "Ley", "2024-01-01", "2024-12-31")

    assert len(docs) == 1
    assert docs[0].f_public == "2024-01-01"


def test_extraer_documentos_falls_back_to_upload_date():
    scraper = ScrapADR()
    html = '<a href="/wp-content/uploads/2024/06/circular-sin-fecha.pdf">Circular sin fecha en el texto</a>'
    docs = scraper._extraer_documentos(html, "Circular", "2024-01-01", "2024-12-31")

    assert len(docs) == 1
    assert docs[0].f_public == "2024-06-01"


def test_extraer_documentos_excludes_out_of_range():
    scraper = ScrapADR()
    html = '<a href="/wp-content/uploads/2020/04/decreto-viejo.pdf">Decreto No. 0100 del 01 de abril de 2020</a>'
    docs = scraper._extraer_documentos(html, "Decreto", "2024-01-01", "2024-12-31")

    assert docs == []


@responses.activate
def test_scrap_aggregates_across_categories():
    def _callback(request):
        slug = parse_qs(urlparse(request.url).query).get("slug", [""])[0]
        if slug == "leyes":
            html = '<a href="/wp-content/uploads/2024/05/ley-123.pdf">LEY 123 DE 2024</a>'
            body = json.dumps([{"content": {"rendered": html}}])
        else:
            body = json.dumps([{"content": {"rendered": ""}}])
        return (200, {"Content-Type": "application/json"}, body)

    responses.add_callback(responses.GET, _API_PAGES, callback=_callback, content_type="application/json")

    scraper = ScrapADR()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-12-31")

    assert len(docs) == 1
    assert docs[0].tipo == "Ley"
    assert docs[0].f_public == "2024-01-01"


@responses.activate
def test_scrap_continues_past_a_failing_resolucion_year():
    # A single failing/unavailable year page (e.g. a transient 500) must not
    # abort the whole run and lose documents already found in other years.
    def _callback(request):
        slug = parse_qs(urlparse(request.url).query).get("slug", [""])[0]
        if slug == "resoluciones-2024":
            return (500, {}, "boom")
        if slug == "resoluciones-2025":
            html = '<a href="/wp-content/uploads/2025/05/res-1.pdf">Resolución 001 de 2025</a>'
            return (200, {"Content-Type": "application/json"}, json.dumps([{"content": {"rendered": html}}]))
        return (200, {"Content-Type": "application/json"}, json.dumps([{"content": {"rendered": ""}}]))

    responses.add_callback(responses.GET, _API_PAGES, callback=_callback, content_type="application/json")

    scraper = ScrapADR()
    docs = scraper.scrap(fini="2024-01-01", ffin="2025-12-31")

    assert len(docs) == 1
    assert docs[0].tipo == "Resolución"
    assert docs[0].f_public == "2025-01-01"


def test_adr_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["adr"] is ScrapADR
