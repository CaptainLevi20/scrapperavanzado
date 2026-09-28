import datetime

import pytest

from core.scrapers.families.procuraduria import (
    _id_de_relid,
    _numero_normativa,
    _relid,
    _safe_title,
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
