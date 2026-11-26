# Fuente Función Pública (Gestor Normativo) — diseño

**Fecha:** 2026-11-23
**Entidad:** Departamento Administrativo de la Función Pública (`funcion_publica`, sigla propuesta `DAFP`)
**Estado:** pendiente de aprobación del administrador. No se programa nada
hasta que se apruebe.

> El enlace que dio el usuario
> (`https://www.funcionpublica.gov.co/eva/gestornormativo/consulta_avanzada.php`)
> es sólo el **formulario** de la consulta avanzada del Gestor Normativo. El
> formulario no envía nada: un JavaScript llama a
> `gestion/funphp/funajax.php?t=ejecuta_busqueda_avanzada2&…` y pinta la
> respuesta. Ese endpoint es el listado real que usa la familia.
>
> El Gestor Normativo es una **compilación de normas de todo el Estado**
> (leyes, sentencias, decretos de todos los ministerios…). Esta familia se
> limita a lo que **expide la propia Función Pública** (filtro
> `entidad1=88`, "Departamento Administrativo de la Función Pública"). Ver
> pregunta 1.

## Objetivo

Familia de scraper nueva `funcion_publica`, desde **2015**, con las normas
que expide la Función Pública. Propuesta (a confirmar, pregunta 2):

| Sección (tipo del Gestor) | `tipodoc` | tipo asignado | título |
|---|---|---|---|
| Concepto | 7 | `Concepto` | `CTO_DAFP_{número}_{año}` |
| Concepto Marco | 785 | `Concepto` | `CTO_DAFP_{número}_{año}` |
| CONCEPTOS GUIAS | 1305 | `Concepto` | `CTO_DAFP_{número}_{año}` |
| Decreto / Decretos Salariales | 11 / 987 | `Decreto` | `D{número:04}{año:03}` (regla común de `core/naming.py`) |
| Resolución | 29 | `Resolución` | `R_DAFP_{número}_{año}` |
| Circular | 6 | `Circular` | `C_DAFP_{número}_{año}` |
| Circular Externa | 825 | `Circular` | `CE_DAFP_{número}_{año}` |
| Circular Conjunta | 184 | `Circular` | `CJ_DAFP_{número}_{año}` |
| Circular Unificada | 845 | `Circular` | `CU_DAFP_{número}_{año}` (prefijo nuevo, ver pregunta 3) |

Se dejan **fuera** aunque vengan con `entidad1=88`: Ley, Sentencia,
Comunicado y Documento de Relatoría (son normas de otras autoridades o
piezas de divulgación que el Gestor asocia a la Función Pública; 1-17 por
año).

Familia **plana**: sin actuaciones, sin anexos, sin `family_params`.

## Construcción del sitio

- PHP propio ("EVA - Gestor Normativo"), HTML servido en el servidor. Sin
  WAF, sin captcha. Pone una cookie `cookiesession1` (balanceador) que no hace
  falta enviar. UTF-8.
- **Certificado TLS roto:** el servidor envía como intermedio el de Sectigo,
  pero su certificado lo firma Let's Encrypt `YR1` (raíz `ISRG Root YR`).
  `requests` falla con `SSLError` (`certifi` no trae esa raíz todavía).
  Con la cadena correcta (intermedio bajado de `http://yr1.i.lencr.org/`) el
  certificado es válido, así que es un error de configuración del sitio,
  no un ataque. Se usa **`verify=False` sólo para `www.funcionpublica.gov.co`**
  (sesión del scraper y `link["verify"] = False`), documentado en el código y
  en la guía, como `ssf`, `snr` y `supersolidaria`.

### Listado por año (lo que usa la familia)

`GET /eva/gestornormativo/gestion/funphp/funajax.php?t=ejecuta_busqueda_avanzada2&entidad1=88&ano=<año>&pagina=1`

- Devuelve **todo el año en una sola respuesta** (no pagina de verdad pese
  al parámetro `pagina`): "Número de documentos encontrados: N" y N enlaces.
  2021 → 6.192 filas, 4 MB, 2,7 s. Se puede agregar `&tipdoc=<id>` para pedir
  un solo tipo (se usa uno por tipo para no bajar Leyes/Sentencias).
- Cada resultado:

  ```html
  <a href="norma.php?i=276776" target="_blank" class="list-group-item list-group-item-action">
    <h5 class="list-group-item-heading">Concepto 138331 de 2026</h5>
    <p class="list-group-item-text">Función Pública precisó que los empleados públicos del nivel territorial…</p>
  </a>
  ```

