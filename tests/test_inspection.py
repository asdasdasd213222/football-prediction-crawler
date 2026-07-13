from __future__ import annotations

import json
from pathlib import Path

import pytest

from multisite_crawler.inspection import (
    InspectionInputError,
    build_daily_report,
    load_health_report_input,
    main,
    parse_health_report_input,
    render_markdown,
)

FIXTURES = Path(__file__).parent / "fixtures/inspection"


def test_healthy_input_produces_a_concise_beijing_report() -> None:
    health_input = load_health_report_input(FIXTURES / "healthy.json")

    report = build_daily_report(health_input)
    rendered = render_markdown(report)

    assert report.status == "healthy"
    assert report.window_start == "2026-07-12T08:00:00+08:00"
    assert report.sources[0].failure_rate == 0
    assert report.sources[0].findings == ()
    assert "# Crawler Daily Inspection" in rendered
    assert "`demo_api`" in rendered


def test_attention_report_includes_each_actionable_safe_finding() -> None:
    health_input = load_health_report_input(FIXTURES / "attention.json")

    report = build_daily_report(health_input)
    rendered = render_markdown(report)

    assert report.requires_action
    assert report.status == "attention"
    findings = report.sources[0].findings
    assert "failure rate at or above 20%" in findings
    assert "last success is older than 24 hours" in findings
    assert "item count deviates by at least 50%" in findings
    assert "new parser-failure snapshots require review" in findings
    assert "observed HTTP 401, 403, or 429" in findings
    assert "queue depth at or above 100" in findings
    assert "circuit breaker is open" in findings
    assert "HTTP 401/403/429: `401=0, 403=1, 429=2`" in rendered


def test_input_rejects_secrets_and_unbounded_unknown_fields() -> None:
    document = json.loads((FIXTURES / "healthy.json").read_text(encoding="utf-8"))
    document["sources"][0]["authorization"] = "not-permitted"

    with pytest.raises(InspectionInputError, match="unexpected authorization"):
        parse_health_report_input(document)


def test_no_sources_produces_a_trackable_setup_review_report() -> None:
    report = build_daily_report(
        parse_health_report_input(
            {"window_end": "2026-07-13T08:00:00+08:00", "sources": []}
        )
    )

    assert report.status == "no_data"
    assert "Human setup review is required." in render_markdown(report)


def test_cli_writes_deterministic_json_and_markdown_outputs(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    markdown_output = tmp_path / "report.md"

    exit_code = main(
        [
            "--input",
            str(FIXTURES / "healthy.json"),
            "--output",
            str(output),
            "--markdown-output",
            str(markdown_output),
            "--now",
            "2026-07-13T08:01:00+08:00",
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["generated_at"] == "2026-07-13T08:01:00+08:00"
    assert payload["status"] == "healthy"
    assert "Status: `healthy`" in markdown_output.read_text(encoding="utf-8")
