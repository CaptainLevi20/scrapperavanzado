def test_post_bulk_download_creates_row_and_dispatches_task(api_client, auth_header, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "api.routers.bulk_downloads.build_bulk_download_zip.delay", lambda bulk_download_id: calls.append(bulk_download_id)
    )

    response = api_client.post("/bulk-downloads", headers=auth_header)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["document_count"] == 0
    assert calls == [body["id"]]


def test_get_bulk_downloads_lists_most_recent_first(api_client, auth_header, monkeypatch):
    monkeypatch.setattr("api.routers.bulk_downloads.build_bulk_download_zip.delay", lambda *a, **k: None)

    first = api_client.post("/bulk-downloads", headers=auth_header).json()
    second = api_client.post("/bulk-downloads", headers=auth_header).json()

    response = api_client.get("/bulk-downloads", headers=auth_header)

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [second["id"], first["id"]]


def test_get_bulk_download_download_returns_404_when_not_completed(api_client, auth_header, monkeypatch):
    monkeypatch.setattr("api.routers.bulk_downloads.build_bulk_download_zip.delay", lambda *a, **k: None)

    created = api_client.post("/bulk-downloads", headers=auth_header).json()

    response = api_client.get(f"/bulk-downloads/{created['id']}/download", headers=auth_header)

    assert response.status_code == 404


def test_get_bulk_download_download_returns_signed_url_when_completed(api_client, auth_header, db_session):
    from core.db import repository

    bulk_download = repository.create_bulk_download(db_session)
    repository.set_bulk_download_status(
        db_session, bulk_download.id, "completed", document_count=2, zip_storage_key="bulk-downloads/1.zip"
    )

    response = api_client.get(f"/bulk-downloads/{bulk_download.id}/download", headers=auth_header)

    assert response.status_code == 200
    assert "url" in response.json()


def test_get_bulk_download_download_signs_against_the_bucket_it_was_actually_uploaded_to(
    api_client, auth_header, db_session, monkeypatch
):
    """Regression test: the presigned URL used to always sign against whatever
    s3_bucket is configured RIGHT NOW, not the bucket the zip actually landed
    in when it was built. If that setting is ever reconfigured, an old zip
    would become unreachable even though the file itself never moved."""
    from core.db import repository

    bulk_download = repository.create_bulk_download(db_session)
    repository.set_bulk_download_status(
        db_session,
        bulk_download.id,
        "completed",
        document_count=2,
        zip_storage_key="bulk-downloads/1.zip",
        storage_bucket="a-different-bucket-name",
    )

    captured = {}

    def _fake_presigned_url(bucket, key, **kwargs):
        captured["bucket"] = bucket
        return "https://example.com/signed"

    monkeypatch.setattr("api.routers.bulk_downloads.presigned_url", _fake_presigned_url)

    response = api_client.get(f"/bulk-downloads/{bulk_download.id}/download", headers=auth_header)

    assert response.status_code == 200
    assert captured["bucket"] == "a-different-bucket-name"


def test_get_bulk_download_download_falls_back_to_the_default_bucket_for_rows_without_one(
    api_client, auth_header, db_session, monkeypatch
):
    """A row written before storage_bucket existed (or otherwise never
    recorded one) has nothing to fall back on except the current default."""
    from core.config import get_settings
    from core.db import repository

    bulk_download = repository.create_bulk_download(db_session)
    repository.set_bulk_download_status(
        db_session, bulk_download.id, "completed", document_count=2, zip_storage_key="bulk-downloads/1.zip"
    )

    captured = {}

    def _fake_presigned_url(bucket, key, **kwargs):
        captured["bucket"] = bucket
        return "https://example.com/signed"

    monkeypatch.setattr("api.routers.bulk_downloads.presigned_url", _fake_presigned_url)

    response = api_client.get(f"/bulk-downloads/{bulk_download.id}/download", headers=auth_header)

    assert response.status_code == 200
    assert captured["bucket"] == get_settings().s3_bucket


def test_delete_bulk_download_frees_its_documents_and_deletes_the_zip(api_client, auth_header, db_session, monkeypatch):
    from core.db import repository

    repository.create_source_family(db_session, key="jep", display_name="JEP")
    source = repository.create_source(db_session, family_key="jep", name="JEP", family_params={})
    bulk_download = repository.create_bulk_download(db_session)
    repository.set_bulk_download_status(
        db_session, bulk_download.id, "completed", document_count=1, zip_storage_key="bulk-downloads/1.zip",
        storage_bucket="a-bucket",
    )
    document = repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="Doc 1", review_status="useful",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.mark_documents_bulk_downloaded(db_session, [document.id], bulk_download.id)

    deleted = {}
    monkeypatch.setattr(
        "api.routers.bulk_downloads.delete_object",
        lambda bucket, key: deleted.update(bucket=bucket, key=key),
    )

    response = api_client.delete(f"/bulk-downloads/{bulk_download.id}", headers=auth_header)

    assert response.status_code == 200
    assert response.json() == {"documents_freed": 1}
    assert deleted == {"bucket": "a-bucket", "key": "bulk-downloads/1.zip"}
    assert repository.get_bulk_download(db_session, bulk_download.id) is None
    refreshed = repository.get_document(db_session, document.id)
    assert refreshed.bulk_download_id is None


def test_delete_bulk_download_skips_storage_delete_when_there_is_no_zip(api_client, auth_header, db_session, monkeypatch):
    """A bulk download that never completed (pending/failed) has no
    zip_storage_key — nothing to delete in MinIO, and delete_object must not
    be called with an empty key."""
    from core.db import repository

    bulk_download = repository.create_bulk_download(db_session)

    calls = []
    monkeypatch.setattr("api.routers.bulk_downloads.delete_object", lambda bucket, key: calls.append((bucket, key)))

    response = api_client.delete(f"/bulk-downloads/{bulk_download.id}", headers=auth_header)

    assert response.status_code == 200
    assert response.json() == {"documents_freed": 0}
    assert calls == []


def test_delete_bulk_download_returns_404_for_unknown_id(api_client, auth_header):
    assert api_client.delete("/bulk-downloads/999999", headers=auth_header).status_code == 404


def test_get_bulk_downloads_rejects_out_of_range_limit_and_offset(api_client, auth_header):
    assert api_client.get("/bulk-downloads?offset=-1", headers=auth_header).status_code == 422
    assert api_client.get("/bulk-downloads?limit=0", headers=auth_header).status_code == 422
    assert api_client.get("/bulk-downloads?limit=1000000", headers=auth_header).status_code == 422


def test_bulk_downloads_endpoints_require_authentication(api_client):
    assert api_client.post("/bulk-downloads").status_code == 401
    assert api_client.get("/bulk-downloads").status_code == 401
    assert api_client.get("/bulk-downloads/1/download").status_code == 401
    assert api_client.delete("/bulk-downloads/1").status_code == 401