| Dato | De dónde |
|---|---|
| id de la norma | `i` del `href` (`norma.php?i=<id>`) |
| tipo, número y año | `h5`: `<Tipo> <número> de <año>` |
| epígrafe | `p.list-group-item-text` |
| fecha | **no está en el listado**: hay que abrir el detalle |

- El listado **no** viene ordenado (ni por fecha ni por id).

### Detalle

`GET /eva/gestornormativo/norma.php?i=<id>` (0,64 s de mediana):

```
Concepto 138331 de 2026 Departamento Administrativo de la Función Pública
Descargar PDF                      ← <a href="norma_pdf.php?i=276776">
Fechas
Fecha de Expedición: 15 de abril de 2026
Fecha de Entrada en Vigencia: 15 de abril de 2026
Medio de Publicación:
Temas (1) …
```

Se leen "Fecha de Expedición" y "Fecha de Entrada en Vigencia" con
`core/fecha_es.py` (la segunda sólo como respaldo, ver Fechas y filtro). No
hay fecha de publicación en el Gestor.

### Descarga

`GET /eva/gestornormativo/norma_pdf.php?i=<id>` → `200`,
`Content-Type: application/pdf`,
`Content-disposition: inline; filename="Concepto_138331_de_2026_Departamento_Administrativo_de_la_Función_Pública.pdf"`.

- El PDF **se genera en cada petición** a partir del HTML de la norma (no es
  el oficio original escaneado). Trae dos bytes (`\t\n`) antes de `%PDF-`;
  `core/verificacion_archivos.py` ya lo acepta (busca la firma en el primer
  KB).
- `Last-Modified` es siempre "ahora" y el tamaño **cambia unos bytes entre
  dos descargas** (84.286 vs 84.288 B, la fecha de generación va dentro). La
  revisión de republicación por `Content-Length` daría falsos positivos todos
  los días → **`checks_for_republication = False`**.
- La URL (`norma_pdf.php?i=<id>`) es estable y única por norma: es **la**
  identidad del documento. **`doc_id_uses_publication_date = False`**
  (`doc_id` = sólo la URL, como `minsalud`, `procuraduria` e `icbf`). La
  fecha no puede entrar en el `doc_id` porque aquí es un dato que la familia
  **corrige** (ver Fechas y filtro) a partir de fechas que el sitio tiene mal:
  si la Función Pública arregla una fecha (el 31-12-1969 de la 753262, por
  ejemplo) o cambia la regla de corrección, con la fecha dentro el mismo
  concepto se bajaría otra vez como documento nuevo.

### Otro índice que se descartó

`/dafpIndexerBGN/norma/index?…&filtroEntidad=…&ordenarPor=FECHA_EXPEDICION&offset=&max=`
(buscador tipo Solr) ordena por fecha de expedición descendente, pero
tampoco trae la fecha en el resultado, tarda 15 s por página de 100 y, por
el retraso de carga (abajo), ordenar por expedición no ahorra nada. Se
documenta por si el listado por año deja de funcionar.

## Fechas y filtro

Hallazgos de la revisión de las 268 normas de 2026 (detalle por detalle):

1. **Se cargan con meses de retraso y en tandas.** Entre las últimas
   cargadas (ids 279xxx) hay conceptos expedidos en enero de 2026. No hay
   fecha de carga para filtrar por publicación.
2. **La fecha de expedición tiene errores:** 14 de 268 tienen un año que no
   es el del título (`Concepto 588851 de 2026` con expedición 2024-09-29;
   `Concepto 610931 de 2025` con expedición 29-12-**2026**, en el futuro;
   `Concepto 753262 de 2026` con 31-12-1969, fecha vacía).

Propuesta:

- `f_public = f_providencia` se elige en este orden (el año del título es el
  dato más fiable: lo confirman el número de radicado y el nombre del PDF):
  1. **Fecha de Expedición**, si se puede leer, su año coincide con el año
     del título y no está en el futuro.
  2. Si no, **Fecha de Entrada en Vigencia**, con las mismas tres
     condiciones. Caso real (revisión del 2026-11-26): `Concepto 753262 de
     2026` trae expedición 31-12-1969 (fecha vacía) pero vigencia
     **06-01-2026**, que sí sirve.
  3. Si tampoco, `"<año del título>-01-01"`.

  En los casos 2 y 3 se avisa por `on_progress` con las fechas que traía el
  sitio y la que se usó. Así baja el ~5 % de normas que quedaban en 1 de
  enero (cuántas exactamente se mide en la corrida real).
