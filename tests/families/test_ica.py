import datetime
import threading

import pytest
import responses
from responses import matchers

from core.scrapers.families import ica as ica_module
from core.scrapers.families.ica import (
    _ANIO_MINIMO,
    _NACIONALES_URL,
    _SECCIONALES_URL,
    _SOURCE,
    _archivo,
    _fechas,
    _filas,
    _titulo,
    _ultima_pagina,
    ScrapIca,
)
from core.scrapers.registry import FAMILY_REGISTRY

_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre"]
_contador = iter(range(10**6))


def _es(fecha: str) -> str:
    d = datetime.date.fromisoformat(fecha)
    return f"{d.day:02d} de {_MESES[d.month - 1]} de {d.year}"


def _fila(num, anio, pub, exp, palabra="Resolución", guid=None, observacion=None, diario=None,
          epigrafe="&ldquo;Por la cual se modifican los artículos 4 y 6&rdquo;.", archivo=None):
    # Copia de una fila real de resoluciones-seccionales / -oficinas-nacionales.
    guid = guid or f"9b51243d-4f83-420f-894c-{next(_contador):012d}"
    if archivo is None:
        archivo = f"{anio}R{num:09d}.aspx" if isinstance(num, int) else "x.aspx"
    href = f"/getattachment/{guid}/{archivo}"
    texto = f"{palabra} {num} de {anio}"
    obs = (
        f'<div><br/>Observación: {observacion} <a href="/getattachment/6e26/2026R00015837.aspx" target="_blank">'
        "artículo 4 de la Resolución No. 00015837</a>.<br />\n&nbsp;</div>"
    ) if observacion else ""
    do = (
        f'<br/><a href="imprenta.gov.co/diario-oficial" target="_blank">Diario Oficial: {diario[0]}</a> ({diario[1]})'
    ) if diario else ""
    return (
        '<div class="row py-3">\n'
        '  <div class="col-md-2 text-center pt-2">\n'
        f'    <a href="{href}" target="_blank" title="Descargar el documento {texto}"><img src="/i-pdf.png" /></a>\n'
        '    <div class="pt-2 pl-2">302 kb</div>\n'
        "  </div>\n"
        '  <div class="col-md-10">\n'
        f'    <div class="tiponorma">{palabra}</div>\n'
        f'    <h2 class="mb-0"><a href="{href}" target="_blank" class="text-5">{texto} - <!--StartFragment-->{epigrafe}\n&nbsp;</a></h2>\n'
        f"    <div>Publicación: {_es(pub)} | Expedición: {_es(exp)}</div>\n"
        f"    {obs}\n    {do}\n"
        "  </div>\n"
        "</div><hr/>"
    )


def _html(url, filas, ultima=1) -> str:
    pag = (
        f'<ul class="pagination"><li><a class="page-link next" href="/{url.split(".co/")[1]}?page={ultima}" '
        'aria-label="Ultima" title="Ir a la última página"><span><i aria-label="Ultima"></i>|</span></a></li></ul>'
    ) if ultima > 1 else ""
    return "<html><body><div class='container'>" + "".join(filas) + "</div>" + pag + "</body></html>"


def _seccion(url, *paginas, status=200):
    ultima = len(paginas)
    for p, filas in enumerate(paginas, start=1):
        match = [matchers.query_param_matcher({"page": str(p)} if p > 1 else {})]
        responses.add(responses.GET, url, body=_html(url, filas, ultima), status=status, match=match)


@pytest.fixture(autouse=True)
def _sin_espera(monkeypatch):
    monkeypatch.setattr(ica_module, "_ESPERA_REINTENTO_SEG", 0)


def _vacia(url):
    _seccion(url, [])


def test_source_y_registro():
    assert _SOURCE == "Instituto Colombiano Agropecuario"
    assert _ANIO_MINIMO == 2015
    assert FAMILY_REGISTRY["ica"] is ScrapIca
    assert ScrapIca.filters_by_publication_date is True
    assert ScrapIca.checks_for_republication is True


