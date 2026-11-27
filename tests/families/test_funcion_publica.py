import datetime
import threading

import pytest
import responses
from responses import matchers

from core.scrapers.families import funcion_publica as fp
from core.scrapers.families.funcion_publica import (
    _DETALLE_URL,
    _LISTADO_URL,
    _PDF_URL,
    _SOURCE,
    _anios,
    _elegir_fecha,
    _filas,
    _leer_detalle,
    _leer_h5,
    _titulo,
    ScrapFuncionPublica,
)
from core.scrapers.registry import FAMILY_REGISTRY


@pytest.fixture(autouse=True)
def _sin_pausa(monkeypatch):
    monkeypatch.setattr(fp, "_PAUSA_DETALLE", 0)


def _fila(norma_id, h5, epigrafe=""):
    # Copia de una fila real de funajax.php?t=ejecuta_busqueda_avanzada2.
    return (
        f'\t\t\t\t\t\t<a href="norma.php?i={norma_id}" target="_blank" class="list-group-item list-group-item-action">\n'
        f'\t\t\t\t\t\t\t<h5 class="list-group-item-heading">{h5}</h5>\n'
        f'\t\t\t\t\t\t\t<p class="list-group-item-text">{epigrafe}</p>\n'
        "\t\t\t\t\t\t</a> \n"
    )


def _listado(*filas):
    return (
        '\t\n<div class="container"> <h2><strong>Resultados</strong></h2>\n'
        '\t\t\t\t\t  <div class="row mt-3"> \n'
        '\t\t\t\t\t  <div class="col-lg-12 col-md-12"> \n'
        f'\t\t\t\t\t  <p class="list-group-item-text">Número de documentos encontrados: {len(filas)}</p> \n'
        + "".join(filas)
        + "</div></div></div>"
    )


def _detalle(norma_id, expedicion="15 de abril de 2026", vigencia="15 de abril de 2026", pdf=True):
    # Copia del bloque real de norma.php (botón y acordeón "Fechas").
    boton = (
        f'\t\t<a href="norma_pdf.php?i={norma_id}" target="_blank">\n'
        '\t\t<!--<a href="#" onclick="mostrarMensajeNoDisponible(); return false;" target="_blank">-->\n'
        '\t\t\t<button type="button" class="btn btn-yellow">Descargar PDF</button>\n\t\t</a>\n'
    ) if pdf else ""
    return (
        '<html><body><h2 class="titulo-norma"><strong>Concepto 138331 de 2026 Departamento Administrativo de la '
        'Función Pública</strong></h2>\n<div class="col-lg-3 col-md-12">\n' + boton +
        '<div id="collapseOne" class="collapse" aria-labelledby="headingOne" data-parent="#accordion">\n'
        '      <div class="card-body">\n'
        f"\t\t\t<p>Fecha de Expedición: {expedicion}</p>\n"
        '\t\t\t<p class="subrayado2"></p>\n'
        f"\t\t\t<p>Fecha de Entrada en Vigencia: {vigencia}</p>\n"
        '\t\t\t<p class="subrayado2"></p>\n'
        "\t\t\t<p>Medio de Publicación: </p>\n"
        "      </div></div></div></body></html>"
    )


def _mock_listados(anio, por_tipo=None, status=None):
    """Registra el listado de cada tipodoc del año: vacío salvo los dados."""
    por_tipo = por_tipo or {}
    status = status or {}
    for tipodoc, *_ in fp._TIPOS:
        responses.add(
            responses.GET,
            _LISTADO_URL,
            body=_listado(*por_tipo.get(tipodoc, [])),
            status=status.get(tipodoc, 200),
            match=[matchers.query_param_matcher({
                "t": "ejecuta_busqueda_avanzada2", "entidad1": "88", "tipdoc": tipodoc,
                "ano": str(anio), "pagina": "1",
            })],
        )


def _mock_detalle(norma_id, status=200, **kw):
    responses.add(
        responses.GET,
        _DETALLE_URL,
        body=_detalle(norma_id, **kw),
        status=status,
        match=[matchers.query_param_matcher({"i": norma_id})],
    )


