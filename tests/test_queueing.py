from __future__ import annotations

from multisite_crawler.queueing import QueueDepths, queue_depths, queue_for


def test_queue_for_routes_each_task_kind_to_its_own_queue() -> None:
    assert queue_for("http") == "http"
    assert queue_for("browser") == "browser"


def test_queue_depths_reads_each_named_queue() -> None:
    class FakeRedis:
        def llen(self, name: str) -> int:
            return {"http": 2, "browser": 3}[name]

    assert queue_depths(FakeRedis()) == QueueDepths(http=2, browser=3)
