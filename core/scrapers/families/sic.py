"""Superintendencia de Industria y Comercio (SIC).

Normativa propia de la SIC desde el "Sistema de búsquedas de normas, propio de
la entidad" de su sede electrónica (Drupal). Ver
docs/superpowers/specs/2026-10-07-fuente-sic-design.md.
"""
import re
import unicodedata
from typing import List, NamedTuple, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

_BASE = "https://sedeelectronica.sic.gov.co"
_LISTADO = f"{_BASE}/transparencia/normativa/busqueda-de-normas/entidad"
_SOURCE = "Superintendencia de Industria y Comercio"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

_POR_PAGINA = 20
_PAGINAS_RE = re.compile(r"Mostrando la p\S*gina\s+\d+\s+de\s+(\d+)")


class Ficha(NamedTuple):
    expedicion: Optional[str]
    publicacion: Optional[str]
    pdfs: List[str]


def _espacios(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _filas_listado(html: str) -> List[Tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    filas = []
    for a in soup.select("div.normas--row h2.field__label a[href]"):
        filas.append((a["href"], _espacios(a.get_text(" "))))
    return filas


def _num_paginas(html: str) -> int:
    m = _PAGINAS_RE.search(html)
    if m:
        return int(m.group(1))
    return 1 if _filas_listado(html) else 0


def _fecha_campo(soup: BeautifulSoup, campo: str) -> Optional[str]:
    t = soup.select_one(f".field--name-{campo} time[datetime]")
    if t is None:
        return None
    iso = t["datetime"][:10]
    return iso if re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso) else None


def _ficha(html: str) -> Ficha:
    soup = BeautifulSoup(html, "html.parser")
    pdfs: List[str] = []
    # sólo los adjuntos del campo de archivo: todas las páginas del sitio traen
    # además un enlace global a "Términos y condiciones -Sede Electrónica.pdf"
    for a in soup.select(".field--name-field-archivo a[href]"):
        url = urljoin(_BASE, a["href"])
        if url not in pdfs:
            pdfs.append(url)
    return Ficha(
        expedicion=_fecha_campo(soup, "field-fecha-generacion"),
        publicacion=_fecha_campo(soup, "field-fecha-publicacion"),
        pdfs=pdfs,
    )


_CLAS_RES = "177"
_CLAS_CIR = "179"
_CLAS_TCU = "178"
_CLAS_DOC = "180"

_TIPO_RES = "Resolución"
_TIPO_CIR = "Circular"
_TIPO_TCU = "Título Circular Única"
_TIPO_CTO = "Concepto"
_TIPO_REL = "Relatoría"

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_MAX_TITULO = 120

# Sólo se mira la "cabeza" del título (antes de comillas, coma o " por "): el
# epígrafe de una resolución propia puede citar un ministerio sin ser de él.
_CABEZA_RE = re.compile(r'["“”«»,]| por ')
_OTRA_ENTIDAD_RE = re.compile(r"\b(?:de la|del)\s+(?:comision|ministerio|departamento|agencia|presidencia)\b")

_NUM_RES_RE = re.compile(r"resolucion(?:es)?\s*(?:no\.?|n[°º]\.?|numero)?\s*(\d[\d.]*)")
_NUM_CIR_RE = re.compile(r"circular(?:\s+(?:externa|interna|conjunta))?\s*(?:no\.?|n[°º]\.?|numero)?\s*(\d+)")
_ROMANO_RE = re.compile(r"titulo\s+([ivxlc]+)\b")
_RADICADO_RE = re.compile(r"concepto\s+(?:no\.?\s*)?(\d{2})\s*[- ]\s*(\d+)")


def _norm(s: str) -> str:
    """Minúsculas, sin acentos y con espacios colapsados (incluye &nbsp;)."""
    sin = "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))
    return _espacios(sin).lower()


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:_MAX_TITULO].strip(" .")


def _crudo(titulo_sitio: str) -> str:
    crudo = (titulo_sitio or "").strip()[:_MAX_TITULO].strip(" .")
    return crudo or "documento"


def _de_otra_entidad(t: str) -> bool:
    cabeza = _CABEZA_RE.split(t, maxsplit=1)[0]
    return bool(_OTRA_ENTIDAD_RE.search(cabeza))


def _clasificar(clasif: str, titulo: str) -> Optional[str]:
    t = _norm(titulo)
    if t.startswith("proyecto"):
        return None
    if clasif == _CLAS_RES:
        return None if _de_otra_entidad(t) else _TIPO_RES
    if clasif == _CLAS_CIR:
        return None if _de_otra_entidad(t) else _TIPO_CIR
    if clasif == _CLAS_TCU:
        return _TIPO_RES if t.startswith("resolucion") else _TIPO_TCU
    if clasif == _CLAS_DOC:
        if t.startswith("concepto"):
            return _TIPO_CTO
        if t.startswith("relatoria"):
            return _TIPO_REL
        if t.startswith("resolucion"):
            return _TIPO_RES
        return None
    return None


def _entero(texto: str) -> Optional[int]:
    digitos = texto.replace(".", "")
    return int(digitos) if digitos.isdigit() else None


def _titulo(tipo: str, titulo_sitio: str, expedicion: str) -> Tuple[str, bool]:
    t = _norm(titulo_sitio)
    anio = expedicion[:4]
    if tipo in (_TIPO_RES, _TIPO_REL):
        m = _NUM_RES_RE.search(t)
        n = _entero(m.group(1)) if m else None
        if n is not None:
            pref = "R" if tipo == _TIPO_RES else "REL"
            return f"{pref}_SIC_{n:04d}_{anio}", False
    elif tipo == _TIPO_CIR:
        m = _NUM_CIR_RE.search(t)
        if m:
            return f"C_SIC_{int(m.group(1)):04d}_{anio}", False
    elif tipo == _TIPO_TCU:
        m = _ROMANO_RE.search(t)
        if m:
            return f"TCU_SIC_{m.group(1).upper()}_{expedicion.replace('-', '')}", False
    elif tipo == _TIPO_CTO:
        m = _RADICADO_RE.search(t)
        if m:
            return f"CTO_SIC_{m.group(1)}-{m.group(2)}", False
    return _crudo(titulo_sitio), True
