# Fuente Cámara de Comercio de Cali — diseño

**Fecha:** 2026-11-23 (revisado 2026-11-26 con las decisiones del administrador)
**Entidad:** Cámara de Comercio de Cali — Centro de Conciliación, Arbitraje y
Amigable Composición (`cc_cali`, sigla `CCC`)
**Estado:** pendiente de aprobación del administrador. No se programa nada
hasta que se apruebe.

> **Sigla:** `CCC`, decidida por el administrador el 2026-11-25 (pregunta 1).
> Cartagena queda como `CCCAR`, así que no se confunden. `CC` (carta
> circular) es otro prefijo de tipo, no una sigla, y los títulos separan
> por `_`, así que `LA_CCC_…` no choca.

> La URL que dio el usuario
> (`/programas-y-servicios-empresariales/centro-de-conciliacion-arbitraje-y-amigable-composicion/arbitraje/laudos-arbitrales/`)
> es un **índice**: solo tiene botones a una página por año. Los laudos
> están en esas páginas (`/laudos-2015/`, `/laudos/laudos-2022/`, …).

## Objetivo

Familia de scraper nueva `cc_cali` con una sección:

| Sección | Origen | tipo asignado | prefijo de título |
|---|---|---|---|
| Laudos | Páginas anuales enlazadas desde el índice de laudos | `Laudo arbitral` | `LA` |

Cada PDF de la tabla entra como un `RawDocModel`. Familia **plana**: sin
actuaciones, sin anexos, sin `family_params`. **Sin piso de año:** entra todo
lo que publica el sitio, desde la página `1980-1996` (decisión del
administrador del 2026-11-26, pregunta 3).

## Construcción del sitio

- **WordPress** (tema propio `ccc-template`) detrás de **Cloudflare**. Hoy
  Cloudflare **no** pone desafío: responde 200 tanto con `User-Agent` de
  navegador como con el de `python-requests`, sin cookies obligatorias (pone
  `PHPSESSID`, que no hace falta). TLS válido. Si un día aparece un desafío de
  JavaScript, se pausa la fuente (regla del paso 2 de la guía).
- **La API REST está cerrada**: `/wp-json/…` responde `403`. Se lee el HTML.
- **Índice:** la página de la URL del usuario trae **30 enlaces** de año
  (`/laudos-1980-1996/`, `/laudos/laudos-1997/` … `/laudos-2025/`). Las rutas
  no son uniformes (unas con `/laudos/`, otras sin él; las viejas redirigen
  con 301), así que **las páginas de año se toman de los enlaces del índice**
  (`href` que contenga `laudos-AAAA` o `laudos-AAAA-AAAA`), no se arman a
  mano. Hoy no existe `laudos-2026` (404): cuando la Cámara la cree,
  aparecerá en el índice.
- **Página de año:** dentro de `<article>` hay **una** tabla
  `table.tabla3` con una fila por archivo (comprobado en las 30 páginas):

  ```html
  <tr class="impar"><th>2</th><td>
    <a href="https://www.ccc.org.co/wp-content/uploads/2024/07/031.-06-03-24-LAUDO-ARBITRAL-OSWALDO-CEDEÑO-REYES-Vs-POLLOS-BUCANERO-S.A..pdf"
       target="_blank">031. 06-03-24 LAUDO ARBITRAL OSWALDO CEDEÑO REYES Vs POLLOS BUCANERO S.A.</a>
  </td></tr>
  ```

  Lo único que hay es **el texto del enlace** (partes, a veces número o
  fecha) y la URL del PDF. **No hay columnas** de radicado, fecha ni partes.
  El `<th>` es solo la posición en la tabla.
- **La página `1980-1996`** agrupa 17 años en una sola tabla (10 laudos) y
  ninguno trae fecha ni año en el texto o el nombre del archivo. Ver
  "Fechas".
- Sin paginación: 1 petición al índice + 1 por página de año (30), ~0,8 s
  cada una.

### Descarga

- Los PDF están en `wp-content/uploads/AAAA/MM/…`: enlace directo, `GET`
  normal, `Content-Type: application/pdf`, `Content-Length` y `Last-Modified`.
- `HEAD` funciona (273/273 = 200, ninguno roto; comprobado el 2026-11-26): la
  revisión de republicación por tamaño sirve (`checks_for_republication =
  True`, por defecto).
- `link = {"url": href, "method": "GET"}`. Algunas URL traen tildes y `Ñ` en
  el nombre (`…CEDEÑO…`); `requests` las codifica bien (`HEAD` 200).
