import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import core.reorganize as reorganize_module
from core.reorganize import analyze_batch, apply_folder_renames, apply_moves
from api.schemas import ResolvedFolderRename, ResolvedMove


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


def test_ignored_junk_files_are_excluded_everywhere(tmp_path):
    # Root-level junk.
    _touch(tmp_path / "Thumbs.db")
    # Bare junk directly under a con_entidad Tipo (would otherwise be extra_depth).
    _touch(tmp_path / "DECRETOS" / "desktop.ini")
    # Junk sitting alongside an already-correctly-placed file.
    _touch(tmp_path / "DECRETOS" / "PGN" / "2019" / "D_PGN_0001_2019.pdf")
    _touch(tmp_path / "DECRETOS" / "PGN" / "2019" / "Thumbs.db")
    # Junk in a Tipo/Año folder (would otherwise be missing_entity_folder).
    _touch(tmp_path / "DECRETOS" / "2022" / "Thumbs.db")
    # A second entity-like dir so DECRETOS' entity_like (PGN, OTRO) strictly
    # outnumbers year_like (2022) under the majority tie-break.
    (tmp_path / "DECRETOS" / "OTRO").mkdir(parents=True, exist_ok=True)
    # Junk in a Tipo/Entidad folder (would otherwise be missing_year_folder).
    _touch(tmp_path / "RESOLUCIONES" / "SGCANDINA" / "desktop.ini")
    # Junk in a sin_entidad Tipo's year folder, with an UPPERCASE variant —
    # detection must be case-insensitive (Windows filenames are too).
    _touch(tmp_path / "Leyes" / "2022" / "L_0001_2022.pdf")
    _touch(tmp_path / "Leyes" / "2022" / "THUMBS.DB")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert result.extra_depth == []
    assert result.total_files == 2  # only D_PGN_0001_2019.pdf and L_0001_2022.pdf
    assert _by_tipo(result, "DECRETOS").total_files == 1
    assert _by_tipo(result, "Leyes").total_files == 1


def test_ignored_junk_file_inside_a_deeper_nested_folder_is_not_listed(tmp_path):
    _touch(tmp_path / "Gacetas" / "GC" / "1992" / "AC" / "AC_0001_1992.pdf")
    _touch(tmp_path / "Gacetas" / "GC" / "1992" / "AC" / "Thumbs.db")

    result = analyze_batch(tmp_path)

    assert len(result.extra_depth) == 1
    assert result.extra_depth[0].current_path == "Gacetas/GC/1992/AC/AC_0001_1992.pdf"
    assert result.total_files == 1


def test_entity_mismatch_detected_when_filename_disagrees_with_folder(tmp_path):
    _touch(tmp_path / "ACUERDOS" / "ARCHIVO" / "2003" / "A_AGN_0015_2003.pdf")

    result = analyze_batch(tmp_path)

    assert len(result.exceptions) == 1
    exc = result.exceptions[0]
    assert exc.tipo == "ACUERDOS"
    assert exc.kind == "entity_mismatch"
    assert exc.current_path == "ACUERDOS/ARCHIVO/2003/A_AGN_0015_2003.pdf"
    assert exc.detected_entity == "AGN"
    assert exc.detected_year == 2003
    assert exc.proposed_path == "ACUERDOS/AGN/2003/A_AGN_0015_2003.pdf"
    assert _by_tipo(result, "ACUERDOS").exception_count == 1
    assert result.total_files == 1


def test_no_entity_mismatch_when_filename_agrees_with_folder(tmp_path):
    _touch(tmp_path / "ACUERDOS" / "AGN" / "2003" / "A_AGN_0015_2003.pdf")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert _by_tipo(result, "ACUERDOS").total_files == 1
    assert _by_tipo(result, "ACUERDOS").exception_count == 0


