# Nueva fuente: Procuraduría General de la Nación (PGN) — Design

## Problema

El equipo de fuentes pidió la normatividad de la Procuraduría General de la
Nación, partiendo de
`https://www.procuraduria.gov.co/procuraduria/Pages/normatividad.aspx`, y
además sus **conceptos** (sección SIREL). Una sola fuente, dos secciones.
Familia técnica nueva: `procuraduria`, sigla `PGN`.

## Descubrimiento

### Estructura del sitio

- La página de SharePoint `normatividad.aspx` **no tiene contenido propio**:
  su `PlaceHolderMain` está vacío y el contenido real es un marco hacia la
  **Relatoría**, una aplicación Java aparte:
  `https://apps.procuraduria.gov.co/relatoria/index.jsp?option=co.gov.pgn.relatoria.frontend.component.pagefactory.NormatividadPageFactory`.
- Un navegador sin ventana con el agente de usuario por defecto
  (`HeadlessChrome`) recibe una página de bloqueo ("Página Web No
  Disponible!") en `www.procuraduria.gov.co`. Con un agente de usuario de
  Chrome normal pasa. `requests` con un `User-Agent` de navegador funciona en
  ambos hosts.
- **`apps.procuraduria.gov.co` (las consultas de Normativa y SIREL) entrega su
  cadena TLS incompleta** (le falta el intermediario "GeoTrust EV RSA CA G2"),
  verificado con `openssl`: `certifi`/`requests` no pueden validarla y fallan
  con `CERTIFICATE_VERIFY_FAILED`. Igual que en la SSF, la SNR, Supersolidaria,
  la Corte Constitucional y la CNDJ, la sesión de consultas usa `verify=False`.
  `www.procuraduria.gov.co` (las descargas de los documentos) **sí** valida
  bien y no lleva `verify=False` — el `link` de cada documento no trae la
  clave `"verify"`.
- Ambos buscadores (Normativa y SIREL) **muestran un reCAPTCHA** en el
  formulario, pero el servidor **no lo exige**: los enlaces de paginación que
  el propio sitio pone bajo la tabla son `GET` planos y devuelven resultados.
  **Decisión del usuario:** usar esos `GET`; si algún día el servidor empieza
  a exigir el reCAPTCHA, la sección devolverá 0 y se pausa la fuente. **Nunca
  se intenta resolver ni saltar el reCAPTCHA.**

### Sección 1 — Normativa

- URL de consulta (`GET`, sin cookies ni sesión):
  `https://apps.procuraduria.gov.co/relatoria/index.jsp?option=co.gov.pgn.relatoria.frontend.component.pagefactory.NormatividadPageFactory&action=consultar_normatividad&anio={AAAA}&tematica=&numero=&tipo=&descripcion_corta=&descripcion_larga=&fecha_documento=&max_results=1000&first_result=0`
- **Sin `anio` devuelve 0 filas** → se consulta **año por año**.
  `max_results` grande trae el año entero en una página (el año más grande,
  2020, tiene 92 filas). El pie `Resultados 1 - N de M` permite verificar que
  N == M.
- Tabla `table.cms-table`, columnas: `Año | Tipo Documento | Número |
  Temática | Descripción Corta | Descripción Larga | Fecha Documento |
  (enlace "Ver Documento")`. Fecha en ISO `AAAA-MM-DD`. Hay 1 fila sin
  fecha y 1 sin enlace (en todo el catálogo).
- Catálogo al 2026-09-28: 683 filas 1991–2026. Tipos en el `<select>`:
  Acuerdo, Circular, Circular Conjunta, Circular Externa, Constitución,
  Decreto, Directiva, Directiva Conjunta, Directiva Unificada, Instructivo,
  Ley, Manual, Memorando, Protocolo, Resolución.
- **Enlaces**:
  - Propios de la PGN:
    `…/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId={base64 del id numérico}&mode=…`
    Aparecen en dos hosts (`www.` y `apps.`), con `mode=inline` o
    `mode=1#page=inline`, a veces con tabulación al final y en un caso con la
    URL concatenada varias veces. **Los de `apps.` dan 404**; la forma
    canónica `https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId={relId}&mode=inline`
    funciona para todos (verificado con ids viejos y nuevos, `HEAD` incluido).
    Sirve PDF o Word (`.doc`), con `Content-Disposition` limpio
    (`DIRECTIVA 21 DE 2025.pdf`).
  - Externos (~65): Senado (HTML), Presidencia, MinSalud, Función Pública,
    Alcaldía de Bogotá, `…/relatoria/media/file/…`, y 2 "enlaces" que son
    texto suelto. **Decisión del usuario: se excluyen** — solo entran filas
    cuyo enlace es `.webdocumento?accion=verDocumentoRel`.
- **Repetidos**: 12 filas repiten el mismo `relId` (misma norma listada dos
  veces, a veces con otra descripción o fecha) → se deduplica por `relId`,
  quedándose con la primera fila con fecha.
- **La columna "Año" puede no coincidir con la fecha** (6 casos, p. ej. una
  resolución de 2014 listada en 2020) → manda la fecha. Límite aceptado: una
  corrida cuyo rango cubre la fecha pero no el año del listado no la ve
  (p. ej. la resolución 122 con fecha 2018-09-24, listada en 2020, solo
  entra en una corrida que incluya 2020). Son 6 casos y 5 caen antes del
  piso 2015.
- En alcance (propios, 2015+, sin repetidos): **537**. Resolución 237,
  Directiva 143, Circular 101, Memorando 27, Instructivo 13, Circular
  Conjunta 8, Directiva Conjunta 5, Decreto 1, Acuerdo 1, Protocolo 1.

### Sección 2 — Conceptos (SIREL)

- URL de consulta (`GET`, sin sesión):
  `https://apps.procuraduria.gov.co/relatoria/index.jsp?option=co.gov.pgn.relatoria.frontend.component.pagefactory.PirelResolucionesPageFactory&action=consultar_area&tipo_documento={TIPO}&numero=&dependencia=&palabra_clave=&fecha_inicial={AAAA-MM-DD}&fecha_final={AAAA-MM-DD}&max_results=10000&first_result=0`
  con `TIPO` ∈ {`CONCEPTO`, `CONCEPTO (MISIONAL)`} (url-encoded). El filtro
  de fechas funciona en el servidor.
- Tabla `table.cms-table`, columnas: `Tipo Documento | Número | Dependencia
  | Tema | Subtema | Doc. (enlace) | Fecha`. Fecha en prosa española
  (`jueves, 30 julio 2026`).
- **Una fila por tema**: cada concepto se repite ~6 veces (una por
  tema/subtema) con el mismo enlace → se agrupa por `docId`.
- Volumen: `CONCEPTO (MISIONAL)` ~3.000–5.800 filas/año ≈ **580–790
  conceptos únicos/año** (2016: 578, 2025: 786); `CONCEPTO` simple: 22 en
  total, casi todos antiguos. Desde 2015: ~8.000–9.000 documentos.
- Enlace:
  `https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoWeb&elementId={ruta}&docId={id}&mode=1#page=inline,…`
  → se usa sin el fragmento `#…`. Sirve Word (`.doc`/`.docx`), `HEAD`
  funciona.
- **Número escrito a mano, muy irregular** (muestra de 2025 y 2016):
  `236-2026` (forma mayoritaria), `393`, `CONCEPTO 159 - 2026`,
  `119 de 2016`, `Concepto N. 00023`, `N/N`, `2025-525`, `16-158`, `C-6194`
  (conceptos antiguos ante la Corte Constitucional), `D-…`, codificación
  rota (`Concepto Ã¿Â¿ 061`), y ~12/año **vacíos**.
- **Números repetidos entre dependencias**: cada Procuraduría Delegada lleva
  su propio consecutivo (120 de 786 en 2025).

## Diseño

### Estructura

- Módulo `core/scrapers/families/procuraduria.py`, clase `ScrapProcuraduria`
  (patrón de `ssf.py` / `supersalud.py`): una fuente, dos secciones
  (`seccion` = `"Normativa"` / `"Conceptos"`).
- Registro en `core/scrapers/registry.py` y en `core/seed.py`
  (`family_key="procuraduria"`, nombre **"Procuraduría General de la
  Nación"**, descripción "Normativa (resoluciones, directivas, circulares,
  memorandos…) y conceptos publicados por la Procuraduría General de la
  Nación").
- Transporte: `requests` con `User-Agent` de navegador y peticiones en
  serie (una a la vez, como las demás familias; ninguna usa
  `core/rate_limit.py`). La sesión de consultas usa `verify=False` — la
  cadena TLS de `apps.procuraduria.gov.co` llega incompleta (ver
  "Estructura del sitio" arriba). Las descargas van a
  `www.procuraduria.gov.co`, que sí valida bien, así que el `link` de cada
  documento no lleva `verify=False`.
- Consultas paginadas por seguridad: se piden páginas de `_PAGINA` filas
  (`first_result` += `_PAGINA`) hasta completar el total del pie
  "Resultados … de M" (hoy un año de conceptos cabe en una sola página).
- Una búsqueda vacía legítima trae la tabla con solo el encabezado y el pie
  `Resultados 0 - 0 de 0`; **sin pie = página inesperada** (bloqueo,
  reCAPTCHA exigido, cambio del sitio) → error de la sección.
- **Piso de año: 2015** en ambas secciones (el rango de la corrida se recorta
  a `max(fini, 2015-01-01)`).

### Flujo por sección

**Normativa**
1. Para cada año `AAAA` desde `max(año(fini), 2015)` hasta `año(ffin)`:
   pedir la URL de consulta con ese año.
2. Leer las filas de `table.cms-table`; comprobar con el pie de "Resultados"
   que se leyó todo (si no, error de corrida).
3. Descartar filas sin enlace o con enlace que no sea `verDocumentoRel`.
   Extraer el **primer** `relId` del `href` y armar la URL canónica.
4. Deduplicar por `relId`.
5. Fecha del documento = columna "Fecha Documento"; si está vacía, `AAAA-01-01`
   con el año de la columna "Año".
6. Calcular títulos (ver Nomenclatura) **sobre el año completo**, y luego
   quedarse con las filas cuya fecha cae en `[fini, ffin]`.

**Conceptos**
1. Para cada año calendario que toca `[max(fini, 2015-01-01), ffin]`: pedir
   ambos tipos con `fecha_inicial=AAAA-01-01&fecha_final=AAAA-12-31`
   (año completo, para que los sufijos de choque sean estables; ver
   Nomenclatura).
2. Agrupar filas por `docId`; conservar número, dependencia, fecha y el
   enlace (sin `#…`); juntar los pares tema/subtema.
3. Fecha: `core/fecha_es` sobre `jueves, 30 julio 2026` (se descarta el día
   de la semana).
4. Calcular títulos sobre el año completo y filtrar por `[fini, ffin]`.

### Campos de `RawDocModel`

| Campo | Normativa | Conceptos |
|---|---|---|
| `title` | según Nomenclatura | según Nomenclatura |
| `tipo` | tipo tal cual del sitio (`Circular Conjunta`, `Resolución`…) | `Concepto` |
| `seccion` | `Normativa` | `Conceptos` |
| `f_public` / `f_providencia` | fecha del documento | fecha del documento |
| `detalle` | descripción corta — descripción larga (temática) | dependencia; temas: `Tema: subtema` separados por `; ` |
| `link.url` | URL canónica `verDocumentoRel` | URL `verDocumentoWeb` sin fragmento |

- `doc_id_uses_publication_date = False`: la identidad es el enlace
  canónico (`relId` / `docId` son estables); la fecha en el sitio se ha
  visto corregida entre listados (repetidos con fechas distintas), y no debe
  crear un documento nuevo.
- `checks_for_republication = True` (hay `HEAD` barato con
  `Content-Length`).
- Sin auto-marcado "útil" (solo CC/CSJ/CE lo tienen).

### Nomenclatura

**Normativa** — `{PREFIJO}_PGN_{número}_{año}`

| Tipo del sitio | Prefijo |
|---|---|
| Resolución | `R` |
| Directiva, Directiva Conjunta | `DIR` |
| Circular, Circular Conjunta | `C` |
| Memorando | `M` |
| Carta circular (si aparece) | `CCIR` |
| Instructivo | `INS` |
| Acuerdo | `A` |
| Protocolo | `PRO` |
| Decreto | código común `codigo_ley_decreto("D", …)` → `D0262000` (dedup entre fuentes de ministerios, igual que allí) |
| Cualquier otro tipo | `DOC` + aviso en el log de la corrida |

- **Número**: puramente numérico → 4 dígitos con ceros (`21` → `0021`).
  Número + letra → 4 dígitos + letra, sin espacio (`7A` → `0007A`,
  `34 A` → `0034A`). Con guion → tal cual (`100-01`, `13-4`).
- **Año**: el de la fecha del documento; si no hay fecha, la columna "Año".

**Conceptos** — `CTO_PGN_{consecutivo a 7 dígitos}_{año}`

Reglas de lectura del número (en orden; se normaliza antes: NFC, mayúsculas,
se quitan `CONCEPTO`, `NO.`, `NO`, `N.`, `Nº` y caracteres no
alfanuméricos sueltos):

1. `{n}` `-`, `/` o ` DE ` `{AAAA}` (año de 4 dígitos al final) →
   consecutivo `n`, año `AAAA`. Ej.: `236-2026`, `119 de 2016`, `263/2025`.
2. `{AAAA}-{n}` (año de 4 dígitos al inicio, entre 1990 y el año actual) →
   consecutivo `n`, año `AAAA`. Ej.: `2025-525`, `2019-430944`.
3. `{AA}-{n}` donde `AA` == los dos últimos dígitos del año de la fecha →
   consecutivo `n`, año de la fecha. Ej.: `16-158` (fecha 2016).
4. `C-{n}` / `D-{n}` (referencia de expediente ante la Corte) o un solo
   número → consecutivo `n`, año de la fecha. Ej.: `C-6194`, `393`,
   `00023`.
5. Cualquier otra cosa con dígitos → el primer grupo de dígitos como
   consecutivo, año de la fecha; aviso en el log.
6. **Sin dígitos (vacío)** → `CTO_PGN_SN{docId}_{año de la fecha}`.
   Ej.: `CTO_PGN_SN245408_2025`.

El consecutivo se rellena a 7 dígitos (`236` → `0000236`); si ya tiene más
de 7, se deja tal cual.

**Títulos repetidos** (ambas secciones, decisión del usuario: sufijo
numérico)
- Si dos o más documentos distintos producen el mismo título, se ordenan por
  su id interno del sitio (`relId` decodificado / `docId`) ascendente: el
  primero queda limpio y los siguientes llevan `_2`, `_3`…
  Ej.: `C_PGN_0001_2023`, `C_PGN_0001_2023_2`, `C_PGN_0001_2023_3`.
- Se calcula sobre **el año completo** (por eso ambas secciones consultan
  años enteros), así el título de un documento no depende del rango de la
  corrida. Los documentos nuevos del sitio reciben ids mayores, así que los
  ya guardados conservan su título.
- Límite conocido: el agrupamiento es por año de la **consulta**; un título
  cuyo año (por el número) difiere del año de la fecha podría chocar con uno
  de otro año sin detectarse. Se acepta; el guardado de archivos ya tiene su
  propia protección contra pisarse (como en Supersolidaria).

### Errores

- Página de bloqueo, reCAPTCHA exigido, tabla ausente o pie de
  "Resultados" inconsistente → error de la sección en la corrida (queda en
  `run_errors`), la otra sección sigue.
- Documento que da 404 → error por documento, como en el resto.
- Fecha ilegible → se usa `AAAA-01-01` del año consultado y aviso en el log.

## Pruebas

- `tests/families/test_procuraduria.py`, con HTML armado en la misma prueba
  copiando la estructura real de las tablas (convención del proyecto, como
  `test_ssf.py` / `test_supersolidaria.py`) y `responses` para simular el
  sitio:
  - lectura de ambas tablas y del pie "Resultados";
  - URL canónica desde todas las variantes de `href` (host `apps.`,
    `mode=1#…`, tabulación, URL concatenada) y descarte de externos;
  - dedup por `relId`; agrupación de conceptos por `docId` con sus temas;
  - prefijos por tipo, plegado de conjuntas, Decreto con código común, tipo
    desconocido → `DOC`;
  - todas las formas de número de Normativa y de Conceptos (tabla de casos
    de arriba), incluido `SN{docId}`;
  - sufijos `_2`/`_3` por choque, estables al cambiar el rango de fechas;
  - piso 2015 y filtro por `[fini, ffin]`.
- `tests/test_seed.py`: subir los conteos fijos por la familia nueva.
- Corrida real en desarrollo: un mes (Normativa + Conceptos), revisar
  títulos y archivos; luego un año completo.

## Despliegue

Código nuevo + `core.seed` una vez en producción. Sin migración.
