import threading
import time
from collections import defaultdict, deque

# In-process sliding-window rate limiter. Deliberately not Redis-backed: the API
# runs as a single uvicorn process (no --workers flag in the Dockerfile), so
# per-process in-memory state is already correct and avoids adding a new
# app-level dependency on Redis (today it's only used as the Celery broker). A
# multi-process or multi-instance deployment would need a shared store instead.
_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def check_rate_limit(key: str, limit: int, window_seconds: float) -> bool:
    """Returns True if this call is within the limit (and records it), False if
    the caller has already hit `limit` calls for `key` within the trailing
    `window_seconds`."""
    now = time.monotonic()
    with _lock:
        hits = _hits[key]
        while hits and now - hits[0] > window_seconds:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True


def reset_rate_limits() -> None:
    """Clears all recorded hits — used by the test suite so rate limiting from
    one test can't bleed into another."""
    with _lock:
        _hits.clear()
