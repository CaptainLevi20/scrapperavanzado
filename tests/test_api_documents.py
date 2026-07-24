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


def test_list_documents_filters_by_downloaded_at_range(api_client, auth_header, db_session):
    from datetime import datetime, timezone

    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session,
        doc_id="doc-ingresado-hoy",
        source_id=source.id,
        title="T-100/24",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
        downloaded_at=datetime(2026, 7, 23, 15, 0, 0, tzinfo=timezone.utc),
    )
    repository.insert_document(
        db_session,
        doc_id="doc-ingresado-ayer",
        source_id=source.id,
        title="T-200/24",
        storage_bucket="iurisync-test",
        storage_key="b.pdf",
        downloaded_at=datetime(2026, 7, 22, 23, 59, 0, tzinfo=timezone.utc),
    )
    repository.insert_document(
        db_session,
        doc_id="doc-ingresado-manana",
        source_id=source.id,
        title="T-300/24",
        storage_bucket="iurisync-test",
        storage_key="c.pdf",
        downloaded_at=datetime(2026, 7, 24, 0, 0, 1, tzinfo=timezone.utc),
    )

    response = api_client.get(
        "/documents",
        params={"downloaded_from": "2026-07-23", "downloaded_to": "2026-07-23"},
        headers=auth_header,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["doc_id"] == "doc-ingresado-hoy"
    assert not any(item["doc_id"] == "doc-ingresado-manana" for item in body["items"])


def test_list_documents_downloaded_at_range_is_inclusive_of_the_whole_end_day(api_client, auth_header, db_session):
    from datetime import datetime, timezone

    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session,
        doc_id="doc-fin-de-dia",
        source_id=source.id,
        title="T-300/24",
        storage_bucket="iurisync-test",
        storage_key="c.pdf",
        downloaded_at=datetime(2026, 7, 23, 23, 59, 59, tzinfo=timezone.utc),
    )
    repository.insert_document(
        db_session,
        doc_id="doc-justo-fuera-del-rango",
        source_id=source.id,
        title="T-400/24",
        storage_bucket="iurisync-test",
        storage_key="d.pdf",
        downloaded_at=datetime(2026, 7, 24, 0, 0, 0, tzinfo=timezone.utc),
    )

    response = api_client.get(
        "/documents",
        params={"downloaded_from": "2026-07-23", "downloaded_to": "2026-07-23"},
        headers=auth_header,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["doc_id"] == "doc-fin-de-dia"
    assert not any(item["doc_id"] == "doc-justo-fuera-del-rango" for item in body["items"])


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


def test_get_document_tipos_scoped_to_a_source(api_client, auth_header, db_session):
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

    response = api_client.get(f"/documents/tipos?source_id={source_a.id}", headers=auth_header)

    assert response.status_code == 200
    assert response.json() == ["Sentencia"]


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


def test_patch_document_title_updates_and_returns_document(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T065_24",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    response = api_client.patch(
        f"/documents/{document.id}/title", json={"title": "ST065_24 (corregido a mano)"}, headers=auth_header
    )

    assert response.status_code == 200
    assert response.json()["title"] == "ST065_24 (corregido a mano)"


def test_patch_document_title_strips_surrounding_whitespace(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T065_24",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    response = api_client.patch(
        f"/documents/{document.id}/title", json={"title": "  Título con espacios  "}, headers=auth_header
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Título con espacios"


def test_patch_document_title_rejects_blank_value(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T065_24",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    response = api_client.patch(f"/documents/{document.id}/title", json={"title": "   "}, headers=auth_header)

    assert response.status_code == 422


def test_patch_document_title_returns_404_when_missing(api_client, auth_header):
    response = api_client.patch("/documents/999999/title", json={"title": "Nuevo título"}, headers=auth_header)
    assert response.status_code == 404


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


def test_get_document_versions_lists_most_recently_superseded_first(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session, doc_id="doc-v", source_id=source.id, title="A. 1/26",
        storage_bucket="iurisync-test", storage_key="v1.rtf", file_size_bytes=100,
    )
    repository.archive_and_replace_document(
        db_session, document.id, storage_bucket="iurisync-test", storage_key="v2.rtf", file_size_bytes=200
    )
    repository.archive_and_replace_document(
        db_session, document.id, storage_bucket="iurisync-test", storage_key="v3.rtf", file_size_bytes=300
    )

    response = api_client.get(f"/documents/{document.id}/versions", headers=auth_header)

    assert response.status_code == 200
    body = response.json()
    assert [v["file_size_bytes"] for v in body] == [200, 100]


def test_get_document_versions_returns_empty_list_for_a_document_with_no_history(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session, doc_id="doc-no-versions", source_id=source.id, title="A. 2/26",
        storage_bucket="iurisync-test", storage_key="only.rtf", file_size_bytes=50,
    )

    response = api_client.get(f"/documents/{document.id}/versions", headers=auth_header)

    assert response.status_code == 200
    assert response.json() == []


def test_get_document_version_download_returns_404_for_a_version_of_another_document(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document_a = repository.insert_document(
        db_session, doc_id="doc-a", source_id=source.id, title="A", storage_bucket="iurisync-test",
        storage_key="a.rtf", file_size_bytes=10,
    )
    document_b = repository.insert_document(
        db_session, doc_id="doc-b", source_id=source.id, title="B", storage_bucket="iurisync-test",
        storage_key="b.rtf", file_size_bytes=10,
    )
    repository.archive_and_replace_document(
        db_session, document_b.id, storage_bucket="iurisync-test", storage_key="b-v2.rtf", file_size_bytes=20
    )
    [version_of_b] = repository.list_document_versions(db_session, document_b.id)

    response = api_client.get(f"/documents/{document_a.id}/versions/{version_of_b.id}/download", headers=auth_header)

    assert response.status_code == 404


def test_get_document_version_download_returns_signed_url(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session, doc_id="doc-download-version", source_id=source.id, title="A. 3/26",
        storage_bucket="iurisync-test", storage_key="v1.rtf", file_size_bytes=10,
    )
    repository.archive_and_replace_document(
        db_session, document.id, storage_bucket="iurisync-test", storage_key="v2.rtf", file_size_bytes=20
    )
    [version] = repository.list_document_versions(db_session, document.id)

    response = api_client.get(f"/documents/{document.id}/versions/{version.id}/download", headers=auth_header)

    assert response.status_code == 200
    assert "url" in response.json()
