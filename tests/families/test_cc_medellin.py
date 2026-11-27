import datetime
import threading

import responses

from core.scrapers.families.cc_medellin import (
    _SOURCE,
    _URL,
    _fecha_encabezado,
    _fecha_nombre,
    _radicado,
    _titulo,
    _url_limpia,
    ScrapCcMedellin,
)
from core.scrapers.registry import FAMILY_REGISTRY

_DOCS = "/Portals/0/Documentos/Laudos/"
_ABS = "https://www.camaramedellin.com.co"


# --- Fragmentos reales de la página (2026-11-26) -----------------------------

def _strong(encabezado, href, texto):
    """Maqueta de 2024-2026: <p><strong>encabezado</strong><br/><a>."""
    return (
        f'<p style="text-align:justify"><strong>{encabezado}</strong><br />\n'
        f'<a href="{href}" target="_blank">{texto}</a></p>\n\n'
    )


def _li(encabezado, href, texto):
    """Maqueta de años anteriores: <ul><li>encabezado</li></ul><p><a>."""
    return f"<ul>\n <li>{encabezado}</li>\n</ul>\n\n<p><a href=\"{href}\">{texto}</a></p>\n\n"


def _panel(anio, *filas):
    return (
        '<div class="acordeon__item">\n<div>\n</div>\n'
        f'<div class="acordeon_title">\n<h2>Laudos {anio}</h2>\n</div>\n'
        '<div class="acordeon_content">\n' + "".join(filas) + "</div>\n</div>\n"
    )


def _pagina(*paneles):
    return ("<html><body><div class=\"DnnModule\">" + "".join(paneles) + "</div></body></html>").encode("utf-8")


