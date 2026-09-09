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

_BASE = "https://www.supersolidaria.gov.co"
_SOURCE = "Superintendencia de la Economía Solidaria"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
_ANIO_MIN = 2015

_URL_CONCEPTOS = f"{_BASE}/es/conceptos-juridicos-y-contables"

# (url, tipo mostrado, prefijo de título, fecha_por_prosa)
_SECCIONES_TABLA = [
    (f"{_BASE}/es/content/resoluciones-generales", "Resolución", "R", True),
    (f"{_BASE}/es/content/circulares-externas-por-ano", "Circular Externa", "CE", False),
    (f"{_BASE}/es/content/circulares-conjuntas", "Circular Conjunta", "CJ", False),
    (f"{_BASE}/es/content/cartas-circulares", "Carta Circular", "CC", False),
]

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_H2_ANIO_RE = re.compile(
    r"(?i)(?:resoluciones\s+generales|circulares\s+externas|cartas\s+circulares)\s*(20\d{2})\b"
)
_FECHA_ARCHIVO_RE = re.compile(r"/(\d{4})(\d{2})(\d{2})_[^/]+$")
_RADICADO_RE = re.compile(r"\b(\d{7,})\b")
_NUM_MARCADO_RE = re.compile(r"(?:N[°º]|No\.?)\s*0*(\d+)", re.IGNORECASE)
_ENTERO_SUELTO_RE = re.compile(r"\b0*(\d{1,6})\b")
_ANEXO_RE = re.compile(r"^(anexo|matriz de)\b")


def _sin_acentos(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)
    )


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _extension_del_href(href: str) -> str:
    ruta = (href or "").split("?")[0].split("#")[0]
    m = re.search(r"\.([A-Za-z0-9]{1,5})$", ruta)
    return m.group(1).lower() if m else ""


def _es_anexo(titulo: str) -> bool:
    return bool(_ANEXO_RE.match(_sin_acentos(titulo or "").strip().lower()))


def _num_seccion(prefijo: str, titulo: str) -> Optional[int]:
    t = titulo or ""
    if prefijo == "R":
        m = _RADICADO_RE.search(t)
        if m:
            d = m.group(1)
            return int(d[-6:]) if len(d) >= 7 else int(d)
        m = _ENTERO_SUELTO_RE.search(t)
        return int(m.group(1)) if m else None
    m = _NUM_MARCADO_RE.search(t)
    if m:
        return int(m.group(1))
    return None


def _anio_de_h2(texto: str) -> Optional[int]:
    m = _H2_ANIO_RE.search(_sin_acentos(texto or ""))
    return int(m.group(1)) if m else None


def _prefijo_fecha_archivo(href: str) -> Optional[str]:
    m = _FECHA_ARCHIVO_RE.search((href or "").split("?")[0])
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    try:
        return datetime.date(y, mo, d).isoformat()
    except ValueError:
        return None


def _iso_de_time(time_iso: Optional[str]) -> Optional[str]:
    if not time_iso:
        return None
    try:
        return datetime.date.fromisoformat(time_iso[:10]).isoformat()
    except ValueError:
        return None


def _fecha_concepto(href: str, time_iso: Optional[str]) -> Optional[str]:
    return _prefijo_fecha_archivo(href) or _iso_de_time(time_iso)


def _titulo(prefijo: str, tipo: str, titulo_crudo: str, anio: str, es_anexo: bool) -> Tuple[str, bool]:
    numero = _num_seccion(prefijo, titulo_crudo)
    if numero is None:
        return ((titulo_crudo or "").strip() or "documento")[:120].strip(" .") or "documento", True
    base = f"{prefijo}_SES_{numero:04d}_{anio}"
    if es_anexo:
        base = f"{base}_A01"
    return base, False


def _titulo_concepto(href: str, titulo_fila: str, anio: str) -> Tuple[str, bool]:
    nombre = (href or "").split("/")[-1].split("?")[0]
    m = re.search(r"_(\d{10,})\.pdf$", nombre, re.IGNORECASE)
    if m:
        return f"CTO_SES_{m.group(1)}_{anio}", False
    return ((titulo_fila or "").strip() or "documento")[:120].strip(" .") or "documento", True
