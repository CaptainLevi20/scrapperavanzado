# Fuente Corantioquia — diseño

**Fecha:** 2026-10-26
**Entidad:** Corporación Autónoma Regional del Centro de Antioquia (`corantioquia`, sigla `CORANT`)
**Estado:** borrador con las decisiones del usuario (2026-10-26, ver "Decisiones") — pendiente de aprobación del administrador antes de implementar

> El enlace que dio el usuario (`https://www.corantioquia.gov.co/normativa-interna/`)
> es una página WordPress/Elementor armada a mano: trae unos cuantos PDF
> sueltos (estatutos, acuerdos de 2007-2015, alguna resolución reciente) y,
> para cada año desde 2016, **sólo un enlace** a
> `https://sirena.corantioquia.gov.co/esirena/CtrlPublicaciones#/<año>`. Ese
> enlace es el **Boletín Oficial** de e-SIRENA, el sistema de trámites de la
> corporación, y es donde están todos los actos publicados. Esta familia lee
> el boletín, no la página de WordPress.

## Objetivo

Familia de scraper nueva `corantioquia` con dos secciones, desde **2025**:

| Sección | De dónde | tipo asignado | prefijo de título |
|---|---|---|---|
| Resoluciones | documentos del boletín con `tipo.nombre == "Resolución"` | `Resolución` | `R` |
| Acuerdos | documentos del boletín con `tipo.nombre == "Acuerdo"` | `Acuerdo` | `A` |

Mismos prefijos que `cdmb`. Familia **plana**: sin actuaciones, sin anexos,
sin `family_params`.

