import datetime
import re
import time
import unicodedata
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
# Fallas pasajeras del sitio (5xx, 429, conexión): se reintenta cada página
# antes de darla por perdida.
_MAX_INTENTOS = 3
_ESPERA_REINTENTO_SEG = 5
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
# Último tramo del enlace: "2026R000019595.aspx" → año 2026, número 19595.
_ARCHIVO_RE = re.compile(r"^(\d{4})R0*(\d+)\.aspx$", re.IGNORECASE)
_DIARIO_RE = re.compile(r"Diario Oficial:\s*(\d+)\s*(?:\((\d{1,2}/\d{1,2}/\d{4})\))?", re.IGNORECASE)
_NO_TITULO_RE = re.compile(r"[^A-Za-z0-9]+")


def _norm_texto(s: str) -> str:
    # NFC: si el sitio manda la "ó" descompuesta ("o" + tilde suelta), los
    # rótulos "Publicación"/"Expedición"/"Observación" y "Resolución" no se
    # reconocerían y se perdería cada fila (pasó con MinEducación, PR #104).
    s = unicodedata.normalize("NFC", s or "")
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


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


def _archivo(href: str) -> Optional[Tuple[int, int]]:
    """(año, número) del nombre del archivo del enlace, o None si el nombre no
    sigue el patrón AAAAR<número>.aspx."""
    nombre = urlparse(href).path.rsplit("/", 1)[-1]
    m = _ARCHIVO_RE.match(nombre)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _fechas(texto: str) -> Tuple[str, str]:
    """("Publicación: …", "Expedición: …") → (texto de publicación, texto de
    expedición). Se parte por "|" y cada mitad se reconoce por su rótulo."""
    publicacion = expedicion = ""
    for mitad in texto.split("|"):
        rotulo, _, valor = mitad.partition(":")
        rotulo = rotulo.strip().lower()
        if rotulo in ("publicación", "publicacion"):
            publicacion = valor.strip()
        elif rotulo in ("expedición", "expedicion"):
            expedicion = valor.strip()
    return publicacion, expedicion


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
            if "|" in t and re.match(r"publicaci[oó]n:", t, re.IGNORECASE):
                publicacion, expedicion = _fechas(t)
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
    """HTML de una página del listado. Reintenta las fallas pasajeras; un 4xx
    (salvo 429) es el sitio rechazando la página y no se reintenta."""
    params = {"page": str(pagina)} if pagina > 1 else None
    for intento in range(_MAX_INTENTOS):
        if intento:
            time.sleep(_ESPERA_REINTENTO_SEG * intento)
        try:
            resp = session.get(url, params=params, timeout=60)
            resp.raise_for_status()
            return resp.text
        except requests.HTTPError as e:
            codigo = e.response.status_code if e.response is not None else 0
            if (400 <= codigo < 500 and codigo != 429) or intento == _MAX_INTENTOS - 1:
                raise
        except requests.RequestException:
            if intento == _MAX_INTENTOS - 1:
                raise
    raise AssertionError("inalcanzable")


@register_family("ica")
class ScrapIca(BaseScrapper):
    # Se filtra por fecha de publicación: el ICA sube resoluciones días,
    # meses o años después de expedirlas. Cada corrida recorre el listado
    # entero (decisión del administrador, 2026-11-18), así que no hace falta
    # scheduled_min_lookback_days ni hay corte por fecha de expedición.
    filters_by_publication_date = True

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update(_HEADERS)
        docs: List[RawDocModel] = []
        vistos: set = set()

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

                for fila in filas:
                    if stop_event is not None and stop_event.is_set():
                        return docs[:limit]
                    doc = self._fila_a_doc(fila, seccional, fini, ffin, avisar)
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

                if pagina >= ultima:
                    break
                if stop_event is not None and stop_event.is_set():
                    return docs[:limit]
                # Una página que sigue fallando tras los reintentos se salta y
                # se sigue con la siguiente: el listado va por expedición y se
                # filtra por publicación, así que una resolución vieja recién
                # publicada puede estar en cualquier página; cortar aquí la
                # dejaría sin revisar mientras siga dentro de la ventana.
                html = None
                while html is None and pagina < ultima:
                    if stop_event is not None and stop_event.is_set():
                        return docs[:limit]
                    pagina += 1
                    try:
                        html = _pagina(session, url, pagina)
                    except requests.RequestException as e:
                        avisar(f"Error consultando {nombre}, página {pagina}: {e}; se salta esa página")
                if html is None:
                    break

        return docs[:limit]

    @staticmethod
    def _fila_a_doc(fila: dict, seccional: bool, fini: str, ffin: str, avisar) -> Optional[RawDocModel]:
        """Documento de la fila, o None si queda fuera (fecha ilegible, antes
        del piso o publicada fuera de [fini, ffin])."""
        title, numero, anio, epigrafe = _titulo(fila["texto"], seccional)
        publicacion = parse_fecha_providencia_es(fila["publicacion"])
        expedicion = parse_fecha_providencia_es(fila["expedicion"])
        if publicacion is None or expedicion is None:
            avisar(f"Aviso: {title} sin fecha de publicación o expedición legible, se omite")
            return None
        if expedicion < _PISO:
            return None
        f_public = publicacion.isoformat()
        if f_public < fini or f_public > ffin:
            return None

        sin_verificar = numero is None
        if sin_verificar:
            avisar(f"Aviso: texto inesperado '{fila['texto'][:80]}'; título {title} sin verificar")
        else:
            # Errores de carga del sitio: el año del texto no es el de
            # expedición, o el número/año del texto no es el del nombre del
            # archivo ("Resolución 899 de 2021" con archivo 2022R889). Se deja
            # el título del texto, marcado para revisarlo a mano.
            if anio != expedicion.year:
                sin_verificar = True
                avisar(f"Aviso: {title} fue expedida el {expedicion.isoformat()}; "
                       "se deja el año del título del sitio, sin verificar")
            archivo = _archivo(fila["href"])
            if archivo is not None and archivo != (anio, numero):
                sin_verificar = True
                avisar(f"Aviso: {title} no cuadra con su archivo: texto {numero} de {anio}, "
                       f"archivo {archivo[1]} de {archivo[0]}; título sin verificar")

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
        )
