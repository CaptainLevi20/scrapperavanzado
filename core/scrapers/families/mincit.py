import re
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.naming import codigo_ley_decreto
from core.utils import storage_path

_BASE_URL = "https://www.mincit.gov.co"

# slug de categoría -> (tipo mostrado, letra del código de título)
_CATEGORIAS = {
    "resoluciones": ("Resolución", "R"),
    "decretos": ("Decreto", "D"),
    "circulares": ("Circular", "C"),
    "leyes": ("Ley", "L"),
}

_FECHA_PATTERN = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_NUMERO_PATTERN = re.compile(r"^\S+\s+(\d+)")
_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
# Todo lo anterior al primer "," o ":" es "{tipo} {numero} del {fecha}"; lo que
# sigue es la descripción, con comillas opcionales alrededor (Resoluciones/
# Decretos/Leyes usan coma+comillas, Circulares usa dos puntos sin comillas) y
# un punto final opcional que se descarta junto con la comilla de cierre.
_DETALLE_PATTERN = re.compile(r'^[^,:]+[,:]\s*"?(.*?)"?\.?$', re.DOTALL)


def _parse_fecha(texto: str) -> Optional[str]:
    m = _FECHA_PATTERN.search(texto)
    if not m:
        return None
    dia, mes, anio = m.groups()
    return f"{anio}-{mes.zfill(2)}-{dia.zfill(2)}"


def _parse_numero(texto_archivo: str) -> Optional[str]:
    m = _NUMERO_PATTERN.match(texto_archivo.strip())
    return m.group(1) if m else None


def _parse_detalle(texto_archivo: str) -> Optional[str]:
    m = _DETALLE_PATTERN.match(texto_archivo.strip())
    if not m:
        return None
    detalle = m.group(1).strip()
    return detalle or None


def _normalize_title(letra: str, numero: str, anio: str) -> str:
    return codigo_ley_decreto(letra, numero, anio) or f"{letra}_MCIT_{int(numero):04d}_{anio}"


_SLUG_ANIO_PATTERN = re.compile(r"^(\d{4})(?:-(\d{4}))?$")


def _anios_del_slug(slug: str) -> List[int]:
    m = _SLUG_ANIO_PATTERN.match(slug)
    if not m:
        return []
    inicio = int(m.group(1))
    fin = int(m.group(2)) if m.group(2) else inicio
    if fin < inicio:
        inicio, fin = fin, inicio
    return list(range(inicio, fin + 1))


def _mapa_anio_a_slug(html: str, categoria: str) -> dict:
    patron = re.compile(rf'href="/normatividad/{re.escape(categoria)}/([^"]+)"')
    mapa = {}
    for slug in set(patron.findall(html)):
        for anio in _anios_del_slug(slug):
            mapa[anio] = slug
    return mapa


@register_family("mincit")
class ScrapMINCIT(BaseScrapper):
    filters_by_publication_date = True

    def __init__(self):
        self.source = "Ministerio de Comercio, Industria y Turismo"

    def _extraer_filas(self, html: str, tipo: str, letra: str, fini: str, ffin: str, on_progress=None) -> List[RawDocModel]:
        docs: List[RawDocModel] = []
        soup = BeautifulSoup(html, "html.parser")
        tabla = soup.find("table", id="Listado")
        if tabla is None:
            if on_progress:
                on_progress(f"[{self.source}] Error: no se encontró la tabla de documentos (id=Listado)")
            return docs
        tbody = tabla.find("tbody")
        if tbody is None:
            if on_progress:
                on_progress(f"[{self.source}] Error: la tabla de documentos no tiene <tbody>")
            return docs

        for fila in tbody.find_all("tr"):
            celdas = fila.find_all("td")
            if len(celdas) < 6:
                continue

            texto_archivo = celdas[1].get_text(" ", strip=True)
            f_providencia = _parse_fecha(celdas[3].get_text(strip=True))
            f_public = _parse_fecha(celdas[4].get_text(strip=True))
            if not f_providencia or not f_public:
                continue
            if f_public < fini or f_public > ffin:
                continue

            enlace = celdas[5].find("a", href=True)
            if not enlace:
                continue
            url = urljoin(_BASE_URL, enlace["href"])

            numero = _parse_numero(texto_archivo)
            detalle = _parse_detalle(texto_archivo)
            anio_providencia = f_providencia[:4]

            if numero is not None:
                title = _normalize_title(letra, numero, anio_providencia)
                title_unverified = False
            else:
                title = texto_archivo
                title_unverified = True

            safe_title = _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")

            docs.append(RawDocModel(
                source=self.source,
                link={"url": url, "method": "GET"},
                title=title,
                tipo=tipo,
                f_public=f_public,
                f_providencia=f_providencia,
                detalle=detalle,
                save_path=storage_path(self.source, f_public, tipo, f"{safe_title}(extension)"),
                title_unverified=title_unverified,
            ))

        return docs

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        docs: List[RawDocModel] = []
        # Las páginas de archivo se agrupan por año de EXPEDICIÓN, pero el rango pedido
        # es de PUBLICACIÓN (ver filters_by_publication_date): una norma expedida en
        # diciembre suele publicarse semanas después, ya en el año siguiente. Se pide un
        # año extra hacia atrás; el filtro por f_public de _extraer_filas descarta lo que
        # quede fuera del rango real.
        _ANIOS_DE_MARGEN = 1
        anio_inicial = int(fini[:4]) - _ANIOS_DE_MARGEN
        anio_final = int(ffin[:4])

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
                    on_progress(f"[{self.source}] Error consultando índice de {tipo}: {e}")
                continue

            mapa = _mapa_anio_a_slug(resp.text, categoria)
            if not mapa:
                if on_progress:
                    on_progress(f"[{self.source}] Error: el índice de {tipo} no devolvió páginas de archivo reconocibles")
                continue

            slugs = sorted({mapa[a] for a in range(anio_inicial, anio_final + 1) if a in mapa})

            for slug in slugs:
                if stop_event is not None and stop_event.is_set():
                    return docs

                try:
                    resp = session.get(f"{_BASE_URL}/normatividad/{categoria}/{slug}", timeout=30)
                    resp.raise_for_status()
                except Exception as e:
                    if on_progress:
                        on_progress(f"[{self.source}] Error consultando {categoria}/{slug}: {e}")
                    continue

                docs.extend(self._extraer_filas(resp.text, tipo, letra, fini, ffin, on_progress=on_progress))
                if len(docs) >= limit:
                    return docs[:limit]

        return docs
