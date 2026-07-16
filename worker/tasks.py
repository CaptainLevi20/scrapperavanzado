import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath

from core.db import repository
from core.db.session import SessionLocal
from core.downloader import Downloader, convert_to_pdf_via_libreoffice
from core.scrapers import families  # noqa: F401 — ensures registry is populated
from core.scrapers.registry import resolve_scraper
from core.storage import download_file, upload_file
from core.utils import compute_doc_id
from worker.celery_app import celery_app

logger = logging.getLogger(__name__)

# Downloading + converting (LibreOffice) + uploading a single document is
# dominated by I/O wait and by an external subprocess, so worker threads (not
# processes) already parallelize it well — each soffice invocation gets its own
# disposable profile (see core/downloader.py), so concurrent conversions no
# longer collide on LibreOffice's shared-profile lock. 6 was chosen to leave
# headroom on a 16-core box rather than saturate it entirely.
MAX_CONCURRENT_DOCUMENT_DOWNLOADS = 6


def _parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _default_date_str(value: date | None) -> str:
    if value:
        return value.strftime("%Y-%m-%d")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _download_and_upload_one(doc, tmp_path: Path):
    """Runs in a worker thread: download, convert, and upload a single document.
    Returns (payload, error) — payload is the dict of fields insert_document needs
    beyond doc_id/source_id/run_source_id, or None if an error occurred. Owns its
    own Downloader (and therefore its own WordConverter/Word COM instance) so
    concurrent threads never share Word state."""
    downloader = Downloader()
    try:
        result = downloader.download(doc, tmp_path)
        bucket, storage_key = upload_file(result.local_path, result.storage_key, content_type=result.content_type)

        return {
            "storage_bucket": bucket,
            "storage_key": storage_key,
            "content_type": result.content_type,
            "file_extension": Path(result.storage_key).suffix,
            "file_size_bytes": result.file_size_bytes,
            "converted_format": result.converted_format,
        }, None
    except Exception as exc:
        return None, exc
    finally:
        downloader.close()


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
        with tempfile.TemporaryDirectory(prefix=f"run_source_{run_source_id}_") as tmp_dir:
            tmp_path = Path(tmp_dir)

            pending = []
            for doc in docs:
                if repository.is_cancel_requested(db, run.id):
                    break
                doc_id = compute_doc_id(doc)
                if repository.document_exists(db, doc_id):
                    continue
                pending.append((doc_id, doc))

            with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOCUMENT_DOWNLOADS) as executor:
                futures = {
                    executor.submit(_download_and_upload_one, doc, tmp_path): (doc_id, doc)
                    for doc_id, doc in pending
                }
                for future in as_completed(futures):
                    doc_id, doc = futures[future]
                    payload, exc = future.result()

                    if exc is not None:
                        if isinstance(exc, FileNotFoundError):
                            logger.info("Documento no disponible aún: %s", exc)
                            continue
                        docs_errors += 1
                        repository.add_run_error(
                            db, run_source_id, str(exc), context={"title": doc.title, "url": doc.link.get("url")}
                        )
                        continue

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
                        **payload,
                    )
                    docs_new += 1

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


@celery_app.task(name="worker.generate_document_preview_pdf")
def generate_document_preview_pdf(document_id: int) -> str:
    db = SessionLocal()
    try:
        document = repository.get_document(db, document_id)
        if document is None:
            raise ValueError(f"Documento {document_id} no encontrado")
        if document.preview_storage_key:
            return document.preview_storage_key

        with tempfile.TemporaryDirectory(prefix=f"preview_{document_id}_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            extension = Path(document.storage_key).suffix
            local_path = tmp_path / f"original{extension}"
            download_file(document.storage_bucket, document.storage_key, local_path)

            pdf_path = convert_to_pdf_via_libreoffice(local_path)

            # storage_key is an S3-style key (always "/"-delimited), not an OS filesystem path,
            # so PurePosixPath is used here (rather than Path) to strip only the filename
            # component's own extension without the host OS's native separator leaking into
            # the reconstructed key on Windows.
            base_key = str(PurePosixPath(document.storage_key).with_suffix(""))
            preview_key = f"{base_key}.preview.pdf"
            upload_file(pdf_path, preview_key, bucket=document.storage_bucket, content_type="application/pdf")

        repository.set_document_preview_key(db, document_id, preview_key)
        return preview_key
    finally:
        db.close()
