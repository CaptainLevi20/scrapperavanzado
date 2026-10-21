# Fuente CDMB — diseño

**Fecha:** 2026-10-21
**Entidad:** Corporación Autónoma Regional para la Defensa de la Meseta de Bucaramanga (`cdmb`, sigla `CDMB`)
**Estado:** borrador — pendiente de aprobación del administrador

> El enlace que dio el usuario (`https://www.cdmb.gov.co/tema/normatividad`)
> **no es** el listado de actos de la entidad. Es el portal nuevo "Mi Colombia
> Digital" (Angular + API JSON pública) y sus 374 elementos son, casi todos,
> notificaciones por aviso (~322) y normas nacionales republicadas (~40). Las
> resoluciones y acuerdos propios de la CDMB viven en el sistema documental
> **GDI** (`http://caracoli.cdmb.gov.co/gdi/`), al que el propio portal enlaza
> desde su entrada "Resoluciones". Esta familia lee el GDI.

## Objetivo

Familia de scraper nueva `cdmb` con dos secciones, desde **2025**:

| Sección | URL de listado | tipo asignado | prefijo de título |
|---|---|---|---|
| Resoluciones | `POST /gdi/res_consulta.php` (un año por petición) | `Resolución` | `R` |
| Acuerdos | `GET /gdi/acuerdos.php?bloque=N` (30 filas por página) | `Acuerdo` | `A` |

`R_` sigue la convención de `snr`/`supersalud`/`supervigilancia`; `A` es la
abreviatura que ya usan los ministerios para `Acuerdo` (`mininterior`).

Cada documento (PDF) entra como un `RawDocModel`. Familia **plana**: sin
actuaciones, sin anexos, sin `family_params`.

Pedido del usuario (2026-10-21): "resoluciones y acuerdos", **sin autos**, desde
2025, sigla `CDMB`.

## Construcción del sitio (GDI)

- PHP 5.2 / Apache 2.2 en `caracoli.cdmb.gov.co`. HTML plano con tablas, **sin
  JavaScript, sin WAF, sin captcha**. Sólo **HTTP**: el puerto 443 no responde
  (no hay TLS que verificar, así que tampoco aplica `verify=False`).
- Codificación **ISO-8859-1 / windows-1252** → decodificar con `cp1252`.
- Sin cookies obligatorias: el `PHPSESSID` que entrega no hace falta para
  consultar (verificado sin cookie jar).
- Los PDF son enlaces directos con nombre hash estable:
  `http://caracoli.cdmb.gov.co/gdi/resoluciones/dc085f34b270a559d095.pdf`,
  `.../gdi/acuerdos/8b39b2c720d5c6c1dc5a.pdf`. `HEAD` responde `200` con
  `Content-Length`, `ETag` y `Last-Modified` → el chequeo de republicación del
  worker funciona sin cambios (`checks_for_republication = True`, el valor por
  defecto).

### Resoluciones

Formulario `POST` a `res_consulta.php` con `ob=0&anhoc=<AAAA>&palabras=&botonenv=Buscar`.
Devuelve **todo el año en una sola página** (sin paginación; 2026 = 610 filas,
330 KB). Fila:

```html
<td align="center" class="Estilo13"><a target=_blank href="./resoluciones/dc085f34b270a559d095.pdf ">1298</a></td>
<td ...>09/10/2026</td>
<td ...>POR MEDIO DE LA CUAL SE RESUELVE RECURSO DE REPOSICIÓN ... (recortado)</td>
<td ...><a target=_blank href=res_consdet.php?resolucion=1298&anhoc=2026>...</a></td>
```

| Dato | De dónde | Notas |
|---|---|---|
| enlace | `href` `./resoluciones/<hash>.pdf` (quitar espacio final) → absoluto | Clave de dedup dentro de la corrida |
| número | texto del enlace (`1298`) | 1–4 dígitos en 2025-2026 |
| fecha | `DD/MM/AAAA` de la fila | fecha del acto; ver "Fechas" |
| referencia | tercera celda | recortada por el sitio a ~90 caracteres; no se usa en el título |

Una fila sólo cuenta si tiene enlace a `res_consdet.php?resolucion=<n>`.

### Acuerdos

