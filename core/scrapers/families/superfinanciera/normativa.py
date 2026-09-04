import re
from collections import namedtuple
from typing import Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.utils import storage_path

_BASE_URL = "https://www.superfinanciera.gov.co"
_INDICE_URL = (
    f"{_BASE_URL}/publicaciones/20149/normativanormativa-generalcirculares-externas-"
    "cartas-circulares-y-resoluciones-desde-el-ano-20149/"
)

# encabezado de columna (sin el " (1)"/" (2)"/" (3)") -> (tipo mostrado, sigla del título)
_TIPOS = {
    "Circulares Externas": ("Circular Externa", "C"),
    "Cartas Circulares": ("Carta Circular", "CCIR"),
    "Resoluciones": ("Resolución", "R"),
}

_ANIO_RE = re.compile(r"^\s*((?:19|20)\d{2})\s*$")
_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')

_FilaNormativa = namedtuple("_FilaNormativa", "numero_raw numero_link fecha_raw descripcion anexos_urls")

_MESES = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
    "septiembre": "09", "setiembre": "09", "octubre": "10",
    "noviembre": "11", "diciembre": "12",
}
_FECHA_RE = re.compile(
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+(\d{1,2})",
    re.IGNORECASE,
)


def _limpiar_encabezado(texto: str) -> str:
    # "Circulares Externas (1)" -> "Circulares Externas"
    return re.sub(r"\s*\(\d+\)\s*$", "", (texto or "").strip())


def _fecha_iso(fecha_raw: str, anio: int):
    m = _FECHA_RE.search(fecha_raw or "")
    if not m:
        return None
    mes = _MESES[m.group(1).lower()]
    dia = int(m.group(2))
    if not 1 <= dia <= 31:
        return None
    return f"{anio:04d}-{mes}-{dia:02d}"


def _titulo(sigla: str, numero_raw: str, anio: int):
    if numero_raw and numero_raw.isdigit():
        return f"{sigla}_SF_{int(numero_raw):04d}_{anio}", False
    return (numero_raw or "documento"), True


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _fila_a_docs(fila, tipo, sigla, anio, numero_link, fini, ffin, source, on_progress):
    title, unverified = _titulo(sigla, fila.numero_raw, anio)
    fecha = _fecha_iso(fila.fecha_raw, anio)
    if fecha is None:
        fecha = f"{anio:04d}-01-01"
        if on_progress:
            on_progress(f"[{source}] Aviso: sin fecha parseable para «{title}» ({tipo} {anio}), se usa {fecha}")
    if fecha < fini or fecha > ffin:
        return []

    docs = [RawDocModel(
        source=source,
        link={"url": numero_link, "method": "GET"},
        title=title,
        tipo=tipo,
        f_public=fecha,
        f_providencia=fecha,
        detalle=fila.descripcion,
        save_path=storage_path(source, fecha, tipo, f"{_safe_title(title)}(extension)"),
        title_unverified=unverified,
    )]
    if unverified:
        return docs  # sin un título madre estable no se pueden nombrar los anexos
    for n, url in enumerate(fila.anexos_urls, start=1):
        anexo_title = f"{title}_A{n:02d}"
        docs.append(RawDocModel(
            source=source,
            link={"url": url, "method": "GET"},
            title=anexo_title,
            tipo=tipo,
            f_public=fecha,
            f_providencia=fecha,
            detalle=f"Anexo {n} de {title}",
            save_path=storage_path(source, fecha, tipo, f"{_safe_title(anexo_title)}(extension)"),
        ))
    return docs


def _parse_indice(html: str, base_url: str) -> Dict[str, Dict[int, str]]:
    soup = BeautifulSoup(html, "html.parser")
    for tabla in soup.find_all("table"):
        encabezados = [_limpiar_encabezado(c.get_text()) for c in tabla.find_all(["th", "td"], limit=3)]
        col_por_indice = {i: h for i, h in enumerate(encabezados) if h in _TIPOS}
        if len(col_por_indice) < 3:
            continue
        resultado: Dict[str, Dict[int, str]] = {h: {} for h in col_por_indice.values()}
        for fila in tabla.find_all("tr"):
            celdas = fila.find_all("td")
            if not celdas:
                continue
            for i, celda in enumerate(celdas):
                encabezado = col_por_indice.get(i)
                if encabezado is None:
                    continue
                enlace = celda.find("a", href=True)
                if enlace is None:
                    continue
                m = _ANIO_RE.match(enlace.get_text())
                if not m:
                    continue
                resultado[encabezado][int(m.group(1))] = urljoin(base_url + "/", enlace["href"])
        return resultado
    return {}


def _parse_pagina_anio(html: str, base_url: str) -> List[_FilaNormativa]:
    soup = BeautifulSoup(html, "html.parser")
    tabla = soup.find("table")
    if tabla is None:
        return []
    filas: List[_FilaNormativa] = []
    for tr in tabla.find_all("tr"):
        celdas = tr.find_all("td")
        if len(celdas) < 3:
            continue  # fila de encabezado u otra cosa
        celda_num, celda_fecha, celda_desc = celdas[0], celdas[1], celdas[2]
        enlace_num = celda_num.find("a", href=True)
        if enlace_num is None:
            continue
        numero_raw = celda_num.get_text(strip=True)
        numero_link = urljoin(base_url + "/", enlace_num["href"])
        fecha_raw = celda_fecha.get_text(" ", strip=True)
        anexos_urls = [
            urljoin(base_url + "/", a["href"])
            for a in celda_desc.find_all("a", href=True)
        ]
        # descripción sin el texto de los enlaces de anexo
        for a in celda_desc.find_all("a"):
            a.extract()
        descripcion = celda_desc.get_text(" ", strip=True) or None
        filas.append(_FilaNormativa(numero_raw, numero_link, fecha_raw, descripcion, anexos_urls))
    return filas


def scrap_normativa(fini, ffin, source, limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
    return []
