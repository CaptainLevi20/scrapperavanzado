"""Contraloría General de la República (CGR).

El "Sistema de Búsqueda de Normas" de la CGR
(cgr-sistemanormatividad.contraloria.gov.co, una aplicación React) consume una
API JSON pública que es un intermediario sobre cuatro bibliotecas de SharePoint
Online. Esa API es la fuente real: cada listado responde la biblioteca completa
en una sola petición `POST`, y los archivos se bajan con otro `POST`
(`getDownloadFileApiBuffer`, cuerpo `{"Id", "List"}`).

Particularidades (ver docs/superpowers/specs/2026-11-23-fuente-contraloria-design.md):

- El número se lee del nombre del archivo (`FileLeafRef`), no del campo
  "Número", que viene truncado o con basura en varias filas. Se copia tal
  cual lo escribe la CGR (sin rellenar ni quitar ceros).
- La identidad del documento es el número normalizado (`body["path"]`), no
  el `Id` de SharePoint, porque la CGR borra y vuelve a crear filas con otro
  `Id` y otra fecha.
- Los `Id` se repiten entre bibliotecas y, para esos, la API entrega a veces
  el archivo de otra biblioteca. Para las filas de la ventana cuyo `Id` se
  repite se pregunta a `getFileInfo` qué archivo saldría; si no es el de la
  fila, se omite con aviso y entra en una corrida posterior.
"""

import re
import time
import unicodedata
from typing import Dict, List, Optional, Set, Tuple

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_SOURCE = "Contraloría General de la República"
_SIGLA = "CGR"
_ANIO_MINIMO = 2015
_API = "https://cgr-sistemarelatoria-api.contraloria.gov.co/api/relatoria2"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_HEADERS = {"User-Agent": _UA, "Accept": "application/json"}

# Cuerpo que manda el formulario vacío del buscador: trae la biblioteca entera.
_CUERPO_LISTADO = {
    "ResolucionClasificacion": None,
    "ResolucionVigencia": None,
    "CircularDestinatario": None,
    "CircularAnio": None,
    "ConceptoJuridicoAnio": None,
    "ConceptoJuridicoTipoConcepto": None,
    "JurisprudenciaAnio": None,
    "JurisprudenciaCorporacion": None,
    "JurisprudenciaTipoProvidencia": None,
    "JurisprudenciaSalaSeccion": None,
    "OrdenarPor": {
        "Label": "FechaDecision",
        "id": 1,
        "Title": "Fecha de decisión más reciente primero",
        "Default": False,
    },
    "keyword": "",
    "FechaInicio": None,
    "FechaFin": None,
    "PalabrasClave": None,
    "advQuery": [],
}

# (clave interna, endpoint, biblioteca de SharePoint, campo de fecha, campo de
# número, campo de detalle, nombre para los avisos)
_SECCIONES = [
    ("resoluciones", "getResoluciones", "Resoluciones",
     "Fecha_x0020_de_x0020_expedicion", "Numero_x0020_de_x0020_resolucion", "Title", "Resoluciones"),
    ("conceptos", "getConceptosJuridicos", "Conceptos Juridicos",
     "Fecha", "Numero_x0020_de_x0020_concepto", "Tema", "Conceptos jurídicos"),
    ("circulares", "getCirculares", "Circulares",
     "Fecha", "Numero_x0020_de_x0020_Circular", "Asunto2", "Circulares"),
]
# Jurisprudencia no se descarga (sentencias de las cortes, no actos de la
# CGR); se lee sólo para saber qué `Id` se repiten entre bibliotecas.
_JURISPRUDENCIA = ("getJurisprudencia", "Jurisprudencia")

_EXTENSIONES = {"pdf", "doc", "docx"}
_ALGO_SALIO_MAL = "something went wrong"
# Pausa entre llamadas a getFileInfo (una por segundo, para no cargar la API).
_PAUSA_VERIFICACION = 1.0

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|#]')

