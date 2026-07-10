# Backend SaaS de scraping de fuentes — Diseño

Fecha: 2026-07-10

## Contexto y objetivo

Existe un proyecto de escritorio (`C:\Users\asant\WebScrapping_Fuentes`, alias IURISYNC) que descarga documentos de ~13 familias de fuentes (Corte Constitucional, Corte Suprema, JEP, SAMAI —Tribunales Administrativos—, Rama Judicial —Tribunales Superiores y Juzgados—, CNDJ, ADR, ADRES, ANE, ANH), los sube a Google Drive y registra cada descarga en Google Sheets, todo disparado manualmente o vía Tarea Programada de Windows desde una GUI de tkinter.

El objetivo de este diseño es un **backend nuevo, tipo SaaS de uso interno**, que:
- Reutilice la lógica de scraping ya construida y probada en `scrappers/`, `models/models.py` y `downloader.py`.
- Clasifique cada fuente por **familia técnica** (la implementación de scraping que comparte), para que agregar una fuente nueva dentro de una familia existente sea configuración, no código.
- Descargue archivos y los almacene junto con toda su metadata de forma estructurada en **PostgreSQL**, reemplazando SQLite + Google Sheets.
- Se exponga vía una **API REST** (FastAPI), con corridas de scraping ejecutadas en segundo plano (Celery + Redis), disparables manualmente o por horario.

Explícitamente fuera de alcance en este ciclo: frontend/dashboard web (se diseñará por separado), multi-tenancy real (varios clientes externos), y despliegue en Linux/nube (el backend corre en Windows, conservando Word COM para conversión a RTF).

## Arquitectura general

Repo nuevo (`scrapper-avanzado`, este mismo directorio), con esta estructura:

```
scrapper-avanzado/
├── core/
│   ├── scrapers/        # adaptado de scrappers/ (familias + fuentes concretas)
│   ├── models.py        # RawDocModel (Pydantic), igual que hoy
│   ├── downloader.py     # adaptado de downloader.py (GET/POST/jwt_indirect, WordConverter)
│   ├── storage.py       # cliente S3/MinIO (sube archivo, genera key, URL firmada)
│   └── db/              # modelos SQLAlchemy + repositorios
├── api/
│   ├── main.py          # app FastAPI
│   ├── routers/         # /sources, /runs, /documents, /health
│   └── deps.py          # auth por API key, sesión de DB
├── worker/
│   ├── celery_app.py    # config Celery (broker/backend = Redis)
│   ├── tasks.py         # orquestación + scrape_source_task
│   └── beat_schedule.py # programación diaria (reemplaza setup_scheduler.py)
├── alembic/              # migraciones de schema Postgres
├── tests/
└── docker-compose.yml    # Postgres + Redis + MinIO para desarrollo local
```

Dos procesos además de Postgres/Redis/MinIO: la API (uvicorn) y el/los worker(s) de Celery + Celery Beat. Ambos importan el mismo paquete `core/`.

**Nota Celery en Windows:** el pool `prefork` (basado en `fork`) no existe en Windows; el worker arranca con `--pool=solo` (single-process) o `--pool=threads`. Como los scrapers de SAMAI y Rama Judicial ya usan sus propios `ThreadPoolExecutor` internos, `--pool=solo` con varias tareas Celery encoladas es razonable para empezar.

El proyecto de escritorio (`WebScrapping_Fuentes`) queda intacto y funcionando en paralelo mientras este backend madura; no se toca ni se retira nada de ese repo.

## Modelo de familia técnica

Hoy esto existe implícitamente en el código (SAMAI y Rama Judicial son una sola clase parametrizada que cubre decenas de tribunales), pero está hardcodeado en Python (`scrappers/__init__.py` arma el diccionario `SCRAPERS` a mano). Se hace explícito y dirigido por datos:

**`source_families`** (tabla de referencia, pocas filas, casi estática)

| campo | ejemplo |
|---|---|
| `key` | `samai`, `rama_judicial`, `constitucional`, `corte_suprema`, `jep`, `cndj`, `adr`, `adres`, `ane`, `anh` |
| `display_name` | "SAMAI (Tribunales Administrativos)" |
| `description` | qué sitio/tecnología cubre |

