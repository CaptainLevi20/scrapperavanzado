from core.models import RawDocModel
from core.utils import compute_doc_id, extract_filename, is_safe_storage_key, make_doc_id, rekey_filename, storage_path


def test_make_doc_id_is_deterministic():
    assert make_doc_id("foo", "2026-01-01") == make_doc_id("foo", "2026-01-01")
    assert make_doc_id("foo", "2026-01-01") != make_doc_id("bar", "2026-01-01")


def test_compute_doc_id_prefers_body_path_over_url():
    doc = RawDocModel(
        source="s", link={"url": "https://x/1", "method": "GET", "body": {"path": "radicado-1"}},
        title="t", tipo="Auto", f_public="2026-01-01",
    )
    assert compute_doc_id(doc) == make_doc_id("radicado-1", "2026-01-01")


def test_compute_doc_id_falls_back_to_url_without_body_path():
    doc = RawDocModel(
        source="s", link={"url": "https://x/1", "method": "GET"},
        title="t", tipo="Auto", f_public="2026-01-01",
    )
    assert compute_doc_id(doc) == make_doc_id("https://x/1", "2026-01-01")


def test_compute_doc_id_ignores_publication_date_when_told_to():
    # Rama Judicial: the same underlying file can be re-listed under a new
    # f_public (the site republishes an unclaimed "estado" the next day). The
    # doc_id must stay identical across that date change so the
    # republication-detection check in worker/tasks.py actually fires.
    doc_day_one = RawDocModel(
        source="s", link={"url": "https://x/1", "method": "GET", "body": {"path": "same-uuid"}},
        title="t", tipo="Auto", f_public="2026-06-10",
    )
    doc_day_two = RawDocModel(
        source="s", link={"url": "https://x/1", "method": "GET", "body": {"path": "same-uuid"}},
        title="t", tipo="Auto", f_public="2026-06-11",
    )

    assert compute_doc_id(doc_day_one, include_publication_date=False) == compute_doc_id(
        doc_day_two, include_publication_date=False
    )


def test_compute_doc_id_still_varies_by_publication_date_by_default():
    doc_day_one = RawDocModel(
        source="s", link={"url": "https://x/1", "method": "GET", "body": {"path": "same-uuid"}},
        title="t", tipo="Auto", f_public="2026-06-10",
    )
    doc_day_two = RawDocModel(
        source="s", link={"url": "https://x/1", "method": "GET", "body": {"path": "same-uuid"}},
        title="t", tipo="Auto", f_public="2026-06-11",
    )

    assert compute_doc_id(doc_day_one) != compute_doc_id(doc_day_two)


def test_extract_filename_from_content_disposition():
    result = extract_filename('attachment; filename="doc.pdf"', "", "https://x/y", "fallback")
    assert result == {"filename": "doc", "extension": ".pdf"}


def test_extract_filename_falls_back_to_content_type_and_url():
    result = extract_filename("", "application/pdf", "https://x/carpeta/archivo", "fallback")
    assert result == {"filename": "archivo", "extension": ".pdf"}


def test_extract_filename_keeps_the_discriminating_middle_part_of_a_multi_dot_name():
    """Regression test: the stem used to be taken up to the FIRST dot
    (split(".")[0]) while the extension was taken from the LAST dot
    (split(".")[-1]) — two incompatible criteria. "Sentencia.T-123.2024.pdf"
    used to lose everything after the first dot, becoming just "Sentencia" —
    the part that actually distinguishes it from other documents. Two
    documents with different middle parts but the same prefix would then
    collapse onto the same storage key and silently overwrite each other."""
    result = extract_filename('attachment; filename="Sentencia.T-123.2024.pdf"', "", "https://x/y", "fallback")
    assert result == {"filename": "Sentencia.T-123.2024", "extension": ".pdf"}


def test_extract_filename_strips_path_separators_from_a_malicious_content_disposition():
    """Regression test: the remote server controls this header entirely — a
    filename containing '/' used to survive untouched and land directly in the
    storage key, letting a malicious/misconfigured site put a document in an
    unexpected subfolder (or, combined with a template like
    "(filename)(extension)", escape the intended storage root). A resulting
    name may still legitimately CONTAIN ".." as a substring (e.g.
    "-..-etc-passwd") — that's just an odd filename, not a traversal risk, once
    every "/" is gone and it's used as a single path segment (see
    is_safe_storage_key, which is the actual traversal check)."""
    result = extract_filename('attachment; filename="../../etc/passwd.pdf"', "", "https://x/y", "fallback")
    assert "/" not in result["filename"]
    assert "\\" not in result["filename"]
    assert result["filename"] not in ("..", ".")
    assert result["extension"] == ".pdf"


def test_extract_filename_strips_backslashes_and_control_characters():
    result = extract_filename('attachment; filename="a\\b\x01c.pdf"', "", "https://x/y", "fallback")
    assert "\\" not in result["filename"]
    assert "\x01" not in result["filename"]


def test_extract_filename_falls_back_to_a_generic_name_when_sanitizing_leaves_nothing():
    # The stem (everything before the LAST dot) is made entirely of dots, with
    # no other character — collapses to nothing once sanitized, so it must
    # fall back rather than produce an empty storage key segment.
    result = extract_filename('attachment; filename="...pdf"', "", "https://x/y", "fallback")
    assert result["filename"] == "documento"
    assert result["extension"] == ".pdf"


def test_extract_filename_sanitizes_a_malicious_extension_too():
    # The extension is just whatever comes after the LAST dot in the header's
    # filename — also attacker-controlled, also used to build the storage key.
    result = extract_filename('attachment; filename="doc.pdf/../evil"', "", "https://x/y", "fallback")
    assert "/" not in result["extension"]


