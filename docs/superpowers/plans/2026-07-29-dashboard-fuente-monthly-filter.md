# Dashboard Fuente Monthly Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a month filter to the "Documentos por fuente" dashboard card, so it can show each source's document count for a specific month instead of only its all-time total.

**Architecture:** Backend: `count_documents_by_source` gains optional `year`/`month` filters (reusing the same effective-date expression `count_documents_by_month` already uses), exposed via a new `month` query param on `GET /documents/stats`. Frontend: a new `selectedMonth` state feeds that param into the existing `statsQuery`, with a month `<select>` added to the "Documentos por fuente" card header (mirroring the year `<select>` already on "Actividad mensual").

**Tech Stack:** Python/SQLAlchemy/FastAPI (backend), React/TypeScript/TanStack Query/Tailwind (frontend), pytest (backend tests), Vitest + Testing Library + MSW (frontend tests).

## Global Constraints

- Omitting `month` must leave `by_source` byte-for-byte identical to today's all-time total — this is the default state ("Todos los meses").
- The month filter uses the **same year** already selected by "Actividad mensual"'s existing year `<select>` — no second year selector.
- "Documentos por tipo" is untouched — no month filter there.
- "Month" means the same effective date `count_documents_by_month` already uses (`f_public`, falling back to `downloaded_at`) — not a different date field.

---

### Task 1: Backend — scope `count_documents_by_source` to a year/month

**Files:**
- Modify: `core/db/repository.py:490-498`
- Modify: `api/routers/documents.py:116-140`
- Test: `tests/test_api_documents.py`

**Interfaces:**
- Consumes: `_effective_date_expr()` (already defined in `core/db/repository.py:511-515`, no changes needed).
- Produces: `count_documents_by_source(db: Session, year: Optional[int] = None, month: Optional[int] = None) -> list[tuple[int, str, int]]` — same return shape as today; `GET /documents/stats` accepts a new optional `month` query param (int, 1-12).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api_documents.py` (after `test_get_document_stats_does_not_cap_by_source_or_by_tipo_at_eight`, at the end of the file):

```python
def test_get_document_stats_by_source_can_be_scoped_to_a_month(api_client, auth_header, db_session):
    # Regression + feature test: by_source defaults to the all-time total
    # (unchanged from today), but passing year+month scopes it down to just
    # that month — using the same effective date (f_public, falling back to
    # downloaded_at) that by_month already uses.
    from datetime import date

    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(
        db_session, family_key="constitucional", name="Corte Constitucional", family_params={}
    )

    repository.insert_document(
        db_session, doc_id="doc-marzo", source_id=source.id, title="Doc marzo",
        tipo="Sentencia", storage_bucket="iurisync-test", storage_key="doc-marzo.pdf",
        f_public=date(2026, 3, 15),
    )
    repository.insert_document(
        db_session, doc_id="doc-abril-1", source_id=source.id, title="Doc abril 1",
        tipo="Sentencia", storage_bucket="iurisync-test", storage_key="doc-abril-1.pdf",
        f_public=date(2026, 4, 5),
    )
    repository.insert_document(
        db_session, doc_id="doc-abril-2", source_id=source.id, title="Doc abril 2",
        tipo="Sentencia", storage_bucket="iurisync-test", storage_key="doc-abril-2.pdf",
        f_public=date(2026, 4, 20),
    )
    repository.insert_document(
        db_session, doc_id="doc-otro-anio", source_id=source.id, title="Doc otro año",
        tipo="Sentencia", storage_bucket="iurisync-test", storage_key="doc-otro-anio.pdf",
        f_public=date(2025, 4, 10),
    )

    # Sin mes: comportamiento actual, total histórico (las 4).
    response = api_client.get("/documents/stats", headers=auth_header)
    assert response.status_code == 200
    by_source = {row["name"]: row["count"] for row in response.json()["by_source"]}
    assert by_source == {"Corte Constitucional": 4}

    # Con mes: solo abril de 2026 (2 documentos) — no marzo de 2026 ni abril de 2025.
    response = api_client.get("/documents/stats", params={"year": 2026, "month": 4}, headers=auth_header)
    assert response.status_code == 200
    by_source = {row["name"]: row["count"] for row in response.json()["by_source"]}
    assert by_source == {"Corte Constitucional": 2}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_documents.py::test_get_document_stats_by_source_can_be_scoped_to_a_month -v`
Expected: FAIL — the second assertion fails because `/documents/stats?year=2026&month=4` currently ignores `month` entirely (no such query param exists yet) and returns the same all-time total (4) both times, so `by_source == {"Corte Constitucional": 2}` fails with `{"Corte Constitucional": 4} != {"Corte Constitucional": 2}`.

- [ ] **Step 3: Add year/month scoping to `count_documents_by_source`**

In `core/db/repository.py`, replace lines 490-498:

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
```

