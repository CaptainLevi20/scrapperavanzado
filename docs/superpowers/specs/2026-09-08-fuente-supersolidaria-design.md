# Fuente Supersolidaria — diseño

**Fecha:** 2026-09-08
**Entidad:** Superintendencia de la Economía Solidaria (`supersolidaria`, sigla `SES`)
**Estado:** aprobado para plan

> No confundir con `supersociedades` (Superintendencia de Sociedades) — entidad
> y sitio distintos. Esta familia es la segunda mitad del pedido "Superintendencia
> de Sociedades" del usuario, que en realidad mezclaba las dos superintendencias.

## Objetivo

Familia de scraper nueva `supersolidaria` que trae cinco secciones de
normativa de `www.supersolidaria.gov.co`:

| Sección | URL | tipo mostrado | prefijo de título |
|---|---|---|---|
| Resoluciones generales | `/es/content/resoluciones-generales` | `Resolución` | `R` |
| Circulares externas | `/es/content/circulares-externas-por-ano` | `Circular Externa` | `CE` |
| Circulares conjuntas | `/es/content/circulares-conjuntas` | `Circular Conjunta` | `CJ` |
| Cartas circulares | `/es/content/cartas-circulares` | `Carta Circular` | `CC` |
| Conceptos | `/es/conceptos-juridicos-y-contables` | `Concepto` | `CTO` |

Cada documento (PDF, o `.xlsx`/`.doc` para anexos) entra como un `RawDocModel`.

## Construcción del sitio

- **Drupal 10**, `www.supersolidaria.gov.co`. **Corrección post-implementación:**
  el host sirve una cadena TLS incompleta (le falta el intermediario) que
  `certifi`/`requests` no puede validar aunque `curl` sí (trust store del SO).
  Por eso la familia **sí** usa `session.verify = False` + `link["verify"] = False`,
  5ª familia con este patrón (ssf, constitucional, cndj, snr). El supuesto
  original de "TLS válido" era falso.
- Archivos bajo `/sites/default/files/` (`.../data/`, `.../normativa/`,
  `.../conceptos_juridicos_y_contables/`). Enlaces relativos → `urljoin(_BASE, …)`.
- **Las 4 primeras secciones**: toda la lista viene en **una sola página**
  HTML (sin AJAX). Los documentos se agrupan bajo encabezados
  `<h2>… <AÑO></h2>` (p. ej. `Circulares Externas 2024`, mayúsculas y `&nbsp;`
  variables). Hay además un widget QuickTabs por año que es sólo navegación
  alterna — **no hace falta tocarlo**, el contenido completo ya está en el HTML.
  - Resoluciones generales: ~360 adjuntos, 2000–2026.
  - Circulares externas: ~466 adjuntos (incluye anexos), 2000–2026.
  - Cartas circulares: ~121 adjuntos, 2005–2026.
  - Circulares conjuntas: **6 adjuntos**, sin encabezados de año, títulos =
    nombres de archivo crudos.
- **Conceptos**: una **vista Drupal paginada** — `?page=0,1,2,…`, 11 filas por
  página, hoy 3 páginas (~30 conceptos). Se recorre incrementando `page` hasta
  una página con 0 filas.

### Marcado de un documento (secciones de tabla)

```html
<div class="paragraph paragraph--type--archivos-collection …">
  <div class="field field--name-field-archivo …">
    <table data-striping="1"><thead>…</thead><tbody><tr><td>
      <span class="file file--mime-application-pdf …">
        <a href="/sites/default/files/data/20260520_circular_externa_101.pdf"
           title="20260520_circular_externa_101.pdf">Circular Externa N° 101</a>
      </span><span>(235.15 KB)</span>
    </td><td>235.15 KB</td></tr></tbody></table>
  </div>
</div>
```

- Un `<a>` dentro de `span.file` = **un documento**. `título` = texto del `<a>`
  (SIN el ` (NNN KB)` — eso es un `<span>` hermano). `href` = el archivo.
- Los anexos son `<a>` **hermanos** (no anidados) con título que empieza por
  "Anexo" / "Matriz de comentarios" / "Matriz de observaciones", o archivos
  no-PDF.
