import datetime

import requests
import responses
from bs4 import BeautifulSoup

from core.scrapers.families.supervigilancia import (
    _SOURCE,
    _ANIO_MINIMO,
    _norm_texto,
    _safe_title,
    _id_de_href,
    _num_en_texto,
    _num_al_inicio,
    _num_en_prosa,
    _fecha_de_meta,
    _titulo,
    _head_info,
    _fila_a_doc,
    _items_de_listado,
    _BASE,
    ScrapSupervigilancia,
)
from core.scrapers.registry import FAMILY_REGISTRY, resolve_scraper


def test_source_string_matches_seed_name():
    assert _SOURCE == "Superintendencia de Vigilancia y Seguridad Privada"
    assert _ANIO_MINIMO == 2015


def test_norm_texto_strips_zero_width_and_collapses_space():
    assert _norm_texto("Res​olución   No.  1\n\t2") == "Resolución No. 1 2"


def test_safe_title_replaces_forbidden_chars_and_truncates():
    assert _safe_title('a/b:c"d') == "a-b-c-d"
    assert len(_safe_title("x" * 200)) == 120


def test_id_de_href():
    assert _id_de_href("/web/content/10260?download=true") == "10260"
    assert _id_de_href("https://www.supervigilancia.gov.co/web/content/7096?download=true") == "7096"
    assert _id_de_href("/circular-externa-no-1") is None


def test_num_en_texto_any_position_uppercased():
    assert _num_en_texto('filename="20261000015947CS RESOLUCION.pdf"') == "20261000015947CS"
    assert _num_en_texto("RESOLUCION No. 202540000099737cs - TRAMITES.pdf") == "202540000099737CS"
    assert _num_en_texto("Renting operativo.pdf") is None


def test_num_al_inicio_only_when_leading():
    assert _num_al_inicio("20263200005647CS Por la cual...") == "20263200005647CS"
    assert _num_al_inicio("Por la cual se deroga la 20221300053467CS") is None


def test_num_en_prosa():
    assert _num_en_prosa("POR MEDIO DE LA CUAL SE EFECTÚA UNA CORRECCIÓN A LA RESOLUCIÓN No. 2023320000649") == "2023320000649"
    assert _num_en_prosa("Resolucion 20253200007657 lineamientos para Reporte") == "20253200007657"
    assert _num_en_prosa("Ley Lorenzo") is None


def test_num_en_prosa_circular():
    # las circulares traen el número sin "CS" y a veces de 3 dígitos
    assert _num_en_prosa("Circular externa 20251300000015 corrección circular tarifas", "C") == "20251300000015"
    assert _num_en_prosa("Circular 465 de 2017.pdf", "C") == "465"
    assert _num_en_prosa("Circular Externa No. 20241300000445 Tarifas", "C") == "20241300000445"
    # cada tipo busca sólo su propia palabra: una resolución que menciona una
    # circular no toma el número de la circular, y viceversa
    assert _num_en_prosa("Resolución que modifica la Circular 465 de 2017") is None
    assert _num_en_prosa("Circular sobre la Resolución 20253200007657", "C") is None


def test_fecha_de_meta_variants():
    assert _fecha_de_meta("Publicación: 08/05/2026") == datetime.date(2026, 5, 8)
    assert _fecha_de_meta("|Expedición: 23/01/2008") == datetime.date(2008, 1, 23)
    assert _fecha_de_meta("Publicación: Hoy") is None
    assert _fecha_de_meta("Expedición: --") is None
    assert _fecha_de_meta("") is None
    assert _fecha_de_meta("Expedición: 32/13/2020") is None


def test_fecha_de_meta_en_palabras():
    """Regresión: las filas de 2018-2022 escriben la fecha en palabras y se
    descartaban todas como "sin fecha" (26 resoluciones en el sitio real)."""
    assert _fecha_de_meta(
        "Publicación: 27 de julio de 2020 | Expedición: 27 de julio de 2020"
    ) == datetime.date(2020, 7, 27)
    # errata real del sitio: "de /2020"
    assert _fecha_de_meta("Publicación: 01 de junio de /2020 | Expedición: 01 de junio de 2020") == datetime.date(2020, 6, 1)
    # "Hace 5 días" no es una fecha: se usa la de expedición
    assert _fecha_de_meta("Publicación: Hace 5 días | Expedición: 10 de enero de 2021") == datetime.date(2021, 1, 10)


