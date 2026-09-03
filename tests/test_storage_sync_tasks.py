from datetime import date

from sqlalchemy.orm import sessionmaker

from core.db import repository
import core.storage_sync as storage_sync
from worker.celery_app import celery_app
from worker.storage_sync_tasks import reconcile_all_task, reconcile_document_task, reconcile_title_group_task


def _rama_judicial_source(db_session):
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    return repository.create_source(db_session, family_key="rama_judicial", name="Tribunal", family_params={})


def test_reconcile_title_group_task_renames_every_sibling(db_session, test_engine, monkeypatch):
    celery_app.conf.task_always_eager = True
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.storage_sync_tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr(storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(storage_sync, "delete_object", lambda *a: None)

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

    reconcile_title_group_task("rama_judicial", shared_title)

    assertion_session = task_session_factory()
    try:
        d1 = repository.get_document(assertion_session, doc1.id)
        d2 = repository.get_document(assertion_session, doc2.id)
        assert d1.storage_key == "carpeta/T_SANT_68001_33_33_007_2025_00290_02_20260806.pdf"
        assert d2.storage_key == "carpeta/T_SANT_68001_33_33_007_2025_00290_02_20260820.pdf"
    finally:
        assertion_session.close()


def test_reconcile_document_task_renames_the_document_and_its_versions(db_session, test_engine, monkeypatch):
    celery_app.conf.task_always_eager = True
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.storage_sync_tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr(storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(storage_sync, "delete_object", lambda *a: None)

    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T-123-24",
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder.pdf",
    )
    repository.archive_and_replace_document(db_session, doc.id, storage_bucket="iurisync-test", storage_key="carpeta/placeholder-v1.pdf")

    reconcile_document_task(doc.id)

    assertion_session = task_session_factory()
    try:
        refreshed = repository.get_document(assertion_session, doc.id)
        assert refreshed.storage_key == "carpeta/T-123-24-v2.pdf"
        [version] = repository.list_document_versions(assertion_session, doc.id)
        assert version.storage_key == "carpeta/T-123-24-v1.pdf"
    finally:
        assertion_session.close()


def test_reconcile_document_task_does_not_raise_for_a_nonexistent_document(db_session, test_engine, monkeypatch):
    celery_app.conf.task_always_eager = True
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.storage_sync_tasks.SessionLocal", task_session_factory)

    reconcile_document_task(999999)  # no debe lanzar


def test_reconcile_all_task_sweeps_everything(db_session, test_engine, monkeypatch):
    celery_app.conf.task_always_eager = True
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.storage_sync_tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr(storage_sync, "copy_object", lambda *a: None)
    monkeypatch.setattr(storage_sync, "delete_object", lambda *a: None)

    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T-123-24",
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder.pdf",
    )

    reconcile_all_task()

    assertion_session = task_session_factory()
    try:
        assert repository.get_document(assertion_session, doc.id).storage_key == "carpeta/T-123-24.pdf"
    finally:
        assertion_session.close()
