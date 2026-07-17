# Detección de republicación de documentos — Diseño

Fecha: 2026-07-16

## Contexto y objetivo

Algunas fuentes (empezando por Corte Constitucional) publican un documento con un número de expediente/sentencia fijo y, días o semanas después, lo **reemplazan en la misma URL** con una versión más completa (agregan la tesis, salvamentos o aclaraciones de voto), sin cambiar el número de documento ni, normalmente, la fecha de publicación. Hoy el pipeline de scraping calcula `doc_id` a partir del número de documento + fecha de publicación (`core/utils.py:compute_doc_id`) y, si ya existe un documento con ese `doc_id`, lo salta incondicionalmente (`worker/tasks.py`, `document_exists`) — así que una republicación nunca se detecta ni se vuelve a descargar, sin importar cuántas veces se re-corra el rango de fechas.

Este diseño agrega una verificación automática: cuando un run trae un documento que ya existe, en vez de saltarlo sin más, se compara su tamaño contra el tamaño real que expone el sitio de origen. Si cambió, se descarga la nueva versión y se **archiva la anterior sin perderla** (versionado, no sobreescritura).

Explícitamente en alcance:
- 8 familias con URL de descarga directa (GET): `constitucional`, `jep`, `adr`, `adres`, `ane`, `anh`, `cndj`, `rama_judicial`.
- Verificación automática dentro del flujo normal de un run — no requiere una acción separada ni un job programado aparte.
- Verificación barata primero (`HEAD` al `link.url`, comparando `Content-Length` contra `file_size_bytes` guardado); si el `HEAD` no da un tamaño utilizable, se cae a descargar y comparar el tamaño real.
- Versionado completo: la versión reemplazada se conserva (archivo + metadatos), consultable y descargable después.
- Al reemplazar, `review_status` del documento vuelve a `"pending"` (el contenido cambió, la revisión anterior ya no aplica con certeza).
- El historial de versiones es visible en el modal de previsualización de documentos.
- El conteo de "documentos actualizados por republicación" se ve por fuente en el detalle de cada run (mismo lugar que ya muestra `docs_new`/`docs_errors`).

Explícitamente fuera de alcance (por ahora):
- **Corte Suprema (CSJ) y SAMAI**: su mecanismo de descarga (POST a un endpoint compartido, y JWT indirecto respectivamente) no expone una URL de archivo directa para un `HEAD` barato — verificar cambios ahí requeriría descargar el archivo completo cada vez para comparar, lo cual es demasiado costoso dado el volumen actual (CSJ ya tiene 1003 documentos). Se deja como un problema aparte a resolver después; `checks_for_republication = False` explícito en esas dos familias.
- Notificar a alguien cuando se detecta una republicación (aparte de que quede visible en el run y en el historial de versiones).
- Deduplicar/comprimir versiones antiguas o purgarlas después de N días — se guardan indefinidamente, igual que el resto del almacenamiento de este proyecto.
- Diff visual entre versiones (mostrar qué cambió dentro del documento) — solo se expone el archivo completo de cada versión para descargar.

## Modelo de datos

Nueva tabla `document_versions` — cada fila es una versión **reemplazada** (no incluye la versión actual, que sigue viviendo en `documents`):

```python
class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    storage_bucket = Column(String, nullable=False)
    storage_key = Column(Text, nullable=False)
    content_type = Column(String, nullable=True)
    file_extension = Column(String, nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    converted_format = Column(String, nullable=True)
    source_url = Column(Text, nullable=True)
    downloaded_at = Column(DateTime(timezone=True), nullable=False)  # cuándo se descargó originalmente esta versión
    superseded_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)  # cuándo fue reemplazada
```

`documents.review_status`/`reviewed_at` se resetean a `"pending"`/`NULL` cuando el documento se reemplaza — no se necesita ningún campo nuevo ahí.

`run_sources` gana una columna `docs_updated` (Integer, default 0) — cuenta cuántos documentos se reemplazaron por republicación en ese run, junto a `docs_new`/`docs_errors` ya existentes.

Una sola migración de Alembic cubre ambos cambios (tabla nueva + columna nueva).

## Mecanismo de archivado (clave: no hay que re-descargar el archivo viejo)

Cuando se detecta un cambio de tamaño:

1. **El archivo viejo se queda exactamente donde está** (mismo `storage_bucket`/`storage_key` que ya tenía) — no hay que copiarlo ni volver a subirlo. Solo se crea una fila en `document_versions` que **apunta a esa misma clave**, junto con una copia de los demás metadatos de archivo que tenía el documento en ese momento (`content_type`, `file_size_bytes`, etc.) y su `downloaded_at` original.
2. El archivo **nuevo** se descarga y se sube bajo una **clave distinta** (nunca debe pisar la clave del archivo viejo, que la fila de versión recién creada sigue referenciando) — se distingue con un sufijo (ej. marca de tiempo) antes de la extensión.
3. La fila de `documents` se actualiza con los datos del archivo nuevo (`storage_key`, `file_size_bytes`, `content_type`, etc.), y `review_status`/`reviewed_at` se resetean.

Este orden (archivar referencia → subir lo nuevo con clave distinta → actualizar el documento) es lo que garantiza que la versión vieja nunca se pierde ni se sobreescribe, sin gastar ancho de banda re-descargándola.

## Backend

### `core/scrapers/base.py`

```python
checks_for_republication = True
```

Por defecto `True` (aplica a la mayoría de familias). `ScrapCorteSuprema` (`core/scrapers/families/corte_suprema.py`) y `ScrapTribunales`/SAMAI (`core/scrapers/families/samai.py`) lo sobreescriben a `False` explícitamente.

### `core/downloader.py`

Nueva función, junto a las demás utilidades de descarga:

```python
def check_remote_content_length(url: str, timeout: int = 15) -> Optional[int]:
    """HEAD barato para saber si el archivo remoto cambió de tamaño sin descargarlo.
    Devuelve None si el servidor no expone Content-Length o si la petición falla —
    el llamador debe entonces caer a descargar y comparar el tamaño real."""
    try:
        response = requests.head(url, allow_redirects=True, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code != 200:
            return None
        content_length = response.headers.get("Content-Length")
        return int(content_length) if content_length is not None else None
    except requests.exceptions.RequestException:
        return None
```

### `core/db/repository.py`

- `get_document_by_doc_id(db, doc_id) -> Optional[Document]`
- `archive_and_replace_document(db, document_id, **new_fields) -> Document`: crea la fila de `DocumentVersion` a partir del estado actual del documento, aplica `new_fields` sobre la fila de `Document`, resetea `review_status`/`reviewed_at`, hace commit y devuelve el documento actualizado.
- `list_document_versions(db, document_id) -> list[DocumentVersion]`: ordenado por `superseded_at desc` (la más recientemente reemplazada primero).
- `get_document_version(db, version_id) -> Optional[DocumentVersion]`.

### `worker/tasks.py` — `scrape_source_task`

El bucle de deduplicación cambia de "si existe, saltar" a "si existe, decidir si hace falta reemplazar":

- Para cada documento que el scraper devuelve y que **ya existe** por `doc_id`:
  - Si `scraper.checks_for_republication` es `False` → se salta, comportamiento idéntico al actual.
  - Si es `True` → `check_remote_content_length(doc.link["url"])`. Si el tamaño obtenido coincide con `existing.file_size_bytes` → se salta (sin cambios). Si difiere, o el `HEAD` no dio un tamaño → se agrega a la cola de descarga como **candidato a reemplazo** (no como documento nuevo).
- Los candidatos a reemplazo se descargan con el mismo pool de hilos que los documentos nuevos (mismo `_download_and_upload_one`).
- Tras la descarga de un candidato a reemplazo: si el tamaño real descargado coincide con el que ya tenía el documento (cubre el caso en que el `HEAD` no dio dato mssoluto pero el archivo en realidad no cambió), se descarta sin tocar nada. Si difiere de verdad, se llama a `repository.archive_and_replace_document(...)` con los datos del archivo nuevo, y se cuenta en `docs_updated` (no en `docs_new`).
- `set_run_source_status` al finalizar el run ahora también recibe `docs_updated=docs_updated`.

### `api/schemas.py`

```python
class DocumentVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    document_id: int
    file_size_bytes: Optional[int] = None
    content_type: Optional[str] = None
    downloaded_at: datetime
    superseded_at: datetime
```

`RunSourceOut` gana `docs_updated: int`.

### `api/routers/documents.py`

