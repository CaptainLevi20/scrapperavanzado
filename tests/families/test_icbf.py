import datetime
import io
import re
import threading
import zipfile

import responses
from responses import matchers

from core.scrapers.families.icbf import (
    _ANIO_MINIMO,
    _fecha_del_encabezado,
    _texto_inicial_docx,
    _LISTADO_URL,
    _SOURCE,
    _anios,
    _filas,
    _titulo,
    _url_documento,
    ScrapIcbf,
)
from core.scrapers.registry import FAMILY_REGISTRY

_SITIO = "https://www.icbf.gov.co"


def _fila(num, anio, slug=None, epigrafe="Representación legal de niños, niñas y adolescentes", categoria="CONCEPTO"):
    # Copia de una fila real de /concepto (celdas con espacios finales y el
    # epígrafe envuelto en <p><span style=...>).
    slug = slug or f"concepto-{num}-de-{anio}".replace(" ", "")
    return (
        "<tr>\n"
        f'  <td headers="view-field-tipo-norma-table-column" class="views-field views-field-field-tipo-norma">{categoria}          </td>\n'
        f'  <td headers="view-field-numero-table-column" class="views-field views-field-field-numero">{num}          </td>\n'
        f'  <td headers="view-field-anio-table-column" class="views-field views-field-field-anio">{anio}          </td>\n'
        '  <td headers="view-field-epigrafe-table-column" class="views-field views-field-field-epigrafe">'
        f'<p><span style="font-family:&quot;Verdana&quot;,sans-serif;">Respuesta&nbsp;</span><span lang="ES">{epigrafe}</span></p>          </td>\n'
        f'  <td headers="view-view-node-table-column" class="views-field views-field-view-node"><a href="/normograma/{slug}" hreflang="es">Consultar</a>          </td>\n'
        "</tr>\n"
    )


def _listado(*filas, siguiente=None) -> str:
    # Copia del paginador real: el enlace "página siguiente" sólo está si hay más.
    pager = (
        '<nav class="pager" role="navigation" aria-label="Paginación"><ul class="pagination pager__items">'
        '<li class="page-item pager__item--next">'
        f'<a href="?field_anio_value=2016&amp;page={siguiente}" title="Ir a la página siguiente" rel="next" class="page-link">'
        '<span class="visually-hidden">Siguiente página</span><span aria-hidden="true">››</span></a></li></ul></nav>'
    ) if siguiente is not None else ""
    return (
        '<html><body><table class="cols-5"><thead><tr><th>Categoría</th><th>Número</th><th>Año</th>'
        "<th>Temática</th><th></th></tr></thead>\n<tbody>\n" + "".join(filas) + "</tbody></table>" + pager + "</body></html>"
    )


def _detalle(archivo=None) -> str:
    boton = (
        '<div class="norma-box"><label>Documento</label>\n'
        f'  <a href="/sites/default/files/normas/{archivo}"\n     target="_blank"\n     class="btn-documento">\n'
        "    Descargar documento\n  </a>\n</div>"
    ) if archivo else ""
    return f'<html><body><div class="epigrafe"><p>Texto</p></div>{boton}</body></html>'


def _anio(anio, *paginas, status=200):
    """Registra las páginas del listado de un año."""
    for p, filas in enumerate(paginas):
        siguiente = p + 1 if p + 1 < len(paginas) else None
        responses.add(
            responses.GET, _LISTADO_URL, body=_listado(*filas, siguiente=siguiente), status=status,
            match=[matchers.query_param_matcher({"field_anio_value": str(anio), "page": str(p)})],
        )


def _docx(encabezado: str) -> bytes:
    """Un .docx mínimo como los del ICBF: el encabezado partido en trozos
    (Word corta palabras y fechas: "CONCEPTO 10 D" + "E 2026"), luego el resto."""
    mitad = len(encabezado) // 2
    trozos = [encabezado[:mitad], encabezado[mitad:]]
    corridas = "".join(f"<w:r><w:t xml:space=\"preserve\">{t}</w:t></w:r>" for t in trozos)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        f"<w:p>{corridas}</w:p><w:p><w:r><w:t>INSTITUTO COLOMBIANO DE BIENESTAR FAMILIAR</w:t></w:r></w:p>"
        "</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