Cada `key` mapea, en código, a una clase adaptadora que implementa `BaseScrapper` — la lógica ya escrita en `scrappers/samai.py`, `rama_judicial.py`, etc., prácticamente sin tocar. El mapeo vive en un registro Python simple: `FAMILY_REGISTRY: dict[str, Type[BaseScrapper]]`.

**`sources`** (las fuentes concretas configurables — hoy son las ~90 entradas del dict `SCRAPERS`)

| campo | ejemplo |
|---|---|
| `id` | PK |
| `family_key` | FK → `source_families.key`, ej. `samai` |
| `name` | "Tribunal Administrativo de Cundinamarca" |
| `family_params` | JSONB, ej. `{"corp_code": "2500023"}` — los kwargs que hoy se pasan al constructor |
| `active` | bool — habilita/deshabilita sin tocar código |
| `created_at` | TIMESTAMPTZ |

Al disparar una corrida, el worker lee la fila de `sources`, busca la clase por `family_key` en `FAMILY_REGISTRY`, la instancia con `**family_params`, y llama `.scrap()` — el contrato `BaseScrapper` actual, sin cambios.

**Por qué cumple el objetivo de evitar duplicar desarrollos:** agregar un nuevo Tribunal Administrativo (ya cubierto por SAMAI) pasa a ser un `INSERT` en `sources`, no código nuevo. Solo se escribe una clase/familia nueva cuando aparece un sitio con tecnología genuinamente distinta. Una migración inicial puebla `sources` con las ~90 entradas que hoy están en el dict `SCRAPERS`.

## Modelo de datos PostgreSQL

**`runs`** — una corrida de scraping

| campo | tipo |
|---|---|
| `id` | PK |
| `triggered_by` | `manual` \| `scheduled` |
| `fini`, `ffin` | DATE |
| `status` | `pending`\|`running`\|`completed`\|`failed`\|`cancelled` |
| `cancel_requested` | BOOLEAN DEFAULT false |
| `started_at`, `finished_at` | TIMESTAMPTZ |
| `created_at` | TIMESTAMPTZ |

**`run_sources`** — resultado por fuente dentro de una corrida

| campo | tipo |
|---|---|
| `id` | PK |
| `run_id` | FK → `runs.id` |
| `source_id` | FK → `sources.id` |
| `status` | `pending`\|`running`\|`completed`\|`failed` |
| `docs_new`, `docs_errors` | INT |
| `error_message` | TEXT, nullable (error a nivel de fuente completa, ej. sitio caído) |
| `started_at`, `finished_at` | TIMESTAMPTZ |

**`run_errors`** — detalle granular de errores por documento dentro de una fuente

| campo | tipo |
|---|---|
| `id` | PK |
| `run_source_id` | FK → `run_sources.id` |
| `message` | TEXT |
| `context` | JSONB (ej. título/URL del documento que falló) |
| `occurred_at` | TIMESTAMPTZ |

**`documents`** — reemplazo estructurado de la tabla `downloaded` de `memory.db` + las filas de Google Sheets, con todos los campos de `RawDocModel`

| campo | tipo |
|---|---|
| `id` | PK |
| `doc_id` | TEXT UNIQUE — mismo hash SHA1 de hoy (`make_doc_id`), clave de deduplicación |
| `source_id` | FK → `sources.id` |
| `run_source_id` | FK → `run_sources.id` (qué corrida lo descargó) |
| `title`, `tipo`, `seccion`, `especialidad`, `magistrado`, `detalle` | TEXT, nullable donde aplica |
| `f_public`, `f_providencia` | DATE, nullable |
| `source_url` | TEXT (URL original) |
| `storage_bucket`, `storage_key` | TEXT (ubicación en object storage) |
| `content_type`, `file_extension`, `file_size_bytes` | metadata del archivo |
| `converted_format` | TEXT, nullable (`rtf`/`rtf_word` si se convirtió) |
| `downloaded_at` | TIMESTAMPTZ |

**`api_keys`**

| campo | tipo |
|---|---|
| `id` | PK |
| `name` | TEXT |
| `key_hash` | TEXT UNIQUE (nunca en claro) |
| `active` | BOOLEAN |
| `last_used_at` | TIMESTAMPTZ, nullable |
| `created_at` | TIMESTAMPTZ |

