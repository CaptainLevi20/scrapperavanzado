import re
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
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
    return f"{letra}_MCIT_{int(numero):04d}_{anio}"


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

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        return []
