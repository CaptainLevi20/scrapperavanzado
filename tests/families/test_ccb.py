import datetime
import threading

import responses
from responses import matchers

from core.naming import es_familia_con_actuaciones
from core.scrapers.families.ccb import (
    _ANIO_MINIMO,
    _API,
    _SCOPE_LAUDOS,
    _SEARCH_URL,
    _SOURCE,
    _fecha_issued,
    _radicado,
    ScrapCcb,
)
from core.scrapers.registry import FAMILY_REGISTRY


def _m(valor):
    return [{"value": valor, "language": None, "authority": None, "confidence": -1, "place": 0}]


def _item(uuid, *, radicado="159970", title="159970: MANUFACTURAS TERPIEL SAS VS. MOLASASA COL SAS",
          issued="2026-05-29", accessioned="2026-10-01T15:09:13Z", dc_type=None, handle=None):
    # Recorte de un ítem real de /discover/search/objects.
    metadata = {
        "dc.title": _m(title),
        "dc.date.accessioned": _m(accessioned),
        "dc.contributor.convocante": _m("MANUFACTURAS TERPIEL SAS"),
    }
    if radicado is not None:
        metadata["dc.description.radicado"] = _m(radicado)
    if issued is not None:
        metadata["dc.date.issued"] = _m(issued)
    if dc_type is not None:
        metadata["dc.type"] = _m(dc_type)
    return {
        "id": uuid, "uuid": uuid, "name": title, "handle": handle or f"11520/{uuid}",
        "metadata": metadata, "type": "item",
    }


def _busqueda(items, pagina=0, total_paginas=1):
    return {
        "_embedded": {"searchResult": {
            "_embedded": {"objects": [
                {"type": "discover", "_embedded": {"indexableObject": it}} for it in items
            ]},
            "page": {"number": pagina, "size": 100, "totalPages": total_paginas, "totalElements": len(items)},
        }},
    }


def _bitstream(uuid, md5, nombre="159970 MANUFACTURAS TERPIEL.pdf", seq=1, bundle="ORIGINAL"):
    return {"uuid": uuid, "name": nombre, "sizeBytes": 1000, "sequenceId": seq, "bundleName": bundle,
            "checkSum": {"checkSumAlgorithm": "MD5", "value": md5}}


def _bundles(*originales, extra=True):
    bundles = [{"name": "ORIGINAL", "_embedded": {"bitstreams": {"_embedded": {"bitstreams": list(originales)}}}}]
    if extra:
        for nombre in ("TEXT", "THUMBNAIL", "LICENSE"):
            bundles.append({"name": nombre, "_embedded": {"bitstreams": {"_embedded": {"bitstreams": [
                _bitstream(f"{nombre}-bit", f"{nombre}-md5", nombre="x.txt", bundle=nombre)
            ]}}}})
    return {"_embedded": {"bundles": bundles}}


def _listado(items, pagina=0, total_paginas=1, status=200, fini="2026-01-01", ffin="2026-12-31"):
    responses.add(
        responses.GET, _SEARCH_URL, status=status,
        json=_busqueda(items, pagina, total_paginas) if status == 200 else {"error": "x"},
        match=[matchers.query_param_matcher({
            "scope": _SCOPE_LAUDOS, "dsoType": "ITEM",
            "query": f"dc.date.accessioned_dt:[{fini}T00:00:00Z TO {ffin}T23:59:59Z]",
            "sort": "dc.date.accessioned,DESC", "size": "100", "page": str(pagina),
        })],
    )


def _archivos(item_uuid, *bitstreams, status=200, extra=True):
    responses.add(
        responses.GET, f"{_API}/core/items/{item_uuid}/bundles", status=status,
        json=_bundles(*bitstreams, extra=extra) if status == 200 else {"error": "x"},
        match=[matchers.query_param_matcher({"embed": "bitstreams"})],
    )


def _scrap(fini="2026-01-01", ffin="2026-12-31", **kw):
    return ScrapCcb().scrap(fini, ffin, **kw)


def test_source_registro_y_atributos():
    assert _SOURCE == "Cámara de Comercio de Bogotá"
    assert _ANIO_MINIMO == 2015
    assert FAMILY_REGISTRY["ccb"] is ScrapCcb
    assert ScrapCcb.filters_by_publication_date is True
    assert ScrapCcb.checks_for_republication is False
    assert ScrapCcb.scheduled_min_lookback_days == 7
    assert ScrapCcb.alerta_margen_dias == 120


