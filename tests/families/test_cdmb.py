import datetime
import threading

import responses
from responses import matchers

from core.scrapers.families.cdmb import (
    _ACU_URL,
    _ANIO_MINIMO,
    _RES_URL,
    _SOURCE,
    _fecha,
    _numero,
    _titulo,
    ScrapCdmb,
)
from core.scrapers.registry import FAMILY_REGISTRY


def _fila_res(num, fecha, ref="POR MEDIO DE LA CUAL SE RESUELVE RECURSO DE REPOSICIÓN", pdf="dc085f34b270a559d095"):
    # Copia de una fila real de res_consulta.php (href con espacio final,
    # </a> suelto en la referencia).
    return (
        "<tr>\n"
        f'  <td align="center" class="Estilo13"><a target=_blank href="./resoluciones/{pdf}.pdf ">{num}</a></td>\n'
        f'  <td><span class="Estilo13">{fecha}</span></td>\n'
        f'  <td><span class="sombreado">{ref}</a></span></td>\n'
        f"  <TD class=texcontenido bgcolor=#EEEDED ALIGN=CENTER><a target=_blank href=res_consdet.php?resolucion={num}&anhoc=2026>"
        "<img src ='imagenes/completar_ico.gif' border=0 height=23 ALT='Consultar Resolución'></a></TD>\n"
        "    </tr>\n"
    )


def _fila_acu(num, fecha, pdf="8b39b2c720d5c6c1dc5a.pdf", ref="POR MEDIO DEL CUAL SE SUSTRAE UN ÁREA DEL DRMI"):
    return (
        "<tr>\n"
        f'  <td align="center" class="Estilo13"><a href="./acuerdos/{pdf}">{num}</a></td>\n'
        f'  <td><span class="Estilo13">{fecha}</span></td>\n'
        f'  <td><span class="sombreado"> {ref}</a></span></td>\n'
        "  <!-- <TD class=texcontenido bgcolor=#EEEDED ALIGN=CENTER><a href=acu_consdet.php?num_acuerdo=&anho=&bloque=0>"
        "<img src ='imagenes/completar_ico.gif' border=0 height=23 ALT='Consultar Acuerdo'></a></TD>  -->\n"
        f"  <TD class=texcontenido bgcolor=#EEEDED ALIGN=CENTER><a href=acu_consdet.php?num_acuerdo={num}&bloque=0>"
        "<img src ='imagenes/completar_ico.gif' border=0 height=23 ALT='Consultar Acuerdo'></a></TD>\n"
        "    </tr>\n"
    )


def _pagina(*filas) -> bytes:
    html = (
        "<html><body><table><tbody>\n"
        '  <tr class="TABLA_ENCABEZADO_USUARIOS_NEW">\n'
        '    <th class="letratablas">Número</th><th>Fecha</th><th>Referencia</th><th>Ver</th>\n'
        " </tr>\n" + "".join(filas) + "</tbody></table></body></html>"
    )
    return html.encode("cp1252")


def _res_body(anio):
    return matchers.urlencoded_params_matcher(
        {"ob": "0", "anhoc": str(anio), "palabras": "", "botonenv": "Buscar"}, allow_blank=True
    )


def _acuerdos(*paginas):
    """Registra las páginas de acuerdos y una página final vacía."""
    for i, filas in enumerate(list(paginas) + [()]):
        responses.add(
            responses.GET, _ACU_URL, body=_pagina(*filas),
            match=[matchers.query_param_matcher({"bloque": str(i * 30)})],
        )


def _res(anio, *filas, status=200):
    responses.add(responses.POST, _RES_URL, body=_pagina(*filas), status=status, match=[_res_body(anio)])


def test_source_y_registro():
    assert _SOURCE == "Corporación Autónoma Regional para la Defensa de la Meseta de Bucaramanga"
    assert _ANIO_MINIMO == 2025
    assert FAMILY_REGISTRY["cdmb"] is ScrapCdmb
    assert ScrapCdmb.scheduled_min_lookback_days == 90
    assert ScrapCdmb.checks_for_republication is True


