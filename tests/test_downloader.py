import subprocess
from pathlib import Path

import pytest
import requests
import responses
from pypdf import PdfWriter

import core.downloader as downloader_module
from core.downloader import Downloader, check_remote_content_length
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
def test_download_raises_file_not_found_when_server_returns_html_instead_of_the_file(tmp_path):
    """Some sites answer a not-yet-published document link with HTTP 200 and their
    own app-shell HTML (a "soft 404") instead of a real 404 status. Without this
    check, that HTML gets silently stored as if it were the actual document."""
    responses.add(
        responses.GET,
        "https://example.com/file.pdf",
        body="<!DOCTYPE html><html><body>App shell</body></html>",
        headers={"Content-Type": "text/html; charset=utf-8"},
        status=200,
    )
    downloader = Downloader()
    with pytest.raises(FileNotFoundError):
        downloader.download(_doc(), tmp_path)


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


@responses.activate
def test_download_retries_on_connection_error_then_succeeds(tmp_path):
    """A dropped/reset connection is just as transient as a timeout — a slow or
    flaky source (observed for real against JEP's site) shouldn't be treated as
    a permanent failure on the first blip."""
    calls = {"count": 0}

    def _callback(request):
        calls["count"] += 1
        if calls["count"] < 2:
            raise requests.exceptions.ConnectionError()
        return (200, {"Content-Type": "application/pdf"}, b"ok")

    responses.add_callback(responses.GET, "https://example.com/file.pdf", callback=_callback)
    downloader = Downloader()
    result = downloader.download(_doc(), tmp_path)
    assert result.local_path.read_bytes() == b"ok"
    assert calls["count"] == 2


@responses.activate
def test_download_retries_on_chunked_encoding_error_then_succeeds(tmp_path):
    """An incomplete/interrupted read mid-stream (ChunkedEncodingError) is also
    transient and must not be treated as a permanent failure on the first try."""
    calls = {"count": 0}

    def _callback(request):
        calls["count"] += 1
        if calls["count"] < 2:
            raise requests.exceptions.ChunkedEncodingError()
        return (200, {"Content-Type": "application/pdf"}, b"ok")

    responses.add_callback(responses.GET, "https://example.com/file.pdf", callback=_callback)
    downloader = Downloader()
    result = downloader.download(_doc(), tmp_path)
    assert result.local_path.read_bytes() == b"ok"
    assert calls["count"] == 2


@responses.activate
def test_download_raises_after_exhausting_all_retries_on_transient_errors(tmp_path):
    calls = {"count": 0}

    def _callback(request):
        calls["count"] += 1
        raise requests.exceptions.ConnectionError("conexión rechazada")

    responses.add_callback(responses.GET, "https://example.com/file.pdf", callback=_callback)
    downloader = Downloader()
    with pytest.raises(requests.exceptions.ConnectionError):
        downloader.download(_doc(), tmp_path)
    assert calls["count"] == 3


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
def test_download_preserves_doc_convert_to_value_in_converted_format(tmp_path, monkeypatch):
    """converted_format must reflect the document's own convert_to value (e.g. 'rtf_word',
    the only value used in production by the samai family), not a hardcoded literal —
    even when the actual conversion happens via the pypdf fallback rather than Word."""
    responses.add(
        responses.GET,
        "https://example.com/file.pdf",
        body=_pdf_bytes(),
        headers={"Content-Type": "application/pdf"},
        status=200,
    )
    downloader = Downloader()

    def _raise(*_args, **_kwargs):
        raise RuntimeError("Word no disponible")

    monkeypatch.setattr(downloader._word_converter, "convert", _raise)

    result = downloader.download(_doc(convert_to="rtf_word"), tmp_path)

    assert result.converted_format == "rtf_word"
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


@responses.activate
def test_download_updates_content_type_to_rtf_when_conversion_succeeds(tmp_path):
    """The stored content_type must reflect the CONVERTED file (RTF), not the
    original pre-conversion type — otherwise the upload would carry a mismatched
    Content-Type header, the same class of bug already fixed for the un-converted
    upload path (worker/tasks.py)."""
    responses.add(
        responses.GET,
        "https://example.com/file.pdf",
        body=_pdf_bytes(),
        headers={"Content-Type": "application/pdf"},
        status=200,
    )
    downloader = Downloader()
    result = downloader.download(_doc(convert_to="rtf"), tmp_path)

    assert result.content_type == "application/rtf"


@responses.activate
def test_download_keeps_original_content_type_when_conversion_silently_fails(tmp_path, monkeypatch):
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

    assert result.content_type == "application/pdf"


def test_find_soffice_returns_path_from_which(monkeypatch):
    monkeypatch.setattr(downloader_module.shutil, "which", lambda name: "/usr/bin/soffice")
    assert downloader_module._find_soffice() == "/usr/bin/soffice"


