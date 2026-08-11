from datetime import date
from pathlib import PurePosixPath
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


def _fecha_para_nombre(document):
    # f_providencia manda; si no está, se usa f_public como respaldo (solo
    # relevante para familias con actuaciones, ver es_familia_con_actuaciones).
    return document.f_providencia or document.f_public


def nombre_documento(document, family_key: Optional[str]) -> str:
    es_caso = es_familia_con_actuaciones(family_key, document.title)
    # El documento vigente siempre lleva el número de versión más alto, así que
    # total_versiones == version_no y el sufijo aparece cuando version_no > 1.
    return construir_nombre(
        document.title, _fecha_para_nombre(document), es_caso,
        version_no=document.version_no, total_versiones=document.version_no,
    )


def nombre_version(document, version, family_key: Optional[str]) -> str:
    es_caso = es_familia_con_actuaciones(family_key, document.title)
    # Una versión archivada solo existe si hubo republicación, así que el total
    # (el version_no del documento vigente) siempre es > 1 y el sufijo aparece.
    return construir_nombre(
        document.title, _fecha_para_nombre(document), es_caso,
        version_no=version.version_no, total_versiones=document.version_no,
    )


def _con_extension(nombre: str, storage_key: str) -> str:
    ext = PurePosixPath(storage_key).suffix
    return f"{nombre}{ext}" if ext else nombre


def nombre_archivo_documento(document, family_key: Optional[str]) -> str:
    return _con_extension(nombre_documento(document, family_key), document.storage_key)


def nombre_archivo_version(document, version, family_key: Optional[str]) -> str:
    return _con_extension(nombre_version(document, version, family_key), version.storage_key)
