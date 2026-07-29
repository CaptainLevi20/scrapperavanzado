# Vinculación de casos entre tribunales (SAMAI) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detectar automáticamente cuando el mismo proceso judicial reaparece en más de un tribunal dentro de SAMAI (ej. Tribunal Administrativo → Consejo de Estado), dejar la sugerencia pendiente de confirmación humana, y mostrar el proceso completo como una línea de tiempo una vez confirmado.

**Architecture:** Se agrega un campo `radicado` (normalizado, solo dígitos) a `documents`, poblado por el scraper de SAMAI al capturar cada documento. Tres tablas nuevas (`case_links`, `case_link_stages`, `case_link_suggestions`) modelan el expediente, sus etapas (fuente+radicado) y la bandeja de sugerencias pendientes — completamente separadas de `documents`. Después de cada run de una fuente SAMAI, una función de comparación por prefijo de dígitos genera sugerencias; nunca se auto-confirma nada. Confirmar, descartar y vincular manualmente son operaciones explícitas desde una bandeja nueva en el frontend; una línea de tiempo dedicada muestra el expediente ya confirmado.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (backend), React + TanStack Query + React Router (frontend), pytest / vitest.

## Global Constraints

- Alcance v1: solo dentro de la familia `samai` (spec, sección "Alcance").
- El campo `radicado` no se muestra como columna en la tabla de documentos de la interfaz (decisión explícita del usuario).
- La comparación usa los primeros ~16 dígitos (`MIN_MATCH_DIGITS`), ajustable después — nunca se auto-confirma, siempre requiere acción humana.
- El generador de sugerencias corre después de guardar los documentos del run; un fallo ahí nunca debe tumbar el run.
- El par de fuentes de una sugerencia se guarda en un orden consistente (no se generan sugerencias espejo A~B y B~A).

---

## Mapa de archivos

**Backend — nuevos:**
- `alembic/versions/<generado>_add_radicado_and_case_links.py`
- `api/routers/case_links.py`
- `core/backfill_samai_radicado.py`
- `tests/test_api_case_links.py`
- `tests/test_backfill_samai_radicado.py`

**Backend — modificados:**
- `core/models.py` (campo `radicado` en `RawDocModel`)
- `core/scrapers/families/samai.py` (poblar `radicado`)
- `core/db/models.py` (columna + 3 tablas nuevas)
- `core/utils.py` (`matching_prefix_length`, `MIN_MATCH_DIGITS`)
- `core/db/repository.py` (motor de coincidencias + confirmar/descartar/vincular + lookups)
- `worker/tasks.py` (pasar `radicado` al insertar; hook post-run)
- `api/schemas.py` (schemas nuevos + extensión de `DocumentOut`)
- `api/routers/documents.py` (incluir estado de vínculo en la respuesta)
- `api/main.py` (registrar router)
- `tests/test_core_utils.py`, `tests/families/test_samai.py`, `tests/test_repository.py`, `tests/test_tasks.py`, `tests/test_api_documents.py` (casos nuevos)

**Frontend — nuevos:**
- `frontend/src/api/caseLinks.ts` + `.test.ts`
- `frontend/src/pages/CaseLinksPage.tsx` + `.test.tsx`
- `frontend/src/pages/CaseLinkDetailPage.tsx` + `.test.tsx`

**Frontend — modificados:**
- `frontend/src/api/types.ts` (tipos nuevos + extensión de `Document`)
- `frontend/src/App.tsx`, `frontend/src/components/layout/Sidebar.tsx`
- `frontend/src/pages/DocumentsPage.tsx` + `.test.tsx` (nota de caso relacionado)

---

### Task 1: Función pura de comparación de radicados

**Files:**
- Modify: `core/utils.py`
- Test: `tests/test_core_utils.py`

**Interfaces:**
- Produces: `matching_prefix_length(a: str, b: str) -> int`, `MIN_MATCH_DIGITS: int = 16` — usados por `core/db/repository.py` en la Task 5.

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar al final de `tests/test_core_utils.py`:

```python
from core.utils import matching_prefix_length, MIN_MATCH_DIGITS


def test_matching_prefix_length_counts_shared_leading_digits():
    assert matching_prefix_length("25000234200020200000802", "25000234200020200000801") == 22


def test_matching_prefix_length_stops_at_first_difference():
    assert matching_prefix_length("11001032800020260027100", "11001032900020260027100") == 8


def test_matching_prefix_length_returns_zero_for_completely_different_strings():
    assert matching_prefix_length("11001032800020260027100", "99999999999999999999999") == 0


def test_matching_prefix_length_handles_different_lengths():
    assert matching_prefix_length("110010328000", "1100103280") == 10


def test_min_match_digits_is_16():
    # Documenta el umbral de partida usado por el generador de sugerencias
    # (core/db/repository.py) — ajustable si con casos reales confirmados se
    # ve que sugiere de más o de menos (ver spec, sección "Cómo se generan").
    assert MIN_MATCH_DIGITS == 16
```

- [ ] **Step 2: Confirmar que fallan**

Run: `.venv/Scripts/pytest tests/test_core_utils.py -k matching_prefix_length -v`
Expected: FAIL con `ImportError` (`matching_prefix_length` no existe todavía).

- [ ] **Step 3: Implementar**

Agregar al final de `core/utils.py`:

```python
# Umbral de partida para sugerir que dos radicados de fuentes distintas son el
# mismo proceso en otra instancia — no hay certeza de si el radicado cambia
# una parte (posiblemente el segmento final) entre instancias, así que en vez
# de una regla exacta se compara solo el prefijo inicial. Una persona siempre
# confirma antes de que cuente como el mismo expediente (ver
# docs/superpowers/specs/2026-07-29-vinculacion-casos-samai-design.md).
MIN_MATCH_DIGITS = 16


def matching_prefix_length(a: str, b: str) -> int:
    length = 0
    for char_a, char_b in zip(a, b):
        if char_a != char_b:
            break
        length += 1
    return length
```

- [ ] **Step 4: Confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_core_utils.py -k "matching_prefix_length or min_match_digits" -v`
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add core/utils.py tests/test_core_utils.py
git commit -m "feat: agrega comparación de prefijo de radicados"
```

---

### Task 2: Campo `radicado` en RawDocModel y en el scraper de SAMAI

**Files:**
- Modify: `core/models.py`
- Modify: `core/scrapers/families/samai.py`
- Test: `tests/families/test_samai.py`

**Interfaces:**
- Consumes: nada nuevo.
- Produces: `RawDocModel.radicado: Optional[str]` — consumido por `worker/tasks.py` en la Task 4.

- [ ] **Step 1: Escribir la prueba que falla**

Agregar a `tests/families/test_samai.py` (junto a los demás tests de `_parse_row`):

```python
def test_parse_row_populates_radicado_as_digits_only():
    # El radicado real de SAMAI a veces trae guiones (ej. "25000-23-42-000-
    # 2020-00008-02" en producción); el campo normalizado siempre queda solo
    # con dígitos, sin importar cómo lo haya escrito el sitio.
    row_html = _ROW_HTML.replace("<td>25001233300020260001200</td>", "<td>25001-23-33-000-2026-00012-00</td>", 1)
    row = BeautifulSoup(row_html, "html.parser").find("tr")
    scraper = ScrapTribunales(corp_code="1100103", corp_name="Consejo de Estado")

    doc = scraper._parse_row(row, "1100103", "Consejo de Estado", "Sección Primera", "2026-06-15")

    assert doc.radicado == "25001233300020260001200"
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv/Scripts/pytest tests/families/test_samai.py -k radicado_as_digits -v`
Expected: FAIL — `AttributeError: 'RawDocModel' object has no attribute 'radicado'` (o `radicado` es `None`).

- [ ] **Step 3: Implementar**

En `core/models.py`, agregar el campo a `RawDocModel` (después de `magistrado`):

```python
    magistrado: Optional[str] = None
    # Número de radicado normalizado (solo dígitos, sin guiones/espacios) —
    # cuando el scraper lo tiene disponible en crudo (hoy solo SAMAI). Se usa
    # para detectar cuándo el mismo proceso aparece en otra fuente/tribunal,
    # nunca se muestra en la interfaz.
    radicado: Optional[str] = None
```

En `core/scrapers/families/samai.py`, en `_parse_row` (justo después de la línea `radicado = tds[1].get_text(strip=True)`), agregar:

```python
        radicado_digits = re.sub(r"\D", "", radicado)
```

Y en el `return RawDocModel(...)` al final del método, agregar el nuevo campo:

```python
            f_providencia=fecha_prov,
            save_path=path,
            radicado=radicado_digits or None,
        )
```

- [ ] **Step 4: Confirmar que pasa**

Run: `.venv/Scripts/pytest tests/families/test_samai.py -v`
Expected: todos PASSED, incluyendo el nuevo.

- [ ] **Step 5: Commit**

```bash
git add core/models.py core/scrapers/families/samai.py tests/families/test_samai.py
git commit -m "feat: samai captura el radicado normalizado de cada documento"
```

---

### Task 3: Migración — columna `radicado` y tablas de vinculación de casos

**Files:**
- Create: `alembic/versions/<generado>_add_radicado_and_case_links.py`
- Modify: `core/db/models.py`

**Interfaces:**
- Produces: `Document.radicado`, modelos `CaseLink`, `CaseLinkStage`, `CaseLinkSuggestion` — consumidos por `core/db/repository.py` (Task 5-6).

- [ ] **Step 1: Generar el archivo de migración**

Run: `.venv/Scripts/alembic revision -m "add radicado and case links"`

Esto crea `alembic/versions/<id>_add_radicado_and_case_links.py` con `down_revision = 'fc6425d9cc05'` (la cabeza actual) ya puesto automáticamente.

- [ ] **Step 2: Escribir el contenido de la migración**

Reemplazar el cuerpo de `upgrade()`/`downgrade()` del archivo generado:

```python
def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('documents', sa.Column('radicado', sa.String(), nullable=True))
    op.create_index('ix_documents_radicado', 'documents', ['radicado'])

    op.create_table(
        'case_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'case_link_stages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('case_link_id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('radicado', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['case_link_id'], ['case_links.id']),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_id', 'radicado', name='uq_case_link_stages_source_radicado'),
    )
    op.create_table(
        'case_link_suggestions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_id_a', sa.Integer(), nullable=False),
        sa.Column('radicado_a', sa.String(), nullable=False),
        sa.Column('source_id_b', sa.Integer(), nullable=False),
        sa.Column('radicado_b', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('matched_digits', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['source_id_a'], ['sources.id']),
        sa.ForeignKeyConstraint(['source_id_b'], ['sources.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'source_id_a', 'radicado_a', 'source_id_b', 'radicado_b',
            name='uq_case_link_suggestions_pair',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('case_link_suggestions')
    op.drop_table('case_link_stages')
    op.drop_table('case_links')
    op.drop_index('ix_documents_radicado', table_name='documents')
    op.drop_column('documents', 'radicado')
```