def test_source_y_registro():
    assert FAMILY_REGISTRY["funcion_publica"] is ScrapFuncionPublica
    s = ScrapFuncionPublica()
    assert s.source == _SOURCE == "Departamento Administrativo de la Función Pública"
    assert s.checks_for_republication is False
    assert s.doc_id_uses_publication_date is False
    assert s.scheduled_min_lookback_days == 400


def test_solo_tipos_de_la_tabla():
    tipodocs = {t[0] for t in fp._TIPOS}
    assert tipodocs == {"7", "785", "1305", "11", "987", "29", "6", "825", "184", "845"}


@pytest.mark.parametrize("h5,prefijo,titulo", [
    ("Concepto 138331 de 2026", "CTO", "CTO_DAFP_138331_2026"),
    ("Concepto 000511 de 2026", "CTO", "CTO_DAFP_000511_2026"),
    ("Decreto 1384 de 2026", None, "D1384026"),
    ("Decreto 226 de 2026", None, "D0226026"),
    ("Circular Externa 100-011 de 2026", "CE", "CE_DAFP_100-011_2026"),
    ("Circular Conjunta 01 de 2026", "CJ", "CJ_DAFP_01_2026"),
    ("Circular Unificada 1 de 2020", "CU", "CU_DAFP_1_2020"),
    ("Resolución 035 de 2020", "R", "R_DAFP_035_2020"),
    ("Concepto 050101  de 2026", "CTO", "CTO_DAFP_050101_2026"),
    ("Concepto 050101\tde 2026", "CTO", "CTO_DAFP_050101_2026"),
])
def test_titulo(h5, prefijo, titulo):
    numero, anio = _leer_h5(h5)
    assert _titulo(prefijo, numero, anio, "1") == (titulo, False)


@pytest.mark.parametrize("h5,titulo", [
    ("Concepto 451981* de 2024", "CTO_DAFP_451981_2024"),
    ("Concepto ¿248691 de 2023", "CTO_DAFP_248691_2023"),
    ("Concepto  de 2021", "CTO_DAFP_SN-999_2021"),
])
def test_titulo_raro_sin_verificar(h5, titulo):
    numero, anio = _leer_h5(h5)
    assert _titulo("CTO", numero, anio, "999") == (titulo, True)


def test_concepto_con_letras_conserva_el_numero_sin_verificar():
    numero, anio = _leer_h5("Concepto C-197 de 2025")
    assert _titulo("CTO", numero, anio, "1") == ("CTO_DAFP_C-197_2025", True)


def test_decreto_con_numero_no_numerico_queda_sin_verificar():
    assert _titulo(None, "12A", 2026, "1") == ("D_DAFP_12A_2026", True)


def test_encabezado_sin_forma():
    assert _leer_h5("Documento sin año") == (None, None)


def test_parseo_listado():
    html = _listado(
        _fila("271436", "Circular Externa 100-002 de 2026", "Insta a las entidades de la rama ejecutiva nacional"),
        _fila("271536", "Circular Externa 100-003 de 2026"),
    )
    assert _filas(html) == [
        {"id": "271436", "h5": "Circular Externa 100-002 de 2026",
         "epigrafe": "Insta a las entidades de la rama ejecutiva nacional"},
        {"id": "271536", "h5": "Circular Externa 100-003 de 2026", "epigrafe": ""},
    ]


def test_listado_vacio():
    assert _filas(_listado()) == []


def test_parseo_detalle():
    d = _leer_detalle(_detalle("276776"))
    assert d == {"expedicion": datetime.date(2026, 4, 15), "vigencia": datetime.date(2026, 4, 15), "tiene_pdf": True}
    sin_pdf = _leer_detalle(_detalle("1", expedicion="", vigencia="", pdf=False))
    assert sin_pdf == {"expedicion": None, "vigencia": None, "tiene_pdf": False}


