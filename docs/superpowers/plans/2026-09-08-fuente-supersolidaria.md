# Fuente Supersolidaria — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Familia de scraper nueva `supersolidaria` que trae 5 secciones de normativa (Resoluciones, Circulares externas, Circulares conjuntas, Cartas circulares, Conceptos) de la Superintendencia de la Economía Solidaria, cada adjunto como un `RawDocModel`.

**Architecture:** `requests` + BeautifulSoup, sin navegador. Sitio **Drupal 10**, TLS válido (NUNCA `verify=False`). Las 4 secciones de tabla traen toda la lista en una página HTML, con los documentos agrupados bajo encabezados `<h2>… AÑO`. Conceptos es una vista Drupal paginada (`?page=N`, 11/página). La fecha de cada documento se resuelve por una cadena de respaldo distinta por sección (prosa del título / `<time datetime>` / prefijo `AAAAMMDD` del archivo / año del `<h2>`). Anexos → documento aparte con sufijo `_A01`.

**Tech Stack:** Python 3.14, `requests`, `beautifulsoup4` (`bs4`), `core.fecha_es.parse_fecha_providencia_es`, `pytest`, `responses`.

**Spec:** `docs/superpowers/specs/2026-09-08-fuente-supersolidaria-design.md`

## Global Constraints

- Source name exacto: `"Superintendencia de la Economía Solidaria"`. Sigla en títulos: `SES`.
- `_BASE = "https://www.supersolidaria.gov.co"`. **TLS válido**: NUNCA `verify=False` ni `link["verify"]`.
- Prefijos de título por tipo: `R` (Resolución), `CE` (Circular Externa), `CJ` (Circular Conjunta), `CC` (Carta Circular), `CTO` (Concepto).
- Nomenclatura `{PREFIJO}_SES_{numero:04d}_{año}` (`+ "_A01"` si es anexo). `title_unverified=True` + título crudo `[:120].strip(" .")` (o `"documento"` si vacío) cuando no hay número.
- Resolución: `numero` = últimos 6 dígitos del radicado si el radicado tiene ≥7 dígitos; si es un entero corto, el entero tal cual.
- `f_public` = `f_providencia` = fecha resuelta (ISO `YYYY-MM-DD`). Cadena por sección (ver spec "Fecha del documento"). Año-solo → `{AAAA}-01-01`.
- Cobertura: **desde 2015**. Se descarta todo doc con fecha `< "2015-01-01"`, o fuera de `[fini, ffin]`.
- Anexo = título (sin acentos, minúsculas) empieza por `anexo` o `matriz de`. La extensión NO decide anexo. `.xlsx`/`.doc` se ingieren.
- Dedup por URL de PDF (un `set` global a la corrida). Colisión de `{PREF}_SES_{n}_{año}[_A01]` con archivo distinto → 2º se degrada a `title_unverified` + título crudo.
- `filters_by_publication_date = True`.
- `scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]`. Respetar `stop_event` (chequear y `return docs[:limit]`) y `limit`.
- Conceptos: paginar `?page=0,1,2,…` hasta una página con 0 filas; tope defensivo `page > 200`.
- Gate por tarea: `pytest tests/families/test_supersolidaria.py -q` (+ `tests/test_seed.py` en Task 4, + `tests/families/test_supersociedades.py -q` en Task 3 tras tocar `__init__.py`). NO pytest completo.
- Todas las pruebas con `responses` / fixtures — cero red real en el gate.

---

## File Structure

- **Create** `core/scrapers/families/supersolidaria.py` — toda la familia (~320 líneas; misma forma que `supersociedades.py` / `ssf.py`).
- **Create** `tests/families/test_supersolidaria.py`.
- **Modify** `core/scrapers/families/__init__.py` — la línea de import termina hoy `…, snr, supersociedades  # noqa: F401`; añadir `, supersolidaria` antes del `  # noqa`.
- **Modify** `core/seed.py` — entrada en `_FAMILIES` + `create_source_if_missing`.
- **Modify** `tests/test_seed.py` — subir 3 aserciones.
- **Modify** `docs/guia-despliegue-sistemas.md` — sección nueva.

---

### Task 1: Constantes y helpers puros

**Files:**
- Create: `core/scrapers/families/supersolidaria.py`
- Test: `tests/families/test_supersolidaria.py`

**Interfaces:**
- Consumes: nada.
- Produces (firmas exactas):
  - `_BASE: str`, `_SOURCE: str`, `_UA: str`, `_ANIO_MIN: int = 2015`
  - `_URL_CONCEPTOS: str`
  - `_SECCIONES_TABLA: list[tuple[str, str, str, bool]]` — `(url, tipo, prefijo, fecha_por_prosa)`. `fecha_por_prosa` es `True` sólo para Resoluciones.
  - `_sin_acentos(s: str) -> str`
  - `_safe_title(title: str) -> str`
  - `_extension_del_href(href: str) -> str` — extensión en minúsculas sin punto (`"pdf"`, `"xlsx"`, `""`).
  - `_es_anexo(titulo: str) -> bool`
  - `_num_seccion(prefijo: str, titulo: str) -> Optional[int]`
  - `_anio_de_h2(texto: str) -> Optional[int]`
  - `_prefijo_fecha_archivo(href: str) -> Optional[str]` — `AAAAMMDD` inicial del nombre de archivo → `YYYY-MM-DD`; `None` si no hay o es inválido.
  - `_fecha_concepto(href: str, time_iso: Optional[str]) -> Optional[str]`
  - `_titulo(prefijo: str, tipo: str, titulo_crudo: str, anio: str, es_anexo: bool) -> Tuple[str, bool]`
  - `_titulo_concepto(href: str, titulo_fila: str, anio: str) -> Tuple[str, bool]`