- [ ] **Step 3: Agregar los modelos ORM**

En `core/db/models.py`, agregar la columna a `Document` (después de `magistrado = Column(...)`):

```python
    magistrado = Column(String, nullable=True)
    # Radicado normalizado (solo dígitos) — solo poblado por familias que lo
    # capturan en crudo (hoy: samai). Nunca se muestra en la interfaz; existe
    # para detectar el mismo proceso en otra fuente (ver CaseLink más abajo).
    radicado = Column(String, nullable=True)
```

Y agregar al final del archivo, después de `UserSession`:

```python
class CaseLink(Base):
    __tablename__ = "case_links"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class CaseLinkStage(Base):
    __tablename__ = "case_link_stages"

    id = Column(Integer, primary_key=True)
    case_link_id = Column(Integer, ForeignKey("case_links.id"), nullable=False)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    radicado = Column(String, nullable=False)


class CaseLinkSuggestion(Base):
    __tablename__ = "case_link_suggestions"

    id = Column(Integer, primary_key=True)
    source_id_a = Column(Integer, ForeignKey("sources.id"), nullable=False)
    radicado_a = Column(String, nullable=False)
    source_id_b = Column(Integer, ForeignKey("sources.id"), nullable=False)
    radicado_b = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending", server_default="pending")
    matched_digits = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: Correr la migración contra la base de desarrollo y verificar**

Run: `.venv/Scripts/alembic upgrade head`
Expected: termina sin error; `docker exec scrapper-avanzado-postgres-1 psql -U iurisync -d iurisync -c "\d case_link_suggestions"` muestra la tabla nueva.

Run: `.venv/Scripts/alembic downgrade -1 && .venv/Scripts/alembic upgrade head`
Expected: el downgrade y el upgrade vuelven a correr sin error (confirma que `downgrade()` es simétrico).

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/ core/db/models.py
git commit -m "feat: agrega tablas de vinculación de casos y columna radicado"
```

---

### Task 4: Guardar `radicado` al insertar un documento

**Files:**
- Modify: `worker/tasks.py`
- Test: `tests/test_tasks.py`

**Interfaces:**
- Consumes: `RawDocModel.radicado` (Task 2), `Document.radicado` (Task 3).
- Produces: `Document.radicado` poblado en cada insert — consumido por `generate_case_link_suggestions_for_run` (Task 5) vía la columna misma.

- [ ] **Step 1: Escribir la prueba que falla**

Buscar el test existente para `scrape_source_task` que verifica los campos guardados (`test_scrape_source_task_downloads_new_document_and_marks_run_source_completed` en `tests/test_tasks.py`) y agregar, en el mismo archivo, un test nuevo enfocado solo en el campo `radicado`:

```python
@responses.activate
def test_scrape_source_task_stores_radicado_from_the_scraped_document(db_session, test_engine, monkeypatch):
    celery_app.conf.task_always_eager = True

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    DummyFamilyScraper.docs_to_return = [
        RawDocModel(
            source="Dummy Source",
            link={"url": "https://example.com/doc1", "method": "GET"},
            title="Documento 1",
            tipo="Auto",
            f_public="2026-01-01",
            radicado="25001233300020260001200",
        )
    ]
    responses.add(
        responses.GET,
        "https://example.com/doc1",
        body=b"contenido",
        headers={"Content-Type": "application/pdf"},
        status=200,
    )

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    scrape_source_task(run_source.id)

    assertion_session = task_session_factory()
    [document] = repository.list_documents(assertion_session, source_id=source.id)[0]
    assert document.radicado == "25001233300020260001200"
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv/Scripts/pytest tests/test_tasks.py -k stores_radicado -v`
Expected: FAIL — `AssertionError: None != '25001233300020260001200'` (el campo no se está pasando todavía).

- [ ] **Step 3: Implementar**

En `worker/tasks.py`, en la llamada a `repository.insert_document_reporting_whether_created(...)` (la que arma `title=doc.title, tipo=doc.tipo, ...`), agregar la línea `radicado=doc.radicado,` junto a `magistrado=doc.magistrado,`:

```python
                                            magistrado=doc.magistrado,
                                            radicado=doc.radicado,
                                            detalle=doc.detalle,
```

- [ ] **Step 4: Confirmar que pasa**

Run: `.venv/Scripts/pytest tests/test_tasks.py -k stores_radicado -v`
Expected: PASSED

- [ ] **Step 5: Commit**

```bash
git add worker/tasks.py tests/test_tasks.py
git commit -m "feat: guarda el radicado al insertar un documento"
```

---

### Task 5: Motor de coincidencias — generar sugerencias

**Files:**
- Modify: `core/db/repository.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: `matching_prefix_length`, `MIN_MATCH_DIGITS` (Task 1), `CaseLinkSuggestion`, `Document.radicado` (Task 3).
- Produces: `generate_case_link_suggestions_for_run(db, run_id) -> int` — consumido por `worker/tasks.py` (Task 7).

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `tests/test_repository.py`:

```python
def _make_samai_source(db_session, name):
    repository.create_source_family_if_missing(db_session, key="samai", display_name="SAMAI")
    return repository.create_source(db_session, family_key="samai", name=name, family_params={})


def test_generate_case_link_suggestions_for_run_creates_a_pending_suggestion_across_sources(db_session):
    tribunal = _make_samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _make_samai_source(db_session, "Consejo de Estado")

    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=tribunal.id)

    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, run_source_id=run_source.id,
        title="25000234200020200000801(NRD)", radicado="25000234200020200000801",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id,
        title="25000234200020200000802(NRD)", radicado="25000234200020200000802",
        storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    created = repository.generate_case_link_suggestions_for_run(db_session, run.id)

    assert created == 1
    [suggestion] = repository.list_pending_case_link_suggestions(db_session)
    assert suggestion.matched_digits == 22
    assert (suggestion.source_id_a, suggestion.radicado_a) == (tribunal.id, "25000234200020200000801")
    assert (suggestion.source_id_b, suggestion.radicado_b) == (consejo.id, "25000234200020200000802")


def test_generate_case_link_suggestions_ignores_documents_in_the_same_source(db_session):
    tribunal = _make_samai_source(db_session, "Tribunal Administrativo de Antioquia")
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=tribunal.id)

    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, run_source_id=run_source.id,
        title="t1", radicado="25000234200020200000801", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=tribunal.id, run_source_id=run_source.id,
        title="t2", radicado="25000234200020200000801", storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    created = repository.generate_case_link_suggestions_for_run(db_session, run.id)

    assert created == 0
    assert repository.list_pending_case_link_suggestions(db_session) == []


def test_generate_case_link_suggestions_does_not_duplicate_an_existing_pair(db_session):
    tribunal = _make_samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _make_samai_source(db_session, "Consejo de Estado")
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=tribunal.id)
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, run_source_id=run_source.id,
        title="t1", radicado="25000234200020200000801", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id,
        title="t2", radicado="25000234200020200000802", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    repository.generate_case_link_suggestions_for_run(db_session, run.id)

    created_again = repository.generate_case_link_suggestions_for_run(db_session, run.id)

    assert created_again == 0
    assert len(repository.list_pending_case_link_suggestions(db_session)) == 1


def test_generate_case_link_suggestions_ignores_non_samai_families(db_session):
    repository.create_source_family_if_missing(db_session, key="rama_judicial", display_name="Rama Judicial")
    juzgado = repository.create_source(db_session, family_key="rama_judicial", name="Juzgado X", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=juzgado.id)
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=juzgado.id, run_source_id=run_source.id,
        title="t1", radicado="25000234200020200000801", storage_bucket="iurisync-test", storage_key="a.pdf",
    )

    created = repository.generate_case_link_suggestions_for_run(db_session, run.id)

    assert created == 0
```

- [ ] **Step 2: Confirmar que fallan**

Run: `.venv/Scripts/pytest tests/test_repository.py -k generate_case_link_suggestions -v`
Expected: FAIL — `AttributeError: module 'core.db.repository' has no attribute 'generate_case_link_suggestions_for_run'`.

- [ ] **Step 3: Implementar**

Agregar a `core/db/repository.py` (después de `count_documents_by_title_within_family`, y agregar `CaseLink, CaseLinkStage, CaseLinkSuggestion` al import de `core.db.models` en la cabecera, y `matching_prefix_length, MIN_MATCH_DIGITS` al import de `core.utils`):

```python
def _samai_case_groups(db: Session) -> list[tuple[int, str]]:
    stmt = (
        select(Document.source_id, Document.radicado)
        .join(Source, Source.id == Document.source_id)
        .where(Source.family_key == "samai", Document.radicado.is_not(None))
        .distinct()
    )
    return list(db.execute(stmt).all())


def _create_case_link_suggestion_if_missing(
    db: Session, source_id_a: int, radicado_a: str, source_id_b: int, radicado_b: str, matched_digits: int
) -> bool:
    # Orden consistente por (source_id, radicado) para que el mismo cruce
    # nunca genere dos filas espejo (A~B y B~A) — ver spec, sección
    # "Cómo se generan las sugerencias".
    if (source_id_b, radicado_b) < (source_id_a, radicado_a):
        source_id_a, radicado_a, source_id_b, radicado_b = source_id_b, radicado_b, source_id_a, radicado_a

    exists_stmt = select(CaseLinkSuggestion.id).where(
        CaseLinkSuggestion.source_id_a == source_id_a,
        CaseLinkSuggestion.radicado_a == radicado_a,
        CaseLinkSuggestion.source_id_b == source_id_b,
        CaseLinkSuggestion.radicado_b == radicado_b,
    )
    if db.scalars(exists_stmt).first() is not None:
        return False

    db.add(CaseLinkSuggestion(
        source_id_a=source_id_a, radicado_a=radicado_a,
        source_id_b=source_id_b, radicado_b=radicado_b,
        matched_digits=matched_digits, status="pending",
    ))
    db.commit()
    return True


def generate_case_link_suggestions(db: Session, new_groups: list[tuple[int, str]]) -> int:
    """Por cada (source_id, radicado) en new_groups, compara contra TODOS los
    grupos samai existentes de una fuente distinta; crea una sugerencia
    pendiente por cada coincidencia de al menos MIN_MATCH_DIGITS dígitos
    iniciales que no exista ya. Devuelve cuántas sugerencias nuevas se
    crearon."""
    all_groups = _samai_case_groups(db)
    created = 0
    for source_id, radicado in new_groups:
        for other_source_id, other_radicado in all_groups:
            if other_source_id == source_id:
                continue
            matched = matching_prefix_length(radicado, other_radicado)
            if matched < MIN_MATCH_DIGITS:
                continue
            if _create_case_link_suggestion_if_missing(
                db, source_id, radicado, other_source_id, other_radicado, matched
            ):
                created += 1
    return created