`GET acuerdos.php?bloque=0`, `bloque=30`, … Muestra **todos los años juntos**
(el campo `anhoc` se ignora: con 2025 sigue mostrando 470 registros) en orden de
número descendente. 16 páginas hoy. Fila con la misma forma (enlace
`./acuerdos/<hash>.pdf`, número, fecha, referencia) y detalle en
`acu_consdet.php?num_acuerdo=<n>`.

- La numeración de acuerdos es **corrida, no anual** (2025 = acuerdos 1484 a 1504;
  2026 llega hasta el 1511). El año del título sale de la fecha de la fila.
- Criterio de parada: página sin filas con `num_acuerdo=<dígitos>`. Tope duro de
  50 páginas.
- Se recorren todas las páginas en cada corrida (~16 GET); no se corta por fecha
  porque el orden es por número, no por fecha, y ya hay errores de fecha (ver
  abajo).

## Número y nombre canónico

- Resolución → `R_CDMB_{numero:04d}_{anio}`. Ej.: `R_CDMB_1298_2026`,
  `R_CDMB_0045_2025` (relleno a 4 dígitos como `R_SNR_0123_2026`).
- Acuerdo → `A_CDMB_{numero:04d}_{anio}`. Ej.: `A_CDMB_1511_2026`.
- `title_unverified=False` siempre: el número viene en una celda propia y
  limpia. Sin `resolve_unverified_document`.
- Número que no es entero positivo (se vieron `-1295` y `-1351` en acuerdos de
  2015 y 2018) → se toma el valor absoluto si hay PDF; fila sin PDF (`href`
  `./acuerdos/ELIMINADO`) → se descarta con aviso. Ambos casos están hoy por
  debajo del piso 2025; se manejan sólo por robustez.

## Fechas

- `f_public` y `f_providencia` = la fecha de la fila (fecha del acto). No se usa
  la "Fecha de Publicación" del detalle porque exige una petición por documento
  (~600-1.400 por año).
- **El GDI publica con mucho retraso.** Muestra de las 60 resoluciones más
  recientes (2026-10-21): días entre la fecha del acto y "Publicado el" →
  mediana **33**, p90 **47**, máx. **54**. Acuerdo 1511: 26/06 → 07/07 (11 días).
  Por eso `scheduled_min_lookback_days = 90`. No cuesta peticiones extra: una
  sola petición trae el año completo y los acuerdos se recorren enteros igual.
  En enero, la ventana de 90 días cruza de año → se piden los dos años.
- Fila sin `DD/MM/AAAA` legible → se descarta con aviso.
- **Fechas erróneas del sitio:** un auto con fecha 16/12/2026 (dos meses en el
  futuro) y un acuerdo con año 2109. El filtro `fini`/`ffin` los deja fuera
  solos; se emite un aviso `on_progress` cuando una fila trae fecha posterior a
  hoy, para que quede visible. No se corrigen.

## Piso de año y rango

- `_ANIO_MINIMO = 2025`. El rango real de cada corrida lo da `fini`/`ffin`; el
  piso sólo impide pedir/aceptar algo anterior a 2025 aunque la corrida manual
  pida un rango más amplio. Bajarlo después es cambiar esa constante.
- Resoluciones: se pide un `POST` por cada año entre `max(fini.year, 2025)` y
  `ffin.year`. Se filtra por la fecha de la fila, no por el año pedido (el
  listado de 2021 trae una fila fechada en 2022).

## Deduplicación dentro de una corrida

- Clave: URL del PDF. En 2015-2026 no hay números repetidos dentro de un año
  ni PDF compartidos entre filas, pero la clave por URL protege si aparecen.

## `save_path` / almacenamiento

`storage_path(_SOURCE, fecha_iso, tipo, f"{title}(extension)")`, igual que el
resto. `_SOURCE = "Corporación Autónoma Regional para la Defensa de la Meseta de Bucaramanga"`
(mismo texto que el `name` del seed).

## Volumen esperado

| | 2025 | 2026 (a 21-oct) |
|---|---|---|
| Resoluciones | 859 | 610 |
| Acuerdos | 21 | 7 |

Corrida completa desde 2025: ~1.500 documentos, 2 POST + ~16 GET de listado.
Corrida diaria: las mismas ~18 peticiones de listado + descargas nuevas.

## Fuera de alcance (v1)

- **Autos** (`aut_consulta.php`, 1.304 en 2025, 803 en 2026): excluidos por
  pedido del usuario. Misma plantilla con paginación de 30; se añade fácil si
  cambian de idea.
