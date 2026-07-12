from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from multisite_crawler.browser_artifacts import BrowserArtifactWriter
from multisite_crawler.browser_runtime import (
    BrowserOperationError,
    BrowserRuntimeConfigurationError,
    BrowserRuntimeSettings,
    ManagedEdgeRuntime,
)


@pytest.fixture
def settings(tmp_path: Path) -> BrowserRuntimeSettings:
    executable = tmp_path.parent / "msedge.exe"
    executable.touch()
    return BrowserRuntimeSettings(
        edge_executable_path=executable.resolve(),
        user_data_dir=(tmp_path.parent / "browser-profile").resolve(),
        failure_snapshot_dir=(tmp_path.parent / "browser-snapshots").resolve(),
        page_timeout_seconds=30.0,
        action_timeout_seconds=10.0,
    )


def test_settings_require_an_edge_executable_and_external_profile(
    tmp_path: Path,
) -> None:
    with pytest.raises(BrowserRuntimeConfigurationError, match="EDGE_EXECUTABLE"):
        BrowserRuntimeSettings.from_environment({}, repository_root=tmp_path)


def test_settings_reject_a_profile_inside_the_repository(tmp_path: Path) -> None:
    executable = tmp_path.parent / "msedge.exe"
    executable.touch()
    environment = {
        "BROWSER_EDGE_EXECUTABLE_PATH": str(executable),
        "BROWSER_USER_DATA_DIR": str(tmp_path / "edge-profile"),
        "BROWSER_FAILURE_SNAPSHOT_DIR": str(tmp_path.parent / "snapshots"),
    }

    with pytest.raises(BrowserRuntimeConfigurationError, match="outside"):
        BrowserRuntimeSettings.from_environment(environment, repository_root=tmp_path)


def test_settings_accept_an_external_profile_and_snapshot_dir(tmp_path: Path) -> None:
    repository_root = tmp_path
    executable = tmp_path.parent / "msedge.exe"
    executable.touch()
    profile_dir = tmp_path.parent / "browser-profile"
    snapshot_dir = tmp_path.parent / "browser-snapshots"
    environment = {
        "BROWSER_EDGE_EXECUTABLE_PATH": str(executable),
        "BROWSER_USER_DATA_DIR": str(profile_dir),
        "BROWSER_FAILURE_SNAPSHOT_DIR": str(snapshot_dir),
        "BROWSER_PAGE_TIMEOUT_SECONDS": "30",
        "BROWSER_ACTION_TIMEOUT_SECONDS": "10",
    }

    settings = BrowserRuntimeSettings.from_environment(
        environment,
        repository_root=repository_root,
    )

    assert settings.edge_executable_path == executable.resolve()
    assert settings.user_data_dir == profile_dir.resolve()
    assert settings.failure_snapshot_dir == snapshot_dir.resolve()
    assert settings.page_timeout_seconds == 30.0
    assert settings.action_timeout_seconds == 10.0
    assert snapshot_dir.is_dir()


