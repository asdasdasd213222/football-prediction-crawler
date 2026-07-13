"""Site-neutral retry, review, and circuit-breaker policy primitives."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from socket import gaierror
from typing import Protocol


class RedisStateStore(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, *, ex: int | None = None) -> object: ...


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float

    def should_retry(self, *, status_code: int | None, error: Exception | None) -> bool:
        if status_code in {401, 403}:
            return False
        return status_code in {429, 502, 503} or isinstance(
            error, (ConnectionError, TimeoutError, gaierror)
        )

    def delay_seconds(self, attempt: int, *, random_value: float) -> float:
        delay = float(
            min(
                self.max_delay_seconds,
                self.base_delay_seconds * 2 ** (attempt - 1),
            )
        )
        return delay * (0.5 + random_value)

    def retry_after_seconds(self, value: str | None) -> int | None:
        return int(value) if value is not None and value.isdigit() else None


@dataclass(frozen=True)
class ResponseFailure(Exception):
    """A non-success HTTP response evaluated by the shared policy."""

    status_code: int
    retry_after: str | None = None
    body: str = ""


def run_with_retry[T](
    policy: RetryPolicy,
    operation: Callable[[], T],
    *,
    sleep_seconds: Callable[[float], None],
    random_value: Callable[[], float],
) -> T:
    """Execute one operation with bounded, policy-controlled retries."""
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return operation()
        except ResponseFailure as error:
            if should_request_human_review(error.body) or not policy.should_retry(
                status_code=error.status_code, error=None
            ):
                raise
            if attempt == policy.max_attempts:
                raise
            delay = policy.retry_after_seconds(error.retry_after)
            sleep_seconds(
                float(delay)
                if delay is not None
                else policy.delay_seconds(attempt, random_value=random_value())
            )
        except (ConnectionError, TimeoutError, gaierror):
            if attempt == policy.max_attempts:
                raise
            sleep_seconds(policy.delay_seconds(attempt, random_value=random_value()))
    raise RuntimeError("retry loop exhausted")


def should_request_human_review(body: str) -> bool:
    """Identify access-control prompts without attempting to bypass them."""
    lowered = body.lower()
    return "captcha" in lowered or "access denied" in lowered


@dataclass
class _CircuitState:
    failures: int = 0
    opened_at: float | None = None
    half_open: bool = False


@dataclass
class CircuitBreaker:
    failure_threshold: int
    recovery_seconds: float
    _states: dict[str, _CircuitState] = field(default_factory=dict)

    def allow_request(self, source_id: str, *, now: float) -> bool:
        state = self._states.setdefault(source_id, _CircuitState())
        if state.opened_at is None:
            return True
        if now - state.opened_at < self.recovery_seconds:
            return False
        if state.half_open:
            return False
        state.half_open = True
        return True

    def record_failure(self, source_id: str, *, now: float) -> None:
        state = self._states.setdefault(source_id, _CircuitState())
        state.failures += 1
        if state.failures >= self.failure_threshold:
            state.opened_at = now
            state.half_open = False

    def record_success(self, source_id: str) -> None:
        self._states[source_id] = _CircuitState()


@dataclass
class FixedWindowRateLimiter:
    """Per-source fixed-window limiter; Redis persistence is added at task edge."""

    max_requests: int
    window_seconds: float
    _windows: dict[str, tuple[float, int]] = field(default_factory=dict)

    def allow(self, source_id: str, *, now: float) -> bool:
        window_start, count = self._windows.get(source_id, (now, 0))
        if now - window_start >= self.window_seconds:
            window_start, count = now, 0
        if count >= self.max_requests:
            return False
        self._windows[source_id] = (window_start, count + 1)
        return True


class RedisCircuitBreaker:
    """Redis-persisted circuit state, isolated by source id."""

    def __init__(
        self, store: RedisStateStore, threshold: int, recovery_seconds: int
    ) -> None:
        self.store, self.threshold, self.recovery_seconds = (
            store,
            threshold,
            recovery_seconds,
        )

    def allow_request(self, source_id: str, now: float) -> bool:
        state = json.loads(self.store.get(f"circuit:{source_id}") or "{}")
        opened = state.get("opened")
        if opened is None:
            return True
        if now - float(opened) < self.recovery_seconds:
            return False
        if state.get("half_open"):
            return False
        state["half_open"] = True
        self.store.set(
            f"circuit:{source_id}", json.dumps(state), ex=self.recovery_seconds
        )
        return True

    def record_failure(self, source_id: str, now: float) -> None:
        key = f"circuit:{source_id}"
        state = json.loads(self.store.get(key) or "{}")
        failures = int(state.get("failures", 0)) + 1
        self.store.set(
            key,
            json.dumps(
                {"failures": failures, "opened": now}
                if failures >= self.threshold
                else {"failures": failures}
            ),
            ex=self.recovery_seconds,
        )

    def record_success(self, source_id: str) -> None:
        self.store.set(f"circuit:{source_id}", "{}", ex=1)
