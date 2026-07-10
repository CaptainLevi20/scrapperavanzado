# Backend SaaS de Scraping — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new internal backend (FastAPI + Celery/Redis + PostgreSQL + S3-compatible storage) that reuses the scraping logic from `C:\Users\asant\WebScrapping_Fuentes`, formalized around an explicit "familia técnica" registry, replacing Google Drive/Sheets with PostgreSQL + object storage.

**Architecture:** A `core/` package holds scraper adapters (registered by family key), the download/conversion pipeline, the object-storage client, and the SQLAlchemy/repository data layer. `api/` (FastAPI) and `worker/` (Celery) both import `core/` and run as separate processes. Corridas ("runs") are orchestrated as a Celery chord: one task per configured source, fanning in to a finalize callback.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2.x + Alembic, Celery 5.x + Redis, PostgreSQL 16, boto3 against MinIO (dev) / S3-compatible storage (prod), pytest + `responses` for HTTP mocking.

## Global Constraints

- Backend runs on Windows (per design spec); Word COM (`pywin32`) stays Windows-only via an environment marker in `requirements.txt` — it is never imported unless `WordConverter.convert()` is actually called, so it does not block installation or testing on other platforms.
- Mono-tenant, uso interno — no tenant/org modeling.
- No Google Drive / Google Sheets anywhere in this codebase — PostgreSQL + object storage replace them entirely.
- Every scraper adapter implements the existing `BaseScrapper` contract (`scrap(fini, ffin, q="", limit=..., stop_event=None, on_progress=None) -> List[RawDocModel]`) unchanged, so logic ported from `WebScrapping_Fuentes/scrappers/` needs no behavioral rewrite.
- `RawDocModel` (Pydantic) keeps the exact same fields as `WebScrapping_Fuentes/models/models.py`.
- Storage keys mirror today's local hierarchy (`{source}/{f_public}/{tipo}/{filename}{extension}`) but always use forward slashes, since they are S3 object keys, not filesystem paths — this is the one deliberate deviation from a byte-for-byte port, done to keep `os.path.join`-produced backslashes (from Windows) out of storage keys.
- Tests never hit the real government sites — HTTP calls are mocked with the `responses` library using synthetic fixtures shaped like the real responses (verified against the code's parsing logic already in the reused scrapers).
- API auth is a static API key sent via the `X-API-Key` header, validated by SHA-256 hash lookup — keys are minted via a CLI, never a self-service endpoint.
- This plan ports two scraper families end-to-end (`constitucional` — a standalone single-source family, and `samai` — a parameterized multi-source family) to prove the family/source registry model for both shapes. Porting the remaining families (Corte Suprema, JEP, CNDJ, Rama Judicial, ADR, ADRES, ANE, ANH) is explicitly out of scope for this plan — it is a mechanical repeat of the pattern established in Tasks 8–9, tracked as follow-up work.

---

### Task 1: Project scaffolding, settings, and local infrastructure

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `docker-compose.yml`
- Create: `core/__init__.py`
- Create: `core/config.py`
- Create: `pytest.ini`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `core.config.Settings` (pydantic-settings model), `core.config.get_settings() -> Settings`

- [ ] **Step 1: Create `requirements.txt`**

```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
sqlalchemy>=2.0.35
alembic>=1.13.0
psycopg[binary]>=3.2.0
celery[redis]>=5.4.0
redis>=5.0.0
boto3>=1.35.0
pydantic>=2.9.0
pydantic-settings>=2.5.0
requests>=2.31.0
beautifulsoup4>=4.12.0
pypdf>=4.0.0
pywin32>=306; platform_system == "Windows"
httpx>=0.27.0

# dev / test
pytest>=8.3.0
pytest-cov>=5.0.0
responses>=0.25.0
```

- [ ] **Step 2: Create `.gitignore`**

```
.venv/
venv/
__pycache__/
*.pyc
.env
.pytest_cache/
.coverage
```

- [ ] **Step 3: Create `.env.example`**

```
DATABASE_URL=postgresql+psycopg://iurisync:iurisync@localhost:5432/iurisync
TEST_DATABASE_URL=postgresql+psycopg://iurisync:iurisync@localhost:5432/iurisync_test
REDIS_URL=redis://localhost:6379/0
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=iurisync-documents
S3_REGION=us-east-1
```

- [ ] **Step 4: Create `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: iurisync
      POSTGRES_PASSWORD: iurisync
      POSTGRES_DB: iurisync
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data

volumes:
  postgres_data:
  minio_data:
```

- [ ] **Step 5: Create `core/__init__.py`** (empty file, makes `core` a package)

- [ ] **Step 6: Create `core/config.py`**

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://iurisync:iurisync@localhost:5432/iurisync"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "iurisync-documents"
    s3_region: str = "us-east-1"
    api_key_header: str = "X-API-Key"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 7: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
```

- [ ] **Step 8: Write the test**

Create `tests/__init__.py` (empty) and `tests/test_config.py`:

```python
from core.config import Settings, get_settings


def test_settings_have_expected_defaults():
    settings = Settings(_env_file=None)
    assert settings.s3_bucket == "iurisync-documents"
    assert settings.api_key_header == "X-API-Key"


def test_get_settings_is_cached():
    assert get_settings() is get_settings()
```

- [ ] **Step 9: Set up the virtual environment and run the test**

Run:
```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pytest tests/test_config.py -v
```
Expected: `2 passed`

- [ ] **Step 10: Start local infrastructure and confirm it's healthy**

Run: `docker compose up -d` then `docker compose ps`
Expected: `postgres`, `redis`, `minio` all show `running`/`healthy`.

- [ ] **Step 11: Commit**

```bash
git add requirements.txt .gitignore .env.example docker-compose.yml core/__init__.py core/config.py pytest.ini tests/__init__.py tests/test_config.py
git commit -m "chore: scaffold project, settings, and local infra (postgres/redis/minio)"
```

---

### Task 2: Database models, session, and Alembic migration

**Files:**
- Create: `core/db/__init__.py`
- Create: `core/db/models.py`
- Create: `core/db/session.py`
- Create: `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/` (via `alembic init`)
- Test: `tests/test_migrations.py`

**Interfaces:**
- Consumes: `core.config.get_settings()` (Task 1)
- Produces: `core.db.models.Base`, `SourceFamily`, `Source`, `Run`, `RunSource`, `RunError`, `Document`, `ApiKey`; `core.db.session.engine`, `SessionLocal`, `get_db()`

- [ ] **Step 1: Create `core/db/__init__.py`** (empty)

- [ ] **Step 2: Create `core/db/models.py`**

```python
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def _utcnow():
    return datetime.now(timezone.utc)


class SourceFamily(Base):
    __tablename__ = "source_families"

    key = Column(String, primary_key=True)
    display_name = Column(String, nullable=False)
    description = Column(Text, nullable=True)


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True)
    family_key = Column(String, ForeignKey("source_families.key"), nullable=False)
    name = Column(String, nullable=False, unique=True)
    family_params = Column(JSONB, nullable=False, default=dict)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class Run(Base):
    __tablename__ = "runs"

    id = Column(Integer, primary_key=True)
    triggered_by = Column(String, nullable=False)  # 'manual' | 'scheduled'
    fini = Column(Date, nullable=True)
    ffin = Column(Date, nullable=True)
    status = Column(String, nullable=False, default="pending")
    cancel_requested = Column(Boolean, nullable=False, default=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class RunSource(Base):
    __tablename__ = "run_sources"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    status = Column(String, nullable=False, default="pending")
    docs_new = Column(Integer, nullable=False, default=0)
    docs_errors = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)


