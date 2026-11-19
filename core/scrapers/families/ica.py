import datetime
import re
from typing import List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from core.fecha_es import parse_fecha_providencia_es
from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

# "Normativa › Normas ICA" del sitio del ICA (Kentico CMS, ASP.NET). Cada
# listado va por fecha de expedición descendente, 4 resoluciones por página.
_BASE = "https://www.ica.gov.co/"
_SOURCE = "Instituto Colombiano Agropecuario"
_SIGLA = "ICA"
_TIPO = "Resolución"
_ANIO_MINIMO = 2015
_PISO = datetime.date(_ANIO_MINIMO, 1, 1)
# El ICA publica con retraso (mediana de días, pero hasta años). Se pagina por
# expedición hasta dos años antes de fini y se filtra por publicación.
_MARGEN_EXPEDICION_DIAS = 730
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "es-CO,es;q=0.9"}

_SECCIONALES_URL = urljoin(_BASE, "normatividad/normas-ica/resoluciones-seccionales")
_NACIONALES_URL = urljoin(_BASE, "normatividad/normas-ica/resoluciones-oficinas-nacionales")

# (nombre, url, seccional). La "S" del título marca la sección seccional; el
# consecutivo es único en todo el ICA.
_SECCIONES = [
    ("Resoluciones seccionales", _SECCIONALES_URL, True),
    ("Resoluciones nacionales (MSF y RT)", _NACIONALES_URL, False),
]

# "Norma" y "Acuerdo" aparecen por errores de carga del sitio en filas que son
# resoluciones; la sección entera es de resoluciones.
_TEXTO_RE = re.compile(
    r"^\s*(?:Resoluci[oó]n|Norma|Acuerdo)\s+(?:No\.?\s*)?(\d+)\s+de\s+(\d{4})", re.IGNORECASE
)
_FECHAS_RE = re.compile(r"Publicaci[oó]n:\s*(.*?)\s*\|\s*Expedici[oó]n:\s*(.*)", re.IGNORECASE)
_DIARIO_RE = re.compile(r"Diario Oficial:\s*(\d+)\s*(?:\((\d{1,2}/\d{1,2}/\d{4})\))?", re.IGNORECASE)
_NO_TITULO_RE = re.compile(r"[^A-Za-z0-9]+")


