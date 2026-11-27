import json
import threading

import pytest
import responses

from core.scrapers.families.adres import (
    _BASE_URL,
    _SOURCE,
    ScrapADRES,
    bloques_doclist,
    numero_y_anio,
)
from core.scrapers.registry import FAMILY_REGISTRY

# --- Fragmentos reales del sitio (Next.js + Payload, RSC) ----------------------
# Filas copiadas tal cual del payload de https://www.adres.gov.co/normativa/…
# (2026-11-26). El payload envuelve cada bloque así:
#   …{"label":"docList",…,{"documents":[…],"heading":"ADRES",…}
# y el "heading" va DESPUÉS del arreglo.

_R_199531 = {
    "id": "6b0787a6ba1661fff70c3ece", "url": "", "date": "01/10/2026",
    "file": {"id": 7454, "alt": "Resolucion_199531_de_2026 ", "url": "/api/media/file/Resolucion_199531_de_2026.pdf",
             "filename": "Resolucion_199531_de_2026.pdf", "mimeType": "application/pdf", "width": None, "height": None},
    "meta": [{"id": "6b0787a6ba1661fff70c3ecf", "label": "Fecha", "value": "01/10/2026"},
             {"id": "6b0787a6ba1661fff70c3ed0", "label": "Descripción",
              "value": "Por medio de la cual Se adiciona a la Resolución 1012-2022 en materia de delegación de funciones y se dictan otras disposiciones"}],
    "name": "Resolucion_199531_de_2026 ", "type": "pdf",
    "description": "Se adiciona a la Resolución 1012-2022 en materia de delegación de funciones y se dictan otras disposiciones",
}
_R_12758 = {
    "id": "ce91e9a9d1f183d538becf5d", "url": "/api/media/file/Resoluci%C3%B3n%2012758%20de%202023.pdf", "date": "",
    "file": {"id": 5067, "alt": "Resolución 12758 de 2023", "url": "/api/media/file/Resoluci%C3%B3n%2012758%20de%202023.pdf",
             "filename": "Resolución 12758 de 2023.pdf", "mimeType": "application/pdf", "width": None, "height": None},
    "meta": [{"id": "4d1d401917bdb50d13039dc4", "label": "Fecha", "value": "01/09/2023"},
             {"id": "6c08d958eb08a47566105d2d", "label": "Descripción", "value": "Por la cual se adoptan las condiciones operativas …"}],
    "name": "Resolución 12758 de 2023", "type": "pdf", "description": "",
}
_R_00012758 = {
    "id": "2c99c47b43212ff384f0efa8", "url": "/api/media/file/Resoluci%C3%B3n%2000012758.pdf", "date": "",
    "file": {"id": 5068, "alt": "Resolución 00012758 ", "url": "/api/media/file/Resoluci%C3%B3n%2000012758.pdf",
             "filename": "Resolución 00012758.pdf", "mimeType": "application/pdf", "width": None, "height": None},
    "meta": [{"id": "35167217eba0f2a4d2897146", "label": "Fecha", "value": "29/08/2023"},
             {"id": "07e21b9c4a2135034347e697", "label": "Descripción", "value": "Por la cual se adoptan las condiciones operativas …"}],
    "name": "Resolución 00012758 ", "type": "pdf", "description": "",
}
_R_2707 = {
    "id": "2313a3b5328d2d9feaba52a7", "url": "/api/media/file/Resoluci%C3%B3n%20n%C3%BAmero%202707%20de%202020.pdf", "date": "",
    "file": {"id": 5140, "alt": "Resolución número 2707 de 2020",
             "url": "/api/media/file/Resoluci%C3%B3n%20n%C3%BAmero%202707%20de%202020.pdf",
             "filename": "Resolución número 2707 de 2020.pdf", "mimeType": "application/pdf", "width": None, "height": None},
    "meta": [{"id": "d41fead490df6da70e6fb076", "label": "Fecha", "value": "29/05/2021"},
             {"id": "5a7ea1d36c8db098e1d9bcd8", "label": "Descripción",
              "value": "Por la cual se adoptan las especificaciones técnicas y operativas para el proceso de auditoría …"}],
    "name": "Resolución número 2707 de 2020", "type": "pdf", "description": "",
}
_R_1769_RUTA_VIEJA = {
    "id": "6a5817061356c15068513f29", "url": "/normativa/Documents/Resolucion-1769-2024.pdf", "date": "",
    "meta": [{"id": "6a5817061356c15068513f27", "label": "Fecha", "value": "18/09/2024"},
             {"id": "6a5817061356c15068513f28", "label": "Descripción",
              "value": "​Por medio de la cual se asignan recursos a los departamentos ​"}],
    "name": "1769", "type": "pdf", "description": "",
}
_R_2707_VLEX = {
    "id": "6a5817061356c15068513f2f",
    "url": "//diario-oficial.vlex.com.co/vid/resolucion-numero-2707-2020-844949273#:~:text=Junio%20de%202020",
    "date": "",
    "meta": [{"id": "6a5817061356c15068513f2d", "label": "Fecha", "value": "29/05/2020"},
             {"id": "6a5817061356c15068513f2e", "label": "Descripción", "value": "​Por la cual se adoptan …"}],
    "name": "2707", "type": "pdf", "description": "",
}
_MINSALUD_1620 = {
    "id": "6a5817061356c15068513f62", "url": "//www.minsalud.gov.co/Normatividad_Nuevo/Forms/DispForm.aspx?ID=6264", "date": "",
    "meta": [{"id": "6a5817061356c15068513f60", "label": "Fecha", "value": "05/10/2020"},
             {"id": "6a5817061356c15068513f61", "label": "Descripción", "value": "Por la cual se establece …"}],
    "name": "1620", "type": "pdf", "description": "",
}


