from collections import Counter
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
from core.document_dates import extract_confirmed_year

YEAR_RE = re.compile(r"^(?:1[89]\d{2}|20\d{2})$")

# OS-generated junk, never a real document — ignored entirely: not counted,
# not listed as an exception or as extra_depth, nothing asks about it.
_IGNORED_FILENAMES = {"thumbs.db", "desktop.ini", ".ds_store"}

# Known entity synonyms, confirmed by the user — an old/alternate
# abbreviation that must always resolve to today's correct one, regardless
# of which one happens to be more common in any given folder. This is a
# small, rarely-changing list edited directly here (dev-only tool, no UI
# for it) — add an entry whenever another confirmed synonym turns up.
# Keys are matched case-insensitively (see _detect_entity_from_filename).
_ENTITY_ALIASES = {
    "SHACIENDABOG": "SDHBOG",
    # Siglas de ministerios anteriores al cambio de 2026-09-03 (ver
    # core/backfill_ministerios_siglas.py): archivos viejos deben resolver a
    # la sigla nueva.
    "MEN": "ME",
    "MADR": "MA",
    "MDEPORTE": "MDEP",
    "MINENERGIA": "MME",
    "MININT": "MI",
    "MINJUSTICIA": "MJ",
    "MINTRABAJO": "MTRA",
    "CONBOG": "CONCBOG",
    "SHDBOG": "SDHBOG",
}

# Words that describe the KIND of document (a joint/mixed circular, a
# guide, an attachment...), not a different entity — they land in the same
# filename position as a real entity code but never mean "move this file",
# they just describe the document, with the real entity a few tokens later
# (or absent entirely). Reported real cases: CIRCULAR/PGN/2024/
# C_MIXTA_PGN_0009_2024.pdf ("circular mixta") and CONCEPTO/DAFP/2025/
# CTO_GUIA_DAFP_0000002_2025.pdf ("guía" — a guide, with "DAFP" as the real
# entity right after it). "ANEXO" ("annex/attachment") was caught the same
# way while checking the batch for this exact shape — same reasoning,
# never reported separately. Same rationale as the digit check below: none
# of these are a value worth comparing against a folder name, so they
# resolve to "can't determine" and the file is left exactly where it
# already is.
_NON_ENTITY_TOKENS = {"MIXTA", "CONJUN", "GUIA", "ANEXO"}

# Folder-name corrections confirmed by the user directly, for isolated
# single-file (or few-file) entity folders where the usual majority-vote
# rename can never fire — there's only ever one filename to "vote", so it
# can never reach the >=2 minimum. The correct name is known with
# certainty anyway, so these bypass that minimum entirely. Keyed by
# (Tipo, current folder name); same small, rarely-changing,
# edited-directly-in-code list as _ENTITY_ALIASES above.
_CONFIRMED_FOLDER_RENAMES: dict[tuple[str, str], str] = {
    ("ACUERDOS", "CODIRUMED"): "CONDIRUDEMED",
    ("ACUERDOS", "CRIOACHA"): "CRIOHACHA",
    ("ACUERDOS", "MINAGRICULTURA"): "MA",
}


def _is_year_name(name: str) -> bool:
    return bool(YEAR_RE.match(name))


