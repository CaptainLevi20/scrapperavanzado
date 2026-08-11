from datetime import date
from typing import Optional

from core.utils import is_radicado_title, is_samai_case_title

# Familias cuyo título identifica un proceso (no una providencia puntual): sus
# documentos "tienen actuaciones" y llevan el sufijo de fecha. Cada una trae su
# propio chequeo de "¿este título parece de caso?" — mismo criterio que la
# agrupación en api/routers/documents.py, centralizado aquí para reutilizarlo.
_FAMILIAS_CON_ACTUACIONES = {
    "rama_judicial": is_radicado_title,
    "samai": lambda t: is_samai_case_title(t) or is_radicado_title(t),
}


def es_familia_con_actuaciones(family_key: Optional[str], title: str) -> bool:
    check = _FAMILIAS_CON_ACTUACIONES.get(family_key or "")
    return bool(check and check(title))


def construir_nombre(
    base: str,
    fecha: Optional[date],
    es_caso: bool,
    version_no: int,
    total_versiones: int,
) -> str:
    """Arma el nombre canónico: base, luego fecha de providencia (AAAAMMDD) solo
    si el documento tiene actuaciones y hay una fecha, luego "_v{n}" solo si hay
    más de una versión. No incluye la extensión del archivo."""
    nombre = base
    if es_caso and fecha is not None:
        nombre = f"{nombre}_{fecha.strftime('%Y%m%d')}"
    if total_versiones > 1:
        nombre = f"{nombre}_v{version_no}"
    return nombre
