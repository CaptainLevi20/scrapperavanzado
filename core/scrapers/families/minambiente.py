import datetime
import re
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE_URL = "https://www.minambiente.gov.co"
_AJAX_URL = f"{_BASE_URL}/wp-admin/admin-ajax.php"
_AJAX_ACTION = "normativa_paginacion-load-posts-2"

# slug (solo para logging) -> (termID del sitio, tipo mostrado, letra del código de título)
# "Conpes"/"CONPES" y "Concepto" se tratan aparte (ver _CONCEPTOS_TERM_ID / letra literal).
# "Circular" usa letra "C" (misma convención que mincit.py) pero su número real
# es un código de radicado alfanumérico, no un consecutivo — ver
# _CODIGO_CIRCULAR_PATTERN más abajo.
_CATEGORIAS = {
    "resoluciones": (46, "Resolución", "R"),
    "leyes": (47, "Ley", "L"),
    "decretos": (48, "Decreto", "D"),
    "autos": (58, "Auto", "A"),
    "conpes": (61, "Conpes", "CONPES"),
    "circulares": (60, "Circular", "C"),
}
_CONCEPTOS_TERM_ID = 962
_CONCEPTOS_TIPO = "Concepto"

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_MESES_ALT = "|".join(_MESES.keys())

_DIA = r"(?:0?[1-9]|[12]\d|3[01])"

# Misma técnica de cascada que core/scrapers/families/madr.py: una sola
# alternancia (no 4 regex probados por separado) para que gane la fecha real
# que aparece primero en el resto del título, en vez de que una fecha
# casual en texto libre posterior "secuestre" el resultado.
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

_NUMERO_PATTERN = re.compile(r"\d+")
# Las Circulares no numeran con un consecutivo corto: usan un código de
# radicado que mezcla dígitos y una letra, con el año embebido al inicio
# (ej. "10002026E4000041" en "Circular 10002026E4000041 del 23 de julio de
# 2026"). Un \d+ simple lo cortaría en el primer bloque de dígitos
# ("10002026"), perdiendo el resto del código — se exige que empiece y
# termine en dígito, con letras/dígitos en el medio, como un solo token
# contiguo (sin espacios). Si una Circular no trae un código así (ej.
# "Circular de medidas y recomendaciones..."), no matchea; si además esa
# entrada no tiene ninguna fecha reconocible en el título (caso real
# observado), se descarta por completo, igual que cualquier otra categoría
# sin fecha parseable.
_CODIGO_CIRCULAR_PATTERN = re.compile(r"\d[\dA-Za-z]*\d")
_PUBLICADO_PATTERN = re.compile(
    rf"Publicado:\s*({_MESES_ALT})\s+(\d{{1,2}}),\s*(\d{{4}})", re.IGNORECASE
)
_FECHA_CONCEPTO_PATTERN = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def _resto_tras_numero(titulo: str, numero: str) -> str:
    idx = titulo.find(numero)
    if idx == -1:
        return titulo
    return titulo[idx + len(numero):]


def _parse_fecha(texto: str) -> Optional[str]:
    m = _FECHA_PATTERN.search(texto)
    if not m:
        return None

    dia1, mes1, anio1, mes2, dia2, anio2, mes3, anio3, anio4 = m.groups()

    if dia1 is not None:
        mes_num = _MESES[mes1.lower()]
        try:
            datetime.date(int(anio1), mes_num, int(dia1))
        except ValueError:
            return f"{anio1}-{mes_num:02d}-01"
        return f"{anio1}-{mes_num:02d}-{int(dia1):02d}"
    if dia2 is not None:
        mes_num = _MESES[mes2.lower()]
        try:
            datetime.date(int(anio2), mes_num, int(dia2))
        except ValueError:
            return f"{anio2}-{mes_num:02d}-01"
        return f"{anio2}-{mes_num:02d}-{int(dia2):02d}"
    if mes3 is not None:
        return f"{anio3}-{_MESES[mes3.lower()]:02d}-01"
    return f"{anio4}-01-01"


def _parse_publicado(texto: str) -> Optional[str]:
    m = _PUBLICADO_PATTERN.search(texto)
    if not m:
        return None
    mes, dia, anio = m.groups()
    return f"{anio}-{_MESES[mes.lower()]:02d}-{int(dia):02d}"


def _parse_fecha_concepto(texto: str) -> Optional[str]:
    m = _FECHA_CONCEPTO_PATTERN.search(texto)
    if not m:
        return None
    dia, mes, anio = m.groups()
    try:
        datetime.date(int(anio), int(mes), int(dia))
    except ValueError:
        return None
    return f"{anio}-{int(mes):02d}-{int(dia):02d}"


def _normalize_title(letra: str, numero: str, anio: str) -> str:
    if letra == "C":
        # El código de radicado de Circulares ya viene con su propio formato
        # fijo (no es un consecutivo corto) — se usa tal cual, sin forzarlo a
        # entero ni rellenarlo con ceros.
        return f"C_MADS_{numero}_{anio}"
    return f"{letra}_MADS_{int(numero):04d}_{anio}"


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


