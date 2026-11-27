import subprocess
from pathlib import Path

import pytest
import requests
import responses

import core.downloader as downloader_module
from core.downloader import Downloader, check_remote_content_length
from core.models import RawDocModel


def _doc(method="GET", url="https://example.com/file.pdf", body=None, save_path=None, verify=None):
    link = {"url": url, "method": method}
    if body:
        link["body"] = body
    if verify is not None:
        link["verify"] = verify
    return RawDocModel(
        source="Test",
        link=link,
        title="Documento de prueba",
        tipo="Auto",
        f_public="2026-01-01",
        save_path=save_path,
    )


@responses.activate
def test_download_verifies_tls_by_default(tmp_path, monkeypatch):
    responses.add(
        responses.GET, "https://example.com/file.pdf",
        body=b"%PDF-1.4 x", headers={"Content-Type": "application/pdf"}, status=200,
    )
    verifies = []
    real_get = downloader_module.requests.get
    monkeypatch.setattr(
        downloader_module.requests, "get",
        lambda *a, **k: (verifies.append(k.get("verify")), real_get(*a, **k))[1],
    )

    Downloader().download(_doc(), tmp_path)

    assert verifies == [True]


@responses.activate
def test_download_skips_tls_verification_when_the_link_declares_verify_false(tmp_path, monkeypatch):
    # La Corte Constitucional presenta un certificado que certifi no valida; su
    # scraper marca link["verify"] = False para que la descarga no falle con SSL.
    responses.add(
        responses.GET, "https://example.com/file.pdf",
        body=b"%PDF-1.4 x", headers={"Content-Type": "application/pdf"}, status=200,
    )
    verifies = []
    real_get = downloader_module.requests.get
    monkeypatch.setattr(
        downloader_module.requests, "get",
        lambda *a, **k: (verifies.append(k.get("verify")), real_get(*a, **k))[1],
    )

    Downloader().download(_doc(verify=False), tmp_path)

    assert verifies == [False]


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
def test_download_rejects_a_save_path_template_that_resolves_outside_the_storage_root(tmp_path):
    """Regression test: a family's save_path template (e.g. adr/adres/ane/anh's
    "(filename)(extension)") interpolates the remote server's own filename
    directly. Even though extract_filename now sanitizes that filename, this is
    a backstop for the template itself producing something unsafe — it must
    raise instead of silently proceeding with a key that could escape the
    storage root."""
    responses.add(
        responses.GET,
        "https://example.com/file.pdf",
        body=b"%PDF-1.4 contenido de prueba",
        headers={"Content-Type": "application/pdf"},
        status=200,
    )
    downloader = Downloader()
    doc = _doc(save_path="../../(filename)(extension)")
    with pytest.raises(ValueError, match="no segura"):
        downloader.download(doc, tmp_path)


@responses.activate
def test_download_strips_charset_parameter_from_content_type(tmp_path):
    """Regression test: Rama Judicial's tribunal sites send `Content-Type:
    application/pdf;charset=UTF-8` (verified for real against Tribunal Superior
    de Bogotá/Antioquia/Cauca documents), and the raw header was being stored
    verbatim — the preview endpoint's exact-match check (`== "application/pdf"`)
    then silently 404'd on otherwise-valid, previewable PDFs. content_type must
    be normalized to just the MIME type, discarding any `;param=value` suffix."""
    responses.add(
        responses.GET,
        "https://example.com/file.pdf",
        body=b"%PDF-1.4 contenido de prueba",
        headers={"Content-Type": "application/pdf;charset=UTF-8"},
        status=200,
    )
    downloader = Downloader()
    result = downloader.download(_doc(), tmp_path)

    assert result.content_type == "application/pdf"


@responses.activate
def test_download_normalizes_octet_stream_content_type_to_pdf_from_filename_extension(tmp_path):
    """La Superintendencia Financiera (loader.php) sirve todo con
    `Content-Type: application/octet-stream`. Guardado tal cual, la vista previa
    404 para todos sus documentos aunque sean PDFs válidos. Cuando el servidor
    no dio un tipo real, debe derivarse de la extensión del archivo."""
    responses.add(
        responses.GET,
        "https://example.com/loader.php?id=1",
        body=b"%PDF-1.4 contenido",
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Disposition": 'attachment; filename="x.pdf"',
        },
        status=200,
    )
    result = Downloader().download(_doc(url="https://example.com/loader.php?id=1"), tmp_path)

    assert result.content_type == "application/pdf"


