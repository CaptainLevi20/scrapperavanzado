from core.db import repository
import core.storage_sync as storage_sync


def _rama_judicial_source(db_session):
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    return repository.create_source(db_session, family_key="rama_judicial", name="Tribunal", family_params={})


def test_reconcile_document_renames_when_the_stored_key_does_not_match(db_session, monkeypatch):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T_SANT_68001_33_33_007_2025_00290_02",
        storage_bucket="iurisync-test", storage_key="Rama Judicial/2026-08-06/Auto/placeholder.pdf",
    )

    renamed = []
    monkeypatch.setattr(storage_sync, "rename_object", lambda bucket, old_key, new_key: renamed.append((bucket, old_key, new_key)))

    result = storage_sync.reconcile_document(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert result is True
    assert renamed == [(
        "iurisync-test",
        "Rama Judicial/2026-08-06/Auto/placeholder.pdf",
        "Rama Judicial/2026-08-06/Auto/T_SANT_68001_33_33_007_2025_00290_02.pdf",
    )]
    db_session.refresh(doc)
    assert doc.storage_key == "Rama Judicial/2026-08-06/Auto/T_SANT_68001_33_33_007_2025_00290_02.pdf"


def test_reconcile_document_does_nothing_when_the_stored_key_already_matches(db_session, monkeypatch):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T-123-24",
        storage_bucket="iurisync-test", storage_key="carpeta/T-123-24.pdf",
    )

    called = []
    monkeypatch.setattr(storage_sync, "rename_object", lambda *a: called.append(a))

    result = storage_sync.reconcile_document(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert result is False
    assert called == []


def test_reconcile_document_logs_and_returns_false_when_rename_fails(db_session, monkeypatch, caplog):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T_SANT_68001_33_33_007_2025_00290_02",
        storage_bucket="iurisync-test", storage_key="Rama Judicial/2026-08-06/Auto/placeholder.pdf",
    )

    def _boom(bucket, old_key, new_key):
        raise RuntimeError("MinIO no disponible")

    monkeypatch.setattr(storage_sync, "rename_object", _boom)

    result = storage_sync.reconcile_document(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert result is False
    db_session.refresh(doc)
    assert doc.storage_key == "Rama Judicial/2026-08-06/Auto/placeholder.pdf"  # sin cambios
    assert "No se pudo renombrar el documento" in caplog.text


def test_reconcile_document_versions_renames_each_archived_version(db_session, monkeypatch):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T-123-24",
        storage_bucket="iurisync-test", storage_key="carpeta/v3.pdf",
    )
    repository.archive_and_replace_document(db_session, doc.id, storage_bucket="iurisync-test", storage_key="carpeta/v1-viejo.pdf")
    doc = repository.get_document(db_session, doc.id)
    repository.archive_and_replace_document(db_session, doc.id, storage_bucket="iurisync-test", storage_key="carpeta/v2-viejo.pdf")
    doc = repository.get_document(db_session, doc.id)

    renamed = []
    monkeypatch.setattr(storage_sync, "rename_object", lambda bucket, old_key, new_key: renamed.append((old_key, new_key)))

    count = storage_sync.reconcile_document_versions(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert count == 2
    versions = {v.storage_key for v in repository.list_document_versions(db_session, doc.id)}
    assert versions == {"carpeta/T-123-24_v1.pdf", "carpeta/T-123-24_v2.pdf"}


def test_reconcile_document_versions_returns_zero_when_document_has_no_history(db_session, monkeypatch):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T-123-24",
        storage_bucket="iurisync-test", storage_key="carpeta/T-123-24.pdf",
    )

    monkeypatch.setattr(storage_sync, "rename_object", lambda *a: (_ for _ in ()).throw(AssertionError("no debería llamarse")))

    count = storage_sync.reconcile_document_versions(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert count == 0


def test_reconcile_document_versions_logs_and_continues_when_rename_fails(db_session, monkeypatch, caplog):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T-123-24",
        storage_bucket="iurisync-test", storage_key="carpeta/v3.pdf",
    )
    repository.archive_and_replace_document(db_session, doc.id, storage_bucket="iurisync-test", storage_key="carpeta/v1-viejo.pdf")
    doc = repository.get_document(db_session, doc.id)
    repository.archive_and_replace_document(db_session, doc.id, storage_bucket="iurisync-test", storage_key="carpeta/v2-viejo.pdf")
    doc = repository.get_document(db_session, doc.id)

    def _boom(bucket, old_key, new_key):
        raise RuntimeError("MinIO no disponible")

    monkeypatch.setattr(storage_sync, "rename_object", _boom)

    count = storage_sync.reconcile_document_versions(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert count == 0
    # Verify versions were not renamed (keys should stay unchanged)
    versions = {v.storage_key for v in repository.list_document_versions(db_session, doc.id)}
    assert versions == {"carpeta/v3.pdf", "carpeta/v1-viejo.pdf"}  # sin cambios
    assert "No se pudo renombrar la versión" in caplog.text


def test_reconcile_title_group_gives_full_date_to_every_sibling_when_there_are_two(db_session, monkeypatch):
    from datetime import date

    source = _rama_judicial_source(db_session)
    shared_title = "T_SANT_68001_33_33_007_2025_00290_02"
    doc1 = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title=shared_title, f_providencia=date(2026, 8, 6),
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder1.pdf",
    )
    doc2 = repository.insert_document(
        db_session, doc_id="d2", source_id=source.id, title=shared_title, f_providencia=date(2026, 8, 20),
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder2.pdf",
    )

    monkeypatch.setattr(storage_sync, "rename_object", lambda *a: None)

    result = storage_sync.reconcile_title_group(db_session, "rama_judicial", shared_title)

    assert result == {"documentos_renombrados": 2, "versiones_renombradas": 0}
    db_session.refresh(doc1)
    db_session.refresh(doc2)
    assert doc1.storage_key == "carpeta/T_SANT_68001_33_33_007_2025_00290_02_20260806.pdf"
    assert doc2.storage_key == "carpeta/T_SANT_68001_33_33_007_2025_00290_02_20260820.pdf"


def test_reconcile_title_group_gives_year_only_when_there_is_a_single_document(db_session, monkeypatch):
    from datetime import date

    source = _rama_judicial_source(db_session)
    title = "T_CUND_25307_33_33_003_2024_00094_01"
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title=title, f_providencia=date(2026, 3, 15),
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder.pdf",
    )

    monkeypatch.setattr(storage_sync, "rename_object", lambda *a: None)

    result = storage_sync.reconcile_title_group(db_session, "rama_judicial", title)

    assert result == {"documentos_renombrados": 1, "versiones_renombradas": 0}
    db_session.refresh(doc)
    assert doc.storage_key == "carpeta/T_CUND_25307_33_33_003_2024_00094_01_2026.pdf"
