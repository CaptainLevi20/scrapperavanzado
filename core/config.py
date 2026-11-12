from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://iurisync:iurisync@localhost:5432/iurisync"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint_url: str = "http://localhost:9000"
    # Only needed when the backend itself is reachable at a different address than
    # MinIO is from an end user's browser (e.g. the office deployment's Caddy
    # reverse proxy, see docs/guia-despliegue-sistemas.md) — presigned URLs are
    # generated against this host instead, while actual upload/download traffic
    # between the backend and MinIO still uses s3_endpoint_url directly.
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
    # Tope de tamaño de cada archivo descargado de una fuente, en MB. Un archivo
    # más grande se corta a mitad de la descarga y el documento queda fallido:
    # así un archivo enorme (error del sitio o malintencionado) no llena el disco.
    # 300 por los datos de producción (2026-11-05): de 80.037 documentos el 99,9 %
    # pesa menos de 11 MB; el más pesado legítimo es una sentencia RTF de la Corte
    # Constitucional de 206,5 MB. Un PDF de 819 MB del Tribunal de Bogotá queda fuera.
    max_download_mb: int = 300
    # Antivirus (ClamAV, servicio `clamav` del docker-compose). Cada archivo
    # descargado se revisa antes de guardarlo; si el antivirus no responde, el
    # documento NO se guarda. Los infectados van al bucket de cuarentena.
    antivirus_habilitado: bool = True
    clamav_host: str = "localhost"
    clamav_port: int = 3310
    # Un archivo de 300 MB (el tope) tarda en revisarse; holgado a propósito.
    clamav_timeout_segundos: float = 300
    s3_bucket_cuarentena: str = "iurisync-cuarentena"


@lru_cache
def get_settings() -> Settings:
    return Settings()
