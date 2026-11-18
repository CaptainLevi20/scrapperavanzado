import json
from pathlib import Path

import pytest
import requests
import responses
from responses import matchers

import core.scrapers.families.corte_suprema as csj_module
from core.scrapers.families.corte_suprema import (
    ScrapCorteSuprema,
    _clasificar_sala,
    _doc_desde_resultado,
    _tipo_desde_ojeador,
    _tramos_mensuales,
    _url_descarga,
)
from core.scrapers.registry import FAMILY_REGISTRY


@pytest.fixture(autouse=True)
def _sin_espera_entre_reintentos(monkeypatch):
    # Los reintentos esperan unos segundos entre intento e intento contra el
    # sitio real; en las pruebas no hay nada que esperar.
    monkeypatch.setattr(csj_module, "_ESPERA_REINTENTO_SEG", 0)


def test_corte_suprema_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["corte_suprema"] is ScrapCorteSuprema


def test_resolve_unverified_document_recovers_the_title_and_tipo_from_the_files_own_text(monkeypatch):
    # Real-world example: nombre_providencia said "doc", but the file's first
    # page actually names the real providencia — "ATP1800-2019" — an Auto (A).
    monkeypatch.setattr(csj_module, "_extraer_texto_primera_pagina", lambda *_a, **_k: "Radicado No. ATP1800-2019")

    class _Doc:
        title = "doc_2019"
        tipo = "Desconocido"

    doc = _Doc()
    scraper = ScrapCorteSuprema()
    scraper.resolve_unverified_document(doc, Path("fake.docx"), "application/vnd.openxmlformats")

    assert doc.title == "ATP1800-2019"
    assert doc.tipo == "Auto"


def test_resolve_unverified_document_leaves_doc_untouched_when_no_code_is_found(monkeypatch):
    monkeypatch.setattr(csj_module, "_extraer_texto_primera_pagina", lambda *_a, **_k: "sin ningún código aquí")

    class _Doc:
        title = "doc_2019"
        tipo = "Desconocido"

    doc = _Doc()
    scraper = ScrapCorteSuprema()
    scraper.resolve_unverified_document(doc, Path("fake.docx"), "application/vnd.openxmlformats")

    assert doc.title == "doc_2019"
    assert doc.tipo == "Desconocido"


def test_resolve_unverified_document_is_defensive_about_read_failures(monkeypatch, caplog):
    def _raise(*_a, **_k):
        raise RuntimeError("archivo corrupto")

    monkeypatch.setattr(csj_module, "_extraer_texto_primera_pagina", _raise)

    class _Doc:
        title = "doc_2019"
        tipo = "Desconocido"

    doc = _Doc()
    scraper = ScrapCorteSuprema()
    with caplog.at_level("WARNING", logger="core.scrapers.families.corte_suprema"):
        scraper.resolve_unverified_document(doc, Path("fake.docx"), "application/vnd.openxmlformats")  # no debe lanzar

    assert doc.title == "doc_2019"
    # Regression test: this used to be a bare print(), invisible to server logs —
    # now it must go through the logging module like the rest of the project.
    assert any("No se pudo leer la primera página" in r.message for r in caplog.records)


# --- Ojeador (buscador nuevo de la Corte, noviembre 2026) -------------------

_UBICACION_REAL = (
    "SALAS/CIVIL/2026/Dr. Fernando Augusto Jiménez Valderrama/11.- Noviembre/Autos/"
    "AC7263-2026 [2026-03319-00].docx"
)