_RES_RE = re.compile(r"^(OGZ|REG-EJE|REG-ORG|ORG|REG)[- ]*(\d+[A-Z]?)[- ]+(\d{4})", re.I)
# Radicado del gestor documental (conceptos de 2015 y alguno suelto de 2016).
# "1E" es un error de digitación de "IE" que aparece en 8 archivos.
_RADICADO_RE = re.compile(r"(?<!\d)((\d{4})(?:EE|IE|1E)\d{6,8})(?!\d)", re.I)
_CTO_RE = re.compile(
    r"^0?CGR\s*-\s*[O0]J\s*-\s*(?:PI\s*-\s*)?(\d+[A-Z]?)\s*(?:-|de\b)\s*(\d{4})(?!\d)", re.I
)
_CIR_RE = re.compile(r"^Circular\s+(Conjunta\s+)?(\d+[A-Z]?)\s*-\s*(\d{4})(?!\d)", re.I)
_CIR_NUM_RE = re.compile(r"^(?:Circular\s+)?(Conjunta\s+)?(\d+[A-Z]?)\s*-\s*(\d{4})(?!\d)", re.I)


def _norm_texto(s) -> str:
    s = unicodedata.normalize("NFC", s or "").replace("​", "")
    return re.sub(r"\s+", " ", s).strip()


def _norm_guiones(s: str) -> str:
    return re.sub(r"[‐-―]", "-", s or "")


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title or "")[:120].strip(" .")


def _valor(numero: str) -> str:
    """Número para comparar (identidad y duplicados): sin ceros a la izquierda
    y con su letra en mayúscula (`0131A` → `131A`, `0000` → `0`)."""
    return re.sub(r"^0+(?=\d)", "", numero).upper()


def _fecha(item: dict, campo: str) -> Optional[str]:
    """La parte de fecha del ISO UTC (`…T05:00:00Z`, `T07`, `T08`) ya es la
    fecha correcta en Colombia: no se convierte de zona."""
    crudo = item.get(campo) or ""
    if not re.match(r"^\d{4}-\d{2}-\d{2}", crudo):
        return None
    return crudo[:10]


def _partes_archivo(file_leaf_ref: str) -> Tuple[str, str]:
    """(nombre sin extensión, extensión en minúscula) de `FileLeafRef`."""
    nombre = _norm_texto(file_leaf_ref)
    if "." not in nombre:
        return nombre, ""
    stem, _, ext = nombre.rpartition(".")
    return stem, ext.lower()


def _num_resolucion(texto: str) -> Optional[Tuple[str, str, int]]:
    """(serie, número tal cual, año) de `OGZ-0897-2026`, `REG-EJE-0131A-2024`…"""
    m = _RES_RE.match(_norm_guiones(_norm_texto(texto)))
    if not m:
        return None
    return m.group(1).upper(), m.group(2).upper(), int(m.group(3))


def _num_concepto(texto: str) -> Optional[Tuple[str, int]]:
    """(número tal cual, año) de `CGR-OJ-130-2026`, `CGR–OJ-157 de 2024`,
    `CGR-OJ-PI-144-2024`, `CGR-OJ-0094A-2021-PI`, `0CGR-OJ-0189-2018`,
    `CGR-0J-016 de 2024`, o el radicado (`2015EE0012345`, `20151E0038709`,
    `CGR-OJ-2016IE0067575`)."""
    limpio = _norm_guiones(_norm_texto(texto))
    m = _RADICADO_RE.search(limpio)
    if m:
        return m.group(1).upper(), int(m.group(2))
    m = _CTO_RE.match(limpio)
    if m:
        return m.group(1).upper(), int(m.group(2))
    return None


def _num_circular(texto: str, regex=_CIR_RE) -> Optional[Tuple[bool, str, int]]:
    """(conjunta, número tal cual, año) de `Circular 0004-2015`,
    `Circular Conjunta 0010-2025`."""
    m = regex.match(_norm_guiones(_norm_texto(texto)))
    if not m:
        return None
    return bool(m.group(1)), m.group(2).upper(), int(m.group(3))


def _identificar(seccion: str, item: dict, campo_numero: str, stem: str, anio_fecha: int):
    """Devuelve (título, tipo, clave de identidad, año del número, verificado).

    `clave` es el número normalizado (ver "Identidad del documento" en el
    diseño); una fila sin número legible usa el nombre del archivo saneado.
    El título lleva el número tal cual."""
    campo = _norm_texto(item.get(campo_numero))
    if seccion == "resoluciones":
        r = _num_resolucion(stem) or _num_resolucion(campo)
        if r:
            serie, num, anio = r
            return (f"R_{_SIGLA}_{serie}-{num}_{anio}", "Resolución",
                    f"{serie}-{_valor(num)}-{anio}", anio, True)
        tipo = "Resolución"
    elif seccion == "conceptos":
        c = _num_concepto(stem) or _num_concepto(campo)
        if c:
            num, anio = c
            return (f"CTO_{_SIGLA}_{num}_{anio}", "Concepto", f"{_valor(num)}-{anio}", anio, True)
        tipo = "Concepto"
    else:
        c = _num_circular(stem) or _num_circular(campo, _CIR_NUM_RE)
        if c:
            conjunta, num, anio = c
            if conjunta:
                return (f"CJ_{_SIGLA}_{num}_{anio}", "Circular conjunta",
                        f"CJ-{_valor(num)}-{anio}", anio, True)
            return (f"C_{_SIGLA}_{num}_{anio}", "Circular", f"{_valor(num)}-{anio}", anio, True)
        tipo = "Circular"
    titulo = _safe_title(stem) or "documento"
    return titulo, tipo, f"archivo-{titulo}", anio_fecha, False