def test_no_entity_mismatch_for_a_case_only_difference(tmp_path):
    # Reported real case: Documentos/INVIMA held files naming "invima"
    # (lowercase). Windows folder names are already case-insensitive — a
    # case-only difference is never a real mismatch, the folder is left as-is.
    _touch(tmp_path / "Documentos" / "INVIMA" / "2020" / "D_invima_0001_2020.pdf")
    _touch(tmp_path / "Documentos" / "INVIMA" / "2021" / "D_invima_0002_2021.pdf")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert result.folder_renames == []
    assert _by_tipo(result, "Documentos").total_files == 2
    assert _by_tipo(result, "Documentos").exception_count == 0


def test_no_entity_mismatch_when_filename_cant_be_parsed(tmp_path):
    _touch(tmp_path / "ACUERDOS" / "ARCHIVO" / "2003" / "documento-suelto.pdf")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert _by_tipo(result, "ACUERDOS").total_files == 1
    assert _by_tipo(result, "ACUERDOS").exception_count == 0


def test_folder_rename_suggested_when_all_files_agree_on_a_different_entity(tmp_path):
    _touch(tmp_path / "ACUERDOS" / "CMARAUCA" / "2016" / "A_CARAUCA_100_2016.pdf")
    _touch(tmp_path / "ACUERDOS" / "CMARAUCA" / "2017" / "A_CARAUCA_200_2017.pdf")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert len(result.folder_renames) == 1
    fr = result.folder_renames[0]
    assert fr.tipo == "ACUERDOS"
    assert fr.current_entity == "CMARAUCA"
    assert fr.suggested_entity == "CARAUCA"
    assert fr.current_path == "ACUERDOS/CMARAUCA"
    assert fr.proposed_path == "ACUERDOS/CARAUCA"
    assert fr.file_count == 2
    assert _by_tipo(result, "ACUERDOS").total_files == 2
    assert _by_tipo(result, "ACUERDOS").exception_count == 2


def test_folder_rename_ignores_joint_circulars_with_a_hyphenated_entity(tmp_path):
    # Reported real case: CIRCULAR/Min Minas y Energia has 49 files naming
    # "MME" plus 2 joint circulars co-issued with other ministries, encoded
    # as a hyphenated compound ("MME-MJD-MDEF"). The compound shouldn't
    # count as a vote against the 49-file consensus.
    _touch(tmp_path / "CIRCULAR" / "Min Minas y Energia" / "2005" / "C_MME_0025_2005.pdf")
    _touch(tmp_path / "CIRCULAR" / "Min Minas y Energia" / "2005" / "C_MME_0038_2005.pdf")
    _touch(tmp_path / "CIRCULAR" / "Min Minas y Energia" / "2025" / "C_MME-MJD-MDEF_40008_2025.pdf")
    _touch(tmp_path / "CIRCULAR" / "Min Minas y Energia" / "2025" / "C_MME-MTRA_40017_2025.pdf")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert len(result.folder_renames) == 1
    fr = result.folder_renames[0]
    assert fr.current_entity == "Min Minas y Energia"
    assert fr.suggested_entity == "MME"
    assert fr.file_count == 2
    assert _by_tipo(result, "CIRCULAR").total_files == 4


def test_folder_rename_suggested_when_a_clear_majority_disagrees_with_the_folder(tmp_path):
    # Reported real case: CONCEPTO/CCTCP has 318 files naming "CTCP" (plus
    # 18 more with a stray space typo, "CTCP" after stripping) against only
    # 65 naming "CCTCP" (plus 3 " CCTCP" typos) — a clear majority, not a
    # unanimous one. Confirmed by the user: CTCP is the correct entity.
    _touch(tmp_path / "CONCEPTO" / "CCTCP" / "2025" / "CTO_CTCP_0000185_2025.pdf")
    _touch(tmp_path / "CONCEPTO" / "CCTCP" / "2025" / "CTO_CTCP_0000223_2025.pdf")
    _touch(tmp_path / "CONCEPTO" / "CCTCP" / "2025" / "CTO_CTCP_0000437_2025.pdf")
    _touch(tmp_path / "CONCEPTO" / "CCTCP" / "2026" / "CTO_ CTCP_0000239_2026.pdf")
    _touch(tmp_path / "CONCEPTO" / "CCTCP" / "2025" / "CTO_CCTCP_0000060_2025.pdf")
    _touch(tmp_path / "CONCEPTO" / "CCTCP" / "2026" / "CTO_ CCTCP_0000011_2026.pdf")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert len(result.folder_renames) == 1
    fr = result.folder_renames[0]
    assert fr.current_entity == "CCTCP"
    assert fr.suggested_entity == "CTCP"
    assert fr.file_count == 4  # the 3 "CTCP" + 1 " CTCP" (typo, stripped)
    assert _by_tipo(result, "CONCEPTO").total_files == 6


