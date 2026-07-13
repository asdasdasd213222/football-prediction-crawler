"""Read-only, redaction-safe daily health inspection reporting."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

BEIJING = ZoneInfo("Asia/Shanghai")
_SOURCE_ID = re.compile(r"^[a-z0-9_-]+$")
_INSPECTION_WINDOW = timedelta(hours=24)
_MAX_QUEUE_DEPTH = 100
_MAX_FAILURE_RATE = 0.2
_MAX_ITEM_DEVIATION = 0.5
_INTERESTING_HTTP_STATUSES = ("401", "403", "429")


class InspectionInputError(ValueError):
    """Raised when a health-report input is not safe or structurally valid."""


@dataclass(frozen=True)
class SourceHealthInput:
    """Safe aggregate health data for one source over the inspection window."""

    source_id: str
    runs_succeeded: int
    runs_failed: int
    last_success_at: datetime | None
    average_duration_seconds: float
    p95_duration_seconds: float
    item_count: int
    baseline_item_count: int | None
    parse_failure_snapshot_count: int
    http_statuses: Mapping[str, int]
    queue_depth: int
    circuit_breaker_open: bool


@dataclass(frozen=True)
class HealthReportInput:
    """A complete safe 24-hour health-report input."""

    window_end: datetime
    sources: tuple[SourceHealthInput, ...]


@dataclass(frozen=True)
class SourceInspection:
    """Stable summary and findings for one source."""

    source_id: str
    failure_rate: float
    last_success_at: str | None
    average_duration_seconds: float
    p95_duration_seconds: float
    item_count: int
    baseline_item_count: int | None
    parse_failure_snapshot_count: int
    http_statuses: Mapping[str, int]
    queue_depth: int
    circuit_breaker_open: bool
    findings: tuple[str, ...]


@dataclass(frozen=True)
class DailyInspectionReport:
    """Machine-trackable report without runtime secrets or source payloads."""

    schema_version: int
    generated_at: str
    window_start: str
    window_end: str
    status: str
    sources: tuple[SourceInspection, ...]

    @property
    def requires_action(self) -> bool:
        return self.status == "attention"

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


def load_health_report_input(path: Path) -> HealthReportInput:
    """Load a non-secret aggregate health document from a local file."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InspectionInputError(
            "health report input is not readable JSON"
        ) from error
    return parse_health_report_input(document)


def parse_health_report_input(document: object) -> HealthReportInput:
    """Validate the bounded public-health document used by daily inspection."""
    root = _mapping(document, "health report")
    _only_keys(root, {"window_end", "sources"}, "health report")
    window_end = _timestamp(root.get("window_end"), "window_end")
    raw_sources = root.get("sources")
    if not isinstance(raw_sources, list):
        raise InspectionInputError("sources must be a list")
    sources = tuple(_source_input(raw_source) for raw_source in raw_sources)
    source_ids = [source.source_id for source in sources]
    if len(source_ids) != len(set(source_ids)):
        raise InspectionInputError("sources must not repeat source_id")
    return HealthReportInput(window_end=window_end, sources=sources)


def build_daily_report(
    health_input: HealthReportInput, *, now: datetime | None = None
) -> DailyInspectionReport:
    """Evaluate a fixed 24-hour input into safe actionable findings."""
    generated_at = _beijing_timestamp(now or health_input.window_end, "now")
    reports = tuple(
        _inspect_source(source, health_input.window_end)
        for source in health_input.sources
    )
    status = "no_data" if not reports else "healthy"
    if any(source.findings for source in reports):
        status = "attention"
    return DailyInspectionReport(
        schema_version=1,
        generated_at=generated_at.isoformat(),
        window_start=(health_input.window_end - _INSPECTION_WINDOW).isoformat(),
        window_end=health_input.window_end.isoformat(),
        status=status,
        sources=reports,
    )


