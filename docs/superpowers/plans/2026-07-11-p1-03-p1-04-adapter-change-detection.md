# P1-03 And P1-04 Adapter And Change Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a strict site-neutral adapter contract and PostgreSQL-backed idempotent change detection with three-run inactive detection.

**Architecture:** Adapters produce validated `FetchResult` and `CrawlItem` values without database access. A generic repository hashes canonical business data, persists source validators, and owns transactional record/event updates. PostgreSQL remains the concurrency and uniqueness boundary.

**Tech Stack:** Python 3.12, Pydantic 2, SQLAlchemy 2, Alembic, Psycopg 3, PostgreSQL 16, Pytest, Ruff, Mypy.

## Global Constraints

- Implement P1-03 and P1-04 only; do not add schedulers, queues, browser automation, real websites, credentials, or deployment.
- Store timestamps as Beijing civil time (`Asia/Shanghai`) in `TIMESTAMP WITHOUT TIME ZONE`.
- Keep source-specific selectors and field mapping inside adapters; scheduler and persistence code remain site-neutral.
- Use PostgreSQL JSONB, SQLAlchemy, and Alembic for persistence changes.
- A record becomes inactive only after three consecutive successful complete collections omit it.
- Never commit, log, or document database URLs or credentials; use only a disposable shell-local `TEST_DATABASE_URL` for integration tests.
- Run Ruff, Mypy, Pytest, Compose config, and Alembic upgrade/downgrade/upgrade before completion.
- Do not create commits because the shared repository contains existing untracked work.

---

### Task 1: Strict Adapter Contract And Fake Adapter Runner

**Files:**
- Create: `src/multisite_crawler/adapters/__init__.py`
- Create: `src/multisite_crawler/adapters/base.py`
- Create: `tests/test_adapters.py`

**Interfaces:**
- Produces `FetchResult(body: bytes, etag: str | None, last_modified: str | None)`, `CrawlItem(external_id: str, data: dict[str, JsonValue])`, `BaseAdapter`, `AdapterRunner`, and the five declared adapter errors.
- `BaseAdapter.fetch() -> FetchResult`, `parse(FetchResult) -> Sequence[Mapping[str, JsonValue]]`, `normalize(Mapping[str, JsonValue]) -> CrawlItem`, and `fingerprint(CrawlItem) -> str` are called in that order.

- [ ] **Step 1: Write failing tests for a valid fake adapter and strict invalid output rejection**

```python
def test_runner_returns_validated_fake_adapter_items() -> None:
    result = AdapterRunner(FakeAdapter()).run()
    assert [item.external_id for item in result.items] == ["match-1"]
    assert result.raw_response_hash


def test_runner_rejects_blank_external_id_before_storage() -> None:
    with pytest.raises(AdapterContractError, match="external_id"):
        AdapterRunner(InvalidAdapter()).run()
```

- [ ] **Step 2: Run the adapter tests and verify collection fails because the package is absent**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests\\test_adapters.py -q`

Expected: FAIL with `ModuleNotFoundError` for `multisite_crawler.adapters`.

- [ ] **Step 3: Implement the minimum contract and runner**

```python
class BaseAdapter(ABC):
    @abstractmethod
    def fetch(self) -> FetchResult: ...

    @abstractmethod
    def parse(self, response: FetchResult) -> Sequence[Mapping[str, JsonValue]]: ...

    @abstractmethod
    def normalize(self, raw_item: Mapping[str, JsonValue]) -> CrawlItem: ...

    @abstractmethod
    def fingerprint(self, item: CrawlItem) -> str: ...
```

`AdapterRunner.run()` catches unexpected source exceptions and raises the
operation-specific adapter error with the original cause. It accepts an empty
sequence, validates each normalized item with strict Pydantic models, computes
the raw SHA-256, and rejects any adapter fingerprint different from the shared
canonical business fingerprint.

- [ ] **Step 4: Add tests for empty data, malformed parsed values, normalization failures, and fingerprint mismatch**

```python
def test_runner_allows_a_successful_empty_collection() -> None:
    assert AdapterRunner(EmptyAdapter()).run().items == ()


