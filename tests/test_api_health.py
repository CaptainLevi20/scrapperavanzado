def test_health_check_does_not_require_api_key(api_client):
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
