# Fuente SIC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nueva familia de scraper `sic` que descarga Resoluciones, Circulares, Títulos de la Circular Única y Doctrina (conceptos/relatorías) propias de la Superintendencia de Industria y Comercio desde su buscador de normas en Drupal.

**Architecture:** Un solo módulo `core/scrapers/families/sic.py` con cuatro capas: (1) parseo de HTML (fila de listado, nº de páginas, ficha), (2) clasificación + nomenclatura, (3) enumeración completa de una tajada (clasificación × año de publicación) que combina recorrido de páginas + búsqueda adaptativa por fragmentos de dígitos y verifica contra el total exacto, (4) la clase `ScrapSIC.scrap()` que abre cada ficha, filtra y emite `RawDocModel`. Registro en `core/seed.py`.

**Tech Stack:** Python 3.14, requests, BeautifulSoup (bs4), pytest + `responses`.

**Spec:** `docs/superpowers/specs/2026-10-07-fuente-sic-design.md`

## Global Constraints

- Family key `sic`; nombre de fuente `Superintendencia de Industria y Comercio`; sigla en títulos `SIC`.
- Listado: `https://sedeelectronica.sic.gov.co/transparencia/normativa/busqueda-de-normas/entidad`, 20 filas por página, `page` 0-based.
- Clasificaciones (`field_clasificacion2_target_id`): `177` Resoluciones, `179` Circulares, `178` Títulos Circular Única, `180` Doctrina. Año de publicación: `field_fecha_publicacion_value=<AAAA>`. Texto: `combine`.
- TLS válido: **NO** usar `verify=False`.
- Piso: fecha de expedición ≥ `2015-01-01`.
- `f_public` = Fecha publicación; `f_providencia` = Fecha Expedición; `filters_by_publication_date = True`.
- Títulos: `R_SIC_{n:04d}_{año}`, `C_SIC_{n:04d}_{año}` (todas las circulares), `TCU_SIC_{romano}_{AAAAMMDD}`, `CTO_SIC_{AA-NNNNNN}`, `REL_SIC_{n:04d}_{año}`; `año` = año de expedición; anexos `_A01`, `_A02`…; sin número → título crudo `[:120].strip(" .")` + `title_unverified=True`.
- Sólo PDFs de `field--name-field-archivo` (nunca el enlace global "Términos y condiciones").
- Mensajes `on_progress` con prefijo `[Superintendencia de Industria y Comercio]`, en español.
- Sin migración de base de datos.

## Review Focus

1. **Corrida diaria sin documentos nuevos en Doctrina/Títulos CU** — son clasificaciones que casi no se actualizan; una tajada vacía es normal y NO debe emitir aviso de "cambió el marcado" (sólo si TODAS las clasificaciones vienen vacías). Test en Task 4.
2. **Resolución SIC con "del Ministerio" dentro de su epígrafe** ("Resolución No. X "Por la cual se … del Ministerio de Comercio"") — no debe descartarse como "otra entidad": el filtro mira sólo la cabeza del título antes de comillas/coma/" por ". Test en Task 2.
3. **Misma resolución listada en Resoluciones y en Doctrina** (mismo PDF) — una sola descarga, sin colisión. Test en Task 4.
4. **Ficha que falla (timeout/500) en medio de la corrida** — se avisa y se sigue con las demás; no aborta la clasificación. Test en Task 4.
5. **Presupuesto de búsquedas agotado** — se avisa con "Error" y se procesan igual las fichas ya enumeradas. Test en Task 3.

---

### Task 1: Parseo de listado y ficha

**Files:**
- Create: `core/scrapers/families/sic.py`
- Test: `tests/families/test_sic.py`

**Interfaces:**
- Produces:
  - `_BASE: str`, `_LISTADO: str`, `_SOURCE: str`, `_UA: str`, `_POR_PAGINA = 20`
  - `_filas_listado(html: str) -> List[Tuple[str, str]]` — `[(href_relativo, titulo)]`
  - `_num_paginas(html: str) -> int` — `N` de "Mostrando la página 1 de N"; sin encabezado → `1` si hay filas, `0` si no
  - `_ficha(html: str) -> Ficha` con `Ficha = NamedTuple(expedicion: Optional[str], publicacion: Optional[str], pdfs: List[str])` (fechas `AAAA-MM-DD`, pdfs absolutos)

- [ ] **Step 1: Write the failing tests**

Crear `tests/families/test_sic.py`:

```python
from core.scrapers.families.sic import (
    _BASE,
    _ficha,
    _filas_listado,
    _num_paginas,
)

# Marcado real del listado (recortado), 2026-10-07
_FILA = """
<div class="mb-2"><div style="width: 100%;"><div class="views-field views-field-nothing"><span class="field-content"><div class="normas--row shadow-sm p-3 mb-5 bg-body rounded">
	<div class="row">
		<div class="col-md-5">
<span class="text-secondary">Tipo de norma: <strong>Resoluciones  </strong></span>
		</div>
		<div class="col-md-7">
<span class="badge tag--pin label--pin mb-2 ms-2">Despacho de la Superintendencia </span>
		</div>
	</div>
<h2 class="field__label"><a href="{href}" hreflang="es">{titulo}</a></h2>
<div class="col-md-12">
<p> resumen </p>
</div>
</div></span></div></div></div>
"""


def _listado(filas, encabezado="Mostrando la página 1 de 8 páginas"):
    cuerpo = "".join(_FILA.format(href=h, titulo=t) for h, t in filas)
    return f"<html><body><main><div>{encabezado}</div>{cuerpo}</main></body></html>"


def test_filas_listado_extrae_href_y_titulo_limpio():
    html = _listado([
        ("/transparencia/normativa/resolucion-no-77121", "Resolución No. 77121 del 29 de septiembre de 2026 &quot;Por la cual se deroga&quot;"),
        ("/transparencia/normativa/circular-externa-010", "Circular\xa0Externa  010"),
    ])
    assert _filas_listado(html) == [
        ("/transparencia/normativa/resolucion-no-77121",
         'Resolución No. 77121 del 29 de septiembre de 2026 "Por la cual se deroga"'),
        ("/transparencia/normativa/circular-externa-010", "Circular Externa 010"),
    ]


def test_filas_listado_vacio():
    assert _filas_listado("<html><main>Sin resultados</main></html>") == []


def test_num_paginas_lee_el_encabezado():
    assert _num_paginas(_listado([("/a", "x")])) == 8
    assert _num_paginas(_listado([("/a", "x")], "Mostrando la página 1 de 379 páginas")) == 379


def test_num_paginas_sin_encabezado():
    assert _num_paginas(_listado([("/a", "x")], encabezado="")) == 1
    assert _num_paginas(_listado([], encabezado="")) == 0


# Marcado real de una ficha (recortado), 2026-10-07
_FICHA = """
<html><body><main>
<div class="sic--fecha1">
  <div class="field field--name-field-fecha-generacion field--type-datetime field--label-above">
    <div class="field__label">Fecha Expedición</div>
    <div class="field__item"><time datetime="2026-09-29T12:00:00Z" class="datetime">Sep 29, 2026</time></div>
  </div>
</div>
<div class="sic--fecha2">
  <div class="field field--name-field-fecha-publicacion field--type-datetime field--label-above">
    <div class="field__label">Fecha publicación</div>
    <div class="field__item"><time datetime="2026-09-30T12:00:00Z" class="datetime">Sep 30, 2026</time></div>
  </div>
</div>
{adjuntos}
<a href="https://sedeelectronica.sic.gov.co/sites/default/files/normativa/T%C3%A9rminos%20y%20condiciones%20-Sede%20Electr%C3%B3nica.pdf">Términos</a>
</main></body></html>
"""

_ADJUNTOS = """
<div class="sic--adjuntos">
  <div class="field field--name-field-archivo field--type-file field--label-above">
    <div class="field__label">Archivos adjuntos</div>
    <div class="field__items">
      {items}
    </div>
  </div>
</div>
"""

_ITEM = """<div class="field__item"><span class="file file--mime-application-pdf file--application-pdf">
  <a href="{href}" type="application/pdf" target="_blank">Documento<span class="visually-hidden"> (se abrirá en una nueva pestaña)</span></a>
  <p>(276.91 KB)</p></span></div>"""


def _html_ficha(*hrefs):
    adj = _ADJUNTOS.format(items="".join(_ITEM.format(href=h) for h in hrefs)) if hrefs else ""
    return _FICHA.format(adjuntos=adj)


def test_ficha_fechas_y_pdf():
    f = _ficha(_html_ficha("/sites/default/files/normativa/RESOLUCI%C3%93N%2077121%20DE%202026.pdf"))
    assert f.expedicion == "2026-09-29"
    assert f.publicacion == "2026-09-30"
    assert f.pdfs == [f"{_BASE}/sites/default/files/normativa/RESOLUCI%C3%93N%2077121%20DE%202026.pdf"]


def test_ficha_varios_adjuntos_en_orden_y_sin_duplicados():
    f = _ficha(_html_ficha("/sites/default/files/a.pdf", "/sites/default/files/b.pdf", "/sites/default/files/a.pdf"))
    assert f.pdfs == [f"{_BASE}/sites/default/files/a.pdf", f"{_BASE}/sites/default/files/b.pdf"]


def test_ficha_solo_enlace_externo_no_tiene_pdfs():
    # el enlace global "Términos y condiciones" está fuera de field-archivo y no cuenta
    html = _html_ficha().replace(
        "</main>",
        '<div class="sic--enlace"><a href="javascript:void(0)" onclick="showModal(\'https\\u003A\\/\\/www.mintrabajo.gov.co\\/x\')">Ingresa</a></div></main>',
    )
    f = _ficha(html)
    assert f.pdfs == []
    assert f.expedicion == "2026-09-29"


def test_ficha_sin_fechas():
    f = _ficha("<html><main><p>nada</p></main></html>")
    assert (f.expedicion, f.publicacion, f.pdfs) == (None, None, [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/families/test_sic.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.scrapers.families.sic'`

- [ ] **Step 3: Write minimal implementation**

Crear `core/scrapers/families/sic.py`:

```python
"""Superintendencia de Industria y Comercio (SIC).

Normativa propia de la SIC desde el "Sistema de búsquedas de normas, propio de
la entidad" de su sede electrónica (Drupal). Ver
docs/superpowers/specs/2026-10-07-fuente-sic-design.md.
"""
import re
from typing import List, NamedTuple, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

_BASE = "https://sedeelectronica.sic.gov.co"
_LISTADO = f"{_BASE}/transparencia/normativa/busqueda-de-normas/entidad"
_SOURCE = "Superintendencia de Industria y Comercio"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

_POR_PAGINA = 20
_PAGINAS_RE = re.compile(r"Mostrando la p\S*gina\s+\d+\s+de\s+(\d+)")


class Ficha(NamedTuple):
    expedicion: Optional[str]
    publicacion: Optional[str]
    pdfs: List[str]


def _espacios(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _filas_listado(html: str) -> List[Tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    filas = []
    for a in soup.select("div.normas--row h2.field__label a[href]"):
        filas.append((a["href"], _espacios(a.get_text(" "))))
    return filas


def _num_paginas(html: str) -> int:
    m = _PAGINAS_RE.search(html)
    if m:
        return int(m.group(1))
    return 1 if _filas_listado(html) else 0


def _fecha_campo(soup: BeautifulSoup, campo: str) -> Optional[str]:
    t = soup.select_one(f".field--name-{campo} time[datetime]")
    if t is None:
        return None
    iso = t["datetime"][:10]
    return iso if re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso) else None


def _ficha(html: str) -> Ficha:
    soup = BeautifulSoup(html, "html.parser")
    pdfs: List[str] = []
    # sólo los adjuntos del campo de archivo: todas las páginas del sitio traen
    # además un enlace global a "Términos y condiciones -Sede Electrónica.pdf"
    for a in soup.select(".field--name-field-archivo a[href]"):
        url = urljoin(_BASE, a["href"])
        if url not in pdfs:
            pdfs.append(url)
    return Ficha(
        expedicion=_fecha_campo(soup, "field-fecha-generacion"),
        publicacion=_fecha_campo(soup, "field-fecha-publicacion"),
        pdfs=pdfs,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/families/test_sic.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/sic.py tests/families/test_sic.py
git commit -m "feat(sic): parseo del listado y de la ficha del buscador de normas"
```

---

### Task 2: Clasificación y nomenclatura

**Files:**
- Modify: `core/scrapers/families/sic.py` (agregar al final)
- Test: `tests/families/test_sic.py` (agregar al final)

**Interfaces:**
- Consumes: nada de Task 1 salvo el módulo.
- Produces:
  - Constantes de clasificación: `_CLAS_RES = "177"`, `_CLAS_CIR = "179"`, `_CLAS_TCU = "178"`, `_CLAS_DOC = "180"`
  - Tipos: `_TIPO_RES = "Resolución"`, `_TIPO_CIR = "Circular"`, `_TIPO_TCU = "Título Circular Única"`, `_TIPO_CTO = "Concepto"`, `_TIPO_REL = "Relatoría"`
  - `_clasificar(clasif: str, titulo: str) -> Optional[str]` — tipo, o `None` si se descarta
  - `_titulo(tipo: str, titulo_sitio: str, expedicion: str) -> Tuple[str, bool]` — `(título, title_unverified)`; `expedicion` en `AAAA-MM-DD`
  - `_crudo(titulo_sitio: str) -> str`
  - `_safe_title(title: str) -> str`

- [ ] **Step 1: Write the failing tests**

Agregar a `tests/families/test_sic.py` (y sumar los nombres al import del inicio):

