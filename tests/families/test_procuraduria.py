import datetime

import pytest
import requests
import responses
from responses import matchers

from core.scrapers.families.procuraduria import (
    _PaginaInesperada,
    _RELATORIA,
    _con_sufijos,
    _consultar,
    _fecha_iso,
    _fecha_sirel,
    _filas,
    _id_de_relid,
    _numero_concepto,
    _numero_normativa,
    _pie,
    _relid,
    _safe_title,
    _titulo_concepto,
    _titulo_normativa,
    _url_normativa,
)


# ---- URL canónica de Normativa ----
_CANON = "https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId=MjQ0MTg1&mode=inline"


@pytest.mark.parametrize("href", [
    "https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId=MjQ0MTg1&mode=inline",
    "https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId=MjQ0MTg1&mode=inline\t",
    "https://apps.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId=MjQ0MTg1&mode=1#page=inline",
    "https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId=MjQ0MTg1&mode=1#page=inline"
    "https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId=MjQ0MTg1&mode=1#page=inline"
    "https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId=MjQ0MTg1&mode=1#page=inline",
])
def test_url_canonica_desde_todas_las_variantes(href):
    assert _url_normativa(_relid(href)) == _CANON


@pytest.mark.parametrize("href", [
    None,
    "",
    "http://www.secretariasenado.gov.co/senado/basedoc/ley_1712_2014.html",
    "https://dapre.presidencia.gov.co/normativa/normativa/DECRETO%201168%20DEL%2025%20DE%20AGOSTO%20DE%202020.pdf",
    "https://www.procuraduria.gov.co/relatoria/media/file/CDU-2017(2).pdf",
    "*Programa válido únicamente para empleados activos en TP Nicaragua.",
])
def test_relid_none_para_externos_y_texto_suelto(href):
    assert _relid(href) is None


def test_id_de_relid_decodifica_base64():
    assert _id_de_relid("MjQ0MTg1") == 244185
    assert _id_de_relid("Mzg0") == 384


def test_id_de_relid_cero_si_no_decodifica():
    assert _id_de_relid("%%%") == 0


# ---- número de Normativa ----
@pytest.mark.parametrize("crudo,esperado", [
    ("21", "0021"),
    ("338", "0338"),
    ("7A", "0007A"),
    ("34 A", "0034A"),
    ("100-01", "100-01"),
    ("13-4", "13-4"),
    (" 5 ", "0005"),
    ("", ""),
])
def test_numero_normativa(crudo, esperado):
    assert _numero_normativa(crudo) == esperado


# ---- título de Normativa ----
@pytest.mark.parametrize("tipo,numero,anio,esperado", [
    ("Resolución", "338", 2025, "R_PGN_0338_2025"),
    ("Directiva", "21", 2025, "DIR_PGN_0021_2025"),
    ("Directiva Conjunta", "1", 2021, "DIR_PGN_0001_2021"),
    ("Circular", "12", 2025, "C_PGN_0012_2025"),
    ("Circular Conjunta", "100-01", 2016, "C_PGN_100-01_2016"),
    ("Memorando", "2", 2026, "M_PGN_0002_2026"),
    ("Carta Circular", "1", 2026, "CCIR_PGN_0001_2026"),
    ("Instructivo", "3", 2024, "INS_PGN_0003_2024"),
    ("Acuerdo", "1", 2019, "A_PGN_0001_2019"),
    ("Protocolo", "1", 2022, "PRO_PGN_0001_2022"),
    ("Circular", "7A", 2012, "C_PGN_0007A_2012"),
    ("Decreto", "262", 2000, "D0262000"),
])
def test_titulo_normativa(tipo, numero, anio, esperado):
    assert _titulo_normativa(tipo, numero, anio, id_interno=1) == (esperado, False)


def test_titulo_normativa_tipo_desconocido_usa_doc_y_avisa():
    assert _titulo_normativa("Manual", "4", 2020, id_interno=1) == ("DOC_PGN_0004_2020", True)


def test_titulo_normativa_sin_numero_usa_sn_id():
    assert _titulo_normativa("Resolución", "", 2022, id_interno=240116) == ("R_PGN_SN240116_2022", False)


