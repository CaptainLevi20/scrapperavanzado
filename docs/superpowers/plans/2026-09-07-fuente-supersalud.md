# Fuente Supersalud — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir la fuente "Superintendencia Nacional de Salud" (familia técnica `supersalud`) que raspa Resoluciones y Circulares Externas del portal SharePoint de Supersalud.

**Architecture:** Un módulo plano `core/scrapers/families/supersalud.py` con `@register_family("supersalud")`. El transporte no usa el REST de búsqueda de SharePoint (bloqueado por un WAF) sino el endpoint CSOM `client.svc/ProcessQuery` con un *form digest* obtenido de `/_api/contextinfo`. Por cada carpeta (`Resoluciones`, `CircularesExterna`) y cada año del rango (piso 2015) se pagina de 500 en 500; cada fila se mapea a `RawDocModel` y el PDF/ZIP se descarga directo desde `docs.supersalud.gov.co`.

**Tech Stack:** Python, `requests`, `pytest`, `responses` (mock HTTP en tests). Sin BeautifulSoup (la respuesta es JSON). Sin navegador.

**Spec:** `docs/superpowers/specs/2026-09-07-fuente-supersalud-design.md`

## Global Constraints

- **Sigla de entidad en el título:** `SNS` (verbatim).
- **Formato de título:** `{letra}_SNS_{numero:04d}_{anio}` con `letra` = `R` (Resolución) / `C` (Circular Externa); `anio` = año de **publicación** (`f_public[:4]`).
- **Anexo con número parseable:** sufijo **fijo** `_A01` (nunca `_A02`+). Anexo sin número → `title_unverified`, sin sufijo.
- **Cobertura:** solo publicaciones con `f_public >= 2015-01-01`. Si el rango pedido empieza antes, el piso sube a `2015`.
- **Sin Actas de Conciliación.** Solo carpetas `Resoluciones` y `CircularesExterna`.
- **Resoluciones:** todas, sin filtro de contenido administrativo.
- **Anexos:** documento propio (fila `documents`), sin agrupación madre↔anexo. Nada del andamiaje "N anexos" de `superfinanciera`.
- **Flags `BaseScrapper`:** `filters_by_publication_date = True`; los otros dos quedan en su valor por defecto.
- **Decodificación:** las respuestas de `/_api/contextinfo` y `/_vti_bin/client.svc/ProcessQuery` traen BOM UTF-8 → `json.loads(resp.content.decode("utf-8-sig"))`.
- **`review_status`:** por defecto (`pending`). Sin `auto_review_status` en el seed.
- Ejecutar Python siempre con `.venv/Scripts/python` / `.venv/Scripts/pytest` (shell: Git Bash en Windows nativo).

---

## File Structure

- **Create `core/scrapers/families/supersalud.py`** — la familia completa: constantes, helpers de parseo (fecha, anexo, número, título, saneo), helpers de transporte (`_form_digest`, `_build_body`, `_process_query`), mapeo `_fila_a_doc`, y la clase `ScrapSupersalud`. Un solo archivo, ~200 líneas, al estilo `core/scrapers/families/mincit.py`.
- **Modify `core/scrapers/families/__init__.py`** — añadir `supersalud` a la línea de import de registro.
- **Modify `core/seed.py`** — entrada en `_FAMILIES` + una llamada `repository.create_source_if_missing(...)`.
- **Create `tests/families/test_supersalud.py`** — unit tests de los helpers + tests de `_fila_a_doc` + tests de `scrap()` con `responses`.
- **Modify `docs/guia-despliegue-sistemas.md`** — nota corta de la fuente nueva (dónde termine la lista de fuentes / familias).

---

## Task 1: Helpers de parseo (fecha, anexo, número, título)

**Files:**
- Create: `core/scrapers/families/supersalud.py`
- Test: `tests/families/test_supersalud.py`

**Interfaces:**
- Produces:
  - `_sin_acentos(s: str) -> str`
  - `_es_anexo(title: str | None) -> bool`
  - `_parse_numero(numero_raw: str | None, title: str | None) -> int | None`
  - `_safe_title(title: str) -> str`
  - `_titulo(letra: str, numero_raw: str | None, title_raw: str, anio: str, es_anexo: bool) -> tuple[str, bool]` — devuelve `(title, title_unverified)`
  - `_fecha_publicacion(raw: str | None) -> str | None` — ISO `YYYY-MM-DD` o `None`

- [ ] **Step 1: Write the failing tests**

Create `tests/families/test_supersalud.py`:

```python
from core.scrapers.families.supersalud import (
    _es_anexo,
    _fecha_publicacion,
    _parse_numero,
    _safe_title,
    _titulo,
)


# ---- _es_anexo ----
def test_es_anexo_true_for_accented_uppercase_prefix():
    assert _es_anexo("Anexo resolución número 2024910010006782-6 de 2024") is True
    assert _es_anexo("ANEXO RESOLUCION No. 2022910010007513-6 de 2022") is True


def test_es_anexo_false_for_normal_title():
    assert _es_anexo("Resolución número 2024910010006787-6 de 2024") is False
    assert _es_anexo("") is False
    assert _es_anexo(None) is False


# ---- _parse_numero ----
def test_parse_numero_radicado_form_takes_last_six_of_twelve_block():
    assert _parse_numero("2026151000000002-5", "") == 2
    assert _parse_numero("2022130000000054-5", "") == 54
    assert _parse_numero("2024910010006787-6", "") == 6787


def test_parse_numero_radicado_form_without_dash():
    assert _parse_numero("20221300000000545", "") == 54


def test_parse_numero_radicado_found_inside_anexo_title():
    assert _parse_numero(None, "Anexo resolución número 2024910010006782-6 de 2024") == 6782


def test_parse_numero_classic_form_strips_leading_zeros_and_trailing_year():
    assert _parse_numero("047", "") == 47
    assert _parse_numero("003 de 2019", "") == 3
    assert _parse_numero("10924 de 2018", "") == 10924


def test_parse_numero_falls_back_to_title_when_numero_raw_blank():
    assert _parse_numero("  ", "Circular Externa 006 de 2016") == 6


def test_parse_numero_returns_none_for_unparseable():
    assert _parse_numero("", "Por medio de la cual se ordena la toma de posesión") is None
    assert _parse_numero("010 de 2017     010 de 2017", "") is None
    assert _parse_numero(None, None) is None


# ---- _safe_title ----
def test_safe_title_replaces_path_invalid_chars_and_trims():
    assert _safe_title('Doc/con "raros": x|y*') == "Doc-con -raros-- x-y-"
    assert _safe_title("  x.  ") == "x"


def test_safe_title_truncates_to_120():
    assert len(_safe_title("z" * 300)) == 120


# ---- _titulo ----
def test_titulo_verified_canonical_code():
    assert _titulo("C", "2026151000000002-5", "irrelevante", "2026", False) == ("C_SNS_0002_2026", False)
    assert _titulo("R", "2024910010006787-6", "irrelevante", "2024", False) == ("R_SNS_6787_2024", False)


def test_titulo_verified_anexo_gets_fixed_a01_suffix():
    assert _titulo(
        "R", None, "Anexo resolución número 2024910010006782-6 de 2024", "2024", True
    ) == ("R_SNS_6782_2024_A01", False)


def test_titulo_unverified_keeps_raw_title_trimmed_to_120():
    title, unv = _titulo("R", "", "Por medio de la cual se ordena la toma de posesión", "2013", False)
    assert unv is True
    assert title == "Por medio de la cual se ordena la toma de posesión"


def test_titulo_unverified_anexo_has_no_suffix():
    title, unv = _titulo("C", "", "Anexo - Tablas de referencia - CE", "2026", True)
    assert unv is True
    assert title == "Anexo - Tablas de referencia - CE"
    assert not title.endswith("_A01")


# ---- _fecha_publicacion ----
def test_fecha_publicacion_takes_first_half_of_doubled_value():
    raw = "2026-09-04T05:00:00Z\n\n2026-09-04T05:00:00.0000000Z"
    assert _fecha_publicacion(raw) == "2026-09-04"


def test_fecha_publicacion_single_value():
    assert _fecha_publicacion("2021-08-18T05:00:00.0000000Z") == "2021-08-18"


def test_fecha_publicacion_none_when_missing_or_unparseable():
    assert _fecha_publicacion(None) is None
    assert _fecha_publicacion("") is None
    assert _fecha_publicacion("sin fecha") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/families/test_supersalud.py -q`
