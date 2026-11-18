# CSJ — migración al buscador "Ojeador" — diseño

**Fecha:** 2026-11-18
**Fuente:** Corte Suprema de Justicia (familia existente `corte_suprema`, fuente `CSJ`)
**Estado:** pendiente de aprobación del administrador — **no implementar todavía** (decisiones del 2026-11-18 incorporadas)

## Por qué

El buscador que usa hoy la familia (`consultaprovidenciasbk.cortesuprema.gov.co/api`,
GraphQL) dejó de recibir providencias: lo último es del 30-04-2026 en
Civil/Laboral y de julio en Penal (ver `project_csj_index_stale`, octubre
2026). La Corte lo reemplazó por **Ojeador** (`https://ojeador.cortesuprema.gov.co`),
que sí está al día. Producción tiene hoy **186** providencias de la CSJ; el
índice nuevo tiene **32.977** sólo de 2026.

**Objetivo:** que la fuente `CSJ` vuelva a traer todo lo que la Corte publica,
desde el buscador nuevo, sin cambiar nada de lo que el administrador ve
(nombre de la fuente, títulos, carpetas, marca automática de "útil"), y
recuperar **todo 2026**.

**No objetivos:** años anteriores a 2026 (se puede hacer después con la misma
familia); usar el texto, temas o resúmenes que trae Ojeador; buscar por
palabras.

**Anti-objetivos (sería un fracaso aunque funcione):** duplicar las 186
providencias que ya están en producción; cambiar el formato de títulos o
carpetas de la CSJ; dejar el índice viejo consultándose en paralelo.

## Enfoques considerados

1. **Reescribir la familia `corte_suprema` sobre el buscador nuevo — ELEGIDO**
   (recomendación de Claude; el administrador no pidió otro). Misma fuente
   `CSJ`, mismos títulos/carpetas/`auto_review_status`, más un script único
   que actualiza la identidad de las providencias ya guardadas.
2. Familia nueva `csj_ojeador` y desactivar la vieja: más fácil de revertir,
   pero parte la CSJ en dos fuentes en filtros, reportes y aviso de salud, y
   el problema de duplicados es el mismo.
3. Mantener ambos índices: descartado, el viejo ya no se alimenta y sólo
   traería duplicados.

## El sitio nuevo (verificado 2026-11-18)

- Ojeador es una app Next.js; el navegador consulta un servicio aparte,
  **`https://buscadorjurisprudenciabackend.cortesuprema.gov.co`**. Público:
  sin credenciales, sin cookies, sin WAF, TLS válido (sin `verify=False`).
