import hashlib
import re

from core.models import RawDocModel

# Espejo del formato que produce core/scrapers/families/rama_judicial.py::_normalize_title
# (T_{CODIGO}_{radicado segmentado en 23 dígitos}). No importa TRIBUNAL_CODES desde el
# módulo del scraper para no acoplar esta capa a uno de familia específico — el rango de
# 2-5 letras mayúsculas cubre los códigos reales (3-4 letras) con margen.
RADICADO_TITLE_PATTERN = re.compile(r"^T_[A-Z]{2,5}_\d{5}_\d{2}_\d{2}_\d{3}_\d{4}_\d{5}_\d{2}$")


def is_radicado_title(title: str) -> bool:
    return bool(RADICADO_TITLE_PATTERN.match(title))


def make_doc_id(key: str, f_public: str) -> str:
    return hashlib.sha1(f"{key}_{f_public}".encode()).hexdigest()


def compute_doc_id(doc: RawDocModel, include_publication_date: bool = True) -> str:
    body = doc.link.get("body") or {}
    key = body["path"] if "path" in body else doc.link["url"]
    if not include_publication_date:
        return hashlib.sha1(key.encode()).hexdigest()
    return make_doc_id(key, doc.f_public)


def extract_filename(disposition: str, content_type: str, url: str, opt_title: str) -> dict:
    if disposition:
        match = re.search(r'filename="?([^"]+)"?', disposition)
        if match:
            filename = match.group(1)
            ext = "." + filename.split(".")[-1] if "." in filename else ""
            return {"filename": filename.split(".")[0], "extension": ext}

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
            ext = "." + url_ext
    return {"filename": name, "extension": ext}


def storage_path(*parts) -> str:
    return "/".join(str(p) for p in parts)
