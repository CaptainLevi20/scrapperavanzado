# Reporte mensual de extracción — Design

## Problema

El usuario administra el sistema pero no tiene forma de revisar, mes a mes,
qué tanto se está extrayendo: cuántos documentos nuevos/actualizados/con
error salieron de cada fuente, si hubo fallas, y cómo se compara con el mes
anterior. Hoy esa información solo existe dispersa en la base de datos
(`runs`, `run_sources`, `run_errors`, `documents`) sin ninguna vista
consolidada.

## Alcance (v1)

- Un PDF por mes, descargable, con cuatro secciones: resumen general,
  detalle por fuente, detalle de errores, comparación con el mes anterior.
- Se genera automáticamente el día 1 de cada mes (cubre el mes que acaba de
  cerrar) y también bajo demanda para cualquier mes ya terminado.
- Página nueva "Reportes" en el menú con el listado histórico y descarga.
- No incluye envío por correo ni notificaciones — solo queda disponible
  para descargar desde la app (igual que las descargas masivas).
- No incluye edición/anotación del PDF ni comparación más allá de "mes vs.
  mes anterior" (sin promedios móviles, sin gráficas).

## Modelo de datos

Tabla nueva `monthly_reports` (mismo espíritu que `bulk_downloads`):

```
id              PK
period          Date, not null   -- primer día del mes que cubre (ej. 2026-08-01)
status          String, not null, default "pending"  -- pending|running|completed|failed
triggered_by    String, not null  -- "scheduled" | "manual"
storage_bucket  String, nullable  -- solo si status == completed
storage_key     Text, nullable    -- solo si status == completed
error_message   Text, nullable    -- solo si status == failed
started_at      DateTime, nullable
finished_at     DateTime, nullable
created_at      DateTime, not null, default now
```

Sin restricción de unicidad en `period`: cada generación (automática o
manual) inserta una fila nueva. Pedir el mismo mes dos veces produce dos
reportes en el listado — igual de simple que `bulk_downloads`, que tampoco
deduplica. El listado se ordena por `created_at` descendente.

Migración de Alembic nueva para la tabla; sin cambios a tablas existentes.

## Agregación de métricas (`core/reporting.py`)

Módulo nuevo de funciones puras de solo lectura sobre la base de datos —
sin efectos secundarios, para poder probarlas con datos conocidos sin pasar
por Celery ni por el render del PDF.

`build_monthly_report_data(db, period: date) -> dict`:

- `period_start = period` (ya es el día 1), `period_end` = día 1 del mes
  siguiente (exclusivo). El "mes anterior" para la comparación es el mismo
  cálculo desplazado un mes atrás.
- La actividad del mes se mide por **corridas (`runs`) cuyo `started_at`
  cae en `[period_start, period_end)`** — no por `documents.downloaded_at`
  — porque `run_sources.docs_new/docs_updated/docs_errors` ya es el
  conteo autoritativo por fuente que usa el resto de la app (ej. la página
  de detalle de un run), y evita contar de más si un documento se
  actualiza varias veces en runs sucesivos del mismo mes (se suma una vez
  por cada run, que es el comportamiento correcto: cada run que lo tocó
  contó como una actualización real de la fuente).
- **Resumen general**: `docs_new`, `docs_updated`, `docs_errors` totales
  (suma de todos los `run_sources` de los runs del mes); conteo de runs
  por `status` (`completed`, `completed_with_errors`, `failed`,
  `cancelled` — los valores reales que usa `_finalize_run` en
  `worker/tasks.py`); espacio de almacenamiento = suma de
  `file_size_bytes` de `documents` con `downloaded_at` en el rango del mes
  (aproximación de "lo que se agregó este mes", documentada como tal en el
  propio PDF).
- **Detalle por fuente**: `run_sources` de los runs del mes, agrupados por
  `source_id` (join a `sources`/`source_families` para nombre); por fuente,
  `docs_new`/`docs_updated`/`docs_errors` y si tuvo algún `run_source.status
  == "failed"` ese mes. Entre las fuentes **activas** (`sources.active ==
  true`), las que no tuvieron ninguna corrida en el mes se listan aparte
  como "sin actividad este mes" (si la lista no está vacía) — visibilidad
  de fuentes calladas que deberían estar corriendo. Las fuentes pausadas
  (`active == false`, ej. Minhacienda, MinTransporte) no se listan en
  ningún lado del reporte — ya están fuera de operación a propósito.
- **Detalle de errores**: `run_errors` unidos a `run_sources` (para el
  nombre de la fuente) y `runs` (para acotar por mes), ordenados por
  `occurred_at`. El `message` se trunca a 300 caracteres en el PDF (una
  tabla con mensajes completos rompería el layout); el mensaje completo
  sigue disponible en la base de datos para quien necesite más detalle.
- **Comparación con el mes anterior**: misma agregación por fuente para
  `period` desplazado un mes atrás; por fuente, delta de `docs_new` y
  variación porcentual. Si el mes anterior tuvo 0 y este mes tiene > 0 se
  muestra "nueva actividad" en vez de un porcentaje (división por cero). Si
  ambos meses tienen 0, la fuente no aparece en esta sección.

Devuelve un diccionario con esas cuatro claves más `period` y
`period_label` (ej. `"Septiembre 2026"`, usando un mapa de meses en
español local a este módulo — no se reutiliza `core/fecha_es.py`, que es
un parser de fechas en prosa, no un formateador).

## Render del PDF (`core/reporting_pdf.py`)

Se agrega `reportlab` a `requirements.txt` — librería Python pura, sin
dependencias del sistema (a diferencia de weasyprint, que en Windows
necesita GTK instalado aparte y es una fuente típica de fallos de
entorno).

