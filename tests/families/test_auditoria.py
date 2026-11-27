import threading
from urllib.parse import quote_plus

import pytest
import requests
import responses

from core.scrapers.families.auditoria import (
    _ANIO_MINIMO,
    _BASE,
    _SOURCE,
    _detalle,
    _enlace_limpio,
    _fecha_carga,
    _numero,
    _parse_carpeta,
    _titulo,
    _valor_numero,
    ScrapAuditoria,
)
from core.scrapers.registry import FAMILY_REGISTRY

_DOCS = "https://www.auditoria.gov.co/documents/20123"
_INST = {
    "conceptos-juridicos": "h6j3F7UA67se",
    "resoluciones": "Jjx7nXQXAbGp",
    "circulares": "pgO78BwckEE6",
}


def _url_carpeta(pagina, folder_id):
    return f"{_BASE}{pagina}/-/document_library/{_INST[pagina]}/view/{folder_id}"


def _fila_carpeta(pagina, folder_id, nombre):
    # Copia de una fila real de carpeta del portlet DLPortlet.
    inst = _INST[pagina]
    return (
        f'<li class="list-group-item list-group-item-flex    " data-qa-id="row" data-folder="true" '
        f'data-draggable="false" data-selectable="true" data-folder-id="{folder_id}" '
        f'data-title="{nombre}" data-actions="download" >\n'
        '<div class="autofit-col"><div class="checkbox"><label>'
        f'<input class="entry-selector" name="_com_liferay_document_library_web_portlet_DLPortlet_INSTANCE_{inst}_rowIdsFolder" '
        f'title="Seleccionar" type="checkbox" value="{folder_id}" ></label></div></div>\n'
        '<div class=" autofit-col autofit-col-expand" data-qa-id="rowItemContent"><h2 class="h5">'
        f'<a href="{_url_carpeta(pagina, folder_id)}?_com_liferay_document_library_web_portlet_DLPortlet_INSTANCE_{inst}_redirect=x">'
        f"\n\t\t{nombre}\n</a></h2></div>\n</li>\n"
    )


def _fila_archivo(pagina, folder_id, nombre, uuid, t):
    # Copia de una fila real de archivo: el mismo archivo sale tres veces
    # (miniatura, ficha/vista y descarga con download=true) y el menú de
    # acciones trae un <li> anidado.
    inst = _INST[pagina]
    ruta = f"{_DOCS}/{folder_id}/{quote_plus(nombre)}/{uuid}"
    return (
        f'<li class="list-group-item list-group-item-flex    " data-qa-id="row" data-draggable="false" '
        f'data-selectable="true" data-title="{nombre}" data-actions="download" >\n'
        '<div class=" autofit-col" data-qa-id="rowItemContent">'
        f'<div class="aspect-ratio-bg-cover" style="background-image: url(\'{ruta}?version=1.0&amp;t={t}&amp;documentThumbnail=1\')">'
        f'<img alt="thumbnail" class="sr-only" src="{ruta}?version=1.0&amp;t={t}&amp;documentThumbnail=1"></div></div>\n'
        '<div class=" autofit-col autofit-col-expand" data-qa-id="rowItemContent"><h2 class="h5">'
        f'<a href="{_BASE}{pagina}/-/document_library/{inst}/view_file/3341515?x=1">\n\t\t{nombre}\n</a></h2>'
        f'<a href="{ruta}?version=1.0&amp;t={t}">ver</a></div>\n'
        '<div class=" autofit-col" data-qa-id="rowItemContent"><ul class="dropdown-menu">'
        f'<li class="" role="presentation"><a href="{ruta}?t={t}&amp;download=true" target="_self" '
        'class=" lfr-icon-item taglib-icon">Descargar (486 KB)</a></li></ul></div>\n</li>\n'
    )


