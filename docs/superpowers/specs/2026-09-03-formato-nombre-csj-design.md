# Formato de nombre de la CSJ — solo el código

**Fecha:** 2026-09-03
**Tipo:** cambio acotado (bounded)

## Qué cambió

### 1. Título de los documentos de la Corte Suprema

`core/scrapers/families/corte_suprema.py` — en `scrap()`, el título pasó de
`CSJ_{bucket}_{código}_{año}` al **código a secas**.

| Antes | Ahora |
|---|---|
| `CSJ_SCP_AP2260-2025(62924)_2026` | `AP2260-2025(62924)` |
| `CSJ_SCT_STL5177-2026_2024` | `STL5177-2026` |
| `CSJ_SCC_AC2794-2026 [2024-00858-00]_2024` | `AC2794-2026 [2024-00858-00]` |

El código conserva su guion interno y los paréntesis/corchetes; el saneo de
caracteres inválidos para nombre de archivo (`\ / * ? : " < > |` → `-`) sigue
igual.

**Excepción — código no reconocible.** Cuando la CSJ manda un título inservible
(`doc`, `(3)`), el relleno mantiene `_<año>` (`doc_2026`) como desempate
provisional, hasta que se lee el archivo y se recupera el código real.

### 2. La carpeta de guardado no cambia

La sigla de la sala (`SCT`/`SCL`/`SCC`/`SCP`, con la reasignación de tutelas a
la sala que las resolvió — ver `_bucket_real`) se sigue calculando y se sigue
usando como carpeta: `CSJ/SCP/AP2260-2025(62924).pdf`. Solo desaparece del
nombre del archivo.

### 3. Recuperación del código desde el archivo

Cuando la CSJ manda un título inservible (`doc`, `(3)`), el documento se guarda
con un relleno (`doc_2024`) y marcado `title_unverified`; al descargarlo,
`resolve_unverified_document` lee la primera página, saca el código real y
reescribe el título al código a secas (`ATP1800-2019`).

Antes, el año se sacaba del propio título de relleno con una expresión regular
anclada a las cuatro siglas de sala (`_TITULO_PLACEHOLDER_RE`); esa expresión se
eliminó — el título nuevo no lleva ni sala ni año.

### 4. Backfill de lo ya guardado

`core/backfill_csj_titles.py` (corrida única, idempotente):

- Recorre los documentos de la familia `corte_suprema`.
- `nuevo_titulo_csj()` pasa de `CSJ_<sala>_<código>_<año>` directo al código,
  preservando un `-v{n}` de versión si lo tenía. El `_<año>` solo se quita si lo
  que queda es un código reconocible (`_CODIGO_RE`); un título de relleno
  (`CSJ_SCC_doc_2024` → `doc_2024`) conserva su año. Un título que ya está
  migrado, o que no tiene la forma vieja, se salta.
- Actualiza el título en la base y renombra el archivo real (y sus versiones
  archivadas) con `storage_sync.reconcile_document` /
  `reconcile_document_versions`. La carpeta `CSJ/<sala>/` se conserva; solo
  cambia el nombre del archivo.

`core/backfill_csj_storage_keys.py` (anterior, otro propósito: re-sincronizar
`storage_key` con un título ya corregido) no se toca.

## Cómo aplicar en producción

1. Merge a `master` → CI construye las imágenes en GHCR.
2. En el servidor de la oficina:
   ```powershell
   docker compose pull
   docker compose up -d
   docker compose run --rm api python -m core.backfill_csj_titles
   ```
   El script imprime cuántos títulos y archivos tocó. Se puede repetir sin
   efectos secundarios.

## Pruebas

- `tests/families/test_corte_suprema.py` — títulos y recuperación de código en
  el formato nuevo; el relleno sin código conserva `_<año>`.
- `tests/test_backfill_csj_titles.py` — quita del prefijo y del año, preserva el
  sufijo de versión, conserva el año en el relleno, renombra conservando la
  carpeta, idempotencia, y que no toca otras fuentes.
