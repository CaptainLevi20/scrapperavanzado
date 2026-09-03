import requests
import responses
from responses import matchers

from core.scrapers.registry import FAMILY_REGISTRY
from core.scrapers.families.minvivienda import (
    ScrapMinvivienda,
    _clasificar_fila_auto,
    _extraer_numero,
    _normalize_title,
    _parse_f_public,
)

_LISTADO_URL = "https://minvivienda.gov.co/normativa"


def _fila(titulo, fecha_iso, creado_texto="Mié, 05/08/2026 - 19:03", pdf_url="https://minvivienda.gov.co/sites/default/files/normativa/doc.pdf", resumen="Por la cual se resuelve algo", con_archivo=True):
    archivo_html = (
        f'<span class="file"><a href="{pdf_url}" type="application/pdf" target="_blank">doc.pdf</a></span>'
        if con_archivo
        else ""
    )
    return f"""
<div class="views-row">
  <div class="listing-title"><span><a href="/normativa/x" hreflang="es">{titulo}</a></span></div>
  <div class="views-field views-field-field-legal-regulation-date">
    <span class="views-label">Fecha de Norma: </span>
    <span class="field-content"><time datetime="{fecha_iso}">{fecha_iso}</time></span>
  </div>
  <div class="views-field views-field-created">
    <span class="views-label">Fecha de publicación: : </span>
    <span class="field-content">{creado_texto}</span>
  </div>
  <div class="views-field views-field-field-summary">
    <span class="field-content"><p>{resumen}</p></span>
  </div>
  <div class="views-field views-field-field-legal-regulation-file">
    <span class="field-content">{archivo_html}</span>
  </div>
</div>
"""


def _matcher(tipo_param: str, page: int):
    return matchers.query_param_matcher({"tipo": tipo_param, "page": str(page)})


def test_extraer_numero_finds_clean_number_before_year():
    assert _extraer_numero("Resolución 0786 - 2026", "Resolución") == "0786"


def test_extraer_numero_handles_de_separator():
    assert _extraer_numero("Circular 0048 de 2026", "Circular") == "0048"


def test_extraer_numero_handles_no_prefix():
    assert _extraer_numero("Circular No. 0003 - 2024", "Circular") == "0003"


def test_extraer_numero_finds_number_with_trailing_text_after_year():
    # "Directiva 006 - 2019 de la Procuraduría..." -- el número no está al
    # final del título, por eso la búsqueda no puede ir anclada a $.
    assert _extraer_numero("Directiva 006 - 2019 de la Procuraduría General de la Nación", "Directiva") == "006"
    assert _extraer_numero("Circular 031 - 2011 - Procuraduría", "Circular") == "031"


def test_extraer_numero_circular_falls_back_to_radicado_code():
    assert _extraer_numero("Circular 2026EE0026348", "Circular") == "2026EE0026348"


def test_extraer_numero_returns_none_when_no_number_and_not_circular():
    assert _extraer_numero("Auto admisorio Acción Popular 50001-23-33-000-2026-00192-00", "Auto") is None


def test_extraer_numero_circular_returns_none_when_no_digits_at_all():
    assert _extraer_numero("Circular adopción de medidas de prevención por temporada de lluvias", "Circular") is None


def test_normalize_title_pads_numeric_code():
    assert _normalize_title("R", "786", "2026") == "R_MVCT_0786_2026"


def test_normalize_title_uses_conpes_literal():
    assert _normalize_title("CONPES", "3947", "2018") == "CONPES_MVCT_3947_2018"


def test_normalize_title_circular_radicado_code_used_as_is():
    assert _normalize_title("C", "2026EE0026348", "2026") == "C_MVCT_2026EE0026348_2026"


def test_parse_f_public_extracts_date_ignoring_weekday_and_time():
    assert _parse_f_public("Mié, 05/08/2026 - 19:03") == "2026-08-05"


def test_clasificar_fila_auto_reclassifies_by_leading_word():
    assert _clasificar_fila_auto("Circular 2020EE0037555") == ("Circular", "C")
    assert _clasificar_fila_auto("Sentencia 2020-0972") == ("Sentencia", "S")
    assert _clasificar_fila_auto("Aviso 05001 23 33 000 2023 00646 00") == ("Aviso", "AV")
    assert _clasificar_fila_auto("Auto admisorio Acción Popular 2022-00032") == ("Auto", "AU")
    assert _clasificar_fila_auto("Medida Cautelar de Suspensión Provisional") == ("Auto", "AU")


def test_minvivienda_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["minvivienda"].__name__ == "ScrapMinvivienda"


def test_filters_by_publication_date_stays_at_default_false():
    assert ScrapMinvivienda.filters_by_publication_date is False


def test_doc_id_uses_publication_date_is_disabled():
    assert ScrapMinvivienda.doc_id_uses_publication_date is False


