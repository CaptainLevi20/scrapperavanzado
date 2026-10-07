# Fuente SIC — diseño

**Fecha:** 2026-10-07
**Entidad:** Superintendencia de Industria y Comercio (`sic`, sigla `SIC`)
**Estado:** aprobado para plan

## Objetivo

Familia de scraper nueva `sic` que trae la normativa **propia** de la SIC desde
el "Sistema de búsquedas de normas, propio de la entidad" de su sede electrónica:

`https://sedeelectronica.sic.gov.co/transparencia/normativa/busqueda-de-normas/entidad`

| Clasificación del buscador | id (`field_clasificacion2_target_id`) | tipo mostrado | prefijo |
|---|---|---|---|
| Resoluciones (general + particular + "no aplica") | `177` | `Resolución` | `R` |
| Circulares (externas, internas, conjuntas…) | `179` | `Circular` | `C` |
| Títulos Circular Única | `178` | `Título Circular Única` | `TCU` |
| Doctrina (conceptos, relatorías, resoluciones) | `180` | `Concepto` / `Relatoría` / `Resolución` | `CTO` / `REL` / `R` |

### Por qué no la URL original

El usuario dio `/transparencia/normativa/normativa-de-la-entidad/normativa-aplicable`
(clasificación `18`). Es un compendio curado de ~80 normas **de otras
entidades** (decretos de MinHacienda/MinTrabajo, resoluciones CRC/MinSalud,
directivas presidenciales…) que enlazan a sitios externos (SUIN, Función
Pública, portales ministeriales), varios rotos. Se descartó, igual que
MinTransporte. El buscador propio sí trae los actos de la SIC con PDF alojado
en la propia SIC.

## Construcción del sitio

- **Drupal**, `sedeelectronica.sic.gov.co`. TLS válido → **sin** `verify=False`.
  Sin WAF. Sin API (`/jsonapi` 404, `?_format=json` 406); el RSS sólo trae
  novedades mezcladas; `/taxonomy/term/<id>` muestra títulos **sin enlace**.
- **Listado** (GET): filtros `field_clasificacion2_target_id`,
  `field_tipo_acto_target_id`, `field_clasificacion5_target_id` (tema),
  `field_fecha_publicacion_value=<AAAA>` (año de **publicación**), `combine`
  (texto, coincidencia por *contiene* sobre el título) y `page=<n>` (0-based).
  20 filas por página; `items_per_page` se ignora. Encabezado
  `Mostrando la página 1 de N páginas` (ausente si 0 resultados).
- **Fila del listado:**

  ```html
  <div class="normas--row …">
    <span class="text-secondary">Tipo de norma: <strong>Resoluciones </strong></span>
    <span class="badge tag--pin …">Despacho de la Superintendencia </span>   (tema, opcional)
    <h2 class="field__label"><a href="/transparencia/normativa/<slug>">Título</a></h2>
    <p>resumen…</p>
  </div>
  ```

  El listado **no trae fechas**; hay que abrir la ficha.
- **Ficha** (`/transparencia/normativa/<slug>`):

  ```html
  <div class="field field--name-field-fecha-generacion …">
    <div class="field__label">Fecha Expedición</div>
    <div class="field__item"><time datetime="2026-09-29T12:00:00Z">Sep 29, 2026</time></div>
  </div>
  <div class="field field--name-field-fecha-publicacion …">
    <div class="field__label">Fecha publicación</div>
    <div class="field__item"><time datetime="2026-09-30T12:00:00Z">…</time></div>
  </div>
  <div class="field field--name-field-archivo …">           (Archivos adjuntos, opcional)
    <div class="field__item"><span class="file …">
      <a href="/sites/default/files/normativa/RESOLUCI%C3%93N…77121%20DE%202026.pdf">…</a>
    </span></div>
  </div>
  <div class="sic--enlace">… onclick="showModal('https:\/\/www.mintrabajo…')" …</div>  (enlace externo, opcional)
  ```

  Las fechas se leen del atributo `datetime` (ISO), no del texto ("Sep",
  "Mayo"…). Los PDF se toman **sólo** de `field--name-field-archivo`: el sitio
  pone en todas las páginas un enlace global a
  `…/normativa/Términos y condiciones -Sede Electrónica.pdf` que nunca es un
  documento.

