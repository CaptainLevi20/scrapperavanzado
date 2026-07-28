import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

from core.models import RawDocModel
from core.utils import extract_filename, is_safe_storage_key, storage_path

# LibreOffice's winget/MSI installer does not add soffice.exe to PATH (verified: absent
# from both the user and Machine-level PATH env vars after a fresh install), so PATH
# lookup alone cannot be relied on for this executable on Windows.
_SOFFICE_FALLBACK_PATHS = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
]


def check_remote_content_length(url: str, timeout: int = 15) -> Optional[int]:
    """HEAD barato para saber si el archivo remoto cambió de tamaño sin descargarlo
    completo. Devuelve None si el servidor no expone Content-Length, responde con un
    status distinto de 200, o la petición falla — el llamador debe entonces caer a
    descargar y comparar el tamaño real."""
    try:
        response = requests.head(url, allow_redirects=True, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    except requests.exceptions.RequestException:
        return None
    if response.status_code != 200:
        return None
    content_length = response.headers.get("Content-Length")
    return int(content_length) if content_length is not None else None


def _find_soffice() -> str:
    found = shutil.which("soffice")
    if found:
        return found
    for path in _SOFFICE_FALLBACK_PATHS:
        if Path(path).exists():
            return path
    raise FileNotFoundError("No se encontró el ejecutable de LibreOffice (soffice)")


def _run_soffice(convert_args: list[str], input_path: Path, output_suffix: str, timeout: int) -> Path:
    """Ejecuta soffice en modo headless con un perfil de usuario aislado y
    desechable para esta única invocación. LibreOffice usa por defecto un perfil
    compartido con bloqueo exclusivo: si otra instancia headless ya está corriendo
    (por ejemplo, un backfill en curso al mismo tiempo que una vista previa bajo
    demanda), la segunda invocación falla en silencio — sin excepción, sin stderr,
    y sin generar el archivo de salida — confirmado empíricamente reproduciendo
    justo ese escenario. Un perfil por invocación elimina esa colisión."""
    soffice = _find_soffice()
    output_dir = input_path.parent
    with tempfile.TemporaryDirectory(prefix="lo_profile_") as profile_dir:
        result = subprocess.run(
            [
                soffice,
                "--headless",
                f"-env:UserInstallation=file:///{Path(profile_dir).as_posix()}",
                *convert_args,
                "--outdir",
                str(output_dir),
                str(input_path),
            ],
            capture_output=True,
            timeout=timeout,
            text=True,
        )
    output_path = input_path.with_suffix(output_suffix)
    if not output_path.exists():
        raise RuntimeError(
            f"LibreOffice no generó el archivo esperado: {output_path}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return output_path


def convert_to_pdf_via_libreoffice(input_path: Path, timeout: int = 180) -> Path:
    """Convierte un documento de oficina (RTF, DOC, DOCX) a PDF usando LibreOffice —
    usado para generar la vista previa bajo demanda. A diferencia de Word (52.4s en
    una prueba real con un RTF de 20MB con imágenes incrustadas, contra el límite
    síncrono de 30s del endpoint de previsualización), LibreOffice tomó 15.9s para
    el mismo archivo."""
    return _run_soffice(["--convert-to", "pdf"], input_path, ".pdf", timeout)


@dataclass
class DownloadResult:
    local_path: Path
    storage_key: str
    content_type: str
    file_size_bytes: int
    converted_format: str | None = None


class Downloader:
    @staticmethod
    def _resolve_jwt_indirect(jwt_url: str, headers: dict) -> requests.Response:
        session = requests.Session()
        session.headers.update(headers)
        ver = session.get(jwt_url, timeout=30)
        ver.raise_for_status()
        soup = BeautifulSoup(ver.text, "html.parser")

        blob_url = next(
            (a["href"] for a in soup.find_all("a", href=True) if "blob.core.windows.net" in a["href"]),
            None,
        )
        if blob_url:
            return session.get(blob_url, stream=True, timeout=120)

        raise FileNotFoundError(f"Archivo aún no disponible en SAMAI: {jwt_url[:80]}")

    @staticmethod
    def _resolve_storage_key(doc: RawDocModel, filename: dict) -> str:
        if doc.save_path:
            return doc.save_path.replace("(filename)", filename["filename"]).replace(
                "(extension)", filename["extension"]
            )
        return storage_path(doc.source, doc.f_public, doc.tipo, f"{filename['filename']}{filename['extension']}")

    def download(self, doc: RawDocModel, tmp_dir: Path, stop_event=None) -> DownloadResult:
        headers = {"User-Agent": "Mozilla/5.0"}

        # Un timeout, una conexión rechazada/cortada, o una lectura incompleta a
        # mitad de la descarga son todas transitorias (se observó esto en producción
        # contra el sitio de JEP, que responde lento e inconsistente bajo carga) —
        # ninguna debe tratarse como fallo permanente en el primer intento. Se
        # reintenta la secuencia completa (conexión + lectura del cuerpo) porque un
        # corte a mitad de la descarga dejaría un archivo parcial si solo se
        # reintentara la conexión inicial.
        _TRANSIENT_ERRORS = (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
        )

        last_exc = None
        for _attempt in range(3):
            try:
                if doc.link["method"] == "POST":
                    headers["Content-Type"] = "application/json"
                    body = doc.link.get("body", {})
                    response = requests.post(doc.link["url"], json=body, headers=headers, stream=True, timeout=120)
                elif doc.link["method"] == "jwt_indirect":
                    response = self._resolve_jwt_indirect(doc.link["url"], headers)
                else:
                    response = requests.get(doc.link["url"], headers=headers, stream=True, timeout=120)

                with response as r:
                    r.raise_for_status()
                    # Some sources (Rama Judicial's tribunal sites) send parameters
                    # after the MIME type (e.g. "application/pdf;charset=UTF-8").
                    # Stored verbatim, that breaks every exact-match consumer downstream
                    # (the preview endpoint's `== "application/pdf"` check, in particular)
                    # even though the file itself is a perfectly valid, previewable PDF.
                    content_type = r.headers.get("Content-Type", "").split(";", 1)[0].strip()
                    if content_type.lower().startswith("text/html"):
                        raise FileNotFoundError(
                            f"El servidor devolvió una página HTML en vez del archivo: {doc.link['url']}"
                        )
                    disposition = r.headers.get("Content-Disposition", "")

                    filename = extract_filename(disposition, content_type, doc.link["url"], doc.title)
                    storage_key = self._resolve_storage_key(doc, filename)
                    if not is_safe_storage_key(storage_key):
                        # Backstop in case a family's own save_path template (not
                        # just the remote filename extract_filename already
                        # sanitizes) produces something unsafe — fail this one
                        # document instead of silently writing outside where
                        # every other document expects to live.
                        raise ValueError(f"Clave de almacenamiento no segura: {storage_key!r}")

                    temp_path = tmp_dir / f"{uuid.uuid4().hex}{filename['extension']}"
                    with open(temp_path, "wb") as f:
                        for chunk in r.iter_content(8192):
                            if stop_event is not None and getattr(stop_event, "is_set", lambda: False)():
                                raise InterruptedError("Descarga cancelada")
                            if chunk:
                                f.write(chunk)
                break
            except _TRANSIENT_ERRORS as e:
                last_exc = e
        else:
            raise last_exc

        return DownloadResult(
            local_path=temp_path,
            storage_key=storage_key,
            content_type=content_type,
            file_size_bytes=temp_path.stat().st_size,
        )
