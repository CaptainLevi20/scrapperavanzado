import re
import unicodedata
from typing import List, Optional, Tuple
from urllib.parse import unquote, urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE = "https://www.supersociedades.gov.co"
_SOURCE = "Superintendencia de Sociedades"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

_MESES = {
    "enero": "ENE", "febrero": "FEB", "marzo": "MAR", "abril": "ABR",
    "mayo": "MAY", "junio": "JUN", "julio": "JUL", "agosto": "AGO",
    "septiembre": "SEP", "setiembre": "SEP", "octubre": "OCT",
    "noviembre": "NOV", "diciembre": "DIC",
}
# sigla -> número de mes (para clasificar semestre y para la fecha del jurídico)
_MES_NUM = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}

_TIPO_JURIDICO = "Boletín Jurídico"
_TIPO_CONTABLE = "Boletín Contable"

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
# sin \b: en el sitio real el año viene pegado al mes ("Septiembre2024",
# "BoletinJuridico-Octubre2021.pdf"). Los lookarounds de dígito evitan además
# leer un año falso dentro de una fecha larga ("...-ABRIL-200520.pdf").
_ANIO_RE = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
# "semestre i" | "semestre ii" | "semestre 1" | "semestre 2" (tras normalizar)
_SEMESTRE_RE = re.compile(r"semestre\s+(ii|i|2|1)\b")


def _sin_acentos(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)
    )


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _mes_a_sigla(texto: str) -> Optional[str]:
    t = _sin_acentos(texto or "").lower()
    # el primero que aparezca por posición en el texto
    encontrados = [(t.find(nombre), sigla) for nombre, sigla in _MESES.items() if nombre in t]
    if not encontrados:
        return None
    return min(encontrados)[1]


def _anio(texto: str) -> Optional[int]:
    m = _ANIO_RE.search(texto or "")
    if not m:
        return None
    n = int(m.group(1))
    return n if 2000 <= n <= 2100 else None


def _periodo_juridico(titulo: str) -> Optional[Tuple[str, int]]:
    mes = _mes_a_sigla(titulo)
    anio = _anio(titulo)
    if mes is None or anio is None:
        return None
    return mes, anio


def _periodo_contable(titulo: str) -> Optional[Tuple[str, int]]:
    anio = _anio(titulo)
    if anio is None:
        return None
    t = _sin_acentos(titulo or "").lower()
    m = _SEMESTRE_RE.search(t)
    if m:
        sem = "SII" if m.group(1) in ("ii", "2") else "SI"
        return sem, anio
    mes = _mes_a_sigla(titulo)
    if mes is not None:
        return ("SI" if _MES_NUM[mes] <= 6 else "SII"), anio
    return None


def _fecha_de_periodo(tipo: str, periodo: Tuple[str, int]) -> Optional[str]:
    clave, anio = periodo
    if tipo == _TIPO_JURIDICO:
        num = _MES_NUM.get(clave)
        return f"{anio:04d}-{num:02d}-01" if num else None
    if tipo == _TIPO_CONTABLE:
        if clave == "SI":
            return f"{anio:04d}-06-30"
        if clave == "SII":
            return f"{anio:04d}-12-31"
    return None


def _titulo(tipo: str, periodo: Optional[Tuple[str, int]], titulo_crudo: str) -> Tuple[str, bool]:
    if periodo is not None:
        clave, anio = periodo
        return f"BOL_SS_{clave}_{anio}", False
    crudo = ((titulo_crudo or "").strip() or "documento")[:120].strip(" .")
    return (crudo or "documento"), True


# Los adjuntos de Liferay viven bajo /documents/<groupId>/<folderId>/<archivo>/<uuid>
_DOC_RE = re.compile(r"/documents/\d+/\d+/")


def _nombre_archivo_pdf(pdf_href: str) -> str:
    """Nombre del archivo PDF dentro de un href de Liferay.

    El href llega codificado ("Bolet%C3%ADn+enero+2026+2.pdf") y con el uuid y
    la query detrás del nombre; esto devuelve sólo "Boletín enero 2026 2.pdf".
    """
    ruta = unquote((pdf_href or "").split("?")[0]).replace("+", " ")
    segmentos = [s for s in ruta.split("/") if s.lower().endswith(".pdf")]
    return segmentos[-1] if segmentos else ""


def _nombre_normalizado_pdf(href: str) -> str:
    """Nombre del PDF en minúsculas y sin tildes, o "" si el href no es un adjunto."""
    if not _DOC_RE.search(href or ""):
        return ""
    return _sin_acentos(_nombre_archivo_pdf(href)).lower()


def _es_pdf_de_boletin(href: str) -> bool:
    """El adjunto es el boletín (y no el decreto del pie ni un banner).

    El nombre del archivo tiene que **empezar** por "bolet": así entran
    `BoletinJuridico-*.pdf`, `Boletin_agosto_2026.pdf`,
    `BOLETIN-CONCEPTOS-*.pdf` o `Boletín enero 2026 2.pdf`, y quedan fuera
    `Banner-Boletin-juridico-septiembre.jpg.pdf` (un banner cuyo nombre
    contiene "Boletin") y `Decreto-Unico-Reglamentario-...pdf` (pie de página).
    """
    return _nombre_normalizado_pdf(href).startswith("bolet")


