# Fuente Supersociedades — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nueva familia de scraper `supersociedades` que trae el Boletín Jurídico (mensual) y el Boletín Contable (semestral) de la Superintendencia de Sociedades, cada boletín como un documento (su PDF compilado).

**Architecture:** `requests` + BeautifulSoup, sin navegador, mismo patrón que las demás familias. El portal Liferay renderiza toda la lista de boletines en el HTML estático (portlet Asset Publisher; sin paginación). Por cada sección: GET la página de la sección → parsear cada `journal-content-article` (título + URL del artículo) → derivar mes/semestre+año del título → filtrar por rango de fechas ANTES de abrir el artículo → GET el artículo → extraer el enlace `/documents/.../*.pdf` → un `RawDocModel` por boletín.

**Tech Stack:** Python 3.14, `requests`, `beautifulsoup4` (`bs4`), `pytest`, `responses` (HTTP simulado en tests).

**Spec:** `docs/superpowers/specs/2026-09-08-fuente-supersociedades-design.md`

## Global Constraints

- Entidad / source name exacto: `"Superintendencia de Sociedades"`. Sigla en títulos: `SS`.
- `_BASE = "https://www.supersociedades.gov.co"`. **TLS válido**: NUNCA usar `verify=False` ni `link["verify"]`.
- Nomenclatura verificada: `BOL_SS_{MES}_{año}` (jurídico; `MES ∈ {ENE,FEB,MAR,ABR,MAY,JUN,JUL,AGO,SEP,OCT,NOV,DIC}`) y `BOL_SS_{SEM}_{año}` (contable; `SEM ∈ {SI,SII}`).
- Fallback sin `{MES|SEM}` o sin año: `title_unverified=True`, `title` = título crudo `[:120].strip(" .")` (o `"documento"` si vacío). El ítem se ingiere solo si se pudo resolver una fecha; si no, se omite con aviso por `on_progress`.
- `f_public` = `f_providencia`: jurídico → `{año}-{mm}-01`; contable `SI` → `{año}-06-30`, `SII` → `{año}-12-31`.
- Cobertura: **todo lo disponible**, sin piso de año.
- `filters_by_publication_date = True`.
- `scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]`. Respetar `stop_event` (chequear y devolver `docs[:limit]`) y `limit` (cortar al alcanzarlo).
- Gate de pruebas por tarea: `pytest tests/families/test_supersociedades.py -q` (suite enfocada). NO correr la suite completa.
- Todos los tests con `responses` — cero red real.

---

## File Structure

- **Create** `core/scrapers/families/supersociedades.py` — toda la familia (constantes, helpers de parseo, parsers de HTML, clase `ScrapSupersociedades`). Un archivo, ~230 líneas, mismo tamaño/estilo que `ssf.py` y `supersalud.py`.
- **Create** `tests/families/test_supersociedades.py` — pruebas unitarias de helpers + parsers + `scrap()` con `responses`.
- **Modify** `core/scrapers/families/__init__.py` — agregar `supersociedades` a la línea de import `# noqa: F401`.
- **Modify** `core/seed.py` — entrada en `_FAMILIES` + `create_source_if_missing`.
- **Modify** `tests/test_seed.py` — subir 3 aserciones fijas.
- **Modify** `docs/guia-despliegue-sistemas.md` — sección nueva.

---

### Task 1: Constantes y helpers de parseo de periodo/título

**Files:**
- Create: `core/scrapers/families/supersociedades.py`
- Test: `tests/families/test_supersociedades.py`

**Interfaces:**
- Consumes: nada (primera tarea).
- Produces:
  - `_BASE: str = "https://www.supersociedades.gov.co"`
  - `_SOURCE: str = "Superintendencia de Sociedades"`
  - `_UA: str` (user-agent de navegador)
  - `_MESES: dict[str, str]` — nombre de mes ES en minúsculas sin acento → sigla de 3 letras (`"enero"→"ENE"`, …, `"diciembre"→"DIC"`).
  - `_sin_acentos(s: str) -> str`
  - `_safe_title(title: str) -> str`
  - `_mes_a_sigla(texto: str) -> Optional[str]` — primer nombre de mes ES que aparezca en `texto` → su sigla; `None` si ninguno.
  - `_anio(texto: str) -> Optional[int]` — primer entero de 4 dígitos entre 2000 y 2100 en `texto`; `None` si ninguno.
  - `_periodo_juridico(titulo: str) -> Optional[Tuple[str, int]]` — `("AGO", 2026)`; `None` si falta mes o año.
  - `_periodo_contable(titulo: str) -> Optional[Tuple[str, int]]` — `("SI"|"SII", 2026)`; `None` si falta semestre/mes o año.
  - `_fecha_de_periodo(tipo: str, periodo: Tuple[str, int]) -> Optional[str]` — ISO `YYYY-MM-DD`; `None` si `periodo` no es reconocible para ese `tipo`.
  - `_titulo(tipo: str, periodo: Optional[Tuple[str, int]], titulo_crudo: str) -> Tuple[str, bool]` — `(title, unverified)`.

