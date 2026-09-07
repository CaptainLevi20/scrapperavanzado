# Fuente SNR — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir la fuente "Superintendencia de Notariado y Registro" (familia técnica `snr`) que raspa Circulares y Resoluciones del portal WordPress de la SNR.

**Architecture:** Un módulo plano `core/scrapers/families/snr.py` con `@register_family("snr")`. El sitio no tiene paginación en su listado, así que la enumeración usa una búsqueda `POST r=<texto>` al URL de cada categoría, con recursión adaptativa por prefijo del código de norma (`CIR-YYYY-NNNNNN` / `RES-YYYY-NNNNNN`) cuando la búsqueda por año devuelve más de lo que muestra (~20). Los PDF se descargan directo de `servicios.supernotariado.gov.co/files/…`.

**Tech Stack:** Python, `requests`, `beautifulsoup4` (`bs4`), `pytest`, `responses`. `core/fecha_es.parse_fecha_providencia_es` para la fecha en prosa. `core/downloader.py` resuelve la extensión.

**Spec:** `docs/superpowers/specs/2026-09-07-fuente-snr-design.md`

## Global Constraints

- **Sigla de entidad en el título:** `SNR` (verbatim).
- **Formato de título:** `{letra}_SNR_{numero:04d}_{anio}` con `letra` = `C` (Circular) / `R` (Resolución); `numero` = consecutivo del código (`000348` → 348; Resoluciones llega a 5 dígitos como `21492` — `:04d` NO recorta); `anio` = año del código.
- **Código de norma:** `(CIR|RES)-<4 díg año>-<6 díg consecutivo>-<1 díg>`. Sin código con esa forma → `title_unverified = True` con el texto crudo del título (o `"documento"` si vacío), recortado a 120.
- **Fecha:** `parse_fecha_providencia_es(<texto del <a>>)` (prosa `"del 03 de septiembre del 2026"`); respaldo = la fecha ISO tras `Publicación:`; si ninguna → descartar la tarjeta con aviso `on_progress` que contenga `"sin fecha"`.
- **Piso de cobertura:** `_ANIO_MIN = 2015`. Descartar tarjetas con `fecha.year < 2015`. El rango pedido acota además.
- **Solo tarjetas con `<a href>` en `div.contenido_download`.** Las `<li>` sin `<a>` ("notificación por aviso") se cuentan y se omiten.
- **Categorías:** `circulares` (minúscula) y `Resoluciones` (mayúscula inicial). Nada más.
- **Flags `BaseScrapper`:** `filters_by_publication_date = True`; los otros dos por defecto.
- **`review_status`:** por defecto (`pending`). Sin `auto_review_status` en el seed.
- **`_UMBRAL = 18`** — tope de tarjetas que el listado/búsqueda muestra sin paginación.
- **`tests/test_seed.py`** lleva conteos canónicos: `len(families)` 23→**24**; el set de claves de `test_seed_populates_families_and_sources_and_is_idempotent` gana `"snr"`; las dos aserciones `assert len(sources) == 1 + 28 + 20 + 33 + 6` pasan a `1 + 28 + 21 + 33 + 6` (con su comentario). Ver `memory/dev_env_gotchas`.
- Ejecutar Python con `.venv/Scripts/python` / `.venv/Scripts/pytest` (Git Bash en Windows nativo).
- **Gate de test por tarea = suite enfocada**, NO `pytest -q` completo: `.venv/Scripts/python -m pytest tests/families/test_snr.py tests/families/test_mincit.py -q`. La suite completa corre en CI sobre el PR.

---

## File Structure

- **Create `core/scrapers/families/snr.py`** — la familia completa: constantes + `_CATEGORIAS`, helpers de parseo (`_parse_codigo`, `_titulo`, `_safe_title`, `_resultados_total`), parseo de tarjetas (`_tarjetas`) y mapeo (`_tarjeta_a_doc`), transporte + enumeración (`_buscar`, `_enumerar_categoria` con su recursión `_bloque`), y la clase `ScrapSNR`. Módulo plano, ~230 líneas, estilo `core/scrapers/families/mincit.py`.
- **Modify `core/scrapers/families/__init__.py`** — añadir `snr` a la línea de import.
- **Modify `core/seed.py`** — entrada en `_FAMILIES` + una llamada `repository.create_source_if_missing(...)`.
- **Modify `tests/test_seed.py`** — los tres bumps de conteo (23→24 familias).
- **Create `tests/families/test_snr.py`** — unit tests de helpers + tarjetas + mapeo + enumeración con `responses`.
- **Modify `docs/guia-despliegue-sistemas.md`** — nota de la fuente nueva (§10).

---

## Task 1: Helpers de parseo (código, título, fecha-total, saneo) + constantes

**Files:**
- Create: `core/scrapers/families/snr.py`
- Test: `tests/families/test_snr.py`

**Interfaces:**
- Produces:
  - `_safe_title(title: str) -> str`
  - `_parse_codigo(texto: str) -> tuple[str, int, int] | None` — `(letra, numero, anio)` desde `"CIR-2026-000348-4 …"` → `("C", 348, 2026)`
  - `_titulo(codigo: tuple | None, texto_crudo: str) -> tuple[str, bool]` — `(title, title_unverified)`
  - `_resultados_total(html: str) -> int` — el número tras `"Resultados "` (sin `.`/`,`); `-1` si no aparece
- Constantes: `_BASE`, `_SOURCE`, `_UA`, `_UMBRAL` (18), `_ANIO_MIN` (2015), `_CATEGORIAS` (lista de `(segmento_url, tipo, letra)`).

- [ ] **Step 1: Write the failing tests**

Create `tests/families/test_snr.py`:

```python
from core.scrapers.families.snr import (
    _parse_codigo,
    _resultados_total,
    _safe_title,
    _titulo,
)


# ---- _parse_codigo ----
def test_parse_codigo_circular():
    assert _parse_codigo('CIR-2026-000348-4 del 03 de septiembre del 2026 "x"') == ("C", 348, 2026)


def test_parse_codigo_resolucion_five_digit_consecutive():
    assert _parse_codigo('RES-2026-021492-6 del 20 de agosto de 2026 "x"') == ("R", 21492, 2026)


def test_parse_codigo_none_for_old_format():
    assert _parse_codigo("RES.445-2019EXPTE.407-2017") is None
    assert _parse_codigo("Circular informativa sin código") is None
    assert _parse_codigo("") is None


# ---- _titulo ----
def test_titulo_verified_circular():
    assert _titulo(("C", 348, 2026), "irrelevante") == ("C_SNR_0348_2026", False)


def test_titulo_verified_resolucion_keeps_five_digits():
    assert _titulo(("R", 21492, 2026), "irrelevante") == ("R_SNR_21492_2026", False)


def test_titulo_unverified_keeps_raw_trimmed():
    title, unv = _titulo(None, "RES.445-2019 texto libre del sitio")
    assert unv is True
    assert title == "RES.445-2019 texto libre del sitio"


def test_titulo_unverified_empty_falls_back_to_documento():
    assert _titulo(None, "   ") == ("documento", True)


# ---- _resultados_total ----
def test_resultados_total_reads_and_strips_separators():
    assert _resultados_total("<div>Resultados 355</div>") == 355
    assert _resultados_total("Resultados 10.901 circulares") == 10901
    assert _resultados_total("Resultados 2,634") == 2634


def test_resultados_total_minus_one_when_absent():
    assert _resultados_total("<html>sin conteo</html>") == -1


# ---- _safe_title ----
def test_safe_title_sanitizes_and_trims():
    assert _safe_title('Doc/con "raros": x|y*  .') == "Doc-con -raros-- x-y-"
    assert len(_safe_title("z" * 300)) == 120
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/families/test_snr.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write the module with the helpers**

Create `core/scrapers/families/snr.py`:

```python
import datetime
import re
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.fecha_es import parse_fecha_providencia_es
from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE = "https://www.supernotariado.gov.co/transparencia/normatividad"
_SOURCE = "Superintendencia de Notariado y Registro"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_UMBRAL = 18
_ANIO_MIN = 2015

# (segmento de URL de la categoría, tipo mostrado, letra del código de título)
_CATEGORIAS = [
    ("circulares", "Circular", "C"),
    ("Resoluciones", "Resolución", "R"),
]

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_CODIGO_RE = re.compile(r"\b(CIR|RES)-(\d{4})-(\d{6})-\d\b")
_RESULTADOS_RE = re.compile(r"Resultados\s*([\d.,]+)")
_PUB_RE = re.compile(r"Publicaci[oó]n:\s*(\d{4}-\d{2}-\d{2})")


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _parse_codigo(texto: str) -> Optional[Tuple[str, int, int]]:
    m = _CODIGO_RE.search(texto or "")
    if not m:
        return None
    letra = "C" if m.group(1) == "CIR" else "R"
    return letra, int(m.group(3)), int(m.group(2))


def _titulo(codigo: Optional[Tuple[str, int, int]], texto_crudo: str) -> Tuple[str, bool]:
    if codigo is None:
        return ((texto_crudo or "").strip() or "documento")[:120], True
    letra, numero, anio = codigo
    return f"{letra}_SNR_{numero:04d}_{anio}", False


def _resultados_total(html: str) -> int:
    m = _RESULTADOS_RE.search(html or "")
    if not m:
        return -1
    return int(m.group(1).replace(".", "").replace(",", ""))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/families/test_snr.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/snr.py tests/families/test_snr.py
git commit -m "feat(snr): helpers de parseo de código, título y conteo"
```

---

## Task 2: Parseo de tarjetas + mapeo a RawDocModel

**Files:**
- Modify: `core/scrapers/families/snr.py`
- Test: `tests/families/test_snr.py`

**Interfaces:**
- Consumes: helpers de Task 1; `parse_fecha_providencia_es`; `storage_path`; `RawDocModel`.
- Produces:
  - `_tarjetas(html: str) -> tuple[list[dict], int]` — `(tarjetas, n_sin_pdf)`. Cada tarjeta: `{"titulo_txt": str, "publicacion": str | None, "pdf_url": str}`. Solo las `<li>` de `ul.docs_download` cuyo `div.contenido_download` tiene un `<a href>`; las demás incrementan `n_sin_pdf`.
  - `_tarjeta_a_doc(tarjeta: dict, tipo: str, fini: str, ffin: str, on_progress) -> RawDocModel | None`
    - `None` si no hay fecha parseable (con aviso `"sin fecha"`), `fecha.year < _ANIO_MIN`, o la fecha ISO cae fuera de `[fini, ffin]`.

- [ ] **Step 1: Write the failing tests**

Añadir a `tests/families/test_snr.py`:

```python
from core.scrapers.families.snr import _tarjeta_a_doc, _tarjetas

