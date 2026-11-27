"""Prosperidad Social (DPS): resoluciones, circulares y acuerdos interinstitucionales.

Las páginas de "Normativa" del sitio son WordPress + Elementor. Cada sección
es una página con un acordeón por año y, dentro, una tabla
``TIPO | FECHA | No. | CONTENIDO``. La API REST de WordPress entrega la página
entera (todos los años) en una sola respuesta, así que cada corrida lee la
sección completa con una petición.

Los PDF no están en WordPress: cada número enlaza a un enlace compartido
anónimo de SharePoint Online. Con ``download=1`` el enlace redirige al PDF
real (y ``HEAD`` también funciona, así que la revisión de republicación por
tamaño sirve).

Decretos y leyes del sector quedan fuera (decisión del usuario del
2026-11-26: sólo lo propio del DPS). El Normograma aparte de la entidad
queda para una v2. Ver docs/superpowers/specs/2026-11-23-fuente-dps-design.md.
"""
import datetime
import re
import unicodedata
from typing import List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE = "https://prosperidadsocial.gov.co"
_API_PAGES = f"{_BASE}/wp-json/wp/v2/pages"
_SOURCE = "Departamento Administrativo para la Prosperidad Social"
_SIGLA = "DPS"
_ANIO_MINIMO = 2015
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# (nombre de la sección, id de la página de WordPress, tipo, prefijo)
_SECCIONES = [
    ("Resoluciones", 33139, "Resolución", "R"),
    ("Circulares", 1221, "Circular", "C"),
    ("Acuerdos interinstitucionales", 52177, "Acuerdo", "A"),
]

_MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
# Enlace compartido de SharePoint que apunta a un archivo. Los ":f:" son
# carpetas, no documentos.
_SHAREPOINT_RE = re.compile(r"^https://[a-z0-9-]+\.sharepoint\.com/:(?!f:)[a-z]:/", re.IGNORECASE)
_ANIO_PANEL_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
_NUMERO_RE = re.compile(r"^(\d+)")
_NO_TITULO_RE = re.compile(r"[^A-Z0-9-]+")


def _limpiar(texto: str) -> str:
    """Quita los espacios de ancho cero que el sitio pone por todas partes
    (incluso dentro del número: ``1\\u200b997``) y normaliza los espacios."""
    texto = (texto or "").replace("​", "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", texto).strip()


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _mes(palabra: str) -> Optional[int]:
    """Mes a partir de su nombre completo o abreviado (``sep``, ``sept``,
    ``julio``, ``Dic``)."""
    palabra = _sin_tildes(palabra.lower())
    if len(palabra) < 3:
        return None
    for i, nombre in enumerate(_MESES, start=1):
        if nombre.startswith(palabra):
            return i
    return None


def _es_anio(token: str) -> bool:
    # "15", "2015" y el error de digitación "018" (año de 3 cifras).
    return token.isdigit() and (len(token) in (2, 4) or (len(token) == 3 and token.startswith("0")))


def _parse_fecha(texto: str, anio_panel: int) -> Optional[datetime.date]:
    """Fecha de expedición de la celda FECHA.

    Aparecen muchas formas: ``06 de noviembre de 2026``, ``19 de junio 2024``,
    ``27-feb-15``, ``05-ene.-17``, ``28-sep-018``, ``06-mar``, ``24 – ene``,
    ``sept-20`` (mes primero, sin año)… Muchas no traen año: el año es
    siempre el del panel del acordeón, que es lo que agrupa el listado y el
    que va en el título. Devuelve None si no se puede leer.
    """
    tokens = [t for t in re.findall(r"\d+|[^\W\d_]+", _limpiar(texto).lower()) if t not in ("de", "del")]
    dia = mes = None
    if len(tokens) in (2, 3) and tokens[0].isdigit():
        dia, mes = int(tokens[0]), _mes(tokens[1])
        if len(tokens) == 3 and not _es_anio(tokens[2]):
            return None
    elif len(tokens) == 2 and tokens[1].isdigit():
        mes, dia = _mes(tokens[0]), int(tokens[1])
    if dia is None or mes is None:
        return None
    try:
        return datetime.date(anio_panel, mes, dia)
    except ValueError:
        return None


