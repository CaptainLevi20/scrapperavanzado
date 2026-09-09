from core.scrapers.families.supersolidaria import (
    _anio_de_h2,
    _es_anexo,
    _extension_del_href,
    _fecha_concepto,
    _filas_concepto,
    _iter_documentos,
    _num_seccion,
    _prefijo_fecha_archivo,
    _resolver_fecha,
    _safe_title,
    _titulo,
    _titulo_concepto,
)
from bs4 import BeautifulSoup


def test_extension_del_href():
    assert _extension_del_href("/sites/default/files/data/20260520_circular_externa_101.pdf") == "pdf"
    assert _extension_del_href("/x/y/2._anexo.docx?a=1") == "docx"
    assert _extension_del_href("/x/y/matriz.XLSX") == "xlsx"
    assert _extension_del_href("/es/content/algo") == ""


def test_es_anexo():
    assert _es_anexo("Anexo - Circular Externa N° 101") is True
    assert _es_anexo("ANEXO técnico") is True
    assert _es_anexo("Matriz de Comentarios - Circular N° 101") is True
    assert _es_anexo("Matriz de Observaciones") is True
    assert _es_anexo("Circular Externa N° 101") is False
    assert _es_anexo("") is False


def test_num_seccion_resolucion_radicado_largo_ultimos_6():
    assert _num_seccion("R", "Resolución 2025430007935 del 30 de diciembre de 2025") == 7935
    assert _num_seccion("R", "Resolución 2026113001925 del 26 de marzo de 2026") == 1925


def test_num_seccion_resolucion_forma_corta():
    assert _num_seccion("R", "Resolución 745 de 2003") == 745


def test_num_seccion_circulares_y_cartas():
    assert _num_seccion("CE", "Circular Externa N° 102") == 102
    assert _num_seccion("CE", "Anexo - Circular Externa N° 101") == 101
    assert _num_seccion("CC", "Carta Circular N° 37") == 37
    assert _num_seccion("CJ", "Circular conjunta No. 067") == 67


def test_num_seccion_none_cuando_no_hay():
    assert _num_seccion("CJ", "ministro_del_trabajo_y_superintendente_de_la_economia_solidaria") is None
    assert _num_seccion("CE", "Circular Externa sin numero") is None


def test_anio_de_h2():
    assert _anio_de_h2("Circulares Externas 2024") == 2024
    assert _anio_de_h2("CIRCULARES EXTERNAS 2022") == 2022
    assert _anio_de_h2("\xa0CIRCULARES EXTERNAS 2021") == 2021
    assert _anio_de_h2("Resoluciones Generales 2016") == 2016
    assert _anio_de_h2("Cartas Circulares 2015") == 2015
    assert _anio_de_h2("Resoluciones Generales") is None
    assert _anio_de_h2("Otra cosa 2020") is None


def test_prefijo_fecha_archivo():
    assert _prefijo_fecha_archivo("/sites/default/files/data/20260520_circular_externa_101.pdf") == "2026-05-20"
    assert _prefijo_fecha_archivo("/x/circular-conjunta-nov-09_0.pdf") is None
    assert _prefijo_fecha_archivo("/x/20261332_algo.pdf") is None  # mes/día inválidos


def test_fecha_concepto():
    assert _fecha_concepto("/x/20260821_concepto_20261100232001.pdf", None) == "2026-08-21"
    assert _fecha_concepto("/x/concept_uni.pdf", "2025-05-16T00:00:00Z") == "2025-05-16"
    assert _fecha_concepto("/x/concept_uni.pdf", None) is None


def test_titulo_verificado_y_anexo():
    assert _titulo("CE", "Circular Externa", "Circular Externa N° 102", "2026", False) == ("CE_SES_0102_2026", False)
    assert _titulo("CE", "Circular Externa", "Anexo - Circular Externa N° 101", "2026", True) == ("CE_SES_0101_2026_A01", False)
    assert _titulo("R", "Resolución", "Resolución 2025430007935 del 30 de diciembre de 2025", "2025", False) == ("R_SES_7935_2025", False)


