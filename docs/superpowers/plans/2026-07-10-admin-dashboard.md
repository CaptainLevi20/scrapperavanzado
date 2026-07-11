# Dashboard Administrativo IURISYNC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a React admin dashboard so the internal Avance Jurídico team can manage scraping sources, trigger/monitor runs, and search/download documents without touching the API directly.

**Architecture:** SPA (`frontend/`, Vite + React + TypeScript) fully separate from the Python backend, calling it over HTTP with an API key stored in `localStorage`. React Router for navigation, `@tanstack/react-query` for data fetching/caching/polling, Tailwind CSS + shadcn/ui for styling. One small backend change (CORS) is required so the browser can call the API and read presigned download responses cross-origin.

**Tech Stack:** Vite, React 18+, TypeScript, React Router v6+, `@tanstack/react-query` v5, Tailwind CSS v4, shadcn/ui, Vitest, `@testing-library/react`, MSW (Mock Service Worker). Backend: FastAPI `CORSMiddleware`, boto3 bucket CORS.

## Global Constraints

- Design spec: `docs/superpowers/specs/2026-07-10-admin-dashboard-design.md` — read it for rationale; this plan is the executable breakdown of it.
- Frontend lives entirely in `frontend/` at the repo root, as its own npm project (own `package.json`, `node_modules`). Never mix frontend deps into the Python backend's `requirements.txt`.
- All HTTP calls to the backend go through `frontend/src/api/client.ts`'s `apiFetch`/`buildQuery`. No component calls `fetch` directly except the binary-download path in `frontend/src/api/documents.ts` (documented exception — JSON parsing doesn't apply to file downloads).
- The API key is stored under the `localStorage` key `iurisync_api_key` and sent as the `X-API-Key` header (matches `api/deps.py`'s `require_api_key`, alias `"X-API-Key"`).
- All UI copy is in Spanish, matching the rest of the backend (error messages, docs, README).
- Run status values are exactly `"pending"`, `"running"`, `"completed"` (source: `worker/tasks.py` — there is no `"error"`/`"cancelled"` run status; only `"completed"` is terminal). Run-source status values are exactly `"pending"`, `"running"`, `"completed"`, `"failed"`.
- Backend base URL comes from `VITE_API_BASE_URL` (Vite env var), defaulting to `http://localhost:8000` when unset.
- Testing: Vitest + `@testing-library/react` + MSW. No test may hit a real network endpoint — always mock via `frontend/src/test/server.ts`.
- Do not modify Python backend files except `core/config.py`, `api/main.py`, `.env.example`, `tests/test_cors.py`, `tests/test_storage.py` in Task 1 (CORS) — no other backend changes are in scope. `core/storage.py` is read but not modified (see Task 1's "Important note" on MinIO CORS).

**Cross-cutting correction (discovered during Task 10, fixed in commit `09746ba`, not tied to any single numbered task):** no task brief ever ran `npx tsc -b` (full TypeScript project type-check) as a pass/fail gate — only Vitest. This let two real gaps slip through silently for several tasks:
1. `frontend/src/main.tsx` kept Vite's scaffolded `import App from './App.tsx'` (default import) even after Task 2 changed `App.tsx` to a named-only export (`export function App()`) to satisfy its own test's `import { App }`. Every Vitest test imports `{ App }` directly and never exercises `main.tsx`, so this was invisible to the test suite — but the actual running app (`npm run dev` / production build) would have had `App === undefined` at runtime. Fixed by changing `main.tsx`'s import to `import { App } from './App.tsx'` (do not add a default export back to `App.tsx` — many test files already depend on the named export).
2. `buildQuery`'s parameter type (`Record<string, string | number | boolean | undefined>`, from Task 4) requires an explicit index signature on any interface passed to it. `ListSourcesParams`/`ListRunsParams`/`ListDocumentsParams` (Task 5) lacked one. Fixed by adding `[key: string]: string | number | boolean | undefined;` as the last member of each of the three interfaces.

If a later task's implementer runs `tsc -b` (recommended, since Task 15's final `npm run build` step depends on it passing) and finds new errors, fix them the same way: minimal, targeted, and only touching what's necessary — don't introduce `any` to silence errors.

---

## File Structure

**Backend (modified):**
- `core/config.py` — add `cors_origins` setting.
- `api/main.py` — add `CORSMiddleware`.
- `.env.example` — document `CORS_ORIGINS`.
- `tests/test_cors.py` — new test file.
- `tests/test_storage.py` — extended with a test confirming MinIO's default CORS behavior (no `core/storage.py` production code change — see Task 1's "Important note").

**Frontend (new `frontend/` project):**
- `frontend/package.json`, `vite.config.ts`, `tsconfig.json`, `tsconfig.node.json`, `index.html`, `.gitignore`, `.env.example`, `components.json` (shadcn) — project config.
- `frontend/src/main.tsx`, `App.tsx`, `index.css` — entrypoint.
- `frontend/src/api/types.ts` — TypeScript types mirroring `api/schemas.py`.
- `frontend/src/api/client.ts` — fetch wrapper, `ApiError`, key storage, `buildQuery`, unauthorized-handler registration.
- `frontend/src/api/sourceFamilies.ts`, `sources.ts`, `runs.ts`, `documents.ts` — one file per backend resource.
- `frontend/src/auth/AuthContext.tsx`, `ProtectedRoute.tsx` — API-key session state and route guarding.
- `frontend/src/components/layout/AppLayout.tsx`, `Sidebar.tsx` — page chrome.
- `frontend/src/components/StatusBadge.tsx`, `ErrorBanner.tsx` — shared small components used across pages.
- `frontend/src/components/ui/*` — shadcn/ui generated primitives (button, dialog, input, select, checkbox, label, card).
- `frontend/src/lib/formatters.ts` — byte/date formatting helpers.
- `frontend/src/pages/LoginPage.tsx`, `OverviewPage.tsx`, `SourcesPage.tsx`, `RunsPage.tsx`, `RunDetailPage.tsx`, `DocumentsPage.tsx` — one file per screen from the design spec.
- `frontend/src/test/setup.ts`, `server.ts` — Vitest + MSW test infrastructure.
- `frontend/README.md` — setup/run instructions for the frontend.

---

### Task 1: Backend CORS support for the frontend origin

**Files:**
- Modify: `core/config.py`
- Modify: `api/main.py`
- Modify: `.env.example`
- Test: `tests/test_cors.py` (new)
- Test: `tests/test_storage.py` (extend, no production code change — see the "Important note" below)

**Interfaces:**
- Consumes: `core.config.get_settings()` (existing), `tests/conftest.py`'s `api_client` fixture and `TEST_S3_BUCKET` constant (existing).
- Produces: `Settings.cors_origins: str` (comma-separated origins), used by `api/main.py`. Later frontend tasks assume the browser can call the API from `http://localhost:5173` and read presigned-download responses without a CORS error — this task is what makes that true.

