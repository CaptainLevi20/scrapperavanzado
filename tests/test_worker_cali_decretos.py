from pathlib import Path

import pytest
import responses

import worker.tasks as tasks

_PDF_BYTES = b"%PDF-1.6\n" + b"x" * 5000
_HTML_BYTES = b"<html><body>error 404</body></html>"


@pytest.fixture(autouse=True)
def _sin_esperas(monkeypatch):
    # Ruling 1: _descargar_un_pdf llama time.sleep directamente (no recibe un
    # parametro `dormir`), asi que el backoff se neutraliza parcheando el modulo.
    monkeypatch.setattr(tasks.time, "sleep", lambda *_a: None)


@responses.activate
def test_descargar_un_pdf_http_success_moves_file(tmp_path):
    responses.add(responses.GET, "https://x.test/a.pdf", body=_PDF_BYTES, status=200)
    destino = tmp_path / "out" / "D_ALCACALI_0001_1974.pdf"
    motivo = tasks._descargar_un_pdf("https://x.test/a.pdf", destino, tmp_path)
    assert motivo is None
    assert destino.read_bytes() == _PDF_BYTES


@responses.activate
def test_descargar_un_pdf_non_pdf_body_fails_after_retries(tmp_path):
    responses.add(responses.GET, "https://x.test/b.pdf", body=_HTML_BYTES, status=200)
    responses.add(responses.GET, "https://x.test/b.pdf", body=_HTML_BYTES, status=200)
    responses.add(responses.GET, "https://x.test/b.pdf", body=_HTML_BYTES, status=200)
    responses.add(responses.GET, "https://x.test/b.pdf", body=_HTML_BYTES, status=200)
    destino = tmp_path / "out" / "x.pdf"
    motivo = tasks._descargar_un_pdf("https://x.test/b.pdf", destino, tmp_path)
    assert motivo == "no-es-pdf"
    assert not destino.exists()


@responses.activate
def test_descargar_un_pdf_http_error_then_success(tmp_path):
    responses.add(responses.GET, "https://x.test/c.pdf", status=503)
    responses.add(responses.GET, "https://x.test/c.pdf", body=_PDF_BYTES, status=200)
    destino = tmp_path / "out" / "c.pdf"
    motivo = tasks._descargar_un_pdf("https://x.test/c.pdf", destino, tmp_path)
    assert motivo is None
    assert destino.read_bytes() == _PDF_BYTES


def test_descargar_un_pdf_ftp_failure_reports_ftp_no_disponible(tmp_path, monkeypatch):
    def _boom(url, destino_tmp):
        raise OSError("ftp unreachable")

    monkeypatch.setattr(tasks, "_descargar_ftp", _boom)
    destino = tmp_path / "out" / "d.pdf"
    motivo = tasks._descargar_un_pdf(
        "ftp://ftp.cali.gov.co/DECRETOS/1984/x.pdf", destino, tmp_path
    )
    assert motivo == "ftp-no-disponible"
