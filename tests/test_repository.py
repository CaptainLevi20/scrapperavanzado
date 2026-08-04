import pytest

from core.db import repository


def test_create_and_list_sources(db_session):
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})

    sources = repository.list_sources(db_session, family_key="constitucional")
    assert [s.name for s in sources] == ["Corte Constitucional"]


def test_list_sources_filters_by_has_documents(db_session):
    """The Documents page's Fuente filter should only offer sources that actually
    have at least one document — a source with zero documents just clutters the
    dropdown with an option that would always return an empty table."""
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    with_docs = repository.create_source(
        db_session, family_key="constitucional", name="Corte Constitucional", family_params={}
    )
    without_docs = repository.create_source(
        db_session, family_key="constitucional", name="Fuente Vacía", family_params={}
    )
    repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=with_docs.id,
        title="T-100/24",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    sources = repository.list_sources(db_session, has_documents=True)

    assert [s.id for s in sources] == [with_docs.id]
    assert without_docs.id not in [s.id for s in sources]


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


def test_bulk_download_lifecycle(db_session):
    from datetime import datetime, timezone

    bulk_download = repository.create_bulk_download(db_session)
    assert bulk_download.status == "pending"
    assert bulk_download.document_count == 0
    assert bulk_download.failed_count == 0

    repository.set_bulk_download_status(
        db_session, bulk_download.id, "running", started_at=datetime.now(timezone.utc)
    )
    refreshed = repository.get_bulk_download(db_session, bulk_download.id)
    assert refreshed.status == "running"
    assert refreshed.started_at is not None

    repository.set_bulk_download_status(
        db_session,
        bulk_download.id,
        "completed",
        document_count=5,
        failed_count=1,
        zip_storage_key="bulk-downloads/1.zip",
        finished_at=datetime.now(timezone.utc),
    )
    refreshed = repository.get_bulk_download(db_session, bulk_download.id)
    assert refreshed.status == "completed"
    assert refreshed.document_count == 5
    assert refreshed.failed_count == 1
    assert refreshed.zip_storage_key == "bulk-downloads/1.zip"


def test_set_run_status_does_not_raise_for_a_nonexistent_run(db_session):
    """Regression test: this used to be a bare db.get(Run, run_id) with no None
    check — a run that was deleted (or a stale/wrong id from a leftover Celery
    task) raised AttributeError instead of just being a no-op."""
    repository.set_run_status(db_session, 999999, "completed")


def test_set_run_source_status_does_not_raise_for_a_nonexistent_run_source(db_session):
    repository.set_run_source_status(db_session, 999999, "completed", docs_new=1)


def test_set_bulk_download_status_does_not_raise_for_a_nonexistent_bulk_download(db_session):
    repository.set_bulk_download_status(db_session, 999999, "completed")


def test_touch_session_does_not_raise_for_a_nonexistent_session(db_session):
    """touch_session runs on every authenticated request (api/deps.py) — a
    session deleted in the tiny window between being validated and being
    touched (e.g. a concurrent logout) must not turn an otherwise-successful
    request into a 500."""
    repository.touch_session(db_session, 999999)


def test_update_user_password_does_not_raise_for_a_nonexistent_user(db_session):
    repository.update_user_password(db_session, 999999, "new-hash")


def test_touch_user_last_login_does_not_raise_for_a_nonexistent_user(db_session):
    repository.touch_user_last_login(db_session, 999999)


def test_list_bulk_downloads_orders_by_most_recent_first(db_session):
    first = repository.create_bulk_download(db_session)
    second = repository.create_bulk_download(db_session)

    listed = repository.list_bulk_downloads(db_session)

    assert [item.id for item in listed] == [second.id, first.id]


def test_list_useful_documents_filters_by_review_status(db_session):
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-useful", source_id=source.id, title="A", review_status="useful",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-pending", source_id=source.id, title="B",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    useful = repository.list_useful_documents(db_session)

    assert [doc.doc_id for doc in useful] == ["doc-useful"]


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


def test_insert_document_reporting_whether_created_reports_true_only_on_the_first_insert(db_session):
    """Regression test: insert_document's on_conflict_do_nothing made the
    second call a silent no-op with no way to tell it apart from a real
    insert — worker/tasks.py used to count every attempt as 'new' regardless,
    inflating docs_new when the same doc_id was attempted twice."""
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})

    payload = dict(
        doc_id="report-created-test",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-02-01/Sentencia/T-065-24.rtf",
    )
    first_doc, first_created = repository.insert_document_reporting_whether_created(db_session, **payload)
    second_doc, second_created = repository.insert_document_reporting_whether_created(db_session, **payload)

    assert first_created is True
    assert second_created is False
    assert first_doc.id == second_doc.id


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


