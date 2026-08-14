import responses

from core.scrapers.families.mineducacion import (
    ScrapMineducacion,
    _extraer_fila,
    _normalize_title,
    _pdf_href_from_doc_href,
)
from core.scrapers.registry import FAMILY_REGISTRY


def test_mineducacion_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["mineducacion"].__name__ == "ScrapMineducacion"


def test_filters_by_publication_date_stays_at_default_false():
    assert ScrapMineducacion.filters_by_publication_date is False


def test_doc_id_uses_publication_date_is_true():
    # A diferencia de minvivienda/minambiente (donde f_public es un
    # timestamp del sitio que puede re-fecharse), aquí f_public viene del
    # propio identificador del documento en el Normograma -- intrínseco,
    # nunca cambia para el mismo archivo.
    assert ScrapMineducacion.doc_id_uses_publication_date is True


def test_normalize_title_builds_canonical_code():
    assert _normalize_title("R", "19230", "2026") == "R_MEN_19230_2026"


def test_normalize_title_pads_short_numbers_to_four_digits():
    assert _normalize_title("D", "802", "2026") == "D_MEN_0802_2026"


def test_normalize_title_uses_directiva_literal_instead_of_a_single_letter():
    assert _normalize_title("DIRECTIVA", "3", "2026") == "DIRECTIVA_MEN_0003_2026"


def test_normalize_title_falls_back_to_raw_number_when_not_numeric():
    assert _normalize_title("C", "12A", "2026") == "C_MEN_12A_2026"


def test_pdf_href_from_doc_href_swaps_docs_for_docs_pdf_and_extension():
    assert (
        _pdf_href_from_doc_href("docs/resolucion_mineducacion_19230_2026.htm")
        == "docs/pdf/resolucion_mineducacion_19230_2026.pdf"
    )


def test_pdf_href_from_doc_href_handles_no_leading_folder():
    assert _pdf_href_from_doc_href("resolucion_19230_2026.htm") == "pdf/resolucion_19230_2026.pdf"


def _fila(id_documento: str, href: str, descripcion: str = "Descripción de prueba.") -> str:
    return f"""
    <div class="opcion-nueva">
      <a href="{href}" target="_blank">
        <div class="id-documento">{id_documento}</div>
        <div class="descripcion-documento"><p>{descripcion}</p></div>
      </a>
    </div>
    """


def test_extraer_fila_parses_a_clean_row_with_me_suffix():
    html = _fila(
        "Resolución 19230 de 2026 ME",
        "docs/resolucion_mineducacion_19230_2026.htm",
        descripcion="Por la cual se valida el Modelo de Gestión de Calidad.",
    )
    from bs4 import BeautifulSoup

    fila = BeautifulSoup(html, "html.parser").select_one("div.opcion-nueva")

    resultado = _extraer_fila(fila, "Resolución", "R", source="Ministerio de Educación Nacional")
    assert resultado is not None
    anio, doc = resultado

    assert anio == "2026"
    assert doc.title == "R_MEN_19230_2026"
    assert doc.tipo == "Resolución"
    assert doc.f_public == "2026-01-01"
    assert doc.title_unverified is False
    assert doc.detalle == "Por la cual se valida el Modelo de Gestión de Calidad."
    assert doc.link["url"] == (
        "https://normograma.info/men/compilacion/compilacion/docs/pdf/resolucion_mineducacion_19230_2026.pdf"
    )
    assert doc.save_path == "Ministerio de Educación Nacional/2026-01-01/Resolución/R_MEN_19230_2026(extension)"


def test_extraer_fila_parses_a_row_without_me_suffix():
    # Decreto y Ley no llevan el sufijo " ME" (los expiden Presidencia y
    # Congreso, no el Ministerio).
    html = _fila("Decreto 802 de 2026", "docs/decreto_0802_2026.htm")
    from bs4 import BeautifulSoup

    fila = BeautifulSoup(html, "html.parser").select_one("div.opcion-nueva")

    resultado = _extraer_fila(fila, "Decreto", "D", source="Ministerio de Educación Nacional")
    assert resultado is not None
    anio, doc = resultado
    assert anio == "2026"
    assert doc.title == "D_MEN_0802_2026"


