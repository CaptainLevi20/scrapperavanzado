from core.config import get_settings


def test_register_creates_user_and_returns_a_working_session(api_client, db_session):
    settings = get_settings()
    response = api_client.post(
        "/auth/register",
        json={"username": "ana", "password": "Password123", "invite_code": settings.registration_code},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "ana"
    assert len(body["token"]) > 20

    me_response = api_client.get("/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me_response.status_code == 200
    assert me_response.json() == {"username": "ana"}


def test_register_rejects_wrong_invite_code(api_client):
    response = api_client.post(
        "/auth/register",
        json={"username": "ana", "password": "Password123", "invite_code": "wrong-code"},
    )
    assert response.status_code == 401


def test_register_rejects_duplicate_username(api_client, db_session):
    settings = get_settings()
    payload = {"username": "ana", "password": "Password123", "invite_code": settings.registration_code}
    api_client.post("/auth/register", json=payload)

    response = api_client.post("/auth/register", json=payload)

    assert response.status_code == 409


def test_register_rejects_a_short_password(api_client):
    settings = get_settings()
    response = api_client.post(
        "/auth/register",
        json={"username": "ana", "password": "short", "invite_code": settings.registration_code},
    )
    assert response.status_code == 422


def test_login_with_correct_credentials_returns_a_session(api_client, db_session):
    settings = get_settings()
    api_client.post(
        "/auth/register",
        json={"username": "ana", "password": "Password123", "invite_code": settings.registration_code},
    )

    response = api_client.post("/auth/login", json={"username": "ana", "password": "Password123"})

    assert response.status_code == 200
    assert response.json()["username"] == "ana"


def test_login_rejects_wrong_password(api_client, db_session):
    settings = get_settings()
    api_client.post(
        "/auth/register",
        json={"username": "ana", "password": "Password123", "invite_code": settings.registration_code},
    )

    response = api_client.post("/auth/login", json={"username": "ana", "password": "wrong-password"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Usuario o contraseña incorrectos"


def test_login_rejects_unknown_username(api_client):
    response = api_client.post("/auth/login", json={"username": "ghost", "password": "Password123"})
    assert response.status_code == 401


def test_me_rejects_a_missing_or_invalid_token(api_client):
    response = api_client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_me_rejects_a_missing_authorization_header(api_client):
    response = api_client.get("/auth/me")
    assert response.status_code == 401


def test_logout_invalidates_the_session(api_client, db_session):
    settings = get_settings()
    register_response = api_client.post(
        "/auth/register",
        json={"username": "ana", "password": "Password123", "invite_code": settings.registration_code},
    )
    token = register_response.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    logout_response = api_client.post("/auth/logout", headers=headers)
    assert logout_response.status_code == 204

    me_response = api_client.get("/auth/me", headers=headers)
    assert me_response.status_code == 401


def test_change_password_updates_the_password(api_client, db_session):
    settings = get_settings()
    register_response = api_client.post(
        "/auth/register",
        json={"username": "ana", "password": "Password123", "invite_code": settings.registration_code},
    )
    token = register_response.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    change_response = api_client.post(
        "/auth/change-password",
        json={"current_password": "Password123", "new_password": "NewPassword456"},
        headers=headers,
    )
    assert change_response.status_code == 204

    login_response = api_client.post("/auth/login", json={"username": "ana", "password": "NewPassword456"})
    assert login_response.status_code == 200


def test_change_password_rejects_wrong_current_password(api_client, db_session):
    settings = get_settings()
    register_response = api_client.post(
        "/auth/register",
        json={"username": "ana", "password": "Password123", "invite_code": settings.registration_code},
    )
    token = register_response.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = api_client.post(
        "/auth/change-password",
        json={"current_password": "wrong", "new_password": "NewPassword456"},
        headers=headers,
    )
    assert response.status_code == 401
