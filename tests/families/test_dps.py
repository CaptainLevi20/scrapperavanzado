import datetime
import threading

import pytest
import responses

from core.scrapers.families.dps import (
    _ANIO_MINIMO,
    _API_PAGES,
    _SECCIONES,
    _SOURCE,
    _filas,
    _limpiar,
    _parse_fecha,
    _titulo,
    _url_descarga,
    ScrapDPS,
)
from core.scrapers.registry import FAMILY_REGISTRY

_SP = "https://dpsco.sharepoint.com/:b:/s/CentroDocumentacionPSF/"
_ZW = "\u200b"


def _a(clave, texto, consulta=""):
    # Enlace real: compartido anónimo de SharePoint, a veces con "?e=XXXX".
    return f'<a href="{_SP}{clave}{consulta}" rel="noopener" target="_blank"><span data-olk-copy-source="MessageBody">{texto}</span></a>'


def _fila(tipo, fecha, numero_html, contenido="Por la cual se establecen los empleos"):
    # Copia de una fila real del acordeón (cuatro celdas con estilos de Word).
    return (
        f'<tr><td style="width: 12.7517%; text-align: center;"><span data-olk-copy-source="MessageBody">{tipo}</span>'
        '<span data-olk-copy-source="MessageBody"><br/></span></td>'
        f'<td style="width: 15.4362%; text-align: center;"><span data-olk-copy-source="MessageBody">{fecha}</span></td>'
        f'<td style="width: 12.2484%; text-align: center;">{numero_html}</td>'
        f'<td style="width: 59.5637%; text-align: justify;"><span data-olk-copy-source="MessageBody">{contenido}</span></td></tr>'
    )


_CABECERA = (
    '<tr style="height: 24px;"><td style="text-align: center;"><strong>TIPO</strong></td>'
    '<td style="text-align: center;"><strong>FECHA</strong></td>'
    '<td style="text-align: center;"><strong>No.</strong></td>'
    '<td style="text-align: center;"><strong>CONTENIDO</strong></td></tr>'
)


def _panel(titulo, *filas, cabecera=True):
    return (
        '<div class="elementor-toggle-item">'
        '<div class="elementor-tab-title" data-tab="1" role="tab">'
        '<span aria-hidden="true" class="elementor-toggle-icon elementor-toggle-icon-left"></span>'
        f'<a class="elementor-toggle-title" href="">{titulo}</a></div>'
        '<div class="elementor-tab-content elementor-clearfix" role="tabpanel">'
        '<table style="border-collapse: collapse; width: 100%;"><tbody>'
        + (_CABECERA if cabecera else "") + "".join(filas) +
        "</tbody></table></div></div>"
    )


def _pagina(*paneles, page_id=33139):
    return {
        "id": page_id,
        "modified": "2026-11-10T09:12:44",
        "content": {"rendered": '<div class="elementor-toggle" role="tablist">' + "".join(paneles) + "</div>", "protected": False},
    }


def _seccion(page_id, *paneles, status=200):
    if status != 200:
        responses.add(responses.GET, f"{_API_PAGES}/{page_id}", status=status)
        return
    responses.add(responses.GET, f"{_API_PAGES}/{page_id}", json=_pagina(*paneles, page_id=page_id), status=200)


_IDS = {nombre: page_id for nombre, page_id, *_ in _SECCIONES}


def _vacias(*excepto):
    for nombre, page_id in _IDS.items():
        if nombre not in excepto:
            _seccion(page_id)


# ---------- registro y ajustes ----------


def test_registro_y_ajustes():
    assert FAMILY_REGISTRY["dps"] is ScrapDPS
    s = ScrapDPS()
    assert s.source == _SOURCE == "Departamento Administrativo para la Prosperidad Social"
    assert s.scheduled_min_lookback_days == 60
    assert s.doc_id_uses_publication_date is False
    assert s.checks_for_republication is True
    assert s.alerta_margen_dias == 120
    assert _ANIO_MINIMO == 2015
    # Sólo lo propio del DPS: sin decretos ni leyes (decisión del 2026-11-26).
    assert [(n, t, p) for n, _, t, p in _SECCIONES] == [
        ("Resoluciones", "Resolución", "R"),
        ("Circulares", "Circular", "C"),
        ("Acuerdos interinstitucionales", "Acuerdo", "A"),
    ]


