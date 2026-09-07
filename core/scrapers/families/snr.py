import datetime
import re
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.fecha_es import parse_fecha_providencia_es
from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE = "https://www.supernotariado.gov.co/transparencia/normatividad"
_SOURCE = "Superintendencia de Notariado y Registro"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_UMBRAL = 18
_ANIO_MIN = 2015

# (segmento de URL de la categoría, tipo mostrado, letra del código de título)
_CATEGORIAS = [
    ("circulares", "Circular", "C"),
    ("Resoluciones", "Resolución", "R"),
]

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_CODIGO_RE = re.compile(r"\b(CIR|RES)-(\d{4})-(\d{6})-\d\b")
_RESULTADOS_RE = re.compile(r"Resultados\s*([\d.,]+)")
_PUB_RE = re.compile(r"Publicaci[oó]n:\s*(\d{4}-\d{2}-\d{2})")


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _parse_codigo(texto: str) -> Optional[Tuple[str, int, int]]:
    m = _CODIGO_RE.search(texto or "")
    if not m:
        return None
    letra = "C" if m.group(1) == "CIR" else "R"
    return letra, int(m.group(3)), int(m.group(2))


def _titulo(codigo: Optional[Tuple[str, int, int]], texto_crudo: str) -> Tuple[str, bool]:
    if codigo is None:
        return ((texto_crudo or "").strip() or "documento")[:120], True
    letra, numero, anio = codigo
    return f"{letra}_SNR_{numero:04d}_{anio}", False


def _resultados_total(html: str) -> int:
    m = _RESULTADOS_RE.search(html or "")
    if not m:
        return -1
    return int(m.group(1).replace(".", "").replace(",", ""))


def _tarjetas(html: str) -> Tuple[List[dict], int]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: List[dict] = []
    sin_pdf = 0
    for li in soup.select("ul.docs_download > li"):
        cont = li.select_one("div.contenido_download")
        if cont is None:
            continue
        a = cont.find("a", href=True)
        if a is None:
            sin_pdf += 1
            continue
        mpub = _PUB_RE.search(cont.get_text(" ", strip=True))
        out.append({
            "titulo_txt": a.get_text(" ", strip=True),
            "publicacion": mpub.group(1) if mpub else None,
            "pdf_url": a["href"].strip(),
        })
    return out, sin_pdf


def _tarjeta_a_doc(tarjeta, tipo, fini, ffin, on_progress) -> Optional[RawDocModel]:
    titulo_txt = tarjeta.get("titulo_txt") or ""
    fecha = parse_fecha_providencia_es(titulo_txt)
    if fecha is None and tarjeta.get("publicacion"):
        try:
            fecha = datetime.date.fromisoformat(tarjeta["publicacion"])
        except ValueError:
            fecha = None
    if fecha is None:
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: tarjeta sin fecha parseable «{titulo_txt[:70]}», se omite")
        return None
    if fecha.year < _ANIO_MIN:
        return None
    iso = fecha.isoformat()
    if iso < fini or iso > ffin:
        return None

    codigo = _parse_codigo(titulo_txt)
    title, unverified = _titulo(codigo, titulo_txt)
    safe = _safe_title(title)
    return RawDocModel(
        source=_SOURCE,
        link={"url": urljoin(_BASE, tarjeta["pdf_url"]), "method": "GET"},
        title=title,
        tipo=tipo,
        f_public=iso,
        f_providencia=iso,
        detalle=titulo_txt or None,
        save_path=storage_path(_SOURCE, iso, tipo, f"{safe}(extension)"),
        title_unverified=unverified,
    )


def _buscar(session: requests.Session, categoria: str, termino: str) -> Tuple[int, str]:
    resp = session.post(f"{_BASE}/{categoria}/", data={"r": termino}, timeout=200)
    resp.raise_for_status()
    return _resultados_total(resp.text), resp.text


def _enumerar_categoria(session, categoria, letra, fini, ffin, stop_event, on_progress) -> List[dict]:
    tipo_code = "CIR" if letra == "C" else "RES"
    anio_ini = max(_ANIO_MIN, int(fini[:4]))
    anio_fin = int(ffin[:4])
    por_url: dict = {}

    def _add(cards):
        for c in cards:
            por_url.setdefault(c["pdf_url"], c)

    for anio in range(anio_ini, anio_fin + 1):
        if stop_event is not None and stop_event.is_set():
            return list(por_url.values())
        try:
            total, html = _buscar(session, categoria, str(anio))
        except Exception as e:
            if on_progress:
                on_progress(f"[{_SOURCE}] Error consultando {categoria} {anio}: {e}")
            continue
        cards, _ = _tarjetas(html)
        if len(cards) > _UMBRAL or (total >= 0 and len(cards) >= total):
            _add(cards)
            continue

        def _bloque(pref: str):
            if stop_event is not None and stop_event.is_set():
                return
            termino = f"{tipo_code}-{anio}-{pref}"
            try:
                t, h = _buscar(session, categoria, termino)
            except Exception as e:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Error consultando {categoria} {termino}: {e}")
                return
            if t == 0:
                return
            cs, _ = _tarjetas(h)
            if t <= _UMBRAL or (t >= 0 and len(cs) >= t):
                _add(cs)
                return
            if len(pref) >= 5:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Aviso: bloque {termino} con {t} > {_UMBRAL}, posible corte")
                _add(cs)
                return
            for d in "0123456789":
                _bloque(pref + d)

        for d in "0123456789":
            _bloque(d)

    return list(por_url.values())
