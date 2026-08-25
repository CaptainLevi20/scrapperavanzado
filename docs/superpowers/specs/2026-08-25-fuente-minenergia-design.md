# Nueva fuente: Normatividad Ministerio de Minas y Energía (MinEnergía) — Design

## Problema

El Ministerio de Minas y Energía publica su normatividad en un micrositio
propio, `https://normativame.minenergia.gov.co`, sobre la plataforma
Nexura (confirmado por el header `Server: Nexura/7.3`). No encaja en
ninguna de las 18 familias existentes. La URL dada por el usuario
(`loader.php?lServicio=Normatividad&lTipo=User&lFuncion=buscar`) es un
buscador que, sin ningún parámetro de búsqueda, ya muestra **todo** el
listado paginado — no hace falta enviar el formulario.

## Descubrimiento

Confirmado con fetch directo (`curl`, sin headers especiales — sitio sin
protección anti-bot):

- El listado es una **tabla HTML servida por el servidor** (no requiere
  JS): columnas `Nombre estandar` (el número de la norma, ya aislado y
  limpio — no hay que extraerlo de un texto), `Tipo de Norma` (`Decreto`,
  `Resolución` o `Circular` — los 3 únicos tipos vistos en el muestreo),
  `Vigencia` (fecha real del acto, `DD/MM/AAAA`, sin ambigüedad de
  formato) y `Resumen` (detalle).
- El formulario de búsqueda solo filtra por **entidad** (fija, "Ministerio
  de Minas y Energía"), **vigencia** (un año, campo de texto libre —
  `&vigencia={año}` como parámetro GET), **sector** (Ambiental/Energía/
  Gas/General/Hidrocarburos/Minas/Regalías — no relevante para el
  alcance) y **palabras clave**. **No hay filtro por tipo de norma**: los
  3 tipos vienen siempre mezclados en la misma tabla.
- **Paginación**: `&genPag=N`, 10 filas por página. Confirmado con fetch
  real: una página fuera de rango devuelve la tabla sin ninguna fila
  (`0` `<tr>`) — esa es la señal de corte, no el número de enlaces de
  paginación visibles (la barra de paginación solo muestra una ventana
  deslizante de páginas cercanas, no el total real).
- **Orden descendente por fecha confirmado dentro de cada año filtrado por
  `vigencia`** (verificado con fetch real de las páginas 1 y 5 del año
  2026: fechas estrictamente no crecientes en todo el rango, de agosto a
  julio). Esto permite la misma optimización que `mindeporte`/
  `mininterior`: en cuanto la fila más vieja de una página ya es anterior
  a `fini`, se corta la paginación de ese año sin pedir más páginas —
  importante aquí porque, a diferencia de esas familias, cada fila en
  rango implica un segundo request (la página de detalle), así que sin
  este corte un rango de fechas angosto dentro de un año con muchos
  registros pediría igual todas las páginas de todo el año.
- El número (`Nombre estandar`) enlaza a una página de detalle
  (`https://normativame.minenergia.gov.co/normatividad/{id}/norma/`) —
  **el único lugar donde aparece el PDF real**, dentro de un
  `<iframe src="public_html/info/minergia/media/tmp/{archivo}.pdf">`
  (ruta relativa al dominio). Confirmado con 3 muestras reales (Decreto,
  Resolución, Circular): mismo patrón en los 3 casos. Hay un segundo
  `<iframe>` con una URL alterna (`loader.php?...lTipo=viewpdf&id=...`)
  pero está **dentro de un comentario HTML** (`<!-- ... -->`) — no se
  parsea como nodo real, se ignora naturalmente al usar un parser HTML
  normal.
- **Esto implica 2 requests por documento** (uno para el listado, uno
  para la página de detalle) — a diferencia de todas las demás familias,
  que resuelven el enlace de descarga directo desde el propio listado.
- Descarga de PDF confirmada con `curl` real (`User-Agent: Mozilla/5.0`,
  sin sesión): `200`, `application/pdf`, 557 KB en la primera muestra.

## Alcance (v1)

Decisión explícita del usuario: los 3 tipos vistos (Decreto, Resolución,
Circular) — no hay ninguna razón técnica para excluir alguno, los 3 traen
número y fecha igual de limpios (a diferencia de otras fuentes, aquí no
hay heterogeneidad de formato entre tipos porque el sitio ya entrega
número/tipo/fecha como columnas separadas, no embebidas en texto libre).