Expected: FAIL — `ModuleNotFoundError` / `ImportError` (el módulo aún no existe).

- [ ] **Step 3: Write the module with the helpers**

Create `core/scrapers/families/supersalud.py`:

```python
import datetime
import re
import unicodedata
from typing import List, Optional, Tuple

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_BASE = "https://www.supersalud.gov.co/es-co"
_CONTEXTINFO = f"{_BASE}/_api/contextinfo"
_PROCESS_QUERY = f"{_BASE}/_vti_bin/client.svc/ProcessQuery"
_DOCS_PREFIX = "https://docs.supersalud.gov.co/PortalWeb/Juridica"

# (carpeta en docs.supersalud, tipo mostrado, letra del código de título)
_CATEGORIAS = [
    ("Resoluciones", "Resolución", "R"),
    ("CircularesExterna", "Circular Externa", "C"),
]

_ANIO_MINIMO = 2015
_PAGE = 500

_SOURCE = "Superintendencia Nacional de Salud"

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
# año (4) + bloque de 12 dígitos (dependencia 6 + consecutivo 6) + sufijo "-D" o "D"
_RADICADO_RE = re.compile(r"(\d{4})(\d{12})-?\d?\b")
_CLASICO_RE = re.compile(r"^0*(\d{1,5})$")
_SUFIJO_ANIO_RE = re.compile(r"\s+de\s+\d{4}\s*$", re.IGNORECASE)
_ANEXO_PREFIJO_RE = re.compile(r"^anexo\s+", re.IGNORECASE)


def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def _es_anexo(title: Optional[str]) -> bool:
    return _sin_acentos((title or "").strip()).lower().startswith("anexo")


def _parse_numero(numero_raw: Optional[str], title: Optional[str]) -> Optional[int]:
    base = (numero_raw or "").strip() or (title or "").strip()
    if not base:
        return None
    base = _sin_acentos(base)
    base = _ANEXO_PREFIJO_RE.sub("", base)
    base = re.sub(r"\s+", " ", base).strip()
    base = _SUFIJO_ANIO_RE.sub("", base).strip()

    m = _RADICADO_RE.search(base)
    if m:
        return int(m.group(2)[-6:])

    m = _CLASICO_RE.match(base)
    if m:
        return int(m.group(1))

    return None


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _titulo(
    letra: str, numero_raw: Optional[str], title_raw: str, anio: str, es_anexo: bool
) -> Tuple[str, bool]:
    numero = _parse_numero(numero_raw, title_raw)
    if numero is None:
        return (title_raw or "").strip()[:120], True
    base = f"{letra}_SNS_{numero:04d}_{anio}"
    if es_anexo:
        base = f"{base}_A01"
    return base, False


def _fecha_publicacion(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    candidato = raw.split("\n")[0].strip()[:10]
    try:
        datetime.date.fromisoformat(candidato)
    except ValueError:
        return None
    return candidato
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/families/test_supersalud.py -q`
Expected: PASS (todos los tests de este archivo).

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/supersalud.py tests/families/test_supersalud.py
git commit -m "feat(supersalud): helpers de parseo de fecha, anexo, número y título"
```

---

## Task 2: Mapeo fila → RawDocModel (`_fila_a_doc`)

**Files:**
- Modify: `core/scrapers/families/supersalud.py`
- Test: `tests/families/test_supersalud.py`

**Interfaces:**
- Consumes: `_es_anexo`, `_fecha_publicacion`, `_titulo`, `_safe_title` (Task 1); `storage_path` de `core.utils`; `RawDocModel` de `core.models`.
- Produces: `_fila_a_doc(fila: dict, tipo: str, letra: str, fini: str, ffin: str, on_progress) -> RawDocModel | None`
  - `fila` es un dict con claves `Title`, `Path`, `NumeroOWSTEXT`, `DescripcionOWSMTXT`, `FechadePublicacionOWSDATE`, `RefinableString00`, `FileExtension` (cualquiera puede venir `None` o ausente).
  - Devuelve `None` si: no hay `Path`; no hay fecha parseable; la fecha cae fuera de `[fini, ffin]`.

- [ ] **Step 1: Write the failing tests**

Añadir a `tests/families/test_supersalud.py`:

```python
from core.scrapers.families.supersalud import _fila_a_doc

_FILA_RESOLUCION = {
    "Title": "Resolución número 2024910010006787-6 de 2024",
    "Path": "https://docs.supersalud.gov.co/PortalWeb/Juridica/Resoluciones/Resolución número 2024910010006787-6 de 2024.pdf",
    "NumeroOWSTEXT": "2024910010006787-6",
    "DescripcionOWSMTXT": "Por la cual se efectúa un nombramiento en periodo de prueba.",
    "FechadePublicacionOWSDATE": "2024-07-09T05:00:00Z\n\n2024-07-09T05:00:00.0000000Z",
    "RefinableString00": "2024",
    "FileExtension": "pdf",
}


