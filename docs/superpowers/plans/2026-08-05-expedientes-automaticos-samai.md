# Expedientes automáticos entre tribunales (SAMAI) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que los expedientes que cruzan más de una fuente SAMAI se armen automáticamente (sin confirmación humana), se listen en una sección "Expedientes", muestren cada documento abrible en la línea de tiempo, y permitan quitar una etapa que no corresponda (recordando esa separación).

**Architecture:** Se reutilizan las tablas `case_links` y `case_link_stages` y la lógica de unión `_link_case_group`. El generador de sugerencias se reemplaza por un armado directo (`assemble_case_links`) que corre tras cada run y en el backfill. Se agrega una tabla `case_link_separations` (instancias que una persona quitó, para no volver a unirlas) y se elimina toda la maquinaria de sugerencias pendientes y de vinculación manual.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (backend), React + TanStack Query + React Router (frontend), pytest / vitest.

## Global Constraints

- Solo dentro de la familia `samai`. Solo expedientes que cruzan **más de una fuente**.
- El umbral de coincidencia es `MIN_MATCH_DIGITS = 21` (ya existe en `core/utils.py`) — los primeros 21 dígitos identifican el proceso; los dígitos 22-23 son la instancia.
- Nunca se muestra el radicado como columna en la tabla de Documentos (decisión previa).
- El armado corre después de guardar los documentos del run; un fallo ahí nunca debe tumbar el run.
- No hay "deshacer" una separación desde la interfaz (fuera de alcance v1).
- Correr las pruebas de backend **archivo por archivo** (`.venv/Scripts/pytest tests/<archivo>.py`), no toda la suite en una sola corrida — combinar muchos archivos dispara un bloqueo conocido en la base de pruebas.

---

## Mapa de archivos

**Backend — modificados:**
- `core/db/models.py` (+ `CaseLinkSeparation`; al final se quita `CaseLinkSuggestion`)
- `alembic/versions/<generado_1>_add_case_link_separations.py` (crea la tabla nueva)
- `alembic/versions/<generado_2>_drop_case_link_suggestions.py` (elimina la tabla vieja)
- `core/db/repository.py` (armado automático, separaciones, listado; se quita la maquinaria de sugerencias)
- `worker/tasks.py` (`_finalize_run` llama al armado)
- `core/backfill_samai_radicado.py` (llama al armado)
- `api/schemas.py` (+ `CaseLinkListItemOut`, `stage_id` en `CaseLinkStageOut`; se quitan schemas de sugerencia/manual; se simplifica `DocumentOut`)
- `api/routers/case_links.py` (listar expedientes, quitar etapa; se quitan endpoints de sugerencia/manual)
- `api/routers/documents.py` (nota simplificada)
- `tests/test_repository.py`, `tests/test_tasks.py`, `tests/test_backfill_samai_radicado.py`, `tests/test_api_case_links.py`, `tests/test_api_documents.py` (casos nuevos; se quitan los de sugerencias)

**Frontend — modificados/creados:**
- `frontend/src/api/caseLinks.ts`, `frontend/src/api/types.ts`
- Crear `frontend/src/pages/ExpedientesPage.tsx` (+ `.test.tsx`); eliminar `frontend/src/pages/CaseLinksPage.tsx` (+ `.test.tsx`)
- `frontend/src/pages/CaseLinkDetailPage.tsx` (+ `.test.tsx`)
- `frontend/src/App.tsx`, `frontend/src/components/layout/Sidebar.tsx`
- `frontend/src/pages/DocumentsPage.tsx` (+ `.test.tsx`)

---

### Task 1: Tabla y modelo de separaciones

**Files:**
- Modify: `core/db/models.py`
- Create: `alembic/versions/<generado>_add_case_link_separations.py`
- Test: `tests/test_migrations.py` (ya cubre "todas las tablas existen"; se le agrega la nueva a `EXPECTED_TABLES`)

**Interfaces:**
- Produces: modelo `CaseLinkSeparation` (`case_link_separations`) — consumido por `core/db/repository.py` (Tasks 2, 3).

- [ ] **Step 1: Agregar la tabla esperada a la prueba de migraciones**

En `tests/test_migrations.py`, agregar `"case_link_separations"` al conjunto `EXPECTED_TABLES`.

- [ ] **Step 2: Confirmar que falla**

Primero recrear la base de pruebas limpia (evita estado viejo):
```bash
docker exec scrapper-avanzado-postgres-1 psql -U iurisync -d postgres -c "DROP DATABASE IF EXISTS iurisync_test;" -c "CREATE DATABASE iurisync_test OWNER iurisync;"
```
Run (con el venv en PATH para que `alembic` resuelva): `PATH="$(pwd)/.venv/Scripts:$PATH" .venv/Scripts/pytest tests/test_migrations.py -q`
Expected: FAIL — falta la tabla `case_link_separations`.

- [ ] **Step 3: Agregar el modelo ORM**

En `core/db/models.py`, después de `class CaseLinkStage`, agregar:

```python
class CaseLinkSeparation(Base):
    __tablename__ = "case_link_separations"

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    radicado = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (UniqueConstraint("source_id", "radicado", name="uq_case_link_separations_source_radicado"),)
```

Confirmar que `UniqueConstraint` está importado en la cabecera de `core/db/models.py` (junto a `Column`, `ForeignKey`, etc.); si no, agregarlo al import de `sqlalchemy`.

- [ ] **Step 4: Generar y escribir la migración**

Run: `PATH="$(pwd)/.venv/Scripts:$PATH" .venv/Scripts/alembic revision -m "add case link separations"`

En el archivo generado, reemplazar el cuerpo:

```python
def upgrade() -> None:
    op.create_table(
        'case_link_separations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('radicado', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_id', 'radicado', name='uq_case_link_separations_source_radicado'),
    )


def downgrade() -> None:
    op.drop_table('case_link_separations')
```

- [ ] **Step 5: Confirmar que pasa**

Run: `PATH="$(pwd)/.venv/Scripts:$PATH" .venv/Scripts/pytest tests/test_migrations.py -q`
Expected: PASSED

- [ ] **Step 6: Commit**

```bash
git add core/db/models.py alembic/versions/ tests/test_migrations.py
git commit -m "feat: tabla case_link_separations para instancias separadas a mano"
```

---

### Task 2: Armado automático de expedientes

**Files:**
- Modify: `core/db/repository.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: `matching_prefix_length`, `MIN_MATCH_DIGITS` (`core/utils.py`), `_link_case_group`, `_get_case_link_stage`, `_samai_case_groups` (ya existen), `CaseLinkSeparation` (Task 1).
- Produces: `assemble_case_links(db, new_groups: list[tuple[int, str]]) -> int`, `assemble_case_links_for_run(db, run_id: int) -> int`, `_separated_instances(db) -> set[tuple[int, str]]` — consumidos por `worker/tasks.py` y `core/backfill_samai_radicado.py` (Task 5).

Nota: en esta tarea se **agregan** las funciones de armado junto a las de sugerencia existentes; el cambio de `worker`/`backfill` para usarlas es la Task 5, y la eliminación de la maquinaria de sugerencias es la Task 8.

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `tests/test_repository.py` (usan el helper `_make_samai_source` ya existente):

```python
def test_assemble_case_links_creates_expediente_directly_across_sources(db_session):
    tribunal = _make_samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _make_samai_source(db_session, "Consejo de Estado")
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=tribunal.id)
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, run_source_id=run_source.id,
        title="t1", radicado="05001233300020180047100", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id,
        title="t2", radicado="05001233300020180047101", storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    linked = repository.assemble_case_links_for_run(db_session, run.id)

    assert linked == 1
    [case_link] = db_session.query(repository.CaseLink).all()
    stages = {(s.source_id, s.radicado) for s in repository.list_case_link_stages(db_session, case_link.id)}
    assert stages == {
        (tribunal.id, "05001233300020180047100"),
        (consejo.id, "05001233300020180047101"),
    }


