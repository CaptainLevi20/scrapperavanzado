# Fuente Ministerio de Salud y Protección Social — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar la familia `minsalud` (fuente "Ministerio de Salud y Protección Social") con cuatro secciones — Resoluciones, Circulares, Conceptos y Boletines — leídas de la biblioteca SharePoint `Normatividad_Nuevo` por su API REST, con la nomenclatura de los ministerios.

**Architecture:** Un módulo `core/scrapers/families/minsalud.py` con funciones puras (lectura de número/radicado/mes, año y fecha en cascada, título, armado de documentos) y una clase `ScrapMinSalud` que hace UNA consulta paginada a la API (`odata.nextLink`), reparte por "Tipo de Norma", calcula títulos y sufijos sobre toda la lista y filtra por el rango de la corrida. El helper de sufijos por choque se mueve de `procuraduria.py` a `core/naming.py` para compartirlo.

**Tech Stack:** Python 3.14, `requests`, `pytest` + `responses` 0.26.

**Spec:** `docs/superpowers/specs/2026-09-28-fuente-minsalud-design.md`

## Global Constraints

- `family_key="minsalud"`, nombre exacto de la fuente: `"Ministerio de Salud y Protección Social"`, sigla en títulos: `MSPS`.
- API: `https://www.minsalud.gov.co/_api/web/GetList('/Normatividad_Nuevo')/items`, cabecera `Accept: application/json;odata=nometadata`, `$top=5000`, paginación por `odata.nextLink`. TLS normal (**sin** `verify=False`).
- Secciones por "Tipo de Norma" que **empieza por** (tras `strip()`): `Resolución` → seccion `Resoluciones`, tipo `Resolución`, prefijo `R`; `Circular` → `Circulares`, `Circular`, `C`; `Concepto` → `Conceptos`, `Concepto`, `CTO`; `Boletines` → `Boletines`, `Boletín Jurídico`, `BOL`. Solo archivos (`FSObjType == 0`).
- Piso: año del documento `>= 2015`. Rango de la corrida sobre la fecha del documento.
- Títulos: `R_MSPS_{n:04d}_{año}`, `C_MSPS_{n:04d}_{año}`, `CTO_MSPS_{radicado}_{año}`, `BOL_MSPS_{MES}_{año}` (MES en `ENE FEB MAR ABR MAY JUN JUL AGO SEP OCT NOV DIC`); sin número → `{PREFIJO}_MSPS_SN{ID}_{año}` + aviso.
- Choques de título: `_2`, `_3`… por `ID` ascendente, calculados sobre toda la lista antes de filtrar por rango.
- Fecha en cascada: Publicación (hora Colombia, UTC−5) → fecha en prosa de la descripción/título del mismo año → `Created` (hora Colombia) del mismo año → `AAAA-01-01` + aviso.
- `scheduled_min_lookback_days = 60`; `doc_id_uses_publication_date = False`; `checks_for_republication` queda `True`.
- Mensajes de progreso con prefijo `[Ministerio de Salud y Protección Social]`; avisos con `Aviso:` (nunca la palabra "Error"); falla de la API → mensaje con `Error` y 0 documentos. Avisos solo para documentos que la corrida conserva.
- Comentarios y mensajes en español.

## Review Focus

- La API responde una página sin `odata.nextLink` pero con 5000 elementos, o un JSON sin `value` (sitio cambiado): lo primero es normal (se termina), lo segundo debe ser un Error visible, no 0 documentos silenciosos (Task 5).
- Una fecha en prosa de OTRO año en la descripción (p. ej. "deroga la Resolución del 5 de marzo de 2014") no debe usarse como fecha del documento (Task 3).
- `Publicación` en UTC `…T05:00:00Z` debe dar el mismo día en Colombia, no el anterior; `…T04:59Z` sí el anterior (Task 3).
- Correr un mes y correr el año completo debe dar el mismo título a un documento con choque (Task 4).
- Rutas de archivo con tildes y espacios (`Resolución No 1809 de 2026.pdf`) deben quedar url-codificadas en el enlace (Task 4).

---

## File Structure

- **Modify** `core/naming.py` — nueva función pública `con_sufijos(pares)`.
- **Modify** `core/scrapers/families/procuraduria.py` — usa `core.naming.con_sufijos` (se borra su copia local; se conserva el nombre `_con_sufijos` como alias importado).
- **Modify** `tests/test_naming.py` — pruebas de `con_sufijos`.
- **Create** `core/scrapers/families/minsalud.py` — toda la familia.
- **Create** `tests/families/test_minsalud.py`.
- **Modify** `core/scrapers/families/__init__.py`, `core/seed.py`, `tests/test_seed.py`.
- **Modify** `docs/guia-despliegue-sistemas.md` — sección de la fuente (al final, después de Procuraduría).

Comando de pruebas (Git Bash, raíz del repo): `.venv/Scripts/python -m pytest tests/families/test_minsalud.py -v`. **No** correr la suite completa ni suites de base de datos salvo las que la tarea nombra.

---

### Task 1: `con_sufijos` compartido en `core/naming.py`

**Files:**
- Modify: `core/naming.py`
- Modify: `core/scrapers/families/procuraduria.py` (la función `_con_sufijos`, ~líneas 223-240, y el import de `core.naming`)
- Test: `tests/test_naming.py`

**Interfaces:**
- Produces: `core.naming.con_sufijos(pares: List[Tuple[str, int]]) -> List[str]` — recibe `(título_base, id_interno)` en cualquier orden y devuelve los títulos finales en el mismo orden de entrada.

- [ ] **Step 1: Write the failing tests** — agregar al final de `tests/test_naming.py` (y `con_sufijos` al import de `core.naming` que ya tenga el archivo; si importa con `from core.naming import (...)`, agregarlo ahí; si no, agregar `from core.naming import con_sufijos`):

```python
# ---- con_sufijos (títulos repetidos dentro de una fuente) ----
def test_con_sufijos_sin_choques_no_cambia():
    assert con_sufijos([("A", 3), ("B", 1)]) == ["A", "B"]


def test_con_sufijos_ordena_por_id_y_conserva_orden_de_entrada():
    pares = [("C_X_0001_2023", 300), ("C_X_0001_2023", 100), ("Y", 5), ("C_X_0001_2023", 200)]
    assert con_sufijos(pares) == ["C_X_0001_2023_3", "C_X_0001_2023", "Y", "C_X_0001_2023_2"]


def test_con_sufijos_empate_de_id_desempata_por_posicion():
    assert con_sufijos([("T", 0), ("T", 0)]) == ["T", "T_2"]


def test_con_sufijos_lista_vacia():
    assert con_sufijos([]) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_naming.py -k con_sufijos -v`
