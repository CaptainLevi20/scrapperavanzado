# Nueva fuente: Ministerio de Salud y Protección Social (MinSalud) — Design

## Problema

El equipo de fuentes pidió cuatro secciones de normativa del Ministerio de
Salud y Protección Social:

- `https://www.minsalud.gov.co/Normativa/Paginas/Norm_Resoluciones.aspx`
- `https://www.minsalud.gov.co/Normativa/Paginas/Norm_Circulares.aspx`
- `https://www.minsalud.gov.co/Normativa/Paginas/Norm_Conceptos.aspx`
- `https://www.minsalud.gov.co/Normativa/Paginas/Norm_Boletines.aspx`

Una sola fuente, cuatro secciones. Familia técnica nueva: `minsalud`, sigla
`MSPS` (ya reservada como sigla de ministerio en `core/reorganize.py`).
Nomenclatura: convenciones de los ministerios (decisión del usuario,
2026-09-28).

## Descubrimiento

### Estructura del sitio

- **SharePoint.** Las cuatro páginas son marcos: su contenido es un
  `<iframe>` a vistas de **una sola biblioteca de documentos**,
  `/Normatividad_Nuevo`:
  `/Normatividad_Nuevo/Forms/{Resoluciones|Circulares|Conceptos|Boletines}.aspx?IsDlg=1`.
- Las páginas HTML son **muy lentas** (2–4 min por página con `curl`), pero
  la **API REST de SharePoint** responde rápido desde `requests` (la lista
  completa, 6.234 elementos, en ~3 s en dos páginas):
  `GET https://www.minsalud.gov.co/_api/web/GetList('/Normatividad_Nuevo')/items?$top=5000&$select=…`
  con `Accept: application/json;odata=nometadata`; paginación por
  `odata.nextLink`. Sin autenticación, sin bot-manager, sin reCAPTCHA, TLS
  válido (sin `verify=False`).
- **Filtro de cada vista** (CAML de la vista, leído por la API
  `…/views?$select=ServerRelativeUrl,ViewQuery`): `BeginsWith` sobre
  `Tipo_x0020_de_x0020_Norma` con `Resolución`, `Circular`, `Concepto` y
  `Boletines` respectivamente. Se replica ese filtro.
- Columnas útiles (nombre interno → significado):
  `ID`, `Title` (título), `FileLeafRef` (nombre del archivo), `FileRef`
  (ruta del archivo), `FSObjType` (0 = archivo, 1 = carpeta; hay 2 carpetas),
  `Tipo_x0020_de_x0020_Norma` (tipo), `A_x00f1_o` (año, texto),
  `Publicaci_x00f3_n` (fecha de publicación, ISO con hora UTC),
  `Descripci_x00f3_n` (descripción, multilínea), `Tem_x00e1_tica`,
  `Subtema`, `Responsable` (dependencia; solo en conceptos), `Created`
  (fecha de subida).
- **Descarga directa:** `https://www.minsalud.gov.co` + `FileRef`
  (url-codificado). `HEAD`/`GET` 200 en < 1 s, `Content-Length` presente,
  **sin `Content-Disposition`** (la extensión sale del tipo de contenido o de
  la URL — `core/utils.extract_filename` ya lo cubre).

### Datos (al 2026-09-28)

Tipos de norma en la biblioteca (26 valores, sucios): `Resolución` 2404,
`Concepto` 1112, `Decreto` 887, `Circular` 588, `Acuerdo CNSSS` 353,
`Resolución ` (con espacio) 204, `Ley` 190, `Boletines Jurídicos` 156, …,
`Resolución CRES` 17, `Circular CRES` 4, `Circular ` 1.

| Sección | Total | Desde 2015 (por columna Año) | Con fecha de publicación |
|---|---|---|---|
| Resoluciones | 2.625 | 1.476 | 260 |
| Circulares | 593 | 327 | 113 |
| Conceptos | 1.112 | 954 | 6 |
| Boletines | 156 | 141 | 0 |

- Extensiones desde 2015: casi todo PDF; resoluciones: 2 `.zip`, 1 `.rar`,
  1 `.7z`; circulares: 1 `.msg`.
- `Created` coincide con el año de la columna Año en 2.752 de 2.898
  documentos (95%).
