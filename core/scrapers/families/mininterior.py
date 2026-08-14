import re
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE_URL = "https://www.mininterior.gov.co"
_ARCHIVE_URL = f"{_BASE_URL}/normatividad/"

# Tipo (badge de texto tal como lo publica el sitio) -> letra del código de
# título. El sitio mezcla en un único listado cronológico normas formales
# (Decreto, Resolución...) con documentos administrativos internos (Informe,
# Manual, Memorandos, Notificación, Tutela, Meci...); a pedido explícito del
# usuario el alcance se queda acotado a lo que típicamente se entiende como
# normatividad -- cualquier tipo que no esté en este diccionario se descarta
# sin detener la paginación (ver _extraer_item).
_TIPOS_EN_ALCANCE = {
    "Decreto": "D",
    "Resolución": "R",
    "Circular": "C",
    "Circular Externa": "C",
    "Circular Interna": "C",
    "Ley": "L",
    "Ley Estatutaria": "LEST",
    "Directiva": "DIRECTIVA",
    "Acuerdo": "A",
    "Concepto": "CONCEPTO",
    "Acto Administrativo": "ACTOADM",
    "Acto Legislativo": "ACTOLEG",
}

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# Formato real y único visto en "Fecha de entrada en vigencia": "{mes en
# minúscula} {día sin cero a la izquierda}, {año}" (ej. "agosto 5, 2026").
_FECHA_PATTERN = re.compile(r"^\s*(\w+)\s+(\d{1,2}),\s*(\d{4})\s*$")

_NUMERO_PATTERN = re.compile(r"No\.?\s*(\d+)", re.IGNORECASE)
_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')


def _normalize_title(letra: str, numero: str, anio: str) -> str:
    return f"{letra}_MININT_{int(numero):04d}_{anio}"


def _parse_fecha(texto: str) -> Optional[str]:
    m = _FECHA_PATTERN.match(texto)
    if not m:
        return None
    mes_texto, dia, anio = m.groups()
    mes_num = _MESES.get(mes_texto.lower())
    if mes_num is None:
        return None
    return f"{anio}-{mes_num:02d}-{int(dia):02d}"


def _parse_numero(titulo: str) -> Optional[str]:
    m = _NUMERO_PATTERN.search(titulo)
    return m.group(1) if m else None


def _campo_con_etiqueta(p_tag) -> Optional[tuple]:
    """Un campo `p.dmach-acf-value` con una `span.dmach-acf-label` interna
    (Descripción, Fecha de entrada en vigencia) trae la etiqueta seguida del
    valor -- se devuelve (etiqueta, valor) ya separados, quitando la etiqueta
    del árbol antes de leer el texto restante (más robusto que recortar un
    prefijo de texto: el separador ": " entre etiqueta y valor no siempre
    tiene el mismo espaciado que produce get_text al unir nodos). El badge de
    tipo es el único `p.dmach-acf-value` SIN esa etiqueta interna, así que se
    distingue por su ausencia en vez de por su clase CSS."""
    label_tag = p_tag.select_one(".dmach-acf-label")
    if label_tag is None:
        return None
    etiqueta = label_tag.get_text(strip=True).rstrip(":").strip()
    label_tag.extract()
    valor = p_tag.get_text(" ", strip=True)
    return etiqueta, valor


def _extraer_item(item, on_progress=None, source: str = "") -> Optional[RawDocModel]:
    titulo_tag = item.select_one("h4.dmach-post-title")
    if titulo_tag is None:
        return None
    titulo = titulo_tag.get_text(strip=True)

    tipo = None
    descripcion = None
    fecha_texto = None
    for p_tag in item.select("p.dmach-acf-value"):
        campo = _campo_con_etiqueta(p_tag)
        if campo is None:
            tipo = p_tag.get_text(strip=True)
            continue
        etiqueta, valor = campo
        etiqueta_baja = etiqueta.lower()
        if "descripción" in etiqueta_baja:
            descripcion = valor or None
        elif "fecha de entrada en vigencia" in etiqueta_baja:
            fecha_texto = valor

    if tipo not in _TIPOS_EN_ALCANCE:
        return None
    letra = _TIPOS_EN_ALCANCE[tipo]

    if not fecha_texto:
        if on_progress:
            on_progress(f"[{source}] Aviso: no se encontró fecha de vigencia para «{titulo}», se omite")
        return None
    fecha = _parse_fecha(fecha_texto)
    if fecha is None:
        if on_progress:
            on_progress(f"[{source}] Aviso: no se pudo interpretar la fecha «{fecha_texto}» de «{titulo}», se omite")
        return None

    enlace = item.select_one("a.et_pb_button")
    if enlace is None or not enlace.get("href"):
        if on_progress:
            on_progress(f"[{source}] Aviso: no se encontró enlace de descarga para «{titulo}», se omite")
        return None
    url = urljoin(_BASE_URL, enlace["href"])

    numero = _parse_numero(titulo)
    if numero is not None:
        title = _normalize_title(letra, numero, fecha[:4])
        title_unverified = False
    else:
        title = titulo
        title_unverified = True

    safe_title = _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")

    return RawDocModel(
        source=source,
        link={"url": url, "method": "GET"},
        title=title,
        tipo=tipo,
        f_public=fecha,
        detalle=descripcion,
        save_path=storage_path(source, fecha, tipo, f"{safe_title}(extension)"),
        title_unverified=title_unverified,
    )


@register_family("mininterior")
class ScrapMininterior(BaseScrapper):
    def __init__(self):
        self.source = "Ministerio del Interior"

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        docs: List[RawDocModel] = []
        pagina = 1
        while True:
            if stop_event is not None and stop_event.is_set():
                return docs
            if on_progress:
                on_progress(f"[{self.source}] Procesando página {pagina}...")

            url = _ARCHIVE_URL if pagina == 1 else f"{_ARCHIVE_URL}page/{pagina}/"
            try:
                resp = session.get(url, timeout=30)
                resp.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{self.source}] Error consultando página {pagina}: {e}")
                return docs

            items = BeautifulSoup(resp.text, "html.parser").select("div.dmach-grid-item")
            if not items:
                return docs

            llego_al_limite_inferior = False
            for item in items:
                doc = _extraer_item(item, on_progress=on_progress, source=self.source)
                if doc is None:
                    continue
                if doc.f_public < fini:
                    # El listado va del más nuevo al más viejo: al llegar a un
                    # documento anterior a fini, todo lo que sigue (en esta
                    # página y en las siguientes) también lo es.
                    llego_al_limite_inferior = True
                    break
                if doc.f_public > ffin:
                    continue
                docs.append(doc)
                if len(docs) >= limit:
                    return docs[:limit]

            if llego_al_limite_inferior:
                return docs

            pagina += 1