def test_titulo_fallback_sin_numero():
    t, unv = _titulo("CJ", "Circular Conjunta", "ministro_del_trabajo_y_superintendente", "2009", False)
    assert unv is True and t == "ministro_del_trabajo_y_superintendente"
    assert _titulo("CE", "Circular Externa", "   ", "2020", False) == ("documento", True)


def test_titulo_concepto():
    assert _titulo_concepto("/x/20260821_concepto_20261100232001.pdf", "irrelevante", "2026") == ("CTO_SES_20261100232001_2026", False)
    t, unv = _titulo_concepto("/x/20250516_concept_uni.pdf", "Concepto Unificado - Tratamiento", "2025")
    assert unv is True and t == "Concepto Unificado - Tratamiento"


def test_safe_title():
    assert _safe_title('a/b:c"  .') == "a-b-c-"
    assert len(_safe_title("z" * 200)) == 120


def test_resolver_fecha_resolucion_por_prosa():
    f = _resolver_fecha("Resolución", True,
                        "Resolución 2025430007935 del 30 de diciembre de 2025",
                        "/x/resolucion_2025430007935.pdf", None, None)
    assert f == "2025-12-30"


def test_resolver_fecha_circular_prefiere_time_luego_archivo_luego_h2():
    assert _resolver_fecha("Circular Externa", False, "Circular Externa N° 45", "/x/y.pdf",
                           2019, "2023-02-10T00:00:00Z") == "2023-02-10"
    assert _resolver_fecha("Circular Externa", False, "Circular Externa N° 45",
                           "/x/20221007_circular_externa_42.pdf", 2019, None) == "2022-10-07"
    assert _resolver_fecha("Circular Externa", False, "Circular Externa N° 45",
                           "/x/circular_externa_42.pdf", 2019, None) == "2019-01-01"


def test_resolver_fecha_none_cuando_no_hay_nada():
    assert _resolver_fecha("Circular Conjunta", False, "ministro_del_trabajo", "/x/y.pdf", None, None) is None


_HTML_TABLA = """
<h2 class="western">Circulares Externas</h2>
<h2 class="western">Circulares Externas 2026</h2>
<div class="paragraph paragraph--type--archivos-collection">
 <div class="field field--name-field-archivo"><table><thead><tr><th>Adjunto</th><th>Tamaño</th></tr></thead>
 <tbody><tr><td><span class="file file--mime-application-pdf"><a href="/sites/default/files/data/20260520_circular_externa_101.pdf" title="x">Circular Externa N° 101</a></span><span>(1 KB)</span></td><td>1 KB</td></tr></tbody></table></div>
 <div class="field field--name-field-fecha-de-publicacion"><div class="field__item"><time datetime="2026-05-20T14:54:24Z">x</time></div></div>
</div>
<div class="paragraph paragraph--type--archivos-collection">
 <div class="field field--name-field-archivo"><table><tbody><tr><td><span class="file"><a href="/sites/default/files/data/20260521_anexo_tecnico_circ_101.pdf" title="x">Anexo - Circular Externa N° 101</a></span></td></tr></tbody></table></div>
</div>
<h2 class="western">CIRCULARES EXTERNAS 2015</h2>
<div class="paragraph paragraph--type--archivos-collection">
 <div class="field field--name-field-archivo"><table><tbody><tr><td><span class="file"><a href="/sites/default/files/data/circular_externa_10.pdf" title="x">Circular Externa N° 10</a></span></td></tr></tbody></table></div>
</div>
"""


