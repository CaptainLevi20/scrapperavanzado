from core.db import repository
from core.seed import seed_source_families_and_sources


def test_seed_populates_families_and_sources_and_is_idempotent(db_session):
    seed_source_families_and_sources(db_session)
    seed_source_families_and_sources(db_session)  # running twice must not duplicate rows

    families = repository.list_source_families(db_session)
    assert {f.key for f in families} == {
        "constitucional", "samai", "corte_suprema", "jep", "cndj",
        "adr", "adres", "ane", "anh", "rama_judicial",
    }

    sources = repository.list_sources(db_session)
    # 1 (Corte Constitucional) + 28 (SAMAI) + 7 (fuente única: corte_suprema, jep, cndj,
    # adr, adres, ane, anh) + 33 (Tribunales Superiores, incl. Bogotá D.C.) + 6 (tipos de Juzgado) = 75
    assert len(sources) == 1 + 28 + 7 + 33 + 6

    rama_judicial_sources = repository.list_sources(db_session, family_key="rama_judicial")
    assert len(rama_judicial_sources) == 39
    assert any(s.family_params.get("dept_code") == "05" for s in rama_judicial_sources)
    assert any(
        s.family_params.get("entidad_id") == "31" and s.family_params.get("dept_code") == ""
        for s in rama_judicial_sources
    )
