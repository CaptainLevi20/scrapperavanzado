from datetime import date, datetime, timezone

import core.reporting as reporting
from core.db import repository
from core.reporting import build_monthly_report_data, period_label, previous_period


def test_previous_period_handles_year_rollover():
    assert previous_period(date(2026, 1, 1)) == date(2025, 12, 1)
    assert previous_period(date(2026, 8, 1)) == date(2026, 7, 1)


def test_period_label_is_in_spanish():
    assert period_label(date(2026, 8, 1)) == "Agosto 2026"
    assert period_label(date(2026, 1, 1)) == "Enero 2026"


def test_date_bounds_handles_year_rollover():
    assert reporting._date_bounds(date(2026, 12, 1)) == (date(2026, 12, 1), date(2027, 1, 1))
    assert reporting._date_bounds(date(2026, 8, 1)) == (date(2026, 8, 1), date(2026, 9, 1))


def _fuente(db_session, source_name, active=True):
    family_key = source_name.lower().replace(" ", "-")
    repository.create_source_family(db_session, key=family_key, display_name=source_name)
    source = repository.create_source(db_session, family_key=family_key, name=source_name, family_params={})
    if not active:
        repository.update_source(db_session, source.id, active=False)
    return source


def _corrida(db_session, source, started_at, docs_new=0, docs_updated=0, docs_errors=0, run_status="completed"):
    run = repository.create_run(db_session, triggered_by="manual", fini=None, ffin=None)
    repository.set_run_status(db_session, run.id, run_status, started_at=started_at)
    run_source = repository.create_run_source(db_session, run_id=run.id, source_id=source.id)
    repository.set_run_source_status(
        db_session, run_source.id, run_status, docs_new=docs_new, docs_updated=docs_updated, docs_errors=docs_errors
    )
    return run, run_source


def _documento(db_session, source, doc_id, f_public, downloaded_at=None, tipo=None, file_size_bytes=None):
    kwargs = dict(
        doc_id=doc_id, source_id=source.id, title=f"Doc {doc_id}",
        storage_bucket="iurisync-test", storage_key=f"{doc_id}.pdf",
        f_public=f_public, tipo=tipo, file_size_bytes=file_size_bytes,
    )
    if downloaded_at is not None:
        kwargs["downloaded_at"] = downloaded_at
    return repository.insert_document(db_session, **kwargs)


def test_build_monthly_report_data_for_an_empty_month_is_all_zeros(db_session):
    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert data["period_label"] == "Agosto 2026"
    assert data["resumen"] == {"total_documentos": 0, "storage_bytes": 0, "num_fuentes": 0}
    assert data["por_fuente"] == []
    assert data["fuentes_sin_publicaciones"] == []
    assert data["documentos_por_tipo"] == []
    assert data["comparacion"] == []
    assert data["actividad"] == {"runs_by_status": {}}
    assert data["errores"] == []


def test_build_monthly_report_data_totals_come_from_publication_date_not_downloaded_at(db_session):
    """The whole report counts by f_public. downloaded_at is set OUTSIDE the month
    (January) for every document to prove it no longer affects the counts."""
    source = _fuente(db_session, "Corte Constitucional")
    fuera_de_mes = datetime(2026, 1, 5, tzinfo=timezone.utc)
    _documento(db_session, source, "d1", date(2026, 8, 5), downloaded_at=fuera_de_mes, file_size_bytes=1000)
    _documento(db_session, source, "d2", date(2026, 8, 20), downloaded_at=fuera_de_mes, file_size_bytes=2000)
    # f_public fuera del mes (julio) aunque downloaded_at caiga dentro de agosto: no debe contar.
    _documento(db_session, source, "d3", date(2026, 7, 31), downloaded_at=datetime(2026, 8, 10, tzinfo=timezone.utc), file_size_bytes=500)

    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert data["resumen"] == {"total_documentos": 2, "storage_bytes": 3000, "num_fuentes": 1}
    assert data["por_fuente"] == [{"source_id": source.id, "source_name": "Corte Constitucional", "total": 2}]


def test_build_monthly_report_data_por_fuente_sorted_by_total_desc_then_name(db_session):
    fuente_a = _fuente(db_session, "Corte Constitucional")
    fuente_b = _fuente(db_session, "CSJ")
    _documento(db_session, fuente_a, "a1", date(2026, 8, 5))
    _documento(db_session, fuente_b, "b1", date(2026, 8, 5))
    _documento(db_session, fuente_b, "b2", date(2026, 8, 6))
    _documento(db_session, fuente_b, "b3", date(2026, 8, 7))

    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert data["por_fuente"] == [
        {"source_id": fuente_b.id, "source_name": "CSJ", "total": 3},
        {"source_id": fuente_a.id, "source_name": "Corte Constitucional", "total": 1},
    ]