class RunError(Base):
    __tablename__ = "run_errors"

    id = Column(Integer, primary_key=True)
    run_source_id = Column(Integer, ForeignKey("run_sources.id"), nullable=False)
    message = Column(Text, nullable=False)
    context = Column(JSONB, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    doc_id = Column(String, nullable=False, unique=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    run_source_id = Column(Integer, ForeignKey("run_sources.id"), nullable=True)
    title = Column(String, nullable=False)
    tipo = Column(String, nullable=True)
    seccion = Column(String, nullable=True)
    especialidad = Column(String, nullable=True)
    magistrado = Column(String, nullable=True)
    detalle = Column(Text, nullable=True)
    f_public = Column(Date, nullable=True)
    f_providencia = Column(Date, nullable=True)
    source_url = Column(Text, nullable=True)
    storage_bucket = Column(String, nullable=False)
    storage_key = Column(Text, nullable=False)
    content_type = Column(String, nullable=True)
    file_extension = Column(String, nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    converted_format = Column(String, nullable=True)
    downloaded_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    key_hash = Column(String, nullable=False, unique=True)
    active = Column(Boolean, nullable=False, default=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
```

- [ ] **Step 3: Create `core/db/session.py`**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 4: Initialize Alembic**

Run: `.venv\Scripts\alembic init alembic`
Expected: creates `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/`.

- [ ] **Step 5: Wire `alembic/env.py` to the app's models and settings**

Edit the generated `alembic/env.py`: replace the line `target_metadata = None` with the following, and replace the `run_migrations_online`/`run_migrations_offline` calls' use of `config.get_main_option("sqlalchemy.url")` by setting the URL from settings at the top of the file:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import get_settings
from core.db.models import Base

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata
```

(Insert this block right after the existing `config = context.config` line in the generated file, before `target_metadata = None`, and delete the `target_metadata = None` line.)

- [ ] **Step 6: Generate the initial migration**

Run: `.venv\Scripts\alembic revision --autogenerate -m "initial schema"`
Expected: a new file appears under `alembic/versions/` containing `create_table` calls for all 7 tables.

- [ ] **Step 7: Create the test database**

Run:
```
docker compose exec postgres psql -U iurisync -d iurisync -c "CREATE DATABASE iurisync_test;"
```

- [ ] **Step 8: Write the test**

Create `tests/test_migrations.py`:

```python
import subprocess

from sqlalchemy import create_engine, inspect

TEST_DATABASE_URL = "postgresql+psycopg://iurisync:iurisync@localhost:5432/iurisync_test"

EXPECTED_TABLES = {
    "source_families",
    "sources",
    "runs",
    "run_sources",
    "run_errors",
    "documents",
    "api_keys",
}


def test_alembic_upgrade_head_creates_all_tables():
    subprocess.run(
        ["alembic", "upgrade", "head"],
        env={"DATABASE_URL": TEST_DATABASE_URL, "PATH": _path_env()},
        check=True,
    )
    engine = create_engine(TEST_DATABASE_URL, future=True)
    tables = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES.issubset(tables)
    engine.dispose()


def _path_env():
    import os

    return os.environ["PATH"]
```

Note: this test shells out to `alembic`, so it must run with the project's `.venv` active (`alembic` on `PATH`).

- [ ] **Step 9: Run the test**

Run: `.venv\Scripts\pytest tests/test_migrations.py -v`
Expected: `1 passed`

- [ ] **Step 10: Commit**

```bash
git add core/db alembic alembic.ini tests/test_migrations.py
git commit -m "feat: add SQLAlchemy models and Alembic migration for core schema"
```

---

### Task 3: Repository layer

**Files:**
- Create: `core/db/repository.py`
- Test: `tests/conftest.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: `core.db.models.*` (Task 2)
- Produces: all functions listed below, used by Tasks 11, 12, 14, 15, 16, 17, 18:
  - `list_source_families(db) -> list[SourceFamily]`
  - `create_source_family(db, key, display_name, description=None) -> SourceFamily`
  - `list_sources(db, family_key=None, active=None) -> list[Source]`
  - `get_source(db, source_id) -> Source | None`
  - `create_source(db, family_key, name, family_params, active=True) -> Source`
  - `update_source(db, source_id, active=None, family_params=None) -> Source | None`
  - `create_run(db, triggered_by, fini, ffin) -> Run`
  - `get_run(db, run_id) -> Run | None`
  - `list_runs(db, status=None) -> list[Run]`
  - `set_run_status(db, run_id, status, started_at=None, finished_at=None) -> None`
  - `request_run_cancel(db, run_id) -> Run | None`
  - `is_cancel_requested(db, run_id) -> bool`
  - `create_run_source(db, run_id, source_id) -> RunSource`
  - `get_run_source(db, run_source_id) -> RunSource | None`
  - `list_run_sources(db, run_id) -> list[RunSource]`
  - `set_run_source_status(db, run_source_id, status, **fields) -> None`
  - `add_run_error(db, run_source_id, message, context=None) -> RunError`
  - `document_exists(db, doc_id) -> bool`
  - `insert_document(db, **fields) -> Document | None`
  - `list_documents(db, source_id=None, family_key=None, tipo=None, f_public_from=None, f_public_to=None, title_contains=None, limit=50, offset=0) -> tuple[list[Document], int]`
  - `get_document(db, document_id) -> Document | None`
  - `create_api_key(db, name, key_hash) -> ApiKey`
  - `get_active_api_key_by_hash(db, key_hash) -> ApiKey | None`

- [ ] **Step 1: Create `core/db/repository.py`**

```python
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from core.db.models import ApiKey, Document, Run, RunError, RunSource, Source, SourceFamily


def list_source_families(db: Session) -> list[SourceFamily]:
    return list(db.scalars(select(SourceFamily)).all())


def create_source_family(db: Session, key: str, display_name: str, description: Optional[str] = None) -> SourceFamily:
    family = SourceFamily(key=key, display_name=display_name, description=description)
    db.add(family)
    db.commit()
    db.refresh(family)
    return family


def list_sources(db: Session, family_key: Optional[str] = None, active: Optional[bool] = None) -> list[Source]:
    stmt = select(Source)
    if family_key is not None:
        stmt = stmt.where(Source.family_key == family_key)
    if active is not None:
        stmt = stmt.where(Source.active == active)
    return list(db.scalars(stmt).all())


def get_source(db: Session, source_id: int) -> Optional[Source]:
    return db.get(Source, source_id)


def create_source(db: Session, family_key: str, name: str, family_params: dict, active: bool = True) -> Source:
    source = Source(family_key=family_key, name=name, family_params=family_params, active=active)
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def update_source(
    db: Session, source_id: int, active: Optional[bool] = None, family_params: Optional[dict] = None
) -> Optional[Source]:
    source = db.get(Source, source_id)
    if source is None:
        return None
    if active is not None:
        source.active = active
    if family_params is not None:
        source.family_params = family_params
    db.commit()
    db.refresh(source)
    return source


def create_run(db: Session, triggered_by: str, fini: Optional[date], ffin: Optional[date]) -> Run:
    run = Run(triggered_by=triggered_by, fini=fini, ffin=ffin, status="pending")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_run(db: Session, run_id: int) -> Optional[Run]:
    return db.get(Run, run_id)


def list_runs(db: Session, status: Optional[str] = None) -> list[Run]:
    stmt = select(Run).order_by(Run.created_at.desc())
    if status is not None:
        stmt = stmt.where(Run.status == status)
    return list(db.scalars(stmt).all())


def set_run_status(
    db: Session,
    run_id: int,
    status: str,
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
) -> None:
    run = db.get(Run, run_id)
    run.status = status
    if started_at is not None:
        run.started_at = started_at
    if finished_at is not None:
        run.finished_at = finished_at
    db.commit()


def request_run_cancel(db: Session, run_id: int) -> Optional[Run]:
    run = db.get(Run, run_id)
    if run is None:
        return None
    run.cancel_requested = True
    db.commit()
    db.refresh(run)
    return run


def is_cancel_requested(db: Session, run_id: int) -> bool:
    run = db.get(Run, run_id)
    return bool(run and run.cancel_requested)


def create_run_source(db: Session, run_id: int, source_id: int) -> RunSource:
    run_source = RunSource(run_id=run_id, source_id=source_id, status="pending")
    db.add(run_source)
    db.commit()
    db.refresh(run_source)
    return run_source


def get_run_source(db: Session, run_source_id: int) -> Optional[RunSource]:
    return db.get(RunSource, run_source_id)


def list_run_sources(db: Session, run_id: int) -> list[RunSource]:
    stmt = select(RunSource).where(RunSource.run_id == run_id)
    return list(db.scalars(stmt).all())


def set_run_source_status(db: Session, run_source_id: int, status: str, **fields) -> None:
    run_source = db.get(RunSource, run_source_id)
    run_source.status = status
    for key, value in fields.items():
        setattr(run_source, key, value)
    db.commit()


def add_run_error(db: Session, run_source_id: int, message: str, context: Optional[dict] = None) -> RunError:
    error = RunError(run_source_id=run_source_id, message=message, context=context)
    db.add(error)
    db.commit()
    db.refresh(error)
    return error


def document_exists(db: Session, doc_id: str) -> bool:
    stmt = select(Document.id).where(Document.doc_id == doc_id)
    return db.scalars(stmt).first() is not None


def insert_document(db: Session, **fields) -> Optional[Document]:
    stmt = pg_insert(Document).values(**fields).on_conflict_do_nothing(index_elements=["doc_id"])
    db.execute(stmt)
    db.commit()
    return db.scalars(select(Document).where(Document.doc_id == fields["doc_id"])).first()


def list_documents(
    db: Session,
    source_id: Optional[int] = None,
    family_key: Optional[str] = None,
    tipo: Optional[str] = None,
    f_public_from: Optional[date] = None,
    f_public_to: Optional[date] = None,
    title_contains: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Document], int]:
    stmt = select(Document)
    if source_id is not None:
        stmt = stmt.where(Document.source_id == source_id)
    if family_key is not None:
        stmt = stmt.join(Source, Source.id == Document.source_id).where(Source.family_key == family_key)
    if tipo is not None:
        stmt = stmt.where(Document.tipo == tipo)
    if f_public_from is not None:
        stmt = stmt.where(Document.f_public >= f_public_from)
    if f_public_to is not None:
        stmt = stmt.where(Document.f_public <= f_public_to)
    if title_contains is not None:
        stmt = stmt.where(Document.title.ilike(f"%{title_contains}%"))

    total = len(list(db.scalars(stmt).all()))
    stmt = stmt.order_by(Document.downloaded_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all()), total


def get_document(db: Session, document_id: int) -> Optional[Document]:
    return db.get(Document, document_id)


def create_api_key(db: Session, name: str, key_hash: str) -> ApiKey:
    api_key = ApiKey(name=name, key_hash=key_hash, active=True)
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    return api_key


def get_active_api_key_by_hash(db: Session, key_hash: str) -> Optional[ApiKey]:
    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.active.is_(True))
    return db.scalars(stmt).first()
```

- [ ] **Step 2: Create the shared test fixtures**

Create `tests/conftest.py`:

```python
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.db.models import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://iurisync:iurisync@localhost:5432/iurisync_test",
)
TEST_S3_ENDPOINT_URL = os.environ.get("TEST_S3_ENDPOINT_URL", "http://localhost:9000")
TEST_S3_BUCKET = os.environ.get("TEST_S3_BUCKET", "iurisync-test")


@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(test_engine):
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
    session_factory = sessionmaker(bind=test_engine, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 3: Write the tests**

Create `tests/test_repository.py`:

```python
from core.db import repository


def test_create_and_list_sources(db_session):
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})

    sources = repository.list_sources(db_session, family_key="constitucional")
    assert [s.name for s in sources] == ["Corte Constitucional"]


def test_run_and_run_source_lifecycle(db_session):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})

    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    assert run.status == "pending"

    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)
    repository.set_run_source_status(db_session, run_source.id, "completed", docs_new=3, docs_errors=1)

    [refreshed] = repository.list_run_sources(db_session, run.id)
    assert refreshed.status == "completed"
    assert refreshed.docs_new == 3
    assert refreshed.docs_errors == 1

    repository.request_run_cancel(db_session, run.id)
    assert repository.is_cancel_requested(db_session, run.id) is True


def test_insert_document_is_idempotent_on_doc_id(db_session):
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})

    payload = dict(
        doc_id="abc123",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-02-01/Sentencia/T-065-24.rtf",
    )
    first = repository.insert_document(db_session, **payload)
    second = repository.insert_document(db_session, **payload)

    assert first.id == second.id
    assert repository.document_exists(db_session, "abc123") is True


def test_api_key_create_and_lookup_by_hash(db_session):
    repository.create_api_key(db_session, name="tests", key_hash="hash123")
    found = repository.get_active_api_key_by_hash(db_session, "hash123")
    assert found is not None
    assert found.name == "tests"
    assert repository.get_active_api_key_by_hash(db_session, "missing") is None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\pytest tests/test_repository.py -v`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add core/db/repository.py tests/conftest.py tests/test_repository.py
git commit -m "feat: add repository layer for sources, runs, documents, and api keys"
```

---

### Task 4: Core scraping contracts (models, base scraper, utils)

**Files:**
- Create: `core/models.py`
- Create: `core/scrapers/__init__.py`
- Create: `core/scrapers/base.py`
- Create: `core/utils.py`
- Test: `tests/test_core_utils.py`

**Interfaces:**
- Produces: `core.models.RawDocModel`, `core.scrapers.base.BaseScrapper`, `core.utils.make_doc_id(key, f_public)`, `core.utils.compute_doc_id(doc) -> str`, `core.utils.extract_filename(disposition, content_type, url, opt_title) -> dict`, `core.utils.storage_path(*parts) -> str`

- [ ] **Step 1: Create `core/models.py`** (ported unchanged from `WebScrapping_Fuentes/models/models.py`)

```python
from typing import List, Optional

from pydantic import BaseModel


class RawDocModel(BaseModel):
    source: str
    link: dict
    title: str
    tipo: str
    f_public: str
    f_providencia: Optional[str] = None
    seccion: Optional[str] = None
    seccion_en_carpeta: bool = True
    especialidad: Optional[str] = None
    magistrado: Optional[str] = None
    detalle: Optional[str] = None
    save_path: Optional[str] = None
    convert_to: Optional[str] = None

    def __getitem__(self, key):
        return getattr(self, key)
```

- [ ] **Step 2: Create `core/scrapers/__init__.py`** (empty)

- [ ] **Step 3: Create `core/scrapers/base.py`** (ported unchanged)

```python
class BaseScrapper:
    source = None

    def scrap(self, fini, ffin, q="", limit=100, stop_event=None, on_progress=None):
        raise NotImplementedError("Subclasses must implement this method.")
```

- [ ] **Step 4: Create `core/utils.py`**

```python
import hashlib
import re

from core.models import RawDocModel


def make_doc_id(key: str, f_public: str) -> str:
    return hashlib.sha1(f"{key}_{f_public}".encode()).hexdigest()


def compute_doc_id(doc: RawDocModel) -> str:
    body = doc.link.get("body") or {}
    key = body["path"] if "path" in body else doc.link["url"]
    return make_doc_id(key, doc.f_public)


def extract_filename(disposition: str, content_type: str, url: str, opt_title: str) -> dict:
    if disposition:
        match = re.search(r'filename="?([^"]+)"?', disposition)
        if match:
            filename = match.group(1)
            ext = "." + filename.split(".")[-1] if "." in filename else ""
            return {"filename": filename.split(".")[0], "extension": ext}

    if "rtf" in content_type.lower():
        ext = ".rtf"
    elif "pdf" in content_type.lower():
        ext = ".pdf"
    elif "word" in content_type.lower() or "officedocument" in content_type.lower():
        ext = ".docx"
    else:
        ext = ""

    url_path = url.split("?")[0]
    name = url_path.split("/")[-1] or opt_title
    if "." in name:
        base, _, url_ext = name.rpartition(".")
        name = base
        if not ext:
            ext = "." + url_ext
    return {"filename": name, "extension": ext}


def storage_path(*parts) -> str:
    return "/".join(str(p) for p in parts)
```

- [ ] **Step 5: Write the tests**

Create `tests/test_core_utils.py`:

```python
from core.models import RawDocModel
from core.utils import compute_doc_id, extract_filename, make_doc_id, storage_path


def test_make_doc_id_is_deterministic():
    assert make_doc_id("foo", "2026-01-01") == make_doc_id("foo", "2026-01-01")
    assert make_doc_id("foo", "2026-01-01") != make_doc_id("bar", "2026-01-01")


def test_compute_doc_id_prefers_body_path_over_url():
    doc = RawDocModel(
        source="s", link={"url": "https://x/1", "method": "GET", "body": {"path": "radicado-1"}},
        title="t", tipo="Auto", f_public="2026-01-01",
    )
    assert compute_doc_id(doc) == make_doc_id("radicado-1", "2026-01-01")


def test_compute_doc_id_falls_back_to_url_without_body_path():
    doc = RawDocModel(
        source="s", link={"url": "https://x/1", "method": "GET"},
        title="t", tipo="Auto", f_public="2026-01-01",
    )
    assert compute_doc_id(doc) == make_doc_id("https://x/1", "2026-01-01")


def test_extract_filename_from_content_disposition():
    result = extract_filename('attachment; filename="doc.pdf"', "", "https://x/y", "fallback")
    assert result == {"filename": "doc", "extension": ".pdf"}


def test_extract_filename_falls_back_to_content_type_and_url():
    result = extract_filename("", "application/pdf", "https://x/carpeta/archivo", "fallback")
    assert result == {"filename": "archivo", "extension": ".pdf"}


def test_storage_path_joins_with_forward_slashes():
    assert storage_path("Corte Constitucional", "2026-01-01", "Sentencia", "T-1.rtf") == (
        "Corte Constitucional/2026-01-01/Sentencia/T-1.rtf"
    )
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv\Scripts\pytest tests/test_core_utils.py -v`
Expected: `6 passed`

- [ ] **Step 7: Commit**

```bash
git add core/models.py core/scrapers/base.py core/scrapers/__init__.py core/utils.py tests/test_core_utils.py
git commit -m "feat: port RawDocModel, BaseScrapper, and shared scraping utils"
```

---

### Task 5: Family registry

**Files:**
- Create: `core/scrapers/registry.py`
- Test: `tests/test_registry.py`

**Interfaces:**
- Consumes: `core.scrapers.base.BaseScrapper` (Task 4)
- Produces: `core.scrapers.registry.register_family(key)` (decorator), `core.scrapers.registry.resolve_scraper(family_key, params) -> BaseScrapper`, `core.scrapers.registry.FAMILY_REGISTRY`

- [ ] **Step 1: Write the failing test**

Create `tests/test_registry.py`:

```python
import pytest

from core.scrapers.base import BaseScrapper
from core.scrapers.registry import FAMILY_REGISTRY, register_family, resolve_scraper


def test_register_family_adds_class_to_registry():
    @register_family("dummy")
    class DummyScraper(BaseScrapper):
        def __init__(self, greeting="hi"):
            self.greeting = greeting

        def scrap(self, fini, ffin, **kwargs):
            return [self.greeting]

    assert FAMILY_REGISTRY["dummy"] is DummyScraper


def test_resolve_scraper_instantiates_with_params():
    scraper = resolve_scraper("dummy", {"greeting": "hola"})
    assert scraper.scrap("2026-01-01", "2026-01-02") == ["hola"]


def test_resolve_scraper_raises_for_unknown_family():
    with pytest.raises(ValueError, match="desconocida"):
        resolve_scraper("no-existe", {})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.scrapers.registry'`

- [ ] **Step 3: Create `core/scrapers/registry.py`**

```python
from typing import Dict, Type

from core.scrapers.base import BaseScrapper

FAMILY_REGISTRY: Dict[str, Type[BaseScrapper]] = {}


def register_family(key: str):
    def _wrap(cls: Type[BaseScrapper]):
        FAMILY_REGISTRY[key] = cls
        return cls

    return _wrap


def resolve_scraper(family_key: str, params: dict) -> BaseScrapper:
    try:
        cls = FAMILY_REGISTRY[family_key]
    except KeyError:
        raise ValueError(f"Familia técnica desconocida: {family_key}")
    return cls(**params)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_registry.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/registry.py tests/test_registry.py
git commit -m "feat: add family registry mapping family_key to scraper adapter classes"
```

---

### Task 6: Object storage client

**Files:**
- Create: `core/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: `core.config.get_settings()` (Task 1)
- Produces: `core.storage.ensure_bucket(bucket)`, `core.storage.upload_file(local_path, key, bucket=None, content_type=None) -> tuple[str, str]`, `core.storage.presigned_url(bucket, key, expires_in=3600) -> str`

- [ ] **Step 1: Create `core/storage.py`**

```python
from pathlib import Path
from typing import Optional

import boto3
from botocore.client import Config as BotoConfig

from core.config import get_settings


def _client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=BotoConfig(signature_version="s3v4"),
    )


def ensure_bucket(bucket: str) -> None:
    client = _client()
    existing = [b["Name"] for b in client.list_buckets().get("Buckets", [])]
    if bucket not in existing:
        client.create_bucket(Bucket=bucket)


def upload_file(
    local_path: Path, key: str, bucket: Optional[str] = None, content_type: Optional[str] = None
) -> tuple[str, str]:
    settings = get_settings()
    bucket = bucket or settings.s3_bucket
    ensure_bucket(bucket)
    client = _client()
    extra_args = {"ContentType": content_type} if content_type else {}
    client.upload_file(str(local_path), bucket, key, ExtraArgs=extra_args)
    return bucket, key


def presigned_url(bucket: str, key: str, expires_in: int = 3600) -> str:
    client = _client()
    return client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in
    )