def test_list_documents_orders_by_f_public_descending_with_nulls_last(db_session):
    from datetime import date

    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-older", source_id=source.id, title="Older", f_public=date(2026, 1, 1),
        storage_bucket="iurisync-test", storage_key="older.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-no-date", source_id=source.id, title="No date", f_public=None,
        storage_bucket="iurisync-test", storage_key="no-date.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-newer", source_id=source.id, title="Newer", f_public=date(2026, 6, 1),
        storage_bucket="iurisync-test", storage_key="newer.pdf",
    )

    items, _ = repository.list_documents(db_session)

    assert [d.doc_id for d in items] == ["doc-newer", "doc-older", "doc-no-date"]


def test_list_documents_total_counts_every_match_not_just_the_current_page(db_session):
    """Regression test: total used to be computed by materializing every
    matching Document row and calling len() on it — functionally correct, but
    means the count must reflect ALL matches regardless of limit/offset, not
    just what fits on the current page. This pins that behavior down through
    the COUNT-subquery rewrite."""
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    for i in range(5):
        repository.insert_document(
            db_session, doc_id=f"doc-{i}", source_id=source.id, title=f"Doc {i}",
            storage_bucket="iurisync-test", storage_key=f"{i}.pdf",
        )

    items, total = repository.list_documents(db_session, limit=2, offset=0)

    assert total == 5
    assert len(items) == 2

    items_page_2, total_page_2 = repository.list_documents(db_session, limit=2, offset=4)
    assert total_page_2 == 5
    assert len(items_page_2) == 1


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


