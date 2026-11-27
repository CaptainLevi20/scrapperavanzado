"""Cámara de Comercio de Barranquilla — laudos arbitrales.

Diseño: docs/superpowers/specs/2026-11-23-fuente-cc_barranquilla-design.md.

Los laudos están en una carpeta del OneDrive (SharePoint Online) de una
funcionaria del Centro de Conciliación y Arbitraje, compartida con
"cualquier persona con el vínculo". El enlace público está en la tarjeta
"Laudos Arbitrales" de la página del Centro. Abrir ese enlace deja una cookie
anónima (FedAuth) con la que la API REST de SharePoint lista las carpetas;
sin ella todo responde 403 o manda al inicio de sesión de Microsoft. Por eso
la descarga usa el método "sharepoint_compartido" de core/downloader.py, que
abre el enlace antes de bajar el archivo con la misma sesión.

Una subcarpeta por año (2014…), con los PDF dentro. La fecha del laudo sólo
está en el nombre del archivo, en varios formatos; no hay radicado, así que
la fecha completa hace de número: LA_CCBAR_{AAAAMMDD}_{año}.
"""
import datetime
import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple
from urllib.parse import parse_qs, quote, urlparse

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_SOURCE = "Cámara de Comercio de Barranquilla"
# "CCB" es la Cámara de Comercio de Bogotá en IURISYNC (familia ccb); la
# sigla de Barranquilla la decidió el administrador el 2026-11-25.
_SIGLA = "CCBAR"
_TIPO = "Laudo arbitral"
_PREF = "LA"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "es-CO,es;q=0.9"}
_JSON = {"Accept": "application/json;odata=nometadata"}

_PAGINA_CENTRO = "https://www.camarabaq.org.co/centro-de-conciliacion-y-arbitraje/"
# Respaldo si la tarjeta desaparece de la página (se avisa en la corrida).
_ENLACE_CONOCIDO = (
    "https://camarabquilla-my.sharepoint.com/:f:/g/personal/naltamar_camarabaq_org_co/"
    "EtYmeJ4NR1dHv54S0g4JT54BsqsrOfoDFjcYOdtNF_sHMA?e=goH5U0"
)
# Sitio y carpeta raíz conocidos. Normalmente salen del `id` de la página a
# la que redirige el enlace; estos son el respaldo.
_SITIO_CONOCIDO = "https://camarabquilla-my.sharepoint.com/personal/naltamar_camarabaq_org_co"
_RAIZ_CONOCIDA = "/personal/naltamar_camarabaq_org_co/Documents/LAUDOS CENTRO DE CONCILIACIÓN Y ARBITRAJE CCB"

# Listar todo cuesta ~16 peticiones (~3 s) y los laudos se suben con semanas
# o años de retraso (uno de 2014 se subió en 2026): la corrida diaria recorre
# siempre la carpeta entera. Mismo valor en las cámaras nuevas.
_TODA_LA_CARPETA_DIAS = 20_000

_AAAA_MM_DD = re.compile(r"^(\d{4})\s*-\s*(\d{1,2})\s*-\s*(\d{1,2})(?!\d)")
# "2018-09-2018": el día no se puede leer.
_AAAA_MM_ILEGIBLE = re.compile(r"^(\d{4})\s*-\s*(\d{1,2})\s*-\s*\d{3,}")
_DD_MM_AAAA = re.compile(r"^(\d{1,2})\s*-\s*(\d{1,2})\s*-\s*(\d{4})(?!\d)")
_OCHO_CIFRAS = re.compile(r"^(\d{8})(?!\d)")
_PREFIJO_FECHA = re.compile(r"^\s*\d[\d\s-]*?(?=\s[^\d\s-])")
_PALABRA_LAUDO = re.compile(
    r"^(?:audiencia\s+de\s+laudo\s+y\s+)?(?:laudo|ludo)(?:\s+arbitra(?:l|je))?(?:\s+de)?\s+(?:-\s*)?",
    re.IGNORECASE,
)


def _nfc(texto: str) -> str:
    # Hay nombres con la tilde separada de la letra (U+0301), como en MinEducación.
    return unicodedata.normalize("NFC", texto or "")


def _fecha_valida(anio: int, mes: int, dia: int) -> Optional[datetime.date]:
    try:
        return datetime.date(anio, mes, dia)
    except ValueError:
        return None


def _anio_posible(anio: int) -> bool:
    return 1990 <= anio <= datetime.date.today().year + 1


def _fecha_ocho_cifras(cifras: str) -> Optional[datetime.date]:
    """Hay prefijos AAAAMMDD (20240515) y DDMMAAAA (18062026): se lee como
    AAAAMMDD si las 4 primeras cifras son un año posible y el resto da una
    fecha válida; si no, como DDMMAAAA."""
    anio = int(cifras[:4])
    if _anio_posible(anio):
        fecha = _fecha_valida(anio, int(cifras[4:6]), int(cifras[6:8]))
        if fecha is not None:
            return fecha
    anio = int(cifras[4:])
    if _anio_posible(anio):
        return _fecha_valida(anio, int(cifras[2:4]), int(cifras[:2]))
    return None


