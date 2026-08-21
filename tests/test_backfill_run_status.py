from core.backfill_run_status import backfill
from core.db import repository


def _source(db_session, name="Tribunal"):
    return repository.create_source(db_session, family_key="samai", name=name, family_params={})


def test_backfill_reclassifies_a_failed_run_with_mixed_sources_as_completed_with_errors(db_session):
    """Regresión: antes del 2026-08-21, cualquier fuente fallida marcaba el run
    entero como 'failed', aunque otras hubieran terminado bien. Esos runs ya
    guardados deben pasar a 'completed_with_errors', el estado que ahora
    distingue un fracaso parcial de uno total."""
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source_ok = _source(db_session, "Tribunal OK")
    source_bad = _source(db_session, "Tribunal Fallido")
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source_ok = repository.create_run_source(db_session, run_id=run.id, source_id=source_ok.id)
    run_source_bad = repository.create_run_source(db_session, run_id=run.id, source_id=source_bad.id)
    repository.set_run_source_status(db_session, run_source_ok.id, "completed")
    repository.set_run_source_status(db_session, run_source_bad.id, "failed", error_message="boom")
    repository.set_run_status(db_session, run.id, "failed")

    result = backfill(db_session)

    db_session.refresh(run)
    assert run.status == "completed_with_errors"
    assert result == {"runs_updated": 1}


def test_backfill_leaves_a_run_where_every_source_failed_as_failed(db_session):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source1 = _source(db_session, "Tribunal A")
    source2 = _source(db_session, "Tribunal B")
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source1 = repository.create_run_source(db_session, run_id=run.id, source_id=source1.id)
    run_source2 = repository.create_run_source(db_session, run_id=run.id, source_id=source2.id)
    repository.set_run_source_status(db_session, run_source1.id, "failed", error_message="boom 1")
    repository.set_run_source_status(db_session, run_source2.id, "failed", error_message="boom 2")
    repository.set_run_status(db_session, run.id, "failed")

    result = backfill(db_session)

    db_session.refresh(run)
    assert run.status == "failed"
    assert result == {"runs_updated": 0}


def test_backfill_ignores_runs_that_are_not_failed(db_session):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source = _source(db_session)
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    repository.create_run_source(db_session, run_id=run.id, source_id=source.id)
    repository.set_run_status(db_session, run.id, "completed")

    result = backfill(db_session)

    db_session.refresh(run)
    assert run.status == "completed"
    assert result == {"runs_updated": 0}


def test_backfill_is_idempotent_across_two_runs(db_session):
    repository.create_source_family(db_session, key="samai", display_name="SAMAI")
    source_ok = _source(db_session, "Tribunal OK")
    source_bad = _source(db_session, "Tribunal Fallido")
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    run_source_ok = repository.create_run_source(db_session, run_id=run.id, source_id=source_ok.id)
    run_source_bad = repository.create_run_source(db_session, run_id=run.id, source_id=source_bad.id)
    repository.set_run_source_status(db_session, run_source_ok.id, "completed")
    repository.set_run_source_status(db_session, run_source_bad.id, "failed", error_message="boom")
    repository.set_run_status(db_session, run.id, "failed")

    backfill(db_session)
    second_result = backfill(db_session)

    db_session.refresh(run)
    assert run.status == "completed_with_errors"
    assert second_result == {"runs_updated": 0}
