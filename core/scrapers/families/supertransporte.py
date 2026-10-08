"""Superintendencia de Transporte (Supertransporte).

Sitio WordPress (www.supertransporte.gov.co) más la "Biblioteca Jurídica", una
aplicación aparte con los conceptos. Ver
docs/superpowers/specs/2026-10-08-fuente-supertransporte-design.md.

- Resoluciones generales: una página por año (2000→hoy) generada por el plugin
  "resoluciones_menu"; cada bloque <section class="resolution"> trae número,
  fecha, epígrafe, el PDF y a veces anexos.
- Circulares externas, conjuntas y resoluciones internas: listas de enlaces en
  la página de Normativa (transparencia-normatividad), con número y fecha en
  el texto del enlace.
- Circulares SICOV: lista numerada en su propia página.
- Circular Única de Infraestructura y Transporte: un PDF por título; cuando la
  actualizan suben PDFs nuevos en otra carpeta, que entran como documentos
  nuevos con su fecha.
- Conceptos (2020-2021): la Biblioteca Jurídica es una aplicación React cuyo
  listado viene escrito dentro de su propio bundle.js (no consulta ningún
  servidor); los archivos se sirven desde /files/<nombre>. Sus fechas son de
  relleno ("01-01-<año>"), así que el filtro de rango es por año.

Las carpetas de /documentos/ siguen el patrón <año>/<Mes>/<Dependencia>_<día>/:
es la fecha en que se subió el archivo y se usa como fecha de publicación (una
resolución del 3 de agosto puede subirse el 2 de septiembre). Si la carpeta no
sigue el patrón se usa la fecha de expedición.
"""
import re
import unicodedata
from datetime import date
from typing import Dict, List, NamedTuple, Optional, Tuple
from urllib.parse import quote, unquote, urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.naming import con_sufijos
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE = "https://www.supertransporte.gov.co"
_NORMATIVA = f"{_BASE}/index.php/transparencia-normatividad/"
_RESOLUCIONES = f"{_BASE}/index.php/resoluciones-generales/"
_SICOV = f"{_BASE}/index.php/transparencia-normatividad-circular-sicov/"
_CIRCULAR_UNICA = f"{_BASE}/index.php/circulares/circular-unica-de-infraestructura-y-transporte/"
_BIBLIOTECA = "https://bibliotecajuridica.supertransporte.gov.co:3000"
_SOURCE = "Superintendencia de Transporte"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

_SIGLA = "SPT"
_TIPO_RES = "Resolución"
_TIPO_CIR = "Circular"
_TIPO_TCU = "Título Circular Única"
_TIPO_CTO = "Concepto"

_ANIO_MIN = 2000
# Años de margen hacia atrás al elegir páginas de resoluciones: la página es la
# del año de expedición y la fecha pedida es la de publicación (subida).
_ANIOS_DE_MARGEN = 1

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_MAX_TITULO = 120

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _norm(s: str) -> str:
    """Minúsculas, sin acentos y con espacios colapsados (incluye &nbsp;)."""
    sin = "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin).strip().lower()


def _espacios(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:_MAX_TITULO].strip(" .")


def _crudo(texto: str) -> str:
    return (texto or "").strip()[:_MAX_TITULO].strip(" .") or "documento"


def _iso(anio: int, mes: int, dia: int) -> Optional[str]:
    try:
        return date(anio, mes, dia).isoformat()
    except ValueError:
        return None


_FECHA_RE = re.compile(r"(\d{1,2})\s+de\s+([a-z]+)(?:\s+(?:de|del)?\s*(\d{4}))?")


_MES_PEGADO_RE = re.compile(r"(" + "|".join(_MESES) + r")(del?)\b")


