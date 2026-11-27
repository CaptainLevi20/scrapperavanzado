# Fuente ADRES (rediseño v2) — diseño

**Fecha:** 2026-11-23
**Entidad:** Administradora de los Recursos del Sistema General de Seguridad Social en Salud (`adres`, sigla propuesta `ADRES`)
**Estado:** aprobado por el administrador el 2026-11-26. Las preguntas que
seguían abiertas toman la propuesta del diseño; la migración es la opción A.
Plan: `docs/superpowers/plans/2026-11-26-fuente-adres.md`.

> **La familia `adres` ya existe** (`core/scrapers/families/adres.py`, port
> de julio de 2026, sin diseño ni ficha en la guía de despliegue) **y hoy no
> trae nada.** Entre el 9 y el 12 de agosto de 2026 la ADRES cambió su sitio
> de SharePoint a Next.js + Payload CMS. El scraper actual busca tablas cuyo
> primer encabezado sea `Fecha` y enlaces `RefreshPageTo`, y ya no hay ninguno
> de los dos. Corrido en vivo el 2026-11-23 desde 2015: **0 documentos en
> 1,1 s y ningún aviso de error**. La corrida diaria no trae nada desde
> mediados de agosto y nada lo señaló.
>
> Este diseño reescribe la familia (misma clave, misma fuente en el seed) y
> la pone al día con la convención de la guía: títulos canónicos, piso,
> dedup y ficha.

## Objetivo

Reescribir `adres` con tres secciones, desde **2015** (la ADRES empezó en
2017, así que el piso no recorta nada):

| Sección | URL | Bloque | tipo | título |
|---|---|---|---|---|
| Resoluciones | `https://www.adres.gov.co/normativa/resoluciones` | `heading == "ADRES"` | `Resolución` | `R_ADRES_{número}_{año}` |
| Circulares | `https://www.adres.gov.co/normativa/circulares` | `heading == "ADRES"` | `Circular` | `C_ADRES_{número}_{año}` |
| Acuerdos | `https://www.adres.gov.co/normativa/acuerdos` | `heading == "ADRES"` | `Acuerdo` | `A_ADRES_{número}_{año}` |

Familia **plana**: sin actuaciones, sin anexos, sin `family_params`.

`/normativa/resoluciones` **no** es todo lo que expide la ADRES (en 2025 su
consecutivo iba por la 185.869): es una selección que la entidad publica,
~8-20 resoluciones al año. Ver pregunta 10 (normograma).

## Construcción del sitio

- **Next.js (App Router) + Payload CMS**, detrás de un **Azure Application
  Gateway** que bloquea el `User-Agent` `python-requests/*` (403). Con un UA
  de navegador pasa (el descargador del worker ya manda `Mozilla/5.0`).
  Sin desafío JS ni captcha. TLS válido.
- Las rutas viejas de SharePoint (`/_api/...`, `/normativa/Documents/...`,
  `/normativa/ResolucionesADRES/...`) devuelven la página 404 de Next **con
  estado 200** (soft-404, HTML).
- **Una sola petición por sección trae la lista completa.** La tabla visible
  muestra 30 filas y el resto se pagina en el navegador, pero la página
  trae todas las filas en el payload RSC de Next:

  ```html
  <script>self.__next_f.push([1,"…{\"label\":\"docList\",…{\"documents\":[{\"id\":\"6a58…\",\"date\":\"01/10/2026\",\"file\":{\"url\":\"/api/media/file/Resolucion_199531_de_2026.pdf\",\"filename\":\"Resolucion_199531_de_2026.pdf\",\"mimeType\":\"application/pdf\"},\"meta\":[{\"label\":\"Fecha\",\"value\":\"01/10/2026\"},{\"label\":\"Descripción\",\"value\":\"Por medio de la cual …\"}],\"name\":\"Resolucion_199531_de_2026 \",\"description\":\"Se adiciona a la Resolución 1012-2022 …\"}, …],\"heading\":\"ADRES\",\"collapsible\":\"closed\",…,\"pageSize\":30,…,\"sort\":\"date-desc\"}"])</script>
  ```

  Se concatenan los `self.__next_f.push([1,"…"])`, se decodifican y se lee
  cada `"documents":[…]` con `json.JSONDecoder.raw_decode`. Cada página tiene
  dos bloques `docList` (la clave es `"label":"docList"`, no `blockLabel`):
  **"ADRES"** (lo propio) y **"Ministerio de Salud"** (normas de MinSalud,
  que ya cubre la familia `minsalud`; se ignora).

  **Ojo con el orden:** el `"heading"` del bloque va **después** del arreglo
  `documents` (es la clave hermana que sigue al `]`), no antes. El nombre del
  bloque se lee justo donde termina el `raw_decode`. Si se buscara hacia atrás,
  se tomaría el `heading` del bloque anterior y "ADRES" y "Ministerio de Salud"
  quedarían cruzados (comprobado en la revisión del 2026-11-26: así se leen
  las 11 normas de MinSalud como si fueran de la ADRES).

