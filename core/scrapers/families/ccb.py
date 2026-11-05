import datetime
import hashlib
import re
from typing import Iterator, List, Optional

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

# Biblioteca Digital de la CCB: DSpace 7.5 con API REST pública. www.ccb.org.co
# responde 403 a clientes sin navegador; este host es aparte y abierto.
_API = "https://bibliotecadigital.ccb.org.co/server/api"
_SEARCH_URL = f"{_API}/discover/search/objects"
_SOURCE = "Cámara de Comercio de Bogotá"
_SIGLA = "CCB"
_TIPO = "Laudo arbitral"
_PREF = "LA"
_ANIO_MINIMO = 2015
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_HEADERS = {"User-Agent": _UA, "Accept": "application/json", "Accept-Language": "es-CO,es;q=0.9"}

# Subcomunidad "C. Laudos Arbitrales" (colecciones de arbitraje nacional y
# social) dentro de la comunidad "Arbitraje y Conciliación".
_SCOPE_LAUDOS = "3beaa692-cecf-44c7-b0e8-d4179d228431"
_POR_PAGINA = 100
_PAGINA_TOPE = 50
_MAX_TITULO = 120

_RADICADO_RE = re.compile(r"^\s*(\d+)")
_ISSUED_RE = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?")
_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')


def _meta(item: dict, campo: str) -> str:
    valores = (item.get("metadata") or {}).get(campo) or []
    return (valores[0].get("value") or "").strip() if valores else ""


def _fecha_issued(texto: str) -> Optional[datetime.date]:
    """dc.date.issued: AAAA-MM-DD, o AAAA-MM (dos ítems) → día 01."""
    m = _ISSUED_RE.match(texto or "")
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3) or 1))
    except ValueError:
        return None


def _fecha_accessioned(texto: str) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat((texto or "")[:10])
    except ValueError:
        return None


def _radicado(*candidatos: str) -> Optional[str]:
    """Dígitos iniciales del primer candidato que los tenga: metadato radicado,
    luego dc.title ("157594: …"), luego el nombre del PDF ("151064 ….pdf").
    "137003Encargo fiduciario" → 137003; "4920/5468" → 4920."""
    for texto in candidatos:
        m = _RADICADO_RE.match(texto or "")
        if m:
            return str(int(m.group(1)))
    return None


def _titulo(radicado: str, anio: int) -> str:
    return f"{_PREF}_{_SIGLA}_{radicado}_{anio}"


def _titulo_respaldo(dc_title: str) -> str:
    limpio = _INVALID_PATH_CHARS.sub("-", re.sub(r"\s+", " ", dc_title or "")).strip()
    return limpio[:_MAX_TITULO].strip(" .") or "laudo"


def _id_item(handle: str) -> str:
    """Número del ítem en la biblioteca: último tramo del handle ("11520/29990"
    → "29990"); si no hay handle, el uuid."""
    return _INVALID_PATH_CHARS.sub("-", str(handle or "").rstrip("/").rsplit("/", 1)[-1]) or "sin-id"


def _items(session, fini: str, ffin: str, stop_event, on_progress=None) -> Iterator[dict]:
    """Ítems subidos (dc.date.accessioned) en [fini, ffin]. El rango sólo
    funciona sobre el campo Solr con sufijo _dt; sin él se ignora.

    Si se llega a _PAGINA_TOPE y quedan páginas, lo reporta como error de la
    corrida (el mensaje lleva "Error"): el orden es por fecha de subida
    descendente, así que lo que faltaría son los laudos subidos primero, y
    sin el aviso la corrida se vería completa (revisión del PR #110)."""
    params = {
        "scope": _SCOPE_LAUDOS,
        "dsoType": "ITEM",
        "query": f"dc.date.accessioned_dt:[{fini}T00:00:00Z TO {ffin}T23:59:59Z]",
        "sort": "dc.date.accessioned,DESC",
        "size": _POR_PAGINA,
    }
    for pagina in range(_PAGINA_TOPE):
        if stop_event is not None and stop_event.is_set():
            return
        resp = session.get(_SEARCH_URL, params={**params, "page": pagina}, timeout=60)
        resp.raise_for_status()
        resultado = resp.json().get("_embedded", {}).get("searchResult", {})
        for objeto in resultado.get("_embedded", {}).get("objects", []):
            item = objeto.get("_embedded", {}).get("indexableObject")
            if item:
                yield item
        total_paginas = (resultado.get("page") or {}).get("totalPages", 0)
        if pagina + 1 >= total_paginas:
            return
    if on_progress:
        faltan = total_paginas - _PAGINA_TOPE
        on_progress(
            f"[{_SOURCE}] Error: la búsqueda llegó al tope de {_PAGINA_TOPE} páginas y quedaron "
            f"{faltan} páginas sin revisar ({_POR_PAGINA} laudos por página). Hay que subir "
            f"_PAGINA_TOPE en core/scrapers/families/ccb.py o partir la corrida en rangos más cortos."
        )


def _pdfs(session, item_uuid: str) -> List[dict]:
    """Bitstreams del bundle ORIGINAL, en orden; TEXT, THUMBNAIL y LICENSE se
    ignoran."""
    resp = session.get(f"{_API}/core/items/{item_uuid}/bundles", params={"embed": "bitstreams"}, timeout=60)
    resp.raise_for_status()
    for bundle in resp.json().get("_embedded", {}).get("bundles", []):
        if bundle.get("name") != "ORIGINAL":
            continue
        bitstreams = bundle.get("_embedded", {}).get("bitstreams", {}).get("_embedded", {}).get("bitstreams", [])
        return sorted(bitstreams, key=lambda b: b.get("sequenceId") or 0)
    return []


