# Propagar "Útil" a todas las actuaciones de un caso — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Marcar (o desmarcar) un documento como útil aplica el mismo estado a todas las actuaciones del mismo caso, y la descarga masiva incluye las versiones archivadas de cada documento útil.

**Architecture:** La agrupación por caso ya existe (`es_familia_con_actuaciones` + mismo título dentro de la familia). Se expande el conjunto de ids en los dos puntos de escritura del estado de revisión (`update_document_review_status`, `bulk_update_document_review_status`) mediante un helper nuevo `_expandir_a_grupos`. Una actuación que llega después hereda el estado del grupo vía una función nueva llamada desde `scrape_source_task`. `build_bulk_download_zip` agrega las `DocumentVersion` archivadas al ZIP. El visor del frontend refleja el grupo completo al actualizar su snapshot.

**Tech Stack:** Python 3.14, SQLAlchemy 2.x (Core `update()`), FastAPI, Celery, pytest; React + TanStack Query + Vitest/RTL/MSW en el frontend.

**Spec:** `docs/superpowers/specs/2026-09-03-propagar-util-actuaciones-design.md`

## Global Constraints

- Familias "con actuaciones" (grupo por título): solo `rama_judicial` y `samai`. La señal canónica es `core.naming.es_familia_con_actuaciones(family_key, title)`. No inventar otra.
- Propagación **simétrica**: aplica igual a `"useful"`, `"not_useful"` y `"pending"`.
- Todo cambio de estado pone `reviewed_at = datetime.now(timezone.utc)` y `bulk_download_id = None` en cada fila afectada (mismo comportamiento que hoy en `update_document_review_status`).
- No se cruza entre fuentes distintas (nada de `CaseLink` / `radicado` en este plan).
- Un documento suelto (fuente sin actuaciones) se comporta exactamente como hoy.
- Los tests que tocan base de datos usan la fixture `db_session` (ver `tests/conftest.py`); se ejecutan de forma dirigida por archivo/función, nunca la suite pesada completa en paralelo.
- Mensajes de usuario y docstrings en español, como el resto del módulo.
- Comando de test backend: `.venv/Scripts/python -m pytest <ruta>::<test> -v`. Frontend: `cd frontend && npm test -- --run <ruta>`.
- No commitear salvo que el paso lo diga explícitamente; cada tarea termina con su propio commit.

---

### Task 1: `_expandir_a_grupos` + propagación en `update_document_review_status`

**Files:**
- Modify: `core/db/repository.py` (añadir `_expandir_a_grupos` justo antes de `update_document_review_status` en la línea ~1036; reescribir el cuerpo de `update_document_review_status`)
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: `es_familia_con_actuaciones` (ya importado en `repository.py` línea 10), `get_source_family_keys(db, source_ids: list[int]) -> dict[int, str]` (línea ~656), `list_documents_by_title_within_family(db, family_key: str, title: str) -> list[Document]` (línea ~703), `sqlalchemy.update`/`select` (ya importados línea 5).
- Produces:
  - `_expandir_a_grupos(db: Session, document_ids: list[int]) -> list[int]` — devuelve los ids dados más los de las actuaciones hermanas (mismo `family_key` + mismo `title`) de los que pertenezcan a una familia con actuaciones; ids inexistentes se conservan tal cual; sin repetidos; ordenada.
  - `update_document_review_status(db, document_id: int, review_status: str) -> Optional[Document]` — firma sin cambios; ahora escribe también las hermanas; devuelve el `Document` pedido (o `None` si no existe).

- [ ] **Step 1: Write the failing test**

En `tests/test_repository.py`, al final del bloque de tests de review status (después de `test_update_document_review_status_returns_none_when_missing`, ~línea 270):

```python
def test_update_document_review_status_propagates_to_sibling_actuaciones(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(
        db_session, family_key="samai", name="Consejo de Estado", family_params={}
    )
    titulo = "11001-03-28-000-2026-00300-00"
    a1 = repository.insert_document(
        db_session, doc_id="a1", source_id=source.id, title=titulo,
        storage_bucket="iurisync-test", storage_key="a1.pdf",
    )
    a2 = repository.insert_document(
        db_session, doc_id="a2", source_id=source.id, title=titulo,
        storage_bucket="iurisync-test", storage_key="a2.pdf",
    )
    otro = repository.insert_document(
        db_session, doc_id="otro", source_id=source.id, title="99999-99-99-000-2026-11111-00",
        storage_bucket="iurisync-test", storage_key="otro.pdf",
    )

    devuelto = repository.update_document_review_status(db_session, a1.id, "useful")

    assert devuelto.id == a1.id
    for d in (a1, a2, otro):
        db_session.refresh(d)
    assert a1.review_status == "useful"
    assert a2.review_status == "useful"          # hermana arrastrada
    assert a2.reviewed_at is not None
    assert a2.bulk_download_id is None
    assert otro.review_status == "pending"       # otro caso, intacto


def test_update_document_review_status_is_symmetric_for_all_states(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(
        db_session, family_key="rama_judicial", name="Rama Judicial", family_params={}
    )
    titulo = "T_BTA_11001_31_03_022_2019_00814_02"
    a1 = repository.insert_document(
        db_session, doc_id="a1", source_id=source.id, title=titulo,
        storage_bucket="iurisync-test", storage_key="a1.pdf", review_status="useful",
    )
    a2 = repository.insert_document(
        db_session, doc_id="a2", source_id=source.id, title=titulo,
        storage_bucket="iurisync-test", storage_key="a2.pdf", review_status="useful",
    )

    repository.update_document_review_status(db_session, a2.id, "pending")

    db_session.refresh(a1)
    assert a1.review_status == "pending"   # desmarcar también propaga


def test_update_document_review_status_standalone_document_only_affects_itself(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(
        db_session, family_key="constitucional", name="Corte Constitucional", family_params={}
    )
    d1 = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="C-034-26",
        storage_bucket="iurisync-test", storage_key="d1.pdf",
    )
    d2 = repository.insert_document(
        db_session, doc_id="d2", source_id=source.id, title="C-034-26",
        storage_bucket="iurisync-test", storage_key="d2.pdf",
    )

    repository.update_document_review_status(db_session, d1.id, "useful")

    db_session.refresh(d2)
    # 'constitucional' no es familia con actuaciones: mismo título no es el mismo caso.
    assert d2.review_status == "pending"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_repository.py::test_update_document_review_status_propagates_to_sibling_actuaciones tests/test_repository.py::test_update_document_review_status_is_symmetric_for_all_states tests/test_repository.py::test_update_document_review_status_standalone_document_only_affects_itself -v`
