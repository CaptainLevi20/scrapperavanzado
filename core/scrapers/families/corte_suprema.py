import logging
import re
import time
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import quote

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

logger = logging.getLogger(__name__)

# El backend de la Corte falla de a ratos (con el buscador viejo, en vivo: ~1
# de cada 180 consultas devolvió algo que no era JSON). Sin reintento, una sola falla cortaba la sala
# completa por el resto de la corrida.
_MAX_INTENTOS = 3
_ESPERA_REINTENTO_SEG = 5

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')

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


# --- Ojeador (buscador nuevo de la Corte, noviembre 2026) -------------------
# ojeador.cortesuprema.gov.co consulta este servicio público (sin credenciales,
# TLS válido). Ver docs/superpowers/specs/2026-11-18-csj-ojeador-design.md.
_BASE = "https://buscadorjurisprudenciabackend.cortesuprema.gov.co"
_SOURCE = "CSJ"

# Sala (campo `Sala`/`Especialidad` de Ojeador) -> (especialidad, seccion, carpeta).
_SALAS = {
    "CIVIL": ("Civil", "Sala de Casación Civil", "SCC"),
    "LABORAL": ("Laboral", "Sala de Casación Laboral", "SCL"),
    "PENAL": ("Penal", "Sala de Casación Penal", "SCP"),
    "PLENA": ("Plena", "Sala Plena", "SPL"),
}
# Cómo aparece cada sala dentro de `Ubicacion` (las tutelas penales van en
# "SALAS/TUTELAS/PENA/..."), para cuando `Sala` viene vacía.
_SALA_EN_RUTA = (("CIVIL", "CIVIL"), ("LABORAL", "LABORAL"), ("PENA", "PENAL"), ("PLENA", "PLENA"))

# Ojeador no acepta más de 100 resultados por página ni recorrer más de 10.000
# por búsqueda ("page * limit" > 10.000 -> 400).
_POR_PAGINA = 100
_VENTANA_MAX = 10000


def _tramos_mensuales(fini: str, ffin: str) -> list[tuple[str, str]]:
    """Parte [fini, ffin] en meses calendario (el primero y el último
    recortados al rango): Ojeador no deja recorrer más de 10.000 resultados
    por búsqueda y un mes completo de todas las salas ronda los 2.000-4.000."""
    inicio = datetime.fromisoformat(fini).date()
    fin = datetime.fromisoformat(ffin).date()
    tramos = []
    while inicio <= fin:
        siguiente_mes = (inicio.replace(day=28) + timedelta(days=4)).replace(day=1)
        cierre = min(siguiente_mes - timedelta(days=1), fin)
        tramos.append((inicio.isoformat(), cierre.isoformat()))
        inicio = siguiente_mes
    return tramos


def _tramos_diarios(fini: str, ffin: str) -> list[tuple[str, str]]:
    inicio = datetime.fromisoformat(fini).date()
    fin = datetime.fromisoformat(ffin).date()
    return [((inicio + timedelta(days=k)).isoformat(),) * 2 for k in range((fin - inicio).days + 1)]


def _tipo_desde_ojeador(tipo_providencia: str, codigo: Optional[str]) -> str:
    tipo = (tipo_providencia or "").strip().upper()
    if tipo.startswith("AUTO"):
        return "Auto"
    if tipo.startswith("SENTENCIA"):
        return "Sentencia"
    if tipo.startswith("CONCEPTO"):
        return "Concepto"
    return (_tipo_from_titulo(codigo) if codigo else None) or "Desconocido"


