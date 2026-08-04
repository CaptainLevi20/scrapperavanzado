from core.db import repository


def _samai_source(db_session, name):
    repository.create_source_family_if_missing(db_session, key="samai", display_name="SAMAI")
    return repository.create_source(db_session, family_key="samai", name=name, family_params={})


def test_list_pending_suggestions_returns_case_group_context(api_client, db_session, auth_header):
    tribunal = _samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _samai_source(db_session, "Consejo de Estado")
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, title="t1",
        radicado="25000234200020200000801", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id, title="t2",
        radicado="25000234200020200000802", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    repository._create_case_link_suggestion_if_missing(
        db_session, tribunal.id, "25000234200020200000801", consejo.id, "25000234200020200000802", 22
    )

    response = api_client.get("/case-link-suggestions", headers=auth_header)

    assert response.status_code == 200
    [suggestion] = response.json()
    assert suggestion["matched_digits"] == 22
    assert {suggestion["case_a"]["source_name"], suggestion["case_b"]["source_name"]} == {
        "Tribunal Administrativo de Antioquia", "Consejo de Estado",
    }
    assert suggestion["case_a"]["document_count"] == 1


def test_confirm_suggestion_returns_404_when_not_found(api_client, auth_header):
    response = api_client.post("/case-link-suggestions/999/confirm", headers=auth_header)
    assert response.status_code == 404


def test_confirm_then_get_case_link_shows_both_stages(api_client, db_session, auth_header):
    tribunal = _samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _samai_source(db_session, "Consejo de Estado")
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, title="t1",
        radicado="25000234200020200000801", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id, title="t2",
        radicado="25000234200020200000802", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    repository._create_case_link_suggestion_if_missing(
        db_session, tribunal.id, "25000234200020200000801", consejo.id, "25000234200020200000802", 22
    )
    [suggestion] = repository.list_pending_case_link_suggestions(db_session)

    confirm_response = api_client.post(f"/case-link-suggestions/{suggestion.id}/confirm", headers=auth_header)
    assert confirm_response.status_code == 200
    case_link_id = confirm_response.json()["id"]

    get_response = api_client.get(f"/case-links/{case_link_id}", headers=auth_header)
    assert get_response.status_code == 200
    stages = get_response.json()["stages"]
    assert len(stages) == 2
    assert {s["source_name"] for s in stages} == {"Tribunal Administrativo de Antioquia", "Consejo de Estado"}
    assert all(len(s["documents"]) == 1 for s in stages)


def test_dismiss_suggestion_removes_it_from_the_pending_list(api_client, db_session, auth_header):
    tribunal = _samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _samai_source(db_session, "Consejo de Estado")
    repository._create_case_link_suggestion_if_missing(
        db_session, tribunal.id, "25000234200020200000801", consejo.id, "25000234200020200000802", 22
    )
    [suggestion] = repository.list_pending_case_link_suggestions(db_session)

    response = api_client.post(f"/case-link-suggestions/{suggestion.id}/dismiss", headers=auth_header)

    assert response.status_code == 200
    assert api_client.get("/case-link-suggestions", headers=auth_header).json() == []


def test_create_manual_case_link(api_client, db_session, auth_header):
    tribunal = _samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _samai_source(db_session, "Consejo de Estado")
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, title="t1",
        radicado="11111111111111111111101", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id, title="t2",
        radicado="11111111111111111111102", storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    response = api_client.post(
        "/case-links",
        headers=auth_header,
        json={
            "source_id_a": tribunal.id, "radicado_a": "11111111111111111111101",
            "source_id_b": consejo.id, "radicado_b": "11111111111111111111102",
        },
    )

    assert response.status_code == 200
    assert len(response.json()["stages"]) == 2
