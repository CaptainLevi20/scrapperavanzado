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


def build_monthly_report_data(db: Session, period: date) -> dict:
    period_start, period_end = _bounds(period)
    prev_start, prev_end = _bounds(previous_period(period))

    por_fuente = repository.summarize_run_sources_for_period(db, period_start, period_end)
    por_fuente_anterior = repository.summarize_run_sources_for_period(db, prev_start, prev_end)
    docs_new_anterior_by_source = {row["source_id"]: row["docs_new"] for row in por_fuente_anterior}

    comparacion = []
    for row in por_fuente:
        actual = row["docs_new"]
        anterior = docs_new_anterior_by_source.get(row["source_id"], 0)
        if actual == 0 and anterior == 0:
            continue
        comparacion.append(
            {
                "source_name": row["source_name"],
                "docs_new_actual": actual,
                "docs_new_anterior": anterior,
                "variacion_pct": _variacion_pct(actual, anterior),
            }
        )

    errores = repository.list_run_errors_for_period(db, period_start, period_end)
    for error in errores:
        if len(error["message"]) > _MENSAJE_MAX_LEN:
            error["message"] = error["message"][:_MENSAJE_MAX_LEN] + "…"

    resumen = {
        "docs_new": sum(row["docs_new"] for row in por_fuente),
        "docs_updated": sum(row["docs_updated"] for row in por_fuente),
        "docs_errors": sum(row["docs_errors"] for row in por_fuente),
        "runs_by_status": repository.count_runs_by_status_for_period(db, period_start, period_end),
        "storage_bytes": repository.sum_document_storage_for_period(db, period_start, period_end),
    }

    return {
        "period": period,
        "period_label": period_label(period),
        "resumen": resumen,
        "por_fuente": por_fuente,
        "fuentes_sin_actividad": repository.list_active_sources_without_activity_in_period(db, period_start, period_end),
        "errores": errores,
        "comparacion": comparacion,
    }
