"""Redis-backed scheduler process entry point."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import sleep
from typing import cast

from redis import Redis

from multisite_crawler.config import CrawlerConfig, QueueName, load_config
from multisite_crawler.database import beijing_now
from multisite_crawler.scheduler import SchedulerService, SchedulerStore
from multisite_crawler.tasks import run_browser_task, run_http_task

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScheduledSource:
    """The site-neutral schedule fields needed by the scheduler loop."""

    source_id: str
    interval_seconds: int
    queue: QueueName


@dataclass(frozen=True)
class SchedulerCycleFailure:
    """One source failure isolated during a scheduler service cycle."""

    source_id: str
    error: Exception


def configured_sources(config: CrawlerConfig) -> list[ScheduledSource]:
    """Convert enabled validated sources into scheduler-safe schedule entries."""
    return [
        ScheduledSource(source.id, source.interval_seconds, source.queue)
        for source in config.sources
        if source.enabled
    ]


def run_cycle(
    service: SchedulerService, sources: list[ScheduledSource], current: datetime
) -> list[SchedulerCycleFailure]:
    """Dispatch due sources while returning source-scoped failures explicitly."""
    failures: list[SchedulerCycleFailure] = []
    for source in sources:
        try:
            service.tick(source.source_id, current)
        except Exception as error:
            LOGGER.exception("scheduler tick failed for source_id=%s", source.source_id)
            failures.append(SchedulerCycleFailure(source.source_id, error))
    return failures


def main() -> None:
    """Run the site-neutral scheduler service loop."""
    redis_client = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    config_path = Path(
        os.environ.get("SCHEDULER_CONFIG_PATH", "configs/sources.example.yaml")
    )
    sources = configured_sources(load_config(config_path))
    sources_by_id = {source.source_id: source for source in sources}

    def dispatch(source_id: str) -> None:
        source = sources_by_id[source_id]
        if source.queue is QueueName.HTTP:
            run_http_task.delay(source_id)
        else:
            run_browser_task.delay(source_id)

    service = SchedulerService(cast(SchedulerStore, redis_client), dispatch)
    current = beijing_now()
    for source in sources:
        service.register_if_missing(source.source_id, source.interval_seconds, current)
    while True:
        run_cycle(service, sources, beijing_now())
        sleep(1)


if __name__ == "__main__":
    main()
