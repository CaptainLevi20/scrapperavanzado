from core.scrapers.registry import FAMILY_REGISTRY
from core.scrapers.families.mincit import (
    _normalize_title,
    _parse_detalle,
    _parse_fecha,
    _parse_numero,
)


def test_mincit_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["mincit"].__name__ == "ScrapMINCIT"


def test_parse_fecha_converts_ddmmyyyy_to_isoformat():
    assert _parse_fecha("30/12/2025") == "2025-12-30"


def test_parse_fecha_returns_none_when_no_date_found():
    assert _parse_fecha("sin fecha") is None


def test_parse_numero_extracts_leading_number_after_tipo():
    texto = 'Resolución 365 del 30 de diciembre de 2025, "por la cual se adopta..."'
    assert _parse_numero(texto) == "365"


def test_parse_numero_extracts_number_with_leading_zero():
    texto = "Circular 018 del 27 de diciembre de 2024: distribución y administración..."
    assert _parse_numero(texto) == "018"


def test_parse_numero_returns_none_when_no_leading_number():
    assert _parse_numero("Documento sin número al inicio") is None


def test_parse_detalle_extracts_quoted_text_after_comma():
    texto = (
        'Resolución 365 del 30 de diciembre de 2025, '
        '"por la cual se adopta la determinación final".'
    )
    assert _parse_detalle(texto) == "por la cual se adopta la determinación final"


def test_parse_detalle_extracts_text_after_colon_without_quotes():
    texto = (
        "Circular 018 del 27 de diciembre de 2024: distribución y administración "
        "del contingente de exportación de azúcar."
    )
    assert _parse_detalle(texto) == (
        "distribución y administración del contingente de exportación de azúcar"
    )


def test_parse_detalle_returns_none_without_separator():
    assert _parse_detalle("Texto sin separador de descripción") is None


def test_normalize_title_builds_canonical_code():
    assert _normalize_title("R", "365", "2025") == "R_MCIT_0365_2025"


def test_normalize_title_pads_short_numbers_to_four_digits():
    assert _normalize_title("C", "18", "2024") == "C_MCIT_0018_2024"


def test_normalize_title_uses_letter_per_tipo():
    assert _normalize_title("L", "2094", "2021") == "L2094021"
    assert _normalize_title("D", "1438", "2025") == "D1438025"


from core.scrapers.families.mincit import _anios_del_slug, _mapa_anio_a_slug

_INDICE_HTML = """
<a href="/normatividad/leyes" class="active">Leyes</a>
<a href="/normatividad/leyes/2021">2021</a>
<a href="/normatividad/leyes/1990-1994">1990-1994</a>
<a href="/normatividad/leyes/1979-1989">1979-1989</a>
"""


def test_anios_del_slug_handles_single_year():
    assert _anios_del_slug("2021") == [2021]


def test_anios_del_slug_handles_range():
    assert _anios_del_slug("1990-1994") == [1990, 1991, 1992, 1993, 1994]


def test_anios_del_slug_handles_reversed_range():
    assert _anios_del_slug("1995-1990") == [1990, 1991, 1992, 1993, 1994, 1995]


def test_anios_del_slug_returns_empty_for_non_year_slug():
    assert _anios_del_slug("circulares-conjuntas") == []


def test_mapa_anio_a_slug_maps_each_year_including_ranges():
    mapa = _mapa_anio_a_slug(_INDICE_HTML, "leyes")

    assert mapa[2021] == "2021"
    assert mapa[1990] == "1990-1994"
    assert mapa[1994] == "1990-1994"
    assert mapa[1985] == "1979-1989"


def test_mapa_anio_a_slug_ignores_other_categories():
    html = '<a href="/normatividad/decretos/2021">2021</a>'
    assert _mapa_anio_a_slug(html, "leyes") == {}


from core.scrapers.families.mincit import ScrapMINCIT

_FILA_HTML = """
<table id="Listado">
  <thead>
    <th>No</th>
    <th>Archivo</th>
    <th class="text-center">Tamaño</th>
    <th class="text-center">Fecha de expedición</th>
    <th class="text-center">Fecha de publicación</th>
    <th></th>
  </thead>
  <tbody>
    <tr>
      <td class="text-center">1</td>
      <td>Resolución 365 del 30 de diciembre de 2025, "por la cual se adopta la determinación final".</td>
      <td class="text-center">1,35 MB</td>
      <td class="text-center">30/12/2025</td>
      <td class="text-center">12/02/2026</td>
      <td><a href="/getattachment/0764f7b2-98fe-4007-acf0-65689bd02404/Resolucion-365.aspx" target="_blank">Descargar</a></td>
    </tr>
  </tbody>
</table>
"""


