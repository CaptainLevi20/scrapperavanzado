# Leyes y Decretos de ministerios: código sin sigla + deduplicación entre fuentes

**Fecha:** 2026-09-03
**Tipo:** arquitectural (nombrado en ~10 scrapers + deduplicación entre fuentes + backfill que renombra y deduplica)

## Problema

Hoy cada ministerio nombra sus Leyes y Decretos con su propia sigla
(`L_MA_2277_2022`, `D_ME_0715_2001`). Una misma ley/decreto la publican varios
ministerios (una ley toca varios sectores), así que quedan filas distintas para
la misma norma. Se quiere: un código único sin sigla de ministerio, y que la
misma norma no se duplique entre fuentes.

## Formato nuevo

`<L|D>` + `<número, 4 dígitos con ceros a la izquierda>` + `<año>`, **sin
separadores**. El año:

| Rango | Dígitos | Ejemplo |
|---|---|---|
| 2000 en adelante | 3 (`año % 1000`) | 2022 → `022`, 2001 → `001`, 2000 → `000` |
| 1900–1999 | 2 (`año % 100`) | 1901 → `01`, 1995 → `95` |
| 1800–1899 | 3 (`año % 1000`) | 1888 → `888` |

Ejemplos: `L2277022`, `L0715001`, `D0111096`, `L010093`.

**Solo aplica a `letra == "L"` y `letra == "D"`.** Resoluciones (`R`),
Circulares (`C`), Conpes, Directivas, Autos (`A`), Acuerdos, y los prefijos
propios de mininterior (`LEST` Ley Estatutaria, `ACTOLEG` Acto Legislativo,
`ACTOADM`, `CONCEPTO`, `DIRECTIVA`) **no cambian** — siguen con
`{letra}_{SIGLA}_{numero:04d}_{anio}`.

**Parseo:** sin ambigüedad porque el número siempre son 4 dígitos (tras `L`/`D`
los 4 primeros son el número, el resto el año). Si un número supera 9999 (raro
en leyes/decretos) no se rellena y el parseo limpio se pierde — se acepta.

**Se pierde el siglo:** `L010093` es Ley 100 de 1993, pero también sería la de
1893 con el mismo string bajo la regla de 1800-1899 (888 vs 93 lo desambigua en
ese caso puntual; el choque real sería 1993 vs 2093). Norma anterior a ~1950
es rarísima en normatividad de ministerios; se acepta.

## Deduplicación entre ministerios

**Familias de ministerio** (conjunto nuevo `_MINISTERIO_FAMILIES` en
`core/db/repository.py`): `madr, minambiente, mincit, mindeporte, mineducacion,
mininterior, minenergia, minjusticia, mintrabajo, minvivienda`.

### Al scrapear (forward)

En `worker/tasks.py::scrape_source_task`, en el paso de metadata (antes de
descargar), en la rama `existing is None`: si `doc.title` es un código de
ley/decreto (empieza por `L`/`D` seguido de dígitos — se valida con un helper
`es_codigo_ley_decreto`) **y** ya existe un documento con ese título exacto en
cualquier fuente de ministerio (`repository.list_ministerio_documents_by_title`),
se omite: no se agrega a `pending`, no se descarga, no se inserta.

**Gana el que ya está.** El "archivo más grande" (abajo) aplica solo al
backfill. Edge case aceptado: si tras el backfill un ministerio publica una
versión más grande de una ley existente, se omite (no reemplaza); el chequeo de
republicación de la propia fuente lo cubre si re-lista en su URL.

### En el backfill (documentos ya guardados)

`core/backfill_leyes_decretos.py` (corrida única, `python -m ...`):

