"""Procuraduría General de la Nación (PGN) — dos secciones de la Relatoría
(apps.procuraduria.gov.co/relatoria). Diseño:
docs/superpowers/specs/2026-09-28-fuente-procuraduria-design.md

- Normativa: buscador de normatividad, consultado año por año (sin año el
  sitio devuelve 0 filas).
- Conceptos: SIREL, tipos CONCEPTO y CONCEPTO (MISIONAL), por rango de fechas
  (se pide el año completo para que los sufijos por choque sean estables).

La página de SharePoint normatividad.aspx es solo un marco vacío; el contenido
real es esta aplicación Java. Ambos buscadores MUESTRAN un reCAPTCHA que el
servidor no exige para los GET de paginación que el propio sitio enlaza. Si
algún día lo exige, la respuesta llega sin el pie "Resultados … de N" y la
sección registra un Error — nunca se intenta resolver ni saltar el reCAPTCHA.
"""
import base64
import datetime
import re
import unicodedata
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

from core.fecha_es import _MESES
from core.models import RawDocModel
from core.naming import codigo_ley_decreto
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_SOURCE = "Procuraduría General de la Nación"
_ANIO_MIN = 2015
# Con el User-Agent por defecto de un navegador sin ventana ("HeadlessChrome")
# www.procuraduria.gov.co responde una página de bloqueo; con uno de Chrome
# normal (o el de requests + este encabezado) responde bien.
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
_RELATORIA = "https://apps.procuraduria.gov.co/relatoria/index.jsp"
_OPT_NORMATIVA = "co.gov.pgn.relatoria.frontend.component.pagefactory.NormatividadPageFactory"
_OPT_SIREL = "co.gov.pgn.relatoria.frontend.component.pagefactory.PirelResolucionesPageFactory"
_TIPOS_CONCEPTO = ("CONCEPTO", "CONCEPTO (MISIONAL)")
# Filas por página pedidas al buscador (max_results). Hoy el año más grande de
# conceptos tiene ~5.800 filas, así que cabe en una sola página; la consulta
# igual pagina por si crece.
_PAGINA = 10000
_TIMEOUT = 300

# Los enlaces propios de Normativa llegan "sucios": host apps. (da 404),
# mode=1#page=inline, tabulación al final, o la URL pegada varias veces. Se toma
# el PRIMER relId y se arma siempre la forma canónica en www. (verificada para
# ids viejos y nuevos, HEAD incluido).
_RELID_RE = re.compile(r"accion=verDocumentoRel&(?:amp;)?relId=([A-Za-z0-9+/=%]+)")
_DOC_REL = "https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId={}&mode=inline"

# Nomenclatura acordada con el equipo de fuentes (clave: tipo del sitio en
# minúsculas y sin acentos). Las conjuntas se pliegan a su tipo base en el
# TÍTULO; el campo `tipo` del documento conserva el nombre original.
_PREFIJOS = {
    "resolucion": "R",
    "directiva": "DIR",
    "directiva conjunta": "DIR",
    "circular": "C",
    "circular conjunta": "C",
    "memorando": "M",
    "carta circular": "CCIR",
    "instructivo": "INS",
    "acuerdo": "A",
    "protocolo": "PRO",
}
_PREFIJO_DESCONOCIDO = "DOC"

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')


def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def _clave_tipo(tipo: str) -> str:
    return " ".join(_sin_acentos(tipo).lower().split())


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _relid(href: Optional[str]) -> Optional[str]:
    m = _RELID_RE.search(href or "")
    return m.group(1) if m else None


def _url_normativa(relid: str) -> str:
    return _DOC_REL.format(relid)


def _id_de_relid(relid: str) -> int:
    """relId es el id numérico del documento en base64 (MjQ0MTg1 -> 244185).
    Se usa solo para ordenar los choques de título; 0 si no decodifica."""
    try:
        crudo = unquote(relid)
        crudo += "=" * (-len(crudo) % 4)
        return int(base64.b64decode(crudo, validate=True).decode("ascii"))
    except Exception:
        return 0


def _numero_normativa(numero: str) -> str:
    n = " ".join((numero or "").split())
    if re.fullmatch(r"\d+", n):
        return f"{int(n):04d}"
    m = re.fullmatch(r"(\d+)\s*([A-Za-z])", n)
    if m:
        return f"{int(m.group(1)):04d}{m.group(2).upper()}"
    return n.replace(" ", "")