def _pagina(pagina, folder_id, filas, intervalo=None):
    # Migas de pan y selector de tamaño (enlaces a la misma carpeta), menú
    # lateral con el Normograma (carpeta 119334) y pie con otros documentos.
    inst = _INST[pagina]
    selector = "".join(
        f'<a href="{_url_carpeta(pagina, folder_id)}?_com_liferay_document_library_web_portlet_DLPortlet_INSTANCE_{inst}_delta={n}">'
        f"{n} Elementos por página</a>"
        for n in (5, 10, 20)
    )
    pag = f'<p class="pagination-results">\n\t\t\tMostrando el intervalo {intervalo[0]} - {intervalo[1]} de {intervalo[2]} resultados.\n\t\t</p>' if intervalo else ""
    return (
        "<html><body>"
        f'<nav><a href="{_url_carpeta(pagina, folder_id)}?nav=1"></a></nav>'
        '<aside><a href="/documents/20123/119334/Normograma+Auditoria+General+de+la+Republica.pdf/3c283633-fc3e-c254-c19d-8b3f3e21634b?t=1693316541257">'
        "Normograma (Actos Legislativos-Leyes-Decretos)</a></aside>"
        f'<ul class="list-group">{"".join(filas)}</ul>{selector}{pag}'
        '<footer><a href="https://www.auditoria.gov.co/documents/20123/127064/Politica-editorial.pdf/0c3c?t=1755725898997">'
        "Política Editorial</a></footer></body></html>"
    )


# t (ms) de cargas reales.
_T_2025_03_28 = "1743104103922"
_T_2026_10_30 = "1793400000000"  # 2026-10-30 17:40 Bogotá
_T_2024_05_23 = "1716467244362"


# --- unidades -------------------------------------------------------------


def test_familia_registrada():
    assert FAMILY_REGISTRY["auditoria"] is ScrapAuditoria
    s = ScrapAuditoria()
    assert s.source == _SOURCE
    assert s.filters_by_publication_date is True
    assert s.doc_id_uses_publication_date is False
    assert s.checks_for_republication is True
    assert _ANIO_MINIMO == 2025


def test_fecha_de_carga_en_hora_de_bogota():
    assert _fecha_carga(_T_2024_05_23) == "2024-05-23"
    # 2025-03-28 00:35 UTC es todavía el 27 en Bogotá.
    assert _fecha_carga("1743122100000") == "2025-03-27"
    assert _fecha_carga(None) is None
    assert _fecha_carga("x") is None


def test_enlace_limpio_quita_t_y_download():
    href = f"{_DOCS}/108816/AGR-Concepto+110.015.2025.pdf/5a7486fd-9fe1?t={_T_2025_03_28}&download=true"
    assert _enlace_limpio(href) == f"{_DOCS}/108816/AGR-Concepto+110.015.2025.pdf/5a7486fd-9fe1"


def test_parse_carpeta_subcarpetas_archivos_y_dedup_por_uuid():
    html = _pagina("conceptos-juridicos", "108816", [
        _fila_carpeta("conceptos-juridicos", "3809705", "Conceptos 2026"),
        _fila_carpeta("conceptos-juridicos", "119334", "Normograma"),
        _fila_archivo("conceptos-juridicos", "108816", "AGR-Concepto 110.015.2025.De la prescripcion.pdf",
                      "5a7486fd-9fe1", _T_2025_03_28),
        _fila_archivo("conceptos-juridicos", "108816", "AGR-Concepto 110.015.2025.De la prescripcion.pdf",
                      "5a7486fd-9fe1", _T_2025_03_28),
    ], intervalo=(1, 32, 32))
    subs, archivos, intervalo = _parse_carpeta(html)
    assert subs == [("3809705", "Conceptos 2026")]
    assert len(archivos) == 1
    a = archivos[0]
    assert a["nombre"] == "AGR-Concepto 110.015.2025.De la prescripcion.pdf"
    assert a["uuid"] == "5a7486fd-9fe1"
    assert a["t"] == _T_2025_03_28
    assert "?" not in a["url"] and a["url"].endswith("/108816/AGR-Concepto+110.015.2025.De+la+prescripcion.pdf/5a7486fd-9fe1")
    assert intervalo == (1, 32, 32)


def test_parse_carpeta_sin_intervalo_y_entidades_escapadas():
    html = _pagina("circulares", "108260", [
        _fila_archivo("circulares", "1", "Concepto 110.063.2026 Control preventivo &amp;#8211; competencia.pdf",
                      "u1", _T_2025_03_28),
    ])
    _, archivos, intervalo = _parse_carpeta(html)
    assert intervalo is None
    assert archivos[0]["nombre"] == "Concepto 110.063.2026 Control preventivo – competencia.pdf"


