# Fuente Cámara de Comercio de Armenia — diseño

**Fecha:** 2026-10-26
**Entidad:** Cámara de Comercio de Armenia y del Quindío — Centro de Conciliación,
Arbitraje y Amigable Composición (`cc_armenia`, sigla `CCAQ`)
**Estado:** borrador con las decisiones del usuario (2026-10-26, ver "Decisiones") — pendiente de aprobación del administrador antes de implementar

> El cliente pidió "laudos" al hablar de la CDMB; los laudos vienen de las
> cámaras de comercio (ver `2026-10-21-fuente-cdmb-design.md`). Esta familia
> trae los de Armenia. La de Bogotá se diseña aparte.

## Objetivo

Familia de scraper nueva `cc_armenia` con una sección:

| Sección | URL de listado | tipo asignado | prefijo de título |
|---|---|---|---|
| Laudos | `GET https://camaraarmenia.org.co/centro-de-conciliacion/arbitraje/`, pestaña "Laudos" (`#tab-9bad5edebe8f416b63c`) | `Laudo arbitral` | `LA` |

Cada laudo (PDF) entra como un `RawDocModel`. Familia **plana**: sin
actuaciones, sin anexos, sin `family_params`.

## Construcción del sitio

- WordPress con tema **Avada** (Fusion Builder) sobre Apache. TLS válido.
  Sin WAF, sin captcha, sin cookies obligatorias (sólo pone `_fbp`).
- La pestaña "Laudos" **no se carga por JavaScript**: el `<div role="tabpanel"
  id="tab-9bad5edebe8f416b63c">` viene completo en el HTML de la página
  (~210 KB, UTF-8). El `#tab-…` de la URL sólo selecciona la pestaña en el
  navegador; la petición es la misma página.
- La misma página está en la API de WordPress
  (`/wp-json/wp/v2/pages/7928`, `content.rendered` contiene la tabla), pero
  no aporta nada sobre el HTML; se usa el HTML, que es lo que ve el usuario.
  Si un día el HTML se rompe por cambios del tema, la API es la alternativa.
- Sin paginación: una tabla, una petición.
- Página modificada por última vez el **2025-04-23** (`modified` de la API).

### La tabla

```html
<div aria-labelledby="fusion-tab-laudos" class="tab-pane fade fusion-clearfix" id="tab-9bad5edebe8f416b63c" role="tabpanel">
<table width="100%"><thead><tr>
  <th>Radicado</th><th>Demandante</th><th>Demandado</th><th>Fecha del Laudo</th><th>Archivo</th>
</tr></thead><tbody>
<tr>
  <td align="left">20230515</td>
  <td align="left">AGROPECUARIA ARCANGEL MIGUEL S.A.S</td>
  <td align="left">…</td>
  <td align="left">18 DE DICIEMBRE DE 2024</td>
  <td align="left"><a href="https://camaraarmenia.org.co/DocumentosCamara/Laudos/LAUDO ARBITRAL AGROPECUARIA ARCANGEL GUILLERMO ROJAS PENA.pdf">Ver archivo</a></td>
</tr>
```

| Dato | De dónde | Notas |
|---|---|---|
| enlace | `href` de la 5.ª celda, absoluto | Trae **espacios** sin codificar; `requests` los codifica (`%20`) y el servidor responde bien. Clave de dedup. |
| radicado | 1.ª celda, 8 dígitos | Número interno del caso. **No** es una fecha ni guarda relación fija con el año del laudo (radicado `20220403` → laudo de julio de 2023). |
| demandante / demandado | 2.ª y 3.ª celdas | Van a `detalle` como `"<demandante> vs <demandado>"`; no al título. |
| fecha | 4.ª celda, en palabras (`03 DE MARZO DE 2006`) | Una fila viene sin el segundo "DE" (`06 DE MARZO 2017`), que `core.fecha_es.parse_fecha_providencia_es` **no** reconoce → parser propio tolerante (`DD [DE] MES [DE] AAAA`). |

La tabla se ubica por `aria-labelledby="fusion-tab-laudos"` (estable si el
editor reordena pestañas) y, si falla, por el id `tab-9bad5edebe8f416b63c`.
Una fila cuenta si tiene 5 celdas y un enlace.

### Archivos

`/DocumentosCamara/Laudos/<nombre>.pdf`, servidos por Apache directo.
`HEAD` → `200` con `Content-Length` y `Last-Modified`, **sin `ETag`**. El
chequeo de republicación del worker compara `Content-Length`, así que funciona
(`checks_for_republication = True`, por defecto). Todos los archivos tienen
`Last-Modified` del 2025-04-23 (re-subida en bloque), así que esa fecha no
sirve como fecha de publicación.

## Número y nombre canónico

- `LA_CCAQ_{radicado}_{año}`, con el año de la **fecha del laudo**.
  Ej.: `LA_CCAQ_20230515_2024`, `LA_CCAQ_20240419_2025`.