def _resultado(**override):
    # Resultado real de buscadorjurisprudenciabackend.cortesuprema.gov.co/search/
    # (2026-11-18), recortado a los campos que usa la familia.
    item = {
        "id": "1171961",
        "Nombre": "AC7263-2026 [2026-03319-00]",
        "Numerador": "AC7263-2026",
        "CUI": "11001020300020260331900",
        "FechaConsolidacionFirma": "2026-11-06",
        "Especialidad": "CIVIL",
        "Sala": "CIVIL",
        "TipoDeProvidencia": "AUTO",
        "ClaseActuacion": "RECURSO DE REVISIÓN",
        "Ponente": "DR FERNANDO AUGUSTO JIMÉNEZ VALDERRAMA",
        "Ubicacion": _UBICACION_REAL,
    }
    item.update(override)
    return item


def test_tramos_mensuales_recorta_primer_y_ultimo_mes():
    assert _tramos_mensuales("2026-01-15", "2026-03-10") == [
        ("2026-01-15", "2026-01-31"),
        ("2026-02-01", "2026-02-28"),
        ("2026-03-01", "2026-03-10"),
    ]


def test_tramos_mensuales_un_solo_dia():
    assert _tramos_mensuales("2026-11-18", "2026-11-18") == [("2026-11-18", "2026-11-18")]


def test_tramos_mensuales_cruza_el_cambio_de_anio():
    assert _tramos_mensuales("2025-12-20", "2026-01-05") == [
        ("2025-12-20", "2025-12-31"),
        ("2026-01-01", "2026-01-05"),
    ]


@pytest.mark.parametrize(
    "tipo_providencia, codigo, esperado",
    [
        ("AUTO", "AC1-2026", "Auto"),
        ("AUTO TUTELA", "ATP1-2026", "Auto"),
        ("AUTOHABEAS", "AHP1-2026", "Auto"),
        ("SENTENCIA", "SC1-2026", "Sentencia"),
        ("SENTENCIA TUTELA", "STP1-2026", "Sentencia"),
        ("CONCEPTO", "CP1-2026", "Concepto"),
        ("CONCEPTO EXTRADICCION", "CP2-2026", "Concepto"),
        ("OTROS", "SC9-2026", "Sentencia"),
        ("Otros", None, "Desconocido"),
        ("", None, "Desconocido"),
    ],
)
def test_tipo_desde_ojeador(tipo_providencia, codigo, esperado):
    assert _tipo_desde_ojeador(tipo_providencia, codigo) == esperado


def test_clasificar_sala_tutela_penal_va_a_la_sala_que_la_resolvio():
    item = _resultado(
        Sala="PENAL", Especialidad="PENAL", TipoDeProvidencia="SENTENCIA TUTELA",
        Ubicacion="SALAS/TUTELAS/PENA/2026/Dr. Gerson Chaverra Castro/Sentencia/STP21139-2026.docx",
    )
    assert _clasificar_sala(item) == ("Tutela", "Sala de Casación Penal", "SCP")


def test_clasificar_sala_plena():
    item = _resultado(
        Sala="PLENA", Especialidad="PLENA", TipoDeProvidencia="AUTO",
        Ubicacion="SALAS/PLENA/2026/Autos/APL6636-2026.docx",
    )
    assert _clasificar_sala(item) == ("Plena", "Sala Plena", "SPL")


def test_clasificar_sala_civil_y_laboral():
    assert _clasificar_sala(_resultado()) == ("Civil", "Sala de Casación Civil", "SCC")
    laboral = _resultado(Sala="LABORAL", Especialidad="LABORAL", Ubicacion="SALAS/LABORAL/2026/x/AL1-2026.docx")
    assert _clasificar_sala(laboral) == ("Laboral", "Sala de Casación Laboral", "SCL")


def test_clasificar_sala_vacia_o_desconocida_no_rompe():
    sin_sala = _resultado(Sala="", Especialidad="", Ubicacion="SALAS/LABORAL/2026/x.docx")
    assert _clasificar_sala(sin_sala) == ("Laboral", "Sala de Casación Laboral", "SCL")
    rara = _resultado(Sala="OTRA", Especialidad="", Ubicacion="raro/x.docx")
    assert _clasificar_sala(rara) == (None, None, "OTRA")


