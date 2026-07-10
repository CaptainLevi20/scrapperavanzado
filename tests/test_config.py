from core.config import Settings, get_settings


def test_settings_have_expected_defaults():
    settings = Settings(_env_file=None)
    assert settings.s3_bucket == "iurisync-documents"
    assert settings.api_key_header == "X-API-Key"


def test_get_settings_is_cached():
    assert get_settings() is get_settings()
