from datetime import datetime, timezone, timedelta

from core.db import repository
from core.db.models import DocumentVersion
from core.backfill_version_no import asignar_version_no


def test_backfill_numera_versiones_por_antiguedad(db_session):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
    doc = repository.insert_document(
        db_session, doc_id="bf-1", source_id=source.id, title="rad-1",
        storage_bucket="iurisync-test", storage_key="v3.pdf",
    )
    ahora = datetime.now(timezone.utc)
    # Dos versiones archivadas, la más antigua primero (superseded_at menor).
    db_session.add(DocumentVersion(document_id=doc.id, storage_bucket="b", storage_key="v1.pdf",
                                   downloaded_at=ahora, superseded_at=ahora - timedelta(days=2)))
    db_session.add(DocumentVersion(document_id=doc.id, storage_bucket="b", storage_key="v2.pdf",
                                   downloaded_at=ahora, superseded_at=ahora - timedelta(days=1)))
    db_session.commit()

    actualizados = asignar_version_no(db_session)

    versions = repository.list_document_versions(db_session, doc.id)
    por_key = {v.storage_key: v.version_no for v in versions}
    assert por_key == {"v1.pdf": 1, "v2.pdf": 2}
    assert repository.get_document(db_session, doc.id).version_no == 3
    assert actualizados == 1


def test_backfill_documento_sin_versiones_queda_en_1(db_session):
    repository.create_source_family(db_session, key="constitucional", display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key="constitucional", name="Corte Constitucional", family_params={})
    doc = repository.insert_document(
        db_session, doc_id="bf-2", source_id=source.id, title="T-1",
        storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    asignar_version_no(db_session)
    assert repository.get_document(db_session, doc.id).version_no == 1