- [ ] **Step 1: Escribir las pruebas y verificarlas en rojo**

Crear `tests/families/test_supersolidaria.py`:

```python
from core.scrapers.families.supersolidaria import (
    _anio_de_h2,
    _es_anexo,
    _extension_del_href,
    _fecha_concepto,
    _num_seccion,
    _prefijo_fecha_archivo,
    _safe_title,
    _titulo,
    _titulo_concepto,
)


def test_extension_del_href():
    assert _extension_del_href("/sites/default/files/data/20260520_circular_externa_101.pdf") == "pdf"
    assert _extension_del_href("/x/y/2._anexo.docx?a=1") == "docx"
    assert _extension_del_href("/x/y/matriz.XLSX") == "xlsx"
    assert _extension_del_href("/es/content/algo") == ""


def test_es_anexo():
    assert _es_anexo("Anexo - Circular Externa N° 101") is True
    assert _es_anexo("ANEXO técnico") is True
    assert _es_anexo("Matriz de Comentarios - Circular N° 101") is True
    assert _es_anexo("Matriz de Observaciones") is True
    assert _es_anexo("Circular Externa N° 101") is False
    assert _es_anexo("") is False


def test_num_seccion_resolucion_radicado_largo_ultimos_6():
    assert _num_seccion("R", "Resolución 2025430007935 del 30 de diciembre de 2025") == 7935
    assert _num_seccion("R", "Resolución 2026113001925 del 26 de marzo de 2026") == 1925


def test_num_seccion_resolucion_forma_corta():
    assert _num_seccion("R", "Resolución 745 de 2003") == 745


def test_num_seccion_circulares_y_cartas():
    assert _num_seccion("CE", "Circular Externa N° 102") == 102
    assert _num_seccion("CE", "Anexo - Circular Externa N° 101") == 101
    assert _num_seccion("CC", "Carta Circular N° 37") == 37
    assert _num_seccion("CJ", "Circular conjunta No. 067") == 67


def test_num_seccion_none_cuando_no_hay():
    assert _num_seccion("CJ", "ministro_del_trabajo_y_superintendente_de_la_economia_solidaria") is None
    assert _num_seccion("CE", "Circular Externa sin numero") is None


def test_anio_de_h2():
    assert _anio_de_h2("Circulares Externas 2024") == 2024
    assert _anio_de_h2("CIRCULARES EXTERNAS 2022") == 2022
    assert _anio_de_h2("\xa0CIRCULARES EXTERNAS 2021") == 2021
    assert _anio_de_h2("Resoluciones Generales 2016") == 2016
    assert _anio_de_h2("Cartas Circulares 2015") == 2015
    assert _anio_de_h2("Resoluciones Generales") is None
    assert _anio_de_h2("Otra cosa 2020") is None


def test_prefijo_fecha_archivo():
    assert _prefijo_fecha_archivo("/sites/default/files/data/20260520_circular_externa_101.pdf") == "2026-05-20"
    assert _prefijo_fecha_archivo("/x/circular-conjunta-nov-09_0.pdf") is None
    assert _prefijo_fecha_archivo("/x/20261332_algo.pdf") is None  # mes/día inválidos


def test_fecha_concepto():
    assert _fecha_concepto("/x/20260821_concepto_20261100232001.pdf", None) == "2026-08-21"
    assert _fecha_concepto("/x/concept_uni.pdf", "2025-05-16T00:00:00Z") == "2025-05-16"
    assert _fecha_concepto("/x/concept_uni.pdf", None) is None


def test_titulo_verificado_y_anexo():
    assert _titulo("CE", "Circular Externa", "Circular Externa N° 102", "2026", False) == ("CE_SES_0102_2026", False)
    assert _titulo("CE", "Circular Externa", "Anexo - Circular Externa N° 101", "2026", True) == ("CE_SES_0101_2026_A01", False)
    assert _titulo("R", "Resolución", "Resolución 2025430007935 del 30 de diciembre de 2025", "2025", False) == ("R_SES_7935_2025", False)


def test_titulo_fallback_sin_numero():
    t, unv = _titulo("CJ", "Circular Conjunta", "ministro_del_trabajo_y_superintendente", "2009", False)
    assert unv is True and t == "ministro_del_trabajo_y_superintendente"
    assert _titulo("CE", "Circular Externa", "   ", "2020", False) == ("documento", True)


def test_titulo_concepto():
    assert _titulo_concepto("/x/20260821_concepto_20261100232001.pdf", "irrelevante", "2026") == ("CTO_SES_20261100232001_2026", False)
    t, unv = _titulo_concepto("/x/20250516_concept_uni.pdf", "Concepto Unificado - Tratamiento", "2025")
    assert unv is True and t == "Concepto Unificado - Tratamiento"


def test_safe_title():
    assert _safe_title('a/b:c"  .') == "a-b-c-"
    assert len(_safe_title("z" * 200)) == 120
```

Correr: `.venv/Scripts/python -m pytest tests/families/test_supersolidaria.py -q`
Esperado: FAIL — `ModuleNotFoundError: No module named 'core.scrapers.families.supersolidaria'`.

- [ ] **Step 2: Escribir el módulo (imports, constantes, helpers)**

Crear `core/scrapers/families/supersolidaria.py`:

```python
import datetime
import re
import unicodedata
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.fecha_es import parse_fecha_providencia_es
from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE = "https://www.supersolidaria.gov.co"
_SOURCE = "Superintendencia de la Economía Solidaria"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
_ANIO_MIN = 2015

_URL_CONCEPTOS = f"{_BASE}/es/conceptos-juridicos-y-contables"

# (url, tipo mostrado, prefijo de título, fecha_por_prosa)
_SECCIONES_TABLA = [
    (f"{_BASE}/es/content/resoluciones-generales", "Resolución", "R", True),
    (f"{_BASE}/es/content/circulares-externas-por-ano", "Circular Externa", "CE", False),
    (f"{_BASE}/es/content/circulares-conjuntas", "Circular Conjunta", "CJ", False),
    (f"{_BASE}/es/content/cartas-circulares", "Carta Circular", "CC", False),
]

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_H2_ANIO_RE = re.compile(
    r"(?i)(?:resoluciones\s+generales|circulares\s+externas|cartas\s+circulares)\s*(20\d{2})\b"
)
_FECHA_ARCHIVO_RE = re.compile(r"/(\d{4})(\d{2})(\d{2})_[^/]+$")
_RADICADO_RE = re.compile(r"\b(\d{7,})\b")
_NUM_MARCADO_RE = re.compile(r"(?:N[°º]|No\.?)\s*0*(\d+)", re.IGNORECASE)
_ENTERO_SUELTO_RE = re.compile(r"\b0*(\d{1,6})\b")
_ANEXO_RE = re.compile(r"^(anexo|matriz de)\b")


def _sin_acentos(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)
    )


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _extension_del_href(href: str) -> str:
    ruta = (href or "").split("?")[0].split("#")[0]
    m = re.search(r"\.([A-Za-z0-9]{1,5})$", ruta)
    return m.group(1).lower() if m else ""


def _es_anexo(titulo: str) -> bool:
    return bool(_ANEXO_RE.match(_sin_acentos(titulo or "").strip().lower()))


def _num_seccion(prefijo: str, titulo: str) -> Optional[int]:
    t = titulo or ""
    if prefijo == "R":
        m = _RADICADO_RE.search(t)
        if m:
            d = m.group(1)
            return int(d[-6:]) if len(d) >= 7 else int(d)
        m = _ENTERO_SUELTO_RE.search(t)
        return int(m.group(1)) if m else None
    m = _NUM_MARCADO_RE.search(t)
    if m:
        return int(m.group(1))
    return None


def _anio_de_h2(texto: str) -> Optional[int]:
    m = _H2_ANIO_RE.search(_sin_acentos(texto or ""))
    return int(m.group(1)) if m else None


def _prefijo_fecha_archivo(href: str) -> Optional[str]:
    m = _FECHA_ARCHIVO_RE.search((href or "").split("?")[0])
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    try:
        return datetime.date(y, mo, d).isoformat()
    except ValueError:
        return None


def _iso_de_time(time_iso: Optional[str]) -> Optional[str]:
    if not time_iso:
        return None
    try:
        return datetime.date.fromisoformat(time_iso[:10]).isoformat()
    except ValueError:
        return None


def _fecha_concepto(href: str, time_iso: Optional[str]) -> Optional[str]:
    return _prefijo_fecha_archivo(href) or _iso_de_time(time_iso)


def _titulo(prefijo: str, tipo: str, titulo_crudo: str, anio: str, es_anexo: bool) -> Tuple[str, bool]:
    numero = _num_seccion(prefijo, titulo_crudo)
    if numero is None:
        return ((titulo_crudo or "").strip() or "documento")[:120].strip(" .") or "documento", True
    base = f"{prefijo}_SES_{numero:04d}_{anio}"
    if es_anexo:
        base = f"{base}_A01"
    return base, False


def _titulo_concepto(href: str, titulo_fila: str, anio: str) -> Tuple[str, bool]:
    nombre = (href or "").split("/")[-1].split("?")[0]
    m = re.search(r"_(\d{10,})\.pdf$", nombre, re.IGNORECASE)
    if m:
        return f"CTO_SES_{m.group(1)}_{anio}", False
    return ((titulo_fila or "").strip() or "documento")[:120].strip(" .") or "documento", True
```

Notas:
- `_H2_ANIO_RE` corre sobre `_sin_acentos(texto)` así que `Economía`→`Economia` no interfiere; el `\xa0` (`&nbsp;`) queda como espacio tras `NFKD`.
- `_num_seccion("R", …)`: `_RADICADO_RE` (`\d{7,}`) captura el radicado largo; para "Resolución 745 de 2003" no hay corrida de ≥7 dígitos, cae a `_ENTERO_SUELTO_RE` y toma 745 (NO 2003, porque 745 aparece antes).

- [ ] **Step 3: Correr en verde**

`.venv/Scripts/python -m pytest tests/families/test_supersolidaria.py -q` → PASS (13 tests).

- [ ] **Step 4: Commit**

```bash
git add core/scrapers/families/supersolidaria.py tests/families/test_supersolidaria.py
git commit -m "feat(supersolidaria): constantes y helpers de parseo"
```

---

### Task 2: Parseo de HTML (fecha, documentos de tabla, filas de conceptos)

**Files:**
- Modify: `core/scrapers/families/supersolidaria.py`
- Test: `tests/families/test_supersolidaria.py`

**Interfaces:**
- Consumes: todo lo de Task 1.
- Produces:
  - `_resolver_fecha(tipo: str, fecha_por_prosa: bool, titulo: str, href: str, anio_h2: Optional[int], time_iso: Optional[str]) -> Optional[str]`
  - `_iter_documentos(soup) -> "Iterator[Tuple[str, object]]"` — emite `("h2", anio:int)` por cada `<h2>` con año, y `("doc", (titulo:str, href:str, time_iso:Optional[str]))` por cada `<a>` dentro de un `span.file`. Recorre en orden de documento.
  - `_filas_concepto(html: str) -> List[Tuple[str, str, Optional[str]]]` — `(titulo, href_pdf, time_iso)` por fila de la vista.

- [ ] **Step 1: Escribir las pruebas y verificarlas en rojo**

Añadir a `tests/families/test_supersolidaria.py`:

```python
from core.scrapers.families.supersolidaria import (
    _filas_concepto,
    _iter_documentos,
    _resolver_fecha,
)
from bs4 import BeautifulSoup


def test_resolver_fecha_resolucion_por_prosa():
    f = _resolver_fecha("Resolución", True,
                        "Resolución 2025430007935 del 30 de diciembre de 2025",
                        "/x/resolucion_2025430007935.pdf", None, None)
    assert f == "2025-12-30"


def test_resolver_fecha_circular_prefiere_time_luego_archivo_luego_h2():
    assert _resolver_fecha("Circular Externa", False, "Circular Externa N° 45", "/x/y.pdf",
                           2019, "2023-02-10T00:00:00Z") == "2023-02-10"
    assert _resolver_fecha("Circular Externa", False, "Circular Externa N° 45",
                           "/x/20221007_circular_externa_42.pdf", 2019, None) == "2022-10-07"
    assert _resolver_fecha("Circular Externa", False, "Circular Externa N° 45",
                           "/x/circular_externa_42.pdf", 2019, None) == "2019-01-01"


def test_resolver_fecha_none_cuando_no_hay_nada():
    assert _resolver_fecha("Circular Conjunta", False, "ministro_del_trabajo", "/x/y.pdf", None, None) is None


_HTML_TABLA = """
<h2 class="western">Circulares Externas</h2>
<h2 class="western">Circulares Externas 2026</h2>
<div class="paragraph paragraph--type--archivos-collection">
 <div class="field field--name-field-archivo"><table><thead><tr><th>Adjunto</th><th>Tamaño</th></tr></thead>
 <tbody><tr><td><span class="file file--mime-application-pdf"><a href="/sites/default/files/data/20260520_circular_externa_101.pdf" title="x">Circular Externa N° 101</a></span><span>(1 KB)</span></td><td>1 KB</td></tr></tbody></table></div>
 <div class="field field--name-field-fecha-de-publicacion"><div class="field__item"><time datetime="2026-05-20T14:54:24Z">x</time></div></div>
</div>
<div class="paragraph paragraph--type--archivos-collection">
 <div class="field field--name-field-archivo"><table><tbody><tr><td><span class="file"><a href="/sites/default/files/data/20260521_anexo_tecnico_circ_101.pdf" title="x">Anexo - Circular Externa N° 101</a></span></td></tr></tbody></table></div>
</div>
<h2 class="western">CIRCULARES EXTERNAS 2015</h2>
<div class="paragraph paragraph--type--archivos-collection">
 <div class="field field--name-field-archivo"><table><tbody><tr><td><span class="file"><a href="/sites/default/files/data/circular_externa_10.pdf" title="x">Circular Externa N° 10</a></span></td></tr></tbody></table></div>
</div>
"""


def test_iter_documentos_emite_h2_y_docs_en_orden():
    soup = BeautifulSoup(_HTML_TABLA, "html.parser")
    eventos = list(_iter_documentos(soup))
    kinds = [e[0] for e in eventos]
    assert kinds == ["h2", "doc", "doc", "h2", "doc"]
    assert eventos[0][1] == 2026
    t0, h0, time0 = eventos[1][1]
    assert t0 == "Circular Externa N° 101"
    assert h0 == "/sites/default/files/data/20260520_circular_externa_101.pdf"
    assert time0 == "2026-05-20T14:54:24Z"
    assert eventos[3][1] == 2015
    assert eventos[4][1][0] == "Circular Externa N° 10"


_HTML_CONCEPTOS = """
<table><thead><tr><th>Nombre</th><th>Resumen</th><th></th></tr></thead><tbody>
<tr>
  <td class="views-field views-field-title"><a href="/es/content/principales-aspectos">Principales aspectos</a></td>
  <td class="views-field views-field-body"><p>Resumen…</p></td>
  <td class="views-field views-field-nothing"><a href="/sites/default/files/conceptos_juridicos_y_contables/20260821_concepto_20261100232001.pdf" target="_blank"><a href="/sites/default/files/conceptos_juridicos_y_contables/20260821_concepto_20261100232001.pdf">Ver más</a></a></td>
</tr>
</tbody></table>
"""


def test_filas_concepto():
    filas = _filas_concepto(_HTML_CONCEPTOS)
    assert len(filas) == 1
    titulo, href, time_iso = filas[0]
    assert titulo == "Principales aspectos"
    assert href == "/sites/default/files/conceptos_juridicos_y_contables/20260821_concepto_20261100232001.pdf"
    assert time_iso is None


def test_filas_concepto_pagina_vacia():
    assert _filas_concepto("<table><thead><tr><th>Nombre</th></tr></thead><tbody></tbody></table>") == []
    assert _filas_concepto("<html><body>nada</body></html>") == []
```

Correr: `.venv/Scripts/python -m pytest tests/families/test_supersolidaria.py -q -k "resolver_fecha or iter_documentos or filas_concepto"`
Esperado: FAIL (`cannot import name '_resolver_fecha'`).

- [ ] **Step 2: Implementar el parseo**

Añadir a `core/scrapers/families/supersolidaria.py` (después de `_titulo_concepto`):

