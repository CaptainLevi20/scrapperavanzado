import pytest

from core.db import repository
from core.backfill_constitucional_titles import backfill, nuevo_titulo_constitucional
from core import backfill_constitucional_titles as bf


@pytest.mark.parametrize(
    "viejo, esperado",
    [
        ("ST065_24", "ST-065-24"),
        ("SC034_26", "SC-034-26"),
        ("SU066_26", "SU-066-26"),
        ("A846_26", "A-846-26"),
        ("ST065_24_v2", "ST-065-24-v2"),
    ],
)
def test_nuevo_titulo_convierte_el_formato_viejo(viejo, esperado):
    assert nuevo_titulo_constitucional(viejo) == esperado


@pytest.mark.parametrize("ya_migrado", ["ST-065-24", "SU-066-26", "A-846-26-v2"])
def test_nuevo_titulo_devuelve_none_cuando_ya_esta_en_el_formato_nuevo(ya_migrado):
    assert nuevo_titulo_constitucional(ya_migrado) is None


@pytest.mark.parametrize("raro", ["", "cualquier cosa", "T-123-24"])
def test_nuevo_titulo_devuelve_none_cuando_no_reconoce_el_formato(raro):
    assert nuevo_titulo_constitucional(raro) is None


def _fuente_constitucional(db_session):
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    return repository.create_source(
        db_session, family_key="constitucional", name="Corte Constitucional", family_params={}
    )


def test_backfill_actualiza_titulo_y_renombra_el_archivo(db_session, monkeypatch):
    source = _fuente_constitucional(db_session)
    doc = repository.insert_document(
        db_session, doc_id="cc-1", source_id=source.id, title="ST065_24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-02-01/Sentencia de Tutela/ST065_24.rtf",
    )
    copiados = []
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda bucket, old, new: copiados.append((old, new)))
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)

    resultado = backfill(db_session)

    refrescado = repository.get_document(db_session, doc.id)
    assert refrescado.title == "ST-065-24"
    assert refrescado.storage_key == "Corte Constitucional/2024-02-01/Sentencia de Tutela/ST-065-24.rtf"
    assert copiados == [
        (
            "Corte Constitucional/2024-02-01/Sentencia de Tutela/ST065_24.rtf",
            "Corte Constitucional/2024-02-01/Sentencia de Tutela/ST-065-24.rtf",
        )
    ]
    assert resultado["documentos_actualizados"] == 1


def test_backfill_es_idempotente(db_session, monkeypatch):
    source = _fuente_constitucional(db_session)
    repository.insert_document(
        db_session, doc_id="cc-2", source_id=source.id, title="SC034_26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-01-01/Sentencia Constitucional/SC034_26.rtf",
    )
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)

    primera = backfill(db_session)
    segunda = backfill(db_session)

    assert primera["documentos_actualizados"] == 1
    assert segunda["documentos_actualizados"] == 0


def test_backfill_no_toca_documentos_de_otras_fuentes(db_session, monkeypatch):
    _fuente_constitucional(db_session)
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    otra = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
    doc = repository.insert_document(
        db_session, doc_id="otra-1", source_id=otra.id, title="ST065_24",
        storage_bucket="iurisync-test", storage_key="Consejo de Estado/x/ST065_24.pdf",
    )
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)

    resultado = backfill(db_session)

    assert repository.get_document(db_session, doc.id).title == "ST065_24"
    assert resultado["documentos_actualizados"] == 0