## Listado completo: paginación inestable

El listado ordena por fecha de publicación y **los empates se reordenan al azar
en cada petición** (muy frecuentes: decenas de nombramientos publicados el
mismo día). Recorrer `page=0..N-1` repite filas y se salta otras: en
Resoluciones 2025 (615 filas reales) una pasada ve ~455 únicas, y dos pasadas
siguen sin completar. No hay parámetro de orden expuesto.

**Estrategia (prototipada y verificada: 158/158 en 2026, 615/615 en 2025):**
por cada **(clasificación, año de publicación)**:

1. Página 0 → `N` páginas. Si no hay encabezado ni filas → tajada vacía.
2. **Total exacto** = `(N-1)*20 + filas(page=N-1)`.
3. Si `N == 1` → la tajada está completa (una sola página no sufre el
   reordenamiento).
4. Si no: recorrer `page=0..N-1` (unión por `href`). Si ya se tiene el total →
   listo.
5. Si falta: **búsqueda adaptativa por fragmentos de dígitos** con `combine`
   (misma idea que `snr`): consultar `"0"…"9"`; un fragmento que devuelve
   **una sola página** aporta todas sus filas; uno que devuelve más se extiende
   con un dígito más (`"77"→"770"…"779"`), hasta longitud máxima 6. Se **detiene
   apenas la unión alcanza el total**. Tope global `_MAX_BUSQUEDAS` por corrida.
6. Si al terminar la unión < total (tope agotado, o títulos sin dígitos
   distintivos): aviso por `on_progress` con cuántas faltan; se sigue con lo
   encontrado.

Rango de años a consultar: publicación ∈ `[año(fini), min(año(ffin)+1, año actual)]`
(un acto expedido a fin de año puede publicarse en enero siguiente), y nunca
antes de 2015.

## Qué entra

Por cada fila única se abre la ficha. Se descarta:

- **Sin PDF propio** (sólo enlace externo, o nada): fuera. Esto excluye de forma
  natural casi todas las normas de otras entidades y los registros viejos sin
  archivo. (Muestreo: 100 % de los registros ≥ 2015 de las 4 clasificaciones
  tienen PDF propio.)
- **Fecha de expedición < 2015-01-01**: fuera.
- **Fecha de publicación fuera de `[fini, ffin]`**: fuera.
- **Proyectos**: título que empieza por "Proyecto" (sin acentos, minúsculas).
- **Resoluciones de otras entidades**: título que menciona "de la Comisión…",
  "del Ministerio…", "del Departamento…", "de la Agencia…", "de la Presidencia…"
  (son pocas; casi todas ya caen por no tener PDF propio).
- **Doctrina** que no sea concepto, relatoría o resolución (sentencias,
  radicados de otros tribunales, informes, actas, estudios, autos, decretos,
  circulares): fuera.

Se **incluyen** las resoluciones de carácter particular (nombramientos).

## Fechas

- `f_public` = **Fecha publicación** de la ficha;
  `f_providencia` = **Fecha Expedición**.
- `filters_by_publication_date = True`: el rango de la corrida se compara con la
  publicación, así un acto publicado días después de expedido no se pierde en
  la corrida diaria.
- Si falta la de publicación se usa la de expedición y viceversa; si faltan
  ambas → se omite con aviso.

## Nomenclatura de títulos

`año` = año de la **fecha de expedición**. `número` como entero con relleno a 4
(`{n:04d}`); los números de la SIC suelen tener 5 dígitos y quedan tal cual.