1. **Renombrar.** Por cada fuente de ministerio, transformar el título de sus
   Leyes/Decretos del formato con sigla (`^([LD])_[A-Z]+_(\d+)_(\d{4})$` —
   cualquier sigla, así que da igual si el backfill de siglas
   `backfill_ministerios_siglas` ya corrió o no) al nuevo.
   Actualiza el título en la base y renombra el archivo (y versiones) con
   `storage_sync.reconcile_document` / `reconcile_document_versions`. Guarda de
   colisión intra-fuente como en `backfill_csj_titles` /
   `backfill_ministerios_siglas`.
2. **Deduplicar entre fuentes.** Agrupar los documentos de ley/decreto de todas
   las fuentes de ministerio por título canónico. Para cada grupo con más de
   uno: conservar el de `file_size_bytes` mayor (desempate: `id` menor; los
   `NULL` pierden frente a cualquier tamaño conocido) y **borrar los demás** —
   fila + objeto de almacenamiento (y sus versiones). Reusar el helper de
   borrado de `repository` si existe uno para un documento suelto; si no, borrar
   fila y devolver las claves de almacenamiento a limpiar.

## Implementación

### `core/naming.py`

```python
def codigo_ley_decreto(letra: str, numero: str, anio: str) -> str | None:
    if letra not in ("L", "D"):
        return None
    y = int(anio)
    anio_str = f"{y % 100:02d}" if 1900 <= y <= 1999 else f"{y % 1000:03d}"
    return f"{letra}{int(numero):04d}{anio_str}"


_CODIGO_LEY_DECRETO_RE = re.compile(r"^[LD]\d{4,}\d{2,3}$")  # sanity para el forward

def es_codigo_ley_decreto(titulo: str) -> bool:
    return bool(_CODIGO_LEY_DECRETO_RE.match(titulo or ""))
```

### Scrapers (los 10)

`madr, minambiente, mincit, mindeporte, mineducacion, mininterior, minenergia,
minjusticia, mintrabajo, minvivienda` — cada `_normalize_title(letra, numero,
anio)` pasa a:

```python
return codigo_ley_decreto(letra, numero, anio) or f"{letra}_<SIGLA>_{int(numero):04d}_{anio}"
```

`minenergia` y `minjusticia` no scrapean Leyes pero **sí Decretos**, así que
también cambian (solo para `D`). `minjusticia` conserva su rama `if letra ==
"C"` antes de esa línea; `minvivienda` conserva su rama de número no numérico.

### `core/db/repository.py`

- `_MINISTERIO_FAMILIES` (frozenset).
- `list_ministerio_documents_by_title(db, title) -> list[Document]`.

### `worker/tasks.py`

En la rama `existing is None` del bucle de metadata (~línea 380): antes de
`pending.append`, si `es_codigo_ley_decreto(doc.title)` y
`list_ministerio_documents_by_title(db, doc.title)` no está vacío → `continue`
(omitir). No incrementa `docs_new` ni `docs_errors`.

## Pruebas

- `tests/test_naming.py`: `codigo_ley_decreto` — los 3 rangos de año, relleno
  del número a 4, `None` para `R`/`C`/`A`/`LEST`; `es_codigo_ley_decreto`.
- `tests/families/test_{madr,minambiente,mincit,mindeporte,mineducacion,
  mininterior,mintrabajo,minvivienda}.py`: títulos de L/D en el formato nuevo;
  R/C/otros sin cambio.
- `tests/test_tasks.py`: al scrapear una ley cuyo código ya existe en otra
  fuente de ministerio → se omite (no se descarga ni inserta); una resolución
  con el mismo número NO se omite.
- `tests/test_backfill_leyes_decretos.py`: renombrado L/D, R/C intactos,
  dedup por `file_size_bytes` (mayor gana, `NULL` pierde, desempate por id),
  guarda de colisión intra-fuente, no toca otras familias.

## Cómo aplicar en producción

1. Merge → CI.
2. `alembic upgrade head` (sin migración nueva para esto).
3. `docker compose run --rm api python -m core.backfill_leyes_decretos` —
   imprime, por fuente, títulos renombrados y, al final, duplicados borrados.
   Idempotente.