def render_markdown(report: DailyInspectionReport) -> str:
    """Render a concise stable report suitable for a GitHub step summary or issue."""
    lines = [
        "# Crawler Daily Inspection",
        "",
        f"- Status: `{report.status}`",
        f"- Window: `{report.window_start}` to `{report.window_end}`",
        f"- Generated: `{report.generated_at}`",
    ]
    if report.status == "no_data":
        lines.extend(
            (
                "",
                "No safe health-report input was supplied. "
                "Human setup review is required.",
            )
        )
        return "\n".join(lines) + "\n"
    for source in report.sources:
        baseline = (
            str(source.baseline_item_count)
            if source.baseline_item_count is not None
            else "none"
        )
        lines.extend(
            (
                "",
                f"## `{source.source_id}`",
                f"- Failure rate: `{source.failure_rate:.2%}`",
                f"- Last success: `{source.last_success_at or 'none'}`",
                "- Duration: "
                f"average `{source.average_duration_seconds:.3f}s`, "
                f"P95 `{source.p95_duration_seconds:.3f}s`",
                f"- Items: current `{source.item_count}`, baseline `{baseline}`",
                f"- Parse-failure snapshots: `{source.parse_failure_snapshot_count}`",
                f"- HTTP 401/403/429: `{_status_summary(source.http_statuses)}`",
                f"- Queue depth: `{source.queue_depth}`",
                f"- Circuit breaker open: `{str(source.circuit_breaker_open).lower()}`",
            )
        )
        if source.findings:
            lines.append("- Findings: " + "; ".join(source.findings))
    return "\n".join(lines) + "\n"


