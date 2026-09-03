import re
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.naming import codigo_ley_decreto
from core.utils import storage_path

_BASE_URL = "https://minvivienda.gov.co"
_LISTADO_URL = f"{_BASE_URL}/normativa"
_FILAS_POR_PAGINA = 20

# slug de categoría (solo logging) -> (valor real de "tipo" en la URL del
# sitio -- confirmado con fetch, es singular y con tilde donde aplique;
# "tipo=Resoluciones" en plural no devuelve resultados -- letra del código
# de título)
_CATEGORIAS = {
    "resoluciones": ("Resolución", "R"),
    "decretos": ("Decreto", "D"),
    "leyes": ("Ley", "L"),
    "conpes": ("CONPES", "CONPES"),
    "acuerdos": ("Acuerdo", "A"),
    "directivas": ("Directiva", "DIR"),
    "circulares": ("Circular", "C"),
    "autos": ("Auto", "AU"),
}

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')

# Número corto pegado a su año, en cualquier parte del título (no anclado al
# final): cubre tanto "Resolución 0786 - 2026" (numero al final) como
# "Directiva 006 - 2019 de la Procuraduría..." / "Circular 031 - 2011 -
# Procuraduría" (texto colgando después del año, real en el sitio).
# El separador ("-"/"de") exige espacio a cada lado a propósito: en un
# "numero - año" real siempre hay espacios (confirmado en el muestreo real).
# Sin ese requisito, el patrón matchea dentro de números de expediente/
# radicado largos sin espacios (ej. "Auto admisorio ... 50001-23-33-000-2026-
# 00192-00", donde "000-2026" parece válido pero es un fragmento del
# radicado, no el número real del Auto).
_NUMERO_CORTO_PATTERN = re.compile(r"(?:No\.?\s*)?(\d{1,4})\s+(?:-|de)\s+\d{4}", re.IGNORECASE)
# Las Circulares con código de radicado (sin consecutivo corto, ej.
# "2026EE0026348" en "Circular 2026EE0026348") mezclan dígitos y letras --
# mismo patrón que minambiente.py, se exige que empiece y termine en dígito.
_CODIGO_CIRCULAR_PATTERN = re.compile(r"\d[\dA-Za-z]*\d")

_FECHA_PUBLICACION_PATTERN = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def _extraer_numero(titulo: str, tipo: str) -> Optional[str]:
    m = _NUMERO_CORTO_PATTERN.search(titulo)
    if m:
        return m.group(1)
    if tipo == "Circular":
        m = _CODIGO_CIRCULAR_PATTERN.search(titulo)
        if m:
            return m.group(0)
    return None


def _normalize_title(letra: str, numero: str, anio: str) -> str:
    if not numero.isdigit():
        # Código de radicado de Circular: no es un consecutivo corto, se usa
        # tal cual, sin int()/zero-pad.
        return f"{letra}_MVCT_{numero}_{anio}"
    return codigo_ley_decreto(letra, numero, anio) or f"{letra}_MVCT_{int(numero):04d}_{anio}"


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


# La categoría "Auto" del sitio mezcla Autos reales con Sentencias, Avisos
# judiciales y Circulares mal etiquetadas (verificado con fetch real) -- se
# reclasifica cada fila por la palabra inicial de su propio título, más
# confiable que la etiqueta de categoría del sitio.
def _clasificar_fila_auto(titulo: str) -> Tuple[str, str]:
    low = titulo.strip().lower()
    if low.startswith("circular"):
        return "Circular", "C"
    if low.startswith("sentencia"):
        return "Sentencia", "S"
    if low.startswith("aviso"):
        return "Aviso", "AV"
    return "Auto", "AU"


def _parse_f_public(texto: str) -> Optional[str]:
    m = _FECHA_PUBLICACION_PATTERN.search(texto)
    if not m:
        return None
    dia, mes, anio = m.groups()
    return f"{anio}-{mes}-{dia}"


