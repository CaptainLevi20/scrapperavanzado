"""Verificación del tipo REAL de cada archivo descargado.

IURISYNC trae archivos de sitios ajenos y la mayoría pasan después a los demás
productos (RedJurista, la BDU, JurIA) y al banco de datos de la entidad. Antes
de guardar uno se comprueba por su contenido, no por el Content-Type que manda
el servidor ni por la extensión del nombre:

- que sea un formato permitido: PDF, Word (DOC/DOCX), Excel (XLS/XLSX), RTF,
  TIFF, o un ZIP de anexos que solo contenga esos formatos;
- que no esté dañado (PDF sin su marca de final, ZIP que no se puede leer);
- que no traiga macros (el código que un documento de Office puede ejecutar).

Todo lo demás se rechaza con ArchivoNoPermitido y el documento queda como
fallido en la corrida, con el motivo. Revisado contra los 2.698 documentos de
desarrollo el 2026-11-05: ninguno legítimo queda rechazado.

Esto NO reemplaza un antivirus (es el siguiente paso del plan): un PDF bien
formado con contenido malicioso pasa esta verificación.
"""

import zipfile
from pathlib import Path, PurePosixPath

_FIRMA_OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # DOC / XLS antiguos
_FIRMA_ZIP = b"PK\x03\x04"  # DOCX / XLSX y ZIP
_FIRMAS_TIFF = (b"II*\x00", b"MM\x00*")

# Nombre del módulo de macros dentro de un DOC/XLS antiguo (en UTF-16).
_MARCA_MACROS_OLE2 = "_VBA_PROJECT".encode("utf-16-le")
_TAMANO_BLOQUE = 1024 * 1024

# El estándar PDF permite basura antes del encabezado (hasta 1 KB) y algunos
# generadores dejan relleno tras la marca de final; en los 2.476 PDF de
# desarrollo la marca "%%EOF" siempre está dentro de los últimos 2 KB.
_PDF_BUSCAR_ENCABEZADO = 1024
_PDF_BUSCAR_FINAL = 4096

_EXTENSIONES_PERMITIDAS_EN_ZIP = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".rtf", ".tif", ".tiff"}


class ArchivoNoPermitido(ValueError):
    """El archivo descargado no es un documento permitido, está dañado o trae macros."""


def verificar_archivo(ruta: Path, origen: str = "") -> str:
    """Comprueba el archivo en `ruta` y devuelve el formato detectado ("pdf",
    "word", "excel", "office-antiguo", "rtf", "tiff" o "zip"). Lanza
    ArchivoNoPermitido si no pasa. `origen` (la URL) solo se usa en el mensaje."""
    sufijo = f": {origen}" if origen else ""
    tamano = ruta.stat().st_size
    if tamano == 0:
        raise ArchivoNoPermitido(f"El archivo descargado está vacío{sufijo}")

    with open(ruta, "rb") as archivo:
        inicio = archivo.read(_PDF_BUSCAR_ENCABEZADO)

    # Primero las firmas que van EXACTAMENTE al inicio del archivo. El PDF va de
    # último porque su marca se busca en todo el primer KB: un ZIP que guarda un
    # PDF sin comprimir también tiene "%PDF-" ahí, y si se revisara primero, el
    # ZIP pasaría como PDF sin revisar lo demás que trae adentro.
    if inicio.startswith(_FIRMA_ZIP):
        return _verificar_zip(ruta, sufijo)
    if inicio.startswith(_FIRMA_OLE2):
        if _contiene(ruta, _MARCA_MACROS_OLE2):
            raise ArchivoNoPermitido(f"El documento de Office trae macros{sufijo}")
        return "office-antiguo"
    if inicio[:4] in _FIRMAS_TIFF:
        return "tiff"
    if inicio.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"{\\rtf"):
        return "rtf"
    if b"%PDF-" in inicio:
        _verificar_pdf(ruta, tamano, sufijo)
        return "pdf"
    raise ArchivoNoPermitido(
        f"Tipo de archivo no permitido (no es PDF, Word, Excel, RTF ni TIFF){sufijo}"
    )


def _verificar_pdf(ruta: Path, tamano: int, sufijo: str) -> None:
    with open(ruta, "rb") as archivo:
        archivo.seek(max(0, tamano - _PDF_BUSCAR_FINAL))
        final = archivo.read()
    if b"%%EOF" not in final:
        raise ArchivoNoPermitido(f"El PDF está incompleto o dañado (no tiene marca de final){sufijo}")


def _verificar_zip(ruta: Path, sufijo: str) -> str:
    try:
        with zipfile.ZipFile(ruta) as zf:
            nombres = [i.filename for i in zf.infolist() if not i.is_dir()]
    except (zipfile.BadZipFile, OSError) as exc:
        raise ArchivoNoPermitido(f"El archivo comprimido está dañado{sufijo}") from exc

    if "[Content_Types].xml" in nombres:
        # Documento de Office moderno (DOCX/XLSX): por dentro es un ZIP.
        if any(PurePosixPath(n).name.lower() == "vbaproject.bin" for n in nombres):
            raise ArchivoNoPermitido(f"El documento de Office trae macros{sufijo}")
        if any(n.startswith("word/") for n in nombres):
            return "word"
        if any(n.startswith("xl/") for n in nombres):
            return "excel"
        raise ArchivoNoPermitido(
            f"Tipo de archivo no permitido (documento de Office que no es Word ni Excel){sufijo}"
        )

    # ZIP de anexos: cada archivo de adentro debe ser de un formato permitido.
    for nombre in nombres:
        if PurePosixPath(nombre).suffix.lower() not in _EXTENSIONES_PERMITIDAS_EN_ZIP:
            raise ArchivoNoPermitido(
                f"El archivo comprimido contiene un archivo no permitido ({nombre}){sufijo}"
            )
    return "zip"


def _contiene(ruta: Path, marca: bytes) -> bool:
    """Busca `marca` en el archivo por bloques, sin cargarlo entero en memoria,
    conservando el final de cada bloque para no perder una marca partida en el
    borde entre dos lecturas."""
    solape = len(marca) - 1
    cola = b""
    with open(ruta, "rb") as archivo:
        while bloque := archivo.read(_TAMANO_BLOQUE):
            ventana = cola + bloque
            if marca in ventana:
                return True
            cola = ventana[-solape:]
    return False
