import datetime
import unicodedata

from bs4 import BeautifulSoup

from core.scrapers.families.ssf import (
    _fecha_corta,
    _fecha_guion,
    _fecha_slash,
    _fila_circular,
    _fila_concepto,
    _fila_resolucion,
    _num_circular,
    _num_resolucion,
    _safe_title,
    _tablas_de_datos,
    _titulo,
    _titulo_concepto,
)


# ---- fechas ----
def test_fecha_corta_ddmmyy_to_20yy():
    assert _fecha_corta("RESOLUCIÓN RES. 0789 DE 15-09-26") == datetime.date(2026, 9, 15)


def test_fecha_corta_none_when_absent_or_invalid():
    assert _fecha_corta("RESOLUCIÓN 1617 del 30 de diciembre de 2025") is None
    assert _fecha_corta("32-13-26") is None


def test_fecha_corta_none_for_iso_date_left_digit_boundary():
    # una fecha ISO no debe leerse como DD-MM-YY por el borde de dígito a la izquierda
    assert _fecha_corta("2025-09-15") is None


def test_fecha_slash_ddmmyyyy():
    assert _fecha_slash("17/12/2025") == datetime.date(2025, 12, 17)
    assert _fecha_slash("6/10/2003") == datetime.date(2003, 10, 6)


def test_fecha_slash_none_when_absent_or_invalid():
    assert _fecha_slash("sin fecha") is None
    assert _fecha_slash("30/02/2025") is None


def test_fecha_slash_none_when_long_digit_run_precedes():
    # el borde de dígito a la izquierda impide leer "23/10/2003" dentro de "123/10/2003"
    assert _fecha_slash("123/10/2003") is None


# ---- número circular ----
def test_num_circular_with_ce_prefix():
    assert _num_circular("CE 00011") == ("11", "")


def test_num_circular_without_ce_prefix():
    assert _num_circular("00002") == ("2", "")


def test_num_circular_letter_suffix_uppercased():
    assert _num_circular("CE 0003A") == ("3", "A")


def test_num_circular_none_when_no_digits():
    assert _num_circular("") is None
    assert _num_circular("circular externa") is None


# ---- número resolución ----
def test_num_resolucion_from_asunto_first():
    assert _num_resolucion('Resolución 0789 del 15 de Agosto de 2026 "x"', "RESOLUCIÓN RES. 0789 DE 15-09-26") == "0789"


def test_num_resolucion_falls_back_to_documento():
    assert _num_resolucion("texto sin numero de resolucion", "RESOLUCIÓN RES. 0612 DE 03-08-26") == "0612"
    assert _num_resolucion("", "RESOLUCIÓN 1617 del 30 de diciembre de 2025") == "1617"


def test_num_resolucion_none_when_unparseable():
    assert _num_resolucion("por la cual se hace algo", "documento raro") is None


def test_num_resolucion_acepta_numero_acentuado_tras_nfc():
    # _num_resolucion normaliza a NFC, así que "Número" real lleva "ú" acentuada
    assert _num_resolucion("Resolución Número 0789 del 1 de agosto de 2026", "") == "0789"


def test_num_resolucion_acepta_no_entre_palabra_y_digitos():
    assert _num_resolucion("Resolución No. 0789 del 31 marzo de 2026", "RESOLUCIÓN No. 0789") == "0789"


def test_num_resolucion_nfd_asunto_ignora_referencia_posterior():
    # El Asunto real de la SSF llega a veces en NFD (la "ó" = "o" + U+0301) y
    # cita OTRA resolución más adelante; debe devolverse el número LÍDER (0612),
    # nunca el de la cita (0267).
    asunto = unicodedata.normalize(
        "NFD",
        'Resolución No. 0612 del 3 de agosto de 2026 '
        '"por la cual se modifica la Resolución No. 0267 de 2026"',
    )
    assert _num_resolucion(asunto, "RESOLUCIÓN RES. 0612 DE 03-08-26") == "0612"


def test_num_resolucion_nfc_asunto_con_referencia_posterior():
    asunto = 'Resolución 1617 del 30 de diciembre de 2025 "deroga la Resolución No. 0053 de 2019"'
    assert _num_resolucion(asunto, "RESOLUCIÓN 1617 del 30 de diciembre de 2025") == "1617"


# ---- título ----
def test_titulo_verified_resolucion():
    assert _titulo("R", "0789", "", 2026, "irrelevante") == ("R_SSF_0789_2026", False)


def test_titulo_verified_circular_with_letter_suffix():
    assert _titulo("C", "3", "A", 2024, "irrelevante") == ("C_SSF_0003A_2024", False)


