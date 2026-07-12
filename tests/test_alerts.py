from __future__ import annotations

from datetime import datetime
from uuid import UUID

import pytest

from multisite_crawler.alerts import (
    AlertEvaluator,
    AlertState,
    AlertThresholds,
    MetricScenario,
)

NOW = datetime(2026, 7, 12, 13, 0, 0)
RUN_ID = UUID("00000000-0000-0000-0000-000000000001")


class MemoryState:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value


@pytest.mark.parametrize(
    ("scenario", "expected_rule"),
    [
        (MetricScenario(consecutive_failures=3), "crawler_consecutive_failures"),
        (MetricScenario(last_success_age_seconds=601), "crawler_no_recent_success"),
        (MetricScenario(items_found=0), "crawler_items_zero"),
        (MetricScenario(item_deviation_ratio=0.9), "crawler_items_abnormal"),
        (MetricScenario(parse_error_rate=0.5), "crawler_parse_error_rate"),
        (MetricScenario(http_status=403), "crawler_access_denied"),
        (MetricScenario(captcha_seen=True), "crawler_captcha"),
        (MetricScenario(queue_depth=200), "crawler_queue_backlog"),
        (
            MetricScenario(worker_last_heartbeat_age_seconds=121),
            "crawler_worker_offline",
        ),
        (MetricScenario(postgres_available=False), "crawler_postgres_down"),
        (MetricScenario(redis_available=False), "crawler_redis_down"),
        (MetricScenario(disk_free_ratio=0.01), "crawler_disk_low"),
    ],
)
def test_each_threshold_emits_one_safe_active_alert(
    scenario: MetricScenario, expected_rule: str
) -> None:
    events = AlertEvaluator(AlertThresholds(), MemoryState()).evaluate(
        "demo_api", RUN_ID, scenario, NOW
    )

    assert [event.rule for event in events] == [expected_rule]
    event = events[0]
    assert event.state is AlertState.ACTIVE
    assert event.source_id == "demo_api"
    assert event.crawl_run_id == RUN_ID
    assert event.troubleshooting_path.startswith("docs/")
    assert "token" not in event.to_json().lower()


def test_repeated_condition_is_deduplicated_and_healthy_state_resolves() -> None:
    state = MemoryState()
    evaluator = AlertEvaluator(AlertThresholds(), state)
    failing = MetricScenario(consecutive_failures=3)

    first = evaluator.evaluate("demo_api", RUN_ID, failing, NOW)
    repeated = evaluator.evaluate("demo_api", RUN_ID, failing, NOW)
    resolved = evaluator.evaluate("demo_api", RUN_ID, MetricScenario(), NOW)
    healthy_repeat = evaluator.evaluate("demo_api", RUN_ID, MetricScenario(), NOW)

    assert [event.state for event in first] == [AlertState.ACTIVE]
    assert repeated == []
    assert [event.state for event in resolved] == [AlertState.RESOLVED]
    assert healthy_repeat == []