def _encabezado_de(slug: str) -> str:
    # concepto-10-de-2026 → "CONCEPTO 10 DE 2026 (5 de marzo)"
    m = re.match(r"concepto-([0-9A-Za-z]+)-de-(\d{4})$", slug)
    return f"CONCEPTO {m.group(1)} DE {m.group(2)} (5 de marzo)" if m else "SIN ENCABEZADO"


def _det(slug, archivo=None, status=200, encabezado=None, status_docx=200):
    responses.add(responses.GET, f"{_SITIO}/normograma/{slug}", body=_detalle(archivo), status=status)
    if archivo:
        url = f"{_SITIO}/sites/default/files/normas/{archivo}"
        if not any(r.url == url for r in responses.registered()):
            responses.add(responses.GET, url, body=_docx(encabezado or _encabezado_de(slug)), status=status_docx)


def _archivo(num, anio):
    return f"CONCEPTO%20{num}%20DE%20{anio}.docx"


def test_source_y_registro():
    assert _SOURCE == "Instituto Colombiano de Bienestar Familiar"
    assert _ANIO_MINIMO == 2015
    assert FAMILY_REGISTRY["icbf"] is ScrapIcbf
    assert ScrapIcbf.checks_for_republication is True
    assert ScrapIcbf.filters_by_publication_date is False


def test_titulo():
    assert _titulo("10", 2026) == ("CTO_ICBF_0010_2026", False)
    assert _titulo("3C", 2020) == ("CTO_ICBF_0003C_2020", False)
    assert _titulo("132 A", 2017) == ("CTO_ICBF_0132A_2017", False)
    assert _titulo("142-1", 2015) == ("CTO_ICBF_0142-1_2015", False)
    assert _titulo("11b", 2018) == ("CTO_ICBF_0011B_2018", False)


def test_titulo_fuera_de_patron():
    assert _titulo("S/N 4", 2019) == ("CTO_ICBF_SN4_2019", True)
    assert _titulo("", 2019) == ("CTO_ICBF_SN_2019", True)


def test_parseo_fila():
    filas = _filas(_listado(_fila("132 A", 2017, slug="concepto-132-de-2017-0", epigrafe="Patria potestad")))
    assert filas == [{
        "categoria": "CONCEPTO",
        "numero": "132 A",
        "anio": "2017",
        "epigrafe": "Respuesta Patria potestad",
        "href": f"{_SITIO}/normograma/concepto-132-de-2017-0",
    }]


def test_parseo_detalle():
    url = f"{_SITIO}/normograma/concepto-10-de-2026"
    assert _url_documento(_detalle(_archivo(10, 2026)), url) == (
        f"{_SITIO}/sites/default/files/normas/CONCEPTO%2010%20DE%202026.docx"
    )
    assert _url_documento(_detalle(), url) is None


def test_anios_pedidos():
    assert list(_anios("2010-01-01", "2016-06-30")) == [2015, 2016]
    assert list(_anios("2026-11-10", "2026-11-10")) == [2026]
    assert list(_anios("2025-12-29", "2026-01-02")) == [2025, 2026]


@responses.activate
def test_documento_completo():
    _anio(2026, [_fila(10, 2026, epigrafe="Kick Boxing")])
    _det("concepto-10-de-2026", _archivo(10, 2026))
    docs = ScrapIcbf().scrap("2026-11-10", "2026-11-10")
    assert len(docs) == 1
    d = docs[0]
    assert d.title == "CTO_ICBF_0010_2026"
    assert d.tipo == "Concepto"
    # Fecha leída del encabezado del .docx ("CONCEPTO 10 DE 2026 (5 de marzo)").
    assert d.f_public == d.f_providencia == "2026-03-05"
    assert d.detalle == "Respuesta Kick Boxing"
    assert d.link == {"url": f"{_SITIO}/sites/default/files/normas/CONCEPTO%2010%20DE%202026.docx", "method": "GET"}
    assert d.save_path == f"{_SOURCE}/2026-03-05/Concepto/CTO_ICBF_0010_2026(extension)"
    assert d.title_unverified is False


@responses.activate
def test_solo_anios_desde_el_piso():
    _anio(2015, [_fila(1, 2015)])
    _anio(2016, [_fila(2, 2016)])
    _det("concepto-1-de-2015", _archivo(1, 2015))
    _det("concepto-2-de-2016", _archivo(2, 2016))
    docs = ScrapIcbf().scrap("2010-01-01", "2016-06-30")
    assert [d.title for d in docs] == ["CTO_ICBF_0001_2015", "CTO_ICBF_0002_2016"]
    pedidos = [c.request.params.get("field_anio_value") for c in responses.calls if "field_anio_value" in c.request.url]
    assert pedidos == ["2015", "2016"]