- [ ] **Step 1: Escribir las pruebas y verificarlas en rojo**

Crear `tests/families/test_supersociedades.py`:

```python
from core.scrapers.families.supersociedades import (
    _anio,
    _fecha_de_periodo,
    _mes_a_sigla,
    _periodo_contable,
    _periodo_juridico,
    _safe_title,
    _titulo,
)


def test_mes_a_sigla_todos_los_meses():
    pares = {
        "enero": "ENE", "Febrero": "FEB", "MARZO": "MAR", "abril": "ABR",
        "mayo": "MAY", "junio": "JUN", "julio": "JUL", "Agosto": "AGO",
        "septiembre": "SEP", "Octubre": "OCT", "noviembre": "NOV", "DICIEMBRE": "DIC",
    }
    for nombre, sigla in pares.items():
        assert _mes_a_sigla(f"Boletín Jurídico {nombre} 2026") == sigla


def test_mes_a_sigla_none_sin_mes():
    assert _mes_a_sigla("Boletín Informativo Contable 2017") is None
    assert _mes_a_sigla("") is None


def test_anio_primero_valido():
    assert _anio("BOLETÍN CONCEPTOS JURÍDICOS JULIO 2026") == 2026
    assert _anio("Boletín Contable 2021 - Semestre II") == 2021
    assert _anio("sin año") is None
    assert _anio("año 1999") is None


def test_periodo_juridico_ambos_formatos_de_titulo():
    assert _periodo_juridico("Boletín Jurídico Agosto 2026") == ("AGO", 2026)
    assert _periodo_juridico("BOLETÍN CONCEPTOS JURÍDICOS JULIO 2026") == ("JUL", 2026)


def test_periodo_juridico_none_si_falta_mes_o_anio():
    assert _periodo_juridico("Boletín Jurídico 2026") is None
    assert _periodo_juridico("Boletín Jurídico Agosto") is None


def test_periodo_contable_semestre_romano_y_arabigo():
    assert _periodo_contable("Boletín Informativo Contable 2026 - Semestre I") == ("SI", 2026)
    assert _periodo_contable("Boletín Informativo Contable 2025 - Semestre II") == ("SII", 2025)
    assert _periodo_contable("Boletín Contable 2022 - Semestre 2") == ("SII", 2022)
    assert _periodo_contable("Boletín Contable 2023 - Semestre 1") == ("SI", 2023)


def test_periodo_contable_por_mes_cuando_no_dice_semestre():
    assert _periodo_contable("Boletin Contable Diciembre 2023") == ("SII", 2023)
    assert _periodo_contable("Boletin Contable Marzo 2019") == ("SI", 2019)


def test_periodo_contable_none_sin_semestre_ni_mes():
    assert _periodo_contable("Boletín Informativo Contable 2017") is None


def test_fecha_de_periodo():
    assert _fecha_de_periodo("Boletín Jurídico", ("AGO", 2026)) == "2026-08-01"
    assert _fecha_de_periodo("Boletín Jurídico", ("ENE", 2020)) == "2020-01-01"
    assert _fecha_de_periodo("Boletín Contable", ("SI", 2026)) == "2026-06-30"
    assert _fecha_de_periodo("Boletín Contable", ("SII", 2025)) == "2025-12-31"


def test_titulo_verificado_y_fallback():
    assert _titulo("Boletín Jurídico", ("AGO", 2026), "irrelevante") == ("BOL_SS_AGO_2026", False)
    assert _titulo("Boletín Contable", ("SI", 2026), "irrelevante") == ("BOL_SS_SI_2026", False)
    t, unv = _titulo("Boletín Contable", None, "Boletín Informativo Contable 2017")
    assert unv is True and t == "Boletín Informativo Contable 2017"
    assert _titulo("Boletín Jurídico", None, "   ") == ("documento", True)


def test_safe_title_sanea_y_recorta():
    assert _safe_title('a/b:c"  .') == "a-b-c-"
    assert len(_safe_title("z" * 200)) == 120
```

Correr: `pytest tests/families/test_supersociedades.py -q`
Esperado: FAIL en la recolección — `ModuleNotFoundError: No module named 'core.scrapers.families.supersociedades'`.

- [ ] **Step 2: Escribir el archivo con imports, constantes y helpers**

Crear `core/scrapers/families/supersociedades.py`:

```python
import re
import unicodedata
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE = "https://www.supersociedades.gov.co"
_SOURCE = "Superintendencia de Sociedades"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

_MESES = {
    "enero": "ENE", "febrero": "FEB", "marzo": "MAR", "abril": "ABR",
    "mayo": "MAY", "junio": "JUN", "julio": "JUL", "agosto": "AGO",
    "septiembre": "SEP", "setiembre": "SEP", "octubre": "OCT",
    "noviembre": "NOV", "diciembre": "DIC",
}
# sigla -> número de mes (para clasificar semestre y para la fecha del jurídico)
_MES_NUM = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_ANIO_RE = re.compile(r"\b(20\d{2})\b")
# "semestre i" | "semestre ii" | "semestre 1" | "semestre 2" (tras normalizar)
_SEMESTRE_RE = re.compile(r"semestre\s+(ii|i|2|1)\b")


def _sin_acentos(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)
    )


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _mes_a_sigla(texto: str) -> Optional[str]:
    t = _sin_acentos(texto or "").lower()
    # el primero que aparezca por posición en el texto
    encontrados = [(t.find(nombre), sigla) for nombre, sigla in _MESES.items() if nombre in t]
    if not encontrados:
        return None
    return min(encontrados)[1]


def _anio(texto: str) -> Optional[int]:
    m = _ANIO_RE.search(texto or "")
    if not m:
        return None
    n = int(m.group(1))
    return n if 2000 <= n <= 2100 else None


def _periodo_juridico(titulo: str) -> Optional[Tuple[str, int]]:
    mes = _mes_a_sigla(titulo)
    anio = _anio(titulo)
    if mes is None or anio is None:
        return None
    return mes, anio


def _periodo_contable(titulo: str) -> Optional[Tuple[str, int]]:
    anio = _anio(titulo)
    if anio is None:
        return None
    t = _sin_acentos(titulo or "").lower()
    m = _SEMESTRE_RE.search(t)
    if m:
        sem = "SII" if m.group(1) in ("ii", "2") else "SI"
        return sem, anio
    mes = _mes_a_sigla(titulo)
    if mes is not None:
        return ("SI" if _MES_NUM[mes] <= 6 else "SII"), anio
    return None


def _fecha_de_periodo(tipo: str, periodo: Tuple[str, int]) -> Optional[str]:
    clave, anio = periodo
    if tipo == "Boletín Jurídico":
        num = _MES_NUM.get(clave)
        return f"{anio:04d}-{num:02d}-01" if num else None
    if tipo == "Boletín Contable":
        if clave == "SI":
            return f"{anio:04d}-06-30"
        if clave == "SII":
            return f"{anio:04d}-12-31"
    return None


def _titulo(tipo: str, periodo: Optional[Tuple[str, int]], titulo_crudo: str) -> Tuple[str, bool]:
    if periodo is not None:
        clave, anio = periodo
        return f"BOL_SS_{clave}_{anio}", False
    return ((titulo_crudo or "").strip() or "documento")[:120].strip(" ."), True
```

- [ ] **Step 3: Correr las pruebas en verde**

`pytest tests/families/test_supersociedades.py -q`
Esperado: PASS (11 tests).

- [ ] **Step 4: Commit**

```bash
git add core/scrapers/families/supersociedades.py tests/families/test_supersociedades.py
git commit -m "feat(supersociedades): helpers de parseo de periodo y título"
```

---

### Task 2: Parsers de HTML (lista de boletines y PDF del artículo)

**Files:**
- Modify: `core/scrapers/families/supersociedades.py`
- Test: `tests/families/test_supersociedades.py`

**Interfaces:**
- Consumes: `_BASE` (Task 1).
- Produces:
  - `_items_de_lista(html: str, link_class: str) -> List[Tuple[str, str]]` — por cada `<a class="{link_class}" ...>` de la página de sección, devuelve `(titulo, url_articulo)` donde `titulo` es el atributo `title=` y `url_articulo` es el `href` tal cual (ya viene absoluto). Lista vacía si no hay ninguno.
  - `_pdf_del_articulo(html: str) -> Optional[str]` — primer `href` que matchee `/documents/\d+/\d+/[^"]*bolet[ií]n[^"]*\.pdf` (case-insensitive, sobre el texto sin acentos del href); `None` si no hay. Debe ignorar el `Decreto-Unico-Reglamentario-Sectorial-1074-de-2015.pdf` del pie de página.

- [ ] **Step 1: Escribir las pruebas y verificarlas en rojo**

Añadir a `tests/families/test_supersociedades.py`:

```python
from core.scrapers.families.supersociedades import _items_de_lista, _pdf_del_articulo

_LISTA_JURIDICO = """
<div class="journal-content-article" data-analytics-asset-title="Boletín Jurídico Agosto 2026">
  <a class="tituloBolConJuriHistorico" id="bolConJuriTitulo" alt="Boletín Jurídico Agosto 2026"
     title="Boletín Jurídico Agosto 2026"
     href="https://www.supersociedades.gov.co:443/boletines-conceptos-juridicos/-/asset_publisher/atwl/content/boletin-juridico-agosto-2026?_x=10183496">t</a>
</div>
<div class="journal-content-article" data-analytics-asset-title="BOLETÍN CONCEPTOS JURÍDICOS JULIO 2026">
  <a class="tituloBolConJuriHistorico" title="BOLETÍN CONCEPTOS JURÍDICOS JULIO 2026"
     href="https://www.supersociedades.gov.co:443/boletines-conceptos-juridicos/-/asset_publisher/atwl/content/boletin-julio-2026?_x=1">t</a>
</div>
<div class="journal-content-article" data-analytics-asset-title="WC-Footer">
  <a class="otra-clase" title="pie" href="/algo">x</a>
</div>
"""

_LISTA_CONTABLE = """
<div class="journal-content-article">
  <a class="tituloBol_ConContHistorico" title="Boletín Informativo Contable 2026 - Semestre I"
     href="https://www.supersociedades.gov.co:443/boletines-de-conceptos-contables/-/asset_publisher/atwl/content/contable-2026-si?_x=2">t</a>
</div>
"""

_ARTICULO_CON_PDF = """
<div class="journal-content-article" data-analytics-asset-title="Boletín Jurídico Agosto 2026">
  <p>Consulte los conceptos ...</p>
  <a class="boton-super" title="Continuar"
     href="/documents/20122/9476810/Boletin_agosto_2026.pdf/63d7754c-633b-2bdd-0ea6-1884bac487d7?t=1787932667029">
     PDF Boletín Jurídico </a>
</div>
<footer>
  <a href="/documents/107391/897146/Decreto-Unico-Reglamentario-Sectorial-1074-de-2015.pdf">decreto</a>
</footer>
"""

_ARTICULO_SIN_PDF = """
<div class="journal-content-article"><p>Texto sin adjunto.</p></div>
<footer><a href="/documents/107391/897146/Decreto-Unico-Reglamentario-Sectorial-1074-de-2015.pdf">d</a></footer>
"""


def test_items_de_lista_juridico_toma_title_y_href_ignora_footer():
    items = _items_de_lista(_LISTA_JURIDICO, "tituloBolConJuriHistorico")
    assert items == [
        ("Boletín Jurídico Agosto 2026",
         "https://www.supersociedades.gov.co:443/boletines-conceptos-juridicos/-/asset_publisher/atwl/content/boletin-juridico-agosto-2026?_x=10183496"),
        ("BOLETÍN CONCEPTOS JURÍDICOS JULIO 2026",
         "https://www.supersociedades.gov.co:443/boletines-conceptos-juridicos/-/asset_publisher/atwl/content/boletin-julio-2026?_x=1"),
    ]


def test_items_de_lista_contable():
    items = _items_de_lista(_LISTA_CONTABLE, "tituloBol_ConContHistorico")
    assert items == [
        ("Boletín Informativo Contable 2026 - Semestre I",
         "https://www.supersociedades.gov.co:443/boletines-de-conceptos-contables/-/asset_publisher/atwl/content/contable-2026-si?_x=2"),
    ]


def test_items_de_lista_vacia_si_cambia_la_clase():
    assert _items_de_lista(_LISTA_JURIDICO, "clase-que-no-existe") == []


def test_pdf_del_articulo_toma_el_boletin_no_el_decreto():
    assert _pdf_del_articulo(_ARTICULO_CON_PDF) == (
        "/documents/20122/9476810/Boletin_agosto_2026.pdf/63d7754c-633b-2bdd-0ea6-1884bac487d7?t=1787932667029"
    )


def test_pdf_del_articulo_none_si_no_hay():
    assert _pdf_del_articulo(_ARTICULO_SIN_PDF) is None
```

Correr: `pytest tests/families/test_supersociedades.py -q -k "items_de_lista or pdf_del_articulo"`
Esperado: FAIL (`cannot import name '_items_de_lista'`).

- [ ] **Step 2: Implementar los parsers**

Añadir a `core/scrapers/families/supersociedades.py` (después de `_titulo`):

```python
_PDF_RE = re.compile(r"/documents/\d+/\d+/[^\"']*bolet[ií]n[^\"']*\.pdf[^\"']*", re.IGNORECASE)


def _items_de_lista(html: str, link_class: str) -> List[Tuple[str, str]]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: List[Tuple[str, str]] = []
    for a in soup.find_all("a", class_=link_class, href=True):
        titulo = (a.get("title") or a.get_text(" ", strip=True) or "").strip()
        href = a["href"].strip()
        if titulo and href:
            out.append((titulo, href))
    return out


def _pdf_del_articulo(html: str) -> Optional[str]:
    for a in BeautifulSoup(html or "", "html.parser").find_all("a", href=True):
        href = a["href"].strip()
        if _PDF_RE.search(_sin_acentos(href)):
            return href
    return None
```

