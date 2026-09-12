from app.rate_limit import InMemoryRateLimiter


def test_limiter_bounds_clients_and_recovers_after_window() -> None:
    now = [0.0]
    limiter = InMemoryRateLimiter(
        limit=1,
        window_seconds=60,
        max_clients=2,
        clock=lambda: now[0],
    )

    assert limiter.allow("a")
    assert limiter.allow("b")
    assert not limiter.allow("c")

    now[0] = 61.0
    assert limiter.allow("c")
