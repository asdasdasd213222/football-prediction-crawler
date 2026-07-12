# Dedicated Edge Browser Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a locally managed Microsoft Edge browser worker that can run one
browser-queue operation under the existing Redis lease without using a daily
browser session, credentials, or a real website.

**Architecture:** The browser worker runs on the Windows host because the
locally installed Edge executable and its dedicated profile must not be mounted
into the Linux Compose worker. A generic `ManagedEdgeRuntime` owns Playwright
lifecycle, timeouts, resource blocking, and cleanup. Future source adapters
will receive a generic page handle from that runtime and retain all selectors
and parsing; this task adds no site adapter.

**Tech Stack:** Python 3.12, Playwright for Python, locally installed Microsoft
Edge, Celery, Redis, Pytest, Ruff, Mypy, Docker Compose.

## Global Constraints

- Use a dedicated `BROWSER_USER_DATA_DIR` outside the repository; never attach
  to an everyday Edge window over CDP.
- Do not automate login, inspect cookies, or persist credentials, tokens, or
  account data.
- Keep the polling minimum at 60 seconds and preserve the existing per-source
  Redis lease boundary.
- Keep selectors and website-specific parsing out of scheduler, task, and
  runtime modules.
- Use only offline local test pages for P4-01; do not contact a real website.

---

### Task 1: Add Browser Runtime Settings And Dependency Boundaries

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example`
- Modify: `.gitignore`
- Create: `src/multisite_crawler/browser_runtime.py`
- Test: `tests/test_browser_runtime.py`

**Interfaces:**
- Produces `BrowserRuntimeSettings.from_environment(environ, repository_root)`.
- Produces immutable settings: `edge_executable_path`, `user_data_dir`,
  `page_timeout_seconds`, `action_timeout_seconds`, and
  `failure_snapshot_dir`.
- Raises `BrowserRuntimeConfigurationError` for missing, relative,
  in-repository, or non-positive settings.

- [ ] **Step 1: Write the failing settings tests**

```python
def test_settings_require_an_edge_executable_and_external_profile(
    tmp_path: Path,
) -> None:
    with pytest.raises(BrowserRuntimeConfigurationError, match="EDGE_EXECUTABLE"):
        BrowserRuntimeSettings.from_environment({}, repository_root=tmp_path)


def test_settings_reject_a_profile_inside_the_repository(tmp_path: Path) -> None:
    executable = tmp_path.parent / "msedge.exe"
    executable.touch()
    environment = {
        "BROWSER_EDGE_EXECUTABLE_PATH": str(executable),
        "BROWSER_USER_DATA_DIR": str(tmp_path / "edge-profile"),
        "BROWSER_FAILURE_SNAPSHOT_DIR": str(tmp_path.parent / "snapshots"),
    }
    with pytest.raises(BrowserRuntimeConfigurationError, match="outside"):
        BrowserRuntimeSettings.from_environment(environment, repository_root=tmp_path)
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_browser_runtime.py -q`

Expected: FAIL because `multisite_crawler.browser_runtime` does not exist.

- [ ] **Step 3: Add the optional browser dependency and non-secret names**

```toml
[project.optional-dependencies]
browser = [
    "playwright>=1.46,<2",
]
```

```dotenv
BROWSER_EDGE_EXECUTABLE_PATH=
BROWSER_USER_DATA_DIR=
BROWSER_FAILURE_SNAPSHOT_DIR=
BROWSER_PAGE_TIMEOUT_SECONDS=30
BROWSER_ACTION_TIMEOUT_SECONDS=10
```

Add `browser-profiles/` and `browser-failure-snapshots/` to `.gitignore`.
The runtime still rejects those paths when they resolve inside the repository.

- [ ] **Step 4: Implement strict host-only settings**

```python
class BrowserRuntimeConfigurationError(ValueError):
    """Raised when an Edge worker would use an unsafe local path."""


@dataclass(frozen=True)
class BrowserRuntimeSettings:
    edge_executable_path: Path
    user_data_dir: Path
    failure_snapshot_dir: Path
    page_timeout_seconds: float
    action_timeout_seconds: float

    @classmethod
    def from_environment(
        cls, environ: Mapping[str, str], *, repository_root: Path
    ) -> BrowserRuntimeSettings:
        ...