- `GET /documents/{document_id}/versions` → `list[DocumentVersionOut]`, ordenado más reciente primero.
- `GET /documents/{document_id}/versions/{version_id}/download` → si la versión no existe o no pertenece a ese documento, `404`; si no, `{"url": presigned_url(...)}` con `ResponseContentDisposition` de descarga (mismo patrón que `/bulk-downloads/{id}/download`).

## Frontend

### `api/documents.ts`

```ts
export interface DocumentVersion {
  id: number;
  document_id: number;
  file_size_bytes: number | null;
  content_type: string | null;
  downloaded_at: string;
  superseded_at: string;
}

export function fetchDocumentVersions(documentId: number): Promise<DocumentVersion[]> {
  return apiFetch<DocumentVersion[]>(`/documents/${documentId}/versions`);
}

export function fetchDocumentVersionUrl(documentId: number, versionId: number): Promise<string> {
  return apiFetch<{ url: string }>(`/documents/${documentId}/versions/${versionId}/download`).then((data) => data.url);
}
```

### `components/DocumentPreviewDialog.tsx`

Debajo de la cabecera (título/tipo/fecha), una sección que solo se muestra si el documento tiene versiones anteriores: "N versiones anteriores", cada una con su fecha de reemplazo (`superseded_at`), su tamaño, y un botón "Descargar" que usa `fetchDocumentVersionUrl` + `downloadFromUrl` (mismo patrón ya usado para el ZIP de descarga masiva).

### `pages/RunDetailPage.tsx`

La tabla de fuentes del run gana una columna "Actualizados" mostrando `runSource.docs_updated`, junto a las columnas ya existentes de nuevos/errores.

## Manejo de errores

- **El `HEAD` falla o no da `Content-Length`**: no es un error — dispara el camino de respaldo (descargar y comparar tamaño real), igual que si el tamaño hubiera dado diferente.
- **La descarga de un candidato a reemplazo falla** (red, 404, etc.): se cuenta como error normal en `docs_errors` (mismo camino que ya existe para documentos nuevos), no rompe el resto del run.
- **El tamaño remoto coincide tras la verificación cara** (se descargó completo para comparar y resultó ser igual): se descarta sin generar ninguna versión ni tocar el documento — no es un error, es la confirmación de que no había cambiado.

## Testing

- **Backend**:
  - `tests/test_core_utils.py` o `tests/test_downloader.py`: `check_remote_content_length` — devuelve el entero cuando el servidor responde con `Content-Length`; devuelve `None` si la respuesta no trae el header, si el status no es 200, o si la petición lanza una excepción de red.
  - `tests/test_repository.py`: `archive_and_replace_document` — crea la fila de `DocumentVersion` con los valores previos del documento, actualiza el documento con los nuevos, resetea `review_status`/`reviewed_at`; `list_document_versions` ordena por `superseded_at desc`.
  - `tests/test_tasks.py`: `scrape_source_task` —
    - Un documento que ya existe y cuyo `HEAD` reporta el mismo tamaño: se salta, no se descarga, `docs_new`/`docs_updated` en cero para ese documento.
    - Un documento que ya existe y cuyo tamaño remoto difiere: se descarga, se archiva la versión vieja (con su storage_key original intacto y accesible), el documento se actualiza con el archivo nuevo bajo una clave distinta, `review_status` vuelve a `"pending"`, `docs_updated` se incrementa.
    - Una familia con `checks_for_republication = False`: un documento existente siempre se salta sin hacer ningún `HEAD`, igual que el comportamiento actual.
  - `tests/test_api_documents.py`: `GET /documents/{id}/versions` lista ordenado; `GET /documents/{id}/versions/{version_id}/download` da 404 para una versión de otro documento o inexistente, da la URL firmada para una válida.
- **Frontend**:
  - `api/documents.test.ts`: tests para `fetchDocumentVersions`/`fetchDocumentVersionUrl`.
  - `components/DocumentPreviewDialog.test.tsx`: no muestra la sección de versiones si la lista viene vacía; la muestra con fecha/tamaño/botón de descarga cuando hay versiones; el botón de descarga llama a la URL firmada correcta.
  - `pages/RunDetailPage.test.tsx`: la tabla muestra la columna "Actualizados" con el valor de `docs_updated`.