def test_titulo_unverified_keeps_raw_trimmed():
    title, unv = _titulo("R", None, "", 2025, "RESOLUCIÓN 99 rara del sitio")
    assert unv is True
    assert title == "RESOLUCIÓN 99 rara del sitio"


def test_titulo_unverified_empty_raw_falls_back_to_documento():
    assert _titulo("C", None, "", 2025, "") == ("documento", True)


# ---- safe_title ----
def test_safe_title_replaces_invalid_and_trims():
    assert _safe_title('Doc/con "raros": x|y*  .') == "Doc-con -raros-- x-y-"
    assert len(_safe_title("z" * 300)) == 120


# ---- tables and rows ----
_RES_HTML = """
<div>
<table><tr><td>layout</td></tr></table>
<table>
  <tr><th>Documento</th><th>Asunto</th><th>Enlace</th></tr>
  <tr>
    <td>RESOLUCIÓN RES. 0789 DE 15-09-26</td>
    <td>Resolución 0789 del 15 de Agosto de 2026 "Por la cual se hace algo"</td>
    <td><a href="/documents/d/guest/res-0789">Descargar</a></td>
  </tr>
  <tr>
    <td>RESOLUCIÓN 1617 del 30 de diciembre de 2025</td>
    <td>Resolución 1617 del 30 de diciembre de 2025 "Por la cual se deroga otra"</td>
    <td><a href="https://www.ssf.gov.co/documents/d/guest/res-1617">Descargar</a></td>
  </tr>
  <tr>
    <td>RESOLUCIÓN 0053 del 5 de febrero de 2019</td>
    <td>Resolución 0053 del 5 de febrero de 2019 "vieja"</td>
    <td><a href="/documents/d/guest/res-0053">Descargar</a></td>
  </tr>
</table>
</div>
"""

_CIR_HTML = """
<table>
  <tr><th>Número</th><th>Fecha</th><th>Asunto</th><th>Adjunto</th></tr>
  <tr><td>CE 00011</td><td>17/12/2025</td><td>CANALES OFICIALES</td>
      <td><a href="/documents/d/guest/circular-0011-2025">Circular externa 00011-2025</a></td></tr>
  <tr><td>CE 0003A</td><td>28/06/2024</td><td>Ampliación del periodo</td>
      <td><a href="https://www.ssf.gov.co/documents/d/guest/circular-00003a">Circular externa 0003A</a></td></tr>
  <tr><td>00002</td><td>24/07/2026</td><td>XVIII ENCUENTRO</td>
      <td><a href="/documents/d/guest/circular-ssf-2026-00002">Circular externa SSF 2026-00002</a></td></tr>
  <tr><td>CE 0028</td><td>27/12/2010</td><td>reporte de recaudos</td>
      <td><a href="/documents/20127/47342/0028.pdf/uuid">Circular externa 0028</a></td></tr>
</table>
"""


def test_tablas_de_datos_picks_by_header_ignoring_layout():
    soup = BeautifulSoup(_RES_HTML, "html.parser")
    tablas = _tablas_de_datos(soup, {"documento", "asunto", "enlace"})
    assert len(tablas) == 1
    assert len(tablas[0].find_all("tr")) == 4  # header + 3 filas


def _rows(html, columnas):
    soup = BeautifulSoup(html, "html.parser")
    t = _tablas_de_datos(soup, columnas)[0]
    return t.find_all("tr")[1:]


def test_fila_resolucion_prefers_asunto_prose_date_and_number():
    tr = _rows(_RES_HTML, {"documento", "asunto", "enlace"})[0]
    doc = _fila_resolucion(tr, "2024-01-01", "2026-12-31", None)
    assert doc is not None
    assert doc.title == "R_SSF_0789_2026"
    assert doc.tipo == "Resolución"
    assert doc.f_public == "2026-08-15"  # del Asunto ("15 de Agosto de 2026"), NO 15-09-26
    assert doc.f_providencia == "2026-08-15"
    assert doc.link == {"url": "https://www.ssf.gov.co/documents/d/guest/res-0789", "method": "GET", "verify": False}
    assert doc.save_path == "Superintendencia del Subsidio Familiar/2026-08-15/Resolución/R_SSF_0789_2026(extension)"
    assert doc.detalle.startswith("Resolución 0789")


def test_fila_resolucion_format_2025():
    tr = _rows(_RES_HTML, {"documento", "asunto", "enlace"})[1]
    doc = _fila_resolucion(tr, "2024-01-01", "2026-12-31", None)
    assert doc.title == "R_SSF_1617_2025"
    assert doc.f_public == "2025-12-30"


