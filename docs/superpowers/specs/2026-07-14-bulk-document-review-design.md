# Marcado en lote de documentos (útil/no útil) — Diseño

Fecha: 2026-07-14

## Contexto y objetivo

La feature de estado de revisión (`docs/superpowers/specs/2026-07-14-document-review-status-design.md`, ya mergeada) agregó el marcado individual por fila en `DocumentsPage`: dos botones "Útil"/"No útil" por documento, respaldados por `PATCH /documents/{id}`. Marcar documentos de a uno es lento cuando hay muchos por revisar del mismo lote (ej. todos los resultados de un run, o todos los que coinciden con un filtro).

Este diseño agrega selección múltiple sobre la tabla y una acción de marcado en lote que aplica a todos los documentos seleccionados de una sola vez.

Explícitamente fuera de alcance (confirmado con el usuario):
- Exclusión/filtrado automático de documentos `not_useful` de otras vistas — el estado de revisión sigue siendo puramente informativo, tal como en el diseño anterior.
- Selección que persista entre páginas o cambios de filtro — se resetea siempre que cambia lo que se está viendo.
- Un tercer botón de lote para revertir a `"pending"` — mismo alcance que el marcado individual (no existe ese botón tampoco ahí).

## Backend

### `PATCH /documents/bulk-review` (nuevo endpoint)

- Body: `BulkDocumentReviewUpdate { document_ids: list[int] (mínimo 1 elemento), review_status: Literal["pending", "useful", "not_useful"] }`. Una lista vacía o un `review_status` fuera de esas 3 opciones devuelve 422 automático (validación de Pydantic — `document_ids` usa `conlist(int, min_length=1)` o el `Field(min_length=1)` equivalente).
- Llama a `repository.bulk_update_document_review_status(db, document_ids, review_status) -> int`.
- Devuelve `{"updated": N}` donde `N` es la cantidad de filas realmente actualizadas (puede ser menor a `len(document_ids)` si algún id no existe — no es un error, simplemente no cuenta; en la práctica el frontend solo envía ids que acaba de listar desde `GET /documents`, así que este caso no debería ocurrir).

### `repository.bulk_update_document_review_status`

Un solo `UPDATE documents SET review_status = :status, reviewed_at = :now WHERE id IN (:ids)` (vía SQLAlchemy Core `update()`, no un loop de N updates individuales) — una sola vuelta a la base de datos sin importar cuántos documentos se marquen. Devuelve `result.rowcount`.

## Frontend

### Selección

- Nueva columna de checkbox, primera de la tabla. Un checkbox por fila (`aria-label` con el título del documento) más un checkbox en el encabezado que selecciona/deselecciona todos los documentos actualmente visibles en la página (no todos los que existan bajo el filtro — solo los cargados en esa página de 50).
- Estado local `const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())`.
- La selección se limpia (`setSelectedIds(new Set())`) dentro de cada `onChange` de filtro (Título, Tipo, Fuente, Familia, Revisión) y dentro de los handlers de "Anterior"/"Siguiente" — el mismo lugar donde ya se resetea `page` a `0`, sin introducir un `useEffect` nuevo.

### Barra de acción en lote

- Se renderiza solo cuando `selectedIds.size > 0`, entre los banners de error existentes y la tabla.
- Muestra el conteo ("N seleccionados") y dos botones: "Marcar como útil" y "Marcar como no útil".
- Un clic dispara la nueva mutation de lote con `Array.from(selectedIds)` y el estado correspondiente.
- Al completarse con éxito: invalida `["documents"]` (mismo query key que ya invalida el marcado individual) y limpia `selectedIds`.

### API client

Nueva función en `frontend/src/api/documents.ts`:

```typescript
export function bulkUpdateDocumentReviewStatus(
  documentIds: number[],
  review_status: DocumentReviewStatus
): Promise<{ updated: number }> {
  return apiFetch<{ updated: number }>("/documents/bulk-review", {
    method: "PATCH",
    body: JSON.stringify({ document_ids: documentIds, review_status }),
  });
}
```

## Manejo de errores

- `document_ids` vacío o `review_status` inválido → 422 automático (Pydantic), sin código adicional.
- Fallo de red al aplicar el lote: se reutiliza el patrón `ErrorBanner` ya existente en la página (nuevo estado `bulkError`, mismo tratamiento que `downloadError`/`reviewError`).
- Un id inexistente dentro del lote no es un error — simplemente no se refleja en el conteo devuelto; no hay caso especial que manejar en el frontend porque los ids siempre provienen de una lista recién cargada.

## Testing y validación

- **Backend**: test de `repository.bulk_update_document_review_status` (marca varios documentos de una vez, verifica `review_status`/`reviewed_at` en cada uno, y que el conteo devuelto sea correcto); tests de `PATCH /documents/bulk-review` (éxito, 422 con lista vacía, 422 con `review_status` inválido).
- **Frontend**: seleccionar dos documentos vía checkboxes y verificar que el checkbox "seleccionar todos" refleja el estado; hacer clic en "Marcar como útil" en lote y verificar que el `PATCH /documents/bulk-review` se dispara con los ids y estado correctos, y que la selección se limpia después; cambiar cualquier filtro y verificar que la selección se resetea.

## Fuera de alcance

- Exclusión/filtrado automático de documentos `not_useful` de otras vistas.
- Selección persistente entre páginas o cambios de filtro.
- Botón de lote para revertir a `"pending"`.
- Selección de "todos los documentos que coinciden con el filtro" más allá de la página actual (ej. un botón "seleccionar los 369 resultados") — solo aplica a lo cargado en pantalla.
