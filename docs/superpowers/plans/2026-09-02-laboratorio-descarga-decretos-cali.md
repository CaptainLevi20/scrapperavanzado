# Descarga masiva de Decretos de Cali (Laboratorio) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third tab to the Laboratorio page that bulk-downloads every decree (~72.000) from cali.gov.co's `paginador.php` into `DECRETOS/ALCACALI/{año}/D_ALCACALI_{numero}_{año}.pdf` on disk, as a resumable Celery task driven by a JSON state file.

**Architecture:** Pure parsing/naming/state helpers in `core/cali_decretos.py`; a no-DB Celery task in `worker/tasks.py` that walks `paginador.php?pag=N`, downloads PDFs 8-at-a-time with a `ThreadPoolExecutor`, and rewrites `{destino}/_descarga_estado.json` after each page; an admin-only FastAPI router (`start` / `status` / `stop`) that enqueues the task and reads the state file; a React panel that polls `status` every 3 s.

**Tech Stack:** Python 3, FastAPI, Celery (Redis broker), `requests`, `ftplib`, BeautifulSoup4, `responses` (test HTTP mocking), pytest; React + TypeScript + Vite, Vitest + Testing Library + MSW.

**Spec:** `docs/superpowers/specs/2026-09-02-laboratorio-descarga-decretos-cali-design.md`

## Global Constraints

- Endpoints protected with `require_admin` at router level (`api/deps.py:require_admin`); non-admin → `403`.
- The Celery task never touches the database — its only persistent state is `{destino}/_descarga_estado.json`.
- State-file writes are atomic: write to `<name>.tmp`, then `os.replace`.
- Filename pattern, verbatim: `D_ALCACALI_{numero}_{año}.pdf`. Entity is always the literal `ALCACALI`. Type prefix is always the literal `D`.
- Folder layout, verbatim: `{destino}/DECRETOS/ALCACALI/{año}/`.
- Per-PDF retry schedule, verbatim: 1 initial attempt + 3 retries, sleeping `2, 8, 30` seconds before retries 1, 2, 3.
- Concurrency starts at 8; drops to 3 (for the rest of the run) after 5 consecutive PDF failures.
- A PDF is valid only if its first 4 bytes are `%PDF` **and** its size is > 1024 bytes.
- `avisos` and `fallidos` lists in the state file are capped at 1000 entries each; the `*_count` integers always hold the true total.
- All new user-facing strings are in Spanish, matching the existing Laboratorio panels.
- `master` is branch-protected; work happens on the branch `feature/laboratorio-descarga-decretos-cali` (already created). Do not push or open a PR unless the user asks.

---

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `core/cali_decretos.py` | Create | Pure helpers: parse one `paginador.php` page, normalize número/año, build destination path, validate "is a PDF", and read/write/shape the state dict. No network, no FastAPI, no Celery. |
| `worker/tasks.py` | Modify | Add `descargar_decretos_cali_task` and its private helpers (`_pedir_pagina`, `_descargar_un_pdf`, `_descargar_http`, `_descargar_ftp`, `_clasificar_error`, `_preparar_trabajos`, `_ejecutar_trabajos`, `_pasada_final_fallidos`). |
| `api/schemas.py` | Modify | Add `CaliDecretosStartRequest`, `CaliDecretosStopRequest`, `CaliDecretosAviso`, `CaliDecretosFallido`, `CaliDecretosEstado`. |
| `api/routers/cali_decretos.py` | Create | `POST /cali-decretos/start`, `GET /cali-decretos/status`, `POST /cali-decretos/stop`. |
| `api/main.py` | Modify | Import and `include_router` the new router. |
| `frontend/src/api/caliDecretos.ts` | Create | `startCaliDecretos` / `getCaliDecretosStatus` / `stopCaliDecretos` + the estado TypeScript types. |
| `frontend/src/pages/formatter/CaliDecretosPanel.tsx` | Create | Path input + Iniciar/Detener + progress + collapsible Fallidos/Avisos lists. |
| `frontend/src/pages/FormatterPage.tsx` | Modify | Add the third tab. |
| `tests/test_core_cali_decretos.py` | Create | Task 1 + Task 2 tests. |
| `tests/test_worker_cali_decretos.py` | Create | Task 3 + Task 4 tests. |
| `tests/test_api_cali_decretos.py` | Create | Task 5 tests. |
| `frontend/src/pages/formatter/CaliDecretosPanel.test.tsx` | Create | Task 6 tests. |
| `frontend/src/pages/FormatterPage.test.tsx` | Modify | Task 7 test. |

---

## Task 1: Pure parsing & naming helpers

**Files:**
- Create: `core/cali_decretos.py`
- Test: `tests/test_core_cali_decretos.py`

**Interfaces:**
- Consumes: nothing (leaf module). `beautifulsoup4` is already a dependency (`requirements.txt`).
- Produces:
  - `BASE_PAGINADOR: str = "https://www.cali.gov.co/aplicaciones/boletin_decretos/paginador.php"`
  - `ENTIDAD: str = "ALCACALI"`, `PREFIJO_TIPO: str = "D"`
  - `@dataclass FilaDecreto(numero_raw: str, fecha: str, anio_raw: str, pdf_url: str | None)`
  - `@dataclass PaginaParseada(filas: list[FilaDecreto], total_registros: int | None, total_paginas: int | None)`
  - `parse_pagina(html: str) -> PaginaParseada`
  - `normalizar_numero(texto: str) -> str | None`
  - `resolver_anio(anio_raw: str, fecha: str) -> int | None`
  - `ruta_destino(destino: Path, numero: str, anio: int, sufijo: int = 0) -> Path`
  - `es_pdf_valido(head_bytes: bytes, size: int) -> bool`
  - `_normalizar_url(url: str) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_core_cali_decretos.py`:

```python
from pathlib import Path

from core.cali_decretos import (
    es_pdf_valido,
    normalizar_numero,
    parse_pagina,
    resolver_anio,
    ruta_destino,
    _normalizar_url,
)

# One <tr> from a real paginador.php response, trimmed to two rows: one http PDF,
# one ftp PDF, plus the pager line page-1 responses carry.
_HTML = """
<table><thead><tr><th>TIPO</th></tr></thead><tbody>
<tr><td><center>DECRETO</center></td><td><center>0001</center></td>
<td><center>1974-01-02</center></td><td class='text-left'>Por el cual se impone una multa</td>
<td><a href="javascript:;" onMouseUp="MM_openBrWindow1('nota.php?cod=10860','descargar','')">Ver</a></td>
<td><center>1974</center></td><td><center>SECRETARIA GENERAL</center></td>
<td><button type='button' href="javascript:;" onMouseUp="MM_openBrWindow(10860,'http://www.cali.gov.co/aplicaciones/boletin_publicaciones/../boletin_publicaciones/imagenes_documentos_decretos/abc123.pdf','descargar','width=600,height=400')">Descargar</button></td></tr>
<tr><td><center>DECRETO</center></td><td><center>0001</center></td>
<td><center>1984-01-02</center></td><td class='text-left'>Otro</td>
<td><a href="javascript:;">Ver</a></td>
<td><center>1984</center></td><td><center>SECRETARIA GENERAL</center></td>
<td><button type='button' onMouseUp="MM_openBrWindow(23337,'ftp://ftp.cali.gov.co/DECRETOS/1984/DECRETO0001ENERO1984.pdf','descargar','width=600,height=400')">Descargar</button></td></tr>
</tbody>
<td colspan='10'><div><nav><ul class='pager'>
<li><a href='#'>Primero</a></li></ul></nav></div>
<b>71945 registros (filtrado de 71969 registros en total)</b>
<center><strong>Pagina 1/7195</strong></center></td></table>
"""


def test_parse_pagina_extracts_rows_pdf_urls_and_totals():
    pagina = parse_pagina(_HTML)
    assert len(pagina.filas) == 2
    assert pagina.filas[0].numero_raw == "0001"
    assert pagina.filas[0].fecha == "1974-01-02"
    assert pagina.filas[0].anio_raw == "1974"
    assert pagina.filas[0].pdf_url == (
        "https://www.cali.gov.co/aplicaciones/boletin_publicaciones/"
        "imagenes_documentos_decretos/abc123.pdf"
    )
    assert pagina.filas[1].pdf_url == "ftp://ftp.cali.gov.co/DECRETOS/1984/DECRETO0001ENERO1984.pdf"
    assert pagina.total_paginas == 7195
    assert pagina.total_registros == 71969


def test_parse_pagina_row_without_download_button_has_none_url():
    html = """
    <table><tbody><tr>
    <td>DECRETO</td><td>0005</td><td>1975-02-02</td><td>x</td><td>y</td><td>1975</td><td>SG</td>
    <td>sin boton</td></tr></tbody></table>
    """
    pagina = parse_pagina(html)
    assert len(pagina.filas) == 1
    assert pagina.filas[0].pdf_url is None
    assert pagina.total_paginas is None
    assert pagina.total_registros is None


def test_normalizar_numero():
    assert normalizar_numero("1") == "0001"
    assert normalizar_numero("0001") == "0001"
    assert normalizar_numero("1234") == "1234"
    assert normalizar_numero("12345") == "12345"
    assert normalizar_numero("0010A") == "0010A"
    assert normalizar_numero("13 bis") == "13-BIS"
    assert normalizar_numero("") is None
    assert normalizar_numero("—") is None
    assert normalizar_numero("   ") is None


def test_resolver_anio():
    assert resolver_anio("1996", "1996-01-02") == 1996
    assert resolver_anio("", "1996-01-02") == 1996
    assert resolver_anio("  ", "2019-12-31") == 2019
    assert resolver_anio("", "") is None
    assert resolver_anio("abcd", "no hay fecha") is None


def test_ruta_destino():
    base = Path("D:/DESCARGA")
    assert ruta_destino(base, "0010", 1987) == base / "DECRETOS" / "ALCACALI" / "1987" / "D_ALCACALI_0010_1987.pdf"
    assert ruta_destino(base, "0010", 1987, sufijo=2) == (
        base / "DECRETOS" / "ALCACALI" / "1987" / "D_ALCACALI_0010_1987_2.pdf"
    )


def test_es_pdf_valido():
    assert es_pdf_valido(b"%PDF", 5000) is True
    assert es_pdf_valido(b"<htm", 5000) is False
    assert es_pdf_valido(b"%PDF", 200) is False


def test_normalizar_url_collapses_dotdot_and_upgrades_http():
    assert _normalizar_url(
        "http://www.cali.gov.co/aplicaciones/boletin_publicaciones/../boletin_publicaciones/x/a.pdf"
    ) == "https://www.cali.gov.co/aplicaciones/boletin_publicaciones/x/a.pdf"
    # ftp URLs are left untouched
    assert _normalizar_url("ftp://ftp.cali.gov.co/x.pdf") == "ftp://ftp.cali.gov.co/x.pdf"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_core_cali_decretos.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.cali_decretos'`.