```python
from core.scrapers.families.sic import (
    _CLAS_CIR,
    _CLAS_DOC,
    _CLAS_RES,
    _CLAS_TCU,
    _TIPO_CIR,
    _TIPO_CTO,
    _TIPO_REL,
    _TIPO_RES,
    _TIPO_TCU,
    _clasificar,
    _crudo,
    _safe_title,
    _titulo,
)


def test_clasificar_resoluciones_incluye_nombramientos():
    assert _clasificar(_CLAS_RES, 'Resolución No. 77121 del 29 de septiembre de 2026 "Por la cual se deroga"') == _TIPO_RES
    assert _clasificar(_CLAS_RES, "Resolución No. 29705 de 2026 PROFESIONAL U. 2044-07 G.T. REGULACIÓN - OFICINA ASESORA JURÍDICA") == _TIPO_RES


def test_clasificar_descarta_proyectos():
    assert _clasificar(_CLAS_RES, "Proyecto de Resolución “Por la cual se adicionan incisos”") is None
    assert _clasificar(_CLAS_CIR, "Proyecto de Circular Externa la cual tiene como asunto") is None


def test_clasificar_descarta_otra_entidad_por_la_cabeza_del_titulo():
    assert _clasificar(_CLAS_RES, "Resolución 7356 de 2024 de la Comisión de Regulación de Comunicaciones, “Por la cual”") is None
    assert _clasificar(_CLAS_RES, "Resolución 0612 de 2024 del Ministerio de Comercio Industria y Turismo, “Por la cual”") is None
    assert _clasificar(_CLAS_RES, 'Resolución 862 de 2023 de la Dirección de Regulación del Ministerio de Comercio, "Por la cual"') is None
    assert _clasificar(_CLAS_CIR, "Circular Externa 1 de 2023 - De la Agencia Nacional de Defensa Jurídica del Estado, “Lineamientos”") is None


def test_clasificar_no_descarta_sic_que_cita_un_ministerio_en_su_epigrafe():
    assert _clasificar(_CLAS_RES, 'Resolución No. 1111 del 24 de enero de 2025 "Por medio de la cual se fija la tasa del Ministerio de Comercio"') == _TIPO_RES
    assert _clasificar(_CLAS_RES, 'Resolución No 122 de 2025 de la Superintendencia de Industria y Comercio, "Por la cual"') == _TIPO_RES
    assert _clasificar(_CLAS_RES, "Resolución 1059 por la cual se reglamenta lo del Ministerio") == _TIPO_RES


def test_clasificar_titulos_circular_unica():
    assert _clasificar(_CLAS_TCU, "Título X - Actualizado el 30 de enero de 2026.") == _TIPO_TCU
    assert _clasificar(_CLAS_TCU, 'Resolución No. 62932 de 2025 "Por la cual se adiciona"') == _TIPO_RES


def test_clasificar_doctrina():
    assert _clasificar(_CLAS_DOC, "Concepto 15-159447 del 25 de agosto de 2015") == _TIPO_CTO
    assert _clasificar(_CLAS_DOC, "RELATORÍA RESOLUCIÓN 27305 - 10-07-2019 - CONCONCRETO") == _TIPO_REL
    assert _clasificar(_CLAS_DOC, "Resolución No. 3839 del 4 de febrero de 2015") == _TIPO_RES
    for otro in (
        "Sentencia Expediente Radicación 2007 00102 02 del 16 de febrero de 2017 Consejo Estado",
        "Radicado No. 2016-01884-01 del 12 de octubre de 2016 Consejo Superior de la Judicatura",
        "Informe de gestión 2016", "Acta 3 de 2016", "Estudio de mercado", "Auto 123",
    ):
        assert _clasificar(_CLAS_DOC, otro) is None, otro


def test_titulo_resolucion():
    assert _titulo(_TIPO_RES, 'Resolución No. 77121 del 29 de septiembre de 2026 "Por la cual"', "2026-09-29") == ("R_SIC_77121_2026", False)
    assert _titulo(_TIPO_RES, "RESOLUCIÓN 000610 DE 13 DE ABRIL DE 2026", "2026-04-13") == ("R_SIC_0610_2026", False)
    assert _titulo(_TIPO_RES, "Resolución Número 122 de 2025", "2025-01-10") == ("R_SIC_0122_2025", False)
    assert _titulo(_TIPO_RES, "Resolución N° 4.231 de 2024", "2024-02-22") == ("R_SIC_4231_2024", False)


def test_titulo_circular_todas_con_c():
    assert _titulo(_TIPO_CIR, "Circular Externa No 4 de 2024 de la Superintendencia", "2024-05-02") == ("C_SIC_0004_2024", False)
    assert _titulo(_TIPO_CIR, "Circular Interna No. 006 del 17 de marzo de 2025", "2025-03-17") == ("C_SIC_0006_2025", False)
    assert _titulo(_TIPO_CIR, "Circular Conjunta 010 de 2026", "2026-02-08") == ("C_SIC_0010_2026", False)
    assert _titulo(_TIPO_CIR, "Circular 011 de 2020", "2020-07-01") == ("C_SIC_0011_2020", False)
    assert _titulo(_TIPO_CIR, "Circular\xa0Externa 001 del 2026", "2026-01-15") == ("C_SIC_0001_2026", False)


def test_titulo_circular_sin_numero_queda_sin_verificar():
    assert _titulo(_TIPO_CIR, "Circular Única de Calidad Turística", "2026-02-06") == ("Circular Única de Calidad Turística", True)


def test_titulo_circular_unica_romano_y_fecha_de_version():
    assert _titulo(_TIPO_TCU, "Título X - Actualizado el 30 de enero de 2026.", "2026-01-30") == ("TCU_SIC_X_20260130", False)
    assert _titulo(_TIPO_TCU, "TÍTULO II", "2021-03-23") == ("TCU_SIC_II_20210323", False)
    assert _titulo(_TIPO_TCU, "Titulo I.", "2022-09-29") == ("TCU_SIC_I_20220929", False)
    assert _titulo(_TIPO_TCU, "Título X Propiedad Industrial", "2022-01-17") == ("TCU_SIC_X_20220117", False)


def test_titulo_concepto_radicado():
    assert _titulo(_TIPO_CTO, "Concepto 15-159447 del 25 de agosto de 2015", "2015-08-25") == ("CTO_SIC_15-159447", False)
    assert _titulo(_TIPO_CTO, "Concepto 17 49443 del 28 de marzo de 2017", "2017-03-28") == ("CTO_SIC_17-49443", False)
    assert _titulo(_TIPO_CTO, "Concepto sobre publicidad", "2016-01-01") == ("Concepto sobre publicidad", True)


def test_titulo_relatoria():
    assert _titulo(_TIPO_REL, "RELATORÍA RESOLUCIÓN 27305 - 10-07-2019 - CONCONCRETO", "2019-07-10") == ("REL_SIC_27305_2019", False)
    assert _titulo(_TIPO_REL, "RELATORÍA RESOLUCIÓN 56158 DEL 31-08-2021 - RESUELVE RECURSO - ASE", "2021-08-31") == ("REL_SIC_56158_2021", False)


def test_crudo_y_safe_title():
    assert _crudo("  ") == "documento"
    assert _crudo("x" * 200) == "x" * 120
    assert _crudo("Título final. ") == "Título final"
    assert _safe_title('Resolución "X": a/b') == "Resolución -X-- a-b"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/families/test_sic.py -v`
