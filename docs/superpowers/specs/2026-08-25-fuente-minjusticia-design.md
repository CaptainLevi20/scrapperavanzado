# Nueva fuente: Normatividad Ministerio de Justicia y del Derecho (MinJusticia) — Design

## Problema

El Ministerio de Justicia y del Derecho publica su normatividad bajo
`https://www.minjusticia.gov.co/normatividad-co` sobre un sitio Microsoft
SharePoint (confirmado por los headers `Server: Microsoft-IIS/10.0`,
`MicrosoftSharePointTeamServices`, y `generator: Microsoft SharePoint`). No
encaja en ninguna de las 17 familias existentes. La página en sí no trae
ningún documento: enlaza a sub-páginas (`Paginas/Decretos.aspx`,
`Paginas/Resoluciones.aspx`, `Paginas/Circulares.aspx`, ...) cuyo listado
se renderiza client-side vía un web part de SharePoint — el HTML servido
no contiene ni tablas ni enlaces a PDF.

## Descubrimiento — la API REST de SharePoint es pública y anónima

En vez de parsear el HTML renderizado (que requeriría ejecutar JS), se
confirmó con fetch directo que la **API REST estándar de SharePoint está
expuesta sin autenticación** en este sitio público:

```
GET {base}/_api/web/lists?$select=Title,ItemCount,BaseTemplate&$filter=Hidden eq false
```

devuelve las bibliotecas del sitio, incluidas 3 relevantes (bibliotecas de
documentos, `BaseTemplate=101`):

| Lista | Items | Contenido |
|---|---|---|
| `Decretos` | 430 | Normatividad real, muy homogénea |
| `Resoluciones` | 786 | Normatividad real, mayormente homogénea |
| `Circulares` | 43 | Normatividad real, pero con código interno heterogéneo |

Cada item de estas 3 listas trae, confirmado con fetch real
(`$select=Title,MJAnio,MJDescripcion,MJFechaExpedicion,MJTipo,File/ServerRelativeUrl,File/Name&$expand=File`),
columnas propias del sitio:

- `Title`: texto corto, ej. `"0254 de 4 marzo"` (Decreto), `"1510 del 10 de
  agosto"` (Resolución), `"CIRCULAR No MJD-CIR26-0000002-SCF-30320"`
  (Circular) — **sin año** en Decretos/Resoluciones (vive en `MJAnio`
  aparte).
- `MJFechaExpedicion`: fecha ISO real del acto (`"2025-03-04T05:00:00Z"`)
  — **siempre presente** en las 3 listas, ya estructurada por el propio
  sitio. A diferencia de todas las demás familias del proyecto, **no hace
  falta ningún parseo de fecha en español ni cascada de niveles**: se lee
  directo del campo.
- `MJAnio`: año como texto, redundante con el año de `MJFechaExpedicion`
  (se usa el de `MJFechaExpedicion` por consistencia, ver "Nomenclatura").
- `MJDescripcion`: en la práctica siempre `"."` o `None` (confirmado en 15
  muestras reales de Decretos) — no aporta ninguna descripción real, se
  trata como ausente.
- `MJTipo`: puebla `"Decreto"`/`"Resolucion"` de forma confiable en
  Decretos/Resoluciones, pero en Circulares es **inconsistente**: a veces
  `"Circular"`, a veces `"Decreto"` (mal clasificado dentro de su propia
  lista), a veces `None` — no se usa como fuente de verdad; el `tipo` del
  documento lo determina la LISTA de la que vino (parámetro fijo pasado
  por el llamador), nunca este campo.
- `File/ServerRelativeUrl` y `File/Name` (vía `$expand=File`): enlace
  directo al PDF, ej.
  `/normatividad-co/Decretos/DECRETO 0254 DEL 4 DE MARZO DE 2025.pdf`.
  Descarga confirmada con `curl` real (`User-Agent: Mozilla/5.0`, sin
  sesión): `200`, `application/pdf` — mismo header que ya usa
  `core/downloader.py` para todas las fuentes.