def generate_case_link_suggestions_for_run(db: Session, run_id: int) -> int:
    """Se corre después de que un run terminó de guardar sus documentos (ver
    worker/tasks.py::_finalize_run). Solo mira las fuentes samai que
    participaron en ESTE run — el resto del archivo ya fue comparado en runs
    anteriores o en el backfill (core/backfill_samai_radicado.py)."""
    run_sources = list_run_sources(db, run_id)
    samai_source_ids = {
        rs.source_id for rs in run_sources
        if (source := db.get(Source, rs.source_id)) is not None and source.family_key == "samai"
    }
    if not samai_source_ids:
        return 0

    stmt = (
        select(Document.source_id, Document.radicado)
        .where(Document.source_id.in_(samai_source_ids), Document.radicado.is_not(None))
        .distinct()
    )
    new_groups = list(db.execute(stmt).all())
    return generate_case_link_suggestions(db, new_groups)


def list_pending_case_link_suggestions(db: Session) -> list[CaseLinkSuggestion]:
    stmt = (
        select(CaseLinkSuggestion)
        .where(CaseLinkSuggestion.status == "pending")
        .order_by(CaseLinkSuggestion.created_at.desc())
    )
    return list(db.scalars(stmt).all())
```

- [ ] **Step 4: Confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_repository.py -k generate_case_link_suggestions -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add core/db/repository.py tests/test_repository.py
git commit -m "feat: motor de coincidencias por prefijo de radicado entre fuentes samai"
```

---

### Task 6: Confirmar, descartar, vincular manualmente y consultar el expediente

**Files:**
- Modify: `core/db/repository.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: `CaseLink`, `CaseLinkStage`, `CaseLinkSuggestion` (Task 3), `list_pending_case_link_suggestions` (Task 5).
- Produces: `confirm_case_link_suggestion`, `dismiss_case_link_suggestion`, `create_manual_case_link`, `get_case_link`, `get_case_link_suggestion`, `case_group_summary`, `find_confirmed_case_link_for_document`, `find_pending_case_link_suggestion_for_document`, `get_case_link_status_for_documents`, `list_documents_by_source_and_radicado` — consumidos por `api/routers/case_links.py` (Task 9) y `api/routers/documents.py` (Task 9).

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `tests/test_repository.py`:

```python
def test_confirm_case_link_suggestion_creates_a_case_link_with_both_stages(db_session):
    tribunal = _make_samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _make_samai_source(db_session, "Consejo de Estado")
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, title="t1",
        radicado="25000234200020200000801", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id, title="t2",
        radicado="25000234200020200000802", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    repository._create_case_link_suggestion_if_missing(
        db_session, tribunal.id, "25000234200020200000801", consejo.id, "25000234200020200000802", 22
    )
    [suggestion] = repository.list_pending_case_link_suggestions(db_session)

    case_link = repository.confirm_case_link_suggestion(db_session, suggestion.id)

    assert case_link is not None
    stages = {(s.source_id, s.radicado) for s in db_session.query(repository.CaseLinkStage).all()}
    assert stages == {
        (tribunal.id, "25000234200020200000801"),
        (consejo.id, "25000234200020200000802"),
    }
    resolved = repository.get_case_link_suggestion(db_session, suggestion.id)
    assert resolved.status == "confirmed"
    assert resolved.resolved_at is not None


def test_dismiss_case_link_suggestion_marks_it_dismissed_without_creating_a_case_link(db_session):
    tribunal = _make_samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _make_samai_source(db_session, "Consejo de Estado")
    repository._create_case_link_suggestion_if_missing(
        db_session, tribunal.id, "25000234200020200000801", consejo.id, "25000234200020200000802", 22
    )
    [suggestion] = repository.list_pending_case_link_suggestions(db_session)

    result = repository.dismiss_case_link_suggestion(db_session, suggestion.id)

    assert result.status == "dismissed"
    assert repository.list_pending_case_link_suggestions(db_session) == []


def test_confirm_case_link_suggestion_returns_none_when_already_resolved(db_session):
    tribunal = _make_samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _make_samai_source(db_session, "Consejo de Estado")
    repository._create_case_link_suggestion_if_missing(
        db_session, tribunal.id, "25000234200020200000801", consejo.id, "25000234200020200000802", 22
    )
    [suggestion] = repository.list_pending_case_link_suggestions(db_session)
    repository.dismiss_case_link_suggestion(db_session, suggestion.id)

    assert repository.confirm_case_link_suggestion(db_session, suggestion.id) is None


def test_create_manual_case_link_extends_an_existing_case_link_instead_of_duplicating(db_session):
    tribunal = _make_samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _make_samai_source(db_session, "Consejo de Estado")
    tercera = _make_samai_source(db_session, "Sección Tercera")
    case_link = repository.create_manual_case_link(
        db_session, tribunal.id, "25000234200020200000801", consejo.id, "25000234200020200000802"
    )

    # Una tercera etapa del MISMO expediente (ej. una eventual revisión) se
    # suma al case_link ya existente, en vez de crear uno nuevo aparte.
    extended = repository.create_manual_case_link(
        db_session, consejo.id, "25000234200020200000802", tercera.id, "25000234200020200000899"
    )

    assert extended.id == case_link.id
    stages = repository.list_case_link_stages(db_session, case_link.id)
    assert {s.source_id for s in stages} == {tribunal.id, consejo.id, tercera.id}


def test_create_manual_case_link_merges_two_case_links_when_both_sides_already_belong_to_one(db_session):
    # Caso raro pero posible: A~B se confirmó por separado de C~D, y después
    # alguien vincula B~C manualmente al descubrir que en realidad son el
    # mismo expediente completo (A-B-C-D). Deben quedar en UN solo case_link,
    # no en dos.
    a = _make_samai_source(db_session, "Fuente A")
    b = _make_samai_source(db_session, "Fuente B")
    c = _make_samai_source(db_session, "Fuente C")
    d = _make_samai_source(db_session, "Fuente D")
    link_ab = repository.create_manual_case_link(db_session, a.id, "11111111111111111111101", b.id, "11111111111111111111102")
    link_cd = repository.create_manual_case_link(db_session, c.id, "11111111111111111111103", d.id, "11111111111111111111104")
    assert link_ab.id != link_cd.id

    merged = repository.create_manual_case_link(
        db_session, b.id, "11111111111111111111102", c.id, "11111111111111111111103"
    )

    stages = repository.list_case_link_stages(db_session, merged.id)
    assert {s.source_id for s in stages} == {a.id, b.id, c.id, d.id}
    # El case_link "perdedor" (link_cd) ya no debe tener etapas propias —
    # todas se movieron al que sobrevivió.
    remaining_ids = {link_ab.id, link_cd.id} - {merged.id}
    [orphan_id] = remaining_ids
    assert repository.list_case_link_stages(db_session, orphan_id) == []


def test_find_confirmed_case_link_for_document_returns_none_when_not_linked(db_session):
    tribunal = _make_samai_source(db_session, "Tribunal Administrativo de Antioquia")
    document = repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, title="t1",
        radicado="25000234200020200000801", storage_bucket="iurisync-test", storage_key="a.pdf",
    )

    assert repository.find_confirmed_case_link_for_document(db_session, document.id) is None


def test_get_case_link_status_for_documents_reports_pending_and_confirmed(db_session):
    tribunal = _make_samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _make_samai_source(db_session, "Consejo de Estado")
    otra = _make_samai_source(db_session, "Otra Fuente")

    pending_doc = repository.insert_document(
        db_session, doc_id="doc-p", source_id=tribunal.id, title="tp",
        radicado="25000234200020200000801", storage_bucket="iurisync-test", storage_key="p.pdf",
    )
    repository._create_case_link_suggestion_if_missing(
        db_session, tribunal.id, "25000234200020200000801", consejo.id, "25000234200020200000802", 22
    )

    confirmed_doc = repository.insert_document(
        db_session, doc_id="doc-c", source_id=otra.id, title="tc",
        radicado="99999999999999999999901", storage_bucket="iurisync-test", storage_key="c.pdf",
    )
    repository.create_manual_case_link(
        db_session, otra.id, "99999999999999999999901", consejo.id, "99999999999999999999902"
    )

    unrelated_doc = repository.insert_document(
        db_session, doc_id="doc-u", source_id=tribunal.id, title="tu",
        radicado="11111111111111111111111", storage_bucket="iurisync-test", storage_key="u.pdf",
    )

    status = repository.get_case_link_status_for_documents(
        db_session, [pending_doc.id, confirmed_doc.id, unrelated_doc.id]
    )

    assert status[pending_doc.id]["status"] == "pending"
    assert status[pending_doc.id]["other_source_name"] == "Consejo de Estado"
    assert status[confirmed_doc.id]["status"] == "confirmed"
    assert status[confirmed_doc.id]["other_source_name"] == "Consejo de Estado"
    assert unrelated_doc.id not in status
```

- [ ] **Step 2: Confirmar que fallan**

Run: `.venv/Scripts/pytest tests/test_repository.py -k "case_link_suggestion or manual_case_link or confirmed_case_link or case_link_status" -v`
Expected: FAIL — funciones no existen todavía.

- [ ] **Step 3: Implementar**

Agregar a `core/db/repository.py` (después de `list_pending_case_link_suggestions`; agregar `tuple_` al import de `sqlalchemy` en la cabecera):

```python
def get_case_link_suggestion(db: Session, suggestion_id: int) -> Optional[CaseLinkSuggestion]:
    return db.get(CaseLinkSuggestion, suggestion_id)


def _get_case_link_stage(db: Session, source_id: int, radicado: str) -> Optional[CaseLinkStage]:
    stmt = select(CaseLinkStage).where(CaseLinkStage.source_id == source_id, CaseLinkStage.radicado == radicado)
    return db.scalars(stmt).first()


