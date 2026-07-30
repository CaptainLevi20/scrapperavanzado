# Dashboard Metric Scroll Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make "Documentos por tipo" and "Documentos por fuente" on the dashboard show every source/tipo with at least one document (not just the top 8), with an internal scroll in each card so the card's height doesn't grow unbounded.

**Architecture:** Backend: drop the hardcoded `limit=8` from the two SQLAlchemy count queries that feed `GET /documents/stats`. Frontend: wrap the existing `BarList` component's list in a fixed-max-height, vertically-scrollable container — no new component, no new endpoint.

**Tech Stack:** Python/SQLAlchemy (backend), React/TypeScript/Tailwind (frontend), pytest (backend tests), Vitest + Testing Library + MSW (frontend tests).

## Global Constraints

- Order stays count-descending (unchanged) — only the cap is removed, not the sort.
- No new query parameters, no pagination, no "ver más" button — just show everything, scrolled.
- `max-h-72` (18rem/288px) approximates the ~8 rows visible today; with 8 or fewer results no scrollbar should appear.
- Out of scope: Actividad mensual, Novedades, Últimos runs — none of those cards have this bug.

---

### Task 1: Remove the top-8 cap on document counts by source and by tipo

**Files:**
- Modify: `core/db/repository.py:490-510`
- Test: `tests/test_api_documents.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `count_documents_by_source(db: Session) -> list[tuple[int, str, int]]` and `count_documents_by_tipo(db: Session) -> list[tuple[str, int]]` — same names and return shapes as today, just without a `limit` parameter. `api/routers/documents.py` already calls both with no `limit` argument, so it needs no change.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api_documents.py` (after `test_get_document_stats_aggregates_over_the_full_table_not_a_sample`, which already exists at the end of the file):

```python
def test_get_document_stats_does_not_cap_by_source_or_by_tipo_at_eight(api_client, auth_header, db_session):
    # Regression guard: count_documents_by_source/count_documents_by_tipo used
    # to hard-cap results at limit=8 (ordered by count desc), so a low-volume
    # source or tipo past the top 8 silently never reached the dashboard —
    # e.g. a newly added source with few documents so far.
    from datetime import date

    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")

    tipos = [f"Tipo{i}" for i in range(10)]
    for i in range(10):
        source = repository.create_source(
            db_session, family_key="constitucional", name=f"Fuente {i}", family_params={}
        )
        repository.insert_document(
            db_session,
            doc_id=f"doc-{i}",
            source_id=source.id,
            title=f"Documento {i}",
            tipo=tipos[i],
            storage_bucket="iurisync-test",
            storage_key=f"doc-{i}.pdf",
            f_public=date(2026, 3, 10),
        )

    response = api_client.get("/documents/stats", headers=auth_header)

    assert response.status_code == 200
    body = response.json()
    assert len(body["by_source"]) == 10
    assert {row["name"] for row in body["by_source"]} == {f"Fuente {i}" for i in range(10)}
    assert len(body["by_tipo"]) == 10
    assert {row["tipo"] for row in body["by_tipo"]} == set(tipos)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_documents.py::test_get_document_stats_does_not_cap_by_source_or_by_tipo_at_eight -v`
Expected: FAIL — `assert len(body["by_source"]) == 10` fails because only 8 rows come back (`assert 8 == 10`).

- [ ] **Step 3: Remove the limit from both repository functions**

In `core/db/repository.py`, replace lines 490-510:

```python
def count_documents_by_source(db: Session, limit: int = 8) -> list[tuple[int, str, int]]:
    stmt = (
        select(Source.id, Source.name, func.count(Document.id))
        .select_from(Document)
        .join(Source, Source.id == Document.source_id)
        .group_by(Source.id, Source.name)
        .order_by(func.count(Document.id).desc())
        .limit(limit)
    )
    return list(db.execute(stmt).all())


def count_documents_by_tipo(db: Session, limit: int = 8) -> list[tuple[str, int]]:
    tipo_expr = func.coalesce(Document.tipo, "Sin tipo")
    stmt = (
        select(tipo_expr, func.count(Document.id))
        .group_by(tipo_expr)
        .order_by(func.count(Document.id).desc())
        .limit(limit)
    )
    return list(db.execute(stmt).all())
```

with:

```python
def count_documents_by_source(db: Session) -> list[tuple[int, str, int]]:
    stmt = (
        select(Source.id, Source.name, func.count(Document.id))
        .select_from(Document)
        .join(Source, Source.id == Document.source_id)
        .group_by(Source.id, Source.name)
        .order_by(func.count(Document.id).desc())
    )
    return list(db.execute(stmt).all())


def count_documents_by_tipo(db: Session) -> list[tuple[str, int]]:
    tipo_expr = func.coalesce(Document.tipo, "Sin tipo")
    stmt = (
        select(tipo_expr, func.count(Document.id))
        .group_by(tipo_expr)
        .order_by(func.count(Document.id).desc())
    )
    return list(db.execute(stmt).all())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_documents.py::test_get_document_stats_does_not_cap_by_source_or_by_tipo_at_eight -v`