def _norm_texto(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def _titulo(texto: str, seccional: bool) -> Tuple[str, Optional[int], Optional[int], str]:
    """(título, número, año, epígrafe) a partir del texto del enlace. Si el
    texto no cumple el patrón, número y año son None y el título se arma con
    el texto saneado."""
    texto = _norm_texto(texto)
    pref = f"R_{_SIGLA}_" + ("S" if seccional else "")
    m = _TEXTO_RE.match(texto)
    if not m:
        cabeza = texto.split(" - ", 1)[0]
        saneado = _NO_TITULO_RE.sub("_", cabeza).strip("_")[:60] or "SN"
        return f"{pref}{saneado}", None, None, texto
    numero, anio = int(m.group(1)), int(m.group(2))
    epigrafe = texto[m.end():].lstrip(" -–—").strip()
    return f"{pref}{numero:04d}_{anio}", numero, anio, epigrafe


def _ultima_pagina(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    a = soup.find("a", attrs={"aria-label": "Ultima"}, href=True)
    if a is None:
        return 1
    valores = parse_qs(urlparse(a["href"]).query).get("page") or []
    try:
        return max(1, int(valores[0]))
    except (IndexError, ValueError):
        return 1


def _filas(html: str) -> List[dict]:
    """Filas crudas de una página del listado."""
    soup = BeautifulSoup(html, "html.parser")
    filas = []
    for row in soup.select("div.row.py-3"):
        enlace = row.select_one("h2 a[href]")
        if enlace is None:
            continue
        publicacion = expedicion = observacion = ""
        col = row.select_one("div.col-md-10") or row
        for div in col.find_all("div", recursive=False):
            t = _norm_texto(div.get_text(" ", strip=True))
            m = _FECHAS_RE.search(t)
            if m:
                publicacion, expedicion = m.group(1), m.group(2)
            elif t.lower().startswith("observación:") or t.lower().startswith("observacion:"):
                observacion = _norm_texto(t.split(":", 1)[1])
        diario = ""
        m = _DIARIO_RE.search(_norm_texto(col.get_text(" ", strip=True)))
        if m:
            diario = f"Diario Oficial {m.group(1)}" + (f" ({m.group(2)})" if m.group(2) else "")
        filas.append({
            "href": urljoin(_BASE, enlace["href"].strip()),
            "texto": _norm_texto(enlace.get_text(" ", strip=True)),
            "publicacion": publicacion,
            "expedicion": expedicion,
            "observacion": observacion,
            "diario": diario,
        })
    return filas


def _pagina(session, url: str, pagina: int) -> str:
    params = {"page": str(pagina)} if pagina > 1 else None
    resp = session.get(url, params=params, timeout=60)
    resp.raise_for_status()
    return resp.text


@register_family("ica")
class ScrapIca(BaseScrapper):
    # Se filtra por fecha de publicación: el ICA sube resoluciones días,
    # meses o años después de expedirlas. La paginación ya mira dos años de
    # expedición hacia atrás, así que no hace falta scheduled_min_lookback_days.
    filters_by_publication_date = True

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update(_HEADERS)
        docs: List[RawDocModel] = []
        vistos: set = set()
        corte = max(_PISO, datetime.date.fromisoformat(fini) - datetime.timedelta(days=_MARGEN_EXPEDICION_DIAS))

        def avisar(texto):
            if on_progress:
                on_progress(f"[{_SOURCE}] {texto}")

        for nombre, url, seccional in _SECCIONES:
            avisar(f"Procesando {nombre}...")
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            try:
                html = _pagina(session, url, 1)
            except requests.RequestException as e:
                avisar(f"Error consultando {nombre}: {e}")
                continue
            ultima = _ultima_pagina(html)
            pagina = 1
            while True:
                filas = _filas(html)
                if pagina == 1 and not filas:
                    avisar(f"Error: {nombre} no trajo ninguna resolución")
                    break

                ultima_expedicion = None
                for fila in filas:
                    if stop_event is not None and stop_event.is_set():
                        return docs[:limit]
                    doc, expedicion = self._fila_a_doc(fila, seccional, fini, ffin, avisar)
                    if expedicion is not None:
                        ultima_expedicion = expedicion
                    if doc is None:
                        continue
                    clave = (seccional, doc.title)
                    if clave in vistos or doc.link["url"] in vistos:
                        avisar(f"Aviso: {doc.title} aparece repetida, se deja la primera")
                        continue
                    vistos.add(clave)
                    vistos.add(doc.link["url"])
                    docs.append(doc)
                    if len(docs) >= limit:
                        return docs[:limit]

                if pagina >= ultima or (ultima_expedicion is not None and ultima_expedicion < corte):
                    break
                if stop_event is not None and stop_event.is_set():
                    return docs[:limit]
                pagina += 1
                try:
                    html = _pagina(session, url, pagina)
                except requests.RequestException as e:
                    avisar(f"Error consultando {nombre}, página {pagina}: {e}")
                    break

        return docs[:limit]

    @staticmethod
    def _fila_a_doc(fila: dict, seccional: bool, fini: str, ffin: str, avisar) -> Tuple[Optional[RawDocModel], Optional[datetime.date]]:
        """(documento o None, fecha de expedición o None si es ilegible)."""
        title, numero, anio, epigrafe = _titulo(fila["texto"], seccional)
        publicacion = parse_fecha_providencia_es(fila["publicacion"])
        expedicion = parse_fecha_providencia_es(fila["expedicion"])
        if publicacion is None or expedicion is None:
            avisar(f"Aviso: {title} sin fecha de publicación o expedición legible, se omite")
            return None, expedicion
        if expedicion < _PISO:
            return None, expedicion
        f_public = publicacion.isoformat()
        if f_public < fini or f_public > ffin:
            return None, expedicion

        sin_verificar = numero is None
        if sin_verificar:
            avisar(f"Aviso: texto inesperado '{fila['texto'][:80]}'; título {title} sin verificar")
        elif anio != expedicion.year:
            avisar(f"Aviso: {title} fue expedida el {expedicion.isoformat()}; se deja el año del título del sitio")

        partes = [epigrafe] if epigrafe else []
        if fila["observacion"]:
            partes.append(fila["observacion"])
        if fila["diario"]:
            partes.append(fila["diario"])
        return RawDocModel(
            source=_SOURCE,
            link={"url": fila["href"], "method": "GET"},
            title=title,
            tipo=_TIPO,
            f_public=f_public,
            f_providencia=expedicion.isoformat(),
            detalle=" — ".join(partes) or None,
            save_path=storage_path(_SOURCE, f_public, _TIPO, f"{title}(extension)"),
            title_unverified=sin_verificar,
        ), expedicion