def test_iter_documentos_emite_h2_y_docs_en_orden():
    soup = BeautifulSoup(_HTML_TABLA, "html.parser")
    eventos = list(_iter_documentos(soup))
    kinds = [e[0] for e in eventos]
    assert kinds == ["h2", "doc", "doc", "h2", "doc"]
    assert eventos[0][1] == 2026
    t0, h0, time0 = eventos[1][1]
    assert t0 == "Circular Externa N° 101"
    assert h0 == "/sites/default/files/data/20260520_circular_externa_101.pdf"
    assert time0 == "2026-05-20T14:54:24Z"
    assert eventos[3][1] == 2015
    assert eventos[4][1][0] == "Circular Externa N° 10"


_HTML_CONCEPTOS = """
<table><thead><tr><th>Nombre</th><th>Resumen</th><th></th></tr></thead><tbody>
<tr>
  <td class="views-field views-field-title"><a href="/es/content/principales-aspectos">Principales aspectos</a></td>
  <td class="views-field views-field-body"><p>Resumen…</p></td>
  <td class="views-field views-field-nothing"><a href="/sites/default/files/conceptos_juridicos_y_contables/20260821_concepto_20261100232001.pdf" target="_blank"><a href="/sites/default/files/conceptos_juridicos_y_contables/20260821_concepto_20261100232001.pdf">Ver más</a></a></td>
</tr>
</tbody></table>
"""


def test_filas_concepto():
    filas = _filas_concepto(_HTML_CONCEPTOS)
    assert len(filas) == 1
    titulo, href, time_iso = filas[0]
    assert titulo == "Principales aspectos"
    assert href == "/sites/default/files/conceptos_juridicos_y_contables/20260821_concepto_20261100232001.pdf"
    assert time_iso is None


def test_filas_concepto_pagina_vacia():
    assert _filas_concepto("<table><thead><tr><th>Nombre</th></tr></thead><tbody></tbody></table>") == []
    assert _filas_concepto("<html><body>nada</body></html>") == []


import threading

import responses

from core.scrapers.registry import FAMILY_REGISTRY
from core.scrapers.families.supersolidaria import ScrapSupersolidaria

_RES_URL = "https://www.supersolidaria.gov.co/es/content/resoluciones-generales"
_CE_URL = "https://www.supersolidaria.gov.co/es/content/circulares-externas-por-ano"
_CJ_URL = "https://www.supersolidaria.gov.co/es/content/circulares-conjuntas"
_CC_URL = "https://www.supersolidaria.gov.co/es/content/cartas-circulares"
_CTO_URL = "https://www.supersolidaria.gov.co/es/conceptos-juridicos-y-contables"


def _doc(href, titulo):
    return (
        '<div class="paragraph paragraph--type--archivos-collection">'
        '<div class="field field--name-field-archivo"><table><tbody><tr><td>'
        f'<span class="file file--mime-application-pdf"><a href="{href}" title="x">{titulo}</a></span>'
        '<span>(1 KB)</span></td></tr></tbody></table></div></div>'
    )


def _pagina_tabla(h2_y_docs):
    # h2_y_docs: lista de ("h2","Circulares Externas 2026") | ("doc", href, titulo)
    partes = []
    for item in h2_y_docs:
        if item[0] == "h2":
            partes.append(f'<h2 class="western">{item[1]}</h2>')
        else:
            partes.append(_doc(item[1], item[2]))
    return "<html><body>" + "".join(partes) + "</body></html>"


def _pagina_conceptos(filas):
    trs = "".join(
        f'<tr><td class="views-field views-field-title"><a href="/es/content/{i}">{t}</a></td>'
        f'<td class="views-field views-field-body"><p>r</p></td>'
        f'<td class="views-field views-field-nothing"><a href="{h}">Ver más</a></td></tr>'
        for i, (t, h) in enumerate(filas)
    )
    return f"<html><body><table><tbody>{trs}</tbody></table></body></html>"


def _vacias():
    return {
        _RES_URL: "<html><body></body></html>",
        _CE_URL: "<html><body></body></html>",
        _CJ_URL: "<html><body></body></html>",
        _CC_URL: "<html><body></body></html>",
    }


