# Reporte mensual de extracción Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un PDF mensual, descargable desde una página nueva "Reportes", con el detalle de todo lo que el sistema extrajo ese mes (resumen, por fuente, errores, comparación con el mes anterior) — generado automáticamente el día 1 de cada mes o bajo demanda para cualquier mes ya cerrado.

**Architecture:** Tabla nueva `monthly_reports` (mismo patrón que `bulk_downloads`). Las corridas (`runs`/`run_sources`/`run_errors`) del mes, filtradas por `Run.started_at`, son la única fuente de verdad de la actividad del mes; `core/reporting.py` las agrega en un diccionario, `core/reporting_pdf.py` lo convierte a PDF con `reportlab`, una tarea de Celery lo sube a MinIO y actualiza el estado de la fila, y un endpoint REST (espejo de `/bulk-downloads`) lo expone al frontend.

**Tech Stack:** FastAPI, SQLAlchemy + Alembic, Celery + `beat_schedule`, `reportlab` (nueva dependencia), React + TanStack Query, MinIO (boto3).

**Spec:** `docs/superpowers/specs/2026-09-17-reporte-mensual-design.md`

## Global Constraints

- La actividad de un mes se mide SIEMPRE por `Run.started_at` en `[período, período+1 mes)` — nunca por `documents.downloaded_at` — excepto el uso de almacenamiento del resumen, que es la única métrica basada en `documents.downloaded_at` (documentado como tal).
- `period` es siempre el día 1 del mes (`date(año, mes, 1)`); no hay restricción de unicidad — cada generación inserta una fila nueva.
- Solo se listan como "sin actividad" las fuentes con `sources.active == true`.
- Los mensajes de error se truncan a 300 caracteres en el PDF.
- No se puede generar el reporte de un mes que no ha terminado (mes actual o futuro) — regla aplicada tanto en el backend como en el frontend.
- Clave de almacenamiento del PDF: `reportes/{period:%Y-%m}_{report_id}.pdf`.
- `reportlab` es la librería de generación de PDF (pura Python, sin dependencias del sistema).

---

## Task 1: Modelo, migración y CRUD básico de `monthly_reports`

**Files:**
- Modify: `core/db/models.py` (agregar clase `MonthlyReport`)
- Modify: `core/db/repository.py:10` (import), y agregar CRUD al final del bloque de `bulk_downloads` (después de `delete_bulk_download`, antes de `def list_useful_documents`)
- Create: `alembic/versions/<hash>_add_monthly_reports.py` (generado por `alembic revision`)
- Test: `tests/test_repository.py`

**Interfaces:**
- Produces: `MonthlyReport` (modelo SQLAlchemy, tabla `monthly_reports`); `repository.create_monthly_report(db, period: date, triggered_by: str) -> MonthlyReport`; `repository.get_monthly_report(db, monthly_report_id: int) -> Optional[MonthlyReport]`; `repository.list_monthly_reports(db, limit: int = 50, offset: int = 0) -> list[MonthlyReport]`; `repository.set_monthly_report_status(db, monthly_report_id: int, status: str, **fields) -> None`.

- [ ] **Step 1: Escribir la prueba que falla**

Agregar a `tests/test_repository.py`, justo después de `test_bulk_download_lifecycle`:

```python
def test_monthly_report_lifecycle(db_session):
    from datetime import date, datetime, timezone

    report = repository.create_monthly_report(db_session, period=date(2026, 8, 1), triggered_by="manual")
    assert report.status == "pending"
    assert report.period == date(2026, 8, 1)
    assert report.triggered_by == "manual"

    repository.set_monthly_report_status(
        db_session, report.id, "running", started_at=datetime.now(timezone.utc)
    )
    refreshed = repository.get_monthly_report(db_session, report.id)
    assert refreshed.status == "running"
    assert refreshed.started_at is not None

    repository.set_monthly_report_status(
        db_session,
        report.id,
        "completed",
        storage_bucket="iurisync-test",
        storage_key="reportes/2026-08_1.pdf",
        finished_at=datetime.now(timezone.utc),
    )
    refreshed = repository.get_monthly_report(db_session, report.id)
    assert refreshed.status == "completed"
    assert refreshed.storage_key == "reportes/2026-08_1.pdf"


def test_list_monthly_reports_orders_by_most_recent_first(db_session):
    from datetime import date

    first = repository.create_monthly_report(db_session, period=date(2026, 7, 1), triggered_by="scheduled")
    second = repository.create_monthly_report(db_session, period=date(2026, 8, 1), triggered_by="manual")

    reports = repository.list_monthly_reports(db_session)

    assert [r.id for r in reports] == [second.id, first.id]
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv/Scripts/pytest tests/test_repository.py -k monthly_report -v`
Expected: FAIL — `AttributeError: module 'core.db.repository' has no attribute 'create_monthly_report'`

- [ ] **Step 3: Agregar el modelo**

En `core/db/models.py`, después de la clase `BulkDownload` (antes de `class Document(Base):`):

```python
class MonthlyReport(Base):
    __tablename__ = "monthly_reports"

    id = Column(Integer, primary_key=True)
    period = Column(Date, nullable=False)  # primer día del mes que cubre
    status = Column(String, nullable=False, default="pending")  # pending | running | completed | failed
    triggered_by = Column(String, nullable=False)  # 'manual' | 'scheduled'
    storage_bucket = Column(String, nullable=True)  # solo si status == completed
    storage_key = Column(Text, nullable=True)  # solo si status == completed
    error_message = Column(Text, nullable=True)  # solo si status == failed
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
```

- [ ] **Step 4: Agregar el CRUD al repositorio**

En `core/db/repository.py:10`, cambiar:

```python
from core.db.models import BulkDownload, CaseLink, CaseLinkSeparation, CaseLinkStage, Document, DocumentVersion, Run, RunError, RunSource, Source, SourceFamily, User, UserSession
```

por:

```python
from core.db.models import BulkDownload, CaseLink, CaseLinkSeparation, CaseLinkStage, Document, DocumentVersion, MonthlyReport, Run, RunError, RunSource, Source, SourceFamily, User, UserSession
```

Justo después de `delete_bulk_download` (y antes de `def list_useful_documents`), agregar:

```python
def create_monthly_report(db: Session, period: date, triggered_by: str) -> MonthlyReport:
    monthly_report = MonthlyReport(period=period, status="pending", triggered_by=triggered_by)
    db.add(monthly_report)
    db.commit()
    db.refresh(monthly_report)
    return monthly_report


def get_monthly_report(db: Session, monthly_report_id: int) -> Optional[MonthlyReport]:
    return db.get(MonthlyReport, monthly_report_id)


def list_monthly_reports(db: Session, limit: int = 50, offset: int = 0) -> list[MonthlyReport]:
    stmt = (
        select(MonthlyReport)
        .order_by(MonthlyReport.created_at.desc(), MonthlyReport.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt).all())


def set_monthly_report_status(db: Session, monthly_report_id: int, status: str, **fields) -> None:
    monthly_report = db.get(MonthlyReport, monthly_report_id)
    if monthly_report is None:
        return
    monthly_report.status = status
    for key, value in fields.items():
        setattr(monthly_report, key, value)
    db.commit()
```

- [ ] **Step 5: Confirmar que las pruebas pasan**

Run: `.venv/Scripts/pytest tests/test_repository.py -k monthly_report -v`
Expected: PASS (2 pruebas)

- [ ] **Step 6: Generar y completar la migración de Alembic**

Run: `.venv/Scripts/python -m alembic revision -m "add monthly reports"`

Esto crea `alembic/versions/<hash>_add_monthly_reports.py` con `down_revision` ya apuntado al head actual (`7509921b8e2b`) automáticamente. Reemplazar el cuerpo del archivo generado (dejando intactos `revision`, `down_revision`, `branch_labels`, `depends_on` tal como los escribió Alembic) por:

```python
def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'monthly_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('period', sa.Date(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('triggered_by', sa.String(), nullable=False),
        sa.Column('storage_bucket', sa.String(), nullable=True),
        sa.Column('storage_key', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('monthly_reports')
```

Run: `.venv/Scripts/python -m alembic upgrade head`
Expected: aplica sin error; `.venv/Scripts/python -m alembic current` muestra el nuevo hash como head.

- [ ] **Step 7: Commit**

```bash
git add core/db/models.py core/db/repository.py alembic/versions/*_add_monthly_reports.py tests/test_repository.py
git commit -m "feat: agregar tabla monthly_reports y su CRUD básico"
```

