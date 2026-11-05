import datetime
import re
import threading

import requests
import responses

from core.scrapers.families.cc_armenia import (
    _ANIO_MINIMO,
    _SOURCE,
    _URL,
    _fecha,
    _nombre_archivo,
    ScrapCcArmenia,
)
from core.scrapers.registry import FAMILY_REGISTRY

_DOCS = "https://camaraarmenia.org.co/DocumentosCamara/Laudos/"


def _fila(radicado, demandante, demandado, fecha, archivo):
    # Copia de una fila real de la pestaña "Laudos" (href con espacios sin codificar).
    return (
        "<tr>\n"
        f'<td align="left">{radicado}</td>\n'
        f'<td align="left">{demandante}</td>\n'
        f'<td align="left">{demandado}</td>\n'
        f'<td align="left">{fecha}</td>\n'
        f'<td align="left"><a href="{_DOCS}{archivo}">Ver archivo</a></td>\n'
        "</tr>\n"
    )


_AGRO = _fila("20230515", "AGROPECUARIA ARCANGEL MIGUEL S.A.S", "GUILLERMO ROJAS PEÑA",
              "18 DE DICIEMBRE DE 2024", "LAUDO ARBITRAL AGROPECUARIA ARCANGEL GUILLERMO ROJAS PENA.pdf")
_PLATINIUM = _fila("20170306", "PLATINIUM IBÉRICA S.A.", "AICA S.A. ARQUITECTOS",
                   "06 DE MARZO 2017", "LAUDO ARBITRAL PLATINIUM IBERICA SA.pdf")
_QUIMBAYA = _fila("20220403", "UNIÓN TEMPORAL ALUMBRADO PÚBLICO QUIMBAYA", "MUNICIPIO DE QUIMBAYA",
                  "05 DE JULIO DE 2023", "LAUDO ARBITRAL UNION TEMPORAL ALUMBRADO PUBLICO QUIMBAYA.pdf")
_CIRCULAR = _fila("20220624", "MARTHA LIBIA CRUZ y DIMAS ALBERTO ARIAS", "GEO CASAMAESTRA S.A.S.",
                  "24 DE JUNIO DE 2022",
                  "Respuesta a la Invitacion a participar en la reglamentacion de la Ley 2445 de 2025 "
                  "CIRCULAR No MJD-CIR25-0000025-DMSC-20100.pdf")
_BARILOCHE = _fila("20060303", "BARILOCHE S.A", "FIDUCIARIA LA PREVISORA S.A.",
                   "03 DE MARZO DE 2006", "LAUDO ARBITRAL BARILOCHE SA.pdf")


def _pagina(*filas, tab_id="tab-9bad5edebe8f416b63c", label="fusion-tab-laudos"):
    return (
        "<html><body><div class=\"fusion-tabs\">"
        '<div aria-labelledby="fusion-tab-tarifas" class="tab-pane" id="tab-otro" role="tabpanel">'
        "<table><tr><td>1</td><td>2</td><td>3</td><td>4</td><td><a href=\"/tarifas.pdf\">x</a></td></tr></table></div>"
        f'<div aria-labelledby="{label}" class="tab-pane fade fusion-clearfix" id="{tab_id}" role="tabpanel">'
        '<table width="100%"><thead><tr>'
        "<th>Radicado</th><th>Demandante</th><th>Demandado</th><th>Fecha del Laudo</th><th>Archivo</th>"
        "</tr></thead><tbody>\n" + "".join(filas) + "</tbody></table></div></div></body></html>"
    ).encode("utf-8")


def _listado(*filas, status=200, **kw):
    responses.add(responses.GET, _URL, body=_pagina(*filas, **kw), status=status)


def _head(archivo, status=200):
    responses.add(responses.HEAD, _DOCS + archivo, status=status)


def _heads_ok():
    """HEAD 200 para cualquier PDF de la carpeta de laudos."""
    responses.add(responses.HEAD, re.compile(re.escape(_DOCS) + ".*"), status=200)


def _scrap(fini="2006-01-01", ffin="2026-12-31", **kw):
    return ScrapCcArmenia().scrap(fini, ffin, **kw)


def test_source_y_registro():
    assert _SOURCE == "Cámara de Comercio de Armenia y del Quindío"
    assert _ANIO_MINIMO == 2006
    assert FAMILY_REGISTRY["cc_armenia"] is ScrapCcArmenia