| Dato | De dónde |
|---|---|
| enlace | `file.url` → `https://www.adres.gov.co/api/media/file/<archivo>` |
| número y año | `name` (el nombre del archivo sin extensión) |
| fecha | `meta` con `label == "Fecha"`, `DD/MM/AAAA` |
| epígrafe | `description`; si viene vacío, `meta` "Descripción" |

- **Otra vía, descartada por ahora (pregunta 1):** la API REST de Payload,
  `GET /api/pages?where[fullPath][equals]=/normativa/resoluciones`, da el
  mismo JSON sin tener que leer el RSC, y además `file.filesize` y
  `file.createdAt`. Es pública, pero `robots.txt` dice `Disallow: /api`.
  El RSC es un formato interno de Next.js y puede cambiar al actualizar el
  framework; el objeto `documents` es el mismo en las dos vías y el `doc_id`
  sale igual. **Ojo:** `robots.txt` no sirve para decidir entre las dos, porque
  los PDF también se bajan de `/api/media/file/…`, que está bajo el mismo
  `Disallow: /api`: con cualquiera de las dos vías la familia ya pide rutas
  `/api`. Lo que pesa es la fragilidad del RSC frente a la limpieza del JSON.

### Descarga

`GET /api/media/file/Resolucion_199531_de_2026.pdf` → `200`,
`Content-Type: application/pdf`, `Content-Length`, `ETag` de Azure Blob, sin
`Content-Disposition` ni `Last-Modified`.

- **`HEAD` responde 404** (JSON), aunque el `GET` da 200. La revisión de
  republicación (`check_remote_content_length`) recibe `None`, y el worker
  baja **entero** cada documento ya guardado que vuelva a salir en la
  ventana. Propuesta: **`checks_for_republication = False`** (pregunta 8).
- Formatos en alcance: 304 PDF + 1 ZIP con 3 PDF
  (`RESOLUCION-0082395-2024.zip`), que `verificacion_archivos` acepta.

## Fechas y filtro

- `meta.Fecha` es la fecha de **expedición**: coincide con la fecha de firma
  en los 5 PDF con texto que se revisaron. El campo `date` de arriba no se
  usa: en Resoluciones viene vacío casi siempre (lleno en 4 de 146) y en
  Acuerdos siempre, pero en Circulares viene lleno en las 161 filas
  (revisión del 2026-11-26). `meta.Fecha` es lo único que está en las tres.
- `f_public = f_providencia = Fecha`. Filtro: `fini <= Fecha <= ffin`.
- **Piso:** `_ANIO_MINIMO = 2015`.
- **Retraso de carga:** entre 0 y 28 días según `file.createdAt` (hay una
  resolución subida a la biblioteca el 23-11 que todavía no está en la
  página). **`scheduled_min_lookback_days = 45`**. No cuesta nada: cada
  corrida lee el listado completo con 3 peticiones.
- **Salud de fuentes:** la ADRES publica poco (7 resoluciones y 3
  circulares en 2025), así que es normal pasar meses sin nada nuevo. Se
  fija **`alerta_margen_dias`** tras la corrida real, con la pausa más larga
  entre documentos de los últimos años (misma regla que las demás fuentes de
  publicación esporádica), para que la alerta de "fuente que puede estar
  fallando" no salte por eso. **Fijado en 140 días** (corrida del
  2026-11-26: la pausa más larga desde 2022 fue de 133 días, del 26-03 al
  06-08-2025).
