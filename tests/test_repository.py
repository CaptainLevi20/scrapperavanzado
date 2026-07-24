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


def test_count_rama_judicial_documents_by_title_groups_within_the_family_only(db_session):
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

    result = repository.count_rama_judicial_documents_by_title(db_session, [shared_title])

    assert result == {shared_title: 2}


def test_count_rama_judicial_documents_by_title_returns_empty_dict_for_empty_input(db_session):
    assert repository.count_rama_judicial_documents_by_title(db_session, []) == {}


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
        db_session, family_key="rama_judicial", collapse_rama_judicial_cases=True
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
        db_session, family_key="rama_judicial", collapse_rama_judicial_cases=True
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
        db_session, family_key="rama_judicial", collapse_rama_judicial_cases=True
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
        db_session, family_key="rama_judicial", collapse_rama_judicial_cases=True
    )

    assert total == 1
    assert items[0].doc_id == "doc-dated"


def test_list_documents_collapse_does_not_apply_to_fallback_titles(db_session):
    """A magistrado-name fallback title repeated across unrelated documents must
    never be collapsed, even with collapse_rama_judicial_cases=True."""
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
        db_session, family_key="rama_judicial", collapse_rama_judicial_cases=True
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

    items, total = repository.list_documents(db_session, collapse_rama_judicial_cases=True)

    doc_ids = {d.doc_id for d in items}
    assert "doc-rama-old" not in doc_ids
    assert "doc-rama-new" in doc_ids
    assert "doc-jep" in doc_ids
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
