"""Site-neutral renewable Redis leases for source task overlap control."""

from __future__ import annotations

from threading import Event, Thread
from typing import Protocol
from uuid import uuid4

RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""
RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""


class RedisLeaseStore(Protocol):
    """The minimal Redis operations required for a safe lease."""

    def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool | None: ...

    def eval(self, script: str, numkeys: int, *args: object) -> object: ...


def source_lock_key(source_id: str) -> str:
    """Return the default lock key for a single source task."""
    return f"crawler:lock:source:{source_id}"


def page_lock_key(source_id: str, page_id: str) -> str:
    """Return a finer-grained lock key for a future paginated source task."""
    return f"{source_lock_key(source_id)}:page:{page_id}"


class RedisLease:
    """A token-owned Redis lease that can only be renewed or released by owner."""

    def __init__(
        self,
        store: RedisLeaseStore,
        key: str,
        *,
        ttl_seconds: int,
        token: str | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._store = store
        self.key = key
        self.ttl_seconds = ttl_seconds
        self.token = token or uuid4().hex

    def acquire(self) -> bool:
        """Atomically acquire this lease if no other owner currently holds it."""
        return bool(
            self._store.set(
                self.key,
                self.token,
                nx=True,
                ex=self.ttl_seconds,
            )
        )

    def renew(self) -> bool:
        """Extend the lease only when its owner token still matches."""
        return bool(
            self._store.eval(
                RENEW_SCRIPT,
                1,
                self.key,
                self.token,
                self.ttl_seconds,
            )
        )

    def release(self) -> bool:
        """Delete the lease only when its owner token still matches."""
        return bool(self._store.eval(RELEASE_SCRIPT, 1, self.key, self.token))


class LeaseHeartbeat:
    """Renew a held lease until its owner finishes or loses ownership."""

    def __init__(self, lease: RedisLease, interval_seconds: float) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._lease = lease
        self._interval_seconds = interval_seconds
        self._stop_event = Event()
        self._thread = Thread(target=self._run, daemon=True)

    def start(self) -> None:
        """Start the background lease renewal loop."""
        self._thread.start()

    def stop(self) -> None:
        """Stop renewal before a token-safe release."""
        self._stop_event.set()
        self._thread.join()

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval_seconds):
            if not self._lease.renew():
                return
