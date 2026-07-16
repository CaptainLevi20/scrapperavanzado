# Descarga masiva de documentos útiles — Diseño

Fecha: 2026-07-16

## Contexto y objetivo

Hoy, revisar y marcar documentos como "Útil" (vía el previsualizador) no tiene ninguna forma de recolectarlos después: hay que descargarlos uno por uno con el botón "Descargar" de cada fila. Este diseño agrega un botón "Descarga masiva" que empaqueta en un único `.zip` **todos** los documentos con `review_status = "useful"` en todo el sistema (sin importar los filtros activos en la tabla), organizados con la misma jerarquía de carpetas que ya usa cada fuente para guardar sus archivos en MinIO (su `storage_key` completo, ej. `JEP/2026-06-01/Auto/....pdf`).

Explícitamente en alcance:
- Botón "Descarga masiva" en `DocumentsPage`, que dispara la generación del ZIP y navega a una nueva página de historial.
- Generación del ZIP en background (Celery), no en el navegador — para no depender de la memoria/pestaña del cliente con cientos de archivos.
- Nueva página "Descargas masivas": historial de descargas generadas (estado, cantidad de documentos, fecha, botón de descarga cuando termina), con polling mientras haya alguna en curso — mismo patrón que la Bitácora de Runs.
- Si un archivo individual falla al leerse de MinIO, se omite y se sigue con el resto (no aborta todo el ZIP por un archivo dañado); se cuenta cuántos fallaron.
- Si no hay ningún documento "Útil" al momento de generar, el job termina en `failed` con un mensaje claro.

Explícitamente fuera de alcance:
- Filtrar la descarga masiva por fuente/tipo/fecha — siempre son *todos* los "Útil" del sistema.
- Expiración/limpieza automática de ZIPs viejos en MinIO (se quedan indefinidamente; se puede agregar después si el espacio se vuelve un problema).
- Cancelar una descarga masiva en curso (a diferencia de los Runs, que sí soportan `cancel_requested`).
- Deduplicar contenido entre descargas masivas sucesivas (cada clic genera un ZIP nuevo y completo, aunque el set de "Útil" no haya cambiado).
- Notificaciones (email, etc.) cuando termina — el usuario se entera al ver la página de historial.

## Modelo de datos

Nueva tabla `bulk_downloads` (espejo simplificado de `runs`, sin sub-tabla por fuente ya que es una sola operación global, no repartida entre fuentes):

```python
class BulkDownload(Base):
    __tablename__ = "bulk_downloads"

    id = Column(Integer, primary_key=True)
    status = Column(String, nullable=False, default="pending")  # pending | running | completed | failed
    document_count = Column(Integer, nullable=False, default=0)  # incluidos en el zip
    failed_count = Column(Integer, nullable=False, default=0)    # se omitieron por error de lectura
    zip_storage_key = Column(Text, nullable=True)                # solo si status == completed
    error_message = Column(Text, nullable=True)                  # solo si status == failed
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
```

Migración de Alembic nueva para la tabla.

## Backend

### `core/db/repository.py`

- `create_bulk_download(db) -> BulkDownload`: inserta con `status="pending"`.
- `list_bulk_downloads(db, limit=50, offset=0) -> list[BulkDownload]`: ordenado por `created_at desc`.
- `get_bulk_download(db, id) -> Optional[BulkDownload]`.
- `set_bulk_download_status(db, id, status, **fields)`: actualiza status y los campos que correspondan (`started_at`, `finished_at`, `document_count`, `failed_count`, `zip_storage_key`, `error_message`) — mismo patrón que `set_run_status`.
- `list_useful_documents(db) -> list[Document]`: `select(Document).where(Document.review_status == "useful")`. Es el snapshot que consume el task; se llama una sola vez al arrancar, así que documentos marcados "Útil" mientras el zip se arma no se cuelan a mitad de camino.

### `worker/tasks.py`

Nueva task `build_bulk_download_zip(bulk_download_id: int)`:

1. Carga la fila `BulkDownload`, marca `status="running"`, `started_at=now`.
2. `documents = repository.list_useful_documents(db)`. Si está vacía: `status="failed"`, `error_message="No hay documentos marcados como Útil para descargar"`, `finished_at=now`, retorna.
3. Crea un directorio temporal (`tempfile.TemporaryDirectory`), y para cada documento:
   - `dest = tmp_path / document.storage_key`; `dest.parent.mkdir(parents=True, exist_ok=True)` (boto3 no crea subdirectorios solo — `storage_key` ya trae los separadores `/` de la jerarquía, así que hay que crearlos antes de llamar a `download_file`).
   - `core.storage.download_file(document.storage_bucket, document.storage_key, dest)`.
   - Si falla (excepción de boto3, archivo no encontrado, etc.): loggea el error, incrementa un contador local `failed_count`, continúa con el siguiente documento — no aborta el job entero.
4. Si **todos** fallaron (ninguno se pudo descargar): `status="failed"`, mensaje correspondiente.
5. Arma un `.zip` (módulo estándar `zipfile`) recorriendo los archivos descargados, usando el mismo `storage_key` relativo como nombre de entrada dentro del zip (preserva la jerarquía Fuente/Fecha/Tipo/archivo tal cual).
6. Sube el zip a MinIO bajo la clave `bulk-downloads/{bulk_download_id}.zip` (mismo bucket default que ya usa `upload_file`).
7. `status="completed"`, `document_count=<descargados con éxito>`, `failed_count=<fallidos>`, `zip_storage_key="bulk-downloads/{id}.zip"`, `finished_at=now`.
8. Cualquier excepción no prevista en el flujo general (no por-documento): `status="failed"`, `error_message=str(exc)`.