def test_safe_title_reemplaza_caracteres_invalidos():
    assert _safe_title('C_PGN_1/2"3_2016') == "C_PGN_1-2-3_2016"


# ---- fechas ----
def test_fecha_iso():
    assert _fecha_iso("2025-12-19") == datetime.date(2025, 12, 19)
    assert _fecha_iso(" 2025-12-19 ") == datetime.date(2025, 12, 19)


def test_fecha_iso_none():
    assert _fecha_iso("") is None
    assert _fecha_iso("2025-02-30") is None
    assert _fecha_iso("19/12/2025") is None


def test_fecha_sirel_prosa_con_dia_de_semana():
    assert _fecha_sirel("jueves, 30 julio 2026") == datetime.date(2026, 7, 30)
    assert _fecha_sirel("miércoles, 9 septiembre 2026") == datetime.date(2026, 9, 9)
    assert _fecha_sirel("sábado, 12 junio 2010") == datetime.date(2010, 6, 12)


def test_fecha_sirel_none():
    assert _fecha_sirel("") is None
    assert _fecha_sirel("jueves, 31 febrero 2026") is None


# ---- número de concepto ----
@pytest.mark.parametrize("crudo,anio_fecha,esperado", [
    # regla 1: consecutivo + separador + año de 4 dígitos al final
    ("236-2026", 2026, (236, 2026, False)),
    ("004 - 2025", 2025, (4, 2025, False)),
    ("97-2025", 2025, (97, 2025, False)),
    ("119 de 2016", 2016, (119, 2016, False)),
    ("263/2025", 2025, (263, 2025, False)),
    ("CONCEPTO 159 - 2026", 2026, (159, 2026, False)),
    ("Concepto No. 12-2016", 2016, (12, 2016, False)),
    ("concepto No 999 de 2016", 2016, (999, 2016, False)),
    ("C -160-2026", 2026, (160, 2026, False)),
    ("C- 175-2025", 2025, (175, 2025, False)),
    ("236-2026.", 2026, (236, 2026, False)),
    ("123DE 2025", 2025, (123, 2025, False)),
    # regla 2: año de 4 dígitos al inicio
    ("2025-525", 2025, (525, 2025, False)),
    ("2019-430944", 2022, (430944, 2019, False)),
    ("CONCEPTO E-2021-671179", 2026, (671179, 2021, False)),
    # regla 3: año de 2 dígitos al inicio que coincide con la fecha
    ("16-158", 2016, (158, 2016, False)),
    ("CONCEPTO 16-34", 2016, (34, 2016, False)),
    # regla 4: referencia C-/D- o número solo -> año de la fecha
    ("C-6194", 2016, (6194, 2016, False)),
    ("D-1234", 2016, (1234, 2016, False)),
    ("393", 2025, (393, 2025, False)),
    ("Concepto N. 00023", 2016, (23, 2016, False)),
    ("CONCEPTO Nº 061", 2025, (61, 2025, False)),
    # regla 5: cualquier otra cosa con dígitos -> primer grupo + aviso
    ("SIN 5", 2025, (5, 2025, True)),
    ("Concepto Ã¿Â¿Ã¿Â¿ 061", 2025, (61, 2025, False)),
    ("16-158", 2020, (16, 2020, True)),
    # regla 4: N° (grados) debe quitarse como N. y Nº
    ("CONCEPTO N° 061", 2025, (61, 2025, False)),
    ("N° 12-2016", 2016, (12, 2016, False)),
    ("No. 5-2025", 2025, (5, 2025, False)),
])
def test_numero_concepto(crudo, anio_fecha, esperado):
    assert _numero_concepto(crudo, anio_fecha) == esperado


@pytest.mark.parametrize("crudo", ["", "   ", "CONCEPTO", "Sin número"])
def test_numero_concepto_none_sin_digitos(crudo):
    assert _numero_concepto(crudo, 2025) is None


def test_numero_concepto_no_toma_anio_fuera_de_rango_como_anio():
    # "2025-1234": 1234 no es un año plausible -> regla 2 (año al inicio)
    assert _numero_concepto("2025-1234", 2025) == (1234, 2025, False)


