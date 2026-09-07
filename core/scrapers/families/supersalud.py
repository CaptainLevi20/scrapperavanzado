import datetime
import re
import unicodedata
from typing import List, Optional, Tuple

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE = "https://www.supersalud.gov.co/es-co"
_CONTEXTINFO = f"{_BASE}/_api/contextinfo"
_PROCESS_QUERY = f"{_BASE}/_vti_bin/client.svc/ProcessQuery"
_DOCS_PREFIX = "https://docs.supersalud.gov.co/PortalWeb/Juridica"

# (carpeta en docs.supersalud, tipo mostrado, letra del código de título)
_CATEGORIAS = [
    ("Resoluciones", "Resolución", "R"),
    ("CircularesExterna", "Circular Externa", "C"),
]

_ANIO_MINIMO = 2015
_PAGE = 500

_SOURCE = "Superintendencia Nacional de Salud"

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
# año (4) + bloque de 12 dígitos (dependencia 6 + consecutivo 6) + sufijo "-D" o "D"
_RADICADO_RE = re.compile(r"(\d{4})(\d{12})-?\d?\b")
_CLASICO_RE = re.compile(r"^0*(\d{1,5})$")
_SUFIJO_ANIO_RE = re.compile(r"\s+de\s+\d{4}\s*$", re.IGNORECASE)
_ANEXO_PREFIJO_RE = re.compile(r"^anexo\s+", re.IGNORECASE)


def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def _es_anexo(title: Optional[str]) -> bool:
    return _sin_acentos((title or "").strip()).lower().startswith("anexo")


def _parse_numero(numero_raw: Optional[str], title: Optional[str]) -> Optional[int]:
    base = (numero_raw or "").strip() or (title or "").strip()
    if not base:
        return None
    base = _sin_acentos(base)
    base = _ANEXO_PREFIJO_RE.sub("", base)
    base = re.sub(r"\s+", " ", base).strip()
    base = _SUFIJO_ANIO_RE.sub("", base).strip()

    m = _RADICADO_RE.search(base)
    if m:
        return int(m.group(2)[-6:])

    # For classic form, find all digit sequences in the text
    numbers = re.findall(r"\d+", base)
    if len(numbers) == 1 and _CLASICO_RE.match(numbers[0]):
        return int(numbers[0])

    return None


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _titulo(
    letra: str, numero_raw: Optional[str], title_raw: str, anio: str, es_anexo: bool
) -> Tuple[str, bool]:
    numero = _parse_numero(numero_raw, title_raw)
    if numero is None:
        return (title_raw or "").strip()[:120], True
    base = f"{letra}_SNS_{numero:04d}_{anio}"
    if es_anexo:
        base = f"{base}_A01"
    return base, False


def _fecha_publicacion(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    candidato = raw.split("\n")[0].strip()[:10]
    try:
        datetime.date.fromisoformat(candidato)
    except ValueError:
        return None
    return candidato


def _fila_a_doc(fila, tipo, letra, fini, ffin, on_progress) -> Optional[RawDocModel]:
    url = (fila.get("Path") or "").strip()
    if not url:
        return None

    f_public = _fecha_publicacion(fila.get("FechadePublicacionOWSDATE"))
    title_raw = (fila.get("Title") or "").strip()
    if f_public is None:
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: fila sin fecha de publicación parseable «{title_raw[:80]}», se omite")
        return None
    if f_public < fini or f_public > ffin:
        return None

    es_anexo = _es_anexo(title_raw)
    title, unverified = _titulo(
        letra, fila.get("NumeroOWSTEXT"), title_raw, f_public[:4], es_anexo
    )
    safe = _safe_title(title)
    return RawDocModel(
        source=_SOURCE,
        link={"url": url, "method": "GET"},
        title=title,
        tipo=tipo,
        f_public=f_public,
        f_providencia=f_public,
        detalle=(fila.get("DescripcionOWSMTXT") or "").strip() or None,
        save_path=storage_path(_SOURCE, f_public, tipo, f"{safe}(extension)"),
        title_unverified=unverified,
    )
