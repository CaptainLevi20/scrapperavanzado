import requests

from core.storage import _client, presigned_url, upload_file
from tests.conftest import TEST_S3_BUCKET


def test_client_is_reused_across_calls_with_the_same_endpoint():
    """Regresión: _client() creaba un cliente boto3 (y su propio pool de
    conexiones) nuevo en cada llamada — con cientos/miles de llamadas
    seguidas (ej. el backfill de storage_sync) esto acumula conexiones más
    rápido de lo que el sistema operativo las cierra, poniendo todo cada vez
    más lento. Debe reutilizar el mismo cliente."""
    first = _client()
    second = _client()
    assert first is second


def test_client_caches_separately_per_endpoint_url():
    default_client = _client()
    other_client = _client(endpoint_url="http://otro-endpoint-de-prueba:9000")
    assert default_client is not other_client
    assert _client(endpoint_url="http://otro-endpoint-de-prueba:9000") is other_client


def test_upload_file_and_presigned_url_roundtrip(tmp_path):
    local_file = tmp_path / "doc.txt"
    local_file.write_text("contenido de prueba")

    bucket, key = upload_file(local_file, "test/doc.txt", bucket=TEST_S3_BUCKET, content_type="text/plain")

    url = presigned_url(bucket, key)
    response = requests.get(url, timeout=10)
    assert response.status_code == 200
    assert response.text == "contenido de prueba"


def test_presigned_url_response_allows_cross_origin_read(tmp_path):
    file_path = tmp_path / "cors-check.txt"
    file_path.write_text("contenido de prueba")
    bucket, key = upload_file(file_path, "cors-check.txt", bucket=TEST_S3_BUCKET)
    url = presigned_url(bucket, key)

    response = requests.get(url, headers={"Origin": "http://localhost:5173"}, timeout=10)

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") in ("*", "http://localhost:5173")


def test_presigned_url_with_response_content_disposition_sets_the_header(tmp_path):
    """A plain fetch()+Blob throws away Content-Disposition, so when the frontend
    points an iframe straight at a presigned URL instead (to let the browser's own
    pdf viewer offer a correct download filename), the header has to come from the
    signed request itself via ResponseContentDisposition."""
    local_file = tmp_path / "doc.pdf"
    local_file.write_text("contenido de prueba")
    bucket, key = upload_file(local_file, "test/content-disposition.pdf", bucket=TEST_S3_BUCKET, content_type="application/pdf")

    url = presigned_url(bucket, key, response_content_disposition='inline; filename="Mi Documento.pdf"')
    response = requests.get(url, timeout=10)

    assert response.status_code == 200
    assert response.headers.get("content-disposition") == 'inline; filename="Mi Documento.pdf"'


def test_download_file_writes_the_object_to_the_given_path(tmp_path):
    from core.storage import download_file

    local_file = tmp_path / "original.txt"
    local_file.write_text("contenido original")
    bucket, key = upload_file(local_file, "test/download-roundtrip.txt", bucket=TEST_S3_BUCKET, content_type="text/plain")

    destination = tmp_path / "downloaded.txt"
    download_file(bucket, key, destination)

    assert destination.read_text() == "contenido original"
