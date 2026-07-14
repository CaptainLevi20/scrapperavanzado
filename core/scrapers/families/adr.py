import re
from typing import List

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE_URL = "https://www.adr.gov.co"
_API_PAGES = f"{_BASE_URL}/wp-json/wp/v2/pages"

# Categorías de "Normativa de la entidad" que son páginas planas de WordPress
# (un solo listado de enlaces, sin subdivisión por año)
_CATEGORIAS_PLANAS = {
    "leyes": "Ley",
    "decretos": "Decreto",
    "acuerdos": "Acuerdo",
    "reglamentos": "Reglamento",
    "circulares": "Circular",
    "conceptos-juridicos": "Concepto Jurídico",
    "directivas": "Directiva",
    "covid-19": "Covid-19",
}
# "Resoluciones" es la única categoría dividida en subpáginas por año
# (resoluciones-2016 ... resoluciones-2026), más una subpágina fija de nombramientos
_RESOLUCIONES_SLUGS_FIJOS = ["resoluciones-de-nombramientos"]

_MESES = {
    "ENERO": "01", "FEBRERO": "02", "MARZO": "03", "ABRIL": "04",
    "MAYO": "05", "JUNIO": "06", "JULIO": "07", "AGOSTO": "08",
    "SEPTIEMBRE": "09", "OCTUBRE": "10", "NOVIEMBRE": "11", "DICIEMBRE": "12",
}
# Nivel 1 de precisión: fecha completa embebida en el texto del enlace
# (ej. "Decreto No. 0381 del 07 de abril de 2026")
_FULL_DATE_PATTERN = re.compile(
    r"(\d{1,2})\s+DE[L]?\s+(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO"
    r"|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)\s+DE[L]?\s+(\d{4})",
    re.IGNORECASE,
)
# Nivel 2: solo el año (ej. "LEY 2387 DE 2024", "Acuerdo 001 de 2025")
_YEAR_ONLY_PATTERN = re.compile(r"\bDE[L]?\s+(\d{4})\b", re.IGNORECASE)
# Nivel 3 (último recurso): fecha de subida del archivo, tomada de la ruta
# /wp-content/uploads/YYYY/MM/ — para documentos sin ninguna fecha en el texto
_UPLOAD_DATE_PATTERN = re.compile(r"/uploads/(\d{4})/(\d{2})/")

_PDF_LINK_PATTERN = re.compile(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>([^<]*)</a>', re.IGNORECASE)


def _parse_full_date(text: str):
    m = _FULL_DATE_PATTERN.search(text.upper())
    if m:
        day = m.group(1).zfill(2)
        month = _MESES[m.group(2).upper()]
        year = int(m.group(3))
        if 1990 <= year <= 2100:
            return f"{year}-{month}-{day}"
    return None


def _parse_year_only(text: str):
    m = _YEAR_ONLY_PATTERN.search(text.upper())
    if m and 1990 <= int(m.group(1)) <= 2100:
        return int(m.group(1))
    return None


def _parse_upload_year_month(url: str):
    m = _UPLOAD_DATE_PATTERN.search(url)
    if m:
        return int(m.group(1)), m.group(2)
    return None


@register_family("adr")
class ScrapADR(BaseScrapper):
    def __init__(self):
        self.source = "Agencia de Desarrollo Rural"

    def _fetch_page_content(self, session, slug):
        resp = session.get(_API_PAGES, params={"slug": slug}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        return data[0]["content"]["rendered"]

    def _extraer_documentos(self, html, tipo, fini, ffin):
        docs = []
        if not html:
            return docs

        anio_inicial = int(fini[:4])
        anio_final = int(ffin[:4])

        for href, texto in _PDF_LINK_PATTERN.findall(html):
            texto = texto.strip()
            url = href if href.startswith("http") else f"{_BASE_URL}{href}"

            fecha_completa = _parse_full_date(texto)
            if fecha_completa:
                if fecha_completa < fini or fecha_completa > ffin:
                    continue
                f_public = fecha_completa
            else:
                anio = _parse_year_only(texto)
                mes = "01"
                if anio is None:
                    upload = _parse_upload_year_month(url)
                    if upload is None:
                        continue
                    anio, mes = upload
                if anio < anio_inicial or anio > anio_final:
                    continue
                f_public = f"{anio}-{mes}-01"

            path = storage_path(self.source, f_public, tipo, "(filename)(extension)")

            docs.append(RawDocModel(
                source=self.source,
                link={"url": url, "method": "GET"},
                title=texto or url.rsplit("/", 1)[-1],
                tipo=tipo,
                f_public=f_public,
                save_path=path,
            ))

        return docs

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        docs = []

        for slug, tipo in _CATEGORIAS_PLANAS.items():
            if stop_event is not None and stop_event.is_set():
                return docs
            if on_progress:
                on_progress(f"[{self.source}] Procesando {tipo}...")
            html = self._fetch_page_content(session, slug)
            docs.extend(self._extraer_documentos(html, tipo, fini, ffin))
            if len(docs) >= limit:
                return docs[:limit]

        if stop_event is not None and stop_event.is_set():
            return docs
        if on_progress:
            on_progress(f"[{self.source}] Procesando Resolución...")

        for slug in _RESOLUCIONES_SLUGS_FIJOS:
            html = self._fetch_page_content(session, slug)
            docs.extend(self._extraer_documentos(html, "Resolución", fini, ffin))

        anio_inicial = int(fini[:4])
        anio_final = int(ffin[:4])
        for anio in range(anio_inicial, anio_final + 1):
            if stop_event is not None and stop_event.is_set():
                return docs
            html = self._fetch_page_content(session, f"resoluciones-{anio}")
            docs.extend(self._extraer_documentos(html, "Resolución", fini, ffin))
            if len(docs) >= limit:
                return docs[:limit]

        return docs
