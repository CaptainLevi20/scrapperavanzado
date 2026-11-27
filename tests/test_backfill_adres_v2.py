from datetime import date

import pytest

from core import backfill_adres_v2 as bf
from core.backfill_adres_v2 import backfill, clave_archivo, elegir_coincidencia, indice_del_sitio, ya_migrado
from core.db import repository
from core.models import RawDocModel
from core.scrapers.families.adres import _SOURCE
from core.utils import compute_doc_id, storage_path

_VIEJA = "https://www.adres.gov.co/normativa/ResolucionesADRES/"
_NUEVA = "https://www.adres.gov.co/api/media/file/"


def _nuevo(archivo, title, f_public, tipo="Resolución", detalle="Epígrafe"):
    return RawDocModel(
        source=_SOURCE, link={"url": _NUEVA + archivo, "method": "GET"}, title=title, tipo=tipo,
        f_public=f_public, f_providencia=f_public, detalle=detalle,
        save_path=storage_path(_SOURCE, f_public, tipo, f"{title}(extension)"),
    )


# --- lógica pura (sin base de datos) -----------------------------------------

def test_clave_archivo_compara_sin_codificar_ni_mayusculas():
    assert clave_archivo(_VIEJA + "Resoluci%C3%B3n%20137%20de%202022.pdf") == "resolución 137 de 2022.pdf"
    assert clave_archivo(_NUEVA + "Resolución 137 de 2022.pdf") == "resolución 137 de 2022.pdf"
    assert clave_archivo(None) == ""


def test_ya_migrado():
    assert ya_migrado(_NUEVA + "x.pdf")
    assert not ya_migrado(_VIEJA + "x.pdf")
    assert not ya_migrado(None)


def test_elegir_coincidencia_por_nombre_de_archivo():
    nuevo = _nuevo("Resolucion_199531_de_2026.pdf", "R_ADRES_199531_2026", "2026-10-01")
    indice = indice_del_sitio([nuevo])
    assert elegir_coincidencia(_VIEJA + "Resolucion_199531_de_2026.pdf", date(2026, 10, 1), indice) is nuevo
    assert elegir_coincidencia(_VIEJA + "otro.pdf", date(2026, 10, 1), indice) is None


def test_elegir_coincidencia_un_solo_candidato_acepta_la_fecha_corregida():
    # La v2 corrige la fecha de "2707 de 2020" (Fecha 29/05/2021 -> 2020-05-29).
    nuevo = _nuevo("Resolución número 2707 de 2020.pdf", "R_ADRES_2707_2020", "2020-05-29")
    indice = indice_del_sitio([nuevo])
    assert elegir_coincidencia(_VIEJA + "Resoluci%C3%B3n%20n%C3%BAmero%202707%20de%202020.pdf", date(2021, 5, 29), indice) is nuevo


def test_elegir_coincidencia_varios_candidatos_desempata_por_fecha():
    a = _nuevo("0001.pdf", "C_ADRES_0001_2018", "2018-01-10", tipo="Circular")
    b = _nuevo("0001.pdf", "C_ADRES_0001_2019", "2019-02-11", tipo="Circular")
    indice = indice_del_sitio([a, b])
    assert elegir_coincidencia(_VIEJA + "0001.pdf", date(2019, 2, 11), indice) is b
    assert elegir_coincidencia(_VIEJA + "0001.pdf", date(2020, 1, 1), indice) == "ambiguo"
    assert elegir_coincidencia(_VIEJA + "0001.pdf", None, indice) == "ambiguo"


def test_documentos_del_sitio_no_sigue_si_el_listado_vino_incompleto():
    class _Roto:
        def scrap(self, fini, ffin, on_progress=None):
            on_progress("[ADRES] Error consultando Resoluciones: 503")
            return []

    with pytest.raises(RuntimeError):
        bf.documentos_del_sitio(_Roto())


# --- backfill contra la base (necesita Postgres) -----------------------------

def _fuente(db_session):
    repository.create_source_family(db_session, key="adres", display_name="ADRES")
    return repository.create_source(db_session, family_key="adres", name=_SOURCE, family_params={})