def _link(item_id: int, biblioteca: str, seccion: str, clave: str, ext: str) -> dict:
    """Descarga por `POST`. `body["path"]` es la identidad (compute_doc_id lo
    usa en vez de la URL, que es la misma para todos). El fragmento `#…` sólo
    sirve para que el descargador tome la extensión del final de la URL (la
    API no manda `Content-Disposition`); `requests` no lo envía."""
    return {
        "url": f"{_API}/getDownloadFileApiBuffer#{clave}.{ext}",
        "method": "POST",
        "body": {"Id": item_id, "List": biblioteca, "path": f"cgr/{seccion}/{clave}"},
    }


def _listar(session: requests.Session, endpoint: str) -> list:
    resp = session.post(f"{_API}/{endpoint}", json=_CUERPO_LISTADO, timeout=120)
    resp.raise_for_status()
    datos = resp.json()
    if not isinstance(datos, list):
        raise ValueError(f"respuesta inesperada de {endpoint}")
    return datos


def _info_archivo(session: requests.Session, item_id: int, biblioteca: str) -> Optional[str]:
    """`FileRef` que entregaría la descarga ahora mismo, o None si la API no
    responde bien (un reintento si dice "something went wrong")."""
    for intento in range(2):
        try:
            resp = session.post(
                f"{_API}/getFileInfo", json={"Id": item_id, "List": biblioteca}, timeout=60
            )
            if resp.status_code == 200 and _ALGO_SALIO_MAL not in resp.text:
                ref = resp.json().get("FileRef")
                if ref:
                    return ref
        except (requests.RequestException, ValueError):
            pass
        if intento == 0 and _PAUSA_VERIFICACION:
            time.sleep(_PAUSA_VERIFICACION)
    return None