def test_list_distinct_document_tipos_scoped_to_a_source(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source_a = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    source_b = repository.create_source(db_session, family_key="constitucional", name="Otra fuente", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source_a.id, title="A", tipo="Sentencia",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source_b.id, title="B", tipo="Auto",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    assert repository.list_distinct_document_tipos(db_session, source_id=source_a.id) == ["Sentencia"]
    assert repository.list_distinct_document_tipos(db_session, source_id=source_b.id) == ["Auto"]


def test_list_distinct_document_secciones_scoped_to_tipo(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="A", tipo="Sentencia", seccion="SECCION PRIMERA",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="B", tipo="Auto", seccion="SECCION SEGUNDA",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-3", source_id=source.id, title="C", tipo=None, seccion=None,
        storage_bucket="iurisync-test", storage_key="c.pdf",
    )

    assert repository.list_distinct_document_secciones(db_session) == ["SECCION PRIMERA", "SECCION SEGUNDA"]
    assert repository.list_distinct_document_secciones(db_session, source_id=source.id, tipo="Sentencia") == ["SECCION PRIMERA"]
    assert repository.list_distinct_document_secciones(db_session, tipo="Auto") == ["SECCION SEGUNDA"]


def test_list_distinct_document_especialidades_scoped_to_seccion(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="A", seccion="SECCION PRIMERA", especialidad="Nulidad",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="B", seccion="SECCION SEGUNDA", especialidad="Conciliación",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    assert repository.list_distinct_document_especialidades(db_session) == ["Conciliación", "Nulidad"]
    assert repository.list_distinct_document_especialidades(db_session, seccion="SECCION PRIMERA") == ["Nulidad"]
    assert repository.list_distinct_document_especialidades(db_session, seccion="SECCION SEGUNDA") == ["Conciliación"]


def test_list_distinct_document_magistrados_scoped_to_especialidad(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="A", especialidad="Nulidad", magistrado="Ana Pérez",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="B", especialidad="Conciliación", magistrado="Luis Gómez",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    assert repository.list_distinct_document_magistrados(db_session) == ["Ana Pérez", "Luis Gómez"]
    assert repository.list_distinct_document_magistrados(db_session, especialidad="Nulidad") == ["Ana Pérez"]
    assert repository.list_distinct_document_magistrados(db_session, especialidad="Conciliación") == ["Luis Gómez"]


def test_list_documents_filters_by_seccion_especialidad_magistrado(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    match = repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="Coincide",
        seccion="SECCION PRIMERA", especialidad="Nulidad", magistrado="Ana Pérez",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="No coincide",
        seccion="SECCION SEGUNDA", especialidad="Conciliación", magistrado="Luis Gómez",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    items, total = repository.list_documents(
        db_session, seccion="SECCION PRIMERA", especialidad="Nulidad", magistrado="Ana Pérez"
    )

    assert total == 1
    assert items[0].id == match.id


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


def test_create_user_defaults_to_not_admin(db_session):
    user = repository.create_user(db_session, username="ana", password_hash="hashed")
    assert user.is_admin is False


def test_create_user_can_be_created_as_admin(db_session):
    user = repository.create_user(db_session, username="admin", password_hash="hashed", is_admin=True)
    assert user.is_admin is True


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


def test_get_document_by_doc_id_returns_none_when_missing(db_session):
    assert repository.get_document_by_doc_id(db_session, "does-not-exist") is None


def test_archive_and_replace_document_snapshots_old_file_and_updates_with_new(db_session):
    from datetime import datetime, timezone

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    original_downloaded_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
    document = repository.insert_document(
        db_session,
        doc_id="doc-republished",
        source_id=source.id,
        title="A. 829/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-01/Auto/A.829-26.rtf",
        content_type="application/rtf",
        file_size_bytes=76245,
        source_url="https://www.corteconstitucional.gov.co/sentencias/Autos/2026/A829-26.rtf",
        review_status="useful",
        downloaded_at=original_downloaded_at,
    )
    assert repository.get_document_by_doc_id(db_session, "doc-republished").id == document.id

    updated = repository.archive_and_replace_document(
        db_session,
        document.id,
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-01/Auto/A.829-26-republicado-20260716T120000.rtf",
        content_type="application/rtf",
        file_extension=".rtf",
        file_size_bytes=98000,
        converted_format=None,
    )

    assert updated.storage_key == "Corte Constitucional/2026-06-01/Auto/A.829-26-republicado-20260716T120000.rtf"
    assert updated.file_size_bytes == 98000
    assert updated.review_status == "pending"
    assert updated.reviewed_at is None

    [version] = repository.list_document_versions(db_session, document.id)
    assert version.storage_key == "Corte Constitucional/2026-06-01/Auto/A.829-26.rtf"
    assert version.file_size_bytes == 76245
    assert version.downloaded_at == original_downloaded_at


def test_archive_and_replace_document_refreshes_downloaded_at_so_chained_replacements_snapshot_correctly(db_session):
    # Regression guard: archive_and_replace_document used to leave downloaded_at
    # frozen at the original download time. A second replacement would then
    # snapshot that stale value into its DocumentVersion row instead of the
    # actual time the intermediate (first-replacement) version was fetched.
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-chained-replace",
        source_id=source.id,
        title="A. 1/26",
        storage_bucket="iurisync-test",
        storage_key="v1.rtf",
        file_size_bytes=100,
    )
    original_downloaded_at = document.downloaded_at

    first_replacement = repository.archive_and_replace_document(
        db_session, document.id, storage_bucket="iurisync-test", storage_key="v2.rtf", file_size_bytes=200
    )
    assert first_replacement.downloaded_at != original_downloaded_at
    first_replacement_downloaded_at = first_replacement.downloaded_at

    second_replacement = repository.archive_and_replace_document(
        db_session, document.id, storage_bucket="iurisync-test", storage_key="v3.rtf", file_size_bytes=300
    )

    versions = repository.list_document_versions(db_session, document.id)
    # versions[0] es la más recientemente reemplazada (v2, archivada en el segundo
    # reemplazo) — su downloaded_at debe ser el momento real en que v2 fue
    # descargada (el primer reemplazo), no la fecha de creación original de v1.
    assert versions[0].storage_key == "v2.rtf"
    assert versions[0].downloaded_at == first_replacement_downloaded_at
    assert second_replacement.downloaded_at != first_replacement_downloaded_at


def test_archive_and_replace_document_raises_a_clear_error_when_the_document_no_longer_exists(db_session):
    """Regression test: this used to be `db.get(Document, document_id)` with no
    None check, so a document deleted between being listed as a republication
    candidate and this write raised a bare AttributeError deep inside — now it
    must fail with a clear, specific error the caller can actually log."""
    with pytest.raises(ValueError, match="ya no existe"):
        repository.archive_and_replace_document(
            db_session, 999999, storage_bucket="iurisync-test", storage_key="v2.rtf", file_size_bytes=200
        )


def test_archive_and_replace_document_blocks_on_a_concurrent_in_flight_replacement(test_engine):
    """Regression test: two overlapping runs replacing the same republished
    document used to both read the same stale row (plain read-modify-write, no
    locking) and the last commit silently won, leaving a DocumentVersion that
    doesn't actually match what was overwritten. with_for_update() must make a
    second, concurrent replacement block on the row lock until the first one
    commits, instead of racing it."""
    import threading
    import time

    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=test_engine, future=True)

    setup_session = session_factory()
    repository.create_source_family(setup_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(
        setup_session, family_key="constitucional", name="Corte Constitucional", family_params={}
    )
    document = repository.insert_document(
        setup_session,
        doc_id="doc-concurrent-replace",
        source_id=source.id,
        title="A. 1/26",
        storage_bucket="iurisync-test",
        storage_key="v1.rtf",
        file_size_bytes=100,
    )
    document_id = document.id
    setup_session.close()

    lock_acquired = threading.Event()
    release_lock = threading.Event()
    timeline: list[tuple[str, float]] = []

    def _hold_the_row_lock():
        from sqlalchemy import select

        from core.db.models import Document

        session = session_factory()
        session.execute(select(Document).where(Document.id == document_id).with_for_update())
        lock_acquired.set()
        release_lock.wait(timeout=5)
        timeline.append(("first_write_committed", time.monotonic()))
        session.commit()
        session.close()

    holder = threading.Thread(target=_hold_the_row_lock)
    holder.start()
    assert lock_acquired.wait(timeout=5), "el hilo que sostiene el lock nunca lo adquirió"

    second_session = session_factory()

    def _second_replacement():
        repository.archive_and_replace_document(
            second_session,
            document_id,
            storage_bucket="iurisync-test",
            storage_key="v2-from-second-run.rtf",
            file_size_bytes=200,
        )
        timeline.append(("second_write_done", time.monotonic()))

    waiter = threading.Thread(target=_second_replacement)
    waiter.start()

    # Give the second thread every chance to (wrongly) proceed without blocking.
    time.sleep(0.5)
    assert waiter.is_alive(), "la segunda escritura no debería avanzar mientras la primera sostiene el lock"

    release_lock.set()
    holder.join(timeout=5)
    waiter.join(timeout=5)
    assert not waiter.is_alive()

    assert [event for event, _ in timeline] == ["first_write_committed", "second_write_done"]
    second_session.close()


def test_list_document_versions_orders_most_recently_superseded_first(db_session):
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-multi-version",
        source_id=source.id,
        title="A. 900/26",
        storage_bucket="iurisync-test",
        storage_key="v1.rtf",
        file_size_bytes=100,
    )
    repository.archive_and_replace_document(
        db_session, document.id, storage_bucket="iurisync-test", storage_key="v2.rtf", file_size_bytes=200
    )
    repository.archive_and_replace_document(
        db_session, document.id, storage_bucket="iurisync-test", storage_key="v3.rtf", file_size_bytes=300
    )

    versions = repository.list_document_versions(db_session, document.id)

    assert [v.storage_key for v in versions] == ["v2.rtf", "v1.rtf"]
    assert repository.get_document_version(db_session, versions[0].id).id == versions[0].id

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


def test_delete_sessions_for_user_removes_all_except_the_given_token(db_session):
    user = repository.create_user(db_session, username="ana", password_hash="hashed")
    repository.create_session(db_session, user_id=user.id, token_hash="keep-me")
    repository.create_session(db_session, user_id=user.id, token_hash="kick-me-1")
    repository.create_session(db_session, user_id=user.id, token_hash="kick-me-2")

    removed = repository.delete_sessions_for_user(db_session, user.id, except_token_hash="keep-me")

    assert removed == 2
    assert repository.get_valid_session_by_token_hash(db_session, "keep-me") is not None
    assert repository.get_valid_session_by_token_hash(db_session, "kick-me-1") is None
    assert repository.get_valid_session_by_token_hash(db_session, "kick-me-2") is None


def test_delete_sessions_for_user_removes_everything_when_no_exception_given(db_session):
    user = repository.create_user(db_session, username="ana", password_hash="hashed")
    repository.create_session(db_session, user_id=user.id, token_hash="tok-1")
    repository.create_session(db_session, user_id=user.id, token_hash="tok-2")

    removed = repository.delete_sessions_for_user(db_session, user.id)

    assert removed == 2
    assert repository.get_valid_session_by_token_hash(db_session, "tok-1") is None
    assert repository.get_valid_session_by_token_hash(db_session, "tok-2") is None


def test_delete_sessions_for_user_does_not_affect_other_users(db_session):
    user_a = repository.create_user(db_session, username="ana", password_hash="hashed")
    user_b = repository.create_user(db_session, username="bea", password_hash="hashed")
    repository.create_session(db_session, user_id=user_a.id, token_hash="ana-tok")
    repository.create_session(db_session, user_id=user_b.id, token_hash="bea-tok")

    repository.delete_sessions_for_user(db_session, user_a.id)

    assert repository.get_valid_session_by_token_hash(db_session, "ana-tok") is None
    assert repository.get_valid_session_by_token_hash(db_session, "bea-tok") is not None


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


def test_list_documents_filters_by_title_exact_not_substring(db_session):
    """title_exact must be a real equality filter, unlike the existing
    title_contains (ilike '%...%'), which would incorrectly match both of these
    since one title is a superstring of the other."""
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    repository.insert_document(
        db_session,
        doc_id="doc-exact",
        source_id=source.id,
        title="T_BTA_11001_31_03_048_2022_00418_02",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )
    repository.insert_document(
        db_session,
        doc_id="doc-superstring",
        source_id=source.id,
        title="T_BTA_11001_31_03_048_2022_00418_02X",
        storage_bucket="iurisync-test",
        storage_key="b.pdf",
    )

    items, total = repository.list_documents(db_session, title_exact="T_BTA_11001_31_03_048_2022_00418_02")

    assert total == 1
    assert [d.doc_id for d in items] == ["doc-exact"]


def test_list_documents_title_contains_treats_underscore_as_a_literal_character(db_session):
    """Regression test: title_contains used to build a raw ILIKE '%...%' pattern
    without escaping LIKE metacharacters. '_' is a SQL LIKE wildcard for "any
    single character" — Rama Judicial titles are full of real underscores
    (e.g. "T_BTA_11001_..."), so searching for one used to also match unrelated
    titles that merely have SOME character in each of those positions."""
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(db_session, family_key="rama_judicial", name="Tribunal", family_params={})
    repository.insert_document(
        db_session,
        doc_id="doc-real",
        source_id=source.id,
        title="T_BTA_11001_31_03_048_2022_00418_02",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )
    # Same length, every underscore position replaced by an "X" — with '_'
    # treated as a wildcard this would falsely match a search for "T_BTA".
    repository.insert_document(
        db_session,
        doc_id="doc-unrelated",
        source_id=source.id,
        title="TXBTAX11001X31X03X048X2022X00418X02",
        storage_bucket="iurisync-test",
        storage_key="b.pdf",
    )

    items, total = repository.list_documents(db_session, title_contains="T_BTA")

    assert total == 1
    assert [d.doc_id for d in items] == ["doc-real"]


def test_list_documents_title_contains_treats_percent_as_a_literal_character(db_session):
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="CC", family_params={})
    repository.insert_document(
        db_session,
        doc_id="doc-percent",
        source_id=source.id,
        title="Acuerdo 100% Seguro",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )
    repository.insert_document(
        db_session,
        doc_id="doc-other",
        source_id=source.id,
        title="Acuerdo 100 cosas Seguro",
        storage_bucket="iurisync-test",
        storage_key="b.pdf",
    )

    items, total = repository.list_documents(db_session, title_contains="100%")

    assert total == 1
    assert [d.doc_id for d in items] == ["doc-percent"]


def test_list_documents_title_contains_still_matches_normally_without_metacharacters(db_session):
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="CC", family_params={})
    repository.insert_document(
        db_session,
        doc_id="doc-match",
        source_id=source.id,
        title="Sentencia sobre tutela",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )
    repository.insert_document(
        db_session,
        doc_id="doc-no-match",
        source_id=source.id,
        title="Auto de sustanciación",
        storage_bucket="iurisync-test",
        storage_key="b.pdf",
    )

    items, total = repository.list_documents(db_session, title_contains="tutela")

    assert total == 1
    assert [d.doc_id for d in items] == ["doc-match"]


def test_get_source_family_keys_returns_a_mapping_for_the_given_ids(db_session):
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    repository.create_source_family(db_session, key="jep", display_name="JEP")
    rama_source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    jep_source = repository.create_source(db_session, family_key="jep", name="JEP", family_params={})

    result = repository.get_source_family_keys(db_session, [rama_source.id, jep_source.id])

    assert result == {rama_source.id: "rama_judicial", jep_source.id: "jep"}


def test_get_source_family_keys_returns_empty_dict_for_empty_input(db_session):
    assert repository.get_source_family_keys(db_session, []) == {}


def test_count_documents_by_title_within_family_groups_within_the_family_only(db_session):
    """The same title in a DIFFERENT family must not be counted together with the
    rama_judicial ones — a coincidental title collision across families isn't the
    same case."""
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    repository.create_source_family(db_session, key="jep", display_name="JEP")
    rama_source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    jep_source = repository.create_source(db_session, family_key="jep", name="JEP", family_params={})

    shared_title = "T_BTA_11001_31_03_048_2022_00418_02"
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=rama_source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=rama_source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-3", source_id=jep_source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="c.pdf",
    )

    result = repository.count_documents_by_title_within_family(db_session, [shared_title], "rama_judicial")

    assert result == {shared_title: 2}


