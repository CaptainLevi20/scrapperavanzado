from pathlib import Path
from typing import Optional

import boto3
from botocore.client import Config as BotoConfig

from core.config import get_settings


def _client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
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


def presigned_url(bucket: str, key: str, expires_in: int = 3600) -> str:
    client = _client()
    return client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in
    )