@responses.activate
def test_paginacion():
    pagina_llena = [_fila(n, 2016) for n in range(200, 100, -1)]  # 100 filas
    _anio(2016, pagina_llena, [_fila(5, 2016)])
    for n in list(range(101, 201)) + [5]:
        _det(f"concepto-{n}-de-2016", _archivo(n, 2016))
    docs = ScrapIcbf().scrap("2016-01-01", "2016-12-31")
    assert len(docs) == 101
    listados = [c for c in responses.calls if "field_anio_value" in c.request.url]
    assert [c.request.params["page"] for c in listados] == ["0", "1"]


@responses.activate
def test_detalle_sin_archivo_se_omite():
    _anio(2015, [_fila(75, 2015), _fila(74, 2015)])
    _det("concepto-75-de-2015")
    _det("concepto-74-de-2015", _archivo(74, 2015))
    avisos = []
    docs = ScrapIcbf().scrap("2015-01-01", "2015-12-31", on_progress=avisos.append)
    assert [d.title for d in docs] == ["CTO_ICBF_0074_2015"]
    assert any("CTO_ICBF_0075_2015 no trae archivo" in a for a in avisos)


@responses.activate
def test_dedup_por_archivo():
    _anio(2018, [_fila("11A", 2018), _fila("11B", 2018)])
    _det("concepto-11A-de-2018", "MISMO.docx")
    _det("concepto-11B-de-2018", "MISMO.docx")
    avisos = []
    docs = ScrapIcbf().scrap("2018-01-01", "2018-12-31", on_progress=avisos.append)
    assert [d.title for d in docs] == ["CTO_ICBF_0011A_2018"]
    assert any("CTO_ICBF_0011B_2018 repite un archivo" in a for a in avisos)


@responses.activate
def test_numero_fuera_de_patron_sin_verificar():
    _anio(2019, [_fila("S/N", 2019, slug="concepto-sn-de-2019")])
    _det("concepto-sn-de-2019", "X.docx")
    avisos = []
    docs = ScrapIcbf().scrap("2019-01-01", "2019-12-31", on_progress=avisos.append)
    assert docs[0].title == "CTO_ICBF_SN_2019"
    assert docs[0].title_unverified is True
    assert any("número de concepto inesperado" in a for a in avisos)


@responses.activate
def test_stop_event():
    _anio(2015, [_fila(1, 2015)])
    _det("concepto-1-de-2015", _archivo(1, 2015))
    stop = threading.Event()

    def progreso(texto):
        if "2016" in texto:
            stop.set()

    docs = ScrapIcbf().scrap("2015-01-01", "2020-12-31", stop_event=stop, on_progress=progreso)
    assert [d.title for d in docs] == ["CTO_ICBF_0001_2015"]
    assert not any("field_anio_value=2017" in c.request.url for c in responses.calls)


@responses.activate
def test_falla_de_un_anio_y_de_un_detalle():
    _anio(2015, [], status=500)
    _anio(2016, [_fila(2, 2016), _fila(1, 2016)])
    _det("concepto-2-de-2016", status=500)
    _det("concepto-1-de-2016", _archivo(1, 2016))
    avisos = []
    docs = ScrapIcbf().scrap("2015-01-01", "2016-12-31", on_progress=avisos.append)
    assert [d.title for d in docs] == ["CTO_ICBF_0001_2016"]
    assert any("Error consultando los conceptos de 2015" in a for a in avisos)
    assert any("Error consultando el detalle de CTO_ICBF_0002_2016" in a for a in avisos)


@responses.activate
def test_listado_vacio_avisa_error():
    _anio(2024, [])
    _anio(2025, [])
    avisos = []
    assert ScrapIcbf().scrap("2024-01-01", "2025-12-31", on_progress=avisos.append) == []
    assert any("Error: el listado no trajo ningún concepto" in a for a in avisos)


@responses.activate
def test_limit():
    _anio(2016, [_fila(3, 2016), _fila(2, 2016), _fila(1, 2016)])
    for n in (3, 2, 1):
        _det(f"concepto-{n}-de-2016", _archivo(n, 2016))
    docs = ScrapIcbf().scrap("2016-01-01", "2016-12-31", limit=2)
    assert [d.title for d in docs] == ["CTO_ICBF_0003_2016", "CTO_ICBF_0002_2016"]
    assert not any("concepto-1-de-2016" in c.request.url for c in responses.calls)


