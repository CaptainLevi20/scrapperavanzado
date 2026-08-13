# Fuente Minvivienda (Ministerio de Vivienda, Ciudad y Territorio) — Plan de implementación

**Goal:** Agregar una familia de scraper nueva `minvivienda` que recolecte
las 8 categorías de `https://minvivienda.gov.co/normativa` (Resoluciones,
Decretos, Leyes, CONPES, Acuerdos, Directivas, Circulares y Autos), conectada
al registro, al seed y al pipeline existente igual que cualquier otra
familia.

**Architecture:** Un archivo nuevo `core/scrapers/families/minvivienda.py`
con una clase `ScrapMinvivienda(BaseScrapper)` registrada bajo
`@register_family("minvivienda")`. Cada categoría se recorre con `GET
https://minvivienda.gov.co/normativa?tipo={Tipo}&page={N}` (vista de Drupal
renderizada en HTML plano, sin AJAX), 20 filas por página, con corte
temprano de paginación porque el listado está ordenado descendente por la
fecha real de la norma. `tipo=Auto` mezcla varios tipos de documento bajo la
misma etiqueta del lado del sitio, así que cada fila de esa categoría se
reclasifica por la palabra inicial de su propio título en vez de confiar en
la etiqueta de categoría. Una entrada `Source` se agrega a `core/seed.py`
(`family_params={}`), sin cambios de frontend.

**Tech Stack:** Python, `requests`, `beautifulsoup4`, `pytest`, `responses`
(con `matchers.query_param_matcher`) — mismo stack que `minambiente.py`/
`mincit.py`/`madr.py`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-13-fuente-minvivienda-design.md` —
  cada regla abajo (alcance, manejo de fechas, formato de título) viene de
  ahí.
- Alcance: las 8 categorías del sitio, ninguna excluida (a pedido explícito
  del usuario) — ver spec para la reclasificación de `tipo=Auto`.
- Base URL: `https://minvivienda.gov.co`; listado:
  `https://minvivienda.gov.co/normativa`.
- Título: `{LETRA}_MVCT_{numero:04d}_{año}` (`R`/`D`/`L`/`A`/`AU`/`S`/`AV`
  para Resolución/Decreto/Ley/Acuerdo/Auto/Sentencia/Aviso, literal `CONPES`
  y `DIRECTIVA` para esas dos), `C_MVCT_{código}_{año}` para Circulares con
  radicado alfanumérico (código tal cual, sin `int()`/zero-pad).
- `f_public` (`created`, obligatorio en `RawDocModel`) y `f_providencia`
  (`field-legal-regulation-date`, opcional) se guardan ambos; `fini`/`ffin`
  filtran contra `f_providencia` — `created` verificado no confiable (puede
  quedar años atrás de la fecha real por reindexado del CMS del sitio).
  `filters_by_publication_date` se queda en el default de `BaseScrapper`
  (`False`). `doc_id_uses_publication_date` se pone en `False` explícitamente
  (mismo motivo que `minambiente`/`rama_judicial`/`samai`).

---

### Task 1: Fetch + parseo de una fila + normalización de título — done

**Files:** `core/scrapers/families/minvivienda.py`,
`tests/families/test_minvivienda.py`

`_fetch_pagina(session, tipo_param, page)` hace un `GET` a `/normativa` con
`tipo`/`page`. `_extraer_fila` parsea un `div.views-row`: título de
`.listing-title a`, `f_providencia` del atributo `datetime` de
`.views-field-field-legal-regulation-date time` (ya ISO 8601, no requiere
regex de fecha en texto libre), `f_public` de `.views-field-created`
(regex simple `\d{2}/\d{2}/\d{4}`, ignora día de semana y hora), archivo de
`.views-field-field-legal-regulation-file a[href]` (fila descartada si
falta), detalle de `.views-field-field-summary p`.

`_extraer_numero(titulo, tipo)`: `_NUMERO_CORTO_PATTERN` busca en cualquier
parte del título (no anclado al final) un número corto seguido de su año,
con espacio obligatorio a cada lado del separador (`-`/`de`); si no matchea
y el tipo es Circular, cae a `_CODIGO_CIRCULAR_PATTERN` (radicado
alfanumérico, mismo patrón que `minambiente.py`). `_normalize_title` arma el
título final; si `numero` es `None`, `title_unverified=True` con el título
crudo del sitio — el documento **no se descarta** porque `f_providencia` ya
viene del campo estructurado, no del título.

