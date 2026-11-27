"""Auditoría General de la República (AGR).

El sitio es un Liferay DXP: conceptos, resoluciones y circulares son
bibliotecas de documentos (portlet DLPortlet) organizadas en carpetas por
año. Las API JSON de Liferay responden 403 al invitado, así que se lee el
HTML del portlet. Diseño: docs/superpowers/specs/2026-11-23-fuente-auditoria-design.md.

TLS: el servidor envía su certificado (GeoTrust TLS RSA CA G1) con un
intermedio equivocado (Comodo AAA) en vez del G1, y `requests` falla con
CERTIFICATE_VERIFY_FAILED. Se usa verify=False SOLO para este host: en la
sesión del scraper y en link["verify"] = False para la descarga.

Fechas: el listado no trae la fecha de expedición. f_public = fecha de
carga del archivo (parámetro `?t=` del enlace, en hora de Bogotá) y el
filtro de la corrida va por esa fecha (filters_by_publication_date).
f_providencia = 1 de enero del año del documento (el de la carpeta).
"""
import datetime
import html as html_lib
import re
import unicodedata
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

import requests
import urllib3
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_SOURCE = "Auditoría General de la República"
_SIGLA = "AGR"
_ETIQUETA = "[Auditoría General]"
_ANIO_MINIMO = 2025
_BASE = "https://www.auditoria.gov.co/web/guest/auditoria/normatividad/"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "es-CO,es;q=0.9"}
_FILAS_POR_PAGINA = 500
# La carpeta más grande tiene ~110 archivos: con 500 por página cabe en una.
# Los topes sólo frenan un paginador o un árbol de carpetas que no terminen.
_PAGINAS_TOPE = 20
_CARPETAS_TOPE = 200
# Carpeta del "Normograma" del menú lateral: no es un acto de la AGR.
_CARPETAS_IGNORADAS = frozenset({"119334"})
_BOGOTA = datetime.timezone(datetime.timedelta(hours=-5))

# (nombre, página, instancia del portlet, carpeta inicial, clase)
# Las resoluciones arrancan en sus subcarpetas Orgánicas y Reglamentarias:
# la raíz de Resoluciones también trae Ordinarias (fuera de alcance) y
# "Repositorio Ofi Jurídica" (resoluciones del Minsalud).
_SECCIONES = (
    ("Conceptos jurídicos", "conceptos-juridicos", "h6j3F7UA67se", "108816", "CTO"),
    ("Resoluciones orgánicas", "resoluciones", "Jjx7nXQXAbGp", "2437712", "ORG"),
    ("Resoluciones reglamentarias", "resoluciones", "Jjx7nXQXAbGp", "2437715", "REG"),
    ("Circulares", "circulares", "pgO78BwckEE6", "108260", "CIRCULAR"),
)

_TIPOS = {
    "CTO": "Concepto",
    "ORG": "Resolución orgánica",
    "REG": "Resolución reglamentaria",
    "CE": "Circular externa",
    "CJ": "Circular conjunta",
    "CD": "Circular dispositiva",
}

# Quita tildes conservando la longitud del texto, para poder cortar el
# asunto (detalle) del nombre original con las posiciones del normalizado.
_SIN_TILDES = str.maketrans("áéíóúÁÉÍÓÚüÜñÑ", "aeiouAEIOUuUnN")

_ANIO_RE = re.compile(r"(?<!\d)(20\d{2}|19\d{2})(?!\d)")
_INTERVALO_RE = re.compile(r"Mostrando el intervalo\s+(\d+)\s*-\s*(\d+)\s+de\s+(\d+)")
_NUMERO = r"(\d+[a-z]?(?:-\d{1,2})?)"
_SEP_ANIO = r"(?:[\s_.-]*(?:de|del)?[\s_.-]*(\d{4})(?!\d))?"
_NRO = r"(?:n\s*[°º]|nro|no|numero)?\.?"
# Conceptos: lo que sigue al código de oficina 110 (se tolera la errata 1100).
_CONCEPTO_RE = re.compile(r"(?<!\d)1100?[.\-_ ]" + _NUMERO + r"(?:[.\-_ ](\d{4})(?!\d))?")
_RESOLUCION_RE = re.compile(
    r"(?:organicas?|org\b|reglament[a-z]*|regalment[a-z]*)\.?[\s_]*" + _NRO + r"[\s_.]*" + _NUMERO + _SEP_ANIO
)
_CIRCULAR_RE = re.compile(
    r"(externa|conjunta|dispositiva)[\s_]*" + _NRO + r"[\s_.]*" + _NUMERO + _SEP_ANIO
)
# Sin la palabra de la clase ("Circular 009 de 2026"): el número se lee igual
# y la clase queda como externa sin verificar.
_CIRCULAR_SIN_CLASE_RE = re.compile(r"circular(?:es)?[\s_]*" + _NRO + r"[\s_.]*" + _NUMERO + _SEP_ANIO)
_CLASE_CIRCULAR = {"externa": "CE", "conjunta": "CJ", "dispositiva": "CD"}
# Archivo sin clase reconocible en una carpeta de resoluciones
# ("39-02-2025_010-IGIP.pdf"): número entre _ y _/-.
_NUMERO_SUELTO_RE = re.compile(r"_(\d+)[_-]")
_ANEXO_RE = re.compile(r"\b(anexo|manual)")
_ORDINAL_RE = re.compile(r"^\s*\d{1,3}\.\s+")
_EXTENSION_RE = re.compile(r"\.(pdf|docx?|xlsx?)$", re.IGNORECASE)
_NO_TITULO_RE = re.compile(r"[^A-Za-z0-9-]+")


