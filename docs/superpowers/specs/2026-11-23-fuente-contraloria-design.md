# Fuente Contraloría General de la República (CGR) — diseño

**Fecha:** 2026-11-23
**Entidad:** Contraloría General de la República (`contraloria`, sigla propuesta `CGR`)
**Estado:** pendiente de aprobación del administrador. No se programa nada
hasta que se apruebe.

> El enlace que dio el usuario
> (`https://www.contraloria.gov.co/web/relatoria/normatividad-y-relatoria`)
> es una página de Liferay que sólo contiene un `<iframe>` hacia el
> **"Sistema de Búsqueda de Normas de la CGR"**
> (`https://cgr-sistemanormatividad.contraloria.gov.co/`), una aplicación
> React. Esa aplicación consume una **API JSON pública**
> (`https://cgr-sistemarelatoria-api.contraloria.gov.co/api/relatoria2`) que
> es un intermediario sobre cuatro bibliotecas de SharePoint Online
> (`congenrep.sharepoint.com/sites/relatoria2`). Esa API es la fuente real.
>
> Las demás páginas del menú no traen actos de la CGR: "Normativa aplicable"
> son enlaces a leyes externas (Senado, Función Pública), "Producción
> normativa" es texto sobre proyectos, "Boletín jurídico" es otro `<iframe>`
> (`relatoria.z20.web.core.windows.net/boletines/`) y "SUIN" redirige al
> SUIN-Juriscol.

## Objetivo

Familia de scraper nueva `contraloria`, desde **2015** (fecha de expedición).
Propuesta (a confirmar, pregunta 1):

| Sección | Endpoint (POST) | Biblioteca (`List`) | tipo | título | Filas desde 2015 |
|---|---|---|---|---|---|
| Resoluciones | `/getResoluciones` | `Resoluciones` | `Resolución` | `R_CGR_{serie}-{número}_{año}` | 516 |
| Conceptos jurídicos | `/getConceptosJuridicos` | `Conceptos Juridicos` | `Concepto` | `CTO_CGR_{número}_{año}` | 2.512 |
| Circulares (opcional, ver casos raros) | `/getCirculares` | `Circulares` | `Circular` | `C_CGR_{número}_{año}` / `CJ_CGR_…` | 60 (sólo 3 descargables) |

Familia **plana**: sin anexos (un archivo por fila), sin actuaciones, sin
`family_params`.

Jurisprudencia (la cuarta biblioteca) queda fuera: son sentencias y autos
del Consejo de Estado y la Corte Constitucional sobre la CGR, no actos de
la CGR, y casi todos sus archivos no se pueden descargar (ver casos raros).

## Construcción del sitio

- `www.contraloria.gov.co`: Liferay detrás de Azure Application Gateway
  (cookies `ApplicationGatewayAffinity*`, `JSESSIONID`). TLS válido. Sin WAF,
  sin captcha, sin desafío de JavaScript.
- `cgr-sistemanormatividad.contraloria.gov.co`: SPA (Vite + React + MUI). El
  `baseURL` de la API está en el bundle (`/assets/index-*.js`).
- `cgr-sistemarelatoria-api.contraloria.gov.co`: API Node (las rutas
  inexistentes responden al estilo Fastify: `Route GET:/… not found`). TLS
  válido, CORS `*`, sin autenticación ni cookies. No hace falta pasar por el
  sitio principal.

### Listados

`POST {API}/getResoluciones` (y `getCirculares`, `getConceptosJuridicos`,
`getJurisprudencia`) con el cuerpo JSON que manda el formulario vacío:

```json
{"ResolucionClasificacion":null,"ResolucionVigencia":null,"CircularDestinatario":null,
 "CircularAnio":null,"ConceptoJuridicoAnio":null,"ConceptoJuridicoTipoConcepto":null,
 "JurisprudenciaAnio":null,"JurisprudenciaCorporacion":null,"JurisprudenciaTipoProvidencia":null,
 "JurisprudenciaSalaSeccion":null,
 "OrdenarPor":{"Label":"FechaDecision","id":1,"Title":"Fecha de decisión más reciente primero","Default":false},
 "keyword":"","FechaInicio":null,"FechaFin":null,"PalabrasClave":null,"advQuery":[]}
```

Responde **la biblioteca completa en una sola respuesta** (la paginación de
10 en 10 la hace el navegador): Resoluciones 1.699 filas / 1,9 MB / 2,2 s;
Conceptos 2.652 / 2,5 MB / 1,2 s; Circulares 68 / 78 KB; Jurisprudencia
341 / 560 KB. Sin paginación: **una petición por sección**.

