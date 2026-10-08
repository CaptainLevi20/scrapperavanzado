import re

import responses

from core.scrapers.registry import FAMILY_REGISTRY
from core.scrapers.families.supertransporte import (
    ScrapSupertransporte,
    Concepto,
    Entrada,
    _BIBLIOTECA,
    _CIRCULAR_UNICA,
    _NORMATIVA,
    _RESOLUCIONES,
    _SICOV,
    _conceptos_del_bundle,
    _entradas_normativa,
    _entradas_sicov,
    _expedicion_entrada,
    _fecha_carpeta,
    _fecha_texto,
    _numero,
    _paginas_por_anio,
    _publicacion,
    _resoluciones_de_pagina,
    _titulo_concepto,
    _titulo_entrada,
    _titulo_tcu,
    _titulos_circular_unica,
)

_DOC = "https://www.supertransporte.gov.co/documentos"
_HTML = {"Content-Type": "text/html; charset=UTF-8"}


def test_supertransporte_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["supertransporte"].__name__ == "ScrapSupertransporte"


# ---------------------------------------------------------------- fechas

def test_fecha_texto_formas_del_sitio():
    assert _fecha_texto("Fecha de resolución: 03 de Agosto 2026") == "2026-08-03"
    assert _fecha_texto("Fecha de publicación: 31 de Marzo de 2000") == "2000-03-31"
    assert _fecha_texto("Fecha de resolución: 08 de Noviembrede 2012") == "2012-11-08"
    assert _fecha_texto("Circular Externa No. 054 del 01 de septiembre de 2023") == "2023-09-01"


def test_fecha_texto_sin_anio_usa_el_de_la_pagina():
    assert _fecha_texto("Bogotá, 22 de Diciembre", 2011) == "2011-12-22"
    assert _fecha_texto("Bogotá, 22 de Diciembre") is None


def test_fecha_carpeta():
    assert _fecha_carpeta(f"{_DOC}/2026/Septiembre/Notificaciones_02/9788.pdf") == "2026-09-02"
    assert _fecha_carpeta(f"{_DOC}/2018/Junio/Notificaciones_28_C/CIRCULAR_27_2018.pdf") == "2018-06-28"
    assert _fecha_carpeta(f"{_DOC}/2025/noviembre/Juridica_20/x.pdf") == "2025-11-20"
    # carpetas viejas sin día
    assert _fecha_carpeta(f"{_DOC}/2011/notificaciones/resoluciones_generales/7706.pdf") is None
    assert _fecha_carpeta(f"{_DOC}/2016/Marzo/RES_7725_2016.pdf") is None


def test_publicacion_es_la_carpeta_salvo_que_sea_anterior_a_la_expedicion():
    assert _publicacion(f"{_DOC}/2026/Septiembre/Notificaciones_02/9788.pdf", "2026-08-03") == "2026-09-02"
    assert _publicacion(f"{_DOC}/2026/Enero/X_02/9788.pdf", "2026-08-03") == "2026-08-03"
    assert _publicacion(f"{_DOC}/2011/notificaciones/r/1.pdf", "2011-12-22") == "2011-12-22"


def test_numero_relleno_y_radicados_tal_cual():
    assert _numero("54") == "0054"
    assert _numero("054") == "0054"
    assert _numero("9788") == "9788"
    assert _numero("14744") == "14744"
    assert _numero("20265330000164") == "20265330000164"


# ---------------------------------------------------------- resoluciones

def _seccion(cabeza, fecha, epigrafe, href, extra=""):
    return f"""
<section class="resolution"><div class="d-flex mb-4">
  <div class="mt-4 icono-resolution"><a href="{href}"><img src="icono-pdf.png"/></a></div>
  <div class="ml-3 linea-botton">
    <a class="boton-enlace-activo" href="{href}">{cabeza}</a>
    <p class="body-2">{fecha}</p>
    <p class="body-1">{epigrafe}</p>
    {extra}
  </div></div></section>"""


