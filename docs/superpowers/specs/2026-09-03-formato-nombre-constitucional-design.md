# Formato de nombre de la Corte Constitucional — con guiones

**Fecha:** 2026-09-03
**Tipo:** cambio acotado (bounded)

## Qué cambió

### 1. Título de los documentos de la Corte Constitucional

`core/scrapers/families/constitucional.py::_normalize_title` ahora separa el
prefijo de letras, el número de la providencia y el año con guiones, en vez de
pegarlos con un guion bajo intermedio.

| `prov_sentencia` (crudo) | Antes | Ahora |
|---|---|---|
| `T-065/24` | `ST065_24` | `ST-065-24` |
| `C-034/26` | `SC034_26` | `SC-034-26` |
| `SU.066/26` | `SU066_26` | `SU-066-26` |
| `A. 846/26` | `A846_26` | `A-846-26` |

Reglas que **no** cambiaron: la `S` se antepone a las sentencias (T/C) y no se
duplica en las de unificación (`SU…`); los autos no llevan `S`; el tipo se
sigue deduciendo del prefijo del número, no del campo `prov_tipo`.

El título alimenta tanto el nombre del archivo descargado como la ruta de
guardado, así que ambos quedan con el formato nuevo automáticamente.

### 2. Sufijo de versión — global

`core/naming.py::construir_nombre` arma el sufijo de republicación. Pasó de
`_v{n}` a `-v{n}`. Es una función **compartida por todas las fuentes**, así que
el cambio aplica a cualquier documento republicado (ej. Consejo de Estado:
`…_20260731_v1` → `…_20260731-v1`). En el próximo barrido de conciliación
(`core/storage_sync.py::reconcile_all`, tarea nocturna) los archivos ya
guardados de documentos republicados se renombran solos al nuevo sufijo.

Decisión tomada explícitamente con el usuario: se prefirió el cambio global
antes que una regla especial solo para la Corte Constitucional.

### 3. Backfill de lo ya guardado

`core/backfill_constitucional_titles.py` (corrida única, idempotente):

- Recorre los documentos cuya fuente es "Corte Constitucional".
- `nuevo_titulo_constitucional()` convierte el título viejo (`ST065_24`,
  `ST065_24_v2`) al nuevo (`ST-065-24`, `ST-065-24-v2`). Un título que ya está
  en formato nuevo, o que no tiene la forma esperada, se salta.
- Actualiza el título en la base y renombra el archivo real (y sus versiones
  archivadas) reusando `storage_sync.reconcile_document` /
  `reconcile_document_versions`.

El `doc_id` de la Corte Constitucional se deriva del número crudo
(`prov_sentencia`) + fecha de publicación, **no** del título, así que cambiar
el formato del título no rompe la identidad ni la deduplicación de los
documentos existentes.

## Cómo aplicar en producción

1. Merge a `master` → CI construye las imágenes en GHCR.
2. En el servidor de la oficina:
   ```powershell
   docker compose pull
   docker compose up -d
   docker compose run --rm api python -m core.backfill_constitucional_titles
   ```
   El script imprime cuántos títulos se actualizaron y cuántos archivos se
   renombraron. Se puede volver a correr sin efectos secundarios.

## Pruebas

- `tests/families/test_constitucional.py` — formato nuevo en los 5 casos.
- `tests/test_naming.py`, `tests/test_storage_sync.py`,
  `tests/test_storage_sync_tasks.py`, `tests/test_tasks.py`,
  `tests/test_api_documents.py` — sufijo `-v{n}`.
- `tests/test_backfill_constitucional_titles.py` — conversión de títulos,
  renombrado, idempotencia, y que no toca otras fuentes.
