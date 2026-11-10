import time

from app.core.ratelimit import RateLimiter


def test_limiter_allows_until_limit_then_blocks():
    lim = RateLimiter(limit=3, window_seconds=60)
    assert [lim.allow("ip") for _ in range(3)] == [True, True, True]
    assert lim.allow("ip") is False


def test_limiter_resets_after_window():
    lim = RateLimiter(limit=2, window_seconds=1)
    assert lim.allow("ip")
    assert lim.allow("ip")
    assert not lim.allow("ip")
    time.sleep(1.1)
    assert lim.allow("ip")


def test_limiter_keys_are_independent():
    lim = RateLimiter(limit=1, window_seconds=60)
    assert lim.allow("a")
    assert lim.allow("b")
    assert not lim.allow("a")
