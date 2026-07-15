# Autenticación de usuarios (registro + login) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar la API key compartida (`X-API-Key`, tabla `api_keys`) por un sistema real de usuario y contraseña, con registro propio protegido por un código de invitación, sesiones con expiración deslizante, y cambio de contraseña desde la app.

**Architecture:** Dos tablas nuevas (`users`, `sessions`) reemplazan `api_keys`. El login/registro emite un token de sesión aleatorio cuyo hash SHA-256 se guarda en `sessions` (nunca el token en claro — mismo principio que ya usaban las API keys); el cliente lo manda como `Authorization: Bearer <token>` en cada request. Las contraseñas se hashean con `bcrypt` (nunca SHA-256 puro). La migración se hace en 4 pasos backend que nunca dejan la app sin autenticación funcional a mitad de camino (agregar lo nuevo → exponer los endpoints → migrar los routers existentes → recién ahí borrar lo viejo), seguidos de 3 pasos de frontend.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + `bcrypt` + pytest (backend), React + TanStack Query + Vitest/Testing Library + MSW (frontend).

## Global Constraints

- Se reemplaza el mecanismo de API key **por completo** — no coexisten `X-API-Key` y `Authorization: Bearer` en el estado final.
- Contraseñas: hash con `bcrypt`, nunca SHA-256 puro. Mínimo 8 caracteres (`Field(min_length=8)`).
- Token de sesión: `secrets.token_urlsafe(32)`, hasheado con SHA-256 antes de guardar en `sessions.token_hash` (el token en claro nunca se persiste, solo se devuelve una vez al cliente).
- Expiración deslizante de sesión: 30 días desde la creación o el último uso; cada request válido la extiende.
- Header de autenticación: `Authorization: Bearer <token>` — reemplaza `X-API-Key` en todos los endpoints protegidos.
- Mensajes de error genéricos en login (`"Usuario o contraseña incorrectos"` para usuario inexistente Y contraseña incorrecta, sin distinguir cuál).
- Sin roles, sin panel de administración, sin recuperación de contraseña por correo, sin rate limiting, sin límite de sesiones concurrentes — todo esto está explícitamente fuera de alcance según el spec.
- `require_api_key` no debe seguir usándose en ningún router después de la Tarea 3; la Tarea 4 borra por completo el mecanismo viejo (tabla, modelo, funciones de repositorio, CLI).

---

### Task 1: Modelos, migración y repositorio de usuarios/sesiones (aditivo)

Este paso solo agrega tablas y funciones nuevas — no toca nada del mecanismo de API key existente, que sigue funcionando exactamente igual.

**Files:**
- Modify: `core/db/models.py` (agregar `User`, `UserSession` — clase `UserSession`, no `Session`, para no chocar con `sqlalchemy.orm.Session` ya importado como tipo en todo `repository.py`)
- Modify: `core/db/repository.py` (agregar funciones nuevas, no tocar las de `ApiKey`)
- Modify: `core/security.py` (agregar hashing de contraseñas y de tokens de sesión, no tocar `hash_api_key`)
- Modify: `requirements.txt` (agregar `bcrypt`)
- Create: `alembic/versions/<revision_id>_add_users_and_sessions.py`
- Test: `tests/test_security.py` (nuevo), `tests/test_repository.py` (agregar casos)

**Interfaces:**
- Produces: `User` (columnas: `id`, `username`, `password_hash`, `active`, `created_at`, `last_login_at`), `UserSession` (columnas: `id`, `user_id`, `token_hash`, `created_at`, `expires_at`, `last_used_at`); `hash_password(raw_password: str) -> str`, `verify_password(raw_password: str, password_hash: str) -> bool`, `hash_session_token(raw_token: str) -> str`; `repository.create_user(db, username, password_hash) -> User`, `repository.get_user_by_username(db, username) -> Optional[User]`, `repository.create_session(db, user_id, token_hash) -> UserSession`, `repository.get_valid_session_by_token_hash(db, token_hash) -> Optional[UserSession]`, `repository.touch_session(db, session_id) -> None`, `repository.delete_session(db, token_hash) -> None`, `repository.update_user_password(db, user_id, password_hash) -> None`, `repository.touch_user_last_login(db, user_id) -> None`.

- [ ] **Step 1: Instalar bcrypt y agregarlo a requirements.txt**

Run: `.venv\Scripts\pip install bcrypt`

En `requirements.txt`, agregar esta línea después de `httpx>=0.27.0`:

```
bcrypt>=4.0.0
```

- [ ] **Step 2: Escribir los tests de seguridad que fallan**

Crear `tests/test_security.py`:

```python
from core.security import hash_password, hash_session_token, verify_password


def test_hash_password_produces_a_verifiable_but_different_string():
    password_hash = hash_password("correct horse battery staple")

    assert password_hash != "correct horse battery staple"
    assert verify_password("correct horse battery staple", password_hash) is True


def test_verify_password_rejects_a_wrong_password():
    password_hash = hash_password("correct horse battery staple")

    assert verify_password("wrong password", password_hash) is False


def test_hash_password_salts_so_the_same_password_hashes_differently():
    first = hash_password("same-password")
    second = hash_password("same-password")

    assert first != second


def test_hash_session_token_is_deterministic():
    assert hash_session_token("abc") == hash_session_token("abc")
    assert hash_session_token("abc") != hash_session_token("xyz")
```

- [ ] **Step 3: Confirmar que fallan**

Run: `.venv\Scripts\pytest tests/test_security.py -v`
Expected: FAIL con `ImportError`/`AttributeError` — `hash_password`, `verify_password`, `hash_session_token` no existen todavía.

- [ ] **Step 4: Implementar el hashing en `core/security.py`**

Reemplazar el contenido completo del archivo por:

```python
from hashlib import sha256

import bcrypt


def hash_api_key(raw_key: str) -> str:
    return sha256(raw_key.encode("utf-8")).hexdigest()


def hash_password(raw_password: str) -> str:
    return bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(raw_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(raw_password.encode("utf-8"), password_hash.encode("utf-8"))


def hash_session_token(raw_token: str) -> str:
    return sha256(raw_token.encode("utf-8")).hexdigest()
```

(`hash_api_key` se mantiene tal cual por ahora — `require_api_key` todavía la usa. Se elimina recién en la Tarea 4.)

- [ ] **Step 5: Confirmar que los tests de seguridad pasan**

Run: `.venv\Scripts\pytest tests/test_security.py -v`
Expected: 4 passed.

- [ ] **Step 6: Agregar los modelos `User` y `UserSession`**

En `core/db/models.py`, agregar al final del archivo (después de la clase `ApiKey` existente):

```python
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    last_login_at = Column(DateTime(timezone=True), nullable=True)


class UserSession(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
```

(La clase se llama `UserSession`, no `Session` — `repository.py` ya importa `Session` de `sqlalchemy.orm` como anotación de tipo en todas las funciones; llamarla `Session` chocaría con ese nombre.)

- [ ] **Step 7: Escribir los tests de repositorio que fallan**

Agregar al final de `tests/test_repository.py`:

