"""Superintendencia de Industria y Comercio (SIC).

Normativa propia de la SIC desde el "Sistema de búsquedas de normas, propio de
la entidad" de su sede electrónica (Drupal). Ver
docs/superpowers/specs/2026-10-07-fuente-sic-design.md.
"""
import re
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
