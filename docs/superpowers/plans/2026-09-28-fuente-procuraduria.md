# Fuente Procuraduría General de la Nación — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar la familia `procuraduria` (fuente "Procuraduría General de la Nación") con dos secciones — Normativa (Relatoría) y Conceptos (SIREL) — que descarga sus documentos con la nomenclatura acordada.

**Architecture:** Un módulo nuevo `core/scrapers/families/procuraduria.py` con funciones puras (nomenclatura, lectura de números, sufijos por choque, lectura de tablas HTML) y una clase `ScrapProcuraduria` que consulta año por año ambos buscadores por `GET` (`requests`), agrupa/deduplica, asigna títulos sobre el año completo y filtra por el rango de la corrida. Se registra en `core/scrapers/families/__init__.py` y `core/seed.py`.

**Tech Stack:** Python 3.14, `requests`, `beautifulsoup4`, `pytest` + `responses` (0.26, `responses.matchers`).

**Spec:** `docs/superpowers/specs/2026-09-28-fuente-procuraduria-design.md`

## Global Constraints

- `family_key="procuraduria"`, nombre de fuente exacto: `"Procuraduría General de la Nación"`, sigla en títulos: `PGN`.
- Piso: documentos con fecha `>= 2015-01-01` (`_ANIO_MIN = 2015`).
- Solo documentos propios: Normativa acepta únicamente enlaces `.webdocumento?accion=verDocumentoRel&relId=…`; URL canónica `https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId={relId}&mode=inline`.
- Conceptos: tipos SIREL `CONCEPTO` y `CONCEPTO (MISIONAL)`; enlace sin el fragmento `#…`.
- Prefijos Normativa: Resolución `R`, Directiva y Directiva Conjunta `DIR`, Circular y Circular Conjunta `C`, Memorando `M`, Carta circular `CCIR`, Instructivo `INS`, Acuerdo `A`, Protocolo `PRO`, Decreto → `codigo_ley_decreto("D", …)`, cualquier otro → `DOC` + aviso.
- Número Normativa: 4 dígitos con ceros; número+letra → `0007A`; con guion → tal cual.
- Conceptos: `CTO_PGN_{consecutivo:07d}_{año}`; sin dígitos → `CTO_PGN_SN{docId}_{año de la fecha}`.
- Choques de título: `_2`, `_3`… ordenados por id interno del sitio ascendente, calculados sobre el año completo consultado.
- **Nunca** intentar resolver o saltar el reCAPTCHA; respuesta sin pie `Resultados … de N` → mensaje con la palabra `Error` (se convierte en error visible de la corrida) y la sección/año sigue con el siguiente.
- TLS válido: **no** usar `verify=False`.
- `doc_id_uses_publication_date = False`; `checks_for_republication` queda en `True` (por defecto).
- Mensajes de progreso con prefijo `[Procuraduría General de la Nación]`; avisos con `Aviso:`, errores con `Error` (el worker solo convierte en error los que contienen "Error").
- Comentarios y mensajes en español, como el resto de familias.

## Review Focus

- Un año donde el sitio responde con la página de bloqueo o pide el reCAPTCHA: se espera un "Error" por ese año y que los demás años/sección sigan (Task 4 y Task 6 lo prueban).
- Correr dos rangos distintos (un mes vs el año completo) debe dar el **mismo título** al mismo documento con choque (Task 5 y Task 6 lo prueban para ambas secciones).
- Enlaces de Normativa "sucios" (host `apps.`, `mode=1#page=inline`, tabulación, URL concatenada 4 veces) deben producir una sola URL canónica `www.` (Task 1).
- Concepto con número irreconocible con dígitos (`SIN 5`, codificación rota): se nombra con el primer grupo de dígitos y deja un aviso, nunca revienta la corrida (Task 2 y Task 6).
- Rango de corrida enteramente anterior a 2015 (o `fini > ffin`): cero peticiones al sitio y lista vacía (Task 7).

---

## File Structure

- **Create** `core/scrapers/families/procuraduria.py` — toda la familia: constantes, funciones puras, consulta paginada, armado de documentos por sección, clase registrada.
- **Create** `tests/families/test_procuraduria.py` — pruebas unitarias y de `scrap()` con `responses`.
- **Modify** `core/scrapers/families/__init__.py` — importar el módulo para que se registre.
- **Modify** `core/seed.py` — familia y fuente nuevas.
- **Modify** `tests/test_seed.py` — conteos fijos (26→27 familias, 23→24 fuentes únicas).
- **Modify** `docs/guia-despliegue-sistemas.md` — sección de la fuente nueva (después de la de `supersolidaria`).

Un solo archivo de familia sigue el patrón de `ssf.py`/`supersolidaria.py` (~400–500 líneas). Las tareas 1–3 construyen las funciones puras, 4 la lectura/consulta HTML, 5–6 el armado por sección, 7 la clase + registro + seed, 8 la documentación y 9 la validación real.

Todas las pruebas se corren con:
`.venv/Scripts/python -m pytest tests/families/test_procuraduria.py -v`
(desde la raíz del repo, en Git Bash).

---

### Task 1: Esqueleto del módulo + nomenclatura de Normativa + URL canónica

**Files:**
- Create: `core/scrapers/families/procuraduria.py`
- Test: `tests/families/test_procuraduria.py`

**Interfaces:**
- Produces:
  - constantes `_SOURCE: str`, `_ANIO_MIN: int`, `_UA: str`, `_RELATORIA: str`, `_OPT_NORMATIVA: str`, `_OPT_SIREL: str`, `_TIPOS_CONCEPTO: tuple[str, str]`, `_PAGINA: int`, `_TIMEOUT: int`
  - `_safe_title(title: str) -> str`
  - `_relid(href: Optional[str]) -> Optional[str]`
  - `_url_normativa(relid: str) -> str`
  - `_id_de_relid(relid: str) -> int` (0 si no decodifica)
  - `_numero_normativa(numero: str) -> str`
  - `_titulo_normativa(tipo: str, numero: str, anio: int, id_interno: int) -> tuple[str, bool]` — `(título, tipo_desconocido)`

- [ ] **Step 1: Write the failing tests**

Crear `tests/families/test_procuraduria.py`:

```python
import datetime

import pytest

from core.scrapers.families.procuraduria import (
    _id_de_relid,
    _numero_normativa,
    _relid,
    _safe_title,
    _titulo_normativa,
    _url_normativa,
)


# ---- URL canónica de Normativa ----
_CANON = "https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId=MjQ0MTg1&mode=inline"


@pytest.mark.parametrize("href", [
    "https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId=MjQ0MTg1&mode=inline",
    "https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId=MjQ0MTg1&mode=inline\t",
    "https://apps.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId=MjQ0MTg1&mode=1#page=inline",
    "https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId=MjQ0MTg1&mode=1#page=inline"
    "https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId=MjQ0MTg1&mode=1#page=inline"
    "https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId=MjQ0MTg1&mode=1#page=inline",
])
def test_url_canonica_desde_todas_las_variantes(href):
    assert _url_normativa(_relid(href)) == _CANON


@pytest.mark.parametrize("href", [
    None,
    "",
    "http://www.secretariasenado.gov.co/senado/basedoc/ley_1712_2014.html",
    "https://dapre.presidencia.gov.co/normativa/normativa/DECRETO%201168%20DEL%2025%20DE%20AGOSTO%20DE%202020.pdf",
    "https://www.procuraduria.gov.co/relatoria/media/file/CDU-2017(2).pdf",
    "*Programa válido únicamente para empleados activos en TP Nicaragua.",
])
def test_relid_none_para_externos_y_texto_suelto(href):
    assert _relid(href) is None


def test_id_de_relid_decodifica_base64():
    assert _id_de_relid("MjQ0MTg1") == 244185
    assert _id_de_relid("Mzg0") == 384


def test_id_de_relid_cero_si_no_decodifica():
    assert _id_de_relid("%%%") == 0


# ---- número de Normativa ----
@pytest.mark.parametrize("crudo,esperado", [
    ("21", "0021"),
    ("338", "0338"),
    ("7A", "0007A"),
    ("34 A", "0034A"),
    ("100-01", "100-01"),
    ("13-4", "13-4"),
    (" 5 ", "0005"),
    ("", ""),
])
def test_numero_normativa(crudo, esperado):
    assert _numero_normativa(crudo) == esperado


# ---- título de Normativa ----
@pytest.mark.parametrize("tipo,numero,anio,esperado", [
    ("Resolución", "338", 2025, "R_PGN_0338_2025"),
    ("Directiva", "21", 2025, "DIR_PGN_0021_2025"),
    ("Directiva Conjunta", "1", 2021, "DIR_PGN_0001_2021"),
    ("Circular", "12", 2025, "C_PGN_0012_2025"),
    ("Circular Conjunta", "100-01", 2016, "C_PGN_100-01_2016"),
    ("Memorando", "2", 2026, "M_PGN_0002_2026"),
    ("Carta Circular", "1", 2026, "CCIR_PGN_0001_2026"),
    ("Instructivo", "3", 2024, "INS_PGN_0003_2024"),
    ("Acuerdo", "1", 2019, "A_PGN_0001_2019"),
    ("Protocolo", "1", 2022, "PRO_PGN_0001_2022"),
    ("Circular", "7A", 2012, "C_PGN_0007A_2012"),
    ("Decreto", "262", 2000, "D0262000"),
])
def test_titulo_normativa(tipo, numero, anio, esperado):
    assert _titulo_normativa(tipo, numero, anio, id_interno=1) == (esperado, False)


def test_titulo_normativa_tipo_desconocido_usa_doc_y_avisa():
    assert _titulo_normativa("Manual", "4", 2020, id_interno=1) == ("DOC_PGN_0004_2020", True)


def test_titulo_normativa_sin_numero_usa_sn_id():
    assert _titulo_normativa("Resolución", "", 2022, id_interno=240116) == ("R_PGN_SN240116_2022", False)


def test_safe_title_reemplaza_caracteres_invalidos():
    assert _safe_title('C_PGN_1/2"3_2016') == "C_PGN_1-2-3_2016"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/families/test_procuraduria.py -v`