Cada fila es el ítem de SharePoint tal cual (OData):

```json
{"Id":1928,"FileLeafRef":"OGZ-0897-2026.pdf",
 "Title":"Por la cual se adopta la versión 7.0 del Manual Específico de Funciones …",
 "Clasificacion":"Resolución Organizacional","Numero_x0020_de_x0020_resolucion":"OGZ-0897-2026",
 "Fecha_x0020_de_x0020_expedicion":"2026-11-04T08:00:00Z","Vigencia":"Rige a partir de su publicación",
 "Tema2":"Adoptar la versión 7.0 del Manual …"}
{"Id":5979,"FileLeafRef":"CGR-OJ-130-2026.pdf","Title":"Viabilidad juridica de modificar …",
 "Fecha":"2026-11-23T08:00:00Z","Numero_x0020_de_x0020_concepto":"CGR-OJ-130-2026","Ano":"2026",
 "TipoConcepto":"Posición institucional","Tema":"Asignación por evaluación de desempeño - …"}
```

| Dato | Resoluciones | Conceptos | Circulares |
|---|---|---|---|
| fecha | `Fecha_x0020_de_x0020_expedicion` | `Fecha` | `Fecha` |
| número y año | `FileLeafRef` (respaldo: `Numero_x0020_de_…`) | `FileLeafRef` (respaldo: `Numero_x0020_de_concepto`) | `FileLeafRef` |
| extensión | `FileLeafRef` | `FileLeafRef` | `FileLeafRef` |
| `detalle` | `Title` (epígrafe) | `Tema` (`Title` está vacío en 2.505 de 2.512) | `Asunto2` |
| identidad | `Id` | `Id` | `Id` |

El número se lee del **nombre del archivo** y no del campo "Número": el
campo viene truncado en varias filas (`CGR-OJ-0089-20`, `CGR-OJ-182-202`,
`OGZ-0660`), mientras el archivo trae el número completo.

### Descarga

- `POST {API}/getDownloadFileApiBuffer` con `{"Id": <Id>, "List": "<biblioteca>"}`
  → `200`, `Content-Type: application/octet-stream`, `Content-Length`, sin
  `Content-Disposition`. `GET` y `HEAD` dan `404`. Un `Id` inexistente
  responde `200` `text/plain` `Ohhh, something went wrong...` (el
  verificador de tipo real lo rechaza).
- `POST {API}/getFileInfo` con el mismo cuerpo → `{"Id", "FileLeafRef",
  "FileRef":"/sites/relatoria2/<biblioteca>/<archivo>"}`: sirve para
  comprobar **qué archivo** va a entregar la descarga (ver casos raros).
- El descargador ya soporta `method: "POST"` con `body` en JSON
  (`core/downloader.py`), y acepta claves de más en el cuerpo (probado:
  la API ignora `path`). Se propone:

  ```python
  link = {
      "url": f"{API}/getDownloadFileApiBuffer#{FileLeafRef}",
      "method": "POST",
      "body": {"Id": item_id, "List": biblioteca, "path": f"cgr/{biblioteca}/{item_id}"},
  }
  ```

  - `body["path"]` da la **identidad** del documento: `compute_doc_id` usa
    `body["path"]` cuando existe; sin él todos los documentos de una misma
    fecha compartirían `url` y chocarían.
  - El `#{FileLeafRef}` da la **extensión**: sin `Content-Disposition`,
    `extract_filename` la toma del final de la URL; `requests` no envía el
    fragmento. Así el `octet-stream` se normaliza a `application/pdf` /
    `msword` / `docx` y la vista previa funciona. Alternativa más limpia
    (pregunta 6): que el descargador acepte `link["filename"]`, un cambio
    pequeño de núcleo con su prueba.
- `checks_for_republication = False`: no hay URL directa para `HEAD`.
- Muestra de 12 por sección: resoluciones mediana 0,25 MB (máx. 19,5 MB),
  conceptos mediana 3,9 MB (máx. 11,3 MB); respuesta en ~0,7-0,8 s.
- Extensiones desde 2015: resoluciones 390 PDF, 103 DOCX, 23 DOC; conceptos
  todos PDF; circulares PDF/DOCX. Todas permitidas por
  `core/verificacion_archivos.py`.

## Fechas y filtro