def test_is_safe_storage_key_accepts_a_normal_multi_segment_key():
    assert is_safe_storage_key("Corte Constitucional/2026-06-01/Auto/A.829-26.rtf") is True


def test_is_safe_storage_key_rejects_traversal_and_absolute_paths():
    assert is_safe_storage_key("../../etc/passwd") is False
    assert is_safe_storage_key("a/../../b") is False
    assert is_safe_storage_key("/etc/passwd") is False
    assert is_safe_storage_key("") is False


def test_storage_path_joins_with_forward_slashes():
    assert storage_path("Corte Constitucional", "2026-01-01", "Sentencia", "T-1.rtf") == (
        "Corte Constitucional/2026-01-01/Sentencia/T-1.rtf"
    )


def test_rekey_filename_replaces_only_the_filename_segment():
    # CSJ-style key: bucket directory unaffected by title, real extension kept.
    assert rekey_filename("CSJ/SCT/CSJ_SCT_doc_2026.pdf", "CSJ_SCT_ABC1234_2026") == (
        "CSJ/SCT/CSJ_SCT_ABC1234_2026.pdf"
    )


def test_rekey_filename_sanitizes_invalid_characters_in_the_new_title():
    # SAMAI-style title complemented with a parenthesized extra number after
    # download — invalid filesystem characters in the corrected title must not
    # leak into the storage key.
    assert rekey_filename("SAMAI/2026-01-01/Auto/11001-radicado.pdf", "11001-radicado(74.604)CE") == (
        "SAMAI/2026-01-01/Auto/11001-radicado(74.604)CE.pdf"
    )
    rekeyed = rekey_filename("Dummy/2026-01-01/doc.pdf", 'bad:"title"<>')
    directory, _, new_filename = rekeyed.rpartition("/")
    assert directory == "Dummy/2026-01-01"
    assert new_filename.endswith(".pdf")
    assert not any(c in new_filename for c in ':"<>')


def test_rekey_filename_falls_back_to_old_stem_when_title_sanitizes_to_nothing():
    assert rekey_filename("Dummy/2026-01-01/doc.pdf", "   ") == "Dummy/2026-01-01/doc.pdf"


from core.utils import is_radicado_title


def test_is_radicado_title_matches_a_real_formatted_radicado():
    # Real example from Tribunal Superior de Bogotá (código "BTA", 3 letters).
    assert is_radicado_title("T_BTA_11001_31_03_048_2022_00418_02") is True


def test_is_radicado_title_matches_a_four_letter_tribunal_code():
    # Real example from Tribunal Superior de Antioquia (código "ANTI", 4 letters).
    assert is_radicado_title("T_ANTI_05001_31_10_006_2022_00505_03") is True


def test_is_radicado_title_rejects_a_magistrado_name_fallback():
    """When the scraper can't parse a radicado out of the filename, it falls back
    to other text (e.g. a magistrado's name) — this can legitimately repeat across
    unrelated documents and must never be treated as the same case."""
    assert is_radicado_title("DR. WILLIAM SANTA MARIN") is False


def test_is_radicado_title_rejects_an_empty_string():
    assert is_radicado_title("") is False


def test_is_radicado_title_rejects_a_title_missing_a_segment():
    # Missing the final 2-digit segment.
    assert is_radicado_title("T_BTA_11001_31_03_048_2022_00418") is False


from core.utils import is_samai_case_title


def test_is_samai_case_title_matches_a_real_formatted_title():
    assert is_samai_case_title("11001-03-28-000-2026-00271-00(NE)") is True


def test_is_samai_case_title_matches_a_multi_letter_acronym():
    assert is_samai_case_title("11001-03-24-000-2022-00373-00(NSP)") is True


def test_is_samai_case_title_rejects_a_bare_radicado_without_acronym():
    # No known clase matched — _normalizar_titulo leaves it as the bare radicado
    # (see core/scrapers/families/samai.py), which must not be grouped as a case.
    assert is_samai_case_title("11001-03-24-000-2022-00373-00") is False


def test_is_samai_case_title_rejects_an_empty_string():
    assert is_samai_case_title("") is False


def test_is_samai_case_title_matches_a_complemented_title_with_acronimo():
    # core/scrapers/families/samai.py::_complementar_titulo_con_numero inserts
    # the extra number between the radicado and the acronimo — the resulting
    # title still identifies the same case and must still be grouped.
    assert is_samai_case_title("25000-23-37-000-2021-00423-01(30146)(NRD)") is True


def test_is_samai_case_title_rejects_a_bare_radicado_complemented_with_only_a_number():
    # No acronimo matched (_normalizar_titulo left the title as a bare
    # radicado) but the title still picked up the extra number, so it becomes
    # "{radicado}({numero})" — a lone all-digit parenthetical group must NOT be
    # mistaken for a real acronimo (which always starts with an uppercase
    # letter — see _CLASE_ACRONIMOS in core/scrapers/families/samai.py).
    assert is_samai_case_title("11001-03-24-000-2026-99999-00(30146)") is False


def test_is_samai_case_title_matches_a_complemented_title_with_numero_ano_format():
    # Confirmado con datos reales: el número extra no siempre es solo
    # dígitos — también aparece como "3104-2023" (número-año).
    assert is_samai_case_title("66001-23-33-000-2017-00141-01(3104-2023)(NRD)") is True


def test_is_samai_case_title_matches_a_complemented_title_with_dotted_digits():
    # Confirmado con datos reales: también aparece con punto de miles, ej. "(74.604)".
    assert is_samai_case_title("11001-03-15-000-2025-04868-00(74.604)(RER)") is True