No se usa `ThreadPoolExecutor` aquí (a diferencia de `scrape_source_task`) — es una operación de archivo secuencial, no hay necesidad de paralelizar descargas para este caso de uso, y mantenerlo simple reduce superficie de error.

### `api/schemas.py`

```python
class BulkDownloadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    document_count: int
    failed_count: int
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
```

### `api/routers/bulk_downloads.py` (nuevo router)

- `POST /bulk-downloads` → `repository.create_bulk_download(db)`, dispara `build_bulk_download_zip.delay(bulk_download.id)`, responde `202` con el `BulkDownloadOut` recién creado (status `pending`).
- `GET /bulk-downloads` → `repository.list_bulk_downloads(db, limit, offset)`.
- `GET /bulk-downloads/{id}/download` → si `status != "completed"` o `zip_storage_key` es `None`, `404`; si no, `presigned_url(bucket, zip_storage_key, response_content_disposition='attachment; filename="descarga_masiva_{id}.zip"')` y responde `{"url": ...}` (mismo patrón ya usado por `/documents/{id}/preview`, para poder invocar `downloadFromUrl` en el frontend en vez de depender de una redirección directa).

Registrado en `api/main.py` junto a los demás routers.

## Frontend

### `api/bulkDownloads.ts` (nuevo)

```ts
export interface BulkDownload {
  id: number;
  status: "pending" | "running" | "completed" | "failed";
  document_count: number;
  failed_count: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export function createBulkDownload(): Promise<BulkDownload> {
  return apiFetch<BulkDownload>("/bulk-downloads", { method: "POST" });
}

export function fetchBulkDownloads(params: { limit?: number; offset?: number } = {}): Promise<BulkDownload[]> {
  return apiFetch<BulkDownload[]>(`/bulk-downloads${buildQuery(params)}`);
}

export function fetchBulkDownloadUrl(id: number): Promise<string> {
  return apiFetch<{ url: string }>(`/bulk-downloads/${id}/download`).then((data) => data.url);
}
```

### `pages/BulkDownloadsPage.tsx` (nuevo)

Tabla igual a `RunsPage`: columnas ID, Estado (`StatusBadge`, que ya soporta `pending`/`running`/`completed`/`failed` sin cambios), Documentos (`document_count`, y si `failed_count > 0` un texto secundario "N omitidos"), Creado, y una columna Descarga con un botón que, cuando `status === "completed"`, llama `fetchBulkDownloadUrl(id)` y luego `downloadFromUrl(url, \`descarga_masiva_${id}.zip\`)` (ambas ya existen — la segunda se reutiliza tal cual de `api/documents.ts`, ya que ignora los headers de la respuesta y nombra el archivo con el segundo argumento).

`useQuery` con `refetchInterval` idéntico al de `RunsPage`: sigue sondeando mientras exista alguna fila con `status` no terminal (`pending`/`running`).

Ruta nueva `/bulk-downloads`, agregada a la navegación en `AppLayout.tsx`.

### `pages/DocumentsPage.tsx`

Botón "Descarga masiva" junto al botón de filtro de fecha. Al hacer clic: `createBulkDownload()` → `navigate("/bulk-downloads")`. No requiere ningún estado local ni confirmación adicional (no es destructivo, es solo lectura + empaquetado).

## Manejo de errores

- **0 documentos útiles**: el job termina `failed` con mensaje claro; se ve igual que cualquier otro error en la tabla de historial (fila roja con el mensaje), no rompe nada del lado del usuario — simplemente no hay ZIP que descargar.
- **Algunos documentos fallan al leerse de MinIO**: se omiten individualmente; el job igual termina `completed` con `failed_count > 0`, visible en la tabla como aviso ("N omitidos"), para que quede constancia sin bloquear la descarga de lo que sí se pudo armar.
- **Todos los documentos fallan**: `failed` con mensaje describiendo cuántos se intentaron y fallaron.
- **Fallo inesperado** (ej. sin espacio en disco al armar el zip, error de conexión con MinIO al subir el resultado): `failed` con `str(exc)` como mensaje — mismo patrón que ya usa `run_source.error_message`.

## Testing

- **Backend**:
  - `tests/test_repository.py` (o archivo nuevo): `create_bulk_download`, `list_bulk_downloads` ordena por más reciente, `set_bulk_download_status` actualiza los campos esperados, `list_useful_documents` filtra correctamente por `review_status`.
  - `tests/test_tasks.py`: `build_bulk_download_zip` — caso feliz (mockeando `download_file`/`upload_file`) verifica que sube un zip con las entradas esperadas (nombres = `storage_key`) y marca `completed` con el conteo correcto; caso sin documentos útiles marca `failed` con el mensaje esperado; caso con un documento que falla al descargar se omite y cuenta en `failed_count` sin abortar el resto.
  - `tests/test_api_bulk_downloads.py` (nuevo): `POST /bulk-downloads` crea la fila y dispara la task (mockeada); `GET /bulk-downloads` lista ordenado; `GET /bulk-downloads/{id}/download` da 404 si no está `completed`, da la URL firmada si sí.
- **Frontend**:
  - `api/bulkDownloads.test.ts` (nuevo): tests MSW estándar para las tres funciones.
  - `pages/BulkDownloadsPage.test.tsx` (nuevo): renderiza el historial, muestra el botón de descarga solo cuando `completed`, sigue sondeando mientras haya un job no terminal (mismo patrón que el test de polling de `RunsPage.test.tsx`).
  - `pages/DocumentsPage.test.tsx`: agrega un caso que confirma que el botón "Descarga masiva" llama a `createBulkDownload` y navega a `/bulk-downloads`.