def test_no_folder_rename_when_the_alternate_entity_is_not_a_clear_majority(tmp_path):
    # 2 files disagree with the folder, but 2 also agree with it — a tie,
    # not a majority. Stays as individual entity_mismatch review.
    _touch(tmp_path / "CONCEPTO" / "CCTCP" / "2025" / "CTO_CTCP_0000185_2025.pdf")
    _touch(tmp_path / "CONCEPTO" / "CCTCP" / "2025" / "CTO_CTCP_0000223_2025.pdf")
    _touch(tmp_path / "CONCEPTO" / "CCTCP" / "2025" / "CTO_CCTCP_0000060_2025.pdf")
    _touch(tmp_path / "CONCEPTO" / "CCTCP" / "2025" / "CTO_CCTCP_0000097_2025.pdf")

    result = analyze_batch(tmp_path)

    assert result.folder_renames == []
    assert len(result.exceptions) == 2
    assert all(e.kind == "entity_mismatch" and e.detected_entity == "CTCP" for e in result.exceptions)


def test_no_folder_rename_suggested_for_a_single_mismatched_file(tmp_path):
    _touch(tmp_path / "ACUERDOS" / "CMARAUCA" / "2016" / "A_CARAUCA_100_2016.pdf")

    result = analyze_batch(tmp_path)

    assert result.folder_renames == []
    assert len(result.exceptions) == 1
    assert result.exceptions[0].kind == "entity_mismatch"
    assert result.exceptions[0].proposed_path == "ACUERDOS/CARAUCA/2016/A_CARAUCA_100_2016.pdf"


def test_no_folder_rename_when_some_files_still_agree_with_the_folder(tmp_path):
    _touch(tmp_path / "ACUERDOS" / "CMARAUCA" / "2016" / "A_CARAUCA_100_2016.pdf")
    _touch(tmp_path / "ACUERDOS" / "CMARAUCA" / "2017" / "A_CMARAUCA_200_2017.pdf")

    result = analyze_batch(tmp_path)

    assert result.folder_renames == []
    assert len(result.exceptions) == 1
    assert result.exceptions[0].current_path == "ACUERDOS/CMARAUCA/2016/A_CARAUCA_100_2016.pdf"
    assert result.exceptions[0].kind == "entity_mismatch"


def test_no_folder_rename_when_files_disagree_with_each_other(tmp_path):
    _touch(tmp_path / "ACUERDOS" / "CMARAUCA" / "2016" / "A_CARAUCA_100_2016.pdf")
    _touch(tmp_path / "ACUERDOS" / "CMARAUCA" / "2017" / "A_OTRAENT_200_2017.pdf")

    result = analyze_batch(tmp_path)

    assert result.folder_renames == []
    assert len(result.exceptions) == 2
    assert {e.detected_entity for e in result.exceptions} == {"CARAUCA", "OTRAENT"}


def test_no_folder_rename_when_the_target_folder_already_exists(tmp_path):
    _touch(tmp_path / "ACUERDOS" / "CMARAUCA" / "2016" / "A_CARAUCA_100_2016.pdf")
    _touch(tmp_path / "ACUERDOS" / "CMARAUCA" / "2017" / "A_CARAUCA_200_2017.pdf")
    _touch(tmp_path / "ACUERDOS" / "CARAUCA" / "2019" / "A_CARAUCA_300_2019.pdf")

    result = analyze_batch(tmp_path)

    assert result.folder_renames == []
    assert len(result.exceptions) == 2
    assert all(e.kind == "entity_mismatch" for e in result.exceptions)


