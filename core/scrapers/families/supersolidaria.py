import datetime
import re
import unicodedata
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
import urllib3
from bs4 import BeautifulSoup

from core.fecha_es import parse_fecha_providencia_es
from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

# www.supersolidaria.gov.co entrega una cadena TLS incompleta (le falta el
# certificado intermedio), así que `certifi` no puede validarla y `requests`
# aborta con CERTIFICATE_VERIFY_FAILED aunque `curl` —que usa el almacén de
# confianza del sistema— sí pase. Mismo caso que la Corte Constitucional, la
# CNDJ, la SSF y la SNR: se salta la verificación TLS para este host (sesión
# aquí + link["verify"] = False para la descarga posterior).
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_BASE = "https://www.supersolidaria.gov.co"
_SOURCE = "Superintendencia de la Economía Solidaria"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
_ANIO_MIN = 2015
_MAX_TITULO = 120

_URL_CONCEPTOS = f"{_BASE}/es/conceptos-juridicos-y-contables"

# (url, tipo mostrado, prefijo de título, fecha_por_prosa, avisa_doc_a_doc)
# `avisa_doc_a_doc=False` en Circulares Conjuntas: esa página no tiene
# encabezados de año ni prefijos de fecha en los archivos, así que sus 6
# adjuntos (2001-2009, todos bajo el piso) se descartan siempre; en vez de 6
# avisos por corrida se emite una sola línea resumen.
_SECCIONES_TABLA = [
    (f"{_BASE}/es/content/resoluciones-generales", "Resolución", "R", True, True),
    (f"{_BASE}/es/content/circulares-externas-por-ano", "Circular Externa", "CE", False, True),
    (f"{_BASE}/es/content/circulares-conjuntas", "Circular Conjunta", "CJ", False, False),
    (f"{_BASE}/es/content/cartas-circulares", "Carta Circular", "CC", False, True),
]

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_H2_ANIO_RE = re.compile(
    r"(?i)(?:resoluciones\s+generales|circulares\s+externas|cartas\s+circulares)\s*(20\d{2})\b"
)
_FECHA_ARCHIVO_RE = re.compile(r"/(\d{4})(\d{2})(\d{2})_[^/]+$")
# Radicado de resolución: año de 4 dígitos + letras opcionales intercaladas +
# consecutivo + letra final opcional. Casos reales: `2025430007935`,
# `2023SES008005`, `202506201000001R`. Los límites son «no alfanumérico» (y no
# `\b`) para que `Resolución_2019300001805` también case, ya que `_` es \w.
_RADICADO_RE = re.compile(r"(?i)(?<![0-9A-Z])(\d{4}[A-Z]{0,4}\d{6,}[A-Z]{0,4})(?![0-9A-Z])")
# Forma corta antigua: el número va inmediatamente después de «Resolución»
# (`Resolución 745 de 2003`, `Resolución 001 – Enero 2009`).
_CORTO_RE = re.compile(r"(?i)\bresoluci[oó]n\s*(?:N[°ºo]\.?|Nro\.?)?\s*0*(\d{1,5})\b(?!\d)")
_NUM_MARCADO_RE = re.compile(r"(?:N[°º]|No\.?|Nro\.?)\s*0*(\d+)", re.IGNORECASE)
# Respaldo para circulares/cartas sin marcador: `Circular Externa 52`,
# `Carta Circular 001`. `(\d{1,4})\b(?!\d)` evita morder radicados largos como
# `Circular Externa 20224400083742`, que quedan sin verificar (correcto).
_NUM_TRAS_TIPO_RE = re.compile(
    r"(?i)(?:circular(?:\s+externa|\s+conjunta)?|carta\s+circular)\s*0*(\d{1,4})\b(?!\d)"
)
_ANEXO_RE = re.compile(r"^(anexo|matriz de)\b")
_EXTENSION_RE = re.compile(r"\.[A-Za-z0-9]{1,5}$")


def _sin_acentos(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)
    )


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:_MAX_TITULO].strip(" .")


def _stem_del_href(href: str) -> str:
    """Nombre del archivo sin extensión, saneado. Discriminador determinista
    (misma URL -> mismo sufijo en cada corrida) para títulos que colisionan."""
    nombre = (href or "").split("?")[0].split("#")[0].rstrip("/").split("/")[-1]
    return _INVALID_PATH_CHARS.sub("-", _EXTENSION_RE.sub("", nombre))[:60].strip(" .")


def _es_anexo(titulo: str) -> bool:
    return bool(_ANEXO_RE.match(_sin_acentos(titulo or "").strip().lower()))


def _num_seccion(prefijo: str, titulo: str) -> Optional[int]:
    t = titulo or ""
    if prefijo == "R":
        m = _RADICADO_RE.search(t)
        if m:
            # los últimos 6 dígitos del radicado (ignorando las letras)
            return int(re.sub(r"[^\d]", "", m.group(1))[-6:])
        m = _CORTO_RE.search(t)
        return int(m.group(1)) if m else None
    m = _NUM_MARCADO_RE.search(t) or _NUM_TRAS_TIPO_RE.search(t)
    return int(m.group(1)) if m else None