def _link_case_group(db: Session, source_id_a: int, radicado_a: str, source_id_b: int, radicado_b: str) -> CaseLink:
    stage_a = _get_case_link_stage(db, source_id_a, radicado_a)
    stage_b = _get_case_link_stage(db, source_id_b, radicado_b)

    if stage_a is not None and stage_b is not None:
        if stage_a.case_link_id != stage_b.case_link_id:
            # Los dos lados ya pertenecían a expedientes distintos (ej. se
            # confirmaron por separado antes de saber que eran el mismo
            # proceso) — se funden en uno solo en vez de dejar dos.
            other_stages = db.scalars(
                select(CaseLinkStage).where(CaseLinkStage.case_link_id == stage_b.case_link_id)
            ).all()
            for stage in other_stages:
                stage.case_link_id = stage_a.case_link_id
            db.commit()
        return db.get(CaseLink, stage_a.case_link_id)

    if stage_a is not None:
        db.add(CaseLinkStage(case_link_id=stage_a.case_link_id, source_id=source_id_b, radicado=radicado_b))
        db.commit()
        return db.get(CaseLink, stage_a.case_link_id)

    if stage_b is not None:
        db.add(CaseLinkStage(case_link_id=stage_b.case_link_id, source_id=source_id_a, radicado=radicado_a))
        db.commit()
        return db.get(CaseLink, stage_b.case_link_id)

    case_link = CaseLink()
    db.add(case_link)
    db.flush()
    db.add(CaseLinkStage(case_link_id=case_link.id, source_id=source_id_a, radicado=radicado_a))
    db.add(CaseLinkStage(case_link_id=case_link.id, source_id=source_id_b, radicado=radicado_b))
    db.commit()
    db.refresh(case_link)
    return case_link


def confirm_case_link_suggestion(db: Session, suggestion_id: int) -> Optional[CaseLink]:
    suggestion = db.get(CaseLinkSuggestion, suggestion_id)
    if suggestion is None or suggestion.status != "pending":
        return None
    case_link = _link_case_group(
        db, suggestion.source_id_a, suggestion.radicado_a, suggestion.source_id_b, suggestion.radicado_b
    )
    suggestion.status = "confirmed"
    suggestion.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return case_link


def dismiss_case_link_suggestion(db: Session, suggestion_id: int) -> Optional[CaseLinkSuggestion]:
    suggestion = db.get(CaseLinkSuggestion, suggestion_id)
    if suggestion is None or suggestion.status != "pending":
        return None
    suggestion.status = "dismissed"
    suggestion.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(suggestion)
    return suggestion


def create_manual_case_link(
    db: Session, source_id_a: int, radicado_a: str, source_id_b: int, radicado_b: str
) -> CaseLink:
    return _link_case_group(db, source_id_a, radicado_a, source_id_b, radicado_b)


def get_case_link(db: Session, case_link_id: int) -> Optional[CaseLink]:
    return db.get(CaseLink, case_link_id)


def list_case_link_stages(db: Session, case_link_id: int) -> list[CaseLinkStage]:
    stmt = select(CaseLinkStage).where(CaseLinkStage.case_link_id == case_link_id)
    return list(db.scalars(stmt).all())


def list_documents_by_source_and_radicado(db: Session, source_id: int, radicado: str) -> list[Document]:
    stmt = (
        select(Document)
        .where(Document.source_id == source_id, Document.radicado == radicado)
        .order_by(Document.f_public.asc().nulls_last(), Document.id.asc())
    )
    return list(db.scalars(stmt).all())


def case_group_summary(db: Session, source_id: int, radicado: str) -> dict:
    stmt = select(
        func.count(Document.id), func.min(Document.f_public), func.max(Document.f_public)
    ).where(Document.source_id == source_id, Document.radicado == radicado)
    count, f_min, f_max = db.execute(stmt).one()
    return {"document_count": count, "f_public_min": f_min, "f_public_max": f_max}


def find_confirmed_case_link_for_document(db: Session, document_id: int) -> Optional[CaseLink]:
    document = db.get(Document, document_id)
    if document is None or document.radicado is None:
        return None
    stage = _get_case_link_stage(db, document.source_id, document.radicado)
    if stage is None:
        return None
    return db.get(CaseLink, stage.case_link_id)


def find_pending_case_link_suggestion_for_document(db: Session, document_id: int) -> Optional[CaseLinkSuggestion]:
    document = db.get(Document, document_id)
    if document is None or document.radicado is None:
        return None
    stmt = select(CaseLinkSuggestion).where(
        CaseLinkSuggestion.status == "pending",
        or_(
            and_(
                CaseLinkSuggestion.source_id_a == document.source_id,
                CaseLinkSuggestion.radicado_a == document.radicado,
            ),
            and_(
                CaseLinkSuggestion.source_id_b == document.source_id,
                CaseLinkSuggestion.radicado_b == document.radicado,
            ),
        ),
    )
    return db.scalars(stmt).first()


def get_case_link_status_for_documents(db: Session, document_ids: list[int]) -> dict[int, dict]:
    """Versión en lote de find_confirmed_case_link_for_document +
    find_pending_case_link_suggestion_for_document — usada por el listado de
    documentos (api/routers/documents.py) para no hacer 2 consultas por cada
    fila de la página (mismo patrón que count_documents_by_title_within_family
    ya usa para 'actuaciones')."""
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

    confirmed_by_pair: dict[tuple[int, str], dict] = {}
    stages = list(
        db.scalars(
            select(CaseLinkStage).where(tuple_(CaseLinkStage.source_id, CaseLinkStage.radicado).in_(pairs))
        ).all()
    )
    if stages:
        case_link_ids = {s.case_link_id for s in stages}
        all_stages = list(
            db.scalars(select(CaseLinkStage).where(CaseLinkStage.case_link_id.in_(case_link_ids))).all()
        )
        stages_by_link: dict[int, list[CaseLinkStage]] = {}
        for stage in all_stages:
            stages_by_link.setdefault(stage.case_link_id, []).append(stage)
        source_names = dict(
            db.execute(
                select(Source.id, Source.name).where(Source.id.in_({s.source_id for s in all_stages}))
            ).all()
        )
        for stage in stages:
            others = [
                s for s in stages_by_link[stage.case_link_id]
                if (s.source_id, s.radicado) != (stage.source_id, stage.radicado)
            ]
            other_label = ", ".join(sorted({source_names.get(o.source_id, "otra fuente") for o in others})) or None
            confirmed_by_pair[(stage.source_id, stage.radicado)] = {
                "status": "confirmed",
                "case_link_id": stage.case_link_id,
                "suggestion_id": None,
                "other_source_name": other_label,
            }

    remaining_pairs = pairs - set(confirmed_by_pair)
    pending_by_pair: dict[tuple[int, str], dict] = {}
    if remaining_pairs:
        suggestions = list(
            db.scalars(
                select(CaseLinkSuggestion).where(
                    CaseLinkSuggestion.status == "pending",
                    or_(
                        tuple_(CaseLinkSuggestion.source_id_a, CaseLinkSuggestion.radicado_a).in_(remaining_pairs),
                        tuple_(CaseLinkSuggestion.source_id_b, CaseLinkSuggestion.radicado_b).in_(remaining_pairs),
                    ),
                )
            ).all()
        )
        if suggestions:
            other_source_ids = {s.source_id_a for s in suggestions} | {s.source_id_b for s in suggestions}
            source_names = dict(
                db.execute(select(Source.id, Source.name).where(Source.id.in_(other_source_ids))).all()
            )
            for s in suggestions:
                pair_a, pair_b = (s.source_id_a, s.radicado_a), (s.source_id_b, s.radicado_b)
                if pair_a in remaining_pairs:
                    pending_by_pair[pair_a] = {
                        "status": "pending", "case_link_id": None, "suggestion_id": s.id,
                        "other_source_name": source_names.get(s.source_id_b),
                    }
                if pair_b in remaining_pairs:
                    pending_by_pair[pair_b] = {
                        "status": "pending", "case_link_id": None, "suggestion_id": s.id,
                        "other_source_name": source_names.get(s.source_id_a),
                    }

    result: dict[int, dict] = {}
    for d in docs:
        info = confirmed_by_pair.get((d.source_id, d.radicado)) or pending_by_pair.get((d.source_id, d.radicado))
        if info:
            result[d.id] = info
    return result
```

También agregar `tuple_` a la línea de import de sqlalchemy (`from sqlalchemy import and_, cast, delete, exists, func, or_, select, tuple_, update`).

- [ ] **Step 4: Confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_repository.py -v`
Expected: todos PASSED (incluye los de tasks anteriores, sin regresiones).

- [ ] **Step 5: Commit**

```bash
git add core/db/repository.py tests/test_repository.py
git commit -m "feat: confirmar/descartar/vincular manualmente expedientes entre tribunales"
```

---

### Task 7: Disparar la generación de sugerencias al terminar un run

**Files:**
- Modify: `worker/tasks.py`
- Test: `tests/test_tasks.py`

**Interfaces:**
- Consumes: `repository.generate_case_link_suggestions_for_run` (Task 5).

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `tests/test_tasks.py`:

```python
def test_finalize_run_triggers_case_link_suggestion_generation(db_session, test_engine, monkeypatch):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(db_session, family_key="samai", name="Tribunal X", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)

    calls = []
    monkeypatch.setattr(
        "worker.tasks.repository.generate_case_link_suggestions_for_run",
        lambda db, run_id: calls.append(run_id) or 0,
    )

    tasks_module._finalize_run(run.id)

    assert calls == [run.id]


def test_finalize_run_still_completes_when_suggestion_generation_fails(db_session, test_engine, monkeypatch):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(db_session, family_key="samai", name="Tribunal X", family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    repository.create_run_source(db_session, run_id=run.id, source_id=source.id)

    task_session_factory = sessionmaker(bind=test_engine, future=True)
    monkeypatch.setattr("worker.tasks.SessionLocal", task_session_factory)

    def _boom(db, run_id):
        raise RuntimeError("fallo simulado")

    monkeypatch.setattr("worker.tasks.repository.generate_case_link_suggestions_for_run", _boom)

    tasks_module._finalize_run(run.id)

    assertion_session = task_session_factory()
    assert repository.get_run(assertion_session, run.id).status == "completed"
```

- [ ] **Step 2: Confirmar que fallan**

Run: `.venv/Scripts/pytest tests/test_tasks.py -k case_link_suggestion_generation -v`
Expected: el primer test falla porque `generate_case_link_suggestions_for_run` nunca se llama (`calls == []`); el segundo falla porque la excepción simulada se propaga y el run no llega a "completed".

- [ ] **Step 3: Implementar**

En `worker/tasks.py`, modificar `_finalize_run` (agregar el bloque justo antes de `repository.set_run_status(db, run_id, status, ...)`, dentro del mismo `try`):

```python
def _finalize_run(run_id: int):
    db = SessionLocal()
    try:
        run = repository.get_run(db, run_id)
        run_sources = repository.list_run_sources(db, run_id)
        if run is not None and run.cancel_requested:
            status = "cancelled"
        elif any(rs.status == "failed" for rs in run_sources):
            status = "failed"
        else:
            status = "completed"

        # Corre después de que los documentos del run ya están guardados —
        # un fallo aquí (ej. un problema de datos inesperado) no debe
        # impedir que el run se marque como terminado; solo se pierde esta
        # ronda de sugerencias, que el próximo run o el backfill manual
        # puede volver a generar.
        try:
            repository.generate_case_link_suggestions_for_run(db, run_id)
        except Exception:
            logger.exception("Falló la generación de sugerencias de casos relacionados para el run %s", run_id)

        repository.set_run_status(db, run_id, status, finished_at=datetime.now(timezone.utc))
    finally:
        db.close()
```