- Las fechas vienen en ISO UTC con tres horas distintas según cómo se cargó
  la fila: `T05:00:00Z` (medianoche de Colombia), `T07:00:00Z` y
  `T08:00:00Z` (medianoche del Pacífico, la zona del servidor de
  SharePoint). En los tres casos **la parte de la fecha (`[:10]`) es la
  fecha correcta**; no se convierte de zona. No existe ninguna hora ≥ 12.
- `f_public = f_providencia` = fecha de expedición (la API no da fecha de
  publicación; `Created`/`Modified` no vienen). Filtro `fini <= fecha <= ffin`.
  **Piso:** 2015.
- Fila sin fecha (4 en resoluciones, ninguna desde 2015 salvo
  `OGZ-00801-2022`): se omite con aviso.
- **Retraso de carga:** desconocido con precisión. Por el orden de los `Id`
  de SharePoint, la mitad de las resoluciones se sube en días y el 90 % en
  menos de 45 días; hay cargas en lote de conceptos viejos. Como cada
  corrida trae la biblioteca completa en una petición, mirar atrás no
  cuesta: **`scheduled_min_lookback_days = 120`**. Lo ya descargado se
  salta por `doc_id`.

## Número y nombre canónico

### Resoluciones

La CGR numera **por serie**, cada una con su consecutivo:

| Serie (en el archivo) | Clasificación | Desde 2015 |
|---|---|---|
| `OGZ` | Resolución Organizacional (y 4 de "Proceso de Responsabilidad Fiscal") | 287 |
| `REG-EJE` | Resolución Reglamentaria Ejecutiva | 159 |
| `REG-ORG` | Resolución Reglamentaria Orgánica | 70 |

Como el número se repite entre series (`OGZ-0001-2015` y `REG-EJE-0001-2015`
son documentos distintos), la serie entra en el título:
`R_CGR_OGZ-0897_2026`, `R_CGR_REG-EJE-0123_2026`, `R_CGR_REG-ORG-0043_2020`
(pregunta 3).

- Se lee `FileLeafRef` sin extensión con
  `^(OGZ|REG-EJE|REG-ORG|ORG|REG)[- ]*(\d+[A-Z]?)[- ]+(\d{4})`; número sin
  ceros a la izquierda y relleno a 4 (`00801` → `0801`, `0131A` se
  conserva). Se descartan sufijos `(2)`, `FD`, `.` final.
- Si el archivo no encaja (hoy ninguno desde 2015; el campo "Número" sí
  falla en 4, p. ej. `0008-2016` cuyo archivo es `REG-ORG-0008-2016.PDF`)
  → campo "Número" + año de la fecha; si tampoco, texto saneado,
  `title_unverified=True` y aviso.
- **Año = el del número**, no el de la fecha. Hay 6 filas donde no
  coinciden (`REG-EJE-0103-2021` expedida `2022-01-17`, `OGZ-0401-2016`
  con fecha `2015-03-17`…): título con el año del número, `f_public` con la
  fecha de la fila, y aviso. No se "arregla".
- `detalle` = `Clasificacion` + epígrafe.

### Conceptos jurídicos