- [ ] **Step 3: Write the implementation**

Create `core/cali_decretos.py`:

```python
"""Herramientas puras para la descarga masiva de decretos de Cali (Laboratorio).

Sin red, sin FastAPI, sin Celery — solo parseo de una página de paginador.php,
normalización de número/año, armado de rutas, validación de "esto es un PDF", y
lectura/escritura/forma del archivo de estado. Ver
docs/superpowers/specs/2026-09-02-laboratorio-descarga-decretos-cali-design.md
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup

BASE_PAGINADOR = "https://www.cali.gov.co/aplicaciones/boletin_decretos/paginador.php"
ENTIDAD = "ALCACALI"
PREFIJO_TIPO = "D"

_MM_OPEN = re.compile(r"MM_openBrWindow\(\s*\d+\s*,\s*'([^']+)'")
_SOLO_DIGITOS = re.compile(r"^\d+$")
_NO_ALNUM_NI_GUION = re.compile(r"[^A-Z0-9-]")
_ANIO_4 = re.compile(r"(1[89]\d{2}|20\d{2})")
_PAGINA_DE = re.compile(r"Pagina\s+\d+\s*/\s*(\d+)")
_TOTAL_REGISTROS = re.compile(r"de\s+([\d.]+)\s+registros\s+en\s+total")
_DOTDOT = "/boletin_publicaciones/../boletin_publicaciones/"


@dataclass
class FilaDecreto:
    numero_raw: str
    fecha: str
    anio_raw: str
    pdf_url: str | None


@dataclass
class PaginaParseada:
    filas: list[FilaDecreto]
    total_registros: int | None
    total_paginas: int | None


def _normalizar_url(url: str) -> str:
    if url.lower().startswith("ftp://"):
        return url
    url = url.replace(_DOTDOT, "/boletin_publicaciones/")
    if url.startswith("http://www.cali.gov.co"):
        url = "https://www.cali.gov.co" + url[len("http://www.cali.gov.co"):]
    return url


def parse_pagina(html: str) -> PaginaParseada:
    soup = BeautifulSoup(html, "html.parser")
    filas: list[FilaDecreto] = []
    tbody = soup.find("tbody")
    for tr in tbody.find_all("tr") if tbody else []:
        celdas = tr.find_all("td")
        if len(celdas) < 7:
            continue
        pdf_url = None
        boton = tr.find("button")
        if boton is not None:
            atributo = boton.get("onmouseup") or ""
            m = _MM_OPEN.search(atributo)
            if m:
                pdf_url = _normalizar_url(m.group(1))
        filas.append(
            FilaDecreto(
                numero_raw=celdas[1].get_text(strip=True),
                fecha=celdas[2].get_text(strip=True),
                anio_raw=celdas[5].get_text(strip=True),
                pdf_url=pdf_url,
            )
        )

    mp = _PAGINA_DE.search(html)
    mr = _TOTAL_REGISTROS.search(html)
    return PaginaParseada(
        filas=filas,
        total_registros=int(mr.group(1).replace(".", "")) if mr else None,
        total_paginas=int(mp.group(1)) if mp else None,
    )


def normalizar_numero(texto: str) -> str | None:
    limpio = texto.strip()
    if _SOLO_DIGITOS.match(limpio):
        return f"{int(limpio):04d}"
    subido = re.sub(r"\s+", "-", limpio.upper())
    subido = _NO_ALNUM_NI_GUION.sub("", subido).strip("-")
    return subido or None


def resolver_anio(anio_raw: str, fecha: str) -> int | None:
    limpio = anio_raw.strip()
    if re.fullmatch(r"\d{4}", limpio):
        return int(limpio)
    m = _ANIO_4.search(fecha or "")
    return int(m.group(1)) if m else None


def ruta_destino(destino: Path, numero: str, anio: int, sufijo: int = 0) -> Path:
    nombre = f"{PREFIJO_TIPO}_{ENTIDAD}_{numero}_{anio}"
    if sufijo:
        nombre = f"{nombre}_{sufijo}"
    return destino / "DECRETOS" / ENTIDAD / str(anio) / f"{nombre}.pdf"


def es_pdf_valido(head_bytes: bytes, size: int) -> bool:
    return size > 1024 and head_bytes[:4] == b"%PDF"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_core_cali_decretos.py -v`
Expected: PASS (all 8 tests in this file so far).

- [ ] **Step 5: Commit**

```bash
git add core/cali_decretos.py tests/test_core_cali_decretos.py
git commit -m "feat(cali-decretos): pure parsing and naming helpers"
```

---

## Task 2: State-file helpers

**Files:**
- Modify: `core/cali_decretos.py` (append the state helpers)
- Test: `tests/test_core_cali_decretos.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `NOMBRE_ESTADO: str = "_descarga_estado.json"`, `MAX_LISTA: int = 1000`, `TAREA_VIVA_SEGUNDOS: int = 300`
  - `ruta_estado(destino: Path) -> Path`
  - `ahora_iso() -> str` (UTC, format `"%Y-%m-%dT%H:%M:%SZ"`)
  - `estado_inicial() -> dict`
  - `leer_estado(destino: Path) -> dict | None`
  - `escribir_estado(destino: Path, estado: dict) -> None` (sets `estado["actualizado"]` then atomic-writes)
  - `recortar_listas(estado: dict) -> None`
  - `tarea_viva(estado: dict, ahora: datetime) -> bool`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_core_cali_decretos.py`:

```python
import json
from datetime import datetime, timedelta, timezone

from core.cali_decretos import (
    MAX_LISTA,
    ahora_iso,
    escribir_estado,
    estado_inicial,
    leer_estado,
    recortar_listas,
    ruta_estado,
    tarea_viva,
)


def test_leer_estado_returns_none_when_missing(tmp_path):
    assert leer_estado(tmp_path) is None


def test_escribir_then_leer_roundtrips_and_is_atomic(tmp_path):
    estado = estado_inicial()
    estado["descargados"] = 7
    escribir_estado(tmp_path, estado)
    assert not (ruta_estado(tmp_path).with_name("_descarga_estado.json.tmp")).exists()
    vuelto = leer_estado(tmp_path)
    assert vuelto["descargados"] == 7
    assert vuelto["estado"] == "en_curso"
    assert vuelto["actualizado"]  # touched on write


def test_estado_inicial_shape():
    estado = estado_inicial()
    for clave in (
        "version", "estado", "iniciado", "actualizado", "terminado",
        "total_registros_sitio", "total_paginas", "ultima_pagina_completada",
        "descargados", "ya_existian", "duplicados", "fallidos_count",
        "detener_solicitado", "concurrencia_actual", "avisos", "fallidos",
    ):
        assert clave in estado
    assert estado["estado"] == "en_curso"
    assert estado["ultima_pagina_completada"] == 0
    assert estado["concurrencia_actual"] == 8


def test_recortar_listas_caps_at_max():
    estado = estado_inicial()
    estado["avisos"] = [{"tipo": "duplicado"}] * (MAX_LISTA + 50)
    estado["fallidos"] = [{"url": "x"}] * (MAX_LISTA + 50)
    recortar_listas(estado)
    assert len(estado["avisos"]) == MAX_LISTA
    assert len(estado["fallidos"]) == MAX_LISTA


def test_tarea_viva():
    ahora = datetime(2026, 9, 2, 15, 0, 0, tzinfo=timezone.utc)
    reciente = estado_inicial()
    reciente["actualizado"] = (ahora - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert tarea_viva(reciente, ahora) is True

    viejo = estado_inicial()
    viejo["actualizado"] = (ahora - timedelta(seconds=600)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert tarea_viva(viejo, ahora) is False

    terminado = estado_inicial()
    terminado["estado"] = "terminado"
    terminado["actualizado"] = ahora.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert tarea_viva(terminado, ahora) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_core_cali_decretos.py -k "estado or recortar or tarea_viva" -v`
Expected: FAIL — `ImportError` for the new names.

