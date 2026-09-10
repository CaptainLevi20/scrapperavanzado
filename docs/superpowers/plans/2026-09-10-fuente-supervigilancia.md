# Fuente Supervigilancia — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir la familia de scraper `supervigilancia` (Superintendencia de Vigilancia y Seguridad Privada) que trae Resoluciones y Conceptos jurídicos de `www.supervigilancia.gov.co`.

**Architecture:** Un módulo nuevo `core/scrapers/families/supervigilancia.py` con la clase `ScrapSupervigilancia(BaseScrapper)` registrada vía `@register_family("supervigilancia")`. Sitio Odoo: listados estáticos con bloques `div.s_dl_item`, paginación por sufijo de URL (`-pagina02`, …), descarga por `/web/content/{id}?download=true`. El número real de cada resolución se lee del `Content-Disposition` de una petición `HEAD` por documento (no está fiable en el listado ni en el texto del PDF). Familia plana: sin actuaciones, sin anexos, sin `family_params`, sin migración.

**Tech Stack:** Python 3.14, `requests` + `beautifulsoup4` (parser `html.parser`), `pydantic` (`RawDocModel`), `pytest` + `responses` para mockear HTTP.

**Spec:** `docs/superpowers/specs/2026-09-10-fuente-supervigilancia-design.md`

## Global Constraints

- **Sigla de títulos:** `SVySP`. Prefijo `R` para resoluciones, `CTO` para conceptos.
- **Formato del título con número:** `f"{pref}_SVySP_{numero}_{anio}"`, número **literal** (sin `zfill`, sin normalizar, mayúsculas, con sufijo `CS`). Sin número → título descriptivo recortado a 120 chars + `title_unverified=True`, y el documento **igual se guarda**.
- **`_SOURCE = "Superintendencia de Vigilancia y Seguridad Privada"`** — string EXACTO, debe coincidir carácter por carácter con el `name=` que usa `core/seed.py` (así se enlazan los `RawDocModel` con la fuente en BD).
- **Piso de año:** `_ANIO_MINIMO = 2015`. Fila con `fecha.year < 2015` → no entra. Además se respeta el rango `fini`/`ffin` de la corrida (`fini <= fecha.isoformat() <= ffin`).
- **TLS válido → NO usar `verify=False`** en ninguna petición ni en `link`.
- **Cabecera obligatoria en toda petición:** `Accept-Language: es-CO,es;q=0.9` (fijada en `session.headers`). Sin ella Odoo redirige a `/en/…` y las páginas de paginación vienen sin `div.s_dl_item`.
- **`User-Agent`:** `"Mozilla/5.0 (Windows NT 10.0; Win64; x64)"`.
- **Fechas de sitio:** formato `DD/MM/AAAA`. `f_public` y `f_providencia` se ponen **ambas** a esa fecha. Fecha `"Hoy"` → fecha de la corrida (`datetime.date.today()`). Fecha `"--"`, vacía o sin `DD/MM/AAAA` → descartar el documento con aviso `on_progress`, no aproximar.
- **Tipo:** se deriva de la sección que se está rastreando, NUNCA de `data-category` ni de `.s_dl_doc_type` (son ruido de plantilla).
- **Pruebas dirigidas:** `pytest tests/families/test_supervigilancia.py tests/test_seed.py` (sin la suite pesada completa, sin `-p xdist` / `-n`).
- **Rama de trabajo:** `feature/fuente-supervigilancia` (ya creada; el spec ya está commiteado ahí).

---

### Task 1: Constantes del módulo y helpers de parseo puros

**Files:**
- Create: `core/scrapers/families/supervigilancia.py`
- Test: `tests/families/test_supervigilancia.py`

**Interfaces:**
- Consumes: nada (primer task).
- Produces:
  - `_BASE: str = "https://www.supervigilancia.gov.co"`
  - `_SOURCE: str` (ver Global Constraints)
  - `_ANIO_MINIMO: int = 2015`
  - `_HEADERS: dict` — `{"User-Agent": ..., "Accept-Language": "es-CO,es;q=0.9"}`
  - `_SECCIONES: list[tuple[str, str, str]]` — `[(url_listado_pagina1, tipo, pref), …]`; el `pref` es `"R"` o `"CTO"`, el `tipo` es `"Resolución"` o `"Concepto"`.
  - `_norm_texto(s: str) -> str` — NFC + quita `​` (ancho cero) + colapsa espacios en blanco (`\s+` → `" "`) + `.strip()`.
  - `_safe_title(title: str) -> str` — reemplaza `[\\/*?:"<>|]` por `-`, recorta a 120, `.strip(" .")`.
  - `_id_de_href(href: str) -> str | None` — de `"/web/content/10260?download=true"` (o URL absoluta) devuelve `"10260"`; `None` si no hay match de `/web/content/(\d+)`.
  - `_num_en_texto(texto: str) -> str | None` — primer `\d{6,}CS` (case-insensitive) en cualquier posición → devuelto en MAYÚSCULAS (`"20263200005647CS"`). `None` si no hay.
  - `_num_al_inicio(texto: str) -> str | None` — `^\s*(\d{6,}CS)\b` (case-insensitive) → MAYÚSCULAS; `None` si no está al inicio.
  - `_num_en_prosa(texto: str) -> str | None` — `resoluci[oó]n\s+(?:n[o°º]\.?\s*|n[uú]mero\s*)?(\d{4,})` (case-insensitive, sobre texto NFC) → los dígitos tal cual; `None` si no hay.
  - `_fecha_de_meta(meta: str, hoy: datetime.date) -> datetime.date | None` — si `meta` (ya normalizado) contiene `"Hoy"` (case-insensitive, como palabra) y ningún `DD/MM/AAAA` → `hoy`; si contiene un `\d{1,2}/\d{1,2}/\d{4}` válido → esa fecha; en otro caso (`"--"`, vacío, fecha inválida) → `None`.
  - `_titulo(pref: str, numero: str | None, anio: int, texto_crudo: str, filename_stem: str | None) -> tuple[str, bool]` — con `numero`: `(f"{pref}_SVySP_{numero}_{anio}", False)`. Sin `numero`: base = `texto_crudo` normalizado y sin sufijo `.pdf`/`.PDF`; si queda vacío, `filename_stem` sin `.pdf`; si ambos vacíos, `"documento"`. Devuelve `(base[:120], True)`.

- [ ] **Step 1: Escribir los tests de los helpers puros**

