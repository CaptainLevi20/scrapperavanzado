# Propagar "Útil" a todas las actuaciones de un caso

**Fecha:** 2026-09-03
**Tipo:** arquitectural (cambia la semántica de "marcar útil" + toca base de datos, worker y frontend)

## Problema

Hoy, marcar un documento como "Útil" afecta solo esa fila. Un caso con varias
actuaciones (cada actuación es un `Document` propio, con su `review_status`)
exige marcar una por una, y es fácil que se descargue el caso incompleto. El
usuario necesita: marcar cualquier documento relacionado marca todos, para que
la descarga masiva traiga el caso completo — incluidas las versiones archivadas.

## Alcance

- **Sí:** propagación dentro de un grupo de actuaciones (misma familia + mismo
  título), en los dos endpoints de marcado; simétrico para los tres estados;
  herencia del estado al llegar una actuación nueva; versiones archivadas
  dentro del ZIP de descarga masiva.
- **No:** cruce entre fuentes distintas (mismo radicado vía `CaseLink`).
  Documentos sueltos (fuentes sin actuaciones) siguen igual.

## Definición de "grupo"

Para un `Document` `d` con familia `fam`:

- Si `es_familia_con_actuaciones(fam, d.title)` es verdadero (familias
  `rama_judicial` y `samai`), el grupo son todos los `Document` con
  `(Source.family_key == fam, Document.title == d.title)` — la misma señal que
  `list_documents_by_title_within_family` / `actuacion_counts_by_title` /
  el panel "Otras actuaciones de este caso" del visor.
- Si no, el grupo es `{d}` (documento suelto: nada que propagar).

Las versiones archivadas (`DocumentVersion`) **no** son miembros del grupo — no
tienen `review_status` propio; viajan con su actuación vigente.

## Cambios

### 1. `core/db/repository.py` — propagación al marcar

**Nuevo helper interno:**

```
_expandir_a_grupos(db, document_ids) -> list[int]
```

Carga los `Document` por id, y para cada uno cuyo `(familia, título)` sea de
caso, añade los ids de todas sus actuaciones hermanas. Devuelve la lista de ids
única (incluye los originales). Un id de documento suelto se devuelve tal cual.

**`update_document_review_status(db, document_id, review_status)`** (botón
individual, `PATCH /documents/{id}`):

- Expande `[document_id]` con `_expandir_a_grupos`.
- Aplica `review_status`, `reviewed_at = now`, `bulk_download_id = NULL` a todas
  esas filas (un solo `UPDATE ... WHERE id IN (...)`).
- Devuelve el `Document` originalmente pedido (refrescado) — la respuesta del
  endpoint no cambia de forma.
- Si el documento no existe, devuelve `None` como hoy.

**`bulk_update_document_review_status(db, document_ids, review_status)`**
(selección múltiple, `PATCH /documents/bulk-review`):

- Expande `document_ids` con `_expandir_a_grupos` antes del `UPDATE` existente.
- `rowcount` devuelto refleja todas las filas afectadas (incluye hermanas).

Simétrico: sirve para `useful`, `not_useful` y `pending`. Marcar/desmarcar
cualquiera del grupo mueve a todo el grupo.

### 2. `worker/tasks.py` — herencia al llegar una actuación nueva (opción C)

`scrape_source_task` ya acumula `titulos_con_actuacion_nueva: set[(family_key,
title)]` y, al final, dispara `reconcile_title_group_task.delay(...)` por cada
uno. En ese mismo bucle se añade una llamada síncrona (usa la `db` de la tarea,
las filas nuevas ya están commiteadas):

```
repository.heredar_review_status_de_actuaciones_existentes(db, family_key, title)
```

**Nueva función en `repository.py`:**

- Carga el grupo `(family_key, title)`.
- Mira el `review_status` de los miembros que **no** están en `pending`.
- Si todos esos coinciden en un mismo estado (`useful` o `not_useful`) y hay al
  menos uno, aplica ese estado (+ `reviewed_at = now`, `bulk_download_id = NULL`)
  a los miembros que estén en `pending`.
