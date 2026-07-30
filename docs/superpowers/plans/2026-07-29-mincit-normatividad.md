# Fuente MinCIT (familia `mincit`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar una familia técnica nueva (`mincit`) que scrapea Resoluciones, Decretos, Circulares y Leyes de `https://www.mincit.gov.co/normatividad`, y registrar su fuente en el catálogo.

**Architecture:** Un scraper `requests` + `BeautifulSoup` (mismo estilo que `core/scrapers/families/anh.py`): por cada categoría se lee el índice para descubrir qué páginas de archivo (por año o rango de años) existen, se piden solo las que caen en `[fini, ffin]`, y se parsea la tabla `#Listado` de cada una a `RawDocModel`.

**Tech Stack:** Python, `requests`, `beautifulsoup4`, `pydantic` (`RawDocModel`), `pytest` + `responses` para las pruebas.

## Global Constraints

- Fecha de filtro (`fini`/`ffin`) contra **Fecha de publicación** (`f_public`), no Fecha de expedición — la clase debe fijar `filters_by_publication_date = True` en `BaseScrapper`.
- `f_providencia` = Fecha de expedición.
- Título: `f"{LETRA}_MCIT_{numero:04d}_{año}"` con `LETRA` = R/L/D/C según Resolución/Ley/Decreto/Circular; `año` es el año de `f_providencia`.
- Si no se puede extraer el número del texto de la celda, usar el texto crudo como título y marcar `title_unverified=True`.
- Alcance v1: solo `resoluciones`, `decretos`, `circulares`, `leyes`. No tocar Jurisprudencia/Proyectos/Agenda Regulatoria/DUR/Emplazamientos/Normograma.
- Un año/slug que falle no debe descartar los documentos ya recolectados de otras páginas/categorías (log vía `on_progress`, `continue`).

---

## Contexto de referencia (HTML real verificado)

Fila real de `https://www.mincit.gov.co/normatividad/resoluciones/2025`:

```html
<table class="table table-striped table-bordered pt-4" id="Listado">
  <thead>
    <th>No</th>
    <th>Archivo</th>
    <th class="text-center">Tamaño</th>
    <th class="text-center">Fecha de expedición</th>
    <th class="text-center">Fecha de publicación</th>
    <th></th>
  </thead>
  <tbody>
    <tr>
      <td class="text-center">1</td>
      <td>Resolución 365 del 30 de diciembre de 2025, "por la cual se adopta la determinación final dentro de la investigación iniciada mediante Resolución 192 del 3 de julio de 2024".</td>
      <td class="text-center">1,35 MB</td>
      <td class="text-center">30/12/2025</td>
      <td class="text-center">12/02/2026</td>
      <td>
        <a href="/getattachment/0764f7b2-98fe-4007-acf0-65689bd02404/Resolucion-365-del-30-de-diciembre-de-2025.aspx" target="_blank">Descargar</a>
      </td>
    </tr>
  </tbody>
</table>
```

Nota: el `<thead>` no envuelve sus `<th>` en un `<tr>` (HTML real, no es un error de transcripción) — por eso el parseo debe apuntar directo al `<tbody>` en vez de asumir que la primera `<tr>` de la tabla es el encabezado.

Formato de celda "Archivo" verificado en las 4 categorías:
- Resolución/Decreto/Ley: `"{Tipo} {numero} del {fecha}, "{descripción}"."`  (coma + comillas)
- Circular: `"Circular {numero} del {fecha}: {descripción}."`  (dos puntos, sin comillas)

Índice de categoría (`/normatividad/{categoria}`) enlaza a páginas de archivo por año (`/normatividad/leyes/2021`) o por rango (`/normatividad/leyes/1990-1994`, `/normatividad/circulares/1995-1990` — rango invertido, confirmado real) y a veces a slugs no numéricos que deben ignorarse (`/normatividad/circulares/circulares-conjuntas`).

---

### Task 1: Esqueleto de la familia `mincit` y registro

**Files:**
- Create: `core/scrapers/families/mincit.py`
- Modify: `core/scrapers/families/__init__.py`
- Test: `tests/families/test_mincit.py`

**Interfaces:**
- Produces: `core.scrapers.families.mincit.ScrapMINCIT` (subclase de `BaseScrapper`, `source = "Ministerio de Comercio, Industria y Turismo"`, `filters_by_publication_date = True`, registrada como `@register_family("mincit")`). `scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]` existe pero por ahora devuelve `[]`.

