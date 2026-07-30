# Fuente MADR (Ministerio de Agricultura y Desarrollo Rural) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new scraper family `madr` that scrapes Leyes, Decretos, Resoluciones and Conpes from `https://www.minagricultura.gov.co/normatividad`, wired into the registry, the seed data, and the existing worker/frontend pipeline exactly like every other family.

**Architecture:** One new file `core/scrapers/families/madr.py` with a `ScrapMADR(BaseScrapper)` class registered under `@register_family("madr")`. It fetches one HTML page per category (no pagination — the site renders full history in a single response), parses `<article class="item_norm">` blocks with BeautifulSoup, resolves a 3-level date cascade from free-text titles, and normalizes titles to `{LETRA}_MADR_{numero:04d}_{año}`. One `Source` row is added to `core/seed.py` (`family_params={}`), no frontend changes needed.

**Tech Stack:** Python, `requests`, `beautifulsoup4`, `pytest`, `responses` (HTTP mocking) — all already used by `core/scrapers/families/mincit.py` and its tests, which this plan mirrors directly.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-30-fuente-minagricultura-design.md` — every rule below (date cascade, title format, error handling) traces back to it. Do not deviate without re-reading it.
- Scope is exactly 4 categories: `leyes`, `decretos`, `resoluciones`, `conpes`. Do not add `jurisprudencia`, `notificaciones`, `agenda-regulatoria`, `analisis-normativos`, or `proyectos-normativos` — they are explicitly out of scope.
- Base URL: `https://www.minagricultura.gov.co`.
- Title format: `{LETRA}_MADR_{numero:04d}_{año}` where `LETRA` is `L`/`D`/`R` for Ley/Decreto/Resolución, and the literal `CONPES` for Conpes (confirmed with the user — not a single letter).
- Only `f_public` is set (no `f_providencia` — the site exposes a single date per document). `filters_by_publication_date` stays at its `BaseScrapper` default (`False`).

---

### Task 1: Date-parsing and title-normalization helpers

**Files:**
- Create: `core/scrapers/families/madr.py`
- Test: `tests/families/test_madr.py`

**Interfaces:**
- Produces: `_MESES: dict[str, int]`, `_resto_tras_numero(data_title: str, numero: str) -> str`, `_parse_fecha(texto: str) -> Optional[str]` (returns `"YYYY-MM-DD"` or `None`), `_normalize_title(letra: str, numero: str, anio: str) -> str`.

These are pure functions with no I/O — the foundation the rest of the family builds on. `_parse_fecha` must handle 4 real, verified title-date shapes, tried in this order (first match wins):

1. `"{dia} [DE] {mes} DE[L] {año}"` — day-then-month, with or without the connecting "DE" (site is inconsistent): `"DECRETO 0765 DEL 15 DE JULIO DEL 2026"`, `"RESOLUCION 000247 DEL 27 JULIO DE 2026"`.
2. `"DE {mes} {dia} DE {año}"` — month-then-day: `"RESOLUCION 000179 DE MAYO 4 DE 2026"`.
3. `"DE {mes} DE {año}"` — month + year, no day: `"LEY 2337 DE OCTUBRE DE 2023"`.
4. `"DE {año}"` — year only: `"LEY 2311 DE 2023"`, always for Conpes: `"CONPES 4076 DE 2022"`.

**Why `_resto_tras_numero` exists (critical — do not skip):** the act number (e.g. `2321` in `"LEY 2321 DE SEPTIEMBRE DE 2023"`) sits right before the date phrase. If the date regexes run on the full title, the number's own trailing digits can be misread as a day: `"2321 DE SEPTIEMBRE DE 2023"` naively matches level 1 with day=`21` (a plausible day!), producing the wrong date `2023-09-21` instead of the correct `2023-09-01` (this title has no real day — only month+year). `_resto_tras_numero` slices the title to only what comes *after* the known `data-number` value, so the date regexes never see the act number's digits at all. Always call `_parse_fecha(_resto_tras_numero(data_title, numero))`, never `_parse_fecha(data_title)` directly, when `numero` is non-empty.

