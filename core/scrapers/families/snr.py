import datetime
import re
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.fecha_es import parse_fecha_providencia_es
from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE = "https://www.supernotariado.gov.co/transparencia/normatividad"
_SOURCE = "Superintendencia de Notariado y Registro"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_UMBRAL = 18
_ANIO_MIN = 2015

# (segmento de URL de la categoría, tipo mostrado, letra del código de título)
_CATEGORIAS = [
    ("circulares", "Circular", "C"),
    ("Resoluciones", "Resolución", "R"),
]

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_CODIGO_RE = re.compile(r"\b(CIR|RES)-(\d{4})-(\d{6})-\d\b")
_RESULTADOS_RE = re.compile(r"Resultados\s*([\d.,]+)")
_PUB_RE = re.compile(r"Publicaci[oó]n:\s*(\d{4}-\d{2}-\d{2})")


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _parse_codigo(texto: str) -> Optional[Tuple[str, int, int]]:
    m = _CODIGO_RE.search(texto or "")
    if not m:
        return None
    letra = "C" if m.group(1) == "CIR" else "R"
    return letra, int(m.group(3)), int(m.group(2))


def _titulo(codigo: Optional[Tuple[str, int, int]], texto_crudo: str) -> Tuple[str, bool]:
    if codigo is None:
        return ((texto_crudo or "").strip() or "documento")[:120], True
    letra, numero, anio = codigo
    return f"{letra}_SNR_{numero:04d}_{anio}", False


def _resultados_total(html: str) -> int:
    m = _RESULTADOS_RE.search(html or "")
    if not m:
        return -1
    return int(m.group(1).replace(".", "").replace(",", ""))