- [ ] **Step 1: Escribir el test de registro (debe fallar)**

Crear `tests/families/test_mincit.py` con:

```python
from core.scrapers.registry import FAMILY_REGISTRY


def test_mincit_is_registered_under_its_family_key():
    import core.scrapers.families  # noqa: F401

    assert FAMILY_REGISTRY["mincit"].__name__ == "ScrapMINCIT"


def test_scrap_returns_empty_list_by_default():
    from core.scrapers.families.mincit import ScrapMINCIT

    scraper = ScrapMINCIT()
    assert scraper.scrap(fini="2024-01-01", ffin="2024-12-31") == []
```

- [ ] **Step 2: Correr el test y confirmar que falla**

Run: `pytest tests/families/test_mincit.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'core.scrapers.families.mincit'`

- [ ] **Step 3: Crear el esqueleto de la familia**

Crear `core/scrapers/families/mincit.py`:

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

_BASE_URL = "https://www.mincit.gov.co"

# slug de categoría -> (tipo mostrado, letra del código de título)
_CATEGORIAS = {
    "resoluciones": ("Resolución", "R"),
    "decretos": ("Decreto", "D"),
    "circulares": ("Circular", "C"),
    "leyes": ("Ley", "L"),
}


@register_family("mincit")
class ScrapMINCIT(BaseScrapper):
    filters_by_publication_date = True

    def __init__(self):
        self.source = "Ministerio de Comercio, Industria y Turismo"

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        return []
```

- [ ] **Step 4: Registrar el import en `__init__.py`**

Modificar `core/scrapers/families/__init__.py` (línea 1):

```python
from . import constitucional, samai, corte_suprema, jep, cndj, adr, adres, ane, anh, rama_judicial, mincit  # noqa: F401
```

- [ ] **Step 5: Correr los tests y confirmar que pasan**

Run: `pytest tests/families/test_mincit.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add core/scrapers/families/mincit.py core/scrapers/families/__init__.py tests/families/test_mincit.py
git commit -m "feat: agrega esqueleto de la familia mincit"
```

---

### Task 2: Helpers de parseo de texto (fecha, número, detalle, título)

**Files:**
- Modify: `core/scrapers/families/mincit.py`
- Test: `tests/families/test_mincit.py`

**Interfaces:**
- Consumes: nada nuevo (funciones puras a nivel de módulo).
- Produces:
  - `_parse_fecha(texto: str) -> Optional[str]` — `"30/12/2025"` → `"2025-12-30"`; `None` si no hay match.
  - `_parse_numero(texto_archivo: str) -> Optional[str]` — dígitos crudos (con o sin ceros a la izquierda) del inicio de la celda; `None` si no hay match.
  - `_parse_detalle(texto_archivo: str) -> Optional[str]` — texto descriptivo después de la fecha, sin comillas envolventes ni punto final; `None` si no hay separador `,`/`:`.
  - `_normalize_title(letra: str, numero: str, anio: str) -> str` — `f"{letra}_MCIT_{int(numero):04d}_{anio}"`.

- [ ] **Step 1: Escribir los tests de los helpers (deben fallar)**

Agregar a `tests/families/test_mincit.py`:

```python
from core.scrapers.families.mincit import (
    _normalize_title,
    _parse_detalle,
    _parse_fecha,
    _parse_numero,
)


def test_parse_fecha_converts_ddmmyyyy_to_isoformat():
    assert _parse_fecha("30/12/2025") == "2025-12-30"


def test_parse_fecha_returns_none_when_no_date_found():
    assert _parse_fecha("sin fecha") is None


def test_parse_numero_extracts_leading_number_after_tipo():
    texto = 'Resolución 365 del 30 de diciembre de 2025, "por la cual se adopta..."'
    assert _parse_numero(texto) == "365"


def test_parse_numero_extracts_number_with_leading_zero():
    texto = "Circular 018 del 27 de diciembre de 2024: distribución y administración..."
    assert _parse_numero(texto) == "018"


def test_parse_numero_returns_none_when_no_leading_number():
    assert _parse_numero("Documento sin número al inicio") is None


def test_parse_detalle_extracts_quoted_text_after_comma():
    texto = (
        'Resolución 365 del 30 de diciembre de 2025, '
        '"por la cual se adopta la determinación final".'
    )
    assert _parse_detalle(texto) == "por la cual se adopta la determinación final"


