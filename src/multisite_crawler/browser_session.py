"""Non-sensitive lifecycle state for dedicated Edge profiles."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from zoneinfo import ZoneInfo

BEIJING = ZoneInfo("Asia/Shanghai")
_PROFILE_REFERENCE_PATTERN = re.compile(r"^[a-z0-9_]+$")


class SessionStateStore(Protocol):
    """Minimal Redis-shaped store for non-sensitive session state."""

    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str) -> object: ...


class BrowserSessionStatus(StrEnum):
    """Persisted generic state for one dedicated browser profile."""

    UNKNOWN = "unknown"
    READY = "ready"
    LOGIN_REQUIRED = "login_required"
    ACCESS_DENIED = "access_denied"
    CAPTCHA = "captcha"


class BrowserSessionObservation(StrEnum):
    """Safe adapter-provided observation without page text or selectors."""

    READY = "ready"
    LOGIN_REQUIRED = "login_required"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    CAPTCHA = "captcha"
    ACCESS_CONTROL = "access_control"


@dataclass(frozen=True)
class BrowserSessionState:
    """Non-sensitive latest state for an opaque profile reference."""

    profile_reference: str
    status: BrowserSessionStatus
    last_manual_refresh_at: datetime | None
    reason: str | None


class BrowserSessionRequiredError(RuntimeError):
    """Raised when an observation requires an operator to review the profile."""

    def __init__(self, state: BrowserSessionState) -> None:
        self.profile_reference = state.profile_reference
        self.status = state.status
        self.reason = state.reason
        super().__init__(
            "browser session requires human review: "
            f"profile_reference={state.profile_reference} "
            f"status={state.status.value} reason={state.reason}"
        )


class BrowserSessionManager:
    """Store manual refreshes and stop terminal browser-session outcomes."""

    def __init__(self, store: SessionStateStore) -> None:
        self._store = store

    def get_state(self, profile_reference: str) -> BrowserSessionState:
        _validate_profile_reference(profile_reference)
        value = self._store.get(_state_key(profile_reference))
        if value is None:
            return _unknown_state(profile_reference)
        return _deserialize_state(profile_reference, value)

    def record_manual_refresh(
        self, profile_reference: str, current: datetime
    ) -> BrowserSessionState:
        _validate_profile_reference(profile_reference)
        _validate_beijing_datetime(current)
        state = BrowserSessionState(
            profile_reference=profile_reference,
            status=BrowserSessionStatus.READY,
            last_manual_refresh_at=current,
            reason=None,
        )
        self._save(state)
        return state

    def record_observation(
        self,
        profile_reference: str,
        observation: BrowserSessionObservation,
        current: datetime,
    ) -> BrowserSessionState:
        _validate_profile_reference(profile_reference)
        _validate_beijing_datetime(current)
        status, reason = _observation_state(observation)
        state = BrowserSessionState(
            profile_reference=profile_reference,
            status=status,
            last_manual_refresh_at=None,
            reason=reason,
        )
        self._save(state)
        if status is not BrowserSessionStatus.READY:
            raise BrowserSessionRequiredError(state)
        return state

    def _save(self, state: BrowserSessionState) -> None:
        payload = asdict(state)
        refresh_at = state.last_manual_refresh_at
        payload["last_manual_refresh_at"] = (
            refresh_at.isoformat() if refresh_at is not None else None
        )
        payload["status"] = state.status.value
        self._store.set(
            _state_key(state.profile_reference),
            json.dumps(payload, separators=(",", ":"), sort_keys=False),
        )


def _state_key(profile_reference: str) -> str:
    return f"browser-session:{profile_reference}"


def _unknown_state(profile_reference: str) -> BrowserSessionState:
    return BrowserSessionState(
        profile_reference=profile_reference,
        status=BrowserSessionStatus.UNKNOWN,
        last_manual_refresh_at=None,
        reason=None,
    )


def _deserialize_state(profile_reference: str, value: str) -> BrowserSessionState:
    try:
        payload = json.loads(value)
        if not isinstance(payload, Mapping):
            raise ValueError("state must be a mapping")
        if payload.get("profile_reference") != profile_reference:
            raise ValueError("profile reference mismatch")
        status = BrowserSessionStatus(payload["status"])
        reason = payload.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise ValueError("reason must be a string")
        refresh_value = payload.get("last_manual_refresh_at")
        refresh_at = None
        if refresh_value is not None:
            if not isinstance(refresh_value, str):
                raise ValueError("refresh time must be a string")
            refresh_at = datetime.fromisoformat(refresh_value)
            _validate_beijing_datetime(refresh_at)
        return BrowserSessionState(profile_reference, status, refresh_at, reason)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return _unknown_state(profile_reference)


def _observation_state(
    observation: BrowserSessionObservation,
) -> tuple[BrowserSessionStatus, str | None]:
    if observation is BrowserSessionObservation.READY:
        return BrowserSessionStatus.READY, None
    if observation is BrowserSessionObservation.LOGIN_REQUIRED:
        return BrowserSessionStatus.LOGIN_REQUIRED, "login_required"
    if observation is BrowserSessionObservation.CAPTCHA:
        return BrowserSessionStatus.CAPTCHA, "captcha"
    if observation is BrowserSessionObservation.UNAUTHORIZED:
        return BrowserSessionStatus.ACCESS_DENIED, "unauthorized"
    if observation is BrowserSessionObservation.FORBIDDEN:
        return BrowserSessionStatus.ACCESS_DENIED, "forbidden"
    return BrowserSessionStatus.ACCESS_DENIED, "access_control"


def _validate_profile_reference(profile_reference: str) -> None:
    if not _PROFILE_REFERENCE_PATTERN.fullmatch(profile_reference):
        raise ValueError("profile reference must match [a-z0-9_]+")


def _validate_beijing_datetime(value: datetime) -> None:
    if value.tzinfo != BEIJING:
        raise ValueError("timestamp must be timezone-aware Beijing time")
