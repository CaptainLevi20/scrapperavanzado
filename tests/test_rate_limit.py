import time

from core.rate_limit import check_rate_limit, reset_rate_limits


def test_check_rate_limit_allows_up_to_the_limit_then_blocks():
    reset_rate_limits()
    key = "test-key-1"

    for _ in range(3):
        assert check_rate_limit(key, limit=3, window_seconds=60) is True

    assert check_rate_limit(key, limit=3, window_seconds=60) is False


def test_check_rate_limit_tracks_keys_independently():
    reset_rate_limits()

    for _ in range(3):
        assert check_rate_limit("key-a", limit=3, window_seconds=60) is True
    assert check_rate_limit("key-a", limit=3, window_seconds=60) is False

    # A different key must not be affected by key-a's usage.
    assert check_rate_limit("key-b", limit=3, window_seconds=60) is True


def test_check_rate_limit_allows_again_once_the_window_elapses():
    reset_rate_limits()
    key = "test-key-window"

    assert check_rate_limit(key, limit=1, window_seconds=0.05) is True
    assert check_rate_limit(key, limit=1, window_seconds=0.05) is False

    time.sleep(0.1)

    assert check_rate_limit(key, limit=1, window_seconds=0.05) is True