def test_fila_resolucion_below_year_floor_is_dropped():
    tr = _rows(_RES_HTML, {"documento", "asunto", "enlace"})[2]  # 2019
    assert _fila_resolucion(tr, "2018-01-01", "2026-12-31", None) is None


def test_fila_circular_maps_number_date_and_link():
    tr = _rows(_CIR_HTML, {"numero", "fecha", "asunto", "adjunto"})[0]
    doc = _fila_circular(tr, "2024-01-01", "2026-12-31", None)
    assert doc.title == "C_SSF_0011_2025"
    assert doc.tipo == "Circular Externa"
    assert doc.f_public == "2025-12-17"
    assert doc.link == {
        "url": "https://www.ssf.gov.co/documents/d/guest/circular-0011-2025",
        "method": "GET",
        "verify": False,
    }


def test_fila_circular_letter_suffix():
    tr = _rows(_CIR_HTML, {"numero", "fecha", "asunto", "adjunto"})[1]
    doc = _fila_circular(tr, "2024-01-01", "2026-12-31", None)
    assert doc.title == "C_SSF_0003A_2024"


def test_fila_circular_no_ce_prefix():
    tr = _rows(_CIR_HTML, {"numero", "fecha", "asunto", "adjunto"})[2]
    doc = _fila_circular(tr, "2024-01-01", "2026-12-31", None)
    assert doc.title == "C_SSF_0002_2026"


def test_fila_circular_old_row_dropped_by_year_floor():
    tr = _rows(_CIR_HTML, {"numero", "fecha", "asunto", "adjunto"})[3]  # 2010
    assert _fila_circular(tr, "2009-01-01", "2026-12-31", None) is None


def test_fila_circular_outside_requested_range_dropped():
    tr = _rows(_CIR_HTML, {"numero", "fecha", "asunto", "adjunto"})[0]  # 2025-12-17
    assert _fila_circular(tr, "2024-01-01", "2025-06-30", None) is None


def test_fila_resolucion_unverified_when_no_number():
    html = _RES_HTML.replace(
        "RESOLUCIÓN RES. 0789 DE 15-09-26", "DOCUMENTO SIN NUMERO 15-09-26"
    ).replace(
        'Resolución 0789 del 15 de Agosto de 2026 "Por la cual se hace algo"',
        "Acto del 15 de Agosto de 2026 sin numero reconocible",
    )
    tr = _rows(html, {"documento", "asunto", "enlace"})[0]
    doc = _fila_resolucion(tr, "2024-01-01", "2026-12-31", None)
    assert doc.title_unverified is True
    assert doc.title == "DOCUMENTO SIN NUMERO 15-09-26"
    segs = doc.save_path.split("/")
    assert len(segs) == 4 and not any(c in segs[-1] for c in '\\/*?:"<>|')


def test_fila_circular_without_date_is_dropped_and_warns():
    html = _CIR_HTML.replace("17/12/2025", "sin fecha")
    tr = _rows(html, {"numero", "fecha", "asunto", "adjunto"})[0]
    avisos = []
    assert _fila_circular(tr, "2024-01-01", "2026-12-31", avisos.append) is None
    assert any("sin fecha" in m.lower() for m in avisos)


_RES_HTML_FECHA_CORTA = """
<table>
  <tr><th>Documento</th><th>Asunto</th><th>Enlace</th></tr>
  <tr>
    <td>RESOLUCIÓN RES. 0500 DE 07-03-25</td>
    <td>Resolución 0500 por la cual se adopta una decisión</td>
    <td><a href="/documents/d/guest/res-0500">Descargar</a></td>
  </tr>
</table>
"""


def test_fila_resolucion_falls_back_to_documento_fecha_corta_when_asunto_has_no_prose_date():
    # Asunto sin fecha en prosa (solo número) → se usa `or _fecha_corta(documento)`
    tr = _rows(_RES_HTML_FECHA_CORTA, {"documento", "asunto", "enlace"})[0]
    doc = _fila_resolucion(tr, "2024-01-01", "2026-12-31", None)
    assert doc is not None
    assert doc.title == "R_SSF_0500_2025"
    assert doc.f_public == "2025-03-07"


_RES_HTML_SIN_FECHA = """
<table>
  <tr><th>Documento</th><th>Asunto</th><th>Enlace</th></tr>
  <tr>
    <td>RESOLUCIÓN RES. 0501 SIN FECHA RECONOCIBLE</td>
    <td>Resolución 0501 por la cual se adopta otra decisión</td>
    <td><a href="/documents/d/guest/res-0501">Descargar</a></td>
  </tr>
</table>
"""


