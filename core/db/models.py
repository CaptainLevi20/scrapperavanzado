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
    UniqueConstraint,
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
    docs_updated = Column(Integer, nullable=False, default=0)
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


class BulkDownload(Base):
    __tablename__ = "bulk_downloads"

    id = Column(Integer, primary_key=True)
    status = Column(String, nullable=False, default="pending")  # pending | running | completed | failed
    document_count = Column(Integer, nullable=False, default=0)  # incluidos en el zip
    failed_count = Column(Integer, nullable=False, default=0)  # se omitieron por error de lectura
    zip_storage_key = Column(Text, nullable=True)  # solo si status == completed
    # Bucket the zip actually landed in, captured from upload_file()'s own return
    # value — not assumed to always match the CURRENT s3_bucket setting, which
    # could change after this row was written. Nullable because rows created
    # before this column existed have no way to know their own bucket in
    # hindsight; the API falls back to the current default for those.
    storage_bucket = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)  # solo si status == failed
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    doc_id = Column(String, nullable=False, unique=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    run_source_id = Column(Integer, ForeignKey("run_sources.id"), nullable=True)
    # Indexed: the general listing's "collapse case families" clause self-joins
    # documents on equal titles within a family (see repository.list_documents).
    # Without this index that correlated subquery seq-scans the whole table once
    # per row — an O(n²) blow-up that made the total-count for the unfiltered
    # /documents view take ~35s over ~10k rows.
    title = Column(String, nullable=False, index=True)
    tipo = Column(String, nullable=True)
    seccion = Column(String, nullable=True)
    especialidad = Column(String, nullable=True)
    magistrado = Column(String, nullable=True)
    # Radicado normalizado (solo dígitos) — solo poblado por familias que lo
    # capturan en crudo (hoy: samai). Nunca se muestra en la interfaz; existe
    # para detectar el mismo proceso en otra fuente (ver CaseLink más abajo).
    radicado = Column(String, nullable=True)
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
    preview_storage_key = Column(Text, nullable=True)
    downloaded_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    review_status = Column(String, nullable=False, default="pending", server_default="pending")
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    # Número de versión de esta actuación. 1 al crearse; se incrementa en cada
    # republicación (ver archive_and_replace_document). El nombre canónico
    # muestra "-v{n}" solo cuando hay más de una versión (version_no > 1).
    version_no = Column(Integer, nullable=False, default=1, server_default="1")
    # Set once this document has been successfully delivered inside a completed
    # bulk download's zip, so list_useful_documents() can exclude it from the
    # next one. Cleared whenever the document's review status changes, so a
    # fresh "useful" decision makes it eligible again.
    bulk_download_id = Column(Integer, ForeignKey("bulk_downloads.id"), nullable=True)


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    storage_bucket = Column(String, nullable=False)
    storage_key = Column(Text, nullable=False)
    content_type = Column(String, nullable=True)
    file_extension = Column(String, nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    converted_format = Column(String, nullable=True)
    source_url = Column(Text, nullable=True)
    downloaded_at = Column(DateTime(timezone=True), nullable=False)
    superseded_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    # Número de versión que tenía el documento cuando ESTA versión era la
    # vigente (la más antigua = 1). Fijado al archivar en
    # archive_and_replace_document.
    version_no = Column(Integer, nullable=False, default=1, server_default="1")
    # run_source que disparó esta republicación (la actualización que dejó
    # esta versión archivada). Nullable porque archive_and_replace_document
    # también se usa fuera del flujo de scraping normal; sin esto no hay
    # forma de saber qué run actualizó un documento dado (ver informe de run).
    updated_by_run_source_id = Column(Integer, ForeignKey("run_sources.id"), nullable=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    is_admin = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    last_login_at = Column(DateTime(timezone=True), nullable=True)


class UserSession(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)


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


class CaseLinkSeparation(Base):
    __tablename__ = "case_link_separations"

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    radicado = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (UniqueConstraint("source_id", "radicado", name="uq_case_link_separations_source_radicado"),)
