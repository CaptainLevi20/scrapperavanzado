# Fuente SSF — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir la fuente "Superintendencia del Subsidio Familiar" (familia técnica `ssf`) que raspa Resoluciones y Circulares Externas del portal Liferay de la SSF.

**Architecture:** Un módulo plano `core/scrapers/families/ssf.py` con `@register_family("ssf")`, del arquetipo "tabla HTML de normatividad" (como `mincit` / `superfinanciera.normativa`): `requests.get` a dos URLs fijas servidas enteras en HTML, `BeautifulSoup` para parsear todas las tablas de datos de cada página, filtro por fecha en cliente. Sin paginación, sin API, sin transporte especial.

**Tech Stack:** Python, `requests`, `beautifulsoup4` (`bs4`), `pytest`, `responses` (mock HTTP en tests). `core/fecha_es.parse_fecha_providencia_es` para fechas en prosa. `core/downloader.py` ya resuelve la extensión del archivo desde el `Content-Disposition`.

**Spec:** `docs/superpowers/specs/2026-09-07-fuente-ssf-design.md`

## Global Constraints

- **Sigla de entidad en el título:** `SSF` (verbatim).
- **Formato de título:** `{letra}_SSF_{int(digitos):04d}{sufijo_letra}_{año}` con `letra` = `R` (Resolución) / `C` (Circular Externa); `sufijo_letra` = una letra mayúscula pegada al número si la trae (`C_SSF_0003A_2024`), normalmente `""`; `año` = año de la fecha del documento.
- **Piso de cobertura:** solo documentos con fecha cuyo `año >= 2024`. El rango pedido en la corrida se acota además a este piso.
- **Fecha de Resolución:** preferir `core/fecha_es.parse_fecha_providencia_es(asunto)`; respaldo = la fecha corta `DD-MM-YY` de la columna `Documento` (`2000 + YY`). Si ninguna parsea → se descarta la fila con aviso `on_progress`.
- **Fecha de Circular:** columna `Fecha`, formato `DD/MM/YYYY`. Si no parsea → se descarta con aviso.
- **Número no parseable → `title_unverified = True`** con el texto crudo (para Resolución el de `Documento`, respaldo `Asunto`; para Circular el de la celda `Número`, respaldo `Asunto`), recortado a 120.
- **Anexos:** sin manejo especial — una fila = un documento.
- **Flags `BaseScrapper`:** `filters_by_publication_date = True`; los otros dos quedan en su valor por defecto.
- **`review_status`:** por defecto (`pending`). Sin `auto_review_status` en el seed.
- **`tests/test_seed.py`** lleva conteos canónicos que rompen con cada familia nueva: `len(families)` 22→**23**; el set de claves de `test_seed_populates_families_and_sources_and_is_idempotent` gana `"ssf"`; las dos aserciones `assert len(sources) == 1 + 28 + 19 + 33 + 6` pasan a `1 + 28 + 20 + 33 + 6` (con su comentario). Ver `memory/dev_env_gotchas`.
- Ejecutar Python siempre con `.venv/Scripts/python` / `.venv/Scripts/pytest` (shell: Git Bash en Windows nativo).
- **Gate de test por tarea = suite enfocada, NO `pytest -q` completo** (las suites con DB no corren en bloque en este entorno; CI corre la completa en el PR): `.venv/Scripts/python -m pytest tests/families/test_ssf.py tests/families/test_mincit.py -q`.

---

## File Structure

- **Create `core/scrapers/families/ssf.py`** — la familia completa: constantes + `_SECCIONES`, helpers de parseo (fecha, número, título, saneo), selección de tablas y mapeo fila→`RawDocModel` (`_fila_resolucion`, `_fila_circular`, `_armar_doc`), y la clase `ScrapSSF`. Módulo plano, ~160 líneas, estilo `core/scrapers/families/mincit.py`.
- **Modify `core/scrapers/families/__init__.py`** — añadir `ssf` a la línea de import de registro.
- **Modify `core/seed.py`** — entrada en `_FAMILIES` + una llamada `repository.create_source_if_missing(...)`.
- **Modify `tests/test_seed.py`** — los tres bumps de conteo canónico (ver Global Constraints).
- **Create `tests/families/test_ssf.py`** — unit tests de helpers + tests de mapeo de fila con fixtures HTML + tests de `scrap()` con `responses`.
- **Modify `docs/guia-despliegue-sistemas.md`** — nota de la fuente nueva (§10) + mención del `core.seed` (§7 ya lo tiene desde la fuente anterior; confirmar).

---

## Task 1: Helpers de parseo (fecha, número, título) + constantes

**Files:**
- Create: `core/scrapers/families/ssf.py`
- Test: `tests/families/test_ssf.py`

**Interfaces:**
- Produces:
  - `_sin_acentos(s: str) -> str`
  - `_safe_title(title: str) -> str`
  - `_fecha_corta(texto: str) -> datetime.date | None` — `DD-MM-YY` → `date(2000+YY, MM, DD)`
  - `_fecha_slash(texto: str) -> datetime.date | None` — `DD/MM/YYYY` → `date`
  - `_num_circular(celda: str) -> tuple[str, str] | None` — `(digitos_sin_ceros, sufijo_letra_mayus)` o `None`
  - `_num_resolucion(asunto: str, documento: str) -> str | None` — dígitos
  - `_titulo(letra: str, digitos: str | None, sufijo: str, anio: int, texto_crudo: str) -> tuple[str, bool]` — `(title, title_unverified)`