def test_helpers():
    assert _fecha("09/10/2026") == datetime.date(2026, 10, 9)
    assert _fecha("31/02/2026") is None
    assert _fecha("") is None
    assert _numero("1298") == 1298
    assert _numero("-1295") == 1295
    assert _numero("") is None
    assert _titulo("R", 45, 2025) == "R_CDMB_0045_2025"


@responses.activate
def test_resolucion_parseada():
    _res(2026, _fila_res(1298, "09/10/2026"), _fila_res(45, "02/01/2026", pdf="aaaa"))
    _acuerdos()
    docs = ScrapCdmb().scrap("2026-01-01", "2026-10-21")
    assert [d.title for d in docs] == ["R_CDMB_1298_2026", "R_CDMB_0045_2026"]
    d = docs[0]
    assert d.tipo == "Resolución"
    assert d.f_public == d.f_providencia == "2026-10-09"
    assert d.link == {"url": "http://caracoli.cdmb.gov.co/gdi/resoluciones/dc085f34b270a559d095.pdf", "method": "GET"}
    assert d.title_unverified is False
    # cp1252 bien decodificado
    assert d.detalle == "POR MEDIO DE LA CUAL SE RESUELVE RECURSO DE REPOSICIÓN"
    assert d.save_path == f"{_SOURCE}/2026-10-09/Resolución/R_CDMB_1298_2026(extension)"


@responses.activate
def test_un_post_por_anio_y_piso():
    _res(2025, _fila_res(900, "15/12/2025", pdf="a"), _fila_res(800, "10/11/2025", pdf="b"))
    _res(2026, _fila_res(3, "20/01/2026", pdf="c"))
    _acuerdos()
    docs = ScrapCdmb().scrap("2023-01-01", "2026-01-31")
    posts = [c.request for c in responses.calls if c.request.method == "POST"]
    assert [p.body for p in posts] == [
        "ob=0&anhoc=2025&palabras=&botonenv=Buscar",
        "ob=0&anhoc=2026&palabras=&botonenv=Buscar",
    ]
    assert [d.title for d in docs] == ["R_CDMB_0900_2025", "R_CDMB_0800_2025", "R_CDMB_0003_2026"]


@responses.activate
def test_cruce_de_anio_y_filtro_por_fecha_de_fila():
    # El listado de un año puede traer filas de otro: se filtra por la fila.
    _res(2025, _fila_res(900, "15/12/2025", pdf="a"), _fila_res(800, "10/11/2025", pdf="b"),
         _fila_res(1, "05/02/2026", pdf="x"))
    _res(2026, _fila_res(3, "20/01/2026", pdf="c"))
    _acuerdos()
    docs = ScrapCdmb().scrap("2025-12-01", "2026-01-31")
    assert [d.title for d in docs] == ["R_CDMB_0900_2025", "R_CDMB_0003_2026"]


@responses.activate
def test_acuerdos_paginados_y_anio_de_la_fecha():
    _res(2026)
    _acuerdos(
        [_fila_acu(1511, "26/06/2026", pdf="p1.pdf"), _fila_acu(1504, "20/12/2025", pdf="p2.pdf")],
        [_fila_acu(1484, "10/01/2025", pdf="p3.pdf"), _fila_acu(1400, "10/01/2022", pdf="p4.pdf")],
    )
    docs = ScrapCdmb().scrap("2026-01-01", "2026-10-21")
    gets = [c.request.url for c in responses.calls if c.request.method == "GET"]
    assert [u.split("bloque=")[1] for u in gets] == ["0", "30", "60"]
    assert [d.title for d in docs] == ["A_CDMB_1511_2026"]
    assert docs[0].tipo == "Acuerdo"
    assert docs[0].link["url"] == "http://caracoli.cdmb.gov.co/gdi/acuerdos/p1.pdf"
    assert docs[0].detalle.startswith("POR MEDIO DEL CUAL SE SUSTRAE UN ÁREA")