def _fecha_del_nombre(nombre: str) -> Tuple[Optional[datetime.date], bool]:
    """(fecha, supuesta). `supuesta` es True cuando el día no se pudo leer y
    se tomó el 1 del mes. (None, False) si el nombre no trae fecha legible."""
    nombre = nombre.strip()
    m = _AAAA_MM_DD.match(nombre)
    if m:
        anio, mes, dia = (int(g) for g in m.groups())
        if mes > 12 and dia <= 12:
            # "2015-26-06": AAAA-DD-MM
            mes, dia = dia, mes
        return _fecha_valida(anio, mes, dia), False
    m = _AAAA_MM_ILEGIBLE.match(nombre)
    if m:
        fecha = _fecha_valida(int(m.group(1)), int(m.group(2)), 1)
        return fecha, fecha is not None
    m = _DD_MM_AAAA.match(nombre)
    if m:
        dia, mes, anio = (int(g) for g in m.groups())
        return _fecha_valida(anio, mes, dia), False
    m = _OCHO_CIFRAS.match(nombre)
    if m:
        return _fecha_ocho_cifras(m.group(1)), False
    return None, False


def _partes(nombre: str) -> str:
    """Las partes del laudo, tomadas del nombre sin el prefijo de fecha, la
    palabra "LAUDO ARBITRAL" ni la extensión."""
    texto = _nfc(nombre)
    texto = re.sub(r"\.pdf$", "", texto, flags=re.IGNORECASE)
    texto = _PREFIJO_FECHA.sub("", texto, count=1).strip()
    texto = re.sub(r"^-\s*", "", texto)
    texto = _PALABRA_LAUDO.sub("", texto, count=1)
    return re.sub(r"\s+", " ", texto).strip(" .")


@dataclass
class _Entrada:
    carpeta: str
    archivo: dict
    fecha: Optional[datetime.date] = None
    unverified: bool = False
    titulo: str = ""
    sin_fecha: bool = False
    repetida: bool = False

    @property
    def nombre(self) -> str:
        return _nfc(self.archivo.get("Name", ""))

    @property
    def orden(self) -> tuple:
        # Orden de subida: un laudo nuevo siempre se sube después, así que
        # nunca le cambia el título (sufijo o SF{n}) a uno ya guardado.
        return (self.archivo.get("TimeCreated") or "", self.archivo.get("UniqueId") or "")


def _anio_carpeta(carpeta: str) -> Optional[int]:
    return int(carpeta) if re.fullmatch(r"\d{4}", carpeta.strip()) else None


def _titular(entradas: List["_Entrada"], avisar: Callable[[str], None]) -> List["_Entrada"]:
    """Pone fecha y título a cada entrada. Se calcula sobre la carpeta entera
    (no sólo lo que cae en la ventana) para que los sufijos sean estables."""
    listas: List[_Entrada] = []
    sin_fecha: dict = {}
    for e in entradas:
        e.fecha, e.unverified = _fecha_del_nombre(e.nombre)
        if e.fecha is not None:
            listas.append(e)
            continue
        anio = _anio_carpeta(e.carpeta)
        if anio is None:
            avisar(f"[{_SOURCE}] Aviso: '{e.nombre}' no trae fecha y está fuera de una carpeta de año, se omite")
            continue
        sin_fecha.setdefault(anio, []).append(e)

    por_fecha: dict = {}
    for e in listas:
        por_fecha.setdefault(e.fecha, []).append(e)
    for fecha, grupo in por_fecha.items():
        grupo.sort(key=lambda x: x.orden)
        for i, e in enumerate(grupo):
            e.titulo = f"{_PREF}_{_SIGLA}_{fecha.strftime('%Y%m%d')}_{fecha.year}"
            if i:
                e.titulo += f"_{i + 1}"
                e.repetida = True

    for anio, grupo in sin_fecha.items():
        grupo.sort(key=lambda x: x.orden)
        for i, e in enumerate(grupo, start=1):
            e.fecha = datetime.date(anio, 1, 1)
            e.unverified = True
            e.sin_fecha = True
            e.titulo = f"{_PREF}_{_SIGLA}_SF{i}_{anio}"

    return [e for e in entradas if e.titulo]


def _enlace_de_pagina(html: str) -> Optional[str]:
    """El enlace compartido (:f:) de la tarjeta "Laudos Arbitrales"."""
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        texto = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).lower()
        if "sharepoint.com/:f:" in href and "laudos arbitrales" in texto:
            return href
    return None


def _sitio_y_raiz(url_final: str) -> Tuple[str, str]:
    """El enlace redirige a …/_layouts/15/onedrive.aspx?id=<ruta de la carpeta>.
    De ahí salen el sitio (…/personal/<usuario>) y la carpeta raíz."""
    p = urlparse(url_final)
    ruta = (parse_qs(p.query).get("id") or [""])[0]
    segmentos = ruta.split("/")
    if ruta.startswith("/personal/") and len(segmentos) > 3:
        return f"{p.scheme}://{p.netloc}/{segmentos[1]}/{segmentos[2]}", ruta
    return _SITIO_CONOCIDO, _RAIZ_CONOCIDA