```

- [ ] **Step 2: Write the test**

Create `tests/test_storage.py`:

```python
import requests

from core.storage import presigned_url, upload_file
from tests.conftest import TEST_S3_BUCKET


def test_upload_file_and_presigned_url_roundtrip(tmp_path):
    local_file = tmp_path / "doc.txt"
    local_file.write_text("contenido de prueba")

    bucket, key = upload_file(local_file, "test/doc.txt", bucket=TEST_S3_BUCKET, content_type="text/plain")

    url = presigned_url(bucket, key)
    response = requests.get(url, timeout=10)
    assert response.status_code == 200
    assert response.text == "contenido de prueba"
```

- [ ] **Step 3: Run the test**

Run: `.venv\Scripts\pytest tests/test_storage.py -v`
Expected: `1 passed` (requires `docker compose up -d` from Task 1 to be running so MinIO is reachable at `http://localhost:9000`)

- [ ] **Step 4: Commit**

```bash
git add core/storage.py tests/test_storage.py
git commit -m "feat: add S3-compatible object storage client (upload + presigned url)"
```

---

### Task 7: Downloader

**Files:**
- Create: `core/downloader.py`
- Test: `tests/test_downloader.py`

**Interfaces:**
- Consumes: `core.models.RawDocModel` (Task 4), `core.utils.extract_filename`, `core.utils.storage_path` (Task 4)
- Produces: `core.downloader.DownloadResult` (dataclass: `local_path`, `storage_key`, `content_type`, `file_size_bytes`), `core.downloader.Downloader` with `.download(doc, tmp_dir, stop_event=None) -> DownloadResult` and `.close()`

- [ ] **Step 1: Create `core/downloader.py`**

```python
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.utils import extract_filename, storage_path

_WORD_FORMATS = {"rtf": 6, "docx": 16, "pdf": 17}


@dataclass
class DownloadResult:
    local_path: Path
    storage_key: str
    content_type: str
    file_size_bytes: int


def _pdf_to_rtf_fallback(input_path: Path) -> Path:
    from pypdf import PdfReader

    reader = PdfReader(str(input_path))
    if reader.is_encrypted:
        reader.decrypt("")
    output_path = input_path.with_suffix(".rtf")
    with open(output_path, "w", encoding="ascii", errors="replace") as f:
        f.write("{\\rtf1\\ansi\\ansicpg1252\\deff0\n")
        f.write("{\\fonttbl{\\f0\\froman\\fcharset0 Times New Roman;}}\n")
        f.write("\\f0\\fs24\n")
        for page in reader.pages:
            for line in (page.extract_text() or "").splitlines():
                escaped = line.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
                rtf_line = "".join(f"\\u{ord(c)}?" if ord(c) > 127 else c for c in escaped)
                f.write(rtf_line + "\\par\n")
            f.write("\\par\n")
        f.write("}\n")
    return output_path


class WordConverter:
    """Abre Word una sola vez y reutiliza la instancia para todas las conversiones."""

    def __init__(self):
        self._word = None

    def _get_word(self):
        if self._word is None:
            import win32com.client

            self._word = win32com.client.Dispatch("Word.Application")
            self._word.Visible = False
            self._word.DisplayAlerts = 0
        return self._word

    def convert(self, input_path: Path, target_format: str) -> Path:
        fmt = _WORD_FORMATS.get(target_format)
        if fmt is None:
            raise ValueError(f"Formato no soportado: {target_format}")

        output_path = input_path.with_suffix(f".{target_format}")
        word = self._get_word()
        doc = word.Documents.Open(
            str(input_path.resolve()), ConfirmConversions=False, AddToRecentFiles=False
        )
        doc.SaveAs(str(output_path.resolve()), FileFormat=fmt)
        doc.Close(SaveChanges=False)

        if not output_path.exists():
            raise RuntimeError(f"Word no generó el archivo esperado: {output_path}")
        return output_path

    def quit(self):
        if self._word is not None:
            try:
                self._word.Quit()
            except Exception:
                pass
            self._word = None


class Downloader:
    def __init__(self):
        self._word_converter = WordConverter()

    def close(self):
        if self._word_converter:
            self._word_converter.quit()
            self._word_converter = None

    def _convert(self, path: Path, target_format: str) -> Path:
        if target_format == "rtf_word":
            try:
                return self._word_converter.convert(path, "rtf")
            except Exception as word_err:
                logging.warning("WordConverter falló (%s): %s. Usando pypdf fallback.", path.name, word_err)
                try:
                    return _pdf_to_rtf_fallback(path)
                except Exception as e:
                    logging.warning("No se pudo convertir a RTF (%s): %s", path.name, e)
                    return path
        elif target_format == "rtf":
            try:
                return _pdf_to_rtf_fallback(path)
            except Exception as e:
                logging.warning("No se pudo convertir a RTF (%s): %s", path.name, e)
                return path
        else:
            raise ValueError(f"Formato no soportado: {target_format}")

    @staticmethod
    def _resolve_jwt_indirect(jwt_url: str, headers: dict) -> requests.Response:
        session = requests.Session()
        session.headers.update(headers)
        ver = session.get(jwt_url, timeout=30)
        ver.raise_for_status()
        soup = BeautifulSoup(ver.text, "html.parser")

        blob_url = next(
            (a["href"] for a in soup.find_all("a", href=True) if "blob.core.windows.net" in a["href"]),
            None,
        )
        if blob_url:
            return session.get(blob_url, stream=True, timeout=120)

        raise FileNotFoundError(f"Archivo aún no disponible en SAMAI: {jwt_url[:80]}")

    @staticmethod
    def _resolve_storage_key(doc: RawDocModel, filename: dict) -> str:
        if doc.save_path:
            return doc.save_path.replace("(filename)", filename["filename"]).replace(
                "(extension)", filename["extension"]
            )
        return storage_path(doc.source, doc.f_public, doc.tipo, f"{filename['filename']}{filename['extension']}")

    def download(self, doc: RawDocModel, tmp_dir: Path, stop_event=None) -> DownloadResult:
        headers = {"User-Agent": "Mozilla/5.0"}

        last_exc = None
        response = None
        for _attempt in range(3):
            try:
                if doc.link["method"] == "POST":
                    headers["Content-Type"] = "application/json"
                    body = doc.link.get("body", {})
                    response = requests.post(doc.link["url"], json=body, headers=headers, stream=True, timeout=120)
                elif doc.link["method"] == "jwt_indirect":
                    response = self._resolve_jwt_indirect(doc.link["url"], headers)
                else:
                    response = requests.get(doc.link["url"], headers=headers, stream=True, timeout=120)
                break
            except requests.exceptions.Timeout as e:
                last_exc = e
        if response is None:
            raise last_exc

        with response as r:
            r.raise_for_status()
            content_type = r.headers.get("Content-Type", "")
            disposition = r.headers.get("Content-Disposition", "")

            filename = extract_filename(disposition, content_type, doc.link["url"], doc.title)
            storage_key = self._resolve_storage_key(doc, filename)

            temp_path = tmp_dir / f"{uuid.uuid4().hex}{filename['extension']}"
            with open(temp_path, "wb") as f:
                for chunk in r.iter_content(8192):
                    if stop_event is not None and getattr(stop_event, "is_set", lambda: False)():
                        raise InterruptedError("Descarga cancelada")
                    if chunk:
                        f.write(chunk)

        if doc.convert_to:
            converted = self._convert(temp_path, doc.convert_to)
            if converted != temp_path:
                storage_key = storage_key.rsplit(".", 1)[0] + ".rtf" if "." in storage_key else storage_key + ".rtf"
                temp_path = converted

        return DownloadResult(
            local_path=temp_path,
            storage_key=storage_key,
            content_type=content_type,
            file_size_bytes=temp_path.stat().st_size,
        )
```

