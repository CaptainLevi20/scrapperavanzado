# Fuente Cámara de Comercio de Cali — diseño

**Fecha:** 2026-11-23
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
anexos, sin `family_params`. Piso propuesto **2015** (pregunta 3).

## Construcción del sitio

- **WordPress** (tema propio `ccc-template`) detrás de **Cloudflare**. Hoy
  Cloudflare **no** pone desafío: responde 200 tanto con `User-Agent` de
  navegador como con el de `python-requests`, sin cookies obligatorias (pone
  `PHPSESSID`, que no hace falta). TLS válido. Si un día aparece un desafío de
  JavaScript, se pausa la fuente (regla del paso 2 de la guía).
- **La API REST está cerrada**: `/wp-json/…` responde `403`. Se lee el HTML.
- **Índice:** la página de la URL del usuario trae los enlaces a cada año
  (`/laudos-1980-1996/`, `/laudos/laudos-1997/` … `/laudos-2025/`). Las rutas
  no son uniformes (unas con `/laudos/`, otras sin él; las viejas redirigen
  con 301), así que **las páginas de año se toman de los enlaces del índice**
  (`href` que contenga `laudos-AAAA`), no se arman a mano. Hoy no existe
  `laudos-2026` (404): cuando la Cámara la cree, aparecerá en el índice.
- **Página de año:** dentro de `<article>` hay **una** tabla
  `table.tabla3` con una fila por archivo:

  ```html
  <tr class="impar"><th>2</th><td>
    <a href="https://www.ccc.org.co/wp-content/uploads/2024/07/031.-06-03-24-LAUDO-ARBITRAL-OSWALDO-CEDEÑO-REYES-Vs-POLLOS-BUCANERO-S.A..pdf"
       target="_blank">031. 06-03-24 LAUDO ARBITRAL OSWALDO CEDEÑO REYES Vs POLLOS BUCANERO S.A.</a>
  </td></tr>
  ```

  Lo único que hay es **el texto del enlace** (partes, a veces número o
  fecha) y la URL del PDF. **No hay columnas** de radicado, fecha ni partes.
  El `<th>` es solo la posición en la tabla.
- Sin paginación: 1 petición al índice + 1 por año (12 desde 2015), ~0,8 s
  cada una.

### Descarga

- Los PDF están en `wp-content/uploads/AAAA/MM/…`: enlace directo, `GET`
  normal, `Content-Type: application/pdf`, `Content-Length` y `Last-Modified`.
- `HEAD` funciona (69/69 = 200, ninguno roto): la revisión de republicación
  por tamaño sirve (`checks_for_republication = True`, por defecto).
- `link = {"url": href, "method": "GET"}`. Algunas URL traen tildes y `Ñ` en
  el nombre (`…CEDEÑO…`); `requests` las codifica bien.
- Tamaño: 69 PDF desde 2015 suman **245 MB** (mediana ~2 MB, el mayor
  18,7 MB). La descarga es lenta (~15 min para todo en la prueba); la corrida
  diaria no baja nada si no hay laudos nuevos.

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

| Origen | Cuántos (de 69) | Ejemplos |
|---|---|---|
| Fecha en el texto del enlace / nombre del archivo | 12 | `03-02-2017`, `26.10.2017`, `ABR 13_ 2020`, `06-03-24`, `Laudo_12.03.2024`, `23.01.24`, `280624`, `12-de-diciembre-de-2018` |
| Solo el año de la página | 57 | `Ana Rosa Barrios Vs. Hospital Isaías Duarte Cancino E.S.E.` |
| (Texto del PDF, "Santiago de Cali, … de 20xx") | ~43 tienen texto; ~26 son escaneos sin texto | — |

Propuesta:

- `f_providencia` = fecha del nombre si la hay (formatos `dd-mm-aaaa`,
  `dd.mm.aaaa`, `dd-mm-aa`, `dd.mm.aa`, `ddmmaa`, `<mes> dd aaaa`,
  `dd de <mes> de aaaa`; meses con `core/fecha_es.py`); si no,
  **`<año de la página>-01-01`** (como ICBF). `f_public = f_providencia`.