Nota: `_PDF_RE` se aplica sobre `_sin_acentos(href)` para que `bolet[ií]n` cubra tanto `Boletin_...` como un eventual `Boletín_...`; el `[ií]` es redundante tras `_sin_acentos` pero no molesta.

- [ ] **Step 3: Correr las pruebas en verde**

`pytest tests/families/test_supersociedades.py -q`
Esperado: PASS (16 tests).

- [ ] **Step 4: Commit**

```bash
git add core/scrapers/families/supersociedades.py tests/families/test_supersociedades.py
git commit -m "feat(supersociedades): parsers de lista de boletines y PDF del artículo"
```

---

### Task 3: Orquestación `scrap()` y registro de la familia

**Files:**
- Modify: `core/scrapers/families/supersociedades.py`
- Modify: `core/scrapers/families/__init__.py`
- Test: `tests/families/test_supersociedades.py`

**Interfaces:**
- Consumes: todo lo de Task 1 y Task 2.
- Produces:
  - `_SECCIONES: list[tuple[str, str, str, callable]]` — `(url_seccion, tipo, link_class, periodo_fn)` con dos filas:
    - `(f"{_BASE}/boletines-conceptos-juridicos", "Boletín Jurídico", "tituloBolConJuriHistorico", _periodo_juridico)`
    - `(f"{_BASE}/boletines-de-conceptos-contables", "Boletín Contable", "tituloBol_ConContHistorico", _periodo_contable)`
  - `@register_family("supersociedades")` → `class ScrapSupersociedades(BaseScrapper)` con `filters_by_publication_date = True`, `__init__` que fija `self.source = _SOURCE`, y `scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]`.

- [ ] **Step 1: Escribir las pruebas y verificarlas en rojo**

Añadir a `tests/families/test_supersociedades.py`:

```python
import threading

import responses

from core.scrapers.registry import FAMILY_REGISTRY
from core.scrapers.families.supersociedades import ScrapSupersociedades

_JURI_URL = "https://www.supersociedades.gov.co/boletines-conceptos-juridicos"
_CONT_URL = "https://www.supersociedades.gov.co/boletines-de-conceptos-contables"


def _lista(seccion_slug, link_class, items):
    # items: [(title, article_url)]
    filas = "".join(
        f'<div class="journal-content-article" data-analytics-asset-title="{t}">'
        f'<a class="{link_class}" title="{t}" href="{u}">x</a></div>'
        for t, u in items
    )
    return f"<html><body>{filas}</body></html>"


def _articulo(pdf_href):
    return (
        f'<html><body><div class="journal-content-article">'
        f'<a class="boton-super" href="{pdf_href}">PDF</a></div>'
        f'<footer><a href="/documents/107391/897146/Decreto-Unico-Reglamentario-Sectorial-1074-de-2015.pdf">d</a></footer>'
        f'</body></html>'
    )


def test_supersociedades_registrada():
    import core.scrapers.families  # noqa: F401
    assert FAMILY_REGISTRY["supersociedades"].__name__ == "ScrapSupersociedades"


def test_filters_by_publication_date_activo():
    assert ScrapSupersociedades.filters_by_publication_date is True


@responses.activate
def test_scrap_arma_un_doc_por_boletin_en_ambas_secciones():
    art_juri = _JURI_URL + "/-/asset_publisher/atwl/content/juri-ago-2026"
    art_cont = _CONT_URL + "/-/asset_publisher/atwl/content/cont-2026-si"
    responses.add(responses.GET, _JURI_URL,
                  body=_lista("j", "tituloBolConJuriHistorico", [("Boletín Jurídico Agosto 2026", art_juri)]))
    responses.add(responses.GET, art_juri,
                  body=_articulo("/documents/20122/9476810/Boletin_agosto_2026.pdf/uuid?t=1"))
    responses.add(responses.GET, _CONT_URL,
                  body=_lista("c", "tituloBol_ConContHistorico", [("Boletín Informativo Contable 2026 - Semestre I", art_cont)]))
    responses.add(responses.GET, art_cont,
                  body=_articulo("/documents/20122/460462/Boletin-Contable-2026-Semestre-1.pdf/uuid?t=2"))

    docs = ScrapSupersociedades().scrap(fini="2026-01-01", ffin="2026-12-31")
    porss = {d.title: d for d in docs}
    assert set(porss) == {"BOL_SS_AGO_2026", "BOL_SS_SI_2026"}
    j = porss["BOL_SS_AGO_2026"]
    assert j.tipo == "Boletín Jurídico"
    assert j.source == "Superintendencia de Sociedades"
    assert j.f_public == "2026-08-01" and j.f_providencia == "2026-08-01"
    assert j.link == {"url": "https://www.supersociedades.gov.co/documents/20122/9476810/Boletin_agosto_2026.pdf/uuid?t=1", "method": "GET"}
    assert "verify" not in j.link
    assert j.detalle == "Boletín Jurídico Agosto 2026"
    assert j.save_path == "Superintendencia de Sociedades/2026-08-01/Boletín Jurídico/BOL_SS_AGO_2026(extension)"
    c = porss["BOL_SS_SI_2026"]
    assert c.f_public == "2026-06-30" and c.tipo == "Boletín Contable"


@responses.activate
def test_scrap_filtra_por_rango_sin_abrir_el_articulo():
    art_in = _JURI_URL + "/-/asset_publisher/atwl/content/ago"
    art_out = _JURI_URL + "/-/asset_publisher/atwl/content/ene"
    responses.add(responses.GET, _JURI_URL, body=_lista("j", "tituloBolConJuriHistorico", [
        ("Boletín Jurídico Agosto 2026", art_in),
        ("Boletín Jurídico Enero 2026", art_out),
    ]))
    responses.add(responses.GET, art_in, body=_articulo("/documents/1/2/Boletin_agosto_2026.pdf/u?t=1"))
    responses.add(responses.GET, _CONT_URL, body=_lista("c", "tituloBol_ConContHistorico", []))

    docs = ScrapSupersociedades().scrap(fini="2026-07-01", ffin="2026-09-30")
    assert [d.title for d in docs] == ["BOL_SS_AGO_2026"]
    # el artículo de enero NUNCA se solicitó
    urls = [c.request.url for c in responses.calls]
    assert art_out not in urls


@responses.activate
def test_scrap_omite_y_avisa_si_no_hay_pdf():
    art = _JURI_URL + "/-/asset_publisher/atwl/content/ago"
    responses.add(responses.GET, _JURI_URL,
                  body=_lista("j", "tituloBolConJuriHistorico", [("Boletín Jurídico Agosto 2026", art)]))
    responses.add(responses.GET, art, body="<html><body><div class='journal-content-article'>sin pdf</div></body></html>")
    responses.add(responses.GET, _CONT_URL, body=_lista("c", "tituloBol_ConContHistorico", []))

    avisos = []
    docs = ScrapSupersociedades().scrap(fini="2026-01-01", ffin="2026-12-31", on_progress=avisos.append)
    assert docs == []
    assert any("sin PDF" in m or "sin pdf" in m.lower() for m in avisos)


@responses.activate
def test_scrap_omite_y_avisa_si_no_hay_periodo():
    art = _CONT_URL + "/-/asset_publisher/atwl/content/2017"
    responses.add(responses.GET, _JURI_URL, body=_lista("j", "tituloBolConJuriHistorico", []))
    responses.add(responses.GET, _CONT_URL,
                  body=_lista("c", "tituloBol_ConContHistorico", [("Boletín Informativo Contable 2017", art)]))

    avisos = []
    docs = ScrapSupersociedades().scrap(fini="2010-01-01", ffin="2026-12-31", on_progress=avisos.append)
    assert docs == []
    assert any("periodo" in m.lower() for m in avisos)
    # no se abrió el artículo (no hay fecha para filtrar, se descarta antes)
    assert art not in [c.request.url for c in responses.calls]


@responses.activate
def test_scrap_continua_si_una_seccion_falla():
    art = _CONT_URL + "/-/asset_publisher/atwl/content/cont"
    responses.add(responses.GET, _JURI_URL, status=500)
    responses.add(responses.GET, _CONT_URL,
                  body=_lista("c", "tituloBol_ConContHistorico", [("Boletín Informativo Contable 2026 - Semestre I", art)]))
    responses.add(responses.GET, art, body=_articulo("/documents/1/2/Boletin-Contable-2026-Semestre-1.pdf/u?t=1"))

    avisos = []
    docs = ScrapSupersociedades().scrap(fini="2026-01-01", ffin="2026-12-31", on_progress=avisos.append)
    assert [d.title for d in docs] == ["BOL_SS_SI_2026"]
    assert any("Error" in m and "Jurídico" in m for m in avisos)


@responses.activate
def test_scrap_avisa_si_la_lista_viene_vacia():
    responses.add(responses.GET, _JURI_URL, body="<html><body>sin articulos</body></html>")
    responses.add(responses.GET, _CONT_URL, body="<html><body>sin articulos</body></html>")
    avisos = []
    ScrapSupersociedades().scrap(fini="2026-01-01", ffin="2026-12-31", on_progress=avisos.append)
    assert sum(1 for m in avisos if "no se encontró ningún boletín" in m) == 2


@responses.activate
def test_scrap_respeta_stop_event():
    responses.add(responses.GET, _JURI_URL, body=_lista("j", "tituloBolConJuriHistorico", []))
    responses.add(responses.GET, _CONT_URL, body=_lista("c", "tituloBol_ConContHistorico", []))
    ev = threading.Event()
    ev.set()
    docs = ScrapSupersociedades().scrap(fini="2026-01-01", ffin="2026-12-31", stop_event=ev)
    assert docs == []
    assert len(responses.calls) == 0


@responses.activate
def test_scrap_respeta_limit():
    a1 = _JURI_URL + "/a1"
    a2 = _JURI_URL + "/a2"
    responses.add(responses.GET, _JURI_URL, body=_lista("j", "tituloBolConJuriHistorico", [
        ("Boletín Jurídico Julio 2026", a1),
        ("Boletín Jurídico Agosto 2026", a2),
    ]))
    responses.add(responses.GET, a1, body=_articulo("/documents/1/2/Boletin_julio_2026.pdf/u?t=1"))
    responses.add(responses.GET, a2, body=_articulo("/documents/1/2/Boletin_agosto_2026.pdf/u?t=2"))

    docs = ScrapSupersociedades().scrap(fini="2026-01-01", ffin="2026-12-31", limit=1)
    assert len(docs) == 1
```

