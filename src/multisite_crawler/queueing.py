"""Site-neutral queue names and Redis backlog metrics."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from celery import Celery  # type: ignore[import-untyped]
from kombu import Queue  # type: ignore[import-untyped]


class RedisListReader(Protocol):
    """Minimal Redis interface required for queue depth observation."""

    def llen(self, name: str) -> int:
        """Return the length of a Redis list."""


@dataclass(frozen=True)
class QueueDepths:
    """Current backlog sizes for the worker queues."""

    http: int
    browser: int


def queue_for(task_kind: str) -> str:
    """Return the explicit worker queue for a supported task kind."""
    if task_kind not in {"http", "browser"}:
        raise ValueError(f"Unsupported task kind: {task_kind}")
    return task_kind


def queue_depths(redis_client: RedisListReader) -> QueueDepths:
    """Read non-sensitive backlog metrics for both queues."""
    return QueueDepths(
        http=redis_client.llen("http"),
        browser=redis_client.llen("browser"),
    )


def create_celery_app(broker_url: str | None = None) -> Celery:
    """Create a broker-only Celery app with safe worker defaults."""
    app = Celery("multisite_crawler", broker=broker_url or os.environ.get("REDIS_URL"))
    app.conf.update(
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_serializer="json",
        accept_content=["json"],
        result_backend=None,
        task_default_retry_delay=1,
        task_soft_time_limit=60,
        task_time_limit=75,
        broker_transport_options={"visibility_timeout": 10},
        task_queues=(Queue("http"), Queue("browser")),
        task_routes={
            "multisite_crawler.tasks.run_http_task": {"queue": "http"},
            "multisite_crawler.tasks.run_browser_task": {"queue": "browser"},
            "multisite_crawler.tasks.run_browser_runtime_probe_task": {
                "queue": "browser"
            },
            "multisite_crawler.tasks.run_delivery_probe_task": {"queue": "http"},
            "multisite_crawler.tasks.run_lock_probe_task": {"queue": "http"},
        },
    )
    return app