Índices clave: `documents(source_id, f_public)`, `run_sources(run_id)`, `sources(family_key)`.

Migraciones de schema vía **Alembic** (reemplaza el mecanismo casero de `_migrations` en `db/memory.py`).

Con esto, `memory.db` (SQLite) y Google Sheets quedan completamente reemplazados: deduplicación, metadata estructurada e historial de corridas viven todos en Postgres.

## Flujo de ejecución

**Disparo**
- Manual: `POST /runs` (body opcional: `source_ids`, `fini`, `ffin`) → crea fila en `runs` (`status=pending`) y devuelve `202` con `run_id` de inmediato (no bloquea).
- Programado: Celery Beat dispara diariamente una tarea equivalente, con `triggered_by=scheduled`.

**Orquestación** (reemplaza el for-loop secuencial de `runner.py`)
1. Una tarea Celery orquestadora crea una fila en `run_sources` (`status=pending`) por cada fuente activa en alcance, y encola una tarea Celery por fuente (`scrape_source_task(run_source_id)`) usando un `chord` de Celery para saber cuándo cerrar el `run`.
2. Cada `scrape_source_task` resuelve la familia, instancia el adaptador, marca `run_sources.status=running`, y llama `scraper.scrap(fini, ffin)` — mismo contrato `BaseScrapper`.
3. Por cada `RawDocModel`: calcula `doc_id` → si existe en `documents`, se salta. Si es nuevo: `downloader.download()` a un archivo temporal → conversión si aplica → sube a object storage bajo la misma jerarquía de hoy (`{source}/{f_public}/{tipo}/{filename}{ext}` como *key*) → inserta en `documents` con toda la metadata + referencia de storage → borra el temporal local.
4. Errores por documento se registran en `run_errors` y no abortan la fuente completa (igual que hoy). Al terminar, `run_sources` pasa a `completed`/`failed` con sus contadores.
5. Cuando todas las `run_sources` de un `run` llegan a estado terminal, el callback del `chord` cierra el `run` (`completed`, con detalle de fallas por fuente visible en `run_sources`/`run_errors`).

**Progreso:** sin GUI todavía, se consulta vía `GET /runs/{id}` y `GET /runs/{id}/sources` leyendo directo de Postgres (reemplaza los callbacks `on_progress`/`on_new_doc`/`on_stats` de hoy). Push en vivo (SSE) queda para cuando se diseñe el frontend.

**Cancelación:** se reemplaza el `stop_event` en memoria por el flag `cancel_requested` en `runs`, seteado por `POST /runs/{id}/cancel`; cada tarea lo chequea entre documentos.

**Se elimina del flujo:** las notificaciones toast de Windows (`winotify`) no aplican a un proceso de servidor — se descartan en esta fase.

## API / Endpoints

Todos los endpoints requieren header `X-API-Key`, salvo `/health`. JSON, errores en shape estándar de FastAPI, paginación `limit`/`offset` + `total`.

**Fuentes y familias**

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/source-families` | Lista familias técnicas disponibles |
| GET | `/sources` | Lista fuentes configuradas (filtros: `family_key`, `active`) |
| POST | `/sources` | Crea una fuente nueva dentro de una familia existente |
| PATCH | `/sources/{id}` | Activa/desactiva o ajusta `family_params` |

**Corridas**

| Método | Ruta | Qué hace |
|---|---|---|
| POST | `/runs` | Dispara una corrida → `202` + `run_id` |
| GET | `/runs` | Lista corridas (filtros: `status`, rango de fechas) |
| GET | `/runs/{id}` | Detalle + estado agregado |
| GET | `/runs/{id}/sources` | Desglose por fuente |
| POST | `/runs/{id}/cancel` | Marca `cancel_requested` |

**Documentos**

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/documents` | Búsqueda/listado (filtros: `source_id`, `family_key`, `tipo`, rango `f_public`, texto en `title`) |
| GET | `/documents/{id}` | Metadata completa |
| GET | `/documents/{id}/download` | Redirige a URL firmada temporal del object storage |

