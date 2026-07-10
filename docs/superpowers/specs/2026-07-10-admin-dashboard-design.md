# Dashboard Administrativo IURISYNC — Design Spec

**Fecha:** 2026-07-10
**Estado:** Aprobado para planificación

## Contexto

El backend IURISYNC (`docs/superpowers/specs/2026-07-10-saas-scraping-backend-design.md`) ya expone una API REST (FastAPI) para gestionar fuentes de scraping, disparar/monitorear runs (Celery) y consultar documentos descargados. Hoy la única forma de interactuar con la API es vía HTTP directo (curl, Postman, scripts). Este spec cubre un dashboard web para que el equipo interno de Avance Jurídico opere el sistema sin tocar la API a mano.

## Audiencia y alcance

- **Usuarios:** equipo interno únicamente. No es un producto de cara a clientes.
- **Casos de uso, sin prioridad entre ellos:** monitorear runs y sus errores, gestionar qué fuentes/familias están activas, buscar y descargar documentos ya scrapeados.
- **Fuera de alcance:** multi-usuario con roles/permisos, self-service de API keys (se siguen creando por CLI, sin cambios), notificaciones push, edición de contenido de scrapers (solo `family_params`).

## Arquitectura

- **Proyecto separado** `frontend/`, SPA construida con **Vite + React + TypeScript**. No se acopla al proceso de FastAPI; se sirve como build estático (Nginx, MinIO/S3 + CDN, o cualquier hosting estático) apuntando a la API vía `VITE_API_BASE_URL`.
- **Estilos/componentes:** Tailwind CSS + shadcn/ui.
- **Routing:** React Router. Rutas: `/login`, `/` (overview), `/sources`, `/runs`, `/runs/:id`, `/documents`.
- **Data fetching:** `@tanstack/react-query` para cache y refetch. Los runs en estado `pending`/`running` usan `refetchInterval` (4s) hasta alcanzar un estado terminal (`success`/`error`/`cancelled`); se detiene automáticamente al llegar a un estado terminal.
- **Cliente API** (`src/api/client.ts`): wrapper de `fetch` que:
  - Agrega el header de API key (mismo mecanismo que `require_api_key` en `api/deps.py`) a cada request.
  - Lee la base URL de `VITE_API_BASE_URL`.
  - En un 401, limpia la key guardada y redirige a `/login`.
  - Propaga el `detail` de errores 4xx/5xx del backend hacia el componente que hizo la llamada, para mostrarlo en la UI.
- **Autenticación:** reutiliza el modelo de API key existente del backend, sin cambios en el backend.
  - `/login`: campo para pegar la API key + botón "Entrar".
  - Al enviar, se hace un `GET /source-families` de prueba con esa key. Si responde 200, se guarda en `localStorage` (`iurisync_api_key`) y se redirige a `/`.
  - Si responde 401, se muestra "API key inválida".
  - `AuthContext` (React Context) expone `apiKey`, `login(key)`, `logout()`. Rutas protegidas (todo excepto `/login`) redirigen a `/login` si no hay key guardada.

## Pantallas

### Login (`/login`)
Formulario de un solo campo (API key) + botón "Entrar". Sin registro ni recuperación — las keys se crean por CLI (`core.manage create-api-key`) y se comparten manualmente al equipo.

### Overview (`/`)
- Tarjetas resumen: fuentes activas (total), runs de las últimas 24h agrupados por estado (pending/running/success/error), documentos descargados hoy y en los últimos 7 días.
- Tabla de los últimos 5 runs con link a su detalle.
- Botón "Nuevo run" que abre el mismo modal usado en `/runs`.
- Datos derivados client-side a partir de `GET /runs?limit=...` y `GET /documents?limit=...` — no requiere nuevos endpoints de agregación en el backend.