```python
# tests/families/test_supervigilancia.py
import datetime

from core.scrapers.families.supervigilancia import (
    _SOURCE,
    _ANIO_MINIMO,
    _norm_texto,
    _safe_title,
    _id_de_href,
    _num_en_texto,
    _num_al_inicio,
    _num_en_prosa,
    _fecha_de_meta,
    _titulo,
)


def test_source_string_matches_seed_name():
    assert _SOURCE == "Superintendencia de Vigilancia y Seguridad Privada"
    assert _ANIO_MINIMO == 2015


def test_norm_texto_strips_zero_width_and_collapses_space():
    assert _norm_texto("Res​olución   No.  1\n\t2") == "Resolución No. 1 2"


def test_safe_title_replaces_forbidden_chars_and_truncates():
    assert _safe_title('a/b:c"d') == "a-b-c-d"
    assert len(_safe_title("x" * 200)) == 120


def test_id_de_href():
    assert _id_de_href("/web/content/10260?download=true") == "10260"
    assert _id_de_href("https://www.supervigilancia.gov.co/web/content/7096?download=true") == "7096"
    assert _id_de_href("/circular-externa-no-1") is None


def test_num_en_texto_any_position_uppercased():
    assert _num_en_texto('filename="20261000015947CS RESOLUCION.pdf"') == "20261000015947CS"
    assert _num_en_texto("RESOLUCION No. 202540000099737cs - TRAMITES.pdf") == "202540000099737CS"
    assert _num_en_texto("Renting operativo.pdf") is None


def test_num_al_inicio_only_when_leading():
    assert _num_al_inicio("20263200005647CS Por la cual...") == "20263200005647CS"
    assert _num_al_inicio("Por la cual se deroga la 20221300053467CS") is None


def test_num_en_prosa():
    assert _num_en_prosa("POR MEDIO DE LA CUAL SE EFECTÚA UNA CORRECCIÓN A LA RESOLUCIÓN No. 2023320000649") == "2023320000649"
    assert _num_en_prosa("Resolucion 20253200007657 lineamientos para Reporte") == "20253200007657"
    assert _num_en_prosa("Ley Lorenzo") is None


def test_fecha_de_meta_variants():
    hoy = datetime.date(2026, 9, 10)
    assert _fecha_de_meta("Publicación: 08/05/2026", hoy) == datetime.date(2026, 5, 8)
    assert _fecha_de_meta("|Expedición: 23/01/2008", hoy) == datetime.date(2008, 1, 23)
    assert _fecha_de_meta("Publicación: Hoy", hoy) == hoy
    assert _fecha_de_meta("Expedición: --", hoy) is None
    assert _fecha_de_meta("", hoy) is None
    assert _fecha_de_meta("Expedición: 32/13/2020", hoy) is None


def test_titulo_con_numero():
    assert _titulo("R", "20263200005647CS", 2026, "cualquier cosa", None) == ("R_SVySP_20263200005647CS_2026", False)


def test_titulo_sin_numero_usa_texto_crudo_sin_pdf():
    title, unverified = _titulo("CTO", None, 2018, "Renting operativo.pdf", None)
    assert title == "Renting operativo"
    assert unverified is True


def test_titulo_sin_numero_cae_a_filename_stem_cuando_texto_vacio():
    assert _titulo("R", None, 2025, "   ", "20263100016027CS")[0] == "20263100016027CS"


def test_titulo_sin_numero_fallback_documento():
    assert _titulo("R", None, 2025, "", None)[0] == "documento"
```

- [ ] **Step 2: Correr los tests y verlos fallar**

Run: `pytest tests/families/test_supervigilancia.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'core.scrapers.families.supervigilancia'`.

- [ ] **Step 3: Escribir el módulo con constantes y helpers**

```python
# core/scrapers/families/supervigilancia.py
import datetime
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

_BASE = "https://www.supervigilancia.gov.co"
_SOURCE = "Superintendencia de Vigilancia y Seguridad Privada"
_ANIO_MINIMO = 2015
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "es-CO,es;q=0.9"}

# (url de la página 1 del listado, tipo asignado, prefijo de título)
_SECCIONES = [
    (f"{_BASE}/2-1-3-2-resoluciones", "Resolución", "R"),
    (f"{_BASE}/2-1-3-8-conceptos-juridicos", "Concepto", "CTO"),
]
# Sólo Resoluciones pagina; Conceptos es una sola página.
_PAGINA_TOPE = 20

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_ID_RE = re.compile(r"/web/content/(\d+)")
_NUM_CS_ANY = re.compile(r"(\d{6,}CS)", re.I)
_NUM_CS_INICIO = re.compile(r"^\s*(\d{6,}CS)\b", re.I)
_NUM_PROSA = re.compile(r"resoluci[oó]n\s+(?:n[o°º]\.?\s*|n[uú]mero\s*)?(\d{4,})", re.I)
_FECHA_RE = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})\b")
_HOY_RE = re.compile(r"\bhoy\b", re.I)
_PDF_SUFIJO = re.compile(r"\.pdf$", re.I)


def _norm_texto(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "").replace("​", "")
    return re.sub(r"\s+", " ", s).strip()


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title or "")[:120].strip(" .")


def _id_de_href(href: str) -> Optional[str]:
    m = _ID_RE.search(href or "")
    return m.group(1) if m else None


def _num_en_texto(texto: str) -> Optional[str]:
    m = _NUM_CS_ANY.search(texto or "")
    return m.group(1).upper() if m else None


def _num_al_inicio(texto: str) -> Optional[str]:
    m = _NUM_CS_INICIO.match(texto or "")
    return m.group(1).upper() if m else None


def _num_en_prosa(texto: str) -> Optional[str]:
    m = _NUM_PROSA.search(unicodedata.normalize("NFC", texto or ""))
    return m.group(1) if m else None


def _fecha_de_meta(meta: str, hoy: datetime.date) -> Optional[datetime.date]:
    m = _FECHA_RE.search(meta or "")
    if m:
        dd, mm, yyyy = (int(x) for x in m.groups())
        try:
            return datetime.date(yyyy, mm, dd)
        except ValueError:
            return None
    if _HOY_RE.search(meta or ""):
        return hoy
    return None


def _titulo(
    pref: str,
    numero: Optional[str],
    anio: int,
    texto_crudo: str,
    filename_stem: Optional[str],
) -> Tuple[str, bool]:
    if numero:
        return f"{pref}_SVySP_{numero}_{anio}", False
    base = _PDF_SUFIJO.sub("", _norm_texto(texto_crudo))
    if not base and filename_stem:
        base = _PDF_SUFIJO.sub("", _norm_texto(filename_stem))
    return (base or "documento")[:120], True
```

- [ ] **Step 4: Correr los tests y verlos pasar**

