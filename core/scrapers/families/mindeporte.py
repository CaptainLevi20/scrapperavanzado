import re
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.naming import codigo_ley_decreto
from core.utils import storage_path

_BASE_URL = "https://www.mindeporte.gov.co"
_NORMATIVIDAD_PATH = (
    "/transparencia-y-acceso-a-informacion-publica/2-normativa/2-1-normatividad/"
    "normatividad-general-y-reglamentaria"
)

# slug (bajo _NORMATIVIDAD_PATH) -> (tipo mostrado, letra del código de
# título, si la categoría se navega por año o es un único listado plano).
_CATEGORIAS = {
    "resoluciones": ("Resolución", "R", True),
    "normograma/decretos": ("Decreto", "D", False),
    "normograma/leyes": ("Ley", "L", False),
    "normograma/acuerdos": ("Acuerdo", "A", False),
    "normograma/conpes": ("Conpes", "CONPES", False),
    "normograma/directivas": ("Directiva", "DIR", False),
    "normograma/circulares": ("Circular", "C", False),
}

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_MESES_ALT = "|".join(_MESES.keys())
_DIA = r"(?:0?[1-9]|[12]\d|3[01])"

_NUMERO_PATTERN = re.compile(r"\d+")

# Misma técnica de cascada de `madr.py` (día+mes+año / mes+día+año invertido
# / mes+año / solo año, con el conector "de"/"del" exigido entre cada parte),
# con un nivel adicional insertado tras el primero: día+mes+año SIN conector
# entre el mes y el año — visto en una Circular real del sitio ("15 de
# noviembre 2024"), formato que ninguno de los 4 niveles de `madr` reconoce
# porque todos exigen "de"/"del" inmediatamente antes del año.
_FECHA_PATTERN = re.compile(
    r"(?:"
    rf"(?<!\d)({_DIA})\s+(?:DE\s+)?({_MESES_ALT})\s+DEL?\s+(\d{{4}})(?!\d)"
    r"|"
    rf"(?<!\d)({_DIA})\s+(?:DE\s+)?({_MESES_ALT})\s+(\d{{4}})(?!\d)"
    r"|"
    rf"DE\s+({_MESES_ALT})\s+(?<!\d)({_DIA})\s+DEL?\s+(\d{{4}})(?!\d)"
    r"|"
    rf"DE\s+({_MESES_ALT})\s+DEL?\s+(\d{{4}})(?!\d)"
    r"|"
    r"\bDEL?\s*(\d{4})(?!\d)"
    r")",
    re.IGNORECASE,
)


def _resto_tras_numero(titulo: str, numero: str) -> str:
    idx = titulo.find(numero)
    if idx == -1:
        return titulo
    return titulo[idx + len(numero):]


def _normalize_title(letra: str, numero: str, anio: str) -> str:
    return codigo_ley_decreto(letra, numero, anio) or f"{letra}_MDEP_{int(numero):04d}_{anio}"


def _limpiar_detalle(texto: str) -> str:
    # El sitio envuelve el detalle entre comillas, pero mezcla comilla recta
    # de apertura (") con comilla tipográfica de cierre (") pegada ANTES del
    # punto final (ej. `"...del Ministerio del Deporte".`) — un `strip('"')`
    # simple no la quita porque el punto, no la comilla, es el último
    # carácter real de la cadena.
    texto = re.sub(r'^["“]\s*', "", texto)
    texto = re.sub(r'\s*[”"](?=\.?$)', "", texto)
    return texto


def _parse_fecha(texto: str) -> Optional[str]:
    m = _FECHA_PATTERN.search(texto)
    if not m:
        return None

    dia1, mes1, anio1, dia1b, mes1b, anio1b, mes2, dia2, anio2, mes3, anio3, anio4 = m.groups()

    def _fecha_dia(dia: str, mes_nombre: str, anio: str) -> str:
        mes_num = _MESES[mes_nombre.lower()]
        dia_int = int(dia)
        if mes_num == 2 and dia_int > 29 or mes_num in (4, 6, 9, 11) and dia_int > 30 or dia_int > 31:
            return f"{anio}-{mes_num:02d}-01"
        return f"{anio}-{mes_num:02d}-{dia_int:02d}"

    if dia1 is not None:
        return _fecha_dia(dia1, mes1, anio1)
    if dia1b is not None:
        return _fecha_dia(dia1b, mes1b, anio1b)
    if dia2 is not None:
        return _fecha_dia(dia2, mes2, anio2)
    if mes3 is not None:
        return f"{anio3}-{_MESES[mes3.lower()]:02d}-01"
    return f"{anio4}-01-01"