- [ ] **Step 2: Write the tests**

Create `tests/test_downloader.py`:

```python
from pathlib import Path

import pytest
import requests
import responses
from pypdf import PdfWriter

from core.downloader import Downloader
from core.models import RawDocModel


def _doc(method="GET", url="https://example.com/file.pdf", body=None, save_path=None, convert_to=None):
    link = {"url": url, "method": method}
    if body:
        link["body"] = body
    return RawDocModel(
        source="Test",
        link=link,
        title="Documento de prueba",
        tipo="Auto",
        f_public="2026-01-01",
        save_path=save_path,
        convert_to=convert_to,
    )


@responses.activate
def test_download_get_writes_temp_file_and_builds_default_storage_key(tmp_path):
    responses.add(
        responses.GET,
        "https://example.com/file.pdf",
        body=b"%PDF-1.4 contenido de prueba",
        headers={"Content-Type": "application/pdf"},
        status=200,
    )
    downloader = Downloader()
    result = downloader.download(_doc(), tmp_path)

    assert result.local_path.exists()
    assert result.local_path.read_bytes() == b"%PDF-1.4 contenido de prueba"
    assert result.storage_key == "Test/2026-01-01/Auto/file.pdf"
    assert result.content_type == "application/pdf"


@responses.activate
def test_download_post_sends_json_body(tmp_path):
    responses.add(
        responses.POST,
        "https://example.com/api",
        body=b"contenido",
        headers={"Content-Type": "application/octet-stream"},
        status=200,
    )
    downloader = Downloader()
    doc = _doc(method="POST", url="https://example.com/api", body={"id": "123"})
    result = downloader.download(doc, tmp_path)
    assert result.local_path.read_bytes() == b"contenido"


@responses.activate
def test_download_jwt_indirect_resolves_blob_url(tmp_path):
    responses.add(
        responses.GET,
        "https://example.com/ver",
        body='<html><a href="https://foo.blob.core.windows.net/doc.pdf">ver</a></html>',
        status=200,
    )
    responses.add(
        responses.GET,
        "https://foo.blob.core.windows.net/doc.pdf",
        body=b"contenido blob",
        headers={"Content-Type": "application/pdf"},
        status=200,
    )
    downloader = Downloader()
    doc = _doc(method="jwt_indirect", url="https://example.com/ver")
    result = downloader.download(doc, tmp_path)
    assert result.local_path.read_bytes() == b"contenido blob"


@responses.activate
def test_download_jwt_indirect_raises_file_not_found_when_blob_missing(tmp_path):
    responses.add(responses.GET, "https://example.com/ver", body="<html>sin enlace blob</html>", status=200)
    downloader = Downloader()
    doc = _doc(method="jwt_indirect", url="https://example.com/ver")
    with pytest.raises(FileNotFoundError):
        downloader.download(doc, tmp_path)


@responses.activate
def test_download_retries_on_timeout_then_succeeds(tmp_path):
    calls = {"count": 0}

    def _callback(request):
        calls["count"] += 1
        if calls["count"] < 2:
            raise requests.exceptions.Timeout()
        return (200, {"Content-Type": "application/pdf"}, b"ok")

    responses.add_callback(responses.GET, "https://example.com/file.pdf", callback=_callback)
    downloader = Downloader()
    result = downloader.download(_doc(), tmp_path)
    assert result.local_path.read_bytes() == b"ok"
    assert calls["count"] == 2


def test_convert_rtf_word_falls_back_to_pypdf_when_word_conversion_fails(tmp_path, monkeypatch):
    pdf_path = tmp_path / "doc.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    downloader = Downloader()

    def _raise(*_args, **_kwargs):
        raise RuntimeError("Word no disponible")

    monkeypatch.setattr(downloader._word_converter, "convert", _raise)

    converted = downloader._convert(pdf_path, "rtf_word")
    assert converted.suffix == ".rtf"
    assert converted.exists()
```

- [ ] **Step 3: Run the tests**

Run: `.venv\Scripts\pytest tests/test_downloader.py -v`
Expected: `6 passed`

- [ ] **Step 4: Commit**

```bash
git add core/downloader.py tests/test_downloader.py
git commit -m "feat: port downloader (GET/POST/jwt_indirect, RTF conversion with pypdf fallback)"
```

---

### Task 8: Corte Constitucional family (standalone scraper)

**Files:**
- Create: `core/scrapers/families/__init__.py`
- Create: `core/scrapers/families/constitucional.py`
- Test: `tests/families/__init__.py`
- Test: `tests/families/test_constitucional.py`

**Interfaces:**
- Consumes: `core.scrapers.base.BaseScrapper`, `core.models.RawDocModel`, `core.scrapers.registry.register_family` (Tasks 4, 5)
- Produces: `core.scrapers.families.constitucional.ScrapConstitucional`, registered under family key `"constitucional"`

- [ ] **Step 1: Create `core/scrapers/families/constitucional.py`** (ported from `WebScrapping_Fuentes/scrappers/constitucional.py`, with the URL builder inlined and `save_path` built with `storage_path` instead of `os.path.join`)

```python
from datetime import datetime, timedelta
from typing import List

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_DOWNLOAD_URL = "https://www.corteconstitucional.gov.co/sentencias/"


def _search_url(fini: str, ffin: str, q: str = "", limit: int = 1000) -> str:
    return (
        "https://www.corteconstitucional.gov.co/relatoria/buscador_new/"
        f"?searchOption=texto&fini={fini}&ffin={ffin}&buscar_por={q}&maxprov={limit}&slop=1&accion=search&tipo=json"
    )


@register_family("constitucional")
class ScrapConstitucional(BaseScrapper):
    def __init__(self):
        self.source = "Corte Constitucional"

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        fecha_local = datetime.strptime(fini, "%Y-%m-%d")
        fecha_final_global = datetime.strptime(ffin, "%Y-%m-%d")
        docs: List[RawDocModel] = []

        while fecha_local < fecha_final_global:
            fecha_inicial = fecha_local.strftime("%Y-%m-%d")
            fecha_final = min(fecha_local + timedelta(days=365), fecha_final_global)

            url = _search_url(fecha_inicial, fecha_final.strftime("%Y-%m-%d"), q, limit)
            response = requests.get(url)

            if response.status_code != 200:
                raise Exception(
                    f"Error al obtener datos de {self.source}: {response.status_code} - {response.text}"
                )

            results = response.json()
            data = results["data"]["hits"].get("hits", [])

            for item in data:
                raw = item["_source"]
                link = f"{_DOWNLOAD_URL}{raw['rutahtml'].replace('.htm', '.rtf')}"
                fecha_p = raw.get("prov_f_public") or raw["prov_f_sentencia"]
                safe_title = raw["prov_sentencia"].replace("/", "-")
                path = storage_path(self.source, fecha_p, raw["prov_tipo"], f"{safe_title}(extension)")

                docs.append(
                    RawDocModel(
                        source=self.source,
                        link={"url": link, "method": "GET", "body": {"path": raw["prov_sentencia"]}},
                        title=raw["prov_sentencia"],
                        tipo=raw["prov_tipo"],
                        f_public=fecha_p,
                        f_providencia=raw["prov_f_sentencia"],
                        save_path=path,
                    )
                )

            fecha_local = fecha_final

        return docs
```

- [ ] **Step 2: Create `core/scrapers/families/__init__.py`** (imports every family module so `@register_family` runs)

```python
from . import constitucional  # noqa: F401
```

- [ ] **Step 3: Write the test**

Create `tests/families/__init__.py` (empty) and `tests/families/test_constitucional.py`:

```python
import responses

from core.scrapers.families.constitucional import ScrapConstitucional
from core.scrapers.registry import FAMILY_REGISTRY


def _fixture_response():
    return {
        "data": {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "rutahtml": "t-065-24.htm",
                            "prov_sentencia": "T-065/24",
                            "prov_tipo": "Sentencia",
                            "prov_f_public": "2024-02-01",
                            "prov_f_sentencia": "2024-01-25",
                        }
                    }
                ]
            }
        }
    }


@responses.activate
def test_scrap_returns_expected_rawdocmodel():
    responses.add(
        responses.GET,
        "https://www.corteconstitucional.gov.co/relatoria/buscador_new/",
        json=_fixture_response(),
        status=200,
    )
    scraper = ScrapConstitucional()
    docs = scraper.scrap(fini="2024-01-01", ffin="2024-03-01")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "T-065/24"
    assert doc.tipo == "Sentencia"
    assert doc.f_public == "2024-02-01"
    assert doc.f_providencia == "2024-01-25"
    assert doc.link["url"] == "https://www.corteconstitucional.gov.co/sentencias/t-065-24.rtf"
    assert doc.link["body"] == {"path": "T-065/24"}
    assert doc.save_path == "Corte Constitucional/2024-02-01/Sentencia/T-065-24(extension)"


def test_constitucional_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401 — triggers registration

    assert FAMILY_REGISTRY["constitucional"] is ScrapConstitucional
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\pytest tests/families/test_constitucional.py -v`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/__init__.py core/scrapers/families/constitucional.py tests/families/__init__.py tests/families/test_constitucional.py
git commit -m "feat: port Corte Constitucional scraper as the 'constitucional' family"
```

---

### Task 9: SAMAI family (parameterized multi-source scraper)

**Files:**
- Create: `core/scrapers/families/samai.py`
- Modify: `core/scrapers/families/__init__.py`
- Test: `tests/families/test_samai.py`

**Interfaces:**
- Consumes: `core.scrapers.base.BaseScrapper`, `core.models.RawDocModel`, `core.scrapers.registry.register_family` (Tasks 4, 5)
- Produces: `core.scrapers.families.samai.ScrapTribunales(corp_code, corp_name)`, `core.scrapers.families.samai._SAMAI_CORPS: dict[str, str]` (28 entries), registered under family key `"samai"`

- [ ] **Step 1: Create `core/scrapers/families/samai.py`** (ported from `WebScrapping_Fuentes/scrappers/samai.py`, with `os.path.join` replaced by `storage_path` and the class registered via `@register_family("samai")`)

```python
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_URL = "https://samai.consejodeestado.gov.co/vistas/utiles/WEstados.aspx"

_SAMAI_CORPS = {
    "1100103": "Consejo de Estado",
    "0500123": "Tribunal Administrativo de Antioquia",
    "8100123": "Tribunal Administrativo de Arauca",
    "0800123": "Tribunal Administrativo del Atlántico",
    "1300123": "Tribunal Administrativo de Bolívar",
    "1500123": "Tribunal Administrativo de Boyacá",
    "1700123": "Tribunal Administrativo de Caldas",
    "1800123": "Tribunal Administrativo del Caquetá",
    "8500123": "Tribunal Administrativo del Casanare",
    "1900123": "Tribunal Administrativo del Cauca",
    "2000123": "Tribunal Administrativo del Cesar",
    "2700123": "Tribunal Administrativo del Chocó",
    "2300123": "Tribunal Administrativo de Córdoba",
    "2500023": "Tribunal Administrativo de Cundinamarca",
    "4100123": "Tribunal Administrativo del Huila",
    "4400123": "Tribunal Administrativo de la Guajira",
    "4700123": "Tribunal Administrativo del Magdalena",
    "5000123": "Tribunal Administrativo del Meta",
    "5200123": "Tribunal Administrativo de Nariño",
    "5400123": "Tribunal Administrativo de Norte de Santander",
    "8600123": "Tribunal Administrativo del Putumayo",
    "6300123": "Tribunal Administrativo del Quindío",
    "6600123": "Tribunal Administrativo de Risaralda",
    "8800123": "Tribunal Administrativo de San Andrés",
    "6800123": "Tribunal Administrativo de Santander",
    "7000123": "Tribunal Administrativo de Sucre",
    "7300123": "Tribunal Administrativo del Tolima",
    "7600123": "Tribunal Administrativo del Valle del Cauca",
}