**Filtro de fecha nativo**: la API soporta `$filter` sobre
`MJFechaExpedicion` con operadores OData (`ge`/`le` + literal
`datetime'...'`), confirmado con fetch real — permite pedir exactamente el
rango `[fini, ffin]` en una sola consulta por lista, sin necesidad de
paginar hacia atrás cortando por fecha como en las demás familias.
`$top=5000` trae hasta 786 resultados (el máximo de las 3 listas) en una
sola respuesta sin necesitar `$skip`; se sigue el link `d.__next` si
alguna vez apareciera (list más grande a futuro), por robustez.

## Calidad de datos por lista

- **Decretos**: homogéneo — `Title` siempre `"{número} de/del {fecha
  parcial}"`, `MJFechaExpedicion` siempre presente. Sin casos raros
  encontrados en 20 muestras recientes.
- **Resoluciones**: mayormente homogéneo, mismo patrón que Decretos. Un
  caso raro real encontrado (`"002 11 de agosto (2026)"`, archivo real
  `"Res-No-0002-del-11-08-2011-SE-ADOPTA-MANUAL-ESPECIFICO-FUNCIONES.pdf"`
  — un manual de funciones de 2011 mal fechado en el sitio con
  `MJFechaExpedicion=2026-06-02`) — se procesa igual que cualquier otro
  (número `002` extraído normalmente); es un error de datos del propio
  sitio, no algo que este scraper deba detectar o corregir.
- **Circulares**: heterogéneo. La mayoría trae un código interno de
  radicado (`"MJD-CIR{aa}-{consecutivo}[-depto-código]"`, ej.
  `"MJD-CIR26-0000002-SCF-30320"`), pero algunas traen solo una oración
  descriptiva sin ningún código (ej. `"Entrada en vigencia del parágrafo 1
  del artículo 5 de la Ley 2126 de 2021."`). El año embebido en el código
  (`CIR26` → 2026) **no siempre coincide** con el año real de
  `MJFechaExpedicion` (confirmado: un item con código `CIR24` tiene
  `MJFechaExpedicion` de 2026) — nunca se usa el año del código, siempre
  el de `MJFechaExpedicion`.

## Alcance (v1)

Decisión explícita del usuario: **Decretos + Resoluciones + Circulares**
(con parseo dedicado para el código de Circulares).

Quedan fuera (confirmado con fetch real, no son normatividad):
- **Notificaciones** (lista genérica, 671 items): avisos procesales y
  respuestas a PQRSD, no normas.
- **Intervenciones ante el Consejo de Estado** (1215) e **Intervenciones
  ante la Corte Constitucional** (407): alegatos/intervenciones en
  procesos judiciales, no normas emitidas por el ministerio.
- **Documentos**, **Edictos-Anexos**, **Notificacion-Edictos**,
  **NotificacionesEstado**, **SubMenu**, **Páginas**, **Imágenes**,
  **Biblioteca temporal**, **Activos del sitio**: contenido administrativo
  interno o de infraestructura del sitio, no normatividad.

## Familia técnica: `minjusticia`

Archivo nuevo `core/scrapers/families/minjusticia.py`, clase
`ScrapMinJusticia(BaseScrapper)` registrada con `@register_family
("minjusticia")`. Una sola fuente en el seed: `source = "Ministerio de
Justicia y del Derecho"`. Sin `family_params` (`{}`).

## Parseo — sin HTML, consulta directa a la API REST

Un solo extractor (`_extraer_items`) reusado por las 3 listas
(`(lista, tipo, letra)` = `("Decretos", "Decreto", "D")`,
`("Resoluciones", "Resolucion", "R")`, `("Circulares", "Circular", "C")`):

