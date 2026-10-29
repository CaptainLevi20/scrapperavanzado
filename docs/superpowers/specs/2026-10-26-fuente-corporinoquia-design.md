# Fuente Corporinoquia — diseño

**Fecha:** 2026-10-26
**Entidad:** Corporación Autónoma Regional de la Orinoquía (`corporinoquia`, sigla `CORPORINOQUIA`)
**Estado:** borrador con las decisiones del usuario (2026-10-26, ver "Decisiones") — pendiente de aprobación del administrador antes de implementar.
v1 sólo acuerdos; resoluciones pendientes hasta que el ScriptCase responda.

> El enlace que dio el usuario
> (`https://corporinoquia.gov.co/index.php/la-corporacion/normatividad.html`)
> **no es** un listado de actos: es un menú de Joomla con 16 subpáginas
> (leyes, decreto único, normatividad ambiental vigente, estatutos, POMCAS…),
> casi todas normas nacionales republicadas. Los actos propios de la entidad
> están en tres sitios distintos, de muy distinta calidad (ver abajo). El
> alcance "resoluciones y acuerdos desde 2025" es **una suposición** tomada de
> la CDMB; el usuario no lo ha confirmado para esta entidad.

## Dónde están los actos propios

| Qué | Dónde | Estado (2026-10-26) |
|---|---|---|
| **Resoluciones y autos** (todos los de la entidad) | Sistema "Consulta - actos_administrativos" en ScriptCase: `http://177.93.51.139:8082/html/consulta/grid_actos_administrativos/` (enlazado desde *Normatividad → Sistema de búsqueda* y desde *Decisiones que afectan al público*) | **No responde.** Tiempo de espera agotado en 8082, 80 y 443 en tres intentos desde la red de la oficina. Sólo se conoce por copias de archive.org (la última, 04-ago-2025). |
| **Acuerdos del Consejo Directivo** | `https://corporinoquia.gov.co/participacion-ciudadana/acuerdos-aprobados-por-el-consejo-directivo.html` — una página Joomla (SP Page Builder) con un acordeón por año; cada acuerdo es un enlace a **Google Drive** | Funciona. |
| **"Actos Administrativos Internos"** | `/la-corporacion/normatividad/actosadministrativosinternos.html` | Funciona, pero es una lista hecha a mano con **5 resoluciones administrativas** (2022-2025, sólo **una de 2025**: la 120.36.25-0443 del 06-may-2025). No es el registro de resoluciones. |

Otras cosas vistas y descartadas: *Normatividad interna* (reglamentos y una
circular interna de 2025 en Drive), normatividad ambiental vigente (leyes y
decretos nacionales en `/images/docsPdf/`), Athento (`corporinoquia.athento.com`,
ventanilla de PQRS y trámites, exige sesión). No hay sitemap (`/sitemap.xml`
da 404) ni API JSON.

## Objetivo

Familia de scraper nueva `corporinoquia`, desde **2025** (supuesto), con:

| Sección | Origen | tipo asignado | prefijo de título | v1 |
|---|---|---|---|---|
| Acuerdos | página Joomla de acuerdos → Google Drive | `Acuerdo` | `A` | **Sí** |
| Resoluciones | ScriptCase `grid_actos_administrativos` | `Resolución` | `R` | **Bloqueada** hasta que el sistema responda |
| Resoluciones internas (lista manual) | página Joomla "Actos Administrativos Internos" | `Resolución` | `R` | A decidir (pregunta 3) |

Cada documento entra como un `RawDocModel`. Familia **plana**: sin
actuaciones, sin anexos, sin `family_params`.

Propuesta: **v1 = sólo Acuerdos**, y Resoluciones como segunda entrega
cuando se pueda investigar el ScriptCase en vivo. Implementar hoy una
familia de resoluciones a ciegas (sólo con copias de archive.org) no es
aceptable: no se puede probar ni la descarga ni la paginación.

## Construcción del sitio

### Portal Joomla (`corporinoquia.gov.co`)

- Joomla + K2 + SP Page Builder, detrás de nginx. **HTTPS válido** (sin
  `verify=False`), con HSTS. Sin WAF ni captcha; responde a `requests` con un
  `User-Agent` de navegador. Cookie de sesión que no hace falta.
- HTML en UTF-8.

### Acuerdos

`GET /participacion-ciudadana/acuerdos-aprobados-por-el-consejo-directivo.html`
— una sola página (~140 KB), sin paginación. Un panel de acordeón por año
(`<span class="sppb-panel-title">2026</span>`) y, dentro, un bloque de texto
**editado a mano**:

```html
<p><a href="https://drive.google.com/file/d/1tfN3S21FfeRVzIT-fDhCftCKMTSAxKoR/view?usp=sharing" ...>ACUERDO 200.3-2-26-001 DEL 05 ENERO 2026 </a>""POR MEDIO DEL CUAL EL CONSEJO DIRECTIVO REGLAMENTA ..."" 29<em>/01/2026  14:50<br /><br />
<a href="https://drive.google.com/file/d/1IkoWMFYl8QtsrBUafbSZo-E0-vvTooc-/view?usp=sharing" ...>ACUERDO 200.3-2-26-002 DEL 20 FEBRERO 2026 </a>"POR MEDIO DEL CUAL ..." 20/02/2026  10:50<a href="https://drive.google.com/file/d/1m2sOnsj.../view?usp=sharing"><br /></a></em>
```

Variantes del texto del enlace vistas en 2025-2026 (todas deben parsearse):

- `ACUERDO 200.3-2-26-001 DEL 05 ENERO 2026`
- `ACUERDO No.200.3-2-26-003 DEL 17 ABRIL 2026`
- `ACUERDO No. 200.3.2.26.007 DE FECHA 27 DE JULIO DE 2026`
- `ACUERDO 200.3.2-25-006 DE 5 JUNIO 2025`
- `200.3.2-25-004 08 DE ABRIL 2025` (sin la palabra "ACUERDO")

| Dato | De dónde | Notas |
|---|---|---|
| enlace | `href` `drive.google.com/file/d/<ID>/view` → ID | Descarga: `https://drive.google.com/uc?export=download&id=<ID>` |
| número | texto del enlace: código `200.3-2-AA-NNN` con separadores `.` o `-` mezclados → `NNN` | Regex sobre `200\.3[.\-]2[.\-](\d{2})[.\-](\d{1,3})`. El `AA` del código se cruza con el año de la fecha. |
| fecha | texto del enlace: `DD [DE] MES [DE] AAAA` | `core.fecha_es.parse_fecha_providencia_es` **no** sirve (exige "de"); regex propia con los meses en español. |
| referencia | texto entre el enlace y la fecha-hora de publicación | Va a `detalle`. |
| fecha de publicación | `DD/MM/AAAA HH:MM` tras la referencia (a veces partido por `<em>`) | Sólo informativa; no siempre está. |

- Un enlace cuenta sólo si apunta a `drive.google.com/file/d/` **y** su texto
  trae el código `200.3…`. Así se ignoran los enlaces vacíos que deja el
  editor (`<a href="…"><br /></a>`).
- **Error del sitio:** ese enlace vacío del bloque 2026 apunta al mismo
  archivo de Drive que el **Acuerdo 200.3-2-25-002** (`1m2sOnsj…`). Con la
  regla anterior no se toma; y la dedup por ID de Drive lo cubre de todas
  formas.
- Los años 2024 y anteriores traen textos como `Acuerdo 001 de 23 de mayo de
  2024` o `ACUERDO 200.3-2-24-004` **sin fecha**; quedan bajo el piso. Si
  algún día se baja el piso, una fila sin fecha se descarta con aviso (no se
  inventa la fecha con el año del acordeón sin decidirlo antes).

### Google Drive como origen de archivos

- `GET https://drive.google.com/uc?export=download&id=<ID>` → `303` a
  `drive.usercontent.google.com/download?...` → `200` con
  `Content-Disposition: attachment; filename="200-3-2-26-001.pdf"`,
  `Content-Type: application/octet-stream`, `Content-Length` y
  `Last-Modified`. **Sin ETag.** El descargador sigue redirecciones y toma la
  extensión del `Content-Disposition`; no hace falta tocarlo.
- `HEAD` sobre la URL final responde `200` con `Content-Length` → el chequeo de
  republicación funciona (`checks_for_republication = True`, por defecto).