with:

```python
def count_documents_by_source(
    db: Session, year: Optional[int] = None, month: Optional[int] = None
) -> list[tuple[int, str, int]]:
    stmt = (
        select(Source.id, Source.name, func.count(Document.id))
        .select_from(Document)
        .join(Source, Source.id == Document.source_id)
    )
    if year is not None:
        date_expr = _effective_date_expr()
        stmt = stmt.where(func.extract("year", date_expr) == year)
        if month is not None:
            stmt = stmt.where(func.extract("month", date_expr) == month)
    stmt = stmt.group_by(Source.id, Source.name).order_by(func.count(Document.id).desc())
    return list(db.execute(stmt).all())
```

`_effective_date_expr` is defined later in the same file (line 511) but Python resolves the name at call time, not definition time, so this forward reference inside the function body is fine — no reordering needed.

- [ ] **Step 4: Wire the `month` query param through the endpoint**

In `api/routers/documents.py`, replace the `get_document_stats` function (lines 116-140):

```python
@router.get("/documents/stats", response_model=DocumentStatsOut)
def get_document_stats(year: Optional[int] = None, db: Session = Depends(get_db)):
    display_name_by_key = {family.key: family.display_name for family in repository.list_source_families(db)}
    by_family = [
        {"key": key, "display_name": display_name_by_key.get(key, key), "count": count}
        for key, count in repository.count_documents_by_family(db)
    ]
    by_tipo = [{"tipo": tipo, "count": count} for tipo, count in repository.count_documents_by_tipo(db)]
    by_source = [
        {"id": source_id, "name": name, "count": count}
        for source_id, name, count in repository.count_documents_by_source(db)
    ]

    available_years = repository.list_document_years(db)
    effective_year = year if year is not None else (available_years[0] if available_years else date.today().year)
    by_month = repository.count_documents_by_month(db, effective_year)

    return {
        "by_family": by_family,
        "by_tipo": by_tipo,
        "by_source": by_source,
        "by_month": by_month,
        "year": effective_year,
        "available_years": available_years,
    }
```

with:

```python
@router.get("/documents/stats", response_model=DocumentStatsOut)
def get_document_stats(year: Optional[int] = None, month: Optional[int] = None, db: Session = Depends(get_db)):
    display_name_by_key = {family.key: family.display_name for family in repository.list_source_families(db)}
    by_family = [
        {"key": key, "display_name": display_name_by_key.get(key, key), "count": count}
        for key, count in repository.count_documents_by_family(db)
    ]
    by_tipo = [{"tipo": tipo, "count": count} for tipo, count in repository.count_documents_by_tipo(db)]

    available_years = repository.list_document_years(db)
    effective_year = year if year is not None else (available_years[0] if available_years else date.today().year)
    by_month = repository.count_documents_by_month(db, effective_year)

    by_source = [
        {"id": source_id, "name": name, "count": count}
        for source_id, name, count in repository.count_documents_by_source(
            db, year=effective_year if month is not None else None, month=month
        )
    ]

    return {
        "by_family": by_family,
        "by_tipo": by_tipo,
        "by_source": by_source,
        "by_month": by_month,
        "year": effective_year,
        "available_years": available_years,
    }
```