| Caso | Regla | Ejemplo |
|---|---|---|
| Resolución (clasif. 177, o Doctrina/178 cuyo título empieza "Resolución") | `R_SIC_{número}_{año}` — número = primer entero tras `Resolución [No.|N°|Número]` | `R_SIC_77121_2026` |
| Circular (179; externa, interna, conjunta: **todas `C`**) | `C_SIC_{número}_{año}` — número = primer entero tras `Circular [Externa|Interna|Conjunta] [No.|N°]` | `C_SIC_0004_2024` |
| Título Circular Única (178) | `TCU_SIC_{romano}_{AAAAMMDD}` — romano del título (`Título X …`), fecha = expedición (cada versión republicada es un documento distinto) | `TCU_SIC_X_20260130` |
| Concepto (Doctrina) | `CTO_SIC_{radicado}` — radicado `AA-NNNNNN` del título ("Concepto 15-159447", "Concepto 17 49443" → `17-49443`) | `CTO_SIC_15-159447` |
| Relatoría (Doctrina) | `REL_SIC_{número}_{año}` — número de la resolución citada | `REL_SIC_27305_2019` |

- **Sin número reconocible** → `title_unverified=True` + título crudo del sitio
  (`[:120].strip(" .")`).
- **Varios PDF en una ficha** (raro, ~0,5 %): el primero es el documento; los
  siguientes son anexos con sufijo `_A01`, `_A02`…
- **Colisión** (mismo título y tipo para PDF distintos, p. ej. una circular
  externa y una conjunta con igual número y año): el segundo baja al título
  crudo del sitio (mismo criterio que `supersociedades`). Deduplicación por URL
  del PDF.
- Una resolución que aparece en Resoluciones **y** en Doctrina produce el mismo
  título y la misma URL → se ingiere una sola vez.

## Comportamiento de corrida

- `tipo` por documento según la tabla de arriba; `detalle` = título crudo.
- `link = {"url": <pdf absoluto>, "method": "GET"}`; `checks_for_republication`
  queda en su valor por defecto (`True`).
- Errores de red en una tajada o ficha → aviso y se continúa. Una clasificación
  sin ninguna fila en todo el rango → aviso de posible cambio de marcado.
- `stop_event` se revisa entre peticiones; `limit` se respeta.
- **Costo:** la corrida diaria consulta sólo el año en curso (y el siguiente si
  aplica): la enumeración del año (decenas a cientos de consultas) + una ficha
  por documento del año (~600–1.000). La carga inicial 2015→hoy es del orden de
  miles de consultas una sola vez.

## Registro

- `core/seed.py`: entrada `"sic": ("Superintendencia de Industria y Comercio",
  "<descripción>")` y `create_source_if_missing(family_key="sic", …)`.
- `tests/test_seed.py`: subir los conteos fijos (familias 28→29, fuentes
  `1 + 29 + …`) y la lista de familias.
- Sin migración. En producción: `core.seed` una vez tras desplegar.

## Pruebas

- **Unidades** con HTML real guardado como fixture (listado, ficha con PDF,
  ficha sólo con enlace externo, ficha con 2 adjuntos):
  extracción de filas, total exacto, fechas `datetime`, PDFs sólo de
  `field-archivo` (ignorando "Términos y condiciones").
- **Nomenclatura**: cada regla de la tabla + `title_unverified` + anexos +
  colisión.
- **Enumeración**: sesión falsa que simula el reordenamiento al azar → la unión
  página+fragmentos alcanza el total; parada temprana; aviso cuando no se
  alcanza.
- **Filtros**: proyecto, otra entidad, doctrina descartada, < 2015, fuera de
  rango, sin PDF.
- `tests/test_seed.py` actualizado.
- **Corrida real en dev** (rango corto reciente + un año completo) verificando
  totales contra el buscador.

## Fuera de alcance

- `relatoria.sic.gov.co` (buscador SPA de decisiones/conceptos): posible
  segunda etapa.
- La página "Normativa aplicable" (normas de otras entidades).
- Proyectos de resolución/circular, nombramientos sin PDF, sentencias de otros
  tribunales.
