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

    # Resumen del mes
    story.append(Paragraph("Resumen del mes", styles["Heading2"]))
    resumen = data.get("resumen", {})
    resumen_rows = [
        ["Métrica", "Valor"],
        ["Documentos publicados este mes", str(resumen.get("total_documentos", 0))],
        ["Espacio de esos documentos", _format_bytes(resumen.get("storage_bytes", 0))],
        ["Fuentes con publicaciones", str(resumen.get("num_fuentes", 0))],
    ]
    resumen_table = Table(resumen_rows, hAlign="LEFT")
    resumen_table.setStyle(_TABLE_STYLE)
    story.append(resumen_table)
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            escape(
                "Cuenta documentos cuya fecha de publicación cae en el mes y que ya han sido "
                "descargados; puede aumentar si luego se descargan más."
            ),
            styles["Italic"],
        )
    )
    story.append(Spacer(1, 18))

    # Documentos por fuente
    story.append(Paragraph("Documentos por fuente", styles["Heading2"]))
    por_fuente = data.get("por_fuente", [])
    if por_fuente:
        fuente_rows = [["Fuente", "Documentos publicados"]]
        for row in por_fuente:
            fuente_rows.append(
                [
                    Paragraph(escape(row["source_name"]), _CELL_STYLE),
                    str(row["total"]),
                ]
            )
        fuente_table = Table(fuente_rows, hAlign="LEFT")
        fuente_table.setStyle(_TABLE_STYLE)
        story.append(fuente_table)
    else:
        story.append(Paragraph("Ninguna fuente publicó documentos este mes.", styles["Normal"]))
    fuentes_sin_publicaciones = data.get("fuentes_sin_publicaciones", [])
    if fuentes_sin_publicaciones:
        story.append(Spacer(1, 8))
        nombres = ", ".join(escape(nombre) for nombre in fuentes_sin_publicaciones)
        story.append(Paragraph(f"Fuentes activas sin publicaciones este mes: {nombres}.", styles["Normal"]))
    story.append(Spacer(1, 18))

    # Documentos por fuente y tipo
    story.append(Paragraph("Documentos por fuente y tipo", styles["Heading2"]))
    story.append(Paragraph("Documentos publicados en el mes, por tipo.", styles["Italic"]))
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
        story.append(Paragraph("Ninguna fuente publicó documentos este mes.", styles["Normal"]))
    story.append(Spacer(1, 18))

    # Comparación con el mes anterior
    story.append(Paragraph("Comparación con el mes anterior", styles["Heading2"]))
    comparacion = data.get("comparacion", [])
    if comparacion:
        comparacion_rows = [["Fuente", "Este mes", "Mes anterior", "Variación"]]
        for row in comparacion:
            comparacion_rows.append(
                [
                    Paragraph(escape(row["source_name"]), _CELL_STYLE),
                    str(row["total_actual"]),
                    str(row["total_anterior"]),
                    _variacion_texto(row["variacion_pct"]),
                ]
            )
        comparacion_table = Table(comparacion_rows, hAlign="LEFT")
        comparacion_table.setStyle(_TABLE_STYLE)
        story.append(comparacion_table)
    else:
        story.append(Paragraph("Sin datos suficientes para comparar con el mes anterior.", styles["Normal"]))
    story.append(Spacer(1, 18))

    # Actividad de extracción del mes (aparte — no es la métrica principal del reporte)
    story.append(Paragraph("Actividad de extracción del mes", styles["Heading2"]))
    story.append(
        Paragraph(
            "Esto refleja cuándo se ejecutaron los scrapeos (no la fecha de publicación).",
            styles["Italic"],
        )
    )
    story.append(Spacer(1, 6))
    runs_by_status = data.get("actividad", {}).get("runs_by_status", {})
    errores = data.get("errores", [])
    if not runs_by_status and not errores:
        story.append(Paragraph("Sin actividad de extracción registrada este mes.", styles["Normal"]))
    else:
        if runs_by_status:
            runs_rows = [["Estado", "Corridas"]]
            for run_status, count in sorted(runs_by_status.items()):
                runs_rows.append([run_status, str(count)])
            runs_table = Table(runs_rows, hAlign="LEFT")
            runs_table.setStyle(_TABLE_STYLE)
            story.append(runs_table)
            story.append(Spacer(1, 12))
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

    doc.build(story)
    return buffer.getvalue()