_HTML = """
<ul class="docs_download">
  <li>
    <div class="download">
      <!--<a href="https://servicios.supernotariado.gov.co/files/snrcirculares/circular-348-x.pdf"> -->
      <img src="x"><!--<br>Descargar</a> --><br><span>0 Mg</span>
    </div>
    <div class="contenido_download">
      <span class="lettercap"></span> 348<br>
      <a href="https://servicios.supernotariado.gov.co/files/snrcirculares/circular-348-x.pdf" rel="nofollow">CIR-2026-000348-4 del 03 de septiembre del 2026 "Informacion de autos"</a><br>
      <span>Publicación: 2026-09-03</span><br><span>Desfijacion: 2026-09-14</span>
    </div>
    <div class="border-download"></div>
  </li>
  <li>
    <div class="download"><img src="x"><br><span>0 Mg</span></div>
    <div class="contenido_download"><span class="lettercap"></span> 20779<br>
      Notificación por aviso – Resolución No. RES-2026-020779-6 del 13 de agosto de 2026 " Por medio de la cual..."<br>
      <span>Publicación: 2026-08-28</span>
    </div>
  </li>
  <li>
    <div class="contenido_download"><span class="lettercap"></span> 445<br>
      <a href="https://servicios.supernotariado.gov.co/files/content/resoluciones/2019/179715-RES.445-2019.pdf">RES.445-2019EXPTE.407-2017 sin código canónico</a><br>
      <span>Publicación: 2019-05-10</span>
    </div>
  </li>
</ul>
<div class="paginacion_top">Resultados 355</div>
"""


def test_tarjetas_parses_cards_with_link_and_counts_the_rest():
    cards, sin_pdf = _tarjetas(_HTML)
    assert len(cards) == 2  # la circular y la RES.445; la "notificación por aviso" no tiene <a>
    assert sin_pdf == 1
    assert cards[0]["titulo_txt"].startswith("CIR-2026-000348-4 del 03 de septiembre del 2026")
    assert cards[0]["publicacion"] == "2026-09-03"
    assert cards[0]["pdf_url"].endswith("/circular-348-x.pdf")


def test_tarjetas_empty_html():
    assert _tarjetas("") == ([], 0)


def test_tarjeta_a_doc_verified_circular_uses_prose_date():
    cards, _ = _tarjetas(_HTML)
    doc = _tarjeta_a_doc(cards[0], "Circular", "2015-01-01", "2026-12-31", None)
    assert doc is not None
    assert doc.title == "C_SNR_0348_2026"
    assert doc.title_unverified is False
    assert doc.tipo == "Circular"
    assert doc.f_public == "2026-09-03"       # "del 03 de septiembre del 2026"
    assert doc.f_providencia == "2026-09-03"
    assert doc.link == {"url": "https://servicios.supernotariado.gov.co/files/snrcirculares/circular-348-x.pdf", "method": "GET"}
    assert doc.save_path == (
        "Superintendencia de Notariado y Registro/2026-09-03/Circular/C_SNR_0348_2026(extension)"
    )


def test_tarjeta_a_doc_falls_back_to_publicacion_date_when_no_prose():
    card = {"titulo_txt": "Circular sin fecha en prosa", "publicacion": "2025-07-01",
            "pdf_url": "https://servicios.supernotariado.gov.co/files/x.pdf"}
    doc = _tarjeta_a_doc(card, "Circular", "2015-01-01", "2026-12-31", None)
    assert doc is not None
    assert doc.f_public == "2025-07-01"
    assert doc.title_unverified is True  # sin código


def test_tarjeta_a_doc_unverified_for_old_code():
    cards, _ = _tarjetas(_HTML)
    doc = _tarjeta_a_doc(cards[1], "Resolución", "2015-01-01", "2026-12-31", None)  # RES.445-2019, pub 2019-05-10
    assert doc.title_unverified is True
    assert doc.title == "RES.445-2019EXPTE.407-2017 sin código canónico"
    assert doc.f_public == "2019-05-10"
    segs = doc.save_path.split("/")
    assert len(segs) == 4 and not any(c in segs[-1] for c in '\\/*?:"<>|')


def test_tarjeta_a_doc_below_year_floor_is_dropped():
    card = {"titulo_txt": "CIR-2013-000005-4 del 10 de enero de 2013", "publicacion": "2013-01-10",
            "pdf_url": "https://x/y.pdf"}
    assert _tarjeta_a_doc(card, "Circular", "2010-01-01", "2026-12-31", None) is None


def test_tarjeta_a_doc_outside_requested_range_is_dropped():
    cards, _ = _tarjetas(_HTML)
    assert _tarjeta_a_doc(cards[0], "Circular", "2015-01-01", "2026-08-31", None) is None  # doc es 2026-09-03


def test_tarjeta_a_doc_without_any_date_is_dropped_and_warns():
    card = {"titulo_txt": "Circular sin ninguna fecha", "publicacion": None, "pdf_url": "https://x/y.pdf"}
    avisos = []
    assert _tarjeta_a_doc(card, "Circular", "2015-01-01", "2026-12-31", avisos.append) is None
    assert any("sin fecha" in m.lower() for m in avisos)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/families/test_snr.py -q -k "tarjeta"`
Expected: FAIL — `ImportError` de `_tarjetas` / `_tarjeta_a_doc`.

- [ ] **Step 3: Implement `_tarjetas` and `_tarjeta_a_doc`**

Añadir a `core/scrapers/families/snr.py` (después de `_resultados_total`):

```python
def _tarjetas(html: str) -> Tuple[List[dict], int]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: List[dict] = []
    sin_pdf = 0
    for li in soup.select("ul.docs_download > li"):
        cont = li.select_one("div.contenido_download")
        if cont is None:
            continue
        a = cont.find("a", href=True)
        if a is None:
            sin_pdf += 1
            continue
        mpub = _PUB_RE.search(cont.get_text(" ", strip=True))
        out.append({
            "titulo_txt": a.get_text(" ", strip=True),
            "publicacion": mpub.group(1) if mpub else None,
            "pdf_url": a["href"].strip(),
        })
    return out, sin_pdf


