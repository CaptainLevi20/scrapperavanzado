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