Expected: FAIL / ERROR — `ModuleNotFoundError: No module named 'core.scrapers.families.procuraduria'`

- [ ] **Step 3: Write minimal implementation**

Crear `core/scrapers/families/procuraduria.py`:

```python
"""Procuraduría General de la Nación (PGN) — dos secciones de la Relatoría
(apps.procuraduria.gov.co/relatoria). Diseño:
docs/superpowers/specs/2026-09-28-fuente-procuraduria-design.md

- Normativa: buscador de normatividad, consultado año por año (sin año el
  sitio devuelve 0 filas).
- Conceptos: SIREL, tipos CONCEPTO y CONCEPTO (MISIONAL), por rango de fechas
  (se pide el año completo para que los sufijos por choque sean estables).

La página de SharePoint normatividad.aspx es solo un marco vacío; el contenido
real es esta aplicación Java. Ambos buscadores MUESTRAN un reCAPTCHA que el
servidor no exige para los GET de paginación que el propio sitio enlaza. Si
algún día lo exige, la respuesta llega sin el pie "Resultados … de N" y la
sección registra un Error — nunca se intenta resolver ni saltar el reCAPTCHA.
"""
import base64
import datetime
import re
import unicodedata
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

from core.fecha_es import _MESES
from core.models import RawDocModel
from core.naming import codigo_ley_decreto
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_SOURCE = "Procuraduría General de la Nación"
_ANIO_MIN = 2015
# Con el User-Agent por defecto de un navegador sin ventana ("HeadlessChrome")
# www.procuraduria.gov.co responde una página de bloqueo; con uno de Chrome
# normal (o el de requests + este encabezado) responde bien.
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
_RELATORIA = "https://apps.procuraduria.gov.co/relatoria/index.jsp"
_OPT_NORMATIVA = "co.gov.pgn.relatoria.frontend.component.pagefactory.NormatividadPageFactory"
_OPT_SIREL = "co.gov.pgn.relatoria.frontend.component.pagefactory.PirelResolucionesPageFactory"
_TIPOS_CONCEPTO = ("CONCEPTO", "CONCEPTO (MISIONAL)")
# Filas por página pedidas al buscador (max_results). Hoy el año más grande de
# conceptos tiene ~5.800 filas, así que cabe en una sola página; la consulta
# igual pagina por si crece.
_PAGINA = 10000
_TIMEOUT = 300

# Los enlaces propios de Normativa llegan "sucios": host apps. (da 404),
# mode=1#page=inline, tabulación al final, o la URL pegada varias veces. Se toma
# el PRIMER relId y se arma siempre la forma canónica en www. (verificada para
# ids viejos y nuevos, HEAD incluido).
_RELID_RE = re.compile(r"accion=verDocumentoRel&(?:amp;)?relId=([A-Za-z0-9+/=%]+)")
_DOC_REL = "https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId={}&mode=inline"

# Nomenclatura acordada con el equipo de fuentes (clave: tipo del sitio en
# minúsculas y sin acentos). Las conjuntas se pliegan a su tipo base en el
# TÍTULO; el campo `tipo` del documento conserva el nombre original.
_PREFIJOS = {
    "resolucion": "R",
    "directiva": "DIR",
    "directiva conjunta": "DIR",
    "circular": "C",
    "circular conjunta": "C",
    "memorando": "M",
    "carta circular": "CCIR",
    "instructivo": "INS",
    "acuerdo": "A",
    "protocolo": "PRO",
}
_PREFIJO_DESCONOCIDO = "DOC"

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')


def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def _clave_tipo(tipo: str) -> str:
    return " ".join(_sin_acentos(tipo).lower().split())


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _relid(href: Optional[str]) -> Optional[str]:
    m = _RELID_RE.search(href or "")
    return m.group(1) if m else None


def _url_normativa(relid: str) -> str:
    return _DOC_REL.format(relid)


def _id_de_relid(relid: str) -> int:
    """relId es el id numérico del documento en base64 (MjQ0MTg1 -> 244185).
    Se usa solo para ordenar los choques de título; 0 si no decodifica."""
    try:
        crudo = unquote(relid)
        crudo += "=" * (-len(crudo) % 4)
        return int(base64.b64decode(crudo, validate=True).decode("ascii"))
    except Exception:
        return 0


def _numero_normativa(numero: str) -> str:
    n = " ".join((numero or "").split())
    if re.fullmatch(r"\d+", n):
        return f"{int(n):04d}"
    m = re.fullmatch(r"(\d+)\s*([A-Za-z])", n)
    if m:
        return f"{int(m.group(1)):04d}{m.group(2).upper()}"
    return n.replace(" ", "")


def _titulo_normativa(tipo: str, numero: str, anio: int, id_interno: int) -> Tuple[str, bool]:
    """(título, tipo_desconocido). El Decreto usa el código común de
    ministerios (D####YYY, deduplicado entre fuentes en el worker)."""
    clave = _clave_tipo(tipo)
    crudo = (numero or "").strip()
    if clave == "decreto" and re.fullmatch(r"\d+", crudo):
        return codigo_ley_decreto("D", crudo, str(anio)), False
    num = _numero_normativa(crudo) or f"SN{id_interno}"
    prefijo = _PREFIJOS.get(clave)
    if prefijo is None:
        return f"{_PREFIJO_DESCONOCIDO}_PGN_{num}_{anio}", True
    return f"{prefijo}_PGN_{num}_{anio}", False
```

Nota: `datetime`, `Dict`, `List`, `requests`, `BeautifulSoup`, `RawDocModel`, `BaseScrapper`, `register_family`, `storage_path`, `_MESES` se usan en las tareas siguientes; si el linter del proyecto se queja de imports sin uso en este paso intermedio, está bien — no hay linter en CI que bloquee.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/families/test_procuraduria.py -v`
Expected: PASS (todas)

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/procuraduria.py tests/families/test_procuraduria.py
git commit -m "feat(procuraduria): nomenclatura de Normativa y URL canónica de documentos"
```

---

### Task 2: Número, fecha y título de Conceptos

**Files:**
- Modify: `core/scrapers/families/procuraduria.py` (agregar al final)
- Test: `tests/families/test_procuraduria.py` (agregar)

**Interfaces:**
- Consumes: nada de Task 1 salvo el módulo.
- Produces:
  - `_fecha_iso(texto: str) -> Optional[datetime.date]` (Normativa, `AAAA-MM-DD`)
  - `_fecha_sirel(texto: str) -> Optional[datetime.date]` (`jueves, 30 julio 2026`)
  - `_numero_concepto(numero: str, anio_fecha: int) -> Optional[tuple[int, int, bool]]` — `(consecutivo, año, aviso)`; `None` si no hay dígitos
  - `_titulo_concepto(numero: str, fecha: datetime.date, doc_id: str) -> tuple[str, bool]` — `(título, aviso)`

- [ ] **Step 1: Write the failing tests**

Agregar al import de `tests/families/test_procuraduria.py`: `_fecha_iso, _fecha_sirel, _numero_concepto, _titulo_concepto`, y al final:

```python
# ---- fechas ----
def test_fecha_iso():
    assert _fecha_iso("2025-12-19") == datetime.date(2025, 12, 19)
    assert _fecha_iso(" 2025-12-19 ") == datetime.date(2025, 12, 19)


def test_fecha_iso_none():
    assert _fecha_iso("") is None
    assert _fecha_iso("2025-02-30") is None
    assert _fecha_iso("19/12/2025") is None


def test_fecha_sirel_prosa_con_dia_de_semana():
    assert _fecha_sirel("jueves, 30 julio 2026") == datetime.date(2026, 7, 30)
    assert _fecha_sirel("miércoles, 9 septiembre 2026") == datetime.date(2026, 9, 9)
    assert _fecha_sirel("sábado, 12 junio 2010") == datetime.date(2010, 6, 12)


def test_fecha_sirel_none():
    assert _fecha_sirel("") is None
    assert _fecha_sirel("jueves, 31 febrero 2026") is None


# ---- número de concepto ----
@pytest.mark.parametrize("crudo,anio_fecha,esperado", [
    # regla 1: consecutivo + separador + año de 4 dígitos al final
    ("236-2026", 2026, (236, 2026, False)),
    ("004 - 2025", 2025, (4, 2025, False)),
    ("97-2025", 2025, (97, 2025, False)),
    ("119 de 2016", 2016, (119, 2016, False)),
    ("263/2025", 2025, (263, 2025, False)),
    ("CONCEPTO 159 - 2026", 2026, (159, 2026, False)),
    ("Concepto No. 12-2016", 2016, (12, 2016, False)),
    ("concepto No 999 de 2016", 2016, (999, 2016, False)),
    ("C -160-2026", 2026, (160, 2026, False)),
    ("C- 175-2025", 2025, (175, 2025, False)),
    ("236-2026.", 2026, (236, 2026, False)),
    ("123DE 2025", 2025, (123, 2025, False)),
    # regla 2: año de 4 dígitos al inicio
    ("2025-525", 2025, (525, 2025, False)),
    ("2019-430944", 2022, (430944, 2019, False)),
    ("CONCEPTO E-2021-671179", 2026, (671179, 2021, False)),
    # regla 3: año de 2 dígitos al inicio que coincide con la fecha
    ("16-158", 2016, (158, 2016, False)),
    ("CONCEPTO 16-34", 2016, (34, 2016, False)),
    # regla 4: referencia C-/D- o número solo -> año de la fecha
    ("C-6194", 2016, (6194, 2016, False)),
    ("D-1234", 2016, (1234, 2016, False)),
    ("393", 2025, (393, 2025, False)),
    ("Concepto N. 00023", 2016, (23, 2016, False)),
    ("CONCEPTO Nº 061", 2025, (61, 2025, False)),
    # regla 5: cualquier otra cosa con dígitos -> primer grupo + aviso
    ("SIN 5", 2025, (5, 2025, True)),
    ("Concepto Ã¿Â¿Ã¿Â¿ 061", 2025, (61, 2025, False)),
    ("16-158", 2020, (16, 2020, True)),
])
def test_numero_concepto(crudo, anio_fecha, esperado):
    assert _numero_concepto(crudo, anio_fecha) == esperado


@pytest.mark.parametrize("crudo", ["", "   ", "CONCEPTO", "Sin número"])
def test_numero_concepto_none_sin_digitos(crudo):
    assert _numero_concepto(crudo, 2025) is None


def test_numero_concepto_no_toma_anio_fuera_de_rango_como_anio():
    # "2025-1234": 1234 no es un año plausible -> regla 2 (año al inicio)
    assert _numero_concepto("2025-1234", 2025) == (1234, 2025, False)


# ---- título de concepto ----
def test_titulo_concepto_rellena_a_7():
    assert _titulo_concepto("236-2026", datetime.date(2026, 9, 9), "245582") == ("CTO_PGN_0000236_2026", False)


def test_titulo_concepto_mas_de_7_digitos_se_deja():
    assert _titulo_concepto("2019-12345678", datetime.date(2022, 3, 10), "1") == ("CTO_PGN_12345678_2019", False)


def test_titulo_concepto_sin_numero_usa_sn_docid():
    assert _titulo_concepto("", datetime.date(2025, 5, 2), "245408") == ("CTO_PGN_SN245408_2025", False)


def test_titulo_concepto_propaga_aviso():
    assert _titulo_concepto("SIN 5", datetime.date(2025, 5, 2), "9") == ("CTO_PGN_0000005_2025", True)
```

Nota sobre `"Concepto Ã¿Â¿Ã¿Â¿ 061"`: tras quitar "CONCEPTO" y los caracteres raros queda `061` → regla 4 (número solo), sin aviso. Y `"16-158"` con fecha 2020: `16` ≠ `20`, no es regla 3; `16-158` no calza reglas 1, 2 ni 4 → regla 5 (primer grupo `16`, aviso).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/families/test_procuraduria.py -v`
Expected: ERROR — `ImportError: cannot import name '_fecha_iso'`

- [ ] **Step 3: Write minimal implementation**

Agregar al final de `core/scrapers/families/procuraduria.py`:

```python
def _fecha_iso(texto: str) -> Optional[datetime.date]:
    try:
        return datetime.date.fromisoformat((texto or "").strip())
    except ValueError:
        return None


# SIREL escribe la fecha en prosa con el día de la semana y SIN "de":
# "jueves, 30 julio 2026" (core.fecha_es exige "de" antes del año, por eso
# este patrón propio reusa solo su tabla de meses).
_FECHA_SIREL = re.compile(
    r"(\d{1,2})\s+(" + "|".join(_MESES) + r")\s+(?:de\s+)?(\d{4})", re.IGNORECASE
)


def _fecha_sirel(texto: str) -> Optional[datetime.date]:
    m = _FECHA_SIREL.search(texto or "")
    if not m:
        return None
    try:
        return datetime.date(int(m.group(3)), _MESES[m.group(2).lower()], int(m.group(1)))
    except ValueError:
        return None


def _anio_plausible(a: int) -> bool:
    return 1990 <= a <= datetime.date.today().year + 1


def _normalizar_numero_concepto(numero: str) -> str:
    s = unicodedata.normalize("NFC", numero or "").upper()
    s = re.sub(r"\bCONCEPTO\b", " ", s)
    s = re.sub(r"\bN[Oº°]?\s*\.", " ", s)   # "N.", "NO.", "Nº."
    s = re.sub(r"\bN[Oº°]\b", " ", s)       # "NO", "Nº"
    s = re.sub(r"[^A-Z0-9/\- ]", " ", s)    # codificación rota, comillas, puntos
    s = re.sub(r"\s*([/-])\s*", r"\1", s)
    return " ".join(s.split()).strip("-/ ")


_NUM_ANIO_FINAL = re.compile(r"^(?:[A-Z]{1,2}-?)?(\d+)\s*(?:[/-]|DE\b)\s*(\d{4})$")
_NUM_ANIO_INICIAL = re.compile(r"^(?:[A-Z]{1,2}-?)?(\d{4})[/-](\d+)$")
_NUM_ANIO_CORTO = re.compile(r"^(\d{2})[/-](\d+)$")
_NUM_SOLO = re.compile(r"^(?:[A-Z]{1,2}-?)?(\d+)$")


def _numero_concepto(numero: str, anio_fecha: int) -> Optional[Tuple[int, int, bool]]:
    """(consecutivo, año, aviso) según las reglas del diseño; None si el número
    no trae ningún dígito. `aviso` = True cuando se cayó a la regla 5 (se tomó
    el primer grupo de dígitos a ciegas)."""
    s = _normalizar_numero_concepto(numero)
    m = _NUM_ANIO_FINAL.match(s)
    if m and _anio_plausible(int(m.group(2))):
        return int(m.group(1)), int(m.group(2)), False
    m = _NUM_ANIO_INICIAL.match(s)
    if m and _anio_plausible(int(m.group(1))):
        return int(m.group(2)), int(m.group(1)), False
    m = _NUM_ANIO_CORTO.match(s)
    if m and m.group(1) == f"{anio_fecha % 100:02d}":
        return int(m.group(2)), anio_fecha, False
    m = _NUM_SOLO.match(s)
    if m:
        return int(m.group(1)), anio_fecha, False
    m = re.search(r"\d+", s)
    if m:
        return int(m.group(0)), anio_fecha, True
    return None


def _titulo_concepto(numero: str, fecha: datetime.date, doc_id: str) -> Tuple[str, bool]:
    r = _numero_concepto(numero, fecha.year)
    if r is None:
        return f"CTO_PGN_SN{doc_id}_{fecha.year}", False
    consecutivo, anio, aviso = r
    return f"CTO_PGN_{consecutivo:07d}_{anio}", aviso
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/families/test_procuraduria.py -v`
Expected: PASS. Si algún caso parametrizado falla, ajustar la **normalización o el orden de reglas** (no el caso esperado): los esperados vienen de datos reales del sitio y de las reglas aprobadas en el diseño.

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/procuraduria.py tests/families/test_procuraduria.py
git commit -m "feat(procuraduria): lectura de número, fecha y título de conceptos"
```

---

### Task 3: Sufijos por choque de título

**Files:**
- Modify: `core/scrapers/families/procuraduria.py`
- Test: `tests/families/test_procuraduria.py`

**Interfaces:**
- Produces: `_con_sufijos(pares: List[Tuple[str, int]]) -> List[str]` — recibe `(título_base, id_interno)` en cualquier orden y devuelve los títulos finales **en el mismo orden de entrada**.

- [ ] **Step 1: Write the failing tests**

Agregar `_con_sufijos` al import y al final:

```python
# ---- sufijos por choque ----
def test_con_sufijos_sin_choques_no_cambia():
    assert _con_sufijos([("A", 3), ("B", 1)]) == ["A", "B"]


def test_con_sufijos_ordena_por_id_y_conserva_orden_de_entrada():
    pares = [("C_PGN_0001_2023", 300), ("C_PGN_0001_2023", 100), ("X", 5), ("C_PGN_0001_2023", 200)]
    assert _con_sufijos(pares) == ["C_PGN_0001_2023_3", "C_PGN_0001_2023", "X", "C_PGN_0001_2023_2"]


def test_con_sufijos_empate_de_id_desempata_por_posicion():
    assert _con_sufijos([("T", 0), ("T", 0)]) == ["T", "T_2"]


def test_con_sufijos_estable_ante_subconjuntos_con_ids_mayores():
    # el mismo documento (id 100) conserva su título aunque aparezcan otros
    # con ids mayores (documentos nuevos del sitio)
    antes = _con_sufijos([("T", 100)])
    despues = _con_sufijos([("T", 100), ("T", 150)])
    assert antes[0] == despues[0] == "T"
    assert despues[1] == "T_2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/families/test_procuraduria.py -k sufijos -v`