```

Resolve paths with `Path.resolve()`. Require the executable to exist and be a
file. Require profile and failure paths to be absolute and outside the resolved
repository root; create only the snapshot directory, never copy or inspect the
profile. Parse timeout values as finite positive numbers and report the variable
name without echoing its value.

- [ ] **Step 5: Extend and pass the focused tests**

Add tests for a valid external profile, a relative profile, a relative snapshot
directory, and non-positive timeout values. Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_browser_runtime.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the isolated settings change**

```powershell
git add pyproject.toml .env.example .gitignore src/multisite_crawler/browser_runtime.py tests/test_browser_runtime.py
git commit -m "feat: add dedicated Edge runtime settings"
```

### Task 2: Implement Managed Edge Lifecycle And Redacted Artifacts

**Files:**
- Modify: `src/multisite_crawler/browser_runtime.py`
- Create: `src/multisite_crawler/browser_artifacts.py`
- Test: `tests/test_browser_runtime.py`
- Test: `tests/test_browser_artifacts.py`

**Interfaces:**
- Produces `ManagedEdgeRuntime(settings, playwright_factory)`.
- Exposes `run(operation: Callable[[BrowserPage], T]) -> T`.
- Produces `BrowserArtifactWriter.write_failure(source_id, safe_html, screenshot)`.
- `BrowserPage` is a narrow protocol; site selectors never enter this module.

- [ ] **Step 1: Write failing lifecycle tests with a fake gateway**

```python
def test_runtime_closes_page_and_context_after_success(
    settings: BrowserRuntimeSettings,
) -> None:
    fake = FakePlaywrightFactory()
    runtime = ManagedEdgeRuntime(settings, playwright_factory=fake)

    assert runtime.run(lambda page: page.title()) == "fixture"
    assert fake.page.closed is True
    assert fake.context.closed is True


def test_runtime_blocks_media_and_sets_bounded_timeouts(
    settings: BrowserRuntimeSettings,
) -> None:
    fake = FakePlaywrightFactory()
    ManagedEdgeRuntime(settings, playwright_factory=fake).run(lambda page: None)

    assert fake.context.blocked_resource_types == {"font", "image", "media"}
    assert fake.page.default_timeout_ms == 10_000
    assert fake.page.default_navigation_timeout_ms == 30_000
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_browser_runtime.py -q`

Expected: FAIL because `ManagedEdgeRuntime` is not defined.

- [ ] **Step 3: Implement the narrow persistent-context runtime**

```python
class ManagedEdgeRuntime:
    def run[T](self, operation: Callable[[BrowserPage], T]) -> T:
        with self._playwright_factory() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(self._settings.user_data_dir),
                executable_path=str(self._settings.edge_executable_path),
                headless=False,
            )
            page = context.pages[0] if context.pages else context.new_page()
            try:
                context.route("**/*", self._block_unneeded_resources)
                page.set_default_timeout(
                    int(self._settings.action_timeout_seconds * 1000)
                )
                page.set_default_navigation_timeout(
                    int(self._settings.page_timeout_seconds * 1000)
                )
                return operation(page)
            finally:
                page.close()
                context.close()
```

Use a fake gateway in unit tests; the suite must never launch Edge. Re-raise
operation exceptions after cleanup. Block only image, font, and media resource
types; do not intercept or alter requests.

- [ ] **Step 4: Write failing redaction tests**

```python
def test_artifact_writer_rejects_full_page_html(tmp_path: Path) -> None:
    writer = BrowserArtifactWriter(tmp_path)
    with pytest.raises(ValueError, match="safe fragment"):
        writer.write_failure(source_id="demo", safe_html=None, screenshot=None)


def test_artifact_writer_removes_secret_like_attributes(tmp_path: Path) -> None:
    artifact = BrowserArtifactWriter(tmp_path).write_failure(
        source_id="demo",
        safe_html='<table><input value="secret"><tr><td>ok</td></tr></table>',
        screenshot=None,
    )
    assert "secret" not in artifact.html_path.read_text(encoding="utf-8")
```

- [ ] **Step 5: Implement artifact writing and verify it**

Accept only adapter-provided table fragments. Remove form controls, scripts,
styles, event attributes, and attributes named `cookie`, `token`,
`authorization`, or `password`. Name artifacts with a validated
`[a-z0-9_]+` source ID and generated UUID. Do not save a screenshot unless a
future adapter supplies a clipped safe region.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_browser_runtime.py tests/test_browser_artifacts.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit lifecycle and artifact behavior**

```powershell
git add src/multisite_crawler/browser_runtime.py src/multisite_crawler/browser_artifacts.py tests/test_browser_runtime.py tests/test_browser_artifacts.py
git commit -m "feat: add managed Edge lifecycle"
```

### Task 3: Wire The Host Browser Worker Without A Site Adapter

**Files:**
- Modify: `src/multisite_crawler/tasks.py`
- Modify: `src/multisite_crawler/queueing.py`
- Modify: `compose.yaml`
- Create: `src/multisite_crawler/browser_worker.py`
- Create: `scripts/run_browser_worker.ps1`
- Create: `scripts/verify_edge_runtime.ps1`
- Test: `tests/test_browser_tasks.py`
- Test: `tests/test_queueing.py`

**Interfaces:**
- Produces `run_browser_operation(source_id, operation, runtime, store)`.
- Produces Celery task `run_browser_runtime_probe_task()` routed to `browser`.
- Produces a PowerShell launcher that validates settings before starting Celery.

- [ ] **Step 1: Write failing task and route tests**

```python
def test_browser_operation_uses_the_existing_source_lease() -> None:
    store = MemoryRedis()
    runtime = FakeRuntime()

    assert run_browser_operation("demo", lambda page: "ok", runtime, store) == "ok"
    assert runtime.calls == 1