- [ ] **Step 3: Write the implementation**

Append to `core/cali_decretos.py`:

```python
import json
import os
from datetime import datetime, timezone

NOMBRE_ESTADO = "_descarga_estado.json"
MAX_LISTA = 1000
TAREA_VIVA_SEGUNDOS = 300


def ruta_estado(destino: Path) -> Path:
    return destino / NOMBRE_ESTADO


def ahora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def estado_inicial() -> dict:
    ahora = ahora_iso()
    return {
        "version": 1,
        "estado": "en_curso",
        "iniciado": ahora,
        "actualizado": ahora,
        "terminado": None,
        "total_registros_sitio": None,
        "total_paginas": None,
        "ultima_pagina_completada": 0,
        "descargados": 0,
        "ya_existian": 0,
        "duplicados": 0,
        "fallidos_count": 0,
        "detener_solicitado": False,
        "concurrencia_actual": 8,
        "avisos": [],
        "fallidos": [],
    }


def leer_estado(destino: Path) -> dict | None:
    ruta = ruta_estado(destino)
    if not ruta.is_file():
        return None
    return json.loads(ruta.read_text(encoding="utf-8"))


def escribir_estado(destino: Path, estado: dict) -> None:
    estado["actualizado"] = ahora_iso()
    ruta = ruta_estado(destino)
    tmp = ruta.with_name(ruta.name + ".tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, ruta)


def recortar_listas(estado: dict) -> None:
    estado["avisos"] = estado["avisos"][:MAX_LISTA]
    estado["fallidos"] = estado["fallidos"][:MAX_LISTA]


def tarea_viva(estado: dict, ahora: datetime) -> bool:
    if estado.get("estado") != "en_curso":
        return False
    try:
        actualizado = datetime.strptime(estado["actualizado"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except (KeyError, ValueError, TypeError):
        return False
    return (ahora - actualizado).total_seconds() < TAREA_VIVA_SEGUNDOS
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_core_cali_decretos.py -v`
Expected: PASS (all tests in the file).

- [ ] **Step 5: Commit**

```bash
git add core/cali_decretos.py tests/test_core_cali_decretos.py
git commit -m "feat(cali-decretos): state-file helpers"
```

---

## Task 3: Single-PDF downloader with retries

**Files:**
- Modify: `worker/tasks.py` (add helpers near the other module-level download helpers)
- Test: `tests/test_worker_cali_decretos.py`

**Interfaces:**
- Consumes: `core.cali_decretos.es_pdf_valido`.
- Produces (all in `worker/tasks.py`):
  - `_CALI_USER_AGENT: str`
  - `_CALI_ESPERAS: tuple[int, int, int] = (2, 8, 30)`
  - `_descargar_http(url: str, destino_tmp: Path) -> tuple[bytes, int]` — streams to `destino_tmp`, returns `(primeros_4_bytes, tamaño_total)`. Raises on HTTP error.
  - `_descargar_ftp(url: str, destino_tmp: Path) -> tuple[bytes, int]` — same contract over FTP (passive).
  - `_clasificar_error(exc: Exception) -> str` — `"timeout"` / `"conexion"` / `"http-<código>"` / `"error"`.
  - `_descargar_un_pdf(url: str, destino_final: Path, tmp_dir: Path, dormir=time.sleep) -> str | None` — returns `None` on success (file moved to `destino_final`), else a reason string. `ftp://` failures always report `"ftp-no-disponible"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_worker_cali_decretos.py`:

```python
from pathlib import Path

import responses

import worker.tasks as tasks

_PDF_BYTES = b"%PDF-1.6\n" + b"x" * 5000
_HTML_BYTES = b"<html><body>error 404</body></html>"


@responses.activate
def test_descargar_un_pdf_http_success_moves_file(tmp_path):
    responses.add(responses.GET, "https://x.test/a.pdf", body=_PDF_BYTES, status=200)
    destino = tmp_path / "out" / "D_ALCACALI_0001_1974.pdf"
    motivo = tasks._descargar_un_pdf("https://x.test/a.pdf", destino, tmp_path, dormir=lambda _s: None)
    assert motivo is None
    assert destino.read_bytes() == _PDF_BYTES


@responses.activate
def test_descargar_un_pdf_non_pdf_body_fails_after_retries(tmp_path):
    responses.add(responses.GET, "https://x.test/b.pdf", body=_HTML_BYTES, status=200)
    responses.add(responses.GET, "https://x.test/b.pdf", body=_HTML_BYTES, status=200)
    responses.add(responses.GET, "https://x.test/b.pdf", body=_HTML_BYTES, status=200)
    responses.add(responses.GET, "https://x.test/b.pdf", body=_HTML_BYTES, status=200)
    destino = tmp_path / "out" / "x.pdf"
    motivo = tasks._descargar_un_pdf("https://x.test/b.pdf", destino, tmp_path, dormir=lambda _s: None)
    assert motivo == "no-es-pdf"
    assert not destino.exists()


@responses.activate
def test_descargar_un_pdf_http_error_then_success(tmp_path):
    responses.add(responses.GET, "https://x.test/c.pdf", status=503)
    responses.add(responses.GET, "https://x.test/c.pdf", body=_PDF_BYTES, status=200)
    destino = tmp_path / "out" / "c.pdf"
    motivo = tasks._descargar_un_pdf("https://x.test/c.pdf", destino, tmp_path, dormir=lambda _s: None)
    assert motivo is None
    assert destino.read_bytes() == _PDF_BYTES


def test_descargar_un_pdf_ftp_failure_reports_ftp_no_disponible(tmp_path, monkeypatch):
    def _boom(url, destino_tmp):
        raise OSError("ftp unreachable")

    monkeypatch.setattr(tasks, "_descargar_ftp", _boom)
    destino = tmp_path / "out" / "d.pdf"
    motivo = tasks._descargar_un_pdf(
        "ftp://ftp.cali.gov.co/DECRETOS/1984/x.pdf", destino, tmp_path, dormir=lambda _s: None
    )
    assert motivo == "ftp-no-disponible"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_worker_cali_decretos.py -v`
Expected: FAIL — `AttributeError: module 'worker.tasks' has no attribute '_descargar_un_pdf'`.

- [ ] **Step 3: Write the implementation**

In `worker/tasks.py`, confirm the top of the file already has `import time`, `from pathlib import Path`, `import requests`. Add `import ftplib` and `from urllib.parse import urlsplit` to the imports. Then add, near `_download_and_upload_one`:

```python
from core import cali_decretos as cali

_CALI_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_CALI_ESPERAS = (2, 8, 30)
_CALI_CHUNK = 64 * 1024


def _descargar_http(url: str, destino_tmp: Path) -> tuple[bytes, int]:
    with requests.get(
        url,
        stream=True,
        timeout=60,
        allow_redirects=True,
        headers={"User-Agent": _CALI_USER_AGENT},
    ) as respuesta:
        respuesta.raise_for_status()
        head = b""
        size = 0
        with open(destino_tmp, "wb") as archivo:
            for chunk in respuesta.iter_content(_CALI_CHUNK):
                if not chunk:
                    continue
                if len(head) < 4:
                    head = (head + chunk)[:4]
                size += len(chunk)
                archivo.write(chunk)
    return head, size


def _descargar_ftp(url: str, destino_tmp: Path) -> tuple[bytes, int]:
    partes = urlsplit(url)
    ftp = ftplib.FTP(timeout=60)
    ftp.connect(partes.hostname, partes.port or 21)
    ftp.login()
    ftp.set_pasv(True)
    head = b""
    size = 0
    with open(destino_tmp, "wb") as archivo:
        def _recibir(datos: bytes) -> None:
            nonlocal head, size
            if len(head) < 4:
                head = (head + datos)[:4]
            size += len(datos)
            archivo.write(datos)

        ftp.retrbinary(f"RETR {partes.path}", _recibir)
    try:
        ftp.quit()
    except Exception:  # noqa: BLE001 — cerrar la conexión no debe romper una descarga ya lograda
        pass
    return head, size


def _clasificar_error(exc: Exception) -> str:
    if isinstance(exc, requests.Timeout):
        return "timeout"
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return f"http-{exc.response.status_code}"
    if isinstance(exc, requests.ConnectionError):
        return "conexion"
    return "error"


def _descargar_un_pdf(url: str, destino_final: Path, tmp_dir: Path, dormir=time.sleep) -> str | None:
    """Descarga un PDF con reintentos. Devuelve None si quedó guardado y validado
    en `destino_final`; si no, un string con el motivo del último fallo."""
    es_ftp = url.lower().startswith("ftp://")
    tmp = tmp_dir / f"descarga_{abs(hash(url))}.part"
    motivo = "error"
    for espera in (0, *_CALI_ESPERAS):
        if espera:
            dormir(espera)
        try:
            if es_ftp:
                head, size = _descargar_ftp(url, tmp)
            else:
                head, size = _descargar_http(url, tmp)
        except Exception as exc:  # noqa: BLE001 — cualquier fallo de red se reintenta
            motivo = "ftp-no-disponible" if es_ftp else _clasificar_error(exc)
            continue
        if not cali.es_pdf_valido(head, size):
            motivo = "no-es-pdf"
            continue
        destino_final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, destino_final)
        return None
    tmp.unlink(missing_ok=True)
    return motivo
```