def test_assemble_case_links_is_idempotent(db_session):
    tribunal = _make_samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _make_samai_source(db_session, "Consejo de Estado")
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=tribunal.id)
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, run_source_id=run_source.id,
        title="t1", radicado="05001233300020180047100", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id,
        title="t2", radicado="05001233300020180047101", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    repository.assemble_case_links_for_run(db_session, run.id)

    linked_again = repository.assemble_case_links_for_run(db_session, run.id)

    assert linked_again == 0
    assert db_session.query(repository.CaseLink).count() == 1


def test_assemble_case_links_skips_separated_instances(db_session):
    tribunal = _make_samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _make_samai_source(db_session, "Consejo de Estado")
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=tribunal.id)
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, run_source_id=run_source.id,
        title="t1", radicado="05001233300020180047100", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id,
        title="t2", radicado="05001233300020180047101", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    # La instancia del Consejo se marca como separada -> no debe volver a unirse.
    db_session.add(repository.CaseLinkSeparation(source_id=consejo.id, radicado="05001233300020180047101"))
    db_session.commit()

    linked = repository.assemble_case_links_for_run(db_session, run.id)

    assert linked == 0
    assert db_session.query(repository.CaseLink).count() == 0
```

- [ ] **Step 2: Confirmar que fallan**

Run: `.venv/Scripts/pytest tests/test_repository.py -k assemble_case_links -v`
Expected: FAIL — `assemble_case_links_for_run` no existe.

- [ ] **Step 3: Implementar**

En `core/db/repository.py`, agregar `CaseLinkSeparation` al import desde `core.db.models`. Agregar (después de `generate_case_link_suggestions_for_run`):

```python
def _separated_instances(db: Session) -> set[tuple[int, str]]:
    rows = db.execute(select(CaseLinkSeparation.source_id, CaseLinkSeparation.radicado)).all()
    return {(source_id, radicado) for source_id, radicado in rows}


def assemble_case_links(db: Session, new_groups: list[tuple[int, str]]) -> int:
    """Por cada (source_id, radicado) en new_groups, compara contra TODOS los
    grupos samai existentes de una fuente distinta; por cada coincidencia de al
    menos MIN_MATCH_DIGITS dígitos iniciales (y que ninguna de las dos instancias
    esté separada a mano), une las dos instancias en un expediente vía
    _link_case_group. Devuelve cuántos cruces cambiaron el agrupamiento (etapa
    nueva o fusión); las uniones ya existentes no se cuentan. No crea sugerencias
    pendientes: arma el expediente directamente."""
    all_groups = _samai_case_groups(db)
    separated = _separated_instances(db)
    linked = 0
    for source_id, radicado in new_groups:
        if (source_id, radicado) in separated:
            continue
        for other_source_id, other_radicado in all_groups:
            if other_source_id == source_id:
                continue
            if (other_source_id, other_radicado) in separated:
                continue
            if matching_prefix_length(radicado, other_radicado) < MIN_MATCH_DIGITS:
                continue
            stage_a = _get_case_link_stage(db, source_id, radicado)
            stage_b = _get_case_link_stage(db, other_source_id, other_radicado)
            already_together = (
                stage_a is not None and stage_b is not None and stage_a.case_link_id == stage_b.case_link_id
            )
            _link_case_group(db, source_id, radicado, other_source_id, other_radicado)
            if not already_together:
                linked += 1
    return linked


def assemble_case_links_for_run(db: Session, run_id: int) -> int:
    """Se corre después de que un run terminó de guardar sus documentos (ver
    worker/tasks.py::_finalize_run). Solo mira los documentos que este run
    concreto insertó/tocó (vía run_source_id), para las fuentes samai que
    participaron en él."""
    run_sources = list_run_sources(db, run_id)
    samai_run_source_ids = {
        rs.id for rs in run_sources
        if (source := db.get(Source, rs.source_id)) is not None and source.family_key == "samai"
    }
    if not samai_run_source_ids:
        return 0
    stmt = (
        select(Document.source_id, Document.radicado)
        .where(Document.run_source_id.in_(samai_run_source_ids), Document.radicado.is_not(None))
        .distinct()
    )
    new_groups = list(db.execute(stmt).all())
    return assemble_case_links(db, new_groups)
```

- [ ] **Step 4: Confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_repository.py -k assemble_case_links -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add core/db/repository.py tests/test_repository.py
git commit -m "feat: arma expedientes automáticamente (reemplazo del generador de sugerencias)"
```

---

### Task 3: Quitar una etapa (separación) y disolver expediente

**Files:**
- Modify: `core/db/repository.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: `CaseLink`, `CaseLinkStage`, `CaseLinkSeparation`, `_link_case_group`, `list_case_link_stages`.
- Produces: `separate_case_link_stage(db, case_link_id: int, stage_id: int) -> Optional[dict]` — consumido por `api/routers/case_links.py` (Task 7). Devuelve `None` si la etapa no existe en ese expediente; `{"dissolved": bool, "case_link_id": int | None}` en caso contrario.

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `tests/test_repository.py`:

```python
def _assembled_case_link(db_session, tribunal, consejo):
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, title="t1",
        radicado="05001233300020180047100", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id, title="t2",
        radicado="05001233300020180047101", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    return repository._link_case_group(
        db_session, tribunal.id, "05001233300020180047100", consejo.id, "05001233300020180047101"
    )


def test_separate_case_link_stage_dissolves_a_two_stage_expediente_and_records_separation(db_session):
    tribunal = _make_samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _make_samai_source(db_session, "Consejo de Estado")
    case_link = _assembled_case_link(db_session, tribunal, consejo)
    [consejo_stage] = [s for s in repository.list_case_link_stages(db_session, case_link.id) if s.source_id == consejo.id]

    result = repository.separate_case_link_stage(db_session, case_link.id, consejo_stage.id)

    assert result == {"dissolved": True, "case_link_id": None}
    # El expediente se disolvió (quedaba con una sola fuente).
    assert db_session.get(repository.CaseLink, case_link.id) is None
    assert repository.list_case_link_stages(db_session, case_link.id) == []
    # La instancia quitada quedó registrada como separada.
    assert (consejo.id, "05001233300020180047101") in repository._separated_instances(db_session)
    # Los documentos NO se tocaron.
    assert len(repository.list_documents_by_source_and_radicado(db_session, consejo.id, "05001233300020180047101")) == 1


def test_separate_case_link_stage_keeps_expediente_when_two_sources_remain(db_session):
    tribunal = _make_samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _make_samai_source(db_session, "Consejo de Estado")
    tercera = _make_samai_source(db_session, "Consejo de Estado - Sección Tercera")
    case_link = _assembled_case_link(db_session, tribunal, consejo)
    # Tercera etapa del mismo proceso.
    repository.insert_document(
        db_session, doc_id="doc-c", source_id=tercera.id, title="t3",
        radicado="05001233300020180047102", storage_bucket="iurisync-test", storage_key="c.pdf",
    )
    repository._link_case_group(
        db_session, consejo.id, "05001233300020180047101", tercera.id, "05001233300020180047102"
    )
    [tercera_stage] = [s for s in repository.list_case_link_stages(db_session, case_link.id) if s.source_id == tercera.id]

    result = repository.separate_case_link_stage(db_session, case_link.id, tercera_stage.id)

    assert result == {"dissolved": False, "case_link_id": case_link.id}
    remaining = {s.source_id for s in repository.list_case_link_stages(db_session, case_link.id)}
    assert remaining == {tribunal.id, consejo.id}


def test_separate_case_link_stage_returns_none_when_stage_not_in_expediente(db_session):
    tribunal = _make_samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _make_samai_source(db_session, "Consejo de Estado")
    case_link = _assembled_case_link(db_session, tribunal, consejo)

    assert repository.separate_case_link_stage(db_session, case_link.id, 999999) is None