def test_settings_reject_relative_profile_and_snapshot_paths(tmp_path: Path) -> None:
    executable = tmp_path.parent / "msedge.exe"
    executable.touch()
    environment = {
        "BROWSER_EDGE_EXECUTABLE_PATH": str(executable),
        "BROWSER_USER_DATA_DIR": "relative-profile",
        "BROWSER_FAILURE_SNAPSHOT_DIR": "relative-snapshots",
    }

    with pytest.raises(BrowserRuntimeConfigurationError, match="BROWSER_USER_DATA_DIR"):
        BrowserRuntimeSettings.from_environment(environment, repository_root=tmp_path)

    environment["BROWSER_USER_DATA_DIR"] = str(tmp_path.parent / "browser-profile")

    with pytest.raises(
        BrowserRuntimeConfigurationError,
        match="BROWSER_FAILURE_SNAPSHOT_DIR",
    ):
        BrowserRuntimeSettings.from_environment(environment, repository_root=tmp_path)


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("BROWSER_PAGE_TIMEOUT_SECONDS", "0"),
        ("BROWSER_PAGE_TIMEOUT_SECONDS", "-1"),
        ("BROWSER_ACTION_TIMEOUT_SECONDS", "0"),
        ("BROWSER_ACTION_TIMEOUT_SECONDS", "-1"),
    ],
)
def test_settings_reject_non_positive_timeouts(
    tmp_path: Path,
    variable: str,
    value: str,
) -> None:
    executable = tmp_path.parent / "msedge.exe"
    executable.touch()
    environment = {
        "BROWSER_EDGE_EXECUTABLE_PATH": str(executable),
        "BROWSER_USER_DATA_DIR": str(tmp_path.parent / "browser-profile"),
        "BROWSER_FAILURE_SNAPSHOT_DIR": str(tmp_path.parent / "browser-snapshots"),
        "BROWSER_PAGE_TIMEOUT_SECONDS": "30",
        "BROWSER_ACTION_TIMEOUT_SECONDS": "10",
    }
    environment[variable] = value

    with pytest.raises(BrowserRuntimeConfigurationError, match=variable):
        BrowserRuntimeSettings.from_environment(environment, repository_root=tmp_path)


def test_runtime_closes_page_and_context_after_success(
    settings: BrowserRuntimeSettings,
) -> None:
    fake = FakePlaywrightFactory()
    runtime = ManagedEdgeRuntime(settings, playwright_factory=fake)

    assert runtime.run(lambda page: page.title()) == "fixture"
    assert fake.page.closed is True
    assert fake.context.closed is True


def test_runtime_blocks_media_and_sets_bounded_timeouts(
    settings: BrowserRuntimeSettings,
) -> None:
    fake = FakePlaywrightFactory()

    ManagedEdgeRuntime(settings, playwright_factory=fake).run(lambda page: None)

    assert fake.context.blocked_resource_types == {"font", "image", "media"}
    assert fake.page.default_timeout_ms == 10_000
    assert fake.page.default_navigation_timeout_ms == 30_000


def test_runtime_reraises_operation_errors_after_cleanup(
    settings: BrowserRuntimeSettings,
) -> None:
    fake = FakePlaywrightFactory()
    runtime = ManagedEdgeRuntime(settings, playwright_factory=fake)

    with pytest.raises(RuntimeError, match="boom"):
        runtime.run(lambda page: _raise_runtime_error())

    assert fake.page.closed is True
    assert fake.context.closed is True


def test_runtime_persists_only_adapter_supplied_safe_failure_artifact(
    settings: BrowserRuntimeSettings, tmp_path: Path
) -> None:
    writer = BrowserArtifactWriter(tmp_path)
    runtime = ManagedEdgeRuntime(
        settings,
        playwright_factory=FakePlaywrightFactory(),
        artifact_writer=writer,
    )

    with pytest.raises(BrowserOperationError, match="parse failed"):
        runtime.run(lambda page: _raise_browser_operation_error())

    artifacts = list(tmp_path.glob("demo_*.html"))
    assert len(artifacts) == 1
    assert (
        artifacts[0].read_text(encoding="utf-8")
        == "<table><tr><td>safe</td></tr></table>"
    )


def test_runtime_closes_context_when_new_page_creation_fails(
    settings: BrowserRuntimeSettings,
) -> None:
    fake = FakePlaywrightFactory(start_with_page=False)
    fake.context.raise_on_new_page = RuntimeError("page setup failed")

    with pytest.raises(RuntimeError, match="page setup failed"):
        ManagedEdgeRuntime(settings, playwright_factory=fake).run(lambda page: None)

    assert fake.context.closed is True


def test_runtime_still_closes_context_when_page_close_fails(
    settings: BrowserRuntimeSettings,
) -> None:
    fake = FakePlaywrightFactory()
    fake.page.close_error = RuntimeError("page close failed")

    with pytest.raises(RuntimeError, match="page close failed"):
        ManagedEdgeRuntime(settings, playwright_factory=fake).run(lambda page: None)

    assert fake.context.closed is True


