---
name: run-iurisync
description: Build, run, and drive IURISYNC (FastAPI backend + Celery worker + Vite/React frontend). Use when asked to start the backend or frontend, run the test suites, seed sources, register a user, or interact with the running app end-to-end (login, trigger a scrape run, watch progress, browse/download documents, screenshot the UI).
---

IURISYNC is a Python/FastAPI + Celery backend (repo root) paired with a
Vite/React frontend (`frontend/`). It's driven end-to-end with a small
Playwright script, `.claude/skills/run-iurisync/driver.mjs`, that registers
(or logs in) with a username and password, triggers a real scrape run
against a live source, polls the run to completion, and downloads a
resulting document — the same path a human user takes through the UI. All
paths below are relative to the repo root.

**Verified on:** native Windows (Git Bash + PowerShell), not a Linux
container — commands below use that shell. Docker Desktop must be running
for Postgres/Redis/MinIO.

## Prerequisites

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
cd frontend && npm install && cd ..
```

The driver itself lives in its own tiny npm package (kept separate from
the product's `frontend/` deps since it's agent tooling, not app code):

```bash
cd .claude/skills/run-iurisync
npm install                      # installs playwright
npx playwright install chromium  # downloads the browser binary
cd ../../..
```

## Setup

```bash
copy .env.example .env                     # backend env (DB/Redis/S3 URLs)
docker compose up -d                       # Postgres, Redis, MinIO
docker compose exec postgres psql -U iurisync -d iurisync -c "CREATE DATABASE iurisync_test;"
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m core.seed          # populates source_families/sources
curl -s -X POST http://localhost:8000/auth/register -H "Content-Type: application/json" -d '{"username":"smoke-test","password":"SmokeTest123","invite_code":"changeme"}'
```

The last command registers a `smoke-test` user with password `SmokeTest123`
(using the default invite code, `REGISTRATION_CODE=changeme` in
`.env.example`/`core/config.py`) — only needs running once; if the user
already exists, just log in instead in the driver. The frontend's
`frontend/.env` needs `VITE_API_BASE_URL=http://localhost:8000` (already
the checked-in default).

## Build

No separate build step for local running — `uvicorn --reload` and `vite`
both run from source. (`docker build --target api|worker|beat .` exists
for deployment images; see README.md, not needed to drive the app locally.)

## Run (agent path)

Start the three long-running processes in the background, each in its own
shell (PowerShell `Start-Process` or Bash `&` both work — the important
part is they must all be up before driving the UI):

```bash
.venv/Scripts/python -m uvicorn api.main:app --port 8000 &
.venv/Scripts/python -m celery -A worker.celery_app worker --pool=solo --loglevel=info &
(cd frontend && npm run dev) &
```

Wait for both HTTP endpoints to actually answer before driving anything:

```bash
timeout 30 bash -c 'until curl -sf http://localhost:8000/health >/dev/null; do sleep 1; done'
timeout 30 bash -c 'until curl -sf http://localhost:5173/ >/dev/null; do sleep 1; done'
```

Then drive it with the Playwright script (Node's built-in test runner
isn't involved — this is a plain script, run directly):

```bash
cd .claude/skills/run-iurisync
node driver.mjs flow "smoke-test" "SmokeTest123" "Corte Constitucional" "2024-01-01" "2024-01-31"
```

This performs the full user flow in one shot: log in → open "Nuevo run" →
check the named source → set the date range → submit → poll the run
detail page (re-navigating every 3s) until it reaches a terminal state →
open Documentos → download the first available file. Screenshots and any
downloaded file land in `.claude/skills/run-iurisync/screenshots/`.
Console errors from the page (if any) print inline as `[console error] …`.

| command | what it does |
|---|---|
| `node driver.mjs login <username> <password>` | Log in only, screenshot the dashboard |
| `node driver.mjs screenshot <path> <name>` | Navigate to a frontend route and screenshot it (e.g. `/sources sources-page`) |
| `node driver.mjs flow <username> <password> [sourceName] [fini] [ffin]` | Full login → trigger run → watch → documents flow (defaults: `Corte Constitucional`, `2024-01-01`..`2024-01-31`) |

Pick `sourceName` from whatever's seeded and active — `Corte Constitucional`
is a good default: single source, fast real scrape, known-reliable.

## Run (human path)

`uvicorn --reload` on :8000, `celery worker` in its own terminal, `npm run
dev` on :5173 (prints the URL). Ctrl-C each to stop. Log in at
`http://localhost:5173/login` with the username/password registered above,
or register a new account at `/register`.

## Test

```bash
.venv/Scripts/pytest -v          # backend: 90 passed, 1 pre-existing failure (see Gotchas)
cd frontend && npm test -- --run # frontend: 16 files / 63 tests passed
```

---

## Gotchas

- **The source picker in "Nuevo run" is a checkbox list, not a `<select>`.**
  Each source renders as `<input type="checkbox" aria-label="{source.name}">`
  (see `frontend/src/pages/RunsPage.tsx`). Use
  `page.getByRole("checkbox", { name: sourceName, exact: true }).check()`.
  Leaving all checkboxes unchecked triggers a run against *every* active
  source — fine for the real app, too slow/broad for a smoke test.
- **`test_migrations.py::test_alembic_upgrade_head_creates_all_tables` fails
  on this Windows shell** with `FileNotFoundError: [WinError 2]` — it
  shells out to the `alembic` executable by bare name and the subprocess
  call can't resolve it in this environment. Pre-existing, unrelated to
  app code; the 90 other backend tests are unaffected.
- **Real external scrapes, not mocks.** The driver's `flow` command hits
  the actual government site behind whatever `family_key` the chosen
  source uses. A completed run for `Corte Constitucional` over one month
  (2024-01) pulled 203 real documents in well under a minute — but any
  family could be slow or briefly down; the driver's `watchRun` polls for
  60s by default and just screenshots whatever state it's in at timeout,
  it doesn't hang forever.
- **Downloads need `acceptDownloads: true` on the browser context** (set
  in `driver.mjs`) or Playwright's `waitForEvent("download", ...)` never
  fires and the click just hangs until its own timeout.
