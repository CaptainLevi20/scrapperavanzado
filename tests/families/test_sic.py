import random
import threading
from datetime import date
from urllib.parse import parse_qs, urlparse

import requests
import responses

from core.scrapers.families.sic import (
    _BASE,
    _LISTADO,
    ScrapSIC,
    _PresupuestoAgotado,
    _anios,
    _enumerar_tajada,
    _CLAS_CIR,
    _CLAS_DOC,
    _CLAS_RES,
    _CLAS_TCU,
    _TIPO_CIR,
    _TIPO_CTO,
    _TIPO_REL,
    _TIPO_RES,
    _TIPO_TCU,
    _clasificar,
    _crudo,
    _safe_title,
    _titulo,
    _ficha,
    _filas_listado,
    _num_paginas,
)

# Marcado real del listado (recortado), 2026-10-07
_FILA = """
<div class="mb-2"><div style="width: 100%;"><div class="views-field views-field-nothing"><span class="field-content"><div class="normas--row shadow-sm p-3 mb-5 bg-body rounded">
	<div class="row">
		<div class="col-md-5">
<span class="text-secondary">Tipo de norma: <strong>Resoluciones  </strong></span>
		</div>
		<div class="col-md-7">
<span class="badge tag--pin label--pin mb-2 ms-2">Despacho de la Superintendencia </span>
		</div>
	</div>
<h2 class="field__label"><a href="{href}" hreflang="es">{titulo}</a></h2>
<div class="col-md-12">
<p> resumen </p>
</div>
</div></span></div></div></div>
"""


def _listado(filas, encabezado="Mostrando la página 1 de 8 páginas"):
    cuerpo = "".join(_FILA.format(href=h, titulo=t) for h, t in filas)
    return f"<html><body><main><div>{encabezado}</div>{cuerpo}</main></body></html>"


def test_filas_listado_extrae_href_y_titulo_limpio():
    html = _listado([
        ("/transparencia/normativa/resolucion-no-77121", "Resolución No. 77121 del 29 de septiembre de 2026 &quot;Por la cual se deroga&quot;"),
        ("/transparencia/normativa/circular-externa-010", "Circular\xa0Externa  010"),
    ])
    assert _filas_listado(html) == [
        ("/transparencia/normativa/resolucion-no-77121",
         'Resolución No. 77121 del 29 de septiembre de 2026 "Por la cual se deroga"'),
        ("/transparencia/normativa/circular-externa-010", "Circular Externa 010"),
    ]


def test_filas_listado_vacio():
    assert _filas_listado("<html><main>Sin resultados</main></html>") == []


def test_num_paginas_lee_el_encabezado():
    assert _num_paginas(_listado([("/a", "x")])) == 8
    assert _num_paginas(_listado([("/a", "x")], "Mostrando la página 1 de 379 páginas")) == 379


def test_num_paginas_sin_encabezado():
    assert _num_paginas(_listado([("/a", "x")], encabezado="")) == 1
    assert _num_paginas(_listado([], encabezado="")) == 0


# Marcado real de una ficha (recortado), 2026-10-07
_FICHA = """
<html><body><main>
<div class="sic--fecha1">
  <div class="field field--name-field-fecha-generacion field--type-datetime field--label-above">
    <div class="field__label">Fecha Expedición</div>
    <div class="field__item"><time datetime="2026-09-29T12:00:00Z" class="datetime">Sep 29, 2026</time></div>
  </div>
</div>
<div class="sic--fecha2">
  <div class="field field--name-field-fecha-publicacion field--type-datetime field--label-above">
    <div class="field__label">Fecha publicación</div>
    <div class="field__item"><time datetime="2026-09-30T12:00:00Z" class="datetime">Sep 30, 2026</time></div>
  </div>
</div>
{adjuntos}
<a href="https://sedeelectronica.sic.gov.co/sites/default/files/normativa/T%C3%A9rminos%20y%20condiciones%20-Sede%20Electr%C3%B3nica.pdf">Términos</a>
</main></body></html>
"""

_ADJUNTOS = """
<div class="sic--adjuntos">
  <div class="field field--name-field-archivo field--type-file field--label-above">
    <div class="field__label">Archivos adjuntos</div>
    <div class="field__items">
      {items}
    </div>
  </div>
</div>
"""

