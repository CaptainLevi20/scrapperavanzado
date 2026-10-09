# Fuente Supervigilancia — diseño

**Fecha:** 2026-09-10
**Entidad:** Superintendencia de Vigilancia y Seguridad Privada (`supervigilancia`, sigla `SVySP`)
**Estado:** aprobado para plan

> El enlace `/circulares` que dio el usuario es una caja de búsqueda vacía (stub
> del tema GOV.CO), no un listado. El listado real de circulares es
> `/2-1-3-3-circulares` y sólo tiene 9 documentos; las ~90 circulares históricas
> son páginas Odoo sueltas alcanzables sólo por sitemap. **Circulares queda
> fuera de v1** (ver "Fuera de alcance").

## Objetivo

Familia de scraper nueva `supervigilancia` que trae dos secciones de normativa de
`www.supervigilancia.gov.co`:

| Sección | URL de listado | tipo asignado | prefijo de título |
|---|---|---|---|
| Resoluciones | `/2-1-3-2-resoluciones` + `-pagina02`, `-pagina03`, … | `Resolución` | `R` |
| Conceptos jurídicos | `/2-1-3-8-conceptos-juridicos` (una sola página) | `Concepto` | `CTO` |

`R_` sigue la convención de `supersalud`/`ssf` para resoluciones; `CTO_` la de
`ssf`/`supersolidaria`/`superfinanciera` para conceptos (`CTO_SSF_`, `CTO_SES_`,
`CTO_SF_`).

Cada documento (PDF) entra como un `RawDocModel`. Familia **plana**: sin
actuaciones, sin anexos, sin `family_params`, sin `auto_review_status`.

## Construcción del sitio

- **Odoo** (Odoo.sh), `www.supervigilancia.gov.co`. Plataforma nueva para el
  proyecto — las 28 fuentes actuales son Joomla/Drupal/Liferay/WordPress/
  SharePoint/ASP.NET.
- **TLS válido** → **sin `verify=False`**. Sin WAF, sin challenge JS, sin cookies
  de sesión, sin form-digest. Es el transporte más simple de las familias
  recientes: `requests` + BeautifulSoup, molde estándar (como `ssf`/`snr`).
- **Cabecera de idioma obligatoria:** `Accept-Language: es-CO,es;q=0.9` en cada
  petición (fijada en `session.headers`). Sin ella, Odoo redirige a `/en/…` y las
  páginas de paginación en inglés vienen **sin contenido** (`div.s_dl_item` = 0);
  el contenido no está traducido al mirror inglés. Con ella, la respuesta se
  queda en español y trae los documentos. Es el equivalente aquí a lo que
  `verify=False` fue para `ssf`: un ajuste de transporte de una línea sin el cual
  la fuente rinde casi cero. (Un cookie `frontend_lang=es_CO` produce el mismo
  efecto; se usa la cabecera por ser más simple.)
- Los PDF se descargan con GET directo a
  `https://www.supervigilancia.gov.co/web/content/{id}?download=true` →
  `application/pdf` con `Content-Disposition: attachment; filename="…"`.
- **Una petición `HEAD` por documento durante el rastreo.** El número real de la
  resolución **no está** ni en la fila del listado (de forma fiable) ni en el
  texto del PDF (la primera página es un bloque de firmas; algunos PDF ni
  siquiera tienen texto extraíble) — pero **sí está en el nombre de archivo del
  `Content-Disposition`**, y `HEAD` sobre `/web/content/{id}?download=true` lo
  devuelve sin bajar el cuerpo, junto con `Content-Length`. Son ~110 HEAD por
  corrida completa (volumen minúsculo). Por eso esta familia **no** implementa
  `resolve_unverified_document` (ese enganche recibe el archivo ya descargado, no
  las cabeceras HTTP, y aquí el número no está en el contenido).

### Marcado de un documento

Cada documento del listado es un bloque:

