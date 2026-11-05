"""Pruebas de la verificación del tipo real de cada archivo descargado.

IURISYNC descarga archivos de sitios ajenos y la mayoría pasan después a los
demás productos y al banco de datos de la entidad. Antes de guardar uno, se
comprueba por su CONTENIDO (no por lo que dice el servidor ni por la
extensión) que de verdad sea PDF, Word, RTF, Excel o TIFF, que no esté
dañado y que no traiga macros.

Los archivos de prueba se construyen aquí mismo con los bytes reales de cada
formato, en vez de cuerpos falsos como b"contenido".
"""

import io
import zipfile

import pytest
import responses

from core.downloader import Downloader
from core.models import RawDocModel
from core.verificacion_archivos import ArchivoNoPermitido, verificar_archivo

_PDF_VALIDO = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
_OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504


def _zip(entradas: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for nombre, contenido in entradas.items():
            zf.writestr(nombre, contenido)
    return buffer.getvalue()


def _docx(con_macros: bool = False) -> bytes:
    entradas = {"[Content_Types].xml": b"<Types/>", "word/document.xml": b"<w:document/>"}
    if con_macros:
        entradas["word/vbaProject.bin"] = _OLE2
    return _zip(entradas)


def _xlsx() -> bytes:
    return _zip({"[Content_Types].xml": b"<Types/>", "xl/workbook.xml": b"<workbook/>"})


def _escribir(tmp_path, contenido: bytes, nombre: str = "archivo.bin"):
    ruta = tmp_path / nombre
    ruta.write_bytes(contenido)
    return ruta


# --- Lo que SÍ se acepta -------------------------------------------------


@pytest.mark.parametrize(
    "contenido",
    [
        pytest.param(_PDF_VALIDO, id="pdf"),
        pytest.param(b"\r\n" + _PDF_VALIDO, id="pdf-con-bytes-antes-del-encabezado"),
        pytest.param(_PDF_VALIDO + b"\x00" * 100, id="pdf-con-relleno-tras-el-final"),
        pytest.param(_docx(), id="docx"),
        pytest.param(_xlsx(), id="xlsx"),
        pytest.param(_OLE2, id="doc-o-xls-antiguo"),
        pytest.param(b"{\\rtf1\\ansi texto}", id="rtf"),
        pytest.param(b"II*\x00" + b"\x00" * 20, id="tiff"),
        # Anexo real de la Superfinanciera: un ZIP con un Excel y un Word.
        pytest.param(_zip({"formato.xlsx": _xlsx(), "instructivo.docx": _docx()}), id="zip-de-anexos"),
    ],
)
def test_acepta_los_formatos_permitidos(tmp_path, contenido):
    verificar_archivo(_escribir(tmp_path, contenido))


# --- Lo que se rechaza ----------------------------------------------------


@pytest.mark.parametrize(
    "contenido, motivo",
    [
        pytest.param(b"", "vacío", id="vacio"),
        pytest.param(b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 64, "no permitido", id="programa-exe"),
        pytest.param(b"<html><body>hola</body></html>", "no permitido", id="pagina-web"),
        pytest.param(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32, "no permitido", id="imagen-png"),
        pytest.param(_PDF_VALIDO[:-7], "incompleto", id="pdf-cortado-sin-final"),
        pytest.param(b"PK\x03\x04 esto no es un zip", "dañado", id="zip-danado"),
        pytest.param(_docx(con_macros=True), "macros", id="docx-con-macros"),
        pytest.param(_OLE2 + "_VBA_PROJECT".encode("utf-16-le"), "macros", id="doc-antiguo-con-macros"),
        pytest.param(_zip({"factura.pdf": _PDF_VALIDO, "abrir.exe": b"MZ"}), "abrir.exe", id="zip-con-programa"),
        pytest.param(_zip({"interno.zip": _zip({"a.pdf": _PDF_VALIDO})}), "interno.zip", id="zip-dentro-de-zip"),
        pytest.param(
            _zip({"[Content_Types].xml": b"<Types/>", "ppt/presentation.xml": b"<p/>"}),
            "no permitido",
            id="presentacion-pptx",
        ),
    ],
)
def test_rechaza_lo_que_no_es_un_documento_permitido(tmp_path, contenido, motivo):
    with pytest.raises(ArchivoNoPermitido, match=motivo):
        verificar_archivo(_escribir(tmp_path, contenido))


def test_un_programa_con_extension_pdf_se_rechaza(tmp_path):
    # La extensión no cuenta: lo que manda es el contenido.
    with pytest.raises(ArchivoNoPermitido):
        verificar_archivo(_escribir(tmp_path, b"MZ\x90\x00" + b"\x00" * 64, nombre="sentencia.pdf"))


def test_detecta_macros_partidas_entre_dos_bloques_de_lectura(tmp_path, monkeypatch):
    # El nombre del módulo de macros puede quedar partido justo en el borde
    # entre dos lecturas del archivo; aun así debe detectarse.
    import core.verificacion_archivos as modulo

    monkeypatch.setattr(modulo, "_TAMANO_BLOQUE", 16)
    marca = "_VBA_PROJECT".encode("utf-16-le")
    contenido = _OLE2[:8] + b"\x00" * 3 + marca + b"\x00" * 40
    with pytest.raises(ArchivoNoPermitido, match="macros"):
        verificar_archivo(_escribir(tmp_path, contenido))


# --- Integración con la descarga ------------------------------------------


def _doc(url="https://example.com/file.pdf"):
    return RawDocModel(
        source="Test",
        link={"url": url, "method": "GET"},
        title="Documento de prueba",
        tipo="Auto",
        f_public="2026-01-01",
    )


@pytest.mark.verificar_archivos
@responses.activate
def test_la_descarga_rechaza_un_programa_disfrazado_de_pdf_y_no_deja_el_archivo(tmp_path):
    responses.add(
        responses.GET,
        "https://example.com/file.pdf",
        body=b"MZ\x90\x00" + b"\x00" * 64,
        headers={"Content-Type": "application/pdf"},
        status=200,
    )

    with pytest.raises(ArchivoNoPermitido, match="https://example.com/file.pdf"):
        Downloader().download(_doc(), tmp_path)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.verificar_archivos
@responses.activate
def test_la_descarga_de_un_pdf_valido_sigue_funcionando(tmp_path):
    responses.add(
        responses.GET,
        "https://example.com/file.pdf",
        body=_PDF_VALIDO,
        headers={"Content-Type": "application/pdf"},
        status=200,
    )

    result = Downloader().download(_doc(), tmp_path)

    assert result.local_path.read_bytes() == _PDF_VALIDO