```

- [ ] **Step 2: Confirmar que fallan**

Run: `.venv/Scripts/pytest tests/test_repository.py -k separate_case_link_stage -v`
Expected: FAIL — `separate_case_link_stage` no existe.

- [ ] **Step 3: Implementar**

En `core/db/repository.py`, agregar:

```python
def _record_separation(db: Session, source_id: int, radicado: str) -> None:
    exists = db.scalars(
        select(CaseLinkSeparation.id).where(
            CaseLinkSeparation.source_id == source_id, CaseLinkSeparation.radicado == radicado
        )
    ).first()
    if exists is None:
        db.add(CaseLinkSeparation(source_id=source_id, radicado=radicado))


def separate_case_link_stage(db: Session, case_link_id: int, stage_id: int) -> Optional[dict]:
    """Quita una etapa (instancia) de un expediente: registra la separación para
    que el armado no la vuelva a unir, borra la etapa, y si el expediente queda
    con menos de dos fuentes distintas lo disuelve. Los documentos no se tocan.
    Devuelve None si la etapa no pertenece a ese expediente."""
    stage = db.get(CaseLinkStage, stage_id)
    if stage is None or stage.case_link_id != case_link_id:
        return None

    _record_separation(db, stage.source_id, stage.radicado)
    db.delete(stage)
    db.commit()

    remaining = list_case_link_stages(db, case_link_id)
    if len({s.source_id for s in remaining}) < 2:
        for s in remaining:
            db.delete(s)
        case_link = db.get(CaseLink, case_link_id)
        if case_link is not None:
            db.delete(case_link)
        db.commit()
        return {"dissolved": True, "case_link_id": None}

    return {"dissolved": False, "case_link_id": case_link_id}
```

- [ ] **Step 4: Confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_repository.py -k separate_case_link_stage -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add core/db/repository.py tests/test_repository.py
git commit -m "feat: quitar una etapa del expediente (separación) y disolver si queda una sola fuente"
```

---

### Task 4: Listar expedientes con resumen

**Files:**
- Modify: `core/db/repository.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Produces: `list_case_links_with_summary(db) -> list[dict]` con claves `id`, `source_names` (list[str] ordenada), `radicados` (list[str] ordenada), `stage_count` (int), `document_count` (int), `f_public_min` (date|None), `f_public_max` (date|None) — consumido por `api/routers/case_links.py` (Task 7).

- [ ] **Step 1: Escribir la prueba que falla**

Agregar a `tests/test_repository.py`:

```python
def test_list_case_links_with_summary_reports_sources_counts_and_dates(db_session):
    tribunal = _make_samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _make_samai_source(db_session, "Consejo de Estado")
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, title="t1", radicado="05001233300020180047100",
        f_public="2023-01-01", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-a2", source_id=tribunal.id, title="t1b", radicado="05001233300020180047100",
        f_public="2023-02-01", storage_bucket="iurisync-test", storage_key="a2.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id, title="t2", radicado="05001233300020180047101",
        f_public="2024-05-01", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    repository._link_case_group(
        db_session, tribunal.id, "05001233300020180047100", consejo.id, "05001233300020180047101"
    )

    [summary] = repository.list_case_links_with_summary(db_session)

    assert summary["source_names"] == ["Consejo de Estado", "Tribunal Administrativo de Antioquia"]
    assert summary["stage_count"] == 2
    assert summary["document_count"] == 3
    assert str(summary["f_public_min"]) == "2023-01-01"
    assert str(summary["f_public_max"]) == "2024-05-01"
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv/Scripts/pytest tests/test_repository.py -k list_case_links_with_summary -v`
Expected: FAIL — la función no existe.

- [ ] **Step 3: Implementar**

En `core/db/repository.py`, agregar:

```python
def list_case_links_with_summary(db: Session) -> list[dict]:
    result: list[dict] = []
    case_links = db.scalars(select(CaseLink).order_by(CaseLink.created_at.desc())).all()
    for case_link in case_links:
        stages = list_case_link_stages(db, case_link.id)
        if not stages:
            continue
        source_ids = {s.source_id for s in stages}
        names = dict(db.execute(select(Source.id, Source.name).where(Source.id.in_(source_ids))).all())
        total_docs = 0
        f_mins: list = []
        f_maxs: list = []
        for stage in stages:
            summary = case_group_summary(db, stage.source_id, stage.radicado)
            total_docs += summary["document_count"]
            if summary["f_public_min"] is not None:
                f_mins.append(summary["f_public_min"])
            if summary["f_public_max"] is not None:
                f_maxs.append(summary["f_public_max"])
        result.append({
            "id": case_link.id,
            "source_names": sorted({names.get(sid, "Fuente eliminada") for sid in source_ids}),
            "radicados": sorted({s.radicado for s in stages}),
            "stage_count": len(stages),
            "document_count": total_docs,
            "f_public_min": min(f_mins) if f_mins else None,
            "f_public_max": max(f_maxs) if f_maxs else None,
        })
    return result
```

- [ ] **Step 4: Confirmar que pasa**

Run: `.venv/Scripts/pytest tests/test_repository.py -k list_case_links_with_summary -v`
Expected: PASSED

- [ ] **Step 5: Commit**

```bash
git add core/db/repository.py tests/test_repository.py
git commit -m "feat: listar expedientes con resumen (fuentes, documentos, fechas)"
```

---

### Task 5: El run y el backfill usan el armado automático

**Files:**
- Modify: `worker/tasks.py`
- Modify: `core/backfill_samai_radicado.py`
- Test: `tests/test_tasks.py`, `tests/test_backfill_samai_radicado.py`

**Interfaces:**
- Consumes: `assemble_case_links_for_run`, `assemble_case_links` (Task 2).

- [ ] **Step 1: Ajustar la prueba del run**

En `tests/test_tasks.py`, en los dos tests `test_finalize_run_triggers_case_link_suggestion_generation` y `test_finalize_run_still_completes_when_suggestion_generation_fails`, reemplazar el nombre `generate_case_link_suggestions_for_run` por `assemble_case_links_for_run` (en el `monkeypatch.setattr(...)` y en el cuerpo). La lógica de los tests no cambia.

- [ ] **Step 2: Ajustar la prueba del backfill**

En `tests/test_backfill_samai_radicado.py::test_backfill_populates_radicado_and_generates_suggestions`, la aserción `assert result["suggestions_created"] == 1` pasa a `assert result["case_links_assembled"] == 1`.

- [ ] **Step 3: Confirmar que fallan**

Run: `.venv/Scripts/pytest tests/test_tasks.py -k case_link -v` y `.venv/Scripts/pytest tests/test_backfill_samai_radicado.py -v`
Expected: FAIL — todavía se llama `generate_case_link_suggestions_for_run` / la clave del resultado es `suggestions_created`.

- [ ] **Step 4: Implementar**

En `worker/tasks.py`, dentro de `_finalize_run`, reemplazar la línea `repository.generate_case_link_suggestions_for_run(db, run_id)` por `repository.assemble_case_links_for_run(db, run_id)` (dentro del mismo `try/except` que ya existe; el mensaje del `logger.exception(...)` puede quedar igual o decir "armado de expedientes").

En `core/backfill_samai_radicado.py`, en `backfill(...)`, reemplazar:
```python
    suggestions_created = repository.generate_case_link_suggestions(db, all_groups)
    return {"documents_updated": documents_updated, "suggestions_created": suggestions_created}
```
por:
```python
    case_links_assembled = repository.assemble_case_links(db, all_groups)
    return {"documents_updated": documents_updated, "case_links_assembled": case_links_assembled}
```
Y en `main()`, la línea `print(f"Sugerencias nuevas: {result['suggestions_created']}")` pasa a `print(f"Cruces vinculados: {result['case_links_assembled']}")`.

- [ ] **Step 5: Confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_tasks.py -q` y `.venv/Scripts/pytest tests/test_backfill_samai_radicado.py -q`
Expected: PASSED (ambos archivos)

- [ ] **Step 6: Commit**

```bash
git add worker/tasks.py core/backfill_samai_radicado.py tests/test_tasks.py tests/test_backfill_samai_radicado.py
git commit -m "feat: el run y el backfill arman expedientes automáticamente"
```

---

