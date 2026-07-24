def test_get_sources_requires_authentication(api_client):
    response = api_client.get("/sources")
    assert response.status_code == 401


def test_get_sources_rejects_invalid_token(api_client):
    response = api_client.get("/sources", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401


def test_create_and_list_source(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")

    create_response = api_client.post(
        "/sources",
        json={"family_key": "constitucional", "name": "Corte Constitucional", "family_params": {}},
        headers=auth_header,
    )
    assert create_response.status_code == 201
    source_id = create_response.json()["id"]

    list_response = api_client.get("/sources", headers=auth_header)
    assert list_response.status_code == 200
    assert [s["name"] for s in list_response.json()] == ["Corte Constitucional"]

    patch_response = api_client.patch(f"/sources/{source_id}", json={"active": False}, headers=auth_header)
    assert patch_response.status_code == 200
    assert patch_response.json()["active"] is False


def test_get_sources_filters_by_has_documents(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    with_docs = repository.create_source(
        db_session, family_key="constitucional", name="Corte Constitucional", family_params={}
    )
    repository.create_source(db_session, family_key="constitucional", name="Fuente Vacía", family_params={})
    repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=with_docs.id,
        title="T-100/24",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
    )

    response = api_client.get("/sources", params={"has_documents": "true"}, headers=auth_header)

    assert response.status_code == 200
    assert [s["name"] for s in response.json()] == ["Corte Constitucional"]


def test_get_source_families_reports_which_filter_by_publication_date(api_client, auth_header, db_session):
    """The 'Nuevo run' UI needs to tell the user, per source, whether the fini/ffin
    range will be matched against fecha de publicación or fecha de providencia —
    this is what it reads to decide."""
    from core.db import repository

    repository.create_source_family(db_session, key="jep", display_name="JEP")
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")

    response = api_client.get("/source-families", headers=auth_header)

    assert response.status_code == 200
    by_key = {family["key"]: family for family in response.json()}
    assert by_key["jep"]["filters_by_publication_date"] is True
    assert by_key["constitucional"]["filters_by_publication_date"] is False


def test_patch_unknown_source_returns_404(api_client, auth_header):
    response = api_client.patch("/sources/999999", json={"active": False}, headers=auth_header)
    assert response.status_code == 404


def test_create_source_with_unknown_family_key_returns_400(api_client, auth_header):
    response = api_client.post(
        "/sources",
        json={"family_key": "no-existe", "name": "Fuente X", "family_params": {}},
        headers=auth_header,
    )
    assert response.status_code == 400


def test_get_sources_respects_limit_and_offset(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    for name in ["Fuente A", "Fuente B", "Fuente C"]:
        repository.create_source(db_session, family_key="constitucional", name=name, family_params={})

    response = api_client.get("/sources?limit=2", headers=auth_header)
    assert response.status_code == 200
    assert len(response.json()) == 2

    response = api_client.get("/sources?limit=2&offset=2", headers=auth_header)
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_authenticated_request_updates_session_last_used_at(api_client, auth_header, db_session):
    from core.db import repository
    from core.security import hash_session_token

    raw_token = auth_header["Authorization"].removeprefix("Bearer ")
    before = repository.get_valid_session_by_token_hash(db_session, hash_session_token(raw_token))
    assert before.last_used_at is None

    response = api_client.get("/sources", headers=auth_header)
    assert response.status_code == 200

    after = repository.get_valid_session_by_token_hash(db_session, hash_session_token(raw_token))
    assert after.last_used_at is not None