def test_resolucion_basica_con_anexo():
    html = _seccion(
        "Supertransporte expide la Resolución 9596 de 2026",
        "Fecha de resolución: 29 de Julio 2026",
        "“Por la cual se adiciona el Parágrafo 9”",
        f"{_DOC}/2026/Agosto/Planeacion_20/1_Resolucion_9596.pdf",
        f'<a class="boton-enlace-activo" href="{_DOC}/2026/Agosto/Planeacion_20/ANEXO.pdf">- <em>ANEXO TÉCNICO</em></a>',
    )
    rs = _resoluciones_de_pagina(html, 2026)
    assert [(r.title, r.unverified, r.expedicion) for r in rs] == [
        ("R_SPT_9596_2026", False, "2026-07-29"),
        ("R_SPT_9596_2026_A01", False, "2026-07-29"),
    ]
    assert rs[0].detalle == "“Por la cual se adiciona el Parágrafo 9”"
    assert rs[1].detalle == "ANEXO TÉCNICO"


def test_resolucion_2011_fecha_en_el_primer_parrafo_aunque_el_epigrafe_diga_fecha():
    html = _seccion(
        "Supertransporte expide la Resolución 4630 de 2011",
        "Bogotá, 20 de Septiembre",
        "RESOLUCIÓN No. 4630 de 2011: FIJA FECHA LIMITE PAGO TASA DE VIGILANCIA.",
        f"{_DOC}/2011/notificaciones/resoluciones_generales/4630.pdf",
    )
    (r,) = _resoluciones_de_pagina(html, 2011)
    assert (r.title, r.expedicion) == ("R_SPT_4630_2011", "2011-09-20")


def test_resolucion_variantes_de_cabeza():
    for cabeza, titulo in [
        ("Supertransporte expide la Resolución No. 44931 de 2018", "R_SPT_44931_2018"),
        ("Supertransporte expide la Resolución No. 10579  de 2019", "R_SPT_10579_2019"),
        ("Supertransporte expide la ResolucionesResolución 78669 de 2016", "R_SPT_78669_2016"),
        ("Supertransporte expide la Resolución 159 de 2000", "R_SPT_0159_2000"),
    ]:
        (r,) = _resoluciones_de_pagina(_seccion(cabeza, "Fecha de resolución: 01 de Marzo de 2016", "x", f"{_DOC}/a.pdf"), 2016)
        assert r.title == titulo


def test_resolucion_sin_numero_queda_sin_verificar():
    (r,) = _resoluciones_de_pagina(
        _seccion("Supertransporte expide la FE DE ERRATAS", "Fecha de publicación: 20 de Mayo de 2021", "x", f"{_DOC}/f.pdf"), 2021
    )
    assert r.unverified is True
    assert r.title == "FE DE ERRATAS"


def test_bloque_con_varias_resoluciones_numeradas():
    lis = "".join(
        f'<li><a class="boton-enlace-activo" href="{_DOC}/2015/RESOL.%20{n}.pdf">{n}</a></li>' for n in (19009, 19010)
    )
    html = f"""<section class="resolution"><div class="ml-3 linea-botton">
      <a class="boton-enlace-activo">Supertransporte expide las Resoluciones 19009 y 19010 de 2015</a>
      <p class="body-2">Fecha de resolución: 18 de Septiembre de 2015</p>
      <p class="body-1">Por medio de la cual… <ul>{lis}</ul></p></div></section>"""
    assert [r.title for r in _resoluciones_de_pagina(html, 2015)] == ["R_SPT_19009_2015", "R_SPT_19010_2015"]


def test_enlaces_secundarios_que_son_otras_resoluciones_o_paginas_web():
    extra = (
        f'<a class="boton-enlace-activo" href="{_DOC}/2016/Enero/N_29_RG/20165500047785.pdf">Supertransporte expide la Resolución 4778 de 2016</a>'
        '<a class="boton-enlace-activo" href="https://www.supertransporte.gov.co/index.php/circulares/modulo-sigt/">https://www.supertransporte.gov.co/index.php/circulares/modulo-sigt/</a>'
        f'<a class="boton-enlace-activo" href="{_DOC}/2019/video.mp4">Video Tutorial</a>'
    )
    html = _seccion("Supertransporte expide la Resolución 5555 de 2016", "Fecha de resolución: 08 de Febrero de 2016", "x", f"{_DOC}/5555.pdf", extra)
    assert [r.title for r in _resoluciones_de_pagina(html, 2016)] == ["R_SPT_5555_2016", "R_SPT_4778_2016"]


