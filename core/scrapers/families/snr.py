import datetime
import re
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests
import urllib3
from bs4 import BeautifulSoup

from core.fecha_es import parse_fecha_providencia_es
from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

# Tanto www.supernotariado.gov.co (enumeración) como
# servicios.supernotariado.gov.co (archivos) entregan una cadena TLS incompleta
# (le falta el intermediario) que `certifi` no puede validar — igual que
# ssf.gov.co, la Corte Constitucional y la CNDJ. Verificado en vivo 2026-09-07:
# el host de archivos también falla con verify=True. Se salta la verificación
# en ambos (session.verify = False en scrap() + link["verify"] = False al descargar).
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_BASE = "https://www.supernotariado.gov.co/transparencia/normatividad"
_SOURCE = "Superintendencia de Notariado y Registro"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
# Cuántos resultados "caben cómodamente" en una página: si el sitio reporta un
# total menor o igual a esto, el bloque no necesita subdividirse.
_UMBRAL = 18
# Tope duro observado en vivo (2026-09-07) en el listado de CIRCULARES: nunca
# devuelve más de 20 fichas, diga lo que diga el conteo «Resultados N».
# (Resoluciones sí entrega todo: r=2024 -> 4034 fichas.) NO es lo mismo que
# _UMBRAL: confundirlos hacía que una página truncada pareciera completa.
_PAGINA_MAX = 20
# Tope de búsquedas por categoría para que una corrida no se dispare.
_MAX_BUSQUEDAS = 4000
_ANIO_MIN = 2015

# (segmento de URL de la categoría, tipo mostrado, letra del código de título)
_CATEGORIAS = [
    ("circulares", "Circular", "C"),
    ("Resoluciones", "Resolución", "R"),
]

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_CODIGO_RE = re.compile(r"\b(CIR|RES)-(\d{4})-(\d{6})-\d\b")
_RESULTADOS_RE = re.compile(r"Resultados\s*([\d.,]+)")
_PUB_RE = re.compile(r"Publicaci[oó]n:\s*(\d{4}-\d{2}-\d{2})")


class _PresupuestoAgotado(Exception):
    """Se agotó el tope de búsquedas de una categoría."""


def _completo(n_vistas: int, total: int) -> bool:
    """¿La respuesta muestra TODAS las fichas que el sitio dice tener?

    `n_vistas` son las fichas RENDERIZADAS, incluidas las que no traen archivo
    adjunto: el conteo «Resultados N» del sitio las cuenta todas (en
    Resoluciones ~1/3 de las fichas no tienen adjunto), así que comparar sólo
    las descargables daría siempre "incompleto".

    Tampoco sirve mirar si llegaron "muchas" fichas: el listado de circulares
    corta en _PAGINA_MAX, y una página llena es justo la señal de que falta
    información, no de que esté completa.
    """
    if total >= 0:
        return n_vistas >= total
    # Sin conteo legible sólo se puede confiar en una página que no viene topada.
    return n_vistas < _PAGINA_MAX


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _parse_codigo(texto: str) -> Optional[Tuple[str, int, int]]:
    m = _CODIGO_RE.search(texto or "")
    if not m:
        return None
    letra = "C" if m.group(1) == "CIR" else "R"
    return letra, int(m.group(3)), int(m.group(2))


def _titulo(codigo: Optional[Tuple[str, int, int]], texto_crudo: str) -> Tuple[str, bool]:
    if codigo is None:
        return ((texto_crudo or "").strip() or "documento")[:120], True
    letra, numero, anio = codigo
    return f"{letra}_SNR_{numero:04d}_{anio}", False


def _resultados_total(html: str) -> int:
    m = _RESULTADOS_RE.search(html or "")
    if not m:
        return -1
    return int(m.group(1).replace(".", "").replace(",", ""))


def _tarjetas(html: str) -> Tuple[List[dict], int]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: List[dict] = []
    sin_pdf = 0
    for li in soup.select("ul.docs_download > li"):
        cont = li.select_one("div.contenido_download")
        if cont is None:
            continue
        a = cont.find("a", href=True)
        if a is None or not a["href"].strip().lower().startswith("http"):
            # Sin adjunto real (o un href que no es una descarga: javascript:, #, …)
            sin_pdf += 1
            continue
        mpub = _PUB_RE.search(cont.get_text(" ", strip=True))
        out.append({
            "titulo_txt": a.get_text(" ", strip=True),
            "publicacion": mpub.group(1) if mpub else None,
            "pdf_url": a["href"].strip(),
        })
    return out, sin_pdf


def _tarjeta_a_doc(tarjeta, tipo, fini, ffin, on_progress) -> Optional[RawDocModel]:
    titulo_txt = tarjeta.get("titulo_txt") or ""
    # Fecha de la norma (la que va en la prosa del título) y fecha en que la
    # SNR la publicó (el campo «Publicación:» de la tarjeta). Pueden diferir
    # varios días; la fuente filtra por fecha de PUBLICACIÓN.
    fecha_prov = parse_fecha_providencia_es(titulo_txt)
    fecha_pub = None
    if tarjeta.get("publicacion"):
        try:
            fecha_pub = datetime.date.fromisoformat(tarjeta["publicacion"])
        except ValueError:
            fecha_pub = None

    f_public_date = fecha_pub or fecha_prov
    f_providencia_date = fecha_prov or fecha_pub
    if f_public_date is None:
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: tarjeta sin fecha parseable «{titulo_txt[:70]}», se omite")
        return None
    if f_public_date.year < _ANIO_MIN:
        return None
    iso = f_public_date.isoformat()
    if iso < fini or iso > ffin:
        return None

    codigo = _parse_codigo(titulo_txt)
    title, unverified = _titulo(codigo, titulo_txt)
    safe = _safe_title(title)
    return RawDocModel(
        source=_SOURCE,
        link={"url": urljoin(_BASE, tarjeta["pdf_url"]), "method": "GET", "verify": False},
        title=title,
        tipo=tipo,
        f_public=iso,
        f_providencia=f_providencia_date.isoformat(),
        detalle=titulo_txt or None,
        save_path=storage_path(_SOURCE, iso, tipo, f"{safe}(extension)"),
        title_unverified=unverified,
    )