def test_radicado_toma_los_digitos_iniciales():
    assert _radicado("137003Encargo fiduciario") == "137003"
    assert _radicado("137562\n") == "137562"
    assert _radicado("4920/5468") == "4920"
    assert _radicado("", "157594: X VS. Y") == "157594"
    assert _radicado("", "TRIBUNAL ARBITRAL DE X", "151064 ESTEFANIA.pdf") == "151064"
    assert _radicado("SN 125", "TRIBUNAL ARBITRAL", "laudo.pdf") is None


def test_fecha_issued():
    assert _fecha_issued("2026-05-29") == datetime.date(2026, 5, 29)
    assert _fecha_issued("2019-07") == datetime.date(2019, 7, 1)
    assert _fecha_issued("") is None


@responses.activate
def test_item_a_documento():
    _listado([_item("i1")])
    _archivos("i1", _bitstream("b1", "md5-1"))

    [doc] = _scrap()

    assert doc.title == "LA_CCB_159970_2026"
    assert doc.tipo == "Laudo arbitral"
    assert doc.f_providencia == "2026-05-29"
    assert doc.f_public == "2026-10-01"
    assert doc.link == {"url": f"{_API}/core/bitstreams/b1/content", "method": "GET"}
    assert doc.detalle == "159970: MANUFACTURAS TERPIEL SAS VS. MOLASASA COL SAS"
    assert doc.title_unverified is False
    assert doc.save_path.startswith(f"{_SOURCE}/2026-05-29/Laudo arbitral/LA_CCB_159970_2026_h")
    assert doc.save_path.endswith("(extension)")


@responses.activate
def test_radicado_de_respaldo_del_titulo_y_del_pdf():
    _listado([
        _item("i1", radicado=None, title="157594: X VS. Y"),
        _item("i2", radicado=None, title="TRIBUNAL ARBITRAL DE X VS. Y"),
    ])
    _archivos("i1", _bitstream("b1", "md5-1"))
    _archivos("i2", _bitstream("b2", "md5-2", nombre="151064 ESTEFANIA.pdf"))

    assert [d.title for d in _scrap()] == ["LA_CCB_157594_2026", "LA_CCB_151064_2026"]


@responses.activate
def test_radicados_sucios():
    _listado([
        _item("i1", radicado="137003Encargo fiduciario"),
        _item("i2", radicado="137562\n"),
        _item("i3", radicado="4920/5468"),
    ])
    _archivos("i1", _bitstream("b1", "md5-1"))
    _archivos("i2", _bitstream("b2", "md5-2"))
    _archivos("i3", _bitstream("b3", "md5-3"))

    assert [d.title for d in _scrap()] == ["LA_CCB_137003_2026", "LA_CCB_137562_2026", "LA_CCB_4920_2026"]


@responses.activate
def test_sin_radicado_usa_el_titulo_sin_verificar():
    _listado([_item("i1", radicado="SN 125", title="TRIBUNAL ARBITRAL DE A/B VS. C")])
    _archivos("i1", _bitstream("b1", "md5-1", nombre="laudo.pdf"))

    [doc] = _scrap()

    # Lleva el número del ítem en la biblioteca (handle 11520/i1) para que
    # dos laudos con el mismo título no se pisen.
    assert doc.title == "TRIBUNAL ARBITRAL DE A-B VS. C_i1"
    assert doc.title_unverified is True
    assert doc.save_path.endswith("/TRIBUNAL ARBITRAL DE A-B VS. C_i1(extension)")
    assert not es_familia_con_actuaciones("ccb", doc.title)


@responses.activate
def test_fecha_issued_parcial_o_ausente():
    _listado([_item("i1", issued="2026-03"), _item("i2", radicado="2", issued=None)])
    _archivos("i1", _bitstream("b1", "md5-1"))
    _archivos("i2", _bitstream("b2", "md5-2"))
    avisos = []

    d1, d2 = _scrap(on_progress=avisos.append)

    assert d1.f_providencia == "2026-03-01"
    assert d2.f_providencia == d2.f_public == "2026-10-01"
    assert any("sin fecha del laudo" in a for a in avisos)


@responses.activate
def test_piso_por_anio_del_laudo_sin_pedir_bundles():
    _listado([_item("viejo", issued="2014-06-30", accessioned="2026-03-01T00:00:00Z"), _item("i1")])
    _archivos("i1", _bitstream("b1", "md5-1"))

    assert [d.title for d in _scrap()] == ["LA_CCB_159970_2026"]
    assert not any("viejo" in c.request.url for c in responses.calls)