@responses.activate
def test_scrap_parses_a_clean_resolucion_row():
    html = _fila("Resolución 0786 - 2026", "2026-08-05T23:52:51Z")
    responses.add(responses.GET, _LISTADO_URL, body=html, match=[_matcher("Resolución", 0)])
    for tipo_param, count in [
        ("Decreto", 0), ("Ley", 0), ("CONPES", 0), ("Acuerdo", 0),
        ("Directiva", 0), ("Circular", 0), ("Auto", 0),
    ]:
        responses.add(responses.GET, _LISTADO_URL, body="", match=[_matcher(tipo_param, 0)])

    scraper = ScrapMinvivienda()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "R_MVCT_0786_2026"
    assert doc.title_unverified is False
    assert doc.tipo == "Resolución"
    assert doc.f_providencia == "2026-08-05"
    assert doc.f_public == "2026-08-05"
    assert doc.detalle == "Por la cual se resuelve algo"
    assert doc.link["url"].endswith("doc.pdf")


@responses.activate
def test_fetch_pagina_does_not_double_encode_the_tipo_param():
    # Regresión: un primer intento pre-codificaba "tipo" con urllib.parse.quote
    # antes de pasarlo a requests, que ya codifica los valores de `params` --
    # el resultado era "%25C3%25B3" (el "%" de la primera codificación
    # codificado otra vez) en vez de "%C3%B3", que el sitio real no reconoce
    # y devuelve 0 resultados. Se confirma inspeccionando la URL real enviada.
    responses.add(responses.GET, _LISTADO_URL, body="", match=[_matcher("Resolución", 0)])

    scraper = ScrapMinvivienda()
    scraper._fetch_pagina(requests.Session(), "Resolución", 0)

    sent_url = responses.calls[0].request.url
    assert "%C3%B3" in sent_url
    assert "%25C3%25B3" not in sent_url


@responses.activate
def test_scrap_reclassifies_auto_bucket_rows_by_title():
    filas = "".join([
        _fila("Circular 2020EE0037555", "2020-06-01T00:00:00Z"),
        _fila("Sentencia 2020-0972", "2020-05-01T00:00:00Z"),
        _fila("Aviso 05001 23 33 000 2023 00646 00", "2023-02-01T00:00:00Z"),
        _fila("Auto 0155 - 2018", "2018-01-01T00:00:00Z"),
    ])
    responses.add(responses.GET, _LISTADO_URL, body=filas, match=[_matcher("Auto", 0)])
    responses.add(responses.GET, _LISTADO_URL, body="", match=[_matcher("Auto", 1)])
    for tipo_param in ["Resolución", "Decreto", "Ley", "CONPES", "Acuerdo", "Directiva", "Circular"]:
        responses.add(responses.GET, _LISTADO_URL, body="", match=[_matcher(tipo_param, 0)])

    scraper = ScrapMinvivienda()
    docs = scraper.scrap(fini="2000-01-01", ffin="2026-12-31")

    tipos = {d.title: d.tipo for d in docs}
    assert tipos["C_MVCT_2020EE0037555_2020"] == "Circular"
    # "Sentencia 2020-0972" no trae espacios alrededor del guion -- no es un
    # "numero - año" real, sino un radicado pegado; queda sin verificar con
    # el título crudo en vez de un número inventado.
    assert tipos["Sentencia 2020-0972"] == "Sentencia"
    # "Aviso 05001 23 33 000 2023 00646 00" no trae "-"/"de" entre número y
    # año (son solo espacios) -- ningún patrón matchea, queda sin verificar
    # con el título crudo, en vez de un número inventado.
    assert tipos["Aviso 05001 23 33 000 2023 00646 00"] == "Aviso"
    assert tipos["AU_MVCT_0155_2018"] == "Auto"


@responses.activate
def test_scrap_stops_paginating_once_a_full_page_is_older_than_fini():
    pagina_0 = _fila("Resolución 0002 - 2026", "2026-02-01T00:00:00Z")
    pagina_1_vieja = _fila("Resolución 0001 - 2020", "2020-01-01T00:00:00Z")
    responses.add(responses.GET, _LISTADO_URL, body=pagina_0, match=[_matcher("Resolución", 0)])
    responses.add(responses.GET, _LISTADO_URL, body=pagina_1_vieja, match=[_matcher("Resolución", 1)])
    # No se registra la página 2: si el scraper la pidiera, `responses` lanzaría
    # ConnectionError por falta de matcher, y el test fallaría -- así se prueba
    # el corte temprano sin necesitar inspeccionar llamadas internamente.
    for tipo_param in ["Decreto", "Ley", "CONPES", "Acuerdo", "Directiva", "Circular", "Auto"]:
        responses.add(responses.GET, _LISTADO_URL, body="", match=[_matcher(tipo_param, 0)])

    scraper = ScrapMinvivienda()
    docs = scraper.scrap(fini="2025-01-01", ffin="2026-12-31")

    assert {d.title for d in docs} == {"R_MVCT_0002_2026"}


