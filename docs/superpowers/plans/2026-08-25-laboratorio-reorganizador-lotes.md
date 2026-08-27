# Reorganizador de lotes (Laboratorio) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Reorganización" tab inside Laboratorio that audits a heavy intake batch (organized `Tipo → [Entidad] → Año → archivo`) against that convention and fixes only the files that don't fit — never the files that are already correctly placed.

**Architecture:** A synchronous FastAPI endpoint pair (`/reorganize/analyze`, `/reorganize/apply`), admin-gated, that walks a disk path given as plain text (no browser file picker) and returns/executes a small set of file moves. The frontend adds a second tab to the existing `FormatterPage`, reusing its table/panel conventions.

**Tech Stack:** FastAPI + Pydantic (backend), React + TypeScript + Vitest/Testing Library/MSW (frontend), pytest (backend tests).

**Spec:** `docs/superpowers/specs/2026-08-25-laboratorio-reorganizador-lotes-design.md`

## Global Constraints

- No browser folder picker (`showDirectoryPicker`) — the admin types an absolute disk path; the **backend** walks it directly.
- No Celery / background job — analysis is synchronous (a full walk of the reference batch took ~15s for 53k files).
- `apply` never overwrites an existing destination file, and never touches files that are already correctly placed.
- Fusing/renaming top-level Tipo folders (e.g. `Ccircular` vs `CIRCULAR`) is out of scope — never attempted.
- Anything nested deeper than `Tipo/[Entidad]/Año/archivo`, or that otherwise doesn't match one of the two defined exception kinds, is reported as `extra_depth` (informational) and never moved.
- All `*_path` fields in requests/responses are **relative to `root_path`**, forward-slash-separated, never an absolute disk path.
- Every `/reorganize/*` route requires `is_admin` (via `require_admin`, same dependency `api/routers/sources.py` already uses).

---

## Task 1: `core/reorganize.py` — `analyze_batch`

**Files:**
- Modify: `api/schemas.py` (append new models at the end of the file)
- Create: `core/reorganize.py`
- Test: `tests/test_core_reorganize.py`

**Interfaces:**
- Produces: `core.reorganize.analyze_batch(root: Path) -> api.schemas.BatchAnalysis`, and the schema classes `TipoSummary`, `ReorganizeException`, `ExtraDepthEntry`, `BatchAnalysis`, `ResolvedMove`, `MoveResult`, `ApplyResult` (all in `api/schemas.py`) that Task 2 and Task 3 both import.

- [ ] **Step 1: Append the new Pydantic models to `api/schemas.py`**

Add at the end of `api/schemas.py` (imports at the top of that file already include `Literal`, `Optional`, `BaseModel` — no new imports needed):

```python
class ReorganizeAnalyzeRequest(BaseModel):
    root_path: str


class TipoSummary(BaseModel):
    tipo: str
    total_files: int
    exception_count: int


class ReorganizeException(BaseModel):
    tipo: str
    kind: Literal["missing_entity_folder", "missing_year_folder"]
    current_path: str
    detected_entity: Optional[str] = None
    detected_year: Optional[int] = None
    mtime_year_hint: Optional[int] = None
    proposed_path: Optional[str] = None


class ExtraDepthEntry(BaseModel):
    tipo: str
    current_path: str


class BatchAnalysis(BaseModel):
    root_path: str
    total_files: int
    tipos: list[TipoSummary]
    exceptions: list[ReorganizeException]
    extra_depth: list[ExtraDepthEntry]


class ResolvedMove(BaseModel):
    current_path: str
    target_path: str


class ReorganizeApplyRequest(BaseModel):
    root_path: str
    moves: list[ResolvedMove]


class MoveResult(BaseModel):
    current_path: str
    target_path: str
    moved: bool
    skip_reason: Optional[str] = None


class ApplyResult(BaseModel):
    results: list[MoveResult]
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_core_reorganize.py`:

```python
import os
from datetime import datetime, timezone
from pathlib import Path

from core.reorganize import analyze_batch


def _touch(path: Path, content: str = "contenido") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _by_tipo(result, tipo):
    return next(t for t in result.tipos if t.tipo == tipo)


def test_correctly_placed_files_produce_no_exceptions(tmp_path):
    _touch(tmp_path / "DECRETOS" / "MSPS" / "2022" / "D_MSPS_0017AJ_2022.pdf")
    _touch(tmp_path / "DECRETOS" / "PGN" / "2019" / "D_PGN_0001_2019.pdf")
    _touch(tmp_path / "Leyes" / "2022" / "L_0001_2022.pdf")

    result = analyze_batch(tmp_path)

    assert result.total_files == 3
    assert result.exceptions == []
    assert result.extra_depth == []
    assert _by_tipo(result, "DECRETOS").total_files == 2
    assert _by_tipo(result, "DECRETOS").exception_count == 0
    assert _by_tipo(result, "Leyes").total_files == 1


def test_missing_entity_folder_resolved_from_filename(tmp_path):
    _touch(tmp_path / "DECRETOS" / "PGN" / "2019" / "D_PGN_0001_2019.pdf")
    _touch(tmp_path / "DECRETOS" / "2022" / "D_MSPS_0017AJ_2022.pdf")

    result = analyze_batch(tmp_path)

    assert len(result.exceptions) == 1
    exc = result.exceptions[0]
    assert exc.tipo == "DECRETOS"
    assert exc.kind == "missing_entity_folder"
    assert exc.current_path == "DECRETOS/2022/D_MSPS_0017AJ_2022.pdf"
    assert exc.detected_entity == "MSPS"
    assert exc.detected_year == 2022
    assert exc.proposed_path == "DECRETOS/MSPS/2022/D_MSPS_0017AJ_2022.pdf"
    assert _by_tipo(result, "DECRETOS").exception_count == 1
    assert result.total_files == 2


def test_missing_entity_folder_unresolved_when_entity_cant_be_parsed(tmp_path):
    _touch(tmp_path / "DECRETOS" / "PGN" / "2019" / "D_PGN_0001_2019.pdf")
    _touch(tmp_path / "DECRETOS" / "2022" / "decreto-suelto.pdf")

    result = analyze_batch(tmp_path)

    exc = next(e for e in result.exceptions if e.current_path.endswith("decreto-suelto.pdf"))
    assert exc.kind == "missing_entity_folder"
    assert exc.detected_entity is None
    assert exc.detected_year == 2022
    assert exc.proposed_path is None


def test_missing_year_folder_resolved_from_filename(tmp_path):
    _touch(tmp_path / "RESOLUCIONES" / "PGN" / "R_PGN_0158_2015.pdf")

    result = analyze_batch(tmp_path)

    assert len(result.exceptions) == 1
    exc = result.exceptions[0]
    assert exc.tipo == "RESOLUCIONES"
    assert exc.kind == "missing_year_folder"
    assert exc.current_path == "RESOLUCIONES/PGN/R_PGN_0158_2015.pdf"
    assert exc.detected_entity == "PGN"
    assert exc.detected_year == 2015
    assert exc.mtime_year_hint is None
    assert exc.proposed_path == "RESOLUCIONES/PGN/2015/R_PGN_0158_2015.pdf"


def test_missing_year_folder_unresolved_uses_mtime_as_hint(tmp_path):
    path = tmp_path / "RESOLUCIONES" / "SGCANDINA" / "RSG2058.docx"
    _touch(path)
    ts = datetime(2022, 6, 15, tzinfo=timezone.utc).timestamp()
    os.utime(path, (ts, ts))

    result = analyze_batch(tmp_path)

    assert len(result.exceptions) == 1
    exc = result.exceptions[0]
    assert exc.kind == "missing_year_folder"
    assert exc.detected_entity == "SGCANDINA"
    assert exc.detected_year is None
    assert exc.mtime_year_hint == 2022
    assert exc.proposed_path is None


def test_sin_entidad_tipo_bare_file_is_missing_year_folder(tmp_path):
    _touch(tmp_path / "Leyes" / "2022" / "L_0001_2022.pdf")
    _touch(tmp_path / "Leyes" / "LEY_0042_2019.pdf")

    result = analyze_batch(tmp_path)

    assert len(result.exceptions) == 1
    exc = result.exceptions[0]
    assert exc.tipo == "Leyes"
    assert exc.kind == "missing_year_folder"
    assert exc.current_path == "Leyes/LEY_0042_2019.pdf"
    assert exc.detected_entity is None
    assert exc.detected_year == 2019
    assert exc.proposed_path == "Leyes/2019/LEY_0042_2019.pdf"


def test_extra_depth_reports_deeper_nesting_without_treating_it_as_an_exception(tmp_path):
    _touch(tmp_path / "Gacetas" / "GC" / "1992" / "regular.pdf")
    _touch(tmp_path / "Gacetas" / "GC" / "1992" / "AC" / "AC_0001_1992.pdf")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert len(result.extra_depth) == 1
    entry = result.extra_depth[0]
    assert entry.tipo == "Gacetas"
    assert entry.current_path == "Gacetas/GC/1992/AC/AC_0001_1992.pdf"
    assert result.total_files == 2
    assert _by_tipo(result, "Gacetas").total_files == 2


def test_bare_file_directly_under_con_entidad_tipo_is_extra_depth(tmp_path):
    _touch(tmp_path / "CIRCULAR" / "PGN" / "2019" / "C_PGN_0001_2019.pdf")
    _touch(tmp_path / "CIRCULAR" / "stray.pdf")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert len(result.extra_depth) == 1
    assert result.extra_depth[0].current_path == "CIRCULAR/stray.pdf"
    assert result.total_files == 2
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/test_core_reorganize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.reorganize'` (or `ImportError`).