def test_extraer_filas_parses_row_and_builds_canonical_title():
    scraper = ScrapMINCIT()
    docs = scraper._extraer_filas(_FILA_HTML, "Resolución", "R", "2026-01-01", "2026-12-31")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "R_MCIT_0365_2025"
    assert doc.title_unverified is False
    assert doc.tipo == "Resolución"
    assert doc.f_public == "2026-02-12"  # Fecha de publicación
    assert doc.f_providencia == "2025-12-30"  # Fecha de expedición
    assert doc.detalle == "por la cual se adopta la determinación final"
    assert doc.link["url"] == "https://www.mincit.gov.co/getattachment/0764f7b2-98fe-4007-acf0-65689bd02404/Resolucion-365.aspx"
    assert doc.save_path == "Ministerio de Comercio, Industria y Turismo/2026-02-12/Resolución/R_MCIT_0365_2025(extension)"


def test_extraer_filas_filters_by_publication_date_not_expedicion():
    scraper = ScrapMINCIT()
    # Fecha de expedición (30/12/2025) cae en 2025, pero Fecha de publicación
    # (12/02/2026) es la que se debe usar para el filtro — el rango pedido es
    # solo 2025, así que este documento debe quedar excluido.
    docs = scraper._extraer_filas(_FILA_HTML, "Resolución", "R", "2025-01-01", "2025-12-31")

    assert docs == []


def test_extraer_filas_marks_title_unverified_when_no_numero():
    html = _FILA_HTML.replace(
        'Resolución 365 del 30 de diciembre de 2025, "por la cual se adopta la determinación final".',
        'Documento sin número reconocible en el texto.',
    )
    scraper = ScrapMINCIT()
    docs = scraper._extraer_filas(html, "Resolución", "R", "2026-01-01", "2026-12-31")

    assert len(docs) == 1
    assert docs[0].title == "Documento sin número reconocible en el texto."
    assert docs[0].title_unverified is True


def test_extraer_filas_sanitizes_title_unverified_for_save_path():
    # Texto crudo del sitio con caracteres inválidos para una ruta de archivo:
    # "/" inyectaría un segmento de carpeta extra, ':' y '"' rompen el nombre
    # de archivo en Windows (incluido el arcname del ZIP de descarga masiva).
    html = _FILA_HTML.replace(
        'Resolución 365 del 30 de diciembre de 2025, "por la cual se adopta la determinación final".',
        'Documento/con "caracteres": invalidos|raros*.',
    )
    scraper = ScrapMINCIT()
    docs = scraper._extraer_filas(html, "Resolución", "R", "2026-01-01", "2026-12-31")

    assert len(docs) == 1
    doc = docs[0]
    # El título crudo se conserva tal cual para lectura humana.
    assert doc.title == 'Documento/con "caracteres": invalidos|raros*.'
    assert doc.title_unverified is True

    # save_path: fuente/fecha/tipo/archivo — exactamente 4 segmentos, sin que
    # el "/" del título haya inyectado un segmento extra.
    segmentos = doc.save_path.split("/")
    assert len(segmentos) == 4
    ultimo_segmento = segmentos[-1]
    assert not any(c in ultimo_segmento for c in '\\/*?:"<>|')


def test_extraer_filas_skips_row_without_download_link():
    html = _FILA_HTML.replace(
        '<a href="/getattachment/0764f7b2-98fe-4007-acf0-65689bd02404/Resolucion-365.aspx" target="_blank">Descargar</a>',
        '',
    )
    scraper = ScrapMINCIT()
    docs = scraper._extraer_filas(html, "Resolución", "R", "2026-01-01", "2026-12-31")

    assert docs == []


import responses

_INDICE_RESOLUCIONES_HTML = """
<a href="/normatividad/resoluciones" class="active">Resoluciones</a>
<a href="/normatividad/resoluciones/2026">2026</a>
"""

_INDICE_DECRETOS_HTML = """
<a href="/normatividad/decretos" class="active">Decretos</a>
<a href="/normatividad/decretos/2026">2026</a>
"""

_INDICE_VACIO_HTML = '<a href="/normatividad/circulares" class="active">Circulares</a>'

_PAGINA_RESOLUCION_HTML = """
<table id="Listado">
  <thead><th>No</th><th>Archivo</th><th>Tamaño</th><th>Fecha de expedición</th><th>Fecha de publicación</th><th></th></thead>
  <tbody>
    <tr>
      <td>1</td>
      <td>Resolución 010 del 5 de enero de 2026, "por la cual se dictan disposiciones".</td>
      <td>1 MB</td><td>05/01/2026</td><td>06/01/2026</td>
      <td><a href="/getattachment/aaa/Resolucion-010.aspx">Descargar</a></td>
    </tr>
  </tbody>
</table>
"""