@responses.activate
def test_download_normalizes_octet_stream_content_type_to_docx_from_filename_extension(tmp_path):
    responses.add(
        responses.GET,
        "https://example.com/loader.php?id=2",
        body=b"PK\x03\x04 contenido",
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Disposition": 'attachment; filename="x.docx"',
        },
        status=200,
    )
    result = Downloader().download(_doc(url="https://example.com/loader.php?id=2"), tmp_path)

    assert result.content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@responses.activate
def test_download_leaves_octet_stream_content_type_untouched_for_an_unmapped_extension(tmp_path):
    responses.add(
        responses.GET,
        "https://example.com/loader.php?id=3",
        body=b"PK\x03\x04 zip",
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Disposition": 'attachment; filename="x.zip"',
        },
        status=200,
    )
    result = Downloader().download(_doc(url="https://example.com/loader.php?id=3"), tmp_path)

    assert result.content_type == "application/octet-stream"


@responses.activate
def test_download_does_not_override_a_real_server_content_type_using_the_extension(tmp_path):
    """La normalización solo aplica al caso octet-stream / vacío. Si el servidor
    mandó un tipo real (application/pdf), una extensión `.doc` en el nombre del
    archivo no debe pisarlo."""
    responses.add(
        responses.GET,
        "https://example.com/loader.php?id=4",
        body=b"%PDF-1.4 contenido",
        headers={
            "Content-Type": "application/pdf",
            "Content-Disposition": 'attachment; filename="x.doc"',
        },
        status=200,
    )
    result = Downloader().download(_doc(url="https://example.com/loader.php?id=4"), tmp_path)

    assert result.content_type == "application/pdf"


@responses.activate
def test_download_normalizes_text_plain_content_type_to_pdf_from_filename_extension(tmp_path):
    """Corantioquia (e-SIRENA) sirve sus PDF con `Content-Type: text/plain` y
    `filename=<id>.pdf`. Guardado tal cual, quedarían sin vista previa."""
    responses.add(
        responses.GET,
        "https://example.com/CtrlPublicaciones?ctrlAction=D&doc=2483007",
        body=b"%PDF-1.6 contenido",
        headers={
            "Content-Type": "text/plain",
            "Content-Disposition": "attachment; filename=2483007.pdf",
        },
        status=200,
    )
    result = Downloader().download(
        _doc(url="https://example.com/CtrlPublicaciones?ctrlAction=D&doc=2483007"), tmp_path
    )

    assert result.content_type == "application/pdf"
    assert result.local_path.suffix == ".pdf"


@responses.activate
def test_download_leaves_text_plain_content_type_untouched_for_a_real_text_file(tmp_path):
    responses.add(
        responses.GET,
        "https://example.com/notas",
        body=b"texto plano",
        headers={
            "Content-Type": "text/plain",
            "Content-Disposition": 'attachment; filename="notas.txt"',
        },
        status=200,
    )
    result = Downloader().download(_doc(url="https://example.com/notas"), tmp_path)

    assert result.content_type == "text/plain"


