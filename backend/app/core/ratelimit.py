import threading
import time


class RateLimiter:
    """Fixed-window, in-process rate limiter keyed by a string (e.g. client IP).

    Lightweight guard for auth endpoints. Counts are kept per key in a fixed
    time window; when the window elapses the counter resets. This is an
    in-memory guard, not a distributed one — sufficient for a single-process
    MVP deployment.
    """

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._window_start: dict[str, float] = {}
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            start = self._window_start.get(key)
            if start is None or now - start >= self.window:
                self._window_start[key] = now
                self._counts[key] = 1
                return True
            count = self._counts.get(key, 0)
            if count >= self.limit:
                return False
            self._counts[key] = count + 1
            return True

    def reset(self) -> None:
        with self._lock:
            self._window_start.clear()
            self._counts.clear()
