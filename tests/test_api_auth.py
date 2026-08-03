from core.config import get_settings
from core.db import repository


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
    assert me_response.json() == {"username": "ana", "is_admin": False}


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


def test_register_rejects_a_username_that_is_too_short(api_client):
    settings = get_settings()
    response = api_client.post(
        "/auth/register",
        json={"username": "an", "password": "Password123", "invite_code": settings.registration_code},
    )
    assert response.status_code == 422


def test_register_rejects_a_username_that_is_only_whitespace(api_client):
    settings = get_settings()
    response = api_client.post(
        "/auth/register",
        json={"username": "   ", "password": "Password123", "invite_code": settings.registration_code},
    )
    assert response.status_code == 422


def test_register_strips_surrounding_whitespace_from_the_username(api_client, db_session):
    settings = get_settings()
    response = api_client.post(
        "/auth/register",
        json={"username": "  ana  ", "password": "Password123", "invite_code": settings.registration_code},
    )
    assert response.status_code == 200
    assert response.json()["username"] == "ana"


def test_register_is_disabled_while_the_registration_code_is_still_the_public_default(api_client):
    """Regression test: 'changeme' ships in the source code, so it's not a
    secret anyone configured — it's public. Registration must refuse outright
    while it's still set to that, rather than accept it as a valid code."""
    settings = get_settings()
    settings.registration_code = "changeme"

    response = api_client.post(
        "/auth/register",
        json={"username": "ana", "password": "Password123", "invite_code": "changeme"},
    )

    assert response.status_code == 403


def test_register_is_rate_limited_per_client(api_client):
    """Regression test: nothing used to stop repeated /auth/register attempts,
    letting an attacker brute-force the invite code with no friction at all."""
    from api.routers.auth import REGISTER_RATE_LIMIT

    settings = get_settings()
    for i in range(REGISTER_RATE_LIMIT):
        response = api_client.post(
            "/auth/register",
            json={"username": f"user{i}", "password": "Password123", "invite_code": "wrong-code"},
        )
        assert response.status_code == 401  # invite code is wrong, but not yet rate-limited

    limited_response = api_client.post(
        "/auth/register",
        json={"username": "one-more", "password": "Password123", "invite_code": settings.registration_code},
    )
    assert limited_response.status_code == 429


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


def test_login_reports_is_admin_for_an_admin_user(api_client, db_session):
    from core.db import repository
    from core.security import hash_password

    repository.create_user(db_session, username="admin-user", password_hash=hash_password("Password123"), is_admin=True)

    response = api_client.post("/auth/login", json={"username": "admin-user", "password": "Password123"})

    assert response.status_code == 200
    assert response.json()["is_admin"] is True


def test_login_reports_is_admin_false_for_a_regular_user(api_client, db_session):
    from core.db import repository
    from core.security import hash_password

    repository.create_user(db_session, username="regular-user", password_hash=hash_password("Password123"))

    response = api_client.post("/auth/login", json={"username": "regular-user", "password": "Password123"})

    assert response.status_code == 200
    assert response.json()["is_admin"] is False


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


def test_deactivated_user_session_stops_working_immediately(api_client, db_session):
    """Regression test: `active` was only ever checked at login time — once a
    session existed, deactivating the user had zero effect on it. Their
    already-valid token must stop working on the very next request, not just
    at their next login attempt."""
    settings = get_settings()
    register_response = api_client.post(
        "/auth/register",
        json={"username": "ana", "password": "Password123", "invite_code": settings.registration_code},
    )
    token = register_response.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert api_client.get("/auth/me", headers=headers).status_code == 200

    user = repository.get_user_by_username(db_session, "ana")
    user.active = False
    db_session.commit()

    response = api_client.get("/auth/me", headers=headers)
    assert response.status_code == 401


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


def test_change_password_revokes_other_sessions_but_keeps_the_current_one(api_client, db_session):
    """Regression test: changing your password used to leave every other active
    session (e.g. one a stolen device still holds) working for up to 30 days —
    exactly the moment a stolen session should get kicked out. The session that
    made the change must survive; every other one for that user must not."""
    settings = get_settings()
    register_response = api_client.post(
        "/auth/register",
        json={"username": "ana", "password": "Password123", "invite_code": settings.registration_code},
    )
    token_a = register_response.json()["token"]

    login_response = api_client.post("/auth/login", json={"username": "ana", "password": "Password123"})
    token_b = login_response.json()["token"]
    assert token_a != token_b

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    assert api_client.get("/auth/me", headers=headers_a).status_code == 200
    assert api_client.get("/auth/me", headers=headers_b).status_code == 200

    change_response = api_client.post(
        "/auth/change-password",
        json={"current_password": "Password123", "new_password": "NewPassword456"},
        headers=headers_a,
    )
    assert change_response.status_code == 204

    assert api_client.get("/auth/me", headers=headers_a).status_code == 200
    assert api_client.get("/auth/me", headers=headers_b).status_code == 401


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