def _fecha_texto(texto: str, anio_defecto: Optional[int] = None) -> Optional[str]:
    """«03 de Agosto 2026», «31 de Marzo de 2000», «08 de Noviembrede 2012»,
    «Bogotá, 22 de Diciembre» (sin año: se usa `anio_defecto`)."""
    for m in _FECHA_RE.finditer(_MES_PEGADO_RE.sub(r"\1 \2", _norm(texto))):
        mes = _MESES.get(m.group(2))
        if mes is None:
            continue
        anio = int(m.group(3)) if m.group(3) else anio_defecto
        if anio is None:
            continue
        iso = _iso(anio, mes, int(m.group(1)))
        if iso:
            return iso
    return None


_CARPETA_RE = re.compile(r"/documentos/(\d{4})/([A-Za-z]+)/[^/]*?_(\d{1,2})(?:_[A-Za-z]+)?/", re.IGNORECASE)


def _fecha_carpeta(url: str) -> Optional[str]:
    """Fecha de subida según la carpeta: /documentos/2026/Septiembre/Notificaciones_02/."""
    m = _CARPETA_RE.search(unquote(url))
    if not m:
        return None
    mes = _MESES.get(_norm(m.group(2)))
    if mes is None:
        return None
    return _iso(int(m.group(1)), mes, int(m.group(3)))


def _publicacion(url: str, expedicion: str) -> str:
    """La fecha de la carpeta, salvo que sea anterior a la expedición (carpeta
    reutilizada): entonces la de expedición."""
    carpeta = _fecha_carpeta(url)
    return carpeta if carpeta and carpeta >= expedicion else expedicion


def _numero(n: str) -> str:
    """Números cortos con relleno a 4 dígitos; radicados largos tal cual."""
    n = n.lstrip("0") or "0"
    return f"{int(n):04d}" if len(n) <= 6 else n


_EXT_DOCUMENTO = (".pdf", ".tif", ".tiff", ".zip", ".doc", ".docx", ".xls", ".xlsx")


def _es_documento(url: str) -> bool:
    """Archivos del sitio; deja fuera páginas web enlazadas como «anexo» y
    videos tutoriales."""
    return "/documentos/" in url and unquote(url).lower().endswith(_EXT_DOCUMENTO)


# ---------------------------------------------------------------- resoluciones

class Resolucion(NamedTuple):
    url: str
    title: str
    unverified: bool
    expedicion: Optional[str]
    detalle: Optional[str]


_NUM_RES_RE = re.compile(r"resolucion(?:es)?\s*(?:no\.?\s*)?(\d+)\s+de\s+(\d{4})")


def _resoluciones_de_pagina(html: str, anio_pagina: int) -> List[Resolucion]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Resolucion] = []
    for sec in soup.select("section.resolution"):
        enlaces = sec.select("a.boton-enlace-activo")
        if not enlaces:
            continue
        cabeza = _espacios(enlaces[0].get_text(" "))
        parrafos = [_espacios(p.get_text(" ")) for p in sec.find_all("p")]
        # «Fecha de resolución: …» / «Fecha de publicación: …»; las de 2011 dicen
        # «Bogotá, 22 de Diciembre» en el primer párrafo (y el epígrafe puede
        # hablar de una «fecha límite»)
        texto_fecha = next((p for p in parrafos if _norm(p).startswith("fecha de")), parrafos[0] if parrafos else "")
        expedicion = _fecha_texto(texto_fecha, anio_pagina)
        detalle = next((p for p in parrafos if p != texto_fecha), None) or None

        m = _NUM_RES_RE.search(_norm(cabeza))
        anio = m.group(2) if m else str(anio_pagina)
        base = f"R_{_SIGLA}_{_numero(m.group(1))}_{anio}" if m else None

        anexo = 0
        for a in enlaces:
            href = a.get("href")
            if not href:
                continue
            url = urljoin(_BASE, href.strip())
            if a is not enlaces[0] and not _es_documento(url):
                continue
            texto = _espacios(a.get_text(" "))
            otra = _NUM_RES_RE.search(_norm(texto)) if a is not enlaces[0] else None
            if otra:
                # un bloque que enlaza, además, otras resoluciones que lo
                # acompañan («Supertransporte expide la Resolución 5554 de 2016»)
                out.append(Resolucion(url, f"R_{_SIGLA}_{_numero(otra.group(1))}_{otra.group(2)}", False, expedicion, texto))
            elif re.fullmatch(r"\d+", texto):
                # «Supertransporte expide las Resoluciones 19009, 19010 y 19011»:
                # cada enlace es una resolución distinta
                out.append(Resolucion(url, f"R_{_SIGLA}_{_numero(texto)}_{anio}", False, expedicion, detalle))
            elif a is enlaces[0]:
                if base:
                    out.append(Resolucion(url, base, False, expedicion, detalle))
                else:
                    out.append(Resolucion(url, _crudo(cabeza.replace("Supertransporte expide la", "")), True, expedicion, detalle))
            else:
                anexo += 1
                principal = base or _crudo(cabeza)
                out.append(Resolucion(url, f"{principal}_A{anexo:02d}", base is None, expedicion, texto.strip(" -") or detalle))
    return out


