# Fuente Contraloría General de la República (CGR) — diseño

**Fecha:** 2026-11-23 (revisado 2026-11-26 con las decisiones del
administrador y una nueva medición contra la API en vivo)
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

Familia de scraper nueva `contraloria`, desde **2015** (fecha de expedición)
en **todas** las secciones, conceptos incluidos (decisión del administrador,
2026-11-26). Propuesta (a confirmar, pregunta 1):

| Sección | Endpoint (POST) | Biblioteca (`List`) | tipo | título | Filas desde 2015 |
|---|---|---|---|---|---|
| Resoluciones | `/getResoluciones` | `Resoluciones` | `Resolución` | `R_CGR_{serie}-{número}_{año}` | 516 |
| Conceptos jurídicos | `/getConceptosJuridicos` | `Conceptos Juridicos` | `Concepto` | `CTO_CGR_{número}_{año}` | 2.513 |
| Circulares | `/getCirculares` | `Circulares` | `Circular` / `Circular conjunta` | `C_CGR_{número}_{año}` / `CJ_CGR_{número}_{año}` | 60 |

Familia **plana**: sin anexos (un archivo por fila), sin actuaciones, sin
`family_params`.

Las **circulares** se proponen ahora **dentro** (antes eran opcionales
porque parecía que sólo 3 de 60 se podían descargar): el 2026-11-26 una
muestra de 6 se descargó bien en la mañana y, en la tarde, 30 de las 60
salían bien y 30 mal; el problema es el mismo
que afecta a las resoluciones (ver "La API confunde `Id` repetidos") y se
trata con la misma verificación, no dejando fuera la sección.

Jurisprudencia (la cuarta biblioteca) queda fuera: son sentencias y autos
del Consejo de Estado y la Corte Constitucional sobre la CGR, no actos de
la CGR, y ya llegan por las familias de las cortes.

## Construcción del sitio

- `www.contraloria.gov.co`: Liferay detrás de Azure Application Gateway
  (cookies `ApplicationGatewayAffinity*`, `JSESSIONID`). TLS válido. Sin WAF,
  sin captcha, sin desafío de JavaScript.
- `cgr-sistemanormatividad.contraloria.gov.co`: SPA (Vite + React + MUI). El
  `baseURL` de la API está en el bundle (`/assets/index-*.js`).
- `cgr-sistemarelatoria-api.contraloria.gov.co`: API Node (las rutas
  inexistentes responden al estilo Fastify: `Route GET:/… not found`). TLS
  válido (Sectigo; `requests` valida sin `verify=False`, comprobado el
  2026-11-26), CORS `*`, sin autenticación ni cookies. No hace falta pasar
  por el sitio principal.

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
10 en 10 la hace el navegador): Resoluciones 1.699 filas / 1,9 MB / 2 s;
Conceptos 2.653 / 2,5 MB / 1-3 s; Circulares 68 / 78 KB; Jurisprudencia
341 / 560 KB. Sin paginación: **una petición por sección**.

Cada fila es el ítem de SharePoint tal cual (OData):

```json
{"Id":1928,"FileLeafRef":"OGZ-0897-2026.pdf",
 "Title":"Por la cual se adopta la versión 7.0 del Manual Específico de Funciones …",
 "Clasificacion":"Resolución Organizacional","Numero_x0020_de_x0020_resolucion":"OGZ-0897-2026",
 "Fecha_x0020_de_x0020_expedicion":"2026-11-04T08:00:00Z","Vigencia":"Rige a partir de su publicación",
 "Tema2":"Adoptar la versión 7.0 del Manual …"}
{"Id":5984,"FileLeafRef":"CGR-OJ-130-2026.pdf","Title":"Viabilidad juridica de modificar …",
 "Fecha":"2026-11-17T08:00:00Z","Numero_x0020_de_x0020_concepto":"CGR-OJ-130-2026","Ano":"2026",
 "TipoConcepto":"Posición institucional","Tema":"Asignación por evaluación de desempeño - …"}
```

(El 2026-11-23 esa misma fila de concepto era `Id` 5979 con fecha
2026-11-23; el 2026-11-26 es `Id` 5984 con fecha 2026-11-17 y el `Id` 5979
ya no existe. Ver "Identidad del documento".)

