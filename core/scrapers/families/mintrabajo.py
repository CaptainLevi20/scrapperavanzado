import re
from datetime import date, datetime
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.naming import codigo_ley_decreto
from core.utils import storage_path

_BASE_URL = "https://www.mintrabajo.gov.co"
_MARCO_LEGAL_URL = f"{_BASE_URL}/web/guest/marco-legal"

_LETRAS = {"Decreto": "D", "Resolución": "R", "Resolucion": "R", "Circular": "C", "Leyes": "L"}

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_NUMERO_PATTERN = re.compile(r"\d+")

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_MESES_ALT = "|".join(_MESES.keys())
# Fecha en prosa española: "{día} de {mes} [de] {año}" -- el conector "de"
# entre mes y año es opcional (visto en el sitio real: "29 de julio 2021",
# "31 agosto 2023" sin ningún "de" en absoluto).
_FECHA_PROSA_PATTERN = re.compile(
    rf"(\d{{1,2}})\s+(?:de\s+)?({_MESES_ALT})\s+(?:de\s+)?(\d{{4}})", re.IGNORECASE
)


def _normalize_title(letra: str, numero: str, anio: str) -> str:
    return codigo_ley_decreto(letra, numero, anio) or f"{letra}_MTRA_{int(numero):04d}_{anio}"


def _parse_fecha_flexible(texto: str) -> Optional[str]:
    texto = texto.replace("\xa0", " ").strip()

    try:
        return datetime.strptime(texto, "%d/%m/%Y").date().isoformat()
    except ValueError:
        pass

    m = _FECHA_PROSA_PATTERN.search(texto)
    if m:
        dia, mes_nombre, anio = m.groups()
        mes = _MESES[mes_nombre.lower()]
        try:
            return date(int(anio), mes, int(dia)).isoformat()
        except ValueError:
            return f"{anio}-{mes:02d}-01"

    if re.fullmatch(r"\d{4}", texto):
        return f"{texto}-01-01"

    return None


def _parsear_fila(tr) -> Optional[dict]:
    tds = tr.find_all("td")
    if len(tds) < 5:
        return None

    tipo = tds[0].get_text(strip=True)
    letra = _LETRAS.get(tipo)
    if letra is None:
        return None

    norma = tds[1].get_text(" ", strip=True)
    numero_match = _NUMERO_PATTERN.search(norma)
    numero = numero_match.group(0) if numero_match else None

    fecha = _parse_fecha_flexible(tds[3].get_text(strip=True))
    if fecha is None:
        return None

    epigrafe = tds[2].get_text(" ", strip=True) or None

    enlace = tds[4].find("a", href=True)
    if enlace is None:
        return None

    return {
        "tipo": tipo, "letra": letra, "numero": numero, "fecha": fecha,
        "norma": norma, "epigrafe": epigrafe, "url": urljoin(_BASE_URL + "/", enlace["href"]),
    }


@register_family("mintrabajo")
class ScrapMinTrabajo(BaseScrapper):
    def __init__(self):
        self.source = "Ministerio del Trabajo"

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        if on_progress:
            on_progress(f"[{self.source}] Procesando marco legal...")

        try:
            resp = session.get(_MARCO_LEGAL_URL, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            if on_progress:
                on_progress(f"[{self.source}] Error consultando marco legal: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        docs: List[RawDocModel] = []

        for tr in soup.find_all("tr"):
            if stop_event is not None and stop_event.is_set():
                return docs
            if len(docs) >= limit:
                return docs[:limit]

            fila = _parsear_fila(tr)
            if fila is None:
                continue
            if fila["fecha"] < fini or fila["fecha"] > ffin:
                continue

            if fila["numero"] is not None:
                title = _normalize_title(fila["letra"], fila["numero"], fila["fecha"][:4])
                title_unverified = False
            else:
                title = fila["norma"]
                title_unverified = True
            safe_title = _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")

            docs.append(RawDocModel(
                source=self.source,
                link={"url": fila["url"], "method": "GET"},
                title=title,
                tipo=fila["tipo"],
                f_public=fila["fecha"],
                f_providencia=fila["fecha"],
                detalle=fila["epigrafe"],
                save_path=storage_path(self.source, fila["fecha"], fila["tipo"], f"{safe_title}(extension)"),
                title_unverified=title_unverified,
            ))

        return docs[:limit]
