# Autenticación de usuarios (registro + login) — Diseño

Fecha: 2026-07-15

## Contexto y objetivo

IURISYNC protege hoy todos sus endpoints con una sola **API key compartida** (tabla `api_keys`, hash SHA-256, header `X-API-Key`, dependencia `require_api_key` en cada router). No hay usuarios: cualquiera con la clave ve y hace exactamente lo mismo.

Este diseño reemplaza ese mecanismo por un login real de **usuario y contraseña**, con **registro propio** protegido por un código de invitación compartido (no hay panel de administración ni CLI para crear usuarios). No hay roles ni permisos — todos los usuarios autenticados tienen acceso idéntico a toda la aplicación; la única distinción es "¿hay una sesión válida o no?".

Explícitamente en alcance:
- Registro propio (usuario + contraseña + código de invitación), con login automático tras registrarse.
- Login con usuario y contraseña.
- Cierre de sesión con invalidación real del lado del servidor.
- Cambio de contraseña por el propio usuario, desde la app.

Explícitamente fuera de alcance:
- Roles o permisos de cualquier tipo.
- Recuperación de contraseña por correo (si alguien la pierde sin poder cambiarla desde la app, no hay flujo — se resuelve creando una cuenta nueva).
- Rate limiting o bloqueo por intentos fallidos de login.
- Límite de sesiones concurrentes por usuario.
- Panel de administración de usuarios.

## Arquitectura

Se elimina por completo el mecanismo de API key: la tabla `api_keys`, `core/security.py::hash_api_key` (se reemplaza por hashing de contraseñas), `api/deps.py::require_api_key`, el comando `core/manage.py::create-api-key` (y su test en `tests/test_manage.py`, ya que no hace falta CLI de creación con registro propio), y toda referencia a `X-API-Key` en el frontend.

Dos tablas nuevas:

**`users`**
- `id`, `username` (string, único, not null), `password_hash` (string, not null), `active` (bool, default `True`), `created_at`, `last_login_at` (nullable).

**`sessions`**
- `id`, `user_id` (FK a `users.id`), `token_hash` (string, not null — nunca se guarda el token en claro, mismo principio que ya usaban las API keys), `created_at`, `expires_at` (not null), `last_used_at` (nullable).

**Contraseñas**: hash con `bcrypt` (nueva dependencia — `bcrypt>=4.0.0` en `requirements.txt`). Mínimo 8 caracteres, validado por Pydantic en los schemas de entrada.

**Código de invitación**: nuevo campo `registration_code: str` en `core/config.py::Settings` (variable de entorno, mismo patrón que `s3_access_key`/`s3_secret_key` — un secreto de configuración, no algo que vive en la base de datos).

**Sesión**: al hacer login o registro exitoso, se genera un token aleatorio (`secrets.token_urlsafe(32)`, igual que ya hace `core/manage.py::create_api_key` hoy para las API keys), se guarda su hash SHA-256 en `sessions.token_hash`, y el token en claro se devuelve una sola vez al cliente. Cada request protegido lo manda como `Authorization: Bearer <token>`.

**Expiración deslizante**: `expires_at` se fija a 30 días desde la creación; cada request válido lo extiende otros 30 días desde ese momento (`repository.touch_session` actualiza `last_used_at` y `expires_at` en la misma operación que ya hace `touch_api_key_last_used` hoy, extendido). Una sesión usada regularmente nunca expira; una olvidada caduca sola a los 30 días de inactividad.

**Cerrar sesión**: borra la fila de `sessions` — invalidación real e inmediata, no solo "olvidar" el token del lado del cliente.

## Backend

### Nuevos endpoints (`api/routers/auth.py`)

- **`POST /auth/register`** — body `{username, password, invite_code}`. Verifica `invite_code == settings.registration_code`; si no coincide, `401` `"Código de invitación inválido"`. Verifica que `username` no exista; si ya existe, `409` `"Ese nombre de usuario ya está en uso"`. Crea el usuario (`password_hash` vía bcrypt), crea la sesión, devuelve `{token, username}`.
- **`POST /auth/login`** — body `{username, password}`. Busca el usuario por `username`; si no existe o la contraseña no verifica contra `password_hash`, `401` `"Usuario o contraseña incorrectos"` (mensaje genérico en ambos casos, para no revelar si el usuario existe). Si es válido y `active`, crea la sesión, actualiza `last_login_at`, devuelve `{token, username}`.
- **`POST /auth/logout`** — requiere sesión válida (`Depends(require_session)`); borra la fila de `sessions` correspondiente al token actual.
- **`POST /auth/change-password`** — requiere sesión válida. Body `{current_password, new_password}`. Verifica `current_password` contra el hash guardado; si no coincide, `401` `"La contraseña actual no es correcta"`. `new_password` con mínimo 8 caracteres (422 automático si no). Actualiza `password_hash`.
- **`GET /auth/me`** — requiere sesión válida; devuelve `{username}`. Lo usa el frontend al arrancar para confirmar que el token guardado sigue siendo válido y obtener el nombre del usuario, sin decodificar nada del lado del cliente (el token es opaco).