```html
<div class="s_dl_item p-3 mb-3 rounded-3"
     data-category="acuerdos" data-format="pdf"
     data-href="/web/content/10260?download=true" data-name="Documento">
  <div class="s_dl_item_icon_col">
    <span class="s_dl_file_size">394 Kb</span>
  </div>
  <div class="s_dl_info">
    <div class="s_dl_doc_type">resoluciones</div>
    <div class="s_dl_doc_name">
      20263200005647CS
      <b>Por la cual se actualiza y se adopta el Manual de Políticas Contables…</b>
    </div>
    <div class="s_dl_doc_meta"><span>Publicación: 08/05/2026</span></div>
  </div>
  <a class="s_dl_btn_download" href="/web/content/10260?download=true"><i class="fa fa-download"></i></a>
</div>
```

Selector de fila: `div.s_dl_item`. Campos:

| Dato | De dónde | Notas |
|---|---|---|
| id / enlace | `data-href` (o `href` del `a.s_dl_btn_download`) → `/web/content/{id}?download=true` | `{id}` numérico = clave de dedup primaria dentro de la corrida |
| título | texto de `.s_dl_doc_name` | NFC + borrar `​` (espacios de ancho cero, presentes en varios títulos) + colapsar espacios; si termina en `.pdf`, quitar extensión |
| fecha | texto de `.s_dl_doc_meta` | primer `DD/MM/AAAA`, venga con "Expedición:", "Publicación:", "|Expedición:" (sin espacio) o suelta |
| nombre de archivo real | `Content-Disposition` de la respuesta `HEAD` a `/web/content/{id}?download=true` | fuente primaria del número (ver abajo); su longitud + `Content-Length` son la clave de dedup secundaria |
| tipo | **la página de origen**, no el HTML | ver abajo |

El campo `.s_dl_file_size` (`"394 Kb"`) del listado se ignora — es aproximado
(redondeado a Kb/Mb); para deduplicar se usa el `Content-Length` exacto del HEAD.

**Campos que se ignoran por completo:** `data-category` (`"acuerdos"`,
`"ordenanzas"`, `"decretos"`, `"circulares"` al azar) y `.s_dl_doc_type`
(`"resoluciones"`, `"circular"`, `"CIRCULAR"` inconsistente). Son ruido de
plantilla del snippet Odoo. En la página de resoluciones hay filas con
`data-category="circulares"`; se clasifican igual como `Resolución`.

## Paginación (Resoluciones)

- La página 1 (`/2-1-3-2-resoluciones`) es una **selección destacada** con ~46
  bloques que **repite** documentos que también aparecen en las páginas 2+.
- Las páginas siguientes son `-pagina02`, `-pagina03`, … (sufijo de dos dígitos,
  con cero a la izquierda). ~9-11 bloques cada una.
- **Criterio de parada:** iterar incrementando el número hasta que una página
  devuelva **0 bloques `div.s_dl_item`**. Tope duro de seguridad en `-pagina20`.
- No se usa el enlace "Siguiente página" del sitio (en la página 1 apunta a una
  sección no relacionada) ni el conteo de páginas del `sitemap.xml` (lista hasta
  `-pagina14` pero la 12 ya viene vacía).
- Estado observado 2026-09-10: 11 páginas con contenido, **145 filas** en total,
  ~90-110 tras aplicar el piso 2015.

Conceptos: una sola petición, sin paginación. 17 filas hoy, 2008–2020, con
duplicados evidentes (mismos PDF, IDs de `/web/content` casi consecutivos).

## Número y nombre canónico

El número de resolución es **inconsistente** en el listado: sólo ~36/145 filas
traen un token `\d{6,}CS` al inicio del título; ~38/145 no traen ningún número;
el resto lo llevan incrustado en prosa (`"…RESOLUCIÓN No. 20221300053467…"`,
`"Resolucion 20253200007657 lineamientos…"`, `"Resolución 2328 de 2008"`). Pero
el **nombre de archivo del `Content-Disposition`** (vía HEAD) casi siempre lo
trae limpio: `"20261000015947CS RESOLUCION…pdf"`, `"RESOLUCION No.
202540000099737CS - TRAMITES (2).pdf"`, `20263100016027CS.pdf`.