def test_url_descarga_codifica_la_ubicacion():
    assert _url_descarga(_UBICACION_REAL) == (
        "https://buscadorjurisprudenciabackend.cortesuprema.gov.co/document/descargar?path="
        "SALAS%2FCIVIL%2F2026%2FDr.%20Fernando%20Augusto%20Jim%C3%A9nez%20Valderrama%2F11.-%20Noviembre"
        "%2FAutos%2FAC7263-2026%20%5B2026-03319-00%5D.docx"
    )


def test_doc_desde_resultado_completo():
    doc = _doc_desde_resultado(_resultado())
    assert doc.title == "AC7263-2026 [2026-03319-00]"
    assert doc.title_unverified is False
    assert doc.tipo == "Auto"
    assert doc.especialidad == "Civil"
    assert doc.seccion == "Sala de Casación Civil"
    assert doc.f_public == "2026-11-06"
    assert doc.f_providencia == "2026-11-06"
    assert doc.link == {"url": _url_descarga(_UBICACION_REAL), "method": "GET"}
    assert doc.save_path == "CSJ/SCC/AC7263-2026 [2026-03319-00](extension)"
    assert doc.source == "CSJ"


def test_doc_desde_resultado_sin_codigo_marca_titulo_por_verificar():
    doc = _doc_desde_resultado(_resultado(Nombre="doc", Numerador=""))
    assert doc.title == "doc_2026"
    assert doc.title_unverified is True


def test_doc_desde_resultado_usa_numerador_si_el_nombre_no_calza():
    doc = _doc_desde_resultado(_resultado(Nombre="(3)", Numerador="AL12909-2026"))
    assert doc.title == "AL12909-2026"
    assert doc.title_unverified is False


def test_doc_desde_resultado_sin_ubicacion_lanza_keyerror():
    item = _resultado()
    del item["Ubicacion"]
    with pytest.raises(KeyError):
        _doc_desde_resultado(item)


# --- scrap() sobre Ojeador ---------------------------------------------------

_SEARCH = "https://buscadorjurisprudenciabackend.cortesuprema.gov.co/search/"


def _params(fini, ffin, page):
    return {
        "query_text": "", "orden": "recientes", "limit": "100",
        "page": str(page), "fechaInicio": fini, "fechaFin": ffin,
    }


def _docs(n, fecha="2026-10-15", desde=0):
    return [
        _resultado(
            id=str(desde + k), Nombre=f"AC{desde + k}-2026", Numerador=f"AC{desde + k}-2026",
            FechaConsolidacionFirma=fecha, Ubicacion=f"SALAS/CIVIL/2026/x/AC{desde + k}-2026.docx",
        )
        for k in range(n)
    ]


def _pagina(rsps, fini, ffin, page, docs, num_found, status=200):
    rsps.add(
        responses.GET, _SEARCH, status=status,
        json={"numFound": num_found, "returned": len(docs), "docs": docs},
        match=[matchers.query_param_matcher(_params(fini, ffin, page))],
    )


@responses.activate
def test_scrap_pagina_hasta_completar_el_mes():
    _pagina(responses, "2026-10-01", "2026-10-31", 1, _docs(100), 230)
    _pagina(responses, "2026-10-01", "2026-10-31", 2, _docs(100, desde=100), 230)
    _pagina(responses, "2026-10-01", "2026-10-31", 3, _docs(30, desde=200), 230)

    docs = ScrapCorteSuprema().scrap("2026-10-01", "2026-10-31")

    assert len(docs) == 230
    assert len(responses.calls) == 3


@responses.activate
def test_scrap_para_en_page_por_100_igual_a_numfound():
    _pagina(responses, "2026-10-01", "2026-10-31", 1, _docs(100), 200)
    _pagina(responses, "2026-10-01", "2026-10-31", 2, _docs(100, desde=100), 200)

    docs = ScrapCorteSuprema().scrap("2026-10-01", "2026-10-31")

    assert len(docs) == 200
    assert len(responses.calls) == 2  # no pide una tercera página vacía