`render_monthly_report_pdf(data: dict) -> bytes`: arma el PDF con
`SimpleDocTemplate` — portada con el período, y las cuatro secciones como
tablas (`Table`/`TableStyle`) en el orden fijo: resumen, por fuente,
errores, comparación. Sin gráficas en v1 (fuera de alcance; tablas cubren
"lo más detallado posible" sin la complejidad de generar imágenes).

## Tarea de Celery (`worker/tasks.py`)

`worker.build_monthly_report(report_id: int)`:

1. `set_monthly_report_status(db, report_id, "running", started_at=now)`.
2. `data = build_monthly_report_data(db, report.period)`.
3. `pdf_bytes = render_monthly_report_pdf(data)`.
4. Sube a MinIO: `storage_key = f"reportes/{period:%Y-%m}_{report_id}.pdf"`
   (se incluye el `id` para que dos generaciones del mismo mes no se
   pisen), bucket = `get_settings().s3_bucket`.
5. `set_monthly_report_status(db, report_id, "completed", storage_bucket=...,
   storage_key=..., finished_at=now)`.
6. Cualquier excepción en 2–4 → `set_monthly_report_status(db, report_id,
   "failed", error_message=str(exc), finished_at=now)` (mismo patrón que
   `build_bulk_download_zip`).

Un mes sin ninguna corrida no es un error: `build_monthly_report_data`
devuelve todo en cero y el PDF se genera igual, dejando constancia de que
no hubo actividad.

## Generación automática (`worker/beat_schedule.py`)

`worker.trigger_monthly_report`: calcula el mes recién cerrado (hoy es el
día 1; el mes a reportar es el anterior — con manejo explícito de cruce de
año: enero → diciembre del año pasado), crea la fila con
`triggered_by="scheduled"` y dispara `build_monthly_report.delay(id)`.

Entrada en `beat_schedule`: `crontab(day_of_month=1, hour=3, minute=30)` —
después de `nightly-storage-sync` (02:00) y antes de `daily-scrape` (06:00),
para no competir por recursos con el scrape del día.

## API (`api/routers/reports.py`)

Nuevo router, mismo patrón que `bulk_downloads.py`:

- `POST /reports` — body `{"period": "2026-08"}` (formato `YYYY-MM`). Se
  parsea a `date(año, mes, 1)`. Si `period >= date(hoy.año, hoy.mes, 1)`
  (el mes actual o uno futuro, que todavía no terminó) → `400` con mensaje
  "No se puede generar el reporte de un mes que no ha terminado."
  `triggered_by="manual"`. `202` con la fila creada.
- `GET /reports?limit&offset` — lista paginada, orden `created_at` desc.
- `GET /reports/{id}/download` — `404` si no existe o `status !=
  "completed"`; si no, URL firmada con
  `response_content_disposition=attachment; filename="reporte_{period:%Y-%m}.pdf"`.

Esquema nuevo `MonthlyReportOut` en `api/schemas.py` (mismos campos que la
tabla, sin `storage_bucket`/`storage_key` crudos — igual que
`BulkDownloadOut` no los expone).

## Frontend

`frontend/src/pages/ReportsPage.tsx` (+ `.test.tsx`), registrada en
`App.tsx` (ruta `/reports`, lazy) y en el menú de `Sidebar.tsx`:

- Tabla: Mes | Estado | Creado | Descargar — mismo componente de estado
  visual que ya usa `BulkDownloadsPage` para pending/running/completed/failed.
- Selector de mes (`<input type="month">`) + botón "Generar" que llama a
  `POST /reports`; deshabilitado si el mes elegido es el actual o uno
  futuro (mismo límite que valida el backend, para no depender solo del
  error del servidor).
- Mientras haya alguna fila en `pending`/`running`, refresco periódico del
  listado (mismo patrón de polling que ya usa `RunDetailPage`).

## Pruebas

- `tests/test_reporting.py` — `build_monthly_report_data` con fixtures de
  runs/run_sources/run_errors/documents conocidos: sumas correctas por
  fuente, mes vacío da todo en cero, fuentes sin actividad se listan
  aparte, comparación con mes anterior (caso normal, caso "mes anterior en
  cero", caso ambos en cero se omite), truncado de mensajes de error a 300
  caracteres, cruce de año en el cálculo del mes anterior (enero → diciembre).
  Smoke test de `render_monthly_report_pdf`: dado un `data` de ejemplo,
  produce bytes que empiezan con `%PDF`.
- `tests/test_tasks.py` — `build_monthly_report`: camino feliz (mockeando
  `upload_file`) deja la fila en `completed` con `storage_key` seteado;
  camino de falla (excepción forzada en la agregación o el upload) deja la
  fila en `failed` con `error_message`.
- `tests/test_beat_schedule.py` — `trigger_monthly_report` crea la fila del
  mes anterior con `triggered_by="scheduled"` y dispara la tarea; caso de
  cruce de año (ejecutar el 1 de enero); la entrada está en `beat_schedule`
  con el crontab esperado.
- `tests/test_api_reports.py` — `POST /reports` crea y dispara (202); mes
  actual/futuro → 400; `GET /reports` lista y pagina; `GET
  /reports/{id}/download` con `completed` da URL firmada, con
  pending/failed/inexistente da 404.
- `frontend/src/pages/ReportsPage.test.tsx` — mismo esqueleto que
  `BulkDownloadsPage.test.tsx`: renderiza el listado, botón "Generar"
  deshabilitado para el mes actual, dispara `POST /reports` con el mes
  elegido, enlace de descarga solo en filas `completed`.