- El **año** del documento es el de la página, salvo que el nombre traiga una
  fecha completa: en la página **2025** hay dos laudos con fecha de **2024**
  en el nombre (`0039.1 Laudo árbitral 31-05-2024`, `0057. Acta No.25 Laudo
  18-09-2024`) y en la de 2023 uno cuyo PDF dice 12-08-2022. Se propone que
  mande la fecha del nombre y se avise cuando no coincide con la página
  (pregunta 4). La del PDF no se usa (ver "Leer el PDF").
- Filtro `fini <= fecha <= ffin`; piso sobre el año del documento.
- Como la Cámara agrega laudos a años viejos y leer todo cuesta 13 peticiones,
  **`scheduled_min_lookback_days = 10_000`** (toda la tabla, como Armenia y
  Barranquilla). La deduplicación por enlace evita volver a bajar lo ya
  guardado.
- Publica muy poco (3-10 laudos al año, en tandas de meses): **`alerta_margen_dias = 365`**
  para que la alerta de "fuente que puede estar fallando" no salga siempre
  (pregunta 6).

## Número y nombre canónico

El radicado del Centro tiene la forma **`A-AAAAMMDD-NNNN`** (fecha de
radicación + consecutivo). Solo aparece en el nombre en 16 de 69 archivos
(los 15 de 2022-2023, `LaudoArbitral_Rad_A-20201223-0803`, y uno de 2024,
`045. Laudo Arbitral A-202210260876`).

- **Con radicado en el nombre** → `LA_CCC_{AAAAMMDDNNNN}_{año}`, p. ej.
  `LA_CCC_202012230803_2022`. Se aceptan `A-AAAAMMDD-NNNN` y
  `A-AAAAMMDDNNNN`; sin la `A` y sin guiones, solo dígitos, como el radicado
  de Bogotá.
- **Sin radicado pero con fecha completa** → `LA_CCC_{MMDD}_{año}`, como
  Barranquilla (`LA_CCC_0306_2024`).
- **Sin radicado ni fecha** (41 de 69) → título de respaldo: texto del enlace
  saneado (sin "Laudo arbitral", "Tribunal", sin puntos, ≤ 80 caracteres) +
  `_{año}`, y `title_unverified=True`. Ej.:
  `LA_CCC_Ana_Rosa_Barrios_Vs_Hospital_Isaias_Duarte_Cancino_ESE_2015`
  (pregunta 5).
- Los prefijos `031.`, `0061.`, `0097.1` de 2024-2025 **no son el radicado**:
  al comparar con el PDF, el `0061.` de 2024 es el radicado `A-20230324`. Y el
  `0061` aparece en 2024 y otra vez en 2025 con fechas distintas. Se dejan en
  el `detalle`, no en el título.
- `detalle` = texto del enlace (partes).
- Títulos repetidos dentro de una corrida (dos archivos con el mismo título,
  distinto enlace) → actuaciones como en Bogotá: el segundo con
  `_{AAAAMMDD}` si tienen fechas distintas; si no, `_2`, con aviso.
- `save_path = storage_path(_SOURCE, fecha, "Laudo arbitral", f"{title}(extension)")`.

### Leer el PDF (`resolve_unverified_document`) — opcional