```python
def _resolver_fecha(tipo, fecha_por_prosa, titulo, href, anio_h2, time_iso):
    if fecha_por_prosa:
        d = parse_fecha_providencia_es(titulo or "")
        if d is not None:
            return d.isoformat()
        pf = _prefijo_fecha_archivo(href)
        if pf:
            return pf
        return f"{anio_h2:04d}-01-01" if anio_h2 else None
    # circulares externas / conjuntas / cartas
    iso = _iso_de_time(time_iso) or _prefijo_fecha_archivo(href)
    if iso:
        return iso
    return f"{anio_h2:04d}-01-01" if anio_h2 else None


def _time_iso_de_paragraph(a_tag) -> Optional[str]:
    # sube al paragraph--type--archivos-collection y busca un <time datetime=…>
    cont = a_tag
    for _ in range(6):
        cont = cont.parent
        if cont is None:
            return None
        clases = cont.get("class") or []
        if any("archivos-collection" in c or "paragraph--type--archivos" in c for c in clases):
            t = cont.find("time", attrs={"datetime": True})
            return t["datetime"] if t else None
    return None


def _iter_documentos(soup):
    # recorre todos los <h2> y <a> de span.file en orden de documento
    for nodo in soup.find_all(["h2", "a"]):
        if nodo.name == "h2":
            anio = _anio_de_h2(nodo.get_text(" ", strip=True))
            if anio is not None:
                yield ("h2", anio)
            continue
        # <a>: sólo si su padre inmediato es span.file
        padre = nodo.parent
        if padre is None or padre.name != "span":
            continue
        clases = padre.get("class") or []
        if not any(c == "file" or c.startswith("file--") for c in clases):
            continue
        href = (nodo.get("href") or "").strip()
        if not href:
            continue
        titulo = nodo.get_text(" ", strip=True)
        yield ("doc", (titulo, href, _time_iso_de_paragraph(nodo)))


def _filas_concepto(html: str) -> List[Tuple[str, str, Optional[str]]]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: List[Tuple[str, str, Optional[str]]] = []
    for tr in soup.select("tr"):
        cel_tit = tr.select_one("td.views-field-title")
        cel_dl = tr.select_one("td.views-field-nothing")
        if cel_tit is None or cel_dl is None:
            continue
        a_tit = cel_tit.find("a")
        a_dl = cel_dl.find("a", href=True)
        if a_tit is None or a_dl is None:
            continue
        titulo = a_tit.get_text(" ", strip=True)
        href = a_dl["href"].strip()
        t = tr.find("time", attrs={"datetime": True})
        out.append((titulo, href, t["datetime"] if t else None))
    return out
```

- [ ] **Step 3: Correr en verde**

`.venv/Scripts/python -m pytest tests/families/test_supersolidaria.py -q` → PASS (20 tests).

- [ ] **Step 4: Commit**

```bash
git add core/scrapers/families/supersolidaria.py tests/families/test_supersolidaria.py
git commit -m "feat(supersolidaria): parseo de fecha, documentos de tabla y filas de conceptos"
```

---

### Task 3: Orquestación `scrap()` y registro

**Files:**
- Modify: `core/scrapers/families/supersolidaria.py`
- Modify: `core/scrapers/families/__init__.py`
- Test: `tests/families/test_supersolidaria.py`

**Interfaces:**
- Consumes: todo lo de Tasks 1-2.
- Produces: `@register_family("supersolidaria")` → `class ScrapSupersolidaria(BaseScrapper)` con `filters_by_publication_date = True`, `__init__` que fija `self.source = _SOURCE`, y `scrap(...)`.

- [ ] **Step 1: Escribir las pruebas y verificarlas en rojo**

Añadir a `tests/families/test_supersolidaria.py`:

```python
import threading

import responses

from core.scrapers.registry import FAMILY_REGISTRY
from core.scrapers.families.supersolidaria import ScrapSupersolidaria

_RES_URL = "https://www.supersolidaria.gov.co/es/content/resoluciones-generales"
_CE_URL = "https://www.supersolidaria.gov.co/es/content/circulares-externas-por-ano"
_CJ_URL = "https://www.supersolidaria.gov.co/es/content/circulares-conjuntas"
_CC_URL = "https://www.supersolidaria.gov.co/es/content/cartas-circulares"
_CTO_URL = "https://www.supersolidaria.gov.co/es/conceptos-juridicos-y-contables"


def _doc(href, titulo):
    return (
        '<div class="paragraph paragraph--type--archivos-collection">'
        '<div class="field field--name-field-archivo"><table><tbody><tr><td>'
        f'<span class="file file--mime-application-pdf"><a href="{href}" title="x">{titulo}</a></span>'
        '<span>(1 KB)</span></td></tr></tbody></table></div></div>'
    )


def _pagina_tabla(h2_y_docs):
    # h2_y_docs: lista de ("h2","Circulares Externas 2026") | ("doc", href, titulo)
    partes = []
    for item in h2_y_docs:
        if item[0] == "h2":
            partes.append(f'<h2 class="western">{item[1]}</h2>')
        else:
            partes.append(_doc(item[1], item[2]))
    return "<html><body>" + "".join(partes) + "</body></html>"


def _pagina_conceptos(filas):
    trs = "".join(
        f'<tr><td class="views-field views-field-title"><a href="/es/content/{i}">{t}</a></td>'
        f'<td class="views-field views-field-body"><p>r</p></td>'
        f'<td class="views-field views-field-nothing"><a href="{h}">Ver más</a></td></tr>'
        for i, (t, h) in enumerate(filas)
    )
    return f"<html><body><table><tbody>{trs}</tbody></table></body></html>"


def _vacias():
    return {
        _RES_URL: "<html><body></body></html>",
        _CE_URL: "<html><body></body></html>",
        _CJ_URL: "<html><body></body></html>",
        _CC_URL: "<html><body></body></html>",
    }


def _registrar(paginas, conceptos_por_pagina):
    # `responses` entrega múltiples registros de la misma URL en orden y repite
    # el último; la query `?page=N` no distingue (matching por path). Así que se
    # registran las páginas de conceptos en secuencia + una vacía al final.
    for url, body in paginas.items():
        responses.add(responses.GET, url, body=body)
    for filas in conceptos_por_pagina:
        responses.add(responses.GET, _CTO_URL, body=_pagina_conceptos(filas))
    responses.add(responses.GET, _CTO_URL, body=_pagina_conceptos([]))


def test_supersolidaria_registrada():
    import core.scrapers.families  # noqa: F401
    assert FAMILY_REGISTRY["supersolidaria"].__name__ == "ScrapSupersolidaria"


def test_filters_by_publication_date_activo():
    assert ScrapSupersolidaria.filters_by_publication_date is True


@responses.activate
def test_scrap_resolucion_por_prosa_y_circular_por_h2():
    pag = _vacias()
    pag[_RES_URL] = _pagina_tabla([
        ("h2", "Resoluciones Generales 2025"),
        ("doc", "/sites/default/files/data/20260101_resolucion_2025430007935.pdf",
         "Resolución 2025430007935 del 30 de diciembre de 2025"),
    ])
    pag[_CE_URL] = _pagina_tabla([
        ("h2", "Circulares Externas 2020"),
        ("doc", "/sites/default/files/data/circular_externa_60.pdf", "Circular Externa N° 60"),
    ])
    _registrar(pag, [])
    docs = ScrapSupersolidaria().scrap(fini="2015-01-01", ffin="2026-12-31")
    por = {d.title: d for d in docs}
    assert por["R_SES_7935_2025"].f_public == "2025-12-30"
    assert por["R_SES_7935_2025"].tipo == "Resolución"
    assert por["R_SES_7935_2025"].link == {
        "url": "https://www.supersolidaria.gov.co/sites/default/files/data/20260101_resolucion_2025430007935.pdf",
        "method": "GET",
    }
    assert "verify" not in por["R_SES_7935_2025"].link
    assert por["CE_SES_0060_2020"].f_public == "2020-01-01"
    assert por["CE_SES_0060_2020"].save_path == (
        "Superintendencia de la Economía Solidaria/2020-01-01/Circular Externa/CE_SES_0060_2020(extension)"
    )


@responses.activate
def test_scrap_anexo_recibe_sufijo_a01():
    pag = _vacias()
    pag[_CE_URL] = _pagina_tabla([
        ("h2", "Circulares Externas 2026"),
        ("doc", "/sites/default/files/data/20260520_circular_externa_101.pdf", "Circular Externa N° 101"),
        ("doc", "/sites/default/files/data/20260521_anexo_tecnico_circ_101.pdf", "Anexo - Circular Externa N° 101"),
        ("doc", "/sites/default/files/data/20260521_matriz.xlsx", "Matriz de Comentarios - Circular N° 101"),
    ])
    _registrar(pag, [])
    docs = ScrapSupersolidaria().scrap(fini="2015-01-01", ffin="2026-12-31")
    titles = {d.title for d in docs}
    assert "CE_SES_0101_2026" in titles
    assert "CE_SES_0101_2026_A01" in titles
    # el 2º anexo del mismo número colisiona -> degradado a crudo
    assert any(d.title_unverified and "Matriz" in d.title for d in docs)


@responses.activate
def test_scrap_aplica_piso_2015_y_rango():
    pag = _vacias()
    pag[_CE_URL] = _pagina_tabla([
        ("h2", "Circulares Externas 2013"),
        ("doc", "/x/circular_externa_5.pdf", "Circular Externa N° 5"),
        ("h2", "Circulares Externas 2026"),
        ("doc", "/x/circular_externa_99.pdf", "Circular Externa N° 99"),
    ])
    _registrar(pag, [])
    docs = ScrapSupersolidaria().scrap(fini="2015-01-01", ffin="2026-12-31")
    assert {d.title for d in docs} == {"CE_SES_0099_2026"}


@responses.activate
def test_scrap_conceptos_pagina_hasta_vacio():
    _registrar(_vacias(), [
        [("Principales aspectos", "/sites/default/files/conceptos_juridicos_y_contables/20260821_concepto_20261100232001.pdf")],
        [("Concepto Unificado", "/sites/default/files/conceptos_juridicos_y_contables/20250516_concept_uni.pdf")],
    ])
    docs = ScrapSupersolidaria().scrap(fini="2015-01-01", ffin="2026-12-31")
    conc = {d.title: d for d in docs if d.tipo == "Concepto"}
    assert set(conc) == {"CTO_SES_20261100232001_2026", "Concepto Unificado"}
    assert conc["CTO_SES_20261100232001_2026"].f_public == "2026-08-21"
    assert conc["Concepto Unificado"].title_unverified is True
    assert conc["Concepto Unificado"].f_public == "2025-05-16"


@responses.activate
def test_scrap_omite_doc_sin_fecha_y_avisa():
    pag = _vacias()
    pag[_CJ_URL] = _pagina_tabla([("doc", "/sites/default/files/normativa/circular-conjunta-nov-09.pdf", "circular-conjunta-nov-09")])
    _registrar(pag, [])
    avisos = []
    docs = ScrapSupersolidaria().scrap(fini="2015-01-01", ffin="2026-12-31", on_progress=avisos.append)
    assert [d for d in docs if d.tipo == "Circular Conjunta"] == []
    assert any("sin fecha" in m.lower() for m in avisos)


@responses.activate
def test_scrap_continua_si_una_seccion_falla():
    pag = _vacias()
    responses.add(responses.GET, _RES_URL, status=500)
    del pag[_RES_URL]
    pag[_CE_URL] = _pagina_tabla([("h2", "Circulares Externas 2026"), ("doc", "/x/circular_externa_7.pdf", "Circular Externa N° 7")])
    _registrar(pag, [])
    avisos = []
    docs = ScrapSupersolidaria().scrap(fini="2015-01-01", ffin="2026-12-31", on_progress=avisos.append)
    assert {d.title for d in docs} == {"CE_SES_0007_2026"}
    assert any("Error" in m and "Resoluci" in m for m in avisos)


@responses.activate
def test_scrap_dedup_por_url():
    pag = _vacias()
    dup = "/sites/default/files/data/20260520_circular_externa_101.pdf"
    pag[_CE_URL] = _pagina_tabla([
        ("h2", "Circulares Externas 2026"),
        ("doc", dup, "Circular Externa N° 101"),
        ("doc", dup, "Circular Externa N° 101"),
    ])
    _registrar(pag, [])
    docs = ScrapSupersolidaria().scrap(fini="2015-01-01", ffin="2026-12-31")
    assert len([d for d in docs if d.tipo == "Circular Externa"]) == 1


@responses.activate
def test_scrap_respeta_stop_event():
    ev = threading.Event(); ev.set()
    assert ScrapSupersolidaria().scrap(fini="2015-01-01", ffin="2026-12-31", stop_event=ev) == []
    assert len(responses.calls) == 0

@responses.activate
def test_scrap_limit_corta():
    pag = _vacias()
    pag[_CE_URL] = _pagina_tabla([("h2", "Circulares Externas 2026"),
                                  ("doc", "/x/circular_externa_1.pdf", "Circular Externa N° 1"),
                                  ("doc", "/x/circular_externa_2.pdf", "Circular Externa N° 2")])
    _registrar(pag, [])
    assert len(ScrapSupersolidaria().scrap(fini="2015-01-01", ffin="2026-12-31", limit=1)) == 1
```

