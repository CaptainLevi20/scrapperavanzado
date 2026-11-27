import json
import threading

import pytest
import requests
import responses

from core.scrapers.families import contraloria as cgr
from core.scrapers.families.contraloria import (
    _ANIO_MINIMO,
    _API,
    _SOURCE,
    ScrapContraloria,
    _fecha,
    _identificar,
    _link,
    _num_circular,
    _num_concepto,
    _num_resolucion,
    _partes_archivo,
    _valor,
)
from core.scrapers.registry import FAMILY_REGISTRY, resolve_scraper
from core.utils import compute_doc_id, extract_filename


@pytest.fixture(autouse=True)
def _sin_pausa(monkeypatch):
    monkeypatch.setattr(cgr, "_PAUSA_VERIFICACION", 0)


# --- Filas reales de la API (recortadas a los campos que se usan) ----------

def _res(id_, archivo, fecha, numero=None, clasif="Resolución Organizacional", titulo="Por la cual se adopta"):
    return {
        "odata.type": "SP.Data.ResolucionesItem",
        "Id": id_,
        "FileLeafRef": archivo,
        "Title": titulo,
        "Clasificacion": clasif,
        "Numero_x0020_de_x0020_resolucion": numero if numero is not None else archivo.rsplit(".", 1)[0],
        "Fecha_x0020_de_x0020_expedicion": fecha,
        "Vigencia": "Rige a partir de su publicación",
    }


def _cto(id_, archivo, fecha, numero=None, tema="ADQUISICIÓN DE VEHÍCULOS ELÉCTRICOS"):
    return {
        "odata.type": "SP.Data.Conceptos_x0020_JuridicosItem",
        "Id": id_,
        "FileLeafRef": archivo,
        "Title": None,
        "Fecha": fecha,
        "Tema": tema,
        "Numero_x0020_de_x0020_concepto": numero if numero is not None else archivo.rsplit(".", 1)[0],
        "Ano": fecha[:4] if fecha else None,
        "TipoConcepto": "Posición institucional",
    }


def _cir(id_, archivo, fecha, numero=None, asunto="Directrices sobre el uso de la inteligencia artificial"):
    return {
        "odata.type": "SP.Data.CircularesItem",
        "Id": id_,
        "FileLeafRef": archivo,
        "Title": None,
        "Numero_x0020_de_x0020_Circular": numero if numero is not None else archivo.rsplit(".", 1)[0],
        "Fecha": fecha,
        "Asunto2": asunto,
        "Destinatario": None,
    }


def _jur(id_, archivo="25000-23-37-000-2022-00567-01.pdf"):
    return {"odata.type": "SP.Data.JurisprudenciaItem", "Id": id_, "FileLeafRef": archivo,
            "Fecha": "2024-09-12T07:00:00Z", "Corporacion": "Consejo de Estado"}


def _file_info(id_, biblioteca, archivo):
    return {
        "odata.metadata": "https://congenrep.sharepoint.com/sites/relatoria2/_api/$metadata#SP.ListData.CircularesItems/@Element&$select=FileLeafRef,FileRef,ID",
        "Id": id_,
        "FileLeafRef": archivo,
        "ID": id_,
        "FileRef": f"/sites/relatoria2/{biblioteca}/{archivo}",
    }


def _mock_listados(res=(), cto=(), cir=(), jur=()):
    responses.add(responses.POST, f"{_API}/getResoluciones", json=list(res))
    responses.add(responses.POST, f"{_API}/getConceptosJuridicos", json=list(cto))
    responses.add(responses.POST, f"{_API}/getCirculares", json=list(cir))
    responses.add(responses.POST, f"{_API}/getJurisprudencia", json=list(jur))


def _llamadas(endpoint):
    return [c for c in responses.calls if c.request.url == f"{_API}/{endpoint}"]


# --- Registro y constantes ---------------------------------------------------

def test_registro_y_constantes():
    assert _SOURCE == "Contraloría General de la República"
    assert _ANIO_MINIMO == 2015
    assert FAMILY_REGISTRY["contraloria"] is ScrapContraloria
    assert isinstance(resolve_scraper("contraloria", {}), ScrapContraloria)
    assert ScrapContraloria.scheduled_min_lookback_days == 120
    assert ScrapContraloria.checks_for_republication is False
    assert ScrapContraloria.doc_id_uses_publication_date is False


# --- Caso 1: fechas ----------------------------------------------------------

