# Dashboard: mostrar todas las fuentes/tipos en "Documentos por tipo" y "Documentos por fuente"

## Problema

Las tarjetas "Documentos por tipo" y "Documentos por fuente" del dashboard
(`frontend/src/pages/DashboardPage.tsx`) no muestran fuentes/tipos con poco
volumen — por ejemplo, MinCIT (12 documentos) no aparece.

No es un problema visual de recorte: el backend limita ambas métricas a los
primeros 8 resultados (`core/db/repository.py`, `count_documents_by_source` y
`count_documents_by_tipo`, ambas con `limit: int = 8`, ordenadas por cantidad
descendente). Hoy hay 12 fuentes con documentos y 13 tipos distintos en la
base de desarrollo, así que cualquier fuente/tipo fuera del top 8 por volumen
simplemente no llega al frontend.

## Alcance

- Quitar el límite de 8 en `count_documents_by_source` y
  `count_documents_by_tipo` — son las únicas dos funciones que alimentan el
  endpoint de stats (`GET /documents/stats`, `api/routers/documents.py`), sin
  otro caller que dependa de un tope, así que no hace falta dejar el
  parámetro como opcional "por si acaso".
- Mantener el orden actual (cantidad descendente) — no se pide cambiarlo,
  solo que no se corte.
- Agregar scroll interno a la tarjeta en el frontend para que, con más de 8
  resultados, la tarjeta mantenga su tamaño actual (~8 filas visibles) y el
  resto se vea bajando dentro de ella, en vez de que la tarjeta crezca sin
  límite.

Fuera de alcance: cambiar el orden de la lista, agregar filtros/búsqueda
dentro de la tarjeta, o tocar las otras métricas del dashboard (Actividad
mensual, Novedades, Últimos runs) — ninguna de esas tiene el mismo problema.

## Backend

En `core/db/repository.py`:

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

(se quita el parámetro `limit` y el `.limit(limit)` de ambas — el resto de
cada función queda igual). `api/routers/documents.py` no necesita cambios:
ya llama a ambas sin pasar `limit`.

## Frontend

En `frontend/src/pages/DashboardPage.tsx`, el componente `BarList` (usado por
ambas tarjetas) se envuelve en un contenedor con altura máxima fija y scroll
vertical:

```tsx
function BarList({ data }: { data: CountBucket[] }) {
  if (data.length === 0) {
    return <p className="text-sm text-muted-foreground">Sin datos suficientes todavía.</p>;
  }
  const max = Math.max(...data.map((d) => d.count), 1);
  return (
    <div className="max-h-72 space-y-2.5 overflow-y-auto pr-1">
      {data.map((bucket) => (
        /* ... contenido de cada bucket, sin cambios ... */
      ))}
    </div>
  );
}
```

`max-h-72` (18rem/288px) aproxima las ~8 filas que se ven hoy sin necesidad
de scroll — con 8 o menos resultados no cambia nada visualmente (no aparece
la barra de scroll si el contenido cabe). El `pr-1` evita que la barra de
scroll del navegador tape el número de la última columna.

## Pruebas

- Backend (`tests/test_api_documents.py`): un test con documentos repartidos
  en más de 8 fuentes distintas y más de 8 tipos distintos, confirmando que
  `by_source`/`by_tipo` en la respuesta de `/documents/stats` los trae todos
  — no solo los primeros 8. Regresión directa contra el bug reportado.
- Frontend (`DashboardPage.test.tsx`): un test con más de 8 entradas en
  `by_source`/`by_tipo` (mock de `/documents/stats`), confirmando que todas
  las etiquetas están presentes en el DOM de la tarjeta correspondiente.
