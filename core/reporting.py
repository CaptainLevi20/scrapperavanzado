from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from core.db import repository

_MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

_MENSAJE_MAX_LEN = 300


def _bounds(period: date) -> tuple[datetime, datetime]:
    # Límites del mes en UTC: una corrida en las últimas ~5h del mes en hora
    # de Colombia (UTC-5) cuenta en el mes siguiente. Los scrapes programados
    # corren 06:00 COT, así que solo corridas manuales cerca de medianoche podrían desplazarse.
    start = datetime(period.year, period.month, 1, tzinfo=timezone.utc)
    if period.month == 12:
        end = datetime(period.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(period.year, period.month + 1, 1, tzinfo=timezone.utc)
    return start, end


def _date_bounds(period: date) -> tuple[date, date]:
    """Límites del mes como fechas (no datetimes), para comparar contra
    documents.f_public (columna Date). Medio-abierto [start, end)."""
    if period.month == 12:
        end = date(period.year + 1, 1, 1)
    else:
        end = date(period.year, period.month + 1, 1)
    return period, end


def _now() -> datetime:
    return datetime.now(timezone.utc)


def previous_period(period: date) -> date:
    if period.month == 1:
        return date(period.year - 1, 12, 1)
    return date(period.year, period.month - 1, 1)


def period_label(period: date) -> str:
    return f"{_MESES_ES[period.month].capitalize()} {period.year}"


def _variacion_pct(actual: int, anterior: int) -> Optional[float]:
    if anterior == 0:
        return None
    return round((actual - anterior) / anterior * 100, 1)


def _build_documentos_por_tipo(db: Session, period_start: date, period_end: date) -> list[dict]:
    rows = repository.summarize_documents_by_source_and_tipo_for_period(db, period_start, period_end)

    por_fuente: dict[str, list[dict]] = {}
    for row in rows:
        tipo_label = row["tipo"] if row["tipo"] is not None else "Sin tipo"
        por_fuente.setdefault(row["source_name"], []).append({"tipo": tipo_label, "count": row["count"]})

    documentos_por_tipo = []
    for source_name, tipos in por_fuente.items():
        tipos_ordenados = sorted(tipos, key=lambda t: t["count"], reverse=True)
        documentos_por_tipo.append(
            {
                "source_name": source_name,
                "total": sum(t["count"] for t in tipos_ordenados),
                "tipos": tipos_ordenados,
            }
        )
    return documentos_por_tipo


def build_monthly_report_data(db: Session, period: date) -> dict:
    # Actividad de extracción (corridas/errores) sigue midiéndose por Run.started_at,
    # en UTC datetimes — es un aparte, no la métrica principal del reporte.
    period_start_dt, period_end_dt = _bounds(period)
    # Todo lo demás cuenta por fecha de PUBLICACIÓN (documents.f_public, columna Date).
    date_start, date_end = _date_bounds(period)
    prev_date_start, prev_date_end = _date_bounds(previous_period(period))

    por_fuente = repository.summarize_documents_by_source_for_period(db, date_start, date_end)
    por_fuente_anterior = repository.summarize_documents_by_source_for_period(db, prev_date_start, prev_date_end)
    total_anterior_by_source = {row["source_id"]: row["total"] for row in por_fuente_anterior}

    comparacion = []
    for row in por_fuente:
        actual = row["total"]
        anterior = total_anterior_by_source.get(row["source_id"], 0)
        if actual == 0 and anterior == 0:
            continue
        comparacion.append(
            {
                "source_name": row["source_name"],
                "total_actual": actual,
                "total_anterior": anterior,
                "variacion_pct": _variacion_pct(actual, anterior),
            }
        )

    errores = repository.list_run_errors_for_period(db, period_start_dt, period_end_dt)
    for error in errores:
        if len(error["message"]) > _MENSAJE_MAX_LEN:
            error["message"] = error["message"][:_MENSAJE_MAX_LEN] + "…"

    resumen = {
        "total_documentos": repository.count_documents_for_period(db, date_start, date_end),
        "storage_bytes": repository.sum_document_storage_for_period(db, date_start, date_end),
        "num_fuentes": len(por_fuente),
    }

    now = _now()
    is_partial = period_end_dt > now
    as_of_label = (
        f"datos hasta el {now.day} de {_MESES_ES[now.month]} de {now.year}" if is_partial else None
    )

    return {
        "period": period,
        "period_label": period_label(period),
        "is_partial": is_partial,
        "as_of_label": as_of_label,
        "resumen": resumen,
        "por_fuente": por_fuente,
        "fuentes_sin_publicaciones": repository.list_active_sources_without_publications_in_period(db, date_start, date_end),
        "documentos_por_tipo": _build_documentos_por_tipo(db, date_start, date_end),
        "comparacion": comparacion,
        "actividad": {
            "runs_by_status": repository.count_runs_by_status_for_period(db, period_start_dt, period_end_dt),
        },
        "errores": errores,
    }