def test_browser_runtime_probe_is_routed_to_the_browser_queue() -> None:
    app = create_celery_app("redis://localhost:6379/0")
    assert app.conf.task_routes[
        "multisite_crawler.tasks.run_browser_runtime_probe_task"
    ] == {"queue": "browser"}
```

- [ ] **Step 2: Run focused task tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_browser_tasks.py tests/test_queueing.py -q`

Expected: FAIL because the browser operation and probe task do not exist.

- [ ] **Step 3: Add generic task wiring**

```python
def run_browser_operation[T](
    source_id: str,
    operation: Callable[[BrowserPage], T],
    runtime: BrowserRuntime,
    store: RedisLeaseStore,
) -> T | LockOutcome:
    return run_with_source_lease(
        store, source_id, lambda: runtime.run(operation)
    )
```

The probe must use only an explicit local `http://127.0.0.1` fixture URL and
return its title. It is opt-in through a dedicated environment variable.
`run_browser_task` remains source-neutral until P3-04 provides an adapter
registry.

- [ ] **Step 4: Move Edge execution out of Compose**

Remove `worker-browser` from `compose.yaml`; its Linux image cannot safely
run the Windows Edge executable or host profile. Keep Redis, the HTTP worker,
the scheduler, and the browser queue declaration. Implement the host launcher:

```powershell
if (-not $env:REDIS_URL) { throw 'REDIS_URL is required.' }
& .\.venv\Scripts\python.exe -m multisite_crawler.browser_worker
```

`browser_worker.py` must validate `BrowserRuntimeSettings` and then invoke
Celery's worker entry point for the `browser` queue. The verification script
starts a local fixture server and runs only when the operator supplies `-Run`;
it must stop the fixture it starts.

- [ ] **Step 5: Verify focused tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_browser_tasks.py tests/test_queueing.py -q
docker compose config
```

Expected: tests PASS and Compose validates without a Linux Edge worker.

- [ ] **Step 6: Commit host-worker wiring**

```powershell
git add src/multisite_crawler/tasks.py src/multisite_crawler/queueing.py compose.yaml src/multisite_crawler/browser_worker.py scripts/run_browser_worker.ps1 scripts/verify_edge_runtime.ps1 tests/test_browser_tasks.py tests/test_queueing.py
git commit -m "feat: add host Edge browser worker"
```

### Task 4: Document Operation And Run P4-01 Acceptance

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-07-11-browser-first-edge-data-pipeline-design.md`
- Modify: `TODO.md`

**Interfaces:**
- Documents manual external-profile setup and the host-worker launch command.
- Documents that P4-01 is offline-only and P4-02 is required before any
  authenticated source run.

- [ ] **Step 1: Add operational documentation**

Document this non-secret local pattern:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,browser]"
$env:BROWSER_EDGE_EXECUTABLE_PATH = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$env:BROWSER_USER_DATA_DIR = 'D:\crawler-edge-profile'
$env:BROWSER_FAILURE_SNAPSHOT_DIR = 'D:\crawler-edge-snapshots'
.\scripts\run_browser_worker.ps1
```

State that P4-02, not P4-01, authorizes manual login. State that P4-01 tests
never visit a real-site URL.

- [ ] **Step 2: Run the complete quality gate**

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest -q
docker compose config
```

Expected: every command exits with code 0.

- [ ] **Step 3: Run the approved local Edge lifecycle check**

With an external empty profile and no real-site URL:

```powershell
.\scripts\verify_edge_runtime.ps1 -Run
```

Expected: a local fixture title is returned; page and context cleanup are
reported; no profile contents or page body are printed.

- [ ] **Step 4: Update acceptance status only after evidence is complete**

Check only P4-01 items whose tests and local lifecycle check passed. Do not
check P4-02 or any P3-04 item. Record commands, outcomes, and the remaining
robots/authorization review in the task report.

- [ ] **Step 5: Commit documentation and acceptance evidence**

```powershell
git add README.md docs/superpowers/specs/2026-07-11-browser-first-edge-data-pipeline-design.md TODO.md
git commit -m "docs: document dedicated Edge worker operation"
```

## Plan Self-Review

- Scope coverage: Task 1 validates non-secret host configuration; Task 2 owns
  lifecycle and safe artifacts; Task 3 reuses the existing browser queue and
  Redis lease without adding source logic; Task 4 provides documentation and
  all P4-01 acceptance commands.
- No source selectors, real-site URLs, account data, Cookie reads, automated
  login, or P3-04 adapter behavior appears in the plan.
- Every implementation task begins with a focused failing test and ends with a
  passing command. All interface names are introduced before use.