def _clasificar_sala(item: dict) -> tuple[Optional[str], Optional[str], str]:
    """(especialidad, seccion, carpeta). Una tutela conserva la sala que la
    resolvió como carpeta (como antes) pero su especialidad es "Tutela"."""
    ubicacion = (item.get("Ubicacion") or "").upper()
    sala = (item.get("Sala") or item.get("Especialidad") or "").strip().upper()
    if not sala:
        sala = next((nombre for marca, nombre in _SALA_EN_RUTA if marca in ubicacion), "")
    if sala not in _SALAS:
        return None, None, sala or _SOURCE
    especialidad, seccion, carpeta = _SALAS[sala]
    if "TUTELA" in (item.get("TipoDeProvidencia") or "").upper() or "/TUTELAS/" in ubicacion:
        especialidad = "Tutela"
    return especialidad, seccion, carpeta


def _url_descarga(ubicacion: str) -> str:
    return f"{_BASE}/document/descargar?path={quote(ubicacion, safe='')}"


def _doc_desde_resultado(item: dict) -> RawDocModel:
    """Arma el documento de un resultado de Ojeador. Lanza KeyError si falta
    `Ubicacion` o `FechaConsolidacionFirma` (resultado inservible)."""
    ubicacion = item["Ubicacion"]
    fecha = item["FechaConsolidacionFirma"][:10]
    nombre = (item.get("Nombre") or "").strip()
    codigo = _codigo_from_titulo(nombre) or _codigo_from_titulo((item.get("Numerador") or "").strip())
    titulo = codigo or f"{_INVALID_PATH_CHARS.sub('-', nombre or 'doc')}_{fecha[:4]}"
    especialidad, seccion, carpeta = _clasificar_sala(item)
    safe_titulo = _INVALID_PATH_CHARS.sub("-", titulo)
    return RawDocModel(
        source=_SOURCE,
        link={"url": _url_descarga(ubicacion), "method": "GET"},
        title=titulo,
        title_unverified=codigo is None,
        tipo=_tipo_desde_ojeador(item.get("TipoDeProvidencia") or "", codigo),
        especialidad=especialidad,
        seccion=seccion,
        f_public=fecha,
        f_providencia=fecha,
        save_path=storage_path(_SOURCE, carpeta, f"{safe_titulo}(extension)"),
    )