- Tamaño: **273 PDF, ≈ 560 MB** (69 desde 2015 suman 245 MB; los 204
  anteriores, 315 MB; el mayor 21,4 MB). La descarga es lenta (~15 min para
  los 69 desde 2015 en la prueba; la primera corrida completa, del orden de
  40-60 min); la corrida diaria no baja nada si no hay laudos nuevos.

### La carpeta `uploads/AAAA/MM` no es la fecha del laudo

Los archivos se suben en tandas, y la Cámara **agrega laudos a años viejos**:

| Subida | Qué se subió |
|---|---|
| 2022-02 | Casi todo 2015-2021 (re-subida en bloque) |
| 2024-07 | 2022, 2023 y 2024 |
| 2025-10 / 2026-01 | 2025 |
| **2026-08** | 13 laudos nuevos en las páginas de **2015, 2016, 2018, 2019 y 2021** |

Por eso la corrida diaria tiene que leer **todas** las páginas de año, no solo
la del año en curso.

## Fechas y filtro

No hay fecha en el listado. De dónde se puede sacar:

| Origen | Cuántos (de 273) | Ejemplos |
|---|---|---|
| Fecha en el texto del enlace **o** en el nombre del archivo | 12 (todos desde 2015) | `03-02-2017`, `26.10.2017`, `ABR 13_ 2020`, `06-03-24`, `Laudo_12.03.2024`, `23.01.24`, `280624`, `12-de-diciembre-de-2018` |
| Solo el año de la página | 251 | `Ana Rosa Barrios Vs. Hospital Isaías Duarte Cancino E.S.E.` |
| Ni siquiera el año (página `1980-1996`) | 10 | `Casa Inglesa Ltda. Vs. Armerad Betong Vagforbattingar` |
| (Texto del PDF, "Santiago de Cali, … de 20xx") | desde 2015: ~43 de 69 tienen texto; ~26 son escaneos | — |

**La fecha se busca en los dos lugares**, el texto del enlace y el nombre del
archivo: hay fechas que están solo en el nombre (`LAUDO-INSTALTUR-10-08-2015.pdf`,
`…Corema-vs-Mapfre-12-de-diciembre-de-2018-…`). Para el título de respaldo
(ver "Número") se usa solo el texto.

**Lector propio de fechas.** `core/fecha_es.py` (`parse_fecha_providencia_es`)
no sirve tal cual: probado el 2026-11-26, devuelve `None` para
`ABR 13_ 2020`, `12-de-diciembre-de-2018` y `03 02 2017`, y no entiende años
de dos cifras. La familia lleva su propio lector, con pruebas, para:

| Forma | Ejemplo | Nota |
|---|---|---|
| `dd-mm-aaaa`, `dd.mm.aaaa`, `dd mm aaaa` | `03 02 2017`, `26.10.2017`, `10-08-2015` | separador `-`, `.` o espacio |
| `dd-mm-aa`, `dd.mm.aa` | `06-03-24`, `23.01.24` | año de 2 cifras → `20aa` |
| `ddmmaa` (6 cifras) | `280624` | solo si es fecha válida |
| `<mes abreviado> dd aaaa` | `ABR 13_ 2020` | `ENE`…`DIC`, mes primero, `_` y espacios sueltos |
| `dd de <mes> de aaaa` con guiones o `_` | `12-de-diciembre-de-2018` | se pasan `-`/`_` a espacios y se usa `fecha_es` |

- Un año suelto **no** es fecha: `Acuavalle 2010 Vs. Acuavalle…` (página
  2014) trae `2010` como parte del nombre de una parte. Solo cuentan fechas
  completas (día, mes y año).
- Los prefijos de numeración (`031.`, `0061.`, `0097.1.`, `001.3`, `40.1.`)
  no se leen como fecha: el lector exige día ≤ 31, mes ≤ 12 y la forma
  completa de la tabla.

Propuesta:

- `f_providencia` = fecha del texto o del nombre si la hay; si no,
  **`<año de la página>-01-01`** (como ICBF). `f_public = f_providencia`.
- **Página `1980-1996`:** sin año propio. Se propone `1996-01-01` (el último
  año del rango: el laudo es de 1996 o antes) + aviso y
  `title_unverified=True` (pregunta 9).
- El **año** del documento es el de la página, salvo que el nombre traiga una
  fecha completa: en la página **2025** hay dos laudos con fecha de **2024**
  en el nombre (`0039.1 Laudo árbitral 31-05-2024`, `0057. Acta No.25 Laudo
  18-09-2024`) y en la de 2023 uno cuyo PDF dice 12-08-2022. Se propone que
  mande la fecha del nombre y se avise cuando no coincide con la página
  (pregunta 4). La del PDF no se usa (ver "Leer el PDF").