def _titulo(prefijo: str, numero: str, anio: int) -> Tuple[str, bool]:
    """Título canónico y si quedó sin verificar.

    El número se copia tal cual lo escribe el DPS, sin quitar ni poner ceros
    (decisión del administrador del 2026-11-26): ``00464`` → ``R_DPS_00464_2016``.
    De ``0079 Anexo`` se toma la parte numérica.
    """
    numero = _limpiar(numero)
    m = _NUMERO_RE.match(numero)
    if m:
        return f"{prefijo}_{_SIGLA}_{m.group(1)}_{anio}", False
    saneado = _NO_TITULO_RE.sub("", _sin_tildes(numero.upper())) or "SN"
    return f"{prefijo}_{_SIGLA}_{saneado}_{anio}", True


def _clave_numero(numero: str, anio: int):
    """Para comparar números: ``2418`` y ``02418`` son el mismo."""
    m = _NUMERO_RE.match(_limpiar(numero))
    return (int(m.group(1)) if m else _limpiar(numero).upper(), anio)


def _url_descarga(href: str) -> str:
    """El enlace compartido abre un visor; con ``download=1`` redirige al PDF."""
    return f"{href}{'&' if '?' in href else '?'}download=1"


def _enlaces_sharepoint(nodo) -> List[str]:
    vistos = []
    for a in nodo.find_all("a", href=True):
        href = a["href"].strip()
        if _SHAREPOINT_RE.match(href) and href not in vistos:
            vistos.append(href)
    return vistos


def _filas(html: str) -> List[dict]:
    """Filas de todos los paneles de una sección, en el orden del sitio."""
    soup = BeautifulSoup(html or "", "html.parser")
    filas = []
    for panel in soup.select("div.elementor-toggle-item"):
        titulo = panel.select_one(".elementor-toggle-title")
        m = _ANIO_PANEL_RE.search(_limpiar(titulo.get_text(" ")) if titulo else "")
        anio = int(m.group(1)) if m else None
        for tr in panel.select("tr"):
            celdas = tr.find_all("td", recursive=False)
            if len(celdas) < 3:
                continue
            textos = [_limpiar(td.get_text(" ")) for td in celdas]
            if textos[1].upper() == "FECHA" or textos[0].upper() == "TIPO":
                continue  # cabecera
            numero_a = next(
                (a for a in celdas[2].find_all("a", href=True) if _SHAREPOINT_RE.match(a["href"].strip())),
                None,
            )
            numero = _limpiar(numero_a.get_text(" ")) if numero_a else textos[2]
            filas.append({
                "anio": anio,
                "panel": _limpiar(titulo.get_text(" ")) if titulo else "",
                "tipo": textos[0],
                "fecha": textos[1],
                "numero": numero,
                "enlaces": _enlaces_sharepoint(tr),
                "epigrafe": textos[3] if len(textos) > 3 else "",
            })
    return filas