- [ ] **Step 1: Write the failing tests for `_resto_tras_numero` and `_normalize_title`**

```python
# tests/families/test_madr.py
from core.scrapers.families.madr import _normalize_title, _resto_tras_numero


def test_resto_tras_numero_strips_everything_up_to_and_including_the_number():
    assert _resto_tras_numero("DECRETO 0765 DEL 15 DE JULIO DEL 2026", "0765") == " DEL 15 DE JULIO DEL 2026"


def test_resto_tras_numero_avoids_reading_the_act_number_as_a_day():
    # Sin este recorte, "21" (los últimos dos dígitos de "2321") se leería
    # como un día válido y produciría "2023-09-21" en vez de "2023-09-01".
    assert _resto_tras_numero("LEY 2321 DE SEPTIEMBRE DE 2023", "2321") == " DE SEPTIEMBRE DE 2023"


def test_resto_tras_numero_returns_full_text_when_number_not_found():
    assert _resto_tras_numero("Documento sin número reconocible", "9999") == "Documento sin número reconocible"


def test_normalize_title_builds_canonical_code():
    assert _normalize_title("D", "765", "2026") == "D_MADR_0765_2026"


def test_normalize_title_pads_short_numbers_to_four_digits():
    assert _normalize_title("R", "179", "2026") == "R_MADR_0179_2026"


def test_normalize_title_uses_conpes_literal_instead_of_a_single_letter():
    assert _normalize_title("CONPES", "4076", "2022") == "CONPES_MADR_4076_2022"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/families/test_madr.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.scrapers.families.madr'`

- [ ] **Step 3: Create `core/scrapers/families/madr.py` with the module scaffolding and these two functions**

```python
import re
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE_URL = "https://www.minagricultura.gov.co"

# slug de categoría -> (tipo mostrado, letra del código de título)
_CATEGORIAS = {
    "leyes": ("Ley", "L"),
    "decretos": ("Decreto", "D"),
    "resoluciones": ("Resolución", "R"),
    "conpes": ("Conpes", "CONPES"),
}

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')


def _resto_tras_numero(data_title: str, numero: str) -> str:
    idx = data_title.find(numero)
    if idx == -1:
        return data_title
    return data_title[idx + len(numero):]


def _normalize_title(letra: str, numero: str, anio: str) -> str:
    return f"{letra}_MADR_{int(numero):04d}_{anio}"
```

- [ ] **Step 4: Run tests to verify `_resto_tras_numero` and `_normalize_title` tests pass**

Run: `pytest tests/families/test_madr.py -v`
Expected: 3 PASS (`_resto_tras_numero`/`_normalize_title` tests), rest still failing on `_parse_fecha`/`_MESES` import.

- [ ] **Step 5: Write the failing tests for `_parse_fecha`, covering all 4 real date shapes plus the collision regression**

```python
from core.scrapers.families.madr import _parse_fecha


def test_parse_fecha_dia_de_mes_del_anio():
    assert _parse_fecha(" DEL 15 DE JULIO DEL 2026") == "2026-07-15"


def test_parse_fecha_dia_mes_sin_conector_de():
    # Variante real sin "DE" entre día y mes: "DEL 27 JULIO DE 2026".
    assert _parse_fecha(" DEL 27 JULIO DE 2026") == "2026-07-27"


def test_parse_fecha_mes_dia_anio_orden_invertido():
    # Variante real con mes antes del día: "DE MAYO 4 DE 2026".
    assert _parse_fecha(" DE MAYO 4 DE 2026") == "2026-05-04"


def test_parse_fecha_mes_anio_sin_dia():
    assert _parse_fecha(" DE OCTUBRE DE 2023") == "2023-10-01"


def test_parse_fecha_solo_anio():
    assert _parse_fecha(" DE 2023") == "2023-01-01"


def test_parse_fecha_conpes_siempre_solo_anio():
    assert _parse_fecha(" DE 2022") == "2022-01-01"


def test_parse_fecha_returns_none_when_no_date_found():
    assert _parse_fecha("texto sin fecha reconocible") is None


def test_parse_fecha_is_case_insensitive():
    assert _parse_fecha(" del 19 de mayo de 2023") == "2023-05-19"


def test_parse_fecha_does_not_misread_trailing_act_number_digits_as_a_day():
    # Regresión del caso documentado en _resto_tras_numero: si a _parse_fecha
    # se le pasara el título completo en vez del resto ya recortado, "21" (de
    # "2321") se leería como día. Aquí se prueba directamente sobre el resto
    # ya recortado, que es como _extraer_articulos debe invocarlo siempre.
    resto = _resto_tras_numero("LEY 2321 DE SEPTIEMBRE DE 2023", "2321")
    assert _parse_fecha(resto) == "2023-09-01"
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `pytest tests/families/test_madr.py -v`
Expected: FAIL with `ImportError: cannot import name '_parse_fecha'`

- [ ] **Step 7: Add `_MESES` and the date cascade to `core/scrapers/families/madr.py`**

Append after `_INVALID_PATH_CHARS`:

```python
_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_MESES_ALT = "|".join(_MESES.keys())