Correr: `pytest tests/families/test_supersociedades.py -q -k scrap`
Esperado: FAIL (`cannot import name 'ScrapSupersociedades'`).

- [ ] **Step 2: Implementar `scrap()` y el registro**

Añadir a `core/scrapers/families/supersociedades.py`:

```python
_SECCIONES = [
    (f"{_BASE}/boletines-conceptos-juridicos", "Boletín Jurídico",
     "tituloBolConJuriHistorico", _periodo_juridico),
    (f"{_BASE}/boletines-de-conceptos-contables", "Boletín Contable",
     "tituloBol_ConContHistorico", _periodo_contable),
]


@register_family("supersociedades")
class ScrapSupersociedades(BaseScrapper):
    filters_by_publication_date = True

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": _UA})
        docs: List[RawDocModel] = []

        for url_seccion, tipo, link_class, periodo_fn in _SECCIONES:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            if on_progress:
                on_progress(f"[{_SOURCE}] Procesando {tipo}...")
            try:
                resp = session.get(url_seccion, timeout=60)
                resp.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Error consultando {tipo}: {e}")
                continue

            items = _items_de_lista(resp.text, link_class)
            if not items and on_progress:
                on_progress(
                    f"[{_SOURCE}] Aviso: no se encontró ningún boletín de {tipo} "
                    "(¿cambió el marcado de la página?)"
                )

            vistos: set = set()
            for titulo, url_articulo in items:
                if stop_event is not None and stop_event.is_set():
                    return docs[:limit]
                periodo = periodo_fn(titulo)
                fecha = _fecha_de_periodo(tipo, periodo) if periodo is not None else None
                if fecha is None:
                    if on_progress:
                        on_progress(
                            f"[{_SOURCE}] Aviso: boletín sin periodo reconocible «{titulo[:70]}», se omite"
                        )
                    continue
                if fecha < fini or fecha > ffin:
                    continue
                try:
                    art = session.get(url_articulo, timeout=60)
                    art.raise_for_status()
                except Exception as e:
                    if on_progress:
                        on_progress(f"[{_SOURCE}] Error abriendo boletín «{titulo[:70]}»: {e}")
                    continue
                pdf = _pdf_del_articulo(art.text)
                if not pdf:
                    if on_progress:
                        on_progress(
                            f"[{_SOURCE}] Aviso: boletín «{titulo[:70]}» sin PDF en el artículo, se omite"
                        )
                    continue
                url_pdf = urljoin(_BASE, pdf)
                if url_pdf in vistos:
                    continue
                vistos.add(url_pdf)
                title, unverified = _titulo(tipo, periodo, titulo)
                safe = _safe_title(title)
                docs.append(RawDocModel(
                    source=_SOURCE,
                    link={"url": url_pdf, "method": "GET"},
                    title=title,
                    tipo=tipo,
                    f_public=fecha,
                    f_providencia=fecha,
                    detalle=titulo or None,
                    save_path=storage_path(_SOURCE, fecha, tipo, f"{safe}(extension)"),
                    title_unverified=unverified,
                ))
                if len(docs) >= limit:
                    return docs[:limit]

        return docs[:limit]
```

Modificar `core/scrapers/families/__init__.py`: agregar `supersociedades` a la lista de módulos importados (misma línea `# noqa: F401` donde están `..., ssf, snr`). Buscar la línea del import y añadir `, supersociedades` antes del `  # noqa: F401`.

- [ ] **Step 3: Correr las pruebas en verde**

`pytest tests/families/test_supersociedades.py -q`
Esperado: PASS (26 tests). Correr también `pytest tests/families/test_ssf.py -q` para confirmar que tocar `families/__init__.py` no rompió otra familia.

- [ ] **Step 4: Commit**