def test_folder_rename_wins_despite_several_one_off_stray_typos(tmp_path):
    # Reported real case: RESOLUCIONES/SDH had 883 files — 681 "SDHBOG",
    # 190 "SHACIENDABOG" (a confirmed alias, see the alias test below), and
    # a handful of one-file typos (SDHBO, SDHGOG, SHDBOG, SDPBOG). None of
    # those stray typos should be able to block the suggestion for the
    # dominant majority just by each being "yet another disagreeing value".
    _touch(tmp_path / "RESOLUCIONES" / "SDH" / "2020" / "R_SDHBOG_0001_2020.pdf")
    _touch(tmp_path / "RESOLUCIONES" / "SDH" / "2021" / "R_SDHBOG_0002_2021.pdf")
    _touch(tmp_path / "RESOLUCIONES" / "SDH" / "2022" / "R_SDHBOG_0003_2022.pdf")
    _touch(tmp_path / "RESOLUCIONES" / "SDH" / "2019" / "R_SDH_0004_2019.pdf")  # agrees with the folder
    _touch(tmp_path / "RESOLUCIONES" / "SDH" / "2018" / "R_SDHTYPO_0005_2018.pdf")  # one-off stray

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert len(result.folder_renames) == 1
    fr = result.folder_renames[0]
    assert fr.current_entity == "SDH"
    assert fr.suggested_entity == "SDHBOG"
    assert fr.file_count == 3


def test_shaciendabog_is_always_normalized_to_sdhbog(tmp_path):
    _touch(tmp_path / "RESOLUCIONES" / "SDH" / "2023" / "R_SHACIENDABOG_0001_2023.pdf")
    _touch(tmp_path / "RESOLUCIONES" / "SDH" / "2024" / "R_SHACIENDABOG_0002_2024.pdf")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert len(result.folder_renames) == 1
    fr = result.folder_renames[0]
    assert fr.suggested_entity == "SDHBOG"
    assert fr.file_count == 2


def test_men_filename_token_is_recognized_as_me_and_causes_no_exception(tmp_path):
    # Reported real case: CIRCULAR/ME/2025/C_MEN_0026_2025.pdf — "MEN" isn't
    # a real entity, it's an old abbreviation for "ME" (Ministerio de
    # Educación). The file already sits in the correct "ME" folder; without
    # the alias it would be wrongly flagged as an entity_mismatch proposing
    # a bogus "MEN" folder that doesn't exist anywhere in the real batch.
    _touch(tmp_path / "CIRCULAR" / "ME" / "2025" / "C_MEN_0026_2025.pdf")
    _touch(tmp_path / "CIRCULAR" / "ME" / "2025" / "C_MEN_0027_2025.pdf")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert result.folder_renames == []


def test_conbog_is_always_normalized_to_concbog_even_on_a_tied_vote(tmp_path):
    # Reported real case: ACUERDOS/CONBOG had exactly 4 files, split 2-2
    # between "CONBOG" (agreeing with the folder) and "CONCBOG" — an exact
    # tie the majority-vote rule can't break on its own. The user confirmed
    # "CONCBOG" is the correct name, so the alias forces every file (both
    # groups) to resolve to it, turning the tie into a unanimous rename.
    _touch(tmp_path / "ACUERDOS" / "CONBOG" / "1995" / "A_CONBOG_0024_1995.pdf")
    _touch(tmp_path / "ACUERDOS" / "CONBOG" / "2023" / "A_CONBOG_0897_2023.pdf")
    _touch(tmp_path / "ACUERDOS" / "CONBOG" / "2001" / "A_CONCBOG_0030_2001.pdf")
    _touch(tmp_path / "ACUERDOS" / "CONBOG" / "2008" / "A_CONCBOG_0341_2008.pdf")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert len(result.folder_renames) == 1
    fr = result.folder_renames[0]
    assert fr.current_entity == "CONBOG"
    assert fr.suggested_entity == "CONCBOG"
    assert fr.file_count == 4


