import math
import re
from collections import namedtuple
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.fecha_es import parse_fecha_providencia_es
from core.models import RawDocModel
from core.utils import storage_path

_BASE_URL = "https://www.superfinanciera.gov.co"
_BUSCAR_URL = f"{_BASE_URL}/ABCD/superfinanciera/php/buscar_integrada.php"
_COLECCION = "ac|Doctrina y conceptos|TM_"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_POR_PAGINA = 25

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_TOTAL_RE = re.compile(r"de\s+([\d.,]+)\s+registros", re.IGNORECASE)
# "2020311455 - 001 del 5 de febrero de 2021"
_CONCEPTO_RE = re.compile(r"^\s*(\d{6,})\s*-\s*(\d{1,4})\s+del?\s+(.+?)\s*$")

_RegistroConcepto = namedtuple(
    "_RegistroConcepto", "radicado consecutivo fecha_texto titulo_norma resumen archivo_url raw_concepto"
)


def _total_registros(html: str) -> Optional[int]:
    m = _TOTAL_RE.search(html or "")
    if not m:
        return None
    return int(re.sub(r"[.,]", "", m.group(1)))


def _campo(registro, etiqueta: str) -> str:
    for td in registro.find_all("td"):
        if td.get_text(strip=True).rstrip(":").strip().lower() == etiqueta.rstrip(":").lower():
            siguiente = td.find_next_sibling("td")
            if siguiente is not None:
                return siguiente.get_text(" ", strip=True)
    return ""


def _parse_pagina(html: str, base_url: str) -> List[_RegistroConcepto]:
    soup = BeautifulSoup(html, "html.parser")
    registros: List[_RegistroConcepto] = []
    for tabla in soup.find_all("table", class_="registro"):
        raw_concepto = _campo(tabla, "Concepto:")
        titulo_norma = _campo(tabla, "Título de la norma:")
        resumen = _campo(tabla, "Resumen:")
        enlace = tabla.find("a", string=re.compile("Archivo de texto", re.IGNORECASE))
        archivo_url = urljoin(base_url + "/", enlace["href"]) if enlace and enlace.get("href") else None

        m = _CONCEPTO_RE.match(raw_concepto)
        if m:
            radicado, consecutivo, fecha_texto = m.group(1), m.group(2), m.group(3)
        else:
            radicado = consecutivo = None
            fecha_texto = raw_concepto
        registros.append(_RegistroConcepto(
            radicado, consecutivo, fecha_texto, titulo_norma, resumen, archivo_url, raw_concepto
        ))
    return registros


def _titulo_concepto(radicado: str, consecutivo: str) -> str:
    anio = radicado[:4]
    numero = radicado[4:]
    base = f"CTO_SF_{numero.zfill(7)}_{anio}"
    try:
        c = int(consecutivo)
    except (TypeError, ValueError):
        c = 1
    if c != 1:
        base = f"{base}_{c:02d}"
    return base


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _registro_a_doc(reg, fini, ffin, source, on_progress) -> Optional[RawDocModel]:
    fecha = parse_fecha_providencia_es(reg.fecha_texto or "")
    if fecha is None:
        if on_progress:
            on_progress(f"[{source}] Aviso: sin fecha en «{reg.raw_concepto[:80]}», se omite")
        return None
    fecha_iso = fecha.strftime("%Y-%m-%d")
    if fecha_iso < fini or fecha_iso > ffin:
        return None
    if not reg.archivo_url:
        if on_progress:
            on_progress(f"[{source}] Aviso: sin «Archivo de texto» para «{reg.raw_concepto[:80]}», se omite")
        return None

    if reg.radicado and reg.consecutivo:
        title = _titulo_concepto(reg.radicado, reg.consecutivo)
        unverified = False
    else:
        title = (reg.titulo_norma or reg.raw_concepto or "concepto")[:120]
        unverified = True

    partes = [p for p in (reg.titulo_norma, reg.resumen) if p]
    detalle = " — ".join(partes) or None

    return RawDocModel(
        source=source,
        link={"url": reg.archivo_url, "method": "GET"},
        title=title,
        tipo="Concepto",
        f_public=fecha_iso,
        f_providencia=fecha_iso,
        detalle=detalle,
        save_path=storage_path(source, fecha_iso, "Concepto", f"{_safe_title(title)}(extension)"),
        title_unverified=unverified,
    )


def _campos_form_continuar(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", attrs={"name": "continuar"})
    if form is None:
        return {}
    campos = {}
    for inp in form.find_all("input"):
        nombre = inp.get("name")
        if nombre:
            campos[nombre] = inp.get("value", "")
    return campos


def _consulta_inicial() -> dict:
    return {
        "base": "juris", "cipar": "", "Opcion": "libre", "coleccion": _COLECCION,
        "Expresion": "$", "titulo_c": "", "resaltar": "", "submenu": "", "Pft": "", "mostrar_exp": "",
    }


def scrap_conceptos(fini, ffin, source, limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
    session = requests.Session()
    session.headers.update(_HEADERS)
    docs: List[RawDocModel] = []

    try:
        r = session.post(_BUSCAR_URL, data=_consulta_inicial(), timeout=60)
        r.raise_for_status()
    except Exception as e:
        if on_progress:
            on_progress(f"[{source}] Error abriendo la colección Doctrina y conceptos: {e}")
        return []

    total = _total_registros(r.text) or 0
    paginas = max(1, math.ceil(total / _POR_PAGINA))
    if on_progress:
        on_progress(f"[{source}] Doctrina y conceptos: {total} registros, {paginas} páginas")

    def _procesar(html: str):
        for reg in _parse_pagina(html, _BASE_URL):
            doc = _registro_a_doc(reg, fini, ffin, source, on_progress)
            if doc is not None:
                docs.append(doc)

    _procesar(r.text)
    campos = _campos_form_continuar(r.text)

    for pagina in range(2, paginas + 1):
        if stop_event is not None and stop_event.is_set():
            return docs[:limit]
        if len(docs) >= limit:
            return docs[:limit]
        cuerpo = dict(campos)
        cuerpo["pagina"] = str(pagina)
        cuerpo["desde"] = str((pagina - 1) * _POR_PAGINA + 1)

        html = None
        for intento in range(2):
            try:
                pr = session.post(_BUSCAR_URL, data=cuerpo, timeout=60)
                pr.raise_for_status()
                html = pr.text
                break
            except Exception as e:
                if intento == 1 and on_progress:
                    on_progress(f"[{source}] Error consultando la página {pagina} de conceptos: {e}")
        if html is None:
            continue
        _procesar(html)
        nuevos_campos = _campos_form_continuar(html)
        if nuevos_campos:
            campos = nuevos_campos

    return docs[:limit]
