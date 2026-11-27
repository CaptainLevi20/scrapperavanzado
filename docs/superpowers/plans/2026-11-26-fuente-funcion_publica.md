# Fuente Función Pública (Gestor Normativo) — Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir la familia de scraper `funcion_publica` (Departamento Administrativo de la Función Pública) con las normas que expide la propia entidad en el Gestor Normativo, desde 2015, y extender la deduplicación de leyes/decretos a `dps` y `funcion_publica`.

**Architecture:** Un módulo nuevo `core/scrapers/families/funcion_publica.py` con `ScrapFuncionPublica(BaseScrapper)` registrada vía `@register_family("funcion_publica")`. Listado por año y tipo (`funajax.php?t=ejecuta_busqueda_avanzada2&entidad1=88&tipdoc=<id>&ano=<año>&pagina=1`, todo el año en una respuesta), detalle `norma.php?i=<id>` para las fechas, descarga `norma_pdf.php?i=<id>`. Familia plana: sin actuaciones, sin anexos, sin `family_params`, sin migración. Cambio fuera de la familia (aprobado): `core/db/repository.py` busca leyes/decretos también en `dps` y `funcion_publica`.

**Tech Stack:** Python 3.14, `requests` + `beautifulsoup4`, `core/fecha_es.py`, `core/naming.codigo_ley_decreto`, `pytest` + `responses`.

**Spec:** `docs/superpowers/specs/2026-11-23-fuente-funcion_publica-design.md` (aprobado por el administrador el 2026-11-26).

## Global Constraints

- **`_SOURCE = "Departamento Administrativo de la Función Pública"`** — igual al `name=` del seed.
- **Sigla `DAFP`.** Prefijos: `CTO` (Concepto, Concepto Marco, Conceptos Guías), `R`, `C`, `CE`, `CJ`, `CU` (Circular Unificada). Decretos (Decreto y Decretos Salariales): `codigo_ley_decreto("D", n, año)`.
- **Número tal cual** lo escribe la entidad (sin quitar ni poner ceros), salvo decretos. Número con caracteres raros → se limpia (letras, dígitos, `-`) y `title_unverified=True` + aviso; conceptos/resoluciones con letras (`C-197`) → sin verificar; sin número → `SN-<id>`.
- **Fecha:** expedición → vigencia → `<año del título>-01-01`; una fecha vale si su año es el del título y no está en el futuro. Casos 2 y 3 se avisan. `f_public = f_providencia`.
- **Piso:** 2015 (año del título). Años pedidos `max(fini.año, 2015)…ffin.año`; filas de otro año no abren detalle.
- `verify=False` sólo para `www.funcionpublica.gov.co` (sesión + `link["verify"]`), documentado.
- `checks_for_republication = False`, `doc_id_uses_publication_date = False`, `scheduled_min_lookback_days = 400`.
- Pausa de 0,3 s entre detalles (`_PAUSA_DETALLE`, 0 en pruebas).
- **Pruebas dirigidas:** `.venv/bin/pytest tests/families/test_funcion_publica.py tests/test_seed.py`; las de `tests/test_tasks.py` necesitan Postgres.

---

### Task 1: Encabezado → título

**Files:** Create `core/scrapers/families/funcion_publica.py`, `tests/families/test_funcion_publica.py`.

- [x] Pruebas: `_leer_h5` + `_titulo` para cada tipo (casos 1-2 del spec), espacios dobles/tabulador, raros (`451981*`, `¿248691`, `C-197`, sin número), decreto no numérico.
- [x] Implementar `_TIPOS`, `_H5_RE`, `_leer_h5`, `_titulo`.

### Task 2: Listado y detalle con HTML real

- [x] Pruebas: `_filas` (no cuenta el párrafo "Número de documentos encontrados"), listado vacío, `_leer_detalle` (fechas y enlace `norma_pdf.php`).
- [x] Pruebas: `_elegir_fecha` con los casos reales 753262 (vigencia), 588851 (año distinto), 610931 (futura).
- [x] Implementar `_filas`, `_leer_detalle`, `_elegir_fecha`, `_anios`.

### Task 3: `scrap()` con el sitio simulado

- [x] Pruebas: documento completo (`link`, título, tipo, fechas, `detalle`), decreto y `CU`, filtro por fecha corregida, fila de otro año sin detalle, dedup por id entre tipos, detalle sin PDF, número raro, título repetido (aviso), listado y detalle que fallan (aviso y sigue), `stop_event`, `limit`, piso, varios años, atributos de clase.
- [x] Implementar `ScrapFuncionPublica.scrap`.

### Task 4: Dedup de leyes/decretos en todos los sentidos

**Files:** Modify `core/db/repository.py`, `tests/test_tasks.py`.

- [x] `_FAMILIAS_DEDUP_LEY_DECRETO = _MINISTERIO_FAMILIES | {"dps", "funcion_publica"}`; `list_ministerio_documents_by_title` lo usa; docstring actualizado. `_MINISTERIO_FAMILIES` no cambia (lo usan los backfills).
- [x] Prueba parametrizada `test_scrape_source_task_skips_a_decreto_already_published_by_dps_or_funcion_publica` (funcion_publica→ministerio, funcion_publica→dps, dps→funcion_publica, ministerio→funcion_publica, ministerio→dps) y prueba de que los backfills no incluyen las dos familias.
- [ ] Correr `tests/test_tasks.py` con Postgres levantado.

### Task 5: Registro, seed y conteos

**Files:** `core/scrapers/families/__init__.py`, `core/seed.py`, `tests/test_seed.py`.

- [ ] Import `funcion_publica`; `_FAMILIES` + `create_source_if_missing(..., family_key="funcion_publica", name=_SOURCE, family_params={})`; conteos +1.

### Task 6: Corrida real local

- [ ] 2026 completo y un año grande (2021); abrir varios PDF; contar fechas corregidas; segunda corrida sin descargas nuevas. Fijar `alerta_margen_dias` con lo que salga.

### Task 7: Ficha en `docs/guia-despliegue-sistemas.md`

- [ ] Ficha en lenguaje sencillo, con la carga inicial por tramos de años y la revisión de disco.