Run: `pytest tests/families/test_supervigilancia.py -v`
Expected: PASS (13 tests).

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/supervigilancia.py tests/families/test_supervigilancia.py
git commit -m "feat(supervigilancia): constantes y helpers de parseo puros"
```

---

### Task 2: `_head_info` — leer el `Content-Disposition` con HEAD

**Files:**
- Modify: `core/scrapers/families/supervigilancia.py`
- Test: `tests/families/test_supervigilancia.py`

**Interfaces:**
- Consumes: `_HEADERS` de Task 1.
- Produces:
  - `_head_info(session: requests.Session, url: str) -> dict` — hace `session.head(url, timeout=30, allow_redirects=True)` y devuelve `{"filename": str | None, "content_length": int | None}`. El `filename` se saca de `Content-Disposition` con `re.search(r'filename="?([^"\r\n;]+)"?', disp)` y se le aplica `.strip()`. El `content_length` es `int(headers["Content-Length"])` si es dígito, si no `None`. **Cualquier excepción** (`requests.RequestException`, timeout, etc.) → devuelve `{"filename": None, "content_length": None}` (no propaga).

- [ ] **Step 1: Escribir los tests**

```python
import requests
import responses

from core.scrapers.families.supervigilancia import _head_info

_URL = "https://www.supervigilancia.gov.co/web/content/10102?download=true"


@responses.activate
def test_head_info_parsea_filename_y_length():
    responses.add(
        responses.HEAD, _URL,
        headers={
            "Content-Disposition": 'attachment; filename="20261000015947CS RESOLUCION.pdf"',
            "Content-Length": "403369",
        },
    )
    got = _head_info(requests.Session(), _URL)
    assert got == {"filename": "20261000015947CS RESOLUCION.pdf", "content_length": 403369}


@responses.activate
def test_head_info_filename_sin_comillas():
    responses.add(
        responses.HEAD, _URL,
        headers={"Content-Disposition": "attachment; filename=20263100016027CS.pdf"},
    )
    assert _head_info(requests.Session(), _URL)["filename"] == "20263100016027CS.pdf"


@responses.activate
def test_head_info_sin_disposition():
    responses.add(responses.HEAD, _URL, headers={"Content-Length": "10"})
    assert _head_info(requests.Session(), _URL) == {"filename": None, "content_length": 10}


@responses.activate
def test_head_info_excepcion_de_red_devuelve_vacio():
    responses.add(responses.HEAD, _URL, body=requests.ConnectionError("boom"))
    assert _head_info(requests.Session(), _URL) == {"filename": None, "content_length": None}
```

- [ ] **Step 2: Correr los tests y verlos fallar**

Run: `pytest tests/families/test_supervigilancia.py -k head_info -v`
Expected: FAIL con `ImportError: cannot import name '_head_info'`.

- [ ] **Step 3: Implementar `_head_info`**

```python
_FILENAME_RE = re.compile(r'filename="?([^"\r\n;]+)"?', re.I)


def _head_info(session: requests.Session, url: str) -> dict:
    try:
        resp = session.head(url, timeout=30, allow_redirects=True)
    except requests.RequestException:
        return {"filename": None, "content_length": None}
    disp = resp.headers.get("Content-Disposition", "")
    m = _FILENAME_RE.search(disp)
    filename = m.group(1).strip() if m else None
    raw_len = resp.headers.get("Content-Length", "")
    content_length = int(raw_len) if raw_len.isdigit() else None
    return {"filename": filename, "content_length": content_length}
```

- [ ] **Step 4: Correr los tests y verlos pasar**

Run: `pytest tests/families/test_supervigilancia.py -k head_info -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/supervigilancia.py tests/families/test_supervigilancia.py
git commit -m "feat(supervigilancia): _head_info lee Content-Disposition vía HEAD"
```

---

### Task 3: `_fila_a_doc` — un bloque `s_dl_item` → `RawDocModel | None`

**Files:**
- Modify: `core/scrapers/families/supervigilancia.py`
- Test: `tests/families/test_supervigilancia.py`

**Interfaces:**
- Consumes: todos los helpers de Task 1 + `_head_info` de Task 2 (a través de `head_info` que se le pasa ya resuelto — `_fila_a_doc` NO hace red).
- Produces:
  - `_fila_a_doc(item, tipo: str, pref: str, head_info: dict, fini: str, ffin: str, hoy: datetime.date, on_progress) -> RawDocModel | None`
    - `item`: un `Tag` de BeautifulSoup con clase `s_dl_item`.
    - Pasos:
      1. `href = item.get("data-href") or (item.select_one("a.s_dl_btn_download") or {}).get("href", "")`. `doc_id = _id_de_href(href)`. Si no hay `doc_id` → `None`.
      2. `nombre_txt = _norm_texto((item.select_one(".s_dl_doc_name") or _texto_vacio).get_text(" ", strip=True))`.
      3. `meta_txt = _norm_texto((item.select_one(".s_dl_doc_meta") or _texto_vacio).get_text(" ", strip=True))`.
      4. `fecha = _fecha_de_meta(meta_txt, hoy)`. Si `None` → `on_progress(f"[{_SOURCE}] Aviso: {tipo} sin fecha «{nombre_txt[:70]}», se omite")` y `return None`.
      5. `if fecha.year < _ANIO_MINIMO: return None`. `iso = fecha.isoformat()`. `if iso < fini or iso > ffin: return None`.
      6. Número, primero que acierte: `_num_en_texto(head_info.get("filename") or "")` → `_num_al_inicio(nombre_txt)` → `_num_en_prosa(nombre_txt)`.
      7. `filename_stem = (head_info.get("filename") or "").rsplit(".", 1)[0] or None`.
      8. `title, unverified = _titulo(pref, numero, fecha.year, nombre_txt, filename_stem)`.
      9. `safe = _safe_title(title)`.
      10. `return RawDocModel(source=_SOURCE, link={"url": f"{_BASE}/web/content/{doc_id}?download=true", "method": "GET"}, title=title, tipo=tipo, f_public=iso, f_providencia=iso, detalle=nombre_txt or None, save_path=storage_path(_SOURCE, iso, tipo, f"{safe}(extension)"), title_unverified=unverified)`.
  - Módulo: `_texto_vacio` es un pequeño objeto con `.get_text(...)` que devuelve `""`; o simplemente usar `item.select_one(sel)` y comprobar `None` antes de `.get_text`. Elegir la forma más legible; no dejar `AttributeError` posible.

- [ ] **Step 1: Escribir los tests**

```python
import datetime

from bs4 import BeautifulSoup

from core.scrapers.families.supervigilancia import _fila_a_doc, _SOURCE

HOY = datetime.date(2026, 9, 10)
FINI, FFIN = "2000-01-01", "2100-12-31"


def _item(html: str):
    return BeautifulSoup(html, "html.parser").select_one("div.s_dl_item")


_ITEM_CON_NUM_LISTADO = _item(
    '<div class="s_dl_item" data-category="acuerdos" data-href="/web/content/10260?download=true">'
    '<span class="s_dl_file_size">394 Kb</span>'
    '<div class="s_dl_doc_type">resoluciones</div>'
    '<div class="s_dl_doc_name">20263200005647CS <b>Por la cual se actualiza el Manual</b></div>'
    '<div class="s_dl_doc_meta"><span>Publicación: 08/05/2026</span></div></div>'
)


