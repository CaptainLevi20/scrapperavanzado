import datetime

import pytest

from core.scrapers.families.procuraduria import (
    _fecha_iso,
    _fecha_sirel,
    _id_de_relid,
    _numero_concepto,
    _numero_normativa,
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