def test_corrida_diaria_de_enero_revisa_el_anio_anterior():
    # Un concepto de 2026 subido a mediados de enero de 2027 tiene que
    # entrar: la ventana diaria ampliada debe alcanzar todavía 2026.
    import datetime
    for hoy in (datetime.date(2027, 1, 15), datetime.date(2027, 1, 31)):
        fini = hoy - datetime.timedelta(days=ScrapIcbf.scheduled_min_lookback_days)
        assert 2026 in _anios(fini.isoformat(), hoy.isoformat())


@responses.activate
def test_falla_de_una_pagina_conserva_las_anteriores():
    # 2016 tiene dos páginas: si la segunda falla, los 100 conceptos de la
    # primera se descargan igual y la corrida avisa que el año quedó a medias.
    pagina_llena = [_fila(n, 2016) for n in range(200, 100, -1)]  # 100 filas
    _anio(2016, pagina_llena)
    responses.add(
        responses.GET, _LISTADO_URL, status=503,
        match=[matchers.query_param_matcher({"field_anio_value": "2016", "page": "1"})],
    )
    for n in range(101, 201):
        _det(f"concepto-{n}-de-2016", _archivo(n, 2016))
    avisos = []
    docs = ScrapIcbf().scrap("2016-01-01", "2016-12-31", on_progress=avisos.append)
    assert len(docs) == 100
    assert any("Error consultando la página 2 de los conceptos de 2016" in a and "incompleto" in a for a in avisos)


@responses.activate
def test_numero_repetido_no_pisa_el_archivo():
    # Dos filas distintas con el mismo número y año: cada una se guarda en su
    # propio archivo (sufijo estable sacado de su URL), sin importar el orden,
    # y la corrida avisa para revisarlas a mano.
    import hashlib
    _anio(2015, [_fila(10, 2015, slug="concepto-10-de-2015"), _fila(10, 2015, slug="concepto-10-de-2015-0")])
    _det("concepto-10-de-2015", "A.docx")
    _det("concepto-10-de-2015-0", "B.docx")
    avisos = []
    docs = ScrapIcbf().scrap("2015-01-01", "2015-12-31", on_progress=avisos.append)
    assert [d.title for d in docs] == ["CTO_ICBF_0010_2015", "CTO_ICBF_0010_2015"]
    assert all(d.title_unverified for d in docs)
    for d in docs:
        h = hashlib.sha1(d.link["url"].encode()).hexdigest()[:7]
        assert d.save_path == f"{_SOURCE}/{d.f_public}/Concepto/CTO_ICBF_0010_2015_h{h}(extension)"
    assert docs[0].save_path != docs[1].save_path
    assert any("CTO_ICBF_0010_2015 aparece 2 veces" in a for a in avisos)


@responses.activate
def test_paginacion_sigue_al_paginador_no_al_tamano_de_pagina():
    # Si el sitio pasa a mostrar 50 por página, se siguen pidiendo páginas
    # mientras el paginador ofrezca "página siguiente".
    p0 = [_fila(n, 2016) for n in range(166, 116, -1)]
    p1 = [_fila(n, 2016) for n in range(116, 66, -1)]
    p2 = [_fila(n, 2016) for n in range(66, 0, -1)]
    _anio(2016, p0, p1, p2)
    for n in range(1, 167):
        _det(f"concepto-{n}-de-2016", _archivo(n, 2016))
    docs = ScrapIcbf().scrap("2016-01-01", "2016-12-31")
    assert len(docs) == 166


@responses.activate
def test_tope_de_paginas_avisa(monkeypatch):
    from core.scrapers.families import icbf as icbf_module
    monkeypatch.setattr(icbf_module, "_PAGINAS_POR_ANIO_TOPE", 2)
    _anio(2016, [_fila(3, 2016)], [_fila(2, 2016)], [_fila(1, 2016)])
    for n in (3, 2, 1):
        _det(f"concepto-{n}-de-2016", _archivo(n, 2016))
    avisos = []
    docs = ScrapIcbf().scrap("2016-01-01", "2016-12-31", on_progress=avisos.append)
    assert len(docs) == 2
    assert any("tope de 2 páginas" in a and "2016" in a for a in avisos)