- Constantes: `_BASE`, `_SOURCE`, `_ANIO_MIN` (2024), `_UA`, `_SECCIONES` (lista de `(url, tipo, letra, columnas:set[str])`).

- [ ] **Step 1: Write the failing tests**

Create `tests/families/test_ssf.py`:

```python
import datetime

from core.scrapers.families.ssf import (
    _fecha_corta,
    _fecha_slash,
    _num_circular,
    _num_resolucion,
    _safe_title,
    _titulo,
)


# ---- fechas ----
def test_fecha_corta_ddmmyy_to_20yy():
    assert _fecha_corta("RESOLUCIÓN RES. 0789 DE 15-09-26") == datetime.date(2026, 9, 15)


def test_fecha_corta_none_when_absent_or_invalid():
    assert _fecha_corta("RESOLUCIÓN 1617 del 30 de diciembre de 2025") is None
    assert _fecha_corta("32-13-26") is None


def test_fecha_slash_ddmmyyyy():
    assert _fecha_slash("17/12/2025") == datetime.date(2025, 12, 17)
    assert _fecha_slash("6/10/2003") == datetime.date(2003, 10, 6)


def test_fecha_slash_none_when_absent_or_invalid():
    assert _fecha_slash("sin fecha") is None
    assert _fecha_slash("30/02/2025") is None


# ---- número circular ----
def test_num_circular_with_ce_prefix():
    assert _num_circular("CE 00011") == ("11", "")


def test_num_circular_without_ce_prefix():
    assert _num_circular("00002") == ("2", "")


def test_num_circular_letter_suffix_uppercased():
    assert _num_circular("CE 0003A") == ("3", "A")


def test_num_circular_none_when_no_digits():
    assert _num_circular("") is None
    assert _num_circular("circular externa") is None


# ---- número resolución ----
def test_num_resolucion_from_asunto_first():
    assert _num_resolucion('Resolución 0789 del 15 de Agosto de 2026 "x"', "RESOLUCIÓN RES. 0789 DE 15-09-26") == "0789"


def test_num_resolucion_falls_back_to_documento():
    assert _num_resolucion("texto sin numero de resolucion", "RESOLUCIÓN RES. 0612 DE 03-08-26") == "0612"
    assert _num_resolucion("", "RESOLUCIÓN 1617 del 30 de diciembre de 2025") == "1617"


def test_num_resolucion_none_when_unparseable():
    assert _num_resolucion("por la cual se hace algo", "documento raro") is None


# ---- título ----
def test_titulo_verified_resolucion():
    assert _titulo("R", "0789", "", 2026, "irrelevante") == ("R_SSF_0789_2026", False)


def test_titulo_verified_circular_with_letter_suffix():
    assert _titulo("C", "3", "A", 2024, "irrelevante") == ("C_SSF_0003A_2024", False)


def test_titulo_unverified_keeps_raw_trimmed():
    title, unv = _titulo("R", None, "", 2025, "RESOLUCIÓN 99 rara del sitio")
    assert unv is True
    assert title == "RESOLUCIÓN 99 rara del sitio"


def test_titulo_unverified_empty_raw_falls_back_to_documento():
    assert _titulo("C", None, "", 2025, "") == ("documento", True)


# ---- safe_title ----
def test_safe_title_replaces_invalid_and_trims():
    assert _safe_title('Doc/con "raros": x|y*  .') == "Doc-con -raros-- x-y-"
    assert len(_safe_title("z" * 300)) == 120
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/families/test_ssf.py -q`
Expected: FAIL — `ModuleNotFoundError` (el módulo aún no existe).

- [ ] **Step 3: Write the module with the helpers**

Create `core/scrapers/families/ssf.py`:

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

_BASE = "https://www.ssf.gov.co"
_SOURCE = "Superintendencia del Subsidio Familiar"
_ANIO_MIN = 2024
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# (url, tipo mostrado, letra del código, columnas esperadas del encabezado en
# minúsculas y sin acentos)
_SECCIONES = [
    (f"{_BASE}/web/guest/resoluciones2", "Resolución", "R", {"documento", "asunto", "enlace"}),
    (f"{_BASE}/web/guest/normativa-circulares", "Circular Externa", "C", {"numero", "fecha", "asunto", "adjunto"}),
]

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_NUM_RES_ASUNTO = re.compile(r"resoluci[oó]n\s+(\d+)", re.I)
_NUM_RES_DOC = re.compile(r"(?:RES\.?|RESOLUCI[ÓO]N)\s*(\d+)", re.I)
_FECHA_CORTA = re.compile(r"(\d{1,2})-(\d{1,2})-(\d{2})\b")
_FECHA_SLASH = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})\b")
_NUM_CIRCULAR = re.compile(r"^\s*(?:CE\s*)?0*(\d+)\s*([A-Za-z]?)", re.I)


def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _fecha_corta(texto: str) -> Optional[datetime.date]:
    m = _FECHA_CORTA.search(texto or "")
    if not m:
        return None
    dd, mm, yy = (int(x) for x in m.groups())
    try:
        return datetime.date(2000 + yy, mm, dd)
    except ValueError:
        return None


def _fecha_slash(texto: str) -> Optional[datetime.date]:
    m = _FECHA_SLASH.search(texto or "")
    if not m:
        return None
    dd, mm, yyyy = (int(x) for x in m.groups())
    try:
        return datetime.date(yyyy, mm, dd)
    except ValueError:
        return None


