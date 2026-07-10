import requests

from core.storage import presigned_url, upload_file
from tests.conftest import TEST_S3_BUCKET


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
