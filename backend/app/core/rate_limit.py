import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """In-memory per-key limiter: at most `limit` hits per `window_seconds`.

    State lives in one process, so the limit is per API instance. That is
    enough for a single free-tier instance; multiple instances would need a
    shared store (Postgres or Redis), which is not justified yet.
    """

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window_seconds:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            if len(self._hits) > 10_000:  # bound memory under many distinct clients
                self._evict_idle(now)
            return True

    def _evict_idle(self, now: float) -> None:
        idle = [k for k, h in self._hits.items() if not h or h[-1] <= now - self.window_seconds]
        for key in idle:
            del self._hits[key]