def test_count_documents_by_title_within_family_works_for_samai_too(db_session):
    """Consejo de Estado (samai) cases work the same way as rama_judicial's —
    several actuaciones on the same case share the exact same title."""
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})

    shared_title = "11001-03-28-000-2026-00271-00(NE)"
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    result = repository.count_documents_by_title_within_family(db_session, [shared_title], "samai")

    assert result == {shared_title: 2}


def test_count_documents_by_title_within_family_returns_empty_dict_for_empty_input(db_session):
    assert repository.count_documents_by_title_within_family(db_session, [], "rama_judicial") == {}


def test_list_documents_collapse_keeps_only_the_most_recent_actuacion(db_session):
    """The Documents table should show only the newest actuación of a shared
    radicado by default — the older ones remain fetchable via title_exact for
    the case-view modal, they just don't clutter the general listing."""
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    shared_title = "T_BTA_11001_31_03_048_2022_00418_02"
    from datetime import date
    repository.insert_document(
        db_session, doc_id="doc-old", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="a.pdf", f_public=date(2026, 1, 1),
    )
    repository.insert_document(
        db_session, doc_id="doc-mid", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="b.pdf", f_public=date(2026, 2, 1),
    )
    repository.insert_document(
        db_session, doc_id="doc-new", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="c.pdf", f_public=date(2026, 3, 1),
    )

    items, total = repository.list_documents(
        db_session, family_key="rama_judicial", collapse_case_families=True
    )

    assert total == 1
    assert [d.doc_id for d in items] == ["doc-new"]