- ~500 resoluciones y ~140 circulares traen en la descripción una fecha en
  prosa ("Publicada en el Diario Oficial No. 53.638 con fecha 25 de
  septiembre de 2026").
- Nombres de archivo escritos a mano, con muchas variantes: `Resolución No.
  1809 de 2026`, `Resolucion No 276 de 2019`, `Resolución No.N de N`,
  `Resolución N del N`, `Resolución No. Nde N`; `Circular Externa No 031 de
  2026`, `Circular No. 47 de 2017`, `Circualr No. …`; `Concepto Jurídico
  201711601019341 de 2017`, `Concepto Jurídico 2026423001919502 ID 1976825`;
  `Boletín Jurídico No 5 Mayo 2016`, `Boletín Jurídico No. 002 de febrero
  2025`, `Boletin Juridico No 4 del 2015`.
- **Retraso de publicación** (documentos con fecha de publicación, 2023+):
  resoluciones mediana 2 días, 90% ≤ 33 días, máx 505; circulares mediana
  2, 90% ≤ 27, máx 213. ~40% se sube más de 3 días después.

## Diseño

### Estructura

- Módulo `core/scrapers/families/minsalud.py`, clase `ScrapMinSalud`
  (patrón de `supersalud.py`/`procuraduria.py`): una fuente, cuatro
  secciones.
- Registro en `core/scrapers/families/__init__.py` y `core/seed.py`
  (`family_key="minsalud"`, nombre **"Ministerio de Salud y Protección
  Social"**, descripción "Resoluciones, circulares, conceptos jurídicos y
  boletines jurídicos publicados por el Ministerio de Salud y Protección
  Social").
- Transporte: una sola consulta paginada a la API REST (`requests`,
  `User-Agent` de navegador, verificación TLS normal, `timeout` amplio porque
  el sitio a veces es lento).
- **Piso: 2015** (por el año del documento).
- `scheduled_min_lookback_days = 60` (decisión del usuario): la corrida
  diaria mira 60 días hacia atrás para atrapar lo que se sube tarde. Costo
  bajo: la lista completa llega en una sola consulta; solo se re-verifican
  (HEAD) los documentos ya guardados de esos 60 días.
- `doc_id_uses_publication_date = False`: la identidad es la URL del
  archivo (la fecha del documento puede reconstruirse distinto si el sitio
  completa la fecha de publicación más tarde).
- `checks_for_republication = True` (HEAD barato con `Content-Length`).
- **No** se agrega a `_MINISTERIO_FAMILIES` (esa lista solo sirve para
  deduplicar Leyes/Decretos, que estas secciones no traen).

### Secciones

| Sección (`seccion`) | Filtro del tipo (empieza por) | `tipo` del documento | Prefijo |
|---|---|---|---|
| Resoluciones | `Resolución` | `Resolución` | `R` |
| Circulares | `Circular` | `Circular` | `C` |
| Conceptos | `Concepto` | `Concepto` | `CTO` |
| Boletines | `Boletines` | `Boletín Jurídico` | `BOL` |

Solo entran archivos (`FSObjType == 0`).

### Año y fecha

- **Año del documento:** la columna `Año` (primeros 4 dígitos). Si está
  vacía, el último año de 4 dígitos (1990 hasta el año siguiente al actual, la misma tolerancia de Procuraduría) del nombre del
  archivo; si tampoco, el año de `Created`.
- **Fecha** (`f_public` = `f_providencia`), en cascada:
  1. `Publicación` (se toma la fecha en hora de Colombia: el sitio guarda
     `…T05:00:00Z` = medianoche en Bogotá).
  2. La primera fecha en prosa de la descripción o del título
     (`core/fecha_es.parse_fecha_providencia_es`), **si es del año del
     documento**.
  3. `Created` (hora de Colombia), **si es del año del documento**.
  4. Respaldo (+ aviso en el registro): si `Created` es del año siguiente al
     del documento (documento de fin de año que el Ministerio sube en enero),
     `AAAA-12-31` del año del documento, para que la corrida diaria de 60 días
     todavía lo alcance; en cualquier otro caso (`Created` de otro año, o
     ausente), `AAAA-01-01`.
- Piso y rango de la corrida se aplican sobre esa fecha.

### Nomenclatura

Convención de los ministerios: `{PREFIJO}_MSPS_{número}_{año}`.

- **Resoluciones y circulares:** número del nombre del archivo (sin la
  extensión); si no trae, del título. Se normaliza (NFC, minúsculas, sin
  acentos) y se prueban en orden:
  1. número (1–6 dígitos) seguido del año `(19|20)AA`, tolerando `de`/`del`
     y una fecha en prosa en medio: `(?<!\d)(\d{1,6})\s*(?:de|del)?\s*(?:\d{1,2}\s+de\s+\w+\s+del?\s+)?((?:19|20)\d{2})\b`
     ("No. 001133 de 2017", "Nro.00532 de 2017", "No 45 del 31 de dciiembre del 2019");
  2. número tras el marcador "No"/"Nº"/"N°" (con `.`/`_` opcional): `\bn(?:o|°|º)?[._]?\s*(\d{1,6})\b`
     ("Circular externa No. 0015", "No_9");
  3. número al inicio del nombre: `^\s*(\d{1,6})\b` ("3312 Establece requisitos…");
  4. último número del nombre: `(\d{1,6})\s*$` ("Circular Conjunta 036").
  El número se usa sin ceros a la izquierda y se rellena a 4 dígitos
  (`R_MSPS_1809_2026`, `C_MSPS_0031_2026`, `R_MSPS_13956_2016`). El año del
  título es siempre el del documento (columna Año), aunque el nombre del
  archivo diga otro. Verificado sobre los 1.805 documentos reales desde
  2015: solo 1 queda sin número. Todas las variantes de circular (externa,
  interna, conjunta, Comisión Nacional de Precios de Medicamentos) llevan
  `C`.
- **Conceptos:** `CTO_MSPS_{radicado}_{año}` — el radicado es el primer
  grupo de 12–17 dígitos del nombre del archivo o del título, tal cual
  (`CTO_MSPS_201711601019341_2017`, `CTO_MSPS_2026423001919502_2026`).
- **Boletines:** `BOL_MSPS_{MES}_{año}` (decisión del usuario, como
  Supersociedades). Mes (`ENE`…`DIC`): la palabra del mes en el nombre del
  archivo o el título; si no hay, el número del boletín si está entre 1 y 12
  ("No 4 del 2015" → `ABR`); si tampoco, el mes de la fecha del documento
  cuando ésta no es la de respaldo `AAAA-01-01`.
- **Sin número/radicado/mes reconocible:** `{PREFIJO}_MSPS_SN{ID}_{año}` +
  aviso (hoy 2 casos: "Alcance a la Circular Salud Vida" y un "Decreto No.
  1600 de 2022" clasificado como Concepto — se respeta la clasificación del
  sitio; los dos `Res.pdf` se resuelven por su título).
- **Títulos repetidos** (16 grupos, 32 documentos: duplicados subidos dos
  veces, series distintas con el mismo número —interna/externa/conjunta,
  CNPMDM—, versiones "con anexo técnico"): el de menor `ID` del sitio queda
  limpio y los siguientes llevan `_2`, `_3`… (mismo criterio que
  Procuraduría). Se calcula sobre **toda la lista** antes de filtrar por
  rango, así el título no depende del rango de la corrida.

### Campos de `RawDocModel`

| Campo | Valor |
|---|---|
| `title` | según Nomenclatura |
| `tipo` | según la tabla de Secciones |
| `seccion` | `Resoluciones` / `Circulares` / `Conceptos` / `Boletines` |
| `f_public` / `f_providencia` | fecha según la cascada |
| `detalle` | título del sitio — descripción (temática / subtema); en conceptos, además, la dependencia responsable |
| `link.url` | `https://www.minsalud.gov.co` + `FileRef` url-codificado |
| `save_path` | `storage_path(fuente, fecha, tipo, "{título}(extension)")` |

### Errores

- Falla de la API (HTTP, JSON inválido, sin `value`) → un "Error
  consultando la biblioteca de normativa: …" en el registro (se vuelve error
  visible de la corrida) y 0 documentos.
- Avisos (nunca con la palabra "Error"): fecha de respaldo, número no
  reconocido. Solo para documentos que la corrida conserva.

### Riesgos aceptados

- Los ~16 grupos de títulos repetidos incluyen duplicados reales (el mismo
  documento subido dos veces con otro nombre de archivo): entran como dos
  documentos (`X` y `X_2`); se detectan a simple vista.
- Documentos viejos sin fecha de publicación ni fecha en prosa quedan con la
  fecha de subida (95% del mismo año) o con `AAAA-01-01`; para años viejos
  conviene correr por año completo.

## Pruebas

- `tests/families/test_minsalud.py`, con respuestas de la API armadas con la
  forma real (`responses`):
  - reparto por sección con variantes de tipo (`Resolución `, `Resolución
    CRES`, `Circular CRES`, `Boletines Jurídicos`) y exclusión de otros
    tipos y carpetas;
  - todas las formas de número de resoluciones/circulares, radicado de
    conceptos, mes de boletines, y el respaldo `SN{ID}`;
  - cascada de fechas (publicación en UTC → hora Colombia, prosa del mismo
    año, `Created` del mismo año, 1 de enero);
  - sufijos `_2`/`_3` estables ante rangos distintos;
  - piso 2015, filtro de rango, paginación por `odata.nextLink`, error de la
    API.
- `tests/test_seed.py`: conteos fijos por la familia nueva.
- Validación real en desarrollo: un mes reciente y un año viejo (2017).

## Despliegue

Código nuevo + `core.seed` una vez en producción. Sin migración.