Expected: FAIL — `ImportError: cannot import name '_CLAS_CIR'`

- [ ] **Step 3: Write minimal implementation**

Agregar `import unicodedata` a los imports de `sic.py` y al final del módulo:

```python
_CLAS_RES = "177"
_CLAS_CIR = "179"
_CLAS_TCU = "178"
_CLAS_DOC = "180"

_TIPO_RES = "Resolución"
_TIPO_CIR = "Circular"
_TIPO_TCU = "Título Circular Única"
_TIPO_CTO = "Concepto"
_TIPO_REL = "Relatoría"

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_MAX_TITULO = 120

# Sólo se mira la "cabeza" del título (antes de comillas, coma o " por "): el
# epígrafe de una resolución propia puede citar un ministerio sin ser de él.
_CABEZA_RE = re.compile(r'["“”«»,]| por ')
_OTRA_ENTIDAD_RE = re.compile(r"\b(?:de la|del)\s+(?:comision|ministerio|departamento|agencia|presidencia)\b")

_NUM_RES_RE = re.compile(r"resolucion(?:es)?\s*(?:no\.?|n[°º]\.?|numero)?\s*(\d[\d.]*)")
_NUM_CIR_RE = re.compile(r"circular(?:\s+(?:externa|interna|conjunta))?\s*(?:no\.?|n[°º]\.?|numero)?\s*(\d+)")
_ROMANO_RE = re.compile(r"titulo\s+([ivxlc]+)\b")
_RADICADO_RE = re.compile(r"concepto\s+(?:no\.?\s*)?(\d{2})\s*[- ]\s*(\d+)")


def _norm(s: str) -> str:
    """Minúsculas, sin acentos y con espacios colapsados (incluye &nbsp;)."""
    sin = "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))
    return _espacios(sin).lower()


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:_MAX_TITULO].strip(" .")


def _crudo(titulo_sitio: str) -> str:
    crudo = (titulo_sitio or "").strip()[:_MAX_TITULO].strip(" .")
    return crudo or "documento"


def _de_otra_entidad(t: str) -> bool:
    cabeza = _CABEZA_RE.split(t, maxsplit=1)[0]
    return bool(_OTRA_ENTIDAD_RE.search(cabeza))


def _clasificar(clasif: str, titulo: str) -> Optional[str]:
    t = _norm(titulo)
    if t.startswith("proyecto"):
        return None
    if clasif == _CLAS_RES:
        return None if _de_otra_entidad(t) else _TIPO_RES
    if clasif == _CLAS_CIR:
        return None if _de_otra_entidad(t) else _TIPO_CIR
    if clasif == _CLAS_TCU:
        return _TIPO_RES if t.startswith("resolucion") else _TIPO_TCU
    if clasif == _CLAS_DOC:
        if t.startswith("concepto"):
            return _TIPO_CTO
        if t.startswith("relatoria"):
            return _TIPO_REL
        if t.startswith("resolucion"):
            return _TIPO_RES
        return None
    return None


def _entero(texto: str) -> Optional[int]:
    digitos = texto.replace(".", "")
    return int(digitos) if digitos.isdigit() else None


def _titulo(tipo: str, titulo_sitio: str, expedicion: str) -> Tuple[str, bool]:
    t = _norm(titulo_sitio)
    anio = expedicion[:4]
    if tipo in (_TIPO_RES, _TIPO_REL):
        m = _NUM_RES_RE.search(t)
        n = _entero(m.group(1)) if m else None
        if n is not None:
            pref = "R" if tipo == _TIPO_RES else "REL"
            return f"{pref}_SIC_{n:04d}_{anio}", False
    elif tipo == _TIPO_CIR:
        m = _NUM_CIR_RE.search(t)
        if m:
            return f"C_SIC_{int(m.group(1)):04d}_{anio}", False
    elif tipo == _TIPO_TCU:
        m = _ROMANO_RE.search(t)
        if m:
            return f"TCU_SIC_{m.group(1).upper()}_{expedicion.replace('-', '')}", False
    elif tipo == _TIPO_CTO:
        m = _RADICADO_RE.search(t)
        if m:
            return f"CTO_SIC_{m.group(1)}-{m.group(2)}", False
    return _crudo(titulo_sitio), True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/families/test_sic.py -v`
Expected: all passed (8 de Task 1 + 13 nuevos)

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/sic.py tests/families/test_sic.py
git commit -m "feat(sic): clasificación de fichas y nomenclatura de títulos"
```

---

### Task 3: Enumeración completa de una tajada (clasificación × año)

**Files:**
- Modify: `core/scrapers/families/sic.py` (agregar al final)
- Test: `tests/families/test_sic.py` (agregar al final)

**Interfaces:**
- Consumes: `_LISTADO`, `_POR_PAGINA`, `_filas_listado`, `_num_paginas` (Task 1).
- Produces:
  - `_MAX_BUSQUEDAS = 4000` (presupuesto de consultas de listado por corrida), `_MAX_LARGO_FRAGMENTO = 6`
  - `class _PresupuestoAgotado(Exception)`
  - `_enumerar_tajada(session, clasif: str, anio: int, presupuesto: List[int], stop_event, on_progress) -> Dict[str, str]` — `{href: titulo}`; descuenta `presupuesto[0]` por consulta; lanza `_PresupuestoAgotado` al llegar a 0.

- [ ] **Step 1: Write the failing tests**

Agregar a `tests/families/test_sic.py` (sumar `_enumerar_tajada`, `_LISTADO`, `_PresupuestoAgotado` al import, e `import random`, `from urllib.parse import parse_qs, urlparse`, `import requests`, `import responses` arriba):

```python
def _sitio_inestable(todos, semilla=1, modo="azar"):
    """Callback de `responses` que imita el buscador real, con búsqueda
    `combine` por 'contiene' sobre el título. `modo`:
    - "azar": reordena al azar en cada petición (filas repetidas y perdidas)
    - "pierde": toda página no final devuelve las 20 primeras (pérdida segura)
    - "estable": paginación correcta"""
    rnd = random.Random(semilla)

    def cb(request):
        qs = parse_qs(urlparse(request.url).query)
        combine = qs.get("combine", [""])[0]
        lista = [(h, t) for h, t in todos if combine in t] if combine else list(todos)
        if not lista:
            return (200, {}, _listado([], encabezado=""))
        n = (len(lista) + 19) // 20
        p = int(qs.get("page", ["0"])[0])
        orden = list(lista)
        if n > 1 and modo == "azar":
            rnd.shuffle(orden)  # el "orden" cambia en cada petición
        if p == n - 1:
            pagina = orden[(n - 1) * 20:] if modo == "estable" else orden[: len(lista) - (n - 1) * 20]
        elif modo == "estable":
            pagina = orden[p * 20:(p + 1) * 20]
        else:
            pagina = orden[:20]
        return (200, {}, _listado(pagina, encabezado=f"Mostrando la página {p + 1} de {n} páginas"))

    return cb