def test_paginas_por_anio_respeta_slugs_raros():
    html = (
        '<a href="https://www.supertransporte.gov.co/index.php/resoluciones-generales/2020-2/">2020</a>'
        '<a href="https://www.supertransporte.gov.co/index.php/resoluciones-generales/2021/">2021</a>'
        '<a href="https://www.supertransporte.gov.co/index.php/resoluciones-generales/2026/feed/">feed</a>'
    )
    assert _paginas_por_anio(html) == {
        2020: f"{_RESOLUCIONES}2020-2/",
        2021: f"{_RESOLUCIONES}2021/",
    }


# ------------------------------------------------------------ circulares

def _e(texto, seccion="Circulares externas", url=f"{_DOC}/2026/Octubre/Planeacion_07/c.pdf"):
    return Entrada(url, texto, seccion)


def test_titulo_circulares_todas_con_c():
    casos = [
        ("Circular Externa No. 20265330000164 del 07 de octubre de 2026", "C_SPT_20265330000164_2026"),
        ("Circular Externa No. 054 del 01 de septiembre de 2023", "C_SPT_0054_2023"),
        ("Circular No. 018 del 22 de septiembre de 2021 – Implementación de la Resolución 1519 de 2020", "C_SPT_0018_2021"),
        ("Circular Conjunta Externa No. 64 del 02 de septiembre de 2016", "C_SPT_0064_2016"),
        ("Circular Conjunta MT 20234000000597 del 27 de septiembre de 2023 – Servicio", "C_SPT_20234000000597_2023"),
        ("Circular Conjunta 20244000000107 del 24 de enero de 2024 – Alcance", "C_SPT_20244000000107_2024"),
        ("1. Circular Externa 20265330000024 de 2026) – SICOV – Operadores", "C_SPT_20265330000024_2026"),
        ("4. CIRCULAR 26 de 2018 – «presentación homologados»", "C_SPT_0026_2018"),
        ("5. Circular 22 de 2018–Modificación Plazo Circular 15 de 2018", "C_SPT_0022_2018"),
    ]
    for texto, titulo in casos:
        e = _e(texto)
        assert _titulo_entrada(e, _expedicion_entrada(e)) == ("Circular", titulo, False), texto


def test_alcance_y_fe_de_erratas_no_toman_el_numero_de_otra_circular():
    for texto in (
        "Alcance a la Circular Externa No. 20231010000327 del 10 de julio de 2023",
        "Fe de Erratas – Circular Conjunta Externa No. 2023101075272 del 10 de julio de 2023",
    ):
        tipo, titulo, unv = _titulo_entrada(_e(texto, url=f"{_DOC}/2023/Julio/D_12/circular.pdf"), "2023-07-10")
        assert (titulo, unv) == (texto, True)


def test_circular_sin_numero_es_sn():
    e = _e(
        "Reiteración cumplimiento régimen normativo en el control a toda forma de ilegalidad",
        url=f"{_DOC}/2023/Marzo/Juridica_30/Circular-Reiteracion-Control.pdf",
    )
    exp = _expedicion_entrada(e)
    assert exp == "2023-03-30"
    assert _titulo_entrada(e, exp) == ("Circular", "C_SPT_SN_2023", False)


def test_resolucion_interna():
    e = _e("Resolución 8209 del 14 de agosto de 2024", seccion="Resoluciones internas")
    assert _expedicion_entrada(e) == "2024-08-14"
    assert _titulo_entrada(e, "2024-08-14") == ("Resolución", "R_SPT_8209_2024", False)