def test_fila_resolucion_without_parseable_date_is_dropped_and_warns():
    tr = _rows(_RES_HTML_SIN_FECHA, {"documento", "asunto", "enlace"})[0]
    avisos = []
    assert _fila_resolucion(tr, "2024-01-01", "2026-12-31", avisos.append) is None
    assert any("sin fecha" in m.lower() for m in avisos)


# ---- orquestación scrap() + registro (Task 3) ----
import threading  # noqa: E402

import responses  # noqa: E402

from core.scrapers.registry import FAMILY_REGISTRY  # noqa: E402
from core.scrapers.families.ssf import ScrapSSF  # noqa: E402

_RES_URL = "https://www.ssf.gov.co/web/guest/resoluciones2"
_CIR_URL = "https://www.ssf.gov.co/web/guest/normativa-circulares"

_RES_PAGE = """<html><body>
<table><tr><th>x</th></tr><tr><td>layout</td></tr></table>
<table>
  <tr><th>Documento</th><th>Asunto</th><th>Enlace</th></tr>
  <tr><td>RESOLUCIÓN RES. 0789 DE 15-09-26</td>
      <td>Resolución 0789 del 15 de Agosto de 2026 "x"</td>
      <td><a href="/documents/d/guest/res-0789">D</a></td></tr>
  <tr><td>RESOLUCIÓN 0053 del 5 de febrero de 2019</td>
      <td>Resolución 0053 del 5 de febrero de 2019 "vieja"</td>
      <td><a href="/documents/d/guest/res-0053">D</a></td></tr>
</table></body></html>
"""

_CIR_PAGE = """<html><body>
<table>
  <tr><th>Número</th><th>Fecha</th><th>Asunto</th><th>Adjunto</th></tr>
  <tr><td>CE 00011</td><td>17/12/2025</td><td>CANALES</td>
      <td><a href="/documents/d/guest/cir-0011">A</a></td></tr>
</table></body></html>
"""


def test_ssf_is_registered():
    import core.scrapers.families  # noqa: F401
    assert FAMILY_REGISTRY["ssf"].__name__ == "ScrapSSF"


def test_filters_by_publication_date_is_enabled():
    assert ScrapSSF.filters_by_publication_date is True


@responses.activate
def test_scrap_collects_both_sections_and_applies_year_floor():
    responses.add(responses.GET, _RES_URL, body=_RES_PAGE)
    responses.add(responses.GET, _CIR_URL, body=_CIR_PAGE)

    docs = ScrapSSF().scrap(fini="2018-01-01", ffin="2026-12-31")
    titles = {d.title for d in docs}
    assert titles == {"R_SSF_0789_2026", "C_SSF_0011_2025"}  # la resolución de 2019 cae por el piso 2024


@responses.activate
def test_scrap_respects_requested_range():
    responses.add(responses.GET, _RES_URL, body=_RES_PAGE)
    responses.add(responses.GET, _CIR_URL, body=_CIR_PAGE)

    docs = ScrapSSF().scrap(fini="2026-01-01", ffin="2026-12-31")
    assert {d.title for d in docs} == {"R_SSF_0789_2026"}  # la circular es de 2025


@responses.activate
def test_scrap_continues_when_one_section_fails():
    responses.add(responses.GET, _RES_URL, status=500)
    responses.add(responses.GET, _CIR_URL, body=_CIR_PAGE)

    progreso = []
    docs = ScrapSSF().scrap(fini="2024-01-01", ffin="2026-12-31", on_progress=progreso.append)
    assert {d.title for d in docs} == {"C_SSF_0011_2025"}
    assert any("Error" in m for m in progreso)


@responses.activate
def test_scrap_stops_on_stop_event():
    responses.add(responses.GET, _RES_URL, body=_RES_PAGE)
    responses.add(responses.GET, _CIR_URL, body=_CIR_PAGE)
    ev = threading.Event()
    ev.set()
    docs = ScrapSSF().scrap(fini="2024-01-01", ffin="2026-12-31", stop_event=ev)
    assert docs == []
    assert len(responses.calls) == 0


_HEADER_CHANGED_PAGE = """<html><body>
<table>
  <tr><th>Otra</th><th>Cosa</th></tr>
  <tr><td>foo</td><td>bar</td></tr>
</table></body></html>
"""