```python
def test_create_user_and_lookup_by_username(db_session):
    repository.create_user(db_session, username="ana", password_hash="hashed")

    found = repository.get_user_by_username(db_session, "ana")
    assert found is not None
    assert found.password_hash == "hashed"
    assert found.active is True
    assert repository.get_user_by_username(db_session, "missing") is None


def test_create_and_validate_session(db_session):
    user = repository.create_user(db_session, username="ana", password_hash="hashed")

    session = repository.create_session(db_session, user_id=user.id, token_hash="tokhash")

    found = repository.get_valid_session_by_token_hash(db_session, "tokhash")
    assert found is not None
    assert found.id == session.id
    assert repository.get_valid_session_by_token_hash(db_session, "missing") is None


def test_get_valid_session_by_token_hash_excludes_expired_sessions(db_session):
    from datetime import datetime, timedelta, timezone

    from core.db.models import UserSession

    user = repository.create_user(db_session, username="ana", password_hash="hashed")
    expired = UserSession(
        user_id=user.id,
        token_hash="expired-hash",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(expired)
    db_session.commit()

    assert repository.get_valid_session_by_token_hash(db_session, "expired-hash") is None


def test_touch_session_extends_expiration(db_session):
    user = repository.create_user(db_session, username="ana", password_hash="hashed")
    session = repository.create_session(db_session, user_id=user.id, token_hash="tokhash")
    original_expiry = session.expires_at

    repository.touch_session(db_session, session.id)

    refreshed = repository.get_valid_session_by_token_hash(db_session, "tokhash")
    assert refreshed.last_used_at is not None
    assert refreshed.expires_at > original_expiry


def test_delete_session_removes_it(db_session):
    user = repository.create_user(db_session, username="ana", password_hash="hashed")
    repository.create_session(db_session, user_id=user.id, token_hash="tokhash")

    repository.delete_session(db_session, "tokhash")

    assert repository.get_valid_session_by_token_hash(db_session, "tokhash") is None


def test_update_user_password_changes_the_hash(db_session):
    user = repository.create_user(db_session, username="ana", password_hash="old-hash")

    repository.update_user_password(db_session, user.id, "new-hash")

    refreshed = repository.get_user_by_username(db_session, "ana")
    assert refreshed.password_hash == "new-hash"


def test_touch_user_last_login_sets_timestamp(db_session):
    user = repository.create_user(db_session, username="ana", password_hash="hashed")
    assert user.last_login_at is None

    repository.touch_user_last_login(db_session, user.id)

    refreshed = repository.get_user_by_username(db_session, "ana")
    assert refreshed.last_login_at is not None
```

- [ ] **Step 8: Confirmar que fallan**

Run: `.venv\Scripts\pytest tests/test_repository.py -v`
Expected: los 7 tests nuevos FAIL con `AttributeError: module 'core.db.repository' has no attribute 'create_user'` (y equivalentes).

- [ ] **Step 9: Implementar las funciones de repositorio**

En `core/db/repository.py`, cambiar la línea de import de:

```python
from datetime import date, datetime, timezone
```

a:

```python
from datetime import date, datetime, timedelta, timezone
```

Y cambiar:

```python
from core.db.models import ApiKey, Document, Run, RunError, RunSource, Source, SourceFamily
```

a:

```python
from core.db.models import ApiKey, Document, Run, RunError, RunSource, Source, SourceFamily, User, UserSession
```

Agregar al final del archivo:

```python
SESSION_TTL = timedelta(days=30)


def create_user(db: Session, username: str, password_hash: str) -> User:
    user = User(username=username, password_hash=password_hash, active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    stmt = select(User).where(User.username == username)
    return db.scalars(stmt).first()


def create_session(db: Session, user_id: int, token_hash: str) -> UserSession:
    now = datetime.now(timezone.utc)
    session = UserSession(user_id=user_id, token_hash=token_hash, expires_at=now + SESSION_TTL)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_valid_session_by_token_hash(db: Session, token_hash: str) -> Optional[UserSession]:
    stmt = select(UserSession).where(
        UserSession.token_hash == token_hash,
        UserSession.expires_at > datetime.now(timezone.utc),
    )
    return db.scalars(stmt).first()


def touch_session(db: Session, session_id: int) -> None:
    session = db.get(UserSession, session_id)
    now = datetime.now(timezone.utc)
    session.last_used_at = now
    session.expires_at = now + SESSION_TTL
    db.commit()


def delete_session(db: Session, token_hash: str) -> None:
    stmt = select(UserSession).where(UserSession.token_hash == token_hash)
    session = db.scalars(stmt).first()
    if session is not None:
        db.delete(session)
        db.commit()


def update_user_password(db: Session, user_id: int, password_hash: str) -> None:
    user = db.get(User, user_id)
    user.password_hash = password_hash
    db.commit()


def touch_user_last_login(db: Session, user_id: int) -> None:
    user = db.get(User, user_id)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
```

- [ ] **Step 10: Confirmar que los tests de repositorio pasan**

Run: `.venv\Scripts\pytest tests/test_repository.py -v`
Expected: todos PASS, incluyendo los 7 nuevos.

- [ ] **Step 11: Crear y completar la migración de Alembic**

Run: `.venv\Scripts\alembic revision -m "add users and sessions"`

Esto crea un archivo en `alembic/versions/<hash>_add_users_and_sessions.py` con `down_revision` apuntando automáticamente a la migración actual (`1f83d3e98af8`, la de `review_status`). Reemplazar el cuerpo de `upgrade()`/`downgrade()` por:

```python
def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
    )
    op.create_table(
        'sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('sessions')
    op.drop_table('users')
```

- [ ] **Step 12: Aplicar la migración y verificar**

Run: `.venv\Scripts\alembic upgrade head`
Expected: sin errores.

Run: `docker compose exec postgres psql -U iurisync -d iurisync -c "\dt"`
Expected: aparecen `users` y `sessions` junto a las tablas existentes (incluyendo `api_keys`, que sigue ahí).

- [ ] **Step 13: Correr toda la suite de backend**

Run: `.venv\Scripts\pytest -v`
Expected: todo PASS salvo la falla preexistente no relacionada de `test_migrations.py` (problema de entorno con el subprocess de `alembic`, no de este cambio).

- [ ] **Step 14: Commit**

```bash
git add core/db/models.py core/db/repository.py core/security.py requirements.txt tests/test_security.py tests/test_repository.py alembic/versions/*_add_users_and_sessions.py
git commit -m "feat: add users/sessions tables and password/session hashing (additive)"
```

---

### Task 2: Endpoints de autenticación (`/auth/*`)

Expone login/registro/logout/cambio de contraseña/verificación de sesión. Los routers existentes (`sources`, `runs`, `documents`) siguen usando `require_api_key` sin cambios — esta tarea solo agrega, no migra nada todavía.

**Files:**
- Modify: `core/config.py` (agregar `registration_code`)
- Modify: `.env.example` (agregar `REGISTRATION_CODE`)
- Modify: `api/schemas.py` (agregar los schemas de auth)
- Modify: `api/deps.py` (agregar `require_session`, sin tocar `require_api_key`)
- Create: `api/routers/auth.py`
- Modify: `api/main.py` (registrar el router nuevo)
- Modify: `tests/conftest.py` (agregar fixture `auth_header`)
- Modify: `tests/test_config.py` (agregar assertion de `registration_code`)
- Test: `tests/test_api_auth.py` (nuevo)

**Interfaces:**
- Consumes: `repository.create_user`, `repository.get_user_by_username`, `repository.create_session`, `repository.get_valid_session_by_token_hash`, `repository.touch_session`, `repository.delete_session`, `repository.update_user_password`, `repository.touch_user_last_login` (Task 1); `hash_password`, `verify_password`, `hash_session_token` (Task 1).
- Produces: `require_session` (dependencia FastAPI, devuelve `User`); endpoints `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `POST /auth/change-password`, `GET /auth/me`; fixture de test `auth_header`.

- [ ] **Step 1: Agregar `registration_code` a la configuración**

En `core/config.py`, agregar esta línea dentro de la clase `Settings`, después de `cors_origins`:

```python
    registration_code: str = "changeme"
```

En `.env.example`, agregar al final:

```
REGISTRATION_CODE=changeme
```

En `tests/test_config.py`, agregar esta línea dentro de `test_settings_have_expected_defaults`, después de la línea de `s3_bucket`:

```python
    assert settings.registration_code == "changeme"