- **Filtro:** entra la norma si su fecha (ya corregida) cae en `[fini, ffin]`.
- **Piso:** `_ANIO_MINIMO = 2015` (por año del título).
- **Años pedidos:** `max(fini.año, 2015) … ffin.año`. Sólo se abren los
  detalles de las filas de esos años.
- **Corrida diaria:** por el retraso de carga, una ventana de 3 días perdería
  casi todo. `scheduled_min_lookback_days = 400` → la diaria pide el año en
  curso y el anterior y abre el detalle de cada norma de esos dos años
  (hoy 268 + 221 ≈ 490 detalles ≈ 5-6 min). Lo ya guardado no se vuelve a
  bajar (el worker deduplica por `doc_id`, que aquí es sólo la URL).
- **Salud de fuentes:** las tandas de carga pueden dejar semanas sin nada
  nuevo; `alerta_margen_dias` se fija tras la corrida real.

## Número y nombre canónico

- Regex sobre el `h5`: `^\s*(?P<tipo>.+?)\s+(?P<num>[\w.\-]+)\s+de\s+(?P<anio>\d{4})\s*$`.
- **Regla general (decisión del administrador, 2026-11-26, común a ADRES,
  DPS y Función Pública):** el número se copia **tal cual lo escribe la
  entidad**, sin quitar ni poner ceros.
- **Conceptos:** el número del Gestor ya viene con 6 cifras (`000511`,
  `138331`; son los últimos dígitos del radicado `20264000138331`). Se
  conserva tal cual: `CTO_DAFP_138331_2026`, `CTO_DAFP_000511_2026`.
- **Circulares** con número compuesto (`100-011`, `100001`, `01`): se
  conserva tal cual, sin rellenar: `CE_DAFP_100-011_2026`,
  `CJ_DAFP_01_2026`.
- **Resoluciones:** también tal cual, sin rellenar (la primera versión
  proponía relleno a 4): `Resolución 035 de 2020` → `R_DAFP_035_2020`,
  `Resolución 177 de 2020` → `R_DAFP_177_2020`.
- **Decretos:** `codigo_ley_decreto("D", número, año)` → `D1384026`. Es la
  única excepción a "tal cual": el código común de `core/naming.py` rellena
  a 4 a propósito, para reconocer el mismo decreto en varias fuentes. **Hoy
  ese reconocimiento es de un solo sentido** (el chequeo del worker sólo mira
  las familias de `_MINISTERIO_FAMILIES`, y `funcion_publica` no está ahí; no
  existe una familia de Presidencia). Con el cambio aprobado por el
  administrador el 2026-11-26 (ver Integración) funciona en todos los
  sentidos entre ministerios, `dps` y `funcion_publica`.
- Espacios dobles o tabulador antes de "de" (16 casos, `Concepto 050101  de 2026`)
  son normales: la regex usa `\s+`.
- `h5` raro (hoy 4 desde 2015: `Concepto 451981* de 2024`,
  `Concepto ¿248691 de 2023`, `Concepto C-197 de 2025`, `Concepto  de 2021`
  sin número): se limpia el número (letras, dígitos y `-`); sin número →
  `CTO_DAFP_SN-<id>_<año>`; siempre `title_unverified=True` + aviso.
- `detalle` = epígrafe del listado.

## Recorrido

1. Para cada año pedido y cada `tipodoc` de la tabla: un `GET` al listado.
2. Dedup por `id` (un mismo `i` no se repite hoy, pero se protege).
3. Para cada fila: `GET` del detalle → fecha de expedición (y se comprueba
   que tenga el enlace `norma_pdf.php`; si no, se omite con aviso).
4. Filtro de fecha → `RawDocModel` con
   `link={"url": ".../norma_pdf.php?i=<id>", "method": "GET", "verify": False}`.
5. Pausa corta entre detalles (0,3 s) para no cargar el servidor.

## Volumen esperado (`entidad1=88`, todas las clases)

| Año | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Total | 455 | 433 | 76 | 33 | 2.119 | 3.188 | 6.192 | 4.620 | 3.592 | 2.201 | 221 | 268 |
| de ellos Concepto | 423 | 413 | 58 | 28 | 2.106 | 3.176 | 6.172 | 4.606 | 3.562 | 2.183 | 193 | 228 |

