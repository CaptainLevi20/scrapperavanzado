import re
import unicodedata
from typing import List

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_JEP_URL = "https://relatoria.jep.gov.co/listarProvidecias"
_JEP_DOWNLOAD_URL = "https://relatoria.jep.gov.co/"

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')

# El API de JEP no expone un campo de "tipo de documento" separado: "nombre" es en
# realidad la sala/sección (ej. "S - Sala de Amnistía o Indulto"), no el tipo. El
# tipo real (Auto, Resolución, Sentencia...) solo aparece como prefijo del nombre
# de archivo en "hipervinculo" (ej. "Auto_SRVR-003_06-julio-2018.pdf"). Reglas en
# orden de especificidad: los prefijos compuestos van antes que sus sub-cadenas
# (ej. "sv-av" antes que "sv" y "av") para no matchear la regla equivocada.
_TIPO_REGLAS = [
    ("sv-av", "Salvamento y Aclaración de Voto"),
    ("spav", "Salvamento y Aclaración de Voto"),
    ("sentencia-interpretativa", "Sentencia Interpretativa"),
    ("sentencia interpretativa", "Sentencia Interpretativa"),
    ("sentencia", "Sentencia"),
    ("resolucion", "Resolución"),
    ("resolicion", "Resolución"),  # typo visto en datos reales de la fuente
    ("auto", "Auto"),
    ("av", "Aclaración de Voto"),
    ("sv", "Salvamento de Voto"),
    ("concepto", "Concepto"),
    ("acuerdo", "Acuerdo"),
    ("anexo", "Anexo"),
    ("edicion", "Boletín"),
    ("boletin", "Boletín"),
    ("guia", "Guía"),
    ("protocolo", "Protocolo"),
    ("aclaracion", "Aclaración"),
    ("oficio", "Oficio"),
    ("manual", "Manual"),
    ("lineamiento", "Lineamiento"),
]


def _extraer_tipo(hipervinculo: str) -> str:
    fname = hipervinculo.rsplit("/", 1)[-1]
    prefijo = fname.split("_", 1)[0].strip()
    clave = unicodedata.normalize("NFKD", prefijo).encode("ascii", "ignore").decode().lower()
    for patron, tipo in _TIPO_REGLAS:
        if clave.startswith(patron):
            return tipo
    return ""


@register_family("jep")
class ScrapJEP(BaseScrapper):
    def __init__(self):
        self.source = "JEP"
        self.url = None

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        # El API de JEP no expone mes/día: "fecha" siempre es un año (ej. 2024), no una
        # fecha completa. Por eso fini/ffin se recortan a año aquí y el filtro de abajo
        # compara años, no días — pedir un rango de meses dentro del mismo año devuelve
        # el año completo, no un subconjunto. La deduplicación por doc_id en el pipeline
        # de descarga es lo que evita reprocesar/reportar los mismos documentos en cada corrida.
        anio_inicial = fini[:4]
        anio_final = ffin[:4]
        self.url = _JEP_URL
        docs = []

        response = requests.get(self.url)

        if response.status_code != 200:
            raise Exception(
                f"Error al obtener datos de {self.source}: {response.status_code} - {response.text} el sitio pudo haber cambiado su estructura o el formato de respuesta, informare al equipo de desarrollo para actualizar el scraper."
            )

        try:
            results = response.json()
        except ValueError:
            raise Exception(
                f"La respuesta no es JSON válido. Contenido recibido:\n{response.text[:500]}"
            )

        data = results
        vistos = set()  # JEP repite el mismo documento con distintos "id" en su propio listado

        for item in data:
            fecha_p = item.get("fecha", 0)
            if fecha_p is None:
                fecha_p = 0

            if int(fecha_p) < int(anio_inicial) or int(fecha_p) > int(anio_final):
                continue  # Salta al siguiente item si la fecha no está dentro del rango

            if not item.get("hipervinculo"):
                continue  # registros placeholder (ej. id=1 "No Aplica") sin archivo real

            hipervinculo = item["hipervinculo"]
            if hipervinculo in vistos:
                continue  # evita reintentar el mismo documento roto muchas veces en la misma corrida
            vistos.add(hipervinculo)

            link = f"{_JEP_DOWNLOAD_URL}{hipervinculo}"

            radicado = item.get("radicado", "")
            seccion = item.get("nombre") or ""  # sala/sección (ej. "S - Sala de Amnistía o Indulto")
            tipo = _extraer_tipo(hipervinculo)
            # El pipeline de este backend (worker/tasks.py:_parse_date) exige "YYYY-MM-DD"
            # estricto; JEP solo tiene año, así que se ancla al 1 de enero de ese año (mismo
            # criterio que el fallback de "solo año" ya usado en adr.py/ane.py).
            fecha_p = f"{fecha_p}-01-01"

            # el radicado NO identifica un único documento: el mismo número de caso se
            # reutiliza para el Auto, su SV/AV, y luego la Sentencia y el suyo propio.
            # Sin el id (único y siempre presente en el API) esos documentos distintos
            # comparten ruta local — el segundo pisa al primero, o peor: el downloader
            # ve que el archivo ya existe (guard pensado para el paralelismo de SAMAI) y
            # lo salta sin descargar, aunque igual quede marcado como descargado.
            safe_radicado = _INVALID_PATH_CHARS.sub("-", radicado)
            item_id = item.get("id", "")
            path = storage_path(self.source, fecha_p, tipo, f"{safe_radicado}-{item_id}(extension)")

            doc = RawDocModel(
                source=self.source,
                link={"url": link, "method": "GET"},
                title=radicado,
                tipo=tipo,
                seccion=seccion,
                seccion_en_carpeta=False,
                f_public=fecha_p,
                save_path=path,
            )

            docs.append(doc)

        return docs