def test_list_documents_collapse_breaks_ties_by_id_when_f_public_matches(db_session):
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    shared_title = "T_BTA_11001_31_03_048_2022_00418_02"
    from datetime import date
    first = repository.insert_document(
        db_session, doc_id="doc-a", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="a.pdf", f_public=date(2026, 1, 1),
    )
    second = repository.insert_document(
        db_session, doc_id="doc-b", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="b.pdf", f_public=date(2026, 1, 1),
    )
    assert second.id > first.id  # sanity check on the tie-break assumption

    items, total = repository.list_documents(
        db_session, family_key="rama_judicial", collapse_case_families=True
    )

    assert total == 1
    assert items[0].doc_id == "doc-b"


def test_list_documents_collapse_breaks_ties_by_id_when_f_public_is_null_on_both(db_session):
    """f_public is nullable — a naive SQL comparison against NULL is never true,
    so two NULL-f_public siblings could otherwise both survive the collapse
    (neither provably "older" than the other). The id tie-break must still apply."""
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    shared_title = "T_BTA_11001_31_03_048_2022_00418_02"
    first = repository.insert_document(
        db_session, doc_id="doc-a", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="a.pdf", f_public=None,
    )
    second = repository.insert_document(
        db_session, doc_id="doc-b", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="b.pdf", f_public=None,
    )
    assert second.id > first.id

    items, total = repository.list_documents(
        db_session, family_key="rama_judicial", collapse_case_families=True
    )

    assert total == 1
    assert items[0].doc_id == "doc-b"