@responses.activate
def test_scrap_warns_when_no_data_table_found():
    # Si la SSF renombra columnas o reestructura el encabezado, la sección no
    # rinde filas: scrap() debe devolver [] Y avisar por on_progress con "Error"
    # y el nombre del tipo (antes se devolvía 0 en silencio).
    responses.add(responses.GET, _RES_URL, body=_HEADER_CHANGED_PAGE)
    responses.add(responses.GET, _CIR_URL, body=_HEADER_CHANGED_PAGE)

    progreso = []
    docs = ScrapSSF().scrap(fini="2024-01-01", ffin="2026-12-31", on_progress=progreso.append)
    assert docs == []
    assert any("Error" in m and "Resolución" in m for m in progreso)
    assert any("Error" in m and "Circular Externa" in m for m in progreso)


_RES_PAGE_DOS_EN_RANGO = """<html><body>
<table>
  <tr><th>Documento</th><th>Asunto</th><th>Enlace</th></tr>
  <tr><td>RESOLUCIÓN RES. 0789 DE 15-09-26</td>
      <td>Resolución 0789 del 15 de Agosto de 2026 "x"</td>
      <td><a href="/documents/d/guest/res-0789">D</a></td></tr>
  <tr><td>RESOLUCIÓN RES. 0790 DE 16-09-26</td>
      <td>Resolución 0790 del 16 de Agosto de 2026 "y"</td>
      <td><a href="/documents/d/guest/res-0790">D</a></td></tr>
</table></body></html>
"""


@responses.activate
def test_scrap_limit_truncates_results():
    responses.add(responses.GET, _RES_URL, body=_RES_PAGE_DOS_EN_RANGO)

    docs = ScrapSSF().scrap(fini="2024-01-01", ffin="2026-12-31", limit=1)
    assert len(docs) == 1


def test_seed_families_dict_has_ssf_entry():
    from core.seed import _FAMILIES
    assert "ssf" in _FAMILIES
    display_name, description = _FAMILIES["ssf"]
    assert display_name == "Superintendencia del Subsidio Familiar"
    assert "esolucion" in description or "esoluciones" in description
    assert "irculares" in description


# ============================================================================
# Conceptos jurídicos (juridica.ssf.gov.co) — tercera sección de la familia
# ============================================================================

from core.scrapers.families.ssf import _buscar_conceptos  # noqa: E402

_JURIDICA_URL = "https://juridica.ssf.gov.co/"


# ---- _fecha_guion (DD-MM-AAAA, año de 4 dígitos) ----
def test_fecha_guion_ddmmyyyy():
    assert _fecha_guion("17-07-2024") == datetime.date(2024, 7, 17)
    assert _fecha_guion("Publicado el 04-12-2019 por la oficina") == datetime.date(2019, 12, 4)


def test_fecha_guion_none_when_absent_or_invalid():
    assert _fecha_guion("sin fecha") is None
    assert _fecha_guion("32-01-2024") is None


def test_fecha_guion_does_not_match_two_digit_year():
    # el formato corto DD-MM-AA no debe colarse como AAAA
    assert _fecha_guion("15-09-26") is None


# ---- _titulo_concepto (número tomado del NOMBRE DEL PDF de respuesta) ----
_BLOB = "https://juridica.blob.core.windows.net/juridica-documentos"


def test_titulo_concepto_from_pdf_filename():
    assert _titulo_concepto(f"{_BLOB}/2-2024-15780.pdf") == ("CTO_SSF_15780_2024", False)


def test_titulo_concepto_keeps_leading_zeros_verbatim_and_accepts_prefix_1():
    # "0117480" y "117480" son radicados distintos en este sitio: no se normaliza
    assert _titulo_concepto(f"{_BLOB}/1-2019-0117480.pdf") == ("CTO_SSF_0117480_2019", False)


def test_titulo_concepto_collapses_double_pdf_extension():
    assert _titulo_concepto(f"{_BLOB}/2-2026-25.pdf.pdf") == ("CTO_SSF_25_2026", False)


def test_titulo_concepto_distinguishes_padded_from_unpadded_consecutive():
    a, _ = _titulo_concepto(f"{_BLOB}/2-2024-5949.pdf")
    b, _ = _titulo_concepto(f"{_BLOB}/2-2024-005949.pdf")
    assert a == "CTO_SSF_5949_2024" and b == "CTO_SSF_005949_2024" and a != b


def test_titulo_concepto_unverified_when_malformed():
    # año de 3 dígitos (error de tipeo real del sitio)
    assert _titulo_concepto(f"{_BLOB}/2-209-087668.pdf") == ("2-209-087668", True)
    assert _titulo_concepto("") == ("concepto", True)