- Fecha explícita opcional: un bloque
  `field--name-field-fecha-de-publicacion` con `<time datetime="2026-01-21T…Z">`
  cerca del documento (sólo ~56 de 466 lo traen).

### Marcado de una fila de Conceptos

```html
<tr>
  <td class="views-field-title"><a href="/es/content/<slug>">Título del concepto</a></td>
  <td class="views-field-body"><p>Resumen…</p></td>
  <td class="views-field-nothing"><a href="/sites/default/files/conceptos_juridicos_y_contables/20260821_concepto_20261100232001.pdf">Ver más</a></td>
</tr>
```

(el `<a>` de descarga está doblemente anidado en el HTML crudo — BeautifulSoup
encuentra el `href` interno igual.)

## Cobertura

**Desde 2015.** Se descarta todo documento cuya fecha resuelta sea anterior a
`2015-01-01`, y el bucle de años (donde aplica) arranca en
`max(2015, año_de_fini)`.

## Fecha del documento (`f_public` = `f_providencia`)

`filters_by_publication_date = True`. Cadena de resolución por sección:

- **Resoluciones:** `parse_fecha_providencia_es(titulo)` (el título trae la
  prosa "… del 30 de diciembre de 2025") → si falla, prefijo `AAAAMMDD` del
  nombre de archivo → si falla, año del `<h2>` contenedor → `AAAA-01-01`.
- **Circulares externas / Cartas circulares:** prefijo `AAAAMMDD` del archivo →
  **año del `<h2>` contenedor** → `AAAA-01-01`. (El `<h2>` es la señal universal
  y fiable de estas dos.)
- **Circulares conjuntas:** prefijo `AAAAMMDD` → si nada, se omite con aviso
  (en la práctica: 0 documentos hoy, todos < 2015 y sin fecha).
- **Conceptos:** prefijo `AAAAMMDD` del nombre de archivo → si nada, se omite
  con aviso.

**Corrección post-implementación:** el `<time datetime>` que la primera versión
del spec ponía como fuente PRIMARIA de circulares/cartas **no existe alcanzable**
en el DOM real (0 de 981 anclas lo resuelven — vive en campos de nodo, uno por
pestaña-año, no por documento). Se eliminó `_time_iso_de_paragraph` y todo el
plumbing de `time_iso`; la fecha sale del nombre de archivo o del encabezado de
año.

Si la fecha resuelta cae fuera de `[fini, ffin]` o antes de 2015, se descarta.
Un año-solo (`AAAA-01-01`) es deliberadamente aproximado; el título es la
referencia real.

## Nomenclatura de títulos

Formato general `{PREFIJO}_SES_{numero:04d}_{año}`; `title_unverified=True` +
título crudo (`[:120].strip(" .")`, o `"documento"` si vacío) cuando el número
no se puede determinar. `año` = año de la fecha resuelta.

- **Resolución** — título `"Resolución 2025430007935 del …"`: el número es un
  radicado largo. `numero` = **últimos 6 dígitos** del radicado
  (`R_SES_007935_2025`). Formas viejas cortas ("Resolución 745 de 2003") →
  el entero tal cual (`R_SES_0745_2003`).
- **Circular Externa** — `"Circular Externa N° 102"` → `CE_SES_0102_{año}`.
- **Circular Conjunta** — `"Circular conjunta No. 067"` → `CJ_SES_0067_{año}`;
  las de título = nombre de archivo → `title_unverified`.
- **Carta Circular** — `"Carta Circular N° 37"` → `CC_SES_0037_{año}`.
- **Concepto** — radicado del nombre de archivo
  (`20260821_concepto_20261100232001.pdf` → `20261100232001`) →
  `CTO_SES_{radicado}_{año}`; sin radicado (`20250516_concept_uni.pdf`) →
  `title_unverified` con el título de la fila.

### Anexos → documento aparte con sufijo `_A01`

Un adjunto es **anexo** si su **título** (sin acentos, en minúsculas) empieza
por `anexo` o `matriz de` (cubre "Matriz de Comentarios", "Matriz de
Observaciones"). La extensión por sí sola NO marca anexo (una circular vieja
sólo en `.doc` sigue siendo el documento principal). Los anexos `.xlsx`/`.doc`
sí se ingieren.