@pytest.mark.parametrize("crudo", ["2026-11-04T05:00:00Z", "2026-11-04T07:00:00Z", "2026-11-04T08:00:00Z"])
def test_fecha_toma_la_parte_de_fecha_sin_convertir_zona(crudo):
    assert _fecha({"Fecha": crudo}, "Fecha") == "2026-11-04"


def test_fecha_vacia_o_ausente():
    assert _fecha({"Fecha": None}, "Fecha") is None
    assert _fecha({"Fecha": ""}, "Fecha") is None
    assert _fecha({}, "Fecha") is None


# --- Caso 2: resoluciones ----------------------------------------------------

@pytest.mark.parametrize("archivo, esperado", [
    ("OGZ-0897-2026.pdf", "R_CGR_OGZ-0897_2026"),
    ("REG-EJE-0123-2026.PDF", "R_CGR_REG-EJE-0123_2026"),
    ("OGZ-00801-2022.PDF", "R_CGR_OGZ-00801_2022"),
    ("REG-EJE-0131A-2024.pdf", "R_CGR_REG-EJE-0131A_2024"),
    ("REG-ORG-0043-2020.pdf", "R_CGR_REG-ORG-0043_2020"),
    ("OGZ-0824-2023 (2).PDF", "R_CGR_OGZ-0824_2023"),
    ("OGZ-0825-2023 FD.PDF", "R_CGR_OGZ-0825_2023"),
    ("OGZ-0553-2017. .pdf", "R_CGR_OGZ-0553_2017"),
])
def test_titulo_resolucion_numero_tal_cual(archivo, esperado):
    fila = _res(1, archivo, "2026-01-01T05:00:00Z")
    stem, _ = _partes_archivo(archivo)
    titulo, tipo, _clave, _anio, ok = _identificar("resoluciones", fila, "Numero_x0020_de_x0020_resolucion", stem, 2026)
    assert (titulo, tipo, ok) == (esperado, "Resolución", True)


def test_resolucion_cae_al_campo_numero_si_el_archivo_no_encaja():
    fila = _res(1, "Resolución firmada.pdf", "2016-01-01T05:00:00Z", numero="REG-ORG-0008-2016")
    titulo, _tipo, _clave, _anio, ok = _identificar(
        "resoluciones", fila, "Numero_x0020_de_x0020_resolucion", "Resolución firmada", 2016)
    assert (titulo, ok) == ("R_CGR_REG-ORG-0008_2016", True)


def test_resolucion_sin_numero_queda_sin_verificar():
    fila = _res(1, "Resolución firmada.pdf", "2016-01-01T05:00:00Z", numero="")
    titulo, _tipo, clave, anio, ok = _identificar(
        "resoluciones", fila, "Numero_x0020_de_x0020_resolucion", "Resolución firmada", 2016)
    assert ok is False
    assert titulo == "Resolución firmada"
    assert clave == "archivo-Resolución firmada"
    assert anio == 2016


def test_num_resolucion_serie_y_anio():
    assert _num_resolucion("REG-EJE-0103-2021") == ("REG-EJE", "0103", 2021)
    assert _num_resolucion("CGR-OJ-130-2026") is None


# --- Caso 3: conceptos -------------------------------------------------------

@pytest.mark.parametrize("archivo, esperado", [
    ("CGR-OJ-130-2026.pdf", "CTO_CGR_130_2026"),
    ("CGR–OJ-157-2025.pdf", "CTO_CGR_157_2025"),  # guion largo
    ("CGR-OJ-157 de 2024.pdf", "CTO_CGR_157_2024"),
    ("CGR-OJ-076  de 2024.pdf", "CTO_CGR_076_2024"),
    ("CGR-OJ-033de 2024.pdf", "CTO_CGR_033_2024"),
    ("CGR-OJ-0094A-2021-PI.pdf", "CTO_CGR_0094A_2021"),
    ("CGR-OJ-0119-2021PI.pdf", "CTO_CGR_0119_2021"),
    ("CGR-OJ-096-2022 PI.pdf", "CTO_CGR_096_2022"),
    ("CGR-OJ-PI-144-2024.pdf", "CTO_CGR_144_2024"),
    ("CGR-OJ-PI-031 de 2024.pdf", "CTO_CGR_031_2024"),
    ("CGR-OJ-PI-217-2022.pdf", "CTO_CGR_217_2022"),
    ("0CGR-OJ-0189-2018.pdf", "CTO_CGR_0189_2018"),
    ("CGR-0J-016 de 2024.pdf", "CTO_CGR_016_2024"),
    ("CGR-OJ-177-2022.docx.pdf", "CTO_CGR_177_2022"),
    ("CGR-OJ-0021-2018 (1).pdf", "CTO_CGR_0021_2018"),
    ("2015EE0012345.pdf", "CTO_CGR_2015EE0012345_2015"),
    ("2015IE0121754.pdf", "CTO_CGR_2015IE0121754_2015"),
    ("20151E0038709.pdf", "CTO_CGR_20151E0038709_2015"),
    ("CGR-OJ-2016IE0067575.pdf", "CTO_CGR_2016IE0067575_2016"),
])
def test_titulo_concepto(archivo, esperado):
    fila = _cto(1, archivo, "2024-01-01T05:00:00Z")
    stem, _ = _partes_archivo(archivo)
    titulo, tipo, _clave, _anio, ok = _identificar("conceptos", fila, "Numero_x0020_de_x0020_concepto", stem, 2024)
    assert (titulo, tipo, ok) == (esperado, "Concepto", True)


