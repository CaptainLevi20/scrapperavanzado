import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

logger = logging.getLogger(__name__)

_CORTE_SUPREMA_URL = "https://consultaprovidenciasbk.cortesuprema.gov.co/api"
_DOWNLOAD_URL = "https://consultaprovidenciasbk.cortesuprema.gov.co/downloadFile/"

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')

# Fixed UTC-5, not zoneinfo("America/Bogota") — Colombia has had no DST since
# 1993, so a fixed offset is exactly as correct while side-stepping any
# dependency on the host having an IANA tz database available (Windows dev
# machines don't ship one; the Linux prod containers do, but there's no reason
# to depend on that either way for an offset that never changes).
_COLOMBIA_TZ = timezone(timedelta(hours=-5))

# The document's own code (e.g. "ATP428-2026", "STL5177-2026") is always at
# the very start of the title. A bracketed/parenthesized reference number
# right after it — "(50621)", "[2024-00858-00]" — is part of the code and
# must be kept; plain-word junk after that ("- RESERVADO", "EDITADA") is not.
_CODIGO_RE = re.compile(r"^[A-Za-z]+\d+-\d{4}(?:\s*[\[\(][\d\-]+[\]\)])?")


def _codigo_from_titulo(titulo: str) -> Optional[str]:
    match = _CODIGO_RE.match(titulo)
    return match.group(0) if match else None


# Same shape as _CODIGO_RE but searched anywhere in a page of free text (not
# anchored to the start) — used to recover the code from the document's own
# content when the title metadata was unusable (e.g. "doc", "(3)").
_CODIGO_EN_TEXTO_RE = re.compile(r"\b([A-Za-z]{1,4}\d{1,6}-\d{4})\b")

def _codigo_desde_texto(texto: str) -> Optional[str]:
    match = _CODIGO_EN_TEXTO_RE.search(texto or "")
    return match.group(1).upper() if match else None


def _extraer_texto_primera_pagina(local_path, content_type: str) -> str:
    suffix = local_path.suffix.lower()
    if suffix == ".docx":
        from docx import Document as DocxDocument

        docx_doc = DocxDocument(str(local_path))
        # .docx has no fixed pagination — the code is always near the top of
        # the document, so the first paragraphs stand in for "page 1".
        return "\n".join(p.text for p in docx_doc.paragraphs[:30])
    # Falls back to pypdf for anything else (".pdf", or an unclear suffix
    # when content_type says pdf) — CSJ documents are always one or the other.
    from pypdf import PdfReader

    reader = PdfReader(str(local_path))
    if not reader.pages:
        return ""
    return reader.pages[0].extract_text() or ""


def _especialidad_from_online_path(online_path: str) -> Optional[str]:
    path = online_path.upper()
    # Tutela wins even when the path also names the internal sala that
    # resolved it (e.g. ".../TUTELAS/PENAL/..." is a tutela, not a Penal case).
    if "TUTELA" in path:
        return "Tutela"
    if "CIVIL" in path:
        return "Civil"
    if "LABORAL" in path:
        return "Laboral"
    if "PENAL" in path:
        return "Penal"
    return None


def _tipo_from_titulo(titulo: str) -> Optional[str]:
    # autoSentencia comes back null for some items — but the document's own
    # code already says which it is: "S..." (SC/SP/STC/STP...) is always a
    # Sentencia, "A..." (AC/AL/ATC/ATP...) is always an Auto, and "CP..." is a
    # Concepto (verified against a real one: Sala Penal issuing a concepto on
    # an extradition request, e.g. "CP098-2026").
    if titulo[:2].upper() == "CP":
        return "Concepto"
    primera_letra = titulo[:1].upper()
    if primera_letra == "S":
        return "Sentencia"
    if primera_letra == "A":
        return "Auto"
    return None


