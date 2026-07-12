"""Redis-backed, low-cardinality Prometheus metric state."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from multisite_crawler.observability import RunOutcome
from multisite_crawler.queueing import QueueDepths

_SOURCE_ID = re.compile(r"^[a-z0-9_-]+$")
_PREFIX = "crawler:metrics"


class MetricsRedis(Protocol):
    """The minimal Redis operations required by the metrics state store."""

    def hincrby(self, name: str, key: str, amount: int = 1) -> int: ...

    def hset(self, name: str, key: str, value: str) -> int: ...

    def hgetall(self, name: str) -> Mapping[str, str]: ...

    def sadd(self, name: str, *values: str) -> int: ...

    def smembers(self, name: str) -> set[str]: ...


@dataclass(frozen=True)
class MetricsSnapshot:
    """A safe, numeric view of source and queue metrics."""

    sources: Mapping[str, Mapping[str, str]]
    queue_depths: QueueDepths


class RedisMetricsStore:
    """Maintain counters and gauges in stable Redis hashes per source."""

    def __init__(self, client: MetricsRedis) -> None:
        self._client = client

    def record_run(
        self,
        *,
        source_id: str,
        run_id: UUID,
        outcome: RunOutcome,
        duration_seconds: float,
        item_count: int,
        current: datetime,
    ) -> None:
        self._validate_source(source_id)
        if duration_seconds < 0 or item_count < 0:
            raise ValueError("run metrics must not be negative")
        key = self._source_key(source_id)
        self._register(source_id)
        self._client.hincrby(key, f"run_total:{outcome.value}")
        if outcome is RunOutcome.FAILED:
            self._client.hincrby(key, "run_failed_total")
        self._client.hset(key, "run_duration_seconds", str(duration_seconds))
        self._client.hset(key, "items_found", str(item_count))
        self._client.hset(key, "last_run_id", str(run_id))
        if outcome is RunOutcome.SUCCEEDED:
            self._client.hset(key, "last_success_timestamp", str(current.timestamp()))

    def record_http_status(self, source_id: str, status_code: int) -> None:
        self._validate_source(source_id)
        if status_code < 100 or status_code > 599:
            raise ValueError("status_code must be an HTTP status")
        self._register(source_id)
        self._client.hincrby(self._source_key(source_id), f"http_status:{status_code}")

    def record_items(self, source_id: str, *, created: int, updated: int) -> None:
        self._validate_source(source_id)
        if created < 0 or updated < 0:
            raise ValueError("item metrics must not be negative")
        key = self._source_key(source_id)
        self._register(source_id)
        self._client.hincrby(key, "items_created", created)
        self._client.hincrby(key, "items_updated", updated)

    def record_parse_error(self, source_id: str) -> None:
        self._increment(source_id, "parse_error_total")

    def record_lock_skip(self, source_id: str) -> None:
        self._increment(source_id, "lock_skip_total")

    def record_circuit_breaker(self, source_id: str, *, is_open: bool) -> None:
        self._validate_source(source_id)
        self._register(source_id)
        self._client.hset(
            self._source_key(source_id),
            "circuit_breaker_state",
            "1" if is_open else "0",
        )

    def snapshot(self, *, queue_depths: QueueDepths) -> MetricsSnapshot:
        sources = {
            source_id: dict(self._client.hgetall(self._source_key(source_id)))
            for source_id in sorted(self._client.smembers(f"{_PREFIX}:sources"))
        }
        return MetricsSnapshot(sources, queue_depths)

    def _increment(self, source_id: str, field: str) -> None:
        self._validate_source(source_id)
        self._register(source_id)
        self._client.hincrby(self._source_key(source_id), field)

    def _register(self, source_id: str) -> None:
        self._client.sadd(f"{_PREFIX}:sources", source_id)

    @staticmethod
    def _validate_source(source_id: str) -> None:
        if not _SOURCE_ID.fullmatch(source_id):
            raise ValueError("source_id must match [a-z0-9_-]+")

    @staticmethod
    def _source_key(source_id: str) -> str:
        return f"{_PREFIX}:source:{source_id}"


def render_prometheus(snapshot: MetricsSnapshot) -> str:
    """Render only fixed metric names and bounded labels in Prometheus format."""
    lines = [
        "# HELP crawler_queue_depth Current queue backlog.",
        "# TYPE crawler_queue_depth gauge",
        _metric("crawler_queue_depth", snapshot.queue_depths.http, queue="http"),
        _metric("crawler_queue_depth", snapshot.queue_depths.browser, queue="browser"),
    ]
    fields = (
        ("crawler_run_failed_total", "run_failed_total", "counter"),
        ("crawler_run_duration_seconds", "run_duration_seconds", "gauge"),
        ("crawler_items_found", "items_found", "gauge"),
        ("crawler_items_created", "items_created", "counter"),
        ("crawler_items_updated", "items_updated", "counter"),
        ("crawler_last_success_timestamp", "last_success_timestamp", "gauge"),
        ("crawler_parse_error_total", "parse_error_total", "counter"),
        ("crawler_lock_skip_total", "lock_skip_total", "counter"),
        ("crawler_circuit_breaker_state", "circuit_breaker_state", "gauge"),
    )
    for source_id, values in snapshot.sources.items():
        lines.extend(_run_total_lines(source_id, values))
        for metric_name, field, metric_type in fields:
            lines.extend(
                (
                    f"# TYPE {metric_name} {metric_type}",
                    _metric(metric_name, values.get(field, "0"), source_id=source_id),
                )
            )
        for field, value in sorted(values.items()):
            if field.startswith("http_status:"):
                lines.extend(
                    (
                        "# TYPE crawler_http_status_total counter",
                        _metric(
                            "crawler_http_status_total",
                            value,
                            source_id=source_id,
                            status_code=field.split(":", 1)[1],
                        ),
                    )
                )
    return "\n".join(lines) + "\n"


def _run_total_lines(source_id: str, values: Mapping[str, str]) -> list[str]:
    lines = ["# TYPE crawler_run_total counter"]
    for outcome in RunOutcome:
        lines.append(
            _metric(
                "crawler_run_total",
                values.get(f"run_total:{outcome.value}", "0"),
                source_id=source_id,
                outcome=outcome.value,
            )
        )
    return lines


def _metric(name: str, value: int | str, **labels: str) -> str:
    rendered_labels = ",".join(f'{key}="{labels[key]}"' for key in sorted(labels))
    return f"{name}{{{rendered_labels}}} {value}"