Expected: ERROR — `ImportError: cannot import name '_con_sufijos'`

- [ ] **Step 3: Write minimal implementation**

```python
def _con_sufijos(pares: List[Tuple[str, int]]) -> List[str]:
    """Distingue títulos repetidos (cada dependencia de la PGN numera por su
    cuenta): dentro de cada grupo de títulos iguales, el de menor id interno
    del sitio queda limpio y los siguientes llevan _2, _3… Se llama siempre
    con el AÑO COMPLETO consultado, para que el título de un documento no
    dependa del rango de fechas de la corrida."""
    por_titulo: Dict[str, List[int]] = {}
    for i, (titulo, _) in enumerate(pares):
        por_titulo.setdefault(titulo, []).append(i)
    salida = [titulo for titulo, _ in pares]
    for titulo, indices in por_titulo.items():
        if len(indices) < 2:
            continue
        orden = sorted(indices, key=lambda i: (pares[i][1], i))
        for k, i in enumerate(orden[1:], start=2):
            salida[i] = f"{titulo}_{k}"
    return salida
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/families/test_procuraduria.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/procuraduria.py tests/families/test_procuraduria.py
git commit -m "feat(procuraduria): sufijos _2/_3 para títulos repetidos"
```

---

### Task 4: Lectura de la tabla HTML y consulta paginada

**Files:**
- Modify: `core/scrapers/families/procuraduria.py`
- Test: `tests/families/test_procuraduria.py`

**Interfaces:**
- Produces:
  - `_pie(html: str) -> Optional[int]` — total `M` de `Resultados X - Y de M`; `None` si no hay pie
  - `_filas(html: str) -> List[Tuple[List[str], Optional[str]]]` — `(celdas de texto, href del primer <a> o None)` por cada fila de datos de `table.cms-table`
  - `class _PaginaInesperada(RuntimeError)`
  - `_consultar(session: requests.Session, params: dict) -> List[Tuple[List[str], Optional[str]]]` — pide `_RELATORIA` con `params` + `max_results=_PAGINA` + `first_result`, pagina hasta el total; lanza `_PaginaInesperada` si falta el pie o el conteo no cuadra
- También produce los helpers de prueba `_html_normativa`, `_html_sirel` en el archivo de tests (Tasks 5–7 los usan).

- [ ] **Step 1: Write the failing tests**

Agregar al import: `_PaginaInesperada, _RELATORIA, _consultar, _filas, _pie`, más `import requests`, `import responses`, `from responses import matchers` al inicio del archivo de tests. Luego agregar:

```python
# ---- helpers de HTML con la forma real del sitio ----
def _pie_html(n):
    return (
        '<div align="center"><table class="adminlist"><tr><td nowrap="true" width="48%" align="center">'
        f"                       Resultados {1 if n else 0} - {n} de {n}</td></tr></table></div>"
    )


def _html_normativa(filas, total=None, con_pie=True):
    """filas: (año, tipo, número, temática, corta, larga, fecha, href|None)"""
    trs = []
    for anio, tipo, num, tem, corta, larga, fecha, href in filas:
        tds = "".join(f'<td align="left">\n{c}</td>' for c in (anio, tipo, num, tem, corta, larga, fecha))
        enlace = (
            f'<td>\n<a href="{href}" target="_blank">\n<img src="images/icons/down.png"/>\nVer Documento</a>\n</td>'
            if href else "<td></td>"
        )
        trs.append(f"<tr>\n{tds}{enlace}</tr>")
    n = len(filas) if total is None else total
    encabezado = (
        '<tr><th align="left">A&#241;o</th><th>Tipo Documento</th><th>N&#250;mero</th><th>Tem&#225;tica</th>'
        "<th>Descripci&#243;n Corta</th><th>Descripci&#243;n Larga</th><th>Fecha Documento</th><th></th></tr>"
    )
    return (
        '<html><body><form id="form_process"><table><tr><td>Año</td></tr></table></form>'
        f'<table class="cms-table">{encabezado}{"".join(trs)}</table>'
        f'{_pie_html(n) if con_pie else ""}</body></html>'
    )


def _html_sirel(filas, total=None, con_pie=True):
    """filas: (tipo, número, dependencia, tema, subtema, href, fecha)"""
    trs = []
    for tipo, num, dep, tema, sub, href, fecha in filas:
        trs.append(
            "<tr>"
            + "".join(f'<td align="left">\n{c}</td>' for c in (tipo, num, dep, tema, sub))
            + f'<td>\n<a href="{href}" target="_blank">\n<img src="images/icons/down.png"/>\nDocumento</a>\n</td>'
            + f'<td align="left">\n{fecha}</td></tr>'
        )
    n = len(filas) if total is None else total
    encabezado = (
        "<tr><th>Tipo Documento</th><th>N&#250;mero</th><th>Dependencia</th><th>Tema</th>"
        "<th>Subtema</th><th>Doc.</th><th>Fecha</th></tr>"
    )
    return (
        f'<html><body><form id="form_process"></form><table class="cms-table">{encabezado}{"".join(trs)}</table>'
        f'{_pie_html(n) if con_pie else ""}</body></html>'
    )


_HREF_REL = "https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoRel&relId={}&mode=inline"


def _href_cto(doc_id):
    return (
        "https://www.procuraduria.gov.co/sim/relatoria/.webdocumento?accion=verDocumentoWeb"
        f"&elementId=PRODUCCION/RELATO_DATA_TYPE/2026/08/26/x{doc_id}.docx&docId={doc_id}"
        "&mode=1#page=inline,,toolbar=no,location=no"
    )


# ---- lectura de tabla ----
def test_pie_lee_total():
    assert _pie(_html_normativa([], total=84)) == 84
    assert _pie(_html_normativa([])) == 0


def test_pie_none_sin_pie():
    assert _pie("<html><body>Página Web No Disponible!</body></html>") is None


def test_filas_salta_encabezado_y_devuelve_celdas_y_href():
    html = _html_normativa([
        ("2025", "Directiva", "21", "Funciones de la Entidad", "Ley de Cuotas", "Cumplimiento…", "2025-12-19",
         _HREF_REL.format("MjQ0MTg1")),
        ("2018", "Circular", "7", "Funciones de la Entidad", "Apoyo Consular", "A ciudadanos…", "2018-10-23", None),
    ])
    filas = _filas(html)
    assert len(filas) == 2
    assert filas[0][0][:3] == ["2025", "Directiva", "21"]
    assert filas[0][1] == _HREF_REL.format("MjQ0MTg1")
    assert filas[1][1] is None


def test_filas_vacio_sin_tabla():
    assert _filas("<html><body></body></html>") == []


# ---- consulta paginada ----
def _sesion():
    s = requests.Session()
    s.headers.update({"User-Agent": "x"})
    return s


@responses.activate
def test_consultar_una_pagina():
    html = _html_normativa([("2025", "Circular", "1", "t", "c", "l", "2025-01-02", _HREF_REL.format("MQ=="))])
    responses.add(responses.GET, _RELATORIA, body=html)
    filas = _consultar(_sesion(), {"anio": "2025"})
    assert len(filas) == 1
    q = responses.calls[0].request.url
    assert "anio=2025" in q and "max_results=" in q and "first_result=0" in q


@responses.activate
def test_consultar_pagina_hasta_el_total(monkeypatch):
    import core.scrapers.families.procuraduria as mod
    monkeypatch.setattr(mod, "_PAGINA", 2)
    f = lambda i: ("2025", "Circular", str(i), "t", "c", "l", "2025-01-02", _HREF_REL.format(f"id{i}"))
    responses.add(responses.GET, _RELATORIA, body=_html_normativa([f(1), f(2)], total=3),
                  match=[matchers.query_param_matcher({"first_result": "0"}, strict_match=False)])
    responses.add(responses.GET, _RELATORIA, body=_html_normativa([f(3)], total=3),
                  match=[matchers.query_param_matcher({"first_result": "2"}, strict_match=False)])
    assert [c[2] for c, _ in _consultar(_sesion(), {"anio": "2025"})] == ["1", "2", "3"]


@responses.activate
def test_consultar_vacio_legitimo():
    responses.add(responses.GET, _RELATORIA, body=_html_normativa([]))
    assert _consultar(_sesion(), {"anio": "2027"}) == []


@responses.activate
def test_consultar_sin_pie_es_pagina_inesperada():
    responses.add(responses.GET, _RELATORIA, body="<html><body>Página Web No Disponible!</body></html>")
    with pytest.raises(_PaginaInesperada):
        _consultar(_sesion(), {"anio": "2025"})


@responses.activate
def test_consultar_conteo_que_no_cuadra_es_pagina_inesperada():
    html = _html_normativa([("2025", "Circular", "1", "t", "c", "l", "2025-01-02", _HREF_REL.format("MQ=="))], total=5)
    responses.add(responses.GET, _RELATORIA, body=html)
    with pytest.raises(_PaginaInesperada):
        _consultar(_sesion(), {"anio": "2025"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/families/test_procuraduria.py -v`
