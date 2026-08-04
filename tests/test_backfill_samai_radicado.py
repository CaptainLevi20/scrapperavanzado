from core.backfill_samai_radicado import backfill
from core.db import repository


def test_backfill_populates_radicado_and_generates_suggestions(db_session):
    repository.create_source_family_if_missing(db_session, key="samai", display_name="SAMAI")
    tribunal = repository.create_source(db_session, family_key="samai", name="Tribunal Administrativo de Antioquia", family_params={})
    consejo = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
    doc_a = repository.insert_document(
        db_session, doc_id="doc-a", source_id=tribunal.id,
        title="25000234200020200000801(NRD)", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    doc_b = repository.insert_document(
        db_session, doc_id="doc-b", source_id=consejo.id,
        title="25000234200020200000802(NRD)", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    # Título que NO tiene forma de caso (respaldo del scraper) — no debe
    # producir un radicado ni participar en la comparación.
    doc_c = repository.insert_document(
        db_session, doc_id="doc-c", source_id=tribunal.id,
        title="DR. WILLIAM SANTA MARIN", storage_bucket="iurisync-test", storage_key="c.pdf",
    )

    result = backfill(db_session)

    db_session.refresh(doc_a)
    db_session.refresh(doc_b)
    db_session.refresh(doc_c)
    assert doc_a.radicado == "25000234200020200000801"
    assert doc_b.radicado == "25000234200020200000802"
    assert doc_c.radicado is None
    assert result["documents_updated"] == 2
    assert result["suggestions_created"] == 1
    assert len(repository.list_pending_case_link_suggestions(db_session)) == 1
