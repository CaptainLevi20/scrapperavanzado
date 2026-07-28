import re
from typing import List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE_URL = "https://www.anh.gov.co"
_LIST_URL = f"{_BASE_URL}/es/normatividad2/normatividad/"

_MESES = {
    "ENERO": "01", "FEBRERO": "02", "MARZO": "03", "ABRIL": "04",
    "MAYO": "05", "JUNIO": "06", "JULIO": "07", "AGOSTO": "08",
    "SEPTIEMBRE": "09", "OCTUBRE": "10", "NOVIEMBRE": "11", "DICIEMBRE": "12",
}
_DATE_PATTERN = re.compile(
    r"(\d{1,2})\s+DE[L]?\s+(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO"
    r"|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)\s+DE[L]?\s+(\d{4})",
    re.IGNORECASE,
)
_MAX_PAGINAS = 60


def _parse_fecha(text: str):
    m = _DATE_PATTERN.search(text.upper())
    if m:
        day = m.group(1).zfill(2)
        month = _MESES[m.group(2).upper()]
        year = int(m.group(3))
        if 1990 <= year <= 2100:
            return f"{year}-{month}-{day}"
    return None


@register_family("anh")
class ScrapANH(BaseScrapper):
    def __init__(self):
        self.source = "Agencia Nacional de Hidrocarburos"

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        docs = []

        for pagina in range(1, _MAX_PAGINAS + 1):
            if stop_event is not None and stop_event.is_set():
                return docs
            if on_progress:
                on_progress(f"[{self.source}] Página {pagina}...")

            params = {"start_date": fini, "end_date": ffin, "page": pagina}
            try:
                resp = session.get(_LIST_URL, params=params, timeout=30)
                resp.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{self.source}] Error en página {pagina}: {e}")
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            table = soup.find("table")
            if not table:
                break
            rows = table.find_all("tr")[1:]  # saltar encabezado
            if not rows:
                break

            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 6:
                    continue

                tipo = cells[1].get_text(strip=True)
                numero = cells[2].get_text(strip=True)
                fecha_txt = cells[3].get_text(strip=True)
                descripcion = cells[4].get_text(" ", strip=True)

                f_public = _parse_fecha(fecha_txt)
                if not f_public:
                    continue

                a_descargar = cells[5].find("a", string=lambda s: s and "descargar" in s.lower())
                if not a_descargar or not a_descargar.get("href"):
                    continue
                url = urljoin(_BASE_URL, a_descargar["href"])

                anio = f_public[:4]
                titulo = f"{tipo} {numero} de {anio}"

                docs.append(RawDocModel(
                    source=self.source,
                    link={"url": url, "method": "GET"},
                    title=titulo,
                    tipo=tipo,
                    detalle=descripcion or None,
                    f_public=f_public,
                    save_path=storage_path(self.source, f_public, tipo, "(filename)(extension)"),
                ))
                if len(docs) >= limit:
                    return docs[:limit]

            pagination = soup.find("ul", class_="pagination")
            if pagination is None:
                break
            paginas_disponibles = [
                a.get_text(strip=True) for a in pagination.find_all("a", class_="page-link")
                if a.get_text(strip=True).isdigit()
            ]
            if not paginas_disponibles or pagina >= int(max(paginas_disponibles)):
                break
        else:
            # The loop ran through all _MAX_PAGINAS iterations without ever
            # hitting one of the natural stop conditions above — meaning page
            # _MAX_PAGINAS itself still pointed at further pages. Silently
            # capping here would drop whatever comes after page _MAX_PAGINAS
            # with no trace of it ever happening.
            if on_progress:
                on_progress(
                    f"[{self.source}] Error: se alcanzó el tope de {_MAX_PAGINAS} páginas con más "
                    "resultados pendientes; puede haber documentos sin recoger."
                )

        return docs
