from core.db import repository
import core.purge_inactive_source_documents as purge_module
from core.purge_inactive_source_documents import purge


def _source(db_session, name="Fuente de prueba", family_key="test-family", active=True):
    if repository.get_source_family(db_session, family_key) is None:
        repository.create_source_family(db_session, key=family_key, display_name=family_key)
    return repository.create_source(db_session, family_key=family_key, name=name, family_params={}, active=active)


def _document(db_session, source_id, doc_id="doc-1", **overrides):
    fields = dict(
        doc_id=doc_id,
        source_id=source_id,
        title="Documento de prueba",
        storage_bucket="iurisync-test",
        storage_key=f"fuente/{doc_id}.pdf",
    )
    fields.update(overrides)
    return repository.insert_document(db_session, **fields)


# --- repository.purge_documents_for_source -----------------------------------


def test_purge_documents_for_source_deletes_document_and_returns_storage_key(db_session):
    source = _source(db_session, active=False)
    doc = _document(db_session, source.id)
    doc_id, bucket, key = doc.id, doc.storage_bucket, doc.storage_key

    result = repository.purge_documents_for_source(db_session, source.id)

    assert result["documents_deleted"] == 1
    assert (bucket, key) in result["storage_objects"]
    assert repository.get_document(db_session, doc_id) is None


def test_purge_documents_for_source_includes_preview_storage_key_when_present(db_session):
    source = _source(db_session, active=False)
    doc = _document(db_session, source.id, preview_storage_key="fuente/doc-1.preview.pdf")
    bucket = doc.storage_bucket

    result = repository.purge_documents_for_source(db_session, source.id)

    assert (bucket, "fuente/doc-1.preview.pdf") in result["storage_objects"]


def test_purge_documents_for_source_deletes_document_versions_too(db_session):
    source = _source(db_session, active=False)
    doc = _document(db_session, source.id)
    doc_id, doc_doc_id, doc_title = doc.id, doc.doc_id, doc.title
    repository.archive_and_replace_document(
        db_session,
        doc_id,
        doc_id=doc_doc_id,
        source_id=source.id,
        title=doc_title,
        storage_bucket="iurisync-test",
        storage_key="fuente/doc-1-v2.pdf",
    )

    result = repository.purge_documents_for_source(db_session, source.id)

    assert result["documents_deleted"] == 1
    assert ("iurisync-test", "fuente/doc-1.pdf") in result["storage_objects"]  # la versión archivada
    assert ("iurisync-test", "fuente/doc-1-v2.pdf") in result["storage_objects"]  # la vigente
    assert repository.get_document(db_session, doc_id) is None


def test_purge_documents_for_source_deletes_run_sources_and_run_errors(db_session):
    source = _source(db_session, active=False)
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_id = run.id
    run_source = repository.create_run_source(db_session, run_id=run_id, source_id=source.id)
    run_source_id = run_source.id
    repository.add_run_error(db_session, run_source_id=run_source_id, message="algo falló")

    result = repository.purge_documents_for_source(db_session, source.id)

    assert result["run_sources_deleted"] == 1
    assert repository.get_run_source(db_session, run_source_id) is None
    # El Run en sí no se borra — puede tener otras fuentes.
    assert repository.get_run(db_session, run_id) is not None


def test_purge_documents_for_source_leaves_other_sources_untouched(db_session):
    fuente_a = _source(db_session, name="Fuente A", active=False)
    fuente_b = _source(db_session, name="Fuente B", active=True)
    doc_a_id = _document(db_session, fuente_a.id, doc_id="doc-a").id
    doc_b_id = _document(db_session, fuente_b.id, doc_id="doc-b").id

    repository.purge_documents_for_source(db_session, fuente_a.id)

    assert repository.get_document(db_session, doc_a_id) is None
    assert repository.get_document(db_session, doc_b_id) is not None


def test_purge_documents_for_source_is_a_noop_when_source_has_no_documents(db_session):
    source = _source(db_session, active=False)
    result = repository.purge_documents_for_source(db_session, source.id)
    assert result == {"documents_deleted": 0, "run_sources_deleted": 0, "storage_objects": []}


# --- purge() (el script) ------------------------------------------------------


def test_purge_dry_run_does_not_delete_anything(db_session, monkeypatch):
    source = _source(db_session, active=False)
    doc_id = _document(db_session, source.id).id

    called = []
    monkeypatch.setattr(purge_module, "delete_object", lambda *a: called.append(a))

    resultado = purge(db_session, confirm=False)

    assert resultado["modo"] == "simulación (nada se borró)"
    assert resultado["documentos"] == 1
    assert called == []
    assert repository.get_document(db_session, doc_id) is not None  # nada se borró de verdad


def test_purge_confirm_deletes_documents_and_storage_objects(db_session, monkeypatch):
    source = _source(db_session, active=False)
    doc_id = _document(db_session, source.id).id

    called = []
    monkeypatch.setattr(purge_module, "delete_object", lambda *a: called.append(a))

    resultado = purge(db_session, confirm=True)

    assert resultado["modo"] == "borrado real"
    assert resultado["documentos"] == 1
    assert called == [("iurisync-test", "fuente/doc-1.pdf")]
    assert repository.get_document(db_session, doc_id) is None


def test_purge_only_touches_inactive_sources(db_session, monkeypatch):
    fuente_activa = _source(db_session, name="Activa", active=True)
    fuente_inactiva = _source(db_session, name="Inactiva", active=False)
    doc_activa_id = _document(db_session, fuente_activa.id, doc_id="doc-activa").id
    doc_inactiva_id = _document(db_session, fuente_inactiva.id, doc_id="doc-inactiva").id

    monkeypatch.setattr(purge_module, "delete_object", lambda *a: None)

    resultado = purge(db_session, confirm=True)

    assert resultado["fuentes_inactivas"] == 1
    assert repository.get_document(db_session, doc_activa_id) is not None
    assert repository.get_document(db_session, doc_inactiva_id) is None


def test_purge_continues_after_storage_delete_failure(db_session, monkeypatch):
    source = _source(db_session, active=False)
    doc_id = _document(db_session, source.id).id

    def fallar(*_a):
        raise RuntimeError("MinIO no disponible")

    monkeypatch.setattr(purge_module, "delete_object", fallar)

    resultado = purge(db_session, confirm=True)

    # El objeto de almacenamiento no se pudo borrar, pero la fila sí — no debe
    # reventar el resto de la corrida.
    assert resultado["documentos"] == 1
    assert repository.get_document(db_session, doc_id) is None