Expected: ERROR — `ImportError: cannot import name 'con_sufijos'`

- [ ] **Step 3: Implement** — en `core/naming.py`, cambiar `from typing import Optional` por `from typing import Dict, List, Optional, Tuple` y agregar al final:

```python
def con_sufijos(pares: List[Tuple[str, int]]) -> List[str]:
    """Distingue títulos repetidos dentro de una fuente (p. ej. dependencias
    que numeran por su cuenta, o el mismo número en series distintas): dentro
    de cada grupo de títulos iguales, el de menor id interno del sitio queda
    limpio y los siguientes llevan _2, _3… en orden de id. Quien la llama
    debe pasarle el conjunto COMPLETO de documentos que comparte numeración
    (el año o la lista entera), no solo los del rango de la corrida, para que
    el título de un documento no dependa de ese rango."""
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

En `core/scrapers/families/procuraduria.py`: borrar la función `_con_sufijos` completa (docstring incluido) y cambiar `from core.naming import codigo_ley_decreto` por:

```python
from core.naming import codigo_ley_decreto
from core.naming import con_sufijos as _con_sufijos
```

(Los usos internos `_con_sufijos(...)` y el import de `tests/families/test_procuraduria.py` siguen funcionando sin cambios.)

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python -m pytest tests/test_naming.py tests/families/test_procuraduria.py -v`
Expected: PASS (todas, incluidas las 4 pruebas `_con_sufijos` de Procuraduría)

- [ ] **Step 5: Commit**

```bash
git add core/naming.py core/scrapers/families/procuraduria.py tests/test_naming.py
git commit -m "refactor: mover el helper de sufijos por choque a core/naming para compartirlo"
```

---

### Task 2: Esqueleto del módulo + lectura de número, radicado y mes

**Files:**
- Create: `core/scrapers/families/minsalud.py`
- Test: `tests/families/test_minsalud.py`

**Interfaces:**
- Produces: constantes `_SOURCE`, `_BASE`, `_API`, `_CAMPOS`, `_ANIO_MIN`, `_UA`, `_TIMEOUT`, `_SECCIONES`, `_MESES_ABR`; funciones `_norm(texto) -> str`, `_sin_extension(nombre) -> str`, `_numero_norma(texto) -> Optional[int]`, `_radicado(texto) -> Optional[str]`, `_mes_boletin(texto, fecha: Optional[date]) -> Optional[int]`.

- [ ] **Step 1: Write the failing tests** — crear `tests/families/test_minsalud.py`:

```python
import datetime

import pytest

from core.scrapers.families.minsalud import (
    _mes_boletin,
    _norm,
    _numero_norma,
    _radicado,
    _sin_extension,
)


def test_norm_quita_acentos_y_minusculas():
    assert _norm("Resolución JURÍDICO Nº") == "resolucion juridico nº"


def test_sin_extension():
    assert _sin_extension("Resolución No 1809 de 2026.pdf") == "Resolución No 1809 de 2026"
    assert _sin_extension("Circular externa No. 0015.PDF") == "Circular externa No. 0015"
    assert _sin_extension("Sin extension") == "Sin extension"


@pytest.mark.parametrize("texto,esperado", [
    # regla 1: número + año (tolerando de/del y fecha en prosa en medio)
    ("Resolución No. 1809 de 2026", 1809),
    ("Resolucion No 276 de 2019", 276),
    ("Resolución No.2722 de 2019", 2722),
    ("Resolución 1099 del 2020", 1099),
    ("Resolución No. 0304de 2015", 304),
    ("Resolución No. 001133 de 2017", 1133),
    ("Resolución Nro.00532 de 2017", 532),
    ("Resolución 013956 de 2016", 13956),
    ("Circular No. 45 del 31 de Dciiembre del 2019", 45),
    ("Circular Externa No 0031 de 2026", 31),
    ("Circualr No. 12 de 2016", 12),
    ("Modificación transitoria resolución 227 de 2020", 227),
    # regla 2: número tras el marcador No/Nº/N° (con . o _ opcional)
    ("Circular externa No. 0015", 15),
    ("Circular externa No_9 Minsalud y UNGRD", 9),
    # regla 3: número al inicio
    ("3312 Establece requisitos - condiciones para giro", 3312),
    # regla 4: último número del nombre
    ("Circular Conjunta 036", 36),
])
def test_numero_norma(texto, esperado):
    assert _numero_norma(texto) == esperado


@pytest.mark.parametrize("texto", ["Alcance a la Circular Salud   Vida", "Res", "", None])
def test_numero_norma_none(texto):
    assert _numero_norma(texto) is None


@pytest.mark.parametrize("texto,esperado", [
    ("Concepto Jurídico 201711601019341 de 2017", "201711601019341"),
    ("CONCEPTO JURÍDICO 2026423003321522 ID 2258969 7", "2026423003321522"),
    ("Concepto Jurídico No 2026424000867002", "2026424000867002"),
    ("Concepto Jurídico  202211600135321 de 2022", "202211600135321"),
])
def test_radicado(texto, esperado):
    assert _radicado(texto) == esperado


@pytest.mark.parametrize("texto", ["Decreto No. 1600 de 2022", "Concepto 12345 de 2020", "", None])
def test_radicado_none(texto):
    assert _radicado(texto) is None


@pytest.mark.parametrize("texto,fecha,esperado", [
    ("Boletín Jurídico No 5 Mayo 2016", None, 5),
    ("Boletín Jurídico No. 002 de febrero 2025", None, 2),
    ("Boletín Jurídico No 12 Diciembre de 2019", None, 12),
    ("Boletín Jurídico No 9 Setiembre 2018", None, 9),
    ("Boletin Juridico No 4 del 2015", None, 4),
    ("Boletín Jurídico No. 06  de 2026", None, 6),
    ("Boletín Jurídico especial", datetime.date(2020, 7, 31), 7),
])
def test_mes_boletin(texto, fecha, esperado):
    assert _mes_boletin(texto, fecha) == esperado


@pytest.mark.parametrize("texto", ["Boletín Jurídico especial", "Boletín Jurídico No 15 de 2020"])
def test_mes_boletin_none(texto):
    assert _mes_boletin(texto, None) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/families/test_minsalud.py -v`
Expected: ERROR — `ModuleNotFoundError: No module named 'core.scrapers.families.minsalud'`

- [ ] **Step 3: Implement** — crear `core/scrapers/families/minsalud.py`:

```python
"""Ministerio de Salud y Protección Social (MinSalud) — cuatro secciones de
normativa. Diseño: docs/superpowers/specs/2026-09-28-fuente-minsalud-design.md

Las cuatro páginas "Norm_*.aspx" del sitio son marcos de SharePoint sobre UNA
sola biblioteca de documentos, /Normatividad_Nuevo, filtrada por la columna
"Tipo de Norma" (empieza por Resolución / Circular / Concepto / Boletines).
Las páginas HTML tardan minutos en responder, pero la API REST de SharePoint
entrega la lista completa en segundos, así que se lee de ahí con una sola
consulta paginada (odata.nextLink). TLS válido: sin verify=False.
"""
import datetime
import re
import unicodedata
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

from core.fecha_es import parse_fecha_providencia_es
from core.models import RawDocModel
from core.naming import con_sufijos
from core.scrapers.base import BaseScrapper
from core.scrapers.registry import register_family
from core.utils import storage_path

_SOURCE = "Ministerio de Salud y Protección Social"
_BASE = "https://www.minsalud.gov.co"
_API = f"{_BASE}/_api/web/GetList('/Normatividad_Nuevo')/items"
_CAMPOS = (
    "ID,Title,FileLeafRef,FileRef,FSObjType,Tipo_x0020_de_x0020_Norma,A_x00f1_o,"
    "Publicaci_x00f3_n,Descripci_x00f3_n,Tem_x00e1_tica,Subtema,Responsable,Created"
)
_ANIO_MIN = 2015
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
# El sitio a veces tarda en responder (las páginas HTML, minutos); la API suele
# contestar en segundos, pero se deja margen amplio.
_TIMEOUT = 300

# (prefijo del "Tipo de Norma", sección, tipo del documento, prefijo del título)
_SECCIONES = [
    ("Resolución", "Resoluciones", "Resolución", "R"),
    ("Circular", "Circulares", "Circular", "C"),
    ("Concepto", "Conceptos", "Concepto", "CTO"),
    ("Boletines", "Boletines", "Boletín Jurídico", "BOL"),
]
_MESES_ABR = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]
_MESES_PALABRA = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')
_EXTENSION = re.compile(r"\.[A-Za-z0-9]{2,4}$")

# Número de resolución/circular, en orden de preferencia (sobre texto
# normalizado: minúsculas, sin acentos). Los nombres de archivo se escriben a
# mano con muchas variantes ("No.", "Nro.", "No_9", "0304de 2015", "del 31 de
# diciembre del 2019", números con ceros a la izquierda de hasta 6 dígitos).
_NUM_CON_ANIO = re.compile(
    r"(?<!\d)(\d{1,6})\s*(?:de|del)?\s*(?:\d{1,2}\s+de\s+\w+\s+del?\s+)?((?:19|20)\d{2})\b"
)
_NUM_TRAS_MARCADOR = re.compile(r"\bn(?:o|°|º)?[._]?\s*(\d{1,6})\b")
_NUM_AL_INICIO = re.compile(r"^\s*(\d{1,6})\b")
_NUM_AL_FINAL = re.compile(r"(?<!\d)(\d{1,6})\s*$")
_RADICADO = re.compile(r"(?<!\d)(\d{12,17})(?!\d)")
_NUM_BOLETIN = re.compile(r"\bn(?:o|°|º)?[._]?\s*0*(\d{1,2})\b")


def _norm(texto: Optional[str]) -> str:
    s = unicodedata.normalize("NFKD", unicodedata.normalize("NFC", texto or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _sin_extension(nombre: Optional[str]) -> str:
    return _EXTENSION.sub("", nombre or "")


def _safe_title(title: str) -> str:
    return _INVALID_PATH_CHARS.sub("-", title)[:120].strip(" .")


def _numero_norma(texto: Optional[str]) -> Optional[int]:
    n = _norm(texto)
    for patron in (_NUM_CON_ANIO, _NUM_TRAS_MARCADOR, _NUM_AL_INICIO, _NUM_AL_FINAL):
        m = patron.search(n)
        if m:
            return int(m.group(1))
    return None


def _radicado(texto: Optional[str]) -> Optional[str]:
    m = _RADICADO.search(texto or "")
    return m.group(1) if m else None


def _mes_boletin(texto: Optional[str], fecha: Optional[datetime.date]) -> Optional[int]:
    """Mes del boletín: la palabra del mes; si no hay, el número del boletín
    cuando está entre 1 y 12 (uno por mes); si tampoco, el mes de `fecha`
    (que el llamador pasa solo cuando NO es la fecha de respaldo 1 de enero)."""
    n = _norm(texto)
    for palabra, mes in _MESES_PALABRA.items():
        if re.search(rf"\b{palabra}\b", n):
            return mes
    m = _NUM_BOLETIN.search(n)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(1))
    return fecha.month if fecha is not None else None
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python -m pytest tests/families/test_minsalud.py -v`
Expected: PASS. Si falla un caso parametrizado, ajustar el código (normalización/regex), nunca el valor esperado: vienen de nombres reales del sitio.

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/minsalud.py tests/families/test_minsalud.py
git commit -m "feat(minsalud): lectura de número, radicado y mes de los documentos"
```

---

### Task 3: Año y fecha en cascada

**Files:**
- Modify: `core/scrapers/families/minsalud.py`
- Test: `tests/families/test_minsalud.py`

**Interfaces:**
- Consumes: `_norm` (Task 2).
- Produces:
  - `_item(**kw) -> dict` — helper de pruebas (en el archivo de tests) con la forma real de un elemento de la API; Tasks 4-5 lo reutilizan.
  - `_anio_doc(item: dict) -> int`
  - `_fecha_local(iso: Optional[str]) -> Optional[datetime.date]`
  - `_fecha_doc(item: dict, anio: int) -> Tuple[datetime.date, bool]` — `(fecha, es_respaldo)`; `es_respaldo=True` solo cuando se usó `AAAA-01-01`.

- [ ] **Step 1: Write the failing tests** — agregar `_anio_doc, _fecha_doc, _fecha_local` al import y al final:

```python
# ---- helper con la forma real de un elemento de la API ----
def _item(id=1, tipo="Resolución", archivo="Resolución No 1809 de 2026.pdf", titulo=None,
          anio="2026", pub=None, desc=None, tematica="Salud", subtema=None,
          responsable=None, creado="2026-09-22T15:27:31Z", carpeta=0):
    return {
        "ID": id,
        "Title": titulo if titulo is not None else archivo.rsplit(".", 1)[0],
        "FileLeafRef": archivo,
        "FileRef": f"/Normatividad_Nuevo/{archivo}",
        "FSObjType": carpeta,
        "Tipo_x0020_de_x0020_Norma": tipo,
        "A_x00f1_o": anio,
        "Publicaci_x00f3_n": pub,
        "Descripci_x00f3_n": desc,
        "Tem_x00e1_tica": tematica,
        "Subtema": subtema,
        "Responsable": responsable,
        "Created": creado,
    }


