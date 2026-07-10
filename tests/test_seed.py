from core.db import repository
from core.seed import seed_source_families_and_sources


def test_seed_populates_families_and_sources_and_is_idempotent(db_session):
    seed_source_families_and_sources(db_session)
    seed_source_families_and_sources(db_session)  # running twice must not duplicate rows

    families = repository.list_source_families(db_session)
    assert {f.key for f in families} == {"constitucional", "samai"}

    sources = repository.list_sources(db_session)
    assert len(sources) == 1 + 28  # Corte Constitucional + 28 SAMAI corps

    samai_sources = repository.list_sources(db_session, family_key="samai")
    assert any(s.family_params.get("corp_code") == "1100103" for s in samai_sources)