# ---- título de concepto ----
def test_titulo_concepto_rellena_a_7():
    assert _titulo_concepto("236-2026", datetime.date(2026, 9, 9), "245582") == ("CTO_PGN_0000236_2026", False)


def test_titulo_concepto_mas_de_7_digitos_se_deja():
    assert _titulo_concepto("2019-12345678", datetime.date(2022, 3, 10), "1") == ("CTO_PGN_12345678_2019", False)


def test_titulo_concepto_sin_numero_usa_sn_docid():
    assert _titulo_concepto("", datetime.date(2025, 5, 2), "245408") == ("CTO_PGN_SN245408_2025", False)


def test_titulo_concepto_propaga_aviso():
    assert _titulo_concepto("SIN 5", datetime.date(2025, 5, 2), "9") == ("CTO_PGN_0000005_2025", True)


# ---- sufijos por choque ----
def test_con_sufijos_sin_choques_no_cambia():
    assert _con_sufijos([("A", 3), ("B", 1)]) == ["A", "B"]


def test_con_sufijos_ordena_por_id_y_conserva_orden_de_entrada():
    pares = [("C_PGN_0001_2023", 300), ("C_PGN_0001_2023", 100), ("X", 5), ("C_PGN_0001_2023", 200)]
    assert _con_sufijos(pares) == ["C_PGN_0001_2023_3", "C_PGN_0001_2023", "X", "C_PGN_0001_2023_2"]


def test_con_sufijos_empate_de_id_desempata_por_posicion():
    assert _con_sufijos([("T", 0), ("T", 0)]) == ["T", "T_2"]


def test_con_sufijos_estable_ante_subconjuntos_con_ids_mayores():
    # el mismo documento (id 100) conserva su título aunque aparezcan otros
    # con ids mayores (documentos nuevos del sitio)
    antes = _con_sufijos([("T", 100)])
    despues = _con_sufijos([("T", 100), ("T", 150)])
    assert antes[0] == despues[0] == "T"
    assert despues[1] == "T_2"


# ---- helpers de HTML con la forma real del sitio ----
def _pie_html(n):
    return (
        '<div align="center"><table class="adminlist"><tr><td nowrap="true" width="48%" align="center">'
        f"                       Resultados {1 if n else 0} - {n} de {n}</td></tr></table></div>"
    )


def _html_normativa(filas, total=None, con_pie=True):
    """filas: (año, tipo, número, temática, corta, larga, fecha, href|None)"""
    trs = []
    for anio, tipo, num, tem, corta, larga, fecha, href in filas:
        tds = "".join(f'<td align="left">\n{c}</td>' for c in (anio, tipo, num, tem, corta, larga, fecha))
        enlace = (
            f'<td>\n<a href="{href}" target="_blank">\n<img src="images/icons/down.png"/>\nVer Documento</a>\n</td>'
            if href else "<td></td>"
        )
        trs.append(f"<tr>\n{tds}{enlace}</tr>")
    n = len(filas) if total is None else total
    encabezado = (
        '<tr><th align="left">A&#241;o</th><th>Tipo Documento</th><th>N&#250;mero</th><th>Tem&#225;tica</th>'
        "<th>Descripci&#243;n Corta</th><th>Descripci&#243;n Larga</th><th>Fecha Documento</th><th></th></tr>"
    )
    return (
        '<html><body><form id="form_process"><table><tr><td>Año</td></tr></table></form>'
        f'<table class="cms-table">{encabezado}{"".join(trs)}</table>'
        f'{_pie_html(n) if con_pie else ""}</body></html>'
    )


def _html_sirel(filas, total=None, con_pie=True):
    """filas: (tipo, número, dependencia, tema, subtema, href, fecha)"""
    trs = []
    for tipo, num, dep, tema, sub, href, fecha in filas:
        trs.append(
            "<tr>"
            + "".join(f'<td align="left">\n{c}</td>' for c in (tipo, num, dep, tema, sub))
            + f'<td>\n<a href="{href}" target="_blank">\n<img src="images/icons/down.png"/>\nDocumento</a>\n</td>'
            + f'<td align="left">\n{fecha}</td></tr>'
        )
    n = len(filas) if total is None else total
    encabezado = (
        "<tr><th>Tipo Documento</th><th>N&#250;mero</th><th>Dependencia</th><th>Tema</th>"
        "<th>Subtema</th><th>Doc.</th><th>Fecha</th></tr>"
    )
    return (
        f'<html><body><form id="form_process"></form><table class="cms-table">{encabezado}{"".join(trs)}</table>'
        f'{_pie_html(n) if con_pie else ""}</body></html>'
    )