Mismo alcance que la CDMB ("resoluciones y acuerdos, sin autos, desde
2025"), confirmado por el usuario. Ver "Decisiones".

## Construcción del sitio (e-SIRENA)

- Java (JSESSIONID) detrás de Apache 2.4 / Windows. La página
  `CtrlPublicaciones` es un cascarón AngularJS 1.2 (`publicaciones/js/boletines.js`)
  que pide **JSON** al mismo endpoint. Se usa el JSON directo: sin
  JavaScript, sin WAF, sin captcha, sin cookies obligatorias (probado sin
  cookie jar).
- **TLS: cadena incompleta.** `www.` y `sirena.corantioquia.gov.co` entregan
  sólo el certificado `*.corantioquia.gov.co` sin el intermedio *Sectigo
  Public Server Authentication CA OV R36* → `requests`/`curl` fallan con
  "unable to get local issuer certificate". En la investigación se verificó
  completando la cadena con el intermedio publicado por Sectigo
  (`http://crt.sectigo.com/SectigoPublicServerAuthenticationCAOVR36.crt`,
  URL AIA del propio certificado) y verifica bien. Ver "TLS" más abajo.
- Codificación UTF-8.

### Índice de boletines

`GET /esirena/CtrlPublicaciones?ctrlAction=C&pagina=1&doAction=A` → un JSON
(~260 KB) con **todos** los boletines de 2014 a hoy, agrupados por año:

```json
{"limit": 0, "boletines": {"2026": [
  {"numero": 2876, "agno": 0, "documentos": [], "mes": "Octubre",
   "nombre": "2876 de 14 de octubre de 2026"}, ...]}}
```

- Un boletín por día hábil (2024 = 244, 2025 = 226, 2026 = 194 al 26-oct).
- La **fecha del boletín** sólo viene en `nombre` (`"<n> de DD de <mes> de AAAA"`).
  El boletín del día ya aparece ese mismo día (el 2884 "de 26 de octubre" se
  vio el 26-oct).

### Documentos de un boletín

`GET /esirena/CtrlPublicaciones?ctrlAction=C&numero=<n>&pagina=<p>` →
15 documentos por página (`"limit": 15`). `agno` y `mes` no hacen falta.
Pasada la última página: `{"limit": 15, "boletines": {}, "error": ""}`.

```json
{"limit": 15, "boletines": {"2026": {"2876": {"numero": 2876, "nombre": "2876 de 14 de octubre de 2026",
  "pagina": 1, "documentos": [
  {"sirenaRadicado": "040-RES2610-3892", "fechaRadicacion": "09 de Octubre de 2026",
   "tipo": {"nombre": "Resolución"}, "subtipo": {"nombre": "Por la cual se archiva un expediente"},
   "cantidadAnexos": 0,
   "linkDescarga": "https://sirena.corantioquia.gov.co/esirena/CtrlPublicaciones?ctrlAction=D&doc=2483007"}, ...]}}}}
```

| Dato | De dónde | Notas |
|---|---|---|
| enlace | `linkDescarga` (`ctrlAction=D&doc=<id>`) | Clave de dedup dentro de la corrida (`doc`). |
| radicado | `sirenaRadicado` | `<dependencia>[<oficina>]-<TIPO><AAMM>-<consecutivo>` |
| fecha del acto | `fechaRadicacion` (`"09 de Octubre de 2026"`) | → `f_providencia` |
| fecha de publicación | `nombre` del boletín | → `f_public` |
| descripción | `subtipo.nombre` | Genérica ("Por la cual se otorga un permiso de vertimiento"); sin nombres de particulares. Va a `detalle` junto con el radicado. |
| tipo | `tipo.nombre` | Ver tabla de volumen. |

Hay que ir a buscar `subtipo` con `.get`: un registro (una notificación) no lo trae.

### Descarga

`ctrlAction=D&doc=<id>` responde un PDF real (`%PDF-1.6`) con
`Content-Disposition: attachment; filename=<otro-id>.pdf` y
`Content-Type: text/plain` (equivocado; ver "Descargador"). `HEAD` responde `200` con `Content-Length` pero **sin `ETag` ni
`Last-Modified`**; no respeta `Range`. El chequeo de republicación del worker
funciona por tamaño (`checks_for_republication = True`, por defecto).

## Número y nombre canónico

El radicado trae tipo, año, mes y un **consecutivo anual por tipo, común a
todas las dependencias** (040, 160AN, 160TH…): en 2025 las resoluciones van
del 1 al 4967 y no hay dos con el mismo (tipo, año, consecutivo) en todo
2025-2026. El código de dependencia no hace falta en el título.

- Patrón: `^\d{3}[A-Z]{0,4}-(RES|ACU)(\d{2})(\d{2})-(\d+)$`.
- Resolución → `R_CORANT_{consecutivo:04d}_{20AA}`. Ej.: `040-RES2610-3892`
  → `R_CORANT_3892_2026`; `160TH-RES2501-80` → `R_CORANT_0080_2025`.
- Acuerdo → `A_CORANT_{consecutivo:04d}_{20AA}`. Ej.: `180-ACU2610-84` →
  `A_CORANT_0084_2026`.
- El año del título sale del radicado. En 2025-2026 `AAMM` coincide siempre
  con `fechaRadicacion` (0 diferencias en ~4.700 actos).
- `title_unverified=False` siempre.
- Radicado que no cumple el patrón (hoy sólo los antiguos `130SAE-1105-131`,
  `130SAE-15`, todos anteriores a 2016 y por eso fuera del piso) → si aun así
  pasa el filtro de fecha, título `R_CORANT_<radicado saneado>` y aviso
  `on_progress`.
- La numeración de acuerdos tiene huecos (2025: del 10 al 124, publicados 25).
  No es un error de la familia: el boletín sólo trae los acuerdos del Consejo
  Directivo que se publican.

## Fechas y filtro

- `f_public` = fecha del boletín; `f_providencia` = `fechaRadicacion`.
- **`filters_by_publication_date = True`**: la corrida recorre los boletines
  cuya fecha cae en `[fini, ffin]` y toma todos sus documentos. Motivo: el
  boletín de un día es fijo (el mismo acto no se vio en dos boletines en
  2025-2026), así que filtrar por boletín no pierde nada y no hay que mirar
  meses atrás.
- Retraso entre el acto y su publicación (2025-2026, resoluciones y
  acuerdos): mediana **1 día**, p99 **11 días**; 18 de ~4.700 por encima de
  30 días (hasta 225 días para un acto de 2025). Con el filtro por boletín
  esos también entran en la corrida diaria del día en que salen.
  **No hace falta `scheduled_min_lookback_days`.**
- **Piso:** se descarta el acto con `fechaRadicacion` anterior a 2025 aunque
  salga en un boletín de 2025 o 2026. El boletín republica actos viejos
  (resoluciones de 2000-2015 publicadas en febrero de 2026, `130SAE-…`, y
  ~15 de 2023-2024). `_ANIO_MINIMO = 2025`. También se piden sólo boletines
  con fecha ≥ 2025-01-01.
- Documento sin `fechaRadicacion` legible o boletín sin fecha en `nombre` →
  se descarta con aviso (0 casos en 2025-2026).

## Recorrido

1. `GET` del índice (una petición).
2. Para cada boletín con fecha en `[max(fini, 2025-01-01), ffin]`, en orden
   cronológico: páginas 1, 2, … hasta que la respuesta traiga 0 documentos o
   menos de 15 (así se ahorra la última petición vacía). Tope duro de 30
   páginas por boletín (el mayor visto tiene 3).
3. Se quedan sólo `Resolución` y `Acuerdo`.

Corrida completa desde 2025: 1 + ~1.000 `GET` livianos, unos 80 segundos
medidos. Corrida diaria (3-4 boletines): ~10 `GET`.

## Deduplicación dentro de una corrida

- Clave: `doc` del `linkDescarga`. En 2025-2026 no hay radicados ni enlaces
  repetidos; la clave protege si aparecen.

## TLS

Dos opciones; se propone la **A** por ser la convención del proyecto:

- **A. `verify=False` sólo para `*.corantioquia.gov.co`**, en la sesión
  (`session.verify = False`) y en `link["verify"] = False` de cada documento,
  como `snr`/`ssf`/`supersolidaria`, documentado en el código y en la guía.
- **B. Completar la cadena:** guardar el intermedio Sectigo OV R36 en el repo
  y pasar como `verify` la ruta de un bundle (certifi + intermedio). Más
  seguro, pero `link["verify"]` se guarda en la base y el bundle tiene que
  existir con la misma ruta en la API y en el worker; es un patrón nuevo.

Ver "Preguntas abiertas".

## Descargador: `text/plain` → `application/pdf`

Hoy `core/downloader.py` sólo corrige el `content_type` cuando el servidor
manda uno vacío o `application/octet-stream` (caso Superfinanciera): lo
deriva de la extensión ya resuelta con `_EXT_TO_CONTENT_TYPE`. Un
`text/plain` pasa intacto y se guarda así; el endpoint de vista previa
ramifica por `content_type` exacto (`== "application/pdf"`), así que **los
~4.700 PDF de Corantioquia quedarían sin vista previa**.

Cambio (fuera de la familia, en `core/downloader.py`):

- Tratar `text/plain` igual que `application/octet-stream` / vacío, **pero
  sólo si la extensión resuelta está en `_EXT_TO_CONTENT_TYPE`** (`.pdf`,
  `.docx`, `.doc`, `.rtf`, `.xlsx`). La extensión sale del
  `Content-Disposition` (`filename=<id>.pdf`), que `extract_filename` ya lee
  antes que el `Content-Type`.
- Un `.txt` real (o cualquier extensión no mapeada) sigue como
  `text/plain`: no se inventa un tipo.
- Actualizar el comentario de `_EXT_TO_CONTENT_TYPE` para nombrar a
  Corantioquia junto a la Superfinanciera.

Es genérico (no mira la fuente): cualquier otra fuente que mande un PDF como
`text/plain` con un nombre `.pdf` también gana la vista previa.

**Documentos ya guardados:** ninguno (la fuente es nueva), así que no hace
falta corregir `content_type` en la base.

## `save_path` / almacenamiento

`storage_path(_SOURCE, f_public, tipo, f"{title}(extension)")`, igual que el
resto. `_SOURCE = "Corporación Autónoma Regional del Centro de Antioquia"`
(mismo texto que el `name` del seed).

## Volumen esperado

Por año del acto (`fechaRadicacion`), contado en los boletines de 2025-2026:

| tipo en el boletín | 2025 | 2026 (a 26-oct) | ¿entra? |
|---|---|---|---|
| Resolución | 2.560 | 2.092 | sí |
| Acuerdo | 25 | 23 | sí |
| Acto administrativo (autos, `ADM`) | ~1.800 | ~1.600 | no (supuesto) |
| Notificación por aviso (`NAV`) | 135 | 380 | no |
| Edicto (`EDI`) | 47 | 304 | no |
| Aviso, Comunicación oficial interna | 3 | 4 | no |

Corrida completa desde 2025: **~4.700 documentos**. Unos 230 por mes.

Casi todas las resoluciones son **actos individuales de trámite ambiental**
(permisos de vertimiento ~500/año, concesiones de aguas, sancionatorios,
archivos de expediente, desistimientos). Sólo ~100 en 2025-2026 tienen
subtipo `General`. Ver "Preguntas abiertas".

## Fuera de alcance (v1)

- **Autos** (`Acto administrativo`), **notificaciones por aviso**, **edictos**,
  **avisos**: fuera por el mismo criterio que la CDMB (supuesto).
- Los PDF sueltos de la página de WordPress (estatutos, acuerdos 2007-2015,
  resoluciones viejas): anteriores al piso. Varios enlaces apuntan a
  `http://localhost/Wordpress/...` y están rotos.
- `/normativa-externa/`: normas de otras entidades.
- Anexos: `cantidadAnexos` es 0 en los ~4.700 actos de 2025-2026. Si aparece
  uno mayor que 0 se emite un aviso y se guarda sólo el documento principal.
- Años anteriores a 2025 (el boletín llega hasta 2014).

## Integración

**Archivos nuevos:**

- `core/scrapers/families/corantioquia.py` — `@register_family("corantioquia")`,
  `class ScrapCorantioquia(BaseScrapper)`, `filters_by_publication_date = True`.
- `tests/families/test_corantioquia.py`.

**Archivos que se tocan:**

- `core/scrapers/families/__init__.py` — añadir `corantioquia` al import.
- `core/downloader.py` — `text/plain` con extensión conocida se normaliza
  por la extensión (ver "Descargador").
- `tests/test_downloader.py` — pruebas del cambio (ver "Pruebas").
- `core/seed.py` — entrada en `_FAMILIES` y
  `create_source_if_missing(db, family_key="corantioquia", name=_SOURCE, family_params={})`.
- `tests/test_seed.py` — sumar uno al número de familias y al bloque de
  "fuente única", añadir `"corantioquia"` al conjunto de claves y al
  comentario. **Los conteos se suben sobre lo que haya en `master` al
  implementar**: la rama de la CDMB ya los lleva a 32 familias /
  `1 + 28 + 29 + 33 + 6`, y hay otras tres fuentes diseñándose a la vez
  (Cámara de Comercio de Armenia, Cámara de Comercio de Bogotá,
  Corporinoquia).
- `docs/guia-despliegue-sistemas.md` — ficha de la fuente (paso 7).

Sin migración Alembic. En producción: `python -m core.seed` una vez.

## Pruebas

`tests/families/test_corantioquia.py`, con fragmentos reales del JSON y
`responses`, sin internet:

1. Parseo del radicado → `040-RES2610-3892` da `R_CORANT_3892_2026`;
   `160TH-RES2501-80` da `R_CORANT_0080_2025`; `180-ACU2610-84` da
   `A_CORANT_0084_2026`; oficina de tres letras (`160SAE-RES2412-5845`) cumple
   el patrón.
2. Fecha del boletín desde `nombre` y fecha del acto desde `fechaRadicacion`
   (meses en español con mayúscula: "09 de Octubre de 2026").
3. Un documento → `tipo`, `f_public` (boletín), `f_providencia` (acto),
   `detalle`, `link` (con `verify` según la opción de TLS elegida),
   `save_path`.
4. Índice: sólo se piden boletines con fecha en `[fini, ffin]`; con
   `fini=2023-01-01` no se pide ninguno anterior a 2025.
5. Paginación: página llena de 15 → se pide la 2; página con menos de 15 o
   `"boletines": {}` → se detiene.
6. Filtro por tipo: autos, notificaciones y edictos no entran.
7. Piso: acto de 2023 publicado en un boletín de 2026 → descartado.
8. Acto de 2025 publicado meses después → entra con `f_public` del boletín.
9. Radicado fuera del patrón con fecha ≥ 2025 → título saneado y aviso.
10. `subtipo` ausente → no rompe.
11. Fecha ilegible → descartado con aviso.
12. Dedup por `doc`.
13. `stop_event` activado → corta y devuelve lo acumulado.
14. Falla del índice (500) → aviso y lista vacía; falla de un boletín → aviso
    y sigue con el siguiente.
15. `limit` respetado.

En `tests/test_downloader.py`:

16. Respuesta `Content-Type: text/plain` con
    `Content-Disposition: attachment; filename=2483007.pdf` → se guarda con
    `content_type = "application/pdf"` y extensión `.pdf`.
17. `text/plain` con un `.txt` (o sin extensión mapeada) → queda
    `text/plain`.
18. Un tipo real (`application/pdf`, `application/msword`) pasa intacto
    (regresión del caso Superfinanciera).

Se corren dirigidas: `pytest tests/families/test_corantioquia.py tests/test_downloader.py tests/test_seed.py`.

## Riesgos y notas

- **Volumen alto y de trámite:** ~2.600 resoluciones al año, casi todas
  permisos individuales. Ocupa almacenamiento y puede no ser lo que el cliente
  espera de "normativa interna".
- **El boletín es la vista pública de un sistema de trámites.** Si la
  corporación cambia e-SIRENA, la corrida dará 0 documentos o error del
  índice.
- **TLS roto en el servidor** (falta el intermedio). Si lo arreglan, la
  opción A sigue funcionando y la B también.
- **Sin `ETag`:** la republicación sólo se detecta si cambia el tamaño.
- El `Content-Type` del PDF es `text/plain`; lo corrige el descargador (ver
  "Descargador"). Verificar en la corrida real que el documento guardado
  quede `application/pdf` y abra la vista previa.

## Decisiones (2026-10-26)

1. **Alcance:** como en la CDMB — sólo resoluciones y acuerdos. Sin autos,
   edictos ni notificaciones por aviso.
2. **Resoluciones:** todas, sin filtrar por subtipo ni dependencia (el
   criterio queda en manos de la entidad).
3. **Piso:** 2025.
4. **Sigla:** `CORANT`.
5. **TLS:** opción A (`verify=False` sólo para `*.corantioquia.gov.co`, como
   `snr`).
6. **Vista previa (2026-10-29):** los PDF llegan como `text/plain`; se
   arregla en el descargador (`text/plain` + extensión conocida → tipo por
   extensión), no en la familia.