def test_confirmed_single_file_folder_rename_bypasses_the_two_file_minimum(tmp_path):
    # Reported real cases: ACUERDOS/CODIRUMED, ACUERDOS/CRIOACHA and
    # ACUERDOS/MINAGRICULTURA each have exactly one file, so the normal
    # majority-vote rename (which needs >=2 matching files) can never fire
    # for them — they'd sit as per-file entity_mismatch forever, needing a
    # manual click every single analysis even though the user already
    # confirmed the correct name. _CONFIRMED_FOLDER_RENAMES bypasses that
    # minimum for these specific, individually-confirmed folders.
    _touch(tmp_path / "ACUERDOS" / "CODIRUMED" / "1987" / "A_CONDIRUDEMED_0985_1987.pdf")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert len(result.folder_renames) == 1
    fr = result.folder_renames[0]
    assert fr.current_entity == "CODIRUMED"
    assert fr.suggested_entity == "CONDIRUDEMED"
    assert fr.file_count == 1


def test_folder_rename_groups_case_variants_of_the_same_alternate_entity(tmp_path):
    _touch(tmp_path / "ACUERDOS" / "CMARAUCA" / "2016" / "A_CARAUCA_100_2016.pdf")
    _touch(tmp_path / "ACUERDOS" / "CMARAUCA" / "2017" / "A_carauca_200_2017.pdf")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert len(result.folder_renames) == 1
    fr = result.folder_renames[0]
    assert fr.suggested_entity == "CARAUCA"
    assert fr.file_count == 2


def test_no_folder_rename_when_the_target_folder_already_exists_in_a_different_case(tmp_path):
    _touch(tmp_path / "ACUERDOS" / "CMARAUCA" / "2016" / "A_CARAUCA_100_2016.pdf")
    _touch(tmp_path / "ACUERDOS" / "CMARAUCA" / "2017" / "A_CARAUCA_200_2017.pdf")
    _touch(tmp_path / "ACUERDOS" / "carauca" / "2019" / "A_CARAUCA_300_2019.pdf")

    result = analyze_batch(tmp_path)

    assert result.folder_renames == []
    assert len(result.exceptions) == 2
    assert all(e.kind == "entity_mismatch" for e in result.exceptions)


def test_year_mismatch_detected_when_filename_disagrees_with_folder(tmp_path):
    _touch(tmp_path / "ACUERDOS" / "MME" / "2014" / "A_MME_0031_2015.pdf")

    result = analyze_batch(tmp_path)

    assert len(result.exceptions) == 1
    exc = result.exceptions[0]
    assert exc.tipo == "ACUERDOS"
    assert exc.kind == "year_mismatch"
    assert exc.current_path == "ACUERDOS/MME/2014/A_MME_0031_2015.pdf"
    assert exc.detected_entity == "MME"
    assert exc.detected_year == 2015
    assert exc.proposed_path == "ACUERDOS/MME/2015/A_MME_0031_2015.pdf"
    assert _by_tipo(result, "ACUERDOS").exception_count == 1
    assert result.total_files == 1


def test_no_year_mismatch_when_filename_agrees_with_folder(tmp_path):
    _touch(tmp_path / "ACUERDOS" / "MME" / "2015" / "A_MME_0031_2015.pdf")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert _by_tipo(result, "ACUERDOS").total_files == 1
    assert _by_tipo(result, "ACUERDOS").exception_count == 0


def test_no_year_mismatch_when_filename_year_cant_be_parsed(tmp_path):
    _touch(tmp_path / "ACUERDOS" / "MME" / "2014" / "documento-suelto.pdf")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert _by_tipo(result, "ACUERDOS").total_files == 1
    assert _by_tipo(result, "ACUERDOS").exception_count == 0


