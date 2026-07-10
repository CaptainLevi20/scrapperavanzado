def test_get_sources_requires_api_key(api_client):
    response = api_client.get("/sources")
    assert response.status_code == 422  # missing required X-API-Key header


def test_get_sources_rejects_invalid_key(api_client):
    response = api_client.get("/sources", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_create_and_list_source(api_client, api_key_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")

    create_response = api_client.post(
        "/sources",
        json={"family_key": "constitucional", "name": "Corte Constitucional", "family_params": {}},
        headers=api_key_header,
    )
    assert create_response.status_code == 201
    source_id = create_response.json()["id"]

    list_response = api_client.get("/sources", headers=api_key_header)
    assert list_response.status_code == 200
    assert [s["name"] for s in list_response.json()] == ["Corte Constitucional"]

    patch_response = api_client.patch(f"/sources/{source_id}", json={"active": False}, headers=api_key_header)
    assert patch_response.status_code == 200
    assert patch_response.json()["active"] is False


def test_patch_unknown_source_returns_404(api_client, api_key_header):
    response = api_client.patch("/sources/999999", json={"active": False}, headers=api_key_header)
    assert response.status_code == 404


def test_authenticated_request_updates_api_key_last_used_at(api_client, api_key_header, db_session):
    from core.db import repository
    from core.security import hash_api_key

    raw_key = api_key_header["X-API-Key"]
    before = repository.get_active_api_key_by_hash(db_session, hash_api_key(raw_key))
    assert before.last_used_at is None

    response = api_client.get("/sources", headers=api_key_header)
    assert response.status_code == 200

    after = repository.get_active_api_key_by_hash(db_session, hash_api_key(raw_key))
    assert after.last_used_at is not None