- No hay prefijo de laudo en el repositorio (sólo SAMAI usa `RALA` como
  *tipo de proceso* "Recurso de anulación de laudo arbitral"; no aplica).
  `LA` es el prefijo nuevo y se usa igual en Bogotá.
- Sigla `CCAQ` (Cámara de Comercio de Armenia y del Quindío) para no chocar
  con otras "CCA…" futuras. Bogotá es `CCB`.
- `title_unverified=False`: el radicado viene en una celda propia, limpio.
  Fila sin radicado de dígitos → se descarta con aviso.

## Fechas

- `f_public` y `f_providencia` = fecha del laudo (la única que hay).
- El sitio no dice cuándo se publicó cada laudo. El último (20-ene-2025) se
  vio en la página después de esa fecha; la re-subida en bloque de abril de
  2025 borró cualquier otra pista. **El retraso es desconocido** y la
  publicación, esporádica.
- Como una sola petición trae toda la tabla, mirar atrás no cuesta nada:
  **la corrida diaria mira desde 2006** (el piso). Así un laudo subido con
  años de retraso entra igual en la diaria.
- `scheduled_min_lookback_days` es un número fijo de días (el worker hace
  `hoy - días`), así que se pone uno que llegue hasta antes de 2006:
  `scheduled_min_lookback_days = 10_000` (~27 años: hoy llega a 1999 y cubre
  2006 hasta 2033). El piso `_ANIO_MINIMO = 2006` de la familia recorta lo
  anterior. Una prueba falla si el número deja de cubrir el 2006-01-01.
- Costo: igual que antes (1 GET + 14 HEAD). Los laudos ya guardados vuelven
  a listarse cada día y el worker los reconoce por su id; su chequeo de
  republicación hace un `HEAD` por laudo (12).
- Fila sin fecha legible → se descarta con aviso. Fecha posterior a hoy →
  aviso `on_progress` (no se vio ninguna).

## Piso de año y rango

Hay **14 laudos en total**, de 2006 a 2025. `_ANIO_MINIMO = 2006`: se trae
todo (es poco y es lo que el cliente quiere).

## Deduplicación y errores del sitio

- Clave dentro de la corrida: URL del PDF. Hoy no hay repetidos.
- **Archivo que no es el laudo:** la fila del radicado `20220624` (Martha
  Libia Cruz y Dimas Alberto Arias vs Geo Casamaestra, 24-jun-2022) enlaza a
  `Respuesta a la Invitacion a participar en la reglamentacion de la Ley 2445
  de 2025 CIRCULAR No MJD-CIR25-0000025-DMSC-20100.pdf` — una circular del
  Ministerio de Justicia, no el laudo. El laudo correcto existe en la
  biblioteca de medios de WordPress:
  `/wp-content/uploads/2024/07/LAUDO-ARBITRAL.-JUNIO-24-DE-2022.-MARTHA-LIBIA-CRUZ-VS-GEOCASAMAESTRA-SAS.pdf`.
  Regla: una fila cuyo **nombre de archivo** no contiene `LAUDO` se descarta
  con aviso (así no se guarda una circular con nombre de laudo).
- **El "LAUDO" se busca sólo en el nombre del archivo, no en la URL
  completa.** Todos los PDF viven en `/DocumentosCamara/Laudos/`, así que
  buscar en la ruta siempre encontraría "Laudos" y la regla no descartaría
  nada. Nombre = último segmento de la ruta del `href`, decodificado
  (`unquote`, por los `%20`), comparado sin distinguir mayúsculas.
  Ej.: `Respuesta a la Invitacion … DMSC-20100.pdf` → descartado;
  `LAUDO ARBITRAL AGROPECUARIA … .pdf` → entra.
- **Archivo roto:** la fila `20221111` (Soluciones Integrales de Ingeniería
  Aplicada SIIA, 01-oct-2024) da **404**. Como son 14 filas, el scraper hace
  `HEAD` a cada PDF (14 peticiones) y descarta con aviso los que no
  respondan `200`, en vez de dejar que el worker falle la descarga en cada
  corrida.

## `save_path` / almacenamiento

`storage_path(_SOURCE, fecha_iso, "Laudo arbitral", f"{title}(extension)")`.
`_SOURCE = "Cámara de Comercio de Armenia y del Quindío"` (mismo texto que el
`name` del seed).

## Volumen esperado

| Año del laudo | 2006 | 2017 | 2020 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|
| Filas | 1 | 2 | 3 | 2 | 1 | 4 | 1 |

14 filas; hoy entrarían **12** (menos la circular mal enlazada y el 404).
Corrida diaria: 1 GET + 14 HEAD. Prácticamente nunca habrá documentos nuevos.

## Fuera de alcance (v1)

- El resto de pestañas de la página (¿Qué es el arbitraje?, Tarifas,
  Beneficios, Listado de árbitros): no son documentos.
