from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import Date as SqlDate
from sqlalchemy import cast, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from core.db.models import BulkDownload, Document, DocumentVersion, Run, RunError, RunSource, Source, SourceFamily, User, UserSession


def list_source_families(db: Session) -> list[SourceFamily]:
    return list(db.scalars(select(SourceFamily)).all())


def create_source_family(db: Session, key: str, display_name: str, description: Optional[str] = None) -> SourceFamily:
    family = SourceFamily(key=key, display_name=display_name, description=description)
    db.add(family)
    db.commit()
    db.refresh(family)
    return family


def get_source_family(db: Session, key: str) -> Optional[SourceFamily]:
    return db.get(SourceFamily, key)


def list_sources(
    db: Session,
    family_key: Optional[str] = None,
    active: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Source]:
    stmt = select(Source)
    if family_key is not None:
        stmt = stmt.where(Source.family_key == family_key)
    if active is not None:
        stmt = stmt.where(Source.active == active)
    stmt = stmt.order_by(Source.id).limit(limit).offset(offset)
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


def list_runs(db: Session, status: Optional[str] = None, limit: int = 100, offset: int = 0) -> list[Run]:
    stmt = select(Run).order_by(Run.created_at.desc(), Run.id.desc())
    if status is not None:
        stmt = stmt.where(Run.status == status)
    stmt = stmt.limit(limit).offset(offset)
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


def create_bulk_download(db: Session) -> BulkDownload:
    bulk_download = BulkDownload(status="pending")
    db.add(bulk_download)
    db.commit()
    db.refresh(bulk_download)
    return bulk_download


def get_bulk_download(db: Session, bulk_download_id: int) -> Optional[BulkDownload]:
    return db.get(BulkDownload, bulk_download_id)


def list_bulk_downloads(db: Session, limit: int = 50, offset: int = 0) -> list[BulkDownload]:
    stmt = (
        select(BulkDownload)
        .order_by(BulkDownload.created_at.desc(), BulkDownload.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt).all())


def set_bulk_download_status(db: Session, bulk_download_id: int, status: str, **fields) -> None:
    bulk_download = db.get(BulkDownload, bulk_download_id)
    bulk_download.status = status
    for key, value in fields.items():
        setattr(bulk_download, key, value)
    db.commit()


def list_useful_documents(db: Session) -> list[Document]:
    stmt = select(Document).where(Document.review_status == "useful")
    return list(db.scalars(stmt).all())


def document_exists(db: Session, doc_id: str) -> bool:
    stmt = select(Document.id).where(Document.doc_id == doc_id)
    return db.scalars(stmt).first() is not None


def insert_document(db: Session, **fields) -> Optional[Document]:
    stmt = pg_insert(Document).values(**fields).on_conflict_do_nothing(index_elements=["doc_id"])
    db.execute(stmt)
    db.commit()
    return db.scalars(select(Document).where(Document.doc_id == fields["doc_id"])).first()


def get_document_by_doc_id(db: Session, doc_id: str) -> Optional[Document]:
    return db.scalars(select(Document).where(Document.doc_id == doc_id)).first()


def archive_and_replace_document(
    db: Session, document_id: int, review_status: str = "pending", **new_fields
) -> Document:
    document = db.get(Document, document_id)
    version = DocumentVersion(
        document_id=document.id,
        storage_bucket=document.storage_bucket,
        storage_key=document.storage_key,
        content_type=document.content_type,
        file_extension=document.file_extension,
        file_size_bytes=document.file_size_bytes,
        converted_format=document.converted_format,
        source_url=document.source_url,
        downloaded_at=document.downloaded_at,
    )
    db.add(version)
    for key, value in new_fields.items():
        setattr(document, key, value)
    document.downloaded_at = datetime.now(timezone.utc)
    # A source configured with family_params.auto_review_status (e.g. "el equipo
    # de fuentes" declaring everything from Corte Constitucional useful) should
    # keep landing there on republication too, not reset to "pending" — callers
    # pass that override in; it defaults to the original "always reset" behavior.
    document.review_status = review_status
    document.reviewed_at = None
    db.commit()
    db.refresh(document)
    return document


def list_document_versions(db: Session, document_id: int) -> list[DocumentVersion]:
    stmt = (
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.superseded_at.desc())
    )
    return list(db.scalars(stmt).all())


def get_document_version(db: Session, version_id: int) -> Optional[DocumentVersion]:
    return db.get(DocumentVersion, version_id)


def list_distinct_document_tipos(db: Session, source_id: Optional[int] = None) -> list[str]:
    stmt = select(Document.tipo).distinct().where(Document.tipo.is_not(None))
    if source_id is not None:
        stmt = stmt.where(Document.source_id == source_id)
    stmt = stmt.order_by(Document.tipo)
    return list(db.scalars(stmt).all())


