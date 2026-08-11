# Diseño: Nombre canónico con versionado y actuaciones (todas las fuentes)

**Fecha:** 2026-08-10
**Estado:** Aprobado el diseño; pendiente plan de implementación.

## Problema

Hoy el nombre de un documento **no es consistente** entre dónde se ve y cómo se
descarga:

- En la lista/app se muestra `document.title`.
- La descarga individual (`GET /documents/{id}/download`) redirige a la URL
  prefirmada **sin** `Content-Disposition`, así que el archivo toma el nombre
  físico del `storage_key` (que puede diferir del título).
- La descarga de una versión anterior (`.../versions/{vid}/download`) hace lo
  mismo: nombre del `storage_key` de la versión.
- El ZIP masivo (`worker/tasks.py`) usa `arcname=document.storage_key` — la
  ruta interna completa, con carpetas.
- La previsualización sí usa el título (`_preview_content_disposition`).

Cuatro caminos distintos. Además, el usuario necesita que el nombre codifique
información de **actuaciones** (procesos judiciales con radicado) y de
**versiones** (republicaciones), que hoy no se refleja en el nombre.

## Objetivo

Un **único nombre canónico** por documento, **idéntico** en: nombre visible en
la app, descarga individual, descarga de versión, cada archivo dentro del ZIP y
previsualización. Aplica a **todas las fuentes**.

### Receta del nombre

```
{base}[_{fecha_providencia}][_v{n}]      (+ extensión del archivo al descargar)
```

- **base**: el `title` actual del documento (identificador propio de cada
  fuente). No cambia. Ej. Consejo de Estado: `11001-03-28-000-2026-00300-00`.
- **`_{fecha_providencia}`** en formato `AAAAMMDD`: **solo** si el documento
  pertenece a un proceso con radicado (familias "con actuaciones": `samai`,
  `rama_judicial`) y su título tiene forma de radicado.
- **`_v{n}`**: **solo** si el documento tiene **más de una** versión.

### Ejemplos

| Caso | Nombre |
|---|---|
| Sin actuaciones, 1 versión | `T-123-24` |
| Sin actuaciones, republicado | `T-123-24_v1`, `T-123-24_v2` |
| Con actuaciones | `11001-03-28-000-2026-00300-00_20260731` |
| Con actuaciones + versión | `11001-03-28-000-2026-00300-00_20260731_v1` |

## Enfoque elegido (Opción A): nombre calculado, sin renombrar archivos

El `title` y los `storage_key` **no se tocan**. El nombre canónico es una capa
de presentación que se **calcula** a partir de datos que ya existen (`title`,
detección de familia con actuaciones, `f_providencia`) más el número de versión.

Ventajas: cero renombrados/movimientos en el almacenamiento; los documentos
existentes adoptan el nombre nuevo automáticamente; se preserva la agrupación de
actuaciones por `title` (que se rompería si incrustáramos los sufijos en el
título); reversible.

Se descartó la Opción B (renombrar físicamente cada archivo) por riesgo alto
(renombrado masivo + movimiento en cada republicación) y porque rompería la
agrupación por título.

## Componentes

### 1. Función de nombre canónico (núcleo)

Función pura nueva (p. ej. `core/naming.py`) que arma el nombre:

- Entrada: `base` (título), `f_providencia` (fecha o `None`), `es_caso` (bool:
  familia con actuaciones **y** título con forma de radicado), `version_no`
  (entero) y `total_versiones` (entero).
- Regla de fecha: añade `_{f_providencia:%Y%m%d}` solo si `es_caso` y hay una
  fecha disponible.
- Regla de versión: añade `_v{version_no}` solo si `total_versiones > 1`.
- Orden fijo: `base` → fecha → versión.
- No incluye la extensión; el llamador añade la extensión real del archivo al
  usarla como nombre de descarga.

Helpers de conveniencia en el backend:
`nombre_descarga_documento(document) -> str` y
`nombre_descarga_version(document, version) -> str`, que devuelven
`{nombre_canónico}{.ext}` usando la extensión del `storage_key` correspondiente.