# ---------- caso 1: espacios de ancho cero ----------


def test_limpiar_quita_ancho_cero_y_espacios():
    assert _limpiar(f"RESOLUCIO{_ZW}{_ZW}N\xa0 CONJUNTA ") == "RESOLUCION CONJUNTA"
    assert _limpiar(f"1{_ZW}997") == "1997"


# ---------- caso 2: fechas ----------


@pytest.mark.parametrize("texto,panel,esperada", [
    ("06 de noviembre de 2026", 2026, "2026-11-06"),
    ("19 de junio 2024", 2024, "2024-06-19"),
    ("28 de enero del 2025", 2025, "2025-01-28"),
    ("25 de Agosto de 2025", 2025, "2025-08-25"),
    ("27-feb-15", 2015, "2015-02-27"),
    ("01-Sept-2020", 2020, "2020-09-01"),
    ("31-jul- 2018", 2018, "2018-07-31"),
    ("2-julio-2020", 2020, "2020-07-02"),
    ("05-ene.-17", 2017, "2017-01-05"),
    ("30-dic.-16", 2016, "2016-12-30"),
    ("28-sep-018", 2018, "2018-09-28"),
    ("06-mar", 2024, "2024-03-06"),
    ("8-JUN-20", 2020, "2020-06-08"),
    ("24 – ene", 2023, "2023-01-24"),
    ("sept-20", 2021, "2021-09-20"),
    ("oct-8", 2021, "2021-10-08"),
    ("JUL-26", 2022, "2022-07-26"),
    ("22-sept", 2021, "2021-09-22"),
    (f"14-{_ZW}julio", 2022, "2022-07-14"),
])
def test_parse_fecha_formatos_reales(texto, panel, esperada):
    assert _parse_fecha(texto, panel) == datetime.date.fromisoformat(esperada)


@pytest.mark.parametrize("texto", ["", "sin fecha", "31-feb", "45-mar", "15-xyz-2020"])
def test_parse_fecha_ilegible(texto):
    assert _parse_fecha(texto, 2020) is None


def test_parse_fecha_con_anio_distinto_al_del_panel_usa_el_panel():
    # El año del panel manda: es lo que agrupa el listado y va en el título.
    assert _parse_fecha("10-dic-19", 2020) == datetime.date(2020, 12, 10)


# ---------- caso 3: número → título ----------


@pytest.mark.parametrize("prefijo,numero,anio,titulo", [
    ("R", "00464", 2016, "R_DPS_00464_2016"),
    ("R", "243654", 2026, "R_DPS_243654_2026"),
    ("R", "0079 Anexo", 2024, "R_DPS_0079_2024"),
    ("C", "018", 2021, "C_DPS_018_2021"),
    ("A", "001", 2025, "A_DPS_001_2025"),
    ("R", f"1{_ZW}997", 2019, "R_DPS_1997_2019"),
])
def test_titulo_numero_tal_cual(prefijo, numero, anio, titulo):
    assert _titulo(prefijo, numero, anio) == (titulo, False)


def test_titulo_numero_raro_queda_sin_verificar():
    assert _titulo("R", "S/N", 2020) == ("R_DPS_SN_2020", True)
    assert _titulo("R", "", 2020) == ("R_DPS_SN_2020", True)


# ---------- caso 4: enlace de descarga ----------


def test_url_descarga():
    assert _url_descarga(f"{_SP}IQDxi") == f"{_SP}IQDxi?download=1"
    assert _url_descarga(f"{_SP}EYLYH?e=Hi6iqk") == f"{_SP}EYLYH?e=Hi6iqk&download=1"


# ---------- caso 5: lectura del acordeón, anexos y enlaces ignorados ----------