def test_numero_desde_head_filename_gana():
    head = {"filename": "20261000015947CS RESOLUCION DE LINEAMIENTOS Y PAGO.pdf", "content_length": 403369}
    doc = _fila_a_doc(_ITEM_CON_NUM_LISTADO, "Resolución", "R", head, FINI, FFIN, HOY, None)
    assert doc.title == "R_SVySP_20261000015947CS_2026"
    assert doc.title_unverified is False
    assert doc.tipo == "Resolución"
    assert doc.f_public == "2026-05-08" and doc.f_providencia == "2026-05-08"
    assert doc.link == {"url": "https://www.supervigilancia.gov.co/web/content/10260?download=true", "method": "GET"}
    assert "verify" not in doc.link
    assert doc.save_path.startswith(f"{_SOURCE}/2026-05-08/Resolución/")


def test_numero_desde_listado_cuando_head_sin_filename():
    head = {"filename": None, "content_length": None}
    doc = _fila_a_doc(_ITEM_CON_NUM_LISTADO, "Resolución", "R", head, FINI, FFIN, HOY, None)
    assert doc.title == "R_SVySP_20263200005647CS_2026"


def test_numero_en_prosa():
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/900?download=true">'
        '<div class="s_dl_doc_name">POR MEDIO DE LA CUAL SE EFECTÚA UNA CORRECCIÓN A LA RESOLUCIÓN No. 2023320000649</div>'
        '<div class="s_dl_doc_meta"><span>|Expedición: 30/10/2025</span></div></div>'
    )
    doc = _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, HOY, None)
    assert doc.title == "R_SVySP_2023320000649_2025"


def test_sin_numero_se_guarda_con_title_unverified():
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/901?download=true">'
        '<div class="s_dl_doc_name"><strong>LINEAMIENTOS PARA LA AUTORIZACIÓN DE PRESTACIÓN DE SERVICIOS</strong></div>'
        '<div class="s_dl_doc_meta"><span>Expedición: 15/09/2025</span></div></div>'
    )
    doc = _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, HOY, None)
    assert doc.title == "LINEAMIENTOS PARA LA AUTORIZACIÓN DE PRESTACIÓN DE SERVICIOS"
    assert doc.title_unverified is True


def test_fecha_hoy():
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/902?download=true">'
        '<div class="s_dl_doc_name">20263100016027CS - Manual</div>'
        '<div class="s_dl_doc_meta"><span>Publicación: Hoy</span><span>|</span><span>Expedición: --</span></div></div>'
    )
    doc = _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, HOY, None)
    assert doc.f_public == "2026-09-10"


def test_fecha_ausente_descarta_con_aviso():
    avisos = []
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/903?download=true">'
        '<div class="s_dl_doc_name">Algo sin fecha</div>'
        '<div class="s_dl_doc_meta"><span>Expedición: --</span></div></div>'
    )
    doc = _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, HOY, avisos.append)
    assert doc is None
    assert avisos and "sin fecha" in avisos[0]


def test_zero_width_en_titulo_se_limpia():
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/904?download=true">'
        '<div class="s_dl_doc_name">Res​olución sin número</div>'
        '<div class="s_dl_doc_meta"><span>Expedición: 01/02/2020</span></div></div>'
    )
    doc = _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, HOY, None)
    assert doc.title == "Resolución sin número"


def test_piso_2015():
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/905?download=true">'
        '<div class="s_dl_doc_name">Vieja</div>'
        '<div class="s_dl_doc_meta"><span>Expedición: 17/03/2009</span></div></div>'
    )
    assert _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, HOY, None) is None


def test_fuera_de_rango_fini_ffin():
    item = _item(
        '<div class="s_dl_item" data-href="/web/content/906?download=true">'
        '<div class="s_dl_doc_name">20251300003057CS x</div>'
        '<div class="s_dl_doc_meta"><span>Expedición: 04/03/2025</span></div></div>'
    )
    assert _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, "2026-01-01", "2026-12-31", HOY, None) is None


def test_etiquetas_basura_no_afectan_el_tipo():
    item = _item(
        '<div class="s_dl_item" data-category="circulares" data-href="/web/content/907?download=true">'
        '<div class="s_dl_doc_type">CIRCULAR</div>'
        '<div class="s_dl_doc_name">RESOLUCION No. 202540000099737CS - Por la cual...</div>'
        '<div class="s_dl_doc_meta"><span>Expedición: 01/12/2025</span></div></div>'
    )
    doc = _fila_a_doc(item, "Resolución", "R", {"filename": None, "content_length": None}, FINI, FFIN, HOY, None)
    assert doc.tipo == "Resolución"
    assert doc.title == "R_SVySP_202540000099737CS_2025"


def test_concepto_titulo_es_nombre_de_archivo():
    item = _item(
        '<div class="s_dl_item" data-category="decretos" data-href="/web/content/7786?download=true">'
        '<div class="s_dl_doc_type">circular</div>'
        '<div class="s_dl_doc_name"><strong>Renting operativo.pdf</strong></div>'
        '<div class="s_dl_doc_meta"><span>Expedición: <span>28/05/2018</span></span></div></div>'
    )
    doc = _fila_a_doc(item, "Concepto", "CTO", {"filename": "Renting operativo.pdf", "content_length": 2696244}, FINI, FFIN, HOY, None)
    assert doc.tipo == "Concepto"
    assert doc.title == "Renting operativo"
    assert doc.title_unverified is True
```

- [ ] **Step 2: Correr los tests y verlos fallar**

Run: `pytest tests/families/test_supervigilancia.py -k fila_a_doc -v`
Expected: FAIL con `ImportError: cannot import name '_fila_a_doc'`.

- [ ] **Step 3: Implementar `_fila_a_doc`**

```python
def _texto(item, sel: str) -> str:
    node = item.select_one(sel)
    return _norm_texto(node.get_text(" ", strip=True)) if node else ""