Detección de "con actuaciones": se centraliza reutilizando la lógica que ya
existe en `api/routers/documents.py` (`_CASE_TITLE_CHECKS`: familias `samai` y
`rama_judicial`, con su propio chequeo de "título de caso" —
`is_samai_case_title`/`is_radicado_title` de `core/utils.py`). Se extrae a un
punto único reutilizable por el naming, el ZIP y el router.

### 2. Numeración de versiones (persistida)

Para no recalcular conteos en cada consulta, se persiste el número de versión.

- Columna nueva `version_no` (entero, no nulo, `default 1`, `server_default
  '1'`) en `documents` y en `document_versions`.
- Al **insertar** un documento nuevo: `version_no = 1` (sin sufijo, porque es
  única).
- Al **republicar** (`archive_and_replace_document` en
  `core/db/repository.py`): la versión archivada hereda el `version_no` actual
  del documento; el documento incrementa su `version_no` en 1. Primera
  republicación → archivada `v1`, documento `v2`.
- `total_versiones` del documento vigente = su propio `version_no` (siempre es
  el máximo). Una versión archivada existe solo cuando hubo republicación, por
  lo que su sufijo siempre se muestra.

### 3. Fecha de providencia en Rama Judicial

Rama Judicial no expone la fecha de providencia en sus metadatos; sí está en la
**primera página del PDF** (verificado en vivo: ~90%+ de aciertos sobre
providencias individuales; 25/25 PDFs legibles con `cryptography`).

- Se reutiliza el enganche post-descarga que ya usan SAMAI y Corte Suprema
  (`resolve_unverified_document` en `core/scrapers/base.py`, disparado por el
  worker justo tras descargar el archivo, con el PDF en disco — sin descargas
  extra). Rama Judicial marca sus documentos con título de radicado para que el
  worker invoque el enganche.
- El enganche lee la página 1, extrae la fecha con un **parser de fechas en
  español** (maneja día en dígitos "8 de mayo de 2026" y en letras con número
  entre paréntesis "diez (10) de agosto de dos mil veintiséis (2026)") y la
  guarda en `doc.f_providencia`.
- Aplica **solo** a documentos cuyo título es un radicado (providencias
  individuales: autos y sentencias). Los documentos sin radicado en el título
  (estados electrónicos, avisos) quedan fuera del sufijo de fecha por la regla
  general y no necesitan extracción.
- **Respaldo (fallback):** cuando no se pueda leer/parsear la fecha (~10%), se
  usa la fecha del listado (`f_public`, ya disponible) para el sufijo, de modo
  que el nombre siempre quede definido y sin colisiones. `f_providencia` puede
  quedar en `None`; el naming usa `f_providencia` si existe, si no `f_public`,
  para familias con actuaciones.
- **Dependencia nueva:** agregar `cryptography>=3.1` a `requirements.txt` (los
  PDFs vienen cifrados con AES; sin ese paquete `pypdf` no los abre).
- El `f_providencia` de Rama Judicial es **solo para el nombre**; no entra en el
  `doc_id` (que sigue basado en el `uuid` del archivo), así que no altera la
  identidad ni la detección de republicación.

### 4. Cableado de descarga, vista y API

Todos los puntos usan el nombre canónico:

- `GET /documents/{id}/download`: pasar `response_content_disposition` con
  `attachment; filename="{nombre_canónico}{.ext}"` a `presigned_url` (hoy no lo
  pasa).
- `GET /documents/{id}/versions/{vid}/download`: igual, con el nombre de la
  versión (incluye su `_v{n}`).
- `preview_document` / `_preview_content_disposition`: usar el nombre canónico
  como base en lugar de `document.title`.
- ZIP masivo (`worker/tasks.py`): `arcname = {nombre_canónico}{.ext}`. Si dos
  entradas coincidieran en nombre, se desambigua con sufijo ` (2)`, ` (3)`…
  antes de la extensión, para no sobrescribir dentro del ZIP.
