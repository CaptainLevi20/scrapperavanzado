import logging
from datetime import date

import pytest
from sqlalchemy import text

from core.db import repository
import core.storage_sync as storage_sync


def _rama_judicial_source(db_session):
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    return repository.create_source(db_session, family_key="rama_judicial", name="Tribunal", family_params={})


@pytest.fixture(autouse=True)
def _minio_por_defecto_todo_existe(monkeypatch):
    """Por defecto, en estas pruebas el objeto al que apunta storage_key SÍ
    existe en MinIO, para que reconcile_* siga el camino normal de
    copiar + renombrar. Las pruebas del auto-reparado de punteros rotos
    sobreescriben esto con su propio monkeypatch."""
    monkeypatch.setattr(storage_sync, "object_exists", lambda bucket, key: True)
    monkeypatch.setattr(storage_sync, "list_objects", lambda bucket, prefix: [])


def test_reconcile_document_renames_when_the_stored_key_does_not_match(db_session, monkeypatch):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T_SANT_68001_33_33_007_2025_00290_02",
        storage_bucket="iurisync-test", storage_key="Rama Judicial/2026-08-06/Auto/placeholder.pdf",
    )

    copied = []
    monkeypatch.setattr(storage_sync, "copy_object", lambda bucket, old_key, new_key: copied.append((bucket, old_key, new_key)))
    monkeypatch.setattr(storage_sync, "delete_object", lambda *a: None)

    result = storage_sync.reconcile_document(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert result is True
    assert copied == [(
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
    monkeypatch.setattr(storage_sync, "copy_object", lambda *a: called.append(a))
    monkeypatch.setattr(storage_sync, "delete_object", lambda *a: called.append(a))

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

    monkeypatch.setattr(storage_sync, "copy_object", _boom)

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
    monkeypatch.setattr(storage_sync, "copy_object", lambda bucket, old_key, new_key: renamed.append((old_key, new_key)))
    monkeypatch.setattr(storage_sync, "delete_object", lambda *a: None)

    count = storage_sync.reconcile_document_versions(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert count == 2
    versions = {v.storage_key for v in repository.list_document_versions(db_session, doc.id)}
    assert versions == {"carpeta/T-123-24-v1.pdf", "carpeta/T-123-24-v2.pdf"}


def test_reconcile_document_versions_returns_zero_when_document_has_no_history(db_session, monkeypatch):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T-123-24",
        storage_bucket="iurisync-test", storage_key="carpeta/T-123-24.pdf",
    )

    monkeypatch.setattr(storage_sync, "copy_object", lambda *a: (_ for _ in ()).throw(AssertionError("no debería llamarse")))
    monkeypatch.setattr(storage_sync, "delete_object", lambda *a: (_ for _ in ()).throw(AssertionError("no debería llamarse")))

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

    monkeypatch.setattr(storage_sync, "copy_object", _boom)

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

    monkeypatch.setattr(storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(storage_sync, "delete_object", lambda *a: None)

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

    monkeypatch.setattr(storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(storage_sync, "delete_object", lambda *a: None)

    result = storage_sync.reconcile_title_group(db_session, "rama_judicial", title)

    assert result == {"documentos_renombrados": 1, "versiones_renombradas": 0}
    db_session.refresh(doc)
    assert doc.storage_key == "carpeta/T_CUND_25307_33_33_003_2024_00094_01_2026.pdf"


def test_reconcile_all_covers_case_families_and_plain_families_together(db_session, monkeypatch):
    from datetime import date

    rama_source = _rama_judicial_source(db_session)
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    const_source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})

    shared_title = "T_SANT_68001_33_33_007_2025_00290_02"
    caso1 = repository.insert_document(
        db_session, doc_id="d1", source_id=rama_source.id, title=shared_title, f_providencia=date(2026, 8, 6),
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder1.pdf",
    )
    caso2 = repository.insert_document(
        db_session, doc_id="d2", source_id=rama_source.id, title=shared_title, f_providencia=date(2026, 8, 20),
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder2.pdf",
    )
    suelto = repository.insert_document(
        db_session, doc_id="d3", source_id=const_source.id, title="T-065/24",
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder-suelto.pdf",
    )

    monkeypatch.setattr(storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(storage_sync, "delete_object", lambda *a: None)

    result = storage_sync.reconcile_all(db_session)

    assert result == {"documentos_renombrados": 3, "versiones_renombradas": 0}
    db_session.refresh(caso1)
    db_session.refresh(caso2)
    db_session.refresh(suelto)
    assert caso1.storage_key == "carpeta/T_SANT_68001_33_33_007_2025_00290_02_20260806.pdf"
    assert caso2.storage_key == "carpeta/T_SANT_68001_33_33_007_2025_00290_02_20260820.pdf"
    assert suelto.storage_key == "carpeta/T-065-24.pdf"


def test_reconcile_all_is_idempotent(db_session, monkeypatch):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T-123-24",
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder.pdf",
    )

    monkeypatch.setattr(storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(storage_sync, "delete_object", lambda *a: None)

    storage_sync.reconcile_all(db_session)
    second = storage_sync.reconcile_all(db_session)

    assert second == {"documentos_renombrados": 0, "versiones_renombradas": 0}


# --- Finding 1: computed-key collisions between siblings must not be renamed ---


def test_reconcile_title_group_skips_sibling_documents_that_collide_on_the_same_computed_key(db_session, monkeypatch, caplog):
    from datetime import date

    source = _rama_judicial_source(db_session)
    shared_title = "T_SANT_68001_33_33_007_2025_00290_02"
    same_date = date(2026, 8, 6)
    # Same folder, same title, same f_providencia => both siblings compute the
    # exact same target key ("carpeta/T_..._20260806.pdf").
    doc1 = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title=shared_title, f_providencia=same_date,
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder1.pdf",
    )
    doc2 = repository.insert_document(
        db_session, doc_id="d2", source_id=source.id, title=shared_title, f_providencia=same_date,
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder2.pdf",
    )

    monkeypatch.setattr(storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(storage_sync, "delete_object", lambda *a: None)

    result = storage_sync.reconcile_title_group(db_session, "rama_judicial", shared_title)

    assert result == {"documentos_renombrados": 0, "versiones_renombradas": 0}
    db_session.refresh(doc1)
    db_session.refresh(doc2)
    # Neither side of the colliding pair gets touched.
    assert doc1.storage_key == "carpeta/placeholder1.pdf"
    assert doc2.storage_key == "carpeta/placeholder2.pdf"
    assert "colisión" in caplog.text.lower()
    assert "documentos" in caplog.text.lower()
    assert shared_title in caplog.text


def test_reconcile_title_group_skips_archived_versions_of_different_siblings_that_collide(db_session, monkeypatch, caplog):
    from datetime import date

    source = _rama_judicial_source(db_session)
    shared_title = "T_SANT_68001_33_33_007_2025_00290_02"
    same_date = date(2026, 8, 6)
    # Same folder + same title + same f_providencia for both siblings. Each is
    # republished exactly once: archive_and_replace_document archives the
    # document's key *at the time of the call* as a version_no=1 version, then
    # moves the current document on to the new key passed in — so both
    # archived versions keep the same folder ("carpeta/"), same version_no=1
    # and same total_versiones=2 => both compute the same target key.
    doc1 = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title=shared_title, f_providencia=same_date,
        storage_bucket="iurisync-test", storage_key="carpeta/actual1.pdf",
    )
    doc2 = repository.insert_document(
        db_session, doc_id="d2", source_id=source.id, title=shared_title, f_providencia=same_date,
        storage_bucket="iurisync-test", storage_key="carpeta/actual2.pdf",
    )
    repository.archive_and_replace_document(
        db_session, doc1.id, storage_bucket="iurisync-test", storage_key="carpeta/nueva1.pdf",
    )
    repository.archive_and_replace_document(
        db_session, doc2.id, storage_bucket="iurisync-test", storage_key="carpeta/nueva2.pdf",
    )

    monkeypatch.setattr(storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(storage_sync, "delete_object", lambda *a: None)

    storage_sync.reconcile_title_group(db_session, "rama_judicial", shared_title)

    version1 = repository.list_document_versions(db_session, doc1.id)[0]
    version2 = repository.list_document_versions(db_session, doc2.id)[0]
    assert version1.storage_key == "carpeta/actual1.pdf"
    assert version2.storage_key == "carpeta/actual2.pdf"
    assert "colisión" in caplog.text.lower()
    assert "versiones" in caplog.text.lower()


def test_reconcile_title_group_still_reconciles_non_colliding_group_normally(db_session, monkeypatch):
    """Regression: adding the collision guard must not break the ordinary
    two-sibling happy path (different dates => different computed keys)."""
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

    monkeypatch.setattr(storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(storage_sync, "delete_object", lambda *a: None)

    result = storage_sync.reconcile_title_group(db_session, "rama_judicial", shared_title)

    assert result == {"documentos_renombrados": 2, "versiones_renombradas": 0}
    db_session.refresh(doc1)
    db_session.refresh(doc2)
    assert doc1.storage_key == "carpeta/T_SANT_68001_33_33_007_2025_00290_02_20260806.pdf"
    assert doc2.storage_key == "carpeta/T_SANT_68001_33_33_007_2025_00290_02_20260820.pdf"


# --- Regresión: incidente doc 39905 (2026-08-21) — reconcile_document borraba
# la clave vieja en MinIO ANTES de confirmar que la base ya apuntaba a la
# nueva. Si la escritura en la base fallaba justo después del renombrado en
# MinIO, storage_key se quedaba apuntando a una clave ya borrada — el
# documento quedaba con un registro válido en la base pero sin archivo real
# en el almacén (404 al intentar leerlo). ---


def test_reconcile_document_does_not_delete_old_key_when_db_write_fails_after_copy(db_session, monkeypatch, caplog):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T_SANT_68001_33_33_007_2025_00290_02",
        storage_bucket="iurisync-test", storage_key="Rama Judicial/2026-08-06/Auto/placeholder.pdf",
    )

    copied = []
    deleted = []
    monkeypatch.setattr(storage_sync, "copy_object", lambda bucket, old_key, new_key: copied.append((bucket, old_key, new_key)))
    monkeypatch.setattr(storage_sync, "delete_object", lambda bucket, key: deleted.append((bucket, key)))

    def _flaky_update(db, document_id, storage_key):
        db.execute(text("SELECT 1/0"))

    monkeypatch.setattr(storage_sync.repository, "update_document_storage_key", _flaky_update)

    result = storage_sync.reconcile_document(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert result is False
    # El archivo ya se copió a la clave nueva...
    assert copied == [(
        "iurisync-test",
        "Rama Judicial/2026-08-06/Auto/placeholder.pdf",
        "Rama Judicial/2026-08-06/Auto/T_SANT_68001_33_33_007_2025_00290_02.pdf",
    )]
    # ...pero la clave VIEJA nunca debe borrarse, porque la base nunca llegó a
    # apuntar a la nueva — borrarla dejaría storage_key apuntando a un objeto
    # que ya no existe (el incidente real que esto evita). Sí puede borrarse
    # la copia nueva recién creada, como limpieza best-effort — eso no deja
    # ninguna referencia rota, solo evita un duplicado huérfano.
    assert ("iurisync-test", "Rama Judicial/2026-08-06/Auto/placeholder.pdf") not in deleted
    db_session.refresh(doc)
    assert doc.storage_key == "Rama Judicial/2026-08-06/Auto/placeholder.pdf"  # sin cambios


def test_reconcile_document_only_deletes_old_key_after_db_write_succeeds(db_session, monkeypatch):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T_SANT_68001_33_33_007_2025_00290_02",
        storage_bucket="iurisync-test", storage_key="Rama Judicial/2026-08-06/Auto/placeholder.pdf",
    )

    calls = []
    monkeypatch.setattr(storage_sync, "copy_object", lambda bucket, old_key, new_key: calls.append(("copy", old_key, new_key)))
    monkeypatch.setattr(storage_sync, "delete_object", lambda bucket, key: calls.append(("delete", key)))

    result = storage_sync.reconcile_document(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert result is True
    # Orden estricto: primero se copia, y solo se borra la clave vieja después
    # (la base ya se actualizó en ese punto, ver siguiente assert).
    assert [c[0] for c in calls] == ["copy", "delete"]
    assert calls[1][1] == "Rama Judicial/2026-08-06/Auto/placeholder.pdf"
    db_session.refresh(doc)
    assert doc.storage_key == "Rama Judicial/2026-08-06/Auto/T_SANT_68001_33_33_007_2025_00290_02.pdf"


# --- Finding 2: a DB-write failure must not poison the shared session ---


def test_reconcile_document_rolls_back_session_so_the_next_document_still_reconciles(db_session, monkeypatch):
    source = _rama_judicial_source(db_session)
    doc1 = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T-111-24",
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder1.pdf",
    )
    doc2 = repository.insert_document(
        db_session, doc_id="d2", source_id=source.id, title="T-222-24",
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder2.pdf",
    )

    monkeypatch.setattr(storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(storage_sync, "delete_object", lambda *a: None)

    original_update = repository.update_document_storage_key

    def _flaky_update(db, document_id, storage_key):
        if document_id == doc1.id:
            # Force a genuine DB-level error (not just a Python-level raise) so
            # the session's transaction is actually left in a failed state,
            # exactly like a real DB-write failure would.
            db.execute(text("SELECT 1/0"))
        return original_update(db, document_id, storage_key)

    monkeypatch.setattr(storage_sync.repository, "update_document_storage_key", _flaky_update)

    result1 = storage_sync.reconcile_document(db_session, doc1, "rama_judicial", tiene_actuaciones=False)
    # Without db.rollback() in the except block, this next call would raise
    # outside any try/except here, because the session is still in a failed
    # transaction state from doc1's failure.
    result2 = storage_sync.reconcile_document(db_session, doc2, "rama_judicial", tiene_actuaciones=False)

    assert result1 is False
    assert result2 is True
    db_session.refresh(doc2)
    assert doc2.storage_key == "carpeta/T-222-24.pdf"


def test_reconcile_document_versions_rolls_back_session_so_the_next_version_still_reconciles(db_session, monkeypatch):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T-123-24",
        storage_bucket="iurisync-test", storage_key="carpeta/v3.pdf",
    )
    repository.archive_and_replace_document(db_session, doc.id, storage_bucket="iurisync-test", storage_key="carpeta/v1-viejo.pdf")
    doc = repository.get_document(db_session, doc.id)
    repository.archive_and_replace_document(db_session, doc.id, storage_bucket="iurisync-test", storage_key="carpeta/v2-viejo.pdf")
    doc = repository.get_document(db_session, doc.id)

    # archive_and_replace_document archives the document's key *as of the
    # call* and moves the current document on to the new key passed in — so
    # after two calls the archived versions are "carpeta/v3.pdf" (the
    # original) and "carpeta/v1-viejo.pdf" (archived on the second call); the
    # current document itself ends up at "carpeta/v2-viejo.pdf".
    all_versions = repository.list_document_versions(db_session, doc.id)
    failing_version = next(v for v in all_versions if v.storage_key == "carpeta/v3.pdf")
    other_version = next(v for v in all_versions if v.storage_key == "carpeta/v1-viejo.pdf")

    monkeypatch.setattr(storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(storage_sync, "delete_object", lambda *a: None)

    original_update = repository.update_document_version_storage_key

    def _flaky_update(db, version_id, storage_key):
        if version_id == failing_version.id:
            db.execute(text("SELECT 1/0"))
        return original_update(db, version_id, storage_key)

    monkeypatch.setattr(storage_sync.repository, "update_document_version_storage_key", _flaky_update)

    count = storage_sync.reconcile_document_versions(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    # The failing version is skipped, but the other one still gets reconciled
    # — proving the session recovered after the first failure. Order of
    # iteration (by superseded_at desc) isn't relied on here — each version is
    # checked by identity, not by which ran first.
    assert count == 1
    db_session.refresh(failing_version)
    db_session.refresh(other_version)
    assert failing_version.storage_key == "carpeta/v3.pdf"  # unchanged, failed
    assert other_version.storage_key == f"carpeta/T-123-24-v{other_version.version_no}.pdf"  # reconciled


# --- Auto-reparado: storage_key apuntando a un objeto que ya no existe en MinIO
# (incidente descargas masivas, 2026-09-09) — un reconcile anterior renombró el
# objeto en MinIO pero la escritura en la base no llegó a confirmarse, dejando
# storage_key apuntando a una clave ya borrada. reconcile_document NO podía
# recuperarse en corridas posteriores: hacía copy_object DESDE esa clave rota,
# el copiado fallaba con 404, dejaba un warning y se rendía. La descarga masiva
# lee storage_key tal cual => 404 para todos => falla total. ---


def test_reconcile_document_repairs_pointer_when_old_key_missing_but_canonical_object_exists(db_session, monkeypatch, caplog):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T_SANT_68001_33_33_007_2025_00290_02",
        storage_bucket="iurisync-test", storage_key="Rama Judicial/2026-08-06/Auto/viejo.pdf",
    )
    canonica = "Rama Judicial/2026-08-06/Auto/T_SANT_68001_33_33_007_2025_00290_02.pdf"

    # La clave vieja NO existe; el objeto real ya está bajo su nombre canónico.
    monkeypatch.setattr(storage_sync, "object_exists", lambda bucket, key: key == canonica)
    copiados, borrados = [], []
    monkeypatch.setattr(storage_sync, "copy_object", lambda *a: copiados.append(a))
    monkeypatch.setattr(storage_sync, "delete_object", lambda *a: borrados.append(a))

    result = storage_sync.reconcile_document(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert result is True
    assert copiados == []   # no se copia nada: el objeto ya está donde debe
    assert borrados == []   # no se borra nada: la clave vieja ni existe
    db_session.refresh(doc)
    assert doc.storage_key == canonica
    assert "objeto inexistente" in caplog.text


def test_reconcile_document_repairs_pointer_by_unique_folder_match(db_session, monkeypatch):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T_SANT_68001_33_33_007_2025_00290_02",
        f_providencia=date(2026, 8, 6),
        storage_bucket="iurisync-test", storage_key="carpeta/viejo.pdf",
    )
    # nombre canónico calculado ahora: "carpeta/T_SANT_..._2026.pdf" (año, 1
    # sola actuación). El objeto real quedó con la fecha completa de un
    # reconcile previo que sí lo renombró en MinIO.
    real = "carpeta/T_SANT_68001_33_33_007_2025_00290_02_20260806.pdf"

    monkeypatch.setattr(storage_sync, "object_exists", lambda bucket, key: key == real)
    monkeypatch.setattr(
        storage_sync, "list_objects",
        lambda bucket, prefix: [real, "carpeta/otro-documento_2025.pdf"],
    )
    monkeypatch.setattr(storage_sync, "copy_object", lambda *a: (_ for _ in ()).throw(AssertionError("no debe copiar")))
    monkeypatch.setattr(storage_sync, "delete_object", lambda *a: (_ for _ in ()).throw(AssertionError("no debe borrar")))

    result = storage_sync.reconcile_document(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert result is True
    db_session.refresh(doc)
    assert doc.storage_key == real


def test_reconcile_document_logs_error_and_gives_up_when_real_object_cannot_be_located(db_session, monkeypatch, caplog):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T_SANT_68001_33_33_007_2025_00290_02",
        f_providencia=date(2026, 8, 6),
        storage_bucket="iurisync-test", storage_key="carpeta/viejo.pdf",
    )
    monkeypatch.setattr(storage_sync, "object_exists", lambda bucket, key: False)
    monkeypatch.setattr(storage_sync, "list_objects", lambda bucket, prefix: [])  # carpeta vacía
    monkeypatch.setattr(storage_sync, "copy_object", lambda *a: (_ for _ in ()).throw(AssertionError("no debe copiar")))

    with caplog.at_level(logging.ERROR):
        result = storage_sync.reconcile_document(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert result is False
    db_session.refresh(doc)
    assert doc.storage_key == "carpeta/viejo.pdf"  # sin cambios
    assert "corrección manual" in caplog.text.lower()


def test_reconcile_document_gives_up_when_folder_match_is_ambiguous(db_session, monkeypatch, caplog):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T_SANT_68001_33_33_007_2025_00290_02",
        f_providencia=date(2026, 8, 6),
        storage_bucket="iurisync-test", storage_key="carpeta/viejo.pdf",
    )
    # Dos objetos en la carpeta reducen a la misma base (mismo radicado, dos
    # fechas): no hay una coincidencia inequívoca => no se toca nada.
    gemelo_a = "carpeta/T_SANT_68001_33_33_007_2025_00290_02_20260806.pdf"
    gemelo_b = "carpeta/T_SANT_68001_33_33_007_2025_00290_02_20260820.pdf"
    monkeypatch.setattr(storage_sync, "object_exists", lambda bucket, key: False)
    monkeypatch.setattr(storage_sync, "list_objects", lambda bucket, prefix: [gemelo_a, gemelo_b])
    monkeypatch.setattr(storage_sync, "copy_object", lambda *a: (_ for _ in ()).throw(AssertionError("no debe copiar")))

    with caplog.at_level(logging.ERROR):
        result = storage_sync.reconcile_document(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert result is False
    db_session.refresh(doc)
    assert doc.storage_key == "carpeta/viejo.pdf"


def test_reconcile_document_versions_repairs_pointer_when_old_key_missing_but_canonical_object_exists(db_session, monkeypatch, caplog):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T-123-24",
        storage_bucket="iurisync-test", storage_key="carpeta/actual.pdf",
    )
    repository.archive_and_replace_document(db_session, doc.id, storage_bucket="iurisync-test", storage_key="carpeta/nueva.pdf")
    doc = repository.get_document(db_session, doc.id)
    version = repository.list_document_versions(db_session, doc.id)[0]
    canonica_version = storage_sync._expected_version_key(doc, version, "rama_judicial", False)
    assert canonica_version != version.storage_key  # el objeto real quedó bajo el nombre canónico

    monkeypatch.setattr(storage_sync, "object_exists", lambda bucket, key: key == canonica_version)
    monkeypatch.setattr(storage_sync, "copy_object", lambda *a: (_ for _ in ()).throw(AssertionError("no debe copiar")))
    monkeypatch.setattr(storage_sync, "delete_object", lambda *a: (_ for _ in ()).throw(AssertionError("no debe borrar")))

    count = storage_sync.reconcile_document_versions(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert count == 1
    db_session.refresh(version)
    assert version.storage_key == canonica_version
    assert "objeto inexistente" in caplog.text


def test_reconcile_document_falls_back_to_normal_rename_when_minio_check_errors(db_session, monkeypatch, caplog):
    """Si la consulta de existencia a MinIO falla (MinIO caído, permisos), NO
    se entra al auto-reparado: se sigue el camino normal de copiar + renombrar,
    que ya captura sus propias fallas. Nunca se bloquea al llamador."""
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T-123-24",
        storage_bucket="iurisync-test", storage_key="carpeta/viejo.pdf",
    )

    def _minio_caido(bucket, key):
        raise RuntimeError("MinIO no disponible")

    monkeypatch.setattr(storage_sync, "object_exists", _minio_caido)
    copiados = []
    monkeypatch.setattr(storage_sync, "copy_object", lambda *a: copiados.append(a))
    monkeypatch.setattr(storage_sync, "delete_object", lambda *a: None)

    result = storage_sync.reconcile_document(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert result is True
    assert copiados == [("iurisync-test", "carpeta/viejo.pdf", "carpeta/T-123-24.pdf")]
    db_session.refresh(doc)
    assert doc.storage_key == "carpeta/T-123-24.pdf"
