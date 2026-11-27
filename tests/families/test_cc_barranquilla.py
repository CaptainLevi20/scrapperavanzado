import datetime
import threading
import unicodedata
from urllib.parse import quote

import responses

from core.scrapers.families import cc_barranquilla as m
from core.scrapers.registry import FAMILY_REGISTRY

# Fragmentos reales (recortados a los campos que se usan) de la API REST de
# SharePoint del OneDrive compartido de la Cámara, tomados el 2026-11-26.
_SITIO = "https://camarabquilla-my.sharepoint.com/personal/naltamar_camarabaq_org_co"
_RAIZ = "/personal/naltamar_camarabaq_org_co/Documents/LAUDOS CENTRO DE CONCILIACIÓN Y ARBITRAJE CCB"
_ENLACE = (
    "https://camarabquilla-my.sharepoint.com/:f:/g/personal/naltamar_camarabaq_org_co/"
    "EtYmeJ4NR1dHv54S0g4JT54BsqsrOfoDFjcYOdtNF_sHMA?e=goH5U0"
)
_ONEDRIVE = (
    f"{_SITIO}/_layouts/15/onedrive.aspx?id=%2Fpersonal%2Fnaltamar_camarabaq_org_co%2FDocuments"
    "%2FLAUDOS%20CENTRO%20DE%20CONCILIACI%C3%93N%20Y%20ARBITRAJE%20CCB&ga=1"
)

_PAGINA = f"""<html><body>
<div class="card"><a href="https://camarabaq.org.co/tarifas" class="m-0"><h3>Tarifas</h3></a></div>
<div class="card-body d-flex align-items-center">
  <a href="{_ENLACE}" class="m-0"  >
    <h3 class="fs-6">Laudos Arbitrales</h3>
  </a>
</div></body></html>"""


def _archivo(carpeta, nombre, creado, uid):
    return {
        "Length": "266858",
        "Name": nombre,
        "ServerRelativeUrl": f"{_RAIZ}/{carpeta}/{nombre}",
        "TimeCreated": creado,
        "TimeLastModified": creado,
        "UniqueId": uid,
    }


def _carpeta(nombre):
    return {"Name": nombre, "ServerRelativeUrl": f"{_RAIZ}/{nombre}", "ItemCount": 1}


_ANIOS = {
    "2026": [
        _archivo("2026", "31082026 LAUDO ARBITRAL INVERSIONES DOS OCEANOS SAS Vs ALIMENTOS PIPO.pdf",
                 "2026-09-18T03:46:14Z", "2ed4869c-0028-4846-8f34-82d96027fe21"),
        _archivo("2026", "18062026 Laudo Arbitral de LUIS PEREZ GAVIRIA contra FUNBISFRON.pdf",
                 "2026-06-26T21:30:52Z", "252b82d0-b061-421c-a17b-658f562d153e"),
    ],
    "2025": [
        _archivo("2025", "LAUDO ARBITRAL INVERSIONES AVANADE VS ALPECOL Y OTRO..pdf",
                 "2025-05-20T22:57:31Z", "d4d72538-4be0-494d-91c4-75df25d5b020"),
    ],
    "2018": [
        _archivo("2018", "2019-08-08 LAUDO ARBITRAL FABIAN PICON OLIVER contra EMANUEL JESUS PICON CARRILLO y OTRO.pdf",
                 "2022-10-19T15:05:06Z", "add9fa46-9780-4246-a872-0a9e8e30f25a"),
        _archivo("2018", "2018-09-2018 LAUDO ARBITRAL JOSE GABRIEL MARQUEZ SANTOS VS PUMA ENERGY COLOMBIA COMBUSTIBLE S.A.S.pdf",
                 "2022-10-19T15:02:04Z", "489abe16-86c5-4646-92ea-33dcdc621004"),
    ],
    "2014": [
        _archivo("2014", "2014-08-06 LAUDO PROTECCIÓN GASODUCTO Vs PROMIGAS SA ESP.pdf",
                 "2026-05-06T21:44:52Z", "caea0682-ff75-4e94-a99c-1473e60bb107"),
    ],
}