@pytest.mark.parametrize("nombre,clase,numero,anio", [
    ("AGR-Concepto 110.015.2025.De la prescripcion.pdf", "CTO", "015", 2025),
    ("AGR -Concepto 110.014.2025. De la función.pdf", "CTO", "014", 2025),
    ("AGR- Concepto 110.019.2026 Del proceso.pdf", "CTO", "019", 2026),
    ("13. AGR- Concepto 110.022.2026 De la rendición.pdf", "CTO", "022", 2026),
    ("4.  Concepto 110.070.2026 De la responsabilidad.pdf", "CTO", "070", 2026),
    ("AGR -Concepto 1100.023.2025. Del proceso.pdf", "CTO", "023", 2025),
    ("AGR-Concepto-110-009-SIA-ATC.080 1.Del proceso.pdf", "CTO", "009", None),
    ("Concepto 110.042A.2011 x.pdf", "CTO", "042a", 2011),
    ("Concepto 110.061-1.2011 x.pdf", "CTO", "061-1", 2011),
    ("Resolución Orgánica No. 003 Por la cual se reglamenta.pdf", "ORG", "003", None),
    ("Resolución Orgánica 001 Por la cual.pdf", "ORG", "001", None),
    ("Resolución Orgánica No. 008_2025 Por medio.pdf", "ORG", "008", 2025),
    ("Res. Organica 04 de 2019.pdf", "ORG", "04", 2019),
    ("AGR. Res. Org. 003 - Por la cual.pdf", "ORG", "003", None),
    ("Res_Reglamentaria No. 001_2025 Delega.pdf", "REG", "001", 2025),
    ("Resolución Reglamentaria N° 005 Modifica parcialmente la Reglamentaria 010_2024.pdf", "REG", "005", None),
    ("Resolución Reglamentaria No 007 Modifica.pdf", "REG", "007", None),
    ("Resolución Reglamentaria No. 001 de 2026 Manual.pdf", "REG", "001", 2026),
    ("Res_Reglamentaria_NO_007_2019.pdf", "REG", "007", 2019),
    ("Resolucion Reglamenteria 004 x.pdf", "REG", "004", None),
    ("Resolucion Regalmentaria 006 x.pdf", "REG", "006", None),
    ("Resolución Orgánica No. 003 Por la cual se incluye un parágrafo transitorio Res_011_2024.pdf", "ORG", "003", None),
    ("Circular Externa 006 de 2025.pdf", "CIRCULAR", "006", 2025),
    ("Circular Externa 004 DE 2025.pdf", "CIRCULAR", "004", 2025),
    ("Circular Dispositiva No. 003 de 2026 Apertura.pdf", "CIRCULAR", "003", 2026),
    ("AGR_Circular_Externa_005_2021 (ANEXO).pdf", "CIRCULAR", "005", 2021),
])
def test_numero_tal_cual(nombre, clase, numero, anio):
    leido = _numero(nombre, clase)
    assert leido is not None
    assert leido[0] == numero
    assert leido[1] == anio


def test_numero_ilegible_y_clase_de_circular_del_nombre():
    assert _numero("39-02-2025_010-IGIP.pdf", "ORG") is None
    assert _numero("Circular Conjunta 001 de 2021.pdf", "CIRCULAR")[2] == "CJ"
    assert _numero("Circular Dispositiva 002.pdf", "CIRCULAR")[2] == "CD"


def test_titulo_y_valor():
    assert _titulo("CTO", "015", 2025) == "CTO_AGR_015_2025"
    assert _titulo("R", "003", 2026, "ORG") == "R_AGR_ORG-003_2026"
    assert _titulo("R", "001", 2025, "REG") == "R_AGR_REG-001_2025"
    assert _titulo("CTO", "042a", 2011) == "CTO_AGR_042A_2011"
    assert _valor_numero("008") == _valor_numero("08") == _valor_numero("8") == "8"
    assert _valor_numero("042a") == "42A"


def test_detalle_es_el_asunto():
    nombre = "13. AGR- Concepto 110.022.2026 De la rendición de la cuenta.pdf"
    assert _detalle(nombre, _numero(nombre, "CTO")[3]) == "De la rendición de la cuenta"
    nombre = "Circular Externa 006 de 2025.pdf"
    assert _detalle(nombre, _numero(nombre, "CIRCULAR")[3]) is None


# --- scrap() con el sitio simulado ------------------------------------------


def _registrar(rsps, pagina, folder_id, filas, intervalo=None):
    rsps.add(responses.GET, _url_carpeta(pagina, folder_id), body=_pagina(pagina, folder_id, filas, intervalo))


