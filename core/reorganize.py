from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import re
import shutil

from api.schemas import (
    ApplyResult,
    BatchAnalysis,
    ExtraDepthEntry,
    FolderRenameOutcome,
    FolderRenameSuggestion,
    MoveResult,
    ReorganizeException,
    ResolvedFolderRename,
    ResolvedMove,
    TipoSummary,
)

YEAR_RE = re.compile(r"^(?:1[89]\d{2}|20\d{2})$")

# OS-generated junk, never a real document — ignored entirely: not counted,
# not listed as an exception or as extra_depth, nothing asks about it.
_IGNORED_FILENAMES = {"thumbs.db", "desktop.ini", ".ds_store"}


def _is_year_name(name: str) -> bool:
    return bool(YEAR_RE.match(name))


def _is_ignored_file(name: str) -> bool:
    return name.lower() in _IGNORED_FILENAMES


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
    # A real entity code is always at least partly alphabetic (MSPS, PGN,
    # AGN, GC...) — a purely numeric second token means the filename
    # actually follows the shorter CODIGO_NUMERO_AÑO convention (no entity
    # segment at all, e.g. Gacetas' GC_0114_1992.pdf), and what looked like
    # "parts[1]" is really the document number, not an entity. isdigit()
    # also covers a year mistakenly landing in that position.
    return None if entity.isdigit() else entity