def test_parse_detalle_extracts_text_after_colon_without_quotes():
    texto = (
        "Circular 018 del 27 de diciembre de 2024: distribución y administración "
        "del contingente de exportación de azúcar."
    )
    assert _parse_detalle(texto) == (
        "distribución y administración del contingente de exportación de azúcar"
    )


def test_parse_detalle_returns_none_without_separator():
    assert _parse_detalle("Texto sin separador de descripción") is None


def test_normalize_title_builds_canonical_code():
    assert _normalize_title("R", "365", "2025") == "R_MCIT_0365_2025"


def test_normalize_title_pads_short_numbers_to_four_digits():
    assert _normalize_title("C", "18", "2024") == "C_MCIT_0018_2024"


def test_normalize_title_uses_letter_per_tipo():
    assert _normalize_title("L", "2094", "2021") == "L_MCIT_2094_2021"
    assert _normalize_title("D", "1438", "2025") == "D_MCIT_1438_2025"
```

- [ ] **Step 2: Correr los tests y confirmar que fallan**

Run: `pytest tests/families/test_mincit.py -v`
Expected: FAIL con `ImportError: cannot import name '_normalize_title'` (y los demás helpers)

- [ ] **Step 3: Implementar los helpers**

Agregar a `core/scrapers/families/mincit.py`, después de `_CATEGORIAS`:

```python
_FECHA_PATTERN = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_NUMERO_PATTERN = re.compile(r"^\S+\s+(\d+)")
# Todo lo anterior al primer "," o ":" es "{tipo} {numero} del {fecha}"; lo que
# sigue es la descripción, con comillas opcionales alrededor (Resoluciones/
# Decretos/Leyes usan coma+comillas, Circulares usa dos puntos sin comillas) y
# un punto final opcional que se descarta junto con la comilla de cierre.
_DETALLE_PATTERN = re.compile(r'^[^,:]+[,:]\s*"?(.*?)"?\.?$', re.DOTALL)


def _parse_fecha(texto: str) -> Optional[str]:
    m = _FECHA_PATTERN.search(texto)
    if not m:
        return None
    dia, mes, anio = m.groups()
    return f"{anio}-{mes.zfill(2)}-{dia.zfill(2)}"


def _parse_numero(texto_archivo: str) -> Optional[str]:
    m = _NUMERO_PATTERN.match(texto_archivo.strip())
    return m.group(1) if m else None


def _parse_detalle(texto_archivo: str) -> Optional[str]:
    m = _DETALLE_PATTERN.match(texto_archivo.strip())
    if not m:
        return None
    detalle = m.group(1).strip()
    return detalle or None


def _normalize_title(letra: str, numero: str, anio: str) -> str:
    return f"{letra}_MCIT_{int(numero):04d}_{anio}"
```

- [ ] **Step 4: Correr los tests y confirmar que pasan**

Run: `pytest tests/families/test_mincit.py -v`
Expected: PASS (todos los tests, incluidos los del Task 1)

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/mincit.py tests/families/test_mincit.py
git commit -m "feat: agrega helpers de parseo de fecha/numero/detalle/titulo para mincit"
```

---

### Task 3: Descubrimiento de años/slugs desde el índice de categoría

**Files:**
- Modify: `core/scrapers/families/mincit.py`
- Test: `tests/families/test_mincit.py`

**Interfaces:**
- Consumes: nada de tasks anteriores.
- Produces:
  - `_anios_del_slug(slug: str) -> List[int]` — años cubiertos por un slug de archivo (`"2021"` → `[2021]`; `"1990-1994"` → `[1990, 1991, 1992, 1993, 1994]`; rango invertido `"1995-1990"` → `[1990, ..., 1995]`; slug no numérico → `[]`).
  - `_mapa_anio_a_slug(html: str, categoria: str) -> dict[int, str]` — mapa año→slug construido a partir del HTML del índice de una categoría.

- [ ] **Step 1: Escribir los tests (deben fallar)**

Agregar a `tests/families/test_mincit.py`:

```python
from core.scrapers.families.mincit import _anios_del_slug, _mapa_anio_a_slug

_INDICE_HTML = """
<a href="/normatividad/leyes" class="active">Leyes</a>
<a href="/normatividad/leyes/2021">2021</a>
<a href="/normatividad/leyes/1990-1994">1990-1994</a>
<a href="/normatividad/leyes/1979-1989">1979-1989</a>
"""


def test_anios_del_slug_handles_single_year():
    assert _anios_del_slug("2021") == [2021]


def test_anios_del_slug_handles_range():
    assert _anios_del_slug("1990-1994") == [1990, 1991, 1992, 1993, 1994]


def test_anios_del_slug_handles_reversed_range():
    assert _anios_del_slug("1995-1990") == [1990, 1991, 1992, 1993, 1994, 1995]


def test_anios_del_slug_returns_empty_for_non_year_slug():
    assert _anios_del_slug("circulares-conjuntas") == []


def test_mapa_anio_a_slug_maps_each_year_including_ranges():
    mapa = _mapa_anio_a_slug(_INDICE_HTML, "leyes")

    assert mapa[2021] == "2021"
    assert mapa[1990] == "1990-1994"
    assert mapa[1994] == "1990-1994"
    assert mapa[1985] == "1979-1989"


def test_mapa_anio_a_slug_ignores_other_categories():
    html = '<a href="/normatividad/decretos/2021">2021</a>'
    assert _mapa_anio_a_slug(html, "leyes") == {}
```

- [ ] **Step 2: Correr los tests y confirmar que fallan**

Run: `pytest tests/families/test_mincit.py -v`
Expected: FAIL con `ImportError: cannot import name '_anios_del_slug'`

- [ ] **Step 3: Implementar el descubrimiento de años**

Agregar a `core/scrapers/families/mincit.py`, después de los helpers del Task 2:

```python
_SLUG_ANIO_PATTERN = re.compile(r"^(\d{4})(?:-(\d{4}))?$")


def _anios_del_slug(slug: str) -> List[int]:
    m = _SLUG_ANIO_PATTERN.match(slug)
    if not m:
        return []
    inicio = int(m.group(1))
    fin = int(m.group(2)) if m.group(2) else inicio
    if fin < inicio:
        inicio, fin = fin, inicio
    return list(range(inicio, fin + 1))


def _mapa_anio_a_slug(html: str, categoria: str) -> dict:
    patron = re.compile(rf'href="/normatividad/{re.escape(categoria)}/([^"]+)"')
    mapa = {}
    for slug in set(patron.findall(html)):
        for anio in _anios_del_slug(slug):
            mapa[anio] = slug
    return mapa
```

- [ ] **Step 4: Correr los tests y confirmar que pasan**

Run: `pytest tests/families/test_mincit.py -v`
Expected: PASS (todos los tests)

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/mincit.py tests/families/test_mincit.py
git commit -m "feat: agrega descubrimiento de anios/slugs del indice de categoria en mincit"
```

---

### Task 4: Parseo de una página de archivo (tabla) a `RawDocModel`

**Files:**
- Modify: `core/scrapers/families/mincit.py`
- Test: `tests/families/test_mincit.py`

**Interfaces:**
- Consumes: `_parse_fecha`, `_parse_numero`, `_parse_detalle`, `_normalize_title` (Task 2); `RawDocModel`, `storage_path` (ya importados).
- Produces: `ScrapMINCIT._extraer_filas(self, html: str, tipo: str, letra: str, fini: str, ffin: str) -> List[RawDocModel]`.

- [ ] **Step 1: Escribir los tests (deben fallar)**

Agregar a `tests/families/test_mincit.py`:

```python
from core.scrapers.families.mincit import ScrapMINCIT

_FILA_HTML = """
<table id="Listado">
  <thead>
    <th>No</th>
    <th>Archivo</th>
    <th class="text-center">Tamaño</th>
    <th class="text-center">Fecha de expedición</th>
    <th class="text-center">Fecha de publicación</th>
    <th></th>
  </thead>
  <tbody>
    <tr>
      <td class="text-center">1</td>
      <td>Resolución 365 del 30 de diciembre de 2025, "por la cual se adopta la determinación final".</td>
      <td class="text-center">1,35 MB</td>
      <td class="text-center">30/12/2025</td>
      <td class="text-center">12/02/2026</td>
      <td><a href="/getattachment/0764f7b2-98fe-4007-acf0-65689bd02404/Resolucion-365.aspx" target="_blank">Descargar</a></td>
    </tr>
  </tbody>
</table>
"""


def test_extraer_filas_parses_row_and_builds_canonical_title():
    scraper = ScrapMINCIT()
    docs = scraper._extraer_filas(_FILA_HTML, "Resolución", "R", "2026-01-01", "2026-12-31")

    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "R_MCIT_0365_2025"
    assert doc.title_unverified is False
    assert doc.tipo == "Resolución"
    assert doc.f_public == "2026-02-12"  # Fecha de publicación
    assert doc.f_providencia == "2025-12-30"  # Fecha de expedición
    assert doc.detalle == "por la cual se adopta la determinación final"
    assert doc.link["url"] == "https://www.mincit.gov.co/getattachment/0764f7b2-98fe-4007-acf0-65689bd02404/Resolucion-365.aspx"
    assert doc.save_path == "Ministerio de Comercio, Industria y Turismo/2026-02-12/Resolución/R_MCIT_0365_2025(extension)"