_PAGINA_DECRETO_HTML = """
<table id="Listado">
  <thead><th>No</th><th>Archivo</th><th>Tamaño</th><th>Fecha de expedición</th><th>Fecha de publicación</th><th></th></thead>
  <tbody>
    <tr>
      <td>1</td>
      <td>Decreto 020 del 10 de enero de 2026, "por el cual se reglamenta algo".</td>
      <td>1 MB</td><td>10/01/2026</td><td>11/01/2026</td>
      <td><a href="/getattachment/bbb/Decreto-020.aspx">Descargar</a></td>
    </tr>
  </tbody>
</table>
"""


@responses.activate
def test_scrap_aggregates_across_categories_using_year_index():
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/resoluciones", body=_INDICE_RESOLUCIONES_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/resoluciones/2026", body=_PAGINA_RESOLUCION_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/decretos", body=_INDICE_DECRETOS_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/decretos/2026", body=_PAGINA_DECRETO_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/circulares", body=_INDICE_VACIO_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/leyes", body=_INDICE_VACIO_HTML)

    scraper = ScrapMINCIT()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert {d.title for d in docs} == {"R_MCIT_0010_2026", "D0020026"}


@responses.activate
def test_scrap_does_not_request_years_outside_range():
    indice_con_dos_anios = """
    <a href="/normatividad/resoluciones/2020">2020</a>
    <a href="/normatividad/resoluciones/2026">2026</a>
    """
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/resoluciones", body=indice_con_dos_anios)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/resoluciones/2026", body=_PAGINA_RESOLUCION_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/decretos", body=_INDICE_VACIO_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/circulares", body=_INDICE_VACIO_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/leyes", body=_INDICE_VACIO_HTML)

    scraper = ScrapMINCIT()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert len(docs) == 1
    urls_pedidas = {c.request.url for c in responses.calls}
    assert "https://www.mincit.gov.co/normatividad/resoluciones/2020" not in urls_pedidas


@responses.activate
def test_scrap_continues_past_a_failing_year_page():
    indice_con_dos_anios = """
    <a href="/normatividad/resoluciones/2025">2025</a>
    <a href="/normatividad/resoluciones/2026">2026</a>
    """
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/resoluciones", body=indice_con_dos_anios)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/resoluciones/2025", status=500)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/resoluciones/2026", body=_PAGINA_RESOLUCION_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/decretos", body=_INDICE_VACIO_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/circulares", body=_INDICE_VACIO_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/leyes", body=_INDICE_VACIO_HTML)

    progreso = []
    scraper = ScrapMINCIT()
    docs = scraper.scrap(fini="2025-01-01", ffin="2026-12-31", on_progress=progreso.append)

    assert len(docs) == 1
    assert docs[0].title == "R_MCIT_0010_2026"
    assert any("Error" in m and "resoluciones/2025" in m for m in progreso)


@responses.activate
def test_scrap_widens_lower_year_bound_to_catch_publicacion_lag():
    # Las páginas de archivo se agrupan por año de EXPEDICIÓN. Este documento fue
    # expedido el 30/12/2025 (por eso vive en la página .../resoluciones/2025) pero
    # publicado el 12/02/2026 — ya dentro del rango pedido (2026 completo). Sin el
    # margen de un año hacia atrás, la página .../resoluciones/2025 nunca se pediría
    # y el documento se perdería silenciosamente.
    indice_resoluciones = """
    <a href="/normatividad/resoluciones" class="active">Resoluciones</a>
    <a href="/normatividad/resoluciones/2025">2025</a>
    <a href="/normatividad/resoluciones/2026">2026</a>
    """
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/resoluciones", body=indice_resoluciones)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/resoluciones/2025", body=_FILA_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/resoluciones/2026", body="<html></html>")
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/decretos", body=_INDICE_VACIO_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/circulares", body=_INDICE_VACIO_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/leyes", body=_INDICE_VACIO_HTML)

    scraper = ScrapMINCIT()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert {d.title for d in docs} == {"R_MCIT_0365_2025"}


@responses.activate
def test_scrap_continues_past_a_failing_category_index():
    # Si el índice de UNA categoría falla (500), las otras 3 categorías deben
    # seguir procesándose con normalidad — el fallo no debe abortar todo el run.
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/resoluciones", body=_INDICE_RESOLUCIONES_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/resoluciones/2026", body=_PAGINA_RESOLUCION_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/decretos", body=_INDICE_DECRETOS_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/decretos/2026", body=_PAGINA_DECRETO_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/circulares", status=500)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/leyes", body=_INDICE_VACIO_HTML)

    progreso = []
    scraper = ScrapMINCIT()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31", on_progress=progreso.append)

    assert {d.title for d in docs} == {"R_MCIT_0010_2026", "D0020026"}
    assert any("Error" in m and "índice de Circular" in m for m in progreso)


def test_filters_by_publication_date_is_enabled():
    assert ScrapMINCIT.filters_by_publication_date is True
