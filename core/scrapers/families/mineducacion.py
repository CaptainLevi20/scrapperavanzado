import re
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE_URL = "https://normograma.info/men/compilacion/compilacion/"

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')

# slug de categoría (solo logging) -> (nombre base del archivo del Normograma,
# tipo mostrado, letra del código de título). El Normograma organiza cada
# tipo de norma por entidad de origen -- se usa siempre la página de la
# entidad correcta para el sector educación: el propio Ministerio para
# Resolución/Circular/Directiva/Acuerdo/Concepto, pero Presidencia para
# Decreto y Congreso para Ley (son quienes realmente los expiden). A pedido
# explícito del usuario el alcance se queda acotado a estas 7 -- el
# Normograma también compila normativa de decenas de otras entidades del
# sector (SENA, ICETEX, universidades públicas, JEP...), que se dejó fuera
# a propósito.
_CATEGORIAS = {
    "resoluciones": ("cndser_ministerio_educacion_nacional", "Resolución", "R"),
    "decretos": ("cndsed_presidencia_republica", "Decreto", "D"),
    "circulares": ("cndsec_ministerio_educacion_nacional", "Circular", "C"),
    "directivas": ("cndsed_ministerio_educacion_nacional", "Directiva", "DIRECTIVA"),
    "acuerdos": ("cndsea_ministerio_educacion_nacional", "Acuerdo", "A"),
    "leyes": ("cndsel_congreso_republica", "Ley", "L"),
    "conceptos": ("c-dc_occ_ministerio_educacion_nacional", "Concepto", "CONCEPTO"),
}

# Formato real, uniforme en las 7 categorías (confirmado contra 1269 filas
# reales muestreadas, de 2026 hasta 1905, cero excepciones): "{Tipo}
# {numero} de {año}", con un " ME" final opcional (presente cuando el
# Ministerio mismo expide el documento; ausente para Decreto/Ley, que son de
# Presidencia/Congreso). No se necesita capturar la palabra de tipo: ya se
# conoce de antemano, viene de qué página se está scrapeando.
_ID_DOCUMENTO_PATTERN = re.compile(r"^\S+\s+(\S+)\s+de\s+(\d{4})(?:\s+ME)?$")


def _normalize_title(letra: str, numero: str, anio: str) -> str:
    if not numero.isdigit():
        return f"{letra}_MEN_{numero}_{anio}"
    return f"{letra}_MEN_{int(numero):04d}_{anio}"


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _pdf_href_from_doc_href(doc_href: str) -> str:
    # El enlace real de cada fila apunta a la página HTML transcrita del
    # documento ("docs/resolucion_..._2026.htm"), no al PDF -- el PDF real
    # vive en una ruta paralela "docs/pdf/....pdf" (confirmado inspeccionando
    # docFunction.js del visor: pathDocumentosPDF = "pdf/", concatenado al
    # nombre de archivo sin extensión + ".pdf"). No hace falta visitar la
    # página del documento para averiguarlo -- es una transformación de
    # texto sobre el propio href del listado.
    carpeta, _, archivo = doc_href.rpartition("/")
    nombre = archivo.rsplit(".", 1)[0]
    carpeta_pdf = f"{carpeta}/pdf" if carpeta else "pdf"
    return f"{carpeta_pdf}/{nombre}.pdf"


def _extraer_fila(fila, tipo: str, letra: str, on_progress=None, source: str = ""):
    idd_tag = fila.select_one(".id-documento")
    enlace = fila.find("a", href=True)
    if idd_tag is None or enlace is None:
        return None

    texto = idd_tag.get_text(strip=True)
    m = _ID_DOCUMENTO_PATTERN.match(texto)
    if not m:
        if on_progress:
            on_progress(f"[{source}] Aviso: formato de documento no reconocido «{texto}», se omite")
        return None
    numero, anio = m.groups()

    desc_tag = fila.select_one(".descripcion-documento")
    detalle = desc_tag.get_text(" ", strip=True) if desc_tag else None

    url = urljoin(_BASE_URL, _pdf_href_from_doc_href(enlace["href"]))
    f_public = f"{anio}-01-01"
    title = _normalize_title(letra, numero, anio)
    safe = _safe_title(title)

    return anio, RawDocModel(
        source=source,
        link={"url": url, "method": "GET"},
        title=title,
        tipo=tipo,
        f_public=f_public,
        detalle=detalle,
        save_path=storage_path(source, f_public, tipo, f"{safe}(extension)"),
        title_unverified=False,
    )


