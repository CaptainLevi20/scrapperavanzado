"""Procuraduría General de la Nación (PGN) — dos secciones de la Relatoría
(apps.procuraduria.gov.co/relatoria). Diseño:
docs/superpowers/specs/2026-09-28-fuente-procuraduria-design.md

- Normativa: buscador de normatividad, consultado año por año (sin año el
  sitio devuelve 0 filas).
- Conceptos: SIREL, tipos CONCEPTO y CONCEPTO (MISIONAL), por rango de fechas
  (se pide el año completo para que los sufijos por choque sean estables).

La página de SharePoint normatividad.aspx es solo un marco vacío; el contenido
real es esta aplicación Java. Ambos buscadores MUESTRAN un reCAPTCHA que el
servidor no exige para los GET de paginación que el propio sitio enlaza. Si
algún día lo exige, la respuesta llega sin el pie "Resultados … de N" y la
sección registra un Error — nunca se intenta resolver ni saltar el reCAPTCHA.
"""
import base64
import datetime
import re
import unicodedata
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

from core.fecha_es import _MESES
from core.models import RawDocModel
from core.naming import codigo_ley_decreto
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_SOURCE = "Procuraduría General de la Nación"
_ANIO_MIN = 2015
# Con el User-Agent por defecto de un navegador sin ventana ("HeadlessChrome")
# www.procuraduria.gov.co responde una página de bloqueo; con uno de Chrome
# normal (o el de requests + este encabezado) responde bien.
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
_RELATORIA = "https://apps.procuraduria.gov.co/relatoria/index.jsp"
_OPT_NORMATIVA = "co.gov.pgn.relatoria.frontend.component.pagefactory.NormatividadPageFactory"
_OPT_SIREL = "co.gov.pgn.relatoria.frontend.component.pagefactory.PirelResolucionesPageFactory"
_TIPOS_CONCEPTO = ("CONCEPTO", "CONCEPTO (MISIONAL)")
# Filas por página pedidas al buscador (max_results). Hoy el año más grande de
# conceptos tiene ~5.800 filas, así que cabe en una sola página; la consulta
# igual pagina por si crece.
_PAGINA = 10000
_TIMEOUT = 300

# Los enlaces propios de Normativa llegan "sucios": host apps. (da 404),
# mode=1#page=inline, tabulación al final, o la URL pegada varias veces. Se toma
# el PRIMER relId y se arma siempre la forma canónica en www. (verificada para
# ids viejos y nuevos, HEAD incluido).
_RELID_RE = re.compile(r"accion=verDocumentoRel&(?:amp;)?relId=([A-Za-z0-9+/=%]+)")
_DOC_REL = "https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId={}&mode=inline"

# Nomenclatura acordada con el equipo de fuentes (clave: tipo del sitio en
# minúsculas y sin acentos). Las conjuntas se pliegan a su tipo base en el
# TÍTULO; el campo `tipo` del documento conserva el nombre original.
_PREFIJOS = {
    "resolucion": "R",
    "directiva": "DIR",
    "directiva conjunta": "DIR",
    "circular": "C",
    "circular conjunta": "C",
    "memorando": "M",
    "carta circular": "CCIR",
    "instructivo": "INS",
    "acuerdo": "A",
    "protocolo": "PRO",
}
_PREFIJO_DESCONOCIDO = "DOC"

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')


def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def _clave_tipo(tipo: str) -> str:
    return " ".join(_sin_acentos(tipo).lower().split())


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _relid(href: Optional[str]) -> Optional[str]:
    m = _RELID_RE.search(href or "")
    return m.group(1) if m else None


def _url_normativa(relid: str) -> str:
    return _DOC_REL.format(relid)


def _id_de_relid(relid: str) -> int:
    """relId es el id numérico del documento en base64 (MjQ0MTg1 -> 244185).
    Se usa solo para ordenar los choques de título; 0 si no decodifica."""
    try:
        crudo = unquote(relid)
        crudo += "=" * (-len(crudo) % 4)
        return int(base64.b64decode(crudo, validate=True).decode("ascii"))
    except Exception:
        return 0


def _numero_normativa(numero: str) -> str:
    n = " ".join((numero or "").split())
    if re.fullmatch(r"\d+", n):
        return f"{int(n):04d}"
    m = re.fullmatch(r"(\d+)\s*([A-Za-z])", n)
    if m:
        return f"{int(m.group(1)):04d}{m.group(2).upper()}"
    return n.replace(" ", "")


def _titulo_normativa(tipo: str, numero: str, anio: int, id_interno: int) -> Tuple[str, bool]:
    """(título, tipo_desconocido). El Decreto usa el código común de
    ministerios (D####YYY, deduplicado entre fuentes en el worker)."""
    clave = _clave_tipo(tipo)
    crudo = (numero or "").strip()
    if clave == "decreto" and re.fullmatch(r"\d+", crudo):
        return codigo_ley_decreto("D", crudo, str(anio)), False
    num = _numero_normativa(crudo) or f"SN{id_interno}"
    prefijo = _PREFIJOS.get(clave)
    if prefijo is None:
        return f"{_PREFIJO_DESCONOCIDO}_PGN_{num}_{anio}", True
    return f"{prefijo}_PGN_{num}_{anio}", False