def _titulo_normativa(tipo: str, numero: str, anio: int, id_interno: int) -> Tuple[str, bool]:
    """(título, tipo_desconocido). El Decreto usa el código común de
    ministerios (D####YYY, deduplicado entre fuentes en el worker)."""
    clave = _clave_tipo(tipo)
    crudo = (numero or "").strip()
    if clave == "decreto" and re.fullmatch(r"\d+", crudo):
        return codigo_ley_decreto("D", crudo, str(anio)), False
    num = _numero_normativa(crudo) or f"SN{id_interno}"
    prefijo = _PREFIJOS.get(clave)
    if prefijo is None:
        return f"{_PREFIJO_DESCONOCIDO}_PGN_{num}_{anio}", True
    return f"{prefijo}_PGN_{num}_{anio}", False


def _fecha_iso(texto: str) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat((texto or "").strip())
    except ValueError:
        return None


# SIREL escribe la fecha en prosa con el día de la semana y SIN "de":
# "jueves, 30 julio 2026" (core.fecha_es exige "de" antes del año, por eso
# este patrón propio reusa solo su tabla de meses).
_FECHA_SIREL = re.compile(
    r"(\d{1,2})\s+(" + "|".join(_MESES) + r")\s+(?:de\s+)?(\d{4})", re.IGNORECASE
)


def _fecha_sirel(texto: str) -> Optional[datetime.date]:
    m = _FECHA_SIREL.search(texto or "")
    if not m:
        return None
    try:
        return datetime.date(int(m.group(3)), _MESES[m.group(2).lower()], int(m.group(1)))
    except ValueError:
        return None


def _anio_plausible(a: int) -> bool:
    return 1990 <= a <= datetime.date.today().year + 1


def _normalizar_numero_concepto(numero: str) -> str:
    s = unicodedata.normalize("NFC", numero or "").upper()
    s = re.sub(r"\bCONCEPTO\b", " ", s)
    s = re.sub(r"\bN[Oº°]?\s*\.", " ", s)   # "N.", "NO.", "Nº."
    s = re.sub(r"\bN[Oº°](?=\s|\d|$)", " ", s)  # "NO", "Nº", "N°" followed by space/digit/end
    s = re.sub(r"[^A-Z0-9/\- ]", " ", s)    # codificación rota, comillas, puntos
    s = re.sub(r"\s*([/-])\s*", r"\1", s)
    return " ".join(s.split()).strip("-/ ")


_NUM_ANIO_FINAL = re.compile(r"^(?:[A-Z]{1,2}-?)?(\d+)\s*(?:[/-]|DE\b)\s*(\d{4})$")
_NUM_ANIO_INICIAL = re.compile(r"^(?:[A-Z]{1,2}-?)?(\d{4})[/-](\d+)$")
_NUM_ANIO_CORTO = re.compile(r"^(\d{2})[/-](\d+)$")
_NUM_SOLO = re.compile(r"^(?:[A-Z]{1,2}-?)?(\d+)$")


def _numero_concepto(numero: str, anio_fecha: int) -> Optional[Tuple[int, int, bool]]:
    """(consecutivo, año, aviso) según las reglas del diseño; None si el número
    no trae ningún dígito. `aviso` = True cuando se cayó a la regla 5 (se tomó
    el primer grupo de dígitos a ciegas)."""
    s = _normalizar_numero_concepto(numero)
    m = _NUM_ANIO_FINAL.match(s)
    if m and _anio_plausible(int(m.group(2))):
        return int(m.group(1)), int(m.group(2)), False
    m = _NUM_ANIO_INICIAL.match(s)
    if m and _anio_plausible(int(m.group(1))):
        return int(m.group(2)), int(m.group(1)), False
    m = _NUM_ANIO_CORTO.match(s)
    if m and m.group(1) == f"{anio_fecha % 100:02d}":
        return int(m.group(2)), anio_fecha, False
    m = _NUM_SOLO.match(s)
    if m:
        return int(m.group(1)), anio_fecha, False
    m = re.search(r"\d+", s)
    if m:
        return int(m.group(0)), anio_fecha, True
    return None


def _titulo_concepto(numero: str, fecha: datetime.date, doc_id: str) -> Tuple[str, bool]:
    r = _numero_concepto(numero, fecha.year)
    if r is None:
        return f"CTO_PGN_SN{doc_id}_{fecha.year}", False
    consecutivo, anio, aviso = r
    return f"CTO_PGN_{consecutivo:07d}_{anio}", aviso