def _docs(n):
    return [(f"/transparencia/normativa/r-{i}", f"Resolución {10000 + i * 37} de 2025 PROFESIONAL") for i in range(n)]


@responses.activate
def test_enumerar_tajada_una_pagina_no_busca_por_fragmentos():
    todos = _docs(15)
    responses.add_callback(responses.GET, _LISTADO, callback=_sitio_inestable(todos))
    pres = [100]
    got = _enumerar_tajada(requests.Session(), _CLAS_RES, 2025, pres, None, None)
    assert got == dict(todos)
    assert len(responses.calls) == 1
    qs = parse_qs(urlparse(responses.calls[0].request.url).query)
    assert qs["field_clasificacion2_target_id"] == ["177"]
    assert qs["field_fecha_publicacion_value"] == ["2025"]


@responses.activate
def test_enumerar_tajada_vacia():
    responses.add_callback(responses.GET, _LISTADO, callback=_sitio_inestable([]))
    assert _enumerar_tajada(requests.Session(), _CLAS_DOC, 2026, [100], None, None) == {}


@responses.activate
def test_enumerar_tajada_completa_pese_al_reordenamiento():
    todos = _docs(130)  # 7 páginas
    responses.add_callback(responses.GET, _LISTADO, callback=_sitio_inestable(todos))
    progreso = []
    got = _enumerar_tajada(requests.Session(), _CLAS_RES, 2025, [4000], None, progreso.append)
    assert got == dict(todos)
    assert not any("faltan" in m for m in progreso)


@responses.activate
def test_enumerar_tajada_no_busca_fragmentos_si_las_paginas_ya_completan():
    todos = _docs(45)  # 3 páginas
    responses.add_callback(responses.GET, _LISTADO, callback=_sitio_inestable(todos, modo="estable"))
    pres = [4000]
    got = _enumerar_tajada(requests.Session(), _CLAS_RES, 2025, pres, None, None)
    assert got == dict(todos)
    assert not any("combine=" in c.request.url for c in responses.calls)
    assert len(responses.calls) == 3          # página 0, última, página 1
    assert pres[0] == 4000 - 3


@responses.activate
def test_enumerar_tajada_avisa_cuando_faltan():
    # títulos sin dígitos: la búsqueda por fragmentos no puede encontrarlos, y
    # el sitio "pierde" la página del medio
    todos = [(f"/transparencia/normativa/x-{i}", "Por la cual se suspenden términos") for i in range(60)]
    responses.add_callback(responses.GET, _LISTADO, callback=_sitio_inestable(todos, modo="pierde"))
    progreso = []
    got = _enumerar_tajada(requests.Session(), _CLAS_RES, 2025, [4000], None, progreso.append)
    assert len(got) < 60
    assert any(f"faltan {60 - len(got)}" in m for m in progreso)


@responses.activate
def test_enumerar_tajada_presupuesto_agotado():
    responses.add_callback(responses.GET, _LISTADO, callback=_sitio_inestable(_docs(130)))
    pres = [5]
    try:
        _enumerar_tajada(requests.Session(), _CLAS_RES, 2025, pres, None, None)
        assert False, "debía agotar el presupuesto"
    except _PresupuestoAgotado:
        pass
    assert len(responses.calls) == 5


@responses.activate
def test_enumerar_tajada_ultima_pagina_caida_no_da_un_total_falso():
    # 30 fichas = 2 páginas; la última (page=1) falla siempre. Sin total
    # verificable no se puede dar por completa la tajada con las 20 de la
    # página 0: se sigue con la búsqueda por fragmentos.
    todos = _docs(30)
    sitio = _sitio_inestable(todos, modo="estable")

    def cb(request):
        if "page=1" in request.url:
            return (500, {}, "error")
        return sitio(request)

    responses.add_callback(responses.GET, _LISTADO, callback=cb)
    progreso = []
    got = _enumerar_tajada(requests.Session(), _CLAS_RES, 2025, [4000], None, progreso.append)
    assert any("Error" in m for m in progreso)
    assert len([c for c in responses.calls if "page=1" in c.request.url]) == 2  # un reintento
    assert got == dict(todos)
    assert not any("faltan" in m for m in progreso)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/families/test_sic.py -v`
Expected: FAIL — `ImportError: cannot import name '_enumerar_tajada'`

- [ ] **Step 3: Write minimal implementation**

Agregar `Dict` a `from typing import …` y al final de `sic.py`:

```python
# Consultas de listado (páginas + fragmentos) permitidas en una corrida. Una
# carga 2015→hoy completa gasta del orden de 1.000 por año grande.
_MAX_BUSQUEDAS = 4000
_MAX_LARGO_FRAGMENTO = 6
_DIGITOS = "0123456789"


class _PresupuestoAgotado(Exception):
    pass


