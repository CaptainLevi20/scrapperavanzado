# Fuente Superintendencia Financiera de Colombia — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar la Superintendencia Financiera de Colombia como una sola
fuente, con dos scrapers internos (normativa HTML por año + Doctrina y
Conceptos del catálogo ABCD), y hacer que los anexos de las circulares se
muestren agrupados ("N anexos"), a la manera de las "actuaciones".

**Architecture:** Familia técnica nueva `superfinanciera` como paquete
`core/scrapers/families/superfinanciera/` con un `__init__.py` que
registra `ScrapSuperfinanciera` y orquesta dos submódulos independientes
(`normativa.py`, `conceptos.py`). Los anexos entran como documentos
hermanos con título `{padre}_A01`; una lógica de colapso nueva en
`repository.list_documents` (paralela a la de "case families") los oculta
del listado y expone `anexo_count`; un endpoint nuevo
`GET /documents/{id}/anexos` los lista; `_expandir_a_grupos` los arrastra
a la descarga masiva del documento madre; el frontend muestra un chip
"N anexos".

**Tech Stack:** Python 3.14, `requests`, `beautifulsoup4` (ya es
dependencia, ver `core/downloader.py`), SQLAlchemy, FastAPI, pytest +
`responses`; frontend React + Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-03-fuente-superfinanciera-design.md`

## Global Constraints

- Familia técnica: `superfinanciera`. Una sola fuente en el seed:
  `name = "Superintendencia Financiera de Colombia"`, `family_params = {}`
  (sin `auto_review_status` → todo entra `review_status = "pending"`).
- Nomenclatura (verbatim del spec):
  - Circular Externa: `C_SF_{numero:04d}_{año}` (ej. `C_SF_0020_2026`).
  - Carta Circular: `CCIR_SF_{numero:04d}_{año}` (ej. `CCIR_SF_0020_2026`).
  - Resolución: `R_SF_{numero:04d}_{año}` (ej. `R_SF_0020_2026`).
  - Concepto: `CTO_SF_{numero:07d}_{año}` con `año = radicado[:4]` y
    `numero = radicado[4:]` (ej. `2026019914` → `CTO_SF_0019914_2026`).
  - Anexo: `{titulo_madre}_A{n:02d}` (ej. `C_SF_0020_2026_A01`).
- Concepto — choque de radicado: `consecutivo` normalizado a entero; si
  `== 1` no lleva sufijo, si `!= 1` se agrega `_{consecutivo:02d}`
  (ej. `CTO_SF_0045919_1998_04`).
- El scraper de conceptos recorre **todas** las páginas del catálogo en
  cada corrida (no hay filtro de fecha ni orden cronológico) y filtra por
  rango de fechas del lado del cliente.
- Sin migración de esquema. `anexo_count` se calcula en la consulta.
- Fixtures de prueba: HTML real recortado, construido inline en el
  archivo de test con helpers (mismo estilo que
  `tests/families/test_minjusticia.py`), mockeando las URLs con
  `responses.RequestsMock()`.
- Mensajes de error recuperables del scraper: se emiten por
  `on_progress(f"[{source}] Error ...")` (el worker convierte los que
  contienen "Error" en `RunError` visibles).

---

## File Structure

**Crear:**
- `core/scrapers/families/superfinanciera/__init__.py` — clase
  registrada `ScrapSuperfinanciera` + orquestación de los dos submódulos.
- `core/scrapers/families/superfinanciera/normativa.py` — Circulares
  Externas, Cartas Circulares, Resoluciones + anexos.
- `core/scrapers/families/superfinanciera/conceptos.py` — Doctrina y
  Conceptos (catálogo ABCD).
- `tests/families/test_superfinanciera_normativa.py`
- `tests/families/test_superfinanciera_conceptos.py`
- `tests/families/test_superfinanciera_registry.py`
- (tests nuevos van en archivos ya existentes: `tests/test_repository.py`,
  `tests/test_api_documents.py`, `tests/test_naming.py` — no se crean
  archivos de test de backend nuevos salvo los de familias)
- `frontend/src/components/AnexosDialog.tsx`
- `frontend/src/components/AnexosDialog.test.tsx`

**Modificar:**
- `core/scrapers/families/__init__.py` — agregar `superfinanciera` al
  import.
- `core/seed.py` — entrada en `_FAMILIES` + `create_source_if_missing`.
- `core/naming.py` — helpers `es_anexo_title`, `titulo_padre_de_anexo`.
- `core/db/repository.py` — colapso de anexos en `list_documents`;
  `anexo_counts_by_document`; `list_anexos_of_document`;
  `_expandir_a_grupos` (arrastrar anexos del documento madre).
- `api/routers/documents.py` — poblar `anexo_count`; endpoint
  `GET /documents/{document_id}/anexos`.
- `api/schemas.py` — campo `anexo_count` en `DocumentOut`.
- `frontend/src/api/types.ts` — `anexo_count`.
- `frontend/src/pages/DocumentsPage.tsx` — `AnexoBadge` + apertura del
  `AnexosDialog`.

---

## PARTE A — Scraper `normativa`

### Task 1: Scaffold de la familia `superfinanciera`

**Files:**
- Create: `core/scrapers/families/superfinanciera/__init__.py`
- Create: `core/scrapers/families/superfinanciera/normativa.py`
- Create: `core/scrapers/families/superfinanciera/conceptos.py`
- Modify: `core/scrapers/families/__init__.py`
- Modify: `core/seed.py`
- Modify: `tests/test_seed.py` (conteos + set de `family_key`)
- Test: `tests/families/test_superfinanciera_registry.py`

**Interfaces:**
- Produces:
  - `ScrapSuperfinanciera(BaseScrapper)` con
    `source = "Superintendencia Financiera de Colombia"` y
    `scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> list[RawDocModel]`.
  - `core/scrapers/families/normativa.py::scrap_normativa(fini, ffin, source, limit, stop_event, on_progress) -> list[RawDocModel]` (stub por ahora, devuelve `[]`).
  - `core/scrapers/families/conceptos.py::scrap_conceptos(fini, ffin, source, limit, stop_event, on_progress) -> list[RawDocModel]` (stub por ahora, devuelve `[]`).

- [ ] **Step 1: Escribir el test de registro y seed**

```python
# tests/families/test_superfinanciera_registry.py
from core.scrapers.registry import FAMILY_REGISTRY


def test_superfinanciera_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["superfinanciera"].__name__ == "ScrapSuperfinanciera"


def test_superfinanciera_scraper_source_name():
    import core.scrapers.families  # noqa: F401

    scraper = FAMILY_REGISTRY["superfinanciera"]()
    assert scraper.source == "Superintendencia Financiera de Colombia"


def test_superfinanciera_scrap_returns_empty_list_with_no_data(monkeypatch):
    import core.scrapers.families  # noqa: F401
    from core.scrapers.families.superfinanciera import normativa, conceptos

    monkeypatch.setattr(normativa, "scrap_normativa", lambda *a, **k: [])
    monkeypatch.setattr(conceptos, "scrap_conceptos", lambda *a, **k: [])
    scraper = FAMILY_REGISTRY["superfinanciera"]()
    assert scraper.scrap(fini="2026-01-01", ffin="2026-01-31", on_progress=lambda m: None) == []
```

- [ ] **Step 2: Correr el test y verlo fallar**

Run: `pytest tests/families/test_superfinanciera_registry.py -v`
Expected: FAIL con `KeyError: 'superfinanciera'`.

- [ ] **Step 3: Crear los submódulos stub**

```python
# core/scrapers/families/superfinanciera/normativa.py
from typing import List

from core.models import RawDocModel


