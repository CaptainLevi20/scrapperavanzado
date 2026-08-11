import logging
import shutil
import tempfile
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath

from core.db import repository
from core.db.session import SessionLocal
from core.downloader import Downloader, check_remote_content_length, convert_to_pdf_via_libreoffice
from core.scrapers import families  # noqa: F401 — ensures registry is populated
from core.scrapers.registry import resolve_scraper
from core.storage import download_file, upload_file
from core.utils import compute_doc_id, is_safe_storage_key, rekey_filename
from worker.celery_app import celery_app

logger = logging.getLogger(__name__)


class _ScrapProgressCollector:
    """Every family scraper accepts an on_progress(message) callback and already
    tags its own recovered-from failures with 'Error ...' (a section, a page,
    a date range that failed but didn't abort the whole scrap) — but nothing in
    production ever passed on_progress in, so those messages were generated and
    immediately discarded. This collects them so the caller can turn the
    'Error'-tagged ones into visible RunErrors once scrap() returns. A lock
    guards it because some families (e.g. SAMAI) call on_progress from their own
    background thread pool, not just the main thread."""

    def __init__(self):
        self._lock = threading.Lock()
        self.error_messages: list[str] = []

    def __call__(self, message: str) -> None:
        logger.info(message)
        if "Error" in message:
            with self._lock:
                self.error_messages.append(message)

# Downloading + converting (LibreOffice) + uploading a single document is
# dominated by I/O wait and by an external subprocess, so worker threads (not
# processes) already parallelize it well — each soffice invocation gets its own
# disposable profile (see core/downloader.py), so concurrent conversions no
# longer collide on LibreOffice's shared-profile lock. 6 was chosen to leave
# headroom on a 16-core box rather than saturate it entirely.
MAX_CONCURRENT_DOCUMENT_DOWNLOADS = 6

# How often the cancellation poller (see scrape_source_task) re-checks
# is_cancel_requested while downloads are in flight. A module-level constant so
# tests can monkeypatch it down instead of waiting on the real interval.
CANCEL_POLL_INTERVAL_SECONDS = 2


def _parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _default_date_str(value: date | None) -> str:
    if value:
        return value.strftime("%Y-%m-%d")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _download_and_upload_one(
    doc,
    tmp_path: Path,
    scraper=None,
    override_storage_key: str | None = None,
    skip_upload_if_size_matches: int | None = None,
    stop_event: threading.Event | None = None,
):
    """Runs in a worker thread: download and upload a single document (in its
    original source format — no conversion happens at storage time, only for
    on-demand previews via convert_to_pdf_via_libreoffice). Returns (payload,
    error) — payload is the dict of fields insert_document/
    archive_and_replace_document needs beyond doc_id/source_id/run_source_id, or
    None if an error occurred (error not None) or nothing changed (error is None too —
    this is how a republication candidate whose real downloaded size matches the
    stored one is discarded WITHOUT ever uploading, avoiding an orphaned object in
    storage). `override_storage_key`, when given, is used instead of the
    freshly-computed key — this is how a republication replacement lands under a
    distinct key instead of the original document's. `stop_event`, when given and
    set, makes an in-flight download abort with InterruptedError (Downloader
    already checks it between chunks) — how a cancelled run stops downloads that
    were already underway, not just ones that hadn't started yet."""
    downloader = Downloader()
    try:
        result = downloader.download(doc, tmp_path, stop_event=stop_event)
        if doc.title_unverified and scraper is not None:
            # doc.title (and possibly doc.tipo) get corrected in place from the
            # file's own content — see e.g. ScrapCorteSuprema for the "doc"/"(3)"
            # placeholder-title case this exists for. result.storage_key was
            # already resolved from the pre-correction title, so it must be
            # rebuilt from the corrected one now (see rekey_filename) — otherwise
            # the fix only lands in the database and the actual stored file (and
            # any bulk-download ZIP built from storage_key) keeps the old name.
            titulo_antes = doc.title
            scraper.resolve_unverified_document(doc, result.local_path, result.content_type)
            # Solo se reconstruye la clave de almacenamiento si el enganche realmente
            # corrigió el título (SAMAI/CSJ). Rama Judicial usa el enganche solo para
            # extraer f_providencia y NO cambia el título; reejecutar rekey en ese caso
            # reescribiría la clave descriptiva al radicado canónico —perdería el
            # detalle del nombre y podría colisionar dos actuaciones del mismo radicado
            # en una misma clave, sobrescribiendo el archivo.
            if doc.title != titulo_antes:
                result.storage_key = rekey_filename(result.storage_key, doc.title)
        if skip_upload_if_size_matches is not None and result.file_size_bytes == skip_upload_if_size_matches:
            return None, None
        upload_key = override_storage_key or result.storage_key
        bucket, storage_key = upload_file(result.local_path, upload_key, content_type=result.content_type)

        return {
            "storage_bucket": bucket,
            "storage_key": storage_key,
            "content_type": result.content_type,
            "file_extension": Path(storage_key).suffix,
            "file_size_bytes": result.file_size_bytes,
            "converted_format": result.converted_format,
        }, None
    except Exception as exc:
        return None, exc