Confirmar que `worker/tasks.py` ya tiene `logger = logging.getLogger(__name__)` (si no existe, agregarlo junto a los demás imports del módulo).

- [ ] **Step 4: Confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_tasks.py -k case_link_suggestion_generation -v`
Expected: 2 PASSED

Run: `.venv/Scripts/pytest tests/test_tasks.py -v`
Expected: todos PASSED (sin regresiones).

- [ ] **Step 5: Commit**

```bash
git add worker/tasks.py tests/test_tasks.py
git commit -m "feat: genera sugerencias de casos relacionados al terminar un run"
```

---

### Task 8: Schemas de la API

**Files:**
- Modify: `api/schemas.py`

**Interfaces:**
- Produces: `CaseGroupOut`, `CaseLinkSuggestionOut`, `CaseLinkStageOut`, `CaseLinkOut`, `ManualCaseLinkCreate`, `CaseLinkStageDocumentOut`; extensión de `DocumentOut` — consumidos por `api/routers/case_links.py` y `api/routers/documents.py` (Task 9).

No lleva TDD propio (son solo definiciones de datos, sin lógica) — se verifica indirectamente por los tests de la Task 9.

- [ ] **Step 1: Agregar los schemas**

En `api/schemas.py`, extender `DocumentOut` (agregar después de `case_document_count: Optional[int] = None`):

```python
    case_link_status: Optional[Literal["pending", "confirmed"]] = None
    case_link_id: Optional[int] = None
    case_link_suggestion_id: Optional[int] = None
    case_link_other_source_name: Optional[str] = None
```

Y agregar al final del archivo:

```python
class CaseGroupOut(BaseModel):
    source_id: int
    source_name: str
    radicado: str
    document_count: int
    f_public_min: Optional[date] = None
    f_public_max: Optional[date] = None


class CaseLinkSuggestionOut(BaseModel):
    id: int
    matched_digits: int
    status: str
    created_at: datetime
    case_a: CaseGroupOut
    case_b: CaseGroupOut


class CaseLinkStageDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    f_public: Optional[date] = None
    f_providencia: Optional[date] = None


class CaseLinkStageOut(BaseModel):
    source_id: int
    source_name: str
    radicado: str
    f_public_min: Optional[date] = None
    f_public_max: Optional[date] = None
    documents: list[CaseLinkStageDocumentOut]


class CaseLinkOut(BaseModel):
    id: int
    stages: list[CaseLinkStageOut]


class ManualCaseLinkCreate(BaseModel):
    source_id_a: int
    radicado_a: str = Field(min_length=1)
    source_id_b: int
    radicado_b: str = Field(min_length=1)
```

- [ ] **Step 2: Commit**

```bash
git add api/schemas.py
git commit -m "feat: schemas de la API para vinculación de casos"
```

---

### Task 9: Endpoints de la API

**Files:**
- Create: `api/routers/case_links.py`
- Modify: `api/main.py`
- Modify: `api/routers/documents.py`
- Test: `tests/test_api_case_links.py`
- Test: `tests/test_api_documents.py`

**Interfaces:**
- Consumes: todo lo de las Tasks 5, 6, 8.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_api_case_links.py`:

```python
from core.db import repository


def _samai_source(db_session, name):
    repository.create_source_family_if_missing(db_session, key="samai", display_name="SAMAI")
    return repository.create_source(db_session, family_key="samai", name=name, family_params={})


def test_list_pending_suggestions_returns_case_group_context(api_client, db_session, auth_header):
    tribunal = _samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _samai_source(db_session, "Consejo de Estado")
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, title="t1",
        radicado="25000234200020200000801", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id, title="t2",
        radicado="25000234200020200000802", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    repository._create_case_link_suggestion_if_missing(
        db_session, tribunal.id, "25000234200020200000801", consejo.id, "25000234200020200000802", 22
    )

    response = api_client.get("/case-link-suggestions", headers=auth_header)

    assert response.status_code == 200
    [suggestion] = response.json()
    assert suggestion["matched_digits"] == 22
    assert {suggestion["case_a"]["source_name"], suggestion["case_b"]["source_name"]} == {
        "Tribunal Administrativo de Antioquia", "Consejo de Estado",
    }
    assert suggestion["case_a"]["document_count"] == 1


def test_confirm_suggestion_returns_404_when_not_found(api_client, auth_header):
    response = api_client.post("/case-link-suggestions/999/confirm", headers=auth_header)
    assert response.status_code == 404


def test_confirm_then_get_case_link_shows_both_stages(api_client, db_session, auth_header):
    tribunal = _samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _samai_source(db_session, "Consejo de Estado")
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, title="t1",
        radicado="25000234200020200000801", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id, title="t2",
        radicado="25000234200020200000802", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    repository._create_case_link_suggestion_if_missing(
        db_session, tribunal.id, "25000234200020200000801", consejo.id, "25000234200020200000802", 22
    )
    [suggestion] = repository.list_pending_case_link_suggestions(db_session)

    confirm_response = api_client.post(f"/case-link-suggestions/{suggestion.id}/confirm", headers=auth_header)
    assert confirm_response.status_code == 200
    case_link_id = confirm_response.json()["id"]

    get_response = api_client.get(f"/case-links/{case_link_id}", headers=auth_header)
    assert get_response.status_code == 200
    stages = get_response.json()["stages"]
    assert len(stages) == 2
    assert {s["source_name"] for s in stages} == {"Tribunal Administrativo de Antioquia", "Consejo de Estado"}
    assert all(len(s["documents"]) == 1 for s in stages)


def test_dismiss_suggestion_removes_it_from_the_pending_list(api_client, db_session, auth_header):
    tribunal = _samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _samai_source(db_session, "Consejo de Estado")
    repository._create_case_link_suggestion_if_missing(
        db_session, tribunal.id, "25000234200020200000801", consejo.id, "25000234200020200000802", 22
    )
    [suggestion] = repository.list_pending_case_link_suggestions(db_session)

    response = api_client.post(f"/case-link-suggestions/{suggestion.id}/dismiss", headers=auth_header)

    assert response.status_code == 200
    assert api_client.get("/case-link-suggestions", headers=auth_header).json() == []


def test_create_manual_case_link(api_client, db_session, auth_header):
    tribunal = _samai_source(db_session, "Tribunal Administrativo de Antioquia")
    consejo = _samai_source(db_session, "Consejo de Estado")
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, title="t1",
        radicado="11111111111111111111101", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id, title="t2",
        radicado="11111111111111111111102", storage_bucket="iurisync-test", storage_key="b.pdf",
    )

    response = api_client.post(
        "/case-links",
        headers=auth_header,
        json={
            "source_id_a": tribunal.id, "radicado_a": "11111111111111111111101",
            "source_id_b": consejo.id, "radicado_b": "11111111111111111111102",
        },
    )

    assert response.status_code == 200
    assert len(response.json()["stages"]) == 2
```

Agregar a `tests/test_api_documents.py`:

```python
def test_get_documents_includes_pending_case_link_note(api_client, db_session, auth_header):
    repository.create_source_family_if_missing(db_session, key="samai", display_name="SAMAI")
    tribunal = repository.create_source(db_session, family_key="samai", name="Tribunal Administrativo de Antioquia", family_params={})
    consejo = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
    repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id, title="t1",
        radicado="25000234200020200000801", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id, title="t2",
        radicado="25000234200020200000802", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    repository._create_case_link_suggestion_if_missing(
        db_session, tribunal.id, "25000234200020200000801", consejo.id, "25000234200020200000802", 22
    )

    response = api_client.get("/documents", headers=auth_header)

    by_radicado = {d["source_id"]: d for d in response.json()["items"]}
    assert by_radicado[tribunal.id]["case_link_status"] == "pending"
    assert by_radicado[tribunal.id]["case_link_other_source_name"] == "Consejo de Estado"
```

(Revisa el import al inicio de `tests/test_api_documents.py` — si `repository` no está importado todavía en ese archivo, agregar `from core.db import repository`.)

- [ ] **Step 2: Confirmar que fallan**

Run: `.venv/Scripts/pytest tests/test_api_case_links.py tests/test_api_documents.py -k "case_link" -v`
Expected: FAIL — `404 Not Found` (el router no existe todavía) / `KeyError: 'case_link_status'`.

- [ ] **Step 3: Implementar**

Crear `api/routers/case_links.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_db, require_session
from api.schemas import (
    CaseGroupOut,
    CaseLinkOut,
    CaseLinkStageDocumentOut,
    CaseLinkStageOut,
    CaseLinkSuggestionOut,
    ManualCaseLinkCreate,
)
from core.db import repository

router = APIRouter(dependencies=[Depends(require_session)])


def _case_group_out(db: Session, source_id: int, radicado: str) -> CaseGroupOut:
    source = repository.get_source(db, source_id)
    summary = repository.case_group_summary(db, source_id, radicado)
    return CaseGroupOut(
        source_id=source_id,
        source_name=source.name if source else "Fuente eliminada",
        radicado=radicado,
        **summary,
    )


def _case_link_out(db: Session, case_link_id: int) -> CaseLinkOut:
    stages = repository.list_case_link_stages(db, case_link_id)
    stage_outs = []
    for stage in stages:
        source = repository.get_source(db, stage.source_id)
        summary = repository.case_group_summary(db, stage.source_id, stage.radicado)
        documents = repository.list_documents_by_source_and_radicado(db, stage.source_id, stage.radicado)
        stage_outs.append(
            CaseLinkStageOut(
                source_id=stage.source_id,
                source_name=source.name if source else "Fuente eliminada",
                radicado=stage.radicado,
                f_public_min=summary["f_public_min"],
                f_public_max=summary["f_public_max"],
                documents=[CaseLinkStageDocumentOut.model_validate(d) for d in documents],
            )
        )
    return CaseLinkOut(id=case_link_id, stages=stage_outs)


@router.get("/case-link-suggestions", response_model=list[CaseLinkSuggestionOut])
def list_pending_case_link_suggestions(db: Session = Depends(get_db)):
    suggestions = repository.list_pending_case_link_suggestions(db)
    return [
        CaseLinkSuggestionOut(
            id=s.id,
            matched_digits=s.matched_digits,
            status=s.status,
            created_at=s.created_at,
            case_a=_case_group_out(db, s.source_id_a, s.radicado_a),
            case_b=_case_group_out(db, s.source_id_b, s.radicado_b),
        )
        for s in suggestions
    ]


@router.post("/case-link-suggestions/{suggestion_id}/confirm", response_model=CaseLinkOut)
def confirm_case_link_suggestion(suggestion_id: int, db: Session = Depends(get_db)):
    case_link = repository.confirm_case_link_suggestion(db, suggestion_id)
    if case_link is None:
        raise HTTPException(status_code=404, detail="Sugerencia no encontrada o ya resuelta")
    return _case_link_out(db, case_link.id)


@router.post("/case-link-suggestions/{suggestion_id}/dismiss")
def dismiss_case_link_suggestion(suggestion_id: int, db: Session = Depends(get_db)):
    suggestion = repository.dismiss_case_link_suggestion(db, suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Sugerencia no encontrada o ya resuelta")
    return {"status": suggestion.status}


@router.post("/case-links", response_model=CaseLinkOut)
def create_manual_case_link(payload: ManualCaseLinkCreate, db: Session = Depends(get_db)):
    case_link = repository.create_manual_case_link(
        db, payload.source_id_a, payload.radicado_a, payload.source_id_b, payload.radicado_b
    )
    return _case_link_out(db, case_link.id)


@router.get("/case-links/{case_link_id}", response_model=CaseLinkOut)
def get_case_link(case_link_id: int, db: Session = Depends(get_db)):
    if repository.get_case_link(db, case_link_id) is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    return _case_link_out(db, case_link_id)
```

