from core.reporting_pdf import render_monthly_report_pdf

_DATA_VACIA = {
    "period": None,
    "period_label": "Agosto 2026",
    "resumen": {"docs_new": 0, "docs_updated": 0, "docs_errors": 0, "runs_by_status": {}, "storage_bytes": 0},
    "por_fuente": [],
    "fuentes_sin_actividad": [],
    "errores": [],
    "comparacion": [],
    "is_partial": False,
    "as_of_label": None,
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
    "is_partial": True,
    "as_of_label": "datos hasta el 17 de septiembre de 2026",
}


def test_render_monthly_report_pdf_produces_a_valid_pdf_for_an_empty_month():
    pdf_bytes = render_monthly_report_pdf(_DATA_VACIA)

    assert pdf_bytes.startswith(b"%PDF")


def test_render_monthly_report_pdf_produces_a_valid_pdf_with_full_content():
    pdf_bytes = render_monthly_report_pdf(_DATA_CON_CONTENIDO)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000


def test_render_monthly_report_pdf_wraps_long_text_cells_with_special_chars():
    """Regression test: long text + & and < characters must wrap and escape properly."""
    long_source = "Superintendencia de Vigilancia & Seguridad Privada"
    long_message = "Error downloading document: connection timeout after 300s & retry < 3 times attempted due to network < issues & server unavailable status reported from upstream API endpoint which indicates the remote service was temporarily down for maintenance or overloaded with requests processing queue was full and could not accept new submissions at the time of the request " + ("x" * 50)  # ~300 chars with special chars

    data_con_texto_largo = {
        "period": None,
        "period_label": "Agosto 2026",
        "resumen": {
            "docs_new": 1, "docs_updated": 0, "docs_errors": 1,
            "runs_by_status": {"failed": 1}, "storage_bytes": 0,
        },
        "por_fuente": [
            {"source_id": 1, "source_name": long_source, "docs_new": 1, "docs_updated": 0, "docs_errors": 1, "had_failure": True},
        ],
        "fuentes_sin_actividad": [],
        "errores": [
            {"source_name": long_source, "message": long_message, "occurred_at": __import__("datetime").datetime(2026, 8, 15, 10, 30)},
        ],
        "comparacion": [
            {"source_name": long_source, "docs_new_actual": 1, "docs_new_anterior": 0, "variacion_pct": None},
        ],
    }

    pdf_bytes = render_monthly_report_pdf(data_con_texto_largo)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000


def test_render_monthly_report_pdf_escapes_special_chars_in_fuentes_sin_actividad():
    """Regression test: source names with XML special chars in fuentes_sin_actividad must be escaped."""
    data_with_special_chars = {
        "period": None,
        "period_label": "Agosto 2026",
        "resumen": {"docs_new": 0, "docs_updated": 0, "docs_errors": 0, "runs_by_status": {}, "storage_bytes": 0},
        "por_fuente": [],
        "fuentes_sin_actividad": ["Super & Cía <Vigilancia>"],
        "errores": [],
        "comparacion": [],
    }

    pdf_bytes = render_monthly_report_pdf(data_with_special_chars)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000