def _sitio(rsps, conceptos_root_extra=(), circulares=True):
    # Conceptos: raíz con carpetas por año (2024 no debe pedirse) y archivos
    # sueltos (uno repetido de 2025, uno sin año, uno viejo).
    _registrar(rsps, "conceptos-juridicos", "108816", [
        _fila_carpeta("conceptos-juridicos", "3809705", "Conceptos 2026"),
        _fila_carpeta("conceptos-juridicos", "3253128", "Conceptos 2025"),
        _fila_carpeta("conceptos-juridicos", "2553287", "Conceptos 2024"),
        _fila_archivo("conceptos-juridicos", "108816", "AGR-Concepto 110.15.2025.De la prescripcion.pdf",
                      "raiz-015", _T_2025_03_28),
        _fila_archivo("conceptos-juridicos", "108816", "AGR-Concepto-110-010-SIA ATC 083 Contrato.pdf",
                      "raiz-sin-anio", _T_2024_05_23),
        _fila_archivo("conceptos-juridicos", "108816", "AGR-Concepto 110.109.2022. Convenios.pdf",
                      "raiz-2022", _T_2024_05_23),
        *conceptos_root_extra,
    ], intervalo=(1, 6, 6))
    _registrar(rsps, "conceptos-juridicos", "3809705", [
        _fila_archivo("conceptos-juridicos", "3809705", "13. AGR- Concepto 110.072.2026 De las sociedades.pdf",
                      "c072", _T_2026_10_30),
    ])
    _registrar(rsps, "conceptos-juridicos", "3253128", [
        _fila_archivo("conceptos-juridicos", "3253128", "AGR-Concepto 110.015.2025.De la prescripcion.pdf",
                      "c015", _T_2025_03_28),
        _fila_archivo("conceptos-juridicos", "3253128", "AGR-Concepto 110.016.2026.Del proceso.pdf",
                      "c016", _T_2025_03_28),
    ])
    # Orgánicas: carpeta del año con el escaneo sin clase.
    _registrar(rsps, "resoluciones", "2437712", [
        _fila_carpeta("resoluciones", "3294861", "Res. Orgánicas 2025"),
        _fila_carpeta("resoluciones", "119710", "Res. Orgánicas 2019"),
    ])
    _registrar(rsps, "resoluciones", "3294861", [
        _fila_archivo("resoluciones", "3294861", "39-02-2025_010-IGIP.pdf", "igip", _T_2026_10_30),
        _fila_archivo("resoluciones", "3294861", "Resolución Orgánica No. 010 Por la cual se adoptan los IGIP.pdf",
                      "o010", _T_2025_03_28),
        _fila_archivo("resoluciones", "3294861", "Resolución Orgánica 003 Por la cual se incluye Res_011_2024.pdf",
                      "o003", _T_2025_03_28),
        _fila_archivo("resoluciones", "3294861", "Resolución Orgánica 03 Otra cosa.pdf",
                      "o003b", _T_2025_03_28),
        _fila_archivo("resoluciones", "3294861", "Resolución Orgánica 003 ANEXO tablas.pdf",
                      "o003anexo", _T_2025_03_28),
        _fila_archivo("resoluciones", "3294861", "Documento suelto.pdf", "suelto", _T_2025_03_28),
    ])
    # Reglamentarias: carpeta sin año con subcarpeta de 2026.
    _registrar(rsps, "resoluciones", "2437715", [
        _fila_carpeta("resoluciones", "3826600", "Res. Reglamentarias 2026"),
    ])
    _registrar(rsps, "resoluciones", "3826600", [
        _fila_archivo("resoluciones", "3826600",
                      "Resolución Reglamentaria N° 005 Modifica la Reglamentaria 010_2024.pdf", "r005", _T_2026_10_30),
    ])
    if circulares:
        _registrar(rsps, "circulares", "108260", [
            _fila_carpeta("circulares", "3864048", "2026"),
            _fila_carpeta("circulares", "2558891", "2024"),
        ], intervalo=(1, 2, 2))
        _registrar(rsps, "circulares", "3864048", [
            _fila_carpeta("circulares", "3864100", "Circulares Dispositivas 2026"),
            _fila_archivo("circulares", "3864048", "Circular Conjunta 001 de 2026.pdf", "cj001", _T_2026_10_30),
            _fila_archivo("circulares", "3864048", "Circular 009 de 2026.pdf", "sinclase", _T_2026_10_30),
        ])
        _registrar(rsps, "circulares", "3864100", [
            _fila_archivo("circulares", "3864100", "Circular Dispositiva No. 003 de 2025 Apertura.pdf",
                          "cd003", _T_2026_10_30),
        ])
    else:
        rsps.add(responses.GET, _url_carpeta("circulares", "108260"), status=503)


