from __future__ import annotations

from datetime import datetime
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen
from uuid import UUID

from multisite_crawler.metrics import (
    MetricsSnapshot,
    RedisMetricsStore,
    render_prometheus,
)
from multisite_crawler.metrics_service import create_metrics_server
from multisite_crawler.observability import RunOutcome
from multisite_crawler.queueing import QueueDepths


class MemoryRedis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.members: dict[str, set[str]] = {}

    def hincrby(self, name: str, key: str, amount: int = 1) -> int:
        current = int(self.hashes.setdefault(name, {}).get(key, "0")) + amount
        self.hashes[name][key] = str(current)
        return current

    def hset(self, name: str, key: str, value: str) -> int:
        self.hashes.setdefault(name, {})[key] = value
        return 1

    def hgetall(self, name: str) -> dict[str, str]:
        return self.hashes.get(name, {}).copy()

    def sadd(self, name: str, *values: str) -> int:
        self.members.setdefault(name, set()).update(values)
        return len(values)

    def smembers(self, name: str) -> set[str]:
        return self.members.get(name, set()).copy()


def test_prometheus_output_has_required_metrics_and_bounded_labels() -> None:
    store = RedisMetricsStore(MemoryRedis())
    run_id = UUID("00000000-0000-0000-0000-000000000001")
    store.record_run(
        source_id="demo_api",
        run_id=run_id,
        outcome=RunOutcome.SUCCEEDED,
        duration_seconds=1.25,
        item_count=3,
        current=datetime(2026, 7, 12, 12, 0, 0),
    )
    store.record_http_status("demo_api", 200)
    store.record_items("demo_api", created=1, updated=2)
    store.record_lock_skip("demo_api")
    store.record_circuit_breaker("demo_api", is_open=False)

    rendered = render_prometheus(
        store.snapshot(queue_depths=QueueDepths(http=2, browser=1))
    )

    assert 'crawler_run_total{outcome="succeeded",source_id="demo_api"} 1' in rendered
    assert (
        'crawler_http_status_total{source_id="demo_api",status_code="200"} 1'
        in rendered
    )
    assert 'crawler_queue_depth{queue="http"} 2' in rendered
    for metric in (
        "crawler_run_failed_total",
        "crawler_run_duration_seconds",
        "crawler_items_found",
        "crawler_items_created",
        "crawler_items_updated",
        "crawler_last_success_timestamp",
        "crawler_parse_error_total",
        "crawler_lock_skip_total",
        "crawler_circuit_breaker_state",
    ):
        assert metric in rendered
    assert str(run_id) not in rendered
    assert "https://" not in rendered


def test_metrics_server_exposes_only_loopback_metrics_path() -> None:
    server = create_metrics_server(
        "127.0.0.1",
        0,
        lambda: MetricsSnapshot({}, QueueDepths(http=0, browser=0)),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        with urlopen(f"http://{host}:{port}/metrics") as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
        assert "crawler_queue_depth" in body
        try:
            urlopen(f"http://{host}:{port}/other")
        except HTTPError as error:
            assert error.code == 404
        else:
            raise AssertionError("non-metrics route must return 404")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