P2026 = _panel(
    2026,
    _strong("Radicado: 2025 A 0032. Laudo proferido el 13 de marzo de 2026.",
            "https://www.camaramedellin.com.co/Portals/0/Documentos/Laudos/2026/2025 A 0032 13-03-2026.pdf"
            "?ver=h34xuLdGhk-_eC8SJCWYZg%3d%3d",
            "Partes: JORGE IVÁN PENAGOS GARCÉS contra LA FUNDACIÓN CLÍNICA DEL NORTE."),
)
P2025 = _panel(
    2025,
    _strong("Radicado: 2022 A 0048. Laudo proferido el 24 de enero de 2025.",
            _DOCS + "2025/2022 A 0048 22-01-2025.pdf",
            "Partes: LUZ INDELY MEJÍA BERRÍO contra HOSPITAL"),
)
P2024 = _panel(
    2024,
    '<p style="text-align:justify"><strong>Radicado: 2023 A 0004. Laudo proferido el 02 de mayo de 2024.</strong></p>\n\n'
    '<p style="text-align:justify"><a href="/Portals/0/Documentos/Arbitraje/2025/2023 A 0004 02-05-2024.pdf'
    '?ver=aaf_vraBNMj17WqIC4M1jQ%3d%3d">CARLOS ALBERTO BORJA contra ARLEY JOSÉ DIAZ</a></p>\n\n'
    '<p style="text-align:justify"><strong>Radicado: 2023 A 0004. Laudo proferido el 31 de mayo de 2024.</strong></p>\n\n'
    '<p style="text-align:justify"><a href="/Portals/0/Documentos/Arbitraje/2025/2023 A 0037 31-05-2024.pdf">'
    "Partes: OTRA PARTE contra OTRA</a></p>\n",
)
P2023 = _panel(
    2023,
    '<ul>\n <li style="text-align:justify"><strong>Radicado: 2022 AP 0001. Laudo proferido el 06 de marzo de 2023.'
    '</strong></li>\n</ul>\n<p style="text-align:justify"><a href="/Portals/0/Documentos/Laudos/2023/2022 a 0001 '
    '06-03-2023.pdf">Partes: LPA DE COLOMBIA S.A.S. y ACREEDORES.</a></p>\n'
    "<ul>\n <li><strong>Radicado: 2022 A 0001. Laudo proferido el 06 de marzo de 2023.</strong></li>\n</ul>\n"
    '<p><a href="/Portals/0/Documentos/Laudos/2023/2022 a 0001 06-03-2023.pdf">Partes: LUIS FERNANDO ECHEVERRI '
    "LÓPEZ contra JONATHAN TANGARIFE RESTREPO</a></p>\n"
    '<ul>\n <li style="text-align:justify"><strong>Radicado: 2022 AP 0002. Laudo proferido el 12 de abril de 2023.'
    '</strong></li>\n</ul>\n<p style="text-align:justify"><a href="/Portals/0/Documentos/Laudos/2023/2022 AP 0002 '
    '12-04-2023.pdf">Partes: INVERSIONES MARATÓN S.A.S. y ACREEDORES.</a></p>\n',
)
P2022 = _panel(
    2022,
    "<ul>\n <li><strong>Radicado: 2020 A 0025. Laudo proferido el 04 de febrero de 2022.</strong></li>\n</ul>\n"
    '<p><a href="/Portals/0/Documentos/Laudos/2022/2020 A 0025 04-02-2022.pdf">Partes: JUAN CARLOS OSORIO '
    "ARBELÁEZ contra BTG PACTUAL SOCIEDAD FIDUCIARIA S.A.</a></p>\n"
    "<ul>\n <li><strong>Radicado: 2020 A 0007. Laudo proferido el 28 de febrero de 2022.</strong></li>\n</ul>\n"
    '<p><a href="/Portals/0/Documentos/Laudos/2022/2020 A 0025 04-02-2022.pdf">Partes: MGM SUSTAINABLE ENERGY '
    "S.A.S. contra MAPFRE SEGUROS GENERALES DE COLOMBIA S.A.</a></p>\n"
    '<ul>\n <li style="text-align: justify;"><strong><a name="_Hlk135051592">Radicado: 2020 A 0011. Laudo '
    "proferido el 14 de junio de 2022.</a></strong></li>\n</ul>\n"
    '<p style="text-align:justify"><a href="/Portals/0/Documentos/Laudos/2022/2020 A 0011 14-06-2022.pdf">'
    "Partes: ARQUITECTOS E INGENIEROS ASOCIADOS S.A. contra VÉRTICE INGENIERÍA S.A.S.</a></p>\n",
)
P2021 = _panel(
    2021,
    "<ul>\n<li>Radicado:<strong> </strong>2018 A 0015. Laudo proferido el 3 de marzo de 2021</li>\n</ul>\n"
    '<p><a href="/Portals/0/Documentos/Laudos/2021/2018 A 0015 03-03-2021.pdf">Partes:FIDEICOMISO '
    "MACROPROYECTO PAJARITO contra INSERCO S.A.</a></p>\n",
)
P2020 = _panel(
    2020,
    _li("Radicado: 2019 A 0087. Laudo proferido el 12 de agosto de 2010.",
        _DOCS + "2020/2019 A 0087 LAUDO ARBITRAL 12 AGO.pdf",
        "Partes: FEDERACIÓN GREMIAL DE TRABAJADORES DE LA SALUD contra EMPRESA SOCIAL DEL ESTADO HOSPITAL SAN "
        "RAFAEL DEL MUNICIPIO DE ITAGÜÍ."),
)
P2019 = _panel(
    2019,
    _li("Radicado: 2018 A 0018. Laudo emitido el 24 de abril de 2019.",
        _DOCS + "2019/Rad_ 2018 A 0018- LAUDO- 24-04-2019f5d8.pdf?ver=X9RPN8zRRZAyEaJX0AZy6A%3d%3d",
        "Partes: FÁBRICA DE BRASIERES HABY S.A contra COOPERATIVA ESPECIALIZADA DE AHORRO Y CRÉDITO COOPANTEX"),
)
P2018 = _panel(
    2018,
    _li("Radicado: 2017 A 0013. Laudo emitido el 25 de enero de 2018.",
        _DOCS + "2018/2017-a-0013-25-ene-18.pdf",
        "Partes: JUAN DAVID CASTAÑO TOBÓN contra VICENTE MIRO ARISTIZÁBAL SERNA"),
)
P2017 = _panel(
    2017,
    _li("Radicado: 2016 A 004. Laudo proferido el 16 de febrero de 2017.",
        _DOCS + "2017/2016 A 004 LAUDO ARBITRAL - Feb-11.pdf?ver=_kMT26XX4ac62SCRemSSgg%3d%3d",
        "Partes: CEDRO ROJO PISOS EN MADERA S.A.S contra CONINSA R.H"),
    _li("Radicado: 2016 A 012. Laudo emitido el 24 de febrero de 2017",
        _DOCS + "2017/2016 A 004-24-02-2017.pdf?ver=sgDTmPjSEWBtVmYSE2aAFw%3d%3d",
        "Partes: MISIÓN EMPRESARIAL SERVICIOS TEMPORALES S.A CONTRA LA EMPRESA PARA LA SEGURIDAD URBANA DE "
        "MEDELLÍN ESU."),
)
P2015 = _panel(
    2015,
    _li("Radicado: 2013 A 034. Laudo emitido el 29 de enero de 2015",
        _DOCS + "2015/29-de-enero-de-2015-2013-A-034.pdf?ver=Sbq39kL1fNOE7AVEK00__A%3d%3d",
        "Partes: LEASING BANCOLOMBIA S.A CONTRA CENTRO COMERCIAL SAN DIEGO P.H"),
)
P2014 = _panel(
    2014,
    _li("2013 A 005. Laudo emitido el 26 de marzo de 2014",
        _DOCS + "2014/26-de-marzo-de-2014-2013-A-005.pdf?ver=9CArtJa92AVGuprnPt-SaA%3d%3d",
        "Partes: MÓNICA ELIANA OCHOA BETANCUR Y JOSÉ MIGUEL LÓPEZ OCHOA CONTRA LA PALITA S.A.S"),
    _li("Radicado: 2013 A 007. Laudo emitido el 05 de agosto de 2014",
        _DOCS + "2014/5-de-agosto-de-2014-2013-A-031.pdf?ver=D-NrgXimK0HkUol2jc_UuA%3d%3d",
        "Partes: MARIA JOSEFA CALDERÓN DE CADAVID Y OTROS CONTRA LEIDY JOHANA ZULUAGA ARBELÁEZ"),
    _li("Radicado 6 de agosto de 2014- 2013 A 031",
        _DOCS + "2014/06_de_agosto_de_2014-_2013_A_007.pdf?ver=WmWfWcP4cOYZFshM-NPIhw%3d%3d",
        "Radicado 6 de agosto de 2014- 2013 A 031"),
)
P2010 = _panel(
    2010,
    _li("Radicado 2009 A 059. Laudo emitido el 21 de mayo de 2010",
        _DOCS + "2010/21-de-mayo-de-2010-2009- 059-ilovepdf-compressed.pdf?ver=pzA_GTSdHeGIx9wBHEdT3g%3d%3d",
        "Partes: WILSON GILBERTO CHACÓN FORERO CONTRA CLÍNICA OFTAMOLÓGICA DE ANTIOQUIA S.A (CLOFAN S.A)"),
)
P2001 = _panel(
    2001,
    _li("Radicado1999 A 023. Laudo emitido el 15 de marzo de 2001",
        _DOCS + "2001-99/1999-A-023-15-de-marzo-de-2001.pdf?ver=vwVBG6UEhABPrk90EuK4-A%3d%3d",
        "Partes: NÚCLEO PROYECTOS Y CONSTRUCCIONES S.A CONTRA GENERAR S.A E.S.P"),
)
P1999 = _panel(
    1999,
    _li("Radicado 1998 A 016. Laudo emitido el 31 de mayo de 1999",
        _DOCS + "2001-99/1998-A-016-31-de-mayo-de-1999.pdf?ver=x%3d%3d",
        "Partes: MOTOCLUB DE COLOMBIA LTDA CONTRA FEDERACIÓN"),
)