def _tarjeta_a_doc(tarjeta, tipo, fini, ffin, on_progress) -> Optional[RawDocModel]:
    titulo_txt = tarjeta.get("titulo_txt") or ""
    fecha = parse_fecha_providencia_es(titulo_txt)
    if fecha is None and tarjeta.get("publicacion"):
        try:
            fecha = datetime.date.fromisoformat(tarjeta["publicacion"])
        except ValueError:
            fecha = None
    if fecha is None:
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: tarjeta sin fecha parseable «{titulo_txt[:70]}», se omite")
        return None
    if fecha.year < _ANIO_MIN:
        return None
    iso = fecha.isoformat()
    if iso < fini or iso > ffin:
        return None

    codigo = _parse_codigo(titulo_txt)
    title, unverified = _titulo(codigo, titulo_txt)
    safe = _safe_title(title)
    return RawDocModel(
        source=_SOURCE,
        link={"url": urljoin(_BASE, tarjeta["pdf_url"]), "method": "GET"},
        title=title,
        tipo=tipo,
        f_public=iso,
        f_providencia=iso,
        detalle=titulo_txt or None,
        save_path=storage_path(_SOURCE, iso, tipo, f"{safe}(extension)"),
        title_unverified=unverified,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/families/test_snr.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/snr.py tests/families/test_snr.py
git commit -m "feat(snr): parseo de tarjetas y mapeo a RawDocModel"
```

---

## Task 3: Transporte + enumeración adaptativa por prefijo

**Files:**
- Modify: `core/scrapers/families/snr.py`
- Test: `tests/families/test_snr.py`

**Interfaces:**
- Consumes: `_tarjetas`, `_resultados_total` (Tasks 1-2); `requests`.
- Produces:
  - `_buscar(session: requests.Session, categoria: str, termino: str) -> tuple[int, str]` — `POST {_BASE}/{categoria}/` con `data={"r": termino}`, `timeout=200`; devuelve `(_resultados_total(text), text)`. `raise_for_status()`.
  - `_enumerar_categoria(session, categoria: str, letra: str, fini: str, ffin: str, stop_event, on_progress) -> list[dict]` — todas las tarjetas (con `<a>`) de la categoría en el rango de años `[max(_ANIO_MIN, fini.year), ffin.year]`, deduplicadas por `pdf_url`.

**Comportamiento de `_enumerar_categoria`:**
- `tipo_code = "CIR" if letra == "C" else "RES"`.
- Por cada `anio` en el rango:
  - `stop_event` check → return lo acumulado.
  - `_buscar(session, categoria, str(anio))` → `(total, html)`. Si lanza → `on_progress` `"Error"` + `continue`.
  - `cards, _ = _tarjetas(html)`. Si `len(cards) > _UMBRAL` **o** (`total >= 0` y `len(cards) >= total`): la búsqueda por año devolvió todo → agregar `cards`, siguiente año.
  - Si no: recursión `_bloque(pref)` para `pref` en `"0".."9"`:
    - `termino = f"{tipo_code}-{anio}-{pref}"`; `_buscar(...)` → `(t, h)` (error → `on_progress` `"Error"` + return).
    - `t == 0` → return (poda).
    - `cs, _ = _tarjetas(h)`. Si `t <= _UMBRAL` **o** (`t >= 0` y `len(cs) >= t`) → agregar `cs`, return.
    - `len(pref) >= 5` → `on_progress` aviso (bloque de 10 con `> _UMBRAL`, no esperado) + agregar `cs` + return.
    - Si no → `_bloque(pref + d)` para `d` en `"0".."9"`.
    - `stop_event` check al entrar en `_bloque` → return sin más.
- Dedup por `pdf_url` (dict `{pdf_url: tarjeta}`).

- [ ] **Step 1: Write the failing tests**

Añadir a `tests/families/test_snr.py`:

```python
import responses

from core.scrapers.families.snr import _buscar, _enumerar_categoria

_CIR_URL = "https://www.supernotariado.gov.co/transparencia/normatividad/circulares/"
_RES_URL = "https://www.supernotariado.gov.co/transparencia/normatividad/Resoluciones/"


def _page(cards_html, total):
    return f'<ul class="docs_download">{cards_html}</ul><div>Resultados {total}</div>'


def _card(codigo, pub, url):
    return (
        f'<li><div class="contenido_download"><span class="lettercap"></span> x<br>'
        f'<a href="{url}">{codigo} del 03 de septiembre del 2026 "t"</a><br>'
        f'<span>Publicación: {pub}</span></div></li>'
    )


def test_buscar_posts_r_param_and_reads_total():
    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, _CIR_URL, body=_page(_card("CIR-2026-000001-4", "2026-01-05", "https://x/1.pdf"), 1))
        session = __import__("requests").Session()
        total, html = _buscar(session, "circulares", "2026")
    assert total == 1
    assert "docs_download" in html
    assert rsps.calls[0].request.body == "r=2026"


@responses.activate
def test_enumerar_uses_year_search_directly_when_it_returns_everything():
    # caso Resoluciones: r=2026 devuelve MÁS que _UMBRAL -> se usa directo, sin recursión
    cards = "".join(_card(f"RES-2026-{i:06d}-6", "2026-06-01", f"https://x/r{i}.pdf") for i in range(1, 25))
    responses.add(responses.POST, _RES_URL, body=_page(cards, 24))
    session = __import__("requests").Session()
    got = _enumerar_categoria(session, "Resoluciones", "R", "2026-01-01", "2026-12-31", None, None)
    assert len(got) == 24
    assert sum(1 for c in responses.calls if "Resoluciones" in c.request.url) == 1  # un solo POST