# Nivel 1: "{dia} [DE] {mes} DE[L] {año}" — el sitio a veces omite el "DE"
# entre día y mes ("DEL 27 JULIO DE 2026") y a veces lo incluye ("DEL 15 DE
# JULIO DEL 2026"); ambas formas comparten este patrón porque "DE" es opcional.
_FECHA_DIA_MES_ANIO = re.compile(
    rf"(\d{{1,2}})\s+(?:DE\s+)?({_MESES_ALT})\s+DEL?\s+(\d{{4}})\s*$", re.IGNORECASE
)
# Nivel 2: "DE {mes} {dia} DE {año}" — orden mes-día invertido, visto en
# Resoluciones ("DE MAYO 4 DE 2026").
_FECHA_MES_DIA_ANIO = re.compile(
    rf"DE\s+({_MESES_ALT})\s+(\d{{1,2}})\s+DE\s+(\d{{4}})\s*$", re.IGNORECASE
)
# Nivel 3: "DE {mes} DE {año}" — mes y año sin día (ej. Leyes: "DE OCTUBRE DE 2023").
_FECHA_MES_ANIO = re.compile(rf"DE\s+({_MESES_ALT})\s+DE\s+(\d{{4}})\s*$", re.IGNORECASE)
# Nivel 4: "DE {año}" — solo año. Siempre es el caso de Conpes.
_FECHA_ANIO = re.compile(r"DE\s+(\d{4})\s*$", re.IGNORECASE)


def _parse_fecha(texto: str) -> Optional[str]:
    m = _FECHA_DIA_MES_ANIO.search(texto)
    if m:
        dia, mes_nombre, anio = m.groups()
        if 1 <= int(dia) <= 31:
            return f"{anio}-{_MESES[mes_nombre.lower()]:02d}-{int(dia):02d}"

    m = _FECHA_MES_DIA_ANIO.search(texto)
    if m:
        mes_nombre, dia, anio = m.groups()
        if 1 <= int(dia) <= 31:
            return f"{anio}-{_MESES[mes_nombre.lower()]:02d}-{int(dia):02d}"

    m = _FECHA_MES_ANIO.search(texto)
    if m:
        mes_nombre, anio = m.groups()
        return f"{anio}-{_MESES[mes_nombre.lower()]:02d}-01"

    m = _FECHA_ANIO.search(texto)
    if m:
        return f"{m.group(1)}-01-01"

    return None
```

The `1 <= int(dia) <= 31` guards on levels 1-2 exist so that if a caller ever
passes the *full* title (numero not stripped) and the numero's own digits
happen to fall in range and touch a `DE {mes}` phrase, an out-of-range day
(e.g. `37`) falls through to the next level instead of producing an invalid
date string — a safety net, not a substitute for calling
`_resto_tras_numero` first.

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/families/test_madr.py -v`
Expected: All PASS.

- [ ] **Step 9: Commit**

```bash
git add core/scrapers/families/madr.py tests/families/test_madr.py
git commit -m "feat: agrega parseo de fecha y normalización de título para familia madr"
```

---

### Task 2: Article extraction (`ScrapMADR._extraer_articulos`)