def _con_sufijos(pares: List[Tuple[str, int]]) -> List[str]:
    """Distingue títulos repetidos (cada dependencia de la PGN numera por su
    cuenta): dentro de cada grupo de títulos iguales, el de menor id interno
    del sitio queda limpio y los siguientes llevan _2, _3… Se llama siempre
    con el AÑO COMPLETO consultado, para que el título de un documento no
    dependa del rango de fechas de la corrida."""
    por_titulo: Dict[str, List[int]] = {}
    for i, (titulo, _) in enumerate(pares):
        por_titulo.setdefault(titulo, []).append(i)
    salida = [titulo for titulo, _ in pares]
    for titulo, indices in por_titulo.items():
        if len(indices) < 2:
            continue
        orden = sorted(indices, key=lambda i: (pares[i][1], i))
        for k, i in enumerate(orden[1:], start=2):
            salida[i] = f"{titulo}_{k}"
    return salida


# ---- lectura de tabla HTML y consulta paginada ----
_PIE_RE = re.compile(r"Resultados\s+\d+\s*-\s*\d+\s+de\s+(\d+)")


def _pie(html: str) -> Optional[int]:
    m = _PIE_RE.search(html or "")
    return int(m.group(1)) if m else None


def _filas(html: str) -> List[Tuple[List[str], Optional[str]]]:
    soup = BeautifulSoup(html or "", "html.parser")
    tabla = soup.find("table", class_="cms-table")
    if tabla is None:
        return []
    out = []
    for tr in tabla.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:  # fila de encabezado (<th>)
            continue
        a = tr.find("a", href=True)
        out.append(([td.get_text(" ", strip=True) for td in tds], a["href"].strip() if a else None))
    return out


class _PaginaInesperada(RuntimeError):
    pass


