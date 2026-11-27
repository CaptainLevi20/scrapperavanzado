"""ADRES — resoluciones, circulares y acuerdos propios (v2).

Diseño: docs/superpowers/specs/2026-11-23-fuente-adres-design.md.

Desde agosto de 2026 el sitio es Next.js (App Router) + Payload CMS. Cada
página de /normativa trae TODAS sus filas en el payload RSC
(`self.__next_f.push([1,"…"])`), así que basta una petición por sección. Cada
página tiene dos bloques "docList": "ADRES" (lo propio) y "Ministerio de
Salud" (normas de MinSalud, que cubre la familia `minsalud`; se ignora). El
`"heading"` de cada bloque va DESPUÉS de su arreglo `"documents"`.

El sitio está detrás de un Azure Application Gateway que rechaza el
User-Agent de `requests` (403): la sesión manda uno de navegador. `HEAD` a
los archivos responde 404 aunque el `GET` da 200, por eso
`checks_for_republication = False`.
"""
import json
import re
import unicodedata
from datetime import date
from typing import List, Optional
from urllib.parse import urljoin

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_SOURCE = "Administradora de los Recursos del Sistema General de Seguridad Social en Salud"
_BASE_URL = "https://www.adres.gov.co"
_SIGLA = "ADRES"
_ANIO_MINIMO = 2015
_BLOQUE_PROPIO = "ADRES"
_PREFIJO_ARCHIVO = "/api/media/file/"
_RUTA_VIEJA = "/normativa/Documents/"
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

# El número es la tira de dígitos completa ((?!\d) evita que la regex parta
# "0000014_24_06_2024" en número "000" y año "0014").
_PATRONES = {
    "resoluciones": re.compile(
        r"^\s*(?:adres\s*-\s*)?(?:res(?:olu?ci?on)?\.?)?[\s_\-\.]*(?:(?:no|numero|npumero)\.?[\s_\-]*)?"
        r"(\d+)(?!\d)(?:[\s_\-]*(?:de|del)?[\s_\-]*(\d{4})(?!\d))?"
    ),
    "circulares": re.compile(r"^\s*(\d+)(?!\d)(?:[\s_\-]*(?:de)?[\s_\-]*(\d{4})(?!\d))?"),
    "acuerdos": re.compile(r"^\s*acuerdo[\s_]*(?:(?:no|numero)[\s_]*)?(\d+)(?!\d)(?:[\s_]*de[\s_]*(\d{4})(?!\d))?"),
}

# (ruta, nombre para avisos, tipo, prefijo del título)
_SECCIONES = [
    ("resoluciones", "Resoluciones", "Resolución", "R"),
    ("circulares", "Circulares", "Circular", "C"),
    ("acuerdos", "Acuerdos", "Acuerdo", "A"),
]

_PUSH = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
_DOCUMENTS = re.compile(r'"documents":')
_HEADING = re.compile(r'\s*,\s*"heading"\s*:\s*"((?:[^"\\]|\\.)*)"')
_FECHA = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$")
_ANCHO_CERO = re.compile(r"[​‌‍﻿]")


def _texto_rsc(html: str) -> str:
    partes = []
    for m in _PUSH.finditer(html):
        try:
            partes.append(json.loads(m.group(1)))
        except ValueError:
            continue
    return "".join(partes)


def bloques_doclist(html: str) -> list[tuple[str, list[dict]]]:
    """[(heading, documents), …] de cada bloque docList del payload RSC, en
    orden. El heading se lee en la clave que sigue al arreglo; leerlo hacia
    atrás cruzaría los bloques "ADRES" y "Ministerio de Salud"."""
    texto = _texto_rsc(html)
    decoder = json.JSONDecoder()
    bloques = []
    for m in _DOCUMENTS.finditer(texto):
        try:
            documentos, fin = decoder.raw_decode(texto, m.end())
        except ValueError:
            continue
        if not isinstance(documentos, list):
            continue
        h = _HEADING.match(texto, fin)
        heading = json.loads(f'"{h.group(1)}"') if h else ""
        bloques.append((heading, [d for d in documentos if isinstance(d, dict)]))
    return bloques


def numero_y_anio(seccion: str, name: str) -> Optional[tuple[str, Optional[int]]]:
    """(número tal cual lo escribe la ADRES, año del nombre o None), o None si
    el nombre no tiene la forma esperada."""
    m = _PATRONES[seccion].match(_sin_tildes(name or ""))
    if not m:
        return None
    anio = int(m.group(2)) if m.group(2) else None
    if anio is not None and not (1990 <= anio <= date.today().year + 1):
        anio = None
    return m.group(1), anio


def _limpio(texto) -> str:
    return re.sub(r"\s+", " ", _ANCHO_CERO.sub("", texto or "")).strip()


def _meta(doc: dict, etiqueta: str) -> str:
    for item in doc.get("meta") or []:
        if isinstance(item, dict) and item.get("label") == etiqueta:
            return item.get("value") or ""
    return ""


def _fecha(doc: dict) -> Optional[date]:
    m = _FECHA.match(_meta(doc, "Fecha"))
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _quitar_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def _sin_tildes(texto: str) -> str:
    return _quitar_tildes(texto).lower()


def _saneado(texto: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "_", _quitar_tildes(texto)).strip("_") or "documento"