def test_extraer_filas_filters_by_publication_date_not_expedicion():
    scraper = ScrapMINCIT()
    # Fecha de expedición (30/12/2025) cae en 2025, pero Fecha de publicación
    # (12/02/2026) es la que se debe usar para el filtro — el rango pedido es
    # solo 2025, así que este documento debe quedar excluido.
    docs = scraper._extraer_filas(_FILA_HTML, "Resolución", "R", "2025-01-01", "2025-12-31")

    assert docs == []


def test_extraer_filas_marks_title_unverified_when_no_numero():
    html = _FILA_HTML.replace(
        'Resolución 365 del 30 de diciembre de 2025, "por la cual se adopta la determinación final".',
        'Documento sin número reconocible en el texto.',
    )
    scraper = ScrapMINCIT()
    docs = scraper._extraer_filas(html, "Resolución", "R", "2026-01-01", "2026-12-31")

    assert len(docs) == 1
    assert docs[0].title == "Documento sin número reconocible en el texto."
    assert docs[0].title_unverified is True


def test_extraer_filas_skips_row_without_download_link():
    html = _FILA_HTML.replace(
        '<a href="/getattachment/0764f7b2-98fe-4007-acf0-65689bd02404/Resolucion-365.aspx" target="_blank">Descargar</a>',
        '',
    )
    scraper = ScrapMINCIT()
    docs = scraper._extraer_filas(html, "Resolución", "R", "2026-01-01", "2026-12-31")

    assert docs == []
```

- [ ] **Step 2: Correr los tests y confirmar que fallan**

Run: `pytest tests/families/test_mincit.py -v`
Expected: FAIL con `AttributeError: 'ScrapMINCIT' object has no attribute '_extraer_filas'`

- [ ] **Step 3: Implementar `_extraer_filas`**

Agregar el método dentro de `class ScrapMINCIT` en `core/scrapers/families/mincit.py` (después de `__init__`, antes de `scrap`):

```python
    def _extraer_filas(self, html: str, tipo: str, letra: str, fini: str, ffin: str) -> List[RawDocModel]:
        docs: List[RawDocModel] = []
        soup = BeautifulSoup(html, "html.parser")
        tabla = soup.find("table", id="Listado")
        if tabla is None:
            return docs
        tbody = tabla.find("tbody")
        if tbody is None:
            return docs

        for fila in tbody.find_all("tr"):
            celdas = fila.find_all("td")
            if len(celdas) < 6:
                continue

            texto_archivo = celdas[1].get_text(" ", strip=True)
            f_providencia = _parse_fecha(celdas[3].get_text(strip=True))
            f_public = _parse_fecha(celdas[4].get_text(strip=True))
            if not f_providencia or not f_public:
                continue
            if f_public < fini or f_public > ffin:
                continue

            enlace = celdas[5].find("a", href=True)
            if not enlace:
                continue
            url = urljoin(_BASE_URL, enlace["href"])

            numero = _parse_numero(texto_archivo)
            detalle = _parse_detalle(texto_archivo)
            anio_providencia = f_providencia[:4]

            if numero is not None:
                title = _normalize_title(letra, numero, anio_providencia)
                title_unverified = False
            else:
                title = texto_archivo
                title_unverified = True

            docs.append(RawDocModel(
                source=self.source,
                link={"url": url, "method": "GET"},
                title=title,
                tipo=tipo,
                f_public=f_public,
                f_providencia=f_providencia,
                detalle=detalle,
                save_path=storage_path(self.source, f_public, tipo, f"{title}(extension)"),
                title_unverified=title_unverified,
            ))

        return docs
```

- [ ] **Step 4: Correr los tests y confirmar que pasan**

Run: `pytest tests/families/test_mincit.py -v`
Expected: PASS (todos los tests)

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/mincit.py tests/families/test_mincit.py
git commit -m "feat: agrega parseo de tabla Listado a RawDocModel en mincit"
```

---

### Task 5: Orquestación completa (`scrap()`)

**Files:**
- Modify: `core/scrapers/families/mincit.py`
- Test: `tests/families/test_mincit.py`

