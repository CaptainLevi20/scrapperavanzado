import datetime
import re
import unicodedata
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.fecha_es import parse_fecha_providencia_es
from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE = "https://www.supervigilancia.gov.co"
_SOURCE = "Superintendencia de Vigilancia y Seguridad Privada"
_ANIO_MINIMO = 2015
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "es-CO,es;q=0.9"}

# (url de la página 1 del listado, tipo asignado, prefijo de título)
_SECCIONES = [
    (f"{_BASE}/2-1-3-2-resoluciones", "Resolución", "R"),
    (f"{_BASE}/2-1-3-8-conceptos-juridicos", "Concepto", "CTO"),
]
# Sólo Resoluciones pagina; Conceptos es una sola página.
_PAGINA_TOPE = 20

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_ID_RE = re.compile(r"/web/content/(\d+)")
_NUM_CS_ANY = re.compile(r"(\d{6,}CS)", re.I)
_NUM_CS_INICIO = re.compile(r"^\s*(\d{6,}CS)\b", re.I)
_NUM_PROSA = re.compile(r"resoluci[oó]n\s+(?:n[o°º]\.?\s*|n[uú]mero\s*)?(\d{4,})", re.I)
_FECHA_RE = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})\b")
_PDF_SUFIJO = re.compile(r"\.pdf$", re.I)


def _norm_texto(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "").replace("​", "")
    return re.sub(r"\s+", " ", s).strip()


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title or "")[:120].strip(" .")


def _id_de_href(href: str) -> Optional[str]:
    m = _ID_RE.search(href or "")
    return m.group(1) if m else None


def _num_en_texto(texto: str) -> Optional[str]:
    m = _NUM_CS_ANY.search(texto or "")
    return m.group(1).upper() if m else None


def _num_al_inicio(texto: str) -> Optional[str]:
    m = _NUM_CS_INICIO.match(texto or "")
    return m.group(1).upper() if m else None


def _num_en_prosa(texto: str) -> Optional[str]:
    m = _NUM_PROSA.search(unicodedata.normalize("NFC", texto or ""))
    return m.group(1) if m else None


def _fecha_de_meta(meta: str) -> Optional[datetime.date]:
    # "Hoy" / "Hace 5 días" no se toman como fecha: el sitio los pone como texto
    # fijo incluso en resoluciones de 2007 (listado /2-1-normativa-resoluciones).
    m = _FECHA_RE.search(meta or "")
    if m:
        dd, mm, yyyy = (int(x) for x in m.groups())
        try:
            return datetime.date(yyyy, mm, dd)
        except ValueError:
            return None
    # Las filas de 2018-2022 traen la fecha en palabras ("27 de julio de 2020").
    escrita = parse_fecha_providencia_es(meta or "")
    if escrita:
        return escrita
    return None


def _titulo(
    pref: str,
    numero: Optional[str],
    anio: int,
    texto_crudo: str,
    filename_stem: Optional[str],
) -> Tuple[str, bool]:
    if numero:
        return f"{pref}_SVySP_{numero}_{anio}", False
    base = _PDF_SUFIJO.sub("", _norm_texto(texto_crudo))
    if not base and filename_stem:
        base = _PDF_SUFIJO.sub("", _norm_texto(filename_stem))
    return (base or "documento")[:120], True


_FILENAME_RE = re.compile(r'filename="?([^"\r\n;]+)"?', re.I)


def _head_info(session: requests.Session, url: str) -> dict:
    try:
        resp = session.head(url, timeout=30, allow_redirects=True)
    except requests.RequestException:
        return {"filename": None, "content_length": None}
    disp = resp.headers.get("Content-Disposition", "")
    m = _FILENAME_RE.search(disp)
    filename = m.group(1).strip() if m else None
    raw_len = resp.headers.get("Content-Length", "")
    content_length = int(raw_len) if raw_len.isdigit() else None
    return {"filename": filename, "content_length": content_length}


def _texto(item, sel: str) -> str:
    node = item.select_one(sel)
    return _norm_texto(node.get_text(" ", strip=True)) if node else ""