**Extracción del número — primero que acierte gana:**

1. `\d{6,}CS` en el nombre de archivo del `Content-Disposition` de la respuesta
   HEAD (búsqueda en cualquier posición, no anclada; mayúsculas). ← fuente
   primaria.
2. Token `^\s*(\d{6,}CS)\b` al inicio del texto de `.s_dl_doc_name` del listado
   (respaldo si el HEAD falló por red).
3. Prosa en el `.s_dl_doc_name`: `Resoluci[oó]n\s+(?:N[o°º]\.?\s*)?(\d{4,})`.
4. Sin número → el documento **igual se guarda** con título descriptivo.

**Construcción del `title`** (lo que `construir_nombre` usa como `base`).
`{pref}` = `R` para resoluciones, `CTO` para conceptos:

- Con número → `f"{pref}_SVySP_{numero}_{anio}"`, `title_unverified=False`.
  Ej.: `R_SVySP_20263200005647CS_2026`. El número se guarda **literal**: sin
  relleno de ceros, sin normalizar, con el sufijo `CS`, en mayúsculas — los
  números modernos ya son largos y únicos (mismo criterio que `snr` y que los
  conceptos de `ssf`).
- Sin número → título crudo recortado a 120 caracteres (el del listado, o el
  `stem` del nombre de archivo del HEAD si el del listado quedó vacío),
  `title_unverified=True`.

**Sin `resolve_unverified_document`.** El número no aparece en el texto del PDF
(verificado: primera página = bloque de firmas; algunos PDF sin texto), así que
no hay nada que recuperar del archivo descargado. El `title_unverified=True`
queda sólo como marca informativa de "título no canónico"; el worker intentará el
enganche y no hará nada (implementación por defecto de `BaseScrapper`).

**Conceptos:** casi ninguna fila trae número ni en el listado ni en el
`Content-Disposition` (nombres como `"Renting operativo.pdf"`). Casi todos entran
con `title_unverified=True` y título descriptivo. Si el `Content-Disposition`
trae un `\d{6,}CS`, se produce `CTO_SVySP_{numero}_{anio}`.

## Fechas

Texto de `.s_dl_doc_meta`. Se toma el primer `DD/MM/AAAA`. Casos especiales:

- Sin `DD/MM/AAAA` pero con la fecha en palabras (`"27 de julio de 2020"`,
  típico de las filas 2018-2022) → se lee con `core/fecha_es.py`. *(Añadido
  2026-10-09: sin esto se descartaban 26 resoluciones reales.)*
- `"Hoy"` → fecha de la corrida.
- `"--"`, vacío, o sin ninguna fecha legible → **se descarta el documento** con un aviso
  vía `on_progress` (no se aproximan fechas; el `Content-Disposition` no trae
  fecha de forma fiable).

`f_public` y `f_providencia` se ponen **ambas** a esa fecha (el sitio no
distingue expedición de publicación de forma fiable).

## Piso de año y rango

- Piso fijo `_ANIO_MINIMO = 2015`. Fila con año < 2015 → `None`.
- Además se respeta el rango `fini`/`ffin` de la corrida (comparación de
  `fecha.isoformat()`), igual que el resto de familias.

## Deduplicación dentro de una corrida

Un solo conjunto `vistos` compartido por las dos secciones.

- **Clave primaria:** el `{id}` de `/web/content/{id}`. La página 1 de
  Resoluciones repite documentos de las páginas 2-11; el mismo `{id}` se procesa
  una sola vez.