@responses.activate
def test_enumerar_recurses_by_prefix_when_year_search_is_capped():
    # Catálogo falso: 60 circulares de 2026 en 3 bloques de 100 (20 c/u, cada
    # bloque > _UMBRAL para forzar la recursión hasta bloques de 10).
    catalogo = list(range(1, 21)) + list(range(150, 170)) + list(range(300, 320))  # 20+20+20 = 60

    def cb(request):
        term = request.body.split("r=", 1)[1]
        if term == "2026":
            nums = catalogo
        elif term.startswith("CIR-2026-"):
            pref = term[len("CIR-2026-"):]
            nums = [n for n in catalogo if f"{n:06d}".startswith(pref)]
        else:
            return (200, {}, _page("", 0))
        resultados = len(nums)
        mostrados = nums if resultados <= 18 else nums[:18]  # el listado corta a ~18
        cards = "".join(_card(f"CIR-2026-{n:06d}-4", "2026-09-01", f"https://x/c{n}.pdf") for n in mostrados)
        return (200, {}, _page(cards, resultados))

    responses.add_callback(responses.POST, _CIR_URL, callback=cb, content_type="text/html")
    session = __import__("requests").Session()
    got = _enumerar_categoria(session, "circulares", "C", "2026-01-01", "2026-12-31", None, None)
    # los 60 del catálogo, recolectados vía bloques cuya búsqueda cabe en <=_UMBRAL
    assert len({g["pdf_url"] for g in got}) == 60


@responses.activate
def test_enumerar_dedups_by_pdf_url():
    def cb(request):
        term = request.body.split("r=", 1)[1]
        if term == "2026":
            return (200, {}, _page(_card("CIR-2026-000001-4", "2026-01-05", "https://x/dup.pdf"), 355))
        # todo prefijo devuelve la misma tarjeta duplicada
        return (200, {}, _page(_card("CIR-2026-000001-4", "2026-01-05", "https://x/dup.pdf"), 1))
    responses.add_callback(responses.POST, _CIR_URL, callback=cb, content_type="text/html")
    session = __import__("requests").Session()
    got = _enumerar_categoria(session, "circulares", "C", "2026-01-01", "2026-12-31", None, None)
    assert len(got) == 1


@responses.activate
def test_enumerar_continues_past_a_failing_year():
    def cb(request):
        term = request.body.split("r=", 1)[1]
        if term == "2015":
            return (500, {}, "boom")
        return (200, {}, _page(_card("CIR-2016-000001-4", "2016-02-01", "https://x/ok.pdf"), 1))
    responses.add_callback(responses.POST, _CIR_URL, callback=cb, content_type="text/html")
    progreso = []
    session = __import__("requests").Session()
    got = _enumerar_categoria(session, "circulares", "C", "2015-01-01", "2016-12-31", None, progreso.append)
    assert any(g["pdf_url"].endswith("/ok.pdf") for g in got)
    assert any("Error" in m for m in progreso)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/families/test_snr.py -q -k "buscar or enumerar"`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement the transport + enumeration**

Añadir a `core/scrapers/families/snr.py` (después de `_tarjeta_a_doc`):

```python
def _buscar(session: requests.Session, categoria: str, termino: str) -> Tuple[int, str]:
    resp = session.post(f"{_BASE}/{categoria}/", data={"r": termino}, timeout=200)
    resp.raise_for_status()
    return _resultados_total(resp.text), resp.text


def _enumerar_categoria(session, categoria, letra, fini, ffin, stop_event, on_progress) -> List[dict]:
    tipo_code = "CIR" if letra == "C" else "RES"
    anio_ini = max(_ANIO_MIN, int(fini[:4]))
    anio_fin = int(ffin[:4])
    por_url: dict = {}

    def _add(cards):
        for c in cards:
            por_url.setdefault(c["pdf_url"], c)

    for anio in range(anio_ini, anio_fin + 1):
        if stop_event is not None and stop_event.is_set():
            return list(por_url.values())
        try:
            total, html = _buscar(session, categoria, str(anio))
        except Exception as e:
            if on_progress:
                on_progress(f"[{_SOURCE}] Error consultando {categoria} {anio}: {e}")
            continue
        cards, _ = _tarjetas(html)
        if len(cards) > _UMBRAL or (total >= 0 and len(cards) >= total):
            _add(cards)
            continue

        def _bloque(pref: str):
            if stop_event is not None and stop_event.is_set():
                return
            termino = f"{tipo_code}-{anio}-{pref}"
            try:
                t, h = _buscar(session, categoria, termino)
            except Exception as e:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Error consultando {categoria} {termino}: {e}")
                return
            if t == 0:
                return
            cs, _ = _tarjetas(h)
            if t <= _UMBRAL or (t >= 0 and len(cs) >= t):
                _add(cs)
                return
            if len(pref) >= 5:
                if on_progress:
                    on_progress(f"[{_SOURCE}] Aviso: bloque {termino} con {t} > {_UMBRAL}, posible corte")
                _add(cs)
                return
            for d in "0123456789":
                _bloque(pref + d)

        for d in "0123456789":
            _bloque(d)

    return list(por_url.values())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/families/test_snr.py tests/families/test_mincit.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/snr.py tests/families/test_snr.py
git commit -m "feat(snr): transporte POST + enumeración adaptativa por prefijo de código"
```

---

## Task 4: `ScrapSNR.scrap` + registro + smoke test en vivo

**Files:**
- Modify: `core/scrapers/families/snr.py`
- Modify: `core/scrapers/families/__init__.py`
- Test: `tests/families/test_snr.py`

**Interfaces:**
- Consumes: `_CATEGORIAS`, `_enumerar_categoria` (Task 3), `_tarjeta_a_doc` (Task 2).
- Produces: `ScrapSNR` registrada como `@register_family("snr")`, `filters_by_publication_date = True`, con
  `scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]`.

**Comportamiento de `scrap`:**
1. `session = requests.Session()` con `User-Agent: _UA`.
2. Por cada `(categoria, tipo, letra)` en `_CATEGORIAS`:
   - `stop_event` check antes de la categoría → `return docs[:limit]`.
   - `on_progress(f"[{_SOURCE}] Procesando {tipo}...")`.
   - `tarjetas = _enumerar_categoria(session, categoria, letra, fini, ffin, stop_event, on_progress)`.
   - Por cada tarjeta: `doc = _tarjeta_a_doc(tarjeta, tipo, fini, ffin, on_progress)`; si no es `None`, `append`; si `len(docs) >= limit`, `return docs[:limit]`.
3. `return docs[:limit]`.

- [ ] **Step 1: Write the failing tests**

Añadir a `tests/families/test_snr.py`:

```python
import threading