Correr: `.venv/Scripts/python -m pytest tests/families/test_supersolidaria.py -q -k scrap`
Esperado: FAIL (`cannot import name 'ScrapSupersolidaria'`).

- [ ] **Step 2: Implementar `scrap()` y el registro**

Añadir a `core/scrapers/families/supersolidaria.py`:

```python
def _agregar(docs, vistos, ya_emitidos, source, tipo, url_pdf, titulo, fecha, prefijo, es_anexo, limit):
    """Construye y agrega un RawDocModel; devuelve True si se alcanzó `limit`."""
    if url_pdf in vistos:
        return False
    title, unverified = _titulo(prefijo, tipo, titulo, fecha[:4], es_anexo)
    if not unverified and title in ya_emitidos and ya_emitidos[title] != url_pdf:
        # colisión de clave con archivo distinto -> degradar
        title, unverified = ((titulo or "").strip() or "documento")[:120].strip(" .") or "documento", True
    vistos.add(url_pdf)
    if not unverified:
        ya_emitidos[title] = url_pdf
    safe = _safe_title(title)
    docs.append(RawDocModel(
        source=source,
        link={"url": url_pdf, "method": "GET"},
        title=title,
        tipo=tipo,
        f_public=fecha,
        f_providencia=fecha,
        detalle=(titulo or "").strip() or None,
        save_path=storage_path(source, fecha, tipo, f"{safe}(extension)"),
        title_unverified=unverified,
    ))
    return len(docs) >= limit


@register_family("supersolidaria")
class ScrapSupersolidaria(BaseScrapper):
    filters_by_publication_date = True

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": _UA})
        docs: List[RawDocModel] = []
        vistos: set = set()
        ya_emitidos: dict = {}
        piso = f"{_ANIO_MIN:04d}-01-01"

        for url, tipo, prefijo, fecha_por_prosa in _SECCIONES_TABLA:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            if on_progress:
                on_progress(f"[{_SOURCE}] Procesando {tipo}...")
            try:
                resp = session.get(url, timeout=90)
                resp.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Error consultando {tipo}: {e}")
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            anio_actual: Optional[int] = None
            for kind, payload in _iter_documentos(soup):
                if stop_event is not None and stop_event.is_set():
                    return docs[:limit]
                if kind == "h2":
                    anio_actual = payload
                    continue
                titulo, href, time_iso = payload
                url_pdf = urljoin(_BASE, href)
                fecha = _resolver_fecha(tipo, fecha_por_prosa, titulo, href, anio_actual, time_iso)
                if fecha is None:
                    if on_progress:
                        on_progress(f"[{_SOURCE}] Aviso: {tipo} sin fecha «{titulo[:70]}», se omite")
                    continue
                if fecha < piso or fecha < fini or fecha > ffin:
                    continue
                if _agregar(docs, vistos, ya_emitidos, _SOURCE, tipo, url_pdf, titulo, fecha,
                            prefijo, _es_anexo(titulo), limit):
                    return docs[:limit]

        # --- Conceptos (vista paginada) ---
        if stop_event is not None and stop_event.is_set():
            return docs[:limit]
        if on_progress:
            on_progress(f"[{_SOURCE}] Procesando Concepto...")
        page = 0
        while True:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            try:
                resp = session.get(_URL_CONCEPTOS, params={"page": page}, timeout=90)
                resp.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Error consultando Concepto (page {page}): {e}")
                break
            filas = _filas_concepto(resp.text)
            if not filas:
                break
            for titulo, href, time_iso in filas:
                if not href:
                    continue
                url_pdf = urljoin(_BASE, href)
                if url_pdf in vistos:
                    continue
                fecha = _fecha_concepto(href, time_iso)
                if fecha is None:
                    if on_progress:
                        on_progress(f"[{_SOURCE}] Aviso: Concepto sin fecha «{titulo[:70]}», se omite")
                    continue
                if fecha < piso or fecha < fini or fecha > ffin:
                    continue
                title, unverified = _titulo_concepto(href, titulo, fecha[:4])
                vistos.add(url_pdf)
                safe = _safe_title(title)
                docs.append(RawDocModel(
                    source=_SOURCE,
                    link={"url": url_pdf, "method": "GET"},
                    title=title,
                    tipo="Concepto",
                    f_public=fecha,
                    f_providencia=fecha,
                    detalle=(titulo or "").strip() or None,
                    save_path=storage_path(_SOURCE, fecha, "Concepto", f"{safe}(extension)"),
                    title_unverified=unverified,
                ))
                if len(docs) >= limit:
                    return docs[:limit]
            page += 1
            if page > 200:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Aviso: tope de 200 páginas de Concepto alcanzado")
                break

        return docs[:limit]
```

