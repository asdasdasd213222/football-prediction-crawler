"""Site-neutral Celery task entry points."""

# mypy: disable-error-code=untyped-decorator

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from time import monotonic, sleep
from typing import Protocol, TypeVar, cast
from urllib.parse import urlsplit
from uuid import uuid4

from redis import Redis

from multisite_crawler.browser_artifacts import BrowserArtifactWriter
from multisite_crawler.browser_runtime import (
    BrowserPage,
    BrowserRuntimeConfigurationError,
    BrowserRuntimeSettings,
    ManagedEdgeRuntime,
    PlaywrightGateway,
)
from multisite_crawler.browser_session import (
    BrowserSessionManager,
    BrowserSessionObservation,
    BrowserSessionState,
)
from multisite_crawler.locking import (
    LeaseHeartbeat,
    RedisLease,
    RedisLeaseStore,
    source_lock_key,
)
from multisite_crawler.observability import (
    RunContext,
    RunEvent,
    RunOutcome,
    emit_run_event,
)
from multisite_crawler.queueing import create_celery_app

celery_app = create_celery_app()
LOGGER = logging.getLogger(__name__)
LOCK_TTL_SECONDS = 90
PROBE_URL_ENVIRONMENT_VARIABLE = "BROWSER_RUNTIME_PROBE_URL"
T = TypeVar("T")


class BrowserRuntime(Protocol):
    """Runtime boundary used by generic browser operations."""

    def run(self, operation: Callable[[BrowserPage], T]) -> T: ...


class _ProbePage(Protocol):
    def goto(self, url: str) -> object: ...

    def title(self) -> str: ...


class LockOutcome(StrEnum):
    """A non-exceptional source task result when overlap is prevented."""

    SKIPPED_OVERLAP = "skipped_overlap"


def run_with_source_lease[T](
    store: RedisLeaseStore,
    source_id: str,
    operation: Callable[[], T],
    *,
    ttl_seconds: int = LOCK_TTL_SECONDS,
    renew_interval_seconds: float | None = None,
    event_logger: logging.Logger | None = None,
    task_id: str = "internal",
) -> T | LockOutcome:
    """Run one source operation only while its Redis lease is held."""
    logger = event_logger or LOGGER
    context = RunContext(source_id, uuid4(), task_id)
    started_at = monotonic()
    lease = RedisLease(store, source_lock_key(source_id), ttl_seconds=ttl_seconds)
    if not lease.acquire():
        LOGGER.info("skipped_overlap source_id=%s", source_id)
        emit_run_event(
            logger,
            RunEvent(
                "run_skipped",
                context,
                RunOutcome.SKIPPED,
                duration_seconds=monotonic() - started_at,
            ),
        )
        return LockOutcome.SKIPPED_OVERLAP
    heartbeat = LeaseHeartbeat(
        lease,
        renew_interval_seconds
        if renew_interval_seconds is not None
        else max(1, ttl_seconds / 3),
    )
    heartbeat.start()
    try:
        result = operation()
        emit_run_event(
            logger,
            RunEvent(
                "run_finished",
                context,
                RunOutcome.SUCCEEDED,
                duration_seconds=monotonic() - started_at,
            ),
        )
        return result
    except BaseException as error:
        emit_run_event(
            logger,
            RunEvent(
                "run_failed",
                context,
                RunOutcome.FAILED,
                duration_seconds=monotonic() - started_at,
                exception=error,
            ),
        )
        raise
    finally:
        heartbeat.stop()
        lease.release()


def run_browser_operation[T](
    source_id: str,
    operation: Callable[[BrowserPage], T],
    runtime: BrowserRuntime,
    store: RedisLeaseStore,
) -> T | LockOutcome:
    """Run one generic browser operation under the existing source lease."""
    return run_with_source_lease(store, source_id, lambda: runtime.run(operation))


def record_browser_session_observation(
    manager: BrowserSessionManager,
    profile_reference: str,
    observation: BrowserSessionObservation,
    current: datetime,
) -> BrowserSessionState:
    """Persist a safe adapter observation without retrying a login action."""
    return manager.record_observation(profile_reference, observation, current)


def run_browser_runtime_probe(
    runtime: BrowserRuntime,
    store: RedisLeaseStore,
) -> str | LockOutcome:
    """Probe only an explicitly configured loopback fixture and return its title."""
    url = _probe_url_from_environment()

    def operation(page: BrowserPage) -> str:
        probe_page = cast(_ProbePage, page)
        probe_page.goto(url)
        return probe_page.title()

    return run_browser_operation("browser_runtime_probe", operation, runtime, store)


def _redis_lease_store() -> RedisLeaseStore:
    redis_client = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    return cast(RedisLeaseStore, redis_client)


def _browser_runtime(
    playwright_factory: Callable[[], PlaywrightGateway] | None = None,
    settings: BrowserRuntimeSettings | None = None,
) -> ManagedEdgeRuntime:
    if playwright_factory is None:
        from playwright.sync_api import sync_playwright

        playwright_factory = cast(Callable[[], PlaywrightGateway], sync_playwright)
    if settings is None:
        settings = BrowserRuntimeSettings.from_environment(
            os.environ,
            repository_root=Path(__file__).resolve().parents[2],
        )
    return ManagedEdgeRuntime(
        settings,
        playwright_factory=playwright_factory,
        artifact_writer=BrowserArtifactWriter(settings.failure_snapshot_dir),
    )


def _probe_url_from_environment() -> str:
    url = os.environ.get(PROBE_URL_ENVIRONMENT_VARIABLE, "").strip()
    parsed = urlsplit(url)
    if (
        not url
        or parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise BrowserRuntimeConfigurationError(
            f"{PROBE_URL_ENVIRONMENT_VARIABLE} must be an explicit "
            "http://127.0.0.1 fixture URL"
        )
    return url


@celery_app.task(
    bind=True,
    autoretry_for=(ConnectionError,),
    retry_backoff=True,
    max_retries=3,
)
def run_http_task(self: object, source_id: str) -> str:
    """Queue-safe HTTP task placeholder; source work arrives in a later task."""
    return str(
        run_with_source_lease(_redis_lease_store(), source_id, lambda: source_id)
    )


@celery_app.task(
    bind=True,
    autoretry_for=(ConnectionError,),
    retry_backoff=True,
    max_retries=3,
)
def run_browser_task(self: object, source_id: str) -> str:
    """Queue-safe browser task placeholder; browser work arrives later."""
    return str(
        run_with_source_lease(_redis_lease_store(), source_id, lambda: source_id)
    )


@celery_app.task(bind=True, acks_late=True)
def run_browser_runtime_probe_task(self: object) -> str:
    """Run the opt-in local Edge fixture probe on the browser queue."""
    return str(run_browser_runtime_probe(_browser_runtime(), _redis_lease_store()))


@celery_app.task(bind=True, acks_late=True)
def run_delivery_probe_task(self: object, seconds: int) -> str:
    """Local integration probe for late-acknowledged task redelivery."""
    sleep(seconds)
    return "delivery-probe"


@celery_app.task(bind=True, acks_late=True)
def run_lock_probe_task(self: object, source_id: str, seconds: int) -> str:
    """Local-only probe that holds one source lease while simulating slow work."""

    def operation() -> str:
        sleep(seconds)
        return source_id

    result = run_with_source_lease(
        _redis_lease_store(),
        source_id,
        operation,
    )
    return str(result)