@responses.activate
def test_scrap_stops_when_page_returns_no_rows():
    responses.add(responses.GET, _LISTADO_URL, body="", match=[_matcher("Acuerdo", 0)])
    for tipo_param in ["Resolución", "Decreto", "Ley", "CONPES", "Directiva", "Circular", "Auto"]:
        responses.add(responses.GET, _LISTADO_URL, body="", match=[_matcher(tipo_param, 0)])

    scraper = ScrapMinvivienda()
    docs = scraper.scrap(fini="2000-01-01", ffin="2026-12-31")

    assert docs == []


@responses.activate
def test_scrap_skips_row_without_file_link():
    html = _fila("Resolución 0786 - 2026", "2026-08-05T23:52:51Z", con_archivo=False)
    responses.add(responses.GET, _LISTADO_URL, body=html, match=[_matcher("Resolución", 0)])
    for tipo_param in ["Decreto", "Ley", "CONPES", "Acuerdo", "Directiva", "Circular", "Auto"]:
        responses.add(responses.GET, _LISTADO_URL, body="", match=[_matcher(tipo_param, 0)])

    scraper = ScrapMinvivienda()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert docs == []


@responses.activate
def test_scrap_continues_past_a_failing_category():
    responses.add(responses.GET, _LISTADO_URL, status=500, match=[_matcher("Resolución", 0)])
    html = _fila("Decreto 0772 - 2026", "2026-07-16T14:16:14Z")
    responses.add(responses.GET, _LISTADO_URL, body=html, match=[_matcher("Decreto", 0)])
    for tipo_param in ["Ley", "CONPES", "Acuerdo", "Directiva", "Circular", "Auto"]:
        responses.add(responses.GET, _LISTADO_URL, body="", match=[_matcher(tipo_param, 0)])

    progreso = []
    scraper = ScrapMinvivienda()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31", on_progress=progreso.append)

    assert {d.title for d in docs} == {"D0772026"}
    assert any("Error" in m and "Resolución" in m for m in progreso)


@responses.activate
def test_scrap_keeps_document_without_recognizable_number_as_unverified():
    html = _fila("Circular adopción de medidas de prevención por temporada de lluvias", "2017-05-01T00:00:00Z")
    responses.add(responses.GET, _LISTADO_URL, body=html, match=[_matcher("Circular", 0)])
    for tipo_param in ["Resolución", "Decreto", "Ley", "CONPES", "Acuerdo", "Directiva", "Auto"]:
        responses.add(responses.GET, _LISTADO_URL, body="", match=[_matcher(tipo_param, 0)])

    scraper = ScrapMinvivienda()
    docs = scraper.scrap(fini="2000-01-01", ffin="2026-12-31")

    assert len(docs) == 1
    assert docs[0].title == "Circular adopción de medidas de prevención por temporada de lluvias"
    assert docs[0].title_unverified is True
    assert docs[0].f_providencia == "2017-05-01"


@responses.activate
def test_scrap_respects_limit():
    filas = "".join([
        _fila(f"Resolución {n:04d} - 2026", "2026-02-01T00:00:00Z") for n in range(1, 4)
    ])
    responses.add(responses.GET, _LISTADO_URL, body=filas, match=[_matcher("Resolución", 0)])
    for tipo_param in ["Decreto", "Ley", "CONPES", "Acuerdo", "Directiva", "Circular", "Auto"]:
        responses.add(responses.GET, _LISTADO_URL, body="", match=[_matcher(tipo_param, 0)])

    scraper = ScrapMinvivienda()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31", limit=1)

    assert len(docs) == 1


@responses.activate
def test_scrap_falls_back_to_providencia_when_publicado_field_unparseable():
    html = _fila("Resolución 0786 - 2026", "2026-08-05T23:52:51Z", creado_texto="sin fecha reconocible")
    responses.add(responses.GET, _LISTADO_URL, body=html, match=[_matcher("Resolución", 0)])
    for tipo_param in ["Decreto", "Ley", "CONPES", "Acuerdo", "Directiva", "Circular", "Auto"]:
        responses.add(responses.GET, _LISTADO_URL, body="", match=[_matcher(tipo_param, 0)])

    scraper = ScrapMinvivienda()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert len(docs) == 1
    assert docs[0].f_public == "2026-08-05"
    assert docs[0].f_providencia == "2026-08-05"


@responses.activate
def test_scrap_filters_out_documents_outside_requested_range():
    html = _fila("Resolución 0001 - 2010", "2010-01-01T00:00:00Z")
    responses.add(responses.GET, _LISTADO_URL, body=html, match=[_matcher("Resolución", 0)])
    for tipo_param in ["Decreto", "Ley", "CONPES", "Acuerdo", "Directiva", "Circular", "Auto"]:
        responses.add(responses.GET, _LISTADO_URL, body="", match=[_matcher(tipo_param, 0)])

    scraper = ScrapMinvivienda()
    docs = scraper.scrap(fini="2020-01-01", ffin="2026-12-31")

    assert docs == []
