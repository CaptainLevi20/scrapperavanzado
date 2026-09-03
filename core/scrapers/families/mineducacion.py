import datetime
import re
import time
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE_URL = "https://www.mineducacion.gov.co"
_LISTADO_URL_TPL = _BASE_URL + "/portal/Normatividad/Ultimas-publicaciones;anos-normatividad/{anio}/"

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_ZERO_WIDTH = re.compile(r"[​‌‍﻿]")

# El sitio no separa por categoría en la URL: todos los tipos de norma se
# listan juntos por año, así que el tipo se determina por la primera palabra
# del título de cada fila (confirmado con muestreo real, 306 filas 2016-
# 2026). "Proyecto de Decreto/Resolución" (borrador en consulta pública, no
# es norma vigente) y cualquier otro documento fuera de esta lista (ej.
# "Guía...", "Manual...", "Reglamento Operativo...", vistos una sola vez cada
# uno) se excluyen a propósito -- no son un tipo de norma reconocible.
_TIPOS = {
    "resolución": ("Resolución", "R"),
    "resolucion": ("Resolución", "R"),
    "decreto": ("Decreto", "D"),
    "ley": ("Ley", "L"),
    "circular": ("Circular", "C"),
    "directiva": ("Directiva", "DIRECTIVA"),
    "acuerdo": ("Acuerdo", "A"),
}

_PRIMERA_PALABRA_PATTERN = re.compile(r"^([A-Za-zÁÉÍÓÚÑáéíóúñ]+)")
# El número de la norma siempre aparece antes de la fecha, justo después de
# la palabra de tipo (con una marca "N°"/"No."/"NO."/"nro." opcional en
# medio, que no contiene dígitos propios) -- el primer grupo de dígitos del
# título completo es siempre el número real, nunca parte de la fecha (que
# viene después).
_NUMERO_PATTERN = re.compile(r"\d+")

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_MESES_ALT = "|".join(_MESES.keys())
_MESES_ABREV = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
}
_MESES_ABREV_ALT = "|".join(_MESES_ABREV.keys())
_DIA = r"(?:0?[1-9]|[12]\d|3[01])"

# Cascada de formatos de fecha reales vistos en el título después del número
# (confirmado con 306 títulos reales, 2016-2026), de más a menos específico,
# combinados en UNA sola alternancia (mismo criterio que madr.py: un único
# .search() para que gane la coincidencia más a la izquierda, sin que un
# nivel más específico "secuestre" una fecha casual más adelante en texto
# libre):
# 1. "4 de agosto de 2026" / "27 de mayo del 2016" -- nombre de mes, con "de"
#    antes del día y antes del año, ambos opcionales por separado (varias
#    filas reales omiten el segundo: "7 de julio 2026").
# 2. "de agosto de 2026" -- sin día, solo nombre de mes.
# 3. "15-3-2022" -- fecha numérica DD-M-AAAA o DD/M/AAAA.
# 4. "26 NOV 2019" / "04 FEB 2026" -- mes abreviado en mayúsculas, sin "de".
# 5. "de 2026" -- solo año, sin día ni mes.
_FECHA_PATTERN = re.compile(
    r"(?:"
    rf"(?<!\d)({_DIA})\s+(?:de\s+)?({_MESES_ALT})\s+(?:del?\s+)?(\d{{4}})(?!\d)"
    r"|"
    rf"de\s+({_MESES_ALT})\s+(?:del?\s+)?(\d{{4}})(?!\d)"
    r"|"
    rf"(?<!\d)({_DIA})[-/](\d{{1,2}})[-/](\d{{4}})(?!\d)"
    r"|"
    rf"(?<!\d)({_DIA})\s+({_MESES_ABREV_ALT})\.?\s+(\d{{4}})(?!\d)"
    r"|"
    r"de\s*(\d{4})(?!\d)"
    r")",
    re.IGNORECASE,
)


def _limpiar_titulo(titulo: str) -> str:
    return _ZERO_WIDTH.sub("", titulo).strip()


def _clasificar_tipo(titulo: str):
    m = _PRIMERA_PALABRA_PATTERN.match(titulo)
    if not m:
        return None
    return _TIPOS.get(m.group(1).lower())


def _extraer_numero(titulo: str) -> Optional[str]:
    m = _NUMERO_PATTERN.search(titulo)
    return m.group(0) if m else None


def _resto_tras_numero(titulo: str, numero: str) -> str:
    idx = titulo.find(numero)
    if idx == -1:
        return titulo
    return titulo[idx + len(numero):]


def _parse_fecha(texto: str) -> Optional[str]:
    m = _FECHA_PATTERN.search(texto)
    if not m:
        return None
    dia1, mes1, anio1, mes2, anio2, dia3, mes3n, anio3, dia4, mes4, anio4, anio5 = m.groups()

    if dia1 is not None:
        mes_num = _MESES[mes1.lower()]
        try:
            datetime.date(int(anio1), mes_num, int(dia1))
        except ValueError:
            return f"{anio1}-{mes_num:02d}-01"
        return f"{anio1}-{mes_num:02d}-{int(dia1):02d}"
    if mes2 is not None:
        return f"{anio2}-{_MESES[mes2.lower()]:02d}-01"
    if dia3 is not None:
        try:
            datetime.date(int(anio3), int(mes3n), int(dia3))
        except ValueError:
            return None
        return f"{anio3}-{int(mes3n):02d}-{int(dia3):02d}"
    if dia4 is not None:
        mes_num = _MESES_ABREV[mes4.lower()]
        try:
            datetime.date(int(anio4), mes_num, int(dia4))
        except ValueError:
            return f"{anio4}-{mes_num:02d}-01"
        return f"{anio4}-{mes_num:02d}-{int(dia4):02d}"
    return f"{anio5}-01-01"


