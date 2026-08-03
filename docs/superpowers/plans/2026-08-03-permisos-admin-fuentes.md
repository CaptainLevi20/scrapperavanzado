# Permiso de administrador para gestionar fuentes — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restringir a un rol de administrador (`is_admin`) la capacidad de crear, activar o desactivar fuentes de scraping — hoy cualquier usuario autenticado puede hacerlo, y el run programado diario recorre automáticamente toda fuente activa.

**Architecture:** Columna booleana `is_admin` en `users` (default `false`, solo la cuenta `admin` la tiene en `true`). Una dependencia FastAPI nueva (`require_admin`) protege `POST /sources` y `PATCH /sources/{id}`; el resto de rutas de fuentes sigue siendo de solo lectura para cualquier sesión válida. El frontend se entera del rol vía `/auth/me` y la respuesta de login/registro, y oculta el botón "Activar/Desactivar" cuando el usuario no es admin.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (backend), React + TanStack Query + Context API (frontend), pytest / vitest.

## Global Constraints

- Mismo comportamiento en desarrollo y en producción — sin bandera de entorno (spec, sección "Alcance").
- `GET /sources` y `GET /source-families` no cambian: siguen abiertos a cualquier usuario con sesión.
- `POST /runs` y `POST /runs/{id}/cancel` no cambian: cualquier usuario sigue lanzando/cancelando runs manuales.
- Solo la cuenta `admin` queda con `is_admin=true` tras la migración; `aulloa`, `verify-test`, `smoke-test` y cualquier registro futuro quedan en `false` por default.
- No se construye ninguna pantalla para gestionar roles — subir a alguien a admin es una operación manual en la base de datos.

---

## Prerrequisito de entorno (léelo antes de la Tarea 1)

**Esto no es una tarea de código — es un chequeo de una sola vez en esta base de datos de desarrollo local, no se comitea nada.**

La tabla `alembic_version` de este Postgres local quedó apuntando a una
revisión (`4f2e0178ff96`) que no corresponde a ningún archivo en
`alembic/versions/` — un resto de cuando los datos de este Postgres se
migraron desde un checkout antiguo (`featuresaas-scraping-backend`, ver
`docs/` / memoria del proyecto), copiando el volumen de datos en vez de
correr las migraciones. El *esquema* real ya coincide con la cabeza actual
de archivos (`fc6425d9cc05` — confirmado: `bulk_downloads.storage_bucket`,
que es justo lo que agrega esa migración, ya existe en la tabla real), solo
el marcador de bookkeeping está desactualizado. Sin arreglar esto,
`alembic upgrade head` en la Tarea 1 falla con `Can't locate revision
identified by '4f2e0178ff96'`.

- [ ] **Paso 1: Confirmar que el esquema ya está al día**

Run: `docker compose exec -T postgres psql -U iurisync -d iurisync -c "\d+ bulk_downloads"`
Expected: la columna `storage_bucket` ya aparece en la tabla (si no aparece,
NO sigas con el paso 2 — el esquema real está más atrás de lo que parece y
hay que investigar antes de tocar `alembic_version`).

- [ ] **Paso 2: Resincronizar el marcador de Alembic (sin tocar datos ni esquema)**

Run: `cd C:/Users/asant/scrapper-avanzado && .venv/Scripts/python -m alembic stamp fc6425d9cc05`
Expected: sin salida de error.

- [ ] **Paso 3: Verificar**

Run: `.venv/Scripts/python -m alembic current`
Expected: `fc6425d9cc05 (head)`

---

### Task 1: Columna `is_admin` en `users` + migración

**Files:**
- Modify: `core/db/models.py` (clase `User`)
- Modify: `core/db/repository.py` (`create_user`)
- Modify: `tests/test_repository.py`
- Create: `alembic/versions/<generado>_add_is_admin_to_users.py`

**Interfaces:**
- Produces: `User.is_admin: bool` (columna ORM); `repository.create_user(db, username, password_hash, is_admin: bool = False) -> User`.

