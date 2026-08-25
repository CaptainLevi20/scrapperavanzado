import os
from datetime import datetime, timezone
from pathlib import Path

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
