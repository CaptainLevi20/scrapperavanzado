import datetime
import threading

import pytest
import responses

from core.scrapers.families.corporinoquia import (
    _ANIO_MINIMO,
    _SOURCE,
    _URL,
    _enlaces,
    _fecha,
    _referencia,
    ScrapCorporinoquia,
)
from core.scrapers.registry import FAMILY_REGISTRY


def _a(drive_id, texto):
    return (f'<a href="https://drive.google.com/file/d/{drive_id}/view?usp=sharing" '
            f'target="_blank" rel="noopener noreferrer">{texto}</a>')


# Recorte real del bloque 2026: el acuerdo siguiente queda dentro del <em> que
# abrió la fecha de publicación del anterior, y al final un enlace vacío que
# apunta al archivo del Acuerdo 200.3-2-25-002.
_BLOQUE_2026 = (
    "<p>" + _a("1tfN3S21FfeRVzIT-fDhCftCKMTSAxKoR", "ACUERDO 200.3-2-26-001 DEL 05 ENERO 2026 ")
    + '""POR MEDIO DEL CUAL EL CONSEJO DIRECTIVO REGLAMENTA LA CONVOCATORIA"" 29<em>/01/2026  14:50<br /><br />\n'
    + _a("1IkoWMFYl8QtsrBUafbSZo-E0-vvTooc-", "ACUERDO 200.3-2-26-002 DEL 20 FEBRERO 2026 ")
    + '"POR MEDIO DEL CUAL SE APRUEBA EL INFORME INTEGRAL" 20/02/2026  10:50'
    + '<a href="https://drive.google.com/file/d/1m2sOnsjiopQ4z9v1n8q7wc7x-L-JDvu2/view?usp=sharing"><br /></a></em></p>'
)
_BLOQUE_2025 = (
    "<p>" + _a("1m2sOnsjiopQ4z9v1n8q7wc7x-L-JDvu2", "ACUERDO 200.3-2-25-002 DE 21 FEBRERO 2025")
    + ' "POR MEDIO DEL CUAL SE APRUEBA EL INFORME 2024"<br /><br />'
    + _a("1GF3_REiKihgOFfPUP0H3U3uITB9vUhti", "200.3.2-25-004 08 DE ABRIL 2025")
    + ' "POR MEDIO DEL CUAL SE AUTORIZA A LA DIRECTORA"<br /></p>'
)
_BLOQUE_2024 = (
    "<p>" + _a("1kCU10aZJEA_ENKAtl9qGup8pw6TQZqjw", "Acuerdo 001 de 23 de mayo de 2024")
    + ' "POR MEDIO DEL CUAL SE APRUEBA EL PLAN DE ACCIÓN"<br />'
    + _a("1aKQdHh5gJHjKbWoQeK84lSEhzxT-p0s3", "ACUERDO 200.3-2-24-004")
    + ' "POR MEDIO DEL CUAL SE CONCEDE UNA AUTORIZACIÓN"<br />'
    + _a("1Kj6Dphwl4L5msQ7CI3pjNg8OTkqZTbai", "ACUERDO 200.3-2-24-6 DE 28 DE NOVIEMBRE DE 2024")
    + "</p>"
)


def _pagina(*bloques):
    paneles = "".join(
        f'<div class="sppb-panel"><div class="sppb-panel-heading"><span class="sppb-panel-title">{anio}</span></div>'
        f'<div class="sppb-panel-collapse"><div class="sppb-panel-body">{html}</div></div></div>'
        for anio, html in bloques
    )
    return f"<html><body><div class=\"sppb-panel-group\">{paneles}</div></body></html>".encode("utf-8")


def _listado(*bloques, status=200):
    responses.add(responses.GET, _URL, body=_pagina(*bloques), status=status)


def _scrap(fini="2025-01-01", ffin="2026-12-31", **kw):
    return ScrapCorporinoquia().scrap(fini, ffin, **kw)