**Interfaces:**
- Consumes: `_mapa_anio_a_slug` (Task 3), `ScrapMINCIT._extraer_filas` (Task 4), `_CATEGORIAS` (Task 1).
- Produces: `ScrapMINCIT.scrap(...)` completo — reemplaza el `return []` del Task 1.

- [ ] **Step 1: Quitar el test placeholder del Task 1**

El test `test_scrap_returns_empty_list_by_default` (agregado en el Task 1) llama
a `scraper.scrap(...)` sin mockear HTTP — una vez que este task implemente el
`scrap()` real, esa llamada intentaría una petición de red de verdad contra
mincit.gov.co en cada corrida de la suite. Eliminar esa función de
`tests/families/test_mincit.py` por completo (queda reemplazada por los tests
con `@responses.activate` de este mismo task, que sí cubren el caso de
respuesta vacía vía `_INDICE_VACIO_HTML`).

- [ ] **Step 2: Escribir los tests nuevos (deben fallar)**

Agregar a `tests/families/test_mincit.py`:

```python
import responses

_INDICE_RESOLUCIONES_HTML = """
<a href="/normatividad/resoluciones" class="active">Resoluciones</a>
<a href="/normatividad/resoluciones/2026">2026</a>
"""

_INDICE_DECRETOS_HTML = """
<a href="/normatividad/decretos" class="active">Decretos</a>
<a href="/normatividad/decretos/2026">2026</a>
"""

_INDICE_VACIO_HTML = '<a href="/normatividad/circulares" class="active">Circulares</a>'

_PAGINA_RESOLUCION_HTML = """
<table id="Listado">
  <thead><th>No</th><th>Archivo</th><th>Tamaño</th><th>Fecha de expedición</th><th>Fecha de publicación</th><th></th></thead>
  <tbody>
    <tr>
      <td>1</td>
      <td>Resolución 010 del 5 de enero de 2026, "por la cual se dictan disposiciones".</td>
      <td>1 MB</td><td>05/01/2026</td><td>06/01/2026</td>
      <td><a href="/getattachment/aaa/Resolucion-010.aspx">Descargar</a></td>
    </tr>
  </tbody>
</table>
"""

_PAGINA_DECRETO_HTML = """
<table id="Listado">
  <thead><th>No</th><th>Archivo</th><th>Tamaño</th><th>Fecha de expedición</th><th>Fecha de publicación</th><th></th></thead>
  <tbody>
    <tr>
      <td>1</td>
      <td>Decreto 020 del 10 de enero de 2026, "por el cual se reglamenta algo".</td>
      <td>1 MB</td><td>10/01/2026</td><td>11/01/2026</td>
      <td><a href="/getattachment/bbb/Decreto-020.aspx">Descargar</a></td>
    </tr>
  </tbody>
</table>
"""


@responses.activate
def test_scrap_aggregates_across_categories_using_year_index():
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/resoluciones", body=_INDICE_RESOLUCIONES_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/resoluciones/2026", body=_PAGINA_RESOLUCION_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/decretos", body=_INDICE_DECRETOS_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/decretos/2026", body=_PAGINA_DECRETO_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/circulares", body=_INDICE_VACIO_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/leyes", body=_INDICE_VACIO_HTML)

    scraper = ScrapMINCIT()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert {d.title for d in docs} == {"R_MCIT_0010_2026", "D_MCIT_0020_2026"}


@responses.activate
def test_scrap_does_not_request_years_outside_range():
    indice_con_dos_anios = """
    <a href="/normatividad/resoluciones/2020">2020</a>
    <a href="/normatividad/resoluciones/2026">2026</a>
    """
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/resoluciones", body=indice_con_dos_anios)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/resoluciones/2026", body=_PAGINA_RESOLUCION_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/decretos", body=_INDICE_VACIO_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/circulares", body=_INDICE_VACIO_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/leyes", body=_INDICE_VACIO_HTML)

    scraper = ScrapMINCIT()
    docs = scraper.scrap(fini="2026-01-01", ffin="2026-12-31")

    assert len(docs) == 1
    urls_pedidas = {c.request.url for c in responses.calls}
    assert "https://www.mincit.gov.co/normatividad/resoluciones/2020" not in urls_pedidas


@responses.activate
def test_scrap_continues_past_a_failing_year_page():
    indice_con_dos_anios = """
    <a href="/normatividad/resoluciones/2025">2025</a>
    <a href="/normatividad/resoluciones/2026">2026</a>
    """
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/resoluciones", body=indice_con_dos_anios)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/resoluciones/2025", status=500)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/resoluciones/2026", body=_PAGINA_RESOLUCION_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/decretos", body=_INDICE_VACIO_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/circulares", body=_INDICE_VACIO_HTML)
    responses.add(responses.GET, "https://www.mincit.gov.co/normatividad/leyes", body=_INDICE_VACIO_HTML)

    progreso = []
    scraper = ScrapMINCIT()
    docs = scraper.scrap(fini="2025-01-01", ffin="2026-12-31", on_progress=progreso.append)

    assert len(docs) == 1
    assert docs[0].title == "R_MCIT_0010_2026"
    assert any("Error" in m and "resoluciones/2025" in m for m in progreso)
```

