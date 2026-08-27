"""Extract a confirmed year from a document's own content.

Some Tipos (CAN "Decisiones", SGCANDINA "Resoluciones") have hundreds of
files whose filename encodes no year at all (e.g. "RSG2367.docx") — only
the sequential instrument number. The filesystem's mtime is not
authoritative (files freshly added to the archive get today's mtime
regardless of when the real document was issued — confirmed on real data:
RSG1475.docx carries a 2024 mtime for a resolution actually issued in
2012). These official instruments do reliably print their own real date
inside the document itself, in one of two places:
  - near the top: "Gaceta Oficial No <n>[, Lima,] <día> de <mes> de <año>"
    (SGCANDINA), or a masthead line "LIMA, <día> de <mes> de <año>" (CAN
    gazette bulletins bundling several Decisiones in one PDF).
  - the closing signature block: "Dada en la ciudad de Lima, ... a los
    <día> días del mes de <mes> del año <año>" — day and month as digits
    or words, year always spelled out in words.
Extracting from both and requiring them to agree (when both are present)
is what makes this safe to trust as much as a year read from the filename
itself — never guess a single, ambiguous source.
"""

import re
import unicodedata
from pathlib import Path
from typing import Optional

from core.fecha_es import parse_fecha_providencia_es

_UNITS = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"]
_TEENS = {
    10: "diez", 11: "once", 12: "doce", 13: "trece", 14: "catorce", 15: "quince",
    16: "dieciseis", 17: "diecisiete", 18: "dieciocho", 19: "diecinueve",
}
_TWENTIES = {
    20: "veinte", 21: "veintiuno", 22: "veintidos", 23: "veintitres", 24: "veinticuatro",
    25: "veinticinco", 26: "veintiseis", 27: "veintisiete", 28: "veintiocho", 29: "veintinueve",
}
_TENS = {30: "treinta", 40: "cuarenta", 50: "cincuenta", 60: "sesenta", 70: "setenta", 80: "ochenta", 90: "noventa"}


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _word_0_99(n: int) -> str:
    if n == 0:
        return ""
    if n < 10:
        return _UNITS[n]
    if n in _TEENS:
        return _TEENS[n]
    if n in _TWENTIES:
        return _TWENTIES[n]
    base = (n // 10) * 10
    if n % 10 == 0:
        return _TENS[base]
    return f"{_TENS[base]} y {_UNITS[n % 10]}"


def _word_for_year(year: int) -> Optional[str]:
    if 2000 <= year < 2040:
        rem = year - 2000
        return ("dos mil " + _word_0_99(rem)).strip()
    if 1900 <= year < 2000:
        rem = year - 1900
        return ("mil novecientos " + _word_0_99(rem)).strip()
    return None


def _build_year_words() -> dict[str, int]:
    words = {_word_for_year(y): y for y in range(1990, 2036)}
    # Some documents spell 21-29 as three words ("veinte y dos") instead of
    # the single compound ("veintidós") — both are valid Spanish.
    for y in range(2021, 2030):
        spaced = _word_for_year(y).replace("veinti", "veinte y ", 1)
        words.setdefault(spaced, y)
    return words


_YEAR_WORDS = _build_year_words()
_YEAR_WORD_ALTERNATION = "|".join(re.escape(k) for k in sorted(_YEAR_WORDS, key=len, reverse=True))

# A digit-based date near the top of the document — the Gaceta Oficial
# publication line for a single resolution, or the gazette bulletin's own
# masthead date for a multi-Decisión PDF. Reuses the same digit-date parser
# already trusted for judicial rulings (core/fecha_es.py); bounded to a
# window near the top rather than searched over the whole document, since
# an unbounded search would happily match a citation to some OTHER,
# unrelated instrument's date further down in the "VISTOS" section.
_TOP_DATE_WINDOW = 500

# The closing signature block. Anchored on "Dada/Dado en la ciudad de" first
# so the year search only looks within a small window right after it —
# otherwise an unrelated "... del año ..." phrase earlier in a long
# document's body (e.g. "dentro del año en curso") gets matched instead.
_SIGNATURE_ANCHOR_RE = re.compile(r"da(?:da|do)\s+en\s+la\s+ciudad\s+de")
_SIGNATURE_YEAR_RE = re.compile(rf"del\s+a[nñ]o\s+({_YEAR_WORD_ALTERNATION})\b")
_SIGNATURE_WINDOW = 300


def _rtf_hex_byte(match: re.Match) -> bytes:
    return bytes([int(match.group(1), 16)]).decode("cp1252", errors="replace").encode("utf-8")


def _extract_text(path: Path) -> Optional[str]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".docx":
            from docx import Document as DocxDocument

            doc = DocxDocument(str(path))
            return "\n".join(p.text for p in doc.paragraphs)
        if suffix == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        if suffix == ".rtf":
            raw = path.read_bytes()
            # \'XX hex-escapes (cp1252) must be decoded to the real
            # character BEFORE stripping control words, or accented
            # letters (á, é, ñ...) collapse to nothing and break the
            # Spanish word matching below.
            text_bytes = re.sub(rb"\\'([0-9a-fA-F]{2})", _rtf_hex_byte, raw)
            text = text_bytes.decode("utf-8", errors="ignore")
            text = re.sub(r"\\par[d]?\b", "\n", text)
            text = re.sub(r"\\[a-zA-Z]+-?[0-9]* ?", " ", text)
            text = re.sub(r"[{}\\]", " ", text)
            return text
    except Exception:
        # Corrupt file, unsupported internal structure, etc. — never a
        # value worth guessing from, same principle as everywhere else in
        # this tool: fall through to "can't determine".
        return None
    # Legacy ".doc" (pre-2007 binary format) has no library available here
    # — left unconfirmed rather than adding a new dependency for it.
    return None


def extract_confirmed_year(path: Path) -> Optional[int]:
    """The document's own real year, only when found unambiguously.

    Returns None whenever there's nothing to read, no date pattern found,
    or the two independent signals (top-of-document date, closing
    signature block) disagree — never a guess.
    """
    text = _extract_text(path)
    if not text:
        return None
    normalized = _strip_accents(text.lower())
    normalized = re.sub(r"\s+", " ", normalized)

    top_date = parse_fecha_providencia_es(normalized[:_TOP_DATE_WINDOW])
    top_year = top_date.year if top_date else None

    signature_year = None
    anchor = _SIGNATURE_ANCHOR_RE.search(normalized)
    if anchor:
        window = normalized[anchor.end():anchor.end() + _SIGNATURE_WINDOW]
        sig_match = _SIGNATURE_YEAR_RE.search(window)
        if sig_match:
            signature_year = _YEAR_WORDS.get(sig_match.group(1))

    if top_year and signature_year:
        return top_year if top_year == signature_year else None
    return top_year or signature_year
