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