Fuera de alcance: cualquier otro tipo que pudiera aparecer fuera del
muestreo se procesa igual (el extractor no filtra por tipo, solo mapea la
letra de la nomenclatura) — si apareciera un tipo no mapeado, se deja con
título crudo + `title_unverified=True` en vez de fallar.

## Familia técnica: `minenergia`

Archivo nuevo `core/scrapers/families/minenergia.py`, clase
`ScrapMinEnergia(BaseScrapper)` registrada con `@register_family
("minenergia")`. Una sola fuente en el seed: `source = "Ministerio de
Minas y Energía"`. Sin `family_params` (`{}`).

## Parseo

Dado que el sitio no permite filtrar por rango de fechas exacto (solo por
año vía `vigencia`), la estrategia es:

1. Por cada año en `[fini.year, ffin.year]`: pedir
   `loader.php?lServicio=Normatividad&lTipo=User&lFuncion=buscar&vigencia={año}&genPag={n}`,
   incrementando `genPag` desde 1 hasta que una página devuelva la tabla
   sin filas.
2. Por cada fila (`tr` dentro de `table#date_table`, saltando el
   encabezado): extraer número (`td[0]`, texto del `<a>`), tipo (`td[1]`),
   fecha (`td[2]`, `DD/MM/AAAA` → ISO), resumen (`td[3]`) y la URL de
   detalle (`href` del `<a>` en `td[0]`).
3. Filtrar la fecha exacta contra `[fini, ffin]` (el filtro `vigencia` del
   sitio solo acota por año, no por día).
4. Para cada fila dentro de rango, pedir la página de detalle y extraer
   el `src` del primer (y único real) `<iframe>` — resuelto contra
   `https://normativame.minenergia.gov.co/` con `urljoin`.
5. Si la página de detalle no trae ningún `<iframe>` (sin archivo
   adjunto), se omite el documento con aviso vía `on_progress`.

**Número**: ya viene aislado en su propia celda — no hace falta ninguna
extracción por regex sobre texto libre (a diferencia de todas las demás
familias). Solo se valida que sea numérico (`str.isdigit()`); si no lo
fuera (no se observó ningún caso real), fallback a título crudo +
`title_unverified=True`.

**Fecha**: `DD/MM/AAAA` se parsea directo con `datetime.strptime` — sin
cascada de niveles, sin ambigüedad de formato (a diferencia de las
familias que extraen la fecha de un título en prosa).

## Nomenclatura del título

Decisión explícita del usuario: mismo estilo que las demás fuentes.

- `title = f"{LETRA}_MINENERGIA_{numero:04d}_{año}"` — `D` (Decreto), `R`
  (Resolución), `C` (Circular). `año` = año de la fecha de "Vigencia"
  (fecha real del acto, no una fecha de indexación del sitio — no se
  observó ningún indicio de fecha no confiable aquí, a diferencia de
  `minambiente`/`mindeporte`).
- Sin número reconocible (no observado en la práctica): `title` = número
  crudo tal cual lo trae el sitio, `title_unverified=True`.

## Manejo de errores

Un año o página cuyo `GET` falle (timeout, HTTP error) no descarta lo ya
recolectado de las demás — se registra vía `on_progress` y se continúa
(mismo patrón que todas las demás familias). Una fila sin `<iframe>` en
su página de detalle se omite individualmente.

## Seed

En `core/seed.py`:
- Nueva entrada en `_FAMILIES`: `"minenergia"`.
- `repository.create_source_if_missing(db, family_key="minenergia",
  name="Ministerio de Minas y Energía", family_params={})`.

## Frontend

Ningún cambio: mismo hallazgo que todas las demás familias.

## Pruebas

`tests/families/test_minenergia.py`, con fixtures HTML reales recortados
(tabla de listado + página de detalle con `<iframe>`), mockeadas con
`responses`, cubriendo:
- El parseo de una fila del listado (número, tipo, fecha, resumen, URL de
  detalle) para los 3 tipos.
- El parseo de la página de detalle (extracción del `<iframe src=...>`,
  ignorando el que está dentro de un comentario HTML).
- El filtro exacto de fecha dentro del año pedido.
- El corte de paginación por página sin filas.
- Selección de años en rango `[fini.year, ffin.year]`.
- Omisión de una fila sin `<iframe>` en su detalle.
- Continúa con lo demás si un año o una página de detalle falla.
- Que `minenergia` quede registrada en `FAMILY_REGISTRY`.
