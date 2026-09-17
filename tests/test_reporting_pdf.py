from core.reporting_pdf import render_monthly_report_pdf

_DATA_VACIA = {
    "period": None,
    "period_label": "Agosto 2026",
    "resumen": {"docs_new": 0, "docs_updated": 0, "docs_errors": 0, "runs_by_status": {}, "storage_bytes": 0},
    "por_fuente": [],
    "fuentes_sin_actividad": [],
    "errores": [],
    "comparacion": [],
}

_DATA_CON_CONTENIDO = {
    "period": None,
    "period_label": "Agosto 2026",
    "resumen": {
        "docs_new": 8, "docs_updated": 1, "docs_errors": 2,
        "runs_by_status": {"completed": 3, "failed": 1}, "storage_bytes": 5_242_880,
    },
    "por_fuente": [
        {"source_id": 1, "source_name": "Corte Constitucional", "docs_new": 5, "docs_updated": 1, "docs_errors": 0, "had_failure": False},
        {"source_id": 2, "source_name": "CSJ", "docs_new": 3, "docs_updated": 0, "docs_errors": 2, "had_failure": True},
    ],
    "fuentes_sin_actividad": ["Minhacienda"],
    "errores": [
        {"source_name": "CSJ", "message": "Timeout al descargar", "occurred_at": __import__("datetime").datetime(2026, 8, 15, 10, 30)},
    ],
    "comparacion": [
        {"source_name": "Corte Constitucional", "docs_new_actual": 5, "docs_new_anterior": 0, "variacion_pct": None},
        {"source_name": "CSJ", "docs_new_actual": 3, "docs_new_anterior": 6, "variacion_pct": -50.0},
    ],
}


def test_render_monthly_report_pdf_produces_a_valid_pdf_for_an_empty_month():
    pdf_bytes = render_monthly_report_pdf(_DATA_VACIA)

    assert pdf_bytes.startswith(b"%PDF")


def test_render_monthly_report_pdf_produces_a_valid_pdf_with_full_content():
    pdf_bytes = render_monthly_report_pdf(_DATA_CON_CONTENIDO)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000