# ---- año ----
def test_anio_doc_de_la_columna():
    assert _anio_doc(_item(anio="2017")) == 2017
    assert _anio_doc(_item(anio="2017 ")) == 2017


def test_anio_doc_del_nombre_si_falta_la_columna():
    assert _anio_doc(_item(anio=None, archivo="Circular No 5 de 2019.pdf")) == 2019


def test_anio_doc_no_confunde_un_radicado_con_un_anio():
    it = _item(anio=None, archivo="Concepto Jurídico 201711601019341.pdf", creado="2017-06-30T10:00:00Z")
    assert _anio_doc(it) == 2017


def test_anio_doc_de_created_como_ultimo_recurso():
    assert _anio_doc(_item(anio="", archivo="Res.pdf", creado="2024-03-01T12:00:00Z")) == 2024


# ---- fecha ----
def test_fecha_local_convierte_utc_a_colombia():
    assert _fecha_local("2026-09-24T05:00:00Z") == datetime.date(2026, 9, 24)
    assert _fecha_local("2026-09-24T04:59:00Z") == datetime.date(2026, 9, 23)
    assert _fecha_local(None) is None
    assert _fecha_local("basura") is None


def test_fecha_doc_prefiere_publicacion():
    it = _item(pub="2026-09-24T05:00:00Z", desc="con fecha 25 de septiembre de 2026")
    assert _fecha_doc(it, 2026) == (datetime.date(2026, 9, 24), False)


def test_fecha_doc_prosa_de_la_descripcion_del_mismo_anio():
    it = _item(desc="Publicada en el Diario Oficial No. 53.638 con fecha 25 de septiembre de 2026")
    assert _fecha_doc(it, 2026) == (datetime.date(2026, 9, 25), False)


def test_fecha_doc_prosa_del_titulo():
    it = _item(archivo="Circular No. 45 de 2019.pdf", titulo="Circular No. 45 del 31 de diciembre del 2019",
               anio="2019", creado="2020-01-10T10:00:00Z")
    assert _fecha_doc(it, 2019) == (datetime.date(2019, 12, 31), False)


def test_fecha_doc_ignora_prosa_de_otro_anio_y_usa_created():
    it = _item(anio="2017", desc="Deroga la resolución del 5 de marzo de 2014", creado="2017-06-30T15:00:00Z")
    assert _fecha_doc(it, 2017) == (datetime.date(2017, 6, 30), False)


def test_fecha_doc_respaldo_1_de_enero_si_created_es_de_otro_anio():
    it = _item(anio="2019", creado="2020-01-10T10:00:00Z")
    assert _fecha_doc(it, 2019) == (datetime.date(2019, 1, 1), True)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/families/test_minsalud.py -v`
Expected: ERROR — `ImportError: cannot import name '_anio_doc'`

- [ ] **Step 3: Implement** — agregar al final de `minsalud.py`:

```python
# El sitio guarda las fechas en UTC; "…T05:00:00Z" es la medianoche en Bogotá.
_COLOMBIA = datetime.timezone(datetime.timedelta(hours=-5))
_ANIO_EN_TEXTO = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


def _anio_plausible(a: int) -> bool:
    return 1990 <= a <= datetime.date.today().year + 1


def _fecha_local(iso: Optional[str]) -> Optional[datetime.date]:
    try:
        dt = datetime.datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(_COLOMBIA).date()


def _anio_doc(item: dict) -> int:
    """Año del documento: columna Año; si falta, el último año del nombre del
    archivo; si tampoco, el año de subida (Created)."""
    crudo = (item.get("A_x00f1_o") or "").strip()[:4]
    if crudo.isdigit() and _anio_plausible(int(crudo)):
        return int(crudo)
    anios = [int(a) for a in _ANIO_EN_TEXTO.findall(item.get("FileLeafRef") or "") if _anio_plausible(int(a))]
    if anios:
        return anios[-1]
    creado = _fecha_local(item.get("Created"))
    return creado.year if creado else datetime.date.today().year


def _fecha_doc(item: dict, anio: int) -> Tuple[datetime.date, bool]:
    """(fecha, es_respaldo). Cascada: Publicación → fecha en prosa de la
    descripción o del título, si es del año del documento → Created, si es del
    año → 1 de enero del año (respaldo)."""
    pub = _fecha_local(item.get("Publicaci_x00f3_n"))
    if pub is not None:
        return pub, False
    for texto in (item.get("Descripci_x00f3_n"), item.get("Title")):
        f = parse_fecha_providencia_es(texto or "")
        if f is not None and f.year == anio:
            return f, False
    creado = _fecha_local(item.get("Created"))
    if creado is not None and creado.year == anio:
        return creado, False
    return datetime.date(anio, 1, 1), True
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python -m pytest tests/families/test_minsalud.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/minsalud.py tests/families/test_minsalud.py
git commit -m "feat(minsalud): año y fecha del documento en cascada"
```

---

### Task 4: Título y armado de documentos

**Files:**
- Modify: `core/scrapers/families/minsalud.py`
- Test: `tests/families/test_minsalud.py`

**Interfaces:**
- Consumes: `_numero_norma`, `_radicado`, `_mes_boletin`, `_sin_extension` (Task 2); `_anio_doc`, `_fecha_doc` (Task 3); `con_sufijos` (Task 1); test helper `_item` (Task 3).
- Produces:
  - `_seccion_de(tipo: Optional[str]) -> Optional[Tuple[str, str, str]]` — `(seccion, tipo_doc, prefijo)` o `None`.
  - `_titulo(prefijo: str, item: dict, anio: int, fecha: date, es_respaldo: bool) -> Tuple[str, bool]` — `(título, aviso)`.
  - `_docs(items: List[dict], desde: str, hasta: str, on_progress) -> List[RawDocModel]`.
  - `_avisar(on_progress, mensaje: str) -> None`.

- [ ] **Step 1: Write the failing tests** — agregar `_docs, _seccion_de, _titulo` al import y al final:

```python
# ---- sección ----
@pytest.mark.parametrize("tipo,esperado", [
    ("Resolución", ("Resoluciones", "Resolución", "R")),
    ("Resolución ", ("Resoluciones", "Resolución", "R")),
    ("Resolución CRES", ("Resoluciones", "Resolución", "R")),
    ("Circular", ("Circulares", "Circular", "C")),
    ("Circular CRES", ("Circulares", "Circular", "C")),
    ("Concepto", ("Conceptos", "Concepto", "CTO")),
    ("Boletines Jurídicos", ("Boletines", "Boletín Jurídico", "BOL")),
])
def test_seccion_de(tipo, esperado):
    assert _seccion_de(tipo) == esperado