Registrar en `api/main.py`:

```python
from api.routers import auth, bulk_downloads, case_links, documents, health, runs, sources
```

```python
app.include_router(case_links.router)
```

En `api/routers/documents.py`, dentro de `get_documents` (después del bloque que arma `counts`/`case_document_count`, justo antes del `return`), agregar:

```python
    case_link_status = repository.get_case_link_status_for_documents(db, [d.id for d in items])
    for d in items:
        info = case_link_status.get(d.id)
        if info:
            d.case_link_status = info["status"]
            d.case_link_id = info["case_link_id"]
            d.case_link_suggestion_id = info["suggestion_id"]
            d.case_link_other_source_name = info["other_source_name"]
```

Y en `get_document` (documento único), agregar antes del `return document`:

```python
    info = repository.get_case_link_status_for_documents(db, [document.id]).get(document.id)
    if info:
        document.case_link_status = info["status"]
        document.case_link_id = info["case_link_id"]
        document.case_link_suggestion_id = info["suggestion_id"]
        document.case_link_other_source_name = info["other_source_name"]
```

- [ ] **Step 4: Confirmar que pasan**

Run: `.venv/Scripts/pytest tests/test_api_case_links.py tests/test_api_documents.py -v`
Expected: todos PASSED

Run: `.venv/Scripts/pytest -v`
Expected: toda la suite de backend PASSED (sin regresiones).

- [ ] **Step 5: Commit**

```bash
git add api/routers/case_links.py api/main.py api/routers/documents.py tests/test_api_case_links.py tests/test_api_documents.py
git commit -m "feat: endpoints de la API para vinculación de casos"
```

---

### Task 10: Script de una sola corrida para los datos existentes

**Files:**
- Create: `core/backfill_samai_radicado.py`
- Test: `tests/test_backfill_samai_radicado.py`

**Interfaces:**
- Consumes: `is_samai_case_title` (existente en `core/utils.py`), `generate_case_link_suggestions` (Task 5).

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_backfill_samai_radicado.py`:

```python
from core.backfill_samai_radicado import backfill
from core.db import repository


def test_backfill_populates_radicado_and_generates_suggestions(db_session):
    repository.create_source_family_if_missing(db_session, key="samai", display_name="SAMAI")
    tribunal = repository.create_source(db_session, family_key="samai", name="Tribunal Administrativo de Antioquia", family_params={})
    consejo = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
    doc_a = repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id,
        title="25000234200020200000801(NRD)", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    doc_b = repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id,
        title="25000234200020200000802(NRD)", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    # Título que NO tiene forma de caso (respaldo del scraper) — no debe
    # producir un radicado ni participar en la comparación.
    doc_c = repository.insert_document(
        db_session, doc_id="doc-c", source_id=tribunal.id,
        title="DR. WILLIAM SANTA MARIN", storage_bucket="iurisync-test", storage_key="c.pdf",
    )

    result = backfill(db_session)

    db_session.refresh(doc_a)
    db_session.refresh(doc_b)
    db_session.refresh(doc_c)
    assert doc_a.radicado == "25000234200020200000801"
    assert doc_b.radicado == "25000234200020200000802"
    assert doc_c.radicado is None
    assert result["documents_updated"] == 2
    assert result["suggestions_created"] == 1
    assert len(repository.list_pending_case_link_suggestions(db_session)) == 1
```

- [ ] **Step 2: Confirmar que falla**

Run: `.venv/Scripts/pytest tests/test_backfill_samai_radicado.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.backfill_samai_radicado'`.

- [ ] **Step 3: Implementar**

Crear `core/backfill_samai_radicado.py`:

```python
"""Corrida única: pobla Document.radicado para los documentos de SAMAI que ya
existen (capturados antes de que el scraper guardara el campo) y genera las
sugerencias de casos relacionados sobre todo ese histórico de una vez — ver
docs/superpowers/specs/2026-07-29-vinculacion-casos-samai-design.md, sección
"Datos existentes (backfill)".

Uso: .venv/Scripts/python -m core.backfill_samai_radicado
Se puede correr más de una vez sin problema: los documentos que ya tienen
radicado se dejan tal cual, y generate_case_link_suggestions no duplica
sugerencias ya existentes.
"""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import repository
from core.db.models import Document, Source
from core.db.session import SessionLocal
from core.utils import is_samai_case_title

_RADICADO_FROM_TITLE = re.compile(r"^(\d+)\(")


def backfill(db: Session) -> dict:
    stmt = (
        select(Document)
        .join(Source, Source.id == Document.source_id)
        .where(Source.family_key == "samai", Document.radicado.is_(None))
    )
    documents_updated = 0
    for document in db.scalars(stmt).all():
        if not is_samai_case_title(document.title):
            continue
        match = _RADICADO_FROM_TITLE.match(document.title)
        if not match:
            continue
        document.radicado = match.group(1)
        documents_updated += 1
    db.commit()

    stmt = (
        select(Document.source_id, Document.radicado)
        .join(Source, Source.id == Document.source_id)
        .where(Source.family_key == "samai", Document.radicado.is_not(None))
        .distinct()
    )
    all_groups = list(db.execute(stmt).all())
    suggestions_created = repository.generate_case_link_suggestions(db, all_groups)

    return {"documents_updated": documents_updated, "suggestions_created": suggestions_created}


def main():
    db = SessionLocal()
    try:
        result = backfill(db)
        print(f"Documentos actualizados: {result['documents_updated']}")
        print(f"Sugerencias nuevas: {result['suggestions_created']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Confirmar que pasa**

Run: `.venv/Scripts/pytest tests/test_backfill_samai_radicado.py -v`
Expected: PASSED

- [ ] **Step 5: Commit**

```bash
git add core/backfill_samai_radicado.py tests/test_backfill_samai_radicado.py
git commit -m "feat: script de una sola corrida para poblar radicado en documentos existentes"
```

---

### Task 11: Cliente de API y tipos del frontend

**Files:**
- Create: `frontend/src/api/caseLinks.ts`
- Test: `frontend/src/api/caseLinks.test.ts`
- Modify: `frontend/src/api/types.ts`

**Interfaces:**
- Produces: `CaseGroup`, `CaseLinkSuggestion`, `CaseLinkStage`, `CaseLink`, tipo `Document` extendido; `fetchCaseLinkSuggestions`, `confirmCaseLinkSuggestion`, `dismissCaseLinkSuggestion`, `createManualCaseLink`, `fetchCaseLink` — consumidos por `CaseLinksPage.tsx`, `CaseLinkDetailPage.tsx`, `DocumentsPage.tsx` (Tasks 12-14).

- [ ] **Step 1: Escribir las pruebas que fallan**

Ver el patrón de test existente en `frontend/src/api/bulkDownloads.test.ts` y seguirlo. Crear `frontend/src/api/caseLinks.test.ts`:

```typescript
import { describe, expect, it, vi, beforeEach } from "vitest";
import * as client from "./client";
import {
  confirmCaseLinkSuggestion,
  createManualCaseLink,
  dismissCaseLinkSuggestion,
  fetchCaseLink,
  fetchCaseLinkSuggestions,
} from "./caseLinks";

vi.mock("./client", async () => {
  const actual = await vi.importActual<typeof client>("./client");
  return { ...actual, apiFetch: vi.fn() };
});

describe("caseLinks api", () => {
  beforeEach(() => {
    vi.mocked(client.apiFetch).mockReset();
  });

  it("fetches pending suggestions", async () => {
    vi.mocked(client.apiFetch).mockResolvedValue([]);
    await fetchCaseLinkSuggestions();
    expect(client.apiFetch).toHaveBeenCalledWith("/case-link-suggestions");
  });

  it("confirms a suggestion", async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({ id: 1, stages: [] });
    await confirmCaseLinkSuggestion(7);
    expect(client.apiFetch).toHaveBeenCalledWith("/case-link-suggestions/7/confirm", { method: "POST" });
  });

  it("dismisses a suggestion", async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({ status: "dismissed" });
    await dismissCaseLinkSuggestion(7);
    expect(client.apiFetch).toHaveBeenCalledWith("/case-link-suggestions/7/dismiss", { method: "POST" });
  });

  it("creates a manual link", async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({ id: 1, stages: [] });
    await createManualCaseLink({ source_id_a: 1, radicado_a: "a", source_id_b: 2, radicado_b: "b" });
    expect(client.apiFetch).toHaveBeenCalledWith("/case-links", {
      method: "POST",
      body: JSON.stringify({ source_id_a: 1, radicado_a: "a", source_id_b: 2, radicado_b: "b" }),
    });
  });

  it("fetches a case link by id", async () => {
    vi.mocked(client.apiFetch).mockResolvedValue({ id: 1, stages: [] });
    await fetchCaseLink(1);
    expect(client.apiFetch).toHaveBeenCalledWith("/case-links/1");
  });
});
```

- [ ] **Step 2: Confirmar que fallan**

Run: `cd frontend && npm test -- --run caseLinks`
Expected: FAIL — `Cannot find module './caseLinks'`.

- [ ] **Step 3: Implementar**

Agregar a `frontend/src/api/types.ts` (después de `PaginatedDocuments`), y extender `Document`:

```typescript
export interface CaseGroup {
  source_id: number;
  source_name: string;
  radicado: string;
  document_count: number;
  f_public_min: string | null;
  f_public_max: string | null;
}

