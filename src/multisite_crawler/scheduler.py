"""Beijing-time scheduling decisions independent of task transport."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, cast


class SchedulerStore(Protocol):
    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str) -> object: ...


@dataclass(frozen=True)
class SchedulerState:
    """Persisted per-source scheduler state."""

    next_run_at: datetime
    paused: bool


def next_run_at(current: datetime, interval_seconds: int) -> datetime:
    """Return the next Beijing-local run without relying on host timezone."""
    if interval_seconds < 60:
        raise ValueError("interval_seconds must be at least 60")
    return current + timedelta(seconds=interval_seconds)


def should_dispatch(state: SchedulerState, current: datetime) -> bool:
    """Allow one due dispatch unless the source is paused."""
    return not state.paused and current >= state.next_run_at


def state_key(source_id: str) -> str:
    """Return the Redis key for one source scheduler state."""
    return f"scheduler:{source_id}"


class SchedulerService:
    """Redis-backed per-source dispatch state without overlap locking."""

    def __init__(self, store: SchedulerStore, dispatch: Callable[[str], None]) -> None:
        self._store = store
        self._dispatch = dispatch

    def register(
        self, source_id: str, interval_seconds: int, current: datetime
    ) -> None:
        next_run_at(current, interval_seconds)
        self._store.set(
            state_key(source_id),
            json.dumps(
                {
                    "interval": interval_seconds,
                    "paused": False,
                    "next": current.isoformat(),
                }
            ),
        )

    def register_if_missing(
        self, source_id: str, interval_seconds: int, current: datetime
    ) -> bool:
        """Create initial state only when Redis has no prior scheduler state."""
        if self._store.get(state_key(source_id)) is not None:
            return False
        self.register(source_id, interval_seconds, current)
        return True

    def pause(self, source_id: str, paused: bool) -> None:
        state = self._load(source_id)
        state["paused"] = paused
        self._save(source_id, state)

    def manual_trigger(self, source_id: str) -> None:
        self._dispatch(source_id)

    def next_run(self, source_id: str) -> datetime:
        return datetime.fromisoformat(str(self._load(source_id)["next"]))

    def tick(self, source_id: str, current: datetime) -> bool:
        state = self._load(source_id)
        schedule = SchedulerState(
            datetime.fromisoformat(str(state["next"])), bool(state["paused"])
        )
        if not should_dispatch(schedule, current):
            return False
        interval = state["interval"]
        if isinstance(interval, bool) or not isinstance(interval, int):
            raise ValueError("Scheduler interval must be an integer")
        state["next"] = next_run_at(current, interval).isoformat()
        state["last_dispatch"] = current.isoformat()
        self._save(source_id, state)
        self._dispatch(source_id)
        return True

    def _load(self, source_id: str) -> dict[str, object]:
        value = self._store.get(state_key(source_id))
        if value is None:
            raise KeyError(f"Unknown scheduled source: {source_id}")
        return cast(dict[str, object], json.loads(value))

    def _save(self, source_id: str, state: dict[str, object]) -> None:
        self._store.set(state_key(source_id), json.dumps(state))