def _enumerar_tajada(session, clasif: str, anio: int, presupuesto: List[int],
                     stop_event, on_progress) -> Dict[str, str]:
    """Todas las fichas de una clasificación publicadas en `anio`.

    El buscador reordena al azar las filas con igual fecha de publicación en
    cada petición, así que recorrer las páginas repite unas y pierde otras. Se
    conoce el total exacto (la última página dice cuántas filas quedan), y se
    completa con búsquedas `combine` por fragmentos de dígitos: un fragmento
    que cabe en una página no sufre el reordenamiento. Se para apenas se
    alcanza el total.
    """
    base = {"field_clasificacion2_target_id": clasif, "field_fecha_publicacion_value": str(anio)}
    por_href: Dict[str, str] = {}

    def parar() -> bool:
        return stop_event is not None and stop_event.is_set()

    def consultar(extra: dict) -> Tuple[int, List[Tuple[str, str]]]:
        if presupuesto[0] <= 0:
            raise _PresupuestoAgotado
        presupuesto[0] -= 1
        try:
            resp = session.get(_LISTADO, params={**base, **extra}, timeout=90)
            resp.raise_for_status()
        except Exception as e:
            if on_progress:
                on_progress(f"[{_SOURCE}] Error consultando el listado {clasif}/{anio} {extra}: {e}")
            return -1, []
        return _num_paginas(resp.text), _filas_listado(resp.text)

    def agregar(filas):
        for href, titulo in filas:
            por_href.setdefault(href, titulo)

    n, filas = consultar({"page": 0})
    agregar(filas)
    if n <= 1:
        return por_href

    m_ult, ultimas = consultar({"page": n - 1})
    if m_ult < 0:
        m_ult, ultimas = consultar({"page": n - 1})  # un reintento
    agregar(ultimas)
    # sin la última página no hay total verificable: se enumera sin parada temprana
    total: Optional[int] = (n - 1) * _POR_PAGINA + len(ultimas) if m_ult >= 0 else None

    def completo() -> bool:
        return total is not None and len(por_href) >= total

    for p in range(1, n - 1):
        if parar() or completo():
            break
        agregar(consultar({"page": p})[1])

    def fragmento(s: str):
        if parar() or completo():
            return
        m, filas = consultar({"combine": s})
        if m <= 1 or len(s) >= _MAX_LARGO_FRAGMENTO:
            agregar(filas)
            return
        for d in _DIGITOS:
            fragmento(s + d)

    for d in _DIGITOS:
        fragmento(d)

    if total is not None and len(por_href) < total and not parar() and on_progress:
        on_progress(
            f"[{_SOURCE}] Aviso: listado {clasif}/{anio} con {total} fichas, "
            f"faltan {total - len(por_href)} que no se pudieron enumerar"
        )
    return por_href
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/families/test_sic.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/sic.py tests/families/test_sic.py
git commit -m "feat(sic): enumeración completa por tajada pese a la paginación inestable"
```

---

### Task 4: Clase `ScrapSIC` (fichas, filtros, anexos, colisiones)

**Files:**
- Modify: `core/scrapers/families/sic.py` (agregar imports y al final)
- Modify: `core/scrapers/families/__init__.py` (importar `sic`)
- Test: `tests/families/test_sic.py` (agregar al final)

**Interfaces:**
- Consumes: todo lo anterior.
- Produces:
  - `_ANIO_MIN = 2015`, `_CLASIFICACIONES: List[Tuple[str, str]]` (orden: Resoluciones, Circulares, Títulos CU, Doctrina)
  - `_anios(fini: str, ffin: str, hoy: date) -> List[int]`
  - `@register_family("sic") class ScrapSIC(BaseScrapper)` con `filters_by_publication_date = True` y `scrap(fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]`

- [ ] **Step 1: Write the failing tests**

Agregar a `tests/families/test_sic.py` (sumar `ScrapSIC`, `_anios` al import y `from datetime import date`):

```python
def test_anios_rango_y_piso():
    hoy = date(2026, 10, 7)
    assert _anios("2026-10-01", "2026-10-07", hoy) == [2026]
    assert _anios("2025-12-01", "2025-12-31", hoy) == [2025, 2026]  # se publica en enero siguiente
    assert _anios("2010-01-01", "2016-06-30", hoy) == [2015, 2016, 2017]
    assert _anios("2000-01-01", "2010-12-31", hoy) == []


def _registrar_sitio(listados, fichas):
    """listados: {clasif: [(href, titulo)]} (una página, cualquier año);
    fichas: {href: html}."""
    def cb_listado(request):
        qs = parse_qs(urlparse(request.url).query)
        filas = listados.get(qs["field_clasificacion2_target_id"][0], [])
        return (200, {}, _listado(filas, encabezado=""))

    responses.add_callback(responses.GET, _LISTADO, callback=cb_listado)
    for href, html in fichas.items():
        if isinstance(html, int):
            responses.add(responses.GET, f"{_BASE}{href}", status=html)
        else:
            responses.add(responses.GET, f"{_BASE}{href}", body=html)


def _ficha_con(exp, pub, *pdfs):
    return _html_ficha(*pdfs).replace("2026-09-29", exp).replace("2026-09-30", pub)


@responses.activate
def test_scrap_resolucion_basica():
    _registrar_sitio(
        {_CLAS_RES: [("/r1", 'Resolución No. 77121 del 29 de septiembre de 2026 "Por la cual"')]},
        {"/r1": _ficha_con("2026-09-29", "2026-09-30", "/sites/default/files/normativa/R77121.pdf")},
    )
    docs = ScrapSIC().scrap("2026-09-01", "2026-09-30")
    assert len(docs) == 1
    d = docs[0]
    assert d.title == "R_SIC_77121_2026"
    assert d.tipo == "Resolución"
    assert d.f_public == "2026-09-30"
    assert d.f_providencia == "2026-09-29"
    assert d.link == {"url": f"{_BASE}/sites/default/files/normativa/R77121.pdf", "method": "GET"}
    assert d.save_path == "Superintendencia de Industria y Comercio/2026-09-30/Resolución/R_SIC_77121_2026(extension)"
    assert d.title_unverified is False
    assert d.detalle.startswith("Resolución No. 77121")


@responses.activate
def test_scrap_filtra_por_publicacion_piso_y_pdf():
    _registrar_sitio(
        {_CLAS_RES: [
            ("/fuera", "Resolución 1 de 2026"),        # publicada fuera de rango
            ("/vieja", "Resolución 2 de 2014"),        # expedida antes de 2015
            ("/sinpdf", "Resolución 3 de 2026"),       # sólo enlace externo
            ("/ok", "Resolución 4 de 2026"),
        ]},
        {
            "/fuera": _ficha_con("2026-08-01", "2026-08-02", "/f/1.pdf"),
            "/vieja": _ficha_con("2014-12-30", "2026-09-10", "/f/2.pdf"),
            "/sinpdf": _ficha_con("2026-09-10", "2026-09-10"),
            "/ok": _ficha_con("2026-09-10", "2026-09-10", "/f/4.pdf"),
        },
    )
    progreso = []
    docs = ScrapSIC().scrap("2026-09-01", "2026-09-30", on_progress=progreso.append)
    assert [d.title for d in docs] == ["R_SIC_0004_2026"]
    assert any("sin PDF" in m for m in progreso)


@responses.activate
def test_scrap_descartados_no_abren_ficha():
    _registrar_sitio(
        {_CLAS_RES: [("/p", "Proyecto de Resolución “X”")],
         _CLAS_DOC: [("/s", "Sentencia Expediente 2007 00102 Consejo de Estado")]},
        {},
    )
    progreso = []
    docs = ScrapSIC().scrap("2026-09-01", "2026-09-30", on_progress=progreso.append)
    assert docs == []
    assert not any(c.request.url in (f"{_BASE}/p", f"{_BASE}/s") for c in responses.calls)
    assert any("1 fichas descartadas" in m for m in progreso)


@responses.activate
def test_scrap_anexos_y_colision():
    _registrar_sitio(
        {_CLAS_CIR: [
            ("/ce", "Circular Externa 010 de 2026"),
            ("/cj", "Circular Conjunta 010 de 2026"),
        ]},
        {
            "/ce": _ficha_con("2026-02-16", "2026-02-16", "/f/ce.pdf", "/f/ce-anexo.pdf"),
            "/cj": _ficha_con("2026-02-08", "2026-02-08", "/f/cj.pdf"),
        },
    )
    docs = ScrapSIC().scrap("2026-01-01", "2026-12-31")
    por_url = {d.link["url"].rsplit("/", 1)[-1]: d for d in docs}
    assert por_url["ce.pdf"].title == "C_SIC_0010_2026"
    assert por_url["ce-anexo.pdf"].title == "C_SIC_0010_2026_A01"
    # misma clave que la externa -> baja al título del sitio, sin verificar
    assert por_url["cj.pdf"].title == "Circular Conjunta 010 de 2026"
    assert por_url["cj.pdf"].title_unverified is True
    assert all(d.tipo == "Circular" for d in docs)