- Fecha ilegible (0 casos hoy) → fila descartada con aviso.

## Número y nombre canónico

El número sale del `name`, que es el nombre del archivo tal como lo subió la
ADRES, en formatos muy variados (`Resolucion_199531_de_2026`,
`Res.146756-2024`, `RESOLUCION No 0089666 de 2024`, `Resolucón número 388 de 2020`,
`ADRES - Resolución 41656 de 2019`, `Resolución 1659`, `1431`).

Regex sobre el texto sin tildes, en minúsculas (probada: 144 de 144
resoluciones, 161 de 161 circulares, 4 de 4 acuerdos):

```
Resoluciones: ^\s*(?:adres\s*-\s*)?(?:res(?:olu?ci?on)?\.?)?[\s_\-\.]*(?:(?:no|numero|npumero)\.?[\s_\-]*)?(\d+)(?:[\s_\-]*(?:de|del)?[\s_\-]*(\d{4})(?!\d))?
Circulares:   ^\s*(\d+)(?:[\s_\-]*(?:de)?[\s_\-]*(\d{4})(?!\d))?
Acuerdos:     ^\s*acuerdo[\s_]*(?:(?:no|numero)[\s_]*)?(\d+)(?:[\s_]*de[\s_]*(\d{4}))?
```

(Al programar se agregó `(?!\d)` justo después del grupo del número en las
tres: sin él, la circular `0000014_24_06_2024` se partía en número `000` y
año `0014`. Las regex ya **no** quitan los ceros: el grupo del número es `(\d+)` sin
`0*` delante. Vuelta a probar el 2026-11-26 con el listado vivo: siguen
cubriendo todas las filas propias.)

- Número **tal cual lo escribe la ADRES** en el `name`, sin quitar ni poner
  ceros (decisión del administrador, 2026-11-26): `Resolucion_0128021_de_2026`
  → `R_ADRES_0128021_2026`; `RESOLUCION_0000009_2026` → `R_ADRES_0000009_2026`;
  `Resolución número 007 de 2019` → `R_ADRES_007_2019`; circular `000008` →
  `C_ADRES_000008_{año}`. Desde 2024 los números de resolución son de 6-7
  cifras (consecutivo tipo radicado), mezclados con algunos de 3-4.
- Para **comparar** números (dedup, choque de títulos) se usa el valor
  numérico (`int`), no el texto: `02418` y `2418` son el mismo número. El
  título conserva el texto de la fila que se queda.
- **Año:** el del `name` si lo trae; si no (9 resoluciones, 150 de 161
  circulares, 1 acuerdo), el de `Fecha`.
- **Año del nombre distinto del de `Fecha`** (4 resoluciones:
  `0144 de 2021` con Fecha 15/02/2020, `2152 de 2020` con 10/03/2021,
  `2707 de 2020` con 29/05/2021, `701 de 2018` con 23/03/2021): todo indica
  que el error está en el **año** de `Fecha`. Para la 2707 el mismo bloque
  "ADRES" trae además una fila externa (vlex) de la "Resolución número 2707
  de 2020" con fecha **29/05/2020**: mismo día y mes, año del nombre. Regla:
  - título con el año del nombre;
  - `f_public = f_providencia` = **día y mes de `Fecha` + año del nombre**
    (`2707 de 2020` → `2020-05-29`), para que quede en la carpeta y el rango
    de fechas del año correcto; si esa combinación no es una fecha válida
    (29/02 en año no bisiesto), `<año del nombre>-01-01`;
  - se mantiene **`title_unverified=True`** y un aviso `on_progress` con la
    `Fecha` original y la corregida.
- `name` que no cumple la regex (0 casos hoy) → título con el texto saneado,
  `title_unverified=True` y aviso.
- `detalle` = `description` (es el correcto en el único caso en que no
  coincide con `meta.Descripción`: `Resolucion_169660-2026`).
- `save_path = storage_path(_SOURCE, fecha, tipo, f"{title}(extension)")`
  (reemplaza el `(filename)(extension)` de hoy, que ya estaba señalado en
  `docs/code-review-findings.md`).