`worker/tasks.py` already imports `os`? It imports `shutil`, `tempfile` — add `import os` if absent.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_worker_cali_decretos.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add worker/tasks.py tests/test_worker_cali_decretos.py
git commit -m "feat(cali-decretos): single-PDF downloader with retries and FTP support"
```

---

## Task 4: The Celery task — page walk, concurrency, resume, stop

**Files:**
- Modify: `worker/tasks.py` (add the task and its helpers)
- Test: `tests/test_worker_cali_decretos.py` (append)

**Interfaces:**
- Consumes: everything from Task 3, plus `core.cali_decretos` (`parse_pagina`, `normalizar_numero`, `resolver_anio`, `ruta_destino`, `estado_inicial`, `leer_estado`, `escribir_estado`, `recortar_listas`, `ahora_iso`, `BASE_PAGINADOR`).
- Produces (in `worker/tasks.py`):
  - `_pedir_pagina(sesion: requests.Session, pag: int, dormir=time.sleep) -> cali.PaginaParseada | None`
  - `_preparar_trabajos(pagina, destino: Path, vistos: set, estado: dict) -> list[tuple[str, Path]]` — one `(url, destino_final)` per downloadable row; mutates `estado["avisos"]`, `estado["duplicados"]`, `estado["ya_existian"]` as it goes; skips rows already on disk.
  - `_ejecutar_trabajos(trabajos, tmp_dir: Path, estado: dict, fallos_seguidos: int) -> int` — runs the pool at `estado["concurrencia_actual"]`, updates `descargados` / `fallidos` / `fallidos_count`, applies the 5-consecutive-failures → concurrency 3 rule, returns the new `fallos_seguidos`.
  - `_pasada_final_fallidos(destino: Path, estado: dict, tmp_dir: Path) -> None` — one retry sweep over `estado["fallidos"]`.
  - `descargar_decretos_cali_task(destino_str: str) -> None` — `@celery_app.task(name="worker.descargar_decretos_cali_task")`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_worker_cali_decretos.py`:

```python
import json

from core.cali_decretos import leer_estado

_BASE = "https://www.cali.gov.co/aplicaciones/boletin_decretos/paginador.php"


def _pagina_html(filas, total_paginas=2):
    trs = ""
    for numero, fecha, anio, url in filas:
        boton = (
            f"<button onMouseUp=\"MM_openBrWindow(1,'{url}','descargar','')\">Descargar</button>"
            if url
            else "<span>sin boton</span>"
        )
        trs += (
            f"<tr><td>DECRETO</td><td>{numero}</td><td>{fecha}</td><td>desc</td>"
            f"<td>nota</td><td>{anio}</td><td>SG</td><td>{boton}</td></tr>"
        )
    return (
        f"<table><tbody>{trs}</tbody>"
        f"<td colspan='10'><b>10 registros (filtrado de 71969 registros en total)</b>"
        f"<strong>Pagina 1/{total_paginas}</strong></td></table>"
    )


@responses.activate
def test_task_happy_path_two_pages_builds_tree_and_marks_terminado(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)

    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "1"})],
        body=_pagina_html([("0001", "1974-01-02", "1974", "https://pdf.test/a.pdf")]),
    )
    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "2"})],
        body=_pagina_html([("0002", "1975-05-05", "1975", "https://pdf.test/b.pdf")]),
    )
    responses.add(responses.GET, "https://pdf.test/a.pdf", body=_PDF_BYTES, status=200)
    responses.add(responses.GET, "https://pdf.test/b.pdf", body=_PDF_BYTES, status=200)

    tasks.descargar_decretos_cali_task(str(tmp_path))

    assert (tmp_path / "DECRETOS" / "ALCACALI" / "1974" / "D_ALCACALI_0001_1974.pdf").read_bytes() == _PDF_BYTES
    assert (tmp_path / "DECRETOS" / "ALCACALI" / "1975" / "D_ALCACALI_0002_1975.pdf").exists()
    estado = leer_estado(tmp_path)
    assert estado["estado"] == "terminado"
    assert estado["descargados"] == 2
    assert estado["ultima_pagina_completada"] == 2
    assert estado["total_paginas"] == 2


@responses.activate
def test_task_pdf_failure_lands_in_fallidos_without_aborting(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)
    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "1"})],
        body=_pagina_html(
            [
                ("0001", "1974-01-02", "1974", "https://pdf.test/ok.pdf"),
                ("0002", "1974-02-02", "1974", "https://pdf.test/bad.pdf"),
            ],
            total_paginas=1,
        ),
    )
    responses.add(responses.GET, "https://pdf.test/ok.pdf", body=_PDF_BYTES, status=200)
    responses.add(responses.GET, "https://pdf.test/bad.pdf", status=500)

    tasks.descargar_decretos_cali_task(str(tmp_path))

    estado = leer_estado(tmp_path)
    assert estado["estado"] == "terminado_con_fallos"
    assert estado["descargados"] == 1
    assert estado["fallidos_count"] == 1
    assert estado["fallidos"][0]["numero"] == "0002"
    assert estado["fallidos"][0]["url"] == "https://pdf.test/bad.pdf"


@responses.activate
def test_task_skips_files_already_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)
    ya = tmp_path / "DECRETOS" / "ALCACALI" / "1974" / "D_ALCACALI_0001_1974.pdf"
    ya.parent.mkdir(parents=True, exist_ok=True)
    ya.write_bytes(_PDF_BYTES)

    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "1"})],
        body=_pagina_html([("0001", "1974-01-02", "1974", "https://pdf.test/a.pdf")], total_paginas=1),
    )
    # No mock for https://pdf.test/a.pdf on purpose: it must NOT be requested.

    tasks.descargar_decretos_cali_task(str(tmp_path))

    estado = leer_estado(tmp_path)
    assert estado["ya_existian"] == 1
    assert estado["descargados"] == 0


@responses.activate
def test_task_duplicate_numero_anio_gets_suffix_and_aviso(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)
    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "1"})],
        body=_pagina_html(
            [
                ("0010", "1987-01-02", "1987", "https://pdf.test/one.pdf"),
                ("0010", "1987-03-03", "1987", "https://pdf.test/two.pdf"),
            ],
            total_paginas=1,
        ),
    )
    responses.add(responses.GET, "https://pdf.test/one.pdf", body=_PDF_BYTES, status=200)
    responses.add(responses.GET, "https://pdf.test/two.pdf", body=_PDF_BYTES, status=200)

    tasks.descargar_decretos_cali_task(str(tmp_path))

    y = tmp_path / "DECRETOS" / "ALCACALI" / "1987"
    assert (y / "D_ALCACALI_0010_1987.pdf").exists()
    assert (y / "D_ALCACALI_0010_1987_2.pdf").exists()
    estado = leer_estado(tmp_path)
    assert estado["duplicados"] == 1
    assert any(a["tipo"] == "duplicado" for a in estado["avisos"])


@responses.activate
def test_task_stops_between_pages_when_detener_solicitado(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)
    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "1"})],
        body=_pagina_html([("0001", "1974-01-02", "1974", "https://pdf.test/a.pdf")], total_paginas=5),
    )
    responses.add(responses.GET, "https://pdf.test/a.pdf", body=_PDF_BYTES, status=200)

    real_escribir = tasks.cali.escribir_estado

    def _escribir_y_pedir_stop(destino, estado):
        real_escribir(destino, estado)
        if estado.get("ultima_pagina_completada") == 1:
            actual = tasks.cali.leer_estado(destino)
            actual["detener_solicitado"] = True
            real_escribir(destino, actual)

    monkeypatch.setattr(tasks.cali, "escribir_estado", _escribir_y_pedir_stop)

    tasks.descargar_decretos_cali_task(str(tmp_path))

    estado = leer_estado(tmp_path)
    assert estado["estado"] == "detenido"
    assert estado["ultima_pagina_completada"] == 1


@responses.activate
def test_task_resume_does_not_rewalk_completed_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)
    estado = tasks.cali.estado_inicial()
    estado.update(estado="detenido", total_paginas=2, ultima_pagina_completada=1)
    tasks.cali.escribir_estado(tmp_path, estado)

    # Only pag=1 (mandatory totals refresh) and pag=2 are mocked; pag=1 has no PDF
    # so re-reading it must not try to download anything.
    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "1"})],
        body=_pagina_html([("0001", "1974-01-02", "1974", None)], total_paginas=2),
    )
    responses.add(
        responses.GET, _BASE, status=200,
        match=[responses.matchers.query_param_matcher({"pag": "2"})],
        body=_pagina_html([("0002", "1975-05-05", "1975", "https://pdf.test/b.pdf")], total_paginas=2),
    )
    responses.add(responses.GET, "https://pdf.test/b.pdf", body=_PDF_BYTES, status=200)

    tasks.descargar_decretos_cali_task(str(tmp_path))

    final = leer_estado(tmp_path)
    assert final["estado"] == "terminado"
    assert (tmp_path / "DECRETOS" / "ALCACALI" / "1975" / "D_ALCACALI_0002_1975.pdf").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_worker_cali_decretos.py -v`
Expected: FAIL — `AttributeError: module 'worker.tasks' has no attribute 'descargar_decretos_cali_task'`.

- [ ] **Step 3: Write the implementation**

Append to `worker/tasks.py`:

```python
_CALI_INTENTOS_PAGINA = 4
_CALI_FALLOS_PARA_BAJAR_CONCURRENCIA = 5
_CALI_CONCURRENCIA_REDUCIDA = 3


def _pedir_pagina(sesion: requests.Session, pag: int, dormir=time.sleep) -> "cali.PaginaParseada | None":
    url = f"{cali.BASE_PAGINADOR}?pag={pag}"
    for espera in (0, *_CALI_ESPERAS):
        if espera:
            dormir(espera)
        try:
            respuesta = sesion.get(url, timeout=30, allow_redirects=True)
            respuesta.raise_for_status()
        except Exception:  # noqa: BLE001 — se reintenta cualquier fallo de red
            continue
        return cali.parse_pagina(respuesta.text)
    return None


def _preparar_trabajos(pagina, destino: Path, vistos: set, estado: dict) -> list[tuple[str, Path]]:
    trabajos: list[tuple[str, Path]] = []
    for fila in pagina.filas:
        if fila.pdf_url is None:
            estado["avisos"].append(
                {"tipo": "fila_sin_enlace", "numero": fila.numero_raw or None, "anio": None}
            )
            continue
        numero = cali.normalizar_numero(fila.numero_raw)
        if numero is None:
            estado["avisos"].append({"tipo": "sin_numero", "anio": None, "url": fila.pdf_url})
            continue
        anio = cali.resolver_anio(fila.anio_raw, fila.fecha)
        if anio is None:
            estado["avisos"].append({"tipo": "sin_anio", "numero": numero, "url": fila.pdf_url})
            continue

        clave = (numero, anio)
        sufijo = 0
        if clave in vistos:
            sufijo = 2
            destino_final = cali.ruta_destino(destino, numero, anio, sufijo)
            while destino_final.exists():
                sufijo += 1
                destino_final = cali.ruta_destino(destino, numero, anio, sufijo)
            estado["duplicados"] += 1
            estado["avisos"].append(
                {
                    "tipo": "duplicado",
                    "numero": numero,
                    "anio": anio,
                    "guardado_como": destino_final.name,
                }
            )
        else:
            vistos.add(clave)
            destino_final = cali.ruta_destino(destino, numero, anio)
            if destino_final.exists() and destino_final.stat().st_size > 1024:
                estado["ya_existian"] += 1
                continue

        trabajos.append((fila.pdf_url, destino_final))
    return trabajos


def _ejecutar_trabajos(trabajos, tmp_dir: Path, estado: dict, fallos_seguidos: int) -> int:
    if not trabajos:
        return fallos_seguidos
    with ThreadPoolExecutor(max_workers=estado["concurrencia_actual"]) as executor:
        futuros = {
            executor.submit(_descargar_un_pdf, url, destino_final, tmp_dir): (url, destino_final)
            for url, destino_final in trabajos
        }
        for futuro in as_completed(futuros):
            url, destino_final = futuros[futuro]
            motivo = futuro.result()
            if motivo is None:
                estado["descargados"] += 1
                fallos_seguidos = 0
                continue
            numero_anio = _numero_anio_de_ruta(destino_final)
            estado["fallidos"].append(
                {
                    "numero": numero_anio[0],
                    "anio": numero_anio[1],
                    "url": url,
                    "motivo": motivo,
                    "intentos": len(_CALI_ESPERAS) + 1,
                }
            )
            estado["fallidos_count"] += 1
            fallos_seguidos += 1
            if (
                fallos_seguidos >= _CALI_FALLOS_PARA_BAJAR_CONCURRENCIA
                and estado["concurrencia_actual"] != _CALI_CONCURRENCIA_REDUCIDA
            ):
                estado["concurrencia_actual"] = _CALI_CONCURRENCIA_REDUCIDA
                estado["avisos"].append(
                    {"tipo": "concurrencia_reducida", "numero": None, "anio": None}
                )
    return fallos_seguidos


def _numero_anio_de_ruta(ruta: Path) -> tuple[str | None, int | None]:
    # D_ALCACALI_{numero}_{anio}[_n].pdf  → (numero, anio)
    partes = ruta.stem.split("_")
    if len(partes) >= 4 and partes[0] == cali.PREFIJO_TIPO:
        anio = partes[3] if partes[3].isdigit() else None
        return partes[2], int(anio) if anio else None
    return None, None


def _pasada_final_fallidos(destino: Path, estado: dict, tmp_dir: Path) -> None:
    pendientes = estado["fallidos"]
    estado["fallidos"] = []
    estado["fallidos_count"] = 0
    for entrada in pendientes:
        numero, anio = entrada.get("numero"), entrada.get("anio")
        if numero and anio:
            destino_final = cali.ruta_destino(destino, numero, anio)
        else:
            destino_final = tmp_dir / "reintento.pdf"
        motivo = _descargar_un_pdf(entrada["url"], destino_final, tmp_dir)
        if motivo is None and numero and anio:
            estado["descargados"] += 1
        else:
            estado["fallidos"].append({**entrada, "motivo": motivo or entrada["motivo"]})
            estado["fallidos_count"] += 1
    cali.recortar_listas(estado)
    cali.escribir_estado(destino, estado)


@celery_app.task(name="worker.descargar_decretos_cali_task")
def descargar_decretos_cali_task(destino_str: str) -> None:
    destino = Path(destino_str)
    estado = cali.leer_estado(destino) or cali.estado_inicial()
    estado["estado"] = "en_curso"
    estado["detener_solicitado"] = False
    cali.escribir_estado(destino, estado)

    sesion = requests.Session()
    sesion.headers.update({"User-Agent": _CALI_USER_AGENT})
    vistos: set[tuple[str, int]] = set()
    fallos_seguidos = 0

    try:
        with tempfile.TemporaryDirectory(prefix="cali_decretos_") as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)

            primera = _pedir_pagina(sesion, 1)
            if primera is not None:
                if primera.total_paginas:
                    estado["total_paginas"] = primera.total_paginas
                if primera.total_registros:
                    estado["total_registros_sitio"] = primera.total_registros
                cali.escribir_estado(destino, estado)

            total_paginas = estado["total_paginas"] or 0
            inicio = estado["ultima_pagina_completada"] + 1

            for pag in range(inicio, total_paginas + 1):
                fresco = cali.leer_estado(destino)
                if fresco and fresco.get("detener_solicitado"):
                    estado["detener_solicitado"] = True
                    estado["estado"] = "detenido"
                    cali.escribir_estado(destino, estado)
                    return

                pagina = primera if pag == 1 else _pedir_pagina(sesion, pag)
                if pagina is None:
                    estado["fallidos"].append(
                        {
                            "numero": None,
                            "anio": None,
                            "url": f"{cali.BASE_PAGINADOR}?pag={pag}",
                            "motivo": "pagina",
                            "intentos": _CALI_INTENTOS_PAGINA,
                        }
                    )
                    estado["fallidos_count"] += 1
                    estado["ultima_pagina_completada"] = pag
                    cali.recortar_listas(estado)
                    cali.escribir_estado(destino, estado)
                    continue

                trabajos = _preparar_trabajos(pagina, destino, vistos, estado)
                fallos_seguidos = _ejecutar_trabajos(trabajos, tmp_dir, estado, fallos_seguidos)
                estado["ultima_pagina_completada"] = pag
                cali.recortar_listas(estado)
                cali.escribir_estado(destino, estado)

            _pasada_final_fallidos(destino, estado, tmp_dir)

        estado["estado"] = "terminado_con_fallos" if estado["fallidos"] else "terminado"
        estado["terminado"] = cali.ahora_iso()
        cali.recortar_listas(estado)
        cali.escribir_estado(destino, estado)
    except Exception as exc:  # noqa: BLE001 — nunca dejar el estado en "en_curso"
        logger.exception("descargar_decretos_cali_task falló")
        estado["estado"] = "terminado_con_fallos"
        estado["avisos"].append({"tipo": "error_inesperado", "numero": None, "anio": None, "url": str(exc)})
        cali.recortar_listas(estado)
        cali.escribir_estado(destino, estado)
```

Notes:
- The stop test monkeypatches `cali.escribir_estado`; because the task calls it as `cali.escribir_estado(...)` (module attribute), the patch takes effect. Keep that call form — do **not** `from core.cali_decretos import escribir_estado`.
- The `time` module must be reachable as `tasks.time` for the tests' `monkeypatch.setattr(tasks.time, "sleep", ...)` — it already is (`import time` at the top of `worker/tasks.py`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_worker_cali_decretos.py -v`
Expected: PASS (all 10 tests).

- [ ] **Step 5: Run the full core+worker suites for regressions**

Run: `python -m pytest tests/test_core_cali_decretos.py tests/test_worker_cali_decretos.py tests/test_tasks.py -v`
Expected: PASS. (`test_tasks.py` must be unaffected — the only shared file is `worker/tasks.py`, appended to.)

- [ ] **Step 6: Commit**

```bash
git add worker/tasks.py tests/test_worker_cali_decretos.py
git commit -m "feat(cali-decretos): resumable Celery task for the full page walk"
```

---

## Task 5: API router + schemas

**Files:**
- Modify: `api/schemas.py` (append the 5 models)
- Create: `api/routers/cali_decretos.py`
- Modify: `api/main.py` (import + `include_router`)
- Test: `tests/test_api_cali_decretos.py`

**Interfaces:**
- Consumes: `core.cali_decretos` (`leer_estado`, `escribir_estado`, `estado_inicial`, `tarea_viva`), `worker.tasks.descargar_decretos_cali_task`, `api.deps.require_admin`.
- Produces:
  - `api/schemas.py`: `CaliDecretosStartRequest`, `CaliDecretosStopRequest`, `CaliDecretosAviso`, `CaliDecretosFallido`, `CaliDecretosEstado`.
  - `api/routers/cali_decretos.py`: `router` with `POST /cali-decretos/start`, `GET /cali-decretos/status`, `POST /cali-decretos/stop`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_cali_decretos.py`:

```python
from pathlib import Path

