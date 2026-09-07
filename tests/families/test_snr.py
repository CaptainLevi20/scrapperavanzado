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
    assert doc.link == {"url": "https://servicios.supernotariado.gov.co/files/snrcirculares/circular-348-x.pdf", "method": "GET", "verify": False}
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


import responses

from core.scrapers.families.snr import _buscar, _enumerar_categoria

_CIR_URL = "https://www.supernotariado.gov.co/transparencia/normatividad/circulares/"
_RES_URL = "https://www.supernotariado.gov.co/transparencia/normatividad/Resoluciones/"


def _page(cards_html, total):
    return f'<ul class="docs_download">{cards_html}</ul><div>Resultados {total}</div>'


def _card(codigo, pub, url):
    return (
        f'<li><div class="contenido_download"><span class="lettercap"></span> x<br>'
        f'<a href="{url}">{codigo} del 03 de septiembre del 2026 "t"</a><br>'
        f'<span>Publicación: {pub}</span></div></li>'
    )


def test_buscar_posts_r_param_and_reads_total():
    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, _CIR_URL, body=_page(_card("CIR-2026-000001-4", "2026-01-05", "https://x/1.pdf"), 1))
        session = __import__("requests").Session()
        total, html = _buscar(session, "circulares", "2026")
        # responses 0.26.x limpia rsps.calls al salir del context manager -> comprobar dentro
        assert rsps.calls[0].request.body == "r=2026"
    assert total == 1
    assert "docs_download" in html


@responses.activate
def test_enumerar_uses_year_search_directly_when_it_returns_everything():
    # caso Resoluciones: r=2026 devuelve MÁS que _UMBRAL -> se usa directo, sin recursión
    cards = "".join(_card(f"RES-2026-{i:06d}-6", "2026-06-01", f"https://x/r{i}.pdf") for i in range(1, 25))
    responses.add(responses.POST, _RES_URL, body=_page(cards, 24))
    session = __import__("requests").Session()
    got = _enumerar_categoria(session, "Resoluciones", "R", "2026-01-01", "2026-12-31", None, None)
    assert len(got) == 24
    assert sum(1 for c in responses.calls if "Resoluciones" in c.request.url) == 1  # un solo POST


@responses.activate
def test_enumerar_recurses_by_prefix_when_year_search_is_capped():
    # Catálogo falso: 60 circulares de 2026 en 3 bloques de 100 (20 c/u, cada
    # bloque > _UMBRAL para forzar la recursión hasta bloques de 10).
    catalogo = list(range(1, 21)) + list(range(150, 170)) + list(range(300, 320))  # 20+20+20 = 60

    def cb(request):
        term = request.body.split("r=", 1)[1]
        if term == "2026":
            nums = catalogo
        elif term.startswith("CIR-2026-"):
            pref = term[len("CIR-2026-"):]
            nums = [n for n in catalogo if f"{n:06d}".startswith(pref)]
        else:
            return (200, {}, _page("", 0))
        resultados = len(nums)
        mostrados = nums if resultados <= 18 else nums[:18]  # el listado corta a ~18
        cards = "".join(_card(f"CIR-2026-{n:06d}-4", "2026-09-01", f"https://x/c{n}.pdf") for n in mostrados)
        return (200, {}, _page(cards, resultados))

    responses.add_callback(responses.POST, _CIR_URL, callback=cb, content_type="text/html")
    session = __import__("requests").Session()
    got = _enumerar_categoria(session, "circulares", "C", "2026-01-01", "2026-12-31", None, None)
    # los 60 del catálogo, recolectados vía bloques cuya búsqueda cabe en <=_UMBRAL
    assert len({g["pdf_url"] for g in got}) == 60


@responses.activate
def test_enumerar_dedups_by_pdf_url():
    def cb(request):
        term = request.body.split("r=", 1)[1]
        if term == "2026":
            return (200, {}, _page(_card("CIR-2026-000001-4", "2026-01-05", "https://x/dup.pdf"), 355))
        # todo prefijo devuelve la misma tarjeta duplicada
        return (200, {}, _page(_card("CIR-2026-000001-4", "2026-01-05", "https://x/dup.pdf"), 1))
    responses.add_callback(responses.POST, _CIR_URL, callback=cb, content_type="text/html")
    session = __import__("requests").Session()
    got = _enumerar_categoria(session, "circulares", "C", "2026-01-01", "2026-12-31", None, None)
    assert len(got) == 1