- [ ] **Step 1: Escribir los tests que fallan**

En `tests/test_repository.py`, justo después de
`test_create_user_and_lookup_by_username` (línea ~396):

```python
def test_create_user_defaults_to_not_admin(db_session):
    user = repository.create_user(db_session, username="ana", password_hash="hashed")
    assert user.is_admin is False


def test_create_user_can_be_created_as_admin(db_session):
    user = repository.create_user(db_session, username="admin", password_hash="hashed", is_admin=True)
    assert user.is_admin is True
```

- [ ] **Step 2: Correr los tests y confirmar que fallan**

Run: `.venv/Scripts/pytest tests/test_repository.py -k "defaults_to_not_admin or can_be_created_as_admin" -v`
Expected: FAIL con `TypeError: create_user() got an unexpected keyword argument 'is_admin'` (o `AttributeError` en `user.is_admin`).

- [ ] **Step 3: Agregar la columna al modelo**

En `core/db/models.py`, dentro de `class User(Base):` (línea 149-154 hoy),
agregar después de `active`:

```python
    active = Column(Boolean, nullable=False, default=True)
    is_admin = Column(Boolean, nullable=False, default=False, server_default="false")
```

- [ ] **Step 4: Agregar el parámetro a `create_user`**

En `core/db/repository.py`, reemplazar:

```python
def create_user(db: Session, username: str, password_hash: str) -> User:
    user = User(username=username, password_hash=password_hash, active=True)
```

por:

```python
def create_user(db: Session, username: str, password_hash: str, is_admin: bool = False) -> User:
    user = User(username=username, password_hash=password_hash, active=True, is_admin=is_admin)
```

- [ ] **Step 5: Correr los tests y confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_repository.py -k "defaults_to_not_admin or can_be_created_as_admin" -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Generar el archivo de migración**

Run: `cd C:/Users/asant/scrapper-avanzado && .venv/Scripts/python -m alembic revision -m "add is_admin to users"`

Esto crea `alembic/versions/<hash>_add_is_admin_to_users.py` con
`down_revision` ya apuntado a `fc6425d9cc05` automáticamente (es el único
head de archivos). Anota el `<hash>` generado — lo necesitas en el paso 8.

- [ ] **Step 7: Completar `upgrade()`/`downgrade()`**

Reemplazar el cuerpo del archivo generado (dejando intactos `revision`,
`down_revision`, `branch_labels`, `depends_on` tal como los escribió
Alembic) por:

```python
def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='false'))
    op.execute("UPDATE users SET is_admin = true WHERE username = 'admin'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'is_admin')
```

- [ ] **Step 8: Aplicar la migración al Postgres de desarrollo y verificar**

Run: `.venv/Scripts/python -m alembic upgrade head`
Expected: sin errores, termina en la nueva revisión.

Run: `docker compose exec -T postgres psql -U iurisync -d iurisync -c "SELECT username, is_admin FROM users ORDER BY id;"`
Expected:

```
 username    | is_admin
-------------+----------
 admin       | t
 aulloa      | f
 verify-test | f
 smoke-test  | f
```

- [ ] **Step 9: Commit**

```bash
git add core/db/models.py core/db/repository.py tests/test_repository.py alembic/versions/
git commit -m "$(cat <<'EOF'
feat: agrega columna is_admin a users con backfill de la cuenta admin

Base para restringir la gestión de fuentes (activar/desactivar/crear)
a un rol de administrador — ver docs/superpowers/specs/2026-08-03-permisos-admin-fuentes-design.md.
EOF
)"
```

---

### Task 2: Exponer `is_admin` en `/auth/me`, `/auth/login` y `/auth/register`

**Files:**
- Modify: `api/schemas.py` (`MeResponse`, `AuthResponse`)
- Modify: `api/routers/auth.py` (`register`, `login`, `me`)
- Modify: `tests/test_api_auth.py`