def test_fecha_tolera_el_de_faltante():
    assert _fecha("18 DE DICIEMBRE DE 2024") == datetime.date(2024, 12, 18)
    assert _fecha("06 DE MARZO 2017") == datetime.date(2017, 3, 6)
    assert _fecha("31 DE FEBRERO DE 2020") is None
    assert _fecha("PENDIENTE") is None


def test_nombre_archivo_decodifica_y_toma_el_ultimo_segmento():
    assert _nombre_archivo(_DOCS + "LAUDO%20ARBITRAL%20X.pdf") == "LAUDO ARBITRAL X.pdf"
    assert _nombre_archivo(_DOCS + "Circular.pdf") == "Circular.pdf"


@responses.activate
def test_fila_a_documento():
    _listado(_AGRO)
    _heads_ok()

    [doc] = _scrap()

    assert doc.title == "LA_CCAQ_20230515_2024"
    assert doc.tipo == "Laudo arbitral"
    assert doc.f_public == doc.f_providencia == "2024-12-18"
    assert doc.detalle == "AGROPECUARIA ARCANGEL MIGUEL S.A.S vs GUILLERMO ROJAS PEÑA"
    assert doc.link == {"url": _DOCS + "LAUDO ARBITRAL AGROPECUARIA ARCANGEL GUILLERMO ROJAS PENA.pdf", "method": "GET"}
    assert doc.title_unverified is False
    assert doc.save_path == f"{_SOURCE}/2024-12-18/Laudo arbitral/LA_CCAQ_20230515_2024(extension)"


@responses.activate
def test_fecha_sin_segundo_de():
    _listado(_PLATINIUM)
    _heads_ok()

    [doc] = _scrap()

    assert doc.f_providencia == "2017-03-06"
    assert doc.title == "LA_CCAQ_20170306_2017"


@responses.activate
def test_anio_del_titulo_sale_de_la_fecha_no_del_radicado():
    _listado(_QUIMBAYA)
    _heads_ok()

    [doc] = _scrap()

    assert doc.title == "LA_CCAQ_20220403_2023"


@responses.activate
def test_rango_y_piso():
    _listado(_BARILOCHE, _QUIMBAYA, _AGRO, _fila("20050101", "A", "B", "01 DE MARZO DE 2005", "LAUDO VIEJO.pdf"))
    _heads_ok()

    assert [d.title for d in _scrap("2023-01-01", "2023-12-31")] == ["LA_CCAQ_20220403_2023"]
    assert [d.title for d in _scrap("2000-01-01", "2026-12-31")] == [
        "LA_CCAQ_20060303_2006", "LA_CCAQ_20220403_2023", "LA_CCAQ_20230515_2024",
    ]


@responses.activate
def test_archivo_sin_laudo_en_el_nombre_se_descarta_aunque_la_ruta_diga_laudos():
    minusculas = _fila("20240419", "CÁMARA DE COMERCIO", "RIVIERA PARK S.A.S.",
                       "20 DE ENERO DE 2025", "laudo%20arbitral%20riviera.pdf")
    _listado(_CIRCULAR, minusculas)
    _heads_ok()
    avisos = []

    docs = _scrap(on_progress=avisos.append)

    assert [d.title for d in docs] == ["LA_CCAQ_20240419_2025"]
    assert any("20220624" in a and "no es un laudo" in a for a in avisos)


@responses.activate
def test_pdf_que_no_responde_se_descarta():
    roto = _fila("20221111", "SOLUCIONES INTEGRALES", "CONSTRUCCIONES BUENDÍA",
                 "01 DE OCTUBRE DE 2024", "LAUDO ARBITRAL SIIA.pdf")
    _listado(roto, _AGRO)
    _head("LAUDO ARBITRAL SIIA.pdf", status=404)
    _head("LAUDO ARBITRAL AGROPECUARIA ARCANGEL GUILLERMO ROJAS PENA.pdf")
    avisos = []

    docs = _scrap(on_progress=avisos.append)

    assert [d.title for d in docs] == ["LA_CCAQ_20230515_2024"]
    assert any("LA_CCAQ_20221111_2024" in a and "no existe" in a for a in avisos)