Expected: los tres FAIL — `propagates_to_sibling_actuaciones` y `is_symmetric` fallan en el assert de la hermana (`pending` != `useful`/`pending`); `standalone` PASA ya (comportamiento actual solo toca `d1`) — si pasa desde el inicio, déjalo, sirve de regresión.

- [ ] **Step 3: Implement `_expandir_a_grupos` and rewrite `update_document_review_status`**

En `core/db/repository.py`, insertar justo antes de `def update_document_review_status` (~línea 1036):

```python
def _expandir_a_grupos(db: Session, document_ids: list[int]) -> list[int]:
    """Devuelve `document_ids` más los ids de todas las actuaciones hermanas
    (mismo family_key + mismo título) de los documentos que pertenezcan a una
    familia con actuaciones (ver es_familia_con_actuaciones). Un documento
    suelto se devuelve tal cual; los ids inexistentes se conservan (el UPDATE
    que los recibe simplemente no los encuentra). Sin repetidos, ordenada."""
    if not document_ids:
        return []
    documentos = list(db.scalars(select(Document).where(Document.id.in_(document_ids))).all())
    family_keys = get_source_family_keys(db, [d.source_id for d in documentos])
    ids: set[int] = set(document_ids)
    grupos_vistos: set[tuple[str, str]] = set()
    for d in documentos:
        fam = family_keys.get(d.source_id)
        if not es_familia_con_actuaciones(fam, d.title):
            continue
        if (fam, d.title) in grupos_vistos:
            continue
        grupos_vistos.add((fam, d.title))
        for hermano in list_documents_by_title_within_family(db, fam, d.title):
            ids.add(hermano.id)
    return sorted(ids)
```

Reemplazar el cuerpo de `update_document_review_status` (~líneas 1036-1047) por:

```python
def update_document_review_status(db: Session, document_id: int, review_status: str) -> Optional[Document]:
    document = db.get(Document, document_id)
    if document is None:
        return None
    # Una decisión de revisión se aplica a TODO el caso: marcar (o desmarcar)
    # una actuación arrastra a sus hermanas, para que la descarga masiva traiga
    # el caso completo. Un documento suelto solo se afecta a sí mismo.
    ids = _expandir_a_grupos(db, [document_id])
    db.execute(
        update(Document)
        .where(Document.id.in_(ids))
        .values(
            review_status=review_status,
            reviewed_at=datetime.now(timezone.utc),
            # Una decisión fresca vuelve a habilitar el documento para descarga
            # masiva, aunque una versión anterior ya se haya entregado.
            bulk_download_id=None,
        )
    )
    db.commit()
    db.refresh(document)
    return document
```