def _es_pdf_de_conceptos(href: str) -> bool:
    """Respaldo para los boletines de 2019–2020, publicados como
    `CONCEPTOS-JURIDICOS-JULIO-2019.pdf` / `B-CONCEPTOS-JURIDICOS-ENERO-2020.pdf`,
    sin la palabra "Boletín" en el nombre del archivo. Sólo se consulta si el
    artículo no trae ningún PDF que empiece por "Bolet"."""
    nombre = _nombre_normalizado_pdf(href)
    return "conceptos" in nombre and "juridic" in nombre


def _items_de_lista(html: str, link_class: str) -> List[Tuple[str, str]]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: List[Tuple[str, str]] = []
    for a in soup.find_all("a", class_=link_class, href=True):
        titulo = (a.get("title") or a.get_text(" ", strip=True) or "").strip()
        href = a["href"].strip()
        if titulo and href:
            out.append((titulo, href))
    return out


def _pdf_del_articulo(html: str) -> Optional[str]:
    hrefs = [
        a["href"].strip()
        for a in BeautifulSoup(html or "", "html.parser").find_all("a", href=True)
    ]
    for criterio in (_es_pdf_de_boletin, _es_pdf_de_conceptos):
        for href in hrefs:
            if criterio(href):
                return href
    return None


_SECCIONES = [
    (f"{_BASE}/boletines-conceptos-juridicos", _TIPO_JURIDICO,
     "tituloBolConJuriHistorico", _periodo_juridico),
    (f"{_BASE}/boletines-de-conceptos-contables", _TIPO_CONTABLE,
     "tituloBol_ConContHistorico", _periodo_contable),
]


@register_family("supersociedades")
class ScrapSupersociedades(BaseScrapper):
    filters_by_publication_date = True

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": _UA})
        docs: List[RawDocModel] = []

        for url_seccion, tipo, link_class, periodo_fn in _SECCIONES:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            if on_progress:
                on_progress(f"[{_SOURCE}] Procesando {tipo}...")
            try:
                resp = session.get(url_seccion, timeout=60)
                resp.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Error consultando {tipo}: {e}")
                continue

            items = _items_de_lista(resp.text, link_class)
            if not items and on_progress:
                on_progress(
                    f"[{_SOURCE}] Aviso: no se encontró ningún boletín de {tipo} "
                    "(¿cambió el marcado de la página?)"
                )

            vistos: set = set()
            # título generado -> URL del PDF que ya lo ocupó (evita que dos
            # boletines del mismo período compartan save_path y se pisen)
            titulos_emitidos: dict = {}
            sin_pdf_de_boletin = 0
            for titulo, url_articulo in items:
                if stop_event is not None and stop_event.is_set():
                    return docs[:limit]
                periodo = periodo_fn(titulo)
                fecha = _fecha_de_periodo(tipo, periodo) if periodo is not None else None
                # con fecha conocida el rango se aplica antes de abrir el artículo
                if fecha is not None and (fecha < fini or fecha > ffin):
                    continue
                try:
                    art = session.get(urljoin(_BASE, url_articulo), timeout=60)
                    art.raise_for_status()
                except Exception as e:
                    if on_progress:
                        on_progress(f"[{_SOURCE}] Error abriendo boletín «{titulo[:70]}»: {e}")
                    continue
                pdf = _pdf_del_articulo(art.text)
                if not pdf:
                    if fecha is None:
                        # la lista mezcla guías, libros y revistas que no son
                        # boletines: se resumen en una línea al final
                        sin_pdf_de_boletin += 1
                    elif on_progress:
                        on_progress(
                            f"[{_SOURCE}] Aviso: boletín «{titulo[:70]}» sin PDF en el artículo, se omite"
                        )
                    continue
                if fecha is None:
                    # el título no trae año (p. ej. "Boletín Conceptos Jurídicos
                    # – Octubre"): se lee del nombre del archivo PDF
                    periodo = periodo_fn(_nombre_archivo_pdf(pdf))
                    fecha = _fecha_de_periodo(tipo, periodo) if periodo is not None else None
                    if fecha is None:
                        if on_progress:
                            on_progress(
                                f"[{_SOURCE}] Aviso: boletín sin período reconocible ni en el "
                                f"título ni en el PDF «{titulo[:70]}», se omite"
                            )
                        continue
                    if fecha < fini or fecha > ffin:
                        continue
                # la query "?t=<mtime>" cambia en cada republicación y arrastraría
                # el doc_id, así que no se guarda (el PDF responde igual sin ella)
                url_pdf = urljoin(_BASE, pdf).split("?")[0]
                if url_pdf in vistos:
                    continue
                vistos.add(url_pdf)
                title, unverified = _titulo(tipo, periodo, titulo)
                if titulos_emitidos.get(title, url_pdf) != url_pdf:
                    # otro boletín del mismo período ya usó ese título: éste baja
                    # al título crudo del sitio (que sí los distingue)
                    title, unverified = _titulo(tipo, None, titulo)
                titulos_emitidos.setdefault(title, url_pdf)
                safe = _safe_title(title)
                docs.append(RawDocModel(
                    source=_SOURCE,
                    link={"url": url_pdf, "method": "GET"},
                    title=title,
                    tipo=tipo,
                    f_public=fecha,
                    f_providencia=fecha,
                    detalle=titulo or None,
                    save_path=storage_path(_SOURCE, fecha, tipo, f"{safe}(extension)"),
                    title_unverified=unverified,
                ))
                if len(docs) >= limit:
                    return docs[:limit]

            if sin_pdf_de_boletin and on_progress:
                on_progress(
                    f"[{_SOURCE}] {sin_pdf_de_boletin} entradas de {tipo} "
                    "sin PDF de boletín, omitidas"
                )

        return docs[:limit]
