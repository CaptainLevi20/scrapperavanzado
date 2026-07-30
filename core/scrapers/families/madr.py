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