def test_titulo_con_numero():
    assert _titulo("R", "20263200005647CS", 2026, "cualquier cosa", None) == ("R_SVySP_20263200005647CS_2026", False)


def test_titulo_sin_numero_usa_texto_crudo_sin_pdf():
    title, unverified = _titulo("CTO", None, 2018, "Renting operativo.pdf", None)
    assert title == "Renting operativo"
    assert unverified is True


def test_titulo_sin_numero_cae_a_filename_stem_cuando_texto_vacio():
    assert _titulo("R", None, 2025, "   ", "20263100016027CS")[0] == "20263100016027CS"


def test_titulo_sin_numero_fallback_documento():
    assert _titulo("R", None, 2025, "", None)[0] == "documento"


_URL = "https://www.supervigilancia.gov.co/web/content/10102?download=true"


@responses.activate
def test_head_info_parsea_filename_y_length():
    responses.add(
        responses.HEAD, _URL,
        headers={
            "Content-Disposition": 'attachment; filename="20261000015947CS RESOLUCION.pdf"',
            "Content-Length": "403369",
        },
    )
    got = _head_info(requests.Session(), _URL)
    assert got == {"filename": "20261000015947CS RESOLUCION.pdf", "content_length": 403369, "etag": None}


@responses.activate
def test_head_info_filename_sin_comillas():
    responses.add(
        responses.HEAD, _URL,
        headers={"Content-Disposition": "attachment; filename=20263100016027CS.pdf"},
    )
    assert _head_info(requests.Session(), _URL)["filename"] == "20263100016027CS.pdf"


@responses.activate
def test_head_info_sin_disposition():
    responses.add(responses.HEAD, _URL, headers={"Content-Length": "10"})
    assert _head_info(requests.Session(), _URL) == {"filename": None, "content_length": 10, "etag": None}


@responses.activate
def test_head_info_excepcion_de_red_devuelve_vacio():
    responses.add(responses.HEAD, _URL, body=requests.ConnectionError("boom"))
    assert _head_info(requests.Session(), _URL) == {"filename": None, "content_length": None, "etag": None}


FINI, FFIN = "2000-01-01", "2100-12-31"


def _item(html: str):
    return BeautifulSoup(html, "html.parser").select_one("div.s_dl_item")


_ITEM_CON_NUM_LISTADO = _item(
    '<div class="s_dl_item" data-category="acuerdos" data-href="/web/content/10260?download=true">'
    '<span class="s_dl_file_size">394 Kb</span>'
    '<div class="s_dl_doc_type">resoluciones</div>'
    '<div class="s_dl_doc_name">20263200005647CS <b>Por la cual se actualiza el Manual</b></div>'
    '<div class="s_dl_doc_meta"><span>Publicación: 08/05/2026</span></div></div>'
)


def test_numero_desde_head_filename_gana():
    head = {"filename": "20261000015947CS RESOLUCION DE LINEAMIENTOS Y PAGO.pdf", "content_length": 403369}
    doc = _fila_a_doc(_ITEM_CON_NUM_LISTADO, "Resolución", "R", head, FINI, FFIN, None)
    assert doc.title == "R_SVySP_20261000015947CS_2026"
    assert doc.title_unverified is False
    assert doc.tipo == "Resolución"
    assert doc.f_public == "2026-05-08" and doc.f_providencia == "2026-05-08"
    assert doc.link == {"url": "https://www.supervigilancia.gov.co/web/content/10260?download=true", "method": "GET"}
    assert "verify" not in doc.link
    assert doc.save_path.startswith(f"{_SOURCE}/2026-05-08/Resolución/")


def test_numero_desde_listado_cuando_head_sin_filename():
    head = {"filename": None, "content_length": None}
    doc = _fila_a_doc(_ITEM_CON_NUM_LISTADO, "Resolución", "R", head, FINI, FFIN, None)
    assert doc.title == "R_SVySP_20263200005647CS_2026"