_ITEM = """<div class="field__item"><span class="file file--mime-application-pdf file--application-pdf">
  <a href="{href}" type="application/pdf" target="_blank">Documento<span class="visually-hidden"> (se abrirá en una nueva pestaña)</span></a>
  <p>(276.91 KB)</p></span></div>"""


def _html_ficha(*hrefs):
    adj = _ADJUNTOS.format(items="".join(_ITEM.format(href=h) for h in hrefs)) if hrefs else ""
    return _FICHA.format(adjuntos=adj)


def test_ficha_fechas_y_pdf():
    f = _ficha(_html_ficha("/sites/default/files/normativa/RESOLUCI%C3%93N%2077121%20DE%202026.pdf"))
    assert f.expedicion == "2026-09-29"
    assert f.publicacion == "2026-09-30"
    assert f.pdfs == [f"{_BASE}/sites/default/files/normativa/RESOLUCI%C3%93N%2077121%20DE%202026.pdf"]


def test_ficha_varios_adjuntos_en_orden_y_sin_duplicados():
    f = _ficha(_html_ficha("/sites/default/files/a.pdf", "/sites/default/files/b.pdf", "/sites/default/files/a.pdf"))
    assert f.pdfs == [f"{_BASE}/sites/default/files/a.pdf", f"{_BASE}/sites/default/files/b.pdf"]


def test_ficha_solo_enlace_externo_no_tiene_pdfs():
    # el enlace global "Términos y condiciones" está fuera de field-archivo y no cuenta
    html = _html_ficha().replace(
        "</main>",
        '<div class="sic--enlace"><a href="javascript:void(0)" onclick="showModal(\'https\\u003A\\/\\/www.mintrabajo.gov.co\\/x\')">Ingresa</a></div></main>',
    )
    f = _ficha(html)
    assert f.pdfs == []
    assert f.expedicion == "2026-09-29"


def test_ficha_sin_fechas():
    f = _ficha("<html><main><p>nada</p></main></html>")
    assert (f.expedicion, f.publicacion, f.pdfs) == (None, None, [])


def test_clasificar_resoluciones_incluye_nombramientos():
    assert _clasificar(_CLAS_RES, 'Resolución No. 77121 del 29 de septiembre de 2026 "Por la cual se deroga"') == _TIPO_RES
    assert _clasificar(_CLAS_RES, "Resolución No. 29705 de 2026 PROFESIONAL U. 2044-07 G.T. REGULACIÓN - OFICINA ASESORA JURÍDICA") == _TIPO_RES


def test_clasificar_descarta_proyectos():
    assert _clasificar(_CLAS_RES, "Proyecto de Resolución “Por la cual se adicionan incisos”") is None
    assert _clasificar(_CLAS_CIR, "Proyecto de Circular Externa la cual tiene como asunto") is None


def test_clasificar_descarta_otra_entidad_por_la_cabeza_del_titulo():
    assert _clasificar(_CLAS_RES, "Resolución 7356 de 2024 de la Comisión de Regulación de Comunicaciones, “Por la cual”") is None
    assert _clasificar(_CLAS_RES, "Resolución 0612 de 2024 del Ministerio de Comercio Industria y Turismo, “Por la cual”") is None
    assert _clasificar(_CLAS_RES, 'Resolución 862 de 2023 de la Dirección de Regulación del Ministerio de Comercio, "Por la cual"') is None
    assert _clasificar(_CLAS_CIR, "Circular Externa 1 de 2023 - De la Agencia Nacional de Defensa Jurídica del Estado, “Lineamientos”") is None


def test_clasificar_no_descarta_sic_que_cita_un_ministerio_en_su_epigrafe():
    assert _clasificar(_CLAS_RES, 'Resolución No. 1111 del 24 de enero de 2025 "Por medio de la cual se fija la tasa del Ministerio de Comercio"') == _TIPO_RES
    assert _clasificar(_CLAS_RES, 'Resolución No 122 de 2025 de la Superintendencia de Industria y Comercio, "Por la cual"') == _TIPO_RES
    assert _clasificar(_CLAS_RES, "Resolución 1059 por la cual se reglamenta lo del Ministerio") == _TIPO_RES


