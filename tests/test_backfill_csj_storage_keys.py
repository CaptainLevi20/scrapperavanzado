from core.backfill_csj_storage_keys import backfill
import core.backfill_csj_storage_keys as backfill_module
from core.db import repository


def _csj_source(db_session):
    repository.create_source_family(db_session, key="corte_suprema", display_name="CSJ")
    return repository.create_source(db_session, family_key="corte_suprema", name="CSJ", family_params={})


def test_backfill_renames_object_and_updates_storage_key_when_mismatched(db_session, monkeypatch):
    source = _csj_source(db_session)
    doc = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="CSJ_SCT_ABC1234_2026",
        storage_bucket="iurisync-test",
        storage_key="CSJ/SCT/CSJ_SCT_doc_2026.pdf",
    )

    renamed = []
    monkeypatch.setattr(
        backfill_module,
        "rename_object",
        lambda bucket, old_key, new_key: renamed.append((bucket, old_key, new_key)),
    )

    result = backfill(db_session)

    db_session.refresh(doc)
    assert doc.storage_key == "CSJ/SCT/CSJ_SCT_ABC1234_2026.pdf"
    assert renamed == [("iurisync-test", "CSJ/SCT/CSJ_SCT_doc_2026.pdf", "CSJ/SCT/CSJ_SCT_ABC1234_2026.pdf")]
    assert result["documents_updated"] == 1


def test_backfill_leaves_untouched_when_storage_key_already_matches_title(db_session, monkeypatch):
    source = _csj_source(db_session)
    doc = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="CSJ_SCT_ABC1234_2026",
        storage_bucket="iurisync-test",
        storage_key="CSJ/SCT/CSJ_SCT_ABC1234_2026.pdf",
    )

    renamed = []
    monkeypatch.setattr(
        backfill_module,
        "rename_object",
        lambda *a: renamed.append(a),
    )

    result = backfill(db_session)

    db_session.refresh(doc)
    assert doc.storage_key == "CSJ/SCT/CSJ_SCT_ABC1234_2026.pdf"
    assert renamed == []
    assert result["documents_updated"] == 0


def test_backfill_is_idempotent_across_two_runs(db_session, monkeypatch):
    source = _csj_source(db_session)
    doc = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="CSJ_SCT_ABC1234_2026",
        storage_bucket="iurisync-test",
        storage_key="CSJ/SCT/CSJ_SCT_doc_2026.pdf",
    )

    monkeypatch.setattr(backfill_module, "rename_object", lambda *a: None)

    backfill(db_session)
    second_result = backfill(db_session)

    db_session.refresh(doc)
    assert doc.storage_key == "CSJ/SCT/CSJ_SCT_ABC1234_2026.pdf"
    assert second_result["documents_updated"] == 0


def test_backfill_ignores_documents_from_other_sources(db_session, monkeypatch):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(
        db_session, family_key="samai", name="Consejo de Estado", family_params={}
    )
    repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="11001-03-26-000-2026-00084-00(74369)(RER)",
        storage_bucket="iurisync-test",
        storage_key="Consejo de Estado/seccion/2026-08-03/Auto/11001-03-26-000-2026-00084-00.pdf",
    )

    called = []
    monkeypatch.setattr(backfill_module, "rename_object", lambda *a: called.append(a))

    result = backfill(db_session)

    assert called == []
    assert result["documents_updated"] == 0


def test_backfill_continues_after_rename_failure(db_session, monkeypatch):
    source = _csj_source(db_session)
    doc1 = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="CSJ_SCT_ABC1234_2026",
        storage_bucket="iurisync-test",
        storage_key="CSJ/SCT/CSJ_SCT_doc_2026.pdf",
    )
    doc2 = repository.insert_document(
        db_session,
        doc_id="doc-2",
        source_id=source.id,
        title="CSJ_SCT_DEF5678_2026",
        storage_bucket="iurisync-test",
        storage_key="CSJ/SCT/CSJ_SCT_doc2_2026.pdf",
    )

    def rename_with_failure(bucket, old_key, new_key):
        if "doc_2026" in old_key and "doc2" not in old_key:
            raise RuntimeError("MinIO no disponible")

    monkeypatch.setattr(backfill_module, "rename_object", rename_with_failure)

    result = backfill(db_session)

    db_session.refresh(doc1)
    db_session.refresh(doc2)
    assert doc1.storage_key == "CSJ/SCT/CSJ_SCT_doc_2026.pdf"  # sin cambios, la renombrada falló
    assert doc2.storage_key == "CSJ/SCT/CSJ_SCT_DEF5678_2026.pdf"  # esta sí se procesó
    assert result["documents_updated"] == 1