- [ ] **Step 3: Correr los tests y confirmar que fallan**

Run: `pytest tests/families/test_mincit.py -v`
Expected: FAIL — `test_scrap_aggregates_across_categories_using_year_index` y las otras dos nuevas fallan porque `scrap()` todavía devuelve `[]`.

- [ ] **Step 4: Implementar `scrap()`**

Reemplazar el `scrap` del Task 1 en `core/scrapers/families/mincit.py`:

```python
    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        docs: List[RawDocModel] = []
        anio_inicial = int(fini[:4])
        anio_final = int(ffin[:4])

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
                    on_progress(f"[{self.source}] Error consultando índice de {tipo}: {e}")
                continue

            mapa = _mapa_anio_a_slug(resp.text, categoria)
            slugs = sorted({mapa[a] for a in range(anio_inicial, anio_final + 1) if a in mapa})

            for slug in slugs:
                if stop_event is not None and stop_event.is_set():
                    return docs

                try:
                    resp = session.get(f"{_BASE_URL}/normatividad/{categoria}/{slug}", timeout=30)
                    resp.raise_for_status()
                except Exception as e:
                    if on_progress:
                        on_progress(f"[{self.source}] Error consultando {categoria}/{slug}: {e}")
                    continue

                docs.extend(self._extraer_filas(resp.text, tipo, letra, fini, ffin))
                if len(docs) >= limit:
                    return docs[:limit]

        return docs
```

- [ ] **Step 5: Correr todos los tests del archivo y confirmar que pasan**

Run: `pytest tests/families/test_mincit.py -v`
Expected: PASS (todos los tests del archivo, de los 5 tasks)

- [ ] **Step 6: Commit**

```bash
git add core/scrapers/families/mincit.py tests/families/test_mincit.py
git commit -m "feat: implementa scrap() completo para la familia mincit"
```

---

### Task 6: Integración en el catálogo (seed) y documentación

**Files:**
- Modify: `core/seed.py`
- Modify: `tests/test_seed.py`
- Modify: `README.md:58`

**Interfaces:**
- Consumes: `core.scrapers.families.mincit` (Task 1, ya importado por `core/scrapers/families/__init__.py` — no hace falta importarlo de nuevo en `seed.py`, `create_source_if_missing` solo necesita la clave `"mincit"`, no la clase).
- Produces: fuente `"Ministerio de Comercio, Industria y Turismo"` con `family_key="mincit"` disponible en el catálogo tras correr `python -m core.seed`.

**Nota:** este task requiere Postgres corriendo (`docker compose up -d`, con la base `iurisync_test` creada — ver README.md, sección "Setup local", pasos 3-4) porque `tests/test_seed.py` usa la fixture `db_session` contra una base real.

- [ ] **Step 1: Actualizar el test de seed (debe fallar)**

En `tests/test_seed.py`, editar `test_seed_populates_families_and_sources_and_is_idempotent` (líneas 53-66):

```python
def test_seed_populates_families_and_sources_and_is_idempotent(db_session):
    seed_source_families_and_sources(db_session)
    seed_source_families_and_sources(db_session)  # running twice must not duplicate rows

    families = repository.list_source_families(db_session)
    assert {f.key for f in families} == {
        "constitucional", "samai", "corte_suprema", "jep", "cndj",
        "adr", "adres", "ane", "anh", "rama_judicial", "mincit",
    }

    sources = repository.list_sources(db_session)
    # 1 (Corte Constitucional) + 28 (SAMAI) + 8 (fuente única: corte_suprema, jep, cndj,
    # adr, adres, ane, anh, mincit) + 33 (Tribunales Superiores, incl. Bogotá D.C.) + 6 (tipos de Juzgado) = 76
    assert len(sources) == 1 + 28 + 8 + 33 + 6

    rama_judicial_sources = repository.list_sources(db_session, family_key="rama_judicial")
    assert len(rama_judicial_sources) == 39
    assert any(s.family_params.get("dept_code") == "05" for s in rama_judicial_sources)
    assert any(
        s.family_params.get("entidad_id") == "31" and s.family_params.get("dept_code") == ""
        for s in rama_judicial_sources
    )
```

