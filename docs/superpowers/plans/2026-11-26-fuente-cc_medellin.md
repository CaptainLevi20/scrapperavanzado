# Fuente Cámara de Comercio de Medellín — Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir la familia de scraper `cc_medellin` (Cámara de Comercio de
Medellín para Antioquia) que trae los laudos arbitrales de la página
"Laudos arbitrales" del Centro de Conciliación, Arbitraje y Amigable
Composición, desde 1999.

**Architecture:** Un módulo nuevo `core/scrapers/families/cc_medellin.py` con
la clase `ScrapCcMedellin(BaseScrapper)` registrada vía
`@register_family("cc_medellin")`. Sitio DNN (EasyDNNnews, acordeón) detrás de
Cloudflare: una sola petición trae los 27 paneles. Cada enlace a `/Portals/`
se empareja con el último encabezado (`<li>` o `<strong>` exterior). Las filas
se agrupan por el radicado del **nombre del PDF** en toda la página antes de
filtrar por fecha. Familia plana: sin actuaciones, sin anexos, sin
`family_params`, sin migración.

**Tech Stack:** Python 3.14, `requests` + `beautifulsoup4` (`html.parser`),
`core/fecha_es.py`, `pytest` + `responses`.

**Spec:** `docs/superpowers/specs/2026-11-23-fuente-cc_medellin-design.md`
(aprobado por el administrador el 2026-11-26).

## Global Constraints

- **Sigla:** `CCMA`. Prefijo `LA`. Tipo `Laudo arbitral`.
- **Título:** `LA_CCMA_{año_rad}-{A|AP}-{consecutivo tal cual}_{año_laudo}`;
  solo se unifican separadores y la letra en mayúscula.
- **`_SOURCE = "Cámara de Comercio de Medellín para Antioquia"`**, igual al
  `name=` del seed.
- **Sin piso de año.** Filtro `fini <= fecha <= ffin`.
- **`scheduled_min_lookback_days = 20_000`**, sin `alerta_margen_dias`,
  `checks_for_republication = True`.
- **URL:** absoluta, ruta codificada (`%20`), sin `?ver=…`.
- **TLS válido** → sin `verify=False`.
- **Pruebas dirigidas:** `.venv/bin/pytest tests/families/test_cc_medellin.py tests/test_seed.py`.

---

### Task 1: Radicado del nombre, título y URL (casos 1, 8)

**Files:** Create `core/scrapers/families/cc_medellin.py`,
`tests/families/test_cc_medellin.py`.

- [x] Prueba: `_radicado` con cada forma de nombre (`2025 A 0032 …`,
  `2017-a-0013-…`, `Rad_ 2018 A 0018- …`, `29-de-enero-de-2015-2013-A-034`,
  `2022 AP 0002`, `2022 a 0001`) y los encabezados viejos.
- [x] Prueba: `_titulo` con consecutivo tal cual.
- [x] Prueba: `_url_limpia` quita `?ver=`, codifica espacios, completa rutas
  relativas.
- [x] Implementar `_radicado`, `_clave`, `_titulo`, `_url_limpia`.

### Task 2: Fechas (caso 2)

- [x] Prueba: encabezado con `fecha_es` ("10 febrero de 2021", mayúsculas,
  "Radicado 6 de agosto de 2014- …").
- [x] Prueba: fecha del nombre (`dd-mm-aaaa`, `dd-de-mes-de-aaaa`, con `_`).
- [x] Prueba: año imposible (`2019 A 0087`, 2010 → 2020-08-12, aviso);
  encabezado ≠ nombre (`2022 A 0048`) → gana el encabezado, aviso; sin fecha
  en el encabezado → la del nombre; sin ninguna → se omite.
- [x] Implementar `_fecha_encabezado`, `_fecha_nombre`, `_fecha_fila`.

### Task 3: Lectura del acordeón (caso 3)

- [x] Prueba con fragmentos reales: maquetas `<p><strong>…</strong><br/><a>`,
  `<ul><li>…</li></ul><p><a>`, `<li><strong><a name=…>` (ancla sin href) y
  `<li>Radicado:<strong> </strong>…` (strong interior vacío).
- [x] Implementar `_filas`.

### Task 4: Reglas de enlaces (casos 4-7)

- [x] Prueba: enlace copiado (`2020 A 0007` → `2020 A 0025`,
  `2022 AP 0001` → `2022 A 0001`, la fila que coincide va después).
- [x] Prueba: mismo PDF con dos nombres (`2016 A 004` / `2016 A 012`).
- [x] Prueba: error de digitación (`2023 A 0004` vs `2023 A 0037`).
- [x] Prueba: enlaces cruzados 2014 (se quedan los dos, sin verificar).
- [x] Prueba: nombre sin radicado (`2009- 059`) → encabezado, sin verificar.
- [x] Prueba: dos PDF distintos con el mismo radicado → el primero, aviso.
- [x] Implementar `_elegir_filas` y `_fila_a_doc`.

### Task 5: `scrap()` (casos 9-10)

- [x] Prueba: detalle sin `Partes:`, filtro sin piso (entra 1999), conteo
  completo, atributos de clase.
- [x] Prueba: `stop_event`, `limit`, página que falla, página sin paneles.
- [x] Implementar `ScrapCcMedellin.scrap`.

### Task 6: Registro (lo integra quien coordina el lote)

- [ ] Import en `core/scrapers/families/__init__.py`.
- [ ] `_FAMILIES` y `create_source_if_missing` en `core/seed.py`.
- [ ] Conteos en `tests/test_seed.py`.

### Task 7: Corrida real

- [x] `scrap()` contra el sitio real (2026-11-26): 299 filas → 292 laudos,
  186 desde 2015, 9 sin verificar (4 desde 2015); avisos iguales a los del
  diseño.
- [x] 6 PDF bajados con `core/downloader.py`: todos PDF reales; el `HEAD`
  da el mismo tamaño (la revisión de republicación sirve).
- [ ] Corrida completa en la app local y segunda corrida sin descargas nuevas.

### Task 8: Ficha

- [ ] Ficha en `docs/guia-despliegue-sistemas.md` (texto listo).