Expected: ERROR — `ImportError: cannot import name '_PaginaInesperada'`

- [ ] **Step 3: Write minimal implementation**

```python
_PIE_RE = re.compile(r"Resultados\s+\d+\s*-\s*\d+\s+de\s+(\d+)")


def _pie(html: str) -> Optional[int]:
    m = _PIE_RE.search(html or "")
    return int(m.group(1)) if m else None


def _filas(html: str) -> List[Tuple[List[str], Optional[str]]]:
    soup = BeautifulSoup(html or "", "html.parser")
    tabla = soup.find("table", class_="cms-table")
    if tabla is None:
        return []
    out = []
    for tr in tabla.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:  # fila de encabezado (<th>)
            continue
        a = tr.find("a", href=True)
        out.append(([td.get_text(" ", strip=True) for td in tds], a["href"].strip() if a else None))
    return out


class _PaginaInesperada(RuntimeError):
    pass


def _consultar(session: requests.Session, params: dict) -> List[Tuple[List[str], Optional[str]]]:
    filas: List[Tuple[List[str], Optional[str]]] = []
    primero = 0
    while True:
        resp = session.get(
            _RELATORIA,
            params={**params, "max_results": _PAGINA, "first_result": primero},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        total = _pie(resp.text)
        if total is None:
            raise _PaginaInesperada(
                "la respuesta no trae el pie 'Resultados … de N' "
                "(¿bloqueo, reCAPTCHA exigido o cambio del sitio?)"
            )
        pagina = _filas(resp.text)
        filas.extend(pagina)
        primero += _PAGINA
        if not pagina or len(filas) >= total or primero >= total:
            break
    if len(filas) != total:
        raise _PaginaInesperada(f"se leyeron {len(filas)} filas de {total}")
    return filas
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/families/test_procuraduria.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/procuraduria.py tests/families/test_procuraduria.py
git commit -m "feat(procuraduria): lectura de la tabla de la Relatoría y consulta paginada"
```

---

### Task 5: Sección Normativa — de filas a documentos

**Files:**
- Modify: `core/scrapers/families/procuraduria.py`
- Test: `tests/families/test_procuraduria.py`

**Interfaces:**
- Consumes: `_relid`, `_url_normativa`, `_id_de_relid`, `_titulo_normativa` (Task 1); `_fecha_iso` (Task 2); `_con_sufijos` (Task 3); `_filas`/`_html_normativa`/`_HREF_REL` (Task 4).
- Produces:
  - `_params_normativa(anio: int) -> dict`
  - `_docs_normativa(filas, anio_consulta: int, desde: str, hasta: str, on_progress) -> List[RawDocModel]` — `desde`/`hasta` en ISO; `desde` ya viene recortado al piso 2015.

- [ ] **Step 1: Write the failing tests**

Agregar al import: `_docs_normativa, _params_normativa`, y:

```python
# ---- sección Normativa ----
def _fn(anio, tipo, num, fecha, relid, corta="Corta", larga="Larga", tem="Funciones de la Entidad"):
    return (anio, tipo, num, tem, corta, larga, fecha, _HREF_REL.format(relid) if relid else None)


def _b64(n):
    import base64
    return base64.b64encode(str(n).encode()).decode()


def test_params_normativa():
    p = _params_normativa(2025)
    assert p["anio"] == "2025" and p["action"] == "consultar_normatividad"
    assert p["option"].endswith("NormatividadPageFactory")


def test_docs_normativa_campos_basicos():
    filas = _filas(_html_normativa([_fn("2025", "Directiva", "21", "2025-12-19", _b64(244185),
                                        corta="Ley de Cuotas", larga="Cumplimiento de la ley 581")]))
    [d] = _docs_normativa(filas, 2025, "2015-01-01", "2025-12-31", None)
    assert d.title == "DIR_PGN_0021_2025"
    assert d.tipo == "Directiva"
    assert d.seccion == "Normativa"
    assert d.f_public == d.f_providencia == "2025-12-19"
    assert d.link == {"url": _HREF_REL.format(_b64(244185)), "method": "GET"}
    assert d.detalle == "Ley de Cuotas — Cumplimiento de la ley 581 (Funciones de la Entidad)"
    assert d.source == "Procuraduría General de la Nación"
    assert d.save_path == "Procuraduría General de la Nación/2025-12-19/Directiva/DIR_PGN_0021_2025(extension)"


def test_docs_normativa_descarta_externos_y_sin_enlace():
    html = _html_normativa([
        ("2020", "Ley", "2016", "Normas Generales", "c", "l", "2020-02-27",
         "http://www.secretariasenado.gov.co/senado/basedoc/ley_2016_2020.html"),
        ("2018", "Circular", "7", "t", "c", "l", "2018-10-23", None),
    ])
    assert _docs_normativa(_filas(html), 2020, "2015-01-01", "2026-12-31", None) == []


def test_docs_normativa_repetido_por_relid_entra_una_vez_prefiriendo_fila_con_fecha():
    html = _html_normativa([
        _fn("2022", "Resolución", "413", "", _b64(240116)),
        _fn("2022", "Resolución", "413", "2022-12-07", _b64(240116)),
    ])
    [d] = _docs_normativa(_filas(html), 2022, "2015-01-01", "2022-12-31", None)
    assert d.f_public == "2022-12-07"


def test_docs_normativa_sin_fecha_usa_1_de_enero_del_anio_de_la_columna():
    html = _html_normativa([_fn("2022", "Resolución", "9", "", _b64(5))])
    avisos = []
    [d] = _docs_normativa(_filas(html), 2022, "2015-01-01", "2022-12-31", avisos.append)
    assert d.f_public == "2022-01-01"
    assert any("Aviso" in a for a in avisos)


def test_docs_normativa_anio_del_titulo_sale_de_la_fecha_no_de_la_columna():
    html = _html_normativa([_fn("2024", "Protocolo", "1", "2022-12-22", _b64(7))])
    [d] = _docs_normativa(_filas(html), 2024, "2015-01-01", "2024-12-31", None)
    assert d.title == "PRO_PGN_0001_2022"


def test_docs_normativa_choques_con_sufijo_por_id():
    html = _html_normativa([
        _fn("2023", "Circular", "1", "2023-01-23", _b64(300)),
        _fn("2023", "Circular", "1", "2023-01-12", _b64(100)),
        _fn("2023", "Circular Conjunta", "1", "2023-01-06", _b64(200)),
    ])
    docs = _docs_normativa(_filas(html), 2023, "2015-01-01", "2023-12-31", None)
    por_fecha = {d.f_public: d.title for d in docs}
    assert por_fecha == {
        "2023-01-12": "C_PGN_0001_2023",
        "2023-01-06": "C_PGN_0001_2023_2",
        "2023-01-23": "C_PGN_0001_2023_3",
    }
    tipos = {d.f_public: d.tipo for d in docs}
    assert tipos["2023-01-06"] == "Circular Conjunta"


def test_docs_normativa_sufijo_estable_con_rango_corto():
    html = _html_normativa([
        _fn("2023", "Circular", "1", "2023-01-23", _b64(300)),
        _fn("2023", "Circular", "1", "2023-01-12", _b64(100)),
    ])
    [d] = _docs_normativa(_filas(html), 2023, "2023-01-20", "2023-01-31", None)
    assert d.title == "C_PGN_0001_2023_2"


def test_docs_normativa_filtra_por_rango_y_piso():
    html = _html_normativa([
        _fn("2020", "Resolución", "122", "2018-09-24", _b64(1)),   # fuera del rango pedido
        _fn("2020", "Resolución", "60", "2014-04-08", _b64(2)),    # antes del piso
        _fn("2020", "Resolución", "5", "2020-03-01", _b64(3)),
    ])
    docs = _docs_normativa(_filas(html), 2020, "2020-01-01", "2020-12-31", None)
    assert [d.title for d in docs] == ["R_PGN_0005_2020"]


def test_docs_normativa_tipo_desconocido_avisa():
    avisos = []
    html = _html_normativa([_fn("2021", "Manual", "4", "2021-05-05", _b64(9))])
    [d] = _docs_normativa(_filas(html), 2021, "2015-01-01", "2021-12-31", avisos.append)
    assert d.title == "DOC_PGN_0004_2021"
    assert any("Aviso" in a and "Manual" in a for a in avisos)
    assert not any("Error" in a for a in avisos)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/families/test_procuraduria.py -k normativa -v`
Expected: ERROR — `ImportError: cannot import name '_docs_normativa'`

- [ ] **Step 3: Write minimal implementation**

