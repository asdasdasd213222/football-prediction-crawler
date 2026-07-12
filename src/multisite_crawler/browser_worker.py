"""Windows host entry point for the dedicated browser queue worker."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from multisite_crawler.browser_runtime import (
    BrowserRuntimeConfigurationError,
    BrowserRuntimeSettings,
)
from multisite_crawler.tasks import celery_app


def browser_worker_argv(environ: Mapping[str, str]) -> list[str]:
    """Return browser-only Celery arguments with explicit concurrency."""
    concurrency = _positive_integer(
        environ.get("BROWSER_WORKER_CONCURRENCY", "1"),
        "BROWSER_WORKER_CONCURRENCY",
    )
    if concurrency != 1:
        raise BrowserRuntimeConfigurationError(
            "BROWSER_WORKER_CONCURRENCY must be 1 for a shared Edge profile"
        )
    memory_megabytes = _positive_integer(
        environ.get("BROWSER_MAX_MEMORY_MB", "1024"),
        "BROWSER_MAX_MEMORY_MB",
    )
    return [
        "worker",
        "--queues=browser",
        "--loglevel=INFO",
        f"--concurrency={concurrency}",
        f"--max-memory-per-child={memory_megabytes * 1024}",
    ]


def _positive_integer(raw_value: str, variable_name: str) -> int:
    """Parse one non-secret positive integer worker setting."""
    try:
        value = int(raw_value)
    except ValueError as error:
        raise BrowserRuntimeConfigurationError(
            f"{variable_name} must be a positive integer"
        ) from error
    if value < 1:
        raise BrowserRuntimeConfigurationError(
            f"{variable_name} must be a positive integer"
        )
    return value


def validate_browser_runtime_settings(
    environ: Mapping[str, str] | None = None,
) -> None:
    """Validate host Edge settings before Celery starts consuming work."""
    BrowserRuntimeSettings.from_environment(
        os.environ if environ is None else environ,
        repository_root=Path(__file__).resolve().parents[2],
    )


def main() -> None:
    """Validate settings and start a worker restricted to the browser queue."""
    validate_browser_runtime_settings()
    celery_app.worker_main(browser_worker_argv(os.environ))


if __name__ == "__main__":
    main()
