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

# radicado_documento (or its expediente fallback) is sometimes just a raw case
# number instead of a real document code — e.g. "1842", "15022955620220000001",
# "0000272-75.2026.0.00.0001" — with no letters at all.
_NUMERO_CRUDO_RE = re.compile(r"^[\d.\-]+$")

_MESES = "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre"
# nombre_providencia embeds "<tipo>_<código>_<día-mes-año>" (e.g.
# "Resolución_SDSJ-731_3-marzo-2026") or, when the day/month is missing,
# "<tipo>_<código>_<año>" (e.g. "Resolución_SAI-AOI-D-DVI-046_2026") — these
# match that trailing date/year so it can be stripped, leaving just the code.
_FECHA_SUFFIX_RE = re.compile(rf"[-_]\d{{1,2}}-(?:{_MESES})-(\d{{4}})$", re.IGNORECASE)
_ANIO_SUFFIX_RE = re.compile(r"[-_](\d{4})$")

# Solo el guión inmediatamente antes del año final se cambia a "_" — el resto
# de guiones dentro del código (ej. "SDSJ-RPP-1881") se dejan tal cual.
_ANIO_CON_GUION_RE = re.compile(r"-(\d{4})$")

# radicado_documento for "de Voto" providencias (Aclaración/Salvamento) sometimes
# comes back as the whole filing name instead of just its code — e.g.
# "AV_Dra-Sandra-Castro_Resolución_SDSJ-RPP-1881" (prefix, magistrado's name,
# tipo word, and only then the real code). The real code is always the last
# "_"-separated segment.
_RADICADO_COMPUESTO_DE_VOTO_RE = re.compile(r"^(?:AV|SV)_")

# tipo_documento can say plain "Auto"/"Sentencia" even when nombre_providencia
# itself is a separately-filed Aclaración/Salvamento de Voto attached to that
# providencia (JEP doesn't always classify these under their own "de Voto"
# tipo) — e.g. nombre_providencia "AV_Dra-Sandra-Gamboa_Auto_TP-SA-2241_..."
# for a tipo_documento of just "Auto". The separator after AV/SV is
# inconsistent in the source data too ("AV_Dra..." vs "SV-Dra...").
_MARCA_VOTO_EN_NOMBRE_RE = re.compile(r"^(AV|SV)[_-]")

_ETIQUETA_POR_MARCA = {"AV": "Aclaración de Voto", "SV": "Salvamento de Voto"}


def _normalizar_tipo(tipo: str, nombre_providencia: str) -> str:
    """If nombre_providencia reveals this is actually a vote annotation
    (AV_/SV_) but tipo_documento doesn't say so — or says the *wrong* one, as
    JEP's own data sometimes does — fold the correct "Aclaración/Salvamento de
    Voto de <tipo>" qualifier in, so the document lands under the right tipo
    (and storage folder), not lumped in with plain Autos/Sentencias."""
    marca = _MARCA_VOTO_EN_NOMBRE_RE.match(nombre_providencia or "")
    if not marca:
        return tipo
    etiqueta = _ETIQUETA_POR_MARCA[marca.group(1)]
    if etiqueta in tipo:
        return tipo
    for otra in _ETIQUETA_POR_MARCA.values():
        if otra != etiqueta and tipo.startswith(otra):
            return tipo.replace(otra, etiqueta, 1)
    return f"{etiqueta} de {tipo}"


def _years_in_range(fini: str, ffin: str) -> list[int]:
    return list(range(int(fini[:4]), int(ffin[:4]) + 1))


def _codigo_desde_radicado_compuesto(radicado: str) -> str:
    if _RADICADO_COMPUESTO_DE_VOTO_RE.match(radicado) and radicado.count("_") >= 3:
        return radicado.rsplit("_", 1)[-1]
    return radicado


_PREFIJOS_CONOCIDOS = ("R_", "S_", "SV_", "AV_")