---

## Task 2: Consultas de agregación por período

**Files:**
- Modify: `core/db/repository.py` (agregar funciones al final del archivo)
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: modelos `Run`, `RunSource`, `RunError`, `Document`, `Source` (ya importados en `core/db/repository.py`).
- Produces: `repository.summarize_run_sources_for_period(db, period_start: datetime, period_end: datetime) -> list[dict]` (cada dict: `source_id`, `source_name`, `docs_new`, `docs_updated`, `docs_errors`, `had_failure`); `repository.list_active_sources_without_activity_in_period(db, period_start, period_end) -> list[str]`; `repository.list_run_errors_for_period(db, period_start, period_end) -> list[dict]` (cada dict: `source_name`, `message`, `occurred_at`); `repository.count_runs_by_status_for_period(db, period_start, period_end) -> dict[str, int]`; `repository.sum_document_storage_for_period(db, period_start, period_end) -> int`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `tests/test_repository.py` (al final del archivo):

```python
def _fuente_con_corrida(db_session, source_name, started_at, docs_new=0, docs_updated=0, docs_errors=0, run_status="completed", active=True):
    from core.db import repository as repo

    family_key = source_name.lower().replace(" ", "-")
    repo.create_source_family(db_session, key=family_key, display_name=source_name)
    source = repo.create_source(db_session, family_key=family_key, name=source_name, family_params={})
    if not active:
        repo.update_source(db_session, source.id, active=False)
    run = repo.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    repo.set_run_status(db_session, run.id, run_status, started_at=started_at)
    run_source = repo.create_run_source(db_session, run_id=run.id, source_id=source.id)
    repo.set_run_source_status(
        db_session, run_source.id, run_status, docs_new=docs_new, docs_updated=docs_updated, docs_errors=docs_errors
    )
    return source, run, run_source


def test_summarize_run_sources_for_period_sums_only_runs_started_within_range(db_session):
    from datetime import datetime, timezone

    dentro = datetime(2026, 8, 15, tzinfo=timezone.utc)
    fuera = datetime(2026, 7, 31, tzinfo=timezone.utc)
    _fuente_con_corrida(db_session, "Corte Constitucional", dentro, docs_new=5, docs_updated=2, docs_errors=1)
    _fuente_con_corrida(db_session, "CSJ", fuera, docs_new=99)

    period_start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    period_end = datetime(2026, 9, 1, tzinfo=timezone.utc)
    rows = repository.summarize_run_sources_for_period(db_session, period_start, period_end)

    assert len(rows) == 1
    assert rows[0]["source_name"] == "Corte Constitucional"
    assert rows[0]["docs_new"] == 5
    assert rows[0]["docs_updated"] == 2
    assert rows[0]["docs_errors"] == 1
    assert rows[0]["had_failure"] is False


def test_summarize_run_sources_for_period_sums_across_multiple_runs_of_the_same_source(db_session):
    from datetime import datetime, timezone

    family_key = "constitucional"
    repository.create_source_family(db_session, key=family_key, display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key=family_key, name="Corte Constitucional", family_params={})
    for started_at, docs_new in [(datetime(2026, 8, 5, tzinfo=timezone.utc), 3), (datetime(2026, 8, 20, tzinfo=timezone.utc), 4)]:
        run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
        repository.set_run_status(db_session, run.id, "completed", started_at=started_at)
        run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)
        repository.set_run_source_status(db_session, run_source.id, "completed", docs_new=docs_new)

    period_start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    period_end = datetime(2026, 9, 1, tzinfo=timezone.utc)
    rows = repository.summarize_run_sources_for_period(db_session, period_start, period_end)

    assert rows[0]["docs_new"] == 7


def test_summarize_run_sources_for_period_flags_had_failure(db_session):
    from datetime import datetime, timezone

    dentro = datetime(2026, 8, 15, tzinfo=timezone.utc)
    _fuente_con_corrida(db_session, "Minjusticia", dentro, docs_errors=3, run_status="failed")

    period_start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    period_end = datetime(2026, 9, 1, tzinfo=timezone.utc)
    rows = repository.summarize_run_sources_for_period(db_session, period_start, period_end)

    assert rows[0]["had_failure"] is True


def test_list_active_sources_without_activity_in_period_excludes_ones_with_runs_and_inactive_ones(db_session):
    from datetime import datetime, timezone

    dentro = datetime(2026, 8, 15, tzinfo=timezone.utc)
    _fuente_con_corrida(db_session, "Corte Constitucional", dentro, docs_new=1)  # tuvo actividad
    repository.create_source_family(db_session, key="minhacienda", display_name="Minhacienda")
    repository.create_source(db_session, family_key="minhacienda", name="Minhacienda", family_params={})  # activa, sin corridas
    inactiva = repository.create_source_family(db_session, key="mintransporte", display_name="MinTransporte")
    fuente_inactiva = repository.create_source(db_session, family_key="mintransporte", name="MinTransporte", family_params={})
    repository.update_source(db_session, fuente_inactiva.id, active=False)

    period_start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    period_end = datetime(2026, 9, 1, tzinfo=timezone.utc)
    nombres = repository.list_active_sources_without_activity_in_period(db_session, period_start, period_end)

    assert nombres == ["Minhacienda"]


def test_list_run_errors_for_period_filters_by_run_started_at(db_session):
    from datetime import datetime, timezone

    _, _, run_source_dentro = _fuente_con_corrida(db_session, "Corte Constitucional", datetime(2026, 8, 10, tzinfo=timezone.utc))
    repository.add_run_error(db_session, run_source_dentro.id, "Timeout al descargar")
    _, _, run_source_fuera = _fuente_con_corrida(db_session, "CSJ", datetime(2026, 7, 10, tzinfo=timezone.utc))
    repository.add_run_error(db_session, run_source_fuera.id, "Error de julio, no debe salir")

    period_start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    period_end = datetime(2026, 9, 1, tzinfo=timezone.utc)
    errores = repository.list_run_errors_for_period(db_session, period_start, period_end)

    assert len(errores) == 1
    assert errores[0]["source_name"] == "Corte Constitucional"
    assert errores[0]["message"] == "Timeout al descargar"


def test_count_runs_by_status_for_period(db_session):
    from datetime import datetime, timezone

    repository.create_source_family(db_session, key="jep", display_name="JEP")
    source = repository.create_source(db_session, family_key="jep", name="JEP", family_params={})
    for status in ["completed", "completed", "failed"]:
        run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
        repository.set_run_status(db_session, run.id, status, started_at=datetime(2026, 8, 5, tzinfo=timezone.utc))

    period_start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    period_end = datetime(2026, 9, 1, tzinfo=timezone.utc)
    counts = repository.count_runs_by_status_for_period(db_session, period_start, period_end)

    assert counts == {"completed": 2, "failed": 1}


def test_sum_document_storage_for_period_only_counts_documents_downloaded_within_range(db_session):
    from datetime import date, datetime, timezone

    repository.create_source_family(db_session, key="jep", display_name="JEP")
    source = repository.create_source(db_session, family_key="jep", name="JEP", family_params={})
    repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="Doc 1",
        storage_bucket="iurisync-test", storage_key="d1.pdf", file_size_bytes=1000,
        downloaded_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )
    repository.insert_document(
        db_session, doc_id="d2", source_id=source.id, title="Doc 2",
        storage_bucket="iurisync-test", storage_key="d2.pdf", file_size_bytes=500,
        downloaded_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
    )

    period_start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    period_end = datetime(2026, 9, 1, tzinfo=timezone.utc)
    total = repository.sum_document_storage_for_period(db_session, period_start, period_end)

    assert total == 1000
```

- [ ] **Step 2: Confirmar que fallan**

Run: `.venv/Scripts/pytest tests/test_repository.py -k "summarize_run_sources or without_activity or run_errors_for_period or runs_by_status or document_storage_for_period" -v`
Expected: FAIL — `AttributeError` (las funciones no existen todavía)

- [ ] **Step 3: Implementar las funciones**

Al final de `core/db/repository.py`:

```python
def summarize_run_sources_for_period(db: Session, period_start: datetime, period_end: datetime) -> list[dict]:
    stmt = (
        select(
            Source.id,
            Source.name,
            func.coalesce(func.sum(RunSource.docs_new), 0),
            func.coalesce(func.sum(RunSource.docs_updated), 0),
            func.coalesce(func.sum(RunSource.docs_errors), 0),
            func.bool_or(RunSource.status == "failed"),
        )
        .select_from(RunSource)
        .join(Run, RunSource.run_id == Run.id)
        .join(Source, RunSource.source_id == Source.id)
        .where(Run.started_at >= period_start, Run.started_at < period_end)
        .group_by(Source.id, Source.name)
        .order_by(Source.name)
    )
    return [
        {
            "source_id": source_id,
            "source_name": source_name,
            "docs_new": docs_new,
            "docs_updated": docs_updated,
            "docs_errors": docs_errors,
            "had_failure": had_failure,
        }
        for source_id, source_name, docs_new, docs_updated, docs_errors, had_failure in db.execute(stmt).all()
    ]


def list_active_sources_without_activity_in_period(db: Session, period_start: datetime, period_end: datetime) -> list[str]:
    active_subq = (
        select(RunSource.source_id)
        .join(Run, RunSource.run_id == Run.id)
        .where(Run.started_at >= period_start, Run.started_at < period_end)
    )
    stmt = (
        select(Source.name)
        .where(Source.active.is_(True), Source.id.not_in(active_subq))
        .order_by(Source.name)
    )
    return list(db.scalars(stmt).all())


def list_run_errors_for_period(db: Session, period_start: datetime, period_end: datetime) -> list[dict]:
    stmt = (
        select(RunError, Source.name)
        .join(RunSource, RunError.run_source_id == RunSource.id)
        .join(Run, RunSource.run_id == Run.id)
        .join(Source, RunSource.source_id == Source.id)
        .where(Run.started_at >= period_start, Run.started_at < period_end)
        .order_by(RunError.occurred_at)
    )
    return [
        {"source_name": source_name, "message": error.message, "occurred_at": error.occurred_at}
        for error, source_name in db.execute(stmt).all()
    ]


def count_runs_by_status_for_period(db: Session, period_start: datetime, period_end: datetime) -> dict[str, int]:
    stmt = (
        select(Run.status, func.count(Run.id))
        .where(Run.started_at >= period_start, Run.started_at < period_end)
        .group_by(Run.status)
    )
    return dict(db.execute(stmt).all())


def sum_document_storage_for_period(db: Session, period_start: datetime, period_end: datetime) -> int:
    stmt = select(func.coalesce(func.sum(Document.file_size_bytes), 0)).where(
        Document.downloaded_at >= period_start, Document.downloaded_at < period_end
    )
    return db.scalar(stmt) or 0
```

- [ ] **Step 4: Confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_repository.py -k "summarize_run_sources or without_activity or run_errors_for_period or runs_by_status or document_storage_for_period" -v`
Expected: PASS (7 pruebas)

- [ ] **Step 5: Commit**

```bash
git add core/db/repository.py tests/test_repository.py
git commit -m "feat: agregar consultas de agregación por período para el reporte mensual"
```

---

## Task 3: Agregación del reporte (`core/reporting.py`)

**Files:**
- Create: `core/reporting.py`
- Test: `tests/test_reporting.py`

**Interfaces:**
- Consumes: `repository.summarize_run_sources_for_period`, `repository.list_active_sources_without_activity_in_period`, `repository.list_run_errors_for_period`, `repository.count_runs_by_status_for_period`, `repository.sum_document_storage_for_period` (Task 2).
- Produces: `build_monthly_report_data(db: Session, period: date) -> dict` con claves `period` (date), `period_label` (str, ej. `"Agosto 2026"`), `resumen` (dict: `docs_new`, `docs_updated`, `docs_errors`, `runs_by_status` (dict), `storage_bytes`), `por_fuente` (list[dict], mismo shape que `summarize_run_sources_for_period`), `fuentes_sin_actividad` (list[str]), `errores` (list[dict]: `source_name`, `message` truncado a 300, `occurred_at`), `comparacion` (list[dict]: `source_name`, `docs_new_actual`, `docs_new_anterior`, `variacion_pct` (float o `None`)). También `previous_period(period: date) -> date` y `period_label(period: date) -> str`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Create `tests/test_reporting.py`:

```python
from datetime import date, datetime, timezone

from core.db import repository
from core.reporting import build_monthly_report_data, period_label, previous_period


def test_previous_period_handles_year_rollover():
    assert previous_period(date(2026, 1, 1)) == date(2025, 12, 1)
    assert previous_period(date(2026, 8, 1)) == date(2026, 7, 1)


def test_period_label_is_in_spanish():
    assert period_label(date(2026, 8, 1)) == "Agosto 2026"
    assert period_label(date(2026, 1, 1)) == "Enero 2026"


def _fuente_con_corrida(db_session, source_name, started_at, docs_new=0, docs_updated=0, docs_errors=0, run_status="completed"):
    family_key = source_name.lower().replace(" ", "-")
    repository.create_source_family(db_session, key=family_key, display_name=source_name)
    source = repository.create_source(db_session, family_key=family_key, name=source_name, family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    repository.set_run_status(db_session, run.id, run_status, started_at=started_at)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)
    repository.set_run_source_status(
        db_session, run_source.id, run_status, docs_new=docs_new, docs_updated=docs_updated, docs_errors=docs_errors
    )
    return source


def test_build_monthly_report_data_for_an_empty_month_is_all_zeros(db_session):
    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert data["period_label"] == "Agosto 2026"
    assert data["resumen"]["docs_new"] == 0
    assert data["resumen"]["docs_updated"] == 0
    assert data["resumen"]["docs_errors"] == 0
    assert data["resumen"]["runs_by_status"] == {}
    assert data["resumen"]["storage_bytes"] == 0
    assert data["por_fuente"] == []
    assert data["errores"] == []
    assert data["comparacion"] == []


def test_build_monthly_report_data_totals_the_summary_from_per_source_rows(db_session):
    _fuente_con_corrida(db_session, "Corte Constitucional", datetime(2026, 8, 10, tzinfo=timezone.utc), docs_new=5, docs_updated=1, docs_errors=2)
    _fuente_con_corrida(db_session, "CSJ", datetime(2026, 8, 12, tzinfo=timezone.utc), docs_new=3)

    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert data["resumen"]["docs_new"] == 8
    assert data["resumen"]["docs_updated"] == 1
    assert data["resumen"]["docs_errors"] == 2
    assert len(data["por_fuente"]) == 2


def test_build_monthly_report_data_truncates_error_messages_to_300_chars(db_session):
    source = _fuente_con_corrida(db_session, "Corte Constitucional", datetime(2026, 8, 10, tzinfo=timezone.utc))
    run_source = repository.list_run_sources_with_source_names(
        db_session, repository.list_runs(db_session)[0].id
    )[0]
    repository.add_run_error(db_session, run_source.id, "x" * 400)

    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert len(data["errores"][0]["message"]) == 301  # 300 + "…"
    assert data["errores"][0]["message"].endswith("…")


def test_build_monthly_report_data_comparison_marks_new_activity_when_previous_month_was_zero(db_session):
    _fuente_con_corrida(db_session, "Corte Constitucional", datetime(2026, 8, 10, tzinfo=timezone.utc), docs_new=5)

    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert data["comparacion"] == [
        {"source_name": "Corte Constitucional", "docs_new_actual": 5, "docs_new_anterior": 0, "variacion_pct": None}
    ]


def test_build_monthly_report_data_comparison_computes_percentage_change(db_session):
    family_key = "constitucional"
    repository.create_source_family(db_session, key=family_key, display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key=family_key, name="Corte Constitucional", family_params={})

    run_julio = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    repository.set_run_status(db_session, run_julio.id, "completed", started_at=datetime(2026, 7, 10, tzinfo=timezone.utc))
    run_source_julio = repository.create_run_source(db_session, run_id=run_julio.id, source_id=source.id)
    repository.set_run_source_status(db_session, run_source_julio.id, "completed", docs_new=10)

    run_agosto = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    repository.set_run_status(db_session, run_agosto.id, "completed", started_at=datetime(2026, 8, 10, tzinfo=timezone.utc))
    run_source_agosto = repository.create_run_source(db_session, run_id=run_agosto.id, source_id=source.id)
    repository.set_run_source_status(db_session, run_source_agosto.id, "completed", docs_new=15)

    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert data["comparacion"] == [
        {"source_name": "Corte Constitucional", "docs_new_actual": 15, "docs_new_anterior": 10, "variacion_pct": 50.0}
    ]


