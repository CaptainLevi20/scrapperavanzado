# Sincronizar el nombre del archivo en MinIO con el nombre canónico — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el archivo real guardado en MinIO (`storage_key` de cada `Document` y cada `DocumentVersion`) siempre refleje el nombre canónico vigente de ese documento — inicialmente (backfill) y de ahí en adelante (renombrado automático en cascada + barrido nocturno de respaldo).

**Architecture:** Un motor central puro (`core/storage_sync.py`) calcula el nombre esperado con las funciones ya existentes de `core/naming.py`, y usa `core.utils.rekey_filename` + `core.storage.rename_object` (ambas ya existen) para renombrar solo lo que no coincida. Tres puntos de disparo (actuación nueva durante una descarga, republicación, edición manual de título) encolan tareas Celery que llaman a ese mismo motor; una tarea nocturna programada corre el mismo motor sobre todo el archivo como red de seguridad, y también sirve como el backfill inicial.

**Tech Stack:** Python/SQLAlchemy/Alembic (sin migración nueva — no hay columnas nuevas), Celery (tareas + beat), boto3/MinIO vía `core/storage.py`.

## Global Constraints

- **No se toca `title` ni `doc_id`, ni la detección de republicación** — solo `storage_key` (de `Document` y `DocumentVersion`).
- **Un renombrado fallido nunca bloquea ni hace fallar** la descarga, la republicación o la edición de título que lo disparó — todo disparo es un `.delay()` independiente (fire-and-forget).
- **`storage_key` en la base solo se actualiza si el renombrado en MinIO ya tuvo éxito** — base de datos y MinIO nunca quedan en desacuerdo entre sí.
- **Comentarios y textos en español**, siguiendo el estilo del repo.
- **Pruebas:** `python -m pytest <archivo/patrón> -v` (suites de BD dirigidas, no en paralelo ni la suite completa).
- **Producción:** fusionar PR → CI construye imágenes GHCR → `docker compose pull/up` → correr el backfill una vez (no hay migración de base de datos que correr).

---

### Task 1: `repository.update_document_version_storage_key`

**Files:**
- Modify: `core/db/repository.py:958-965` (justo después de `update_document_storage_key`)
- Test: `tests/test_repository.py` (al final del archivo, ~línea 1695)

**Interfaces:**
- Produces: `update_document_version_storage_key(db: Session, version_id: int, storage_key: str) -> Optional[DocumentVersion]`

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de `tests/test_repository.py`:

```python
def test_update_document_version_storage_key_updates_and_returns_the_version(db_session):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
    doc = repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="rad-1",
        storage_bucket="iurisync-test", storage_key="v1.pdf",
    )
    repository.archive_and_replace_document(db_session, doc.id, storage_bucket="iurisync-test", storage_key="v2.pdf")
    [version] = repository.list_document_versions(db_session, doc.id)

    updated = repository.update_document_version_storage_key(db_session, version.id, "renombrado.pdf")

    assert updated.storage_key == "renombrado.pdf"
    db_session.refresh(version)
    assert version.storage_key == "renombrado.pdf"


def test_update_document_version_storage_key_returns_none_when_missing(db_session):
    assert repository.update_document_version_storage_key(db_session, 999999, "x.pdf") is None
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `python -m pytest tests/test_repository.py -k update_document_version_storage_key -v`
Expected: FAIL (`AttributeError: module 'core.db.repository' has no attribute 'update_document_version_storage_key'`).

- [ ] **Step 3: Implementar la función**

En `core/db/repository.py`, justo después de `update_document_storage_key` (línea 965, antes de la línea en blanco que precede a `purge_documents_for_source`):

```python
def update_document_version_storage_key(db: Session, version_id: int, storage_key: str) -> Optional[DocumentVersion]:
    version = db.get(DocumentVersion, version_id)
    if version is None:
        return None
    version.storage_key = storage_key
    db.commit()
    db.refresh(version)
    return version
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `python -m pytest tests/test_repository.py -k update_document_version_storage_key -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add core/db/repository.py tests/test_repository.py
git commit -m "feat(repo): update_document_version_storage_key"
```

---

### Task 2: `repository.list_documents_by_title_within_family`

**Files:**
- Modify: `core/db/repository.py:557-588` (justo después de `actuacion_counts_by_title`)
- Test: `tests/test_repository.py`

**Interfaces:**
- Produces: `list_documents_by_title_within_family(db: Session, family_key: str, title: str) -> list[Document]`

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de `tests/test_repository.py`:

```python
def test_list_documents_by_title_within_family_scopes_by_family(db_session):
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    repository.create_source_family(db_session, key="jep", display_name="JEP")
    rama_source = repository.create_source(db_session, family_key="rama_judicial", name="Tribunal", family_params={})
    jep_source = repository.create_source(db_session, family_key="jep", name="JEP", family_params={})

    shared_title = "T_BTA_11001_31_03_048_2022_00418_02"
    doc1 = repository.insert_document(
        db_session, doc_id="d1", source_id=rama_source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    doc2 = repository.insert_document(
        db_session, doc_id="d2", source_id=rama_source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    # Mismo texto de título, pero en otra familia — no debe aparecer.
    repository.insert_document(
        db_session, doc_id="d3", source_id=jep_source.id, title=shared_title,
        storage_bucket="iurisync-test", storage_key="c.pdf",
    )

    result = repository.list_documents_by_title_within_family(db_session, "rama_judicial", shared_title)

    assert {d.id for d in result} == {doc1.id, doc2.id}


def test_list_documents_by_title_within_family_returns_empty_list_when_no_match(db_session):
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    repository.create_source(db_session, family_key="rama_judicial", name="Tribunal", family_params={})

    assert repository.list_documents_by_title_within_family(db_session, "rama_judicial", "no-existe") == []
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `python -m pytest tests/test_repository.py -k list_documents_by_title_within_family -v`
Expected: FAIL (`AttributeError`).

- [ ] **Step 3: Implementar la función**

En `core/db/repository.py`, justo después de `actuacion_counts_by_title` (después de la línea 587 `return counts`):

```python
def list_documents_by_title_within_family(db: Session, family_key: str, title: str) -> list[Document]:
    stmt = (
        select(Document)
        .join(Source, Source.id == Document.source_id)
        .where(Source.family_key == family_key, Document.title == title)
    )
    return list(db.scalars(stmt).all())
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `python -m pytest tests/test_repository.py -k list_documents_by_title_within_family -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add core/db/repository.py tests/test_repository.py
git commit -m "feat(repo): list_documents_by_title_within_family"
```