def test_extraer_fila_returns_none_for_unrecognized_format():
    html = _fila("Texto sin el formato esperado", "docs/algo.htm")
    from bs4 import BeautifulSoup

    fila = BeautifulSoup(html, "html.parser").select_one("div.opcion-nueva")

    progreso = []
    resultado = _extraer_fila(fila, "Resolución", "R", on_progress=progreso.append, source="MEN")
    assert resultado is None
    assert any("no reconocido" in m for m in progreso)


def test_extraer_fila_returns_none_when_no_link():
    html = """
    <div class="opcion-nueva">
      <div class="id-documento">Resolución 1 de 2026 ME</div>
    </div>
    """
    from bs4 import BeautifulSoup

    fila = BeautifulSoup(html, "html.parser").select_one("div.opcion-nueva")

    assert _extraer_fila(fila, "Resolución", "R", source="MEN") is None


def test_extraer_fila_handles_missing_description():
    html = """
    <div class="opcion-nueva">
      <a href="docs/resolucion_1_2026.htm">
        <div class="id-documento">Resolución 1 de 2026 ME</div>
      </a>
    </div>
    """
    from bs4 import BeautifulSoup

    fila = BeautifulSoup(html, "html.parser").select_one("div.opcion-nueva")

    resultado = _extraer_fila(fila, "Resolución", "R", source="MEN")
    assert resultado is not None
    _, doc = resultado
    assert doc.detalle is None


_SELECT_HTML_TPL = """
<html><body>
<select>
{options}
</select>
{filas}
</body></html>
"""


def _pagina(years_options: list, filas_html: str = "") -> str:
    options = "\n".join(f'<option value="{i+1}">{y}</option>' for i, y in enumerate(years_options))
    return _SELECT_HTML_TPL.format(options=options, filas=filas_html)


@responses.activate
def test_scrap_categoria_only_fetches_years_not_already_embedded():
    base_page = _pagina(
        ["2026", "2025", "2024"],
        filas_html=_fila("Resolución 1 de 2026 ME", "docs/resolucion_1_2026.htm"),
    )
    year_2025_page = _fila("Resolución 2 de 2025 ME", "docs/resolucion_2_2025.htm")

    responses.add(responses.GET, "https://normograma.info/men/compilacion/compilacion/cndser_x.html", body=base_page)
    responses.add(
        responses.GET,
        "https://normograma.info/men/compilacion/compilacion/cndser_x_2025.html",
        body=year_2025_page,
    )
    # 2024 no se pide porque queda fuera del rango solicitado (fini=2025).

    scraper = ScrapMineducacion()
    import requests

    session = requests.Session()
    docs = scraper._scrap_categoria(session, "cndser_x", "Resolución", "R", "2025-01-01", "2026-12-31")

    assert {d.title for d in docs} == {"R_MEN_0001_2026", "R_MEN_0002_2025"}
    assert len(responses.calls) == 2  # base + solo 2025, nunca 2024


@responses.activate
def test_scrap_categoria_does_not_refetch_a_year_already_embedded_in_the_base_page():
    # Categoría pequeña (ej. Acuerdo real): todos sus años ya vienen en la
    # página base, sin archivos "_{año}.html" separados -- pedir uno
    # devolvería 404 en el sitio real. No debe intentarlo.
    base_page = _pagina(
        ["2023", "2022"],
        filas_html=(
            _fila("Acuerdo 1 de 2023 ME", "docs/acuerdo_1_2023.htm")
            + _fila("Acuerdo 1 de 2022 ME", "docs/acuerdo_1_2022.htm")
        ),
    )
    responses.add(responses.GET, "https://normograma.info/men/compilacion/compilacion/cndsea_x.html", body=base_page)

    scraper = ScrapMineducacion()
    import requests

    session = requests.Session()
    docs = scraper._scrap_categoria(session, "cndsea_x", "Acuerdo", "A", "2022-01-01", "2023-12-31")

    assert {d.title for d in docs} == {"A_MEN_0001_2023", "A_MEN_0001_2022"}
    assert len(responses.calls) == 1  # solo la página base, ningún fragmento


