# Fuente Supersociedades — diseño

**Fecha:** 2026-09-08
**Entidad:** Superintendencia de Sociedades (`supersociedades`, sigla `SS`)
**Estado:** aprobado para plan

## Objetivo

Familia de scraper nueva `supersociedades` que trae los dos boletines de
recopilación de conceptos de la Superintendencia de Sociedades, cada boletín
como **un documento** (su PDF compilado):

1. **Boletín Jurídico** — mensual — `https://www.supersociedades.gov.co/boletines-conceptos-juridicos`
2. **Boletín Contable** — semestral — `https://www.supersociedades.gov.co/boletines-de-conceptos-contables`

No se separan los conceptos individuales de dentro del PDF (igual criterio que
el Boletín Jurídico de Supersalud).

## Construcción del sitio

- Portal **Liferay** (`Liferay-Portal: Liferay Digital Experience Platform`).
  **Certificado TLS válido** — la familia usa verificación normal (NO
  `verify=False`).
- Cada sección es **una página** cuyo *Asset Publisher portlet* renderiza en
  el HTML estático **todos** los ítems como bloques
  `<div class="journal-content-article" data-analytics-asset-title="...">`.
  Un script del sitio los muestra/filtra con JS, pero los datos ya están en
  el HTML: **no hay que ejecutar JavaScript y no hay paginación**.
- Cada bloque de la lista da: el **título**
  (`data-analytics-asset-title`, p. ej. `"Boletín Jurídico Agosto 2026"` /
  `"Boletín Informativo Contable 2026 - Semestre I"`) y el **enlace al
  artículo** (`<a ... href=".../-/asset_publisher/atwl/content/<slug>?...">`).