TODOS = (P2026, P2025, P2024, P2023, P2022, P2021, P2020, P2019, P2018, P2017, P2015, P2014, P2010, P2001, P1999)


def _listado(*paneles, status=200):
    responses.add(responses.GET, _URL, body=_pagina(*paneles), status=status)


def _scrap(fini="1990-01-01", ffin="2026-12-31", **kw):
    return ScrapCcMedellin().scrap(fini, ffin, **kw)


def _por_titulo(docs):
    return {d.title: d for d in docs}


# --- Registro y atributos ------------------------------------------------------

def test_source_registro_y_ventana():
    assert _SOURCE == "Cámara de Comercio de Medellín para Antioquia"
    assert FAMILY_REGISTRY["cc_medellin"] is ScrapCcMedellin
    assert ScrapCcMedellin.scheduled_min_lookback_days == 20_000
    # La ventana tiene que llegar al laudo más viejo (31-05-1999).
    assert datetime.date.today() - datetime.timedelta(days=20_000) < datetime.date(1999, 5, 31)
    assert ScrapCcMedellin.checks_for_republication is True
    assert "alerta_margen_dias" not in ScrapCcMedellin.__dict__


# --- Caso 1: radicado del nombre y título --------------------------------------

def test_radicado_de_cada_forma_de_nombre():
    assert _radicado("2025 A 0032 13-03-2026.pdf") == (2025, "A", "0032")
    assert _radicado("2017-a-0013-25-ene-18.pdf") == (2017, "A", "0013")
    assert _radicado("Rad_ 2018 A 0018- LAUDO- 24-04-2019f5d8.pdf") == (2018, "A", "0018")
    assert _radicado("29-de-enero-de-2015-2013-A-034.pdf") == (2013, "A", "034")
    assert _radicado("2022 AP 0002 12-04-2023.pdf") == (2022, "AP", "0002")
    assert _radicado("2022 a 0001 06-03-2023.pdf") == (2022, "A", "0001")
    assert _radicado("06_de_agosto_de_2014-_2013_A_007.pdf") == (2013, "A", "007")
    assert _radicado("2019 A 0003 ACTA Y LAUDO 21 ENE 2020.pdf") == (2019, "A", "0003")
    # Sin la A no hay radicado.
    assert _radicado("21-de-mayo-de-2010-2009- 059-ilovepdf-compressed.pdf") is None
    # Encabezados viejos.
    assert _radicado("Radicado1999 A 023. Laudo emitido el 15 de marzo de 2001") == (1999, "A", "023")
    assert _radicado("Radicado 6 de agosto de 2014- 2013 A 031") == (2013, "A", "031")