def test_build_monthly_report_data_documentos_por_tipo_groups_by_source_and_tipo_por_publicacion(db_session):
    source = _fuente(db_session, "Corte Constitucional")
    fuera_de_mes = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _documento(db_session, source, "d1", date(2026, 8, 5), downloaded_at=fuera_de_mes, tipo="Sentencia")
    _documento(db_session, source, "d2", date(2026, 8, 10), downloaded_at=fuera_de_mes, tipo="Sentencia")
    _documento(db_session, source, "d3", date(2026, 8, 11), downloaded_at=fuera_de_mes, tipo="Sentencia")
    _documento(db_session, source, "d4", date(2026, 8, 12), downloaded_at=fuera_de_mes, tipo="Auto")
    _documento(db_session, source, "d5", date(2026, 8, 13), downloaded_at=fuera_de_mes, tipo="Auto")
    _documento(db_session, source, "d6", date(2026, 8, 20), downloaded_at=fuera_de_mes, tipo=None)
    # Fuera del mes por f_public, aunque su downloaded_at hubiera caído en agosto.
    _documento(db_session, source, "d7", date(2026, 7, 30), downloaded_at=datetime(2026, 8, 15, tzinfo=timezone.utc), tipo="Sentencia")

    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert data["documentos_por_tipo"] == [
        {
            "source_name": "Corte Constitucional",
            "total": 6,
            "tipos": [
                {"tipo": "Sentencia", "count": 3},
                {"tipo": "Auto", "count": 2},
                {"tipo": "Sin tipo", "count": 1},
            ],
        }
    ]


def test_build_monthly_report_data_comparison_marks_new_activity_when_previous_month_was_zero(db_session):
    source = _fuente(db_session, "Corte Constitucional")
    _documento(db_session, source, "d1", date(2026, 8, 5))
    _documento(db_session, source, "d2", date(2026, 8, 6))

    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert data["comparacion"] == [
        {"source_name": "Corte Constitucional", "total_actual": 2, "total_anterior": 0, "variacion_pct": None}
    ]


def test_build_monthly_report_data_comparison_computes_percentage_change(db_session):
    source = _fuente(db_session, "Corte Constitucional")
    for i in range(10):
        _documento(db_session, source, f"jul{i}", date(2026, 7, 10 + (i % 15)))
    for i in range(15):
        _documento(db_session, source, f"ago{i}", date(2026, 8, 10))

    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert data["comparacion"] == [
        {"source_name": "Corte Constitucional", "total_actual": 15, "total_anterior": 10, "variacion_pct": 50.0}
    ]


def test_build_monthly_report_data_comparison_skips_sources_with_zero_in_both_months(db_session):
    # Fuente activa pero sin ninguna publicación ni este mes ni el anterior: no debe
    # aparecer en la comparación (solo en fuentes_sin_publicaciones).
    _fuente(db_session, "Minhacienda")

    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert data["comparacion"] == []
    assert data["fuentes_sin_publicaciones"] == ["Minhacienda"]


def test_build_monthly_report_data_marks_the_current_month_as_partial(db_session, monkeypatch):
    monkeypatch.setattr(reporting, "_now", lambda: datetime(2026, 9, 17, tzinfo=timezone.utc))

    data = build_monthly_report_data(db_session, date(2026, 9, 1))

    assert data["is_partial"] is True
    assert data["as_of_label"] is not None
    assert "17 de septiembre de 2026" in data["as_of_label"]


def test_build_monthly_report_data_a_closed_month_is_not_partial(db_session, monkeypatch):
    monkeypatch.setattr(reporting, "_now", lambda: datetime(2026, 9, 17, tzinfo=timezone.utc))

    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert data["is_partial"] is False
    assert data["as_of_label"] is None


def test_build_monthly_report_data_actividad_reflects_runs_by_started_at(db_session):
    source = _fuente(db_session, "Corte Constitucional")
    _corrida(db_session, source, datetime(2026, 8, 10, tzinfo=timezone.utc), docs_new=1, run_status="completed")
    _corrida(db_session, source, datetime(2026, 8, 12, tzinfo=timezone.utc), docs_new=1, run_status="completed")
    _corrida(db_session, source, datetime(2026, 8, 15, tzinfo=timezone.utc), run_status="failed")
    # Corrida fuera del mes: no debe contar en la actividad.
    _corrida(db_session, source, datetime(2026, 7, 15, tzinfo=timezone.utc), run_status="completed")

    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert data["actividad"] == {"runs_by_status": {"completed": 2, "failed": 1}}


def test_build_monthly_report_data_errores_still_by_run_date_and_truncated(db_session):
    source = _fuente(db_session, "Corte Constitucional")
    _run, run_source = _corrida(db_session, source, datetime(2026, 8, 10, tzinfo=timezone.utc))
    repository.add_run_error(db_session, run_source.id, "x" * 400)
    # Error de una corrida de julio: no debe salir en el reporte de agosto.
    _run2, run_source2 = _corrida(db_session, source, datetime(2026, 7, 10, tzinfo=timezone.utc))
    repository.add_run_error(db_session, run_source2.id, "error de julio")

    data = build_monthly_report_data(db_session, date(2026, 8, 1))

    assert len(data["errores"]) == 1
    assert data["errores"][0]["source_name"] == "Corte Constitucional"
    assert len(data["errores"][0]["message"]) == 301  # 300 + "…"
    assert data["errores"][0]["message"].endswith("…")
