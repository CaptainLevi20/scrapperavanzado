import collections
import datetime
import re
import time
from typing import Iterator, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup

from core.fecha_es import parse_fecha_providencia_es
from core.models import RawDocModel
from core.naming import codigo_ley_decreto
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

# Gestor Normativo de la Función Pública (PHP propio). El formulario de la
# consulta avanzada llama por JavaScript a funajax.php, que devuelve TODO un
# año (sin paginar de verdad) para la entidad y el tipo pedidos. Cada fila
# enlaza al detalle norma.php?i=<id>, que trae las fechas, y el PDF se genera
# en norma_pdf.php?i=<id>. Ver
# docs/superpowers/specs/2026-11-23-fuente-funcion_publica-design.md.
#
# Certificado TLS roto: el servidor envía el intermedio de Sectigo pero su
# certificado lo firma Let's Encrypt YR1 (raíz ISRG Root YR, que certifi aún
# no trae). Con la cadena correcta es válido, así que es un error de
# configuración del sitio: se usa verify=False SOLO para este host (sesión del
# scraper y link["verify"] de cada documento), como ssf, snr y supersolidaria.
_BASE = "https://www.funcionpublica.gov.co/eva/gestornormativo/"
_LISTADO_URL = urljoin(_BASE, "gestion/funphp/funajax.php")
_DETALLE_URL = urljoin(_BASE, "norma.php")
_PDF_URL = urljoin(_BASE, "norma_pdf.php")
_SOURCE = "Departamento Administrativo de la Función Pública"
_SIGLA = "DAFP"
_ENTIDAD = "88"  # "Departamento Administrativo de la Función Pública" en el selector
_ANIO_MINIMO = 2015
_PAUSA_DETALLE = 0.3  # segundos entre detalles, para no cargar el servidor
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "es-CO,es;q=0.9"}

# tipodoc del Gestor -> (nombre para los avisos, tipo, prefijo del título).
# Prefijo None = decreto: usa el código común de leyes y decretos
# (core/naming.py), sin sigla, para reconocer el mismo decreto en otras
# fuentes. Ley, Sentencia, Comunicado y Documento de Relatoría quedan fuera.
_TIPOS = (
    ("7", "Concepto", "Concepto", "CTO"),
    ("785", "Concepto Marco", "Concepto", "CTO"),
    ("1305", "Conceptos Guías", "Concepto", "CTO"),
    ("11", "Decreto", "Decreto", None),
    ("987", "Decretos Salariales", "Decreto", None),
    ("29", "Resolución", "Resolución", "R"),
    ("6", "Circular", "Circular", "C"),
    ("825", "Circular Externa", "Circular", "CE"),
    ("184", "Circular Conjunta", "Circular", "CJ"),
    ("845", "Circular Unificada", "Circular", "CU"),
)

# "<Tipo> <número> de <año>"; espacios dobles o tabulador antes de "de" son
# normales en el sitio. El número puede faltar ("Concepto  de 2021").
_H5_RE = re.compile(r"^\s*(?P<tipo>.+?)\s+(?:(?P<num>\S+)\s+)?de\s+(?P<anio>\d{4})\s*$", re.IGNORECASE)
_PREFIJOS_SOLO_DIGITOS = {"CTO", "R"}
_NUMERO_LIMPIO_RE = re.compile(r"[^A-Za-z0-9-]+")
_FECHA_RE = {
    "expedicion": re.compile(r"Fecha de Expedici[oó]n:\s*(.*)", re.IGNORECASE),
    "vigencia": re.compile(r"Fecha de Entrada en Vigencia:\s*(.*)", re.IGNORECASE),
}