def test_titulo():
    assert _titulo("Resolución 19595 de 2026 - “Por la cual…”.", True)[:3] == ("R_ICA_S19595_2026", 19595, 2026)
    assert _titulo("Resolución 22227 de 2026 - x", False)[0] == "R_ICA_22227_2026"
    assert _titulo("Resolución 805 de 2025 - x", True)[0] == "R_ICA_S0805_2025"
    assert _titulo("Resolución 00805 de 2025", True)[0] == "R_ICA_S0805_2025"
    assert _titulo("Resolución 20263040030395 de 2026 - x", False)[0] == "R_ICA_20263040030395_2026"
    assert _titulo("Resolucion No. 12 de 2019 - x", False)[0] == "R_ICA_0012_2019"
    assert _titulo("Resolución 19595 de 2026 - “Por la cual”.", True)[3] == "“Por la cual”."


def test_titulo_norma_y_acuerdo():
    assert _titulo("Norma 8970 de 2024 - Por la cual", True)[0] == "R_ICA_S8970_2024"
    assert _titulo("Acuerdo 97962 de 2021 - Por la cual", True)[0] == "R_ICA_S97962_2021"


def test_titulo_fuera_de_patron():
    title, numero, anio, _ = _titulo("Res. sin número - Por la cual", True)
    assert (title, numero, anio) == ("R_ICA_SRes_sin_n_mero", None, None)


def test_archivo():
    assert _archivo("https://www.ica.gov.co/getattachment/9b51/2026R000019595.aspx") == (2026, 19595)
    assert _archivo("/getattachment/9b51/2022R889.aspx") == (2022, 889)
    assert _archivo("/getattachment/9b51/2026R00015837.aspx?lang=es-CO") == (2026, 15837)
    assert _archivo("/getattachment/9b51/Resolucion-805.aspx") is None
    assert _archivo("/getattachment/9b51/2026R000019595.pdf") is None


def test_fechas():
    assert _fechas("Publicación: 02 de octubre de 2026 | Expedición: 01 de octubre de 2026") == (
        "02 de octubre de 2026", "01 de octubre de 2026")
    assert _fechas("Publicacion: 02 de octubre de 2026|Expedicion: 01 de octubre de 2026") == (
        "02 de octubre de 2026", "01 de octubre de 2026")
    assert _fechas("Publicación: 02 de octubre de 2026") == ("02 de octubre de 2026", "")


def test_ultima_pagina():
    assert _ultima_pagina(_html(_SECCIONALES_URL, [], ultima=59)) == 59
    assert _ultima_pagina(_html(_SECCIONALES_URL, [])) == 1


def test_parseo_fila():
    filas = _filas(_html(_NACIONALES_URL, [_fila(
        22227, 2026, "2026-11-10", "2026-11-09", guid="e554",
        observacion="La presente resolución rige a partir de su publicación.",
        diario=("53685", "09/11/2026"),
    )]))
    assert filas == [{
        "href": "https://www.ica.gov.co/getattachment/e554/2026R000022227.aspx",
        "texto": "Resolución 22227 de 2026 - “Por la cual se modifican los artículos 4 y 6”.",
        "publicacion": "10 de noviembre de 2026",
        "expedicion": "09 de noviembre de 2026",
        "observacion": "La presente resolución rige a partir de su publicación. artículo 4 de la Resolución No. 00015837 .",
        "diario": "Diario Oficial 53685 (09/11/2026)",
    }]


@responses.activate
def test_documento_completo():
    _seccion(_SECCIONALES_URL, [_fila(19595, 2026, "2026-10-02", "2026-10-01", guid="9b51", observacion="Rige.")])
    _seccion(_NACIONALES_URL, [_fila(22227, 2026, "2026-10-10", "2026-10-09", guid="e554", diario=("53685", "09/11/2026"))])
    docs = ScrapIca().scrap("2026-10-01", "2026-10-31")
    assert [d.title for d in docs] == ["R_ICA_S19595_2026", "R_ICA_22227_2026"]
    s, n = docs
    assert s.tipo == n.tipo == "Resolución"
    assert s.f_public == "2026-10-02"
    assert s.f_providencia == "2026-10-01"
    assert s.link == {"url": "https://www.ica.gov.co/getattachment/9b51/2026R000019595.aspx", "method": "GET"}
    assert s.save_path == f"{_SOURCE}/2026-10-02/Resolución/R_ICA_S19595_2026(extension)"
    assert s.detalle.startswith("“Por la cual se modifican los artículos 4 y 6”. — Rige.")
    assert n.detalle == "“Por la cual se modifican los artículos 4 y 6”. — Diario Oficial 53685 (09/11/2026)"
    assert s.title_unverified is False