def test_fecha_del_encabezado_formatos_reales():
    # Formatos copiados de conceptos reales del sitio (2026-11-19).
    casos = [
        ("CONCEPTO 10 DE 2026(30 de julio)INSTITUTO COLOMBIANO", "10", 2026, datetime.date(2026, 7, 30)),
        ("CONCEPTO No. 4 DE 2026(14 de mayo)Para: ADRIANA", "4", 2026, datetime.date(2026, 5, 14)),
        ("CONCEPTO 7 DE 2022(mayo 13)INSTITUTO", "7", 2022, datetime.date(2022, 5, 13)),
        ("CONCEPTO 66 DE 2019(28 de Noviembre)INSTITUTO", "66", 2019, datetime.date(2019, 11, 28)),
        ("CONCEPTO 117 DE 2016 (septiembre 22) INSTITUTO", "117", 2016, datetime.date(2016, 9, 22)),
        ("CONCEPTO 3C DE 2020 (2 de marzo) INSTITUTO", "3C", 2020, datetime.date(2020, 3, 2)),
        ("CONCEPTO 142-1 DE 2015 (1 de abril) INSTITUTO", "142-1", 2015, datetime.date(2015, 4, 1)),
    ]
    for texto, numero, anio, esperado in casos:
        assert _fecha_del_encabezado(texto, numero, anio) == (esperado, ""), texto


def test_fecha_del_encabezado_casos_sin_fecha():
    # Reales: sin fecha en el encabezado (56 de 2019, 50 de 2019 con "()").
    assert _fecha_del_encabezado("CONCEPTO 56 DE 2019 INSTITUTO COLOMBIANO", "56", 2019)[0] is None
    assert _fecha_del_encabezado("CONCEPTO 50 DE 2019 () INSTITUTO", "50", 2019)[0] is None
    # Reales: el archivo es de otro concepto (13 de 2015 abre el 14 de 2014;
    # 2 de 2026 dice "2 DE 2025"): no se confía en su fecha.
    fecha, motivo = _fecha_del_encabezado("CONCEPTO 14 DE 2014 (enero 30) INSTITUTO", "13", 2015)
    assert fecha is None and "concepto 14 de 2014" in motivo
    assert _fecha_del_encabezado("CONCEPTO No. 2 DE 2025 (20 de abril) INSTITUTO", "2", 2026)[0] is None
    assert _fecha_del_encabezado("Resolución 5 de 2020", "5", 2020)[0] is None
    assert _fecha_del_encabezado("CONCEPTO 5 DE 2020 (31 de febrero)", "5", 2020)[0] is None
    assert _fecha_del_encabezado(None, "5", 2020)[0] is None


def test_texto_inicial_docx():
    assert _texto_inicial_docx(_docx("CONCEPTO 10 DE 2026 (30 de julio)")).startswith(
        "CONCEPTO 10 DE 2026 (30 de julio) INSTITUTO COLOMBIANO"
    )
    assert _texto_inicial_docx(b"no es un zip") is None


@responses.activate
def test_sin_fecha_legible_queda_el_1_de_enero_con_aviso():
    _anio(2019, [_fila(56, 2019)])
    _det("concepto-56-de-2019", _archivo(56, 2019), encabezado="CONCEPTO 56 DE 2019 INSTITUTO COLOMBIANO")
    avisos = []
    docs = ScrapIcbf().scrap("2019-01-01", "2019-12-31", on_progress=avisos.append)
    assert docs[0].f_public == docs[0].f_providencia == "2019-01-01"
    assert any("CTO_ICBF_0056_2019 queda con fecha 2019-01-01" in a for a in avisos)


@responses.activate
def test_si_no_baja_el_docx_se_deja_para_la_proxima_corrida():
    # Guardarlo con el 1 de enero lo dejaría así para siempre.
    _anio(2026, [_fila(10, 2026), _fila(7, 2026)])
    _det("concepto-10-de-2026", _archivo(10, 2026), status_docx=503)
    _det("concepto-7-de-2026", _archivo(7, 2026))
    avisos = []
    docs = ScrapIcbf().scrap("2026-01-01", "2026-12-31", on_progress=avisos.append)
    assert [d.title for d in docs] == ["CTO_ICBF_0007_2026"]
    assert any("Error descargando CTO_ICBF_0010_2026" in a and "próxima corrida" in a for a in avisos)


def test_identidad_no_depende_de_la_fecha():
    assert ScrapIcbf.doc_id_uses_publication_date is False