def test_expedicion_sicov_no_toma_fechas_de_la_descripcion():
    e = _e(
        "6. Circular 03 de 2018 – Acciones para … registrados antes del 18 de diciembre de 2017",
        seccion="Circulares SICOV",
        url=f"{_DOC}/2018/Enero/Notificaciones_17_C/CIRCULAR_03_2018.pdf",
    )
    assert _expedicion_entrada(e) == "2018-01-17"
    e = _e(
        "15. Circular 26 de 2017– Cumplimiento de La Resolucion 993 de 25 de Abril de 2017",
        seccion="Circulares SICOV",
        url=f"{_DOC}/2017/Mayo/Notificaciones_09_C/CIRCULAR_26_2017.pdf",
    )
    assert _expedicion_entrada(e) == "2017-05-09"


def test_expedicion_sicov_carpeta_de_otro_anio_queda_en_enero():
    e = _e("24. Circular 18 de 2015 – Mejoras", seccion="Circulares SICOV", url=f"{_DOC}/2015/notificaciones/circulares/018_2015.pdf")
    assert _expedicion_entrada(e) == "2015-01-01"


def test_entradas_normativa_y_sicov():
    html = f"""
    <section id="leyes"><a href="https://www.funcionpublica.gov.co/x">Ver norma</a></section>
    <section id="circ-externas"><a href="{_DOC}/2026/a.pdf">Circular Externa No. 1 del 2 de enero de 2026</a></section>
    <section id="circ-conjuntas"><a href="/documentos/2024/b.pdf">Circular Conjunta No. 16 del 15 de marzo de 2024</a></section>
    <section id="res-internas"><a href="{_DOC}/2024/c.pdf">Resolución 8209 del 14 de agosto de 2024</a></section>"""
    assert [(e.seccion, e.url) for e in _entradas_normativa(html)] == [
        ("Resoluciones internas", f"{_DOC}/2024/c.pdf"),
        ("Circulares externas", f"{_DOC}/2026/a.pdf"),
        ("Circulares conjuntas", f"{_DOC}/2024/b.pdf"),
    ]
    sicov = f"""<a href="{_DOC}/2025/febrero/Atencion_25/CARTA.pdf">Carta de trato digno</a>
    <a href="{_DOC}/2018/x.pdf">2. Circular 43 de 2018) – SICOV</a>"""
    assert [e.texto for e in _entradas_sicov(sicov)] == ["2. Circular 43 de 2018) – SICOV"]


# --------------------------------------------------------- circular única

def test_circular_unica():
    html = f"""
    <a href="{_DOC}/2026/Agosto/Juridica_18/TITULO_I.pdf">TÍTULO I. MODO ACUÁTICO</a>
    <a href="/documentos/2026/Agosto/Juridica_18/TITULO_IV.pdf">TÍTULO IV. SUPERVISIÓN SUBJETIVA</a>
    <a href="/documentos/2026/Agosto/Juridica_18/CUADRO.pdf">CUADRO CONTROL MODIFICACIONES</a>
    <a href="#_ftn1">[1]</a>"""
    filas = _titulos_circular_unica(html)
    assert [t for _, t in filas] == ["TÍTULO I. MODO ACUÁTICO", "TÍTULO IV. SUPERVISIÓN SUBJETIVA", "CUADRO CONTROL MODIFICACIONES"]
    assert [_titulo_tcu(t, "2026-08-18") for _, t in filas] == [
        "TCU_SPT_I_20260818", "TCU_SPT_IV_20260818", "TCU_SPT_CUADRO-CONTROL_20260818",
    ]


# --------------------------------------------------------------- conceptos

_BUNDLE = """
class ProcessService {
  constructor() {
    this.documents = [//RESOLUCIONES
    {
      "titulo": "Resolución 7655 de 2020",
      "categoria": "Resoluciones Generales",
      "documento": "http://www.suin-juriscol.gov.co/viewDocument.asp?id=1"
    }, //LUISA
    {
      "titulo": "TRANSPORTE ESPECIAL",
      "contenido": "Contrato de vinculación",
      "categoria": "Conceptos",
      "anio": "2020",
      "fecha": "01-01-2020",
      "documento": "20203000407701.tif "
    }, {
      "titulo": "TRANSPORTE ESPECIAL",
      "contenido": "Repetido",
      "categoria": "Conceptos",
      "anio": "2020",
      "documento": "20203000407701.tif"
    }, {
      "titulo": "COVID-19",
      "contenido": "Protocolos",
      "categoria": "Conceptos",
      "anio": "2021",
      "documento": "Concepto covid.pdf"
    }];
  }
}"""


