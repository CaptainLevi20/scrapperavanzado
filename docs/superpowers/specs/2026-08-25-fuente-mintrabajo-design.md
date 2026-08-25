# Nueva fuente: Marco legal Ministerio del Trabajo (MinTrabajo) — Design

## Problema

El Ministerio del Trabajo publica su normatividad en
`https://www.mintrabajo.gov.co/web/guest/marco-legal`, un portal Liferay
(`web/guest/...`, cookie `JSESSIONID`). No encaja en ninguna de las 22
familias existentes. A diferencia de todas las demás, esta página es
**contenido estático editorial**: una única página con varias tablas HTML
(41 en total, agrupadas por el propio editor, no por año de forma
predecible) que cubren **toda** la normatividad de una sola vez — sin
paginación, sin buscador, sin AJAX.

## Descubrimiento

Confirmado con fetch directo (`curl`/`requests`, sin protección anti-bot):

- Cada tabla comparte la misma estructura de columnas:

  ```html
  <table>
    <thead>
      <tr><th>Tipo de Norma</th><th>Norma</th><th>Epígrafe</th>
          <th>Fecha de Expedición</th><th>Acceso</th></tr>
    </thead>
    <tbody>
      <tr>
        <td data-label="Tipo de Norma">Decreto</td>
        <td data-label="Norma">1040 del 05 de Agosto de 2026</td>
        <td data-label="Epígrafe">Por el cual se reglamentan...</td>
        <td data-label="Fecha de Expedición">05/08/2026</td>
        <td data-label="Acceso"><a href="/documents/d/guest/decreto-no-1040-del-5-de-agosto-de-2026">Descargar</a></td>
      </tr>
      ...
    </tbody>
  </table>
  ```

- **781 filas totales** en un solo fetch de la página completa, sin
  necesidad de paginar. Se extraen con `soup.find_all("tr")` en todo el
  documento (cada `<tr>` ya trae sus 5 columnas con `data-label`
  identificando cada una — no depende de a qué tabla pertenece).
- **Tipos encontrados**: `Resolución` (443), `Decreto` (175), `Circular`
  (128), `Leyes` (32), `Códigos` (2), `Manual` (1).
- **Enlace de "Acceso"**: apunta a `/documents/d/guest/{slug}` (Liferay
  Document and Media) — confirmado con `curl` real que **resuelve
  directo al PDF** (`200`, `application/pdf`, 12 MB en la muestra
  probada), sin página de detalle intermedia (a diferencia de
  `minenergia`). Algunos enlaces son absolutos
  (`https://www.mintrabajo.gov.co/documents/...`), otros relativos
  (`/documents/...`) — se resuelven ambos con `urljoin`. Un puñado de
  filas antiguas enlaza a hosts externos
  (`dapre.presidencia.gov.co`, `cdn.actualicese.com`) con el mismo patrón
  de columna — se usan tal cual, sin tratamiento especial.
- **Columna "Norma"**: número aislado del acto, a veces con el tipo
  redundante (`"Ley 2466 de 2025"`) a veces no (`"1040 del 05 de Agosto de
  2026"`, `"No 0096"`) — en todos los casos el primer run de dígitos
  (`\d+`) es el número correcto del acto (verificado en el muestreo, sin
  ningún caso real donde un número posterior en la cadena preceda al
  número del acto).
- **Columna "Fecha de Expedición" — dos formatos mezclados, sin
  ambigüedad entre sí**:
  1. `DD/MM/AAAA` (a veces sin cero a la izquierda, ej. `"7/06/1950"`).
  2. Prosa en español `"{día} de {mes} [de] {año}"` — el conector "de"
     entre mes y año es opcional (visto en el sitio real:
     `"29 de julio 2021"`, `"31 agosto 2023"` sin ningún "de").
  3. Solo año (`"2025"`), un caso real encontrado.
  - **~1% de filas con typos reales del sitio** (mes mal escrito
    `"Octobre"`/`"septiemebre"`, día pegado al "de" sin espacio
    `"18de Julio 2025"`, año truncado `"202"`) — no se intenta adivinar
    estas fechas, se descartan igual que cualquier fila sin fecha
    reconocible (9 de 781 filas, confirmado con el parser real contra
    todas las filas).