def _seccion_from_online_path(online_path: str) -> Optional[str]:
    # Unlike especialidad, a tutela does NOT get its own bucket here — it's
    # resolved by one of the three actual Salas de Casación, named in the path
    # segment right after "TUTELAS/" (e.g. ".../TUTELAS/PENAL/..."), so the
    # same Civil/Laboral/Penal check doubles as "which sala decided this".
    path = online_path.upper()
    if "CIVIL" in path:
        return "Sala de Casación Civil"
    if "LABORAL" in path:
        return "Sala de Casación Laboral"
    if "PENAL" in path:
        return "Sala de Casación Penal"
    return None


_BUCKET_POR_SECCION = {
    "Sala de Casación Civil": "SCC",
    "Sala de Casación Laboral": "SCL",
    "Sala de Casación Penal": "SCP",
}


def _bucket_real(bucket_por_busqueda: str, seccion: Optional[str]) -> str:
    # The "Tutelas" search bucket (SCT) only says which CSJ query found the
    # document, not who actually decided it — every tutela is resolved by one
    # of the three real Salas de Casación, so the title/storage bucket should
    # reflect that Sala instead of the generic "SCT".
    if bucket_por_busqueda == "SCT" and seccion in _BUCKET_POR_SECCION:
        return _BUCKET_POR_SECCION[seccion]
    return bucket_por_busqueda


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
    # CSJ's download is a POST to a shared endpoint with a body param, not a direct
    # file URL — there's nothing cheap to HEAD, so republication checking is out of
    # scope for this family (see tests/families/test_corte_suprema.py).
    checks_for_republication = False

    def __init__(self):
        self.source = "CSJ"
        self.url = _CORTE_SUPREMA_URL
        self.tipos = {"Tutelas": "SCT", "Laboral": "SCL", "Civil": "SCC", "Penal": "SCP"}

    def resolve_unverified_document(self, doc, local_path, content_type) -> None:
        try:
            texto = _extraer_texto_primera_pagina(local_path, content_type)
        except Exception as e:
            logger.warning(
                "No se pudo leer la primera página de %s para recuperar el título: %s",
                local_path.name, e,
            )
            return

        codigo = _codigo_desde_texto(texto)
        if not codigo:
            return

        # El título es el código a secas: el año que llevaba el relleno
        # ("doc_2019") era solo un desempate provisional, y el bucket vive en
        # la carpeta de guardado, no en el nombre del archivo.
        doc.title = codigo
        tipo_recuperado = _tipo_from_titulo(codigo)
        if tipo_recuperado:
            doc.tipo = tipo_recuperado

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        docs = []
        # CSJ lists the same providencia twice within one search — once as
        # .docx, once as .pdf — not a republication over time, just two
        # formats of the same submission. Keep only one per (bucket, código,
        # fecha), preferring the .pdf since it's directly previewable.
        indice_por_clave: dict[tuple, int] = {}
        es_pdf_por_clave: dict[tuple, bool] = {}

        fecha_inicio = datetime.fromisoformat(fini).date()
        fecha_fin = datetime.fromisoformat(ffin).date()

        for tipo in self.tipos:
            if stop_event is not None and stop_event.is_set():
                return docs

            stop = False
            start = 0
            agregados_este_tipo = 0
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
                            # fechaCreacion comes back as a UTC instant; fini/ffin (and
                            # therefore fecha_inicio/fecha_fin) are Colombia calendar
                            # dates. Converting to Colombia's own offset before taking
                            # .date() is what makes the two comparable — comparing UTC's
                            # .date() directly against them shifted the whole window by
                            # 5 hours, losing anything published after ~7pm COT and
                            # picking up the previous day's after-7pm items instead.
                            fecha_obj = datetime.fromisoformat(item["fechaCreacion"].replace("Z", "+00:00")).astimezone(
                                _COLOMBIA_TZ
                            )

                            if fecha_obj.date() > fecha_fin:
                                continue
                            elif fecha_obj.date() < fecha_inicio:
                                stop = True
                                break

                            fecha = fecha_obj.strftime("%Y-%m-%d")
                            titulo_crudo = item["title"].split(".")[-2].strip()
                            extension = item["title"].rsplit(".", 1)[-1].lower() if "." in item["title"] else ""
                            es_pdf = extension == "pdf"
                            online_path = item["onlinePath"]
                            seccion = _seccion_from_online_path(online_path)
                            # Cuando no se identifica bien el código (ej. "doc", "(3)") se
                            # usa el título crudo como relleno y se marca title_unverified
                            # para que, al descargar el archivo real, se revise su primera
                            # página y se recupere el código verdadero (ver
                            # resolve_unverified_document).
                            codigo = _codigo_from_titulo(titulo_crudo)
                            nombre_base = codigo or titulo_crudo
                            # Una tutela usa la sala que realmente la resolvió (seccion) como
                            # su bucket, no el genérico "SCT" de la búsqueda — ver _bucket_real.
                            bucket = _bucket_real(self.tipos[tipo], seccion)
                            # El título es el código a secas. El bucket (sala) va
                            # solo en la carpeta de guardado (CSJ/<bucket>/...).
                            # Cuando el código no se pudo identificar, el relleno
                            # lleva "_<año>" como desempate provisional hasta que
                            # resolve_unverified_document lea el código real.
                            titulo = nombre_base if codigo else f"{nombre_base}_{fecha_obj.year}"

                            clave = (bucket, nombre_base, fecha)
                            if clave in indice_por_clave:
                                if es_pdf and not es_pdf_por_clave[clave]:
                                    pass  # esta versión (pdf) reemplaza a la ya guardada (no-pdf)
                                else:
                                    continue  # ya se tiene una versión igual o mejor (pdf) de este mismo documento

                            auto_sentencia = item.get("autoSentencia")
                            tipo_doc = auto_sentencia.capitalize() if auto_sentencia else _tipo_from_titulo(nombre_base) or "Desconocido"
                            safe_titulo = _INVALID_PATH_CHARS.sub("-", titulo)
                            doc = RawDocModel(
                                tipo=tipo_doc,
                                title=titulo,
                                title_unverified=codigo is None,
                                especialidad=_especialidad_from_online_path(online_path),
                                seccion=seccion,
                                link={
                                    "url": _DOWNLOAD_URL,
                                    "body": {"path": online_path},
                                    "method": "POST",
                                },
                                f_public=fecha,
                                source=self.source,
                                save_path=storage_path(self.source, bucket, f"{safe_titulo}(extension)"),
                            )

                            if clave in indice_por_clave:
                                docs[indice_por_clave[clave]] = doc
                                es_pdf_por_clave[clave] = True
                                continue

                            indice_por_clave[clave] = len(docs)
                            es_pdf_por_clave[clave] = es_pdf
                            docs.append(doc)
                            # `limit` es por tipo (Tutelas/Laboral/Civil/Penal), no global —
                            # Tutelas por sí solo suele superar 1000 en un rango amplio, y
                            # antes esto agotaba el límite compartido dejando a los otros 3
                            # tipos con apenas 1 documento cada uno.
                            agregados_este_tipo += 1

                            if agregados_este_tipo >= limit:
                                stop = True
                                break
                        except (KeyError, IndexError) as e:
                            if on_progress:
                                on_progress(f"[{self.source}] Error: campo inesperado en resultado de '{tipo}': {e}")
                            continue

                    start += 10

                except Exception as e:
                    msg = str(e)
                    if "502" in msg or "503" in msg or "504" in msg:
                        msg += " Para el caso puntual de la Corte Suprema de Justicia no se puede realizar ningún cambio por el momento ya que ambas URLs apuntan a un mismo servidor que actualmente está caído."
                    if on_progress:
                        on_progress(f"[{self.source}] Error scraping tipo '{tipo}': {msg}")
                    stop = True

        return docs