def _fila(name, fecha, archivo=None, description="Epígrafe"):
    archivo = archivo or f"{name.strip()}.pdf"
    return {
        "id": "x", "url": "", "date": "",
        "file": {"id": 1, "alt": name, "url": f"/api/media/file/{archivo}", "filename": archivo,
                 "mimeType": "application/pdf", "width": None, "height": None},
        "meta": [{"id": "a", "label": "Fecha", "value": fecha}, {"id": "b", "label": "Descripción", "value": description}],
        "name": name, "type": "pdf", "description": description,
    }


def _bloque(heading, documents, n):
    return (
        f'["$","$L2c","{n}",{{"label":"docList","verbose":false,"children":["$","$L2d",null,'
        f'{{"visibility":{{"visible":true}},"children":["$","$L2e",null,{{'
        f'"documents":{json.dumps(documents, ensure_ascii=False)},"heading":"{heading}","collapsible":"closed",'
        f'"nested":false,"searchable":true,"pageSize":30,"searchPlaceholder":"$undefined","sort":"date-desc"}}]}}]}}]'
    )


def _pagina(*bloques):
    """HTML con el payload RSC partido en varios self.__next_f.push, como el
    sitio real (un bloque puede quedar cortado entre dos push)."""
    texto = "1:[" + ",".join(_bloque(h, docs, i) for i, (h, docs) in enumerate(bloques)) + "]\n"
    mitad = len(texto) // 2
    partes = [texto[:mitad], texto[mitad:]]
    scripts = "".join(f"<script>self.__next_f.push([1,{json.dumps(p)}])</script>" for p in partes)
    return f"<!DOCTYPE html><html><head></head><body><div>Normativa</div><script>(self.__next_f=self.__next_f||[]).push([0])</script>{scripts}</body></html>"


_URL = {s: f"{_BASE_URL}/normativa/{s}" for s in ("resoluciones", "circulares", "acuerdos")}


def _registrar(rsps, resoluciones=(), circulares=(), acuerdos=()):
    for seccion, docs in (("resoluciones", resoluciones), ("circulares", circulares), ("acuerdos", acuerdos)):
        rsps.add(responses.GET, _URL[seccion], body=_pagina(("ADRES", list(docs)), ("Ministerio de Salud", [_MINSALUD_1620])))


def _scrap(fini="2015-01-01", ffin="2026-12-31", **kw):
    avisos = []
    docs = ScrapADRES().scrap(fini, ffin, on_progress=avisos.append, **kw)
    return docs, avisos


