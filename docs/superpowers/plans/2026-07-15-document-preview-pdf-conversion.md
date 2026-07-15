# Conversión RTF/DOC/DOCX → PDF para previsualización — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir previsualizar documentos RTF/DOC/DOCX (ej. las providencias de Corte Constitucional) generando un PDF bajo demanda la primera vez que se abre el modal de previsualización, sin afectar en nada la descarga (que siempre sirve el archivo original).

**Architecture:** Nueva columna `preview_storage_key` en `documents` (cachea el PDF ya generado); una nueva tarea de Celery reutiliza el `WordConverter` ya existente (basado en Word/COM) para convertir a PDF bajo demanda; un nuevo endpoint `GET /documents/{id}/preview` decide entre servir el archivo original (si ya es PDF), servir el PDF cacheado, disparar la conversión y esperarla, o responder que no es previsualizable — todo sin tocar `/download`. El frontend amplía qué tipos intenta previsualizar y apunta al nuevo endpoint.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + Celery (ya usado, mismo worker), pywin32/Word COM (ya usado vía `WordConverter`), React + TanStack Query, Vitest + Testing Library + MSW.

## Global Constraints

- `GET /documents/{id}/download` no cambia — siempre sirve `storage_key`/`content_type` originales, sin excepción.
- La conversión es **bajo demanda** (al pedir la previsualización), nunca durante el scraping/run.
- El mecanismo es por **tipo de contenido**, no por fuente: aplica a cualquier documento con `content_type` en `{"application/rtf", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}`.
- Una vez generado, el PDF de previsualización se cachea para siempre en `preview_storage_key` — nunca se regenera automáticamente.
- Timeout esperando la conversión → `504` con detalle `"La vista previa está tardando más de lo esperado, intenta de nuevo"`. Fallo de conversión → `502` con detalle `"No se pudo generar la vista previa"`. Tipo no convertible → `404` con detalle `"Vista previa no disponible para este tipo de archivo"`.
- No se expone `preview_storage_key` en ningún schema de la API (`DocumentOut` no cambia) — es un detalle interno que el frontend nunca lee directamente, solo llama a `/preview`.

---

### Task 1: Columna `preview_storage_key` y función de repositorio

**Files:**
- Modify: `core/db/models.py`
- Modify: `core/db/repository.py`
- Create: `alembic/versions/<revision_id>_add_document_preview_storage_key.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Produces: `Document.preview_storage_key: Optional[str]` (columna nullable); `repository.set_document_preview_key(db: Session, document_id: int, preview_storage_key: str) -> Optional[Document]` — usada por la tarea de Celery (Task 3).

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de `tests/test_repository.py`:

```python
def test_set_document_preview_key_updates_the_column(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-1",
        source_id=source.id,
        title="T-200/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Tutela/T-200-26.rtf",
        content_type="application/rtf",
    )
    assert document.preview_storage_key is None

    updated = repository.set_document_preview_key(
        db_session, document.id, "Corte Constitucional/2026-06-30/Tutela/T-200-26.preview.pdf"
    )

    assert updated.preview_storage_key == "Corte Constitucional/2026-06-30/Tutela/T-200-26.preview.pdf"


def test_set_document_preview_key_returns_none_when_document_missing(db_session):
    from core.db import repository

    assert repository.set_document_preview_key(db_session, 999999, "some/key.pdf") is None
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv\Scripts\pytest tests/test_repository.py -v -k preview_key`
Expected: FAIL — `Document` no tiene `preview_storage_key` y `repository.set_document_preview_key` no existe.

- [ ] **Step 3: Agregar la columna al modelo**

En `core/db/models.py`, dentro de la clase `Document`, agregar esta línea justo después de `converted_format = Column(String, nullable=True)`:

```python
    preview_storage_key = Column(Text, nullable=True)
```

- [ ] **Step 4: Agregar la función de repositorio**

En `core/db/repository.py`, agregar al final del archivo:

```python
def set_document_preview_key(db: Session, document_id: int, preview_storage_key: str) -> Optional[Document]:
    document = db.get(Document, document_id)
    if document is None:
        return None
    document.preview_storage_key = preview_storage_key
    db.commit()
    db.refresh(document)
    return document