```python
def _avisar(on_progress, mensaje: str) -> None:
    if on_progress:
        on_progress(f"[{_SOURCE}] {mensaje}")


def _params_normativa(anio: int) -> dict:
    return {
        "option": _OPT_NORMATIVA,
        "action": "consultar_normatividad",
        "anio": str(anio),
        "tematica": "",
        "numero": "",
        "tipo": "",
        "descripcion_corta": "",
        "descripcion_larga": "",
        "fecha_documento": "",
    }


def _armar(titulo: str, tipo: str, seccion: str, fecha: datetime.date, url: str, detalle: Optional[str]) -> RawDocModel:
    iso = fecha.isoformat()
    return RawDocModel(
        source=_SOURCE,
        link={"url": url, "method": "GET"},
        title=titulo,
        tipo=tipo,
        f_public=iso,
        f_providencia=iso,
        seccion=seccion,
        detalle=detalle or None,
        save_path=storage_path(_SOURCE, iso, tipo, f"{_safe_title(titulo)}(extension)"),
    )


def _docs_normativa(filas, anio_consulta: int, desde: str, hasta: str, on_progress) -> List[RawDocModel]:
    # 1) solo documentos propios (verDocumentoRel), deduplicados por relId,
    #    prefiriendo la fila que sí trae fecha
    por_relid: Dict[str, dict] = {}
    for celdas, href in filas:
        if len(celdas) < 7:
            continue
        relid = _relid(href)
        if relid is None:  # sin enlace, o norma de otra entidad (Senado, Presidencia…)
            continue
        anio_col, tipo, numero, tematica, corta, larga, fecha_txt = celdas[:7]
        fila = {
            "anio_col": anio_col, "tipo": tipo, "numero": numero, "tematica": tematica,
            "corta": corta, "larga": larga, "fecha": _fecha_iso(fecha_txt),
        }
        previa = por_relid.get(relid)
        if previa is None or (previa["fecha"] is None and fila["fecha"] is not None):
            por_relid[relid] = fila

    # 2) fecha (o 1 de enero del año del listado) y título base
    base = []
    for relid, f in por_relid.items():
        fecha = f["fecha"]
        if fecha is None:
            anio = int(f["anio_col"]) if f["anio_col"].isdigit() else anio_consulta
            fecha = datetime.date(anio, 1, 1)
            _avisar(on_progress, f"Aviso: {f['tipo']} {f['numero']} sin fecha en Normativa, se usa {fecha.isoformat()}")
        titulo, desconocido = _titulo_normativa(f["tipo"], f["numero"], fecha.year, _id_de_relid(relid))
        if desconocido:
            _avisar(on_progress, f"Aviso: tipo desconocido «{f['tipo']}» en Normativa, se guarda como {titulo}")
        base.append((relid, f, fecha, titulo))

    # 3) sufijos sobre el año completo, y recién después el filtro por rango
    titulos = _con_sufijos([(titulo, _id_de_relid(relid)) for relid, _, _, titulo in base])
    docs = []
    for (relid, f, fecha, _), titulo in zip(base, titulos):
        iso = fecha.isoformat()
        if iso < desde or iso > hasta:
            continue
        detalle = " — ".join(x for x in (f["corta"], f["larga"]) if x)
        if f["tematica"]:
            detalle = f"{detalle} ({f['tematica']})" if detalle else f["tematica"]
        docs.append(_armar(titulo, f["tipo"], "Normativa", fecha, _url_normativa(relid), detalle))
    return docs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/families/test_procuraduria.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/procuraduria.py tests/families/test_procuraduria.py
git commit -m "feat(procuraduria): sección Normativa (filtro de externos, dedup, títulos y rango)"
```

---

### Task 6: Sección Conceptos — de filas a documentos

**Files:**
- Modify: `core/scrapers/families/procuraduria.py`
- Test: `tests/families/test_procuraduria.py`

**Interfaces:**
- Consumes: `_fecha_sirel`, `_titulo_concepto` (Task 2); `_con_sufijos` (Task 3); `_filas`/`_html_sirel`/`_href_cto` (Task 4); `_avisar`, `_armar` (Task 5).
- Produces:
  - `_params_conceptos(tipo: str, desde: str, hasta: str) -> dict`
  - `_docs_conceptos(filas, anio_consulta: int, desde: str, hasta: str, on_progress) -> List[RawDocModel]`

- [ ] **Step 1: Write the failing tests**

Agregar al import: `_docs_conceptos, _params_conceptos`, y:

```python
# ---- sección Conceptos ----
_DEP = "PROCURADURIA DELEGADA DE INTERVENCION 11: SEPTIMA ANTE EL CONSEJO DE ESTADO"


def _fc(num, doc_id, fecha, tema="VICTIMA", sub="Sub", tipo="CONCEPTO (MISIONAL)", dep=_DEP):
    return (tipo, num, dep, tema, sub, _href_cto(doc_id), fecha)


def test_params_conceptos():
    p = _params_conceptos("CONCEPTO (MISIONAL)", "2025-01-01", "2025-12-31")
    assert p["tipo_documento"] == "CONCEPTO (MISIONAL)"
    assert p["fecha_inicial"] == "2025-01-01" and p["fecha_final"] == "2025-12-31"
    assert p["action"] == "consultar_area"
    assert p["option"].endswith("PirelResolucionesPageFactory")


def test_docs_conceptos_agrupa_filas_por_tema():
    html = _html_sirel([
        _fc("236-2026", "245582", "miércoles, 9 septiembre 2026", tema="VICTIMA", sub="Verdad"),
        _fc("236-2026", "245582", "miércoles, 9 septiembre 2026", tema="PRUEBAS", sub="Valoración"),
        _fc("236-2026", "245582", "miércoles, 9 septiembre 2026", tema="PRUEBAS", sub="Valoración"),
    ])
    [d] = _docs_conceptos(_filas(html), 2026, "2015-01-01", "2026-12-31", None)
    assert d.title == "CTO_PGN_0000236_2026"
    assert d.tipo == "Concepto"
    assert d.seccion == "Conceptos"
    assert d.f_public == "2026-09-09"
    assert d.link["url"] == _href_cto("245582").split("#")[0]
    assert d.detalle == f"{_DEP}; VICTIMA: Verdad; PRUEBAS: Valoración"
    assert d.save_path == "Procuraduría General de la Nación/2026-09-09/Concepto/CTO_PGN_0000236_2026(extension)"


def test_docs_conceptos_sin_numero_usa_sn_docid():
    html = _html_sirel([_fc("", "245408", "jueves, 30 julio 2026")])
    [d] = _docs_conceptos(_filas(html), 2026, "2015-01-01", "2026-12-31", None)
    assert d.title == "CTO_PGN_SN245408_2026"


def test_docs_conceptos_choques_entre_dependencias_con_sufijo_por_docid():
    html = _html_sirel([
        _fc("186-2025", "243000", "lunes, 10 marzo 2025", dep="DELEGADA A"),
        _fc("186-2025", "242000", "miércoles, 2 abril 2025", dep="DELEGADA B"),
    ])
    docs = _docs_conceptos(_filas(html), 2025, "2015-01-01", "2025-12-31", None)
    assert {d.f_public: d.title for d in docs} == {
        "2025-04-02": "CTO_PGN_0000186_2025",
        "2025-03-10": "CTO_PGN_0000186_2025_2",
    }


def test_docs_conceptos_sufijo_estable_con_rango_corto():
    html = _html_sirel([
        _fc("186-2025", "243000", "lunes, 10 marzo 2025"),
        _fc("186-2025", "242000", "miércoles, 2 abril 2025"),
    ])
    [d] = _docs_conceptos(_filas(html), 2025, "2025-03-01", "2025-03-31", None)
    assert d.title == "CTO_PGN_0000186_2025_2"


def test_docs_conceptos_fecha_ilegible_usa_1_de_enero_y_avisa():
    avisos = []
    html = _html_sirel([_fc("5-2025", "1", "sin fecha")])
    [d] = _docs_conceptos(_filas(html), 2025, "2015-01-01", "2025-12-31", avisos.append)
    assert d.f_public == "2025-01-01"
    assert any("Aviso" in a for a in avisos)


def test_docs_conceptos_numero_raro_avisa_sin_error():
    avisos = []
    html = _html_sirel([_fc("SIN 5", "2", "lunes, 10 marzo 2025")])
    [d] = _docs_conceptos(_filas(html), 2025, "2015-01-01", "2025-12-31", avisos.append)
    assert d.title == "CTO_PGN_0000005_2025"
    assert any("Aviso" in a and "SIN 5" in a for a in avisos)
    assert not any("Error" in a for a in avisos)


def test_docs_conceptos_ignora_filas_sin_docid():
    html = _html_sirel([("CONCEPTO", "1-2025", _DEP, "T", "S", "https://otro.sitio/x.pdf", "lunes, 10 marzo 2025")])
    assert _docs_conceptos(_filas(html), 2025, "2015-01-01", "2025-12-31", None) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/families/test_procuraduria.py -k conceptos -v`
Expected: ERROR — `ImportError: cannot import name '_docs_conceptos'`

- [ ] **Step 3: Write minimal implementation**

