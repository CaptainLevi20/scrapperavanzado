"""Superintendencia de Industria y Comercio (SIC).

Normativa propia de la SIC desde el "Sistema de búsquedas de normas, propio de
la entidad" de su sede electrónica (Drupal). Ver
docs/superpowers/specs/2026-10-07-fuente-sic-design.md.
"""
import re
import unicodedata
from typing import Dict, List, NamedTuple, Optional, Tuple
from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

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

# "re?s?olucion": el sitio trae erratas reales ("Reolución 56937 de 2025")
_NUM_RES_RE = re.compile(r"re?s?olucion(?:es)?\s*(?:no\.?|n[°º]\.?|numero)?\s*(\d[\d.]*)")
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


# Consultas de listado (páginas + fragmentos) permitidas en una corrida. Una
# carga 2015→hoy completa gasta del orden de 1.000 por año grande.
_MAX_BUSQUEDAS = 4000
_MAX_LARGO_FRAGMENTO = 6
_DIGITOS = "0123456789"


class _PresupuestoAgotado(Exception):
    pass


def _enumerar_tajada(session, clasif: str, anio: int, presupuesto: List[int],
                     stop_event, on_progress) -> Dict[str, str]:
    """Todas las fichas de una clasificación publicadas en `anio`.

    El buscador reordena al azar las filas con igual fecha de publicación en
    cada petición, así que recorrer las páginas repite unas y pierde otras. Se
    conoce el total exacto (la última página dice cuántas filas quedan), y se
    completa con búsquedas `combine` por fragmentos de dígitos: un fragmento
    que cabe en una página no sufre el reordenamiento. Se para apenas se
    alcanza el total.
    """
    base = {"field_clasificacion2_target_id": clasif, "field_fecha_publicacion_value": str(anio)}
    por_href: Dict[str, str] = {}

    def parar() -> bool:
        return stop_event is not None and stop_event.is_set()

    def consultar(extra: dict) -> Tuple[int, List[Tuple[str, str]]]:
        if presupuesto[0] <= 0:
            raise _PresupuestoAgotado
        presupuesto[0] -= 1
        try:
            resp = session.get(_LISTADO, params={**base, **extra}, timeout=90)
            resp.raise_for_status()
        except Exception as e:
            if on_progress:
                on_progress(f"[{_SOURCE}] Error consultando el listado {clasif}/{anio} {extra}: {e}")
            return -1, []
        return _num_paginas(resp.text), _filas_listado(resp.text)

    def agregar(filas):
        for href, titulo in filas:
            por_href.setdefault(href, titulo)

    n, filas = consultar({"page": 0})
    agregar(filas)
    if n <= 1:
        return por_href

    m_ult, ultimas = consultar({"page": n - 1})
    if m_ult < 0:
        m_ult, ultimas = consultar({"page": n - 1})  # un reintento
    agregar(ultimas)
    # sin la última página no hay total verificable: se enumera sin parada temprana
    total: Optional[int] = (n - 1) * _POR_PAGINA + len(ultimas) if m_ult >= 0 else None

    def completo() -> bool:
        return total is not None and len(por_href) >= total

    for p in range(1, n - 1):
        if parar() or completo():
            break
        agregar(consultar({"page": p})[1])

    def fragmento(s: str):
        if parar() or completo():
            return
        m, filas = consultar({"combine": s})
        if m <= 1 or len(s) >= _MAX_LARGO_FRAGMENTO:
            agregar(filas)
            return
        for d in _DIGITOS:
            fragmento(s + d)

    for d in _DIGITOS:
        fragmento(d)

    if total is not None and len(por_href) < total and not parar() and on_progress:
        on_progress(
            f"[{_SOURCE}] Aviso: listado {clasif}/{anio} con {total} fichas, "
            f"faltan {total - len(por_href)} que no se pudieron enumerar"
        )
    return por_href


_ANIO_MIN = 2015
_PISO = f"{_ANIO_MIN}-01-01"

# Orden deliberado: las resoluciones de Resoluciones reclaman su título
# R_SIC_… antes que las mismas resoluciones repetidas en Doctrina.
_CLASIFICACIONES: List[Tuple[str, str]] = [
    (_CLAS_RES, "Resoluciones"),
    (_CLAS_CIR, "Circulares"),
    (_CLAS_TCU, "Títulos Circular Única"),
    (_CLAS_DOC, "Doctrina"),
]