@responses.activate
def test_enumerar_continues_past_a_failing_year():
    def cb(request):
        term = request.body.split("r=", 1)[1]
        if term == "2015":
            return (500, {}, "boom")
        return (200, {}, _page(_card("CIR-2016-000001-4", "2016-02-01", "https://x/ok.pdf"), 1))
    responses.add_callback(responses.POST, _CIR_URL, callback=cb, content_type="text/html")
    progreso = []
    session = __import__("requests").Session()
    got = _enumerar_categoria(session, "circulares", "C", "2015-01-01", "2016-12-31", None, progreso.append)
    assert any(g["pdf_url"].endswith("/ok.pdf") for g in got)
    assert any("Error" in m for m in progreso)


import threading

from core.scrapers.registry import FAMILY_REGISTRY
from core.scrapers.families.snr import ScrapSNR


def test_snr_is_registered():
    import core.scrapers.families  # noqa: F401
    assert FAMILY_REGISTRY["snr"].__name__ == "ScrapSNR"


def test_filters_by_publication_date_is_enabled():
    assert ScrapSNR.filters_by_publication_date is True


@responses.activate
def test_scrap_collects_both_categories():
    responses.add(responses.POST, _CIR_URL,
                  body=_page(_card("CIR-2026-000010-4", "2026-03-01", "https://x/c10.pdf"), 1))
    responses.add(responses.POST, _RES_URL,
                  body=_page(_card("RES-2026-000020-6", "2026-04-01", "https://x/r20.pdf"), 1))
    docs = ScrapSNR().scrap(fini="2026-01-01", ffin="2026-12-31")
    assert {d.title for d in docs} == {"C_SNR_0010_2026", "R_SNR_0020_2026"}
    assert {d.tipo for d in docs} == {"Circular", "Resolución"}


@responses.activate
def test_scrap_applies_year_floor_and_range():
    # una circular de 2013 (bajo el piso) y una de 2026 en rango.
    # La tarjeta de 2013 se arma a mano para que su fecha en prosa sea de 2013
    # (el helper _card fija la prosa a 2026); así el piso de año la descarta.
    old_card = (
        '<li><div class="contenido_download"><span class="lettercap"></span> x<br>'
        '<a href="https://x/old.pdf">CIR-2013-000001-4 del 10 de enero de 2013 "t"</a><br>'
        '<span>Publicación: 2013-01-10</span></div></li>'
    )
    body = _page(
        old_card
        + _card("CIR-2026-000002-4", "2026-05-01", "https://x/new.pdf"), 2)
    responses.add(responses.POST, _CIR_URL, body=body)
    responses.add(responses.POST, _RES_URL, body=_page("", 0))
    docs = ScrapSNR().scrap(fini="2010-01-01", ffin="2026-12-31")
    assert {d.title for d in docs} == {"C_SNR_0002_2026"}


@responses.activate
def test_scrap_stops_on_stop_event():
    responses.add(responses.POST, _CIR_URL, body=_page("", 0))
    responses.add(responses.POST, _RES_URL, body=_page("", 0))
    ev = threading.Event()
    ev.set()
    docs = ScrapSNR().scrap(fini="2026-01-01", ffin="2026-12-31", stop_event=ev)
    assert docs == []
    assert len(responses.calls) == 0


@responses.activate
def test_scrap_respects_limit():
    cards = "".join(_card(f"CIR-2026-{i:06d}-4", "2026-02-01", f"https://x/c{i}.pdf") for i in range(1, 6))
    responses.add(responses.POST, _CIR_URL, body=_page(cards, 5))
    responses.add(responses.POST, _RES_URL, body=_page("", 0))
    docs = ScrapSNR().scrap(fini="2026-01-01", ffin="2026-12-31", limit=2)
    assert len(docs) == 2