## Casos raros del sitio

| Caso | Qué se hace |
|---|---|
| Enlaces a otros dominios en el bloque "ADRES" de Resoluciones (vlex.com.co → 2707/2020, xhygnusnews.com → 2067/2020) | Se descartan (sólo `www.adres.gov.co/api/media/file/`), como hoy. Las dos resoluciones tienen además su propia fila con PDF de la ADRES. |
| Acuerdos externos en el bloque "ADRES" de Acuerdos: acuerdos de la CRES 25, 29 y 30 de **2011** (enlaces a normograma.supersalud, icbf.gov.co y asociacionusuariossanitas.com) | Se descartan por dominio ajeno y además quedan bajo el piso de 2015. Son 3 de las 7 filas del bloque; las 4 restantes son los acuerdos propios. |
| Dos filas con la ruta vieja `/normativa/Documents/…` (1769/2024 y 137/2022) | El archivo existe con el mismo nombre en `/api/media/file/`. Se rehace la URL y se avisa (pregunta 6). |
| Duplicado 12758/2023: dos filas, mismo archivo (mismo sha1), fechas 29/08 y 01/09 | Dedup por (sección, valor numérico del número, año): se queda la **fecha más antigua** (la que dice el PDF) y se avisa. |
| Duplicado 2935/2020: dos filas, mismo archivo, misma fecha | Dedup y aviso. |
| Circulares internas (turnos, simulacros, tarjetas de acceso, "PARA: SERVIDORES PÚBLICOS DE LA ADRES") mezcladas con las externas | No se distinguen desde el listado; **se incluyen todas** (decisión del administrador, 2026-11-25). Hoy no chocan en (número, año). |
| `Resolucion_2682_de_2025`, un número de otra serie en un año donde el consecutivo va por 185.869 | Se deja tal cual. |

## Volumen esperado (archivos propios, por año de `Fecha`)

| Sección | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Resoluciones | 9 | 24 | 12 | 15 | 14 | 12 | 19 | 20 | 7 | 8 | 140 |
| Circulares | 10 | 16 | 20 | 56 | 11 | 20 | 12 | 10 | 3 | 3 | 161 |
| Acuerdos | 1 | 0 | 0 | 1 | 0 | 0 | 1 | 1 | 0 | 0 | 4 |

Resoluciones: 140 = 140 archivos propios + 2 rutas viejas rehechas − 2
duplicados. (El 2026-11-26 el listado ya traía 10 resoluciones de 2026, no
8: se sumaron `RESOLUCION_0204811_2026`, del 25-11, y
`Resolucion_0204744_2026`. El retraso de carga es el esperado.) Corrida completa: **~305 documentos, ~245 MB, 4-6 min**.
Corrida diaria: 3 peticiones (~3 s) y 0-2 documentos nuevos por semana.

## Fuera de alcance

- **Proyectos de acto administrativo** (31): borradores para comentarios,
  sin número ni fecha estructurada, en ZIP/DOCX/XLSX.
- **Acción popular** (6): avisos a la comunidad sin fecha, ZIP de hasta 75 MB.
- **Fallos de tutela** (8): notificaciones de tutelas con **nombres de
  personas naturales** en el nombre del archivo; no son normativa.
- Bloques "Ministerio de Salud" de las tres páginas: normas de MinSalud
  (los cubre `minsalud`).
- Las 13 páginas "Normativa" temáticas fuera de `/normativa` (giro directo,
  recobros, SIIECAT…).
- `normograma.adres.gov.co`: otro sitio, con la cadena TLS incompleta y que
  por HTTP se queda colgado. Puede ser mucho más completo (pregunta 10).

## Documentos ya guardados en producción (migración)

`doc_id = sha1(url + "_" + f_public)`; el título no entra.

- **La URL de todos los documentos cambió** con el sitio nuevo:
  `/normativa/ResolucionesADRES/<archivo>` y `/normativa/CircularesADRES/<archivo>`
  pasaron a `/api/media/file/<archivo>`. El nombre del archivo y la fecha se
  conservaron (comprobado en Wayback del 12-07-2026).
