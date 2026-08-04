from pathlib import Path
from typing import Optional

import boto3
from botocore.client import Config as BotoConfig

from core.config import get_settings


def _client(endpoint_url: Optional[str] = None):
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url or settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=BotoConfig(signature_version="s3v4"),
    )


def ensure_bucket(bucket: str) -> None:
    client = _client()
    existing = [b["Name"] for b in client.list_buckets().get("Buckets", [])]
    if bucket not in existing:
        client.create_bucket(Bucket=bucket)


def upload_file(
    local_path: Path, key: str, bucket: Optional[str] = None, content_type: Optional[str] = None
) -> tuple[str, str]:
    settings = get_settings()
    bucket = bucket or settings.s3_bucket
    ensure_bucket(bucket)
    client = _client()
    extra_args = {"ContentType": content_type} if content_type else {}
    client.upload_file(str(local_path), bucket, key, ExtraArgs=extra_args)
    return bucket, key


def presigned_url(
    bucket: str, key: str, expires_in: int = 3600, response_content_disposition: Optional[str] = None
) -> str:
    # Signed against s3_public_endpoint_url when set (e.g. the office deployment's
    # Caddy reverse proxy fronting MinIO) — the browser fetching this URL is not
    # necessarily on the same machine as the backend, so it needs a host it can
    # actually reach, distinct from the internal endpoint upload_file/download_file
    # use for backend<->MinIO traffic.
    settings = get_settings()
    client = _client(endpoint_url=settings.s3_public_endpoint_url)
    params = {"Bucket": bucket, "Key": key}
    if response_content_disposition:
        params["ResponseContentDisposition"] = response_content_disposition
    return client.generate_presigned_url("get_object", Params=params, ExpiresIn=expires_in)


def download_file(bucket: str, key: str, local_path: Path) -> None:
    client = _client()
    client.download_file(bucket, key, str(local_path))


def delete_object(bucket: str, key: str) -> None:
    client = _client()
    client.delete_object(Bucket=bucket, Key=key)


def rename_object(bucket: str, old_key: str, new_key: str) -> None:
    """Server-side rename (copy + delete) — the object's bytes never leave
    MinIO/S3 through this process, unlike a download_file + upload_file
    round-trip."""
    if old_key == new_key:
        return
    client = _client()
    client.copy_object(Bucket=bucket, CopySource={"Bucket": bucket, "Key": old_key}, Key=new_key)
    delete_object(bucket, old_key)