def test_build_monthly_report_data_comparison_skips_sources_with_zero_in_both_months(db_session):
    # Fuente activa pero sin ninguna corrida ni este mes ni el anterior: no debe
    # aparecer en la comparación (solo en fuentes_sin_actividad).
    repository.create_source_family(db_session, key="minhacienda", display_name="Minhacienda")
    repository.create_source(db_session, family_key="minhacienda", name="Minhacienda", family_params={})

    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert data["comparacion"] == []
    assert data["fuentes_sin_actividad"] == ["Minhacienda"]
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv/Scripts/pytest tests/test_reporting.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.reporting'`

- [ ] **Step 3: Implementar `core/reporting.py`**

```python
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from core.db import repository

_MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

_MENSAJE_MAX_LEN = 300


def _bounds(period: date) -> tuple[datetime, datetime]:
    start = datetime(period.year, period.month, 1, tzinfo=timezone.utc)
    if period.month == 12:
        end = datetime(period.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(period.year, period.month + 1, 1, tzinfo=timezone.utc)
    return start, end


def previous_period(period: date) -> date:
    if period.month == 1:
        return date(period.year - 1, 12, 1)
    return date(period.year, period.month - 1, 1)


def period_label(period: date) -> str:
    return f"{_MESES_ES[period.month].capitalize()} {period.year}"


def _variacion_pct(actual: int, anterior: int) -> Optional[float]:
    if anterior == 0:
        return None
    return round((actual - anterior) / anterior * 100, 1)


def build_monthly_report_data(db: Session, period: date) -> dict:
    period_start, period_end = _bounds(period)
    prev_start, prev_end = _bounds(previous_period(period))

    por_fuente = repository.summarize_run_sources_for_period(db, period_start, period_end)
    por_fuente_anterior = repository.summarize_run_sources_for_period(db, prev_start, prev_end)
    docs_new_anterior_by_source = {row["source_id"]: row["docs_new"] for row in por_fuente_anterior}

    comparacion = []
    for row in por_fuente:
        actual = row["docs_new"]
        anterior = docs_new_anterior_by_source.get(row["source_id"], 0)
        if actual == 0 and anterior == 0:
            continue
        comparacion.append(
            {
                "source_name": row["source_name"],
                "docs_new_actual": actual,
                "docs_new_anterior": anterior,
                "variacion_pct": _variacion_pct(actual, anterior),
            }
        )

    errores = repository.list_run_errors_for_period(db, period_start, period_end)
    for error in errores:
        if len(error["message"]) > _MENSAJE_MAX_LEN:
            error["message"] = error["message"][:_MENSAJE_MAX_LEN] + "…"

    resumen = {
        "docs_new": sum(row["docs_new"] for row in por_fuente),
        "docs_updated": sum(row["docs_updated"] for row in por_fuente),
        "docs_errors": sum(row["docs_errors"] for row in por_fuente),
        "runs_by_status": repository.count_runs_by_status_for_period(db, period_start, period_end),
        "storage_bytes": repository.sum_document_storage_for_period(db, period_start, period_end),
    }

    return {
        "period": period,
        "period_label": period_label(period),
        "resumen": resumen,
        "por_fuente": por_fuente,
        "fuentes_sin_actividad": repository.list_active_sources_without_activity_in_period(db, period_start, period_end),
        "errores": errores,
        "comparacion": comparacion,
    }
```

- [ ] **Step 4: Confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_reporting.py -v`
Expected: PASS (8 pruebas)

- [ ] **Step 5: Commit**

```bash
git add core/reporting.py tests/test_reporting.py
git commit -m "feat: agregar core/reporting.py con la agregación del reporte mensual"
```

---

## Task 4: Render del PDF (`core/reporting_pdf.py`)

**Files:**
- Modify: `requirements.txt` (agregar `reportlab`)
- Create: `core/reporting_pdf.py`
- Test: `tests/test_reporting_pdf.py`

**Interfaces:**
- Consumes: el diccionario que produce `build_monthly_report_data` (Task 3) — no importa la función directamente, solo su forma.
- Produces: `render_monthly_report_pdf(data: dict) -> bytes`.

- [ ] **Step 1: Agregar la dependencia**

En `requirements.txt`, después de la línea `openpyxl>=3.1.0`:

```
reportlab>=4.2.0
```

Run: `.venv/Scripts/pip install -r requirements.txt`

- [ ] **Step 2: Escribir la prueba que falla**

Create `tests/test_reporting_pdf.py`:

```python
from core.reporting_pdf import render_monthly_report_pdf

_DATA_VACIA = {
    "period": None,
    "period_label": "Agosto 2026",
    "resumen": {"docs_new": 0, "docs_updated": 0, "docs_errors": 0, "runs_by_status": {}, "storage_bytes": 0},
    "por_fuente": [],
    "fuentes_sin_actividad": [],
    "errores": [],
    "comparacion": [],
}

_DATA_CON_CONTENIDO = {
    "period": None,
    "period_label": "Agosto 2026",
    "resumen": {
        "docs_new": 8, "docs_updated": 1, "docs_errors": 2,
        "runs_by_status": {"completed": 3, "failed": 1}, "storage_bytes": 5_242_880,
    },
    "por_fuente": [
        {"source_id": 1, "source_name": "Corte Constitucional", "docs_new": 5, "docs_updated": 1, "docs_errors": 0, "had_failure": False},
        {"source_id": 2, "source_name": "CSJ", "docs_new": 3, "docs_updated": 0, "docs_errors": 2, "had_failure": True},
    ],
    "fuentes_sin_actividad": ["Minhacienda"],
    "errores": [
        {"source_name": "CSJ", "message": "Timeout al descargar", "occurred_at": __import__("datetime").datetime(2026, 8, 15, 10, 30)},
    ],
    "comparacion": [
        {"source_name": "Corte Constitucional", "docs_new_actual": 5, "docs_new_anterior": 0, "variacion_pct": None},
        {"source_name": "CSJ", "docs_new_actual": 3, "docs_new_anterior": 6, "variacion_pct": -50.0},
    ],
}


def test_render_monthly_report_pdf_produces_a_valid_pdf_for_an_empty_month():
    pdf_bytes = render_monthly_report_pdf(_DATA_VACIA)

    assert pdf_bytes.startswith(b"%PDF")


def test_render_monthly_report_pdf_produces_a_valid_pdf_with_full_content():
    pdf_bytes = render_monthly_report_pdf(_DATA_CON_CONTENIDO)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000
```

- [ ] **Step 3: Confirmar que falla**

Run: `.venv/Scripts/pytest tests/test_reporting_pdf.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.reporting_pdf'`

- [ ] **Step 4: Implementar `core/reporting_pdf.py`**