def _prefijo_por_tipo(tipo: str, nombre_providencia: str = "") -> str:
    marca_voto = _MARCA_VOTO_EN_NOMBRE_RE.match(nombre_providencia or "")
    if marca_voto:
        return f"{marca_voto.group(1)}_"
    if "Salvamento de Voto" in tipo:
        return "SV_"
    if "Aclaración de Voto" in tipo:
        return "AV_"
    if tipo == "Resolución":
        return "R_"
    if tipo == "Sentencia":
        return "S_"
    return ""


def _codigo_desde_nombre_providencia(nombre_providencia: str) -> str:
    if not nombre_providencia:
        return ""
    partes = nombre_providencia.split("_", 1)
    resto = partes[1] if len(partes) > 1 else partes[0]
    match = _FECHA_SUFFIX_RE.search(resto) or _ANIO_SUFFIX_RE.search(resto)
    return resto[: match.start()] if match else resto


def _es_codigo_valido(valor: str) -> bool:
    return bool(valor) and " " not in valor and re.search(r"[A-Za-z]", valor) is not None


def _normalizar_titulo(radicado: str, nombre_providencia: str, anio_providencia: str, tipo: str) -> str:
    titulo = radicado
    # Regla 0: "AV_Nombre-Apellido_Tipo_CODIGO" trae el nombre del magistrado y
    # la palabra del tipo mezclados con el radicado — se queda solo el código.
    titulo = _codigo_desde_radicado_compuesto(titulo or "")
    # Regla 1: un título que es puro número no sirve como nombre — se intenta
    # recuperar el código real desde nombre_providencia.
    if _NUMERO_CRUDO_RE.match(titulo or ""):
        candidato = _codigo_desde_nombre_providencia(nombre_providencia)
        if _es_codigo_valido(candidato):
            titulo = candidato
    # Regla 2: todo título debe terminar en su año. Se compara contra el año
    # real (no un patrón genérico "-20XX"): el consecutivo de un código como
    # "SDSJ-2015" ya superó 2000 y se confundiría con un año que no es. Se
    # acepta tanto "-año" como "_año" (ya normalizado) para que la función sea
    # idempotente — volver a aplicarla sobre un título ya procesado no debe
    # agregarle el año una segunda vez.
    if not (titulo.endswith(f"-{anio_providencia}") or titulo.endswith(f"_{anio_providencia}")):
        titulo = f"{titulo}-{anio_providencia}"
    # Regla 4: prefijo según el tipo de documento (Resolución, Sentencia,
    # Salvamento/Aclaración de Voto), antepuesto antes de normalizar guiones.
    # Se revisa contra cualquier prefijo conocido (no solo el que tocaría
    # ahora) para que un título ya prefijado nunca quede con dos apilados.
    prefijo = _prefijo_por_tipo(tipo, nombre_providencia)
    if prefijo and not titulo.startswith(_PREFIJOS_CONOCIDOS):
        titulo = f"{prefijo}{titulo}"
    # Regla 3: solo el guión previo al año se reemplaza por guión bajo — el
    # resto de los guiones del código (ej. "SDSJ-RPP-1881") se conservan.
    return _ANIO_CON_GUION_RE.sub(r"_\1", titulo)


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

                    nombre_providencia = raw.get("nombre_providencia") or ""
                    tipo = _normalizar_tipo(raw.get("tipo_documento") or "", nombre_providencia)
                    seccion = raw.get("sala_seccion") or ""
                    # El radicado identifica el documento puntual; el expediente es el número
                    # del proceso judicial completo. Se prefiere el radicado como título/nombre
                    # de archivo, con el expediente como respaldo si la fuente no lo trae.
                    radicado = raw.get("radicado_documento") or raw.get("expediente") or ""
                    titulo = _normalizar_titulo(radicado, nombre_providencia, fecha_documento[:4], tipo)

                    hipervinculo = (raw.get("hipervinculo") or "").lstrip("/")
                    link = f"{_JEP_BASE_URL}{hipervinculo}"

                    safe_titulo = _INVALID_PATH_CHARS.sub("-", titulo)
                    path = storage_path(
                        self.source, f_public, tipo, f"{safe_titulo}_{providencia_id}(extension)"
                    )

                    docs.append(
                        RawDocModel(
                            source=self.source,
                            link={"url": link, "method": "GET"},
                            title=titulo,
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
