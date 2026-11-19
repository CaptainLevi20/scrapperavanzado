"""Limpieza de carpetas temporales que dejaron tareas muertas.

Cada tarea pesada (una fuente dentro de una corrida, una descarga masiva, una
vista previa, el reporte mensual) trabaja en un ``TemporaryDirectory`` que se
borra solo al terminar. Si el proceso muere a la mitad (Docker se cae, el
contenedor se reinicia, el disco se llena) esa carpeta queda para siempre en el
/tmp del contenedor. Pasó en producción el 2026-11-19: la corrida 140 de la CSJ
murió con la caída de Docker y dejó 5,2 GB en ``/tmp/run_source_8558_*``.

Al arrancar el worker se borran las carpetas con esos prefijos que llevan un
buen rato sin cambios. En producción no hay ninguna tarea corriendo en ese
momento dentro del contenedor, así que todas son huérfanas; el margen de edad
es para desarrollo en Windows, donde varios workers pueden compartir la misma
carpeta temporal del sistema y uno no debe borrarle la carpeta al otro.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Prefijos de los TemporaryDirectory que crean worker/tasks.py y core/downloader.py.
PREFIJOS = ("run_source_", "bulk_download_", "preview_", "monthly_report_", "lo_profile_")

# Una tarea viva escribe archivos nuevos continuamente; 6 horas sin ningún
# cambio dentro de la carpeta es señal clara de que nadie la está usando.
EDAD_MINIMA_HORAS = 6.0


def _ultimo_cambio(carpeta: Path) -> float:
    """El mtime más reciente entre la carpeta y todo lo que tiene adentro."""
    ultimo = carpeta.stat().st_mtime
    for ruta in carpeta.rglob("*"):
        try:
            ultimo = max(ultimo, ruta.stat().st_mtime)
        except OSError:
            continue
    return ultimo


def limpiar_temporales_huerfanos(
    directorio: Optional[Path] = None,
    edad_minima_horas: float = EDAD_MINIMA_HORAS,
    ahora: Optional[float] = None,
) -> list[Path]:
    """Borra las carpetas temporales de tareas muertas. Devuelve las borradas."""
    base = Path(directorio) if directorio is not None else Path(tempfile.gettempdir())
    if not base.is_dir():
        return []
    limite = (ahora if ahora is not None else time.time()) - edad_minima_horas * 3600

    borradas: list[Path] = []
    for carpeta in base.iterdir():
        if not carpeta.name.startswith(PREFIJOS) or not carpeta.is_dir() or carpeta.is_symlink():
            continue
        try:
            if _ultimo_cambio(carpeta) > limite:
                continue
            shutil.rmtree(carpeta)
        except OSError as exc:
            logger.warning("No se pudo borrar la carpeta temporal %s: %s", carpeta, exc)
            continue
        borradas.append(carpeta)

    if borradas:
        logger.info(
            "Se borraron %d carpetas temporales de tareas interrumpidas: %s",
            len(borradas),
            ", ".join(p.name for p in borradas),
        )
    return borradas
