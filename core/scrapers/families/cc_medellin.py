import datetime
import re
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, unquote, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from core.fecha_es import parse_fecha_providencia_es
from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

# Página DNN (módulo EasyDNNnews, plantilla "acordeón") del Centro de
# Conciliación, Arbitraje y Amigable Composición. Todos los años (1999-2026)
# vienen en el HTML de una sola petición: un panel por año y un enlace directo
# a cada PDF. Está detrás de Cloudflare, que hoy deja pasar sin desafío; si un
# día pide JavaScript, la fuente se pausa (guía, paso 2), no se intenta saltar.
_URL = (
    "https://www.camaramedellin.com.co/quiero-un-servicio-para-mi-empresa/"
    "solucion-de-conflictos/arbitraje/laudos-arbitrales"
)
_SOURCE = "Cámara de Comercio de Medellín para Antioquia"
_SIGLA = "CCMA"
_TIPO = "Laudo arbitral"
_PREF = "LA"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "es-CO,es;q=0.9"}

# Ventana de la corrida diaria: más días que los que hay desde el laudo más
# viejo (31-05-1999), es decir, todo el acordeón. Con 10_000 (Armenia) la
# ventana ya no llegaría a 1999. El Centro sube los laudos por tandas, entre 2 y
# 29 meses después de su fecha, y la página entera es una sola petición.
_TODO_EL_ACORDEON_DIAS = 20_000

# Radicado del Centro: AAAA A NNNN (arbitraje) o AAAA AP NNNN (validación de
# acuerdos de recuperación, Decreto 560 de 2020). Separadores y mayúsculas
# varían en los nombres de archivo ("2017-a-0013-…", "Rad_ 2018 A 0018- …",
# "29-de-enero-de-2015-2013-A-034.pdf"). El primer año seguido de A/AP es el
# radicado, nunca el año de una fecha.
_RADICADO_RE = re.compile(r"(?<!\d)(\d{4})[\s_-]*(AP|A)[\s_-]*(\d{1,4})(?!\d)", re.IGNORECASE)
_FECHA_NUMERICA_RE = re.compile(r"(?<!\d)(\d{1,2})-(\d{1,2})-(\d{4})(?!\d)")
_PANEL_RE = re.compile(r"(\d{4})")


Radicado = Tuple[int, str, str]  # (año, "A"|"AP", consecutivo tal cual)