def test_numero_en_prosa():
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/900?download=true">'
        '<div class="s_dl_doc_name">POR MEDIO DE LA CUAL SE EFECTÚA UNA CORRECCIÓN A LA RESOLUCIÓN No. 2023320000649</div>'
        '<div class="s_dl_doc_meta"><span>|Expedición: 30/10/2025</span></div></div>'
    )
    doc = _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, None)
    assert doc.title == "R_SVySP_2023320000649_2025"


def test_sin_numero_se_guarda_con_title_unverified():
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/901?download=true">'
        '<div class="s_dl_doc_name"><strong>LINEAMIENTOS PARA LA AUTORIZACIÓN DE PRESTACIÓN DE SERVICIOS</strong></div>'
        '<div class="s_dl_doc_meta"><span>Expedición: 15/09/2025</span></div></div>'
    )
    doc = _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, None)
    assert doc.title == "LINEAMIENTOS PARA LA AUTORIZACIÓN DE PRESTACIÓN DE SERVICIOS"
    assert doc.title_unverified is True


def test_fecha_hoy_no_es_fecha():
    """Regresión: el sitio pone "Publicación: Hoy" como texto fijo incluso en
    resoluciones de 2007 sin fecha de expedición; tomarlo como la fecha de la
    corrida las fechaba mal y cambiaba de fecha cada día."""
    avisos = []
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/7151?download=true">'
        '<div class="s_dl_doc_name">Resolucion 1532 17-03-09.pdf</div>'
        '<div class="s_dl_doc_meta"><span>Publicación: Hoy</span><span>|</span><span>Expedición: --</span></div></div>'
    )
    assert _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, avisos.append) is None
    assert avisos and "sin fecha" in avisos[0]


def test_fecha_hoy_con_expedicion_usa_la_expedicion():
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/7146?download=true">'
        '<div class="s_dl_doc_name">Resolución 1300025977 características</div>'
        '<div class="s_dl_doc_meta"><span>Publicación: Hace 2 días | Expedición: 15 de marzo de 2021</span></div></div>'
    )
    doc = _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, None)
    assert doc.f_public == "2021-03-15"


def test_fecha_ausente_descarta_con_aviso():
    avisos = []
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/903?download=true">'
        '<div class="s_dl_doc_name">Algo sin fecha</div>'
        '<div class="s_dl_doc_meta"><span>Expedición: --</span></div></div>'
    )
    doc = _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, avisos.append)
    assert doc is None
    assert avisos and "sin fecha" in avisos[0]


def test_zero_width_en_titulo_se_limpia():
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/904?download=true">'
        '<div class="s_dl_doc_name">Res​olución sin número</div>'
        '<div class="s_dl_doc_meta"><span>Expedición: 01/02/2020</span></div></div>'
    )
    doc = _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, None)
    assert doc.title == "Resolución sin número"


def test_piso_2015():
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/905?download=true">'
        '<div class="s_dl_doc_name">Vieja</div>'
        '<div class="s_dl_doc_meta"><span>Expedición: 17/03/2009</span></div></div>'
    )
    assert _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, None) is None


def test_fuera_de_rango_fini_ffin():
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/906?download=true">'
        '<div class="s_dl_doc_name">20251300003057CS x</div>'
        '<div class="s_dl_doc_meta"><span>Expedición: 04/03/2025</span></div></div>'
    )
    assert _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, "2026-01-01", "2026-12-31", None) is None


def test_etiquetas_basura_no_afectan_el_tipo():
    item = _item(
        '<div class="s_dl_item" data-category="circulares" data-href="/web/content/907?download=true">'
        '<div class="s_dl_doc_type">CIRCULAR</div>'
        '<div class="s_dl_doc_name">RESOLUCION No. 202540000099737CS - Por la cual...</div>'
        '<div class="s_dl_doc_meta"><span>Expedición: 01/12/2025</span></div></div>'
    )
    doc = _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, None)
    assert doc.tipo == "Resolución"
    assert doc.title == "R_SVySP_202540000099737CS_2025"