def _same_entity(a: str, b: str) -> bool:
    # Windows folder names are already case-insensitive (you can't even have
    # "INVIMA" and "invima" as separate sibling folders), so a difference in
    # case alone is never a real mismatch — just inconsistent capitalization
    # in how the filename was typed.
    return a.casefold() == b.casefold()


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
    # A stray space right after the underscore (e.g. "CTO_ CTCP_...") is a
    # data-entry typo, not a different entity — strip it so "CTCP" and
    # " CTCP" resolve to the same value instead of splitting the vote.
    entity = parts[1].strip()
    if not entity:
        return None
    # A real entity code, in every case seen so far, is purely alphabetic —
    # never a single digit in it (MSPS, PGN, AGN, GC, SDHBOG...). A token
    # containing any digit means either the shorter CODIGO_NUMERO_AÑO
    # convention (no entity segment at all, e.g. Gacetas' GC_0114_1992.pdf,
    # where "parts[1]" is really the document number), a year landing in
    # that position, or a filename missing an underscore that merged the
    # entity with the next field (e.g. "CTO_SDHBOG2015IE18890_2015.pdf",
    # meant to be "CTO_SDHBOG_2015IE18890_2015.pdf" — "SDHBOG2015IE18890"
    # is not a real entity, just a data-entry mistake). None of these are a
    # value worth comparing against a folder name, so all of them resolve
    # to "can't determine" rather than risk proposing a garbage folder.
    if any(ch.isdigit() for ch in entity):
        return None
    if entity.upper() in _NON_ENTITY_TOKENS:
        return None
    return _ENTITY_ALIASES.get(entity.upper(), entity)


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
    if year is None:
        # The filename itself encodes no year (real case: CAN "Decisiones"
        # and SGCANDINA "Resoluciones", named only by their sequential
        # instrument number, e.g. "RSG2367.docx") — these official
        # documents reliably print their own real date inside the content
        # itself, which is authoritative unlike mtime (confirmed on real
        # data: a 2012 resolution carried a 2024 mtime, since the file was
        # only recently added to the archive).
        content_year = extract_confirmed_year(file)
        if content_year is not None and YEAR_RE.match(str(content_year)):
            year = content_year
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
                    # A hyphenated entity (e.g. "MME-MJD-MDEF") is a joint circular
                    # co-issued by several entities, not a single one disagreeing with
                    # the folder — it shouldn't count as a vote either way when
                    # deciding whether the whole folder should be renamed. It's not
                    # excluded from per-file entity_mismatch below if that path is
                    # taken instead, only from this folder-level vote.
                    single_entity_resolved = [(y, f, ce) for y, f, ce, _ in resolved if ce is not None and "-" not in ce]
                    # Group every resolved entity case-insensitively (so "CARAUCA" and
                    # "carauca" count as the same value, not two), tracking each
                    # casing's own count so the winning group can propose its most
                    # common spelling.
                    groups: dict[str, list[tuple[int, Path, str]]] = {}
                    for y, f, ce in single_entity_resolved:
                        groups.setdefault(ce.casefold(), []).append((y, f, ce))
                    agree_key = entity.casefold()
                    total_resolved = len(single_entity_resolved)

                    # The winning alternate is whichever non-agreeing group has the
                    # most files — not "the only group that disagrees". A large,
                    # real-world folder always carries a handful of one-off typos
                    # alongside a dominant majority (883-file case: 681 "SDHBOG" +
                    # 190 "SHACIENDABOG" vs. 4 lone one-file misspellings) —
                    # requiring unanimity among every disagreeing file would let
                    # those stragglers block the suggestion for the 871 that really
                    # do agree with each other.
                    candidates = {k: v for k, v in groups.items() if k != agree_key}
                    suggested_entity = None
                    mismatched: list[tuple[int, Path]] = []
                    if candidates:
                        _, winner_files = max(candidates.items(), key=lambda kv: len(kv[1]))
                        suggested_entity = Counter(ce for _, _, ce in winner_files).most_common(1)[0][0]
                        mismatched = [(y, f) for y, f, _ in winner_files]
                    sibling_names_cf = {d.name.casefold() for d in dir_children}
                    confirmed_target = _CONFIRMED_FOLDER_RENAMES.get((tipo, entity))

                    if (
                        confirmed_target is not None
                        and total_resolved > 0
                        and confirmed_target.casefold() not in sibling_names_cf
                    ):
                        # A user-confirmed correction always wins, bypassing the
                        # majority-vote minimum below entirely — it exists precisely
                        # for folders too small (often just one file) to ever reach
                        # that minimum on their own.
                        tipo_exceptions += total_resolved
                        folder_renames.append(
                            FolderRenameSuggestion(
                                tipo=tipo,
                                current_entity=entity,
                                suggested_entity=confirmed_target,
                                current_path=_relpath(root, child),
                                proposed_path=f"{tipo}/{confirmed_target}",
                                file_count=total_resolved,
                            )
                        )
                    elif (
                        suggested_entity is not None
                        # Require at least 2 matching files — a single file's typo is
                        # exactly what per-file entity_mismatch already handles, and a
                        # whole-folder rename shouldn't rest on one data point.
                        and len(mismatched) >= 2
                        # True majority: the winning alternate must outnumber
                        # EVERYONE else combined (the current name plus every other
                        # stray variant), not just beat the current name in
                        # isolation — same principle as the con_entidad/sin_entidad
                        # Tipo tie-break, just extended to more than two groups.
                        and len(mismatched) > total_resolved - len(mismatched)
                        # Never propose renaming onto a folder that already exists —
                        # that would be a merge, not a rename, and deserves its own
                        # explicit review rather than being silently offered here.
                        and suggested_entity.casefold() not in sibling_names_cf
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
                            # two separate exceptions for one file. A hyphenated
                            # entity (a joint document naming more than one, e.g.
                            # "ANCP-DAFP") is never used to propose an entity move
                            # here either — same reasoning as the folder-rename vote
                            # excluding it: it isn't really disagreeing with the
                            # folder, it's just not a single value to compare at all,
                            # even when the folder happens to be none of the parts.
                            entity_wrong = (
                                correct_entity is not None
                                and "-" not in correct_entity
                                and not _same_entity(correct_entity, entity)
                            )
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


def _prune_empty_dirs(root_resolved: Path, start_dir: Path) -> None:
    # Moving the last file out of a folder (e.g. an entity_mismatch fix
    # into a folder that already exists, so it's a per-file move rather
    # than a whole-folder rename) leaves that folder — and its now-empty
    # parent, and so on — behind as orphaned litter. Walk up removing each
    # directory that's completely empty, stopping at the first non-empty
    # one (rmdir raises OSError for that, our natural stop condition) and
    # never at or above the batch root. A leftover Thumbs.db or similar
    # blocks this too — safer to leave a near-empty folder than to also
    # delete files nothing asked to touch.
    current = start_dir.resolve()
    while current != root_resolved and current.is_relative_to(root_resolved):
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


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
            source_parent = source.parent
            shutil.move(str(source), str(target))
            _prune_empty_dirs(root_resolved, source_parent)
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
