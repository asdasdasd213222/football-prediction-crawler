from __future__ import annotations

from multisite_crawler.resilience import (
    CircuitBreaker,
    FixedWindowRateLimiter,
    RedisCircuitBreaker,
    ResponseFailure,
    RetryPolicy,
    run_with_retry,
    should_request_human_review,
)


def test_retry_policy_retries_transient_failures_with_bounded_jitter() -> None:
    policy = RetryPolicy(max_attempts=3, base_delay_seconds=2, max_delay_seconds=30)

    assert policy.should_retry(status_code=503, error=None) is True
    assert policy.should_retry(status_code=None, error=ConnectionResetError()) is True
    assert policy.delay_seconds(2, random_value=0.5) == 4


def test_retry_policy_does_not_retry_access_denials_and_honors_retry_after() -> None:
    policy = RetryPolicy(max_attempts=3, base_delay_seconds=2, max_delay_seconds=30)

    assert policy.should_retry(status_code=401, error=None) is False
    assert policy.should_retry(status_code=403, error=None) is False
    assert policy.retry_after_seconds("7") == 7


def test_access_control_content_requires_human_review() -> None:
    assert should_request_human_review("CAPTCHA required") is True
    assert should_request_human_review("normal response") is False


def test_circuit_breakers_are_isolated_and_allow_one_half_open_probe() -> None:
    breaker = CircuitBreaker(failure_threshold=2, recovery_seconds=60)

    breaker.record_failure("one", now=0)
    breaker.record_failure("one", now=1)
    assert breaker.allow_request("one", now=2) is False
    assert breaker.allow_request("two", now=2) is True
    assert breaker.allow_request("one", now=61) is True
    assert breaker.allow_request("one", now=61) is False


def test_rate_limits_are_isolated_per_source() -> None:
    limiter = FixedWindowRateLimiter(max_requests=2, window_seconds=60)

    assert limiter.allow("one", now=0) is True
    assert limiter.allow("one", now=1) is True
    assert limiter.allow("one", now=2) is False
    assert limiter.allow("two", now=2) is True
    assert limiter.allow("one", now=61) is True


def test_retry_executor_honors_retry_after_and_stops_on_captcha() -> None:
    policy = RetryPolicy(max_attempts=3, base_delay_seconds=2, max_delay_seconds=30)
    waits: list[float] = []
    attempts = 0

    def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ResponseFailure(429, retry_after="7")
        return "ok"

    assert (
        run_with_retry(
            policy, flaky, sleep_seconds=waits.append, random_value=lambda: 0.5
        )
        == "ok"
    )
    assert waits == [7]


def test_redis_circuit_state_persists_by_source() -> None:
    class Store:
        values: dict[str, str] = {}

        def get(self, key: str) -> str | None:
            return self.values.get(key)

        def set(self, key: str, value: str, *, ex: int | None = None) -> None:
            del ex
            self.values[key] = value

    first = RedisCircuitBreaker(Store(), threshold=2, recovery_seconds=60)
    first.record_failure("one", 0)
    first.record_failure("one", 1)
    second = RedisCircuitBreaker(first.store, threshold=2, recovery_seconds=60)

    assert second.allow_request("one", 2) is False
    assert second.allow_request("two", 2) is True