**Files:**
- Modify: `core/scrapers/families/madr.py`
- Modify: `core/scrapers/families/__init__.py:1`
- Test: `tests/families/test_madr.py`

**Interfaces:**
- Consumes: `_resto_tras_numero`, `_parse_fecha`, `_normalize_title`, `_CATEGORIAS`, `_INVALID_PATH_CHARS` (Task 1), `RawDocModel`, `BaseScrapper`, `register_family`, `storage_path` (already imported in Task 1).
- Produces: `ScrapMADR(BaseScrapper)` class registered as `"madr"`, with `self.source = "Ministerio de Agricultura y Desarrollo Rural"` and method `_extraer_articulos(self, html: str, tipo: str, letra: str, fini: str, ffin: str, on_progress=None) -> List[RawDocModel]`. `scrap()` is added in Task 3 — until then it's fine for the class to only have `_extraer_articulos`.

**Critical, easy-to-miss step:** `core/scrapers/families/__init__.py` currently reads:

```python
from . import constitucional, samai, corte_suprema, jep, cndj, adr, adres, ane, anh, rama_judicial, mincit  # noqa: F401
```

`@register_family("madr")` only runs — and only populates `FAMILY_REGISTRY` — when `core.scrapers.families.madr` is actually imported somewhere. Every existing family is imported here for exactly that reason. If `madr` is not added to this line, `_normalize_title`/`_parse_fecha` unit tests still pass (they import the module directly), but `test_madr_is_registered_under_its_family_key` below fails, and — more importantly — the real app never registers `"madr"` at startup, so `resolve_scraper("madr", {})` raises `ValueError` at run time even though the seed (Task 4) created a `Source` row for it. This must be updated in this task, not deferred.

- [ ] **Step 1: Write the failing tests for `_extraer_articulos`**