@pytest.mark.parametrize("tipo", ["Decreto", "Ley", "Acuerdo CNSSS", "Proyecto Resolución", None, ""])
def test_seccion_de_otros_tipos_no_entran(tipo):
    assert _seccion_de(tipo) is None


# ---- título ----
_F = datetime.date(2026, 9, 24)


def test_titulo_resolucion_y_circular():
    assert _titulo("R", _item(archivo="Resolución No 1809 de 2026.pdf"), 2026, _F, False) == ("R_MSPS_1809_2026", False)
    assert _titulo("C", _item(archivo="Circular Externa No 0031 de 2026.pdf"), 2026, _F, False) == ("C_MSPS_0031_2026", False)
    assert _titulo("R", _item(archivo="Resolución 013956 de 2016.pdf"), 2016, _F, False) == ("R_MSPS_13956_2016", False)


def test_titulo_anio_es_el_del_documento_aunque_el_nombre_diga_otro():
    assert _titulo("R", _item(archivo="Resolución No. 2722 de 2019.pdf"), 2018, _F, False) == ("R_MSPS_2722_2018", False)


def test_titulo_numero_desde_el_titulo_si_el_archivo_no_lo_trae():
    it = _item(archivo="Res.pdf", titulo="Modificación transitoria resolución 227 de 2020")
    assert _titulo("R", it, 2024, _F, False) == ("R_MSPS_0227_2024", False)


def test_titulo_concepto_y_boletin():
    it = _item(tipo="Concepto", archivo="CONCEPTO JURÍDICO 2026423003321522 ID 2258969 7.pdf")
    assert _titulo("CTO", it, 2026, _F, False) == ("CTO_MSPS_2026423003321522_2026", False)
    bol = _item(tipo="Boletines Jurídicos", archivo="Boletín Jurídico No 5 Mayo 2016.pdf")
    assert _titulo("BOL", bol, 2016, datetime.date(2016, 5, 31), False) == ("BOL_MSPS_MAY_2016", False)


def test_titulo_boletin_no_usa_la_fecha_de_respaldo_para_el_mes():
    bol = _item(id=40, tipo="Boletines Jurídicos", archivo="Boletín Jurídico especial.pdf")
    assert _titulo("BOL", bol, 2016, datetime.date(2016, 1, 1), True) == ("BOL_MSPS_SN40_2016", True)


def test_titulo_sin_numero_usa_sn_id_y_avisa():
    it = _item(id=77, tipo="Circular", archivo="Alcance a la Circular Salud   Vida.pdf")
    assert _titulo("C", it, 2019, _F, False) == ("C_MSPS_SN77_2019", True)
    dec = _item(id=5, tipo="Concepto", archivo="Decreto No. 1600 de 2022.pdf")
    assert _titulo("CTO", dec, 2022, _F, False) == ("CTO_MSPS_SN5_2022", True)


# ---- armado de documentos ----
def test_docs_campos_basicos():
    it = _item(id=8950, tipo="Circular", archivo="Circular Externa No 0031 de 2026.pdf",
               pub="2026-09-24T05:00:00Z", desc="Intensificación de acciones\n\nPublicada en el Diario Oficial",
               subtema="Salud ambiental")
    [d] = _docs([it], "2026-09-01", "2026-09-30", None)
    assert d.title == "C_MSPS_0031_2026"
    assert d.tipo == "Circular" and d.seccion == "Circulares"
    assert d.f_public == d.f_providencia == "2026-09-24"
    assert d.link == {
        "url": "https://www.minsalud.gov.co/Normatividad_Nuevo/Circular%20Externa%20No%200031%20de%202026.pdf",
        "method": "GET",
    }
    assert d.detalle == ("Circular Externa No 0031 de 2026 — Intensificación de acciones Publicada en el "
                         "Diario Oficial (Salud / Salud ambiental)")
    assert d.source == "Ministerio de Salud y Protección Social"
    assert d.save_path == "Ministerio de Salud y Protección Social/2026-09-24/Circular/C_MSPS_0031_2026(extension)"


def test_docs_url_codifica_tildes():
    [d] = _docs([_item(pub="2026-09-21T05:00:00Z")], "2026-09-01", "2026-09-30", None)
    assert d.link["url"] == ("https://www.minsalud.gov.co/Normatividad_Nuevo/"
                             "Resoluci%C3%B3n%20No%201809%20de%202026.pdf")


def test_docs_concepto_no_repite_descripcion_igual_al_titulo_y_agrega_dependencia():
    it = _item(tipo="Concepto", archivo="Concepto Jurídico 202611600000001 de 2026.pdf",
               titulo="Concepto sobre juntas", desc="Concepto  sobre\njuntas", responsable="Dirección Jurídica",
               pub="2026-09-21T05:00:00Z")
    [d] = _docs([it], "2026-09-01", "2026-09-30", None)
    assert d.detalle == "Concepto sobre juntas (Salud) — Dependencia: Dirección Jurídica"


def test_docs_reparte_por_seccion_y_excluye_otros_tipos_y_carpetas():
    items = [
        _item(id=1, tipo="Resolución ", archivo="Resolución No 5 de 2025.pdf", anio="2025", pub="2025-03-01T05:00:00Z"),
        _item(id=2, tipo="Decreto", archivo="Decreto No 7 de 2025.pdf", anio="2025", pub="2025-03-01T05:00:00Z"),
        _item(id=3, tipo="Boletines Jurídicos", archivo="Boletín Jurídico No 3 Marzo 2025.pdf", anio="2025",
              pub="2025-03-31T05:00:00Z"),
        _item(id=4, tipo="Resolución", archivo="Carpeta", anio="2025", carpeta=1),
        _item(id=5, tipo=None, archivo="Suelto.pdf", anio="2025"),
    ]
    docs = _docs(items, "2025-01-01", "2025-12-31", None)
    assert sorted((d.seccion, d.title, d.tipo) for d in docs) == [
        ("Boletines", "BOL_MSPS_MAR_2025", "Boletín Jurídico"),
        ("Resoluciones", "R_MSPS_0005_2025", "Resolución"),
    ]