_INVALID_PATH = re.compile(r'[\\/*?:"<>|]')


def _safe(text, maxlen=60):
    return _INVALID_PATH.sub("-", text)[:maxlen]


def _parse_estado_date(val: str):
    return datetime.strptime(val.split(" ")[0], "%d/%m/%Y")


def _parse_prov_date(val: str):
    try:
        return datetime.strptime(val.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
    except Exception:
        return None


def _all_inputs(soup) -> dict:
    out = {}
    for inp in soup.find_all("input"):
        name = inp.get("name")
        if name:
            out[name] = inp.get("value", "")
    return out


@register_family("samai")
class ScrapTribunales(BaseScrapper):
    source = "Tribunales Administrativos"

    def __init__(self, corp_code: str, corp_name: str):
        self._corp_code = corp_code
        self._corp_name = corp_name
        self.source = corp_name

    def scrap(self, fini, ffin, q="", limit=1000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        fini_dt = datetime.strptime(fini, "%Y-%m-%d")
        ffin_dt = datetime.strptime(ffin, "%Y-%m-%d")
        if on_progress:
            on_progress(f"[SAMAI] Procesando {self._corp_name}…")
        try:
            return self._scrap_corp(self._corp_code, self._corp_name, fini_dt, ffin_dt, stop_event, on_progress)
        except Exception as e:
            if on_progress:
                on_progress(f"[SAMAI] Error en {self._corp_name}: {e}")
            return []

    def _new_session(self):
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        return s

    @staticmethod
    def _fetch(fn, *args, **kwargs):
        for attempt in range(2):
            try:
                res = fn(*args, **kwargs)
                res.raise_for_status()
                return res
            except requests.exceptions.Timeout:
                if attempt == 0:
                    time.sleep(5)
                    continue
                raise

    def _step1_get(self, session):
        res = self._fetch(session.get, _URL, timeout=30)
        return BeautifulSoup(res.text, "html.parser")

    def _step2_select_corp(self, session, soup1, corp_code):
        data = {
            **_all_inputs(soup1),
            "ctl00$MainContent$LstCorpHabilitada": corp_code,
            "ctl00$MainContent$ImgBuscar2.x": "10",
            "ctl00$MainContent$ImgBuscar2.y": "10",
        }
        res = self._fetch(session.post, _URL, data=data, timeout=30)
        return BeautifulSoup(res.text, "html.parser")

    def _step3_select_section(self, session, soup2, corp_code, sec_code):
        data = {
            **_all_inputs(soup2),
            "ctl00$MainContent$LstCorpHabilitada": corp_code,
            "ctl00$MainContent$LstCoorporacion": sec_code,
            "ctl00$MainContent$ImgBuscar3.x": "10",
            "ctl00$MainContent$ImgBuscar3.y": "10",
        }
        res = self._fetch(session.post, _URL, data=data, timeout=30)
        return BeautifulSoup(res.text, "html.parser")

    def _step4a_check_all(self, session, soup3, corp_code, sec_code, fecha_val):
        data = {
            **_all_inputs(soup3),
            "ctl00$MainContent$LstCorpHabilitada": corp_code,
            "ctl00$MainContent$LstCoorporacion": sec_code,
            "ctl00$MainContent$LstUEstados": fecha_val,
            "ctl00$MainContent$ChkSeccion": "on",
            "__EVENTTARGET": "ctl00$MainContent$ChkSeccion",
            "__EVENTARGUMENT": "",
        }
        data.pop("ctl00$MainContent$ImgBuscar2", None)
        data.pop("ctl00$MainContent$ImgBuscar3", None)
        data.pop("ctl00$MainContent$CmdBuscar", None)
        res = self._fetch(session.post, _URL, data=data, timeout=30)
        return BeautifulSoup(res.text, "html.parser")

    def _step4b_consultar(self, session, soup_chk, corp_code, sec_code, fecha_val):
        data = {
            **_all_inputs(soup_chk),
            "ctl00$MainContent$LstCorpHabilitada": corp_code,
            "ctl00$MainContent$LstCoorporacion": sec_code,
            "ctl00$MainContent$LstUEstados": fecha_val,
            "ctl00$MainContent$ChkSeccion": "on",
            "ctl00$MainContent$LstCriterio": "Na",
            "ctl00$MainContent$Txtcriterio": "",
            "ctl00$MainContent$CmdBuscar": "Consultar",
        }
        data.pop("ctl00$MainContent$ImgBuscar2", None)
        data.pop("ctl00$MainContent$ImgBuscar3", None)
        return self._fetch(session.post, _URL, data=data, timeout=120).text

    def _scrap_corp(self, corp_code, corp_name, fini_dt, ffin_dt, stop_event, on_progress):
        session = self._new_session()
        soup1 = self._step1_get(session)
        soup2 = self._step2_select_corp(session, soup1, corp_code)

        sel_sec = soup2.find("select", {"id": "MainContent_LstCoorporacion"})
        if not sel_sec:
            return []

        secciones = [(o.get("value", ""), o.text.strip()) for o in sel_sec.find_all("option") if o.get("value")]

        def _process_section(sec_code, sec_name):
            try:
                s = self._new_session()
                s1 = self._step1_get(s)
                s2 = self._step2_select_corp(s, s1, corp_code)
                s3 = self._step3_select_section(s, s2, corp_code, sec_code)
                return self._scrap_section(
                    s, s3, corp_code, corp_name, sec_code, sec_name, fini_dt, ffin_dt, stop_event, on_progress
                )
            except Exception as e:
                if on_progress:
                    on_progress(f"[{corp_name}] Error en {sec_name}: {e}")
                return []

        docs = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(_process_section, sec_code, sec_name): sec_name for sec_code, sec_name in secciones
            }
            for future in as_completed(futures):
                if stop_event and stop_event.is_set():
                    break
                try:
                    docs.extend(future.result())
                except Exception:
                    pass

        return docs

    def _scrap_section(
        self, session, soup3, corp_code, corp_name, sec_code, sec_name, fini_dt, ffin_dt, stop_event, on_progress
    ):
        sel_fechas = soup3.find("select", {"id": "MainContent_LstUEstados"})
        if not sel_fechas:
            return []

        fechas_en_rango = []
        for opt in sel_fechas.find_all("option"):
            val = opt.get("value", "")
            if not val:
                continue
            try:
                dt = _parse_estado_date(val)
                if fini_dt <= dt <= ffin_dt:
                    fechas_en_rango.append((val, dt))
            except Exception:
                continue

        if not fechas_en_rango:
            return []

        docs = []
        for fecha_val, fecha_dt in fechas_en_rango:
            if stop_event and stop_event.is_set():
                break
            try:
                soup_chk = self._step4a_check_all(session, soup3, corp_code, sec_code, fecha_val)
                html = self._step4b_consultar(session, soup_chk, corp_code, sec_code, fecha_val)

                if "No hay resultados" in html:
                    continue

                soup4 = BeautifulSoup(html, "html.parser")
                gv = soup4.find("table", {"id": "MainContent_GvProvidencias"})
                if not gv:
                    continue

                estado_fecha_str = fecha_dt.strftime("%Y-%m-%d")

                for row in gv.find_all("tr")[1:]:
                    doc = self._parse_row(row, corp_code, corp_name, sec_name, estado_fecha_str)
                    if doc:
                        docs.append(doc)
            except Exception as e:
                if on_progress:
                    on_progress(f"[SAMAI] Error fecha {fecha_val} en {sec_name}: {e}")

        return docs

    def _parse_row(self, row, corp_code, corp_name, sec_name, estado_fecha_str):
        tds = row.find_all("td")
        if len(tds) < 10:
            return None

        radicado = tds[1].get_text(strip=True)
        actuacion = tds[7].get_text(strip=True)
        fecha_prov_raw = tds[6].get_text(strip=True)
        fecha_prov = _parse_prov_date(fecha_prov_raw)

        jwt_url = self._extract_jwt_url(tds[9])
        if not jwt_url:
            return None

        palabras = actuacion.split()
        tipo = _safe(palabras[0]) if palabras else ""
        seccion = _safe(sec_name, maxlen=100)
        safe_radicado = _safe(radicado)

        path = storage_path(corp_name, seccion, estado_fecha_str, tipo, f"{safe_radicado}(extension)")

        return RawDocModel(
            source=corp_name,
            link={"url": jwt_url, "method": "jwt_indirect", "body": {"path": f"{corp_code}_{radicado}"}},
            title=radicado,
            tipo=tipo,
            detalle=actuacion,
            seccion=seccion,
            f_public=estado_fecha_str,
            f_providencia=fecha_prov,
            save_path=path,
            convert_to="rtf_word",
        )

    @staticmethod
    def _extract_jwt_url(td) -> Optional[str]:
        a = td.find("a", class_=lambda c: c and "btn-success" in c)
        if not a:
            return None
        onclick = a.get("onclick", "")
        m = re.search(r"CargarVentana\('(https?://[^']+)'\)", onclick, re.IGNORECASE)
        return m.group(1) if m else None
```

- [ ] **Step 2: Register the family module**

Modify `core/scrapers/families/__init__.py`:

```python
from . import constitucional, samai  # noqa: F401
```

- [ ] **Step 3: Write the tests**

Create `tests/families/test_samai.py`:

```python
from bs4 import BeautifulSoup

from core.scrapers.families.samai import ScrapTribunales, _SAMAI_CORPS
from core.scrapers.registry import FAMILY_REGISTRY

_ROW_HTML = """
<tr>
  <td>0</td>
  <td>25001233300020260001200</td>
  <td>Juan Pérez</td>
  <td>3</td><td>4</td><td>5</td>
  <td>14/06/2026</td>
  <td>Auto que rechaza recurso de apelación</td>
  <td>8</td>
  <td><a class="btn-success" onclick="CargarVentana('https://samai.example.com/VerProvidencia?id=1')">Ver</a></td>
</tr>
"""


def test_samai_has_28_registered_tribunals():
    assert len(_SAMAI_CORPS) == 28
    assert _SAMAI_CORPS["1100103"] == "Consejo de Estado"


def test_samai_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["samai"] is ScrapTribunales


def test_parse_row_builds_expected_rawdocmodel():
    row = BeautifulSoup(_ROW_HTML, "html.parser").find("tr")
    scraper = ScrapTribunales(corp_code="2500023", corp_name="Tribunal Administrativo de Cundinamarca")

    doc = scraper._parse_row(row, "2500023", "Tribunal Administrativo de Cundinamarca", "Sección Primera", "2026-06-15")

    assert doc.title == "25001233300020260001200"
    assert doc.tipo == "Auto"
    assert doc.detalle == "Auto que rechaza recurso de apelación"
    assert doc.f_public == "2026-06-15"
    assert doc.f_providencia == "2026-06-14"
    assert doc.link["method"] == "jwt_indirect"
    assert doc.link["url"] == "https://samai.example.com/VerProvidencia?id=1"
    assert doc.link["body"] == {"path": "2500023_25001233300020260001200"}
    assert doc.convert_to == "rtf_word"


def test_parse_row_returns_none_without_jwt_link():
    html = _ROW_HTML.replace('<a class="btn-success"', '<a class="btn-other"')
    row = BeautifulSoup(html, "html.parser").find("tr")
    scraper = ScrapTribunales(corp_code="2500023", corp_name="Tribunal Administrativo de Cundinamarca")
    assert scraper._parse_row(row, "2500023", "Tribunal Administrativo de Cundinamarca", "Sección Primera", "2026-06-15") is None


def test_scrap_section_filters_dates_outside_range(monkeypatch):
    scraper = ScrapTribunales(corp_code="2500023", corp_name="Tribunal Administrativo de Cundinamarca")

    soup3 = BeautifulSoup(
        '<select id="MainContent_LstUEstados">'
        '<option value="15/06/2026 0:00:00">15/06/2026</option>'
        '<option value="15/01/2020 0:00:00">15/01/2020</option>'
        "</select>",
        "html.parser",
    )

    monkeypatch.setattr(scraper, "_step4a_check_all", lambda *a, **k: soup3)
    monkeypatch.setattr(
        scraper,
        "_step4b_consultar",
        lambda *a, **k: f'<table id="MainContent_GvProvidencias"><tr><th>h</th></tr>{_ROW_HTML}</table>',
    )

    from datetime import datetime

    docs = scraper._scrap_section(
        session=None,
        soup3=soup3,
        corp_code="2500023",
        corp_name="Tribunal Administrativo de Cundinamarca",
        sec_code="SEC1",
        sec_name="Sección Primera",
        fini_dt=datetime(2026, 6, 1),
        ffin_dt=datetime(2026, 6, 30),
        stop_event=None,
        on_progress=None,
    )

    # only the 15/06/2026 date is in range; the 2020 one is filtered out before any HTTP call
    assert len(docs) == 1
    assert docs[0].f_public == "2026-06-15"


def test_scrap_swallows_exceptions_and_returns_empty_list(monkeypatch):
    scraper = ScrapTribunales(corp_code="2500023", corp_name="Tribunal Administrativo de Cundinamarca")
    monkeypatch.setattr(scraper, "_scrap_corp", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sitio caído")))

    messages = []
    docs = scraper.scrap(fini="2026-06-01", ffin="2026-06-30", on_progress=messages.append)

    assert docs == []
    assert any("Error en" in m for m in messages)
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\pytest tests/families/test_samai.py -v`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/samai.py core/scrapers/families/__init__.py tests/families/test_samai.py
git commit -m "feat: port SAMAI scraper as the parameterized 'samai' family"
```

---

### Task 10: Celery app configuration

**Files:**
- Create: `worker/__init__.py`
- Create: `worker/celery_app.py`
- Test: `tests/test_celery_app.py`

**Interfaces:**
- Consumes: `core.config.get_settings()` (Task 1)
- Produces: `worker.celery_app.celery_app` (Celery instance)

- [ ] **Step 1: Create `worker/__init__.py`** (empty)

- [ ] **Step 2: Create `worker/celery_app.py`**

```python
from celery import Celery

from core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "iurisync",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["worker.tasks", "worker.beat_schedule"],
)
celery_app.conf.update(timezone="UTC", enable_utc=True)
```

- [ ] **Step 3: Write the test**

Create `tests/test_celery_app.py`:

```python
from worker.celery_app import celery_app


def test_celery_app_is_configured_with_redis_broker():
    assert celery_app.conf.broker_url.startswith("redis://")
    assert celery_app.conf.timezone == "UTC"
```

- [ ] **Step 4: Run the test**

Run: `.venv\Scripts\pytest tests/test_celery_app.py -v`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add worker/__init__.py worker/celery_app.py tests/test_celery_app.py
git commit -m "feat: configure Celery app with Redis broker/backend"
```

---

### Task 11: `scrape_source_task` — the per-source scraping pipeline

**Files:**
- Create: `worker/tasks.py`
- Modify: `tests/conftest.py` (add a dummy family fixture used only by tests)
- Test: `tests/test_tasks.py`

**Interfaces:**
- Consumes: `core.db.repository.*` (Task 3), `core.scrapers.registry.resolve_scraper` (Task 5), `core.downloader.Downloader` (Task 7), `core.storage.upload_file` (Task 6), `core.utils.compute_doc_id` (Task 4), `worker.celery_app.celery_app` (Task 10)
- Produces: `worker.tasks.scrape_source_task(run_source_id: int)` (Celery task)

- [ ] **Step 1: Create `worker/tasks.py`**

```python
import logging
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from core.db import repository
from core.db.session import SessionLocal
from core.downloader import Downloader
from core.scrapers import families  # noqa: F401 — ensures registry is populated
from core.scrapers.registry import resolve_scraper
from core.storage import upload_file
from core.utils import compute_doc_id
from worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _default_date_str(value: date | None) -> str:
    if value:
        return value.strftime("%Y-%m-%d")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@celery_app.task(name="worker.scrape_source_task", bind=True, max_retries=2, default_retry_delay=30)
def scrape_source_task(self, run_source_id: int):
    db = SessionLocal()
    try:
        run_source = repository.get_run_source(db, run_source_id)
        if run_source is None:
            return

        source = repository.get_source(db, run_source.source_id)
        run = repository.get_run(db, run_source.run_id)

        repository.set_run_source_status(db, run_source_id, "running", started_at=datetime.now(timezone.utc))

        try:
            scraper = resolve_scraper(source.family_key, source.family_params or {})
            fini = _default_date_str(run.fini)
            ffin = _default_date_str(run.ffin)
            docs = scraper.scrap(fini=fini, ffin=ffin)
        except Exception as exc:
            repository.set_run_source_status(
                db, run_source_id, "failed", error_message=str(exc), finished_at=datetime.now(timezone.utc)
            )
            return

        docs_new = 0
        docs_errors = 0
        downloader = Downloader()
        try:
            with tempfile.TemporaryDirectory(prefix=f"run_source_{run_source_id}_") as tmp_dir:
                tmp_path = Path(tmp_dir)
                for doc in docs:
                    if repository.is_cancel_requested(db, run.id):
                        break

                    doc_id = compute_doc_id(doc)
                    if repository.document_exists(db, doc_id):
                        continue

                    try:
                        result = downloader.download(doc, tmp_path)
                        bucket, storage_key = upload_file(result.local_path, result.storage_key)
                        repository.insert_document(
                            db,
                            doc_id=doc_id,
                            source_id=source.id,
                            run_source_id=run_source_id,
                            title=doc.title,
                            tipo=doc.tipo,
                            seccion=doc.seccion,
                            especialidad=doc.especialidad,
                            magistrado=doc.magistrado,
                            detalle=doc.detalle,
                            f_public=_parse_date(doc.f_public),
                            f_providencia=_parse_date(doc.f_providencia),
                            source_url=doc.link.get("url"),
                            storage_bucket=bucket,
                            storage_key=storage_key,
                            content_type=result.content_type,
                            file_extension=Path(result.storage_key).suffix,
                            file_size_bytes=result.file_size_bytes,
                            converted_format=doc.convert_to,
                        )
                        docs_new += 1
                    except FileNotFoundError as exc:
                        logger.info("Documento no disponible aún: %s", exc)
                        continue
                    except Exception as exc:
                        docs_errors += 1
                        repository.add_run_error(
                            db, run_source_id, str(exc), context={"title": doc.title, "url": doc.link.get("url")}
                        )
        finally:
            downloader.close()

        repository.set_run_source_status(
            db,
            run_source_id,
            "completed",
            docs_new=docs_new,
            docs_errors=docs_errors,
            finished_at=datetime.now(timezone.utc),
        )
    finally:
        db.close()
```

- [ ] **Step 2: Add a dummy in-process family for pipeline tests**

Modify `tests/conftest.py`, appending:

```python
from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family


@register_family("test-dummy")
class DummyFamilyScraper(BaseScrapper):
    """Registered once at test-collection time; used by pipeline tests instead of hitting a real site."""

    docs_to_return: list[RawDocModel] = []

    def __init__(self, **_params):
        pass

    def scrap(self, fini, ffin, **kwargs):
        return DummyFamilyScraper.docs_to_return
```

- [ ] **Step 3: Write the tests**

Create `tests/test_tasks.py`:

```python
import responses

from core.db import repository
from core.models import RawDocModel
from tests.conftest import DummyFamilyScraper, TEST_S3_BUCKET
from worker.celery_app import celery_app
from worker.tasks import scrape_source_task


@responses.activate
def test_scrape_source_task_downloads_new_document_and_marks_run_source_completed(db_session, monkeypatch):
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
        )
    ]
    responses.add(
        responses.GET,
        "https://example.com/doc1",
        body=b"contenido",
        headers={"Content-Type": "application/pdf"},
        status=200,
    )

    monkeypatch.setattr("worker.tasks.SessionLocal", lambda: db_session)
    monkeypatch.setattr("core.storage.get_settings", lambda: _settings_with_test_bucket())

    scrape_source_task(run_source.id)

    [refreshed] = repository.list_run_sources(db_session, run.id)
    assert refreshed.status == "completed"
    assert refreshed.docs_new == 1
    assert refreshed.docs_errors == 0


