"""
Login throttling per client address.

An address that reaches LOGIN_MAX_ATTEMPTS attempts within LOGIN_INTERVAL
seconds is refused until the oldest attempt is older than the interval. A
successful login clears the address's count, so only failures accumulate.

The attempt is recorded before the password is checked, in the same locked call
that checks the limit. The login route runs in FastAPI's thread pool, so
requests sent in parallel would otherwise all pass the check before any failure
was recorded.

The counts live in this process: a restart clears them, and several workers
would each keep their own.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict


class LoginThrottle:
    """Counts login attempts per key over the last ``interval`` seconds."""

    def __init__(self, maxAttempts: int, interval: int) -> None:
        self.maxAttempts = maxAttempts
        self.interval = interval
        self._attempts: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        """False when maxAttempts is 0 or less."""
        return self.maxAttempts > 0

    def tryAttempt(self, key: str, now: float | None = None) -> bool:
        """Records an attempt for ``key`` and returns True, or returns False when the limit is reached."""
        if not self.enabled:
            return True
        now = time.monotonic() if now is None else now
        with self._lock:
            kept = [at for at in self._attempts[key] if now - at < self.interval]
            if len(kept) >= self.maxAttempts:
                self._attempts[key] = kept
                return False
            kept.append(now)
            self._attempts[key] = kept
            return True

    def reset(self, key: str) -> None:
        """Clears the attempts of ``key``, after a successful login."""
        with self._lock:
            self._attempts.pop(key, None)

    def clear(self) -> None:
        """Clears every key."""
        with self._lock:
            self._attempts.clear()