- La biblioteca de medios de WordPress (`/wp-json/wp/v2/media?search=laudo`):
  tiene 5 copias viejas (julio 2024) de laudos que ya están en la tabla; no se
  recorre.
- Conciliaciones, amigable composición, otros servicios de la Cámara.

## Integración

**Archivos nuevos:**

- `core/scrapers/families/cc_armenia.py` — `@register_family("cc_armenia")`,
  `class ScrapCcArmenia(BaseScrapper)`, `scheduled_min_lookback_days = 10_000`
  (corrida diaria desde 2006, ver "Fechas").
- `tests/families/test_cc_armenia.py`.

**Archivos que se tocan:**

- `core/scrapers/families/__init__.py` — añadir `cc_armenia` al import.
- `core/seed.py` — entrada en `_FAMILIES` y
  `create_source_if_missing(db, family_key="cc_armenia", name=_SOURCE, family_params={})`.
- `tests/test_seed.py` — **+1 familia y +1 fuente de "fuente única"** sobre lo
  que haya en `master` al implementar. Con CDMB ya son 32 familias y
  `1 + 28 + 29 + 33 + 6`; se están diseñando en paralelo Bogotá,
  Corporinoquia y Corantioquia, así que el número final depende del orden de
  los merges. Añadir `"cc_armenia"` al conjunto de claves y al comentario.
- `docs/guia-despliegue-sistemas.md` — ficha de la fuente.

Sin migración Alembic. En producción: `python -m core.seed` una vez.

## Pruebas

`tests/families/test_cc_armenia.py`, con la tabla real recortada y
`responses`, sin internet:

1. Fila → `LA_CCAQ_20230515_2024`, tipo `Laudo arbitral`, fecha
   `2024-12-18`, `detalle` "demandante vs demandado", URL absoluta.
2. Fecha sin el segundo "DE" (`06 DE MARZO 2017`) → `2017-03-06`.
3. Año del título sale de la fecha, no del radicado (`20220403` → `_2023`).
4. Filtro `fini`/`ffin` y piso.
5. Archivo sin `LAUDO` en el nombre → descartado con aviso, **aunque la
   ruta tenga `/Laudos/`**; nombre con `%20` o en minúsculas (`laudo …`)
   → entra.
6. `HEAD` 404 → descartado con aviso; los demás entran.
7. Tabla ubicada por `aria-labelledby` aunque cambie el id de la pestaña.
8. Página sin la pestaña de laudos → aviso y 0 documentos (no excepción).
9. Fila sin fecha / sin radicado → descartada con aviso.
10. Dedup por URL.
11. `stop_event` y `limit`.
12. Error 500 en la página → aviso, lista vacía.
13. `date.today() - timedelta(days=ScrapCcArmenia.scheduled_min_lookback_days)`
    es anterior o igual a `2006-01-01`.

Se corren dirigidas: `pytest tests/families/test_cc_armenia.py tests/test_seed.py`.

## Riesgos y notas

- **Aviso de "fuente que puede estar fallando" permanente.** `core/salud_fuentes.py`
  avisa "silencio" cuando una fuente no tiene ningún documento en el último
  año, sin importar `alerta_margen_dias`. El último laudo es de enero de
  2025, así que esta fuente saldrá en ese aviso desde el primer día y casi
  siempre. Opciones: aceptarlo, o (cambio fuera de la familia, a discutir)
  dejar que una familia se excluya de esa alerta.
- **Tabla editada a mano** en el constructor de páginas: el formato de fecha
  ya varía, y un rediseño del tema puede cambiar la estructura. Un cambio se
  vería como "0 documentos" con el aviso de pestaña no encontrada.
- **El radicado no es único garantizado**: si dos laudos del mismo caso
  (p. ej. laudo y su aclaración) se publican con el mismo radicado y año,
  chocarían en el título. Hoy no pasa; si pasa, sufijo `_A01` como anexo.
- Los laudos nombran a personas naturales en `detalle` (demandante /
  demandado). Son documentos públicos publicados por la Cámara.

## Decisiones (2026-10-26)

1. **Sigla:** `CCAQ` (Bogotá queda `CCB`).
2. **Prefijo:** `LA` para laudo arbitral, igual en todas las cámaras.
3. **Piso:** todos, desde 2006 (14 laudos en la tabla).
4. **Laudo mal enlazado (Martha Libia Cruz, 2022):** se descarta con aviso
   (fila cuyo archivo no tiene "laudo" en el nombre). No se corrige a mano.
5. **Alerta de salud:** se acepta que la fuente salga como "sin documentos en
   más de un año"; no se cambia `salud_fuentes`.
6. **Alcance:** sólo laudos.
7. **Filtro "LAUDO" (2026-10-29):** sólo en el nombre del archivo, no en la
   ruta.
8. **Corrida diaria (2026-10-29):** mira desde 2006, no dos años.

Resultado esperado de la carga completa (revisado el 2026-10-26 contra el
sitio): **12 laudos**, con dos avisos (la circular de 20220624 y el 404 de
20221111).
