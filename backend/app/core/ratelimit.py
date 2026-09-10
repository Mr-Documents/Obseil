"""Rate limiting for the endpoints worth brute-forcing.

Only *failed* attempts are counted, and only against the caller's own client
address. That second point is the design decision that matters: a counter keyed
on the submitted email would let anyone lock a victim out of their own account
by submitting bad passwords for it. Keying on the caller means an attacker can
only ever rate-limit themselves.

The trade-off is the other way round: an attacker spread across many addresses
is not stopped by this. Defending against that belongs at the proxy or WAF
layer, which can see the whole fleet; see ``docs/SECURITY_REVIEW.md``.
"""

from __future__ import annotations

import math
import threading
import time
from abc import ABC, abstractmethod
from collections import OrderedDict, deque
from collections.abc import Callable


class RateLimiter(ABC):
    """A failure counter over a sliding window.

    An interface rather than a concrete class because the in-memory
    implementation below is correct for exactly one process. Running more than
    one replica means moving the counters to shared storage, and that should be
    a change of implementation rather than a change of every caller.
    """

    @abstractmethod
    def retry_after(self, key: str) -> int | None:
        """Seconds until ``key`` may try again, or ``None`` if it may now."""

    @abstractmethod
    def record_failure(self, key: str) -> None:
        """Count one failed attempt against ``key``."""

    @abstractmethod
    def reset(self, key: str) -> None:
        """Forget ``key``'s failures, after a success."""


class InMemoryRateLimiter(RateLimiter):
    """A sliding-window counter held in this process's memory.

    Sliding rather than fixed-window: a fixed window lets an attacker send a
    full quota either side of the boundary, doubling the real rate at exactly
    the moment it matters.

    ``max_keys`` bounds memory. Without it, an attacker cycling source
    addresses would grow the table without limit - the rate limiter itself
    becoming the denial of service. Keys are evicted least-recently-used, which
    is safe here because an evicted key has, by definition, not been active.
    """

    def __init__(
        self,
        *,
        max_attempts: int,
        window_seconds: float,
        max_keys: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")

        self._max_attempts = max_attempts
        self._window = window_seconds
        self._max_keys = max_keys
        self._clock = clock
        self._lock = threading.Lock()
        # Ordered so the least recently touched key is the first to evict.
        self._failures: OrderedDict[str, deque[float]] = OrderedDict()

    def _live_failures(self, key: str, now: float) -> deque[float]:
        """``key``'s failures inside the window, dropping any that have aged out."""
        attempts = self._failures.get(key)
        if attempts is None:
            return deque()
        cutoff = now - self._window
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if not attempts:
            del self._failures[key]
            return deque()
        return attempts

    def retry_after(self, key: str) -> int | None:
        now = self._clock()
        with self._lock:
            attempts = self._live_failures(key, now)
            if len(attempts) < self._max_attempts:
                return None
            # The window clears when the oldest attempt still counted ages out.
            # Round up, so a caller that waits exactly this long is never early.
            return max(1, math.ceil(attempts[0] + self._window - now))

    def record_failure(self, key: str) -> None:
        now = self._clock()
        with self._lock:
            # Either the pruned deque still in the table, or a fresh empty one;
            # assigning back covers both without a second lookup.
            attempts = self._live_failures(key, now)
            attempts.append(now)
            self._failures[key] = attempts
            self._failures.move_to_end(key)
            while len(self._failures) > self._max_keys:
                self._failures.popitem(last=False)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def clear(self) -> None:
        """Forget every key. For tests and for an operator's reset."""
        with self._lock:
            self._failures.clear()


class NullRateLimiter(RateLimiter):
    """Counts nothing and allows everything, for when limiting is disabled."""

    def retry_after(self, key: str) -> int | None:  # noqa: ARG002 - null object
        return None

    def record_failure(self, key: str) -> None:  # noqa: ARG002 - null object
        return None

    def reset(self, key: str) -> None:  # noqa: ARG002 - null object
        return None
