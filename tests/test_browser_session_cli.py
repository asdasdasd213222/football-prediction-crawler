from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from multisite_crawler.browser_session_cli import (
    BrowserSessionConfigurationError,
    format_refresh_result,
    main,
    record_refresh_from_environment,
)

BEIJING_NOW = datetime(2026, 7, 12, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


class MemoryStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value


def test_cli_requires_a_non_secret_profile_reference() -> None:
    with pytest.raises(BrowserSessionConfigurationError, match="PROFILE_REFERENCE"):
        record_refresh_from_environment(MemoryStore(), {}, current=BEIJING_NOW)


def test_cli_configuration_error_does_not_print_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("BROWSER_PROFILE_REFERENCE", raising=False)
    monkeypatch.setattr(sys, "argv", ["browser-session", "record-refresh"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    captured = capsys.readouterr()
    assert exit_info.value.code == 2
    assert "configuration error" in captured.err
    assert "Traceback" not in captured.err
    assert "redis://" not in captured.err


def test_cli_records_refresh_without_paths_or_sensitive_values() -> None:
    state = record_refresh_from_environment(
        MemoryStore(),
        {"BROWSER_PROFILE_REFERENCE": "sporttery_primary"},
        current=BEIJING_NOW,
    )

    rendered = format_refresh_result(state)

    assert "sporttery_primary" in rendered
    assert "ready" in rendered
    assert "2026-07-12T09:30:00+08:00" in rendered
    for marker in ("cookie", "token", "authorization", "password", "account", "D:\\"):
        assert marker not in rendered.lower()


def test_manual_edge_helper_has_no_source_or_credential_parameter() -> None:
    script = Path("scripts/open_edge_profile.ps1").read_text(encoding="utf-8")

    assert "about:blank" in script
    assert "must be outside the repository root" in script
    assert "[switch]$Open" in script
    assert "[switch]$RecordRefresh" in script
    assert "-Url" not in script
    assert "-Password" not in script
    assert "-Cookie" not in script