def test_clasificar_titulos_circular_unica():
    assert _clasificar(_CLAS_TCU, "Título X - Actualizado el 30 de enero de 2026.") == _TIPO_TCU
    assert _clasificar(_CLAS_TCU, 'Resolución No. 62932 de 2025 "Por la cual se adiciona"') == _TIPO_RES


def test_clasificar_doctrina():
    assert _clasificar(_CLAS_DOC, "Concepto 15-159447 del 25 de agosto de 2015") == _TIPO_CTO
    assert _clasificar(_CLAS_DOC, "RELATORÍA RESOLUCIÓN 27305 - 10-07-2019 - CONCONCRETO") == _TIPO_REL
    assert _clasificar(_CLAS_DOC, "Resolución No. 3839 del 4 de febrero de 2015") == _TIPO_RES
    for otro in (
        "Sentencia Expediente Radicación 2007 00102 02 del 16 de febrero de 2017 Consejo Estado",
        "Radicado No. 2016-01884-01 del 12 de octubre de 2016 Consejo Superior de la Judicatura",
        "Informe de gestión 2016", "Acta 3 de 2016", "Estudio de mercado", "Auto 123",
    ):
        assert _clasificar(_CLAS_DOC, otro) is None, otro


def test_titulo_resolucion():
    assert _titulo(_TIPO_RES, 'Resolución No. 77121 del 29 de septiembre de 2026 "Por la cual"', "2026-09-29") == ("R_SIC_77121_2026", False)
    assert _titulo(_TIPO_RES, "RESOLUCIÓN 000610 DE 13 DE ABRIL DE 2026", "2026-04-13") == ("R_SIC_0610_2026", False)
    assert _titulo(_TIPO_RES, "Resolución Número 122 de 2025", "2025-01-10") == ("R_SIC_0122_2025", False)
    assert _titulo(_TIPO_RES, "Resolución N° 4.231 de 2024", "2024-02-22") == ("R_SIC_4231_2024", False)


def test_titulo_resolucion_tolera_erratas_reales_del_sitio():
    # caso real 2025: "Reolución 56937 de 2025 Profesional U. 2044-07 …"
    assert _titulo(_TIPO_RES, "Reolución 56937 de 2025 Profesional U. 2044-07", "2025-07-01") == ("R_SIC_56937_2025", False)
    assert _titulo(_TIPO_RES, "Rsolución 100 de 2025", "2025-07-01") == ("R_SIC_0100_2025", False)


def test_titulo_circular_todas_con_c():
    assert _titulo(_TIPO_CIR, "Circular Externa No 4 de 2024 de la Superintendencia", "2024-05-02") == ("C_SIC_0004_2024", False)
    assert _titulo(_TIPO_CIR, "Circular Interna No. 006 del 17 de marzo de 2025", "2025-03-17") == ("C_SIC_0006_2025", False)
    assert _titulo(_TIPO_CIR, "Circular Conjunta 010 de 2026", "2026-02-08") == ("C_SIC_0010_2026", False)
    assert _titulo(_TIPO_CIR, "Circular 011 de 2020", "2020-07-01") == ("C_SIC_0011_2020", False)
    assert _titulo(_TIPO_CIR, "Circular Externa 001 del 2026", "2026-01-15") == ("C_SIC_0001_2026", False)


def test_titulo_circular_sin_numero_queda_sin_verificar():
    assert _titulo(_TIPO_CIR, "Circular Única de Calidad Turística", "2026-02-06") == ("Circular Única de Calidad Turística", True)


def test_titulo_circular_unica_romano_y_fecha_de_version():
    assert _titulo(_TIPO_TCU, "Título X - Actualizado el 30 de enero de 2026.", "2026-01-30") == ("TCU_SIC_X_20260130", False)
    assert _titulo(_TIPO_TCU, "TÍTULO II", "2021-03-23") == ("TCU_SIC_II_20210323", False)
    assert _titulo(_TIPO_TCU, "Titulo I.", "2022-09-29") == ("TCU_SIC_I_20220929", False)
    assert _titulo(_TIPO_TCU, "Título X Propiedad Industrial", "2022-01-17") == ("TCU_SIC_X_20220117", False)