def _settings_with_test_bucket():
    from core.config import get_settings

    settings = get_settings()
    settings.s3_bucket = TEST_S3_BUCKET
    return settings
```

Note: `db_session.close()` being called inside the task (via its `finally: db.close()`) is harmless for the test's own `db_session` fixture teardown — SQLAlchemy sessions can be closed more than once safely, and the fixture only needs the session usable for the assertions that run before the task's `finally` block executes at the end of `scrape_source_task`. If this proves flaky in practice, replace the `monkeypatch.setattr("worker.tasks.SessionLocal", ...)` with a lambda that returns a **new** session bound to `test_engine` instead of reusing `db_session` directly, and re-query via a fresh session in the assertions.

- [ ] **Step 4: Run the test**

Run: `.venv\Scripts\pytest tests/test_tasks.py -v`
Expected: `1 passed` (requires `docker compose up -d` for Postgres + MinIO)

- [ ] **Step 5: Commit**

```bash
git add worker/tasks.py tests/conftest.py tests/test_tasks.py
git commit -m "feat: add scrape_source_task pipeline (scrape -> dedup -> download -> upload -> persist)"
```

---

### Task 12: Run orchestration (`orchestrate_run`, `finalize_run`, cancellation) and scheduled runs

**Files:**
- Modify: `worker/tasks.py` (add `orchestrate_run`, `finalize_run`)
- Create: `worker/beat_schedule.py`
- Test: `tests/test_orchestration.py`

**Interfaces:**
- Consumes: `worker.tasks.scrape_source_task` (Task 11), `core.db.repository.*` (Task 3)
- Produces: `worker.tasks.orchestrate_run(run_id, source_ids=None)`, `worker.tasks.finalize_run(_results, run_id)`, `worker.beat_schedule.trigger_scheduled_run`

- [ ] **Step 1: Add orchestration tasks to `worker/tasks.py`**

Append to `worker/tasks.py`:

```python
from celery import chord


@celery_app.task(name="worker.orchestrate_run")
def orchestrate_run(run_id: int, source_ids: list[int] | None = None):
    db = SessionLocal()
    try:
        repository.set_run_status(db, run_id, "running", started_at=datetime.now(timezone.utc))
        sources = repository.list_sources(db, active=True)
        if source_ids:
            wanted = set(source_ids)
            sources = [s for s in sources if s.id in wanted]

        run_source_ids = [repository.create_run_source(db, run_id=run_id, source_id=s.id).id for s in sources]
    finally:
        db.close()

    if not run_source_ids:
        _finalize_run(run_id)
        return

    chord((scrape_source_task.s(rsid) for rsid in run_source_ids), finalize_run.s(run_id)).apply_async()


@celery_app.task(name="worker.finalize_run")
def finalize_run(_results, run_id: int):
    _finalize_run(run_id)


def _finalize_run(run_id: int):
    db = SessionLocal()
    try:
        repository.set_run_status(db, run_id, "completed", finished_at=datetime.now(timezone.utc))
    finally:
        db.close()
```

- [ ] **Step 2: Create `worker/beat_schedule.py`**

```python
from celery.schedules import crontab

from core.db import repository
from core.db.session import SessionLocal
from worker.celery_app import celery_app
from worker.tasks import orchestrate_run


@celery_app.task(name="worker.trigger_scheduled_run")
def trigger_scheduled_run():
    db = SessionLocal()
    try:
        run = repository.create_run(db, triggered_by="scheduled", fini=None, ffin=None)
        run_id = run.id
    finally:
        db.close()
    orchestrate_run.delay(run_id)


celery_app.conf.beat_schedule = {
    "daily-scrape": {
        "task": "worker.trigger_scheduled_run",
        "schedule": crontab(hour=6, minute=0),
    },
}
```

- [ ] **Step 3: Write the tests**

Create `tests/test_orchestration.py`:

```python
from core.db import repository
from tests.conftest import DummyFamilyScraper
from core.models import RawDocModel
from worker.celery_app import celery_app
from worker.tasks import orchestrate_run


