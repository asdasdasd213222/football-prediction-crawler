"""Typed, deduplicated alert evaluation from bounded observability state."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

_SOURCE_ID = re.compile(r"^[a-z0-9_-]+$")
_RUNBOOKS = {
    "crawler_consecutive_failures": "docs/operations/observability.md#run-failures",
    "crawler_no_recent_success": "docs/operations/observability.md#run-failures",
    "crawler_items_zero": "docs/operations/observability.md#data-quality",
    "crawler_items_abnormal": "docs/operations/observability.md#data-quality",
    "crawler_parse_error_rate": "docs/operations/observability.md#data-quality",
    "crawler_access_denied": "docs/operations/observability.md#run-failures",
    "crawler_captcha": "docs/operations/observability.md#run-failures",
    "crawler_queue_backlog": "docs/operations/observability.md#queue-backlog",
    "crawler_worker_offline": "docs/operations/observability.md#queue-backlog",
    "crawler_postgres_down": "docs/operations/observability.md#dependencies",
    "crawler_redis_down": "docs/operations/observability.md#dependencies",
    "crawler_disk_low": "docs/operations/observability.md#snapshot-retention",
}


class AlertStateStore(Protocol):
    """Minimal persistent state required to deduplicate alert transitions."""

    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str) -> object: ...


class AlertState(StrEnum):
    """The only alert lifecycle transitions emitted by the evaluator."""

    ACTIVE = "active"
    RESOLVED = "resolved"


@dataclass(frozen=True)
class AlertThresholds:
    """Stable threshold defaults for local observability evaluation."""

    consecutive_failures: int = 3
    max_last_success_age_seconds: int = 600
    item_deviation_ratio: float = 0.5
    parse_error_rate: float = 0.1
    queue_depth: int = 100
    worker_heartbeat_age_seconds: int = 120
    disk_free_ratio: float = 0.05


@dataclass(frozen=True)
class MetricScenario:
    """Safe aggregate values used to evaluate one source's alert rules."""

    consecutive_failures: int = 0
    last_success_age_seconds: int | None = None
    items_found: int | None = None
    item_deviation_ratio: float | None = None
    parse_error_rate: float = 0.0
    http_status: int | None = None
    captcha_seen: bool = False
    queue_depth: int = 0
    worker_last_heartbeat_age_seconds: int | None = None
    postgres_available: bool = True
    redis_available: bool = True
    disk_free_ratio: float = 1.0


@dataclass(frozen=True)
class AlertEvent:
    """A redaction-safe active or recovery notification."""

    rule: str
    state: AlertState
    source_id: str
    crawl_run_id: UUID
    troubleshooting_path: str
    occurred_at: datetime

    def to_json(self) -> str:
        payload = asdict(self)
        payload["state"] = self.state.value
        payload["crawl_run_id"] = str(self.crawl_run_id)
        payload["occurred_at"] = self.occurred_at.isoformat()
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class AlertEvaluator:
    """Emit only state changes so persistent incidents do not create storms."""

    def __init__(self, thresholds: AlertThresholds, state: AlertStateStore) -> None:
        self._thresholds = thresholds
        self._state = state

    def evaluate(
        self,
        source_id: str,
        crawl_run_id: UUID,
        scenario: MetricScenario,
        current: datetime,
    ) -> list[AlertEvent]:
        if not _SOURCE_ID.fullmatch(source_id):
            raise ValueError("source_id must match [a-z0-9_-]+")
        events: list[AlertEvent] = []
        for rule, is_active in self._conditions(scenario):
            key = f"crawler:alerts:{source_id}:{rule}"
            previous = self._state.get(key)
            if is_active and previous != AlertState.ACTIVE.value:
                self._state.set(key, AlertState.ACTIVE.value)
                events.append(
                    self._event(
                        rule, AlertState.ACTIVE, source_id, crawl_run_id, current
                    )
                )
            elif not is_active and previous == AlertState.ACTIVE.value:
                self._state.set(key, AlertState.RESOLVED.value)
                events.append(
                    self._event(
                        rule, AlertState.RESOLVED, source_id, crawl_run_id, current
                    )
                )
        return events

    def _conditions(self, scenario: MetricScenario) -> tuple[tuple[str, bool], ...]:
        thresholds = self._thresholds
        return (
            (
                "crawler_consecutive_failures",
                scenario.consecutive_failures >= thresholds.consecutive_failures,
            ),
            (
                "crawler_no_recent_success",
                scenario.last_success_age_seconds is not None
                and scenario.last_success_age_seconds
                > thresholds.max_last_success_age_seconds,
            ),
            ("crawler_items_zero", scenario.items_found == 0),
            (
                "crawler_items_abnormal",
                scenario.item_deviation_ratio is not None
                and scenario.item_deviation_ratio >= thresholds.item_deviation_ratio,
            ),
            (
                "crawler_parse_error_rate",
                scenario.parse_error_rate >= thresholds.parse_error_rate,
            ),
            ("crawler_access_denied", scenario.http_status in {401, 403, 429}),
            ("crawler_captcha", scenario.captcha_seen),
            ("crawler_queue_backlog", scenario.queue_depth >= thresholds.queue_depth),
            (
                "crawler_worker_offline",
                scenario.worker_last_heartbeat_age_seconds is not None
                and scenario.worker_last_heartbeat_age_seconds
                > thresholds.worker_heartbeat_age_seconds,
            ),
            ("crawler_postgres_down", not scenario.postgres_available),
            ("crawler_redis_down", not scenario.redis_available),
            (
                "crawler_disk_low",
                scenario.disk_free_ratio <= thresholds.disk_free_ratio,
            ),
        )

    @staticmethod
    def _event(
        rule: str,
        state: AlertState,
        source_id: str,
        crawl_run_id: UUID,
        current: datetime,
    ) -> AlertEvent:
        return AlertEvent(
            rule, state, source_id, crawl_run_id, _RUNBOOKS[rule], current
        )
