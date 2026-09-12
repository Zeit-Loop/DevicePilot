from collections import deque
from collections.abc import Callable
from threading import Lock
from time import monotonic


class InMemoryRateLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: float,
        max_clients: int = 10_000,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if limit < 1 or window_seconds <= 0 or max_clients < 1:
            raise ValueError("limit, window_seconds, and max_clients must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self.clock = clock
        self._requests: dict[str, deque[float]] = {}
        self._lock = Lock()

    def allow(self, client_id: str) -> bool:
        now = self.clock()
        cutoff = now - self.window_seconds
        with self._lock:
            timestamps = self._requests.get(client_id)
            if timestamps is not None:
                self._prune(timestamps, cutoff)
                if not timestamps:
                    del self._requests[client_id]
                    timestamps = None

            if timestamps is None:
                if len(self._requests) >= self.max_clients:
                    self._remove_expired_clients(cutoff)
                if len(self._requests) >= self.max_clients:
                    return False
                timestamps = deque()
                self._requests[client_id] = timestamps

            if len(timestamps) >= self.limit:
                return False
            timestamps.append(now)
            return True

    @staticmethod
    def _prune(timestamps: deque[float], cutoff: float) -> None:
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()

    def _remove_expired_clients(self, cutoff: float) -> None:
        for key, timestamps in list(self._requests.items()):
            self._prune(timestamps, cutoff)
            if not timestamps:
                del self._requests[key]