import pytest

import api.routers.cali_decretos as router_module


@pytest.fixture(autouse=True)
def _no_real_celery(monkeypatch):
    class _NoopTask:
        def delay(self, *args, **kwargs):
            return None

    monkeypatch.setattr(router_module, "descargar_decretos_cali_task", _NoopTask())


def test_start_requires_authentication(api_client, tmp_path):
    assert api_client.post("/cali-decretos/start", json={"dest_path": str(tmp_path)}).status_code == 401


def test_endpoints_reject_non_admin(api_client, auth_header, tmp_path):
    for method, path, body in [
        ("post", "/cali-decretos/start", {"dest_path": str(tmp_path)}),
        ("post", "/cali-decretos/stop", {"dest_path": str(tmp_path)}),
    ]:
        assert getattr(api_client, method)(path, json=body, headers=auth_header).status_code == 403
    assert api_client.get(
        "/cali-decretos/status", params={"dest_path": str(tmp_path)}, headers=auth_header
    ).status_code == 403


def test_start_404_for_missing_directory(api_client, admin_auth_header, tmp_path):
    resp = api_client.post(
        "/cali-decretos/start", json={"dest_path": str(tmp_path / "nope")}, headers=admin_auth_header
    )
    assert resp.status_code == 404


def test_start_creates_state_and_enqueues(api_client, admin_auth_header, tmp_path):
    resp = api_client.post(
        "/cali-decretos/start", json={"dest_path": str(tmp_path)}, headers=admin_auth_header
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["estado"] == "en_curso"
    assert (tmp_path / "_descarga_estado.json").is_file()


def test_start_409_when_task_is_alive(api_client, admin_auth_header, tmp_path):
    from core.cali_decretos import escribir_estado, estado_inicial

    escribir_estado(tmp_path, estado_inicial())  # freshly "en_curso", actualizado = now
    resp = api_client.post(
        "/cali-decretos/start", json={"dest_path": str(tmp_path)}, headers=admin_auth_header
    )
    assert resp.status_code == 409


def test_status_404_without_state_then_returns_it(api_client, admin_auth_header, tmp_path):
    assert api_client.get(
        "/cali-decretos/status", params={"dest_path": str(tmp_path)}, headers=admin_auth_header
    ).status_code == 404

    from core.cali_decretos import escribir_estado, estado_inicial

    escribir_estado(tmp_path, estado_inicial())
    resp = api_client.get(
        "/cali-decretos/status", params={"dest_path": str(tmp_path)}, headers=admin_auth_header
    )
    assert resp.status_code == 200
    assert resp.json()["estado"] == "en_curso"


def test_stop_sets_detener_solicitado(api_client, admin_auth_header, tmp_path):
    from core.cali_decretos import escribir_estado, estado_inicial, leer_estado

    escribir_estado(tmp_path, estado_inicial())
    resp = api_client.post(
        "/cali-decretos/stop", json={"dest_path": str(tmp_path)}, headers=admin_auth_header
    )
    assert resp.status_code == 200
    assert leer_estado(tmp_path)["detener_solicitado"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api_cali_decretos.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.routers.cali_decretos'`.

- [ ] **Step 3: Append the schemas**

At the end of `api/schemas.py`:

```python
class CaliDecretosStartRequest(BaseModel):
    dest_path: str


class CaliDecretosStopRequest(BaseModel):
    dest_path: str


class CaliDecretosAviso(BaseModel):
    tipo: str
    numero: Optional[str] = None
    anio: Optional[int] = None
    url: Optional[str] = None
    guardado_como: Optional[str] = None


class CaliDecretosFallido(BaseModel):
    numero: Optional[str] = None
    anio: Optional[int] = None
    url: str
    motivo: str
    intentos: int


class CaliDecretosEstado(BaseModel):
    version: int
    estado: str
    iniciado: str
    actualizado: str
    terminado: Optional[str] = None
    total_registros_sitio: Optional[int] = None
    total_paginas: Optional[int] = None
    ultima_pagina_completada: int
    descargados: int
    ya_existian: int
    duplicados: int
    fallidos_count: int
    detener_solicitado: bool
    concurrencia_actual: int
    avisos: list[CaliDecretosAviso]
    fallidos: list[CaliDecretosFallido]
```

- [ ] **Step 4: Create the router**

Create `api/routers/cali_decretos.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from api.deps import require_admin
from api.schemas import CaliDecretosEstado, CaliDecretosStartRequest, CaliDecretosStopRequest
from core import cali_decretos as cali
from worker.tasks import descargar_decretos_cali_task

router = APIRouter(prefix="/cali-decretos", dependencies=[Depends(require_admin)])


def _directorio(dest_path: str) -> Path:
    destino = Path(dest_path)
    if not destino.is_dir():
        raise HTTPException(status_code=404, detail="La ruta no existe o no es una carpeta")
    return destino


@router.post("/start", response_model=CaliDecretosEstado)
def start(payload: CaliDecretosStartRequest):
    destino = _directorio(payload.dest_path)
    estado = cali.leer_estado(destino)
    if estado is not None and cali.tarea_viva(estado, datetime.now(timezone.utc)):
        raise HTTPException(status_code=409, detail="Ya hay una descarga en curso para esa carpeta")
    if estado is None:
        estado = cali.estado_inicial()
    else:
        estado["estado"] = "en_curso"
        estado["detener_solicitado"] = False
    cali.escribir_estado(destino, estado)
    descargar_decretos_cali_task.delay(str(destino))
    return estado


@router.get("/status", response_model=CaliDecretosEstado)
def status(dest_path: str):
    destino = _directorio(dest_path)
    estado = cali.leer_estado(destino)
    if estado is None:
        raise HTTPException(status_code=404, detail="No hay ninguna descarga registrada para esa carpeta")
    return estado


@router.post("/stop", response_model=CaliDecretosEstado)
def stop(payload: CaliDecretosStopRequest):
    destino = _directorio(payload.dest_path)
    estado = cali.leer_estado(destino)
    if estado is None:
        raise HTTPException(status_code=404, detail="No hay ninguna descarga registrada para esa carpeta")
    estado["detener_solicitado"] = True
    cali.escribir_estado(destino, estado)
    return estado
```

- [ ] **Step 5: Register the router in `api/main.py`**

Change the routers import line to include `cali_decretos` (keep alphabetical order):

```python
from api.routers import (
    auth,
    bulk_downloads,
    cali_decretos,
    case_links,
    documents,
    health,
    reorganize,
    runs,
    sources,
)
```

And add after `app.include_router(reorganize.router)`:

```python
app.include_router(cali_decretos.router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_api_cali_decretos.py -v`
Expected: PASS (8 tests).

- [ ] **Step 7: Run the API suite for regressions**

Run: `python -m pytest tests/test_api_cali_decretos.py tests/test_api_reorganize.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add api/schemas.py api/routers/cali_decretos.py api/main.py tests/test_api_cali_decretos.py
git commit -m "feat(cali-decretos): admin API to start/stop/poll the download"
```

---

## Task 6: Frontend API client + panel

**Files:**
- Create: `frontend/src/api/caliDecretos.ts`
- Create: `frontend/src/pages/formatter/CaliDecretosPanel.tsx`
- Test: `frontend/src/pages/formatter/CaliDecretosPanel.test.tsx`

**Interfaces:**
- Consumes: `apiFetch`, `buildQuery` from `frontend/src/api/client.ts`; `ApiError` from same; `ErrorBanner` (`{ message: string }`) from `frontend/src/components/ErrorBanner`; `Button` (`variant?: "default" | "secondary" | …`) from `frontend/src/components/ui/button`; `Input` from `frontend/src/components/ui/input`.
- Produces:
  - `caliDecretos.ts`: `CaliDecretosAviso`, `CaliDecretosFallido`, `CaliDecretosEstado` interfaces; `startCaliDecretos(destPath)`, `getCaliDecretosStatus(destPath)`, `stopCaliDecretos(destPath)`.
  - `CaliDecretosPanel.tsx`: named export `CaliDecretosPanel` (no props).

- [ ] **Step 1: Write the API client**

Create `frontend/src/api/caliDecretos.ts`:

```ts
import { apiFetch, buildQuery } from "./client";

export interface CaliDecretosAviso {
  tipo: string;
  numero?: string | null;
  anio?: number | null;
  url?: string | null;
  guardado_como?: string | null;
}

export interface CaliDecretosFallido {
  numero?: string | null;
  anio?: number | null;
  url: string;
  motivo: string;
  intentos: number;
}

export type CaliDecretosEstadoNombre =
  | "en_curso"
  | "detenido"
  | "terminado"
  | "terminado_con_fallos";

export interface CaliDecretosEstado {
  version: number;
  estado: CaliDecretosEstadoNombre;
  iniciado: string;
  actualizado: string;
  terminado: string | null;
  total_registros_sitio: number | null;
  total_paginas: number | null;
  ultima_pagina_completada: number;
  descargados: number;
  ya_existian: number;
  duplicados: number;
  fallidos_count: number;
  detener_solicitado: boolean;
  concurrencia_actual: number;
  avisos: CaliDecretosAviso[];
  fallidos: CaliDecretosFallido[];
}

export function startCaliDecretos(destPath: string): Promise<CaliDecretosEstado> {
  return apiFetch<CaliDecretosEstado>("/cali-decretos/start", {
    method: "POST",
    body: JSON.stringify({ dest_path: destPath }),
  });
}

export function getCaliDecretosStatus(destPath: string): Promise<CaliDecretosEstado> {
  return apiFetch<CaliDecretosEstado>(`/cali-decretos/status${buildQuery({ dest_path: destPath })}`);
}

export function stopCaliDecretos(destPath: string): Promise<CaliDecretosEstado> {
  return apiFetch<CaliDecretosEstado>("/cali-decretos/stop", {
    method: "POST",
    body: JSON.stringify({ dest_path: destPath }),
  });
}
```

- [ ] **Step 2: Write the failing test**

Create `frontend/src/pages/formatter/CaliDecretosPanel.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { CaliDecretosPanel } from "./CaliDecretosPanel";

const BASE_URL = "http://localhost:8000";

function estado(overrides: Record<string, unknown> = {}) {
  return {
    version: 1,
    estado: "en_curso",
    iniciado: "2026-09-02T14:00:00Z",
    actualizado: "2026-09-02T14:05:00Z",
    terminado: null,
    total_registros_sitio: 71969,
    total_paginas: 7195,
    ultima_pagina_completada: 100,
    descargados: 990,
    ya_existian: 0,
    duplicados: 2,
    fallidos_count: 3,
    detener_solicitado: false,
    concurrencia_actual: 8,
    avisos: [],
    fallidos: [],
    ...overrides,
  };
}

describe("CaliDecretosPanel", () => {
  it("starts a download and shows progress", async () => {
    server.use(
      http.get(`${BASE_URL}/cali-decretos/status`, () => new HttpResponse(null, { status: 404 })),
      http.post(`${BASE_URL}/cali-decretos/start`, () => HttpResponse.json(estado())),
    );
    const user = userEvent.setup();
    render(<CaliDecretosPanel />);

    await user.type(screen.getByLabelText("Carpeta de destino"), "D:\\DESCARGA CALI");
    await user.click(screen.getByRole("button", { name: "Iniciar" }));

    expect(await screen.findByText(/Página 100 de 7\.195/)).toBeInTheDocument();
    expect(screen.getByText("990")).toBeInTheDocument(); // descargados
    expect(screen.getByRole("button", { name: "Detener" })).toBeInTheDocument();
  });

  it("shows the summary and a retry button for terminado_con_fallos", async () => {
    server.use(
      http.get(`${BASE_URL}/cali-decretos/status`, () =>
        HttpResponse.json(
          estado({
            estado: "terminado_con_fallos",
            ultima_pagina_completada: 7195,
            descargados: 71900,
            fallidos_count: 69,
            fallidos: [
              { numero: "0044", anio: 1984, url: "ftp://x/y.pdf", motivo: "ftp-no-disponible", intentos: 4 },
            ],
          }),
        ),
      ),
    );
    const user = userEvent.setup();
    render(<CaliDecretosPanel />);
    await user.type(screen.getByLabelText("Carpeta de destino"), "D:\\DESCARGA CALI");
    await user.tab(); // triggers onBlur → status fetch

    expect(await screen.findByText(/Terminado con fallos/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar fallidos" })).toBeInTheDocument();
    expect(screen.getByText(/1 por FTP no disponible/)).toBeInTheDocument();
  });

  it("stops a running download", async () => {
    server.use(
      http.get(`${BASE_URL}/cali-decretos/status`, () => HttpResponse.json(estado())),
      http.post(`${BASE_URL}/cali-decretos/stop`, () =>
        HttpResponse.json(estado({ estado: "detenido", detener_solicitado: true })),
      ),
    );
    const user = userEvent.setup();
    render(<CaliDecretosPanel />);
    await user.type(screen.getByLabelText("Carpeta de destino"), "D:\\DESCARGA CALI");
    await user.tab();

    await user.click(await screen.findByRole("button", { name: "Detener" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Reanudar" })).toBeInTheDocument(),
    );
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/formatter/CaliDecretosPanel.test.tsx`
Expected: FAIL — cannot resolve `./CaliDecretosPanel`.

- [ ] **Step 4: Write the panel**

Create `frontend/src/pages/formatter/CaliDecretosPanel.tsx`:

```tsx
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import {
  getCaliDecretosStatus,
  startCaliDecretos,
  stopCaliDecretos,
  type CaliDecretosEstado,
} from "../../api/caliDecretos";
import { ErrorBanner } from "../../components/ErrorBanner";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";

const EN_CURSO = "en_curso";

const ETIQUETA_ESTADO: Record<CaliDecretosEstado["estado"], string> = {
  en_curso: "En curso",
  detenido: "Detenido",
  terminado: "Terminado",
  terminado_con_fallos: "Terminado con fallos",
};

function etiquetaIniciar(estado: CaliDecretosEstado | null): string {
  if (!estado) return "Iniciar";
  if (estado.estado === "terminado_con_fallos") return "Reintentar fallidos";
  if (estado.estado === "detenido") return "Reanudar";
  if (estado.estado === "terminado") return "Revisar de nuevo";
  return "Iniciar";
}

function num(n: number): string {
  return n.toLocaleString("es");
}

function Metrica({ etiqueta, valor }: { etiqueta: string; valor: number }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{etiqueta}</dt>
      <dd className="font-mono-num">{num(valor)}</dd>
    </div>
  );
}

function ListaCopiable({ lineas }: { lineas: string[] }) {
  return (
    <div className="mt-2 space-y-1">
      <Button
        variant="outline"
        size="xs"
        onClick={() => void navigator.clipboard?.writeText(lineas.join("\n"))}
      >
        Copiar lista
      </Button>
      <pre className="max-h-64 overflow-auto rounded bg-secondary/40 p-2 text-[0.7rem] leading-tight">
        {lineas.join("\n")}
      </pre>
    </div>
  );
}

export function CaliDecretosPanel() {
  const [path, setPath] = useState("");
  const [estado, setEstado] = useState<CaliDecretosEstado | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pathRef = useRef(path);
  pathRef.current = path;

  const refrescar = useCallback(async (p: string) => {
    if (!p) return;
    try {
      setEstado(await getCaliDecretosStatus(p));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setEstado(null);
    }
  }, []);

  useEffect(() => {
    if (estado?.estado !== EN_CURSO) return;
    const id = setInterval(() => void refrescar(pathRef.current), 3000);
    return () => clearInterval(id);
  }, [estado?.estado, refrescar]);

  async function accion(fn: () => Promise<CaliDecretosEstado>, fallback: string) {
    setBusy(true);
    setError(null);
    try {
      setEstado(await fn());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : fallback);
    } finally {
      setBusy(false);
    }
  }

  const enCurso = estado?.estado === EN_CURSO;
  const progreso =
    estado && estado.total_paginas
      ? Math.round((estado.ultima_pagina_completada / estado.total_paginas) * 100)
      : 0;
  const fallidosFtp = estado?.fallidos.filter((f) => f.motivo === "ftp-no-disponible").length ?? 0;
  const fallidosOtros = (estado?.fallidos.length ?? 0) - fallidosFtp;
  const listaRecortada = estado ? estado.fallidos.length < estado.fallidos_count : false;

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Descarga todos los decretos publicados en{" "}
        <code>cali.gov.co/&hellip;/consulta-de-decretos</code> a la carpeta indicada, organizados como{" "}
        <code>DECRETOS/ALCACALI/&#123;año&#125;/D_ALCACALI_&#123;número&#125;_&#123;año&#125;.pdf</code>.
        Son ~72.000 archivos: puede ocupar decenas o cientos de GB y tardar varias horas. Podés cerrar
        esta pestaña mientras corre; la descarga sigue en el servidor.
      </p>

      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-1 flex-col gap-1 text-sm">
          <span>Carpeta de destino</span>
          <Input
            value={path}
            onChange={(ev) => setPath(ev.target.value)}
            onBlur={() => void refrescar(path)}
            placeholder="D:\DESCARGA CALI"
          />
        </label>
        <Button
          onClick={() => void accion(() => startCaliDecretos(path), "No se pudo iniciar la descarga.")}
          disabled={!path || busy || enCurso}
        >
          {etiquetaIniciar(estado)}
        </Button>
        {enCurso && (
          <Button
            variant="secondary"
            onClick={() => void accion(() => stopCaliDecretos(path), "No se pudo detener la descarga.")}
            disabled={busy}
          >
            Detener
          </Button>
        )}
      </div>

      {error && <ErrorBanner message={error} />}

      {estado && (
        <div className="space-y-3 rounded-lg border border-border bg-card p-4">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">{ETIQUETA_ESTADO[estado.estado]}</span>
            <span className="text-muted-foreground">
              Página {num(estado.ultima_pagina_completada)} de {num(estado.total_paginas ?? 0)}
            </span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded bg-secondary">
            <div className="h-full bg-primary transition-all" style={{ width: `${progreso}%` }} />
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
            <Metrica etiqueta="Descargados" valor={estado.descargados} />
            <Metrica etiqueta="Ya estaban" valor={estado.ya_existian} />
            <Metrica etiqueta="Duplicados" valor={estado.duplicados} />
            <Metrica etiqueta="Fallidos" valor={estado.fallidos_count} />
          </dl>
          {estado.fallidos_count > 0 && (
            <p className="text-xs text-muted-foreground">
              {num(fallidosFtp)} por FTP no disponible &middot; {num(fallidosOtros)} por otros errores
              {listaRecortada && " (lista recortada a 1.000)"}
            </p>
          )}
          {estado.fallidos.length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer">Fallidos ({num(estado.fallidos.length)})</summary>
              <ListaCopiable
                lineas={estado.fallidos.map(
                  (f) => `${f.numero ?? "?"}\t${f.anio ?? "?"}\t${f.motivo}\t${f.url}`,
                )}
              />
            </details>
          )}
          {estado.avisos.length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer">Avisos ({num(estado.avisos.length)})</summary>
              <ListaCopiable
                lineas={estado.avisos.map(
                  (a) =>
                    `${a.tipo}\t${a.numero ?? ""}\t${a.anio ?? ""}\t${a.guardado_como ?? a.url ?? ""}`,
                )}
              />
            </details>
          )}
        </div>
      )}
    </div>
  );
}
```

If `size="xs"` or `variant="outline"` is not accepted by `Button`, check `frontend/src/components/ui/button.tsx` (it lists `xs` and `outline` in its `cva` config as of this writing) and adjust.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/formatter/CaliDecretosPanel.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/caliDecretos.ts frontend/src/pages/formatter/CaliDecretosPanel.tsx frontend/src/pages/formatter/CaliDecretosPanel.test.tsx
git commit -m "feat(cali-decretos): frontend panel and API client"
```

---

## Task 7: Wire the third tab into FormatterPage

**Files:**
- Modify: `frontend/src/pages/FormatterPage.tsx`
- Modify: `frontend/src/pages/FormatterPage.test.tsx`

**Interfaces:**
- Consumes: `CaliDecretosPanel` from `./formatter/CaliDecretosPanel`.
- Produces: nothing new (self-contained page change).

- [ ] **Step 1: Update the failing test**

Replace the body of the single `it(...)` in `frontend/src/pages/FormatterPage.test.tsx` so it also covers the new tab:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FormatterPage } from "./FormatterPage";

describe("FormatterPage", () => {
  it("switches between the three Laboratorio tabs", async () => {
    const user = userEvent.setup();
    render(<FormatterPage />);

    expect(screen.getByRole("heading", { name: "Laboratorio" })).toBeInTheDocument();
    expect(screen.getByText(/necesita Chrome o Edge/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reorganización" }));
    expect(screen.getByLabelText("Ruta de la carpeta")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Decretos Cali" }));
    expect(screen.getByLabelText("Carpeta de destino")).toBeInTheDocument();
    expect(screen.queryByLabelText("Ruta de la carpeta")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Renombrado" }));
    expect(screen.getByText(/necesita Chrome o Edge/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/FormatterPage.test.tsx`
Expected: FAIL — no "Decretos Cali" button / "Carpeta de destino" not found.

- [ ] **Step 3: Update `FormatterPage.tsx`**

```tsx
import { useState } from "react";
import { Wand2 } from "lucide-react";
import { RenamePanel } from "./formatter/RenamePanel";
import { ReorganizePanel } from "./formatter/ReorganizePanel";
import { CaliDecretosPanel } from "./formatter/CaliDecretosPanel";

type Tab = "rename" | "reorganize" | "cali-decretos";

const TABS: { id: Tab; label: string }[] = [
  { id: "rename", label: "Renombrado" },
  { id: "reorganize", label: "Reorganización" },
  { id: "cali-decretos", label: "Decretos Cali" },
];

function PanelActivo({ tab }: { tab: Tab }) {
  if (tab === "rename") return <RenamePanel />;
  if (tab === "reorganize") return <ReorganizePanel />;
  return <CaliDecretosPanel />;
}

export function FormatterPage() {
  const [tab, setTab] = useState<Tab>("rename");

  return (
    <div className="space-y-6">
      <div>
        <p className="flex items-center gap-1.5 text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">
          <Wand2 className="size-3.5" aria-hidden="true" />
          Herramientas de lote
        </p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">Laboratorio</h1>
      </div>

      <div className="flex gap-1 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-2 text-sm font-medium transition-colors ${
              tab === t.id
                ? "border-b-2 border-primary text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <PanelActivo tab={tab} />
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/FormatterPage.test.tsx`
Expected: PASS.

- [ ] **Step 5: Run the full frontend suite + lint/typecheck**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: PASS, no type errors.

- [ ] **Step 6: Run the full backend suite**

Run: `python -m pytest tests/ -q`
Expected: PASS (no regressions from the `worker/tasks.py`, `api/schemas.py`, `api/main.py` edits).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/FormatterPage.tsx frontend/src/pages/FormatterPage.test.tsx
git commit -m "feat(cali-decretos): add the Decretos Cali tab to Laboratorio"
```

---

## Self-Review

**1. Spec coverage:**

| Spec section | Task |
|---|---|
| Hallazgos: `paginador.php?pag=N`, no cookies, totals from page 1 | Task 1 (`parse_pagina`), Task 4 (`_pedir_pagina`, walk) |
| Hallazgos: PDF URL from `onMouseUp`, `http→https` redirect, `/../` collapse | Task 1 (`_normalizar_url`, `_MM_OPEN`), Task 3 (`allow_redirects=True`) |
| Arquitectura: tercer tab, tabla de piezas | Tasks 5–7 |
| Por qué Celery, sin DB | Task 4 (task has no `SessionLocal`) |
| Flujo (start/status/stop, 409, resume, close tab) | Task 5 (router), Task 6 (polling) |
| Recorrido de páginas + estabilidad | Task 4 (`for pag in range(inicio, total+1)`, page-1 refresh) |
| Nombre de archivo: entidad fija, número normalize, año fallback, ruta | Task 1 (`normalizar_numero`, `resolver_anio`, `ruta_destino`) |
| Números repetidos (`_2` suffix + aviso, vs silent resume-skip) | Task 4 (`_preparar_trabajos`, `vistos` set) + Task 4 test `...duplicate...` |
| Paralelismo 8, page-by-page feed | Task 4 (`_ejecutar_trabajos`) |
| Auto-bajada de velocidad (5 fallos → 3) | Task 4 (`_CALI_FALLOS_PARA_BAJAR_CONCURRENCIA`) |
| Cada PDF: skip-if-exists, temp, validate, move, 3 retries 2/8/30 | Task 3 (`_descargar_un_pdf`), Task 4 (`_preparar_trabajos` skip) |
| Pasada final de fallidos | Task 4 (`_pasada_final_fallidos`) |
| Enlaces `ftp://` (`ftplib`, `ftp-no-disponible`, counted apart) | Task 3 (`_descargar_ftp`), Task 6 (FTP breakdown text) |
| Espacio en disco (aviso en el panel) | Task 6 (intro `<p>`) |
| `_descarga_estado.json` shape + atomic write + caps | Task 2 |
| Tabla de reanudación (5 rows) | Task 4 (resume from `ultima_pagina_completada + 1`), Task 5 (`tarea_viva` → 409) |
| "Terminado" en el panel (resumen + reintentar) | Task 6 (`etiquetaIniciar`, summary block) |
| `core/cali_decretos.py` signatures | Tasks 1–2 |
| `worker/tasks.py` task + helpers | Tasks 3–4 |
| `api/routers/cali_decretos.py` 3 endpoints, `require_admin`, 404/409 | Task 5 |
| `api/schemas.py` 5 models | Task 5 |
| Frontend client + panel + tab | Tasks 6–7 |
| Manejo de errores (404, 403, page fail, pdf fail, disk fail, never stuck en_curso) | Task 4 (`try/except` wrapper), Task 5 (`_directorio`) |
| Pruebas (4 archivos) | Tasks 1–7 test steps |

No gaps.

**2. Placeholder scan:** No "TBD"/"TODO"/"handle edge cases"/"similar to Task N". Every code step has real code. Two "if X is not accepted, check the file" notes (Button variants, ErrorBanner props) point at verified-present APIs and are safety nets, not placeholders.

**3. Type consistency:**
- `estado` dict keys are identical across `estado_inicial` (Task 2), the task body (Task 4), the Pydantic model (Task 5), and the TS interface (Task 6): `version, estado, iniciado, actualizado, terminado, total_registros_sitio, total_paginas, ultima_pagina_completada, descargados, ya_existian, duplicados, fallidos_count, detener_solicitado, concurrencia_actual, avisos, fallidos`.
- `_descargar_un_pdf(url, destino_final, tmp_dir, dormir=time.sleep) -> str | None` — same signature in Task 3 definition, Task 3 tests, and Task 4 callers (`_ejecutar_trabajos`, `_pasada_final_fallidos`).
- `_pedir_pagina(sesion, pag, dormir=time.sleep) -> PaginaParseada | None` — Task 4 definition and callers agree.
- Endpoint paths: `/cali-decretos/start|status|stop` identical in router (Task 5), API tests (Task 5), and TS client (Task 6).
- `FilaDecreto` fields (`numero_raw`, `fecha`, `anio_raw`, `pdf_url`) used consistently in Task 1 and Task 4 (`_preparar_trabajos`).
- Button label strings match between `CaliDecretosPanel` (`etiquetaIniciar`) and both `CaliDecretosPanel.test.tsx` and `FormatterPage.test.tsx` ("Iniciar", "Reintentar fallidos", "Reanudar", "Detener", "Decretos Cali").

No inconsistencies found.
