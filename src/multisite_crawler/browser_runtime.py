"""Strict environment settings for the dedicated local Edge runtime."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeVar

from multisite_crawler.browser_artifacts import BrowserArtifactWriter


class BrowserRuntimeConfigurationError(ValueError):
    """Raised when the browser runtime would use an unsafe local path."""


class BrowserOperationError(RuntimeError):
    """An adapter failure that may include a safe fragment for diagnostics."""

    def __init__(self, message: str, *, source_id: str, safe_html: str) -> None:
        super().__init__(message)
        self.source_id = source_id
        self.safe_html = safe_html


T = TypeVar("T")


class BrowserPage(Protocol):
    """Narrow page protocol for generic browser operations."""

    def set_default_timeout(self, timeout_ms: int) -> None: ...

    def set_default_navigation_timeout(self, timeout_ms: int) -> None: ...

    def close(self) -> None: ...


class BrowserRequest(Protocol):
    """Narrow request protocol used by resource blocking."""

    @property
    def resource_type(self) -> str: ...


class BrowserRoute(Protocol):
    """Narrow route protocol used by resource blocking."""

    request: BrowserRequest

    def abort(self) -> None: ...

    def continue_(self) -> None: ...


class BrowserContext(Protocol):
    """Narrow persistent-context protocol for managed runtime tests."""

    pages: list[BrowserPage]

    def new_page(self) -> BrowserPage: ...

    def route(self, pattern: str, handler: Callable[[BrowserRoute], None]) -> None: ...

    def close(self) -> None: ...


class BrowserChromium(Protocol):
    """Chromium launcher protocol."""

    def launch_persistent_context(
        self,
        *,
        user_data_dir: str,
        executable_path: str,
        headless: bool,
    ) -> BrowserContext: ...


class PlaywrightGateway(Protocol):
    """Context-managed Playwright gateway."""

    chromium: BrowserChromium

    def __enter__(self) -> PlaywrightGateway: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> None: ...


@dataclass(frozen=True)
class BrowserRuntimeSettings:
    """Validated local host settings for the dedicated Edge runtime."""

    edge_executable_path: Path
    user_data_dir: Path
    failure_snapshot_dir: Path
    page_timeout_seconds: float
    action_timeout_seconds: float

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str],
        *,
        repository_root: Path,
    ) -> BrowserRuntimeSettings:
        resolved_repository_root = repository_root.resolve()

        edge_executable_path = _require_existing_external_file(
            environ,
            "BROWSER_EDGE_EXECUTABLE_PATH",
            resolved_repository_root,
        )
        user_data_dir = _require_external_directory(
            environ,
            "BROWSER_USER_DATA_DIR",
            resolved_repository_root,
        )
        failure_snapshot_dir = _require_external_directory(
            environ,
            "BROWSER_FAILURE_SNAPSHOT_DIR",
            resolved_repository_root,
        )
        page_timeout_seconds = _require_positive_timeout(
            environ,
            "BROWSER_PAGE_TIMEOUT_SECONDS",
        )
        action_timeout_seconds = _require_positive_timeout(
            environ,
            "BROWSER_ACTION_TIMEOUT_SECONDS",
        )

        _ensure_snapshot_directory(failure_snapshot_dir)

        return cls(
            edge_executable_path=edge_executable_path,
            user_data_dir=user_data_dir,
            failure_snapshot_dir=failure_snapshot_dir,
            page_timeout_seconds=page_timeout_seconds,
            action_timeout_seconds=action_timeout_seconds,
        )


class ManagedEdgeRuntime:
    """Manage a local Edge persistent context for one browser operation."""

    def __init__(
        self,
        settings: BrowserRuntimeSettings,
        *,
        playwright_factory: Callable[[], PlaywrightGateway],
        artifact_writer: BrowserArtifactWriter | None = None,
    ) -> None:
        self._settings = settings
        self._playwright_factory = playwright_factory
        self._artifact_writer = artifact_writer

    def run(self, operation: Callable[[BrowserPage], T]) -> T:
        with self._playwright_factory() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(self._settings.user_data_dir),
                executable_path=str(self._settings.edge_executable_path),
                headless=False,
            )
            page: BrowserPage | None = None
            operation_error: BaseException | None = None
            try:
                page = context.pages[0] if context.pages else context.new_page()
                context.route("**/*", self._block_unneeded_resources)
                page.set_default_timeout(
                    int(self._settings.action_timeout_seconds * 1000)
                )
                page.set_default_navigation_timeout(
                    int(self._settings.page_timeout_seconds * 1000)
                )
                return operation(page)
            except BaseException as error:
                operation_error = error
                if isinstance(error, BrowserOperationError):
                    self._persist_failure_artifact(error)
                raise
            finally:
                self._close_page_and_context(
                    page=page,
                    context=context,
                    suppress_cleanup_errors=operation_error is not None,
                )

    def _persist_failure_artifact(self, error: BrowserOperationError) -> None:
        if self._artifact_writer is None:
            return
        self._artifact_writer.write_failure(
            source_id=error.source_id,
            safe_html=error.safe_html,
            screenshot=None,
        )

    @staticmethod
    def _block_unneeded_resources(route: BrowserRoute) -> None:
        if route.request.resource_type in {"font", "image", "media"}:
            route.abort()
            return
        route.continue_()

    @staticmethod
    def _close_page_and_context(
        *,
        page: BrowserPage | None,
        context: BrowserContext,
        suppress_cleanup_errors: bool,
    ) -> None:
        page_error: BaseException | None = None
        if page is not None:
            try:
                page.close()
            except BaseException as error:
                if not suppress_cleanup_errors:
                    page_error = error

        try:
            context.close()
        except BaseException as error:
            if suppress_cleanup_errors:
                return
            if page_error is not None:
                raise error from page_error
            raise

        if page_error is not None:
            raise page_error


def _require_existing_external_file(
    environ: Mapping[str, str],
    variable_name: str,
    repository_root: Path,
) -> Path:
    path = _require_external_path(environ, variable_name, repository_root)
    if not path.exists():
        raise BrowserRuntimeConfigurationError(
            f"{variable_name} must point to an existing file"
        )
    if not path.is_file():
        raise BrowserRuntimeConfigurationError(
            f"{variable_name} must point to an existing file"
        )
    return path


def _require_external_directory(
    environ: Mapping[str, str],
    variable_name: str,
    repository_root: Path,
) -> Path:
    path = _require_external_path(environ, variable_name, repository_root)
    if path.exists() and not path.is_dir():
        raise BrowserRuntimeConfigurationError(
            f"{variable_name} must point to a directory"
        )
    return path


def _require_external_path(
    environ: Mapping[str, str],
    variable_name: str,
    repository_root: Path,
) -> Path:
    raw_value = environ.get(variable_name, "")
    if not raw_value.strip():
        raise BrowserRuntimeConfigurationError(f"{variable_name} is required")

    candidate_path = Path(raw_value)
    if not candidate_path.is_absolute():
        raise BrowserRuntimeConfigurationError(f"{variable_name} must be absolute")

    resolved_path = candidate_path.resolve()
    if resolved_path.is_relative_to(repository_root):
        raise BrowserRuntimeConfigurationError(
            f"{variable_name} must be outside the repository root"
        )
    return resolved_path


def _require_positive_timeout(
    environ: Mapping[str, str],
    variable_name: str,
) -> float:
    raw_value = environ.get(variable_name, "")
    if not raw_value.strip():
        raise BrowserRuntimeConfigurationError(f"{variable_name} is required")

    try:
        parsed_value = float(raw_value)
    except ValueError as error:
        raise BrowserRuntimeConfigurationError(
            f"{variable_name} must be a finite positive number"
        ) from error
    if not math.isfinite(parsed_value) or parsed_value <= 0:
        raise BrowserRuntimeConfigurationError(
            f"{variable_name} must be a finite positive number"
        )
    return parsed_value


def _ensure_snapshot_directory(path: Path) -> None:
    if path.exists() and not path.is_dir():
        raise BrowserRuntimeConfigurationError(
            "BROWSER_FAILURE_SNAPSHOT_DIR must point to a directory"
        )
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise BrowserRuntimeConfigurationError(
            "BROWSER_FAILURE_SNAPSHOT_DIR could not be created"
        ) from error