- [ ] **Step 4: Run the review-status tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_repository.py -k review_status -v`
Expected: PASS (incluye los nuevos y los preexistentes `test_update_document_review_status_sets_status_and_timestamp`, `..._resets_bulk_download_id`, `..._returns_none_when_missing`).

- [ ] **Step 5: Commit**

```bash
git add core/db/repository.py tests/test_repository.py
git commit -m "feat(review): marcar util propaga a las actuaciones hermanas del caso"
```

---

### Task 2: propagación en `bulk_update_document_review_status`

**Files:**
- Modify: `core/db/repository.py` (cuerpo de `bulk_update_document_review_status`, ~línea 1152)
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: `_expandir_a_grupos` (Task 1).
- Produces: `bulk_update_document_review_status(db, document_ids: list[int], review_status: str) -> int` — firma sin cambios; ahora expande cada id a su grupo antes del `UPDATE`; el `int` devuelto es el `rowcount` real (incluye hermanas; excluye ids inexistentes).

- [ ] **Step 1: Write the failing test**

En `tests/test_repository.py`, después de `test_bulk_update_document_review_status_ignores_nonexistent_ids` (~línea 528):

```python
def test_bulk_update_document_review_status_expands_each_id_to_its_case_group(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(
        db_session, family_key="samai", name="Consejo de Estado", family_params={}
    )
    caso_a = "11001-03-28-000-2026-00300-00"
    caso_b = "11001-03-28-000-2026-00500-00"
    a1 = repository.insert_document(
        db_session, doc_id="a1", source_id=source.id, title=caso_a,
        storage_bucket="iurisync-test", storage_key="a1.pdf",
    )
    a2 = repository.insert_document(
        db_session, doc_id="a2", source_id=source.id, title=caso_a,
        storage_bucket="iurisync-test", storage_key="a2.pdf",
    )
    b1 = repository.insert_document(
        db_session, doc_id="b1", source_id=source.id, title=caso_b,
        storage_bucket="iurisync-test", storage_key="b1.pdf",
    )
    fuera = repository.insert_document(
        db_session, doc_id="fuera", source_id=source.id, title="77777-77-77-000-2026-99999-00",
        storage_bucket="iurisync-test", storage_key="fuera.pdf",
    )

    # La selección trae una actuación de A y la única de B; se esperan 3 filas
    # tocadas (a1, a2 por expansión, b1), y 'fuera' intacto.
    updated_count = repository.bulk_update_document_review_status(db_session, [a1.id, b1.id], "useful")

    assert updated_count == 3
    for d in (a1, a2, b1, fuera):
        db_session.refresh(d)
    assert a1.review_status == "useful"
    assert a2.review_status == "useful"
    assert b1.review_status == "useful"
    assert fuera.review_status == "pending"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_repository.py::test_bulk_update_document_review_status_expands_each_id_to_its_case_group -v`
Expected: FAIL — `updated_count == 2` (no expande) y `a2.review_status == "pending"`.

- [ ] **Step 3: Implement**

En `core/db/repository.py`, reemplazar el cuerpo de `bulk_update_document_review_status` (~líneas 1152-1160) por:

```python
def bulk_update_document_review_status(db: Session, document_ids: list[int], review_status: str) -> int:
    # Cada id de la selección arrastra a su caso completo (ver _expandir_a_grupos
    # y update_document_review_status): la descarga masiva necesita el caso entero.
    ids = _expandir_a_grupos(db, document_ids)
    stmt = (
        update(Document)
        .where(Document.id.in_(ids))
        .values(review_status=review_status, reviewed_at=datetime.now(timezone.utc), bulk_download_id=None)
    )
    result = db.execute(stmt)
    db.commit()
    return result.rowcount
```

- [ ] **Step 4: Run the bulk-update tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_repository.py -k bulk_update_document_review_status -v`
Expected: PASS (nuevo + `..._updates_matching_rows` + `..._ignores_nonexistent_ids`).

- [ ] **Step 5: Commit**

```bash
git add core/db/repository.py tests/test_repository.py
git commit -m "feat(review): la marca masiva tambien expande cada id a su caso"
```

---

### Task 3: `heredar_review_status_de_actuaciones_existentes`

**Files:**
- Modify: `core/db/repository.py` (nueva función pública, ponerla justo después de `bulk_update_document_review_status`)
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: `list_documents_by_title_within_family` (línea ~703), `sqlalchemy.update`.
- Produces: `heredar_review_status_de_actuaciones_existentes(db: Session, family_key: str, title: str) -> int` — si los miembros no-`"pending"` del grupo `(family_key, title)` coinciden en un único estado, aplica ese estado a los miembros en `"pending"` (con `reviewed_at = now`, `bulk_download_id = None`) y devuelve cuántos actualizó; si el grupo está todo en `"pending"` o los no-`"pending"` están en desacuerdo, devuelve `0` sin tocar nada.

- [ ] **Step 1: Write the failing test**

En `tests/test_repository.py`, después del test de Task 2:

```python
def test_heredar_review_status_aplica_el_estado_del_grupo_a_la_actuacion_pendiente(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(
        db_session, family_key="samai", name="Consejo de Estado", family_params={}
    )
    titulo = "11001-03-28-000-2026-00300-00"
    repository.insert_document(
        db_session, doc_id="a1", source_id=source.id, title=titulo,
        storage_bucket="iurisync-test", storage_key="a1.pdf", review_status="useful",
    )
    nueva = repository.insert_document(
        db_session, doc_id="a2", source_id=source.id, title=titulo,
        storage_bucket="iurisync-test", storage_key="a2.pdf",  # entra 'pending'
    )

    n = repository.heredar_review_status_de_actuaciones_existentes(db_session, "samai", titulo)

    assert n == 1
    db_session.refresh(nueva)
    assert nueva.review_status == "useful"
    assert nueva.reviewed_at is not None


def test_heredar_review_status_no_hace_nada_si_el_grupo_esta_todo_pendiente(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(
        db_session, family_key="samai", name="Consejo de Estado", family_params={}
    )
    titulo = "11001-03-28-000-2026-00300-00"
    repository.insert_document(
        db_session, doc_id="a1", source_id=source.id, title=titulo,
        storage_bucket="iurisync-test", storage_key="a1.pdf",
    )
    repository.insert_document(
        db_session, doc_id="a2", source_id=source.id, title=titulo,
        storage_bucket="iurisync-test", storage_key="a2.pdf",
    )

    assert repository.heredar_review_status_de_actuaciones_existentes(db_session, "samai", titulo) == 0


def test_heredar_review_status_no_hace_nada_si_los_decididos_no_coinciden(db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(
        db_session, family_key="samai", name="Consejo de Estado", family_params={}
    )
    titulo = "11001-03-28-000-2026-00300-00"
    repository.insert_document(
        db_session, doc_id="a1", source_id=source.id, title=titulo,
        storage_bucket="iurisync-test", storage_key="a1.pdf", review_status="useful",
    )
    repository.insert_document(
        db_session, doc_id="a2", source_id=source.id, title=titulo,
        storage_bucket="iurisync-test", storage_key="a2.pdf", review_status="not_useful",
    )
    nueva = repository.insert_document(
        db_session, doc_id="a3", source_id=source.id, title=titulo,
        storage_bucket="iurisync-test", storage_key="a3.pdf",
    )

    assert repository.heredar_review_status_de_actuaciones_existentes(db_session, "samai", titulo) == 0
    db_session.refresh(nueva)
    assert nueva.review_status == "pending"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_repository.py -k heredar_review_status -v`
Expected: FAIL con `AttributeError: module 'core.db.repository' has no attribute 'heredar_review_status_de_actuaciones_existentes'`.

- [ ] **Step 3: Implement**

En `core/db/repository.py`, justo después de `bulk_update_document_review_status`:

```python
def heredar_review_status_de_actuaciones_existentes(db: Session, family_key: str, title: str) -> int:
    """Cuando llega una actuación nueva a un caso ya revisado, la fila nueva
    entra en 'pending'. Si el resto del grupo (familia + título) coincide en un
    único estado distinto de 'pending', se lo aplica también a las 'pending'.
    Si el grupo está todo en 'pending', o los estados decididos no coinciden
    entre sí (datos previos a esta lógica), no toca nada. Devuelve cuántas
    filas actualizó."""
    grupo = list_documents_by_title_within_family(db, family_key, title)
    decididos = {d.review_status for d in grupo if d.review_status != "pending"}
    if len(decididos) != 1:
        return 0
    (estado,) = decididos
    pendientes = [d.id for d in grupo if d.review_status == "pending"]
    if not pendientes:
        return 0
    db.execute(
        update(Document)
        .where(Document.id.in_(pendientes))
        .values(review_status=estado, reviewed_at=datetime.now(timezone.utc), bulk_download_id=None)
    )
    db.commit()
    return len(pendientes)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_repository.py -k heredar_review_status -v`
Expected: PASS (los tres).

- [ ] **Step 5: Commit**

```bash
git add core/db/repository.py tests/test_repository.py
git commit -m "feat(review): actuacion nueva hereda el estado de revision del caso"
```

---

### Task 4: llamar la herencia desde `scrape_source_task`

**Files:**
- Modify: `worker/tasks.py` (bucle `for family_key, title in titulos_con_actuacion_nueva`, ~línea 540)
- Test: `tests/test_tasks.py`

**Interfaces:**
- Consumes: `repository.heredar_review_status_de_actuaciones_existentes` (Task 3), la sesión `db` local de `scrape_source_task`, el set ya existente `titulos_con_actuacion_nueva: set[tuple[str, str]]`.
- Produces: efecto observable — tras `scrape_source_task`, una actuación nueva de un caso ya marcado `useful` queda `useful`.

- [ ] **Step 1: Write the failing test**

En `tests/test_tasks.py`, junto a los demás tests de `scrape_source_task` sobre actuaciones (buscar `titulos_con_actuacion_nueva` o `reconcile_title_group` para ubicar el patrón de fixtures de ese archivo — `DummyFamilyScraper`, `celery_app.conf.task_always_eager = True`, `monkeypatch.setattr("worker.tasks.SessionLocal", ...)`). Añadir:

```python
@responses.activate
def test_scrape_source_task_new_actuacion_inherits_case_review_status(db_session, test_engine, monkeypatch):
    """Un caso 'samai' ya marcado 'useful' recibe una actuación nueva en un
    run posterior: la fila nueva debe quedar 'useful', no 'pending', para que
    la descarga masiva traiga el caso completo sin re-marcar a mano."""
    from core.utils import compute_doc_id

    celery_app.conf.task_always_eager = True
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    titulo = "11001-03-28-000-2026-00300-00"
    repository.insert_document(
        db_session, doc_id="existente", source_id=source.id, title=titulo,
        storage_bucket=TEST_S3_BUCKET, storage_key="Consejo de Estado/x/existente.pdf",
        review_status="useful", f_public="2026-01-01",
    )

    nueva = RawDocModel(
        source="Consejo de Estado",
        link={"url": "https://example.com/nueva", "method": "GET"},
        title=titulo,
        tipo="Auto",
        f_public="2026-02-01",
    )
    DummyFamilyScraper.docs_to_return = [nueva]
    responses.add(
        responses.GET, "https://example.com/nueva",
        body=b"contenido nuevo", headers={"Content-Type": "application/pdf"}, status=200,
    )

    scrape_source_task(run_source.id)

    assertion_session = task_session_factory()
    try:
        nuevo_doc_id = compute_doc_id(nueva, include_publication_date=True)
        fila = assertion_session.scalars(
            select(Document).where(Document.doc_id == nuevo_doc_id)
        ).first()
        assert fila is not None
        assert fila.review_status == "useful"
    finally:
        assertion_session.close()
```

> Nota de implementación del test: reutiliza el `DummyFamilyScraper` y los helpers (`_settings_with_test_bucket`, `TEST_S3_BUCKET`, `select`, `Document`, `sessionmaker`, `RawDocModel`, `celery_app`) tal como los importan/definen los otros tests de `scrape_source_task` en este archivo. Si `DummyFamilyScraper` está registrado bajo otra `family_key`, regístralo/monkeypatchéalo para `"samai"` siguiendo el patrón del test vecino `test_scrape_source_task_dispatches_storage_sync_after_republication`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_tasks.py::test_scrape_source_task_new_actuacion_inherits_case_review_status -v`
Expected: FAIL — `fila.review_status == "pending"`.

- [ ] **Step 3: Implement**

En `worker/tasks.py`, en el bucle de ~línea 540, añadir la llamada síncrona antes del `.delay(...)`:

```python
        for family_key, title in titulos_con_actuacion_nueva:
            # La actuación recién insertada entra 'pending'; si el caso ya
            # estaba revisado, que herede ese estado (ver spec
            # 2026-09-03-propagar-util-actuaciones). Síncrono sobre la misma
            # sesión: las filas nuevas ya se commitearon en el bucle de arriba.
            repository.heredar_review_status_de_actuaciones_existentes(db, family_key, title)
            reconcile_title_group_task.delay(family_key, title)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_tasks.py::test_scrape_source_task_new_actuacion_inherits_case_review_status -v`
Expected: PASS.

- [ ] **Step 5: Run the neighbouring scrape/actuaciones tests for regressions**

Run: `.venv/Scripts/python -m pytest tests/test_tasks.py -k "actuacion or republicac or storage_sync" -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add worker/tasks.py tests/test_tasks.py
git commit -m "feat(review): scrape_source_task hace heredar el estado a la actuacion nueva"
```

---

### Task 5: versiones archivadas dentro del ZIP de descarga masiva

**Files:**
- Modify: `worker/tasks.py` — import de `nombre_archivo_version`; reemplazar `_nombres_zip` por `_entradas_zip`; adaptar `build_bulk_download_zip` (estimación de espacio + bucle de escritura, ~líneas 700-766)
- Test: `tests/test_tasks.py`

**Interfaces:**
- Consumes: `repository.list_document_versions(db, document_id) -> list[DocumentVersion]` (línea ~481, orden `superseded_at` DESC), `core.naming.nombre_archivo_documento`, `core.naming.nombre_archivo_version(document, version, family_key, tiene_actuaciones) -> str` (`core/naming.py` línea ~83), `_carpeta_zip(document, source_names) -> str` (ya existe), `repository.actuacion_counts_by_title`.
- Produces:
  - `_entradas_zip(documents, versions_by_doc, family_keys, actuacion_counts, source_names) -> list[_EntradaZip]` donde
    `_EntradaZip = namedtuple("_EntradaZip", "storage_bucket storage_key arcname document_id")`
    (`document_id` es el del `Document` dueño, tanto para su archivo vigente como para cada versión archivada). Mantiene la desambiguación ` (2)`, ` (3)` de rutas repetidas dentro de la misma carpeta.

- [ ] **Step 1: Write the failing test**

En `tests/test_tasks.py`, después de `test_build_bulk_download_zip_uploads_zip_using_canonical_names` (~línea 1734):

```python
def test_build_bulk_download_zip_includes_archived_versions_of_a_useful_document(db_session, test_engine, monkeypatch):
    from pathlib import Path
    import tempfile
    import zipfile

    from core.storage import presigned_url, upload_file
    from worker.tasks import build_bulk_download_zip

    celery_app.conf.task_always_eager = True
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    repository.create_source_family(db_session, key="jep", display_name="JEP")
    source = repository.create_source(db_session, family_key="jep", name="JEP", family_params={})

    with tempfile.TemporaryDirectory() as tmp:
        vigente = Path(tmp) / "v.pdf"
        vigente.write_bytes(b"contenido vigente")
        upload_file(vigente, "JEP/2026-06-01/Auto/vigente.pdf", bucket=TEST_S3_BUCKET, content_type="application/pdf")
        archivada = Path(tmp) / "a.pdf"
        archivada.write_bytes(b"contenido archivado")
        upload_file(archivada, "JEP/2026-06-01/Auto/archivada.pdf", bucket=TEST_S3_BUCKET, content_type="application/pdf")

    doc = repository.insert_document(
        db_session, doc_id="doc-1", source_id=source.id, title="Doc 1", review_status="useful",
        storage_bucket=TEST_S3_BUCKET, storage_key="JEP/2026-06-01/Auto/vigente.pdf",
        f_public=date(2026, 6, 1), tipo="Auto",
    )
    # Deja al documento con una versión archivada (version_no del vigente pasa a 2).
    repository.archive_and_replace_document(
        db_session, doc.id, storage_bucket=TEST_S3_BUCKET, storage_key="JEP/2026-06-01/Auto/vigente.pdf",
    )
    [version] = repository.list_document_versions(db_session, doc.id)
    version.storage_key = "JEP/2026-06-01/Auto/archivada.pdf"
    db_session.commit()

    bulk_download = repository.create_bulk_download(db_session)
    build_bulk_download_zip(bulk_download.id)

    assertion_session = task_session_factory()
    try:
        refreshed = repository.get_bulk_download(assertion_session, bulk_download.id)
        assert refreshed.status == "completed"
        url = presigned_url(TEST_S3_BUCKET, refreshed.zip_storage_key)
        import requests
        response = requests.get(url, timeout=10)
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "r.zip"
            zip_path.write_bytes(response.content)
            with zipfile.ZipFile(zip_path) as zf:
                names = set(zf.namelist())
                # 'jep' no es familia con actuaciones -> nombre = titulo + [-v{n}] + ext.
                assert "JEP/2026-06-01/Auto/Doc 1.pdf" in names
                assert "JEP/2026-06-01/Auto/Doc 1-v1.pdf" in names
                assert zf.read("JEP/2026-06-01/Auto/Doc 1-v1.pdf") == b"contenido archivado"
    finally:
        assertion_session.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_tasks.py::test_build_bulk_download_zip_includes_archived_versions_of_a_useful_document -v`
Expected: FAIL — `"JEP/2026-06-01/Auto/Doc 1-v1.pdf"` no está en el ZIP.

- [ ] **Step 3: Add the import and replace `_nombres_zip` with `_entradas_zip`**

En `worker/tasks.py` línea 20, ampliar el import:

```python
from core.naming import es_familia_con_actuaciones, nombre_archivo_documento, nombre_archivo_version
```

Añadir cerca de los otros imports de stdlib (línea ~1-10) si no está ya:

```python
from collections import namedtuple
```

Reemplazar toda la función `_nombres_zip` (~líneas 45-67) por:

```python
_EntradaZip = namedtuple("_EntradaZip", "storage_bucket storage_key arcname document_id")


def _entradas_zip(documents, versions_by_doc, family_keys, actuacion_counts, source_names) -> list["_EntradaZip"]:
    """Una entrada por cada archivo que va al ZIP: el archivo vigente de cada
    documento y, a continuación, cada una de sus versiones archivadas. La ruta
    es Fuente/Fecha/Tipo/nombre_canónico(+ext). Desambigua colisiones dentro de
    la misma carpeta agregando ' (2)', ' (3)'… antes de la extensión.
    actuacion_counts (de repository.actuacion_counts_by_title) decide si la
    fecha del nombre va completa o solo el año."""
    usados: dict[str, int] = {}
    entradas: list[_EntradaZip] = []

    def _ruta_unica(carpeta: str, base: str) -> str:
        ruta = f"{carpeta}/{base}"
        if ruta not in usados:
            usados[ruta] = 1
            return ruta
        usados[ruta] += 1
        p = PurePosixPath(base)
        return f"{carpeta}/{p.stem} ({usados[ruta]}){p.suffix}"

    for d in documents:
        fam = family_keys.get(d.source_id)
        tiene_actuaciones = actuacion_counts.get(d.title, 0) > 1
        carpeta = _carpeta_zip(d, source_names)
        base_doc = nombre_archivo_documento(d, fam, tiene_actuaciones)
        entradas.append(_EntradaZip(d.storage_bucket, d.storage_key, _ruta_unica(carpeta, base_doc), d.id))
        for v in versions_by_doc.get(d.id, []):
            base_v = nombre_archivo_version(d, v, fam, tiene_actuaciones)
            entradas.append(_EntradaZip(v.storage_bucket, v.storage_key, _ruta_unica(carpeta, base_v), d.id))
    return entradas
```

- [ ] **Step 4: Rewire `build_bulk_download_zip`**

En `build_bulk_download_zip` (`worker/tasks.py`):

1. Después de `documents = repository.list_useful_documents(db)` y el early-return por lista vacía (~línea 689), construir el mapa de versiones:

```python
        versions_by_doc = {d.id: repository.list_document_versions(db, d.id) for d in documents}
```

2. Reemplazar el bloque de estimación de espacio (~líneas 701-703) por:

```python
            known_sizes = [d.file_size_bytes for d in documents if d.file_size_bytes]
            known_sizes += [
                v.file_size_bytes
                for vs in versions_by_doc.values()
                for v in vs
                if v.file_size_bytes
            ]
            total_items = len(documents) + sum(len(vs) for vs in versions_by_doc.values())
            if known_sizes and len(known_sizes) == total_items:
                required_bytes = sum(known_sizes) + max(known_sizes)
```

   (el resto del `if` — `free_bytes = shutil.disk_usage(...)` y el fallo por espacio — no cambia).

3. Reemplazar el cálculo de `arcnames` y el bucle de escritura (~líneas 731-764). Antes:

```python
            family_keys = repository.get_source_family_keys(db, [d.source_id for d in documents])
            actuacion_counts = repository.actuacion_counts_by_title(db, documents, family_keys)
            source_names = repository.get_source_names(db, [d.source_id for d in documents])
            arcnames = _nombres_zip(documents, family_keys, actuacion_counts, source_names)
            included_document_ids: list[int] = []
            failed_documents: list[tuple[int, str]] = []
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for document, arcname in zip(documents, arcnames):
                    if not is_safe_storage_key(document.storage_key):
                        logger.warning(
                            "Clave de almacenamiento no segura, se omite de la descarga masiva: %s", document.storage_key
                        )
                        failed_count += 1
                        failed_documents.append((document.id, document.title))
                        continue
                    local_path = downloads_dir / document.storage_key
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        download_file(document.storage_bucket, document.storage_key, local_path)
                        zf.write(local_path, arcname=arcname)
                        downloaded_count += 1
                        included_document_ids.append(document.id)
                    except Exception as exc:
                        logger.warning("No se pudo incluir %s en la descarga masiva: %s", document.storage_key, exc)
                        failed_count += 1
                        failed_documents.append((document.id, document.title))
                    finally:
                        local_path.unlink(missing_ok=True)
```

Después:

```python
            family_keys = repository.get_source_family_keys(db, [d.source_id for d in documents])
            actuacion_counts = repository.actuacion_counts_by_title(db, documents, family_keys)
            source_names = repository.get_source_names(db, [d.source_id for d in documents])
            entradas = _entradas_zip(documents, versions_by_doc, family_keys, actuacion_counts, source_names)
            titulo_por_doc_id = {d.id: d.title for d in documents}
            included_document_ids: list[int] = []
            failed_documents: list[tuple[int, str]] = []
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for entrada in entradas:
                    if not is_safe_storage_key(entrada.storage_key):
                        logger.warning(
                            "Clave de almacenamiento no segura, se omite de la descarga masiva: %s", entrada.storage_key
                        )
                        failed_count += 1
                        failed_documents.append((entrada.document_id, titulo_por_doc_id.get(entrada.document_id, "")))
                        continue
                    local_path = downloads_dir / entrada.storage_key
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        download_file(entrada.storage_bucket, entrada.storage_key, local_path)
                        zf.write(local_path, arcname=entrada.arcname)
                        downloaded_count += 1
                        included_document_ids.append(entrada.document_id)
                    except Exception as exc:
                        logger.warning("No se pudo incluir %s en la descarga masiva: %s", entrada.storage_key, exc)
                        failed_count += 1
                        failed_documents.append((entrada.document_id, titulo_por_doc_id.get(entrada.document_id, "")))
                    finally:
                        local_path.unlink(missing_ok=True)
```

Nota: `included_document_ids` puede ahora repetir un id (vigente + versión); `mark_documents_bulk_downloaded` hace `UPDATE ... WHERE id IN (...)`, así que el repetido es inofensivo. `downloaded_count`/`failed_count` ahora cuentan archivos (incluye versiones), que es lo correcto para el mensaje "se metieron N archivos".

- [ ] **Step 5: Run the bulk-download tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_tasks.py -k build_bulk_download_zip -v`
Expected: PASS — el nuevo test más todos los preexistentes (`..._uploads_zip_using_canonical_names`, `..._excludes_documents_already_included...`, `..._skips_a_document_that_fails_to_download`, `..._skips_a_document_with_an_unsafe_storage_key`, `..._fails_when_every_document_fails_to_download`, `..._truncates_the_failed_document_list_beyond_ten`, `..._fails_when_there_are_no_useful_documents`, `..._frees_each_raw_copy_as_soon_as_its_zipped`, `..._fails_early_when_disk_space_is_insufficient`, `..._skips_the_disk_space_check_when_a_document_size_is_unknown`).

Si alguno preexistente falla por el conteo (`document_count`), revisar que su expectativa siga válida: los que no tienen versiones archivadas no cambian de conteo.

- [ ] **Step 6: Grep for other `_nombres_zip` callers**

Run: `grep -rn "_nombres_zip" worker/ tests/`
Expected: 0 resultados fuera de historial. Si un test llamaba `_nombres_zip` directo, reescribirlo contra `_entradas_zip` (mismo cálculo de rutas; ahora devuelve `_EntradaZip` en vez de `str`).

- [ ] **Step 7: Commit**

```bash
git add worker/tasks.py tests/test_tasks.py
git commit -m "feat(descarga-masiva): incluir las versiones archivadas de cada documento util"
```

---

### Task 6: el visor refleja el grupo completo al marcar

**Files:**
- Modify: `frontend/src/components/DocumentPreviewDialog.tsx` (`markMutation.onSuccess` y `markOtherMutation.onSuccess`, ~líneas 98-128)
- Test: `frontend/src/components/DocumentPreviewDialog.test.tsx`

**Interfaces:**
- Consumes: el tipo `Document` (`frontend/src/api/types.ts`: `id`, `source_id`, `title`, `review_status`, `reviewed_at`), la respuesta `Document` de `updateDocumentReviewStatus`.
- Produces: efecto de UI — al marcar una actuación (footer o lista "Otras actuaciones"), todas las filas del `documentsSnapshot` con el mismo `(title, source_id)` que la marcada pasan al nuevo `review_status`/`reviewed_at`.

- [ ] **Step 1: Write the failing test**

En `frontend/src/components/DocumentPreviewDialog.test.tsx`, dentro del bloque que ya usa `showCaseActuaciones` (buscar `"marking another actuación as useful from the list"`, ~línea 538). Añadir después de ese test:

```tsx
  it("marking one actuación from the list reflects the new status on every sibling of the same case", async () => {
    const user = userEvent.setup();
    const documents = [
      makeDocument({ id: 60, title: "Caso X", source_id: 7, detalle: "Auto Actual", review_status: "pending" }),
      makeDocument({ id: 61, title: "Caso X", source_id: 7, detalle: "Auto Anterior", review_status: "pending" }),
      makeDocument({ id: 62, title: "Caso X", source_id: 7, detalle: "Auto Primero", review_status: "pending" }),
    ];
    server.use(
      http.patch(`${BASE_URL}/documents/61`, async () =>
        HttpResponse.json({ ...documents[1], review_status: "useful", reviewed_at: "2026-09-03T00:00:00Z" })
      )
    );

    render(
      <DocumentPreviewDialog documents={documents} initialIndex={0} open onOpenChange={() => {}} showCaseActuaciones />
    );

    // Marca "Útil" en la primera actuación de la lista (id 61).
    const fila = (await screen.findByText("Auto Anterior")).closest("li")!;
    await user.click(within(fila).getByRole("button", { name: "Útil" }));

    // La otra hermana de la lista (id 62) también aparece ahora como marcada:
    // su botón "Útil" queda deshabilitado / con estado activo (ver cómo el
    // componente representa "ya marcado" — el test vecino
    // "lets the user set a sibling actuación back to pending" muestra el patrón).
    await waitFor(() => {
      const filaPrimero = screen.getByText("Auto Primero").closest("li")!;
      expect(within(filaPrimero).getByRole("button", { name: /pendiente/i })).toBeInTheDocument();
    });
  });
```

> Nota: ajustar la aserción final al patrón real del componente para "sibling ya marcado" (el test `"lets the user set a sibling actuación back to pending from the list, shown only when it's already marked"` en el mismo archivo indica cómo se ve un sibling marcado — botón "Pendiente" visible). Importar `within` de `@testing-library/react` si no está.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run src/components/DocumentPreviewDialog.test.tsx -t "reflects the new status on every sibling"`
Expected: FAIL — sólo la fila 61 cambia; la 62 sigue "pending".

- [ ] **Step 3: Implement**

En `frontend/src/components/DocumentPreviewDialog.tsx`, añadir un helper dentro del componente (antes de `markMutation`):

```tsx
  function aplicarEstadoAlCaso(updated: Document) {
    setDocumentsSnapshot((snapshot) =>
      snapshot.map((doc) =>
        doc.title === updated.title && doc.source_id === updated.source_id
          ? { ...doc, review_status: updated.review_status, reviewed_at: updated.reviewed_at }
          : doc
      )
    );
  }
```

En `markMutation.onSuccess`, que hoy es `onSuccess: () => { ... }`, pasarlo a recibir la respuesta y actualizar el caso antes de avanzar/cerrar:

```tsx
  const markMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: DocumentReviewStatus }) => updateDocumentReviewStatus(id, status),
    onSuccess: (updated) => {
      setMarkError(null);
      aplicarEstadoAlCaso(updated);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      if (isLast) {
        onOpenChange(false);
      } else {
        setCurrentIndex((index) => index + 1);
      }
    },
    onError: () => setMarkError("Error al marcar el documento"),
  });
