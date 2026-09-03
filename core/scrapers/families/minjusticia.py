import re
from typing import List, Optional
from urllib.parse import urljoin

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.naming import codigo_ley_decreto
from core.utils import storage_path

_BASE_URL = "https://www.minjusticia.gov.co"
_SITE_URL = f"{_BASE_URL}/normatividad-co"

# lista de SharePoint -> (tipo mostrado, letra del código de título)
_LISTAS = {
    "Decretos": ("Decreto", "D"),
    "Resoluciones": ("Resolucion", "R"),
    "Circulares": ("Circular", "C"),
}

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')

_NUMERO_PATTERN = re.compile(r"\d+")
# Código de radicado interno de las Circulares (ej. "MJD-CIR26-0000002-SCF-30320"),
# a veces sin el prefijo "MJD-". No siempre presente en el título -> ver
# fallback title_unverified.
_CODIGO_CIRCULAR_PATTERN = re.compile(r"CIR\d{2}-\d+")


def _normalize_title(letra: str, numero: str, anio: str) -> str:
    if letra == "C":
        return f"C_MJ_{numero}_{anio}"
    return codigo_ley_decreto(letra, numero, anio) or f"{letra}_MJ_{int(numero):04d}_{anio}"


def _extraer_items(
    session: requests.Session, lista: str, tipo: str, letra: str, fini: str, ffin: str, source: str, on_progress=None
) -> List[RawDocModel]:
    docs: List[RawDocModel] = []
    url = f"{_SITE_URL}/_api/web/lists/getbytitle('{lista}')/items"
    params = {
        "$filter": f"MJFechaExpedicion ge datetime'{fini}T00:00:00Z' and MJFechaExpedicion le datetime'{ffin}T23:59:59Z'",
        "$select": "Title,MJDescripcion,MJFechaExpedicion,File/ServerRelativeUrl,File/Name",
        "$expand": "File",
        "$top": "5000",
    }
    headers = {"Accept": "application/json;odata=verbose"}

    while url is not None:
        try:
            resp = session.get(url, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            if on_progress:
                on_progress(f"[{source}] Error consultando {lista}: {e}")
            return docs

        payload = resp.json()["d"]
        for item in payload.get("results", []):
            file_info = item.get("File")
            if not file_info or not file_info.get("ServerRelativeUrl"):
                if on_progress:
                    on_progress(f"[{source}] Aviso: no se encontró archivo para «{item.get('Title')}», se omite")
                continue

            titulo_sitio = (item.get("Title") or "").strip()
            f_providencia = (item.get("MJFechaExpedicion") or "")[:10] or None
            if f_providencia is None:
                if on_progress:
                    on_progress(f"[{source}] Aviso: sin MJFechaExpedicion para «{titulo_sitio}», se omite")
                continue

            detalle_raw = item.get("MJDescripcion")
            detalle = detalle_raw.strip() if detalle_raw and detalle_raw.strip() not in ("", ".") else None

            if letra == "C":
                codigo_match = _CODIGO_CIRCULAR_PATTERN.search(titulo_sitio)
                numero = codigo_match.group(0) if codigo_match else None
            else:
                numero_match = _NUMERO_PATTERN.search(titulo_sitio)
                numero = numero_match.group(0) if numero_match else None

            if numero is not None:
                title = _normalize_title(letra, numero, f_providencia[:4])
                title_unverified = False
            else:
                title = titulo_sitio
                title_unverified = True

            url_pdf = urljoin(_BASE_URL, file_info["ServerRelativeUrl"])
            safe_title = _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")

            docs.append(RawDocModel(
                source=source,
                link={"url": url_pdf, "method": "GET"},
                title=title,
                tipo=tipo,
                f_public=f_providencia,
                f_providencia=f_providencia,
                detalle=detalle,
                save_path=storage_path(source, f_providencia, tipo, f"{safe_title}(extension)"),
                title_unverified=title_unverified,
            ))

        next_url = payload.get("__next")
        url = next_url
        params = None  # __next ya trae los query params codificados

    return docs


@register_family("minjusticia")
class ScrapMinJusticia(BaseScrapper):
    def __init__(self):
        self.source = "Ministerio de Justicia y del Derecho"

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        docs: List[RawDocModel] = []
        for lista, (tipo, letra) in _LISTAS.items():
            if stop_event is not None and stop_event.is_set():
                return docs
            if len(docs) >= limit:
                return docs[:limit]
            if on_progress:
                on_progress(f"[{self.source}] Procesando {tipo}...")

            docs.extend(_extraer_items(session, lista, tipo, letra, fini, ffin, self.source, on_progress=on_progress))

        return docs[:limit]
