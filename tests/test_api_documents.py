def test_list_documents_paginates_and_filters(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-02-01/Sentencia/T-065-24.rtf",
    )

    response = api_client.get("/documents", headers=auth_header)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["doc_id"] == "doc-1"


def test_get_document_returns_404_when_missing(api_client, auth_header):
    response = api_client.get("/documents/999999", headers=auth_header)
    assert response.status_code == 404


def test_download_document_redirects_to_presigned_url(api_client, auth_header, db_session, monkeypatch):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-02-01/Sentencia/T-065-24.rtf",
    )

    monkeypatch.setattr("api.routers.documents.presigned_url", lambda bucket, key: "https://signed.example.com/file")

    response = api_client.get(f"/documents/{document.id}/download", headers=auth_header, follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "https://signed.example.com/file"


def test_list_documents_filters_by_review_status(api_client, auth_header, db_session):
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

    response = api_client.get("/documents", params={"review_status": "useful"}, headers=auth_header)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["doc_id"] == "doc-useful"
    assert body["items"][0]["review_status"] == "useful"


def test_patch_document_review_status_updates_and_returns_document(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    response = api_client.patch(
        f"/documents/{document.id}", json={"review_status": "not_useful"}, headers=auth_header
    )

    assert response.status_code == 200
    body = response.json()
    assert body["review_status"] == "not_useful"
    assert body["reviewed_at"] is not None


def test_patch_document_review_status_returns_404_when_missing(api_client, auth_header):
    response = api_client.patch("/documents/999999", json={"review_status": "useful"}, headers=auth_header)
    assert response.status_code == 404


def test_patch_document_review_status_rejects_invalid_value(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    response = api_client.patch(
        f"/documents/{document.id}", json={"review_status": "maybe"}, headers=auth_header
    )

    assert response.status_code == 422


def test_bulk_patch_document_review_status_updates_multiple(api_client, auth_header, db_session):
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

    response = api_client.patch(
        "/documents/bulk-review",
        json={"document_ids": [doc1.id, doc2.id], "review_status": "useful"},
        headers=auth_header,
    )

    assert response.status_code == 200
    assert response.json() == {"updated": 2}


def test_bulk_patch_document_review_status_rejects_empty_list(api_client, auth_header):
    response = api_client.patch(
        "/documents/bulk-review",
        json={"document_ids": [], "review_status": "useful"},
        headers=auth_header,
    )

    assert response.status_code == 422


def test_bulk_patch_document_review_status_rejects_invalid_value(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    doc1 = repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="Uno",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )

    response = api_client.patch(
        "/documents/bulk-review",
        json={"document_ids": [doc1.id], "review_status": "maybe"},
        headers=auth_header,
    )

    assert response.status_code == 422


def test_bulk_patch_document_review_status_does_not_collide_with_single_patch_route(api_client, auth_header, db_session):
    # Regresión del orden de rutas: /documents/bulk-review no debe ser
    # capturada por /documents/{document_id} (que intentaría parsear
    # "bulk-review" como int y fallaría con un 422 distinto/incorrecto).
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    doc1 = repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="Uno",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )

    response = api_client.patch(
        "/documents/bulk-review",
        json={"document_ids": [doc1.id], "review_status": "useful"},
        headers=auth_header,
    )

    assert response.status_code == 200
    assert response.json() == {"updated": 1}


def test_preview_pdf_document_redirects_to_original_file(api_client, auth_header, db_session, monkeypatch):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-pdf",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-02-01/Sentencia/T-065-24.pdf",
        content_type="application/pdf",
    )

    monkeypatch.setattr("api.routers.documents.presigned_url", lambda bucket, key: f"https://signed.example.com/{key}")

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header, follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "https://signed.example.com/Corte%20Constitucional/2024-02-01/Sentencia/T-065-24.pdf"


def test_preview_rtf_document_with_cached_preview_redirects_without_calling_celery(api_client, auth_header, db_session, monkeypatch):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-cached",
        source_id=source.id,
        title="T-200/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Tutela/T-200-26.rtf",
        content_type="application/rtf",
    )
    repository.set_document_preview_key(db_session, document.id, "Corte Constitucional/2026-06-30/Tutela/T-200-26.preview.pdf")

    monkeypatch.setattr("api.routers.documents.presigned_url", lambda bucket, key: f"https://signed.example.com/{key}")

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("no debería encolar la tarea si ya hay un preview cacheado")

    monkeypatch.setattr("api.routers.documents.generate_document_preview_pdf", _fail_if_called)

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header, follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "https://signed.example.com/Corte%20Constitucional/2026-06-30/Tutela/T-200-26.preview.pdf"


def test_preview_rtf_document_without_cache_triggers_conversion_and_redirects(api_client, auth_header, db_session, monkeypatch):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-new",
        source_id=source.id,
        title="T-202/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Tutela/T-202-26.rtf",
        content_type="application/rtf",
    )

    monkeypatch.setattr("api.routers.documents.presigned_url", lambda bucket, key: f"https://signed.example.com/{key}")

    class _FakeAsyncResult:
        def get(self, timeout=None):
            return "Corte Constitucional/2026-06-30/Tutela/T-202-26.preview.pdf"

    class _FakeTask:
        def delay(self, document_id):
            return _FakeAsyncResult()

    monkeypatch.setattr("api.routers.documents.generate_document_preview_pdf", _FakeTask())

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header, follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "https://signed.example.com/Corte%20Constitucional/2026-06-30/Tutela/T-202-26.preview.pdf"


def test_preview_returns_504_when_conversion_task_times_out(api_client, auth_header, db_session, monkeypatch):
    from celery.exceptions import TimeoutError as CeleryTimeoutError

    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-timeout",
        source_id=source.id,
        title="T-203/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Tutela/T-203-26.rtf",
        content_type="application/rtf",
    )

    class _FakeAsyncResult:
        def get(self, timeout=None):
            raise CeleryTimeoutError()

    class _FakeTask:
        def delay(self, document_id):
            return _FakeAsyncResult()

    monkeypatch.setattr("api.routers.documents.generate_document_preview_pdf", _FakeTask())

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header, follow_redirects=False)

    assert response.status_code == 504
    assert response.json()["detail"] == "La vista previa está tardando más de lo esperado, intenta de nuevo"


def test_preview_returns_502_when_conversion_fails(api_client, auth_header, db_session, monkeypatch):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-fail",
        source_id=source.id,
        title="T-204/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Tutela/T-204-26.rtf",
        content_type="application/rtf",
    )

    class _FakeAsyncResult:
        def get(self, timeout=None):
            raise RuntimeError("Word no disponible")

    class _FakeTask:
        def delay(self, document_id):
            return _FakeAsyncResult()

    monkeypatch.setattr("api.routers.documents.generate_document_preview_pdf", _FakeTask())

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header, follow_redirects=False)

    assert response.status_code == 502
    assert response.json()["detail"] == "No se pudo generar la vista previa"


def test_preview_returns_404_for_a_non_convertible_content_type(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-unsupported",
        source_id=source.id,
        title="Reporte",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Otro/reporte.txt",
        content_type="text/plain",
    )

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header, follow_redirects=False)

    assert response.status_code == 404
    assert response.json()["detail"] == "Vista previa no disponible para este tipo de archivo"