def test_runtime_preserves_primary_operation_error_when_page_close_also_fails(
    settings: BrowserRuntimeSettings,
) -> None:
    fake = FakePlaywrightFactory()
    fake.page.close_error = RuntimeError("page close failed")

    with pytest.raises(RuntimeError, match="boom"):
        ManagedEdgeRuntime(settings, playwright_factory=fake).run(
            lambda page: _raise_runtime_error()
        )

    assert fake.context.closed is True


def test_runtime_recovers_with_a_new_context_after_a_browser_failure(
    settings: BrowserRuntimeSettings,
) -> None:
    failed = FakePlaywrightFactory(start_with_page=False)
    failed.context.raise_on_new_page = RuntimeError("browser crashed")
    recovered = FakePlaywrightFactory()
    factories = iter([failed, recovered])
    runtime = ManagedEdgeRuntime(settings, playwright_factory=lambda: next(factories))

    with pytest.raises(RuntimeError, match="browser crashed"):
        runtime.run(lambda page: page.title())

    assert runtime.run(lambda page: page.title()) == "fixture"
    assert failed.context.closed is True
    assert recovered.context.closed is True


def _raise_runtime_error() -> None:
    raise RuntimeError("boom")


def _raise_browser_operation_error() -> None:
    raise BrowserOperationError(
        "parse failed",
        source_id="demo",
        safe_html="<table><tr><td>safe</td></tr></table>",
    )


class FakePlaywrightFactory:
    def __init__(self, *, start_with_page: bool = True) -> None:
        self.page = FakePage()
        self.context = FakeBrowserContext(self.page, start_with_page=start_with_page)
        self.chromium = FakeChromium(self.context)

    def __call__(self) -> FakePlaywrightFactory:
        return self

    def __enter__(self) -> FakePlaywrightFactory:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> None:
        return None


class FakeChromium:
    def __init__(self, context: FakeBrowserContext) -> None:
        self._context = context
        self.launch_calls: list[dict[str, Any]] = []

    def launch_persistent_context(
        self,
        *,
        user_data_dir: str,
        executable_path: str,
        headless: bool,
    ) -> FakeBrowserContext:
        self.launch_calls.append(
            {
                "user_data_dir": user_data_dir,
                "executable_path": executable_path,
                "headless": headless,
            }
        )
        return self._context


class FakeBrowserContext:
    def __init__(self, page: FakePage, *, start_with_page: bool = True) -> None:
        self.pages = [page] if start_with_page else []
        self._page = page
        self.closed = False
        self.blocked_resource_types: set[str] = set()
        self.raise_on_new_page: RuntimeError | None = None

    def new_page(self) -> FakePage:
        if self.raise_on_new_page is not None:
            raise self.raise_on_new_page
        return self._page

    def route(self, pattern: str, handler: Any) -> None:
        assert pattern == "**/*"
        for resource_type in ("document", "font", "image", "media", "script"):
            route = FakeRoute(resource_type)
            handler(route)
            if route.was_aborted:
                self.blocked_resource_types.add(resource_type)

    def close(self) -> None:
        self.closed = True


class FakePage:
    def __init__(self) -> None:
        self.closed = False
        self.close_attempted = False
        self.close_error: RuntimeError | None = None
        self.default_timeout_ms: int | None = None
        self.default_navigation_timeout_ms: int | None = None

    def title(self) -> str:
        return "fixture"

    def set_default_timeout(self, timeout_ms: int) -> None:
        self.default_timeout_ms = timeout_ms

    def set_default_navigation_timeout(self, timeout_ms: int) -> None:
        self.default_navigation_timeout_ms = timeout_ms

    def close(self) -> None:
        self.close_attempted = True
        if self.close_error is not None:
            raise self.close_error
        self.closed = True


class FakeRoute:
    def __init__(self, resource_type: str) -> None:
        self.request = FakeRequest(resource_type)
        self.was_aborted = False
        self.was_continued = False

    def abort(self) -> None:
        self.was_aborted = True

    def continue_(self) -> None:
        self.was_continued = True


class FakeRequest:
    def __init__(self, resource_type: str) -> None:
        self.resource_type = resource_type