- `GET {base}/_api/web/lists/getbytitle('{lista}')/items` con
  `$filter=MJFechaExpedicion ge datetime'{fini}T00:00:00Z' and
  MJFechaExpedicion le datetime'{ffin}T23:59:59Z'`,
  `$select=Title,MJDescripcion,MJFechaExpedicion,File/ServerRelativeUrl,File/Name`,
  `$expand=File`, `$top=5000`, header `Accept:
  application/json;odata=verbose` (formato verbose porque es el que
  expone `d.results`/`d.__next` de forma directa, sin negociar una versión
  de API distinta).
- **Fecha**: `f_providencia`/`f_public` = fecha (solo la parte `YYYY-MM-DD`)
  de `MJFechaExpedicion` — sin parseo de texto en español, sin cascada de
  niveles.
- **Detalle**: `MJDescripcion` si no es `None` ni `"."` (tras `strip()`),
  si no `None`.
- **Enlace**: `File.ServerRelativeUrl` resuelto contra el dominio base
  (`https://www.minjusticia.gov.co`).
- **Número**:
  - Decretos/Resoluciones: primer run de dígitos en `Title` (`\d+`) —
    mismo criterio que `minambiente`/`mindeporte`.
  - Circulares: patrón dedicado `CIR\d{2}-\d+` (con o sin el prefijo
    `MJD-`) sobre `Title` — si no hay match, sin número.
- **Sin número reconocible**: `title` = `Title` crudo del sitio,
  `title_unverified=True`. A diferencia de `mindeporte`/`minambiente`,
  **nunca se descarta un item por falta de fecha** — `MJFechaExpedicion`
  siempre está presente en las 3 listas, así que el único fallback posible
  aquí es por número, nunca por fecha.

## Nomenclatura del título

Decisión explícita del usuario: mismo estilo que las demás fuentes.

- `title = f"{LETRA}_MINJUSTICIA_{numero:04d}_{año}"` para Decretos (`D`)
  y Resoluciones (`R`), con `año` = año de `MJFechaExpedicion` (nunca de
  `MJAnio` ni del código interno).
- `title = f"C_MINJUSTICIA_{codigo}_{año}"` para Circulares con código
  reconocible, usando el código tal cual (sin `int()`/relleno de ceros,
  igual que el precedente de `minambiente` para su radicado alfanumérico)
  — ej. `C_MINJUSTICIA_CIR26-0000002_2026`.
- Sin número/código reconocible: `title` = título crudo,
  `title_unverified=True`.

## Manejo de errores

Una lista cuyo `GET` falle (timeout, HTTP error) no descarta lo ya
recolectado de las demás — se registra vía `on_progress` y se continúa
(mismo patrón que todas las demás familias). Un item sin `File` (raro, no
observado en la práctica) se omite individualmente.

## Seed

En `core/seed.py`:
- Nueva entrada en `_FAMILIES`: `"minjusticia"`.
- `repository.create_source_if_missing(db, family_key="minjusticia",
  name="Ministerio de Justicia y del Derecho", family_params={})`.

## Frontend

Ningún cambio: mismo hallazgo que todas las demás familias.

## Pruebas

`tests/families/test_minjusticia.py`, con fixtures JSON reales recortados
(respuestas reales de la API REST, con `responses` mockeando las 3 URLs de
lista), cubriendo:
- El parseo de un item de Decretos/Resoluciones (número, fecha directa
  del campo, enlace, detalle ausente cuando `MJDescripcion` es `"."`).
- El parseo de Circulares con código reconocible y sin código (fallback a
  título crudo + `title_unverified`).
- Que el año usado en la nomenclatura sea el de `MJFechaExpedicion`, no el
  del código interno de la Circular (caso real `CIR24`/2026).
- Que ningún item se descarte por falta de fecha (siempre presente).
- El filtro `$filter` de fecha enviado correctamente en la URL de cada
  lista.
- Que continúa con las demás listas si una falla.
- Que `minjusticia` quede registrada en `FAMILY_REGISTRY`.
