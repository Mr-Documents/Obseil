"""The sliding-window failure counter.

The clock is injected throughout, so these assert real time-dependent
behaviour without a single `sleep` - a test that waits is a test nobody runs.
"""

from __future__ import annotations

import threading

import pytest

from app.core.ratelimit import InMemoryRateLimiter, NullRateLimiter


class FakeClock:
    """A monotonic clock the test moves by hand."""

    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def limiter(clock: FakeClock, *, max_attempts: int = 3, window: float = 60.0, max_keys: int = 100):
    return InMemoryRateLimiter(
        max_attempts=max_attempts,
        window_seconds=window,
        max_keys=max_keys,
        clock=clock,
    )


class TestCounting:
    def test_an_unknown_key_is_allowed(self) -> None:
        assert limiter(FakeClock()).retry_after("1.2.3.4") is None

    def test_failures_below_the_limit_do_not_block(self) -> None:
        rate = limiter(FakeClock(), max_attempts=3)
        for _ in range(2):
            rate.record_failure("1.2.3.4")
        assert rate.retry_after("1.2.3.4") is None

    def test_the_limit_blocks_on_the_nth_failure(self) -> None:
        rate = limiter(FakeClock(), max_attempts=3)
        for _ in range(3):
            rate.record_failure("1.2.3.4")
        assert rate.retry_after("1.2.3.4") is not None

    def test_keys_are_counted_independently(self) -> None:
        rate = limiter(FakeClock(), max_attempts=3)
        for _ in range(3):
            rate.record_failure("1.2.3.4")
        assert rate.retry_after("1.2.3.4") is not None
        assert rate.retry_after("5.6.7.8") is None

    def test_a_success_clears_the_count(self) -> None:
        rate = limiter(FakeClock(), max_attempts=3)
        for _ in range(2):
            rate.record_failure("1.2.3.4")
        rate.reset("1.2.3.4")
        for _ in range(2):
            rate.record_failure("1.2.3.4")
        assert rate.retry_after("1.2.3.4") is None


class TestTheWindowSlides:
    def test_the_block_lifts_once_the_window_passes(self) -> None:
        clock = FakeClock()
        rate = limiter(clock, max_attempts=3, window=60.0)
        for _ in range(3):
            rate.record_failure("1.2.3.4")

        clock.advance(59)
        assert rate.retry_after("1.2.3.4") is not None
        clock.advance(2)
        assert rate.retry_after("1.2.3.4") is None

    def test_retry_after_counts_down(self) -> None:
        clock = FakeClock()
        rate = limiter(clock, max_attempts=3, window=60.0)
        for _ in range(3):
            rate.record_failure("1.2.3.4")

        assert rate.retry_after("1.2.3.4") == 60
        clock.advance(30)
        assert rate.retry_after("1.2.3.4") == 30

    def test_retry_after_is_never_zero_while_blocked(self) -> None:
        """A caller told to wait 0 seconds would retry immediately and fail."""
        clock = FakeClock()
        rate = limiter(clock, max_attempts=3, window=60.0)
        for _ in range(3):
            rate.record_failure("1.2.3.4")

        clock.advance(59.9)
        assert rate.retry_after("1.2.3.4") == 1

    def test_old_failures_age_out_one_at_a_time(self) -> None:
        """The window slides; it does not reset wholesale at a boundary.

        A fixed window would let the two early failures below be forgotten
        together, handing the caller a fresh full quota in one step.
        """
        clock = FakeClock()
        rate = limiter(clock, max_attempts=3, window=60.0)

        rate.record_failure("1.2.3.4")
        clock.advance(30)
        rate.record_failure("1.2.3.4")
        clock.advance(29)
        rate.record_failure("1.2.3.4")
        assert rate.retry_after("1.2.3.4") is not None

        # Only the first failure has aged out, so one slot opens, not three.
        clock.advance(2)
        assert rate.retry_after("1.2.3.4") is None
        rate.record_failure("1.2.3.4")
        assert rate.retry_after("1.2.3.4") is not None


class TestMemoryIsBounded:
    def test_the_table_never_grows_past_max_keys(self) -> None:
        """Otherwise an attacker cycling addresses turns the limiter into the attack."""
        rate = limiter(FakeClock(), max_keys=10)
        for index in range(500):
            rate.record_failure(f"10.0.0.{index}")
        assert len(rate._failures) <= 10

    def test_eviction_keeps_the_most_recent_keys(self) -> None:
        clock = FakeClock()
        rate = limiter(clock, max_attempts=1, max_keys=2)
        rate.record_failure("first")
        rate.record_failure("second")
        rate.record_failure("third")

        assert rate.retry_after("first") is None  # evicted
        assert rate.retry_after("third") is not None

    def test_expired_keys_are_dropped_rather_than_kept_empty(self) -> None:
        clock = FakeClock()
        rate = limiter(clock, window=60.0)
        rate.record_failure("1.2.3.4")
        clock.advance(61)
        rate.retry_after("1.2.3.4")
        assert "1.2.3.4" not in rate._failures


class TestConfiguration:
    @pytest.mark.parametrize(
        ("attempts", "window"),
        [(0, 60.0), (-1, 60.0), (3, 0.0), (3, -5.0)],
    )
    def test_a_nonsensical_limit_is_refused_at_construction(
        self, attempts: int, window: float
    ) -> None:
        with pytest.raises(ValueError):
            InMemoryRateLimiter(max_attempts=attempts, window_seconds=window)

    def test_the_null_limiter_allows_everything(self) -> None:
        rate = NullRateLimiter()
        for _ in range(1_000):
            rate.record_failure("1.2.3.4")
        assert rate.retry_after("1.2.3.4") is None


def test_concurrent_failures_are_all_counted() -> None:
    """Route handlers are plain `def`, so FastAPI calls this from a threadpool.

    Without the lock, concurrent `record_failure` calls lose increments and the
    limit silently never trips.
    """
    rate = InMemoryRateLimiter(max_attempts=1_000, window_seconds=60.0)
    threads = [
        threading.Thread(target=lambda: [rate.record_failure("1.2.3.4") for _ in range(100)])
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(rate._failures["1.2.3.4"]) == 800