| Dato | Resoluciones | Conceptos | Circulares |
|---|---|---|---|
| fecha | `Fecha_x0020_de_x0020_expedicion` | `Fecha` | `Fecha` |
| número y año | `FileLeafRef` (respaldo: `Numero_x0020_de_…`) | `FileLeafRef` (respaldo: `Numero_x0020_de_concepto`) | `FileLeafRef` (respaldo: `Numero_x0020_de_x0020_Circular`) |
| extensión | `FileLeafRef` | `FileLeafRef` | `FileLeafRef` |
| `detalle` | `Title` (epígrafe) | `Tema` (`Title` está vacío en 2.511 de 2.513) | `Asunto2` |
| `Id` | sólo para el cuerpo de la descarga | ídem | ídem |

El número se lee del **nombre del archivo** y no del campo "Número": el
campo viene truncado en varias filas (`CGR-OJ-0089-20`, `CGR-OJ-182-202`,
`CGR-OJ-0210-201`) o con basura (`OGZ-0824-2023 (2)`, `OGZ-0553-2017. `),
mientras el archivo trae el número completo.

### Descarga

- `POST {API}/getDownloadFileApiBuffer` con `{"Id": <Id>, "List": "<biblioteca>"}`
  → `200`, `Content-Type: application/octet-stream`, `Content-Length`, sin
  `Content-Disposition`. `GET` y `HEAD` dan `404`. Un `Id` inexistente
  responde `200` `text/plain` `Ohhh, something went wrong...` (el
  verificador de tipo real lo rechaza).
