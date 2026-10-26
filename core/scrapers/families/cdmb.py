import datetime
import re
from typing import Iterator, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

# Sistema documental GDI (PHP 5.2). Sólo HTTP: el puerto 443 no responde.
_BASE = "http://caracoli.cdmb.gov.co/gdi/"
_SOURCE = "Corporación Autónoma Regional para la Defensa de la Meseta de Bucaramanga"
_SIGLA = "CDMB"
_ANIO_MINIMO = 2025
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "es-CO,es;q=0.9"}
_ENCODING = "cp1252"

_RES_URL = urljoin(_BASE, "res_consulta.php")
_ACU_URL = urljoin(_BASE, "acuerdos.php")
_ACU_POR_PAGINA = 30
_ACU_PAGINA_TOPE = 50

# Una fila cuenta sólo si trae el enlace al detalle con su número.
_DET_RES = re.compile(r"res_consdet\.php\?resolucion=-?\d+")
_DET_ACU = re.compile(r"acu_consdet\.php\?num_acuerdo=-?\d+")
_NUM_RE = re.compile(r"-?\d+")
_FECHA_RE = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)")
_PDF_RE = re.compile(r"\.pdf$", re.I)


def _decodificar(resp: requests.Response) -> str:
    return resp.content.decode(_ENCODING, errors="replace")


def _norm_texto(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _fecha(texto: str) -> Optional[datetime.date]:
    m = _FECHA_RE.search(texto or "")
    if not m:
        return None
    dd, mm, yyyy = (int(x) for x in m.groups())
    try:
        return datetime.date(yyyy, mm, dd)
    except ValueError:
        return None


def _numero(texto: str) -> Optional[int]:
    """Número de la celda; los negativos que trae el sitio (-1295) se toman
    en valor absoluto."""
    m = _NUM_RE.search(texto or "")
    if not m:
        return None
    n = abs(int(m.group(0)))
    return n or None


def _titulo(pref: str, numero: int, anio: int) -> str:
    return f"{pref}_{_SIGLA}_{numero:04d}_{anio}"


def _filas(html: str, detalle_re: re.Pattern) -> Iterator[dict]:
    """Filas del listado como dicts crudos (href del PDF, número, fecha,
    referencia). El href viene con espacio final y relativo."""
    soup = BeautifulSoup(html, "html.parser")
    for tr in soup.find_all("tr"):
        if not tr.find("a", href=detalle_re):
            continue
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 3:
            continue
        enlace = tds[0].find("a")
        yield {
            "href": (enlace.get("href") or "").strip() if enlace else "",
            "numero": _norm_texto(tds[0].get_text(" ", strip=True)),
            "fecha": _norm_texto(tds[1].get_text(" ", strip=True)),
            "referencia": _norm_texto(tds[2].get_text(" ", strip=True)),
        }


def _fila_a_doc(fila: dict, tipo: str, pref: str, fini: str, ffin: str, hoy: datetime.date, on_progress) -> Optional[RawDocModel]:
    fecha = _fecha(fila["fecha"])
    if fecha is None:
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: {tipo} {fila['numero']} sin fecha legible, se omite")
        return None
    if fecha > hoy and on_progress:
        on_progress(f"[{_SOURCE}] Aviso: {tipo} {fila['numero']} con fecha futura {fecha.strftime('%d/%m/%Y')}")
    if fecha.year < _ANIO_MINIMO:
        return None
    iso = fecha.isoformat()
    if iso < fini or iso > ffin:
        return None

    numero = _numero(fila["numero"])
    if not _PDF_RE.search(fila["href"]) or numero is None:
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: {tipo} {fila['numero']} del {iso} sin PDF, se omite")
        return None

    title = _titulo(pref, numero, fecha.year)
    return RawDocModel(
        source=_SOURCE,
        link={"url": urljoin(_BASE, fila["href"]), "method": "GET"},
        title=title,
        tipo=tipo,
        f_public=iso,
        f_providencia=iso,
        detalle=fila["referencia"] or None,
        save_path=storage_path(_SOURCE, iso, tipo, f"{title}(extension)"),
    )


def _filas_resoluciones(session, fini: str, ffin: str, stop_event) -> Iterator[dict]:
    """Un POST por año: el GDI devuelve el año entero en una sola página."""
    desde = max(int(fini[:4]), _ANIO_MINIMO)
    for anio in range(desde, int(ffin[:4]) + 1):
        if stop_event is not None and stop_event.is_set():
            return
        datos = {"ob": "0", "anhoc": str(anio), "palabras": "", "botonenv": "Buscar"}
        resp = session.post(_RES_URL, data=datos, timeout=120)
        resp.raise_for_status()
        yield from _filas(_decodificar(resp), _DET_RES)


def _filas_acuerdos(session, fini: str, ffin: str, stop_event) -> Iterator[dict]:
    """Todos los años juntos, por número descendente: se recorre entero."""
    for pagina in range(_ACU_PAGINA_TOPE):
        if stop_event is not None and stop_event.is_set():
            return
        resp = session.get(_ACU_URL, params={"bloque": pagina * _ACU_POR_PAGINA}, timeout=60)
        resp.raise_for_status()
        filas = list(_filas(_decodificar(resp), _DET_ACU))
        if not filas:
            return
        yield from filas


_SECCIONES = [
    (_filas_resoluciones, "Resolución", "R"),
    (_filas_acuerdos, "Acuerdo", "A"),
]


@register_family("cdmb")
class ScrapCdmb(BaseScrapper):
    # El GDI sube los actos semanas después de su fecha (mediana ~33 días,
    # máximo visto 54). Una petición trae el año completo y los acuerdos se
    # recorren enteros, así que mirar 90 días atrás no cuesta peticiones.
    scheduled_min_lookback_days = 90

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update(_HEADERS)
        docs: List[RawDocModel] = []
        vistos: set = set()
        hoy = datetime.date.today()

        for filas_de, tipo, pref in _SECCIONES:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            if on_progress:
                on_progress(f"[{_SOURCE}] Procesando {tipo}...")
            try:
                for fila in filas_de(session, fini, ffin, stop_event):
                    if stop_event is not None and stop_event.is_set():
                        return docs[:limit]
                    doc = _fila_a_doc(fila, tipo, pref, fini, ffin, hoy, on_progress)
                    if doc is None:
                        continue
                    if doc.link["url"] in vistos:
                        if on_progress:
                            on_progress(f"[{_SOURCE}] Aviso: {doc.title} repite un PDF ya visto, se omite")
                        continue
                    vistos.add(doc.link["url"])
                    docs.append(doc)
                    if len(docs) >= limit:
                        return docs[:limit]
            except requests.RequestException as e:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Error consultando {tipo}: {e}")

        return docs[:limit]