- Por eso la v2, sin más, **bajaría todo otra vez como documentos nuevos** y
  duplicaría lo que haya en producción (y daría choques de `storage_key` con
  sufijo `-v2`, como pasó con la CSJ).

Opciones (decide el administrador según lo que haya en producción):

| Opción | Qué hace | Pros | Contras |
|---|---|---|---|
| **A. Backfill de identidad y título** (modelo: `core/backfill_csj_ojeador.py` + `core/backfill_mincit_titulos.py`) | Para cada documento `adres`: lo busca en el listado nuevo por nombre de archivo y fecha y actualiza `doc_id`, `source_url`, `title`, `tipo`, `f_providencia`, `detalle`; `storage_sync` renombra el objeto en MinIO. `--simular` por defecto; no toca los que no encuentra. | Conserva marcas de revisión, historial y descargas masivas. No baja nada. | Un script único más, con pruebas. |
| B. Purgar y bajar de nuevo | Desactivar la fuente, `core/purge_inactive_source_documents.py`, reactivar y corrida completa. | Simple (305 docs, 245 MB). | Pierde marcas "útil" y referencias en reportes. |
| C. Nada | — | — | Todo queda duplicado. |

Consulta para decidir (la corre el administrador en producción):

```sql
SELECT count(*), min(f_public), max(f_public),
       count(*) FILTER (WHERE review_status <> 'pending')
FROM documents d JOIN sources s ON s.id = d.source_id
WHERE s.family_key = 'adres';
```

El v1 funcionó, como mucho, del 14-07 al ~10-08-2026: si sólo corrieron las
diarias habrá pocos documentos y B basta; si alguien marcó documentos,
conviene A.

## Integración

**Archivos que se tocan:**

- `core/scrapers/families/adres.py` — reescrito (misma clave `adres`, misma
  clase registrada, `_SOURCE` igual al `name` del seed).
- `tests/families/test_adres.py` — reescrito con fragmentos reales del RSC.
- `docs/guia-despliegue-sistemas.md` — ficha nueva (hoy no tiene).
- Si se elige la opción A: `core/backfill_adres_v2.py` + su prueba.

**No se tocan** `core/seed.py`, `tests/test_seed.py` ni
`families/__init__.py`: la familia y la fuente ya existen. Sin migración
Alembic.

## Pruebas

`tests/families/test_adres.py`, con `responses` y HTML/RSC real:

1. Lectura del RSC → lista de documentos por bloque (`"label":"docList"`);
   se ignora "Ministerio de Salud". **El `heading` se toma del que sigue al
   arreglo `documents`:** con un fragmento real de dos bloques seguidos
   ("ADRES" y luego "Ministerio de Salud"), las filas del primero quedan como
   "ADRES" y las del segundo como "Ministerio de Salud", no al revés.
2. `name` → título, con el número tal cual: `Resolucion_199531_de_2026` →
   `R_ADRES_199531_2026`; `Resolucion_0128021_de_2026` →
   `R_ADRES_0128021_2026`; `RESOLUCION_0000009_2026` →
   `R_ADRES_0000009_2026`; `Res.146756-2024` → `R_ADRES_146756_2024`;
   `Resolución 1659` + Fecha 2019 → `R_ADRES_1659_2019`; circular
   `0000004_2026` → `C_ADRES_0000004_2026`; circular `000008` + Fecha 2022 →
   `C_ADRES_000008_2022`; `Acuerdo_numero_497_de_2017` → `A_ADRES_497_2017`;
   `Acuerdo_numero_0000002_de_2020` → `A_ADRES_0000002_2020`.
3. Año del nombre ≠ año de Fecha (`Resolución número 2707 de 2020` con
   Fecha `29/05/2021`) → título `R_ADRES_2707_2020`, `f_public == "2020-05-29"`,
   `title_unverified=True` + aviso con las dos fechas; Fecha `29/02/AAAA`
   con año del nombre no bisiesto → `<año>-01-01`.
4. `name` fuera de patrón → título saneado, `title_unverified=True`, aviso.
5. Dominio ajeno descartado; ruta vieja `/normativa/Documents/x.pdf` →
   `/api/media/file/x.pdf` + aviso.