```

- [ ] **Step 2: Escribir los tests de `/auth/*` que fallan**

Crear `tests/test_api_auth.py`:

```python
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
```

- [ ] **Step 3: Confirmar que fallan**

Run: `.venv\Scripts\pytest tests/test_api_auth.py -v`
Expected: FAIL — `/auth/register`, `/auth/login`, etc. no existen todavía (404).

- [ ] **Step 4: Agregar los schemas de auth**

En `api/schemas.py`, agregar al final del archivo:

```python
class RegisterRequest(BaseModel):
    username: str
    password: str = Field(min_length=8)
    invite_code: str


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class AuthResponse(BaseModel):
    token: str
    username: str


class MeResponse(BaseModel):
    username: str
```

- [ ] **Step 5: Agregar `require_session` a `api/deps.py`**

Reemplazar el contenido completo del archivo por:

```python
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from core.db import repository
from core.db.models import User
from core.db.session import get_db
from core.security import hash_api_key, hash_session_token


def require_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    api_key = repository.get_active_api_key_by_hash(db, hash_api_key(x_api_key))
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key inválida")
    repository.touch_api_key_last_used(db, api_key.id)
    return api_key


def require_session(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida")
    token = authorization.removeprefix("Bearer ")
    session = repository.get_valid_session_by_token_hash(db, hash_session_token(token))
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida o expirada")
    repository.touch_session(db, session.id)
    return db.get(User, session.user_id)
```

`authorization` es `Optional[str] = Header(None)` (no `Header(...)`) a propósito: si fuera obligatorio, FastAPI respondería `422` cuando el header falta por completo, en vez del `401` que corresponde semánticamente a "no autenticado" — y que además es el único código que el frontend sabe interpretar como "la sesión no es válida, hay que volver a loguearse".

- [ ] **Step 6: Crear `api/routers/auth.py`**

```python
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from api.deps import get_db, require_session
from api.schemas import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    RegisterRequest,
)
from core.config import get_settings
from core.db import repository
from core.db.models import User
from core.security import hash_password, hash_session_token, verify_password

router = APIRouter(prefix="/auth")


def _issue_session(db: Session, user_id: int) -> str:
    raw_token = secrets.token_urlsafe(32)
    repository.create_session(db, user_id=user_id, token_hash=hash_session_token(raw_token))
    return raw_token


@router.post("/register", response_model=AuthResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    settings = get_settings()
    if payload.invite_code != settings.registration_code:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Código de invitación inválido")
    if repository.get_user_by_username(db, payload.username) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese nombre de usuario ya está en uso")

    user = repository.create_user(db, username=payload.username, password_hash=hash_password(payload.password))
    token = _issue_session(db, user.id)
    return {"token": token, "username": user.username}


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = repository.get_user_by_username(db, payload.username)
    if user is None or not user.active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario o contraseña incorrectos")

    repository.touch_user_last_login(db, user.id)
    token = _issue_session(db, user.id)
    return {"token": token, "username": user.username}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    _user: User = Depends(require_session),
):
    token = (authorization or "").removeprefix("Bearer ")
    repository.delete_session(db, hash_session_token(token))


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_session),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="La contraseña actual no es correcta")
    repository.update_user_password(db, user.id, hash_password(payload.new_password))


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(require_session)):
    return {"username": user.username}
```

(`logout` vuelve a leer `authorization` directamente además de depender de `require_session`: `require_session` valida y da `401` si no corresponde, pero solo devuelve el `User` — no alcanza para saber qué fila de `sessions` borrar. Releer el mismo header para calcular su hash y borrar esa sesión puntual es seguro porque, para cuando el cuerpo de la función corre, `require_session` ya garantizó que el header es válido.)

- [ ] **Step 7: Registrar el router en `api/main.py`**

Cambiar:

```python
from api.routers import documents, health, runs, sources
```

a:

```python
from api.routers import auth, documents, health, runs, sources
```

Y agregar, justo después de `app.include_router(health.router)`:

```python
app.include_router(auth.router)
```

- [ ] **Step 8: Agregar el fixture `auth_header` a `tests/conftest.py`**

Agregar al final del archivo:

```python
@pytest.fixture()
def auth_header(db_session):
    import secrets

    from core.db import repository
    from core.security import hash_password, hash_session_token

    user = repository.create_user(db_session, username="tester", password_hash=hash_password("Password123"))
    raw_token = secrets.token_urlsafe(32)
    repository.create_session(db_session, user_id=user.id, token_hash=hash_session_token(raw_token))
    return {"Authorization": f"Bearer {raw_token}"}
```

(Todavía no reemplaza a `api_key_header` — ese fixture sigue existiendo, los routers viejos lo siguen usando hasta la Tarea 3.)

- [ ] **Step 9: Confirmar que los tests pasan**

Run: `.venv\Scripts\pytest tests/test_api_auth.py tests/test_config.py -v`
Expected: todos PASS.

Run: `.venv\Scripts\pytest -v`
Expected: todo PASS salvo la falla preexistente no relacionada de `test_migrations.py`.

- [ ] **Step 10: Commit**

```bash
git add core/config.py .env.example api/schemas.py api/deps.py api/routers/auth.py api/main.py tests/conftest.py tests/test_config.py tests/test_api_auth.py
git commit -m "feat: add /auth/* endpoints (register, login, logout, change-password, me)"
```

---

### Task 3: Migrar los routers existentes a `require_session`

Los tres routers protegidos (`sources`, `runs`, `documents`) pasan a exigir sesión de usuario en vez de API key. A partir de este punto, la API completa funciona con el mecanismo nuevo — el viejo queda sin usar (se borra recién en la Tarea 4).

**Files:**
- Modify: `api/routers/sources.py`, `api/routers/runs.py`, `api/routers/documents.py`
- Modify: `tests/test_api_sources.py`, `tests/test_api_runs.py`, `tests/test_api_documents.py`

**Interfaces:**
- Consumes: `require_session` (Task 2), fixture `auth_header` (Task 2).

- [ ] **Step 1: Cambiar la dependencia de los 3 routers**

En `api/routers/sources.py`, cambiar:

```python
from api.deps import get_db, require_api_key
```

a:

```python
from api.deps import get_db, require_session
```

Y cambiar:

```python
router = APIRouter(dependencies=[Depends(require_api_key)])
```

a:

```python
router = APIRouter(dependencies=[Depends(require_session)])
```

Repetir el mismo cambio (mismas dos líneas, mismo patrón) en `api/routers/runs.py` y `api/routers/documents.py`.

- [ ] **Step 2: Renombrar el fixture usado en los tests de esos 3 routers**

En `tests/test_api_sources.py`, `tests/test_api_runs.py` y `tests/test_api_documents.py`, renombrar **todas** las apariciones del identificador `api_key_header` a `auth_header` — tanto en la firma de cada función de test que lo recibe como parámetro, como en cada `headers=api_key_header` dentro del cuerpo. Es un renombrado mecánico de un identificador (la forma del fixture no cambia: sigue siendo un dict con un único header de autenticación), así que no debe cambiar ninguna otra línea de estos archivos.

- [ ] **Step 3: Verificar que no queda ninguna referencia vieja**

Run: `grep -rn "api_key_header" tests/test_api_sources.py tests/test_api_runs.py tests/test_api_documents.py`
Expected: sin salida (ninguna coincidencia).

- [ ] **Step 4: Confirmar que los tests pasan con el fixture nuevo**

Run: `.venv\Scripts\pytest tests/test_api_sources.py tests/test_api_runs.py tests/test_api_documents.py -v`
Expected: todos PASS (mismos tests de antes, ahora autenticados vía sesión en vez de API key).

- [ ] **Step 5: Correr toda la suite**

Run: `.venv\Scripts\pytest -v`
Expected: todo PASS salvo la falla preexistente no relacionada de `test_migrations.py`.

- [ ] **Step 6: Commit**

```bash
git add api/routers/sources.py api/routers/runs.py api/routers/documents.py tests/test_api_sources.py tests/test_api_runs.py tests/test_api_documents.py
git commit -m "feat: migrate sources/runs/documents routers from API key to session auth"
```

---

### Task 4: Eliminar el mecanismo de API key

Con todo el backend ya funcionando sobre sesiones, se borra por completo lo que quedó sin usar: tabla, modelo, funciones de repositorio, CLI y su test, y el campo de configuración muerto.

**Files:**
- Modify: `core/db/models.py` (quitar `ApiKey`)
- Modify: `core/db/repository.py` (quitar las funciones de `ApiKey`)
- Modify: `core/security.py` (quitar `hash_api_key`)
- Modify: `api/deps.py` (quitar `require_api_key`)
- Modify: `core/config.py` (quitar `api_key_header`)
- Delete: `core/manage.py`, `tests/test_manage.py`
- Modify: `tests/test_repository.py` (quitar los 2 tests de `ApiKey`)
- Modify: `tests/conftest.py` (quitar el fixture `api_key_header`)
- Modify: `tests/test_config.py` (quitar la aserción de `api_key_header`)
- Modify: `tests/test_migrations.py` (actualizar `EXPECTED_TABLES`)
- Modify: `README.md` (quitar el paso de `create-api-key`)
- Create: `alembic/versions/<revision_id>_drop_api_keys.py`

**Interfaces:**
- Ninguna — esta tarea solo borra código que nada más consume después de la Tarea 3.

- [ ] **Step 1: Quitar `ApiKey` de `core/db/models.py`**

Borrar la clase `ApiKey` completa (las últimas líneas del archivo):

```python
class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    key_hash = Column(String, nullable=False, unique=True)
    active = Column(Boolean, nullable=False, default=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
```

- [ ] **Step 2: Quitar las funciones de `ApiKey` de `core/db/repository.py`**

Cambiar el import de:

```python
from core.db.models import ApiKey, Document, Run, RunError, RunSource, Source, SourceFamily, User, UserSession
```

a:

```python
from core.db.models import Document, Run, RunError, RunSource, Source, SourceFamily, User, UserSession
```

Borrar estas tres funciones (las últimas del archivo):

```python
def create_api_key(db: Session, name: str, key_hash: str) -> ApiKey:
    api_key = ApiKey(name=name, key_hash=key_hash, active=True)
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    return api_key


def get_active_api_key_by_hash(db: Session, key_hash: str) -> Optional[ApiKey]:
    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.active.is_(True))
    return db.scalars(stmt).first()


def touch_api_key_last_used(db: Session, api_key_id: int) -> None:
    api_key = db.get(ApiKey, api_key_id)
    api_key.last_used_at = datetime.now(timezone.utc)
    db.commit()
```

- [ ] **Step 3: Quitar `hash_api_key` de `core/security.py`**

Borrar la función:

```python
def hash_api_key(raw_key: str) -> str:
    return sha256(raw_key.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Quitar `require_api_key` de `api/deps.py`**

Reemplazar el contenido completo del archivo por:

```python
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from core.db import repository
from core.db.models import User
from core.db.session import get_db
from core.security import hash_session_token


def require_session(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida")
    token = authorization.removeprefix("Bearer ")
    session = repository.get_valid_session_by_token_hash(db, hash_session_token(token))
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión inválida o expirada")
    repository.touch_session(db, session.id)
    return db.get(User, session.user_id)
```

- [ ] **Step 5: Quitar `api_key_header` de `core/config.py`**

Borrar la línea:

```python
    api_key_header: str = "X-API-Key"
```

- [ ] **Step 6: Borrar el CLI de API keys y su test**

```bash
rm core/manage.py tests/test_manage.py
```

- [ ] **Step 7: Actualizar los tests que referenciaban lo borrado**

En `tests/test_repository.py`, borrar estos dos tests:

```python
def test_api_key_create_and_lookup_by_hash(db_session):
    repository.create_api_key(db_session, name="tests", key_hash="hash123")
    found = repository.get_active_api_key_by_hash(db_session, "hash123")
    assert found is not None
    assert found.name == "tests"
    assert repository.get_active_api_key_by_hash(db_session, "missing") is None


def test_touch_api_key_last_used_sets_timestamp(db_session):
    api_key = repository.create_api_key(db_session, name="tests", key_hash="hash456")
    assert api_key.last_used_at is None

    repository.touch_api_key_last_used(db_session, api_key.id)

    refreshed = repository.get_active_api_key_by_hash(db_session, "hash456")
    assert refreshed.last_used_at is not None
```

En `tests/conftest.py`, borrar el fixture:

```python
@pytest.fixture()
def api_key_header(db_session):
    from core.db import repository
    from core.security import hash_api_key

    raw_key = "test-key-12345"
    repository.create_api_key(db_session, name="tests", key_hash=hash_api_key(raw_key))
    return {"X-API-Key": raw_key}
```

En `tests/test_config.py`, borrar la línea:

```python
    assert settings.api_key_header == "X-API-Key"
```

En `tests/test_migrations.py`, cambiar:

```python
EXPECTED_TABLES = {
    "source_families",
    "sources",
    "runs",
    "run_sources",
    "run_errors",
    "documents",
    "api_keys",
}
```

a:

```python
EXPECTED_TABLES = {
    "source_families",
    "sources",
    "runs",
    "run_sources",
    "run_errors",
    "documents",
    "users",
    "sessions",
}
```

- [ ] **Step 8: Confirmar que la suite pasa (menos la falla preexistente)**

Run: `.venv\Scripts\pytest -v`
Expected: todo PASS salvo `test_migrations.py::test_alembic_upgrade_head_creates_all_tables` (falla preexistente no relacionada, confirmada desde antes de este plan — el `EXPECTED_TABLES` ya quedó correcto para cuando se arregle el problema de entorno).

- [ ] **Step 9: Crear la migración que borra `api_keys`**

Run: `.venv\Scripts\alembic revision -m "drop api keys"`

Completar el archivo generado:

```python
def upgrade() -> None:
    """Upgrade schema."""
    op.drop_table('api_keys')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        'api_keys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('key_hash', sa.String(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_hash'),
    )
```

- [ ] **Step 10: Aplicar la migración y verificar**

Run: `.venv\Scripts\alembic upgrade head`
Expected: sin errores.

Run: `docker compose exec postgres psql -U iurisync -d iurisync -c "\dt"`
Expected: `api_keys` ya no aparece; `users`/`sessions` siguen ahí.

- [ ] **Step 11: Actualizar el paso de setup en `README.md`**

Cambiar la línea:

```
7. `.venv\Scripts\python -m core.manage create-api-key --name "mi-equipo"` (guarda la key impresa)
```

a:

```
7. Registra tu primer usuario desde el frontend (`/register`) con el código de invitación configurado en `REGISTRATION_CODE`, o directamente vía `POST /auth/register`.
```

- [ ] **Step 12: Commit**

```bash
git add core/db/models.py core/db/repository.py core/security.py api/deps.py core/config.py tests/test_repository.py tests/conftest.py tests/test_config.py tests/test_migrations.py README.md alembic/versions/*_drop_api_keys.py
git rm core/manage.py tests/test_manage.py
git commit -m "feat: remove the retired API key mechanism (table, model, CLI, config)"
```

---

### Task 5: Frontend — cliente HTTP y `AuthContext`

Base de plomería del frontend: el header de autenticación, el módulo de API de auth, y el contexto que sabe si hay una sesión válida.

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/documents.ts` (usa `getStoredApiKey` directamente en `downloadDocumentFile`)
- Create: `frontend/src/api/auth.ts`
- Modify: `frontend/src/auth/AuthContext.tsx`
- Modify: `frontend/src/auth/ProtectedRoute.tsx`
- Test: `frontend/src/api/client.test.ts`, `frontend/src/auth/AuthContext.test.tsx`

**Interfaces:**
- Produces: `getStoredToken()`, `setStoredToken(token)`, `clearStoredToken()` (reemplazan `getStoredApiKey`/`setStoredApiKey`/`clearStoredApiKey`); `login(username, password)`, `register(username, password, invite_code)`, `logoutRequest()`, `fetchMe()`, `changePassword(current, new)` en `api/auth.ts`; `useAuth()` devuelve `{ username, token, isLoading, login, logout }`.

- [ ] **Step 1: Escribir los tests de `client.ts` que fallan**

Reemplazar el contenido completo de `frontend/src/api/client.test.ts` por:

```typescript
import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import {
  ApiError,
  apiFetch,
  buildQuery,
  clearStoredToken,
  getStoredToken,
  registerUnauthorizedHandler,
  setStoredToken,
} from "./client";

const BASE_URL = "http://localhost:8000";

describe("apiFetch", () => {
  beforeEach(() => {
    clearStoredToken();
    registerUnauthorizedHandler(() => {});
  });

  it("sends the stored session token as a Bearer Authorization header", async () => {
    setStoredToken("test-token");
    let receivedHeader: string | null = null;
    server.use(
      http.get(`${BASE_URL}/source-families`, ({ request }) => {
        receivedHeader = request.headers.get("authorization");
        return HttpResponse.json([]);
      })
    );

    await apiFetch("/source-families");

    expect(receivedHeader).toBe("Bearer test-token");
  });

  it("throws ApiError with the backend's detail message on a 4xx response", async () => {
    server.use(
      http.post(`${BASE_URL}/sources`, () =>
        HttpResponse.json({ detail: "Familia técnica desconocida: x" }, { status: 400 })
      )
    );

    await expect(apiFetch("/sources", { method: "POST", body: "{}" })).rejects.toMatchObject({
      status: 400,
      message: "Familia técnica desconocida: x",
    });
  });

  it("clears the stored token and notifies the unauthorized handler on a 401 when a token was sent", async () => {
    setStoredToken("bad-token");
    let notified = false;
    registerUnauthorizedHandler(() => {
      notified = true;
    });
    server.use(http.get(`${BASE_URL}/source-families`, () => new HttpResponse(null, { status: 401 })));

    await expect(apiFetch("/source-families")).rejects.toBeInstanceOf(ApiError);
    expect(getStoredToken()).toBeNull();
    expect(notified).toBe(true);
  });

  it("does not clear session state on a 401 when no token was sent (e.g. a failed login attempt)", async () => {
    let notified = false;
    registerUnauthorizedHandler(() => {
      notified = true;
    });
    server.use(
      http.post(`${BASE_URL}/auth/login`, () =>
        HttpResponse.json({ detail: "Usuario o contraseña incorrectos" }, { status: 401 })
      )
    );

    await expect(apiFetch("/auth/login", { method: "POST", body: "{}" })).rejects.toMatchObject({
      status: 401,
      message: "Usuario o contraseña incorrectos",
    });
    expect(notified).toBe(false);
  });
});

describe("buildQuery", () => {
  it("builds a query string skipping undefined values", () => {
    expect(buildQuery({ a: 1, b: undefined, c: "x" })).toBe("?a=1&c=x");
  });

  it("returns an empty string when there are no defined params", () => {
    expect(buildQuery({ a: undefined })).toBe("");
  });
});
```

- [ ] **Step 2: Confirmar que fallan**

Run: `cd frontend && npm test -- --run src/api/client.test.ts`
Expected: FAIL — `getStoredToken`/`setStoredToken`/`clearStoredToken` no existen todavía, y el header sigue siendo `X-API-Key`.

- [ ] **Step 3: Reescribir `client.ts`**

Reemplazar el contenido completo de `frontend/src/api/client.ts` por:

```typescript
const SESSION_TOKEN_STORAGE_KEY = "iurisync_session_token";

export function getStoredToken(): string | null {
  return localStorage.getItem(SESSION_TOKEN_STORAGE_KEY);
}

export function setStoredToken(token: string): void {
  localStorage.setItem(SESSION_TOKEN_STORAGE_KEY, token);
}

export function clearStoredToken(): void {
  localStorage.removeItem(SESSION_TOKEN_STORAGE_KEY);
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

let unauthorizedHandler: (() => void) | null = null;

export function registerUnauthorizedHandler(handler: () => void): void {
  unauthorizedHandler = handler;
}

export function buildQuery(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (response.status === 401 && token) {
    // Había una sesión guardada y el backend la rechazó (expiró o fue
    // revocada en otro lugar) — se limpia y se notifica para volver al
    // login. Un 401 de un intento de login/registro (sin token todavía)
    // no entra aquí: cae al manejo genérico de abajo, que preserva el
    // detail real que mandó el backend (ej. "Usuario o contraseña
    // incorrectos").
    clearStoredToken();
    unauthorizedHandler?.();
    throw new ApiError(401, "Sesión inválida o expirada");
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // el cuerpo no era JSON; se mantiene el texto de estado HTTP
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
```

- [ ] **Step 4: Actualizar `documents.ts` para usar el token en vez de la API key**

En `frontend/src/api/documents.ts`, cambiar el import de:

```typescript
import { apiFetch, buildQuery, getStoredApiKey } from "./client";
```

a:

```typescript
import { apiFetch, buildQuery, getStoredToken } from "./client";
```

Y dentro de `downloadDocumentFile`, cambiar:

```typescript
  const apiKey = getStoredApiKey();
  const headers = new Headers();
  if (apiKey) headers.set("X-API-Key", apiKey);
```

a:

```typescript
  const token = getStoredToken();
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);
```

- [ ] **Step 5: Confirmar que los tests de `client.ts` pasan**

Run: `cd frontend && npm test -- --run src/api/client.test.ts`
Expected: 4 passed.

- [ ] **Step 6: Crear `frontend/src/api/auth.ts`**

```typescript
import { apiFetch } from "./client";

export interface AuthResponse {
  token: string;
  username: string;
}

export function login(username: string, password: string): Promise<AuthResponse> {
  return apiFetch<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function register(username: string, password: string, invite_code: string): Promise<AuthResponse> {
  return apiFetch<AuthResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password, invite_code }),
  });
}

export function logoutRequest(): Promise<void> {
  return apiFetch<void>("/auth/logout", { method: "POST" });
}

export function fetchMe(): Promise<{ username: string }> {
  return apiFetch<{ username: string }>("/auth/me");
}

export function changePassword(current_password: string, new_password: string): Promise<void> {
  return apiFetch<void>("/auth/change-password", {
    method: "POST",
    body: JSON.stringify({ current_password, new_password }),
  });
}
```

- [ ] **Step 7: Escribir los tests de `AuthContext` que fallan**

Reemplazar el contenido completo de `frontend/src/auth/AuthContext.test.tsx` por:

```tsx
import { describe, expect, it, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { clearStoredToken, getStoredToken, setStoredToken } from "../api/client";
import { AuthProvider, useAuth } from "./AuthContext";

const BASE_URL = "http://localhost:8000";

function Probe() {
  const { username, token, isLoading, login, logout } = useAuth();
  if (isLoading) return <span data-testid="loading">loading</span>;
  return (
    <div>
      <span data-testid="token">{token ?? "none"}</span>
      <span data-testid="username">{username ?? "none"}</span>
      <button onClick={() => login("new-token", "ana")}>login</button>
      <button onClick={() => logout()}>logout</button>
    </div>
  );
}

describe("AuthContext", () => {
  beforeEach(() => clearStoredToken());

  it("starts with no session when localStorage is empty", async () => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    expect(await screen.findByTestId("token")).toHaveTextContent("none");
  });

  it("validates a stored token against /auth/me on mount", async () => {
    setStoredToken("existing-token");
    server.use(http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana" })));

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    expect(await screen.findByTestId("username")).toHaveTextContent("ana");
    expect(screen.getByTestId("token")).toHaveTextContent("existing-token");
  });

  it("clears a stored token that /auth/me rejects", async () => {
    setStoredToken("stale-token");
    server.use(http.get(`${BASE_URL}/auth/me`, () => new HttpResponse(null, { status: 401 })));

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    expect(await screen.findByTestId("token")).toHaveTextContent("none");
    expect(getStoredToken()).toBeNull();
  });

  it("login stores the token/username and updates state", async () => {
    const user = userEvent.setup();
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await screen.findByTestId("token");

    await user.click(screen.getByText("login"));

    expect(screen.getByTestId("token")).toHaveTextContent("new-token");
    expect(screen.getByTestId("username")).toHaveTextContent("ana");
    expect(getStoredToken()).toBe("new-token");
  });

  it("logout calls the backend, then clears the token and updates state", async () => {
    const user = userEvent.setup();
    setStoredToken("existing-token");
    server.use(
      http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana" })),
      http.post(`${BASE_URL}/auth/logout`, () => new HttpResponse(null, { status: 204 }))
    );
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await screen.findByTestId("username");

    await user.click(screen.getByText("logout"));

    await waitFor(() => expect(screen.getByTestId("token")).toHaveTextContent("none"));
    expect(getStoredToken()).toBeNull();
  });
});
```

- [ ] **Step 8: Confirmar que fallan**

Run: `cd frontend && npm test -- --run src/auth/AuthContext.test.tsx`
Expected: FAIL — `AuthContext` todavía expone `apiKey`, no `{ username, token, isLoading }`.

- [ ] **Step 9: Reescribir `AuthContext.tsx`**

Reemplazar el contenido completo de `frontend/src/auth/AuthContext.tsx` por:

```tsx
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { fetchMe, logoutRequest } from "../api/auth";
import { clearStoredToken, getStoredToken, registerUnauthorizedHandler, setStoredToken } from "../api/client";

interface AuthContextValue {
  username: string | null;
  token: string | null;
  isLoading: boolean;
  login: (token: string, username: string) => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => getStoredToken());
  const [username, setUsername] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(() => getStoredToken() !== null);

  useEffect(() => {
    registerUnauthorizedHandler(() => {
      setToken(null);
      setUsername(null);
    });
  }, []);

  useEffect(() => {
    const storedToken = getStoredToken();
    if (!storedToken) {
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    fetchMe()
      .then((me) => {
        if (!cancelled) setUsername(me.username);
      })
      .catch(() => {
        if (!cancelled) {
          clearStoredToken();
          setToken(null);
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function login(newToken: string, newUsername: string) {
    setStoredToken(newToken);
    setToken(newToken);
    setUsername(newUsername);
  }

  async function logout() {
    try {
      await logoutRequest();
    } catch {
      // best-effort: la sesión local se limpia igual aunque la llamada falle
    }
    clearStoredToken();
    setToken(null);
    setUsername(null);
  }

  return (
    <AuthContext.Provider value={{ username, token, isLoading, login, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth debe usarse dentro de AuthProvider");
  return context;
}
```

- [ ] **Step 10: Actualizar `ProtectedRoute.tsx`**

Reemplazar el contenido completo de `frontend/src/auth/ProtectedRoute.tsx` por:

```tsx
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./AuthContext";

export function ProtectedRoute() {
  const { token, isLoading } = useAuth();
  if (isLoading) return null;
  if (!token) return <Navigate to="/login" replace />;
  return <Outlet />;
}
```

- [ ] **Step 11: Confirmar que los tests de `AuthContext` pasan**

Run: `cd frontend && npm test -- --run src/auth/AuthContext.test.tsx`
Expected: 5 passed.

- [ ] **Step 12: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/api/client.test.ts frontend/src/api/documents.ts frontend/src/api/auth.ts frontend/src/auth/AuthContext.tsx frontend/src/auth/AuthContext.test.tsx frontend/src/auth/ProtectedRoute.tsx
git commit -m "feat: switch frontend API client and AuthContext to session tokens"
```

(`LoginPage.tsx`/`LoginPage.test.tsx` quedan rotos después de este commit — todavía usan `getStoredApiKey`. Se arreglan en la Tarea 6, que es la siguiente. No correr `npm run build` recién en este punto; el chequeo de tipos completo se hace al final de la Tarea 6.)

---

### Task 6: Frontend — `LoginPage`, `RegisterPage` y ruteo

**Files:**
- Modify: `frontend/src/pages/LoginPage.tsx`
- Create: `frontend/src/pages/RegisterPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/pages/LoginPage.test.tsx`
- Test: `frontend/src/pages/RegisterPage.test.tsx` (nuevo)

**Interfaces:**
- Consumes: `login`, `register` de `api/auth.ts` (Task 5); `useAuth()` (Task 5).

- [ ] **Step 1: Escribir los tests de `LoginPage` que fallan**

Reemplazar el contenido completo de `frontend/src/pages/LoginPage.test.tsx` por:

```tsx
import { describe, expect, it, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { clearStoredToken, getStoredToken } from "../api/client";
import { AuthProvider } from "../auth/AuthContext";
import { LoginPage } from "./LoginPage";

const BASE_URL = "http://localhost:8000";

function renderLoginPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("LoginPage", () => {
  beforeEach(() => clearStoredToken());

  it("logs in with valid credentials and stores the returned session", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`${BASE_URL}/auth/login`, () => HttpResponse.json({ token: "new-token", username: "ana" }))
    );
    renderLoginPage();

    await user.type(screen.getByPlaceholderText("Usuario"), "ana");
    await user.type(screen.getByPlaceholderText("Contraseña"), "Password123");
    await user.click(screen.getByRole("button", { name: /entrar/i }));

    expect(await screen.findByRole("button", { name: /entrar/i })).toBeEnabled();
    expect(getStoredToken()).toBe("new-token");
  });

  it("shows an error and does not store a session on invalid credentials", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`${BASE_URL}/auth/login`, () =>
        HttpResponse.json({ detail: "Usuario o contraseña incorrectos" }, { status: 401 })
      )
    );
    renderLoginPage();

    await user.type(screen.getByPlaceholderText("Usuario"), "ana");
    await user.type(screen.getByPlaceholderText("Contraseña"), "wrong-password");
    await user.click(screen.getByRole("button", { name: /entrar/i }));

    expect(await screen.findByText("Usuario o contraseña incorrectos")).toBeInTheDocument();
    expect(getStoredToken()).toBeNull();
  });
});
```

- [ ] **Step 2: Confirmar que fallan**

Run: `cd frontend && npm test -- --run src/pages/LoginPage.test.tsx`
Expected: FAIL — `LoginPage` todavía tiene un solo campo ("API key"), no "Usuario"/"Contraseña".

- [ ] **Step 3: Reescribir `LoginPage.tsx`**

Reemplazar el contenido completo por:

```tsx
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { login } from "../api/auth";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { login: setSession } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const { token, username: loggedInUsername } = await login(username, password);
      setSession(token, loggedInUsername);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Usuario o contraseña incorrectos");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-tinta px-4 text-papel">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage:
            "repeating-linear-gradient(0deg, transparent, transparent 27px, currentColor 28px), repeating-linear-gradient(90deg, transparent, transparent 27px, currentColor 28px)",
        }}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-1/3 left-1/2 h-[36rem] w-[36rem] -translate-x-1/2 rounded-full bg-sello/10 blur-3xl"
      />

      <form
        onSubmit={handleSubmit}
        className="relative w-full max-w-sm space-y-6 rounded-xl border border-white/10 bg-tinta-2/80 p-8 shadow-2xl backdrop-blur"
      >
        <div className="space-y-1 text-center">
          <p className="text-[0.6875rem] tracking-[0.24em] text-papel/50 uppercase">Sala de vigilancia jurídica</p>
          <h1 className="font-display text-3xl font-semibold tracking-tight">IURISYNC</h1>
        </div>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <label htmlFor="login-username" className="text-xs font-medium text-papel/70">
              Usuario
            </label>
            <input
              id="login-username"
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="Usuario"
              required
              className="w-full rounded-md border border-white/15 bg-tinta px-3 py-2.5 text-sm text-papel placeholder:text-papel/30 outline-none focus-visible:border-sello focus-visible:ring-[3px] focus-visible:ring-sello/30"
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="login-password" className="text-xs font-medium text-papel/70">
              Contraseña
            </label>
            <input
              id="login-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Contraseña"
              required
              className="w-full rounded-md border border-white/15 bg-tinta px-3 py-2.5 text-sm text-papel placeholder:text-papel/30 outline-none focus-visible:border-sello focus-visible:ring-[3px] focus-visible:ring-sello/30"
            />
          </div>
        </div>

        {error && (
          <p className="rounded-md border border-rojo/40 bg-rojo/10 px-3 py-2 text-sm text-rojo-bg">{error}</p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-sello px-3 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-sello-ink disabled:opacity-60"
        >
          {submitting ? "Verificando…" : "Entrar"}
        </button>

        <p className="text-center text-xs text-papel/50">
          ¿No tienes cuenta?{" "}
          <Link to="/register" className="font-medium text-sello hover:underline">
            Regístrate
          </Link>
        </p>
      </form>
    </div>
  );
}
```

- [ ] **Step 4: Confirmar que los tests de `LoginPage` pasan**

Run: `cd frontend && npm test -- --run src/pages/LoginPage.test.tsx`
Expected: 2 passed.

- [ ] **Step 5: Escribir los tests de `RegisterPage` que fallan**

Crear `frontend/src/pages/RegisterPage.test.tsx`:

```tsx
import { describe, expect, it, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { clearStoredToken, getStoredToken } from "../api/client";
import { AuthProvider } from "../auth/AuthContext";
import { RegisterPage } from "./RegisterPage";

const BASE_URL = "http://localhost:8000";

function renderRegisterPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <RegisterPage />
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("RegisterPage", () => {
  beforeEach(() => clearStoredToken());

  it("registers and logs in automatically on success", async () => {
    const user = userEvent.setup();
    let sentBody: unknown = null;
    server.use(
      http.post(`${BASE_URL}/auth/register`, async ({ request }) => {
        sentBody = await request.json();
        return HttpResponse.json({ token: "new-token", username: "ana" });
      })
    );
    renderRegisterPage();

    await user.type(screen.getByPlaceholderText("Usuario"), "ana");
    await user.type(screen.getByPlaceholderText("Mínimo 8 caracteres"), "Password123");
    await user.type(screen.getByPlaceholderText("Repite la contraseña"), "Password123");
    await user.type(screen.getByPlaceholderText("Código de invitación"), "equipo-2026");
    await user.click(screen.getByRole("button", { name: /crear cuenta/i }));

    expect(await screen.findByRole("button", { name: /crear cuenta/i })).toBeEnabled();
    expect(getStoredToken()).toBe("new-token");
    expect(sentBody).toEqual({ username: "ana", password: "Password123", invite_code: "equipo-2026" });
  });

  it("shows an error when the passwords don't match, without calling the API", async () => {
    const user = userEvent.setup();
    let called = false;
    server.use(
      http.post(`${BASE_URL}/auth/register`, () => {
        called = true;
        return HttpResponse.json({ token: "x", username: "ana" });
      })
    );
    renderRegisterPage();

    await user.type(screen.getByPlaceholderText("Usuario"), "ana");
    await user.type(screen.getByPlaceholderText("Mínimo 8 caracteres"), "Password123");
    await user.type(screen.getByPlaceholderText("Repite la contraseña"), "Different456");
    await user.type(screen.getByPlaceholderText("Código de invitación"), "equipo-2026");
    await user.click(screen.getByRole("button", { name: /crear cuenta/i }));

    expect(await screen.findByText("Las contraseñas no coinciden")).toBeInTheDocument();
    expect(called).toBe(false);
  });

  it("shows the backend's error on an invalid invite code", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`${BASE_URL}/auth/register`, () =>
        HttpResponse.json({ detail: "Código de invitación inválido" }, { status: 401 })
      )
    );
    renderRegisterPage();

    await user.type(screen.getByPlaceholderText("Usuario"), "ana");
    await user.type(screen.getByPlaceholderText("Mínimo 8 caracteres"), "Password123");
    await user.type(screen.getByPlaceholderText("Repite la contraseña"), "Password123");
    await user.type(screen.getByPlaceholderText("Código de invitación"), "wrong-code");
    await user.click(screen.getByRole("button", { name: /crear cuenta/i }));

    expect(await screen.findByText("Código de invitación inválido")).toBeInTheDocument();
    expect(getStoredToken()).toBeNull();
  });
});
```

- [ ] **Step 6: Confirmar que fallan**

Run: `cd frontend && npm test -- --run src/pages/RegisterPage.test.tsx`
Expected: FAIL — el módulo `./RegisterPage` no existe todavía.

- [ ] **Step 7: Crear `RegisterPage.tsx`**

```tsx
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { register } from "../api/auth";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export function RegisterPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { login: setSession } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (password !== confirmPassword) {
      setError("Las contraseñas no coinciden");
      return;
    }
    setSubmitting(true);
    try {
      const { token, username: registeredUsername } = await register(username, password, inviteCode);
      setSession(token, registeredUsername);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo completar el registro");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-tinta px-4 text-papel">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage:
            "repeating-linear-gradient(0deg, transparent, transparent 27px, currentColor 28px), repeating-linear-gradient(90deg, transparent, transparent 27px, currentColor 28px)",
        }}
      />

      <form
        onSubmit={handleSubmit}
        className="relative w-full max-w-sm space-y-6 rounded-xl border border-white/10 bg-tinta-2/80 p-8 shadow-2xl backdrop-blur"
      >
        <div className="space-y-1 text-center">
          <p className="text-[0.6875rem] tracking-[0.24em] text-papel/50 uppercase">Sala de vigilancia jurídica</p>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Crear cuenta</h1>
        </div>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <label htmlFor="register-username" className="text-xs font-medium text-papel/70">
              Usuario
            </label>
            <input
              id="register-username"
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="Usuario"
              required
              className="w-full rounded-md border border-white/15 bg-tinta px-3 py-2.5 text-sm text-papel placeholder:text-papel/30 outline-none focus-visible:border-sello focus-visible:ring-[3px] focus-visible:ring-sello/30"
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="register-password" className="text-xs font-medium text-papel/70">
              Contraseña
            </label>
            <input
              id="register-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Mínimo 8 caracteres"
              required
              minLength={8}
              className="w-full rounded-md border border-white/15 bg-tinta px-3 py-2.5 text-sm text-papel placeholder:text-papel/30 outline-none focus-visible:border-sello focus-visible:ring-[3px] focus-visible:ring-sello/30"
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="register-confirm-password" className="text-xs font-medium text-papel/70">
              Confirmar contraseña
            </label>
            <input
              id="register-confirm-password"
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              placeholder="Repite la contraseña"
              required
              className="w-full rounded-md border border-white/15 bg-tinta px-3 py-2.5 text-sm text-papel placeholder:text-papel/30 outline-none focus-visible:border-sello focus-visible:ring-[3px] focus-visible:ring-sello/30"
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="register-invite-code" className="text-xs font-medium text-papel/70">
              Código de invitación
            </label>
            <input
              id="register-invite-code"
              type="text"
              value={inviteCode}
              onChange={(event) => setInviteCode(event.target.value)}
              placeholder="Código de invitación"
              required
              className="w-full rounded-md border border-white/15 bg-tinta px-3 py-2.5 text-sm text-papel placeholder:text-papel/30 outline-none focus-visible:border-sello focus-visible:ring-[3px] focus-visible:ring-sello/30"
            />
          </div>
        </div>

        {error && (
          <p className="rounded-md border border-rojo/40 bg-rojo/10 px-3 py-2 text-sm text-rojo-bg">{error}</p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-sello px-3 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-sello-ink disabled:opacity-60"
        >
          {submitting ? "Creando cuenta…" : "Crear cuenta"}
        </button>

        <p className="text-center text-xs text-papel/50">
          ¿Ya tienes cuenta?{" "}
          <Link to="/login" className="font-medium text-sello hover:underline">
            Entrar
          </Link>
        </p>
      </form>
    </div>
  );
}
```

- [ ] **Step 8: Confirmar que los tests de `RegisterPage` pasan**

Run: `cd frontend && npm test -- --run src/pages/RegisterPage.test.tsx`
Expected: 3 passed.

- [ ] **Step 9: Agregar la ruta `/register` y actualizar `App.test.tsx`**

En `frontend/src/App.tsx`, agregar el import:

```tsx
import { RegisterPage } from "./pages/RegisterPage";
```

Y agregar la ruta, justo después de `<Route path="/login" element={<LoginPage />} />`:

```tsx
            <Route path="/register" element={<RegisterPage />} />
```

Reemplazar el contenido completo de `frontend/src/App.test.tsx` por:

```tsx
import { describe, expect, it, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "./test/server";
import { clearStoredToken, setStoredToken } from "./api/client";
import { App } from "./App";

const BASE_URL = "http://localhost:8000";

describe("App", () => {
  beforeEach(() => {
    clearStoredToken();
    window.history.pushState({}, "", "/");
  });

  it("redirects to the login page when there is no stored session", async () => {
    render(<App />);
    expect(await screen.findByPlaceholderText("Usuario")).toBeInTheDocument();
  });

  it("renders the Dashboard page when a valid session is already stored", async () => {
    setStoredToken("existing-token");
    server.use(http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana" })));

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 10: Confirmar que todo pasa y el build queda limpio**

Run: `cd frontend && npm test -- --run`
Expected: todos PASS.

Run: `cd frontend && npm run build`
Expected: `tsc -b` y `vite build` sin errores.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/pages/LoginPage.tsx frontend/src/pages/LoginPage.test.tsx frontend/src/pages/RegisterPage.tsx frontend/src/pages/RegisterPage.test.tsx frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat: add username/password LoginPage and self-service RegisterPage"
```

---

### Task 7: Frontend — usuario visible en el Sidebar, logout real y cambio de contraseña

**Files:**
- Create: `frontend/src/components/layout/ChangePasswordDialog.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Test: `frontend/src/components/layout/Sidebar.test.tsx` (nuevo)

**Interfaces:**
- Consumes: `useAuth()` (Task 5), `changePassword` de `api/auth.ts` (Task 5).

- [ ] **Step 1: Escribir los tests del Sidebar que fallan**

Crear `frontend/src/components/layout/Sidebar.test.tsx`:

```tsx
import { describe, expect, it, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { clearStoredToken, getStoredToken, setStoredToken } from "../../api/client";
import { AuthProvider } from "../../auth/AuthContext";
import { Sidebar } from "./Sidebar";

const BASE_URL = "http://localhost:8000";

function renderSidebar() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Sidebar />
      </AuthProvider>
    </MemoryRouter>
  );
}

describe("Sidebar", () => {
  beforeEach(() => clearStoredToken());

  it("shows the logged-in username", async () => {
    setStoredToken("existing-token");
    server.use(http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana" })));

    renderSidebar();

    expect(await screen.findByText("ana")).toBeInTheDocument();
  });

  it("calls the backend logout endpoint before clearing the local session", async () => {
    setStoredToken("existing-token");
    let logoutCalled = false;
    server.use(
      http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana" })),
      http.post(`${BASE_URL}/auth/logout`, () => {
        logoutCalled = true;
        return new HttpResponse(null, { status: 204 });
      })
    );
    const user = userEvent.setup();
    renderSidebar();
    await screen.findByText("ana");

    await user.click(screen.getByText("Cerrar sesión"));

    await waitFor(() => expect(logoutCalled).toBe(true));
    expect(getStoredToken()).toBeNull();
  });

  it("opens the change password dialog and submits a valid change", async () => {
    setStoredToken("existing-token");
    let changeBody: unknown = null;
    server.use(
      http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana" })),
      http.post(`${BASE_URL}/auth/change-password`, async ({ request }) => {
        changeBody = await request.json();
        return new HttpResponse(null, { status: 204 });
      })
    );
    const user = userEvent.setup();
    renderSidebar();
    await screen.findByText("ana");

    await user.click(screen.getByText("Cambiar contraseña"));
    await user.type(screen.getByLabelText("Contraseña actual"), "OldPassword1");
    await user.type(screen.getByLabelText("Nueva contraseña"), "NewPassword2");
    await user.type(screen.getByLabelText("Confirmar nueva contraseña"), "NewPassword2");
    await user.click(screen.getByText("Guardar"));

    expect(await screen.findByText("Contraseña actualizada.")).toBeInTheDocument();
    expect(changeBody).toEqual({ current_password: "OldPassword1", new_password: "NewPassword2" });
  });

  it("shows an error when the new passwords don't match, without calling the API", async () => {
    setStoredToken("existing-token");
    let called = false;
    server.use(
      http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana" })),
      http.post(`${BASE_URL}/auth/change-password`, () => {
        called = true;
        return new HttpResponse(null, { status: 204 });
      })
    );
    const user = userEvent.setup();
    renderSidebar();
    await screen.findByText("ana");

    await user.click(screen.getByText("Cambiar contraseña"));
    await user.type(screen.getByLabelText("Contraseña actual"), "OldPassword1");
    await user.type(screen.getByLabelText("Nueva contraseña"), "NewPassword2");
    await user.type(screen.getByLabelText("Confirmar nueva contraseña"), "Different3");
    await user.click(screen.getByText("Guardar"));

    expect(await screen.findByText("Las contraseñas no coinciden")).toBeInTheDocument();
    expect(called).toBe(false);
  });
});
```

- [ ] **Step 2: Confirmar que fallan**

Run: `cd frontend && npm test -- --run src/components/layout/Sidebar.test.tsx`
Expected: FAIL — el Sidebar todavía no muestra el username ni tiene diálogo de cambio de contraseña, y "Cerrar sesión" no llama al backend.

- [ ] **Step 3: Crear `ChangePasswordDialog.tsx`**

```tsx
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";
import { changePassword } from "../../api/auth";
import { ApiError } from "../../api/client";
import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "../ui/dialog";
import { Input } from "../ui/input";
import { Label } from "../ui/label";

export function ChangePasswordDialog() {
  const [open, setOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const mutation = useMutation({
    mutationFn: () => changePassword(currentPassword, newPassword),
    onSuccess: () => {
      setSuccess(true);
      setError(null);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    },
    onError: (err: unknown) => {
      setError(err instanceof ApiError ? err.message : "No se pudo cambiar la contraseña");
      setSuccess(false);
    },
  });

  function handleSubmit() {
    setError(null);
    setSuccess(false);
    if (newPassword !== confirmPassword) {
      setError("Las contraseñas no coinciden");
      return;
    }
    mutation.mutate();
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen);
        if (nextOpen) {
          setCurrentPassword("");
          setNewPassword("");
          setConfirmPassword("");
          setError(null);
          setSuccess(false);
        }
      }}
    >
      <DialogTrigger asChild>
        <button className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-sidebar-foreground/60 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground">
          <KeyRound className="size-4 shrink-0" aria-hidden="true" />
          Cambiar contraseña
        </button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-display">Cambiar contraseña</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="change-password-current">Contraseña actual</Label>
            <Input
              id="change-password-current"
              type="password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="change-password-new">Nueva contraseña</Label>
            <Input
              id="change-password-new"
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              minLength={8}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="change-password-confirm">Confirmar nueva contraseña</Label>
            <Input
              id="change-password-confirm"
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
            />
          </div>
          {error && <p className="text-sm font-medium text-rojo">{error}</p>}
          {success && <p className="text-sm font-medium text-verde">Contraseña actualizada.</p>}
        </div>
        <DialogFooter>
          <Button onClick={handleSubmit} disabled={mutation.isPending}>
            {mutation.isPending ? "Guardando…" : "Guardar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 4: Actualizar `Sidebar.tsx`**

Reemplazar el contenido completo de `frontend/src/components/layout/Sidebar.tsx` por:

```tsx
import { NavLink } from "react-router-dom";
import { FileStack, Gauge, LogOut, PlayCircle, Radar } from "lucide-react";
import { useAuth } from "../../auth/AuthContext";
import { ChangePasswordDialog } from "./ChangePasswordDialog";

const LINKS = [
  { to: "/", label: "Dashboard", end: true, icon: Gauge },
  { to: "/sources", label: "Fuentes", end: false, icon: Radar },
  { to: "/runs", label: "Runs", end: false, icon: PlayCircle },
  { to: "/documents", label: "Documentos", end: false, icon: FileStack },
];

export function Sidebar() {
  const { username, logout } = useAuth();

  return (
    <nav className="flex h-screen w-60 shrink-0 flex-col bg-sidebar text-sidebar-foreground">
      <div className="px-5 pt-6 pb-5">
        <p className="font-display text-xl font-semibold tracking-tight">IURISYNC</p>
        <p className="mt-0.5 text-[0.6875rem] tracking-[0.18em] text-sidebar-foreground/50 uppercase">
          Sala de vigilancia
        </p>
      </div>

      <ul className="flex-1 space-y-1 px-3">
        {LINKS.map((link) => {
          const Icon = link.icon;
          return (
            <li key={link.to}>
              <NavLink
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-sidebar-primary text-sidebar-primary-foreground"
                      : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground"
                  }`
                }
              >
                <Icon className="size-4 shrink-0" aria-hidden="true" />
                {link.label}
              </NavLink>
            </li>
          );
        })}
      </ul>

      <div className="space-y-1 border-t border-sidebar-border px-3 py-3">
        {username && (
          <p className="truncate px-3 pb-1 text-xs text-sidebar-foreground/50" title={username}>
            {username}
          </p>
        )}
        <ChangePasswordDialog />
        <button
          onClick={() => logout()}
          className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-sidebar-foreground/60 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground"
        >
          <LogOut className="size-4 shrink-0" aria-hidden="true" />
          Cerrar sesión
        </button>
      </div>
    </nav>
  );
}
```

- [ ] **Step 5: Confirmar que los tests pasan**

Run: `cd frontend && npm test -- --run src/components/layout/Sidebar.test.tsx`
Expected: 4 passed.

- [ ] **Step 6: Correr toda la suite y el build**

Run: `cd frontend && npm test -- --run`
Expected: todos PASS.

Run: `cd frontend && npm run build`
Expected: sin errores.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/layout/ChangePasswordDialog.tsx frontend/src/components/layout/Sidebar.tsx frontend/src/components/layout/Sidebar.test.tsx
git commit -m "feat: show logged-in username, real backend logout, and change-password dialog"
```