def test_concepto_anio_del_numero_no_de_la_fecha():
    assert _num_concepto("CGR-OJ-017-2002") == ("017", 2002)


# --- Caso 4: circulares ------------------------------------------------------

@pytest.mark.parametrize("archivo, esperado, tipo", [
    ("Circular 0004-2015.docx", "C_CGR_0004_2015", "Circular"),
    ("Circular 023-2025.pdf", "C_CGR_023_2025", "Circular"),
    ("Circular 0005-2021.PDF", "C_CGR_0005_2021", "Circular"),
    ("Circular Conjunta 0010-2025.pdf", "CJ_CGR_0010_2025", "Circular conjunta"),
])
def test_titulo_circular(archivo, esperado, tipo):
    fila = _cir(1, archivo, "2025-01-01T08:00:00Z")
    stem, _ = _partes_archivo(archivo)
    titulo, t, _clave, _anio, ok = _identificar("circulares", fila, "Numero_x0020_de_x0020_Circular", stem, 2025)
    assert (titulo, t, ok) == (esperado, tipo, True)


def test_circular_sin_numero_queda_sin_verificar():
    fila = _cir(34, "Circular - Auditorías.pdf", "2020-03-18T05:00:00Z", numero="CIRCULAR- AUDITORIAS")
    titulo, tipo, _clave, _anio, ok = _identificar(
        "circulares", fila, "Numero_x0020_de_x0020_Circular", "Circular - Auditorías", 2020)
    assert (titulo, tipo, ok) == ("Circular - Auditorías", "Circular", False)


def test_num_circular_desde_campo_sin_palabra():
    assert _num_circular("023-2025", cgr._CIR_NUM_RE) == (False, "023", 2025)


# --- Caso 5: link e identidad ------------------------------------------------

def test_valor_normalizado():
    assert _valor("0131A") == "131A"
    assert _valor("00801") == "801"
    assert _valor("0000") == "0"
    assert _valor("2015EE0012345") == "2015EE0012345"


def test_link_post_con_path_y_extension_en_fragmento():
    link = _link(1928, "Resoluciones", "resoluciones", "OGZ-897-2026", "pdf")
    assert link["method"] == "POST"
    assert link["url"] == f"{_API}/getDownloadFileApiBuffer#OGZ-897-2026.pdf"
    assert link["body"] == {"Id": 1928, "List": "Resoluciones", "path": "cgr/resoluciones/OGZ-897-2026"}
    # El descargador toma la extensión del final de la URL (sin Content-Disposition).
    assert extract_filename("", "application/octet-stream", link["url"], "x")["extension"] == ".pdf"
    assert extract_filename("", "application/octet-stream",
                            _link(5, "Circulares", "circulares", "4-2015", "docx")["url"], "x")["extension"] == ".docx"


@responses.activate
def test_identidad_no_cambia_si_la_cgr_recrea_la_fila_con_otro_id_y_fecha():
    _mock_listados(cto=[_cto(5979, "CGR-OJ-130-2026.pdf", "2026-11-23T08:00:00Z")])
    antes = ScrapContraloria().scrap("2026-01-01", "2026-12-31")
    responses.reset()
    _mock_listados(cto=[_cto(5984, "CGR-OJ-130-2026.pdf", "2026-11-17T08:00:00Z")])
    despues = ScrapContraloria().scrap("2026-01-01", "2026-12-31")
    assert antes[0].link["body"]["Id"] == 5979 and despues[0].link["body"]["Id"] == 5984
    assert compute_doc_id(antes[0], include_publication_date=False) == compute_doc_id(
        despues[0], include_publication_date=False)


