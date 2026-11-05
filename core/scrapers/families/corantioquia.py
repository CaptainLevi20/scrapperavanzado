import datetime
import re
from typing import Iterator, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests
import urllib3

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

# Boletín Oficial de e-SIRENA. La página CtrlPublicaciones es un cascarón
# AngularJS que pide JSON al mismo endpoint; se lee el JSON directo.
#
# TLS: *.corantioquia.gov.co entrega el certificado sin el intermedio (Sectigo
# Public Server Authentication CA OV R36) y requests falla con "unable to get
# local issuer certificate". Se salta la verificación sólo para este host
# (session.verify = False en scrap() + link["verify"] = False al descargar),
# como en snr.
_URL = "https://sirena.corantioquia.gov.co/esirena/CtrlPublicaciones"
_SOURCE = "Corporación Autónoma Regional del Centro de Antioquia"
_SIGLA = "CORANT"
_ANIO_MINIMO = 2025
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_HEADERS = {"User-Agent": _UA, "Accept": "application/json", "Accept-Language": "es-CO,es;q=0.9"}
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_POR_PAGINA = 15
_PAGINA_TOPE = 30

# tipo.nombre del boletín → (tipo asignado, prefijo). Autos ("Acto
# administrativo"), edictos y notificaciones por aviso no entran.
_TIPOS = {
    "Resolución": ("Resolución", "R"),
    "Acuerdo": ("Acuerdo", "A"),
}

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_FECHA_RE = re.compile(r"(\d{1,2})\s+de\s+([a-zñ]+)\s+de\s+(\d{4})", re.I)
# <dependencia>[<oficina>]-<TIPO><AAMM>-<consecutivo>: 040-RES2610-3892,
# 160TH-RES2501-80. El consecutivo es anual por tipo, común a todas las
# dependencias, así que la dependencia no va en el título.
_RADICADO_RE = re.compile(r"^\d{3}[A-Z]{0,4}-(RES|ACU)(\d{2})(\d{2})-(\d+)$")
_NO_SEGURO_RE = re.compile(r"[^A-Za-z0-9-]+")


def _fecha(texto: str) -> Optional[datetime.date]:
    """"09 de Octubre de 2026" (fechaRadicacion) o el nombre del boletín
    "2876 de 14 de octubre de 2026"."""
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


def _titulo(pref: str, radicado: str) -> Tuple[str, bool]:
    """(título, cumple el patrón). Un radicado fuera del patrón (los antiguos
    130SAE-1105-131) se usa saneado."""
    m = _RADICADO_RE.match(radicado or "")
    if m:
        return f"{pref}_{_SIGLA}_{int(m.group(4)):04d}_20{m.group(2)}", True
    saneado = _NO_SEGURO_RE.sub("-", radicado or "").strip("-") or "sin-radicado"
    return f"{pref}_{_SIGLA}_{saneado}", False


def _id_descarga(link: str) -> str:
    return (parse_qs(urlparse(link or "").query).get("doc") or [link])[0]


def _boletines(session, fini: datetime.date, ffin: datetime.date, on_progress) -> List[Tuple[datetime.date, int]]:
    """(fecha, número) de los boletines con fecha en [fini, ffin], en orden
    cronológico. La fecha sólo viene en el nombre."""
    resp = session.get(_URL, params={"ctrlAction": "C", "pagina": 1, "doAction": "A"}, timeout=120)
    resp.raise_for_status()
    elegidos = []
    for anio, lista in (resp.json().get("boletines") or {}).items():
        if not anio.isdigit() or not (fini.year <= int(anio) <= ffin.year):
            continue
        for boletin in lista or []:
            fecha = _fecha(boletin.get("nombre"))
            if fecha is None:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Aviso: boletín {boletin.get('numero')} sin fecha en el nombre, se omite")
                continue
            if fini <= fecha <= ffin and boletin.get("numero") is not None:
                elegidos.append((fecha, int(boletin["numero"])))
    return sorted(elegidos)