def test_runner_rejects_a_noncanonical_adapter_fingerprint() -> None:
    with pytest.raises(AdapterContractError, match="fingerprint"):
        AdapterRunner(MismatchedFingerprintAdapter()).run()
```

- [ ] **Step 5: Run adapter tests and confirm success**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests\\test_adapters.py -q`

Expected: PASS; the fake adapter completes without any database or network access.

### Task 2: Canonical Hashing And P1-04 Schema Revision

**Files:**
- Create: `src/multisite_crawler/hashing.py`
- Modify: `src/multisite_crawler/models.py`
- Create: `migrations/versions/20260711_02_add_change_detection_state.py`
- Modify: `tests/test_database.py`
- Modify: `tests/test_adapters.py`

**Interfaces:**
- Produces `canonical_json_bytes(value: JsonValue) -> bytes` and `fingerprint_business_data(data: Mapping[str, JsonValue]) -> str`.
- Adds model/table metadata for `SourceFetchState`, `Record.last_seen_at`, and `Record.missing_count`.

- [ ] **Step 1: Write failing canonical-hash tests and migration-metadata tests**

```python
def test_canonical_business_hash_ignores_mapping_key_order() -> None:
    assert fingerprint_business_data({"a": 1, "b": 2}) == fingerprint_business_data(
        {"b": 2, "a": 1}
    )


def test_canonical_business_hash_rejects_unsupported_values() -> None:
    with pytest.raises(ValueError, match="JSON-compatible"):
        fingerprint_business_data({"value": object()})
```

- [ ] **Step 2: Run the focused tests and verify the missing hashing/state implementation fails**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests\\test_adapters.py tests\\test_database.py -q`

Expected: FAIL because `hashing` and `SourceFetchState` do not exist.

- [ ] **Step 3: Implement canonical JSON and the second reversible migration**

Canonical JSON uses UTF-8, sorted mapping keys, compact separators, and
`allow_nan=False`. The migration creates `source_fetch_states(source_id,
etag, last_modified, raw_response_hash, updated_at)` with a source unique key;
it adds nullable `last_seen_at` and non-null `missing_count` defaulting to zero
to `records`. Its downgrade drops the state table and added record columns.

- [ ] **Step 4: Add and run the migration cycle test against disposable PostgreSQL**

```python
@pytest.mark.integration
def test_change_detection_migration_is_reversible() -> None:
    command.upgrade(config, "head")
    assert "source_fetch_states" in inspect(engine).get_table_names()
    command.downgrade(config, "-1")
    assert "source_fetch_states" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")
```

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests\\test_database.py -q` with the shell-local test URL.

Expected: PASS.

### Task 3: Transactional Repository And Missing-Record Reconciliation

**Files:**
- Create: `src/multisite_crawler/record_repository.py`
- Modify: `tests/test_database.py`

**Interfaces:**
- Consumes `Session`, `Source`, validated adapter result, and `fingerprint_business_data`.
- Produces `RecordRepository.persist_collection(source_id: UUID, result: AdapterResult) -> None` and `RecordRepository.reconcile_missing(source_id: UUID, observed_external_ids: set[str]) -> None`.

- [ ] **Step 1: Write failing PostgreSQL integration tests for new, unchanged, and changed records**

```python
def test_persist_collection_creates_once_and_updates_only_on_business_change() -> None:
    repository.persist_collection(source.id, result_for({"score": 1}))
    repository.persist_collection(source.id, result_for({"score": 1}))
    repository.persist_collection(source.id, result_for({"score": 2}))

    assert event_types_for(source.id) == ["created", "updated"]
```

