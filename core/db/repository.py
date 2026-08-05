from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import Date as SqlDate
from sqlalchemy import and_, cast, delete, exists, func, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, aliased

from core.db.models import BulkDownload, CaseLink, CaseLinkSeparation, CaseLinkStage, CaseLinkSuggestion, Document, DocumentVersion, Run, RunError, RunSource, Source, SourceFamily, User, UserSession
from core.utils import MIN_MATCH_DIGITS, RADICADO_TITLE_PATTERN, SAMAI_CASE_TITLE_PATTERN, SAMAI_CASE_TITLE_RAW_PATTERN, matching_prefix_length

_LIKE_ESCAPE_CHAR = "\\"

# Familias cuyo título identifica el CASO (no una actuación puntual), así que varias
# filas distintas pueden compartir el mismo título legítimamente — cada una de estas
# entradas es "family_key -> patrones que confirman que el título sí tiene esa forma"
# (nunca un título de respaldo, como el nombre de un magistrado, que puede repetirse
# sin ser el mismo caso). "samai" tiene tres patrones: Consejo de Estado (dashes),
# Tribunales Administrativos (T_CODE_ format), y documentos antiguos sin normalizar
# (raw 23-digit radicado) capturados antes de que el scraper empezara a guardar
# el campo radicado (ver core/scrapers/families/samai.py::_normalizar_titulo y
# core/backfill_samai_radicado.py).
_CASE_GROUPING_FAMILY_PATTERNS = {
    "rama_judicial": [RADICADO_TITLE_PATTERN],
    "samai": [SAMAI_CASE_TITLE_PATTERN, RADICADO_TITLE_PATTERN, SAMAI_CASE_TITLE_RAW_PATTERN],
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


def list_run_sources_with_source_names(db: Session, run_id: int) -> list[RunSource]:
    stmt = (
        select(RunSource, Source.name)
        .join(Source, RunSource.source_id == Source.id)
        .where(RunSource.run_id == run_id)
    )
    run_sources = []
    for run_source, source_name in db.execute(stmt).all():
        run_source.source_name = source_name
        run_sources.append(run_source)
    return run_sources


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


def list_distinct_document_secciones(
    db: Session, source_id: Optional[int] = None, tipo: Optional[str] = None
) -> list[str]:
    stmt = select(Document.seccion).distinct().where(Document.seccion.is_not(None))
    if source_id is not None:
        stmt = stmt.where(Document.source_id == source_id)
    if tipo is not None:
        stmt = stmt.where(Document.tipo == tipo)
    stmt = stmt.order_by(Document.seccion)
    return list(db.scalars(stmt).all())


def list_distinct_document_especialidades(
    db: Session,
    source_id: Optional[int] = None,
    tipo: Optional[str] = None,
    seccion: Optional[str] = None,
) -> list[str]:
    stmt = select(Document.especialidad).distinct().where(Document.especialidad.is_not(None))
    if source_id is not None:
        stmt = stmt.where(Document.source_id == source_id)
    if tipo is not None:
        stmt = stmt.where(Document.tipo == tipo)
    if seccion is not None:
        stmt = stmt.where(Document.seccion == seccion)
    stmt = stmt.order_by(Document.especialidad)
    return list(db.scalars(stmt).all())


def list_distinct_document_magistrados(
    db: Session,
    source_id: Optional[int] = None,
    tipo: Optional[str] = None,
    seccion: Optional[str] = None,
    especialidad: Optional[str] = None,
) -> list[str]:
    stmt = select(Document.magistrado).distinct().where(Document.magistrado.is_not(None))
    if source_id is not None:
        stmt = stmt.where(Document.source_id == source_id)
    if tipo is not None:
        stmt = stmt.where(Document.tipo == tipo)
    if seccion is not None:
        stmt = stmt.where(Document.seccion == seccion)
    if especialidad is not None:
        stmt = stmt.where(Document.especialidad == especialidad)
    stmt = stmt.order_by(Document.magistrado)
    return list(db.scalars(stmt).all())


def list_documents(
    db: Session,
    source_id: Optional[int] = None,
    family_key: Optional[str] = None,
    tipo: Optional[str] = None,
    seccion: Optional[str] = None,
    especialidad: Optional[str] = None,
    magistrado: Optional[str] = None,
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
    if seccion is not None:
        stmt = stmt.where(Document.seccion == seccion)
    if especialidad is not None:
        stmt = stmt.where(Document.especialidad == especialidad)
    if magistrado is not None:
        stmt = stmt.where(Document.magistrado == magistrado)
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
                and_(
                    OuterSource.family_key == family_key,
                    or_(*[Document.title.op("~")(pattern.pattern) for pattern in patterns]),
                )
                for family_key, patterns in _CASE_GROUPING_FAMILY_PATTERNS.items()
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
    worker/tasks.py::_finalize_run). Solo mira los documentos que este run
    concreto insertó/tocó (vía Document.run_source_id -> RunSource.run_id),
    para las fuentes samai que participaron en él — el resto del archivo ya
    fue comparado en runs anteriores o en el backfill
    (core/backfill_samai_radicado.py) y no hace falta volver a escanearlo."""
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
    return generate_case_link_suggestions(db, new_groups)


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


def list_pending_case_link_suggestions(db: Session) -> list[CaseLinkSuggestion]:
    stmt = (
        select(CaseLinkSuggestion)
        .where(CaseLinkSuggestion.status == "pending")
        .order_by(CaseLinkSuggestion.created_at.desc())
    )
    return list(db.scalars(stmt).all())


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


def count_documents_by_family(db: Session) -> list[tuple[str, int]]:
    stmt = (
        select(Source.family_key, func.count(Document.id))
        .select_from(Document)
        .join(Source, Source.id == Document.source_id)
        .group_by(Source.family_key)
        .order_by(func.count(Document.id).desc())
    )
    return list(db.execute(stmt).all())


def count_documents_by_source(
    db: Session, year: Optional[int] = None, month: Optional[int] = None
) -> list[tuple[int, str, int]]:
    stmt = (
        select(Source.id, Source.name, func.count(Document.id))
        .select_from(Document)
        .join(Source, Source.id == Document.source_id)
    )
    if year is not None:
        date_expr = _effective_date_expr()
        stmt = stmt.where(func.extract("year", date_expr) == year)
        if month is not None:
            stmt = stmt.where(func.extract("month", date_expr) == month)
    stmt = stmt.group_by(Source.id, Source.name).order_by(func.count(Document.id).desc())
    return list(db.execute(stmt).all())


def count_documents_by_tipo(db: Session) -> list[tuple[str, int]]:
    tipo_expr = func.coalesce(Document.tipo, "Sin tipo")
    stmt = (
        select(tipo_expr, func.count(Document.id))
        .group_by(tipo_expr)
        .order_by(func.count(Document.id).desc())
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


def update_document_tipo(db: Session, document_id: int, tipo: str) -> Optional[Document]:
    document = db.get(Document, document_id)
    if document is None:
        return None
    document.tipo = tipo
    db.commit()
    db.refresh(document)
    return document


def update_document_especialidad(db: Session, document_id: int, especialidad: str) -> Optional[Document]:
    document = db.get(Document, document_id)
    if document is None:
        return None
    document.especialidad = especialidad
    db.commit()
    db.refresh(document)
    return document


def update_document_storage_key(db: Session, document_id: int, storage_key: str) -> Optional[Document]:
    document = db.get(Document, document_id)
    if document is None:
        return None
    document.storage_key = storage_key
    db.commit()
    db.refresh(document)
    return document


def purge_documents_for_source(db: Session, source_id: int) -> dict:
    """Deletes every Document (and its DocumentVersion / RunSource / RunError
    rows) belonging to source_id — none of the FKs involved have ON DELETE
    CASCADE, so children are deleted before parents. The Source row itself
    and every other source's data are left untouched. Object storage isn't
    touched here — this layer only owns the database; the caller (see
    core/purge_inactive_source_documents.py) is responsible for deleting the
    (bucket, key) pairs this returns from the actual storage backend."""
    document_rows = list(
        db.execute(
            select(Document.id, Document.storage_bucket, Document.storage_key, Document.preview_storage_key).where(
                Document.source_id == source_id
            )
        ).all()
    )
    document_ids = [row.id for row in document_rows]

    version_rows = (
        list(
            db.execute(
                select(DocumentVersion.storage_bucket, DocumentVersion.storage_key).where(
                    DocumentVersion.document_id.in_(document_ids)
                )
            ).all()
        )
        if document_ids
        else []
    )

    run_source_ids = list(db.scalars(select(RunSource.id).where(RunSource.source_id == source_id)).all())

    if document_ids:
        db.execute(delete(DocumentVersion).where(DocumentVersion.document_id.in_(document_ids)))
        db.execute(delete(Document).where(Document.id.in_(document_ids)))
    if run_source_ids:
        db.execute(delete(RunError).where(RunError.run_source_id.in_(run_source_ids)))
        db.execute(delete(RunSource).where(RunSource.id.in_(run_source_ids)))
    db.commit()

    storage_objects = [(row.storage_bucket, row.storage_key) for row in document_rows]
    storage_objects += [
        (row.storage_bucket, row.preview_storage_key) for row in document_rows if row.preview_storage_key
    ]
    storage_objects += [(row.storage_bucket, row.storage_key) for row in version_rows]

    return {
        "documents_deleted": len(document_ids),
        "run_sources_deleted": len(run_source_ids),
        "storage_objects": storage_objects,
    }


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


def create_user(db: Session, username: str, password_hash: str, is_admin: bool = False) -> User:
    user = User(username=username, password_hash=password_hash, active=True, is_admin=is_admin)
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
