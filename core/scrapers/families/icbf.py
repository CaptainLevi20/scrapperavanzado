import collections
import datetime
import hashlib
import io
import re
import unicodedata
import zipfile
from typing import Iterator, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

# Normograma del ICBF (Drupal). El listado de conceptos es una vista con
# filtro por año; cada fila enlaza a un detalle que trae el .docx.
_BASE = "https://www.icbf.gov.co/"
_LISTADO_URL = urljoin(_BASE, "concepto")
_SOURCE = "Instituto Colombiano de Bienestar Familiar"
_SIGLA = "ICBF"
_PREFIJO = "CTO"
_TIPO = "Concepto"
_ANIO_MINIMO = 2015
_FILAS_POR_PAGINA = 100
# El año más grande (2016) tiene 166 conceptos: 2 páginas de 100. El tope es
# sólo un freno contra un paginador que no termine; deja margen por si el
# sitio achica las páginas, y si se alcanza la corrida lo avisa.
_PAGINAS_POR_ANIO_TOPE = 20
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "es-CO,es;q=0.9"}

# "10", "3C", "132 A", "142-1": la parte numérica se rellena a 4 y el sufijo
# (letra o "-n") se conserva en mayúscula, sin espacios.
_NUMERO_RE = re.compile(r"^(\d+)\s*([A-Za-z]|-\d+)?$")
_NO_TITULO_RE = re.compile(r"[^A-Za-z0-9-]+")

# Fecha del concepto: el sitio sólo da el año, pero cada .docx empieza con
# "CONCEPTO [No.] <n> DE <año>" y, entre paréntesis, el día y el mes en que se
# firmó: "(30 de julio)", "(mayo 13)", "(28 de Noviembre)". Verificado sobre
# los 716 conceptos del sitio (2026-11-19): 711 la traen así; 5 no la traen y
# 3 abren el documento de otro concepto (número o año del encabezado distinto
# del de la fila), y en esos 8 se deja el 1 de enero.
_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
_MES = "|".join(_MESES)
_ENCABEZADO_RE = re.compile(
    r"CONCEPTO\s*(?:N[oO°º]\.?\s*)?(\d+)\s*(?:[A-Za-z]\b|-\s*\d+)?\s*DEL?\s*(\d{4})", re.IGNORECASE
)
_FECHA_ENCABEZADO_RE = re.compile(
    rf"^\s*\(\s*(?:(\d{{1,2}})\s*(?:de\s*)?({_MES})|({_MES})\s*(\d{{1,2}}))\b", re.IGNORECASE
)
# Topes al abrir el .docx (viene de un sitio ajeno): el archivo y el XML del
# texto. Los conceptos reales pesan decenas de KB.
_DOCX_MAX_BYTES = 20 * 1024 * 1024
_XML_MAX_BYTES = 50 * 1024 * 1024