def test_titulo_concepto_radicado():
    assert _titulo(_TIPO_CTO, "Concepto 15-159447 del 25 de agosto de 2015", "2015-08-25") == ("CTO_SIC_15-159447", False)
    assert _titulo(_TIPO_CTO, "Concepto 17 49443 del 28 de marzo de 2017", "2017-03-28") == ("CTO_SIC_17-49443", False)
    assert _titulo(_TIPO_CTO, "Concepto sobre publicidad", "2016-01-01") == ("Concepto sobre publicidad", True)


def test_titulo_relatoria():
    assert _titulo(_TIPO_REL, "RELATORÍA RESOLUCIÓN 27305 - 10-07-2019 - CONCONCRETO", "2019-07-10") == ("REL_SIC_27305_2019", False)
    assert _titulo(_TIPO_REL, "RELATORÍA RESOLUCIÓN 56158 DEL 31-08-2021 - RESUELVE RECURSO - ASE", "2021-08-31") == ("REL_SIC_56158_2021", False)


def test_crudo_y_safe_title():
    assert _crudo("  ") == "documento"
    assert _crudo("x" * 200) == "x" * 120
    assert _crudo("Título final. ") == "Título final"
    assert _safe_title('Resolución "X": a/b') == "Resolución -X-- a-b"


# el sitio real declara charset=UTF-8; sin él requests decodifica en latin-1
_HTML = {"Content-Type": "text/html; charset=UTF-8"}


def _sitio_inestable(todos, semilla=1, modo="azar"):
    """Callback de `responses` que imita el buscador real, con búsqueda
    `combine` por 'contiene' sobre el título. `modo`:
    - "azar": reordena al azar en cada petición (filas repetidas y perdidas)
    - "pierde": toda página no final devuelve las 20 primeras (pérdida segura)
    - "estable": paginación correcta"""
    rnd = random.Random(semilla)

    def cb(request):
        qs = parse_qs(urlparse(request.url).query)
        combine = qs.get("combine", [""])[0]
        lista = [(h, t) for h, t in todos if combine in t] if combine else list(todos)
        if not lista:
            return (200, _HTML, _listado([], encabezado=""))
        n = (len(lista) + 19) // 20
        p = int(qs.get("page", ["0"])[0])
        orden = list(lista)
        if n > 1 and modo == "azar":
            rnd.shuffle(orden)  # el "orden" cambia en cada petición
        if p == n - 1:
            pagina = orden[(n - 1) * 20:] if modo == "estable" else orden[: len(lista) - (n - 1) * 20]
        elif modo == "estable":
            pagina = orden[p * 20:(p + 1) * 20]
        else:
            pagina = orden[:20]
        return (200, _HTML, _listado(pagina, encabezado=f"Mostrando la página {p + 1} de {n} páginas"))

    return cb


def _docs(n):
    return [(f"/transparencia/normativa/r-{i}", f"Resolución {10000 + i * 37} de 2025 PROFESIONAL") for i in range(n)]


@responses.activate
def test_enumerar_tajada_una_pagina_no_busca_por_fragmentos():
    todos = _docs(15)
    responses.add_callback(responses.GET, _LISTADO, callback=_sitio_inestable(todos))
    pres = [100]
    got = _enumerar_tajada(requests.Session(), _CLAS_RES, 2025, pres, None, None)
    assert got == dict(todos)
    assert len(responses.calls) == 1
    qs = parse_qs(urlparse(responses.calls[0].request.url).query)
    assert qs["field_clasificacion2_target_id"] == ["177"]
    assert qs["field_fecha_publicacion_value"] == ["2025"]


@responses.activate
def test_enumerar_tajada_vacia():
    responses.add_callback(responses.GET, _LISTADO, callback=_sitio_inestable([]))
    assert _enumerar_tajada(requests.Session(), _CLAS_DOC, 2026, [100], None, None) == {}


@responses.activate
def test_enumerar_tajada_completa_pese_al_reordenamiento():
    todos = _docs(130)  # 7 páginas
    responses.add_callback(responses.GET, _LISTADO, callback=_sitio_inestable(todos))
    progreso = []
    got = _enumerar_tajada(requests.Session(), _CLAS_RES, 2025, [4000], None, progreso.append)
    assert got == dict(todos)
    assert not any("faltan" in m for m in progreso)


