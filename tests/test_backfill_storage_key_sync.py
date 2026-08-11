from core.backfill_storage_key_sync import run_backfill
from core.db import repository
import core.storage_sync


def test_run_backfill_renames_a_mismatched_document(db_session, monkeypatch):
    repository.create_source_family(db_session, key="rama_judicial", display_name="Rama Judicial")
    source = repository.create_source(db_session, family_key="rama_judicial", name="Tribunal", family_params={})
    doc = repository.insert_document(
        db_session, doc_id="d1", source_id=source.id, title="T-123-24",
        storage_bucket="iurisync-test", storage_key="carpeta/placeholder.pdf",
    )

    monkeypatch.setattr(core.storage_sync, "rename_object", lambda *a: None)

    result = run_backfill(db_session)

    assert result == {"documentos_renombrados": 1, "versiones_renombradas": 0}
    db_session.refresh(doc)
    assert doc.storage_key == "carpeta/T-123-24.pdf"
