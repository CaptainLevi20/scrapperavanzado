from datetime import date

from core.backfill_ce_titles_sin_acronimo import _quitar_acronimo, backfill
from core.db import repository


def test_quitar_acronimo_removes_a_bare_acronimo():
    assert _quitar_acronimo("25000-23-37-000-2021-00423-01(NRD)") == "25000-23-37-000-2021-00423-01"


def test_quitar_acronimo_keeps_the_case_number_and_removes_only_the_acronimo():
    assert _quitar_acronimo("25000-23-37-000-2021-00423-01(30146)(NRD)") == (
        "25000-23-37-000-2021-00423-01(30146)"
    )


def test_quitar_acronimo_handles_the_raw_undashed_format():
    assert _quitar_acronimo("25000234200020200000801(NRD)") == "25000234200020200000801"


def test_quitar_acronimo_returns_none_for_a_bare_radicado():
    # Nada que quitar → None (para que la corrida sea idempotente).
    assert _quitar_acronimo("11001-03-24-000-2026-99999-00") is None


def test_quitar_acronimo_returns_none_when_only_a_number_is_present():
    # El número de caso NO es el acrónimo y se conserva.
    assert _quitar_acronimo("11001-03-24-000-2026-99999-00(30146)") is None


def test_quitar_acronimo_does_not_touch_tribunal_administrativo_titles():
    assert _quitar_acronimo("T_ANTI_05001_23_33_000_2018_01895_00") is None


def test_backfill_strips_acronimo_from_stored_ce_titles(db_session):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
    repository.insert_document(
        db_session, doc_id="con-acronimo", source_id=source.id,
        title="25000-23-37-000-2021-00423-01(NRD)",
        storage_bucket="iurisync-test", storage_key="a.pdf", f_public=date(2026, 7, 14),
    )
    repository.insert_document(
        db_session, doc_id="numero-y-acronimo", source_id=source.id,
        title="25000-23-37-000-2021-00423-01(30146)(NRD)",
        storage_bucket="iurisync-test", storage_key="b.pdf", f_public=date(2026, 7, 15),
    )
    repository.insert_document(
        db_session, doc_id="sin-acronimo", source_id=source.id,
        title="11001-03-24-000-2026-99999-00",
        storage_bucket="iurisync-test", storage_key="c.pdf", f_public=date(2026, 7, 16),
    )

    result = backfill(db_session)

    assert result["documents_updated"] == 2
    titulos = {
        d.doc_id: d.title
        for d in repository.list_documents(db_session, family_key="samai")[0]
    }
    assert titulos["con-acronimo"] == "25000-23-37-000-2021-00423-01"
    assert titulos["numero-y-acronimo"] == "25000-23-37-000-2021-00423-01(30146)"
    assert titulos["sin-acronimo"] == "11001-03-24-000-2026-99999-00"


def test_backfill_is_idempotent(db_session):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = repository.create_source(db_session, family_key="samai", name="Consejo de Estado", family_params={})
    repository.insert_document(
        db_session, doc_id="con-acronimo", source_id=source.id,
        title="25000-23-37-000-2021-00423-01(NRD)",
        storage_bucket="iurisync-test", storage_key="a.pdf", f_public=date(2026, 7, 14),
    )

    assert backfill(db_session)["documents_updated"] == 1
    assert backfill(db_session)["documents_updated"] == 0