def _url_carpeta(ruta):
    return f"{_SITIO}/_api/web/GetFolderByServerRelativePath(decodedurl='{quote(ruta, safe='/')}')"


def _simular_sitio(anios=None, falla=()):
    anios = _ANIOS if anios is None else anios
    responses.add(responses.GET, m._PAGINA_CENTRO, body=_PAGINA, status=200)
    responses.add(responses.GET, _ENLACE, status=302, headers={"Location": _ONEDRIVE})
    responses.add(responses.GET, _ONEDRIVE, status=200, body="<html>onedrive</html>",
                  headers={"Set-Cookie": "FedAuth=galleta; path=/"})
    raiz = {"Name": "LAUDOS CENTRO DE CONCILIACIÓN Y ARBITRAJE CCB", "ServerRelativeUrl": _RAIZ,
            "Files": [], "Folders": [_carpeta("Forms")] + [_carpeta(a) for a in anios]}
    responses.add(responses.GET, _url_carpeta(_RAIZ), json=raiz, status=200)
    for anio, archivos in anios.items():
        if anio in falla:
            responses.add(responses.GET, _url_carpeta(f"{_RAIZ}/{anio}"), status=500)
        else:
            responses.add(responses.GET, _url_carpeta(f"{_RAIZ}/{anio}"),
                          json={"Name": anio, "Files": archivos, "Folders": []}, status=200)


# --- 1. Fecha del nombre ----------------------------------------------------

def test_fecha_formatos_del_sitio():
    f = m._fecha_del_nombre
    assert f("2020-09- 11 LAUDO ALIMENTOS") == (datetime.date(2020, 9, 11), False)
    assert f("2022-01- 20 LAUDO ARBITRAL GRUPO") == (datetime.date(2022, 1, 20), False)
    assert f("2018-02-6 Laudo Urbanismo") == (datetime.date(2018, 2, 6), False)
    assert f("18062026 Laudo Arbitral de LUIS") == (datetime.date(2026, 6, 18), False)
    assert f("20240515 LAUDO ARBITRAL ETANOLES") == (datetime.date(2024, 5, 15), False)
    assert f("24-08-2023 Laudo Arbitral Edilberto") == (datetime.date(2023, 8, 24), False)
    assert f("29082024 - Laudo Arbitral SF Convias") == (datetime.date(2024, 8, 29), False)


def test_fecha_mes_mayor_que_12_se_invierte():
    assert m._fecha_del_nombre("2015-26-06 LAUDO ARBITRAL LUZ") == (datetime.date(2015, 6, 26), False)


def test_fecha_ilegible_toma_anio_y_mes_y_queda_supuesta():
    assert m._fecha_del_nombre("2018-09-2018 LAUDO ARBITRAL JOSE") == (datetime.date(2018, 9, 1), True)


def test_fecha_ausente_o_imposible():
    assert m._fecha_del_nombre("LAUDO ARBITRAL CONSORCIO DESARROLLO ESCOLAR") == (None, False)
    # 8 cifras que no son fecha en ninguna de las dos lecturas
    assert m._fecha_del_nombre("99999999 LAUDO") == (None, False)


def test_regla_de_las_8_cifras():
    assert m._fecha_ocho_cifras("20240515") == datetime.date(2024, 5, 15)
    assert m._fecha_ocho_cifras("18062026") == datetime.date(2026, 6, 18)
    assert m._fecha_ocho_cifras("31082026") == datetime.date(2026, 8, 31)
    assert m._fecha_ocho_cifras("13131313") is None


# --- 2. Unicode descompuesto -------------------------------------------------

def test_nombre_en_nfd_da_lo_mismo_que_en_nfc():
    nfc = "29082024 - Laudo Arbitral SF Convias SAS vs Alcaldía de Barranquilla VF.pdf"
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfd != nfc
    assert m._partes(nfd) == m._partes(nfc) == "SF Convias SAS vs Alcaldía de Barranquilla VF"
    assert m._fecha_del_nombre(m._nfc(nfd)) == m._fecha_del_nombre(nfc)