@register_family("minambiente")
class ScrapMinAmbiente(BaseScrapper):
    # "Publicado:" (que alimenta f_public) puede re-timestampear el mismo
    # archivo por reindexado/migración del CMS del sitio (verificado: un
    # Decreto de 2022 aparece "Publicado: julio 10, 2024") — igual que
    # rama_judicial/samai, el doc_id no debe depender de un campo que puede
    # cambiar para el mismo documento, o un simple reindexado del sitio lo
    # duplicaría en la base de datos.
    doc_id_uses_publication_date = False

    def __init__(self):
        self.source = "Ministerio de Ambiente y Desarrollo Sostenible"

    def _fetch_categoria(self, session, term_id: int) -> str:
        resp = session.post(
            _AJAX_URL,
            data={"page": 1, "area1": term_id, "action": _AJAX_ACTION},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.text

    def _extraer_normas(self, html: str, tipo: str, letra: str, fini: str, ffin: str) -> List[RawDocModel]:
        docs: List[RawDocModel] = []
        soup = BeautifulSoup(html, "html.parser")

        for bloque in soup.find_all("div", class_="box-docgd"):
            enlace = bloque.find("a", class_="documento-normativa", href=True)
            if not enlace:
                continue
            url = urljoin(_BASE_URL, enlace["href"])
            titulo_sitio = enlace.get_text(strip=True)

            descripcion = bloque.find("p", class_="descripcion-archivo")
            detalle = descripcion.get_text(" ", strip=True).strip('"') if descripcion else None

            publicado_span = bloque.find("span", class_="txt-peque-archivo")
            f_public = _parse_publicado(publicado_span.get_text(strip=True)) if publicado_span else None

            patron_numero = _CODIGO_CIRCULAR_PATTERN if tipo == "Circular" else _NUMERO_PATTERN
            numero_match = patron_numero.search(titulo_sitio)
            numero = numero_match.group(0) if numero_match else None
            resto = _resto_tras_numero(titulo_sitio, numero) if numero else titulo_sitio
            f_providencia = _parse_fecha(resto)

            if f_providencia is None:
                title = titulo_sitio
                title_unverified = True
                fecha_filtro = f_providencia
            else:
                fecha_filtro = f_providencia
                if numero is not None:
                    title = _normalize_title(letra, numero, f_providencia[:4])
                    title_unverified = False
                else:
                    title = titulo_sitio
                    title_unverified = True

            if fecha_filtro is None or fecha_filtro < fini or fecha_filtro > ffin:
                continue

            # "Publicado:" es un campo informativo del sitio, no siempre presente
            # (raro) y sujeto a re-timestamping por reindexado del CMS (ver nota en
            # doc_id_uses_publication_date más abajo) — nunca se usa para filtrar ni
            # para identidad, pero f_public es obligatorio en RawDocModel, así que si
            # falta se usa la fecha real del acto (f_providencia, ya validada arriba).
            if f_public is None:
                f_public = f_providencia

            safe = _safe_title(title)

            docs.append(RawDocModel(
                source=self.source,
                link={"url": url, "method": "GET"},
                title=title,
                tipo=tipo,
                f_public=f_public,
                f_providencia=f_providencia,
                detalle=detalle,
                save_path=storage_path(self.source, f_providencia, tipo, f"{safe}(extension)"),
                title_unverified=title_unverified,
            ))

        return docs

    def _extraer_conceptos(self, html: str, fini: str, ffin: str) -> List[RawDocModel]:
        docs: List[RawDocModel] = []
        soup = BeautifulSoup(html, "html.parser")

        for bloque in soup.find_all("div", class_="box-docgd"):
            tabla = bloque.find("table")
            if tabla is None:
                continue

            filas = tabla.find_all("tr")
            for fila in filas[1:]:  # la primera fila es el encabezado
                celdas = fila.find_all("td")
                if len(celdas) < 5:
                    continue

                f_providencia = _parse_fecha_concepto(celdas[1].get_text(strip=True))
                if f_providencia is None:
                    continue
                if f_providencia < fini or f_providencia > ffin:
                    continue

                rad_salida = celdas[2].get_text(strip=True)
                tema = celdas[3].get_text(strip=True) or None

                enlace = celdas[4].find("a", href=True)
                if not enlace:
                    continue
                url = urljoin(_BASE_URL, enlace["href"])

                if rad_salida:
                    title = f"CONCEPTO_MADS_{rad_salida}"
                    title_unverified = False
                else:
                    title = tema or url.rsplit("/", 1)[-1]
                    title_unverified = True

                safe = _safe_title(title)

                docs.append(RawDocModel(
                    source=self.source,
                    link={"url": url, "method": "GET"},
                    title=title,
                    tipo=_CONCEPTOS_TIPO,
                    # Conceptos solo trae una fecha real (columna "Fecha" de la
                    # tabla); se duplica en f_public porque el campo es obligatorio
                    # en RawDocModel, manteniendo f_providencia como la fecha que
                    # de verdad gobierna el filtro fini/ffin en toda la familia.
                    f_public=f_providencia,
                    f_providencia=f_providencia,
                    detalle=tema,
                    save_path=storage_path(self.source, f_providencia, _CONCEPTOS_TIPO, f"{safe}(extension)"),
                    title_unverified=title_unverified,
                ))

        return docs

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        docs: List[RawDocModel] = []

        for _slug, (term_id, tipo, letra) in _CATEGORIAS.items():
            if stop_event is not None and stop_event.is_set():
                return docs
            if on_progress:
                on_progress(f"[{self.source}] Procesando {tipo}...")

            try:
                html = self._fetch_categoria(session, term_id)
            except Exception as e:
                if on_progress:
                    on_progress(f"[{self.source}] Error consultando {tipo}: {e}")
                continue

            docs.extend(self._extraer_normas(html, tipo, letra, fini, ffin))
            if len(docs) >= limit:
                return docs[:limit]

        if stop_event is not None and stop_event.is_set():
            return docs
        if on_progress:
            on_progress(f"[{self.source}] Procesando {_CONCEPTOS_TIPO}...")

        try:
            html = self._fetch_categoria(session, _CONCEPTOS_TERM_ID)
        except Exception as e:
            if on_progress:
                on_progress(f"[{self.source}] Error consultando {_CONCEPTOS_TIPO}: {e}")
            return docs[:limit]

        docs.extend(self._extraer_conceptos(html, fini, ffin))
        return docs[:limit]