@register_family("ccb")
class ScrapCcb(BaseScrapper):
    # La CCB sube los laudos con mucho retraso (p90 ~9 meses, hasta 6 años):
    # la corrida filtra por la fecha de subida a la biblioteca, no por la del
    # laudo, y así cada laudo cae en la ventana del día en que aparece.
    filters_by_publication_date = True
    # HEAD sobre /bitstreams/{uuid}/content responde JSON con Content-Length 1:
    # el chequeo de republicación por tamaño volvería a bajar todo.
    checks_for_republication = False
    # Margen por si el índice de búsqueda tarda en reflejar un ítem archivado.
    scheduled_min_lookback_days = 7
    # Sube por tandas, con meses enteros sin nada.
    alerta_margen_dias = 120

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update(_HEADERS)
        docs: List[RawDocModel] = []
        md5_vistos: set = set()
        uuid_vistos: set = set()

        def parar() -> bool:
            return stop_event is not None and stop_event.is_set()

        if on_progress:
            on_progress(f"[{_SOURCE}] Procesando {_TIPO}...")
        try:
            for item in _items(session, fini, ffin, stop_event, on_progress):
                if parar():
                    return docs[:limit]
                for doc in self._docs_de_item(session, item, md5_vistos, uuid_vistos, on_progress):
                    docs.append(doc)
                    if len(docs) >= limit:
                        return docs[:limit]
        except (requests.RequestException, ValueError) as e:
            if on_progress:
                on_progress(f"[{_SOURCE}] Error consultando {_TIPO}: {e}")

        return docs[:limit]

    def _docs_de_item(self, session, item: dict, md5_vistos: set, uuid_vistos: set, on_progress) -> List[RawDocModel]:
        handle = item.get("handle") or item.get("uuid")
        if _meta(item, "dc.type").lower() == "book":
            # La cartilla "Estructura del Laudo Arbitral", no un laudo.
            return []
        subida = _fecha_accessioned(_meta(item, "dc.date.accessioned"))
        if subida is None:
            if on_progress:
                on_progress(f"[{_SOURCE}] Aviso: ítem {handle} sin fecha de subida, se omite")
            return []
        laudo = _fecha_issued(_meta(item, "dc.date.issued"))
        if laudo is None:
            if on_progress:
                on_progress(f"[{_SOURCE}] Aviso: ítem {handle} sin fecha del laudo, se usa la de subida")
            laudo = subida
        # El piso va contra el año del laudo: en 2018 se subieron de una vez
        # los de 1985-2014. Se descarta antes de pedir los bundles.
        if laudo.year < _ANIO_MINIMO:
            return []

        try:
            pdfs = _pdfs(session, item["uuid"])
        except (requests.RequestException, ValueError, KeyError) as e:
            if on_progress:
                on_progress(f"[{_SOURCE}] Error consultando los archivos del ítem {handle}: {e}")
            return []
        if not pdfs:
            if on_progress:
                on_progress(f"[{_SOURCE}] Aviso: ítem {handle} sin PDF, se omite")
            return []

        dc_title = _meta(item, "dc.title") or item.get("name") or ""
        radicado = _radicado(_meta(item, "dc.description.radicado"), dc_title, pdfs[0].get("name") or "")
        verificado = radicado is not None
        if verificado:
            base = _titulo(radicado, laudo.year)
        else:
            # Sin radicado, el título de la biblioteca puede repetirse ("Laudo
            # arbitral"). Como el nombre del archivo sale del título (al subir y
            # en el renombrado nocturno de core/storage_sync.py), dos laudos
            # distintos con el mismo título y fecha se pisaban en el mismo
            # archivo. El número del ítem en la biblioteca (último tramo del
            # handle, p. ej. 11520/29990 → 29990) lo hace único y sirve para
            # ubicarlo en el sitio al corregirlo a mano. Hallazgo de la revisión
            # del PR #110.
            base = f"{_titulo_respaldo(dc_title)}_{_id_item(handle)}"
        iso_laudo = laudo.isoformat()
        iso_subida = subida.isoformat()

        docs: List[RawDocModel] = []
        for pdf in pdfs:
            bit_uuid = pdf.get("uuid")
            if not bit_uuid or bit_uuid in uuid_vistos:
                continue
            uuid_vistos.add(bit_uuid)
            md5 = ((pdf.get("checkSum") or {}).get("value") or "").lower()
            if md5 and md5 in md5_vistos:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Aviso: {base} ({handle}) repite un PDF ya visto, se omite")
                continue
            if md5:
                md5_vistos.add(md5)

            title = base if not docs else f"{base}_A{len(docs):02d}"
            url = f"{_API}/core/bitstreams/{bit_uuid}/content"
            if verificado:
                # Dos laudos distintos con el mismo radicado y año son
                # actuaciones del mismo título (como la SIC): el sufijo evita
                # que se pisen al subir; core/storage_sync.py pone el nombre final.
                h = hashlib.sha1(url.encode()).hexdigest()[:7]
                nombre_archivo = f"{title}_h{h}"
            else:
                nombre_archivo = title
            docs.append(RawDocModel(
                source=_SOURCE,
                link={"url": url, "method": "GET"},
                title=title,
                tipo=_TIPO,
                f_public=iso_subida,
                f_providencia=iso_laudo,
                detalle=dc_title or None,
                title_unverified=not verificado,
                save_path=storage_path(_SOURCE, iso_laudo, _TIPO, f"{nombre_archivo}(extension)"),
            ))
        return docs