_HREF_REL = "https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId={}&mode=inline"


def _href_cto(doc_id):
    return (
        "https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoWeb"
        f"&elementId=PRODUCCION/RELATO_DATA_TYPE/2026/08/26/x{doc_id}.docx&docId={doc_id}"
        "&mode=1#page=inline,,toolbar=no,location=no"
    )


# ---- lectura de tabla ----
def test_pie_lee_total():
    assert _pie(_html_normativa([], total=84)) == 84
    assert _pie(_html_normativa([])) == 0


def test_pie_none_sin_pie():
    assert _pie("<html><body>Página Web No Disponible!</body></html>") is None


def test_filas_salta_encabezado_y_devuelve_celdas_y_href():
    html = _html_normativa([
        ("2025", "Directiva", "21", "Funciones de la Entidad", "Ley de Cuotas", "Cumplimiento…", "2025-12-19",
         _HREF_REL.format("MjQ0MTg1")),
        ("2018", "Circular", "7", "Funciones de la Entidad", "Apoyo Consular", "A ciudadanos…", "2018-10-23", None),
    ])
    filas = _filas(html)
    assert len(filas) == 2
    assert filas[0][0][:3] == ["2025", "Directiva", "21"]
    assert filas[0][1] == _HREF_REL.format("MjQ0MTg1")
    assert filas[1][1] is None


def test_filas_vacio_sin_tabla():
    assert _filas("<html><body></body></html>") == []


# ---- consulta paginada ----
def _sesion():
    s = requests.Session()
    s.headers.update({"User-Agent": "x"})
    return s


@responses.activate
def test_consultar_una_pagina():
    html = _html_normativa([("2025", "Circular", "1", "t", "c", "l", "2025-01-02", _HREF_REL.format("MQ=="))])
    responses.add(responses.GET, _RELATORIA, body=html)
    filas = _consultar(_sesion(), {"anio": "2025"})
    assert len(filas) == 1
    q = responses.calls[0].request.url
    assert "anio=2025" in q and "max_results=" in q and "first_result=0" in q


@responses.activate
def test_consultar_pagina_hasta_el_total(monkeypatch):
    import core.scrapers.families.procuraduria as mod
    monkeypatch.setattr(mod, "_PAGINA", 2)
    f = lambda i: ("2025", "Circular", str(i), "t", "c", "l", "2025-01-02", _HREF_REL.format(f"id{i}"))
    responses.add(responses.GET, _RELATORIA, body=_html_normativa([f(1), f(2)], total=3),
                  match=[matchers.query_param_matcher({"first_result": "0"}, strict_match=False)])
    responses.add(responses.GET, _RELATORIA, body=_html_normativa([f(3)], total=3),
                  match=[matchers.query_param_matcher({"first_result": "2"}, strict_match=False)])
    assert [c[2] for c, _ in _consultar(_sesion(), {"anio": "2025"})] == ["1", "2", "3"]


@responses.activate
def test_consultar_vacio_legitimo():
    responses.add(responses.GET, _RELATORIA, body=_html_normativa([]))
    assert _consultar(_sesion(), {"anio": "2027"}) == []


@responses.activate
def test_consultar_sin_pie_es_pagina_inesperada():
    responses.add(responses.GET, _RELATORIA, body="<html><body>Página Web No Disponible!</body></html>")
    with pytest.raises(_PaginaInesperada):
        _consultar(_sesion(), {"anio": "2025"})


@responses.activate
def test_consultar_conteo_que_no_cuadra_es_pagina_inesperada():
    html = _html_normativa([("2025", "Circular", "1", "t", "c", "l", "2025-01-02", _HREF_REL.format("MQ=="))], total=5)
    responses.add(responses.GET, _RELATORIA, body=html)
    with pytest.raises(_PaginaInesperada):
        _consultar(_sesion(), {"anio": "2025"})
