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
                        continue  # sin fecha no se puede saber si cae dentro del rango pedido

                    if fecha_documento < fini or fecha_documento > ffin:
                        continue  # filtrado preciso: el servidor solo filtra por año

                    fecha_publicacion = raw.get("fecha_publicacion")
                    f_public = fecha_publicacion[:10] if fecha_publicacion else fecha_documento

                    radicado = raw.get("radicado_documento") or ""
                    tipo = raw.get("tipo_documento") or ""
                    seccion = raw.get("sala_seccion") or ""

                    hipervinculo = (raw.get("hipervinculo") or "").lstrip("/")
                    link = f"{_JEP_BASE_URL}{hipervinculo}"

                    safe_radicado = _INVALID_PATH_CHARS.sub("-", radicado)
                    path = storage_path(
                        self.source, f_public, tipo, f"{safe_radicado}-{providencia_id}(extension)"
                    )

                    docs.append(
                        RawDocModel(
                            source=self.source,
                            link={"url": link, "method": "GET"},
                            title=radicado,
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
