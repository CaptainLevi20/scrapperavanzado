import re
from typing import List
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE_URL = "https://www.adres.gov.co"
_ALLOWED_DOMAIN = "adres.gov.co"

# Solo las categorías con una tabla real de fecha estructurada (Resoluciones,
# Circulares, Acuerdos). "Proyecto de Acto Administrativo" no tiene fecha en
# ningún lado y "Acción popular"/"Fallos de tutela" están vacías — se dejan fuera.
_CATEGORIAS = {
    "/normativa/resoluciones": "Resolución",
    "/normativa/circulares": "Circular",
    "/normativa/acuerdos": "Acuerdo",
}

_NEXT_LINK_PATTERN = re.compile(r'RefreshPageTo\(event,\s*"([^"]+)"\)')
_FECHA_PATTERN = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
_MAX_PAGINAS_POR_CATEGORIA = 60


@register_family("adres")
class ScrapADRES(BaseScrapper):
    def __init__(self):
        self.source = "Administradora de los Recursos del Sistema General de Seguridad Social en Salud"

    def _es_url_propia(self, url: str) -> bool:
        try:
            return _ALLOWED_DOMAIN in urlparse(url).netloc
        except Exception:
            return False

    def _extraer_filas(self, html: str, tipo: str, fini: str, ffin: str, vistos: set):
        """Devuelve (docs_en_rango, fechas_vistas_sin_filtrar) de todas las tablas
        cuya primera columna de encabezado es "Fecha" (biblioteca de documentos
        propia + lista mixta, en ambas variantes de clase CSS que usa SharePoint)."""
        docs = []
        fechas_vistas = []
        soup = BeautifulSoup(html, "html.parser")

        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if not rows:
                continue
            header = [c.get_text(" ", strip=True) for c in rows[0].find_all(["td", "th"])]
            if not header or header[0].strip() != "Fecha":
                continue

            for row in rows[1:]:
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                m = _FECHA_PATTERN.match(cells[0].get_text(" ", strip=True))
                if not m:
                    continue
                f_public = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
                fechas_vistas.append(f_public)

                if f_public < fini or f_public > ffin:
                    continue

                a = cells[1].find("a", href=True)
                if not a:
                    continue
                url = urljoin(_BASE_URL, a["href"])
                if not self._es_url_propia(url) or url in vistos:
                    continue
                vistos.add(url)

                titulo = a.get_text(strip=True)
                descripcion = cells[2].get_text(" ", strip=True) if len(cells) > 2 else ""

                docs.append(RawDocModel(
                    source=self.source,
                    link={"url": url, "method": "GET"},
                    title=titulo,
                    tipo=tipo,
                    detalle=descripcion or None,
                    f_public=f_public,
                    save_path=storage_path(self.source, f_public, tipo, "(filename)(extension)"),
                ))

        return docs, fechas_vistas

    def _extraer_next_links(self, html: str) -> List[str]:
        return [
            urljoin(_BASE_URL, m.group(1).replace("&amp;", "&"))
            for m in _NEXT_LINK_PATTERN.finditer(html)
        ]

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        docs = []
        vistos: set = set()

        for path, tipo in _CATEGORIAS.items():
            if stop_event is not None and stop_event.is_set():
                return docs
            if on_progress:
                on_progress(f"[{self.source}] Procesando {tipo}...")

            # BFS sobre los enlaces "Siguiente": la biblioteca propia y la lista
            # mixta paginan de forma independiente, cada "Siguiente" trae su propio
            # cursor de continuación, así que no hace falta correlacionarlas a mano
            queue = [f"{_BASE_URL}{path}"]
            visitadas: set = set()
            paginas = 0

            while queue and paginas < _MAX_PAGINAS_POR_CATEGORIA:
                if stop_event is not None and stop_event.is_set():
                    return docs
                url = queue.pop(0)
                if url in visitadas:
                    continue
                visitadas.add(url)
                paginas += 1

                try:
                    resp = session.get(url, timeout=30)
                    resp.raise_for_status()
                except Exception as e:
                    if on_progress:
                        on_progress(f"[{self.source}] Error consultando página de {tipo}: {e}")
                    continue

                nuevos, fechas = self._extraer_filas(resp.text, tipo, fini, ffin, vistos)
                docs.extend(nuevos)
                if len(docs) >= limit:
                    return docs[:limit]

                for next_url in self._extraer_next_links(resp.text):
                    if next_url not in visitadas:
                        queue.append(next_url)

            if paginas >= _MAX_PAGINAS_POR_CATEGORIA and queue:
                # The cap was hit with more pages still queued — silently
                # stopping here would drop whatever comes after page
                # _MAX_PAGINAS_POR_CATEGORIA with no trace of it ever happening.
                if on_progress:
                    on_progress(
                        f"[{self.source}] Error: se alcanzó el tope de {_MAX_PAGINAS_POR_CATEGORIA} páginas "
                        f"para {tipo} con más resultados pendientes; puede haber documentos sin recoger."
                    )

        return docs