def test_fila_a_doc_maps_verified_resolucion():
    doc = _fila_a_doc(_FILA_RESOLUCION, "Resolución", "R", "2024-01-01", "2024-12-31", None)
    assert doc is not None
    assert doc.title == "R_SNS_6787_2024"
    assert doc.title_unverified is False
    assert doc.tipo == "Resolución"
    assert doc.source == "Superintendencia Nacional de Salud"
    assert doc.f_public == "2024-07-09"
    assert doc.f_providencia == "2024-07-09"
    assert doc.detalle == "Por la cual se efectúa un nombramiento en periodo de prueba."
    assert doc.link == {
        "url": _FILA_RESOLUCION["Path"],
        "method": "GET",
    }
    assert doc.save_path == (
        "Superintendencia Nacional de Salud/2024-07-09/Resolución/R_SNS_6787_2024(extension)"
    )


def test_fila_a_doc_zip_path_is_used_verbatim():
    fila = dict(_FILA_RESOLUCION)
    fila["Title"] = "Circular Externa 006 de 2016"
    fila["NumeroOWSTEXT"] = "006"
    fila["Path"] = "https://docs.supersalud.gov.co/PortalWeb/Juridica/CircularesExterna/Circular Externa 006 de 2016.zip"
    fila["FechadePublicacionOWSDATE"] = "2016-05-02T05:00:00Z"
    fila["FileExtension"] = "zip"
    doc = _fila_a_doc(fila, "Circular Externa", "C", "2015-01-01", "2016-12-31", None)
    assert doc.title == "C_SNS_0006_2016"
    assert doc.link["url"].endswith(".zip")


def test_fila_a_doc_anexo_gets_a01_suffix():
    fila = dict(_FILA_RESOLUCION)
    fila["Title"] = "Anexo resolución número 2024910010006782-6 de 2024"
    fila["NumeroOWSTEXT"] = "2024910010006782-6"
    doc = _fila_a_doc(fila, "Resolución", "R", "2024-01-01", "2024-12-31", None)
    assert doc.title == "R_SNS_6782_2024_A01"
    assert doc.title_unverified is False


def test_fila_a_doc_unverified_when_no_number():
    fila = dict(_FILA_RESOLUCION)
    fila["Title"] = "Por medio de la cual se ordena la toma de posesión"
    fila["NumeroOWSTEXT"] = ""
    doc = _fila_a_doc(fila, "Resolución", "R", "2024-01-01", "2024-12-31", None)
    assert doc.title == "Por medio de la cual se ordena la toma de posesión"
    assert doc.title_unverified is True
    # save_path saneado: exactamente 4 segmentos, sin caracteres inválidos en el archivo
    segmentos = doc.save_path.split("/")
    assert len(segmentos) == 4
    assert not any(c in segmentos[-1] for c in '\\/*?:"<>|')


def test_fila_a_doc_returns_none_outside_date_range():
    doc = _fila_a_doc(_FILA_RESOLUCION, "Resolución", "R", "2025-01-01", "2025-12-31", None)
    assert doc is None


def test_fila_a_doc_returns_none_without_path():
    fila = dict(_FILA_RESOLUCION)
    fila["Path"] = None
    assert _fila_a_doc(fila, "Resolución", "R", "2024-01-01", "2024-12-31", None) is None