def test_concepto_titulo_es_nombre_de_archivo():
    item = _item(
        '<div class="s_dl_item" data-category="decretos" data-href="/web/content/7786?download=true">'
        '<div class="s_dl_doc_type">circular</div>'
        '<div class="s_dl_doc_name"><strong>Renting operativo.pdf</strong></div>'
        '<div class="s_dl_doc_meta"><span>Expedición: <span>28/05/2018</span></span></div></div>'
    )
    doc = _fila_a_doc(item, "Concepto", "CTO", {"filename": "Renting operativo.pdf", "content_length": 2696244}, FINI, FFIN, None)
    assert doc.tipo == "Concepto"
    assert doc.title == "Renting operativo"
    assert doc.title_unverified is True


# --- _items_de_listado ---

_RES1 = f"{_BASE}/2-1-3-2-resoluciones"
_CONC = f"{_BASE}/2-1-3-8-conceptos-juridicos"


def _pagina(ids):
    bloques = "".join(
        f'<div class="s_dl_item" data-href="/web/content/{i}?download=true">'
        f'<div class="s_dl_doc_name">Doc {i}</div>'
        f'<div class="s_dl_doc_meta"><span>Expedición: 01/06/2025</span></div></div>'
        for i in ids
    )
    return f"<html><body>{bloques}</body></html>"


@responses.activate
def test_items_de_listado_conceptos_una_sola_peticion():
    responses.add(responses.GET, _CONC, body=_pagina([1, 2, 3]))
    items = _items_de_listado(requests.Session(), _CONC, pagina=False, on_progress=None)
    assert len(items) == 3
    assert len(responses.calls) == 1


@responses.activate
def test_items_de_listado_resoluciones_pagina_hasta_vacio():
    responses.add(responses.GET, _RES1, body=_pagina([10, 11]))
    responses.add(responses.GET, f"{_RES1}-pagina02", body=_pagina([20, 21, 22]))
    responses.add(responses.GET, f"{_RES1}-pagina03", body=_pagina([]))  # vacía -> parar
    # -pagina04 NO se registra: si el scraper la pide, responses lanza ConnectionError y el test falla
    items = _items_de_listado(requests.Session(), _RES1, pagina=True, on_progress=None)
    assert len(items) == 5
    urls = [c.request.url for c in responses.calls]
    assert urls == [_RES1, f"{_RES1}-pagina02", f"{_RES1}-pagina03"]


@responses.activate
def test_items_de_listado_error_en_pagina1_devuelve_vacio_con_aviso():
    avisos = []
    responses.add(responses.GET, _RES1, status=502)
    items = _items_de_listado(requests.Session(), _RES1, pagina=True, on_progress=avisos.append)
    assert items == []
    assert avisos and "Error consultando" in avisos[0]


@responses.activate
def test_items_de_listado_tope_duro_de_paginas(monkeypatch):
    monkeypatch.setattr("core.scrapers.families.supervigilancia._PAGINA_TOPE", 3)
    responses.add(responses.GET, _RES1, body=_pagina([1]))
    responses.add(responses.GET, f"{_RES1}-pagina02", body=_pagina([2]))
    responses.add(responses.GET, f"{_RES1}-pagina03", body=_pagina([3]))
    items = _items_de_listado(requests.Session(), _RES1, pagina=True, on_progress=None)
    assert len(items) == 3  # para en pagina03 por el tope, no pide pagina04


# --- ScrapSupervigilancia.scrap ---


def _bloque(i, nombre, meta):
    return (
        f'<div class="s_dl_item" data-href="/web/content/{i}?download=true">'
        f'<div class="s_dl_doc_name">{nombre}</div>'
        f'<div class="s_dl_doc_meta"><span>{meta}</span></div></div>'
    )


def _head(url, filename=None, length=None, etag=None):
    headers = {}
    if etag is not None:
        headers["ETag"] = f'"{etag}"'
    if filename is not None:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    if length is not None:
        headers["Content-Length"] = str(length)
    responses.add(responses.HEAD, url, headers=headers)


def _cd_url(i):
    return f"{_BASE}/web/content/{i}?download=true"