```python
from io import BytesIO
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_TABLE_STYLE = TableStyle(
    [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b2b2b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
)


def _format_bytes(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value / (1024 * 1024):.1f} MB"


def _variacion_texto(variacion_pct: Optional[float]) -> str:
    if variacion_pct is None:
        return "Nueva actividad"
    signo = "+" if variacion_pct >= 0 else ""
    return f"{signo}{variacion_pct:.1f}%"


def render_monthly_report_pdf(data: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    story = [Paragraph(f"Reporte mensual de extracción — {data['period_label']}", styles["Title"]), Spacer(1, 12)]

    # Resumen general
    story.append(Paragraph("Resumen general", styles["Heading2"]))
    resumen = data["resumen"]
    resumen_rows = [
        ["Métrica", "Valor"],
        ["Documentos nuevos", str(resumen["docs_new"])],
        ["Documentos actualizados", str(resumen["docs_updated"])],
        ["Documentos con error", str(resumen["docs_errors"])],
        ["Espacio agregado este mes", _format_bytes(resumen["storage_bytes"])],
    ]
    for run_status, count in sorted(resumen["runs_by_status"].items()):
        resumen_rows.append([f"Corridas — {run_status}", str(count)])
    resumen_table = Table(resumen_rows, hAlign="LEFT")
    resumen_table.setStyle(_TABLE_STYLE)
    story.append(resumen_table)
    story.append(Spacer(1, 18))

    # Detalle por fuente
    story.append(Paragraph("Detalle por fuente", styles["Heading2"]))
    por_fuente = data["por_fuente"]
    if por_fuente:
        fuente_rows = [["Fuente", "Nuevos", "Actualizados", "Errores", "Con fallas"]]
        for row in por_fuente:
            fuente_rows.append(
                [
                    row["source_name"],
                    str(row["docs_new"]),
                    str(row["docs_updated"]),
                    str(row["docs_errors"]),
                    "Sí" if row["had_failure"] else "No",
                ]
            )
        fuente_table = Table(fuente_rows, hAlign="LEFT")
        fuente_table.setStyle(_TABLE_STYLE)
        story.append(fuente_table)
    else:
        story.append(Paragraph("Ninguna fuente tuvo actividad este mes.", styles["Normal"]))
    if data["fuentes_sin_actividad"]:
        story.append(Spacer(1, 8))
        nombres = ", ".join(data["fuentes_sin_actividad"])
        story.append(Paragraph(f"Fuentes activas sin actividad este mes: {nombres}.", styles["Normal"]))
    story.append(Spacer(1, 18))

    # Detalle de errores
    story.append(Paragraph("Detalle de errores", styles["Heading2"]))
    errores = data["errores"]
    if errores:
        error_rows = [["Fuente", "Fecha", "Mensaje"]]
        for error in errores:
            error_rows.append(
                [error["source_name"], error["occurred_at"].strftime("%Y-%m-%d %H:%M"), error["message"]]
            )
        error_table = Table(error_rows, hAlign="LEFT", colWidths=[4 * cm, 3 * cm, 9 * cm])
        error_table.setStyle(_TABLE_STYLE)
        story.append(error_table)
    else:
        story.append(Paragraph("Sin errores registrados este mes.", styles["Normal"]))
    story.append(Spacer(1, 18))

    # Comparación con el mes anterior
    story.append(Paragraph("Comparación con el mes anterior", styles["Heading2"]))
    comparacion = data["comparacion"]
    if comparacion:
        comparacion_rows = [["Fuente", "Este mes", "Mes anterior", "Variación"]]
        for row in comparacion:
            comparacion_rows.append(
                [
                    row["source_name"],
                    str(row["docs_new_actual"]),
                    str(row["docs_new_anterior"]),
                    _variacion_texto(row["variacion_pct"]),
                ]
            )
        comparacion_table = Table(comparacion_rows, hAlign="LEFT")
        comparacion_table.setStyle(_TABLE_STYLE)
        story.append(comparacion_table)
    else:
        story.append(Paragraph("Sin datos suficientes para comparar con el mes anterior.", styles["Normal"]))

    doc.build(story)
    return buffer.getvalue()
```

- [ ] **Step 5: Confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_reporting_pdf.py -v`
Expected: PASS (2 pruebas)

- [ ] **Step 6: Commit**

```bash
git add requirements.txt core/reporting_pdf.py tests/test_reporting_pdf.py
git commit -m "feat: agregar render del PDF del reporte mensual con reportlab"
```

---

## Task 5: Tarea de Celery `worker.build_monthly_report`

**Files:**
- Modify: `worker/tasks.py` (imports + nueva tarea, al final del archivo)
- Test: `tests/test_tasks.py`

**Interfaces:**
- Consumes: `repository.get_monthly_report`, `repository.set_monthly_report_status` (Task 1); `build_monthly_report_data` (Task 3); `render_monthly_report_pdf` (Task 4); `upload_file` (ya existe en `core/storage.py`).
- Produces: tarea Celery `worker.build_monthly_report(report_id: int) -> None`, registrada con `@celery_app.task(name="worker.build_monthly_report")`.

- [ ] **Step 1: Escribir la prueba que falla**

Agregar a `tests/test_tasks.py` (al final del archivo):

```python
def test_build_monthly_report_uploads_pdf_and_marks_completed(db_session, test_engine, monkeypatch):
    from datetime import date
    from sqlalchemy.orm import sessionmaker
    from worker.tasks import build_monthly_report

    celery_app.conf.task_always_eager = True
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    report = repository.create_monthly_report(db_session, period=date(2026, 8, 1), triggered_by="manual")

    build_monthly_report(report.id)

    refreshed = repository.get_monthly_report(db_session, report.id)
    assert refreshed.status == "completed"
    assert refreshed.storage_key == f"reportes/2026-08_{report.id}.pdf"
    assert refreshed.storage_bucket == TEST_S3_BUCKET
    assert refreshed.finished_at is not None


def test_build_monthly_report_marks_failed_on_error(db_session, test_engine, monkeypatch):
    from datetime import date
    from sqlalchemy.orm import sessionmaker
    from worker.tasks import build_monthly_report

    celery_app.conf.task_always_eager = True
    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr(
        "worker.tasks.render_monthly_report_pdf",
        lambda data: (_ for _ in ()).throw(RuntimeError("fallo simulado de render")),
    )

    report = repository.create_monthly_report(db_session, period=date(2026, 8, 1), triggered_by="manual")

    build_monthly_report(report.id)

    refreshed = repository.get_monthly_report(db_session, report.id)
    assert refreshed.status == "failed"
    assert "fallo simulado de render" in refreshed.error_message
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv/Scripts/pytest tests/test_tasks.py -k build_monthly_report -v`
Expected: FAIL — `ImportError: cannot import name 'build_monthly_report' from 'worker.tasks'`

- [ ] **Step 3: Implementar la tarea**

En `worker/tasks.py`, agregar a los imports (junto a los demás `from core...`):

```python
from core.reporting import build_monthly_report_data
from core.reporting_pdf import render_monthly_report_pdf
```

Al final del archivo:

```python
@celery_app.task(name="worker.build_monthly_report")
def build_monthly_report(report_id: int) -> None:
    db = SessionLocal()
    try:
        repository.set_monthly_report_status(db, report_id, "running", started_at=datetime.now(timezone.utc))

        report = repository.get_monthly_report(db, report_id)
        if report is None:
            return

        data = build_monthly_report_data(db, report.period)
        pdf_bytes = render_monthly_report_pdf(data)

        with tempfile.TemporaryDirectory(prefix=f"monthly_report_{report_id}_") as tmp_dir:
            pdf_path = Path(tmp_dir) / "reporte.pdf"
            pdf_path.write_bytes(pdf_bytes)
            key = f"reportes/{report.period:%Y-%m}_{report_id}.pdf"
            bucket, key = upload_file(pdf_path, key, content_type="application/pdf")

        repository.set_monthly_report_status(
            db, report_id, "completed", storage_bucket=bucket, storage_key=key,
            finished_at=datetime.now(timezone.utc),
        )
    except Exception as exc:
        repository.set_monthly_report_status(
            db, report_id, "failed", error_message=str(exc), finished_at=datetime.now(timezone.utc)
        )
    finally:
        db.close()
```

- [ ] **Step 4: Confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_tasks.py -k build_monthly_report -v`
Expected: PASS (2 pruebas)

- [ ] **Step 5: Commit**

```bash
git add worker/tasks.py tests/test_tasks.py
git commit -m "feat: agregar tarea de Celery que arma y sube el PDF del reporte mensual"
```

---

## Task 6: Generación automática (`worker/beat_schedule.py`)

**Files:**
- Modify: `worker/beat_schedule.py`
- Test: `tests/test_beat_schedule.py`

**Interfaces:**
- Consumes: `repository.create_monthly_report` (Task 1); `worker.tasks.build_monthly_report` (Task 5).
- Produces: tarea Celery `worker.trigger_monthly_report`; entrada `"monthly-report"` en `celery_app.conf.beat_schedule`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `tests/test_beat_schedule.py` (al final del archivo):

```python
def test_trigger_monthly_report_creates_the_previous_month_and_dispatches(db_session, test_engine, monkeypatch):
    from datetime import date

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr(beat_schedule, "SessionLocal", task_session_factory)
    monkeypatch.setattr(beat_schedule, "date", type("_FixedDate", (date,), {"today": staticmethod(lambda: date(2026, 9, 1))}))
    dispatched = []
    monkeypatch.setattr(beat_schedule.build_monthly_report, "delay", lambda report_id: dispatched.append(report_id))

    beat_schedule.trigger_monthly_report()

    reports = repository.list_monthly_reports(db_session)
    assert len(reports) == 1
    assert reports[0].period == date(2026, 8, 1)
    assert reports[0].triggered_by == "scheduled"
    assert dispatched == [reports[0].id]


def test_trigger_monthly_report_handles_year_rollover(db_session, test_engine, monkeypatch):
    from datetime import date

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr(beat_schedule, "SessionLocal", task_session_factory)
    monkeypatch.setattr(beat_schedule, "date", type("_FixedDate", (date,), {"today": staticmethod(lambda: date(2026, 1, 1))}))
    monkeypatch.setattr(beat_schedule.build_monthly_report, "delay", lambda report_id: None)

    beat_schedule.trigger_monthly_report()

    reports = repository.list_monthly_reports(db_session)
    assert reports[0].period == date(2025, 12, 1)


def test_beat_schedule_incluye_el_reporte_mensual():
    entrada = beat_schedule.celery_app.conf.beat_schedule["monthly-report"]
    assert entrada["task"] == "worker.trigger_monthly_report"
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv/Scripts/pytest tests/test_beat_schedule.py -k monthly_report -v`
Expected: FAIL — `AttributeError: module 'worker.beat_schedule' has no attribute 'trigger_monthly_report'`

