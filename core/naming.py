import re
from datetime import date
from pathlib import PurePosixPath
from typing import Dict, List, Optional, Tuple

from core.utils import is_radicado_title, is_samai_case_title, is_sic_canonical_title


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


_ANEXO_SUFFIX_RE = re.compile(r"_A\d{2}$")


def es_anexo_title(title: str) -> bool:
    """True si `title` termina en _A + 2 dígitos (ej. C_SF_0020_2026_A01)."""
    return bool(_ANEXO_SUFFIX_RE.search(title or ""))


def titulo_padre_de_anexo(title: str) -> Optional[str]:
    """Quita el sufijo _A\\d\\d; None si no es anexo."""
    if not es_anexo_title(title):
        return None
    return _ANEXO_SUFFIX_RE.sub("", title)


# Familias cuyo título identifica un proceso (no una providencia puntual): sus
# documentos "tienen actuaciones" y llevan el sufijo de fecha. Cada una trae su
# propio chequeo de "¿este título parece de caso?" — mismo criterio que la
# agrupación en api/routers/documents.py, centralizado aquí para reutilizarlo.
_FAMILIAS_CON_ACTUACIONES = {
    "rama_judicial": is_radicado_title,
    "samai": lambda t: is_samai_case_title(t) or is_radicado_title(t),
    # La SIC publica a veces el mismo acto en varias fichas (archivos distintos):
    # se conservan todas como actuaciones del mismo código.
    "sic": is_sic_canonical_title,
}

# Familias cuyo título ya trae el año: con una sola actuación no se le agrega
# el sufijo "_AAAA" (sólo la fecha completa cuando hay más de una).
_FAMILIAS_SIN_ANIO_SI_UNICA = {"sic"}


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
    anio_si_unica: bool = True,
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
        elif anio_si_unica:
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
        anio_si_unica=family_key not in _FAMILIAS_SIN_ANIO_SI_UNICA,
    )


def nombre_version(document, version, family_key: Optional[str], tiene_actuaciones: bool) -> str:
    es_caso = es_familia_con_actuaciones(family_key, document.title)
    # Una versión archivada solo existe si hubo republicación, así que el total
    # (el version_no del documento vigente) siempre es > 1 y el sufijo aparece.
    return construir_nombre(
        document.title, _fecha_para_nombre(document), es_caso, tiene_actuaciones,
        version_no=version.version_no, total_versiones=document.version_no,
        anio_si_unica=family_key not in _FAMILIAS_SIN_ANIO_SI_UNICA,
    )


def _con_extension(nombre: str, storage_key: str) -> str:
    ext = PurePosixPath(storage_key).suffix
    return f"{nombre}{ext}" if ext else nombre


def nombre_archivo_documento(document, family_key: Optional[str], tiene_actuaciones: bool) -> str:
    return _con_extension(nombre_documento(document, family_key, tiene_actuaciones), document.storage_key)


def nombre_archivo_version(document, version, family_key: Optional[str], tiene_actuaciones: bool) -> str:
    return _con_extension(nombre_version(document, version, family_key, tiene_actuaciones), version.storage_key)


def con_sufijos(pares: List[Tuple[str, int]]) -> List[str]:
    """Distingue títulos repetidos dentro de una fuente (p. ej. dependencias
    que numeran por su cuenta, o el mismo número en series distintas): dentro
    de cada grupo de títulos iguales, el de menor id interno del sitio queda
    limpio y los siguientes llevan _2, _3… en orden de id. Quien la llama
    debe pasarle el conjunto COMPLETO de documentos que comparte numeración
    (el año o la lista entera), no solo los del rango de la corrida, para que
    el título de un documento no dependa de ese rango."""
    por_titulo: Dict[str, List[int]] = {}
    for i, (titulo, _) in enumerate(pares):
        por_titulo.setdefault(titulo, []).append(i)
    salida = [titulo for titulo, _ in pares]
    for titulo, indices in por_titulo.items():
        if len(indices) < 2:
            continue
        orden = sorted(indices, key=lambda i: (pares[i][1], i))
        for k, i in enumerate(orden[1:], start=2):
            salida[i] = f"{titulo}_{k}"
    return salida
