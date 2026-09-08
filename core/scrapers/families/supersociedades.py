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

_BASE = "https://www.supersociedades.gov.co"
_SOURCE = "Superintendencia de Sociedades"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

_MESES = {
    "enero": "ENE", "febrero": "FEB", "marzo": "MAR", "abril": "ABR",
    "mayo": "MAY", "junio": "JUN", "julio": "JUL", "agosto": "AGO",
    "septiembre": "SEP", "setiembre": "SEP", "octubre": "OCT",
    "noviembre": "NOV", "diciembre": "DIC",
}
# sigla -> número de mes (para clasificar semestre y para la fecha del jurídico)
_MES_NUM = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_ANIO_RE = re.compile(r"\b(20\d{2})\b")
# "semestre i" | "semestre ii" | "semestre 1" | "semestre 2" (tras normalizar)
_SEMESTRE_RE = re.compile(r"semestre\s+(ii|i|2|1)\b")


def _sin_acentos(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)
    )


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _mes_a_sigla(texto: str) -> Optional[str]:
    t = _sin_acentos(texto or "").lower()
    # el primero que aparezca por posición en el texto
    encontrados = [(t.find(nombre), sigla) for nombre, sigla in _MESES.items() if nombre in t]
    if not encontrados:
        return None
    return min(encontrados)[1]


def _anio(texto: str) -> Optional[int]:
    m = _ANIO_RE.search(texto or "")
    if not m:
        return None
    n = int(m.group(1))
    return n if 2000 <= n <= 2100 else None


def _periodo_juridico(titulo: str) -> Optional[Tuple[str, int]]:
    mes = _mes_a_sigla(titulo)
    anio = _anio(titulo)
    if mes is None or anio is None:
        return None
    return mes, anio


def _periodo_contable(titulo: str) -> Optional[Tuple[str, int]]:
    anio = _anio(titulo)
    if anio is None:
        return None
    t = _sin_acentos(titulo or "").lower()
    m = _SEMESTRE_RE.search(t)
    if m:
        sem = "SII" if m.group(1) in ("ii", "2") else "SI"
        return sem, anio
    mes = _mes_a_sigla(titulo)
    if mes is not None:
        return ("SI" if _MES_NUM[mes] <= 6 else "SII"), anio
    return None


def _fecha_de_periodo(tipo: str, periodo: Tuple[str, int]) -> Optional[str]:
    clave, anio = periodo
    if tipo == "Boletín Jurídico":
        num = _MES_NUM.get(clave)
        return f"{anio:04d}-{num:02d}-01" if num else None
    if tipo == "Boletín Contable":
        if clave == "SI":
            return f"{anio:04d}-06-30"
        if clave == "SII":
            return f"{anio:04d}-12-31"
    return None


def _titulo(tipo: str, periodo: Optional[Tuple[str, int]], titulo_crudo: str) -> Tuple[str, bool]:
    if periodo is not None:
        clave, anio = periodo
        return f"BOL_SS_{clave}_{anio}", False
    return ((titulo_crudo or "").strip() or "documento")[:120].strip(" ."), True


_PDF_RE = re.compile(r"/documents/\d+/\d+/[^\"']*bolet[ií]n[^\"']*\.pdf[^\"']*", re.IGNORECASE)


def _items_de_lista(html: str, link_class: str) -> List[Tuple[str, str]]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: List[Tuple[str, str]] = []
    for a in soup.find_all("a", class_=link_class, href=True):
        titulo = (a.get("title") or a.get_text(" ", strip=True) or "").strip()
        href = a["href"].strip()
        if titulo and href:
            out.append((titulo, href))
    return out


def _pdf_del_articulo(html: str) -> Optional[str]:
    for a in BeautifulSoup(html or "", "html.parser").find_all("a", href=True):
        href = a["href"].strip()
        if _PDF_RE.search(_sin_acentos(href)):
            return href
    return None