def test_entity_mismatch_still_corrects_the_year_when_both_are_wrong(tmp_path):
    _touch(tmp_path / "ACUERDOS" / "ARCHIVO" / "2014" / "A_AGN_0015_2015.pdf")

    result = analyze_batch(tmp_path)

    assert len(result.exceptions) == 1
    exc = result.exceptions[0]
    assert exc.kind == "entity_mismatch"
    assert exc.detected_entity == "AGN"
    assert exc.detected_year == 2015
    assert exc.proposed_path == "ACUERDOS/AGN/2015/A_AGN_0015_2015.pdf"


def test_no_entity_mismatch_for_a_hyphenated_joint_entity_matching_the_folder(tmp_path):
    # Reported real case: CIRCULAR/ANCP/2023/C_ANCP-DAFP_0001_2023.pdf — a
    # circular jointly issued by ANCP and DAFP. It was proposing to move
    # the file into a brand-new "ANCP-DAFP" folder even though ANCP (one of
    # the two entities named) is exactly the folder it's already in.
    _touch(tmp_path / "CIRCULAR" / "ANCP" / "2023" / "C_ANCP-DAFP_0001_2023.pdf")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert result.folder_renames == []
    assert _by_tipo(result, "CIRCULAR").total_files == 1
    assert _by_tipo(result, "CIRCULAR").exception_count == 0


def test_no_entity_mismatch_for_a_hyphenated_joint_entity_matching_neither_part(tmp_path):
    # Same principle even when the current folder isn't one of the named
    # entities at all — a hyphenated value is never a single value to
    # compare against a folder, so it's left alone either way.
    _touch(tmp_path / "CIRCULAR" / "MIJ" / "2023" / "C_ANCP-DAFP_0001_2023.pdf")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert result.folder_renames == []


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


def test_no_entity_mismatch_for_the_shorter_codigo_numero_ano_naming_convention(tmp_path):
    # Gacetas' own naming convention is CODIGO_NUMERO_AÑO (3 parts, no
    # entity segment) — not the general TIPOCODE_ENTIDAD_NUMERO_AÑO (4
    # parts). "0114" here is the gaceta's own number, not an entity code.
    _touch(tmp_path / "Gacetas" / "GC" / "1992" / "GC_0114_1992.pdf")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert _by_tipo(result, "Gacetas").total_files == 1
    assert _by_tipo(result, "Gacetas").exception_count == 0


def test_detected_entity_rejects_a_purely_numeric_second_token(tmp_path):
    _touch(tmp_path / "DECRETOS" / "PGN" / "2019" / "D_PGN_0001_2019.pdf")
    _touch(tmp_path / "DECRETOS" / "2022" / "D_0114_2022.pdf")
    (tmp_path / "DECRETOS" / "OTRO").mkdir(parents=True, exist_ok=True)

    result = analyze_batch(tmp_path)

    exc = next(e for e in result.exceptions if e.current_path.endswith("D_0114_2022.pdf"))
    assert exc.detected_entity is None
    assert exc.proposed_path is None


def test_no_entity_mismatch_when_a_missing_underscore_merges_entity_with_the_next_field(tmp_path):
    # Reported real case: CONCEPTO/SDHBOG/2015/CTO_SDHBOG2015IE18890_2015.pdf
    # — meant to be "CTO_SDHBOG_2015IE18890_2015.pdf" but a missing
    # underscore merged the entity with the document identifier. The
    # resulting "SDHBOG2015IE18890" isn't a real entity (no real entity
    # code anywhere in the batch has ever contained a digit) — it must not
    # propose creating a garbage folder for it.
    _touch(tmp_path / "CONCEPTO" / "SDHBOG" / "2015" / "CTO_SDHBOG2015IE18890_2015.pdf")
    _touch(tmp_path / "CONCEPTO" / "SDHBOG" / "2018" / "CTO_SDHBOG2_0010_2018.pdf")

    result = analyze_batch(tmp_path)

    assert result.exceptions == []
    assert result.folder_renames == []
    assert _by_tipo(result, "CONCEPTO").total_files == 2