def _fila_a_doc(item, tipo, pref, head_info, fini, ffin, on_progress) -> Optional[RawDocModel]:
    href = item.get("data-href") or ""
    if not href:
        btn = item.select_one("a.s_dl_btn_download")
        href = btn.get("href", "") if btn else ""
    doc_id = _id_de_href(href)
    if not doc_id:
        return None

    nombre_txt = _texto(item, ".s_dl_doc_name")
    meta_txt = _texto(item, ".s_dl_doc_meta")

    fecha = _fecha_de_meta(meta_txt)
    if fecha is None:
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: {tipo} sin fecha «{nombre_txt[:70]}», se omite")
        return None
    if fecha.year < _ANIO_MINIMO:
        return None
    iso = fecha.isoformat()
    if iso < fini or iso > ffin:
        return None

    filename = head_info.get("filename") or ""
    numero = _num_en_texto(filename) or _num_en_texto(nombre_txt) or _num_al_inicio(nombre_txt) or _num_en_prosa(nombre_txt)
    filename_stem = filename.rsplit(".", 1)[0] or None if filename else None
    title, unverified = _titulo(pref, numero, fecha.year, nombre_txt, filename_stem)
    safe = _safe_title(title)

    return RawDocModel(
        source=_SOURCE,
        link={"url": f"{_BASE}/web/content/{doc_id}?download=true", "method": "GET"},
        title=title,
        tipo=tipo,
        f_public=iso,
        f_providencia=iso,
        detalle=nombre_txt or None,
        save_path=storage_path(_SOURCE, iso, tipo, f"{safe}(extension)"),
        title_unverified=unverified,
    )


def _pagina_items(session, url: str, on_progress) -> Optional[list]:
    """Devuelve la lista de items de una página, o None si la petición falló."""
    try:
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        if on_progress:
            on_progress(f"[{_SOURCE}] Error consultando {url}: {e}")
        return None
    return BeautifulSoup(resp.text, "html.parser").select("div.s_dl_item")


def _items_de_listado(session, url_pagina1: str, pagina: bool, on_progress) -> list:
    items = _pagina_items(session, url_pagina1, on_progress)
    if not items:
        return []
    todos = list(items)
    if not pagina:
        return todos
    for n in range(2, _PAGINA_TOPE + 1):
        pagina_items = _pagina_items(session, f"{url_pagina1}-pagina{n:02d}", on_progress)
        if not pagina_items:
            break
        todos.extend(pagina_items)
    return todos


@register_family("supervigilancia")
class ScrapSupervigilancia(BaseScrapper):
    # Muchas filas sólo traen la fecha de expedición, que puede ir semanas
    # antes de que suban el archivo; el listado se recorre entero en cada
    # corrida, así que mirar un mes atrás no cuesta peticiones extra.
    scheduled_min_lookback_days = 30

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update(_HEADERS)  # TLS válido: sin verify=False
        docs: List[RawDocModel] = []
        vistos_id: set = set()
        vistos_archivo: set = set()

        for url, tipo, pref in _SECCIONES:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            if on_progress:
                on_progress(f"[{_SOURCE}] Procesando {tipo}...")
            items = _items_de_listado(session, url, pref == "R", on_progress)

            for item in items:
                if stop_event is not None and stop_event.is_set():
                    return docs[:limit]
                doc_id = _id_de_href(item.get("data-href") or "")
                if not doc_id or doc_id in vistos_id:
                    continue
                vistos_id.add(doc_id)

                head = _head_info(session, f"{_BASE}/web/content/{doc_id}?download=true")
                clave = (head["content_length"], head["filename"])
                if clave[0] is not None:
                    if clave in vistos_archivo:
                        if on_progress:
                            on_progress(f"[{_SOURCE}] Aviso: {tipo} {doc_id} es el mismo archivo que otro ya visto, se omite")
                        continue
                    vistos_archivo.add(clave)

                doc = _fila_a_doc(item, tipo, pref, head, fini, ffin, on_progress)
                if doc is None:
                    continue
                docs.append(doc)
                if len(docs) >= limit:
                    return docs[:limit]

        return docs[:limit]