---

### Task 3: `core/storage_sync.py` — `reconcile_document`

**Files:**
- Create: `core/storage_sync.py`
- Test: `tests/test_storage_sync.py`

**Interfaces:**
- Consumes: `core.naming.nombre_documento(document, family_key, tiene_actuaciones) -> str` (Task 1 del feature anterior, ya existe), `core.utils.rekey_filename(storage_key, nombre) -> str` (ya existe), `core.storage.rename_object(bucket, old_key, new_key) -> None` (ya existe), `repository.update_document_storage_key` (ya existe).
- Produces: `reconcile_document(db: Session, document: Document, family_key: Optional[str], tiene_actuaciones: bool) -> bool` (True si renombró).

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_storage_sync.py`:

```python
from core.db import repository
import core.storage_sync as storage_sync


def _rama_judicial_source(db_session):
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    return repository.create_source(db_session, family_key="rama_judicial", name="Tribunal", family_params={})


def test_reconcile_document_renames_when_the_stored_key_does_not_match(db_session, monkeypatch):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T_SANT_68001_33_33_007_2025_00290_02",
        storage_bucket="iurisync-test", storage_key="Rama Judicial/2026-08-06/Auto/placeholder.pdf",
    )

    renamed = []
    monkeypatch.setattr(storage_sync, "rename_object", lambda bucket, old_key, new_key: renamed.append((bucket, old_key, new_key)))

    result = storage_sync.reconcile_document(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert result is True
    assert renamed == [(
        "iurisync-test",
        "Rama Judicial/2026-08-06/Auto/placeholder.pdf",
        "Rama Judicial/2026-08-06/Auto/T_SANT_68001_33_33_007_2025_00290_02.pdf",
    )]
    db_session.refresh(doc)
    assert doc.storage_key == "Rama Judicial/2026-08-06/Auto/T_SANT_68001_33_33_007_2025_00290_02.pdf"


def test_reconcile_document_does_nothing_when_the_stored_key_already_matches(db_session, monkeypatch):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T-123-24",
        storage_bucket="iurisync-test", storage_key="carpeta/T-123-24.pdf",
    )

    called = []
    monkeypatch.setattr(storage_sync, "rename_object", lambda *a: called.append(a))

    result = storage_sync.reconcile_document(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert result is False
    assert called == []


def test_reconcile_document_logs_and_returns_false_when_rename_fails(db_session, monkeypatch, caplog):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T_SANT_68001_33_33_007_2025_00290_02",
        storage_bucket="iurisync-test", storage_key="Rama Judicial/2026-08-06/Auto/placeholder.pdf",
    )

    def _boom(bucket, old_key, new_key):
        raise RuntimeError("MinIO no disponible")

    monkeypatch.setattr(storage_sync, "rename_object", _boom)

    result = storage_sync.reconcile_document(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert result is False
    db_session.refresh(doc)
    assert doc.storage_key == "Rama Judicial/2026-08-06/Auto/placeholder.pdf"  # sin cambios
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `python -m pytest tests/test_storage_sync.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'core.storage_sync'`).

- [ ] **Step 3: Implementar `core/storage_sync.py`**

```python
import logging
from typing import Optional

from sqlalchemy.orm import Session

from core.db import repository
from core.db.models import Document
from core.naming import nombre_documento
from core.storage import rename_object
from core.utils import rekey_filename

logger = logging.getLogger(__name__)


def reconcile_document(db: Session, document: Document, family_key: Optional[str], tiene_actuaciones: bool) -> bool:
    """Renombra en MinIO el archivo de `document` si su storage_key actual no
    coincide con su nombre canónico vigente. Devuelve True solo si el
    renombrado se ejecutó con éxito y storage_key quedó actualizado en la
    base — una falla se registra en el log y no propaga (ver Global
    Constraints del plan: nunca bloquea al llamador)."""
    nombre_esperado = nombre_documento(document, family_key, tiene_actuaciones)
    nueva_key = rekey_filename(document.storage_key, nombre_esperado)
    if nueva_key == document.storage_key:
        return False
    try:
        rename_object(document.storage_bucket, document.storage_key, nueva_key)
    except Exception as exc:
        logger.warning("No se pudo renombrar el documento %s en MinIO: %s", document.id, exc)
        return False
    repository.update_document_storage_key(db, document.id, nueva_key)
    return True
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `python -m pytest tests/test_storage_sync.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add core/storage_sync.py tests/test_storage_sync.py
git commit -m "feat(storage-sync): reconcile_document"
```

---

### Task 4: `core/storage_sync.py` — `reconcile_document_versions`

**Files:**
- Modify: `core/storage_sync.py`
- Test: `tests/test_storage_sync.py`

**Interfaces:**
- Consumes: `core.naming.nombre_version(document, version, family_key, tiene_actuaciones) -> str` (ya existe), `repository.list_document_versions` (ya existe), `repository.update_document_version_storage_key` (Task 1).
- Produces: `reconcile_document_versions(db: Session, document: Document, family_key: Optional[str], tiene_actuaciones: bool) -> int` (cantidad de versiones renombradas).

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_storage_sync.py`:

```python
def test_reconcile_document_versions_renames_each_archived_version(db_session, monkeypatch):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T-123-24",
        storage_bucket="iurisync-test", storage_key="carpeta/v3.pdf",
    )
    repository.archive_and_replace_document(db_session, doc.id, storage_bucket="iurisync-test", storage_key="carpeta/v1-viejo.pdf")
    doc = repository.get_document(db_session, doc.id)
    repository.archive_and_replace_document(db_session, doc.id, storage_bucket="iurisync-test", storage_key="carpeta/v2-viejo.pdf")
    doc = repository.get_document(db_session, doc.id)

    renamed = []
    monkeypatch.setattr(storage_sync, "rename_object", lambda bucket, old_key, new_key: renamed.append((old_key, new_key)))

    count = storage_sync.reconcile_document_versions(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert count == 2
    versions = {v.storage_key for v in repository.list_document_versions(db_session, doc.id)}
    assert versions == {"carpeta/T-123-24_v1.pdf", "carpeta/T-123-24_v2.pdf"}


def test_reconcile_document_versions_returns_zero_when_document_has_no_history(db_session, monkeypatch):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T-123-24",
        storage_bucket="iurisync-test", storage_key="carpeta/T-123-24.pdf",
    )

    monkeypatch.setattr(storage_sync, "rename_object", lambda *a: (_ for _ in ()).throw(AssertionError("no debería llamarse")))

    count = storage_sync.reconcile_document_versions(db_session, doc, "rama_judicial", tiene_actuaciones=False)

    assert count == 0
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `python -m pytest tests/test_storage_sync.py -k reconcile_document_versions -v`
Expected: FAIL (`AttributeError: module 'core.storage_sync' has no attribute 'reconcile_document_versions'`).

- [ ] **Step 3: Implementar la función**

En `core/storage_sync.py`, actualizar el import de `core.naming` para incluir `nombre_version`, y agregar la función al final del archivo:

```python
from core.naming import nombre_documento, nombre_version
```

```python
def reconcile_document_versions(db: Session, document: Document, family_key: Optional[str], tiene_actuaciones: bool) -> int:
    """Igual que reconcile_document, pero para cada versión archivada de
    `document`. Devuelve cuántas se renombraron con éxito."""
    renombradas = 0
    for version in repository.list_document_versions(db, document.id):
        nombre_esperado = nombre_version(document, version, family_key, tiene_actuaciones)
        nueva_key = rekey_filename(version.storage_key, nombre_esperado)
        if nueva_key == version.storage_key:
            continue
        try:
            rename_object(version.storage_bucket, version.storage_key, nueva_key)
        except Exception as exc:
            logger.warning("No se pudo renombrar la versión %s en MinIO: %s", version.id, exc)
            continue
        repository.update_document_version_storage_key(db, version.id, nueva_key)
        renombradas += 1
    return renombradas
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `python -m pytest tests/test_storage_sync.py -v`
Expected: PASS (5 tests en total).

- [ ] **Step 5: Commit**

```bash
git add core/storage_sync.py tests/test_storage_sync.py
git commit -m "feat(storage-sync): reconcile_document_versions"
```

---

### Task 5: `core/storage_sync.py` — `reconcile_title_group`

**Files:**
- Modify: `core/storage_sync.py`
- Test: `tests/test_storage_sync.py`

**Interfaces:**
- Consumes: `repository.list_documents_by_title_within_family` (Task 2), `reconcile_document` (Task 3), `reconcile_document_versions` (Task 4).
- Produces: `reconcile_title_group(db: Session, family_key: str, title: str) -> dict` con claves `documentos_renombrados` y `versiones_renombradas`.

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_storage_sync.py`:

```python
def test_reconcile_title_group_gives_full_date_to_every_sibling_when_there_are_two(db_session, monkeypatch):
    from datetime import date

    source = _rama_judicial_source(db_session)
    shared_title = "T_SANT_68001_33_33_007_2025_00290_02"
    doc1 = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title=shared_title, f_providencia=date(2026, 8, 6),
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder1.pdf",
    )
    doc2 = repository.insert_document(
        db_session, doc_id="d2", source_id=source.id, title=shared_title, f_providencia=date(2026, 8, 20),
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder2.pdf",
    )

    monkeypatch.setattr(storage_sync, "rename_object", lambda *a: None)

    result = storage_sync.reconcile_title_group(db_session, "rama_judicial", shared_title)

    assert result == {"documentos_renombrados": 2, "versiones_renombradas": 0}
    db_session.refresh(doc1)
    db_session.refresh(doc2)
    assert doc1.storage_key == "carpeta/T_SANT_68001_33_33_007_2025_00290_02_20260806.pdf"
    assert doc2.storage_key == "carpeta/T_SANT_68001_33_33_007_2025_00290_02_20260820.pdf"


def test_reconcile_title_group_gives_year_only_when_there_is_a_single_document(db_session, monkeypatch):
    from datetime import date

    source = _rama_judicial_source(db_session)
    title = "T_CUND_25307_33_33_003_2024_00094_01"
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title=title, f_providencia=date(2026, 3, 15),
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder.pdf",
    )

    monkeypatch.setattr(storage_sync, "rename_object", lambda *a: None)

    result = storage_sync.reconcile_title_group(db_session, "rama_judicial", title)

    assert result == {"documentos_renombrados": 1, "versiones_renombradas": 0}
    db_session.refresh(doc)
    assert doc.storage_key == "carpeta/T_CUND_25307_33_33_003_2024_00094_01_2026.pdf"
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `python -m pytest tests/test_storage_sync.py -k reconcile_title_group -v`
Expected: FAIL (`AttributeError`).

- [ ] **Step 3: Implementar la función**

Agregar al final de `core/storage_sync.py`:

```python
def reconcile_title_group(db: Session, family_key: str, title: str) -> dict:
    """Recalcula si el grupo de documentos con este título dentro de esta
    familia tiene más de una actuación (misma señal que case_document_count)
    y reconcilia a cada uno (y sus versiones archivadas) con esa decisión.
    Se dispara cuando llega una actuación nueva, para corregir también a los
    'hermanos' existentes que nadie tocó directamente."""
    documentos = repository.list_documents_by_title_within_family(db, family_key, title)
    tiene_actuaciones = len(documentos) > 1
    documentos_renombrados = 0
    versiones_renombradas = 0
    for documento in documentos:
        if reconcile_document(db, documento, family_key, tiene_actuaciones):
            documentos_renombrados += 1
        versiones_renombradas += reconcile_document_versions(db, documento, family_key, tiene_actuaciones)
    return {"documentos_renombrados": documentos_renombrados, "versiones_renombradas": versiones_renombradas}
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `python -m pytest tests/test_storage_sync.py -v`
Expected: PASS (7 tests en total).

- [ ] **Step 5: Commit**

```bash
git add core/storage_sync.py tests/test_storage_sync.py
git commit -m "feat(storage-sync): reconcile_title_group"
```

---

### Task 6: `core/storage_sync.py` — `reconcile_all`

**Files:**
- Modify: `core/storage_sync.py`
- Test: `tests/test_storage_sync.py`

**Interfaces:**
- Consumes: `repository.get_source_family_keys` (ya existe), `core.naming.es_familia_con_actuaciones` (ya existe), `reconcile_title_group` (Task 5), `reconcile_document` + `reconcile_document_versions` (Tasks 3-4).
- Produces: `reconcile_all(db: Session) -> dict` con claves `documentos_renombrados` y `versiones_renombradas`, recorriendo TODOS los documentos.

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_storage_sync.py`:

```python
def test_reconcile_all_covers_case_families_and_plain_families_together(db_session, monkeypatch):
    from datetime import date

    rama_source = _rama_judicial_source(db_session)
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    const_source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})

    shared_title = "T_SANT_68001_33_33_007_2025_00290_02"
    caso1 = repository.insert_document(
        db_session, doc_id="d1", source_id=rama_source.id, title=shared_title, f_providencia=date(2026, 8, 6),
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder1.pdf",
    )
    caso2 = repository.insert_document(
        db_session, doc_id="d2", source_id=rama_source.id, title=shared_title, f_providencia=date(2026, 8, 20),
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder2.pdf",
    )
    suelto = repository.insert_document(
        db_session, doc_id="d3", source_id=const_source.id, title="T-065/24",
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder-suelto.pdf",
    )

    monkeypatch.setattr(storage_sync, "rename_object", lambda *a: None)

    result = storage_sync.reconcile_all(db_session)

    assert result == {"documentos_renombrados": 3, "versiones_renombradas": 0}
    db_session.refresh(caso1)
    db_session.refresh(caso2)
    db_session.refresh(suelto)
    assert caso1.storage_key == "carpeta/T_SANT_68001_33_33_007_2025_00290_02_20260806.pdf"
    assert caso2.storage_key == "carpeta/T_SANT_68001_33_33_007_2025_00290_02_20260820.pdf"
    assert suelto.storage_key == "carpeta/T-065-24.pdf"


def test_reconcile_all_is_idempotent(db_session, monkeypatch):
    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T-123-24",
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder.pdf",
    )

    monkeypatch.setattr(storage_sync, "rename_object", lambda *a: None)

    storage_sync.reconcile_all(db_session)
    second = storage_sync.reconcile_all(db_session)

    assert second == {"documentos_renombrados": 0, "versiones_renombradas": 0}
```

Nota: `suelto.storage_key` termina en `T-065-24.pdf` (guion en vez de `/`) porque
`_sanitize_filename_segment` (dentro de `rekey_filename`) reemplaza cualquier
carácter no seguro para nombre de archivo — el título `T-065/24` ya se sanitiza
así en el resto del sistema (ver `rekey_filename`/`_INVALID_FILENAME_CHARS`).

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `python -m pytest tests/test_storage_sync.py -k reconcile_all -v`
Expected: FAIL (`AttributeError`).

- [ ] **Step 3: Implementar la función**

Actualizar los imports de `core/storage_sync.py` para agregar `select` y `es_familia_con_actuaciones`:

```python
from sqlalchemy import select

from core.db.models import Document
from core.naming import es_familia_con_actuaciones, nombre_documento, nombre_version
```

Agregar al final de `core/storage_sync.py`:

```python
def reconcile_all(db: Session) -> dict:
    """Recorre todo el archivo. Usado por el backfill inicial y por la tarea
    nocturna (red de seguridad para lo que un disparo inmediato no haya
    cubierto). Agrupa los documentos de familias con actuaciones por
    (familia, título) para no recalcular el conteo por cada uno."""
    documentos = db.scalars(select(Document)).all()
    family_keys = repository.get_source_family_keys(db, [d.source_id for d in documentos])

    grupos_de_caso: set[tuple[str, str]] = set()
    documentos_sueltos: list[Document] = []
    for documento in documentos:
        family_key = family_keys.get(documento.source_id)
        if es_familia_con_actuaciones(family_key, documento.title):
            grupos_de_caso.add((family_key, documento.title))
        else:
            documentos_sueltos.append(documento)

    documentos_renombrados = 0
    versiones_renombradas = 0
    for family_key, title in grupos_de_caso:
        resultado = reconcile_title_group(db, family_key, title)
        documentos_renombrados += resultado["documentos_renombrados"]
        versiones_renombradas += resultado["versiones_renombradas"]

    for documento in documentos_sueltos:
        family_key = family_keys.get(documento.source_id)
        if reconcile_document(db, documento, family_key, False):
            documentos_renombrados += 1
        versiones_renombradas += reconcile_document_versions(db, documento, family_key, False)

    return {"documentos_renombrados": documentos_renombrados, "versiones_renombradas": versiones_renombradas}
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `python -m pytest tests/test_storage_sync.py -v`
Expected: PASS (9 tests en total).

- [ ] **Step 5: Commit**

```bash
git add core/storage_sync.py tests/test_storage_sync.py
git commit -m "feat(storage-sync): reconcile_all"
```

---

### Task 7: Script de backfill `core/backfill_storage_key_sync.py`

**Files:**
- Create: `core/backfill_storage_key_sync.py`
- Test: `tests/test_backfill_storage_key_sync.py`

**Interfaces:**
- Consumes: `core.storage_sync.reconcile_all` (Task 6).
- Produces: `main()` — corrida manual única.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_backfill_storage_key_sync.py`:

```python
from core.backfill_storage_key_sync import run_backfill
from core.db import repository
import core.backfill_storage_key_sync as backfill_module


def test_run_backfill_renames_a_mismatched_document(db_session, monkeypatch):
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(db_session, family_key="rama_judicial", name="Tribunal", family_params={})
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T-123-24",
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder.pdf",
    )

    monkeypatch.setattr(backfill_module, "rename_object", lambda *a: None)

    result = run_backfill(db_session)

    assert result == {"documentos_renombrados": 1, "versiones_renombradas": 0}
    db_session.refresh(doc)
    assert doc.storage_key == "carpeta/T-123-24.pdf"
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `python -m pytest tests/test_backfill_storage_key_sync.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'core.backfill_storage_key_sync'`).

- [ ] **Step 3: Implementar `core/backfill_storage_key_sync.py`**

```python
"""Corrida única: sincroniza storage_key en `documents` y `document_versions`
con el nombre canónico vigente de cada uno — ver core/storage_sync.py y
docs/superpowers/specs/2026-08-11-sincronizar-nombre-archivo-minio-design.md.
Se puede correr más de una vez sin problema: lo que ya coincide no se toca.

Uso: .venv/Scripts/python -m core.backfill_storage_key_sync
"""
import logging

from sqlalchemy.orm import Session

from core.db.session import SessionLocal
from core.storage import rename_object  # noqa: F401 — reexportado para que los tests lo puedan parchear aquí
from core.storage_sync import reconcile_all

logger = logging.getLogger(__name__)


def run_backfill(db: Session) -> dict:
    return reconcile_all(db)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        resultado = run_backfill(db)
        mensaje = (
            f"Documentos renombrados: {resultado['documentos_renombrados']}, "
            f"versiones renombradas: {resultado['versiones_renombradas']}"
        )
        logger.info(mensaje)
        print(mensaje)
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

> Nota: el `rename_object` importado aquí es el mismo objeto que usa
> `core.storage_sync` internamente (Python cachea módulos), así que
> parchear `backfill_module.rename_object` en el test de arriba también
> afecta lo que `reconcile_all` termina llamando — mismo patrón que
> `core/backfill_csj_storage_keys.py`.

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `python -m pytest tests/test_backfill_storage_key_sync.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/backfill_storage_key_sync.py tests/test_backfill_storage_key_sync.py
git commit -m "feat(backfill): sincronizar storage_key con el nombre canónico"
```

---

### Task 8: Tareas Celery (`worker/storage_sync_tasks.py`) + tarea nocturna

**Files:**
- Create: `worker/storage_sync_tasks.py`
- Modify: `worker/celery_app.py:9` (agregar el módulo nuevo a `include`)
- Modify: `worker/beat_schedule.py` (agregar el horario nocturno)
- Test: `tests/test_storage_sync_tasks.py`

**Interfaces:**
- Consumes: `core.storage_sync.reconcile_document`, `reconcile_document_versions`, `reconcile_title_group`, `reconcile_all` (Tasks 3-6); `repository.get_document`, `repository.get_source_family_keys`, `repository.actuacion_counts_by_title` (ya existen).
- Produces: tareas Celery `worker.reconcile_title_group_task(family_key, title)`, `worker.reconcile_document_task(document_id)`, `worker.reconcile_all_task()`.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_storage_sync_tasks.py`:

```python
from datetime import date

from sqlalchemy.orm import sessionmaker

from core.db import repository
import core.storage_sync as storage_sync
from worker.celery_app import celery_app
from worker.storage_sync_tasks import reconcile_all_task, reconcile_document_task, reconcile_title_group_task


def _rama_judicial_source(db_session):
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    return repository.create_source(db_session, family_key="rama_judicial", name="Tribunal", family_params={})


def test_reconcile_title_group_task_renames_every_sibling(db_session, test_engine, monkeypatch):
    celery_app.conf.task_always_eager = True
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.storage_sync_tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr(storage_sync, "rename_object", lambda *a: None)

    source = _rama_judicial_source(db_session)
    shared_title = "T_SANT_68001_33_33_007_2025_00290_02"
    doc1 = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title=shared_title, f_providencia=date(2026, 8, 6),
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder1.pdf",
    )
    doc2 = repository.insert_document(
        db_session, doc_id="d2", source_id=source.id, title=shared_title, f_providencia=date(2026, 8, 20),
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder2.pdf",
    )

    reconcile_title_group_task("rama_judicial", shared_title)

    assertion_session = task_session_factory()
    try:
        d1 = repository.get_document(assertion_session, doc1.id)
        d2 = repository.get_document(assertion_session, doc2.id)
        assert d1.storage_key == "carpeta/T_SANT_68001_33_33_007_2025_00290_02_20260806.pdf"
        assert d2.storage_key == "carpeta/T_SANT_68001_33_33_007_2025_00290_02_20260820.pdf"
    finally:
        assertion_session.close()


def test_reconcile_document_task_renames_the_document_and_its_versions(db_session, test_engine, monkeypatch):
    celery_app.conf.task_always_eager = True
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.storage_sync_tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr(storage_sync, "rename_object", lambda *a: None)

    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T-123-24",
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder.pdf",
    )
    repository.archive_and_replace_document(db_session, doc.id, storage_bucket="iurisync-test", storage_key="carpeta/placeholder-v1.pdf")

    reconcile_document_task(doc.id)

    assertion_session = task_session_factory()
    try:
        refreshed = repository.get_document(assertion_session, doc.id)
        assert refreshed.storage_key == "carpeta/T-123-24_v2.pdf"
        [version] = repository.list_document_versions(assertion_session, doc.id)
        assert version.storage_key == "carpeta/T-123-24_v1.pdf"
    finally:
        assertion_session.close()


def test_reconcile_document_task_does_not_raise_for_a_nonexistent_document(db_session, test_engine, monkeypatch):
    celery_app.conf.task_always_eager = True
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.storage_sync_tasks.SessionLocal", task_session_factory)

    reconcile_document_task(999999)  # no debe lanzar


def test_reconcile_all_task_sweeps_everything(db_session, test_engine, monkeypatch):
    celery_app.conf.task_always_eager = True
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.storage_sync_tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr(storage_sync, "rename_object", lambda *a: None)

    source = _rama_judicial_source(db_session)
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T-123-24",
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder.pdf",
    )

    reconcile_all_task()

    assertion_session = task_session_factory()
    try:
        assert repository.get_document(assertion_session, doc.id).storage_key == "carpeta/T-123-24.pdf"
    finally:
        assertion_session.close()
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `python -m pytest tests/test_storage_sync_tasks.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'worker.storage_sync_tasks'`).

- [ ] **Step 3: Implementar `worker/storage_sync_tasks.py`**