def _paginas_por_anio(html: str) -> Dict[int, str]:
    """El selector de años sólo enlaza los recientes (y 2020 vive en /2020-2/);
    los demás siguen el patrón /<año>/."""
    mapa: Dict[int, str] = {}
    for m in re.finditer(r'href="(https://www\.supertransporte\.gov\.co/index\.php/resoluciones-generales/((\d{4})[^/"]*)/)"', html):
        mapa.setdefault(int(m.group(3)), m.group(1))
    return mapa


# ----------------------------------------------------------------- circulares

class Entrada(NamedTuple):
    url: str
    texto: str
    seccion: str


_SECCIONES_NORMATIVA = {
    "res-internas": "Resoluciones internas",
    "circ-externas": "Circulares externas",
    "circ-conjuntas": "Circulares conjuntas",
}


def _entradas_normativa(html: str) -> List[Entrada]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Entrada] = []
    for ancla, seccion in _SECCIONES_NORMATIVA.items():
        bloque = soup.find(id=ancla)
        if bloque is None:
            continue
        for a in bloque.find_all("a", href=True):
            url = urljoin(_BASE, a["href"].strip())
            if "/documentos/" in url:
                out.append(Entrada(url, _espacios(a.get_text(" ")), seccion))
    return out


def _entradas_sicov(html: str) -> List[Entrada]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Entrada] = []
    for a in soup.find_all("a", href=True):
        texto = _espacios(a.get_text(" "))
        # sólo la lista numerada («1. Circular Externa …»); la página trae además
        # enlaces globales del sitio (carta de trato digno, etc.)
        if "/documentos/" in a["href"] and re.match(r"\d+\.\s*circular", _norm(texto)):
            out.append(Entrada(urljoin(_BASE, a["href"].strip()), texto, "Circulares SICOV"))
    return out


_NUM_CIR_RE = re.compile(r"^(?:\d+\.\s*)?circular(?:\s+(?:conjunta|externa|mt))*\s*(?:no\.?\s*)?(\d+)\s+(?:del?\s+(?:\d{1,2}\s+de\s+[a-z]+\s+de\s+)?)?(\d{4})")
_NUM_RES_INTERNA_RE = re.compile(r"^resolucion\s*(?:no\.?\s*)?(\d+)\s+del?\s+(?:\d{1,2}\s+de\s+[a-z]+\s+de\s+)?(\d{4})")


def _titulo_entrada(e: Entrada, expedicion: str) -> Tuple[str, str, bool]:
    """(tipo, título, sin verificar). El número sólo cuenta si el texto EMPIEZA
    por el acto: «Alcance a la Circular…» o «Fe de Erratas – Circular…» son
    otros documentos y quedan con su texto."""
    t = _norm(e.texto)
    if e.seccion == "Resoluciones internas":
        m = _NUM_RES_INTERNA_RE.match(t)
        if m:
            return _TIPO_RES, f"R_{_SIGLA}_{_numero(m.group(1))}_{m.group(2)}", False
        return _TIPO_RES, _crudo(e.texto), True
    m = _NUM_CIR_RE.match(t)
    if m:
        return _TIPO_CIR, f"C_{_SIGLA}_{_numero(m.group(1))}_{m.group(2)}", False
    if "circular" in _norm(unquote(e.url)) and not re.search(r"\d{3,}", t) and not t.startswith(("alcance", "fe de erratas")):
        # «Reiteración cumplimiento régimen normativo…»: circular sin número
        return _TIPO_CIR, f"C_{_SIGLA}_SN_{expedicion[:4]}", False
    return _TIPO_CIR, _crudo(e.texto), True