```

En `markOtherMutation.onSuccess`, reemplazar el `setDocumentsSnapshot(...)` que sólo toca `updated.id` por `aplicarEstadoAlCaso(updated)`:

```tsx
  const markOtherMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: DocumentReviewStatus }) => updateDocumentReviewStatus(id, status),
    onSuccess: (updated) => {
      setMarkOtherError(null);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      aplicarEstadoAlCaso(updated);
    },
    onError: () => setMarkOtherError("Error al marcar la actuación"),
  });
```

Asegurar que `Document` está importado como tipo en el archivo (revisar los imports de `../api/types`; añadir `Document` a esa lista si falta).

- [ ] **Step 4: Run the dialog tests to verify they pass**

Run: `cd frontend && npm test -- --run src/components/DocumentPreviewDialog.test.tsx`
Expected: PASS — el nuevo test y todos los preexistentes (en especial `"marking another actuación as useful from the list updates only that document, without advancing past the current one"`: sigue sin avanzar el índice ni cerrar; ahora además refleja a las hermanas, lo cual no contradice ese test — si su aserción fuese "las demás NO cambian", actualizarla: bajo la nueva semántica el caso entero cambia).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DocumentPreviewDialog.tsx frontend/src/components/DocumentPreviewDialog.test.tsx
git commit -m "feat(visor): marcar una actuacion refleja el estado en todo el caso"
```

