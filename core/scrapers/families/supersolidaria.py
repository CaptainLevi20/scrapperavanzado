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


def _resolver_fecha(tipo, fecha_por_prosa, titulo, href, anio_h2, time_iso):
    if fecha_por_prosa:
        d = parse_fecha_providencia_es(titulo or "")
        if d is not None:
            return d.isoformat()
        pf = _prefijo_fecha_archivo(href)
        if pf:
            return pf
        return f"{anio_h2:04d}-01-01" if anio_h2 else None
    # circulares externas / conjuntas / cartas
    iso = _iso_de_time(time_iso) or _prefijo_fecha_archivo(href)
    if iso:
        return iso
    return f"{anio_h2:04d}-01-01" if anio_h2 else None


def _time_iso_de_paragraph(a_tag) -> Optional[str]:
    # sube al paragraph--type--archivos-collection y busca un <time datetime=…>
    cont = a_tag
    while cont is not None:
        cont = cont.parent
        if cont is None:
            return None
        clases = cont.get("class") or []
        if any("archivos-collection" in c or "paragraph--type--archivos" in c for c in clases):
            t = cont.find("time", attrs={"datetime": True})
            return t["datetime"] if t else None
    return None


def _iter_documentos(soup):
    # recorre todos los <h2> y <a> de span.file en orden de documento
    for nodo in soup.find_all(["h2", "a"]):
        if nodo.name == "h2":
            anio = _anio_de_h2(nodo.get_text(" ", strip=True))
            if anio is not None:
                yield ("h2", anio)
            continue
        # <a>: sólo si su padre inmediato es span.file
        padre = nodo.parent
        if padre is None or padre.name != "span":
            continue
        clases = padre.get("class") or []
        if not any(c == "file" or c.startswith("file--") for c in clases):
            continue
        href = (nodo.get("href") or "").strip()
        if not href:
            continue
        titulo = nodo.get_text(" ", strip=True)
        yield ("doc", (titulo, href, _time_iso_de_paragraph(nodo)))


def _filas_concepto(html: str) -> List[Tuple[str, str, Optional[str]]]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: List[Tuple[str, str, Optional[str]]] = []
    for tr in soup.select("tr"):
        cel_tit = tr.select_one("td.views-field-title")
        cel_dl = tr.select_one("td.views-field-nothing")
        if cel_tit is None or cel_dl is None:
            continue
        a_tit = cel_tit.find("a")
        a_dl = cel_dl.find("a", href=True)
        if a_tit is None or a_dl is None:
            continue
        titulo = a_tit.get_text(" ", strip=True)
        href = a_dl["href"].strip()
        t = tr.find("time", attrs={"datetime": True})
        out.append((titulo, href, t["datetime"] if t else None))
    return out


def _agregar(docs, vistos, ya_emitidos, source, tipo, url_pdf, titulo, fecha, prefijo, es_anexo, limit):
    """Construye y agrega un RawDocModel; devuelve True si se alcanzó `limit`."""
    if url_pdf in vistos:
        return False
    title, unverified = _titulo(prefijo, tipo, titulo, fecha[:4], es_anexo)
    if not unverified and title in ya_emitidos and ya_emitidos[title] != url_pdf:
        # colisión de clave con archivo distinto -> degradar
        title, unverified = ((titulo or "").strip() or "documento")[:120].strip(" .") or "documento", True
    vistos.add(url_pdf)
    if not unverified:
        ya_emitidos[title] = url_pdf
    safe = _safe_title(title)
    docs.append(RawDocModel(
        source=source,
        link={"url": url_pdf, "method": "GET"},
        title=title,
        tipo=tipo,
        f_public=fecha,
        f_providencia=fecha,
        detalle=(titulo or "").strip() or None,
        save_path=storage_path(source, fecha, tipo, f"{safe}(extension)"),
        title_unverified=unverified,
    ))
    return len(docs) >= limit


@register_family("supersolidaria")
class ScrapSupersolidaria(BaseScrapper):
    filters_by_publication_date = True

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": _UA})
        docs: List[RawDocModel] = []
        vistos: set = set()
        ya_emitidos: dict = {}
        piso = f"{_ANIO_MIN:04d}-01-01"

        for url, tipo, prefijo, fecha_por_prosa in _SECCIONES_TABLA:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            if on_progress:
                on_progress(f"[{_SOURCE}] Procesando {tipo}...")
            try:
                resp = session.get(url, timeout=90)
                resp.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Error consultando {tipo}: {e}")
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            anio_actual: Optional[int] = None
            for kind, payload in _iter_documentos(soup):
                if stop_event is not None and stop_event.is_set():
                    return docs[:limit]
                if kind == "h2":
                    anio_actual = payload
                    continue
                titulo, href, time_iso = payload
                url_pdf = urljoin(_BASE, href)
                fecha = _resolver_fecha(tipo, fecha_por_prosa, titulo, href, anio_actual, time_iso)
                if fecha is None:
                    if on_progress:
                        on_progress(f"[{_SOURCE}] Aviso: {tipo} sin fecha «{titulo[:70]}», se omite")
                    continue
                if fecha < piso or fecha < fini or fecha > ffin:
                    continue
                if _agregar(docs, vistos, ya_emitidos, _SOURCE, tipo, url_pdf, titulo, fecha,
                            prefijo, _es_anexo(titulo), limit):
                    return docs[:limit]

        # --- Conceptos (vista paginada) ---
        if stop_event is not None and stop_event.is_set():
            return docs[:limit]
        if on_progress:
            on_progress(f"[{_SOURCE}] Procesando Concepto...")
        page = 0
        while True:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            try:
                resp = session.get(_URL_CONCEPTOS, params={"page": page}, timeout=90)
                resp.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Error consultando Concepto (page {page}): {e}")
                break
            filas = _filas_concepto(resp.text)
            if not filas:
                break
            for titulo, href, time_iso in filas:
                if not href:
                    continue
                url_pdf = urljoin(_BASE, href)
                if url_pdf in vistos:
                    continue
                fecha = _fecha_concepto(href, time_iso)
                if fecha is None:
                    if on_progress:
                        on_progress(f"[{_SOURCE}] Aviso: Concepto sin fecha «{titulo[:70]}», se omite")
                    continue
                if fecha < piso or fecha < fini or fecha > ffin:
                    continue
                title, unverified = _titulo_concepto(href, titulo, fecha[:4])
                vistos.add(url_pdf)
                safe = _safe_title(title)
                docs.append(RawDocModel(
                    source=_SOURCE,
                    link={"url": url_pdf, "method": "GET"},
                    title=title,
                    tipo="Concepto",
                    f_public=fecha,
                    f_providencia=fecha,
                    detalle=(titulo or "").strip() or None,
                    save_path=storage_path(_SOURCE, fecha, "Concepto", f"{safe}(extension)"),
                    title_unverified=unverified,
                ))
                if len(docs) >= limit:
                    return docs[:limit]
            page += 1
            if page > 200:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Aviso: tope de 200 páginas de Concepto alcanzado")
                break

        return docs[:limit]
