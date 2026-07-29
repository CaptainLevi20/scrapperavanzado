from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import Date as SqlDate
from sqlalchemy import and_, cast, delete, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, aliased

from core.db.models import BulkDownload, Document, DocumentVersion, Run, RunError, RunSource, Source, SourceFamily, User, UserSession
from core.utils import RADICADO_TITLE_PATTERN, SAMAI_CASE_TITLE_PATTERN

_LIKE_ESCAPE_CHAR = "\\"

# Familias cuyo título identifica el CASO (no una actuación puntual), así que varias
# filas distintas pueden compartir el mismo título legítimamente — cada una de estas
# entradas es "family_key -> patrón que confirma que el título sí tiene esa forma"
# (nunca un título de respaldo, como el nombre de un magistrado, que puede repetirse
# sin ser el mismo caso).
_CASE_GROUPING_FAMILY_PATTERNS = {
    "rama_judicial": RADICADO_TITLE_PATTERN,
    "samai": SAMAI_CASE_TITLE_PATTERN,
}


def _escape_like(value: str) -> str:
    """Escapes LIKE/ILIKE metacharacters in user-typed search text so they're
    matched as literal characters instead of wildcards. Without this, '_'
    (matches any single character) and '%' (matches any run of characters) in
    a search term act as wildcards rather than the literal text the user
    typed — real-world impact: Rama Judicial titles are full of underscores
    (e.g. "T_BTA_11001_..."), so a radicado search could silently match
    unrelated documents. Pair with `.ilike(pattern, escape=_LIKE_ESCAPE_CHAR)`."""
    escaped = value.replace(_LIKE_ESCAPE_CHAR, _LIKE_ESCAPE_CHAR * 2)
    return escaped.replace("%", f"{_LIKE_ESCAPE_CHAR}%").replace("_", f"{_LIKE_ESCAPE_CHAR}_")


def list_source_families(db: Session) -> list[SourceFamily]:
    return list(db.scalars(select(SourceFamily)).all())


def create_source_family(db: Session, key: str, display_name: str, description: Optional[str] = None) -> SourceFamily:
    family = SourceFamily(key=key, display_name=display_name, description=description)
    db.add(family)
    db.commit()
    db.refresh(family)
    return family


def create_source_family_if_missing(
    db: Session, key: str, display_name: str, description: Optional[str] = None
) -> None:
    """Idempotent insert used only by core/seed.py. Unlike create_source_family
    (used by the interactive "create source" flow, where a duplicate name
    should surface as an error), two seed runs racing each other — `python -m
    core.seed` launched twice at once, or a future multi-worker startup hook —
    must not crash on a duplicate primary key; the second insert is just a
    no-op instead."""
    stmt = (
        pg_insert(SourceFamily)
        .values(key=key, display_name=display_name, description=description)
        .on_conflict_do_nothing(index_elements=["key"])
    )
    db.execute(stmt)
    db.commit()


def get_source_family(db: Session, key: str) -> Optional[SourceFamily]:
    return db.get(SourceFamily, key)


def list_sources(
    db: Session,
    id: Optional[int] = None,
    family_key: Optional[str] = None,
    active: Optional[bool] = None,
    has_documents: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Source]:
    stmt = select(Source)
    if id is not None:
        stmt = stmt.where(Source.id == id)
    if family_key is not None:
        stmt = stmt.where(Source.family_key == family_key)
    if active is not None:
        stmt = stmt.where(Source.active == active)
    if has_documents is not None:
        has_docs_clause = exists().where(Document.source_id == Source.id)
        stmt = stmt.where(has_docs_clause if has_documents else ~has_docs_clause)
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


def create_source_if_missing(db: Session, family_key: str, name: str, family_params: dict) -> None:
    """Idempotent insert used only by core/seed.py — see create_source_family_if_missing."""
    stmt = (
        pg_insert(Source)
        .values(family_key=family_key, name=name, family_params=family_params, active=True)
        .on_conflict_do_nothing(index_elements=["name"])
    )
    db.execute(stmt)
    db.commit()


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
    if run is None:
        return
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
    if run_source is None:
        return
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
    if bulk_download is None:
        return
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


def _insert_document_and_report_if_created(db: Session, fields: dict) -> tuple[Optional[Document], bool]:
    # RETURNING on an ON CONFLICT DO NOTHING statement yields a row only when the
    # insert actually happened — nothing comes back when it was skipped because
    # doc_id already existed. That's the only reliable way to distinguish "I just
    # created this" from "this was already there" without a separate SELECT
    # racing the insert itself.
    stmt = (
        pg_insert(Document)
        .values(**fields)
        .on_conflict_do_nothing(index_elements=["doc_id"])
        .returning(Document.id)
    )
    inserted_id = db.execute(stmt).scalar()
    db.commit()
    document = db.scalars(select(Document).where(Document.doc_id == fields["doc_id"])).first()
    return document, inserted_id is not None


def insert_document(db: Session, **fields) -> Optional[Document]:
    document, _created = _insert_document_and_report_if_created(db, fields)
    return document


def insert_document_reporting_whether_created(db: Session, **fields) -> tuple[Optional[Document], bool]:
    """Same as insert_document, but also reports whether this call actually
    inserted a new row versus a no-op (the doc_id already existed, either from
    the DB or elsewhere in the same scrap() batch). Used by worker/tasks.py so
    its docs_new counter reflects documents genuinely inserted — not just "we
    attempted an insert" — even in the residual case of two different
    run_sources racing to insert the same document at the same time."""
    return _insert_document_and_report_if_created(db, fields)


def get_document_by_doc_id(db: Session, doc_id: str) -> Optional[Document]:
    return db.scalars(select(Document).where(Document.doc_id == doc_id)).first()