### `require_session` (reemplaza `require_api_key` en `api/deps.py`)

Lee `Authorization: Bearer <token>`, calcula su hash, busca una sesión activa (`expires_at > now()`) con ese hash. Si no existe o expiró, `401`. Si existe, actualiza `last_used_at`/`expires_at` (expiración deslizante) y devuelve el `User` asociado como dependencia inyectable — todos los routers existentes (`sources.py`, `runs.py`, `documents.py`) cambian su dependencia de `Depends(require_api_key)` a `Depends(require_session)`.

## Frontend

- **`LoginPage`**: gana un campo de usuario (hoy solo existe un campo para la API key). El submit pasa a llamar `POST /auth/login` con usuario y contraseña reales.
- **Nueva `RegisterPage`**: usuario, contraseña, confirmar contraseña, código de invitación. Enlazada desde `LoginPage` ("¿No tienes cuenta? Regístrate"). Al éxito, guarda el token devuelto y navega directo al Dashboard (login automático, sin pedir credenciales de nuevo).
- **`AuthContext`**: pasa a guardar `{ username, token }` en vez de solo la API key. Al montar la app, si hay un token guardado, llama `GET /auth/me`; si falla (401), limpia todo y manda a `/login` — mismo patrón que ya existe hoy para el 401 genérico de `apiFetch`.
- **`api/client.ts`**: el header cambia de `X-API-Key: <key>` a `Authorization: Bearer <token>`; se mantiene el mismo manejo de 401 (limpia sesión + dispara el handler de "no autorizado" ya existente).
- **Sidebar**: se agrega el nombre del usuario logueado junto al botón "Cerrar sesión" (que ahora llama a `POST /auth/logout` antes de limpiar el token local), y un enlace/botón "Cambiar contraseña" que abre un formulario (contraseña actual + nueva, dos veces para confirmar).

## Manejo de errores

- Login incorrecto → `401`, mensaje genérico `"Usuario o contraseña incorrectos"`.
- Registro con código de invitación incorrecto → `401`, `"Código de invitación inválido"`.
- Registro con username ya existente → `409`, `"Ese nombre de usuario ya está en uso"`.
- Cambio de contraseña con la actual incorrecta → `401`, `"La contraseña actual no es correcta"`.
- Nueva contraseña con menos de 8 caracteres → `422` automático (Pydantic).
- Token inválido, revocado o expirado en cualquier request protegido → `401` — reutiliza el manejo ya existente en `apiFetch` (limpia el token guardado, dispara logout automático).

## Testing y migración

- **Backend**: tests nuevos para los 5 endpoints de `/auth/*` (éxito y cada error listado arriba) y para `require_session` (sesión válida, expirada, revocada/inexistente, extensión de `expires_at` en cada uso).
- **Migración transversal** (el cambio de mayor superficie): el fixture `api_key_header` en `tests/conftest.py` — usado hoy en prácticamente todos los archivos `tests/test_api_*.py` — se reemplaza por un fixture `auth_header` que crea un usuario y una sesión directamente en la base de prueba, devolviendo `{"Authorization": "Bearer <token>"}`. Todos los tests que usan el fixture viejo se actualizan al nuevo — cambio mecánico pero que toca muchos archivos.
- **Frontend**: tests nuevos para `LoginPage` (usuario+contraseña), `RegisterPage` (registro + login automático + los 2 errores), `AuthContext` (verificación vía `/auth/me` al montar, limpieza en 401), cambio de contraseña, y logout llamando al backend antes de limpiar el estado local.

## Fuera de alcance

- Roles o permisos — todos los usuarios autenticados son iguales.
- Recuperación de contraseña por correo.
- Rate limiting / bloqueo por intentos fallidos de login o registro.
- Límite de sesiones concurrentes por usuario o dispositivo.
- Panel de administración de usuarios (crear/desactivar usuarios queda para una iteración futura si hace falta — hoy ni siquiera hay CLI para esto, ya que el registro propio lo reemplaza).
