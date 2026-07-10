from pathlib import Path

import pytest
import requests
import responses
from pypdf import PdfWriter

from core.downloader import Downloader
from core.models import RawDocModel


def _doc(method="GET", url="https://example.com/file.pdf", body=None, save_path=None, convert_to=None):
    link = {"url": url, "method": method}
    if body:
        link["body"] = body
    return RawDocModel(
        source="Test",
        link=link,
        title="Documento de prueba",
        tipo="Auto",
        f_public="2026-01-01",
        save_path=save_path,
        convert_to=convert_to,
    )


@responses.activate
def test_download_get_writes_temp_file_and_builds_default_storage_key(tmp_path):
    responses.add(
        responses.GET,
        "https://example.com/file.pdf",
        body=b"%PDF-1.4 contenido de prueba",
        headers={"Content-Type": "application/pdf"},
        status=200,
    )
    downloader = Downloader()
    result = downloader.download(_doc(), tmp_path)

    assert result.local_path.exists()
    assert result.local_path.read_bytes() == b"%PDF-1.4 contenido de prueba"
    assert result.storage_key == "Test/2026-01-01/Auto/file.pdf"
    assert result.content_type == "application/pdf"


@responses.activate
def test_download_post_sends_json_body(tmp_path):
    responses.add(
        responses.POST,
        "https://example.com/api",
        body=b"contenido",
        headers={"Content-Type": "application/octet-stream"},
        status=200,
    )
    downloader = Downloader()
    doc = _doc(method="POST", url="https://example.com/api", body={"id": "123"})
    result = downloader.download(doc, tmp_path)
    assert result.local_path.read_bytes() == b"contenido"


@responses.activate
def test_download_jwt_indirect_resolves_blob_url(tmp_path):
    responses.add(
        responses.GET,
        "https://example.com/ver",
        body='<html><a href="https://foo.blob.core.windows.net/doc.pdf">ver</a></html>',
        status=200,
    )
    responses.add(
        responses.GET,
        "https://foo.blob.core.windows.net/doc.pdf",
        body=b"contenido blob",
        headers={"Content-Type": "application/pdf"},
        status=200,
    )
    downloader = Downloader()
    doc = _doc(method="jwt_indirect", url="https://example.com/ver")
    result = downloader.download(doc, tmp_path)
    assert result.local_path.read_bytes() == b"contenido blob"


@responses.activate
def test_download_jwt_indirect_raises_file_not_found_when_blob_missing(tmp_path):
    responses.add(responses.GET, "https://example.com/ver", body="<html>sin enlace blob</html>", status=200)
    downloader = Downloader()
    doc = _doc(method="jwt_indirect", url="https://example.com/ver")
    with pytest.raises(FileNotFoundError):
        downloader.download(doc, tmp_path)


@responses.activate
def test_download_retries_on_timeout_then_succeeds(tmp_path):
    calls = {"count": 0}

    def _callback(request):
        calls["count"] += 1
        if calls["count"] < 2:
            raise requests.exceptions.Timeout()
        return (200, {"Content-Type": "application/pdf"}, b"ok")

    responses.add_callback(responses.GET, "https://example.com/file.pdf", callback=_callback)
    downloader = Downloader()
    result = downloader.download(_doc(), tmp_path)
    assert result.local_path.read_bytes() == b"ok"
    assert calls["count"] == 2


def test_convert_rtf_word_falls_back_to_pypdf_when_word_conversion_fails(tmp_path, monkeypatch):
    pdf_path = tmp_path / "doc.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    downloader = Downloader()

    def _raise(*_args, **_kwargs):
        raise RuntimeError("Word no disponible")

    monkeypatch.setattr(downloader._word_converter, "convert", _raise)

    converted = downloader._convert(pdf_path, "rtf_word")
    assert converted.suffix == ".rtf"
    assert converted.exists()


def _pdf_bytes():
    import io

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@responses.activate
def test_download_records_converted_format_when_conversion_succeeds(tmp_path):
    responses.add(
        responses.GET,
        "https://example.com/file.pdf",
        body=_pdf_bytes(),
        headers={"Content-Type": "application/pdf"},
        status=200,
    )
    downloader = Downloader()
    result = downloader.download(_doc(convert_to="rtf"), tmp_path)

    assert result.converted_format == "rtf"
    assert result.storage_key.endswith(".rtf")
    assert result.local_path.suffix == ".rtf"


@responses.activate
def test_download_leaves_converted_format_none_when_conversion_silently_fails(tmp_path, monkeypatch):
    import core.downloader as downloader_module

    responses.add(
        responses.GET,
        "https://example.com/file.pdf",
        body=b"not actually a pdf",
        headers={"Content-Type": "application/pdf"},
        status=200,
    )

    def _raise(*_args, **_kwargs):
        raise RuntimeError("conversión falló")

    monkeypatch.setattr(downloader_module, "_pdf_to_rtf_fallback", _raise)

    downloader = Downloader()
    result = downloader.download(_doc(convert_to="rtf"), tmp_path)

    assert result.converted_format is None
    assert result.storage_key.endswith(".pdf")
    assert result.local_path.suffix == ".pdf"