```

- [ ] **Step 5: Confirmar que los tests pasan**

Run: `.venv\Scripts\pytest tests/test_repository.py -v -k preview_key`
Expected: 2 passed.

- [ ] **Step 6: Crear y aplicar la migración**

Run: `.venv\Scripts\alembic revision -m "add document preview storage key"`

Completar el archivo generado (el `down_revision` debe apuntar automáticamente a `2da890a73147`, la migración actual más reciente):

```python
def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('documents', sa.Column('preview_storage_key', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('documents', 'preview_storage_key')
```

Run: `.venv\Scripts\alembic upgrade head`
Expected: sin errores.

- [ ] **Step 7: Correr toda la suite de backend**

Run: `.venv\Scripts\pytest -v`
Expected: todo PASS salvo la falla preexistente no relacionada de `test_migrations.py`.

- [ ] **Step 8: Commit**

```bash
git add core/db/models.py core/db/repository.py tests/test_repository.py alembic/versions/*_add_document_preview_storage_key.py
git commit -m "feat: add preview_storage_key column and repository setter"
```

---

### Task 2: `download_file` en `core/storage.py`

**Files:**
- Modify: `core/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Produces: `download_file(bucket: str, key: str, local_path: Path) -> None` — usada por la tarea de Celery (Task 3) para bajar el archivo original antes de convertirlo.

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de `tests/test_storage.py`:

```python
def test_download_file_writes_the_object_to_the_given_path(tmp_path):
    from core.storage import download_file

    local_file = tmp_path / "original.txt"
    local_file.write_text("contenido original")
    bucket, key = upload_file(local_file, "test/download-roundtrip.txt", bucket=TEST_S3_BUCKET, content_type="text/plain")

    destination = tmp_path / "downloaded.txt"
    download_file(bucket, key, destination)

    assert destination.read_text() == "contenido original"
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv\Scripts\pytest tests/test_storage.py -v -k download_file`
Expected: FAIL — `download_file` no existe todavía en `core.storage`.

- [ ] **Step 3: Implementar `download_file`**

En `core/storage.py`, agregar al final del archivo:

```python
def download_file(bucket: str, key: str, local_path: Path) -> None:
    client = _client()
    client.download_file(bucket, key, str(local_path))
```

- [ ] **Step 4: Confirmar que el test pasa**

Run: `.venv\Scripts\pytest tests/test_storage.py -v -k download_file`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add core/storage.py tests/test_storage.py
git commit -m "feat: add download_file helper to fetch an object back from storage"
```

---

### Task 3: Tarea de Celery `generate_document_preview_pdf`

**Files:**
- Modify: `worker/tasks.py`
- Test: `tests/test_tasks.py`

**Interfaces:**
- Consumes: `repository.get_document`, `repository.set_document_preview_key` (Task 1); `core.storage.download_file` (Task 2), `core.storage.upload_file` (ya existente); `core.downloader.WordConverter` (ya existente — `_WORD_FORMATS` ya incluye `"pdf": 17`, no requiere ningún cambio en `core/downloader.py`).
- Produces: `worker.tasks.generate_document_preview_pdf(document_id: int) -> str` (tarea de Celery, registrada como `"worker.generate_document_preview_pdf"`) — usada por el endpoint de la API (Task 4). Devuelve la `preview_storage_key` generada (o ya existente, si se llama dos veces).

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de `tests/test_tasks.py`:

```python
def test_generate_document_preview_pdf_converts_and_saves_the_key(db_session, test_engine, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from core.db import repository
    from worker.tasks import generate_document_preview_pdf

    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})

    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-2",
        source_id=source.id,
        title="T-200/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Tutela/T-200-26.rtf",
        content_type="application/rtf",
    )

    from core.storage import upload_file
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        rtf_path = Path(tmp) / "T-200-26.rtf"
        rtf_path.write_text("contenido rtf de prueba")
        upload_file(rtf_path, document.storage_key, bucket="iurisync-test")

    class _FakeWordConverter:
        def convert(self, input_path, target_format):
            assert target_format == "pdf"
            output_path = input_path.with_suffix(".pdf")
            output_path.write_bytes(b"%PDF-1.4 contenido convertido")
            return output_path

        def quit(self):
            pass

    monkeypatch.setattr("worker.tasks.WordConverter", _FakeWordConverter)
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    result = generate_document_preview_pdf(document.id)

    assert result == "Corte Constitucional/2026-06-30/Tutela/T-200-26.preview.pdf"

    assertion_session = task_session_factory()
    try:
        refreshed = repository.get_document(assertion_session, document.id)
        assert refreshed.preview_storage_key == "Corte Constitucional/2026-06-30/Tutela/T-200-26.preview.pdf"
    finally:
        assertion_session.close()


def test_generate_document_preview_pdf_is_idempotent_when_already_generated(db_session, test_engine, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from core.db import repository
    from worker.tasks import generate_document_preview_pdf

    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-3",
        source_id=source.id,
        title="T-201/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Tutela/T-201-26.rtf",
        content_type="application/rtf",
    )
    repository.set_document_preview_key(db_session, document.id, "already/cached.preview.pdf")

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("no debería intentar convertir de nuevo si ya existe preview_storage_key")

    monkeypatch.setattr("worker.tasks.download_file", _fail_if_called)

    result = generate_document_preview_pdf(document.id)

    assert result == "already/cached.preview.pdf"
```

Add these imports at the top of `tests/test_tasks.py` (alongside the existing ones):

```python
from worker.celery_app import celery_app
from worker.tasks import scrape_source_task, generate_document_preview_pdf
```

(If `celery_app`/`scrape_source_task` are already imported at the top of the file — they are — just add `generate_document_preview_pdf` to that existing import line instead of duplicating it.)

- [ ] **Step 2: Confirmar que fallan**

Run: `.venv\Scripts\pytest tests/test_tasks.py -v -k preview`
Expected: FAIL — `generate_document_preview_pdf` no existe todavía en `worker.tasks`.

- [ ] **Step 3: Implementar la tarea**

En `worker/tasks.py`, cambiar el import de:

```python
from core.downloader import Downloader
```

a:

```python
from core.downloader import Downloader, WordConverter
```

Cambiar:

```python
from core.storage import upload_file
```

a:

```python
from core.storage import download_file, upload_file
```

Agregar al final del archivo:

```python
@celery_app.task(name="worker.generate_document_preview_pdf")
def generate_document_preview_pdf(document_id: int) -> str:
    db = SessionLocal()
    try:
        document = repository.get_document(db, document_id)
        if document is None:
            raise ValueError(f"Documento {document_id} no encontrado")
        if document.preview_storage_key:
            return document.preview_storage_key

        with tempfile.TemporaryDirectory(prefix=f"preview_{document_id}_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            extension = Path(document.storage_key).suffix
            local_path = tmp_path / f"original{extension}"
            download_file(document.storage_bucket, document.storage_key, local_path)

            converter = WordConverter()
            try:
                pdf_path = converter.convert(local_path, "pdf")
            finally:
                converter.quit()

            base_key = document.storage_key.rsplit(".", 1)[0] if "." in document.storage_key else document.storage_key
            preview_key = f"{base_key}.preview.pdf"
            upload_file(pdf_path, preview_key, bucket=document.storage_bucket, content_type="application/pdf")

        repository.set_document_preview_key(db, document_id, preview_key)
        return preview_key
    finally:
        db.close()
```

- [ ] **Step 4: Confirmar que los tests pasan**

Run: `.venv\Scripts\pytest tests/test_tasks.py -v -k preview`
Expected: 2 passed.

- [ ] **Step 5: Correr toda la suite de backend**

Run: `.venv\Scripts\pytest -v`
Expected: todo PASS salvo la falla preexistente no relacionada de `test_migrations.py`.

- [ ] **Step 6: Commit**

```bash
git add worker/tasks.py tests/test_tasks.py
git commit -m "feat: add generate_document_preview_pdf Celery task"
```

---

### Task 4: Endpoint `GET /documents/{id}/preview`

**Files:**
- Modify: `api/routers/documents.py`
- Test: `tests/test_api_documents.py`

**Interfaces:**
- Consumes: `worker.tasks.generate_document_preview_pdf` (Task 3, invocado vía `.delay(...).get(timeout=...)`); `repository.get_document`, `core.storage.presigned_url` (ya usados por `/download`).
- Produces: endpoint `GET /documents/{document_id}/preview` — consumido por el frontend (Task 5).

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/test_api_documents.py`:

```python
def test_preview_pdf_document_redirects_to_original_file(api_client, auth_header, db_session, monkeypatch):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-pdf",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-02-01/Sentencia/T-065-24.pdf",
        content_type="application/pdf",
    )

    monkeypatch.setattr("api.routers.documents.presigned_url", lambda bucket, key: f"https://signed.example.com/{key}")

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header, follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "https://signed.example.com/Corte Constitucional/2024-02-01/Sentencia/T-065-24.pdf"


def test_preview_rtf_document_with_cached_preview_redirects_without_calling_celery(api_client, auth_header, db_session, monkeypatch):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-cached",
        source_id=source.id,
        title="T-200/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Tutela/T-200-26.rtf",
        content_type="application/rtf",
    )
    repository.set_document_preview_key(db_session, document.id, "Corte Constitucional/2026-06-30/Tutela/T-200-26.preview.pdf")

    monkeypatch.setattr("api.routers.documents.presigned_url", lambda bucket, key: f"https://signed.example.com/{key}")

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("no debería encolar la tarea si ya hay un preview cacheado")

    monkeypatch.setattr("api.routers.documents.generate_document_preview_pdf", _fail_if_called)

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header, follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "https://signed.example.com/Corte Constitucional/2026-06-30/Tutela/T-200-26.preview.pdf"


def test_preview_rtf_document_without_cache_triggers_conversion_and_redirects(api_client, auth_header, db_session, monkeypatch):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-new",
        source_id=source.id,
        title="T-202/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Tutela/T-202-26.rtf",
        content_type="application/rtf",
    )

    monkeypatch.setattr("api.routers.documents.presigned_url", lambda bucket, key: f"https://signed.example.com/{key}")

    class _FakeAsyncResult:
        def get(self, timeout=None):
            return "Corte Constitucional/2026-06-30/Tutela/T-202-26.preview.pdf"

    class _FakeTask:
        def delay(self, document_id):
            return _FakeAsyncResult()

    monkeypatch.setattr("api.routers.documents.generate_document_preview_pdf", _FakeTask())

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header, follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "https://signed.example.com/Corte Constitucional/2026-06-30/Tutela/T-202-26.preview.pdf"


def test_preview_returns_504_when_conversion_task_times_out(api_client, auth_header, db_session, monkeypatch):
    from celery.exceptions import TimeoutError as CeleryTimeoutError

    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-timeout",
        source_id=source.id,
        title="T-203/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Tutela/T-203-26.rtf",
        content_type="application/rtf",
    )

    class _FakeAsyncResult:
        def get(self, timeout=None):
            raise CeleryTimeoutError()

    class _FakeTask:
        def delay(self, document_id):
            return _FakeAsyncResult()

    monkeypatch.setattr("api.routers.documents.generate_document_preview_pdf", _FakeTask())

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header, follow_redirects=False)

    assert response.status_code == 504
    assert response.json()["detail"] == "La vista previa está tardando más de lo esperado, intenta de nuevo"


def test_preview_returns_502_when_conversion_fails(api_client, auth_header, db_session, monkeypatch):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-fail",
        source_id=source.id,
        title="T-204/26",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Tutela/T-204-26.rtf",
        content_type="application/rtf",
    )

    class _FakeAsyncResult:
        def get(self, timeout=None):
            raise RuntimeError("Word no disponible")

    class _FakeTask:
        def delay(self, document_id):
            return _FakeAsyncResult()

    monkeypatch.setattr("api.routers.documents.generate_document_preview_pdf", _FakeTask())

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header, follow_redirects=False)

    assert response.status_code == 502
    assert response.json()["detail"] == "No se pudo generar la vista previa"


def test_preview_returns_404_for_a_non_convertible_content_type(api_client, auth_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-preview-unsupported",
        source_id=source.id,
        title="Reporte",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2026-06-30/Otro/reporte.txt",
        content_type="text/plain",
    )

    response = api_client.get(f"/documents/{document.id}/preview", headers=auth_header, follow_redirects=False)

    assert response.status_code == 404
    assert response.json()["detail"] == "Vista previa no disponible para este tipo de archivo"
```

- [ ] **Step 2: Confirmar que fallan**

Run: `.venv\Scripts\pytest tests/test_api_documents.py -v -k preview`
Expected: FAIL — el endpoint `/documents/{document_id}/preview` no existe todavía (404 genérico de FastAPI para ruta no encontrada, no el 404 esperado del test).

- [ ] **Step 3: Implementar el endpoint**

En `api/routers/documents.py`, cambiar el import de:

```python
from core.storage import presigned_url
```

a:

```python
from celery.exceptions import TimeoutError as CeleryTimeoutError

from core.storage import presigned_url
from worker.tasks import generate_document_preview_pdf
```

Agregar, después de la constante del router (`router = APIRouter(...)`) y antes del primer endpoint:

```python
# Tipos que requieren conversión bajo demanda (application/pdf se maneja aparte,
# como passthrough directo, antes de siquiera consultar este set).
CONVERTIBLE_CONTENT_TYPES = {
    "application/rtf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
PREVIEW_TASK_TIMEOUT_SECONDS = 30
```

Agregar al final del archivo, después del endpoint `download_document`:

```python
@router.get("/documents/{document_id}/preview")
def preview_document(document_id: int, db: Session = Depends(get_db)):
    document = repository.get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    if document.content_type == "application/pdf":
        url = presigned_url(document.storage_bucket, document.storage_key)
        return RedirectResponse(url)

    if document.content_type not in CONVERTIBLE_CONTENT_TYPES:
        raise HTTPException(status_code=404, detail="Vista previa no disponible para este tipo de archivo")

    if document.preview_storage_key:
        url = presigned_url(document.storage_bucket, document.preview_storage_key)
        return RedirectResponse(url)

    try:
        preview_key = generate_document_preview_pdf.delay(document_id).get(timeout=PREVIEW_TASK_TIMEOUT_SECONDS)
    except CeleryTimeoutError:
        raise HTTPException(
            status_code=504, detail="La vista previa está tardando más de lo esperado, intenta de nuevo"
        )
    except Exception:
        raise HTTPException(status_code=502, detail="No se pudo generar la vista previa")

    url = presigned_url(document.storage_bucket, preview_key)
    return RedirectResponse(url)
```

- [ ] **Step 4: Confirmar que los tests pasan**

Run: `.venv\Scripts\pytest tests/test_api_documents.py -v -k preview`
Expected: 6 passed.

- [ ] **Step 5: Correr toda la suite de backend**

Run: `.venv\Scripts\pytest -v`
Expected: todo PASS salvo la falla preexistente no relacionada de `test_migrations.py`.

- [ ] **Step 6: Commit**

```bash
git add api/routers/documents.py tests/test_api_documents.py
git commit -m "feat: add GET /documents/{id}/preview with on-demand PDF conversion"
```

---

### Task 5: Frontend — ampliar la previsualización a RTF/DOC/DOCX

**Files:**
- Modify: `frontend/src/api/documents.ts`
- Modify: `frontend/src/api/documents.test.ts`
- Modify: `frontend/src/components/DocumentPreviewDialog.tsx`
- Modify: `frontend/src/components/DocumentPreviewDialog.test.tsx`
- Modify: `frontend/src/pages/DocumentsPage.test.tsx` (un mock inline que exercita el diálogo real necesita apuntar al nuevo endpoint)

**Interfaces:**
- Produces: `fetchDocumentPreviewBlob(id: number): Promise<Blob>` en `api/documents.ts` — usada por `DocumentPreviewDialog`.
- `fetchDocumentBlob` (ya existente) sigue apuntando a `/download`, sin cambios de comportamiento — sigue siendo la que usa `downloadDocumentFile`.

- [ ] **Step 1: Escribir el test que falla para `fetchDocumentPreviewBlob`**

En `frontend/src/api/documents.test.ts`, agregar (después del `describe("fetchDocumentBlob", ...)` existente):

```typescript
describe("fetchDocumentPreviewBlob", () => {
  it("fetches the preview content as a Blob", async () => {
    server.use(
      http.get(`${BASE_URL}/documents/7/preview`, () => new HttpResponse("contenido pdf", { headers: { "Content-Type": "application/pdf" } }))
    );

    const blob = await fetchDocumentPreviewBlob(7);

    expect(blob).toBeInstanceOf(Blob);
    expect(await blob.text()).toBe("contenido pdf");
  });

  it("throws when the preview request fails", async () => {
    server.use(http.get(`${BASE_URL}/documents/8/preview`, () => new HttpResponse(null, { status: 502 })));

    await expect(fetchDocumentPreviewBlob(8)).rejects.toThrow();
  });
});
```

Y actualizar el import de:

```typescript
import { buildDownloadFilename, downloadDocumentFile, fetchDocument, fetchDocumentBlob, fetchDocuments } from "./documents";
```

a:

```typescript
import { buildDownloadFilename, downloadDocumentFile, fetchDocument, fetchDocumentBlob, fetchDocumentPreviewBlob, fetchDocuments } from "./documents";
```

- [ ] **Step 2: Confirmar que falla**

Run: `cd frontend && npm test -- --run src/api/documents.test.ts`
Expected: FAIL — `fetchDocumentPreviewBlob` no existe todavía.

- [ ] **Step 3: Implementar `fetchDocumentPreviewBlob`**

En `frontend/src/api/documents.ts`, reemplazar la función `fetchDocumentBlob` completa por (factoriza el fetch compartido y agrega la nueva función):

```typescript
async function fetchBlobFrom(path: string, errorMessage: string): Promise<Blob> {
  const token = getStoredToken();
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${BASE_URL}${path}`, { headers });
  if (!response.ok) {
    throw new Error(errorMessage);
  }
  return response.blob();
}

export function fetchDocumentBlob(id: number): Promise<Blob> {
  return fetchBlobFrom(`/documents/${id}/download`, "No se pudo cargar el documento");
}

export function fetchDocumentPreviewBlob(id: number): Promise<Blob> {
  return fetchBlobFrom(`/documents/${id}/preview`, "No se pudo cargar la vista previa");
}
```

(`downloadDocumentFile` no cambia — sigue llamando a `fetchDocumentBlob`, que sigue apuntando a `/download`.)

- [ ] **Step 4: Confirmar que los tests pasan**

Run: `cd frontend && npm test -- --run src/api/documents.test.ts`
Expected: todos PASS, incluyendo los 2 nuevos.

- [ ] **Step 5: Actualizar los tests de `DocumentPreviewDialog` para apuntar a `/preview`**

En `frontend/src/components/DocumentPreviewDialog.test.tsx`, cambiar la función helper `mockBlob` de:

```typescript
function mockBlob(id: number, content = "contenido") {
  server.use(
    http.get(`${BASE_URL}/documents/${id}/download`, () => new HttpResponse(content, { headers: { "Content-Type": "application/pdf" } }))
  );
}
```

a:

```typescript
function mockBlob(id: number, content = "contenido") {
  server.use(
    http.get(`${BASE_URL}/documents/${id}/preview`, () => new HttpResponse(content, { headers: { "Content-Type": "application/pdf" } }))
  );
}
```

Esto cubre a los tests que usan el helper `mockBlob` — pero uno de los 10 tests existentes ("shows a retry option when loading the preview fails, and retrying refetches it") no usa `mockBlob`: arma su propio mock inline apuntando directamente a `/documents/1/download` para simular un primer intento fallido y un reintento exitoso. Ese mock inline también debe apuntar al nuevo endpoint. Cambiar, dentro de ese test:

```typescript
    server.use(
      http.get(`${BASE_URL}/documents/1/download`, () => {
        attempts += 1;
        if (attempts === 1) return new HttpResponse(null, { status: 500 });
        return new HttpResponse("contenido", { headers: { "Content-Type": "application/pdf" } });
      })
    );
```

a:

```typescript
    server.use(
      http.get(`${BASE_URL}/documents/1/preview`, () => {
        attempts += 1;
        if (attempts === 1) return new HttpResponse(null, { status: 500 });
        return new HttpResponse("contenido", { headers: { "Content-Type": "application/pdf" } });
      })
    );
```

Con eso, los 10 tests ya existentes siguen pasando apuntando al nuevo endpoint — ninguno depende del `content_type` original del documento para decidir si se llama al blob, solo de que sea `"application/pdf"` (el único tipo previsualizable hasta ahora). Después de este cambio, agregar los 2 tests nuevos que prueban el tipo ampliado:

```typescript
it("renders an iframe for a previewable RTF document (via /preview, not /download)", async () => {
  const documents = [makeDocument({ id: 9, title: "Doc RTF", content_type: "application/rtf" })];
  mockBlob(9);

  renderDialog(documents, 0);

  expect(await screen.findByTitle("Vista previa de Doc RTF")).toBeInTheDocument();
});

it("still shows the fallback message for a genuinely non-previewable type", async () => {
  const documents = [makeDocument({ id: 10, title: "Doc Texto", content_type: "text/plain" })];

  renderDialog(documents, 0);

  expect(await screen.findByText("Vista previa no disponible para este tipo de archivo.")).toBeInTheDocument();
});
```

- [ ] **Step 6: Confirmar que fallan**

Run: `cd frontend && npm test -- --run src/components/DocumentPreviewDialog.test.tsx`
Expected: FAIL — el componente todavía solo intenta previsualizar `content_type === "application/pdf"`, así que el nuevo test de RTF cae en el fallback en vez de mostrar el iframe.

- [ ] **Step 7: Ampliar `DocumentPreviewDialog.tsx`**

Cambiar el import de:

```tsx
import { buildDownloadFilename, downloadDocumentFile, fetchDocumentBlob, updateDocumentReviewStatus } from "../api/documents";
```

a:

```tsx
import { buildDownloadFilename, downloadDocumentFile, fetchDocumentPreviewBlob, updateDocumentReviewStatus } from "../api/documents";
```

Agregar, justo antes de `export function DocumentPreviewDialog(...)`:

```tsx
const PREVIEWABLE_CONTENT_TYPES = new Set([
  "application/pdf",
  "application/rtf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);
```

Cambiar:

```tsx
  const currentDocument = documentsSnapshot[currentIndex];
  const isPdf = currentDocument?.content_type === "application/pdf";
  const isFirst = currentIndex === 0;
  const isLast = currentIndex === documentsSnapshot.length - 1;

  const blobQuery = useQuery({
    queryKey: ["document-blob", currentDocument?.id],
    queryFn: () => fetchDocumentBlob(currentDocument!.id),
    enabled: open && !!currentDocument && isPdf,
  });
```

a:

```tsx
  const currentDocument = documentsSnapshot[currentIndex];
  const isPreviewable = !!currentDocument && PREVIEWABLE_CONTENT_TYPES.has(currentDocument.content_type ?? "");
  const isFirst = currentIndex === 0;
  const isLast = currentIndex === documentsSnapshot.length - 1;

  const blobQuery = useQuery({
    queryKey: ["document-preview-blob", currentDocument?.id],
    queryFn: () => fetchDocumentPreviewBlob(currentDocument!.id),
    enabled: open && !!currentDocument && isPreviewable,
  });
```

Cambiar la línea del render que decide qué mostrar (`{isPdf ? (` ... `) : (`) de:

```tsx
          {isPdf ? (
```

a:

```tsx
          {isPreviewable ? (
```

(El resto del bloque —el manejo de error con `ErrorBanner`/"Reintentar", el estado "Cargando…", el `<iframe>`, y el fallback de descarga— no cambia: ya cubre correctamente los nuevos casos 502/504/404 que puede devolver `/preview`, porque todos caen en la misma rama `blobQuery.isError`.)

- [ ] **Step 8: Confirmar que los tests pasan**

Run: `cd frontend && npm test -- --run src/components/DocumentPreviewDialog.test.tsx`
Expected: 12 passed (10 existentes + 2 nuevos).

- [ ] **Step 9: Corregir el mock inline de `DocumentsPage.test.tsx`**

`frontend/src/pages/DocumentsPage.test.tsx` tiene un test, `"opens the preview dialog with the correct document when Previsualizar is clicked"`, que monta `DocumentPreviewDialog` de verdad (a través de `DocumentsPage`) y mockea directamente `/documents/2/download` para satisfacer su carga del blob. Como el diálogo ahora llama a `/preview` (incluso para PDFs), ese mock debe apuntar al nuevo endpoint. Cambiar, dentro de ese test:

```typescript
      http.get(`${BASE_URL}/documents/2/download`, () => new HttpResponse("x", { headers: { "Content-Type": "application/pdf" } }))
```

a:

```typescript
      http.get(`${BASE_URL}/documents/2/preview`, () => new HttpResponse("x", { headers: { "Content-Type": "application/pdf" } }))
```

(El otro mock de ese archivo, `http.get(\`${BASE_URL}/documents/1/download\`, ...)` en el test `"triggers a download when the download button is clicked"`, no cambia — ese sigue probando el botón "Descargar", que sigue usando `/download` sin ningún cambio.)

Run: `cd frontend && npm test -- --run src/pages/DocumentsPage.test.tsx`
Expected: todos PASS.

- [ ] **Step 10: Correr toda la suite de frontend y el build**

Run: `cd frontend && npm test -- --run`
Expected: todos PASS.

Run: `cd frontend && npm run build`
Expected: `tsc -b` y `vite build` sin errores.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/api/documents.ts frontend/src/api/documents.test.ts frontend/src/components/DocumentPreviewDialog.tsx frontend/src/components/DocumentPreviewDialog.test.tsx frontend/src/pages/DocumentsPage.test.tsx
git commit -m "feat: preview RTF/DOC/DOCX documents via the new /preview endpoint"
```