def _num_circular(celda: str) -> Optional[Tuple[str, str]]:
    m = _NUM_CIRCULAR.match(celda or "")
    if not m:
        return None
    return m.group(1), m.group(2).upper()


def _num_resolucion(asunto: str, documento: str) -> Optional[str]:
    m = _NUM_RES_ASUNTO.search(asunto or "")
    if m:
        return m.group(1)
    m = _NUM_RES_DOC.search(documento or "")
    return m.group(1) if m else None


def _titulo(letra: str, digitos: Optional[str], sufijo: str, anio: int, texto_crudo: str) -> Tuple[str, bool]:
    if digitos:
        return f"{letra}_SSF_{int(digitos):04d}{sufijo}_{anio}", False
    return ((texto_crudo or "").strip() or "documento")[:120], True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/families/test_ssf.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/ssf.py tests/families/test_ssf.py
git commit -m "feat(ssf): helpers de parseo de fecha, número y título"
```

---

## Task 2: Selección de tablas + mapeo fila → RawDocModel

**Files:**
- Modify: `core/scrapers/families/ssf.py`
- Test: `tests/families/test_ssf.py`

**Interfaces:**
- Consumes: helpers de Task 1; `parse_fecha_providencia_es`; `storage_path`; `RawDocModel`.
- Produces:
  - `_tablas_de_datos(soup, columnas: set[str]) -> list` — tablas cuya fila de encabezado contiene `columnas`
  - `_celdas_texto(tr) -> list[str]`
  - `_href_de_fila(tr) -> str | None` — primer `<a href>` no-`javascript`
  - `_fila_resolucion(tr, fini: str, ffin: str, on_progress) -> RawDocModel | None`
  - `_fila_circular(tr, fini: str, ffin: str, on_progress) -> RawDocModel | None`
  - `_armar_doc(tipo, letra, digitos, sufijo, fecha: datetime.date, fini, ffin, asunto, texto_crudo, href) -> RawDocModel | None`
    - devuelve `None` si `fecha.year < _ANIO_MIN`, o `iso < fini`, o `iso > ffin`.

- [ ] **Step 1: Write the failing tests**

Añadir a `tests/families/test_ssf.py`:

```python
from bs4 import BeautifulSoup

from core.scrapers.families.ssf import (
    _fila_circular,
    _fila_resolucion,
    _tablas_de_datos,
)

_RES_HTML = """
<div>
<table><tr><td>layout</td></tr></table>
<table>
  <tr><th>Documento</th><th>Asunto</th><th>Enlace</th></tr>
  <tr>
    <td>RESOLUCIÓN RES. 0789 DE 15-09-26</td>
    <td>Resolución 0789 del 15 de Agosto de 2026 "Por la cual se hace algo"</td>
    <td><a href="/documents/d/guest/res-0789">Descargar</a></td>
  </tr>
  <tr>
    <td>RESOLUCIÓN 1617 del 30 de diciembre de 2025</td>
    <td>Resolución 1617 del 30 de diciembre de 2025 "Por la cual se deroga otra"</td>
    <td><a href="https://www.ssf.gov.co/documents/d/guest/res-1617">Descargar</a></td>
  </tr>
  <tr>
    <td>RESOLUCIÓN 0053 del 5 de febrero de 2019</td>
    <td>Resolución 0053 del 5 de febrero de 2019 "vieja"</td>
    <td><a href="/documents/d/guest/res-0053">Descargar</a></td>
  </tr>
</table>
</div>
"""

_CIR_HTML = """
<table>
  <tr><th>Número</th><th>Fecha</th><th>Asunto</th><th>Adjunto</th></tr>
  <tr><td>CE 00011</td><td>17/12/2025</td><td>CANALES OFICIALES</td>
      <td><a href="/documents/d/guest/circular-0011-2025">Circular externa 00011-2025</a></td></tr>
  <tr><td>CE 0003A</td><td>28/06/2024</td><td>Ampliación del periodo</td>
      <td><a href="https://www.ssf.gov.co/documents/d/guest/circular-00003a">Circular externa 0003A</a></td></tr>
  <tr><td>00002</td><td>24/07/2026</td><td>XVIII ENCUENTRO</td>
      <td><a href="/documents/d/guest/circular-ssf-2026-00002">Circular externa SSF 2026-00002</a></td></tr>
  <tr><td>CE 0028</td><td>27/12/2010</td><td>reporte de recaudos</td>
      <td><a href="/documents/20127/47342/0028.pdf/uuid">Circular externa 0028</a></td></tr>
</table>
"""


def test_tablas_de_datos_picks_by_header_ignoring_layout():
    soup = BeautifulSoup(_RES_HTML, "html.parser")
    tablas = _tablas_de_datos(soup, {"documento", "asunto", "enlace"})
    assert len(tablas) == 1
    assert len(tablas[0].find_all("tr")) == 4  # header + 3 filas


def _rows(html, columnas):
    soup = BeautifulSoup(html, "html.parser")
    t = _tablas_de_datos(soup, columnas)[0]
    return t.find_all("tr")[1:]


def test_fila_resolucion_prefers_asunto_prose_date_and_number():
    tr = _rows(_RES_HTML, {"documento", "asunto", "enlace"})[0]
    doc = _fila_resolucion(tr, "2024-01-01", "2026-12-31", None)
    assert doc is not None
    assert doc.title == "R_SSF_0789_2026"
    assert doc.tipo == "Resolución"
    assert doc.f_public == "2026-08-15"  # del Asunto ("15 de Agosto de 2026"), NO 15-09-26
    assert doc.f_providencia == "2026-08-15"
    assert doc.link == {"url": "https://www.ssf.gov.co/documents/d/guest/res-0789", "method": "GET"}
    assert doc.save_path == "Superintendencia del Subsidio Familiar/2026-08-15/Resolución/R_SSF_0789_2026(extension)"
    assert doc.detalle.startswith("Resolución 0789")


