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


def _tablas_de_datos(soup, columnas):
    out = []
    for t in soup.find_all("table"):
        filas = t.find_all("tr")
        if not filas:
            continue
        encabezado = {
            _sin_acentos(c.get_text(" ", strip=True)).lower()
            for c in filas[0].find_all(["th", "td"])
        }
        if columnas.issubset(encabezado):
            out.append(t)
    return out


def _celdas_texto(tr):
    return [td.get_text(" ", strip=True) for td in tr.find_all("td")]


def _href_de_fila(tr):
    for a in tr.find_all("a", href=True):
        href = a["href"].strip()
        if href and not href.lower().startswith("javascript"):
            return href
    return None


def _armar_doc(tipo, letra, digitos, sufijo, fecha, fini, ffin, asunto, texto_crudo, href) -> Optional[RawDocModel]:
    if fecha.year < _ANIO_MIN:
        return None
    iso = fecha.isoformat()
    if iso < fini or iso > ffin:
        return None
    title, unverified = _titulo(letra, digitos, sufijo, fecha.year, texto_crudo)
    safe = _safe_title(title)
    return RawDocModel(
        source=_SOURCE,
        link={"url": urljoin(_BASE, href), "method": "GET"},
        title=title,
        tipo=tipo,
        f_public=iso,
        f_providencia=iso,
        detalle=(asunto or "").strip() or None,
        save_path=storage_path(_SOURCE, iso, tipo, f"{safe}(extension)"),
        title_unverified=unverified,
    )


def _fila_resolucion(tr, fini, ffin, on_progress) -> Optional[RawDocModel]:
    tds = _celdas_texto(tr)
    if len(tds) < 2:
        return None
    documento, asunto = tds[0], tds[1]
    href = _href_de_fila(tr)
    if not href:
        return None
    fecha = parse_fecha_providencia_es(asunto) or _fecha_corta(documento)
    if fecha is None:
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: resolución sin fecha parseable «{documento[:70]}», se omite")
        return None
    numero = _num_resolucion(asunto, documento)
    return _armar_doc("Resolución", "R", numero, "", fecha, fini, ffin, asunto, documento or asunto, href)


def _fila_circular(tr, fini, ffin, on_progress) -> Optional[RawDocModel]:
    tds = _celdas_texto(tr)
    if len(tds) < 4:
        return None
    celda_num, celda_fecha, asunto = tds[0], tds[1], tds[2]
    href = _href_de_fila(tr)
    if not href:
        return None
    fecha = _fecha_slash(celda_fecha)
    if fecha is None:
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: circular sin fecha parseable «{celda_num[:40]}», se omite")
        return None
    parsed = _num_circular(celda_num)
    digitos, sufijo = parsed if parsed else (None, "")
    return _armar_doc("Circular Externa", "C", digitos, sufijo, fecha, fini, ffin, asunto, celda_num or asunto, href)
