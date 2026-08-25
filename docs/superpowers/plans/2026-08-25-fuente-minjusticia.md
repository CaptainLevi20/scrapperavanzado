# Fuente Ministerio de Justicia y del Derecho (minjusticia) — Plan de implementación

**Goal:** Agregar una familia de scraper nueva `minjusticia` que recolecte
Decretos, Resoluciones y Circulares directamente desde la API REST pública
de SharePoint de `minjusticia.gov.co`, conectada al registro, al seed y al
pipeline existente igual que cualquier otra familia.

**Architecture:** Un archivo `core/scrapers/families/minjusticia.py` con
una clase `ScrapMinJusticia(BaseScrapper)` registrada bajo
`@register_family("minjusticia")`. A diferencia de todas las demás
familias, no hay parseo de HTML: se consulta directo
`GET {base}/_api/web/lists/getbytitle('{lista}')/items` con `$filter`
nativo sobre `MJFechaExpedicion` (fecha real ya estructurada por el
sitio, sin parseo de texto en español) para las 3 listas relevantes
(Decretos, Resoluciones, Circulares). Una entrada `Source` se agrega a
`core/seed.py` (`family_params={}`), sin cambios de frontend.

**Tech Stack:** Python, `requests`, `pytest`, `responses`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-25-fuente-minjusticia-design.md`
  — cada regla abajo viene de ahí, incluido el descubrimiento completo del
  sitio.
- Sin protección anti-robots — la API REST de SharePoint responde
  anónima, confirmado con `curl` plano.
- Rama: `feat/fuente-minjusticia`, creada directo desde `master`.
- Alcance v1 (decisión explícita del usuario): Decretos + Resoluciones +
  Circulares. Fuera: Notificaciones, Intervenciones (Consejo de
  Estado/Corte Constitucional), y el resto de bibliotecas administrativas
  del sitio (no son normatividad).
- Título: `{LETRA}_MINJUSTICIA_{numero:04d}_{año}` para Decretos/
  Resoluciones, `C_MINJUSTICIA_{codigo}_{año}` para Circulares (código
  interno tal cual, sin relleno) — decisión explícita del usuario,
  consistente con las demás fuentes. `año` siempre el de
  `MJFechaExpedicion`, nunca el del código interno de la Circular (pueden
  no coincidir, caso real confirmado).
- Ningún item se descarta por falta de fecha: `MJFechaExpedicion` está
  siempre presente en las 3 listas. Solo la falta de número/código
  reconocible dispara el fallback a título crudo + `title_unverified`.
- `MJDescripcion` es casi siempre el placeholder `"."` (o `None`) — se
  trata como detalle ausente en ambos casos.

---

### Task 1: Consulta y parseo de una lista — done

**Files:** `core/scrapers/families/minjusticia.py`,
`tests/families/test_minjusticia.py`

`_extraer_items(session, lista, tipo, letra, fini, ffin, on_progress)` →
`List[RawDocModel]`: arma la URL con `$filter`/`$select`/`$expand`/`$top`
vía `params` de `requests`, parsea `d.results` (formato JSON verbose),
extrae número (genérico `\d+` o el patrón dedicado de Circulares
`CIR\d{2}-\d+`), arma `f_providencia`/`f_public` desde
`MJFechaExpedicion[:10]`, resuelve la URL del PDF desde
`File.ServerRelativeUrl`, y construye el título normalizado o el
fallback crudo.

- [x] `_extraer_items` + helpers (`_normalize_title`, extracción de
  número por lista).
- [x] 13 pruebas: parseo de un item de Decretos/Resoluciones (incluye
  `detalle=None` cuando `MJDescripcion` es `"."`), Circular con código
  reconocible, Circular sin código (fallback), año tomado de
  `MJFechaExpedicion` y no del código, item sin `File` se omite,
  respuesta con error, paginación vía `__next`.

### Task 2: `scrap()` — 3 listas, filtro de fecha, continúa si una falla — done

**Files:** `core/scrapers/families/minjusticia.py`

- [x] `scrap()` recorre las 3 listas, arma el `$filter` de fecha para
  cada una, agrega resultados, respeta `stop_event`/`limit`.
- [x] Si el `GET` de una lista falla, se registra vía `on_progress` y se
  continúa con las demás (no aborta todo el run).
- [x] Sigue `d.__next` si apareciera (robustez, no se espera en la
  práctica dado el tamaño de las listas).
- [x] 2 pruebas: continúa si una lista falla, `stop_event`.

### Task 3: Seed wiring — done

**Files:** `core/seed.py`, `core/scrapers/families/__init__.py`,
`tests/test_seed.py`

- [x] Agregado `minjusticia` a `_FAMILIES` y
  `create_source_if_missing(db, family_key="minjusticia",
  name="Ministerio de Justicia y del Derecho", family_params={})`.
- [x] Agregado el import en `core/scrapers/families/__init__.py`.
- [x] `tests/test_seed.py` actualizado (17 familias, 82 fuentes en vez de
  81, grupo de "fuente única" de 13 a 14).

### Task 4: Full verification

- [x] `pytest tests/families/test_minjusticia.py -v` — 15 pruebas, todas
  en verde.
- [x] `pytest tests/test_seed.py` — 3 pruebas, todas en verde.
- [x] `pytest` (suite completa) — 909 passed, 1 failed (la falla
  preexistente ya documentada de `test_migrations.py`, no relacionada).
- [x] Sanity check manual contra el sitio real (no mockeado): rango
  2026-06-01 a 2026-08-24 devolvió 9 documentos reales (8 Resoluciones, 1
  Circular; sin Decretos en ese rango) con número, fecha y enlace de PDF
  correctos. El PDF de la Resolución 1510 descargó genuino
  (`application/pdf`, 1.1 MB) con el mismo `User-Agent: Mozilla/5.0` que
  ya usa `core/downloader.py`, sin sesión ni referer especial. El caso
  real "manual mal clasificado como Resolución 002" (ver spec) se procesó
  tal cual, sin intentar corregirlo.
