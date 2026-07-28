import re
from datetime import datetime, timedelta
from typing import List

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_DOWNLOAD_URL = "https://www.corteconstitucional.gov.co/sentencias/"


def _search_url(fini: str, ffin: str, q: str = "", limit: int = 1000) -> str:
    return (
        "https://www.corteconstitucional.gov.co/relatoria/buscador_new/"
        f"?searchOption=texto&fini={fini}&ffin={ffin}&buscar_por={q}&maxprov={limit}&slop=1&accion=search&tipo=json"
    )


# Classified by the providencia number's own prefix (T-/C-/SU) rather than
# trusting prov_tipo: the Corte's own API is inconsistent about the latter
# (a T-series ruling can come back as prov_tipo="Tutela" or, just as often,
# plain "Sentencia"), while the number prefix is always reliable.
_SENTENCIA_DISPLAY_TIPOS = {"Sentencia de Tutela", "Sentencia Constitucional", "Sentencia de Unificación"}


def _normalize_tipo(prov_sentencia: str, prov_tipo: str) -> str:
    if prov_sentencia.startswith("SU"):
        return "Sentencia de Unificación"
    if prov_sentencia.startswith("T"):
        return "Sentencia de Tutela"
    if prov_sentencia.startswith("C"):
        return "Sentencia Constitucional"
    return prov_tipo


def _normalize_title(prov_sentencia: str, tipo: str) -> str:
    # e.g. "T-206/26" -> "T206_26", "A. 846/26" -> "A846_26": drop everything
    # but letters/digits/the providencia-number separator, then turn that
    # separator into an underscore so the result is safe to use as a filename.
    normalized = re.sub(r"[^A-Za-z0-9/]", "", prov_sentencia).replace("/", "_")
    # Every "Sentencia ..." tipo gets an "S" prefix (e.g. "T206_26" ->
    # "ST206_26", "C034_26" -> "SC034_26") unless it already has one —
    # Sentencia de Unificación providencias are numbered "SU..." to begin
    # with, so "SU066_26" is left as-is rather than becoming "SSU066_26".
    if tipo in _SENTENCIA_DISPLAY_TIPOS and not normalized.startswith("S"):
        return f"S{normalized}"
    return normalized


@register_family("constitucional")
class ScrapConstitucional(BaseScrapper):
    def __init__(self):
        self.source = "Corte Constitucional"

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        fecha_local = datetime.strptime(fini, "%Y-%m-%d")
        fecha_final_global = datetime.strptime(ffin, "%Y-%m-%d")
        docs: List[RawDocModel] = []

        while True:
            if stop_event is not None and stop_event.is_set():
                break

            fecha_inicial = fecha_local.strftime("%Y-%m-%d")
            fecha_final = min(fecha_local + timedelta(days=365), fecha_final_global)

            url = _search_url(fecha_inicial, fecha_final.strftime("%Y-%m-%d"), q, limit)
            response = requests.get(url)

            if response.status_code != 200:
                raise Exception(
                    f"Error al obtener datos de {self.source}: {response.status_code} - {response.text}"
                )

            results = response.json()
            data = results["data"]["hits"].get("hits", [])

            for item in data:
                raw = item["_source"]
                link = f"{_DOWNLOAD_URL}{raw['rutahtml'].replace('.htm', '.rtf')}"
                fecha_p = raw.get("prov_f_public") or raw["prov_f_sentencia"]
                tipo = _normalize_tipo(raw["prov_sentencia"], raw["prov_tipo"])
                title = _normalize_title(raw["prov_sentencia"], tipo)
                path = storage_path(self.source, fecha_p, tipo, f"{title}(extension)")

                docs.append(
                    RawDocModel(
                        source=self.source,
                        link={"url": link, "method": "GET", "body": {"path": raw["prov_sentencia"]}},
                        title=title,
                        tipo=tipo,
                        f_public=fecha_p,
                        f_providencia=raw["prov_f_sentencia"],
                        save_path=path,
                    )
                )

            fecha_local = fecha_final
            if fecha_local >= fecha_final_global:
                break

        return docs