def test_fila_resolucion_format_2025():
    tr = _rows(_RES_HTML, {"documento", "asunto", "enlace"})[1]
    doc = _fila_resolucion(tr, "2024-01-01", "2026-12-31", None)
    assert doc.title == "R_SSF_1617_2025"
    assert doc.f_public == "2025-12-30"


def test_fila_resolucion_below_year_floor_is_dropped():
    tr = _rows(_RES_HTML, {"documento", "asunto", "enlace"})[2]  # 2019
    assert _fila_resolucion(tr, "2018-01-01", "2026-12-31", None) is None


def test_fila_circular_maps_number_date_and_link():
    tr = _rows(_CIR_HTML, {"numero", "fecha", "asunto", "adjunto"})[0]
    doc = _fila_circular(tr, "2024-01-01", "2026-12-31", None)
    assert doc.title == "C_SSF_0011_2025"
    assert doc.tipo == "Circular Externa"
    assert doc.f_public == "2025-12-17"
    assert doc.link["url"] == "https://www.ssf.gov.co/documents/d/guest/circular-0011-2025"


def test_fila_circular_letter_suffix():
    tr = _rows(_CIR_HTML, {"numero", "fecha", "asunto", "adjunto"})[1]
    doc = _fila_circular(tr, "2024-01-01", "2026-12-31", None)
    assert doc.title == "C_SSF_0003A_2024"


def test_fila_circular_no_ce_prefix():
    tr = _rows(_CIR_HTML, {"numero", "fecha", "asunto", "adjunto"})[2]
    doc = _fila_circular(tr, "2024-01-01", "2026-12-31", None)
    assert doc.title == "C_SSF_0002_2026"


def test_fila_circular_old_row_dropped_by_year_floor():
    tr = _rows(_CIR_HTML, {"numero", "fecha", "asunto", "adjunto"})[3]  # 2010
    assert _fila_circular(tr, "2009-01-01", "2026-12-31", None) is None


def test_fila_circular_outside_requested_range_dropped():
    tr = _rows(_CIR_HTML, {"numero", "fecha", "asunto", "adjunto"})[0]  # 2025-12-17
    assert _fila_circular(tr, "2024-01-01", "2025-06-30", None) is None


def test_fila_resolucion_unverified_when_no_number():
    html = _RES_HTML.replace(
        "RESOLUCIÓN RES. 0789 DE 15-09-26", "DOCUMENTO SIN NUMERO 15-09-26"
    ).replace(
        'Resolución 0789 del 15 de Agosto de 2026 "Por la cual se hace algo"',
        "Acto del 15 de Agosto de 2026 sin numero reconocible",
    )
    tr = _rows(html, {"documento", "asunto", "enlace"})[0]
    doc = _fila_resolucion(tr, "2024-01-01", "2026-12-31", None)
    assert doc.title_unverified is True
    assert doc.title == "DOCUMENTO SIN NUMERO 15-09-26"
    segs = doc.save_path.split("/")
    assert len(segs) == 4 and not any(c in segs[-1] for c in '\\/*?:"<>|')


def test_fila_circular_without_date_is_dropped_and_warns():
    html = _CIR_HTML.replace("17/12/2025", "sin fecha")
    tr = _rows(html, {"numero", "fecha", "asunto", "adjunto"})[0]
    avisos = []
    assert _fila_circular(tr, "2024-01-01", "2026-12-31", avisos.append) is None
    assert any("sin fecha" in m.lower() for m in avisos)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/families/test_ssf.py -q -k "tablas or fila_"`
Expected: FAIL — `ImportError` de `_tablas_de_datos` / `_fila_resolucion` / `_fila_circular`.

- [ ] **Step 3: Implement table selection + row mapping**

Añadir a `core/scrapers/families/ssf.py` (después de `_titulo`):

```python
def _tablas_de_datos(soup, columnas):
    out = []
    for t in soup.find_all("table"):
        filas = t.find_all("tr")
        if not filas:
            continue
        encabezado = {
            _sin_acentos(c.get_text(" ", strip=True)).lower()
            for c in filas[0].find_all(["th", "td"])
        }
        if columnas.issubset(encabezado):
            out.append(t)
    return out


def _celdas_texto(tr):
    return [td.get_text(" ", strip=True) for td in tr.find_all("td")]


def _href_de_fila(tr):
    for a in tr.find_all("a", href=True):
        href = a["href"].strip()
        if href and not href.lower().startswith("javascript"):
            return href
    return None


def _armar_doc(tipo, letra, digitos, sufijo, fecha, fini, ffin, asunto, texto_crudo, href) -> Optional[RawDocModel]:
    if fecha.year < _ANIO_MIN:
        return None
    iso = fecha.isoformat()
    if iso < fini or iso > ffin:
        return None
    title, unverified = _titulo(letra, digitos, sufijo, fecha.year, texto_crudo)
    safe = _safe_title(title)
    return RawDocModel(
        source=_SOURCE,
        link={"url": urljoin(_BASE, href), "method": "GET"},
        title=title,
        tipo=tipo,
        f_public=iso,
        f_providencia=iso,
        detalle=(asunto or "").strip() or None,
        save_path=storage_path(_SOURCE, iso, tipo, f"{safe}(extension)"),
        title_unverified=unverified,
    )