@register_family("mineducacion")
class ScrapMineducacion(BaseScrapper):
    # f_public viene del propio identificador del documento en el Normograma
    # (solo año, sin día/mes -- el listado no da más precisión), no de un
    # timestamp de reindexado del sitio que pueda cambiar para el mismo
    # archivo -- es intrínseco al documento.
    doc_id_uses_publication_date = True

    def __init__(self):
        self.source = "Ministerio de Educación Nacional"

    def _extraer_filas_pagina(self, html: str, tipo: str, letra: str, on_progress=None):
        """Devuelve {año: [RawDocModel, ...]} con todas las filas de esta página."""
        soup = BeautifulSoup(html, "html.parser")
        por_anio: dict = {}
        for fila in soup.select("div.opcion-nueva"):
            resultado = _extraer_fila(fila, tipo, letra, on_progress=on_progress, source=self.source)
            if resultado is None:
                continue
            anio, doc = resultado
            por_anio.setdefault(anio, []).append(doc)
        return por_anio

    def _anios_disponibles(self, html: str) -> List[str]:
        soup = BeautifulSoup(html, "html.parser")
        return [
            opt.get_text(strip=True)
            for opt in soup.select("select option")
            if opt.get_text(strip=True).isdigit()
        ]

    def _scrap_categoria(self, session, base_filename: str, tipo: str, letra: str, fini: str, ffin: str, on_progress=None) -> List[RawDocModel]:
        docs: List[RawDocModel] = []
        try:
            resp = session.get(_BASE_URL + base_filename + ".html", timeout=60)
            resp.raise_for_status()
        except Exception as e:
            if on_progress:
                on_progress(f"[{self.source}] Error consultando {tipo}: {e}")
            return docs

        anio_ini, anio_fin = int(fini[:4]), int(ffin[:4])
        anios_disponibles = self._anios_disponibles(resp.text)
        por_anio = self._extraer_filas_pagina(resp.text, tipo, letra, on_progress=on_progress)

        anios_necesarios = {a for a in anios_disponibles if anio_ini <= int(a) <= anio_fin}
        # El Normograma solo genera páginas separadas por año cuando una
        # categoría tiene suficiente volumen histórico -- una categoría
        # pequeña (ej. Acuerdo, 6 años) trae TODOS sus años ya embebidos en
        # la página base y no tiene archivos "_{año}.html" separados en
        # absoluto (pedir un GET aparte devolvería 404). Por eso el año que
        # falta se calcula DESPUÉS de ver qué años trajo realmente la
        # página base, en vez de asumir que solo el año más reciente viene
        # incluido.
        anios_faltantes = sorted(anios_necesarios - set(por_anio.keys()))

        for anio in anios_faltantes:
            try:
                resp_anio = session.get(_BASE_URL + base_filename + "_" + anio + ".html", timeout=60)
                resp_anio.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{self.source}] Error consultando {tipo} {anio}: {e}")
                continue
            por_anio_extra = self._extraer_filas_pagina(resp_anio.text, tipo, letra, on_progress=on_progress)
            por_anio.update(por_anio_extra)

        for filas in por_anio.values():
            for doc in filas:
                if fini <= doc.f_public <= ffin:
                    docs.append(doc)

        return docs

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        docs: List[RawDocModel] = []
        for _slug, (base_filename, tipo, letra) in _CATEGORIAS.items():
            if stop_event is not None and stop_event.is_set():
                return docs
            if on_progress:
                on_progress(f"[{self.source}] Procesando {tipo}...")

            docs.extend(
                self._scrap_categoria(session, base_filename, tipo, letra, fini, ffin, on_progress=on_progress)
            )
            if len(docs) >= limit:
                return docs[:limit]

        return docs[:limit]