En los 43 PDF con texto, la primera o segunda página trae casi siempre
`Santiago de Cali, <fecha>` y, desde 2018, el radicado (`Radicado No.
A-20170519`, `Rad. A-20220121`). Se podría corregir el título de los
`title_unverified` después de bajar el archivo. **No se propone para v1**: los
26 escaneos seguirían sin título, la fecha viene en palabras ("veintinueve
(29) de noviembre de dos mil diecinueve") o como plantilla vacía (`_____ (__)
de _____`), y la fecha no se puede cambiar después de calcular la identidad
del documento. Pregunta 7.

## Casos raros del sitio

| Caso | Qué se hace |
|---|---|
| Laudo y su "Aclaración, corrección y adición al laudo" en filas distintas (Instalaciones Hidráulicas vs Hotel Spiwak, 2015) | Dos documentos; el segundo es un acta. Mismo tipo; el título de respaldo los distingue por el texto. |
| Versiones con sufijo (`versión impresa`, `FIRMADO`, `(Ejecutoria)`, `Autenticado`, `VF`, `FINAL`) | Se quedan en el `detalle`; no se limpian. |
| Nombre genérico del archivo (`Laudo-Definitivo.pdf`, 2021) | El texto del enlace sí trae las partes: se usa el texto, nunca el nombre del archivo, para el respaldo. |
| Partes con iniciales (`JGGG Vs. MF`, `JFCJ Vs MGG`) | Tal cual. |
| PDF con fecha de plantilla en blanco (2017, Consorcio Suprema) | Sin efecto en v1 (no se lee el PDF). |
| Año de la página ≠ año del laudo (3 casos) | Manda la fecha del nombre si la hay; aviso. |
| Extensión doble `.doc.pdf` | El descargador usa el `Content-Type`. |
| `laudos-2026` no existe todavía | Se toma lo que liste el índice; año sin página → nada. |
| Mismo enlace en dos filas o dos años | Dedup por enlace, con aviso. Hoy 0 casos. |

## Volumen esperado (desde 2015)

| 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 10 | 8 | 7 | 6 | 5 | 5 | 3 | 7 | 8 | 7 | 3 | **69** |

69 PDF, 245 MB. Antes de 2015: 45 en 2011-2014 y páginas desde 1980.
Corrida diaria: 13 peticiones de listado (~10 s) y normalmente 0 PDF.

## Fuera de alcance (v1)

- Laudos anteriores a 2015 (pregunta 3).
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
directos y `GET` normal.

Atributos: `scheduled_min_lookback_days = 10_000`,
`alerta_margen_dias = 365`, `checks_for_republication = True` (por defecto).

Sin migración Alembic. En producción: `python -m core.seed` una vez.

## Pruebas

`tests/families/test_cc_cali.py`, con `responses` y HTML real del índice y de
dos páginas de año (2015 y 2024):

1. Índice → páginas de año desde los enlaces (`/laudos-2015/` y
   `/laudos/laudos-2022/`), sin armar URL; `1980-1996` ignorada por el piso.
2. Fila → enlace, texto, año de la página; solo filas de `table.tabla3`
   dentro de `<article>` (el PDF del RUT del pie de página no entra).
3. Fechas del nombre: cada formato de la tabla (`06-03-24`, `280624`,
   `ABR 13_ 2020`, `12-de-diciembre-de-2018`…); sin fecha →
   `<año>-01-01`; año del nombre ≠ página → manda el nombre + aviso.
4. Títulos: `LaudoArbitral_Rad_A-20201223-0803` →
   `LA_CCC_202012230803_2022`; `A-202210260876` →
   `LA_CCC_202210260876_2024`; solo fecha → `LA_CCC_0306_2024`; nada →
   respaldo con partes y `title_unverified=True`; `0061.` no se toma como
   número.
5. Título repetido → actuaciones / `_2` con aviso; enlace repetido → dedup.
6. Filtro por fecha y piso; `scheduled_min_lookback_days == 10_000`;
   `alerta_margen_dias == 365`.
7. `stop_event`, `limit`, una página de año que falla (aviso y sigue),
   índice sin años → aviso.

## Preguntas para el usuario / administrador

1. **Sigla:** **Respondida (administrador, 2026-11-25):** `CCC` (Cartagena pasa a `CCCAR`). El administrador
   también confirmó que la página publica laudos hasta 2025.
2. **Clave de familia:** ¿`cc_cali`?
3. **Piso:** ¿2015 (69 laudos) o más atrás (hay desde 1980; 45 más en
   2011-2014)?
4. **Año:** cuando el nombre trae una fecha de otro año que la página (3
   casos), ¿manda la fecha del nombre (propuesto) o la página?
5. **Títulos sin radicado** (53 de 69): ¿`MMDD` cuando hay fecha y partes
   como respaldo `title_unverified` (propuesto), o siempre las partes?
6. **Alerta de salud:** ¿`alerta_margen_dias = 365`?
7. **Leer el PDF** para sacar radicado y fecha (`resolve_unverified_document`):
   ¿v2, o se descarta?
8. **¿Se le pide a la Cámara** que ponga el radicado y la fecha en la tabla?

## Plan de implementación (cuando se apruebe)

1. Prueba + lector de fechas del nombre y armado del título (casos 3-5).
2. Prueba + lectura del índice y de las páginas de año con HTML real
   (casos 1-2).
3. Prueba + `scrap()` con el sitio simulado (casos 6-7).
4. Import en `families/__init__.py`, seed y `tests/test_seed.py`.
5. Corrida real local desde 2015 y segunda corrida sin descargas nuevas.
6. Ficha en `docs/guia-despliegue-sistemas.md`.