def _por_titulo(docs):
    return {d.title: d for d in docs}


@responses.activate
def test_scrap_completo():
    _sitio(responses)
    avisos = []
    docs = ScrapAuditoria().scrap("2025-01-01", "2026-12-31", on_progress=avisos.append)
    t = _por_titulo(docs)
    assert set(t) == {
        "CTO_AGR_072_2026", "CTO_AGR_015_2025", "CTO_AGR_016_2025",
        "R_AGR_ORG-010_2025", "R_AGR_ORG-010_2025_A01", "R_AGR_ORG-003_2025",
        "R_AGR_ORG-003_2025_A01", "R_AGR_ORG-003_2025_A02",
        next(k for k in t if k.startswith("R_AGR_DOCUMENTOSUELTO")),
        "R_AGR_REG-005_2026",
        "CJ_AGR_001_2026", "CE_AGR_009_2026", "CD_AGR_003_2026",
    }
    # Ninguna carpeta bajo el piso se pidió (el simulador fallaría).
    pedidas = [c.request.url for c in responses.calls]
    assert not any("/view/2553287" in u or "/view/119710" in u or "/view/2558891" in u for u in pedidas)
    assert all("deltaEntry=500" in u for u in pedidas)

    c = t["CTO_AGR_072_2026"]
    assert c.tipo == "Concepto"
    assert c.f_public == "2026-10-30"
    assert c.f_providencia == "2026-01-01"
    assert c.detalle == "De las sociedades"
    assert c.link == {"url": f"{_DOCS}/3809705/{quote_plus('13. AGR- Concepto 110.072.2026 De las sociedades.pdf')}/c072",
                      "method": "GET", "verify": False}
    assert c.save_path == f"{_SOURCE}/2026-10-30/Concepto/CTO_AGR_072_2026(extension)"
    assert c.source == _SOURCE

    # Se queda el de la carpeta del año, no el de la raíz.
    assert t["CTO_AGR_015_2025"].link["url"].endswith("/c015")
    # Año: manda la carpeta, con aviso.
    assert any("110.016.2026" in a and "se usa 2025" in a for a in avisos)
    # Concepto de la raíz sin año: omitido con aviso.
    assert any("SIA ATC 083" in a and "se omite" in a for a in avisos)

    assert t["R_AGR_ORG-010_2025"].tipo == "Resolución orgánica"
    assert t["R_AGR_ORG-010_2025_A01"].link["url"].endswith("/igip")
    assert any("39-02-2025_010-IGIP.pdf" in a and "R_AGR_ORG-010_2025" in a for a in avisos)
    # Repetido con otro asunto (03 = 003): anexo con aviso que nombra ambos.
    assert t["R_AGR_ORG-003_2025_A01"].link["url"].endswith("/o003b")
    assert any("número repetido" in a and "Otra cosa" in a for a in avisos)
    # El anexo por palabra va después y sin aviso de repetido.
    assert t["R_AGR_ORG-003_2025_A02"].link["url"].endswith("/o003anexo")
    assert not any("número repetido" in a and "ANEXO" in a for a in avisos)
    suelto = next(d for d in docs if d.title.startswith("R_AGR_DOCUMENTOSUELTO"))
    assert suelto.title_unverified is True

    r = t["R_AGR_REG-005_2026"]
    assert r.tipo == "Resolución reglamentaria" and r.f_providencia == "2026-01-01"

    assert t["CD_AGR_003_2026"].tipo == "Circular dispositiva"
    assert t["CD_AGR_003_2026"].f_providencia == "2026-01-01"
    assert t["CJ_AGR_001_2026"].tipo == "Circular conjunta"
    assert t["CE_AGR_009_2026"].title_unverified is True
    assert sum(d.title_unverified for d in docs) == 2


@responses.activate
def test_scrap_filtra_por_fecha_de_carga():
    _sitio(responses)
    docs = ScrapAuditoria().scrap("2026-10-01", "2026-12-31")
    assert {d.f_public for d in docs} == {"2026-10-30"}
    assert "CTO_AGR_015_2025" not in _por_titulo(docs)


