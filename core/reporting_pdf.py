from io import BytesIO
from typing import Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_TABLE_STYLE = TableStyle(
    [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b2b2b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
)

_CELL_STYLE = ParagraphStyle("cell", parent=getSampleStyleSheet()["Normal"], fontSize=9, leading=11)


def _format_bytes(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value / (1024 * 1024):.1f} MB"


def _variacion_texto(variacion_pct: Optional[float]) -> str:
    if variacion_pct is None:
        return "Nueva actividad"
    signo = "+" if variacion_pct >= 0 else ""
    return f"{signo}{variacion_pct:.1f}%"


def render_monthly_report_pdf(data: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    story = [Paragraph(f"Reporte mensual de extracción — {data['period_label']}", styles["Title"]), Spacer(1, 12)]

    as_of_label = data.get("as_of_label")
    if as_of_label:
        story.append(Paragraph(escape(f"Reporte parcial — {as_of_label}."), styles["Italic"]))
        story.append(Spacer(1, 12))

    # Resumen general
    story.append(Paragraph("Resumen general", styles["Heading2"]))
    resumen = data["resumen"]
    resumen_rows = [
        ["Métrica", "Valor"],
        ["Documentos nuevos", str(resumen["docs_new"])],
        ["Documentos actualizados", str(resumen["docs_updated"])],
        ["Documentos con error", str(resumen["docs_errors"])],
        ["Espacio agregado este mes", _format_bytes(resumen["storage_bytes"])],
    ]
    for run_status, count in sorted(resumen["runs_by_status"].items()):
        resumen_rows.append([f"Corridas — {run_status}", str(count)])
    resumen_table = Table(resumen_rows, hAlign="LEFT")
    resumen_table.setStyle(_TABLE_STYLE)
    story.append(resumen_table)
    story.append(Spacer(1, 18))

    # Detalle por fuente
    story.append(Paragraph("Detalle por fuente", styles["Heading2"]))
    por_fuente = data["por_fuente"]
    if por_fuente:
        fuente_rows = [["Fuente", "Nuevos", "Actualizados", "Errores", "Con fallas"]]
        for row in por_fuente:
            fuente_rows.append(
                [
                    Paragraph(escape(row["source_name"]), _CELL_STYLE),
                    str(row["docs_new"]),
                    str(row["docs_updated"]),
                    str(row["docs_errors"]),
                    "Sí" if row["had_failure"] else "No",
                ]
            )
        fuente_table = Table(fuente_rows, hAlign="LEFT")
        fuente_table.setStyle(_TABLE_STYLE)
        story.append(fuente_table)
    else:
        story.append(Paragraph("Ninguna fuente tuvo actividad este mes.", styles["Normal"]))
    if data["fuentes_sin_actividad"]:
        story.append(Spacer(1, 8))
        nombres = ", ".join(escape(nombre) for nombre in data["fuentes_sin_actividad"])
        story.append(Paragraph(f"Fuentes activas sin actividad este mes: {nombres}.", styles["Normal"]))
    story.append(Spacer(1, 18))

    # Documentos por fuente y tipo
    story.append(Paragraph("Documentos por fuente y tipo", styles["Heading2"]))
    story.append(
        Paragraph(
            "Contados por fecha de descarga del documento; puede diferir de 'Documentos nuevos' del resumen.",
            styles["Italic"],
        )
    )
    story.append(Spacer(1, 6))
    documentos_por_tipo = data.get("documentos_por_tipo")
    if documentos_por_tipo:
        tipo_rows = [["Fuente", "Tipo", "Cantidad"]]
        for fuente in documentos_por_tipo:
            source_label = Paragraph(escape(f"{fuente['source_name']} — total {fuente['total']}"), _CELL_STYLE)
            tipo_rows.append([source_label, "", ""])
            for tipo_row in fuente["tipos"]:
                tipo_rows.append(["", tipo_row["tipo"], str(tipo_row["count"])])
        tipo_table = Table(tipo_rows, hAlign="LEFT")
        tipo_table.setStyle(_TABLE_STYLE)
        story.append(tipo_table)
    else:
        story.append(Paragraph("Ninguna fuente descargó documentos este mes.", styles["Normal"]))
    story.append(Spacer(1, 18))

    # Detalle de errores
    story.append(Paragraph("Detalle de errores", styles["Heading2"]))
    errores = data["errores"]
    if errores:
        error_rows = [["Fuente", "Fecha", "Mensaje"]]
        for error in errores:
            error_rows.append(
                [
                    Paragraph(escape(error["source_name"]), _CELL_STYLE),
                    error["occurred_at"].strftime("%Y-%m-%d %H:%M"),
                    Paragraph(escape(error["message"]), _CELL_STYLE),
                ]
            )
        error_table = Table(error_rows, hAlign="LEFT", colWidths=[4 * cm, 3 * cm, 9 * cm])
        error_table.setStyle(_TABLE_STYLE)
        story.append(error_table)
    else:
        story.append(Paragraph("Sin errores registrados este mes.", styles["Normal"]))
    story.append(Spacer(1, 18))

    # Comparación con el mes anterior
    story.append(Paragraph("Comparación con el mes anterior", styles["Heading2"]))
    comparacion = data["comparacion"]
    if comparacion:
        comparacion_rows = [["Fuente", "Este mes", "Mes anterior", "Variación"]]
        for row in comparacion:
            comparacion_rows.append(
                [
                    Paragraph(escape(row["source_name"]), _CELL_STYLE),
                    str(row["docs_new_actual"]),
                    str(row["docs_new_anterior"]),
                    _variacion_texto(row["variacion_pct"]),
                ]
            )
        comparacion_table = Table(comparacion_rows, hAlign="LEFT")
        comparacion_table.setStyle(_TABLE_STYLE)
        story.append(comparacion_table)
    else:
        story.append(Paragraph("Sin datos suficientes para comparar con el mes anterior.", styles["Normal"]))

    doc.build(story)
    return buffer.getvalue()
