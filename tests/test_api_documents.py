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


def test_list_documents_filters_by_publication_date_range(api_client, auth_header, db_session):
    from datetime import date

    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session,
        doc_id="doc-en-rango",
        source_id=source.id,
        title="T-100/24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-06-15/Sentencia/T-100-24.rtf",
        f_public=date(2024, 6, 15),
    )
    repository.insert_document(
        db_session,
        doc_id="doc-fuera-de-rango",
        source_id=source.id,
        title="T-200/24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-01-05/Sentencia/T-200-24.rtf",
        f_public=date(2024, 1, 5),
    )

    response = api_client.get(
        "/documents",
        params={"f_public_from": "2024-06-01", "f_public_to": "2024-06-30"},
        headers=auth_header,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["doc_id"] == "doc-en-rango"


def test_get_document_tipos_returns_sorted_distinct_values(api_client, auth_header, db_session):
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

    response = api_client.get("/documents/tipos", headers=auth_header)

    assert response.status_code == 200
    assert response.json() == ["Auto", "Sentencia"]


def test_get_document_stats_aggregates_over_the_full_table_not_a_sample(api_client, auth_header, db_session):
    # Regression guard: the dashboard used to compute these breakdowns client-side
    # from only the 1000 most-recently-downloaded documents, which silently
    # undercounted large families once the archive passed that cap. This endpoint
    # must reflect every document, however many there are.
    from datetime import date

    from core.db import repository

    repository.create_source_family(db_session, key="corte_suprema", display_name="Corte Suprema de Justicia")
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    csj = repository.create_source(db_session, family_key="corte_suprema", name="CSJ", family_params={})
    cconst = repository.create_source(
        db_session, family_key="constitucional", name="Corte Constitucional", family_params={}
    )

    for i in range(3):
        repository.insert_document(
            db_session,
            doc_id=f"csj-{i}",
            source_id=csj.id,
            title=f"CSJ {i}",
            tipo="Sentencia",
            storage_bucket="iurisync-test",
            storage_key=f"csj-{i}.pdf",
            f_public=date(2026, 3, 10),
        )
    repository.insert_document(
        db_session,
        doc_id="const-1",
        source_id=cconst.id,
        title="Corte Const 1",
        tipo="Auto",
        storage_bucket="iurisync-test",
        storage_key="const-1.pdf",
        f_public=date(2026, 5, 20),
    )

    response = api_client.get("/documents/stats", headers=auth_header)

    assert response.status_code == 200
    body = response.json()
    by_family = {row["key"]: row["count"] for row in body["by_family"]}
    assert by_family == {"corte_suprema": 3, "constitucional": 1}
    assert next(row for row in body["by_family"] if row["key"] == "corte_suprema")["display_name"] == "Corte Suprema de Justicia"

    by_tipo = {row["tipo"]: row["count"] for row in body["by_tipo"]}
    assert by_tipo == {"Sentencia": 3, "Auto": 1}

    assert body["available_years"] == [2026]
    assert body["year"] == 2026
    assert body["by_month"][2] == 3  # marzo (0-indexado)
    assert body["by_month"][4] == 1  # mayo


def test_get_document_stats_accepts_explicit_year(api_client, auth_header, db_session):
    from datetime import date

    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-2024", source_id=source.id, title="A",
        storage_bucket="iurisync-test", storage_key="a.pdf", f_public=date(2024, 1, 15),
    )
    repository.insert_document(
        db_session, doc_id="doc-2026", source_id=source.id, title="B",
        storage_bucket="iurisync-test", storage_key="b.pdf", f_public=date(2026, 1, 15),
    )

    response = api_client.get("/documents/stats", params={"year": 2024}, headers=auth_header)

    assert response.status_code == 200
    body = response.json()
    assert body["year"] == 2024
    assert body["by_month"][0] == 1
    assert set(body["available_years"]) == {2024, 2026}


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

    monkeypatch.setattr(
        "api.routers.documents.presigned_url", lambda bucket, key, **kwargs: f"https://signed.example.com/{key}"
    )

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header)

    assert response.status_code == 200
    assert response.json()["url"] == "https://signed.example.com/Corte Constitucional/2024-02-01/Sentencia/T-065-24.pdf"