def _fila_a_doc(item, tipo, pref, head_info, fini, ffin, hoy, on_progress) -> Optional[RawDocModel]:
    href = item.get("data-href") or ""
    if not href:
        btn = item.select_one("a.s_dl_btn_download")
        href = btn.get("href", "") if btn else ""
    doc_id = _id_de_href(href)
    if not doc_id:
        return None

    nombre_txt = _texto(item, ".s_dl_doc_name")
    meta_txt = _texto(item, ".s_dl_doc_meta")

    fecha = _fecha_de_meta(meta_txt, hoy)
    if fecha is None:
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: {tipo} sin fecha «{nombre_txt[:70]}», se omite")
        return None
    if fecha.year < _ANIO_MINIMO:
        return None
    iso = fecha.isoformat()
    if iso < fini or iso > ffin:
        return None

    filename = head_info.get("filename") or ""
    numero = _num_en_texto(filename) or _num_al_inicio(nombre_txt) or _num_en_prosa(nombre_txt)
    filename_stem = filename.rsplit(".", 1)[0] or None if filename else None
    title, unverified = _titulo(pref, numero, fecha.year, nombre_txt, filename_stem)
    safe = _safe_title(title)

    return RawDocModel(
        source=_SOURCE,
        link={"url": f"{_BASE}/web/content/{doc_id}?download=true", "method": "GET"},
        title=title,
        tipo=tipo,
        f_public=iso,
        f_providencia=iso,
        detalle=nombre_txt or None,
        save_path=storage_path(_SOURCE, iso, tipo, f"{safe}(extension)"),
        title_unverified=unverified,
    )
```

- [ ] **Step 4: Correr los tests y verlos pasar**

Run: `pytest tests/families/test_supervigilancia.py -k fila_a_doc -v`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/supervigilancia.py tests/families/test_supervigilancia.py
git commit -m "feat(supervigilancia): _fila_a_doc convierte un bloque s_dl_item en RawDocModel"
```

---

### Task 4: `_items_de_listado` — bajar páginas y paginar hasta vacío

**Files:**
- Modify: `core/scrapers/families/supervigilancia.py`
- Test: `tests/families/test_supervigilancia.py`

**Interfaces:**
- Consumes: `_HEADERS`, `_BASE`, `_PAGINA_TOPE` de Task 1.
- Produces:
  - `_items_de_listado(session, url_pagina1: str, pagina: bool, on_progress) -> list` — devuelve la lista de `Tag` `div.s_dl_item` de todas las páginas.
    - Página 1: `GET url_pagina1`. Parsear con `BeautifulSoup(resp.text, "html.parser")`, `soup.select("div.s_dl_item")`.
    - Si `pagina` es `False` (Conceptos): devolver los items de la página 1 y parar.
    - Si `pagina` es `True` (Resoluciones): para `n` en `2.._PAGINA_TOPE`: `GET f"{url_pagina1}-pagina{n:02d}"`; parsear; si `select("div.s_dl_item")` está vacío → parar (no seguir con `n+1`); si no, extender la lista.
    - Cualquier `resp` con `status_code >= 400` o excepción de red en una página → `on_progress(f"[{_SOURCE}] Error consultando {url}: {e}")` y tratar esa página como vacía (parar la paginación; si es la página 1, devolver `[]`).
    - Timeout de cada GET: `timeout=60`.

- [ ] **Step 1: Escribir los tests**

```python
import requests
import responses

from core.scrapers.families.supervigilancia import _items_de_listado, _BASE

_RES1 = f"{_BASE}/2-1-3-2-resoluciones"


def _pagina(ids):
    bloques = "".join(
        f'<div class="s_dl_item" data-href="/web/content/{i}?download=true">'
        f'<div class="s_dl_doc_name">Doc {i}</div>'
        f'<div class="s_dl_doc_meta"><span>Expedición: 01/06/2025</span></div></div>'
        for i in ids
    )
    return f"<html><body>{bloques}</body></html>"


@responses.activate
def test_pagina_conceptos_una_sola_peticion():
    url = f"{_BASE}/2-1-3-8-conceptos-juridicos"
    responses.add(responses.GET, url, body=_pagina([1, 2, 3]))
    items = _items_de_listado(requests.Session(), url, pagina=False, on_progress=None)
    assert len(items) == 3
    assert len(responses.calls) == 1


@responses.activate
def test_resoluciones_pagina_hasta_vacio():
    responses.add(responses.GET, _RES1, body=_pagina([10, 11]))
    responses.add(responses.GET, f"{_RES1}-pagina02", body=_pagina([20, 21, 22]))
    responses.add(responses.GET, f"{_RES1}-pagina03", body=_pagina([]))  # vacía -> parar
    # -pagina04 NO se registra: si el scraper la pide, responses lanza ConnectionError y el test falla
    items = _items_de_listado(requests.Session(), _RES1, pagina=True, on_progress=None)
    assert len(items) == 5
    urls = [c.request.url for c in responses.calls]
    assert urls == [_RES1, f"{_RES1}-pagina02", f"{_RES1}-pagina03"]


@responses.activate
def test_error_en_pagina1_devuelve_vacio_con_aviso():
    avisos = []
    responses.add(responses.GET, _RES1, status=502)
    items = _items_de_listado(requests.Session(), _RES1, pagina=True, on_progress=avisos.append)
    assert items == []
    assert avisos and "Error consultando" in avisos[0]


@responses.activate
def test_tope_duro_de_paginas(monkeypatch):
    monkeypatch.setattr("core.scrapers.families.supervigilancia._PAGINA_TOPE", 3)
    responses.add(responses.GET, _RES1, body=_pagina([1]))
    responses.add(responses.GET, f"{_RES1}-pagina02", body=_pagina([2]))
    responses.add(responses.GET, f"{_RES1}-pagina03", body=_pagina([3]))
    items = _items_de_listado(requests.Session(), _RES1, pagina=True, on_progress=None)
    assert len(items) == 3  # para en pagina03 por el tope, no pide pagina04
```

- [ ] **Step 2: Correr los tests y verlos fallar**

Run: `pytest tests/families/test_supervigilancia.py -k items_de_listado -v`
Expected: FAIL con `ImportError`.

Nota: los tests importan la constante `_PAGINA_TOPE` vía `monkeypatch.setattr`; el bucle debe leer `_PAGINA_TOPE` del módulo en tiempo de ejecución (usar `range(2, _PAGINA_TOPE + 1)` dentro de la función, no capturarlo antes).

- [ ] **Step 3: Implementar `_items_de_listado`**

```python
def _pagina_items(session, url: str, on_progress) -> Optional[list]:
    """Devuelve la lista de items de una página, o None si la petición falló."""
    try:
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        if on_progress:
            on_progress(f"[{_SOURCE}] Error consultando {url}: {e}")
        return None
    return BeautifulSoup(resp.text, "html.parser").select("div.s_dl_item")


def _items_de_listado(session, url_pagina1: str, pagina: bool, on_progress) -> list:
    items = _pagina_items(session, url_pagina1, on_progress)
    if not items:
        return []
    todos = list(items)
    if not pagina:
        return todos
    for n in range(2, _PAGINA_TOPE + 1):
        pagina_items = _pagina_items(session, f"{url_pagina1}-pagina{n:02d}", on_progress)
        if not pagina_items:
            break
        todos.extend(pagina_items)
    return todos
```

- [ ] **Step 4: Correr los tests y verlos pasar**

Run: `pytest tests/families/test_supervigilancia.py -k items_de_listado -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/supervigilancia.py tests/families/test_supervigilancia.py
git commit -m "feat(supervigilancia): _items_de_listado pagina resoluciones hasta página vacía"
```