def test_partes_quitan_fecha_y_laudo_arbitral():
    assert m._partes("31082026 LAUDO ARBITRAL INVERSIONES DOS OCEANOS SAS Vs ALIMENTOS PIPO.pdf") == \
        "INVERSIONES DOS OCEANOS SAS Vs ALIMENTOS PIPO"
    assert m._partes("2022-06-02 LUDO ARBITRAL H3 ARQUITECTURA S.A.S. Vs AVORA S.A.S.pdf") == \
        "H3 ARQUITECTURA S.A.S. Vs AVORA S.A.S"
    assert m._partes("2023-02-06 LAUDO ARBITRAL - Indupark vs Zurich.pdf") == "Indupark vs Zurich"
    assert m._partes("LAUDO ARBITRAL INVERSIONES AVANADE VS ALPECOL Y OTRO..pdf") == \
        "INVERSIONES AVANADE VS ALPECOL Y OTRO"
    assert m._partes(
        "2023-01-02 Audiencia de Laudo y Laudo Arbitral PH HOLDING contra CONJUNTO.pdf"
    ) == "PH HOLDING contra CONJUNTO"


# --- 3. Títulos ---------------------------------------------------------------

def _entrada(carpeta, nombre, creado, uid):
    return m._Entrada(carpeta=carpeta, archivo=_archivo(carpeta, nombre, creado, uid))


def test_titulos_con_fecha_y_misma_fecha_dos_veces_por_orden_de_subida():
    entradas = [
        # el subido después llega primero en el listado
        _entrada("2026", "31082026 LAUDO ARBITRAL B Vs C.pdf", "2026-10-01T00:00:00Z", "bbbb"),
        _entrada("2026", "2026-08-31 LAUDO ARBITRAL A Vs D.pdf", "2026-09-18T00:00:00Z", "aaaa"),
        _entrada("2018", "2018-09-2018 LAUDO ARBITRAL JOSE.pdf", "2022-10-19T15:02:04Z", "cccc"),
    ]
    titulos = {e.archivo["UniqueId"]: (e.titulo, e.unverified) for e in m._titular(entradas, lambda *_: None)}
    assert titulos["aaaa"] == ("LA_CCBAR_20260831_2026", False)
    assert titulos["bbbb"] == ("LA_CCBAR_20260831_2026_2", False)
    assert titulos["cccc"] == ("LA_CCBAR_20180901_2018", True)


def test_titulos_sin_fecha_numerados_por_orden_de_subida_en_la_carpeta():
    entradas = [
        _entrada("2021", "LAUDO ARBITRAL NUEVO.pdf", "2024-01-01T00:00:00Z", "zzzz"),
        _entrada("2021", "LAUDO ARBITRAL CONSORCIO DESARROLLO ESCOLAR.pdf", "2022-10-19T16:13:18Z", "yyyy"),
    ]
    avisos = []
    res = {e.archivo["UniqueId"]: e for e in m._titular(entradas, avisos.append)}
    assert (res["yyyy"].titulo, res["yyyy"].fecha, res["yyyy"].unverified) == \
        ("LA_CCBAR_SF1_2021", datetime.date(2021, 1, 1), True)
    assert res["zzzz"].titulo == "LA_CCBAR_SF2_2021"


# --- 4. Enlace de la página del Centro --------------------------------------

def test_enlace_tomado_de_la_tarjeta_laudos_arbitrales():
    assert m._enlace_de_pagina(_PAGINA) == _ENLACE


def test_sin_tarjeta_no_hay_enlace():
    assert m._enlace_de_pagina("<html><a href='https://x.sharepoint.com/:f:/g/otro'>Tarifas</a></html>") is None


@responses.activate
def test_scrap_usa_el_enlace_conocido_si_la_pagina_no_lo_tiene():
    _simular_sitio()
    responses.replace(responses.GET, m._PAGINA_CENTRO, body="<html>rediseño</html>", status=200)
    avisos = []
    docs = m.ScrapCcBarranquilla().scrap("2014-01-01", "2026-12-31", on_progress=avisos.append)
    assert len(docs) == 6
    assert any("enlace conocido" in a for a in avisos)


