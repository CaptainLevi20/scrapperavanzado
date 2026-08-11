# Diseño: Sincronizar el nombre del archivo en MinIO con el nombre canónico

**Fecha:** 2026-08-11
**Estado:** Aprobado el diseño; pendiente plan de implementación.

## Problema

El nombre canónico (`core/naming.py`, ver spec
`2026-08-10-nombre-canonico-versionado-actuaciones-design.md` y su corrección
`2026-08-11` sobre "solo el año sin otra actuación") se calcula al momento de
mostrar o descargar un documento — nunca toca el archivo real guardado en
MinIO. Esto fue deliberado en el diseño original ("Enfoque calculado, sin
tocar almacenamiento") para evitar el riesgo de renombrados masivos.

En la práctica, esto significa que el archivo dentro de MinIO **nunca ha
tenido** fecha ni versión en su nombre — ni siquiera antes de que existiera
esta función. Por ejemplo, para `T_CUND_25307_33_33_003_2024_00094_01`, el
archivo guardado es literalmente `.../T_CUND_25307_33_33_003_2024_00094_01.pdf`,
mientras que la app ya puede mostrar `..._2026.pdf` o `..._20260806.pdf`.

El usuario necesita que el nombre sea **el mismo en todo lado, todo el
tiempo**: en la tabla de Documentos, en la descarga individual, en el archivo
guardado en MinIO, y en la descarga masiva (ZIP).

## Objetivo

Que el `storage_key` de cada documento (y de cada versión archivada) en MinIO
refleje siempre el nombre canónico vigente de ese documento — inicialmente
(con un backfill de lo que ya existe) y de ahí en adelante, cada vez que algo
cambie ese nombre (llega una actuación nueva para el mismo caso, se republica
un documento, se edita el título a mano).

## Enfoque elegido: disparo inmediato + barrido periódico como red de seguridad

Se evaluaron tres opciones (ver conversación de brainstorming):

- **Elegida:** disparar una tarea en segundo plano cada vez que algo puede
  cambiar el nombre de un documento (o de sus "hermanos" — otras actuaciones
  del mismo caso), **más** una tarea programada que recorre todo el archivo
  cada noche para corregir lo que se haya quedado pendiente por una falla.
  Esa misma tarea de barrido sirve como el backfill inicial.
- **Descartada — solo barrido periódico:** más simple (un solo camino de
  código), pero un documento podría tardar hasta un día en reflejar su nombre
  correcto en MinIO tras un cambio. No cumple con la expectativa de
  inmediatez.
- **Descartada — renombrar solo al descargar:** los documentos "hermanos" que
  nadie descarga directamente se quedarían con el nombre viejo
  indefinidamente. No cumple con "renombrado automático en cascada", ya
  decidido.

Todos los caminos de disparo llaman al **mismo motor central** de
reconciliación (ver Componentes) — no se duplica la lógica de "¿cuál es el
nombre correcto y hace falta renombrar?" en cada uno.

## Componentes

### 1. Motor central: `core/storage_sync.py` (nuevo)

- `reconcile_document(db, document, family_key, tiene_actuaciones) -> bool`:
  calcula el nombre esperado con `nombre_documento` (sin extensión) y
  `core.utils.rekey_filename(document.storage_key, nombre_esperado)` para
  obtener la nueva clave (conserva carpeta y extensión, mismo mecanismo que ya
  usa `core/backfill_csj_storage_keys.py`). Si difiere del `storage_key`
  actual: llama a `core.storage.rename_object` (ya existe — copia+borra del
  lado del servidor) y, **solo si eso tiene éxito**, actualiza `storage_key`
  en la base (`repository.update_document_storage_key`, ya existe). Atrapa
  cualquier excepción, la registra en el log y devuelve `False` sin propagar
  el error.
- `reconcile_document_versions(db, document, family_key, tiene_actuaciones) -> int`:
  igual, para cada `DocumentVersion` archivada de ese documento, usando
  `nombre_version` y una función nueva `repository.update_document_version_storage_key`.
- `reconcile_title_group(db, family_key, title) -> dict`: obtiene todos los
  documentos con ese título dentro de esa familia (función nueva
  `repository.list_documents_by_title_within_family`), calcula
  `tiene_actuaciones = len(documentos) > 1` una sola vez para el grupo, y
  llama a `reconcile_document` + `reconcile_document_versions` para cada uno.
- `reconcile_all(db) -> dict`: recorre todos los documentos. Para familias con
  actuaciones (`rama_judicial`, `samai`), agrupa por `(family_key, title)` y
  llama a `reconcile_title_group` una vez por grupo (evita recalcular el
  conteo por cada documento). Para el resto, `tiene_actuaciones` siempre es
  `False`; solo aplica la regla de versión (`_v{n}`).

### 2. Cambios en `core/db/repository.py`

- `list_documents_by_title_within_family(db, family_key, title) -> list[Document]`
  (nueva).
- `update_document_version_storage_key(db, version_id, storage_key) -> Optional[DocumentVersion]`
  (nueva, mismo patrón que `update_document_storage_key`).

### 3. Tareas en segundo plano: `worker/storage_sync_tasks.py` (nuevo archivo)

- `reconcile_title_group_task(family_key, title)`.
- `reconcile_document_task(document_id)`.
- `reconcile_all_task()` — registrada en `worker/beat_schedule.py` con un
  horario nocturno (ej. `crontab(hour=2, minute=0)`), siguiendo el mismo
  patrón que la tarea diaria de descarga ya existente.

### 4. Puntos de disparo

- **`scrape_source_task`** (`worker/tasks.py`): al terminar de procesar un
  `run_source`, junta los `(family_key, title)` distintos de los documentos
  **nuevos** insertados que pertenecen a una familia con actuaciones y cuyo
  título tiene forma de caso — por cada uno, `.delay()` a
  `reconcile_title_group_task`. Para cada documento **republicado**
  (`archive_and_replace_document`), `.delay(document.id)` a
  `reconcile_document_task`.
- **`patch_document_title`** (`api/routers/documents.py`): tras
  `update_document_title`, `.delay(document.id)` a `reconcile_document_task`.
  (Efectos de segundo orden sobre otros documentos que compartían el título
  viejo/nuevo quedan cubiertos por el barrido nocturno, no por un disparo
  inmediato adicional — es una acción administrativa poco frecuente.)

### 5. Backfill inicial

Script delgado `core/backfill_storage_key_sync.py` que llama a
`core.storage_sync.reconcile_all`, corrida manual única
(`python -m core.backfill_storage_key_sync`), mismo patrón que los backfills
anteriores (`backfill_version_no.py`, `backfill_csj_storage_keys.py`).

## Manejo de errores y casos límite

- Un renombrado fallido nunca bloquea ni hace fallar la descarga, la
  republicación o la edición que lo disparó: los disparos son `.delay()`
  independientes (fire-and-forget), y `reconcile_*` atrapa sus propios
  errores.
- `storage_key` en la base **solo** se actualiza si el renombrado en MinIO ya
  tuvo éxito — base de datos y MinIO nunca quedan en desacuerdo entre sí,
  aunque puedan quedar temporalmente detrás del nombre "ideal".
- Lo que falle queda pendiente y se corrige solo en el siguiente barrido
  nocturno (mismo mecanismo que el backfill inicial, re-ejecutado).
- Caso raro aceptado como limitación conocida: si el renombrado falla justo
  entre "copiar" y "borrar" dentro de `rename_object`, podría quedar una
  copia duplicada bajo la clave nueva, sin que la base la sepa. No se
  construye protección adicional para esto — es poco probable y de bajo
  impacto (espacio de almacenamiento extra, no pérdida ni corrupción de
  datos).
- `preview_storage_key` (el PDF de previsualización auto-generado) **no** se
  renombra — el nombre que ve el usuario en la previsualización ya sale
  correcto vía `Content-Disposition` en el momento de la petición,
  independientemente de cómo se llame ese archivo de caché interno.

## Pruebas

- **`core/storage_sync.py`** (con la base y el bucket de prueba, mismo patrón
  que las pruebas ya existentes de descarga masiva): `reconcile_document`
  renombra cuando el nombre calculado no coincide y no hace nada cuando ya
  coincide; `reconcile_title_group` corrige a todos los hermanos cuando el
  conteo real cambia; `reconcile_all` recorre varias familias sin mezclar
  conteos entre ellas.
- **Tareas Celery** (`task_always_eager`, patrón ya usado en
  `tests/test_tasks.py`): se disparan en el momento correcto (actuación
  nueva durante una descarga, republicación, edición de título); si el
  renombrado falla (mock de `rename_object` lanzando una excepción), la
  tarea que lo disparó igual termina en su estado normal, sin quedar
  atascada.
- **Regresión con el ejemplo real:** un documento sin otra actuación →
  backfill lo deja con `_2026`; llega una segunda actuación con el mismo
  título → ambos (el nuevo y el que ya existía) quedan con fecha completa
  en MinIO.
- **Repositorio:** `list_documents_by_title_within_family` y
  `update_document_version_storage_key` con pruebas unitarias directas.
- **Tarea nocturna:** corre sobre datos desincronizados a propósito (para
  simular una falla anterior) y los corrige.

Nota: las suites de BD se corren de forma dirigida (no en paralelo ni suites
pesadas completas).

## Puesta en marcha

1. Fusionar el PR → CI construye las imágenes nuevas.
2. En el servidor: `docker compose pull` / `up -d`.
3. Correr el backfill una vez:
   `docker compose run --rm api python -m core.backfill_storage_key_sync`
   (renombra en MinIO todo lo que ya existe hoy — para Rama Judicial/SAMAI y
   cualquier documento republicado, esto toca la gran mayoría de los
   archivos guardados).
4. La tarea nocturna queda activa sola, sin pasos manuales adicionales.

## Fuera de alcance

- Renombrar `preview_storage_key`.
- Blindaje transaccional completo del renombrado en MinIO frente a una falla
  a mitad de camino (caso raro, aceptado).
- Disparo inmediato de la cascada completa para una edición manual de
  título (queda cubierto por el barrido nocturno).