@responses.activate
def test_documentos_del_mismo_dia_tienen_doc_id_distinto():
    _mock_listados(res=[
        _res(1928, "OGZ-0897-2026.pdf", "2026-11-04T08:00:00Z"),
        _res(1927, "OGZ-0896-2026.pdf", "2026-11-04T08:00:00Z"),
        _res(1926, "REG-EJE-0896-2026.pdf", "2026-11-04T08:00:00Z"),
    ])
    docs = ScrapContraloria().scrap("2026-01-01", "2026-12-31")
    ids = {compute_doc_id(d, include_publication_date=False) for d in docs}
    assert len(ids) == 3


# --- Caso 6: Id repetidos entre bibliotecas ----------------------------------

@responses.activate
def test_id_repetido_que_coincide_se_emite():
    _mock_listados(
        res=[_res(65, "OGZ-0350-2015.pdf", "2015-05-01T05:00:00Z")],
        cir=[_cir(65, "Circular 0009-2022.pdf", "2022-11-16T05:00:00Z")],
    )
    responses.add(responses.POST, f"{_API}/getFileInfo",
                  json=_file_info(65, "Circulares", "Circular 0009-2022.pdf"))
    docs = ScrapContraloria().scrap("2022-01-01", "2022-12-31")
    assert [d.title for d in docs] == ["C_CGR_0009_2022"]
    pedido = json.loads(_llamadas("getFileInfo")[0].request.body)
    assert pedido == {"Id": 65, "List": "Circulares"}


@responses.activate
def test_id_repetido_que_entrega_otro_archivo_se_omite_con_aviso():
    _mock_listados(
        res=[_res(1259, "OGZ-0876-2025.pdf", "2025-12-10T05:00:00Z")],
        cto=[_cto(1259, "CGR-OJ-173-2021.pdf", "2021-08-01T05:00:00Z")],
    )
    responses.add(responses.POST, f"{_API}/getFileInfo",
                  json=_file_info(1259, "Conceptos Juridicos", "CGR-OJ-173-2021.pdf"))
    avisos = []
    docs = ScrapContraloria().scrap("2025-01-01", "2025-12-31", on_progress=avisos.append)
    assert docs == []
    assert any("R_CGR_OGZ-0876_2025" in a and "otro archivo" in a for a in avisos)


@responses.activate
def test_id_repetido_con_api_fallando_dos_veces_se_omite():
    _mock_listados(
        cir=[_cir(7, "Circular 0011-2015.docx", "2015-07-15T05:00:00Z")],
        jur=[_jur(7)],
    )
    responses.add(responses.POST, f"{_API}/getFileInfo", body="Ohhh, something went wrong...",
                  content_type="text/plain")
    responses.add(responses.POST, f"{_API}/getFileInfo", body="Ohhh, something went wrong...",
                  content_type="text/plain")
    avisos = []
    docs = ScrapContraloria().scrap("2015-01-01", "2015-12-31", on_progress=avisos.append)
    assert docs == []
    assert len(_llamadas("getFileInfo")) == 2
    assert any("no respondió" in a for a in avisos)


@responses.activate
def test_id_repetido_reintento_que_sale_bien():
    _mock_listados(cir=[_cir(7, "Circular 0011-2015.docx", "2015-07-15T05:00:00Z")], jur=[_jur(7)])
    responses.add(responses.POST, f"{_API}/getFileInfo", body="Ohhh, something went wrong...",
                  content_type="text/plain")
    responses.add(responses.POST, f"{_API}/getFileInfo",
                  json=_file_info(7, "Circulares", "Circular 0011-2015.docx"))
    docs = ScrapContraloria().scrap("2015-01-01", "2015-12-31")
    assert [d.title for d in docs] == ["C_CGR_0011_2015"]


@responses.activate
def test_id_unico_no_se_verifica():
    _mock_listados(res=[_res(1928, "OGZ-0897-2026.pdf", "2026-11-04T08:00:00Z")])
    docs = ScrapContraloria().scrap("2026-01-01", "2026-12-31")
    assert len(docs) == 1
    assert _llamadas("getFileInfo") == []