@responses.activate
def test_anio_distinto_de_expedicion_queda_sin_verificar():
    _seccion(_SECCIONALES_URL, [_fila(899, 2021, "2022-02-03", "2022-01-31")])
    _vacia(_NACIONALES_URL)
    avisos = []
    docs = ScrapIca().scrap("2022-01-01", "2022-12-31", on_progress=avisos.append)
    assert docs[0].title == "R_ICA_S0899_2021"
    assert docs[0].title_unverified is True
    assert any("R_ICA_S0899_2021 fue expedida el 2022-01-31" in a for a in avisos)


@responses.activate
def test_texto_distinto_del_archivo_queda_sin_verificar():
    # Caso real: "Resolución 899 de 2021" expedida el 31-01-2022, archivo 2022R889.
    _seccion(_SECCIONALES_URL, [
        _fila(899, 2021, "2022-02-03", "2022-01-31", archivo="2022R889.aspx"),
        # Mismo año que la expedición, pero el número del archivo es otro.
        _fila(500, 2022, "2022-03-03", "2022-03-01", archivo="2022R000000501.aspx"),
    ])
    _vacia(_NACIONALES_URL)
    avisos = []
    docs = ScrapIca().scrap("2022-01-01", "2022-12-31", on_progress=avisos.append)
    assert [(d.title, d.title_unverified) for d in docs] == [
        ("R_ICA_S0899_2021", True), ("R_ICA_S0500_2022", True)]
    assert any("texto 899 de 2021, archivo 889 de 2022" in a for a in avisos)
    assert any("texto 500 de 2022, archivo 501 de 2022" in a for a in avisos)


@responses.activate
def test_archivo_fuera_de_patron_no_se_cruza():
    _seccion(_NACIONALES_URL, [_fila(77, 2024, "2024-05-02", "2024-05-01", archivo="Resolucion-77.aspx")])
    _vacia(_SECCIONALES_URL)
    avisos = []
    docs = ScrapIca().scrap("2024-01-01", "2024-12-31", on_progress=avisos.append)
    assert [(d.title, d.title_unverified) for d in docs] == [("R_ICA_0077_2024", False)]
    assert not any("no cuadra" in a for a in avisos)


@responses.activate
def test_texto_fuera_de_patron_queda_sin_verificar():
    fila = _fila(5, 2020, "2020-03-02", "2020-03-01").replace(
        'class="text-5">Resolución 5 de 2020', 'class="text-5">Res. sin número')
    _seccion(_SECCIONALES_URL, [fila])
    _vacia(_NACIONALES_URL)
    avisos = []
    docs = ScrapIca().scrap("2020-01-01", "2020-12-31", on_progress=avisos.append)
    assert len(docs) == 1 and docs[0].title.startswith("R_ICA_SRes_sin_n_mero_h") and docs[0].title_unverified
    assert any("texto inesperado" in a for a in avisos)


@responses.activate
def test_no_pide_mas_alla_de_la_ultima():
    _seccion(
        _SECCIONALES_URL,
        [_fila(4, 2016, "2016-04-01", "2016-04-01")],
        [_fila(3, 2015, "2015-03-01", "2015-03-01")],
    )
    _vacia(_NACIONALES_URL)
    docs = ScrapIca().scrap("2015-01-01", "2026-12-31")
    assert [d.title for d in docs] == ["R_ICA_S0004_2016", "R_ICA_S0003_2015"]
    pedidas = [c.request.url for c in responses.calls if c.request.url.startswith(_SECCIONALES_URL)]
    assert len(pedidas) == 2