6. Dedup 12758/2023 → queda la fecha más antigua + aviso; dos filas con el
   mismo número escrito distinto (`02418` y `2418`) cuentan como duplicado.
7. Filtro por fecha y piso; `scheduled_min_lookback_days == 45`;
   `checks_for_republication is False`; `alerta_margen_dias` con el valor
   fijado tras la corrida real.
8. **Página sin ningún bloque "ADRES" o sin RSC → aviso "Error: …"** (para que
   un cambio de sitio como el de agosto no vuelva a pasar en silencio).
9. `stop_event`, `limit`, una sección que falla (aviso y sigue).
10. La sesión manda `User-Agent` de navegador.

## Preguntas para el usuario / administrador

1. **Transporte:** ¿HTML + RSC (más frágil, recomendado) o la API de Payload
   `/api/pages` (JSON limpio)? `robots.txt` (`Disallow: /api`) no distingue
   entre las dos: los PDF se bajan de `/api/media/file/` en ambos casos.
   **Se toma la propuesta (aprobación del 2026-11-26):** HTML + RSC.
2. **Alcance:** **Respondida (administrador, 2026-11-25):** Resoluciones, Circulares y Acuerdos.
   Los bloques de MinSalud **no** (se publican en MinSalud).
3. **Circulares internas:** **Respondida (administrador, 2026-11-25):** **se incluyen**. Hay contrato
   con la entidad, así que conviene tenerlas y revisarlas.
4. **Número:** ~~Respondida (administrador, 2026-11-25): sin ceros a la
   izquierda, relleno a 4 sólo si tiene menos de 4 cifras.~~ **Esa respuesta
   quedó reemplazada.** **Respondida por el administrador el 2026-11-26:** el
   número se copia **tal cual lo escribe la entidad**, sin quitar ni poner
   ceros, en las tres fuentes (ADRES, DPS y Función Pública):
   `R_ADRES_0128021_2026`, `R_ADRES_0000009_2026`, `C_ADRES_000008_2022`.
   El diseño ya está ajustado a esta regla.
5. **Sigla `ADRES`:** ¿se aprueba? **Se toma la propuesta (aprobación del
   2026-11-26):** `ADRES`.
6. **Rutas viejas** (2 resoluciones): ¿se rehacen como `/api/media/file/` o se
   omiten con aviso? (Comprobado el 2026-11-26: los dos archivos existen en
   `/api/media/file/` y bajan como PDF; rehacerlas funciona.) **Se toma la
   propuesta (aprobación del 2026-11-26):** se rehacen, con aviso.
7. **Duplicado 12758/2023:** ¿se queda la fila con la fecha más antigua?
   **Se toma la propuesta (aprobación del 2026-11-26):** sí.
8. **Republicación:** `HEAD` da 404. ¿`checks_for_republication = False`
   (propuesto) o se acepta bajar entero cada día lo que esté en la ventana?
   (Comprobado el 2026-11-26: `HEAD` → 404 JSON y `GET` → 200 PDF.) **Se toma
   la propuesta (aprobación del 2026-11-26):** `checks_for_republication = False`.
9. **Migración:** ¿cuántos documentos `adres` hay en producción y alguno está
   marcado? → opción A o B. **Respondida por el usuario el 2026-11-26:**
   opción A, `core/backfill_adres_v2.py` (simula por defecto; `--aplicar`).
10. **Normograma** (`normograma.adres.gov.co`): ¿se estudia como fuente
    aparte? **Se toma la propuesta (aprobación del 2026-11-26):** fuera de
    alcance de esta versión.

## Plan de implementación (cuando se apruebe)

1. Prueba + lector del RSC con HTML real (caso 1).
2. Prueba + `name` → título y casos raros (casos 2-6).
3. Prueba + `scrap()` con el sitio simulado (casos 7-10), reescribiendo
   `adres.py`.
4. Si es la opción A: backfill con `--simular`, sus pruebas y una pasada
   simulada contra una copia de la BD.
5. Corrida real local desde 2015 y segunda corrida sin descargas nuevas.
6. Ficha en `docs/guia-despliegue-sistemas.md`.
