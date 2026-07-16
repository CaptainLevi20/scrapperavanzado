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


def test_list_distinct_document_tipos_returns_sorted_unique_non_null_values(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="A", tipo="Sentencia",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="B", tipo="Auto",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-3", source_id=source.id, title="C", tipo="Auto",
        storage_bucket="iurisync-test", storage_key="c.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-4", source_id=source.id, title="D", tipo=None,
        storage_bucket="iurisync-test", storage_key="d.pdf",
    )

    tipos = repository.list_distinct_document_tipos(db_session)

    assert tipos == ["Auto", "Sentencia"]


def test_bulk_update_document_review_status_updates_matching_rows(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    doc1 = repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="Uno",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    doc2 = repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="Dos",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    doc3 = repository.insert_document(
        db_session, doc_id="doc-3", source_id=source.id, title="Tres",
        storage_bucket="iurisync-test", storage_key="c.pdf",
    )

    updated_count = repository.bulk_update_document_review_status(db_session, [doc1.id, doc2.id], "useful")

    assert updated_count == 2
    db_session.refresh(doc1)
    db_session.refresh(doc2)
    db_session.refresh(doc3)
    assert doc1.review_status == "useful"
    assert doc1.reviewed_at is not None
    assert doc2.review_status == "useful"
    assert doc3.review_status == "pending"


def test_bulk_update_document_review_status_ignores_nonexistent_ids(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    doc1 = repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="Uno",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )

    updated_count = repository.bulk_update_document_review_status(db_session, [doc1.id, 999999], "not_useful")

    assert updated_count == 1


def test_create_user_and_lookup_by_username(db_session):
    repository.create_user(db_session, username="ana", password_hash="hashed")

    found = repository.get_user_by_username(db_session, "ana")
    assert found is not None
    assert found.password_hash == "hashed"
    assert found.active is True
    assert repository.get_user_by_username(db_session, "missing") is None


def test_create_and_validate_session(db_session):
    user = repository.create_user(db_session, username="ana", password_hash="hashed")

    session = repository.create_session(db_session, user_id=user.id, token_hash="tokhash")

    found = repository.get_valid_session_by_token_hash(db_session, "tokhash")
    assert found is not None
    assert found.id == session.id
    assert repository.get_valid_session_by_token_hash(db_session, "missing") is None


def test_get_valid_session_by_token_hash_excludes_expired_sessions(db_session):
    from datetime import datetime, timedelta, timezone

    from core.db.models import UserSession

    user = repository.create_user(db_session, username="ana", password_hash="hashed")
    expired = UserSession(
        user_id=user.id,
        token_hash="expired-hash",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(expired)
    db_session.commit()

    assert repository.get_valid_session_by_token_hash(db_session, "expired-hash") is None


def test_touch_session_extends_expiration(db_session):
    user = repository.create_user(db_session, username="ana", password_hash="hashed")
    session = repository.create_session(db_session, user_id=user.id, token_hash="tokhash")
    original_expiry = session.expires_at

    repository.touch_session(db_session, session.id)

    refreshed = repository.get_valid_session_by_token_hash(db_session, "tokhash")
    assert refreshed.last_used_at is not None
    assert refreshed.expires_at > original_expiry


def test_delete_session_removes_it(db_session):
    user = repository.create_user(db_session, username="ana", password_hash="hashed")
    repository.create_session(db_session, user_id=user.id, token_hash="tokhash")

    repository.delete_session(db_session, "tokhash")

    assert repository.get_valid_session_by_token_hash(db_session, "tokhash") is None


def test_update_user_password_changes_the_hash(db_session):
    user = repository.create_user(db_session, username="ana", password_hash="old-hash")

    repository.update_user_password(db_session, user.id, "new-hash")

    refreshed = repository.get_user_by_username(db_session, "ana")
    assert refreshed.password_hash == "new-hash"


def test_touch_user_last_login_sets_timestamp(db_session):
    user = repository.create_user(db_session, username="ana", password_hash="hashed")
    assert user.last_login_at is None

    repository.touch_user_last_login(db_session, user.id)

    refreshed = repository.get_user_by_username(db_session, "ana")
    assert refreshed.last_login_at is not None


def test_set_document_preview_key_updates_the_column(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-1",
        source_id=source.id,
        title="T-200/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Tutela/T-200-26.rtf",
        content_type="application/rtf",
    )
    assert document.preview_storage_key is None

    updated = repository.set_document_preview_key(
        db_session, document.id, "Corte Constitucional/2026-06-30/Tutela/T-200-26.preview.pdf"
    )

    assert updated.preview_storage_key == "Corte Constitucional/2026-06-30/Tutela/T-200-26.preview.pdf"


def test_set_document_preview_key_returns_none_when_document_missing(db_session):
    from core.db import repository

    assert repository.set_document_preview_key(db_session, 999999, "some/key.pdf") is None