- **Búsqueda:** `GET /search/` con parámetros
  `query_text=""`, `orden=recientes`, `limit` (**máx. 100**; 500 → 422),
  `page` (desde 1), `fechaInicio` / `fechaFin` (`AAAA-MM-DD`), opcional
  `especialidad` (`CIVIL`, `LABORAL`, `PENAL`, `PLENA`).
  - El filtro de fechas se aplica sobre `FechaConsolidacionFirma` y se
    respeta (probado: 200 resultados de octubre, todos en octubre).
  - Orden `recientes` = `FechaConsolidacionFirma` descendente; páginas sin
    solapamiento.
  - **Ventana máxima: `page * limit ≤ 10.000`** (más allá → 400 "La ventana
    de resultados no puede superar 10000 documentos… acote la búsqueda").
  - Respuesta: `numFound`, `paginable_documents`, `returned`, `docs[]`,
    `facets`.
- **Campos útiles de cada `doc`:**

  | Campo | Ejemplo |
  |---|---|
  | `id` | `"1171961"` |
  | `Nombre` | `AC7263-2026 [2026-03319-00]` |
  | `Numerador` | `AC7263-2026` |
  | `CUI` | `11001020300020260331900` |
  | `FechaConsolidacionFirma` | `2026-11-06` |
  | `Especialidad` | `CIVIL` / `LABORAL` / `PENAL` / `PLENA` |
  | `Sala` | igual que `Especialidad` (también en tutelas: la sala que resolvió) |
  | `TipoDeProvidencia` | `AUTO`, `SENTENCIA`, `SENTENCIA TUTELA`, `AUTO TUTELA`, `CONCEPTO EXTRADICCION`, `AUTOHABEAS`, `CONCEPTO`, `OTROS`/`Otros` |
  | `ClaseActuacion` | `RECURSO DE CASACIÓN`, `CONFLICTO`, `ACCIÓN DE TUTELA - SEGUNDA INSTANCIA`… |
  | `Ponente` | `DR FERNANDO AUGUSTO JIMÉNEZ VALDERRAMA` |
  | `Ubicacion` | `SALAS/CIVIL/2026/Dr. …/11.- Noviembre/Autos/AC7263-2026 [2026-03319-00].docx` |

  Tutelas: `Ubicacion` = `SALAS/TUTELAS/PENA/2026/…`, `Sala` = `PENAL`.
  Sala Plena: `SALAS/PLENA/2026/Autos/APL6636-2026.docx`.
- **Descarga:** `GET /document/descargar?path=<Ubicacion>` → `200`,
  `Content-Type: application/pdf`,
  `Content-Disposition: attachment; filename="AC7263-2026 [2026-03319-00].pdf"`.
  Aunque `Ubicacion` termine en `.docx`, el servicio entrega **PDF**. Mediana
  ~240 KB por archivo. `HEAD` responde **405** → no hay revisión barata de
  republicación.
- **Búsqueda por código:** `query_text=AC2794-2026` devuelve esa providencia
  (y alguna otra que la menciona); hay que quedarse con la de `Numerador`
  exacto.
- **Frescura (2026-11-18):** lo más reciente es del 06-11 (Civil), 05-11
  (Laboral), 22-10 (Penal y Plena): la Corte publica con 2 a 4 semanas de
  retraso respecto a la fecha de firma.
- **Volumen 2026:** 32.977 (Civil 11.861, Penal 10.837, Laboral 9.713,
  Plena 566); ~1.800 en octubre (todas las salas). Tipos: 18.838 sentencias
  de tutela, 9.392 autos, 2.750 autos de tutela, 1.583 sentencias, 234
  conceptos de extradición, 137 autos de habeas, 36 conceptos, 7 otros.

## Diseño

### Recorrido

- Para el rango `[fini, ffin]` pedido, se parte en **meses calendario**
  (el primero y el último recortados al rango). Por cada tramo:
  `GET /search/?query_text=&orden=recientes&limit=100&page=p&fechaInicio=…&fechaFin=…`
  sin filtro de especialidad, `p = 1, 2, …` hasta `returned < 100` o
  `page * 100 ≥ numFound`.
- Si un tramo trae `numFound > 10.000` (no pasa hoy: el mes más grande ronda
  ~4.000), se vuelve a partir **por día**; si un solo día pasara de 10.000, se
  parte además por `especialidad` y, si aún así no cabe, se avisa por
  `on_progress` que el día quedó incompleto. Decisión de Claude.
- Reintentos como hoy (`_MAX_INTENTOS = 3`, 5 s): 5xx, error de conexión o
  respuesta que no es JSON se reintentan; un 4xx corta ese tramo con aviso
  "el sitio pudo haber cambiado".
- `limit` del `scrap()`: por defecto **sin tope práctico** (≥ 40.000) para
  que la corrida de recuperación de 2026 no se corte; se respeta si el
  llamador pasa uno menor.
- `stop_event` se revisa entre páginas.

### Filtro y fechas

- `f_public = f_providencia = FechaConsolidacionFirma` (AAAA-MM-DD). Ya no se
  usa `fechaCreacion` ni la conversión a hora de Colombia (la fecha nueva no
  trae hora).
- El filtro lo hace el servidor; se re-verifica en el cliente que la fecha
  esté en `[fini, ffin]` (descarta con aviso si no).
- `filters_by_publication_date` sigue en `False`. Decisión de Claude: la
  fecha de firma es la fecha de la providencia.
- **`scheduled_min_lookback_days = 45`**: la Corte publica con 2-4 semanas de
  retraso; la corrida diaria mira 45 días atrás. Lo ya guardado se descarta
  por `doc_id` antes de descargar.

### Título, tipo, sala y carpeta

Se conserva todo el formato actual (PR #71: "CSJ = código a secas").

- **Título:** `_codigo_from_titulo(Nombre)` con el `_CODIGO_RE` actual
  (`AC7263-2026 [2026-03319-00]`, `STP21139-2026`). Si no calza, se prueba
  `Numerador`; si tampoco, `title = Nombre` saneado con `_<año>` de desempate,
  `title_unverified=True` y se mantiene `resolve_unverified_document`
  (lee la primera página del PDF).
- **Tipo** (`TipoDeProvidencia` → `tipo`):

  | Ojeador | tipo |
  |---|---|
  | `AUTO`, `AUTO TUTELA`, `AUTOHABEAS` | `Auto` |
  | `SENTENCIA`, `SENTENCIA TUTELA` | `Sentencia` |
  | `CONCEPTO`, `CONCEPTO EXTRADICCION` | `Concepto` |
  | otro / vacío | `_tipo_from_titulo(código)` o `Desconocido` |

- **especialidad:** `Tutela` si `TipoDeProvidencia` contiene `TUTELA` (o
  `Ubicacion` contiene `/TUTELAS/`); si no, `Civil` / `Laboral` / `Penal` /
  `Plena` según `Especialidad`.
- **seccion:** `Sala de Casación Civil|Laboral|Penal` según `Sala`; **`Sala Plena`**
  para `PLENA`.
- **Carpeta (bucket):** `SCC` / `SCL` / `SCP` según `Sala` (las tutelas van a
  la sala que las resolvió, como hoy) y **`SPL`** para Sala Plena (nuevo).
  `save_path = storage_path("CSJ", bucket, f"{safe_titulo}(extension)")`, igual
  que hoy.
- Se elimina la deduplicación pdf/docx (Ojeador trae una sola entrada por
  providencia). Se deduplica dentro de la corrida por `id` de Ojeador.

### Enlace y descarga

- `link = {"url": "https://buscadorjurisprudenciabackend.cortesuprema.gov.co/document/descargar?path=<Ubicacion codificada>", "method": "GET"}`.
  El `doc_id` sale de esa URL + `f_public` (comportamiento por defecto).
- `checks_for_republication = False` (el `HEAD` da 405), como hoy.
- El descargador ya toma `.pdf` del `Content-Disposition`. Sin cambios en
  `core/downloader.py`.

### Lo que se borra

`_CORTE_SUPREMA_URL`, `_DOWNLOAD_URL`, la consulta GraphQL, `self.tipos`,
`_especialidad_from_online_path`, `_seccion_from_online_path`,
`_bucket_real` y la nota sobre "ambas URLs apuntan a un mismo servidor caído".
Se conservan `_CODIGO_RE` (lo importa `core/backfill_csj_titles.py`),
`_codigo_from_titulo`, `_codigo_desde_texto`, `_tipo_from_titulo`,
`_extraer_texto_primera_pagina` y `resolve_unverified_document`.

## Las providencias que ya están guardadas

Las 186 de producción (y las de desarrollo) tienen `doc_id` calculado con la
ruta vieja (`/var/www/html/Index/CIVIL/…`, POST). Con la URL nueva el worker
no las reconocería y las bajaría otra vez con sufijo `-v2`.

**Script único `core/backfill_csj_ojeador.py`** (mismo estilo que los
`backfill_*` existentes: idempotente, `--simular` por defecto o flag
explícito, resumen al final):

1. Toma los documentos de la fuente `CSJ` cuyo `source_url` todavía es el
   del host viejo (`https://consultaprovidenciasbk.cortesuprema.gov.co/downloadFile/`;
   el worker guarda sólo `link["url"]`, así que hoy todas las CSJ comparten
   ese mismo valor).
2. Para cada uno, saca el código del título (`_codigo_from_titulo`) y busca
   en Ojeador `query_text=<código>`, quedándose con los resultados de
   `Numerador` exacto. Desempate: el de `Nombre` igual al título guardado;
   si sigue habiendo más de uno, es ambiguo. (No se puede comparar fechas: lo
   guardado tiene `fechaCreacion`, no la fecha de firma.) Títulos sin código
   reconocible (relleno `doc_2025`) → "sin coincidencia".
3. Si hay **una** coincidencia: arma el `RawDocModel` que produciría el
   scraper nuevo para ese resultado y actualiza `doc_id` (con
   `compute_doc_id`), `source_url` y `f_public`/`f_providencia` (pasan de
   `fechaCreacion` a la fecha de firma), **sin tocar el archivo ni su
   `storage_key`** (la carpeta de la CSJ no lleva fecha).
4. Si no hay coincidencia o hay ambigüedad: no toca nada y lo lista en el
   resumen.

Se corre **una vez en producción, después de desplegar y antes de la
corrida de recuperación**, en dos pasos:

- **Primero `--simular`**: no cambia nada y lista cuántas reconoce, cuáles no
  y cuáles son ambiguas. Si queda alguna sin reconocer, el administrador
  decide con esa lista (dejarla y aceptar el duplicado, o borrarla) **antes**
  de la recuperación; el script no borra nada por su cuenta. Decisión de
  Claude.
- Luego la corrida real.

**Pendiente de confirmar antes de la corrida real (decisión del
administrador, 2026-11-18):** el script cambia el `doc_id` (identificador
interno, expuesto por la API) de las providencias ya guardadas; el archivo,
el título y la carpeta no cambian. El administrador no sabe si RedJurista,
BDU o JurIA reconocen documentos por ese identificador: hay que confirmarlo
con quien maneja esos productos. Si dependen de él, esas ~186 providencias
les aparecerían como nuevas.

**Ventana de riesgo:** entre el despliegue y el script, la corrida diaria
(45 días atrás) no toca providencias viejas (todas las guardadas son de
abril o antes en Civil/Laboral y de julio o antes en Penal), así que no
genera duplicados; aun así, conviene correr el script el mismo día del
despliegue.

## Recuperación de 2026

**Alcance decidido por el administrador:** todo 2026 (2026-01-01 a hoy).

- **Por meses, uno a la vez** (~3.000 providencias y ~700 MB cada mes):
  corridas manuales de la CSJ de un mes calendario, lanzadas después de la
  corrida diaria para no frenar a las demás fuentes (el worker lista todo el
  rango antes de descargar y no corta por `limit`). Si una falla a mitad, se
  repite ese mes; lo ya guardado se salta solo. Decisión de Claude.
- **Antes de empezar:** comprobar en el servidor que hay espacio libre para
  ~8 GB (33.000 PDF × ~240 KB); la guía de despliegue trae el comando.
- **Tiempo:** dominado por una descarga por providencia; se mide en la
  corrida local de octubre y se anota en la guía para planear los meses.

**Todas entran como "útil"** (opción elegida por el administrador el
2026-11-18, igual que hoy: la fuente ya tiene `auto_review_status = useful`
en producción), incluidas las ~19.000 sentencias de tutela, los autos de
tutela y los de habeas corpus. Sin filtro por tipo.

## Integración

**Archivos que cambian:**
- `core/scrapers/families/corte_suprema.py` — reescritura descrita arriba.
- `tests/families/test_corte_suprema.py` — se reemplazan las pruebas del
  GraphQL por las del servicio nuevo (con `responses`, sin internet).
- `core/backfill_csj_ojeador.py` + `tests/test_backfill_csj_ojeador.py` — nuevos.
- `docs/guia-despliegue-sistemas.md` — ficha de la CSJ y pasos de despliegue
  (script + corrida de recuperación).

Sin migración Alembic, sin `core.seed` (la fuente ya existe), sin cambios en
el descargador.

## Pruebas

1. Recorrido: un mes con 230 resultados → 3 páginas (100, 100, 30) y para.
2. Partición por meses: `2026-01-15 → 2026-03-10` pide 3 tramos con las
   fechas correctas.
3. Tramo con `numFound > 10.000` → se parte por días.
4. 400 de "ventana de resultados" o cualquier 4xx → aviso y sigue con el
   siguiente tramo; 5xx → reintenta 3 veces.
5. Documento completo: título, `tipo`, `especialidad`, `seccion`, carpeta,
   `f_public`, `link` (con `Ubicacion` codificada: espacios, tildes, `[ ]`).
6. Tutela de la Sala Penal → `especialidad="Tutela"`, carpeta `SCP`.
7. Sala Plena → `seccion="Sala Plena"`, carpeta `SPL`.
8. Tabla de tipos completa, incluido `AUTOHABEAS` y `OTROS`.
9. Título sin código reconocible → `title_unverified=True` y desempate con año.
10. Fecha fuera del rango pedido → descartada.
11. Dedup por `id`; `stop_event`; `limit`.
12. `scheduled_min_lookback_days == 45`, `checks_for_republication is False`.
13. Script: coincidencia única → actualiza `doc_id`/enlace sin tocar el
    archivo; varias o ninguna → no toca y reporta; segunda corrida → 0
    cambios.

Corridas dirigidas: `pytest tests/families/test_corte_suprema.py tests/test_backfill_csj_ojeador.py tests/test_backfill_csj_titles.py`.

## Validación antes de entregar

- Corrida real local de **octubre 2026** completa (las 4 salas): número de
  providencias = `numFound` del sitio, todas descargadas como PDF, títulos sin
  `title_unverified` salvo casos raros, carpetas `SCC/SCL/SCP/SPL`.
- Segunda corrida del mismo mes → 0 descargas nuevas.
- Script sobre la base local con providencias viejas → todas reconocidas.
- Medir el tiempo por descarga para estimar la recuperación de 2026.

## Decisiones (2026-11-18)

Del administrador:
1. **Enfoque:** reescribir la familia `corte_suprema` (recomendado por Claude; no se pidió otro).
2. **Recuperación:** todo 2026.
3. **"Útil":** todo lo de la CSJ entra como útil, también tutelas y habeas.
4. **Identificador interno:** no se sabe si otros productos lo usan → confirmar antes del script.

De Claude (corregibles):
5. Sala Plena incluida, carpeta `SPL`.
6. `scheduled_min_lookback_days = 45`.
7. Partición por meses, con días como respaldo si un tramo pasa de 10.000.
8. Script con `--simular` primero; nada se borra sin decisión del administrador.
9. Recuperación mes a mes, después de la corrida diaria, con chequeo de espacio.

## Riesgos

- **Volumen de la recuperación** (~33.000 documentos, ~8 GB): espacio en
  MinIO del servidor y horas de corrida. Hacerla por tramos.
- **Servicio nuevo sin documentación pública:** si la Corte cambia
  parámetros, la búsqueda dará 4xx; el aviso de salud de fuentes lo
  detecta.
- **Retraso de publicación** mayor a 45 días en alguna sala: se perdería
  hasta una corrida manual. El aviso de salud ayuda a verlo.
- **Archivos que el servicio no convierta a PDF:** el descargador guarda lo
  que llegue (`.docx`) y la verificación de tipo de archivo lo acepta.