def _consultar(session: requests.Session, params: dict) -> List[Tuple[List[str], Optional[str]]]:
    filas: List[Tuple[List[str], Optional[str]]] = []
    primero = 0
    while True:
        resp = session.get(
            _RELATORIA,
            params={**params, "max_results": _PAGINA, "first_result": primero},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        total = _pie(resp.text)
        if total is None:
            raise _PaginaInesperada(
                "la respuesta no trae el pie 'Resultados … de N' "
                "(¿bloqueo, reCAPTCHA exigido o cambio del sitio?)"
            )
        pagina = _filas(resp.text)
        filas.extend(pagina)
        primero += _PAGINA
        if not pagina or len(filas) >= total or primero >= total:
            break
    if len(filas) != total:
        raise _PaginaInesperada(f"se leyeron {len(filas)} filas de {total}")
    return filas


# ---- sección Normativa: de filas a documentos ----
def _avisar(on_progress, mensaje: str) -> None:
    if on_progress:
        on_progress(f"[{_SOURCE}] {mensaje}")


def _params_normativa(anio: int) -> dict:
    return {
        "option": _OPT_NORMATIVA,
        "action": "consultar_normatividad",
        "anio": str(anio),
        "tematica": "",
        "numero": "",
        "tipo": "",
        "descripcion_corta": "",
        "descripcion_larga": "",
        "fecha_documento": "",
    }


def _armar(titulo: str, tipo: str, seccion: str, fecha: datetime.date, url: str, detalle: Optional[str]) -> RawDocModel:
    iso = fecha.isoformat()
    return RawDocModel(
        source=_SOURCE,
        link={"url": url, "method": "GET"},
        title=titulo,
        tipo=tipo,
        f_public=iso,
        f_providencia=iso,
        seccion=seccion,
        detalle=detalle or None,
        save_path=storage_path(_SOURCE, iso, tipo, f"{_safe_title(titulo)}(extension)"),
    )


def _docs_normativa(filas, anio_consulta: int, desde: str, hasta: str, on_progress) -> List[RawDocModel]:
    # 1) solo documentos propios (verDocumentoRel), deduplicados por relId,
    #    prefiriendo la fila que sí trae fecha
    por_relid: Dict[str, dict] = {}
    for celdas, href in filas:
        if len(celdas) < 7:
            continue
        relid = _relid(href)
        if relid is None:  # sin enlace, o norma de otra entidad (Senado, Presidencia…)
            continue
        anio_col, tipo, numero, tematica, corta, larga, fecha_txt = celdas[:7]
        fila = {
            "anio_col": anio_col, "tipo": tipo, "numero": numero, "tematica": tematica,
            "corta": corta, "larga": larga, "fecha": _fecha_iso(fecha_txt),
        }
        previa = por_relid.get(relid)
        if previa is None or (previa["fecha"] is None and fila["fecha"] is not None):
            por_relid[relid] = fila

    # 2) fecha (o 1 de enero del año del listado) y título base
    base = []
    for relid, f in por_relid.items():
        fecha = f["fecha"]
        if fecha is None:
            anio = int(f["anio_col"]) if f["anio_col"].isdigit() else anio_consulta
            fecha = datetime.date(anio, 1, 1)
            _avisar(on_progress, f"Aviso: {f['tipo']} {f['numero']} sin fecha en Normativa, se usa {fecha.isoformat()}")
        titulo, desconocido = _titulo_normativa(f["tipo"], f["numero"], fecha.year, _id_de_relid(relid))
        if desconocido:
            _avisar(on_progress, f"Aviso: tipo desconocido «{f['tipo']}» en Normativa, se guarda como {titulo}")
        base.append((relid, f, fecha, titulo))

    # 3) sufijos sobre el año completo, y recién después el filtro por rango
    titulos = _con_sufijos([(titulo, _id_de_relid(relid)) for relid, _, _, titulo in base])
    docs = []
    for (relid, f, fecha, _), titulo in zip(base, titulos):
        iso = fecha.isoformat()
        if iso < desde or iso > hasta:
            continue
        detalle = " — ".join(x for x in (f["corta"], f["larga"]) if x)
        if f["tematica"]:
            detalle = f"{detalle} ({f['tematica']})" if detalle else f["tematica"]
        docs.append(_armar(titulo, f["tipo"], "Normativa", fecha, _url_normativa(relid), detalle))
    return docs


# ---- sección Conceptos: de filas a documentos ----
_DOCID_RE = re.compile(r"[?&]docId=(\d+)")


def _params_conceptos(tipo: str, desde: str, hasta: str) -> dict:
    return {
        "option": _OPT_SIREL,
        "action": "consultar_area",
        "tipo_documento": tipo,
        "numero": "",
        "dependencia": "",
        "palabra_clave": "",
        "fecha_inicial": desde,
        "fecha_final": hasta,
    }


def _docs_conceptos(filas, anio_consulta: int, desde: str, hasta: str, on_progress) -> List[RawDocModel]:
    # SIREL repite cada concepto una vez por tema/subtema: se agrupa por docId
    grupos: Dict[str, dict] = {}
    for celdas, href in filas:
        if len(celdas) < 7 or not href:
            continue
        m = _DOCID_RE.search(href)
        if not m:
            continue
        doc_id = m.group(1)
        _tipo, numero, dependencia, tema, subtema, _doc, fecha_txt = celdas[:7]
        g = grupos.get(doc_id)
        if g is None:
            g = grupos[doc_id] = {
                "numero": numero, "dependencia": dependencia, "fecha_txt": fecha_txt,
                "url": href.split("#", 1)[0].strip(), "temas": [],
            }
        par = f"{tema}: {subtema}" if tema and subtema else (tema or subtema)
        if par and par not in g["temas"]:
            g["temas"].append(par)

    base = []
    for doc_id, g in grupos.items():
        fecha = _fecha_sirel(g["fecha_txt"])
        if fecha is None:
            fecha = datetime.date(anio_consulta, 1, 1)
            _avisar(on_progress, f"Aviso: concepto {g['numero'] or doc_id} con fecha ilegible «{g['fecha_txt']}», se usa {fecha.isoformat()}")
        titulo, aviso = _titulo_concepto(g["numero"], fecha, doc_id)
        if aviso:
            _avisar(on_progress, f"Aviso: número de concepto poco claro «{g['numero']}», se nombra {titulo}")
        base.append((doc_id, g, fecha, titulo))

    titulos = _con_sufijos([(titulo, int(doc_id)) for doc_id, _, _, titulo in base])
    docs = []
    for (doc_id, g, fecha, _), titulo in zip(base, titulos):
        iso = fecha.isoformat()
        if iso < desde or iso > hasta:
            continue
        detalle = "; ".join(x for x in [g["dependencia"], *g["temas"]] if x)
        docs.append(_armar(titulo, "Concepto", "Conceptos", fecha, g["url"], detalle))
    return docs
