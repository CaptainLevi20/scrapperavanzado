import re
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE_URL = "https://www.minagricultura.gov.co"

# slug de categoría -> (tipo mostrado, letra del código de título)
_CATEGORIAS = {
    "leyes": ("Ley", "L"),
    "decretos": ("Decreto", "D"),
    "resoluciones": ("Resolución", "R"),
    "conpes": ("Conpes", "CONPES"),
}

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_MESES_ALT = "|".join(_MESES.keys())

# Nivel 1: "{dia} [DE] {mes} DE[L] {año}" — el sitio a veces omite el "DE"
# entre día y mes ("DEL 27 JULIO DE 2026") y a veces lo incluye ("DEL 15 DE
# JULIO DEL 2026"); ambas formas comparten este patrón porque "DE" es opcional.
_FECHA_DIA_MES_ANIO = re.compile(
    rf"(\d{{1,2}})\s+(?:DE\s+)?({_MESES_ALT})\s+DEL?\s+(\d{{4}})\s*$", re.IGNORECASE
)
# Nivel 2: "DE {mes} {dia} DE {año}" — orden mes-día invertido, visto en
# Resoluciones ("DE MAYO 4 DE 2026").
_FECHA_MES_DIA_ANIO = re.compile(
    rf"DE\s+({_MESES_ALT})\s+(\d{{1,2}})\s+DE\s+(\d{{4}})\s*$", re.IGNORECASE
)
# Nivel 3: "DE {mes} DE {año}" — mes y año sin día (ej. Leyes: "DE OCTUBRE DE 2023").
_FECHA_MES_ANIO = re.compile(rf"DE\s+({_MESES_ALT})\s+DE\s+(\d{{4}})\s*$", re.IGNORECASE)
# Nivel 4: "DE {año}" — solo año. Siempre es el caso de Conpes.
_FECHA_ANIO = re.compile(r"DE\s+(\d{4})\s*$", re.IGNORECASE)


def _resto_tras_numero(data_title: str, numero: str) -> str:
    idx = data_title.find(numero)
    if idx == -1:
        return data_title
    return data_title[idx + len(numero):]


def _normalize_title(letra: str, numero: str, anio: str) -> str:
    return f"{letra}_MADR_{int(numero):04d}_{anio}"


def _parse_fecha(texto: str) -> Optional[str]:
    m = _FECHA_DIA_MES_ANIO.search(texto)
    if m:
        dia, mes_nombre, anio = m.groups()
        if 1 <= int(dia) <= 31:
            return f"{anio}-{_MESES[mes_nombre.lower()]:02d}-{int(dia):02d}"

    m = _FECHA_MES_DIA_ANIO.search(texto)
    if m:
        mes_nombre, dia, anio = m.groups()
        if 1 <= int(dia) <= 31:
            return f"{anio}-{_MESES[mes_nombre.lower()]:02d}-{int(dia):02d}"

    m = _FECHA_MES_ANIO.search(texto)
    if m:
        mes_nombre, anio = m.groups()
        return f"{anio}-{_MESES[mes_nombre.lower()]:02d}-01"

    m = _FECHA_ANIO.search(texto)
    if m:
        return f"{m.group(1)}-01-01"

    return None


@register_family("madr")
class ScrapMADR(BaseScrapper):
    def __init__(self):
        self.source = "Ministerio de Agricultura y Desarrollo Rural"

    def _extraer_articulos(self, html: str, tipo: str, letra: str, fini: str, ffin: str, on_progress=None) -> List[RawDocModel]:
        docs: List[RawDocModel] = []
        soup = BeautifulSoup(html, "html.parser")

        for art in soup.find_all("article", class_="item_norm"):
            data_title = (art.get("data-title") or "").strip()
            numero = (art.get("data-number") or "").strip()
            detalle = (art.get("data-info") or "").strip() or None
            if detalle:
                detalle = detalle.strip('"')

            enlace = art.find("a", href=True)
            if not enlace:
                continue
            url = urljoin(_BASE_URL, enlace["href"])

            resto = _resto_tras_numero(data_title, numero) if numero else data_title
            fecha = _parse_fecha(resto)
            if fecha is None:
                if on_progress:
                    on_progress(f"[{self.source}] Aviso: no se pudo determinar fecha para «{data_title}», se omite")
                continue
            if fecha < fini or fecha > ffin:
                continue

            if numero:
                title = _normalize_title(letra, numero, fecha[:4])
                title_unverified = False
            else:
                title = data_title
                title_unverified = True

            safe_title = _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")

            docs.append(RawDocModel(
                source=self.source,
                link={"url": url, "method": "GET"},
                title=title,
                tipo=tipo,
                f_public=fecha,
                detalle=detalle,
                save_path=storage_path(self.source, fecha, tipo, f"{safe_title}(extension)"),
                title_unverified=title_unverified,
            ))

        return docs

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        docs: List[RawDocModel] = []
        for categoria, (tipo, letra) in _CATEGORIAS.items():
            if stop_event is not None and stop_event.is_set():
                return docs
            if on_progress:
                on_progress(f"[{self.source}] Procesando {tipo}...")

            try:
                resp = session.get(f"{_BASE_URL}/normatividad/{categoria}", timeout=30)
                resp.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{self.source}] Error consultando {categoria}: {e}")
                continue

            docs.extend(self._extraer_articulos(resp.text, tipo, letra, fini, ffin, on_progress=on_progress))
            if len(docs) >= limit:
                return docs[:limit]

        return docs