@responses.activate
def test_download_does_not_override_a_real_msword_content_type_using_the_extension(tmp_path):
    responses.add(
        responses.GET,
        "https://example.com/loader.php?id=5",
        body=b"\xd0\xcf\x11\xe0 contenido",
        headers={
            "Content-Type": "application/msword",
            "Content-Disposition": 'attachment; filename="x.pdf"',
        },
        status=200,
    )
    result = Downloader().download(_doc(url="https://example.com/loader.php?id=5"), tmp_path)

    assert result.content_type == "application/msword"


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
def test_download_jwt_indirect_resolves_blob_url_from_viewer_js_call(tmp_path):
    # SAMAI (Consejo de Estado / Tribunales Administrativos) stopped linking the
    # file as a plain <a href> and now hands it to a JS PDF viewer instead — the
    # real URL only appears inside a VerProvidenciaViewer.init(...) call. Confirmed
    # live on 2026-07-28: without this fallback, every SAMAI document is silently
    # dropped as "not available yet".
    responses.add(
        responses.GET,
        "https://example.com/ver",
        body=(
            "<html><script>"
            "VerProvidenciaViewer.init('panel', "
            '{"url":"https://foo.blob.core.windows.net/doc.pdf?sv=x&sig=y",'
            '"filename":"doc.pdf"});'
            "</script></html>"
        ),
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


@responses.activate
def test_download_stores_the_document_in_its_original_format_without_converting(tmp_path):
    """Every source stores documents exactly as downloaded — no format conversion
    happens at storage time (that only ever happens on demand, for previews, via
    convert_to_pdf_via_libreoffice). converted_format must stay None and both the
    storage key and content_type must reflect the original file untouched."""
    responses.add(
        responses.GET,
        "https://example.com/file.pdf",
        body=b"%PDF-1.4 contenido de prueba",
        headers={"Content-Type": "application/pdf"},
        status=200,
    )
    downloader = Downloader()
    result = downloader.download(_doc(), tmp_path)

    assert result.converted_format is None
    assert result.storage_key.endswith(".pdf")
    assert result.local_path.suffix == ".pdf"
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


def test_check_remote_content_length_passes_verify_false_through(monkeypatch):
    # Un host con la cadena TLS incompleta (ssf.gov.co, constitucional, cndj) marca
    # link["verify"] = False; el HEAD barato debe honrarlo o siempre falla el
    # handshake y el documento se re-descarga completo en cada corrida.
    captured = {}

    class _Resp:
        status_code = 200
        headers = {"Content-Length": "123"}

    def _fake_head(url, **kwargs):
        captured.update(kwargs)
        return _Resp()

    monkeypatch.setattr("core.downloader.requests.head", _fake_head)

    assert check_remote_content_length("https://x/f.pdf", verify=False) == 123
    assert captured["verify"] is False


def test_check_remote_content_length_verify_defaults_to_true(monkeypatch):
    captured = {}

    class _Resp:
        status_code = 200
        headers = {}

    def _fake_head(url, **kwargs):
        captured.update(kwargs)
        return _Resp()

    monkeypatch.setattr("core.downloader.requests.head", _fake_head)

    check_remote_content_length("https://x/f.pdf")
    assert captured.get("verify", True) is True


# --- Tope de tamaño de las descargas ----------------------------------------
# Un archivo enorme (por error del sitio o a propósito) no debe poder llenar el
# disco del servidor: la descarga se corta apenas pasa el tope y el temporal se
# borra. Se configura con MAX_DOWNLOAD_MB (ver core/config.py).

from core.verificacion_archivos import ArchivoNoPermitido


@responses.activate
def test_download_rechaza_sin_descargar_si_el_servidor_anuncia_un_tamano_mayor_al_tope(tmp_path):
    responses.add(
        responses.GET, "https://example.com/file.pdf",
        body=b"x" * 50, headers={"Content-Type": "application/pdf", "Content-Length": "5000"}, status=200,
    )

    with pytest.raises(ArchivoNoPermitido, match="tamaño máximo"):
        Downloader(max_bytes=1000).download(_doc(), tmp_path)

    assert list(tmp_path.iterdir()) == []


@responses.activate
def test_download_corta_y_borra_el_temporal_si_el_archivo_pasa_el_tope_sin_anunciarlo(tmp_path):
    responses.add(
        responses.GET, "https://example.com/file.pdf",
        body=b"x" * 5000, headers={"Content-Type": "application/pdf"}, status=200,
    )

    with pytest.raises(ArchivoNoPermitido, match="tamaño máximo"):
        Downloader(max_bytes=1000).download(_doc(), tmp_path)

    assert list(tmp_path.iterdir()) == []


@responses.activate
def test_download_no_reintenta_un_archivo_que_pasa_el_tope(tmp_path):
    responses.add(
        responses.GET, "https://example.com/file.pdf",
        body=b"x" * 5000, headers={"Content-Type": "application/pdf"}, status=200,
    )

    with pytest.raises(ArchivoNoPermitido):
        Downloader(max_bytes=1000).download(_doc(), tmp_path)

    assert len(responses.calls) == 1


@responses.activate
def test_download_acepta_un_archivo_justo_en_el_tope(tmp_path):
    responses.add(
        responses.GET, "https://example.com/file.pdf",
        body=b"x" * 1000, headers={"Content-Type": "application/pdf"}, status=200,
    )

    result = Downloader(max_bytes=1000).download(_doc(), tmp_path)

    assert result.file_size_bytes == 1000


def test_el_tope_por_defecto_sale_de_la_configuracion(monkeypatch):
    from core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_download_mb", 7)

    assert Downloader().max_bytes == 7 * 1024 * 1024


@responses.activate
def test_download_calcula_la_huella_digital_del_archivo(tmp_path):
    # SHA-256 del contenido, calculado mientras se descarga (sin volver a leer
    # el archivo): sirve para encontrar y rastrear un archivo que resulte malo.
    import hashlib

    responses.add(
        responses.GET, "https://example.com/file.pdf",
        body=b"%PDF-1.4 contenido", headers={"Content-Type": "application/pdf"}, status=200,
    )

    result = Downloader().download(_doc(), tmp_path)

    assert result.sha256 == hashlib.sha256(b"%PDF-1.4 contenido").hexdigest()


# --- 429 Too Many Requests (CSJ/Ojeador, nov 2026: ~10% de las descargas de
# un mes con 6 descargas en paralelo) --------------------------------------

@responses.activate
def test_download_espera_y_reintenta_un_429_respetando_retry_after(tmp_path, monkeypatch):
    import core.downloader as dl

    esperas = []
    monkeypatch.setattr(dl.time, "sleep", esperas.append)
    responses.add(responses.GET, "https://example.com/file.pdf", status=429, headers={"Retry-After": "7"})
    responses.add(responses.GET, "https://example.com/file.pdf", body=b"ok", headers={"Content-Type": "application/pdf"})

    result = Downloader().download(_doc(), tmp_path)

    assert result.local_path.read_bytes() == b"ok"
    assert esperas == [7]


@responses.activate
def test_download_429_sin_retry_after_espera_un_tiempo_creciente(tmp_path, monkeypatch):
    import core.downloader as dl

    esperas = []
    monkeypatch.setattr(dl.time, "sleep", esperas.append)
    responses.add(responses.GET, "https://example.com/file.pdf", status=429)
    responses.add(responses.GET, "https://example.com/file.pdf", status=429)
    responses.add(responses.GET, "https://example.com/file.pdf", body=b"ok", headers={"Content-Type": "application/pdf"})

    Downloader().download(_doc(), tmp_path)

    assert len(esperas) == 2 and esperas[0] > 0 and esperas[1] > esperas[0]


@responses.activate
def test_download_se_rinde_tras_varios_429(tmp_path, monkeypatch):
    import core.downloader as dl

    monkeypatch.setattr(dl.time, "sleep", lambda _s: None)
    for _ in range(dl._MAX_ESPERAS_429 + 1):
        responses.add(responses.GET, "https://example.com/file.pdf", status=429)

    with pytest.raises(requests.exceptions.HTTPError):
        Downloader().download(_doc(), tmp_path)
    assert len(responses.calls) == dl._MAX_ESPERAS_429 + 1


@responses.activate
def test_download_retry_after_exagerado_se_acota(tmp_path, monkeypatch):
    import core.downloader as dl

    esperas = []
    monkeypatch.setattr(dl.time, "sleep", esperas.append)
    responses.add(responses.GET, "https://example.com/file.pdf", status=429, headers={"Retry-After": "3600"})
    responses.add(responses.GET, "https://example.com/file.pdf", body=b"ok", headers={"Content-Type": "application/pdf"})

    Downloader().download(_doc(), tmp_path)

    assert esperas == [dl._ESPERA_429_MAX_SEG]


@responses.activate
def test_download_cancelar_durante_una_espera_por_429_corta_de_inmediato(tmp_path, monkeypatch):
    # Revisión final: time.sleep ignoraba la cancelación; una corrida
    # cancelada podía quedar hasta ~5 min por documento esperando.
    import threading

    import core.downloader as dl

    monkeypatch.setattr(dl.time, "sleep", lambda _s: pytest.fail("no debe dormir sin mirar la cancelación"))
    parar = threading.Event()
    parar.set()
    responses.add(responses.GET, "https://example.com/file.pdf", status=429, headers={"Retry-After": "30"})

    with pytest.raises(InterruptedError):
        Downloader().download(_doc(), tmp_path, stop_event=parar)
    assert len(responses.calls) == 1


@responses.activate
def test_download_sharepoint_compartido_opens_share_link_then_file_with_same_session(tmp_path):
    # Cámara de Comercio de Barranquilla: OneDrive compartido "cualquier persona
    # con el vínculo". El archivo sólo baja con la cookie anónima FedAuth que
    # deja el enlace compartido; sin ella, SharePoint manda al inicio de sesión.
    compartido = "https://tenant-my.sharepoint.com/:f:/g/personal/x/AbC?e=1"
    archivo = "https://tenant-my.sharepoint.com/personal/x/_layouts/15/download.aspx?UniqueId=abc"
    responses.add(
        responses.GET, compartido, status=200, body="<html>onedrive</html>",
        headers={"Set-Cookie": "FedAuth=galleta; path=/; secure; HttpOnly"},
    )

    def _archivo(request):
        if "FedAuth=galleta" not in (request.headers.get("Cookie") or ""):
            return (200, {"Content-Type": "text/html; charset=utf-8"}, "<html>Inicie sesión</html>")
        return (200, {"Content-Type": "application/pdf",
                      "Content-Disposition": 'attachment; filename="laudo.pdf"'}, b"%PDF-1.4 laudo")

    responses.add_callback(responses.GET, archivo, callback=_archivo)
    doc = _doc(method="sharepoint_compartido", url=archivo)
    doc.link["compartido"] = compartido

    result = Downloader().download(doc, tmp_path)

    assert result.local_path.read_bytes() == b"%PDF-1.4 laudo"
    assert result.content_type == "application/pdf"
    assert [c.request.url for c in responses.calls] == [compartido, archivo]


@responses.activate
def test_download_sharepoint_compartido_without_cookie_fails_instead_of_saving_login_page(tmp_path):
    compartido = "https://tenant-my.sharepoint.com/:f:/g/personal/x/AbC?e=1"
    archivo = "https://tenant-my.sharepoint.com/personal/x/_layouts/15/download.aspx?UniqueId=abc"
    responses.add(responses.GET, compartido, status=200, body="<html>sin cookie</html>")
    responses.add(
        responses.GET, archivo, status=200, body="<html>Inicie sesión en su cuenta</html>",
        headers={"Content-Type": "text/html; charset=utf-8"},
    )
    doc = _doc(method="sharepoint_compartido", url=archivo)
    doc.link["compartido"] = compartido

    with pytest.raises(FileNotFoundError):
        Downloader().download(doc, tmp_path)
    assert list(tmp_path.iterdir()) == []


# Función Pública (funcion_publica): su servidor anuncia un Content-Length que
# no cuenta los dos bytes "\t\n" que antepone al PDF, así que todos llegan sin
# los dos últimos bytes ("%%E" en vez de "%%EOF"). Con link["completar_fin_pdf"]
# el descargador completa solo esa marca; sin la bandera el PDF se rechaza.
_PDF_CORTADO = b"\t\n%PDF-1.4\n1 0 obj<<>>endobj\nxref\n0 1\ntrailer<<>>\nstartxref\n9\n%%E"


def _doc_completar(body, completar=True):
    doc = _doc(url="https://www.funcionpublica.gov.co/eva/gestornormativo/norma_pdf.php?i=1")
    if completar:
        doc.link["completar_fin_pdf"] = True
    responses.add(
        responses.GET, doc.link["url"], body=body,
        headers={"Content-Type": "application/pdf"}, status=200,
    )
    return doc


@pytest.mark.verificar_archivos
@responses.activate
def test_download_completes_cut_pdf_end_marker_when_link_asks(tmp_path):
    import hashlib

    result = Downloader().download(_doc_completar(_PDF_CORTADO), tmp_path)

    contenido = result.local_path.read_bytes()
    assert contenido == _PDF_CORTADO + b"OF"
    assert result.file_size_bytes == len(contenido)
    assert result.sha256 == hashlib.sha256(contenido).hexdigest()


@pytest.mark.verificar_archivos
@responses.activate
def test_download_completes_end_marker_cut_by_one_byte(tmp_path):
    result = Downloader().download(_doc_completar(_PDF_CORTADO + b"O"), tmp_path)

    assert result.local_path.read_bytes().endswith(b"startxref\n9\n%%EOF")


@pytest.mark.verificar_archivos
@responses.activate
def test_download_leaves_complete_pdf_untouched_when_link_asks(tmp_path):
    completo = _PDF_CORTADO + b"OF"

    result = Downloader().download(_doc_completar(completo), tmp_path)

    assert result.local_path.read_bytes() == completo


@pytest.mark.verificar_archivos
@responses.activate
def test_download_still_rejects_cut_pdf_without_the_flag(tmp_path):
    with pytest.raises(ArchivoNoPermitido, match="marca de final"):
        Downloader().download(_doc_completar(_PDF_CORTADO, completar=False), tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.verificar_archivos
@responses.activate
def test_download_does_not_invent_end_of_truly_truncated_pdf(tmp_path):
    # Cortado a la mitad: no termina en "%%E"/"%%EO" tras startxref, así que
    # no se completa nada y la verificación lo sigue rechazando.
    with pytest.raises(ArchivoNoPermitido, match="marca de final"):
        Downloader().download(_doc_completar(_PDF_CORTADO[:30]), tmp_path)