---

### Task 5: `ScrapSupervigilancia.scrap` — orquestación, HEAD por fila, dedup

**Files:**
- Modify: `core/scrapers/families/supervigilancia.py`
- Test: `tests/families/test_supervigilancia.py`

**Interfaces:**
- Consumes: `_SECCIONES`, `_items_de_listado`, `_head_info`, `_fila_a_doc`, `_HEADERS`.
- Produces:
  - `@register_family("supervigilancia")` sobre `class ScrapSupervigilancia(BaseScrapper)`.
  - `__init__(self): self.source = _SOURCE`.
  - `scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]`:
    - `session = requests.Session(); session.headers.update(_HEADERS)` (sin `session.verify = False`).
    - `hoy = datetime.date.today()`.
    - `docs: List[RawDocModel] = []`; `vistos_id: set[str] = set()`; `vistos_archivo: set[tuple] = set()`.
    - Para `(url, tipo, pref)` en `_SECCIONES`:
      - chequear `stop_event` (`if stop_event is not None and stop_event.is_set(): return docs[:limit]`).
      - `on_progress(f"[{_SOURCE}] Procesando {tipo}...")`.
      - `pagina = (pref == "R")`.
      - `items = _items_de_listado(session, url, pagina, on_progress)`.
      - Para cada `item`:
        - `stop_event` de nuevo → `return docs[:limit]`.
        - `doc_id = _id_de_href(item.get("data-href") or "")` — si `None`, `continue`.
        - **dedup primaria:** `if doc_id in vistos_id: continue`. `vistos_id.add(doc_id)`.
        - `head = _head_info(session, f"{_BASE}/web/content/{doc_id}?download=true")`.
        - **dedup secundaria:** `clave = (head["content_length"], head["filename"])`; `if clave[0] is not None and clave in vistos_archivo: on_progress(aviso "duplicado (mismo archivo)"); continue`. Si `clave[0] is not None`: `vistos_archivo.add(clave)`.
        - `doc = _fila_a_doc(item, tipo, pref, head, fini, ffin, hoy, on_progress)`.
        - `if doc is None: continue`.
        - `docs.append(doc)`; `if len(docs) >= limit: return docs[:limit]`.
    - `return docs[:limit]`.

- [ ] **Step 1: Escribir los tests end-to-end**

```python
import datetime

import requests
import responses

from core.scrapers.families.supervigilancia import ScrapSupervigilancia, _BASE
from core.scrapers.registry import FAMILY_REGISTRY, resolve_scraper

_RES1 = f"{_BASE}/2-1-3-2-resoluciones"
_CONC = f"{_BASE}/2-1-3-8-conceptos-juridicos"


def _bloque(i, nombre, meta):
    return (
        f'<div class="s_dl_item" data-href="/web/content/{i}?download=true">'
        f'<div class="s_dl_doc_name">{nombre}</div>'
        f'<div class="s_dl_doc_meta"><span>{meta}</span></div></div>'
    )


def _head(url, filename=None, length=None):
    headers = {}
    if filename is not None:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    if length is not None:
        headers["Content-Length"] = str(length)
    responses.add(responses.HEAD, url, headers=headers)


def _cd_url(i):
    return f"{_BASE}/web/content/{i}?download=true"


@responses.activate
def test_scrap_end_to_end_dos_secciones():
    responses.add(responses.GET, _RES1, body=(
        _bloque(100, "20261000000001CS Uno", "Publicación: 01/03/2026")
        + _bloque(101, "Sin número dos", "Expedición: 02/03/2026")
    ))
    responses.add(responses.GET, f"{_RES1}-pagina02", body="<html></html>")  # vacía
    responses.add(responses.GET, _CONC, body=_bloque(200, "Renting operativo.pdf", "Expedición: 28/05/2018"))
    _head(_cd_url(100), filename="20261000000001CS Uno.pdf", length=111)
    _head(_cd_url(101), filename=None, length=222)
    _head(_cd_url(200), filename="Renting operativo.pdf", length=333)

    docs = ScrapSupervigilancia().scrap("2000-01-01", "2100-12-31")
    titles = sorted(d.title for d in docs)
    assert titles == ["Renting operativo", "R_SVySP_20261000000001CS_2026", "Sin número dos"]
    assert {d.tipo for d in docs} == {"Resolución", "Concepto"}


@responses.activate
def test_scrap_dedup_primaria_por_id():
    # el mismo id en página 1 y página 2 -> un solo doc, un solo HEAD
    responses.add(responses.GET, _RES1, body=_bloque(100, "20261000000001CS Uno", "Publicación: 01/03/2026"))
    responses.add(responses.GET, f"{_RES1}-pagina02", body=_bloque(100, "20261000000001CS Uno (repe)", "Publicación: 01/03/2026"))
    responses.add(responses.GET, f"{_RES1}-pagina03", body="<html></html>")
    responses.add(responses.GET, _CONC, body="<html></html>")
    _head(_cd_url(100), filename="20261000000001CS.pdf", length=111)

    docs = ScrapSupervigilancia().scrap("2000-01-01", "2100-12-31")
    assert len(docs) == 1
    assert sum(1 for c in responses.calls if c.request.method == "HEAD") == 1


@responses.activate
def test_scrap_dedup_secundaria_por_content_length_y_filename():
    responses.add(responses.GET, _RES1, body=(
        _bloque(100, "Res A", "Publicación: 01/03/2026")
        + _bloque(200, "Res B", "Publicación: 01/03/2026")
    ))
    responses.add(responses.GET, f"{_RES1}-pagina02", body="<html></html>")
    responses.add(responses.GET, _CONC, body="<html></html>")
    _head(_cd_url(100), filename="20261000015947CS ALGO.pdf", length=403369)
    _head(_cd_url(200), filename="20261000015947CS ALGO.pdf", length=403369)  # mismo archivo, id distinto

    avisos = []
    docs = ScrapSupervigilancia().scrap("2000-01-01", "2100-12-31", on_progress=avisos.append)
    assert len(docs) == 1
    assert any("mismo archivo" in a for a in avisos)


@responses.activate
def test_scrap_head_con_error_de_red_no_rompe():
    responses.add(responses.GET, _RES1, body=_bloque(100, "20263200005647CS Uno", "Publicación: 01/03/2026"))
    responses.add(responses.GET, f"{_RES1}-pagina02", body="<html></html>")
    responses.add(responses.GET, _CONC, body="<html></html>")
    responses.add(responses.HEAD, _cd_url(100), body=requests.ConnectionError("boom"))

    docs = ScrapSupervigilancia().scrap("2000-01-01", "2100-12-31")
    assert len(docs) == 1
    assert docs[0].title == "R_SVySP_20263200005647CS_2026"  # cae al número del listado


@responses.activate
def test_scrap_respeta_limit():
    responses.add(responses.GET, _RES1, body="".join(
        _bloque(i, f"2026100000000{i}CS x", "Publicación: 01/03/2026") for i in range(1, 6)
    ))
    responses.add(responses.GET, f"{_RES1}-pagina02", body="<html></html>")
    responses.add(responses.GET, _CONC, body="<html></html>")
    for i in range(1, 6):
        _head(_cd_url(i), filename=f"2026100000000{i}CS.pdf", length=i)
    docs = ScrapSupervigilancia().scrap("2000-01-01", "2100-12-31", limit=2)
    assert len(docs) == 2


def test_familia_registrada():
    assert FAMILY_REGISTRY.get("supervigilancia") is ScrapSupervigilancia
    assert isinstance(resolve_scraper("supervigilancia", {}), ScrapSupervigilancia)
```