def _norm(texto: str) -> str:
    texto = unicodedata.normalize("NFC", texto or "").replace("\xa0", " ")
    return texto.translate(_SIN_TILDES).lower()


def _anio_en(texto: str) -> Optional[int]:
    m = _ANIO_RE.search(texto or "")
    return int(m.group(1)) if m else None


def _valor_numero(numero: str) -> str:
    """Valor para comparar números: 008 = 08 = 8 (conserva el sufijo)."""
    m = re.match(r"(\d+)(.*)", numero)
    return f"{int(m.group(1))}{m.group(2).upper()}" if m else numero.upper()


def _fecha_carga(t: str) -> Optional[str]:
    try:
        ms = int(t)
    except (TypeError, ValueError):
        return None
    return datetime.datetime.fromtimestamp(ms / 1000, tz=_BOGOTA).date().isoformat()


def _enlace_limpio(href: str) -> str:
    """Enlace de descarga sin `?t=` (cambia con cada versión) ni `download=true`."""
    p = urlsplit(href)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


def _parse_carpeta(html: str) -> Tuple[List[Tuple[str, str]], List[dict], Optional[Tuple[int, int, int]]]:
    """Subcarpetas [(folderId, nombre)], archivos y el intervalo (a, b, N) si
    aparece el texto "Mostrando el intervalo". Lee sólo las filas del portlet:
    así quedan fuera las migas de pan, el selector de tamaño de página y los
    enlaces del menú lateral y del pie."""
    soup = BeautifulSoup(html, "html.parser")
    subcarpetas: List[Tuple[str, str]] = []
    archivos: List[dict] = []
    uuids = set()
    for fila in soup.select('li[data-qa-id="row"]'):
        # data-title llega con entidades escapadas dos veces ("&#8211;").
        nombre = re.sub(r"\s+", " ", html_lib.unescape(fila.get("data-title", ""))).strip()
        if fila.get("data-folder") == "true":
            fid = fila.get("data-folder-id", "").strip()
            if fid and fid not in _CARPETAS_IGNORADAS and fid not in {c[0] for c in subcarpetas}:
                subcarpetas.append((fid, nombre))
            continue
        for a in fila.find_all("a", href=True):
            href = a["href"].strip()
            if "/documents/" not in href or "download=true" not in href:
                continue
            partes = urlsplit(href).path.strip("/").split("/")
            # documents/<groupId>/<folderId>/<nombre>/<uuid>
            if len(partes) < 5 or partes[2] in _CARPETAS_IGNORADAS:
                continue
            uuid = partes[4]
            if uuid in uuids:
                continue
            uuids.add(uuid)
            t = re.search(r"[?&]t=(\d+)", href)
            archivos.append({
                "nombre": nombre,
                "url": _enlace_limpio(href),
                "uuid": uuid,
                "t": t.group(1) if t else None,
            })
            break
    m = _INTERVALO_RE.search(soup.get_text(" "))
    intervalo = (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
    return subcarpetas, archivos, intervalo


def _numero(nombre: str, clase: str):
    """(número tal cual, año del nombre pegado al número, clase de circular
    leída del nombre, fin del número en el texto) o None si no se reconoce.
    Para resoluciones y circulares se toma la PRIMERA coincidencia: el resto
    del nombre puede citar otra norma ("Modifica la Reglamentaria 010_2024")."""
    texto = _norm(nombre)
    if clase == "CTO":
        m = _CONCEPTO_RE.search(texto)
        if not m:
            return None
        return m.group(1), (int(m.group(2)) if m.group(2) else None), None, m.end()
    if clase in ("ORG", "REG"):
        m = _RESOLUCION_RE.search(texto)
        if not m:
            return None
        return m.group(1), (int(m.group(2)) if m.group(2) else None), None, m.end()
    m = _CIRCULAR_RE.search(texto)
    if not m:
        m = _CIRCULAR_SIN_CLASE_RE.search(texto)
        if not m:
            return None
        return m.group(1), (int(m.group(2)) if m.group(2) else None), None, m.end()
    return m.group(2), (int(m.group(3)) if m.group(3) else None), _CLASE_CIRCULAR[m.group(1)], m.end()


def _detalle(nombre: str, fin: Optional[int]) -> Optional[str]:
    """Asunto: lo que sigue al número (sin el ordinal de carga ni la extensión)."""
    resto = nombre[fin:] if fin is not None else ""
    resto = _EXTENSION_RE.sub("", resto.strip())
    resto = re.sub(r"^[\s.,;:_()\-–]+", "", resto)
    resto = re.sub(r"[\s.,;:_\-–]+$", "", resto)
    resto = re.sub(r"\s+", " ", resto.replace("_", " ")).strip()
    return resto or None


def _numero_titulo(numero: str) -> str:
    return _NO_TITULO_RE.sub("", numero.upper())


def _titulo(prefijo: str, numero: str, anio: int, clase_resolucion: Optional[str] = None) -> str:
    num = _numero_titulo(numero)
    if clase_resolucion:
        num = f"{clase_resolucion}-{num}"
    return f"{prefijo}_{_SIGLA}_{num}_{anio}"


def _prefijo_y_tipo(clase: str, clase_circular: Optional[str]) -> Tuple[str, str, Optional[str]]:
    """(prefijo del título, tipo, clase que va dentro del número)."""
    if clase == "CTO":
        return "CTO", _TIPOS["CTO"], None
    if clase in ("ORG", "REG"):
        return "R", _TIPOS[clase], clase
    return clase_circular, _TIPOS[clase_circular], None


def _clase_circular_de_carpeta(nombre_carpeta: str) -> Optional[str]:
    texto = _norm(nombre_carpeta)
    for palabra, clase in _CLASE_CIRCULAR.items():
        if palabra in texto:
            return clase
    return None


@register_family("auditoria")
class ScrapAuditoria(BaseScrapper):
    # Filtro por fecha de carga (?t=): el listado no trae la de expedición.
    filters_by_publication_date = True
    # Una versión nueva del mismo archivo conserva el uuid (y por tanto el
    # enlace limpio) pero cambia ?t=: sin la fecha en el doc_id no se
    # duplica y la revisión por tamaño detecta la republicación.
    doc_id_uses_publication_date = False

    def __init__(self):
        self.source = _SOURCE

    def _get_carpeta(self, session, pagina, instancia, folder_id, stop_event):
        """Todas las páginas de una carpeta: (subcarpetas, archivos)."""
        prefijo = f"_com_liferay_document_library_web_portlet_DLPortlet_INSTANCE_{instancia}_"
        url = f"{_BASE}{pagina}/-/document_library/{instancia}/view/{folder_id}"
        subcarpetas: List[Tuple[str, str]] = []
        archivos: List[dict] = []
        for cur in range(1, _PAGINAS_TOPE + 1):
            if stop_event is not None and stop_event.is_set():
                break
            resp = session.get(
                url,
                params={prefijo + "deltaEntry": str(_FILAS_POR_PAGINA), prefijo + "curEntry": str(cur)},
                timeout=60,
            )
            resp.raise_for_status()
            subs, arch, intervalo = _parse_carpeta(resp.text)
            for s in subs:
                if s not in subcarpetas:
                    subcarpetas.append(s)
            vistos = {a["uuid"] for a in archivos}
            archivos.extend(a for a in arch if a["uuid"] not in vistos)
            if intervalo is None or intervalo[1] >= intervalo[2]:
                return subcarpetas, archivos, False
        return subcarpetas, archivos, True

    def _recorrer(self, session, pagina, instancia, raiz, nombre_seccion, stop_event, avisar):
        """Recorre en profundidad desde `raiz`. Devuelve archivos con su
        contexto: año de la carpeta (el más cercano con año en el nombre),
        nombre de la carpeta donde están y si es la raíz de la sección."""
        salida: List[dict] = []
        pendientes = [(raiz, nombre_seccion, None, True)]
        visitadas = set()
        while pendientes:
            if stop_event is not None and stop_event.is_set():
                break
            folder_id, nombre, anio, es_raiz = pendientes.pop(0)
            if folder_id in visitadas:
                continue
            visitadas.add(folder_id)
            if len(visitadas) > _CARPETAS_TOPE:
                avisar(f"{_ETIQUETA} {nombre_seccion}: demasiadas carpetas; se corta el recorrido")
                break
            try:
                subs, archivos, truncada = self._get_carpeta(session, pagina, instancia, folder_id, stop_event)
            except requests.RequestException as e:
                avisar(f"{_ETIQUETA} Error leyendo la carpeta «{nombre}» de {nombre_seccion}: {e}")
                if es_raiz:
                    raise
                continue
            if truncada:
                avisar(f"{_ETIQUETA} La carpeta «{nombre}» alcanzó el tope de páginas; puede quedar incompleta")
            for a in archivos:
                salida.append({**a, "anio_carpeta": anio, "carpeta": nombre, "en_raiz": es_raiz})
            hijas = []
            for fid, sub_nombre in subs:
                sub_anio = _anio_en(sub_nombre)
                # Una carpeta con un año menor que el piso no se abre; las
                # carpetas sin año en el nombre se abren siempre.
                if sub_anio is not None and sub_anio < _ANIO_MINIMO:
                    continue
                hijas.append((fid, sub_nombre, sub_anio or anio, False))
            pendientes[0:0] = hijas
        return salida

    def _documentos_de_seccion(self, archivos, clase, nombre_seccion, avisar):
        """Convierte los archivos de una sección en (orden, datos de documento)
        aplicando año, número, dedup y anexos."""
        candidatos = []
        for orden, a in enumerate(archivos):
            nombre = a["nombre"]
            leido = _numero(nombre, clase)
            clase_circular = None
            if clase == "CIRCULAR" and not a["en_raiz"]:
                # La clase sale de la subcarpeta ("Circulares Externas 2025");
                # un archivo suelto en la carpeta del año ("2025/") no la
                # trae y se toma del nombre del archivo más abajo.
                clase_circular = _clase_circular_de_carpeta(a["carpeta"])
            anio_nombre = leido[1] if leido else None
            anio = a["anio_carpeta"]
            if anio is None:
                anio = anio_nombre or (_anio_en(nombre) if leido is None else None)
                if anio is None:
                    avisar(
                        f"{_ETIQUETA} {nombre_seccion}: «{nombre}» no trae año y está fuera de las "
                        "carpetas por año; se omite"
                    )
                    continue
            elif anio_nombre is not None and anio_nombre != anio:
                avisar(
                    f"{_ETIQUETA} {nombre_seccion}: «{nombre}» dice {anio_nombre} pero está en la "
                    f"carpeta de {anio}; se usa {anio}"
                )
            if anio < _ANIO_MINIMO:
                continue
            fecha = _fecha_carga(a["t"])
            if fecha is None:
                avisar(f"{_ETIQUETA} {nombre_seccion}: «{nombre}» sin fecha de carga; se omite")
                continue
            norm = _norm(nombre)
            if leido is None:
                tipo_orden = 2
            elif _ANEXO_RE.search(norm):
                tipo_orden = 1
            else:
                tipo_orden = 0
            candidatos.append({
                "a": a, "leido": leido, "anio": anio, "fecha": fecha, "orden": orden,
                "clase_circular": clase_circular, "tipo_orden": tipo_orden,
            })

        # Primero los de las carpetas de año, luego los de la raíz; dentro de
        # cada grupo, principales antes que anexos y que los sin clase.
        candidatos.sort(key=lambda c: (c["a"]["en_raiz"], c["tipo_orden"], c["orden"]))
        principales: Dict[tuple, dict] = {}
        anexos_por_base: Dict[str, int] = {}
        resultado = []
        for c in candidatos:
            a, anio, nombre = c["a"], c["anio"], c["a"]["nombre"]
            unverified = False
            detalle = None
            if c["leido"] is not None:
                numero, _anio_nombre, clase_circ_nombre, fin = c["leido"]
                clase_circular = c["clase_circular"] or clase_circ_nombre
                if clase == "CIRCULAR" and clase_circular is None:
                    avisar(f"{_ETIQUETA} {nombre_seccion}: «{nombre}» sin clase de circular; se toma externa")
                    clase_circular, unverified = "CE", True
                prefijo, tipo, clase_res = _prefijo_y_tipo(clase, clase_circular)
                clave = (prefijo, clase_res, _valor_numero(numero), anio)
                base = _titulo(prefijo, numero, anio, clase_res)
                detalle = _detalle(nombre, fin)
                if clave in principales:
                    previo = principales[clave]
                    if a["en_raiz"] and not previo["en_raiz"]:
                        # Mismo concepto en la raíz y en su carpeta del año.
                        continue
                    if c["tipo_orden"] != 1:
                        avisar(
                            f"{_ETIQUETA} {nombre_seccion}: número repetido {base}: «{previo['nombre']}» y "
                            f"«{nombre}»; el segundo queda como anexo"
                        )
                    title = self._siguiente_anexo(previo["base"], anexos_por_base)
                else:
                    principales[clave] = {"nombre": nombre, "en_raiz": a["en_raiz"],
                                          "carpeta": a["carpeta"], "base": base}
                    title = base
            else:
                # Sin número reconocible. En una carpeta de resoluciones, un
                # "_<n>-" que coincide con una resolución de la misma carpeta
                # se toma como su anexo (p. ej. 39-02-2025_010-IGIP.pdf).
                prefijo, tipo, clase_res = _prefijo_y_tipo(clase, c["clase_circular"] or "CE")
                title = None
                if clase in ("ORG", "REG"):
                    for m in _NUMERO_SUELTO_RE.finditer(nombre):
                        clave = (prefijo, clase_res, _valor_numero(m.group(1)), anio)
                        previo = principales.get(clave)
                        if previo and previo["carpeta"] == a["carpeta"]:
                            title = self._siguiente_anexo(previo["base"], anexos_por_base)
                            avisar(
                                f"{_ETIQUETA} {nombre_seccion}: «{nombre}» no dice qué resolución es; "
                                f"se toma como anexo de {previo['base']}"
                            )
                            break
                if title is None:
                    saneado = _NO_TITULO_RE.sub("", _EXTENSION_RE.sub("", nombre).upper())[:40] or "SN"
                    title = f"{prefijo}_{_SIGLA}_{saneado}_{anio}"
                    unverified = True
                    avisar(f"{_ETIQUETA} {nombre_seccion}: no se reconoce el número de «{nombre}»")
                detalle = _detalle(_ORDINAL_RE.sub("", nombre), 0)
            resultado.append({
                "url": a["url"], "title": title, "tipo": tipo, "fecha": c["fecha"], "anio": anio,
                "detalle": detalle, "unverified": unverified,
            })
        return resultado

    @staticmethod
    def _siguiente_anexo(base: str, anexos_por_base: Dict[str, int]) -> str:
        n = anexos_por_base.get(base, 0) + 1
        anexos_por_base[base] = n
        return f"{base}_A{n:02d}"

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        def avisar(texto):
            if on_progress is not None:
                on_progress(texto)

        session = requests.Session()
        # Cadena TLS con el intermedio equivocado; ver nota del módulo.
        session.verify = False
        session.headers.update(_HEADERS)
        docs: List[RawDocModel] = []
        urls = set()

        for nombre_seccion, pagina, instancia, raiz, clase in _SECCIONES:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            avisar(f"{_ETIQUETA} Procesando {nombre_seccion}...")
            try:
                archivos = self._recorrer(session, pagina, instancia, raiz, nombre_seccion, stop_event, avisar)
            except requests.RequestException:
                continue
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            encontrados = self._documentos_de_seccion(archivos, clase, nombre_seccion, avisar)
            if not encontrados:
                avisar(f"{_ETIQUETA} {nombre_seccion}: no se encontraron documentos desde {_ANIO_MINIMO}")
            for d in encontrados:
                if not (fini <= d["fecha"] <= ffin) or d["url"] in urls:
                    continue
                urls.add(d["url"])
                docs.append(RawDocModel(
                    source=_SOURCE,
                    # verify=False: cadena TLS rota del host; ver nota del módulo.
                    link={"url": d["url"], "method": "GET", "verify": False},
                    title=d["title"],
                    tipo=d["tipo"],
                    f_public=d["fecha"],
                    f_providencia=f"{d['anio']}-01-01",
                    detalle=d["detalle"],
                    title_unverified=d["unverified"],
                    save_path=storage_path(_SOURCE, d["fecha"], d["tipo"], f"{d['title']}(extension)"),
                ))
                if len(docs) >= limit:
                    return docs[:limit]
        return docs[:limit]