(`by_source` moved below `effective_year`/`by_month` since it now depends on `effective_year`; `by_family`/`by_tipo` stay where they were, unaffected.)

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_api_documents.py::test_get_document_stats_by_source_can_be_scoped_to_a_month -v`
Expected: PASS

- [ ] **Step 6: Run the full stats test group to confirm no regression**

Run: `python -m pytest tests/test_api_documents.py -v -k stats`
Expected: PASS (all three stats tests: the full-table-aggregation test, the no-cap-at-8 test, and the new month-scoping test)

- [ ] **Step 7: Commit**

```bash
git add core/db/repository.py api/routers/documents.py tests/test_api_documents.py
git commit -m "feat: agrega filtro de mes/año a count_documents_by_source"
```

---

### Task 2: Frontend — month selector on "Documentos por fuente"

**Files:**
- Modify: `frontend/src/api/documents.ts:32-34`
- Modify: `frontend/src/pages/DashboardPage.tsx:136-140,185-198`
- Test: `frontend/src/pages/DashboardPage.test.tsx`

**Interfaces:**
- Consumes: `GET /documents/stats?year=&month=` (Task 1, already deployed by this point in the plan).
- Produces: `fetchDocumentStats(year?: number, month?: number): Promise<DocumentStats>` — same return type as today, with a new optional second parameter. No other file calls `fetchDocumentStats` besides `DashboardPage.tsx` (confirmed by the existing single call site), so this signature change is safe.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/pages/DashboardPage.test.tsx`, inside the `describe("DashboardPage", ...)` block (after the existing `"shows every source/tipo from the stats endpoint..."` test):

```tsx
  it("filters Documentos por fuente by month when a month is selected", async () => {
    mockBaselines();
    const user = userEvent.setup();
    let statsRequestedMonth: string | null = null;
    server.use(
      http.get(`${BASE_URL}/documents/stats`, ({ request }) => {
        const url = new URL(request.url);
        const month = url.searchParams.get("month");
        statsRequestedMonth = month;
        if (month === "4") {
          return HttpResponse.json({ ...STATS, by_source: [{ id: 1, name: "Corte Constitucional", count: 5 }] });
        }
        return HttpResponse.json(STATS);
      }),
      http.get(`${BASE_URL}/documents`, () => HttpResponse.json({ items: [], total: 0, limit: 1, offset: 0 }))
    );

    renderPage();

    const fuenteHeading = await screen.findByText("Documentos por fuente");
    const fuenteCard = fuenteHeading.closest(".rounded-lg") as HTMLElement;
    await waitFor(() => expect(within(fuenteCard).getByText("Consejo de Estado")).toBeInTheDocument());

    const monthSelect = within(fuenteCard).getByLabelText("Mes");
    await user.selectOptions(monthSelect, "4");

    await waitFor(() => expect(statsRequestedMonth).toBe("4"));
    await waitFor(() => expect(within(fuenteCard).queryByText("Consejo de Estado")).not.toBeInTheDocument());
    expect(within(fuenteCard).getByText("5")).toBeInTheDocument();
  });
```

`user` needs `userEvent.setup()` — already imported at the top of this file (`import userEvent from "@testing-library/user-event";`, used by other tests in the file), no new import needed.

- [ ] **Step 2: Run test to verify it fails**

Run (from `frontend/`): `npx vitest run src/pages/DashboardPage.test.tsx -t "filters Documentos por fuente by month"`
Expected: FAIL — `within(fuenteCard).getByLabelText("Mes")` throws because no such label/control exists yet in the "Documentos por fuente" card.

- [ ] **Step 3: Add `month` to `fetchDocumentStats`**

In `frontend/src/api/documents.ts`, replace lines 32-34:

```ts
export function fetchDocumentStats(year?: number): Promise<DocumentStats> {
  return apiFetch<DocumentStats>(`/documents/stats${buildQuery({ year })}`);
}
```

with:

```ts
export function fetchDocumentStats(year?: number, month?: number): Promise<DocumentStats> {
  return apiFetch<DocumentStats>(`/documents/stats${buildQuery({ year, month })}`);
}
```