- [ ] **Step 3: Implementar**

En `worker/beat_schedule.py`, cambiar el import:

```python
from worker.tasks import build_bulk_download_zip, orchestrate_run
```

por:

```python
from worker.tasks import build_bulk_download_zip, build_monthly_report, orchestrate_run
```

Agregar la tarea (después de `trigger_scheduled_bulk_download`, antes de `celery_app.conf.beat_schedule = {`):

```python
@celery_app.task(name="worker.trigger_monthly_report")
def trigger_monthly_report():
    today = date.today()
    if today.month == 1:
        period = date(today.year - 1, 12, 1)
    else:
        period = date(today.year, today.month - 1, 1)

    db = SessionLocal()
    try:
        report = repository.create_monthly_report(db, period=period, triggered_by="scheduled")
        report_id = report.id
    finally:
        db.close()
    build_monthly_report.delay(report_id)
```

Y agregar la entrada al diccionario `beat_schedule`:

```python
    "monthly-report": {
        "task": "worker.trigger_monthly_report",
        # Día 1 de cada mes, después de nightly-storage-sync (02:00) y antes
        # del scrape diario (06:00), para no competir por recursos.
        "schedule": crontab(day_of_month=1, hour=3, minute=30),
    },
```

- [ ] **Step 4: Confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_beat_schedule.py -k monthly_report -v`
Expected: PASS (3 pruebas)

- [ ] **Step 5: Commit**

```bash
git add worker/beat_schedule.py tests/test_beat_schedule.py
git commit -m "feat: generar el reporte mensual automáticamente el día 1 de cada mes"
```

---

## Task 7: API REST (`api/routers/reports.py`)

**Files:**
- Modify: `api/schemas.py` (agregar `MonthlyReportCreate`, `MonthlyReportOut`)
- Create: `api/routers/reports.py`
- Modify: `api/main.py` (registrar el router)
- Test: `tests/test_api_reports.py`

**Interfaces:**
- Consumes: `repository.create_monthly_report`, `repository.get_monthly_report`, `repository.list_monthly_reports` (Task 1); `worker.tasks.build_monthly_report` (Task 5); `presigned_url` (ya existe en `core/storage.py`).
- Produces: `POST /reports`, `GET /reports`, `GET /reports/{id}/download`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Create `tests/test_api_reports.py`:

```python
from datetime import date


def test_post_report_creates_row_and_dispatches_task(api_client, auth_header, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "api.routers.reports.build_monthly_report.delay", lambda report_id: calls.append(report_id)
    )
    monkeypatch.setattr("api.routers.reports.date", type("_FixedDate", (date,), {"today": staticmethod(lambda: date(2026, 9, 17))}))

    response = api_client.post("/reports", json={"period": "2026-08-01"}, headers=auth_header)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["period"] == "2026-08-01"
    assert body["triggered_by"] == "manual"
    assert calls == [body["id"]]


def test_post_report_rejects_the_current_month(api_client, auth_header, monkeypatch):
    monkeypatch.setattr("api.routers.reports.build_monthly_report.delay", lambda *a, **k: None)
    monkeypatch.setattr("api.routers.reports.date", type("_FixedDate", (date,), {"today": staticmethod(lambda: date(2026, 9, 17))}))

    response = api_client.post("/reports", json={"period": "2026-09-01"}, headers=auth_header)

    assert response.status_code == 400


def test_post_report_rejects_a_future_month(api_client, auth_header, monkeypatch):
    monkeypatch.setattr("api.routers.reports.build_monthly_report.delay", lambda *a, **k: None)
    monkeypatch.setattr("api.routers.reports.date", type("_FixedDate", (date,), {"today": staticmethod(lambda: date(2026, 9, 17))}))

    response = api_client.post("/reports", json={"period": "2026-10-01"}, headers=auth_header)

    assert response.status_code == 400


def test_get_reports_lists_most_recent_first(api_client, auth_header, monkeypatch):
    monkeypatch.setattr("api.routers.reports.build_monthly_report.delay", lambda *a, **k: None)
    monkeypatch.setattr("api.routers.reports.date", type("_FixedDate", (date,), {"today": staticmethod(lambda: date(2026, 9, 17))}))

    first = api_client.post("/reports", json={"period": "2026-07-01"}, headers=auth_header).json()
    second = api_client.post("/reports", json={"period": "2026-08-01"}, headers=auth_header).json()

    response = api_client.get("/reports", headers=auth_header)

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [second["id"], first["id"]]


def test_get_report_download_returns_404_when_not_completed(api_client, auth_header, monkeypatch):
    monkeypatch.setattr("api.routers.reports.build_monthly_report.delay", lambda *a, **k: None)
    monkeypatch.setattr("api.routers.reports.date", type("_FixedDate", (date,), {"today": staticmethod(lambda: date(2026, 9, 17))}))

    created = api_client.post("/reports", json={"period": "2026-08-01"}, headers=auth_header).json()

    response = api_client.get(f"/reports/{created['id']}/download", headers=auth_header)

    assert response.status_code == 404


def test_get_report_download_returns_signed_url_when_completed(api_client, auth_header, db_session):
    from core.db import repository

    report = repository.create_monthly_report(db_session, period=date(2026, 8, 1), triggered_by="manual")
    repository.set_monthly_report_status(
        db_session, report.id, "completed", storage_key=f"reportes/2026-08_{report.id}.pdf", storage_bucket="iurisync-test"
    )

    response = api_client.get(f"/reports/{report.id}/download", headers=auth_header)

    assert response.status_code == 200
    assert "url" in response.json()


def test_reports_endpoints_require_authentication(api_client):
    assert api_client.post("/reports", json={"period": "2026-08-01"}).status_code == 401
    assert api_client.get("/reports").status_code == 401
    assert api_client.get("/reports/1/download").status_code == 401
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv/Scripts/pytest tests/test_api_reports.py -v`
Expected: FAIL — `404 Not Found` (la ruta no existe todavía)

- [ ] **Step 3: Agregar los esquemas**

En `api/schemas.py`, después de `BulkDownloadDeletionOut`:

```python
class MonthlyReportCreate(BaseModel):
    period: date


class MonthlyReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    period: date
    status: str
    triggered_by: str
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
```

- [ ] **Step 4: Crear el router**

Create `api/routers/reports.py`:

```python
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from api.deps import get_db, require_session
from api.schemas import MonthlyReportCreate, MonthlyReportOut
from core.config import get_settings
from core.db import repository
from core.storage import presigned_url
from worker.tasks import build_monthly_report

router = APIRouter(dependencies=[Depends(require_session)])


@router.post("/reports", response_model=MonthlyReportOut, status_code=status.HTTP_202_ACCEPTED)
def post_report(payload: MonthlyReportCreate, db: Session = Depends(get_db)):
    period = date(payload.period.year, payload.period.month, 1)
    today = date.today()
    current_period = date(today.year, today.month, 1)
    if period >= current_period:
        raise HTTPException(status_code=400, detail="No se puede generar el reporte de un mes que no ha terminado.")

    report = repository.create_monthly_report(db, period=period, triggered_by="manual")
    build_monthly_report.delay(report.id)
    return report