- El **enlace al PDF NO está en la lista**: está dentro de cada artículo, como
  `href="/documents/<n>/<n>/<archivo>.pdf/<uuid>?t=<ts>"` (botón "PDF Boletín
  Jurídico" / "PDF Boletín Contable"). Hay que **abrir cada artículo** para
  obtenerlo.
- Volumen actual: jurídico **161** ítems (mensual, desde ~2013); contable
  **15** ítems (semestral, desde 2017).

## Cobertura

**Todo lo disponible** — sin piso de año. (El backfill inicial abre ~176
artículos y baja ~176 PDF; las corridas incrementales solo tocan los ítems
cuyo mes/semestre cae en el rango.)

## Nomenclatura

`filters_by_publication_date = True`. El título del ítem es la fuente de
verdad del periodo.

### Boletín Jurídico (mensual)

`BOL_SS_{MES}_{año}` con `MES ∈ {ENE, FEB, MAR, ABR, MAY, JUN, JUL, AGO, SEP,
OCT, NOV, DIC}`.

- Se busca en el título (normalizado sin acentos, en minúsculas) el nombre de
  mes en español y un año de 4 dígitos.
- Ejemplos reales de título: `"Boletín Jurídico Agosto 2026"`,
  `"BOLETÍN CONCEPTOS JURÍDICOS JULIO 2026"` → ambos `BOL_SS_JUL/AGO_2026`.
- `f_public` = **día 1 del mes** (`{año}-{mm}-01`). `f_providencia` = igual.
- tipo mostrado: `"Boletín Jurídico"`.

### Boletín Contable (semestral)

`BOL_SS_{SEM}_{año}` con `SEM ∈ {SI, SII}`.

- `"Semestre I"` / `"Semestre 1"` → `SI`; `"Semestre II"` / `"Semestre 2"` →
  `SII`.
- Sin la palabra "Semestre" pero con un mes: mes en `enero..junio` → `SI`;
  `julio..diciembre` → `SII` (cubre `"Boletin Contable Diciembre 2023"`).
- `f_public`: `SI` → `{año}-06-30`; `SII` → `{año}-12-31`. `f_providencia` =
  igual.
- tipo mostrado: `"Boletín Contable"`.

### Fallback (ambas secciones)

Si no se puede determinar `{MES|SEM}` **o** el año: `title_unverified = True`,
`title` = título crudo recortado a 120 y `.strip(" .")` (fallback
`"documento"` si el título viniera vacío). El ítem **igual se ingiere** si se
pudo resolver una fecha; si tampoco hay fecha, se omite con aviso por
`on_progress`.

## Flujo de `scrap(fini, ffin, ...)`

```
session = requests.Session()  (verificación TLS normal, User-Agent de navegador)
docs = []
for (url_seccion, tipo, parser_periodo) in [_SECCION_JURIDICO, _SECCION_CONTABLE]:
    if stop_event set: return docs[:limit]
    on_progress("Procesando {tipo}...")
    GET url_seccion  (si falla -> aviso, continue)
    items = _items_de_lista(html)   # [(titulo, url_articulo), ...] de todos los journal-content-article
    if not items and on_progress: aviso "no se encontró ningún boletín (¿cambió la página?)"
    for (titulo, url_articulo) in items:
        if stop_event set: return docs[:limit]
        periodo = parser_periodo(titulo)      # ("AGO", 2026) | ("SI", 2026) | None
        fecha   = _fecha_de_periodo(periodo)  # "2026-08-01" | "2026-06-30" | None
        if fecha is None:
            on_progress("Aviso: boletín sin periodo/fecha reconocible «...», se omite"); continue
        if fecha < fini or fecha > ffin: continue     # filtro barato ANTES de abrir el artículo
        GET url_articulo  (si falla -> aviso, continue)
        pdf_url = _pdf_del_articulo(html_articulo)     # primer /documents/.../*.pdf del cuerpo
        if not pdf_url:
            on_progress("Aviso: boletín «...» sin PDF en el artículo, se omite"); continue
        title, unverified = _titulo(tipo, periodo, titulo)
        docs.append(RawDocModel(
            source="Superintendencia de Sociedades",
            link={"url": urljoin(_BASE, pdf_url), "method": "GET"},   # sin verify=False
            title=title, tipo=tipo,
            f_public=fecha, f_providencia=fecha,
            detalle=titulo,          # el título descriptivo del boletín
            save_path=storage_path(source, fecha, tipo, f"{safe}(extension)"),
            title_unverified=unverified))
        if len(docs) >= limit: return docs[:limit]
return docs[:limit]
```

Dedup por URL de PDF dentro de cada sección (defensivo, por si un mes
aparece dos veces en la lista con slugs `-1`, `-2`).

## Piezas y pruebas

| Función | Qué hace | Pruebas clave |
|---|---|---|
| `_mes_a_sigla(texto) -> Optional[str]` | nombre de mes ES → `ENE..DIC` | los 12 meses; con acento y sin; None si no hay |
| `_periodo_juridico(titulo) -> Optional[Tuple[str,int]]` | `("AGO", 2026)` | ambos formatos reales de título; None sin mes o sin año |
| `_periodo_contable(titulo) -> Optional[Tuple[str,int]]` | `("SI"/"SII", 2026)` | "Semestre I/II/1/2"; "Diciembre 2023"→SII; "2017" solo→None |
| `_fecha_de_periodo(tipo, periodo) -> Optional[str]` | ISO | jurídico→`-01`; contable SI→`-06-30`, SII→`-12-31`; None |
| `_titulo(tipo, periodo, crudo) -> Tuple[str,bool]` | `BOL_SS_...` o crudo+unverified | verificado y fallback |
| `_items_de_lista(html) -> List[Tuple[str,str]]` | (título, url_artículo) de cada `journal-content-article` que sea un boletín | ignora el bloque `WC-Footer`; lista vacía si cambia el marcado |
| `_pdf_del_articulo(html) -> Optional[str]` | primer enlace `/documents/\d+/\d+/[^"]*bolet[ií]n[^"]*\.pdf[^"]*` (nombre de archivo con "boletin", case-insensitive, sin acentos) | ignora el `Decreto-Unico-...pdf` del pie de página que aparece en todas las páginas; None si no hay |
| `_safe_title` | saneo de nombre de archivo | reutilizar patrón del resto de familias |
| `ScrapSupersociedades.scrap` | orquestación de las 2 secciones | ambas secciones, filtro de rango previo al fetch del artículo, `stop_event`, `limit`, degradación si una sección falla, aviso si la lista viene vacía |

Todas las pruebas con HTTP simulado (`responses`), sin red real en el gate.

## Alta de la fuente

- `core/seed.py`: entrada en `_FAMILIES` (`"supersociedades": ("Superintendencia
  de Sociedades", "Boletín jurídico (mensual) y boletín contable (semestral)
  de recopilación de conceptos, publicados por la Superintendencia de
  Sociedades")`) + `repository.create_source_if_missing(db,
  family_key="supersociedades", name="Superintendencia de Sociedades",
  family_params={})`.
- `core/scrapers/families/__init__.py`: agregar `supersociedades` al import.
- `tests/test_seed.py`: subir las 3 aserciones fijas (nº de familias, set de
  keys, nº de fuentes).
- `docs/guia-despliegue-sistemas.md`: sección nueva (qué trae, desde cuándo,
  nomenclatura, TLS válido, `python -m core.seed` de una vez).

## Fuera de alcance

- Separar conceptos individuales de dentro de cada PDF.
- Las 5 secciones de **Supersolidaria** (`supersolidaria.gov.co`) — entidad
  distinta, familia aparte, spec propio después de esta.
