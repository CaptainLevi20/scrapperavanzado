import threading

import responses
from responses import matchers

from core.scrapers.families.icbf import (
    _ANIO_MINIMO,
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


def _listado(*filas) -> str:
    return (
        '<html><body><table class="cols-5"><thead><tr><th>Categoría</th><th>Número</th><th>Año</th>'
        "<th>Temática</th><th></th></tr></thead>\n<tbody>\n" + "".join(filas) + "</tbody></table></body></html>"
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
        responses.add(
            responses.GET, _LISTADO_URL, body=_listado(*filas), status=status,
            match=[matchers.query_param_matcher({"field_anio_value": str(anio), "page": str(p)})],
        )


def _det(slug, archivo=None, status=200):
    responses.add(responses.GET, f"{_SITIO}/normograma/{slug}", body=_detalle(archivo), status=status)


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
    assert d.f_public == d.f_providencia == "2026-01-01"
    assert d.detalle == "Respuesta Kick Boxing"
    assert d.link == {"url": f"{_SITIO}/sites/default/files/normas/CONCEPTO%2010%20DE%202026.docx", "method": "GET"}
    assert d.save_path == f"{_SOURCE}/2026-01-01/Concepto/CTO_ICBF_0010_2026(extension)"
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
