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
| id / enlace | `data-href` (o `href` del `a.s_dl_btn_download`) → `/web/content/{id}?download=true` | `{id}` numérico = clave de dedup dentro de la corrida |
| título | texto de `.s_dl_doc_name` | NFC + borrar `​` (espacios de ancho cero, presentes en varios títulos) + colapsar espacios; si termina en `.pdf`, quitar extensión |
| fecha | texto de `.s_dl_doc_meta` | primer `DD/MM/AAAA`, venga con "Expedición:", "Publicación:", "|Expedición:" (sin espacio) o suelta |
| tamaño | `.s_dl_file_size` (`"394 Kb"`) | sólo para el desempate de dedup de conceptos |
| tipo | **la página de origen**, no el HTML | ver abajo |

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

## Número, nombre canónico y verificación

El número de resolución es **inconsistente**: sólo ~36/145 filas traen un token
`\d{6,}CS` al inicio del título; ~38/145 no traen ningún número; el resto lo
llevan incrustado en prosa (`"…RESOLUCIÓN No. 20221300053467…"`,
`"Resolucion 20253200007657 lineamientos…"`, `"Resolución 2328 de 2008"`).

**Extracción del número — primero que acierte gana:**

1. Token `^\s*(\d{6,}CS)\b` al inicio del texto de `.s_dl_doc_name` (mayúsculas).
2. Nombre de archivo del `Content-Disposition` de la descarga
   (`"20261000015947CS RESOLUCION DE LINEAMIENTOS Y PAGO.pdf"`) — vía
   `resolve_unverified_document`, ver abajo.
3. Prosa en el título: `Resoluci[oó]n\s+(?:N[o°º]\.?\s*)?(\d{4,})`.
4. Sin número → el documento **igual se guarda**.

**Construcción del `title`** (lo que `construir_nombre` usa como `base`).
`{pref}` = `R` para resoluciones, `CTO` para conceptos:

- Con número → `f"{pref}_SVySP_{numero}_{anio}"`, `title_unverified=False`.
  Ej.: `R_SVySP_20263200005647CS_2026`. El número se guarda **literal**: sin
  relleno de ceros, sin normalizar, con el sufijo `CS`, en mayúsculas — los
  números modernos ya son largos y únicos (mismo criterio que `snr` y que los
  conceptos de `ssf`).
- Sin número → título crudo recortado a 120 caracteres, `title_unverified=True`.

**`resolve_unverified_document`:** para los docs con `title_unverified=True`, tras
descargar el PDF se inspecciona el nombre de archivo (`Content-Disposition`, ya
disponible del propio GET de descarga). Si trae un `\d{6,}CS`, se reescribe
`doc.title` a `f"{pref}_SVySP_{numero}_{anio}"` y se baja `title_unverified`.
Si no, se conserva el título descriptivo. `tipo` no cambia (viene de la sección).

**Conceptos:** ninguna fila trae número → todos entran con
`title_unverified=True` y título crudo; `resolve_unverified_document` intenta el
`\d{6,}CS` del `Content-Disposition` y, si aparece, produce
`CTO_SVySP_{numero}_{anio}`.

## Fechas

Texto de `.s_dl_doc_meta`. Se toma el primer `DD/MM/AAAA`. Casos especiales:

- `"Hoy"` → fecha de la corrida.
- `"--"`, vacío, o sin `DD/MM/AAAA` → se intenta la fecha del nombre de archivo
  del `Content-Disposition`; si tampoco hay, **se descarta el documento** con un
  aviso vía `on_progress` (no se aproximan fechas).

`f_public` y `f_providencia` se ponen **ambas** a esa fecha (el sitio no
distingue expedición de publicación de forma fiable).

## Piso de año y rango

- Piso fijo `_ANIO_MINIMO = 2015`. Fila con año < 2015 → `None`.
- Además se respeta el rango `fini`/`ffin` de la corrida (comparación de
  `fecha.isoformat()`), igual que el resto de familias.

## Deduplicación dentro de una corrida

- **Clave primaria:** el `{id}` de `/web/content/{id}`. La página 1 de
  Resoluciones repite documentos de las páginas 2-11; el mismo `{id}` se procesa
  una sola vez.
- **Conceptos, desempate extra:** si dos `{id}` distintos dan idéntico título
  normalizado **y** idéntico `.s_dl_file_size`, se descarta el segundo con aviso.

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
(~15 bloques por página, recortado):

1. Parseo feliz — fila con `\d+CS` al inicio → `title = R_SVySP_{num}_{año}`,
   tipo `Resolución`, fecha correcta, `title_unverified=False`.
2. Número en prosa — `"…CORRECCIÓN A LA RESOLUCIÓN No. 2023…"` → número extraído
   del patrón en prosa.
3. Sin número — `"LINEAMIENTOS PARA LA AUTORIZACIÓN…"` → título crudo,
   `title_unverified=True`.
4. `resolve_unverified_document` — `Content-Disposition:
   filename="20261000015947CS ….pdf"` → reescribe a
   `R_SVySP_20261000015947CS_{año}`.
5. Fecha `"Hoy"` → fecha de la corrida. Fecha `"--"` / vacía → documento
   descartado con aviso.
6. `​` en el título → se limpia.
7. Piso 2015 — fila de 2009 → `None`.
8. Rango `fini`/`ffin` — fila fuera de rango → `None`.
9. Paginación — mock de páginas 1-3 con contenido y página 4 vacía → para en la
   4, no pide la 5.
10. Dedup por `/web/content/{id}` — mismo id en página 1 y página 3 → un
    documento.
11. Conceptos — dedup de dos filas con mismo título normalizado + mismo tamaño →
    una; título con `.pdf` → extensión quitada.
12. Etiquetas basura — fila con `data-category="circulares"` en la página de
    resoluciones → se clasifica `Resolución`.

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
- **`resolve_unverified_document` depende del `Content-Disposition`.** Si el sitio
  deja de mandar `filename=`, los docs sin número se quedan con título
  descriptivo (no rompe, sólo pierden el nombre canónico).