### Task 6: Simplificar la nota de caso en el listado de documentos (backend)

**Files:**
- Modify: `core/db/repository.py`
- Modify: `api/routers/documents.py`
- Modify: `api/schemas.py`
- Test: `tests/test_repository.py`, `tests/test_api_documents.py`

**Interfaces:**
- Produces: `get_case_link_status_for_documents(db, document_ids) -> dict[int, dict]` con claves `case_link_id` (int) y `other_source_name` (str|None) — consumido por `api/routers/documents.py`. Se elimina el estado "pending".
- `DocumentOut` pasa a tener `case_link_id: Optional[int]` y `case_link_other_source_name: Optional[str]` (se quitan `case_link_status` y `case_link_suggestion_id`).

- [ ] **Step 1: Ajustar/escribir las pruebas**

En `tests/test_repository.py`, el test existente `test_get_case_link_status_for_documents_reports_pending_and_confirmed` se reemplaza por uno que solo cubre lo confirmado (ya no hay pendientes):

```python
def test_get_case_link_status_for_documents_reports_confirmed_expedientes(db_session):
    tribunal = _make_samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _make_samai_source(db_session, "Consejo de Estado")
    doc_trib = repository.insert_document(
        db_session, doc_id="doc-t", source_id=tribunal.id, title="tt",
        radicado="05001233300020180047100", storage_bucket="iurisync-test", storage_key="t.pdf",
    )
    doc_consejo = repository.insert_document(
        db_session, doc_id="doc-c", source_id=consejo.id, title="tc",
        radicado="05001233300020180047101", storage_bucket="iurisync-test", storage_key="c.pdf",
    )
    unrelated = repository.insert_document(
        db_session, doc_id="doc-u", source_id=tribunal.id, title="tu",
        radicado="11111111111111111111111", storage_bucket="iurisync-test", storage_key="u.pdf",
    )
    repository._link_case_group(
        db_session, tribunal.id, "05001233300020180047100", consejo.id, "05001233300020180047101"
    )

    status = repository.get_case_link_status_for_documents(db_session, [doc_trib.id, doc_consejo.id, unrelated.id])

    assert status[doc_trib.id]["other_source_name"] == "Consejo de Estado"
    assert status[doc_consejo.id]["other_source_name"] == "Tribunal Administrativo de Antioquia"
    assert isinstance(status[doc_trib.id]["case_link_id"], int)
    assert unrelated.id not in status
```

En `tests/test_api_documents.py`, el test `test_get_documents_includes_pending_case_link_note` se reemplaza por uno de expediente confirmado:

```python
def test_get_documents_includes_case_link_note(api_client, db_session, auth_header):
    repository.create_source_family_if_missing(db_session, key="samai", display_name="SAMAI")
    tribunal = repository.create_source(db_session, family_key="samai", name="Tribunal Administrativo de Antioquia", family_params={})
    consejo = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, title="t1",
        radicado="05001233300020180047100", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id, title="t2",
        radicado="05001233300020180047101", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    repository._link_case_group(
        db_session, tribunal.id, "05001233300020180047100", consejo.id, "05001233300020180047101"
    )

    response = api_client.get("/documents", headers=auth_header)

    by_source = {d["source_id"]: d for d in response.json()["items"]}
    assert by_source[tribunal.id]["case_link_id"] is not None
    assert by_source[tribunal.id]["case_link_other_source_name"] == "Consejo de Estado"
```

- [ ] **Step 2: Confirmar que fallan**

Run: `.venv/Scripts/pytest tests/test_repository.py -k get_case_link_status -v` y `.venv/Scripts/pytest tests/test_api_documents.py -k case_link -v`
Expected: FAIL.

- [ ] **Step 3: Implementar**

En `api/schemas.py`, dentro de `DocumentOut`, reemplazar las cuatro líneas de `case_link_*` por:
```python
    case_link_id: Optional[int] = None
    case_link_other_source_name: Optional[str] = None
```

En `core/db/repository.py`, reemplazar el cuerpo de `get_case_link_status_for_documents` por una versión que solo mira etapas confirmadas (sin la rama de sugerencias pendientes):

```python
def get_case_link_status_for_documents(db: Session, document_ids: list[int]) -> dict[int, dict]:
    """Para cada documento que pertenece a un expediente (su (source, radicado)
    es una etapa de un case_link), devuelve el id del expediente y el nombre de
    las OTRAS fuentes que participan. Usado por el listado de documentos."""
    if not document_ids:
        return {}
    docs = db.execute(
        select(Document.id, Document.source_id, Document.radicado).where(
            Document.id.in_(document_ids), Document.radicado.is_not(None)
        )
    ).all()
    if not docs:
        return {}
    pairs = {(d.source_id, d.radicado) for d in docs}
    stages = list(
        db.scalars(
            select(CaseLinkStage).where(tuple_(CaseLinkStage.source_id, CaseLinkStage.radicado).in_(pairs))
        ).all()
    )
    if not stages:
        return {}
    case_link_ids = {s.case_link_id for s in stages}
    all_stages = list(
        db.scalars(select(CaseLinkStage).where(CaseLinkStage.case_link_id.in_(case_link_ids))).all()
    )
    stages_by_link: dict[int, list[CaseLinkStage]] = {}
    for stage in all_stages:
        stages_by_link.setdefault(stage.case_link_id, []).append(stage)
    source_names = dict(
        db.execute(select(Source.id, Source.name).where(Source.id.in_({s.source_id for s in all_stages}))).all()
    )
    by_pair: dict[tuple[int, str], dict] = {}
    for stage in stages:
        others = [
            s for s in stages_by_link[stage.case_link_id]
            if (s.source_id, s.radicado) != (stage.source_id, stage.radicado)
        ]
        other_label = ", ".join(sorted({source_names.get(o.source_id, "otra fuente") for o in others})) or None
        by_pair[(stage.source_id, stage.radicado)] = {
            "case_link_id": stage.case_link_id,
            "other_source_name": other_label,
        }
    return {d.id: by_pair[(d.source_id, d.radicado)] for d in docs if (d.source_id, d.radicado) in by_pair}
```

En `api/routers/documents.py`, reemplazar los dos bloques que rellenan la nota (en `get_documents` y en `get_document`) por la versión de dos campos. En `get_documents`:
```python
    case_link_status = repository.get_case_link_status_for_documents(db, [d.id for d in items])
    for d in items:
        info = case_link_status.get(d.id)
        if info:
            d.case_link_id = info["case_link_id"]
            d.case_link_other_source_name = info["other_source_name"]
```
Y el bloque análogo en `get_document`:
```python
    info = repository.get_case_link_status_for_documents(db, [document.id]).get(document.id)
    if info:
        document.case_link_id = info["case_link_id"]
        document.case_link_other_source_name = info["other_source_name"]
```

- [ ] **Step 4: Confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_repository.py -k get_case_link_status -v` y `.venv/Scripts/pytest tests/test_api_documents.py -q`
Expected: PASSED

- [ ] **Step 5: Commit**

```bash
git add core/db/repository.py api/routers/documents.py api/schemas.py tests/test_repository.py tests/test_api_documents.py
git commit -m "feat: la nota de expediente en Documentos ya no tiene estado pendiente"
```

---

### Task 7: Endpoints de la API — listar expedientes y quitar etapa

**Files:**
- Modify: `api/schemas.py`
- Modify: `api/routers/case_links.py`
- Test: `tests/test_api_case_links.py`

**Interfaces:**
- Consumes: `repository.list_case_links_with_summary` (Task 4), `repository.separate_case_link_stage` (Task 3), `repository.get_case_link`, `repository.list_case_link_stages`.
- Produces: `GET /case-links`, `DELETE /case-links/{case_link_id}/stages/{stage_id}`, y `stage_id` en cada etapa de `GET /case-links/{id}`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `tests/test_api_case_links.py` (usa el helper `_samai_source` ya existente):

```python
def test_list_case_links_returns_assembled_expedientes(api_client, db_session, auth_header):
    tribunal = _samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _samai_source(db_session, "Consejo de Estado")
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, title="t1",
        radicado="05001233300020180047100", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id, title="t2",
        radicado="05001233300020180047101", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    repository._link_case_group(
        db_session, tribunal.id, "05001233300020180047100", consejo.id, "05001233300020180047101"
    )

    response = api_client.get("/case-links", headers=auth_header)

    assert response.status_code == 200
    [item] = response.json()
    assert item["stage_count"] == 2
    assert item["document_count"] == 2
    assert set(item["source_names"]) == {"Tribunal Administrativo de Antioquia", "Consejo de Estado"}


