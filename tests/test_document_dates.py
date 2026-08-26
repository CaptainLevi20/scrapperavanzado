from pathlib import Path

import docx

from core.document_dates import extract_confirmed_year


def _make_docx(path: Path, paragraphs: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = docx.Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    doc.save(str(path))


def _make_rtf(path: Path, text: str) -> None:
    # Minimal valid RTF wrapper. Encode accented characters as \'XX cp1252
    # hex escapes, matching how real Word-exported RTF represents them —
    # this is exactly the encoding extract_confirmed_year has to decode.
    escaped = "".join(
        f"\\'{b:02x}" if b > 127 else chr(b) for b in text.encode("cp1252")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("{\\rtf1\\ansi\\deff0 " + escaped + "}").encode("cp1252", errors="ignore"))


def test_extracts_from_gaceta_oficial_line_near_the_top(tmp_path):
    f = tmp_path / "RSG2473.docx"
    _make_docx(
        f,
        [
            "RESOLUCIÓN 2473",
            "Gaceta Oficial No 5624, Lima, 18 de febrero de 2025",
            "Adopción del Permiso Fitosanitario...",
        ],
    )
    assert extract_confirmed_year(f) == 2025


def test_extracts_from_word_only_closing_signature_block(tmp_path):
    f = tmp_path / "RSG2058.docx"
    _make_docx(
        f,
        [
            "RESOLUCIÓN N° 2058",
            "Precios de Referencia del Sistema Andino de Franjas de Precios",
            "LA SECRETARÍA GENERAL DE LA COMUNIDAD ANDINA,",
            "VISTOS: El artículo 29 del Acuerdo de Cartagena...",
            "Dada en la ciudad de Lima, Perú, a los veintitrés días del mes de abril del año dos mil diecinueve.",
            "Jorge Hernando Pedraza",
            "Secretario General",
        ],
    )
    assert extract_confirmed_year(f) == 2019


def test_accepts_the_spaced_veinte_y_dos_form_as_well_as_veintidos(tmp_path):
    f = tmp_path / "RSG2280.docx"
    _make_docx(
        f,
        [
            "RESOLUCIÓN N° 2280",
            "Inadmite el Reclamo interpuesto por...",
            "Dada en la ciudad de Lima, Perú, a los ocho días del mes de agosto del año dos mil veinte y dos.",
        ],
    )
    assert extract_confirmed_year(f) == 2022


def test_returns_none_when_top_date_and_signature_disagree(tmp_path):
    # Real case: a Gaceta Oficial bulletin bundling several Decisiones
    # stated 2025 in its own masthead, but one Decisión's own closing
    # signature (elsewhere in the same PDF) read as 2026 — never guess
    # which one is right, leave it for manual review instead.
    f = tmp_path / "DEC-bundle.docx"
    _make_docx(
        f,
        [
            "GACETA OFICIAL",
            "LIMA, 24 DE JUNIO DE 2025",
            "DECISIÓN N° 943",
            "Dada en la ciudad de Lima, a los veinticuatro días del mes de junio del año dos mil veintiséis.",
        ],
    )
    assert extract_confirmed_year(f) is None


def test_ignores_an_unrelated_del_ano_phrase_in_the_body_before_the_signature(tmp_path):
    # A citation or unrelated phrase earlier in the document body
    # ("dentro del año en curso") must not be picked up instead of the
    # real closing-signature date — the search has to anchor on "Dada en
    # la ciudad de" first, not just find any "del año ..." anywhere.
    f = tmp_path / "RSG-citation.docx"
    _make_docx(
        f,
        [
            "RESOLUCIÓN N° 2264",
            "CONSIDERANDO: dentro del año en curso se han presentado varias solicitudes...",
            "Dada en la ciudad de Lima, Perú, a los nueve días del mes de mayo del año dos mil veintidós.",
        ],
    )
    assert extract_confirmed_year(f) == 2022


def test_returns_none_when_no_date_pattern_is_present(tmp_path):
    f = tmp_path / "RSG-nodate.docx"
    _make_docx(f, ["RESOLUCIÓN N° 9999", "Texto sin ninguna fecha reconocible."])
    assert extract_confirmed_year(f) is None


def test_extracts_from_rtf_with_hex_escaped_accented_characters(tmp_path):
    f = tmp_path / "RSG2265.rtf"
    _make_rtf(
        f,
        "RESOLUCIÓN N° 2265\n"
        "Gaceta Oficial No 5013 de 8 de agosto de 2022\n"
        "LA SECRETARÍA GENERAL DE LA COMUNIDAD ANDINA,",
    )
    assert extract_confirmed_year(f) == 2022


def test_legacy_doc_format_is_left_unconfirmed(tmp_path):
    # No library available for the pre-2007 binary .doc format — this
    # should never crash, just fall through to "can't determine".
    f = tmp_path / "RSG0495.doc"
    f.write_bytes(b"\xd0\xcf\x11\xe0not a real doc file")
    assert extract_confirmed_year(f) is None


def test_corrupt_docx_is_left_unconfirmed_not_raised(tmp_path):
    f = tmp_path / "corrupt.docx"
    f.write_bytes(b"this is not a real zip/docx file")
    assert extract_confirmed_year(f) is None
