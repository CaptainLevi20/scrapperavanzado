"""Ministerio de Salud y Protección Social (MinSalud) — cuatro secciones de
normativa. Diseño: docs/superpowers/specs/2026-09-28-fuente-minsalud-design.md

Las cuatro páginas "Norm_*.aspx" del sitio son marcos de SharePoint sobre UNA
sola biblioteca de documentos, /Normatividad_Nuevo, filtrada por la columna
"Tipo de Norma" (empieza por Resolución / Circular / Concepto / Boletines).
Las páginas HTML tardan minutos en responder, pero la API REST de SharePoint
entrega la lista completa en segundos, así que se lee de ahí con una sola
consulta paginada (odata.nextLink). TLS válido: sin verify=False.
"""
import datetime
import re
import unicodedata
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

from core.fecha_es import parse_fecha_providencia_es
from core.models import RawDocModel
from core.naming import con_sufijos
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_SOURCE = "Ministerio de Salud y Protección Social"
_BASE = "https://www.minsalud.gov.co"
_API = f"{_BASE}/_api/web/GetList('/Normatividad_Nuevo')/items"
_CAMPOS = (
    "ID,Title,FileLeafRef,FileRef,FSObjType,Tipo_x0020_de_x0020_Norma,A_x00f1_o,"
    "Publicaci_x00f3_n,Descripci_x00f3_n,Tem_x00e1_tica,Subtema,Responsable,Created"
)
_ANIO_MIN = 2015
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
# El sitio a veces tarda en responder (las páginas HTML, minutos); la API suele
# contestar en segundos, pero se deja margen amplio.
_TIMEOUT = 300

# (prefijo del "Tipo de Norma", sección, tipo del documento, prefijo del título)
_SECCIONES = [
    ("Resolución", "Resoluciones", "Resolución", "R"),
    ("Circular", "Circulares", "Circular", "C"),
    ("Concepto", "Conceptos", "Concepto", "CTO"),
    ("Boletines", "Boletines", "Boletín Jurídico", "BOL"),
]
_MESES_ABR = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]
_MESES_PALABRA = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_EXTENSION = re.compile(r"\.[A-Za-z0-9]{2,4}$")

# Número de resolución/circular, en orden de preferencia (sobre texto
# normalizado: minúsculas, sin acentos). Los nombres de archivo se escriben a
# mano con muchas variantes ("No.", "Nro.", "No_9", "0304de 2015", "del 31 de
# diciembre del 2019", números con ceros a la izquierda de hasta 6 dígitos).
_NUM_CON_ANIO = re.compile(
    r"(?<!\d)(\d{1,6})\s*(?:de|del)?\s*(?:\d{1,2}\s+de\s+\w+\s+del?\s+)?((?:19|20)\d{2})\b"
)
_NUM_TRAS_MARCADOR = re.compile(r"\bn(?:o|°|º)?[._]?\s*(\d{1,6})\b")
_NUM_AL_INICIO = re.compile(r"^\s*(\d{1,6})\b")
_NUM_AL_FINAL = re.compile(r"(?<!\d)(\d{1,6})\s*$")
_RADICADO = re.compile(r"(?<!\d)(\d{12,17})(?!\d)")
_NUM_BOLETIN = re.compile(r"\bn(?:o|°|º)?[._]?\s*0*(\d{1,2})\b")


