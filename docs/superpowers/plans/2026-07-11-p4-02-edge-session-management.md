# Dedicated Edge Session Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Add non-sensitive, Redis-backed lifecycle state for manually
authenticated dedicated Edge profiles without handling credentials or visiting a
real source.

**Architecture:** A generic session manager persists an opaque profile
reference, Beijing-local manual-refresh time, and a fixed session-state
vocabulary in Redis. Future source adapters provide only a typed visible-state
observation; the shared manager stops terminal states for human review. A
PowerShell helper opens only `about:blank` in the dedicated profile and records
a refresh through a local CLI after the operator closes Edge.

**Tech Stack:** Python 3.12, Redis protocol boundary, Microsoft Edge,
PowerShell, Pytest, Ruff, Mypy, Docker Compose.

## Global Constraints

- Do not automate login or accept usernames, passwords, cookies, tokens,
  account data, browser storage state, or real source URLs.
- Store timestamps as Beijing local time (`Asia/Shanghai`).
- A profile reference is an opaque non-secret identifier, never an absolute
  path or account identifier.
- Session failure states stop work for human review; no retry performs login.
- Use only in-memory stores, local helpers, and `about:blank` for P4-02 tests.
- Keep all site selectors, page text, and source mappings out of this task.

---

### Task 1: Add Typed Session State And Redis-Sized Persistence

**Files:**
- Create: `src/multisite_crawler/browser_session.py`
- Create: `tests/test_browser_session.py`

**Interfaces:**
- Produces `BrowserSessionStatus`, `BrowserSessionObservation`,
  `BrowserSessionState`, `BrowserSessionManager`, and
  `BrowserSessionRequiredError`.
- Consumes `SessionStateStore.get(key) -> str | None` and
  `SessionStateStore.set(key, value) -> object`.
- Produces key `browser-session:<profile_reference>` containing only JSON with
  `profile_reference`, `status`, `last_manual_refresh_at`, and `reason`.

- [ ] **Step 1: Write failing state-transition tests**

```python
def test_manual_refresh_records_beijing_time_and_ready_state() -> None:
    store = MemoryStore()
    manager = BrowserSessionManager(store)
    current = datetime(2026, 7, 11, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    state = manager.record_manual_refresh("sporttery_primary", current)

    assert state.status is BrowserSessionStatus.READY
    assert state.last_manual_refresh_at == current
    assert "cookie" not in store.values["browser-session:sporttery_primary"]


def test_terminal_observation_requires_human_review() -> None:
    manager = BrowserSessionManager(MemoryStore())

    with pytest.raises(BrowserSessionRequiredError, match="captcha"):
        manager.record_observation(
            "sporttery_primary", BrowserSessionObservation.CAPTCHA, BEIJING_NOW
        )
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_browser_session.py -q`

Expected: FAIL because `browser_session` does not exist.

- [ ] **Step 3: Implement fixed-vocabulary session state**

```python
class BrowserSessionStatus(StrEnum):
    UNKNOWN = "unknown"
    READY = "ready"
    LOGIN_REQUIRED = "login_required"
    ACCESS_DENIED = "access_denied"
    CAPTCHA = "captcha"


class BrowserSessionObservation(StrEnum):
    READY = "ready"
    LOGIN_REQUIRED = "login_required"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    CAPTCHA = "captcha"
    ACCESS_CONTROL = "access_control"
```

`record_manual_refresh` validates `[a-z0-9_]+`, requires a timezone-aware
Beijing timestamp, sets `ready`, and overwrites only refresh time/state.
`record_observation` maps `unauthorized`, `forbidden`, and
`access_control` to `access_denied`; it stores a fixed reason then raises
`BrowserSessionRequiredError` for every terminal outcome. It must not accept
arbitrary text as a reason.

- [ ] **Step 4: Add edge-case and sensitive-data tests**

Test invalid profile references, naive/non-Beijing datetimes, invalid JSON
state, idempotent repeated manual refresh, all terminal observations, and a
serialized-state scan for `cookie`, `token`, `authorization`, `password`,
and `account`.