from core.scrapers.registry import FAMILY_REGISTRY
from core.scrapers.families.snr import ScrapSNR


def test_snr_is_registered():
    import core.scrapers.families  # noqa: F401
    assert FAMILY_REGISTRY["snr"].__name__ == "ScrapSNR"


def test_filters_by_publication_date_is_enabled():
    assert ScrapSNR.filters_by_publication_date is True


@responses.activate
def test_scrap_collects_both_categories():
    responses.add(responses.POST, _CIR_URL,
                  body=_page(_card("CIR-2026-000010-4", "2026-03-01", "https://x/c10.pdf"), 1))
    responses.add(responses.POST, _RES_URL,
                  body=_page(_card("RES-2026-000020-6", "2026-04-01", "https://x/r20.pdf"), 1))
    docs = ScrapSNR().scrap(fini="2026-01-01", ffin="2026-12-31")
    assert {d.title for d in docs} == {"C_SNR_0010_2026", "R_SNR_0020_2026"}
    assert {d.tipo for d in docs} == {"Circular", "Resolución"}


@responses.activate
def test_scrap_applies_year_floor_and_range():
    # una circular de 2013 (bajo el piso) y una de 2026 en rango
    body = _page(
        _card("CIR-2013-000001-4", "2013-01-10", "https://x/old.pdf")
        + _card("CIR-2026-000002-4", "2026-05-01", "https://x/new.pdf"), 2)
    responses.add(responses.POST, _CIR_URL, body=body)
    responses.add(responses.POST, _RES_URL, body=_page("", 0))
    docs = ScrapSNR().scrap(fini="2010-01-01", ffin="2026-12-31")
    assert {d.title for d in docs} == {"C_SNR_0002_2026"}


@responses.activate
def test_scrap_stops_on_stop_event():
    responses.add(responses.POST, _CIR_URL, body=_page("", 0))
    responses.add(responses.POST, _RES_URL, body=_page("", 0))
    ev = threading.Event()
    ev.set()
    docs = ScrapSNR().scrap(fini="2026-01-01", ffin="2026-12-31", stop_event=ev)
    assert docs == []
    assert len(responses.calls) == 0


@responses.activate
def test_scrap_respects_limit():
    cards = "".join(_card(f"CIR-2026-{i:06d}-4", "2026-02-01", f"https://x/c{i}.pdf") for i in range(1, 6))
    responses.add(responses.POST, _CIR_URL, body=_page(cards, 5))
    responses.add(responses.POST, _RES_URL, body=_page("", 0))
    docs = ScrapSNR().scrap(fini="2026-01-01", ffin="2026-12-31", limit=2)
    assert len(docs) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/families/test_snr.py -q -k "scrap or is_registered or filters_by"`
Expected: FAIL — `ImportError: cannot import name 'ScrapSNR'`.

- [ ] **Step 3: Implement `ScrapSNR` and register it**

Añadir al final de `core/scrapers/families/snr.py`:

```python
@register_family("snr")
class ScrapSNR(BaseScrapper):
    filters_by_publication_date = True

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": _UA})
        docs: List[RawDocModel] = []

        for categoria, tipo, letra in _CATEGORIAS:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            if on_progress:
                on_progress(f"[{_SOURCE}] Procesando {tipo}...")
            tarjetas = _enumerar_categoria(session, categoria, letra, fini, ffin, stop_event, on_progress)
            for tarjeta in tarjetas:
                doc = _tarjeta_a_doc(tarjeta, tipo, fini, ffin, on_progress)
                if doc is not None:
                    docs.append(doc)
                    if len(docs) >= limit:
                        return docs[:limit]

        return docs[:limit]
```

Modificar `core/scrapers/families/__init__.py` — añadir `snr` al final:

```python
from . import constitucional, samai, corte_suprema, jep, cndj, adr, adres, ane, anh, rama_judicial, mincit, madr, minambiente, minvivienda, mineducacion, mininterior, mindeporte, minjusticia, minenergia, mintrabajo, superfinanciera, supersalud, ssf, snr  # noqa: F401
```

- [ ] **Step 4: Run the family test file**

Run: `.venv/Scripts/pytest tests/families/test_snr.py tests/families/test_mincit.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Smoke test en vivo (manual, obligatorio antes de commitear)**

El sitio es lento y su búsqueda podría comportarse distinto en vivo. Correr contra el sitio real con un rango CORTO (para no disparar el backfill completo):

```bash
.venv/Scripts/python -c "
from core.scrapers.families.snr import ScrapSNR
docs = ScrapSNR().scrap(fini='2026-06-01', ffin='2026-09-07', on_progress=print)
print('TOTAL', len(docs))
for d in docs[:12]:
    print(d.f_public, '|', d.tipo, '|', d.title, '|', d.title_unverified, '|', d.link['url'][:95])
assert docs, 'sin documentos: revisar el selector de tarjetas o la búsqueda POST'
assert all('2026-06-01' <= d.f_public <= '2026-09-07' for d in docs), 'fechas fuera de rango'
assert any(d.tipo == 'Circular' for d in docs), 'falta Circular'
verif = [d for d in docs if not d.title_unverified]
print('verificados', len(verif), '/', len(docs))
import requests
r = requests.get(docs[0].link['url'], timeout=60)
print('descarga doc[0]:', r.status_code, r.headers.get('content-type'), len(r.content), 'bytes', r.content[:5])
assert r.status_code == 200 and r.content[:4] == b'%PDF', 'el PDF no descargó'
print('OK')
"
```

