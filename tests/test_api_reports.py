from datetime import date


def test_post_report_creates_row_and_dispatches_task(api_client, auth_header, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "api.routers.reports.build_monthly_report.delay", lambda report_id: calls.append(report_id)
    )
    monkeypatch.setattr("api.routers.reports.date", type("_FixedDate", (date,), {"today": staticmethod(lambda: date(2026, 9, 17))}))

    response = api_client.post("/reports", json={"period": "2026-08-01"}, headers=auth_header)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["period"] == "2026-08-01"
    assert body["triggered_by"] == "manual"
    assert calls == [body["id"]]


def test_post_report_rejects_the_current_month(api_client, auth_header, monkeypatch):
    monkeypatch.setattr("api.routers.reports.build_monthly_report.delay", lambda *a, **k: None)
    monkeypatch.setattr("api.routers.reports.date", type("_FixedDate", (date,), {"today": staticmethod(lambda: date(2026, 9, 17))}))

    response = api_client.post("/reports", json={"period": "2026-09-01"}, headers=auth_header)

    assert response.status_code == 400


def test_post_report_rejects_a_future_month(api_client, auth_header, monkeypatch):
    monkeypatch.setattr("api.routers.reports.build_monthly_report.delay", lambda *a, **k: None)
    monkeypatch.setattr("api.routers.reports.date", type("_FixedDate", (date,), {"today": staticmethod(lambda: date(2026, 9, 17))}))

    response = api_client.post("/reports", json={"period": "2026-10-01"}, headers=auth_header)

    assert response.status_code == 400


def test_get_reports_lists_most_recent_first(api_client, auth_header, monkeypatch):
    monkeypatch.setattr("api.routers.reports.build_monthly_report.delay", lambda *a, **k: None)
    monkeypatch.setattr("api.routers.reports.date", type("_FixedDate", (date,), {"today": staticmethod(lambda: date(2026, 9, 17))}))

    first = api_client.post("/reports", json={"period": "2026-07-01"}, headers=auth_header).json()
    second = api_client.post("/reports", json={"period": "2026-08-01"}, headers=auth_header).json()

    response = api_client.get("/reports", headers=auth_header)

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [second["id"], first["id"]]


def test_get_report_download_returns_404_when_not_completed(api_client, auth_header, monkeypatch):
    monkeypatch.setattr("api.routers.reports.build_monthly_report.delay", lambda *a, **k: None)
    monkeypatch.setattr("api.routers.reports.date", type("_FixedDate", (date,), {"today": staticmethod(lambda: date(2026, 9, 17))}))

    created = api_client.post("/reports", json={"period": "2026-08-01"}, headers=auth_header).json()

    response = api_client.get(f"/reports/{created['id']}/download", headers=auth_header)

    assert response.status_code == 404


def test_get_report_download_returns_signed_url_when_completed(api_client, auth_header, db_session):
    from core.db import repository

    report = repository.create_monthly_report(db_session, period=date(2026, 8, 1), triggered_by="manual")
    repository.set_monthly_report_status(
        db_session, report.id, "completed", storage_key=f"reportes/2026-08_{report.id}.pdf", storage_bucket="iurisync-test"
    )

    response = api_client.get(f"/reports/{report.id}/download", headers=auth_header)

    assert response.status_code == 200
    assert "url" in response.json()


def test_reports_endpoints_require_authentication(api_client):
    assert api_client.post("/reports", json={"period": "2026-08-01"}).status_code == 401
    assert api_client.get("/reports").status_code == 401
    assert api_client.get("/reports/1/download").status_code == 401
