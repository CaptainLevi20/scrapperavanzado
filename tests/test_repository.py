from core.db import repository


def test_create_and_list_sources(db_session):
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})

    sources = repository.list_sources(db_session, family_key="constitucional")
    assert [s.name for s in sources] == ["Corte Constitucional"]


def test_run_and_run_source_lifecycle(db_session):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})

    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    assert run.status == "pending"

    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)
    repository.set_run_source_status(db_session, run_source.id, "completed", docs_new=3, docs_errors=1)

    [refreshed] = repository.list_run_sources(db_session, run.id)
    assert refreshed.status == "completed"
    assert refreshed.docs_new == 3
    assert refreshed.docs_errors == 1

    repository.request_run_cancel(db_session, run.id)
    assert repository.is_cancel_requested(db_session, run.id) is True


def test_insert_document_is_idempotent_on_doc_id(db_session):
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})

    payload = dict(
        doc_id="abc123",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-02-01/Sentencia/T-065-24.rtf",
    )
    first = repository.insert_document(db_session, **payload)
    second = repository.insert_document(db_session, **payload)

    assert first.id == second.id
    assert repository.document_exists(db_session, "abc123") is True


def test_api_key_create_and_lookup_by_hash(db_session):
    repository.create_api_key(db_session, name="tests", key_hash="hash123")
    found = repository.get_active_api_key_by_hash(db_session, "hash123")
    assert found is not None
    assert found.name == "tests"
    assert repository.get_active_api_key_by_hash(db_session, "missing") is None


def test_touch_api_key_last_used_sets_timestamp(db_session):
    api_key = repository.create_api_key(db_session, name="tests", key_hash="hash456")
    assert api_key.last_used_at is None

    repository.touch_api_key_last_used(db_session, api_key.id)

    refreshed = repository.get_active_api_key_by_hash(db_session, "hash456")
    assert refreshed.last_used_at is not None


def test_update_document_review_status_sets_status_and_timestamp(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-review-1",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-02-01/Sentencia/T-065-24.rtf",
    )

    assert document.review_status == "pending"
    assert document.reviewed_at is None

    updated = repository.update_document_review_status(db_session, document.id, "useful")

    assert updated is not None
    assert updated.review_status == "useful"
    assert updated.reviewed_at is not None


def test_update_document_review_status_returns_none_when_missing(db_session):
    from core.db import repository

    assert repository.update_document_review_status(db_session, 999999, "useful") is None


def test_list_documents_filters_by_review_status(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    useful_doc = repository.insert_document(
        db_session,
        doc_id="doc-useful",
        source_id=source.id,
        title="Útil",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )
    repository.insert_document(
        db_session,
        doc_id="doc-pending",
        source_id=source.id,
        title="Pendiente",
        storage_bucket="iurisync-test",
        storage_key="b.pdf",
    )
    repository.update_document_review_status(db_session, useful_doc.id, "useful")

    items, total = repository.list_documents(db_session, review_status="useful")

    assert total == 1
    assert items[0].doc_id == "doc-useful"