- [ ] **Step 4: Write `core/reorganize.py`**

```python
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import re

from api.schemas import (
    ApplyResult,
    BatchAnalysis,
    ExtraDepthEntry,
    MoveResult,
    ReorganizeException,
    ResolvedMove,
    TipoSummary,
)

YEAR_RE = re.compile(r"^(?:1[89]\d{2}|20\d{2})$")


def _is_year_name(name: str) -> bool:
    return bool(YEAR_RE.match(name))


def _last_underscore_token(stem: str) -> Optional[str]:
    parts = stem.split("_")
    return parts[-1] if len(parts) >= 2 else None


def _detect_year_from_filename(filename: str) -> Optional[int]:
    token = _last_underscore_token(Path(filename).stem)
    return int(token) if token is not None and YEAR_RE.match(token) else None


def _detect_entity_from_filename(filename: str) -> Optional[str]:
    parts = Path(filename).stem.split("_")
    return parts[1] if len(parts) >= 3 else None


def _relpath(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _collect_extra_depth(root: Path, tipo: str, start: Path, out: list[ExtraDepthEntry]) -> int:
    count = 0
    for f in sorted(start.rglob("*")):
        if f.is_file():
            out.append(ExtraDepthEntry(tipo=tipo, current_path=_relpath(root, f)))
            count += 1
    return count


def _missing_entity_exception(root: Path, tipo: str, year: int, file: Path) -> ReorganizeException:
    entity = _detect_entity_from_filename(file.name)
    proposed = f"{tipo}/{entity}/{year}/{file.name}" if entity else None
    return ReorganizeException(
        tipo=tipo,
        kind="missing_entity_folder",
        current_path=_relpath(root, file),
        detected_entity=entity,
        detected_year=year,
        mtime_year_hint=None,
        proposed_path=proposed,
    )


def _missing_year_exception(root: Path, tipo: str, entity: Optional[str], file: Path) -> ReorganizeException:
    year = _detect_year_from_filename(file.name)
    mtime_hint = None
    if year is None:
        mtime_hint = datetime.fromtimestamp(file.stat().st_mtime, tz=timezone.utc).year
    proposed = None
    if year is not None:
        proposed = f"{tipo}/{entity}/{year}/{file.name}" if entity else f"{tipo}/{year}/{file.name}"
    return ReorganizeException(
        tipo=tipo,
        kind="missing_year_folder",
        current_path=_relpath(root, file),
        detected_entity=entity,
        detected_year=year,
        mtime_year_hint=mtime_hint,
        proposed_path=proposed,
    )


def analyze_batch(root: Path) -> BatchAnalysis:
    tipos: list[TipoSummary] = []
    exceptions: list[ReorganizeException] = []
    extra_depth: list[ExtraDepthEntry] = []
    total_files = 0

    for tipo_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        tipo = tipo_dir.name
        dir_children = sorted(c for c in tipo_dir.iterdir() if c.is_dir())
        file_children = sorted(c for c in tipo_dir.iterdir() if c.is_file())
        year_like = [c for c in dir_children if _is_year_name(c.name)]
        entity_like = [c for c in dir_children if not _is_year_name(c.name)]
        con_entidad = len(entity_like) >= len(year_like)

        tipo_total = 0
        tipo_exceptions = 0

        if con_entidad:
            # A bare file directly under a Tipo that otherwise uses entities has
            # no recovery rule the spec defines (it only covers Tipo/Año/archivo
            # and Tipo/Entidad/archivo) — reported as extra_depth so it's never
            # silently dropped from the count.
            for f in file_children:
                tipo_total += 1
                extra_depth.append(ExtraDepthEntry(tipo=tipo, current_path=_relpath(root, f)))

            for child in dir_children:
                if _is_year_name(child.name):
                    year = int(child.name)
                    for f in sorted(child.iterdir()):
                        if f.is_file():
                            tipo_total += 1
                            tipo_exceptions += 1
                            exceptions.append(_missing_entity_exception(root, tipo, year, f))
                        else:
                            tipo_total += _collect_extra_depth(root, tipo, f, extra_depth)
                else:
                    entity = child.name
                    for ec in sorted(child.iterdir()):
                        if ec.is_file():
                            tipo_total += 1
                            tipo_exceptions += 1
                            exceptions.append(_missing_year_exception(root, tipo, entity, ec))
                        elif _is_year_name(ec.name):
                            for f in sorted(ec.iterdir()):
                                if f.is_file():
                                    tipo_total += 1
                                else:
                                    tipo_total += _collect_extra_depth(root, tipo, f, extra_depth)
                        else:
                            tipo_total += _collect_extra_depth(root, tipo, ec, extra_depth)
        else:
            for child in dir_children:
                if _is_year_name(child.name):
                    for f in sorted(child.iterdir()):
                        if f.is_file():
                            tipo_total += 1
                        else:
                            tipo_total += _collect_extra_depth(root, tipo, f, extra_depth)
                else:
                    tipo_total += _collect_extra_depth(root, tipo, child, extra_depth)
            for f in file_children:
                tipo_total += 1
                tipo_exceptions += 1
                exceptions.append(_missing_year_exception(root, tipo, None, f))

        tipos.append(TipoSummary(tipo=tipo, total_files=tipo_total, exception_count=tipo_exceptions))
        total_files += tipo_total

    return BatchAnalysis(
        root_path=str(root),
        total_files=total_files,
        tipos=tipos,
        exceptions=exceptions,
        extra_depth=extra_depth,
    )
```

