import re
from datetime import date
from pathlib import PurePosixPath
from typing import Optional

from core.utils import is_radicado_title, is_samai_case_title


def codigo_ley_decreto(letra: str, numero: str, anio: str) -> Optional[str]:
    """Código canónico SIN sigla de ministerio para Leyes y Decretos, común a
    todas las fuentes de normatividad: "<L|D>" + número (4 dígitos, ceros a la
    izquierda) + año, sin separadores. El año va en 3 dígitos (año % 1000)
    salvo 1900-1999, que van en 2 (año % 100): 2022 -> "022", 1901 -> "01",
    1888 -> "888". Devuelve None para cualquier otro `letra` (R, C, A, LEST…),
    que conserva el formato con sigla.

    Ej.: ("L", "2277", "2022") -> "L2277022"; ("D", "111", "1996") -> "D011196"."""
    if letra not in ("L", "D"):
        return None
    y = int(anio)
    anio_str = f"{y % 100:02d}" if 1900 <= y <= 1999 else f"{y % 1000:03d}"
    return f"{letra}{int(numero):04d}{anio_str}"


# "<L|D>" + al menos 4 dígitos de número + 2 o 3 de año = 6+ dígitos en total.
_CODIGO_LEY_DECRETO_RE = re.compile(r"^[LD]\d{6,}$")


def es_codigo_ley_decreto(titulo: str) -> bool:
    """True si `titulo` ya tiene la forma del código canónico de ley/decreto
    (para deduplicar entre fuentes en el worker)."""
    return bool(_CODIGO_LEY_DECRETO_RE.match(titulo or ""))

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
    tiene_actuaciones: bool,
    version_no: int,
    total_versiones: int,
) -> str:
    """Arma el nombre canónico: base, luego la fecha de providencia solo si el
    título tiene forma de caso y hay una fecha — con el día completo (AAAAMMDD)
    cuando el documento ya tiene más de una actuación registrada (para poder
    distinguirlas), o solo el año cuando todavía no tiene ninguna otra
    actuación (nada que distinguir todavía, pero igual se muestra el año) —,
    y luego "-v{n}" solo si hay más de una versión. No incluye la extensión
    del archivo."""
    nombre = base
    if es_caso and fecha is not None:
        if tiene_actuaciones:
            nombre = f"{nombre}_{fecha.strftime('%Y%m%d')}"
        else:
            nombre = f"{nombre}_{fecha.strftime('%Y')}"
    if total_versiones > 1:
        nombre = f"{nombre}-v{version_no}"
    return nombre


def _fecha_para_nombre(document):
    # f_providencia manda; si no está, se usa f_public como respaldo (solo
    # relevante para familias con actuaciones, ver es_familia_con_actuaciones).
    return document.f_providencia or document.f_public


def nombre_documento(document, family_key: Optional[str], tiene_actuaciones: bool) -> str:
    es_caso = es_familia_con_actuaciones(family_key, document.title)
    # El documento vigente siempre lleva el número de versión más alto, así que
    # total_versiones == version_no y el sufijo aparece cuando version_no > 1.
    return construir_nombre(
        document.title, _fecha_para_nombre(document), es_caso, tiene_actuaciones,
        version_no=document.version_no, total_versiones=document.version_no,
    )


def nombre_version(document, version, family_key: Optional[str], tiene_actuaciones: bool) -> str:
    es_caso = es_familia_con_actuaciones(family_key, document.title)
    # Una versión archivada solo existe si hubo republicación, así que el total
    # (el version_no del documento vigente) siempre es > 1 y el sufijo aparece.
    return construir_nombre(
        document.title, _fecha_para_nombre(document), es_caso, tiene_actuaciones,
        version_no=version.version_no, total_versiones=document.version_no,
    )


def _con_extension(nombre: str, storage_key: str) -> str:
    ext = PurePosixPath(storage_key).suffix
    return f"{nombre}{ext}" if ext else nombre


def nombre_archivo_documento(document, family_key: Optional[str], tiene_actuaciones: bool) -> str:
    return _con_extension(nombre_documento(document, family_key, tiene_actuaciones), document.storage_key)


def nombre_archivo_version(document, version, family_key: Optional[str], tiene_actuaciones: bool) -> str:
    return _con_extension(nombre_version(document, version, family_key, tiene_actuaciones), version.storage_key)