Expected: PASS

- [ ] **Step 5: Run the full stats test group to confirm no regression**

Run: `python -m pytest tests/test_api_documents.py -v -k stats`
Expected: PASS (both `test_get_document_stats_aggregates_over_the_full_table_not_a_sample` and the new test)

- [ ] **Step 6: Commit**

```bash
git add core/db/repository.py tests/test_api_documents.py
git commit -m "fix: no limitar Documentos por tipo/fuente a los primeros 8 resultados"
```

---

### Task 2: Add internal scroll to the dashboard metric cards

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx:64-89`
- Test: `frontend/src/pages/DashboardPage.test.tsx`

**Interfaces:**
- Consumes: `CountBucket[]` (unchanged, from `frontend/src/lib/dashboardStats.ts`).
- Produces: no new exports — `BarList` keeps the same props (`{ data: CountBucket[] }`) and is used identically by both "Documentos por tipo" and "Documentos por fuente" cards, unchanged.

This task depends on Task 1 only conceptually (the bug it demonstrates is fully reproducible with a frontend-only mock, no real backend needed — the test below mocks `/documents/stats` directly, so Task 1 does not need to be deployed for this task's test to pass).

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/pages/DashboardPage.test.tsx`, inside the `describe("DashboardPage", ...)` block (after the existing `"renders the Documentos por tipo and por fuente charts..."` test):

```tsx
  it("shows every source/tipo from the stats endpoint, even past the old 8-item cap, inside a scrollable card", async () => {
    mockBaselines();
    server.use(
      http.get(`${BASE_URL}/documents/stats`, () =>
        HttpResponse.json({
          ...STATS,
          by_source: Array.from({ length: 10 }, (_, index) => ({
            id: index + 1,
            name: `Fuente ${index + 1}`,
            count: 10 - index,
          })),
          by_tipo: Array.from({ length: 10 }, (_, index) => ({
            tipo: `Tipo ${index + 1}`,
            count: 10 - index,
          })),
        })
      ),
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [], total: 0, limit: 1, offset: 0 }))
    );

    renderPage();

    const fuenteHeading = await screen.findByText("Documentos por fuente");
    const fuenteCard = fuenteHeading.closest(".rounded-lg") as HTMLElement;
    await waitFor(() => expect(within(fuenteCard).getByText("Fuente 1")).toBeInTheDocument());
    expect(within(fuenteCard).getByText("Fuente 10")).toBeInTheDocument();
    const fuenteScroll = within(fuenteCard).getByText("Fuente 1").closest(".overflow-y-auto");
    expect(fuenteScroll).not.toBeNull();

    const tipoHeading = screen.getByText("Documentos por tipo");
    const tipoCard = tipoHeading.closest(".rounded-lg") as HTMLElement;
    expect(within(tipoCard).getByText("Tipo 1")).toBeInTheDocument();
    expect(within(tipoCard).getByText("Tipo 10")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/DashboardPage.test.tsx -t "scrollable card"`
Expected: FAIL — `expect(fuenteScroll).not.toBeNull()` fails because `BarList`'s container has no `overflow-y-auto` class yet (all 10 items still render, since nothing currently caps them client-side, but there's no scroll container).

- [ ] **Step 3: Add the scroll container to `BarList`**

In `frontend/src/pages/DashboardPage.tsx`, in the `BarList` component, change line 70 from:

```tsx
      <div className="space-y-2.5">
```

to:

```tsx
      <div className="max-h-72 space-y-2.5 overflow-y-auto pr-1">
```

(the rest of `BarList`, lines 71-88, is unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/DashboardPage.test.tsx -t "scrollable card"`
Expected: PASS

- [ ] **Step 5: Run the full DashboardPage test file to confirm no regression**

Run: `cd frontend && npx vitest run src/pages/DashboardPage.test.tsx`
Expected: PASS (all tests in the file, including the pre-existing "renders the Documentos por tipo and por fuente charts..." test)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/DashboardPage.tsx frontend/src/pages/DashboardPage.test.tsx
git commit -m "feat: agrega scroll interno a las tarjetas de Documentos por tipo/fuente"
```

---

## Verificación final

- [ ] **Correr toda la suite backend**

Run: `python -m pytest -q` (requiere `docker compose up -d` para Postgres/MinIO)
Expected: PASS, sin regresiones.

- [ ] **Correr toda la suite frontend**

Run: `cd frontend && npx vitest run`
Expected: PASS, sin regresiones.

- [ ] **Probar contra el sitio real (smoke test manual)**

Con el backend y frontend de desarrollo corriendo y la fuente MinCIT ya sembrada (ver sesión anterior), abrir el dashboard en el navegador y confirmar que "Ministerio de Comercio, Industria y Turismo" aparece en la tarjeta "Documentos por fuente" (haciendo scroll si hace falta) y que las tarjetas no crecieron de tamaño respecto a como se veían antes.