```python
import logging

from core.db import repository
from core.db.session import SessionLocal
from core.storage_sync import reconcile_all, reconcile_document, reconcile_document_versions, reconcile_title_group
from worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="worker.reconcile_title_group_task")
def reconcile_title_group_task(family_key: str, title: str) -> None:
    db = SessionLocal()
    try:
        reconcile_title_group(db, family_key, title)
    finally:
        db.close()


@celery_app.task(name="worker.reconcile_document_task")
def reconcile_document_task(document_id: int) -> None:
    db = SessionLocal()
    try:
        document = repository.get_document(db, document_id)
        if document is None:
            return
        family_key = repository.get_source_family_keys(db, [document.source_id]).get(document.source_id)
        tiene_actuaciones = (
            repository.actuacion_counts_by_title(db, [document], {document.source_id: family_key}).get(document.title, 0) > 1
        )
        reconcile_document(db, document, family_key, tiene_actuaciones)
        reconcile_document_versions(db, document, family_key, tiene_actuaciones)
    finally:
        db.close()


@celery_app.task(name="worker.reconcile_all_task")
def reconcile_all_task() -> None:
    db = SessionLocal()
    try:
        resultado = reconcile_all(db)
        logger.info(
            "Barrido nocturno de sincronización — documentos renombrados: %s, versiones renombradas: %s",
            resultado["documentos_renombrados"], resultado["versiones_renombradas"],
        )
    finally:
        db.close()
```

En `worker/celery_app.py`, cambiar la línea `include=["worker.tasks", "worker.beat_schedule"],` por:

```python
    include=["worker.tasks", "worker.beat_schedule", "worker.storage_sync_tasks"],
```

En `worker/beat_schedule.py`, agregar el import y el horario nocturno:

```python
from worker.storage_sync_tasks import reconcile_all_task  # noqa: F401 — registra la tarea en beat_schedule
```

(agregar junto a los demás imports, después de `from worker.tasks import orchestrate_run`)

Y cambiar el diccionario final:

```python
celery_app.conf.beat_schedule = {
    "daily-scrape": {
        "task": "worker.trigger_scheduled_run",
        "schedule": crontab(hour=6, minute=0),
    },
    "nightly-storage-sync": {
        "task": "worker.reconcile_all_task",
        "schedule": crontab(hour=2, minute=0),
    },
}
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `python -m pytest tests/test_storage_sync_tasks.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add worker/storage_sync_tasks.py worker/celery_app.py worker/beat_schedule.py tests/test_storage_sync_tasks.py
git commit -m "feat(worker): tareas de reconciliación de storage_key + barrido nocturno"
```

---

### Task 9: Disparo en `scrape_source_task` — actuación nueva

**Files:**
- Modify: `worker/tasks.py:1-18` (imports), `worker/tasks.py:203-205` (variables del loop), `worker/tasks.py:372-373` (rama "new"), `worker/tasks.py:401-403` (después del try/except principal)
- Test: `tests/test_tasks.py`

**Interfaces:**
- Consumes: `core.naming.es_familia_con_actuaciones` (ya existe), `worker.storage_sync_tasks.reconcile_title_group_task` (Task 8).

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_tasks.py` (después de los tests de `scrape_source_task` existentes, junto a los que usan `DummyFamilyScraper`):

```python
@responses.activate
def test_scrape_source_task_dispatches_storage_sync_when_a_second_actuacion_arrives(db_session, test_engine, monkeypatch):
    """Regresión: T_SANT_68001_33_33_007_2025_00290_02 no tenía otra actuación
    y su archivo en MinIO se guardó sin ningún sufijo (ver spec). Cuando llega
    una segunda actuación con el mismo título, el documento existente (el que
    nadie tocó directamente) también debe quedar renombrado con fecha
    completa en MinIO, no solo el nuevo."""
    from pathlib import Path
    import tempfile

    from core.scrapers.registry import FAMILY_REGISTRY
    from core.storage import upload_file

    monkeypatch.setitem(FAMILY_REGISTRY, "rama_judicial", DummyFamilyScraper)

    celery_app.conf.task_always_eager = True
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("worker.storage_sync_tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Tribunal Superior de Bogotá", family_params={}
    )

    shared_title = "T_SANT_68001_33_33_007_2025_00290_02"
    existing_key = f"Rama Judicial/2026-08-06/Auto/{shared_title}.pdf"
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / "existente.pdf"
        local.write_bytes(b"contenido existente")
        upload_file(local, existing_key, bucket=TEST_S3_BUCKET, content_type="application/pdf")

    existing_doc = repository.insert_document(
        db_session, doc_id="rj-existente", source_id=source.id, title=shared_title,
        storage_bucket=TEST_S3_BUCKET, storage_key=existing_key,
        f_providencia=date(2026, 8, 6),
    )

    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    DummyFamilyScraper.docs_to_return = [
        RawDocModel(
            source="Tribunal Superior de Bogotá",
            link={"url": "https://example.com/doc-nuevo", "method": "GET"},
            title=shared_title,
            tipo="Auto",
            f_public="2026-08-20",
            f_providencia="2026-08-20",
        )
    ]
    responses.add(
        responses.GET, "https://example.com/doc-nuevo",
        body=b"contenido nuevo", headers={"Content-Type": "application/pdf"}, status=200,
    )

    scrape_source_task(run_source.id)

    assertion_session = task_session_factory()
    try:
        documentos = {
            d.id: d for d in repository.list_documents_by_title_within_family(assertion_session, "rama_judicial", shared_title)
        }
        assert len(documentos) == 2
        assert documentos[existing_doc.id].storage_key == f"Rama Judicial/2026-08-06/Auto/{shared_title}_20260806.pdf"
        nuevo = next(d for d in documentos.values() if d.id != existing_doc.id)
        assert nuevo.storage_key == f"Rama Judicial/2026-08-06/Auto/{shared_title}_20260820.pdf"
    finally:
        assertion_session.close()
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `python -m pytest tests/test_tasks.py -k dispatches_storage_sync_when_a_second_actuacion -v`
Expected: FAIL — `documentos[existing_doc.id].storage_key` sigue siendo la clave sin sufijo (todavía no hay disparo).

- [ ] **Step 3: Implementar el disparo**

En `worker/tasks.py`, agregar a los imports (junto a `from core.naming import nombre_archivo_documento`):

```python
from core.naming import es_familia_con_actuaciones, nombre_archivo_documento
```

y (junto a los demás imports, después de `from core.utils import ...`):

```python
from worker.storage_sync_tasks import reconcile_document_task, reconcile_title_group_task
```

Justo después de `docs_errors = 0` (dentro de `scrape_source_task`, antes del `for message in progress.error_messages:`):

```python
        docs_new = 0
        docs_updated = 0
        docs_errors = 0
        # Títulos con forma de caso que recibieron una actuación nueva en esta
        # corrida — al terminar se dispara una reconciliación de storage_key
        # para todo el grupo (core/storage_sync.py), no solo para el
        # documento nuevo: sus "hermanos" existentes también pueden necesitar
        # pasar de solo-año a fecha completa.
        titulos_con_actuacion_nueva: set[tuple[str, str]] = set()
        # Documentos republicados en esta corrida — cada uno dispara su
        # propia reconciliación (les cambió el sufijo de versión).
        documentos_republicados: set[int] = set()