def test_elegir_fecha():
    hoy = datetime.date(2026, 11, 26)
    d = datetime.date
    assert _elegir_fecha(d(2026, 4, 15), d(2026, 4, 15), 2026, hoy) == ("2026-04-15", "expedicion")
    # Caso real 753262: expedición vacía (31-12-1969) y vigencia buena.
    assert _elegir_fecha(d(1969, 12, 31), d(2026, 1, 6), 2026, hoy) == ("2026-01-06", "vigencia")
    # Caso real 588851 de 2026 con expedición y vigencia de 2024.
    assert _elegir_fecha(d(2024, 9, 29), d(2024, 9, 29), 2026, hoy) == ("2026-01-01", "anio")
    # Caso real 610931 de 2025 con expedición futura.
    assert _elegir_fecha(d(2026, 12, 29), None, 2025, hoy) == ("2025-01-01", "anio")
    assert _elegir_fecha(None, None, 2025, hoy) == ("2025-01-01", "anio")


def test_anios_pedidos():
    assert list(_anios("2010-01-01", "2016-06-01")) == [2015, 2016]
    assert list(_anios("2026-01-01", "2026-11-26")) == [2026]
    assert list(_anios("2010-01-01", "2014-12-31")) == []


@responses.activate
def test_documento_completo():
    _mock_listados(2026, {"7": [_fila("276776", "Concepto 138331 de 2026", "Bonificación por servicios")]})
    _mock_detalle("276776")
    docs = ScrapFuncionPublica().scrap("2026-01-01", "2026-12-31")
    assert len(docs) == 1
    d = docs[0]
    assert d.source == _SOURCE
    assert d.link == {"url": f"{_PDF_URL}?i=276776", "method": "GET", "verify": False, "completar_fin_pdf": True}
    assert d.title == "CTO_DAFP_138331_2026"
    assert d.tipo == "Concepto"
    assert d.f_public == d.f_providencia == "2026-04-15"
    assert d.detalle == "Bonificación por servicios"
    assert d.title_unverified is False
    assert d.save_path.endswith("CTO_DAFP_138331_2026(extension)")


@responses.activate
def test_tipos_decreto_y_circular():
    _mock_listados(2026, {
        "11": [_fila("1", "Decreto 1384 de 2026")],
        "845": [_fila("2", "Circular Unificada 1 de 2026")],
    })
    _mock_detalle("1")
    _mock_detalle("2")
    docs = ScrapFuncionPublica().scrap("2026-01-01", "2026-12-31")
    assert [(d.title, d.tipo) for d in docs] == [("D1384026", "Decreto"), ("CU_DAFP_1_2026", "Circular")]


@responses.activate
def test_filtro_por_fecha_corregida():
    avisos = []
    _mock_listados(2026, {"7": [
        _fila("10", "Concepto 1 de 2026"),
        _fila("11", "Concepto 2 de 2026"),
        _fila("12", "Concepto 753262 de 2026"),
    ]})
    _mock_detalle("10", expedicion="15 de abril de 2026")
    _mock_detalle("11", expedicion="2 de enero de 2026")
    _mock_detalle("12", expedicion="31 de diciembre de 1969", vigencia="06 de enero de 2026")
    docs = ScrapFuncionPublica().scrap("2026-01-05", "2026-02-28", on_progress=avisos.append)
    assert [(d.title, d.f_public) for d in docs] == [("CTO_DAFP_753262_2026", "2026-01-06")]
    assert any("CTO_DAFP_753262_2026" in a and "se usa 2026-01-06" in a for a in avisos)


@responses.activate
def test_fila_de_otro_anio_no_abre_detalle():
    _mock_listados(2026, {"7": [_fila("10", "Concepto 1 de 2025")]})
    docs = ScrapFuncionPublica().scrap("2026-01-01", "2026-12-31")
    assert docs == []
    assert not any(c.request.url.startswith(_DETALLE_URL) for c in responses.calls)


@responses.activate
def test_dedup_por_id_entre_tipos():
    _mock_listados(2026, {"7": [_fila("10", "Concepto 1 de 2026")], "785": [_fila("10", "Concepto 1 de 2026")]})
    _mock_detalle("10")
    docs = ScrapFuncionPublica().scrap("2026-01-01", "2026-12-31")
    assert len(docs) == 1