- **Riesgo conocido:** Drive responde con una página HTML de "no se pudo
  analizar en busca de virus" para archivos de más de ~100 MB, y con HTML de
  cuota excedida si un archivo se descarga mucho. El descargador ya rechaza
  una página HTML en lugar del archivo ("El servidor devolvió una página
  HTML…"), así que se vería como error de descarga, no como archivo basura.
  Los acuerdos medidos pesan 1-8 MB.
- Ninguna familia actual descarga de Google Drive; ésta sería la primera.

### Resoluciones (ScriptCase) — lo que se sabe, para la segunda entrega

Por copias de archive.org (2023-09 → 2025-08):

- Aplicación ScriptCase 8 (`grid_actos_administrativos`). Columnas:
  **Auto/Resolución**, **Número** (`20036200262`, `5006201503`), **Fecha
  Expedición**, **Descripción**, **Fecha Publicación**, **Archivo**.
  Mezcla autos y resoluciones; filtrable por la primera columna.
- 10 filas por página, navegación por AJAX (`nm_gp_submit_ajax("rec", …)`);
  tiene exportación CSV/XLS y búsqueda avanzada.
- Total: 12.631 (sep-2023), 2.018 (jul-2024, al parecer se recargó la base),
  5.777 (abr-2025), 5.991 (ago-2025) → unos **60 actos al mes**, autos
  incluidos.
- **El PDF está atado a la sesión:**
  `grid_actos_administrativos_doc.php?script_case_init=…&script_case_session=<PHPSESSID>&nm_cod_doc=documento_db&nm_nome_doc=<base64>`.
  Una URL así cambia en cada corrida (duplicaría todo en la segunda corrida)
  y el descargador del worker no conserva la sesión del scraper. Integrarlo
  casi seguro exige **un método de descarga nuevo** en `core/downloader.py`
  (abrir sesión y pedir el documento), es decir, tocar algo fuera de la
  familia — se debe aprobar aparte.
- Hoy no responde: no se sabe si se cayó, si se movió o si sólo acepta IP
  colombianas o de cierta red. **No se intenta rodear.**

## Número y nombre canónico

- Acuerdo → `A_CORPORINOQUIA_{numero:04d}_{anio}`. Ej.:
  `A_CORPORINOQUIA_0001_2026`, `A_CORPORINOQUIA_0017_2025`.
  - La numeración **es anual** (vuelve a `001` cada año); el año sale de la
    fecha del acuerdo. Si el `AA` del código no coincide con el año de la
    fecha, gana la fecha y se emite aviso.
- Sigla: `CORPORINOQUIA` es la que usa la propia entidad. Es larga; la
  alternativa era `CRO`, pero no la usa nadie. Confirmada `CORPORINOQUIA`.
- `title_unverified=False` cuando hay código y fecha; si el texto no trae el
  código `200.3…` pero sí fecha, el enlace se descarta con aviso (no hay
  acuerdos así en 2025-2026).

## Fechas

- `f_public` y `f_providencia` = fecha del acuerdo (la del texto del
  enlace). La hora de publicación que sigue a la referencia no siempre está
  y va en otro nodo de texto; no se usa.
- Retraso de publicación: el acuerdo 26-001 (05-ene) se publicó el 29-ene
  (24 días); los demás de 2026 se publicaron el mismo día o pocos días
  después. Se propone `scheduled_min_lookback_days = 60`. No cuesta
  peticiones: es una sola página.
- Fecha posterior a hoy → aviso `on_progress` (como en CDMB).

## Piso de año, rango y deduplicación

- `_ANIO_MINIMO = 2025`; el rango real lo dan `fini`/`ffin`.
- Clave de dedup dentro de la corrida: **ID de Drive**.

## `save_path` / almacenamiento

`storage_path(_SOURCE, fecha_iso, tipo, f"{title}(extension)")`.
`_SOURCE = "Corporación Autónoma Regional de la Orinoquía"` (mismo texto que el
`name` del seed).

## Volumen esperado

| | 2025 | 2026 (a 26-oct) |
|---|---|---|
| Acuerdos | 17 | 12 |
| Resoluciones (ScriptCase, si vuelve; autos aparte) | desconocido | desconocido |
| Resoluciones internas (lista manual) | 1 | 0 |

Corrida completa v1: 29 documentos, 1 GET de listado. Corrida diaria: 1 GET +
descargas nuevas (uno o dos al mes).

## Fuera de alcance (v1)

- **Resoluciones y autos del ScriptCase**: bloqueados (servidor sin respuesta
  y descarga atada a sesión). Segunda entrega.
- Normas nacionales republicadas en *Normatividad* (leyes, decretos,
  resoluciones de otras entidades).
- Circulares internas, reglamentos, estatutos, POMCAS.
- Años anteriores a 2025.

## Integración

**Archivos nuevos:**

- `core/scrapers/families/corporinoquia.py` — `@register_family("corporinoquia")`,
  `class ScrapCorporinoquia(BaseScrapper)`, `scheduled_min_lookback_days = 60`.
- `tests/families/test_corporinoquia.py`.

**Archivos que se tocan:**

- `core/scrapers/families/__init__.py` — añadir `corporinoquia` al import.
- `core/seed.py` — entrada en `_FAMILIES` y
  `create_source_if_missing(db, family_key="corporinoquia", name=_SOURCE, family_params={})`.
- `tests/test_seed.py` — **+1 familia y +1 fuente única** respecto de lo que
  haya en `master` al implementar. Con CDMB ya integrada son 32 familias y
  `1 + 28 + 29 + 33 + 6`; esta fuente lo lleva a 33 y `1 + 28 + 30 + 33 + 6`
  **sólo si** ninguna de las otras fuentes que se diseñan en paralelo
  (CC Armenia, CCB, Corantioquia) entró antes. Añadir `"corporinoquia"` al
  conjunto de claves y al comentario.
- `docs/guia-despliegue-sistemas.md` — ficha de la fuente (paso 7).

Sin migración Alembic. Sin cambios en el descargador para v1. En
producción: `python -m core.seed` una vez.

## Pruebas

`tests/families/test_corporinoquia.py`, con fragmentos reales del HTML de la
página de acuerdos y `responses`, sin internet:

1. Cada variante de texto del enlace (las cinco de arriba) → número y fecha
   correctos; `A_CORPORINOQUIA_0001_2026`, relleno a 4 dígitos.
2. URL de descarga armada desde el ID de Drive
   (`https://drive.google.com/uc?export=download&id=…`).
3. Enlace vacío (`<a href="…"><br /></a>`) ignorado, aunque su ID sea el de
   otro acuerdo.
4. Referencia recogida en `detalle` sin la fecha-hora de publicación.
5. Filtro por `fini`/`ffin` y piso 2025 (los acuerdos de 2024 no entran).
6. Año del código distinto del de la fecha → gana la fecha, aviso.
7. Enlace con código y sin fecha → descartado con aviso.
8. Fecha futura → fuera de rango y aviso.
9. Dedup por ID de Drive.
10. `stop_event` y `limit` respetados.
11. Falla de la página (500) → aviso y lista vacía, sin excepción.

Se corren dirigidas: `pytest tests/families/test_corporinoquia.py tests/test_seed.py`.

## Riesgos y notas

- **Página editada a mano.** Cada acuerdo nuevo lo pega una persona en un
  bloque de texto libre; el formato del texto ya cambió tres veces en dos
  años. Un formato nuevo se verá como avisos de "sin código"/"sin fecha" en
  la corrida, no como error. Las pruebas fijan las variantes conocidas.
- **Google Drive** puede devolver HTML (archivo grande, cuota, archivo
  privado o borrado) en lugar del PDF; el descargador lo reporta como error.
  Si la entidad cambia los permisos de un archivo, ese acuerdo dejará de
  bajar.
- **Volumen muy bajo** (uno o dos acuerdos al mes): la alerta "fuente que
  puede estar fallando" podría saltar en meses sin acuerdos. Evaluar
  `alerta_margen_dias` (p. ej. 60) en la implementación.
- **El grueso de lo que produce la entidad (resoluciones y autos) queda
  fuera** mientras el ScriptCase no responda. Hay que decírselo claro al
  usuario: v1 trae ~30 documentos, no cientos.

## Decisiones (2026-10-26)

1. **Alcance:** como en la CDMB — resoluciones y acuerdos, sin autos, desde
   2025.
2. **ScriptCase de resoluciones:** tampoco abre desde el navegador del
   usuario (y volvió a dar tiempo agotado el 26-oct-2026). Se
   entrega **v1 sólo con acuerdos**. Las resoluciones quedan como **trabajo
   pendiente** (segunda entrega): preguntar a la entidad por el sistema y,
   cuando responda, investigarlo en vivo; casi seguro exigirá un método de
   descarga nuevo en `core/downloader.py` (PDF atado a la sesión), que se
   aprueba aparte.
3. **"Actos Administrativos Internos":** se ignora hasta tener el ScriptCase.
4. **Sigla:** `CORPORINOQUIA`.

### Notas de verificación

- Prueba contra el sitio (26-oct-2026, `2023-01-01`→hoy): 29 acuerdos (17 de
  2025, 12 de 2026), sin avisos. Descarga por Drive verificada con el `Downloader`
  del proyecto (`application/pdf`, extensión `.pdf`) y el `HEAD` de
  republicación devuelve el tamaño: **no hace falta tocar el descargador**
  (el ID de Drive es estable entre corridas).
- `alerta_margen_dias` no se fija: `scheduled_min_lookback_days = 60` ya
  cumple ese papel (ver `core/scrapers/base.py`).
- Un enlace con código de un año bajo el piso y sin fecha (`ACUERDO
  200.3-2-24-004`) se descarta en silencio; sólo se avisa si el código es de
  2025 en adelante.