def _fila_resolucion(tr, fini, ffin, on_progress) -> Optional[RawDocModel]:
    tds = _celdas_texto(tr)
    if len(tds) < 2:
        return None
    documento, asunto = tds[0], tds[1]
    href = _href_de_fila(tr)
    if not href:
        return None
    fecha = parse_fecha_providencia_es(asunto) or _fecha_corta(documento)
    if fecha is None:
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: resolución sin fecha parseable «{documento[:70]}», se omite")
        return None
    numero = _num_resolucion(asunto, documento)
    return _armar_doc("Resolución", "R", numero, "", fecha, fini, ffin, asunto, documento or asunto, href)


def _fila_circular(tr, fini, ffin, on_progress) -> Optional[RawDocModel]:
    tds = _celdas_texto(tr)
    if len(tds) < 4:
        return None
    celda_num, celda_fecha, asunto = tds[0], tds[1], tds[2]
    href = _href_de_fila(tr)
    if not href:
        return None
    fecha = _fecha_slash(celda_fecha)
    if fecha is None:
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: circular sin fecha parseable «{celda_num[:40]}», se omite")
        return None
    parsed = _num_circular(celda_num)
    digitos, sufijo = parsed if parsed else (None, "")
    return _armar_doc("Circular Externa", "C", digitos, sufijo, fecha, fini, ffin, asunto, celda_num or asunto, href)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/families/test_ssf.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/ssf.py tests/families/test_ssf.py
git commit -m "feat(ssf): selección de tablas y mapeo de fila a RawDocModel"
```

---

## Task 3: `ScrapSSF.scrap` + registro + smoke test en vivo

**Files:**
- Modify: `core/scrapers/families/ssf.py`
- Modify: `core/scrapers/families/__init__.py`
- Test: `tests/families/test_ssf.py`

**Interfaces:**
- Consumes: `_SECCIONES`, `_tablas_de_datos`, `_fila_resolucion`, `_fila_circular` (Tasks 1-2).
- Produces: `ScrapSSF` registrada como `@register_family("ssf")`, con
  `scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]` y `filters_by_publication_date = True`.

**Comportamiento de `scrap`:**
1. `session = requests.Session()` con `User-Agent: _UA`.
2. Por cada `(url, tipo, letra, columnas)` en `_SECCIONES`:
   - Chequear `stop_event` antes de la sección → `return docs[:limit]`.
   - `on_progress(f"[{_SOURCE}] Procesando {tipo}...")`.
   - `GET url` con `timeout=60`; si lanza (incluye `raise_for_status`), `on_progress` con `"Error"` y **`continue`** a la siguiente sección (no abortar).
   - `BeautifulSoup(resp.text, "html.parser")`.
   - `fila_fn = _fila_resolucion if letra == "R" else _fila_circular`.
   - Por cada tabla de `_tablas_de_datos(soup, columnas)` (chequear `stop_event` entre tablas), por cada `<tr>` menos el encabezado: `doc = fila_fn(tr, fini, ffin, on_progress)`; si no es `None`, `append`; si `len(docs) >= limit`, `return docs[:limit]`.
3. `return docs[:limit]`.

- [ ] **Step 1: Write the failing tests**

Añadir a `tests/families/test_ssf.py`:

```python
import threading

import responses

from core.scrapers.registry import FAMILY_REGISTRY
from core.scrapers.families.ssf import ScrapSSF

_RES_URL = "https://www.ssf.gov.co/web/guest/resoluciones2"
_CIR_URL = "https://www.ssf.gov.co/web/guest/normativa-circulares"

_RES_PAGE = """<html><body>
<table><tr><th>x</th></tr><tr><td>layout</td></tr></table>
<table>
  <tr><th>Documento</th><th>Asunto</th><th>Enlace</th></tr>
  <tr><td>RESOLUCIÓN RES. 0789 DE 15-09-26</td>
      <td>Resolución 0789 del 15 de Agosto de 2026 "x"</td>
      <td><a href="/documents/d/guest/res-0789">D</a></td></tr>
  <tr><td>RESOLUCIÓN 0053 del 5 de febrero de 2019</td>
      <td>Resolución 0053 del 5 de febrero de 2019 "vieja"</td>
      <td><a href="/documents/d/guest/res-0053">D</a></td></tr>
</table></body></html>
"""

_CIR_PAGE = """<html><body>
<table>
  <tr><th>Número</th><th>Fecha</th><th>Asunto</th><th>Adjunto</th></tr>
  <tr><td>CE 00011</td><td>17/12/2025</td><td>CANALES</td>
      <td><a href="/documents/d/guest/cir-0011">A</a></td></tr>
</table></body></html>
"""


def test_ssf_is_registered():
    import core.scrapers.families  # noqa: F401
    assert FAMILY_REGISTRY["ssf"].__name__ == "ScrapSSF"


def test_filters_by_publication_date_is_enabled():
    assert ScrapSSF.filters_by_publication_date is True


@responses.activate
def test_scrap_collects_both_sections_and_applies_year_floor():
    responses.add(responses.GET, _RES_URL, body=_RES_PAGE)
    responses.add(responses.GET, _CIR_URL, body=_CIR_PAGE)

    docs = ScrapSSF().scrap(fini="2018-01-01", ffin="2026-12-31")
    titles = {d.title for d in docs}
    assert titles == {"R_SSF_0789_2026", "C_SSF_0011_2025"}  # la resolución de 2019 cae por el piso 2024