@responses.activate
def test_paginacion_hasta_total_pages():
    _listado([_item("i1")], pagina=0, total_paginas=2)
    _listado([_item("i2", radicado="148862")], pagina=1, total_paginas=2)
    _archivos("i1", _bitstream("b1", "md5-1"))
    _archivos("i2", _bitstream("b2", "md5-2"))

    assert [d.title for d in _scrap()] == ["LA_CCB_159970_2026", "LA_CCB_148862_2026"]


@responses.activate
def test_cartilla_book_excluida():
    _listado([_item("i1", radicado=None, title="Estructura del Laudo Arbitral CAC - CCB", dc_type="book")])

    assert _scrap() == []


@responses.activate
def test_mismo_md5_en_dos_items_entra_una_vez():
    _listado([_item("i1", radicado="146034"), _item("i2", radicado="146034")])
    _archivos("i1", _bitstream("b1", "igual"))
    _archivos("i2", _bitstream("b2", "IGUAL"))
    avisos = []

    assert len(_scrap(on_progress=avisos.append)) == 1
    assert any("repite un PDF" in a for a in avisos)


@responses.activate
def test_mismo_radicado_y_anio_con_pdf_distinto_son_actuaciones():
    _listado([
        _item("i1", radicado="142529", issued="2025-06-10"),
        _item("i2", radicado="142529", issued="2025-08-13"),
    ])
    _archivos("i1", _bitstream("b1", "md5-1"))
    _archivos("i2", _bitstream("b2", "md5-2"))

    d1, d2 = _scrap()

    assert d1.title == d2.title == "LA_CCB_142529_2025"
    assert d1.save_path != d2.save_path
    assert es_familia_con_actuaciones("ccb", d1.title)


@responses.activate
def test_dos_pdf_en_original_el_segundo_es_anexo():
    _listado([_item("i1")])
    _archivos("i1", _bitstream("b2", "md5-2", seq=3), _bitstream("b1", "md5-1", seq=2))

    d1, d2 = _scrap()

    assert d1.title == "LA_CCB_159970_2026"
    assert d1.link["url"].endswith("/bitstreams/b1/content")
    assert d2.title == "LA_CCB_159970_2026_A01"
    assert all("TEXT" not in d.link["url"] for d in (d1, d2))


@responses.activate
def test_falla_de_bundles_sigue_con_los_demas():
    _listado([_item("i1"), _item("i2", radicado="148862")])
    _archivos("i1", status=500)
    _archivos("i2", _bitstream("b2", "md5-2"))
    avisos = []

    assert [d.title for d in _scrap(on_progress=avisos.append)] == ["LA_CCB_148862_2026"]
    assert any("archivos del ítem" in a for a in avisos)


@responses.activate
def test_falla_del_listado_devuelve_lo_acumulado():
    _listado([_item("i1")], pagina=0, total_paginas=2)
    _listado([], pagina=1, status=500)
    _archivos("i1", _bitstream("b1", "md5-1"))
    avisos = []

    assert [d.title for d in _scrap(on_progress=avisos.append)] == ["LA_CCB_159970_2026"]
    assert any("Error consultando" in a for a in avisos)


@responses.activate
def test_limit_y_stop_event():
    _listado([_item("i1"), _item("i2", radicado="148862")])
    _archivos("i1", _bitstream("b1", "md5-1"))
    _archivos("i2", _bitstream("b2", "md5-2"))

    assert len(_scrap(limit=1)) == 1

    parar = threading.Event()
    parar.set()
    assert _scrap(stop_event=parar) == []


@responses.activate
def test_dos_laudos_sin_radicado_con_el_mismo_titulo_y_fecha_no_comparten_archivo():
    # Hallazgo de la revisión del PR #110: sin radicado, el nombre del archivo
    # era solo el título genérico. Dos laudos distintos con el mismo título y la
    # misma fecha del laudo caían en la misma clave de almacenamiento y el
    # segundo sobrescribía al primero.
    a = _item("a", radicado=None, title="Laudo arbitral")
    b = _item("b", radicado=None, title="Laudo arbitral")
    _listado([a, b])
    _archivos("a", _bitstream("bit-a", "md5-a", nombre="laudo.pdf"))
    _archivos("b", _bitstream("bit-b", "md5-b", nombre="laudo.pdf"))

    docs = _scrap()

    assert len(docs) == 2
    assert all(d.title_unverified for d in docs)
    assert docs[0].save_path != docs[1].save_path