- [ ] **Step 2: Correr los tests y verlos fallar**

Run: `pytest tests/families/test_supervigilancia.py -k "scrap or familia_registrada" -v`
Expected: FAIL con `ImportError: cannot import name 'ScrapSupervigilancia'`.

- [ ] **Step 3: Implementar la clase y `scrap`**

```python
@register_family("supervigilancia")
class ScrapSupervigilancia(BaseScrapper):
    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update(_HEADERS)  # TLS válido: sin verify=False
        hoy = datetime.date.today()
        docs: List[RawDocModel] = []
        vistos_id: set = set()
        vistos_archivo: set = set()

        for url, tipo, pref in _SECCIONES:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            if on_progress:
                on_progress(f"[{_SOURCE}] Procesando {tipo}...")
            items = _items_de_listado(session, url, pref == "R", on_progress)

            for item in items:
                if stop_event is not None and stop_event.is_set():
                    return docs[:limit]
                doc_id = _id_de_href(item.get("data-href") or "")
                if not doc_id or doc_id in vistos_id:
                    continue
                vistos_id.add(doc_id)

                head = _head_info(session, f"{_BASE}/web/content/{doc_id}?download=true")
                clave = (head["content_length"], head["filename"])
                if clave[0] is not None:
                    if clave in vistos_archivo:
                        if on_progress:
                            on_progress(f"[{_SOURCE}] Aviso: {tipo} {doc_id} es el mismo archivo que otro ya visto, se omite")
                        continue
                    vistos_archivo.add(clave)

                doc = _fila_a_doc(item, tipo, pref, head, fini, ffin, hoy, on_progress)
                if doc is None:
                    continue
                docs.append(doc)
                if len(docs) >= limit:
                    return docs[:limit]

        return docs[:limit]
```

- [ ] **Step 4: Correr los tests y verlos pasar**

Run: `pytest tests/families/test_supervigilancia.py -v`
Expected: PASS (toda la suite: helpers + head_info + fila_a_doc + items_de_listado + scrap + familia_registrada).

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/supervigilancia.py tests/families/test_supervigilancia.py
git commit -m "feat(supervigilancia): ScrapSupervigilancia.scrap orquesta secciones, HEAD y dedup"
```

---

### Task 6: Registrar el módulo en `families/__init__.py`

**Files:**
- Modify: `core/scrapers/families/__init__.py:1`

**Interfaces:**
- Consumes: el módulo `supervigilancia` de Task 5.
- Produces: el `import` del módulo, para que el decorador `@register_family` corra al importar el paquete (así lo hacen las 26 familias actuales).

- [ ] **Step 1: Escribir el test**

```python
# en tests/families/test_supervigilancia.py
def test_registrada_al_importar_el_paquete():
    import importlib
    import core.scrapers.families as fam
    importlib.reload(fam)
    from core.scrapers.registry import FAMILY_REGISTRY
    assert "supervigilancia" in FAMILY_REGISTRY
```

- [ ] **Step 2: Correr el test y verlo fallar**

Run: `pytest tests/families/test_supervigilancia.py::test_registrada_al_importar_el_paquete -v`
Expected: FAIL (el paquete no importa `supervigilancia`, así que tras `reload` la clave no está garantizada por el paquete).

- [ ] **Step 3: Añadir el import**

En `core/scrapers/families/__init__.py`, línea 1, añadir `, supervigilancia` al final de la lista de imports (antes del comentario `# noqa: F401`):

```python
from . import constitucional, samai, corte_suprema, jep, cndj, adr, adres, ane, anh, rama_judicial, mincit, madr, minambiente, minvivienda, mineducacion, mininterior, mindeporte, minjusticia, minenergia, mintrabajo, superfinanciera, supersalud, ssf, snr, supersociedades, supersolidaria, supervigilancia  # noqa: F401
```

- [ ] **Step 4: Correr el test y verlo pasar**

