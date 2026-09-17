from datetime import date, datetime, timezone

from core.db import repository
from core.reporting import build_monthly_report_data, period_label, previous_period


def test_previous_period_handles_year_rollover():
    assert previous_period(date(2026, 1, 1)) == date(2025, 12, 1)
    assert previous_period(date(2026, 8, 1)) == date(2026, 7, 1)


def test_period_label_is_in_spanish():
    assert period_label(date(2026, 8, 1)) == "Agosto 2026"
    assert period_label(date(2026, 1, 1)) == "Enero 2026"


def _fuente_con_corrida(db_session, source_name, started_at, docs_new=0, docs_updated=0, docs_errors=0, run_status="completed"):
    family_key = source_name.lower().replace(" ", "-")
    repository.create_source_family(db_session, key=family_key, display_name=source_name)
    source = repository.create_source(db_session, family_key=family_key, name=source_name, family_params={})
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    repository.set_run_status(db_session, run.id, run_status, started_at=started_at)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)
    repository.set_run_source_status(
        db_session, run_source.id, run_status, docs_new=docs_new, docs_updated=docs_updated, docs_errors=docs_errors
    )
    return source


def test_build_monthly_report_data_for_an_empty_month_is_all_zeros(db_session):
    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert data["period_label"] == "Agosto 2026"
    assert data["resumen"]["docs_new"] == 0
    assert data["resumen"]["docs_updated"] == 0
    assert data["resumen"]["docs_errors"] == 0
    assert data["resumen"]["runs_by_status"] == {}
    assert data["resumen"]["storage_bytes"] == 0
    assert data["por_fuente"] == []
    assert data["errores"] == []
    assert data["comparacion"] == []


def test_build_monthly_report_data_totals_the_summary_from_per_source_rows(db_session):
    _fuente_con_corrida(db_session, "Corte Constitucional", datetime(2026, 8, 10, tzinfo=timezone.utc), docs_new=5, docs_updated=1, docs_errors=2)
    _fuente_con_corrida(db_session, "CSJ", datetime(2026, 8, 12, tzinfo=timezone.utc), docs_new=3)

    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert data["resumen"]["docs_new"] == 8
    assert data["resumen"]["docs_updated"] == 1
    assert data["resumen"]["docs_errors"] == 2
    assert len(data["por_fuente"]) == 2


def test_build_monthly_report_data_truncates_error_messages_to_300_chars(db_session):
    source = _fuente_con_corrida(db_session, "Corte Constitucional", datetime(2026, 8, 10, tzinfo=timezone.utc))
    run_source = repository.list_run_sources_with_source_names(
        db_session, repository.list_runs(db_session)[0].id
    )[0]
    repository.add_run_error(db_session, run_source.id, "x" * 400)

    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert len(data["errores"][0]["message"]) == 301  # 300 + "…"
    assert data["errores"][0]["message"].endswith("…")


def test_build_monthly_report_data_comparison_marks_new_activity_when_previous_month_was_zero(db_session):
    _fuente_con_corrida(db_session, "Corte Constitucional", datetime(2026, 8, 10, tzinfo=timezone.utc), docs_new=5)

    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert data["comparacion"] == [
        {"source_name": "Corte Constitucional", "docs_new_actual": 5, "docs_new_anterior": 0, "variacion_pct": None}
    ]


def test_build_monthly_report_data_comparison_computes_percentage_change(db_session):
    family_key = "constitucional"
    repository.create_source_family(db_session, key=family_key, display_name="Corte Constitucional")
    source = repository.create_source(db_session, family_key=family_key, name="Corte Constitucional", family_params={})

    run_julio = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    repository.set_run_status(db_session, run_julio.id, "completed", started_at=datetime(2026, 7, 10, tzinfo=timezone.utc))
    run_source_julio = repository.create_run_source(db_session, run_id=run_julio.id, source_id=source.id)
    repository.set_run_source_status(db_session, run_source_julio.id, "completed", docs_new=10)

    run_agosto = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    repository.set_run_status(db_session, run_agosto.id, "completed", started_at=datetime(2026, 8, 10, tzinfo=timezone.utc))
    run_source_agosto = repository.create_run_source(db_session, run_id=run_agosto.id, source_id=source.id)
    repository.set_run_source_status(db_session, run_source_agosto.id, "completed", docs_new=15)

    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert data["comparacion"] == [
        {"source_name": "Corte Constitucional", "docs_new_actual": 15, "docs_new_anterior": 10, "variacion_pct": 50.0}
    ]


def test_build_monthly_report_data_comparison_skips_sources_with_zero_in_both_months(db_session):
    # Fuente activa pero sin ninguna corrida ni este mes ni el anterior: no debe
    # aparecer en la comparación (solo en fuentes_sin_actividad).
    repository.create_source_family(db_session, key="minhacienda", display_name="Minhacienda")
    repository.create_source(db_session, family_key="minhacienda", name="Minhacienda", family_params={})

    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert data["comparacion"] == []
    assert data["fuentes_sin_actividad"] == ["Minhacienda"]