def _enlace(doc: dict) -> tuple[Optional[str], Optional[str]]:
    """(url absoluta del archivo en la ADRES, ruta vieja rehecha o None).
    None como url = enlace a otro dominio (se descarta)."""
    archivo = (doc.get("file") or {}).get("url") or ""
    if archivo.startswith(_PREFIJO_ARCHIVO):
        return urljoin(_BASE_URL, archivo), None
    url = doc.get("url") or ""
    if url.startswith(_PREFIJO_ARCHIVO):
        return urljoin(_BASE_URL, url), None
    if url.startswith(_RUTA_VIEJA):
        # El archivo existe con el mismo nombre en /api/media/file/
        # (comprobado el 2026-11-26 para las dos filas que quedan así).
        return urljoin(_BASE_URL, _PREFIJO_ARCHIVO + url[len(_RUTA_VIEJA):]), url
    return None, None


@register_family("adres")
class ScrapADRES(BaseScrapper):
    # El sitio tarda hasta ~4 semanas en listar lo que sube; leer el listado
    # completo cuesta 3 peticiones, así que mirar más atrás no cuesta nada.
    scheduled_min_lookback_days = 45
    # HEAD a /api/media/file/ responde 404 (el GET da 200): sin revisión barata.
    checks_for_republication = False
    # Publica poco y a saltos: la pausa más larga entre documentos desde 2022
    # fue de 133 días (26-03 a 06-08-2025; corrida real del 2026-11-26).
    alerta_margen_dias = 140

    def __init__(self):
        self.source = _SOURCE

    def documentos_de_seccion(self, html: str, seccion: str, nombre: str, tipo: str, prefijo: str, avisar) -> List[RawDocModel]:
        """Todas las filas propias de la sección (sin filtrar por fecha), ya
        deduplicadas. Avisa con "Error:" si la página no trae el bloque ADRES,
        para que un cambio de sitio no vuelva a pasar en silencio."""
        bloques = bloques_doclist(html)
        propios = [docs for heading, docs in bloques if heading.strip() == _BLOQUE_PROPIO]
        if not propios:
            avisar(f"Error: la página de {nombre} no trae el bloque \"{_BLOQUE_PROPIO}\" "
                   f"({len(bloques)} bloques leídos); puede que el sitio haya cambiado.")
            return []

        elegidos: dict = {}
        for fila in (f for docs in propios for f in docs):
            name = _limpio(fila.get("name"))
            url, ruta_vieja = _enlace(fila)
            if url is None:
                continue
            fecha = _fecha(fila)
            if fecha is None:
                avisar(f"Fila sin fecha legible en {nombre} ({name!r}, {_meta(fila, 'Fecha')!r}): se omite.")
                continue
            if ruta_vieja:
                avisar(f"{nombre}: {name!r} enlaza a la ruta vieja {ruta_vieja}; se usa {url}.")

            parsed = numero_y_anio(seccion, name)
            unverified = False
            if parsed is None:
                titulo = _saneado(name)
                unverified = True
                clave = ("url", url)
                avisar(f"{nombre}: nombre fuera de patrón {name!r}; queda como {titulo!r} sin verificar.")
            else:
                numero, anio_nombre = parsed
                anio = anio_nombre or fecha.year
                if anio_nombre and anio_nombre != fecha.year:
                    try:
                        corregida = fecha.replace(year=anio_nombre)
                    except ValueError:
                        corregida = date(anio_nombre, 1, 1)
                    avisar(f"{nombre}: {name!r} tiene Fecha {fecha:%d/%m/%Y} de otro año; "
                           f"se usa {corregida.isoformat()} y queda sin verificar.")
                    fecha = corregida
                    unverified = True
                titulo = f"{prefijo}_{_SIGLA}_{numero}_{anio}"
                clave = (int(numero), anio)

            f_iso = fecha.isoformat()
            doc = RawDocModel(
                source=_SOURCE,
                link={"url": url, "method": "GET"},
                title=titulo,
                tipo=tipo,
                f_public=f_iso,
                f_providencia=f_iso,
                detalle=_limpio(fila.get("description")) or _limpio(_meta(fila, "Descripción")) or None,
                save_path=storage_path(_SOURCE, f_iso, tipo, f"{titulo}(extension)"),
                title_unverified=unverified,
            )
            previo = elegidos.get(clave)
            if previo is not None:
                quedan, sale = (previo, doc) if previo.f_public <= doc.f_public else (doc, previo)
                avisar(f"{nombre}: {titulo} repetido ({quedan.f_public} y {sale.f_public}); "
                       f"se queda el de la fecha más antigua.")
                elegidos[clave] = quedan
            else:
                elegidos[clave] = doc
        return list(elegidos.values())

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        def avisar(texto):
            if on_progress:
                on_progress(f"[{self.source}] {texto}")

        session = requests.Session()
        session.headers.update({"User-Agent": _USER_AGENT, "Accept-Language": "es-CO,es;q=0.9"})
        piso = f"{_ANIO_MINIMO}-01-01"

        docs: List[RawDocModel] = []
        for seccion, nombre, tipo, prefijo in _SECCIONES:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            avisar(f"Procesando {nombre}...")
            try:
                resp = session.get(f"{_BASE_URL}/normativa/{seccion}", timeout=60)
                resp.raise_for_status()
            except Exception as e:
                avisar(f"Error consultando {nombre}: {e}")
                continue

            for doc in self.documentos_de_seccion(resp.text, seccion, nombre, tipo, prefijo, avisar):
                if doc.f_public < piso or not (fini <= doc.f_public <= ffin):
                    continue
                docs.append(doc)
                if len(docs) >= limit:
                    return docs[:limit]
        return docs[:limit]