- El número del anexo se saca de **su propio título** (suele citar al padre:
  "Anexo - Circular Externa N° 101" → 101) con la misma regla del tipo de la
  sección. Título → `{PREFIJO}_SES_{numero:04d}_{año}_A01`.
- Si el título del anexo no permite sacar número → `title_unverified` + título
  crudo.
- Si dos anexos de la misma sección resuelven al mismo
  `{PREFIJO}_SES_{numero}_{año}_A01` con **archivos distintos**, el segundo se
  degrada a `title_unverified` + título crudo (evita colisión de `save_path`,
  mismo criterio que `supersociedades`).
- Los anexos `.xlsx` / `.doc` **sí** se ingieren; `(extension)` se resuelve por
  `Content-Type` al descargar.

## Flujo de `scrap(fini, ffin, …)`

```
session = requests.Session()  (verificación TLS normal, User-Agent de navegador)
docs = []; vistos_por_url = set()

# --- 4 secciones de tabla ---
for (url, tipo, prefijo, fecha_desde_titulo) in _SECCIONES_TABLA:
    if stop_event set: return docs[:limit]
    on_progress("Procesando {tipo}...")
    GET url  (si falla -> on_progress "Error consultando {tipo}: …"; continue)
    soup = BeautifulSoup(html)
    anio_actual = None
    for nodo in soup.recorrido_en_orden():           # h2 y bloques de archivo intercalados
        if nodo es <h2> con año:  anio_actual = ese año;  continue
        if nodo es un <a> de archivo (span.file > a):  # es_anexo se decide por el título
            titulo = texto del <a>;  href = nodo["href"];  url_pdf = urljoin(_BASE, href)
            if url_pdf in vistos_por_url: continue
            es_anexo = _es_anexo(titulo, href)
            fecha = _resolver_fecha(tipo, titulo, href, anio_actual, <time cercano>)
            if fecha is None: on_progress("Aviso: … sin fecha, se omite"); continue
            if fecha < "2015-01-01" or fecha < fini or fecha > ffin: continue
            title, unverified = _titulo(prefijo, tipo, titulo, fecha[:4], es_anexo, ya_emitidos)
            vistos_por_url.add(url_pdf)
            docs.append(RawDocModel(source=_SOURCE,
                link={"url": url_pdf, "method": "GET"},         # sin verify
                title=title, tipo=tipo, f_public=fecha, f_providencia=fecha,
                detalle=titulo or None,
                save_path=storage_path(_SOURCE, fecha, tipo, f"{_safe_title(title)}(extension)"),
                title_unverified=unverified))
            if len(docs) >= limit: return docs[:limit]

# --- Conceptos (vista paginada) ---
if stop_event set: return docs[:limit]
on_progress("Procesando Concepto...")
page = 0
while True:
    if stop_event set: return docs[:limit]
    GET url_conceptos + "?page=" + page   (si falla -> aviso; break)
    filas = tabla.filas de datos
    if not filas: break
    for fila in filas:
        titulo = texto de td.views-field-title a
        href   = td.views-field-nothing a  (el de descarga)
        if not href: on_progress("Aviso: concepto sin PDF «…», se omite"); continue
        url_pdf = urljoin(_BASE, href); if url_pdf in vistos_por_url: continue
        fecha = _fecha_concepto(href, <time de la fila>)
        if fecha is None: aviso; continue
        if fecha < "2015-01-01" or fecha < fini or fecha > ffin: continue
        title, unverified = _titulo_concepto(href, titulo, fecha[:4])
        vistos_por_url.add(url_pdf)
        docs.append(RawDocModel(... tipo="Concepto" ...))
        if len(docs) >= limit: return docs[:limit]
    page += 1
    if page > 200: on_progress("Aviso: tope de páginas de Conceptos"); break

return docs[:limit]
```

`_SECCIONES_TABLA` incluye Circulares Conjuntas con `anio_actual` siempre
`None` (no tiene `<h2>` de año); su fecha sale del archivo/título o se omite.

## Piezas y pruebas