**Salud**

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/health` | Liveness/readiness (DB, Redis, storage) — sin auth |

**Gestión de API keys:** se hace vía CLI (`python -m core.manage create-api-key --name "..."`), no vía endpoint — evita que una key administre keys.

## Manejo de errores

| Tipo | Ejemplo | Tratamiento |
|---|---|---|
| Documento aún no disponible | `FileNotFoundError` de SAMAI | Se salta en silencio, no cuenta como error |
| Falla de descarga de un documento | Timeout HTTP, error de conversión | Reintento (3 intentos en `Downloader`); si persiste, error puntual en `run_errors` y se sigue con el resto |
| Falla de todo el `scrap()` de una fuente | Sitio caído, HTML cambió | Reintento a nivel de tarea Celery (backoff); si persiste, esa `run_source` pasa a `failed`, no aborta las demás fuentes |
| Falla al subir a object storage | S3/MinIO no responde | Reintento de subida; si falla definitivo, cuenta como error y el temporal se limpia igual |
| Falla catastrófica de orquestación | Sin conexión a Postgres/Redis | El `run` completo pasa a `failed` |

Un `run` se marca `completed` aunque algunas fuentes hayan fallado — el detalle vive en `run_sources`/`run_errors`.

**Idempotencia real:** el chequeo de `doc_id` antes de descargar es una optimización; la garantía contra duplicados es el `UNIQUE` en `documents.doc_id` con `ON CONFLICT DO NOTHING` al insertar, cubriendo reintentos o corridas solapadas.

**Word COM:** se mantiene el fallback a `pypdf` ya existente. Con el worker en `--pool=solo` no hay concurrencia real dentro del proceso, así que una sola instancia de Word COM por worker es segura.

**Logging:** se mantiene log a archivo/stdout para operación, pero la fuente de verdad para historial y errores pasa a ser Postgres (`run_sources`, `run_errors`), consultable vía API.

## Plan de testing

Hoy el proyecto de escritorio no tiene test suite; este backend lo establece desde el inicio.

- **Unitarios (`core/`):** adaptadores de familia (SAMAI, Rama Judicial + un par de standalone) probados con respuestas HTTP grabadas/mockeadas — cubrir la familia cubre todas sus fuentes, no se prueba cada una de las ~90 individualmente. `downloader.py` (GET/POST/`jwt_indirect` mockeados, reintentos, fallback de conversión — Word COM en sí no se prueba en CI, solo el fallback a `pypdf`). `doc_id`/dedup como función pura. `storage.py` contra MinIO local o mocks.
- **Integración con Postgres real:** repositorios (inserción con `ON CONFLICT`, transiciones de estado) contra Postgres de test con migraciones de Alembic aplicadas.
- **API:** `TestClient`/`httpx.AsyncClient` de FastAPI contra DB de test — auth, formas de request/response, paginación, `202` al disparar run, `/cancel`.
- **Worker/orquestación:** Celery en modo *eager* para la lógica de orquestación sin broker real; pruebas de integración con el stack completo (`docker-compose`) contra un sitio mockeado (no los sitios reales) validando el pipeline scrape→dedup→descarga→conversión→subida→persistencia.
- **Explícitamente fuera de alcance:** pruebas en vivo contra los sitios reales en CI (frágil, riesgo de bloqueo de IP); cobertura exhaustiva por cada una de las ~90 fuentes configuradas.
- **CI:** GitHub Actions levantando `docker-compose` (Postgres/Redis/MinIO), corriendo el set anterior salvo Word COM, que queda como checklist manual en la máquina Windows real de destino.

## Decisiones de alcance (resumen)

| Decisión | Resultado |
|---|---|
| Modelo | Mono-tenant, uso interno |
| Alcance de este diseño | Backend + API (frontend queda para otro ciclo) |
| Drive/Sheets | Reemplazados totalmente por PostgreSQL |
| Archivos | Object storage (S3/MinIO) |
| Disparo de corridas | Manual (API) + programado (Celery Beat) |
| Cola de tareas | Celery + Redis |
| SO del backend | Windows (se conserva Word COM para RTF) |
| Auth | Sí, API Key estática |
| Ubicación | Repo nuevo (`scrapper-avanzado`), reutilizando `scrappers/`, `models/`, `downloader.py` de `WebScrapping_Fuentes` como base |
