import re
from datetime import datetime
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE_URL = "https://normativame.minenergia.gov.co"
_LOADER_URL = f"{_BASE_URL}/loader.php"

_LETRAS = {"Decreto": "D", "Resolución": "R", "Resolucion": "R", "Circular": "C"}

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')


def _normalize_title(letra: str, numero: str, anio: str) -> str:
    return f"{letra}_MME_{int(numero):04d}_{anio}"


def _parsear_fila(tr) -> Optional[dict]:
    tds = tr.find_all("td")
    if len(tds) < 4:
        return None

    enlace = tds[0].find("a", href=True)
    if enlace is None:
        return None
    numero = enlace.get_text(strip=True)

    tipo = tds[1].get_text(strip=True)
    fecha_texto = tds[2].get_text(strip=True)
    try:
        fecha = datetime.strptime(fecha_texto, "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None

    resumen = tds[3].get_text(" ", strip=True) or None

    return {
        "numero": numero,
        "tipo": tipo,
        "fecha": fecha,
        "resumen": resumen,
        "detalle_url": enlace["href"],
    }


def _extraer_pdf_de_detalle(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    iframe = soup.find("iframe", src=True)
    if iframe is None:
        return None
    return urljoin(_BASE_URL + "/", iframe["src"])


def _filas_de_pagina(html: str) -> List[dict]:
    soup = BeautifulSoup(html, "html.parser")
    tabla = soup.find("table", id="date_table")
    if tabla is None:
        return []
    filas = []
    for tr in tabla.find_all("tr")[1:]:  # la primera fila es el encabezado
        fila = _parsear_fila(tr)
        if fila is not None:
            filas.append(fila)
    return filas


@register_family("minenergia")
class ScrapMinEnergia(BaseScrapper):
    def __init__(self):
        self.source = "Ministerio de Minas y Energía"

    def _procesar_fila(self, session: requests.Session, fila: dict, on_progress=None) -> Optional[RawDocModel]:
        detalle_url = urljoin(_BASE_URL + "/", fila["detalle_url"])
        try:
            resp = session.get(detalle_url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            if on_progress:
                on_progress(f"[{self.source}] Error consultando detalle de «{fila['numero']}»: {e}")
            return None

        url_pdf = _extraer_pdf_de_detalle(resp.text)
        if url_pdf is None:
            if on_progress:
                on_progress(f"[{self.source}] Aviso: sin archivo adjunto para «{fila['numero']}», se omite")
            return None

        letra = _LETRAS.get(fila["tipo"])
        if letra is not None and fila["numero"].isdigit():
            title = _normalize_title(letra, fila["numero"], fila["fecha"][:4])
            title_unverified = False
        else:
            title = fila["numero"]
            title_unverified = True

        safe_title = _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")

        return RawDocModel(
            source=self.source,
            link={"url": url_pdf, "method": "GET"},
            title=title,
            tipo=fila["tipo"],
            f_public=fila["fecha"],
            f_providencia=fila["fecha"],
            detalle=fila["resumen"],
            save_path=storage_path(self.source, fila["fecha"], fila["tipo"], f"{safe_title}(extension)"),
            title_unverified=title_unverified,
        )

    def _paginar_anio(
        self, session: requests.Session, anio: int, fini: str, ffin: str, limit: int, docs: List[RawDocModel],
        stop_event=None, on_progress=None,
    ) -> None:
        pagina = 1
        while True:
            if stop_event is not None and stop_event.is_set():
                return
            if len(docs) >= limit:
                return

            params = {
                "lServicio": "Normatividad", "lTipo": "User", "lFuncion": "buscar",
                "vigencia": str(anio), "genPag": str(pagina),
            }
            try:
                resp = session.get(_LOADER_URL, params=params, timeout=30)
                resp.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{self.source}] Error consultando {anio} página {pagina}: {e}")
                return

            filas = _filas_de_pagina(resp.text)
            if not filas:
                return

            for fila in filas:
                if fila["fecha"] < fini or fila["fecha"] > ffin:
                    continue
                if stop_event is not None and stop_event.is_set():
                    return
                if len(docs) >= limit:
                    return
                doc = self._procesar_fila(session, fila, on_progress=on_progress)
                if doc is not None:
                    docs.append(doc)

            # Orden descendente por fecha confirmado dentro de cada año filtrado
            # por "vigencia": en cuanto la fila más vieja de la página ya es
            # anterior a fini, toda página siguiente también lo será — se puede
            # cortar aquí sin pedirlas.
            if min(fila["fecha"] for fila in filas) < fini:
                return

            pagina += 1

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        docs: List[RawDocModel] = []
        anio_ini = int(fini[:4])
        anio_fin = int(ffin[:4])

        for anio in range(anio_ini, anio_fin + 1):
            if stop_event is not None and stop_event.is_set():
                return docs
            if len(docs) >= limit:
                return docs[:limit]
            if on_progress:
                on_progress(f"[{self.source}] Procesando vigencia {anio}...")
            self._paginar_anio(session, anio, fini, ffin, limit, docs, stop_event, on_progress)

        return docs[:limit]