- **Clave secundaria (mismo archivo, `{id}` distinto):** la tupla
  `(Content-Length, nombre_de_archivo_del_Content-Disposition)` de la respuesta
  HEAD. En Resoluciones hay ids distintos (p. ej. 10102 y 10260) que sirven
  **byte a byte el mismo PDF**; en Conceptos pasa igual con bloques de ids casi
  consecutivos. Si la tupla ya se vio, se descarta con aviso. Si el HEAD falló
  (sin `Content-Length`), sólo aplica la clave primaria.

## `save_path` / almacenamiento

`storage_path(_SOURCE, fecha_iso, tipo, f"{safe_title}(extension)")`, idéntico al
resto de familias. `_SOURCE = "supervigilancia"`.

## Fuera de alcance (v1)

- **Circulares.** El listado `/2-1-3-3-circulares` tiene sólo 9 bloques; las ~90
  circulares históricas (2006–2026) son páginas Odoo individuales
  (`/circular-externa-no-XXX-…`) y posts de blog (`/blog/name-2/circular-…-NNN`)
  con maquetación heterogénea, alcanzables sólo rastreando `sitemap.xml`. Es un
  proyecto aparte (rastreador de sitemap + parseo por-página frágil). Se puede
  añadir después como sección adicional si aparece un listado mejor.
- **Decretos** (`/2-1-3-1-decretos`, 6 páginas) y **Directivas presidenciales**
  (`/2-1-3-4-directivas-presidenciales`) — no pedidos; misma plantilla si algún
  día se quieren.

## Integración

**Archivos nuevos:**

- `core/scrapers/families/supervigilancia.py` — `@register_family("supervigilancia")`,
  `class ScrapSupervigilancia(BaseScrapper)`, más el helper de parseo del bloque
  `s_dl_item` (se queda en este archivo; si aparece otra fuente Odoo se extrae a
  un común — YAGNI por ahora).
- `tests/families/test_supervigilancia.py`.

**Archivos que se tocan:**

- `core/seed.py` — entrada en el dict de familias (nombre + descripción) y
  `create_source_if_missing(db, family_key="supervigilancia",
  name="Superintendencia de Vigilancia y Seguridad Privada", family_params={})`.
- `tests/test_seed.py` — conteos fijados: familias `26 → 27`; fuentes
  `1 + 28 + 23 + 33 + 6` → `1 + 28 + 24 + 33 + 6` (dos ocurrencias en el
  archivo); añadir `"supervigilancia"` al conjunto de claves y a la lista del
  comentario.
- `core/scrapers/families/__init__.py` — import del módulo nuevo si el paquete
  los lista explícitamente (verificar al implementar).

**Sin migración Alembic.** Añadir familia + fuente es sólo datos. Despliegue a
producción: merge del PR → CI construye imágenes GHCR → correr una vez
`python -m core.seed` en el servidor (sin migración).

**Registro:** entra en `FAMILY_REGISTRY` por el decorador;
`resolve_scraper("supervigilancia", {})` la instancia.

## Pruebas

`tests/families/test_supervigilancia.py`, con HTML real fijado como fixture
(~15 bloques por página, recortado) y las peticiones HTTP (`requests.Session.get`
y `.head`) interceptadas con `responses` o un doble de sesión, mapeando URL →
`(html | headers)` fijados. Casos:

1. Parseo feliz — HEAD devuelve `Content-Disposition:
   filename="20263200005647CS RESOLUCION….pdf"` → `title =
   R_SVySP_20263200005647CS_{año}`, tipo `Resolución`, fecha correcta,
   `title_unverified=False`.