- Filtro `fini <= fecha <= ffin`. Sin piso.
- Como la Cámara agrega laudos a años viejos y leer todo cuesta 31
  peticiones, la corrida diaria lee toda la tabla:
  **`scheduled_min_lookback_days = 20_000`** (~55 años). Tiene que ser mayor
  que los días desde el laudo más viejo: con `10_000` (Armenia) la ventana
  llegaría solo a 1999 y dejaría fuera 1980-1998. Es el mismo valor en las
  cuatro cámaras nuevas. La deduplicación por enlace evita volver a bajar lo
  ya guardado.
- **Alerta de salud:** **no** se pone `alerta_margen_dias`. El aviso toma el
  mayor entre `scheduled_min_lookback_days` y `alerta_margen_dias`
  (`api/routers/sources.py`), así que con 20.000 días el margen no cambia
  nada. Lo que sí pasa (`core/salud_fuentes.py`): el aviso de "fuente que
  puede estar fallando" sale **cuando no hay ningún laudo con fecha de los
  últimos 12 meses**. Hoy el laudo más reciente con fecha es del
  2025-01-03 (`0061. Laudo árbitral 03.01.2025`), así que **el aviso va a
  salir desde la primera corrida**, como en Armenia, hasta que la Cámara
  publique laudos de 2026 (pregunta 6).

## Número y nombre canónico

El radicado del Centro tiene la forma **`A-AAAAMMDD-NNNN`** (fecha de
radicación + consecutivo). Solo aparece en el nombre en 16 de 273 archivos
(los 15 de 2022-2023, `LaudoArbitral_Rad_A-20201223-0803`, y uno de 2024,
`045. Laudo Arbitral A-202210260876`). Antes de 2015, ninguno.

- **Con radicado en el nombre** → `LA_CCC_{radicado tal cual}_{año}`. El
  número se copia **como lo escribe la Cámara**, sin quitarle la `A` ni los
  guiones y sin rellenar (decisión del administrador del 2026-11-26,
  pregunta 5): `LA_CCC_A-20201223-0803_2022`, `LA_CCC_A-202210260876_2024`.
- **Sin radicado pero con fecha completa** → `LA_CCC_{AAAAMMDD}_{año}`, la
  regla común de las cámaras sin radicado (decisión del administrador del
  2026-11-26): `LA_CCC_20240306_2024`.
- **Sin radicado ni fecha** (245 de 273) → título de respaldo: texto del
  enlace saneado (sin "Laudo arbitral", "Tribunal", sin puntos ni tildes,
  ≤ 80 caracteres) + `_{año}`, y `title_unverified=True`. Ej.:
  `LA_CCC_Ana_Rosa_Barrios_Vs_Hospital_Isaias_Duarte_Cancino_ESE_2015`
  (pregunta 5).
- Los prefijos `031.`, `0061.`, `0097.1` de 2024-2025 **no son el radicado**:
  al comparar con el PDF, el `0061.` de 2024 es el radicado `A-20230324`. Y el
  `0061` aparece en 2024 y otra vez en 2025 con fechas distintas. Se dejan en
  el `detalle`, no en el título.
- `detalle` = texto del enlace (partes).
- **Títulos repetidos dentro de una corrida** (dos archivos con el mismo
  título, distinto enlace) → el primero queda sin sufijo y los siguientes
  llevan `_2`, `_3`… **con aviso**, igual que Barranquilla y Cartagena. **No**
  se usan actuaciones: agruparlas exigiría registrar la familia fuera de ella
  (`core/naming.py`, `core/db/repository.py` y un patrón en `core/utils.py`,
  como `ccb`). El orden para el sufijo es el de la ruta del archivo
  (`uploads/AAAA/MM/nombre`): un archivo nuevo siempre cae en una carpeta de
  subida más reciente, así que no le cambia el sufijo a uno ya guardado.
  Hoy pasa en 5 grupos, porque el corte a 80 caracteres se come la parte que
  los distingue: el laudo y su "Aclaración" de Hotel Spiwak (2015), Limor
  (2013), Servimed (2010 y 2013) y Burbado (2012, dos filas con el mismo
  texto).
- `save_path = storage_path(_SOURCE, fecha, "Laudo arbitral", f"{title}(extension)")`.

### Leer el PDF (`resolve_unverified_document`) — opcional

