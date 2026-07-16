import re
from typing import List

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_JEP_SEARCHADV_URL = "https://relatoria.jep.gov.co/searchadv"
_JEP_BASE_URL = "https://relatoria.jep.gov.co/"

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')

_PER_PAGE = 200


def _years_in_range(fini: str, ffin: str) -> list[int]:
    return list(range(int(fini[:4]), int(ffin[:4]) + 1))


@register_family("jep")
class ScrapJEP(BaseScrapper):
    # The JEP includes fecha_publicacion on every hit, so fini/ffin can be matched
    # precisely against it client-side (the server itself only filters by year) —
    # unlike most families, which can only filter by providencia date.
    filters_by_publication_date = True

    def __init__(self):
        self.source = "JEP"

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        docs: List[RawDocModel] = []
        vistos = set()  # providencia_id ya procesados en esta corrida (JEP puede repetir el mismo documento)

        for anio in _years_in_range(fini, ffin):
            if stop_event is not None and stop_event.is_set():
                break

            page = 1
            while True:
                if stop_event is not None and stop_event.is_set():
                    break

                response = requests.post(
                    _JEP_SEARCHADV_URL,
                    json={
                        "alguna_palabra": "",
                        "todas_palabras": "",
                        "frase_exacta": "",
                        "ninguna_palabra": "",
                        "anio": str(anio),
                        "sala_seccion": "",
                        "tipo_documento": "",
                        "page": page,
                        "per_page": _PER_PAGE,
                    },
                )

                if response.status_code != 200:
                    raise Exception(
                        f"Error al obtener datos de {self.source}: {response.status_code} - {response.text}"
                    )

                try:
                    data = response.json()
                except ValueError:
                    raise Exception(
                        f"La respuesta no es JSON válido. Contenido recibido:\n{response.text[:500]}"
                    )

                reponse = data.get("reponse")
                if reponse is None:
                    break

                hits = reponse.get("hits", {}).get("hits", [])
                total = reponse.get("hits", {}).get("total", {}).get("value", 0)

                for hit in hits:
                    raw = hit["_source"]

                    providencia_id = raw.get("providencia_id")
                    if providencia_id in vistos:
                        continue
                    vistos.add(providencia_id)

                    fecha_documento = raw.get("fecha_documento")
                    if not fecha_documento:
                        continue  # sin fecha de providencia no se puede construir el documento

                    fecha_publicacion = raw.get("fecha_publicacion")
                    f_public = fecha_publicacion[:10] if fecha_publicacion else fecha_documento

                    if f_public < fini or f_public > ffin:
                        continue  # filtrado preciso por fecha de publicación: el servidor solo filtra por año

                    radicado = raw.get("radicado_documento") or ""
                    tipo = raw.get("tipo_documento") or ""
                    seccion = raw.get("sala_seccion") or ""
                    # El expediente es el número del proceso judicial; el radicado identifica
                    # solo el documento puntual. Se prefiere el expediente como título/nombre
                    # de archivo, con el radicado como respaldo si la fuente no lo trae.
                    expediente = raw.get("expediente") or radicado

                    hipervinculo = (raw.get("hipervinculo") or "").lstrip("/")
                    link = f"{_JEP_BASE_URL}{hipervinculo}"

                    safe_expediente = _INVALID_PATH_CHARS.sub("-", expediente)
                    path = storage_path(
                        self.source, f_public, tipo, f"{safe_expediente}-{providencia_id}(extension)"
                    )

                    docs.append(
                        RawDocModel(
                            source=self.source,
                            link={"url": link, "method": "GET"},
                            title=expediente,
                            tipo=tipo,
                            seccion=seccion,
                            seccion_en_carpeta=False,
                            f_public=f_public,
                            f_providencia=fecha_documento,
                            save_path=path,
                        )
                    )

                if len(hits) < _PER_PAGE or page * _PER_PAGE >= total:
                    break
                page += 1

        return docs