@router.get("/reports", response_model=list[MonthlyReportOut])
def get_reports(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    return repository.list_monthly_reports(db, limit=limit, offset=offset)


@router.get("/reports/{report_id}/download")
def get_report_download(report_id: int, db: Session = Depends(get_db)):
    report = repository.get_monthly_report(db, report_id)
    if report is None or report.status != "completed" or not report.storage_key:
        raise HTTPException(status_code=404, detail="Reporte no disponible")

    bucket = report.storage_bucket or get_settings().s3_bucket
    url = presigned_url(
        bucket,
        report.storage_key,
        response_content_disposition=f'attachment; filename="reporte_{report.period:%Y-%m}.pdf"',
    )
    return {"url": url}
```

- [ ] **Step 5: Registrar el router**

En `api/main.py:4`, cambiar:

```python
from api.routers import auth, bulk_downloads, cali_decretos, case_links, documents, health, reorganize, runs, sources
```

por:

```python
from api.routers import auth, bulk_downloads, cali_decretos, case_links, documents, health, reorganize, reports, runs, sources
```

Y agregar, junto a los demás `app.include_router(...)`:

```python
app.include_router(reports.router)
```

- [ ] **Step 6: Confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_api_reports.py -v`
Expected: PASS (7 pruebas)

- [ ] **Step 7: Commit**

```bash
git add api/schemas.py api/routers/reports.py api/main.py tests/test_api_reports.py
git commit -m "feat: agregar endpoints REST para generar y descargar reportes mensuales"
```

---

## Task 8: Cliente API y formateador de mes en el frontend

**Files:**
- Create: `frontend/src/api/reports.ts`
- Modify: `frontend/src/lib/formatters.ts` (agregar `formatMonth` y `getPreviousMonthString`)

**Interfaces:**
- Produces: `interface MonthlyReport` (`id`, `period`, `status`, `triggered_by`, `error_message`, `started_at`, `finished_at`, `created_at`); `fetchReports(params): Promise<MonthlyReport[]>`; `createReport(period: string /* "YYYY-MM" */): Promise<MonthlyReport>`; `fetchReportUrl(id: number): Promise<string>`; `formatMonth(value: string | null): string`; `getPreviousMonthString(from?: Date): string` (retorna `"YYYY-MM"`).

- [ ] **Step 1: Crear el cliente API**

Create `frontend/src/api/reports.ts`:

```typescript
import { apiFetch, buildQuery } from "./client";

export interface MonthlyReport {
  id: number;
  period: string;
  status: "pending" | "running" | "completed" | "failed";
  triggered_by: "manual" | "scheduled";
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface ListReportsParams {
  limit?: number;
  offset?: number;
  [key: string]: string | number | boolean | undefined;
}

export function fetchReports(params: ListReportsParams = {}): Promise<MonthlyReport[]> {
  return apiFetch<MonthlyReport[]>(`/reports${buildQuery(params)}`);
}

export function createReport(period: string): Promise<MonthlyReport> {
  return apiFetch<MonthlyReport>("/reports", { method: "POST", body: JSON.stringify({ period: `${period}-01` }) });
}

export function fetchReportUrl(id: number): Promise<string> {
  return apiFetch<{ url: string }>(`/reports/${id}/download`).then((data) => data.url);
}
```

- [ ] **Step 2: Agregar los helpers de formato**

En `frontend/src/lib/formatters.ts`, después de `formatDate`:

```typescript
const MONTH_ONLY_PATTERN = /^(\d{4})-(\d{2})/;

// "period" llega como fecha del día 1 ("2026-08-01"); se muestra solo mes y año
// en español, con la misma corrección de zona horaria que parseDateOnlyAsLocal
// (si no, en América/Bogotá el mes mostrado puede quedar un día atrás y cruzar
// al mes anterior).
export function formatMonth(value: string | null): string {
  if (!value) return "—";
  const match = MONTH_ONLY_PATTERN.exec(value);
  if (!match) return value;
  const [, year, month] = match;
  const label = new Date(Number(year), Number(month) - 1, 1).toLocaleDateString("es-CO", {
    year: "numeric",
    month: "long",
  });
  return label.charAt(0).toUpperCase() + label.slice(1);
}

// "YYYY-MM" del mes calendario anterior al de `from` (por defecto, hoy), en
// hora local — mismo criterio de "hoy local" que todayDateString. Es el tope
// permitido para generar un reporte manual (el mes actual todavía no cerró).
export function getPreviousMonthString(from: Date = new Date()): string {
  const year = from.getFullYear();
  const month = from.getMonth(); // 0-indexed; month-1 en 1-indexed es el mes anterior
  const previous = new Date(year, month - 1, 1);
  const previousYear = previous.getFullYear();
  const previousMonth = String(previous.getMonth() + 1).padStart(2, "0");
  return `${previousYear}-${previousMonth}`;
}
```

- [ ] **Step 3: Verificar manualmente**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores de tipos nuevos.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/reports.ts frontend/src/lib/formatters.ts
git commit -m "feat: agregar cliente API y formateadores de mes para reportes"
```

---

## Task 9: Página "Reportes" (frontend)

**Files:**
- Create: `frontend/src/pages/ReportsPage.tsx`
- Test: `frontend/src/pages/ReportsPage.test.tsx`
- Modify: `frontend/src/App.tsx` (ruta `/reports`)
- Modify: `frontend/src/components/layout/Sidebar.tsx` (entrada de menú)

**Interfaces:**
- Consumes: `fetchReports`, `createReport`, `fetchReportUrl`, `MonthlyReport` (Task 8); `formatMonth`, `formatDateTime`, `getPreviousMonthString` (Task 8 / `formatters.ts` existente); `downloadFromUrl` (ya existe en `frontend/src/api/documents.ts`); `StatusBadge`, `ErrorBanner`, `EmptyState`, `TableRowsSkeleton`, `Button`, estilos de `frontend/src/lib/tableStyles.ts` (ya existen).
- Produces: componente `ReportsPage`, ruta `/reports`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Create `frontend/src/pages/ReportsPage.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { delay, http, HttpResponse } from "msw";
import { server } from "../test/server";
import { ReportsPage } from "./ReportsPage";

const BASE_URL = "http://localhost:8000";

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ReportsPage />
    </QueryClientProvider>
  );
}

const COMPLETED = {
  id: 1,
  period: "2026-08-01",
  status: "completed",
  triggered_by: "scheduled",
  error_message: null,
  started_at: "2026-09-01T03:30:00Z",
  finished_at: "2026-09-01T03:31:00Z",
  created_at: "2026-09-01T03:30:00Z",
};

describe("ReportsPage", () => {
  it("renders the fetched reports with month and status", async () => {
    server.use(http.get(`${BASE_URL}/reports`, () => HttpResponse.json([COMPLETED])));

    renderPage();

    expect(await screen.findByText("Agosto 2026")).toBeInTheDocument();
    expect(screen.getByText("Completado")).toBeInTheDocument();
  });

  it("shows an empty state when there is no history yet", async () => {
    server.use(http.get(`${BASE_URL}/reports`, () => HttpResponse.json([])));

    renderPage();

    expect(await screen.findByText(/todav.a no se ha generado ning.n reporte/i)).toBeInTheDocument();
  });

  it("does not show the empty state while the first request is still in flight", async () => {
    server.use(
      http.get(`${BASE_URL}/reports`, async () => {
        await delay(50);
        return HttpResponse.json([]);
      })
    );

    renderPage();

    expect(screen.queryByText(/todav.a no se ha generado ning.n reporte/i)).not.toBeInTheDocument();
    expect(await screen.findByText(/todav.a no se ha generado ning.n reporte/i)).toBeInTheDocument();
  });

  it("generates a report for the selected month", async () => {
    let posted: unknown = null;
    server.use(
      http.get(`${BASE_URL}/reports`, () => HttpResponse.json([])),
      http.post(`${BASE_URL}/reports`, async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json({ ...COMPLETED, id: 2, status: "pending", period: "2026-07-01" }, { status: 202 });
      })
    );
    const user = userEvent.setup();
    renderPage();

    const monthInput = await screen.findByLabelText(/mes/i);
    await user.clear(monthInput);
    await user.type(monthInput, "2026-07");
    await user.click(screen.getByRole("button", { name: /generar/i }));

    await waitFor(() => expect(posted).toEqual({ period: "2026-07-01" }));
  });

  it("shows an error banner when generation is rejected", async () => {
    server.use(
      http.get(`${BASE_URL}/reports`, () => HttpResponse.json([])),
      http.post(`${BASE_URL}/reports`, () =>
        HttpResponse.json({ detail: "No se puede generar el reporte de un mes que no ha terminado." }, { status: 400 })
      )
    );
    const user = userEvent.setup();
    renderPage();

    const monthInput = await screen.findByLabelText(/mes/i);
    await user.clear(monthInput);
    await user.type(monthInput, "2026-07");
    await user.click(screen.getByRole("button", { name: /generar/i }));

    expect(await screen.findByText("No se puede generar el reporte de un mes que no ha terminado.")).toBeInTheDocument();
  });

  it("shows a Descargar button only when completed, wired to the presigned url", async () => {
    server.use(
      http.get(`${BASE_URL}/reports`, () => HttpResponse.json([COMPLETED])),
      http.get(`${BASE_URL}/reports/1/download`, () => HttpResponse.json({ url: "https://signed.example.com/1.pdf" }))
    );
    server.use(http.get("https://signed.example.com/1.pdf", () => HttpResponse.text("contenido")));
    const clickSpy = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    const createElementSpy = vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const element = originalCreateElement(tag);
      if (tag === "a") element.click = clickSpy;
      return element;
    });

    const user = userEvent.setup();
    renderPage();

    const button = await screen.findByRole("button", { name: /descargar/i });
    await user.click(button);

    await waitFor(() => expect(clickSpy).toHaveBeenCalledOnce());
    createElementSpy.mockRestore();
  });

  it("shows the error message instead of a download button for a failed report", async () => {
    server.use(
      http.get(`${BASE_URL}/reports`, () =>
        HttpResponse.json([{ ...COMPLETED, status: "failed", error_message: "No se pudo generar el PDF" }])
      )
    );

    renderPage();

    expect(await screen.findByText("No se pudo generar el PDF")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /descargar/i })).not.toBeInTheDocument();
  });

  it("polls again while a report is not in a terminal state, and stops once it is", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let callCount = 0;
    server.use(
      http.get(`${BASE_URL}/reports`, () => {
        callCount += 1;
        return HttpResponse.json([{ ...COMPLETED, status: callCount >= 2 ? "completed" : "running" }]);
      })
    );

    renderPage();
    await waitFor(() => expect(callCount).toBe(1));

    await vi.advanceTimersByTimeAsync(4100);
    await waitFor(() => expect(callCount).toBe(2));

    await vi.advanceTimersByTimeAsync(4100);
    expect(callCount).toBe(2);

    vi.useRealTimers();
  });
});
```

- [ ] **Step 2: Confirmar que falla**

Run: `cd frontend && npx vitest run src/pages/ReportsPage.test.tsx`
Expected: FAIL — no se puede resolver `./ReportsPage`

- [ ] **Step 3: Implementar la página**

Create `frontend/src/pages/ReportsPage.tsx`:

```tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileBarChart2 } from "lucide-react";
import { ApiError } from "../api/client";
import { downloadFromUrl } from "../api/documents";
import { createReport, fetchReports, fetchReportUrl, type MonthlyReport } from "../api/reports";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { StatusBadge } from "../components/StatusBadge";
import { TableRowsSkeleton } from "../components/TableSkeleton";
import { Button } from "../components/ui/button";
import { formatDateTime, formatMonth, getPreviousMonthString } from "../lib/formatters";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TD_MONO, TH, THEAD_ROW } from "../lib/tableStyles";