@responses.activate
def test_tabla_se_ubica_por_el_encabezado_aunque_cambie_el_id():
    _listado(_AGRO, tab_id="tab-nuevo123")
    _heads_ok()

    assert [d.title for d in _scrap()] == ["LA_CCAQ_20230515_2024"]


@responses.activate
def test_pagina_sin_pestana_de_laudos():
    _listado(_AGRO, tab_id="otro", label="fusion-tab-otro")
    avisos = []

    assert _scrap(on_progress=avisos.append) == []
    assert any("pestaña de laudos" in a for a in avisos)


@responses.activate
def test_fila_sin_fecha_o_sin_radicado():
    _listado(
        _fila("20230515", "A", "B", "PENDIENTE", "LAUDO A.pdf"),
        _fila("", "C", "D", "18 DE DICIEMBRE DE 2024", "LAUDO C.pdf"),
        _PLATINIUM,
    )
    _heads_ok()
    avisos = []

    docs = _scrap(on_progress=avisos.append)

    assert [d.title for d in docs] == ["LA_CCAQ_20170306_2017"]
    assert any("sin fecha legible" in a for a in avisos)
    assert any("sin radicado legible" in a for a in avisos)


@responses.activate
def test_dedup_por_url():
    _listado(_AGRO, _AGRO)
    _heads_ok()
    avisos = []

    assert len(_scrap(on_progress=avisos.append)) == 1
    assert any("repite" in a for a in avisos)


@responses.activate
def test_limit_y_stop_event():
    _listado(_BARILOCHE, _PLATINIUM, _AGRO)
    _heads_ok()

    assert len(_scrap(limit=2)) == 2

    parar = threading.Event()
    parar.set()
    assert _scrap(stop_event=parar) == []


@responses.activate
def test_error_de_la_pagina():
    _listado(status=500)
    avisos = []

    assert _scrap(on_progress=avisos.append) == []
    assert any("Error consultando" in a for a in avisos)


def test_corrida_diaria_mira_hasta_el_piso():
    desde = datetime.date.today() - datetime.timedelta(days=ScrapCcArmenia.scheduled_min_lookback_days)
    assert desde <= datetime.date(_ANIO_MINIMO, 1, 1)


@responses.activate
def test_enlace_relativo_se_completa_con_el_dominio():
    # Hallazgo de la revisión del PR #110: un href relativo (lo que guarda
    # WordPress si el editor pega una ruta) se usaba tal cual; la consulta
    # previa fallaba y el laudo se saltaba en silencio.
    relativo = _fila("20230515", "AGROPECUARIA", "ROJAS", "18 DE DICIEMBRE DE 2024", "LAUDO ARBITRAL AGRO.pdf")
    relativo = relativo.replace(_DOCS, "/DocumentosCamara/Laudos/")
    _listado(relativo)
    _heads_ok()

    [doc] = _scrap()

    assert doc.link["url"] == _DOCS + "LAUDO ARBITRAL AGRO.pdf"


@responses.activate
def test_si_la_consulta_previa_no_es_concluyente_el_laudo_se_incluye():
    # Hallazgo de la revisión del PR #110: cualquier respuesta distinta de 200
    # (405 si el servidor no acepta HEAD, 403 de un firewall, 5xx, un corte de
    # red) descartaba el laudo con un simple aviso, en todas las corridas.
    # Solo "no existe" (404/410) lo descarta; en los demás casos se incluye y
    # la descarga decide: si falla, queda como error visible de la corrida.
    a = _fila("1", "A", "B", "01 DE ENERO DE 2024", "LAUDO 1.pdf")
    b = _fila("2", "A", "B", "01 DE ENERO DE 2024", "LAUDO 2.pdf")
    c = _fila("3", "A", "B", "01 DE ENERO DE 2024", "LAUDO 3.pdf")
    d = _fila("4", "A", "B", "01 DE ENERO DE 2024", "LAUDO 4.pdf")
    _listado(a, b, c, d)
    _head("LAUDO 1.pdf", status=405)
    _head("LAUDO 2.pdf", status=503)
    responses.add(responses.HEAD, _DOCS + "LAUDO 3.pdf", body=requests.exceptions.ConnectionError("corte"))
    _head("LAUDO 4.pdf", status=410)

    assert [doc.title for doc in _scrap()] == ["LA_CCAQ_1_2024", "LA_CCAQ_2_2024", "LA_CCAQ_3_2024"]