# --- 1. Lectura del RSC --------------------------------------------------------

def test_bloques_doclist_toma_el_heading_que_sigue_al_arreglo():
    html = _pagina(("ADRES", [_R_199531, _R_12758]), ("Ministerio de Salud", [_MINSALUD_1620]))
    bloques = bloques_doclist(html)
    assert [(h, [d["name"] for d in docs]) for h, docs in bloques] == [
        ("ADRES", ["Resolucion_199531_de_2026 ", "Resolución 12758 de 2023"]),
        ("Ministerio de Salud", ["1620"]),
    ]


def test_bloques_doclist_sin_rsc_devuelve_vacio():
    assert bloques_doclist("<html><body>404</body></html>") == []


# --- 2. Número y año -----------------------------------------------------------

@pytest.mark.parametrize("seccion,name,esperado", [
    ("resoluciones", "Resolucion_199531_de_2026 ", ("199531", 2026)),
    ("resoluciones", "Resolucion_0128021_de_2026", ("0128021", 2026)),
    ("resoluciones", "RESOLUCION_0000009_2026", ("0000009", 2026)),
    ("resoluciones", "Res.146756-2024", ("146756", 2024)),
    ("resoluciones", "RESOLUCION No 0089666 de 2024", ("0089666", 2024)),
    ("resoluciones", "Resolucion_No-0170665_de_2024", ("0170665", 2024)),
    ("resoluciones", "Resolucón número 388 de 2020", ("388", 2020)),
    ("resoluciones", "Resolución npumero 2752 de 2020", ("2752", 2020)),
    ("resoluciones", "ADRES - Resolución 41656 de 2019", ("41656", 2019)),
    ("resoluciones", "RESOLUCIÓN NÚMERO 552 DE 2021", ("552", 2021)),
    ("resoluciones", "Resolución número 668 del 2018", ("668", 2018)),
    ("resoluciones", "Resolución número 007 de 2019", ("007", 2019)),
    ("resoluciones", "Resolución 1659", ("1659", None)),
    ("resoluciones", "1431", ("1431", None)),
    ("resoluciones", "RESOLUCION 3341 Reemplaza 1423", ("3341", None)),
    ("resoluciones", "Resolucion_2935_Alcance_1431 de 2020 v2707", ("2935", None)),
    ("circulares", "0000004_2026", ("0000004", 2026)),
    ("circulares", "0000011_de_2025", ("0000011", 2025)),
    ("circulares", "0000021-de-2024", ("0000021", 2024)),
    ("circulares", "000008", ("000008", None)),
    # La fecha pegada al número no es el año del nombre: no se parte el número.
    ("circulares", "0000014_24_06_2024", ("0000014", None)),
    ("circulares", "0000007_29-04-2024", ("0000007", None)),
    ("acuerdos", "Acuerdo_numero_497_de_2017", ("497", 2017)),
    ("acuerdos", "Acuerdo_numero_0000002_de_2020", ("0000002", 2020)),
    ("acuerdos", "Acuerdo_0001_de_2024", ("0001", 2024)),
    ("acuerdos", "Acuerdo_No_1", ("1", None)),
])
def test_numero_y_anio(seccion, name, esperado):
    assert numero_y_anio(seccion, name) == esperado


def test_numero_y_anio_fuera_de_patron():
    assert numero_y_anio("resoluciones", "Instructivo giro directo") is None
    assert numero_y_anio("acuerdos", "Resolución 1 de 2020") is None