@responses.activate
def test_scrap_respects_requested_range():
    responses.add(responses.GET, _RES_URL, body=_RES_PAGE)
    responses.add(responses.GET, _CIR_URL, body=_CIR_PAGE)

    docs = ScrapSSF().scrap(fini="2026-01-01", ffin="2026-12-31")
    assert {d.title for d in docs} == {"R_SSF_0789_2026"}  # la circular es de 2025


@responses.activate
def test_scrap_continues_when_one_section_fails():
    responses.add(responses.GET, _RES_URL, status=500)
    responses.add(responses.GET, _CIR_URL, body=_CIR_PAGE)

    progreso = []
    docs = ScrapSSF().scrap(fini="2024-01-01", ffin="2026-12-31", on_progress=progreso.append)
    assert {d.title for d in docs} == {"C_SSF_0011_2025"}
    assert any("Error" in m for m in progreso)


@responses.activate
def test_scrap_stops_on_stop_event():
    responses.add(responses.GET, _RES_URL, body=_RES_PAGE)
    responses.add(responses.GET, _CIR_URL, body=_CIR_PAGE)
    ev = threading.Event()
    ev.set()
    docs = ScrapSSF().scrap(fini="2024-01-01", ffin="2026-12-31", stop_event=ev)
    assert docs == []
    assert len(responses.calls) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/families/test_ssf.py -q -k "scrap or is_registered or filters_by"`
Expected: FAIL — `ImportError: cannot import name 'ScrapSSF'`.

- [ ] **Step 3: Implement `ScrapSSF` and register it**

Añadir al final de `core/scrapers/families/ssf.py`:

```python
@register_family("ssf")
class ScrapSSF(BaseScrapper):
    filters_by_publication_date = True

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": _UA})
        docs: List[RawDocModel] = []

        for url, tipo, letra, columnas in _SECCIONES:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            if on_progress:
                on_progress(f"[{_SOURCE}] Procesando {tipo}...")
            try:
                resp = session.get(url, timeout=60)
                resp.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Error consultando {tipo}: {e}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            fila_fn = _fila_resolucion if letra == "R" else _fila_circular
            for tabla in _tablas_de_datos(soup, columnas):
                if stop_event is not None and stop_event.is_set():
                    return docs[:limit]
                for tr in tabla.find_all("tr")[1:]:
                    doc = fila_fn(tr, fini, ffin, on_progress)
                    if doc is not None:
                        docs.append(doc)
                        if len(docs) >= limit:
                            return docs[:limit]

        return docs[:limit]
```

Modificar `core/scrapers/families/__init__.py` — añadir `ssf` al final de la lista de imports:

```python
from . import constitucional, samai, corte_suprema, jep, cndj, adr, adres, ane, anh, rama_judicial, mincit, madr, minambiente, minvivienda, mineducacion, mininterior, mindeporte, minjusticia, minenergia, mintrabajo, superfinanciera, supersalud, ssf  # noqa: F401
```

- [ ] **Step 4: Run the family test file**

Run: `.venv/Scripts/pytest tests/families/test_ssf.py tests/families/test_mincit.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Smoke test en vivo (manual, obligatorio antes de commitear)**

El HTML real puede haber cambiado de forma desde la muestra. Correr contra el sitio real:

```bash
.venv/Scripts/python -c "
from core.scrapers.families.ssf import ScrapSSF
docs = ScrapSSF().scrap(fini='2024-01-01', ffin='2026-12-31', on_progress=print)
print('TOTAL', len(docs))
for d in docs[:10]:
    print(d.f_public, '|', d.tipo, '|', d.title, '|', d.title_unverified, '|', d.link['url'][:95])
assert docs, 'sin documentos: revisar los encabezados de tabla o los selectores'
assert all(d.f_public >= '2024-01-01' for d in docs), 'llegaron fechas bajo el piso'
assert any(d.tipo == 'Circular Externa' for d in docs) and any(d.tipo == 'Resolución' for d in docs), 'falta una de las dos secciones'
verif = [d for d in docs if not d.title_unverified]
print('verificados:', len(verif), '/', len(docs))
print('OK')
"
```

A ojo: se imprimen filas de ambos tipos, títulos `R_SSF_####_20XX` / `C_SSF_####_20XX` mayormente verificados, URLs que apuntan a `www.ssf.gov.co/documents/d/guest/...`. Si sale `sin documentos`, revisar que los encabezados de las tablas reales coincidan con los conjuntos de `_SECCIONES` (imprimir `{_sin_acentos(c.get_text()).lower() for c in fila0}` de cada `<table>`). **No** commitear hasta que pase.

- [ ] **Step 6: Commit**

```bash
git add core/scrapers/families/ssf.py core/scrapers/families/__init__.py tests/families/test_ssf.py
git commit -m "feat(ssf): orquestación scrap() de las dos secciones + registro de la familia"
```

---

## Task 4: Seed + bump de test_seed.py + nota de documentación

**Files:**
- Modify: `core/seed.py`
- Modify: `tests/test_seed.py`
- Modify: `docs/guia-despliegue-sistemas.md`
- Test: `tests/families/test_ssf.py`

**Interfaces:**
- Consumes: `FAMILY_REGISTRY` ya poblado por el import de Task 3.
- Produces: entrada `"ssf"` en `_FAMILIES` y una fuente `"Superintendencia del Subsidio Familiar"` sembrada con `family_key="ssf"`, `family_params={}`.