@register_family("minvivienda")
class ScrapMinvivienda(BaseScrapper):
    # "Fecha de publicación" (created, que alimenta f_public) puede
    # re-timestampear el mismo archivo por reindexado/migración del CMS del
    # sitio (verificado: una Resolución de 2000 aparece "Publicado" en 2020,
    # 20 años después) -- igual que minambiente/rama_judicial/samai, el
    # doc_id no debe depender de un campo que puede cambiar para el mismo
    # documento, o un simple reindexado lo duplicaría en la base de datos.
    doc_id_uses_publication_date = False

    def __init__(self):
        self.source = "Ministerio de Vivienda, Ciudad y Territorio"

    def _fetch_pagina(self, session, tipo: str, page: int) -> str:
        # `tipo` va sin percent-encode manual a propósito: `requests` ya
        # codifica los valores de `params` -- pre-codificarlo (con
        # urllib.parse.quote) lo codifica dos veces (ej. "ó" -> "%C3%B3" ->
        # "%25C3%25B3"), lo que el sitio real no reconoce y devuelve 0
        # resultados. Confirmado con un chequeo en vivo contra el sitio.
        resp = session.get(
            _LISTADO_URL,
            params={"tipo": tipo, "page": page},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.text

    def _extraer_fila(self, fila, tipo_categoria: str, letra_categoria: str) -> Optional[RawDocModel]:
        enlace_titulo = fila.select_one(".listing-title a")
        if not enlace_titulo:
            return None
        titulo_sitio = enlace_titulo.get_text(strip=True)

        if tipo_categoria == "Auto":
            tipo, letra = _clasificar_fila_auto(titulo_sitio)
        else:
            tipo, letra = tipo_categoria, letra_categoria

        fecha_tag = fila.select_one(".views-field-field-legal-regulation-date time[datetime]")
        if not fecha_tag or not fecha_tag.get("datetime"):
            return None
        f_providencia = fecha_tag["datetime"][:10]

        enlace_archivo = fila.select_one(".views-field-field-legal-regulation-file a[href]")
        if not enlace_archivo:
            return None
        url = urljoin(_BASE_URL, enlace_archivo["href"])

        creado_tag = fila.select_one(".views-field-created .field-content")
        f_public = _parse_f_public(creado_tag.get_text(strip=True)) if creado_tag else None
        if f_public is None:
            f_public = f_providencia

        resumen_tag = fila.select_one(".views-field-field-summary p") or fila.select_one(
            ".views-field-field-summary .field-content"
        )
        detalle = resumen_tag.get_text(" ", strip=True) if resumen_tag else None

        numero = _extraer_numero(titulo_sitio, tipo)
        if numero is not None:
            title = _normalize_title(letra, numero, f_providencia[:4])
            title_unverified = False
        else:
            title = titulo_sitio
            title_unverified = True

        safe = _safe_title(title)

        return RawDocModel(
            source=self.source,
            link={"url": url, "method": "GET"},
            title=title,
            tipo=tipo,
            f_public=f_public,
            f_providencia=f_providencia,
            detalle=detalle,
            save_path=storage_path(self.source, f_providencia, tipo, f"{safe}(extension)"),
            title_unverified=title_unverified,
        )

    def _extraer_pagina(self, html: str, tipo_categoria: str, letra_categoria: str, fini: str, ffin: str):
        """Devuelve (documentos_en_rango, hay_filas, todas_por_debajo_de_fini)."""
        soup = BeautifulSoup(html, "html.parser")
        filas = soup.select("div.views-row")

        docs: List[RawDocModel] = []
        todas_viejas = True

        for fila in filas:
            doc = self._extraer_fila(fila, tipo_categoria, letra_categoria)
            if doc is None:
                continue
            if doc.f_providencia >= fini:
                todas_viejas = False
            if fini <= doc.f_providencia <= ffin:
                docs.append(doc)

        return docs, bool(filas), todas_viejas

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        docs: List[RawDocModel] = []

        for _slug, (tipo_categoria, letra_categoria) in _CATEGORIAS.items():
            if stop_event is not None and stop_event.is_set():
                return docs
            if on_progress:
                on_progress(f"[{self.source}] Procesando {tipo_categoria}...")

            page = 0
            while True:
                if stop_event is not None and stop_event.is_set():
                    return docs

                try:
                    html = self._fetch_pagina(session, tipo_categoria, page)
                except Exception as e:
                    if on_progress:
                        on_progress(f"[{self.source}] Error consultando {tipo_categoria} (página {page}): {e}")
                    break

                pagina_docs, hay_filas, todas_viejas = self._extraer_pagina(
                    html, tipo_categoria, letra_categoria, fini, ffin
                )
                docs.extend(pagina_docs)
                if len(docs) >= limit:
                    return docs[:limit]

                if not hay_filas or todas_viejas:
                    break
                page += 1

        return docs[:limit]