```python
_DOCID_RE = re.compile(r"[?&]docId=(\d+)")


def _params_conceptos(tipo: str, desde: str, hasta: str) -> dict:
    return {
        "option": _OPT_SIREL,
        "action": "consultar_area",
        "tipo_documento": tipo,
        "numero": "",
        "dependencia": "",
        "palabra_clave": "",
        "fecha_inicial": desde,
        "fecha_final": hasta,
    }


def _docs_conceptos(filas, anio_consulta: int, desde: str, hasta: str, on_progress) -> List[RawDocModel]:
    # SIREL repite cada concepto una vez por tema/subtema: se agrupa por docId
    grupos: Dict[str, dict] = {}
    for celdas, href in filas:
        if len(celdas) < 7 or not href:
            continue
        m = _DOCID_RE.search(href)
        if not m:
            continue
        doc_id = m.group(1)
        _tipo, numero, dependencia, tema, subtema, _doc, fecha_txt = celdas[:7]
        g = grupos.get(doc_id)
        if g is None:
            g = grupos[doc_id] = {
                "numero": numero, "dependencia": dependencia, "fecha_txt": fecha_txt,
                "url": href.split("#", 1)[0].strip(), "temas": [],
            }
        par = f"{tema}: {subtema}" if tema and subtema else (tema or subtema)
        if par and par not in g["temas"]:
            g["temas"].append(par)

    base = []
    for doc_id, g in grupos.items():
        fecha = _fecha_sirel(g["fecha_txt"])
        if fecha is None:
            fecha = datetime.date(anio_consulta, 1, 1)
            _avisar(on_progress, f"Aviso: concepto {g['numero'] or doc_id} con fecha ilegible «{g['fecha_txt']}», se usa {fecha.isoformat()}")
        titulo, aviso = _titulo_concepto(g["numero"], fecha, doc_id)
        if aviso:
            _avisar(on_progress, f"Aviso: número de concepto poco claro «{g['numero']}», se nombra {titulo}")
        base.append((doc_id, g, fecha, titulo))

    titulos = _con_sufijos([(titulo, int(doc_id)) for doc_id, _, _, titulo in base])
    docs = []
    for (doc_id, g, fecha, _), titulo in zip(base, titulos):
        iso = fecha.isoformat()
        if iso < desde or iso > hasta:
            continue
        detalle = "; ".join(x for x in [g["dependencia"], *g["temas"]] if x)
        docs.append(_armar(titulo, "Concepto", "Conceptos", fecha, g["url"], detalle))
    return docs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/families/test_procuraduria.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/procuraduria.py tests/families/test_procuraduria.py
git commit -m "feat(procuraduria): sección Conceptos (agrupación por tema, títulos y rango)"
```

---

### Task 7: Clase `ScrapProcuraduria`, registro y seed

**Files:**
- Modify: `core/scrapers/families/procuraduria.py`
- Modify: `core/scrapers/families/__init__.py`
- Modify: `core/seed.py`
- Modify: `tests/test_seed.py`
- Test: `tests/families/test_procuraduria.py`

**Interfaces:**
- Consumes: `_consultar`, `_PaginaInesperada` (Task 4); `_params_normativa`, `_docs_normativa`, `_avisar` (Task 5); `_params_conceptos`, `_docs_conceptos` (Task 6).
- Produces: `ScrapProcuraduria` registrada como `"procuraduria"`, con `scrap(self, fini, ffin, q="", limit=100000, stop_event=None, on_progress=None) -> List[RawDocModel]`.

- [ ] **Step 1: Write the failing tests**

Agregar al final de `tests/families/test_procuraduria.py`:

```python
# ---- scrap() completo ----
import threading

from core.scrapers.families.procuraduria import ScrapProcuraduria
from core.scrapers.registry import FAMILY_REGISTRY


def _registrar_normativa(anio, html):
    responses.add(responses.GET, _RELATORIA, body=html, match=[
        matchers.query_param_matcher({"action": "consultar_normatividad", "anio": str(anio)}, strict_match=False)
    ])


def _registrar_conceptos(tipo, anio, html):
    responses.add(responses.GET, _RELATORIA, body=html, match=[
        matchers.query_param_matcher(
            {"action": "consultar_area", "tipo_documento": tipo,
             "fecha_inicial": f"{anio}-01-01", "fecha_final": f"{anio}-12-31"},
            strict_match=False,
        )
    ])


def test_procuraduria_registrada():
    import core.scrapers.families  # noqa: F401
    assert FAMILY_REGISTRY["procuraduria"].__name__ == "ScrapProcuraduria"


def test_identidad_no_usa_fecha_y_revisa_republicacion():
    assert ScrapProcuraduria.doc_id_uses_publication_date is False
    assert ScrapProcuraduria.checks_for_republication is True


@responses.activate
def test_scrap_un_anio_ambas_secciones():
    _registrar_normativa(2025, _html_normativa([_fn("2025", "Resolución", "338", "2025-11-21", _b64(244004))]))
    _registrar_conceptos("CONCEPTO", 2025, _html_sirel([]))
    _registrar_conceptos("CONCEPTO (MISIONAL)", 2025, _html_sirel([_fc("97-2025", "243100", "martes, 18 noviembre 2025")]))
    docs = ScrapProcuraduria().scrap(fini="2025-11-01", ffin="2025-11-30")
    assert sorted(d.title for d in docs) == ["CTO_PGN_0000097_2025", "R_PGN_0338_2025"]
    assert {d.seccion for d in docs} == {"Normativa", "Conceptos"}


@responses.activate
def test_scrap_varios_anios():
    for anio in (2024, 2025):
        _registrar_normativa(anio, _html_normativa([_fn(str(anio), "Circular", "1", f"{anio}-06-01", _b64(anio))]))
        _registrar_conceptos("CONCEPTO", anio, _html_sirel([]))
        _registrar_conceptos("CONCEPTO (MISIONAL)", anio, _html_sirel([]))
    docs = ScrapProcuraduria().scrap(fini="2024-01-01", ffin="2025-12-31")
    assert sorted(d.title for d in docs) == ["C_PGN_0001_2024", "C_PGN_0001_2025"]


@responses.activate
def test_scrap_recorta_al_piso_2015():
    _registrar_normativa(2015, _html_normativa([_fn("2015", "Resolución", "1", "2015-03-03", _b64(1))]))
    _registrar_conceptos("CONCEPTO", 2015, _html_sirel([]))
    _registrar_conceptos("CONCEPTO (MISIONAL)", 2015, _html_sirel([]))
    docs = ScrapProcuraduria().scrap(fini="2010-01-01", ffin="2015-12-31")
    assert [d.title for d in docs] == ["R_PGN_0001_2015"]
    # solo se consultó 2015 (1 Normativa + 2 Conceptos)
    assert len(responses.calls) == 3


@responses.activate
def test_scrap_rango_antes_del_piso_no_consulta_nada():
    assert ScrapProcuraduria().scrap(fini="2010-01-01", ffin="2014-12-31") == []
    assert len(responses.calls) == 0


@responses.activate
def test_scrap_anio_bloqueado_registra_error_y_sigue():
    _registrar_normativa(2024, "<html><body>Página Web No Disponible!</body></html>")
    _registrar_normativa(2025, _html_normativa([_fn("2025", "Circular", "3", "2025-02-02", _b64(3))]))
    for anio in (2024, 2025):
        _registrar_conceptos("CONCEPTO", anio, _html_sirel([]))
        _registrar_conceptos("CONCEPTO (MISIONAL)", anio, _html_sirel([_fc(f"1-{anio}", str(anio), f"lunes, 3 marzo {anio}")]))
    mensajes = []
    docs = ScrapProcuraduria().scrap(fini="2024-01-01", ffin="2025-12-31", on_progress=mensajes.append)
    assert sorted(d.title for d in docs) == ["CTO_PGN_0000001_2024", "CTO_PGN_0000001_2025", "C_PGN_0003_2025"]
    errores = [m for m in mensajes if "Error" in m]
    assert len(errores) == 1 and "Normativa 2024" in errores[0]


@responses.activate
def test_scrap_conceptos_bloqueado_registra_error_y_no_pierde_normativa():
    _registrar_normativa(2025, _html_normativa([_fn("2025", "Circular", "3", "2025-02-02", _b64(3))]))
    _registrar_conceptos("CONCEPTO", 2025, "<html>reCAPTCHA</html>")
    _registrar_conceptos("CONCEPTO (MISIONAL)", 2025, _html_sirel([_fc("1-2025", "9", "lunes, 3 marzo 2025")]))
    mensajes = []
    docs = ScrapProcuraduria().scrap(fini="2025-01-01", ffin="2025-12-31", on_progress=mensajes.append)
    assert [d.title for d in docs] == ["C_PGN_0003_2025"]
    assert any("Error" in m and "Conceptos 2025" in m for m in mensajes)


@responses.activate
def test_scrap_respeta_stop_event():
    ev = threading.Event()
    ev.set()
    assert ScrapProcuraduria().scrap(fini="2025-01-01", ffin="2025-12-31", stop_event=ev) == []
    assert len(responses.calls) == 0
```

