import responses

from core.scrapers.families.mintrabajo import (
    ScrapMinTrabajo,
    _normalize_title,
    _parse_fecha_flexible,
    _parsear_fila,
)
from core.scrapers.registry import FAMILY_REGISTRY
from bs4 import BeautifulSoup

_MARCO_LEGAL_URL = "https://www.mintrabajo.gov.co/web/guest/marco-legal"


def test_mintrabajo_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["mintrabajo"].__name__ == "ScrapMinTrabajo"


def test_normalize_title_builds_canonical_code():
    assert _normalize_title("D", "1040", "2026") == "D_MTRA_1040_2026"


def test_normalize_title_pads_short_numbers_to_four_digits():
    assert _normalize_title("C", "96", "2026") == "C_MTRA_0096_2026"


# --- _parse_fecha_flexible: 3 formatos --------------------------------

def test_parse_fecha_formato_slash():
    assert _parse_fecha_flexible("05/08/2026") == "2026-08-05"


def test_parse_fecha_formato_slash_sin_cero_a_la_izquierda():
    assert _parse_fecha_flexible("7/06/1950") == "1950-06-07"


def test_parse_fecha_prosa_con_conector_de():
    assert _parse_fecha_flexible("24 de Agosto\xa0de 2026") == "2026-08-24"


def test_parse_fecha_prosa_sin_conector_entre_mes_y_anio():
    # Real: "29 de julio 2021" y "31 agosto 2023" -- sin "de" antes del año,
    # y a veces sin "de" entre día y mes tampoco.
    assert _parse_fecha_flexible("29 de julio 2021") == "2021-07-29"
    assert _parse_fecha_flexible("31 agosto 2023") == "2023-08-31"


def test_parse_fecha_solo_anio():
    assert _parse_fecha_flexible("2025") == "2025-01-01"


def test_parse_fecha_returns_none_for_real_site_typos():
    # Typos reales del sitio -- no se inventa la fecha.
    assert _parse_fecha_flexible("12 de Octobre de 2012") is None
    assert _parse_fecha_flexible("21 de septiemebre 2022") is None
    assert _parse_fecha_flexible("13 de julio de 202") is None
    assert _parse_fecha_flexible("18de Julio 2025") is None


# --- _parsear_fila ------------------------------------------------------

def _fila_html(tipo, norma, epigrafe, fecha, href):
    html = f"""
    <tr>
        <td data-label="Tipo de Norma">{tipo}</td>
        <td data-label="Norma">{norma}</td>
        <td data-label="Epígrafe">{epigrafe}</td>
        <td data-label="Fecha de Expedición">{fecha}</td>
        <td data-label="Acceso"><a href="{href}">Descargar</a></td>
    </tr>
    """
    return BeautifulSoup(html, "html.parser").find("tr")


def test_parsear_fila_decreto():
    tr = _fila_html(
        "Decreto", "1040 del 05 de Agosto de 2026",
        "Por el cual se reglamentan...", "05/08/2026",
        "/documents/d/guest/decreto-no-1040-del-5-de-agosto-de-2026",
    )
    fila = _parsear_fila(tr)

    assert fila["tipo"] == "Decreto"
    assert fila["letra"] == "D"
    assert fila["numero"] == "1040"
    assert fila["fecha"] == "2026-08-05"
    assert fila["epigrafe"] == "Por el cual se reglamentan..."
    assert fila["url"] == "https://www.mintrabajo.gov.co/documents/d/guest/decreto-no-1040-del-5-de-agosto-de-2026"


def test_parsear_fila_leyes_extracts_number_ignoring_embedded_type_word():
    tr = _fila_html("Leyes", "Ley 2466 de 2025", "Reforma laboral", "25 de junio de 2025", "/documents/d/guest/ley-2466")
    fila = _parsear_fila(tr)

    assert fila["letra"] == "L"
    assert fila["numero"] == "2466"
    assert fila["fecha"] == "2025-06-25"


def test_parsear_fila_circular_con_prefijo_no():
    tr = _fila_html("Circular", "No 0096", "Orientaciones laborales", "13 de Agosto de 2026", "/documents/d/guest/circular-96")
    fila = _parsear_fila(tr)

    assert fila["letra"] == "C"
    assert fila["numero"] == "0096"


def test_parsear_fila_resolves_absolute_url_unchanged():
    tr = _fila_html(
        "Decreto", "1036 del 05 de Agosto de 2026", "detalle", "05/08/2026",
        "https://www.mintrabajo.gov.co/documents/d/guest/decreto-no-1036",
    )
    fila = _parsear_fila(tr)
    assert fila["url"] == "https://www.mintrabajo.gov.co/documents/d/guest/decreto-no-1036"


