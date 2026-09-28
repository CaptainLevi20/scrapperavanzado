import datetime

import pytest

from core.scrapers.families.minsalud import (
    _anio_doc,
    _fecha_doc,
    _fecha_local,
    _mes_boletin,
    _norm,
    _numero_norma,
    _radicado,
    _sin_extension,
)


def test_norm_quita_acentos_y_minusculas():
    # NFKD convierte el ordinal "º" en "o": "Nº" queda "no", que el marcador de número ya reconoce
    assert _norm("Resolución JURÍDICO Nº") == "resolucion juridico no"


def test_sin_extension():
    assert _sin_extension("Resolución No 1809 de 2026.pdf") == "Resolución No 1809 de 2026"
    assert _sin_extension("Circular externa No. 0015.PDF") == "Circular externa No. 0015"
    assert _sin_extension("Sin extension") == "Sin extension"


@pytest.mark.parametrize("texto,esperado", [
    # regla 1: número + año (tolerando de/del y fecha en prosa en medio)
    ("Resolución No. 1809 de 2026", 1809),
    ("Resolucion No 276 de 2019", 276),
    ("Resolución No.2722 de 2019", 2722),
    ("Resolución 1099 del 2020", 1099),
    ("Resolución No. 0304de 2015", 304),
    ("Resolución No. 001133 de 2017", 1133),
    ("Resolución Nro.00532 de 2017", 532),
    ("Resolución 013956 de 2016", 13956),
    ("Circular No. 45 del 31 de Dciiembre del 2019", 45),
    ("Circular Externa No 0031 de 2026", 31),
    ("Circualr No. 12 de 2016", 12),
    ("Modificación transitoria resolución 227 de 2020", 227),
    # regla 2: número tras el marcador No/Nº/N° (con . o _ opcional)
    ("Circular externa No. 0015", 15),
    ("Circular externa No_9 Minsalud y UNGRD", 9),
    # regla 3: número al inicio
    ("3312 Establece requisitos - condiciones para giro", 3312),
    # regla 4: último número del nombre
    ("Circular Conjunta 036", 36),
])
def test_numero_norma(texto, esperado):
    assert _numero_norma(texto) == esperado


@pytest.mark.parametrize("texto", ["Alcance a la Circular Salud   Vida", "Res", "", None])
def test_numero_norma_none(texto):
    assert _numero_norma(texto) is None


@pytest.mark.parametrize("texto,esperado", [
    ("Concepto Jurídico 201711601019341 de 2017", "201711601019341"),
    ("CONCEPTO JURÍDICO 2026423003321522 ID 2258969 7", "2026423003321522"),
    ("Concepto Jurídico No 2026424000867002", "2026424000867002"),
    ("Concepto Jurídico  202211600135321 de 2022", "202211600135321"),
])
def test_radicado(texto, esperado):
    assert _radicado(texto) == esperado


@pytest.mark.parametrize("texto", ["Decreto No. 1600 de 2022", "Concepto 12345 de 2020", "", None])
def test_radicado_none(texto):
    assert _radicado(texto) is None


@pytest.mark.parametrize("texto,fecha,esperado", [
    ("Boletín Jurídico No 5 Mayo 2016", None, 5),
    ("Boletín Jurídico No. 002 de febrero 2025", None, 2),
    ("Boletín Jurídico No 12 Diciembre de 2019", None, 12),
    ("Boletín Jurídico No 9 Setiembre 2018", None, 9),
    ("Boletin Juridico No 4 del 2015", None, 4),
    ("Boletín Jurídico No. 06  de 2026", None, 6),
    ("Boletín Jurídico especial", datetime.date(2020, 7, 31), 7),
    ("Boletín Jurídico Diciembre - Noviembre 2015", None, 12),
])
def test_mes_boletin(texto, fecha, esperado):
    assert _mes_boletin(texto, fecha) == esperado


@pytest.mark.parametrize("texto", ["Boletín Jurídico especial", "Boletín Jurídico No 15 de 2020"])
def test_mes_boletin_none(texto):
    assert _mes_boletin(texto, None) is None


# ---- helper con la forma real de un elemento de la API ----
def _item(id=1, tipo="Resolución", archivo="Resolución No 1809 de 2026.pdf", titulo=None,
          anio="2026", pub=None, desc=None, tematica="Salud", subtema=None,
          responsable=None, creado="2026-09-22T15:27:31Z", carpeta=0):
    return {
        "ID": id,
        "Title": titulo if titulo is not None else archivo.rsplit(".", 1)[0],
        "FileLeafRef": archivo,
        "FileRef": f"/Normatividad_Nuevo/{archivo}",
        "FSObjType": carpeta,
        "Tipo_x0020_de_x0020_Norma": tipo,
        "A_x00f1_o": anio,
        "Publicaci_x00f3_n": pub,
        "Descripci_x00f3_n": desc,
        "Tem_x00e1_tica": tematica,
        "Subtema": subtema,
        "Responsable": responsable,
        "Created": creado,
    }


# ---- año ----
def test_anio_doc_de_la_columna():
    assert _anio_doc(_item(anio="2017")) == 2017
    assert _anio_doc(_item(anio="2017 ")) == 2017


def test_anio_doc_del_nombre_si_falta_la_columna():
    assert _anio_doc(_item(anio=None, archivo="Circular No 5 de 2019.pdf")) == 2019


def test_anio_doc_no_confunde_un_radicado_con_un_anio():
    it = _item(anio=None, archivo="Concepto Jurídico 201711601019341.pdf", creado="2017-06-30T10:00:00Z")
    assert _anio_doc(it) == 2017


def test_anio_doc_de_created_como_ultimo_recurso():
    assert _anio_doc(_item(anio="", archivo="Res.pdf", creado="2024-03-01T12:00:00Z")) == 2024


# ---- fecha ----
def test_fecha_local_convierte_utc_a_colombia():
    assert _fecha_local("2026-09-24T05:00:00Z") == datetime.date(2026, 9, 24)
    assert _fecha_local("2026-09-24T04:59:00Z") == datetime.date(2026, 9, 23)
    assert _fecha_local(None) is None
    assert _fecha_local("basura") is None


def test_fecha_doc_prefiere_publicacion():
    it = _item(pub="2026-09-24T05:00:00Z", desc="con fecha 25 de septiembre de 2026")
    assert _fecha_doc(it, 2026) == (datetime.date(2026, 9, 24), False)


def test_fecha_doc_prosa_de_la_descripcion_del_mismo_anio():
    it = _item(desc="Publicada en el Diario Oficial No. 53.638 con fecha 25 de septiembre de 2026")
    assert _fecha_doc(it, 2026) == (datetime.date(2026, 9, 25), False)


def test_fecha_doc_prosa_del_titulo():
    it = _item(archivo="Circular No. 45 de 2019.pdf", titulo="Circular No. 45 del 31 de diciembre del 2019",
               anio="2019", creado="2020-01-10T10:00:00Z")
    assert _fecha_doc(it, 2019) == (datetime.date(2019, 12, 31), False)


def test_fecha_doc_ignora_prosa_de_otro_anio_y_usa_created():
    it = _item(anio="2017", desc="Deroga la resolución del 5 de marzo de 2014", creado="2017-06-30T15:00:00Z")
    assert _fecha_doc(it, 2017) == (datetime.date(2017, 6, 30), False)


def test_fecha_doc_respaldo_1_de_enero_si_created_es_de_otro_anio():
    it = _item(anio="2019", creado="2020-01-10T10:00:00Z")
    assert _fecha_doc(it, 2019) == (datetime.date(2019, 1, 1), True)
