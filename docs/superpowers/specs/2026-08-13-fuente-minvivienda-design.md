# Diseño: Nueva fuente — Ministerio de Vivienda, Ciudad y Territorio (Minvivienda)

**Fecha:** 2026-08-13
**Estado:** Implementado.

## Problema

Continuación del proyecto "una fuente a la vez" para IURISYNC (la fuente
anterior, MinAmbiente, quedó en el PR #46). Esta vez:
`Ministerio de Vivienda, Ciudad y Territorio:
https://minvivienda.gov.co/normativa`.

## Descubrimiento de la página

Investigación hecha con fetch directo del HTML del sitio (no solo con una
herramienta de lectura web genérica — su primer resultado devolvió cifras de
conteo y paginación que resultaron ser **inventadas**: ningún número
aparecía en el HTML real al comprobarlo con `requests`).

- El sitio es **Drupal 9** (a diferencia de MinAmbiente, que era WordPress a
  medida) — no existe hoy una familia Drupal/Views genérica → **familia
  nueva** `minvivienda`, mismo criterio que `mincit`/`madr`/`minambiente`
  (ministerio con maquetación propia).
- El listado es una vista de Drupal (Views) **renderizada en HTML plano del
  lado del servidor** — sin AJAX, sin JS necesario: `GET
  https://minvivienda.gov.co/normativa?tipo={Tipo}&page={N}` (0-indexed).
  El valor de `tipo` debe ser exactamente el que usa el sitio en sus propios
  enlaces de categoría (singular, con tilde/URL-encoded donde aplique:
  `Resolución`→`Resoluci%C3%B3n`, `Ley`, `Decreto`, `Circular`, `CONPES`,
  `Auto`, `Acuerdo`, `Directiva`) — `tipo=Resoluciones` (plural) da 0
  resultados.
- Paginación tradicional, 20 documentos por página, con un link `rel=last`
  que da el número de la última página (confirmado: 974 páginas para
  Resoluciones ⇒ ~19.500 documentos; 15 para Decreto; 11 para Circular).
  **Confirmado que el listado completo de cada categoría está ordenado
  descendente por la fecha real de la norma**, de la más nueva a la más
  vieja, consistente en todas las categorías revisadas.
- Cada fila (`div.views-row`) trae todo lo necesario ya en el HTML, sin
  visitar la página de detalle del documento:
  - Título: `.listing-title a`.
  - Fecha real de la norma (`f_providencia`), ya en **ISO 8601** —
    `.views-field-field-legal-regulation-date time[datetime]` — no requiere
    parsear fechas en texto libre como MinAmbiente/MADR/MinCIT.
  - Fecha de publicación en el sitio (`f_public`, informativa):
    `.views-field-created`, texto tipo `"Mié, 05/08/2026 - 19:03"`.
  - Enlace real al PDF: `.views-field-field-legal-regulation-file a[href]`
    (distinto del link del título, que apunta al nodo Drupal).
  - Descripción: `.views-field-field-summary p`.

## Alcance — las 8 categorías del sitio, todas incluidas

A pedido explícito del usuario se incluyen las 8 categorías del sitio, sin
excluir ninguna. El reto real es que **la categoría `tipo=Auto` del sitio
mezcla tipos de documento distintos bajo la misma etiqueta** (verificado con
fetch, 184 items revisados): Autos reales con numeración limpia (`"Auto
0155 - 2018"`), pero también Sentencias (`"SENTENCIA 2020-0972"`), Avisos
judiciales (`"Aviso 05001 23 33 000 2023 00646 00"`), autos de trámite en
texto libre sin numeración (`"Auto admisorio Acción Popular 50001-23-33-
000-2026-00192-00"`), y Circulares mal etiquetadas (`"Circular
2020EE0037555"` aparece dentro de `tipo=Auto`). En vez de ingerir todo eso
como "Auto", cada fila de `tipo=Auto` se **reclasifica por la palabra
inicial de su propio título** — más confiable que la etiqueta de categoría
del sitio, que ya demostró estar mezclada:

```
"Circular ..."  -> tipo Circular (misma letra/lógica que la categoría Circular)
"Sentencia ..."  -> tipo Sentencia, letra S
"Aviso ..."      -> tipo Aviso, letra AV
cualquier otro   -> tipo Auto, letra AU
```

Una fila reclasificada como Circular usa el mismo `doc_id` (basado en la URL
del PDF) que tendría si apareciera en la categoría `Circular` real — si el
sitio la lista en ambos lados, el pipeline la trata como el mismo documento.

| Categoría | `tipo=` | Letra |
|---|---|---|
| Resoluciones | `Resolución` | `R` |
| Decretos | `Decreto` | `D` |
| Leyes | `Ley` | `L` |
| CONPES | `CONPES` | literal `CONPES` |
| Acuerdos | `Acuerdo` | `A` |
| Directivas | `Directiva` | literal `DIRECTIVA` |
| Circulares | `Circular` | `C` |
| Autos | `Auto` | `AU` (o `Circular`/`S`/`AV` según reclasificación) |

En todos los casos, si no se logra extraer un número confiable, el
documento **no se descarta**: `f_providencia` viene de un campo estructurado
del sitio (`<time datetime>`, siempre presente), así que se guarda con
`title_unverified=True` y el título crudo del sitio — a diferencia de
MinAmbiente, donde la fecha salía del propio título y su ausencia obligaba a
descartar la fila.

## Familia técnica: `minvivienda`

`core/scrapers/families/minvivienda.py`, registrado con
`@register_family("minvivienda")`.

### Paginación con corte temprano

Como el listado está ordenado descendente por `f_providencia`, el bucle de
paginación por categoría se detiene en cuanto: la página no trae ninguna
fila, o todas sus filas quedaron por debajo de `fini` (todo lo que sigue es
aún más viejo). Sin esto, una corrida pediría hasta 974 páginas solo para
Resoluciones en cada ejecución; con el corte, una corrida incremental normal
solo pide 1-2 páginas por categoría — el costo de recorrer el historial
completo solo se paga una vez, en el backfill inicial.

### Extracción del número — un patrón, no anclado al final

`_NUMERO_CORTO_PATTERN` busca en cualquier parte del título un número corto
seguido de su año (`\d{1,4}\s+(?:-|de)\s+\d{4}`, con `"No."` opcional
antes). Cubre tanto el caso simple (`"Resolución 0786 - 2026"` → `0786`)
como los que tienen texto colgando después del año (`"Directiva 006 - 2019
de la Procuraduría..."` → `006`).

**El separador exige espacio a cada lado a propósito.** El primer intento
sin ese requisito (`\d{1,4}\s*(?:-|de)\s*\d{4}`) producía un falso positivo
real: en `"Auto admisorio Acción Popular 50001-23-33-000-2026-00192-00"`
matcheaba `"000-2026"` como si fuera un `numero - año` válido, cuando en
realidad es un fragmento del radicado judicial pegado sin espacios. Exigir
`\s+` (al menos un espacio) a cada lado del separador distingue
correctamente un campo real de "número - año" (siempre con espacios, en
las ~40 muestras reales revisadas) de un número de expediente/radicado
largo con guiones pegados (nunca con espacios). Esto se encontró escribiendo
las pruebas unitarias, antes de cualquier corrida contra el sitio real.

Si `_NUMERO_CORTO_PATTERN` no matchea y el tipo resuelto es Circular, se
intenta el mismo patrón de código de radicado alfanumérico de MinAmbiente
(`_CODIGO_CIRCULAR_PATTERN`, `\d[\dA-Za-z]*\d`) para capturar casos como
`"2026EE0026348"`.

El año del título se toma de `f_providencia[:4]` (ya disponible del campo
estructurado), no se re-extrae del texto del título.

## Fechas — por qué se filtra por `f_providencia`

Igual que MinAmbiente: `f_public` (`created`, "Fecha de publicación" del
sitio) verificado con fetch real como no confiable — una Resolución de 2000
(`f_providencia` real `2000-11-17`) aparece con `created` `18/09/2020`, 20
años después, artefacto de reindexado/migración del CMS. Se filtra
`fini`/`ffin` contra `f_providencia` (`filters_by_publication_date` en
`False`, el default), y `doc_id_uses_publication_date = False` (mismo motivo
que `minambiente`/`rama_judicial`/`samai`: no depender para la identidad del
documento de un campo que el propio sitio puede re-timestampear).

## Nomenclatura del título

`_normalize_title(letra, numero, anio)`:
- `numero` puramente numérico → `f"{letra}_MVCT_{int(numero):04d}_{anio}"`
  (CONPES/Directiva usan su literal en vez de una letra).
- `numero` alfanumérico (radicado de Circular) → `f"C_MVCT_{numero}_{anio}"`
  tal cual, sin `int()`/zero-pad.
- Sin `numero` → `title_unverified=True`, título = texto crudo del sitio.

`MVCT` es la sigla oficial verificada del Ministerio de Vivienda, Ciudad y
Territorio (normograma.mintic.gov.co, CREG, Wikipedia — mismo patrón que
`MADS`/`MCIT`).

## Bug real encontrado en el chequeo contra el sitio real

El chequeo manual (no mockeado) reveló que `tipo=Resolución` devolvía 0
resultados en producción pese a que las pruebas unitarias pasaban: el código
pre-codificaba el valor de `tipo` con `urllib.parse.quote()` antes de
pasarlo a `requests.get(params=...)`, que ya codifica los valores del dict
`params` — el resultado quedaba codificado dos veces (`"ó"` → `%C3%B3` →
`%25C3%25B3`), que el sitio real no reconoce como el mismo carácter. Se
corrigió pasando el valor sin codificar (`"Resolución"` tal cual) y dejando
que `requests` lo codifique una única vez; se agregó una prueba que
inspecciona la URL realmente enviada para evitar la regresión. Ninguna
prueba con `responses` lo detectó porque `responses` intercepta antes de
que la codificación real importe para el matcher — solo una corrida contra
el sitio real lo expuso, igual que el bug de los dos `<span>` en MinAmbiente.

## Manejo de errores

Una página o categoría cuyo `GET` falle no descarta lo ya recolectado — se
registra vía `on_progress` y se continúa con la siguiente categoría. Una
fila sin link de archivo se descarta silenciosamente.

## Seed

`core/seed.py`: nueva entrada `"minvivienda"` en `_FAMILIES` y
`create_source_if_missing(..., family_key="minvivienda", family_params={})`,
mismo patrón que `madr`/`mincit`/`minambiente`. Conteos hardcodeados en
`tests/test_seed.py` actualizados (13 familias).

## Frontend

Ningún cambio de código — Sources/Runs/Documents/dashboard leen familias
desde la API, sin lógica hardcodeada por `family_key`.

## Pruebas

`tests/families/test_minvivienda.py`, 25 pruebas: extracción de número
(caso limpio, con "No.", con "de", con texto colgando tras el año, radicado
alfanumérico, sin número, y el caso de regresión del radicado con guiones
sin espacios), reclasificación de filas de `tipo=Auto`, corte temprano de
paginación (página completa por debajo de `fini`, página vacía), fila sin
archivo descartada, categoría que falla no descarta las demás, filtro por
`f_providencia`, límite respetado, y flags de la familia
(`filters_by_publication_date`/`doc_id_uses_publication_date` en `False`).