def test_conceptos_del_bundle():
    assert _conceptos_del_bundle(_BUNDLE) == [
        Concepto("20203000407701.tif", "TRANSPORTE ESPECIAL", "Contrato de vinculación", "2020"),
        Concepto("Concepto covid.pdf", "COVID-19", "Protocolos", "2021"),
    ]
    assert _conceptos_del_bundle("sin listado") == []


def test_titulo_concepto():
    assert _titulo_concepto(Concepto("20203000407701.tif", "T", "C", "2020")) == ("CTO_SPT_20203000407701", False)
    assert _titulo_concepto(Concepto("Concepto covid.pdf", "COVID-19", "Protocolos", "2021")) == ("COVID-19 Protocolos", True)


# ------------------------------------------------------------- scrap

def _registrar_sitio(resoluciones_2026="", normativa="", sicov="", circular_unica="", bundle=_BUNDLE):
    responses.add(responses.GET, re.compile(re.escape(_RESOLUCIONES) + r"2026/"), body=resoluciones_2026, headers=_HTML)
    responses.add(responses.GET, re.compile(re.escape(_RESOLUCIONES) + r"20(?!26)\d\d/"), body="", headers=_HTML)
    responses.add(responses.GET, _NORMATIVA, body=normativa, headers=_HTML)
    responses.add(responses.GET, _SICOV, body=sicov, headers=_HTML)
    responses.add(responses.GET, _CIRCULAR_UNICA, body=circular_unica, headers=_HTML)
    responses.add(responses.GET, f"{_BIBLIOTECA}/", body='<script defer src="/static/js/bundle.js"></script>', headers=_HTML)
    responses.add(responses.GET, f"{_BIBLIOTECA}/static/js/bundle.js", body=bundle, headers={"Content-Type": "application/javascript"})


@responses.activate
def test_scrap_resolucion_fecha_de_publicacion_es_la_carpeta():
    _registrar_sitio(resoluciones_2026=_seccion(
        "Supertransporte expide la Resolución 9788 de 2026",
        "Fecha de resolución: 03 de Agosto 2026",
        "“Por la cual se adiciona un artículo”",
        f"{_DOC}/2026/Septiembre/Notificaciones_02/9788.pdf",
    ))
    docs = ScrapSupertransporte().scrap("2026-09-01", "2026-09-30")
    assert len(docs) == 1
    d = docs[0]
    assert d.title == "R_SPT_9788_2026"
    assert d.tipo == "Resolución"
    assert d.f_providencia == "2026-08-03"
    assert d.f_public == "2026-09-02"
    assert d.link == {"url": f"{_DOC}/2026/Septiembre/Notificaciones_02/9788.pdf", "method": "GET"}
    assert d.save_path == "Superintendencia de Transporte/2026-09-02/Resolución/R_SPT_9788_2026(extension)"
    assert d.title_unverified is False
    # expedida en agosto pero subida en septiembre: una corrida de agosto no la ve
    assert ScrapSupertransporte().scrap("2026-08-01", "2026-08-31") == []