def _norm(texto: Optional[str]) -> str:
    s = unicodedata.normalize("NFKD", unicodedata.normalize("NFC", texto or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _sin_extension(nombre: Optional[str]) -> str:
    return _EXTENSION.sub("", nombre or "")


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _numero_norma(texto: Optional[str]) -> Optional[int]:
    n = _norm(texto)
    for patron in (_NUM_CON_ANIO, _NUM_TRAS_MARCADOR, _NUM_AL_INICIO, _NUM_AL_FINAL):
        m = patron.search(n)
        if m:
            return int(m.group(1))
    return None


def _radicado(texto: Optional[str]) -> Optional[str]:
    m = _RADICADO.search(texto or "")
    return m.group(1) if m else None


def _mes_boletin(texto: Optional[str], fecha: Optional[datetime.date]) -> Optional[int]:
    """Mes del boletín: la palabra del mes; si no hay, el número del boletín
    cuando está entre 1 y 12 (uno por mes); si tampoco, el mes de `fecha`
    (que el llamador pasa solo cuando NO es la fecha de respaldo 1 de enero)."""
    n = _norm(texto)
    # Find all month-word matches and return the one that appears earliest in the text
    earliest_match = None
    earliest_mes = None
    for palabra, mes in _MESES_PALABRA.items():
        m = re.search(rf"\b{palabra}\b", n)
        if m and (earliest_match is None or m.start() < earliest_match):
            earliest_match = m.start()
            earliest_mes = mes
    if earliest_mes is not None:
        return earliest_mes
    m = _NUM_BOLETIN.search(n)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(1))
    return fecha.month if fecha is not None else None


# El sitio guarda las fechas en UTC; "…T05:00:00Z" es la medianoche en Bogotá.
_COLOMBIA = datetime.timezone(datetime.timedelta(hours=-5))
_ANIO_EN_TEXTO = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


def _anio_plausible(a: int) -> bool:
    return 1990 <= a <= datetime.date.today().year + 1


def _fecha_local(iso: Optional[str]) -> Optional[datetime.date]:
    try:
        dt = datetime.datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(_COLOMBIA).date()


def _anio_doc(item: dict) -> int:
    """Año del documento: columna Año; si falta, el último año del nombre del
    archivo; si tampoco, el año de subida (Created)."""
    crudo = (item.get("A_x00f1_o") or "").strip()[:4]
    if crudo.isdigit() and _anio_plausible(int(crudo)):
        return int(crudo)
    anios = [int(a) for a in _ANIO_EN_TEXTO.findall(item.get("FileLeafRef") or "") if _anio_plausible(int(a))]
    if anios:
        return anios[-1]
    creado = _fecha_local(item.get("Created"))
    return creado.year if creado else datetime.date.today().year


def _fecha_doc(item: dict, anio: int) -> Tuple[datetime.date, bool]:
    """(fecha, es_respaldo). Cascada: Publicación → fecha en prosa de la
    descripción o del título, si es del año del documento → Created, si es del
    año → 1 de enero del año (respaldo)."""
    pub = _fecha_local(item.get("Publicaci_x00f3_n"))
    if pub is not None:
        return pub, False
    for texto in (item.get("Descripci_x00f3_n"), item.get("Title")):
        f = parse_fecha_providencia_es(texto or "")
        if f is not None and f.year == anio:
            return f, False
    creado = _fecha_local(item.get("Created"))
    if creado is not None and creado.year == anio:
        return creado, False
    return datetime.date(anio, 1, 1), True


def _avisar(on_progress, mensaje: str) -> None:
    if on_progress:
        on_progress(f"[{_SOURCE}] {mensaje}")


def _seccion_de(tipo: Optional[str]) -> Optional[Tuple[str, str, str]]:
    """Réplica del filtro de las vistas del sitio: "Tipo de Norma" EMPIEZA por
    Resolución / Circular / Concepto / Boletines (absorbe "Resolución " con
    espacio, "Resolución CRES", "Circular CRES", "Boletines Jurídicos")."""
    t = (tipo or "").strip()
    for prefijo_tipo, seccion, tipo_doc, prefijo in _SECCIONES:
        if t.startswith(prefijo_tipo):
            return seccion, tipo_doc, prefijo
    return None


def _titulo(prefijo: str, item: dict, anio: int, fecha: datetime.date, es_respaldo: bool) -> Tuple[str, bool]:
    """(título, aviso). El número sale del nombre del archivo o, si no trae,
    del título del sitio; el año es siempre el del documento."""
    archivo = _sin_extension(item.get("FileLeafRef"))
    titulo_sitio = item.get("Title") or ""
    if prefijo in ("R", "C"):
        n = _numero_norma(archivo)
        if n is None:
            n = _numero_norma(titulo_sitio)
        if n is not None:
            return f"{prefijo}_MSPS_{n:04d}_{anio}", False
    elif prefijo == "CTO":
        rad = _radicado(archivo) or _radicado(titulo_sitio)
        if rad:
            return f"CTO_MSPS_{rad}_{anio}", False
    elif prefijo == "BOL":
        fecha_util = None if es_respaldo else fecha
        mes = _mes_boletin(archivo, None) or _mes_boletin(titulo_sitio, fecha_util)
        if mes:
            return f"BOL_MSPS_{_MESES_ABR[mes - 1]}_{anio}", False
    return f"{prefijo}_MSPS_SN{item.get('ID')}_{anio}", True


def _una_linea(texto: Optional[str]) -> str:
    return " ".join((texto or "").split())


def _detalle(item: dict) -> Optional[str]:
    titulo = _una_linea(item.get("Title"))
    desc = _una_linea(item.get("Descripci_x00f3_n"))
    partes = [titulo] + ([desc] if desc and desc != titulo else [])
    detalle = " — ".join(p for p in partes if p)
    tema = " / ".join(x for x in (_una_linea(item.get("Tem_x00e1_tica")), _una_linea(item.get("Subtema"))) if x)
    if tema:
        detalle = f"{detalle} ({tema})" if detalle else tema
    dependencia = _una_linea(item.get("Responsable"))
    if dependencia:
        detalle = f"{detalle} — Dependencia: {dependencia}" if detalle else f"Dependencia: {dependencia}"
    return detalle or None


def _docs(items: List[dict], desde: str, hasta: str, on_progress) -> List[RawDocModel]:
    # 1) título base y fecha de TODOS los documentos de las cuatro secciones
    #    (los avisos se guardan y solo se emiten para los que quedan)
    base = []
    for item in items:
        if item.get("FSObjType") != 0:
            continue
        sec = _seccion_de(item.get("Tipo_x0020_de_x0020_Norma"))
        if sec is None:
            continue
        seccion, tipo_doc, prefijo = sec
        anio = _anio_doc(item)
        fecha, es_respaldo = _fecha_doc(item, anio)
        titulo, aviso_num = _titulo(prefijo, item, anio, fecha, es_respaldo)
        avisos = []
        if es_respaldo:
            avisos.append(f"Aviso: {titulo} sin fecha publicada, se usa {fecha.isoformat()}")
        if aviso_num:
            avisos.append(f"Aviso: no se reconoce el número de «{item.get('FileLeafRef')}», se nombra {titulo}")
        base.append((item, seccion, tipo_doc, anio, fecha, titulo, avisos))

    # 2) sufijos sobre toda la lista, y recién después piso + rango
    titulos = con_sufijos([(titulo, int(item.get("ID") or 0)) for item, _, _, _, _, titulo, _ in base])
    docs = []
    for (item, seccion, tipo_doc, anio, fecha, _, avisos), titulo in zip(base, titulos):
        iso = fecha.isoformat()
        if anio < _ANIO_MIN or iso < desde or iso > hasta:
            continue
        for mensaje in avisos:
            _avisar(on_progress, mensaje)
        docs.append(RawDocModel(
            source=_SOURCE,
            link={"url": _BASE + quote(item.get("FileRef") or ""), "method": "GET"},
            title=titulo,
            tipo=tipo_doc,
            f_public=iso,
            f_providencia=iso,
            seccion=seccion,
            detalle=_detalle(item),
            save_path=storage_path(_SOURCE, iso, tipo_doc, f"{_safe_title(titulo)}(extension)"),
        ))
    return docs
