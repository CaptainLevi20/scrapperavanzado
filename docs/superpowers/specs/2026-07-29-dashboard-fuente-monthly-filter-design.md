# Dashboard: filtro mensual en "Documentos por fuente"

## Problema

"Documentos por fuente" siempre muestra el total histórico de documentos de
cada fuente, sin forma de acotarlo a un mes específico. El usuario quiere ver
cuántos documentos aportó cada fuente en un mes puntual, no solo su total
acumulado.

## Alcance

- Agregar un selector de mes a la tarjeta "Documentos por fuente" del
  dashboard (`frontend/src/pages/DashboardPage.tsx`). Por defecto ("Todos los
  meses") se comporta exactamente igual que hoy — total histórico, sin
  filtrar.
- El selector de mes usa el **mismo año** que ya gobierna la tarjeta
  "Actividad mensual" (su selector de año existente) — no se agrega un
  segundo selector de año. Un solo control de año en el dashboard.
- "Documentos por tipo" no se toca — sigue mostrando el total histórico, sin
  filtro de mes.

Fuera de alcance: cambiar el orden de las barras, agregar un selector de año
independiente para esta tarjeta, o exponer el filtro mensual en "Documentos
por tipo".

## Backend

En `core/db/repository.py`, `count_documents_by_source` gana dos parámetros
opcionales:

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

Sin `year`/`month` (caso por defecto), el `WHERE` no se agrega y el
comportamiento es idéntico al actual (total histórico). Usa la misma
`_effective_date_expr()` (fecha de publicación, con `downloaded_at` como
respaldo) que ya usa `count_documents_by_month`, para que "mes N" signifique
lo mismo en ambas tarjetas.

En `api/routers/documents.py`, `GET /documents/stats` gana el query param
`month: Optional[int] = None`. Cuando `month` viene, se le pasa a
`count_documents_by_source` junto con el `effective_year` ya calculado (el
mismo que usa `count_documents_by_month`); cuando no viene, se llama sin
`year`/`month` (total histórico, sin cambios de comportamiento):

```python
def get_document_stats(year: Optional[int] = None, month: Optional[int] = None, db: Session = Depends(get_db)):
    ...
    available_years = repository.list_document_years(db)
    effective_year = year if year is not None else (available_years[0] if available_years else date.today().year)
    by_month = repository.count_documents_by_month(db, effective_year)
    by_source = [
        {"id": source_id, "name": name, "count": count}
        for source_id, name, count in repository.count_documents_by_source(
            db, year=effective_year if month is not None else None, month=month
        )
    ]
```

## Frontend

En `DashboardPage.tsx`:

- Nuevo estado `selectedMonth: number | null` (`null` = "Todos los meses").
- `statsQuery` agrega `selectedMonth` a su `queryKey` y a los parámetros que
  le pasa a `fetchDocumentStats` (que gana un parámetro `month?: number`
  junto al `year?: number` que ya tiene, en `frontend/src/api/documents.ts`).
- En el encabezado de la tarjeta "Documentos por fuente" se agrega un
  `NativeSelect` con opciones "Todos los meses" (valor vacío) + los 12 meses
  (reutilizando `MONTH_LABELS`, ya definido en este archivo) — mismo patrón
  visual que el selector de año de "Actividad mensual".
- Al elegir un mes, `sourceBuckets` (ya calculado desde
  `statsQuery.data?.by_source`) refleja automáticamente los conteos
  filtrados que devuelve el backend — no hace falta lógica de filtrado en el
  frontend.

## Pruebas

- Backend (`tests/test_api_documents.py`): un test con documentos de una
  misma fuente repartidos en distintos meses/años, confirmando que pedir
  `?month=N` filtra `by_source` correctamente al mes/año pedido, y que
  omitir `month` mantiene el total histórico (regresión directa: no debe
  cambiar el comportamiento por defecto).
- Frontend (`DashboardPage.test.tsx`): un test que selecciona un mes en el
  selector nuevo de "Documentos por fuente" y confirma (a) que la petición a
  `/documents/stats` incluye ese `month` como query param, y (b) que las
  barras de la tarjeta reflejan los datos filtrados que devuelve el mock (no
  los del total histórico).