# ---- _fila_concepto ----
_CONCEPTO_HTML = """
<table>
  <tr><th>Radicado</th><th>Conclusión</th><th>Fuentes Formales</th><th>Fecha</th>
      <th>Tema</th><th>Sub Tema</th><th>Palabras clave</th><th>Link</th></tr>
  <tr>
    <td>2-2024-15780</td>
    <td>Las cajas de compensación familiar pueden pagar el subsidio en especie</td>
    <td>Artículos 1, 5, 41 de la Ley 21 de 1982</td>
    <td>17-07-2024</td>
    <td>Subsidio familiar</td>
    <td>Subsidio familiar en especie</td>
    <td>becas educativas, autonomía administrativa</td>
    <td><a href="https://juridica.blob.core.windows.net/juridica-documentos/2-2024-15780.pdf"
           target="_blank">Ver PDF</a></td>
  </tr>
  <tr>
    <td>1-2019-017014</td>
    <td>A la cuota monetaria del subsidio familiar tendrán derecho los trabajadores</td>
    <td>Ley 21 de 1982 artículo 54</td>
    <td>04-12-2019</td>
    <td>Subsidio Familiar</td>
    <td>Cuota monetaria</td>
    <td>cuota, subsidio</td>
    <td><a href="https://juridica.blob.core.windows.net/juridica-documentos/1-2019-017014.pdf">Ver PDF</a></td>
  </tr>
  <tr>
    <td>2-2014-000900</td>
    <td>Concepto viejo anterior al piso de cobertura</td>
    <td>N/A</td>
    <td>10-05-2014</td>
    <td>Otros</td><td>Otros</td><td>viejo</td>
    <td><a href="https://juridica.blob.core.windows.net/juridica-documentos/2-2014-000900.pdf">Ver PDF</a></td>
  </tr>
  <tr>
    <td>2-209-087668</td>
    <td>Concepto con radicado malformado (año de 3 dígitos)</td>
    <td>N/A</td>
    <td>20-08-2021</td>
    <td>Otros</td><td>Otros</td><td>malformado</td>
    <td><a href="https://juridica.blob.core.windows.net/juridica-documentos/2-209-087668.pdf">Ver PDF</a></td>
  </tr>
  <tr>
    <td>2-2023-000111</td>
    <td>Concepto sin fecha reconocible en su celda</td>
    <td>N/A</td>
    <td>fecha ilegible</td>
    <td>Otros</td><td>Otros</td><td>sinfecha</td>
    <td><a href="https://juridica.blob.core.windows.net/juridica-documentos/2-2023-000111.pdf">Ver PDF</a></td>
  </tr>
  <tr>
    <td>1-2025-019827</td>
    <td>La columna trae el radicado de la consulta (1-), pero el PDF es la respuesta (2-)</td>
    <td>Ley 21 de 1982</td>
    <td>10-09-2025</td>
    <td>Subsidio familiar</td><td>Especie</td><td>consulta</td>
    <td><a href="https://juridica.blob.core.windows.net/juridica-documentos/2-2025-019142.pdf">Ver PDF</a></td>
  </tr>
</table>
"""


def _concepto_rows():
    soup = BeautifulSoup(_CONCEPTO_HTML, "html.parser")
    cols = {"radicado", "conclusion", "fuentes formales", "fecha", "tema", "sub tema", "palabras clave", "link"}
    return _tablas_de_datos(soup, cols)[0].find_all("tr")[1:]


def test_fila_concepto_maps_all_fields():
    tr = _concepto_rows()[0]
    doc = _fila_concepto(tr, "2015-01-01", "2026-12-31", None)
    assert doc is not None
    assert doc.title == "CTO_SSF_15780_2024"
    assert doc.title_unverified is False
    assert doc.tipo == "Concepto"
    assert doc.f_public == "2024-07-17"
    assert doc.f_providencia == "2024-07-17"
    # juridica.blob.core.windows.net tiene TLS válido -> sin verify=False
    assert doc.link == {
        "url": "https://juridica.blob.core.windows.net/juridica-documentos/2-2024-15780.pdf",
        "method": "GET",
    }
    # el detalle guarda el radicado de la columna + la conclusión
    assert "Radicado: 2-2024-15780" in doc.detalle
    assert "Las cajas de compensación familiar" in doc.detalle
    assert doc.save_path == (
        "Superintendencia del Subsidio Familiar/2024-07-17/Concepto/CTO_SSF_15780_2024(extension)"
    )