@responses.activate
def test_scrap_categoria_finds_current_year_documents_on_a_narrow_incremental_window():
    # Regresión: f_public es siempre "{año}-01-01" (el Normograma no da
    # día/mes), pero las corridas programadas reales usan una ventana corta
    # tipo "hoy - 3 días" (ver worker/beat_schedule.py), casi nunca 1 de
    # enero. Si el filtro comparara fini/ffin como fecha exacta contra
    # "2026-01-01", un documento recién publicado en agosto de 2026 nunca
    # pasaría un fini como "2026-08-01" -- la fuente quedaría ciega a
    # documentos nuevos el resto del año. El filtro debe comparar por año,
    # no por fecha exacta.
    base_page = _pagina(
        ["2026"],
        filas_html=_fila("Resolución 1 de 2026 ME", "docs/resolucion_1_2026.htm"),
    )
    responses.add(responses.GET, "https://normograma.info/men/compilacion/compilacion/cndser_x.html", body=base_page)

    scraper = ScrapMineducacion()
    import requests

    session = requests.Session()
    # Ventana angosta típica de una corrida programada: "hoy - 3 días" a
    # "hoy", muy lejos del 1 de enero.
    docs = scraper._scrap_categoria(session, "cndser_x", "Resolución", "R", "2026-08-10", "2026-08-13")

    assert {d.title for d in docs} == {"R_MEN_0001_2026"}


@responses.activate
def test_scrap_categoria_filters_out_of_range_years():
    base_page = _pagina(
        ["2026"],
        filas_html=_fila("Resolución 1 de 2026 ME", "docs/resolucion_1_2026.htm"),
    )
    responses.add(responses.GET, "https://normograma.info/men/compilacion/compilacion/cndser_x.html", body=base_page)

    scraper = ScrapMineducacion()
    import requests

    session = requests.Session()
    docs = scraper._scrap_categoria(session, "cndser_x", "Resolución", "R", "2020-01-01", "2020-12-31")

    assert docs == []


@responses.activate
def test_scrap_categoria_continues_when_a_year_fragment_fails():
    base_page = _pagina(["2026", "2025"], filas_html=_fila("Resolución 1 de 2026 ME", "docs/resolucion_1_2026.htm"))
    responses.add(responses.GET, "https://normograma.info/men/compilacion/compilacion/cndser_x.html", body=base_page)
    responses.add(
        responses.GET, "https://normograma.info/men/compilacion/compilacion/cndser_x_2025.html", status=500
    )

    progreso = []
    scraper = ScrapMineducacion()
    import requests

    session = requests.Session()
    docs = scraper._scrap_categoria(
        session, "cndser_x", "Resolución", "R", "2025-01-01", "2026-12-31", on_progress=progreso.append
    )

    assert {d.title for d in docs} == {"R_MEN_0001_2026"}
    assert any("Error" in m and "2025" in m for m in progreso)


@responses.activate
def test_scrap_categoria_continues_when_base_page_fails():
    responses.add(responses.GET, "https://normograma.info/men/compilacion/compilacion/cndser_x.html", status=500)

    progreso = []
    scraper = ScrapMineducacion()
    import requests

    session = requests.Session()
    docs = scraper._scrap_categoria(
        session, "cndser_x", "Resolución", "R", "2025-01-01", "2026-12-31", on_progress=progreso.append
    )

    assert docs == []
    assert any("Error" in m for m in progreso)