def _norm_texto(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def _titulo(numero: str, anio: int) -> Tuple[str, bool]:
    """Título canónico y si quedó sin verificar (número fuera del patrón)."""
    numero = _norm_texto(numero)
    m = _NUMERO_RE.match(numero)
    if m:
        sufijo = (m.group(2) or "").upper()
        return f"{_PREFIJO}_{_SIGLA}_{int(m.group(1)):04d}{sufijo}_{anio}", False
    saneado = _NO_TITULO_RE.sub("", numero.upper()) or "SN"
    return f"{_PREFIJO}_{_SIGLA}_{saneado}_{anio}", True


def _celda(tr, campo: str) -> str:
    td = tr.find("td", class_=f"views-field-{campo}")
    return _norm_texto(td.get_text(" ", strip=True)) if td else ""


def _filas(html: str) -> List[dict]:
    """Filas del listado: categoría, número, año, epígrafe y href del detalle."""
    soup = BeautifulSoup(html, "html.parser")
    filas = []
    for tr in soup.select("tbody tr"):
        enlace = tr.select_one("td.views-field-view-node a[href]")
        if enlace is None:
            continue
        filas.append({
            "categoria": _celda(tr, "field-tipo-norma"),
            "numero": _celda(tr, "field-numero"),
            "anio": _celda(tr, "field-anio"),
            "epigrafe": _celda(tr, "field-epigrafe"),
            "href": urljoin(_BASE, enlace["href"].strip()),
        })
    return filas


def _url_documento(html: str, url_detalle: str) -> Optional[str]:
    """URL absoluta del archivo del concepto (botón "Descargar documento")."""
    soup = BeautifulSoup(html, "html.parser")
    a = soup.select_one("a.btn-documento[href]")
    if a is None or not a["href"].strip():
        return None
    return urljoin(url_detalle, a["href"].strip())


def _texto_inicial_docx(contenido: bytes, caracteres: int = 400) -> Optional[str]:
    """Primeros caracteres del texto de un .docx, o None si no se puede leer.
    Word parte las palabras en trozos (`<w:t>CONCEPTO 10 D</w:t><w:t>E 2026`):
    se unen sin espacio dentro del párrafo y con espacio entre párrafos."""
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as z:
            info = z.getinfo("word/document.xml")
            if info.file_size > _XML_MAX_BYTES:
                return None
            xml = z.read(info).decode("utf-8", "replace")
    except (zipfile.BadZipFile, KeyError, OSError, ValueError):
        return None
    xml = re.sub(r"</w:p>", " ", xml)
    texto = re.sub(r"<[^>]+>", "", xml).replace("﻿", "")
    texto = unicodedata.normalize("NFC", texto)
    return re.sub(r"\s+", " ", texto).strip()[:caracteres]


def _fecha_del_encabezado(texto: Optional[str], numero: str, anio: int) -> Tuple[Optional[datetime.date], str]:
    """(fecha, motivo): la fecha de firma del concepto leída del encabezado del
    .docx, sólo si el encabezado es el de ESTE concepto (mismo número y año que
    la fila). Si no, (None, motivo legible para el aviso)."""
    if not texto:
        return None, "no se pudo leer el documento"
    m = _ENCABEZADO_RE.search(texto[:200])
    if m is None:
        return None, "el documento no empieza con 'CONCEPTO <número> DE <año>'"
    num_fila = re.match(r"\d+", _norm_texto(numero))
    if num_fila is None or int(m.group(1)) != int(num_fila.group(0)) or int(m.group(2)) != anio:
        return None, f"el documento es el concepto {m.group(1)} de {m.group(2)}, no el {numero} de {anio}"
    f = _FECHA_ENCABEZADO_RE.match(texto[m.end():m.end() + 40])
    if f is None:
        return None, "el encabezado no trae día y mes"
    dia = int(f.group(1) or f.group(4))
    mes = _MESES[(f.group(2) or f.group(3)).lower()]
    try:
        return datetime.date(anio, mes, dia), ""
    except ValueError:
        return None, f"fecha imposible en el encabezado ({dia}/{mes})"


def _descargar_docx(session, url: str) -> bytes:
    """El .docx completo, con tope de tamaño."""
    with session.get(url, timeout=60, stream=True) as resp:
        resp.raise_for_status()
        partes, total = [], 0
        for trozo in resp.iter_content(64 * 1024):
            total += len(trozo)
            if total > _DOCX_MAX_BYTES:
                raise requests.RequestException(f"archivo de más de {_DOCX_MAX_BYTES // (1024 * 1024)} MB")
            partes.append(trozo)
    return b"".join(partes)


def _anios(fini: str, ffin: str) -> range:
    return range(max(int(fini[:4]), _ANIO_MINIMO), int(ffin[:4]) + 1)


def _hay_pagina_siguiente(html: str) -> bool:
    """El paginador de Drupal trae el enlace rel="next" sólo si hay más."""
    return BeautifulSoup(html, "html.parser").select_one('a[rel="next"]') is not None


def _filas_del_anio(session, anio: int, stop_event, avisar) -> Iterator[dict]:
    # Una página que falla corta el año ahí, pero conserva las filas de las
    # páginas que ya cargaron: perder 100 conceptos por un error en la
    # segunda página sería peor que bajar el año incompleto y avisarlo.
    for pagina in range(_PAGINAS_POR_ANIO_TOPE):
        if stop_event is not None and stop_event.is_set():
            return
        try:
            resp = session.get(
                _LISTADO_URL, params={"field_anio_value": str(anio), "page": str(pagina)}, timeout=60
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            if pagina == 0:
                avisar(f"Error consultando los conceptos de {anio}: {e}")
            else:
                avisar(
                    f"Error consultando la página {pagina + 1} de los conceptos de {anio}: {e}; "
                    "el año queda incompleto"
                )
            return
        filas = _filas(resp.text)
        yield from filas
        # Se sigue el paginador del sitio, no un tamaño de página supuesto: si
        # el ICBF cambia cuántos muestra por página, igual se recorren todas.
        # Una página llena de 100 sin paginador también sigue (por si el
        # paginador cambia de forma); una página vacía siempre corta.
        if not filas:
            return
        if not _hay_pagina_siguiente(resp.text) and len(filas) < _FILAS_POR_PAGINA:
            return
    avisar(
        f"Aviso: los conceptos de {anio} llegaron al tope de {_PAGINAS_POR_ANIO_TOPE} páginas; "
        "puede haber más sin revisar"
    )


@register_family("icbf")
class ScrapIcbf(BaseScrapper):
    # El listado sólo da el año de cada concepto; la fecha de firma se lee del
    # encabezado del .docx (ver _fecha_del_encabezado) y, si no se puede, queda
    # el <año>-01-01. Se filtra por el AÑO de la fila, no por la fecha: un
    # concepto firmado en julio y subido en agosto tiene que entrar igual.
    #
    # Identidad = sólo la URL del archivo: con la fecha dentro del doc_id, una
    # fecha corregida (o el paso del 1 de enero a la fecha real, ver
    # core/backfill_icbf_fechas.py) haría ver el mismo concepto como nuevo.
    doc_id_uses_publication_date = False

    # La corrida diaria pide el año en curso
    # completo (una página). Los años salen de fini/ffin, así que sin esto la
    # ventana diaria (unos pocos días) deja de tocar diciembre apenas pasan
    # los primeros días de enero, y un concepto del año anterior que el ICBF
    # suba a mediados de enero nunca se pediría. Con 45 días, la corrida
    # diaria revisa también el año anterior hasta mediados de febrero.
    scheduled_min_lookback_days = 45

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update(_HEADERS)
        docs: List[RawDocModel] = []
        vistos: set = set()
        anio_ini, anio_fin = int(fini[:4]), int(ffin[:4])
        anios = _anios(fini, ffin)
        filas_totales = 0

        def avisar(texto):
            if on_progress:
                on_progress(f"[{_SOURCE}] {texto}")

        for anio in anios:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            avisar(f"Procesando conceptos de {anio}...")
            filas = list(_filas_del_anio(session, anio, stop_event, avisar))
            filas_totales += len(filas)

            # Dos filas distintas con el mismo número y año darían el mismo
            # nombre de archivo y la segunda pisaría a la primera. Se cuentan
            # sobre el listado completo del año (cada corrida lo trae entero),
            # así el sufijo no depende del orden de las filas ni de cuál se
            # guardó primero.
            repetidos = collections.Counter(
                _titulo(f["numero"], int(f["anio"]))[0]
                for f in filas
                if f["categoria"].upper() == "CONCEPTO" and f["anio"].isdigit()
            )

            for fila in filas:
                if stop_event is not None and stop_event.is_set():
                    return docs[:limit]
                if fila["categoria"].upper() != "CONCEPTO":
                    continue
                try:
                    anio_fila = int(fila["anio"])
                except ValueError:
                    avisar(f"Aviso: concepto {fila['numero']} sin año legible, se omite")
                    continue
                if anio_fila < _ANIO_MINIMO or not (anio_ini <= anio_fila <= anio_fin):
                    continue

                title, sin_verificar = _titulo(fila["numero"], anio_fila)
                if sin_verificar:
                    avisar(f"Aviso: número de concepto inesperado '{fila['numero']}' de {anio_fila}; título {title} sin verificar")

                try:
                    resp = session.get(fila["href"], timeout=60)
                    resp.raise_for_status()
                except requests.RequestException as e:
                    avisar(f"Error consultando el detalle de {title}: {e}")
                    continue
                url = _url_documento(resp.text, fila["href"])
                if url is None:
                    avisar(f"Aviso: {title} no trae archivo para descargar, se omite")
                    continue
                if url in vistos:
                    avisar(f"Aviso: {title} repite un archivo ya visto, se omite")
                    continue
                vistos.add(url)

                nombre_archivo = title
                if repetidos[title] > 1:
                    nombre_archivo = f"{title}_h{hashlib.sha1(url.encode()).hexdigest()[:7]}"
                    sin_verificar = True
                    avisar(
                        f"Aviso: {title} aparece {repetidos[title]} veces en el listado; "
                        f"se guarda como {nombre_archivo} para no pisar al otro, revisar a mano"
                    )

                # La fecha sale del encabezado del propio .docx. Si no se puede
                # bajar, se deja para la próxima corrida (guardarlo con el 1 de
                # enero lo dejaría así para siempre: ya guardado, no se revisa).
                try:
                    contenido = _descargar_docx(session, url)
                except requests.RequestException as e:
                    avisar(f"Error descargando {title} para leer su fecha: {e}; se intentará en la próxima corrida")
                    vistos.discard(url)
                    continue
                fecha_concepto, motivo = _fecha_del_encabezado(_texto_inicial_docx(contenido), fila["numero"], anio_fila)
                if fecha_concepto is None:
                    fecha = f"{anio_fila}-01-01"
                    avisar(f"Aviso: {title} queda con fecha {fecha}: {motivo}")
                else:
                    fecha = fecha_concepto.isoformat()

                docs.append(RawDocModel(
                    source=_SOURCE,
                    link={"url": url, "method": "GET"},
                    title=title,
                    tipo=_TIPO,
                    f_public=fecha,
                    f_providencia=fecha,
                    detalle=fila["epigrafe"] or None,
                    save_path=storage_path(_SOURCE, fecha, _TIPO, f"{nombre_archivo}(extension)"),
                    title_unverified=sin_verificar,
                ))
                if len(docs) >= limit:
                    return docs[:limit]

        # En enero es normal que el año nuevo aún no tenga conceptos; si
        # tampoco los trae un año anterior, la vista del sitio cambió.
        if filas_totales == 0 and any(a < datetime.date.today().year for a in anios):
            avisar("Error: el listado no trajo ningún concepto")

        return docs[:limit]