def _buscar(session: requests.Session, categoria: str, termino: str) -> Tuple[int, str]:
    resp = session.post(f"{_BASE}/{categoria}/", data={"r": termino}, timeout=200)
    resp.raise_for_status()
    return _resultados_total(resp.text), resp.text


def _enumerar_categoria(session, categoria, letra, fini, ffin, stop_event, on_progress) -> List[dict]:
    tipo_code = "CIR" if letra == "C" else "RES"
    anio_ini = max(_ANIO_MIN, int(fini[:4]))
    anio_fin = int(ffin[:4])
    por_url: dict = {}
    contador = [0]   # búsquedas gastadas en esta categoría
    omitidas = [0]   # tarjetas sin archivo adjunto

    def _add(cards):
        for c in cards:
            por_url.setdefault(c["pdf_url"], c)

    def _buscar_presupuestado(termino: str) -> Tuple[int, List[dict], int]:
        if contador[0] >= _MAX_BUSQUEDAS:
            raise _PresupuestoAgotado
        contador[0] += 1
        total, html = _buscar(session, categoria, termino)
        cards, sin_pdf = _tarjetas(html)
        omitidas[0] += sin_pdf
        return total, cards, len(cards) + sin_pdf

    def _bloque(pref: str, anio: int):
        if stop_event is not None and stop_event.is_set():
            return
        termino = f"{tipo_code}-{anio}-{pref}"
        try:
            t, cs, vistas = _buscar_presupuestado(termino)
        except _PresupuestoAgotado:
            raise
        except Exception as e:
            if on_progress:
                on_progress(f"[{_SOURCE}] Error consultando {categoria} {termino}: {e}")
            return
        if t == 0:
            return
        # Se deja de dividir cuando el bloque ya está completo, o cuando el
        # total reportado es lo bastante chico como para caber en una página.
        if _completo(vistas, t) or (0 <= t <= _UMBRAL):
            _add(cs)
            return
        if len(pref) >= 5:
            if on_progress:
                on_progress(
                    f"[{_SOURCE}] Error: bloque {termino} con {t} resultados "
                    "no se pudo dividir más, se truncó"
                )
            _add(cs)
            return
        for d in "0123456789":
            _bloque(pref + d, anio)

    try:
        for anio in range(anio_ini, anio_fin + 1):
            if stop_event is not None and stop_event.is_set():
                break
            try:
                total, cards, vistas = _buscar_presupuestado(str(anio))
            except _PresupuestoAgotado:
                raise
            except Exception as e:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Error consultando {categoria} {anio}: {e}")
                continue
            if _completo(vistas, total):
                _add(cards)
                continue
            # La respuesta vino topada en _PAGINA_MAX. Se conservan igual las
            # fichas que el sitio SÍ mostró de este año: para las circulares
            # anteriores a ~2025 —que no traen el código «CIR-AAAA-NNNNNN»— la
            # recursión por prefijo no encuentra nada, así que estas ~20 fichas
            # más recientes son la única cobertura posible del año. Para los años
            # con código, la recursión vuelve a traerlas y _add las deduplica por
            # URL, sin doble conteo.
            _add(cards)
            if on_progress:
                on_progress(
                    f"[{_SOURCE}] Aviso: {categoria} {anio} devolvió {total} "
                    f"resultados pero el sitio sólo muestra {len(cards)}; se "
                    "conservan esas y se intenta completar por código de norma"
                )
            # Los consecutivos vienen con relleno a 6 dígitos y ninguno llega a
            # 100.000, así que TODOS caen bajo el prefijo "0": se arranca ahí en
            # vez de gastar nueve búsquedas garantizadas vacías ("1".."9").
            _bloque("0", anio)
    except _PresupuestoAgotado:
        if on_progress:
            on_progress(
                f"[{_SOURCE}] Error: presupuesto de {_MAX_BUSQUEDAS} búsquedas "
                f"agotado en {categoria}, resultados incompletos"
            )

    if omitidas[0] and on_progress:
        on_progress(
            f"[{_SOURCE}] Aviso: {omitidas[0]} tarjetas sin archivo adjunto omitidas en {categoria}"
        )
    return list(por_url.values())


@register_family("snr")
class ScrapSNR(BaseScrapper):
    filters_by_publication_date = True

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        # Cadena TLS incompleta del sitio; ver nota al inicio del módulo.
        session.verify = False
        session.headers.update({"User-Agent": _UA})
        docs: List[RawDocModel] = []

        for categoria, tipo, letra in _CATEGORIAS:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            if on_progress:
                on_progress(f"[{_SOURCE}] Procesando {tipo}...")
            tarjetas = _enumerar_categoria(session, categoria, letra, fini, ffin, stop_event, on_progress)
            for tarjeta in tarjetas:
                doc = _tarjeta_a_doc(tarjeta, tipo, fini, ffin, on_progress)
                if doc is not None:
                    docs.append(doc)
                    if len(docs) >= limit:
                        return docs[:limit]

        return docs[:limit]
