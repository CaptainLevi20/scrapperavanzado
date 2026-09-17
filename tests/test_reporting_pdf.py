from core.reporting_pdf import render_monthly_report_pdf

_DATA_VACIA = {
    "period": None,
    "period_label": "Agosto 2026",
    "is_partial": False,
    "as_of_label": None,
    "resumen": {"total_documentos": 0, "storage_bytes": 0, "num_fuentes": 0},
    "por_fuente": [],
    "fuentes_sin_publicaciones": [],
    "documentos_por_tipo": [],
    "comparacion": [],
    "actividad": {"runs_by_status": {}},
    "errores": [],
}

_DATA_CON_CONTENIDO = {
    "period": None,
    "period_label": "Agosto 2026",
    "is_partial": True,
    "as_of_label": "datos hasta el 17 de septiembre de 2026",
    "resumen": {"total_documentos": 8, "storage_bytes": 5_242_880, "num_fuentes": 2},
    "por_fuente": [
        {"source_id": 1, "source_name": "Corte Constitucional", "total": 5},
        {"source_id": 2, "source_name": "CSJ", "total": 3},
    ],
    "fuentes_sin_publicaciones": ["Minhacienda"],
    "documentos_por_tipo": [
        {
            "source_name": "Corte Constitucional",
            "total": 5,
            "tipos": [
                {"tipo": "Sentencia", "count": 3},
                {"tipo": "Auto", "count": 2},
            ],
        }
    ],
    "comparacion": [
        {"source_name": "Corte Constitucional", "total_actual": 5, "total_anterior": 0, "variacion_pct": None},
        {"source_name": "CSJ", "total_actual": 3, "total_anterior": 6, "variacion_pct": -50.0},
    ],
    "actividad": {"runs_by_status": {"completed": 3, "failed": 1}},
    "errores": [
        {"source_name": "CSJ", "message": "Timeout al descargar", "occurred_at": __import__("datetime").datetime(2026, 8, 15, 10, 30)},
    ],
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
        "is_partial": False,
        "as_of_label": None,
        "resumen": {"total_documentos": 1, "storage_bytes": 0, "num_fuentes": 1},
        "por_fuente": [
            {"source_id": 1, "source_name": long_source, "total": 1},
        ],
        "fuentes_sin_publicaciones": [],
        "documentos_por_tipo": [],
        "comparacion": [
            {"source_name": long_source, "total_actual": 1, "total_anterior": 0, "variacion_pct": None},
        ],
        "actividad": {"runs_by_status": {"failed": 1}},
        "errores": [
            {"source_name": long_source, "message": long_message, "occurred_at": __import__("datetime").datetime(2026, 8, 15, 10, 30)},
        ],
    }

    pdf_bytes = render_monthly_report_pdf(data_con_texto_largo)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000


def test_render_monthly_report_pdf_escapes_special_chars_in_fuentes_sin_publicaciones():
    """Regression test: source names with XML special chars in fuentes_sin_publicaciones must be escaped."""
    data_with_special_chars = {
        "period": None,
        "period_label": "Agosto 2026",
        "resumen": {"total_documentos": 0, "storage_bytes": 0, "num_fuentes": 0},
        "por_fuente": [],
        "fuentes_sin_publicaciones": ["Super & Cía <Vigilancia>"],
        "documentos_por_tipo": [],
        "comparacion": [],
        "actividad": {"runs_by_status": {}},
        "errores": [],
    }

    pdf_bytes = render_monthly_report_pdf(data_with_special_chars)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000