### Fuentes (`/sources`)
- Tabla: nombre, familia (`family_key`), estado activo/inactivo, acciones.
- Filtros: `family_key` (select poblado desde `GET /source-families`) y `active` (sí/no/todos). Paginación con `limit`/`offset`.
- Modal "Nueva fuente" → `POST /sources`: familia (select), nombre (texto), `family_params` (editor de texto plano validado como JSON antes de enviar), activo (checkbox, default true).
- Edición inline: toggle de `active` y botón "Editar parámetros" (mismo editor JSON) → ambos vía `PATCH /sources/{id}`.
- Manejo de errores: si `POST /sources` devuelve 400 (familia desconocida), mostrar el mensaje del backend tal cual bajo el campo de familia.

### Runs (`/runs`)
- Tabla: id, `triggered_by`, badge de estado con color (pending=gris, running=azul, success=verde, error=rojo, cancelled=amarillo), `fini`/`ffin`, `created_at`.
- Filtro por estado (`status_filter`). Paginación con `limit`/`offset`.
- Botón "Nuevo run" → modal: multi-select de fuentes activas (vacío = todas las activas), rango de fechas opcional (`fini`/`ffin`) → `POST /runs`. Al crear, navega a `/runs/:id` del run recién creado.
- Filas en estado no terminal hacen polling (ver Arquitectura) para reflejar cambios de estado sin recargar la página.

### Detalle de Run (`/runs/:id`)
- Encabezado: estado (con el mismo polling mientras no sea terminal), `fini`/`ffin`, `started_at`/`finished_at`, `cancel_requested`.
- Tabla de fuentes del run (`GET /runs/{id}/sources`): fuente, estado, `docs_new`, `docs_errors`, `error_message` (si existe, en una celda expandible).
- Botón "Cancelar run" (`POST /runs/{id}/cancel`), visible solo si el estado no es terminal. Tras click, deshabilita el botón y muestra "Cancelación solicitada" (el run sigue su curso hasta que el worker respete el `stop_event`, no es instantáneo).

### Documentos (`/documents`)
- Tabla paginada (`GET /documents`, respuesta `{items, total, limit, offset}`).
- Filtros: fuente (`source_id`), familia (`family_key`), tipo (`tipo`), búsqueda de texto en título (`title`).
- Columnas: título, tipo, sección, fecha providencia (`f_providencia`), tamaño (`file_size_bytes` formateado a KB/MB), botón "Descargar".
- "Descargar" navega (nueva pestaña) a `GET /documents/{id}/download`, que redirige a una URL presignada de S3/MinIO — no requiere manejo especial en el frontend más allá de abrir el link.

## Manejo de errores

- Errores de red o 5xx: banner de error genérico con opción de reintentar (react-query `retry` + botón manual).
- Errores de validación (4xx con `detail`): se muestran inline junto al campo o acción relevante, usando el texto de `detail` tal cual devuelve el backend (ya están en español en los mensajes existentes, ej. "Familia técnica desconocida: X").
- 401 en cualquier momento (key revocada/inválida): logout automático + redirect a `/login`.

## Testing

- **Unitario/componentes:** Vitest + React Testing Library para componentes de formulario (validación de `family_params` como JSON, validación de rango de fechas) y para el cliente API (manejo de 401, propagación de `detail`).
- **Mocking de API:** `msw` (Mock Service Worker) para simular las respuestas de los 4 routers (`sources`, `runs`, `documents`, `source-families`) sin depender del backend real corriendo.
- **E2E (opcional, fuera del plan inicial):** Playwright cubriendo el flujo login → crear fuente → disparar run → ver detalle → buscar documento. Se deja como posible seguimiento, no bloqueante para el MVP.

## Variables de entorno

- `VITE_API_BASE_URL`: URL base de la API (ej. `http://localhost:8000` en desarrollo).

## Fuera de alcance (seguimiento futuro)

- Multi-usuario con roles y permisos diferenciados.
- WebSockets/streaming en vivo para runs (se usa polling en su lugar — ver decisión en la sesión de brainstorming).
- Gráficos históricos/analítica avanzada más allá de los contadores del Overview.
- Internacionalización (la UI se construye directamente en español, como el resto del backend).
