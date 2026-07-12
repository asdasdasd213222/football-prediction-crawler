from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from multisite_crawler.browser_session import (
    BrowserSessionManager,
    BrowserSessionObservation,
    BrowserSessionRequiredError,
    BrowserSessionStatus,
)

BEIJING = ZoneInfo("Asia/Shanghai")
BEIJING_NOW = datetime(2026, 7, 11, 12, 0, tzinfo=BEIJING)
SENSITIVE_MARKERS = ("cookie", "token", "authorization", "password", "account")


class MemoryStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value


def test_manual_refresh_records_beijing_time_and_ready_state() -> None:
    store = MemoryStore()
    manager = BrowserSessionManager(store)

    state = manager.record_manual_refresh("sporttery_primary", BEIJING_NOW)

    assert state.profile_reference == "sporttery_primary"
    assert state.status is BrowserSessionStatus.READY
    assert state.last_manual_refresh_at == BEIJING_NOW
    assert state.reason is None
    assert "cookie" not in store.values["browser-session:sporttery_primary"]


def test_manual_refresh_replaces_terminal_state() -> None:
    store = MemoryStore()
    manager = BrowserSessionManager(store)

    with pytest.raises(BrowserSessionRequiredError):
        manager.record_observation(
            "sporttery_primary", BrowserSessionObservation.CAPTCHA, BEIJING_NOW
        )

    refreshed = manager.record_manual_refresh(
        "sporttery_primary", BEIJING_NOW + timedelta(minutes=5)
    )

    assert refreshed.profile_reference == "sporttery_primary"
    assert refreshed.status is BrowserSessionStatus.READY
    assert refreshed.reason is None
    assert refreshed.last_manual_refresh_at == BEIJING_NOW + timedelta(minutes=5)


def test_repeated_manual_refresh_is_idempotent_except_for_refresh_time() -> None:
    store = MemoryStore()
    manager = BrowserSessionManager(store)

    first = manager.record_manual_refresh("sporttery_primary", BEIJING_NOW)
    second = manager.record_manual_refresh(
        "sporttery_primary", BEIJING_NOW + timedelta(minutes=10)
    )

    assert first.profile_reference == second.profile_reference
    assert second.status is BrowserSessionStatus.READY
    assert second.reason is None
    assert second.last_manual_refresh_at == BEIJING_NOW + timedelta(minutes=10)


@pytest.mark.parametrize("profile_reference", ["Sporttery", "sporttery-primary", ""])
def test_invalid_profile_reference_is_rejected(profile_reference: str) -> None:
    manager = BrowserSessionManager(MemoryStore())

    with pytest.raises(ValueError, match="profile reference"):
        manager.record_manual_refresh(profile_reference, BEIJING_NOW)


def test_manual_refresh_requires_timezone_aware_beijing_time() -> None:
    manager = BrowserSessionManager(MemoryStore())
    naive_now = datetime(2026, 7, 11, 12, 0)

    with pytest.raises(ValueError, match="timezone-aware Beijing"):
        manager.record_manual_refresh("sporttery_primary", naive_now)


def test_manual_refresh_rejects_non_beijing_timezone() -> None:
    manager = BrowserSessionManager(MemoryStore())
    utc_now = datetime(2026, 7, 11, 4, 0, tzinfo=ZoneInfo("UTC"))

    with pytest.raises(ValueError, match="timezone-aware Beijing"):
        manager.record_manual_refresh("sporttery_primary", utc_now)


def test_invalid_json_state_falls_back_to_unknown_state() -> None:
    store = MemoryStore()
    store.set("browser-session:sporttery_primary", "{bad json")
    manager = BrowserSessionManager(store)

    state = manager.get_state("sporttery_primary")

    assert state.profile_reference == "sporttery_primary"
    assert state.status is BrowserSessionStatus.UNKNOWN
    assert state.last_manual_refresh_at is None
    assert state.reason is None


@pytest.mark.parametrize(
    ("observation", "status", "reason"),
    [
        (
            BrowserSessionObservation.LOGIN_REQUIRED,
            BrowserSessionStatus.LOGIN_REQUIRED,
            "login_required",
        ),
        (
            BrowserSessionObservation.UNAUTHORIZED,
            BrowserSessionStatus.ACCESS_DENIED,
            "unauthorized",
        ),
        (
            BrowserSessionObservation.FORBIDDEN,
            BrowserSessionStatus.ACCESS_DENIED,
            "forbidden",
        ),
        (
            BrowserSessionObservation.ACCESS_CONTROL,
            BrowserSessionStatus.ACCESS_DENIED,
            "access_control",
        ),
        (
            BrowserSessionObservation.CAPTCHA,
            BrowserSessionStatus.CAPTCHA,
            "captcha",
        ),
    ],
)
def test_terminal_observation_requires_human_review(
    observation: BrowserSessionObservation,
    status: BrowserSessionStatus,
    reason: str,
) -> None:
    store = MemoryStore()
    manager = BrowserSessionManager(store)

    with pytest.raises(BrowserSessionRequiredError, match=reason) as error_info:
        manager.record_observation("sporttery_primary", observation, BEIJING_NOW)

    state = manager.get_state("sporttery_primary")

    assert state.status is status
    assert state.reason == reason
    assert state.last_manual_refresh_at is None
    assert error_info.value.profile_reference == "sporttery_primary"
    assert error_info.value.status is status
    assert error_info.value.reason == reason


def test_ready_observation_persists_ready_state_without_error() -> None:
    manager = BrowserSessionManager(MemoryStore())

    state = manager.record_observation(
        "sporttery_primary", BrowserSessionObservation.READY, BEIJING_NOW
    )

    assert state.status is BrowserSessionStatus.READY
    assert state.reason is None
    assert state.last_manual_refresh_at is None


def test_serialized_state_contains_only_expected_fields_and_no_sensitive_markers() -> (
    None
):
    store = MemoryStore()
    manager = BrowserSessionManager(store)
    manager.record_manual_refresh("sporttery_primary", BEIJING_NOW)

    serialized = store.values["browser-session:sporttery_primary"]
    payload = json.loads(serialized)

    assert payload == {
        "profile_reference": "sporttery_primary",
        "status": "ready",
        "last_manual_refresh_at": "2026-07-11T12:00:00+08:00",
        "reason": None,
    }
    lowered = serialized.lower()
    assert all(marker not in lowered for marker in SENSITIVE_MARKERS)
