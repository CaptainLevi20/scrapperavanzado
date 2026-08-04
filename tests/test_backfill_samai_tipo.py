from core.backfill_samai_tipo import backfill
from core.db import repository


def _samai_source(db_session, name="Tribunal Administrativo de Cundinamarca"):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    return repository.create_source(db_session, family_key="samai", name=name, family_params={})


def test_backfill_normalizes_all_caps_tipo(db_session):
    source = _samai_source(db_session)
    doc = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T_CUND_25001233300020260001200",
        tipo="AUTO",
        storage_bucket="iurisync-test",
        storage_key="Tribunal Administrativo de Cundinamarca/seccion/2026-08-03/AUTO/doc.pdf",
    )

    result = backfill(db_session)

    db_session.refresh(doc)
    assert doc.tipo == "Auto"
    assert result["documents_updated"] == 1


def test_backfill_merges_autos_plural_into_auto(db_session):
    source = _samai_source(db_session)
    doc = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T_CUND_25001233300020260001200",
        tipo="Autos",
        storage_bucket="iurisync-test",
        storage_key="Tribunal Administrativo de Cundinamarca/seccion/2026-08-03/Autos/doc.pdf",
    )

    result = backfill(db_session)

    db_session.refresh(doc)
    assert doc.tipo == "Auto"
    assert result["documents_updated"] == 1


def test_backfill_leaves_untouched_when_tipo_already_normalized(db_session):
    source = _samai_source(db_session)
    doc = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T_CUND_25001233300020260001200",
        tipo="Auto",
        storage_bucket="iurisync-test",
        storage_key="Tribunal Administrativo de Cundinamarca/seccion/2026-08-03/Auto/doc.pdf",
    )

    result = backfill(db_session)

    db_session.refresh(doc)
    assert doc.tipo == "Auto"
    assert result["documents_updated"] == 0


def test_backfill_is_idempotent_across_two_runs(db_session):
    source = _samai_source(db_session)
    doc = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T_CUND_25001233300020260001200",
        tipo="aUTO",
        storage_bucket="iurisync-test",
        storage_key="Tribunal Administrativo de Cundinamarca/seccion/2026-08-03/aUTO/doc.pdf",
    )

    backfill(db_session)
    second_result = backfill(db_session)

    db_session.refresh(doc)
    assert doc.tipo == "Auto"
    assert second_result["documents_updated"] == 0


def test_backfill_ignores_documents_from_other_families(db_session):
    repository.create_source_family(db_session, key="corte_suprema", display_name="CSJ")
    source = repository.create_source(db_session, family_key="corte_suprema", name="CSJ", family_params={})
    doc = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="CSJ_SCT_ABC1234_2026",
        tipo="AUTO",
        storage_bucket="iurisync-test",
        storage_key="CSJ/SCT/doc.pdf",
    )

    result = backfill(db_session)

    db_session.refresh(doc)
    assert doc.tipo == "AUTO"  # sin tocar — no es de la familia samai
    assert result["documents_updated"] == 0


def test_backfill_continues_after_update_failure(db_session, monkeypatch):
    source = _samai_source(db_session)
    doc1 = repository.insert_document(
        db_session,
        doc_id="doc-1",
        source_id=source.id,
        title="T_CUND_25001233300020260001200",
        tipo="AUTO",
        storage_bucket="iurisync-test",
        storage_key="Tribunal Administrativo de Cundinamarca/seccion/2026-08-03/AUTO/doc.pdf",
    )
    doc2 = repository.insert_document(
        db_session,
        doc_id="doc-2",
        source_id=source.id,
        title="T_CUND_25001233300020260001201",
        tipo="SENTENCIA",
        storage_bucket="iurisync-test",
        storage_key="Tribunal Administrativo de Cundinamarca/seccion/2026-08-03/SENTENCIA/doc2.pdf",
    )

    import core.backfill_samai_tipo as backfill_module

    real_update = repository.update_document_tipo

    def update_with_failure(db, document_id, tipo):
        if document_id == doc1.id:
            raise RuntimeError("DB no disponible")
        return real_update(db, document_id, tipo)

    monkeypatch.setattr(backfill_module.repository, "update_document_tipo", update_with_failure)

    result = backfill(db_session)

    db_session.refresh(doc1)
    db_session.refresh(doc2)
    assert doc1.tipo == "AUTO"  # sin cambios, la actualización falló
    assert doc2.tipo == "Sentencia"  # esta sí se procesó
    assert result["documents_updated"] == 1