def test_find_soffice_falls_back_to_known_windows_install_path_when_not_on_path(monkeypatch, tmp_path):
    monkeypatch.setattr(downloader_module.shutil, "which", lambda name: None)
    fake_soffice = tmp_path / "soffice.exe"
    fake_soffice.write_text("")
    monkeypatch.setattr(downloader_module, "_SOFFICE_FALLBACK_PATHS", [str(fake_soffice)])

    assert downloader_module._find_soffice() == str(fake_soffice)


def test_find_soffice_raises_when_not_found_anywhere(monkeypatch):
    monkeypatch.setattr(downloader_module.shutil, "which", lambda name: None)
    monkeypatch.setattr(downloader_module, "_SOFFICE_FALLBACK_PATHS", [])

    with pytest.raises(FileNotFoundError):
        downloader_module._find_soffice()


def test_convert_to_pdf_via_libreoffice_invokes_soffice_without_an_import_filter(tmp_path, monkeypatch):
    """Unlike the PDF->RTF direction, converting a native office format (RTF/DOC/DOCX)
    to PDF needs no --infilter override — LibreOffice already knows how to read those
    as Writer documents."""
    rtf_path = tmp_path / "doc.rtf"
    rtf_path.write_text("{\\rtf1}")

    monkeypatch.setattr(downloader_module, "_find_soffice", lambda: "soffice")

    captured = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        (tmp_path / "doc.pdf").write_bytes(b"%PDF-1.4")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(downloader_module.subprocess, "run", _fake_run)

    result = downloader_module.convert_to_pdf_via_libreoffice(rtf_path)

    assert result == rtf_path.with_suffix(".pdf")
    cmd = captured["cmd"]
    assert cmd[0] == "soffice"
    assert cmd[1] == "--headless"
    assert cmd[2].startswith("-env:UserInstallation=")
    assert cmd[3:] == ["--convert-to", "pdf", "--outdir", str(tmp_path), str(rtf_path)]


def test_libreoffice_conversions_use_a_different_isolated_profile_per_invocation(tmp_path, monkeypatch):
    """Regression test: LibreOffice's default shared user profile holds an exclusive
    lock, so a second concurrent headless invocation silently fails (no exception,
    no stderr, no output file) while another is already running — reproduced for
    real by running the JEP backfill and an on-demand preview conversion at the
    same time. Each invocation must get its own disposable profile directory."""
    monkeypatch.setattr(downloader_module, "_find_soffice", lambda: "soffice")

    captured_profiles = []

    def _fake_run(cmd, **kwargs):
        env_arg = next(arg for arg in cmd if arg.startswith("-env:UserInstallation="))
        captured_profiles.append(env_arg)
        output_path = Path(cmd[-1]).with_suffix(".pdf")
        output_path.write_bytes(b"%PDF-1.4")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(downloader_module.subprocess, "run", _fake_run)

    doc_a = tmp_path / "a.rtf"
    doc_a.write_text("{\\rtf1}")
    doc_b = tmp_path / "b.rtf"
    doc_b.write_text("{\\rtf1}")

    downloader_module.convert_to_pdf_via_libreoffice(doc_a)
    downloader_module.convert_to_pdf_via_libreoffice(doc_b)

    assert len(captured_profiles) == 2
    assert captured_profiles[0] != captured_profiles[1]


def test_convert_to_pdf_via_libreoffice_raises_when_output_file_is_missing(tmp_path, monkeypatch):
    rtf_path = tmp_path / "doc.rtf"
    rtf_path.write_text("{\\rtf1}")

    monkeypatch.setattr(downloader_module, "_find_soffice", lambda: "soffice")
    monkeypatch.setattr(
        downloader_module.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, stdout="", stderr="algo falló"),
    )

    with pytest.raises(RuntimeError):
        downloader_module.convert_to_pdf_via_libreoffice(rtf_path)


@responses.activate
def test_check_remote_content_length_returns_the_header_value():
    responses.add(responses.HEAD, "https://example.com/file.rtf", headers={"Content-Length": "76245"}, status=200)

    assert check_remote_content_length("https://example.com/file.rtf") == 76245


@responses.activate
def test_check_remote_content_length_returns_none_when_header_is_missing():
    responses.add(responses.HEAD, "https://example.com/file.rtf", status=200)

    assert check_remote_content_length("https://example.com/file.rtf") is None


@responses.activate
def test_check_remote_content_length_returns_none_on_non_200_status():
    responses.add(responses.HEAD, "https://example.com/file.rtf", status=404)

    assert check_remote_content_length("https://example.com/file.rtf") is None


@responses.activate
def test_check_remote_content_length_returns_none_on_request_exception():
    def _callback(request):
        raise requests.exceptions.ConnectionError("conexión rechazada")

    responses.add_callback(responses.HEAD, "https://example.com/file.rtf", callback=_callback)

    assert check_remote_content_length("https://example.com/file.rtf") is None