def test_get_case_link_includes_stage_ids(api_client, db_session, auth_header):
    tribunal = _samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _samai_source(db_session, "Consejo de Estado")
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, title="t1",
        radicado="05001233300020180047100", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id, title="t2",
        radicado="05001233300020180047101", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    case_link = repository._link_case_group(
        db_session, tribunal.id, "05001233300020180047100", consejo.id, "05001233300020180047101"
    )

    response = api_client.get(f"/case-links/{case_link.id}", headers=auth_header)

    stages = response.json()["stages"]
    assert all(isinstance(s["stage_id"], int) for s in stages)


def test_remove_stage_dissolves_two_stage_expediente(api_client, db_session, auth_header):
    tribunal = _samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _samai_source(db_session, "Consejo de Estado")
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, title="t1",
        radicado="05001233300020180047100", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id, title="t2",
        radicado="05001233300020180047101", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    case_link = repository._link_case_group(
        db_session, tribunal.id, "05001233300020180047100", consejo.id, "05001233300020180047101"
    )
    stage = repository.list_case_link_stages(db_session, case_link.id)[0]

    response = api_client.delete(f"/case-links/{case_link.id}/stages/{stage.id}", headers=auth_header)

    assert response.status_code == 200
    assert response.json()["dissolved"] is True
    assert api_client.get("/case-links", headers=auth_header).json() == []


def test_remove_stage_returns_404_when_stage_not_in_expediente(api_client, db_session, auth_header):
    tribunal = _samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _samai_source(db_session, "Consejo de Estado")
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, title="t1",
        radicado="05001233300020180047100", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id, title="t2",
        radicado="05001233300020180047101", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    case_link = repository._link_case_group(
        db_session, tribunal.id, "05001233300020180047100", consejo.id, "05001233300020180047101"
    )

    response = api_client.delete(f"/case-links/{case_link.id}/stages/999999", headers=auth_header)

    assert response.status_code == 404
```

- [ ] **Step 2: Confirmar que fallan**

Run: `.venv/Scripts/pytest tests/test_api_case_links.py -k "list_case_links or stage_ids or remove_stage" -v`
Expected: FAIL.

- [ ] **Step 3: Implementar**

En `api/schemas.py`:
- En `CaseLinkStageOut`, agregar `stage_id: int` como primer campo.
- Agregar al final:
```python
class CaseLinkListItemOut(BaseModel):
    id: int
    source_names: list[str]
    radicados: list[str]
    stage_count: int
    document_count: int
    f_public_min: Optional[date] = None
    f_public_max: Optional[date] = None
```

En `api/routers/case_links.py`:
- Agregar `CaseLinkListItemOut` al import de `api.schemas`.
- En `_case_link_out`, pasar `stage_id=stage.id` al construir cada `CaseLinkStageOut`.
- Agregar los endpoints:
```python
@router.get("/case-links", response_model=list[CaseLinkListItemOut])
def list_case_links(db: Session = Depends(get_db)):
    return [CaseLinkListItemOut(**item) for item in repository.list_case_links_with_summary(db)]


