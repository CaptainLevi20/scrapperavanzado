# Novedades del día Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Dashboard's "Novedades" panel show only documents ingested *today* (`downloaded_at`), and make its "Ver todos →" link land on the Documents page with that same "today" filter pre-applied and adjustable.

**Architecture:** Add a `downloaded_from`/`downloaded_to` date-range filter to `GET /documents` and `repository.list_documents` (same shape as the existing `f_public_from`/`f_public_to`). The Dashboard passes today's date on both ends of that range for its Novedades query. The Documents page gains a matching "Agregado" date-filter control (same popover pattern as the existing "Fecha de publicación" one) and seeds it from `today` when arriving via a `react-router` `Link state` flag set by the Dashboard's "Ver todos" link.

**Tech Stack:** FastAPI + SQLAlchemy (backend), React + TanStack Query + react-router-dom (frontend), pytest (backend tests), Vitest + Testing Library + MSW (frontend tests).

## Global Constraints

- "Hoy" is computed from the browser's local date, compared against `downloaded_at` (stored UTC) as a UTC calendar-day range — documented, accepted skew of a few hours around midnight, do not add timezone-conversion logic beyond this.
- Do not change `list_documents`'s `ORDER BY` (`f_public DESC NULLS LAST, id DESC`) — it stays the same whether or not `downloaded_from`/`downloaded_to` are supplied.
- Do not use `new Date().toISOString().slice(0, 10)` for "today" anywhere in the frontend — it truncates to UTC and shifts a day in America/Bogota (UTC-5). Use the local-component `todayDateString()` helper built in Task 2.
- No URL query-string filter sync for Documents in general — only the one-shot `location.state` seed described in Task 4.

---

### Task 1: Backend — `downloaded_from`/`downloaded_to` filter on `GET /documents`

**Files:**
- Modify: `core/db/repository.py:257-287` (`list_documents`)
- Modify: `api/routers/documents.py:52-77` (`get_documents`)
- Test: `tests/test_api_documents.py`

