import datetime

from bs4 import BeautifulSoup

from core.scrapers.families.ssf import (
    _fecha_corta,
    _fecha_slash,
    _fila_circular,
    _fila_resolucion,
    _num_circular,
    _num_resolucion,
    _safe_title,
    _tablas_de_datos,
    _titulo,
)


# ---- fechas ----
def test_fecha_corta_ddmmyy_to_20yy():
    assert _fecha_corta("RESOLUCIÓN RES. 0789 DE 15-09-26") == datetime.date(2026, 9, 15)


def test_fecha_corta_none_when_absent_or_invalid():
    assert _fecha_corta("RESOLUCIÓN 1617 del 30 de diciembre de 2025") is None
    assert _fecha_corta("32-13-26") is None


def test_fecha_slash_ddmmyyyy():
    assert _fecha_slash("17/12/2025") == datetime.date(2025, 12, 17)
    assert _fecha_slash("6/10/2003") == datetime.date(2003, 10, 6)


def test_fecha_slash_none_when_absent_or_invalid():
    assert _fecha_slash("sin fecha") is None
    assert _fecha_slash("30/02/2025") is None


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
    assert doc.link == {"url": "https://www.ssf.gov.co/documents/d/guest/res-0789", "method": "GET"}
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
    assert doc.link["url"] == "https://www.ssf.gov.co/documents/d/guest/circular-0011-2025"


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
