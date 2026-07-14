import re
import unicodedata
from typing import List
from urllib.parse import urlparse

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE_URL = "https://ane.gov.co"
_LIST_API = f"{_BASE_URL}/_api/web/lists/getbytitle('contenidos')/items"
_ALLOWED_DOMAIN = "ane.gov.co"

# "Normativa aplicable" — la sección raíz que corresponde a la URL que se compartió
# (?p=711). El árbol se recorre recursivamente vía SharePoint REST ("contenidos"
# list, campo "padre") hasta llegar a nodos tipoContenido="Archivo".
_ROOT_ID = 711

_MESES = {
    "ENERO": "01", "FEBRERO": "02", "MARZO": "03", "ABRIL": "04",
    "MAYO": "05", "JUNIO": "06", "JULIO": "07", "AGOSTO": "08",
    "SEPTIEMBRE": "09", "OCTUBRE": "10", "NOVIEMBRE": "11", "DICIEMBRE": "12",
}
_FULL_DATE_PATTERN = re.compile(
    r"(\d{1,2})\s+DE[L]?\s+(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO"
    r"|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)\s+DE[L]?\s+(\d{4})",
    re.IGNORECASE,
)
_YEAR_ONLY_PATTERN = re.compile(r"\bDE[L]?\s+(\d{4})\b", re.IGNORECASE)


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


@register_family("ane")
class ScrapANE(BaseScrapper):
    def __init__(self):
        self.source = "Agencia Nacional del Espectro"

    def _hijos(self, session, padre_id):
        params = {
            "$filter": f"padre eq {padre_id}",
            "$select": "ID,Title,tipoContenido,archivo,vigencia",
            "$top": "500",
        }
        resp = session.get(_LIST_API, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json().get("value", [])

    def _es_url_propia(self, url: str) -> bool:
        try:
            return _ALLOWED_DOMAIN in urlparse(url).netloc
        except Exception:
            return False

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json;odata=nometadata",
        })

        anio_inicial = int(fini[:4])
        anio_final = int(ffin[:4])

        docs = []
        visitados = set()
        cola = [_ROOT_ID]

        while cola:
            if stop_event is not None and stop_event.is_set():
                return docs
            padre_id = cola.pop(0)
            if padre_id in visitados:
                continue
            visitados.add(padre_id)

            try:
                items = self._hijos(session, padre_id)
            except Exception as e:
                if on_progress:
                    on_progress(f"[{self.source}] Error consultando sección {padre_id}: {e}")
                continue

            for it in items:
                tipo_contenido = (it.get("tipoContenido") or "").strip()
                # algunos títulos vienen con acentos en forma NFD (o + combining
                # acute) en vez de NFC; normalizar evita que "Resolución" se
                # cuente como dos "tipo" distintos
                titulo = unicodedata.normalize("NFC", (it.get("Title") or "").strip())

                if tipo_contenido != "Archivo":
                    cola.append(it["ID"])
                    continue

                if titulo.lower().startswith("normograma"):
                    continue  # compendio temático sin fecha real por documento

                archivo = it.get("archivo") or {}
                url = archivo.get("Url") or ""
                if not url or not self._es_url_propia(url):
                    continue

                fecha_completa = _parse_full_date(titulo)
                if fecha_completa:
                    if fecha_completa < fini or fecha_completa > ffin:
                        continue
                    f_public = fecha_completa
                else:
                    anio = _parse_year_only(titulo)
                    if anio is None:
                        vigencia = str(it.get("vigencia") or "")
                        if vigencia.isdigit() and len(vigencia) == 4:
                            anio = int(vigencia)
                    if anio is None:
                        continue
                    if anio < anio_inicial or anio > anio_final:
                        continue
                    f_public = f"{anio}-01-01"

                palabras = titulo.split()
                tipo = palabras[0] if palabras else "Documento"

                docs.append(RawDocModel(
                    source=self.source,
                    link={"url": url, "method": "GET"},
                    title=titulo,
                    tipo=tipo,
                    f_public=f_public,
                    save_path=storage_path(self.source, f_public, tipo, "(filename)(extension)"),
                ))
                if len(docs) >= limit:
                    return docs[:limit]

            if on_progress and items:
                on_progress(f"[{self.source}] Procesadas {len(visitados)} secciones, {len(docs)} documentos...")

        return docs