# --- 5-7. scrap() completo ----------------------------------------------------

@responses.activate
def test_scrap_recorre_carpetas_y_arma_documentos():
    _simular_sitio()
    avisos = []
    docs = m.ScrapCcBarranquilla().scrap("1900-01-01", "2026-12-31", on_progress=avisos.append)
    por_titulo = {d.title: d for d in docs}
    assert set(por_titulo) == {
        "LA_CCBAR_20260831_2026", "LA_CCBAR_20260618_2026", "LA_CCBAR_SF1_2025",
        "LA_CCBAR_20190808_2019", "LA_CCBAR_20180901_2018", "LA_CCBAR_20140806_2014",
    }
    d = por_titulo["LA_CCBAR_20260831_2026"]
    assert d.link == {
        "url": f"{_SITIO}/_layouts/15/download.aspx?UniqueId=2ed4869c-0028-4846-8f34-82d96027fe21",
        "method": "sharepoint_compartido",
        "compartido": _ENLACE,
    }
    assert d.tipo == "Laudo arbitral"
    assert d.f_public == d.f_providencia == "2026-08-31"
    assert d.detalle == "INVERSIONES DOS OCEANOS SAS Vs ALIMENTOS PIPO"
    assert d.save_path.endswith("LA_CCBAR_20260831_2026(extension)")
    assert d.title_unverified is False
    sf = por_titulo["LA_CCBAR_SF1_2025"]
    assert sf.f_public == "2025-01-01" and sf.title_unverified is True
    assert por_titulo["LA_CCBAR_20180901_2018"].title_unverified is True
    assert any("sin fecha" in a for a in avisos)
    assert any("ilegible" in a for a in avisos)
    assert any("carpeta 2018" in a for a in avisos)  # PICON: fecha 2019 en carpeta 2018
    # Forms no se abre
    assert not any("Forms" in c.request.url for c in responses.calls)


@responses.activate
def test_scrap_filtra_por_fecha_sin_piso():
    _simular_sitio()
    docs = m.ScrapCcBarranquilla().scrap("2014-01-01", "2014-12-31")
    assert [d.title for d in docs] == ["LA_CCBAR_20140806_2014"]


def test_atributos_de_la_familia():
    cls = FAMILY_REGISTRY["cc_barranquilla"]
    assert cls is m.ScrapCcBarranquilla
    assert cls.scheduled_min_lookback_days == 20_000
    assert cls.checks_for_republication is False


@responses.activate
def test_scrap_carpeta_que_falla_avisa_y_sigue():
    _simular_sitio(falla=("2026",))
    avisos = []
    docs = m.ScrapCcBarranquilla().scrap("1900-01-01", "2026-12-31", on_progress=avisos.append)
    assert len(docs) == 4
    assert any("2026" in a and "Error" in a for a in avisos)


@responses.activate
def test_scrap_respeta_limit_y_stop_event():
    _simular_sitio()
    assert len(m.ScrapCcBarranquilla().scrap("1900-01-01", "2026-12-31", limit=2)) == 2

    parar = threading.Event()
    parar.set()
    assert m.ScrapCcBarranquilla().scrap("1900-01-01", "2026-12-31", stop_event=parar) == []


@responses.activate
def test_scrap_listado_vacio():
    _simular_sitio(anios={})
    assert m.ScrapCcBarranquilla().scrap("1900-01-01", "2026-12-31") == []


@responses.activate
def test_scrap_enlace_caido_es_error_de_la_corrida():
    responses.add(responses.GET, m._PAGINA_CENTRO, body=_PAGINA, status=200)
    responses.add(responses.GET, _ENLACE, status=404)
    avisos = []
    assert m.ScrapCcBarranquilla().scrap("1900-01-01", "2026-12-31", on_progress=avisos.append) == []
    assert any("Error" in a for a in avisos)
