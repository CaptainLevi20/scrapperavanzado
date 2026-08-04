from pathlib import Path

from core.backfill_ce_titles import backfill
import core.backfill_ce_titles as backfill_module
from core.db import repository


def _consejo_de_estado_source(db_session):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    return repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})


def test_backfill_updates_title_when_number_found_on_first_page(db_session, monkeypatch):
    source = _consejo_de_estado_source(db_session)
    doc = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="25000-23-37-000-2021-00423-01(NRD)",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    monkeypatch.setattr(backfill_module, "download_file", lambda *_a, **_k: None)
    monkeypatch.setattr(
        backfill_module,
        "_extraer_texto_primera_pagina",
        lambda *_a, **_k: "Radicación  25000-23-37-000-2021-00423-01 (30146)",
    )

    result = backfill(db_session)

    db_session.refresh(doc)
    assert doc.title == "25000-23-37-000-2021-00423-01(30146)(NRD)"
    assert result["documents_updated"] == 1


def test_backfill_leaves_title_untouched_when_number_not_found(db_session, monkeypatch):
    source = _consejo_de_estado_source(db_session)
    doc = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="25000-23-37-000-2021-00423-01(NRD)",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    monkeypatch.setattr(backfill_module, "download_file", lambda *_a, **_k: None)
    monkeypatch.setattr(
        backfill_module,
        "_extraer_texto_primera_pagina",
        lambda *_a, **_k: "Radicación  25000-23-37-000-2021-00423-01",
    )

    result = backfill(db_session)

    db_session.refresh(doc)
    assert doc.title == "25000-23-37-000-2021-00423-01(NRD)"
    assert result["documents_updated"] == 0


def test_backfill_is_idempotent_across_two_runs(db_session, monkeypatch):
    source = _consejo_de_estado_source(db_session)
    doc = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="25000-23-37-000-2021-00423-01(NRD)",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    monkeypatch.setattr(backfill_module, "download_file", lambda *_a, **_k: None)
    monkeypatch.setattr(
        backfill_module,
        "_extraer_texto_primera_pagina",
        lambda *_a, **_k: "Radicación  25000-23-37-000-2021-00423-01 (30146)",
    )

    backfill(db_session)
    second_result = backfill(db_session)

    db_session.refresh(doc)
    assert doc.title == "25000-23-37-000-2021-00423-01(30146)(NRD)"
    assert second_result["documents_updated"] == 0


def test_backfill_updates_title_with_numero_ano_format(db_session, monkeypatch):
    # Confirmado con datos reales: el número extra no siempre es solo
    # dígitos — también aparece como "3104-2023" (número-año), y el guard de
    # idempotencia debe reconocerlo igual que el formato de solo dígitos.
    source = _consejo_de_estado_source(db_session)
    doc = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="66001-23-33-000-2017-00141-01(NRD)",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    monkeypatch.setattr(backfill_module, "download_file", lambda *_a, **_k: None)
    monkeypatch.setattr(
        backfill_module,
        "_extraer_texto_primera_pagina",
        lambda *_a, **_k: "Radicación:  66001-23-33-000-2017-00141-01 (3104-2023)",
    )

    result = backfill(db_session)
    second_result = backfill(db_session)

    db_session.refresh(doc)
    assert doc.title == "66001-23-33-000-2017-00141-01(3104-2023)(NRD)"
    assert result["documents_updated"] == 1
    assert second_result["documents_updated"] == 0


def test_backfill_ignores_documents_from_other_sources(db_session, monkeypatch):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    tribunal = repository.create_source(
        db_session, family_key="samai", name="Tribunal Administrativo de Cundinamarca", family_params={}
    )
    repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=tribunal.id,
        title="T_CUND_25001233300020260001200",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    called = []
    monkeypatch.setattr(backfill_module, "download_file", lambda *a, **k: called.append(a))

    result = backfill(db_session)

    assert called == []
    assert result["documents_updated"] == 0


def test_backfill_continues_after_database_commit_failure(db_session, monkeypatch):
    source = _consejo_de_estado_source(db_session)
    # First document: its update will fail
    doc1 = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="25000-23-37-000-2021-00423-01(NRD)",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )
    # Second document: should still be processed even after doc1 fails
    doc2 = repository.insert_document(
        db_session,
        doc_id="doc-2",
        source_id=source.id,
        title="25000-23-37-000-2021-00423-02(NRD)",
        storage_bucket="iurisync-test",
        storage_key="b.pdf",
    )

    monkeypatch.setattr(backfill_module, "download_file", lambda *_a, **_k: None)

    # Return text with numbers for both radicados
    call_count = [0]

    def mock_extract_text(*_a, **_k):
        call_count[0] += 1
        if call_count[0] == 1:
            return "Radicación  25000-23-37-000-2021-00423-01 (30146)"
        else:
            return "Radicación  25000-23-37-000-2021-00423-02 (30147)"

    monkeypatch.setattr(
        backfill_module,
        "_extraer_texto_primera_pagina",
        mock_extract_text,
    )

    # Track which documents were attempted for update
    update_attempts = []
    original_update = repository.update_document_title

    def update_with_failure(db, document_id, title):
        update_attempts.append(document_id)
        if document_id == doc1.id:
            # Simulate a database error during update
            raise RuntimeError("Database commit failed for doc1")
        return original_update(db, document_id, title)

    monkeypatch.setattr(
        repository,
        "update_document_title",
        update_with_failure,
    )

    result = backfill(db_session)

    # Verify that both documents were ATTEMPTED to be updated
    assert update_attempts == [doc1.id, doc2.id]

    # doc1 should remain unchanged due to the exception
    db_session.refresh(doc1)
    assert doc1.title == "25000-23-37-000-2021-00423-01(NRD)"

    # doc2 should still be updated even though doc1 failed
    db_session.refresh(doc2)
    assert doc2.title == "25000-23-37-000-2021-00423-02(30147)(NRD)"

    # Only doc2 should be successfully updated (doc1 failed)
    assert result["documents_updated"] == 1