```python
from core.scrapers.registry import FAMILY_REGISTRY
from core.scrapers.families.madr import ScrapMADR


def test_madr_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["madr"].__name__ == "ScrapMADR"


_ARTICULO_DECRETO_HTML = """
<div class="cnt_normas container-fluid p-0">
<article class="col-12 pb-5 item_norm"
    data-title="DECRETO 0765 DEL 15 DE JULIO DEL 2026"
    data-info="&quot;Por el cual se adicionan los decretos 1071 del 2015&quot;"
    data-year="2026"
    data-number="0765"
    data-link="t3://file?uid=14012"
    data-content="">
    <div class="cnt_item_norm">
        <h3>
            <a itemprop="url" href="/fileadmin/normatividad/decretos/DECRETO_No._0765_DEL_15_DE_JULIO_DE_2026.pdf">
                <span itemprop="headline">DECRETO 0765 DEL 15 DE JULIO DEL 2026</span>
            </a>
        </h3>
    </div>
</article>
</div>
"""


def test_extraer_articulos_parses_article_and_builds_canonical_title():
    scraper = ScrapMADR()
    docs = scraper._extraer_articulos(_ARTICULO_DECRETO_HTML, "Decreto", "D", "2026-01-01", "2026-12-31")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "D_MADR_0765_2026"
    assert doc.title_unverified is False
    assert doc.tipo == "Decreto"
    assert doc.f_public == "2026-07-15"
    assert doc.f_providencia is None
    assert doc.detalle == "Por el cual se adicionan los decretos 1071 del 2015"
    assert doc.link["url"] == (
        "https://www.minagricultura.gov.co/fileadmin/normatividad/decretos/"
        "DECRETO_No._0765_DEL_15_DE_JULIO_DE_2026.pdf"
    )
    assert doc.save_path == "Ministerio de Agricultura y Desarrollo Rural/2026-07-15/Decreto/D_MADR_0765_2026(extension)"


def test_extraer_articulos_filters_out_of_range_dates():
    scraper = ScrapMADR()
    docs = scraper._extraer_articulos(_ARTICULO_DECRETO_HTML, "Decreto", "D", "2020-01-01", "2020-12-31")

    assert docs == []


_ARTICULO_CONPES_SIN_DIA_HTML = """
<article class="col-12 pb-5 item_norm"
    data-title="CONPES 4076 DE 2022"
    data-info="Política Pública de equidad de género para las mujeres."
    data-year="2022"
    data-number="4076"
    data-link="t3://file?uid=281"
    data-content="">
    <div class="cnt_item_norm">
        <h3>
            <a itemprop="url" href="/fileadmin/normatividad/conpes/CONPES_4076_DE_2022.pdf">
                <span itemprop="headline">CONPES 4076 DE 2022</span>
            </a>
        </h3>
    </div>
</article>
"""


def test_extraer_articulos_conpes_uses_year_only_and_conpes_literal():
    scraper = ScrapMADR()
    docs = scraper._extraer_articulos(_ARTICULO_CONPES_SIN_DIA_HTML, "Conpes", "CONPES", "2022-01-01", "2022-12-31")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "CONPES_MADR_4076_2022"
    assert doc.f_public == "2022-01-01"


def test_extraer_articulos_marks_title_unverified_when_no_data_number():
    html = _ARTICULO_DECRETO_HTML.replace('data-number="0765"', 'data-number=""')
    scraper = ScrapMADR()
    docs = scraper._extraer_articulos(html, "Decreto", "D", "2026-01-01", "2026-12-31")

    assert len(docs) == 1
    assert docs[0].title == "DECRETO 0765 DEL 15 DE JULIO DEL 2026"
    assert docs[0].title_unverified is True


def test_extraer_articulos_sanitizes_title_unverified_for_save_path():
    html = _ARTICULO_DECRETO_HTML.replace('data-number="0765"', 'data-number=""').replace(
        'data-title="DECRETO 0765 DEL 15 DE JULIO DEL 2026"',
        'data-title="Documento/con &quot;caracteres&quot;: raros|del 15 de julio de 2026"',
    ).replace(
        '<span itemprop="headline">DECRETO 0765 DEL 15 DE JULIO DEL 2026</span>',
        '<span itemprop="headline">Documento/con "caracteres": raros|del 15 de julio de 2026</span>',
    )
    scraper = ScrapMADR()
    docs = scraper._extraer_articulos(html, "Decreto", "D", "2026-01-01", "2026-12-31")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title_unverified is True
    segmentos = doc.save_path.split("/")
    assert len(segmentos) == 4
    ultimo_segmento = segmentos[-1]
    assert not any(c in ultimo_segmento for c in '\\/*?:"<>|')


def test_extraer_articulos_skips_article_without_download_link():
    html = _ARTICULO_DECRETO_HTML.replace(
        '<a itemprop="url" href="/fileadmin/normatividad/decretos/DECRETO_No._0765_DEL_15_DE_JULIO_DE_2026.pdf">',
        '<a>',
    )
    scraper = ScrapMADR()
    docs = scraper._extraer_articulos(html, "Decreto", "D", "2026-01-01", "2026-12-31")

    assert docs == []


def test_extraer_articulos_skips_article_without_any_parseable_date():
    html = _ARTICULO_DECRETO_HTML.replace(
        'data-title="DECRETO 0765 DEL 15 DE JULIO DEL 2026"',
        'data-title="DECRETO SIN FECHA RECONOCIBLE"',
    ).replace(
        '<span itemprop="headline">DECRETO 0765 DEL 15 DE JULIO DEL 2026</span>',
        '<span itemprop="headline">DECRETO SIN FECHA RECONOCIBLE</span>',
    )
    scraper = ScrapMADR()
    docs = scraper._extraer_articulos(html, "Decreto", "D", "2026-01-01", "2026-12-31")

    assert docs == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/families/test_madr.py -v`
Expected: FAIL — `ScrapMADR` doesn't exist yet.

- [ ] **Step 3: Add the class and `_extraer_articulos` to `core/scrapers/families/madr.py`**

Append at the end of the file:

```python
@register_family("madr")
class ScrapMADR(BaseScrapper):
    def __init__(self):
        self.source = "Ministerio de Agricultura y Desarrollo Rural"

    def _extraer_articulos(self, html: str, tipo: str, letra: str, fini: str, ffin: str, on_progress=None) -> List[RawDocModel]:
        docs: List[RawDocModel] = []
        soup = BeautifulSoup(html, "html.parser")

        for art in soup.find_all("article", class_="item_norm"):
            data_title = (art.get("data-title") or "").strip()
            numero = (art.get("data-number") or "").strip()
            detalle = (art.get("data-info") or "").strip() or None
            if detalle:
                detalle = detalle.strip('"')

            enlace = art.find("a", href=True)
            if not enlace:
                continue
            url = urljoin(_BASE_URL, enlace["href"])

            resto = _resto_tras_numero(data_title, numero) if numero else data_title
            fecha = _parse_fecha(resto)
            if fecha is None:
                if on_progress:
                    on_progress(f"[{self.source}] Aviso: no se pudo determinar fecha para «{data_title}», se omite")
                continue
            if fecha < fini or fecha > ffin:
                continue

            if numero:
                title = _normalize_title(letra, numero, fecha[:4])
                title_unverified = False
            else:
                title = data_title
                title_unverified = True

            safe_title = _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")

            docs.append(RawDocModel(
                source=self.source,
                link={"url": url, "method": "GET"},
                title=title,
                tipo=tipo,
                f_public=fecha,
                detalle=detalle,
                save_path=storage_path(self.source, fecha, tipo, f"{safe_title}(extension)"),
                title_unverified=title_unverified,
            ))

        return docs
```

- [ ] **Step 4: Add `madr` to `core/scrapers/families/__init__.py`**

Change `core/scrapers/families/__init__.py:1` from:
```python
from . import constitucional, samai, corte_suprema, jep, cndj, adr, adres, ane, anh, rama_judicial, mincit  # noqa: F401
```
to:
```python
from . import constitucional, samai, corte_suprema, jep, cndj, adr, adres, ane, anh, rama_judicial, mincit, madr  # noqa: F401
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/families/test_madr.py -v`
Expected: All PASS, including `test_madr_is_registered_under_its_family_key`.

- [ ] **Step 6: Commit**

```bash
git add core/scrapers/families/madr.py core/scrapers/families/__init__.py tests/families/test_madr.py
git commit -m "feat: agrega parseo de artículos y registro de la familia madr"
```

---

### Task 3: `scrap()` orchestration across the 4 categories

**Files:**
- Modify: `core/scrapers/families/madr.py`
- Test: `tests/families/test_madr.py`

**Interfaces:**
- Consumes: `ScrapMADR._extraer_articulos`, `_CATEGORIAS` (Task 1/2).
- Produces: `ScrapMADR.scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]` — the method `BaseScrapper` requires and the worker calls.

- [ ] **Step 1: Write the failing tests for `scrap()`**