export interface CaseLinkSuggestion {
  id: number;
  matched_digits: number;
  status: string;
  created_at: string;
  case_a: CaseGroup;
  case_b: CaseGroup;
}

export interface CaseLinkStageDocument {
  id: number;
  title: string;
  f_public: string | null;
  f_providencia: string | null;
}

export interface CaseLinkStage {
  source_id: number;
  source_name: string;
  radicado: string;
  f_public_min: string | null;
  f_public_max: string | null;
  documents: CaseLinkStageDocument[];
}

export interface CaseLink {
  id: number;
  stages: CaseLinkStage[];
}

export interface ManualCaseLinkInput {
  source_id_a: number;
  radicado_a: string;
  source_id_b: number;
  radicado_b: string;
}
```

Y en `Document`, agregar (junto a `case_document_count`):

```typescript
  case_link_status?: "pending" | "confirmed" | null;
  case_link_id?: number | null;
  case_link_suggestion_id?: number | null;
  case_link_other_source_name?: string | null;
```

Crear `frontend/src/api/caseLinks.ts`:

```typescript
import { apiFetch } from "./client";
import type { CaseLink, CaseLinkSuggestion, ManualCaseLinkInput } from "./types";

export function fetchCaseLinkSuggestions(): Promise<CaseLinkSuggestion[]> {
  return apiFetch<CaseLinkSuggestion[]>("/case-link-suggestions");
}

export function confirmCaseLinkSuggestion(suggestionId: number): Promise<CaseLink> {
  return apiFetch<CaseLink>(`/case-link-suggestions/${suggestionId}/confirm`, { method: "POST" });
}

export function dismissCaseLinkSuggestion(suggestionId: number): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(`/case-link-suggestions/${suggestionId}/dismiss`, { method: "POST" });
}

export function createManualCaseLink(input: ManualCaseLinkInput): Promise<CaseLink> {
  return apiFetch<CaseLink>("/case-links", { method: "POST", body: JSON.stringify(input) });
}

export function fetchCaseLink(id: number): Promise<CaseLink> {
  return apiFetch<CaseLink>(`/case-links/${id}`);
}
```

- [ ] **Step 4: Confirmar que pasan**

Run: `cd frontend && npm test -- --run caseLinks`
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/caseLinks.ts frontend/src/api/caseLinks.test.ts frontend/src/api/types.ts
git commit -m "feat: cliente de API para vinculación de casos"
```

---

### Task 12: Página "Casos por confirmar" (bandeja)

**Files:**
- Create: `frontend/src/pages/CaseLinksPage.tsx`
- Test: `frontend/src/pages/CaseLinksPage.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`

**Interfaces:**
- Consumes: `fetchCaseLinkSuggestions`, `confirmCaseLinkSuggestion`, `dismissCaseLinkSuggestion`, `createManualCaseLink` (Task 11).

- [ ] **Step 1: Escribir las pruebas que fallan**

Ver el patrón en `frontend/src/pages/BulkDownloadsPage.test.tsx` y seguirlo (render con `QueryClientProvider` + `MemoryRouter`, mock del módulo de API). Crear `frontend/src/pages/CaseLinksPage.test.tsx`:

```typescript
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { CaseLinksPage } from "./CaseLinksPage";
import * as caseLinksApi from "../api/caseLinks";

vi.mock("../api/caseLinks");

const SUGGESTION = {
  id: 1,
  matched_digits: 22,
  status: "pending",
  created_at: "2026-07-29T00:00:00Z",
  case_a: {
    source_id: 1, source_name: "Tribunal Administrativo de Antioquia", radicado: "25000234200020200000801",
    document_count: 2, f_public_min: "2023-01-01", f_public_max: "2023-06-01",
  },
  case_b: {
    source_id: 2, source_name: "Consejo de Estado", radicado: "25000234200020200000802",
    document_count: 1, f_public_min: "2024-11-01", f_public_max: "2024-11-01",
  },
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CaseLinksPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("CaseLinksPage", () => {
  beforeEach(() => {
    vi.mocked(caseLinksApi.fetchCaseLinkSuggestions).mockResolvedValue([SUGGESTION]);
  });

  it("lists pending suggestions with both tribunals", async () => {
    renderPage();
    expect(await screen.findByText("Tribunal Administrativo de Antioquia")).toBeInTheDocument();
    expect(screen.getByText("Consejo de Estado")).toBeInTheDocument();
    expect(screen.getByText(/22 dígitos/)).toBeInTheDocument();
  });

  it("confirms a suggestion and removes it from the list", async () => {
    vi.mocked(caseLinksApi.confirmCaseLinkSuggestion).mockResolvedValue({ id: 5, stages: [] });
    renderPage();
    await screen.findByText("Tribunal Administrativo de Antioquia");

    await userEvent.click(screen.getByRole("button", { name: "Confirmar" }));

    await waitFor(() => expect(caseLinksApi.confirmCaseLinkSuggestion).toHaveBeenCalledWith(1));
  });

  it("dismisses a suggestion", async () => {
    vi.mocked(caseLinksApi.dismissCaseLinkSuggestion).mockResolvedValue({ status: "dismissed" });
    renderPage();
    await screen.findByText("Tribunal Administrativo de Antioquia");

    await userEvent.click(screen.getByRole("button", { name: "Descartar" }));

    await waitFor(() => expect(caseLinksApi.dismissCaseLinkSuggestion).toHaveBeenCalledWith(1));
  });

  it("shows an empty state when there are no pending suggestions", async () => {
    vi.mocked(caseLinksApi.fetchCaseLinkSuggestions).mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText(/no hay casos pendientes/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Confirmar que fallan**

Run: `cd frontend && npm test -- --run CaseLinksPage`
Expected: FAIL — `Cannot find module './CaseLinksPage'`.

- [ ] **Step 3: Implementar**

Crear `frontend/src/pages/CaseLinksPage.tsx`:

```tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitMerge } from "lucide-react";
import {
  confirmCaseLinkSuggestion,
  createManualCaseLink,
  dismissCaseLinkSuggestion,
  fetchCaseLinkSuggestions,
} from "../api/caseLinks";
import type { CaseGroup } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { ErrorBanner } from "../components/ErrorBanner";
import { Button } from "../components/ui/button";
import { formatDate } from "../lib/formatters";

function CaseSide({ group }: { group: CaseGroup }) {
  return (
    <div>
      <p className="font-medium text-foreground">{group.source_name}</p>
      <p className="text-xs text-muted-foreground">
        {group.document_count} documento{group.document_count === 1 ? "" : "s"}
        {group.f_public_min && ` · ${formatDate(group.f_public_min)} – ${formatDate(group.f_public_max ?? group.f_public_min)}`}
      </p>
    </div>
  );
}

export function CaseLinksPage() {
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);

  const suggestionsQuery = useQuery({
    queryKey: ["case-link-suggestions"],
    queryFn: fetchCaseLinkSuggestions,
  });

  const confirmMutation = useMutation({
    mutationFn: confirmCaseLinkSuggestion,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["case-link-suggestions"] }),
    onError: () => setActionError("No se pudo confirmar la sugerencia. Intenta de nuevo."),
  });

  const dismissMutation = useMutation({
    mutationFn: dismissCaseLinkSuggestion,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["case-link-suggestions"] }),
    onError: () => setActionError("No se pudo descartar la sugerencia. Intenta de nuevo."),
  });

  return (
    <div className="space-y-6">
      <div>
        <p className="flex items-center gap-1.5 text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">
          <GitMerge className="size-3.5" aria-hidden="true" />
          Casos por confirmar
        </p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">
          ¿Es el mismo caso?
        </h1>
      </div>

      {suggestionsQuery.isError && (
        <ErrorBanner message="No se pudieron cargar las sugerencias." onRetry={() => suggestionsQuery.refetch()} />
      )}
      {actionError && <ErrorBanner message={actionError} />}

      {!suggestionsQuery.isLoading && (suggestionsQuery.data?.length ?? 0) === 0 && !suggestionsQuery.isError && (
        <EmptyState message="No hay casos pendientes por confirmar." />
      )}

      <div className="space-y-3">
        {suggestionsQuery.data?.map((suggestion) => (
          <div key={suggestion.id} className="rounded-lg border border-border bg-card p-4">
            <div className="flex items-center justify-between gap-4">
              <div className="grid flex-1 grid-cols-2 gap-4">
                <CaseSide group={suggestion.case_a} />
                <CaseSide group={suggestion.case_b} />
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span className="text-xs text-muted-foreground">{suggestion.matched_digits} dígitos en común</span>
                <Button
                  size="sm"
                  onClick={() => confirmMutation.mutate(suggestion.id)}
                  disabled={confirmMutation.isPending}
                >
                  Confirmar
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => dismissMutation.mutate(suggestion.id)}
                  disabled={dismissMutation.isPending}
                >
                  Descartar
                </Button>
              </div>
            </div>
          </div>
        ))}
      </div>

      <ManualLinkForm onError={setActionError} />
    </div>
  );
}

function ManualLinkForm({ onError }: { onError: (message: string | null) => void }) {
  const queryClient = useQueryClient();
  const [sourceIdA, setSourceIdA] = useState("");
  const [radicadoA, setRadicadoA] = useState("");
  const [sourceIdB, setSourceIdB] = useState("");
  const [radicadoB, setRadicadoB] = useState("");

  const manualLinkMutation = useMutation({
    mutationFn: createManualCaseLink,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["case-link-suggestions"] });
      setSourceIdA("");
      setRadicadoA("");
      setSourceIdB("");
      setRadicadoB("");
      onError(null);
    },
    onError: () => onError("No se pudo vincular manualmente. Verifica los datos."),
  });

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    manualLinkMutation.mutate({
      source_id_a: Number(sourceIdA),
      radicado_a: radicadoA,
      source_id_b: Number(sourceIdB),
      radicado_b: radicadoB,
    });
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-lg border border-dashed border-border p-4">
      <p className="mb-3 text-sm font-medium text-foreground">Vincular manualmente</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <input
          className="rounded-md border border-input px-2 py-1 text-sm"
          placeholder="ID fuente A"
          value={sourceIdA}
          onChange={(e) => setSourceIdA(e.target.value)}
        />
        <input
          className="rounded-md border border-input px-2 py-1 text-sm"
          placeholder="Radicado A"
          value={radicadoA}
          onChange={(e) => setRadicadoA(e.target.value)}
        />
        <input
          className="rounded-md border border-input px-2 py-1 text-sm"
          placeholder="ID fuente B"
          value={sourceIdB}
          onChange={(e) => setSourceIdB(e.target.value)}
        />
        <input
          className="rounded-md border border-input px-2 py-1 text-sm"
          placeholder="Radicado B"
          value={radicadoB}
          onChange={(e) => setRadicadoB(e.target.value)}
        />
      </div>
      <Button type="submit" size="sm" className="mt-3" disabled={manualLinkMutation.isPending}>
        Vincular
      </Button>
    </form>
  );
}
```

Agregar la ruta en `frontend/src/App.tsx` (import + `<Route>`, junto a `/bulk-downloads`):

```tsx
import { CaseLinksPage } from "./pages/CaseLinksPage";
```

```tsx
                <Route path="/casos-por-confirmar" element={<CaseLinksPage />} />