def test_list_documents_collapse_prefers_a_real_date_over_a_null_one_regardless_of_id(db_session):
    """A genuine f_public is stronger evidence of recency than the id tie-break,
    which should only decide ties when dates are truly indistinguishable (equal
    or both missing) — a NULL-dated sibling must never outrank a real-dated one
    just for having a higher id."""
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    shared_title = "T_BTA_11001_31_03_048_2022_00418_02"
    from datetime import date
    dated = repository.insert_document(
        db_session, doc_id="doc-dated", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="a.pdf", f_public=date(2026, 1, 1),
    )
    undated = repository.insert_document(
        db_session, doc_id="doc-undated", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="b.pdf", f_public=None,
    )
    assert undated.id > dated.id  # sanity check: id alone would favor the wrong document

    items, total = repository.list_documents(
        db_session, family_key="rama_judicial", collapse_case_families=True
    )

    assert total == 1
    assert items[0].doc_id == "doc-dated"


def test_list_documents_collapse_does_not_apply_to_fallback_titles(db_session):
    """A magistrado-name fallback title repeated across unrelated documents must
    never be collapsed, even with collapse_case_families=True."""
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Antioquia", family_params={}
    )
    repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="DR. WILLIAM SANTA MARIN",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-2", source_id=source.id, title="DR. WILLIAM SANTA MARIN",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    items, total = repository.list_documents(
        db_session, family_key="rama_judicial", collapse_case_families=True
    )

    assert total == 2


