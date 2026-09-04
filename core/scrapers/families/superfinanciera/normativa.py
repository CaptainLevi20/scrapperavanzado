import re
from typing import Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.utils import storage_path

_BASE_URL = "https://www.superfinanciera.gov.co"
_INDICE_URL = (
    f"{_BASE_URL}/publicaciones/20149/normativanormativa-generalcirculares-externas-"
    "cartas-circulares-y-resoluciones-desde-el-ano-20149/"
)

# encabezado de columna (sin el " (1)"/" (2)"/" (3)") -> (tipo mostrado, sigla del título)
_TIPOS = {
    "Circulares Externas": ("Circular Externa", "C"),
    "Cartas Circulares": ("Carta Circular", "CCIR"),
    "Resoluciones": ("Resolución", "R"),
}

_ANIO_RE = re.compile(r"^\s*((?:19|20)\d{2})\s*$")
_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')


def _limpiar_encabezado(texto: str) -> str:
    # "Circulares Externas (1)" -> "Circulares Externas"
    return re.sub(r"\s*\(\d+\)\s*$", "", (texto or "").strip())


def _parse_indice(html: str, base_url: str) -> Dict[str, Dict[int, str]]:
    soup = BeautifulSoup(html, "html.parser")
    for tabla in soup.find_all("table"):
        encabezados = [_limpiar_encabezado(c.get_text()) for c in tabla.find_all(["th", "td"], limit=3)]
        col_por_indice = {i: h for i, h in enumerate(encabezados) if h in _TIPOS}
        if len(col_por_indice) < 3:
            continue
        resultado: Dict[str, Dict[int, str]] = {h: {} for h in col_por_indice.values()}
        for fila in tabla.find_all("tr"):
            celdas = fila.find_all("td")
            if not celdas:
                continue
            for i, celda in enumerate(celdas):
                encabezado = col_por_indice.get(i)
                if encabezado is None:
                    continue
                enlace = celda.find("a", href=True)
                if enlace is None:
                    continue
                m = _ANIO_RE.match(enlace.get_text())
                if not m:
                    continue
                resultado[encabezado][int(m.group(1))] = urljoin(base_url + "/", enlace["href"])
        return resultado
    return {}


def scrap_normativa(fini, ffin, source, limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
    return []