@router.delete("/case-links/{case_link_id}/stages/{stage_id}")
def remove_case_link_stage(case_link_id: int, stage_id: int, db: Session = Depends(get_db)):
    result = repository.separate_case_link_stage(db, case_link_id, stage_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Etapa no encontrada en este expediente")
    return result
```
(El endpoint `GET /case-links/{case_link_id}` existente se conserva.)

- [ ] **Step 4: Confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_api_case_links.py -k "list_case_links or stage_ids or remove_stage" -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add api/schemas.py api/routers/case_links.py tests/test_api_case_links.py
git commit -m "feat: endpoints para listar expedientes y quitar una etapa"
```

---

### Task 8: Eliminar la maquinaria de sugerencias y vinculación manual

**Files:**
- Modify: `api/routers/case_links.py`, `api/schemas.py`
- Modify: `core/db/repository.py`
- Modify: `core/db/models.py`
- Create: `alembic/versions/<generado>_drop_case_link_suggestions.py`
- Test: `tests/test_api_case_links.py`, `tests/test_repository.py`

**Interfaces:**
- Se eliminan: endpoints `GET /case-link-suggestions`, `POST .../confirm`, `POST .../dismiss`, `POST /case-links` (manual); funciones de repositorio `generate_case_link_suggestions`, `generate_case_link_suggestions_for_run`, `_create_case_link_suggestion_if_missing`, `list_pending_case_link_suggestions`, `get_case_link_suggestion`, `confirm_case_link_suggestion`, `dismiss_case_link_suggestion`, `create_manual_case_link`, `find_pending_case_link_suggestion_for_document`; schemas `CaseLinkSuggestionOut`, `ManualCaseLinkCreate`; modelo `CaseLinkSuggestion` y su tabla.

- [ ] **Step 1: Quitar las pruebas obsoletas**

En `tests/test_api_case_links.py`, eliminar los tests que ejercen sugerencias/manual: `test_list_pending_suggestions_returns_case_group_context`, `test_confirm_suggestion_returns_404_when_not_found`, `test_confirm_then_get_case_link_shows_both_stages`, `test_dismiss_suggestion_removes_it_from_the_pending_list`, `test_create_manual_case_link`, `test_create_manual_case_link_rejects_non_samai_source`, `test_create_manual_case_link_rejects_nonexistent_source`, `test_create_manual_case_link_rejects_linking_a_pair_to_itself`.

En `tests/test_repository.py`, eliminar los tests que ejercen sugerencias/confirmación/manual: los `test_generate_case_link_suggestions_*`, `test_confirm_case_link_suggestion_*`, `test_dismiss_case_link_suggestion_*`, `test_create_manual_case_link_*`, `test_find_confirmed_case_link_for_document_returns_none_when_not_linked` (si depende de funciones eliminadas, si no, se conserva). Conservar los tests de `_link_case_group` que se hacen vía `create_manual_case_link` **reescribiéndolos** para llamar directamente a `repository._link_case_group(...)`.

- [ ] **Step 2: Quitar el código de sugerencias/manual**

En `api/routers/case_links.py`: eliminar los endpoints `list_pending_case_link_suggestions`, `confirm_case_link_suggestion`, `dismiss_case_link_suggestion`, `create_manual_case_link`, la función `_case_group_out`, y los imports `CaseGroupOut`, `CaseLinkSuggestionOut`, `ManualCaseLinkCreate`.

En `api/schemas.py`: eliminar `CaseLinkSuggestionOut` y `ManualCaseLinkCreate`. Conservar `CaseGroupOut` solo si algo lo usa; si no, eliminarlo también.

En `core/db/repository.py`: eliminar las funciones listadas en "Interfaces" (todas las de sugerencias/confirmación/manual). Conservar `_samai_case_groups`, `_get_case_link_stage`, `_link_case_group`, `get_case_link`, `list_case_link_stages`, `list_documents_by_source_and_radicado`, `case_group_summary`, `find_confirmed_case_link_for_document` (si se usa), y todo lo de las Tasks 2-4-6. Quitar `CaseLinkSuggestion` del import de `core.db.models`.

- [ ] **Step 3: Migración que elimina la tabla**

Run: `PATH="$(pwd)/.venv/Scripts:$PATH" .venv/Scripts/alembic revision -m "drop case link suggestions"`

En el archivo generado:
```python
def upgrade() -> None:
    op.drop_table('case_link_suggestions')


def downgrade() -> None:
    op.create_table(
        'case_link_suggestions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_id_a', sa.Integer(), nullable=False),
        sa.Column('radicado_a', sa.String(), nullable=False),
        sa.Column('source_id_b', sa.Integer(), nullable=False),
        sa.Column('radicado_b', sa.String(), nullable=False),
        sa.Column('status', sa.String(), server_default='pending', nullable=False),
        sa.Column('matched_digits', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['source_id_a'], ['sources.id']),
        sa.ForeignKeyConstraint(['source_id_b'], ['sources.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_id_a', 'radicado_a', 'source_id_b', 'radicado_b', name='uq_case_link_suggestions_pair'),
    )
```

En `core/db/models.py`, eliminar la clase `CaseLinkSuggestion`.

- [ ] **Step 4: Confirmar que pasa todo lo afectado**

Recrear la base de pruebas limpia y correr (archivo por archivo):
```bash
docker exec scrapper-avanzado-postgres-1 psql -U iurisync -d postgres -c "DROP DATABASE IF EXISTS iurisync_test;" -c "CREATE DATABASE iurisync_test OWNER iurisync;"
```
Run: `PATH="$(pwd)/.venv/Scripts:$PATH" .venv/Scripts/pytest tests/test_migrations.py tests/test_api_case_links.py tests/test_repository.py -q` (uno por uno si hace falta)
Expected: PASSED, sin referencias colgadas a `CaseLinkSuggestion`.

- [ ] **Step 5: Commit**

```bash
git add api/routers/case_links.py api/schemas.py core/db/repository.py core/db/models.py alembic/versions/ tests/test_api_case_links.py tests/test_repository.py
git commit -m "refactor: elimina sugerencias pendientes y vinculación manual"
```

---

### Task 9: Cliente de API y tipos del frontend

**Files:**
- Modify: `frontend/src/api/caseLinks.ts`
- Modify: `frontend/src/api/types.ts`
- Test: `frontend/src/api/caseLinks.test.ts`

**Interfaces:**
- Produces: `fetchCaseLinks(): Promise<CaseLinkListItem[]>`, `separateCaseLinkStage(caseLinkId, stageId): Promise<{dissolved: boolean; case_link_id: number | null}>`, `fetchCaseLink(id)` (se conserva); tipos `CaseLinkListItem`, `CaseLinkStage` con `stage_id`, `Document` con `case_link_id`/`case_link_other_source_name`.

- [ ] **Step 1: Reescribir las pruebas del cliente**

Reemplazar el contenido de `frontend/src/api/caseLinks.test.ts` por:

```typescript
import { describe, expect, it, vi, beforeEach } from "vitest";
import * as client from "./client";
import { fetchCaseLinks, fetchCaseLink, separateCaseLinkStage } from "./caseLinks";

vi.mock("./client", async () => {
  const actual = await vi.importActual<typeof client>("./client");
  return { ...actual, apiFetch: vi.fn() };
});

describe("caseLinks api", () => {
  beforeEach(() => {
    vi.mocked(client.apiFetch).mockReset();
  });

  it("fetches the list of expedientes", async () => {
    vi.mocked(client.apiFetch).mockResolvedValue([]);
    await fetchCaseLinks();
    expect(client.apiFetch).toHaveBeenCalledWith("/case-links");
  });

  it("fetches a single expediente by id", async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({ id: 1, stages: [] });
    await fetchCaseLink(1);
    expect(client.apiFetch).toHaveBeenCalledWith("/case-links/1");
  });

  it("removes a stage from an expediente", async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({ dissolved: false, case_link_id: 1 });
    await separateCaseLinkStage(1, 7);
    expect(client.apiFetch).toHaveBeenCalledWith("/case-links/1/stages/7", { method: "DELETE" });
  });
});
```

- [ ] **Step 2: Confirmar que fallan**

Run: `cd frontend && npm test -- --run caseLinks`
Expected: FAIL.

- [ ] **Step 3: Implementar**

Reemplazar `frontend/src/api/caseLinks.ts` por:
```typescript
import { apiFetch } from "./client";
import type { CaseLink, CaseLinkListItem } from "./types";

export function fetchCaseLinks(): Promise<CaseLinkListItem[]> {
  return apiFetch<CaseLinkListItem[]>("/case-links");
}

export function fetchCaseLink(id: number): Promise<CaseLink> {
  return apiFetch<CaseLink>(`/case-links/${id}`);
}

export function separateCaseLinkStage(
  caseLinkId: number,
  stageId: number,
): Promise<{ dissolved: boolean; case_link_id: number | null }> {
  return apiFetch(`/case-links/${caseLinkId}/stages/${stageId}`, { method: "DELETE" });
}
```

En `frontend/src/api/types.ts`:
- En `Document`, reemplazar las cuatro líneas `case_link_*` por:
```typescript
  case_link_id?: number | null;
  case_link_other_source_name?: string | null;
```
- Eliminar `CaseLinkSuggestion` y `ManualCaseLinkInput`; eliminar `CaseGroup` si nada más lo usa.
- En `CaseLinkStage`, agregar `stage_id: number;` como primer campo.
- Agregar:
```typescript
export interface CaseLinkListItem {
  id: number;
  source_names: string[];
  radicados: string[];
  stage_count: number;
  document_count: number;
  f_public_min: string | null;
  f_public_max: string | null;
}
```

- [ ] **Step 4: Confirmar que pasan**

Run: `cd frontend && npm test -- --run caseLinks`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/caseLinks.ts frontend/src/api/types.ts frontend/src/api/caseLinks.test.ts
git commit -m "feat: cliente de API de expedientes (listar, ver, quitar etapa)"
```

---

### Task 10: Página "Expedientes" (listado)

**Files:**
- Create: `frontend/src/pages/ExpedientesPage.tsx`, `frontend/src/pages/ExpedientesPage.test.tsx`
- Delete: `frontend/src/pages/CaseLinksPage.tsx`, `frontend/src/pages/CaseLinksPage.test.tsx`

**Interfaces:**
- Consumes: `fetchCaseLinks` (Task 9). Enlaza cada expediente a `/expedientes/:caseLinkId`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `frontend/src/pages/ExpedientesPage.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { ExpedientesPage } from "./ExpedientesPage";
import * as caseLinksApi from "../api/caseLinks";

vi.mock("../api/caseLinks");

const ITEM = {
  id: 5,
  source_names: ["Consejo de Estado", "Tribunal Administrativo del Atlántico"],
  radicados: ["08001233300020260014600", "08001233300020260014601"],
  stage_count: 2,
  document_count: 3,
  f_public_min: "2026-07-16",
  f_public_max: "2026-07-31",
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ExpedientesPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ExpedientesPage", () => {
  beforeEach(() => {
    vi.mocked(caseLinksApi.fetchCaseLinks).mockResolvedValue([ITEM]);
  });

  it("lists expedientes with their sources and counts", async () => {
    renderPage();
    expect(await screen.findByText("Tribunal Administrativo del Atlántico", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Consejo de Estado", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/3 documentos/)).toBeInTheDocument();
  });

  it("links each expediente to its timeline", async () => {
    renderPage();
    const link = await screen.findByRole("link", { name: /ver expediente/i });
    expect(link).toHaveAttribute("href", "/expedientes/5");
  });

  it("shows an empty state when there are no expedientes", async () => {
    vi.mocked(caseLinksApi.fetchCaseLinks).mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText(/no hay expedientes/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Confirmar que fallan**

Run: `cd frontend && npm test -- --run ExpedientesPage`
Expected: FAIL — `Cannot find module './ExpedientesPage'`.

- [ ] **Step 3: Implementar**

Crear `frontend/src/pages/ExpedientesPage.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { GitMerge } from "lucide-react";
import { fetchCaseLinks } from "../api/caseLinks";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { formatDate } from "../lib/formatters";

export function ExpedientesPage() {
  const expedientesQuery = useQuery({
    queryKey: ["case-links"],
    queryFn: fetchCaseLinks,
  });

  return (
    <div className="space-y-6">
      <div>
        <p className="flex items-center gap-1.5 text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">
          <GitMerge className="size-3.5" aria-hidden="true" />
          Expedientes
        </p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">
          Procesos que cruzan tribunales
        </h1>
      </div>

      {expedientesQuery.isError && (
        <ErrorBanner message="No se pudieron cargar los expedientes." onRetry={() => expedientesQuery.refetch()} />
      )}

      {!expedientesQuery.isLoading && (expedientesQuery.data?.length ?? 0) === 0 && !expedientesQuery.isError && (
        <EmptyState message="No hay expedientes todavía." />
      )}

      <div className="space-y-3">
        {expedientesQuery.data?.map((expediente) => (
          <div key={expediente.id} className="flex items-center justify-between gap-4 rounded-lg border border-border bg-card p-4">
            <div>
              <p className="font-medium text-foreground">{expediente.source_names.join(" · ")}</p>
              <p className="text-xs text-muted-foreground">
                {expediente.stage_count} instancia{expediente.stage_count === 1 ? "" : "s"} ·{" "}
                {expediente.document_count} documento{expediente.document_count === 1 ? "" : "s"}
                {expediente.f_public_min &&
                  ` · ${formatDate(expediente.f_public_min)} – ${formatDate(expediente.f_public_max ?? expediente.f_public_min)}`}
              </p>
            </div>
            <Link
              to={`/expedientes/${expediente.id}`}
              className="shrink-0 text-sm font-medium text-primary underline-offset-2 hover:underline"
            >
              Ver expediente
            </Link>
          </div>
        ))}
      </div>
    </div>
  );
}
```

Eliminar `frontend/src/pages/CaseLinksPage.tsx` y `frontend/src/pages/CaseLinksPage.test.tsx`.

- [ ] **Step 4: Confirmar que pasan**

Run: `cd frontend && npm test -- --run ExpedientesPage`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ExpedientesPage.tsx frontend/src/pages/ExpedientesPage.test.tsx
git rm frontend/src/pages/CaseLinksPage.tsx frontend/src/pages/CaseLinksPage.test.tsx
git commit -m "feat: página Expedientes (listado) en lugar de la bandeja de confirmación"
```

---

### Task 11: Línea de tiempo — abrir documentos y quitar etapa

**Files:**
- Modify: `frontend/src/pages/CaseLinkDetailPage.tsx`
- Test: `frontend/src/pages/CaseLinkDetailPage.test.tsx`

**Interfaces:**
- Consumes: `fetchCaseLink`, `separateCaseLinkStage` (Task 9), `fetchDocumentBlob` + `downloadBlob` (`frontend/src/api/documents.ts`), `CaseLinkStage.stage_id`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Reemplazar `frontend/src/pages/CaseLinkDetailPage.test.tsx` por (mock de `../api/caseLinks` y `../api/documents`):

```typescript
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { CaseLinkDetailPage } from "./CaseLinkDetailPage";
import * as caseLinksApi from "../api/caseLinks";
import * as documentsApi from "../api/documents";

vi.mock("../api/caseLinks");
vi.mock("../api/documents");

const CASE_LINK = {
  id: 5,
  stages: [
    {
      stage_id: 11, source_id: 1, source_name: "Tribunal Administrativo del Atlántico",
      radicado: "08001233300020260014600", f_public_min: "2026-07-16", f_public_max: "2026-07-16",
      documents: [{ id: 10, title: "T_ATLA_08001_23_33_000_2026_00146_00", f_public: "2026-07-16", f_providencia: "2026-07-15" }],
    },
    {
      stage_id: 12, source_id: 2, source_name: "Consejo de Estado",
      radicado: "08001233300020260014601", f_public_min: "2026-07-31", f_public_max: "2026-07-31",
      documents: [{ id: 20, title: "08001-23-33-000-2026-00146-01(NE)", f_public: "2026-07-31", f_providencia: "2026-07-30" }],
    },
  ],
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/expedientes/5"]}>
        <Routes>
          <Route path="/expedientes/:caseLinkId" element={<CaseLinkDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("CaseLinkDetailPage", () => {
  beforeEach(() => {
    vi.mocked(caseLinksApi.fetchCaseLink).mockResolvedValue(CASE_LINK);
  });

  it("shows each stage's documents", async () => {
    renderPage();
    expect(await screen.findByText("T_ATLA_08001_23_33_000_2026_00146_00")).toBeInTheDocument();
    expect(screen.getByText("08001-23-33-000-2026-00146-01(NE)")).toBeInTheDocument();
  });

  it("opens a document when its button is clicked", async () => {
    vi.mocked(documentsApi.fetchDocumentBlob).mockResolvedValue(new Blob(["x"]));
    vi.mocked(documentsApi.downloadBlob).mockImplementation(() => {});
    renderPage();
    await screen.findByText("T_ATLA_08001_23_33_000_2026_00146_00");

    const [openButton] = screen.getAllByRole("button", { name: /abrir/i });
    await userEvent.click(openButton);

    await waitFor(() => expect(documentsApi.fetchDocumentBlob).toHaveBeenCalledWith(10));
  });

  it("removes a stage when 'Quitar del expediente' is clicked and confirmed", async () => {
    vi.mocked(caseLinksApi.separateCaseLinkStage).mockResolvedValue({ dissolved: false, case_link_id: 5 });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderPage();
    await screen.findByText("T_ATLA_08001_23_33_000_2026_00146_00");

    const [removeButton] = screen.getAllByRole("button", { name: /quitar del expediente/i });
    await userEvent.click(removeButton);

    await waitFor(() => expect(caseLinksApi.separateCaseLinkStage).toHaveBeenCalledWith(5, 11));
  });
});
```

- [ ] **Step 2: Confirmar que fallan**

Run: `cd frontend && npm test -- --run CaseLinkDetailPage`
Expected: FAIL.

- [ ] **Step 3: Implementar**

Reemplazar `frontend/src/pages/CaseLinkDetailPage.tsx` por:

```tsx
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { fetchCaseLink, separateCaseLinkStage } from "../api/caseLinks";
import { downloadBlob, fetchDocumentBlob } from "../api/documents";
import type { CaseLinkStage } from "../api/types";
import { Button } from "../components/ui/button";
import { ErrorBanner } from "../components/ErrorBanner";
import { formatDate } from "../lib/formatters";

function stageSortKey(stage: CaseLinkStage): string {
  return stage.f_public_min ?? "9999-99-99";
}

export function CaseLinkDetailPage() {
  const { caseLinkId } = useParams<{ caseLinkId: string }>();
  const id = Number(caseLinkId);
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);

  const caseLinkQuery = useQuery({
    queryKey: ["case-link", id],
    queryFn: () => fetchCaseLink(id),
    enabled: Number.isFinite(id),
  });

  const removeMutation = useMutation({
    mutationFn: (stageId: number) => separateCaseLinkStage(id, stageId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["case-link", id] });
      queryClient.invalidateQueries({ queryKey: ["case-links"] });
    },
    onError: () => setActionError("No se pudo quitar la etapa. Intenta de nuevo."),
  });

  async function openDocument(documentId: number, title: string) {
    try {
      const blob = await fetchDocumentBlob(documentId);
      downloadBlob(blob, title);
    } catch {
      setActionError("No se pudo abrir el documento.");
    }
  }

  const orderedStages = useMemo(
    () => [...(caseLinkQuery.data?.stages ?? [])].sort((a, b) => stageSortKey(a).localeCompare(stageSortKey(b))),
    [caseLinkQuery.data]
  );

  if (caseLinkQuery.isError) {
    return <ErrorBanner message="No se pudo cargar el expediente." onRetry={() => caseLinkQuery.refetch()} />;
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">Expediente</p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">
          Línea de tiempo del caso
        </h1>
      </div>

      {actionError && <ErrorBanner message={actionError} />}

      <ol className="space-y-4 border-l border-border pl-6">
        {orderedStages.map((stage) => (
          <li key={stage.stage_id} className="relative">
            <span className="absolute -left-[1.65rem] top-1 size-2.5 rounded-full bg-primary" aria-hidden="true" />
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-foreground">{stage.source_name}</h2>
                <p className="text-xs text-muted-foreground">
                  {stage.f_public_min && formatDate(stage.f_public_min)}
                  {stage.f_public_max && stage.f_public_max !== stage.f_public_min && ` – ${formatDate(stage.f_public_max)}`}
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  if (window.confirm("Esta instancia dejará de aparecer en el expediente y no se volverá a unir sola. ¿Continuar?")) {
                    removeMutation.mutate(stage.stage_id);
                  }
                }}
                disabled={removeMutation.isPending}
              >
                Quitar del expediente
              </Button>
            </div>
            <ul className="mt-2 space-y-1">
              {stage.documents.map((document) => (
                <li key={document.id} className="flex items-center gap-2 text-sm text-foreground">
                  <span>{document.title}</span>
                  <button
                    type="button"
                    onClick={() => openDocument(document.id, document.title)}
                    className="text-xs text-primary underline-offset-2 hover:underline"
                  >
                    Abrir
                  </button>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </div>
  );
}
```

- [ ] **Step 4: Confirmar que pasan**

Run: `cd frontend && npm test -- --run CaseLinkDetailPage`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/CaseLinkDetailPage.tsx frontend/src/pages/CaseLinkDetailPage.test.tsx
git commit -m "feat: la línea de tiempo abre documentos y permite quitar una etapa"
```

---

### Task 12: Rutas y menú

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Test: los tests existentes de `App`/`Sidebar` si enumeran rutas/enlaces (ajustarlos).

**Interfaces:**
- Consumes: `ExpedientesPage` (Task 10), `CaseLinkDetailPage` (Task 11).

- [ ] **Step 1: Ajustar rutas y menú**

En `frontend/src/App.tsx`:
- Reemplazar `import { CaseLinksPage } from "./pages/CaseLinksPage";` por `import { ExpedientesPage } from "./pages/ExpedientesPage";`.
- Reemplazar las dos rutas:
```tsx
                <Route path="/expedientes" element={<ExpedientesPage />} />
                <Route path="/expedientes/:caseLinkId" element={<CaseLinkDetailPage />} />
```

En `frontend/src/components/layout/Sidebar.tsx`, reemplazar la entrada del menú (el ícono `GitMerge` ya está importado y se sigue usando):
```typescript
  { to: "/expedientes", label: "Expedientes", end: false, icon: GitMerge },
```

- [ ] **Step 2: Confirmar el frontend completo**

Run: `cd frontend && npm test -- --run`
Expected: toda la suite PASSED (revisar en particular `Sidebar.test.tsx` y `App.test.tsx`; ajustar cualquier aserción que todavía mencione "Casos por confirmar" o `/casos-por-confirmar`).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/layout/Sidebar.tsx
git commit -m "feat: ruta /expedientes y entrada 'Expedientes' en el menú"
```

---

### Task 13: Nota de expediente en Documentos (frontend)

**Files:**
- Modify: `frontend/src/pages/DocumentsPage.tsx`
- Test: `frontend/src/pages/DocumentsPage.test.tsx`

**Interfaces:**
- Consumes: `Document.case_link_id`, `Document.case_link_other_source_name` (Task 9).

- [ ] **Step 1: Ajustar las pruebas**

En `frontend/src/pages/DocumentsPage.test.tsx`, reemplazar los tests de la nota. El de nota confirmada usa ahora `case_link_id` (sin `case_link_status`), enlaza a `/expedientes/:id`, y ya no existe el test de "pendiente":

```typescript
it("shows a case-link note with a link to the timeline", async () => {
  mockFilterEndpoints();
  server.use(
    http.get(`${BASE_URL}/documents`, () =>
      HttpResponse.json({
        items: [{ ...DOCUMENT, case_link_id: 5, case_link_other_source_name: "Consejo de Estado" }],
        total: 1,
        limit: 50,
        offset: 0,
      })
    )
  );

  renderPage();

  expect(await screen.findByText(/también aparece en: consejo de estado/i)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /ver línea de tiempo/i })).toHaveAttribute(
    "href",
    "/expedientes/5"
  );
});

it("shows no case-link note when the document has no case_link_id", async () => {
  mockFilterEndpoints();
  server.use(
    http.get(`${BASE_URL}/documents`, () =>
      HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 })
    )
  );

  renderPage();

  await screen.findByText("Sentencia C-001-26");
  expect(screen.queryByText(/también aparece en:/i)).not.toBeInTheDocument();
});
```
Eliminar el test `shows a pending case-link note without a timeline link`.

- [ ] **Step 2: Confirmar que fallan**

Run: `cd frontend && npm test -- --run DocumentsPage`
Expected: FAIL.

- [ ] **Step 3: Implementar**

En `frontend/src/pages/DocumentsPage.tsx`, reemplazar el componente `CaseLinkNote` por la versión de un solo estado:

```tsx
function CaseLinkNote({ document }: { document: Document }) {
  if (document.case_link_id) {
    return (
      <p className="mt-1 text-xs text-muted-foreground">
        También aparece en: {document.case_link_other_source_name} —{" "}
        <Link to={`/expedientes/${document.case_link_id}`} className="underline-offset-2 hover:underline">
          Ver línea de tiempo
        </Link>
      </p>
    );
  }
  return null;
}
```

- [ ] **Step 4: Confirmar que pasan**

Run: `cd frontend && npm test -- --run DocumentsPage`
Expected: PASSED

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/DocumentsPage.tsx frontend/src/pages/DocumentsPage.test.tsx
git commit -m "feat: nota de expediente en Documentos apunta a /expedientes"
```

---

### Task 14: Migración de datos y verificación final

**Files:** ninguno (paso operativo).

- [ ] **Step 1: Aplicar migraciones y armar expedientes sobre los datos existentes (base de desarrollo)**

```bash
PATH="$(pwd)/.venv/Scripts:$PATH" .venv/Scripts/alembic upgrade head
.venv/Scripts/python -m core.backfill_samai_radicado
```
Expected: el backfill imprime "Documentos actualizados: 0" (ya estaban poblados) y "Cruces vinculados: N". La tabla `case_link_suggestions` ya no existe.

- [ ] **Step 2: Verificar en la base**

```bash
docker exec scrapper-avanzado-postgres-1 psql -U iurisync -d iurisync -c "SELECT count(*) AS expedientes FROM case_links; SELECT count(*) AS etapas FROM case_link_stages; SELECT count(*) AS separaciones FROM case_link_separations;"
```
Expected: ~30 expedientes, sus etapas, 0 separaciones.

- [ ] **Step 3: Suite completa (archivo por archivo en backend)**

Recrear la base de pruebas limpia y correr backend por archivos y el frontend completo:
```bash
docker exec scrapper-avanzado-postgres-1 psql -U iurisync -d postgres -c "DROP DATABASE IF EXISTS iurisync_test;" -c "CREATE DATABASE iurisync_test OWNER iurisync;"
```
Run: `PATH="$(pwd)/.venv/Scripts:$PATH" .venv/Scripts/pytest tests/test_repository.py tests/test_api_case_links.py tests/test_api_documents.py tests/test_tasks.py tests/test_backfill_samai_radicado.py tests/test_migrations.py -q` (uno por uno si se cuelga)
Run: `cd frontend && npm test -- --run`
Expected: todo PASSED.

- [ ] **Step 4: Prueba a mano en la app** (skill `run-iurisync`)

Levantar backend + frontend desde el worktree, entrar a **Expedientes**, abrir un expediente, **abrir** un documento y **quitar** una etapa (verificar que el expediente se disuelve si queda una sola fuente y que no reaparece al re-armar).

---

## Después de implementar

1. Antes de pedir revisión, correr toda la suite una vez más (backend por archivos, frontend completo).
2. En producción, tras el despliegue, correr una vez `alembic upgrade head` y `python -m core.backfill_samai_radicado` para armar los expedientes sobre los datos reales (igual que se hizo con el backfill de radicados).
