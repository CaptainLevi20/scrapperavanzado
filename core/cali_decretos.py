"""Herramientas puras para la descarga masiva de decretos de Cali (Laboratorio).

Sin red, sin FastAPI, sin Celery — solo parseo de una página de paginador.php,
normalización de número/año, armado de rutas, validación de "esto es un PDF", y
lectura/escritura/forma del archivo de estado. Ver
docs/superpowers/specs/2026-09-02-laboratorio-descarga-decretos-cali-design.md
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup

BASE_PAGINADOR = "https://www.cali.gov.co/aplicaciones/boletin_decretos/paginador.php"
ENTIDAD = "ALCACALI"
PREFIJO_TIPO = "D"

_MM_OPEN = re.compile(r"MM_openBrWindow\(\s*\d+\s*,\s*'([^']+)'")
_SOLO_DIGITOS = re.compile(r"^\d+$")
_NO_ALNUM_NI_GUION = re.compile(r"[^A-Z0-9-]")
_ANIO_4 = re.compile(r"(1[89]\d{2}|20\d{2})")
_PAGINA_DE = re.compile(r"Pagina\s+\d+\s*/\s*(\d+)")
_TOTAL_REGISTROS = re.compile(r"de\s+([\d.]+)\s+registros\s+en\s+total")
_DOTDOT = "/boletin_publicaciones/../boletin_publicaciones/"


@dataclass
class FilaDecreto:
    numero_raw: str
    fecha: str
    anio_raw: str
    pdf_url: str | None


@dataclass
class PaginaParseada:
    filas: list[FilaDecreto]
    total_registros: int | None
    total_paginas: int | None


def _normalizar_url(url: str) -> str:
    if url.lower().startswith("ftp://"):
        return url
    url = url.replace(_DOTDOT, "/boletin_publicaciones/")
    if url.startswith("http://www.cali.gov.co"):
        url = "https://www.cali.gov.co" + url[len("http://www.cali.gov.co"):]
    return url


def parse_pagina(html: str) -> PaginaParseada:
    soup = BeautifulSoup(html, "html.parser")
    filas: list[FilaDecreto] = []
    tbody = soup.find("tbody")
    for tr in tbody.find_all("tr") if tbody else []:
        celdas = tr.find_all("td")
        if len(celdas) < 7:
            continue
        pdf_url = None
        boton = tr.find("button")
        if boton is not None:
            atributo = boton.get("onmouseup") or ""
            m = _MM_OPEN.search(atributo)
            if m:
                pdf_url = _normalizar_url(m.group(1))
        filas.append(
            FilaDecreto(
                numero_raw=celdas[1].get_text(strip=True),
                fecha=celdas[2].get_text(strip=True),
                anio_raw=celdas[5].get_text(strip=True),
                pdf_url=pdf_url,
            )
        )

    mp = _PAGINA_DE.search(html)
    mr = _TOTAL_REGISTROS.search(html)
    return PaginaParseada(
        filas=filas,
        total_registros=int(mr.group(1).replace(".", "")) if mr else None,
        total_paginas=int(mp.group(1)) if mp else None,
    )


def normalizar_numero(texto: str) -> str | None:
    limpio = texto.strip()
    if _SOLO_DIGITOS.match(limpio):
        return f"{int(limpio):04d}"
    subido = re.sub(r"\s+", "-", limpio.upper())
    subido = _NO_ALNUM_NI_GUION.sub("", subido).strip("-")
    return subido or None


def resolver_anio(anio_raw: str, fecha: str) -> int | None:
    limpio = anio_raw.strip()
    if re.fullmatch(r"\d{4}", limpio):
        return int(limpio)
    m = _ANIO_4.search(fecha or "")
    return int(m.group(1)) if m else None


def ruta_destino(destino: Path, numero: str, anio: int, sufijo: int = 0) -> Path:
    nombre = f"{PREFIJO_TIPO}_{ENTIDAD}_{numero}_{anio}"
    if sufijo:
        nombre = f"{nombre}_{sufijo}"
    return destino / "DECRETOS" / ENTIDAD / str(anio) / f"{nombre}.pdf"


def es_pdf_valido(head_bytes: bytes, size: int) -> bool:
    return size > 1024 and head_bytes[:4] == b"%PDF"
