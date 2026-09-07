import datetime
import re
import unicodedata
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests
import urllib3
from bs4 import BeautifulSoup

from core.fecha_es import parse_fecha_providencia_es
from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

# www.ssf.gov.co entrega una cadena TLS incompleta (le falta el intermediario
# Sectigo) que `certifi` no puede validar — igual que la Corte Constitucional y
# la CNDJ. Se salta la verificación TLS para este host (sesión aquí +
# link["verify"] = False para la descarga).
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
# El sitio escribe indistintamente "Resolución 0789", "Resolución No. 0789",
# "Resolución N° 0789", "Resolución número 0789" y "Resolución # 0789". El texto
# del Asunto llega a veces en Unicode NFD (la "ó" es "o" + acento combinante) y
# suele citar OTRAS resoluciones más adelante ("...deroga la Resolución No. X");
# por eso el patrón del Asunto va ANCLADO al inicio y con `.match` (nunca
# `.search`), tras normalizar a NFC en `_num_resolucion`, para tomar siempre el
# número principal. El del Documento sí usa `.search` (campo corto, sin citas).
_NUM_RES_ASUNTO = re.compile(
    r'^\s*["“”]?\s*resoluci[oó]n\s+(?:n[o°º]\.?\s*|n[uú]mero\s*|#\s*)?(\d+)', re.I
)
_NUM_RES_DOC = re.compile(r"(?:RES\.?|RESOLUCI[ÓO]N)\s*(?:N[O°º]\.?\s*|N[UÚ]MERO\s*|#\s*)?(\d+)", re.I)
_FECHA_CORTA = re.compile(r"(?<!\d)(\d{1,2})-(\d{1,2})-(\d{2})\b")
_FECHA_SLASH = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})\b")
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
    asunto = unicodedata.normalize("NFC", asunto or "")
    documento = unicodedata.normalize("NFC", documento or "")
    m = _NUM_RES_ASUNTO.match(asunto)
    if m:
        return m.group(1)
    m = _NUM_RES_DOC.search(documento)
    return m.group(1) if m else None


def _titulo(letra: str, digitos: Optional[str], sufijo: str, anio: int, texto_crudo: str) -> Tuple[str, bool]:
    if digitos:
        return f"{letra}_SSF_{int(digitos):04d}{sufijo}_{anio}", False
    return ((texto_crudo or "").strip() or "documento")[:120], True


def _tablas_de_datos(soup, columnas: set) -> list:
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


def _celdas_texto(tr) -> list:
    return [td.get_text(" ", strip=True) for td in tr.find_all("td")]


def _href_de_fila(tr) -> Optional[str]:
    for a in tr.find_all("a", href=True):
        href = a["href"].strip()
        if href and not href.lower().startswith("javascript"):
            return href
    return None


def _armar_doc(
    tipo: str,
    letra: str,
    digitos: Optional[str],
    sufijo: str,
    fecha: datetime.date,
    fini: str,
    ffin: str,
    asunto: str,
    texto_crudo: str,
    href: str,
) -> Optional[RawDocModel]:
    if fecha.year < _ANIO_MIN:
        return None
    iso = fecha.isoformat()
    if iso < fini or iso > ffin:
        return None
    title, unverified = _titulo(letra, digitos, sufijo, fecha.year, texto_crudo)
    safe = _safe_title(title)
    return RawDocModel(
        source=_SOURCE,
        link={"url": urljoin(_BASE, href), "method": "GET", "verify": False},
        title=title,
        tipo=tipo,
        f_public=iso,
        f_providencia=iso,
        detalle=(asunto or "").strip() or None,
        save_path=storage_path(_SOURCE, iso, tipo, f"{safe}(extension)"),
        title_unverified=unverified,
    )


def _fila_resolucion(tr, fini: str, ffin: str, on_progress) -> Optional[RawDocModel]:
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


def _fila_circular(tr, fini: str, ffin: str, on_progress) -> Optional[RawDocModel]:
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


@register_family("ssf")
class ScrapSSF(BaseScrapper):
    filters_by_publication_date = True

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        # Cadena TLS incompleta del sitio; ver nota al inicio del módulo.
        session.verify = False
        session.headers.update({"User-Agent": _UA})
        docs: List[RawDocModel] = []

        for url, tipo, letra, columnas in _SECCIONES:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            if on_progress:
                on_progress(f"[{_SOURCE}] Procesando {tipo}...")
            try:
                resp = session.get(url, timeout=60)
                resp.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Error consultando {tipo}: {e}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            fila_fn = _fila_resolucion if letra == "R" else _fila_circular
            tablas = _tablas_de_datos(soup, columnas)
            if not tablas and on_progress:
                on_progress(
                    f"[{_SOURCE}] Error: no se encontró ninguna tabla de datos de {tipo} "
                    "(¿cambiaron los encabezados de la página?)"
                )
            for tabla in tablas:
                if stop_event is not None and stop_event.is_set():
                    return docs[:limit]
                for tr in tabla.find_all("tr")[1:]:
                    doc = fila_fn(tr, fini, ffin, on_progress)
                    if doc is not None:
                        docs.append(doc)
                        if len(docs) >= limit:
                            return docs[:limit]

        return docs[:limit]