def archive_and_replace_document(
    db: Session, document_id: int, review_status: str = "pending", **new_fields
) -> Document:
    # with_for_update() locks the row for the duration of this transaction: a second,
    # concurrent republication of the same document (two overlapping runs touching the
    # same source — see worker/tasks.py's per-RunSource Celery tasks and its own thread
    # pool) must block here and re-read the first write's result, rather than both
    # reading the same stale row and one silently overwriting the other's archived
    # version. Without this, the loser's write survives with a DocumentVersion that
    # doesn't actually match what was archived.
    document = db.scalars(select(Document).where(Document.id == document_id).with_for_update()).first()
    if document is None:
        # The document was deleted between being listed as a republication candidate
        # and this write — nothing to archive or replace. The caller (worker/tasks.py)
        # already treats any exception here as a per-document failure, not a fatal one.
        raise ValueError(f"El documento {document_id} ya no existe (fue eliminado).")
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
    title_exact: Optional[str] = None,
    collapse_case_families: bool = False,
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
        stmt = stmt.where(Document.title.ilike(f"%{_escape_like(title_contains)}%", escape=_LIKE_ESCAPE_CHAR))
    if title_exact is not None:
        stmt = stmt.where(Document.title == title_exact)
    if collapse_case_families:
        # Only affects documents, in one of _CASE_GROUPING_FAMILY_PATTERNS, whose
        # title genuinely matches that family's case-title format (never a scraper
        # fallback title like a magistrado's name, which can legitimately repeat
        # without being the same case) — a document is dropped from the general
        # listing only if a NEWER actuación (by f_public, ties broken by id)
        # sharing that exact title exists within the SAME family. Every other
        # document (any other family, or a non-case-format title) is entirely
        # unaffected by this clause regardless of what it happens to share a title
        # string with.
        OuterSource = aliased(Source)
        OtherDoc = aliased(Document)
        OtherSource = aliased(Source)
        # f_public is nullable — a bare comparison against NULL is never true in SQL,
        # so two NULL-f_public siblings could otherwise both "have no newer sibling"
        # and both survive. Coalescing to date.min treats a missing publication date
        # as the oldest possible, so the id tie-break still deterministically applies.
        other_f_public = func.coalesce(OtherDoc.f_public, date.min)
        this_f_public = func.coalesce(Document.f_public, date.min)
        has_newer_sibling = (
            select(OtherDoc.id)
            .join(OtherSource, OtherSource.id == OtherDoc.source_id)
            .where(
                OtherSource.family_key == OuterSource.family_key,
                OtherDoc.title == Document.title,
                or_(
                    other_f_public > this_f_public,
                    and_(other_f_public == this_f_public, OtherDoc.id > Document.id),
                ),
            )
            .exists()
        )
        is_case_title = or_(
            *[
                and_(OuterSource.family_key == family_key, Document.title.op("~")(pattern.pattern))
                for family_key, pattern in _CASE_GROUPING_FAMILY_PATTERNS.items()
            ]
        )
        stmt = stmt.join(OuterSource, OuterSource.id == Document.source_id).where(
            or_(~is_case_title, ~has_newer_sibling)
        )

    # COUNT via a subquery instead of materializing every matching Document row
    # just to call len() on them — the previous approach got slower with every
    # document added to the archive, on every page load and every keystroke in
    # the search box (see frontend/src/pages/DocumentsPage.tsx's queryKey).
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    stmt = stmt.order_by(Document.f_public.desc().nulls_last(), Document.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all()), total


def get_source_family_keys(db: Session, source_ids: list[int]) -> dict[int, str]:
    if not source_ids:
        return {}
    stmt = select(Source.id, Source.family_key).where(Source.id.in_(source_ids))
    return dict(db.execute(stmt).all())


def count_documents_by_title_within_family(db: Session, titles: list[str], family_key: str) -> dict[str, int]:
    if not titles:
        return {}
    stmt = (
        select(Document.title, func.count(Document.id))
        .join(Source, Source.id == Document.source_id)
        .where(Source.family_key == family_key, Document.title.in_(titles))
        .group_by(Document.title)
    )
    return dict(db.execute(stmt).all())


def count_documents_by_family(db: Session) -> list[tuple[str, int]]:
    stmt = (
        select(Source.family_key, func.count(Document.id))
        .select_from(Document)
        .join(Source, Source.id == Document.source_id)
        .group_by(Source.family_key)
        .order_by(func.count(Document.id).desc())
    )
    return list(db.execute(stmt).all())


def count_documents_by_source(db: Session, limit: int = 8) -> list[tuple[int, str, int]]:
    stmt = (
        select(Source.id, Source.name, func.count(Document.id))
        .select_from(Document)
        .join(Source, Source.id == Document.source_id)
        .group_by(Source.id, Source.name)
        .order_by(func.count(Document.id).desc())
        .limit(limit)
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
    if session is None:
        return
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


def delete_sessions_for_user(db: Session, user_id: int, except_token_hash: Optional[str] = None) -> int:
    """Revokes every session for a user — used when changing password, so someone
    who stole a session gets kicked out right when the legitimate owner reacts to
    it. `except_token_hash` keeps the caller's own current session alive, so
    changing your own password doesn't also log you out of it."""
    stmt = delete(UserSession).where(UserSession.user_id == user_id)
    if except_token_hash is not None:
        stmt = stmt.where(UserSession.token_hash != except_token_hash)
    result = db.execute(stmt)
    db.commit()
    return result.rowcount


def update_user_password(db: Session, user_id: int, password_hash: str) -> None:
    user = db.get(User, user_id)
    if user is None:
        return
    user.password_hash = password_hash
    db.commit()


def touch_user_last_login(db: Session, user_id: int) -> None:
    user = db.get(User, user_id)
    if user is None:
        return
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