def _norm_texto(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def _leer_h5(h5: str) -> Tuple[Optional[str], Optional[int]]:
    """(número tal cual, año) del encabezado de la fila; (None, None) si no
    tiene la forma "<Tipo> <número> de <año>"."""
    m = _H5_RE.match((h5 or "").replace("\xa0", " "))
    if not m:
        return None, None
    return m.group("num"), int(m.group("anio"))


def _titulo(prefijo: Optional[str], numero: Optional[str], anio: int, norma_id: str) -> Tuple[str, bool]:
    """Título canónico y si quedó sin verificar. El número se copia tal cual
    lo escribe la entidad (sin quitar ni poner ceros), salvo los decretos,
    que usan el código común D####YYY. Un número con caracteres raros
    ("451981*", "¿248691") se limpia; sin número queda SN-<id>. Conceptos,
    resoluciones y decretos llevan sólo dígitos ("C-197" es un error de
    carga); las circulares sí traen guiones o letras ("100-011").
    """
    crudo = (numero or "").strip()
    limpio = _NUMERO_LIMPIO_RE.sub("", crudo)
    sin_verificar = limpio != crudo or not limpio
    if prefijo in _PREFIJOS_SOLO_DIGITOS and limpio and not limpio.isdigit():
        sin_verificar = True
    if prefijo is None:
        if limpio.isdigit():
            return codigo_ley_decreto("D", limpio, str(anio)), sin_verificar
        prefijo, sin_verificar = "D", True
    return f"{prefijo}_{_SIGLA}_{limpio or f'SN-{norma_id}'}_{anio}", sin_verificar


def _filas(html: str) -> List[dict]:
    """Filas del listado: id de la norma, encabezado y epígrafe. El párrafo
    "Número de documentos encontrados" usa la misma clase que el epígrafe
    pero está fuera de los enlaces, así que no se cuenta."""
    soup = BeautifulSoup(html, "html.parser")
    filas = []
    for a in soup.select("a.list-group-item[href]"):
        ids = parse_qs(urlparse(a["href"]).query).get("i")
        if not ids or not ids[0].strip().isdigit():
            continue
        h5 = a.select_one("h5")
        p = a.select_one("p.list-group-item-text")
        filas.append({
            "id": ids[0].strip(),
            "h5": _norm_texto(h5.get_text(" ", strip=True)) if h5 else "",
            "epigrafe": _norm_texto(p.get_text(" ", strip=True)) if p else "",
        })
    return filas


def _leer_detalle(html: str) -> dict:
    """Fechas de expedición y de entrada en vigencia (None si no se leen) y
    si el detalle trae el enlace al PDF."""
    soup = BeautifulSoup(html, "html.parser")
    datos = {"expedicion": None, "vigencia": None}
    for p in soup.find_all("p"):
        texto = _norm_texto(p.get_text(" ", strip=True))
        for campo, patron in _FECHA_RE.items():
            m = patron.match(texto)
            if m and datos[campo] is None:
                datos[campo] = parse_fecha_providencia_es(m.group(1))
    datos["tiene_pdf"] = soup.select_one('a[href*="norma_pdf.php"]') is not None
    return datos


def _elegir_fecha(expedicion, vigencia, anio: int, hoy: datetime.date) -> Tuple[str, str]:
    """Fecha del documento y de dónde salió ("expedicion", "vigencia" o
    "anio"). El año del título es el dato más fiable (lo confirman el
    radicado y el nombre del PDF); la fecha del sitio tiene errores (años de
    otro título, fechas futuras, el 31-12-1969 de una fecha vacía)."""
    for origen, fecha in (("expedicion", expedicion), ("vigencia", vigencia)):
        if fecha is not None and fecha.year == anio and fecha <= hoy:
            return fecha.isoformat(), origen
    return f"{anio}-01-01", "anio"


def _anios(fini: str, ffin: str) -> range:
    return range(max(int(fini[:4]), _ANIO_MINIMO), int(ffin[:4]) + 1)


def _listado(session, anio: int, tipodoc: str, nombre: str, avisar) -> Iterator[dict]:
    try:
        resp = session.get(
            _LISTADO_URL,
            params={
                "t": "ejecuta_busqueda_avanzada2",
                "entidad1": _ENTIDAD,
                "tipdoc": tipodoc,
                "ano": str(anio),
                "pagina": "1",
            },
            timeout=120,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        avisar(f"Error consultando {nombre} de {anio}: {e}")
        return
    yield from _filas(resp.text)


@register_family("funcion_publica")
class ScrapFuncionPublica(BaseScrapper):
    # El PDF se genera en cada petición (cambia unos bytes y Last-Modified es
    # siempre "ahora"): comparar tamaños daría republicaciones falsas a diario.
    checks_for_republication = False
    # La URL norma_pdf.php?i=<id> es estable y única por norma. La fecha no
    # entra en el doc_id porque la familia la corrige: si el sitio arregla
    # una fecha, el mismo concepto no debe bajarse otra vez.
    doc_id_uses_publication_date = False
    # Las normas se cargan con meses de retraso y en tandas: la diaria pide el
    # año en curso y el anterior completos (lo ya guardado no se vuelve a bajar).
    scheduled_min_lookback_days = 400

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        session = requests.Session()
        session.headers.update(_HEADERS)
        session.verify = False  # ver el comentario de _BASE
        docs: List[RawDocModel] = []
        vistos: set = set()
        hoy = datetime.date.today()

        def avisar(texto):
            if on_progress:
                on_progress(f"[{_SOURCE}] {texto}")

        def cancelado():
            return stop_event is not None and stop_event.is_set()

        for anio in _anios(fini, ffin):
            titulos_del_anio = collections.Counter()
            for tipodoc, nombre, tipo, prefijo in _TIPOS:
                if cancelado():
                    return docs[:limit]
                avisar(f"Procesando {nombre} de {anio}...")
                for fila in _listado(session, anio, tipodoc, nombre, avisar):
                    if cancelado():
                        return docs[:limit]
                    if fila["id"] in vistos:
                        continue
                    vistos.add(fila["id"])

                    numero, anio_titulo = _leer_h5(fila["h5"])
                    sin_verificar = False
                    if anio_titulo is None:
                        anio_titulo, sin_verificar = anio, True
                        avisar(f"Aviso: encabezado inesperado '{fila['h5']}' (norma {fila['id']}); se toma el año {anio}")
                    if anio_titulo != anio:
                        # El listado por año trae lo de ese año; otra cosa se
                        # pedirá (o no) en su propio año.
                        continue

                    title, raro = _titulo(prefijo, numero, anio_titulo, fila["id"])
                    if raro and not sin_verificar:
                        avisar(f"Aviso: número inesperado en '{fila['h5']}' (norma {fila['id']}); título {title} sin verificar")
                    sin_verificar = sin_verificar or raro

                    if _PAUSA_DETALLE:
                        time.sleep(_PAUSA_DETALLE)
                    try:
                        resp = session.get(_DETALLE_URL, params={"i": fila["id"]}, timeout=60)
                        resp.raise_for_status()
                    except requests.RequestException as e:
                        avisar(f"Error consultando el detalle de {title} (norma {fila['id']}): {e}")
                        continue
                    detalle = _leer_detalle(resp.text)
                    if not detalle["tiene_pdf"]:
                        avisar(f"Aviso: {title} (norma {fila['id']}) no trae PDF para descargar, se omite")
                        continue

                    fecha, origen = _elegir_fecha(detalle["expedicion"], detalle["vigencia"], anio_titulo, hoy)
                    if origen != "expedicion":
                        avisar(
                            f"Aviso: {title} trae expedición {detalle['expedicion'] or 'ilegible'} y vigencia "
                            f"{detalle['vigencia'] or 'ilegible'}; se usa {fecha}"
                        )
                    if not (fini <= fecha <= ffin):
                        continue

                    titulos_del_anio[title] += 1
                    if titulos_del_anio[title] == 2:
                        avisar(f"Aviso: {title} aparece más de una vez en el Gestor; se guardan todas, revisar a mano")

                    docs.append(RawDocModel(
                        source=_SOURCE,
                        # completar_fin_pdf: el servidor corta los dos últimos
                        # bytes de cada PDF ("%%E" en vez de "%%EOF"); el
                        # descargador completa esa marca (ver core/downloader.py).
                        link={
                            "url": f"{_PDF_URL}?i={fila['id']}",
                            "method": "GET",
                            "verify": False,
                            "completar_fin_pdf": True,
                        },
                        title=title,
                        tipo=tipo,
                        f_public=fecha,
                        f_providencia=fecha,
                        detalle=fila["epigrafe"] or None,
                        save_path=storage_path(_SOURCE, fecha, tipo, f"{title}(extension)"),
                        title_unverified=sin_verificar,
                    ))
                    if len(docs) >= limit:
                        return docs[:limit]
        return docs[:limit]