| Función | Qué hace | Pruebas clave |
|---|---|---|
| `_sin_acentos`, `_safe_title` | idénticas al resto de familias | reutilizar patrón |
| `_es_anexo(titulo) -> bool` | título (sin acentos, minúsculas) empieza por `anexo` o `matriz de` | prefijos con acento/mayúscula; circular normal → False; `.doc` con título normal → False |
| `_num_seccion(prefijo, titulo) -> Optional[int]` | número por tipo: radicado→últimos 6; `N° NNN`; `No. NNN`; entero suelto | resolución radicado largo y forma corta; `N° 102`; `No. 067`; sin número → None |
| `_titulo(prefijo, tipo, titulo, anio, es_anexo, ya_emitidos) -> (str, bool)` | `{PREF}_SES_{n:04d}_{anio}` (+`_A01` si anexo); fallback crudo; degradación por colisión | verificado, anexo, fallback, colisión de `_A01` |
| `_anio_de_h2(texto) -> Optional[int]` | `r"(?i)(?:resoluciones generales\|circulares externas\|cartas circulares)\s*&?nbsp;?\s*(20\d{2})"` tolerante | los 3 encabezados, con `&nbsp;` y mayúsculas; un `<h2>` sin año → None |
| `_prefijo_fecha_archivo(href) -> Optional[str]` | `AAAAMMDD` inicial del nombre de archivo → ISO | `20260520_...pdf` → `2026-05-20`; sin prefijo → None; `20261332_` inválido → None |
| `_resolver_fecha(tipo, titulo, href, anio_h2, time_iso) -> Optional[str]` | cadena de la sección "Fecha del documento" | resolución por prosa; circular por `<h2>`; `<time>` gana cuando está; nada → None |
| `_fecha_concepto(href, time_iso) -> Optional[str]` | prefijo del archivo → `<time>` → None | `20260821_...` → `2026-08-21` |
| `_titulo_concepto(href, titulo_fila, anio) -> (str, bool)` | radicado del archivo → `CTO_SES_{rad}_{anio}`; sin radicado → crudo+unverified | `..._20261100232001.pdf`; `20250516_concept_uni.pdf` |
| `_iter_documentos(soup) -> yield ("h2", anio) \| ("doc", a_tag, time_iso)` | recorre el árbol en orden y emite h2-de-año y `<a>` de `span.file` | ignora `<a>` fuera de `span.file`; asocia el `<time>` del mismo paragraph |
| `_filas_concepto(html) -> list[(titulo, href_pdf, time_iso)]` | parsea la tabla de la vista | fila normal; página vacía → `[]` |
| `ScrapSupersolidaria.scrap` | orquesta las 5 secciones | cada sección; filtro de fecha; piso 2015; anexos `_A01`; dedup por URL; `stop_event`; `limit`; degradación por sección; paginación de Conceptos hasta vacío |

Todas las pruebas con HTTP simulado (`responses`), sin red real en el gate.
Fixtures recortadas pero fieles al marcado real de arriba.

## Alta de la fuente

- `core/seed.py`: entrada `_FAMILIES["supersolidaria"]` (`"Superintendencia de
  la Economía Solidaria"`, descripción con las 5 secciones) +
  `repository.create_source_if_missing(db, family_key="supersolidaria",
  name="Superintendencia de la Economía Solidaria", family_params={})`.
- `core/scrapers/families/__init__.py`: agregar `supersolidaria` al import.
- `tests/test_seed.py`: subir las 3 aserciones fijas (25→26 familias;
  `1 + 28 + 22 + 33 + 6` → `1 + 28 + 23 + 33 + 6`; set de keys).
- `docs/guia-despliegue-sistemas.md`: sección nueva (5 secciones, desde 2015,
  TLS válido, nomenclatura, anexos `_A01`, `python -m core.seed` de una vez;
  nota de que las circulares viejas se fechan por el encabezado de año, así
  que su fecha es aproximada al 1 de enero).

## Fuera de alcance

- El widget QuickTabs / sus endpoints AJAX (`/es/quicktabs/nojs/…`) — el HTML
  plano ya trae todo.
- Separar conceptos individuales dentro de un PDF.
- Cualquier sección de `supersociedades` (ya está hecha, PR #81).