@responses.activate
def test_scrap_titulos_y_campos():
    _registrar(
        responses,
        resoluciones=[_R_199531, _fila("Resolución 1659", "12/04/2019")],
        circulares=[_fila("0000004_2026", "01/06/2026"), _fila("000008", "15/03/2022")],
        acuerdos=[_fila("Acuerdo_numero_497_de_2017", "20/12/2017")],
    )
    docs, avisos = _scrap()
    por_titulo = {d.title: d for d in docs}
    assert set(por_titulo) == {
        "R_ADRES_199531_2026", "R_ADRES_1659_2019", "C_ADRES_0000004_2026", "C_ADRES_000008_2022", "A_ADRES_497_2017",
    }
    r = por_titulo["R_ADRES_199531_2026"]
    assert r.source == _SOURCE
    assert r.tipo == "Resolución"
    assert r.f_public == r.f_providencia == "2026-10-01"
    assert r.link == {"url": f"{_BASE_URL}/api/media/file/Resolucion_199531_de_2026.pdf", "method": "GET"}
    assert r.detalle.startswith("Se adiciona a la Resolución 1012-2022")
    assert r.save_path == f"{_SOURCE}/2026-10-01/Resolución/R_ADRES_199531_2026(extension)"
    assert r.title_unverified is False
    assert por_titulo["C_ADRES_000008_2022"].tipo == "Circular"
    assert por_titulo["A_ADRES_497_2017"].tipo == "Acuerdo"
    assert not [a for a in avisos if "Error" in a]


@responses.activate
def test_scrap_detalle_de_meta_si_description_vacia_sin_espacios_de_ancho_cero():
    _registrar(responses, resoluciones=[_R_1769_RUTA_VIEJA])
    docs, _ = _scrap()
    assert docs[0].detalle == "Por medio de la cual se asignan recursos a los departamentos"


# --- 3. Año del nombre distinto del de la Fecha ------------------------------

@responses.activate
def test_anio_del_nombre_distinto_corrige_la_fecha():
    _registrar(responses, resoluciones=[_R_2707])
    docs, avisos = _scrap()
    [d] = docs
    assert d.title == "R_ADRES_2707_2020"
    assert d.f_public == d.f_providencia == "2020-05-29"
    assert d.title_unverified is True
    assert any("29/05/2021" in a and "2020-05-29" in a for a in avisos)


@responses.activate
def test_anio_del_nombre_distinto_29_de_febrero_va_al_1_de_enero():
    _registrar(responses, resoluciones=[_fila("Resolución 55 de 2023", "29/02/2024")])
    [d], _ = _scrap()
    assert d.title == "R_ADRES_55_2023"
    assert d.f_public == "2023-01-01"
    assert d.title_unverified is True


# --- 4. Nombre fuera de patrón ----------------------------------------------

@responses.activate
def test_nombre_fuera_de_patron_queda_sin_verificar():
    _registrar(responses, acuerdos=[_fila("Instructivo giro (directo)", "03/03/2023")])
    docs, avisos = _scrap()
    [d] = docs
    assert d.title == "Instructivo_giro_directo"
    assert d.title_unverified is True
    assert d.f_public == "2023-03-03"
    assert any("Instructivo giro (directo)" in a for a in avisos)


# --- 5. Enlaces ajenos y rutas viejas ---------------------------------------

@responses.activate
def test_dominio_ajeno_se_descarta_y_ruta_vieja_se_rehace():
    _registrar(responses, resoluciones=[_R_2707_VLEX, _R_1769_RUTA_VIEJA])
    docs, avisos = _scrap()
    [d] = docs
    assert d.title == "R_ADRES_1769_2024"
    assert d.link["url"] == f"{_BASE_URL}/api/media/file/Resolucion-1769-2024.pdf"
    assert any("/normativa/Documents/Resolucion-1769-2024.pdf" in a for a in avisos)


@responses.activate
def test_bloque_ministerio_de_salud_se_ignora():
    _registrar(responses)
    docs, _ = _scrap()
    assert docs == []


# --- 6. Duplicados ------------------------------------------------------------

@responses.activate
def test_duplicado_se_queda_la_fecha_mas_antigua():
    _registrar(responses, resoluciones=[_R_12758, _R_00012758])
    docs, avisos = _scrap()
    [d] = docs
    assert d.title == "R_ADRES_00012758_2023"
    assert d.f_public == "2023-08-29"
    assert d.link["url"].endswith("Resoluci%C3%B3n%2000012758.pdf")
    assert any("repetid" in a.lower() for a in avisos)


@responses.activate
def test_mismo_numero_escrito_distinto_es_duplicado():
    _registrar(responses, resoluciones=[_fila("Resolucion 02418 de 2020", "10/03/2020"),
                                        _fila("Resolucion 2418 de 2020", "10/03/2020", archivo="otra.pdf")])
    docs, _ = _scrap()
    assert len(docs) == 1


