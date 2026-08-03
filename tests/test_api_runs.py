def test_post_run_creates_run_and_dispatches_orchestration(api_client, auth_header, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "api.routers.runs.orchestrate_run.delay", lambda run_id, source_ids: calls.append((run_id, source_ids))
    )

    response = api_client.post("/runs", json={"source_ids": [1, 2]}, headers=auth_header)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["triggered_by"] == "manual"
    assert calls == [(body["id"], [1, 2])]


def test_get_run_returns_404_for_unknown_id(api_client, auth_header):
    response = api_client.get("/runs/999999", headers=auth_header)
    assert response.status_code == 404


def test_cancel_run_sets_cancel_requested(api_client, auth_header, monkeypatch, db_session):
    from core.db import repository

    monkeypatch.setattr("api.routers.runs.orchestrate_run.delay", lambda *a, **k: None)

    create_response = api_client.post("/runs", json={}, headers=auth_header)
    run_id = create_response.json()["id"]

    cancel_response = api_client.post(f"/runs/{run_id}/cancel", headers=auth_header)
    assert cancel_response.status_code == 200
    assert cancel_response.json()["cancel_requested"] is True


def test_get_runs_respects_limit_and_offset(api_client, auth_header, monkeypatch):
    monkeypatch.setattr("api.routers.runs.orchestrate_run.delay", lambda *a, **k: None)

    for _ in range(3):
        api_client.post("/runs", json={}, headers=auth_header)

    response = api_client.get("/runs?limit=2", headers=auth_header)
    assert response.status_code == 200
    assert len(response.json()) == 2

    response = api_client.get("/runs?limit=2&offset=2", headers=auth_header)
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_runs_rejects_out_of_range_limit_and_offset(api_client, auth_header):
    assert api_client.get("/runs?offset=-1", headers=auth_header).status_code == 422
    assert api_client.get("/runs?limit=0", headers=auth_header).status_code == 422
    assert api_client.get("/runs?limit=1000000", headers=auth_header).status_code == 422


def test_get_run_sources_reports_docs_updated(api_client, auth_header, monkeypatch, db_session):
    from core.db import repository

    monkeypatch.setattr("api.routers.runs.orchestrate_run.delay", lambda *a, **k: None)
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)
    repository.set_run_source_status(db_session, run_source.id, "completed", docs_new=1, docs_updated=3, docs_errors=0)

    response = api_client.get(f"/runs/{run.id}/sources", headers=auth_header)

    assert response.status_code == 200
    assert response.json()[0]["docs_updated"] == 3
    assert response.json()[0]["source_name"] == "Corte Constitucional"