def test_filas_lee_paneles_y_salta_cabecera():
    html = _pagina(
        _panel("2026", _fila("Resolución", "06 de noviembre de 2026", _a("IQDxi", "243654"))),
        _panel("Circulares 2017", _fila("CIRCULAR" + _ZW, "16-Feb", _a("EYLYH", "007", "?e=Hi6iqk")), cabecera=False),
    )["content"]["rendered"]
    filas = _filas(html)
    assert [(f["anio"], f["fecha"], f["numero"], f["enlaces"]) for f in filas] == [
        (2026, "06 de noviembre de 2026", "243654", [f"{_SP}IQDxi"]),
        (2017, "16-Feb", "007", [f"{_SP}EYLYH?e=Hi6iqk"]),
    ]
    assert filas[0]["epigrafe"] == "Por la cual se establecen los empleos"


def test_filas_varios_pdf_y_enlaces_ajenos():
    numero = (
        _a("IQA1", "00460") + " " + _a("IQA2", "Anexo 1") + " " + _a("IQA2", "repetido")
        + ' <a href="https://dpsco.sharepoint.com/:f:/s/CentroDocumentacionPSF/Carpeta">carpeta</a>'
        + ' <a href="http://centrodedocumentacion.prosperidadsocial.gov.co/Documentos/x.pdf">viejo</a>'
    )
    contenido = 'Texto <a href="https://www.suin-juriscol.gov.co/viewDocument.asp?id=1">SUIN</a> ' + _a("IQA3", "Anexo 2")
    html = _pagina(_panel("2026", _fila("Resolución", "3 de marzo de 2026", numero, contenido)))["content"]["rendered"]
    [fila] = _filas(html)
    assert fila["numero"] == "00460"
    assert fila["enlaces"] == [f"{_SP}IQA1", f"{_SP}IQA2", f"{_SP}IQA3"]


def test_filas_numero_sin_enlace_toma_el_texto_de_la_celda():
    html = _pagina(_panel("2026", _fila("Resolución", "6 de agosto de 2026", "<span>208303</span>")))["content"]["rendered"]
    [fila] = _filas(html)
    assert fila["numero"] == "208303"
    assert fila["enlaces"] == []


# ---------- scrap() con el sitio simulado ----------


def _scrap(fini="2015-01-01", ffin="2026-12-31", **kw):
    avisos = []
    docs = ScrapDPS().scrap(fini, ffin, on_progress=avisos.append, **kw)
    return docs, avisos


@responses.activate
def test_scrap_completo_resoluciones_circulares_acuerdo():
    _seccion(_IDS["Resoluciones"], _panel(
        "2026",
        _fila("Resolución", "06 de noviembre de 2026", _a("IQDxi", "243654"), "Por medio de la cual se modifica"),
        _fila("Resolución", "3 de marzo de 2026", _a("IQA1", "00460") + _a("IQA2", "Anexo") + _a("IQA3", "Anexo")),
    ), _panel("2016", _fila("RESOLUCIÓN CONJUNTA", "30-dic.-16", _a("IQB1", "00464"))))
    _seccion(_IDS["Circulares"], _panel("Circulares 2021", _fila("CIRCULAR", "22-sept", _a("EYL", "018", "?e=Hi6iqk")), cabecera=False))
    _seccion(_IDS["Acuerdos interinstitucionales"], _panel("2025", _fila("Acuerdo Interinstitucional", "16 de enero de 2025", _a("IQC1", "001"))))

    docs, avisos = _scrap()
    resumen = [(d.title, d.tipo, d.f_public, d.link["url"]) for d in docs]
    assert resumen == [
        ("R_DPS_243654_2026", "Resolución", "2026-11-06", f"{_SP}IQDxi?download=1"),
        ("R_DPS_00460_2026", "Resolución", "2026-03-03", f"{_SP}IQA1?download=1"),
        ("R_DPS_00460_2026_A01", "Resolución", "2026-03-03", f"{_SP}IQA2?download=1"),
        ("R_DPS_00460_2026_A02", "Resolución", "2026-03-03", f"{_SP}IQA3?download=1"),
        ("R_DPS_00464_2016", "Resolución", "2016-12-30", f"{_SP}IQB1?download=1"),
        ("C_DPS_018_2021", "Circular", "2021-09-22", f"{_SP}EYL?e=Hi6iqk&download=1"),
        ("A_DPS_001_2025", "Acuerdo", "2025-01-16", f"{_SP}IQC1?download=1"),
    ]
    d = docs[0]
    assert d.source == _SOURCE
    assert d.link["method"] == "GET"
    assert d.f_providencia == "2026-11-06"
    assert d.detalle == "Por medio de la cual se modifica"
    assert d.title_unverified is False
    assert d.save_path == f"{_SOURCE}/2026-11-06/Resolución/R_DPS_243654_2026(extension)"
    assert not [a for a in avisos if "omit" in a.lower() or "repet" in a.lower()]


