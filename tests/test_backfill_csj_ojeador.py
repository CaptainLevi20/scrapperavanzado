from datetime import date

import responses
from responses import matchers

from core.backfill_csj_ojeador import _URL_VIEJA, backfill, elegir_coincidencia
from core.db import repository
from core.scrapers.families.corte_suprema import _doc_desde_resultado, _url_descarga
from core.utils import compute_doc_id

_SEARCH = "https://buscadorjurisprudenciabackend.cortesuprema.gov.co/search/"


def _hit(numerador="AC2794-2026", nombre="AC2794-2026 [2024-00858-00]", fecha="2026-04-30", id_="9001"):
    return {
        "id": id_,
        "Nombre": nombre,
        "Numerador": numerador,
        "FechaConsolidacionFirma": fecha,
        "Especialidad": "CIVIL",
        "Sala": "CIVIL",
        "TipoDeProvidencia": "AUTO",
        "Ubicacion": f"SALAS/CIVIL/2026/Dr. X/4.- Abril/Autos/{nombre}.docx",
    }


def _busqueda(rsps, codigo, hits):
    rsps.add(
        responses.GET, _SEARCH,
        json={"numFound": len(hits), "returned": len(hits), "docs": hits},
        match=[matchers.query_param_matcher({"query_text": codigo, "limit": "20", "page": "1"})],
    )


# --- elegir_coincidencia -----------------------------------------------------

def test_elegir_coincidencia_numerador_exacto():
    otro = _hit(numerador="AC4826-2026", nombre="AC4826-2026 [2020-00001-00]", id_="1")
    bueno = _hit(id_="2")
    assert elegir_coincidencia("AC2794-2026 [2024-00858-00]", [otro, bueno]) is bueno


def test_elegir_coincidencia_desempata_por_nombre():
    a = _hit(nombre="AC2794-2026 [2024-00858-00]", id_="1")
    b = _hit(nombre="AC2794-2026 [2019-00001-00]", id_="2")
    assert elegir_coincidencia("AC2794-2026 [2024-00858-00]", [b, a]) is a


def test_elegir_coincidencia_ambigua():
    # Dos archivos distintos (otra Ubicacion) con el mismo código.
    a = _hit(nombre="AC2794-2026 [2024-00858-00]", id_="1")
    b = dict(_hit(nombre="AC2794-2026 [2024-00858-00]", id_="2"), Ubicacion="SALAS/CIVIL/2026/otra/AC2794-2026.docx")
    assert elegir_coincidencia("AC2794-2026", [a, b]) == "ambiguo"


def test_elegir_coincidencia_sin_resultado_o_sin_codigo():
    assert elegir_coincidencia("AC2794-2026", []) is None
    assert elegir_coincidencia("doc_2025", [_hit()]) is None


def test_elegir_coincidencia_quita_sufijo_de_version():
    bueno = _hit()
    assert elegir_coincidencia("AC2794-2026 [2024-00858-00]-v2", [bueno]) is bueno


# --- backfill ------------------------------------------------------------------

def _fuente_csj(db_session):
    repository.create_source_family(db_session, key="corte_suprema", display_name="Corte Suprema de Justicia")
    return repository.create_source(db_session, family_key="corte_suprema", name="CSJ", family_params={})


def _doc_viejo(db_session, source, title="AC2794-2026 [2024-00858-00]", doc_id="viejo-1"):
    return repository.insert_document(
        db_session, doc_id=doc_id, source_id=source.id, title=title,
        source_url=_URL_VIEJA, f_public=date(2026, 4, 30),
        storage_bucket="iurisync-test", storage_key=f"CSJ/SCC/{title}.pdf",
    )


@responses.activate
def test_backfill_simular_no_cambia_nada(db_session):
    source = _fuente_csj(db_session)
    doc = _doc_viejo(db_session, source)
    _busqueda(responses, "AC2794-2026", [_hit()])

    resultado = backfill(db_session, aplicar=False)

    assert resultado["actualizados"] == 1
    refrescado = repository.get_document(db_session, doc.id)
    assert refrescado.doc_id == "viejo-1"
    assert refrescado.source_url == _URL_VIEJA