def _relpath(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _collect_extra_depth(root: Path, tipo: str, start: Path, out: list[ExtraDepthEntry]) -> int:
    count = 0
    for f in sorted(start.rglob("*")):
        if f.is_file() and not _is_ignored_file(f.name):
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


def _entity_mismatch_exception(root: Path, tipo: str, correct_entity: str, year: int, file: Path) -> ReorganizeException:
    return ReorganizeException(
        tipo=tipo,
        kind="entity_mismatch",
        current_path=_relpath(root, file),
        detected_entity=correct_entity,
        detected_year=year,
        mtime_year_hint=None,
        proposed_path=f"{tipo}/{correct_entity}/{year}/{file.name}",
    )


def _year_mismatch_exception(root: Path, tipo: str, entity: str, correct_year: int, file: Path) -> ReorganizeException:
    return ReorganizeException(
        tipo=tipo,
        kind="year_mismatch",
        current_path=_relpath(root, file),
        detected_entity=entity,
        detected_year=correct_year,
        mtime_year_hint=None,
        proposed_path=f"{tipo}/{entity}/{correct_year}/{file.name}",
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
    folder_renames: list[FolderRenameSuggestion] = []
    total_files = 0

    # Files sitting directly in root (outside any Tipo folder) don't fit the
    # audit rule at all, but they must not silently vanish from the count —
    # same principle as the extra_depth handling below for deeper nesting.
    for p in sorted(f for f in root.iterdir() if f.is_file() and not _is_ignored_file(f.name)):
        extra_depth.append(ExtraDepthEntry(tipo="", current_path=_relpath(root, p)))
        total_files += 1

    for tipo_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        tipo = tipo_dir.name
        dir_children = sorted(c for c in tipo_dir.iterdir() if c.is_dir())
        file_children = sorted(c for c in tipo_dir.iterdir() if c.is_file() and not _is_ignored_file(c.name))
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
                            if _is_ignored_file(f.name):
                                continue
                            tipo_total += 1
                            tipo_exceptions += 1
                            exceptions.append(_missing_entity_exception(root, tipo, year, f))
                        else:
                            tipo_total += _collect_extra_depth(root, tipo, f, extra_depth)
                else:
                    entity = child.name
                    # Bare files (missing_year) and non-year dirs (extra_depth) are
                    # unaffected by a possible folder rename below — handled directly.
                    # Files already at Entidad/Año/archivo are collected first: if
                    # ALL of them consistently resolve to the same DIFFERENT entity,
                    # the real fix isn't moving each file individually, it's renaming
                    # the whole Entidad folder once (see below).
                    year_files: list[tuple[int, Path]] = []
                    for ec in sorted(child.iterdir()):
                        if ec.is_file():
                            if _is_ignored_file(ec.name):
                                continue
                            tipo_total += 1
                            tipo_exceptions += 1
                            exceptions.append(_missing_year_exception(root, tipo, entity, ec))
                        elif _is_year_name(ec.name):
                            year = int(ec.name)
                            for f in sorted(ec.iterdir()):
                                if f.is_file():
                                    if _is_ignored_file(f.name):
                                        continue
                                    tipo_total += 1
                                    year_files.append((year, f))
                                else:
                                    tipo_total += _collect_extra_depth(root, tipo, f, extra_depth)
                        else:
                            tipo_total += _collect_extra_depth(root, tipo, ec, extra_depth)

                    resolved = [
                        (year, f, _detect_entity_from_filename(f.name), _detect_year_from_filename(f.name))
                        for year, f in year_files
                    ]
                    # Evidence FOR keeping the current folder name at all disqualifies a
                    # whole-folder rename — a mixed folder (some files agree, some don't)
                    # is genuine ambiguity, left to per-file review instead of guessing.
                    agrees_with_folder = any(ce == entity for _, _, ce, _ in resolved if ce is not None)
                    disagreeing = {ce for _, _, ce, _ in resolved if ce is not None and ce != entity}
                    suggested_entity = next(iter(disagreeing)) if len(disagreeing) == 1 else None
                    mismatched = [(y, f) for y, f, ce, _ in resolved if ce == suggested_entity]
                    sibling_names = {d.name for d in dir_children}

                    if (
                        not agrees_with_folder
                        and suggested_entity is not None
                        # Require at least 2 agreeing files — a single file's typo is
                        # exactly what per-file entity_mismatch already handles, and a
                        # whole-folder rename shouldn't rest on one data point.
                        and len(mismatched) >= 2
                        # Never propose renaming onto a folder that already exists —
                        # that would be a merge, not a rename, and deserves its own
                        # explicit review rather than being silently offered here.
                        and suggested_entity not in sibling_names
                    ):
                        tipo_exceptions += len(mismatched)
                        folder_renames.append(
                            FolderRenameSuggestion(
                                tipo=tipo,
                                current_entity=entity,
                                suggested_entity=suggested_entity,
                                current_path=_relpath(root, child),
                                proposed_path=f"{tipo}/{suggested_entity}",
                                file_count=len(mismatched),
                            )
                        )
                    else:
                        for year, f, correct_entity, correct_year in resolved:
                            # The file already sits at Tipo/Entidad/Año — structurally
                            # complete — but either folder might be wrong (a catch-all
                            # "ARCHIVO" bucket, or a file filed under the wrong year)
                            # while the filename encodes the real values. Only flag
                            # when the filename resolves to something DIFFERENT from
                            # the folder; an unparseable filename can't prove the
                            # folder wrong, so it stays as-is. Entity takes priority
                            # when both are wrong — the corrected year still rides
                            # along on that same proposed move, rather than raising
                            # two separate exceptions for one file.
                            entity_wrong = correct_entity is not None and correct_entity != entity
                            year_wrong = correct_year is not None and correct_year != year
                            if entity_wrong:
                                tipo_exceptions += 1
                                exceptions.append(
                                    _entity_mismatch_exception(
                                        root, tipo, correct_entity, correct_year if year_wrong else year, f
                                    )
                                )
                            elif year_wrong:
                                tipo_exceptions += 1
                                exceptions.append(_year_mismatch_exception(root, tipo, entity, correct_year, f))
        else:
            for child in dir_children:
                if _is_year_name(child.name):
                    for f in sorted(child.iterdir()):
                        if f.is_file():
                            if _is_ignored_file(f.name):
                                continue
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
        folder_renames=folder_renames,
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


def apply_folder_renames(root: Path, renames: list[ResolvedFolderRename]) -> list[FolderRenameOutcome]:
    results: list[FolderRenameOutcome] = []
    root_resolved = root.resolve()
    for rename in renames:
        source = root / rename.current_path
        target = root / rename.target_path
        try:
            if not source.resolve().is_relative_to(root_resolved) or not target.resolve().is_relative_to(
                root_resolved
            ):
                results.append(
                    FolderRenameOutcome(
                        current_path=rename.current_path,
                        target_path=rename.target_path,
                        renamed=False,
                        skip_reason="La ruta está fuera de la carpeta raíz",
                    )
                )
                continue
            if not source.is_dir():
                results.append(
                    FolderRenameOutcome(
                        current_path=rename.current_path,
                        target_path=rename.target_path,
                        renamed=False,
                        skip_reason="La carpeta de origen ya no existe",
                    )
                )
                continue
            if target.exists():
                results.append(
                    FolderRenameOutcome(
                        current_path=rename.current_path,
                        target_path=rename.target_path,
                        renamed=False,
                        skip_reason="El destino ya existe",
                    )
                )
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            results.append(
                FolderRenameOutcome(
                    current_path=rename.current_path, target_path=rename.target_path, renamed=True, skip_reason=None
                )
            )
        except OSError as exc:
            results.append(
                FolderRenameOutcome(
                    current_path=rename.current_path, target_path=rename.target_path, renamed=False, skip_reason=str(exc)
                )
            )
    return results