```

Dentro del bloque `if kind == "new":`, cambiar:

```python
                                        if created:
                                            docs_new += 1
```

por:

```python
                                        if created:
                                            docs_new += 1
                                            if es_familia_con_actuaciones(source.family_key, doc.title):
                                                titulos_con_actuacion_nueva.add((source.family_key, doc.title))
```

Justo después del `try/except` principal de `scrape_source_task` (después de la línea con `return` dentro de `except Exception as exc:`, antes de `repository.set_run_source_status(db, run_source_id, "cancelled" if was_cancelled else "completed", ...)`):

```python
        for family_key, title in titulos_con_actuacion_nueva:
            reconcile_title_group_task.delay(family_key, title)

        repository.set_run_source_status(
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `python -m pytest tests/test_tasks.py -k dispatches_storage_sync_when_a_second_actuacion -v`
Expected: PASS.

- [ ] **Step 5: Correr toda la suite de `scrape_source_task` para verificar que no hay regresiones**

Run: `python -m pytest tests/test_tasks.py -k scrape_source_task -v`
Expected: todo PASS.

- [ ] **Step 6: Commit**

```bash
git add worker/tasks.py tests/test_tasks.py
git commit -m "feat(worker): disparar reconciliación de storage_key al llegar una actuación nueva"
```

---

### Task 10: Disparo en `scrape_source_task` — republicación

**Files:**
- Modify: `worker/tasks.py:374-379` (rama "replace"/existing)
- Test: `tests/test_tasks.py`

**Interfaces:**
- Consumes: `documentos_republicados` (Task 9), `worker.storage_sync_tasks.reconcile_document_task` (Task 8).

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_tasks.py`:

```python
@responses.activate
def test_scrape_source_task_dispatches_storage_sync_after_republication(db_session, test_engine, monkeypatch):
    """Republicar un documento le agrega/actualiza el sufijo de versión
    (_v2) en el nombre — el archivo vigente y la versión recién archivada
    deben quedar renombrados en MinIO sin que nadie los toque a mano."""
    from core.utils import compute_doc_id

    celery_app.conf.task_always_eager = True
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("worker.storage_sync_tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    raw_doc = RawDocModel(
        source="Dummy Source",
        link={"url": "https://example.com/doc1", "method": "GET"},
        title="Documento 1",
        tipo="Auto",
        f_public="2026-01-01",
    )
    doc_id = compute_doc_id(raw_doc, include_publication_date=True)

    from pathlib import Path
    import tempfile

    from core.storage import upload_file

    existing_key = "Dummy Source/2026-01-01/Auto/Documento 1.pdf"
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / "existente.pdf"
        local.write_bytes(b"contenido viejo")
        upload_file(local, existing_key, bucket=TEST_S3_BUCKET, content_type="application/pdf")

    existing_doc = repository.insert_document(
        db_session, doc_id=doc_id, source_id=source.id, title="Documento 1",
        storage_bucket=TEST_S3_BUCKET, storage_key=existing_key,
        content_type="application/pdf", file_size_bytes=9, source_url="https://example.com/doc1",
    )

    DummyFamilyScraper.docs_to_return = [raw_doc]
    responses.add(responses.HEAD, "https://example.com/doc1", headers={"Content-Length": "20"}, status=200)
    responses.add(
        responses.GET, "https://example.com/doc1",
        body=b"contenido republicado", headers={"Content-Type": "application/pdf"}, status=200,
    )

    scrape_source_task(run_source.id)

    assertion_session = task_session_factory()
    try:
        refreshed = repository.get_document(assertion_session, existing_doc.id)
        assert refreshed.version_no == 2
        assert refreshed.storage_key == "Dummy Source/2026-01-01/Auto/Documento 1_v2.pdf"
        [version] = repository.list_document_versions(assertion_session, existing_doc.id)
        assert version.storage_key == "Dummy Source/2026-01-01/Auto/Documento 1_v1.pdf"
    finally:
        assertion_session.close()
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `python -m pytest tests/test_tasks.py -k dispatches_storage_sync_after_republication -v`
Expected: FAIL — `refreshed.storage_key` sigue siendo la clave republicada sin el sufijo `_v2` (todavía no hay disparo).

- [ ] **Step 3: Implementar el disparo**

En `worker/tasks.py`, dentro del bloque `else:` (rama de republicación), cambiar:

```python
                                    else:
                                        _, existing, doc_id, doc = entry
                                        repository.archive_and_replace_document(
                                            db, existing.id, review_status=auto_review_status or "pending", **payload
                                        )
                                        docs_updated += 1
```

por:

```python
                                    else:
                                        _, existing, doc_id, doc = entry
                                        repository.archive_and_replace_document(
                                            db, existing.id, review_status=auto_review_status or "pending", **payload
                                        )
                                        docs_updated += 1
                                        documentos_republicados.add(existing.id)
```

Y en el mismo punto de disparo agregado en el Task 9 (justo antes de `repository.set_run_source_status(...)`), agregar la segunda línea:

```python
        for family_key, title in titulos_con_actuacion_nueva:
            reconcile_title_group_task.delay(family_key, title)
        for document_id in documentos_republicados:
            reconcile_document_task.delay(document_id)

        repository.set_run_source_status(
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `python -m pytest tests/test_tasks.py -k dispatches_storage_sync_after_republication -v`
Expected: PASS.

- [ ] **Step 5: Correr toda la suite de `scrape_source_task` para verificar que no hay regresiones**

Run: `python -m pytest tests/test_tasks.py -k scrape_source_task -v`
Expected: todo PASS.

- [ ] **Step 6: Commit**

```bash
git add worker/tasks.py tests/test_tasks.py
git commit -m "feat(worker): disparar reconciliación de storage_key al republicar un documento"
```

---

### Task 11: Disparo en `patch_document_title`

**Files:**
- Modify: `api/routers/documents.py:1-30` (imports), `api/routers/documents.py:261-266` (`patch_document_title`)
- Test: `tests/test_api_documents.py`

**Interfaces:**
- Consumes: `worker.storage_sync_tasks.reconcile_document_task` (Task 8).

- [ ] **Step 1: Escribir el test que falla**

Agregar a `tests/test_api_documents.py`:

```python
def test_patch_document_title_dispatches_storage_sync(api_client, auth_header, db_session, monkeypatch):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session, doc_id="doc-title-sync", source_id=source.id, title="T-065/24",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )

    called = []
    monkeypatch.setattr(
        "api.routers.documents.reconcile_document_task.delay", lambda document_id: called.append(document_id)
    )

    response = api_client.patch(
        f"/documents/{document.id}/title", json={"title": "T-065/24 corregido"}, headers=auth_header
    )

    assert response.status_code == 200
    assert called == [document.id]
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `python -m pytest tests/test_api_documents.py -k patch_document_title_dispatches_storage_sync -v`
Expected: FAIL (`AttributeError` al parchear `api.routers.documents.reconcile_document_task` — todavía no está importado ahí).