Run: `pytest tests/families/test_supervigilancia.py -v`
Expected: PASS (toda la suite).

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/__init__.py tests/families/test_supervigilancia.py
git commit -m "feat(supervigilancia): registrar el módulo en families/__init__.py"
```

---

### Task 7: Sembrar la familia y la fuente

**Files:**
- Modify: `core/seed.py` — el dict `_FAMILIES` (una sola tabla `key → (display_name, description)`, ~línea 5-105; la entrada nueva va junto a `"superfinanciera"`…`"supersolidaria"`) y el bloque de llamadas `repository.create_source_if_missing(...)` de fuente única (~línea 207-230, después de `supersolidaria`).
- Modify: `tests/test_seed.py:45`, `tests/test_seed.py:48`, `tests/test_seed.py:58-64` (el `assert {f.key …} == { … }`), `tests/test_seed.py:66-69`

**Interfaces:**
- Consumes: nada de tasks anteriores (sólo la existencia de la familia técnica `"supervigilancia"` en el registro, ya lograda en Task 6, aunque `seed.py` no la importa directamente).
- Produces: una `source_family` con `key="supervigilancia"` y una `source` con `name="Superintendencia de Vigilancia y Seguridad Privada"`, `family_key="supervigilancia"`, `family_params={}`.

- [ ] **Step 1: Actualizar los conteos y el conjunto en `tests/test_seed.py`**

En `tests/test_seed.py`:
- Línea 45: `assert len(families) == 26` → `assert len(families) == 27`
- Línea 48: `assert len(sources) == 1 + 28 + 23 + 33 + 6` → `assert len(sources) == 1 + 28 + 24 + 33 + 6`
- Línea 66 (comentario): cambiar `23 (fuente única: …` para añadir `, supervigilancia` al final de la lista enumerada, y `+ 23 (` → `+ 24 (`
- Línea 69: `assert len(sources) == 1 + 28 + 23 + 33 + 6` → `assert len(sources) == 1 + 28 + 24 + 33 + 6`
- En el `assert {f.key for f in families} == { … }` (línea ~58-64): añadir `"supervigilancia",` a la última línea del conjunto (junto a `"supersalud", "ssf", "snr", "supersociedades", "supersolidaria",`).

- [ ] **Step 2: Correr `tests/test_seed.py` y verlo fallar**

Run: `pytest tests/test_seed.py -v`
Expected: FAIL — `len(families) == 27` falla (todavía hay 26), y el conjunto de claves no incluye `"supervigilancia"`.

- [ ] **Step 3: Añadir la familia y la fuente en `core/seed.py`**

En el dict `_FAMILIES`, junto a las entradas `"superfinanciera"`, `"supersalud"`, `"ssf"`, `"snr"`, `"supersociedades"`, `"supersolidaria"`, añadir:

```python
    "supervigilancia": (
        "Superintendencia de Vigilancia y Seguridad Privada",
        "Normativa (resoluciones) y conceptos jurídicos publicados por la "
        "Superintendencia de Vigilancia y Seguridad Privada",
    ),
```

En el bloque de `create_source_if_missing` (después del de `supersolidaria`), añadir:

```python
    repository.create_source_if_missing(
        db, family_key="supervigilancia",
        name="Superintendencia de Vigilancia y Seguridad Privada", family_params={}
    )
```

- [ ] **Step 4: Correr las pruebas dirigidas y verlas pasar**

Run: `pytest tests/families/test_supervigilancia.py tests/test_seed.py -v`
Expected: PASS (toda la suite de la familia + `test_seed` con los conteos nuevos, incl. el test de idempotencia que siembra dos veces).

- [ ] **Step 5: Commit**

```bash
git add core/seed.py tests/test_seed.py
git commit -m "feat(supervigilancia): sembrar familia y fuente única"
```

---

## Self-Review

**1. Spec coverage:**

| Sección del spec | Task |
|---|---|
| Transporte `requests`+bs4, TLS válido sin `verify=False` | Task 5 (Global Constraints) |
| Cabecera `Accept-Language: es-CO` obligatoria | Task 1 (`_HEADERS`), Task 5 |
| HEAD por documento para leer `Content-Disposition` | Task 2 (`_head_info`), Task 5 |
| Bloque `s_dl_item`: id/href, título, meta, tipo por sección | Task 3 (`_fila_a_doc`) |
| Ignorar `data-category` / `.s_dl_doc_type` | Task 3 (test `test_etiquetas_basura_no_afectan_el_tipo`) |
| Normalización NFC + `​` + colapso de espacios | Task 1 (`_norm_texto`), Task 3 (test zero-width) |
| Orden de extracción del número (filename → inicio listado → prosa → sin número) | Task 1 (helpers), Task 3 (`_fila_a_doc` + tests 1-4) |
| Título `{pref}_SVySP_{numero}_{anio}`, número literal | Task 1 (`_titulo`) |
| Sin número → título descriptivo, `title_unverified=True`, se guarda | Task 1 (`_titulo`), Task 3 (`test_sin_numero_se_guarda…`) |
| Sin `resolve_unverified_document` | (no se implementa; `BaseScrapper` default) — cubierto por omisión |
| Fecha `DD/MM/AAAA`, `"Hoy"` → hoy, `"--"`/vacía → descartar con aviso | Task 1 (`_fecha_de_meta`), Task 3 (tests fecha) |
| `f_public` == `f_providencia` | Task 3 (`_fila_a_doc`, test) |
| Piso `_ANIO_MINIMO = 2015` + rango `fini`/`ffin` | Task 3 (tests piso y rango) |
| Paginación `-paginaNN` hasta página vacía, tope 20 | Task 4 (`_items_de_listado`) |
| Conceptos: una sola página, sin paginación | Task 4 (`pagina=False`, test) |
| Dedup primaria por `{id}` | Task 5 (test `test_scrap_dedup_primaria_por_id`) |
| Dedup secundaria por `(Content-Length, filename)` | Task 5 (test `test_scrap_dedup_secundaria…`) |
| `save_path = storage_path(_SOURCE, iso, tipo, "{safe}(extension)")` | Task 3 (`_fila_a_doc`) |
| `_SOURCE` == `name` de seed | Task 1 (test `test_source_string_matches_seed_name`), Task 7 |
| Registro en `FAMILY_REGISTRY` vía decorador | Task 5, Task 6 |
| `families/__init__.py` import | Task 6 |
| `core/seed.py` familia + fuente | Task 7 |
| `tests/test_seed.py` conteos `26→27`, `23→24`, set de claves | Task 7 |
| Sin migración Alembic | (no aplica — ninguna task crea migración) |
| HEAD que lanza excepción → no rompe, cae a respaldos | Task 2 (test), Task 5 (`test_scrap_head_con_error_de_red_no_rompe`) |
| `stop_event` / `limit` respetados | Task 5 (`test_scrap_respeta_limit`; `stop_event` chequeado en el bucle) |

Fuera de alcance en el spec (Circulares, Decretos, Directivas): sin task, correcto.

**2. Placeholder scan:** sin `TBD`/`TODO`/"handle edge cases"/"similar to Task N". Todos los steps de código traen el código real. La única frase condicional ("elegir la forma más legible" en Task 3 sobre `_texto_vacio`) va acompañada del código concreto (`_texto` con guard `if node else ""`).

**3. Type consistency:**
- `_head_info` devuelve siempre `{"filename": str|None, "content_length": int|None}` — mismas claves en Task 2, Task 3 (`head_info.get("filename")`, `head_info.get("content_length")`) y Task 5 (`head["content_length"]`, `head["filename"]`). Consistente (se usan tanto `.get(...)` como `[...]`; ambas válidas porque las claves siempre existen).
- `_fila_a_doc(item, tipo, pref, head_info, fini, ffin, hoy, on_progress)` — misma firma en la definición (Task 3 Step 3) y en todas las llamadas de los tests y de `scrap` (Task 5).
- `_items_de_listado(session, url_pagina1, pagina, on_progress)` — Task 4 def y Task 5 llamada (`_items_de_listado(session, url, pref == "R", on_progress)`) coinciden posicionalmente.
- `_titulo(pref, numero, anio, texto_crudo, filename_stem)` — 5 args en def (Task 1) y en llamada (Task 3): `_titulo(pref, numero, fecha.year, nombre_txt, filename_stem)`. Consistente.
- Prefijos: `"R"` y `"CTO"` en `_SECCIONES` (Task 1) == los usados en `_titulo` y en `pref == "R"` (Task 4/5). Consistente.

Sin inconsistencias.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-10-fuente-supervigilancia.md`. Two execution options:

1. **Subagent-Driven (recommended)** — un subagente fresco por task, revisión entre tasks, iteración rápida.
2. **Inline Execution** — ejecutar las tasks en esta sesión con checkpoints de revisión.

¿Cuál prefieres?
