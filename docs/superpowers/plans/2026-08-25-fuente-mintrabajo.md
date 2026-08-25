# Fuente Ministerio del Trabajo (mintrabajo) — Plan de implementación

**Goal:** Agregar una familia de scraper nueva `mintrabajo` que recolecte
Decretos, Resoluciones, Circulares y Leyes desde la página estática
"Marco legal" de `mintrabajo.gov.co`, conectada al registro, al seed y al
pipeline existente igual que cualquier otra familia.

**Architecture:** Un archivo `core/scrapers/families/mintrabajo.py` con
una clase `ScrapMinTrabajo(BaseScrapper)` registrada bajo
`@register_family("mintrabajo")`. A diferencia de todas las demás
familias, no hay paginación ni navegación por año: la página completa
(varias tablas HTML con la misma estructura de columnas) se pide en un
único `GET` y se filtra por `[fini, ffin]` en memoria. Una entrada
`Source` se agrega a `core/seed.py` (`family_params={}`), sin cambios de
frontend.

**Tech Stack:** Python, `requests`, `beautifulsoup4`, `pytest`,
`responses`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-25-fuente-mintrabajo-design.md`
  — cada regla abajo viene de ahí, incluido el descubrimiento completo del
  sitio.
- Sin protección anti-robots — confirmado con `curl` plano.
- Rama: `feat/fuente-mintrabajo`, creada directo desde `master`.
- Alcance v1 (decisión explícita del usuario): Decreto + Resolución +
  Circular + Leyes. Fuera: Códigos (compilaciones completas, sin fecha de
  acto individual), Manual (referencia, no norma).
- Título: `{LETRA}_MINTRABAJO_{numero:04d}_{año}` — decisión explícita del
  usuario, consistente con las demás fuentes.
- **Un único `GET`** trae las 781 filas de una vez — sin paginación, sin
  filtro de fecha en el servidor. El filtro `[fini, ffin]` se hace
  siempre en memoria sobre las filas ya parseadas.
- Fecha con 3 formatos posibles (`DD/MM/AAAA`, prosa española con
  conector "de" opcional entre mes y año, solo-año) — sin fecha
  reconocible, la fila se descarta (~1% de filas reales tienen typos del
  sitio que no se intentan adivinar).
- El enlace de "Acceso" ya es el PDF directo — no hay página de detalle
  intermedia (a diferencia de `minenergia`).

---

### Task 1: Parseo de la página completa — done

**Files:** `core/scrapers/families/mintrabajo.py`,
`tests/families/test_mintrabajo.py`

- [x] `_parse_fecha_flexible(texto)` — cascada de 3 formatos descrita
  arriba.
- [x] `_parsear_fila(tr)` → dict con tipo, número, fecha ISO, epígrafe,
  url de acceso (o `None` si la fila no tiene la forma esperada, tipo
  fuera de alcance, o fecha no reconocible).
- [x] 15 pruebas: los 3 formatos de fecha (incluidos los typos reales del
  sitio que deben devolver `None`), fila para los 4 tipos en alcance,
  descarte por tipo fuera de alcance (Códigos/Manual), descarte por fecha
  no reconocible, resolución de enlaces relativos/absolutos/externos.

### Task 2: `scrap()` — un único GET, filtro en memoria — done

**Files:** `core/scrapers/families/mintrabajo.py`

- [x] `scrap()` pide la página una sola vez, parsea todas las filas,
  filtra por `[fini, ffin]`, construye `RawDocModel` con nomenclatura
  normalizada.
- [x] Si el `GET` falla, se registra vía `on_progress` y se devuelve lista
  vacía.
- [x] 5 pruebas: filtro de fecha exacto, `stop_event`, `limit`, error de
  red devuelve lista vacía sin lanzar excepción.

### Task 3: Seed wiring — done

**Files:** `core/seed.py`, `core/scrapers/families/__init__.py`,
`tests/test_seed.py`

- [x] Agregado `mintrabajo` a `_FAMILIES` y
  `create_source_if_missing(db, family_key="mintrabajo",
  name="Ministerio del Trabajo", family_params={})`.
- [x] Agregado el import en `core/scrapers/families/__init__.py`.
- [x] `tests/test_seed.py` actualizado (17 familias, 82 fuentes en vez de
  81, grupo de "fuente única" de 13 a 14).

### Task 4: Full verification

- [x] `pytest tests/families/test_mintrabajo.py -v` — 23 pruebas, todas
  en verde.
- [x] `pytest tests/test_seed.py` — 3 pruebas, todas en verde.
- [x] `pytest` (suite completa) — 917 passed, 1 failed (la falla
  preexistente ya documentada de `test_migrations.py`, no relacionada).
- [x] Sanity check manual contra el sitio real (no mockeado): rango
  2026-06-01 a 2026-08-24 devolvió 51 documentos reales (Decretos y
  Resoluciones) con número, fecha y enlace de PDF correctos. El PDF de la
  Resolución 2635 ("trabajo en casa") descargó genuino (`application/pdf`,
  3.8 MB) con `User-Agent: Mozilla/5.0`, sin sesión ni referer especial.
  Nota: se observó un caso real de datos inconsistentes del propio sitio
  (Decreto 660 y Decreto 551 apuntando al mismo archivo
  `decreto-0551-comprimido`) — se procesó tal cual, sin intentar
  corregirlo, mismo criterio que el manual mal clasificado visto en
  MinJusticia.
