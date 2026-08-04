import hashlib
import re
from pathlib import PurePosixPath

from core.models import RawDocModel

_INVALID_FILENAME_CHARS = re.compile(r'[\\/*?:"<>|\x00-\x1f]')

# Espejo del formato que produce core/scrapers/families/rama_judicial.py::_normalize_title
# (T_{CODIGO}_{radicado segmentado en 23 dígitos}). Desde jul. 2026 también es el formato
# que usa core/scrapers/families/samai.py::_normalizar_titulo para los Tribunales
# Administrativos (todo corp de SAMAI salvo Consejo de Estado, que sigue con
# SAMAI_CASE_TITLE_PATTERN) — deliberadamente igual al de Tribunales Superiores, no al de
# Consejo de Estado. No importa TRIBUNAL_CODES desde el módulo del scraper para no acoplar
# esta capa a uno de familia específico — el rango de 2-5 letras mayúsculas cubre los
# códigos reales (3-4 letras) con margen.
RADICADO_TITLE_PATTERN = re.compile(r"^T_[A-Z]{2,5}_\d{5}_\d{2}_\d{2}_\d{3}_\d{4}_\d{5}_\d{2}$")


def is_radicado_title(title: str) -> bool:
    return bool(RADICADO_TITLE_PATTERN.match(title))


# Espejo del formato que produce core/scrapers/families/samai.py::_normalizar_titulo
# ({radicado}({ACRÓNIMO})) — pero solo para Consejo de Estado; los demás corps de SAMAI
# (Tribunales Administrativos) usan RADICADO_TITLE_PATTERN en su lugar (ver ese
# comentario). El radicado (número del caso, no de una actuación puntual) es lo que se
# repite entre las distintas actuaciones de un mismo caso — igual que el título de
# rama_judicial, así que el mismo mecanismo de agrupar "N actuaciones" por título exacto
# aplica aquí también.
#
# _complementar_titulo_con_numero (mismo módulo de samai.py) puede insertar un número
# extra entre el radicado y el acrónimo — "{radicado}({número})({ACRÓNIMO})" — así que
# ese grupo numérico es opcional aquí. El número no siempre es solo dígitos (datos
# reales confirmaron también "3104-2023" y "74.604"), así que el grupo acepta
# cualquier contenido corto entre paréntesis. El grupo del acrónimo, en cambio, es
# obligatorio y debe empezar con una letra mayúscula (ver _CLASE_ACRONIMOS en
# samai.py: todas las siglas reales empiezan con letra, algunas con dígitos al final
# como "PI1"/"PI2") — nunca puramente numérico, porque un documento sin clase
# conocida y CON el número extra produce un título "{radicado}({número})" (ver
# _normalizar_titulo + Finding 2 del review) que de otro modo sería indistinguible
# de un caso real.
SAMAI_CASE_TITLE_PATTERN = re.compile(
    r"^\d{5}-\d{2}-\d{2}-\d{3}-\d{4}-\d{5}-\d{2}(?:\([^)]{1,30}\))?\([A-Z][A-Z0-9]*\)$"
)


def is_samai_case_title(title: str) -> bool:
    return bool(SAMAI_CASE_TITLE_PATTERN.match(title))


def make_doc_id(key: str, f_public: str) -> str:
    return hashlib.sha1(f"{key}_{f_public}".encode()).hexdigest()


def compute_doc_id(doc: RawDocModel, include_publication_date: bool = True) -> str:
    body = doc.link.get("body") or {}
    key = body["path"] if "path" in body else doc.link["url"]
    if not include_publication_date:
        return hashlib.sha1(key.encode()).hexdigest()
    return make_doc_id(key, doc.f_public)


def _sanitize_filename_segment(name: str, fallback: str = "") -> str:
    """Collapses a value to a single safe path segment before it's used to build
    a storage key. The filename in this function's callers always comes from a
    remote server we don't control (an HTTP header, or the URL/page title it
    served) — without this, a crafted or just unusually-formatted filename
    could inject `/` or `\\` and land the document in an unexpected subfolder,
    or start with `..` and escape the storage root entirely. Strips path
    separators and control characters, and any leading/trailing dots or
    whitespace (so a lone "." or ".." segment, or a Windows-invalid trailing
    dot, collapses to nothing and falls back instead of surviving as-is)."""
    cleaned = _INVALID_FILENAME_CHARS.sub("-", name).strip(" .")
    return cleaned or fallback


def extract_filename(disposition: str, content_type: str, url: str, opt_title: str) -> dict:
    if disposition:
        match = re.search(r'filename="?([^"]+)"?', disposition)
        if match:
            filename = match.group(1)
            # rpartition (not split(".")[0]/[-1], which used different dots for
            # the stem vs. the extension) — a filename like
            # "Sentencia.T-123.2024.pdf" must keep "Sentencia.T-123.2024" as the
            # stem and only ".pdf" as the extension, or two documents with
            # different discriminating middle parts collapse onto the same
            # storage key and silently overwrite each other in storage.
            if "." in filename:
                stem_raw, _, raw_ext = filename.rpartition(".")
            else:
                stem_raw, raw_ext = filename, ""
            sanitized_ext = _sanitize_filename_segment(raw_ext) if raw_ext else ""
            ext = f".{sanitized_ext}" if sanitized_ext else ""
            stem = _sanitize_filename_segment(stem_raw, fallback="documento")
            return {"filename": stem, "extension": ext}

    if "rtf" in content_type.lower():
        ext = ".rtf"
    elif "pdf" in content_type.lower():
        ext = ".pdf"
    elif "word" in content_type.lower() or "officedocument" in content_type.lower():
        ext = ".docx"
    else:
        ext = ""

    url_path = url.split("?")[0]
    name = url_path.split("/")[-1] or opt_title
    if "." in name:
        base, _, url_ext = name.rpartition(".")
        name = base
        if not ext:
            sanitized_ext = _sanitize_filename_segment(url_ext) if url_ext else ""
            ext = f".{sanitized_ext}" if sanitized_ext else ""
    return {"filename": _sanitize_filename_segment(name, fallback="documento"), "extension": ext}


def storage_path(*parts) -> str:
    return "/".join(str(p) for p in parts)


def rekey_filename(storage_key: str, title: str) -> str:
    """Rebuilds a storage key's filename segment from `title`, keeping the same
    directory prefix and extension. Needed because a scraper's
    resolve_unverified_document (see core/scrapers/base.py) corrects doc.title
    only *after* the storage key was already resolved from the pre-correction
    title (e.g. CSJ's "doc"/"(3)" placeholder, or SAMAI's Consejo de Estado
    radicado before its extra number is read from the downloaded PDF) — without
    rebuilding the key, the corrected title lands in the database but the file
    itself keeps its old, uncorrected name in storage, and bulk-download ZIPs
    (which use storage_key, not title, as the archive entry name) would show
    the wrong name even though the single-document download already shows the
    corrected one."""
    path = PurePosixPath(storage_key)
    new_stem = _sanitize_filename_segment(title, fallback=path.stem)
    return str(path.with_name(f"{new_stem}{path.suffix}"))


def is_safe_storage_key(key: str) -> bool:
    """True if `key` is safe to join onto a local directory (or use as a ZIP
    arcname) without escaping it — not empty, not an absolute path, and no
    ".." traversal segment. Storage keys are always POSIX-style ("/"-delimited)
    regardless of the host OS, so PurePosixPath is used to split it into
    segments consistently on every platform."""
    if not key or key.startswith("/") or key.startswith("\\"):
        return False
    parts = PurePosixPath(key).parts
    return bool(parts) and ".." not in parts and not any(part in ("", ".") for part in parts)
