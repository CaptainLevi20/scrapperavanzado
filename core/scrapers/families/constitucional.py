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
                path = storage_path(self.source, fecha_p, raw["prov_tipo"], f"{safe_title}(extension)")

                docs.append(
                    RawDocModel(
                        source=self.source,
                        link={"url": link, "method": "GET", "body": {"path": raw["prov_sentencia"]}},
                        title=raw["prov_sentencia"],
                        tipo=raw["prov_tipo"],
                        f_public=fecha_p,
                        f_providencia=raw["prov_f_sentencia"],
                        save_path=path,
                    )
                )

            fecha_local = fecha_final

        return docs