- **Portal nuevo `cdmb.gov.co/tema/normatividad`**: notificaciones por aviso
  (nombran a particulares; el auto notificado ya vive en el GDI) y normas
  nacionales (leyes, CONPES, políticas) que son de otras entidades. El usuario
  no sabe si se quieren; queda fuera hasta que el cliente lo pida. Se llega por
  la API pública `GET /api/v1/contents?tags=19` (máx. 20 por página) y el
  detalle `GET /api/v1/contents/{friendlyName}` trae `files[].filePath`.
- **"Laudos"**: el usuario los mencionó, pero no aparecen en ningún lado: 0
  resultados en la búsqueda del portal nuevo ("laudo", "arbitral",
  "tribunal de arbitramento") y ninguna mención entre ~7.800 resoluciones
  2015-2026 del GDI. **Pregunta abierta para el cliente.**
- Años anteriores a 2025 (el GDI tiene resoluciones desde al menos 2010 y
  acuerdos desde 2006).

## Integración

**Archivos nuevos:**

- `core/scrapers/families/cdmb.py` — `@register_family("cdmb")`,
  `class ScrapCdmb(BaseScrapper)`, `scheduled_min_lookback_days = 90`.
- `tests/families/test_cdmb.py`.

**Archivos que se tocan:**

- `core/scrapers/families/__init__.py` — añadir `cdmb` al import.
- `core/seed.py` — entrada en `_FAMILIES` y
  `create_source_if_missing(db, family_key="cdmb", name=_SOURCE, family_params={})`.
- `tests/test_seed.py` — familias `31 → 32`; fuentes
  `1 + 28 + 28 + 33 + 6` → `1 + 28 + 29 + 33 + 6` (dos ocurrencias); añadir
  `"cdmb"` al conjunto de claves y al comentario.
- `docs/guia-despliegue-sistemas.md` — ficha de la fuente (paso 7).

Sin migración Alembic. En producción: `python -m core.seed` una vez.

## Pruebas

`tests/families/test_cdmb.py`, con fragmentos reales de HTML (en cp1252) y
`responses`, sin internet:

1. Parseo de una fila de resolución → `R_CDMB_1298_2026`, tipo `Resolución`,
   fecha, URL absoluta sin el espacio final del `href`.
2. Relleno a 4 dígitos → `45` da `R_CDMB_0045_2025`.
3. Acentos en cp1252 decodificados bien (no se usan en el título, pero sí en
   avisos).
4. Resoluciones: con `fini=2025-12-01`, `ffin=2026-01-31` se hacen dos `POST`
   (`anhoc=2025` y `anhoc=2026`) con el cuerpo esperado.
5. Piso: con `fini=2023-01-01` no se pide `anhoc=2023` ni `2024`.
6. Fila de un año fuera del pedido (2022 dentro del listado de 2021) → filtrada
   por su propia fecha.
7. Acuerdos: paginación `bloque=0,30,60` y la página sin filas detiene el ciclo;
   año en el título tomado de la fecha (`A_CDMB_1511_2026`).
8. Acuerdo con número negativo → valor absoluto; con `ELIMINADO` → descartado
   con aviso.
9. Fecha futura → descartada por rango y aviso `on_progress`.
10. Fila sin fecha → descartada con aviso.
11. Dedup por URL.
12. `stop_event` activado → corta y devuelve lo acumulado.
13. Falla de una sección (500 en resoluciones) → aviso y los acuerdos igual
    entran.
14. `limit` respetado.

Se corren dirigidas: `pytest tests/families/test_cdmb.py tests/test_seed.py`.

## Riesgos y notas

- **Servidor viejo** (PHP 5.2, Apache 2.2, Fedora de 2009). Puede caerse o
  migrarse sin aviso; el portal nuevo podría absorber el GDI. Un cambio así se
  vería como "0 documentos" o error de sección en la corrida.
- **Sólo HTTP.** Sin cifrado; aceptable para documentos públicos.
- **Retraso de publicación de hasta ~2 meses** (ver "Fechas"). La ventana de 90
  días lo cubre; un documento subido más tarde se perdería en la diaria y sólo
  entraría con una corrida manual.
- **2018 incompleto en el GDI** (183 resoluciones contra 500-1.400 en otros
  años). Fuera del piso actual; anotarlo si algún día se baja el piso.