def test_titulo_con_consecutivo_tal_cual():
    assert _titulo((2025, "A", "0032"), 2026) == "LA_CCMA_2025-A-0032_2026"
    assert _titulo((2022, "AP", "0002"), 2023) == "LA_CCMA_2022-AP-0002_2023"
    assert _titulo((2016, "A", "004"), 2017) == "LA_CCMA_2016-A-004_2017"
    assert _titulo((2013, "A", "034"), 2015) == "LA_CCMA_2013-A-034_2015"


# --- Caso 8: URL ---------------------------------------------------------------

def test_url_sin_ver_con_espacios_codificados_y_absoluta():
    assert _url_limpia("/Portals/0/Documentos/Laudos/2017/2016 A 004-24-02-2017.pdf?ver=sgDTmPjSEWBtVmYSE2aAFw%3d%3d") == (
        "https://www.camaramedellin.com.co/Portals/0/Documentos/Laudos/2017/2016%20A%20004-24-02-2017.pdf"
    )
    # Ya codificada o absoluta: la misma URL.
    assert _url_limpia(_ABS + "/Portals/0/Documentos/Laudos/2017/2016%20A%20004-24-02-2017.pdf") == (
        _url_limpia("/Portals/0/Documentos/Laudos/2017/2016 A 004-24-02-2017.pdf?ver=otro")
    )


# --- Caso 2: fechas ------------------------------------------------------------

def test_fecha_del_encabezado_y_del_nombre():
    assert _fecha_encabezado("Radicado: 2019 A 0046. Laudo proferido el 10 febrero de 2021.") == datetime.date(2021, 2, 10)
    assert _fecha_encabezado("Laudo emitido el 29 DE MARZO DE 2017") == datetime.date(2017, 3, 29)
    assert _fecha_encabezado("Radicado 6 de agosto de 2014- 2013 A 031") == datetime.date(2014, 8, 6)
    assert _fecha_nombre("2022 A 0048 22-01-2025.pdf") == datetime.date(2025, 1, 22)
    assert _fecha_nombre("29-de-enero-de-2015-2013-A-034.pdf") == datetime.date(2015, 1, 29)
    assert _fecha_nombre("31_de_julio_de_2014-2012_A_033.pdf") == datetime.date(2014, 7, 31)
    assert _fecha_nombre("2019 A 0087 LAUDO ARBITRAL 12 AGO.pdf") is None


@responses.activate
def test_fechas_del_scrap_con_avisos():
    _listado(*TODOS)
    avisos = []
    docs = _por_titulo(_scrap(on_progress=avisos.append))
    # Encabezado y nombre distintos: gana el encabezado, con aviso.
    assert docs["LA_CCMA_2022-A-0048_2025"].f_public == "2025-01-24"
    assert any("2022 A 0048" in a and "2025-01-24" in a and "2025-01-22" in a for a in avisos)
    # Año imposible (2010 < radicado 2019) y el nombre sin año: día y mes del
    # encabezado con el año del panel.
    d = docs["LA_CCMA_2019-A-0087_2020"]
    assert d.f_public == d.f_providencia == "2020-08-12"
    assert any("2019 A 0087" in a and "imposible" in a for a in avisos)