- [ ] **Step 2: Run it and verify the repository module is absent**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests\\test_database.py::test_persist_collection_creates_once_and_updates_only_on_business_change -q`

Expected: FAIL with `ModuleNotFoundError` for `record_repository`.

- [ ] **Step 3: Implement the transaction boundaries**

For each item, select an existing row with `FOR UPDATE`; insert new records in
a nested transaction; on a unique-constraint race, roll back the savepoint and
reread the winning row with `FOR UPDATE`. Set `last_seen_at`, reset
`missing_count`, restore `is_active`, and write `created` or `updated` events
only when required by the old and new business fingerprints. Update the source
fetch state in the same transaction.

- [ ] **Step 4: Add and run tests for raw response metadata, noise isolation, and concurrent delivery**

```python
def test_noise_and_key_order_do_not_create_a_change_event() -> None:
    repository.persist_collection(source.id, result_for({"home": 1, "away": 0}))
    repository.persist_collection(source.id, result_for({"away": 0, "home": 1}))
    assert event_types_for(source.id) == ["created"]
```

Use two independent sessions and a barrier to submit the same source/external
identifier concurrently. Assert one record and one `created` event exist.

- [ ] **Step 5: Add and run the three-successful-run inactive and recovery tests**

```python
def test_three_successful_absences_mark_a_record_inactive_once() -> None:
    repository.persist_collection(source.id, result_for({"score": 1}))
    for _ in range(3):
        repository.persist_collection(source.id, empty_result())
    assert record.is_active is False
    assert event_types_for(source.id) == ["created", "inactive"]
```

Also verify a failed adapter run never calls reconciliation, and a later item
appearance resets `missing_count` and restores activity without a duplicate
event when its fingerprint is unchanged.

### Task 4: Documentation, Full Verification, And Work-Item Completion

**Files:**
- Modify: `README.md`
- Modify: the project work checklist only after every acceptance command passes
- Modify: `tests/test_database.py`
- Modify: `tests/test_adapters.py`

**Interfaces:**
- Documents the adapter boundary, validator fields, canonical business hash,
three-run missing threshold, disposable test database requirement, and Beijing time.

- [ ] **Step 1: Update README with local contract semantics**

Document that adapters are source-specific but storage is generic, ETag and
Last-Modified are persisted validators, and the inactive threshold is three
successful complete collections. Do not add credentials, real endpoints, or
deployment commands.

- [ ] **Step 2: Run the final required quality and migration checks**

```powershell
.\\.venv\\Scripts\\ruff.exe check .
.\\.venv\\Scripts\\ruff.exe format --check .
.\\.venv\\Scripts\\mypy.exe src
$env:TEST_DATABASE_URL = $env:TEST_DATABASE_URL
.\\.venv\\Scripts\\python.exe -m pytest -q
$env:DOCKER_CONFIG = Join-Path $env:TEMP "codex-docker-client"
docker compose config
$env:DATABASE_URL = $env:TEST_DATABASE_URL
.\\.venv\\Scripts\\alembic.exe upgrade head
.\\.venv\\Scripts\\alembic.exe downgrade -1
.\\.venv\\Scripts\\alembic.exe upgrade head
```

Expected: every command exits zero; fake-adapter tests, canonical hash tests,
idempotency, event, inactivity, recovery, concurrent Upsert, and migrations
all pass against the disposable local database.

- [ ] **Step 3: Mark only P1-03 and P1-04 complete after verification**

Replace the P1-03 and P1-04 delivery and acceptance checkboxes, plus their two
execution-list entries, with `[x]` only after Step 2 succeeds. Report that no
production deployment, commit, push, or real-site access occurred.

## Self-Review

1. **Spec coverage:** Task 1 covers the adapter contract, validation, errors,
fake adapter, empty results, and boundaries. Task 2 covers validators, raw and
business hashes, state schema, and migration reversibility. Task 3 covers
idempotency, events, concurrency, three-run inactivity, and recovery. Task 4
covers documentation, all required verification, and completion timing.
2. **Placeholder scan:** No unfinished implementation placeholders are used;
the plan names every module, interface, test behavior, and command.
3. **Type consistency:** `FetchResult`, `CrawlItem`, `AdapterResult`,
`fingerprint_business_data`, and `RecordRepository` retain the same names
throughout the tasks.
