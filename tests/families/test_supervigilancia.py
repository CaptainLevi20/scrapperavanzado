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
)


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


def test_fecha_de_meta_variants():
    hoy = datetime.date(2026, 9, 10)
    assert _fecha_de_meta("Publicación: 08/05/2026", hoy) == datetime.date(2026, 5, 8)
    assert _fecha_de_meta("|Expedición: 23/01/2008", hoy) == datetime.date(2008, 1, 23)
    assert _fecha_de_meta("Publicación: Hoy", hoy) == hoy
    assert _fecha_de_meta("Expedición: --", hoy) is None
    assert _fecha_de_meta("", hoy) is None
    assert _fecha_de_meta("Expedición: 32/13/2020", hoy) is None


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
    assert got == {"filename": "20261000015947CS RESOLUCION.pdf", "content_length": 403369}


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
    assert _head_info(requests.Session(), _URL) == {"filename": None, "content_length": 10}


@responses.activate
def test_head_info_excepcion_de_red_devuelve_vacio():
    responses.add(responses.HEAD, _URL, body=requests.ConnectionError("boom"))
    assert _head_info(requests.Session(), _URL) == {"filename": None, "content_length": None}


HOY = datetime.date(2026, 9, 10)
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
    doc = _fila_a_doc(_ITEM_CON_NUM_LISTADO, "Resolución", "R", head, FINI, FFIN, HOY, None)
    assert doc.title == "R_SVySP_20261000015947CS_2026"
    assert doc.title_unverified is False
    assert doc.tipo == "Resolución"
    assert doc.f_public == "2026-05-08" and doc.f_providencia == "2026-05-08"
    assert doc.link == {"url": "https://www.supervigilancia.gov.co/web/content/10260?download=true", "method": "GET"}
    assert "verify" not in doc.link
    assert doc.save_path.startswith(f"{_SOURCE}/2026-05-08/Resolución/")


def test_numero_desde_listado_cuando_head_sin_filename():
    head = {"filename": None, "content_length": None}
    doc = _fila_a_doc(_ITEM_CON_NUM_LISTADO, "Resolución", "R", head, FINI, FFIN, HOY, None)
    assert doc.title == "R_SVySP_20263200005647CS_2026"


def test_numero_en_prosa():
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/900?download=true">'
        '<div class="s_dl_doc_name">POR MEDIO DE LA CUAL SE EFECTÚA UNA CORRECCIÓN A LA RESOLUCIÓN No. 2023320000649</div>'
        '<div class="s_dl_doc_meta"><span>|Expedición: 30/10/2025</span></div></div>'
    )
    doc = _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, HOY, None)
    assert doc.title == "R_SVySP_2023320000649_2025"


def test_sin_numero_se_guarda_con_title_unverified():
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/901?download=true">'
        '<div class="s_dl_doc_name"><strong>LINEAMIENTOS PARA LA AUTORIZACIÓN DE PRESTACIÓN DE SERVICIOS</strong></div>'
        '<div class="s_dl_doc_meta"><span>Expedición: 15/09/2025</span></div></div>'
    )
    doc = _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, HOY, None)
    assert doc.title == "LINEAMIENTOS PARA LA AUTORIZACIÓN DE PRESTACIÓN DE SERVICIOS"
    assert doc.title_unverified is True


def test_fecha_hoy():
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/902?download=true">'
        '<div class="s_dl_doc_name">20263100016027CS - Manual</div>'
        '<div class="s_dl_doc_meta"><span>Publicación: Hoy</span><span>|</span><span>Expedición: --</span></div></div>'
    )
    doc = _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, HOY, None)
    assert doc.f_public == "2026-09-10"


def test_fecha_ausente_descarta_con_aviso():
    avisos = []
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/903?download=true">'
        '<div class="s_dl_doc_name">Algo sin fecha</div>'
        '<div class="s_dl_doc_meta"><span>Expedición: --</span></div></div>'
    )
    doc = _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, HOY, avisos.append)
    assert doc is None
    assert avisos and "sin fecha" in avisos[0]


def test_zero_width_en_titulo_se_limpia():
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/904?download=true">'
        '<div class="s_dl_doc_name">Res​olución sin número</div>'
        '<div class="s_dl_doc_meta"><span>Expedición: 01/02/2020</span></div></div>'
    )
    doc = _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, HOY, None)
    assert doc.title == "Resolución sin número"


def test_piso_2015():
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/905?download=true">'
        '<div class="s_dl_doc_name">Vieja</div>'
        '<div class="s_dl_doc_meta"><span>Expedición: 17/03/2009</span></div></div>'
    )
    assert _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, HOY, None) is None


def test_fuera_de_rango_fini_ffin():
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/906?download=true">'
        '<div class="s_dl_doc_name">20251300003057CS x</div>'
        '<div class="s_dl_doc_meta"><span>Expedición: 04/03/2025</span></div></div>'
    )
    assert _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, "2026-01-01", "2026-12-31", HOY, None) is None


def test_etiquetas_basura_no_afectan_el_tipo():
    item = _item(
        '<div class="s_dl_item" data-category="circulares" data-href="/web/content/907?download=true">'
        '<div class="s_dl_doc_type">CIRCULAR</div>'
        '<div class="s_dl_doc_name">RESOLUCION No. 202540000099737CS - Por la cual...</div>'
        '<div class="s_dl_doc_meta"><span>Expedición: 01/12/2025</span></div></div>'
    )
    doc = _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, HOY, None)
    assert doc.tipo == "Resolución"
    assert doc.title == "R_SVySP_202540000099737CS_2025"


def test_concepto_titulo_es_nombre_de_archivo():
    item = _item(
        '<div class="s_dl_item" data-category="decretos" data-href="/web/content/7786?download=true">'
        '<div class="s_dl_doc_type">circular</div>'
        '<div class="s_dl_doc_name"><strong>Renting operativo.pdf</strong></div>'
        '<div class="s_dl_doc_meta"><span>Expedición: <span>28/05/2018</span></span></div></div>'
    )
    doc = _fila_a_doc(item, "Concepto", "CTO", {"filename": "Renting operativo.pdf", "content_length": 2696244}, FINI, FFIN, HOY, None)
    assert doc.tipo == "Concepto"
    assert doc.title == "Renting operativo"
    assert doc.title_unverified is True