`apply_moves` is added in Task 2 (it lives in this same file, but is a self-contained addition with its own test cycle).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_core_reorganize.py -v`
Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add api/schemas.py core/reorganize.py tests/test_core_reorganize.py
git commit -m "Add analyze_batch: audit a Tipo/Entidad/Año batch for misplaced files"
```

---

## Task 2: `core/reorganize.py` — `apply_moves`

**Files:**
- Modify: `core/reorganize.py` (append `apply_moves` and its `shutil`/imports)
- Test: `tests/test_core_reorganize.py` (append)

**Interfaces:**
- Consumes: `api.schemas.ResolvedMove`, `MoveResult`, `ApplyResult` (from Task 1).
- Produces: `core.reorganize.apply_moves(root: Path, moves: list[ResolvedMove]) -> ApplyResult`, used by Task 3's router.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_core_reorganize.py`:

```python
from core.reorganize import apply_moves
from api.schemas import ResolvedMove


def test_apply_moves_moves_file_and_creates_missing_folders(tmp_path):
    source = tmp_path / "DECRETOS" / "2022" / "D_MSPS_0017AJ_2022.pdf"
    _touch(source, content="contenido-original")

    result = apply_moves(
        tmp_path,
        [ResolvedMove(current_path="DECRETOS/2022/D_MSPS_0017AJ_2022.pdf", target_path="DECRETOS/MSPS/2022/D_MSPS_0017AJ_2022.pdf")],
    )

    assert result.results[0].moved is True
    assert result.results[0].skip_reason is None
    assert not source.exists()
    target = tmp_path / "DECRETOS" / "MSPS" / "2022" / "D_MSPS_0017AJ_2022.pdf"
    assert target.read_text(encoding="utf-8") == "contenido-original"


def test_apply_moves_skips_when_destination_already_exists(tmp_path):
    source = tmp_path / "DECRETOS" / "2022" / "D_MSPS_0017AJ_2022.pdf"
    _touch(source, content="nuevo")
    target = tmp_path / "DECRETOS" / "MSPS" / "2022" / "D_MSPS_0017AJ_2022.pdf"
    _touch(target, content="ya-existia")

    result = apply_moves(
        tmp_path,
        [ResolvedMove(current_path="DECRETOS/2022/D_MSPS_0017AJ_2022.pdf", target_path="DECRETOS/MSPS/2022/D_MSPS_0017AJ_2022.pdf")],
    )

    assert result.results[0].moved is False
    assert result.results[0].skip_reason is not None
    assert source.exists()
    assert target.read_text(encoding="utf-8") == "ya-existia"


def test_apply_moves_skips_when_source_is_missing(tmp_path):
    result = apply_moves(
        tmp_path,
        [ResolvedMove(current_path="DECRETOS/2022/no-existe.pdf", target_path="DECRETOS/MSPS/2022/no-existe.pdf")],
    )

    assert result.results[0].moved is False
    assert result.results[0].skip_reason is not None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_core_reorganize.py -k apply_moves -v`
Expected: FAIL with `ImportError: cannot import name 'apply_moves'`.

- [ ] **Step 3: Add `apply_moves` to `core/reorganize.py`**

Add `import shutil` to the top of `core/reorganize.py` alongside the existing imports, and append at the end of the file:

```python
def apply_moves(root: Path, moves: list[ResolvedMove]) -> ApplyResult:
    results: list[MoveResult] = []
    for move in moves:
        source = root / move.current_path
        target = root / move.target_path
        if not source.is_file():
            results.append(
                MoveResult(
                    current_path=move.current_path,
                    target_path=move.target_path,
                    moved=False,
                    skip_reason="El archivo de origen ya no existe",
                )
            )
            continue
        if target.exists():
            results.append(
                MoveResult(
                    current_path=move.current_path,
                    target_path=move.target_path,
                    moved=False,
                    skip_reason="El destino ya existe",
                )
            )
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            results.append(
                MoveResult(current_path=move.current_path, target_path=move.target_path, moved=True, skip_reason=None)
            )
        except OSError as exc:
            results.append(
                MoveResult(
                    current_path=move.current_path, target_path=move.target_path, moved=False, skip_reason=str(exc)
                )
            )
    return ApplyResult(results=results)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_core_reorganize.py -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add core/reorganize.py tests/test_core_reorganize.py
git commit -m "Add apply_moves: relocate resolved exceptions without overwriting"
```

---

## Task 3: `api/routers/reorganize.py` — endpoints

**Files:**
- Create: `api/routers/reorganize.py`
- Modify: `api/main.py:4` (add `reorganize` to the router import) and `api/main.py:24` (register the router)
- Test: `tests/test_api_reorganize.py`

**Interfaces:**
- Consumes: `core.reorganize.analyze_batch`, `apply_moves` (Tasks 1-2); `api.deps.require_admin`; `api.schemas.{ReorganizeAnalyzeRequest, ReorganizeApplyRequest, BatchAnalysis, ApplyResult}`.
- Produces: `POST /reorganize/analyze`, `POST /reorganize/apply` — the two HTTP endpoints Task 8 (frontend `api/reorganize.ts`) calls.

This task requires the local Postgres test database used by every other `tests/test_api_*.py` file (via the `db_session`/`api_client` fixtures in `tests/conftest.py`) — same setup already needed to run e.g. `pytest tests/test_api_sources.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_reorganize.py`:

```python
from pathlib import Path


def _touch(path: Path, content: str = "contenido") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_analyze_requires_authentication(api_client, tmp_path):
    response = api_client.post("/reorganize/analyze", json={"root_path": str(tmp_path)})
    assert response.status_code == 401


def test_analyze_rejects_a_non_admin_user(api_client, auth_header, tmp_path):
    response = api_client.post("/reorganize/analyze", json={"root_path": str(tmp_path)}, headers=auth_header)
    assert response.status_code == 403


def test_apply_rejects_a_non_admin_user(api_client, auth_header, tmp_path):
    response = api_client.post(
        "/reorganize/apply", json={"root_path": str(tmp_path), "moves": []}, headers=auth_header
    )
    assert response.status_code == 403


def test_analyze_returns_404_for_a_path_that_does_not_exist(api_client, admin_auth_header, tmp_path):
    response = api_client.post(
        "/reorganize/analyze", json={"root_path": str(tmp_path / "no-existe")}, headers=admin_auth_header
    )
    assert response.status_code == 404


def test_analyze_happy_path(api_client, admin_auth_header, tmp_path):
    _touch(tmp_path / "DECRETOS" / "2022" / "D_MSPS_0017AJ_2022.pdf")

    response = api_client.post("/reorganize/analyze", json={"root_path": str(tmp_path)}, headers=admin_auth_header)

    assert response.status_code == 200
    body = response.json()
    assert body["total_files"] == 1
    assert len(body["exceptions"]) == 1
    assert body["exceptions"][0]["kind"] == "missing_entity_folder"
    assert body["exceptions"][0]["proposed_path"] == "DECRETOS/MSPS/2022/D_MSPS_0017AJ_2022.pdf"


def test_apply_happy_path_moves_the_file_on_disk(api_client, admin_auth_header, tmp_path):
    source = tmp_path / "DECRETOS" / "2022" / "D_MSPS_0017AJ_2022.pdf"
    _touch(source)

    response = api_client.post(
        "/reorganize/apply",
        json={
            "root_path": str(tmp_path),
            "moves": [
                {
                    "current_path": "DECRETOS/2022/D_MSPS_0017AJ_2022.pdf",
                    "target_path": "DECRETOS/MSPS/2022/D_MSPS_0017AJ_2022.pdf",
                }
            ],
        },
        headers=admin_auth_header,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["moved"] is True
    assert not source.exists()
    assert (tmp_path / "DECRETOS" / "MSPS" / "2022" / "D_MSPS_0017AJ_2022.pdf").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_api_reorganize.py -v`
Expected: FAIL — every test gets a `404` from FastAPI itself (route doesn't exist yet) instead of the expected status code.

- [ ] **Step 3: Write `api/routers/reorganize.py`**

```python
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from api.deps import require_admin
from api.schemas import ApplyResult, BatchAnalysis, ReorganizeAnalyzeRequest, ReorganizeApplyRequest
from core.reorganize import analyze_batch, apply_moves

router = APIRouter(dependencies=[Depends(require_admin)])


def _require_directory(root_path: str) -> Path:
    root = Path(root_path)
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="La ruta no existe o no es una carpeta")
    return root


@router.post("/reorganize/analyze", response_model=BatchAnalysis)
def post_reorganize_analyze(payload: ReorganizeAnalyzeRequest):
    return analyze_batch(_require_directory(payload.root_path))


@router.post("/reorganize/apply", response_model=ApplyResult)
def post_reorganize_apply(payload: ReorganizeApplyRequest):
    return apply_moves(_require_directory(payload.root_path), payload.moves)
```

- [ ] **Step 4: Register the router in `api/main.py`**

Change line 4 from:
```python
from api.routers import auth, bulk_downloads, case_links, documents, health, runs, sources
```
to:
```python
from api.routers import auth, bulk_downloads, case_links, documents, health, reorganize, runs, sources
```

Add after line 24 (`app.include_router(case_links.router)`):
```python
app.include_router(reorganize.router)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_api_reorganize.py -v`
Expected: 6 passed.

Also run the full core module's tests once more to confirm nothing broke:
Run: `pytest tests/test_core_reorganize.py -v`
Expected: 11 passed.

- [ ] **Step 6: Commit**

```bash
git add api/routers/reorganize.py api/main.py tests/test_api_reorganize.py
git commit -m "Wire the reorganizer behind admin-gated /reorganize endpoints"
```

---

## Task 4: `frontend/src/api/reorganize.ts` — API client

**Files:**
- Modify: `frontend/src/api/types.ts` (append new types)
- Create: `frontend/src/api/reorganize.ts`
- Test: `frontend/src/api/reorganize.test.ts`

**Interfaces:**
- Produces: `analyzeReorganization(rootPath: string): Promise<BatchAnalysis>`, `applyReorganization(rootPath: string, moves: ResolvedMove[]): Promise<ApplyResult>`, and the TS types `TipoSummary`, `ReorganizeException`, `ExtraDepthEntry`, `BatchAnalysis`, `ResolvedMove`, `MoveResult`, `ApplyResult` — consumed by Task 5 and Task 7.

- [ ] **Step 1: Append the new types to `frontend/src/api/types.ts`**

```ts
export interface TipoSummary {
  tipo: string;
  total_files: number;
  exception_count: number;
}

export type ReorganizeExceptionKind = "missing_entity_folder" | "missing_year_folder";

export interface ReorganizeException {
  tipo: string;
  kind: ReorganizeExceptionKind;
  current_path: string;
  detected_entity: string | null;
  detected_year: number | null;
  mtime_year_hint: number | null;
  proposed_path: string | null;
}

export interface ExtraDepthEntry {
  tipo: string;
  current_path: string;
}

export interface BatchAnalysis {
  root_path: string;
  total_files: number;
  tipos: TipoSummary[];
  exceptions: ReorganizeException[];
  extra_depth: ExtraDepthEntry[];
}

export interface ResolvedMove {
  current_path: string;
  target_path: string;
}

export interface MoveResult {
  current_path: string;
  target_path: string;
  moved: boolean;
  skip_reason: string | null;
}

export interface ApplyResult {
  results: MoveResult[];
}
```

- [ ] **Step 2: Write the failing test**

Create `frontend/src/api/reorganize.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/server";
import { analyzeReorganization, applyReorganization } from "./reorganize";

const BASE_URL = "http://localhost:8000";

describe("reorganize API", () => {
  it("analyzeReorganization posts the root path and returns the analysis", async () => {
    let receivedBody: unknown = null;
    server.use(
      http.post(`${BASE_URL}/reorganize/analyze`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json({
          root_path: "D:/LOTE 2",
          total_files: 1,
          tipos: [],
          exceptions: [],
          extra_depth: [],
        });
      })
    );

    const result = await analyzeReorganization("D:/LOTE 2");

    expect(receivedBody).toEqual({ root_path: "D:/LOTE 2" });
    expect(result.total_files).toBe(1);
  });

  it("applyReorganization posts the root path and the resolved moves", async () => {
    let receivedBody: unknown = null;
    server.use(
      http.post(`${BASE_URL}/reorganize/apply`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json({
          results: [{ current_path: "a", target_path: "b", moved: true, skip_reason: null }],
        });
      })
    );

    const result = await applyReorganization("D:/LOTE 2", [{ current_path: "a", target_path: "b" }]);

    expect(receivedBody).toEqual({ root_path: "D:/LOTE 2", moves: [{ current_path: "a", target_path: "b" }] });
    expect(result.results[0].moved).toBe(true);
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/api/reorganize.test.ts`
Expected: FAIL — `Failed to resolve import "./reorganize"`.

- [ ] **Step 4: Write `frontend/src/api/reorganize.ts`**

```ts
import { apiFetch } from "./client";
import type { ApplyResult, BatchAnalysis, ResolvedMove } from "./types";

export function analyzeReorganization(rootPath: string): Promise<BatchAnalysis> {
  return apiFetch<BatchAnalysis>("/reorganize/analyze", {
    method: "POST",
    body: JSON.stringify({ root_path: rootPath }),
  });
}

export function applyReorganization(rootPath: string, moves: ResolvedMove[]): Promise<ApplyResult> {
  return apiFetch<ApplyResult>("/reorganize/apply", {
    method: "POST",
    body: JSON.stringify({ root_path: rootPath, moves }),
  });
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/api/reorganize.test.ts`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/reorganize.ts frontend/src/api/reorganize.test.ts
git commit -m "Add the reorganize API client"
```

---

## Task 5: `frontend/src/lib/reorganize/proposePath.ts`

**Files:**
- Create: `frontend/src/lib/reorganize/proposePath.ts`
- Test: `frontend/src/lib/reorganize/proposePath.test.ts`

**Interfaces:**
- Consumes: `ReorganizeException` (Task 4).
- Produces: `computeProposedPath(entry: ReorganizeException, correction: Correction): string | null` and the `Correction` interface — both consumed by Task 7 (`ReorganizePanel.tsx`).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/lib/reorganize/proposePath.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { ReorganizeException } from "../../api/types";
import { computeProposedPath } from "./proposePath";

function makeException(overrides: Partial<ReorganizeException> = {}): ReorganizeException {
  return {
    tipo: "DECRETOS",
    kind: "missing_entity_folder",
    current_path: "DECRETOS/2022/D_MSPS_0017AJ_2022.pdf",
    detected_entity: "MSPS",
    detected_year: 2022,
    mtime_year_hint: null,
    proposed_path: null,
    ...overrides,
  };
}

describe("computeProposedPath", () => {
  it("builds Tipo/Entidad/Año/archivo when entity and year are resolved", () => {
    const entry = makeException();
    expect(computeProposedPath(entry, { entity: "MSPS", year: "2022" })).toBe(
      "DECRETOS/MSPS/2022/D_MSPS_0017AJ_2022.pdf"
    );
  });

  it("returns null for missing_entity_folder when entity is blank", () => {
    const entry = makeException({ detected_entity: null });
    expect(computeProposedPath(entry, { entity: "", year: "2022" })).toBeNull();
  });

  it("returns null when year isn't four digits", () => {
    const entry = makeException();
    expect(computeProposedPath(entry, { entity: "MSPS", year: "22" })).toBeNull();
  });

  it("builds Tipo/Año/archivo (no entity segment) for a missing_year_folder entry with no entity", () => {
    const entry = makeException({
      kind: "missing_year_folder",
      current_path: "Leyes/LEY_0042_2019.pdf",
      detected_entity: null,
      detected_year: null,
    });
    expect(computeProposedPath(entry, { entity: "", year: "2019" })).toBe("Leyes/2019/LEY_0042_2019.pdf");
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/lib/reorganize/proposePath.test.ts`
Expected: FAIL — `Failed to resolve import "./proposePath"`.

- [ ] **Step 3: Write `frontend/src/lib/reorganize/proposePath.ts`**

```ts
import type { ReorganizeException } from "../../api/types";

export interface Correction {
  entity: string;
  year: string;
}

function filenameOf(currentPath: string): string {
  const segments = currentPath.split("/");
  return segments[segments.length - 1];
}

export function computeProposedPath(entry: ReorganizeException, correction: Correction): string | null {
  const year = correction.year.trim();
  if (!/^\d{4}$/.test(year)) return null;
  const entity = correction.entity.trim();
  if (entry.kind === "missing_entity_folder" && !entity) return null;
  const filename = filenameOf(entry.current_path);
  return entity ? `${entry.tipo}/${entity}/${year}/${filename}` : `${entry.tipo}/${year}/${filename}`;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/lib/reorganize/proposePath.test.ts`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/reorganize/proposePath.ts frontend/src/lib/reorganize/proposePath.test.ts
git commit -m "Add computeProposedPath: client-side target path preview"
```

---

## Task 6: Relocate the renaming UI into `RenamePanel`

**Files:**
- Create: `frontend/src/pages/formatter/RenamePanel.tsx`
- Create: `frontend/src/pages/formatter/RenamePanel.test.tsx`
- Delete: `frontend/src/pages/FormatterPage.test.tsx` (its content moves into `RenamePanel.test.tsx`; Task 8 writes a fresh, much smaller `FormatterPage.test.tsx` for the tab shell)

`frontend/src/pages/FormatterPage.tsx` itself is **not modified or deleted** in this task — it keeps working exactly as before until Task 8 replaces it with the tab shell. This is a pure relocation: no behavior changes, so there's no new RED/GREEN cycle — the existing assertions are the regression check.

**Interfaces:**
- Produces: `RenamePanel()` (React component), consumed by Task 8's `FormatterPage.tsx`.

- [ ] **Step 1: Create `frontend/src/pages/formatter/RenamePanel.tsx`**

Same content as `frontend/src/pages/FormatterPage.tsx`, with these exact changes:
- Drop the `import { Wand2 } from "lucide-react";` line (only used by the header block being removed).
- Every import starting with `"../components/`, `"../lib/` gains one more `../` (the file moved one directory deeper): `"../components/..."` → `"../../components/..."`, `"../lib/..."` → `"../../lib/..."`.
- Rename the exported function from `FormatterPage` to `RenamePanel`.
- Remove the header block (the eyebrow icon + "Renombrado de lotes" + the `<h1>Laboratorio</h1>`) — that now lives once in the Task 8 tab shell, not per-panel. The component's JSX starts directly with the outer `<div className="space-y-6">` immediately followed by the `{state.step === "unsupported" && ...}` block.

```tsx
import { useState } from "react";
import { ErrorBanner } from "../../components/ErrorBanner";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import {
  analyzeDirectory,
  applyCorrections,
  computeFinalName,
  FormatterError,
  type Correction,
  type FormatterPlan,
} from "../../lib/formatter/analyze";
import { copyFormattedFiles } from "../../lib/formatter/copy";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TH, THEAD_ROW } from "../../lib/tableStyles";