def test_fila_concepto_title_comes_from_pdf_not_from_radicado_cell():
    tr = _concepto_rows()[5]  # celda 1-2025-019827, PDF 2-2025-019142
    doc = _fila_concepto(tr, "2015-01-01", "2026-12-31", None)
    assert doc is not None
    assert doc.title == "CTO_SSF_019142_2025"          # del nombre del PDF
    assert "Radicado: 1-2025-019827" in doc.detalle    # la consulta queda registrada
    assert doc.link["url"].endswith("/2-2025-019142.pdf")


def test_fila_concepto_below_2015_floor_is_dropped():
    tr = _concepto_rows()[2]  # 2014
    assert _fila_concepto(tr, "2010-01-01", "2026-12-31", None) is None


def test_fila_concepto_keeps_rows_from_2015_onward_not_just_2024():
    # el piso de Conceptos es 2015, distinto al 2024 de Resoluciones/Circulares
    tr = _concepto_rows()[1]  # 2019
    doc = _fila_concepto(tr, "2015-01-01", "2026-12-31", None)
    assert doc is not None
    assert doc.title == "CTO_SSF_017014_2019"


def test_fila_concepto_outside_requested_range_is_dropped():
    tr = _concepto_rows()[0]  # 2024-07-17
    assert _fila_concepto(tr, "2015-01-01", "2024-06-30", None) is None


def test_fila_concepto_malformed_radicado_still_ingested_unverified():
    tr = _concepto_rows()[3]  # 2-209-087668, fecha 2021
    doc = _fila_concepto(tr, "2015-01-01", "2026-12-31", None)
    assert doc is not None
    assert doc.title_unverified is True
    assert doc.title == "2-209-087668"
    assert doc.f_public == "2021-08-20"
    segs = doc.save_path.split("/")
    assert len(segs) == 4 and not any(c in segs[-1] for c in '\\/*?:"<>|')


def test_fila_concepto_without_parseable_date_is_dropped_and_warns():
    tr = _concepto_rows()[4]
    avisos = []
    assert _fila_concepto(tr, "2015-01-01", "2026-12-31", avisos.append) is None
    assert any("concepto" in m.lower() and "fecha" in m.lower() for m in avisos)


# ---- _buscar_conceptos: ida y vuelta de tres pasos ----
_JUR_HOME = """<html><body>
<form method="post">
  <p>Fecha de Radicación</p>
  <input name="__RequestVerificationToken" type="hidden" value="TOKEN-abc123" />
</form>
</body></html>"""

_JUR_RESULTS = """<html><body>
<table id="tblDatos">
  <tr><th>Radicado</th><th>Conclusión</th><th>Fuentes Formales</th><th>Fecha</th>
      <th>Tema</th><th>Sub Tema</th><th>Palabras clave</th><th>Link</th></tr>
  <tr><td>2-2025-019142</td><td>Conclusión de prueba</td><td>Ley X</td><td>03-03-2025</td>
      <td>Tema</td><td>Sub</td><td>kw</td>
      <td><a href="https://juridica.blob.core.windows.net/juridica-documentos/2-2025-019142.pdf">Ver PDF</a></td></tr>
</table></body></html>"""


@responses.activate
def test_buscar_conceptos_three_step_flow_and_floors_fechadesde_at_2015():
    responses.add(responses.GET, _JURIDICA_URL, body=_JUR_HOME)
    responses.add(responses.POST, _JURIDICA_URL, status=302, headers={"Location": "/"})
    responses.add(responses.GET, _JURIDICA_URL, body=_JUR_RESULTS)

    html = _buscar_conceptos("2010-01-01", "2026-12-31")

    assert "tblDatos" in html
    assert responses.calls[0].request.method == "GET"
    body = responses.calls[1].request.body
    assert responses.calls[1].request.method == "POST"
    assert "fechaDesde=2015-01-01" in body          # piso 2015, aunque fini sea 2010
    assert "fechaHasta=2026-12-31" in body
    assert "__RequestVerificationToken=TOKEN-abc123" in body
    assert "Buscar=" in body and "Radicado=" in body
    assert responses.calls[2].request.method == "GET"


@responses.activate
def test_buscar_conceptos_uses_fini_when_later_than_2015():
    responses.add(responses.GET, _JURIDICA_URL, body=_JUR_HOME)
    responses.add(responses.POST, _JURIDICA_URL, status=302, headers={"Location": "/"})
    responses.add(responses.GET, _JURIDICA_URL, body=_JUR_RESULTS)

    _buscar_conceptos("2026-01-01", "2026-01-31")
    assert "fechaDesde=2026-01-01" in responses.calls[1].request.body


