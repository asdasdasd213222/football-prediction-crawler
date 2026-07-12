from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest

from multisite_crawler.browser_runtime import (
    BrowserRuntimeConfigurationError,
    BrowserRuntimeSettings,
    PlaywrightGateway,
)
from multisite_crawler.browser_session import (
    BrowserSessionManager,
    BrowserSessionObservation,
    BrowserSessionRequiredError,
)
from multisite_crawler.browser_worker import (
    browser_worker_argv,
    validate_browser_runtime_settings,
)
from multisite_crawler.observability import JsonEventFormatter
from multisite_crawler.queueing import create_celery_app
from multisite_crawler.tasks import (
    LockOutcome,
    _browser_runtime,
    record_browser_session_observation,
    run_browser_operation,
    run_browser_runtime_probe,
    run_with_source_lease,
)


class MemoryRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool:
        del ex
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def eval(self, script: str, numkeys: int, *args: object) -> int:
        del script, numkeys
        key, token = str(args[0]), str(args[1])
        if self.values.get(key) != token:
            return 0
        del self.values[key]
        return 1


class MemorySessionStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value


class FakeRuntime:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, operation: Callable[[Any], str]) -> str:
        self.calls += 1
        return operation(object())


class CapturingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []
        self.setFormatter(JsonEventFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(self.format(record))


def test_browser_operation_uses_the_existing_source_lease() -> None:
    store = MemoryRedis()
    runtime = FakeRuntime()

    assert run_browser_operation("demo", lambda page: "ok", runtime, store) == "ok"
    assert runtime.calls == 1
    assert store.values == {}


def test_source_lease_emits_traceable_safe_run_event() -> None:
    store = MemoryRedis()
    logger = logging.getLogger("test.source_lease")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = CapturingHandler()
    logger.addHandler(handler)

    assert (
        run_with_source_lease(
            store,
            "demo",
            lambda: "ok",
            event_logger=logger,
            task_id="task-local",
        )
        == "ok"
    )

    payload = json.loads(handler.messages[-1])
    assert payload["source_id"] == "demo"
    assert payload["task_id"] == "task-local"
    assert payload["outcome"] == "succeeded"
    assert "crawl_run_id" in payload


def test_browser_operation_skips_when_the_existing_source_lease_is_held() -> None:
    store = MemoryRedis()
    store.set("crawler:lock:source:demo", "other", nx=True, ex=90)

    assert run_browser_operation("demo", lambda page: "ok", FakeRuntime(), store) == (
        LockOutcome.SKIPPED_OVERLAP
    )


def test_captcha_observation_stops_before_browser_retry() -> None:
    manager = BrowserSessionManager(MemorySessionStore())
    now = datetime(2026, 7, 12, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    with pytest.raises(BrowserSessionRequiredError, match="captcha"):
        record_browser_session_observation(
            manager,
            "sporttery_primary",
            BrowserSessionObservation.CAPTCHA,
            now,
        )


def test_browser_runtime_probe_is_routed_to_the_browser_queue() -> None:
    app = create_celery_app("redis://localhost:6379/0")

    assert app.conf.task_routes[
        "multisite_crawler.tasks.run_browser_runtime_probe_task"
    ] == {"queue": "browser"}


def test_probe_requires_an_explicit_local_fixture_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BROWSER_RUNTIME_PROBE_URL", raising=False)

    with pytest.raises(BrowserRuntimeConfigurationError, match="PROBE_URL"):
        run_browser_runtime_probe(FakeRuntime(), MemoryRedis())


def test_probe_rejects_non_loopback_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROWSER_RUNTIME_PROBE_URL", "https://example.invalid")

    with pytest.raises(BrowserRuntimeConfigurationError, match="127.0.0.1"):
        run_browser_runtime_probe(FakeRuntime(), MemoryRedis())


def test_probe_navigates_to_the_fixture_and_returns_its_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BROWSER_RUNTIME_PROBE_URL", "http://127.0.0.1:8765/")
    runtime = FakePageRuntime()

    assert run_browser_runtime_probe(runtime, MemoryRedis()) == "fixture-title"
    assert runtime.page.visited_url == "http://127.0.0.1:8765/"


def test_verify_edge_runtime_script_builds_the_probe_url_from_the_fixture_port() -> (
    None
):
    script = Path("scripts/verify_edge_runtime.ps1").read_text(encoding="utf-8")

    assert "http://127.0.0.1:$fixturePort/" in script
    assert "http://127.0.0.1:8765/" not in script
    assert "[string]::IsNullOrWhiteSpace($publishedPort)" in script
    assert "-ArgumentList $fixtureScript, $portFile" in script
    assert "-ArgumentList '-c'" not in script


def test_worker_validates_runtime_settings_before_starting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BROWSER_EDGE_EXECUTABLE_PATH", raising=False)

    with pytest.raises(BrowserRuntimeConfigurationError, match="EDGE_EXECUTABLE"):
        validate_browser_runtime_settings()


def test_production_browser_runtime_wires_the_failure_artifact_writer(
    tmp_path: Path,
) -> None:
    settings = BrowserRuntimeSettings(
        edge_executable_path=tmp_path / "msedge.exe",
        user_data_dir=tmp_path / "profile",
        failure_snapshot_dir=tmp_path / "snapshots",
        page_timeout_seconds=30.0,
        action_timeout_seconds=10.0,
    )

    runtime = _browser_runtime(
        lambda: cast(PlaywrightGateway, object()),
        settings,
    )

    assert runtime._artifact_writer is not None


def test_browser_worker_uses_its_own_configured_concurrency() -> None:
    assert browser_worker_argv(
        {"BROWSER_WORKER_CONCURRENCY": "1", "BROWSER_MAX_MEMORY_MB": "512"}
    ) == [
        "worker",
        "--queues=browser",
        "--loglevel=INFO",
        "--concurrency=1",
        "--max-memory-per-child=524288",
    ]


@pytest.mark.parametrize("value", ["0", "-1", "2", "invalid"])
def test_browser_worker_rejects_invalid_concurrency(value: str) -> None:
    with pytest.raises(BrowserRuntimeConfigurationError, match="CONCURRENCY"):
        browser_worker_argv({"BROWSER_WORKER_CONCURRENCY": value})


@pytest.mark.parametrize("value", ["0", "-1", "invalid"])
def test_browser_worker_rejects_invalid_memory_limit(value: str) -> None:
    with pytest.raises(BrowserRuntimeConfigurationError, match="MAX_MEMORY"):
        browser_worker_argv({"BROWSER_MAX_MEMORY_MB": value})


class FakePageRuntime:
    def __init__(self) -> None:
        self.page = FakeProbePage()

    def run(self, operation: Callable[[Any], str]) -> str:
        return operation(self.page)


class FakeProbePage:
    visited_url: str | None = None

    def goto(self, url: str) -> None:
        self.visited_url = url

    def title(self) -> str:
        return "fixture-title"