def _guardado(db_session, source, archivo="Resolucion_199531_de_2026.pdf", f_public=date(2026, 10, 1), doc_id="viejo-1"):
    return repository.insert_document(
        db_session, doc_id=doc_id, source_id=source.id, title=archivo.rsplit(".", 1)[0],
        source_url=_VIEJA + archivo, f_public=f_public, storage_bucket="iurisync-test",
        storage_key=f"{_SOURCE}/{f_public.isoformat()}/Resolución/{archivo}",
    )


def _sin_almacenamiento(monkeypatch):
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)
    monkeypatch.setattr(bf.storage_sync, "object_exists", lambda *a: True)


def test_backfill_simula_por_defecto(db_session, monkeypatch):
    source = _fuente(db_session)
    doc = _guardado(db_session, source)
    _sin_almacenamiento(monkeypatch)
    nuevo = _nuevo("Resolucion_199531_de_2026.pdf", "R_ADRES_199531_2026", "2026-10-01")

    resultado = backfill(db_session, [nuevo])

    assert resultado["actualizados"] == 1
    refrescado = repository.get_document(db_session, doc.id)
    assert refrescado.doc_id == "viejo-1"
    assert refrescado.source_url == _VIEJA + "Resolucion_199531_de_2026.pdf"


def test_backfill_aplicar_cambia_identidad_titulo_y_archivo(db_session, monkeypatch):
    source = _fuente(db_session)
    doc = _guardado(db_session, source)
    _sin_almacenamiento(monkeypatch)
    nuevo = _nuevo("Resolucion_199531_de_2026.pdf", "R_ADRES_199531_2026", "2026-10-01", detalle="Se adiciona …")

    resultado = backfill(db_session, [nuevo], aplicar=True)

    assert resultado["actualizados"] == 1
    assert resultado["archivos_renombrados"] == 1
    refrescado = repository.get_document(db_session, doc.id)
    assert refrescado.doc_id == compute_doc_id(nuevo)
    assert refrescado.source_url == nuevo.link["url"]
    assert refrescado.title == "R_ADRES_199531_2026"
    assert refrescado.tipo == "Resolución"
    assert refrescado.f_public == refrescado.f_providencia == date(2026, 10, 1)
    assert refrescado.detalle == "Se adiciona …"
    assert refrescado.storage_key == f"{_SOURCE}/2026-10-01/Resolución/R_ADRES_199531_2026.pdf"


def test_backfill_segunda_corrida_no_cambia_nada(db_session, monkeypatch):
    source = _fuente(db_session)
    _guardado(db_session, source)
    _sin_almacenamiento(monkeypatch)
    nuevo = _nuevo("Resolucion_199531_de_2026.pdf", "R_ADRES_199531_2026", "2026-10-01")
    backfill(db_session, [nuevo], aplicar=True)

    resultado = backfill(db_session, [nuevo], aplicar=True)

    assert resultado["actualizados"] == 0
    assert resultado["ya_migrados"] == 1


def test_backfill_no_encontrado_queda_igual(db_session, monkeypatch):
    source = _fuente(db_session)
    doc = _guardado(db_session, source, archivo="no_existe.pdf")
    _sin_almacenamiento(monkeypatch)

    resultado = backfill(db_session, [], aplicar=True)

    assert resultado["sin_coincidencia"] == 1
    assert repository.get_document(db_session, doc.id).doc_id == "viejo-1"


def test_backfill_no_pisa_un_doc_id_existente_ni_junta_dos_guardados(db_session, monkeypatch):
    source = _fuente(db_session)
    nuevo = _nuevo("Resolucion_199531_de_2026.pdf", "R_ADRES_199531_2026", "2026-10-01")
    # Ya bajado por la v2 antes del script:
    repository.insert_document(
        db_session, doc_id=compute_doc_id(nuevo), source_id=source.id, title="R_ADRES_199531_2026",
        source_url=nuevo.link["url"], storage_bucket="iurisync-test", storage_key="x/R_ADRES_199531_2026.pdf",
    )
    doc = _guardado(db_session, source)
    _sin_almacenamiento(monkeypatch)

    resultado = backfill(db_session, [nuevo], aplicar=True)

    assert resultado["ambiguos"] == 1
    assert resultado["ya_migrados"] == 1
    assert repository.get_document(db_session, doc.id).doc_id == "viejo-1"