def _anios(fini: str, ffin: str, hoy: date) -> List[int]:
    """Años de PUBLICACIÓN a consultar: un acto expedido a fin de año puede
    publicarse en enero del siguiente."""
    desde = max(_ANIO_MIN, int(fini[:4]))
    hasta = min(int(ffin[:4]) + 1, hoy.year)
    return list(range(desde, hasta + 1))


@register_family("sic")
class ScrapSIC(BaseScrapper):
    filters_by_publication_date = True

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": _UA})
        docs: List[RawDocModel] = []
        vistos: set = set()       # URLs de PDF ya emitidas
        claves: dict = {}         # (tipo, safe_title) -> URL del PDF que la ocupa
        presupuesto = [_MAX_BUSQUEDAS]
        agotado = False
        filas_totales = 0

        def parar() -> bool:
            return stop_event is not None and stop_event.is_set()

        for clasif, nombre in _CLASIFICACIONES:
            if parar():
                break
            if on_progress:
                on_progress(f"[{_SOURCE}] Listando {nombre}...")
            filas: Dict[str, str] = {}
            if not agotado:
                try:
                    for anio in _anios(fini, ffin, date.today()):
                        if parar():
                            break
                        filas.update(_enumerar_tajada(session, clasif, anio, presupuesto, stop_event, on_progress))
                except _PresupuestoAgotado:
                    agotado = True
                    if on_progress:
                        on_progress(
                            f"[{_SOURCE}] Error: presupuesto de {_MAX_BUSQUEDAS} consultas de listado "
                            f"agotado en {nombre}; se procesa lo ya encontrado"
                        )
            filas_totales += len(filas)

            descartadas = 0
            sin_pdf = 0
            for href, titulo in filas.items():
                if parar():
                    return docs[:limit]
                tipo = _clasificar(clasif, titulo)
                if tipo is None:
                    descartadas += 1
                    continue
                try:
                    resp = session.get(urljoin(_BASE, href), timeout=90)
                    resp.raise_for_status()
                except Exception as e:
                    if on_progress:
                        on_progress(f"[{_SOURCE}] Error abriendo la ficha «{titulo[:70]}»: {e}")
                    continue
                ficha = _ficha(resp.text)
                expedicion = ficha.expedicion or ficha.publicacion
                publicacion = ficha.publicacion or ficha.expedicion
                if expedicion is None:
                    if on_progress:
                        on_progress(f"[{_SOURCE}] Aviso: ficha sin fechas «{titulo[:70]}», se omite")
                    continue
                if expedicion < _PISO or publicacion < fini or publicacion > ffin:
                    continue
                if not ficha.pdfs:
                    sin_pdf += 1
                    continue

                base_title, unverified = _titulo(tipo, titulo, expedicion)
                for i, url_pdf in enumerate(ficha.pdfs):
                    if url_pdf in vistos:
                        continue
                    vistos.add(url_pdf)
                    sufijo = f"_A{i:02d}" if i else ""
                    title, unv = base_title + sufijo, unverified
                    if claves.get((tipo, _safe_title(title)), url_pdf) != url_pdf:
                        # otra ficha ya ocupó esta clave (p. ej. circular externa
                        # y conjunta con igual número y año): baja al título del sitio
                        title, unv = _crudo(titulo) + sufijo, True
                        n = 2
                        while claves.get((tipo, _safe_title(title)), url_pdf) != url_pdf:
                            title = f"{_crudo(titulo)}_{n}{sufijo}"
                            n += 1
                    claves[(tipo, _safe_title(title))] = url_pdf
                    docs.append(RawDocModel(
                        source=_SOURCE,
                        link={"url": url_pdf, "method": "GET"},
                        title=title,
                        tipo=tipo,
                        f_public=publicacion,
                        f_providencia=expedicion,
                        detalle=titulo or None,
                        save_path=storage_path(_SOURCE, publicacion, tipo, f"{_safe_title(title)}(extension)"),
                        title_unverified=unv,
                    ))
                    if len(docs) >= limit:
                        return docs[:limit]

            if on_progress and (descartadas or sin_pdf):
                on_progress(
                    f"[{_SOURCE}] {nombre}: {descartadas} fichas descartadas (proyectos, otras "
                    f"entidades u otra doctrina) y {sin_pdf} sin PDF propio en el rango"
                )

        if filas_totales == 0 and not parar() and on_progress:
            on_progress(
                f"[{_SOURCE}] Aviso: el buscador no devolvió ninguna ficha en el rango "
                "(¿cambió el marcado de la página?)"
            )
        return docs[:limit]