Modificar `core/scrapers/families/__init__.py`: la línea de import termina `…, snr, supersociedades  # noqa: F401`; cambiar a `…, snr, supersociedades, supersolidaria  # noqa: F401`.

- [ ] **Step 3: Correr en verde**

`.venv/Scripts/python -m pytest tests/families/test_supersolidaria.py -q` → PASS (~30 tests).
`.venv/Scripts/python -m pytest tests/families/test_supersociedades.py -q` → sigue verde (tocamos `__init__.py`).

- [ ] **Step 4: Commit**

```bash
git add core/scrapers/families/supersolidaria.py core/scrapers/families/__init__.py tests/families/test_supersolidaria.py
git commit -m "feat(supersolidaria): orquestación scrap() de las 5 secciones + registro"
```

---

### Task 4: Alta de la fuente (seed, test_seed, guía)

**Files:**
- Modify: `core/seed.py`
- Modify: `tests/test_seed.py`
- Modify: `docs/guia-despliegue-sistemas.md`
- Test: `tests/test_seed.py`

**Interfaces:**
- Consumes: `@register_family("supersolidaria")` de Task 3.
- Produces: nada.

- [ ] **Step 1: Actualizar las aserciones de `tests/test_seed.py` (rojo primero)**

En `tests/test_seed.py`:
- `assert len(families) == 25` → `assert len(families) == 26`.
- Las **dos** líneas `assert len(sources) == 1 + 28 + 22 + 33 + 6` → `assert len(sources) == 1 + 28 + 23 + 33 + 6`.
- En el `set` de keys, tras `"supersalud", "ssf", "snr", "supersociedades",` agregar `"supersolidaria",`.
- En el comentario que enumera las fuentes únicas (`… supersociedades) + 33 …`), cambiar `supersociedades)` por `supersociedades, supersolidaria)` y `= 90` por `= 91` si aparece.

Correr: `.venv/Scripts/python -m pytest tests/test_seed.py -q` → FAIL (seed crea 25/90, se pide 26/91).

- [ ] **Step 2: Agregar la familia y la fuente en `core/seed.py`**

En `_FAMILIES`, después de la entrada `"supersociedades"`:

```python
    "supersolidaria": (
        "Superintendencia de la Economía Solidaria",
        "Normativa (resoluciones generales, circulares externas, circulares "
        "conjuntas, cartas circulares y conceptos jurídicos y contables) "
        "publicada por la Superintendencia de la Economía Solidaria",
    ),
```

En `seed_source_families_and_sources`, junto a la de `supersociedades`:

```python
    repository.create_source_if_missing(
        db, family_key="supersolidaria",
        name="Superintendencia de la Economía Solidaria", family_params={}
    )
```

- [ ] **Step 3: Correr en verde**

`.venv/Scripts/python -m pytest tests/test_seed.py -q` → PASS.

- [ ] **Step 4: Documentar en la guía de despliegue**

En `docs/guia-despliegue-sistemas.md`, sección nueva (español llano, admin), cerca de las otras `super*`:

```markdown
### Superintendencia de la Economía Solidaria (`supersolidaria`)

- **Qué trae:** cinco secciones del sitio jurídico de la Supersolidaria —
  **Resoluciones generales**, **Circulares externas**, **Circulares
  conjuntas**, **Cartas circulares** y **Conceptos jurídicos y contables**.
  Cada archivo entra como un documento; los anexos (incluidos los `.xlsx` /
  `.doc`) entran aparte con el sufijo `_A01`.
- **Desde cuándo:** año 2015 en adelante.
- **Cómo quedan nombrados:** `R_SES_0007_2025` (resolución; el número son los
  últimos dígitos del radicado), `CE_SES_0102_2026` (circular externa),
  `CJ_SES_0067_2004` (circular conjunta), `CC_SES_0037_2026` (carta circular),
  `CTO_SES_<radicado>_2026` (concepto). Cuando no se puede determinar el
  número, el documento entra con su título original y marca de "sin verificar".
- **Detalle técnico:** sitio Drupal con certificado válido (no se salta la
  validación). Las 4 primeras secciones traen todo en una sola página,
  agrupado por año; las circulares y cartas viejas no traen la fecha exacta
  en el título, así que se fecha por el **encabezado de año** y la fecha
  queda aproximada al 1 de enero de ese año. Conceptos es una lista paginada.
- **Fuente nueva:** después de actualizar producción, correr una vez
  `docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.seed`.
  Es seguro repetirlo.
```

- [ ] **Step 5: Commit**

```bash
git add core/seed.py tests/test_seed.py docs/guia-despliegue-sistemas.md
git commit -m "feat(supersolidaria): alta de la fuente + bump de test_seed + guía de despliegue"
```

---

## Notas de verificación final (para el revisor de rama completa)

- `pytest tests/families/test_supersolidaria.py tests/test_seed.py -q` en verde.
- **Verificar en vivo** contra `https://www.supersolidaria.gov.co` las 5 secciones (el revisor de `supersociedades` encontró bugs reales que las 4 revisiones por tarea no vieron por usar fixtures irreales): confirmar que `_iter_documentos` casa el marcado real de `span.file > a`, que los `<h2>` de año se detectan (mayúsculas + `&nbsp;`), que `parse_fecha_providencia_es` resuelve la prosa de los títulos de resolución, que los hrefs no vienen percent-encoded (Drupal suele servirlos limpios — confirmar), y contar cuántos documentos entran vs. cuántos quedan sin fecha por sección para un rango 2015-2026.
- Confirmar que ninguna ruta pone `verify=False` ni `link["verify"]`.
- Confirmar el dedup por URL y la degradación de `_A01` en colisión.
