from core.db import repository
from core.seed import seed_source_families_and_sources


def test_seed_running_concurrently_does_not_crash_or_duplicate_rows(test_engine, db_session):
    # db_session isn't used directly (each thread below opens its own session
    # to reproduce the real race) — it's here for its setup side effect: a
    # fresh drop_all/create_all, so this test's exact-count assertions aren't
    # thrown off by rows any other test left behind in the shared test DB.
    """Regression test: seed_source_families_and_sources used to list what
    already existed and only then create what was missing — two processes
    seeding at the same time (e.g. `python -m core.seed` launched twice at
    once) could both see nothing yet, both try to insert the same row, and the
    loser would crash on a duplicate-key IntegrityError partway through,
    leaving the catalog incomplete. Runs two real, separate DB sessions on
    separate threads to reproduce the actual race, not just sequential calls
    on one session (which the idempotency test above already covers)."""
    import threading

    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=test_engine, future=True)
    errors: list[Exception] = []

    def _run_seed():
        session = session_factory()
        try:
            seed_source_families_and_sources(session)
        except Exception as exc:  # pragma: no cover - only hit if the race still crashes
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=_run_seed) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert errors == []

    assertion_session = session_factory()
    try:
        families = repository.list_source_families(assertion_session)
        assert len(families) == 10

        sources = repository.list_sources(assertion_session, limit=500)
        assert len(sources) == 1 + 28 + 7 + 33 + 6
    finally:
        assertion_session.close()


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
