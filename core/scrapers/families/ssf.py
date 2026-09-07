import datetime
import re
import unicodedata
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.fecha_es import parse_fecha_providencia_es
from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE = "https://www.ssf.gov.co"
_SOURCE = "Superintendencia del Subsidio Familiar"
_ANIO_MIN = 2024
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# (url, tipo mostrado, letra del código, columnas esperadas del encabezado en
# minúsculas y sin acentos)
_SECCIONES = [
    (f"{_BASE}/web/guest/resoluciones2", "Resolución", "R", {"documento", "asunto", "enlace"}),
    (f"{_BASE}/web/guest/normativa-circulares", "Circular Externa", "C", {"numero", "fecha", "asunto", "adjunto"}),
]

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_NUM_RES_ASUNTO = re.compile(r"resoluci[oó]n\s+(\d+)", re.I)
_NUM_RES_DOC = re.compile(r"(?:RES\.?|RESOLUCI[ÓO]N)\s*(\d+)", re.I)
_FECHA_CORTA = re.compile(r"(\d{1,2})-(\d{1,2})-(\d{2})\b")
_FECHA_SLASH = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})\b")
_NUM_CIRCULAR = re.compile(r"^\s*(?:CE\s*)?0*(\d+)\s*([A-Za-z]?)", re.I)


def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _fecha_corta(texto: str) -> Optional[datetime.date]:
    m = _FECHA_CORTA.search(texto or "")
    if not m:
        return None
    dd, mm, yy = (int(x) for x in m.groups())
    try:
        return datetime.date(2000 + yy, mm, dd)
    except ValueError:
        return None


def _fecha_slash(texto: str) -> Optional[datetime.date]:
    m = _FECHA_SLASH.search(texto or "")
    if not m:
        return None
    dd, mm, yyyy = (int(x) for x in m.groups())
    try:
        return datetime.date(yyyy, mm, dd)
    except ValueError:
        return None


def _num_circular(celda: str) -> Optional[Tuple[str, str]]:
    m = _NUM_CIRCULAR.match(celda or "")
    if not m:
        return None
    return m.group(1), m.group(2).upper()


def _num_resolucion(asunto: str, documento: str) -> Optional[str]:
    m = _NUM_RES_ASUNTO.search(asunto or "")
    if m:
        return m.group(1)
    m = _NUM_RES_DOC.search(documento or "")
    return m.group(1) if m else None


def _titulo(letra: str, digitos: Optional[str], sufijo: str, anio: int, texto_crudo: str) -> Tuple[str, bool]:
    if digitos:
        return f"{letra}_SSF_{int(digitos):04d}{sufijo}_{anio}", False
    return ((texto_crudo or "").strip() or "documento")[:120], True