def _listar(session, sitio: str, ruta: str) -> dict:
    valor = quote(ruta.replace("'", "''"), safe="/")
    url = f"{sitio}/_api/web/GetFolderByServerRelativePath(decodedurl='{valor}')"
    resp = session.get(url, params={"$expand": "Folders,Files"}, headers=_JSON, timeout=60)
    resp.raise_for_status()
    return resp.json()


@register_family("cc_barranquilla")
class ScrapCcBarranquilla(BaseScrapper):
    scheduled_min_lookback_days = _TODA_LA_CARPETA_DIAS
    # Obligatorio: el HEAD sin cookie de la revisión de republicación sigue las
    # redirecciones y recibe el tamaño de la página de inicio de sesión de
    # Microsoft, no el del laudo; con la revisión encendida, cada corrida lo
    # volvería a bajar. Además, un laudo no se reemplaza.
    checks_for_republication = False

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        def avisar(texto: str) -> None:
            if on_progress:
                on_progress(texto)

        def cancelado() -> bool:
            return stop_event is not None and stop_event.is_set()

        session = requests.Session()
        session.headers.update(_HEADERS)
        docs: List[RawDocModel] = []
        avisar(f"[{_SOURCE}] Procesando {_TIPO}...")

        enlace = None
        try:
            pagina = session.get(_PAGINA_CENTRO, timeout=60)
            pagina.raise_for_status()
            enlace = _enlace_de_pagina(pagina.content.decode("utf-8", errors="replace"))
        except requests.RequestException as e:
            avisar(f"[{_SOURCE}] Aviso: no se pudo leer la página del Centro ({e})")
        if enlace is None:
            avisar(f"[{_SOURCE}] Aviso: no se encontró el enlace de laudos en la página del Centro; se usa el enlace conocido")
            enlace = _ENLACE_CONOCIDO

        try:
            # Deja la cookie FedAuth en la sesión.
            abierto = session.get(enlace, timeout=60)
            abierto.raise_for_status()
            sitio, raiz = _sitio_y_raiz(abierto.url)
            carpeta_raiz = _listar(session, sitio, raiz)
        except (requests.RequestException, ValueError) as e:
            avisar(f"[{_SOURCE}] Error abriendo la carpeta compartida de laudos: {e}")
            return docs

        entradas: List[_Entrada] = []
        for archivo in carpeta_raiz.get("Files") or []:
            entradas.append(_Entrada(carpeta="", archivo=archivo))
        for carpeta in carpeta_raiz.get("Folders") or []:
            if cancelado():
                return docs
            nombre = carpeta.get("Name", "")
            if nombre == "Forms":  # interna de SharePoint
                continue
            try:
                contenido = _listar(session, sitio, carpeta["ServerRelativeUrl"])
            except (requests.RequestException, ValueError, KeyError) as e:
                avisar(f"[{_SOURCE}] Error consultando la carpeta {nombre}: {e}")
                continue
            for archivo in contenido.get("Files") or []:
                entradas.append(_Entrada(carpeta=nombre, archivo=archivo))

        for e in _titular(entradas, avisar):
            if cancelado():
                return docs[:limit]
            iso = e.fecha.isoformat()
            if iso < fini or iso > ffin:
                continue
            if e.sin_fecha:
                avisar(f"[{_SOURCE}] Aviso: '{e.nombre}' (carpeta {e.carpeta}) sin fecha en el nombre; "
                       f"se usa {iso} y queda como {e.titulo}")
            elif e.unverified:
                avisar(f"[{_SOURCE}] Aviso: '{e.nombre}' con fecha ilegible; se usa {iso} ({e.titulo})")
            if e.repetida:
                avisar(f"[{_SOURCE}] Aviso: otro laudo con la misma fecha; queda como {e.titulo}")
            anio_carpeta = _anio_carpeta(e.carpeta)
            if anio_carpeta is not None and anio_carpeta != e.fecha.year:
                avisar(f"[{_SOURCE}] Aviso: '{e.nombre}' está en la carpeta {e.carpeta} pero su fecha es {iso}")

            uid = e.archivo.get("UniqueId")
            if not uid:
                avisar(f"[{_SOURCE}] Aviso: '{e.nombre}' sin identificador en SharePoint, se omite")
                continue
            docs.append(RawDocModel(
                source=_SOURCE,
                link={
                    "url": f"{sitio}/_layouts/15/download.aspx?UniqueId={uid}",
                    "method": "sharepoint_compartido",
                    "compartido": enlace,
                },
                title=e.titulo,
                tipo=_TIPO,
                f_public=iso,
                f_providencia=iso,
                detalle=_partes(e.nombre) or None,
                title_unverified=e.unverified,
                save_path=storage_path(_SOURCE, iso, _TIPO, f"{e.titulo}(extension)"),
            ))
            if len(docs) >= limit:
                return docs[:limit]
        return docs[:limit]