- [ ] **Step 1: Write the failing tests**

Añadir a `tests/families/test_ssf.py`:

```python
def test_seed_families_dict_has_ssf_entry():
    from core.seed import _FAMILIES
    assert "ssf" in _FAMILIES
    display_name, description = _FAMILIES["ssf"]
    assert display_name == "Superintendencia del Subsidio Familiar"
    assert "esolucion" in description or "esoluciones" in description
    assert "irculares" in description
```

Y actualizar en `tests/test_seed.py` las tres aserciones canónicas (ver Global Constraints): `22` → `23`, añadir `"ssf"` al set de claves, `1 + 28 + 19 + 33 + 6` → `1 + 28 + 20 + 33 + 6` en las dos ocurrencias (y el comentario `... + 19 (fuente única: ...)` → `20` con `ssf` al final de la lista).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/families/test_ssf.py -q -k seed_families_dict`
Expected: FAIL — `KeyError: 'ssf'`.

- [ ] **Step 3: Add the seed entry**

En `core/seed.py`, dentro del dict `_FAMILIES`, añadir (junto a la entrada `"supersalud"`):

```python
    "ssf": (
        "Superintendencia del Subsidio Familiar",
        "Normativa (resoluciones y circulares externas) publicada por la "
        "Superintendencia del Subsidio Familiar",
    ),
```

Y en la zona de llamadas `repository.create_source_if_missing(...)` (después de la de `supersalud`), añadir:

```python
    repository.create_source_if_missing(
        db, family_key="ssf", name="Superintendencia del Subsidio Familiar", family_params={}
    )
```

- [ ] **Step 4: Apply the test_seed.py bumps**

En `tests/test_seed.py`:
- `assert len(families) == 22` → `assert len(families) == 23`
- ambas `assert len(sources) == 1 + 28 + 19 + 33 + 6` → `assert len(sources) == 1 + 28 + 20 + 33 + 6`
- el comentario `# ... + 19 (fuente única: corte_suprema, ..., superfinanciera, supersalud) + 33 ...` → `20 (fuente única: ..., supersalud, ssf)`
- en el set de `test_seed_populates_families_and_sources_and_is_idempotent`, añadir `"ssf",` después de `"supersalud",`

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/families/test_ssf.py tests/test_seed.py tests/test_registry.py -q`
Expected: PASS (todos). (`tests/test_seed.py` puede tardar por la BD; dale hasta ~150s.)

- [ ] **Step 6: Add the documentation note**

En `docs/guia-despliegue-sistemas.md`, en §10 "Notas por fuente", añadir:

```markdown
### Superintendencia del Subsidio Familiar (`ssf`)

Una sola fuente que raspa dos secciones del portal de la SSF:
**Resoluciones** y **Circulares Externas**. Cobertura desde 2024 (las
circulares anteriores a 2011 tienen enlaces de descarga que ya no
funcionan). Es un portal Liferay servido entero en HTML — sin API, sin
filtros. Los documentos se descargan de `www.ssf.gov.co/documents/d/guest/...`.

Títulos: `{C|R}_SSF_{número}_{año}`. Cuando el número no se puede
determinar, el documento entra con el título crudo y marca de "no
verificado".

**Fuente nueva:** después de actualizar producción hay que correr una vez
`docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.seed`
para que aparezca en el listado. Es seguro repetirlo.
```

Confirmar que §7 ("Actualizar a una versión nueva") ya menciona el paso de `core.seed` para fuentes nuevas (se añadió con la fuente anterior); si no está, añadir la misma línea ahí.

- [ ] **Step 7: Commit**

```bash
git add core/seed.py tests/test_seed.py docs/guia-despliegue-sistemas.md tests/families/test_ssf.py
git commit -m "feat(ssf): seed de la fuente + bump de conteos en test_seed + nota de despliegue"
```

---

## Task 5: Verificación completa y PR

**Files:** ninguno nuevo — corridas de verificación y apertura del PR.

- [ ] **Step 1: Suite enfocada + seed + registry**

Run: `.venv/Scripts/python -m pytest tests/families/ tests/test_seed.py tests/test_registry.py -q`
Expected: PASS. (`tests/families/` es rápido; `test_seed.py` tarda por la BD.)

- [ ] **Step 2: Import del registro**

Run: `.venv/Scripts/python -c "import core.scrapers.families; from core.scrapers.registry import FAMILY_REGISTRY; print(sorted(FAMILY_REGISTRY))"`
Expected: la lista incluye `'ssf'`.

- [ ] **Step 3: Seed idempotente contra la BD local**

Run: `.venv/Scripts/python -m core.seed` (dos veces)
Expected: corre sin error ambas veces. Verificar la fuente:

Run: `.venv/Scripts/python -c "from core.db.session import SessionLocal; from core.db import repository; db=SessionLocal(); print([s.name for s in repository.list_sources(db) if s.family_key=='ssf'])"`
Expected: `['Superintendencia del Subsidio Familiar']`.

- [ ] **Step 4: Smoke test en vivo end-to-end**

Repetir el smoke test del Task 3 Step 5 con `fini='2024-01-01' ffin='2026-12-31'` y confirmar que descarga: si el entorno de dev está levantado, disparar una corrida real desde la UI (`run-iurisync`) contra la fuente nueva y previsualizar al menos un documento.

- [ ] **Step 5: Push y PR**

```bash
git push -u origin feature/fuente-ssf
gh pr create --base master --title "feat(ssf): nueva fuente Superintendencia del Subsidio Familiar" --body "$(cat <<'EOF'
Nueva familia técnica `ssf`: raspa Resoluciones y Circulares Externas del
portal Liferay de la Superintendencia del Subsidio Familiar.