def _uno(texto):
    _listado(("2026", "<p>" + _a("ID1", texto) + ' "REFERENCIA"</p>'))
    return _scrap()


def test_source_y_registro():
    assert _SOURCE == "Corporación Autónoma Regional de la Orinoquía"
    assert _ANIO_MINIMO == 2025
    assert FAMILY_REGISTRY["corporinoquia"] is ScrapCorporinoquia
    assert ScrapCorporinoquia.scheduled_min_lookback_days == 60


@pytest.mark.parametrize("texto,titulo,fecha", [
    ("ACUERDO 200.3-2-26-001 DEL 05 ENERO 2026", "A_CORPORINOQUIA_0001_2026", "2026-01-05"),
    ("ACUERDO No.200.3-2-26-003\xa0DEL 17 ABRIL 2026", "A_CORPORINOQUIA_0003_2026", "2026-04-17"),
    ("ACUERDO No. 200.3.2.26.007 DE FECHA 27 DE JULIO DE 2026", "A_CORPORINOQUIA_0007_2026", "2026-07-27"),
    ("ACUERDO 200.3.2-25-006 DE 5 JUNIO 2025", "A_CORPORINOQUIA_0006_2025", "2025-06-05"),
    ("200.3.2-25-004 08 DE ABRIL 2025", "A_CORPORINOQUIA_0004_2025", "2025-04-08"),
    ("ACUERDO 200.3-2-25-017 DE\xa028\xa0NOVIEMBRE\xa02025", "A_CORPORINOQUIA_0017_2025", "2025-11-28"),
])
@responses.activate
def test_variantes_del_texto_del_enlace(texto, titulo, fecha):
    [doc] = _uno(texto)

    assert doc.title == titulo
    assert doc.f_public == doc.f_providencia == fecha
    assert doc.tipo == "Acuerdo"


def test_fecha():
    assert _fecha("DE FECHA 27 DE JULIO DE 2026") == datetime.date(2026, 7, 27)
    assert _fecha("ACUERDO 200.3-2-24-004") is None


def test_referencia_sin_fecha_de_publicacion():
    assert _referencia('""POR MEDIO DEL CUAL SE REGLAMENTA"" 29/01/2026  14:50') == "POR MEDIO DEL CUAL SE REGLAMENTA"
    assert _referencia(' \xa0"POR MEDIO DEL CUAL SE ADOPTA" ') == "POR MEDIO DEL CUAL SE ADOPTA"


@responses.activate
def test_documento_completo_con_descarga_por_drive():
    _listado(("2026", _BLOQUE_2026))

    d1, d2 = _scrap()

    assert d1.title == "A_CORPORINOQUIA_0001_2026"
    assert d1.link == {
        "url": "https://drive.google.com/uc?export=download&id=1tfN3S21FfeRVzIT-fDhCftCKMTSAxKoR",
        "method": "GET",
    }
    assert d1.detalle == "POR MEDIO DEL CUAL EL CONSEJO DIRECTIVO REGLAMENTA LA CONVOCATORIA"
    assert d1.save_path == f"{_SOURCE}/2026-01-05/Acuerdo/A_CORPORINOQUIA_0001_2026(extension)"
    # El segundo está dentro del <em> del primero.
    assert d2.title == "A_CORPORINOQUIA_0002_2026"
    assert d2.detalle == "POR MEDIO DEL CUAL SE APRUEBA EL INFORME INTEGRAL"


def test_enlace_vacio_ignorado_aunque_apunte_a_otro_acuerdo():
    enlaces = list(_enlaces(_BLOQUE_2026))

    assert [e["drive_id"] for e in enlaces] == [
        "1tfN3S21FfeRVzIT-fDhCftCKMTSAxKoR", "1IkoWMFYl8QtsrBUafbSZo-E0-vvTooc-",
    ]