@register_family("contraloria")
class ScrapContraloria(BaseScrapper):
    # La descarga es un POST a un endpoint común: no hay URL para un HEAD.
    checks_for_republication = False
    # La fecha cambia cuando la CGR recrea una fila: no entra en la identidad.
    doc_id_uses_publication_date = False
    # Cada corrida trae la biblioteca completa en una petición; mirar atrás no
    # cuesta y cubre las cargas tardías (el 90 % de las resoluciones se sube
    # en menos de 45 días; hay lotes de conceptos viejos).
    scheduled_min_lookback_days = 120

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None):
        def aviso(msg):
            if on_progress:
                on_progress(f"[{_SOURCE}] {msg}")

        session = requests.Session()
        session.headers.update(_HEADERS)

        listados: Dict[str, list] = {}
        bibliotecas_de_id: Dict[int, Set[str]] = {}
        algun_listado_fallo = False
        endpoints = [(s[0], s[1], s[2], s[6]) for s in _SECCIONES]
        endpoints.append(("jurisprudencia", _JURISPRUDENCIA[0], _JURISPRUDENCIA[1], "Jurisprudencia"))
        for clave, endpoint, biblioteca, nombre in endpoints:
            if stop_event is not None and stop_event.is_set():
                return []
            if clave != "jurisprudencia":
                aviso(f"Procesando {nombre}...")
            try:
                filas = _listar(session, endpoint)
            except (requests.RequestException, ValueError) as exc:
                algun_listado_fallo = True
                aviso(f"Aviso: no se pudo leer el listado de {nombre}: {exc}")
                continue
            listados[clave] = filas
            for fila in filas:
                if isinstance(fila.get("Id"), int):
                    bibliotecas_de_id.setdefault(fila["Id"], set()).add(biblioteca)
        if algun_listado_fallo:
            aviso("Aviso: faltó algún listado; se verifica el archivo de todos los registros de la ventana")

        docs: List[RawDocModel] = []
        for seccion, _endpoint, biblioteca, campo_fecha, campo_numero, campo_detalle, nombre in _SECCIONES:
            filas = listados.get(seccion)
            if filas is None:
                continue
            vistos: Dict[str, str] = {}
            for fila in filas:
                if stop_event is not None and stop_event.is_set():
                    return docs[:limit]
                doc = self._fila_a_doc(
                    session, fila, seccion, biblioteca, campo_fecha, campo_numero, campo_detalle,
                    nombre, fini, ffin, bibliotecas_de_id, algun_listado_fallo, vistos, aviso,
                )
                if doc is None:
                    continue
                docs.append(doc)
                if len(docs) >= limit:
                    return docs[:limit]
        return docs[:limit]

    def _fila_a_doc(self, session, fila, seccion, biblioteca, campo_fecha, campo_numero,
                    campo_detalle, nombre, fini, ffin, bibliotecas_de_id, verificar_todo,
                    vistos, aviso) -> Optional[RawDocModel]:
        archivo = _norm_texto(fila.get("FileLeafRef"))
        item_id = fila.get("Id")
        fecha = _fecha(fila, campo_fecha)
        if fecha is None:
            # Sin fecha no se puede filtrar. Se avisa salvo que el número diga
            # que es anterior al piso (resoluciones viejas de 2000-2013).
            anios = re.findall(r"(?<!\d)(\d{4})(?!\d)", archivo)
            if not anios or int(anios[-1]) >= _ANIO_MINIMO:
                aviso(f"Aviso: {nombre}: registro sin fecha «{archivo[:70]}», se omite")
            return None
        if int(fecha[:4]) < _ANIO_MINIMO or fecha < fini or fecha > ffin:
            return None

        stem, ext = _partes_archivo(archivo)
        if ext not in _EXTENSIONES or not isinstance(item_id, int):
            aviso(f"Aviso: {nombre}: registro sin archivo descargable «{archivo[:70]}», se omite")
            return None

        titulo, tipo, clave, anio_num, verificado = _identificar(
            seccion, fila, campo_numero, stem, int(fecha[:4])
        )
        if not verificado:
            aviso(f"Aviso: {nombre}: no se reconoce el número de «{archivo[:70]}»; se guarda sin verificar")
        elif anio_num != int(fecha[:4]):
            aviso(f"Aviso: {titulo}: el año del número ({anio_num}) no coincide con la fecha {fecha}")

        if clave in vistos:
            aviso(f"Aviso: {nombre}: «{archivo[:70]}» repite el número de «{vistos[clave][:70]}», se omite")
            return None

        # Un Id que existe en otra biblioteca puede descargar el archivo de
        # esa otra: se pregunta qué archivo saldría ahora.
        if verificar_todo or len(bibliotecas_de_id.get(item_id, ())) > 1:
            esperado = f"/sites/relatoria2/{biblioteca}/{fila.get('FileLeafRef')}"
            ref = _info_archivo(session, item_id, biblioteca)
            if _PAUSA_VERIFICACION:
                time.sleep(_PAUSA_VERIFICACION)
            if ref is None:
                aviso(f"Aviso: {titulo}: la CGR no respondió qué archivo entrega; se omite y se intenta en otra corrida")
                return None
            if _norm_texto(ref).casefold() != _norm_texto(esperado).casefold():
                aviso(
                    f"Aviso: {titulo}: la CGR entrega otro archivo para este registro en este momento "
                    f"({ref.rsplit('/', 2)[-2]}/{ref.rsplit('/', 1)[-1]}); se omite y se intenta en otra corrida"
                )
                return None

        vistos[clave] = archivo
        detalle_partes = []
        if seccion == "resoluciones" and _norm_texto(fila.get("Clasificacion")):
            detalle_partes.append(_norm_texto(fila.get("Clasificacion")))
        if _norm_texto(fila.get(campo_detalle)):
            detalle_partes.append(_norm_texto(fila.get(campo_detalle)))
        detalle = " — ".join(detalle_partes) or None

        return RawDocModel(
            source=_SOURCE,
            link=_link(item_id, biblioteca, seccion, clave, ext),
            title=titulo,
            tipo=tipo,
            f_public=fecha,
            f_providencia=fecha,
            detalle=detalle,
            save_path=storage_path(_SOURCE, fecha, tipo, f"{_safe_title(titulo)}(extension)"),
            title_unverified=not verificado,
        )