def test_orchestrate_run_creates_run_sources_and_completes_run(db_session, monkeypatch):
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    monkeypatch.setattr("worker.tasks.SessionLocal", lambda: db_session)

    repository.create_source_family(db_session, key="test-dummy", display_name="Dummy")
    source = repository.create_source(db_session, family_key="test-dummy", name="Dummy Source", family_params={})
    DummyFamilyScraper.docs_to_return = []

    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)

    orchestrate_run(run.id, source_ids=[source.id])

    run_sources = repository.list_run_sources(db_session, run.id)
    assert len(run_sources) == 1
    assert run_sources[0].status == "completed"

    refreshed_run = repository.get_run(db_session, run.id)
    assert refreshed_run.status == "completed"
    assert refreshed_run.finished_at is not None


def test_orchestrate_run_with_no_active_sources_still_completes(db_session, monkeypatch):
    monkeypatch.setattr("worker.tasks.SessionLocal", lambda: db_session)
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)

    orchestrate_run(run.id, source_ids=[999999])

    refreshed_run = repository.get_run(db_session, run.id)
    assert refreshed_run.status == "completed"
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\pytest tests/test_orchestration.py -v --deselect tests/test_orchestration.py::test_orchestrate_run_creates_run_sources_and_completes_run`

Run this deselect first only if the eager chord callback proves to need a real broker in your environment (Celery's `chord` callback dispatch can require a result backend even in eager mode); if `test_orchestrate_run_creates_run_sources_and_completes_run` fails with a backend-related error, replace the `chord(...).apply_async()` call in `orchestrate_run` with a simpler sequential fallback used automatically when `celery_app.conf.task_always_eager` is `True`:

```python
    if celery_app.conf.task_always_eager:
        results = [scrape_source_task.s(rsid).apply() for rsid in run_source_ids]
        finalize_run(results, run_id)
        return

    chord((scrape_source_task.s(rsid) for rsid in run_source_ids), finalize_run.s(run_id)).apply_async()
```

Then run: `.venv\Scripts\pytest tests/test_orchestration.py -v`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add worker/tasks.py worker/beat_schedule.py tests/test_orchestration.py
git commit -m "feat: add run orchestration (chord fan-out/fan-in) and daily Celery Beat schedule"
```

---

### Task 13: FastAPI skeleton, API key auth, and `/health`

**Files:**
- Create: `core/security.py`
- Create: `api/__init__.py`
- Create: `api/deps.py`
- Create: `api/main.py`
- Create: `api/routers/__init__.py`
- Create: `api/routers/health.py`
- Modify: `tests/conftest.py` (add `api_client` and `api_key_header` fixtures)
- Test: `tests/test_api_health.py`

**Interfaces:**
- Produces: `core.security.hash_api_key(raw: str) -> str`, `api.deps.get_db`, `api.deps.require_api_key`, `api.main.app`

- [ ] **Step 1: Create `core/security.py`**

```python
from hashlib import sha256


def hash_api_key(raw_key: str) -> str:
    return sha256(raw_key.encode("utf-8")).hexdigest()
```

- [ ] **Step 2: Create `api/__init__.py`** and **`api/routers/__init__.py`** (both empty)

- [ ] **Step 3: Create `api/deps.py`**

```python
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from core.db import repository
from core.db.session import get_db
from core.security import hash_api_key


def require_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
):
    api_key = repository.get_active_api_key_by_hash(db, hash_api_key(x_api_key))
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key inválida")
    return api_key
```

- [ ] **Step 4: Create `api/routers/health.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.db.session import get_db

router = APIRouter()


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
```

- [ ] **Step 5: Create `api/main.py`**

```python
from fastapi import FastAPI

from api.routers import health

app = FastAPI(title="IURISYNC Backend")
app.include_router(health.router)
```

- [ ] **Step 6: Add API test fixtures**

Modify `tests/conftest.py`, appending:

```python
@pytest.fixture()
def api_client(db_session):
    from fastapi.testclient import TestClient

    from api.deps import get_db
    from api.main import app

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def api_key_header(db_session):
    from core.db import repository
    from core.security import hash_api_key

    raw_key = "test-key-12345"
    repository.create_api_key(db_session, name="tests", key_hash=hash_api_key(raw_key))
    return {"X-API-Key": raw_key}
```

- [ ] **Step 7: Write the test**

Create `tests/test_api_health.py`:

```python
def test_health_check_does_not_require_api_key(api_client):
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 8: Run the test**

Run: `.venv\Scripts\pytest tests/test_api_health.py -v`
Expected: `1 passed`

- [ ] **Step 9: Commit**

```bash
git add core/security.py api/__init__.py api/deps.py api/main.py api/routers/__init__.py api/routers/health.py tests/conftest.py tests/test_api_health.py
git commit -m "feat: add FastAPI skeleton, API key auth dependency, and /health endpoint"
```

---

### Task 14: `/source-families` and `/sources` endpoints

**Files:**
- Create: `api/schemas.py`
- Create: `api/routers/sources.py`
- Modify: `api/main.py`
- Test: `tests/test_api_sources.py`

**Interfaces:**
- Consumes: `core.db.repository.*` (Task 3), `api.deps.get_db`, `api.deps.require_api_key` (Task 13)
- Produces: `api.schemas.SourceFamilyOut`, `SourceOut`, `SourceCreate`, `SourceUpdate`

- [ ] **Step 1: Create `api/schemas.py`**

```python
from typing import Optional

from pydantic import BaseModel, ConfigDict


class SourceFamilyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    display_name: str
    description: Optional[str] = None


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    family_key: str
    name: str
    family_params: dict
    active: bool


class SourceCreate(BaseModel):
    family_key: str
    name: str
    family_params: dict = {}
    active: bool = True


class SourceUpdate(BaseModel):
    active: Optional[bool] = None
    family_params: Optional[dict] = None
```

- [ ] **Step 2: Create `api/routers/sources.py`**

```python
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.deps import get_db, require_api_key
from api.schemas import SourceCreate, SourceFamilyOut, SourceOut, SourceUpdate
from core.db import repository

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/source-families", response_model=list[SourceFamilyOut])
def get_source_families(db: Session = Depends(get_db)):
    return repository.list_source_families(db)


@router.get("/sources", response_model=list[SourceOut])
def get_sources(family_key: Optional[str] = None, active: Optional[bool] = None, db: Session = Depends(get_db)):
    return repository.list_sources(db, family_key=family_key, active=active)