## Qué trae
- `core/scrapers/families/ssf.py` — familia nueva, arquetipo "tabla HTML"
  (como `mincit`): `requests.get` a dos URLs fijas servidas enteras en HTML,
  `BeautifulSoup` para parsear todas las tablas de datos por su encabezado,
  filtro por fecha en cliente. Sin paginación, sin API.
- Títulos `{C|R}_SSF_{nº:04d}_{año}` (conserva sufijo de letra: `C_SSF_0003A_2024`);
  `title_unverified` cuando el número no se puede parsear.
- Fecha de Resolución desde la prosa del Asunto (respaldo: fecha corta de Documento).
- Piso de cobertura 2024 (las circulares 2001-2010 tienen enlaces que devuelven 0 bytes).
- Anexos sin manejo especial (una fila = un documento).
- Seed: una fuente "Superintendencia del Subsidio Familiar". Sin migración.
- `tests/families/test_ssf.py` con fixtures HTML; bump de conteos canónicos en `tests/test_seed.py` (22→23).

## Spec y plan
- `docs/superpowers/specs/2026-09-07-fuente-ssf-design.md`
- `docs/superpowers/plans/2026-09-07-fuente-ssf.md`

## Verificación
- `pytest tests/families/ tests/test_seed.py tests/test_registry.py` verde.
- Smoke test en vivo contra ssf.gov.co: devuelve ambos tipos, fechas ≥ 2024, títulos canónicos.

## Despliegue
Fuente nueva: tras actualizar prod correr una vez `python -m core.seed` (vía `docker compose ... run --rm api`). Sin migración.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**1. Spec coverage:**

| Sección del spec | Task |
|---|---|
| Dos URLs fijas, HTML servido entero, sin paginación | Task 3 (`_SECCIONES`, `scrap`) |
| Selección de tablas de datos por encabezado, ignorar layout | Task 2 (`_tablas_de_datos`) + tests |
| Resolución: número del Asunto (respaldo Documento) | Task 1 (`_num_resolucion`) + tests |
| Resolución: fecha prosa del Asunto (respaldo fecha corta `DD-MM-YY`) | Task 1 (`_fecha_corta`) + Task 2 (`_fila_resolucion`) + tests |
| Circular: número de columna Número (quita `CE`, conserva sufijo letra) | Task 1 (`_num_circular`) + tests |
| Circular: fecha `DD/MM/YYYY` | Task 1 (`_fecha_slash`) + tests |
| Título `{letra}_SSF_{nº:04d}{sufijo}_{año}`; `title_unverified` con crudo | Task 1 (`_titulo`) + tests |
| Piso de cobertura 2024 + filtro por rango | Task 2 (`_armar_doc`) + tests |
| `href` relativo → `urljoin` con `_BASE` | Task 2 (`_armar_doc`, `_fila_*`) + test `link.url` |
| Anexos sin manejo especial | (n/a — no hay código de anexos) |
| `filters_by_publication_date = True`, otros flags por defecto | Task 3 (atributo de clase) + test |
| Resiliencia: una sección que falla no aborta la otra | Task 3 + test |
| `stop_event` y `limit` | Task 3 + tests |
| Seed: una fuente, `family_params={}`, sin `auto_review_status` | Task 4 + test |
| `tests/test_seed.py` bump (23 familias, 20 fuentes únicas, set con `ssf`) | Task 4 |
| Registro en `families/__init__.py` | Task 3 |
| Nota de documentación | Task 4 |
| Sin migración, sin frontend | (n/a — no hay task) |

Sin huecos.

**2. Placeholder scan:** Sin "TBD"/"TODO"/"manejar edge cases". El único paso manual (smoke test en vivo, Task 3 Step 5 / Task 5 Step 4) trae comando exacto y criterios de aceptación.

**3. Type consistency:**
- `_num_circular(celda) -> tuple[str,str] | None` — definido en Task 1, usado en Task 2 `_fila_circular` como `parsed = _num_circular(...); digitos, sufijo = parsed if parsed else (None, "")`.
- `_num_resolucion(asunto, documento) -> str | None` — definido en Task 1, usado en Task 2 `_fila_resolucion` y pasado a `_armar_doc` como `digitos` (con `sufijo=""`).
- `_titulo(letra, digitos, sufijo, anio, texto_crudo) -> tuple[str,bool]` — misma firma en Task 1 (def + tests) y en Task 2 (`_armar_doc` lo llama con esos 5 args).
- `_armar_doc(tipo, letra, digitos, sufijo, fecha, fini, ffin, asunto, texto_crudo, href) -> RawDocModel | None` — definido en Task 2, llamado por `_fila_resolucion` y `_fila_circular` con esos 10 args posicionales.
- `_fila_resolucion` / `_fila_circular` `(tr, fini, ffin, on_progress)` — definidos en Task 2, usados en Task 3 vía `fila_fn(tr, fini, ffin, on_progress)`.
- `_tablas_de_datos(soup, columnas)` — definido en Task 2, usado en Task 3.
- `_SECCIONES` tuplas de 4 (`url, tipo, letra, columnas`) — definido en Task 1, desempaquetado igual en Task 3.

Consistente.