## Alcance (v1)

Decisión explícita del usuario: **Decreto + Resolución + Circular +
Leyes** — los 4 tipos que son actos individuales con fecha propia.

Quedan fuera:
- **Códigos** (2 filas: compilaciones completas como el Código Sustantivo
  del Trabajo — sin fecha de acto individual, sin `Epígrafe`).
- **Manual** (1 fila: manual de referencia del inspector, no una norma).

## Familia técnica: `mintrabajo`

Archivo nuevo `core/scrapers/families/mintrabajo.py`, clase
`ScrapMinTrabajo(BaseScrapper)` registrada con `@register_family
("mintrabajo")`. Una sola fuente en el seed: `source = "Ministerio del
Trabajo"`. Sin `family_params` (`{}`).

## Parseo

Sin pedir por año ni paginar: **un único `GET`** a
`https://www.mintrabajo.gov.co/web/guest/marco-legal`, luego
`soup.find_all("tr")` sobre toda la respuesta.

Por cada `<tr>` con las 5 columnas (`data-label`):

- **Tipo**: `Tipo de Norma` — se mapea a la letra de nomenclatura; si no
  está en el mapa (`Códigos`/`Manual`/cualquier tipo nuevo no
  contemplado), se omite la fila (fuera de alcance, no es un error).
- **Número**: primer run de dígitos (`\d+`) en `Norma`.
- **Fecha**: `Fecha de Expedición`, parseada con
  `_parse_fecha_flexible` — intenta `DD/MM/AAAA`
  (`datetime.strptime`), luego el patrón de prosa en español (día + mes +
  año, con el conector "de" opcional entre cada parte), luego solo-año.
  Sin fecha reconocible → se omite la fila (mismo criterio que
  `minambiente`/`mindeporte`: no se inventa fecha).
- **Detalle**: `Epígrafe` (texto plano, sin comillas que limpiar en el
  muestreo real).
- **Enlace**: `href` del `<a>` en `Acceso`, resuelto con `urljoin` contra
  `https://www.mintrabajo.gov.co/` (soporta relativos, absolutos propios,
  y hosts externos).

## Nomenclatura del título

Decisión explícita del usuario: mismo estilo que las demás fuentes.

- `title = f"{LETRA}_MINTRABAJO_{numero:04d}_{año}"` — `D` (Decreto), `R`
  (Resolución), `C` (Circular), `L` (Leyes).
- Sin número reconocible (no observado en la práctica para los 4 tipos en
  alcance): `title` = texto crudo de `Norma`, `title_unverified=True`.

## Manejo de errores

Si el único `GET` de la página falla, se registra vía `on_progress` y se
devuelve la lista vacía (no hay nada más que reintentar — a diferencia de
las demás familias, no hay múltiples categorías/años independientes).

## Seed

En `core/seed.py`:
- Nueva entrada en `_FAMILIES`: `"mintrabajo"`.
- `repository.create_source_if_missing(db, family_key="mintrabajo",
  name="Ministerio del Trabajo", family_params={})`.

## Frontend

Ningún cambio: mismo hallazgo que todas las demás familias.

## Pruebas

`tests/families/test_mintrabajo.py`, con fixtures HTML reales recortados
(varias `<tr>` reales con sus 5 columnas), mockeadas con `responses`,
cubriendo:
- El parseo de una fila para los 4 tipos en alcance.
- Los 3 formatos de fecha (`DD/MM/AAAA`, prosa con y sin el conector "de"
  entre mes y año, solo-año).
- El descarte de una fila sin fecha reconocible (typo real del sitio).
- El descarte de filas `Códigos`/`Manual` (tipo fuera de alcance).
- La resolución de enlaces relativos, absolutos propios y externos.
- Que un solo `GET` fallido devuelva lista vacía sin lanzar excepción.
- Que `mintrabajo` quede registrada en `FAMILY_REGISTRY`.