def _extraer_articulos(
    html: str, tipo: str, letra: str, fini: str, ffin: str, source: str, on_progress=None
) -> List[RawDocModel]:
    docs: List[RawDocModel] = []
    soup = BeautifulSoup(html, "html.parser")

    for art in soup.find_all("article"):
        titulo_tag = art.select_one("p.text-base.font-semibold")
        if titulo_tag is None:
            continue
        titulo_sitio = titulo_tag.get_text(" ", strip=True)

        enlace = art.select_one("ul.list-disc a[href]")
        if enlace is None:
            if on_progress:
                on_progress(f"[{source}] Aviso: no se encontró enlace de descarga para «{titulo_sitio}», se omite")
            continue
        url = urljoin(_BASE_URL, enlace["href"])

        detalle_tag = art.select_one("p.mt-1.text-sm.leading-tight.text-gray-600")
        detalle = _limpiar_detalle(detalle_tag.get_text(" ", strip=True)) if detalle_tag else None

        numero_match = _NUMERO_PATTERN.search(titulo_sitio)
        numero = numero_match.group(0) if numero_match else None
        resto = _resto_tras_numero(titulo_sitio, numero) if numero else titulo_sitio
        f_providencia = _parse_fecha(resto)

        if f_providencia is None:
            if on_progress:
                on_progress(f"[{source}] Aviso: no se pudo determinar fecha para «{titulo_sitio}», se omite")
            continue
        if f_providencia < fini or f_providencia > ffin:
            continue

        if numero is not None:
            title = _normalize_title(letra, numero, f_providencia[:4])
            title_unverified = False
        else:
            title = titulo_sitio
            title_unverified = True

        safe_title = _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")

        docs.append(RawDocModel(
            source=source,
            link={"url": url, "method": "GET"},
            title=title,
            tipo=tipo,
            f_public=f_providencia,
            f_providencia=f_providencia,
            detalle=detalle,
            save_path=storage_path(source, f_providencia, tipo, f"{safe_title}(extension)"),
            title_unverified=title_unverified,
        ))

    return docs


def _tiene_pagina_siguiente(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    return soup.find("a", rel="next") is not None


def _anos_enlazados(html: str) -> List[int]:
    soup = BeautifulSoup(html, "html.parser")
    anos = set()
    for a in soup.find_all("a", href=True):
        m = re.search(r"/resoluciones/(\d{4})$", a["href"])
        if m:
            anos.add(int(m.group(1)))
    return sorted(anos)


@register_family("mindeporte")
class ScrapMinDeporte(BaseScrapper):
    def __init__(self):
        self.source = "Ministerio del Deporte"

    def _paginar(
        self, session: requests.Session, url_base: str, tipo: str, letra: str, fini: str, ffin: str,
        limit: int, docs: List[RawDocModel], stop_event=None, on_progress=None,
    ) -> None:
        pagina = 1
        while True:
            if stop_event is not None and stop_event.is_set():
                return
            if len(docs) >= limit:
                return

            url = url_base if pagina == 1 else f"{url_base}?page={pagina}"
            try:
                resp = session.get(url, timeout=30)
                resp.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{self.source}] Error consultando {url}: {e}")
                return

            nuevos = _extraer_articulos(resp.text, tipo, letra, fini, ffin, self.source, on_progress=on_progress)
            docs.extend(nuevos)

            # Orden descendente confirmado por fecha real: en cuanto un item
            # (con fecha parseable) queda antes de fini, todo lo que sigue en
            # páginas siguientes también es más viejo — se puede cortar aquí.
            soup = BeautifulSoup(resp.text, "html.parser")
            fechas_pagina = []
            for art in soup.find_all("article"):
                titulo_tag = art.select_one("p.text-base.font-semibold")
                if titulo_tag is None:
                    continue
                titulo_sitio = titulo_tag.get_text(" ", strip=True)
                numero_match = _NUMERO_PATTERN.search(titulo_sitio)
                numero = numero_match.group(0) if numero_match else None
                resto = _resto_tras_numero(titulo_sitio, numero) if numero else titulo_sitio
                fecha = _parse_fecha(resto)
                if fecha is not None:
                    fechas_pagina.append(fecha)

            if fechas_pagina and min(fechas_pagina) < fini:
                return
            if not _tiene_pagina_siguiente(resp.text):
                return

            pagina += 1

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        docs: List[RawDocModel] = []
        for slug, (tipo, letra, por_anio) in _CATEGORIAS.items():
            if stop_event is not None and stop_event.is_set():
                return docs
            if len(docs) >= limit:
                return docs[:limit]
            if on_progress:
                on_progress(f"[{self.source}] Procesando {tipo}...")

            categoria_url = f"{_BASE_URL}{_NORMATIVIDAD_PATH}/{slug}"

            if not por_anio:
                self._paginar(session, categoria_url, tipo, letra, fini, ffin, limit, docs, stop_event, on_progress)
                continue

            try:
                resp = session.get(categoria_url, timeout=30)
                resp.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{self.source}] Error consultando {categoria_url}: {e}")
                continue

            anos = [a for a in _anos_enlazados(resp.text) if str(a) >= fini[:4] and str(a) <= ffin[:4]]
            for ano in anos:
                if stop_event is not None and stop_event.is_set():
                    return docs
                if len(docs) >= limit:
                    return docs[:limit]
                self._paginar(
                    session, f"{categoria_url}/{ano}", tipo, letra, fini, ffin, limit, docs, stop_event, on_progress
                )

        return docs[:limit]
