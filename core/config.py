from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://iurisync:iurisync@localhost:5432/iurisync"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "iurisync-documents"
    s3_region: str = "us-east-1"
    api_key_header: str = "X-API-Key"


@lru_cache
def get_settings() -> Settings:
    return Settings()