def _anio_de_h2(texto: str) -> Optional[int]:
    m = _H2_ANIO_RE.search(_sin_acentos(texto or ""))
    return int(m.group(1)) if m else None


def _prefijo_fecha_archivo(href: str) -> Optional[str]:
    m = _FECHA_ARCHIVO_RE.search((href or "").split("?")[0])
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    try:
        return datetime.date(y, mo, d).isoformat()
    except ValueError:
        return None


def _crudo(titulo: str) -> str:
    """Título original de la página, recortado y saneado como título de respaldo."""
    return ((titulo or "").strip() or "documento")[:_MAX_TITULO].strip(" .") or "documento"


def _con_discriminador(base: str, disc: str) -> str:
    """`base [disc]`, dejando sitio al sufijo dentro del largo máximo."""
    sufijo = f" [{disc}]"
    return (base[: _MAX_TITULO - len(sufijo)]).strip(" .") + sufijo


def _titulo(prefijo: str, titulo_crudo: str, anio: str, es_anexo: bool) -> Tuple[str, bool]:
    numero = _num_seccion(prefijo, titulo_crudo)
    if numero is None:
        return _crudo(titulo_crudo), True
    base = f"{prefijo}_SES_{numero:04d}_{anio}"
    if es_anexo:
        base = f"{base}_A01"
    return base, False


def _titulo_concepto(href: str, titulo_fila: str, anio: str) -> Tuple[str, bool]:
    nombre = (href or "").split("/")[-1].split("?")[0]
    m = re.search(r"_(\d{10,})\.pdf$", nombre, re.IGNORECASE)
    if m:
        return f"CTO_SES_{m.group(1)}_{anio}", False
    return _crudo(titulo_fila), True


def _resolver_fecha(fecha_por_prosa, titulo, href, anio_h2):
    """El sitio no expone una fecha por documento: el `<time>` del nodo es la
    fecha de la pestaña-año, no la del archivo. La cadena real es prosa del
    título (sólo resoluciones) -> prefijo AAAAMMDD del archivo -> año del `<h2>`
    (que deja la fecha aproximada al 1 de enero)."""
    if fecha_por_prosa:
        d = parse_fecha_providencia_es(titulo or "")
        if d is not None:
            return d.isoformat()
    pf = _prefijo_fecha_archivo(href)
    if pf:
        return pf
    return f"{anio_h2:04d}-01-01" if anio_h2 is not None else None


def _iter_documentos(soup):
    # recorre todos los <h2> y <a> de span.file en orden de documento
    for nodo in soup.find_all(["h2", "a"]):
        if nodo.name == "h2":
            anio = _anio_de_h2(nodo.get_text(" ", strip=True))
            if anio is not None:
                yield ("h2", anio)
            continue
        # <a>: sólo si su padre inmediato es span.file
        padre = nodo.parent
        if padre is None or padre.name != "span":
            continue
        clases = padre.get("class") or []
        if not any(c == "file" or c.startswith("file--") for c in clases):
            continue
        href = (nodo.get("href") or "").strip()
        if not href:
            continue
        yield ("doc", (nodo.get_text(" ", strip=True), href))


def _filas_concepto(html: str) -> List[Tuple[str, str]]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: List[Tuple[str, str]] = []
    for tr in soup.select("tr"):
        cel_tit = tr.select_one("td.views-field-title")
        cel_dl = tr.select_one("td.views-field-nothing")
        if cel_tit is None or cel_dl is None:
            continue
        a_tit = cel_tit.find("a")
        a_dl = cel_dl.find("a", href=True)
        if a_tit is None or a_dl is None:
            continue
        out.append((a_tit.get_text(" ", strip=True), a_dl["href"].strip()))
    return out


def _clave_unica(claves, source, tipo, fecha, title, unverified, es_anexo, titulo_crudo, url_pdf):
    """Devuelve `(title, unverified, save_path)` con una clave libre para esta
    URL. `claves` registra TODOS los documentos emitidos (verificados o no),
    porque lo que se pisa en almacenamiento es la ruta, no el título; la clave
    es `(tipo, título saneado)`, que es más estricta que la ruta —dos fechas
    distintas ya dan rutas distintas— y de paso evita títulos repetidos."""
    def ruta(t: str) -> str:
        return storage_path(source, fecha, tipo, f"{_safe_title(t)}(extension)")

    def libre(t: str) -> bool:
        return claves.get((tipo, _safe_title(t))) in (None, url_pdf)

    if libre(title):
        return title, unverified, ruta(title)
    # anexo numerado: _A01 -> _A02 -> _A03… hasta encontrar hueco
    if not unverified and es_anexo and title.endswith("_A01"):
        base = title[: -len("_A01")]
        for n in range(2, 100):
            cand = f"{base}_A{n:02d}"
            if libre(cand):
                return cand, unverified, ruta(cand)
    # degradar al título crudo de la página; si ese también está tomado (muchos
    # adjuntos hermanos comparten el mismo texto), discriminar por el nombre
    # del archivo, que sí es único y estable entre corridas.
    crudo = _crudo(titulo_crudo)
    if libre(crudo):
        return crudo, True, ruta(crudo)
    stem = _stem_del_href(url_pdf)
    for n in range(1, 100):
        disc = stem if n == 1 and stem else f"{stem}-{n}" if stem else str(n)
        cand = _con_discriminador(crudo, disc)
        if libre(cand):
            return cand, True, ruta(cand)
    return crudo, True, ruta(crudo)