@responses.activate
def test_enumerar_tajada_no_busca_fragmentos_si_las_paginas_ya_completan():
    todos = _docs(45)  # 3 páginas
    responses.add_callback(responses.GET, _LISTADO, callback=_sitio_inestable(todos, modo="estable"))
    pres = [4000]
    got = _enumerar_tajada(requests.Session(), _CLAS_RES, 2025, pres, None, None)
    assert got == dict(todos)
    assert not any("combine=" in c.request.url for c in responses.calls)
    assert len(responses.calls) == 3          # página 0, última, página 1
    assert pres[0] == 4000 - 3


@responses.activate
def test_enumerar_tajada_avisa_cuando_faltan():
    # títulos sin dígitos: la búsqueda por fragmentos no puede encontrarlos, y
    # el sitio "pierde" la página del medio
    todos = [(f"/transparencia/normativa/x-{i}", "Por la cual se suspenden términos") for i in range(60)]
    responses.add_callback(responses.GET, _LISTADO, callback=_sitio_inestable(todos, modo="pierde"))
    progreso = []
    got = _enumerar_tajada(requests.Session(), _CLAS_RES, 2025, [4000], None, progreso.append)
    assert len(got) < 60
    assert any(f"faltan {60 - len(got)}" in m and m.startswith("[Superintendencia de Industria y Comercio] Error") for m in progreso)


@responses.activate
def test_enumerar_tajada_presupuesto_agotado():
    responses.add_callback(responses.GET, _LISTADO, callback=_sitio_inestable(_docs(130)))
    pres = [5]
    try:
        _enumerar_tajada(requests.Session(), _CLAS_RES, 2025, pres, None, None)
        assert False, "debía agotar el presupuesto"
    except _PresupuestoAgotado:
        pass
    assert len(responses.calls) == 5


@responses.activate
def test_enumerar_tajada_ultima_pagina_caida_no_da_un_total_falso():
    # 30 fichas = 2 páginas; la última (page=1) falla siempre. Sin total
    # verificable no se puede dar por completa la tajada con las 20 de la
    # página 0: se sigue con la búsqueda por fragmentos.
    todos = _docs(30)
    sitio = _sitio_inestable(todos, modo="estable")

    def cb(request):
        if "page=1" in request.url:
            return (500, {}, "error")
        return sitio(request)

    responses.add_callback(responses.GET, _LISTADO, callback=cb)
    progreso = []
    got = _enumerar_tajada(requests.Session(), _CLAS_RES, 2025, [4000], None, progreso.append)
    assert any("Error" in m for m in progreso)
    assert len([c for c in responses.calls if "page=1" in c.request.url]) == 2  # un reintento
    assert got == dict(todos)
    assert not any("faltan" in m for m in progreso)


def test_anios_rango_y_piso():
    hoy = date(2026, 10, 7)
    assert _anios("2026-10-01", "2026-10-07", hoy) == [2026]
    assert _anios("2025-12-01", "2025-12-31", hoy) == [2025, 2026]  # se publica en enero siguiente
    assert _anios("2010-01-01", "2016-06-30", hoy) == [2015, 2016, 2017]
    assert _anios("2000-01-01", "2010-12-31", hoy) == []


def _registrar_sitio(listados, fichas):
    """listados: {clasif: [(href, titulo)]} (una página, cualquier año);
    fichas: {href: html | código de error}."""
    def cb_listado(request):
        qs = parse_qs(urlparse(request.url).query)
        filas = listados.get(qs["field_clasificacion2_target_id"][0], [])
        return (200, _HTML, _listado(filas, encabezado=""))

    responses.add_callback(responses.GET, _LISTADO, callback=cb_listado)
    for href, html in fichas.items():
        if isinstance(html, int):
            responses.add(responses.GET, f"{_BASE}{href}", status=html)
        else:
            responses.add(responses.GET, f"{_BASE}{href}", body=html, headers=_HTML)


def _ficha_con(exp, pub, *pdfs):
    return _html_ficha(*pdfs).replace("2026-09-29", exp).replace("2026-09-30", pub)


