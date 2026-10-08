import re
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.naming import codigo_ley_decreto, con_sufijos
from core.utils import storage_path

_BASE_URL = "https://www.mincit.gov.co"

# slug de categoría -> (tipo mostrado, letra del código de título)
_CATEGORIAS = {
    "resoluciones": ("Resolución", "R"),
    "decretos": ("Decreto", "D"),
    "circulares": ("Circular", "C"),
    "leyes": ("Ley", "L"),
}

# Páginas sueltas (sin archivo por año) que se recorren completas en cada
# corrida: slug bajo /normatividad -> categoría de _CATEGORIAS a la que pliegan.
# Las circulares conjuntas van con la letra "C" de las circulares normales,
# igual que en procuraduria.py y sic.py.
_PAGINAS_SUELTAS = {
    "circulares/circulares-conjuntas": "circulares",
}

_FECHA_PATTERN = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
# Número de la norma al inicio del texto del archivo. Tolera las variantes que
# usa el sitio entre el tipo y el número, vistas en sus ~3.500 filas:
# calificadores ("Circular Externa Conjunta", "Decreto - Ley"), siglas de
# dependencia ("Circular DVT 003"), "No."/"N°"/"Número", el typo "Circula" y
# el tipo pegado al número ("Resolución194", "Decreto-1503-2002"). El número
# puede llevar letra ("036A") o ser compuesto ("100-003"); el "-2002" de
# "Decreto-1503-2002" no cuenta como parte compuesta (máximo 3 dígitos tras el
# guion, seguido de fin de palabra). "Circular ley 1816" NO matchea a
# propósito: ahí 1816 es el número de la ley citada, no de la circular.
_NUMERO_PATTERN = re.compile(
    r"^(?:decreto(?:[\s\-]+ley\b)?|resoluci[oó]n|circular?|ley)"
    r"(?:[\s,.\-]+(?:externa|interna|conjunta|dvt|vde)\b)*"
    r"[\s\-]*(?:(?:no|n[°º]|n[uú]mero)\.?\s*)?"
    r"(\d+[A-Za-z]?(?:-\d{1,3})?)\b",
    re.IGNORECASE,
)
# Forma vieja (cualquier palabra + número): respaldo para no perder lo que ya
# se reconocía si el texto empieza por algo que _NUMERO_PATTERN no espera.
_NUMERO_SIMPLE_PATTERN = re.compile(r"^\S+\s+(\d+)")
_GUID_PATTERN = re.compile(r"/getattachment/([0-9a-fA-F-]{36})/")

# Circulares conjuntas cuyo número no está en el texto del sitio sino solo en
# el PDF escaneado (no se puede leer automáticamente): consecutivo o radicado
# del Ministerio del Interior, que las expidió junto con MinCIT. Se usa
# abreviado, como el código CIR de minjusticia.py. Clave: GUID del enlace
# /getattachment/<guid>/ — no cambia aunque cambie el texto de la fila.
_NUMEROS_FIJOS = {
    "a441fda3-38c4-486f-972e-5aa38744245d": "OFI2021-32628",  # 17/11/2021
    "4256e984-c3f3-4b82-9500-f4d5eeed8673": "OFI2021-30421",  # 25/10/2021
    "671d34c1-8d0b-43ea-971c-085629ab90a8": "CIR2020-103",  # 20/08/2020
    "b2131143-6312-4bb0-91f5-ea5b35b2986d": "CIR2020-72",  # 28/06/2020
    "0a401c42-f674-409f-84de-10169f6ad7bd": "CIR2020-70",  # 18/06/2020
}
# Circular sin número en ningún lado: "SN", como minsalud.py/procuraduria.py.
_SIN_NUMERO = "SN"
_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
# Todo lo anterior al primer "," o ":" es "{tipo} {numero} del {fecha}"; lo que
# sigue es la descripción, con comillas opcionales alrededor (Resoluciones/
# Decretos/Leyes usan coma+comillas, Circulares usa dos puntos sin comillas) y
# un punto final opcional que se descarta junto con la comilla de cierre.
_DETALLE_PATTERN = re.compile(r'^[^,:]+[,:]\s*"?(.*?)"?\.?$', re.DOTALL)


