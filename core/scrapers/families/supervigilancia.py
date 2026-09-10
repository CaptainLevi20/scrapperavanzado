import datetime
import re
import unicodedata
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE = "https://www.supervigilancia.gov.co"
_SOURCE = "Superintendencia de Vigilancia y Seguridad Privada"
_ANIO_MINIMO = 2015
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "es-CO,es;q=0.9"}

# (url de la página 1 del listado, tipo asignado, prefijo de título)
_SECCIONES = [
    (f"{_BASE}/2-1-3-2-resoluciones", "Resolución", "R"),
    (f"{_BASE}/2-1-3-8-conceptos-juridicos", "Concepto", "CTO"),
]
# Sólo Resoluciones pagina; Conceptos es una sola página.
_PAGINA_TOPE = 20

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_ID_RE = re.compile(r"/web/content/(\d+)")
_NUM_CS_ANY = re.compile(r"(\d{6,}CS)", re.I)
_NUM_CS_INICIO = re.compile(r"^\s*(\d{6,}CS)\b", re.I)
_NUM_PROSA = re.compile(r"resoluci[oó]n\s+(?:n[o°º]\.?\s*|n[uú]mero\s*)?(\d{4,})", re.I)
_FECHA_RE = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})\b")
_HOY_RE = re.compile(r"\bhoy\b", re.I)
_PDF_SUFIJO = re.compile(r"\.pdf$", re.I)


def _norm_texto(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "").replace("​", "")
    return re.sub(r"\s+", " ", s).strip()


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title or "")[:120].strip(" .")


def _id_de_href(href: str) -> Optional[str]:
    m = _ID_RE.search(href or "")
    return m.group(1) if m else None


def _num_en_texto(texto: str) -> Optional[str]:
    m = _NUM_CS_ANY.search(texto or "")
    return m.group(1).upper() if m else None


def _num_al_inicio(texto: str) -> Optional[str]:
    m = _NUM_CS_INICIO.match(texto or "")
    return m.group(1).upper() if m else None


def _num_en_prosa(texto: str) -> Optional[str]:
    m = _NUM_PROSA.search(unicodedata.normalize("NFC", texto or ""))
    return m.group(1) if m else None


def _fecha_de_meta(meta: str, hoy: datetime.date) -> Optional[datetime.date]:
    m = _FECHA_RE.search(meta or "")
    if m:
        dd, mm, yyyy = (int(x) for x in m.groups())
        try:
            return datetime.date(yyyy, mm, dd)
        except ValueError:
            return None
    if _HOY_RE.search(meta or ""):
        return hoy
    return None


def _titulo(
    pref: str,
    numero: Optional[str],
    anio: int,
    texto_crudo: str,
    filename_stem: Optional[str],
) -> Tuple[str, bool]:
    if numero:
        return f"{pref}_SVySP_{numero}_{anio}", False
    base = _PDF_SUFIJO.sub("", _norm_texto(texto_crudo))
    if not base and filename_stem:
        base = _PDF_SUFIJO.sub("", _norm_texto(filename_stem))
    return (base or "documento")[:120], True


_FILENAME_RE = re.compile(r'filename="?([^"\r\n;]+)"?', re.I)


def _head_info(session: requests.Session, url: str) -> dict:
    try:
        resp = session.head(url, timeout=30, allow_redirects=True)
    except requests.RequestException:
        return {"filename": None, "content_length": None}
    disp = resp.headers.get("Content-Disposition", "")
    m = _FILENAME_RE.search(disp)
    filename = m.group(1).strip() if m else None
    raw_len = resp.headers.get("Content-Length", "")
    content_length = int(raw_len) if raw_len.isdigit() else None
    return {"filename": filename, "content_length": content_length}