- Esquemas de respuesta (`DocumentOut`, `DocumentVersionOut`): exponer un campo
  `nombre` con el nombre canónico. `title` se conserva (uso interno/agrupación).
- Frontend: mostrar `nombre` donde hoy se muestra `title` (lista de documentos,
  diálogo de previsualización, diálogo de versiones). Las descargas ya pasan por
  el backend, así que el nombre de archivo sale correcto sin cambios extra en el
  cliente.

### 5. Backfill de lo existente

Como el nombre se calcula, lo único a rellenar en lo guardado es `version_no`.
Script único (estilo `core/backfill_*.py`):

- Documentos con versiones archivadas: ordenar `document_versions` por
  `superseded_at` ascendente y asignar `version_no` 1..k a las archivadas
  (la más antigua = 1); el documento vigente = k+1.
- Documentos sin versiones archivadas: `version_no = 1`.
- Solo base de datos; no toca ni mueve archivos.
- No hace backfill de `f_providencia` de Rama Judicial existente (requeriría
  releer PDFs). Para lo existente sin `f_providencia`, el nombre usa el respaldo
  (`f_public`); lo nuevo sí extraerá la fecha real.

## Manejo de errores y casos límite

- **Familia con actuaciones sin ninguna fecha** (`f_providencia` y `f_public`
  nulos): se omite el sufijo de fecha (queda solo `base` [+ versión]). Situación
  rara; se acepta el nombre sin fecha antes que inventar una.
- **Colisión de nombres en el ZIP**: desambiguación con ` (2)`, ` (3)`… Fuera
  del ZIP no hay colisión relevante (cada descarga es de un documento puntual).
- **PDF de Rama Judicial ilegible o sin fecha parseable**: se usa el respaldo;
  nunca bloquea la ingestión del documento.
- **`storage_key` inseguro**: el ZIP ya lo omite (`is_safe_storage_key`); se
  conserva ese chequeo.

## Pruebas

- **Función de nombre**: unitarias de todas las combinaciones (sin actuaciones/1
  versión; sin actuaciones/republicado → `_v1`/`_v2`; con actuaciones →
  `_AAAAMMDD`; con actuaciones + versión → `_AAAAMMDD_v1`; con actuaciones sin
  fecha → sin sufijo de fecha).
- **Parser de fechas en español**: unitarias sobre los textos reales capturados
  (día en letras con paréntesis, día en dígitos, saltos de línea, año en
  letras).
- **Enganche Rama Judicial**: llena `f_providencia` desde un texto de página 1;
  usa respaldo cuando no hay fecha.
- **Numeración de versiones** (`repository`): insertar + republicar incrementa
  `version_no` y archiva con el número correcto.
- **API**: `download`/`versions/.../download`/`preview` fijan el
  `Content-Disposition` con el nombre canónico correcto; `DocumentOut` incluye
  `nombre`.
- **ZIP** (`worker`): los `arcname` son el nombre canónico y se desambiguan en
  colisión.
- **Backfill**: asigna `version_no` correctamente con y sin versiones.
- **Frontend**: la lista, la previsualización y el diálogo de versiones muestran
  `nombre`.

Nota: las suites de BD se corren de forma dirigida (no en paralelo ni suites
pesadas completas). `test_migrations.py` tiene un fallo pre-existente en Windows,
no relacionado.

## Puesta en marcha

1. Migración Alembic: agrega `version_no` a `documents` y `document_versions`.
2. Agregar `cryptography>=3.1` a `requirements.txt`.
3. Fusionar PR → CI construye imágenes GHCR.
4. En el servidor de la oficina: `docker compose pull` / `up`.
5. Correr el backfill una vez (`docker compose run …`), solo BD.
6. Los documentos existentes adoptan el nombre nuevo apenas se despliega, sin
   migración de almacenamiento.

## Fuera de alcance

- Backfill de `f_providencia` real para el Rama Judicial ya existente (usa el
  respaldo).
- Renombrado físico de archivos en el almacenamiento.
- Cambios al `doc_id`/identidad o a la detección de republicación.
