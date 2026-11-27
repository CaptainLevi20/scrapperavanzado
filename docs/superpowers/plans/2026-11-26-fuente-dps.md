# Fuente Prosperidad Social (DPS) — Plan de implementación

**Goal:** Añadir la familia `dps` (Departamento Administrativo para la Prosperidad Social) con Resoluciones, Circulares y Acuerdos interinstitucionales de `prosperidadsocial.gov.co`, desde 2015.

**Architecture:** Módulo nuevo `core/scrapers/families/dps.py`, clase `ScrapDPS(BaseScrapper)` con `@register_family("dps")`. Una petición por sección a la API REST de WordPress (`/wp-json/wp/v2/pages/<id>`), que trae el acordeón entero (un panel por año, tabla `TIPO | FECHA | No. | CONTENIDO`). Cada número enlaza a un enlace compartido anónimo de SharePoint; se descarga con `download=1` (GET normal con redirecciones, sin cambios en el descargador). Familia con anexos (`_A01`…), sin actuaciones, sin `family_params`, sin migración.

**Tech Stack:** Python 3.14, `requests` + `beautifulsoup4`, `pytest` + `responses`.

**Spec:** `docs/superpowers/specs/2026-11-23-fuente-dps-design.md` (aprobado el 2026-11-26; alcance: sólo lo propio del DPS).

## Global Constraints

- **Sigla:** `DPS`. Prefijos `R` (Resolución), `C` (Circular), `A` (Acuerdo; mismo que `corantioquia` y `corporinoquia`). Resolución conjunta → `R`.
- **Número tal cual** lo escribe el DPS, sin quitar ni poner ceros (`R_DPS_00464_2016`). De `0079 Anexo` se toma la parte numérica. Número sin dígitos → texto saneado, `title_unverified=True` y aviso.
- **`_SOURCE = "Departamento Administrativo para la Prosperidad Social"`**, igual al `name` del seed.
- **Año = el del panel del acordeón**; fecha de expedición = celda FECHA con el año del panel. `f_public = f_providencia`. Piso 2015. Fecha ilegible → fila omitida con aviso.
- Quitar `​` de todo antes de leer.
- `scheduled_min_lookback_days = 60`, `doc_id_uses_publication_date = False`, `checks_for_republication` por defecto (`HEAD` con redirecciones funciona), `alerta_margen_dias = 120`.
- Sin decretos ni leyes. El cambio de dedup de decretos en `core/db/repository.py` lo hace `funcion_publica`.
- **Pruebas dirigidas:** `.venv/bin/pytest tests/families/test_dps.py tests/test_seed.py`.

## Tareas

- [x] **1. Helpers puros** — `_limpiar`, `_parse_fecha` (todas las formas de la tabla del diseño, año del panel), `_titulo`, `_url_descarga` (`?download=1` / `&download=1`). Pruebas casos 1-4.
- [x] **2. Lectura del acordeón** — `_filas(html)`: paneles `div.elementor-toggle-item`, año del título del panel, cabecera reconocida por texto (Circulares no la tiene), número del primer enlace SharePoint de la celda 3 (o el texto si no hay enlace), todos los enlaces SharePoint de la fila sin repetir; se ignoran `:f:` y enlaces ajenos. Pruebas caso 5.
- [x] **3. `scrap()`** — una sección a la vez; sección que falla → aviso y sigue; sección sin filas → aviso. Recorre todas las filas desde el piso (también fuera de la ventana) para deduplicar: por enlace a través de secciones (mismo número → en silencio; números distintos → aviso con los dos títulos) y por (sección, valor numérico, año) con aviso. Primer enlace = documento, los demás `_A01`, `_A02`… Filtro `fini <= fecha <= ffin`, `limit`, `stop_event`. Pruebas casos 6-8.
- [x] **4. Corrida real contra el sitio** (sin BD): 498 documentos desde 2015, 0 sin verificar, segunda pasada idéntica; muestra de 6 PDF bajados con `Downloader` y verificados.
- [ ] **5. Integración** (la hace quien integra): import en `core/scrapers/families/__init__.py`, `_FAMILIES` + `create_source_if_missing` en `core/seed.py`, conteos en `tests/test_seed.py`, ficha en `docs/guia-despliegue-sistemas.md`.
- [ ] **6. Corrida local con worker** desde 2015 y segunda corrida sin descargas nuevas.