@responses.activate
def test_rango_y_piso():
    _listado(("2026", _BLOQUE_2026), ("2025", _BLOQUE_2025), ("2024", _BLOQUE_2024))
    avisos = []

    assert [d.title for d in _scrap("2023-01-01", "2026-12-31", on_progress=avisos.append)] == [
        "A_CORPORINOQUIA_0001_2026", "A_CORPORINOQUIA_0002_2026",
        "A_CORPORINOQUIA_0002_2025", "A_CORPORINOQUIA_0004_2025",
    ]
    assert [d.title for d in _scrap("2026-02-01", "2026-02-28")] == ["A_CORPORINOQUIA_0002_2026"]
    # Los de 2024 (con o sin código, con o sin fecha) quedan fuera en silencio.
    assert not any("Aviso" in a for a in avisos)


@responses.activate
def test_anio_del_codigo_distinto_gana_la_fecha():
    avisos = []
    _listado(("2026", "<p>" + _a("ID1", "ACUERDO 200.3-2-25-018 DEL 05 ENERO 2026") + "</p>"))

    [doc] = _scrap(on_progress=avisos.append)

    assert doc.title == "A_CORPORINOQUIA_0018_2026"
    assert any("no coincide" in a for a in avisos)


@responses.activate
def test_codigo_sin_fecha_y_fecha_sin_codigo_se_descartan_con_aviso():
    _listado(("2026", "<p>" + _a("ID1", "ACUERDO 200.3-2-26-013") + _a("ID2", "Acuerdo 013 de 05 de enero de 2026") + "</p>"))
    avisos = []

    assert _scrap(on_progress=avisos.append) == []
    assert any("sin fecha legible" in a for a in avisos)
    assert any("sin código" in a for a in avisos)


@responses.activate
def test_fecha_futura_avisa_y_queda_fuera_de_rango():
    futuro = datetime.date.today().year + 1
    _listado(("x", "<p>" + _a("ID1", f"ACUERDO 200.3-2-{futuro % 100:02d}-001 DEL 05 ENERO {futuro}") + "</p>"))
    avisos = []

    assert _scrap(ffin=datetime.date.today().isoformat(), on_progress=avisos.append) == []
    assert any("fecha futura" in a for a in avisos)


@responses.activate
def test_dedup_por_id_de_drive():
    _listado(("2026", "<p>" + _a("ID1", "ACUERDO 200.3-2-26-001 DEL 05 ENERO 2026") + "<br>"
              + _a("ID1", "ACUERDO 200.3-2-26-001 DEL 05 ENERO 2026") + "</p>"))

    assert len(_scrap()) == 1


@responses.activate
def test_limit_y_stop_event():
    _listado(("2026", _BLOQUE_2026))

    assert len(_scrap(limit=1)) == 1

    parar = threading.Event()
    parar.set()
    assert _scrap(stop_event=parar) == []


@responses.activate
def test_error_de_la_pagina():
    _listado(status=500)
    avisos = []

    assert _scrap(on_progress=avisos.append) == []
    assert any("Error consultando" in a for a in avisos)


def test_la_descripcion_no_arrastra_el_resto_de_la_pagina():
    # Hallazgo de la revisión del PR #110: la descripción era todo el texto
    # entre un enlace y el siguiente. En el último acuerdo de la página (o en
    # uno sin fecha-hora de publicación) arrastraba el título del acordeón
    # siguiente, el pie de página y hasta el código de la página.
    html = _pagina(
        ("2025", "<p>" + _a("ULTIMO", "ACUERDO 200.3-2-25-009 DE 10 DE DICIEMBRE DE 2025")
         + ' "POR MEDIO DEL CUAL SE APRUEBA EL PRESUPUESTO"</p>'),
        ("2024", "<p>Sin acuerdos publicados</p>"),
    ).decode("utf-8").replace(
        "</body>",
        "<script>var sppbVersion = '5.0';</script><!-- comentario -->"
        "<footer><p>Corporinoquia · Yopal, Casanare · Todos los derechos reservados</p></footer></body>",
    )

    [enlace] = list(_enlaces(html))

    assert _referencia(enlace["resto"]) == "POR MEDIO DEL CUAL SE APRUEBA EL PRESUPUESTO"