**Interfaces:**
- Produces: `repository.list_documents(db, ..., downloaded_from: Optional[date] = None, downloaded_to: Optional[date] = None, ...) -> tuple[list[Document], int]` — new keyword-only-by-convention params, inserted after `f_public_to`.
- Produces: `GET /documents?downloaded_from=YYYY-MM-DD&downloaded_to=YYYY-MM-DD` — same query-param style as the existing `f_public_from`/`f_public_to`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api_documents.py` (place right after `test_list_documents_filters_by_publication_date_range`, following its exact structure):

```python
def test_list_documents_filters_by_downloaded_at_range(api_client, auth_header, db_session):
    from datetime import datetime, timezone

    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session,
        doc_id="doc-ingresado-hoy",
        source_id=source.id,
        title="T-100/24",
        storage_bucket="iurisync-test",
        storage_key="a.pdf",
        downloaded_at=datetime(2026, 7, 23, 15, 0, 0, tzinfo=timezone.utc),
    )
    repository.insert_document(
        db_session,
        doc_id="doc-ingresado-ayer",
        source_id=source.id,
        title="T-200/24",
        storage_bucket="iurisync-test",
        storage_key="b.pdf",
        downloaded_at=datetime(2026, 7, 22, 23, 59, 0, tzinfo=timezone.utc),
    )

    response = api_client.get(
        "/documents",
        params={"downloaded_from": "2026-07-23", "downloaded_to": "2026-07-23"},
        headers=auth_header,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["doc_id"] == "doc-ingresado-hoy"


def test_list_documents_downloaded_at_range_is_inclusive_of_the_whole_end_day(api_client, auth_header, db_session):
    from datetime import datetime, timezone

    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session,
        doc_id="doc-fin-de-dia",
        source_id=source.id,
        title="T-300/24",
        storage_bucket="iurisync-test",
        storage_key="c.pdf",
        downloaded_at=datetime(2026, 7, 23, 23, 59, 59, tzinfo=timezone.utc),
    )

    response = api_client.get(
        "/documents",
        params={"downloaded_from": "2026-07-23", "downloaded_to": "2026-07-23"},
        headers=auth_header,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["doc_id"] == "doc-fin-de-dia"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/test_api_documents.py -k downloaded_at -v`
Expected: FAIL — `TypeError: get_documents() got an unexpected keyword argument` or both documents come back (filter not applied yet), since `downloaded_from`/`downloaded_to` don't exist yet.

- [ ] **Step 3: Add the filter to `repository.list_documents`**

In `core/db/repository.py`, change the signature and body of `list_documents` (currently at lines 257-287):

```python
def list_documents(
    db: Session,
    source_id: Optional[int] = None,
    family_key: Optional[str] = None,
    tipo: Optional[str] = None,
    review_status: Optional[str] = None,
    f_public_from: Optional[date] = None,
    f_public_to: Optional[date] = None,
    downloaded_from: Optional[date] = None,
    downloaded_to: Optional[date] = None,
    title_contains: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Document], int]:
    stmt = select(Document)
    if source_id is not None:
        stmt = stmt.where(Document.source_id == source_id)
    if family_key is not None:
        stmt = stmt.join(Source, Source.id == Document.source_id).where(Source.family_key == family_key)
    if tipo is not None:
        stmt = stmt.where(Document.tipo == tipo)
    if review_status is not None:
        stmt = stmt.where(Document.review_status == review_status)
    if f_public_from is not None:
        stmt = stmt.where(Document.f_public >= f_public_from)
    if f_public_to is not None:
        stmt = stmt.where(Document.f_public <= f_public_to)
    if downloaded_from is not None:
        stmt = stmt.where(
            Document.downloaded_at >= datetime.combine(downloaded_from, datetime.min.time()).replace(tzinfo=timezone.utc)
        )
    if downloaded_to is not None:
        stmt = stmt.where(
            Document.downloaded_at
            < datetime.combine(downloaded_to, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(days=1)
        )
    if title_contains is not None:
        stmt = stmt.where(Document.title.ilike(f"%{title_contains}%"))

    total = len(list(db.scalars(stmt).all()))
    stmt = stmt.order_by(Document.f_public.desc().nulls_last(), Document.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all()), total
```

(`date`, `datetime`, `timedelta`, `timezone` are already imported at the top of this file — no new imports needed.)

- [ ] **Step 4: Wire the params through the API route**

In `api/routers/documents.py`, change `get_documents` (currently lines 52-77):

```python
@router.get("/documents", response_model=PaginatedDocuments)
def get_documents(
    source_id: Optional[int] = None,
    family_key: Optional[str] = None,
    tipo: Optional[str] = None,
    title: Optional[str] = None,
    review_status: Optional[str] = None,
    f_public_from: Optional[date] = None,
    f_public_to: Optional[date] = None,
    downloaded_from: Optional[date] = None,
    downloaded_to: Optional[date] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    items, total = repository.list_documents(
        db,
        source_id=source_id,
        family_key=family_key,
        tipo=tipo,
        review_status=review_status,
        f_public_from=f_public_from,
        f_public_to=f_public_to,
        downloaded_from=downloaded_from,
        downloaded_to=downloaded_to,
        title_contains=title,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}
```

(`date` is already imported at the top of this file.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/test_api_documents.py -k downloaded_at -v`
Expected: `2 passed`

- [ ] **Step 6: Run the full backend suite to check for regressions**

Run: `.venv/Scripts/pytest -q`
Expected: 2 more passing than before this task (the 2 new tests from Step 1), same 1 pre-existing `test_migrations.py` failure documented in `.claude/skills/run-iurisync/SKILL.md`'s Gotchas — unrelated, Windows-only. No other test should regress.

- [ ] **Step 7: Commit**

```bash
git add core/db/repository.py api/routers/documents.py tests/test_api_documents.py
git commit -m "feat: add downloaded_at date-range filter to GET /documents"
```

---

### Task 2: Frontend — `todayDateString()` helper and API client params

**Files:**
- Modify: `frontend/src/lib/formatters.ts`
- Modify: `frontend/src/api/documents.ts:6-17` (`ListDocumentsParams`)
- Test: `frontend/src/lib/formatters.test.ts`

**Interfaces:**
- Produces: `todayDateString(): string` (in `frontend/src/lib/formatters.ts`) — returns today's local date as `"YYYY-MM-DD"`.
- Produces: `ListDocumentsParams` gains `downloaded_from?: string` and `downloaded_to?: string`.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/lib/formatters.test.ts`:

```typescript
import { formatBytes, formatDate, formatDateTime, todayDateString } from "./formatters";

describe("todayDateString", () => {
  it("returns today's local date as YYYY-MM-DD, not shifted by UTC conversion", () => {
    vi.useFakeTimers();
    // 2026-07-23T02:00:00 UTC is still 2026-07-22 in America/Bogota (UTC-5) —
    // this pins system time to exercise exactly the shift formatDate's
    // parseDateOnlyAsLocal comment already warns about, but for "today"
    // instead of a parsed date string.
    vi.setSystemTime(new Date("2026-07-23T02:00:00Z"));

    const result = todayDateString();

    expect(result).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(result).toBe(
      `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, "0")}-${String(new Date().getDate()).padStart(2, "0")}`
    );

    vi.useRealTimers();
  });
});
```

Update the top import line of `frontend/src/lib/formatters.test.ts` to also import `vi` from `vitest`:

```typescript
import { describe, expect, it, vi } from "vitest";
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run formatters`
Expected: FAIL — `todayDateString is not exported` / `is not a function`

- [ ] **Step 3: Implement `todayDateString()`**

In `frontend/src/lib/formatters.ts`, add this function right after `parseDateOnlyAsLocal` (after line 21, before `formatDate`):

```typescript
// Mirrors parseDateOnlyAsLocal's fix in reverse: build "today" from local
// Y/M/D components instead of `new Date().toISOString().slice(0, 10)`, which
// truncates to UTC and would report yesterday's date in the evening in
// America/Bogota (UTC-5).
export function todayDateString(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --run formatters`
Expected: PASS

- [ ] **Step 5: Add the new params to `ListDocumentsParams`**

In `frontend/src/api/documents.ts`, change the interface (currently lines 6-17):

```typescript
export interface ListDocumentsParams {
  source_id?: number;
  family_key?: string;
  tipo?: string;
  title?: string;
  review_status?: DocumentReviewStatus;
  f_public_from?: string;
  f_public_to?: string;
  downloaded_from?: string;
  downloaded_to?: string;
  limit?: number;
  offset?: number;
  [key: string]: string | number | boolean | undefined;
}
```

- [ ] **Step 6: Run the frontend test suite to check for regressions**

Run: `cd frontend && npm test -- --run`
Expected: same pass count as before this task (no existing test references `ListDocumentsParams` shape directly, so this should be a no-op change as far as tests go).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/formatters.ts frontend/src/lib/formatters.test.ts frontend/src/api/documents.ts
git commit -m "feat: add todayDateString helper and downloaded_at params to documents API client"
```

---

### Task 3: Dashboard — scope "Novedades" to today's ingested documents

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/pages/DashboardPage.test.tsx`

**Interfaces:**
- Consumes: `todayDateString()` from `frontend/src/lib/formatters.ts` (Task 2).
- Consumes: `fetchDocuments({ downloaded_from, downloaded_to, limit })` from `frontend/src/api/documents.ts` (Task 2 added the params; the function signature itself is unchanged).
- Produces: Dashboard's `<Link to="/documents" state={{ downloadedToday: true }}>` — the `{ downloadedToday: true }` shape Task 4 reads via `useLocation()`.

- [ ] **Step 1: Write the failing test**

In `frontend/src/pages/DashboardPage.test.tsx`, replace the `mockDocuments()` helper (currently lines 74-93) to assert the Novedades request now carries `downloaded_from`/`downloaded_to`, and update the empty-state test. First, add this new test right after the existing `"renders the Novedades table with the most recent documents"` test (after line 167):

```typescript
  it("requests Novedades scoped to today's downloaded_at range, and shows a today-specific empty state", async () => {
    mockBaselines();
    server.use(
      http.get(`${BASE_URL}/documents/stats`, () => HttpResponse.json(STATS)),
      http.get(`${BASE_URL}/documents`, ({ request }) => {
        const url = new URL(request.url);
        if (url.searchParams.get("review_status") === "pending") {
          return HttpResponse.json({ items: [], total: 2, limit: 1, offset: 0 });
        }
        if (url.searchParams.get("limit") === "1") {
          return HttpResponse.json({ items: [], total: 12, limit: 1, offset: 0 });
        }
        // novedades fetch (limit=8) — assert it now carries the today range
        expect(url.searchParams.get("downloaded_from")).toMatch(/^\d{4}-\d{2}-\d{2}$/);
        expect(url.searchParams.get("downloaded_to")).toBe(url.searchParams.get("downloaded_from"));
        return HttpResponse.json({ items: [], total: 0, limit: 8, offset: 0 });
      })
    );

    renderPage();

    const novedadesHeading = await screen.findByText("Novedades");
    const novedadesSection = novedadesHeading.closest("div.space-y-3") as HTMLElement;
    await waitFor(() => expect(within(novedadesSection).getByText("No han llegado documentos hoy.")).toBeInTheDocument());
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run DashboardPage`
Expected: FAIL — `downloaded_from` search param is `null` (not yet sent), and/or the empty-state text `"No han llegado documentos hoy."` is not found (current text is `"Todavía no ha llegado ningún documento."`).

- [ ] **Step 3: Implement the panel changes**

In `frontend/src/pages/DashboardPage.tsx`:

Add the import (alongside the existing `formatDateTime, formatRelativeTime` import on line 11):

```typescript
import { formatDateTime, formatRelativeTime, todayDateString } from "../lib/formatters";
```

Replace the `novedadesQuery` definition (currently lines 128-131):

```typescript
  const today = todayDateString();
  const novedadesQuery = useQuery({
    queryKey: ["documents", "novedades", today],
    queryFn: () => fetchDocuments({ downloaded_from: today, downloaded_to: today, limit: 8 }),
  });
```

Replace the Novedades section's `EmptyState` (currently line 256):

```tsx
          {novedades.length === 0 && <EmptyState message="No han llegado documentos hoy." />}
```

Replace the "Ver todos →" link (currently lines 225-227):

```tsx
          <Link to="/documents" state={{ downloadedToday: true }} className="text-sm font-medium text-sello-ink hover:underline">
            Ver todos →
          </Link>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --run DashboardPage`
Expected: PASS (all `DashboardPage` tests, including the new one)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/DashboardPage.tsx frontend/src/pages/DashboardPage.test.tsx
git commit -m "feat: scope Dashboard Novedades panel to today's ingested documents"
```

---

### Task 4: Documents page — "Agregado" date filter, seeded from the Dashboard link

**Files:**
- Modify: `frontend/src/pages/DocumentsPage.tsx`
- Modify: `frontend/src/pages/DocumentsPage.test.tsx`

**Interfaces:**
- Consumes: `todayDateString()` from `frontend/src/lib/formatters.ts` (Task 2).
- Consumes: `location.state` shape `{ downloadedToday?: boolean }` produced by the Dashboard's link (Task 3).
- Consumes: `fetchDocuments({ downloaded_from, downloaded_to, ... })` (Task 2 added the params).

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/pages/DocumentsPage.test.tsx`, a new `renderPageWithTodayState` helper and test, placed after the existing `renderPage` helper (after line 21):

```typescript
function renderPageWithTodayState() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[{ pathname: "/documents", state: { downloadedToday: true } }]}>
        <DocumentsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}
```

Then add this test at the end of the `describe("DocumentsPage", ...)` block:

```typescript
  it("seeds the Agregado filter with today's date when arriving with downloadedToday state, and sends it to the API", async () => {
    mockFilterEndpoints();
    let capturedUrl: URL | undefined;
    server.use(
      http.get(`${BASE_URL}/documents`, ({ request }) => {
        capturedUrl = new URL(request.url);
        return HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 });
      })
    );

    renderPageWithTodayState();

    await screen.findByText("Sentencia C-001-26");
    await waitFor(() => expect(capturedUrl?.searchParams.get("downloaded_from")).toMatch(/^\d{4}-\d{2}-\d{2}$/));
    expect(capturedUrl?.searchParams.get("downloaded_to")).toBe(capturedUrl?.searchParams.get("downloaded_from"));

    const agregadoButton = screen.getByRole("button", { name: /Agregado/ });
    expect(agregadoButton.className).toMatch(/border-sello/);
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run DocumentsPage`
Expected: FAIL — no button named `/Agregado/` exists yet, and `downloaded_from`/`downloaded_to` are never sent.

- [ ] **Step 3: Implement the "Agregado" filter**

In `frontend/src/pages/DocumentsPage.tsx`:

Update the import line (currently line 1) to include `useLocation`:

```typescript
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";
```

Update the `formatDate` import (currently line 15) to also bring in `todayDateString`:

```typescript
import { formatDate, todayDateString } from "../lib/formatters";
```

Inside `DocumentsPage()`, right after the existing `fPublicFrom`/`fPublicTo`/`dateFilterOpen` state (currently lines 43-45), add:

```typescript
  const location = useLocation();
  const seedToday = (location.state as { downloadedToday?: boolean } | null)?.downloadedToday === true;
  const [downloadedFrom, setDownloadedFrom] = useState(() => (seedToday ? todayDateString() : ""));
  const [downloadedTo, setDownloadedTo] = useState(() => (seedToday ? todayDateString() : ""));
  const [downloadedFilterOpen, setDownloadedFilterOpen] = useState(false);
```

Add a second ref alongside `dateFilterRef` (currently line 49):

```typescript
  const dateFilterRef = useRef<HTMLDivElement>(null);
  const downloadedFilterRef = useRef<HTMLDivElement>(null);
```

Extend the outside-click effect (currently lines 51-60) to also close the new popover — replace it with:

```typescript
  useEffect(() => {
    if (!dateFilterOpen && !downloadedFilterOpen) return;
    function handleClickOutside(event: MouseEvent) {
      if (dateFilterOpen && dateFilterRef.current && !dateFilterRef.current.contains(event.target as Node)) {
        setDateFilterOpen(false);
      }
      if (downloadedFilterOpen && downloadedFilterRef.current && !downloadedFilterRef.current.contains(event.target as Node)) {
        setDownloadedFilterOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [dateFilterOpen, downloadedFilterOpen]);
```

Update `documentsQuery` (currently lines 90-103) to include the new params in both the key and the fetch:

```typescript
  const documentsQuery = useQuery({
    queryKey: ["documents", title, tipo, sourceId, reviewStatus, fPublicFrom, fPublicTo, downloadedFrom, downloadedTo, page],
    queryFn: () =>
      fetchDocuments({
        title: title || undefined,
        tipo: tipo || undefined,
        source_id: sourceId ? Number(sourceId) : undefined,
        review_status: reviewStatus || undefined,
        f_public_from: fPublicFrom || undefined,
        f_public_to: fPublicTo || undefined,
        downloaded_from: downloadedFrom || undefined,
        downloaded_to: downloadedTo || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
  });
```

Add `const hasDownloadedFilter = !!downloadedFrom || !!downloadedTo;` right after `const hasDateFilter = !!fPublicFrom || !!fPublicTo;` (currently line 111).

Add the new filter control's JSX right after the closing `</div>` of the existing date-filter `<div className="relative" ref={dateFilterRef}>` block (currently ends at line 241, right before the `<Button variant="outline" onClick={() => bulkDownloadMutation.mutate()}...` block):

```tsx
        <div className="relative" ref={downloadedFilterRef}>
          <button
            onClick={() => setDownloadedFilterOpen((open) => !open)}
            className={`flex h-9 items-center gap-1.5 rounded-md border-[1.5px] px-3 text-sm font-medium transition-colors ${
              hasDownloadedFilter
                ? "border-sello/50 bg-sello/10 text-sello-ink"
                : "border-input bg-background text-muted-foreground hover:text-foreground"
            }`}
          >
            <Calendar className="size-3.5" aria-hidden="true" />
            {formatDateFilterLabel(downloadedFrom, downloadedTo) === "Fecha de publicación"
              ? "Agregado"
              : `Agregado: ${formatDateFilterLabel(downloadedFrom, downloadedTo)}`}
          </button>
          {downloadedFilterOpen && (
            <div className="absolute top-full left-0 z-20 mt-2 flex w-64 flex-col gap-3 rounded-lg border border-border bg-card p-3 shadow-md">
              <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
                Desde
                <input
                  type="date"
                  value={downloadedFrom}
                  onChange={(event) => {
                    setDownloadedFrom(event.target.value);
                    setPage(0);
                  }}
                  className="h-8 rounded-md border-[1.5px] border-input bg-background px-2 text-sm outline-none focus-visible:border-ring"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
                Hasta
                <input
                  type="date"
                  value={downloadedTo}
                  onChange={(event) => {
                    setDownloadedTo(event.target.value);
                    setPage(0);
                  }}
                  className="h-8 rounded-md border-[1.5px] border-input bg-background px-2 text-sm outline-none focus-visible:border-ring"
                />
              </label>
              {hasDownloadedFilter && (
                <button
                  onClick={() => {
                    setDownloadedFrom("");
                    setDownloadedTo("");
                    setPage(0);
                  }}
                  className="text-left text-xs font-semibold text-muted-foreground underline underline-offset-2 hover:text-foreground"
                >
                  Limpiar
                </button>
              )}
            </div>
          )}
        </div>
```

(This reuses `formatDateFilterLabel`, already defined at the top of the file — it returns `"Fecha de publicación"` when both inputs are empty regardless of which filter calls it, which is why the button label above special-cases that placeholder string rather than reusing it verbatim.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --run DocumentsPage`
Expected: PASS (all `DocumentsPage` tests, including the new one)

- [ ] **Step 5: Run the full frontend suite to check for regressions**

Run: `cd frontend && npm test -- --run`
Expected: same pass count as before this task plus the 2 new tests (1 in `DashboardPage.test.tsx`, 1 in `DocumentsPage.test.tsx`) — no existing test should break.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/DocumentsPage.tsx frontend/src/pages/DocumentsPage.test.tsx
git commit -m "feat: add Agregado date filter to Documents page, seeded from Dashboard Novedades link"
```

---

## Manual Verification (after all tasks)

- [ ] Start the app per `.claude/skills/run-iurisync/SKILL.md` (`uvicorn`, `celery`, `npm run dev`).
- [ ] Log in, go to the Dashboard. Confirm "Novedades" shows only documents whose `downloaded_at` is today (or the empty state if none), not just the 8 most-recently-published overall.
- [ ] Click "Ver todos →". Confirm it lands on `/documents` with the "Agregado" filter button showing today's date range already active (highlighted), and the table only shows today's ingested documents.
- [ ] Clear the "Agregado" filter on the Documents page and confirm the full archive reappears (filter is a normal, removable filter — not locked).