```bash
git add core/scrapers/families/supersociedades.py core/scrapers/families/__init__.py tests/families/test_supersociedades.py
git commit -m "feat(supersociedades): orquestación scrap() de las dos secciones + registro"
```

---

### Task 4: Alta de la fuente (seed, test_seed, guía de despliegue)

**Files:**
- Modify: `core/seed.py`
- Modify: `tests/test_seed.py`
- Modify: `docs/guia-despliegue-sistemas.md`
- Test: `tests/test_seed.py`

**Interfaces:**
- Consumes: `@register_family("supersociedades")` de Task 3 (el import de `core.scrapers.families` lo puebla en `FAMILY_REGISTRY`).
- Produces: nada para tareas posteriores (última tarea).

- [ ] **Step 1: Actualizar las aserciones fijas de `tests/test_seed.py` (rojo primero)**

En `tests/test_seed.py`:

- Línea `assert len(families) == 24` → `assert len(families) == 25`.
- Las **dos** líneas `assert len(sources) == 1 + 28 + 21 + 33 + 6` → `assert len(sources) == 1 + 28 + 22 + 33 + 6`.
- En el `set` de keys (`test_seed_populates_families_and_sources_and_is_idempotent`), tras `"supersalud", "ssf", "snr",` agregar `"supersociedades",`.
- En el comentario que enumera las 21 fuentes únicas (`... superfinanciera, supersalud, ssf, snr) + 33 ...`), cambiar `snr)` por `snr, supersociedades)` y `21` por `22` si el número aparece en el comentario.

Correr: `pytest tests/test_seed.py -q`
Esperado: FAIL (las aserciones nuevas piden 25 familias / 90 fuentes pero el seed todavía crea 24 / 89).

- [ ] **Step 2: Agregar la familia y la fuente en `core/seed.py`**

En `core/seed.py`, dentro del dict `_FAMILIES`, después de la entrada `"snr"`, agregar:

```python
    "supersociedades": (
        "Superintendencia de Sociedades",
        "Boletín jurídico (mensual) y boletín contable (semestral) de "
        "recopilación de conceptos, publicados por la Superintendencia de Sociedades",
    ),
```

En `seed_source_families_and_sources`, junto a las otras `create_source_if_missing` de fuente única (cerca de la de `snr`), agregar:

```python
    repository.create_source_if_missing(
        db, family_key="supersociedades", name="Superintendencia de Sociedades", family_params={}
    )
```

- [ ] **Step 3: Correr las pruebas en verde**

`pytest tests/test_seed.py -q`
Esperado: PASS.

- [ ] **Step 4: Documentar en la guía de despliegue**

En `docs/guia-despliegue-sistemas.md`, agregar una sección nueva (mismo formato que la de `supersalud`/`snr`), en español llano:

```markdown
### Superintendencia de Sociedades (`supersociedades`)

- **Qué trae:** dos boletines de recopilación de conceptos — el **Boletín
  Jurídico** (mensual) y el **Boletín Contable** (semestral). Cada boletín
  entra como un documento: su PDF completo.
- **Desde cuándo:** todo lo disponible (el jurídico va desde ~2013, el
  contable desde 2017).
- **Cómo quedan nombrados:** `BOL_SS_AGO_2026` (jurídico: mes y año) y
  `BOL_SS_SI_2026` / `BOL_SS_SII_2026` (contable: semestre y año). Si el
  título del boletín no permite deducir el mes/semestre, entra con su título
  original y marca de "sin verificar".
- **Detalle técnico:** portal Liferay con certificado válido (no hace falta
  saltarse la validación). La lista de cada sección viene entera en la página
  (sin paginación); el enlace al PDF está dentro de cada boletín, así que la
  fuente abre cada boletín que caiga en el rango de fechas pedido.
- **Fuente nueva:** después de actualizar producción hay que correr una vez
  `docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.seed`
  para que aparezca en el listado. Es seguro repetirlo.
```

- [ ] **Step 5: Commit**

```bash
git add core/seed.py tests/test_seed.py docs/guia-despliegue-sistemas.md
git commit -m "feat(supersociedades): alta de la fuente + bump de test_seed + guía de despliegue"
```

---

## Notas de verificación final (para el revisor de rama completa)

- `pytest tests/families/test_supersociedades.py tests/test_seed.py -q` en verde.
- Smoke real opcional (fuera del gate, con red): `ScrapSupersociedades().scrap("2026-01-01", "2026-12-31")` debe traer al menos el boletín jurídico del mes en curso y el contable del semestre en curso, ambos con `link["url"]` bajo `https://www.supersociedades.gov.co/documents/...` y sin clave `verify`.
- Confirmar que ninguna ruta del código pone `verify=False` ni `link["verify"]`.
- Confirmar `_pdf_del_articulo` no captura `Decreto-Unico-Reglamentario-Sectorial-1074-de-2015.pdf`.