- Desde 2016 la Oficina Jurídica numera `CGR-OJ-<n>-<año>` (con variantes:
  `CGR–OJ` con guion largo, `de 2024` en vez de `-2024`, `PI` de "posición
  institucional" delante o detrás, `0CGR-OJ`, `CGR-0J`).
  Se normaliza a `CTO_CGR_{n:04}_{año}`: `CGR-OJ-130-2026` →
  `CTO_CGR_0130_2026`; `CGR-OJ-0094A-2021-PI` → `CTO_CGR_0094A_2021`.
- En 2015 los conceptos se identifican por el **radicado** del gestor
  documental (`2015EE0012345`, `2015IE0121754`, 8 casos con `1E` por error
  de digitación: `20151E0038709`). Propuesta: `CTO_CGR_2015EE0012345_2015`
  (el radicado completo, sin rellenar), pregunta 4.
- Caso suelto `CGR-OJ-2016IE0067575` → radicado `2016IE0067575`.
- Año = el del número; 2 discrepancias con la fecha
  (`CGR-OJ-157 de 2024` fechado `2025-01-03`; `CGR-OJ-017-2002` fechado
  `2022-02-14`, el número trae un error de digitación): título con el año
  del número, aviso.

### Circulares

`Circular 0004-2015` → `C_CGR_0004_2015`; `Circular Conjunta 0010-2025` →
`CJ_CGR_0010_2025` (prefijo `CJ` ya existe en la guía);
`CIRCULAR- AUDITORIAS` (sin número) → `title_unverified=True`.

`save_path = storage_path(_SOURCE, fecha, tipo, f"{title}(extension)")`.

## Casos raros del sitio

| Caso | Qué se hace |
|---|---|
| **La API ignora `List`**: la descarga busca el `Id` en una sola de las bibliotecas, sin importar el `List` que se mande. Los `Id` se repiten entre bibliotecas (239 repetidos). Para esos, el sitio oficial entrega **otro documento** (p. ej. la Circular `0001-2022`, `Id` 7, descarga la Resolución `OGZ-0012-2014`). | Antes de emitir un documento cuyo `Id` aparece en otra biblioteca, el scraper llama a `getFileInfo` y compara `FileRef` con `/sites/relatoria2/<biblioteca>/<FileLeafRef>`. Si no coincide → se omite con aviso ("la CGR entrega otro archivo para este registro"). Para eso se leen también los listados de las otras bibliotecas (4 peticiones, ~5 MB). Si la CGR lo corrige, los documentos entran solos. |
| Afectados hoy (desde 2015) | Resoluciones 1 (`REG-ORG-0043-2020`, `Id` 311); conceptos 1 (`CGR-OJ-173-2021`, `Id` 1259); **circulares 57 de 60**; jurisprudencia 105. Se propone avisar a la entidad (pregunta 2). |
| `getFileInfo`/descarga responden a veces `Ohhh, something went wrong...` para un `Id` válido (visto con los `Id` 2-5, intermitente) | En el scraper: un reintento; si sigue, se omite con aviso. En la descarga: el verificador de tipo lo rechaza y el documento queda fallido; la siguiente corrida lo reintenta. |
| Mismo número dos veces en la serie con archivos distintos (`CGR-OJ-157-2024`; `CGR-OJ-0219-2020` / `CGR-OJ-219-2020` del mismo día; `REG-EJE-00131A-2024` / `REG-EJE-0131A-2024`) | Dedup por (sección, serie, número, año): se queda la primera fila y se avisa. |
| Mismo concepto subido dos veces (`CGR-OJ-177-2022.docx.pdf` y `.pdf`; `CGR-OJ-0021-2018 (1).pdf`, fechas 18 y 19-02) | Igual: dedup por número + aviso. |
| Campo "Número" vacío o truncado | Se usa el nombre del archivo (ver arriba). |
| Fila sin archivo legible por extensión (`FileLeafRef` = `2026`, circular `Id` 83) | Se omite con aviso. |

## Volumen esperado (desde 2015, por fecha de expedición)

| Sección | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Resoluciones | 43 | 45 | 46 | 30 | 36 | 77 | 50 | 43 | 50 | 37 | 23 | 36 | 516 |
| Conceptos | 195 | 249 | 262 | 195 | 193 | 214 | 240 | 233 | 218 | 164 | 219 | 130 | 2.512 |
| Circulares (descargables) | 1 | | | | | | | | | | 2 | | 3 (de 60) |

Corrida completa: **~3.030 archivos**, del orden de **10 GB** (los conceptos
pesan ~4 MB de mediana porque son escaneos), unas **1-1,5 h** de descarga.
Corrida diaria: 4 peticiones de listado (~5 MB, ~5 s), unas pocas
`getFileInfo` y 0-5 archivos nuevos.

## Fuera de alcance (v1)

- **Jurisprudencia** (341 sentencias y autos de altas cortes; sólo 2011-2016
  y 2022-2024, y 237 de 341 no se pueden descargar por el error de `Id`).
  No son actos de la CGR y ya llegan por las familias de las cortes.
- **Histórico anterior a abril de 2014**
  (`estrategicos.contraloria.gov.co/normatividad/…/busqueda.asp`, ASP
  clásico): queda bajo el piso.
- Resoluciones y conceptos anteriores a 2015 (1.183 resoluciones desde
  1995, 140 conceptos de 2014).
- Boletín Jurídico (`relatoria.z20.web.core.windows.net/boletines/`):
  publicación de divulgación, no normativa.
- "Normativa aplicable" (leyes externas) y "Producción normativa"
  (proyectos).
- Relatoría de fallos de responsabilidad fiscal: no está publicada en este
  sistema (la página "Relatoría - decisiones destacadas" es la portada
  general de noticias).

## Integración

**Archivos nuevos:** `core/scrapers/families/contraloria.py`
(`@register_family("contraloria")`), `tests/families/test_contraloria.py`.

**Archivos que se tocan:** `core/scrapers/families/__init__.py`,
`core/seed.py` (`_SOURCE = "Contraloría General de la República"`,
`family_params={}`), `tests/test_seed.py` (conteos), ficha en
`docs/guia-despliegue-sistemas.md`.

Sin cambios de núcleo si se acepta el fragmento `#archivo` en la URL
(pregunta 6). Sin migración Alembic. En producción: `python -m core.seed`
una vez.

## Pruebas

`tests/families/test_contraloria.py`, con `responses` y JSON real de la API:

1. Fecha: `…T05:00:00Z`, `…T07:00:00Z`, `…T08:00:00Z` → misma fecha; fila
   sin fecha → omitida con aviso.
2. Resoluciones: `OGZ-0897-2026.pdf` → `R_CGR_OGZ-0897_2026`;
   `REG-EJE-0123-2026.PDF` → `R_CGR_REG-EJE-0123_2026`;
   `OGZ-00801-2022.PDF` → `…_0801_2022`; `REG-EJE-0131A-2024.pdf` →
   `…_0131A_2024`; `OGZ-0824-2023 (2).PDF` y `OGZ-0825-2023 FD.PDF` sin
   sufijo; año del número distinto al de la fecha → aviso.
3. Conceptos: `CGR-OJ-130-2026` → `CTO_CGR_0130_2026`; `CGR–OJ-157 de 2024`,
   `CGR-OJ-0094A-2021-PI`, `0CGR-OJ-0189-2018`, `CGR-0J-016 de 2024`;
   radicados `2015EE…`, `20151E…`, `CGR-OJ-2016IE0067575`.
4. Circulares: `Circular 0004-2015` → `C_CGR_0004_2015`; conjunta → `CJ_…`;
   sin número → `title_unverified`.
5. `link`: URL con `#FileLeafRef`, `method == "POST"`, `body` con `Id`,
   `List` y `path`; dos documentos del mismo día dan `doc_id` distintos.
6. `Id` repetido entre bibliotecas: `getFileInfo` coincide → se emite; no
   coincide → se omite con aviso; responde "something went wrong" dos veces
   → se omite con aviso. `Id` único → no se llama a `getFileInfo`.
7. Dedup por número (dos filas mismo número) → una + aviso.
8. Filtro por fecha y piso; `scheduled_min_lookback_days == 120`;
   `checks_for_republication is False`.
9. `stop_event`, `limit`, una sección que falla (aviso y sigue).

## Preguntas para el usuario / administrador

1. **Secciones:** ¿resoluciones + conceptos jurídicos (propuesto)? ¿Se
   suman las circulares aunque hoy sólo 3 de 60 se puedan descargar?
2. **Error de la API:** ¿se avisa a la CGR de que su buscador entrega otro
   archivo para 57 circulares, 105 sentencias, una resolución y un
   concepto? (No es algo que se pueda arreglar de nuestro lado.)
3. **Nombre de resoluciones:** ¿`R_CGR_OGZ-0897_2026` con la serie en el
   número (propuesto), o `R_CGR_0897_2026` aceptando que el número se
   repite entre series (habría que distinguirlas con otro sufijo)?
4. **Conceptos de 2015** (radicado en vez de número): ¿
   `CTO_CGR_2015EE0012345_2015` (propuesto)?
5. **Piso:** ¿2015? (~10 GB la primera corrida, sobre todo por los
   conceptos.)
6. **Extensión del archivo:** ¿se acepta el truco del fragmento
   `…/getDownloadFileApiBuffer#OGZ-0897-2026.pdf` en la URL, o se prefiere
   un cambio pequeño en `core/downloader.py` (`link["filename"]`)?
7. **Sigla `CGR`:** ¿se aprueba?

## Plan de implementación (cuando se apruebe)

1. Prueba + lectura de fecha y número → título para las tres secciones
   (casos 1-4).
2. Prueba + armado del `link` e identidad (caso 5).
3. Prueba + verificación con `getFileInfo` de los `Id` repetidos y dedup
   (casos 6-7).
4. Prueba + `scrap()` con la API simulada (casos 8-9).
5. Import en `families/__init__.py`, seed y `tests/test_seed.py`.
6. Corrida real local desde 2015 (abrir varios PDF y comparar con el
   listado) y segunda corrida sin descargas nuevas.
7. Ficha en `docs/guia-despliegue-sistemas.md`.