**Interfaces:**
- Consumes: `User.is_admin` (Task 1).
- Produces: `MeResponse.is_admin: bool`, `AuthResponse.is_admin: bool` — el frontend (Task 4) lee estos dos campos.

- [ ] **Step 1: Escribir los tests que fallan**

En `tests/test_api_auth.py`, actualizar la aserción existente en
`test_register_creates_user_and_returns_a_working_session` (línea 19):

```python
    assert me_response.json() == {"username": "ana", "is_admin": False}
```

Y agregar, después de `test_login_rejects_unknown_username` (línea ~140):

```python
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
```

- [ ] **Step 2: Correr los tests y confirmar que fallan**

Run: `.venv/Scripts/pytest tests/test_api_auth.py -v`
Expected: FAIL — `test_register_creates_user_and_returns_a_working_session` por la
igualdad exacta del dict, y los dos tests nuevos con `KeyError: 'is_admin'`.

- [ ] **Step 3: Agregar el campo a los schemas**

En `api/schemas.py`:

```python
class AuthResponse(BaseModel):
    token: str
    username: str
    is_admin: bool


class MeResponse(BaseModel):
    username: str
    is_admin: bool
```

- [ ] **Step 4: Poblar el campo en las tres rutas**

En `api/routers/auth.py`, `register` (línea 63-65):

```python
    user = repository.create_user(db, username=payload.username, password_hash=hash_password(payload.password))
    token = _issue_session(db, user.id)
    return {"token": token, "username": user.username, "is_admin": user.is_admin}
```

`login` (línea 75-76):

```python
    repository.touch_user_last_login(db, user.id)
    token = _issue_session(db, user.id)
    return {"token": token, "username": user.username, "is_admin": user.is_admin}
```

`me` (línea 107-109):

```python
@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(require_session)):
    return {"username": user.username, "is_admin": user.is_admin}
```

- [ ] **Step 5: Correr los tests y confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_api_auth.py -v`
Expected: todos PASS.

- [ ] **Step 6: Correr toda la suite de backend (chequeo de regresión rápido)**

Run: `.venv/Scripts/pytest -q`
Expected: mismo resultado que antes del cambio (90 passed, 1 pre-existing
failure de `test_migrations.py` — ver Gotchas del skill `run-iurisync`,
no relacionado con este cambio).

- [ ] **Step 7: Commit**

```bash
git add api/schemas.py api/routers/auth.py tests/test_api_auth.py
git commit -m "feat: expone is_admin en /auth/me, /auth/login y /auth/register"
```

---

### Task 3: Proteger la gestión de fuentes con `require_admin`

**Files:**
- Modify: `api/deps.py`
- Modify: `api/routers/sources.py`
- Modify: `tests/conftest.py` (fixture `admin_auth_header`)
- Modify: `tests/test_api_sources.py`

**Interfaces:**
- Consumes: `User.is_admin` (Task 1).
- Produces: `require_admin` — dependencia FastAPI reutilizable, mismo patrón que `require_session`.

- [ ] **Step 1: Agregar la fixture de admin y escribir los tests que fallan**

En `tests/conftest.py`, justo después de la fixture `auth_header` existente:

```python
@pytest.fixture()
def admin_auth_header(db_session):
    import secrets

    from core.db import repository
    from core.security import hash_password, hash_session_token

    user = repository.create_user(
        db_session, username="tester-admin", password_hash=hash_password("Password123"), is_admin=True
    )
    raw_token = secrets.token_urlsafe(32)
    repository.create_session(db_session, user_id=user.id, token_hash=hash_session_token(raw_token))
    return {"Authorization": f"Bearer {raw_token}"}