const POLL_INTERVAL_MS = 4000;
const TERMINAL_STATUSES = new Set(["completed", "failed"]);

export function ReportsPage() {
  const maxMonth = getPreviousMonthString();
  const [selectedMonth, setSelectedMonth] = useState(maxMonth);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const reportsQuery = useQuery({
    queryKey: ["monthly-reports"],
    queryFn: () => fetchReports({ limit: 50 }),
    refetchInterval: (query) => {
      const data = query.state.data;
      const hasActive = data?.some((item) => !TERMINAL_STATUSES.has(item.status));
      return hasActive ? POLL_INTERVAL_MS : false;
    },
  });

  const generateMutation = useMutation({
    mutationFn: (period: string) => createReport(period),
    onSuccess: () => {
      setGenerateError(null);
      queryClient.invalidateQueries({ queryKey: ["monthly-reports"] });
    },
    onError: (error: unknown) =>
      setGenerateError(error instanceof ApiError ? error.message : "No se pudo generar el reporte."),
  });

  async function handleDownload(item: MonthlyReport) {
    setDownloadError(null);
    try {
      const url = await fetchReportUrl(item.id);
      await downloadFromUrl(url, `reporte_${item.period.slice(0, 7)}.pdf`);
    } catch {
      setDownloadError("No se pudo descargar el reporte. El enlace pudo haber expirado — intenta de nuevo.");
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="flex items-center gap-1.5 text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">
          <FileBarChart2 className="size-3.5" aria-hidden="true" />
          Métricas de extracción
        </p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">Reportes</h1>
      </div>

      <div className="flex items-end gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="report-month" className="text-xs font-medium text-muted-foreground">
            Mes
          </label>
          <input
            id="report-month"
            type="month"
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
            max={maxMonth}
            value={selectedMonth}
            onChange={(event) => setSelectedMonth(event.target.value)}
          />
        </div>
        <Button
          onClick={() => generateMutation.mutate(selectedMonth)}
          disabled={!selectedMonth || selectedMonth > maxMonth || generateMutation.isPending}
        >
          Generar
        </Button>
      </div>

      {reportsQuery.isError && (
        <ErrorBanner message="No se pudieron cargar los reportes." onRetry={() => reportsQuery.refetch()} />
      )}
      {downloadError && <ErrorBanner message={downloadError} />}
      {generateError && <ErrorBanner message={generateError} />}

      <div className={TABLE_SHELL}>
        <div className={TABLE_SCROLL}>
          <table className={TABLE} aria-busy={reportsQuery.isLoading}>
            <thead>
              <tr className={THEAD_ROW}>
                <th className={TH}>Mes</th>
                <th className={TH}>Estado</th>
                <th className={TH}>Creado</th>
                <th className={TH}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {reportsQuery.isLoading ? (
                <TableRowsSkeleton rows={6} columns={4} widths={["w-28", "w-24", "w-28", "w-24"]} />
              ) : (
                reportsQuery.data?.map((item) => (
                  <tr key={item.id} className={TBODY_ROW}>
                    <td className={TD}>{formatMonth(item.period)}</td>
                    <td className={TD}>
                      <StatusBadge status={item.status} />
                    </td>
                    <td className={TD_MONO}>{formatDateTime(item.created_at)}</td>
                    <td className={TD}>
                      {item.status === "completed" && (
                        <Button variant="outline" size="sm" onClick={() => handleDownload(item)}>
                          Descargar
                        </Button>
                      )}
                      {item.status === "failed" && <span className="text-xs text-rojo">{item.error_message}</span>}
                      {(item.status === "pending" || item.status === "running") && (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {!reportsQuery.isLoading && (reportsQuery.data?.length ?? 0) === 0 && (
          <EmptyState message="Todavía no se ha generado ningún reporte." />
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Confirmar que pasan**

Run: `cd frontend && npx vitest run src/pages/ReportsPage.test.tsx`
Expected: PASS (8 pruebas)

- [ ] **Step 5: Registrar la ruta**

En `frontend/src/App.tsx`, después de la línea de `BulkDownloadsPage`:

```typescript
const ReportsPage = lazy(() => import("./pages/ReportsPage").then((m) => ({ default: m.ReportsPage })));
```

Y, después de `<Route path="/bulk-downloads" element={<BulkDownloadsPage />} />`:

```tsx
<Route path="/reports" element={<ReportsPage />} />
```

- [ ] **Step 6: Registrar la entrada de menú**

En `frontend/src/components/layout/Sidebar.tsx:3`, agregar `FileBarChart2` a los imports de `lucide-react`:

```typescript
import { Archive, FileBarChart2, FileStack, Gauge, GitMerge, LogOut, PanelLeftClose, PanelLeftOpen, PlayCircle, Radar, Wand2 } from "lucide-react";
```

Y, después de la entrada `/bulk-downloads` en `LINKS`:

```typescript
  { to: "/reports", label: "Reportes", end: false, icon: FileBarChart2 },
```

- [ ] **Step 7: Verificar manualmente en el navegador**

Con el entorno corriendo (`uvicorn`, `celery worker`, `npm run dev`), entrar a `http://localhost:5173/reports`, confirmar que la página carga, que el selector de mes no permite elegir el mes actual, y que "Generar" dispara `POST /reports` (revisar la pestaña Network).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/ReportsPage.tsx frontend/src/pages/ReportsPage.test.tsx frontend/src/App.tsx frontend/src/components/layout/Sidebar.tsx
git commit -m "feat: agregar página Reportes con generación manual y descarga"
```

---

## Verificación final

- [ ] Run: `.venv/Scripts/pytest -v` — sin nuevas fallas (aparte de la falla preexistente de `test_migrations.py` en Windows, ver Gotchas de la skill `run-iurisync`).
- [ ] Run: `cd frontend && npm test -- --run` — todo verde.
- [ ] Run: `cd frontend && npx tsc --noEmit` — sin errores de tipos.