En los 43 PDF con texto desde 2015, la primera o segunda página trae casi
siempre `Santiago de Cali, <fecha>` y, desde 2018, el radicado (`Radicado No.
A-20170519`, `Rad. A-20220121`). Se podría corregir el título de los
`title_unverified` después de bajar el archivo. **No se propone para v1**: los
escaneos seguirían sin título, la fecha viene en palabras ("veintinueve
(29) de noviembre de dos mil diecinueve") o como plantilla vacía (`_____ (__)
de _____`), y la fecha no se puede cambiar después de calcular la identidad
del documento. Sin piso, 245 de 273 títulos quedan como respaldo y
`title_unverified` **para siempre** en v1 (no hay nada que los corrija):
esto pesa a favor de una v2 (pregunta 7). Los 204 anteriores a 2015 no se
revisaron por dentro.

## Casos raros del sitio

| Caso | Qué se hace |
|---|---|
| Laudo y su "Aclaración, corrección y adición al laudo" en filas distintas (Instalaciones Hidráulicas vs Hotel Spiwak, 2015) | Dos documentos; el segundo es un acta. Mismo tipo. El corte a 80 caracteres deja el mismo título de respaldo: el segundo lleva `_2` y aviso. |
| Aclaraciones, salvamentos de voto, adiciones, "laudo complementario" en filas aparte (muchas antes de 2015) | Un documento cada uno, mismo tipo; `detalle` = texto de la fila. |
| `Demanda arbitral contra la sociedad QUATRO MTJ S.A.S` (página 2014) | Es una **demanda**, no un laudo. Entra igual (todo lo de la tabla), con tipo `Laudo arbitral`; pregunta 10. |
| Versiones con sufijo (`versión impresa`, `FIRMADO`, `(Ejecutoria)`, `Autenticado`, `VF`, `FINAL`) | Se quedan en el `detalle`; no se limpian. |
| Nombre genérico del archivo (`Laudo-Definitivo.pdf`, 2021; `LA65DE1.pdf`, `BE841AE7.pdf`, 2014) | El texto del enlace sí trae las partes: se usa el texto, nunca el nombre del archivo, para el respaldo. |
| Partes con iniciales (`JGGG Vs. MF`, `JFCJ Vs MGG`) | Tal cual. |
| Año suelto en el nombre de una parte (`Acuavalle 2010`) | No es fecha (ver "Fechas"). |
| PDF con fecha de plantilla en blanco (2017, Consorcio Suprema) | Sin efecto en v1 (no se lee el PDF). |
| Año de la página ≠ año del laudo (3 casos) | Manda la fecha del nombre si la hay; aviso. |
| Página `1980-1996` sin año por laudo | `1996-01-01`, aviso y `title_unverified` (pregunta 9). |
| Extensión doble `.doc.pdf` | El descargador usa el `Content-Type`. |
| `laudos-2026` no existe todavía | Se toma lo que liste el índice; año sin página → nada. |
| Mismo enlace en dos filas o dos años | Dedup por enlace, con aviso. Hoy 0 casos (273 enlaces distintos). |

## Volumen esperado (todo el sitio)

| 1980-1996 | 1997 | 1998 | 1999 | 2000 | 2001 | 2002 | 2003 | 2004 | 2005 | 2006 | 2007 | 2008 | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 10 | 1 | 2 | 8 | 6 | 12 | 7 | 7 | 15 | 9 | 6 | 15 | 15 | 21 | 25 | 9 | 10 | 13 | 13 |

| 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 10 | 8 | 7 | 6 | 5 | 5 | 3 | 7 | 8 | 7 | 3 | **273** |

(por página; contado el 2026-11-26: 204 antes de 2015 + 69 desde 2015). 273
PDF, ≈ 560 MB. Corrida diaria: 31 peticiones de listado (~25 s) y
normalmente 0 PDF.

## Fuera de alcance (v1)

- Leer el PDF para corregir título y fecha (pregunta 7).
- Conciliación, amigable composición, insolvencia y demás servicios del
  Centro (no publican decisiones).

## Integración

**Archivos nuevos:** `core/scrapers/families/cc_cali.py`
(`@register_family("cc_cali")`), `tests/families/test_cc_cali.py`.

**Archivos que se tocan:** `core/scrapers/families/__init__.py`,
`core/seed.py` (`_SOURCE = "Cámara de Comercio de Cali"`,
`family_params={}`), `tests/test_seed.py` (conteos), ficha en
`docs/guia-despliegue-sistemas.md`. **Nada fuera de la familia**: enlaces
directos, `GET` normal y sin actuaciones.

Atributos: `scheduled_min_lookback_days = 20_000`,
`checks_for_republication = True` (por defecto), sin `alerta_margen_dias`.

Sin migración Alembic. En producción: `python -m core.seed` una vez.

## Pruebas

`tests/families/test_cc_cali.py`, con `responses` y HTML real del índice y de
tres páginas de año (`1980-1996`, 2015 y 2024):

1. Índice → páginas de año desde los enlaces (`/laudos-2015/`,
   `/laudos/laudos-2022/` y `/laudos-1980-1996/`), sin armar URL.
2. Fila → enlace, texto, año de la página; solo filas de `table.tabla3`
   dentro de `<article>` (el PDF del RUT del pie de página no entra).
3. Lector de fechas propio, cada forma de la tabla: `06-03-24`, `23.01.24`,
   `280624`, `03 02 2017`, `26.10.2017`, `ABR 13_ 2020`,
   `12-de-diciembre-de-2018`; fecha solo en el nombre del archivo
   (`LAUDO-INSTALTUR-10-08-2015.pdf`) → se toma; `Acuavalle 2010`,
   `0097.1.`, `001.3`, `40.1.` → sin fecha; sin fecha → `<año>-01-01`;
   página `1980-1996` → `1996-01-01` + aviso; año del nombre ≠ página →
   manda el nombre + aviso.
4. Títulos: `LaudoArbitral_Rad_A-20201223-0803` →
   `LA_CCC_A-20201223-0803_2022`; `A-202210260876` →
   `LA_CCC_A-202210260876_2024` (tal cual, sin quitar `A` ni guiones); solo
   fecha → `LA_CCC_20240306_2024`; nada → respaldo con partes y
   `title_unverified=True`; `0061.` no se toma como número.
5. Título repetido (Spiwak 2015, laudo y aclaración) → el de la ruta de
   subida más vieja sin sufijo, el otro `_2` con aviso, sea cual sea el orden
   de las filas; enlace repetido → dedup.
6. Filtro por fecha, sin piso (entra 1980-1996);
   `scheduled_min_lookback_days == 20_000`; sin `alerta_margen_dias`.
7. `stop_event`, `limit`, una página de año que falla (aviso y sigue),
   índice sin años → aviso.

## Preguntas para el usuario / administrador

1. **Sigla:** **Respondida (administrador, 2026-11-25):** `CCC` (Cartagena
   pasa a `CCCAR`). El administrador también confirmó que la página publica
   laudos hasta 2025.
2. **Clave de familia:** ¿`cc_cali`? (sigue abierta; no choca con ninguna
   clave existente).
3. **Piso:** **Respondida por el administrador el 2026-11-26:** sin piso,
   todo lo que publica el sitio, desde la página `1980-1996` (273 laudos).
4. **Año:** cuando el nombre trae una fecha de otro año que la página (3
   casos), ¿manda la fecha del nombre (propuesto) o la página? (sigue
   abierta).
5. **Títulos:** **Respondida por el administrador el 2026-11-26:** el
   radicado se copia tal cual lo escribe la Cámara
   (`LA_CCC_A-20201223-0803_2022`); sin radicado y con fecha, fecha completa
   `LA_CCC_{AAAAMMDD}_{año}`. Sigue abierto si los que no tienen ni radicado
   ni fecha (245) van con el respaldo de partes y `title_unverified`
   (propuesto) o de otra forma.
6. **Alerta de salud:** `alerta_margen_dias` no tiene efecto con
   `scheduled_min_lookback_days = 20_000`; el aviso va a salir desde el
   principio porque no hay laudos con fecha de los últimos 12 meses. ¿Se
   acepta, como en Armenia? (sigue abierta, propuesta: sí).
7. **Leer el PDF** para sacar radicado y fecha (`resolve_unverified_document`):
   ¿v2, o se descarta? Sin piso pesa más: 245 de 273 quedan sin verificar.
   (sigue abierta).
8. **¿Se le pide a la Cámara** que ponga el radicado y la fecha en la tabla?
   (sigue abierta).
9. **Página `1980-1996`** (10 laudos sin año propio): ¿`1996-01-01` con
   aviso y `title_unverified` (propuesto), o `1980-01-01`? (nueva).
10. **La "Demanda arbitral contra QUATRO MTJ"** (página 2014) no es un
    laudo: ¿entra como `Laudo arbitral` igual (propuesto: todo lo de la
    tabla) o se omite con aviso? (nueva).

## Plan de implementación (cuando se apruebe)

1. Prueba + lector de fechas propio y armado del título (casos 3-5).
2. Prueba + lectura del índice y de las páginas de año con HTML real
   (casos 1-2).
3. Prueba + `scrap()` con el sitio simulado (casos 6-7).
4. Import en `families/__init__.py`, seed y `tests/test_seed.py`.
5. Corrida real local completa (desde 1980) y segunda corrida sin descargas
   nuevas.
6. Ficha en `docs/guia-despliegue-sistemas.md`.
