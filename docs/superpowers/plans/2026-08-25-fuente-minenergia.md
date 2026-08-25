# Fuente Ministerio de Minas y Energía (minenergia) — Plan de implementación

**Goal:** Agregar una familia de scraper nueva `minenergia` que recolecte
Decretos, Resoluciones y Circulares desde el micrositio Nexura de
`normativame.minenergia.gov.co`, conectada al registro, al seed y al
pipeline existente igual que cualquier otra familia.

**Architecture:** Un archivo `core/scrapers/families/minenergia.py` con
una clase `ScrapMinEnergia(BaseScrapper)` registrada bajo
`@register_family("minenergia")`. El listado (tabla HTML servida por el
servidor, sin JS) se pide por año (`vigencia={año}`) paginado
(`genPag=N`) hasta una página sin filas; cada fila trae número/tipo/fecha/
resumen ya limpios en columnas separadas. El PDF no está en el listado:
requiere un segundo `GET` a la página de detalle de cada norma para leer
el `<iframe src=...>`. Una entrada `Source` se agrega a `core/seed.py`
(`family_params={}`), sin cambios de frontend.

**Tech Stack:** Python, `requests`, `beautifulsoup4`, `pytest`,
`responses`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-25-fuente-minenergia-design.md`
  — cada regla abajo viene de ahí, incluido el descubrimiento completo del
  sitio.
- Sin protección anti-robots — confirmado con `curl` plano.
- Rama: `feat/fuente-minenergia`, creada directo desde `master`.
- Alcance v1 (decisión explícita del usuario): Decreto + Resolución +
  Circular — los 3 únicos tipos vistos, todos igual de limpios (número y
  fecha en columnas separadas, no hay heterogeneidad de formato entre
  tipos).
- Título: `{LETRA}_MINENERGIA_{numero:04d}_{año}` — decisión explícita del
  usuario, consistente con las demás fuentes. El número ya viene aislado
  en su propia columna, sin necesidad de regex sobre texto libre.
- **2 requests por documento**: uno para la fila del listado, uno para la
  página de detalle (único lugar con el PDF real). No hay atajo.
- Fecha (`DD/MM/AAAA`) se parsea directo, sin cascada de niveles — formato
  fijo y sin ambigüedad.
- El filtro `vigencia` del sitio solo acota por año; el filtro exacto por
  `fini`/`ffin` se hace en el propio scraper sobre la fecha de cada fila.
- Corte de paginación: una página cuya tabla no trae ninguna fila (no el
  número de enlaces de paginación visibles, que solo muestra una ventana
  deslizante), **o** cuya fila más vieja ya es anterior a `fini` (orden
  descendente confirmado dentro de cada año) — crítico aquí porque cada
  fila en rango implica un segundo request de detalle.

---

### Task 1: Parseo de una fila del listado y de la página de detalle — done

**Files:** `core/scrapers/families/minenergia.py`,
`tests/families/test_minenergia.py`

- [x] `_parsear_fila`/`_filas_de_pagina` → filas con número, tipo, fecha
  ISO, resumen, url de detalle.
- [x] `_extraer_pdf_de_detalle(html)` → URL absoluta del PDF desde el
  primer `<iframe src=...>`, o `None` si no hay ninguno.
- [x] Pruebas: parseo de fila para los 3 tipos, fecha `DD/MM/AAAA` → ISO,
  extracción del iframe real ignorando el que está en un comentario HTML,
  detalle sin iframe, tabla vacía/ausente.

### Task 2: `scrap()` — por año, paginación, fetch de detalle, filtro exacto — done

**Files:** `core/scrapers/families/minenergia.py`

- [x] Por cada año en `[fini.year, ffin.year]`, pagina `genPag=1,2,...`
  hasta una página sin filas **o** cuya fila más vieja ya sea anterior a
  `fini` (orden descendente confirmado — evita pedir el resto del año
  cuando el rango pedido es angosto).
- [x] Filtra cada fila contra `[fini, ffin]` exacto antes de pedir su
  detalle (evita requests de detalle innecesarios para filas fuera de
  rango).
- [x] Pide la página de detalle de cada fila en rango, construye
  `RawDocModel` con el número ya limpio y la nomenclatura normalizada.
- [x] Continúa con lo demás si un año, una página o un detalle falla
  (`on_progress`).
- [x] 8 pruebas: corte de paginación por página vacía, corte por fecha
  (nuevo, crítico dado el costo de 2 requests/documento), filtro exacto de
  fecha antes de pedir detalle, omisión de fila sin iframe en su detalle,
  continúa si algo falla, `stop_event`.

### Task 3: Seed wiring — done

**Files:** `core/seed.py`, `core/scrapers/families/__init__.py`,
`tests/test_seed.py`

- [x] Agregado `minenergia` a `_FAMILIES` y
  `create_source_if_missing(db, family_key="minenergia",
  name="Ministerio de Minas y Energía", family_params={})`.
- [x] Agregado el import en `core/scrapers/families/__init__.py`.
- [x] `tests/test_seed.py` actualizado (17 familias, 82 fuentes en vez de
  81, grupo de "fuente única" de 13 a 14).

### Task 4: Full verification

- [x] `pytest tests/families/test_minenergia.py -v` — 17 pruebas, todas
  en verde.
- [x] `pytest tests/test_seed.py` — 3 pruebas, todas en verde.
- [x] `pytest` (suite completa) — 911 passed, 1 failed (la falla
  preexistente ya documentada de `test_migrations.py`, no relacionada).
- [x] Sanity check manual contra el sitio real (no mockeado): un primer
  intento sin el corte de paginación por fecha (Task 2) tardó más de 90s
  para un rango de solo 2 meses dentro de 2026 — confirmó en la práctica
  el riesgo anotado en la spec (cada fila en rango pide su propio detalle,
  y sin corte se recorre el año completo). Tras agregar el corte, el mismo
  rango (2026-08-01 a 2026-08-24) devolvió 14 documentos reales
  (Resoluciones, Decretos, Circulares) en segundos, con número, fecha y
  enlace de PDF correctos. El PDF del Decreto 1187 descargó genuino
  (`application/pdf`, 238 KB) con `User-Agent: Mozilla/5.0`, sin sesión ni
  referer especial.