def _registrar(paginas, conceptos_por_pagina):
    # `responses` entrega múltiples registros de la misma URL en orden y repite
    # el último; la query `?page=N` no distingue (matching por path). Así que se
    # registran las páginas de conceptos en secuencia + una vacía al final.
    for url, body in paginas.items():
        responses.add(responses.GET, url, body=body)
    for filas in conceptos_por_pagina:
        responses.add(responses.GET, _CTO_URL, body=_pagina_conceptos(filas))
    responses.add(responses.GET, _CTO_URL, body=_pagina_conceptos([]))


def test_supersolidaria_registrada():
    import core.scrapers.families  # noqa: F401
    assert FAMILY_REGISTRY["supersolidaria"].__name__ == "ScrapSupersolidaria"


def test_filters_by_publication_date_activo():
    assert ScrapSupersolidaria.filters_by_publication_date is True


@responses.activate
def test_scrap_resolucion_por_prosa_y_circular_por_h2():
    pag = _vacias()
    pag[_RES_URL] = _pagina_tabla([
        ("h2", "Resoluciones Generales 2025"),
        ("doc", "/sites/default/files/data/20260101_resolucion_2025430007935.pdf",
         "Resolución 2025430007935 del 30 de diciembre de 2025"),
    ])
    pag[_CE_URL] = _pagina_tabla([
        ("h2", "Circulares Externas 2020"),
        ("doc", "/sites/default/files/data/circular_externa_60.pdf", "Circular Externa N° 60"),
    ])
    _registrar(pag, [])
    docs = ScrapSupersolidaria().scrap(fini="2015-01-01", ffin="2026-12-31")
    por = {d.title: d for d in docs}
    assert por["R_SES_7935_2025"].f_public == "2025-12-30"
    assert por["R_SES_7935_2025"].tipo == "Resolución"
    assert por["R_SES_7935_2025"].link == {
        "url": "https://www.supersolidaria.gov.co/sites/default/files/data/20260101_resolucion_2025430007935.pdf",
        "method": "GET",
    }
    assert "verify" not in por["R_SES_7935_2025"].link
    assert por["CE_SES_0060_2020"].f_public == "2020-01-01"
    assert por["CE_SES_0060_2020"].save_path == (
        "Superintendencia de la Economía Solidaria/2020-01-01/Circular Externa/CE_SES_0060_2020(extension)"
    )


@responses.activate
def test_scrap_anexo_recibe_sufijo_a01():
    pag = _vacias()
    pag[_CE_URL] = _pagina_tabla([
        ("h2", "Circulares Externas 2026"),
        ("doc", "/sites/default/files/data/20260520_circular_externa_101.pdf", "Circular Externa N° 101"),
        ("doc", "/sites/default/files/data/20260521_anexo_tecnico_circ_101.pdf", "Anexo - Circular Externa N° 101"),
        ("doc", "/sites/default/files/data/20260521_matriz.xlsx", "Matriz de Comentarios - Circular N° 101"),
    ])
    _registrar(pag, [])
    docs = ScrapSupersolidaria().scrap(fini="2015-01-01", ffin="2026-12-31")
    titles = {d.title for d in docs}
    assert "CE_SES_0101_2026" in titles
    assert "CE_SES_0101_2026_A01" in titles
    # el 2º anexo del mismo número colisiona -> degradado a crudo
    assert any(d.title_unverified and "Matriz" in d.title for d in docs)


@responses.activate
def test_scrap_aplica_piso_2015_y_rango():
    pag = _vacias()
    pag[_CE_URL] = _pagina_tabla([
        ("h2", "Circulares Externas 2013"),
        ("doc", "/x/circular_externa_5.pdf", "Circular Externa N° 5"),
        ("h2", "Circulares Externas 2026"),
        ("doc", "/x/circular_externa_99.pdf", "Circular Externa N° 99"),
    ])
    _registrar(pag, [])
    docs = ScrapSupersolidaria().scrap(fini="2015-01-01", ffin="2026-12-31")
    assert {d.title for d in docs} == {"CE_SES_0099_2026"}