A ojo: filas de Circular (y Resolución si hay en el rango), títulos `C_SNR_####_2026`, mayoría verificados, URLs a `servicios.supernotariado.gov.co/files/…`, y el primer PDF descarga (`%PDF`). Si sale `sin documentos`, imprimir el HTML de una respuesta `_buscar` y revisar que `ul.docs_download > li` y el `<a>` de `div.contenido_download` sigan igual. **No** commitear hasta que pase.

- [ ] **Step 6: Commit**

```bash
git add core/scrapers/families/snr.py core/scrapers/families/__init__.py tests/families/test_snr.py
git commit -m "feat(snr): orquestación scrap() de las dos categorías + registro de la familia"
```

---

## Task 5: Seed + bump de test_seed.py + nota de documentación

**Files:**
- Modify: `core/seed.py`
- Modify: `tests/test_seed.py`
- Modify: `docs/guia-despliegue-sistemas.md`
- Test: `tests/families/test_snr.py`

**Interfaces:**
- Consumes: `FAMILY_REGISTRY` poblado por el import de Task 4.
- Produces: entrada `"snr"` en `_FAMILIES` + fuente `"Superintendencia de Notariado y Registro"` sembrada con `family_key="snr"`, `family_params={}`.

- [ ] **Step 1: Write the failing test**

Añadir a `tests/families/test_snr.py`:

```python
def test_seed_families_dict_has_snr_entry():
    from core.seed import _FAMILIES
    assert "snr" in _FAMILIES
    display_name, description = _FAMILIES["snr"]
    assert display_name == "Superintendencia de Notariado y Registro"
    assert "irculares" in description
    assert "esoluciones" in description or "esolucion" in description
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/families/test_snr.py -q -k seed_families_dict`
Expected: FAIL — `KeyError: 'snr'`.

- [ ] **Step 3: Add the seed entry**

En `core/seed.py`, dentro de `_FAMILIES` (junto a la entrada `"ssf"`):

```python
    "snr": (
        "Superintendencia de Notariado y Registro",
        "Normativa (circulares y resoluciones) publicada por la "
        "Superintendencia de Notariado y Registro",
    ),
```

Y en la zona de `repository.create_source_if_missing(...)` (después de la de `ssf`):

```python
    repository.create_source_if_missing(
        db, family_key="snr", name="Superintendencia de Notariado y Registro", family_params={}
    )
```

- [ ] **Step 4: Apply the `tests/test_seed.py` bumps**

En `tests/test_seed.py`:
- `assert len(families) == 23` → `== 24`
- ambas `assert len(sources) == 1 + 28 + 20 + 33 + 6` → `== 1 + 28 + 21 + 33 + 6`
- el comentario `# ... + 20 (fuente única: ..., ssf) + 33 ...` → `21 (fuente única: ..., ssf, snr)`
- en el set de `test_seed_populates_families_and_sources_and_is_idempotent`, añadir `"snr",` después de `"ssf",`

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/families/test_snr.py tests/test_seed.py tests/test_registry.py -q`
Expected: PASS (todos). (`tests/test_seed.py` puede tardar ~150s por la BD.)

- [ ] **Step 6: Add the documentation note**

En `docs/guia-despliegue-sistemas.md`, §10 "Notas por fuente":

```markdown
### Superintendencia de Notariado y Registro (`snr`)

Una sola fuente que raspa dos categorías del portal WordPress de la SNR:
**Circulares** y **Resoluciones**. Cobertura desde 2015. Los documentos se
descargan de `servicios.supernotariado.gov.co/files/…`.

Particularidad: el listado del sitio **no tiene paginación** (solo muestra
~20 por categoría). La familia enumera el catálogo con una búsqueda `POST`
adaptativa por prefijo del número de la norma; por eso una corrida de
**backfill** (rango amplio) tarda ~10–15 minutos, mientras que una
corrida **incremental** (última semana) es rápida. Se saltan las tarjetas
sin archivo adjunto (las "notificación por aviso").

Títulos: `{C|R}_SNR_{número}_{año}` (desde el código `CIR-AAAA-NNNNNN` /
`RES-AAAA-NNNNNN`). Los documentos viejos sin ese código entran con el
título crudo y marca de "no verificado".

**Fuente nueva:** después de actualizar producción hay que correr una vez
`docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.seed`.
Es seguro repetirlo.
```

- [ ] **Step 7: Commit**

```bash
git add core/seed.py tests/test_seed.py docs/guia-despliegue-sistemas.md tests/families/test_snr.py
git commit -m "feat(snr): seed de la fuente + bump de conteos en test_seed + nota de despliegue"
```

---

## Task 6: Verificación completa y PR

**Files:** ninguno nuevo.

- [ ] **Step 1: Suite enfocada + seed + registry + fecha_es**

Run: `.venv/Scripts/python -m pytest tests/families/ tests/test_seed.py tests/test_registry.py tests/test_fecha_es.py -q`
Expected: PASS. (`tests/families/` rápido; `test_seed.py` lento por BD.)

- [ ] **Step 2: Import del registro**

Run: `.venv/Scripts/python -c "import core.scrapers.families; from core.scrapers.registry import FAMILY_REGISTRY; print(sorted(FAMILY_REGISTRY))"`
Expected: la lista incluye `'snr'`.

- [ ] **Step 3: Seed idempotente contra la BD local**

Run: `.venv/Scripts/python -m core.seed` (dos veces) — sin error ambas.
Run: `.venv/Scripts/python -c "from core.db.session import SessionLocal; from core.db import repository; db=SessionLocal(); print([s.name for s in repository.list_sources(db) if s.family_key=='snr'])"`
Expected: `['Superintendencia de Notariado y Registro']`.

- [ ] **Step 4: Smoke test en vivo end-to-end**

Repetir el smoke test del Task 4 Step 5. Si el entorno de dev está levantado, disparar una corrida real desde la UI (`run-iurisync`) contra la fuente nueva con rango corto y confirmar descarga + preview de al menos un documento.

- [ ] **Step 5: Push y PR**

```bash
git push -u origin feature/fuente-snr
gh pr create --base master --title "feat(snr): nueva fuente Superintendencia de Notariado y Registro" --body "$(cat <<'EOF'
Nueva familia técnica `snr`: raspa Circulares y Resoluciones del portal
WordPress de la Superintendencia de Notariado y Registro.

