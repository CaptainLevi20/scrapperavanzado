from core.scrapers.families.snr import (
    _parse_codigo,
    _resultados_total,
    _safe_title,
    _tarjeta_a_doc,
    _tarjetas,
    _titulo,
)


# ---- _parse_codigo ----
def test_parse_codigo_circular():
    assert _parse_codigo('CIR-2026-000348-4 del 03 de septiembre del 2026 "x"') == ("C", 348, 2026)


def test_parse_codigo_resolucion_five_digit_consecutive():
    assert _parse_codigo('RES-2026-021492-6 del 20 de agosto de 2026 "x"') == ("R", 21492, 2026)


def test_parse_codigo_none_for_old_format():
    assert _parse_codigo("RES.445-2019EXPTE.407-2017") is None
    assert _parse_codigo("Circular informativa sin código") is None
    assert _parse_codigo("") is None


# ---- _titulo ----
def test_titulo_verified_circular():
    assert _titulo(("C", 348, 2026), "irrelevante") == ("C_SNR_0348_2026", False)


def test_titulo_verified_resolucion_keeps_five_digits():
    assert _titulo(("R", 21492, 2026), "irrelevante") == ("R_SNR_21492_2026", False)


def test_titulo_unverified_keeps_raw_trimmed():
    title, unv = _titulo(None, "RES.445-2019 texto libre del sitio")
    assert unv is True
    assert title == "RES.445-2019 texto libre del sitio"


def test_titulo_unverified_empty_falls_back_to_documento():
    assert _titulo(None, "   ") == ("documento", True)


# ---- _resultados_total ----
def test_resultados_total_reads_and_strips_separators():
    assert _resultados_total("<div>Resultados 355</div>") == 355
    assert _resultados_total("Resultados 10.901 circulares") == 10901
    assert _resultados_total("Resultados 2,634") == 2634


def test_resultados_total_minus_one_when_absent():
    assert _resultados_total("<html>sin conteo</html>") == -1


# ---- _safe_title ----
def test_safe_title_sanitizes_and_trims():
    assert _safe_title('Doc/con "raros": x|y*  .') == "Doc-con -raros-- x-y-"
    assert len(_safe_title("z" * 300)) == 120


# ---- _tarjetas ----
_HTML = """
<ul class="docs_download">
  <li>
    <div class="download">
      <!--<a href="https://servicios.supernotariado.gov.co/files/snrcirculares/circular-348-x.pdf"> -->
      <img src="x"><!--<br>Descargar</a> --><br><span>0 Mg</span>
    </div>
    <div class="contenido_download">
      <span class="lettercap"></span> 348<br>
      <a href="https://servicios.supernotariado.gov.co/files/snrcirculares/circular-348-x.pdf" rel="nofollow">CIR-2026-000348-4 del 03 de septiembre del 2026 "Informacion de autos"</a><br>
      <span>Publicación: 2026-09-03</span><br><span>Desfijacion: 2026-09-14</span>
    </div>
    <div class="border-download"></div>
  </li>
  <li>
    <div class="download"><img src="x"><br><span>0 Mg</span></div>
    <div class="contenido_download"><span class="lettercap"></span> 20779<br>
      Notificación por aviso – Resolución No. RES-2026-020779-6 del 13 de agosto de 2026 " Por medio de la cual..."<br>
      <span>Publicación: 2026-08-28</span>
    </div>
  </li>
  <li>
    <div class="contenido_download"><span class="lettercap"></span> 445<br>
      <a href="https://servicios.supernotariado.gov.co/files/content/resoluciones/2019/179715-RES.445-2019.pdf">RES.445-2019EXPTE.407-2017 sin código canónico</a><br>
      <span>Publicación: 2019-05-10</span>
    </div>
  </li>
</ul>
<div class="paginacion_top">Resultados 355</div>
"""


def test_tarjetas_parses_cards_with_link_and_counts_the_rest():
    cards, sin_pdf = _tarjetas(_HTML)
    assert len(cards) == 2  # la circular y la RES.445; la "notificación por aviso" no tiene <a>
    assert sin_pdf == 1
    assert cards[0]["titulo_txt"].startswith("CIR-2026-000348-4 del 03 de septiembre del 2026")
    assert cards[0]["publicacion"] == "2026-09-03"
    assert cards[0]["pdf_url"].endswith("/circular-348-x.pdf")


def test_tarjetas_empty_html():
    assert _tarjetas("") == ([], 0)


# ---- _tarjeta_a_doc ----
def test_tarjeta_a_doc_verified_circular_uses_prose_date():
    cards, _ = _tarjetas(_HTML)
    doc = _tarjeta_a_doc(cards[0], "Circular", "2015-01-01", "2026-12-31", None)
    assert doc is not None
    assert doc.title == "C_SNR_0348_2026"
    assert doc.title_unverified is False
    assert doc.tipo == "Circular"
    assert doc.f_public == "2026-09-03"       # "del 03 de septiembre del 2026"
    assert doc.f_providencia == "2026-09-03"
    assert doc.link == {"url": "https://servicios.supernotariado.gov.co/files/snrcirculares/circular-348-x.pdf", "method": "GET"}
    assert doc.save_path == (
        "Superintendencia de Notariado y Registro/2026-09-03/Circular/C_SNR_0348_2026(extension)"
    )


def test_tarjeta_a_doc_falls_back_to_publicacion_date_when_no_prose():
    card = {"titulo_txt": "Circular sin fecha en prosa", "publicacion": "2025-07-01",
            "pdf_url": "https://servicios.supernotariado.gov.co/files/x.pdf"}
    doc = _tarjeta_a_doc(card, "Circular", "2015-01-01", "2026-12-31", None)
    assert doc is not None
    assert doc.f_public == "2025-07-01"
    assert doc.title_unverified is True  # sin código


def test_tarjeta_a_doc_unverified_for_old_code():
    cards, _ = _tarjetas(_HTML)
    doc = _tarjeta_a_doc(cards[1], "Resolución", "2015-01-01", "2026-12-31", None)  # RES.445-2019, pub 2019-05-10
    assert doc.title_unverified is True
    assert doc.title == "RES.445-2019EXPTE.407-2017 sin código canónico"
    assert doc.f_public == "2019-05-10"
    segs = doc.save_path.split("/")
    assert len(segs) == 4 and not any(c in segs[-1] for c in '\\/*?:"<>|')


def test_tarjeta_a_doc_below_year_floor_is_dropped():
    card = {"titulo_txt": "CIR-2013-000005-4 del 10 de enero de 2013", "publicacion": "2013-01-10",
            "pdf_url": "https://x/y.pdf"}
    assert _tarjeta_a_doc(card, "Circular", "2010-01-01", "2026-12-31", None) is None


def test_tarjeta_a_doc_outside_requested_range_is_dropped():
    cards, _ = _tarjetas(_HTML)
    assert _tarjeta_a_doc(cards[0], "Circular", "2015-01-01", "2026-08-31", None) is None  # doc es 2026-09-03


def test_tarjeta_a_doc_without_any_date_is_dropped_and_warns():
    card = {"titulo_txt": "Circular sin ninguna fecha", "publicacion": None, "pdf_url": "https://x/y.pdf"}
    avisos = []
    assert _tarjeta_a_doc(card, "Circular", "2015-01-01", "2026-12-31", avisos.append) is None
    assert any("sin fecha" in m.lower() for m in avisos)