@responses.activate
def test_scrap_conceptos_pagina_hasta_vacio():
    _registrar(_vacias(), [
        [("Principales aspectos", "/sites/default/files/conceptos_juridicos_y_contables/20260821_concepto_20261100232001.pdf")],
        [("Concepto Unificado", "/sites/default/files/conceptos_juridicos_y_contables/20250516_concept_uni.pdf")],
    ])
    docs = ScrapSupersolidaria().scrap(fini="2015-01-01", ffin="2026-12-31")
    conc = {d.title: d for d in docs if d.tipo == "Concepto"}
    assert set(conc) == {"CTO_SES_20261100232001_2026", "Concepto Unificado"}
    assert conc["CTO_SES_20261100232001_2026"].f_public == "2026-08-21"
    assert conc["Concepto Unificado"].title_unverified is True
    assert conc["Concepto Unificado"].f_public == "2025-05-16"


@responses.activate
def test_scrap_omite_doc_sin_fecha_y_avisa():
    pag = _vacias()
    pag[_CJ_URL] = _pagina_tabla([("doc", "/sites/default/files/normativa/circular-conjunta-nov-09.pdf", "circular-conjunta-nov-09")])
    _registrar(pag, [])
    avisos = []
    docs = ScrapSupersolidaria().scrap(fini="2015-01-01", ffin="2026-12-31", on_progress=avisos.append)
    assert [d for d in docs if d.tipo == "Circular Conjunta"] == []
    assert any("sin fecha" in m.lower() for m in avisos)


@responses.activate
def test_scrap_continua_si_una_seccion_falla():
    pag = _vacias()
    responses.add(responses.GET, _RES_URL, status=500)
    del pag[_RES_URL]
    pag[_CE_URL] = _pagina_tabla([("h2", "Circulares Externas 2026"), ("doc", "/x/circular_externa_7.pdf", "Circular Externa N° 7")])
    _registrar(pag, [])
    avisos = []
    docs = ScrapSupersolidaria().scrap(fini="2015-01-01", ffin="2026-12-31", on_progress=avisos.append)
    assert {d.title for d in docs} == {"CE_SES_0007_2026"}
    assert any("Error" in m and "Resoluci" in m for m in avisos)


@responses.activate
def test_scrap_dedup_por_url():
    pag = _vacias()
    dup = "/sites/default/files/data/20260520_circular_externa_101.pdf"
    pag[_CE_URL] = _pagina_tabla([
        ("h2", "Circulares Externas 2026"),
        ("doc", dup, "Circular Externa N° 101"),
        ("doc", dup, "Circular Externa N° 101"),
    ])
    _registrar(pag, [])
    docs = ScrapSupersolidaria().scrap(fini="2015-01-01", ffin="2026-12-31")
    assert len([d for d in docs if d.tipo == "Circular Externa"]) == 1


@responses.activate
def test_scrap_respeta_stop_event():
    ev = threading.Event(); ev.set()
    assert ScrapSupersolidaria().scrap(fini="2015-01-01", ffin="2026-12-31", stop_event=ev) == []
    assert len(responses.calls) == 0

@responses.activate
def test_scrap_limit_corta():
    pag = _vacias()
    pag[_CE_URL] = _pagina_tabla([("h2", "Circulares Externas 2026"),
                                  ("doc", "/x/circular_externa_1.pdf", "Circular Externa N° 1"),
                                  ("doc", "/x/circular_externa_2.pdf", "Circular Externa N° 2")])
    _registrar(pag, [])
    assert len(ScrapSupersolidaria().scrap(fini="2015-01-01", ffin="2026-12-31", limit=1)) == 1
