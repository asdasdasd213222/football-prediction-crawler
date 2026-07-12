"""Safe structured logging primitives for site-neutral runtime events."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID
from zoneinfo import ZoneInfo

BEIJING = ZoneInfo("Asia/Shanghai")
type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
_SOURCE_ID = re.compile(r"^[a-z0-9_-]+$")
_TASK_ID = re.compile(r"^[A-Za-z0-9_.:-]+$")
_EVENT_NAME = re.compile(r"^[a-z_]+$")
_SENSITIVE_KEY_PARTS = (
    "account",
    "authorization",
    "cookie",
    "credential",
    "email",
    "identity",
    "password",
    "phone",
    "secret",
    "token",
)


class ObservabilityConfigurationError(ValueError):
    """Raised when observability configuration would expose unsafe paths."""


class RunOutcome(StrEnum):
    """Fixed terminal outcome vocabulary used in logs and metrics."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class RunContext:
    """Low-cardinality context that links logs for one collection attempt."""

    source_id: str
    crawl_run_id: UUID
    task_id: str

    def __post_init__(self) -> None:
        if not _SOURCE_ID.fullmatch(self.source_id):
            raise ValueError("source_id must match [a-z0-9_-]+")
        if not _TASK_ID.fullmatch(self.task_id):
            raise ValueError("task_id contains unsupported characters")


@dataclass(frozen=True)
class RunEvent:
    """A typed run event whose formatter exposes only safe fixed fields."""

    name: str
    context: RunContext
    outcome: RunOutcome
    duration_seconds: float | None = None
    item_count: int | None = None
    exception: BaseException | None = None
    extra: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _EVENT_NAME.fullmatch(self.name):
            raise ValueError(
                "event name must contain lowercase letters and underscores"
            )
        if self.duration_seconds is not None and self.duration_seconds < 0:
            raise ValueError("duration_seconds must not be negative")
        if self.item_count is not None and self.item_count < 0:
            raise ValueError("item_count must not be negative")


@dataclass(frozen=True)
class LoggingSettings:
    """Validated console or external rotating-file logging configuration."""

    log_file_dir: Path | None
    max_bytes: int
    backup_count: int

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str],
        *,
        repository_root: Path,
    ) -> LoggingSettings:
        max_bytes = _positive_integer(
            environ.get("LOG_MAX_BYTES", "10485760"), "LOG_MAX_BYTES"
        )
        backup_count = _positive_integer(
            environ.get("LOG_BACKUP_COUNT", "7"), "LOG_BACKUP_COUNT"
        )
        raw_directory = environ.get("LOG_FILE_DIR", "").strip()
        if not raw_directory:
            return cls(None, max_bytes, backup_count)
        directory = Path(raw_directory)
        if not directory.is_absolute():
            raise ObservabilityConfigurationError(
                "LOG_FILE_DIR must be an absolute path"
            )
        resolved_directory = directory.resolve()
        if resolved_directory.is_relative_to(repository_root.resolve()):
            raise ObservabilityConfigurationError(
                "LOG_FILE_DIR must be outside the repository root"
            )
        return cls(resolved_directory, max_bytes, backup_count)


class JsonEventFormatter(logging.Formatter):
    """Serialize only the fixed safe shape of a typed run event."""

    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "run_event", None)
        if not isinstance(event, RunEvent):
            return json.dumps(
                {
                    "timestamp": datetime.fromtimestamp(
                        record.created, BEIJING
                    ).isoformat(),
                    "level": record.levelname,
                    "event": "unstructured_log_suppressed",
                },
                separators=(",", ":"),
            )
        payload: dict[str, JsonValue] = {
            "timestamp": datetime.fromtimestamp(record.created, BEIJING).isoformat(),
            "level": record.levelname,
            "event": event.name,
            "source_id": event.context.source_id,
            "crawl_run_id": str(event.context.crawl_run_id),
            "task_id": event.context.task_id,
            "outcome": event.outcome.value,
        }
        if event.duration_seconds is not None:
            payload["duration_seconds"] = event.duration_seconds
        if event.item_count is not None:
            payload["item_count"] = event.item_count
        if event.exception is not None:
            payload["exception_type"] = type(event.exception).__name__
        if event.extra:
            payload["details"] = redact_value(event.extra)
        return json.dumps(
            payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        )


def redact_value(value: object, *, key: str | None = None) -> JsonValue:
    """Convert data to JSON while removing credential, personal, and URL data."""
    if key is not None and _is_sensitive_key(key):
        return "[redacted]"
    if isinstance(value, str):
        return _safe_url(value) if key is not None and "url" in key.lower() else value
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, Mapping):
        return {
            str(raw_key): redact_value(raw_value, key=str(raw_key))
            for raw_key, raw_value in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact_value(item) for item in value]
    return "[omitted]"


def configure_json_logging(name: str, settings: LoggingSettings) -> logging.Logger:
    """Build a non-propagating logger with console or bounded external output."""
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler: logging.Handler
    if settings.log_file_dir is None:
        handler = logging.StreamHandler()
    else:
        settings.log_file_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            settings.log_file_dir / "crawler.jsonl",
            maxBytes=settings.max_bytes,
            backupCount=settings.backup_count,
            encoding="utf-8",
        )
    handler.setFormatter(JsonEventFormatter())
    logger.addHandler(handler)
    return logger


def emit_run_event(logger: logging.Logger, event: RunEvent) -> None:
    """Emit a typed event without ever formatting exception text."""
    level = logging.ERROR if event.outcome is RunOutcome.FAILED else logging.INFO
    logger.log(level, event.name, extra={"run_event": event})


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(marker in normalized for marker in _SENSITIVE_KEY_PARTS)


def _safe_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "[redacted]"
    netloc = parsed.hostname
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _positive_integer(value: str, variable_name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise ObservabilityConfigurationError(
            f"{variable_name} must be a positive integer"
        ) from error
    if parsed <= 0:
        raise ObservabilityConfigurationError(
            f"{variable_name} must be a positive integer"
        )
    return parsed