---

### Task 7: verificación integral

**Files:** ninguno (sólo ejecución)

- [ ] **Step 1: Suite backend completa (sin el test de migraciones roto de siempre)**

Run: `.venv/Scripts/python -m pytest -q --deselect tests/test_migrations.py::test_alembic_upgrade_head_creates_all_tables`
Expected: todo PASS salvo el deseleccionado. Si algo de `test_api_documents.py` sobre `PATCH /documents/{id}` o `/documents/bulk-review` falla, revisar que su expectativa no asumiera "solo una fila cambia" — actualizarla al comportamiento nuevo (propaga al caso) y volver a correr.

- [ ] **Step 2: Suite frontend completa**

Run: `cd frontend && npm test -- --run`
Expected: todo PASS.

- [ ] **Step 3: Commit (si algún test preexistente necesitó ajuste de expectativa)**

```bash
git add -A
git commit -m "test: ajustar expectativas al nuevo comportamiento de propagacion por caso"
```

---

## Self-Review

**1. Spec coverage:**

- Spec §"Definición de grupo" → Task 1 (`_expandir_a_grupos` usa `es_familia_con_actuaciones` + `list_documents_by_title_within_family`). ✔
- Spec §1 "propagación al marcar" (endpoint individual) → Task 1. ✔
- Spec §1 (endpoint bulk) → Task 2. ✔
- Spec §1 "simétrico para los tres estados" → Tasks 1-2 usan un `.values(review_status=...)` genérico; test de simetría en Task 1. ✔
- Spec §2 "herencia opción C" (función + llamada en `scrape_source_task`) → Task 3 (función) + Task 4 (cableado). ✔
- Spec §3 "versiones archivadas en el ZIP" (entrada por versión, nombre `nombre_archivo_version`, misma carpeta, estimación de espacio, entregado vía `bulk_download_id` del padre) → Task 5. ✔
- Spec §4 "frontend: snapshot de todo el caso" → Task 6. ✔
- Spec §"Pruebas" (repositorio, worker, frontend) → tests en Tasks 1-6; barrido final en Task 7. ✔
- Spec §"Riesgos": datos heredados mezclados → cubierto por `test_heredar_review_status_no_hace_nada_si_los_decididos_no_coinciden` (Task 3). ✔

Sin huecos.

**2. Placeholder scan:** No hay "TBD/TODO/etc." Todos los pasos de código traen el bloque real. Las dos "Notas" (Task 4 sobre `DummyFamilyScraper`, Task 6 sobre el patrón de sibling marcado) apuntan a un test vecino concreto del mismo archivo como referencia, no son placeholders de implementación.

**3. Type consistency:**
- `_expandir_a_grupos(db, document_ids: list[int]) -> list[int]` — definida en Task 1, consumida con esa firma en Task 2. ✔
- `heredar_review_status_de_actuaciones_existentes(db, family_key: str, title: str) -> int` — Task 3, llamada en Task 4 con `(db, family_key, title)`. ✔
- `_EntradaZip` namedtuple con campos `storage_bucket storage_key arcname document_id` — definido y consumido dentro de Task 5, coherente en `_entradas_zip` y en el bucle de `build_bulk_download_zip`. ✔
- `aplicarEstadoAlCaso(updated: Document)` — Task 6, usado en ambos `onSuccess`. ✔
- `nombre_archivo_version(document, version, family_key, tiene_actuaciones)` — firma tomada de `core/naming.py` línea ~83. ✔

Sin inconsistencias.
