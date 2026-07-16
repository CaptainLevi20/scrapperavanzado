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


@register_family("constitucional")
class ScrapConstitucional(BaseScrapper):
    def __init__(self):
        self.source = "Corte Constitucional"

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        fecha_local = datetime.strptime(fini, "%Y-%m-%d")
        fecha_final_global = datetime.strptime(ffin, "%Y-%m-%d")
        docs: List[RawDocModel] = []

        while fecha_local < fecha_final_global:
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
                safe_title = raw["prov_sentencia"].replace("/", "-")
                # "Tutela" describes the process a ruling comes from, not the kind of
                # decision — the Corte's own API reports it inconsistently for T-series
                # rulings (sometimes "Sentencia", sometimes "Tutela"), so it's normalized
                # here to keep "tipo" meaning the same thing regardless of which the API
                # happened to return for a given document.
                tipo = "Sentencia" if raw["prov_tipo"] == "Tutela" else raw["prov_tipo"]
                path = storage_path(self.source, fecha_p, tipo, f"{safe_title}(extension)")

                docs.append(
                    RawDocModel(
                        source=self.source,
                        link={"url": link, "method": "GET", "body": {"path": raw["prov_sentencia"]}},
                        title=raw["prov_sentencia"],
                        tipo=tipo,
                        f_public=fecha_p,
                        f_providencia=raw["prov_f_sentencia"],
                        save_path=path,
                    )
                )

            fecha_local = fecha_final

        return docs