def test_parsear_fila_resolves_external_host_unchanged():
    tr = _fila_html(
        "Decreto", "1227 de 2022", "detalle", "18/07/2022",
        "https://dapre.presidencia.gov.co/normativa/normativa/DECRETO%201227.pdf",
    )
    fila = _parsear_fila(tr)
    assert fila["url"] == "https://dapre.presidencia.gov.co/normativa/normativa/DECRETO%201227.pdf"


def test_parsear_fila_returns_none_for_out_of_scope_type():
    tr = _fila_html("Códigos", "Código Sustantivo del Trabajo", "", "7/06/1950", "/documents/d/guest/cst")
    assert _parsear_fila(tr) is None


def test_parsear_fila_returns_none_for_manual_type():
    tr = _fila_html("Manual", "No 0093", "Manual del inspector", "03 de Agosto de 2026", "/documents/d/guest/manual")
    assert _parsear_fila(tr) is None


def test_parsear_fila_returns_none_when_date_unparseable():
    tr = _fila_html("Resolución", "3817 de 2022", "detalle", "21 de septiemebre 2022", "/documents/d/guest/r3817")
    assert _parsear_fila(tr) is None


def test_parsear_fila_returns_none_when_less_than_five_columns():
    html = "<tr><td>Decreto</td><td>1040</td></tr>"
    tr = BeautifulSoup(html, "html.parser").find("tr")
    assert _parsear_fila(tr) is None


# --- scrap(): un único GET, filtro en memoria -----------------------------

_TABLA_HTML = """
<table><thead><tr><th>Tipo de Norma</th><th>Norma</th><th>Epígrafe</th><th>Fecha de Expedición</th><th>Acceso</th></tr></thead>
<tbody>
<tr>
    <td data-label="Tipo de Norma">Decreto</td>
    <td data-label="Norma">1040 del 05 de Agosto de 2026</td>
    <td data-label="Epígrafe">Reglamenta X</td>
    <td data-label="Fecha de Expedición">05/08/2026</td>
    <td data-label="Acceso"><a href="/documents/d/guest/decreto-1040">Descargar</a></td>
</tr>
<tr>
    <td data-label="Tipo de Norma">Resolución</td>
    <td data-label="Norma">2714 de 2020</td>
    <td data-label="Epígrafe">Medida temporal</td>
    <td data-label="Fecha de Expedición">24/01/2020</td>
    <td data-label="Acceso"><a href="/documents/d/guest/res-2714">Descargar</a></td>
</tr>
<tr>
    <td data-label="Tipo de Norma">Códigos</td>
    <td data-label="Norma">Código Sustantivo del Trabajo</td>
    <td data-label="Epígrafe"></td>
    <td data-label="Fecha de Expedición">7/06/1950</td>
    <td data-label="Acceso"><a href="/documents/d/guest/cst">Descargar</a></td>
</tr>
</tbody></table>
"""


@responses.activate
def test_scrap_parses_all_rows_and_filters_by_date_range():
    responses.add(responses.GET, _MARCO_LEGAL_URL, body=_TABLA_HTML)

    scraper = ScrapMinTrabajo()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert [d.title for d in docs] == ["D_MTRA_1040_2026"]
    assert len(responses.calls) == 1


@responses.activate
def test_scrap_excludes_out_of_scope_types_and_out_of_range_dates():
    responses.add(responses.GET, _MARCO_LEGAL_URL, body=_TABLA_HTML)

    scraper = ScrapMinTrabajo()
    docs = scraper.scrap(fini="1900-01-01", ffin="2100-12-31")

    # La fila "Códigos" nunca aparece pese al rango de fechas amplísimo.
    assert [d.title for d in docs] == ["D_MTRA_1040_2026", "R_MTRA_2714_2020"]


@responses.activate
def test_scrap_returns_empty_list_on_request_error():
    responses.add(responses.GET, _MARCO_LEGAL_URL, status=500)

    scraper = ScrapMinTrabajo()
    docs = scraper.scrap(fini="2020-01-01", ffin="2026-12-31")

    assert docs == []


@responses.activate
def test_scrap_respects_stop_event():
    import threading

    stop_event = threading.Event()
    stop_event.set()
    responses.add(responses.GET, _MARCO_LEGAL_URL, body=_TABLA_HTML)

    scraper = ScrapMinTrabajo()
    docs = scraper.scrap(fini="2020-01-01", ffin="2026-12-31", stop_event=stop_event)

    assert docs == []


@responses.activate
def test_scrap_respects_limit():
    responses.add(responses.GET, _MARCO_LEGAL_URL, body=_TABLA_HTML)

    scraper = ScrapMinTrabajo()
    docs = scraper.scrap(fini="1900-01-01", ffin="2100-12-31", limit=1)

    assert len(docs) == 1