def _categoria_urls():
    slugs = {
        "resoluciones": "cndser_ministerio_educacion_nacional",
        "decretos": "cndsed_presidencia_republica",
        "circulares": "cndsec_ministerio_educacion_nacional",
        "directivas": "cndsed_ministerio_educacion_nacional",
        "acuerdos": "cndsea_ministerio_educacion_nacional",
        "leyes": "cndsel_congreso_republica",
        "conceptos": "c-dc_occ_ministerio_educacion_nacional",
    }
    return {k: f"https://normograma.info/men/compilacion/compilacion/{v}.html" for k, v in slugs.items()}


@responses.activate
def test_scrap_aggregates_across_all_seven_categories():
    urls = _categoria_urls()
    empty_page = _pagina([])
    resoluciones_page = _pagina(["2026"], filas_html=_fila("Resolución 1 de 2026 ME", "docs/resolucion_1_2026.htm"))
    leyes_page = _pagina(["2026"], filas_html=_fila("Ley 2600 de 2026", "docs/ley_2600_2026.htm"))

    responses.add(responses.GET, urls["resoluciones"], body=resoluciones_page)
    responses.add(responses.GET, urls["decretos"], body=empty_page)
    responses.add(responses.GET, urls["circulares"], body=empty_page)
    responses.add(responses.GET, urls["directivas"], body=empty_page)
    responses.add(responses.GET, urls["acuerdos"], body=empty_page)
    responses.add(responses.GET, urls["leyes"], body=leyes_page)
    responses.add(responses.GET, urls["conceptos"], body=empty_page)

    scraper = ScrapMineducacion()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert {d.title for d in docs} == {"R_MEN_0001_2026", "L_MEN_2600_2026"}


@responses.activate
def test_scrap_continues_past_a_failing_category():
    urls = _categoria_urls()
    empty_page = _pagina([])
    leyes_page = _pagina(["2026"], filas_html=_fila("Ley 2600 de 2026", "docs/ley_2600_2026.htm"))

    responses.add(responses.GET, urls["resoluciones"], status=500)
    responses.add(responses.GET, urls["decretos"], body=empty_page)
    responses.add(responses.GET, urls["circulares"], body=empty_page)
    responses.add(responses.GET, urls["directivas"], body=empty_page)
    responses.add(responses.GET, urls["acuerdos"], body=empty_page)
    responses.add(responses.GET, urls["leyes"], body=leyes_page)
    responses.add(responses.GET, urls["conceptos"], body=empty_page)

    progreso = []
    scraper = ScrapMineducacion()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31", on_progress=progreso.append)

    assert {d.title for d in docs} == {"L_MEN_2600_2026"}
    assert any("Error" in m and "Resolución" in m for m in progreso)


@responses.activate
def test_scrap_respects_limit():
    urls = _categoria_urls()
    empty_page = _pagina([])
    resoluciones_page = _pagina(
        ["2026"],
        filas_html=(
            _fila("Resolución 1 de 2026 ME", "docs/resolucion_1_2026.htm")
            + _fila("Resolución 2 de 2026 ME", "docs/resolucion_2_2026.htm")
        ),
    )

    responses.add(responses.GET, urls["resoluciones"], body=resoluciones_page)
    for key in ("decretos", "circulares", "directivas", "acuerdos", "leyes", "conceptos"):
        responses.add(responses.GET, urls[key], body=empty_page)

    scraper = ScrapMineducacion()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31", limit=1)

    assert len(docs) == 1


@responses.activate
def test_scrap_respects_stop_event_between_categories():
    import threading

    stop_event = threading.Event()
    stop_event.set()

    scraper = ScrapMineducacion()
    docs = scraper.scrap(fini="2020-01-01", ffin="2026-12-31", stop_event=stop_event)

    assert docs == []
    assert len(responses.calls) == 0