@responses.activate
def test_id_repetido_fuera_de_la_ventana_no_se_verifica():
    _mock_listados(
        res=[_res(65, "OGZ-0350-2015.pdf", "2015-05-01T05:00:00Z")],
        cir=[_cir(65, "Circular 0009-2022.pdf", "2022-11-16T05:00:00Z")],
    )
    docs = ScrapContraloria().scrap("2026-01-01", "2026-12-31")
    assert docs == []
    assert _llamadas("getFileInfo") == []


@responses.activate
def test_si_falta_un_listado_se_verifican_todos_los_de_la_ventana():
    responses.add(responses.POST, f"{_API}/getResoluciones",
                  json=[_res(1928, "OGZ-0897-2026.pdf", "2026-11-04T08:00:00Z")])
    responses.add(responses.POST, f"{_API}/getConceptosJuridicos", json=[])
    responses.add(responses.POST, f"{_API}/getCirculares", status=500)
    responses.add(responses.POST, f"{_API}/getJurisprudencia", json=[])
    responses.add(responses.POST, f"{_API}/getFileInfo",
                  json=_file_info(1928, "Resoluciones", "OGZ-0897-2026.pdf"))
    avisos = []
    docs = ScrapContraloria().scrap("2026-01-01", "2026-12-31", on_progress=avisos.append)
    assert [d.title for d in docs] == ["R_CGR_OGZ-0897_2026"]
    assert len(_llamadas("getFileInfo")) == 1
    assert any("Circulares" in a and "no se pudo leer" in a for a in avisos)


# --- Caso 7: dedup por número ------------------------------------------------

@responses.activate
def test_dedup_por_numero_normalizado_se_queda_la_primera():
    _mock_listados(cto=[
        _cto(4001, "CGR-OJ-0219-2020.pdf", "2020-09-01T05:00:00Z"),
        _cto(4002, "CGR-OJ-219-2020.pdf", "2020-09-01T05:00:00Z"),
        _cto(4003, "CGR-OJ-177-2022.docx.pdf", "2022-05-01T05:00:00Z"),
        _cto(4004, "CGR-OJ-177-2022.pdf", "2022-05-01T05:00:00Z"),
    ])
    avisos = []
    docs = ScrapContraloria().scrap("2015-01-01", "2026-12-31", on_progress=avisos.append)
    assert [d.title for d in docs] == ["CTO_CGR_0219_2020", "CTO_CGR_177_2022"]
    assert sum("repite el número" in a for a in avisos) == 2


@responses.activate
def test_resolucion_y_circular_con_mismo_numero_no_se_confunden():
    _mock_listados(
        res=[_res(10, "OGZ-0004-2015.pdf", "2015-02-25T05:00:00Z")],
        cir=[_cir(5, "Circular 0004-2015.docx", "2015-02-25T05:00:00Z")],
    )
    docs = ScrapContraloria().scrap("2015-01-01", "2015-12-31")
    assert sorted(d.title for d in docs) == ["C_CGR_0004_2015", "R_CGR_OGZ-0004_2015"]


# --- Caso 8: filtro por fecha y piso; armado del documento -------------------

@responses.activate
def test_scrap_completo_filtra_y_arma_documentos():
    _mock_listados(
        res=[
            _res(1928, "OGZ-0897-2026.pdf", "2026-11-04T08:00:00Z",
                 titulo="Por la cual se adopta la versión 7.0 del Manual Específico de Funciones"),
            _res(1500, "OGZ-0700-2024.pdf", "2024-03-01T05:00:00Z"),
            _res(99, "REG-ORG 5145 2000.pdf", None),
            _res(801, "OGZ-00801-2022.PDF", None),
            _res(20, "OGZ-0001-2014.pdf", "2014-12-30T05:00:00Z"),
            _res(1401, "REG-EJE-0103-2021.pdf", "2022-01-17T05:00:00Z", clasif="Resolución Reglamentaria Ejecutiva"),
        ],
        cto=[_cto(5985, "CGR-OJ-131-2026.pdf", "2026-11-25T08:00:00Z")],
        cir=[_cir(83, "2026", None), _cir(82, "Circular 023-2025.pdf", "2025-12-04T08:00:00Z")],
    )
    avisos = []
    docs = ScrapContraloria().scrap("2022-01-01", "2026-12-31", on_progress=avisos.append)
    titulos = [d.title for d in docs]
    assert titulos == [
        "R_CGR_OGZ-0897_2026", "R_CGR_OGZ-0700_2024", "R_CGR_REG-EJE-0103_2021",
        "CTO_CGR_131_2026", "C_CGR_023_2025",
    ]
    d = docs[0]
    assert d.source == _SOURCE
    assert d.tipo == "Resolución"
    assert d.f_public == d.f_providencia == "2026-11-04"
    assert d.detalle == "Resolución Organizacional — Por la cual se adopta la versión 7.0 del Manual Específico de Funciones"
    assert d.save_path == f"{_SOURCE}/2026-11-04/Resolución/R_CGR_OGZ-0897_2026(extension)"
    assert d.link["body"]["path"] == "cgr/resoluciones/OGZ-897-2026"
    assert d.title_unverified is False
    assert docs[3].tipo == "Concepto" and docs[3].detalle == "ADQUISICIÓN DE VEHÍCULOS ELÉCTRICOS"
    assert docs[4].tipo == "Circular"
    # Avisos: fila sin fecha de 2022 (no la de 2000), circular sin archivo, año distinto.
    assert any("sin fecha" in a and "OGZ-00801-2022" in a for a in avisos)
    assert not any("5145" in a for a in avisos)
    assert any("«2026»" in a for a in avisos)
    assert any("R_CGR_REG-EJE-0103_2021" in a and "no coincide" in a for a in avisos)