def test_fila_a_doc_returns_none_and_warns_without_date():
    fila = dict(_FILA_RESOLUCION)
    fila["FechadePublicacionOWSDATE"] = None
    avisos = []
    assert _fila_a_doc(fila, "Resolución", "R", "2024-01-01", "2024-12-31", avisos.append) is None
    assert any("sin fecha" in m.lower() for m in avisos)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/families/test_supersalud.py -q -k fila_a_doc`
Expected: FAIL — `ImportError: cannot import name '_fila_a_doc'`.

- [ ] **Step 3: Implement `_fila_a_doc`**

Añadir a `core/scrapers/families/supersalud.py` (después de `_fecha_publicacion`):

```python
def _fila_a_doc(fila, tipo, letra, fini, ffin, on_progress) -> Optional[RawDocModel]:
    url = (fila.get("Path") or "").strip()
    if not url:
        return None

    f_public = _fecha_publicacion(fila.get("FechadePublicacionOWSDATE"))
    title_raw = (fila.get("Title") or "").strip()
    if f_public is None:
        if on_progress:
            on_progress(f"[{_SOURCE}] Aviso: fila sin fecha de publicación parseable «{title_raw[:80]}», se omite")
        return None
    if f_public < fini or f_public > ffin:
        return None

    es_anexo = _es_anexo(title_raw)
    title, unverified = _titulo(
        letra, fila.get("NumeroOWSTEXT"), title_raw, f_public[:4], es_anexo
    )
    safe = _safe_title(title)
    return RawDocModel(
        source=_SOURCE,
        link={"url": url, "method": "GET"},
        title=title,
        tipo=tipo,
        f_public=f_public,
        f_providencia=f_public,
        detalle=(fila.get("DescripcionOWSMTXT") or "").strip() or None,
        save_path=storage_path(_SOURCE, f_public, tipo, f"{safe}(extension)"),
        title_unverified=unverified,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/families/test_supersalud.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/supersalud.py tests/families/test_supersalud.py
git commit -m "feat(supersalud): mapeo de fila de búsqueda a RawDocModel"
```

---

## Task 3: Transporte CSOM (`_build_body`, `_form_digest`, `_process_query`)

**Files:**
- Modify: `core/scrapers/families/supersalud.py`
- Test: `tests/families/test_supersalud.py`

**Interfaces:**
- Consumes: `requests` (Session), constantes `_CONTEXTINFO`, `_PROCESS_QUERY`, `_DOCS_PREFIX` (Task 1).
- Produces:
  - `_build_body(carpeta: str, anio: int, start_row: int, row_limit: int = _PAGE) -> str` — XML CSOM listo para POST.
  - `_form_digest(session: requests.Session) -> str` — `FormDigestValue`.
  - `_process_query(session: requests.Session, digest: str, carpeta: str, anio: int, start_row: int, row_limit: int = _PAGE) -> list[dict]` — lista de filas (`ResultRows`). Lanza `RuntimeError` si la respuesta trae `ErrorInfo`.

**Contexto CSOM (verificado en vivo):** `KeywordQuery` TypeId `{80173281-fffd-47b6-9a49-312e06ff8428}`, `SearchExecutor` TypeId `{8d2ac302-db2f-46fe-9015-872b35f15098}`. El refiner de año es `RefinableString00:"ǂǂ<hex>"` donde `<hex>` = UTF-8 del año en hex minúscula (`2015` → `32303135`) y `ǂ` es `U+01C2`. `RowLimit` admite hasta 500; `StartRow` pagina. El `QueryTemplate` acota por `path:` a la carpeta en `docs.supersalud.gov.co`.

- [ ] **Step 1: Write the failing tests**

Añadir a `tests/families/test_supersalud.py`:

```python
import json

import responses

from core.scrapers.families.supersalud import _build_body, _form_digest, _process_query


def _bom(payload) -> bytes:
    return b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8")


def test_build_body_embeds_folder_year_hex_and_pagination():
    body = _build_body("CircularesExterna", 2015, 500, 500)
    assert "PortalWeb/Juridica/CircularesExterna" in body
    # 2015 -> UTF-8 hex
    assert "32303135" in body
    assert "ǂǂ" in body
    assert "<Parameter Type=\"Number\">500</Parameter>" in body  # RowLimit
    # TypeIds de KeywordQuery y SearchExecutor
    assert "80173281-fffd-47b6-9a49-312e06ff8428" in body
    assert "8d2ac302-db2f-46fe-9015-872b35f15098" in body


@responses.activate
def test_form_digest_decodes_bom_and_returns_value():
    responses.add(
        responses.POST,
        "https://www.supersalud.gov.co/es-co/_api/contextinfo",
        body=_bom({"FormDigestValue": "0xDEADBEEF"}),
        content_type="application/json",
    )
    session = __import__("requests").Session()
    assert _form_digest(session) == "0xDEADBEEF"


@responses.activate
def test_process_query_returns_result_rows_and_sends_digest_header():
    payload = [
        {"SchemaVersion": "15.0.0.0", "ErrorInfo": None},
        {
            "ResultTables": [
                {
                    "TableType": "RelevantResults",
                    "Properties": {},
                    "ResultRows": [
                        {"Title": "Circular externa número 2026151000000002-5 de 2026",
                         "Path": "https://docs.supersalud.gov.co/PortalWeb/Juridica/CircularesExterna/x.pdf",
                         "NumeroOWSTEXT": "2026151000000002-5",
                         "FechadePublicacionOWSDATE": "2026-01-10T05:00:00Z",
                         "RefinableString00": "2026"},
                    ],
                }
            ]
        },
    ]
    responses.add(
        responses.POST,
        "https://www.supersalud.gov.co/es-co/_vti_bin/client.svc/ProcessQuery",
        body=_bom(payload),
        content_type="application/json",
    )
    session = __import__("requests").Session()
    rows = _process_query(session, "0xDIGEST", "CircularesExterna", 2026, 0)
    assert len(rows) == 1
    assert rows[0]["NumeroOWSTEXT"] == "2026151000000002-5"
    assert responses.calls[0].request.headers["X-RequestDigest"] == "0xDIGEST"
    assert responses.calls[0].request.headers["Content-Type"] == "text/xml"


@responses.activate
def test_process_query_raises_on_error_info():
    payload = [
        {"SchemaVersion": "15.0.0.0",
         "ErrorInfo": {"ErrorMessage": "La validación de seguridad de esta página no es válida"}},
    ]
    responses.add(
        responses.POST,
        "https://www.supersalud.gov.co/es-co/_vti_bin/client.svc/ProcessQuery",
        body=_bom(payload),
        content_type="application/json",
    )
    session = __import__("requests").Session()
    try:
        _process_query(session, "0xDIGEST", "Resoluciones", 2020, 0)
    except RuntimeError as e:
        assert "validación de seguridad" in str(e)
    else:
        raise AssertionError("esperaba RuntimeError")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/families/test_supersalud.py -q -k "build_body or form_digest or process_query"`
Expected: FAIL — `ImportError` de los tres nombres.

- [ ] **Step 3: Implement the transport**

Añadir a `core/scrapers/families/supersalud.py`. Primero, junto a las otras constantes:

```python
import json

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Plantilla CSOM ProcessQuery para una KeywordQuery + SearchExecutor.
# Marcadores: __CARPETA__ (carpeta en docs.supersalud), __HEXYEAR__ (año en
# hex UTF-8), __RL__ (RowLimit), __SR__ (StartRow). Los delimitadores ǂ
# alrededor del año son FQL de SharePoint. Estructura verificada contra el
# tráfico real del Content Search Web Part del portal.
_CSOM_BODY = (
    '<Request xmlns="http://schemas.microsoft.com/sharepoint/clientquery/2009" '
    'SchemaVersion="15.0.0.0" LibraryVersion="16.0.0.0" ApplicationName="Javascript Library">'
    "<Actions>"
    '<ObjectPath Id="2" ObjectPathId="1" />'
    '<SetProperty Id="3" ObjectPathId="1" Name="QueryText"><Parameter Type="String">*</Parameter></SetProperty>'
    '<SetProperty Id="4" ObjectPathId="1" Name="QueryTemplate"><Parameter Type="String">'
    "path:&quot;https://docs.supersalud.gov.co/PortalWeb/Juridica/__CARPETA__&quot; "
    "(IsDocument:&quot;True&quot; OR contentclass:&quot;STS_ListItem&quot;)"
    "</Parameter></SetProperty>"
    '<SetProperty Id="5" ObjectPathId="1" Name="RowLimit"><Parameter Type="Number">__RL__</Parameter></SetProperty>'
    '<SetProperty Id="6" ObjectPathId="1" Name="StartRow"><Parameter Type="Number">__SR__</Parameter></SetProperty>'
    '<SetProperty Id="7" ObjectPathId="1" Name="ClientType"><Parameter Type="String">ContentSearchRegular</Parameter></SetProperty>'
    '<SetProperty Id="8" ObjectPathId="1" Name="TrimDuplicates"><Parameter Type="Boolean">false</Parameter></SetProperty>'
    '<SetProperty Id="9" ObjectPathId="1" Name="Culture"><Parameter Type="Number">3082</Parameter></SetProperty>'
    '<ObjectPath Id="11" ObjectPathId="10" />'
    '<Method Name="Add" Id="12" ObjectPathId="10"><Parameters><Parameter Type="String">Title</Parameter></Parameters></Method>'
    '<Method Name="Add" Id="13" ObjectPathId="10"><Parameters><Parameter Type="String">Path</Parameter></Parameters></Method>'
    '<Method Name="Add" Id="14" ObjectPathId="10"><Parameters><Parameter Type="String">NumeroOWSTEXT</Parameter></Parameters></Method>'
    '<Method Name="Add" Id="15" ObjectPathId="10"><Parameters><Parameter Type="String">DescripcionOWSMTXT</Parameter></Parameters></Method>'
    '<Method Name="Add" Id="16" ObjectPathId="10"><Parameters><Parameter Type="String">FechadePublicacionOWSDATE</Parameter></Parameters></Method>'
    '<Method Name="Add" Id="17" ObjectPathId="10"><Parameters><Parameter Type="String">RefinableString00</Parameter></Parameters></Method>'
    '<Method Name="Add" Id="18" ObjectPathId="10"><Parameters><Parameter Type="String">FileExtension</Parameter></Parameters></Method>'
    '<ObjectPath Id="31" ObjectPathId="30" />'
    '<Method Name="Add" Id="32" ObjectPathId="30"><Parameters>'
    '<Parameter Type="String">RefinableString00:&quot;ǂǂ__HEXYEAR__&quot;</Parameter>'
    "</Parameters></Method>"
    '<ObjectPath Id="20" ObjectPathId="19" />'
    '<Method Name="Add" Id="33" ObjectPathId="19"><Parameters>'
    '<Parameter Type="String">FechadePublicacionOWSDATE</Parameter><Parameter Type="Number">1</Parameter>'
    "</Parameters></Method>"
    '<ObjectPath Id="22" ObjectPathId="21" />'
    '<Method Name="ExecuteQuery" Id="23" ObjectPathId="21"><Parameters><Parameter ObjectPathId="1" /></Parameters></Method>'
    "</Actions>"
    "<ObjectPaths>"
    '<Constructor Id="1" TypeId="{80173281-fffd-47b6-9a49-312e06ff8428}" />'
    '<Property Id="10" ParentId="1" Name="SelectProperties" />'
    '<Property Id="30" ParentId="1" Name="RefinementFilters" />'
    '<Property Id="19" ParentId="1" Name="SortList" />'
    '<Constructor Id="21" TypeId="{8d2ac302-db2f-46fe-9015-872b35f15098}" />'
    "</ObjectPaths></Request>"
)


def _build_body(carpeta: str, anio: int, start_row: int, row_limit: int = _PAGE) -> str:
    hexyear = str(anio).encode("utf-8").hex()
    return (
        _CSOM_BODY.replace("__CARPETA__", carpeta)
        .replace("__HEXYEAR__", hexyear)
        .replace("__RL__", str(row_limit))
        .replace("__SR__", str(start_row))
    )


def _decode(resp) -> object:
    return json.loads(resp.content.decode("utf-8-sig"))


def _form_digest(session: requests.Session) -> str:
    resp = session.post(_CONTEXTINFO, headers={"Accept": "application/json;odata=nometadata"}, timeout=30)
    resp.raise_for_status()
    return _decode(resp)["FormDigestValue"]


def _process_query(
    session: requests.Session, digest: str, carpeta: str, anio: int, start_row: int, row_limit: int = _PAGE
) -> List[dict]:
    resp = session.post(
        _PROCESS_QUERY,
        data=_build_body(carpeta, anio, start_row, row_limit).encode("utf-8"),
        headers={"Content-Type": "text/xml", "X-RequestDigest": digest},
        timeout=90,
    )
    resp.raise_for_status()
    payload = _decode(resp)
    for item in payload:
        if isinstance(item, dict) and item.get("ErrorInfo"):
            raise RuntimeError(item["ErrorInfo"].get("ErrorMessage") or "ProcessQuery devolvió ErrorInfo")
    for item in payload:
        if isinstance(item, dict) and item.get("ResultTables"):
            for tabla in item["ResultTables"]:
                if tabla.get("TableType") == "RelevantResults":
                    return tabla.get("ResultRows", [])
    return []
```

> Nota: mover el `import json` al bloque de imports de arriba del archivo (no dejarlo a media altura). Se muestra aquí junto al código nuevo solo para ubicarlo.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/pytest tests/families/test_supersalud.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/supersalud.py tests/families/test_supersalud.py
git commit -m "feat(supersalud): transporte CSOM ProcessQuery + form digest"
```

---

## Task 4: `ScrapSupersalud.scrap` + registro + smoke test en vivo

**Files:**
- Modify: `core/scrapers/families/supersalud.py`
- Modify: `core/scrapers/families/__init__.py`
- Test: `tests/families/test_supersalud.py`

**Interfaces:**
- Consumes: `_form_digest`, `_process_query` (Task 3), `_fila_a_doc` (Task 2), `_CATEGORIAS`, `_ANIO_MINIMO`, `_PAGE` (Task 1).
- Produces: `ScrapSupersalud` registrada como `@register_family("supersalud")`, con
  `scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]`.

**Comportamiento de `scrap`:**
1. `session = requests.Session()` con `User-Agent: _UA`.
2. `digest = _form_digest(session)` una vez.
3. `anio_ini = max(_ANIO_MINIMO, int(fini[:4]))`, `anio_fin = int(ffin[:4])`.
4. Por cada `(carpeta, tipo, letra)` de `_CATEGORIAS`, y por cada `anio` en `range(anio_ini, anio_fin + 1)`:
   - Paginar: `start = 0`; `rows = _process_query(session, digest, carpeta, anio, start)`; mapear cada fila con `_fila_a_doc`; si `len(rows) < _PAGE` → fin del año; si no `start += _PAGE` y repetir.
   - Si `_process_query` lanza `RuntimeError` cuyo mensaje sugiere digest vencido (`"validación de seguridad"` / `"security validation"`), pedir `digest = _form_digest(session)` de nuevo y reintentar **una** vez esa misma página; si vuelve a fallar, registrar vía `on_progress` (mensaje con `"Error"`) y seguir con el siguiente año.
   - Cualquier otra excepción de un año: registrar vía `on_progress` (con `"Error"`) y seguir.
   - Respetar `stop_event`: si `stop_event is not None and stop_event.is_set()`, `return docs` inmediatamente (entre páginas y entre años).
   - Respetar `limit`: si `len(docs) >= limit`, `return docs[:limit]`.
5. `return docs[:limit]`.

- [ ] **Step 1: Write the failing tests**

Añadir a `tests/families/test_supersalud.py`:

```python
import threading

from core.scrapers.registry import FAMILY_REGISTRY
from core.scrapers.families.supersalud import ScrapSupersalud

_CONTEXTINFO_URL = "https://www.supersalud.gov.co/es-co/_api/contextinfo"
_PQ_URL = "https://www.supersalud.gov.co/es-co/_vti_bin/client.svc/ProcessQuery"


def _rows_payload(rows):
    return [
        {"SchemaVersion": "15.0.0.0", "ErrorInfo": None},
        {"ResultTables": [{"TableType": "RelevantResults", "Properties": {}, "ResultRows": rows}]},
    ]


def _row(title, numero, fecha, path, anio):
    return {
        "Title": title, "NumeroOWSTEXT": numero, "DescripcionOWSMTXT": "desc",
        "FechadePublicacionOWSDATE": fecha, "Path": path, "RefinableString00": anio, "FileExtension": "pdf",
    }


def test_supersalud_is_registered():
    import core.scrapers.families  # noqa: F401
    assert FAMILY_REGISTRY["supersalud"].__name__ == "ScrapSupersalud"


def test_filters_by_publication_date_is_enabled():
    assert ScrapSupersalud.filters_by_publication_date is True


@responses.activate
def test_scrap_collects_both_categories_one_year():
    responses.add(responses.POST, _CONTEXTINFO_URL, body=_bom({"FormDigestValue": "0xD"}))

    def cb(request):
        body = request.body.decode("utf-8") if isinstance(request.body, bytes) else request.body
        if "Juridica/Resoluciones" in body:
            rows = [_row("Resolución número 2026910010008999-6 de 2026", "2026910010008999-6",
                         "2026-03-04T05:00:00Z", "https://docs.supersalud.gov.co/PortalWeb/Juridica/Resoluciones/a.pdf", "2026")]
        else:
            rows = [_row("Circular externa número 2026151000000002-5 de 2026", "2026151000000002-5",
                         "2026-02-10T05:00:00Z", "https://docs.supersalud.gov.co/PortalWeb/Juridica/CircularesExterna/b.pdf", "2026")]
        return (200, {}, _bom(_rows_payload(rows)))

    responses.add_callback(responses.POST, _PQ_URL, callback=cb, content_type="application/json")

    docs = ScrapSupersalud().scrap(fini="2026-01-01", ffin="2026-12-31")
    assert {d.title for d in docs} == {"R_SNS_8999_2026", "C_SNS_0002_2026"}


@responses.activate
def test_scrap_floors_start_year_at_2015():
    responses.add(responses.POST, _CONTEXTINFO_URL, body=_bom({"FormDigestValue": "0xD"}))
    seen_years = []

    def cb(request):
        body = request.body.decode("utf-8") if isinstance(request.body, bytes) else request.body
        # el año va como hex UTF-8 dentro del refiner; recuperarlo
        import re as _re
        m = _re.search(r"ǂǂ([0-9a-f]+)&quot;", body)
        year = bytes.fromhex(m.group(1)).decode("utf-8")
        seen_years.append(year)
        return (200, {}, _bom(_rows_payload([])))

    responses.add_callback(responses.POST, _PQ_URL, callback=cb, content_type="application/json")

    ScrapSupersalud().scrap(fini="2010-01-01", ffin="2015-12-31")
    assert "2010" not in seen_years
    assert "2015" in seen_years


@responses.activate
def test_scrap_paginates_when_page_is_full():
    responses.add(responses.POST, _CONTEXTINFO_URL, body=_bom({"FormDigestValue": "0xD"}))
    calls = {"n": 0}

    def cb(request):
        body = request.body.decode("utf-8") if isinstance(request.body, bytes) else request.body
        if "Juridica/CircularesExterna" not in body:
            return (200, {}, _bom(_rows_payload([])))
        calls["n"] += 1
        if calls["n"] == 1:
            rows = [_row(f"Circular Externa {i:03d} de 2016", f"{i:03d}", "2016-06-01T05:00:00Z",
                         f"https://docs.supersalud.gov.co/PortalWeb/Juridica/CircularesExterna/{i}.pdf", "2016")
                    for i in range(1, 501)]
        else:
            rows = [_row("Circular Externa 900 de 2016", "900", "2016-07-01T05:00:00Z",
                         "https://docs.supersalud.gov.co/PortalWeb/Juridica/CircularesExterna/900.pdf", "2016")]
        return (200, {}, _bom(_rows_payload(rows)))

    responses.add_callback(responses.POST, _PQ_URL, callback=cb, content_type="application/json")

    docs = ScrapSupersalud().scrap(fini="2016-01-01", ffin="2016-12-31")
    assert calls["n"] == 2
    assert any(d.title == "C_SNS_0900_2016" for d in docs)


@responses.activate
def test_scrap_continues_past_a_failing_year():
    responses.add(responses.POST, _CONTEXTINFO_URL, body=_bom({"FormDigestValue": "0xD"}))

    def cb(request):
        body = request.body.decode("utf-8") if isinstance(request.body, bytes) else request.body
        import re as _re
        m = _re.search(r"ǂǂ([0-9a-f]+)&quot;", body)
        year = bytes.fromhex(m.group(1)).decode("utf-8")
        if year == "2015":
            return (200, {}, _bom([{"ErrorInfo": {"ErrorMessage": "boom interno"}}]))
        rows = [_row("Circular externa número 2016151000000003-5 de 2016", "2016151000000003-5",
                     "2016-05-01T05:00:00Z", "https://docs.supersalud.gov.co/PortalWeb/Juridica/CircularesExterna/x.pdf", "2016")]
        return (200, {}, _bom(_rows_payload(rows)))

    responses.add_callback(responses.POST, _PQ_URL, callback=cb, content_type="application/json")

    progreso = []
    docs = ScrapSupersalud().scrap(fini="2015-01-01", ffin="2016-12-31", on_progress=progreso.append)
    assert any(d.title == "C_SNS_0003_2016" for d in docs)
    assert any("Error" in m for m in progreso)


@responses.activate
def test_scrap_stops_on_stop_event():
    responses.add(responses.POST, _CONTEXTINFO_URL, body=_bom({"FormDigestValue": "0xD"}))
    ev = threading.Event()

    def cb(request):
        ev.set()  # se dispara en la primera consulta
        rows = [_row("Circular Externa 001 de 2015", "001", "2015-01-05T05:00:00Z",
                     "https://docs.supersalud.gov.co/PortalWeb/Juridica/CircularesExterna/1.pdf", "2015")]
        return (200, {}, _bom(_rows_payload(rows)))

    responses.add_callback(responses.POST, _PQ_URL, callback=cb, content_type="application/json")

    docs = ScrapSupersalud().scrap(fini="2015-01-01", ffin="2018-12-31", stop_event=ev)
    # se permite 0..N docs de la primera página, pero no debe recorrer los 4 años x 2 categorías
    assert len(responses.calls) <= 3  # 1 contextinfo + a lo sumo 2 process_query
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/pytest tests/families/test_supersalud.py -q -k "scrap or is_registered or filters_by"`
Expected: FAIL — `ImportError: cannot import name 'ScrapSupersalud'`.

- [ ] **Step 3: Implement `ScrapSupersalud` and register it**

Añadir al final de `core/scrapers/families/supersalud.py`:

```python
_DIGEST_VENCIDO = ("validación de seguridad", "validacion de seguridad", "security validation")


@register_family("supersalud")
class ScrapSupersalud(BaseScrapper):
    filters_by_publication_date = True

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": _UA})
        digest = _form_digest(session)

        anio_ini = max(_ANIO_MINIMO, int(fini[:4]))
        anio_fin = int(ffin[:4])
        docs: List[RawDocModel] = []

        for carpeta, tipo, letra in _CATEGORIAS:
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            if on_progress:
                on_progress(f"[{_SOURCE}] Procesando {tipo}...")

            for anio in range(anio_ini, anio_fin + 1):
                if stop_event is not None and stop_event.is_set():
                    return docs[:limit]
                start = 0
                while True:
                    if stop_event is not None and stop_event.is_set():
                        return docs[:limit]
                    try:
                        rows = _process_query(session, digest, carpeta, anio, start)
                    except RuntimeError as e:
                        if any(t in str(e).lower() for t in _DIGEST_VENCIDO):
                            digest = _form_digest(session)
                            try:
                                rows = _process_query(session, digest, carpeta, anio, start)
                            except Exception as e2:
                                if on_progress:
                                    on_progress(f"[{_SOURCE}] Error consultando {tipo} {anio}: {e2}")
                                break
                        else:
                            if on_progress:
                                on_progress(f"[{_SOURCE}] Error consultando {tipo} {anio}: {e}")
                            break
                    except Exception as e:
                        if on_progress:
                            on_progress(f"[{_SOURCE}] Error consultando {tipo} {anio}: {e}")
                        break

                    for fila in rows:
                        doc = _fila_a_doc(fila, tipo, letra, fini, ffin, on_progress)
                        if doc is not None:
                            docs.append(doc)
                            if len(docs) >= limit:
                                return docs[:limit]

                    if len(rows) < _PAGE:
                        break
                    start += _PAGE

        return docs[:limit]
```

Modificar `core/scrapers/families/__init__.py` — añadir `supersalud` al final de la lista de imports:

```python
from . import constitucional, samai, corte_suprema, jep, cndj, adr, adres, ane, anh, rama_judicial, mincit, madr, minambiente, minvivienda, mineducacion, mininterior, mindeporte, minjusticia, minenergia, mintrabajo, superfinanciera, supersalud  # noqa: F401
```

- [ ] **Step 4: Run the family test file**

Run: `.venv/Scripts/pytest tests/families/test_supersalud.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Smoke test en vivo (manual, obligatorio antes de commitear)**

El cuerpo CSOM no se puede validar de verdad con mocks. Correr contra el sitio real:

```bash
.venv/Scripts/python -c "
from core.scrapers.families.supersalud import ScrapSupersalud
docs = ScrapSupersalud().scrap(fini='2024-01-01', ffin='2024-12-31', on_progress=print)
print('TOTAL', len(docs))
for d in docs[:8]:
    print(d.f_public, '|', d.tipo, '|', d.title, '|', d.title_unverified, '|', d.link['url'][:90])
assert docs, 'sin documentos: revisar el cuerpo CSOM o el digest'
assert all(d.f_public.startswith('2024') for d in docs), 'llegaron años fuera del rango: revisar el refiner'
assert any(d.tipo == 'Circular Externa' for d in docs) and any(d.tipo == 'Resolución' for d in docs)
print('OK')
"
```

Verificar a ojo: se imprimen filas de ambos tipos, títulos `C_SNS_####_2024` / `R_SNS_####_2024` mayormente verificados, alguna `title_unverified` aceptable, y URLs que apuntan a `docs.supersalud.gov.co`. Si sale `sin documentos` o años equivocados, ajustar `_CSOM_BODY` (IDs de `ObjectPath`/`Property`, delimitador `ǂ`, TypeIds) y repetir — **no** commitear hasta que pase.

- [ ] **Step 6: Commit**

```bash
git add core/scrapers/families/supersalud.py core/scrapers/families/__init__.py tests/families/test_supersalud.py
git commit -m "feat(supersalud): orquestación scrap() con paginación, piso 2015 y resiliencia por año"
```

---

## Task 5: Seed de la fuente + nota de documentación

**Files:**
- Modify: `core/seed.py:4-78` (dict `_FAMILIES`) y la zona de llamadas `create_source_if_missing`
- Modify: `docs/guia-despliegue-sistemas.md`
- Test: `tests/families/test_supersalud.py`

**Interfaces:**
- Consumes: `FAMILY_REGISTRY` ya poblado por el import de Task 4.
- Produces: entrada `"supersalud"` en `_FAMILIES` y una fuente `"Superintendencia Nacional de Salud"` sembrada con `family_key="supersalud"`, `family_params={}`.

- [ ] **Step 1: Write the failing test**

Añadir a `tests/families/test_supersalud.py`:

```python
def test_seed_families_dict_has_supersalud_entry():
    from core.seed import _FAMILIES
    assert "supersalud" in _FAMILIES
    display_name, description = _FAMILIES["supersalud"]
    assert display_name == "Superintendencia Nacional de Salud"
    assert "esolucion" in description or "esoluciones" in description
    assert "irculares" in description
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/pytest tests/families/test_supersalud.py -q -k seed_families_dict`
Expected: FAIL — `KeyError: 'supersalud'` en `_FAMILIES`.

- [ ] **Step 3: Add the seed entry**

En `core/seed.py`, dentro del dict `_FAMILIES`, añadir (junto a la entrada `"superfinanciera"`):

```python
    "supersalud": (
        "Superintendencia Nacional de Salud",
        "Normativa (resoluciones y circulares externas) publicada por la "
        "Superintendencia Nacional de Salud",
    ),
```

Y en la zona de llamadas `repository.create_source_if_missing(...)` (después de la de `superfinanciera` si existe, o junto a las de agencias), añadir:

```python
    repository.create_source_if_missing(
        db, family_key="supersalud", name="Superintendencia Nacional de Salud", family_params={}
    )
```

- [ ] **Step 4: Run the family test file**

Run: `.venv/Scripts/pytest tests/families/test_supersalud.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Add the documentation note**

En `docs/guia-despliegue-sistemas.md`, donde se listen las fuentes / familias, añadir un párrafo:

```markdown
### Superintendencia Nacional de Salud (`supersalud`)

Una sola fuente que raspa dos secciones del portal SharePoint de
Supersalud: **Resoluciones** y **Circulares Externas** (las Actas de
Conciliación quedan fuera). Cobertura desde 2015.

Particularidad del transporte: el portal es SharePoint y su API REST de
búsqueda (`/_api/search/query`) está bloqueada por un WAF ("Acceso
Bloqueado"). El scraper usa en su lugar el endpoint CSOM
`/_vti_bin/client.svc/ProcessQuery` con un *form digest* que pide a
`/_api/contextinfo`. Los archivos (PDF y algún ZIP) se descargan directo
de `docs.supersalud.gov.co`.

Títulos: `{C|R}_SNS_{número}_{año}` (número = consecutivo; en el radicado
largo nuevo son los últimos 6 dígitos del bloque central). Cuando el
número no se puede determinar, el documento entra con el título crudo y
marca de "no verificado". Los anexos entran como documentos propios con
sufijo `_A01`.
```

- [ ] **Step 6: Commit**

```bash
git add core/seed.py docs/guia-despliegue-sistemas.md tests/families/test_supersalud.py
git commit -m "feat(supersalud): seed de la fuente + nota de despliegue"
```

---

## Task 6: Verificación completa y PR

**Files:** ninguno nuevo — corridas de verificación y apertura del PR.

- [ ] **Step 1: Suite backend completa**

Run: `.venv/Scripts/pytest -q`
Expected: PASS salvo el fallo pre-existente conocido
`tests/families/test_migrations.py::test_alembic_upgrade_head_creates_all_tables`
(`FileNotFoundError [WinError 2]`, no relacionado). Ningún otro fallo nuevo.

- [ ] **Step 2: Lint / import del registro**

Run: `.venv/Scripts/python -c "import core.scrapers.families; from core.scrapers.registry import FAMILY_REGISTRY; print(sorted(FAMILY_REGISTRY))"`
Expected: la lista incluye `'supersalud'`.

- [ ] **Step 3: Seed idempotente contra la BD local**

Run: `.venv/Scripts/python -m core.seed`
Expected: corre sin error; una segunda corrida tampoco falla (ON CONFLICT DO NOTHING). Verificar que aparece la fuente:

Run: `.venv/Scripts/python -c "from core.db.session import SessionLocal; from core.db import repository; db=SessionLocal(); print([s.name for s in repository.list_sources(db) if 'Salud' in s.name])"`
Expected: `['Superintendencia Nacional de Salud']` (el nombre exacto puede variar según el helper de listado; basta con que la fuente exista).

- [ ] **Step 4: Smoke test en vivo end-to-end (opcional pero recomendado)**

Repetir el smoke test del Task 4 Step 5 con un rango chico (p. ej. `2026-01-01`..`2026-12-31`) y, si el entorno de desarrollo está levantado, disparar una corrida real desde la UI (`run-iurisync`) contra la fuente nueva para confirmar descarga + preview de al menos un documento.

- [ ] **Step 5: Push y PR**

```bash
git push -u origin feature/fuente-supersalud
gh pr create --base master --title "feat(supersalud): nueva fuente Superintendencia Nacional de Salud" --body "$(cat <<'EOF'
Nueva familia técnica `supersalud`: raspa Resoluciones y Circulares Externas
del portal SharePoint de la Superintendencia Nacional de Salud.

## Qué trae
- `core/scrapers/families/supersalud.py` — familia nueva. Transporte vía CSOM
  `client.svc/ProcessQuery` + form digest (el REST de búsqueda de SharePoint
  está bloqueado por un WAF). Descarga directa de PDF/ZIP desde
  `docs.supersalud.gov.co`.
- Títulos `{C|R}_SNS_{nº:04d}_{año}` al estilo `superfinanciera`; `title_unverified`
  cuando el número no se puede parsear (18 años de numeración inconsistente).
- Anexos como documentos propios con sufijo `_A01`, sin agrupación madre↔anexo (v1).
- Cobertura desde 2015. Sin Actas de Conciliación.
- Seed: una sola fuente "Superintendencia Nacional de Salud".
- `tests/families/test_supersalud.py` con fixtures JSON mockeadas.

## Spec y plan
- `docs/superpowers/specs/2026-09-07-fuente-supersalud-design.md`
- `docs/superpowers/plans/2026-09-07-fuente-supersalud.md`

## Verificación
- `pytest -q` verde (salvo el fallo pre-existente de `test_migrations`).
- Smoke test en vivo contra supersalud.gov.co: devuelve ambos tipos, años dentro
  de rango, títulos canónicos.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**1. Spec coverage:**

| Sección del spec | Task |
|---|---|
| Transporte: contextinfo + ProcessQuery + digest, decodificación BOM | Task 3 |
| QueryTemplate por carpeta, refiner de año, paginación StartRow/RowLimit 500 | Task 3 (`_build_body`), Task 4 (bucle) |
| Piso de cobertura 2015 | Task 4 (`anio_ini = max(_ANIO_MINIMO, ...)`) + test |
| Solo Resoluciones + Circulares Externas, sin Actas | Task 1 (`_CATEGORIAS`) |
| Fila → RawDocModel: fecha doblada, filtro por rango, `Path` verbatim, descarte sin fecha/sin path | Task 2 (`_fila_a_doc`) + tests |
| Número forma radicado (últimos 6 del bloque de 12) y forma clásica | Task 1 (`_parse_numero`) + tests |
| Título `{letra}_SNS_{nº:04d}_{año}`; `title_unverified` con título crudo | Task 1 (`_titulo`) + tests |
| Anexo → `_A01` fijo; anexo sin número → unverified sin sufijo | Task 1 (`_titulo`) + Task 2 tests |
| `filters_by_publication_date = True`, otros flags por defecto | Task 4 (atributo de clase) + test |
| Resiliencia: un año que falla no aborta el resto; reintento de digest | Task 4 + tests |
| `stop_event` y `limit` incrementales | Task 4 + tests |
| Seed: una fuente, `family_params={}`, sin `auto_review_status` | Task 5 + test |
| Registro en `families/__init__.py` | Task 4 |
| `tests/families/test_supersalud.py` con fixtures JSON reales | Tasks 1–5 |
| Nota de documentación | Task 5 |
| Sin migración, sin frontend | (n/a — no hay task porque no hay cambio) |

Sin huecos.

**2. Placeholder scan:** No hay "TBD"/"TODO"/"manejar edge cases" sin código. El único paso manual (smoke test en vivo, Task 4 Step 5 / Task 6 Step 4) trae el comando exacto y los criterios de aceptación. La nota "mover el `import json` arriba" es una instrucción concreta, no un placeholder.

**3. Type consistency:**
- `_parse_numero(numero_raw, title) -> int | None` — misma firma en Task 1 (def + tests) y en Task 1 `_titulo` (la llama con `(numero_raw, title_raw)`).
- `_titulo(letra, numero_raw, title_raw, anio, es_anexo) -> (str, bool)` — misma firma en Task 1 y su uso en Task 2 `_fila_a_doc`.
- `_fila_a_doc(fila, tipo, letra, fini, ffin, on_progress) -> RawDocModel | None` — definida en Task 2, usada en Task 4 con esos mismos 6 argumentos posicionales.
- `_process_query(session, digest, carpeta, anio, start_row, row_limit=_PAGE) -> list[dict]` — definida en Task 3, usada en Task 4 como `_process_query(session, digest, carpeta, anio, start)`.
- `_form_digest(session) -> str` — definida en Task 3, usada en Task 4 dos veces.
- `_build_body(carpeta, anio, start_row, row_limit=_PAGE) -> str` — definida en Task 3, usada por `_process_query` en Task 3.
- Constantes `_CATEGORIAS`, `_ANIO_MINIMO`, `_PAGE`, `_SOURCE`, `_UA`, `_CONTEXTINFO`, `_PROCESS_QUERY` — definidas en Task 1/Task 3, usadas en Task 4.

Consistente.