- [ ] **Step 3: Implementar el disparo**

En `api/routers/documents.py`, agregar el import junto a `from worker.tasks import generate_document_preview_pdf`:

```python
from worker.storage_sync_tasks import reconcile_document_task
from worker.tasks import generate_document_preview_pdf
```

Cambiar `patch_document_title`:

```python
@router.patch("/documents/{document_id}/title", response_model=DocumentOut)
def patch_document_title(document_id: int, payload: DocumentTitleUpdate, db: Session = Depends(get_db)):
    document = repository.update_document_title(db, document_id, payload.title)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    reconcile_document_task.delay(document.id)
    return _poblar_nombre(db, document)
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `python -m pytest tests/test_api_documents.py -k patch_document_title -v`
Expected: PASS (incluye los tests de `patch_document_title` ya existentes, que no deben romperse).

- [ ] **Step 5: Commit**

```bash
git add api/routers/documents.py tests/test_api_documents.py
git commit -m "feat(api): disparar reconciliación de storage_key al editar el título"
```

---

### Task 12: Verificación integral y puesta en marcha

**Files:**
- No hay cambios de código; verificación de extremo a extremo.

- [ ] **Step 1: Correr las suites backend afectadas (dirigidas)**

Run:
```bash
python -m pytest tests/test_repository.py tests/test_storage_sync.py tests/test_storage_sync_tasks.py tests/test_backfill_storage_key_sync.py tests/test_api_documents.py -v
```
Expected: todo PASS.

Run por separado (más pesada, incluye descargas reales a MinIO de prueba):
```bash
python -m pytest tests/test_tasks.py -k "scrape_source_task or storage_sync" -v
```
Expected: todo PASS.

- [ ] **Step 2: Prueba end-to-end con la app (skill run-iurisync)**

Con el entorno levantado: lanzar una descarga real de una fuente con actuaciones
(ej. Consejo de Estado), confirmar en la UI que el nombre mostrado no cambió
respecto al arreglo anterior, y verificar directamente en la consola de MinIO
que el objeto guardado para ese documento ya tiene el sufijo correcto (año o
fecha completa, según corresponda). Editar el título de un documento a mano y
confirmar (revisando logs de Celery) que se disparó `reconcile_document_task`.

- [ ] **Step 3: Notas de despliegue**

Registrar en el PR:
- No hay migración Alembic — sin columnas nuevas.
- Tras `docker compose pull/up`, correr una vez el backfill:
  ```
  docker compose run --rm api python -m core.backfill_storage_key_sync
  ```
- La tarea nocturna (`worker.reconcile_all_task`, 2:00 AM) queda activa sola en
  cuanto el contenedor `beat` se reinicia con la imagen nueva — sin pasos
  manuales adicionales.

- [ ] **Step 4: Commit (si hubo ajustes de verificación)**

```bash
git add -A
git commit -m "test: verificación integral de la sincronización de storage_key"
```

---

## Self-Review

**Cobertura del spec:**
- Motor central (`reconcile_document`, `reconcile_document_versions`, `reconcile_title_group`, `reconcile_all`) → Tasks 3-6. ✓
- Repositorio (`list_documents_by_title_within_family`, `update_document_version_storage_key`) → Tasks 1-2. ✓
- Backfill inicial → Task 7. ✓
- Tareas Celery + tarea nocturna → Task 8. ✓
- Disparo por actuación nueva (cascada a hermanos) → Task 9. ✓
- Disparo por republicación → Task 10. ✓
- Disparo por edición de título → Task 11. ✓
- Manejo de errores (no bloquear al llamador, no actualizar la base si el renombrado falla) → cubierto en Tasks 3-4 y probado en Task 3. ✓
- Puesta en marcha / verificación → Task 12. ✓

**Consistencia de tipos:** `reconcile_document(db, document, family_key, tiene_actuaciones) -> bool`,
`reconcile_document_versions(db, document, family_key, tiene_actuaciones) -> int`,
`reconcile_title_group(db, family_key, title) -> dict` y `reconcile_all(db) -> dict`
(mismas claves `documentos_renombrados`/`versiones_renombradas` en ambos) se usan de forma
coherente en Tasks 7-11.

**Sin placeholders:** cada paso trae código real y comandos reales.
