import time
from collections import OrderedDict
from threading import RLock
from typing import Callable


class PendingPlayers:
    """A bounded, expiring set of Discord usernames awaiting team assignment."""

    def __init__(
        self,
        *,
        ttl_seconds: int,
        max_size: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_size <= 0:
            raise ValueError("max_size must be positive")

        self._ttl_seconds = ttl_seconds
        self._max_size = max_size
        self._clock = clock
        self._players: OrderedDict[str, float] = OrderedDict()
        self._lock = RLock()

    def add(self, username: str) -> None:
        if not username:
            return

        with self._lock:
            now = self._clock()
            self._purge_expired(now)
            self._players.pop(username, None)
            self._players[username] = now

            while len(self._players) > self._max_size:
                self._players.popitem(last=False)

    def discard(self, username: str) -> None:
        with self._lock:
            self._players.pop(username, None)

    def to_list(self) -> list[str]:
        with self._lock:
            self._purge_expired(self._clock())
            return list(self._players)

    def __contains__(self, username: object) -> bool:
        if not isinstance(username, str):
            return False
        with self._lock:
            self._purge_expired(self._clock())
            return username in self._players

    def __len__(self) -> int:
        return len(self.to_list())

    def _purge_expired(self, now: float) -> None:
        expires_before = now - self._ttl_seconds
        while self._players:
            _, seen_at = next(iter(self._players.items()))
            if seen_at > expires_before:
                break
            self._players.popitem(last=False)