@router.post("/sources", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
def post_source(payload: SourceCreate, db: Session = Depends(get_db)):
    return repository.create_source(
        db, family_key=payload.family_key, name=payload.name, family_params=payload.family_params, active=payload.active
    )


@router.patch("/sources/{source_id}", response_model=SourceOut)
def patch_source(source_id: int, payload: SourceUpdate, db: Session = Depends(get_db)):
    source = repository.update_source(db, source_id, active=payload.active, family_params=payload.family_params)
    if source is None:
        raise HTTPException(status_code=404, detail="Fuente no encontrada")
    return source
```

- [ ] **Step 3: Wire the router**

Modify `api/main.py`:

```python
from fastapi import FastAPI

from api.routers import health, sources

app = FastAPI(title="IURISYNC Backend")
app.include_router(health.router)
app.include_router(sources.router)
```

- [ ] **Step 4: Write the tests**

Create `tests/test_api_sources.py`:

```python
def test_get_sources_requires_api_key(api_client):
    response = api_client.get("/sources")
    assert response.status_code == 422  # missing required X-API-Key header


def test_get_sources_rejects_invalid_key(api_client):
    response = api_client.get("/sources", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_create_and_list_source(api_client, api_key_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")

    create_response = api_client.post(
        "/sources",
        json={"family_key": "constitucional", "name": "Corte Constitucional", "family_params": {}},
        headers=api_key_header,
    )
    assert create_response.status_code == 201
    source_id = create_response.json()["id"]

    list_response = api_client.get("/sources", headers=api_key_header)
    assert list_response.status_code == 200
    assert [s["name"] for s in list_response.json()] == ["Corte Constitucional"]

    patch_response = api_client.patch(f"/sources/{source_id}", json={"active": False}, headers=api_key_header)
    assert patch_response.status_code == 200
    assert patch_response.json()["active"] is False


def test_patch_unknown_source_returns_404(api_client, api_key_header):
    response = api_client.patch("/sources/999999", json={"active": False}, headers=api_key_header)
    assert response.status_code == 404
```

- [ ] **Step 5: Run the tests**

Run: `.venv\Scripts\pytest tests/test_api_sources.py -v`
Expected: `4 passed`

- [ ] **Step 6: Commit**

```bash
git add api/schemas.py api/routers/sources.py api/main.py tests/test_api_sources.py
git commit -m "feat: add /source-families and /sources endpoints"
```

---

### Task 15: `/runs` endpoints

**Files:**
- Modify: `api/schemas.py`
- Create: `api/routers/runs.py`
- Modify: `api/main.py`
- Test: `tests/test_api_runs.py`

**Interfaces:**
- Consumes: `worker.tasks.orchestrate_run` (Task 12), `core.db.repository.*` (Task 3)
- Produces: `api.schemas.RunCreate`, `RunOut`, `RunSourceOut`

- [ ] **Step 1: Add schemas**

Modify `api/schemas.py`, appending:

```python
from datetime import date, datetime


class RunCreate(BaseModel):
    source_ids: Optional[list[int]] = None
    fini: Optional[date] = None
    ffin: Optional[date] = None


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    triggered_by: str
    status: str
    fini: Optional[date] = None
    ffin: Optional[date] = None
    cancel_requested: bool
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime


class RunSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    run_id: int
    source_id: int
    status: str
    docs_new: int
    docs_errors: int
    error_message: Optional[str] = None
```

(Move the `from datetime import date, datetime` to the top of the file alongside the existing `from typing import Optional` import rather than mid-file.)

- [ ] **Step 2: Create `api/routers/runs.py`**

```python
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.deps import get_db, require_api_key
from api.schemas import RunCreate, RunOut, RunSourceOut
from core.db import repository
from worker.tasks import orchestrate_run

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/runs", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
def post_run(payload: RunCreate, db: Session = Depends(get_db)):
    run = repository.create_run(db, triggered_by="manual", fini=payload.fini, ffin=payload.ffin)
    orchestrate_run.delay(run.id, payload.source_ids)
    return run


@router.get("/runs", response_model=list[RunOut])
def get_runs(status_filter: Optional[str] = None, db: Session = Depends(get_db)):
    return repository.list_runs(db, status=status_filter)


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = repository.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run no encontrado")
    return run


@router.get("/runs/{run_id}/sources", response_model=list[RunSourceOut])
def get_run_sources(run_id: int, db: Session = Depends(get_db)):
    return repository.list_run_sources(db, run_id)


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
def post_run_cancel(run_id: int, db: Session = Depends(get_db)):
    run = repository.request_run_cancel(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run no encontrado")
    return run
```

- [ ] **Step 3: Wire the router**

Modify `api/main.py`:

```python
from fastapi import FastAPI

from api.routers import health, runs, sources

app = FastAPI(title="IURISYNC Backend")
app.include_router(health.router)
app.include_router(sources.router)
app.include_router(runs.router)
```

- [ ] **Step 4: Write the tests**

Create `tests/test_api_runs.py`:

```python
def test_post_run_creates_run_and_dispatches_orchestration(api_client, api_key_header, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "api.routers.runs.orchestrate_run.delay", lambda run_id, source_ids: calls.append((run_id, source_ids))
    )

    response = api_client.post("/runs", json={"source_ids": [1, 2]}, headers=api_key_header)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["triggered_by"] == "manual"
    assert calls == [(body["id"], [1, 2])]


def test_get_run_returns_404_for_unknown_id(api_client, api_key_header):
    response = api_client.get("/runs/999999", headers=api_key_header)
    assert response.status_code == 404


def test_cancel_run_sets_cancel_requested(api_client, api_key_header, monkeypatch, db_session):
    from core.db import repository

    monkeypatch.setattr("api.routers.runs.orchestrate_run.delay", lambda *a, **k: None)

    create_response = api_client.post("/runs", json={}, headers=api_key_header)
    run_id = create_response.json()["id"]

    cancel_response = api_client.post(f"/runs/{run_id}/cancel", headers=api_key_header)
    assert cancel_response.status_code == 200
    assert cancel_response.json()["cancel_requested"] is True
```

- [ ] **Step 5: Run the tests**

Run: `.venv\Scripts\pytest tests/test_api_runs.py -v`
Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add api/schemas.py api/routers/runs.py api/main.py tests/test_api_runs.py
git commit -m "feat: add /runs endpoints (trigger, list, detail, per-source, cancel)"
```

---

### Task 16: `/documents` endpoints

**Files:**
- Modify: `api/schemas.py`
- Create: `api/routers/documents.py`
- Modify: `api/main.py`
- Test: `tests/test_api_documents.py`

**Interfaces:**
- Consumes: `core.db.repository.list_documents`, `get_document` (Task 3), `core.storage.presigned_url` (Task 6)
- Produces: `api.schemas.DocumentOut`, `PaginatedDocuments`

- [ ] **Step 1: Add schemas**

Modify `api/schemas.py`, appending:

```python
class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    doc_id: str
    source_id: int
    title: str
    tipo: Optional[str] = None
    seccion: Optional[str] = None
    f_public: Optional[date] = None
    f_providencia: Optional[date] = None
    storage_bucket: str
    storage_key: str
    content_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    downloaded_at: datetime


class PaginatedDocuments(BaseModel):
    items: list[DocumentOut]
    total: int
    limit: int
    offset: int
```

- [ ] **Step 2: Create `api/routers/documents.py`**

```python
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from api.deps import get_db, require_api_key
from api.schemas import DocumentOut, PaginatedDocuments
from core.db import repository
from core.storage import presigned_url

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/documents", response_model=PaginatedDocuments)
def get_documents(
    source_id: Optional[int] = None,
    family_key: Optional[str] = None,
    tipo: Optional[str] = None,
    title: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    items, total = repository.list_documents(
        db, source_id=source_id, family_key=family_key, tipo=tipo, title_contains=title, limit=limit, offset=offset
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, db: Session = Depends(get_db)):
    document = repository.get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return document


@router.get("/documents/{document_id}/download")
def download_document(document_id: int, db: Session = Depends(get_db)):
    document = repository.get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    url = presigned_url(document.storage_bucket, document.storage_key)
    return RedirectResponse(url)
```

- [ ] **Step 3: Wire the router**

Modify `api/main.py`:

```python
from fastapi import FastAPI

from api.routers import documents, health, runs, sources

app = FastAPI(title="IURISYNC Backend")
app.include_router(health.router)
app.include_router(sources.router)
app.include_router(runs.router)
app.include_router(documents.router)
```

- [ ] **Step 4: Write the tests**

Create `tests/test_api_documents.py`:

```python
def test_list_documents_paginates_and_filters(api_client, api_key_header, db_session):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-02-01/Sentencia/T-065-24.rtf",
    )

    response = api_client.get("/documents", headers=api_key_header)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["doc_id"] == "doc-1"


def test_get_document_returns_404_when_missing(api_client, api_key_header):
    response = api_client.get("/documents/999999", headers=api_key_header)
    assert response.status_code == 404


def test_download_document_redirects_to_presigned_url(api_client, api_key_header, db_session, monkeypatch):
    from core.db import repository

    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    document = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T-065/24",
        storage_bucket="iurisync-test",
        storage_key="Corte Constitucional/2024-02-01/Sentencia/T-065-24.rtf",
    )

    monkeypatch.setattr("api.routers.documents.presigned_url", lambda bucket, key: "https://signed.example.com/file")

    response = api_client.get(f"/documents/{document.id}/download", headers=api_key_header, follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "https://signed.example.com/file"
```

- [ ] **Step 5: Run the tests**

Run: `.venv\Scripts\pytest tests/test_api_documents.py -v`
Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add api/schemas.py api/routers/documents.py api/main.py tests/test_api_documents.py
git commit -m "feat: add /documents endpoints (list, detail, presigned download redirect)"
```

---

### Task 17: API key management CLI

**Files:**
- Create: `core/manage.py`
- Test: `tests/test_manage.py`

**Interfaces:**
- Consumes: `core.db.repository.create_api_key` (Task 3), `core.security.hash_api_key` (Task 13)
- Produces: `core.manage.create_api_key(db, name) -> str`

- [ ] **Step 1: Create `core/manage.py`**

```python
import argparse
import secrets

from core.db import repository
from core.db.session import SessionLocal
from core.security import hash_api_key


def create_api_key(db, name: str) -> str:
    raw_key = secrets.token_urlsafe(32)
    repository.create_api_key(db, name=name, key_hash=hash_api_key(raw_key))
    return raw_key


def main():
    parser = argparse.ArgumentParser(prog="manage")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create-api-key")
    create_parser.add_argument("--name", required=True)

    args = parser.parse_args()

    if args.command == "create-api-key":
        db = SessionLocal()
        try:
            raw_key = create_api_key(db, args.name)
        finally:
            db.close()
        print(f"API key creada para '{args.name}': {raw_key}")
        print("Guárdala ahora; no se puede recuperar después (solo se almacena su hash).")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write the test**

Create `tests/test_manage.py`:

```python
from core.db import repository
from core.manage import create_api_key
from core.security import hash_api_key


def test_create_api_key_returns_raw_key_and_stores_only_its_hash(db_session):
    raw_key = create_api_key(db_session, "integración-tests")

    assert len(raw_key) > 20
    found = repository.get_active_api_key_by_hash(db_session, hash_api_key(raw_key))
    assert found is not None
    assert found.name == "integración-tests"
```

- [ ] **Step 3: Run the test**

Run: `.venv\Scripts\pytest tests/test_manage.py -v`
Expected: `1 passed`

- [ ] **Step 4: Commit**

```bash
git add core/manage.py tests/test_manage.py
git commit -m "feat: add CLI for minting API keys (python -m core.manage create-api-key)"
```

---

### Task 18: Seed script for `source_families`/`sources`

**Files:**
- Create: `core/seed.py`
- Test: `tests/test_seed.py`

**Interfaces:**
- Consumes: `core.db.repository.*` (Task 3), `core.scrapers.families.samai._SAMAI_CORPS` (Task 9)
- Produces: `core.seed.seed_source_families_and_sources(db) -> None`

- [ ] **Step 1: Create `core/seed.py`**

```python
from core.db import repository
from core.db.session import SessionLocal
from core.scrapers.families.samai import _SAMAI_CORPS

_FAMILIES = {
    "constitucional": ("Corte Constitucional", "Buscador de relatoría de la Corte Constitucional"),
    "samai": (
        "SAMAI (Tribunales Administrativos)",
        "Sistema SAMAI del Consejo de Estado; cubre Consejo de Estado y Tribunales Administrativos",
    ),
}


def seed_source_families_and_sources(db) -> None:
    existing_families = {f.key for f in repository.list_source_families(db)}
    for key, (display_name, description) in _FAMILIES.items():
        if key not in existing_families:
            repository.create_source_family(db, key=key, display_name=display_name, description=description)

    existing_sources = {s.name for s in repository.list_sources(db)}

    if "Corte Constitucional" not in existing_sources:
        repository.create_source(db, family_key="constitucional", name="Corte Constitucional", family_params={})

    for corp_code, corp_name in _SAMAI_CORPS.items():
        if corp_name not in existing_sources:
            repository.create_source(
                db, family_key="samai", name=corp_name, family_params={"corp_code": corp_code, "corp_name": corp_name}
            )


def main():
    db = SessionLocal()
    try:
        seed_source_families_and_sources(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write the test**

Create `tests/test_seed.py`:

```python
from core.db import repository
from core.seed import seed_source_families_and_sources


def test_seed_populates_families_and_sources_and_is_idempotent(db_session):
    seed_source_families_and_sources(db_session)
    seed_source_families_and_sources(db_session)  # running twice must not duplicate rows

    families = repository.list_source_families(db_session)
    assert {f.key for f in families} == {"constitucional", "samai"}

    sources = repository.list_sources(db_session)
    assert len(sources) == 1 + 28  # Corte Constitucional + 28 SAMAI corps

    samai_sources = repository.list_sources(db_session, family_key="samai")
    assert any(s.family_params.get("corp_code") == "1100103" for s in samai_sources)
```

- [ ] **Step 3: Run the test**

Run: `.venv\Scripts\pytest tests/test_seed.py -v`
Expected: `1 passed`

- [ ] **Step 4: Seed the local dev database**

Run: `.venv\Scripts\python -m core.seed`
Expected: no output on success (idempotent); confirm with `docker compose exec postgres psql -U iurisync -d iurisync -c "SELECT count(*) FROM sources;"` → `29`

- [ ] **Step 5: Commit**

```bash
git add core/seed.py tests/test_seed.py
git commit -m "feat: add idempotent seed script for source_families and sources (constitucional + 28 SAMAI corps)"
```

---

### Task 19: CI workflow and README

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `README.md`

**Interfaces:**
- Consumes: everything above
- Produces: a runnable CI pipeline and onboarding docs; no new Python interfaces

- [ ] **Step 1: Create `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: iurisync
          POSTGRES_PASSWORD: iurisync
          POSTGRES_DB: iurisync_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U iurisync"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Start MinIO
        run: |
          docker run -d --name minio -p 9000:9000 -p 9001:9001 \
            -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \
            minio/minio server /data --console-address ":9001"
          sleep 5
      - name: Run migrations
        env:
          DATABASE_URL: postgresql+psycopg://iurisync:iurisync@localhost:5432/iurisync_test
        run: alembic upgrade head
      - name: Run tests
        env:
          TEST_DATABASE_URL: postgresql+psycopg://iurisync:iurisync@localhost:5432/iurisync_test
          TEST_S3_ENDPOINT_URL: http://localhost:9000
        run: pytest -v
```

Note: `pywin32` is skipped automatically on this `ubuntu-latest` runner via the `platform_system == "Windows"` marker in `requirements.txt` — the RTF conversion tests exercise the `pypdf` fallback path only (Task 7), which is exactly what Task 7's monkeypatch-based test already verifies deterministically, independent of the OS.

- [ ] **Step 2: Create `README.md`**

```markdown
# IURISYNC Backend

Backend SaaS de scraping de fuentes jurídicas/administrativas colombianas. Reutiliza los scrapers de `WebScrapping_Fuentes`, organizados por "familia técnica", con almacenamiento estructurado en PostgreSQL y archivos en un object storage S3-compatible.

## Setup local

1. `python -m venv .venv && .venv\Scripts\pip install -r requirements.txt`
2. `copy .env.example .env`
3. `docker compose up -d` (Postgres, Redis, MinIO)
4. `docker compose exec postgres psql -U iurisync -d iurisync -c "CREATE DATABASE iurisync_test;"`
5. `.venv\Scripts\alembic upgrade head`
6. `.venv\Scripts\python -m core.seed` (puebla `source_families`/`sources`)
7. `.venv\Scripts\python -m core.manage create-api-key --name "mi-equipo"` (guarda la key impresa)

## Correr los servicios

- API: `.venv\Scripts\uvicorn api.main:app --reload --port 8000`
- Worker: `.venv\Scripts\celery -A worker.celery_app worker --pool=solo --loglevel=info`
- Beat (scheduler diario): `.venv\Scripts\celery -A worker.celery_app beat --loglevel=info`

## Tests

`.venv\Scripts\pytest -v` (requiere `docker compose up -d` para las pruebas de integración con Postgres/MinIO).

## Alcance

Este repo porta dos familias de scraping como prueba del modelo (`constitucional`, `samai`). Las demás familias de `WebScrapping_Fuentes` (Corte Suprema, JEP, CNDJ, Rama Judicial, ADR, ADRES, ANE, ANH) se portan siguiendo el mismo patrón de `core/scrapers/families/` + `@register_family(...)` como trabajo de seguimiento.
```

- [ ] **Step 3: Verify the whole suite green locally**

Run: `.venv\Scripts\pytest -v`
Expected: all tests from Tasks 1–18 pass.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml README.md
git commit -m "chore: add CI workflow and README"
```

---

## Follow-up work (explicitly not in this plan)

- Port the remaining scraper families (Corte Suprema, JEP, CNDJ, Rama Judicial, ADR, ADRES, ANE, ANH) using the pattern from Tasks 8–9, plus seeding their `sources` rows.
- Frontend/dashboard consuming this API (separate spec + plan).
- Real-time progress (SSE/WebSockets) once a frontend exists.