@responses.activate
def test_scrap_resolucion_basica():
    _registrar_sitio(
        {_CLAS_RES: [("/r1", 'Resolución No. 77121 del 29 de septiembre de 2026 "Por la cual"')]},
        {"/r1": _ficha_con("2026-09-29", "2026-09-30", "/sites/default/files/normativa/R77121.pdf")},
    )
    docs = ScrapSIC().scrap("2026-09-01", "2026-09-30")
    assert len(docs) == 1
    d = docs[0]
    assert d.title == "R_SIC_77121_2026"
    assert d.tipo == "Resolución"
    assert d.f_public == "2026-09-30"
    assert d.f_providencia == "2026-09-29"
    assert d.link == {"url": f"{_BASE}/sites/default/files/normativa/R77121.pdf", "method": "GET"}
    assert d.save_path == "Superintendencia de Industria y Comercio/2026-09-30/Resolución/R_SIC_77121_2026(extension)"
    assert d.title_unverified is False
    assert d.detalle.startswith("Resolución No. 77121")


@responses.activate
def test_scrap_filtra_por_publicacion_piso_y_pdf():
    _registrar_sitio(
        {_CLAS_RES: [
            ("/fuera", "Resolución 1 de 2026"),        # publicada fuera de rango
            ("/vieja", "Resolución 2 de 2014"),        # expedida antes de 2015
            ("/sinpdf", "Resolución 3 de 2026"),       # sólo enlace externo
            ("/ok", "Resolución 4 de 2026"),
        ]},
        {
            "/fuera": _ficha_con("2026-08-01", "2026-08-02", "/f/1.pdf"),
            "/vieja": _ficha_con("2014-12-30", "2026-09-10", "/f/2.pdf"),
            "/sinpdf": _ficha_con("2026-09-10", "2026-09-10"),
            "/ok": _ficha_con("2026-09-10", "2026-09-10", "/f/4.pdf"),
        },
    )
    progreso = []
    docs = ScrapSIC().scrap("2026-09-01", "2026-09-30", on_progress=progreso.append)
    assert [d.title for d in docs] == ["R_SIC_0004_2026"]
    assert any("sin PDF" in m for m in progreso)


@responses.activate
def test_scrap_descartados_no_abren_ficha():
    _registrar_sitio(
        {_CLAS_RES: [("/p", "Proyecto de Resolución “X”")],
         _CLAS_DOC: [("/s", "Sentencia Expediente 2007 00102 Consejo de Estado")]},
        {},
    )
    progreso = []
    docs = ScrapSIC().scrap("2026-09-01", "2026-09-30", on_progress=progreso.append)
    assert docs == []
    assert not any(c.request.url in (f"{_BASE}/p", f"{_BASE}/s") for c in responses.calls)
    assert any("1 fichas descartadas" in m for m in progreso)


@responses.activate
def test_scrap_anexos_y_colision():
    _registrar_sitio(
        {_CLAS_CIR: [
            ("/ce", "Circular Externa 010 de 2026"),
            ("/cj", "Circular Conjunta 010 de 2026"),
        ]},
        {
            "/ce": _ficha_con("2026-02-16", "2026-02-16", "/f/ce.pdf", "/f/ce-anexo.pdf"),
            "/cj": _ficha_con("2026-02-08", "2026-02-08", "/f/cj.pdf"),
        },
    )
    docs = ScrapSIC().scrap("2026-01-01", "2026-12-31")
    por_url = {d.link["url"].rsplit("/", 1)[-1]: d for d in docs}
    assert por_url["ce.pdf"].title == "C_SIC_0010_2026"
    assert por_url["ce-anexo.pdf"].title == "C_SIC_0010_2026_A01"
    # misma clave que la externa -> baja al título del sitio, sin verificar
    assert por_url["cj.pdf"].title == "Circular Conjunta 010 de 2026"
    assert por_url["cj.pdf"].title_unverified is True
    assert all(d.tipo == "Circular" for d in docs)