Corrida completa desde 2015: **~23.300 documentos** (99 % conceptos).
Costo: 23.300 detalles (≈ 0,65 s) + 23.300 PDF (≈ 1,5 s) ≈ **14 horas**.
Se recomienda lanzarla por tramos de años desde el frontend.

2017-2018 tienen pocos conceptos y 2025 cae a 221: es lo que hay cargado en el
Gestor, no un error de la familia (puede ser el retraso de carga).

## Fuera de alcance (v1)

- Normas de otras entidades que compila el Gestor (leyes, sentencias,
  decretos de ministerios…).
- Ley, Sentencia, Comunicado y Documento de Relatoría con `entidad1=88`.
- Las demás "entidades" Función Pública del selector (`3802` CNSC-DAFP,
  `3822` Vicepresidencia-DAFP, `4041` Unidad Acuerdo de Paz, `4123`
  DAPRE-DAFP): conjuntas o de otra entidad. Ver pregunta 1.
- El oficio original firmado: el Gestor sólo da el PDF generado.
- Antes de 2015.

## Integración

**Archivos nuevos:** `core/scrapers/families/funcion_publica.py`
(`@register_family("funcion_publica")`), `tests/families/test_funcion_publica.py`.

**Archivos que se tocan:** `core/scrapers/families/__init__.py`,
`core/seed.py` (`_SOURCE = "Departamento Administrativo de la Función Pública"`,
`family_params={}`), `tests/test_seed.py` (conteos), y la ficha en
`docs/guia-despliegue-sistemas.md`. Si se aprueba `CU`, nada más: el prefijo
sólo vive en el título.

**Cambio fuera de la familia (aprobado por el administrador el 2026-11-26):
dedup de decretos en todos los sentidos.**

- `core/db/repository.py`: `list_ministerio_documents_by_title` (el chequeo
  que usa `worker/tasks.py:418` antes de bajar un `D…`/`L…`) pasa a buscar
  también en las familias `dps` y `funcion_publica`. Se hace con un conjunto
  propio para este chequeo, p. ej.
  `_FAMILIAS_DEDUP_LEY_DECRETO = _MINISTERIO_FAMILIES | {"dps", "funcion_publica"}`,
  **sin** meterlas en `_MINISTERIO_FAMILIES`: ese conjunto también lo usan
  `core/backfill_leyes_decretos.py` y `core/backfill_directiva_prefix.py`,
  que renombran títulos de ministerios y no deben tocar estas dos fuentes si
  se vuelven a correr. Se actualiza el docstring de la función.
- `tests/test_tasks.py`: prueba nueva junto a
  `test_scrape_source_task_skips_a_ley_already_published_by_another_ministerio`:
  un decreto `D…` que ya está guardado en `funcion_publica` no se vuelve a
  bajar desde una fuente de ministerio ni desde `dps`, y al revés. Es el
  mismo cambio que pide el diseño de `dps`; si los dos se programan por
  separado, el que llegue primero agrega las dos familias y la prueba.
- Gana el que ya está guardado (regla de siempre, ver
  `2026-09-03-formato-leyes-decretos-ministerios`). Hoy no hay cruce entre
  los decretos 2026 de `dps` (5) y los de `funcion_publica` (27), pero puede
  haberlo en otros años.

Sin migración Alembic. En producción: `python -m core.seed` una vez.

## Pruebas

`tests/families/test_funcion_publica.py`, con fragmentos reales y `responses`:

1. `h5` → título por tipo: `Concepto 138331 de 2026` → `CTO_DAFP_138331_2026`;
   `Decreto 1384 de 2026` → `D1384026`; `Circular Externa 100-011 de 2026` →
   `CE_DAFP_100-011_2026`; `Concepto 000511 de 2026` → `CTO_DAFP_000511_2026`;
   `Resolución 035 de 2020` → `R_DAFP_035_2020` (número tal cual, sin
   rellenar).
2. `h5` raro (`451981*`, `¿248691`, `C-197`, sin número) → título limpio,
   `title_unverified=True`, aviso.
3. Parseo del listado (id, `h5`, epígrafe).
4. Parseo del detalle → fecha de expedición y enlace al PDF.
5. Orden de la fecha: expedición buena → se usa; expedición 1969 con
   vigencia 06-01-2026 (caso real 753262) → `2026-01-06` + aviso; expedición
   y vigencia malas (año distinto al del título / futuras / ilegibles) →
   `<año>-01-01` + aviso.