@responses.activate
def test_scrap_seccion_que_falla_avisa_y_sigue():
    _sitio(responses, circulares=False)
    avisos = []
    docs = ScrapAuditoria().scrap("2025-01-01", "2026-12-31", on_progress=avisos.append)
    assert any("Error leyendo la carpeta" in a and "Circulares" in a for a in avisos)
    assert "CTO_AGR_072_2026" in _por_titulo(docs)
    assert not any(d.tipo.startswith("Circular") for d in docs)


@responses.activate
def test_scrap_subcarpeta_que_falla_avisa_y_sigue():
    _sitio(responses)
    responses.replace(responses.GET, _url_carpeta("conceptos-juridicos", "3809705"), status=500)
    avisos = []
    docs = ScrapAuditoria().scrap("2025-01-01", "2026-12-31", on_progress=avisos.append)
    assert any("Conceptos 2026" in a for a in avisos)
    assert "CTO_AGR_015_2025" in _por_titulo(docs)


@responses.activate
def test_scrap_seccion_vacia_avisa():
    _sitio(responses)
    responses.replace(responses.GET, _url_carpeta("resoluciones", "2437715"),
                      body=_pagina("resoluciones", "2437715", []))
    avisos = []
    ScrapAuditoria().scrap("2025-01-01", "2026-12-31", on_progress=avisos.append)
    assert any("Resoluciones reglamentarias: no se encontraron" in a for a in avisos)


@responses.activate
def test_scrap_pagina_con_curentry():
    _sitio(responses)
    url = _url_carpeta("conceptos-juridicos", "3253128")
    responses.replace(
        responses.GET, url,
        body=_pagina("conceptos-juridicos", "3253128", [
            _fila_archivo("conceptos-juridicos", "3253128", "AGR-Concepto 110.015.2025.x.pdf", "c015", _T_2025_03_28),
        ], intervalo=(1, 1, 2)),
        match=[responses.matchers.query_param_matcher(
            {"_com_liferay_document_library_web_portlet_DLPortlet_INSTANCE_h6j3F7UA67se_deltaEntry": "500",
             "_com_liferay_document_library_web_portlet_DLPortlet_INSTANCE_h6j3F7UA67se_curEntry": "1"})],
    )
    responses.add(
        responses.GET, url,
        body=_pagina("conceptos-juridicos", "3253128", [
            _fila_archivo("conceptos-juridicos", "3253128", "AGR-Concepto 110.017.2025.y.pdf", "c017", _T_2025_03_28),
        ], intervalo=(2, 2, 2)),
        match=[responses.matchers.query_param_matcher(
            {"_com_liferay_document_library_web_portlet_DLPortlet_INSTANCE_h6j3F7UA67se_deltaEntry": "500",
             "_com_liferay_document_library_web_portlet_DLPortlet_INSTANCE_h6j3F7UA67se_curEntry": "2"})],
    )
    docs = ScrapAuditoria().scrap("2025-01-01", "2026-12-31")
    assert {"CTO_AGR_015_2025", "CTO_AGR_017_2025"} <= set(_por_titulo(docs))


@responses.activate
def test_scrap_tope_de_paginacion_avisa():
    _sitio(responses)
    # Un paginador que siempre dice que hay más.
    responses.replace(
        responses.GET, _url_carpeta("conceptos-juridicos", "3809705"),
        body=_pagina("conceptos-juridicos", "3809705", [], intervalo=(1, 1, 999)),
    )
    avisos = []
    ScrapAuditoria().scrap("2025-01-01", "2026-12-31", on_progress=avisos.append)
    assert any("tope de páginas" in a for a in avisos)


@responses.activate
def test_scrap_limit_y_cancelacion():
    _sitio(responses)
    assert len(ScrapAuditoria().scrap("2025-01-01", "2026-12-31", limit=2)) == 2
    ev = threading.Event()
    ev.set()
    assert ScrapAuditoria().scrap("2025-01-01", "2026-12-31", stop_event=ev) == []


@responses.activate
def test_scrap_usa_verify_false():
    _sitio(responses)
    original = requests.Session.send
    vistos = []

    def espia(self, request, **kwargs):
        vistos.append(kwargs.get("verify"))
        return original(self, request, **kwargs)

    requests.Session.send = espia
    try:
        ScrapAuditoria().scrap("2025-01-01", "2026-12-31", limit=1)
    finally:
        requests.Session.send = original
    assert vistos and all(v is False for v in vistos)