def test_detected_entity_strips_a_stray_space_typo(tmp_path):
    _touch(tmp_path / "DECRETOS" / "PGN" / "2019" / "D_PGN_0001_2019.pdf")
    _touch(tmp_path / "DECRETOS" / "2022" / "D_ PGN_0002_2022.pdf")
    (tmp_path / "DECRETOS" / "OTRO").mkdir(parents=True, exist_ok=True)

    result = analyze_batch(tmp_path)

    exc = next(e for e in result.exceptions if e.current_path.endswith("D_ PGN_0002_2022.pdf"))
    assert exc.detected_entity == "PGN"
    assert exc.proposed_path == "DECRETOS/PGN/2022/D_ PGN_0002_2022.pdf"


def test_apply_folder_renames_moves_the_whole_directory(tmp_path):
    _touch(tmp_path / "ACUERDOS" / "CMARAUCA" / "2016" / "A_CARAUCA_100_2016.pdf", content="uno")
    _touch(tmp_path / "ACUERDOS" / "CMARAUCA" / "2017" / "A_CARAUCA_200_2017.pdf", content="dos")

    results = apply_folder_renames(
        tmp_path, [ResolvedFolderRename(current_path="ACUERDOS/CMARAUCA", target_path="ACUERDOS/CARAUCA")]
    )

    assert results[0].renamed is True
    assert results[0].skip_reason is None
    assert not (tmp_path / "ACUERDOS" / "CMARAUCA").exists()
    assert (tmp_path / "ACUERDOS" / "CARAUCA" / "2016" / "A_CARAUCA_100_2016.pdf").read_text() == "uno"
    assert (tmp_path / "ACUERDOS" / "CARAUCA" / "2017" / "A_CARAUCA_200_2017.pdf").read_text() == "dos"


def test_apply_folder_renames_skips_when_the_target_already_exists(tmp_path):
    _touch(tmp_path / "ACUERDOS" / "CMARAUCA" / "2016" / "A_CARAUCA_100_2016.pdf", content="nuevo")
    _touch(tmp_path / "ACUERDOS" / "CARAUCA" / "2019" / "A_CARAUCA_300_2019.pdf", content="ya-existia")

    results = apply_folder_renames(
        tmp_path, [ResolvedFolderRename(current_path="ACUERDOS/CMARAUCA", target_path="ACUERDOS/CARAUCA")]
    )

    assert results[0].renamed is False
    assert results[0].skip_reason is not None
    assert (tmp_path / "ACUERDOS" / "CMARAUCA").exists()
    assert (tmp_path / "ACUERDOS" / "CARAUCA" / "2019" / "A_CARAUCA_300_2019.pdf").read_text() == "ya-existia"


def test_apply_folder_renames_skips_when_the_source_no_longer_exists(tmp_path):
    (tmp_path / "ACUERDOS").mkdir(parents=True, exist_ok=True)

    results = apply_folder_renames(
        tmp_path, [ResolvedFolderRename(current_path="ACUERDOS/NO-EXISTE", target_path="ACUERDOS/CARAUCA")]
    )

    assert results[0].renamed is False
    assert results[0].skip_reason is not None


def test_apply_folder_renames_skips_a_target_outside_the_root(tmp_path):
    _touch(tmp_path / "ACUERDOS" / "CMARAUCA" / "2016" / "A_CARAUCA_100_2016.pdf")

    results = apply_folder_renames(
        tmp_path, [ResolvedFolderRename(current_path="ACUERDOS/CMARAUCA", target_path="../outside")]
    )

    assert results[0].renamed is False
    assert results[0].skip_reason is not None
    assert (tmp_path / "ACUERDOS" / "CMARAUCA").exists()
    assert not (tmp_path.parent / "outside").exists()