- `POST {API}/getFileInfo` con el mismo cuerpo → `{"Id", "FileLeafRef",
  "FileRef":"/sites/relatoria2/<biblioteca>/<archivo>"}`: dice **qué
  archivo** entregaría la descarga en ese momento (ver "La API confunde
  `Id` repetidos").
- El descargador ya soporta `method: "POST"` con `body` en JSON
  (`core/downloader.py`), y la API ignora claves de más en el cuerpo
  (probado con `path`). Se propone:

  ```python
  link = {
      "url": f"{API}/getDownloadFileApiBuffer#{FileLeafRef}",
      "method": "POST",
      "body": {"Id": item_id, "List": biblioteca, "path": f"cgr/{seccion}/{clave}"},
  }
  ```

  - `body["path"]` da la **identidad** del documento (ver abajo):
    `compute_doc_id` usa `body["path"]` cuando existe; sin él todos los
    documentos compartirían `url` y chocarían.
  - El `#{FileLeafRef}` da la **extensión**: sin `Content-Disposition`,
    `extract_filename` la toma del final de la URL (comprobado en el código:
    `…/getDownloadFileApiBuffer#OGZ-0897-2026.pdf` → `.pdf`); `requests` no
    envía el fragmento. Así el `octet-stream` se normaliza a
    `application/pdf` / `msword` / `docx` y la vista previa funciona.
    Alternativa más limpia (pregunta 6): que el descargador acepte
    `link["filename"]`, un cambio pequeño de núcleo con su prueba.
  - **Enlace "ver en el sitio" muerto:** el worker guarda `link["url"]`
    como `source_url`. Aquí es un endpoint que sólo acepta `POST` (con `GET`
    da `404`), así que el enlace al origen que ve el usuario no abre nada.
    Es lo mismo que pasa con las otras familias de descarga por `POST`; se
    anota en la ficha de despliegue.
- `checks_for_republication = False`: no hay URL directa para `HEAD`.
- Muestra de 12 por sección: resoluciones mediana 0,25 MB (máx. 19,5 MB),
  conceptos mediana 3,9 MB (máx. 11,3 MB); respuesta en ~0,7-0,8 s.
- Extensiones desde 2015: resoluciones 390 PDF, 103 DOCX, 23 DOC; conceptos
  todos PDF; circulares PDF/DOCX. Todas permitidas por
  `core/verificacion_archivos.py`.

### Identidad del documento

- **El `Id` de SharePoint no es estable:** la fila `CGR-OJ-130-2026` pasó
  del `Id` 5979 (2026-11-23) al 5984 (2026-11-26), con otra fecha. La CGR
  borra y vuelve a crear filas. Si la identidad fuera el `Id`, la fila
  recreada se descargaría otra vez como documento nuevo con el mismo título
  (y con la ventana de 120 días, eso pasa en la corrida diaria).
- Por eso la identidad sale del **número normalizado**:
  `clave = f"{serie}-{valor}-{año}"` para resoluciones (`OGZ-801-2022`),
  `f"{valor}-{año}"` para conceptos y circulares (`130-2026`,
  `CJ-10-2025`), donde `valor` es el número sin ceros a la izquierda y con
  su letra (`0131A` → `131A`). Una fila sin número legible usa el
  `FileLeafRef` saneado como clave.
- `doc_id_uses_publication_date = False`: la fecha de la fila también
  cambia al recrearla (ver arriba), así que no entra en la identidad.
- El `Id` sólo va en el cuerpo de la descarga (y se toma del listado de la
  corrida, por eso una fila recreada se descarga con su `Id` nuevo).
- Consecuencia: si la CGR reemplaza el archivo de un número ya guardado,
  no se detecta (no hay `HEAD`); es lo mismo que con
  `checks_for_republication = False` en otras familias.

## Fechas y filtro

- Las fechas vienen en ISO UTC con tres horas distintas según cómo se cargó
  la fila: `T05:00:00Z` (medianoche de Colombia), `T07:00:00Z` y
  `T08:00:00Z` (medianoche del Pacífico, la zona del servidor de
  SharePoint). En los tres casos **la parte de la fecha (`[:10]`) es la
  fecha correcta**; no se convierte de zona. No existe ninguna hora ≥ 12.
- `f_public = f_providencia` = fecha de expedición (la API no da fecha de
  publicación; `Created`/`Modified` no vienen). Filtro `fini <= fecha <= ffin`.
  **Piso:** 2015 en las tres secciones.
- Fila sin fecha (4 en resoluciones, ninguna desde 2015 salvo
  `OGZ-00801-2022`): se omite con aviso.
- **Retraso de carga:** desconocido con precisión. Por el orden de los `Id`
  de SharePoint, la mitad de las resoluciones se sube en días y el 90 % en
  menos de 45 días; hay cargas en lote de conceptos viejos. Como cada
  corrida trae la biblioteca completa en una petición, mirar atrás no
  cuesta: **`scheduled_min_lookback_days = 120`**. Lo ya descargado se
  salta por `doc_id`.

## Número y nombre canónico

**El número se copia tal como lo escribe la CGR** en el nombre del archivo
(decisión del administrador, 2026-11-26): sin rellenar con ceros ni
quitarlos. Para comparar números (dedup, identidad) se usa el valor
normalizado de "Identidad del documento"; el título lleva el texto tal
cual.

### Resoluciones

La CGR numera **por serie**, cada una con su consecutivo:

| Serie (en el archivo) | Clasificación | Desde 2015 |
|---|---|---|
| `OGZ` | Resolución Organizacional (y 4 de "Proceso de Responsabilidad Fiscal") | 287 |
| `REG-EJE` | Resolución Reglamentaria Ejecutiva | 159 |
| `REG-ORG` | Resolución Reglamentaria Orgánica | 70 |

Como el número se repite entre series (`OGZ-0001-2015` y `REG-EJE-0001-2015`
son documentos distintos), **la serie entra en el número** y se conserva el
prefijo `R` (decisión del administrador, 2026-11-26; mismo estilo que la
Auditoría, `R_AGR_ORG-003_2026`): `R_CGR_OGZ-0897_2026`,
`R_CGR_REG-EJE-0123_2026`, `R_CGR_REG-ORG-0043_2020`.

- Se lee `FileLeafRef` sin extensión con
  `^(OGZ|REG-EJE|REG-ORG|ORG|REG)[- ]*(\d+[A-Z]?)[- ]+(\d{4})` (comprobado:
  encaja en las 516 filas desde 2015); el número va tal cual
  (`OGZ-00801-2022` → `R_CGR_OGZ-00801_2022`, `REG-EJE-0131A-2024` →
  `R_CGR_REG-EJE-0131A_2024`). Se descartan sufijos `(2)`, `FD`, `.` final.
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
  institucional" **detrás** (`CGR-OJ-0094A-2021-PI`) o **entre `OJ` y el
  número** (`CGR-OJ-PI-144-2024.pdf`, `CGR-OJ-PI-031 de 2024.pdf`,
  `CGR-OJ-PI-217-2022.pdf`), `0CGR-OJ`, `CGR-0J`).
  Título `CTO_CGR_{n}_{año}` con el número tal cual: `CGR-OJ-130-2026` →
  `CTO_CGR_130_2026`; `CGR-OJ-0094A-2021-PI` → `CTO_CGR_0094A_2021`;
  `CGR-OJ-PI-144-2024` → `CTO_CGR_144_2024`; `0CGR-OJ-0189-2018` →
  `CTO_CGR_0189_2018`.