```

En `tests/test_api_sources.py`, actualizar `test_create_and_list_source`
(línea 11) para usar `admin_auth_header` en vez de `auth_header` en las
llamadas que crean/modifican (la de listar puede seguir con `auth_header`,
que sigue siendo de solo lectura):

```python
def test_create_and_list_source(api_client, auth_header, admin_auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")

    create_response = api_client.post(
        "/sources",
        json={"family_key": "constitucional", "name": "Corte Constitucional", "family_params": {}},
        headers=admin_auth_header,
    )
    assert create_response.status_code == 201
    source_id = create_response.json()["id"]

    list_response = api_client.get("/sources", headers=auth_header)
    assert list_response.status_code == 200
    assert [s["name"] for s in list_response.json()] == ["Corte Constitucional"]

    patch_response = api_client.patch(f"/sources/{source_id}", json={"active": False}, headers=admin_auth_header)
    assert patch_response.status_code == 200
    assert patch_response.json()["active"] is False
```

También actualizar `test_patch_unknown_source_returns_404` y
`test_create_source_with_unknown_family_key_returns_400` (líneas 91-102)
para usar `admin_auth_header` — de lo contrario, tras el Step 4 de este
task, ambas fallarían con 403 en vez del 404/400 que quieren probar:

```python
def test_patch_unknown_source_returns_404(api_client, admin_auth_header):
    response = api_client.patch("/sources/999999", json={"active": False}, headers=admin_auth_header)
    assert response.status_code == 404


def test_create_source_with_unknown_family_key_returns_400(api_client, admin_auth_header):
    response = api_client.post(
        "/sources",
        json={"family_key": "no-existe", "name": "Fuente X", "family_params": {}},
        headers=admin_auth_header,
    )
    assert response.status_code == 400
```

Y agregar, al final del archivo, los tests de rechazo para un usuario
regular:

```python
def test_post_source_rejects_a_non_admin_user(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")

    response = api_client.post(
        "/sources",
        json={"family_key": "constitucional", "name": "Corte Constitucional", "family_params": {}},
        headers=auth_header,
    )

    assert response.status_code == 403


def test_patch_source_rejects_a_non_admin_user(api_client, auth_header, admin_auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(
        db_session, family_key="constitucional", name="Corte Constitucional", family_params={}
    )

    response = api_client.patch(f"/sources/{source.id}", json={"active": False}, headers=auth_header)

    assert response.status_code == 403


def test_get_sources_works_for_a_non_admin_user(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})

    response = api_client.get("/sources", headers=auth_header)

    assert response.status_code == 200
    assert len(response.json()) == 1
```

- [ ] **Step 2: Correr los tests y confirmar que fallan**

Run: `.venv/Scripts/pytest tests/test_api_sources.py -v`
Expected: `test_post_source_rejects_a_non_admin_user` y
`test_patch_source_rejects_a_non_admin_user` FALLAN (reciben 201/200 en vez
de 403 — la protección todavía no existe); el resto sigue en verde.

- [ ] **Step 3: Agregar `require_admin` a `api/deps.py`**

Agregar al final del archivo:

```python
def require_admin(user: User = Depends(require_session)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Esta acción requiere permisos de administrador")
    return user
```

- [ ] **Step 4: Aplicar la dependencia en las rutas de escritura**

En `api/routers/sources.py`, los imports actuales del archivo son:

```python
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from api.deps import get_db, require_session
from api.schemas import SourceCreate, SourceFamilyOut, SourceOut, SourceUpdate
from core.db import repository
from core.scrapers import families  # noqa: F401 — ensures FAMILY_REGISTRY is populated
from core.scrapers.registry import FAMILY_REGISTRY
```

Cambiar las dos primeras líneas de imports relevantes a:

```python
from api.deps import get_db, require_admin, require_session
from api.schemas import SourceCreate, SourceFamilyOut, SourceOut, SourceUpdate
from core.db import repository
from core.db.models import User
```

Y aplicar la dependencia solo a `POST` y `PATCH` (no a nivel de router, para
no afectar los `GET`):

```python
@router.post("/sources", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
def post_source(payload: SourceCreate, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
```

```python
@router.patch("/sources/{source_id}", response_model=SourceOut)
def patch_source(
    source_id: int,
    payload: SourceUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
```

- [ ] **Step 5: Correr los tests y confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_api_sources.py -v`
Expected: todos PASS.

- [ ] **Step 6: Correr toda la suite de backend**

Run: `.venv/Scripts/pytest -q`
Expected: mismo resultado base (90 passed, 1 pre-existing failure ajena a
este cambio).

- [ ] **Step 7: Commit**

```bash
git add api/deps.py api/routers/sources.py tests/conftest.py tests/test_api_sources.py
git commit -m "feat: restringe crear/activar/desactivar fuentes al rol admin"
```

---

### Task 4: Frontend — `isAdmin` en `AuthContext`

**Files:**
- Modify: `frontend/src/api/auth.ts`
- Modify: `frontend/src/auth/AuthContext.tsx`
- Modify: `frontend/src/auth/AuthContext.test.tsx`
- Modify: `frontend/src/pages/LoginPage.tsx`
- Modify: `frontend/src/pages/RegisterPage.tsx`

**Interfaces:**
- Consumes: `is_admin` en las respuestas de `/auth/me`, `/auth/login`, `/auth/register` (Task 2).
- Produces: `useAuth().isAdmin: boolean` — lo consume `SourcesPage` (Task 5).

- [ ] **Step 1: Escribir los tests que fallan**

En `frontend/src/auth/AuthContext.test.tsx`, actualizar el componente
`Probe` para exponer `isAdmin`:

```tsx
function Probe() {
  const { username, token, isAdmin, isLoading, login, logout } = useAuth();
  if (isLoading) return <span data-testid="loading">loading</span>;
  return (
    <div>
      <span data-testid="token">{token ?? "none"}</span>
      <span data-testid="username">{username ?? "none"}</span>
      <span data-testid="is-admin">{String(isAdmin)}</span>
      <button onClick={() => login("new-token", "ana", true)}>login</button>
      <button onClick={() => logout()}>logout</button>
    </div>
  );
}
```

Y agregar, al final del archivo (dentro del `describe("AuthContext", ...)`):

```tsx
  it("populates isAdmin from /auth/me on mount", async () => {
    setStoredToken("existing-token");
    server.use(http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "ana", is_admin: true })));

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    expect(await screen.findByTestId("is-admin")).toHaveTextContent("true");
  });

  it("login updates isAdmin immediately, without waiting on /auth/me", async () => {
    const user = userEvent.setup();
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    await screen.findByTestId("token");

    await user.click(screen.getByText("login"));

    expect(screen.getByTestId("is-admin")).toHaveTextContent("true");
  });
```

- [ ] **Step 2: Correr los tests y confirmar que fallan**

Run: `cd frontend && npx vitest run --run AuthContext`
Expected: FAIL — `isAdmin` es `undefined` en ambos tests nuevos (y el
`Probe` actualizado rompe compilación/tipos hasta el Step 3).

- [ ] **Step 3: Actualizar `api/auth.ts`**

```typescript
import { apiFetch } from "./client";

export interface AuthResponse {
  token: string;
  username: string;
  is_admin: boolean;
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

export function fetchMe(): Promise<{ username: string; is_admin: boolean }> {
  return apiFetch<{ username: string; is_admin: boolean }>("/auth/me");
}

export function changePassword(current_password: string, new_password: string): Promise<void> {
  return apiFetch<void>(
    "/auth/change-password",
    {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
    },
    { skipUnauthorizedHandling: true }
  );
}
```

(Solo cambian `AuthResponse`, `fetchMe` — el resto del archivo queda igual,
mostrado completo para que quede claro qué NO cambia.)

- [ ] **Step 4: Actualizar `AuthContext.tsx`**

```tsx
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { fetchMe, logoutRequest } from "../api/auth";
import { clearStoredToken, getStoredToken, registerUnauthorizedHandler, setStoredToken } from "../api/client";

interface AuthContextValue {
  username: string | null;
  token: string | null;
  isAdmin: boolean;
  isLoading: boolean;
  login: (token: string, username: string, isAdmin?: boolean) => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => getStoredToken());
  const [username, setUsername] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(() => getStoredToken() !== null);

  useEffect(() => {
    registerUnauthorizedHandler(() => {
      setToken(null);
      setUsername(null);
      setIsAdmin(false);
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
        if (!cancelled) {
          setUsername(me.username);
          setIsAdmin(me.is_admin);
        }
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

  function login(newToken: string, newUsername: string, newIsAdmin = false) {
    setStoredToken(newToken);
    setToken(newToken);
    setUsername(newUsername);
    setIsAdmin(newIsAdmin);
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
    setIsAdmin(false);
  }

  return (
    <AuthContext.Provider value={{ username, token, isAdmin, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth debe usarse dentro de AuthProvider");
  return context;
}
```

- [ ] **Step 5: Correr los tests y confirmar que pasan**

Run: `cd frontend && npx vitest run --run AuthContext`
Expected: todos PASS.

- [ ] **Step 6: Pasar el `is_admin` real en `LoginPage.tsx` y `RegisterPage.tsx`**

En `frontend/src/pages/LoginPage.tsx`, línea 20-21:

```tsx
      const { token, username: loggedInUsername, is_admin } = await login(username, password);
      setSession(token, loggedInUsername, is_admin);
```

En `frontend/src/pages/RegisterPage.tsx`, línea 26-27:

```tsx
      const { token, username: registeredUsername, is_admin } = await register(username, password, inviteCode);
      setSession(token, registeredUsername, is_admin);
```

(`LoginPage.test.tsx`/`RegisterPage.test.tsx` no necesitan cambios: sus
mocks no incluyen `is_admin`, así que llega `undefined` y el parámetro por
defecto de `login()` lo resuelve a `false` — ninguno de esos tests verifica
`isAdmin`.)

- [ ] **Step 7: Correr toda la suite de frontend y el chequeo de tipos**

Run: `cd frontend && npx tsc --noEmit && npm test -- --run`
Expected: sin errores de tipos, todos los tests pasan (mismo conteo base
+ 2 tests nuevos de `AuthContext`).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/auth.ts frontend/src/auth/AuthContext.tsx frontend/src/auth/AuthContext.test.tsx frontend/src/pages/LoginPage.tsx frontend/src/pages/RegisterPage.tsx
git commit -m "feat: expone isAdmin en AuthContext desde /auth/me y login/registro"
```

---

### Task 5: Frontend — Ocultar el botón Activar/Desactivar para no-admins

**Files:**
- Modify: `frontend/src/pages/SourcesPage.tsx`
- Modify: `frontend/src/pages/SourcesPage.test.tsx`

**Interfaces:**
- Consumes: `useAuth().isAdmin` (Task 4).

- [ ] **Step 1: Actualizar el helper de render y escribir los tests que fallan**

En `frontend/src/pages/SourcesPage.test.tsx`, agregar los imports
necesarios y reemplazar `renderPage`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { delay, http, HttpResponse } from "msw";
import { server } from "../test/server";
import { clearStoredToken, setStoredToken } from "../api/client";
import { AuthProvider } from "../auth/AuthContext";
import { SourcesPage } from "./SourcesPage";

const BASE_URL = "http://localhost:8000";

function renderPage({ isAdmin = true }: { isAdmin?: boolean } = {}) {
  clearStoredToken();
  setStoredToken("test-token");
  server.use(http.get(`${BASE_URL}/auth/me`, () => HttpResponse.json({ username: "tester", is_admin: isAdmin })));
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <SourcesPage />
      </AuthProvider>
    </QueryClientProvider>
  );
}
```

(Todas las llamadas existentes a `renderPage()` sin argumentos siguen
funcionando igual — quedan como admin por default, que es el caso que ya
cubrían.)

Agregar, al final del `describe("SourcesPage — toggle active state", ...)`:

```tsx
  it("hides the Activar/Desactivar button for a non-admin user", async () => {
    server.use(
      http.get(`${BASE_URL}/sources`, () =>
        HttpResponse.json([{ id: 1, family_key: "constitucional", name: "Corte Constitucional", family_params: {}, active: true }])
      )
    );

    renderPage({ isAdmin: false });

    await screen.findByText("Corte Constitucional");
    expect(screen.queryByText("Desactivar")).not.toBeInTheDocument();
    expect(screen.queryByText("Activar")).not.toBeInTheDocument();
  });
```

- [ ] **Step 2: Correr los tests y confirmar el estado**

Run: `cd frontend && npx vitest run --run SourcesPage`
Expected: el test nuevo FALLA (el botón "Desactivar" sigue apareciendo
porque `SourceRow` todavía no consulta `isAdmin`); los demás tests de este
archivo deben seguir en verde ya con el `renderPage` nuevo (si alguno falla
por falta de `AuthProvider`/token, revisar el Step 1 antes de continuar).

- [ ] **Step 3: Gatear el botón en `SourceRow`**

En `frontend/src/pages/SourcesPage.tsx`, agregar el import y usar
`isAdmin`:

```tsx
import { useAuth } from "../auth/AuthContext";
```

```tsx
function SourceRow({ source }: { source: Source }) {
  const queryClient = useQueryClient();
  const { isAdmin } = useAuth();
  const toggleMutation = useMutation({
    mutationFn: () => updateSource(source.id, { active: !source.active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sources"] }),
  });

  return (
    <tr className={TBODY_ROW}>
      <td className={`${TD} font-medium text-foreground`}>{source.name}</td>
      <td className={TD}>
        <span className={`stamp bg-card ${source.active ? "border-verde/50 text-verde" : "border-grafito/40 text-grafito"}`}>
          <span className="stamp-dot" />
          {source.active ? "Activa" : "Inactiva"}
        </span>
      </td>
      <td className={TD}>
        {isAdmin && (
          <Button variant="outline" size="sm" onClick={() => toggleMutation.mutate()} disabled={toggleMutation.isPending}>
            <Power className="size-3.5" aria-hidden="true" />
            {source.active ? "Desactivar" : "Activar"}
          </Button>
        )}
      </td>
    </tr>
  );
}
```

(Solo cambia el cuerpo de `SourceRow` — el resto de `SourcesPage.tsx` no se
toca.)

- [ ] **Step 4: Correr los tests y confirmar que pasan**

Run: `cd frontend && npx vitest run --run SourcesPage`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/SourcesPage.tsx frontend/src/pages/SourcesPage.test.tsx
git commit -m "feat: oculta Activar/Desactivar fuentes para usuarios no-admin"
```

---

### Task 6: Verificación final de extremo a extremo

**Files:** ninguno (solo verificación, sin cambios de código).

- [ ] **Step 1: Suite completa de backend**

Run: `.venv/Scripts/pytest -q`
Expected: mismo resultado base que antes de empezar (90 passed + los tests
nuevos de las Tareas 1-3, 1 pre-existing failure ajena a este trabajo —
`test_migrations.py`, ver Gotchas del skill `run-iurisync`).

- [ ] **Step 2: Suite completa de frontend + chequeo de tipos**

Run: `cd frontend && npx tsc --noEmit && npm test -- --run`
Expected: sin errores de tipos, todos los tests pasan (244 base + los
nuevos de las Tareas 4-5).

- [ ] **Step 3: Verificación manual en la app corriendo**

Con el entorno de desarrollo arriba (`uvicorn`, `celery worker`, `npm run
dev`, ver skill `run-iurisync`):
1. Iniciar sesión como `admin` → en "Fuentes", el botón
   "Activar"/"Desactivar" debe aparecer y funcionar.
2. Iniciar sesión como `aulloa` (o cualquier otra cuenta no-admin) → en
   "Fuentes", la columna "Acciones" debe estar vacía en todas las filas.
3. Con la sesión de `aulloa`, intentar `PATCH /sources/{id}` directamente
   (ej. `curl` con su token) → debe responder `403`.

- [ ] **Step 4: No hay commit en esta tarea — es solo verificación.**