Y en `test_seed_running_concurrently_does_not_crash_or_duplicate_rows` (líneas 44-48):

```python
        families = repository.list_source_families(assertion_session)
        assert len(families) == 11

        sources = repository.list_sources(assertion_session, limit=500)
        assert len(sources) == 1 + 28 + 8 + 33 + 6
```

- [ ] **Step 2: Correr los tests y confirmar que fallan**

Requiere Postgres arriba: `docker compose up -d` (si no está corriendo ya).

Run: `pytest tests/test_seed.py -v`
Expected: FAIL — el set de claves no incluye `"mincit"` y los conteos (`10`/`75`) no coinciden con lo que el test ahora espera (`11`/`76`), porque `core/seed.py` todavía no siembra la familia `mincit`.

- [ ] **Step 3: Agregar la familia y la fuente al seed**

En `core/seed.py`, agregar `"mincit"` a `_FAMILIES` (después de `"rama_judicial"`, línea 28-29):

```python
    "rama_judicial": (
        "Rama Judicial (Tribunales Superiores y Juzgados)",
        "Publicaciones procesales de la Rama Judicial; cubre Tribunales Superiores por departamento y Juzgados por tipo",
    ),
    "mincit": (
        "Ministerio de Comercio, Industria y Turismo",
        "Normativa (resoluciones, decretos, circulares, leyes) publicada por el Ministerio de Comercio, Industria y Turismo",
    ),
}
```

Y agregar la creación de la fuente al final de `seed_source_families_and_sources` (después del bloque `for juz_id, juz_name in JUZGADOS_ENTIDADES.items(): ...`, antes de que termine la función):

```python
    repository.create_source_if_missing(
        db, family_key="mincit", name="Ministerio de Comercio, Industria y Turismo", family_params={}
    )
```

- [ ] **Step 4: Correr los tests y confirmar que pasan**

Run: `pytest tests/test_seed.py -v`
Expected: PASS (ambos tests)

- [ ] **Step 5: Correr toda la suite de tests de la familia y del seed juntos**

Run: `pytest tests/families/test_mincit.py tests/test_seed.py -v`
Expected: PASS (todos)

- [ ] **Step 6: Actualizar el conteo de familias en README.md**

En `README.md:58`, cambiar:

```
Este repo porta las 10 familias de scraping de `WebScrapping_Fuentes` (`constitucional`, `samai`, `corte_suprema`, `jep`, `cndj`, `adr`, `adres`, `ane`, `anh`, `rama_judicial`), cada una siguiendo el patrón `core/scrapers/families/` + `@register_family(...)`.
```

por:

```
Este repo porta las 10 familias de scraping de `WebScrapping_Fuentes` (`constitucional`, `samai`, `corte_suprema`, `jep`, `cndj`, `adr`, `adres`, `ane`, `anh`, `rama_judicial`) más `mincit` (desarrollada directamente en este repo, normativa del Ministerio de Comercio, Industria y Turismo), cada una siguiendo el patrón `core/scrapers/families/` + `@register_family(...)`.
```

- [ ] **Step 7: Commit**

```bash
git add core/seed.py tests/test_seed.py README.md
git commit -m "feat: agrega la fuente MinCIT al catalogo (seed) y actualiza el conteo de familias"
```

---

## Verificación final

- [ ] **Correr toda la suite de tests del proyecto**

Run: `pytest -v` (requiere `docker compose up -d` para las pruebas de integración con Postgres/MinIO, según README.md)
Expected: PASS, sin regresiones en otros archivos de test.

- [ ] **Probar el scraper contra el sitio real (smoke test manual, no automatizado)**

```bash
python -c "
from core.scrapers.families.mincit import ScrapMINCIT
s = ScrapMINCIT()
docs = s.scrap(fini='2026-01-01', ffin='2026-07-29', limit=20)
for d in docs[:5]:
    print(d.title, '|', d.tipo, '|', d.f_public, '|', d.link['url'])
print(f'Total: {len(docs)}')
"
```

Confirmar que trae documentos reales de las 4 categorías con títulos en formato `X_MCIT_NNNN_AAAA` y sin excepciones no capturadas.