def _documentos(session, numero: int, stop_event) -> Iterator[dict]:
    """Documentos de un boletín, 15 por página. Una página con menos de 15 es
    la última; pasada la última llega "boletines": {}."""
    for pagina in range(1, _PAGINA_TOPE + 1):
        if stop_event is not None and stop_event.is_set():
            return
        resp = session.get(_URL, params={"ctrlAction": "C", "numero": numero, "pagina": pagina}, timeout=60)
        resp.raise_for_status()
        documentos = []
        for por_numero in (resp.json().get("boletines") or {}).values():
            for boletin in (por_numero or {}).values():
                documentos.extend(boletin.get("documentos") or [])
        yield from documentos
        if len(documentos) < _POR_PAGINA:
            return


def _doc(documento: dict, publicacion: datetime.date, on_progress) -> Optional[RawDocModel]:
    tipo_sitio = ((documento.get("tipo") or {}).get("nombre") or "").strip()
    if tipo_sitio not in _TIPOS:
        return None
    tipo, pref = _TIPOS[tipo_sitio]
    radicado = (documento.get("sirenaRadicado") or "").strip()
    fecha = _fecha(documento.get("fechaRadicacion"))
    if fecha is None:
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: {tipo} {radicado} sin fecha legible, se omite")
        return None
    # El boletín republica actos viejos (resoluciones de 2000-2015 en 2026).
    if fecha.year < _ANIO_MINIMO:
        return None
    link = (documento.get("linkDescarga") or "").strip()
    if not link:
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: {tipo} {radicado} sin enlace de descarga, se omite")
        return None

    title, en_patron = _titulo(pref, radicado)
    if not en_patron and on_progress:
        on_progress(f"[{_SOURCE}] Aviso: {tipo} con radicado fuera del patrón ({radicado}), título {title}")
    if (documento.get("cantidadAnexos") or 0) > 0 and on_progress:
        on_progress(f"[{_SOURCE}] Aviso: {title} trae anexos; sólo se guarda el documento principal")

    iso_pub = publicacion.isoformat()
    subtipo = ((documento.get("subtipo") or {}).get("nombre") or "").strip()
    return RawDocModel(
        source=_SOURCE,
        link={"url": link, "method": "GET", "verify": False},
        title=title,
        tipo=tipo,
        f_public=iso_pub,
        f_providencia=fecha.isoformat(),
        detalle=" — ".join(p for p in (radicado, subtipo) if p) or None,
        save_path=storage_path(_SOURCE, iso_pub, tipo, f"{title}(extension)"),
    )


@register_family("corantioquia")
class ScrapCorantioquia(BaseScrapper):
    # El boletín de un día es fijo y trae los actos publicados ese día, aunque
    # sean de meses atrás: se filtra por la fecha del boletín y la corrida
    # diaria no necesita mirar más atrás.
    filters_by_publication_date = True

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update(_HEADERS)
        session.verify = False
        docs: List[RawDocModel] = []
        vistos: set = set()

        def parar() -> bool:
            return stop_event is not None and stop_event.is_set()

        desde = max(datetime.date.fromisoformat(fini), datetime.date(_ANIO_MINIMO, 1, 1))
        hasta = datetime.date.fromisoformat(ffin)
        if desde > hasta:
            return docs

        if on_progress:
            on_progress(f"[{_SOURCE}] Procesando Boletín Oficial...")
        try:
            boletines = _boletines(session, desde, hasta, on_progress)
        except (requests.RequestException, ValueError) as e:
            if on_progress:
                on_progress(f"[{_SOURCE}] Error consultando el índice de boletines: {e}")
            return docs

        for publicacion, numero in boletines:
            if parar():
                return docs[:limit]
            try:
                for documento in _documentos(session, numero, stop_event):
                    if parar():
                        return docs[:limit]
                    doc = _doc(documento, publicacion, on_progress)
                    if doc is None:
                        continue
                    clave = _id_descarga(doc.link["url"])
                    if clave in vistos:
                        if on_progress:
                            on_progress(f"[{_SOURCE}] Aviso: {doc.title} repite un documento ya visto, se omite")
                        continue
                    vistos.add(clave)
                    docs.append(doc)
                    if len(docs) >= limit:
                        return docs[:limit]
            except (requests.RequestException, ValueError) as e:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Error consultando el boletín {numero}: {e}")

        return docs[:limit]