@responses.activate
def test_acuerdo_negativo_y_eliminado():
    _res(2025)
    _acuerdos([_fila_acu(-1490, "10/05/2025", pdf="neg.pdf"), _fila_acu(1491, "11/05/2025", pdf="ELIMINADO")])
    avisos = []
    docs = ScrapCdmb().scrap("2025-01-01", "2025-12-31", on_progress=avisos.append)
    assert [d.title for d in docs] == ["A_CDMB_1490_2025"]
    assert any("1491" in a and "sin PDF" in a for a in avisos)


@responses.activate
def test_fecha_futura_avisada_y_fuera_de_rango():
    futura = (datetime.date.today() + datetime.timedelta(days=60)).strftime("%d/%m/%Y")
    hoy = datetime.date.today().isoformat()
    _res(int(hoy[:4]), _fila_res(10, futura, pdf="f"))
    _acuerdos([_fila_acu(1600, "01/01/2109", pdf="x.pdf")])
    avisos = []
    docs = ScrapCdmb().scrap(f"{hoy[:4]}-01-01", hoy, on_progress=avisos.append)
    assert docs == []
    assert sum("fecha futura" in a for a in avisos) == 2


@responses.activate
def test_fila_sin_fecha():
    _res(2026, _fila_res(7, "sin fecha", pdf="s"), _fila_res(8, "01/03/2026", pdf="t"))
    _acuerdos()
    avisos = []
    docs = ScrapCdmb().scrap("2026-01-01", "2026-12-31", on_progress=avisos.append)
    assert [d.title for d in docs] == ["R_CDMB_0008_2026"]
    assert any("sin fecha" in a for a in avisos)


@responses.activate
def test_dedup_por_url():
    _res(2026, _fila_res(8, "01/03/2026", pdf="mismo"), _fila_res(9, "02/03/2026", pdf="mismo"))
    _acuerdos()
    avisos = []
    docs = ScrapCdmb().scrap("2026-01-01", "2026-12-31", on_progress=avisos.append)
    assert [d.title for d in docs] == ["R_CDMB_0008_2026"]
    assert any("repite" in a for a in avisos)


@responses.activate
def test_stop_event_corta():
    _res(2026, _fila_res(8, "01/03/2026", pdf="a"), _fila_res(9, "02/03/2026", pdf="b"))
    _acuerdos([_fila_acu(1511, "26/06/2026", pdf="p1.pdf")])
    stop = threading.Event()

    def progreso(texto):
        if "Procesando Acuerdo" in texto:
            stop.set()

    docs = ScrapCdmb().scrap("2026-01-01", "2026-12-31", stop_event=stop, on_progress=progreso)
    assert [d.title for d in docs] == ["R_CDMB_0008_2026", "R_CDMB_0009_2026"]
    assert not any(c.request.method == "GET" for c in responses.calls)


@responses.activate
def test_falla_de_resoluciones_no_tumba_acuerdos():
    _res(2026, status=500)
    _acuerdos([_fila_acu(1511, "26/06/2026", pdf="p1.pdf")])
    avisos = []
    docs = ScrapCdmb().scrap("2026-01-01", "2026-12-31", on_progress=avisos.append)
    assert [d.title for d in docs] == ["A_CDMB_1511_2026"]
    assert any("Error consultando Resolución" in a for a in avisos)


@responses.activate
def test_limit():
    _res(2026, *[_fila_res(n, "01/03/2026", pdf=f"p{n}") for n in range(1, 6)])
    _acuerdos()
    docs = ScrapCdmb().scrap("2026-01-01", "2026-12-31", limit=3)
    assert len(docs) == 3
    assert not any(c.request.method == "GET" for c in responses.calls)
