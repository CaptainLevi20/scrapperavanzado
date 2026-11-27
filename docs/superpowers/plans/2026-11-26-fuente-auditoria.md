# Fuente Auditoría General de la República — Plan de implementación

**Goal:** Añadir la familia `auditoria` (Auditoría General de la República)
con conceptos jurídicos, resoluciones orgánicas y reglamentarias y circulares
desde 2025.

**Architecture:** `core/scrapers/families/auditoria.py`, clase
`ScrapAuditoria(BaseScrapper)` con `@register_family("auditoria")`. Liferay
DXP: se lee el HTML del portlet `DLPortlet` carpeta por carpeta
(`…/document_library/<instancia>/view/<folderId>` con `deltaEntry=500`,
`curEntry` mientras "Mostrando el intervalo a - b de N" diga que hay más),
en profundidad, sin abrir carpetas con año menor al piso. Familia con
anexos (`_A01`), sin actuaciones, sin `family_params`, sin migración.

**Spec:** `docs/superpowers/specs/2026-11-23-fuente-auditoria-design.md`
(aprobado el 2026-11-26).

## Global Constraints

- `_SOURCE = "Auditoría General de la República"` (igual al `name` del seed).
- Sigla `AGR`. Títulos: `CTO_AGR_{n}_{año}`, `R_AGR_ORG-{n}_{año}`,
  `R_AGR_REG-{n}_{año}`, `CE_`/`CJ_`/`CD_AGR_{n}_{año}`. Número **tal cual**
  (sin rellenar ni quitar ceros); para comparar repetidos se usa su valor.
- Piso `_ANIO_MINIMO = 2025` por año del documento (el de la carpeta).
- `verify=False` sólo para este host (sesión y `link["verify"]`).
- `f_public` = fecha de carga (`?t=` en hora de Bogotá);
  `f_providencia` = `<año>-01-01`; `filters_by_publication_date = True`;
  `doc_id_uses_publication_date = False`; enlace sin `?t=` ni `download=true`.
- Pruebas: `.venv/bin/pytest tests/families/test_auditoria.py -q`, sin
  internet (`responses` con filas copiadas del portlet real).

## Tareas

- [x] **1. Lector de carpeta.** `_parse_carpeta`: filas
  `li[data-qa-id="row"]` (carpetas por `data-folder-id`, archivos por el
  enlace `download=true`), dedup por `uuid`, carpeta 119334 ignorada,
  intervalo de paginación; `_enlace_limpio`; `_fecha_carga`. Pruebas
  `test_parse_carpeta_*`, `test_enlace_limpio_*`, `test_fecha_de_carga_*`.
- [x] **2. Número → título.** `_numero` (conceptos tras el código `110`/`1100`,
  primera coincidencia en resoluciones y circulares, clase de circular del
  nombre), `_titulo`, `_valor_numero`, `_detalle`. Pruebas
  `test_numero_tal_cual` (un caso por formato), `test_titulo_y_valor`,
  `test_detalle_es_el_asunto`.
- [x] **3. Reglas de sección.** Año de la carpeta (aviso si el nombre dice
  otro), concepto de la raíz sin año → omitido con aviso, dedup raíz/carpeta,
  anexo por palabra, `39-02-2025_010-IGIP.pdf` → `_A01` con aviso, número
  repetido → `_A01` con aviso, número ilegible → `title_unverified`.
  Prueba `test_scrap_completo`.
- [x] **4. `scrap()`.** Filtro por fecha de carga, sección o subcarpeta que
  falla (aviso y sigue), sección vacía, paginación con `curEntry`, tope de
  páginas, `limit`, `stop_event`, `verify=False`. Pruebas `test_scrap_*`.
- [ ] **5. Integración** (la hace quien integra): import en
  `families/__init__.py`, `_FAMILIES` y `create_source_if_missing` en
  `core/seed.py`, conteos en `tests/test_seed.py`.
- [x] **6. Consulta real** (sin BD) del 2026-11-26 desde 2025-01-01: 198
  documentos, 0 sin verificar; 6 PDF descargados con el `Downloader` y
  verificados. Falta la corrida completa en la aplicación y la segunda
  corrida sin descargas nuevas.
- [ ] **7. Ficha** en `docs/guia-despliegue-sistemas.md`.