@responses.activate
def test_scrap_parte_el_rango_en_meses():
    _pagina(responses, "2026-01-15", "2026-01-31", 1, _docs(1, fecha="2026-01-20"), 1)
    _pagina(responses, "2026-02-01", "2026-02-28", 1, _docs(1, fecha="2026-02-20", desde=1), 1)
    _pagina(responses, "2026-03-01", "2026-03-10", 1, _docs(1, fecha="2026-03-05", desde=2), 1)

    docs = ScrapCorteSuprema().scrap("2026-01-15", "2026-03-10")

    assert [d.f_public for d in docs] == ["2026-01-20", "2026-02-20", "2026-03-05"]


@responses.activate
def test_scrap_mes_con_mas_de_10000_se_parte_por_dias():
    _pagina(responses, "2026-10-01", "2026-10-02", 1, _docs(100), 12000)
    _pagina(responses, "2026-10-01", "2026-10-01", 1, _docs(1, fecha="2026-10-01"), 1)
    _pagina(responses, "2026-10-02", "2026-10-02", 1, _docs(1, fecha="2026-10-02", desde=1), 1)

    docs = ScrapCorteSuprema().scrap("2026-10-01", "2026-10-02")

    assert sorted(d.f_public for d in docs) == ["2026-10-01", "2026-10-02"]


@responses.activate
def test_scrap_un_4xx_avisa_y_sigue_con_el_siguiente_mes():
    _pagina(responses, "2026-01-01", "2026-01-31", 1, [], 0, status=400)
    _pagina(responses, "2026-02-01", "2026-02-28", 1, _docs(1, fecha="2026-02-10"), 1)
    avisos = []

    docs = ScrapCorteSuprema().scrap("2026-01-01", "2026-02-28", on_progress=avisos.append)

    assert [d.f_public for d in docs] == ["2026-02-10"]
    assert any("2026-01-01" in a and "400" in a for a in avisos)
    assert len(responses.calls) == 2  # el 4xx no se reintenta


@responses.activate
def test_scrap_reintenta_5xx_y_respuesta_que_no_es_json():
    m = [matchers.query_param_matcher(_params("2026-10-01", "2026-10-31", 1))]
    responses.add(responses.GET, _SEARCH, status=503, match=m)
    responses.add(responses.GET, _SEARCH, status=200, body="<html>mantenimiento</html>", match=m)
    responses.add(responses.GET, _SEARCH, json={"numFound": 1, "returned": 1, "docs": _docs(1)}, match=m)

    docs = ScrapCorteSuprema().scrap("2026-10-01", "2026-10-31")

    assert len(docs) == 1


@responses.activate
def test_scrap_se_rinde_tras_3_intentos_y_lo_avisa():
    for _ in range(3):
        _pagina(responses, "2026-10-01", "2026-10-31", 1, [], 0, status=502)
    avisos = []

    docs = ScrapCorteSuprema().scrap("2026-10-01", "2026-10-31", on_progress=avisos.append)

    assert docs == []
    assert len(responses.calls) == 3
    assert any("3 intentos" in a for a in avisos)


@responses.activate
def test_scrap_descarta_fecha_fuera_de_rango_con_aviso():
    docs_sitio = _docs(1, fecha="2026-10-15") + _docs(1, fecha="2026-09-30", desde=1)
    _pagina(responses, "2026-10-01", "2026-10-31", 1, docs_sitio, 2)
    avisos = []

    docs = ScrapCorteSuprema().scrap("2026-10-01", "2026-10-31", on_progress=avisos.append)

    assert [d.f_public for d in docs] == ["2026-10-15"]
    assert any("fuera del rango" in a for a in avisos)


