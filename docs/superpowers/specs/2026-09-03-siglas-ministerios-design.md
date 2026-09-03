# Cambio de siglas de ministerios en el título

**Fecha:** 2026-09-03
**Tipo:** cambio acotado (bounded)

## Qué cambió

El título de los documentos de ministerios tiene la forma
`<letra>_<SIGLA>_<número>_<año>` (p. ej. `D_MADR_0765_2026`). Se cambia el
token de la sigla en 7 de las 10 familias:

| Familia | Antes | Ahora |
|---|---|---|
| `madr` (Agricultura y Desarrollo Rural) | `MADR` | `MA` |
| `mindeporte` (Deporte) | `MDEPORTE` | `MDEP` |
| `mineducacion` (Educación Nacional) | `MEN` | `ME` |
| `minenergia` (Minas y Energía) | `MINENERGIA` | `MME` |
| `mininterior` (Interior) | `MININT` | `MI` |
| `minjusticia` (Justicia y del Derecho) | `MINJUSTICIA` | `MJ` |
| `mintrabajo` (Trabajo) | `MINTRABAJO` | `MTRA` |

Sin cambio: `minambiente` (`MADS`), `mincit` (`MCIT`), `minvivienda` (`MVCT`).

Ejemplos: `D_MADR_0765_2026` → `D_MA_0765_2026`;
`C_MINJUSTICIA_CIR26-0000002_2026` → `C_MJ_CIR26-0000002_2026`.

La carpeta de guardado (`Fuente/Fecha/Tipo/`) no cambia. El `doc_id` de estas
fuentes se deriva de la URL de descarga, no del título, así que el cambio no
rompe identidad ni deduplicación.

## Cambios

### 1. Scrapers (7 archivos)

Cada `_normalize_title` (o equivalente) en `core/scrapers/families/` tiene una
línea `return f"{letra}_<SIGLA>_{int(numero):04d}_{anio}"` — se cambia el
literal de la sigla. `minjusticia` tiene además la línea especial de Circulares
(`C_<SIGLA>_{numero}_{anio}`, sin relleno), que también se cambia.

### 2. Reorganizador de lotes — `core/reorganize.py`

`_ENTITY_ALIASES` gana una entrada por cada sigla vieja → nueva (ya tenía
`MEN → ME`), para que un archivo viejo cuyo nombre trae la sigla anterior, ya
ubicado en la carpeta de la sigla nueva, no se marque como `entity_mismatch`.

### 3. Backfill — `core/backfill_ministerios_siglas.py` (nuevo)

Corrida única e idempotente. `_SIGLAS` mapea `family_key → (sigla vieja, sigla
nueva)` para las 7 familias que cambian. Por cada familia:

- `nuevo_titulo(titulo, vieja, nueva)` reemplaza el token de la sigla vía
  `^([A-Za-z]+)_<vieja>_(.+)$`. Un título ya migrado, o de otra forma, se salta.
- Guarda de colisión (mismo patrón que `core/storage_sync.py::_grupos_en_colision`
  y `core/backfill_csj_titles.py`): si dos documentos calcularan la misma clave
  destino se omiten ambos con un `logger.warning`. En la práctica no ocurre —
  el cambio es un swap 1:1 del token y las rutas llevan carpeta de fecha/tipo —
  pero la guarda es barata y consistente.
- Actualiza el título en la base y renombra el archivo real (y sus versiones
  archivadas) con `storage_sync.reconcile_document` / `reconcile_document_versions`.

## Cómo aplicar en producción

1. Merge a `master` → CI construye las imágenes en GHCR.
2. En el servidor de la oficina:
   ```powershell
   docker compose pull
   docker compose up -d
   docker compose run --rm api python -m core.backfill_ministerios_siglas
   ```
   El script imprime, por familia, cuántos títulos y archivos tocó y cuántos
   omitió por colisión. Se puede repetir sin efectos secundarios.

## Pruebas

- `tests/families/test_{madr,mindeporte,mineducacion,minenergia,mininterior,minjusticia,mintrabajo}.py`
  — títulos con la sigla nueva.
- `tests/test_backfill_ministerios_siglas.py` — transformación por familia,
  sufijo de versión conservado, renombrado conservando la carpeta, idempotencia,
  guarda de colisión, y que no toca familias sin cambio ni otras fuentes.
- `tests/test_core_reorganize.py` — las siglas viejas resuelven a la nueva vía
  `_ENTITY_ALIASES`.

## Anexo: prefijo de Directivas DIRECTIVA -> DIR

Además del cambio de siglas, el prefijo de las Directivas pasa de `DIRECTIVA`
a `DIR` en los scrapers que lo usaban (`mineducacion`, `mininterior`,
`minvivienda`; `mindeporte` ya usaba `DIR`). Ej.
`DIRECTIVA_ME_0005_2026` -> `DIR_ME_0005_2026`.

Backfill: `core/backfill_directiva_prefix.py` (corrida única, idempotente).
Recorre las fuentes de ministerio, cambia el prefijo `DIRECTIVA_` -> `DIR_` en
el título y renombra el archivo, con guarda de colisión. No toca otros tipos
ni otras familias.