def _agregar(docs, vistos, claves, source, tipo, url_pdf, titulo_crudo, fecha,
             title, unverified, es_anexo, limit):
    """Construye y agrega un RawDocModel con `save_path` única; devuelve True si
    se alcanzó `limit`."""
    if url_pdf in vistos:
        return False
    vistos.add(url_pdf)
    title, unverified, ruta = _clave_unica(
        claves, source, tipo, fecha, title, unverified, es_anexo, titulo_crudo, url_pdf
    )
    claves[(tipo, _safe_title(title))] = url_pdf
    docs.append(RawDocModel(
        source=source,
        # verify=False: cadena TLS incompleta del host; ver nota del módulo.
        link={"url": url_pdf, "method": "GET", "verify": False},
        title=title,
        tipo=tipo,
        f_public=fecha,
        f_providencia=fecha,
        detalle=(titulo_crudo or "").strip() or None,
        save_path=ruta,
        title_unverified=unverified,
    ))
    return len(docs) >= limit


@register_family("supersolidaria")
class ScrapSupersolidaria(BaseScrapper):
    filters_by_publication_date = True

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        # Cadena TLS incompleta del sitio; ver nota al inicio del módulo.
        session.verify = False
        session.headers.update({"User-Agent": _UA})
        docs: List[RawDocModel] = []
        vistos: set = set()
        claves: Dict[Tuple[str, str], str] = {}
        piso = f"{_ANIO_MIN:04d}-01-01"

        for url, tipo, prefijo, fecha_por_prosa, avisa_doc_a_doc in _SECCIONES_TABLA:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            if on_progress:
                on_progress(f"[{_SOURCE}] Procesando {tipo}...")
            try:
                resp = session.get(url, timeout=90)
                resp.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Error consultando {tipo}: {e}")
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            anio_actual: Optional[int] = None
            n_antes = len(docs)
            for kind, payload in _iter_documentos(soup):
                if stop_event is not None and stop_event.is_set():
                    return docs[:limit]
                if kind == "h2":
                    anio_actual = payload
                    continue
                titulo, href = payload
                url_pdf = urljoin(_BASE, href)
                fecha = _resolver_fecha(fecha_por_prosa, titulo, href, anio_actual)
                if fecha is None:
                    if on_progress and avisa_doc_a_doc:
                        on_progress(f"[{_SOURCE}] Aviso: {tipo} sin fecha «{titulo[:70]}», se omite")
                    continue
                if fecha < piso or fecha < fini or fecha > ffin:
                    continue
                es_anexo = _es_anexo(titulo)
                title, unverified = _titulo(prefijo, titulo, fecha[:4], es_anexo)
                if _agregar(docs, vistos, claves, _SOURCE, tipo, url_pdf, titulo, fecha,
                            title, unverified, es_anexo, limit):
                    return docs[:limit]
            if on_progress and not avisa_doc_a_doc and len(docs) == n_antes:
                on_progress(
                    f"[{_SOURCE}] {tipo}: 0 documentos "
                    f"(sección sin fechas resolubles; hoy todos < {_ANIO_MIN})"
                )

        # --- Conceptos (vista paginada) ---
        if stop_event is not None and stop_event.is_set():
            return docs[:limit]
        if on_progress:
            on_progress(f"[{_SOURCE}] Procesando Concepto...")
        page = 0
        while True:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            try:
                resp = session.get(_URL_CONCEPTOS, params={"page": page}, timeout=90)
                resp.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Error consultando Concepto (page {page}): {e}")
                break
            filas = _filas_concepto(resp.text)
            if not filas:
                break
            for titulo, href in filas:
                if not href:
                    continue
                url_pdf = urljoin(_BASE, href)
                if url_pdf in vistos:
                    continue
                # el PDF trae la fecha en el prefijo AAAAMMDD_ del nombre; los
                # que no lo traen (≈1/3 de la sección) se omiten con aviso.
                fecha = _prefijo_fecha_archivo(href)
                if fecha is None:
                    if on_progress:
                        on_progress(f"[{_SOURCE}] Aviso: Concepto sin fecha «{titulo[:70]}», se omite")
                    continue
                if fecha < piso or fecha < fini or fecha > ffin:
                    continue
                title, unverified = _titulo_concepto(href, titulo, fecha[:4])
                if _agregar(docs, vistos, claves, _SOURCE, "Concepto", url_pdf, titulo, fecha,
                            title, unverified, False, limit):
                    return docs[:limit]
            page += 1
            if page > 200:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Aviso: tope de 200 páginas de Concepto alcanzado")
                break

        return docs[:limit]
