import re
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE_URL = "https://www.minagricultura.gov.co"

# slug de categoría -> (tipo mostrado, letra del código de título)
_CATEGORIAS = {
    "leyes": ("Ley", "L"),
    "decretos": ("Decreto", "D"),
    "resoluciones": ("Resolución", "R"),
    "conpes": ("Conpes", "CONPES"),
}

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_MESES_ALT = "|".join(_MESES.keys())

_DIA = r"(?:0?[1-9]|[12]\d|3[01])"

# Las 4 formas de fecha reales vistas en el sitio, combinadas en UN solo
# patrón con alternancia (en vez de 4 regex probados por separado, cada uno
# buscado sobre la cadena completa). Esto importa por dos razones:
#
# 1. Ninguna alternativa se ancla al final de la cadena ($): el sitio agrega
#    con frecuencia texto libre después de la fecha en data-title (ej. "...
#    DEL 24 DE FEBRERO DE 2026 EESE FInanciamiento", "... DE 2024 Parte 3") —
#    anclar al final descartaba silenciosamente estos documentos reales.
# 2. Al buscarlas como UNA sola alternancia con un único .search(), gana la
#    coincidencia más a la izquierda (posición), y el orden de las
#    alternativas solo desempata cuando varias podrían calzar en la MISMA
#    posición. Probar cada nivel por separado sobre toda la cadena (la
#    versión anterior) dejaba que el nivel 1 (día+mes+año, el más
#    específico) "secuestrara" una fecha completa casual que apareciera más
#    adelante en texto libre de descripción, ignorando la fecha real y
#    correcta que aparece antes pero que solo un nivel menos específico
#    reconoce (ej. "DE OCTUBRE DE 2023 modificado el 5 DE ENERO DEL 2024"
#    debe resolver a 2023-10-01, no a 2024-01-05). Con una sola búsqueda por
#    posición, la fecha real —que siempre aparece primero, justo después del
#    número ya recortado por _resto_tras_numero— gana sin importar qué nivel
#    la reconozca.
#
# El "(?!\d)" al final de cada grupo de año evita que un año se lea como los
# primeros 4 dígitos de un número más largo (ej. no leer "2024" dentro de un
# hipotético "20245").
_FECHA_PATTERN = re.compile(
    r"(?:"
    rf"(?<!\d)({_DIA})\s+(?:DE\s+)?({_MESES_ALT})\s+DEL?\s+(\d{{4}})(?!\d)"
    r"|"
    rf"DE\s+({_MESES_ALT})\s+(?<!\d)({_DIA})\s+DEL?\s+(\d{{4}})(?!\d)"
    r"|"
    rf"DE\s+({_MESES_ALT})\s+DEL?\s+(\d{{4}})(?!\d)"
    r"|"
    r"\bDEL?\s*(\d{4})(?!\d)"
    r")",
    re.IGNORECASE,
)


def _resto_tras_numero(data_title: str, numero: str) -> str:
    idx = data_title.find(numero)
    if idx == -1:
        return data_title
    return data_title[idx + len(numero):]


def _normalize_title(letra: str, numero: str, anio: str) -> str:
    return f"{letra}_MADR_{int(numero):04d}_{anio}"


def _parse_fecha(texto: str) -> Optional[str]:
    m = _FECHA_PATTERN.search(texto)
    if not m:
        return None

    dia1, mes1, anio1, mes2, dia2, anio2, mes3, anio3, anio4 = m.groups()

    if dia1 is not None:
        return f"{anio1}-{_MESES[mes1.lower()]:02d}-{int(dia1):02d}"
    if dia2 is not None:
        return f"{anio2}-{_MESES[mes2.lower()]:02d}-{int(dia2):02d}"
    if mes3 is not None:
        return f"{anio3}-{_MESES[mes3.lower()]:02d}-01"
    return f"{anio4}-01-01"


@register_family("madr")
class ScrapMADR(BaseScrapper):
    def __init__(self):
        self.source = "Ministerio de Agricultura y Desarrollo Rural"

    def _extraer_articulos(self, html: str, tipo: str, letra: str, fini: str, ffin: str, on_progress=None) -> List[RawDocModel]:
        docs: List[RawDocModel] = []
        soup = BeautifulSoup(html, "html.parser")

        for art in soup.find_all("article", class_="item_norm"):
            data_title = (art.get("data-title") or "").strip()
            numero = (art.get("data-number") or "").strip()
            detalle = (art.get("data-info") or "").strip() or None
            if detalle:
                detalle = detalle.strip('"')

            enlace = art.find("a", href=True)
            if not enlace:
                continue
            url = urljoin(_BASE_URL, enlace["href"])

            resto = _resto_tras_numero(data_title, numero) if numero else data_title
            fecha = _parse_fecha(resto)
            if fecha is None:
                if on_progress:
                    on_progress(f"[{self.source}] Aviso: no se pudo determinar fecha para «{data_title}», se omite")
                continue
            if fecha < fini or fecha > ffin:
                continue

            if numero:
                title = _normalize_title(letra, numero, fecha[:4])
                title_unverified = False
            else:
                title = data_title
                title_unverified = True

            safe_title = _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")

            docs.append(RawDocModel(
                source=self.source,
                link={"url": url, "method": "GET"},
                title=title,
                tipo=tipo,
                f_public=fecha,
                detalle=detalle,
                save_path=storage_path(self.source, fecha, tipo, f"{safe_title}(extension)"),
                title_unverified=title_unverified,
            ))

        return docs

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        docs: List[RawDocModel] = []
        for categoria, (tipo, letra) in _CATEGORIAS.items():
            if stop_event is not None and stop_event.is_set():
                return docs
            if on_progress:
                on_progress(f"[{self.source}] Procesando {tipo}...")

            try:
                resp = session.get(f"{_BASE_URL}/normatividad/{categoria}", timeout=30)
                resp.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{self.source}] Error consultando {categoria}: {e}")
                continue

            docs.extend(self._extraer_articulos(resp.text, tipo, letra, fini, ffin, on_progress=on_progress))
            if len(docs) >= limit:
                return docs[:limit]

        return docs