def test_docs_piso_2015_y_rango():
    items = [
        _item(id=1, archivo="Resolución No 1 de 2014.pdf", anio="2014", pub="2014-05-05T05:00:00Z"),
        _item(id=2, archivo="Resolución No 2 de 2020.pdf", anio="2020", pub="2020-05-05T05:00:00Z"),
        _item(id=3, archivo="Resolución No 3 de 2020.pdf", anio="2020", pub="2020-08-05T05:00:00Z"),
    ]
    assert [d.title for d in _docs(items, "2010-01-01", "2020-06-30", None)] == ["R_MSPS_0002_2020"]


def test_docs_choques_con_sufijo_por_id_estables_ante_el_rango():
    items = [
        _item(id=300, archivo="Resolución No 1809 de 2026 Con anexoTécnico.pdf", pub="2026-09-21T05:00:00Z"),
        _item(id=100, archivo="Resolución No 1809 de 2026.pdf", pub="2026-08-05T05:00:00Z"),
    ]
    todos = {d.f_public: d.title for d in _docs(items, "2026-01-01", "2026-12-31", None)}
    assert todos == {"2026-08-05": "R_MSPS_1809_2026", "2026-09-21": "R_MSPS_1809_2026_2"}
    [solo] = _docs(items, "2026-09-01", "2026-09-30", None)
    assert solo.title == "R_MSPS_1809_2026_2"


def test_docs_avisos_solo_de_documentos_conservados():
    avisos = []
    items = [
        _item(id=7, tipo="Circular", archivo="Alcance a la Circular Salud Vida.pdf", anio="2019",
              creado="2020-01-10T10:00:00Z"),
        _item(id=8, tipo="Circular", archivo="Otra circular sin numero.pdf", anio="2021",
              creado="2021-06-01T10:00:00Z"),
    ]
    docs = _docs(items, "2021-01-01", "2021-12-31", avisos.append)
    assert [d.title for d in docs] == ["C_MSPS_SN8_2021"]
    assert any("C_MSPS_SN8_2021" in a for a in avisos)
    assert not any("SN7" in a for a in avisos)
    assert all("Error" not in a for a in avisos)
    assert all(a.startswith("[Ministerio de Salud y Protección Social] Aviso:") for a in avisos)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/families/test_minsalud.py -v`
Expected: ERROR — `ImportError: cannot import name '_docs'`

- [ ] **Step 3: Implement** — agregar al final de `minsalud.py`:

```python
def _avisar(on_progress, mensaje: str) -> None:
    if on_progress:
        on_progress(f"[{_SOURCE}] {mensaje}")


def _seccion_de(tipo: Optional[str]) -> Optional[Tuple[str, str, str]]:
    """Réplica del filtro de las vistas del sitio: "Tipo de Norma" EMPIEZA por
    Resolución / Circular / Concepto / Boletines (absorbe "Resolución " con
    espacio, "Resolución CRES", "Circular CRES", "Boletines Jurídicos")."""
    t = (tipo or "").strip()
    for prefijo_tipo, seccion, tipo_doc, prefijo in _SECCIONES:
        if t.startswith(prefijo_tipo):
            return seccion, tipo_doc, prefijo
    return None


def _titulo(prefijo: str, item: dict, anio: int, fecha: datetime.date, es_respaldo: bool) -> Tuple[str, bool]:
    """(título, aviso). El número sale del nombre del archivo o, si no trae,
    del título del sitio; el año es siempre el del documento."""
    archivo = _sin_extension(item.get("FileLeafRef"))
    titulo_sitio = item.get("Title") or ""
    if prefijo in ("R", "C"):
        n = _numero_norma(archivo)
        if n is None:
            n = _numero_norma(titulo_sitio)
        if n is not None:
            return f"{prefijo}_MSPS_{n:04d}_{anio}", False
    elif prefijo == "CTO":
        rad = _radicado(archivo) or _radicado(titulo_sitio)
        if rad:
            return f"CTO_MSPS_{rad}_{anio}", False
    elif prefijo == "BOL":
        fecha_util = None if es_respaldo else fecha
        mes = _mes_boletin(archivo, None) or _mes_boletin(titulo_sitio, fecha_util)
        if mes:
            return f"BOL_MSPS_{_MESES_ABR[mes - 1]}_{anio}", False
    return f"{prefijo}_MSPS_SN{item.get('ID')}_{anio}", True


def _una_linea(texto: Optional[str]) -> str:
    return " ".join((texto or "").split())


def _detalle(item: dict) -> Optional[str]:
    titulo = _una_linea(item.get("Title"))
    desc = _una_linea(item.get("Descripci_x00f3_n"))
    partes = [titulo] + ([desc] if desc and desc != titulo else [])
    detalle = " — ".join(p for p in partes if p)
    tema = " / ".join(x for x in (_una_linea(item.get("Tem_x00e1_tica")), _una_linea(item.get("Subtema"))) if x)
    if tema:
        detalle = f"{detalle} ({tema})" if detalle else tema
    dependencia = _una_linea(item.get("Responsable"))
    if dependencia:
        detalle = f"{detalle} — Dependencia: {dependencia}" if detalle else f"Dependencia: {dependencia}"
    return detalle or None


def _docs(items: List[dict], desde: str, hasta: str, on_progress) -> List[RawDocModel]:
    # 1) título base y fecha de TODOS los documentos de las cuatro secciones
    #    (los avisos se guardan y solo se emiten para los que quedan)
    base = []
    for item in items:
        if item.get("FSObjType") != 0:
            continue
        sec = _seccion_de(item.get("Tipo_x0020_de_x0020_Norma"))
        if sec is None:
            continue
        seccion, tipo_doc, prefijo = sec
        anio = _anio_doc(item)
        fecha, es_respaldo = _fecha_doc(item, anio)
        titulo, aviso_num = _titulo(prefijo, item, anio, fecha, es_respaldo)
        avisos = []
        if es_respaldo:
            avisos.append(f"Aviso: {titulo} sin fecha publicada, se usa {fecha.isoformat()}")
        if aviso_num:
            avisos.append(f"Aviso: no se reconoce el número de «{item.get('FileLeafRef')}», se nombra {titulo}")
        base.append((item, seccion, tipo_doc, anio, fecha, titulo, avisos))

    # 2) sufijos sobre toda la lista, y recién después piso + rango
    titulos = con_sufijos([(titulo, int(item.get("ID") or 0)) for item, _, _, _, _, titulo, _ in base])
    docs = []
    for (item, seccion, tipo_doc, anio, fecha, _, avisos), titulo in zip(base, titulos):
        iso = fecha.isoformat()
        if anio < _ANIO_MIN or iso < desde or iso > hasta:
            continue
        for mensaje in avisos:
            _avisar(on_progress, mensaje)
        docs.append(RawDocModel(
            source=_SOURCE,
            link={"url": _BASE + quote(item.get("FileRef") or ""), "method": "GET"},
            title=titulo,
            tipo=tipo_doc,
            f_public=iso,
            f_providencia=iso,
            seccion=seccion,
            detalle=_detalle(item),
            save_path=storage_path(_SOURCE, iso, tipo_doc, f"{_safe_title(titulo)}(extension)"),
        ))
    return docs
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python -m pytest tests/families/test_minsalud.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/minsalud.py tests/families/test_minsalud.py
git commit -m "feat(minsalud): títulos, sufijos por choque y armado de documentos"
```

---

### Task 5: Consulta a la API, clase `ScrapMinSalud`, registro y seed

**Files:**
- Modify: `core/scrapers/families/minsalud.py`
- Modify: `core/scrapers/families/__init__.py`
- Modify: `core/seed.py`
- Modify: `tests/test_seed.py`
- Test: `tests/families/test_minsalud.py`

**Interfaces:**
- Consumes: `_docs`, `_avisar` (Task 4); `_API`, `_CAMPOS`, `_UA`, `_TIMEOUT`, `_ANIO_MIN` (Task 2); test helper `_item` (Task 3).
- Produces: `_listar(session: requests.Session) -> List[dict]`; `ScrapMinSalud` registrada como `"minsalud"`, `scrap(self, fini, ffin, q="", limit=100000, stop_event=None, on_progress=None) -> List[RawDocModel]`.

- [ ] **Step 1: Write the failing tests** — agregar al final de `tests/families/test_minsalud.py`:

```python
# ---- API y scrap() ----
import threading