def _norm_texto(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def _radicado(texto: str) -> Optional[Radicado]:
    m = _RADICADO_RE.search(texto or "")
    if not m:
        return None
    return int(m.group(1)), m.group(2).upper(), m.group(3)


def _clave(rad: Radicado) -> Tuple[int, str, int]:
    """Para comparar: el consecutivo como número (2016 A 004 = 2016 A 0004)."""
    return rad[0], rad[1], int(rad[2])


def _rad_texto(rad: Radicado) -> str:
    return f"{rad[0]} {rad[1]} {rad[2]}"


def _titulo(rad: Radicado, anio: int) -> str:
    # El consecutivo va tal cual lo escribe la Cámara (decisión del 2026-11-26);
    # solo se unifican separadores y la letra en mayúscula.
    return f"{_PREF}_{_SIGLA}_{rad[0]}-{rad[1]}-{rad[2]}_{anio}"


def _url_limpia(href: str) -> str:
    """URL absoluta, con la ruta codificada (%20) y sin ?ver=… (sello de versión
    de DNN que el editor no pone siempre: el archivo es el mismo con o sin él, y
    como doc_id = sha1(url + f_public) quitarlo evita duplicados)."""
    p = urlparse(urljoin(_URL, href.strip()))
    return urlunparse((p.scheme, p.netloc, quote(unquote(p.path), safe="/"), "", "", ""))


def _nombre_archivo(url: str) -> str:
    return unquote(urlparse(url).path.rsplit("/", 1)[-1])


def _fecha_encabezado(texto: str) -> Optional[datetime.date]:
    return parse_fecha_providencia_es(texto)


def _fecha_nombre(nombre: str) -> Optional[datetime.date]:
    """Fecha del nombre del PDF: dd-mm-aaaa, o "dd de <mes> de aaaa" con
    guiones o _ en vez de espacios."""
    for m in _FECHA_NUMERICA_RE.finditer(nombre):
        try:
            return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
    return parse_fecha_providencia_es(re.sub(r"[-_]+", " ", nombre), anio_sin_conector=True)


def _filas(html: str, on_progress) -> List[dict]:
    """Una fila por enlace a /Portals/, emparejado con el último encabezado
    (<li> o <strong> exterior) visto antes de él dentro de su panel."""
    soup = BeautifulSoup(html, "html.parser")
    paneles = soup.select("div.acordeon__item")
    if not paneles:
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: no se encontraron los paneles de laudos en la página")
        return []
    filas = []
    for panel in paneles:
        h2 = panel.find("h2")
        m = _PANEL_RE.search(h2.get_text(" ", strip=True) if h2 else "")
        anio_panel = int(m.group(1)) if m else None
        contenido = panel.select_one(".acordeon_content") or panel
        encabezado = ""
        for el in contenido.descendants:
            nombre = getattr(el, "name", None)
            if nombre in ("li", "strong"):
                # Un <strong> dentro de un <li> (o al revés) es parte del mismo
                # encabezado: solo cuenta el elemento exterior.
                if el.find_parent(["li", "strong"]) is None:
                    encabezado = _norm_texto(el.get_text(" ", strip=True))
            elif nombre == "a" and el.get("href") and "/portals/" in el["href"].lower():
                filas.append({
                    "panel": anio_panel,
                    "encabezado": encabezado,
                    "url": _url_limpia(el["href"]),
                    "texto": _norm_texto(el.get_text(" ", strip=True)),
                })
    return filas


def _avisar(on_progress, texto: str) -> None:
    if on_progress:
        on_progress(f"[{_SOURCE}] Aviso: {texto}")


def _elegir_filas(filas: List[dict], on_progress) -> List[dict]:
    """Agrupa las filas por archivo (radicado del nombre del PDF, o la URL si el
    nombre no lo trae) y deja una por grupo. El nombre del archivo dice qué laudo
    es de verdad; el encabezado tiene errores de digitación y enlaces copiados de
    otro laudo. En un grupo de varias filas se queda la primera cuyo encabezado
    coincide con el archivo (o la primera, si ninguna coincide) y las demás se
    omiten con aviso. Una fila sola siempre se queda (enlaces cruzados de 2014)."""
    grupos: "OrderedDict[object, List[dict]]" = OrderedDict()
    for fila in filas:
        fila["rad_archivo"] = _radicado(_nombre_archivo(fila["url"]))
        fila["rad_encabezado"] = _radicado(fila["encabezado"])
        clave = _clave(fila["rad_archivo"]) if fila["rad_archivo"] else fila["url"]
        grupos.setdefault(clave, []).append(fila)

    elegidas = []
    for grupo in grupos.values():
        def coincide(f):
            return (f["rad_archivo"] is not None and f["rad_encabezado"] is not None
                    and _clave(f["rad_archivo"]) == _clave(f["rad_encabezado"]))

        coinciden = [f for f in grupo if coincide(f)]
        elegida = coinciden[0] if coinciden else grupo[0]
        for f in grupo:
            if f is elegida:
                continue
            archivo = _rad_texto(f["rad_archivo"]) if f["rad_archivo"] else _nombre_archivo(f["url"])
            laudo = _rad_texto(f["rad_encabezado"]) if f["rad_encabezado"] else (f["encabezado"] or "sin encabezado")
            if f["url"] != elegida["url"] and coincide(f):
                # Dos PDF distintos con el mismo radicado y ambos encabezados
                # coinciden (laudo + aclaración): se queda el primero.
                _avisar(on_progress, f"el laudo {laudo} tiene otro PDF con el mismo radicado "
                                     f"({_nombre_archivo(f['url'])}), se queda el primero y se omite este")
            else:
                _avisar(on_progress, f"el sitio enlaza el laudo {laudo} al PDF de {archivo}, se omite")
        elegidas.append(elegida)
    return elegidas


def _fecha_fila(fila: dict, rad: Radicado, on_progress) -> Optional[datetime.date]:
    nombre = _nombre_archivo(fila["url"])
    f_enc = _fecha_encabezado(fila["encabezado"])
    f_nom = _fecha_nombre(nombre)
    etiqueta = _rad_texto(rad)
    if f_enc is None:
        if f_nom is None:
            _avisar(on_progress, f"laudo {etiqueta} sin fecha legible, se omite")
            return None
        _avisar(on_progress, f"laudo {etiqueta} sin fecha en el encabezado, se usa la del nombre del archivo")
        return f_nom
    if f_enc.year < rad[0]:
        # Año imposible (error de digitación): un laudo no es anterior a su
        # radicación. Caso real: 2019 A 0087, "12 de agosto de 2010".
        if f_nom is not None and f_nom.year >= rad[0]:
            _avisar(on_progress, f"laudo {etiqueta} con año imposible en el encabezado ({f_enc.isoformat()}), "
                                 f"se usa la fecha del nombre del archivo ({f_nom.isoformat()})")
            return f_nom
        if fila["panel"] and fila["panel"] >= rad[0]:
            try:
                corregida = f_enc.replace(year=fila["panel"])
            except ValueError:  # 29 de febrero
                corregida = datetime.date(fila["panel"], f_enc.month, 28)
            _avisar(on_progress, f"laudo {etiqueta} con año imposible en el encabezado ({f_enc.isoformat()}), "
                                 f"se usa el año del panel ({corregida.isoformat()})")
            return corregida
        _avisar(on_progress, f"laudo {etiqueta} con año imposible en el encabezado ({f_enc.isoformat()}), se omite")
        return None
    if f_nom is not None and f_nom != f_enc:
        _avisar(on_progress, f"laudo {etiqueta}: el encabezado dice {f_enc.isoformat()} y el nombre del "
                             f"archivo {f_nom.isoformat()}; se usa el encabezado")
    return f_enc


def _fila_a_doc(fila: dict, on_progress) -> Optional[RawDocModel]:
    rad_archivo, rad_encabezado = fila["rad_archivo"], fila["rad_encabezado"]
    unverified = False
    if rad_archivo is not None:
        rad = rad_archivo
        if rad_encabezado is None or _clave(rad_encabezado) != _clave(rad_archivo):
            unverified = True
            _avisar(on_progress, f"el encabezado dice {_rad_texto(rad_encabezado) if rad_encabezado else 'otro radicado'} "
                                 f"pero el PDF es {_rad_texto(rad_archivo)}; se usa el del archivo, sin verificar")
    elif rad_encabezado is not None:
        rad = rad_encabezado
        unverified = True
        _avisar(on_progress, f"el nombre del PDF de {_rad_texto(rad)} no trae radicado "
                             f"({_nombre_archivo(fila['url'])}); se usa el del encabezado, sin verificar")
    else:
        _avisar(on_progress, f"laudo sin radicado legible ({fila['encabezado'] or _nombre_archivo(fila['url'])}), se omite")
        return None

    fecha = _fecha_fila(fila, rad, on_progress)
    if fecha is None:
        return None
    iso = fecha.isoformat()
    title = _titulo(rad, fecha.year)

    detalle = fila["texto"]
    if detalle == fila["encabezado"]:
        detalle = ""  # 2014: el texto del enlace repite el encabezado
    detalle = re.sub(r"^partes\s*:\s*", "", detalle, flags=re.IGNORECASE).strip()

    return RawDocModel(
        source=_SOURCE,
        link={"url": fila["url"], "method": "GET"},
        title=title,
        title_unverified=unverified,
        tipo=_TIPO,
        f_public=iso,
        f_providencia=iso,
        detalle=detalle or None,
        save_path=storage_path(_SOURCE, iso, _TIPO, f"{title}(extension)"),
    )


@register_family("cc_medellin")
class ScrapCcMedellin(BaseScrapper):
    # Todo el acordeón llega en una petición y los laudos se suben por tandas,
    # con meses o años de retraso: la corrida diaria lo revisa entero. Sin
    # alerta_margen_dias: con esta ventana no tendría efecto (el aviso de salud
    # sale si pasa un año sin laudos con fecha reciente; aceptado como Armenia).
    scheduled_min_lookback_days = _TODO_EL_ACORDEON_DIAS

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update(_HEADERS)
        docs: List[RawDocModel] = []

        if on_progress:
            on_progress(f"[{_SOURCE}] Procesando {_TIPO}...")
        try:
            resp = session.get(_URL, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as e:
            if on_progress:
                on_progress(f"[{_SOURCE}] Error consultando {_TIPO}: {e}")
            return docs

        # El agrupamiento mira la página entera (no solo el rango): la fila que
        # se omite por enlace copiado depende de las otras filas.
        filas = _elegir_filas(_filas(resp.content.decode("utf-8", errors="replace"), on_progress), on_progress)
        titulos: Dict[str, str] = {}
        for fila in filas:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            doc = _fila_a_doc(fila, on_progress)
            if doc is None:
                continue
            if doc.title in titulos:
                _avisar(on_progress, f"{doc.title} repite el título de otro laudo, se omite")
                continue
            titulos[doc.title] = doc.link["url"]
            if not (fini <= doc.f_public <= ffin):
                continue
            docs.append(doc)
            if len(docs) >= limit:
                return docs[:limit]
        return docs[:limit]