@responses.activate
def test_detalle_sin_pdf_se_omite():
    avisos = []
    _mock_listados(2026, {"7": [_fila("10", "Concepto 1 de 2026")]})
    _mock_detalle("10", pdf=False)
    assert ScrapFuncionPublica().scrap("2026-01-01", "2026-12-31", on_progress=avisos.append) == []
    assert any("no trae PDF" in a for a in avisos)


@responses.activate
def test_numero_raro_sin_verificar_con_aviso():
    avisos = []
    _mock_listados(2024, {"7": [_fila("10", "Concepto 451981* de 2024")]})
    _mock_detalle("10", expedicion="3 de marzo de 2024", vigencia="3 de marzo de 2024")
    docs = ScrapFuncionPublica().scrap("2024-01-01", "2024-12-31", on_progress=avisos.append)
    assert docs[0].title == "CTO_DAFP_451981_2024"
    assert docs[0].title_unverified is True
    assert any("número inesperado" in a for a in avisos)


@responses.activate
def test_titulo_repetido_avisa():
    avisos = []
    _mock_listados(2026, {"7": [_fila("10", "Concepto 1 de 2026"), _fila("11", "Concepto 1 de 2026")]})
    _mock_detalle("10")
    _mock_detalle("11")
    docs = ScrapFuncionPublica().scrap("2026-01-01", "2026-12-31", on_progress=avisos.append)
    assert len(docs) == 2
    assert any("más de una vez" in a for a in avisos)


@responses.activate
def test_falla_un_listado_y_un_detalle_y_sigue():
    avisos = []
    _mock_listados(2026, {"7": [_fila("10", "Concepto 1 de 2026"), _fila("11", "Concepto 2 de 2026")],
                          "11": [_fila("20", "Decreto 1 de 2026")]},
                   status={"785": 500})
    _mock_detalle("10", status=500)
    _mock_detalle("11")
    _mock_detalle("20")
    docs = ScrapFuncionPublica().scrap("2026-01-01", "2026-12-31", on_progress=avisos.append)
    assert [d.title for d in docs] == ["CTO_DAFP_2_2026", "D0001026"]
    assert any("Error consultando Concepto Marco de 2026" in a for a in avisos)
    assert any("Error consultando el detalle de CTO_DAFP_1_2026" in a for a in avisos)


@responses.activate
def test_stop_event():
    stop = threading.Event()
    _mock_listados(2026, {"7": [_fila("10", "Concepto 1 de 2026"), _fila("11", "Concepto 2 de 2026")]})
    _mock_detalle("10")
    _mock_detalle("11")

    def progreso(texto):
        if "Concepto Marco" in texto:
            stop.set()

    docs = ScrapFuncionPublica().scrap("2026-01-01", "2026-12-31", stop_event=stop, on_progress=progreso)
    assert len(docs) == 2
    assert not any("tipdoc=11" in c.request.url for c in responses.calls)


@responses.activate
def test_limit():
    _mock_listados(2026, {"7": [_fila("10", "Concepto 1 de 2026"), _fila("11", "Concepto 2 de 2026")]})
    _mock_detalle("10")
    _mock_detalle("11")
    assert len(ScrapFuncionPublica().scrap("2026-01-01", "2026-12-31", limit=1)) == 1


@responses.activate
def test_antes_del_piso_no_pide_nada():
    assert ScrapFuncionPublica().scrap("2010-01-01", "2014-12-31") == []
    assert len(responses.calls) == 0


@responses.activate
def test_recorre_cada_anio_pedido():
    _mock_listados(2025, {"7": [_fila("10", "Concepto 1 de 2025")]})
    _mock_listados(2026, {"7": [_fila("11", "Concepto 2 de 2026")]})
    _mock_detalle("10", expedicion="5 de mayo de 2025", vigencia="5 de mayo de 2025")
    _mock_detalle("11")
    docs = ScrapFuncionPublica().scrap("2025-01-01", "2026-12-31")
    assert [(d.title, d.f_public) for d in docs] == [("CTO_DAFP_1_2025", "2025-05-05"), ("CTO_DAFP_2_2026", "2026-04-15")]
