# Fuente MinEducación (Ministerio de Educación Nacional) — Plan de implementación

**Goal:** Agregar una familia de scraper nueva `mineducacion` que recolecte
Resolución, Decreto, Circular, Directiva, Acuerdo, Ley y Concepto desde el
Normograma del Ministerio de Educación (`normograma.info/men`), conectada
al registro, al seed y al pipeline existente igual que cualquier otra
familia.

**Architecture:** Un archivo `core/scrapers/families/mineducacion.py` con
una clase `ScrapMineducacion(BaseScrapper)` registrada bajo
`@register_family("mineducacion")`. Cada categoría tiene su propia página
del Normograma (`GET
https://normograma.info/men/compilacion/compilacion/{base}.html`), que
trae el año más reciente embebido más un selector con todo el historial;
los años que faltan se piden por separado
(`GET {base}_{año}.html`) solo cuando el rango solicitado los necesita y
todavía no vinieron en la página base. El PDF real se deriva del propio
`href` de cada fila (`docs/X.htm` → `docs/pdf/X.pdf`), sin visitar la
página del documento. Una entrada `Source` se agrega a `core/seed.py`
(`family_params={}`), sin cambios de frontend.

**Tech Stack:** Python, `requests`, `beautifulsoup4`, `pytest`,
`responses`.

## Historia: dos versiones en el mismo día

Este plan cubre la **segunda y definitiva** versión de la fuente. La
primera versión (implementada y probada primero, con 48 pruebas) usaba
`/portal/Normatividad/Ultimas-publicaciones` — un listado nativo del sitio
del ministerio, fuera del Normograma — pero solo cubría desde 2016 y casi
no tenía Leyes. El usuario notó la falta de Leyes y Conceptos; al
investigar se confirmó que **ninguna** categoría tiene archivo completo
fuera del Normograma (no solo Leyes/Conceptos), y el usuario decidió
explícitamente scrapear el Normograma — el producto de su propia empresa,
Avance Jurídico — en vez de conformarse con el listado parcial. Ver la spec
para el detalle completo de esta decisión y sus alternativas descartadas.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-13-fuente-mineducacion-design.md`
  — cada regla abajo viene de ahí, incluida la historia completa del
  pivote.
- Alcance: 7 categorías, cada una acotada a la entidad que realmente la
  expide dentro del sector educación (Ministerio, o Presidencia/Congreso
  para Decreto/Ley) — a pedido explícito del usuario, **no** se expande a
  las decenas de otras entidades del sector que también compila el
  Normograma (SENA, ICETEX, universidades, JEP...).
- Base URL: `https://normograma.info/men/compilacion/compilacion/`.
- Título: `{LETRA}_MEN_{numero:04d}_{año}` (`R`/`D`/`C`/`A`/`L` para
  Resolución/Decreto/Circular/Acuerdo/Ley, literal `DIRECTIVA` y `CONCEPTO`
  para esos dos).
- `f_public` solo tiene precisión de año (`{año}-01-01`) — el listado del
  Normograma no da día ni mes. Decisión explícita del usuario tras pedir
  recomendación: aceptar esa precisión en vez de visitar cada documento
  (miles de documentos históricos, mucho más lento). Mismo criterio ya
  usado en `madr.py` para casos sin fecha completa.
  `doc_id_uses_publication_date` en el default `True` (a diferencia de
  `minvivienda`/`minambiente`): esta fecha es intrínseca al documento, no
  un timestamp de reindexado. `filters_by_publication_date` en el default
  `False`, mismo criterio que `madr.py`.
- El PDF real se deriva por transformación de texto del `href` del
  listado (`docs/X.htm` → `docs/pdf/X.pdf`), confirmado inspeccionando el
  JS del visor del sitio (`docFunction.js`).

---

### Task 1: Extracción de fila + derivación del PDF real — done

**Files:** `core/scrapers/families/mineducacion.py`,
`tests/families/test_mineducacion.py`

`_extraer_fila` parsea un `div.opcion-nueva`: `id-documento` con el
identificador (`"{Tipo} {numero} de {año}[ ME]"`, un único regex, sin
cascada — formato uniforme verificado contra 1269 filas reales de 2026 a
1905), `descripcion-documento` para el detalle, y el `href` del enlace
transformado a la ruta del PDF real vía `_pdf_href_from_doc_href`.

- [x] Implementado y probado (fila con/sin sufijo " ME", formato no
  reconocido con aviso, sin enlace, sin descripción, derivación del PDF
  con/sin carpeta).

### Task 2: Paginación por año, adaptativa según lo que ya viene embebido — done

**Files:** `core/scrapers/families/mineducacion.py`

`_scrap_categoria` pide la página base, extrae TODAS las filas que ya trae
(agrupadas por el año que cada fila reporta en su propio identificador), y
solo pide como fragmento aparte (`{base}_{año}.html`) los años que el rango
solicitado necesita y que todavía no aparecieron en esa primera pasada.
Esto evita un 404 real en categorías chicas (donde el sitio no genera
fragmentos separados, todo viene embebido) y evita peticiones de más en
categorías grandes.

- [x] Implementado y probado (regresión directa del 404 real: no vuelve a
  pedir un año que la página base ya trajo embebido; filtra fuera de
  rango; continúa cuando un año-fragmento o la página base fallan).

### Task 3: Orquestación `scrap()` por categoría — done

**Files:** `core/scrapers/families/mineducacion.py`,
`core/scrapers/families/__init__.py`

Un `_scrap_categoria` por cada una de las 7 categorías; una que falle no
descarta lo ya recolectado de las demás. `mineducacion` ya estaba en el
import de `core/scrapers/families/__init__.py` desde la primera versión
(sin cambios en este archivo).

- [x] Implementado y probado (agrega las 7 categorías, continúa si una
  falla, límite respetado, `stop_event` respetado entre categorías).

### Task 4: Seed wiring — done (sin cambios de la primera versión)

**Files:** `core/seed.py`

La entrada `"mineducacion"` ya existía desde la primera versión de esta
fuente; solo se actualizó la descripción para reflejar el Normograma.
`family_key`/nombre sin cambios.

- [x] Implementado.

### Task 5: Full verification

- [x] `pytest tests/families/test_mineducacion.py -v` — 23 pruebas, todas
  en verde (reescrito por completo, reemplaza las 48 pruebas de la primera
  versión).
- [x] `pytest` (suite completa) — 770 passed, 1 falla preexistente no
  relacionada (`test_migrations.py::test_alembic_upgrade_head_creates_all_tables`,
  `WinError 2` por PATH en esta máquina Windows).
- [x] Sanity check manual contra el sitio real (no mockeado): 2026 completo
  (112 documentos en 6 categorías con datos ese año, Acuerdo en 0 porque su
  año más reciente es 2023), y un rango histórico 1990-1995 (107
  documentos en Resolución/Decreto/Ley, las únicas 3 categorías con
  cobertura tan antigua) para confirmar que la lógica de fragmentos por año
  también funciona lejos en el pasado. Cero avisos de fila descartada en
  ambas corridas. Verificados 3 PDF reales descargados (`Circular`,
  `Directiva`, `Concepto`) como `application/pdf` genuino, no HTML.
