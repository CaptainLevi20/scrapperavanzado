# Fuente Cámara de Comercio de Barranquilla — Plan de implementación

**Goal:** Añadir la familia `cc_barranquilla` (laudos arbitrales del Centro de
Conciliación y Arbitraje de la Cámara de Comercio de Barranquilla), leídos de
la carpeta de OneDrive compartida en la tarjeta "Laudos Arbitrales" de
`https://www.camarabaq.org.co/centro-de-conciliacion-y-arbitraje/`.

**Architecture:** `core/scrapers/families/cc_barranquilla.py`, clase
`ScrapCcBarranquilla` con `@register_family("cc_barranquilla")`. Abre el
enlace compartido `:f:` (cookie anónima `FedAuth` en la sesión), lista la raíz
y las carpetas de año con la API REST de SharePoint
(`GetFolderByServerRelativePath(decodedurl=…)?$expand=Folders,Files`) y arma
un documento por PDF. La descarga usa el método nuevo `sharepoint_compartido`
de `core/downloader.py` (aprobado por el administrador el 2026-11-26).

**Spec:** `docs/superpowers/specs/2026-11-23-fuente-cc_barranquilla-design.md`

## Global Constraints

- `_SOURCE = "Cámara de Comercio de Barranquilla"` (igual al `name` del seed).
- Sigla `CCBAR`, prefijo `LA`, tipo `Laudo arbitral`. Sin piso de año.
- Título `LA_CCBAR_{AAAAMMDD}_{año}`; misma fecha → `_2`, `_3` por orden de
  subida (`TimeCreated`, `UniqueId`); sin fecha → `LA_CCBAR_SF{n}_{año
  carpeta}` con fecha `<año>-01-01` y `title_unverified`; día ilegible → día 1
  y `title_unverified`. Los sufijos se calculan sobre toda la carpeta.
- Nombres en NFC antes de leerlos.
- `scheduled_min_lookback_days = 20_000`, `checks_for_republication = False`,
  sin `alerta_margen_dias`.
- TLS válido: sin `verify=False`.
- Pruebas: `.venv/bin/pytest tests/families/test_cc_barranquilla.py tests/test_downloader.py tests/test_seed.py`.

## Tareas

- [x] **1. Descargador** — `tests/test_downloader.py`: el método
  `sharepoint_compartido` abre `link["compartido"]` y baja `link["url"]` con
  la misma sesión (cookie simulada); sin cookie, la página de inicio de sesión
  (HTML) deja el documento fallido. Implementar
  `Downloader._resolve_sharepoint_compartido`.
- [x] **2. Fecha y partes del nombre** — formatos `AAAA-MM-DD` (espacios, día
  de una cifra), `AAAA-DD-MM`, `DD-MM-AAAA`, regla de las 8 cifras
  (`AAAAMMDD` / `DDMMAAAA`), ilegible, sin fecha; NFD = NFC; `detalle` sin
  fecha ni "LAUDO ARBITRAL" (incluida la errata "LUDO").
- [x] **3. Títulos** — misma fecha por orden de subida, `SF{n}` por carpeta,
  ilegible sin verificar.
- [x] **4. Enlace de la página** — `href` `:f:` de la tarjeta; sin tarjeta →
  enlace conocido + aviso.
- [x] **5. `scrap()`** — recorrido raíz → años (ignora `Forms`), `link` con
  `method`/`url`/`compartido`, filtro de fechas sin piso, carpeta que falla
  (aviso y sigue), enlace caído (error de la corrida), `limit`,
  `stop_event`, listado vacío, atributos de la clase.
- [ ] **6. Integración** — import en `families/__init__.py`, `_FAMILIES` y
  `create_source_if_missing` en `core/seed.py`, conteos de
  `tests/test_seed.py`.
- [ ] **7. Corrida real local** completa y segunda corrida sin descargas
  nuevas. (Hecha la revisión del listado en vivo y 3 descargas con el método
  nuevo: 71 laudos, 3 sin verificar.)
- [ ] **8. Ficha** en `docs/guia-despliegue-sistemas.md`.
