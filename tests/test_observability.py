from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import UUID

import pytest

from multisite_crawler.observability import (
    JsonEventFormatter,
    LoggingSettings,
    ObservabilityConfigurationError,
    RunContext,
    RunEvent,
    RunOutcome,
)


def test_json_event_includes_trace_fields_and_redacts_sensitive_values() -> None:
    context = RunContext(
        source_id="demo_api",
        crawl_run_id=UUID("00000000-0000-0000-0000-000000000001"),
        task_id="task-1",
    )
    event = RunEvent(
        name="run_finished",
        context=context,
        outcome=RunOutcome.SUCCEEDED,
        duration_seconds=1.5,
        item_count=2,
        extra={
            "Authorization": "secret-value",
            "url": "https://name:password@example.invalid/path?token=leak",
            "nested": {"account_email": "person@example.invalid"},
        },
    )
    record = logging.makeLogRecord(
        {"name": "test.observability", "levelno": logging.INFO, "run_event": event}
    )

    payload = json.loads(JsonEventFormatter().format(record))

    assert payload["source_id"] == "demo_api"
    assert payload["crawl_run_id"] == "00000000-0000-0000-0000-000000000001"
    assert payload["task_id"] == "task-1"
    assert payload["outcome"] == "succeeded"
    assert payload["duration_seconds"] == 1.5
    assert payload["item_count"] == 2
    rendered = json.dumps(payload)
    assert "secret-value" not in rendered
    assert "password" not in rendered
    assert "token=leak" not in rendered
    assert "person@example.invalid" not in rendered
    assert payload["details"]["url"] == "https://example.invalid/path"


def test_failed_event_keeps_exception_type_but_not_exception_message() -> None:
    event = RunEvent(
        name="run_failed",
        context=RunContext("demo_api", UUID(int=2), "task-2"),
        outcome=RunOutcome.FAILED,
        exception=ValueError("password=not-for-logs"),
    )
    record = logging.makeLogRecord(
        {"name": "test.observability", "levelno": logging.ERROR, "run_event": event}
    )

    rendered = JsonEventFormatter().format(record)

    assert '"exception_type":"ValueError"' in rendered
    assert "password=not-for-logs" not in rendered


def test_logging_settings_reject_repository_local_log_directory(tmp_path: Path) -> None:
    with pytest.raises(ObservabilityConfigurationError, match="outside the repository"):
        LoggingSettings.from_environment(
            {"LOG_FILE_DIR": str(tmp_path)},
            repository_root=tmp_path,
        )


def test_logging_settings_accepts_external_rotating_log_directory(
    tmp_path: Path,
) -> None:
    directory = tmp_path.parent / "crawler-logs"

    settings = LoggingSettings.from_environment(
        {
            "LOG_FILE_DIR": str(directory),
            "LOG_MAX_BYTES": "1024",
            "LOG_BACKUP_COUNT": "3",
        },
        repository_root=tmp_path,
    )

    assert settings.log_file_dir == directory.resolve()
    assert settings.max_bytes == 1024
    assert settings.backup_count == 3