import requests
import responses

from core.scrapers.families.minsalud import _API, ScrapMinSalud, _listar
from core.scrapers.registry import FAMILY_REGISTRY

_PAGINA2 = "https://www.minsalud.gov.co/_api/pagina2"


def _sesion():
    return requests.Session()


@responses.activate
def test_listar_una_pagina_y_pide_campos_y_top():
    responses.add(responses.GET, _API, json={"value": [_item(id=1)]})
    assert [x["ID"] for x in _listar(_sesion())] == [1]
    url = responses.calls[0].request.url
    assert "%24top=5000" in url or "$top=5000" in url
    assert "FileLeafRef" in url
    assert responses.calls[0].request.headers["Accept"] == "application/json;odata=nometadata"


@responses.activate
def test_listar_sigue_odata_nextlink():
    responses.add(responses.GET, _API, json={"value": [_item(id=1)], "odata.nextLink": _PAGINA2})
    responses.add(responses.GET, _PAGINA2, json={"value": [_item(id=2)]})
    assert [x["ID"] for x in _listar(_sesion())] == [1, 2]


@responses.activate
def test_listar_json_sin_value_es_error():
    responses.add(responses.GET, _API, json={"error": "cambió"})
    with pytest.raises(RuntimeError):
        _listar(_sesion())


def test_minsalud_registrada_y_banderas():
    import core.scrapers.families  # noqa: F401
    assert FAMILY_REGISTRY["minsalud"].__name__ == "ScrapMinSalud"
    assert ScrapMinSalud.scheduled_min_lookback_days == 60
    assert ScrapMinSalud.doc_id_uses_publication_date is False
    assert ScrapMinSalud.checks_for_republication is True


@responses.activate
def test_scrap_devuelve_documentos_del_rango():
    responses.add(responses.GET, _API, json={"value": [
        _item(id=1, archivo="Resolución No 1809 de 2026.pdf", pub="2026-08-05T05:00:00Z"),
        _item(id=2, tipo="Concepto", archivo="Concepto Jurídico 2026423003321522.pdf", pub="2026-09-21T05:00:00Z"),
    ]})
    docs = ScrapMinSalud().scrap(fini="2026-09-01", ffin="2026-09-30")
    assert [d.title for d in docs] == ["CTO_MSPS_2026423003321522_2026"]


@responses.activate
def test_scrap_rango_antes_del_piso_no_consulta():
    assert ScrapMinSalud().scrap(fini="2010-01-01", ffin="2014-12-31") == []
    assert len(responses.calls) == 0


@responses.activate
def test_scrap_error_de_la_api_se_reporta():
    responses.add(responses.GET, _API, status=500)
    mensajes = []
    assert ScrapMinSalud().scrap(fini="2026-01-01", ffin="2026-12-31", on_progress=mensajes.append) == []
    assert any("Error" in m and "biblioteca de normativa" in m for m in mensajes)


@responses.activate
def test_scrap_respeta_stop_event():
    ev = threading.Event()
    ev.set()
    assert ScrapMinSalud().scrap(fini="2026-01-01", ffin="2026-12-31", stop_event=ev) == []
    assert len(responses.calls) == 0
```

En `tests/test_seed.py`:
- `assert len(families) == 27` → `assert len(families) == 28`
- las dos `assert len(sources) == 1 + 28 + 24 + 33 + 6` → `assert len(sources) == 1 + 28 + 25 + 33 + 6`
- en el conjunto de claves, después de `"procuraduria",` agregar `"minsalud",`
- en el comentario: "24 (fuente única: … supersolidaria, procuraduria)" → "25 (fuente única: … supersolidaria, procuraduria, minsalud)" y "= 92" → "= 93".

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/families/test_minsalud.py -v`
Expected: ERROR — `ImportError: cannot import name 'ScrapMinSalud'`

- [ ] **Step 3: Implement** — agregar al final de `minsalud.py`:

```python
def _listar(session: requests.Session) -> List[dict]:
    """Lista completa de la biblioteca (una consulta, paginada por
    odata.nextLink). Lanza si la respuesta no tiene la forma esperada."""
    url: Optional[str] = _API
    params: Optional[Dict[str, str]] = {"$top": "5000", "$select": _CAMPOS}
    items: List[dict] = []
    while url:
        resp = session.get(
            url, params=params, headers={"Accept": "application/json;odata=nometadata"}, timeout=_TIMEOUT
        )
        resp.raise_for_status()
        datos = resp.json()
        pagina = datos.get("value") if isinstance(datos, dict) else None
        if not isinstance(pagina, list):
            raise RuntimeError("la API no devolvió la lista 'value' (¿cambió el sitio?)")
        items.extend(pagina)
        url = datos.get("odata.nextLink")
        params = None  # el nextLink ya trae sus propios parámetros
    return items


@register_family("minsalud")
class ScrapMinSalud(BaseScrapper):
    # La mitad de las resoluciones/circulares se sube ~2 días después de su
    # fecha, pero el 90% hasta ~1 mes después: la corrida diaria mira 60 días.
    scheduled_min_lookback_days = 60
    # La identidad es la URL del archivo: la fecha puede reconstruirse distinto
    # si el sitio completa la fecha de publicación más tarde.
    doc_id_uses_publication_date = False

    def __init__(self):
        self.source = _SOURCE

    def scrap(self, fini, ffin, q="", limit=100000, stop_event=None, on_progress=None) -> List[RawDocModel]:
        desde = max(fini, f"{_ANIO_MIN}-01-01")
        if desde > ffin or (stop_event is not None and stop_event.is_set()):
            return []
        session = requests.Session()
        session.headers.update({"User-Agent": _UA})
        _avisar(on_progress, "Procesando biblioteca de normativa...")
        try:
            items = _listar(session)
        except Exception as e:
            _avisar(on_progress, f"Error consultando la biblioteca de normativa: {e}")
            return []
        return _docs(items, desde, ffin, on_progress)[:limit]
```