@responses.activate
def test_scrap_deduplica_por_id():
    repetidos = _docs(1) + _docs(1)
    _pagina(responses, "2026-10-01", "2026-10-31", 1, repetidos, 2)

    assert len(ScrapCorteSuprema().scrap("2026-10-01", "2026-10-31")) == 1


@responses.activate
def test_scrap_resultado_sin_ubicacion_se_omite_sin_cortar_la_corrida():
    malos = _docs(2)
    del malos[0]["Ubicacion"]
    _pagina(responses, "2026-10-01", "2026-10-31", 1, malos, 2)
    avisos = []

    docs = ScrapCorteSuprema().scrap("2026-10-01", "2026-10-31", on_progress=avisos.append)

    assert len(docs) == 1
    assert any("campo inesperado" in a for a in avisos)


@responses.activate
def test_scrap_respeta_limit():
    _pagina(responses, "2026-10-01", "2026-10-31", 1, _docs(100), 230)

    assert len(ScrapCorteSuprema().scrap("2026-10-01", "2026-10-31", limit=5)) == 5


@responses.activate
def test_scrap_respeta_stop_event():
    import threading

    parar = threading.Event()
    parar.set()

    assert ScrapCorteSuprema().scrap("2026-10-01", "2026-10-31", stop_event=parar) == []
    assert len(responses.calls) == 0


def test_atributos_de_la_familia():
    assert ScrapCorteSuprema.scheduled_min_lookback_days == 45
    assert ScrapCorteSuprema.checks_for_republication is False
    assert ScrapCorteSuprema.filters_by_publication_date is False


@responses.activate
def test_scrap_deduplica_copias_de_ojeador_con_la_misma_ubicacion():
    # Real (nov 2026): Ojeador indexa SP754-2026(64046) tres veces, con ids
    # distintos y la misma Ubicacion (mismo archivo).
    copias = [
        _resultado(id=i, Nombre="SP754-2026(64046)", Numerador="SP754-2026", Sala="PENAL",
                   Especialidad="PENAL", TipoDeProvidencia="SENTENCIA", FechaConsolidacionFirma="2026-10-15",
                   Ubicacion="SALAS/PENAL/2026/SP754-2026(64046).docx")
        for i in ("1148912", "1122109", "1128418")
    ]
    _pagina(responses, "2026-10-01", "2026-10-31", 1, copias, 3)

    docs = ScrapCorteSuprema().scrap("2026-10-01", "2026-10-31")

    assert [d.title for d in docs] == ["SP754-2026(64046)"]


@responses.activate
def test_scrap_no_emite_dos_documentos_con_la_misma_carpeta_y_titulo():
    # Revisión final: dos rutas distintas con el mismo Nombre irían al mismo
    # archivo en el almacenamiento (el segundo pisaría al primero).
    a = _resultado(id="1", Ubicacion="SALAS/CIVIL/2026/x/AC7263-2026 [2026-03319-00].docx", FechaConsolidacionFirma="2026-10-15")
    b = _resultado(id="2", Ubicacion="SALAS/CIVIL/2026/y/AC7263-2026 [2026-03319-00].docx", FechaConsolidacionFirma="2026-10-15")
    _pagina(responses, "2026-10-01", "2026-10-31", 1, [a, b], 2)
    avisos = []

    docs = ScrapCorteSuprema().scrap("2026-10-01", "2026-10-31", on_progress=avisos.append)

    assert len(docs) == 1
    assert any("mismo nombre" in m for m in avisos)


@responses.activate
def test_scrap_resultados_sin_id_no_se_descartan_entre_si():
    # Revisión final: sin id, todos compartían la clave "id:None" y del
    # segundo en adelante se perdían sin aviso.
    sin_id = _docs(3)
    for item in sin_id:
        del item["id"]
    _pagina(responses, "2026-10-01", "2026-10-31", 1, sin_id, 3)

    assert len(ScrapCorteSuprema().scrap("2026-10-01", "2026-10-31")) == 3