def _parse_fecha(texto: str) -> Optional[str]:
    m = _FECHA_PATTERN.search(texto)
    if not m:
        return None
    dia, mes, anio = m.groups()
    return f"{anio}-{mes.zfill(2)}-{dia.zfill(2)}"


def _parse_numero(texto_archivo: str) -> Optional[str]:
    texto = texto_archivo.strip()
    m = _NUMERO_PATTERN.match(texto) or _NUMERO_SIMPLE_PATTERN.match(texto)
    return m.group(1) if m else None


def _numero_fijo(url: str) -> Optional[str]:
    m = _GUID_PATTERN.search(url)
    return _NUMEROS_FIJOS.get(m.group(1).lower()) if m else None


def _parse_detalle(texto_archivo: str) -> Optional[str]:
    m = _DETALLE_PATTERN.match(texto_archivo.strip())
    if not m:
        return None
    detalle = m.group(1).strip()
    return detalle or None


def _normalize_title(letra: str, numero: str, anio: str) -> str:
    if numero.isdigit():
        return codigo_ley_decreto(letra, numero, anio) or f"{letra}_MCIT_{int(numero):04d}_{anio}"
    m = re.fullmatch(r"(\d+)([A-Za-z])", numero)
    if m:
        # "036A": se rellena la parte numérica y se conserva la letra.
        return f"{letra}_MCIT_{int(m.group(1)):04d}{m.group(2).upper()}_{anio}"
    # Número compuesto ("100-003"), código de otra entidad ("CIR2020-103") o
    # "SN": tal cual, sin int()/relleno — mismo criterio que minjusticia.py.
    return f"{letra}_MCIT_{numero}_{anio}"


_SLUG_ANIO_PATTERN = re.compile(r"^(\d{4})(?:-(\d{4}))?$")


def _anios_del_slug(slug: str) -> List[int]:
    m = _SLUG_ANIO_PATTERN.match(slug)
    if not m:
        return []
    inicio = int(m.group(1))
    fin = int(m.group(2)) if m.group(2) else inicio
    if fin < inicio:
        inicio, fin = fin, inicio
    return list(range(inicio, fin + 1))


def _mapa_anio_a_slug(html: str, categoria: str) -> dict:
    patron = re.compile(rf'href="/normatividad/{re.escape(categoria)}/([^"]+)"')
    mapa = {}
    for slug in set(patron.findall(html)):
        for anio in _anios_del_slug(slug):
            mapa[anio] = slug
    return mapa