@responses.activate
def test_scrap_end_to_end_dos_secciones():
    responses.add(responses.GET, _RES1, body=(
        _bloque(100, "20261000000001CS Uno", "Publicación: 01/03/2026")
        + _bloque(101, "Sin número dos", "Expedición: 02/03/2026")
    ))
    responses.add(responses.GET, f"{_RES1}-pagina02", body="<html></html>")  # vacía
    responses.add(responses.GET, _CONC, body=_bloque(200, "Renting operativo.pdf", "Expedición: 28/05/2018"))
    _head(_cd_url(100), filename="20261000000001CS Uno.pdf", length=111)
    _head(_cd_url(101), filename=None, length=222)
    _head(_cd_url(200), filename="Renting operativo.pdf", length=333)

    docs = ScrapSupervigilancia().scrap("2000-01-01", "2100-12-31")
    titles = sorted(d.title for d in docs)
    assert titles == sorted(["Renting operativo", "R_SVySP_20261000000001CS_2026", "Sin número dos"])
    assert {d.tipo for d in docs} == {"Resolución", "Concepto"}


@responses.activate
def test_scrap_dedup_primaria_por_id():
    # el mismo id en página 1 y página 2 -> un solo doc, un solo HEAD
    responses.add(responses.GET, _RES1, body=_bloque(100, "20261000000001CS Uno", "Publicación: 01/03/2026"))
    responses.add(responses.GET, f"{_RES1}-pagina02", body=_bloque(100, "20261000000001CS Uno (repe)", "Publicación: 01/03/2026"))
    responses.add(responses.GET, f"{_RES1}-pagina03", body="<html></html>")
    responses.add(responses.GET, _CONC, body="<html></html>")
    _head(_cd_url(100), filename="20261000000001CS.pdf", length=111)

    docs = ScrapSupervigilancia().scrap("2000-01-01", "2100-12-31")
    assert len(docs) == 1
    assert sum(1 for c in responses.calls if c.request.method == "HEAD") == 1


@responses.activate
def test_scrap_dedup_secundaria_por_content_length_y_filename():
    responses.add(responses.GET, _RES1, body=(
        _bloque(100, "Res A", "Publicación: 01/03/2026")
        + _bloque(200, "Res B", "Publicación: 01/03/2026")
    ))
    responses.add(responses.GET, f"{_RES1}-pagina02", body="<html></html>")
    responses.add(responses.GET, _CONC, body="<html></html>")
    _head(_cd_url(100), filename="20261000015947CS ALGO.pdf", length=403369)
    _head(_cd_url(200), filename="20261000015947CS ALGO.pdf", length=403369)  # mismo archivo, id distinto

    avisos = []
    docs = ScrapSupervigilancia().scrap("2000-01-01", "2100-12-31", on_progress=avisos.append)
    assert len(docs) == 1
    assert any("mismo archivo" in a for a in avisos)


@responses.activate
def test_scrap_head_con_error_de_red_no_rompe():
    responses.add(responses.GET, _RES1, body=_bloque(100, "20263200005647CS Uno", "Publicación: 01/03/2026"))
    responses.add(responses.GET, f"{_RES1}-pagina02", body="<html></html>")
    responses.add(responses.GET, _CONC, body="<html></html>")
    responses.add(responses.HEAD, _cd_url(100), body=requests.ConnectionError("boom"))

    docs = ScrapSupervigilancia().scrap("2000-01-01", "2100-12-31")
    assert len(docs) == 1
    assert docs[0].title == "R_SVySP_20263200005647CS_2026"  # cae al número del listado


@responses.activate
def test_scrap_respeta_limit():
    responses.add(responses.GET, _RES1, body="".join(
        _bloque(i, f"2026100000000{i}CS x", "Publicación: 01/03/2026") for i in range(1, 6)
    ))
    responses.add(responses.GET, f"{_RES1}-pagina02", body="<html></html>")
    responses.add(responses.GET, _CONC, body="<html></html>")
    for i in range(1, 6):
        _head(_cd_url(i), filename=f"2026100000000{i}CS.pdf", length=i)
    docs = ScrapSupervigilancia().scrap("2000-01-01", "2100-12-31", limit=2)
    assert len(docs) == 2


def test_familia_registrada():
    assert FAMILY_REGISTRY.get("supervigilancia") is ScrapSupervigilancia
    assert isinstance(resolve_scraper("supervigilancia", {}), ScrapSupervigilancia)


def test_corrida_diaria_mira_un_mes_atras():
    assert ScrapSupervigilancia.scheduled_min_lookback_days == 30


