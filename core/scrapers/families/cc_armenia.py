import datetime
import re
from typing import Iterator, List, Optional
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

# Página WordPress (tema Avada) del Centro de Arbitraje. La pestaña "Laudos"
# viene completa en el HTML; el #tab-… de la URL sólo la selecciona.
_URL = "https://camaraarmenia.org.co/centro-de-conciliacion/arbitraje/"
_SOURCE = "Cámara de Comercio de Armenia y del Quindío"
_SIGLA = "CCAQ"
_TIPO = "Laudo arbitral"
_PREF = "LA"
_ANIO_MINIMO = 2006
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "es-CO,es;q=0.9"}

# La pestaña se busca por su encabezado (estable si el editor reordena
# pestañas) y, si no, por el id que tiene hoy.
_TAB_LABEL = "fusion-tab-laudos"
_TAB_ID = "tab-9bad5edebe8f416b63c"

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
# "03 DE MARZO DE 2006"; una fila trae "06 DE MARZO 2017" (sin el segundo DE),
# que core.fecha_es no reconoce.
_FECHA_RE = re.compile(r"(\d{1,2})\s+(?:de\s+)?([a-zñ]+)\s+(?:de\s+)?(\d{4})", re.I)
_RADICADO_RE = re.compile(r"^\d+$")
# Ventana de la corrida diaria: más días que los que hay desde el piso (2006),
# es decir, toda la tabla (~27 años).
_TODA_LA_TABLA_DIAS = 10_000


def _norm_texto(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _fecha(texto: str) -> Optional[datetime.date]:
    m = _FECHA_RE.search(texto or "")
    if not m:
        return None
    mes = _MESES.get(m.group(2).lower())
    if mes is None:
        return None
    try:
        return datetime.date(int(m.group(3)), mes, int(m.group(1)))
    except ValueError:
        return None


def _titulo(radicado: str, anio: int) -> str:
    return f"{_PREF}_{_SIGLA}_{radicado}_{anio}"


def _nombre_archivo(href: str) -> str:
    """Último segmento de la ruta, decodificado. Todos los PDF viven en
    /DocumentosCamara/Laudos/, así que "laudo" se busca sólo aquí."""
    return unquote(urlparse(href).path.rsplit("/", 1)[-1])


def _filas(html: str, on_progress) -> Iterator[dict]:
    soup = BeautifulSoup(html, "html.parser")
    panel = soup.find(attrs={"aria-labelledby": _TAB_LABEL}) or soup.find(id=_TAB_ID)
    if panel is None:
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: no se encontró la pestaña de laudos en la página")
        return
    for tr in panel.find_all("tr"):
        tds = tr.find_all("td")
        enlace = tr.find("a", href=True)
        if len(tds) != 5 or enlace is None:
            continue
        yield {
            "radicado": _norm_texto(tds[0].get_text(" ", strip=True)),
            "demandante": _norm_texto(tds[1].get_text(" ", strip=True)),
            "demandado": _norm_texto(tds[2].get_text(" ", strip=True)),
            "fecha": _norm_texto(tds[3].get_text(" ", strip=True)),
            # Un href relativo (WordPress guarda lo que pegue el editor) se
            # completa con el dominio de la página (revisión del PR #110).
            "href": urljoin(_URL, enlace["href"].strip()),
        }


def _fila_a_doc(fila: dict, fini: str, ffin: str, hoy: datetime.date, on_progress) -> Optional[RawDocModel]:
    radicado = fila["radicado"]
    if not _RADICADO_RE.match(radicado):
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: laudo sin radicado legible ({radicado or 'vacío'}), se omite")
        return None
    fecha = _fecha(fila["fecha"])
    if fecha is None:
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: laudo {radicado} sin fecha legible, se omite")
        return None
    if fecha > hoy and on_progress:
        on_progress(f"[{_SOURCE}] Aviso: laudo {radicado} con fecha futura {fecha.strftime('%d/%m/%Y')}")
    if fecha.year < _ANIO_MINIMO:
        return None
    iso = fecha.isoformat()
    if iso < fini or iso > ffin:
        return None
    # La fila 20220624 enlaza a una circular del Ministerio de Justicia: un
    # archivo cuyo nombre no dice "laudo" no es el laudo.
    if "LAUDO" not in _nombre_archivo(fila["href"]).upper():
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: laudo {radicado} enlaza a un archivo que no es un laudo, se omite")
        return None

    title = _titulo(radicado, fecha.year)
    partes = " vs ".join(p for p in (fila["demandante"], fila["demandado"]) if p)
    return RawDocModel(
        source=_SOURCE,
        link={"url": fila["href"], "method": "GET"},
        title=title,
        tipo=_TIPO,
        f_public=iso,
        f_providencia=iso,
        detalle=partes or None,
        save_path=storage_path(_SOURCE, iso, _TIPO, f"{title}(extension)"),
    )


def _archivo_no_existe(session, url: str) -> bool:
    """True solo si el servidor dice claramente que el PDF no existe (404/410).
    Cualquier otra cosa (405 si no acepta HEAD, 403 de un firewall, 5xx, un
    corte de red) no es concluyente: el laudo se incluye y la descarga decide;
    si falla, queda como error visible de la corrida en vez de saltarse en
    silencio en todas las corridas (revisión del PR #110)."""
    try:
        # 15 s: con ~14 laudos y 60 s, un sitio lento dejaba la corrida de
        # esta fuente colgada ~14 minutos (revisión del PR #110). Un tiempo
        # agotado no es concluyente: el laudo se incluye igual.
        resp = session.head(url, timeout=15, allow_redirects=True)
    except requests.RequestException:
        return False
    return resp.status_code in (404, 410)


@register_family("cc_armenia")
class ScrapCcArmenia(BaseScrapper):
    # La tabla entera llega en una petición y los laudos se suben con retraso
    # desconocido (a veces de años): la corrida diaria revisa TODA la tabla.
    # _TODA_LA_TABLA_DIAS solo tiene que ser mayor que los días desde el piso
    # (2006); _ANIO_MINIMO recorta lo anterior.
    scheduled_min_lookback_days = _TODA_LA_TABLA_DIAS

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update(_HEADERS)
        docs: List[RawDocModel] = []
        vistos: set = set()
        hoy = datetime.date.today()

        if on_progress:
            on_progress(f"[{_SOURCE}] Procesando {_TIPO}...")
        try:
            resp = session.get(_URL, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as e:
            if on_progress:
                on_progress(f"[{_SOURCE}] Error consultando {_TIPO}: {e}")
            return docs

        for fila in _filas(resp.content.decode("utf-8", errors="replace"), on_progress):
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            doc = _fila_a_doc(fila, fini, ffin, hoy, on_progress)
            if doc is None:
                continue
            url = doc.link["url"]
            if url in vistos:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Aviso: {doc.title} repite un PDF ya visto, se omite")
                continue
            vistos.add(url)
            # Una fila (20221111) enlaza a un PDF que da 404: se descarta aquí
            # en vez de fallar la descarga en cada corrida.
            if _archivo_no_existe(session, url):
                if on_progress:
                    on_progress(f"[{_SOURCE}] Aviso: el PDF de {doc.title} no existe en el sitio (404), se omite")
                continue
            docs.append(doc)
            if len(docs) >= limit:
                return docs[:limit]

        return docs[:limit]