2. Número sólo en la fila del listado (HEAD falla / sin `filename`) — `\d+CS` al
   inicio de `.s_dl_doc_name` → mismo `title` canónico (respaldo #2).
3. Número en prosa — HEAD sin número y `.s_dl_doc_name` =
   `"…CORRECCIÓN A LA RESOLUCIÓN No. 2023320000649…"` → número del patrón en
   prosa (respaldo #3).
4. Sin número en ninguna fuente — `"LINEAMIENTOS PARA LA AUTORIZACIÓN…"` → título
   descriptivo, `title_unverified=True`, el documento **se guarda**.
5. Fecha `"Hoy"` → fecha de la corrida. Fecha `"--"` / vacía → documento
   descartado con aviso vía `on_progress`.
6. `​` (ancho cero) en `.s_dl_doc_name` → se limpia del título.
7. Piso 2015 — fila de 2009 → no entra.
8. Rango `fini`/`ffin` — fila de fecha fuera del rango pedido → no entra.
9. Paginación — páginas 1-3 con bloques y página 4 sin `div.s_dl_item` → el
   scraper para en la 4 y no pide `-pagina05`.
10. Dedup primaria — el mismo `{id}` en la página 1 y en la página 3 → un solo
    documento.
11. Dedup secundaria — dos `{id}` distintos cuyo HEAD da el mismo
    `(Content-Length, filename)` → un solo documento, aviso del segundo.
12. Conceptos — título que es nombre de archivo (`"Renting operativo.pdf"`) →
    extensión `.pdf` quitada; sin número → `title_unverified=True`.
13. Etiquetas basura — fila con `data-category="circulares"` /
    `.s_dl_doc_type="CIRCULAR"` en la página de resoluciones → se clasifica
    `Resolución` (el tipo sale de la sección).
14. HEAD que lanza excepción de red → no rompe la corrida; se cae a los
    respaldos #2/#3 y, si tampoco, a título descriptivo.

`tests/test_seed.py` — conteos actualizados pasan; corrida doble sigue siendo
idempotente.

Se corren dirigidas: `pytest tests/families/test_supervigilancia.py
tests/test_seed.py` (sin la suite pesada completa ni `-p xdist`, según la nota
del entorno).

## Riesgos y notas

- **Calidad de datos baja.** Números ausentes en ~26% de resoluciones, títulos
  que son nombres de archivo, fechas "Hoy"/"--", duplicados en conceptos. El
  diseño tolera todo esto explícitamente pero el resultado tendrá más ruido que
  las fuentes limpias (Supersalud, SSF). Análogo más cercano en el repo:
  MinTransporte (pausado por "volcado de documentos ruidoso").
- **Volumen pequeño:** ~100-120 documentos totales tras el piso 2015.
- **Dependencia de la cabecera de idioma.** Si Odoo cambia el manejo de idioma,
  la paginación puede volver a vaciarse. La prueba 9 fija el comportamiento
  esperado con las páginas ya en español; un cambio del sitio se detectaría como
  "0 documentos nuevos" en una corrida real.
- **El número depende del `Content-Disposition` del HEAD.** Si el sitio deja de
  mandar `filename=` con el número, se cae a los respaldos del listado (`\d+CS`
  al inicio, o número en prosa) y, si tampoco, a título descriptivo con
  `title_unverified=True` — no rompe, sólo se pierde el nombre canónico en esas
  filas.
- **Enlaces cruzados en el sitio (observado 2026-10-09).** 4 filas del
  listado apuntan al PDF de *otra* resolución (p. ej. la fila "41307" sirve el
  PDF de la "36567"). Como el número sale del nombre del archivo, esa fila toma
  el número del PDF que realmente se descarga, pero con la fecha de la fila; y
  si su gemela correcta aparece después, la deduplicación por archivo la
  descarta. Es un error de carga del sitio; no se corrige en v1.
- **Corrida diaria a 30 días** (`scheduled_min_lookback_days = 30`): muchas
  filas sólo traen la fecha de expedición, que puede ir semanas antes de la
  subida. El listado se recorre completo en cada corrida, así que no cuesta
  peticiones extra.
- **Primera corrida real (2026-10-09):** 107 documentos 2015→hoy (100
  resoluciones, 7 conceptos), 21 sin número verificado.
- **Un HEAD por documento.** ~110 peticiones extra por corrida completa. Si el
  host las tolera mal (poco probable en Odoo.sh), habría que serializar con una
  pausa; hoy no se considera necesario.