def scrap_normativa(fini, ffin, source, limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
    return []
```

```python
# core/scrapers/families/superfinanciera/conceptos.py
from typing import List

from core.models import RawDocModel


def scrap_conceptos(fini, ffin, source, limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
    return []
```

- [ ] **Step 4: Crear el `__init__.py` con la clase registrada**

```python
# core/scrapers/families/superfinanciera/__init__.py
from typing import List

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.scrapers.families.superfinanciera import conceptos, normativa

_SOURCE = "Superintendencia Financiera de Colombia"


@register_family("superfinanciera")
class ScrapSuperfinanciera(BaseScrapper):
    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        docs: List[RawDocModel] = []
        docs.extend(
            normativa.scrap_normativa(
                fini, ffin, self.source, limit=limit, stop_event=stop_event, on_progress=on_progress
            )
        )
        if len(docs) >= limit:
            return docs[:limit]
        if stop_event is not None and stop_event.is_set():
            return docs[:limit]
        docs.extend(
            conceptos.scrap_conceptos(
                fini, ffin, self.source, limit=limit - len(docs), stop_event=stop_event, on_progress=on_progress
            )
        )
        return docs[:limit]
```

- [ ] **Step 5: Registrar el paquete e insertar en el seed**

En `core/scrapers/families/__init__.py`, agregar `superfinanciera` al
final del import:

```python
from . import constitucional, samai, corte_suprema, jep, cndj, adr, adres, ane, anh, rama_judicial, mincit, madr, minambiente, minvivienda, mineducacion, mininterior, mindeporte, minjusticia, minenergia, mintrabajo, superfinanciera  # noqa: F401
```

En `core/seed.py`, agregar al dict `_FAMILIES` (después de `mintrabajo`):

```python
    "superfinanciera": (
        "Superintendencia Financiera de Colombia",
        "Normativa (circulares externas, cartas circulares, resoluciones) y doctrina y conceptos "
        "publicados por la Superintendencia Financiera de Colombia",
    ),
```

Y en `seed_source_families_and_sources`, junto a los demás
`create_source_if_missing`:

```python
    repository.create_source_if_missing(
        db, family_key="superfinanciera", name="Superintendencia Financiera de Colombia", family_params={}
    )
```

- [ ] **Step 6: Ajustar `tests/test_seed.py`**

Hay 3 aserciones con conteos fijos que suben en 1:

- `assert len(families) == 20` → `== 21` (aparece 1 vez).
- `assert len(sources) == 1 + 28 + 17 + 33 + 6` → `== 1 + 28 + 18 + 33 + 6`
  (aparece 2 veces; la fuente nueva es "fuente única", igual que los
  ministerios, así que sube el término del `17` a `18`; actualizar también
  el comentario que enumera esas fuentes únicas para incluir
  `superfinanciera`).
- En el set literal de `family_key`, agregar `"superfinanciera",`.

- [ ] **Step 7: Correr los tests y verlos pasar**

Run: `pytest tests/families/test_superfinanciera_registry.py tests/test_seed.py tests/test_registry.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add core/scrapers/families/superfinanciera core/scrapers/families/__init__.py core/seed.py tests/test_seed.py tests/families/test_superfinanciera_registry.py
git commit -m "feat(superfinanciera): scaffold de la familia y seed de la fuente"
```

---

### Task 2: `normativa` — parsear la página índice

**Files:**
- Modify: `core/scrapers/families/superfinanciera/normativa.py`
- Test: `tests/families/test_superfinanciera_normativa.py`

**Interfaces:**
- Produces:
  - `_INDICE_URL: str` = `"https://www.superfinanciera.gov.co/publicaciones/20149/normativanormativa-generalcirculares-externas-cartas-circulares-y-resoluciones-desde-el-ano-20149/"`
  - `_TIPOS: dict[str, tuple[str, str]]` = `{"Circulares Externas": ("Circular Externa", "C"), "Cartas Circulares": ("Carta Circular", "CCIR"), "Resoluciones": ("Resolución", "R")}`
  - `_parse_indice(html: str, base_url: str) -> dict[str, dict[int, str]]` — devuelve `{encabezado_columna: {año: url_absoluta}}`.

- [ ] **Step 1: Escribir el test**

```python
# tests/families/test_superfinanciera_normativa.py
from core.scrapers.families.superfinanciera.normativa import _parse_indice

_BASE = "https://www.superfinanciera.gov.co"


def _indice_html():
    # Estructura real recortada: una tabla con una fila de encabezados y filas
    # de años; cada celda de año trae un <a> cuyo texto es el año.
    return """
    <table>
      <tr><th>Circulares Externas (1)</th><th>Cartas Circulares (2)</th><th>Resoluciones (3)</th></tr>
      <tr>
        <td><a href="/publicaciones/10115974/circulares-externas-2026/">2026</a></td>
        <td><a href="/10115975">2026</a></td>
        <td><a href="/publicaciones/10115976/resoluciones-2026/">2026</a></td>
      </tr>
      <tr>
        <td><a href="/publicaciones/10115459/circulares-externas-2025/">2025</a></td>
        <td><a href="/10115460">2025</a></td>
        <td><a href="/10115461">2025</a></td>
      </tr>
    </table>
    """


def test_parse_indice_agrupa_por_columna_y_anio():
    idx = _parse_indice(_indice_html(), _BASE)

    assert set(idx.keys()) == {"Circulares Externas", "Cartas Circulares", "Resoluciones"}
    assert idx["Circulares Externas"][2026] == f"{_BASE}/publicaciones/10115974/circulares-externas-2026/"
    assert idx["Circulares Externas"][2025] == f"{_BASE}/publicaciones/10115459/circulares-externas-2025/"
    assert idx["Cartas Circulares"][2026] == f"{_BASE}/10115975"
    assert idx["Resoluciones"][2025] == f"{_BASE}/10115461"
```

- [ ] **Step 2: Correr el test y verlo fallar**

Run: `pytest tests/families/test_superfinanciera_normativa.py::test_parse_indice_agrupa_por_columna_y_anio -v`
Expected: FAIL con `ImportError: cannot import name '_parse_indice'`.

- [ ] **Step 3: Implementar `_parse_indice`**

```python
# core/scrapers/families/superfinanciera/normativa.py
import re
from typing import Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.utils import storage_path

_BASE_URL = "https://www.superfinanciera.gov.co"
_INDICE_URL = (
    f"{_BASE_URL}/publicaciones/20149/normativanormativa-generalcirculares-externas-"
    "cartas-circulares-y-resoluciones-desde-el-ano-20149/"
)

# encabezado de columna (sin el " (1)"/" (2)"/" (3)") -> (tipo mostrado, sigla del título)
_TIPOS = {
    "Circulares Externas": ("Circular Externa", "C"),
    "Cartas Circulares": ("Carta Circular", "CCIR"),
    "Resoluciones": ("Resolución", "R"),
}

_ANIO_RE = re.compile(r"^\s*((?:19|20)\d{2})\s*$")
_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')


def _limpiar_encabezado(texto: str) -> str:
    # "Circulares Externas (1)" -> "Circulares Externas"
    return re.sub(r"\s*\(\d+\)\s*$", "", (texto or "").strip())


def _parse_indice(html: str, base_url: str) -> Dict[str, Dict[int, str]]:
    soup = BeautifulSoup(html, "html.parser")
    for tabla in soup.find_all("table"):
        encabezados = [_limpiar_encabezado(c.get_text()) for c in tabla.find_all(["th", "td"], limit=3)]
        col_por_indice = {i: h for i, h in enumerate(encabezados) if h in _TIPOS}
        if len(col_por_indice) < 3:
            continue
        resultado: Dict[str, Dict[int, str]] = {h: {} for h in col_por_indice.values()}
        for fila in tabla.find_all("tr"):
            celdas = fila.find_all("td")
            if not celdas:
                continue
            for i, celda in enumerate(celdas):
                encabezado = col_por_indice.get(i)
                if encabezado is None:
                    continue
                enlace = celda.find("a", href=True)
                if enlace is None:
                    continue
                m = _ANIO_RE.match(enlace.get_text())
                if not m:
                    continue
                resultado[encabezado][int(m.group(1))] = urljoin(base_url + "/", enlace["href"])
        return resultado
    return {}
```

- [ ] **Step 4: Correr el test y verlo pasar**

Run: `pytest tests/families/test_superfinanciera_normativa.py::test_parse_indice_agrupa_por_columna_y_anio -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/superfinanciera/normativa.py tests/families/test_superfinanciera_normativa.py
git commit -m "feat(superfinanciera): parsear la página índice de normativa"
```

---

### Task 3: `normativa` — parsear una página de año y su tabla

**Files:**
- Modify: `core/scrapers/families/superfinanciera/normativa.py`
- Test: `tests/families/test_superfinanciera_normativa.py`

**Interfaces:**
- Consumes: `_INVALID_PATH_CHARS` (Task 2).
- Produces:
  - `_FilaNormativa` = `namedtuple("_FilaNormativa", "numero_raw fecha_raw descripcion anexos_urls")`
    (`anexos_urls: list[str]`).
  - `_parse_pagina_anio(html: str, base_url: str) -> list[_FilaNormativa]`.

- [ ] **Step 1: Escribir el test**

```python
def _pagina_anio_html():
    # Real recortado: una sola <table> con encabezados Número|Fecha|Descripción|Boletín*
    return """
    <table>
      <tr><th>Número</th><th>Fecha</th><th>Descripción</th><th>Boletín*</th></tr>
      <tr>
        <td><a href="/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=descargar&idFile=111">008</a></td>
        <td>Septiembre 01</td>
        <td>Imparte instrucciones sobre prospectos. <a href="/loader.php?idFile=222">Anexo</a>.</td>
        <td>831</td>
      </tr>
      <tr>
        <td><a href="/loader.php?idFile=333">007</a></td>
        <td>Agosto 26</td>
        <td>Mitiga efectos del Decreto 1171 de 2026.</td>
        <td>826</td>
      </tr>
    </table>
    """


def test_parse_pagina_anio_extrae_filas_y_anexos():
    filas = _parse_pagina_anio(_pagina_anio_html(), _BASE)

    assert len(filas) == 2
    assert filas[0].numero_raw == "008"
    assert filas[0].fecha_raw == "Septiembre 01"
    assert filas[0].descripcion.startswith("Imparte instrucciones sobre prospectos.")
    assert filas[0].anexos_urls == [f"{_BASE}/loader.php?idFile=222"]
    assert filas[1].numero_raw == "007"
    assert filas[1].anexos_urls == []
```

Agregar el import al inicio del test:
`from core.scrapers.families.superfinanciera.normativa import _parse_indice, _parse_pagina_anio`.

- [ ] **Step 2: Correr y ver fallar**

Run: `pytest tests/families/test_superfinanciera_normativa.py::test_parse_pagina_anio_extrae_filas_y_anexos -v`
Expected: FAIL con `ImportError`.

- [ ] **Step 3: Implementar `_parse_pagina_anio`**

```python
from collections import namedtuple

_FilaNormativa = namedtuple("_FilaNormativa", "numero_raw fecha_raw descripcion anexos_urls")


def _parse_pagina_anio(html: str, base_url: str) -> List[_FilaNormativa]:
    soup = BeautifulSoup(html, "html.parser")
    tabla = soup.find("table")
    if tabla is None:
        return []
    filas: List[_FilaNormativa] = []
    for tr in tabla.find_all("tr"):
        celdas = tr.find_all("td")
        if len(celdas) < 3:
            continue  # fila de encabezado u otra cosa
        celda_num, celda_fecha, celda_desc = celdas[0], celdas[1], celdas[2]
        enlace_num = celda_num.find("a", href=True)
        if enlace_num is None:
            continue
        numero_raw = celda_num.get_text(strip=True)
        fecha_raw = celda_fecha.get_text(" ", strip=True)
        anexos_urls = [
            urljoin(base_url + "/", a["href"])
            for a in celda_desc.find_all("a", href=True)
        ]
        # descripción sin el texto de los enlaces de anexo
        for a in celda_desc.find_all("a"):
            a.extract()
        descripcion = celda_desc.get_text(" ", strip=True) or None
        filas.append(_FilaNormativa(numero_raw, fecha_raw, descripcion, anexos_urls))
    return filas
```

- [ ] **Step 4: Correr y ver pasar**

Run: `pytest tests/families/test_superfinanciera_normativa.py::test_parse_pagina_anio_extrae_filas_y_anexos -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/superfinanciera/normativa.py tests/families/test_superfinanciera_normativa.py
git commit -m "feat(superfinanciera): parsear la tabla de una página de año"
```

---

### Task 4: `normativa` — fecha, título canónico y armado del `RawDocModel`

**Files:**
- Modify: `core/scrapers/families/superfinanciera/normativa.py`
- Test: `tests/families/test_superfinanciera_normativa.py`

**Interfaces:**
- Consumes: `_FilaNormativa` (Task 3), `_TIPOS` (Task 2).
- Produces:
  - `_MESES: dict[str, str]` (nombre en español → `"01"`..`"12"`).
  - `_fecha_iso(fecha_raw: str, anio: int) -> str | None` — `"Septiembre 01" , 2026 -> "2026-09-01"`; `None` si no parsea.
  - `_titulo(sigla: str, numero_raw: str, anio: int) -> tuple[str, bool]` — devuelve `(titulo, title_unverified)`.
  - `_fila_a_docs(fila, tipo, sigla, anio, fini, ffin, source, on_progress) -> list[RawDocModel]` — documento madre + anexos, ya filtrado por `[fini, ffin]`.

- [ ] **Step 1: Escribir los tests**

```python
from core.scrapers.families.superfinanciera.normativa import (
    _parse_indice, _parse_pagina_anio, _fecha_iso, _titulo, _fila_a_docs, _FilaNormativa,
)

_SOURCE = "Superintendencia Financiera de Colombia"


def test_fecha_iso_arma_la_fecha_con_el_anio_de_la_pagina():
    assert _fecha_iso("Septiembre 01", 2026) == "2026-09-01"
    assert _fecha_iso("Diciembre 30", 2020) == "2020-12-30"
    assert _fecha_iso("sin fecha", 2026) is None


def test_titulo_canonico_por_tipo():
    assert _titulo("C", "8", 2026) == ("C_SF_0008_2026", False)
    assert _titulo("CCIR", "20", 2026) == ("CCIR_SF_0020_2026", False)
    assert _titulo("R", "1215", 2020) == ("R_SF_1215_2020", False)
    assert _titulo("C", "s/n", 2026) == ("s/n", True)


def test_fila_a_docs_documento_madre_y_anexos():
    fila = _FilaNormativa(
        numero_raw="8",
        fecha_raw="Septiembre 01",
        descripcion="Imparte instrucciones.",
        anexos_urls=["https://www.superfinanciera.gov.co/loader.php?idFile=222",
                     "https://www.superfinanciera.gov.co/loader.php?idFile=223"],
    )
    fila = fila._replace()  # doc madre lleva el enlace del número; se pasa aparte
    docs = _fila_a_docs(
        fila,
        tipo="Circular Externa",
        sigla="C",
        anio=2026,
        numero_link="https://www.superfinanciera.gov.co/loader.php?idFile=111",
        fini="2026-01-01",
        ffin="2026-12-31",
        source=_SOURCE,
        on_progress=lambda m: None,
    )

    assert [d.title for d in docs] == ["C_SF_0008_2026", "C_SF_0008_2026_A01", "C_SF_0008_2026_A02"]
    madre = docs[0]
    assert madre.tipo == "Circular Externa"
    assert madre.f_public == "2026-09-01"
    assert madre.f_providencia == "2026-09-01"
    assert madre.detalle == "Imparte instrucciones."
    assert madre.link == {"url": "https://www.superfinanciera.gov.co/loader.php?idFile=111", "method": "GET"}
    assert madre.save_path == "Superintendencia Financiera de Colombia/2026-09-01/Circular Externa/C_SF_0008_2026(extension)"
    anexo1 = docs[1]
    assert anexo1.tipo == "Circular Externa"
    assert anexo1.f_public == "2026-09-01"
    assert anexo1.link == {"url": "https://www.superfinanciera.gov.co/loader.php?idFile=222", "method": "GET"}
    assert anexo1.save_path == "Superintendencia Financiera de Colombia/2026-09-01/Circular Externa/C_SF_0008_2026_A01(extension)"


def test_fila_a_docs_fuera_de_rango_se_descarta():
    fila = _FilaNormativa("8", "Septiembre 01", "x", [])
    docs = _fila_a_docs(
        fila, tipo="Circular Externa", sigla="C", anio=2026,
        numero_link="https://x/loader.php?idFile=1",
        fini="2026-01-01", ffin="2026-06-30", source=_SOURCE, on_progress=lambda m: None,
    )
    assert docs == []


def test_fila_a_docs_sin_numero_marca_unverified_y_no_emite_anexos():
    fila = _FilaNormativa("s/n", "Septiembre 01", "x",
                          ["https://x/loader.php?idFile=222"])
    docs = _fila_a_docs(
        fila, tipo="Circular Externa", sigla="C", anio=2026,
        numero_link="https://x/loader.php?idFile=1",
        fini="2026-01-01", ffin="2026-12-31", source=_SOURCE, on_progress=lambda m: None,
    )
    assert len(docs) == 1
    assert docs[0].title_unverified is True


def test_fila_a_docs_fecha_no_parseable_usa_primero_de_enero_y_avisa():
    avisos = []
    fila = _FilaNormativa("8", "??", "x", [])
    docs = _fila_a_docs(
        fila, tipo="Circular Externa", sigla="C", anio=2026,
        numero_link="https://x/loader.php?idFile=1",
        fini="2026-01-01", ffin="2026-12-31", source=_SOURCE, on_progress=avisos.append,
    )
    assert docs[0].f_public == "2026-01-01"
    assert any("Error" not in a and "01-01" not in a for a in avisos) or avisos  # hay al menos un aviso
```

Nota: `_fila_a_docs` recibe el enlace del número por separado
(`numero_link`) porque el `_FilaNormativa` de Task 3 no lo lleva. Ajustar
`_parse_pagina_anio` en este task para incluirlo: cambiar el namedtuple a
`_FilaNormativa = namedtuple("_FilaNormativa", "numero_raw numero_link fecha_raw descripcion anexos_urls")`
y poblar `numero_link = urljoin(base_url + "/", enlace_num["href"])`. Actualizar
el test de Task 3 en consecuencia (agregar `filas[0].numero_link ==
f"{_BASE}/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=descargar&idFile=111"`).

- [ ] **Step 2: Correr y ver fallar**

Run: `pytest tests/families/test_superfinanciera_normativa.py -v`
Expected: FAIL (`ImportError` / los nuevos tests).

- [ ] **Step 3: Implementar**

```python
_MESES = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
    "septiembre": "09", "setiembre": "09", "octubre": "10",
    "noviembre": "11", "diciembre": "12",
}
_FECHA_RE = re.compile(
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+(\d{1,2})",
    re.IGNORECASE,
)


def _fecha_iso(fecha_raw: str, anio: int):
    m = _FECHA_RE.search(fecha_raw or "")
    if not m:
        return None
    mes = _MESES[m.group(1).lower()]
    dia = int(m.group(2))
    if not 1 <= dia <= 31:
        return None
    return f"{anio:04d}-{mes}-{dia:02d}"


def _titulo(sigla: str, numero_raw: str, anio: int):
    if numero_raw and numero_raw.isdigit():
        return f"{sigla}_SF_{int(numero_raw):04d}_{anio}", False
    return (numero_raw or "documento"), True


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _fila_a_docs(fila, tipo, sigla, anio, numero_link, fini, ffin, source, on_progress):
    title, unverified = _titulo(sigla, fila.numero_raw, anio)
    fecha = _fecha_iso(fila.fecha_raw, anio)
    if fecha is None:
        fecha = f"{anio:04d}-01-01"
        if on_progress:
            on_progress(f"[{source}] Aviso: sin fecha parseable para «{title}» ({tipo} {anio}), se usa {fecha}")
    if fecha < fini or fecha > ffin:
        return []

    docs = [RawDocModel(
        source=source,
        link={"url": numero_link, "method": "GET"},
        title=title,
        tipo=tipo,
        f_public=fecha,
        f_providencia=fecha,
        detalle=fila.descripcion,
        save_path=storage_path(source, fecha, tipo, f"{_safe_title(title)}(extension)"),
        title_unverified=unverified,
    )]
    if unverified:
        return docs  # sin un título madre estable no se pueden nombrar los anexos
    for n, url in enumerate(fila.anexos_urls, start=1):
        anexo_title = f"{title}_A{n:02d}"
        docs.append(RawDocModel(
            source=source,
            link={"url": url, "method": "GET"},
            title=anexo_title,
            tipo=tipo,
            f_public=fecha,
            f_providencia=fecha,
            detalle=f"Anexo {n} de {title}",
            save_path=storage_path(source, fecha, tipo, f"{_safe_title(anexo_title)}(extension)"),
        ))
    return docs
```

- [ ] **Step 4: Correr y ver pasar**

Run: `pytest tests/families/test_superfinanciera_normativa.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/superfinanciera/normativa.py tests/families/test_superfinanciera_normativa.py
git commit -m "feat(superfinanciera): fecha, título canónico y anexos de normativa"
```

---

### Task 5: `normativa` — orquestación `scrap_normativa`

**Files:**
- Modify: `core/scrapers/families/superfinanciera/normativa.py`
- Test: `tests/families/test_superfinanciera_normativa.py`

**Interfaces:**
- Consumes: todo lo anterior de `normativa.py`.
- Produces:
  - `scrap_normativa(fini, ffin, source, limit=10000, stop_event=None, on_progress=None) -> list[RawDocModel]`
    (reemplaza el stub de Task 1).

- [ ] **Step 1: Escribir el test de integración**

```python
import responses
from core.scrapers.families.superfinanciera.normativa import scrap_normativa, _INDICE_URL, _BASE_URL


@responses.activate
def test_scrap_normativa_recorre_tipos_y_anios_en_rango():
    responses.add(responses.GET, _INDICE_URL, body=_indice_html())
    # solo 2026 está en rango; se piden los 3 tipos de ese año
    responses.add(responses.GET, f"{_BASE_URL}/publicaciones/10115974/circulares-externas-2026/", body=_pagina_anio_html())
    responses.add(responses.GET, f"{_BASE_URL}/10115975", body=_pagina_anio_html())
    responses.add(responses.GET, f"{_BASE_URL}/publicaciones/10115976/resoluciones-2026/", body=_pagina_anio_html())

    docs = scrap_normativa("2026-01-01", "2026-12-31", _SOURCE, on_progress=lambda m: None)

    # _pagina_anio_html tiene 2 filas; la primera trae 1 anexo -> 3 docs por tipo
    titles = [d.title for d in docs]
    assert "C_SF_0008_2026" in titles
    assert "C_SF_0008_2026_A01" in titles
    assert "CCIR_SF_0008_2026" in titles
    assert "R_SF_0007_2026" in titles
    # 2025 no se pidió (fuera de rango)
    assert all("2025" not in t for t in titles)


@responses.activate
def test_scrap_normativa_una_pagina_fallida_no_tumba_el_resto():
    responses.add(responses.GET, _INDICE_URL, body=_indice_html())
    responses.add(responses.GET, f"{_BASE_URL}/publicaciones/10115974/circulares-externas-2026/", status=500)
    responses.add(responses.GET, f"{_BASE_URL}/10115975", body=_pagina_anio_html())
    responses.add(responses.GET, f"{_BASE_URL}/publicaciones/10115976/resoluciones-2026/", body=_pagina_anio_html())
    avisos = []

    docs = scrap_normativa("2026-01-01", "2026-12-31", _SOURCE, on_progress=avisos.append)

    assert any(d.title.startswith("CCIR_SF_") for d in docs)
    assert any("Error" in a for a in avisos)
```

- [ ] **Step 2: Correr y ver fallar**

Run: `pytest tests/families/test_superfinanciera_normativa.py -k scrap_normativa -v`
Expected: FAIL (el stub devuelve `[]`).

- [ ] **Step 3: Implementar `scrap_normativa`**

```python
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def scrap_normativa(fini, ffin, source, limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
    session = requests.Session()
    session.headers.update(_HEADERS)

    try:
        resp = session.get(_INDICE_URL, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        if on_progress:
            on_progress(f"[{source}] Error consultando el índice de normativa: {e}")
        return []

    indice = _parse_indice(resp.text, _BASE_URL)
    anio_ini, anio_fin = int(fini[:4]), int(ffin[:4])
    docs: List[RawDocModel] = []

    for encabezado, (tipo, sigla) in _TIPOS.items():
        por_anio = indice.get(encabezado, {})
        for anio in range(anio_ini, anio_fin + 1):
            if stop_event is not None and stop_event.is_set():
                return docs[:limit]
            if len(docs) >= limit:
                return docs[:limit]
            url = por_anio.get(anio)
            if url is None:
                continue
            if on_progress:
                on_progress(f"[{source}] {tipo} {anio}...")
            try:
                pr = session.get(url, timeout=30)
                pr.raise_for_status()
            except Exception as e:
                if on_progress:
                    on_progress(f"[{source}] Error consultando {tipo} {anio}: {e}")
                continue
            for fila in _parse_pagina_anio(pr.text, _BASE_URL):
                docs.extend(
                    _fila_a_docs(fila, tipo, sigla, anio, fila.numero_link, fini, ffin, source, on_progress)
                )
    return docs[:limit]
```

- [ ] **Step 4: Correr y ver pasar**

Run: `pytest tests/families/test_superfinanciera_normativa.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/superfinanciera/normativa.py tests/families/test_superfinanciera_normativa.py
git commit -m "feat(superfinanciera): orquestación del scraper de normativa"
```

---

## PARTE B — Scraper `conceptos`

### Task 6: `conceptos` — parsear una página de resultados del catálogo ABCD

**Files:**
- Modify: `core/scrapers/families/superfinanciera/conceptos.py`
- Test: `tests/families/test_superfinanciera_conceptos.py`

**Interfaces:**
- Produces:
  - `_BUSCAR_URL: str` = `"https://www.superfinanciera.gov.co/ABCD/superfinanciera/php/buscar_integrada.php"`
  - `_RegistroConcepto` = `namedtuple("_RegistroConcepto", "radicado consecutivo fecha_texto titulo_norma resumen archivo_url raw_concepto")`
  - `_parse_pagina(html: str, base_url: str) -> list[_RegistroConcepto]`
  - `_total_registros(html: str) -> int | None`

- [ ] **Step 1: Escribir el test**

```python
# tests/families/test_superfinanciera_conceptos.py
from core.scrapers.families.superfinanciera.conceptos import _parse_pagina, _total_registros

_BASE = "https://www.superfinanciera.gov.co"


def _registro_html(concepto, titulo, resumen, id_file):
    return f"""
    <table class="registro">
      <tr><td class="td1">Concepto:</td><td>{concepto}</td></tr>
      <tr><td class="td1">Autor Corporativo:</td><td>Colombia. Superintendencia Financiera de Colombia</td></tr>
      <tr><td class="td1">Título de la norma:</td><td>{titulo}</td></tr>
      <tr><td class="td1">Documento fuente:</td><td>Superintendencia Financiera de Colombia. Conceptos 2021</td></tr>
      <tr><td class="td1">Resumen:</td><td>{resumen}</td></tr>
      <tr><td class="td1">Temas/Materias:</td><td>SERVICIOS FINANCIEROS</td></tr>
      <tr><td class="td1">Acceso web (URL):</td>
          <td><a href="/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=descargar&idFile={id_file}">Archivo de texto</a></td></tr>
    </table>
    """


def _pagina_html(registros, total=3431):
    cuerpo = "".join(registros)
    return f"""
    <html><body>
      <div>Mostrando del 1 al 25 de {total} registros</div>
      {cuerpo}
      <form name="continuar" action="buscar_integrada.php" method="post">
        <input type="hidden" name="Expresion" value="$">
        <input type="hidden" name="base" value="juris">
        <input type="hidden" name="Opcion" value="libre">
        <input type="hidden" name="coleccion" value="ac|Doctrina y conceptos|TM_">
        <input type="hidden" name="count" value="25">
        <input type="hidden" name="pagina" value="1">
        <input type="hidden" name="desde" value="1">
      </form>
    </body></html>
    """


def test_parse_pagina_extrae_campos_del_registro():
    html = _pagina_html([
        _registro_html("2020311455 - 001 del 5 de febrero de 2021", "AFP. Régimen de inversiones", "Límite del 5%.", "1051137"),
    ])
    regs = _parse_pagina(html, _BASE)

    assert len(regs) == 1
    r = regs[0]
    assert r.radicado == "2020311455"
    assert r.consecutivo == "001"
    assert r.fecha_texto == "5 de febrero de 2021"
    assert r.titulo_norma == "AFP. Régimen de inversiones"
    assert r.resumen == "Límite del 5%."
    assert r.archivo_url == f"{_BASE}/loader.php?lServicio=Tools2&lTipo=descargas&lFuncion=descargar&idFile=1051137"


def test_total_registros():
    assert _total_registros(_pagina_html([], total=3431)) == 3431
    assert _total_registros("<div>sin nada</div>") is None
```

- [ ] **Step 2: Correr y ver fallar**

Run: `pytest tests/families/test_superfinanciera_conceptos.py -v`
Expected: FAIL con `ImportError`.

- [ ] **Step 3: Implementar**

```python
# core/scrapers/families/superfinanciera/conceptos.py
import math
import re
from collections import namedtuple
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from core.fecha_es import parse_fecha_providencia_es
from core.models import RawDocModel
from core.utils import storage_path

_BASE_URL = "https://www.superfinanciera.gov.co"
_BUSCAR_URL = f"{_BASE_URL}/ABCD/superfinanciera/php/buscar_integrada.php"
_COLECCION = "ac|Doctrina y conceptos|TM_"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_POR_PAGINA = 25

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_TOTAL_RE = re.compile(r"de\s+([\d.,]+)\s+registros", re.IGNORECASE)
# "2020311455 - 001 del 5 de febrero de 2021"
_CONCEPTO_RE = re.compile(r"^\s*(\d{6,})\s*-\s*(\d{1,4})\s+del?\s+(.+?)\s*$")

_RegistroConcepto = namedtuple(
    "_RegistroConcepto", "radicado consecutivo fecha_texto titulo_norma resumen archivo_url raw_concepto"
)


def _total_registros(html: str) -> Optional[int]:
    m = _TOTAL_RE.search(html or "")
    if not m:
        return None
    return int(re.sub(r"[.,]", "", m.group(1)))


def _campo(registro, etiqueta: str) -> str:
    for td in registro.find_all("td"):
        if td.get_text(strip=True).rstrip(":").strip().lower() == etiqueta.rstrip(":").lower():
            siguiente = td.find_next_sibling("td")
            if siguiente is not None:
                return siguiente.get_text(" ", strip=True)
    return ""


def _parse_pagina(html: str, base_url: str) -> List[_RegistroConcepto]:
    soup = BeautifulSoup(html, "html.parser")
    registros: List[_RegistroConcepto] = []
    for tabla in soup.find_all("table", class_="registro"):
        raw_concepto = _campo(tabla, "Concepto:")
        titulo_norma = _campo(tabla, "Título de la norma:")
        resumen = _campo(tabla, "Resumen:")
        enlace = tabla.find("a", string=re.compile("Archivo de texto", re.IGNORECASE))
        archivo_url = urljoin(base_url + "/", enlace["href"]) if enlace and enlace.get("href") else None

        m = _CONCEPTO_RE.match(raw_concepto)
        if m:
            radicado, consecutivo, fecha_texto = m.group(1), m.group(2), m.group(3)
        else:
            radicado = consecutivo = None
            fecha_texto = raw_concepto
        registros.append(_RegistroConcepto(
            radicado, consecutivo, fecha_texto, titulo_norma, resumen, archivo_url, raw_concepto
        ))
    return registros
```

- [ ] **Step 4: Correr y ver pasar**

Run: `pytest tests/families/test_superfinanciera_conceptos.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/superfinanciera/conceptos.py tests/families/test_superfinanciera_conceptos.py
git commit -m "feat(superfinanciera): parsear una página de resultados del catálogo ABCD"
```

---

### Task 7: `conceptos` — título canónico, fecha y `RawDocModel`

**Files:**
- Modify: `core/scrapers/families/superfinanciera/conceptos.py`
- Test: `tests/families/test_superfinanciera_conceptos.py`

**Interfaces:**
- Consumes: `_RegistroConcepto` (Task 6).
- Produces:
  - `_titulo_concepto(radicado: str, consecutivo: str) -> str` — aplica la regla del sufijo del consecutivo.
  - `_registro_a_doc(reg, fini, ffin, source, on_progress) -> RawDocModel | None` — `None` si queda fuera de rango o no se puede fechar.

- [ ] **Step 1: Escribir los tests**

```python
from datetime import date
from core.scrapers.families.superfinanciera.conceptos import _titulo_concepto, _registro_a_doc, _RegistroConcepto

_SOURCE = "Superintendencia Financiera de Colombia"


def test_titulo_concepto_toma_anio_y_numero_del_radicado():
    assert _titulo_concepto("2026019914", "001") == "CTO_SF_0019914_2026"
    assert _titulo_concepto("2020311455", "1") == "CTO_SF_0311455_2020"


def test_titulo_concepto_sufija_el_consecutivo_solo_si_no_es_1():
    assert _titulo_concepto("1998045919", "1") == "CTO_SF_0045919_1998"
    assert _titulo_concepto("1998045919", "4") == "CTO_SF_0045919_1998_04"
    assert _titulo_concepto("1998045919", "004") == "CTO_SF_0045919_1998_04"


def _reg(concepto_ok=True, id_file="1051137"):
    if concepto_ok:
        return _RegistroConcepto(
            "2020311455", "001", "5 de febrero de 2021", "AFP. Régimen de inversiones",
            "Límite del 5%.", f"https://x/loader.php?idFile={id_file}", "2020311455 - 001 del 5 de febrero de 2021",
        )
    return _RegistroConcepto(
        None, None, "texto sin forma de concepto", "Un título temático", "Resumen.",
        f"https://x/loader.php?idFile={id_file}", "texto sin forma de concepto",
    )


def test_registro_a_doc_arma_el_documento():
    doc = _registro_a_doc(_reg(), "2021-01-01", "2021-12-31", _SOURCE, lambda m: None)
    assert doc.title == "CTO_SF_0311455_2020"
    assert doc.tipo == "Concepto"
    assert doc.f_public == "2021-02-05"
    assert doc.f_providencia == "2021-02-05"
    assert doc.detalle == "AFP. Régimen de inversiones — Límite del 5%."
    assert doc.link == {"url": "https://x/loader.php?idFile=1051137", "method": "GET"}
    assert doc.save_path == "Superintendencia Financiera de Colombia/2021-02-05/Concepto/CTO_SF_0311455_2020(extension)"
    assert doc.title_unverified is False


def test_registro_a_doc_fuera_de_rango_es_none():
    assert _registro_a_doc(_reg(), "2021-03-01", "2021-12-31", _SOURCE, lambda m: None) is None


def test_registro_a_doc_sin_concepto_parseable_usa_titulo_crudo_y_unverified():
    reg = _RegistroConcepto(
        None, None, "8 de mayo de 2026 algo", "Un título temático", "Resumen.",
        "https://x/loader.php?idFile=9", "raw",
    )
    doc = _registro_a_doc(reg, "2026-01-01", "2026-12-31", _SOURCE, lambda m: None)
    assert doc.title_unverified is True
    assert doc.title == "Un título temático"
    assert doc.f_public == "2026-05-08"


def test_registro_a_doc_sin_fecha_se_descarta_con_aviso():
    avisos = []
    reg = _RegistroConcepto(None, None, "sin fecha aquí", "T", "R", "https://x/loader.php?idFile=9", "raw")
    assert _registro_a_doc(reg, "2026-01-01", "2026-12-31", _SOURCE, avisos.append) is None
    assert avisos
```

- [ ] **Step 2: Correr y ver fallar**

Run: `pytest tests/families/test_superfinanciera_conceptos.py -k "titulo_concepto or registro_a_doc" -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implementar**

```python
def _titulo_concepto(radicado: str, consecutivo: str) -> str:
    anio = radicado[:4]
    numero = radicado[4:]
    base = f"CTO_SF_{numero.zfill(7)}_{anio}"
    try:
        c = int(consecutivo)
    except (TypeError, ValueError):
        c = 1
    if c != 1:
        base = f"{base}_{c:02d}"
    return base


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _registro_a_doc(reg, fini, ffin, source, on_progress) -> Optional[RawDocModel]:
    fecha = parse_fecha_providencia_es(reg.fecha_texto or "")
    if fecha is None:
        if on_progress:
            on_progress(f"[{source}] Aviso: sin fecha en «{reg.raw_concepto[:80]}», se omite")
        return None
    fecha_iso = fecha.strftime("%Y-%m-%d")
    if fecha_iso < fini or fecha_iso > ffin:
        return None
    if not reg.archivo_url:
        if on_progress:
            on_progress(f"[{source}] Aviso: sin «Archivo de texto» para «{reg.raw_concepto[:80]}», se omite")
        return None

    if reg.radicado and reg.consecutivo:
        title = _titulo_concepto(reg.radicado, reg.consecutivo)
        unverified = False
    else:
        title = (reg.titulo_norma or reg.raw_concepto or "concepto")[:120]
        unverified = True

    partes = [p for p in (reg.titulo_norma, reg.resumen) if p]
    detalle = " — ".join(partes) or None

    return RawDocModel(
        source=source,
        link={"url": reg.archivo_url, "method": "GET"},
        title=title,
        tipo="Concepto",
        f_public=fecha_iso,
        f_providencia=fecha_iso,
        detalle=detalle,
        save_path=storage_path(source, fecha_iso, "Concepto", f"{_safe_title(title)}(extension)"),
        title_unverified=unverified,
    )
```

- [ ] **Step 4: Correr y ver pasar**

Run: `pytest tests/families/test_superfinanciera_conceptos.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/superfinanciera/conceptos.py tests/families/test_superfinanciera_conceptos.py
git commit -m "feat(superfinanciera): título canónico y armado de documento de conceptos"
```

---

### Task 8: `conceptos` — orquestación `scrap_conceptos` (paginación completa)

**Files:**
- Modify: `core/scrapers/families/superfinanciera/conceptos.py`
- Test: `tests/families/test_superfinanciera_conceptos.py`

**Interfaces:**
- Consumes: todo lo anterior de `conceptos.py`.
- Produces:
  - `scrap_conceptos(fini, ffin, source, limit=10000, stop_event=None, on_progress=None) -> list[RawDocModel]`
    (reemplaza el stub de Task 1).

- [ ] **Step 1: Escribir el test de integración**

```python
import responses
from core.scrapers.families.superfinanciera.conceptos import scrap_conceptos, _BUSCAR_URL


@responses.activate
def test_scrap_conceptos_recorre_todas_las_paginas_y_filtra_por_fecha():
    # total 50 -> 2 páginas de 25 (pero mandamos pocos registros por simplicidad)
    pagina1 = _pagina_html([
        _registro_html("2021012412 - 003 del 23 de febrero de 2021", "Almacenes", "R1", "111"),
        _registro_html("2019009999 - 001 del 1 de marzo de 2019", "Viejo", "R2", "222"),
    ], total=50)
    pagina2 = _pagina_html([
        _registro_html("2021041211 - 001 del 1 de marzo de 2021", "Broker", "R3", "333"),
    ], total=50)
    responses.add(responses.POST, _BUSCAR_URL, body=pagina1)   # primera consulta
    responses.add(responses.POST, _BUSCAR_URL, body=pagina2)   # página 2

    docs = scrap_conceptos("2021-01-01", "2021-12-31", _SOURCE, on_progress=lambda m: None)

    titles = sorted(d.title for d in docs)
    assert titles == ["CTO_SF_0012412_2021_03", "CTO_SF_0041211_2021"]  # el de 2019 queda fuera de rango
    # se hicieron 2 POST (primera + página 2)
    assert len(responses.calls) == 2


@responses.activate
def test_scrap_conceptos_reintenta_una_pagina_fallida_y_sigue():
    pagina1 = _pagina_html([
        _registro_html("2021012412 - 001 del 23 de febrero de 2021", "A", "111"),
    ], total=50)
    responses.add(responses.POST, _BUSCAR_URL, body=pagina1)
    responses.add(responses.POST, _BUSCAR_URL, status=500)  # página 2, primer intento
    responses.add(responses.POST, _BUSCAR_URL, status=500)  # página 2, reintento
    avisos = []

    docs = scrap_conceptos("2021-01-01", "2021-12-31", _SOURCE, on_progress=avisos.append)

    assert [d.title for d in docs] == ["CTO_SF_0012412_2021"]
    assert any("Error" in a for a in avisos)
```

- [ ] **Step 2: Correr y ver fallar**

Run: `pytest tests/families/test_superfinanciera_conceptos.py -k scrap_conceptos -v`
Expected: FAIL (el stub devuelve `[]`).

- [ ] **Step 3: Implementar `scrap_conceptos`**

```python
def _campos_form_continuar(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", attrs={"name": "continuar"})
    if form is None:
        return {}
    campos = {}
    for inp in form.find_all("input"):
        nombre = inp.get("name")
        if nombre:
            campos[nombre] = inp.get("value", "")
    return campos


def _consulta_inicial() -> dict:
    return {
        "base": "juris", "cipar": "", "Opcion": "libre", "coleccion": _COLECCION,
        "Expresion": "$", "titulo_c": "", "resaltar": "", "submenu": "", "Pft": "", "mostrar_exp": "",
    }


def scrap_conceptos(fini, ffin, source, limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
    session = requests.Session()
    session.headers.update(_HEADERS)
    docs: List[RawDocModel] = []

    try:
        r = session.post(_BUSCAR_URL, data=_consulta_inicial(), timeout=60)
        r.raise_for_status()
    except Exception as e:
        if on_progress:
            on_progress(f"[{source}] Error abriendo la colección Doctrina y conceptos: {e}")
        return []

    total = _total_registros(r.text) or 0
    paginas = max(1, math.ceil(total / _POR_PAGINA))
    if on_progress:
        on_progress(f"[{source}] Doctrina y conceptos: {total} registros, {paginas} páginas")

    def _procesar(html: str):
        for reg in _parse_pagina(html, _BASE_URL):
            doc = _registro_a_doc(reg, fini, ffin, source, on_progress)
            if doc is not None:
                docs.append(doc)

    _procesar(r.text)
    campos = _campos_form_continuar(r.text)

    for pagina in range(2, paginas + 1):
        if stop_event is not None and stop_event.is_set():
            return docs[:limit]
        if len(docs) >= limit:
            return docs[:limit]
        cuerpo = dict(campos)
        cuerpo["pagina"] = str(pagina)
        cuerpo["desde"] = str((pagina - 1) * _POR_PAGINA + 1)

        html = None
        for intento in range(2):
            try:
                pr = session.post(_BUSCAR_URL, data=cuerpo, timeout=60)
                pr.raise_for_status()
                html = pr.text
                break
            except Exception as e:
                if intento == 1 and on_progress:
                    on_progress(f"[{source}] Error consultando la página {pagina} de conceptos: {e}")
        if html is None:
            continue
        _procesar(html)
        nuevos_campos = _campos_form_continuar(html)
        if nuevos_campos:
            campos = nuevos_campos

    return docs[:limit]
```

- [ ] **Step 4: Correr y ver pasar**

Run: `pytest tests/families/test_superfinanciera_conceptos.py -v`
Expected: PASS

- [ ] **Step 5: Correr toda la suite de familias**

Run: `pytest tests/families/ -v`
Expected: PASS (sin regresiones).

- [ ] **Step 6: Commit**

```bash
git add core/scrapers/families/superfinanciera/conceptos.py tests/families/test_superfinanciera_conceptos.py
git commit -m "feat(superfinanciera): orquestación del scraper de Doctrina y Conceptos"
```

---

## PARTE C — Agrupación de anexos (backend)

### Task 9: Helpers de nomenclatura de anexos

**Files:**
- Modify: `core/naming.py`
- Test: `tests/test_naming.py` (agregar; si no existe, crearlo)

**Interfaces:**
- Produces:
  - `es_anexo_title(title: str) -> bool` — `True` si `title` termina en `_A` + 2 dígitos.
  - `titulo_padre_de_anexo(title: str) -> str | None` — quita el sufijo `_A\d\d`; `None` si no es anexo.

- [ ] **Step 1: Escribir el test**

```python
# tests/test_naming.py (agregar al final, o crear con este contenido + imports)
from core.naming import es_anexo_title, titulo_padre_de_anexo


def test_es_anexo_title():
    assert es_anexo_title("C_SF_0020_2026_A01") is True
    assert es_anexo_title("C_SF_0020_2026_A15") is True
    assert es_anexo_title("C_SF_0020_2026") is False
    assert es_anexo_title("CTO_SF_0019914_2026") is False
    assert es_anexo_title("") is False


def test_titulo_padre_de_anexo():
    assert titulo_padre_de_anexo("C_SF_0020_2026_A01") == "C_SF_0020_2026"
    assert titulo_padre_de_anexo("R_SF_1215_2020_A09") == "R_SF_1215_2020"
    assert titulo_padre_de_anexo("C_SF_0020_2026") is None
```

- [ ] **Step 2: Correr y ver fallar**

Run: `pytest tests/test_naming.py -k anexo -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implementar en `core/naming.py`**

```python
# junto a los otros helpers de core/naming.py
_ANEXO_SUFFIX_RE = re.compile(r"_A\d{2}$")


def es_anexo_title(title: str) -> bool:
    return bool(_ANEXO_SUFFIX_RE.search(title or ""))


def titulo_padre_de_anexo(title: str) -> Optional[str]:
    if not es_anexo_title(title):
        return None
    return _ANEXO_SUFFIX_RE.sub("", title)
```

- [ ] **Step 4: Correr y ver pasar**

Run: `pytest tests/test_naming.py -k anexo -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/naming.py tests/test_naming.py
git commit -m "feat(anexos): helpers de nomenclatura es_anexo_title / titulo_padre_de_anexo"
```

---

### Task 10: Colapso de anexos y conteo en `repository`

**Files:**
- Modify: `core/db/repository.py`
- Test: `tests/test_repository.py` (agregar tests al final)

**Interfaces:**
- Consumes: `es_anexo_title` (Task 9).
- Produces:
  - `list_documents(..., collapse_case_families=...)` — ahora también
    oculta filas de anexo (`superfinanciera`, título `_A\d\d`) cuando
    existe el documento padre en la misma fuente.
  - `anexo_counts_by_document(db, documents, family_keys) -> dict[int, int]`
    — `{document_id: cantidad_de_anexos}` para los documentos madre de
    `superfinanciera` (0 no se incluye).

- [ ] **Step 1: Escribir el test**

```python
# tests/test_repository.py — mismo estilo que el resto del archivo:
# create_source_family + create_source + insert_document, todo con db_session.
from core.db import repository


def _sf_source(db_session):
    repository.create_source_family(
        db_session, key="superfinanciera", display_name="Superintendencia Financiera de Colombia"
    )
    return repository.create_source(
        db_session, family_key="superfinanciera",
        name="Superintendencia Financiera de Colombia", family_params={},
    )


def _sf_doc(db_session, source_id, title, doc_id=None):
    return repository.insert_document(
        db_session,
        doc_id=doc_id or title,
        source_id=source_id,
        title=title,
        tipo="Circular Externa",
        storage_bucket="iurisync-test",
        storage_key=f"Superintendencia Financiera de Colombia/2026-01-01/Circular Externa/{title}.pdf",
    )


def test_list_documents_oculta_anexos_con_padre_presente(db_session):
    src = _sf_source(db_session)
    _sf_doc(db_session, src.id, "C_SF_0020_2026")
    _sf_doc(db_session, src.id, "C_SF_0020_2026_A01")
    _sf_doc(db_session, src.id, "C_SF_0020_2026_A02")

    items, _ = repository.list_documents(db_session, collapse_case_families=True, limit=50, offset=0)
    titles = {d.title for d in items}
    assert "C_SF_0020_2026" in titles
    assert "C_SF_0020_2026_A01" not in titles
    assert "C_SF_0020_2026_A02" not in titles


def test_list_documents_muestra_anexo_huerfano(db_session):
    src = _sf_source(db_session)
    _sf_doc(db_session, src.id, "C_SF_0099_2026_A01")  # sin padre

    items, _ = repository.list_documents(db_session, collapse_case_families=True, limit=50, offset=0)
    assert "C_SF_0099_2026_A01" in {d.title for d in items}


def test_list_documents_no_colapsa_anexos_sin_collapse_case_families(db_session):
    src = _sf_source(db_session)
    _sf_doc(db_session, src.id, "C_SF_0020_2026")
    _sf_doc(db_session, src.id, "C_SF_0020_2026_A01")

    items, _ = repository.list_documents(
        db_session, title_contains="C_SF_0020_2026", collapse_case_families=False, limit=50, offset=0
    )
    assert {"C_SF_0020_2026", "C_SF_0020_2026_A01"} <= {d.title for d in items}


def test_anexo_counts_by_document(db_session):
    src = _sf_source(db_session)
    madre = _sf_doc(db_session, src.id, "C_SF_0020_2026")
    _sf_doc(db_session, src.id, "C_SF_0020_2026_A01")
    _sf_doc(db_session, src.id, "C_SF_0020_2026_A02")
    sin_anexos = _sf_doc(db_session, src.id, "C_SF_0021_2026")

    counts = repository.anexo_counts_by_document(
        db_session, [madre, sin_anexos], {src.id: "superfinanciera"}
    )
    assert counts == {madre.id: 2}
```

- [ ] **Step 2: Correr y ver fallar**

Run: `pytest tests/test_repository.py -k "anexo or oculta_anexos" -v`
Expected: FAIL.

- [ ] **Step 3: Implementar el colapso en `list_documents`**

Dentro de `list_documents`, dentro del bloque `if collapse_case_families:`,
después de la línea que hace
`stmt = stmt.join(OuterSource, OuterSource.id == Document.source_id).where(or_(~is_case_title, ~has_newer_sibling))`,
agregar el colapso de anexos:

```python
        # Colapso de anexos (paralelo al de "case families"): en la familia
        # superfinanciera, una fila cuyo título termina en _A## se oculta del
        # listado si existe su documento padre (mismo título sin el sufijo,
        # 4 caracteres: "_A" + 2 dígitos) en la misma fuente.
        AnexoPadre = aliased(Document)
        titulo_padre = func.substr(Document.title, 1, func.length(Document.title) - 4)
        es_fila_anexo = and_(
            OuterSource.family_key == "superfinanciera",
            Document.title.op("~")(r"_A\d{2}$"),
        )
        padre_existe = (
            select(AnexoPadre.id)
            .where(
                AnexoPadre.source_id == Document.source_id,
                AnexoPadre.title == titulo_padre,
            )
            .exists()
        )
        stmt = stmt.where(or_(~es_fila_anexo, ~padre_existe))
```

(`aliased`, `and_`, `or_`, `func`, `select` ya están importados en el
módulo.)

- [ ] **Step 4: Implementar `anexo_counts_by_document`**

```python
def anexo_counts_by_document(
    db: Session, documents: list[Document], family_keys: dict[int, str]
) -> dict[int, int]:
    """Para cada documento madre de la familia superfinanciera (título que NO
    es de anexo), cuántas filas hijas {title}_A## existen en la misma fuente.
    No incluye entradas con 0."""
    from core.naming import es_anexo_title

    counts: dict[int, int] = {}
    for d in documents:
        if family_keys.get(d.source_id) != "superfinanciera":
            continue
        if es_anexo_title(d.title):
            continue
        n = db.scalar(
            select(func.count())
            .select_from(Document)
            .where(
                Document.source_id == d.source_id,
                Document.title.like(f"{_escape_like(d.title)}\\_A__", escape="\\"),
            )
        )
        if n:
            counts[d.id] = int(n)
    return counts
```

(`_escape_like` ya existe en el módulo; el patrón `\_A__` = "_A" literal +
exactamente 2 caracteres cualquiera.)

- [ ] **Step 5: Correr y ver pasar**

Run: `pytest tests/test_repository.py -k "anexo or oculta_anexos or huerfano" -v`
Expected: PASS

Run: `pytest tests/test_repository.py -v`
Expected: PASS (sin regresiones en el colapso de case families).

- [ ] **Step 6: Commit**

```bash
git add core/db/repository.py tests/test_repository.py
git commit -m "feat(anexos): colapso en list_documents y conteo por documento"
```

---

### Task 11: Endpoint `GET /documents/{id}/anexos` y `anexo_count` en el listado

**Files:**
- Modify: `core/db/repository.py`
- Modify: `api/routers/documents.py`
- Modify: `api/schemas.py`
- Test: `tests/test_api_documents.py` (agregar tests al final)

**Interfaces:**
- Consumes: `anexo_counts_by_document` (Task 10).
- Produces:
  - `repository.list_anexos_of_document(db, document) -> list[Document]` —
    filas `{document.title}_A##` de la misma fuente, ordenadas por título.
  - `DocumentOut.anexo_count: Optional[int]`.
  - `GET /documents/{document_id}/anexos` → `list[DocumentOut]`.

- [ ] **Step 1: Escribir el test**

```python
# tests/test_api_documents.py — patrón del archivo: fixtures api_client,
# auth_header, db_session; requests con headers=auth_header.
from core.db import repository


def _sf_src_y_docs(db_session, titulos):
    repository.create_source_family(
        db_session, key="superfinanciera", display_name="Superintendencia Financiera de Colombia"
    )
    source = repository.create_source(
        db_session, family_key="superfinanciera",
        name="Superintendencia Financiera de Colombia", family_params={},
    )
    docs = {}
    for t in titulos:
        docs[t] = repository.insert_document(
            db_session, doc_id=t, source_id=source.id, title=t, tipo="Circular Externa",
            storage_bucket="iurisync-test",
            storage_key=f"Superintendencia Financiera de Colombia/2026-01-01/Circular Externa/{t}.pdf",
        )
    return source, docs


def test_listado_documentos_incluye_anexo_count(api_client, auth_header, db_session):
    _sf_src_y_docs(db_session, ["C_SF_0020_2026", "C_SF_0020_2026_A01", "C_SF_0020_2026_A02"])

    r = api_client.get("/documents", headers=auth_header)
    assert r.status_code == 200
    fila = next(d for d in r.json()["items"] if d["title"] == "C_SF_0020_2026")
    assert fila["anexo_count"] == 2


def test_endpoint_anexos_de_documento(api_client, auth_header, db_session):
    _, docs = _sf_src_y_docs(
        db_session, ["C_SF_0020_2026", "C_SF_0020_2026_A02", "C_SF_0020_2026_A01"]
    )
    madre_id = docs["C_SF_0020_2026"].id

    r = api_client.get(f"/documents/{madre_id}/anexos", headers=auth_header)
    assert r.status_code == 200
    assert [d["title"] for d in r.json()] == ["C_SF_0020_2026_A01", "C_SF_0020_2026_A02"]


def test_endpoint_anexos_404_si_no_existe(api_client, auth_header):
    assert api_client.get("/documents/999999/anexos", headers=auth_header).status_code == 404
```

- [ ] **Step 2: Correr y ver fallar**

Run: `pytest tests/test_api_documents.py -k "anexo" -v`
Expected: FAIL.

- [ ] **Step 3: Agregar el campo al schema**

En `api/schemas.py`, dentro de `class DocumentOut`, junto a
`case_document_count`:

```python
    anexo_count: Optional[int] = None
```

- [ ] **Step 4: Implementar `list_anexos_of_document` en `repository.py`**

```python
def list_anexos_of_document(db: Session, document: Document) -> list[Document]:
    stmt = (
        select(Document)
        .where(
            Document.source_id == document.source_id,
            Document.title.like(f"{_escape_like(document.title)}\\_A__", escape="\\"),
        )
        .order_by(Document.title.asc())
    )
    return list(db.scalars(stmt).all())
```

- [ ] **Step 5: Poblar `anexo_count` en el listado y agregar el endpoint**

En `api/routers/documents.py`, en `get_documents`, después del bucle que
setea `case_document_count`:

```python
    anexo_counts = repository.anexo_counts_by_document(db, items, family_keys)
    for d in items:
        d.anexo_count = anexo_counts.get(d.id)
```

Y un endpoint nuevo, junto a `get_document_versions`:

```python
@router.get("/documents/{document_id}/anexos", response_model=list[DocumentOut])
def get_document_anexos(document_id: int, db: Session = Depends(get_db)):
    document = repository.get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    anexos = repository.list_anexos_of_document(db, document)
    fam = repository.get_source_family_keys(db, [document.source_id]).get(document.source_id)
    for a in anexos:
        a.nombre = nombre_documento(a, fam, False)
    return anexos
```

- [ ] **Step 6: Correr y ver pasar**

Run: `pytest tests/test_api_documents.py -k "anexo" -v`
Expected: PASS

Run: `pytest tests/test_api_documents.py -v`
Expected: PASS (sin regresiones).

- [ ] **Step 7: Commit**

```bash
git add core/db/repository.py api/routers/documents.py api/schemas.py tests/test_api_documents.py
git commit -m "feat(anexos): endpoint /documents/{id}/anexos y anexo_count en el listado"
```

---

### Task 12: Arrastrar anexos a la descarga masiva del documento madre

**Files:**
- Modify: `core/db/repository.py` (`_expandir_a_grupos`)
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: `list_anexos_of_document` (Task 11), `es_anexo_title` (Task 9).
- Produces: `_expandir_a_grupos` ahora agrega los ids de los anexos de un
  documento madre de `superfinanciera`.

- [ ] **Step 1: Escribir el test** (reusa `_sf_source` / `_sf_doc` de Task 10)

```python
def test_marcar_util_una_circular_arrastra_sus_anexos(db_session):
    src = _sf_source(db_session)
    madre = _sf_doc(db_session, src.id, "C_SF_0020_2026")
    a1 = _sf_doc(db_session, src.id, "C_SF_0020_2026_A01")
    a2 = _sf_doc(db_session, src.id, "C_SF_0020_2026_A02")

    repository.update_document_review_status(db_session, madre.id, "useful")

    db_session.refresh(a1)
    db_session.refresh(a2)
    assert a1.review_status == "useful"
    assert a2.review_status == "useful"


def test_marcar_util_un_anexo_no_arrastra_a_la_madre(db_session):
    src = _sf_source(db_session)
    madre = _sf_doc(db_session, src.id, "C_SF_0030_2026")
    a1 = _sf_doc(db_session, src.id, "C_SF_0030_2026_A01")

    repository.update_document_review_status(db_session, a1.id, "useful")

    db_session.refresh(madre)
    assert madre.review_status == "pending"
```

- [ ] **Step 2: Correr y ver fallar**

Run: `pytest tests/test_repository.py -k "arrastra" -v`
Expected: FAIL (el anexo no cambia de estado).

- [ ] **Step 3: Extender `_expandir_a_grupos`**

Dentro del bucle `for d in documentos:`, después del bloque que maneja
`es_familia_con_actuaciones`, agregar:

```python
        if family_keys.get(d.source_id) == "superfinanciera" and not es_anexo_title(d.title):
            for anexo in list_anexos_of_document(db, d):
                ids.add(anexo.id)
```

Agregar el import al inicio del módulo si no está:
`from core.naming import es_anexo_title, es_familia_con_actuaciones` (ya
importa `es_familia_con_actuaciones`).

- [ ] **Step 4: Correr y ver pasar**

Run: `pytest tests/test_repository.py -k "arrastra" -v`
Expected: PASS

Run: `pytest tests/test_repository.py tests/test_api_documents.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/db/repository.py tests/test_repository.py
git commit -m "feat(anexos): la decisión de revisión de la circular arrastra a sus anexos"
```

---

## PARTE D — Frontend

### Task 13: Tipo `anexo_count` y chip "N anexos" en la lista

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/pages/DocumentsPage.tsx`
- Test: `frontend/src/pages/DocumentsPage.test.tsx`

**Interfaces:**
- Produces:
  - `Document.anexo_count?: number | null` en `types.ts`.
  - `AnexoBadge({ count }: { count: number })` en `DocumentsPage.tsx`,
    renderizado bajo el título cuando `anexo_count >= 1`.

- [ ] **Step 1: Escribir el test**

```tsx
// en DocumentsPage.test.tsx. El archivo ya tiene: BASE_URL, renderPage(),
// la constante DOCUMENT, y un beforeEach que registra /sources,
// /source-families y /documents/{tipos,secciones,...}. Seguir ese patrón.
it("muestra el chip 'N anexos' para documentos con anexo_count", async () => {
  server.use(
    http.get(`${BASE_URL}/documents`, () =>
      HttpResponse.json({
        items: [{ ...DOCUMENT, id: 1, title: "C_SF_0020_2026", nombre: "C_SF_0020_2026", anexo_count: 2 }],
        total: 1, limit: 50, offset: 0,
      }),
    ),
  );
  renderPage();
  expect(await screen.findByText("2 anexos")).toBeInTheDocument();
});
```

- [ ] **Step 2: Correr y ver fallar**

Run: `cd frontend && npx vitest run src/pages/DocumentsPage.test.tsx -t "N anexos"`
Expected: FAIL (no existe el texto).

- [ ] **Step 3: Implementar**

En `frontend/src/api/types.ts`, junto a `case_document_count`:

```ts
  anexo_count?: number | null;
```

En `frontend/src/pages/DocumentsPage.tsx`, junto a `CaseBadge`:

```tsx
const ANEXO_BADGE_CLASS =
  "inline-block rounded-md border-[1.5px] border-border bg-muted px-2 py-1 text-xs font-semibold text-muted-foreground";

function AnexoBadge({ count }: { count: number }) {
  return <span className={ANEXO_BADGE_CLASS}>{count} {count === 1 ? "anexo" : "anexos"}</span>;
}
```

Y en la celda del título, después del bloque de `CaseBadge`:

```tsx
                  {!!document.anexo_count && document.anexo_count >= 1 && (
                    <div className="mt-1">
                      <button type="button" onClick={() => setAnexosDocument(document)}>
                        <AnexoBadge count={document.anexo_count} />
                      </button>
                    </div>
                  )}
```

Agregar el estado `const [anexosDocument, setAnexosDocument] = useState<Document | null>(null);`
junto a los otros `useState` del componente. (El diálogo se conecta en
Task 14; por ahora `setAnexosDocument` solo guarda el estado.)

- [ ] **Step 4: Correr y ver pasar**

Run: `cd frontend && npx vitest run src/pages/DocumentsPage.test.tsx -t "N anexos"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/pages/DocumentsPage.tsx frontend/src/pages/DocumentsPage.test.tsx
git commit -m "feat(anexos): chip 'N anexos' en la lista de documentos"
```

---

### Task 14: `AnexosDialog` — ver y descargar los anexos

**Files:**
- Create: `frontend/src/components/AnexosDialog.tsx`
- Create: `frontend/src/components/AnexosDialog.test.tsx`
- Modify: `frontend/src/pages/DocumentsPage.tsx`
- Modify: `frontend/src/api/*` (cliente HTTP — agregar `fetchDocumentAnexos`)

**Interfaces:**
- Consumes: `GET /documents/{id}/anexos` (Task 11).
- Produces:
  - `fetchDocumentAnexos(documentId: number): Promise<Document[]>` en el
    módulo de API (mismo archivo donde viven `fetchDocuments` / los demás
    llamados a `/documents`).
  - `AnexosDialog({ document, onClose }: { document: Document | null; onClose: () => void })`.

- [ ] **Step 1: Escribir el test del diálogo**

```tsx
// frontend/src/components/AnexosDialog.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { AnexosDialog } from "./AnexosDialog";

const BASE_URL = "http://localhost:8000";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

it("lista los anexos del documento con botones de descarga", async () => {
  server.use(
    http.get(`${BASE_URL}/documents/5/anexos`, () =>
      HttpResponse.json([
        { id: 51, title: "C_SF_0020_2026_A01", nombre: "C_SF_0020_2026_A01" },
        { id: 52, title: "C_SF_0020_2026_A02", nombre: "C_SF_0020_2026_A02" },
      ]),
    ),
  );
  wrap(<AnexosDialog document={{ id: 5, title: "C_SF_0020_2026", nombre: "C_SF_0020_2026" } as any} onClose={() => {}} />);

  expect(await screen.findByText("C_SF_0020_2026_A01")).toBeInTheDocument();
  expect(screen.getByText("C_SF_0020_2026_A02")).toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: /descargar/i })).toHaveLength(2);
});

it("no renderiza nada cuando document es null", () => {
  wrap(<AnexosDialog document={null} onClose={() => {}} />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Correr y ver fallar**

Run: `cd frontend && npx vitest run src/components/AnexosDialog.test.tsx`
Expected: FAIL (no existe el componente).

- [ ] **Step 3: Agregar `fetchDocumentAnexos` al cliente de API**

En el archivo donde están los demás llamados a `/documents` (p. ej.
`frontend/src/api/documents.ts`):

```ts
export async function fetchDocumentAnexos(documentId: number): Promise<Document[]> {
  const res = await apiClient.get<Document[]>(`/documents/${documentId}/anexos`);
  return res.data;
}
```

(Usar el mismo `apiClient` / helper `get` que usan las funciones vecinas.)

- [ ] **Step 4: Implementar `AnexosDialog`**

```tsx
// frontend/src/components/AnexosDialog.tsx
import { useQuery } from "@tanstack/react-query";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { fetchDocumentAnexos } from "@/api/documents";
import { downloadDocument } from "@/api/documents"; // el helper que ya usa el resto de la app
import type { Document } from "@/api/types";

export function AnexosDialog({ document, onClose }: { document: Document | null; onClose: () => void }) {
  const anexosQuery = useQuery({
    queryKey: ["document-anexos", document?.id],
    queryFn: () => fetchDocumentAnexos(document!.id),
    enabled: document != null,
  });

  if (document == null) return null;

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Anexos de {document.nombre}</DialogTitle>
        </DialogHeader>
        {anexosQuery.isLoading && <p className="text-sm text-muted-foreground">Cargando…</p>}
        <ul className="flex flex-col gap-2">
          {anexosQuery.data?.map((anexo) => (
            <li key={anexo.id} className="flex items-center justify-between gap-3">
              <span className="font-mono text-sm">{anexo.nombre}</span>
              <Button variant="outline" size="sm" onClick={() => downloadDocument(anexo.id)}>
                Descargar
              </Button>
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
```

(Ajustar los imports de `ui/dialog`, `Button` y `downloadDocument` a las
rutas reales del proyecto — copiar de `DocumentPreviewDialog.tsx`.)

- [ ] **Step 5: Conectar el diálogo en `DocumentsPage.tsx`**

Al final del JSX de la página, junto a los demás diálogos:

```tsx
      <AnexosDialog document={anexosDocument} onClose={() => setAnexosDocument(null)} />
```

Import: `import { AnexosDialog } from "@/components/AnexosDialog";`

- [ ] **Step 6: Correr y ver pasar**

Run: `cd frontend && npx vitest run src/components/AnexosDialog.test.tsx src/pages/DocumentsPage.test.tsx`
Expected: PASS

Run: `cd frontend && npx vitest run`
Expected: PASS (sin regresiones).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/AnexosDialog.tsx frontend/src/components/AnexosDialog.test.tsx frontend/src/pages/DocumentsPage.tsx frontend/src/api
git commit -m "feat(anexos): diálogo para ver y descargar los anexos de una circular"
```

---

## PARTE E — Verificación final

### Task 15: Suite completa + prueba en vivo del scraper

**Files:** ninguno (verificación).

- [ ] **Step 1: Suite backend completa**

Run: `pytest tests/ -q`
Expected: PASS (los conteos de `tests/test_seed.py` ya se ajustaron en
Task 1).

- [ ] **Step 2: Suite frontend completa**

Run: `cd frontend && npx vitest run`
Expected: PASS.

- [ ] **Step 3: Lint**

Run: `ruff check core/ api/ tests/` y `cd frontend && npm run lint`
Expected: sin errores nuevos.

- [ ] **Step 4: Prueba en vivo acotada del scraper**

Con el backend y Celery corriendo (skill `run-iurisync`), sembrar la
fuente y lanzar una corrida de rango corto:

```bash
python -m core.seed
```

Lanzar un run desde la UI o la API solo para la fuente
"Superintendencia Financiera de Colombia" con un rango de ~1 mes reciente
(p. ej. el mes actual). Verificar en la lista de documentos:
- Aparecen `C_SF_####_AAAA` / `CCIR_SF_####_AAAA` / `R_SF_####_AAAA` y
  `CTO_SF_#######_AAAA` con fechas dentro del rango.
- Una circular con anexos muestra el chip "N anexos" y el diálogo lista y
  descarga cada anexo.
- Los archivos de conceptos abren como `.docx` y su vista previa se
  genera (conversión LibreOffice).

Anotar en el reporte cualquier diferencia entre el HTML real y los
fixtures (estructura de la tabla índice, clases del catálogo ABCD,
formato de la línea `Concepto:`), y ajustar los parsers + fixtures si
hiciera falta.

- [ ] **Step 5: Commit final (si hubo ajustes)**

```bash
git add -A
git commit -m "fix(superfinanciera): ajustes tras prueba en vivo"
```

---

## Self-Review

**Cobertura del spec:**

| Sección del spec | Task |
|---|---|
| Familia `superfinanciera` como paquete + registro + seed (una fuente) | 1 |
| `normativa`: índice → 3 columnas × años | 2 |
| `normativa`: tabla por año (Número/Fecha/Descripción/anexos) | 3 |
| `normativa`: fecha "Mes DD" + año, título `{sigla}_SF_{n:04d}_{año}`, filtro por rango | 4 |
| `normativa`: anexos `_A01` como documentos hermanos; sin anexos si el padre es unverified | 4 |
| `normativa`: recorrer años en rango × 3 tipos; error por año/tipo no aborta | 5 |
| `conceptos`: parseo de `<table class="registro">` (Concepto/Título/Resumen/Archivo) | 6 |
| `conceptos`: `total registros`, fallback sin línea `Concepto:` | 6, 7 |
| `conceptos`: título del radicado (año/número); regla del consecutivo (≠1 → `_NN`) | 7 |
| `conceptos`: fecha en español, filtro por rango, omitir sin fecha/sin archivo | 7 |
| `conceptos`: recorrer TODAS las páginas vía `continuar`; reintento por página | 8 |
| Helpers `es_anexo_title` / `titulo_padre_de_anexo` | 9 |
| Colapso de anexos en `list_documents` (solo `superfinanciera`, con padre presente, respeta `collapse_case_families`) | 10 |
| `anexo_counts_by_document` | 10 |
| `anexo_count` en `DocumentOut` + poblado en el listado | 11 |
| `GET /documents/{id}/anexos` + `list_anexos_of_document` | 11 |
| `_expandir_a_grupos` arrastra anexos del documento madre (descarga masiva / revisión) | 12 |
| Sin migración de esquema | — (ninguna task crea migración) |
| Frontend: chip "N anexos" | 13 |
| Frontend: ver/descargar cada anexo | 14 |
| `review_status = "pending"` (sin `auto_review_status`) | 1 (seed con `family_params={}`) |
| Pruebas con fixtures HTML reales recortados | 2–8, y ajuste en 15 |

Sin lagunas: cada requisito del spec tiene su task. La herencia de
`review_status` entre madre y anexos queda explícitamente fuera de v1
(spec) y por lo tanto no tiene task.

**Placeholders:** ninguno — cada step de código trae el código real.

**Consistencia de tipos:**
- `_FilaNormativa` gana el campo `numero_link` en Task 4; el test de
  Task 3 se actualiza en ese mismo task (nota explícita en Step 1).
- `scrap_normativa` / `scrap_conceptos` mantienen la firma
  `(fini, ffin, source, limit=…, stop_event=None, on_progress=None)` de
  Task 1 a Task 8.
- `anexo_counts_by_document` devuelve `{document_id: int}` en Task 10 y se
  consume igual en Task 11.
- `list_anexos_of_document(db, document)` definida en Task 11, reusada en
  Task 12.
- `es_anexo_title` / `titulo_padre_de_anexo` definidas en Task 9, usadas
  en 10 y 12.
- Frontend: `anexo_count` agregado en Task 13 y consumido por
  `AnexosDialog` (vía `Document`) en Task 14; `setAnexosDocument` creado
  en Task 13, conectado al diálogo en Task 14.
