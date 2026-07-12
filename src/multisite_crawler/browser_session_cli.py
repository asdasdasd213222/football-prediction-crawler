"""Manual non-sensitive refresh recording for dedicated Edge profiles."""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from datetime import datetime
from typing import cast
from zoneinfo import ZoneInfo

from redis import Redis
from redis.exceptions import RedisError

from multisite_crawler.browser_session import (
    BrowserSessionManager,
    BrowserSessionState,
    SessionStateStore,
)

BEIJING = ZoneInfo("Asia/Shanghai")


class BrowserSessionConfigurationError(ValueError):
    """Raised for a missing or invalid non-secret session configuration."""


def record_refresh_from_environment(
    store: SessionStateStore,
    environ: Mapping[str, str],
    *,
    current: datetime,
) -> BrowserSessionState:
    """Record an operator-confirmed profile refresh without session material."""
    profile_reference = environ.get("BROWSER_PROFILE_REFERENCE", "").strip()
    if not profile_reference:
        raise BrowserSessionConfigurationError("BROWSER_PROFILE_REFERENCE is required")
    try:
        return BrowserSessionManager(store).record_manual_refresh(
            profile_reference,
            current,
        )
    except ValueError as error:
        raise BrowserSessionConfigurationError(
            "BROWSER_PROFILE_REFERENCE is invalid"
        ) from error


def format_refresh_result(state: BrowserSessionState) -> str:
    """Render only the safe profile reference, state, and refresh time."""
    refresh_at = state.last_manual_refresh_at
    if refresh_at is None:
        raise RuntimeError("manual refresh did not produce a timestamp")
    return (
        f"profile_reference={state.profile_reference} "
        f"status={state.status.value} refreshed_at={refresh_at.isoformat()}"
    )


def main() -> None:
    """Record a manual refresh after the operator closes the dedicated Edge."""
    parser = argparse.ArgumentParser(prog="browser-session")
    parser.add_argument("command", choices=["record-refresh"])
    arguments = parser.parse_args()
    if arguments.command != "record-refresh":
        raise RuntimeError("unsupported command")
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url:
        raise BrowserSessionConfigurationError("REDIS_URL is required")
    try:
        store = cast(
            SessionStateStore, Redis.from_url(redis_url, decode_responses=True)
        )
        state = record_refresh_from_environment(
            store,
            os.environ,
            current=datetime.now(BEIJING),
        )
    except BrowserSessionConfigurationError as error:
        parser.exit(2, f"browser session configuration error: {error}\n")
    except RedisError:
        parser.exit(1, "browser session refresh storage is unavailable\n")
    print(format_refresh_result(state))


if __name__ == "__main__":
    main()
