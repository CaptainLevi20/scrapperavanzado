# Descarga masiva diaria automática

**Fecha:** 2026-09-03
**Tipo:** cambio acotado (bounded)

## Qué

Una tarea programada que genera una descarga masiva cada día, sin que nadie
apriete el botón. Aprovecha que Corte Constitucional, CSJ y Consejo de Estado
entran ya marcados como `useful` (ver
`2026-09-03-auto-util-csj-consejo-estado-design.md`).

## Cómo

`worker/beat_schedule.py`:

- Nueva tarea `worker.trigger_scheduled_bulk_download`: si
  `repository.list_useful_documents(db)` no está vacío, crea un `BulkDownload`
  y dispara `build_bulk_download_zip.delay(id)` — la misma secuencia que el
  endpoint `POST /bulk-downloads`. Si no hay nada útil sin entregar, no crea
  el lote (evita ZIPs vacíos).
- Entrada `"daily-bulk-download"` en `beat_schedule`: `crontab(hour=8,
  minute=0)` — después del scrape de las 6:00, con margen para que termine.

`list_useful_documents` ya excluye lo entregado en un lote anterior
(`bulk_download_id` no nulo), así que cada corrida empaqueta solo lo nuevo
desde la anterior.

## Qué NO hace

- No deja el ZIP en ninguna carpeta del usuario ni en un recurso compartido:
  queda en el almacenamiento de la app, listado en "Descargas masivas", y hay
  que bajarlo desde la interfaz.
- No hay política de retención: los ZIPs diarios se acumulan en el
  almacenamiento. Si molesta, se borran a mano desde la lista (o se agrega
  una limpieza después).

## Pruebas

`tests/test_beat_schedule.py`: crea y dispara cuando hay útiles sin entregar;
se omite (sin `BulkDownload`) cuando no hay; la entrada está en
`beat_schedule`.
