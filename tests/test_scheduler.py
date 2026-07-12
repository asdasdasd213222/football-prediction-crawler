from __future__ import annotations

from datetime import datetime, timedelta

from multisite_crawler.config import (
    CircuitBreakerConfig,
    CrawlerConfig,
    QueueName,
    RequestConfig,
    RetryConfig,
    SourceConfig,
    SourceMode,
)
from multisite_crawler.scheduler import (
    SchedulerService,
    SchedulerState,
    next_run_at,
    should_dispatch,
)
from multisite_crawler.scheduler_service import configured_sources, run_cycle


def test_next_run_uses_beijing_local_time() -> None:
    current = datetime(2026, 7, 11, 10, 0, 0)

    assert next_run_at(current, 60) == datetime(2026, 7, 11, 10, 1, 0)


def test_paused_source_is_not_dispatched() -> None:
    state = SchedulerState(next_run_at=datetime(2026, 7, 11, 10, 0, 0), paused=True)

    assert should_dispatch(state, datetime(2026, 7, 11, 10, 1, 0)) is False


def test_overdue_source_dispatches_once_after_restart() -> None:
    state = SchedulerState(next_run_at=datetime(2026, 7, 11, 10, 0, 0), paused=False)

    assert should_dispatch(state, datetime(2026, 7, 11, 10, 5, 0)) is True


def test_service_persists_pause_manual_trigger_and_next_run() -> None:
    class MemoryStore:
        values: dict[str, str] = {}

        def get(self, key: str) -> str | None:
            return self.values.get(key)

        def set(self, key: str, value: str) -> None:
            self.values[key] = value

    dispatched: list[str] = []
    service = SchedulerService(MemoryStore(), dispatched.append)
    current = datetime(2026, 7, 11, 10, 0, 0)
    service.register("demo", 60, current)
    service.pause("demo", True)
    assert service.tick("demo", current) is False
    service.pause("demo", False)
    assert service.tick("demo", current) is True
    assert service.next_run("demo") == datetime(2026, 7, 11, 10, 1, 0)
    service.manual_trigger("demo")
    assert dispatched == ["demo", "demo"]


def test_registration_does_not_overwrite_existing_redis_schedule() -> None:
    class MemoryStore:
        values: dict[str, str] = {}

        def get(self, key: str) -> str | None:
            return self.values.get(key)

        def set(self, key: str, value: str) -> None:
            self.values[key] = value

    service = SchedulerService(MemoryStore(), lambda source_id: None)
    first = datetime(2026, 7, 11, 10, 0, 0)
    assert service.register_if_missing("demo", 60, first) is True
    assert service.tick("demo", first) is True
    assert (
        service.register_if_missing("demo", 60, first + timedelta(minutes=5)) is False
    )
    assert service.next_run("demo") == datetime(2026, 7, 11, 10, 1, 0)


def test_overdue_tick_advances_schedule_before_dispatching_again() -> None:
    class MemoryStore:
        values: dict[str, str] = {}

        def get(self, key: str) -> str | None:
            return self.values.get(key)

        def set(self, key: str, value: str) -> None:
            self.values[key] = value

    dispatched: list[str] = []
    service = SchedulerService(MemoryStore(), dispatched.append)
    due = datetime(2026, 7, 11, 10, 0, 0)
    restart_time = due + timedelta(minutes=5)
    service.register("demo", 60, due)

    assert service.tick("demo", restart_time) is True
    assert service.tick("demo", restart_time) is False
    assert dispatched == ["demo"]
    assert service.next_run("demo") == restart_time + timedelta(minutes=1)


def test_configured_sources_use_only_enabled_source_intervals_and_queues() -> None:
    def source(source_id: str, enabled: bool, interval_seconds: int) -> SourceConfig:
        return SourceConfig(
            id=source_id,
            name=source_id,
            enabled=enabled,
            mode=SourceMode.POLLING,
            interval_seconds=interval_seconds,
            queue=QueueName.HTTP,
            request=RequestConfig(
                url="https://example.invalid/items",
                method="GET",
                timeout_seconds=30,
            ),
            retry=RetryConfig(
                max_attempts=3,
                base_delay_seconds=1,
                max_delay_seconds=2,
            ),
            circuit_breaker=CircuitBreakerConfig(
                failure_threshold=5,
                recovery_seconds=60,
            ),
        )

    configured = configured_sources(
        CrawlerConfig(
            sources=[
                source("http-source", True, 60),
                source("disabled-source", False, 120),
            ]
        )
    )

    assert [
        (item.source_id, item.interval_seconds, item.queue) for item in configured
    ] == [("http-source", 60, QueueName.HTTP)]


def test_failed_source_dispatch_does_not_block_other_sources() -> None:
    class MemoryStore:
        values: dict[str, str] = {}

        def get(self, key: str) -> str | None:
            return self.values.get(key)

        def set(self, key: str, value: str) -> None:
            self.values[key] = value

    dispatched: list[str] = []

    def dispatch(source_id: str) -> None:
        if source_id == "stuck-source":
            raise RuntimeError("broker unavailable")
        dispatched.append(source_id)

    current = datetime(2026, 7, 11, 10, 0, 0)
    service = SchedulerService(MemoryStore(), dispatch)
    service.register("stuck-source", 60, current)
    service.register("healthy-source", 60, current)
    sources = configured_sources(
        CrawlerConfig(
            sources=[
                SourceConfig(
                    id="stuck-source",
                    name="Stuck source",
                    enabled=True,
                    mode=SourceMode.POLLING,
                    interval_seconds=60,
                    queue=QueueName.HTTP,
                    request=RequestConfig(
                        url="https://example.invalid/stuck",
                        method="GET",
                        timeout_seconds=30,
                    ),
                    retry=RetryConfig(
                        max_attempts=3,
                        base_delay_seconds=1,
                        max_delay_seconds=2,
                    ),
                    circuit_breaker=CircuitBreakerConfig(
                        failure_threshold=5,
                        recovery_seconds=60,
                    ),
                ),
                SourceConfig(
                    id="healthy-source",
                    name="Healthy source",
                    enabled=True,
                    mode=SourceMode.POLLING,
                    interval_seconds=60,
                    queue=QueueName.HTTP,
                    request=RequestConfig(
                        url="https://example.invalid/healthy",
                        method="GET",
                        timeout_seconds=30,
                    ),
                    retry=RetryConfig(
                        max_attempts=3,
                        base_delay_seconds=1,
                        max_delay_seconds=2,
                    ),
                    circuit_breaker=CircuitBreakerConfig(
                        failure_threshold=5,
                        recovery_seconds=60,
                    ),
                ),
            ]
        )
    )

    failures = run_cycle(service, sources, current)

    assert dispatched == ["healthy-source"]
    assert [failure.source_id for failure in failures] == ["stuck-source"]
