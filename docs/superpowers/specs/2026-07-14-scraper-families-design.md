# Portar las 8 familias de scraping restantes — Diseño

Fecha: 2026-07-14

## Contexto y objetivo

El backend IURISYNC (`scrapper-avanzado`) porta hoy solo 2 de las ~10 familias técnicas del proyecto original de escritorio (`C:\Users\asant\WebScrapping_Fuentes`): `constitucional` y `samai`. El README documenta explícitamente que el resto queda como trabajo de seguimiento. Este diseño cubre portar las 8 familias restantes, siguiendo el mismo patrón ya establecido: `BaseScrapper` + `@register_family(...)` + `RawDocModel` + seeding en `core/seed.py`.

Las 8 familias, y las fuentes (`Source` rows) que generan:

| `family_key` | Entidad(es) | Fuentes generadas | Complejidad |
|---|---|---|---|
| `corte_suprema` | Corte Suprema de Justicia | 1 | Media — GraphQL vía POST, 4 tipos de providencia |
| `jep` | Jurisdicción Especial para la Paz | 1 | Media — API JSON; solo año de granularidad en fechas |
| `cndj` | Consejo Nacional de Disciplina Judicial | 1 | Media — HTML + regex de fechas en español |
| `adr` | Agencia de Desarrollo Rural | 1 | Media — API REST de WordPress |
| `adres` | ADRES | 1 | Media — HTML, dominio restringido |
| `ane` | Agencia Nacional del Espectro | 1 | Media-alta — SharePoint REST recursivo |
| `anh` | Agencia Nacional de Hidrocarburos | 1 | Baja — HTML + regex de fechas |
| `rama_judicial` | Tribunales Superiores + Juzgados | 38 (32 + 6) | Alta — fan-out paramétrico + `ThreadPoolExecutor` |

**Total: 44 fuentes nuevas** (7 de fuente única + 38 de Rama Judicial), sumadas a las 29 (SAMAI) + 1 (Corte Constitucional) ya existentes.

Explícitamente fuera de alcance: cambios a `core/downloader.py` (las 8 familias solo usan métodos `GET`/`POST`, ya soportados), cambios al frontend (las fuentes nuevas aparecen automáticamente en `SourcesPage`/`RunsPage`/filtros de `DocumentsPage`, que ya consumen `/sources` y `/source-families` genéricamente), rate-limiting o reintentos nuevos más allá de los que cada scraper original ya trae.

## Arquitectura

Sin cambios arquitectónicos: se reutiliza el pipeline existente end-to-end.

```
resolve_scraper(family_key, family_params)   # core/scrapers/registry.py, sin cambios
  → scraper.scrap(fini, ffin)                 # nuevo código, uno por familia
  → List[RawDocModel]                          # core/models.py, sin cambios
  → Downloader.download(doc, tmp_dir)          # core/downloader.py, sin cambios
  → upload_file(...)                           # core/storage.py, sin cambios
  → repository.insert_document(...)            # core/db/repository.py, sin cambios
```

Cada familia nueva es un módulo en `core/scrapers/families/<family_key>.py`, importado desde `core/scrapers/families/__init__.py` (igual que `constitucional`/`samai` hoy) para que el decorador `@register_family` se ejecute al arrancar el proceso.

## Port de cada familia

Por cada uno de los 8 módulos, portar la clase desde `WebScrapping_Fuentes/scrappers/<archivo>.py` preservando:

- La lógica de scraping tal cual (incluyendo comentarios de dominio no obvios ya presentes en el original — ej. las reglas de tipo-por-prefijo de JEP, la nota sobre año-solamente en fechas de JEP, la deduplicación por `hipervinculo`).
- La firma `scrap(self, fini, ffin, q="", limit=..., stop_event=None, on_progress=None) -> List[RawDocModel]` sin cambios (coincide con `BaseScrapper`).

Ajustando mecánicamente:

- Imports: `from core.models import RawDocModel`, `from core.scrapers.base import BaseScrapper`, `from core.scrapers.registry import register_family`.
- Constantes de URL que en el original vienen de `config.config` (ej. `CORTE_SUPREMA_URL`, `JEP_URL`, `CNDJ_BASE_URL`) se inlinean como constantes de módulo — no se crea un `core/config` compartido para esto, siguiendo el patrón ya usado por `constitucional.py`.
- Construcción de `save_path`: se estandariza usando el helper `storage_path(*parts)` de `core/utils.py` (ya usado por `constitucional`/`samai`) en vez de los f-strings crudos del original. Es un cambio puramente cosmético/consistencia — no altera la estructura de la ruta resultante.
- Se agrega `@register_family("<family_key>")` sobre la clase.

### Rama Judicial (fan-out)

Sigue el mismo patrón que SAMAI: una sola clase `ScrapRamaJudicial(dept_code, dept_name, entidad_id)` parametrizada, con dos diccionarios de datos públicos exportados del módulo (`SUPERIORES_DEPTS`, `JUZGADOS_ENTIDADES` — 32 y 6 entradas respectivamente) que `core/seed.py` enumera para crear una `Source` por cada combinación, igual que `SAMAI_CORPS` hoy.

## Cambios en `core/seed.py`

- `_FAMILIES` gana 8 entradas nuevas (`family_key` → `(display_name, description)`).
- Por cada una de las 7 familias de fuente única: un `create_source(family_key=..., name=..., family_params={})`, igual que Corte Constitucional.
- Para `rama_judicial`: se importan `SUPERIORES_DEPTS`/`JUZGADOS_ENTIDADES` desde `core.scrapers.families.rama_judicial` y se itera creando las 38 `Source` con `family_params={"dept_code": ..., "dept_name": ..., "entidad_id": ...}` (o `{"dept_code": "", "dept_name": ..., "entidad_id": ...}` para los juzgados, que no llevan departamento) — todas `active=True` desde el arranque, igual que SAMAI.

## Testing y validación

Por cada una de las 8 familias:

1. **Test unitario** en `tests/families/test_<family_key>.py`, HTTP mockeado vía `responses` (mismo patrón que `test_constitucional.py`/`test_samai.py`): caso feliz + al menos un caso borde específico de esa fuente (ej. JEP: filtro por año y deduplicación por `hipervinculo`; Corte Suprema: corte por fecha y por `limit`; Rama Judicial: ambos fan-outs — un `dept_code` y una `entidad_id` de juzgado).
2. **Validación en vivo**: antes de dar la tarea por terminada, una llamada real a `.scrap()` contra el sitio real de la entidad con un rango de fechas corto, para confirmar que el sitio no cambió su estructura desde que se escribió el scraper original en `WebScrapping_Fuentes`. Se documenta el resultado (cuántos documentos reales encontró, o el error si el sitio cambió) en el reporte de la tarea — no queda como test automatizado permanente, para no atar la suite de CI a la disponibilidad de sitios externos del gobierno colombiano.

## Manejo de errores

Sin cambios: se preserva el patrón ya existente en `worker/tasks.py`. Una excepción no capturada en `.scrap()` marca el `run_source` como `failed` con `error_message`; un error al descargar/procesar un documento individual queda registrado vía `repository.add_run_error(...)` sin abortar el resto de la corrida.

## Fuera de alcance

- `core/downloader.py` — no se toca.
- Frontend — no se toca; las fuentes nuevas aparecen automáticamente.
- Rate-limiting/reintentos nuevos — se preserva el comportamiento original de cada scraper.
- Multi-tenancy, agendamiento especial por familia, o UI para gestionar el fan-out de Rama Judicial más allá de lo que ya ofrece `SourcesPage` — no aplica, sigue el mismo patrón que SAMAI.