@responses.activate
def test_backfill_aplicar_reescribe_identidad_sin_tocar_archivo(db_session):
    source = _fuente_csj(db_session)
    doc = _doc_viejo(db_session, source)  # f_public viejo = fechaCreacion 2026-04-30
    hit = _hit(fecha="2026-04-28")  # fecha de firma en Ojeador
    _busqueda(responses, "AC2794-2026", [hit])

    resultado = backfill(db_session, aplicar=True)

    assert resultado["actualizados"] == 1
    refrescado = repository.get_document(db_session, doc.id)
    assert refrescado.doc_id == compute_doc_id(_doc_desde_resultado(hit))
    assert refrescado.source_url == _url_descarga(hit["Ubicacion"])
    assert refrescado.f_public == date(2026, 4, 28)
    assert refrescado.f_providencia == date(2026, 4, 28)
    assert refrescado.title == "AC2794-2026 [2024-00858-00]"
    assert refrescado.storage_key == "CSJ/SCC/AC2794-2026 [2024-00858-00].pdf"


@responses.activate
def test_backfill_sin_codigo_o_sin_resultado_queda_pendiente(db_session):
    source = _fuente_csj(db_session)
    _doc_viejo(db_session, source, title="doc_2025", doc_id="viejo-1")
    _doc_viejo(db_session, source, title="AC1-2026", doc_id="viejo-2")
    _busqueda(responses, "AC1-2026", [])

    resultado = backfill(db_session, aplicar=True)

    assert resultado["sin_coincidencia"] == 2
    assert resultado["actualizados"] == 0
    assert set(resultado["detalle_pendientes"]) == {"doc_2025", "AC1-2026"}


@responses.activate
def test_backfill_no_pisa_un_doc_id_que_ya_existe(db_session):
    source = _fuente_csj(db_session)
    hit = _hit()
    nuevo = _doc_desde_resultado(hit)
    repository.insert_document(
        db_session, doc_id=compute_doc_id(nuevo), source_id=source.id, title="AC2794-2026 [2024-00858-00]-v2",
        source_url=nuevo.link["url"], storage_bucket="iurisync-test", storage_key="CSJ/SCC/otro.pdf",
    )
    doc = _doc_viejo(db_session, source)
    _busqueda(responses, "AC2794-2026", [hit])

    resultado = backfill(db_session, aplicar=True)

    assert resultado["ambiguos"] == 1
    assert repository.get_document(db_session, doc.id).doc_id == "viejo-1"


@responses.activate
def test_backfill_segunda_corrida_no_cambia_nada(db_session):
    source = _fuente_csj(db_session)
    _doc_viejo(db_session, source)
    _busqueda(responses, "AC2794-2026", [_hit()])
    backfill(db_session, aplicar=True)

    resultado = backfill(db_session, aplicar=True)

    assert resultado["actualizados"] == 0
    assert resultado["ya_migrados"] == 1


@responses.activate
def test_backfill_busca_por_el_numerador_sin_la_referencia_entre_parentesis(db_session):
    # Real (dev, nov 2026): 156 de 176 quedaban "sin coincidencia" porque se
    # buscaba "AP4596-2026(73475)" en vez de "AP4596-2026".
    source = _fuente_csj(db_session)
    _doc_viejo(db_session, source, title="AP4596-2026(73475)")
    hit = _hit(numerador="AP4596-2026", nombre="AP4596-2026(73475)")
    _busqueda(responses, "AP4596-2026", [hit])

    resultado = backfill(db_session, aplicar=False)

    assert resultado["actualizados"] == 1
    assert resultado["sin_coincidencia"] == 0


def test_elegir_coincidencia_copias_del_mismo_archivo_no_son_ambiguas():
    # Ojeador indexa a veces la misma providencia varias veces (ids distintos,
    # misma Ubicacion): es un solo documento.
    a = _hit(numerador="SP754-2026", nombre="SP754-2026(64046)", id_="1")
    b = _hit(numerador="SP754-2026", nombre="SP754-2026(64046)", id_="2")
    assert elegir_coincidencia("SP754-2026(64046)", [a, b]) is a