@responses.activate
def test_scrap_misma_resolucion_en_resoluciones_y_doctrina_se_ingiere_una_vez():
    ficha = _ficha_con("2016-02-04", "2016-02-04", "/f/res3839.pdf")
    _registrar_sitio(
        {_CLAS_RES: [("/r", "Resolución No. 3839 del 4 de febrero de 2016")],
         _CLAS_DOC: [("/d", "Resolución No. 3839 del 4 de febrero de 2016")]},
        {"/r": ficha, "/d": ficha},
    )
    docs = ScrapSIC().scrap("2016-01-01", "2016-12-31")
    assert [d.title for d in docs] == ["R_SIC_3839_2016"]


@responses.activate
def test_scrap_ficha_caida_no_aborta():
    _registrar_sitio(
        {_CLAS_RES: [("/mala", "Resolución 1 de 2026"), ("/buena", "Resolución 2 de 2026")]},
        {"/mala": 500, "/buena": _ficha_con("2026-09-10", "2026-09-10", "/f/2.pdf")},
    )
    progreso = []
    docs = ScrapSIC().scrap("2026-09-01", "2026-09-30", on_progress=progreso.append)
    assert [d.title for d in docs] == ["R_SIC_0002_2026"]
    assert any("Error" in m and "Resolución 1" in m for m in progreso)


@responses.activate
def test_scrap_clasificaciones_vacias_solo_avisan_si_todas_lo_estan():
    _registrar_sitio(
        {_CLAS_RES: [("/r", "Resolución 2 de 2026")]},
        {"/r": _ficha_con("2026-09-10", "2026-09-10", "/f/2.pdf")},
    )
    progreso = []
    ScrapSIC().scrap("2026-09-01", "2026-09-30", on_progress=progreso.append)
    assert not any("cambió" in m for m in progreso)

    responses.reset()
    _registrar_sitio({}, {})
    progreso = []
    ScrapSIC().scrap("2026-09-01", "2026-09-30", on_progress=progreso.append)
    assert any("cambió" in m for m in progreso)


@responses.activate
def test_scrap_respeta_limit_y_stop_event():
    filas = [(f"/r{i}", f"Resolución {i} de 2026") for i in range(1, 6)]
    _registrar_sitio(
        {_CLAS_RES: filas},
        {h: _ficha_con("2026-09-10", "2026-09-10", f"/f/{h[1:]}.pdf") for h, _ in filas},
    )
    assert len(ScrapSIC().scrap("2026-09-01", "2026-09-30", limit=2)) == 2

    import threading
    ev = threading.Event()
    ev.set()
    assert ScrapSIC().scrap("2026-09-01", "2026-09-30", stop_event=ev) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/families/test_sic.py -v`
Expected: FAIL — `ImportError: cannot import name 'ScrapSIC'`

- [ ] **Step 3: Write minimal implementation**

Agregar a los imports de `sic.py`:

```python
from datetime import date

import requests

from core.models import RawDocModel
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path
```

y al final del módulo:

```python
_ANIO_MIN = 2015
_PISO = f"{_ANIO_MIN}-01-01"

# Orden deliberado: las resoluciones de Resoluciones reclaman su título
# R_SIC_… antes que las mismas resoluciones repetidas en Doctrina.
_CLASIFICACIONES: List[Tuple[str, str]] = [
    (_CLAS_RES, "Resoluciones"),
    (_CLAS_CIR, "Circulares"),
    (_CLAS_TCU, "Títulos Circular Única"),
    (_CLAS_DOC, "Doctrina"),
]


def _anios(fini: str, ffin: str, hoy: date) -> List[int]:
    """Años de PUBLICACIÓN a consultar: un acto expedido a fin de año puede
    publicarse en enero del siguiente."""
    desde = max(_ANIO_MIN, int(fini[:4]))
    hasta = min(int(ffin[:4]) + 1, hoy.year)
    return list(range(desde, hasta + 1))


@register_family("sic")
class ScrapSIC(BaseScrapper):
    filters_by_publication_date = True

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=10000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        session = requests.Session()
        session.headers.update({"User-Agent": _UA})
        docs: List[RawDocModel] = []
        vistos: set = set()       # URLs de PDF ya emitidas
        claves: dict = {}         # (tipo, safe_title) -> URL del PDF que la ocupa
        presupuesto = [_MAX_BUSQUEDAS]
        agotado = False
        filas_totales = 0

        def parar() -> bool:
            return stop_event is not None and stop_event.is_set()

        for clasif, nombre in _CLASIFICACIONES:
            if parar():
                break
            if on_progress:
                on_progress(f"[{_SOURCE}] Listando {nombre}...")
            filas: Dict[str, str] = {}
            if not agotado:
                try:
                    for anio in _anios(fini, ffin, date.today()):
                        if parar():
                            break
                        filas.update(_enumerar_tajada(session, clasif, anio, presupuesto, stop_event, on_progress))
                except _PresupuestoAgotado:
                    agotado = True
                    if on_progress:
                        on_progress(
                            f"[{_SOURCE}] Error: presupuesto de {_MAX_BUSQUEDAS} consultas de listado "
                            f"agotado en {nombre}; se procesa lo ya encontrado"
                        )
            filas_totales += len(filas)

            descartadas = 0
            sin_pdf = 0
            for href, titulo in filas.items():
                if parar():
                    return docs[:limit]
                tipo = _clasificar(clasif, titulo)
                if tipo is None:
                    descartadas += 1
                    continue
                try:
                    resp = session.get(urljoin(_BASE, href), timeout=90)
                    resp.raise_for_status()
                except Exception as e:
                    if on_progress:
                        on_progress(f"[{_SOURCE}] Error abriendo la ficha «{titulo[:70]}»: {e}")
                    continue
                ficha = _ficha(resp.text)
                expedicion = ficha.expedicion or ficha.publicacion
                publicacion = ficha.publicacion or ficha.expedicion
                if expedicion is None:
                    if on_progress:
                        on_progress(f"[{_SOURCE}] Aviso: ficha sin fechas «{titulo[:70]}», se omite")
                    continue
                if expedicion < _PISO or publicacion < fini or publicacion > ffin:
                    continue
                if not ficha.pdfs:
                    sin_pdf += 1
                    continue

                base_title, unverified = _titulo(tipo, titulo, expedicion)
                for i, url_pdf in enumerate(ficha.pdfs):
                    if url_pdf in vistos:
                        continue
                    vistos.add(url_pdf)
                    sufijo = f"_A{i:02d}" if i else ""
                    title, unv = base_title + sufijo, unverified
                    if claves.get((tipo, _safe_title(title)), url_pdf) != url_pdf:
                        # otra ficha ya ocupó esta clave (p. ej. circular externa
                        # y conjunta con igual número y año): baja al título del sitio
                        title, unv = _crudo(titulo) + sufijo, True
                        n = 2
                        while claves.get((tipo, _safe_title(title)), url_pdf) != url_pdf:
                            title = f"{_crudo(titulo)}_{n}{sufijo}"
                            n += 1
                    claves[(tipo, _safe_title(title))] = url_pdf
                    docs.append(RawDocModel(
                        source=_SOURCE,
                        link={"url": url_pdf, "method": "GET"},
                        title=title,
                        tipo=tipo,
                        f_public=publicacion,
                        f_providencia=expedicion,
                        detalle=titulo or None,
                        save_path=storage_path(_SOURCE, publicacion, tipo, f"{_safe_title(title)}(extension)"),
                        title_unverified=unv,
                    ))
                    if len(docs) >= limit:
                        return docs[:limit]

            if on_progress and (descartadas or sin_pdf):
                on_progress(
                    f"[{_SOURCE}] {nombre}: {descartadas} fichas descartadas (proyectos, otras "
                    f"entidades u otra doctrina) y {sin_pdf} sin PDF propio en el rango"
                )

        if filas_totales == 0 and not parar() and on_progress:
            on_progress(
                f"[{_SOURCE}] Aviso: el buscador no devolvió ninguna ficha en el rango "
                "(¿cambió el marcado de la página?)"
            )
        return docs[:limit]
