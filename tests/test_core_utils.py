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