En `tests/test_seed.py`, cambiar las tres aserciones de conteo y el conjunto de claves:
- `assert len(families) == 26` → `assert len(families) == 27`
- ambas `assert len(sources) == 1 + 28 + 23 + 33 + 6` → `assert len(sources) == 1 + 28 + 24 + 33 + 6`
- en el conjunto `{... "supersociedades", "supersolidaria",}` agregar `"procuraduria",`
- en el comentario "23 (fuente única: …supersolidaria)" → "24 (fuente única: …supersolidaria, procuraduria)" y "= 91" → "= 92".

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/families/test_procuraduria.py -v`
Expected: ERROR — `ImportError: cannot import name 'ScrapProcuraduria'`

- [ ] **Step 3: Write minimal implementation**

Agregar al final de `core/scrapers/families/procuraduria.py`:

```python
@register_family("procuraduria")
class ScrapProcuraduria(BaseScrapper):
    # relId / docId son estables y la fecha del sitio se ha visto corregida
    # entre listados: la identidad es solo el enlace canónico.
    doc_id_uses_publication_date = False

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=100000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        docs: List[RawDocModel] = []
        desde = max(fini, f"{_ANIO_MIN}-01-01")
        if desde > ffin:
            return docs
        anios = range(int(desde[:4]), int(ffin[:4]) + 1)
        session = requests.Session()
        session.headers.update({"User-Agent": _UA})

        def parar() -> bool:
            return stop_event is not None and stop_event.is_set()

        for anio in anios:
            if parar():
                return docs[:limit]
            _avisar(on_progress, f"Procesando Normativa {anio}...")
            try:
                filas = _consultar(session, _params_normativa(anio))
            except Exception as e:
                _avisar(on_progress, f"Error consultando Normativa {anio}: {e}")
                continue
            docs.extend(_docs_normativa(filas, anio, desde, ffin, on_progress))

        for anio in anios:
            if parar():
                return docs[:limit]
            _avisar(on_progress, f"Procesando Conceptos {anio}...")
            try:
                filas = []
                for tipo in _TIPOS_CONCEPTO:
                    filas.extend(_consultar(session, _params_conceptos(tipo, f"{anio}-01-01", f"{anio}-12-31")))
            except Exception as e:
                _avisar(on_progress, f"Error consultando Conceptos {anio}: {e}")
                continue
            docs.extend(_docs_conceptos(filas, anio, desde, ffin, on_progress))

        return docs[:limit]
```

En `core/scrapers/families/__init__.py`, agregar `procuraduria` al final de la lista de imports:

```python
from . import constitucional, samai, corte_suprema, jep, cndj, adr, adres, ane, anh, rama_judicial, mincit, madr, minambiente, minvivienda, mineducacion, mininterior, mindeporte, minjusticia, minenergia, mintrabajo, superfinanciera, supersalud, ssf, snr, supersociedades, supersolidaria, procuraduria  # noqa: F401
```

En `core/seed.py`, agregar al diccionario `_FAMILIES` (después de `"supersolidaria"`):

```python
    "procuraduria": (
        "Procuraduría General de la Nación",
        "Normativa (resoluciones, directivas, circulares, memorandos…) y "
        "conceptos publicados por la Procuraduría General de la Nación",
    ),
```

y al final de `seed_source_families_and_sources` (después del bloque de `supersolidaria`):

```python
    repository.create_source_if_missing(
        db, family_key="procuraduria", name="Procuraduría General de la Nación", family_params={}
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/families/test_procuraduria.py tests/test_registry.py -v`
Expected: PASS

Run (suite de base de datos, dirigida — no correr la suite pesada completa en paralelo): `.venv/Scripts/python -m pytest tests/test_seed.py -v`
Expected: PASS (requiere Docker con Postgres arriba y la base `iurisync_test`)

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/procuraduria.py core/scrapers/families/__init__.py core/seed.py tests/families/test_procuraduria.py tests/test_seed.py
git commit -m "feat(procuraduria): registrar la familia y la fuente Procuraduría General de la Nación"
```

---

### Task 8: Documentación de despliegue

**Files:**
- Modify: `docs/guia-despliegue-sistemas.md` (nueva sección después de la de `supersolidaria`, antes del siguiente `###`/`##` o al final de esa lista de fuentes)

- [ ] **Step 1: Agregar la sección**

```markdown
### Procuraduría General de la Nación (`procuraduria`)

- **Qué trae:** dos secciones de la Relatoría de la Procuraduría
  (`apps.procuraduria.gov.co/relatoria`) — **Normativa** (resoluciones,
  directivas, circulares, memorandos, instructivos…) y **Conceptos** (SIREL,
  tipos "CONCEPTO" y "CONCEPTO (MISIONAL)"). La página de SharePoint
  `normatividad.aspx` es solo un marco vacío; el contenido real es esa
  aplicación.
- **Qué no trae:** los enlaces de Normativa que apuntan a normas de otras
  entidades (leyes en la página del Senado, decretos de Presidencia,
  resoluciones de MinSalud…) — solo los documentos alojados por la
  Procuraduría.
- **Desde cuándo:** año 2015 en adelante.
- **Cuánto entrega hoy:** unos 537 documentos de Normativa y unos 8.000–9.000
  conceptos (≈600–800 por año). La primera corrida completa de conceptos es
  larga; las siguientes solo traen lo nuevo.
- **Cómo quedan nombrados:** `R_PGN_0338_2025` (resolución), `DIR_PGN_0021_2025`
  (directiva y directiva conjunta), `C_PGN_0012_2025` (circular y circular
  conjunta), `M_PGN_0002_2026` (memorando), `CCIR_…` (carta circular),
  `INS_…` (instructivo), `A_…` (acuerdo), `PRO_…` (protocolo); el decreto usa
  el código común de ministerios (`D0262000`). Conceptos:
  `CTO_PGN_0000236_2026` (consecutivo a 7 dígitos + año); sin número:
  `CTO_PGN_SN245408_2025` (número interno de SIREL). Cada dependencia numera
  por su cuenta, así que cuando dos documentos distintos dan el mismo nombre
  los siguientes llevan `_2`, `_3` (el más antiguo en el sistema de la
  Procuraduría queda sin sufijo).
- **Ojo:** ambos buscadores muestran un reCAPTCHA que hoy el servidor no
  exige para las consultas que usa la fuente. Si algún día lo exige, la
  corrida mostrará errores "Error consultando Normativa/Conceptos …" con 0
  documentos: en ese caso **se pausa la fuente** (no se intenta saltar el
  reCAPTCHA).
- **Detalle técnico:** certificado válido (sin saltarse la validación). Los
  enlaces de Normativa que el sitio publica en `apps.procuraduria.gov.co`
  dan error; la fuente los descarga siempre desde `www.procuraduria.gov.co`.
  Los conceptos llegan en Word (.doc/.docx).
- **Fuente nueva:** después de actualizar producción, correr una vez
  `docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.seed`.
  Es seguro repetirlo.
```

- [ ] **Step 2: Commit**

```bash
git add docs/guia-despliegue-sistemas.md
git commit -m "docs: fuente Procuraduría General de la Nación en la guía de despliegue"
```

---

### Task 9: Validación real en desarrollo

No es TDD: es la verificación contra el sitio real, con el entorno de desarrollo arriba (Docker, uvicorn :8000, Celery `--pool=solo`, Vite :5173).

- [ ] **Step 1: Registrar la fuente y reiniciar Celery**

```bash
.venv/Scripts/python -m core.seed
```
Reiniciar el worker de Celery (no recarga código solo): detener el proceso `celery -A worker.celery_app worker` y volver a lanzarlo con
`.venv/Scripts/python -m celery -A worker.celery_app worker --pool=solo --loglevel=info`.

- [ ] **Step 2: Prueba directa del scraper (sin descargar), un mes**

```bash
.venv/Scripts/python - <<'EOF'
from collections import Counter
from core.scrapers.families.procuraduria import ScrapProcuraduria
msgs = []
docs = ScrapProcuraduria().scrap("2025-12-01", "2025-12-31", on_progress=msgs.append)
print(len(docs), Counter(d.seccion for d in docs))
print([m for m in msgs if "Error" in m or "Aviso" in m][:20])
for d in docs[:15]: print(d.title, d.tipo, d.f_public, d.link["url"][:90])
print("repetidos:", [t for t, n in Counter(d.title for d in docs).items() if n > 1])
EOF
```
Expected: decenas de documentos (Normativa de diciembre 2025 ≈ 10–15; conceptos ≈ 60–90), **0 mensajes "Error"**, **0 títulos repetidos**, URLs `www.procuraduria.gov.co/…verDocumentoRel…mode=inline` y `…verDocumentoWeb…docId=…` sin `#`.

- [ ] **Step 3: Corrida real por la aplicación**

Con el driver del skill `run-iurisync`:
```bash
cd .claude/skills/run-iurisync
node driver.mjs flow "smoke-test" "SmokeTest123" "Procuraduría General de la Nación" "2025-12-01" "2025-12-31"
```
(El driver espera 60 s; si la corrida sigue en curso, revisar su estado en la página de la corrida.) Verificar en Documentos: títulos según la nomenclatura, PDF de Normativa y Word/PDF de Conceptos descargables, y que la corrida no tenga errores.

- [ ] **Step 4: Prueba ampliada, un año completo (solo scraper)**

Repetir el script del Step 2 con `("2023-01-01", "2023-12-31")` — año con choques conocidos (tres "Circular 1"):
Expected: aparecen `C_PGN_0001_2023`, `C_PGN_0001_2023_2`, `C_PGN_0001_2023_3`; 0 títulos repetidos; 0 "Error"; revisar la lista de "Aviso" (números de concepto raros) y anotar en el reporte cuántos hubo.

- [ ] **Step 5: Reportar al usuario**

Informe corto en español sencillo: cuántos documentos por sección, ejemplos de títulos, avisos encontrados, cualquier diferencia con el diseño. No abrir PR sin confirmación del usuario (master está protegido; confirmar antes de abrir PRs).