def test_registrada_al_importar_el_paquete():
    import importlib
    import core.scrapers.families as fam
    importlib.reload(fam)
    assert "supervigilancia" in FAMILY_REGISTRY


# --- Circulares ---

_CIRC = f"{_BASE}/2-1-3-3-circulares"


def test_circular_sin_cs_toma_el_numero_del_texto():
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/7762?download=true">'
        '<div class="s_dl_doc_name">Circular externa 20251300000015 corrección circular tarifas mínimas</div>'
        '<div class="s_dl_doc_meta"><span>| Expedición: 21/01/2025</span></div></div>'
    )
    head = {"filename": "Circular Externa 20251300000015 correccion.pdf", "content_length": 1}
    doc = _fila_a_doc(item, "Circular", "C", head, FINI, FFIN, None)
    assert doc.tipo == "Circular"
    assert doc.title == "C_SVySP_20251300000015_2025"
    assert doc.title_unverified is False


def test_anexo_lleva_sufijo_y_no_choca_con_la_circular():
    """Regresión: "Circular 465 de 2017" y "Circular 465 de 2017 anexo" son dos
    PDF distintos; sin sufijo ambos quedaban como C_SVySP_465_2017."""
    def fila(i, nombre):
        return _item(
            f'<div class="s_dl_item" data-href="/web/content/{i}?download=true">'
            f'<div class="s_dl_doc_name">{nombre}</div>'
            '<div class="s_dl_doc_meta"><span>|Expedición: 05/10/2017</span></div></div>'
        )
    sin = {"filename": None, "content_length": None}
    principal = _fila_a_doc(fila(7767, "Circular 465 de 2017.pdf"), "Circular", "C", sin, FINI, FFIN, None)
    anexo = _fila_a_doc(fila(7768, "Circular 465 de 2017 anexo.pdf"), "Circular", "C", sin, FINI, FFIN, None)
    assert principal.title == "C_SVySP_465_2017"
    assert anexo.title == "C_SVySP_465_2017_A01"
    assert principal.save_path != anexo.save_path


@responses.activate
def test_scrap_incluye_circulares_sin_paginar():
    responses.add(responses.GET, _RES1, body="<html></html>")
    responses.add(responses.GET, _CONC, body="<html></html>")
    responses.add(responses.GET, _CIRC, body=_bloque(7765, "Circular 20241000000045CS Prohibición", "|Expedición: 23/09/2024"))
    # -pagina02 de circulares NO se registra: el listado es una sola página
    _head(_cd_url(7765), filename="CIRCULAR 20241000000045CS PROHIBICION.pdf", length=5)

    docs = ScrapSupervigilancia().scrap("2000-01-01", "2100-12-31")
    assert [(d.tipo, d.title) for d in docs] == [("Circular", "C_SVySP_20241000000045CS_2024")]
    assert not any("-pagina" in c.request.url for c in responses.calls if "circulares" in c.request.url)


@responses.activate
def test_scrap_dedup_por_etag_aunque_cambie_el_nombre():
    """Regresión: el sitio sube el mismo PDF dos veces con nombres levemente
    distintos ("...oficiales Sup.pdf" / "...oficiales .pdf"); con la clave
    (tamaño, nombre) entraban los dos con el mismo título y la misma ruta."""
    responses.add(responses.GET, _RES1, body=(
        _bloque(7139, "Resolución 20253000002067CS medidas", "Publicación: 08/04/2025")
        + _bloque(19434, "Resolución 20253000002067CS medidas", "Publicación: 08/04/2025")
    ))
    responses.add(responses.GET, f"{_RES1}-pagina02", body="<html></html>")
    responses.add(responses.GET, _CONC, body="<html></html>")
    responses.add(responses.GET, _CIRC, body="<html></html>")
    _head(_cd_url(7139), filename="Resolucion 20253000002067CS medidas Sup.pdf", length=456858, etag="a9f30c09")
    _head(_cd_url(19434), filename="Resolucion 20253000002067CS medidas .pdf", length=456858, etag="a9f30c09")

    avisos = []
    docs = ScrapSupervigilancia().scrap("2000-01-01", "2100-12-31", on_progress=avisos.append)
    assert len(docs) == 1
    assert any("mismo archivo" in a for a in avisos)