@responses.activate
def test_piso_2015_aunque_el_rango_empiece_antes():
    _mock_listados(res=[
        _res(20, "OGZ-0001-2014.pdf", "2014-12-30T05:00:00Z"),
        _res(21, "OGZ-0001-2015.pdf", "2015-01-02T05:00:00Z"),
    ])
    docs = ScrapContraloria().scrap("2000-01-01", "2026-12-31")
    assert [d.title for d in docs] == ["R_CGR_OGZ-0001_2015"]


@responses.activate
def test_circular_sin_numero_sale_sin_verificar_con_aviso():
    _mock_listados(cir=[_cir(34, "Circular - Auditorías.pdf", "2020-03-18T05:00:00Z", numero="CIRCULAR- AUDITORIAS")])
    avisos = []
    docs = ScrapContraloria().scrap("2020-01-01", "2020-12-31", on_progress=avisos.append)
    assert docs[0].title_unverified is True
    assert docs[0].title == "Circular - Auditorías"
    assert any("no se reconoce el número" in a for a in avisos)


# --- Caso 9: cancelación, límite y sección que falla -------------------------

@responses.activate
def test_stop_event_devuelve_lo_que_lleva():
    _mock_listados(res=[_res(1, "OGZ-0001-2026.pdf", "2026-01-02T05:00:00Z")])
    ev = threading.Event()
    ev.set()
    assert ScrapContraloria().scrap("2026-01-01", "2026-12-31", stop_event=ev) == []


@responses.activate
def test_limit():
    _mock_listados(res=[_res(i, f"OGZ-{i:04}-2026.pdf", "2026-01-02T05:00:00Z") for i in range(1, 6)])
    docs = ScrapContraloria().scrap("2026-01-01", "2026-12-31", limit=2)
    assert len(docs) == 2


@responses.activate
def test_seccion_que_falla_avisa_y_sigue():
    responses.add(responses.POST, f"{_API}/getResoluciones",
                  body=requests.exceptions.ConnectionError("caído"))
    responses.add(responses.POST, f"{_API}/getConceptosJuridicos",
                  json=[_cto(5985, "CGR-OJ-131-2026.pdf", "2026-11-25T08:00:00Z")])
    responses.add(responses.POST, f"{_API}/getCirculares", json=[])
    responses.add(responses.POST, f"{_API}/getJurisprudencia", json=[])
    responses.add(responses.POST, f"{_API}/getFileInfo",
                  json=_file_info(5985, "Conceptos Juridicos", "CGR-OJ-131-2026.pdf"))
    avisos = []
    docs = ScrapContraloria().scrap("2026-01-01", "2026-12-31", on_progress=avisos.append)
    assert [d.title for d in docs] == ["CTO_CGR_131_2026"]
    assert any("Resoluciones" in a and "no se pudo leer" in a for a in avisos)


@responses.activate
def test_listado_manda_el_cuerpo_del_formulario_vacio():
    _mock_listados()
    ScrapContraloria().scrap("2026-01-01", "2026-12-31")
    cuerpo = json.loads(_llamadas("getResoluciones")[0].request.body)
    assert cuerpo["keyword"] == "" and cuerpo["advQuery"] == []
    assert cuerpo["OrdenarPor"]["Label"] == "FechaDecision"