_SEPARADOR_RE = re.compile(r"\s[–—-]\s|[–—)]|\s-|-\s")


def _expedicion_entrada(e: Entrada) -> Optional[str]:
    # sólo la cabeza: la descripción puede citar otras fechas («… Resolución
    # 993 de 25 de Abril de 2017», «… antes del 18 de diciembre de 2017»)
    cabeza = _SEPARADOR_RE.split(e.texto, maxsplit=1)[0]
    fecha = _fecha_texto(cabeza)
    if fecha:
        return fecha
    # SICOV sólo dice «Circular 43 de 2018»: la carpeta da el día si es del
    # mismo año; si no, 1 de enero de ese año
    m = re.search(r"\bde\s+(\d{4})\b", _norm(e.texto))
    carpeta = _fecha_carpeta(e.url)
    if m:
        if carpeta and carpeta[:4] == m.group(1):
            return carpeta
        return f"{m.group(1)}-01-01"
    return carpeta


# ------------------------------------------------------------ circular única

_ROMANO_RE = re.compile(r"^titulo\s+([ivxlc]+)\b")


def _titulos_circular_unica(html: str) -> List[Tuple[str, str]]:
    """(url, texto) de los PDFs de la sección «Anexos» (un PDF por título)."""
    soup = BeautifulSoup(html, "html.parser")
    out: List[Tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        url = urljoin(_BASE, a["href"].strip())
        texto = _espacios(a.get_text(" "))
        t = _norm(texto)
        if "/documentos/" in url and url.lower().endswith(".pdf") and (_ROMANO_RE.match(t) or "cuadro control" in t):
            out.append((url, texto))
    return out


def _titulo_tcu(texto: str, publicacion: str) -> str:
    m = _ROMANO_RE.match(_norm(texto))
    parte = m.group(1).upper() if m else "CUADRO-CONTROL"
    return f"TCU_{_SIGLA}_{parte}_{publicacion.replace('-', '')}"


# ------------------------------------------------------------------- conceptos

class Concepto(NamedTuple):
    archivo: str
    tema: str
    contenido: str
    anio: str


_CAMPO_RE = re.compile(r'"(\w+)":\s*"((?:[^"\\]|\\.)*)"')
_BLOQUE_RE = re.compile(r'\{[^{}]*?"categoria"[^{}]*\}')


def _conceptos_del_bundle(js: str) -> List[Concepto]:
    """El listado de la Biblioteca está escrito como `this.documents = [...]`
    en ProcessService.js (no es JSON estricto: lleva comentarios), así que se
    lee objeto por objeto."""
    i = js.find("this.documents = [")
    if i < 0:
        return []
    j = js.find("];", i)
    out: List[Concepto] = []
    vistos = set()
    for bloque in _BLOQUE_RE.findall(js[i:j]):
        d = dict(_CAMPO_RE.findall(bloque))
        if d.get("categoria") != "Conceptos":
            continue
        archivo = d.get("documento", "").strip()
        if not archivo or archivo in vistos:
            continue
        vistos.add(archivo)
        anio = archivo[:4] if re.match(r"(19|20)\d{2}\d{10}\.", archivo) else (d.get("anio") or "").strip()
        if not re.fullmatch(r"\d{4}", anio):
            continue
        out.append(Concepto(archivo, _espacios(d.get("titulo", "")), _espacios(d.get("contenido", "")), anio))
    return out


def _titulo_concepto(c: Concepto) -> Tuple[str, bool]:
    m = re.fullmatch(r"(\d{14})\.\w+", c.archivo)
    if m:
        return f"CTO_{_SIGLA}_{m.group(1)}", False
    return _crudo(f"{c.tema} {c.contenido}"), True


def _bundle_url(html: str) -> str:
    m = re.search(r'<script[^>]+src="([^"]+\.js)"', html)
    return urljoin(_BIBLIOTECA + "/", m.group(1)) if m else f"{_BIBLIOTECA}/static/js/bundle.js"


# ---------------------------------------------------------------------- familia

@register_family("supertransporte")
class ScrapSupertransporte(BaseScrapper):
    filters_by_publication_date = True
    # La carpeta (fecha de subida) puede ir semanas detrás de la expedición, y
    # el sitio no avisa: mirar un mes atrás cuesta las mismas pocas páginas.
    scheduled_min_lookback_days = 30

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": _UA})
        docs: List[RawDocModel] = []
        vistos: set = set()

        def parar() -> bool:
            return stop_event is not None and stop_event.is_set()

        def avisar(msg: str) -> None:
            if on_progress:
                on_progress(f"[{_SOURCE}] {msg}")

        def get(url: str, que: str) -> Optional[str]:
            try:
                resp = session.get(url, timeout=90)
                resp.raise_for_status()
            except Exception as e:
                avisar(f"Error consultando {que}: {e}")
                return None
            if "charset" not in resp.headers.get("Content-Type", "").lower():
                # sin charset requests asume ISO-8859-1; el sitio y el bundle son UTF-8
                resp.encoding = "utf-8"
            return resp.text

        def emitir(filas: List[Tuple[str, str, bool, str, str, str, Optional[str]]], en_rango) -> bool:
            """filas: (url, título, sin verificar, tipo, expedición, publicación,
            detalle). Los títulos repetidos se distinguen con _2, _3… sobre el
            conjunto completo (no sólo el rango) para que no dependan de él.
            Devuelve True si se alcanzó el límite."""
            # el mismo archivo enlazado dos veces (un bloque que repite
            # resoluciones con bloque propio) cuenta una sola vez, antes de
            # calcular sufijos
            unicas: Dict[str, int] = {}
            for i, f in enumerate(filas):
                unicas.setdefault(f[0], i)
            filas = [filas[i] for i in sorted(unicas.values())]
            # el nombre limpio es para la copia expedida y subida primero
            orden = sorted(range(len(filas)), key=lambda i: (filas[i][4], filas[i][5], filas[i][0]))
            rango = {i: k for k, i in enumerate(orden)}
            titulos = con_sufijos([(f[1], rango[i]) for i, f in enumerate(filas)])
            for (url, _, unv, tipo, exp, pub, detalle), title in zip(filas, titulos):
                if url in vistos or not en_rango(pub):
                    continue
                vistos.add(url)
                docs.append(RawDocModel(
                    source=_SOURCE,
                    link={"url": url, "method": "GET"},
                    title=title,
                    tipo=tipo,
                    f_public=pub,
                    f_providencia=exp,
                    detalle=detalle or None,
                    save_path=storage_path(_SOURCE, pub, tipo, f"{_safe_title(title)}(extension)"),
                    title_unverified=unv,
                ))
                if len(docs) >= limit:
                    return True
            return False

        def por_fecha(pub: str) -> bool:
            return fini <= pub <= ffin

        # 1. Resoluciones generales, página por año
        avisar("Procesando resoluciones generales...")
        hoy = date.today()
        anio_ini = max(_ANIO_MIN, int(fini[:4]) - _ANIOS_DE_MARGEN)
        anio_fin = min(int(ffin[:4]), hoy.year)
        indice = get(f"{_RESOLUCIONES}{hoy.year}/", "el índice de resoluciones") or ""
        mapa = _paginas_por_anio(indice)
        total_res = 0
        for anio in range(anio_ini, anio_fin + 1):
            if parar():
                return docs[:limit]
            html = get(mapa.get(anio, f"{_RESOLUCIONES}{anio}/"), f"las resoluciones de {anio}")
            if html is None:
                continue
            filas = []
            for r in _resoluciones_de_pagina(html, anio):
                if r.expedicion is None:
                    avisar(f"Aviso: resolución sin fecha «{r.title}», se omite")
                    continue
                filas.append((r.url, r.title, r.unverified, _TIPO_RES, r.expedicion, _publicacion(r.url, r.expedicion), r.detalle))
            total_res += len(filas)
            if emitir(filas, por_fecha):
                return docs[:limit]
        if total_res == 0 and not parar():
            avisar("Error: las páginas de resoluciones no devolvieron ninguna resolución (¿cambió el marcado?)")

        # 2. Circulares y resoluciones internas (Normativa + SICOV), juntas para
        # que el mismo número en dos listas se distinga con _2
        if parar():
            return docs[:limit]
        avisar("Procesando circulares y resoluciones internas...")
        entradas: List[Entrada] = []
        html = get(_NORMATIVA, "la página de Normativa")
        if html is not None:
            entradas += _entradas_normativa(html)
        html = get(_SICOV, "la página de circulares SICOV")
        if html is not None:
            entradas += _entradas_sicov(html)
        if not entradas:
            avisar("Error: no se encontró ninguna circular (¿cambió el marcado?)")
        filas = []
        previo: Optional[Tuple] = None
        for e in entradas:
            exp = _expedicion_entrada(e)
            if exp is None:
                avisar(f"Aviso: circular sin fecha «{e.texto[:70]}», se omite")
                continue
            if _norm(e.texto).startswith("anexo") and previo is not None:
                # «Anexo técnico SICOV-OTPC / Circular Externa No. …»: anexo de la
                # circular listada justo antes
                tipo, title, unv = previo[3], f"{previo[1]}_A01", previo[2]
            else:
                tipo, title, unv = _titulo_entrada(e, exp)
            fila = (e.url, title, unv, tipo, exp, _publicacion(e.url, exp), e.texto)
            filas.append(fila)
            previo = fila
        if emitir(filas, por_fecha):
            return docs[:limit]

        # 3. Circular Única: un PDF por título
        if parar():
            return docs[:limit]
        avisar("Procesando la Circular Única de Infraestructura y Transporte...")
        html = get(_CIRCULAR_UNICA, "la Circular Única")
        if html is not None:
            filas = []
            for url, texto in _titulos_circular_unica(html):
                pub = _fecha_carpeta(url)
                if pub is None:
                    avisar(f"Aviso: título de la Circular Única sin fecha de carpeta «{texto}», se omite")
                    continue
                filas.append((url, _titulo_tcu(texto, pub), False, _TIPO_TCU, pub, pub, texto))
            if not filas:
                avisar("Error: la Circular Única no trajo ningún título (¿cambió el marcado?)")
            if emitir(filas, por_fecha):
                return docs[:limit]

        # 4. Conceptos de la Biblioteca Jurídica: fechas sólo de año
        if parar():
            return docs[:limit]
        avisar("Procesando conceptos de la Biblioteca Jurídica...")
        html = get(f"{_BIBLIOTECA}/", "la Biblioteca Jurídica")
        js = get(_bundle_url(html), "el listado de la Biblioteca Jurídica") if html is not None else None
        if js is not None:
            conceptos = _conceptos_del_bundle(js)
            if not conceptos:
                avisar("Error: la Biblioteca Jurídica no trajo ningún concepto (¿cambió la aplicación?)")
            anio_a, anio_b = int(fini[:4]), int(ffin[:4])
            filas = []
            for c in conceptos:
                title, unv = _titulo_concepto(c)
                fecha = f"{c.anio}-01-01"
                url = f"{_BIBLIOTECA}/files/{quote(c.archivo)}"
                detalle = " — ".join(x for x in (c.tema, c.contenido) if x)
                filas.append((url, title, unv, _TIPO_CTO, fecha, fecha, detalle))
            if emitir(filas, lambda pub: anio_a <= int(pub[:4]) <= anio_b):
                return docs[:limit]

        return docs[:limit]