def list_documents(
    db: Session,
    source_id: Optional[int] = None,
    family_key: Optional[str] = None,
    tipo: Optional[str] = None,
    review_status: Optional[str] = None,
    f_public_from: Optional[date] = None,
    f_public_to: Optional[date] = None,
    downloaded_from: Optional[date] = None,
    downloaded_to: Optional[date] = None,
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
    if review_status is not None:
        stmt = stmt.where(Document.review_status == review_status)
    if f_public_from is not None:
        stmt = stmt.where(Document.f_public >= f_public_from)
    if f_public_to is not None:
        stmt = stmt.where(Document.f_public <= f_public_to)
    if downloaded_from is not None:
        stmt = stmt.where(
            Document.downloaded_at >= datetime.combine(downloaded_from, datetime.min.time()).replace(tzinfo=timezone.utc)
        )
    if downloaded_to is not None:
        stmt = stmt.where(
            Document.downloaded_at
            < datetime.combine(downloaded_to, datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(days=1)
        )
    if title_contains is not None:
        stmt = stmt.where(Document.title.ilike(f"%{title_contains}%"))

    total = len(list(db.scalars(stmt).all()))
    stmt = stmt.order_by(Document.f_public.desc().nulls_last(), Document.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all()), total


def count_documents_by_family(db: Session) -> list[tuple[str, int]]:
    stmt = (
        select(Source.family_key, func.count(Document.id))
        .select_from(Document)
        .join(Source, Source.id == Document.source_id)
        .group_by(Source.family_key)
        .order_by(func.count(Document.id).desc())
    )
    return list(db.execute(stmt).all())


def count_documents_by_tipo(db: Session, limit: int = 8) -> list[tuple[str, int]]:
    tipo_expr = func.coalesce(Document.tipo, "Sin tipo")
    stmt = (
        select(tipo_expr, func.count(Document.id))
        .group_by(tipo_expr)
        .order_by(func.count(Document.id).desc())
        .limit(limit)
    )
    return list(db.execute(stmt).all())


def _effective_date_expr():
    # Dashboard charts bucket documents by fecha de publicación, falling back to
    # downloaded_at for the (rare) document that scraped without one — same
    # fallback the frontend used to apply client-side before this endpoint existed.
    return func.coalesce(Document.f_public, cast(Document.downloaded_at, SqlDate))


def list_document_years(db: Session) -> list[int]:
    year_expr = func.extract("year", _effective_date_expr())
    stmt = select(year_expr).distinct()
    years = [int(year) for (year,) in db.execute(stmt).all() if year is not None]
    return sorted(years, reverse=True)


def count_documents_by_month(db: Session, year: int) -> list[int]:
    date_expr = _effective_date_expr()
    stmt = (
        select(func.extract("month", date_expr), func.count(Document.id))
        .where(func.extract("year", date_expr) == year)
        .group_by(func.extract("month", date_expr))
    )
    counts = [0] * 12
    for month, count in db.execute(stmt).all():
        counts[int(month) - 1] = count
    return counts


def update_document_review_status(db: Session, document_id: int, review_status: str) -> Optional[Document]:
    document = db.get(Document, document_id)
    if document is None:
        return None
    document.review_status = review_status
    document.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(document)
    return document


def update_document_title(db: Session, document_id: int, title: str) -> Optional[Document]:
    document = db.get(Document, document_id)
    if document is None:
        return None
    document.title = title
    db.commit()
    db.refresh(document)
    return document


def bulk_update_document_review_status(db: Session, document_ids: list[int], review_status: str) -> int:
    stmt = (
        update(Document)
        .where(Document.id.in_(document_ids))
        .values(review_status=review_status, reviewed_at=datetime.now(timezone.utc))
    )
    result = db.execute(stmt)
    db.commit()
    return result.rowcount


def get_document(db: Session, document_id: int) -> Optional[Document]:
    return db.get(Document, document_id)


SESSION_TTL = timedelta(days=30)


def create_user(db: Session, username: str, password_hash: str) -> User:
    user = User(username=username, password_hash=password_hash, active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    stmt = select(User).where(User.username == username)
    return db.scalars(stmt).first()


def create_session(db: Session, user_id: int, token_hash: str) -> UserSession:
    now = datetime.now(timezone.utc)
    session = UserSession(user_id=user_id, token_hash=token_hash, expires_at=now + SESSION_TTL)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_valid_session_by_token_hash(db: Session, token_hash: str) -> Optional[UserSession]:
    stmt = select(UserSession).where(
        UserSession.token_hash == token_hash,
        UserSession.expires_at > datetime.now(timezone.utc),
    )
    return db.scalars(stmt).first()


def touch_session(db: Session, session_id: int) -> None:
    session = db.get(UserSession, session_id)
    now = datetime.now(timezone.utc)
    session.last_used_at = now
    session.expires_at = now + SESSION_TTL
    db.commit()


def delete_session(db: Session, token_hash: str) -> None:
    stmt = select(UserSession).where(UserSession.token_hash == token_hash)
    session = db.scalars(stmt).first()
    if session is not None:
        db.delete(session)
        db.commit()


def update_user_password(db: Session, user_id: int, password_hash: str) -> None:
    user = db.get(User, user_id)
    user.password_hash = password_hash
    db.commit()


def touch_user_last_login(db: Session, user_id: int) -> None:
    user = db.get(User, user_id)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()


def set_document_preview_key(db: Session, document_id: int, preview_storage_key: str) -> Optional[Document]:
    document = db.get(Document, document_id)
    if document is None:
        return None
    document.preview_storage_key = preview_storage_key
    db.commit()
    db.refresh(document)
    return document