- [ ] **Step 4: Add `selectedMonth` state and wire it into `statsQuery`**

In `frontend/src/pages/DashboardPage.tsx`, replace lines 136-140:

```tsx
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const statsQuery = useQuery({
    queryKey: ["documents", "stats", selectedYear],
    queryFn: () => fetchDocumentStats(selectedYear ?? undefined),
  });
```

with:

```tsx
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [selectedMonth, setSelectedMonth] = useState<number | null>(null);
  const statsQuery = useQuery({
    queryKey: ["documents", "stats", selectedYear, selectedMonth],
    queryFn: () => fetchDocumentStats(selectedYear ?? undefined, selectedMonth ?? undefined),
  });
```

- [ ] **Step 5: Add the month `<select>` to the "Documentos por fuente" card**

In `frontend/src/pages/DashboardPage.tsx`, replace lines 185-198:

```tsx
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <h2 className="font-display text-lg font-semibold text-foreground">Documentos por tipo</h2>
          <div className="mt-4">
            <BarList data={tipoBuckets} />
          </div>
        </div>
        <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <h2 className="font-display text-lg font-semibold text-foreground">Documentos por fuente</h2>
          <div className="mt-4">
            <BarList data={sourceBuckets} />
          </div>
        </div>
      </div>
```

with:

```tsx
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <h2 className="font-display text-lg font-semibold text-foreground">Documentos por tipo</h2>
          <div className="mt-4">
            <BarList data={tipoBuckets} />
          </div>
        </div>
        <div className="rounded-lg border border-border bg-card p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-lg font-semibold text-foreground">Documentos por fuente</h2>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              Mes
              <NativeSelect
                value={selectedMonth === null ? "" : String(selectedMonth)}
                onChange={(event) => setSelectedMonth(event.target.value === "" ? null : Number(event.target.value))}
                className="w-36"
              >
                <option value="">Todos los meses</option>
                {MONTH_LABELS.map((label, index) => (
                  <option key={label} value={index + 1}>
                    {label}
                  </option>
                ))}
              </NativeSelect>
            </label>
          </div>
          <div className="mt-4">
            <BarList data={sourceBuckets} />
          </div>
        </div>
      </div>
```

- [ ] **Step 6: Run test to verify it passes**

Run (from `frontend/`): `npx vitest run src/pages/DashboardPage.test.tsx -t "filters Documentos por fuente by month"`
Expected: PASS

- [ ] **Step 7: Run the full DashboardPage test file to confirm no regression**

Run (from `frontend/`): `npx vitest run src/pages/DashboardPage.test.tsx`
Expected: PASS (all tests in the file — including the existing "renders the Documentos por tipo and por fuente charts..." and "offers only the years the stats endpoint reports as available" tests, which must still pass since the year `<select>` and its behavior are untouched)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/documents.ts frontend/src/pages/DashboardPage.tsx frontend/src/pages/DashboardPage.test.tsx
git commit -m "feat: agrega selector de mes a Documentos por fuente"
```

---

## Verificación final

- [ ] **Correr toda la suite backend**

Run: `python -m pytest -q` (requiere `docker compose up -d` para Postgres/MinIO)
Expected: PASS, sin regresiones.

- [ ] **Correr toda la suite frontend**

Run (from `frontend/`): `npx vitest run`
Expected: PASS, sin regresiones.

- [ ] **Correr el build/type-check** (el mismo que corre en CI)

Run (from `frontend/`): `npm run build`
Expected: éxito, sin errores de TypeScript (`tsc -b && vite build`).

- [ ] **Probar en el navegador (smoke test manual)**

Con el backend y frontend de desarrollo corriendo, abrir el dashboard y: (1) confirmar que "Documentos por fuente" con "Todos los meses" muestra los mismos totales que antes de este cambio; (2) elegir un mes distinto en el selector nuevo y confirmar que las barras cambian para reflejar solo ese mes (en el año que esté seleccionado en "Actividad mensual"); (3) confirmar que "Documentos por tipo" no cambia al mover el selector de mes.
