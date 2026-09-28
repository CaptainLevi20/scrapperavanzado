import datetime

import pytest

from core.scrapers.families.minsalud import (
    _anio_doc,
    _docs,
    _fecha_doc,
    _fecha_local,
    _mes_boletin,
    _norm,
    _numero_norma,
    _radicado,
    _seccion_de,
    _sin_extension,
    _titulo,
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


# ---- sección ----
@pytest.mark.parametrize("tipo,esperado", [
    ("Resolución", ("Resoluciones", "Resolución", "R")),
    ("Resolución ", ("Resoluciones", "Resolución", "R")),
    ("Resolución CRES", ("Resoluciones", "Resolución", "R")),
    ("Circular", ("Circulares", "Circular", "C")),
    ("Circular CRES", ("Circulares", "Circular", "C")),
    ("Concepto", ("Conceptos", "Concepto", "CTO")),
    ("Boletines Jurídicos", ("Boletines", "Boletín Jurídico", "BOL")),
])
def test_seccion_de(tipo, esperado):
    assert _seccion_de(tipo) == esperado


@pytest.mark.parametrize("tipo", ["Decreto", "Ley", "Acuerdo CNSSS", "Proyecto Resolución", None, ""])
def test_seccion_de_otros_tipos_no_entran(tipo):
    assert _seccion_de(tipo) is None


# ---- título ----
_F = datetime.date(2026, 9, 24)


def test_titulo_resolucion_y_circular():
    assert _titulo("R", _item(archivo="Resolución No 1809 de 2026.pdf"), 2026, _F, False) == ("R_MSPS_1809_2026", False)
    assert _titulo("C", _item(archivo="Circular Externa No 0031 de 2026.pdf"), 2026, _F, False) == ("C_MSPS_0031_2026", False)
    assert _titulo("R", _item(archivo="Resolución 013956 de 2016.pdf"), 2016, _F, False) == ("R_MSPS_13956_2016", False)


def test_titulo_anio_es_el_del_documento_aunque_el_nombre_diga_otro():
    assert _titulo("R", _item(archivo="Resolución No. 2722 de 2019.pdf"), 2018, _F, False) == ("R_MSPS_2722_2018", False)


def test_titulo_numero_desde_el_titulo_si_el_archivo_no_lo_trae():
    it = _item(archivo="Res.pdf", titulo="Modificación transitoria resolución 227 de 2020")
    assert _titulo("R", it, 2024, _F, False) == ("R_MSPS_0227_2024", False)


def test_titulo_concepto_y_boletin():
    it = _item(tipo="Concepto", archivo="CONCEPTO JURÍDICO 2026423003321522 ID 2258969 7.pdf")
    assert _titulo("CTO", it, 2026, _F, False) == ("CTO_MSPS_2026423003321522_2026", False)
    bol = _item(tipo="Boletines Jurídicos", archivo="Boletín Jurídico No 5 Mayo 2016.pdf")
    assert _titulo("BOL", bol, 2016, datetime.date(2016, 5, 31), False) == ("BOL_MSPS_MAY_2016", False)


def test_titulo_boletin_no_usa_la_fecha_de_respaldo_para_el_mes():
    bol = _item(id=40, tipo="Boletines Jurídicos", archivo="Boletín Jurídico especial.pdf")
    assert _titulo("BOL", bol, 2016, datetime.date(2016, 1, 1), True) == ("BOL_MSPS_SN40_2016", True)


def test_titulo_sin_numero_usa_sn_id_y_avisa():
    it = _item(id=77, tipo="Circular", archivo="Alcance a la Circular Salud   Vida.pdf")
    assert _titulo("C", it, 2019, _F, False) == ("C_MSPS_SN77_2019", True)
    dec = _item(id=5, tipo="Concepto", archivo="Decreto No. 1600 de 2022.pdf")
    assert _titulo("CTO", dec, 2022, _F, False) == ("CTO_MSPS_SN5_2022", True)


# ---- armado de documentos ----
def test_docs_campos_basicos():
    it = _item(id=8950, tipo="Circular", archivo="Circular Externa No 0031 de 2026.pdf",
               pub="2026-09-24T05:00:00Z", desc="Intensificación de acciones\n\nPublicada en el Diario Oficial",
               subtema="Salud ambiental")
    [d] = _docs([it], "2026-09-01", "2026-09-30", None)
    assert d.title == "C_MSPS_0031_2026"
    assert d.tipo == "Circular" and d.seccion == "Circulares"
    assert d.f_public == d.f_providencia == "2026-09-24"
    assert d.link == {
        "url": "https://www.minsalud.gov.co/Normatividad_Nuevo/Circular%20Externa%20No%200031%20de%202026.pdf",
        "method": "GET",
    }
    assert d.detalle == ("Circular Externa No 0031 de 2026 — Intensificación de acciones Publicada en el "
                         "Diario Oficial (Salud / Salud ambiental)")
    assert d.source == "Ministerio de Salud y Protección Social"
    assert d.save_path == "Ministerio de Salud y Protección Social/2026-09-24/Circular/C_MSPS_0031_2026(extension)"


def test_docs_url_codifica_tildes():
    [d] = _docs([_item(pub="2026-09-21T05:00:00Z")], "2026-09-01", "2026-09-30", None)
    assert d.link["url"] == ("https://www.minsalud.gov.co/Normatividad_Nuevo/"
                             "Resoluci%C3%B3n%20No%201809%20de%202026.pdf")


def test_docs_concepto_no_repite_descripcion_igual_al_titulo_y_agrega_dependencia():
    it = _item(tipo="Concepto", archivo="Concepto Jurídico 202611600000001 de 2026.pdf",
               titulo="Concepto sobre juntas", desc="Concepto  sobre\njuntas", responsable="Dirección Jurídica",
               pub="2026-09-21T05:00:00Z")
    [d] = _docs([it], "2026-09-01", "2026-09-30", None)
    assert d.detalle == "Concepto sobre juntas (Salud) — Dependencia: Dirección Jurídica"


def test_docs_reparte_por_seccion_y_excluye_otros_tipos_y_carpetas():
    items = [
        _item(id=1, tipo="Resolución ", archivo="Resolución No 5 de 2025.pdf", anio="2025", pub="2025-03-01T05:00:00Z"),
        _item(id=2, tipo="Decreto", archivo="Decreto No 7 de 2025.pdf", anio="2025", pub="2025-03-01T05:00:00Z"),
        _item(id=3, tipo="Boletines Jurídicos", archivo="Boletín Jurídico No 3 Marzo 2025.pdf", anio="2025",
              pub="2025-03-31T05:00:00Z"),
        _item(id=4, tipo="Resolución", archivo="Carpeta", anio="2025", carpeta=1),
        _item(id=5, tipo=None, archivo="Suelto.pdf", anio="2025"),
    ]
    docs = _docs(items, "2025-01-01", "2025-12-31", None)
    assert sorted((d.seccion, d.title, d.tipo) for d in docs) == [
        ("Boletines", "BOL_MSPS_MAR_2025", "Boletín Jurídico"),
        ("Resoluciones", "R_MSPS_0005_2025", "Resolución"),
    ]


def test_docs_piso_2015_y_rango():
    items = [
        _item(id=1, archivo="Resolución No 1 de 2014.pdf", anio="2014", pub="2014-05-05T05:00:00Z"),
        _item(id=2, archivo="Resolución No 2 de 2020.pdf", anio="2020", pub="2020-05-05T05:00:00Z"),
        _item(id=3, archivo="Resolución No 3 de 2020.pdf", anio="2020", pub="2020-08-05T05:00:00Z"),
    ]
    assert [d.title for d in _docs(items, "2010-01-01", "2020-06-30", None)] == ["R_MSPS_0002_2020"]


def test_docs_choques_con_sufijo_por_id_estables_ante_el_rango():
    items = [
        _item(id=300, archivo="Resolución No 1809 de 2026 Con anexoTécnico.pdf", pub="2026-09-21T05:00:00Z"),
        _item(id=100, archivo="Resolución No 1809 de 2026.pdf", pub="2026-08-05T05:00:00Z"),
    ]
    todos = {d.f_public: d.title for d in _docs(items, "2026-01-01", "2026-12-31", None)}
    assert todos == {"2026-08-05": "R_MSPS_1809_2026", "2026-09-21": "R_MSPS_1809_2026_2"}
    [solo] = _docs(items, "2026-09-01", "2026-09-30", None)
    assert solo.title == "R_MSPS_1809_2026_2"


def test_docs_avisos_solo_de_documentos_conservados():
    avisos = []
    items = [
        _item(id=7, tipo="Circular", archivo="Alcance a la Circular Salud Vida.pdf", anio="2019",
              creado="2020-01-10T10:00:00Z"),
        _item(id=8, tipo="Circular", archivo="Otra circular sin numero.pdf", anio="2021",
              creado="2021-06-01T10:00:00Z"),
    ]
    docs = _docs(items, "2021-01-01", "2021-12-31", avisos.append)
    assert [d.title for d in docs] == ["C_MSPS_SN8_2021"]
    assert any("C_MSPS_SN8_2021" in a for a in avisos)
    assert not any("SN7" in a for a in avisos)
    assert all("Error" not in a for a in avisos)
    assert all(a.startswith("[Ministerio de Salud y Protección Social] Aviso:") for a in avisos)


# ---- API y scrap() ----
import threading

import requests
import responses

from core.scrapers.families.minsalud import _API, ScrapMinSalud, _listar
from core.scrapers.registry import FAMILY_REGISTRY

_PAGINA2 = "https://www.minsalud.gov.co/_api/pagina2"


def _sesion():
    return requests.Session()


@responses.activate
def test_listar_una_pagina_y_pide_campos_y_top():
    responses.add(responses.GET, _API, json={"value": [_item(id=1)]})
    assert [x["ID"] for x in _listar(_sesion())] == [1]
    url = responses.calls[0].request.url
    assert "%24top=5000" in url or "$top=5000" in url
    assert "FileLeafRef" in url
    assert responses.calls[0].request.headers["Accept"] == "application/json;odata=nometadata"


@responses.activate
def test_listar_sigue_odata_nextlink():
    responses.add(responses.GET, _API, json={"value": [_item(id=1)], "odata.nextLink": _PAGINA2})
    responses.add(responses.GET, _PAGINA2, json={"value": [_item(id=2)]})
    assert [x["ID"] for x in _listar(_sesion())] == [1, 2]


@responses.activate
def test_listar_json_sin_value_es_error():
    responses.add(responses.GET, _API, json={"error": "cambió"})
    with pytest.raises(RuntimeError):
        _listar(_sesion())


def test_minsalud_registrada_y_banderas():
    import core.scrapers.families  # noqa: F401
    assert FAMILY_REGISTRY["minsalud"].__name__ == "ScrapMinSalud"
    assert ScrapMinSalud.scheduled_min_lookback_days == 60
    assert ScrapMinSalud.doc_id_uses_publication_date is False
    assert ScrapMinSalud.checks_for_republication is True


@responses.activate
def test_scrap_devuelve_documentos_del_rango():
    responses.add(responses.GET, _API, json={"value": [
        _item(id=1, archivo="Resolución No 1809 de 2026.pdf", pub="2026-08-05T05:00:00Z"),
        _item(id=2, tipo="Concepto", archivo="Concepto Jurídico 2026423003321522.pdf", pub="2026-09-21T05:00:00Z"),
    ]})
    docs = ScrapMinSalud().scrap(fini="2026-09-01", ffin="2026-09-30")
    assert [d.title for d in docs] == ["CTO_MSPS_2026423003321522_2026"]


@responses.activate
def test_scrap_rango_antes_del_piso_no_consulta():
    assert ScrapMinSalud().scrap(fini="2010-01-01", ffin="2014-12-31") == []
    assert len(responses.calls) == 0


@responses.activate
def test_scrap_error_de_la_api_se_reporta():
    responses.add(responses.GET, _API, status=500)
    mensajes = []
    assert ScrapMinSalud().scrap(fini="2026-01-01", ffin="2026-12-31", on_progress=mensajes.append) == []
    assert any("Error" in m and "biblioteca de normativa" in m for m in mensajes)


@responses.activate
def test_scrap_respeta_stop_event():
    ev = threading.Event()
    ev.set()
    assert ScrapMinSalud().scrap(fini="2026-01-01", ffin="2026-12-31", stop_event=ev) == []
    assert len(responses.calls) == 0
