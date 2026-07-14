from datetime import datetime
from typing import List

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_CORTE_SUPREMA_URL = "https://consultaprovidenciasbk.cortesuprema.gov.co/api"
_DOWNLOAD_URL = "https://consultaprovidenciasbk.cortesuprema.gov.co/downloadFile/"

_QUERY_TEMPLATE = """query GetSearchResult {{
    getSearchResult(
        searchQuery: {{
            query: "*"
            typeOfQuery: "{}"
            start: {}
            isExact: false
            magistrate: ""
            year: ""
            autoSentencia: ""
            order: "NEW_FIRST"
            roomTutelas: ""
        }}
    ) {{
        numOfResults
        searchResults {{
            typeOfDocument
            aplicationName
            fiveParaphraseResult
            title
            id
            onlinePath
            doctor
            fechaCreacion
            ano
            autoSentencia
            leyesOArticulos
        }}
    }}
}}
"""


@register_family("corte_suprema")
class ScrapCorteSuprema(BaseScrapper):
    def __init__(self):
        self.source = "CSJ"
        self.url = _CORTE_SUPREMA_URL
        self.tipos = {"Tutelas": "SCT", "Laboral": "SCL", "Civil": "SCC", "Penal": "SCP"}

    def scrap(self, fini, ffin, q="", limit=1000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        docs = []

        fecha_inicio = datetime.fromisoformat(fini).date()
        fecha_fin = datetime.fromisoformat(ffin).date()

        for tipo in self.tipos:
            if stop_event is not None and stop_event.is_set():
                return docs

            stop = False
            start = 0
            while not stop:
                try:
                    payload = {"query": _QUERY_TEMPLATE.format(tipo, start)}
                    headers = {"Content-Type": "application/json"}

                    response = requests.post(self.url, json=payload, headers=headers, timeout=60)

                    if response.status_code != 200:
                        if response.status_code in (502, 503, 504):
                            raise Exception(
                                f"Error al obtener datos de {self.source}: servidor temporalmente no disponible ({response.status_code}). Intenta de nuevo más tarde."
                            )
                        raise Exception(
                            f"Error al obtener datos de {self.source}: {response.status_code} — el sitio pudo haber cambiado su estructura. Informar al equipo de desarrollo."
                        )

                    data = response.json()

                    search_results = data.get("data", {}).get("getSearchResult", {}).get("searchResults", [])

                    if not search_results:
                        stop = True
                        break

                    for item in search_results:
                        try:
                            fecha_obj = datetime.fromisoformat(item["fechaCreacion"].replace("Z", "+00:00"))

                            if fecha_obj.date() > fecha_fin:
                                continue
                            elif fecha_obj.date() < fecha_inicio:
                                stop = True
                                break

                            fecha = fecha_obj.strftime("%Y-%m-%d")
                            titulo = item["title"].split(".")[-2].strip()

                            doc = RawDocModel(
                                tipo=item.get("typeOfDocument") or "Desconocido",
                                title=titulo,
                                link={
                                    "url": _DOWNLOAD_URL,
                                    "body": {"path": item["onlinePath"]},
                                    "method": "POST",
                                },
                                f_public=fecha,
                                source=self.source,
                                save_path=storage_path(self.source, self.tipos[tipo], "(filename)(extension)"),
                            )
                            docs.append(doc)

                            if len(docs) >= limit:
                                stop = True
                                break
                        except (KeyError, IndexError) as e:
                            print(f"Error: campo inesperado en resultado de '{tipo}': {e}")
                            continue

                    start += 10

                except Exception as e:
                    msg = str(e)
                    if "502" in msg or "503" in msg or "504" in msg:
                        msg += " Para el caso puntual de la Corte Suprema de Justicia no se puede realizar ningún cambio por el momento ya que ambas URLs apuntan a un mismo servidor que actualmente está caído."
                    print(f"Error scraping tipo '{tipo}': {msg}")
                    stop = True

        return docs