@register_family("corte_suprema")
class ScrapCorteSuprema(BaseScrapper):
    # La descarga de Ojeador responde 405 a un HEAD: no hay forma barata de
    # revisar republicaciones (tampoco la había con el buscador viejo).
    checks_for_republication = False

    # La Corte publica en Ojeador con 2 a 4 semanas de retraso respecto a la
    # fecha de firma: la corrida diaria mira 45 días atrás para no perder nada.
    scheduled_min_lookback_days = 45

    def __init__(self):
        self.source = _SOURCE

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

    def _consultar_pagina(self, fini: str, ffin: str, page: int) -> dict:
        """Una página de resultados de Ojeador, reintentando las fallas
        pasajeras (5xx, error de conexión, respuesta que no es JSON o sin la
        forma esperada). Un 4xx no se reintenta: es la Corte rechazando la
        consulta, no un hipo del servidor."""
        params = {
            "query_text": "", "orden": "recientes", "limit": str(_POR_PAGINA),
            "page": str(page), "fechaInicio": fini, "fechaFin": ffin,
        }
        ultimo_error: Optional[Exception] = None
        for intento in range(_MAX_INTENTOS):
            if intento:
                time.sleep(_ESPERA_REINTENTO_SEG)
            try:
                response = requests.get(f"{_BASE}/search/", params=params, timeout=60)
            except requests.exceptions.RequestException as e:
                ultimo_error = Exception(f"Error al conectar con {self.source}: {e}")
                continue

            if response.status_code >= 500:
                ultimo_error = Exception(
                    f"Error al obtener datos de {self.source}: servidor temporalmente no disponible ({response.status_code})."
                )
                continue
            if response.status_code != 200:
                raise Exception(
                    f"Error al obtener datos de {self.source}: {response.status_code} — el sitio pudo haber "
                    "cambiado su estructura. Informar al equipo de desarrollo."
                )
            try:
                data = response.json()
                if not isinstance(data.get("docs"), list):
                    raise ValueError("sin docs")
            except (ValueError, AttributeError):
                ultimo_error = Exception(
                    f"Error al obtener datos de {self.source}: respuesta inesperada del servidor "
                    "(no es el listado de providencias)."
                )
                continue
            return data

        raise Exception(f"{ultimo_error} (tras {_MAX_INTENTOS} intentos)")

    def _ventanas(self, fini: str, ffin: str, on_progress) -> list[tuple[str, str, Optional[dict]]]:
        """Ventanas de búsqueda para un tramo: el tramo mismo si cabe en los
        10.000 resultados que Ojeador deja recorrer, o un día por ventana si
        no. Devuelve (desde, hasta, primera página ya pedida o None)."""
        primera = self._consultar_pagina(fini, ffin, 1)
        total = primera.get("numFound") or 0
        if total <= _VENTANA_MAX or fini == ffin:
            if total > _VENTANA_MAX and on_progress:
                on_progress(
                    f"[{self.source}] Aviso: el {fini} tiene más de {_VENTANA_MAX} providencias; quedó incompleto"
                )
            return [(fini, ffin, primera)]
        return [(dia, dia, None) for dia, _ in _tramos_diarios(fini, ffin)]

    def scrap(self, fini, ffin, q="", limit=50000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        docs: List[RawDocModel] = []
        vistos: set[str] = set()
        # El archivo se guarda en CSJ/<carpeta>/<título>: dos resultados con la
        # misma carpeta y título irían al mismo archivo y uno pisaría al otro.
        rutas_emitidas: set[str] = set()

        for tramo_ini, tramo_fin in _tramos_mensuales(fini, ffin):
            if stop_event is not None and stop_event.is_set():
                return docs
            try:
                ventanas = self._ventanas(tramo_ini, tramo_fin, on_progress)
            except Exception as e:
                if on_progress:
                    on_progress(f"[{self.source}] Error consultando {tramo_ini}..{tramo_fin}: {e}")
                continue

            for desde, hasta, primera in ventanas:
                page = 1
                datos = primera
                while True:
                    if stop_event is not None and stop_event.is_set():
                        return docs
                    try:
                        if datos is None:
                            datos = self._consultar_pagina(desde, hasta, page)
                    except Exception as e:
                        if on_progress:
                            on_progress(f"[{self.source}] Error consultando {desde}..{hasta}: {e}")
                        break

                    resultados = datos.get("docs") or []
                    for item in resultados:
                        # Ojeador a veces indexa la misma providencia varias
                        # veces (ids distintos, misma Ubicacion = mismo archivo).
                        claves = {
                            f"{tipo}:{valor}"
                            for tipo, valor in (("id", item.get("id")), ("ruta", item.get("Ubicacion")))
                            if valor
                        }
                        if claves & vistos:
                            continue
                        vistos |= claves
                        try:
                            doc = _doc_desde_resultado(item)
                        except (KeyError, TypeError) as e:
                            if on_progress:
                                on_progress(
                                    f"[{self.source}] Error: campo inesperado en un resultado de {desde}..{hasta}: {e}"
                                )
                            continue
                        if not (fini <= doc.f_public <= ffin):
                            if on_progress:
                                on_progress(
                                    f"[{self.source}] Aviso: {doc.title} trae fecha {doc.f_public}, "
                                    "fuera del rango pedido; se omite"
                                )
                            continue
                        if doc.save_path in rutas_emitidas:
                            if on_progress:
                                on_progress(
                                    f"[{self.source}] Aviso: otra providencia con el mismo nombre ({doc.title}) "
                                    "ya está en esta corrida; se omite para no pisar su archivo"
                                )
                            continue
                        rutas_emitidas.add(doc.save_path)
                        docs.append(doc)
                        if len(docs) >= limit:
                            return docs

                    total = datos.get("numFound") or 0
                    if len(resultados) < _POR_PAGINA or page * _POR_PAGINA >= min(total, _VENTANA_MAX):
                        break
                    page += 1
                    datos = None

        return docs