**Important note (discovered during implementation, not in the original design):** open-source MinIO does **not** implement per-bucket CORS via the S3 API (`PutBucketCors`/`GetBucketCors` return `NotImplemented` — that's an AIStor/enterprise-only feature). MinIO only supports a server-wide `MINIO_API_CORS_ALLOW_ORIGIN` setting, which **defaults to `*`** (all origins) when unset. Since this project's `docker-compose.yml` doesn't set that variable, MinIO already answers presigned-URL requests with a permissive `Access-Control-Allow-Origin` header out of the box — no bucket-level application code is needed. Do **not** call `put_bucket_cors` in `core/storage.py`; instead, write a test that confirms this default behavior empirically (Steps 7-9 below).

- [ ] **Step 1: Write the failing CORS preflight test**

```python
# tests/test_cors.py
def test_options_preflight_allows_configured_frontend_origin(api_client):
    response = api_client.options(
        "/source-families",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-api-key",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_cors.py -v`
Expected: FAIL (405 or missing `access-control-allow-origin` header — no CORS middleware installed yet).

- [ ] **Step 3: Add the `cors_origins` setting**

In `core/config.py`, add one field to the `Settings` class (after `api_key_header`):

```python
    cors_origins: str = "http://localhost:5173"
```

- [ ] **Step 4: Wire `CORSMiddleware` into the app**

Replace the contents of `api/main.py` with:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import documents, health, runs, sources
from core.config import get_settings

app = FastAPI(title="IURISYNC Backend")

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in _settings.cors_origins.split(",")],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(sources.router)
app.include_router(runs.router)
app.include_router(documents.router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_cors.py -v`
Expected: PASS

- [ ] **Step 6: Document the new env var**

Append to `.env.example`:

```
CORS_ORIGINS=http://localhost:5173
```

- [ ] **Step 7: Ensure `ensure_bucket` in `core/storage.py` is unchanged**

`core/storage.py`'s `ensure_bucket` must stay exactly as it already is — it only creates the bucket if missing, nothing else:

```python
def ensure_bucket(bucket: str) -> None:
    client = _client()
    existing = [b["Name"] for b in client.list_buckets().get("Buckets", [])]
    if bucket not in existing:
        client.create_bucket(Bucket=bucket)
```

If an earlier attempt at this task added a `put_bucket_cors` call here, remove it — it fails against open-source MinIO with `ClientError: NotImplemented` on every call, which breaks `upload_file()` (and therefore every document download in the scraping pipeline). See the "Important note" above. `core/storage.py` is therefore not actually modified by this task — drop it from the Files list once this step is confirmed.

- [ ] **Step 8: Write a test confirming MinIO's default CORS behavior covers the frontend origin**

Append to `tests/test_storage.py`:

```python
def test_presigned_url_response_allows_cross_origin_read(tmp_path):
    from core.storage import presigned_url, upload_file

    file_path = tmp_path / "cors-check.txt"
    file_path.write_text("contenido de prueba")
    bucket, key = upload_file(file_path, "cors-check.txt", bucket=TEST_S3_BUCKET)
    url = presigned_url(bucket, key)

    response = requests.get(url, headers={"Origin": "http://localhost:5173"}, timeout=10)

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") in ("*", "http://localhost:5173")
```

This is not a red/green TDD step (there's no application code to write — the assertion documents and locks in MinIO's existing default behavior). Skip straight to Step 9.

- [ ] **Step 9: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_storage.py -v`
Expected: PASS (both the existing roundtrip test and the new CORS-header test). If it FAILS with a missing/mismatched `access-control-allow-origin` header, this project's MinIO deployment has `MINIO_API_CORS_ALLOW_ORIGIN` set to something other than the default `*` — stop and report BLOCKED rather than adding a `put_bucket_cors` call back (it will not work against open-source MinIO).

- [ ] **Step 10: Run the full backend suite**

Run: `.venv\Scripts\pytest -v` (requires `docker compose up -d`)
Expected: all tests pass (same count as before + 2 new tests)

- [ ] **Step 11: Commit**

```bash
git add core/config.py api/main.py .env.example tests/test_cors.py tests/test_storage.py
git commit -m "fix: rely on MinIO's default CORS behavior instead of unsupported put_bucket_cors"
```

---

### Task 2: Frontend scaffold — Vite + React + TypeScript + Vitest test pipeline

**Files:**
- Create (via CLI): `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/index.css`, `frontend/.gitignore`
- Create: `frontend/src/test/setup.ts`, `frontend/src/test/server.ts`
- Create: `frontend/.env.example`
- Test: `frontend/src/App.test.tsx`

**Interfaces:**
- Produces: `frontend/src/test/server.ts` exports `server` (an MSW `setupServer()` instance with no handlers registered yet) — every later frontend test imports this and calls `server.use(...)` for its own mocked routes. `frontend/vite.config.ts`'s `test` block (environment `jsdom`, `setupFiles: ["./src/test/setup.ts"]`) is the config every later test run relies on.

- [ ] **Step 1: Scaffold the Vite project**

Run (from the repo root):
```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
```
Expected: `frontend/` exists with `package.json`, `src/App.tsx`, `src/main.tsx`, `vite.config.ts`, `tsconfig.json`.

- [ ] **Step 2: Install routing and data-fetching dependencies**

Run (inside `frontend/`):
```bash
npm install react-router-dom @tanstack/react-query
```

- [ ] **Step 3: Install test dependencies**

Run (inside `frontend/`):
```bash
npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom msw
```

- [ ] **Step 4: Write the failing smoke test**

Create `frontend/src/App.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { App } from "./App";

describe("App", () => {
  it("renders without crashing", () => {
    render(<App />);
    expect(screen.getByText(/vite \+ react/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 5: Run test to verify it fails**

Run: `npx vitest run` (inside `frontend/`)
Expected: FAIL — `document is not defined` (no `jsdom` environment configured yet) or a config error, since Vitest isn't wired into `vite.config.ts` yet.

- [ ] **Step 6: Create the MSW test server (empty handlers for now)**

Create `frontend/src/test/server.ts`:

```ts
import { setupServer } from "msw/node";

export const server = setupServer();
```

- [ ] **Step 7: Create the Vitest setup file**

Create `frontend/src/test/setup.ts`:

```ts
import "@testing-library/jest-dom";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

- [ ] **Step 8: Wire Vitest into `vite.config.ts`**

Replace `frontend/vite.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
```

- [ ] **Step 9: Run test to verify it passes**

Run: `npx vitest run` (inside `frontend/`)
Expected: PASS (1 test)

- [ ] **Step 10: Add the `.env.example` for the frontend**

Create `frontend/.env.example`:

```
VITE_API_BASE_URL=http://localhost:8000
```

- [ ] **Step 11: Add `.gitignore` entries**

Ensure `frontend/.gitignore` (created by the Vite template) includes `node_modules`, `dist`, and add `.env` if not already present.

- [ ] **Step 12: Add a `test` script to `package.json`**

In `frontend/package.json`'s `"scripts"` block, add:
```json
"test": "vitest run"
```

- [ ] **Step 13: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold frontend project with Vite, React, TypeScript, and Vitest"
```

---

### Task 3: Tailwind CSS + shadcn/ui setup

**Files:**
- Modify: `frontend/vite.config.ts`, `frontend/src/index.css`, `frontend/tsconfig.json`
- Create (via CLI): `frontend/components.json`, `frontend/src/components/ui/button.tsx`, `dialog.tsx`, `input.tsx`, `label.tsx`

**Interfaces:**
- Produces: the `@/` path alias (resolves to `frontend/src`), used by every later import of `@/components/ui/*`. The shadcn primitives listed above (`Button`, `Dialog`+subcomponents, `Input`, `Label`) — later tasks (9, 11, 12) import `Button`, `Dialog`, `Input`, `Label` from these paths verbatim. Filters and checklists elsewhere in the app (Tasks 8–13) deliberately use plain native `<select>`/`<input type="checkbox">` elements instead of dedicated shadcn Select/Checkbox primitives — simpler for single-value filters, and it keeps this task's CLI install to only the components actually consumed later (no unused generated files).

**Note for the implementer:** the `shadcn` CLI's interactive prompts and exact flags have changed across versions. Run `npx shadcn@latest init --help` first if the flags below are rejected, and pick the non-interactive/default option for every prompt that still appears (style: default, base color: neutral/slate, CSS variables: yes).

- [ ] **Step 1: Install Tailwind CSS v4's Vite plugin**

Run (inside `frontend/`):
```bash
npm install tailwindcss @tailwindcss/vite
```

- [ ] **Step 2: Add the Tailwind plugin and the `@/` alias to `vite.config.ts`**

Replace `frontend/vite.config.ts`:

```ts
import path from "node:path";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
```

- [ ] **Step 3: Add the alias to `tsconfig.json`**

In `frontend/tsconfig.json`'s `compilerOptions`, add:
```json
"baseUrl": ".",
"paths": {
  "@/*": ["./src/*"]
}
```

- [ ] **Step 4: Import Tailwind in the global stylesheet**

Replace the contents of `frontend/src/index.css` with:
```css
@import "tailwindcss";
```

- [ ] **Step 5: Initialize shadcn/ui**

Run (inside `frontend/`):
```bash
npx shadcn@latest init -d -y
```
Expected: creates `frontend/components.json` and a `frontend/src/lib/utils.ts` (the `cn()` helper shadcn components depend on).

- [ ] **Step 6: Add the base components**

Run (inside `frontend/`):
```bash
npx shadcn@latest add button dialog input label -y
```
Expected: creates `frontend/src/components/ui/button.tsx`, `dialog.tsx`, `input.tsx`, `label.tsx`.

- [ ] **Step 7: Write the failing smoke test**

Create `frontend/src/components/ui/button.smoke.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Button } from "./button";

describe("shadcn/ui setup", () => {
  it("renders a Button component with Tailwind classes applied", () => {
    render(<Button>Probar</Button>);
    const button = screen.getByRole("button", { name: "Probar" });
    expect(button).toBeInTheDocument();
    expect(button.className.length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 8: Run test to verify it fails**

Run: `npx vitest run button.smoke` (inside `frontend/`)
Expected: FAIL if Step 5/6 weren't run yet in this order (module not found). If run after Step 6, it should already pass — in that case skip to Step 9 and note in the report that this step served as verification rather than a red/green cycle.

- [ ] **Step 9: Run the full test suite to verify everything passes**

Run: `npx vitest run` (inside `frontend/`)
Expected: PASS (all tests, including Task 2's smoke test)

- [ ] **Step 10: Commit**

```bash
git add frontend/
git commit -m "feat: set up Tailwind CSS and shadcn/ui base components"
```

---

### Task 4: API client core — types, fetch wrapper, error handling, key storage

**Files:**
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/api/client.ts`
- Test: `frontend/src/api/client.test.ts`

**Interfaces:**
- Consumes: `frontend/src/test/server.ts`'s `server` (Task 2).
- Produces (used by every later API/page task):
  - Types: `SourceFamily`, `Source`, `SourceCreateInput`, `SourceUpdateInput`, `RunStatus`, `RunSourceStatus`, `Run`, `RunCreateInput`, `RunSource`, `Document`, `PaginatedDocuments`.
  - `apiFetch<T>(path: string, options?: RequestInit): Promise<T>` — the only way to call the JSON API.
  - `buildQuery(params: Record<string, string | number | boolean | undefined>): string` — turns a params object into a `?a=b&c=d` query string, skipping `undefined` values.
  - `ApiError extends Error` with a `status: number` field.
  - `getStoredApiKey()`, `setStoredApiKey(key: string)`, `clearStoredApiKey()` — `localStorage` key `iurisync_api_key`.
  - `registerUnauthorizedHandler(handler: () => void): void` — called by `apiFetch` on a 401 response, after clearing the stored key. Task 6's `AuthProvider` registers a handler that clears its own React state.

- [ ] **Step 1: Write the types file**

Create `frontend/src/api/types.ts`:

```ts
export interface SourceFamily {
  key: string;
  display_name: string;
  description: string | null;
}

export interface Source {
  id: number;
  family_key: string;
  name: string;
  family_params: Record<string, unknown>;
  active: boolean;
}

export interface SourceCreateInput {
  family_key: string;
  name: string;
  family_params: Record<string, unknown>;
  active: boolean;
}

export interface SourceUpdateInput {
  active?: boolean;
  family_params?: Record<string, unknown>;
}

export type RunStatus = "pending" | "running" | "completed";
export type RunSourceStatus = "pending" | "running" | "completed" | "failed";

export interface Run {
  id: number;
  triggered_by: string;
  status: RunStatus;
  fini: string | null;
  ffin: string | null;
  cancel_requested: boolean;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface RunCreateInput {
  source_ids?: number[];
  fini?: string;
  ffin?: string;
}

export interface RunSource {
  id: number;
  run_id: number;
  source_id: number;
  status: RunSourceStatus;
  docs_new: number;
  docs_errors: number;
  error_message: string | null;
}

export interface Document {
  id: number;
  doc_id: string;
  source_id: number;
  title: string;
  tipo: string | null;
  seccion: string | null;
  f_public: string | null;
  f_providencia: string | null;
  storage_bucket: string;
  storage_key: string;
  content_type: string | null;
  file_size_bytes: number | null;
  downloaded_at: string;
}

export interface PaginatedDocuments {
  items: Document[];
  total: number;
  limit: number;
  offset: number;
}
```

- [ ] **Step 2: Write the failing client tests**

Create `frontend/src/api/client.test.ts`:

```ts
import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import {
  ApiError,
  apiFetch,
  buildQuery,
  clearStoredApiKey,
  getStoredApiKey,
  registerUnauthorizedHandler,
  setStoredApiKey,
} from "./client";

const BASE_URL = "http://localhost:8000";

describe("apiFetch", () => {
  beforeEach(() => {
    clearStoredApiKey();
    registerUnauthorizedHandler(() => {});
  });

  it("sends the stored API key as the X-API-Key header", async () => {
    setStoredApiKey("test-key");
    let receivedHeader: string | null = null;
    server.use(
      http.get(`${BASE_URL}/source-families`, ({ request }) => {
        receivedHeader = request.headers.get("x-api-key");
        return HttpResponse.json([]);
      })
    );

    await apiFetch("/source-families");

    expect(receivedHeader).toBe("test-key");
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

  it("clears the stored key and notifies the unauthorized handler on a 401", async () => {
    setStoredApiKey("bad-key");
    let notified = false;
    registerUnauthorizedHandler(() => {
      notified = true;
    });
    server.use(http.get(`${BASE_URL}/source-families`, () => new HttpResponse(null, { status: 401 })));

    await expect(apiFetch("/source-families")).rejects.toBeInstanceOf(ApiError);
    expect(getStoredApiKey()).toBeNull();
    expect(notified).toBe(true);
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

- [ ] **Step 3: Run tests to verify they fail**

Run: `npx vitest run client.test` (inside `frontend/`)
Expected: FAIL — `frontend/src/api/client.ts` doesn't exist yet.

- [ ] **Step 4: Implement the client**

Create `frontend/src/api/client.ts`:

```ts
const API_KEY_STORAGE_KEY = "iurisync_api_key";

export function getStoredApiKey(): string | null {
  return localStorage.getItem(API_KEY_STORAGE_KEY);
}

export function setStoredApiKey(key: string): void {
  localStorage.setItem(API_KEY_STORAGE_KEY, key);
}

export function clearStoredApiKey(): void {
  localStorage.removeItem(API_KEY_STORAGE_KEY);
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
  const apiKey = getStoredApiKey();
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (apiKey) headers.set("X-API-Key", apiKey);

  const response = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (response.status === 401) {
    clearStoredApiKey();
    unauthorizedHandler?.();
    throw new ApiError(401, "API key inválida o expirada");
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

- [ ] **Step 5: Run tests to verify they pass**

Run: `npx vitest run client.test` (inside `frontend/`)
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/api/client.test.ts
git commit -m "feat: add API client core (types, fetch wrapper, key storage)"
```

---

### Task 5: API resource functions (source families, sources, runs, documents)

**Files:**
- Create: `frontend/src/api/sourceFamilies.ts`
- Create: `frontend/src/api/sources.ts`
- Create: `frontend/src/api/runs.ts`
- Create: `frontend/src/api/documents.ts`
- Test: `frontend/src/api/sources.test.ts`
- Test: `frontend/src/api/runs.test.ts`
- Test: `frontend/src/api/documents.test.ts`

**Interfaces:**
- Consumes: `apiFetch`, `buildQuery` (Task 4), types from `frontend/src/api/types.ts` (Task 4).
- Produces: `fetchSourceFamilies()`; `fetchSources(params)`, `createSource(input)`, `updateSource(id, input)`; `fetchRuns(params)`, `fetchRun(id)`, `fetchRunSources(runId)`, `createRun(input)`, `cancelRun(id)`; `fetchDocuments(params)`, `fetchDocument(id)`. These are called directly by every page task (8–15) as `queryFn`/`mutationFn` for `@tanstack/react-query`.

- [ ] **Step 1: Write the failing sources tests**

Create `frontend/src/api/sources.test.ts`:

```ts
import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { clearStoredApiKey } from "./client";
import { createSource, fetchSources, updateSource } from "./sources";

const BASE_URL = "http://localhost:8000";

describe("sources API", () => {
  beforeEach(() => clearStoredApiKey());

  it("fetchSources sends filters as query params", async () => {
    let receivedUrl = "";
    server.use(
      http.get(`${BASE_URL}/sources`, ({ request }) => {
        receivedUrl = request.url;
        return HttpResponse.json([]);
      })
    );

    await fetchSources({ family_key: "constitucional", active: true, limit: 20, offset: 0 });

    expect(receivedUrl).toContain("family_key=constitucional");
    expect(receivedUrl).toContain("active=true");
  });

  it("createSource posts the payload and returns the created source", async () => {
    server.use(
      http.post(`${BASE_URL}/sources`, async ({ request }) => {
        const body = await request.json();
        return HttpResponse.json({ id: 1, ...(body as object) }, { status: 201 });
      })
    );

    const result = await createSource({
      family_key: "constitucional",
      name: "Corte Constitucional",
      family_params: {},
      active: true,
    });

    expect(result.id).toBe(1);
    expect(result.name).toBe("Corte Constitucional");
  });

  it("updateSource sends a PATCH to the source's id", async () => {
    let method = "";
    server.use(
      http.patch(`${BASE_URL}/sources/5`, ({ request }) => {
        method = request.method;
        return HttpResponse.json({ id: 5, family_key: "constitucional", name: "x", family_params: {}, active: false });
      })
    );

    const result = await updateSource(5, { active: false });

    expect(method).toBe("PATCH");
    expect(result.active).toBe(false);
  });
});
```

- [ ] **Step 2: Write the failing runs tests**

Create `frontend/src/api/runs.test.ts`:

```ts
import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { clearStoredApiKey } from "./client";
import { cancelRun, createRun, fetchRun, fetchRunSources, fetchRuns } from "./runs";

const BASE_URL = "http://localhost:8000";

describe("runs API", () => {
  beforeEach(() => clearStoredApiKey());

  it("fetchRuns sends the status filter as a query param", async () => {
    let receivedUrl = "";
    server.use(
      http.get(`${BASE_URL}/runs`, ({ request }) => {
        receivedUrl = request.url;
        return HttpResponse.json([]);
      })
    );

    await fetchRuns({ status_filter: "running", limit: 10, offset: 0 });

    expect(receivedUrl).toContain("status_filter=running");
  });

  it("fetchRun fetches a single run by id", async () => {
    server.use(
      http.get(`${BASE_URL}/runs/7`, () =>
        HttpResponse.json({
          id: 7,
          triggered_by: "manual",
          status: "running",
          fini: null,
          ffin: null,
          cancel_requested: false,
          started_at: null,
          finished_at: null,
          created_at: "2026-07-10T00:00:00Z",
        })
      )
    );

    const run = await fetchRun(7);

    expect(run.id).toBe(7);
    expect(run.status).toBe("running");
  });

  it("fetchRunSources fetches the run's sources", async () => {
    server.use(
      http.get(`${BASE_URL}/runs/7/sources`, () =>
        HttpResponse.json([{ id: 1, run_id: 7, source_id: 2, status: "completed", docs_new: 3, docs_errors: 0, error_message: null }])
      )
    );

    const runSources = await fetchRunSources(7);

    expect(runSources).toHaveLength(1);
    expect(runSources[0].source_id).toBe(2);
  });

  it("createRun posts optional source_ids and date range", async () => {
    let body: unknown;
    server.use(
      http.post(`${BASE_URL}/runs`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          { id: 1, triggered_by: "manual", status: "pending", fini: null, ffin: null, cancel_requested: false, started_at: null, finished_at: null, created_at: "2026-07-10T00:00:00Z" },
          { status: 202 }
        );
      })
    );

    await createRun({ source_ids: [1, 2], fini: "2026-01-01" });

    expect(body).toMatchObject({ source_ids: [1, 2], fini: "2026-01-01" });
  });

  it("cancelRun posts to the cancel endpoint", async () => {
    let method = "";
    server.use(
      http.post(`${BASE_URL}/runs/9/cancel`, ({ request }) => {
        method = request.method;
        return HttpResponse.json({ id: 9, triggered_by: "manual", status: "running", fini: null, ffin: null, cancel_requested: true, started_at: null, finished_at: null, created_at: "2026-07-10T00:00:00Z" });
      })
    );

    const run = await cancelRun(9);

    expect(method).toBe("POST");
    expect(run.cancel_requested).toBe(true);
  });
});
```

- [ ] **Step 3: Write the failing documents tests**

Create `frontend/src/api/documents.test.ts`:

```ts
import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { clearStoredApiKey } from "./client";
import { fetchDocument, fetchDocuments } from "./documents";

const BASE_URL = "http://localhost:8000";

describe("documents API", () => {
  beforeEach(() => clearStoredApiKey());

  it("fetchDocuments sends filters and returns the paginated envelope", async () => {
    let receivedUrl = "";
    server.use(
      http.get(`${BASE_URL}/documents`, ({ request }) => {
        receivedUrl = request.url;
        return HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 });
      })
    );

    const result = await fetchDocuments({ title: "sentencia", limit: 50, offset: 0 });

    expect(receivedUrl).toContain("title=sentencia");
    expect(result.total).toBe(0);
  });

  it("fetchDocument fetches a single document by id", async () => {
    server.use(
      http.get(`${BASE_URL}/documents/3`, () =>
        HttpResponse.json({
          id: 3,
          doc_id: "abc",
          source_id: 1,
          title: "Sentencia X",
          tipo: null,
          seccion: null,
          f_public: null,
          f_providencia: null,
          storage_bucket: "iurisync-documents",
          storage_key: "abc.pdf",
          content_type: "application/pdf",
          file_size_bytes: 1024,
          downloaded_at: "2026-07-10T00:00:00Z",
        })
      )
    );

    const document = await fetchDocument(3);

    expect(document.title).toBe("Sentencia X");
  });
});
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `npx vitest run sources.test runs.test documents.test` (inside `frontend/`)
Expected: FAIL — the modules under test don't exist yet.

- [ ] **Step 5: Implement `sourceFamilies.ts`**

Create `frontend/src/api/sourceFamilies.ts`:

```ts
import { apiFetch } from "./client";
import type { SourceFamily } from "./types";

export function fetchSourceFamilies(): Promise<SourceFamily[]> {
  return apiFetch<SourceFamily[]>("/source-families");
}
```

- [ ] **Step 6: Implement `sources.ts`**

Create `frontend/src/api/sources.ts`:

```ts
import { apiFetch, buildQuery } from "./client";
import type { Source, SourceCreateInput, SourceUpdateInput } from "./types";

export interface ListSourcesParams {
  family_key?: string;
  active?: boolean;
  limit?: number;
  offset?: number;
}

export function fetchSources(params: ListSourcesParams = {}): Promise<Source[]> {
  return apiFetch<Source[]>(`/sources${buildQuery(params)}`);
}

export function createSource(input: SourceCreateInput): Promise<Source> {
  return apiFetch<Source>("/sources", { method: "POST", body: JSON.stringify(input) });
}

export function updateSource(id: number, input: SourceUpdateInput): Promise<Source> {
  return apiFetch<Source>(`/sources/${id}`, { method: "PATCH", body: JSON.stringify(input) });
}
```

- [ ] **Step 7: Implement `runs.ts`**

Create `frontend/src/api/runs.ts`:

```ts
import { apiFetch, buildQuery } from "./client";
import type { Run, RunCreateInput, RunSource } from "./types";

export interface ListRunsParams {
  status_filter?: string;
  limit?: number;
  offset?: number;
}

export function fetchRuns(params: ListRunsParams = {}): Promise<Run[]> {
  return apiFetch<Run[]>(`/runs${buildQuery(params)}`);
}

export function fetchRun(id: number): Promise<Run> {
  return apiFetch<Run>(`/runs/${id}`);
}

export function fetchRunSources(runId: number): Promise<RunSource[]> {
  return apiFetch<RunSource[]>(`/runs/${runId}/sources`);
}

export function createRun(input: RunCreateInput): Promise<Run> {
  return apiFetch<Run>("/runs", { method: "POST", body: JSON.stringify(input) });
}

export function cancelRun(id: number): Promise<Run> {
  return apiFetch<Run>(`/runs/${id}/cancel`, { method: "POST" });
}
```

- [ ] **Step 8: Implement `documents.ts`**

Create `frontend/src/api/documents.ts`:

```ts
import { apiFetch, buildQuery } from "./client";
import type { Document, PaginatedDocuments } from "./types";

export interface ListDocumentsParams {
  source_id?: number;
  family_key?: string;
  tipo?: string;
  title?: string;
  limit?: number;
  offset?: number;
}

export function fetchDocuments(params: ListDocumentsParams = {}): Promise<PaginatedDocuments> {
  return apiFetch<PaginatedDocuments>(`/documents${buildQuery(params)}`);
}

export function fetchDocument(id: number): Promise<Document> {
  return apiFetch<Document>(`/documents/${id}`);
}
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `npx vitest run sources.test runs.test documents.test` (inside `frontend/`)
Expected: PASS (13 tests)

- [ ] **Step 10: Commit**

```bash
git add frontend/src/api/
git commit -m "feat: add API resource functions for source families, sources, runs, documents"
```

---

### Task 6: Auth — AuthContext, ProtectedRoute, LoginPage

**Files:**
- Create: `frontend/src/auth/AuthContext.tsx`
- Create: `frontend/src/auth/ProtectedRoute.tsx`
- Create: `frontend/src/pages/LoginPage.tsx`
- Test: `frontend/src/auth/AuthContext.test.tsx`
- Test: `frontend/src/pages/LoginPage.test.tsx`

**Interfaces:**
- Consumes: `getStoredApiKey`, `setStoredApiKey`, `clearStoredApiKey`, `registerUnauthorizedHandler` (Task 4); `fetchSourceFamilies` (Task 5).
- Produces: `AuthProvider` (React component), `useAuth(): { apiKey: string | null; login(key: string): void; logout(): void }`, `ProtectedRoute` (route-guard component using `<Outlet>`), `LoginPage` component. Task 7's `App.tsx` wraps the router in `AuthProvider` and uses `ProtectedRoute` to guard every page except `/login`.

- [ ] **Step 1: Write the failing AuthContext test**

Create `frontend/src/auth/AuthContext.test.tsx`:

```tsx
import { describe, expect, it, beforeEach } from "vitest";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { clearStoredApiKey, getStoredApiKey } from "../api/client";
import { AuthProvider, useAuth } from "./AuthContext";

function Probe() {
  const { apiKey, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="key">{apiKey ?? "none"}</span>
      <button onClick={() => login("new-key")}>login</button>
      <button onClick={() => logout()}>logout</button>
    </div>
  );
}

describe("AuthContext", () => {
  beforeEach(() => clearStoredApiKey());

  it("starts with the key already in localStorage, if any", () => {
    localStorage.setItem("iurisync_api_key", "existing-key");
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );
    expect(screen.getByTestId("key")).toHaveTextContent("existing-key");
  });

  it("login stores the key and updates state", async () => {
    const user = userEvent.setup();
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await user.click(screen.getByText("login"));

    expect(screen.getByTestId("key")).toHaveTextContent("new-key");
    expect(getStoredApiKey()).toBe("new-key");
  });

  it("logout clears the key and updates state", async () => {
    const user = userEvent.setup();
    localStorage.setItem("iurisync_api_key", "existing-key");
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>
    );

    await user.click(screen.getByText("logout"));

    expect(screen.getByTestId("key")).toHaveTextContent("none");
    expect(getStoredApiKey()).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run AuthContext.test` (inside `frontend/`)
Expected: FAIL — `./AuthContext` doesn't exist yet.

- [ ] **Step 3: Implement `AuthContext.tsx`**

Create `frontend/src/auth/AuthContext.tsx`:

```tsx
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { clearStoredApiKey, getStoredApiKey, registerUnauthorizedHandler, setStoredApiKey } from "../api/client";

interface AuthContextValue {
  apiKey: string | null;
  login: (key: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [apiKey, setApiKey] = useState<string | null>(() => getStoredApiKey());

  useEffect(() => {
    registerUnauthorizedHandler(() => setApiKey(null));
  }, []);

  function login(key: string) {
    setStoredApiKey(key);
    setApiKey(key);
  }

  function logout() {
    clearStoredApiKey();
    setApiKey(null);
  }

  return <AuthContext.Provider value={{ apiKey, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth debe usarse dentro de AuthProvider");
  return context;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run AuthContext.test` (inside `frontend/`)
Expected: PASS (3 tests)

- [ ] **Step 5: Implement `ProtectedRoute.tsx`**

Create `frontend/src/auth/ProtectedRoute.tsx`:

```tsx
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./AuthContext";

export function ProtectedRoute() {
  const { apiKey } = useAuth();
  if (!apiKey) return <Navigate to="/login" replace />;
  return <Outlet />;
}
```

- [ ] **Step 6: Write the failing LoginPage test**

Create `frontend/src/pages/LoginPage.test.tsx`:

```tsx
import { describe, expect, it, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { clearStoredApiKey, getStoredApiKey } from "../api/client";
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
  beforeEach(() => clearStoredApiKey());

  it("stores the key and clears the error on a valid key", async () => {
    const user = userEvent.setup();
    server.use(http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([])));
    renderLoginPage();

    await user.type(screen.getByPlaceholderText("API key"), "good-key");
    await user.click(screen.getByRole("button", { name: /entrar/i }));

    expect(await screen.findByRole("button", { name: /entrar/i })).toBeEnabled();
    expect(getStoredApiKey()).toBe("good-key");
  });

  it("shows an error and does not store the key on an invalid key", async () => {
    const user = userEvent.setup();
    server.use(http.get(`${BASE_URL}/source-families`, () => new HttpResponse(null, { status: 401 })));
    renderLoginPage();

    await user.type(screen.getByPlaceholderText("API key"), "bad-key");
    await user.click(screen.getByRole("button", { name: /entrar/i }));

    expect(await screen.findByText("API key inválida")).toBeInTheDocument();
    expect(getStoredApiKey()).toBeNull();
  });
});
```

- [ ] **Step 7: Run test to verify it fails**

Run: `npx vitest run LoginPage.test` (inside `frontend/`)
Expected: FAIL — `./LoginPage` doesn't exist yet.

- [ ] **Step 8: Implement `LoginPage.tsx`**

Create `frontend/src/pages/LoginPage.tsx`:

```tsx
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { fetchSourceFamilies } from "../api/sourceFamilies";
import { clearStoredApiKey, setStoredApiKey } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export function LoginPage() {
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setStoredApiKey(key);
    try {
      await fetchSourceFamilies();
      login(key);
      navigate("/", { replace: true });
    } catch {
      clearStoredApiKey();
      setError("API key inválida");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4 rounded-lg border p-6">
        <h1 className="text-xl font-semibold">IURISYNC — Ingresar</h1>
        <input
          type="password"
          value={key}
          onChange={(event) => setKey(event.target.value)}
          placeholder="API key"
          className="w-full rounded border px-3 py-2"
          required
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button type="submit" disabled={submitting} className="w-full rounded bg-slate-900 px-3 py-2 text-white">
          {submitting ? "Verificando…" : "Entrar"}
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 9: Run test to verify it passes**

Run: `npx vitest run LoginPage.test` (inside `frontend/`)
Expected: PASS (2 tests)

- [ ] **Step 10: Commit**

```bash
git add frontend/src/auth/ frontend/src/pages/LoginPage.tsx frontend/src/pages/LoginPage.test.tsx
git commit -m "feat: add API-key auth (AuthContext, ProtectedRoute, LoginPage)"
```

---

### Task 7: App shell — routing, layout, shared components

**Files:**
- Create: `frontend/src/components/layout/Sidebar.tsx`
- Create: `frontend/src/components/layout/AppLayout.tsx`
- Create: `frontend/src/components/StatusBadge.tsx`
- Create: `frontend/src/components/ErrorBanner.tsx`
- Create: `frontend/src/lib/formatters.ts`
- Create: `frontend/src/pages/OverviewPage.tsx`, `SourcesPage.tsx`, `RunsPage.tsx`, `RunDetailPage.tsx`, `DocumentsPage.tsx` (stub versions — replaced by later tasks)
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/components/StatusBadge.test.tsx`
- Test: `frontend/src/components/ErrorBanner.test.tsx`
- Test: `frontend/src/lib/formatters.test.ts`
- Test: `frontend/src/App.test.tsx` (rewritten)

**Interfaces:**
- Consumes: `AuthProvider`, `ProtectedRoute` (Task 6), `LoginPage` (Task 6).
- Produces: `StatusBadge({ status: string })`, `ErrorBanner({ message: string; onRetry？: () => void })`, `formatBytes(bytes: number | null): string`, `formatDate(value: string | null): string`, `formatDateTime(value: string | null): string`, `AppLayout` (renders `<Sidebar>` + `<Outlet>`). Tasks 8–15 import all of these.

- [ ] **Step 1: Write the failing StatusBadge test**

Create `frontend/src/components/StatusBadge.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders the status text", () => {
    render(<StatusBadge status="completed" />);
    expect(screen.getByText("completed")).toBeInTheDocument();
  });

  it("falls back to a default style for an unknown status", () => {
    render(<StatusBadge status="unknown-status" />);
    expect(screen.getByText("unknown-status")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Write the failing ErrorBanner test**

Create `frontend/src/components/ErrorBanner.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ErrorBanner } from "./ErrorBanner";

describe("ErrorBanner", () => {
  it("renders the message", () => {
    render(<ErrorBanner message="Algo salió mal" />);
    expect(screen.getByText("Algo salió mal")).toBeInTheDocument();
  });

  it("calls onRetry when the retry button is clicked", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<ErrorBanner message="Algo salió mal" onRetry={onRetry} />);

    await user.click(screen.getByText("Reintentar"));

    expect(onRetry).toHaveBeenCalledOnce();
  });
});
```

- [ ] **Step 3: Write the failing formatters test**

Create `frontend/src/lib/formatters.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { formatBytes, formatDate, formatDateTime } from "./formatters";

describe("formatBytes", () => {
  it("formats bytes under 1KB", () => expect(formatBytes(500)).toBe("500 B"));
  it("formats KB", () => expect(formatBytes(2048)).toBe("2.0 KB"));
  it("formats MB", () => expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB"));
  it("returns an em dash for null", () => expect(formatBytes(null)).toBe("—"));
});

describe("formatDate / formatDateTime", () => {
  it("returns an em dash for null", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDateTime(null)).toBe("—");
  });

  it("formats a non-null date string", () => {
    expect(formatDate("2026-07-10")).not.toBe("—");
    expect(formatDateTime("2026-07-10T12:00:00Z")).not.toBe("—");
  });
});
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `npx vitest run StatusBadge.test ErrorBanner.test formatters.test` (inside `frontend/`)
Expected: FAIL — none of the three modules exist yet.

- [ ] **Step 5: Implement `StatusBadge.tsx`**

Create `frontend/src/components/StatusBadge.tsx`:

```tsx
const STATUS_STYLES: Record<string, string> = {
  pending: "bg-gray-200 text-gray-800",
  running: "bg-blue-200 text-blue-800",
  completed: "bg-green-200 text-green-800",
  failed: "bg-red-200 text-red-800",
};

export function StatusBadge({ status }: { status: string }) {
  const className = STATUS_STYLES[status] ?? "bg-gray-200 text-gray-800";
  return <span className={`rounded-full px-2 py-1 text-xs font-medium ${className}`}>{status}</span>;
}
```

- [ ] **Step 6: Implement `ErrorBanner.tsx`**

Create `frontend/src/components/ErrorBanner.tsx`:

```tsx
export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-center justify-between rounded border border-red-300 bg-red-50 px-4 py-2 text-red-800">
      <span>{message}</span>
      {onRetry && (
        <button onClick={onRetry} className="text-sm font-medium underline">
          Reintentar
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 7: Implement `formatters.ts`**

Create `frontend/src/lib/formatters.ts`:

```ts
export function formatBytes(bytes: number | null): string {
  if (bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("es-CO", { year: "numeric", month: "short", day: "numeric" });
}

export function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("es-CO");
}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `npx vitest run StatusBadge.test ErrorBanner.test formatters.test` (inside `frontend/`)
Expected: PASS (9 tests)

- [ ] **Step 9: Implement the Sidebar**

Create `frontend/src/components/layout/Sidebar.tsx`:

```tsx
import { NavLink } from "react-router-dom";

const LINKS = [
  { to: "/", label: "Resumen", end: true },
  { to: "/sources", label: "Fuentes", end: false },
  { to: "/runs", label: "Runs", end: false },
  { to: "/documents", label: "Documentos", end: false },
];

export function Sidebar() {
  return (
    <nav className="w-56 shrink-0 border-r p-4">
      <p className="mb-6 text-lg font-bold">IURISYNC</p>
      <ul className="space-y-2">
        {LINKS.map((link) => (
          <li key={link.to}>
            <NavLink
              to={link.to}
              end={link.end}
              className={({ isActive }) =>
                `block rounded px-3 py-2 ${isActive ? "bg-slate-900 text-white" : "hover:bg-slate-100"}`
              }
            >
              {link.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
```

- [ ] **Step 10: Implement the AppLayout**

Create `frontend/src/components/layout/AppLayout.tsx`:

```tsx
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";

export function AppLayout() {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-6">
        <Outlet />
      </main>
    </div>
  );
}
```

- [ ] **Step 11: Create stub pages for the routes not yet built**

Create `frontend/src/pages/OverviewPage.tsx`:
```tsx
export function OverviewPage() {
  return <div>Resumen (próximamente)</div>;
}
```

Create `frontend/src/pages/SourcesPage.tsx`:
```tsx
export function SourcesPage() {
  return <div>Fuentes (próximamente)</div>;
}
```

Create `frontend/src/pages/RunsPage.tsx`:
```tsx
export function RunsPage() {
  return <div>Runs (próximamente)</div>;
}
```

Create `frontend/src/pages/RunDetailPage.tsx`:
```tsx
export function RunDetailPage() {
  return <div>Detalle de run (próximamente)</div>;
}
```

Create `frontend/src/pages/DocumentsPage.tsx`:
```tsx
export function DocumentsPage() {
  return <div>Documentos (próximamente)</div>;
}
```

- [ ] **Step 12: Wire everything into `App.tsx`**

Replace `frontend/src/App.tsx`:

```tsx
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./auth/AuthContext";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { AppLayout } from "./components/layout/AppLayout";
import { LoginPage } from "./pages/LoginPage";
import { OverviewPage } from "./pages/OverviewPage";
import { SourcesPage } from "./pages/SourcesPage";
import { RunsPage } from "./pages/RunsPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { DocumentsPage } from "./pages/DocumentsPage";

const queryClient = new QueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<ProtectedRoute />}>
              <Route element={<AppLayout />}>
                <Route path="/" element={<OverviewPage />} />
                <Route path="/sources" element={<SourcesPage />} />
                <Route path="/runs" element={<RunsPage />} />
                <Route path="/runs/:runId" element={<RunDetailPage />} />
                <Route path="/documents" element={<DocumentsPage />} />
              </Route>
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
```

- [ ] **Step 13: Rewrite the App smoke test for the new shell**

Replace `frontend/src/App.test.tsx`:

```tsx
import { describe, expect, it, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { clearStoredApiKey } from "./api/client";
import { App } from "./App";

describe("App", () => {
  beforeEach(() => {
    clearStoredApiKey();
    window.history.pushState({}, "", "/");
  });

  it("redirects to the login page when there is no stored API key", () => {
    render(<App />);
    expect(screen.getByPlaceholderText("API key")).toBeInTheDocument();
  });

  it("renders the Overview page when an API key is already stored", () => {
    localStorage.setItem("iurisync_api_key", "existing-key");
    render(<App />);
    expect(screen.getByText("Resumen (próximamente)")).toBeInTheDocument();
  });
});
```

**Important notes (discovered during implementation, not in the original design):**

1. `App.tsx` uses `<BrowserRouter>`, which reads and writes the *real* jsdom `window.location`/history — it is not sandboxed per test. Within one `describe` block, multiple `it()`s in the same file share that same `window`/`document` (Vitest doesn't reset jsdom between tests in the same file, only between files). The first test's `<Navigate to="/login" replace />` (fired because there's no stored key) leaves `window.location.pathname` at `/login` — if a later test doesn't reset it, `<BrowserRouter>` mounts already pointed at `/login` regardless of what's in `localStorage`, and the test fails with the LoginPage rendering instead of the expected page, which looks like a routing/nesting bug but isn't. The `window.history.pushState({}, "", "/")` line in `beforeEach` above is the fix — it resets the URL before every test so each one starts from `/` as intended. If a future test file reuses `render(<App />)` multiple times, apply the same reset.

2. Once routing actually renders the Overview page, `screen.getByText(/Resumen/)` matches BOTH the Sidebar's "Resumen" nav link and the OverviewPage stub's "Resumen (próximamente)" text simultaneously — an ambiguity invisible before fix 1 (only the LoginPage rendered, so no "Resumen" text existed at all) that only surfaces once routing is correct. The assertion above uses the full unique stub text to disambiguate — do not revert to the `/Resumen/` regex.

- [ ] **Step 14: Run the full test suite to verify it passes**

Run: `npx vitest run` (inside `frontend/`)
Expected: PASS (all tests)

- [ ] **Step 15: Commit**

```bash
git add frontend/src/
git commit -m "feat: wire app shell (routing, layout, shared components)"
```

---

### Task 8: SourcesPage — list, filters, pagination

**Files:**
- Modify: `frontend/src/pages/SourcesPage.tsx`
- Test: `frontend/src/pages/SourcesPage.test.tsx`

**Interfaces:**
- Consumes: `fetchSources`, `ListSourcesParams` (Task 5); `fetchSourceFamilies` (Task 5); `ErrorBanner` (Task 7).
- Produces: the filter/pagination shell that Task 9 extends with create/edit actions — Task 9 must not change the `useQuery` keys (`["sources", familyKey, activeFilter, page]`, `["source-families"]`) since that would silently break cache invalidation set up here.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/SourcesPage.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { SourcesPage } from "./SourcesPage";

const BASE_URL = "http://localhost:8000";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <SourcesPage />
    </QueryClientProvider>
  );
}

describe("SourcesPage", () => {
  it("renders the fetched sources", async () => {
    server.use(
      http.get(`${BASE_URL}/source-families`, () =>
        HttpResponse.json([{ key: "constitucional", display_name: "Corte Constitucional", description: null }])
      ),
      http.get(`${BASE_URL}/sources`, () =>
        HttpResponse.json([{ id: 1, family_key: "constitucional", name: "Corte Constitucional", family_params: {}, active: true }])
      )
    );

    renderPage();

    expect(await screen.findByText("Corte Constitucional")).toBeInTheDocument();
  });

  it("refetches with the active filter applied when changed", async () => {
    let lastUrl = "";
    server.use(
      http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/sources`, ({ request }) => {
        lastUrl = request.url;
        return HttpResponse.json([]);
      })
    );
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(lastUrl).toContain("/sources"));
    await user.selectOptions(screen.getByLabelText(/estado/i), "true");

    await waitFor(() => expect(lastUrl).toContain("active=true"));
  });

  it("shows an error banner when the sources request fails", async () => {
    server.use(
      http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/sources`, () => new HttpResponse(null, { status: 500 }))
    );

    renderPage();

    expect(await screen.findByText(/no se pudieron cargar las fuentes/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run SourcesPage.test` (inside `frontend/`)
Expected: FAIL — the stub page has none of this markup.

- [ ] **Step 3: Implement the list/filter/pagination page**

Replace `frontend/src/pages/SourcesPage.tsx`:

```tsx
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchSourceFamilies } from "../api/sourceFamilies";
import { fetchSources } from "../api/sources";
import { ErrorBanner } from "../components/ErrorBanner";

const PAGE_SIZE = 20;

export function SourcesPage() {
  const [familyKey, setFamilyKey] = useState("");
  const [activeFilter, setActiveFilter] = useState("all");
  const [page, setPage] = useState(0);

  const familiesQuery = useQuery({ queryKey: ["source-families"], queryFn: fetchSourceFamilies });

  const sourcesQuery = useQuery({
    queryKey: ["sources", familyKey, activeFilter, page],
    queryFn: () =>
      fetchSources({
        family_key: familyKey || undefined,
        active: activeFilter === "all" ? undefined : activeFilter === "true",
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
  });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Fuentes</h1>

      <div className="flex gap-3">
        <label className="flex items-center gap-2 text-sm">
          Familia
          <select
            value={familyKey}
            onChange={(event) => {
              setFamilyKey(event.target.value);
              setPage(0);
            }}
            className="rounded border px-2 py-1"
          >
            <option value="">Todas</option>
            {familiesQuery.data?.map((family) => (
              <option key={family.key} value={family.key}>
                {family.display_name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          Estado
          <select
            aria-label="Estado"
            value={activeFilter}
            onChange={(event) => {
              setActiveFilter(event.target.value);
              setPage(0);
            }}
            className="rounded border px-2 py-1"
          >
            <option value="all">Todas</option>
            <option value="true">Activas</option>
            <option value="false">Inactivas</option>
          </select>
        </label>
      </div>

      {sourcesQuery.isError && (
        <ErrorBanner message="No se pudieron cargar las fuentes." onRetry={() => sourcesQuery.refetch()} />
      )}

      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b">
            <th className="py-2">Nombre</th>
            <th className="py-2">Familia</th>
            <th className="py-2">Estado</th>
          </tr>
        </thead>
        <tbody>
          {sourcesQuery.data?.map((source) => (
            <tr key={source.id} className="border-b">
              <td className="py-2">{source.name}</td>
              <td className="py-2">{source.family_key}</td>
              <td className="py-2">{source.active ? "Activa" : "Inactiva"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="flex justify-end gap-2">
        <button
          disabled={page === 0}
          onClick={() => setPage((current) => current - 1)}
          className="rounded border px-3 py-1 disabled:opacity-50"
        >
          Anterior
        </button>
        <button
          disabled={(sourcesQuery.data?.length ?? 0) < PAGE_SIZE}
          onClick={() => setPage((current) => current + 1)}
          className="rounded border px-3 py-1 disabled:opacity-50"
        >
          Siguiente
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run SourcesPage.test` (inside `frontend/`)
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/SourcesPage.tsx frontend/src/pages/SourcesPage.test.tsx
git commit -m "feat: add SourcesPage list with filters and pagination"
```

---

### Task 9: SourcesPage — create modal and edit actions

**Files:**
- Modify: `frontend/src/pages/SourcesPage.tsx`
- Test: `frontend/src/pages/SourcesPage.test.tsx` (extend)

**Interfaces:**
- Consumes: `createSource`, `updateSource` (Task 5); `Button`, `Dialog`, `DialogContent`, `DialogFooter`, `DialogHeader`, `DialogTitle`, `DialogTrigger`, `Input`, `Label` (Task 3); `ApiError` (Task 4); `SourceFamily`, `Source` (Task 4 types).
- Produces: nothing consumed by later tasks — this is the last SourcesPage task.

- [ ] **Step 1: Extend the failing tests**

Append to `frontend/src/pages/SourcesPage.test.tsx`:

```tsx
describe("SourcesPage — create and edit", () => {
  it("creates a source and refreshes the list", async () => {
    let createdBody: unknown;
    server.use(
      http.get(`${BASE_URL}/source-families`, () =>
        HttpResponse.json([{ key: "constitucional", display_name: "Corte Constitucional", description: null }])
      ),
      http.get(`${BASE_URL}/sources`, () => HttpResponse.json([])),
      http.post(`${BASE_URL}/sources`, async ({ request }) => {
        createdBody = await request.json();
        return HttpResponse.json({ id: 2, ...(createdBody as object) }, { status: 201 });
      })
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText("Nueva fuente"));
    await user.selectOptions(screen.getByLabelText("Familia de la fuente"), "constitucional");
    await user.type(screen.getByLabelText(/nombre/i), "Corte Constitucional");
    await user.click(screen.getByText("Crear"));

    await waitFor(() => expect(createdBody).toMatchObject({ family_key: "constitucional", name: "Corte Constitucional" }));
  });

  it("toggles a source's active state", async () => {
    let patchedBody: unknown;
    server.use(
      http.get(`${BASE_URL}/source-families`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/sources`, () =>
        HttpResponse.json([{ id: 1, family_key: "constitucional", name: "Corte Constitucional", family_params: {}, active: true }])
      ),
      http.patch(`${BASE_URL}/sources/1`, async ({ request }) => {
        patchedBody = await request.json();
        return HttpResponse.json({ id: 1, family_key: "constitucional", name: "Corte Constitucional", family_params: {}, active: false });
      })
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText("Desactivar"));

    await waitFor(() => expect(patchedBody).toMatchObject({ active: false }));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run SourcesPage.test` (inside `frontend/`)
Expected: FAIL — no "Nueva fuente" button or "Desactivar" action exists yet.

- [ ] **Step 3: Add the create dialog and row actions**

Replace `frontend/src/pages/SourcesPage.tsx` (adds imports, `NewSourceDialog`, and a row action column — list/filter code from Task 8 is unchanged below the new pieces):

```tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchSourceFamilies } from "../api/sourceFamilies";
import { createSource, fetchSources, updateSource } from "../api/sources";
import { ApiError } from "../api/client";
import type { Source, SourceFamily } from "../api/types";
import { ErrorBanner } from "../components/ErrorBanner";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";

const PAGE_SIZE = 20;

function NewSourceDialog({ families }: { families: SourceFamily[] }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [familyKey, setFamilyKey] = useState("");
  const [name, setName] = useState("");
  const [paramsText, setParamsText] = useState("{}");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: createSource,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sources"] });
      setOpen(false);
      setName("");
      setParamsText("{}");
      setError(null);
    },
    onError: (err: unknown) => {
      setError(err instanceof ApiError ? err.message : "Error al crear la fuente");
    },
  });

  function handleSubmit() {
    let familyParams: Record<string, unknown>;
    try {
      familyParams = JSON.parse(paramsText);
    } catch {
      setError("Los parámetros deben ser JSON válido");
      return;
    }
    mutation.mutate({ family_key: familyKey, name, family_params: familyParams, active: true });
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>Nueva fuente</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nueva fuente</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label htmlFor="new-source-family">Familia de la fuente</Label>
            <select
              id="new-source-family"
              value={familyKey}
              onChange={(event) => setFamilyKey(event.target.value)}
              className="w-full rounded border px-2 py-1"
            >
              <option value="">Selecciona una familia</option>
              {families.map((family) => (
                <option key={family.key} value={family.key}>
                  {family.display_name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="new-source-name">Nombre</Label>
            <Input id="new-source-name" value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          <div>
            <Label htmlFor="new-source-params">Parámetros (JSON)</Label>
            <textarea
              id="new-source-params"
              value={paramsText}
              onChange={(event) => setParamsText(event.target.value)}
              className="w-full rounded border px-2 py-1 font-mono text-sm"
              rows={4}
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
        <DialogFooter>
          <Button onClick={handleSubmit} disabled={!familyKey || !name || mutation.isPending}>
            {mutation.isPending ? "Creando…" : "Crear"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SourceRow({ source }: { source: Source }) {
  const queryClient = useQueryClient();
  const toggleMutation = useMutation({
    mutationFn: () => updateSource(source.id, { active: !source.active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sources"] }),
  });

  return (
    <tr className="border-b">
      <td className="py-2">{source.name}</td>
      <td className="py-2">{source.family_key}</td>
      <td className="py-2">{source.active ? "Activa" : "Inactiva"}</td>
      <td className="py-2">
        <button onClick={() => toggleMutation.mutate()} className="text-sm text-blue-600 underline" disabled={toggleMutation.isPending}>
          {source.active ? "Desactivar" : "Activar"}
        </button>
      </td>
    </tr>
  );
}

export function SourcesPage() {
  const [familyKey, setFamilyKey] = useState("");
  const [activeFilter, setActiveFilter] = useState("all");
  const [page, setPage] = useState(0);

  const familiesQuery = useQuery({ queryKey: ["source-families"], queryFn: fetchSourceFamilies });

  const sourcesQuery = useQuery({
    queryKey: ["sources", familyKey, activeFilter, page],
    queryFn: () =>
      fetchSources({
        family_key: familyKey || undefined,
        active: activeFilter === "all" ? undefined : activeFilter === "true",
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Fuentes</h1>
        <NewSourceDialog families={familiesQuery.data ?? []} />
      </div>

      <div className="flex gap-3">
        <label className="flex items-center gap-2 text-sm">
          Familia
          <select
            value={familyKey}
            onChange={(event) => {
              setFamilyKey(event.target.value);
              setPage(0);
            }}
            className="rounded border px-2 py-1"
          >
            <option value="">Todas</option>
            {familiesQuery.data?.map((family) => (
              <option key={family.key} value={family.key}>
                {family.display_name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          Estado
          <select
            aria-label="Estado"
            value={activeFilter}
            onChange={(event) => {
              setActiveFilter(event.target.value);
              setPage(0);
            }}
            className="rounded border px-2 py-1"
          >
            <option value="all">Todas</option>
            <option value="true">Activas</option>
            <option value="false">Inactivas</option>
          </select>
        </label>
      </div>

      {sourcesQuery.isError && (
        <ErrorBanner message="No se pudieron cargar las fuentes." onRetry={() => sourcesQuery.refetch()} />
      )}

      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b">
            <th className="py-2">Nombre</th>
            <th className="py-2">Familia</th>
            <th className="py-2">Estado</th>
            <th className="py-2">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {sourcesQuery.data?.map((source) => (
            <SourceRow key={source.id} source={source} />
          ))}
        </tbody>
      </table>

      <div className="flex justify-end gap-2">
        <button
          disabled={page === 0}
          onClick={() => setPage((current) => current - 1)}
          className="rounded border px-3 py-1 disabled:opacity-50"
        >
          Anterior
        </button>
        <button
          disabled={(sourcesQuery.data?.length ?? 0) < PAGE_SIZE}
          onClick={() => setPage((current) => current + 1)}
          className="rounded border px-3 py-1 disabled:opacity-50"
        >
          Siguiente
        </button>
      </div>
    </div>
  );
}
```

Note: the dialog's field is deliberately labeled "Familia de la fuente" (not just "Familia") so `getByLabelText` can't collide with the page's own "Familia" filter dropdown once the dialog is open — keep both label texts distinct if you touch either one. This also relies on shadcn's `<Label>` rendering a real `<label>` element (it wraps Radix's `Label.Root`, which does); if the generated component's export shape differs, adjust the test query rather than fighting the component.

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run SourcesPage.test` (inside `frontend/`)
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/SourcesPage.tsx frontend/src/pages/SourcesPage.test.tsx
git commit -m "feat: add SourcesPage create modal and active-toggle action"
```

---

### Task 10: RunsPage — list, filters, pagination, polling

**Files:**
- Modify: `frontend/src/pages/RunsPage.tsx`
- Test: `frontend/src/pages/RunsPage.test.tsx`

**Interfaces:**
- Consumes: `fetchRuns`, `ListRunsParams` (Task 5); `StatusBadge`, `ErrorBanner` (Task 7); `formatDateTime` (Task 7).
- Produces: the `["runs", statusFilter, page]` query key and the list/filter/pagination shell that Task 11 extends with the "new run" modal.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/RunsPage.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { RunsPage } from "./RunsPage";

const BASE_URL = "http://localhost:8000";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <RunsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const RUN = {
  id: 1,
  triggered_by: "manual",
  status: "running",
  fini: null,
  ffin: null,
  cancel_requested: false,
  started_at: null,
  finished_at: null,
  created_at: "2026-07-10T00:00:00Z",
};

describe("RunsPage", () => {
  it("renders the fetched runs with a status badge", async () => {
    server.use(
      http.get(`${BASE_URL}/sources`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/runs`, () => HttpResponse.json([RUN]))
    );

    renderPage();

    expect(await screen.findByText("running")).toBeInTheDocument();
  });

  it("polls again while a run is not completed, and stops once it is", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let callCount = 0;
    server.use(
      http.get(`${BASE_URL}/sources`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/runs`, () => {
        callCount += 1;
        return HttpResponse.json([{ ...RUN, status: callCount >= 2 ? "completed" : "running" }]);
      })
    );

    renderPage();
    await waitFor(() => expect(callCount).toBe(1));

    await vi.advanceTimersByTimeAsync(4100);
    await waitFor(() => expect(callCount).toBe(2));

    await vi.advanceTimersByTimeAsync(4100);
    expect(callCount).toBe(2);

    vi.useRealTimers();
  });
});
```

Note: fake timers plus react-query's internal scheduling can be flaky — if `callCount` doesn't advance as expected, try a larger `advanceTimersByTimeAsync` value (react-query may add jitter/backoff) or wrap the assertion in `waitFor` with real timers and a short real interval override instead of faking time. Get this one test genuinely green before moving on; don't relax the assertion to make it pass without understanding why.

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run RunsPage.test` (inside `frontend/`)
Expected: FAIL — the stub page has none of this markup/polling.

- [ ] **Step 3: Implement the list/filter/pagination/polling page**

Replace `frontend/src/pages/RunsPage.tsx`:

```tsx
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchRuns } from "../api/runs";
import { ErrorBanner } from "../components/ErrorBanner";
import { StatusBadge } from "../components/StatusBadge";
import { formatDateTime } from "../lib/formatters";

const PAGE_SIZE = 20;
const POLL_INTERVAL_MS = 4000;

export function RunsPage() {
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(0);

  const runsQuery = useQuery({
    queryKey: ["runs", statusFilter, page],
    queryFn: () =>
      fetchRuns({
        status_filter: statusFilter || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
    refetchInterval: (query) => {
      const data = query.state.data;
      const hasActiveRun = data?.some((run) => run.status !== "completed");
      return hasActiveRun ? POLL_INTERVAL_MS : false;
    },
  });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Runs</h1>

      <label className="flex items-center gap-2 text-sm">
        Estado
        <select
          aria-label="Estado del run"
          value={statusFilter}
          onChange={(event) => {
            setStatusFilter(event.target.value);
            setPage(0);
          }}
          className="rounded border px-2 py-1"
        >
          <option value="">Todos</option>
          <option value="pending">Pendiente</option>
          <option value="running">En curso</option>
          <option value="completed">Completado</option>
        </select>
      </label>

      {runsQuery.isError && (
        <ErrorBanner message="No se pudieron cargar los runs." onRetry={() => runsQuery.refetch()} />
      )}

      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b">
            <th className="py-2">ID</th>
            <th className="py-2">Disparado por</th>
            <th className="py-2">Estado</th>
            <th className="py-2">Creado</th>
          </tr>
        </thead>
        <tbody>
          {runsQuery.data?.map((run) => (
            <tr key={run.id} className="border-b">
              <td className="py-2">{run.id}</td>
              <td className="py-2">{run.triggered_by}</td>
              <td className="py-2"><StatusBadge status={run.status} /></td>
              <td className="py-2">{formatDateTime(run.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="flex justify-end gap-2">
        <button
          disabled={page === 0}
          onClick={() => setPage((current) => current - 1)}
          className="rounded border px-3 py-1 disabled:opacity-50"
        >
          Anterior
        </button>
        <button
          disabled={(runsQuery.data?.length ?? 0) < PAGE_SIZE}
          onClick={() => setPage((current) => current + 1)}
          className="rounded border px-3 py-1 disabled:opacity-50"
        >
          Siguiente
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run RunsPage.test` (inside `frontend/`)
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/RunsPage.tsx frontend/src/pages/RunsPage.test.tsx
git commit -m "feat: add RunsPage list with filters, pagination, and polling"
```

---

### Task 11: RunsPage — new run modal and navigation

**Files:**
- Modify: `frontend/src/pages/RunsPage.tsx`
- Test: `frontend/src/pages/RunsPage.test.tsx` (extend)

**Interfaces:**
- Consumes: `createRun` (Task 5); `fetchSources` (Task 5, for the active-sources checklist); `Button`, `Dialog`, `DialogContent`, `DialogFooter`, `DialogHeader`, `DialogTitle`, `DialogTrigger`, `Input`, `Label` (Task 3); `useNavigate` (react-router-dom).
- Produces: nothing consumed by later tasks — this is the last RunsPage task.

- [ ] **Step 1: Extend the failing test**

Append to `frontend/src/pages/RunsPage.test.tsx`:

```tsx
describe("RunsPage — new run", () => {
  it("creates a run with the selected sources and navigates to its detail page", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    let createdBody: unknown;
    server.use(
      http.get(`${BASE_URL}/sources`, () =>
        HttpResponse.json([{ id: 1, family_key: "constitucional", name: "Corte Constitucional", family_params: {}, active: true }])
      ),
      http.get(`${BASE_URL}/runs`, () => HttpResponse.json([])),
      http.post(`${BASE_URL}/runs`, async ({ request }) => {
        createdBody = await request.json();
        return HttpResponse.json({ ...RUN, id: 42 }, { status: 202 });
      })
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText("Nuevo run"));
    await user.click(screen.getByLabelText("Corte Constitucional"));
    await user.click(screen.getByText("Iniciar run"));

    await waitFor(() => expect(createdBody).toMatchObject({ source_ids: [1] }));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run RunsPage.test` (inside `frontend/`)
Expected: FAIL — no "Nuevo run" button exists yet.

- [ ] **Step 3: Add the new-run dialog**

Replace `frontend/src/pages/RunsPage.tsx` (adds imports, `NewRunDialog`, and wires it into the header — list/filter/polling code from Task 10 is unchanged below):

```tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { createRun, fetchRuns } from "../api/runs";
import { fetchSources } from "../api/sources";
import type { Source } from "../api/types";
import { ErrorBanner } from "../components/ErrorBanner";
import { StatusBadge } from "../components/StatusBadge";
import { Button } from "../components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { formatDateTime } from "../lib/formatters";

const PAGE_SIZE = 20;
const POLL_INTERVAL_MS = 4000;

function NewRunDialog({ sources }: { sources: Source[] }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [fini, setFini] = useState("");
  const [ffin, setFfin] = useState("");

  const mutation = useMutation({
    mutationFn: createRun,
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      setOpen(false);
      navigate(`/runs/${run.id}`);
    },
  });

  function toggleSource(id: number) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((existing) => existing !== id) : [...prev, id]));
  }

  function handleSubmit() {
    mutation.mutate({
      source_ids: selectedIds.length > 0 ? selectedIds : undefined,
      fini: fini || undefined,
      ffin: ffin || undefined,
    });
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>Nuevo run</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuevo run</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>Fuentes (vacío = todas las activas)</Label>
            <div className="max-h-40 space-y-1 overflow-y-auto rounded border p-2">
              {sources.map((source) => (
                <label key={source.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    aria-label={source.name}
                    checked={selectedIds.includes(source.id)}
                    onChange={() => toggleSource(source.id)}
                  />
                  {source.name}
                </label>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <div>
              <Label htmlFor="run-fini">Desde</Label>
              <Input id="run-fini" type="date" value={fini} onChange={(event) => setFini(event.target.value)} />
            </div>
            <div>
              <Label htmlFor="run-ffin">Hasta</Label>
              <Input id="run-ffin" type="date" value={ffin} onChange={(event) => setFfin(event.target.value)} />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button onClick={handleSubmit} disabled={mutation.isPending}>
            {mutation.isPending ? "Creando…" : "Iniciar run"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function RunsPage() {
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(0);

  const activeSourcesQuery = useQuery({
    queryKey: ["sources", "active-for-new-run"],
    queryFn: () => fetchSources({ active: true, limit: 100 }),
  });

  const runsQuery = useQuery({
    queryKey: ["runs", statusFilter, page],
    queryFn: () =>
      fetchRuns({
        status_filter: statusFilter || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
    refetchInterval: (query) => {
      const data = query.state.data;
      const hasActiveRun = data?.some((run) => run.status !== "completed");
      return hasActiveRun ? POLL_INTERVAL_MS : false;
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Runs</h1>
        <NewRunDialog sources={activeSourcesQuery.data ?? []} />
      </div>

      <label className="flex items-center gap-2 text-sm">
        Estado
        <select
          aria-label="Estado del run"
          value={statusFilter}
          onChange={(event) => {
            setStatusFilter(event.target.value);
            setPage(0);
          }}
          className="rounded border px-2 py-1"
        >
          <option value="">Todos</option>
          <option value="pending">Pendiente</option>
          <option value="running">En curso</option>
          <option value="completed">Completado</option>
        </select>
      </label>

      {runsQuery.isError && (
        <ErrorBanner message="No se pudieron cargar los runs." onRetry={() => runsQuery.refetch()} />
      )}

      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b">
            <th className="py-2">ID</th>
            <th className="py-2">Disparado por</th>
            <th className="py-2">Estado</th>
            <th className="py-2">Creado</th>
          </tr>
        </thead>
        <tbody>
          {runsQuery.data?.map((run) => (
            <tr key={run.id} className="border-b">
              <td className="py-2">{run.id}</td>
              <td className="py-2">{run.triggered_by}</td>
              <td className="py-2"><StatusBadge status={run.status} /></td>
              <td className="py-2">{formatDateTime(run.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="flex justify-end gap-2">
        <button
          disabled={page === 0}
          onClick={() => setPage((current) => current - 1)}
          className="rounded border px-3 py-1 disabled:opacity-50"
        >
          Anterior
        </button>
        <button
          disabled={(runsQuery.data?.length ?? 0) < PAGE_SIZE}
          onClick={() => setPage((current) => current + 1)}
          className="rounded border px-3 py-1 disabled:opacity-50"
        >
          Siguiente
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run RunsPage.test` (inside `frontend/`)
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/RunsPage.tsx frontend/src/pages/RunsPage.test.tsx
git commit -m "feat: add RunsPage new-run modal with source selection and navigation"
```

---

### Task 12: RunDetailPage — header, run_sources table, polling, cancel

**Files:**
- Modify: `frontend/src/pages/RunDetailPage.tsx`
- Test: `frontend/src/pages/RunDetailPage.test.tsx`

**Interfaces:**
- Consumes: `fetchRun`, `fetchRunSources`, `cancelRun` (Task 5); `StatusBadge` (Task 7); `formatDateTime` (Task 7); `Button` (Task 3); `useParams` (react-router-dom).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/RunDetailPage.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { RunDetailPage } from "./RunDetailPage";

const BASE_URL = "http://localhost:8000";

function renderPage(runId = "1") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/runs/${runId}`]}>
        <Routes>
          <Route path="/runs/:runId" element={<RunDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const RUN = {
  id: 1,
  triggered_by: "manual",
  status: "running",
  fini: null,
  ffin: null,
  cancel_requested: false,
  started_at: "2026-07-10T00:00:00Z",
  finished_at: null,
  created_at: "2026-07-10T00:00:00Z",
};

const RUN_SOURCE = { id: 1, run_id: 1, source_id: 5, status: "failed", docs_new: 2, docs_errors: 1, error_message: "timeout" };

describe("RunDetailPage", () => {
  it("renders the run header and its sources table", async () => {
    server.use(
      http.get(`${BASE_URL}/runs/1`, () => HttpResponse.json(RUN)),
      http.get(`${BASE_URL}/runs/1/sources`, () => HttpResponse.json([RUN_SOURCE]))
    );

    renderPage();

    expect(await screen.findByText("Run #1")).toBeInTheDocument();
    expect(screen.getByText("timeout")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("shows the cancel button only while the run is not completed", async () => {
    server.use(
      http.get(`${BASE_URL}/runs/1`, () => HttpResponse.json({ ...RUN, status: "completed" })),
      http.get(`${BASE_URL}/runs/1/sources`, () => HttpResponse.json([]))
    );

    renderPage();

    await screen.findByText("Run #1");
    expect(screen.queryByText("Cancelar run")).not.toBeInTheDocument();
  });

  it("requests cancellation and disables the button afterwards", async () => {
    // The GET /runs/1 mock must be stateful: the button's label reads run.cancel_requested
    // from this query, and it only changes after the mutation's onSuccess invalidates and
    // refetches it — a static mock would never reflect the cancellation.
    let cancelRequested = false;
    server.use(
      http.get(`${BASE_URL}/runs/1`, () => HttpResponse.json({ ...RUN, cancel_requested: cancelRequested })),
      http.get(`${BASE_URL}/runs/1/sources`, () => HttpResponse.json([])),
      http.post(`${BASE_URL}/runs/1/cancel`, () => {
        cancelRequested = true;
        return HttpResponse.json({ ...RUN, cancel_requested: true });
      })
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText("Cancelar run"));

    expect(await screen.findByText("Cancelación solicitada")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run RunDetailPage.test` (inside `frontend/`)
Expected: FAIL — the stub page has none of this markup.

- [ ] **Step 3: Implement the page**

Replace `frontend/src/pages/RunDetailPage.tsx`:

```tsx
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cancelRun, fetchRun, fetchRunSources } from "../api/runs";
import { StatusBadge } from "../components/StatusBadge";
import { Button } from "../components/ui/button";
import { formatDateTime } from "../lib/formatters";

const POLL_INTERVAL_MS = 4000;

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const id = Number(runId);
  const queryClient = useQueryClient();

  const runQuery = useQuery({
    queryKey: ["run", id],
    queryFn: () => fetchRun(id),
    refetchInterval: (query) => (query.state.data?.status !== "completed" ? POLL_INTERVAL_MS : false),
  });

  const sourcesQuery = useQuery({
    queryKey: ["run-sources", id],
    queryFn: () => fetchRunSources(id),
    refetchInterval: (query) => {
      const items = query.state.data;
      const hasActive = items?.some((runSource) => runSource.status === "pending" || runSource.status === "running");
      return hasActive ? POLL_INTERVAL_MS : false;
    },
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelRun(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["run", id] }),
  });

  if (!runQuery.data) return <p>Cargando…</p>;
  const run = runQuery.data;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Run #{run.id}</h1>
        <StatusBadge status={run.status} />
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <dt className="font-medium">Disparado por</dt>
        <dd>{run.triggered_by}</dd>
        <dt className="font-medium">Iniciado</dt>
        <dd>{formatDateTime(run.started_at)}</dd>
        <dt className="font-medium">Finalizado</dt>
        <dd>{formatDateTime(run.finished_at)}</dd>
      </dl>

      {run.status !== "completed" && (
        <Button
          variant="destructive"
          disabled={run.cancel_requested || cancelMutation.isPending}
          onClick={() => cancelMutation.mutate()}
        >
          {run.cancel_requested ? "Cancelación solicitada" : "Cancelar run"}
        </Button>
      )}

      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b">
            <th className="py-2">Fuente (id)</th>
            <th className="py-2">Estado</th>
            <th className="py-2">Docs nuevos</th>
            <th className="py-2">Docs con error</th>
            <th className="py-2">Error</th>
          </tr>
        </thead>
        <tbody>
          {sourcesQuery.data?.map((runSource) => (
            <tr key={runSource.id} className="border-b">
              <td className="py-2">{runSource.source_id}</td>
              <td className="py-2"><StatusBadge status={runSource.status} /></td>
              <td className="py-2">{runSource.docs_new}</td>
              <td className="py-2">{runSource.docs_errors}</td>
              <td className="py-2 text-red-600">{runSource.error_message ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run RunDetailPage.test` (inside `frontend/`)
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/RunDetailPage.tsx frontend/src/pages/RunDetailPage.test.tsx
git commit -m "feat: add RunDetailPage with polling and cancel action"
```

---

### Task 13: DocumentsPage — list, filters, pagination

**Files:**
- Modify: `frontend/src/pages/DocumentsPage.tsx`
- Test: `frontend/src/pages/DocumentsPage.test.tsx`

**Interfaces:**
- Consumes: `fetchDocuments`, `ListDocumentsParams` (Task 5); `formatBytes`, `formatDate` (Task 7); `ErrorBanner` (Task 7).
- Produces: the `["documents", filters, page]` query key and the list/filter/pagination shell that Task 14 extends with the download action.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/DocumentsPage.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { DocumentsPage } from "./DocumentsPage";

const BASE_URL = "http://localhost:8000";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <DocumentsPage />
    </QueryClientProvider>
  );
}

const DOCUMENT = {
  id: 1,
  doc_id: "abc",
  source_id: 1,
  title: "Sentencia C-001-26",
  tipo: "sentencia",
  seccion: null,
  f_public: null,
  f_providencia: "2026-01-15",
  storage_bucket: "iurisync-documents",
  storage_key: "abc.pdf",
  content_type: "application/pdf",
  file_size_bytes: 204800,
  downloaded_at: "2026-07-10T00:00:00Z",
};

describe("DocumentsPage", () => {
  it("renders fetched documents with formatted size", async () => {
    server.use(
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 }))
    );

    renderPage();

    expect(await screen.findByText("Sentencia C-001-26")).toBeInTheDocument();
    expect(screen.getByText("200.0 KB")).toBeInTheDocument();
  });

  it("refetches with the title filter applied", async () => {
    let lastUrl = "";
    server.use(
      http.get(`${BASE_URL}/documents`, ({ request }) => {
        lastUrl = request.url;
        return HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 });
      })
    );
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(lastUrl).toContain("/documents"));
    await user.type(screen.getByPlaceholderText(/buscar por t.tulo/i), "sentencia");

    await waitFor(() => expect(lastUrl).toContain("title=sentencia"));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run DocumentsPage.test` (inside `frontend/`)
Expected: FAIL — the stub page has none of this markup.

- [ ] **Step 3: Implement the list/filter/pagination page**

Replace `frontend/src/pages/DocumentsPage.tsx`:

```tsx
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchDocuments } from "../api/documents";
import { ErrorBanner } from "../components/ErrorBanner";
import { formatBytes, formatDate } from "../lib/formatters";

const PAGE_SIZE = 50;

export function DocumentsPage() {
  const [title, setTitle] = useState("");
  const [tipo, setTipo] = useState("");
  const [page, setPage] = useState(0);

  const documentsQuery = useQuery({
    queryKey: ["documents", title, tipo, page],
    queryFn: () =>
      fetchDocuments({
        title: title || undefined,
        tipo: tipo || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
  });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Documentos</h1>

      <div className="flex gap-3">
        <input
          placeholder="Buscar por título"
          value={title}
          onChange={(event) => {
            setTitle(event.target.value);
            setPage(0);
          }}
          className="rounded border px-2 py-1"
        />
        <input
          placeholder="Tipo"
          value={tipo}
          onChange={(event) => {
            setTipo(event.target.value);
            setPage(0);
          }}
          className="rounded border px-2 py-1"
        />
      </div>

      {documentsQuery.isError && (
        <ErrorBanner message="No se pudieron cargar los documentos." onRetry={() => documentsQuery.refetch()} />
      )}

      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b">
            <th className="py-2">Título</th>
            <th className="py-2">Tipo</th>
            <th className="py-2">Fecha providencia</th>
            <th className="py-2">Tamaño</th>
          </tr>
        </thead>
        <tbody>
          {documentsQuery.data?.items.map((document) => (
            <tr key={document.id} className="border-b">
              <td className="py-2">{document.title}</td>
              <td className="py-2">{document.tipo ?? "—"}</td>
              <td className="py-2">{formatDate(document.f_providencia)}</td>
              <td className="py-2">{formatBytes(document.file_size_bytes)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">Total: {documentsQuery.data?.total ?? 0}</p>
        <div className="flex gap-2">
          <button
            disabled={page === 0}
            onClick={() => setPage((current) => current - 1)}
            className="rounded border px-3 py-1 disabled:opacity-50"
          >
            Anterior
          </button>
          <button
            disabled={(documentsQuery.data?.items.length ?? 0) < PAGE_SIZE}
            onClick={() => setPage((current) => current + 1)}
            className="rounded border px-3 py-1 disabled:opacity-50"
          >
            Siguiente
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run DocumentsPage.test` (inside `frontend/`)
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/DocumentsPage.tsx frontend/src/pages/DocumentsPage.test.tsx
git commit -m "feat: add DocumentsPage list with filters and pagination"
```

---

### Task 14: DocumentsPage — download action

**Files:**
- Modify: `frontend/src/api/documents.ts`
- Modify: `frontend/src/pages/DocumentsPage.tsx`
- Modify: `frontend/src/test/setup.ts`
- Test: `frontend/src/api/documents.test.ts` (extend)
- Test: `frontend/src/pages/DocumentsPage.test.tsx` (extend)

**Interfaces:**
- Consumes: `getStoredApiKey` (Task 4).
- Produces: `downloadDocumentFile(id: number, filename: string): Promise<void>` — fetches the (already-redirect-followed, per browser `fetch` semantics) file bytes with the `X-API-Key` header, and triggers a browser download via a temporary object URL. This is the last DocumentsPage task.

**Why not a plain `<a href>`:** `GET /documents/{id}/download` is behind `require_api_key` (header-only auth), and a normal link/`window.open` navigation cannot attach a custom header. `fetch` can, and it will transparently follow the backend's redirect to the presigned S3/MinIO URL (Task 1 configured bucket CORS so the browser can read that cross-origin response).

- [ ] **Step 1: Stub jsdom's missing `URL.createObjectURL`/`revokeObjectURL`**

Append to `frontend/src/test/setup.ts`:

```ts
if (!URL.createObjectURL) {
  URL.createObjectURL = () => "blob:mock-url";
}
if (!URL.revokeObjectURL) {
  URL.revokeObjectURL = () => {};
}
```

- [ ] **Step 2: Write the failing test for `downloadDocumentFile`**

Append to `frontend/src/api/documents.test.ts`:

```ts
import { vi } from "vitest";
import { downloadDocumentFile } from "./documents";

describe("downloadDocumentFile", () => {
  it("fetches the file and triggers a browser download", async () => {
    server.use(
      http.get(`${BASE_URL}/documents/1/download`, () => new HttpResponse(new Blob(["contenido"], { type: "application/pdf" })))
    );
    const clickSpy = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const element = originalCreateElement(tag);
      if (tag === "a") element.click = clickSpy;
      return element;
    });

    await downloadDocumentFile(1, "sentencia.pdf");

    expect(clickSpy).toHaveBeenCalledOnce();
  });

  it("throws when the download request fails", async () => {
    server.use(http.get(`${BASE_URL}/documents/2/download`, () => new HttpResponse(null, { status: 404 })));

    await expect(downloadDocumentFile(2, "x.pdf")).rejects.toThrow();
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `npx vitest run documents.test` (inside `frontend/`)
Expected: FAIL — `downloadDocumentFile` doesn't exist yet.

- [ ] **Step 4: Implement `downloadDocumentFile`**

Append to `frontend/src/api/documents.ts`:

```ts
import { getStoredApiKey } from "./client";

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function downloadDocumentFile(id: number, filename: string): Promise<void> {
  const apiKey = getStoredApiKey();
  const headers = new Headers();
  if (apiKey) headers.set("X-API-Key", apiKey);

  const response = await fetch(`${BASE_URL}/documents/${id}/download`, { headers });
  if (!response.ok) {
    throw new Error("No se pudo descargar el documento");
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
```

(Move the existing `import { apiFetch, buildQuery } from "./client";` line and this new `getStoredApiKey` import together into one `import { apiFetch, buildQuery, getStoredApiKey } from "./client";` at the top of the file.)

- [ ] **Step 5: Run test to verify it passes**

Run: `npx vitest run documents.test` (inside `frontend/`)
Expected: PASS

- [ ] **Step 6: Write the failing DocumentsPage test for the download button**

Append to `frontend/src/pages/DocumentsPage.test.tsx`:

```tsx
it("triggers a download when the download button is clicked", async () => {
  const user = userEvent.setup();
  server.use(
    http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 })),
    http.get(`${BASE_URL}/documents/1/download`, () => new HttpResponse(new Blob(["x"], { type: "application/pdf" })))
  );
  renderPage();

  await user.click(await screen.findByText("Descargar"));

  await waitFor(() => expect(screen.queryByText(/error al descargar/i)).not.toBeInTheDocument());
});
```

- [ ] **Step 7: Run test to verify it fails**

Run: `npx vitest run DocumentsPage.test` (inside `frontend/`)
Expected: FAIL — no "Descargar" button exists yet.

- [ ] **Step 8: Add the download button to the table**

In `frontend/src/pages/DocumentsPage.tsx`, add the import and a new column:

```tsx
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { downloadDocumentFile, fetchDocuments } from "../api/documents";
import { ErrorBanner } from "../components/ErrorBanner";
import { formatBytes, formatDate } from "../lib/formatters";

// ... inside the component, alongside the other queries:
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const downloadMutation = useMutation({
    mutationFn: ({ id, filename }: { id: number; filename: string }) => downloadDocumentFile(id, filename),
    onError: () => setDownloadError("Error al descargar el documento"),
  });
```

Add a "Descargar" column to the table body:

```tsx
              <td className="py-2">{formatBytes(document.file_size_bytes)}</td>
              <td className="py-2">
                <button
                  onClick={() => downloadMutation.mutate({ id: document.id, filename: `${document.title}.pdf` })}
                  className="text-sm text-blue-600 underline"
                >
                  Descargar
                </button>
              </td>
```

And a header cell:
```tsx
            <th className="py-2">Tamaño</th>
            <th className="py-2">Descargar</th>
```

And render `downloadError` via `ErrorBanner` near the top of the returned JSX, below the existing `documentsQuery.isError` banner:
```tsx
      {downloadError && <ErrorBanner message={downloadError} onRetry={() => setDownloadError(null)} />}
```

- [ ] **Step 9: Run test to verify it passes**

Run: `npx vitest run DocumentsPage.test` (inside `frontend/`)
Expected: PASS (3 tests)

- [ ] **Step 10: Run the full frontend test suite**

Run: `npx vitest run` (inside `frontend/`)
Expected: all tests pass

- [ ] **Step 11: Commit**

```bash
git add frontend/src/api/documents.ts frontend/src/api/documents.test.ts frontend/src/pages/DocumentsPage.tsx frontend/src/pages/DocumentsPage.test.tsx frontend/src/test/setup.ts
git commit -m "feat: add document download action via authenticated blob fetch"
```

---

### Task 15: OverviewPage, frontend README, final wiring check

**Files:**
- Modify: `frontend/src/pages/OverviewPage.tsx`
- Test: `frontend/src/pages/OverviewPage.test.tsx`
- Create: `frontend/README.md`

**Interfaces:**
- Consumes: `fetchSources` (Task 5), `fetchRuns` (Task 5), `fetchDocuments` (Task 5), `StatusBadge` (Task 7), `formatDateTime` (Task 7).
- Produces: nothing — this is the final task. It also performs the plan's final build/test verification across the whole `frontend/` project.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/OverviewPage.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { OverviewPage } from "./OverviewPage";

const BASE_URL = "http://localhost:8000";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("OverviewPage", () => {
  it("renders summary counts and the most recent runs", async () => {
    server.use(
      http.get(`${BASE_URL}/sources`, () =>
        HttpResponse.json([{ id: 1, family_key: "constitucional", name: "Corte Constitucional", family_params: {}, active: true }])
      ),
      http.get(`${BASE_URL}/runs`, () =>
        HttpResponse.json([
          {
            id: 1,
            triggered_by: "manual",
            status: "completed",
            fini: null,
            ffin: null,
            cancel_requested: false,
            started_at: null,
            finished_at: null,
            created_at: new Date().toISOString(),
          },
        ])
      ),
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [], total: 12, limit: 1, offset: 0 }))
    );

    renderPage();

    expect(await screen.findByText("1")).toBeInTheDocument();
    expect(await screen.findByText("12")).toBeInTheDocument();
    expect(screen.getByText("#1")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run OverviewPage.test` (inside `frontend/`)
Expected: FAIL — the stub page has none of this markup.

- [ ] **Step 3: Implement the page**

Replace `frontend/src/pages/OverviewPage.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchDocuments } from "../api/documents";
import { fetchRuns } from "../api/runs";
import { fetchSources } from "../api/sources";
import { StatusBadge } from "../components/StatusBadge";
import { formatDateTime } from "../lib/formatters";

const TWENTY_FOUR_HOURS_MS = 24 * 60 * 60 * 1000;

export function OverviewPage() {
  const activeSourcesQuery = useQuery({
    queryKey: ["sources", "active-count"],
    queryFn: () => fetchSources({ active: true, limit: 100 }),
  });

  const recentRunsQuery = useQuery({
    queryKey: ["runs", "recent"],
    queryFn: () => fetchRuns({ limit: 50 }),
  });

  const documentsCountQuery = useQuery({
    queryKey: ["documents", "total-count"],
    queryFn: () => fetchDocuments({ limit: 1 }),
  });

  const runsLast24h = (recentRunsQuery.data ?? []).filter(
    (run) => Date.now() - new Date(run.created_at).getTime() <= TWENTY_FOUR_HOURS_MS
  );
  const byStatus: Record<string, number> = { pending: 0, running: 0, completed: 0 };
  for (const run of runsLast24h) byStatus[run.status] = (byStatus[run.status] ?? 0) + 1;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Resumen</h1>
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded border p-4">
          <p className="text-sm text-gray-500">Fuentes activas</p>
          <p className="text-3xl font-bold">{activeSourcesQuery.data?.length ?? "—"}</p>
        </div>
        <div className="rounded border p-4">
          <p className="text-sm text-gray-500">Runs (24h)</p>
          <p className="text-3xl font-bold">{runsLast24h.length}</p>
          <p className="text-xs text-gray-500">
            {byStatus.pending} pendientes · {byStatus.running} en curso · {byStatus.completed} completados
          </p>
        </div>
        <div className="rounded border p-4">
          <p className="text-sm text-gray-500">Documentos totales</p>
          <p className="text-3xl font-bold">{documentsCountQuery.data?.total ?? "—"}</p>
        </div>
      </div>

      <div>
        <h2 className="mb-2 text-lg font-medium">Últimos runs</h2>
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b">
              <th className="py-2">ID</th>
              <th className="py-2">Estado</th>
              <th className="py-2">Creado</th>
            </tr>
          </thead>
          <tbody>
            {(recentRunsQuery.data ?? []).slice(0, 5).map((run) => (
              <tr key={run.id} className="border-b">
                <td className="py-2">
                  <Link to={`/runs/${run.id}`} className="text-blue-600 underline">
                    #{run.id}
                  </Link>
                </td>
                <td className="py-2"><StatusBadge status={run.status} /></td>
                <td className="py-2">{formatDateTime(run.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run OverviewPage.test` (inside `frontend/`)
Expected: PASS

- [ ] **Step 5: Write the frontend README**

Create `frontend/README.md`:

```markdown
# IURISYNC Admin Dashboard

Panel interno para gestionar fuentes de scraping, disparar/monitorear runs y buscar documentos. Ver el diseño completo en `docs/superpowers/specs/2026-07-10-admin-dashboard-design.md`.

## Setup local

1. `cd frontend && npm install`
2. `copy .env.example .env` (ajusta `VITE_API_BASE_URL` si el backend no corre en `http://localhost:8000`)
3. Asegúrate de que el backend esté corriendo con `CORS_ORIGINS` incluyendo `http://localhost:5173` (valor por defecto en `.env.example` del backend)

## Correr en desarrollo

`npm run dev` — sirve en `http://localhost:5173`

## Tests

`npm test` (Vitest + React Testing Library + MSW, sin red real)

## Build de producción

`npm run build` — genera `dist/`, servible como estático detrás de cualquier hosting (Nginx, S3+CDN, etc.)

## Login

No hay registro de usuarios: pega una API key creada con `python -m core.manage create-api-key --name "..."` (ver README del backend) en la pantalla de login.
```

- [ ] **Step 6: Run the full frontend test suite**

Run: `npx vitest run` (inside `frontend/`)
Expected: all tests pass

- [ ] **Step 7: Verify the production build succeeds**

Run: `npm run build` (inside `frontend/`)
Expected: exits 0, produces `frontend/dist/`

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/OverviewPage.tsx frontend/src/pages/OverviewPage.test.tsx frontend/README.md
git commit -m "feat: add OverviewPage and frontend README"
```
