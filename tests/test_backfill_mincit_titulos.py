import pytest

from core import backfill_mincit_titulos as bf
from core.backfill_mincit_titulos import backfill, es_titulo_canonico
from core.db import repository


@pytest.mark.parametrize(
    "titulo, esperado",
    [
        ("C_MCIT_0065_1995", True),
        ("C_MCIT_SN_2020_2", True),
        ("C_MCIT_CIR2020-103_2020", True),
        ("C_MCIT_100-003_2022", True),
        ("D0444967", True),
        ("Circular Externa 065 de 1995", False),
        ("ANEXO No 01 MCIT - Licencia Previa", False),
    ],
)
def test_es_titulo_canonico(titulo, esperado):
    assert es_titulo_canonico(titulo) is esperado


_CARPETA = "Ministerio de Comercio, Industria y Turismo"


def _fuente(db_session):
    repository.create_source_family(db_session, key="mincit", display_name="MinCIT")
    return repository.create_source(db_session, family_key="mincit", name=_CARPETA, family_params={})


def _sin_almacenamiento(monkeypatch):
    monkeypatch.setattr(bf.storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(bf.storage_sync, "delete_object", lambda *a: None)


def test_backfill_corrige_solo_titulos_crudos(db_session, monkeypatch):
    source = _fuente(db_session)
    crudo = repository.insert_document(
        db_session, doc_id="m-1", source_id=source.id, title="Circular Externa 065 de 1995",
        storage_bucket="iurisync-test",
        storage_key=f"{_CARPETA}/1995-06-01/Circular/Circular Externa 065 de 1995.pdf",
    )
    bueno = repository.insert_document(
        db_session, doc_id="m-2", source_id=source.id, title="R_MCIT_0365_2025",
        storage_bucket="iurisync-test",
        storage_key=f"{_CARPETA}/2026-02-12/Resolución/R_MCIT_0365_2025.pdf",
    )
    _sin_almacenamiento(monkeypatch)

    # Aunque el sitio calcule otro título para el que ya estaba bien, no se toca.
    resultado = backfill(db_session, {"m-1": "C_MCIT_0065_1995", "m-2": "R_MCIT_0365_2025_2"})

    refrescado = repository.get_document(db_session, crudo.id)
    assert refrescado.title == "C_MCIT_0065_1995"
    assert refrescado.storage_key == f"{_CARPETA}/1995-06-01/Circular/C_MCIT_0065_1995.pdf"
    assert repository.get_document(db_session, bueno.id).title == "R_MCIT_0365_2025"
    assert resultado["documentos_actualizados"] == 1


def test_backfill_es_idempotente(db_session, monkeypatch):
    source = _fuente(db_session)
    repository.insert_document(
        db_session, doc_id="m-1", source_id=source.id, title="Circular Externa 065 de 1995",
        storage_bucket="iurisync-test",
        storage_key=f"{_CARPETA}/1995-06-01/Circular/Circular Externa 065 de 1995.pdf",
    )
    _sin_almacenamiento(monkeypatch)

    assert backfill(db_session, {"m-1": "C_MCIT_0065_1995"})["documentos_actualizados"] == 1
    assert backfill(db_session, {"m-1": "C_MCIT_0065_1995"})["documentos_actualizados"] == 0


def test_backfill_simular_no_cambia_nada(db_session, monkeypatch):
    source = _fuente(db_session)
    doc = repository.insert_document(
        db_session, doc_id="m-1", source_id=source.id, title="Circular Externa 065 de 1995",
        storage_bucket="iurisync-test",
        storage_key=f"{_CARPETA}/1995-06-01/Circular/Circular Externa 065 de 1995.pdf",
    )
    _sin_almacenamiento(monkeypatch)

    resultado = backfill(db_session, {"m-1": "C_MCIT_0065_1995"}, simular=True)

    assert resultado["documentos_actualizados"] == 1
    assert repository.get_document(db_session, doc.id).title == "Circular Externa 065 de 1995"