```

En `core/scrapers/families/__init__.py` agregar `, sic` al final de la lista de imports (después de `minsalud`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/families/test_sic.py -v`
Expected: all passed

Nota: `test_scrap_filtra_por_publicacion_piso_y_pdf` depende de que el mensaje de resumen contenga "sin PDF"; el texto de arriba dice "sin PDF propio".

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/sic.py core/scrapers/families/__init__.py tests/families/test_sic.py
git commit -m "feat(sic): familia sic con filtros, anexos y colisiones de título"
```

---

### Task 5: Registro, documentación y corrida real en dev

**Files:**
- Modify: `core/seed.py` (diccionario de descripciones ~línea 96 y bloque `create_source_if_missing` ~línea 240)
- Modify: `tests/test_seed.py:45-69` (conteos y conjunto de familias)
- Modify: `docs/guia-despliegue-sistemas.md` (nueva sección en "10. Notas por fuente", después de `minsalud`)

**Interfaces:**
- Consumes: `ScrapSIC` registrada como `"sic"` (Task 4).

- [ ] **Step 1: Update the seed test (failing)**

En `tests/test_seed.py`:
- `assert len(families) == 28` → `== 29`
- ambos `assert len(sources) == 1 + 28 + 25 + 33 + 6` → `1 + 28 + 26 + 33 + 6`
- en el conjunto de familias agregar `"sic"` tras `"minsalud"`
- en el comentario de fuentes únicas: `25 (fuente única: …, minsalud)` → `26 (fuente única: …, minsalud, sic)` y `= 93` → `= 94`

- [ ] **Step 2: Run seed tests to verify they fail**

Run: `python -m pytest tests/test_seed.py -v`
Expected: FAIL — `assert 28 == 29` (requiere Postgres de dev arriba; si no está, levantar `docker compose up -d db`)

- [ ] **Step 3: Register the source**

En `core/seed.py`, en el diccionario de descripciones (junto a `"minsalud"`):

```python
    "sic": (
        "Superintendencia de Industria y Comercio",
        "Normativa propia (resoluciones, circulares, títulos de la Circular Única "
        "y doctrina) publicada en el buscador de normas de la Superintendencia de "
        "Industria y Comercio",
    ),
```

y tras el `create_source_if_missing` de `minsalud`:

```python
    repository.create_source_if_missing(
        db, family_key="sic", name="Superintendencia de Industria y Comercio", family_params={}
    )
```

- [ ] **Step 4: Run seed tests to verify they pass**

Run: `python -m pytest tests/test_seed.py -v`
Expected: all passed

- [ ] **Step 5: Document the source**

En `docs/guia-despliegue-sistemas.md`, después de la sección de `minsalud` y antes de `### Corte Suprema de Justicia`, agregar (completar los números entre corchetes con los de la corrida del Step 6):

```markdown
### Superintendencia de Industria y Comercio (`sic`)

- **Qué trae:** la normativa propia de la SIC desde su buscador de normas
  (sede electrónica): **Resoluciones** (generales y de carácter particular,
  incluidos los nombramientos), **Circulares** (externas, internas y
  conjuntas), los **Títulos de la Circular Única** (cada versión que se
  republica entra como documento aparte) y la **Doctrina** antigua (conceptos
  y relatorías). Desde 2015.
- **Qué no trae:** proyectos de resolución o circular, normas de otras
  entidades (sólo enlazan a otros sitios), sentencias, informes y actas que el
  buscador clasifica como "doctrina".
- **Cómo quedan nombrados:** `R_SIC_77121_2026`, `C_SIC_0004_2024` (toda
  circular es `C`), `TCU_SIC_X_20260130` (título y fecha de la versión),
  `CTO_SIC_15-159447`, `REL_SIC_27305_2019`. Anexos: `_A01`. Si una circular
  externa y una conjunta tienen el mismo número y año, la segunda entra con el
  título de la página y marca de "sin verificar".
- **Detalle técnico:** el buscador desordena los resultados entre páginas, así
  que la fuente recorre las páginas y luego busca por fragmentos de número
  hasta completar el total que el propio buscador anuncia; si no lo logra,
  lo avisa en el informe ("faltan N"). Cada documento exige abrir su ficha
  (el listado no trae fechas): una corrida diaria abre [N] fichas y tarda
  [M] minutos; la carga completa 2015→hoy, [H] horas.
- **Fuente nueva:** después de actualizar producción hay que correr una vez
  `docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.seed`
  para que aparezca en el listado. Es seguro repetirlo.
```

- [ ] **Step 6: Real run in dev**

Con el entorno de dev arriba (skill `run-iurisync`): reiniciar Celery para que cargue el código nuevo, correr `python -m core.seed`, y lanzar desde la interfaz dos corridas de la fuente "Superintendencia de Industria y Comercio":
1. Rango corto reciente (`2026-09-01` → `2026-10-07`). Verificar: títulos `R_SIC_…`, PDFs abren, sin avisos "faltan".
2. Año completo 2025. Comparar el nº de resoluciones con el total del buscador para 2025 (615 fichas, menos descartadas/sin PDF), anotar duración y nº de fichas abiertas para completar el Step 5.

Revisar el informe de la corrida: ningún "Error" salvo fallas de red puntuales.

- [ ] **Step 7: Full test suite for touched areas**

Run: `python -m pytest tests/families/test_sic.py tests/test_seed.py -v`
Expected: all passed

- [ ] **Step 8: Commit**

```bash
git add core/seed.py tests/test_seed.py docs/guia-despliegue-sistemas.md
git commit -m "feat(sic): registrar la fuente SIC y documentarla"
```
