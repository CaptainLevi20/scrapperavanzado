from core.models import RawDocModel
from core.utils import compute_doc_id, extract_filename, make_doc_id, storage_path


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


def test_storage_path_joins_with_forward_slashes():
    assert storage_path("Corte Constitucional", "2026-01-01", "Sentencia", "T-1.rtf") == (
        "Corte Constitucional/2026-01-01/Sentencia/T-1.rtf"
    )


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