- Si el grupo está todo en `pending`, o los no-`pending` están en desacuerdo
  (datos heredados de antes de este cambio), no toca nada — la actuación nueva
  queda `pending`.

### 3. `worker/tasks.py` — versiones archivadas en el ZIP

En `build_bulk_download_zip`, para cada `Document` útil de
`list_useful_documents`:

- Traer `repository.list_document_versions(db, document.id)`.
- Por cada `DocumentVersion`, añadir una entrada al ZIP con:
  - contenido descargado de `version.storage_bucket` / `version.storage_key`;
  - `arcname` = `nombre_archivo_version(document, version, fam, tiene_actuaciones)`
    saneado con `_INVALID_FILENAME_CHARS`, en la misma carpeta
    `Fuente/Fecha/Tipo/` que la versión vigente.

`_nombres_zip` se extiende (o se le agrega un acompañante) para producir también
los nombres de las versiones, manteniendo la correspondencia posicional con la
lista de objetos a descargar.

**Estimación de espacio:** `known_sizes` incluye ahora `file_size_bytes` de las
versiones archivadas además de las vigentes; si a alguna versión le falta el
tamaño registrado, se omite el chequeo (igual que hoy con los documentos).

**"Ya entregado":** sigue viviendo en `Document.bulk_download_id`. Las versiones
de un documento entregado se consideran entregadas con él; al borrar una
descarga masiva, el reset de `bulk_download_id` en el `Document` las vuelve a
habilitar junto con su padre. `list_useful_documents` no cambia.

### 4. Frontend — `frontend/src/components/DocumentPreviewDialog.tsx`

Cambio mínimo. Al marcar (individual o hermana) ya se invalida la query
`["documents"]`; tras la propagación, el refetch muestra todo el grupo con el
estado nuevo. Además, para que el panel "Otras actuaciones de este caso" no se
quede desactualizado hasta el refetch, `markMutation`/`markOtherMutation`
actualizan el `documentsSnapshot` de **todas** las filas del mismo caso
(mismo `title` + misma fuente), no solo la fila tocada.

Los botones por-actuación siguen existiendo (marcar cualquiera = marcar todas);
convertirlos en indicador de solo lectura queda como posible segundo paso, fuera
de este spec.

## Pruebas

**`tests/test_repository.py`:**

- `update_document_review_status` sobre una actuación marca las hermanas del
  mismo `(familia, título)`; no toca documentos de otro título ni de otra
  familia; un documento suelto solo se afecta a sí mismo.
- Simetría: lo anterior vale para `useful`, `not_useful` y `pending`.
- `bulk_update_document_review_status` expande cada id de la selección a su
  grupo; `rowcount` cuenta las hermanas.
- `heredar_review_status_de_actuaciones_existentes`: grupo uniforme en `useful`
  → la actuación `pending` pasa a `useful`; grupo todo `pending` → sin cambios;
  grupo con no-`pending` en desacuerdo → sin cambios.

**`tests/test_tasks.py` (o `tests/test_worker_zip_names.py`):**

- El ZIP de descarga masiva incluye las versiones archivadas de un documento
  útil, con el nombre `..._<fecha>-v<n>.<ext>` en su carpeta.
- La estimación de espacio suma el tamaño de las versiones.
- `scrape_source_task`: al registrar una actuación nueva de un caso ya marcado
  `useful`, la fila nueva queda `useful`.

**`frontend/src/components/DocumentPreviewDialog.test.tsx`:**

- Marcar una actuación actualiza el estado de todas las filas del mismo caso en
  el panel "Otras actuaciones".

## Riesgos y notas

- **Datos heredados:** grupos que hoy tienen estados mezclados no se "curan"
  solos; el primer marcado manual posterior los deja uniformes. La herencia
  (sección 2) es deliberadamente conservadora ante el desacuerdo.
- **Volumen de escritura:** marcar un caso escribe N filas en vez de 1. N es
  pequeño (actuaciones de un mismo radicado); un solo `UPDATE`.
- **`reviewed_at`:** todas las filas del grupo quedan con el mismo timestamp del
  momento del marcado, aunque algunas no se hayan "revisado" visualmente. Es el
  comportamiento buscado (el grupo se revisa como unidad).