def _normalize_title(letra: str, numero: str, anio: str) -> str:
    return f"{letra}_ME_{int(numero):04d}_{anio}"


# Confirmado en producción (2026-08-25): una petición a este listado por año
# devolvió 404 una sola vez, y el mismo URL respondió 200 con contenido
# normal tres veces seguidas minutos después -- un fallo pasajero del sitio,
# no una página realmente inexistente. Se reintenta también sobre 404 (no
# solo sobre errores de red/5xx) por esa razón, específica de este listado.
def _get_con_reintentos(session, url, timeout=60, intentos=3):
    ultimo_error = None
    for intento in range(intentos):
        try:
            resp = session.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            ultimo_error = e
            if intento < intentos - 1:
                time.sleep(5)
    raise ultimo_error


def _elegir_adjunto(figuras):
    # Cada fila puede traer varios adjuntos (la norma misma + anexos: actas,
    # formatos, guías...). Se prefiere el primer adjunto en formato PDF, en
    # el orden en que aparece en el HTML -- confirmado con el sitio real que
    # el documento principal siempre es el primer PDF listado (su class es
    # "binary-pdf" o "binary-recurso_1"), mientras que un .docx/.xlsx que
    # aparece ANTES que el PDF es siempre un anexo, no la norma (ej. un
    # "Formato Préstamo Bicicletas.docx" listado antes que la circular misma
    # en PDF). Si ninguno es PDF, se usa el primero de todos modos -- mejor
    # que descartar la fila.
    for fig in figuras:
        enlace = fig.find("a", href=True)
        if enlace and enlace["href"].lower().endswith(".pdf"):
            return enlace
    if figuras:
        return figuras[0].find("a", href=True)
    return None


@register_family("mineducacion")
class ScrapMineducacion(BaseScrapper):
    def __init__(self):
        self.source = "Ministerio de Educación Nacional"

    def _extraer_fila(self, h3, base_url: str, on_progress=None):
        titulo_crudo = h3.get_text(strip=True)
        titulo = _limpiar_titulo(titulo_crudo)

        tipo_info = _clasificar_tipo(titulo)
        if tipo_info is None:
            return None
        tipo, letra = tipo_info

        numero = _extraer_numero(titulo)
        if numero is None:
            if on_progress:
                on_progress(f"[{self.source}] Aviso: no se encontró número para «{titulo}», se omite")
            return None

        fecha = _parse_fecha(_resto_tras_numero(titulo, numero))
        if fecha is None:
            if on_progress:
                on_progress(f"[{self.source}] Aviso: no se pudo determinar fecha para «{titulo}», se omite")
            return None

        recuadro = h3.find_parent("div", class_="recuadro")
        figuras = recuadro.select("div.figure.bajardoc") if recuadro else []
        enlace = _elegir_adjunto(figuras)
        if enlace is None:
            if on_progress:
                on_progress(f"[{self.source}] Aviso: no se encontró archivo adjunto para «{titulo}», se omite")
            return None
        url = urljoin(base_url, enlace["href"])

        resumen_tag = recuadro.find("p", class_="abstract") if recuadro else None
        detalle = resumen_tag.get_text(" ", strip=True) if resumen_tag else None

        title = _normalize_title(letra, numero, fecha[:4])
        safe_title = _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")

        doc = RawDocModel(
            source=self.source,
            link={"url": url, "method": "GET"},
            title=title,
            tipo=tipo,
            f_public=fecha,
            detalle=detalle,
            save_path=storage_path(self.source, fecha, tipo, f"{safe_title}(extension)"),
            title_unverified=False,
        )
        return fecha, doc

    def _extraer_anio(self, html: str, fallback_base_url: str, fini: str, ffin: str, on_progress=None) -> List[RawDocModel]:
        soup = BeautifulSoup(html, "html.parser")
        # El listado es una plantilla Newtenberg CMS con <base href> propio,
        # distinto de la URL amigable de la petición -- los enlaces de
        # descarga son relativos a ese <base>, no a la URL pedida.
        base_tag = soup.find("base", href=True)
        base_url = base_tag["href"] if base_tag else fallback_base_url

        docs: List[RawDocModel] = []
        for h3 in soup.select("h3.h4.titulo"):
            resultado = self._extraer_fila(h3, base_url, on_progress=on_progress)
            if resultado is None:
                continue
            fecha, doc = resultado
            if fini <= fecha <= ffin:
                docs.append(doc)
        return docs

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        docs: List[RawDocModel] = []
        for anio in range(int(fini[:4]), int(ffin[:4]) + 1):
            if stop_event is not None and stop_event.is_set():
                return docs
            if on_progress:
                on_progress(f"[{self.source}] Procesando {anio}...")

            url = _LISTADO_URL_TPL.format(anio=anio)
            try:
                resp = _get_con_reintentos(session, url)
            except Exception as e:
                if on_progress:
                    on_progress(f"[{self.source}] Error consultando {anio}: {e}")
                continue

            docs.extend(self._extraer_anio(resp.text, resp.url, fini, ffin, on_progress=on_progress))
            if len(docs) >= limit:
                return docs[:limit]

        return docs[:limit]