@responses.activate
def test_sin_fecha_usa_el_nombre_y_si_no_hay_se_omite():
    _listado(_panel(
        2016,
        _li("Radicado: 2015 A 018.", _DOCS + "2016/2015-A-018-29-de-abril-de-2016.pdf", "Partes: A contra B"),
        _li("Radicado: 2015 A 019.", _DOCS + "2016/2015-A-019.pdf", "Partes: C contra D"),
    ))
    avisos = []
    docs = _scrap(on_progress=avisos.append)
    assert [(d.title, d.f_public) for d in docs] == [("LA_CCMA_2015-A-018_2016", "2016-04-29")]
    assert any("2015 A 019" in a and "sin fecha" in a for a in avisos)


# --- Caso 3: lectura del acordeón ---------------------------------------------

@responses.activate
def test_emparejamiento_en_todas_las_maquetas():
    _listado(*TODOS)
    docs = _por_titulo(_scrap())
    d = docs["LA_CCMA_2025-A-0032_2026"]  # <p><strong>…</strong><br/><a>
    assert d.f_public == "2026-03-13"
    assert d.link == {
        "url": _ABS + "/Portals/0/Documentos/Laudos/2026/2025%20A%200032%2013-03-2026.pdf",
        "method": "GET",
    }
    assert d.detalle == "JORGE IVÁN PENAGOS GARCÉS contra LA FUNDACIÓN CLÍNICA DEL NORTE."
    assert d.tipo == "Laudo arbitral"
    assert d.save_path.endswith("LA_CCMA_2025-A-0032_2026(extension)")
    # <li><strong><a name=…>encabezado</a></strong></li>: el ancla sin href no es un enlace.
    assert docs["LA_CCMA_2020-A-0011_2022"].f_public == "2022-06-14"
    # <li>Radicado:<strong> </strong>2018 A 0015…</li>: el <strong> vacío no borra el encabezado.
    d = docs["LA_CCMA_2018-A-0015_2021"]
    assert d.f_public == "2021-03-03" and not d.title_unverified
    assert d.detalle.startswith("FIDEICOMISO MACROPROYECTO")
    # Encabezados viejos.
    assert docs["LA_CCMA_1999-A-023_2001"].f_public == "2001-03-15"
    assert docs["LA_CCMA_2013-A-005_2014"].f_public == "2014-03-26"
    assert docs["LA_CCMA_2013-A-034_2015"].f_public == "2015-01-29"
    assert docs["LA_CCMA_2018-A-0018_2019"].f_public == "2019-04-24"
    assert docs["LA_CCMA_2017-A-0013_2018"].f_public == "2018-01-25"
    # Validación de acuerdos de recuperación: mismo tipo.
    assert docs["LA_CCMA_2022-AP-0002_2023"].tipo == "Laudo arbitral"


# --- Casos 4-7: reglas de enlaces ---------------------------------------------

@responses.activate
def test_enlace_copiado_de_otro_laudo_se_omite_con_aviso():
    _listado(P2022, P2023)
    avisos = []
    docs = _scrap(on_progress=avisos.append)
    titulos = [d.title for d in docs]
    assert titulos.count("LA_CCMA_2020-A-0025_2022") == 1
    assert titulos.count("LA_CCMA_2022-A-0001_2023") == 1
    d = _por_titulo(docs)["LA_CCMA_2020-A-0025_2022"]
    assert d.f_public == "2022-02-04" and d.detalle.startswith("JUAN CARLOS OSORIO")
    assert not d.title_unverified
    # La fila que coincide (2022 A 0001) se queda aunque vaya después.
    assert _por_titulo(docs)["LA_CCMA_2022-A-0001_2023"].detalle.startswith("LUIS FERNANDO ECHEVERRI")
    assert any("2020 A 0007" in a and "2020 A 0025" in a for a in avisos)
    assert any("2022 AP 0001" in a and "2022 A 0001" in a for a in avisos)
    assert not any("MGM" in (d.detalle or "") for d in docs)


@responses.activate
def test_mismo_pdf_con_dos_nombres_queda_una_fila():
    _listado(P2017)
    avisos = []
    docs = _scrap(on_progress=avisos.append)
    assert [d.title for d in docs] == ["LA_CCMA_2016-A-004_2017"]
    assert docs[0].f_public == "2017-02-16"
    assert any("2016 A 012" in a and "2016 A 004" in a for a in avisos)