@register_family("mincit")
class ScrapMINCIT(BaseScrapper):
    filters_by_publication_date = True

    def __init__(self):
        self.source = "Ministerio de Comercio, Industria y Turismo"

    def _extraer_filas(self, html: str, tipo: str, letra: str, fini: str, ffin: str, on_progress=None) -> List[RawDocModel]:
        docs: List[RawDocModel] = []
        soup = BeautifulSoup(html, "html.parser")
        tabla = soup.find("table", id="Listado")
        if tabla is None:
            if on_progress:
                on_progress(f"[{self.source}] Error: no se encontró la tabla de documentos (id=Listado)")
            return docs
        tbody = tabla.find("tbody")
        if tbody is None:
            if on_progress:
                on_progress(f"[{self.source}] Error: la tabla de documentos no tiene <tbody>")
            return docs

        # Primero se arman TODAS las filas de la página y después se filtra por
        # rango: los sufijos _2, _3... de títulos repetidos (ver con_sufijos) se
        # calculan sobre la página completa, para que el título de un documento
        # no dependa del rango pedido en la corrida.
        filas = []
        for fila in tbody.find_all("tr"):
            celdas = fila.find_all("td")
            if len(celdas) < 6:
                continue

            texto_archivo = celdas[1].get_text(" ", strip=True)
            f_providencia = _parse_fecha(celdas[3].get_text(strip=True))
            f_public = _parse_fecha(celdas[4].get_text(strip=True))
            if not f_providencia or not f_public:
                continue

            enlace = celdas[5].find("a", href=True)
            if not enlace:
                continue
            url = urljoin(_BASE_URL, enlace["href"])

            numero = _numero_fijo(url) or _parse_numero(texto_archivo)
            if numero is None and letra == "C" and re.match(r"(?i)circular?\b", texto_archivo):
                numero = _SIN_NUMERO

            if numero is not None:
                title = _normalize_title(letra, numero, f_providencia[:4])
                title_unverified = False
            else:
                title = texto_archivo
                title_unverified = True
            filas.append((texto_archivo, f_providencia, f_public, url, title, title_unverified))

        # Solo las circulares SN del mismo año se distinguen con _2, _3...; el
        # resto de títulos repetidos del sitio se deja como estaba (cambiarlos
        # renombraría documentos ya guardados). Orden estable: fecha de
        # expedición y luego URL (el sitio no expone un id interno numérico).
        orden = {i: rango for rango, i in enumerate(sorted(range(len(filas)), key=lambda i: (filas[i][1], filas[i][3])))}
        sin_numero = [i for i, f in enumerate(filas) if f"_MCIT_{_SIN_NUMERO}_" in f[4]]
        con_sufijo = con_sufijos([(filas[i][4], orden[i]) for i in sin_numero])
        titulos = dict(zip(sin_numero, con_sufijo))

        for i, (texto_archivo, f_providencia, f_public, url, title, title_unverified) in enumerate(filas):
            if f_public < fini or f_public > ffin:
                continue
            title = titulos.get(i, title)
            safe_title = _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")

            docs.append(RawDocModel(
                source=self.source,
                link={"url": url, "method": "GET"},
                title=title,
                tipo=tipo,
                f_public=f_public,
                f_providencia=f_providencia,
                detalle=_parse_detalle(texto_archivo),
                save_path=storage_path(self.source, f_public, tipo, f"{safe_title}(extension)"),
                title_unverified=title_unverified,
            ))

        return docs

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        docs: List[RawDocModel] = []
        # Las páginas de archivo se agrupan por año de EXPEDICIÓN, pero el rango pedido
        # es de PUBLICACIÓN (ver filters_by_publication_date): una norma expedida en
        # diciembre suele publicarse semanas después, ya en el año siguiente. Se pide un
        # año extra hacia atrás; el filtro por f_public de _extraer_filas descarta lo que
        # quede fuera del rango real.
        _ANIOS_DE_MARGEN = 1
        anio_inicial = int(fini[:4]) - _ANIOS_DE_MARGEN
        anio_final = int(ffin[:4])

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
                    on_progress(f"[{self.source}] Error consultando índice de {tipo}: {e}")
                continue

            mapa = _mapa_anio_a_slug(resp.text, categoria)
            if not mapa:
                if on_progress:
                    on_progress(f"[{self.source}] Error: el índice de {tipo} no devolvió páginas de archivo reconocibles")
                continue

            slugs = sorted({mapa[a] for a in range(anio_inicial, anio_final + 1) if a in mapa})

            for slug in slugs:
                if stop_event is not None and stop_event.is_set():
                    return docs

                try:
                    resp = session.get(f"{_BASE_URL}/normatividad/{categoria}/{slug}", timeout=30)
                    resp.raise_for_status()
                except Exception as e:
                    if on_progress:
                        on_progress(f"[{self.source}] Error consultando {categoria}/{slug}: {e}")
                    continue

                docs.extend(self._extraer_filas(resp.text, tipo, letra, fini, ffin, on_progress=on_progress))
                if len(docs) >= limit:
                    return docs[:limit]

        # Páginas sin archivo por año (p. ej. circulares conjuntas): pocas filas,
        # se recorren completas y el filtro por f_public de _extraer_filas decide.
        urls_vistas = {d.link["url"] for d in docs}
        for slug, categoria in _PAGINAS_SUELTAS.items():
            if stop_event is not None and stop_event.is_set():
                return docs
            tipo, letra = _CATEGORIAS[categoria]
            try:
                resp = session.get(f"{_BASE_URL}/normatividad/{slug}", timeout=30)
                resp.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{self.source}] Error consultando {slug}: {e}")
                continue
            for doc in self._extraer_filas(resp.text, tipo, letra, fini, ffin, on_progress=on_progress):
                # Una conjunta que el sitio también lista en el archivo por año
                # no se repite.
                if doc.link["url"] not in urls_vistas:
                    urls_vistas.add(doc.link["url"])
                    docs.append(doc)
            if len(docs) >= limit:
                return docs[:limit]

        return docs
