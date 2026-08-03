# Permiso de administrador para gestionar fuentes de scraping

## Problema

Hoy no existe ningún concepto de rol en el sistema: cualquier usuario
registrado (`users` no tiene ningún campo de permisos) puede activar,
desactivar o crear una fuente desde `PATCH /sources/{id}` / `POST /sources` —
las mismas rutas que expone la página "Fuentes" del frontend
(`frontend/src/pages/SourcesPage.tsx`).

Cada fuente nueva requiere trabajo de desarrollo específico por familia
técnica (formateo de títulos, parseo de fechas, nomenclatura — ver los specs
de `docs/superpowers/specs/*-design.md` de fuentes ya agregadas) antes de
estar lista para producción. El run programado diario
(`worker/beat_schedule.py::trigger_scheduled_run`) dispara
`orchestrate_run.delay(run_id)` sin `source_ids`, y `orchestrate_run`
(`worker/tasks.py:384`) resuelve ese caso con
`repository.list_sources(db, active=True)` — es decir, **toda** fuente
marcada como activa entra al scraping automático de esa noche, sin ningún
filtro adicional de "esta ya está lista". Si alguien activa una fuente a
medio terminar, esa misma noche se scrapea de verdad y puede producir
documentos con títulos mal formados u otros datos incorrectos.

## Alcance

Se introduce un permiso de administrador que controla quién puede modificar
el catálogo de fuentes. **No** se toca:

- `GET /sources` / `GET /source-families`: siguen abiertos a cualquier
  usuario con sesión (solo lectura).
- `POST /runs`, `POST /runs/{id}/cancel`: cualquier usuario sigue pudiendo
  lanzar/cancelar runs manuales sobre las fuentes que ya estén activas —
  esa decisión la sigue controlando el admin desde Fuentes, no hace falta
  gatear runs también.
- El comportamiento del scheduler (`trigger_scheduled_run`) no cambia — sigue
  recorriendo todas las fuentes activas. La protección está en controlar
  *quién puede marcar una fuente como activa*, no en el propio scheduler.
- No hay distinción de entorno: la misma regla aplica en desarrollo y en
  producción (decisión explícita del usuario — evita sorpresas al desplegar).

## Modelo de datos

Columna nueva `is_admin` (`Boolean`, `nullable=False`, `default=False`) en
`core/db/models.py::User`. Se eligió un booleano y no un campo de rol de
texto (`"admin"` / `"regular"`) porque solo existen dos niveles hoy y no hay
ningún indicio de un tercero — si aparece uno más adelante, migrar de
booleano a texto es un cambio menor comparado con cargar esa flexibilidad
sin usarla ahora.

Migración de Alembic (`alembic/versions/<generado>_add_is_admin_to_users.py`)
que:
1. Agrega la columna con `server_default=false()` (para que las filas
   existentes no queden `NULL`), luego quita el `server_default` a nivel de
   columna Python (mismo patrón que otras columnas booleanas del proyecto,
   ej. `Run.cancel_requested`).
2. En el mismo `upgrade()`, un `UPDATE users SET is_admin = true WHERE
   username = 'admin'` — deja esa única cuenta como administradora; el resto
   (`aulloa`, `verify-test`, `smoke-test`, y cualquier registro futuro vía
   `/auth/register`) quedan en `is_admin=false` por default. Subir a alguien
   más a admin es una operación manual directa en la base de datos — con 1-2
   cuentas admin no se justifica construir una pantalla de gestión de roles.

## Backend

Nueva dependencia `require_admin` en `api/deps.py`, junto a la ya existente
`require_session`:

```python
def require_admin(user: User = Depends(require_session)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Esta acción requiere permisos de administrador")
    return user
```

Se aplica como dependencia de ruta (no a nivel de router, para no afectar los
`GET`) en `api/routers/sources.py`:
- `POST /sources` (crear fuente)
- `PATCH /sources/{source_id}` (activar/desactivar, editar `family_params`)

`GET /sources` y `GET /source-families` no cambian (siguen usando solo
`require_session` a nivel de router).