En `core/scrapers/families/__init__.py`, agregar `minsalud` al final de la lista de imports (`…, supersolidaria, procuraduria, minsalud  # noqa: F401`).

En `core/seed.py`, agregar al diccionario `_FAMILIES` después del bloque `"procuraduria": (...)`:

```python
    "minsalud": (
        "Ministerio de Salud y Protección Social",
        "Resoluciones, circulares, conceptos jurídicos y boletines jurídicos "
        "publicados por el Ministerio de Salud y Protección Social",
    ),
```

y al final de `seed_source_families_and_sources`, después del `create_source_if_missing` de `procuraduria`:

```python
    repository.create_source_if_missing(
        db, family_key="minsalud", name="Ministerio de Salud y Protección Social", family_params={}
    )
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python -m pytest tests/families/test_minsalud.py tests/test_registry.py tests/test_naming.py tests/families/test_procuraduria.py -v`
Expected: PASS

Run (DB, dirigida, sin paralelo): `.venv/Scripts/python -m pytest tests/test_seed.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/scrapers/families/minsalud.py core/scrapers/families/__init__.py core/seed.py tests/families/test_minsalud.py tests/test_seed.py
git commit -m "feat(minsalud): registrar la familia y la fuente Ministerio de Salud y Protección Social"
```

---

### Task 6: Documentación de despliegue

**Files:**
- Modify: `docs/guia-despliegue-sistemas.md` — nueva sección al final, después de la de `procuraduria`.

- [ ] **Step 1: Agregar la sección**

```markdown
### Ministerio de Salud y Protección Social (`minsalud`)

- **Qué trae:** las cuatro secciones de normativa del sitio del Ministerio —
  **Resoluciones**, **Circulares**, **Conceptos jurídicos** y **Boletines
  jurídicos** (uno por mes). Las cuatro páginas del sitio muestran una sola
  biblioteca de documentos; la fuente la lee completa de una vez.
- **Desde cuándo:** año 2015 en adelante.
- **Cuánto entrega hoy:** unos 2.900 documentos — cerca de 1.480
  resoluciones, 330 circulares, 950 conceptos y 140 boletines.
- **Cómo quedan nombrados:** `R_MSPS_1809_2026` (resolución),
  `C_MSPS_0031_2026` (circular: externa, interna, conjunta o de la Comisión
  de Precios de Medicamentos), `CTO_MSPS_201711601019341_2017` (concepto: su
  número de radicado + año), `BOL_MSPS_MAY_2016` (boletín: mes + año). Cuando
  dos documentos distintos dan el mismo nombre (pasa en ~30 casos: el mismo
  documento subido dos veces, versiones "con anexo técnico", o series
  distintas con el mismo número) los siguientes llevan `_2`, `_3`. Si un
  documento no trae número reconocible queda como `…_SN{número interno}_año`
  con un aviso en el registro (hoy 2 casos).
- **Ojo con las fechas:** el sitio solo publica la fecha de los documentos
  de 2023 en adelante. Para los anteriores la fuente usa la fecha escrita en
  la descripción, o la fecha en que el Ministerio subió el archivo (casi
  siempre del mismo año); si ninguna sirve, el 1 de enero del año. Por eso,
  para años viejos, conviene correr la fuente por año completo.
- **Corrida diaria:** esta fuente mira los últimos 60 días (no solo los
  últimos días), porque el Ministerio a veces sube los documentos semanas
  después de su fecha.
- **Detalle técnico:** el sitio web del Ministerio es muy lento (las páginas
  tardan minutos), pero la fuente no las usa: consulta directamente la lista
  de documentos, que responde en segundos. Certificado válido.
- **Fuente nueva:** después de actualizar producción, correr una vez
  `docker compose --env-file .env.production -f docker-compose.prod.yml run --rm api python -m core.seed`.
  Es seguro repetirlo.
```

- [ ] **Step 2: Commit**

```bash
git add docs/guia-despliegue-sistemas.md
git commit -m "docs: fuente Ministerio de Salud y Protección Social en la guía de despliegue"
```

---

### Task 7: Validación real en desarrollo

Verificación contra el sitio real con el entorno de desarrollo arriba.

- [ ] **Step 1: Registrar la fuente y reiniciar Celery** — `.venv/Scripts/python -m core.seed`; reiniciar el worker de Celery (`--pool=solo`).

- [ ] **Step 2: Prueba directa del scraper, un mes reciente**

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python - <<'EOF'
from collections import Counter
from core.scrapers.families.minsalud import ScrapMinSalud
msgs = []
docs = ScrapMinSalud().scrap("2026-08-01", "2026-09-30", on_progress=msgs.append)
print(len(docs), Counter(d.seccion for d in docs))
print([m for m in msgs if "Error" in m or "Aviso" in m][:20])
for d in docs[:15]: print(d.title, "|", d.tipo, "|", d.f_public, "|", d.link["url"][-60:])
print("repetidos:", [t for t, n in Counter(d.title for d in docs).items() if n > 1])
EOF
```
Expected: decenas de documentos de las 4 secciones, 0 "Error", 0 títulos repetidos.

- [ ] **Step 3: Año viejo (2017) — fechas reconstruidas**

Repetir con `("2017-01-01", "2017-12-31")`. Expected: ~87 resoluciones, ~28 circulares, ~91 conceptos, 12 boletines (`BOL_MSPS_ENE_2017` … `DIC`), 0 "Error"; contar cuántos quedaron con fecha de respaldo 1 de enero (avisos) y reportarlo.

- [ ] **Step 4: Corrida real por la aplicación** (driver del skill `run-iurisync`, un mes reciente) y revisar en Documentos títulos, fechas y descarga de archivos.

- [ ] **Step 5: Reportar al usuario** en español sencillo; no abrir PR sin su confirmación.