@responses.activate
def test_scrap_misma_resolucion_en_resoluciones_y_doctrina_se_ingiere_una_vez():
    ficha = _ficha_con("2016-02-04", "2016-02-04", "/f/res3839.pdf")
    _registrar_sitio(
        {_CLAS_RES: [("/r", "Resolución No. 3839 del 4 de febrero de 2016")],
         _CLAS_DOC: [("/d", "Resolución No. 3839 del 4 de febrero de 2016")]},
        {"/r": ficha, "/d": ficha},
    )
    docs = ScrapSIC().scrap("2016-01-01", "2016-12-31")
    assert [d.title for d in docs] == ["R_SIC_3839_2016"]


@responses.activate
def test_scrap_ficha_caida_no_aborta():
    _registrar_sitio(
        {_CLAS_RES: [("/mala", "Resolución 1 de 2026"), ("/buena", "Resolución 2 de 2026")]},
        {"/mala": 500, "/buena": _ficha_con("2026-09-10", "2026-09-10", "/f/2.pdf")},
    )
    progreso = []
    docs = ScrapSIC().scrap("2026-09-01", "2026-09-30", on_progress=progreso.append)
    assert [d.title for d in docs] == ["R_SIC_0002_2026"]
    assert any("Error" in m and "Resolución 1" in m for m in progreso)


@responses.activate
def test_scrap_clasificaciones_vacias_solo_avisan_si_todas_lo_estan():
    _registrar_sitio(
        {_CLAS_RES: [("/r", "Resolución 2 de 2026")]},
        {"/r": _ficha_con("2026-09-10", "2026-09-10", "/f/2.pdf")},
    )
    progreso = []
    ScrapSIC().scrap("2026-09-01", "2026-09-30", on_progress=progreso.append)
    assert not any("cambió" in m for m in progreso)

    responses.reset()
    _registrar_sitio({}, {})
    progreso = []
    ScrapSIC().scrap("2026-09-01", "2026-09-30", on_progress=progreso.append)
    # "Error" para que el worker lo muestre en el informe de la corrida
    assert any("cambió" in m and "Error" in m for m in progreso)


@responses.activate
def test_scrap_respeta_limit_y_stop_event():
    filas = [(f"/r{i}", f"Resolución {i} de 2026") for i in range(1, 6)]
    _registrar_sitio(
        {_CLAS_RES: filas},
        {h: _ficha_con("2026-09-10", "2026-09-10", f"/f/{h[1:]}.pdf") for h, _ in filas},
    )
    assert len(ScrapSIC().scrap("2026-09-01", "2026-09-30", limit=2)) == 2

    ev = threading.Event()
    ev.set()
    assert ScrapSIC().scrap("2026-09-01", "2026-09-30", stop_event=ev) == []


def test_titulo_solo_lee_el_numero_si_el_titulo_empieza_por_el_acto():
    # una aclaración o una resolución que modifica otra NO es esa otra resolución
    assert _titulo(_TIPO_RES, "Aclaración de la Resolución 56937 de 2025", "2025-09-18") == ("Aclaración de la Resolución 56937 de 2025", True)
    assert _titulo(_TIPO_RES, "Fe de erratas de la Resolución No. 1234 de 2025", "2025-03-01")[1] is True
    assert _titulo(_TIPO_CIR, "Lineamientos sobre la Circular 10 de 2020", "2025-03-01")[1] is True
    # el número es el del propio acto, no el de la resolución que modifica
    assert _titulo(_TIPO_RES, "Resolución 4500 de 2025 por la cual se modifica la Resolución 1234 de 2020", "2025-03-01") == ("R_SIC_4500_2025", False)
    assert _titulo(_TIPO_RES, "Resolución por la cual se modifica la Resolución 1234 de 2020", "2025-03-01")[1] is True
    # títulos reales 2025 que sí son la resolución, con un prefijo descriptivo
    assert _titulo(_TIPO_RES, "Nombramiento - Resolución 100348 de 2025", "2025-12-01") == ("R_SIC_100348_2025", False)
    # títulos reales 2025 que NO son la resolución citada
    assert _titulo(_TIPO_RES, "La SIC aclaró la Resolución No. 88766 de 30 de octubre de 2025", "2025-11-05")[1] is True


def test_corrida_diaria_mira_30_dias_atras():
    # la "Fecha publicación" la digita el personal de la SIC: un documento
    # subido días después de esa fecha no debe quedar fuera de la ventana diaria
    assert ScrapSIC.scheduled_min_lookback_days == 30