def test_preview_sets_response_content_disposition_from_the_document_title(api_client, auth_header, db_session, monkeypatch):
    """The browser's OWN pdf viewer chrome (not just our UI) reads its suggested
    download filename from the response's Content-Disposition header — since we
    hand it a presigned URL rather than proxying bytes through a Blob, that hint
    has to be baked into the presigned URL itself via ResponseContentDisposition."""
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-disposition",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-02-01/Sentencia/T-065-24.pdf",
        content_type="application/pdf",
    )

    captured = {}

    def _fake_presigned_url(bucket, key, **kwargs):
        captured["response_content_disposition"] = kwargs.get("response_content_disposition")
        return f"https://signed.example.com/{key}"

    monkeypatch.setattr("api.routers.documents.presigned_url", _fake_presigned_url)

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header)

    assert response.status_code == 200
    assert captured["response_content_disposition"] == 'inline; filename="T-065-24.pdf"'


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

    monkeypatch.setattr(
        "api.routers.documents.presigned_url", lambda bucket, key, **kwargs: f"https://signed.example.com/{key}"
    )

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("no debería encolar la tarea si ya hay un preview cacheado")

    monkeypatch.setattr("api.routers.documents.generate_document_preview_pdf", _fail_if_called)

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header)

    assert response.status_code == 200
    assert response.json()["url"] == "https://signed.example.com/Corte Constitucional/2026-06-30/Tutela/T-200-26.preview.pdf"


def test_preview_prefers_preset_preview_key_over_on_demand_conversion(api_client, auth_header, db_session, monkeypatch):
    """Regression test: for sources whose native format is PDF (e.g. JEP) but are stored
    as RTF for download, preview_storage_key is pre-set at scrape time to the untouched
    original PDF. That must win over the content_type-based on-demand conversion path —
    re-deriving a preview from the RTF would reconstruct it via a PDF-import round-trip,
    which can silently drop visible body text."""
    from core.db import repository

    repository.create_source_family(db_session, key="jep", display_name="JEP")
    source = repository.create_source(db_session, family_key="jep", name="JEP", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-preset-original",
        source_id=source.id,
        title="SAI-AOI-RC-PMA-320-2026",
        storage_bucket="iurisync-test",
        storage_key="JEP/2026-06-12/Resolución/SAI-AOI-RC-PMA-320-2026.rtf",
        content_type="application/rtf",
        preview_storage_key="JEP/2026-06-12/Resolución/SAI-AOI-RC-PMA-320-2026.preview.pdf",
    )

    monkeypatch.setattr(
        "api.routers.documents.presigned_url", lambda bucket, key, **kwargs: f"https://signed.example.com/{key}"
    )

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("no debería intentar una conversión bajo demanda si ya hay un preview_storage_key")

    monkeypatch.setattr("api.routers.documents.generate_document_preview_pdf", _fail_if_called)

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header)

    assert response.status_code == 200
    assert (
        response.json()["url"]
        == "https://signed.example.com/JEP/2026-06-12/Resolución/SAI-AOI-RC-PMA-320-2026.preview.pdf"
    )


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

    monkeypatch.setattr(
        "api.routers.documents.presigned_url", lambda bucket, key, **kwargs: f"https://signed.example.com/{key}"
    )

    class _FakeAsyncResult:
        def get(self, timeout=None):
            return "Corte Constitucional/2026-06-30/Tutela/T-202-26.preview.pdf"

    class _FakeTask:
        def delay(self, document_id):
            return _FakeAsyncResult()

    monkeypatch.setattr("api.routers.documents.generate_document_preview_pdf", _FakeTask())

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header)

    assert response.status_code == 200
    assert response.json()["url"] == "https://signed.example.com/Corte Constitucional/2026-06-30/Tutela/T-202-26.preview.pdf"


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
