import datetime

import requests
import responses

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