def test_list_documents_collapse_does_not_affect_other_families_with_a_coincidental_title(db_session):
    """A non-rama_judicial document sharing a radicado-shaped title with an older
    rama_judicial actuación must never be excluded by the collapse — it isn't
    part of that case."""
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    repository.create_source_family(db_session, key="jep", display_name="JEP")
    rama_source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    jep_source = repository.create_source(db_session, family_key="jep", name="JEP", family_params={})

    shared_title = "T_BTA_11001_31_03_048_2022_00418_02"
    from datetime import date
    repository.insert_document(
        db_session, doc_id="doc-rama-old", source_id=rama_source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="a.pdf", f_public=date(2026, 1, 1),
    )
    repository.insert_document(
        db_session, doc_id="doc-rama-new", source_id=rama_source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="b.pdf", f_public=date(2026, 2, 1),
    )
    repository.insert_document(
        db_session, doc_id="doc-jep", source_id=jep_source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="c.pdf", f_public=date(2026, 1, 15),
    )

    items, total = repository.list_documents(db_session, collapse_case_families=True)

    doc_ids = {d.doc_id for d in items}
    assert "doc-rama-old" not in doc_ids
    assert "doc-rama-new" in doc_ids
    assert "doc-jep" in doc_ids
    assert total == 2


def test_list_documents_collapse_keeps_only_the_most_recent_actuacion_for_samai(db_session):
    """Consejo de Estado (samai) works the same as rama_judicial's collapse —
    several actuaciones sharing a case's radicado+acronym title collapse down
    to just the newest one in the general listing."""
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
    shared_title = "11001-03-28-000-2026-00271-00(NE)"
    from datetime import date
    repository.insert_document(
        db_session, doc_id="doc-old", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="a.pdf", f_public=date(2026, 7, 14),
    )
    repository.insert_document(
        db_session, doc_id="doc-new", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="b.pdf", f_public=date(2026, 7, 27),
    )

    items, total = repository.list_documents(db_session, family_key="samai", collapse_case_families=True)

    assert total == 1
    assert [d.doc_id for d in items] == ["doc-new"]


def test_list_documents_collapse_keeps_only_the_most_recent_actuacion_for_tribunal_administrativo(db_session):
    """A Tribunal Administrativo source is also family "samai", but its titles
    look like rama_judicial's format instead of Consejo de Estado's (see
    core/scrapers/families/samai.py::_normalizar_titulo) — collapsing must
    still recognize that format as a case title within the samai family."""
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(
        db_session, family_key="samai", name="Tribunal Administrativo de Antioquia", family_params={}
    )
    shared_title = "T_ANTI_05001_23_33_000_2018_01895_00"
    from datetime import date
    repository.insert_document(
        db_session, doc_id="doc-old", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="a.pdf", f_public=date(2026, 7, 14),
    )
    repository.insert_document(
        db_session, doc_id="doc-new", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="b.pdf", f_public=date(2026, 7, 27),
    )

    items, total = repository.list_documents(db_session, family_key="samai", collapse_case_families=True)

    assert total == 1
    assert [d.doc_id for d in items] == ["doc-new"]