@responses.activate
def test_paginacion_completa_sin_corte_por_expedicion():
    # Corrida de un solo día: se recorren igual todas las páginas hasta la
    # "Ultima" (y ninguna más), y entra lo expedido años antes pero publicado
    # ese día (como la nacional 93858 de 2021, publicada el 11-08-2026).
    _seccion(
        _SECCIONALES_URL,
        [_fila(30, 2026, "2026-11-05", "2026-11-04"), _fila(29, 2025, "2025-07-01", "2025-07-01")],
        [_fila(28, 2024, "2024-06-01", "2024-06-01"), _fila(27, 2022, "2022-06-01", "2022-06-01")],
        [_fila(26, 2019, "2019-01-01", "2019-01-01")],
    )
    _seccion(
        _NACIONALES_URL,
        [_fila(99999, 2026, "2026-08-10", "2026-08-10")],
        [_fila(93858, 2021, "2026-08-11", "2021-03-26")],
    )
    docs = ScrapIca().scrap("2026-08-11", "2026-08-11")
    assert [d.title for d in docs] == ["R_ICA_93858_2021"]
    assert docs[0].f_providencia == "2021-03-26"
    pedidas = [c.request.url for c in responses.calls]
    assert sum(u.startswith(_SECCIONALES_URL) for u in pedidas) == 3
    assert sum(u.startswith(_NACIONALES_URL) for u in pedidas) == 2
    assert not any("page=4" in u for u in pedidas)


@responses.activate
def test_filtro_por_publicacion():
    _seccion(_SECCIONALES_URL, [
        _fila(3, 2026, "2026-12-01", "2026-11-10"),   # expedida en rango, publicada fuera
        _fila(2, 2026, "2026-11-12", "2026-06-01"),   # expedida meses antes, publicada en rango
        _fila(1, 2026, "2026-10-01", "2026-05-01"),   # publicada antes del rango
    ])
    _vacia(_NACIONALES_URL)
    docs = ScrapIca().scrap("2026-11-01", "2026-11-30")
    assert [d.title for d in docs] == ["R_ICA_S0002_2026"]


@responses.activate
def test_piso_por_expedicion():
    _seccion(_NACIONALES_URL, [
        _fila(10, 2015, "2015-02-01", "2015-01-20"),
        _fila(9, 2014, "2015-01-15", "2014-12-30"),
    ])
    _vacia(_SECCIONALES_URL)
    docs = ScrapIca().scrap("2015-01-01", "2015-12-31")
    assert [d.title for d in docs] == ["R_ICA_0010_2015"]


@responses.activate
def test_dedup():
    _seccion(_SECCIONALES_URL, [
        _fila(28027, 2018, "2018-08-01", "2018-07-30", guid="aaaa"),
        _fila(28027, 2018, "2018-08-01", "2018-07-30", guid="bbbb"),
    ])
    _vacia(_NACIONALES_URL)
    avisos = []
    docs = ScrapIca().scrap("2018-01-01", "2018-12-31", on_progress=avisos.append)
    assert len(docs) == 1
    assert "aaaa" in docs[0].link["url"]
    assert any("R_ICA_S28027_2018 aparece repetida" in a for a in avisos)


@responses.activate
def test_fecha_ilegible_se_omite():
    fila = _fila(5, 2020, "2020-01-01", "2020-01-01").replace("Expedición: 01 de enero de 2020", "Expedición: sin fecha")
    _seccion(_SECCIONALES_URL, [fila])
    _vacia(_NACIONALES_URL)
    avisos = []
    assert ScrapIca().scrap("2020-01-01", "2020-12-31", on_progress=avisos.append) == []
    assert any("sin fecha de publicación o expedición legible" in a for a in avisos)


@responses.activate
def test_stop_event():
    _seccion(_SECCIONALES_URL, [_fila(2, 2026, "2026-11-10", "2026-11-10")])
    stop = threading.Event()

    def progreso(texto):
        if "nacionales" in texto:
            stop.set()

    docs = ScrapIca().scrap("2026-11-01", "2026-11-30", stop_event=stop, on_progress=progreso)
    assert [d.title for d in docs] == ["R_ICA_S0002_2026"]
    assert not any(c.request.url.startswith(_NACIONALES_URL) for c in responses.calls)


