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


def test_ensure_bucket_configures_cors_for_frontend_origin():
    from core.storage import _client, ensure_bucket

    ensure_bucket(TEST_S3_BUCKET)
    client = _client()
    cors = client.get_bucket_cors(Bucket=TEST_S3_BUCKET)

    allowed_origins = cors["CORSRules"][0]["AllowedOrigins"]
    assert "http://localhost:5173" in allowed_origins
    assert "GET" in cors["CORSRules"][0]["AllowedMethods"]
