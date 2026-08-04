from core.backfill_samai_especialidad import backfill
from core.db import repository


def _samai_source(db_session, name="Tribunal Administrativo de Cundinamarca"):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    return repository.create_source(db_session, family_key="samai", name=name, family_params={})


def test_backfill_resolves_clase_now_covered_by_expanded_catalog(db_session):
    source = _samai_source(db_session)
    doc = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T_CUND_25001233300020260001200",
        especialidad="PROCESO EJECUTIVO",
        storage_bucket="iurisync-test",
        storage_key="Tribunal Administrativo de Cundinamarca/seccion/2026-08-03/Auto/doc.pdf",
    )

    result = backfill(db_session)

    db_session.refresh(doc)
    assert doc.especialidad == "Ejecutivo"
    assert result["documents_updated"] == 1


def test_backfill_leaves_untouched_when_already_resolved(db_session):
    source = _samai_source(db_session)
    doc = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T_CUND_25001233300020260001200",
        especialidad="Ejecutivo",
        storage_bucket="iurisync-test",
        storage_key="Tribunal Administrativo de Cundinamarca/seccion/2026-08-03/Auto/doc.pdf",
    )

    result = backfill(db_session)

    db_session.refresh(doc)
    assert doc.especialidad == "Ejecutivo"
    assert result["documents_updated"] == 0


def test_backfill_leaves_untouched_when_clase_still_unknown(db_session):
    source = _samai_source(db_session)
    doc = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T_CUND_25001233300020260001200",
        especialidad="Una clase nunca vista",
        storage_bucket="iurisync-test",
        storage_key="Tribunal Administrativo de Cundinamarca/seccion/2026-08-03/Auto/doc.pdf",
    )

    result = backfill(db_session)

    db_session.refresh(doc)
    assert doc.especialidad == "Una clase nunca vista"
    assert result["documents_updated"] == 0


def test_backfill_is_idempotent_across_two_runs(db_session):
    source = _samai_source(db_session)
    doc = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T_CUND_25001233300020260001200",
        especialidad="ACCIONES POPULARES (R)",
        storage_bucket="iurisync-test",
        storage_key="Tribunal Administrativo de Cundinamarca/seccion/2026-08-03/Auto/doc.pdf",
    )

    backfill(db_session)
    second_result = backfill(db_session)

    db_session.refresh(doc)
    assert doc.especialidad == "Acciones populares"
    assert second_result["documents_updated"] == 0


def test_backfill_ignores_documents_from_other_families(db_session):
    repository.create_source_family(db_session, key="corte_suprema", display_name="CSJ")
    source = repository.create_source(db_session, family_key="corte_suprema", name="CSJ", family_params={})
    doc = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="CSJ_SCT_ABC1234_2026",
        especialidad="PROCESO EJECUTIVO",
        storage_bucket="iurisync-test",
        storage_key="CSJ/SCT/doc.pdf",
    )

    result = backfill(db_session)

    db_session.refresh(doc)
    assert doc.especialidad == "PROCESO EJECUTIVO"  # sin tocar — no es de la familia samai
    assert result["documents_updated"] == 0


def test_backfill_continues_after_update_failure(db_session, monkeypatch):
    source = _samai_source(db_session)
    doc1 = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T_CUND_25001233300020260001200",
        especialidad="PROCESO EJECUTIVO",
        storage_bucket="iurisync-test",
        storage_key="Tribunal Administrativo de Cundinamarca/seccion/2026-08-03/Auto/doc.pdf",
    )
    doc2 = repository.insert_document(
        db_session,
        doc_id="doc-2",
        source_id=source.id,
        title="T_CUND_25001233300020260001201",
        especialidad="OBJECIONES",
        storage_bucket="iurisync-test",
        storage_key="Tribunal Administrativo de Cundinamarca/seccion/2026-08-03/Auto/doc2.pdf",
    )

    import core.backfill_samai_especialidad as backfill_module

    real_update = repository.update_document_especialidad

    def update_with_failure(db, document_id, especialidad):
        if document_id == doc1.id:
            raise RuntimeError("DB no disponible")
        return real_update(db, document_id, especialidad)

    monkeypatch.setattr(backfill_module.repository, "update_document_especialidad", update_with_failure)

    result = backfill(db_session)

    db_session.refresh(doc1)
    db_session.refresh(doc2)
    assert doc1.especialidad == "PROCESO EJECUTIVO"  # sin cambios, la actualización falló
    assert doc2.especialidad == "Objeciones"  # esta sí se procesó
    assert result["documents_updated"] == 1
