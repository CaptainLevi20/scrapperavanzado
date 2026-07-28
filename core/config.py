from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://iurisync:iurisync@localhost:5432/iurisync"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint_url: str = "http://localhost:9000"
    # Only needed when the backend itself is reachable at a different address than
    # MinIO is from an end user's browser (e.g. an ngrok demo tunnel) — presigned
    # URLs are generated against this host instead, while actual upload/download
    # traffic between the backend and MinIO still uses s3_endpoint_url directly.
    s3_public_endpoint_url: str | None = None
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "iurisync-documents"
    s3_region: str = "us-east-1"
    cors_origins: str = "http://localhost:5173"
    registration_code: str = "changeme"
    # The scheduled daily run has no natural "yesterday" concept of its own — it
    # always asks each source for [today - N days, today] so documents published
    # earlier in a day the beat job already ran for (or missed entirely) still get
    # picked up on the next run, instead of only ever seeing an empty "today".
    scheduled_run_lookback_days: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
