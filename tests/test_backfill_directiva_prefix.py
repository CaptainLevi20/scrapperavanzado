import pytest

from core.db import repository
from core.backfill_directiva_prefix import backfill, nuevo_titulo_directiva
from core import backfill_directiva_prefix as bf


@pytest.mark.parametrize(
    "viejo, esperado",
    [
        ("DIRECTIVA_ME_0005_2026", "DIR_ME_0005_2026"),
        ("DIRECTIVA_MI_0012_2025", "DIR_MI_0012_2025"),
        ("DIRECTIVA_MVCT_0006_2019", "DIR_MVCT_0006_2019"),
    ],
)
def test_nuevo_titulo_cambia_el_prefijo(viejo, esperado):
    assert nuevo_titulo_directiva(viejo) == esperado


@pytest.mark.parametrize("titulo", ["DIR_ME_0005_2026", "R_ME_0715_2001", "L2277022", "", "DIRECTIVAX_ME_1_2020"])
def test_nuevo_titulo_devuelve_none_para_lo_demas(titulo):
    assert nuevo_titulo_directiva(titulo) is None


def _fuente(db_session, family_key, name):
    repository.create_source_family(db_session, key=family_key, display_name=name)
    return repository.create_source(db_session, family_key=family_key, name=name, family_params={})


def test_backfill_renombra_directivas_conservando_la_carpeta(db_session, monkeypatch):
    source = _fuente(db_session, "mineducacion", "Ministerio de Educación Nacional")
    dire = repository.insert_document(
        db_session, doc_id="dir-1", source_id=source.id, title="DIRECTIVA_ME_0005_2026",
        storage_bucket="iurisync-test",
        storage_key="Ministerio de Educación Nacional/2026-07-24/Directiva/DIRECTIVA_ME_0005_2026.pdf",
    )
    otro = repository.insert_document(
        db_session, doc_id="reso-1", source_id=source.id, title="R_ME_0100_2026",
        storage_bucket="iurisync-test",
        storage_key="Ministerio de Educación Nacional/2026-01-01/Resolución/R_ME_0100_2026.pdf",
    )
    copiados = []
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda b, o, n: copiados.append((o, n)))
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)

    resultado = backfill(db_session)

    refrescado = repository.get_document(db_session, dire.id)
    assert refrescado.title == "DIR_ME_0005_2026"
    assert refrescado.storage_key == (
        "Ministerio de Educación Nacional/2026-07-24/Directiva/DIR_ME_0005_2026.pdf"
    )
    assert repository.get_document(db_session, otro.id).title == "R_ME_0100_2026"  # sin cambios
    assert resultado["renombrados"] == 1


def test_backfill_es_idempotente_y_no_toca_otras_fuentes(db_session, monkeypatch):
    minint = _fuente(db_session, "mininterior", "Ministerio del Interior")
    cc = _fuente(db_session, "constitucional", "Corte Constitucional")
    repository.insert_document(
        db_session, doc_id="dir-2", source_id=minint.id, title="DIRECTIVA_MI_0012_2025",
        storage_bucket="iurisync-test", storage_key="x/DIRECTIVA_MI_0012_2025.pdf",
    )
    d_cc = repository.insert_document(
        db_session, doc_id="cc-1", source_id=cc.id, title="DIRECTIVA_algo_raro",
        storage_bucket="iurisync-test", storage_key="y/z.rtf",
    )
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)

    primera = backfill(db_session)
    segunda = backfill(db_session)

    assert primera["renombrados"] == 1
    assert segunda["renombrados"] == 0
    # otra familia: intacto aunque el título empiece por DIRECTIVA_
    assert repository.get_document(db_session, d_cc.id).title == "DIRECTIVA_algo_raro"


def test_backfill_guarda_de_colision(db_session, monkeypatch):
    source = _fuente(db_session, "minvivienda", "Ministerio de Vivienda, Ciudad y Territorio")
    key = "Ministerio de Vivienda, Ciudad y Territorio/2019-01-01/Directiva/DIRECTIVA_MVCT_0006_2019.pdf"
    a = repository.insert_document(
        db_session, doc_id="col-a", source_id=source.id, title="DIRECTIVA_MVCT_0006_2019",
        storage_bucket="iurisync-test", storage_key=key,
    )
    b = repository.insert_document(
        db_session, doc_id="col-b", source_id=source.id, title="DIRECTIVA_MVCT_0006_2019",
        storage_bucket="iurisync-test", storage_key=key,
    )
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda *a: (_ for _ in ()).throw(AssertionError("no renombrar")))
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)

    resultado = backfill(db_session)

    assert repository.get_document(db_session, a.id).title == "DIRECTIVA_MVCT_0006_2019"
    assert repository.get_document(db_session, b.id).title == "DIRECTIVA_MVCT_0006_2019"
    assert resultado["colisiones_omitidas"] == 2