## Qué trae
- `core/scrapers/families/snr.py` — familia nueva. El listado del sitio no
  tiene paginación, así que la enumeración usa una búsqueda `POST r=<texto>`
  con recursión adaptativa por prefijo del código de norma
  (`CIR-AAAA-NNNNNN` / `RES-AAAA-NNNNNN`). PDFs directo de
  `servicios.supernotariado.gov.co/files/…`.
- Títulos `{C|R}_SNR_{nº:04d}_{año}`; `title_unverified` para códigos viejos
  que no calzan (`RES.445-2019`).
- Fecha de la prosa del título (respaldo: `Publicación:` ISO). Piso 2015.
  Se saltan las tarjetas sin PDF ("notificación por aviso").
- Seed: una fuente. Bump de `tests/test_seed.py` (24 familias). Sin migración.
- `tests/families/test_snr.py` con fixtures HTML + `responses`.

## Spec y plan
- `docs/superpowers/specs/2026-09-07-fuente-snr-design.md`
- `docs/superpowers/plans/2026-09-07-fuente-snr.md`

## Verificación
- `pytest tests/families/ tests/test_seed.py tests/test_registry.py` verde.
- Smoke test en vivo contra supernotariado.gov.co: rango corto → devuelve
  circulares con títulos canónicos, y el primer PDF descarga (`%PDF`).

## Despliegue
Fuente nueva: tras actualizar prod, correr una vez `python -m core.seed`. Sin migración.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**1. Spec coverage:**

| Sección del spec | Task |
|---|---|
| Categorías `circulares` + `Resoluciones`, casing exacto | Task 1 (`_CATEGORIAS`) |
| Tarjeta: `<a>` de `contenido_download`, omitir las sin `<a>` y contarlas | Task 2 (`_tarjetas`) + tests |
| Código `(CIR|RES)-AAAA-NNNNNN-D` → letra/numero/anio; sin código → unverified | Task 1 (`_parse_codigo`, `_titulo`) + tests |
| Fecha prosa (respaldo `Publicación:`); descarte + aviso si ninguna | Task 2 (`_tarjeta_a_doc`) + tests |
| Piso 2015 + filtro por rango | Task 2 (`_tarjeta_a_doc`) + tests |
| Título `{C|R}_SNR_{nº:04d}_{año}` (5 díg. sin recorte en Resol.) | Task 1 (`_titulo`) + test |
| `_buscar` POST `r=`, `timeout=200`, lee `Resultados` | Task 3 (`_buscar`) + test |
| Enumeración: año directo si devuelve todo; si no, recursión por prefijo con poda `total==0`, corte `<=_UMBRAL`, tope de 5 díg. | Task 3 (`_enumerar_categoria`) + tests |
| Dedup por `pdf_url` | Task 3 + test |
| Resiliencia: un año/prefijo que falla no aborta | Task 3 + test |
| `stop_event` y `limit` | Task 3 (`stop_event`) + Task 4 (`scrap`) + tests |
| `filters_by_publication_date = True`, otros flags por defecto | Task 4 (atributo) + test |
| Registro en `families/__init__.py` | Task 4 |
| Seed: una fuente, `family_params={}`, sin `auto_review_status` | Task 5 + test |
| `tests/test_seed.py` bump (24 familias, 21 fuentes únicas, set con `snr`) | Task 5 |
| Nota de documentación | Task 5 |
| Sin migración, sin frontend | (n/a — no hay task) |

Sin huecos.

**2. Placeholder scan:** Sin "TBD"/"TODO"/"manejar edge cases". El único paso manual (smoke test en vivo, Task 4 Step 5 / Task 6 Step 4) trae comando exacto y criterios de aceptación.

**3. Type consistency:**
- `_parse_codigo(texto) -> tuple[str,int,int] | None` — Task 1 def + tests; consumido por `_titulo` (Task 1) y `_tarjeta_a_doc` (Task 2).
- `_titulo(codigo, texto_crudo) -> tuple[str,bool]` — Task 1 def + tests; consumido por `_tarjeta_a_doc` (Task 2).
- `_resultados_total(html) -> int` — Task 1 def + tests; consumido por `_buscar` (Task 3).
- `_tarjetas(html) -> tuple[list[dict], int]` — Task 2 def + tests; consumido por `_enumerar_categoria` (Task 3) como `cards, _ = _tarjetas(...)`.
- `_tarjeta_a_doc(tarjeta, tipo, fini, ffin, on_progress) -> RawDocModel | None` — Task 2 def + tests; consumido por `ScrapSNR.scrap` (Task 4).
- `_buscar(session, categoria, termino) -> tuple[int,str]` — Task 3 def + tests; consumido por `_enumerar_categoria` (Task 3).
- `_enumerar_categoria(session, categoria, letra, fini, ffin, stop_event, on_progress) -> list[dict]` — Task 3 def + tests; consumido por `ScrapSNR.scrap` (Task 4).
- `_CATEGORIAS` = lista de `(segmento_url, tipo, letra)` — Task 1; desempaquetado igual en Task 4.

Consistente.
