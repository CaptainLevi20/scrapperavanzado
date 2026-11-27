# Fuente Contraloría General de la República — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir la familia `contraloria` (Contraloría General de la República) con
Resoluciones, Conceptos jurídicos y Circulares desde 2015, leídas de la API JSON
del "Sistema de Búsqueda de Normas de la CGR".

**Architecture:** Un módulo nuevo `core/scrapers/families/contraloria.py` con
`ScrapContraloria(BaseScrapper)` registrada vía `@register_family("contraloria")`.
Cada sección es **un** `POST` que trae la biblioteca de SharePoint completa
(sin paginación); se lee también Jurisprudencia sólo para saber qué `Id` se
repiten entre bibliotecas. La descarga es `POST getDownloadFileApiBuffer`
(`{"Id", "List"}`) que hace el worker; la identidad va en `body["path"]` (número
normalizado) y la extensión en el fragmento de la URL. Para las filas de la
ventana con `Id` repetido se consulta `getFileInfo` antes de emitir. Familia
plana: sin anexos, sin actuaciones, sin `family_params`, sin migración, sin
cambios de núcleo.

**Tech Stack:** Python 3.14, `requests`, `pydantic` (`RawDocModel`), `pytest` +
`responses`.

**Spec:** `docs/superpowers/specs/2026-11-23-fuente-contraloria-design.md`

## Global Constraints

- **`_SOURCE = "Contraloría General de la República"`**, igual al `name=` del seed.
- **Sigla `CGR`.** Títulos: `R_CGR_{serie}-{número}_{año}` (`R_CGR_OGZ-0897_2026`),
  `CTO_CGR_{número}_{año}` (`CTO_CGR_130_2026`; 2015: radicado,
  `CTO_CGR_2015EE0012345_2015`), `C_CGR_{número}_{año}`, `CJ_CGR_{número}_{año}`.
  El número va **tal cual** lo escribe la CGR en el nombre del archivo.
- **Año del título = año del número**; si no coincide con la fecha, aviso.
- **Piso 2015** por fecha de expedición en las tres secciones; además `fini <= fecha <= ffin`.
- **Fecha = `[:10]` del ISO**, sin convertir zona. `f_public = f_providencia`.
- **Identidad:** `body["path"] = "cgr/<sección>/<clave>"` con el número sin ceros
  a la izquierda; `doc_id_uses_publication_date = False`.
- `checks_for_republication = False`, `scheduled_min_lookback_days = 120`.
- TLS válido: **sin** `verify=False`.
- **Pruebas dirigidas:** `.venv/bin/pytest tests/families/test_contraloria.py`.

---

### Task 1: Fecha y número → título (casos 1-4 del diseño)

**Files:** Create `core/scrapers/families/contraloria.py`, `tests/families/test_contraloria.py`

- [x] Pruebas de `_fecha` (T05/T07/T08 → misma fecha; vacía → None).
- [x] Pruebas de `_identificar` para resoluciones (series, `(2)`, `FD`, `.` final,
      respaldo con el campo "Número", sin número → `title_unverified`).
- [x] Pruebas para conceptos (guion largo, `de 2024`, `PI` delante/detrás,
      `0CGR`, `CGR-0J`, `.docx.pdf`, radicados `EE`/`IE`/`1E`).
- [x] Pruebas para circulares (`C`, `CJ` con tipo `Circular conjunta`, sin número).
- [x] Implementar `_num_resolucion`, `_num_concepto`, `_num_circular`, `_identificar`.

### Task 2: `link` e identidad (caso 5)

- [x] `_link`: URL `…/getDownloadFileApiBuffer#<clave>.<ext>`, `POST`, `body` con
      `Id`, `List`, `path`; `extract_filename` saca `.pdf`/`.docx` del fragmento.
- [x] Misma fila recreada con otro `Id` y otra fecha → mismo `doc_id`; tres
      documentos del mismo día → tres `doc_id`.

### Task 3: `Id` repetidos y dedup (casos 6-7)

- [x] `getFileInfo` coincide → se emite; otro archivo → se omite con aviso;
      "something went wrong" dos veces → se omite con aviso; un reintento que
      sale bien → se emite.
- [x] `Id` único o fuera de la ventana → no se llama a `getFileInfo`.
- [x] Si falta algún listado → se verifican todas las filas de la ventana.
- [x] Dedup por (sección, clave normalizada), se queda la primera con aviso;
      resolución y circular con el mismo número no se confunden.

### Task 4: `scrap()` completo (casos 8-9)

- [x] Filtro por fecha y piso, filas sin fecha (aviso salvo las anteriores al
      piso), circular sin archivo (`FileLeafRef = "2026"`), detalle y `save_path`.
- [x] `stop_event`, `limit`, sección que falla (aviso y sigue), cuerpo del listado.

### Task 5: Integración (la hace quien integra las ramas)

- [ ] `contraloria` en el `import` de `core/scrapers/families/__init__.py`.
- [ ] `core/seed.py`: familia en `_FAMILIES` y `create_source_if_missing`.
- [ ] `tests/test_seed.py`: conteos y clave esperada.
- [ ] Ficha en `docs/guia-despliegue-sistemas.md` y fila en la tabla de
      "Fuentes que publican con retraso" (120 días).

### Task 6: Corrida real

- [x] `scrap()` en vivo de 2025 (sin BD): 22 resoluciones, 219 conceptos,
      1 circular y 1 circular conjunta en 7 s; 1 resolución omitida porque la
      API entregaba otro archivo (`OGZ-0876-2025` → `CGR-OJ-173-2021`).
- [x] `scrap()` en vivo de 2020: 77 resoluciones, 213 conceptos, 15
      circulares en 75 s (59 `getFileInfo`, todas coincidieron ese día).
- [x] Descarga de muestra con `Downloader` (resoluciones y circulares de `Id`
      repetido, conceptos, un `.docx`): tipo real correcto y contenido igual al
      listado.
- [ ] Corrida completa en el entorno local (worker + BD) por 2025 y segunda
      corrida sin descargas nuevas.
- [ ] **Producción:** no lanzar la carga histórica (~10 GB) hasta ampliar el
      disco; después, una corrida por año (2026 → 2015) revisando el espacio.
