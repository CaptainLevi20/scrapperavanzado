import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import core.reorganize as reorganize_module
from core.reorganize import analyze_batch, apply_moves
from api.schemas import ResolvedMove


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
    # A second entity-like dir is required so entity_like (PGN, OTRO) outnumbers
    # year_like (2022) under the strict-majority tie-break — a bare 1-vs-1 tie
    # now resolves to sin_entidad (see the Leyes/{backup,temp} tie-break test).
    (tmp_path / "DECRETOS" / "OTRO").mkdir(parents=True, exist_ok=True)

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
    # See test_missing_entity_folder_resolved_from_filename: a second entity-like
    # dir avoids a 1-vs-1 tie with the "2022" year folder under the strict-majority
    # tie-break.
    (tmp_path / "DECRETOS" / "OTRO").mkdir(parents=True, exist_ok=True)

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


def test_tipo_with_no_subdirectories_at_all_reports_bare_files_as_extra_depth(tmp_path):
    _touch(tmp_path / "ACTAS" / "ACTA_0001_2020.pdf")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert len(result.extra_depth) == 1
    entry = result.extra_depth[0]
    assert entry.tipo == "ACTAS"
    assert entry.current_path == "ACTAS/ACTA_0001_2020.pdf"
    assert result.total_files == 1
    assert _by_tipo(result, "ACTAS").total_files == 1
    assert _by_tipo(result, "ACTAS").exception_count == 0


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


def test_apply_moves_skips_a_target_outside_the_root(tmp_path):
    source = tmp_path / "DECRETOS" / "2022" / "D_MSPS_0017AJ_2022.pdf"
    _touch(source, content="contenido")

    result = apply_moves(
        tmp_path,
        [ResolvedMove(current_path="DECRETOS/2022/D_MSPS_0017AJ_2022.pdf", target_path="../outside.pdf")],
    )

    assert result.results[0].moved is False
    assert result.results[0].skip_reason is not None
    assert source.exists()
    assert not (tmp_path.parent / "outside.pdf").exists()


def test_apply_moves_skips_a_source_outside_the_root(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside-source.pdf"
    _touch(outside, content="contenido")
    try:
        result = apply_moves(
            tmp_path,
            [ResolvedMove(current_path="../" + outside.name, target_path="DECRETOS/MSPS/2022/x.pdf")],
        )

        assert result.results[0].moved is False
        assert result.results[0].skip_reason is not None
        assert outside.exists()
        assert not (tmp_path / "DECRETOS" / "MSPS" / "2022" / "x.pdf").exists()
    finally:
        outside.unlink(missing_ok=True)


def test_apply_moves_one_failure_does_not_abort_the_rest(tmp_path, monkeypatch):
    moves = []
    for i in range(3):
        source = tmp_path / "DECRETOS" / "2022" / f"file{i}.pdf"
        _touch(source, content=f"contenido-{i}")
        moves.append(
            ResolvedMove(
                current_path=f"DECRETOS/2022/file{i}.pdf",
                target_path=f"DECRETOS/MSPS/2022/file{i}.pdf",
            )
        )

    real_move = shutil.move
    call_count = {"n": 0}

    def flaky_move(src, dst):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise PermissionError("Acceso denegado")
        return real_move(src, dst)

    monkeypatch.setattr(reorganize_module.shutil, "move", flaky_move)

    result = apply_moves(tmp_path, moves)

    assert result.results[0].moved is False
    assert result.results[0].skip_reason is not None
    assert result.results[1].moved is True
    assert result.results[2].moved is True


def test_extra_depth_is_capped_but_total_reflects_true_count(tmp_path, monkeypatch):
    monkeypatch.setattr(reorganize_module, "EXTRA_DEPTH_LIMIT", 3)
    for i in range(5):
        _touch(tmp_path / "Gacetas" / "GC" / "1992" / "AC" / f"AC_000{i}_1992.pdf")

    result = analyze_batch(tmp_path)

    assert len(result.extra_depth) == 3
    assert result.extra_depth_total == 5


def test_tie_between_nonzero_entity_like_and_year_like_dirs_stays_sin_entidad(tmp_path):
    _touch(tmp_path / "Leyes" / "2020" / "L_0001_2020.pdf")
    _touch(tmp_path / "Leyes" / "2021" / "L_0002_2021.pdf")
    (tmp_path / "Leyes" / "backup").mkdir(parents=True, exist_ok=True)
    (tmp_path / "Leyes" / "temp").mkdir(parents=True, exist_ok=True)

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert result.total_files == 2


def test_root_level_loose_file_is_counted_and_reported(tmp_path):
    _touch(tmp_path / "DECRETOS" / "MSPS" / "2022" / "D_MSPS_0017AJ_2022.pdf")
    _touch(tmp_path / "suelto.pdf")

    result = analyze_batch(tmp_path)

    assert result.total_files == 2
    entry = next(e for e in result.extra_depth if e.current_path == "suelto.pdf")
    assert entry.tipo == ""


def test_detected_entity_rejects_a_year_looking_token(tmp_path):
    _touch(tmp_path / "DECRETOS" / "PGN" / "2019" / "D_PGN_0001_2019.pdf")
    _touch(tmp_path / "DECRETOS" / "2022" / "D_2020_0001_2022.pdf")
    # See test_missing_entity_folder_resolved_from_filename: a second entity-like
    # dir avoids a 1-vs-1 tie with the "2022" year folder under the strict-majority
    # tie-break.
    (tmp_path / "DECRETOS" / "OTRO").mkdir(parents=True, exist_ok=True)

    result = analyze_batch(tmp_path)

    exc = next(e for e in result.exceptions if e.current_path.endswith("D_2020_0001_2022.pdf"))
    assert exc.detected_entity is None
    assert exc.proposed_path is None