- [x] Implementado y probado con unidad (número limpio, con "No.", con
  "de", con texto colgando tras el año, radicado alfanumérico, sin número).

### Task 2: Reclasificación de `tipo=Auto` — done

**Files:** `core/scrapers/families/minvivienda.py`

`_clasificar_fila_auto(titulo)`: si el título empieza con "Circular" →
tipo Circular; con "Sentencia" → tipo Sentencia (letra `S`); con "Aviso" →
tipo Aviso (letra `AV`); cualquier otro (incluye "Auto admisorio...",
"Medida Cautelar...") → tipo Auto (letra `AU`). Solo se aplica cuando la
categoría consultada es `Auto`; el resto de categorías usan su tipo/letra
fijos.

- [x] Implementado y probado (una página con las 4 variantes mezcladas
  produce los 4 tipos correctos).

### Task 3: Paginación con corte temprano + orquestación `scrap()` — done

**Files:** `core/scrapers/families/minvivienda.py`,
`core/scrapers/families/__init__.py`

Por categoría, bucle de páginas empezando en 0; se detiene cuando la página
no trae filas, cuando todas sus filas quedaron por debajo de `fini`
(el listado está ordenado descendente, confirmado con fetch real en varias
categorías), o cuando se alcanza `limit`. Una categoría/página que falle no
descarta lo ya recolectado — se registra vía `on_progress` y se sigue con la
siguiente categoría. `minvivienda` agregado al import de
`core/scrapers/families/__init__.py`.

- [x] Implementado y probado (corte por página vieja, corte por página
  vacía, categoría que falla no descarta las demás, límite respetado).

### Task 4: Seed wiring — done

**Files:** `core/seed.py`, `tests/test_seed.py`

Agregado `"minvivienda"` a `_FAMILIES` y un
`create_source_if_missing(..., family_key="minvivienda", family_params={})`,
siguiendo el patrón de las entradas `madr`/`mincit` justo arriba. Conteos
hardcodeados en `tests/test_seed.py` actualizados (12→13 familias, y el
grupo de "fuente única" de 9→10).

- [x] Implementado.

### Task 5: Full verification

- [x] `pytest tests/families/test_minvivienda.py -v` — 25 pruebas, todas en
  verde.
- [x] `pytest` (suite completa) — 772 passed, 1 falla preexistente no
  relacionada (`test_migrations.py::test_alembic_upgrade_head_creates_all_tables`,
  `WinError 2` por PATH en esta máquina Windows — la misma falla ya conocida
  de las fuentes anteriores).
- [x] Encontrado y corregido durante la escritura de pruebas (antes de
  cualquier corrida contra el sitio real): el primer intento de
  `_NUMERO_CORTO_PATTERN` no exigía espacio alrededor del separador
  (`\d{1,4}\s*(?:-|de)\s*\d{4}`) y producía un falso positivo real —
  en `"Auto admisorio Acción Popular 50001-23-33-000-2026-00192-00"`
  matcheaba `"000-2026"` como si fuera un `numero - año` válido, cuando es
  un fragmento del radicado judicial pegado sin espacios. Se corrigió
  exigiendo `\s+` (al menos un espacio) a cada lado del separador —
  confirmado en las ~40 muestras reales revisadas que un campo real de
  "número - año" siempre trae espacios, mientras que un radicado largo con
  guiones nunca los trae. Ver spec para el detalle completo.
- [x] Sanity check manual contra el sitio real (no mockeado): corrido contra
  las 8 categorías. Encontró y corrigió un segundo bug real antes de dar la
  fuente por terminada: `tipo=Resolución` devolvía 0 resultados porque el
  código pre-codificaba el valor con `urllib.parse.quote` antes de pasarlo a
  `requests(params=...)`, que ya codifica los valores — el resultado quedaba
  doble-codificado (`"ó"` → `%C3%B3` → `%25C3%25B3`), que el sitio real no
  reconoce. Se corrigió pasando el valor sin codificar y dejando que
  `requests` lo codifique una sola vez; se agregó una prueba de regresión
  que inspecciona la URL real enviada. Confirmado después: las 8 categorías
  devuelven documentos reales con el formato de título esperado, incluyendo
  la reclasificación de Circulares mal etiquetadas dentro de `tipo=Auto`
  (ej. `C_MVCT_2018EE0091028_2018` con `tipo=Circular`, extraído de una fila
  que el sitio lista bajo `tipo=Auto`).