@register_family("dps")
class ScrapDPS(BaseScrapper):
    # Los PDF se suben días o semanas después de la expedición (la 243654,
    # expedida el 06-11-2026, se subió el 10-11). Cada corrida lee la página
    # entera con una petición, así que mirar atrás no cuesta nada.
    scheduled_min_lookback_days = 60
    # La fecha se arma con texto libre + el año del panel: si el DPS reescribe
    # la celda, con la fecha en el doc_id el mismo PDF entraría como nuevo. El
    # enlace compartido de SharePoint es estable y único por archivo.
    doc_id_uses_publication_date = False
    # Resoluciones publica a tandas: la pausa más larga entre expediciones
    # desde 2020 es de 53 días (142 entre ago-2019 y ene-2020), y la carga al
    # sitio llega días o semanas después. Circulares está parada desde 2021 y
    # Acuerdos tiene una sola fila, así que la alerta la marca Resoluciones.
    alerta_margen_dias = 120

    def __init__(self):
        self.source = _SOURCE

    def _leer_seccion(self, session, page_id: int) -> str:
        resp = session.get(f"{_API_PAGES}/{page_id}", params={"_fields": "id,modified,content"}, timeout=60)
        resp.raise_for_status()
        return resp.json()["content"]["rendered"]

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        def avisar(texto):
            if on_progress:
                on_progress(f"[{_SIGLA}] {texto}")

        session = requests.Session()
        session.headers.update({"User-Agent": _UA, "Accept-Language": "es-CO,es;q=0.9"})

        docs: List[RawDocModel] = []
        # enlace → (sección, clave del número, título): la deduplicación por
        # enlace cruza secciones (las circulares 01 de 2018 y 2019 comparten PDF).
        por_enlace = {}

        for nombre, page_id, tipo, prefijo in _SECCIONES:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            avisar(f"Procesando {nombre}...")
            try:
                filas = _filas(self._leer_seccion(session, page_id))
            except Exception as e:  # una sección caída no tumba la corrida
                avisar(f"Error consultando {nombre}: {e}")
                continue
            if not filas:
                avisar(f"{nombre}: la página llegó sin filas; puede haber cambiado el sitio.")
                continue

            por_numero = {}
            # Todas las filas desde el piso se recorren aunque caigan fuera de
            # la ventana: así la deduplicación (y el título que se queda) no
            # depende del rango de la corrida.
            for fila in filas:
                if stop_event is not None and stop_event.is_set():
                    return docs[:limit]
                anio = fila["anio"]
                if anio is None:
                    avisar(f"{nombre}: panel sin año ('{fila['panel']}'), fila {fila['numero']} omitida.")
                    continue
                if anio < _ANIO_MINIMO:
                    continue
                titulo, sin_verificar = _titulo(prefijo, fila["numero"], anio)
                fecha = _parse_fecha(fila["fecha"], anio)
                if fecha is None:
                    avisar(f"{nombre} {anio}: fecha ilegible '{fila['fecha']}' en la fila {fila['numero']}; se omite.")
                    continue
                if not fila["enlaces"]:
                    avisar(f"{nombre} {anio}: fila {fila['numero']} sin enlace a SharePoint; se omite.")
                    continue

                clave = _clave_numero(fila["numero"], anio)
                principal, *anexos = fila["enlaces"]
                if principal in por_enlace:
                    otra_seccion, otra_clave, otro_titulo = por_enlace[principal]
                    if (otra_seccion, otra_clave) != (nombre, clave):
                        avisar(f"{titulo} y {otro_titulo} usan el mismo archivo en el sitio; se guarda sólo {otro_titulo}.")
                    continue
                if clave in por_numero:
                    avisar(f"{nombre} {anio}: número repetido {fila['numero']} con otro enlace; se queda {por_numero[clave]}.")
                    continue
                por_numero[clave] = titulo
                por_enlace[principal] = (nombre, clave, titulo)
                if sin_verificar:
                    avisar(f"{nombre} {anio}: número no reconocido '{fila['numero']}'; título {titulo} sin verificar.")

                archivos = [(titulo, principal)]
                for href in anexos:
                    if href in por_enlace:
                        continue
                    anexo = f"{titulo}_A{len(archivos):02d}"
                    por_enlace[href] = (nombre, clave, anexo)
                    archivos.append((anexo, href))

                f = fecha.isoformat()
                if not (fini <= f <= ffin):
                    continue
                for titulo_doc, href in archivos:
                    docs.append(RawDocModel(
                        source=_SOURCE,
                        link={"url": _url_descarga(href), "method": "GET"},
                        title=titulo_doc,
                        tipo=tipo,
                        f_public=f,
                        f_providencia=f,
                        detalle=fila["epigrafe"] or None,
                        save_path=storage_path(_SOURCE, f, tipo, f"{titulo_doc}(extension)"),
                        title_unverified=sin_verificar,
                    ))
                if len(docs) >= limit:
                    return docs[:limit]
        return docs[:limit]
