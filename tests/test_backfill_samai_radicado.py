from core.backfill_samai_radicado import _radicado_from_title, backfill
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


def test_backfill_populates_radicado_for_all_three_real_samai_title_formats(db_session):
    repository.create_source_family_if_missing(db_session, key="samai", display_name="SAMAI")
    consejo = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
    tribunal = repository.create_source(db_session, family_key="samai", name="Tribunal Administrativo de Cundinamarca", family_params={})

    # Consejo de Estado, con guiones.
    doc_dashed = repository.insert_document(
        db_session, doc_id="doc-dashed", source_id=consejo.id,
        title="25000-23-37-000-2021-00423-01(NRD)", storage_bucket="iurisync-test", storage_key="a.pdf",
    )
    # Consejo de Estado, con guiones y grupo complementario extra.
    doc_dashed_complement = repository.insert_document(
        db_session, doc_id="doc-dashed-complement", source_id=consejo.id,
        title="66001-23-33-000-2017-00141-01(3104-2023)(NRD)", storage_bucket="iurisync-test", storage_key="b.pdf",
    )
    # Tribunal Administrativo: prefijo T_{CODIGO}_ y sin paréntesis.
    doc_tribunal = repository.insert_document(
        db_session, doc_id="doc-tribunal", source_id=tribunal.id,
        title="T_CUND_25001233300020260001200", storage_bucket="iurisync-test", storage_key="c.pdf",
    )

    result = backfill(db_session)

    db_session.refresh(doc_dashed)
    db_session.refresh(doc_dashed_complement)
    db_session.refresh(doc_tribunal)
    assert doc_dashed.radicado == "25000233700020210042301"
    assert doc_dashed_complement.radicado == "66001233300020170014101"
    assert doc_tribunal.radicado == "25001233300020260001200"
    assert result["documents_updated"] == 3


def test_radicado_from_title_matches_dashed_consejo_de_estado_format():
    assert _radicado_from_title("25000-23-37-000-2021-00423-01(NRD)") == "25000233700020210042301"


def test_radicado_from_title_matches_dashed_consejo_de_estado_with_complement_group():
    assert _radicado_from_title("66001-23-33-000-2017-00141-01(3104-2023)(NRD)") == "66001233300020170014101"


def test_radicado_from_title_matches_tribunal_administrativo_format_without_parens():
    assert _radicado_from_title("T_CUND_25001233300020260001200") == "25001233300020260001200"


def test_radicado_from_title_matches_bare_undashed_digits_format():
    assert _radicado_from_title("25000234200020200000801(NRD)") == "25000234200020200000801"


def test_radicado_from_title_rejects_titles_without_case_form():
    assert _radicado_from_title("DR. WILLIAM SANTA MARIN") is None


def test_radicado_from_title_rejects_wrong_length_digit_strings():
    assert _radicado_from_title("123(NRD)") is None