```python
import responses

_PAGINA_LEYES_HTML = """
<article class="col-12 pb-5 item_norm" data-title="LEY 2311 DE 2023" data-year="2023" data-number="2311">
  <div class="cnt_item_norm"><h3><a itemprop="url" href="/fileadmin/normatividad/leyes/LEY_2311_DE_2023.pdf">x</a></h3></div>
</article>
"""

_PAGINA_DECRETOS_HTML = """
<article class="col-12 pb-5 item_norm" data-title="DECRETO 0212 DEL 5 DE MARZO DE 2023" data-year="2023" data-number="0212">
  <div class="cnt_item_norm"><h3><a itemprop="url" href="/fileadmin/normatividad/decretos/DECRETO_0212.pdf">x</a></h3></div>
</article>
"""

_PAGINA_VACIA_HTML = "<div class=\"news\"></div>"


@responses.activate
def test_scrap_aggregates_across_the_four_categories():
    responses.add(responses.GET, "https://www.minagricultura.gov.co/normatividad/leyes", body=_PAGINA_LEYES_HTML)
    responses.add(responses.GET, "https://www.minagricultura.gov.co/normatividad/decretos", body=_PAGINA_DECRETOS_HTML)
    responses.add(responses.GET, "https://www.minagricultura.gov.co/normatividad/resoluciones", body=_PAGINA_VACIA_HTML)
    responses.add(responses.GET, "https://www.minagricultura.gov.co/normatividad/conpes", body=_PAGINA_VACIA_HTML)

    scraper = ScrapMADR()
    docs = scraper.scrap(fini="2023-01-01", ffin="2023-12-31")

    assert {d.title for d in docs} == {"L_MADR_2311_2023", "D_MADR_0212_2023"}


@responses.activate
def test_scrap_continues_past_a_failing_category():
    responses.add(responses.GET, "https://www.minagricultura.gov.co/normatividad/leyes", body=_PAGINA_LEYES_HTML)
    responses.add(responses.GET, "https://www.minagricultura.gov.co/normatividad/decretos", status=500)
    responses.add(responses.GET, "https://www.minagricultura.gov.co/normatividad/resoluciones", body=_PAGINA_VACIA_HTML)
    responses.add(responses.GET, "https://www.minagricultura.gov.co/normatividad/conpes", body=_PAGINA_VACIA_HTML)

    progreso = []
    scraper = ScrapMADR()
    docs = scraper.scrap(fini="2023-01-01", ffin="2023-12-31", on_progress=progreso.append)

    assert {d.title for d in docs} == {"L_MADR_2311_2023"}
    assert any("Error" in m and "decretos" in m for m in progreso)


@responses.activate
def test_scrap_respects_limit():
    responses.add(responses.GET, "https://www.minagricultura.gov.co/normatividad/leyes", body=_PAGINA_LEYES_HTML)
    responses.add(responses.GET, "https://www.minagricultura.gov.co/normatividad/decretos", body=_PAGINA_DECRETOS_HTML)
    responses.add(responses.GET, "https://www.minagricultura.gov.co/normatividad/resoluciones", body=_PAGINA_VACIA_HTML)
    responses.add(responses.GET, "https://www.minagricultura.gov.co/normatividad/conpes", body=_PAGINA_VACIA_HTML)

    scraper = ScrapMADR()
    docs = scraper.scrap(fini="2023-01-01", ffin="2023-12-31", limit=1)

    assert len(docs) == 1


def test_filters_by_publication_date_stays_at_default_false():
    assert ScrapMADR.filters_by_publication_date is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/families/test_madr.py -v`
Expected: FAIL with `AttributeError: 'ScrapMADR' object has no attribute 'scrap'`

- [ ] **Step 3: Add `scrap()` to `ScrapMADR`**

Append as a method of `ScrapMADR`, after `_extraer_articulos`:

```python
    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        docs: List[RawDocModel] = []
        for categoria, (tipo, letra) in _CATEGORIAS.items():
            if stop_event is not None and stop_event.is_set():
                return docs
            if on_progress:
                on_progress(f"[{self.source}] Procesando {tipo}...")

            try:
                resp = session.get(f"{_BASE_URL}/normatividad/{categoria}", timeout=30)
                resp.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{self.source}] Error consultando {categoria}: {e}")
                continue

            docs.extend(self._extraer_articulos(resp.text, tipo, letra, fini, ffin, on_progress=on_progress))
            if len(docs) >= limit:
                return docs[:limit]

        return docs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/families/test_madr.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/madr.py tests/families/test_madr.py
git commit -m "feat: agrega scrap() de la familia madr sobre las 4 categorías"
```

---

### Task 4: Seed wiring

**Files:**
- Modify: `core/seed.py:6-33` (`_FAMILIES` dict), `core/seed.py:88-90` (end of `seed_source_families_and_sources`)
- Modify: `tests/test_seed.py`

**Interfaces:**
- Consumes: `repository.create_source_family_if_missing`, `repository.create_source_if_missing` (already imported in `core/seed.py`).
- Produces: a `"madr"` row in `SourceFamily` and one `Source` row named `"Ministerio de Agricultura y Desarrollo Rural"` — this is what makes the family show up in the frontend exactly like the other 11.

- [ ] **Step 1: Update the failing assertions in `tests/test_seed.py` first**

In `test_seed_populates_families_and_sources_and_is_idempotent` (`tests/test_seed.py:53-66`), change:

```python
    assert {f.key for f in families} == {
        "constitucional", "samai", "corte_suprema", "jep", "cndj",
        "adr", "adres", "ane", "anh", "rama_judicial", "mincit",
    }
```
to:
```python
    assert {f.key for f in families} == {
        "constitucional", "samai", "corte_suprema", "jep", "cndj",
        "adr", "adres", "ane", "anh", "rama_judicial", "mincit", "madr",
    }
```

and change:
```python
    sources = repository.list_sources(db_session)
    # 1 (Corte Constitucional) + 28 (SAMAI) + 8 (fuente única: corte_suprema, jep, cndj,
    # adr, adres, ane, anh, mincit) + 33 (Tribunales Superiores, incl. Bogotá D.C.) + 6 (tipos de Juzgado) = 76
    assert len(sources) == 1 + 28 + 8 + 33 + 6
```
to:
```python
    sources = repository.list_sources(db_session)
    # 1 (Corte Constitucional) + 28 (SAMAI) + 9 (fuente única: corte_suprema, jep, cndj,
    # adr, adres, ane, anh, mincit, madr) + 33 (Tribunales Superiores, incl. Bogotá D.C.) + 6 (tipos de Juzgado) = 77
    assert len(sources) == 1 + 28 + 9 + 33 + 6
```

In `test_seed_running_concurrently_does_not_crash_or_duplicate_rows` (`tests/test_seed.py:44-48`), change:
```python
        families = repository.list_source_families(assertion_session)
        assert len(families) == 11

        sources = repository.list_sources(assertion_session, limit=500)
        assert len(sources) == 1 + 28 + 8 + 33 + 6
```
to:
```python
        families = repository.list_source_families(assertion_session)
        assert len(families) == 12

        sources = repository.list_sources(assertion_session, limit=500)
        assert len(sources) == 1 + 28 + 9 + 33 + 6
```

- [ ] **Step 2: Run the seed tests to verify they fail**

Run: `pytest tests/test_seed.py -v`
Expected: FAIL — counts are off by one family / one source (madr not seeded yet).

- [ ] **Step 3: Add the `madr` entry to `core/seed.py`**

In `_FAMILIES` (`core/seed.py:6-33`), add after the `"mincit"` entry:

```python
    "madr": (
        "Ministerio de Agricultura y Desarrollo Rural",
        "Normativa (leyes, decretos, resoluciones, conpes) publicada por el Ministerio de Agricultura y Desarrollo Rural",
    ),
```

At the end of `seed_source_families_and_sources` (`core/seed.py:88-90`), add after the `mincit` call:

```python
    repository.create_source_if_missing(
        db, family_key="madr", name="Ministerio de Agricultura y Desarrollo Rural", family_params={}
    )
```

- [ ] **Step 4: Run the seed tests to verify they pass**

Run: `pytest tests/test_seed.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add core/seed.py tests/test_seed.py
git commit -m "feat: agrega la fuente madr al seed de familias y fuentes"
```

---

### Task 5: Full verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full family test file**

Run: `pytest tests/families/test_madr.py -v`
Expected: All PASS (should be ~28 tests across the three prior tasks).

- [ ] **Step 2: Run the full test suite to confirm no regressions**

Run: `pytest`
Expected: All PASS, no failures introduced in unrelated files.

- [ ] **Step 3: Manually sanity-check the live site once (not mocked) to confirm the real page still matches the fixtures**

```bash
python -c "
from core.scrapers.families.madr import ScrapMADR
s = ScrapMADR()
docs = s.scrap(fini='2026-01-01', ffin='2026-12-31', limit=5, on_progress=print)
for d in docs:
    print(d.title, d.tipo, d.f_public, d.title_unverified)
"
```
Expected: prints up to 5 real documents with clean, non-`title_unverified` titles in the `X_MADR_NNNN_2026` / `CONPES_MADR_NNNN_2026` shape. If any real document comes back with `title_unverified=True` or a suspicious date, stop and investigate before moving on — it means the site has a title/date shape not covered by Task 1's cascade.

- [ ] **Step 4: Commit if Step 3 required any fixes, otherwise no commit needed for this task**