@responses.activate
def test_mismo_numero_en_secciones_distintas_no_es_duplicado():
    _registrar(responses, resoluciones=[_fila("Resolucion 5 de 2020", "10/03/2020")],
               circulares=[_fila("5_2020", "10/03/2020")])
    docs, _ = _scrap()
    assert {d.title for d in docs} == {"R_ADRES_5_2020", "C_ADRES_5_2020"}


# --- 7. Filtro, piso y ajustes de la familia ---------------------------------

@responses.activate
def test_filtro_por_fecha_y_piso():
    _registrar(responses, resoluciones=[
        _fila("Resolucion 1 de 2024", "15/01/2024"),
        _fila("Resolucion 2 de 2024", "15/06/2024"),
        _fila("Resolucion 3 de 2014", "15/06/2014"),
    ])
    docs, _ = _scrap("2024-01-01", "2024-03-31")
    assert [d.title for d in docs] == ["R_ADRES_1_2024"]
    docs, _ = _scrap("2000-01-01", "2026-12-31")
    assert {d.title for d in docs} == {"R_ADRES_1_2024", "R_ADRES_2_2024"}


@responses.activate
def test_fecha_ilegible_se_descarta_con_aviso():
    _registrar(responses, resoluciones=[_fila("Resolucion 1 de 2024", "sin fecha")])
    docs, avisos = _scrap()
    assert docs == []
    assert any("Resolucion 1 de 2024" in a for a in avisos)


def test_ajustes_de_la_familia():
    assert ScrapADRES.scheduled_min_lookback_days == 45
    assert ScrapADRES.checks_for_republication is False
    assert ScrapADRES.alerta_margen_dias == 140


def test_registrada_con_su_clave():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["adres"] is ScrapADRES


# --- 8. Sitio cambiado: avisar, no callar ------------------------------------

@responses.activate
def test_pagina_sin_bloque_adres_avisa_error():
    responses.add(responses.GET, _URL["resoluciones"], body="<html><body>Página no encontrada</body></html>")
    responses.add(responses.GET, _URL["circulares"], body=_pagina(("Ministerio de Salud", [_MINSALUD_1620])))
    responses.add(responses.GET, _URL["acuerdos"], body=_pagina(("ADRES", [_fila("Acuerdo_0001_de_2024", "20/12/2024")])))
    docs, avisos = _scrap()
    assert [d.title for d in docs] == ["A_ADRES_0001_2024"]
    errores = [a for a in avisos if "Error" in a]
    assert len(errores) == 2
    assert any("Resoluciones" in a for a in errores) and any("Circulares" in a for a in errores)


# --- 9. Cancelación, límite y sección que falla ------------------------------

@responses.activate
def test_seccion_que_falla_avisa_y_sigue():
    responses.add(responses.GET, _URL["resoluciones"], status=503)
    responses.add(responses.GET, _URL["circulares"], body=_pagina(("ADRES", [_fila("0000004_2026", "01/06/2026")])))
    responses.add(responses.GET, _URL["acuerdos"], body=_pagina(("ADRES", [])))
    docs, avisos = _scrap()
    assert [d.title for d in docs] == ["C_ADRES_0000004_2026"]
    assert any("Error" in a and "Resoluciones" in a for a in avisos)


@responses.activate
def test_limit():
    _registrar(responses, resoluciones=[_fila(f"Resolucion {n} de 2024", "15/01/2024") for n in range(1, 6)])
    docs, _ = _scrap(limit=3)
    assert len(docs) == 3


@responses.activate
def test_stop_event_cancela_antes_de_pedir():
    stop = threading.Event()
    stop.set()
    docs, _ = _scrap(stop_event=stop)
    assert docs == []
    assert len(responses.calls) == 0


# --- 10. User-Agent de navegador ---------------------------------------------

@responses.activate
def test_sesion_con_user_agent_de_navegador():
    _registrar(responses)
    _scrap()
    assert all(c.request.headers["User-Agent"].startswith("Mozilla/5.0") for c in responses.calls)