- [ ] **Step 5: Verify the focused suite**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_browser_session.py -q
```

Expected: PASS.

### Task 2: Add Manual Profile Refresh CLI And Edge Helper

**Files:**
- Create: `src/multisite_crawler/browser_session_cli.py`
- Create: `scripts/open_edge_profile.ps1`
- Modify: `.env.example`
- Modify: `README.md`
- Test: `tests/test_browser_session_cli.py`

**Interfaces:**
- CLI command: `python -m multisite_crawler.browser_session_cli record-refresh`.
- Required non-secret environment values: `REDIS_URL` and
  `BROWSER_PROFILE_REFERENCE`.
- Helper supports only `-Open` and `-RecordRefresh`; it takes no credential,
  URL, cookie, or account parameters.

- [ ] **Step 1: Write failing CLI tests**

```python
def test_cli_requires_a_non_secret_profile_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BROWSER_PROFILE_REFERENCE", raising=False)

    with pytest.raises(BrowserSessionConfigurationError, match="PROFILE_REFERENCE"):
        record_refresh_from_environment(MemoryStore(), {})
```

- [ ] **Step 2: Implement the CLI boundary**

The CLI creates a Redis client only after environment validation, calls
`BrowserSessionManager.record_manual_refresh`, and prints only profile
reference, state value, and Beijing refresh timestamp. No Redis values, cookies,
paths, or exception chains are printed.

The PowerShell helper validates P4-01 Edge/profile settings. `-Open` uses the
configured executable with the dedicated `--user-data-dir` and fixed
`about:blank`; it does not navigate to a source. `-RecordRefresh` invokes
the CLI only after the operator has manually closed Edge.

- [ ] **Step 3: Add documentation and template names**

Add only `BROWSER_PROFILE_REFERENCE=sporttery_primary` to `.env.example`.
Document:

```powershell
.\scripts\open_edge_profile.ps1 -Open
# Operator performs any permitted login manually, then closes Edge.
.\scripts\open_edge_profile.ps1 -RecordRefresh
```

State that P4-02 does not grant source authorization or permit a real URL in
the helper.

- [ ] **Step 4: Verify focused tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_browser_session.py tests/test_browser_session_cli.py -q
```

Expected: PASS.

### Task 3: Integrate Safe Session Outcomes And Local Acceptance

**Files:**
- Modify: `src/multisite_crawler/tasks.py`
- Modify: `tests/test_browser_tasks.py`
- Modify: `README.md`
- Modify: `TODO.md`

**Interfaces:**
- A generic browser task caller may pass only `BrowserSessionObservation` to
  `BrowserSessionManager`; terminal states raise
  `BrowserSessionRequiredError` before retry logic is considered.
- No source adapter, URL, selector, or login action is added.

- [ ] **Step 1: Write failing integration tests**

```python
def test_captcha_state_stops_browser_operation_without_retry() -> None:
    manager = BrowserSessionManager(MemoryStore())

    with pytest.raises(BrowserSessionRequiredError, match="captcha"):
        manager.record_observation(
            "sporttery_primary", BrowserSessionObservation.CAPTCHA, BEIJING_NOW
        )
```

- [ ] **Step 2: Implement only the generic stop boundary**

Add a small task-level helper that records a typed observation through the
manager. It must not parse pages or enqueue a retry. Confirm exceptions contain
only fixed vocabulary and profile references.

- [ ] **Step 3: Run local acceptance**

Start only Redis, set a dummy external profile path and
`BROWSER_PROFILE_REFERENCE=sporttery_primary`, run the refresh CLI against the
local Redis store, then validate stored JSON has no sensitive markers. Do not
open Edge or navigate to any website for this check.

- [ ] **Step 4: Run the full gate and update TODO only after evidence**

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest -q
docker compose config
```

Check P4-02 only after all requirements and the local Redis acceptance pass.
Do not check P3-04 or navigate to the source website.

## Plan Self-Review

- Task 1 owns serializable state, Beijing time, terminal outcomes, and sensitive
  data rejection.
- Task 2 owns the manual-only operational boundary and documentation.
- Task 3 owns generic task integration, local Redis acceptance, full gates, and
  TODO evidence without source-specific collection behavior.
