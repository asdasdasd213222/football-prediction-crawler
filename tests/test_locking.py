from __future__ import annotations

from time import sleep

from multisite_crawler.locking import RedisLease, page_lock_key, source_lock_key
from multisite_crawler.tasks import LockOutcome, run_with_source_lease


class MemoryRedis:
    def __init__(self) -> None:
        self.values: dict[str, tuple[str, int]] = {}
        self.renewals = 0

    def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = (value, ex)
        return True

    def eval(
        self, script: str, numkeys: int, key: str, token: str, ttl: int = 0
    ) -> int:
        del numkeys
        value = self.values.get(key)
        if value is None or value[0] != token:
            return 0
        if "expire" in script:
            self.values[key] = (token, ttl)
            self.renewals += 1
        else:
            del self.values[key]
        return 1

    def expire(self, key: str) -> None:
        self.values.pop(key, None)


def test_one_source_lease_excludes_a_concurrent_owner() -> None:
    store = MemoryRedis()
    first = RedisLease(store, source_lock_key("demo"), ttl_seconds=60, token="first")
    second = RedisLease(store, source_lock_key("demo"), ttl_seconds=60, token="second")

    assert first.acquire() is True
    assert second.acquire() is False


def test_only_owner_token_can_release_or_renew_a_lease() -> None:
    store = MemoryRedis()
    owner = RedisLease(store, source_lock_key("demo"), ttl_seconds=60, token="owner")
    other = RedisLease(store, source_lock_key("demo"), ttl_seconds=60, token="other")

    assert owner.acquire() is True
    assert other.renew() is False
    assert other.release() is False
    assert owner.renew() is True
    assert owner.release() is True


def test_expired_source_lease_allows_worker_crash_recovery() -> None:
    store = MemoryRedis()
    crashed = RedisLease(
        store, source_lock_key("demo"), ttl_seconds=60, token="crashed"
    )
    recovered = RedisLease(
        store, source_lock_key("demo"), ttl_seconds=60, token="recovered"
    )

    assert crashed.acquire() is True
    store.expire(source_lock_key("demo"))
    assert recovered.acquire() is True


def test_page_scoped_keys_are_independent_but_source_keys_are_stable() -> None:
    assert source_lock_key("demo") == "crawler:lock:source:demo"
    assert page_lock_key("demo", "1") == "crawler:lock:source:demo:page:1"
    assert page_lock_key("demo", "1") != page_lock_key("demo", "2")


def test_overlapping_source_task_is_skipped_without_running_operation() -> None:
    store = MemoryRedis()
    held = RedisLease(store, source_lock_key("demo"), ttl_seconds=60, token="held")
    calls: list[str] = []

    assert held.acquire() is True
    outcome = run_with_source_lease(
        store,
        "demo",
        lambda: calls.append("ran") or "demo",
        ttl_seconds=60,
    )

    assert outcome == LockOutcome.SKIPPED_OVERLAP
    assert calls == []


def test_source_task_releases_lease_after_operation_finishes() -> None:
    store = MemoryRedis()

    outcome = run_with_source_lease(
        store,
        "demo",
        lambda: "demo",
        ttl_seconds=60,
    )
    next_owner = RedisLease(store, source_lock_key("demo"), ttl_seconds=60)

    assert outcome == "demo"
    assert next_owner.acquire() is True


def test_slow_source_task_renews_its_lease_before_ttl_can_expire() -> None:
    store = MemoryRedis()

    outcome = run_with_source_lease(
        store,
        "demo",
        lambda: sleep(0.04) or "demo",
        ttl_seconds=60,
        renew_interval_seconds=0.01,
    )

    assert outcome == "demo"
    assert store.renewals >= 1