```

Agregar la entrada en `frontend/src/components/layout/Sidebar.tsx` — extender el import de íconos con `GitMerge` y agregar a `LINKS` (después de `/documents`):

```typescript
import { Archive, FileStack, Gauge, GitMerge, LogOut, PanelLeftClose, PanelLeftOpen, PlayCircle, Radar, Wand2 } from "lucide-react";
```

```typescript
  { to: "/casos-por-confirmar", label: "Casos por confirmar", end: false, icon: GitMerge },
```

- [ ] **Step 4: Confirmar que pasan**

Run: `cd frontend && npm test -- --run CaseLinksPage`
Expected: 4 PASSED

Run: `cd frontend && npm test -- --run`
Expected: toda la suite de frontend PASSED (sin regresiones — revisar en particular `Sidebar.test.tsx` y `App.test.tsx`, que enumeran los links existentes).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/CaseLinksPage.tsx frontend/src/pages/CaseLinksPage.test.tsx frontend/src/App.tsx frontend/src/components/layout/Sidebar.tsx
git commit -m "feat: pantalla de casos por confirmar"
```

---

### Task 13: Línea de tiempo del expediente

**Files:**
- Create: `frontend/src/pages/CaseLinkDetailPage.tsx`
- Test: `frontend/src/pages/CaseLinkDetailPage.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `fetchCaseLink` (Task 11).

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `frontend/src/pages/CaseLinkDetailPage.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { CaseLinkDetailPage } from "./CaseLinkDetailPage";
import * as caseLinksApi from "../api/caseLinks";

vi.mock("../api/caseLinks");

const CASE_LINK = {
  id: 5,
  stages: [
    {
      source_id: 2, source_name: "Consejo de Estado", radicado: "25000234200020200000802",
      f_public_min: "2024-11-01", f_public_max: "2024-11-01",
      documents: [{ id: 20, title: "25000234200020200000802(NRD)", f_public: "2024-11-01", f_providencia: "2024-10-20" }],
    },
    {
      source_id: 1, source_name: "Tribunal Administrativo de Antioquia", radicado: "25000234200020200000801",
      f_public_min: "2023-01-01", f_public_max: "2023-06-01",
      documents: [{ id: 10, title: "25000234200020200000801(NRD)", f_public: "2023-01-01", f_providencia: "2022-12-15" }],
    },
  ],
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/casos-por-confirmar/expedientes/5"]}>
        <Routes>
          <Route path="/casos-por-confirmar/expedientes/:caseLinkId" element={<CaseLinkDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("CaseLinkDetailPage", () => {
  beforeEach(() => {
    vi.mocked(caseLinksApi.fetchCaseLink).mockResolvedValue(CASE_LINK);
  });

  it("orders stages by earliest publication date first", async () => {
    renderPage();
    const stageNames = await screen.findAllByRole("heading", { level: 2 });
    expect(stageNames.map((el) => el.textContent)).toEqual([
      "Tribunal Administrativo de Antioquia",
      "Consejo de Estado",
    ]);
  });

  it("shows each stage's documents", async () => {
    renderPage();
    expect(await screen.findByText("25000234200020200000801(NRD)")).toBeInTheDocument();
    expect(screen.getByText("25000234200020200000802(NRD)")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Confirmar que fallan**

Run: `cd frontend && npm test -- --run CaseLinkDetailPage`
Expected: FAIL — `Cannot find module './CaseLinkDetailPage'`.

- [ ] **Step 3: Implementar**

Crear `frontend/src/pages/CaseLinkDetailPage.tsx`:

```tsx
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { fetchCaseLink } from "../api/caseLinks";
import type { CaseLinkStage } from "../api/types";
import { ErrorBanner } from "../components/ErrorBanner";
import { formatDate } from "../lib/formatters";

function stageSortKey(stage: CaseLinkStage): string {
  return stage.f_public_min ?? "9999-99-99";
}

export function CaseLinkDetailPage() {
  const { caseLinkId } = useParams<{ caseLinkId: string }>();
  const id = Number(caseLinkId);

  const caseLinkQuery = useQuery({
    queryKey: ["case-link", id],
    queryFn: () => fetchCaseLink(id),
    enabled: Number.isFinite(id),
  });

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

      <ol className="space-y-4 border-l border-border pl-6">
        {orderedStages.map((stage) => (
          <li key={`${stage.source_id}-${stage.radicado}`} className="relative">
            <span className="absolute -left-[1.65rem] top-1 size-2.5 rounded-full bg-primary" aria-hidden="true" />
            <h2 className="text-lg font-semibold text-foreground">{stage.source_name}</h2>
            <p className="text-xs text-muted-foreground">
              {stage.f_public_min && formatDate(stage.f_public_min)}
              {stage.f_public_max && stage.f_public_max !== stage.f_public_min && ` – ${formatDate(stage.f_public_max)}`}
            </p>
            <ul className="mt-2 space-y-1">
              {stage.documents.map((document) => (
                <li key={document.id} className="text-sm text-foreground">
                  {document.title}
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

Agregar la ruta en `frontend/src/App.tsx`:

```tsx
import { CaseLinkDetailPage } from "./pages/CaseLinkDetailPage";
```

```tsx
                <Route path="/casos-por-confirmar/expedientes/:caseLinkId" element={<CaseLinkDetailPage />} />
```

- [ ] **Step 4: Confirmar que pasan**

Run: `cd frontend && npm test -- --run CaseLinkDetailPage`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/CaseLinkDetailPage.tsx frontend/src/pages/CaseLinkDetailPage.test.tsx frontend/src/App.tsx
git commit -m "feat: línea de tiempo del expediente"
```

---

### Task 14: Nota de caso relacionado en el listado de documentos

**Files:**
- Modify: `frontend/src/pages/DocumentsPage.tsx`
- Test: `frontend/src/pages/DocumentsPage.test.tsx`

**Interfaces:**
- Consumes: `Document.case_link_status` / `case_link_id` / `case_link_suggestion_id` / `case_link_other_source_name` (Task 11).

- [ ] **Step 1: Escribir las pruebas que fallan**

El archivo mockea la API a nivel de red con MSW (`server.use(http.get(...))`), no con `vi.mock` — seguir ese patrón exacto (ver `mockFilterEndpoints`, `BASE_URL`, `DOCUMENT` ya definidos en el archivo). Agregar dentro del `describe("DocumentsPage", ...)`:

```typescript
it("shows a confirmed case-link note with a link to the timeline", async () => {
  mockFilterEndpoints();
  server.use(
    http.get(`${BASE_URL}/documents`, () =>
      HttpResponse.json({
        items: [{ ...DOCUMENT, case_link_status: "confirmed", case_link_id: 5, case_link_other_source_name: "Consejo de Estado" }],
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
    "/casos-por-confirmar/expedientes/5"
  );
});

it("shows a pending case-link note without a timeline link", async () => {
  mockFilterEndpoints();
  server.use(
    http.get(`${BASE_URL}/documents`, () =>
      HttpResponse.json({
        items: [{ ...DOCUMENT, case_link_status: "pending", case_link_suggestion_id: 9, case_link_other_source_name: "Consejo de Estado" }],
        total: 1,
        limit: 50,
        offset: 0,
      })
    )
  );

  renderPage();

  expect(await screen.findByText(/posible caso relacionado, pendiente de confirmar/i)).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /ver línea de tiempo/i })).not.toBeInTheDocument();
});

it("shows no case-link note when the document has no case_link_status", async () => {
  mockFilterEndpoints();
  server.use(
    http.get(`${BASE_URL}/documents`, () =>
      HttpResponse.json({ items: [DOCUMENT], total: 1, limit: 50, offset: 0 })
    )
  );

  renderPage();

  await screen.findByText("Sentencia C-001-26");
  expect(screen.queryByText(/también aparece en:/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/posible caso relacionado/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Confirmar que fallan**

Run: `cd frontend && npm test -- --run DocumentsPage`
Expected: FAIL — los tres tests nuevos no encuentran el texto/link (el componente todavía no existe).

- [ ] **Step 3: Implementar**

En `frontend/src/pages/DocumentsPage.tsx`, agregar un componente junto a `CaseBadge`:

```tsx
function CaseLinkNote({ document }: { document: Document }) {
  if (document.case_link_status === "confirmed" && document.case_link_id) {
    return (
      <p className="mt-1 text-xs text-muted-foreground">
        También aparece en: {document.case_link_other_source_name} —{" "}
        <Link to={`/casos-por-confirmar/expedientes/${document.case_link_id}`} className="underline-offset-2 hover:underline">
          Ver línea de tiempo
        </Link>
      </p>
    );
  }
  if (document.case_link_status === "pending") {
    return (
      <p className="mt-1 text-xs text-muted-foreground">
        Posible caso relacionado, pendiente de confirmar —{" "}
        <Link to="/casos-por-confirmar" className="underline-offset-2 hover:underline">
          Ver bandeja
        </Link>
      </p>
    );
  }
  return null;
}
```

(Agregar `import { Link } from "react-router-dom";` si el archivo no lo tiene ya.)

Y en la celda de título, justo después del bloque de `CaseBadge` existente (`{!!document.case_document_count && ... <CaseBadge .../>}`), agregar:

```tsx
                  <CaseLinkNote document={document} />
```

- [ ] **Step 4: Confirmar que pasan**

Run: `cd frontend && npm test -- --run DocumentsPage`
Expected: todos PASSED (incluye los 2 nuevos, sin regresiones en los existentes).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/DocumentsPage.tsx frontend/src/pages/DocumentsPage.test.tsx
git commit -m "feat: nota de caso relacionado en el listado de documentos"
```

---

## Después de implementar

1. Correr el backfill contra la base de desarrollo:
   `.venv/Scripts/python -m core.backfill_samai_radicado`
2. Correr toda la suite una vez más antes de pedir revisión:
   `.venv/Scripts/pytest -v` y `cd frontend && npm test -- --run`
3. Usar el flujo real (`run-iurisync` skill / navegador) para confirmar a mano: una sugerencia aparece en "Casos por confirmar", confirmarla lleva a una línea de tiempo con las dos etapas, y la nota aparece en la ficha del documento en ambos estados (pendiente y confirmado).
