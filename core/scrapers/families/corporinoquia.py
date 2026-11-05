import datetime
import re
from typing import Iterator, List, Optional

import requests
from bs4 import BeautifulSoup, Comment, NavigableString

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

# Página Joomla (SP Page Builder) con un acordeón por año; cada acuerdo es un
# enlace a Google Drive pegado a mano en un bloque de texto. Las resoluciones
# (sistema ScriptCase) no responden y quedan para una segunda entrega.
_URL = "https://corporinoquia.gov.co/participacion-ciudadana/acuerdos-aprobados-por-el-consejo-directivo.html"
_SOURCE = "Corporación Autónoma Regional de la Orinoquía"
_SIGLA = "CORPORINOQUIA"
_TIPO = "Acuerdo"
_PREF = "A"
_ANIO_MINIMO = 2025
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "es-CO,es;q=0.9"}
_DRIVE_DESCARGA = "https://drive.google.com/uc?export=download&id={}"

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_DRIVE_RE = re.compile(r"drive\.google\.com/file/d/([\w-]+)")
# 200.3-2-26-001, 200.3.2.26.007, 200.3.2-25-006: separadores mezclados.
_CODIGO_RE = re.compile(r"200\.3[.\-]2[.\-](\d{2})[.\-](\d{1,3})(?!\d)")
# "05 ENERO 2026", "DE FECHA 27 DE JULIO DE 2026", "08 DE ABRIL 2025".
_FECHA_RE = re.compile(
    r"(?<!\d)(\d{1,2})\s+(?:de\s+)?(" + "|".join(_MESES) + r")\s+(?:de\s+)?(\d{4})", re.I
)
# Fecha-hora de publicación que sigue a la referencia ("29/01/2026  14:50").
_PUBLICACION_RE = re.compile(r"\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{4}")


def _norm_texto(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _fecha(texto: str) -> Optional[datetime.date]:
    m = _FECHA_RE.search(texto or "")
    if not m:
        return None
    try:
        return datetime.date(int(m.group(3)), _MESES[m.group(2).lower()], int(m.group(1)))
    except ValueError:
        return None


def _titulo(numero: int, anio: int) -> str:
    return f"{_PREF}_{_SIGLA}_{numero:04d}_{anio}"


def _referencia(texto: str) -> str:
    """Texto entre el enlace y la fecha-hora de publicación, sin comillas ni
    separadores sueltos en los extremos."""
    texto = _PUBLICACION_RE.split(texto or "", maxsplit=1)[0]
    return _norm_texto(texto).strip(" ,-\"“”'")


def _dentro_de_enlace(nodo) -> bool:
    return any(p.name == "a" for p in nodo.parents)


# Texto que nunca es parte de la descripción de un acuerdo.
_ETIQUETAS_SIN_TEXTO = {"script", "style", "noscript", "template"}
# Bloque que contiene el enlace: la descripción solo toma texto de ese bloque.
_BLOQUES = {"p", "li", "td", "div"}


def _bloque(nodo):
    return next((p for p in nodo.parents if p.name in _BLOQUES), None)


def _texto_visible(nodo) -> bool:
    if isinstance(nodo, Comment):
        return False
    return not any(p.name in _ETIQUETAS_SIN_TEXTO for p in nodo.parents)


def _enlaces(html: str) -> Iterator[dict]:
    """Enlaces a Drive en orden de documento, con el texto que los sigue hasta
    el próximo enlace. El editor anida a veces el acuerdo siguiente dentro de
    un <em>, así que se recorre el árbol plano y no los hermanos.

    El "resto" (la descripción) solo toma texto visible del mismo bloque del
    enlace (<p>, <li>, <td> o <div>): sin ese límite, el último acuerdo de la
    página arrastraba el título del acordeón siguiente, el pie de página y el
    código de la página (revisión del PR #110)."""
    soup = BeautifulSoup(html, "html.parser")
    actual = None
    for nodo in soup.descendants:
        if getattr(nodo, "name", None) == "a":
            m = _DRIVE_RE.search(nodo.get("href") or "")
            texto = _norm_texto(nodo.get_text(" ", strip=True))
            if m and texto:
                if actual:
                    yield actual
                actual = {"drive_id": m.group(1), "texto": texto, "resto": "", "bloque": _bloque(nodo)}
            elif m and actual:
                # Enlace vacío que deja el editor (<a href="…"><br /></a>):
                # corta la referencia del anterior.
                yield actual
                actual = None
        elif (
            isinstance(nodo, NavigableString)
            and actual
            and not _dentro_de_enlace(nodo)
            and _texto_visible(nodo)
            and (actual["bloque"] is None or actual["bloque"] in nodo.parents)
        ):
            actual["resto"] += str(nodo)
    if actual:
        yield actual


def _enlace_a_doc(enlace: dict, fini: str, ffin: str, hoy: datetime.date, on_progress) -> Optional[RawDocModel]:
    texto = enlace["texto"]
    codigo = _CODIGO_RE.search(texto)
    fecha = _fecha(texto)
    if codigo is None:
        if fecha is not None and fecha.year >= _ANIO_MINIMO and on_progress:
            on_progress(f"[{_SOURCE}] Aviso: acuerdo sin código 200.3 ({texto}), se omite")
        return None
    anio_codigo = 2000 + int(codigo.group(1))
    if fecha is None:
        # Los de 2024 y antes traen a veces el código sin fecha; sólo se avisa
        # desde el piso.
        if anio_codigo >= _ANIO_MINIMO and on_progress:
            on_progress(f"[{_SOURCE}] Aviso: acuerdo {texto} sin fecha legible, se omite")
        return None
    if fecha > hoy and on_progress:
        on_progress(f"[{_SOURCE}] Aviso: acuerdo {texto} con fecha futura {fecha.strftime('%d/%m/%Y')}")
    if fecha.year < _ANIO_MINIMO:
        return None
    iso = fecha.isoformat()
    if iso < fini or iso > ffin:
        return None
    if anio_codigo != fecha.year and on_progress:
        on_progress(f"[{_SOURCE}] Aviso: acuerdo {texto}: el año del código no coincide con la fecha, se usa {fecha.year}")

    title = _titulo(int(codigo.group(2)), fecha.year)
    return RawDocModel(
        source=_SOURCE,
        link={"url": _DRIVE_DESCARGA.format(enlace["drive_id"]), "method": "GET"},
        title=title,
        tipo=_TIPO,
        f_public=iso,
        f_providencia=iso,
        detalle=_referencia(enlace["resto"]) or None,
        save_path=storage_path(_SOURCE, iso, _TIPO, f"{title}(extension)"),
    )


@register_family("corporinoquia")
class ScrapCorporinoquia(BaseScrapper):
    # Algunos acuerdos se pegan en la página semanas después de su fecha (el
    # 26-001, 24 días). Es una sola página, así que mirar atrás no cuesta.
    scheduled_min_lookback_days = 60

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

        for enlace in _enlaces(resp.content.decode("utf-8", errors="replace")):
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            doc = _enlace_a_doc(enlace, fini, ffin, hoy, on_progress)
            if doc is None:
                continue
            if enlace["drive_id"] in vistos:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Aviso: {doc.title} repite un archivo ya visto, se omite")
                continue
            vistos.add(enlace["drive_id"])
            docs.append(doc)
            if len(docs) >= limit:
                return docs[:limit]

        return docs[:limit]