# ---- scrap() con la sección de Conceptos integrada ----
_RES_PAGE_CONC = _RES_PAGE
_CIR_PAGE_CONC = _CIR_PAGE


@responses.activate
def test_scrap_includes_conceptos_section():
    responses.add(responses.GET, _RES_URL, body=_RES_PAGE_CONC)
    responses.add(responses.GET, _CIR_URL, body=_CIR_PAGE_CONC)
    responses.add(responses.GET, _JURIDICA_URL, body=_JUR_HOME)
    responses.add(responses.POST, _JURIDICA_URL, status=302, headers={"Location": "/"})
    responses.add(responses.GET, _JURIDICA_URL, body=_JUR_RESULTS)

    progreso = []
    docs = ScrapSSF().scrap(fini="2015-01-01", ffin="2026-12-31", on_progress=progreso.append)
    conceptos = [d for d in docs if d.tipo == "Concepto"]
    assert [d.title for d in conceptos] == ["CTO_SSF_019142_2025"]
    assert any("Concepto" in m for m in progreso)


_JUR_RESULTS_DUP = """<html><body>
<table id="tblDatos">
  <tr><th>Radicado</th><th>Conclusión</th><th>Fuentes Formales</th><th>Fecha</th>
      <th>Tema</th><th>Sub Tema</th><th>Palabras clave</th><th>Link</th></tr>
  <tr><td>1-2025-022711</td><td>Responde a una consulta</td><td>Ley X</td><td>10-11-2025</td>
      <td>T</td><td>S</td><td>k</td>
      <td><a href="https://juridica.blob.core.windows.net/juridica-documentos/2-2025-024171.pdf">Ver PDF</a></td></tr>
  <tr><td>1-2025-022721</td><td>Responde a otra consulta con el mismo concepto</td><td>Ley X</td><td>10-11-2025</td>
      <td>T</td><td>S</td><td>k</td>
      <td><a href="https://juridica.blob.core.windows.net/juridica-documentos/2-2025-024171.pdf">Ver PDF</a></td></tr>
</table></body></html>"""


@responses.activate
def test_scrap_conceptos_dedupes_rows_that_point_to_the_same_pdf():
    # el sitio lista el mismo PDF de concepto en dos filas (una por cada consulta
    # que responde); debe entrar una sola vez.
    responses.add(responses.GET, _RES_URL, body=_RES_PAGE_CONC)
    responses.add(responses.GET, _CIR_URL, body=_CIR_PAGE_CONC)
    responses.add(responses.GET, _JURIDICA_URL, body=_JUR_HOME)
    responses.add(responses.POST, _JURIDICA_URL, status=302, headers={"Location": "/"})
    responses.add(responses.GET, _JURIDICA_URL, body=_JUR_RESULTS_DUP)

    docs = ScrapSSF().scrap(fini="2015-01-01", ffin="2026-12-31")
    conceptos = [d for d in docs if d.tipo == "Concepto"]
    assert [d.title for d in conceptos] == ["CTO_SSF_024171_2025"]


@responses.activate
def test_scrap_warns_when_concepto_table_missing():
    responses.add(responses.GET, _RES_URL, body=_RES_PAGE_CONC)
    responses.add(responses.GET, _CIR_URL, body=_CIR_PAGE_CONC)
    responses.add(responses.GET, _JURIDICA_URL, body=_JUR_HOME)
    responses.add(responses.POST, _JURIDICA_URL, status=302, headers={"Location": "/"})
    responses.add(responses.GET, _JURIDICA_URL, body=_HEADER_CHANGED_PAGE)

    progreso = []
    docs = ScrapSSF().scrap(fini="2015-01-01", ffin="2026-12-31", on_progress=progreso.append)
    assert [d for d in docs if d.tipo == "Concepto"] == []
    assert any("Error" in m and "Concepto" in m for m in progreso)


@responses.activate
def test_scrap_continues_when_conceptos_fetch_fails():
    responses.add(responses.GET, _RES_URL, body=_RES_PAGE_CONC)
    responses.add(responses.GET, _CIR_URL, body=_CIR_PAGE_CONC)
    responses.add(responses.GET, _JURIDICA_URL, status=500)

    progreso = []
    docs = ScrapSSF().scrap(fini="2024-01-01", ffin="2026-12-31", on_progress=progreso.append)
    assert {d.title for d in docs} == {"R_SSF_0789_2026", "C_SSF_0011_2025"}
    assert any("Error" in m and "Concepto" in m for m in progreso)