6. Años y tipos pedidos según `fini`/`ffin` y piso 2015.
7. Filtro por fecha, dedup por id, detalle sin PDF → omitido con aviso.
8. `link["verify"] is False`, `checks_for_republication is False`,
   `doc_id_uses_publication_date is False`,
   `scheduled_min_lookback_days == 400`.
9. `stop_event`, `limit`, listado de un tipo/año que falla (aviso y sigue),
   detalle que falla (aviso y sigue).
10. Dedup de decretos en todos los sentidos: prueba en `tests/test_tasks.py`
    (ver Integración).

## Riesgos y notas

- **Volumen:** es la fuente más grande del proyecto después de la Rama
  Judicial. La carga inicial hay que planearla con el administrador
  (espacio en MinIO: ~23.300 PDF de ~80 KB ≈ 2 GB).
- **Espacio en disco del servidor de producción:** el 2026-11-19 el disco C:
  de producción se llenó durante una recuperación grande de la CSJ y Docker
  dejó de responder. Antes de la carga inicial hay que confirmar con
  sistemas que queda espacio libre de sobra (los ~2 GB de PDF más la base de
  datos y los temporales de descarga, con margen) y lanzarla por tramos de
  años, revisando el espacio entre tramos.
- **Fechas corregidas:** con el respaldo de la fecha de vigencia quedan menos
  normas en 1 de enero que el ~5 % de la primera versión; las que queden se
  ordenan por año, no por día.
- **PDF generado:** si la Función Pública cambia la plantilla, los PDF nuevos
  se verán distintos a los viejos; no hay republicación que detectar.
- Si el sitio arregla el certificado, se puede quitar `verify=False`.

## Preguntas para el usuario / administrador

1. **Alcance de "Departamentos Administrativos":** ¿se quiere sólo lo que
   expide la Función Pública (propuesta), o todo el Gestor filtrado a algún
   otro departamento administrativo? (Para Prosperidad Social el Gestor sólo
   tiene 1 norma; ver su propio diseño.)
2. **Tipos:** ¿todos los de la tabla, o sólo conceptos? Los conceptos son el
   99 % del volumen (~23.000).
3. **Prefijo `CU`** para "Circular Unificada" (9 desde 2015): ¿se aprueba o
   se usa `C`?
4. **Fecha corregida** cuando la expedición no cuadra con el año del título:
   ¿se aprueba el orden expedición → vigencia → `<año>-01-01`? (La primera
   versión iba directo a `<año>-01-01`; se agregó el paso por la fecha de
   vigencia tras la revisión del 2026-11-26.)
5. **Sigla `DAFP`:** ¿se aprueba?
6. **Carga inicial** de ~14 horas: ¿se lanza entera o por tramos? (Se
   recomienda por tramos, por el espacio en disco: ver Riesgos.)
7. **Número:** **Respondida por el administrador el 2026-11-26:** el número
   se copia tal cual lo escribe la entidad, sin quitar ni poner ceros, en las
   tres fuentes (ADRES, DPS y Función Pública). Aquí cambia sólo Resoluciones
   (`R_DAFP_035_2020` en vez de `R_DAFP_0035_2020`); conceptos y circulares ya
   iban tal cual. Los decretos siguen con el código común `D…`.
8. **Dedup de decretos:** **Respondida por el administrador el 2026-11-26:**
   `dps` y `funcion_publica` entran al chequeo de
   `list_ministerio_documents_by_title`, para que la dedup funcione en todos
   los sentidos (ver Integración).

## Plan de implementación (cuando se apruebe)

1. Prueba + función `h5` → título (casos 1-2).
2. Prueba + parseo de listado y detalle con HTML real (casos 3-5).
3. Prueba + `scrap()` con el sitio simulado (casos 6-9).
4. Import en `families/__init__.py`, seed y `tests/test_seed.py`.
5. Prueba + dedup de decretos en todos los sentidos
   (`core/db/repository.py`, `tests/test_tasks.py`; caso 10), si no lo hizo
   ya `dps`.
6. Corrida real local de 2026 completo + un año grande (2021) y segunda
   corrida sin descargas nuevas. Fijar `alerta_margen_dias` con lo que salga.
7. Ficha en `docs/guia-despliegue-sistemas.md`.
