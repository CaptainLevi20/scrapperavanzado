from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import re
import shutil

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
    if len(parts) < 3:
        return None
    entity = parts[1]
    return None if _is_year_name(entity) else entity


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


EXTRA_DEPTH_LIMIT = 500


def analyze_batch(root: Path) -> BatchAnalysis:
    tipos: list[TipoSummary] = []
    exceptions: list[ReorganizeException] = []
    extra_depth: list[ExtraDepthEntry] = []
    total_files = 0

    # Files sitting directly in root (outside any Tipo folder) don't fit the
    # audit rule at all, but they must not silently vanish from the count —
    # same principle as the extra_depth handling below for deeper nesting.
    for p in sorted(f for f in root.iterdir() if f.is_file()):
        extra_depth.append(ExtraDepthEntry(tipo="", current_path=_relpath(root, p)))
        total_files += 1

    for tipo_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        tipo = tipo_dir.name
        dir_children = sorted(c for c in tipo_dir.iterdir() if c.is_dir())
        file_children = sorted(c for c in tipo_dir.iterdir() if c.is_file())
        year_like = [c for c in dir_children if _is_year_name(c.name)]
        entity_like = [c for c in dir_children if not _is_year_name(c.name)]
        if len(entity_like) == 0 and len(year_like) == 0:
            # Zero subdirectories: no structural evidence either way. Tie-break to
            # con_entidad=True — this avoids guessing sin_entidad and risking a
            # proposed_path silently missing the Entidad segment for every file.
            con_entidad = True
        else:
            # Otherwise require a strict majority. A tie here (both nonzero) means
            # real ambiguity — e.g. a sin_entidad Tipo whose year folders happen to
            # be outnumbered-or-equal by unrelated non-year folders (backups, temp
            # dirs) — and resolving it to con_entidad would misclassify every
            # correctly-placed file under a year folder as a missing_entity_folder
            # exception. Defer to sin_entidad instead.
            con_entidad = len(entity_like) > len(year_like)

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
        extra_depth=extra_depth[:EXTRA_DEPTH_LIMIT],
        extra_depth_total=len(extra_depth),
    )


def apply_moves(root: Path, moves: list[ResolvedMove]) -> ApplyResult:
    results: list[MoveResult] = []
    root_resolved = root.resolve()
    for move in moves:
        source = root / move.current_path
        target = root / move.target_path
        try:
            if not source.resolve().is_relative_to(root_resolved) or not target.resolve().is_relative_to(
                root_resolved
            ):
                results.append(
                    MoveResult(
                        current_path=move.current_path,
                        target_path=move.target_path,
                        moved=False,
                        skip_reason="La ruta está fuera de la carpeta raíz",
                    )
                )
                continue
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