@responses.activate
def test_falla_de_pagina():
    # Página 1 de seccionales falla → sección vacía; página 2 de nacionales
    # falla → se queda con lo de la página 1.
    _seccion(_SECCIONALES_URL, [], status=500)
    responses.add(responses.GET, _NACIONALES_URL,
                  body=_html(_NACIONALES_URL, [_fila(7, 2026, "2026-11-10", "2026-11-10")], ultima=2),
                  match=[matchers.query_param_matcher({})])
    responses.add(responses.GET, _NACIONALES_URL, status=500, match=[matchers.query_param_matcher({"page": "2"})])
    avisos = []
    docs = ScrapIca().scrap("2015-01-01", "2026-11-30", on_progress=avisos.append)
    assert [d.title for d in docs] == ["R_ICA_0007_2026"]
    assert any("Error consultando Resoluciones seccionales" in a for a in avisos)
    assert any("página 2" in a for a in avisos)


@responses.activate
def test_seccion_sin_filas_avisa_error():
    _vacia(_SECCIONALES_URL)
    _vacia(_NACIONALES_URL)
    avisos = []
    assert ScrapIca().scrap("2026-11-01", "2026-11-30", on_progress=avisos.append) == []
    assert any("Error: Resoluciones seccionales no trajo ninguna resolución" in a for a in avisos)


@responses.activate
def test_limit():
    _seccion(_SECCIONALES_URL, [
        _fila(3, 2026, "2026-11-10", "2026-11-10"),
        _fila(2, 2026, "2026-11-09", "2026-11-09"),
        _fila(1, 2026, "2026-11-08", "2026-11-08"),
    ])
    docs = ScrapIca().scrap("2026-11-01", "2026-11-30", limit=2)
    assert [d.title for d in docs] == ["R_ICA_S0003_2026", "R_ICA_S0002_2026"]
    assert not any(c.request.url.startswith(_NACIONALES_URL) for c in responses.calls)


@responses.activate
def test_pagina_que_falla_una_vez_se_reintenta():
    # Un 502 pasajero en la página 2 no hace perder sus resoluciones.
    responses.add(responses.GET, _SECCIONALES_URL,
                  body=_html(_SECCIONALES_URL, [_fila(3, 2026, "2026-11-10", "2026-11-10")], ultima=2),
                  match=[matchers.query_param_matcher({})])
    responses.add(responses.GET, _SECCIONALES_URL, status=502, match=[matchers.query_param_matcher({"page": "2"})])
    responses.add(responses.GET, _SECCIONALES_URL,
                  body=_html(_SECCIONALES_URL, [_fila(2, 2019, "2026-11-10", "2019-05-05")], ultima=2),
                  match=[matchers.query_param_matcher({"page": "2"})])
    _vacia(_NACIONALES_URL)
    docs = ScrapIca().scrap("2026-11-01", "2026-11-30")
    assert [d.title for d in docs] == ["R_ICA_S0003_2026", "R_ICA_S0002_2019"]


@responses.activate
def test_pagina_que_sigue_fallando_se_salta_y_sigue_con_las_demas():
    # La página 2 falla en todos los intentos: se salta sólo esa y se sigue
    # con la 3, donde está una resolución vieja publicada hace poco.
    paginas = {
        1: [_fila(3, 2026, "2026-11-10", "2026-11-10")],
        3: [_fila(1, 2019, "2026-11-10", "2019-05-05")],
    }
    for p, filas in paginas.items():
        responses.add(responses.GET, _SECCIONALES_URL, body=_html(_SECCIONALES_URL, filas, ultima=3),
                      match=[matchers.query_param_matcher({"page": str(p)} if p > 1 else {})])
    responses.add(responses.GET, _SECCIONALES_URL, status=502, match=[matchers.query_param_matcher({"page": "2"})])
    _vacia(_NACIONALES_URL)
    avisos = []
    docs = ScrapIca().scrap("2026-11-01", "2026-11-30", on_progress=avisos.append)
    assert [d.title for d in docs] == ["R_ICA_S0003_2026", "R_ICA_S0001_2019"]
    pedidos_p2 = [c for c in responses.calls if "page=2" in c.request.url]
    assert len(pedidos_p2) == ica_module._MAX_INTENTOS
    assert any("página 2" in a and "se salta" in a for a in avisos)