- En 2015 los conceptos se identifican por el **radicado** del gestor
  documental (`2015EE0012345`, `2015IE0121754`, 8 casos con `1E` por error
  de digitación: `20151E0038709`). Propuesta: `CTO_CGR_2015EE0012345_2015`
  (el radicado completo, tal cual), pregunta 4.
- Caso suelto `CGR-OJ-2016IE0067575` → radicado `2016IE0067575`.
- Año = el del número; 2 discrepancias con la fecha
  (`CGR-OJ-157 de 2024` fechado `2025-01-03`; `CGR-OJ-017-2002` fechado
  `2022-02-14`, el número trae un error de digitación): título con el año
  del número, aviso.

### Circulares

La CGR lleva **un solo consecutivo** de circulares por año, sin distinguir
externas de internas: el nombre del archivo y el campo "Número" dicen sólo
`Circular 0011-2015`, y el campo `Destinatario` mezcla en la misma serie
circulares a entidades externas ("Servidores públicos y particulares que
administran bienes y fondos de la nación", "Gobernadores - Alcaldes") e
internas ("Funcionarios de la Contraloría General de la República"). El
texto de algunas dice "CIRCULAR EXTERNA" (la 011 de 2015) y el de otras
sólo "CIRCULAR" (la 023 de 2025, para funcionarios de la CGR). Por eso se
usa el prefijo genérico **`C`** (como `C_SSF_…`), no `CE`; las conjuntas,
que sí lo dicen en el nombre, van con **`CJ`**.

`Circular 0004-2015` → `C_CGR_0004_2015`; `Circular 023-2025` →
`C_CGR_023_2025`; `Circular Conjunta 0010-2025` → `CJ_CGR_0010_2025`;
`Circular - Auditorías.pdf` (campo "Número" `CIRCULAR- AUDITORIAS`, sin
número) → `title_unverified=True` y aviso.

`save_path = storage_path(_SOURCE, fecha, tipo, f"{title}(extension)")`.

## La API confunde `Id` repetidos

Los `Id` de SharePoint se repiten entre bibliotecas: 239 `Id` aparecen en
más de una. Desde 2015 eso afecta a **184 resoluciones, las 60 circulares
y 1 concepto**. Para esos `Id`, `getFileInfo` y la descarga entregan el
archivo de **una sola** de las bibliotecas que lo comparten, y el `List`
que se manda no siempre se respeta.

**Lo que se midió (2026-11-26):** para las 245 filas afectadas desde 2015
se llamó `getFileInfo` con su `List` correcto y se comparó `FileRef` con
`/sites/relatoria2/<biblioteca>/<FileLeafRef>`.

| Sección | Filas afectadas desde 2015 | 1.ª medición (mañana, muestra) | 2.ª medición (tarde, completa) |
|---|---|---|---|
| Resoluciones | 184 | `OGZ-0876-2025` (`Id` 1259) entregaba el concepto `CGR-OJ-173-2021`; `REG-ORG-0043-2020` (`Id` 311) y `REG-EJE-0095-2021` (`Id` 353) bien | **184 bien** (incluida `OGZ-0876-2025`) |
| Conceptos | 1 (`CGR-OJ-173-2021`, `Id` 1259) | bien (descarga comprobada abriendo el PDF) | **mal**: entrega la resolución `OGZ-0876-2025` |
| Circulares | 60 | las 6 de la muestra bien (`Id` 7, 63, 64, 65, 74, 82; la 011 de 2015 y la 023 de 2025 comprobadas abriendo el archivo) | **30 bien, 30 mal**: las de `Id` 33-65 (1 de 2019, 15 de 2020, 8 de 2021, 6 de 2022) entregan resoluciones `OGZ` de 2015 (p. ej. la `Circular 0009-2022`, `Id` 65, entrega `OGZ-0350-2015`); las de 2015-2018, la 0006/0005/0004/0002 de 2019 y las dos de 2025 bien |

(La 2.ª medición: 245 llamadas, una por segundo. Repetida seis veces en
un minuto para los `Id` 7 y 1259, la respuesta no cambió: el cambio de
biblioteca ocurre en horas, no petición a petición. La 1.ª medición del
diseño original, del 2026-11-23, decía otra cosa todavía: 57 de 60
circulares mal, `REG-ORG-0043-2020` mal.)

**Conclusión:** no hay una lista fija de registros dañados. Para un `Id`
compartido, la API resuelve unas veces a una biblioteca y otras a otra (el
mismo `Id` 1259 entregó el concepto en la mañana y la resolución en la
tarde; las circulares 63-65 se entregaron bien en la mañana y mal en la
tarde).
Además, a veces responde `Ohhh, something went wrong...` para un `Id`
válido (visto con los `Id` 2-5, 351 y 353; intermitente).

**Qué hace el scraper:**

1. Lee los cuatro listados (también Jurisprudencia, sólo para saber qué
   `Id` se repiten; 4 peticiones, ~5 MB).
2. Aplica el filtro de fechas (`fini`-`ffin`) y el piso **antes** de
   verificar.
3. Sólo para las filas **dentro de la ventana de la corrida** cuyo `Id`
   aparece en otra biblioteca llama `getFileInfo` (un reintento si responde
   "something went wrong") y compara `FileRef`. Si coincide → emite el
   documento. Si no → lo omite con aviso ("la CGR entrega otro archivo para
   este registro en este momento"). Si es reciente, la corrida diaria
   (ventana de 120 días) lo vuelve a intentar y entra solo cuando la API lo
   resuelva bien. Si es histórico (fuera de esa ventana, p. ej. las
   circulares de 2020), sólo vuelve a intentarse con una corrida manual de
   su rango: los avisos de la carga histórica dicen qué rangos repetir.
   Los `Id` que no se repiten no se verifican.
4. Corrida diaria: unas pocas llamadas `getFileInfo`. Corrida por un año
   completo: hasta ~25 (resoluciones y circulares de ese año), una por
   segundo.

**Límite conocido (hueco entre verificar y descargar):** la verificación se
hace al leer el listado; el worker descarga después (segundos u horas, según
la cola). Como la API cambia de biblioteca con el tiempo, un documento
verificado puede descargarse con el archivo equivocado. La descarga no trae
nombre de archivo, así que el descargador no puede notarlo. Mitigaciones:
encolar estos documentos al final de la verificación (lo normal), y en la
corrida real local abrir los archivos de los `Id` repetidos y compararlos
con el listado (plan, paso 6). Si se ve que pasa en la práctica, un v2 puede
verificar en el worker justo antes de descargar (cambio de núcleo: un
"chequeo previo" por familia) o comparar el texto del PDF con el número.

Se propone además avisar a la CGR (pregunta 2).

## Casos raros del sitio

| Caso | Qué se hace |
|---|---|
| `Id` repetido entre bibliotecas | Ver "La API confunde `Id` repetidos". |
| `getFileInfo`/descarga responden a veces `Ohhh, something went wrong...` para un `Id` válido | En el scraper: un reintento; si sigue, se omite con aviso. En la descarga: el verificador de tipo lo rechaza y el documento queda fallido; la siguiente corrida lo reintenta. |
| Fila recreada con otro `Id` y otra fecha (`CGR-OJ-130-2026`: `Id` 5979 → 5984) | La identidad es el número normalizado: no se duplica (ver "Identidad del documento"). |
| Mismo número dos veces en la serie con archivos distintos (`CGR-OJ-157-2024`; `CGR-OJ-0219-2020` / `CGR-OJ-219-2020` del mismo día; `REG-EJE-00131A-2024` / `REG-EJE-0131A-2024`) | Dedup por (sección, serie, valor del número, año) — los dos de cada par tienen la misma clave aunque el texto difiera: se queda la primera fila (su número tal cual va al título) y se avisa. |
| Mismo concepto subido dos veces (`CGR-OJ-177-2022.docx.pdf` y `.pdf`; `CGR-OJ-0021-2018 (1).pdf`, fechas 18 y 19-02) | Igual: dedup por número + aviso. |
| Campo "Número" vacío o truncado | Se usa el nombre del archivo (ver arriba). |
| Fila sin archivo legible por extensión (`FileLeafRef` = `2026`, circular `Id` 83) | Se omite con aviso. |
| La `Circular Conjunta 0001-2021` es el mismo acto que la `AGR-CGR_Circular_Conjunta_001_de_2021` de la Auditoría | La Auditoría tiene piso 2025, así que hoy sólo entra por la CGR. Una conjunta futura publicada por las dos quedaría una vez por entidad. |

## Volumen esperado (desde 2015, por fecha de expedición)

| Sección | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Resoluciones | 43 | 45 | 46 | 30 | 36 | 77 | 50 | 43 | 50 | 37 | 23 | 36 | 516 |
| Conceptos | 195 | 249 | 262 | 195 | 193 | 214 | 240 | 233 | 218 | 164 | 219 | 131 | 2.513 |
| Circulares | 5 | 9 | 3 | 7 | 5 | 15 | 8 | 6 | | | 2 | | 60 |

Corrida completa: **~3.090 archivos, del orden de 10 GB** (los conceptos
pesan ~4 MB de mediana porque son escaneos: ~2.500 × 4 MB), unas
**1-1,5 h** de descarga. Corrida diaria: 4 peticiones de listado (~5 MB,
~5 s), unas pocas `getFileInfo` y 0-5 archivos nuevos.

**Riesgo de disco en producción:** el disco C: del servidor de producción
se llenó el 2026-11-19 (recuperación de la CSJ) y dejó caído Docker; está
pendiente que sistemas lo amplíe. Una primera corrida de ~10 GB **no se
lanza hasta que el disco esté ampliado** y con espacio confirmado, y se
hace **por rangos de años** (p. ej. un año por corrida, empezando por el
más reciente), revisando el espacio libre entre una y otra.

## Fuera de alcance (v1)

- **Jurisprudencia** (341 sentencias y autos de altas cortes; sólo 2011-2016
  y 2022-2024). No son actos de la CGR y ya llegan por las familias de las
  cortes.
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
- Verificar el archivo en el worker justo antes de descargarlo (posible v2,
  ver "Límite conocido").

## Integración

**Archivos nuevos:** `core/scrapers/families/contraloria.py`
(`@register_family("contraloria")`), `tests/families/test_contraloria.py`.

**Archivos que se tocan:** `core/scrapers/families/__init__.py`,
`core/seed.py` (`_SOURCE = "Contraloría General de la República"`,
`family_params={}`), `tests/test_seed.py` (conteos), ficha en
`docs/guia-despliegue-sistemas.md` (incluye: enlace al origen muerto, el
problema de `Id` repetidos y que la primera corrida va por años con el disco
ampliado).

Sin cambios de núcleo si se acepta el fragmento `#archivo` en la URL
(pregunta 6). Sin migración Alembic. En producción: `python -m core.seed`
una vez.

## Pruebas

`tests/families/test_contraloria.py`, con `responses` y JSON real de la API:

1. Fecha: `…T05:00:00Z`, `…T07:00:00Z`, `…T08:00:00Z` → misma fecha; fila
   sin fecha → omitida con aviso.
2. Resoluciones, número tal cual: `OGZ-0897-2026.pdf` →
   `R_CGR_OGZ-0897_2026`; `REG-EJE-0123-2026.PDF` →
   `R_CGR_REG-EJE-0123_2026`; `OGZ-00801-2022.PDF` →
   `R_CGR_OGZ-00801_2022`; `REG-EJE-0131A-2024.pdf` →
   `R_CGR_REG-EJE-0131A_2024`; `OGZ-0824-2023 (2).PDF` y
   `OGZ-0825-2023 FD.PDF` sin sufijo; año del número distinto al de la
   fecha → aviso.
3. Conceptos: `CGR-OJ-130-2026` → `CTO_CGR_130_2026`; `CGR–OJ-157 de 2024`
   → `CTO_CGR_157_2024`; `CGR-OJ-0094A-2021-PI` → `CTO_CGR_0094A_2021`;
   **`CGR-OJ-PI-144-2024` → `CTO_CGR_144_2024`** y `CGR-OJ-PI-031 de 2024`
   → `CTO_CGR_031_2024`; `0CGR-OJ-0189-2018`, `CGR-0J-016 de 2024`;
   radicados `2015EE…`, `20151E…`, `CGR-OJ-2016IE0067575`.
4. Circulares: `Circular 0004-2015` → `C_CGR_0004_2015`; `Circular
   023-2025` → `C_CGR_023_2025`; conjunta → `CJ_CGR_0010_2025`; sin número
   → `title_unverified`.
5. `link` e identidad: URL con `#FileLeafRef`, `method == "POST"`, `body`
   con `Id`, `List` y `path`; `path` sale del número normalizado (no del
   `Id`): la misma fila con otro `Id` y otra fecha da el **mismo**
   `doc_id`; dos documentos del mismo día dan `doc_id` distintos;
   `doc_id_uses_publication_date is False`.
6. `Id` repetido entre bibliotecas: `getFileInfo` coincide → se emite; no
   coincide → se omite con aviso; responde "something went wrong" dos veces
   → se omite con aviso. `Id` único → no se llama a `getFileInfo`. Fila
   con `Id` repetido **fuera de la ventana** de la corrida → no se llama a
   `getFileInfo`.
7. Dedup por número (dos filas mismo número, incluso `0219` / `219`) → una
   + aviso.
8. Filtro por fecha y piso; `scheduled_min_lookback_days == 120`;
   `checks_for_republication is False`.
9. `stop_event`, `limit`, una sección que falla (aviso y sigue).

## Preguntas para el usuario / administrador

1. **Secciones:** ¿resoluciones + conceptos jurídicos + circulares
   (propuesto ahora)? (Revisado el 2026-11-26: las circulares sí se pueden
   descargar; fallan sólo mientras la API resuelve mal su `Id` — en la
   medición de la tarde, 30 de 60 —, igual que puede pasar con las
   resoluciones, y la verificación lo cubre: las que fallan se omiten con
   aviso y entran al repetir la corrida de su rango más adelante.)
2. **Error de la API:** ¿se avisa a la CGR de que su buscador, para los `Id`
   que se repiten entre bibliotecas (184 resoluciones, 60 circulares y 1
   concepto desde 2015), entrega a veces el archivo de otra biblioteca?
   (No es algo que se pueda arreglar de nuestro lado.)
3. **Nombre de resoluciones:** **Respondida por el administrador el
   2026-11-26:** la serie va en el número y se conserva `R`:
   `R_CGR_OGZ-0897_2026`, `R_CGR_REG-EJE-0123_2026`,
   `R_CGR_REG-ORG-0043_2020`. La Auditoría usa el mismo estilo
   (`R_AGR_ORG-003_2026`).
4. **Conceptos de 2015** (radicado en vez de número): ¿
   `CTO_CGR_2015EE0012345_2015` (propuesto)?
5. **Piso:** **Respondida por el administrador el 2026-11-26:** 2015 en
   todas las secciones, conceptos incluidos, aceptando ~10 GB en la primera
   corrida; antes hay que ampliar el disco de producción y la primera
   corrida va por rangos de años.
6. **Extensión del archivo:** ¿se acepta el truco del fragmento
   `…/getDownloadFileApiBuffer#OGZ-0897-2026.pdf` en la URL (funciona con el
   código actual), o se prefiere un cambio pequeño en `core/downloader.py`
   (`link["filename"]`)?
7. **Sigla `CGR`:** ¿se aprueba? (Revisado en el código: no existe en
   ningún título ni familia; no hay choque.)
8. **Formato del número:** **Respondida por el administrador el
   2026-11-26:** el número se copia tal como lo escribe la entidad, sin
   rellenar con ceros ni quitarlos (`CTO_CGR_130_2026`,
   `R_CGR_OGZ-00801_2022`, `C_CGR_0004_2015`).

## Plan de implementación (cuando se apruebe)

1. Prueba + lectura de fecha y número → título para las tres secciones
   (casos 1-4).
2. Prueba + armado del `link` e identidad por número normalizado (caso 5).
3. Prueba + verificación con `getFileInfo` de los `Id` repetidos dentro de
   la ventana, y dedup (casos 6-7).
4. Prueba + `scrap()` con la API simulada (casos 8-9).
5. Import en `families/__init__.py`, seed y `tests/test_seed.py`.
6. Corrida real local por un año reciente (p. ej. 2025): abrir los archivos
   de los `Id` repetidos y varios más y compararlos con el listado; segunda
   corrida sin descargas nuevas.
7. Ficha en `docs/guia-despliegue-sistemas.md`.
8. **Producción:** no lanzar la carga histórica hasta que sistemas amplíe
   el disco (se llenó el 2026-11-19). Después, una corrida por año
   (2026 → 2015), revisando el espacio libre entre corridas.
