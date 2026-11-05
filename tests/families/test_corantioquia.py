import datetime
import threading

import responses
from responses import matchers

from core.scrapers.families.corantioquia import (
    _ANIO_MINIMO,
    _SOURCE,
    _URL,
    _fecha,
    _titulo,
    ScrapCorantioquia,
)
from core.scrapers.registry import FAMILY_REGISTRY


def _boletin_idx(numero, nombre):
    return {"numero": numero, "agno": 0, "documentos": [], "mes": "", "nombre": nombre}


def _indice(*boletines_por_anio, status=200):
    """boletines_por_anio: (año, [(numero, nombre), ...])."""
    cuerpo = {"limit": 0, "error": "", "boletines": {
        str(anio): [_boletin_idx(n, nom) for n, nom in lista] for anio, lista in boletines_por_anio
    }}
    responses.add(
        responses.GET, _URL, status=status, json=cuerpo if status == 200 else {"error": "x"},
        match=[matchers.query_param_matcher({"ctrlAction": "C", "pagina": "1", "doAction": "A"})],
    )


def _documento(doc, radicado="040-RES2610-3892", fecha="09 de Octubre de 2026", tipo="Resolución",
               subtipo="Por la cual se archiva un expediente", anexos=0):
    # Copia de un documento real del boletín 2876.
    d = {
        "validarSeguridad": True, "cantidadAnexos": anexos, "sirenaRadicado": radicado,
        "fechaRadicacion": fecha, "tipo": {"nombre": tipo},
        "registroEnSolicitudes": 0, "seNotifica": False, "sePublica": False, "tieneRecurso": False,
        "linkDescarga": f"https://sirena.corantioquia.gov.co/esirena/CtrlPublicaciones?ctrlAction=D&doc={doc}",
    }
    if subtipo is not None:
        d["subtipo"] = {"nombre": subtipo}
    return d


def _pagina(numero, pagina, *documentos, status=200, anio="2026"):
    cuerpo = {"limit": 15, "error": "", "boletines": {}}
    if documentos:
        cuerpo["boletines"] = {anio: {str(numero): {
            "agno": int(anio), "numero": numero, "nombre": "x", "mes": "x", "pagina": pagina,
            "documentos": list(documentos),
        }}}
    responses.add(
        responses.GET, _URL, status=status, json=cuerpo if status == 200 else {"error": "x"},
        match=[matchers.query_param_matcher({"ctrlAction": "C", "numero": str(numero), "pagina": str(pagina)})],
    )


def _scrap(fini="2026-10-01", ffin="2026-10-31", **kw):
    return ScrapCorantioquia().scrap(fini, ffin, **kw)


def test_source_registro_y_atributos():
    assert _SOURCE == "Corporación Autónoma Regional del Centro de Antioquia"
    assert _ANIO_MINIMO == 2025
    assert FAMILY_REGISTRY["corantioquia"] is ScrapCorantioquia
    assert ScrapCorantioquia.filters_by_publication_date is True
    assert ScrapCorantioquia.scheduled_min_lookback_days is None


def test_titulo_desde_el_radicado():
    assert _titulo("R", "040-RES2610-3892") == ("R_CORANT_3892_2026", True)
    assert _titulo("R", "160TH-RES2501-80") == ("R_CORANT_0080_2025", True)
    assert _titulo("A", "180-ACU2610-84") == ("A_CORANT_0084_2026", True)
    assert _titulo("R", "160SAE-RES2412-5845") == ("R_CORANT_5845_2024", True)
    assert _titulo("R", "130SAE-1105-131") == ("R_CORANT_130SAE-1105-131", False)


def test_fechas_en_espanol():
    assert _fecha("09 de Octubre de 2026") == datetime.date(2026, 10, 9)
    assert _fecha("2876 de 14 de octubre de 2026") == datetime.date(2026, 10, 14)
    assert _fecha("sin fecha") is None


@responses.activate
def test_documento_completo():
    _indice((2026, [(2876, "2876 de 14 de octubre de 2026")]))
    _pagina(2876, 1, _documento(2483007))

    [doc] = _scrap()

    assert doc.title == "R_CORANT_3892_2026"
    assert doc.tipo == "Resolución"
    assert doc.f_public == "2026-10-14"
    assert doc.f_providencia == "2026-10-09"
    assert doc.detalle == "040-RES2610-3892 — Por la cual se archiva un expediente"
    assert doc.link == {
        "url": "https://sirena.corantioquia.gov.co/esirena/CtrlPublicaciones?ctrlAction=D&doc=2483007",
        "method": "GET", "verify": False,
    }
    assert doc.save_path == f"{_SOURCE}/2026-10-14/Resolución/R_CORANT_3892_2026(extension)"


@responses.activate
def test_solo_se_piden_boletines_del_rango_y_desde_el_piso():
    _indice(
        (2026, [(2876, "2876 de 14 de octubre de 2026"), (2900, "2900 de 20 de noviembre de 2026")]),
        (2025, [(2500, "2500 de 02 de enero de 2025")]),
        (2024, [(2400, "2400 de 30 de diciembre de 2024")]),
    )
    _pagina(2500, 1, _documento(1, radicado="040-RES2501-1", fecha="02 de Enero de 2025"))
    _pagina(2876, 1, _documento(2))

    docs = _scrap("2023-01-01", "2026-10-31")

    assert [d.f_public for d in docs] == ["2025-01-02", "2026-10-14"]
    pedidos = [c.request.url for c in responses.calls]
    assert not any("numero=2400" in u or "numero=2900" in u for u in pedidos)


