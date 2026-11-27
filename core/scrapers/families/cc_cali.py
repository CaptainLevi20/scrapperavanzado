"""Laudos arbitrales del Centro de Conciliación, Arbitraje y Amigable
Composición de la Cámara de Comercio de Cali.

Diseño: docs/superpowers/specs/2026-11-23-fuente-cc_cali-design.md.

El índice de laudos sólo trae un botón por año; cada página de año
(WordPress, detrás de Cloudflare sin desafío) tiene una tabla con un enlace
por PDF. No hay columnas de radicado ni de fecha: todo sale del texto del
enlace y del nombre del archivo.
"""

import datetime
import re
import unicodedata
from typing import Iterator, List, Optional, Tuple
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from core.fecha_es import parse_fecha_providencia_es
from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_INDICE = (
    "https://www.ccc.org.co/programas-y-servicios-empresariales/"
    "centro-de-conciliacion-arbitraje-y-amigable-composicion/arbitraje/laudos-arbitrales/"
)
_SOURCE = "Cámara de Comercio de Cali"
_SIGLA = "CCC"
_TIPO = "Laudo arbitral"
_PREF = "LA"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "es-CO,es;q=0.9"}

# Sin piso: la Cámara agrega laudos a años viejos (en 2026-08 subió 13 a las
# páginas de 2015-2021), así que la corrida diaria lee todas las páginas.
# Tiene que ser mayor que los días desde el laudo más viejo (página
# 1980-1996); con 10_000 (Armenia) quedaría fuera lo anterior a 1999.
_TODA_LA_TABLA_DIAS = 20_000

# Corte del título de respaldo (sin radicado ni fecha).
_MAX_RESPALDO = 80

# Enlaces del índice a páginas de año: "/laudos-2015/",
# "/laudos/laudos-2022/", "/laudos-1980-1996/". Las rutas no son uniformes,
# así que se toman tal como vienen y no se arman a mano.
_PAGINA_ANIO_RE = re.compile(r"/laudos-(\d{4})(?:-(\d{4}))?/?$")

# Radicado del Centro, tal como lo escribe la Cámara: A-AAAAMMDD-NNNN o
# A-AAAAMMDDNNNN.
_RADICADO_RE = re.compile(r"(?<![A-Za-z0-9])A-\d{8}(?:-?\d{3,4})?(?!\d)")

# --- Lector de fechas propio (core/fecha_es no entiende años de 2 cifras,
# "ABR 13_ 2020" ni fechas con guiones en vez de espacios). Sólo fechas
# completas: un año suelto ("Acuavalle 2010") no es fecha.
_NUM_RE = re.compile(r"(?<![\d.])(\d{1,2})([-. ])(\d{1,2})\2(\d{4}|\d{2})(?![\d])")
_SEIS_RE = re.compile(r"(?<![\d])(\d{2})(\d{2})(\d{2})(?![\d])")
_MESES_ABR = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SEP": 9, "SET": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}
_ABR_RE = re.compile(
    r"(?<![A-Za-z])(" + "|".join(_MESES_ABR) + r")[\s_-]+(\d{1,2})[\s_-]+(\d{4})(?!\d)",
    re.IGNORECASE,
)


def _fecha_valida(anio: int, mes: int, dia: int) -> Optional[datetime.date]:
    if anio < 100:
        anio += 2000
    try:
        return datetime.date(anio, mes, dia)
    except ValueError:
        return None


