from core.config import Settings, get_settings


def test_settings_have_expected_defaults():
    settings = Settings(_env_file=None)
    assert settings.s3_bucket == "iurisync-documents"
    assert settings.registration_code == "changeme"
    assert settings.scheduled_run_lookback_days == 3


def test_get_settings_is_cached():
    assert get_settings() is get_settings()