type FormatterState =
  | { step: "idle"; notice?: string }
  | { step: "unsupported" }
  | { step: "error"; message: string }
  | { step: "loaded"; inputRoot: FileSystemDirectoryHandle; plan: FormatterPlan; corrections: Map<string, Correction> }
  | { step: "copying"; done: number; total: number };

const REASON_LABEL: Record<string, string> = {
  "no-year": "Año no detectado",
  "no-number": "Número no detectado",
  duplicate: "Número duplicado",
};

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function RenamePanel() {
  const [state, setState] = useState<FormatterState>(() =>
    "showDirectoryPicker" in window ? { step: "idle" } : { step: "unsupported" }
  );

  async function handlePickInput() {
    try {
      const root = await window.showDirectoryPicker();
      const plan = await analyzeDirectory(root);
      setState({ step: "loaded", inputRoot: root, plan, corrections: new Map() });
    } catch (error) {
      if (isAbortError(error)) return;
      const message = error instanceof FormatterError ? error.message : "No se pudo leer la carpeta.";
      setState({ step: "error", message });
    }
  }

  function handleCorrectionChange(path: string, field: keyof Correction, value: string) {
    if (state.step !== "loaded") return;
    const entry = state.plan.entries.find((candidate) => candidate.path === path);
    if (!entry) return;
    const corrections = new Map(state.corrections);
    const current =
      corrections.get(path) ?? { year: String(entry.detectedYear ?? ""), number: String(entry.detectedNumber ?? "") };
    corrections.set(path, { ...current, [field]: value });
    setState({ ...state, corrections });
  }

  async function handleCopy() {
    if (state.step !== "loaded") return;
    const resolvedPlan = applyCorrections(state.plan, state.corrections);
    const resolvedNames = new Map<string, string>();
    for (const entry of resolvedPlan.entries) {
      const name = computeFinalName(resolvedPlan.config, entry);
      if (name) {
        resolvedNames.set(entry.path, name);
      } else if (entry.reason === "no-number") {
        // No number could be determined and the user didn't correct it — copy
        // the file through with its original name instead of blocking the
        // whole batch on a number nobody can reliably guess.
        resolvedNames.set(entry.path, entry.filename);
      }
    }

    let outputRoot: FileSystemDirectoryHandle;
    try {
      outputRoot = await window.showDirectoryPicker({ mode: "readwrite" });
    } catch (error) {
      if (isAbortError(error)) return;
      setState({ step: "error", message: "No se pudo abrir la carpeta de salida." });
      return;
    }

    if (await state.inputRoot.isSameEntry(outputRoot)) {
      setState({ step: "error", message: "La carpeta de salida no puede ser la misma que la de entrada." });
      return;
    }

    setState({ step: "copying", done: 0, total: resolvedNames.size });
    try {
      const { copiedCount, skippedCount } = await copyFormattedFiles(
        outputRoot,
        resolvedPlan,
        resolvedNames,
        (done, total) => {
          if (done % 20 === 0 || done === total) setState({ step: "copying", done, total });
        }
      );
      const copiedLabel = `${copiedCount} archivo${copiedCount === 1 ? "" : "s"} copiado${copiedCount === 1 ? "" : "s"}`;
      setState({
        step: "idle",
        notice:
          skippedCount > 0
            ? `${copiedLabel}, ${skippedCount} omitido${skippedCount === 1 ? "" : "s"} por error de lectura.`
            : `${copiedLabel}.`,
      });
    } catch {
      setState({ step: "error", message: "No se pudo completar la copia." });
    }
  }

  return (
    <div className="space-y-6">
      {state.step === "unsupported" && (
        <ErrorBanner message="Esta función necesita Chrome o Edge; tu navegador actual no es compatible." />
      )}

      {state.step === "idle" && (
        <div className={TABLE_SHELL}>
          <div className="flex flex-col items-center gap-3 px-4 py-10 text-center">
            {state.notice && <p className="text-xs text-muted-foreground">{state.notice}</p>}
            <p className="text-sm text-muted-foreground">
              Elige la carpeta para renombrar los archivos.
            </p>
            <Button onClick={() => void handlePickInput()}>Elegir carpeta de entrada</Button>
          </div>
        </div>
      )}

      {state.step === "error" && <ErrorBanner message={state.message} onRetry={() => setState({ step: "idle" })} />}

      {state.step === "copying" && (
        <p className="text-sm text-muted-foreground">
          Copiando {state.done} / {state.total}…
        </p>
      )}

      {state.step === "loaded" &&
        (() => {
          const resolvedPlan = applyCorrections(state.plan, state.corrections);
          const pending = resolvedPlan.entries.filter((entry) => entry.reason !== null && entry.reason !== "no-number");
          const passthrough = resolvedPlan.entries.filter((entry) => entry.reason === "no-number");
          const visibleRows = resolvedPlan.entries.filter((entry) => {
            if (entry.reason === "no-number" && !state.corrections.has(entry.path)) return false;
            return entry.reason !== null || state.corrections.has(entry.path);
          });
          const ready = resolvedPlan.entries.length - pending.length - passthrough.length;
          const canCopy = pending.length === 0;

          return (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {ready} archivo{ready === 1 ? "" : "s"} listo{ready === 1 ? "" : "s"}
                {passthrough.length > 0
                  ? `, ${passthrough.length} sin número (se copiarán con su nombre original)`
                  : ""}
                {pending.length > 0 ? `, ${pending.length} por revisar` : ""}.
              </p>

              {visibleRows.length > 0 && (
                <div className={TABLE_SHELL}>
                  <div className={TABLE_SCROLL}>
                    <table className={TABLE}>
                      <thead>
                        <tr className={THEAD_ROW}>
                          <th className={TH}>Archivo</th>
                          <th className={TH}>Motivo</th>
                          <th className={TH}>Año</th>
                          <th className={TH}>Número</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visibleRows.map((entry) => {
                          const correction = state.corrections.get(entry.path);
                          const yearValue = correction ? correction.year : String(entry.detectedYear ?? "");
                          const numberValue = correction ? correction.number : String(entry.detectedNumber ?? "");
                          return (
                            <tr key={entry.path} className={TBODY_ROW}>
                              <td className={TD}>{entry.path}</td>
                              <td className={TD}>{entry.reason ? REASON_LABEL[entry.reason] : "Resuelto"}</td>
                              <td className={TD}>
                                <Input
                                  aria-label={`Año para ${entry.path}`}
                                  value={yearValue}
                                  onChange={(event) => handleCorrectionChange(entry.path, "year", event.target.value)}
                                  className="w-24"
                                />
                              </td>
                              <td className={TD}>
                                <Input
                                  aria-label={`Número para ${entry.path}`}
                                  value={numberValue}
                                  onChange={(event) => handleCorrectionChange(entry.path, "number", event.target.value)}
                                  className="w-24"
                                />
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <Button onClick={() => void handleCopy()} disabled={!canCopy}>
                Elegir carpeta de salida y copiar
              </Button>
            </div>
          );
        })()}
    </div>
  );
}
```

- [ ] **Step 2: Create `frontend/src/pages/formatter/RenamePanel.test.tsx`**

Same content as `frontend/src/pages/FormatterPage.test.tsx`, with:
- `import { FormatterPage } from "./FormatterPage";` → `import { RenamePanel } from "./RenamePanel";`
- `import { fakeInputDirectory, fakeOutputDirectory } from "../lib/formatter/testFsFakes";` → `import { fakeInputDirectory, fakeOutputDirectory } from "../../lib/formatter/testFsFakes";`
- `describe("FormatterPage", ...)` → `describe("RenamePanel", ...)`
- Every `<FormatterPage />` → `<RenamePanel />` (8 occurrences)

No other text changes — every assertion stays exactly as it is today.

- [ ] **Step 3: Delete the old test file**

```bash
git rm frontend/src/pages/FormatterPage.test.tsx
```

- [ ] **Step 4: Run the relocated test file**

Run: `cd frontend && npx vitest run src/pages/formatter/RenamePanel.test.tsx`
Expected: 8 passed (same 8 tests, unchanged assertions).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/formatter/RenamePanel.tsx frontend/src/pages/formatter/RenamePanel.test.tsx
git commit -m "Move the renaming UI into formatter/RenamePanel, unchanged"
```

---

## Task 7: `frontend/src/pages/formatter/ReorganizePanel.tsx`

**Files:**
- Create: `frontend/src/pages/formatter/ReorganizePanel.tsx`
- Test: `frontend/src/pages/formatter/ReorganizePanel.test.tsx`

**Interfaces:**
- Consumes: `analyzeReorganization`, `applyReorganization` (Task 4); `computeProposedPath`, `Correction` (Task 5); `ReorganizeException` type (Task 4).
- Produces: `ReorganizePanel()` (React component), consumed by Task 8's `FormatterPage.tsx`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/pages/formatter/ReorganizePanel.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { ReorganizePanel } from "./ReorganizePanel";

const BASE_URL = "http://localhost:8000";

describe("ReorganizePanel", () => {
  it("analyzes a path and disables Aplicar until the missing entity is filled in", async () => {
    server.use(
      http.post(`${BASE_URL}/reorganize/analyze`, () =>
        HttpResponse.json({
          root_path: "D:/LOTE 2",
          total_files: 1,
          tipos: [{ tipo: "DECRETOS", total_files: 1, exception_count: 1 }],
          exceptions: [
            {
              tipo: "DECRETOS",
              kind: "missing_entity_folder",
              current_path: "DECRETOS/2022/D_MSPS_0017AJ_2022.pdf",
              detected_entity: null,
              detected_year: 2022,
              mtime_year_hint: null,
              proposed_path: null,
            },
          ],
          extra_depth: [],
        })
      )
    );
    const user = userEvent.setup();
    render(<ReorganizePanel />);

    await user.type(screen.getByLabelText("Ruta de la carpeta"), "D:\\LOTE 2");
    await user.click(screen.getByRole("button", { name: "Analizar" }));

    expect(await screen.findByText("DECRETOS/2022/D_MSPS_0017AJ_2022.pdf")).toBeInTheDocument();
    expect(screen.getByLabelText("Año para DECRETOS/2022/D_MSPS_0017AJ_2022.pdf")).toHaveValue("2022");
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeDisabled();

    await user.type(screen.getByLabelText("Entidad para DECRETOS/2022/D_MSPS_0017AJ_2022.pdf"), "MSPS");

    expect(screen.getByText("DECRETOS/MSPS/2022/D_MSPS_0017AJ_2022.pdf")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeEnabled();
  });

  it("shows extra-depth entries as informational only, without an Entidad/Año row", async () => {
    server.use(
      http.post(`${BASE_URL}/reorganize/analyze`, () =>
        HttpResponse.json({
          root_path: "D:/LOTE 2",
          total_files: 1,
          tipos: [],
          exceptions: [],
          extra_depth: [{ tipo: "Gacetas", current_path: "Gacetas/GC/1992/AC/AC_0001_1992.pdf" }],
        })
      )
    );
    const user = userEvent.setup();
    render(<ReorganizePanel />);

    await user.type(screen.getByLabelText("Ruta de la carpeta"), "D:\\LOTE 2");
    await user.click(screen.getByRole("button", { name: "Analizar" }));

    expect(await screen.findByText("Gacetas/GC/1992/AC/AC_0001_1992.pdf")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Entidad para Gacetas/)).not.toBeInTheDocument();
  });

  it("pre-fills the year from the mtime hint and applies the resolved move", async () => {
    server.use(
      http.post(`${BASE_URL}/reorganize/analyze`, () =>
        HttpResponse.json({
          root_path: "D:/LOTE 2",
          total_files: 1,
          tipos: [{ tipo: "RESOLUCIONES", total_files: 1, exception_count: 1 }],
          exceptions: [
            {
              tipo: "RESOLUCIONES",
              kind: "missing_year_folder",
              current_path: "RESOLUCIONES/SGCANDINA/RSG2058.docx",
              detected_entity: "SGCANDINA",
              detected_year: null,
              mtime_year_hint: 2022,
              proposed_path: null,
            },
          ],
          extra_depth: [],
        })
      ),
      http.post(`${BASE_URL}/reorganize/apply`, async ({ request }) => {
        const body = (await request.json()) as { root_path: string; moves: { current_path: string; target_path: string }[] };
        expect(body.root_path).toBe("D:\\LOTE 2");
        expect(body.moves).toEqual([
          {
            current_path: "RESOLUCIONES/SGCANDINA/RSG2058.docx",
            target_path: "RESOLUCIONES/SGCANDINA/2022/RSG2058.docx",
          },
        ]);
        return HttpResponse.json({
          results: [
            {
              current_path: "RESOLUCIONES/SGCANDINA/RSG2058.docx",
              target_path: "RESOLUCIONES/SGCANDINA/2022/RSG2058.docx",
              moved: true,
              skip_reason: null,
            },
          ],
        });
      })
    );
    const user = userEvent.setup();
    render(<ReorganizePanel />);

    await user.type(screen.getByLabelText("Ruta de la carpeta"), "D:\\LOTE 2");
    await user.click(screen.getByRole("button", { name: "Analizar" }));
    await screen.findByText("RESOLUCIONES/SGCANDINA/RSG2058.docx");

    expect(screen.getByLabelText("Año para RESOLUCIONES/SGCANDINA/RSG2058.docx")).toHaveValue("2022");
    expect(screen.getByRole("button", { name: "Aplicar" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Aplicar" }));

    expect(await screen.findByText(/1 archivo\(s\) movido\(s\)/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/formatter/ReorganizePanel.test.tsx`
Expected: FAIL — `Failed to resolve import "./ReorganizePanel"`.

- [ ] **Step 3: Write `frontend/src/pages/formatter/ReorganizePanel.tsx`**

```tsx
import { useState } from "react";
import { analyzeReorganization, applyReorganization } from "../../api/reorganize";
import type { ApplyResult, BatchAnalysis, ReorganizeException, ResolvedMove } from "../../api/types";
import { ErrorBanner } from "../../components/ErrorBanner";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { computeProposedPath, type Correction } from "../../lib/reorganize/proposePath";
import { TABLE, TABLE_SCROLL, TABLE_SHELL, TBODY_ROW, TD, TH, THEAD_ROW } from "../../lib/tableStyles";

type ReorganizeState =
  | { step: "idle" }
  | { step: "loading" }
  | { step: "error"; message: string }
  | { step: "loaded"; analysis: BatchAnalysis; corrections: Map<string, Correction> }
  | { step: "applying" }
  | { step: "applied"; result: ApplyResult };

function initialCorrection(entry: ReorganizeException): Correction {
  const year = entry.detected_year ?? entry.mtime_year_hint;
  return { entity: entry.detected_entity ?? "", year: year !== null ? String(year) : "" };
}

export function ReorganizePanel() {
  const [rootPath, setRootPath] = useState("");
  const [state, setState] = useState<ReorganizeState>({ step: "idle" });

  async function handleAnalyze() {
    setState({ step: "loading" });
    try {
      const analysis = await analyzeReorganization(rootPath);
      setState({ step: "loaded", analysis, corrections: new Map() });
    } catch {
      setState({ step: "error", message: "No se pudo analizar la carpeta." });
    }
  }

  function handleCorrectionChange(currentPath: string, field: keyof Correction, value: string) {
    if (state.step !== "loaded") return;
    const entry = state.analysis.exceptions.find((e) => e.current_path === currentPath);
    if (!entry) return;
    const corrections = new Map(state.corrections);
    const current = corrections.get(currentPath) ?? initialCorrection(entry);
    corrections.set(currentPath, { ...current, [field]: value });
    setState({ ...state, corrections });
  }

  async function handleApply() {
    if (state.step !== "loaded") return;
    const moves: ResolvedMove[] = [];
    for (const entry of state.analysis.exceptions) {
      const correction = state.corrections.get(entry.current_path) ?? initialCorrection(entry);
      const target = computeProposedPath(entry, correction);
      if (target) moves.push({ current_path: entry.current_path, target_path: target });
    }
    setState({ step: "applying" });
    try {
      const result = await applyReorganization(rootPath, moves);
      setState({ step: "applied", result });
    } catch {
      setState({ step: "error", message: "No se pudo aplicar la reorganización." });
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-2">
        <div className="flex-1 space-y-1">
          <label htmlFor="reorganize-root-path" className="text-sm font-medium text-foreground">
            Ruta de la carpeta
          </label>
          <Input
            id="reorganize-root-path"
            value={rootPath}
            onChange={(event) => setRootPath(event.target.value)}
            placeholder="D:\LOTE 2"
          />
        </div>
        <Button onClick={() => void handleAnalyze()} disabled={!rootPath || state.step === "loading"}>
          Analizar
        </Button>
      </div>

      {state.step === "error" && <ErrorBanner message={state.message} onRetry={() => setState({ step: "idle" })} />}
      {state.step === "loading" && <p className="text-sm text-muted-foreground">Analizando…</p>}
      {state.step === "applying" && <p className="text-sm text-muted-foreground">Aplicando…</p>}

      {state.step === "applied" && (
        <p className="text-sm text-muted-foreground">
          {state.result.results.filter((r) => r.moved).length} archivo(s) movido(s),{" "}
          {state.result.results.filter((r) => !r.moved).length} omitido(s).
        </p>
      )}

      {state.step === "loaded" &&
        (() => {
          const { analysis, corrections } = state;
          const rows = analysis.exceptions.map((entry) => {
            const correction = corrections.get(entry.current_path) ?? initialCorrection(entry);
            const proposedPath = computeProposedPath(entry, correction);
            return { entry, correction, proposedPath };
          });
          const canApply = rows.length > 0 && rows.every((row) => row.proposedPath !== null);

          return (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {analysis.total_files} archivo(s) analizados, {analysis.exceptions.length} excepción(es),{" "}
                {analysis.extra_depth.length} carpeta(s) con profundidad extra (informativo).
              </p>

              {rows.length > 0 && (
                <div className={TABLE_SHELL}>
                  <div className={TABLE_SCROLL}>
                    <table className={TABLE}>
                      <thead>
                        <tr className={THEAD_ROW}>
                          <th className={TH}>Tipo</th>
                          <th className={TH}>Ruta actual</th>
                          <th className={TH}>Entidad</th>
                          <th className={TH}>Año</th>
                          <th className={TH}>Ruta propuesta</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map(({ entry, correction, proposedPath }) => (
                          <tr key={entry.current_path} className={TBODY_ROW}>
                            <td className={TD}>{entry.tipo}</td>
                            <td className={TD}>{entry.current_path}</td>
                            <td className={TD}>
                              <Input
                                aria-label={`Entidad para ${entry.current_path}`}
                                value={correction.entity}
                                onChange={(event) =>
                                  handleCorrectionChange(entry.current_path, "entity", event.target.value)
                                }
                                className="w-28"
                              />
                            </td>
                            <td className={TD}>
                              <Input
                                aria-label={`Año para ${entry.current_path}`}
                                value={correction.year}
                                onChange={(event) =>
                                  handleCorrectionChange(entry.current_path, "year", event.target.value)
                                }
                                className="w-24"
                              />
                            </td>
                            <td className={TD}>{proposedPath ?? "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {analysis.extra_depth.length > 0 && (
                <div className={TABLE_SHELL}>
                  <div className={TABLE_SCROLL}>
                    <table className={TABLE}>
                      <thead>
                        <tr className={THEAD_ROW}>
                          <th className={TH}>Tipo</th>
                          <th className={TH}>Ruta (no se modifica)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {analysis.extra_depth.map((item) => (
                          <tr key={item.current_path} className={TBODY_ROW}>
                            <td className={TD}>{item.tipo}</td>
                            <td className={TD}>{item.current_path}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <Button onClick={() => void handleApply()} disabled={!canApply}>
                Aplicar
              </Button>
            </div>
          );
        })()}
    </div>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/formatter/ReorganizePanel.test.tsx`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/formatter/ReorganizePanel.tsx frontend/src/pages/formatter/ReorganizePanel.test.tsx
git commit -m "Add ReorganizePanel: analyze/review/apply UI for the batch reorganizer"
```

---

## Task 8: `FormatterPage.tsx` — tab shell

**Files:**
- Modify: `frontend/src/pages/FormatterPage.tsx` (full rewrite)
- Create: `frontend/src/pages/FormatterPage.test.tsx` (fresh file — the old one was deleted in Task 6)

**Interfaces:**
- Consumes: `RenamePanel` (Task 6), `ReorganizePanel` (Task 7).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/FormatterPage.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FormatterPage } from "./FormatterPage";

describe("FormatterPage", () => {
  it("shows the Renombrado panel by default and switches to Reorganización on tab click", async () => {
    const user = userEvent.setup();
    render(<FormatterPage />);

    expect(screen.getByRole("heading", { name: "Laboratorio" })).toBeInTheDocument();
    expect(screen.getByText(/necesita Chrome o Edge/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Ruta de la carpeta")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reorganización" }));

    expect(screen.getByLabelText("Ruta de la carpeta")).toBeInTheDocument();
    expect(screen.queryByText(/necesita Chrome o Edge/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Renombrado" }));

    expect(screen.getByText(/necesita Chrome o Edge/)).toBeInTheDocument();
  });
});
```

This test relies on `showDirectoryPicker` being undefined in the jsdom test environment (confirmed by the pre-existing "shows the unsupported-browser message" test that Task 6 relocated into `RenamePanel.test.tsx`) — no stubbing needed.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/FormatterPage.test.tsx`
Expected: FAIL — `getByRole("button", { name: "Reorganización" })` not found (current `FormatterPage` has no tabs).

- [ ] **Step 3: Rewrite `frontend/src/pages/FormatterPage.tsx`**

```tsx
import { useState } from "react";
import { Wand2 } from "lucide-react";
import { RenamePanel } from "./formatter/RenamePanel";
import { ReorganizePanel } from "./formatter/ReorganizePanel";

type Tab = "rename" | "reorganize";

const TABS: { id: Tab; label: string }[] = [
  { id: "rename", label: "Renombrado" },
  { id: "reorganize", label: "Reorganización" },
];

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

      {tab === "rename" ? <RenamePanel /> : <ReorganizePanel />}
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/FormatterPage.test.tsx`
Expected: 1 passed.

- [ ] **Step 5: Run the full frontend suite**

Run: `cd frontend && npx vitest run`
Expected: all test files pass, including `RenamePanel.test.tsx` and `ReorganizePanel.test.tsx`.

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/FormatterPage.tsx frontend/src/pages/FormatterPage.test.tsx
git commit -m "Turn Laboratorio into a Renombrado/Reorganización tab shell"
```

---

## Final check (not a task — run after Task 8)

- Backend: `pytest tests/test_core_reorganize.py tests/test_api_reorganize.py -v` — 17 passed.
- Frontend: `cd frontend && npx vitest run` — full suite green.
- Frontend: `cd frontend && npx tsc --noEmit` — no errors.
- Manual smoke check (optional, since this tool is dev-only and admin-gated): log in as the admin user, open Laboratorio → Reorganización, point it at a small real folder, confirm the exceptions table and Aplicar behave as expected before ever pointing it at a production batch.