@responses.activate
def test_error_de_digitacion_titulo_del_archivo_sin_verificar():
    _listado(P2024)
    avisos = []
    docs = _por_titulo(_scrap(on_progress=avisos.append))
    assert set(docs) == {"LA_CCMA_2023-A-0004_2024", "LA_CCMA_2023-A-0037_2024"}
    assert not docs["LA_CCMA_2023-A-0004_2024"].title_unverified
    d = docs["LA_CCMA_2023-A-0037_2024"]
    assert d.title_unverified and d.f_public == "2024-05-31"
    assert any("2023 A 0004" in a and "2023 A 0037" in a for a in avisos)


@responses.activate
def test_enlaces_cruzados_se_quedan_los_dos_sin_verificar():
    _listado(P2014)
    avisos = []
    docs = _por_titulo(_scrap(on_progress=avisos.append))
    a, b = docs["LA_CCMA_2013-A-031_2014"], docs["LA_CCMA_2013-A-007_2014"]
    assert a.title_unverified and b.title_unverified
    assert a.link["url"].endswith("5-de-agosto-de-2014-2013-A-031.pdf")
    assert b.link["url"].endswith("06_de_agosto_de_2014-_2013_A_007.pdf")
    assert a.f_public == "2014-08-05" and b.f_public == "2014-08-06"
    # El texto del enlace repite el encabezado: sin detalle.
    assert b.detalle is None
    assert sum("2013 A 007" in x and "2013 A 031" in x for x in avisos) == 2


@responses.activate
def test_nombre_sin_radicado_usa_el_encabezado_sin_verificar():
    _listado(P2010)
    avisos = []
    docs = _scrap(on_progress=avisos.append)
    assert [d.title for d in docs] == ["LA_CCMA_2009-A-059_2010"]
    assert docs[0].title_unverified
    assert any("no trae radicado" in a for a in avisos)


@responses.activate
def test_dos_pdf_distintos_con_el_mismo_radicado_queda_el_primero():
    _listado(_panel(
        2016,
        _li("Radicado: 2015 A 025. Laudo emitido el 20 de agosto de 2016",
            _DOCS + "2016/2015-A-025-20-de-agosto-de-2016.pdf", "Partes: A contra B"),
        _li("Radicado: 2015 A 025. Laudo emitido el 26 de agosto de 2016",
            _DOCS + "2016/2015-A-025-aclaracion-26-de-agosto-2016.pdf", "Partes: A contra B"),
    ))
    avisos = []
    docs = _scrap(on_progress=avisos.append)
    assert len(docs) == 1 and docs[0].f_public == "2016-08-20"
    assert any("mismo radicado" in a for a in avisos)


# --- Caso 9: detalle, filtro, sin piso ----------------------------------------

@responses.activate
def test_detalle_sin_partes_y_filtro_sin_piso():
    _listado(*TODOS)
    docs = _scrap(fini="1999-01-01", ffin="1999-12-31")
    assert [(d.title, d.f_public) for d in docs] == [("LA_CCMA_1998-A-016_1999", "1999-05-31")]
    assert docs[0].detalle == "MOTOCLUB DE COLOMBIA LTDA CONTRA FEDERACIÓN"
    docs = _scrap(fini="2026-01-01", ffin="2026-12-31")
    assert [d.title for d in docs] == ["LA_CCMA_2025-A-0032_2026"]


@responses.activate
def test_conteo_y_orden_completo():
    _listado(*TODOS)
    docs = _scrap()
    # 23 filas: 2020 A 0007, 2022 AP 0001 y 2016 A 012 se omiten.
    assert len(docs) == 20
    assert len({d.title for d in docs}) == 20
    assert docs[0].title == "LA_CCMA_2025-A-0032_2026"
    assert sum(d.title_unverified for d in docs) == 4


# --- Caso 10: cancelación, límite, fallas -------------------------------------

@responses.activate
def test_stop_event_y_limit():
    _listado(*TODOS)
    stop = threading.Event()
    stop.set()
    assert _scrap(stop_event=stop) == []
    assert len(_scrap(limit=2)) == 2


@responses.activate
def test_pagina_que_falla_avisa_y_devuelve_vacio():
    _listado(status=503)
    avisos = []
    assert _scrap(on_progress=avisos.append) == []
    assert any("Error consultando" in a for a in avisos)


@responses.activate
def test_pagina_sin_paneles_avisa():
    responses.add(responses.GET, _URL, body=b"<html><body><p>Mantenimiento</p></body></html>")
    avisos = []
    assert _scrap(on_progress=avisos.append) == []
    assert any("no se encontraron los paneles" in a for a in avisos)