@responses.activate
def test_tildes_descompuestas():
    # Si el sitio manda la "ó" como "o" + tilde suelta (pasó con MinEducación,
    # PR #104), los rótulos Publicación/Expedición/Observación y la palabra
    # "Resolución" se tienen que reconocer igual.
    import unicodedata
    html = _html(_SECCIONALES_URL, [_fila(19595, 2026, "2026-10-02", "2026-10-01", observacion="Rige.")])
    html = unicodedata.normalize("NFD", html)
    assert "Publicací" not in html and "Publicación" in html
    responses.add(responses.GET, _SECCIONALES_URL, body=html, match=[matchers.query_param_matcher({})])
    _vacia(_NACIONALES_URL)
    docs = ScrapIca().scrap("2026-10-01", "2026-10-31")
    assert [d.title for d in docs] == ["R_ICA_S19595_2026"]
    d = docs[0]
    assert d.f_public == "2026-10-02" and d.f_providencia == "2026-10-01"
    assert d.title_unverified is False
    assert "— Rige." in d.detalle and "Resolución No." in d.detalle
    assert d.detalle == unicodedata.normalize("NFC", d.detalle)


@responses.activate
def test_textos_ilegibles_iguales_no_se_toman_por_repetidos():
    # Dos resoluciones distintas (archivos distintos) cuyo texto no se puede
    # leer y coincide: las dos se guardan, cada una con su propio título y
    # archivo, en vez de descartar la segunda como "repetida".
    import hashlib
    filas = [
        _fila(5, 2020, "2020-03-02", "2020-03-01").replace('class="text-5">Resolución 5 de 2020', 'class="text-5">Res. sin número'),
        _fila(6, 2020, "2020-03-02", "2020-03-01").replace('class="text-5">Resolución 6 de 2020', 'class="text-5">Res. sin número'),
    ]
    _seccion(_SECCIONALES_URL, filas)
    _vacia(_NACIONALES_URL)
    avisos = []
    docs = ScrapIca().scrap("2020-01-01", "2020-12-31", on_progress=avisos.append)
    assert len(docs) == 2
    for d in docs:
        h = hashlib.sha1(d.link["url"].encode()).hexdigest()[:7]
        assert d.title == f"R_ICA_SRes_sin_n_mero_h{h}"
        assert d.title_unverified is True
    assert docs[0].save_path != docs[1].save_path
    assert not any("repetida" in a for a in avisos)


@responses.activate
def test_corta_al_llegar_a_una_pagina_entera_anterior_al_piso():
    # El listado va por expedición descendente: una página donde TODO es
    # anterior a 2015 significa que ya no queda nada útil más abajo.
    _seccion(
        _NACIONALES_URL,
        [_fila(20, 2016, "2016-02-01", "2016-01-20"), _fila(19, 2015, "2026-08-11", "2015-01-05")],
        [_fila(18, 2014, "2014-12-01", "2014-11-30"), _fila(17, 2013, "2013-12-01", "2013-11-30")],
        [_fila(16, 2010, "2010-01-01", "2010-01-01")],
        [_fila(15, 2009, "2009-01-01", "2009-01-01")],
    )
    _vacia(_SECCIONALES_URL)
    avisos = []
    docs = ScrapIca().scrap("2015-01-01", "2026-12-31", on_progress=avisos.append)
    assert [d.title for d in docs] == ["R_ICA_0020_2016", "R_ICA_0019_2015"]
    pedidas = [c.request.url for c in responses.calls if c.request.url.startswith(_NACIONALES_URL)]
    assert len(pedidas) == 2
    assert any("desde la página 2 todo es anterior a 2015" in a for a in avisos)


@responses.activate
def test_una_fila_suelta_anterior_al_piso_no_corta():
    # Una sola fila mal fechada (anterior a 2015) en medio de una página con
    # filas válidas no corta la sección: sólo una página entera lo hace.
    _seccion(
        _NACIONALES_URL,
        [_fila(20, 2016, "2016-02-01", "2016-01-20"), _fila(99, 2005, "2016-01-10", "2005-01-01")],
        [_fila(19, 2015, "2015-06-01", "2015-06-01")],
    )
    _vacia(_SECCIONALES_URL)
    docs = ScrapIca().scrap("2015-01-01", "2026-12-31")
    assert [d.title for d in docs] == ["R_ICA_0020_2016", "R_ICA_0019_2015"]