def test_list_documents_collapse_does_not_cross_families_between_samai_and_rama_judicial(db_session):
    """A samai and a rama_judicial document never share the same doc-count
    "sibling" pool, even in the (practically impossible, but not code-enforced
    to be impossible) case their titles happened to collide as strings."""
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    samai_source = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
    rama_source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )

    samai_title = "11001-03-28-000-2026-00271-00(NE)"
    rama_title = "T_BTA_11001_31_03_048_2022_00418_02"
    from datetime import date
    repository.insert_document(
        db_session, doc_id="doc-samai-old", source_id=samai_source.id, title=samai_title,
        storage_bucket="iurisync-test", storage_key="a.pdf", f_public=date(2026, 7, 14),
    )
    repository.insert_document(
        db_session, doc_id="doc-samai-new", source_id=samai_source.id, title=samai_title,
        storage_bucket="iurisync-test", storage_key="b.pdf", f_public=date(2026, 7, 27),
    )
    repository.insert_document(
        db_session, doc_id="doc-rama-old", source_id=rama_source.id, title=rama_title,
        storage_bucket="iurisync-test", storage_key="c.pdf", f_public=date(2026, 1, 1),
    )
    repository.insert_document(
        db_session, doc_id="doc-rama-new", source_id=rama_source.id, title=rama_title,
        storage_bucket="iurisync-test", storage_key="d.pdf", f_public=date(2026, 2, 1),
    )

    items, total = repository.list_documents(db_session, collapse_case_families=True)

    doc_ids = {d.doc_id for d in items}
    assert doc_ids == {"doc-samai-new", "doc-rama-new"}
    assert total == 2


def test_list_documents_collapse_defaults_to_false(db_session):
    """Without explicitly requesting collapse, every existing caller of
    list_documents keeps seeing every document — backward compatible default."""
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )
    shared_title = "T_BTA_11001_31_03_048_2022_00418_02"
    from datetime import date
    repository.insert_document(
        db_session, doc_id="doc-old", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="a.pdf", f_public=date(2026, 1, 1),
    )
    repository.insert_document(
        db_session, doc_id="doc-new", source_id=source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="b.pdf", f_public=date(2026, 2, 1),
    )

    items, total = repository.list_documents(db_session, family_key="rama_judicial")

    assert total == 2


def _make_samai_source(db_session, name):
    repository.create_source_family_if_missing(db_session, key="samai", display_name="SAMAI")
    return repository.create_source(db_session, family_key="samai", name=name, family_params={})


def test_generate_case_link_suggestions_for_run_creates_a_pending_suggestion_across_sources(db_session):
    tribunal = _make_samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _make_samai_source(db_session, "Consejo de Estado")

    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=tribunal.id)

    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, run_source_id=run_source.id,
        title="25000234200020200000801(NRD)", radicado="25000234200020200000801",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id,
        title="25000234200020200000802(NRD)", radicado="25000234200020200000802",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    created = repository.generate_case_link_suggestions_for_run(db_session, run.id)

    assert created == 1
    [suggestion] = repository.list_pending_case_link_suggestions(db_session)
    assert suggestion.matched_digits == 22
    assert (suggestion.source_id_a, suggestion.radicado_a) == (tribunal.id, "25000234200020200000801")
    assert (suggestion.source_id_b, suggestion.radicado_b) == (consejo.id, "25000234200020200000802")


def test_generate_case_link_suggestions_ignores_documents_in_the_same_source(db_session):
    tribunal = _make_samai_source(db_session, "Tribunal Administrativo de Antioquia")
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=tribunal.id)

    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, run_source_id=run_source.id,
        title="t1", radicado="25000234200020200000801", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=tribunal.id, run_source_id=run_source.id,
        title="t2", radicado="25000234200020200000801", storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    created = repository.generate_case_link_suggestions_for_run(db_session, run.id)

    assert created == 0
    assert repository.list_pending_case_link_suggestions(db_session) == []


def test_generate_case_link_suggestions_does_not_duplicate_an_existing_pair(db_session):
    tribunal = _make_samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _make_samai_source(db_session, "Consejo de Estado")
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=tribunal.id)
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, run_source_id=run_source.id,
        title="t1", radicado="25000234200020200000801", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id,
        title="t2", radicado="25000234200020200000802", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    repository.generate_case_link_suggestions_for_run(db_session, run.id)

    created_again = repository.generate_case_link_suggestions_for_run(db_session, run.id)

    assert created_again == 0
    assert len(repository.list_pending_case_link_suggestions(db_session)) == 1


def test_generate_case_link_suggestions_ignores_non_samai_families(db_session):
    repository.create_source_family_if_missing(db_session, key="rama_judicial", display_name="Rama Judicial")
    juzgado = repository.create_source(db_session, family_key="rama_judicial", name="Juzgado X", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=juzgado.id)
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=juzgado.id, run_source_id=run_source.id,
        title="t1", radicado="25000234200020200000801", storage_bucket="iurisync-test", storage_key="a.pdf",
    )

    created = repository.generate_case_link_suggestions_for_run(db_session, run.id)

    assert created == 0