def main(arguments: Sequence[str] | None = None) -> int:
    """Write machine and human readable reports from a bounded local input."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--now", type=str)
    args = parser.parse_args(arguments)
    try:
        health_input = load_health_report_input(args.input)
        now = _timestamp(args.now, "now") if args.now is not None else None
        report = build_daily_report(health_input, now=now)
    except InspectionInputError as error:
        parser.error(str(error))
    args.output.write_text(report.to_json() + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    return 0


def _source_input(value: object) -> SourceHealthInput:
    source = _mapping(value, "source")
    _only_keys(
        source,
        {
            "source_id",
            "runs_succeeded",
            "runs_failed",
            "last_success_at",
            "average_duration_seconds",
            "p95_duration_seconds",
            "item_count",
            "baseline_item_count",
            "parse_failure_snapshot_count",
            "http_statuses",
            "queue_depth",
            "circuit_breaker_open",
        },
        "source",
    )
    source_id = source.get("source_id")
    if not isinstance(source_id, str) or not _SOURCE_ID.fullmatch(source_id):
        raise InspectionInputError("source_id must match [a-z0-9_-]+")
    return SourceHealthInput(
        source_id=source_id,
        runs_succeeded=_nonnegative_int(source.get("runs_succeeded"), "runs_succeeded"),
        runs_failed=_nonnegative_int(source.get("runs_failed"), "runs_failed"),
        last_success_at=_optional_timestamp(source.get("last_success_at")),
        average_duration_seconds=_nonnegative_number(
            source.get("average_duration_seconds"), "average_duration_seconds"
        ),
        p95_duration_seconds=_nonnegative_number(
            source.get("p95_duration_seconds"), "p95_duration_seconds"
        ),
        item_count=_nonnegative_int(source.get("item_count"), "item_count"),
        baseline_item_count=_optional_nonnegative_int(
            source.get("baseline_item_count")
        ),
        parse_failure_snapshot_count=_nonnegative_int(
            source.get("parse_failure_snapshot_count"),
            "parse_failure_snapshot_count",
        ),
        http_statuses=_http_statuses(source.get("http_statuses")),
        queue_depth=_nonnegative_int(source.get("queue_depth"), "queue_depth"),
        circuit_breaker_open=_boolean(
            source.get("circuit_breaker_open"), "circuit_breaker_open"
        ),
    )


def _inspect_source(
    source: SourceHealthInput, window_end: datetime
) -> SourceInspection:
    total_runs = source.runs_succeeded + source.runs_failed
    failure_rate = source.runs_failed / total_runs if total_runs else 0.0
    findings: list[str] = []
    if total_runs == 0:
        findings.append("no runs in the inspection window")
    elif failure_rate >= _MAX_FAILURE_RATE:
        findings.append(f"failure rate at or above {_MAX_FAILURE_RATE:.0%}")
    if source.last_success_at is None:
        findings.append("no recorded successful run")
    elif window_end - source.last_success_at > _INSPECTION_WINDOW:
        findings.append("last success is older than 24 hours")
    if _item_count_is_abnormal(source):
        findings.append(f"item count deviates by at least {_MAX_ITEM_DEVIATION:.0%}")
    if source.parse_failure_snapshot_count:
        findings.append("new parser-failure snapshots require review")
    if any(source.http_statuses[status] for status in _INTERESTING_HTTP_STATUSES):
        findings.append("observed HTTP 401, 403, or 429")
    if source.queue_depth >= _MAX_QUEUE_DEPTH:
        findings.append(f"queue depth at or above {_MAX_QUEUE_DEPTH}")
    if source.circuit_breaker_open:
        findings.append("circuit breaker is open")
    return SourceInspection(
        source_id=source.source_id,
        failure_rate=failure_rate,
        last_success_at=(
            source.last_success_at.isoformat()
            if source.last_success_at is not None
            else None
        ),
        average_duration_seconds=source.average_duration_seconds,
        p95_duration_seconds=source.p95_duration_seconds,
        item_count=source.item_count,
        baseline_item_count=source.baseline_item_count,
        parse_failure_snapshot_count=source.parse_failure_snapshot_count,
        http_statuses=source.http_statuses,
        queue_depth=source.queue_depth,
        circuit_breaker_open=source.circuit_breaker_open,
        findings=tuple(findings),
    )


def _item_count_is_abnormal(source: SourceHealthInput) -> bool:
    baseline = source.baseline_item_count
    if baseline is None or baseline == 0:
        return False
    return abs(source.item_count - baseline) / baseline >= _MAX_ITEM_DEVIATION


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise InspectionInputError(f"{name} must be an object")
    return value


def _only_keys(value: Mapping[str, Any], allowed: set[str], name: str) -> None:
    extra = sorted(set(value) - allowed)
    missing = sorted(allowed - set(value))
    if extra or missing:
        detail = ", ".join(
            [
                *(f"unexpected {key}" for key in extra),
                *(f"missing {key}" for key in missing),
            ]
        )
        raise InspectionInputError(f"{name} has invalid fields: {detail}")


def _timestamp(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise InspectionInputError(f"{name} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise InspectionInputError(f"{name} must be an ISO-8601 timestamp") from error
    return _beijing_timestamp(parsed, name)


def _optional_timestamp(value: object) -> datetime | None:
    return None if value is None else _timestamp(value, "last_success_at")


def _beijing_timestamp(value: datetime, name: str) -> datetime:
    if value.tzinfo is None:
        raise InspectionInputError(f"{name} must include a timezone")
    return value.astimezone(BEIJING)


def _nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InspectionInputError(f"{name} must be a non-negative integer")
    return value


def _optional_nonnegative_int(value: object) -> int | None:
    return None if value is None else _nonnegative_int(value, "baseline_item_count")


def _nonnegative_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise InspectionInputError(f"{name} must be a non-negative number")
    return float(value)


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise InspectionInputError(f"{name} must be a boolean")
    return value


def _http_statuses(value: object) -> Mapping[str, int]:
    statuses = _mapping(value, "http_statuses")
    _only_keys(statuses, set(_INTERESTING_HTTP_STATUSES), "http_statuses")
    return {
        status: _nonnegative_int(statuses[status], f"http_statuses.{status}")
        for status in _INTERESTING_HTTP_STATUSES
    }


def _status_summary(statuses: Mapping[str, int]) -> str:
    return ", ".join(
        f"{status}={statuses[status]}" for status in _INTERESTING_HTTP_STATUSES
    )


if __name__ == "__main__":
    raise SystemExit(main())
