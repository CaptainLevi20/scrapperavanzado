# Fuente Ministerio del Interior (mininterior) — Plan de implementación

**Goal:** Agregar una familia de scraper nueva `mininterior` que recolecte
Decreto, Resolución, Circular, Ley, Ley Estatutaria, Directiva, Acuerdo,
Concepto, Acto Administrativo y Acto Legislativo desde el archivo de
normatividad de `mininterior.gov.co`, conectada al registro, al seed y al
pipeline existente igual que cualquier otra familia.

**Architecture:** Un archivo `core/scrapers/families/mininterior.py` con una
clase `ScrapMininterior(BaseScrapper)` registrada bajo
`@register_family("mininterior")`. El archivo del sitio
(`GET /normatividad/`, `GET /normatividad/page/{n}/`) es un único listado
cronológico con TODOS los tipos mezclados, ordenado del más nuevo al más
viejo por "fecha de entrada en vigencia" — se pagina secuencialmente y se
detiene en cuanto un item en alcance trae una fecha anterior a `fini`. Cada
item fuera del alcance de tipos se descarta sin detener la paginación. Una
entrada `Source` se agrega a `core/seed.py` (`family_params={}`), sin
cambios de frontend.

**Tech Stack:** Python, `requests`, `beautifulsoup4`, `pytest`, `responses`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-13-fuente-mininterior-design.md` —
  cada regla abajo viene de ahí, incluido el descubrimiento completo del
  sitio.
- Sin protección anti-robots — a diferencia de Minhacienda (que quedó
  pausada, ver memoria de proyecto `iurisync-minhacienda-blocked`), este
  sitio no tuvo ningún bloqueo.
- Rama: `feat/fuente-mininterior`, creada directo desde `master` (no desde
  `feat/fuente-mineducacion`, que seguía sin mergear) para que el PR quede
  independiente — decisión explícita del usuario.
- Alcance: solo tipos de norma formales (Decreto, Resolución, Circular
  Externa/Interna, Ley, Ley Estatutaria, Directiva, Acuerdo, Concepto, Acto
  Administrativo, Acto Legislativo) — decisión explícita del usuario, deja
  fuera decenas de tipos administrativos internos (Informe, Manual,
  Memorandos, Meci, Notificación, Tutela...) que el sitio mezcla en el mismo
  listado.
- Título: `{LETRA}_MININT_{numero:04d}_{año}` — decisión explícita del
  usuario de normalizar en vez de conservar el título tal cual lo redacta el
  sitio, para mantener consistencia con `madr`/`mincit`/`mineducacion`.
- `f_public` tiene precisión de día completo (a diferencia de
  Mineducación): se parsea de "Fecha de entrada en vigencia", formato único
  `"{mes en minúsculas} {día}, {año}"`.
- El listado tiene items empatados en la misma fecha entre páginas
  consecutivas (WordPress no usa un desempate estable cuando
  `orderby=meta_value` tiene valores repetidos) — produce duplicados
  ocasionales entre páginas contiguas, inofensivos porque el `doc_id` aguas
  abajo se calcula por URL, no por posición en el listado.

---

### Task 1: Extracción de un item del listado — done

**Files:** `core/scrapers/families/mininterior.py`,
`tests/families/test_mininterior.py`

`_extraer_item` parsea un `div.dmach-grid-item`: badge de tipo (el único
`p.dmach-acf-value` sin `span.dmach-acf-label` interna), título
(`h4.dmach-post-title`), descripción y fecha (los `p.dmach-acf-value` CON
etiqueta, separada del valor quitando el `span` de la etiqueta del árbol
antes de leer el texto restante), y el enlace de descarga
(`a.et_pb_button`). Descarta el item si el tipo no está en
`_TIPOS_EN_ALCANCE`, si falta la fecha o no se puede interpretar, o si falta
el enlace.

- [x] Implementado y probado (parseo del markup real, tipo fuera de
  alcance, sin número reconocible → `title_unverified`, sin fecha, sin
  enlace, sin descripción).

### Task 2: Paginación con corte por fecha — done

**Files:** `core/scrapers/families/mininterior.py`

`scrap()` pide `/normatividad/` y luego `/normatividad/page/{n}/`
secuencialmente. Por cada item en alcance con fecha `< fini`, deja de pedir
páginas (el orden descendente del sitio garantiza que todo lo que sigue
también es más viejo). Una página sin ningún `div.dmach-grid-item` también
detiene la paginación (fin real del archivo).

- [x] Implementado y probado (corte por fecha, corte por página vacía,
  `limit`, `stop_event`, continúa con lo ya recolectado si una página
  falla).

### Task 3: Seed wiring — done

**Files:** `core/seed.py`, `core/scrapers/families/__init__.py`

- [x] Implementado.

### Task 4: Full verification

- [x] `pytest tests/families/test_mininterior.py -v` — 24 pruebas, todas en
  verde.
- [x] `pytest tests/test_seed.py` actualizado (14 familias, 79 fuentes en
  vez de 78) tras agregar `mininterior`.
- [x] `pytest` (suite completa) — todo en verde salvo una falla preexistente
  no relacionada (`test_migrations.py::test_alembic_upgrade_head_creates_all_tables`,
  `WinError 2` por PATH en esta máquina Windows — misma falla ya documentada
  en el plan de Mineducación).
- [x] Sanity check manual contra el sitio real (no mockeado): rango
  2026-08-01 a 2026-08-13 devolvió Decretos y Resoluciones reales con fecha,
  número y enlace de PDF correctos; confirmado que los PDFs descargan
  genuinos (`application/pdf`, 17.9 MB en el primero probado) sin sesión ni
  referer especial. Un bug real de parseo de fecha (la etiqueta "Fecha de
  entrada en vigencia:" no se separaba bien del valor) se encontró y corrigió
  durante este sanity check — sin el fix, `_parse_fecha` fallaba siempre y
  la paginación nunca encontraba el límite inferior.
