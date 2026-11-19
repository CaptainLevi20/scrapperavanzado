import collections
import datetime
import hashlib
import re
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
# El año más grande (2016) tiene 166 conceptos: 2 páginas. 5 es tope de sobra.
_PAGINAS_POR_ANIO_TOPE = 5
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "es-CO,es;q=0.9"}

# "10", "3C", "132 A", "142-1": la parte numérica se rellena a 4 y el sufijo
# (letra o "-n") se conserva en mayúscula, sin espacios.
_NUMERO_RE = re.compile(r"^(\d+)\s*([A-Za-z]|-\d+)?$")
_NO_TITULO_RE = re.compile(r"[^A-Za-z0-9-]+")


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


def _anios(fini: str, ffin: str) -> range:
    return range(max(int(fini[:4]), _ANIO_MINIMO), int(ffin[:4]) + 1)


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
        if len(filas) < _FILAS_POR_PAGINA:
            return


@register_family("icbf")
class ScrapIcbf(BaseScrapper):
    # El sitio sólo da el año de cada concepto: se guarda con fecha
    # <año>-01-01 y se filtra por año. La corrida diaria pide el año en curso
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

                fecha = f"{anio_fila}-01-01"
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