@responses.activate
def test_scrap_filtra_por_fecha_y_piso():
    _seccion(_IDS["Resoluciones"],
             _panel("2026", _fila("Resolución", "06 de noviembre de 2026", _a("IQ1", "243654")),
                    _fila("Resolución", "10 de enero de 2026", _a("IQ2", "00010"))),
             _panel("2014", _fila("Resolución", "5 de mayo de 2014", _a("IQ3", "00500"))))
    _vacias("Resoluciones")
    docs, _ = _scrap("2026-11-01", "2026-11-30")
    assert [d.title for d in docs] == ["R_DPS_243654_2026"]
    docs, _ = _scrap("2010-01-01", "2026-12-31")
    assert "R_DPS_00500_2014" not in [d.title for d in docs]


@responses.activate
def test_scrap_fila_sin_enlace_o_sin_sharepoint_se_omite_con_aviso():
    _seccion(_IDS["Resoluciones"], _panel(
        "2026",
        _fila("Resolución", "6 de agosto de 2026", "<span>208303</span>"),
        _fila("Resolución", "7 de agosto de 2026",
              '<a href="https://www.suin-juriscol.gov.co/viewDocument.asp?id=30019979">1878</a>'),
        _fila("Resolución", "8 de agosto de 2026", _a("IQ9", "208400")),
    ))
    _vacias("Resoluciones")
    docs, avisos = _scrap()
    assert [d.title for d in docs] == ["R_DPS_208400_2026"]
    omitidas = [a for a in avisos if "sin enlace" in a]
    assert len(omitidas) == 2
    assert any("208303" in a for a in omitidas) and any("1878" in a for a in omitidas)


@responses.activate
def test_scrap_fecha_ilegible_se_omite_con_aviso():
    _seccion(_IDS["Resoluciones"], _panel("2026", _fila("Resolución", "pendiente", _a("IQ1", "00001"))))
    _vacias("Resoluciones")
    docs, avisos = _scrap()
    assert docs == []
    assert any("fecha ilegible" in a and "00001" in a for a in avisos)


@responses.activate
def test_scrap_numero_repetido_con_pdf_distinto_se_queda_el_primero():
    # 2418 y 02418 de 2020: el mismo número, dos PDF distintos.
    _seccion(_IDS["Resoluciones"], _panel(
        "2020",
        _fila("RESOLUCIÓN", "10-dic-20", _a("IQX", "2418")),
        _fila("RESOLUCIÓN", "10-dic-20", _a("IQY", "02418")),
    ))
    _vacias("Resoluciones")
    docs, avisos = _scrap()
    assert [(d.title, d.link["url"]) for d in docs] == [("R_DPS_2418_2020", f"{_SP}IQX?download=1")]
    assert any("repetid" in a and "02418" in a for a in avisos)