def _fecha(texto: str) -> Optional[datetime.date]:
    """Primera fecha completa de un texto de enlace o nombre de archivo."""
    if not texto:
        return None
    for m in _NUM_RE.finditer(texto):
        f = _fecha_valida(int(m.group(4)), int(m.group(3)), int(m.group(1)))
        if f:
            return f
    for m in _ABR_RE.finditer(texto):
        f = _fecha_valida(int(m.group(3)), _MESES_ABR[m.group(1).upper()], int(m.group(2)))
        if f:
            return f
    # "12-de-diciembre-de-2018": guiones y "_" a espacios y el lector común.
    f = parse_fecha_providencia_es(re.sub(r"[-_]", " ", texto))
    if f:
        return f
    for m in _SEIS_RE.finditer(texto):
        # "280624" (ddmmaa). Se exige que no forme parte de un radicado.
        if _RADICADO_RE.search(texto[max(0, m.start() - 10):m.end() + 6]):
            continue
        f = _fecha_valida(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if f:
            return f
    return None


# --- Títulos

# Numeración interna al principio ("031.", "0061.", "0097.1.", "001.3",
# "40.1."): no es el radicado, se queda en el detalle.
_NUMERACION_RE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s*")
# Palabras de relleno al principio del texto ("Laudo Arbitral –",
# "LAUDO ARBITRAL.", "Laudo -", "TRIBUNAL ...").
_RELLENO_RE = re.compile(
    r"^(?:(?:laudo|[aá]rbitral|tribunal)(?![A-Za-zÁÉÍÓÚáéíóúñÑ])[\s.:–\-]*)+",
    re.IGNORECASE,
)


def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _respaldo(texto: str) -> str:
    s = _NUMERACION_RE.sub("", texto)
    s = _RELLENO_RE.sub("", s)
    s = _sin_tildes(s).replace(".", "")
    palabras = re.findall(r"[A-Za-z0-9]+", s)
    cuerpo = ""
    for p in palabras:
        candidato = f"{cuerpo}_{p}" if cuerpo else p
        if len(candidato) > _MAX_RESPALDO:
            break
        cuerpo = candidato
    return cuerpo or "SIN_TEXTO"


def _titulo(texto: str, archivo: str, fecha: Optional[datetime.date], anio: int) -> Tuple[str, bool]:
    """(título, title_unverified). Radicado tal cual > fecha completa >
    respaldo con las partes del texto del enlace."""
    m = _RADICADO_RE.search(texto) or _RADICADO_RE.search(archivo)
    if m:
        return f"{_PREF}_{_SIGLA}_{m.group(0)}_{anio}", False
    if fecha is not None:
        return f"{_PREF}_{_SIGLA}_{fecha.strftime('%Y%m%d')}_{anio}", False
    return f"{_PREF}_{_SIGLA}_{_respaldo(texto)}_{anio}", True


# --- Lectura del sitio


def _paginas_de_anio(html: str) -> List[Tuple[str, int, int]]:
    """(url, año inicial, año final) de cada página de año del índice, sin
    repetir y en orden de año."""
    soup = BeautifulSoup(html, "html.parser")
    vistas = {}
    for a in soup.find_all("a", href=True):
        url = urljoin(_INDICE, a["href"].strip())
        m = _PAGINA_ANIO_RE.search(urlparse(url).path)
        if not m or url in vistas:
            continue
        desde = int(m.group(1))
        hasta = int(m.group(2) or desde)
        vistas[url] = (url, desde, hasta)
    return sorted(vistas.values(), key=lambda p: (p[1], p[2], p[0]))


def _filas(html: str, url_pagina: str) -> Iterator[dict]:
    soup = BeautifulSoup(html, "html.parser")
    articulo = soup.find("article")
    if articulo is None:
        return
    for tabla in articulo.select("table.tabla3"):
        for a in tabla.find_all("a", href=True):
            yield {
                "texto": re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip(),
                "href": urljoin(url_pagina, a["href"].strip()),
            }


def _archivo(href: str) -> str:
    return unquote(urlparse(href).path.rsplit("/", 1)[-1])


def _ruta_subida(href: str) -> str:
    """"AAAA/MM/nombre" de wp-content/uploads: un archivo nuevo siempre cae en
    una carpeta más reciente, así que ordenar por esto no le cambia el sufijo
    a un laudo ya guardado."""
    ruta = unquote(urlparse(href).path)
    return ruta.split("/wp-content/uploads/", 1)[-1]


@register_family("cc_cali")
class ScrapCcCali(BaseScrapper):
    scheduled_min_lookback_days = _TODA_LA_TABLA_DIAS
    # Sin alerta_margen_dias: con 20.000 días de ventana no tendría efecto.

    def __init__(self):
        self.source = _SOURCE

    def _aviso(self, on_progress, texto: str) -> None:
        if on_progress:
            on_progress(f"[{_SOURCE}] {texto}")

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        if stop_event is not None and stop_event.is_set():
            return []
        session = requests.Session()
        session.headers.update(_HEADERS)

        self._aviso(on_progress, f"Procesando {_TIPO}...")
        try:
            resp = session.get(_INDICE, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as e:
            self._aviso(on_progress, f"Error consultando el índice de laudos: {e}")
            return []
        paginas = _paginas_de_anio(resp.content.decode("utf-8", errors="replace"))
        if not paginas:
            self._aviso(on_progress, "Aviso: no se encontraron páginas de año en el índice de laudos")
            return []

        # 1) Se lee todo el sitio: los sufijos de títulos repetidos se asignan
        #    sobre el conjunto completo, para que no dependan del rango pedido.
        candidatos = []
        vistos = set()
        for url_pagina, desde, hasta in paginas:
            if stop_event is not None and stop_event.is_set():
                return []
            rango = f"{desde}" if desde == hasta else f"{desde}-{hasta}"
            try:
                r = session.get(url_pagina, timeout=60)
                r.raise_for_status()
            except requests.RequestException as e:
                self._aviso(on_progress, f"Error consultando la página de laudos {rango}: {e}")
                continue
            filas = list(_filas(r.content.decode("utf-8", errors="replace"), url_pagina))
            if not filas:
                self._aviso(on_progress, f"Aviso: la página de laudos {rango} no trae la tabla de laudos")
            for fila in filas:
                href = fila["href"]
                if href in vistos:
                    self._aviso(on_progress, f"Aviso: '{fila['texto']}' ({rango}) repite un enlace ya visto, se omite")
                    continue
                vistos.add(href)
                candidatos.append(self._armar(fila, rango, desde, hasta, on_progress))

        # 2) Títulos repetidos: el de la ruta de subida más vieja queda sin
        #    sufijo; los siguientes llevan _2, _3… con aviso.
        grupos = {}
        for c in candidatos:
            grupos.setdefault(c["title"], []).append(c)
        for title, grupo in grupos.items():
            if len(grupo) < 2:
                continue
            grupo.sort(key=lambda c: _ruta_subida(c["href"]))
            for i, c in enumerate(grupo[1:], start=2):
                c["title"] = f"{title}_{i}"
                self._aviso(on_progress, f"Aviso: título repetido {title}; '{c['texto']}' queda como {c['title']}")

        # 3) Filtro por fecha, en el orden del sitio.
        docs: List[RawDocModel] = []
        for c in candidatos:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            iso = c["fecha"].isoformat()
            if iso < fini or iso > ffin:
                continue
            docs.append(RawDocModel(
                source=_SOURCE,
                link={"url": c["href"], "method": "GET"},
                title=c["title"],
                tipo=_TIPO,
                f_public=iso,
                f_providencia=iso,
                detalle=c["texto"] or None,
                title_unverified=c["unverified"],
                save_path=storage_path(_SOURCE, iso, _TIPO, f"{c['title']}(extension)"),
            ))
            if len(docs) >= limit:
                return docs[:limit]
        return docs[:limit]

    def _armar(self, fila: dict, rango: str, desde: int, hasta: int, on_progress) -> dict:
        texto, href = fila["texto"], fila["href"]
        archivo = _archivo(href)
        # La fecha se busca en el texto y en el nombre del archivo (hay
        # fechas que están sólo en el nombre).
        fecha_nombre = _fecha(texto) or _fecha(archivo)
        unverified = False
        if fecha_nombre is not None:
            fecha = fecha_nombre
            if not (desde <= fecha.year <= hasta):
                self._aviso(
                    on_progress,
                    f"Aviso: '{texto}' está en la página {rango} pero su nombre dice "
                    f"{fecha.strftime('%d/%m/%Y')}; se usa la fecha del nombre",
                )
        else:
            # Sin fecha: 1 de enero del año de la página. La página 1980-1996
            # no tiene año por laudo: se toma 1996 (el laudo es de ese año o
            # anterior), con aviso y sin verificar.
            fecha = datetime.date(hasta, 1, 1)
            if desde != hasta:
                unverified = True
                self._aviso(
                    on_progress,
                    f"Aviso: '{texto}' (página {rango}) no tiene año propio; se usa {hasta}-01-01",
                )
        title, sin_verificar = _titulo(texto, archivo, fecha_nombre, fecha.year)
        return {
            "texto": texto,
            "href": href,
            "fecha": fecha,
            "title": title,
            "unverified": unverified or sin_verificar,
        }