@responses.activate
def test_paginacion():
    _indice((2026, [(2876, "2876 de 14 de octubre de 2026")]))
    _pagina(2876, 1, *[_documento(i, radicado=f"040-RES2610-{i}") for i in range(15)])
    _pagina(2876, 2, _documento(99, radicado="040-RES2610-99"))

    assert len(_scrap()) == 16
    assert not any("pagina=3" in c.request.url for c in responses.calls)


@responses.activate
def test_pagina_vacia_corta():
    _indice((2026, [(2876, "2876 de 14 de octubre de 2026")]))
    _pagina(2876, 1, *[_documento(i, radicado=f"040-RES2610-{i}") for i in range(15)])
    _pagina(2876, 2)

    assert len(_scrap()) == 15


@responses.activate
def test_solo_resoluciones_y_acuerdos():
    _indice((2026, [(2876, "2876 de 14 de octubre de 2026")]))
    _pagina(
        2876, 1,
        _documento(1, radicado="160HX-ADM2610-8330", tipo="Acto administrativo"),
        _documento(2, radicado="040-NAV2610-1", tipo="Notificación por aviso"),
        _documento(3, radicado="040-EDI2610-1", tipo="Edicto"),
        _documento(4, radicado="180-ACU2610-84", tipo="Acuerdo"),
        _documento(5),
    )

    assert [(d.title, d.tipo) for d in _scrap()] == [
        ("A_CORANT_0084_2026", "Acuerdo"), ("R_CORANT_3892_2026", "Resolución"),
    ]


@responses.activate
def test_piso_por_fecha_del_acto_y_acto_atrasado_entra():
    _indice((2026, [(2876, "2876 de 14 de octubre de 2026")]))
    _pagina(
        2876, 1,
        _documento(1, radicado="040-RES2303-10", fecha="03 de Marzo de 2023"),
        _documento(2, radicado="040-RES2503-11", fecha="03 de Marzo de 2025"),
    )

    [doc] = _scrap()

    assert doc.title == "R_CORANT_0011_2025"
    assert doc.f_public == "2026-10-14"
    assert doc.f_providencia == "2025-03-03"


@responses.activate
def test_radicado_fuera_del_patron_avisa():
    _indice((2026, [(2876, "2876 de 14 de octubre de 2026")]))
    _pagina(2876, 1, _documento(1, radicado="130SAE-15", fecha="03 de Marzo de 2025"))
    avisos = []

    [doc] = _scrap(on_progress=avisos.append)

    assert doc.title == "R_CORANT_130SAE-15"
    assert any("fuera del patrón" in a for a in avisos)


@responses.activate
def test_subtipo_ausente_y_fecha_ilegible():
    _indice((2026, [(2876, "2876 de 14 de octubre de 2026")]))
    _pagina(
        2876, 1,
        _documento(1, subtipo=None),
        _documento(2, radicado="040-RES2610-1", fecha="sin fecha"),
    )
    avisos = []

    [doc] = _scrap(on_progress=avisos.append)

    assert doc.detalle == "040-RES2610-3892"
    assert any("sin fecha legible" in a for a in avisos)


@responses.activate
def test_dedup_por_doc():
    _indice((2026, [(2876, "2876 de 14 de octubre de 2026"), (2877, "2877 de 15 de octubre de 2026")]))
    _pagina(2876, 1, _documento(2483007))
    _pagina(2877, 1, _documento(2483007))

    assert len(_scrap()) == 1


@responses.activate
def test_falla_del_indice():
    _indice(status=500)
    avisos = []

    assert _scrap(on_progress=avisos.append) == []
    assert any("índice de boletines" in a for a in avisos)


@responses.activate
def test_falla_de_un_boletin_sigue_con_el_siguiente():
    _indice((2026, [(2876, "2876 de 14 de octubre de 2026"), (2877, "2877 de 15 de octubre de 2026")]))
    _pagina(2876, 1, status=500)
    _pagina(2877, 1, _documento(5))
    avisos = []

    assert [d.f_public for d in _scrap(on_progress=avisos.append)] == ["2026-10-15"]
    assert any("boletín 2876" in a for a in avisos)


@responses.activate
def test_limit_y_stop_event():
    _indice((2026, [(2876, "2876 de 14 de octubre de 2026")]))
    _pagina(2876, 1, _documento(1, radicado="040-RES2610-1"), _documento(2, radicado="040-RES2610-2"))

    assert len(_scrap(limit=1)) == 1

    parar = threading.Event()
    parar.set()
    assert _scrap(stop_event=parar) == []


@responses.activate
def test_resolucion_con_tilde_descompuesta_o_en_mayusculas_no_se_pierde():
    # Hallazgo de la revisión del PR #110: el tipo se comparaba letra por letra
    # con "Resolución". Si el sitio manda la tilde descompuesta ("o" + U+0301,
    # se ve igual en pantalla) o el texto en mayúsculas, la resolución se
    # descartaba sin aviso. Es el mismo error que costó 3 resoluciones en
    # MinEducación (PR #104).
    _indice((2026, [(2876, "2876 de 14 de octubre de 2026")]))
    _pagina(
        2876, 1,
        _documento(1, radicado="040-RES2610-3892", tipo="Resolución"),
        _documento(2, radicado="040-RES2610-3893", tipo="RESOLUCIÓN"),
        _documento(3, radicado="180-ACU2610-84", tipo=" acuerdo "),
    )

    assert [(d.title, d.tipo) for d in _scrap()] == [
        ("R_CORANT_3892_2026", "Resolución"),
        ("R_CORANT_3893_2026", "Resolución"),
        ("A_CORANT_0084_2026", "Acuerdo"),
    ]