@responses.activate
def test_scrap_titulos_repetidos_llevan_sufijo_y_el_mismo_archivo_cuenta_una_vez():
    html = (
        _seccion("Supertransporte expide la Resolución 14744 de 2026", "Fecha de resolución: 19 de Septiembre 2026", "x",
                 f"{_DOC}/2026/Septiembre/Recaudo_22/14744.pdf")
        + _seccion("Supertransporte expide la Resolución 14744 de 2026", "Fecha de resolución: 19 de Septiembre 2026", "x",
                   f"{_DOC}/2026/Octubre/Notificaciones_01/14744.pdf")
        + _seccion("Supertransporte expide la Resolución 14744 de 2026", "Fecha de resolución: 19 de Septiembre 2026", "x",
                   f"{_DOC}/2026/Septiembre/Recaudo_22/14744.pdf")
    )
    _registrar_sitio(resoluciones_2026=html)
    docs = ScrapSupertransporte().scrap("2026-09-01", "2026-10-31")
    assert sorted((d.title, d.f_public) for d in docs) == [
        ("R_SPT_14744_2026", "2026-09-22"),
        ("R_SPT_14744_2026_2", "2026-10-01"),
    ]
    # el sufijo no depende del rango pedido
    (solo,) = ScrapSupertransporte().scrap("2026-10-01", "2026-10-31")
    assert solo.title == "R_SPT_14744_2026_2"


@responses.activate
def test_scrap_circulares_anexo_y_circular_unica():
    normativa = f"""<section id="circ-externas">
      <a href="{_DOC}/2025/noviembre/Juridica_20/120255330000164_00001_SICOV.pdf">Circular Externa No. 20255330000164 del 18 de noviembre de 2025</a>
      <a href="{_DOC}/2025/diciembre/OTIC_02/1/ANEXO_TECNICO.pdf">Anexo técnico SICOV-OTPC versión 3 / Circular Externa No. 2025533000164 del 18 de noviembre de 2025</a>
    </section>"""
    cu = f'<a href="/documentos/2025/Noviembre/Juridica_18/TITULO_III.pdf">TÍTULO III. MODO TERRESTRE</a>'
    _registrar_sitio(normativa=normativa, circular_unica=cu)
    docs = ScrapSupertransporte().scrap("2025-11-01", "2025-12-31")
    assert [(d.title, d.tipo, d.f_providencia, d.f_public) for d in docs] == [
        ("C_SPT_20255330000164_2025", "Circular", "2025-11-18", "2025-11-20"),
        # el anexo se subió en diciembre: su publicación es la de su carpeta
        ("C_SPT_20255330000164_2025_A01", "Circular", "2025-11-18", "2025-12-02"),
        ("TCU_SPT_III_20251118", "Título Circular Única", "2025-11-18", "2025-11-18"),
    ]


@responses.activate
def test_scrap_conceptos_se_filtran_por_anio_no_por_fecha_exacta():
    _registrar_sitio()
    # ventana corta a mitad de año (como la corrida diaria): las fechas de los
    # conceptos son de relleno (1 de enero) y aun así deben aparecer
    docs = ScrapSupertransporte().scrap("2020-08-10", "2020-08-13")
    assert [(d.title, d.tipo, d.f_public) for d in docs] == [("CTO_SPT_20203000407701", "Concepto", "2020-01-01")]
    d = docs[0]
    assert d.link["url"] == f"{_BIBLIOTECA}/files/20203000407701.tif"
    assert d.detalle == "TRANSPORTE ESPECIAL — Contrato de vinculación"
    assert ScrapSupertransporte().scrap("2026-08-10", "2026-08-13") == []


@responses.activate
def test_scrap_avisa_cuando_el_sitio_no_trae_nada():
    _registrar_sitio(bundle="sin listado")
    avisos = []
    ScrapSupertransporte().scrap("2026-01-01", "2026-01-31", on_progress=avisos.append)
    errores = [a for a in avisos if "Error" in a]
    assert any("resoluciones" in a for a in errores)
    assert any("circular" in a for a in errores)
    assert any("Circular Única" in a for a in errores)
    assert any("Biblioteca" in a for a in errores)


@responses.activate
def test_scrap_respeta_el_limite():
    html = "".join(
        _seccion(f"Supertransporte expide la Resolución {n} de 2026", "Fecha de resolución: 01 de Julio 2026", "x",
                 f"{_DOC}/2026/Julio/N_02/{n}.pdf")
        for n in (1, 2, 3)
    )
    _registrar_sitio(resoluciones_2026=html)
    assert len(ScrapSupertransporte().scrap("2026-07-01", "2026-07-31", limit=2)) == 2