def _versioned_replacement_key(original_key: str) -> str:
    """Builds a distinct storage key for a re-downloaded (republished) document, so
    the new upload never overwrites the original object — a DocumentVersion row
    keeps pointing at that original key as the archived version's location."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    posix_key = PurePosixPath(original_key)
    if posix_key.suffix:
        return str(posix_key.with_name(f"{posix_key.stem}-republicado-{timestamp}{posix_key.suffix}"))
    return f"{original_key}-republicado-{timestamp}"


@celery_app.task(name="worker.scrape_source_task")
def scrape_source_task(run_source_id: int):
    db = SessionLocal()
    try:
        run_source = repository.get_run_source(db, run_source_id)
        if run_source is None:
            return

        source = repository.get_source(db, run_source.source_id)
        run = repository.get_run(db, run_source.run_id)

        # A run cancelled before this particular source's task even got a chance
        # to run (e.g. it was still queued behind others in the chord) must not
        # do any real work at all — no network call, no "running" status.
        if repository.is_cancel_requested(db, run.id):
            repository.set_run_source_status(db, run_source_id, "cancelled", finished_at=datetime.now(timezone.utc))
            return

        # A source can declare in family_params that every document it produces
        # should land already reviewed (e.g. the sources team confirming
        # everything from Corte Constitucional is useful) instead of "pending".
        family_params = source.family_params or {}
        auto_review_status = family_params.get("auto_review_status")
        # auto_review_status is orchestration-only metadata consumed above, not a
        # scraper constructor argument - resolve_scraper forwards it to cls(**params),
        # and real family scrapers (unlike this dict) take no **kwargs catch-all.
        scraper_params = {k: v for k, v in family_params.items() if k != "auto_review_status"}

        repository.set_run_source_status(db, run_source_id, "running", started_at=datetime.now(timezone.utc))

        progress = _ScrapProgressCollector()
        try:
            scraper = resolve_scraper(source.family_key, scraper_params)
            fini = _default_date_str(run.fini)
            ffin = _default_date_str(run.ffin)
            docs = scraper.scrap(fini=fini, ffin=ffin, on_progress=progress)
        except Exception as exc:
            repository.set_run_source_status(
                db, run_source_id, "failed", error_message=str(exc), finished_at=datetime.now(timezone.utc)
            )
            return

        docs_new = 0
        docs_updated = 0
        docs_errors = 0
        # Errors the scraper recovered from mid-scrap (a section, page, or date
        # range that failed but didn't abort the whole thing — see
        # _ScrapProgressCollector) must not be silently invisible just because
        # scrap() itself returned normally with a partial result.
        for message in progress.error_messages:
            docs_errors += 1
            repository.add_run_error(db, run_source_id, message)
        was_cancelled = False
        # Set by the poller below the moment a cancellation is noticed, so any
        # download already in flight aborts (Downloader checks it between
        # chunks) instead of only stopping NEW downloads from starting.
        stop_event = threading.Event()
        try:
            with tempfile.TemporaryDirectory(prefix=f"run_source_{run_source_id}_") as tmp_dir:
                tmp_path = Path(tmp_dir)

                pending = []  # (doc_id, doc) -> brand new documents
                replace_candidates = []  # (existing_document, doc_id, doc) -> possible republication
                # A source can legitimately list the same document twice in one
                # scrap() pass (pagination overlap, a listing bug on the remote
                # site, etc.) — without deduping here, both occurrences get
                # downloaded and uploaded to storage, and only the DB write is
                # protected (on_conflict_do_nothing), leaving the second upload
                # as a permanently orphaned object nobody ever references.
                seen_doc_ids: set[str] = set()
                for doc in docs:
                    if repository.is_cancel_requested(db, run.id):
                        was_cancelled = True
                        break
                    doc_id = compute_doc_id(doc, include_publication_date=scraper.doc_id_uses_publication_date)
                    if doc_id in seen_doc_ids:
                        continue
                    seen_doc_ids.add(doc_id)
                    existing = repository.get_document_by_doc_id(db, doc_id)
                    if existing is None:
                        pending.append((doc_id, doc))
                        continue
                    if not scraper.checks_for_republication:
                        continue
                    remote_size = check_remote_content_length(doc.link.get("url"))
                    if remote_size is not None and remote_size == existing.file_size_bytes:
                        continue
                    replace_candidates.append((existing, doc_id, doc))

                if not was_cancelled and (pending or replace_candidates):
                    # Enumerating metadata is typically fast, but the downloads
                    # themselves (the slow part, per the bug this fixes) can run
                    # for a while — nothing above re-checks cancellation once
                    # they start. This background poller does, on its own DB
                    # session (sessions aren't thread-safe), and flips
                    # stop_event the moment someone cancels the run.
                    cancel_poll_stop = threading.Event()
                    # Captured as a plain int, not read as run.id from inside the
                    # thread below: `run` is an ORM object bound to the OUTER
                    # `db` session, and SQLAlchemy expires all of a session's
                    # objects on every commit — the *next* attribute access
                    # (even just .id) then lazily re-queries via whichever
                    # session the object is bound to, regardless of which
                    # thread does the accessing. With many documents committing
                    # on `db` throughout this run, that turned "poll_db is a
                    # separate session" into a false sense of isolation: the
                    # poller thread ended up touching `db` from a second thread
                    # concurrently with the main thread, corrupting its
                    # transaction state ("session is in 'prepared' state").
                    # Capturing the id once, up front, removes any cross-thread
                    # access to `run` itself.
                    run_id = run.id

                    def _poll_cancellation():
                        poll_db = SessionLocal()
                        try:
                            while not cancel_poll_stop.wait(timeout=CANCEL_POLL_INTERVAL_SECONDS):
                                if repository.is_cancel_requested(poll_db, run_id):
                                    stop_event.set()
                                    return
                        finally:
                            poll_db.close()

                    poller = threading.Thread(target=_poll_cancellation, daemon=True)
                    poller.start()
                    try:
                        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOCUMENT_DOWNLOADS) as executor:
                            work_items = [("new", doc_id, doc) for doc_id, doc in pending] + [
                                ("replace", existing, doc_id, doc) for existing, doc_id, doc in replace_candidates
                            ]
                            all_futures = {}
                            for entry in work_items:
                                if stop_event.is_set():
                                    was_cancelled = True
                                    break
                                if entry[0] == "new":
                                    _, doc_id, doc = entry
                                    future = executor.submit(
                                        _download_and_upload_one, doc, tmp_path, scraper, stop_event=stop_event
                                    )
                                else:
                                    _, existing, doc_id, doc = entry
                                    future = executor.submit(
                                        _download_and_upload_one,
                                        doc,
                                        tmp_path,
                                        scraper,
                                        _versioned_replacement_key(existing.storage_key),
                                        existing.file_size_bytes,
                                        stop_event,
                                    )
                                all_futures[future] = entry

                            for future in as_completed(all_futures):
                                entry = all_futures[future]
                                kind = entry[0]
                                doc = entry[-1]
                                payload, exc = future.result()

                                if exc is not None:
                                    if isinstance(exc, InterruptedError):
                                        was_cancelled = True
                                        continue
                                    if isinstance(exc, FileNotFoundError):
                                        logger.info("Documento no disponible aún: %s", exc)
                                        continue
                                    docs_errors += 1
                                    repository.add_run_error(
                                        db, run_source_id, str(exc), context={"title": doc.title, "url": doc.link.get("url")}
                                    )
                                    continue

                                if payload is None:
                                    continue  # candidato a reemplazo confirmado sin cambios; no se subió nada

                                # A DB write failing here (IntegrityError, OperationalError, a dropped
                                # connection) must not kill the whole task — the document was already
                                # downloaded and uploaded, so the failure is recorded like any other
                                # per-document error and the loop moves on to the rest. Without this,
                                # a single bad write used to propagate all the way out of the task,
                                # skipping the final set_run_source_status below and leaving the source
                                # (and, since the chord callback never ran either, the whole Run) stuck
                                # in "running" forever.
                                try:
                                    if kind == "new":
                                        _, doc_id, doc = entry
                                        # reporting_whether_created: even after the in-batch
                                        # dedup above, a different run_source (a concurrent
                                        # or overlapping run touching the same source) could
                                        # race this exact doc_id — on_conflict_do_nothing
                                        # would silently skip the insert, and counting it as
                                        # "new" anyway would inflate the dashboard's count for
                                        # a document this run_source didn't actually add.
                                        _, created = repository.insert_document_reporting_whether_created(
                                            db,
                                            doc_id=doc_id,
                                            source_id=source.id,
                                            run_source_id=run_source_id,
                                            title=doc.title,
                                            tipo=doc.tipo,
                                            seccion=doc.seccion,
                                            especialidad=doc.especialidad,
                                            magistrado=doc.magistrado,
                                            radicado=doc.radicado,
                                            detalle=doc.detalle,
                                            f_public=_parse_date(doc.f_public),
                                            f_providencia=_parse_date(doc.f_providencia),
                                            source_url=doc.link.get("url"),
                                            **({"review_status": auto_review_status} if auto_review_status else {}),
                                            **payload,
                                        )
                                        if created:
                                            docs_new += 1
                                    else:
                                        _, existing, doc_id, doc = entry
                                        repository.archive_and_replace_document(
                                            db, existing.id, review_status=auto_review_status or "pending", **payload
                                        )
                                        docs_updated += 1
                                except Exception as db_exc:
                                    db.rollback()
                                    docs_errors += 1
                                    repository.add_run_error(
                                        db,
                                        run_source_id,
                                        str(db_exc),
                                        context={"title": doc.title, "url": doc.link.get("url")},
                                    )
                    finally:
                        cancel_poll_stop.set()
                        poller.join(timeout=5)
        except Exception as exc:
            # Belt-and-suspenders: anything unexpected in the block above that
            # isn't already one of the per-document errors handled inline must
            # still leave the source in a terminal state rather than stuck
            # "running" — same reasoning as the per-document try/except above.
            db.rollback()
            repository.set_run_source_status(
                db, run_source_id, "failed", error_message=str(exc), finished_at=datetime.now(timezone.utc)
            )
            return

        repository.set_run_source_status(
            db,
            run_source_id,
            "cancelled" if was_cancelled else "completed",
            docs_new=docs_new,
            docs_updated=docs_updated,
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
        run = repository.get_run(db, run_id)
        run_sources = repository.list_run_sources(db, run_id)
        # A run the user explicitly cancelled reports "cancelled" regardless of how
        # individual sources landed — that's the deliberate final word, not
        # something a source finishing "completed"/"failed" out of sheer timing
        # should override.
        if run is not None and run.cancel_requested:
            status = "cancelled"
        elif any(rs.status == "failed" for rs in run_sources):
            status = "failed"
        else:
            status = "completed"

        # Corre después de que los documentos del run ya están guardados —
        # un fallo aquí (ej. un problema de datos inesperado) no debe
        # impedir que el run se marque como terminado; solo se pierde esta
        # ronda de armado de expedientes, que el próximo run o el backfill
        # manual puede volver a ejecutar sobre los mismos grupos (o grupos
        # que se solapen).
        try:
            repository.assemble_case_links_for_run(db, run_id)
        except Exception:
            logger.exception("Falló el armado de expedientes para el run %s", run_id)

        repository.set_run_status(db, run_id, status, finished_at=datetime.now(timezone.utc))
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


@celery_app.task(name="worker.build_bulk_download_zip")
def build_bulk_download_zip(bulk_download_id: int) -> None:
    db = SessionLocal()
    try:
        repository.set_bulk_download_status(
            db, bulk_download_id, "running", started_at=datetime.now(timezone.utc)
        )

        documents = repository.list_useful_documents(db)
        if not documents:
            repository.set_bulk_download_status(
                db,
                bulk_download_id,
                "failed",
                error_message="No hay documentos marcados como Útil para descargar",
                finished_at=datetime.now(timezone.utc),
            )
            return

        with tempfile.TemporaryDirectory(prefix=f"bulk_download_{bulk_download_id}_") as tmp_dir:
            tmp_path = Path(tmp_dir)

            # A rough but real safety check before touching the disk at all: the
            # zip's final size can't exceed the sum of the documents' own sizes,
            # and — since each raw copy is deleted right after being zipped, see
            # below — the only extra room ever needed beyond that is for whichever
            # single file happens to be downloading at the time. Documents saved
            # by an older version of the code may have no recorded size; the
            # check is skipped rather than guessed at in that case.
            known_sizes = [d.file_size_bytes for d in documents if d.file_size_bytes]
            if known_sizes and len(known_sizes) == len(documents):
                required_bytes = sum(known_sizes) + max(known_sizes)
                free_bytes = shutil.disk_usage(tmp_path).free
                if free_bytes < required_bytes:
                    repository.set_bulk_download_status(
                        db,
                        bulk_download_id,
                        "failed",
                        error_message=(
                            "No hay espacio suficiente en el servidor para generar esta descarga "
                            f"masiva (se necesitan aproximadamente {required_bytes / 1_000_000:.0f} MB, "
                            f"hay {free_bytes / 1_000_000:.0f} MB disponibles)."
                        ),
                        finished_at=datetime.now(timezone.utc),
                    )
                    return

            downloads_dir = tmp_path / "files"
            downloads_dir.mkdir()

            zip_path = tmp_path / "bulk_download.zip"
            downloaded_count = 0
            failed_count = 0
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for document in documents:
                    # Re-validated here even though the key was already checked when
                    # it was first written (see core/downloader.py): this document
                    # may have been saved by an older version of the code, or its
                    # row edited directly, and storage_key is about to be joined
                    # onto a real local directory and used as a ZIP arcname — both
                    # places a ".." would actually do damage.
                    if not is_safe_storage_key(document.storage_key):
                        logger.warning(
                            "Clave de almacenamiento no segura, se omite de la descarga masiva: %s", document.storage_key
                        )
                        failed_count += 1
                        continue
                    local_path = downloads_dir / document.storage_key
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        download_file(document.storage_bucket, document.storage_key, local_path)
                        zf.write(local_path, arcname=document.storage_key)
                        downloaded_count += 1
                    except Exception as exc:
                        logger.warning("No se pudo incluir %s en la descarga masiva: %s", document.storage_key, exc)
                        failed_count += 1
                    finally:
                        # Freed as soon as it's zipped instead of kept around until the
                        # whole batch finishes — otherwise disk usage peaks at roughly
                        # twice the total size (every raw copy plus the zip being built).
                        local_path.unlink(missing_ok=True)

            if downloaded_count == 0:
                repository.set_bulk_download_status(
                    db,
                    bulk_download_id,
                    "failed",
                    error_message=f"No se pudo leer ninguno de los {len(documents)} documentos útiles",
                    finished_at=datetime.now(timezone.utc),
                )
                return

            zip_key = f"bulk-downloads/{bulk_download_id}.zip"
            zip_bucket, zip_key = upload_file(zip_path, zip_key, content_type="application/zip")

        repository.set_bulk_download_status(
            db,
            bulk_download_id,
            "completed",
            document_count=downloaded_count,
            failed_count=failed_count,
            zip_storage_key=zip_key,
            storage_bucket=zip_bucket,
            finished_at=datetime.now(timezone.utc),
        )
    except Exception as exc:
        repository.set_bulk_download_status(
            db, bulk_download_id, "failed", error_message=str(exc), finished_at=datetime.now(timezone.utc)
        )
    finally:
        db.close()