Se agrega `is_admin: bool` a dos schemas en `api/schemas.py`:
- `MeResponse` (usado por `GET /auth/me`)
- `AuthResponse` (usado por `POST /auth/login` y `POST /auth/register`) — así
  el frontend conoce el rol inmediatamente tras iniciar sesión, sin esperar
  una segunda llamada a `/auth/me`.

`api/routers/auth.py` construye ambas respuestas a partir del objeto `User`
ya cargado (`login`, `register`, `me`), así que solo hace falta incluir el
campo nuevo al armar el dict/response — no cambia la lógica de
autenticación en sí.

## Frontend

`frontend/src/auth/AuthContext.tsx` gana `isAdmin: boolean`:
- Poblado desde `fetchMe()` en el efecto de montaje (igual que `username`
  hoy).
- Poblado también en `login()` a partir de la respuesta de
  login/register, para que esté disponible de inmediato tras autenticarse
  en la sesión actual (sin depender del efecto de montaje, que no vuelve a
  correr después de un login exitoso).
- `useAuth()` expone `isAdmin` junto a los campos ya existentes.

`frontend/src/pages/SourcesPage.tsx` (`SourceRow`): el botón
"Activar"/"Desactivar" solo se renderiza si `isAdmin` es `true`. Si es
`false`, la celda de "Acciones" queda vacía — no se muestra deshabilitado
con tooltip, porque no hay ninguna acción disponible que valga la pena
señalar a un usuario regular ahí.

Ningún otro componente cambia: `RunsPage` (creación de runs manuales) no
lee `isAdmin`, coherente con que esa acción sigue abierta a todos.

## Manejo de errores

Si un usuario regular llama `POST /sources` o `PATCH /sources/{id}`
directamente (sin pasar por la UI, ej. por API), recibe `403 Forbidden` con
el mensaje ya citado arriba — distinto del `401` que ya devuelve
`require_session` cuando no hay sesión válida. Mismo patrón que el resto de
la API: 401 = "no sé quién eres", 403 = "sé quién eres, pero no puedes hacer
esto".

## Pruebas

**Backend** (`tests/test_api_sources.py`):
- Un usuario sin `is_admin` recibe `403` en `POST /sources`.
- Un usuario sin `is_admin` recibe `403` en `PATCH /sources/{id}` (tanto para
  `active` como para `family_params`).
- Un usuario con `is_admin=true` puede hacer ambas cosas (caso ya cubierto
  hoy, se actualiza el fixture de usuario de test para marcarlo admin
  explícitamente en vez de asumir que cualquier sesión basta).
- `GET /sources` sigue funcionando igual para admin y no-admin.

**Backend — migración de backfill**: la lógica del backfill (`UPDATE ... WHERE
username = 'admin'`) se verificó manualmente contra una base Postgres
descartable, con cuentas `admin`, `aulloa`, `Admin` (mayúscula distinta) y
`smoke-test`: solo `admin` quedó con `is_admin=true`, y el `downgrade`
también resultó limpio. No se agregó una prueba automatizada porque
`tests/conftest.py` crea el esquema de pruebas con
`Base.metadata.create_all(...)` en vez de correr las migraciones de Alembic
reales, así que el `upgrade()` de esta migración nunca se ejecuta dentro de
`pytest`; una prueba dedicada que sí invocara Alembic de verdad tropezaría
con la misma limitación ya conocida de este entorno Windows que hace fallar
`tests/test_migrations.py::test_alembic_upgrade_head_creates_all_tables`
(`FileNotFoundError` al invocar el ejecutable `alembic` como subproceso).

**Frontend** (`frontend/src/pages/SourcesPage.test.tsx`):
- Con `isAdmin=false` en el contexto de auth, el botón
  "Activar"/"Desactivar" no aparece en ninguna fila.
- Con `isAdmin=true`, aparece y funciona como hoy (caso ya cubierto,
  se ajusta el mock de `AuthContext` para declarar `isAdmin=true`
  explícitamente).

**Frontend** (`frontend/src/auth/AuthContext.test.tsx`):
- `isAdmin` se puebla correctamente desde `fetchMe()` y desde `login()`.