@responses.activate
def test_scrap_mismo_pdf_mismo_numero_en_silencio():
    # 860 y 00860 de 2015 con el mismo PDF.
    _seccion(_IDS["Resoluciones"], _panel(
        "2015",
        _fila("RESOLUCIÓN", "27-feb-15", _a("IQS", "860")),
        _fila("RESOLUCIÓN", "27-feb-15", _a("IQS", "00860")),
    ))
    _vacias("Resoluciones")
    docs, avisos = _scrap()
    assert [d.title for d in docs] == ["R_DPS_860_2015"]
    assert not [a for a in avisos if "IQS" in a or "00860" in a]


@responses.activate
def test_scrap_mismo_pdf_con_dos_numeros_avisa_y_guarda_el_primero():
    # 02163/02000 de 2024; circulares 01 de 2018 y de 2019 con el mismo PDF.
    _seccion(_IDS["Resoluciones"], _panel(
        "2024",
        _fila("Resolución", "20-nov", _a("IQM", "02163")),
        _fila("Resolución", "01-oct", _a("IQM", "02000")),
    ))
    _seccion(_IDS["Circulares"],
             _panel("Circulares 2019", _fila("CIRCULAR", "01-Mar-2019", _a("EYC", "01")), cabecera=False),
             _panel("Circulares 2018", _fila("CIRCULAR", "15-Mar-2018", _a("EYC", "01")), cabecera=False))
    _seccion(_IDS["Acuerdos interinstitucionales"])
    docs, avisos = _scrap()
    assert [d.title for d in docs] == ["R_DPS_02163_2024", "C_DPS_01_2019"]
    mismo = [a for a in avisos if "mismo archivo" in a]
    assert any("02163" in a and "02000" in a for a in mismo)
    assert any("C_DPS_01_2019" in a and "C_DPS_01_2018" in a for a in mismo)


@responses.activate
def test_scrap_dedup_no_depende_de_la_ventana():
    # El primero de la pareja cae fuera de la ventana: el segundo igual se
    # descarta, para que el título no cambie según el rango de la corrida.
    _seccion(_IDS["Resoluciones"], _panel(
        "2024",
        _fila("Resolución", "20-nov", _a("IQM", "02163")),
        _fila("Resolución", "01-oct", _a("IQM", "02000")),
    ))
    _vacias("Resoluciones")
    docs, _ = _scrap("2024-10-01", "2024-10-31")
    assert docs == []


@responses.activate
def test_scrap_numero_raro_sin_verificar_con_aviso():
    _seccion(_IDS["Resoluciones"], _panel("2026", _fila("Resolución", "3 de marzo de 2026", _a("IQR", "S/N"))))
    _vacias("Resoluciones")
    docs, avisos = _scrap()
    assert [(d.title, d.title_unverified) for d in docs] == [("R_DPS_SN_2026", True)]
    assert any("número" in a and "S/N" in a for a in avisos)


@responses.activate
def test_scrap_seccion_que_falla_avisa_y_sigue():
    _seccion(_IDS["Resoluciones"], status=500)
    _seccion(_IDS["Circulares"], _panel("Circulares 2021", _fila("CIRCULAR", "22-sept", _a("EYL", "018")), cabecera=False))
    _seccion(_IDS["Acuerdos interinstitucionales"])
    docs, avisos = _scrap()
    assert [d.title for d in docs] == ["C_DPS_018_2021"]
    assert any("Error" in a and "Resoluciones" in a for a in avisos)


@responses.activate
def test_scrap_seccion_vacia_avisa():
    _vacias()
    docs, avisos = _scrap()
    assert docs == []
    assert sum("sin filas" in a for a in avisos) == 3


@responses.activate
def test_scrap_limit_y_stop_event():
    _seccion(_IDS["Resoluciones"], _panel(
        "2026", *[_fila("Resolución", "3 de marzo de 2026", _a(f"IQ{i}", f"0{i}")) for i in range(1, 6)]))
    _vacias("Resoluciones")
    docs, _ = _scrap(limit=2)
    assert [d.title for d in docs] == ["R_DPS_01_2026", "R_DPS_02_2026"]

    stop = threading.Event()
    stop.set()
    docs, _ = _scrap(stop_event=stop)
    assert docs == []
