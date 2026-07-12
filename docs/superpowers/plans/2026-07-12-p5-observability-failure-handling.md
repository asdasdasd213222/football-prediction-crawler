# P5 Observability And Failure Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete P5-01 through P5-04 with safe JSON logs, Redis-backed
Prometheus metrics, deduplicated alerts, and redacted private failure snapshots.

**Architecture:** Site-neutral runtime code publishes typed observation events.
The observation service emits redacted JSON and updates bounded Redis metric
state. A loopback-only exporter renders that state, while the alert evaluator
uses the same state to publish one active and one resolved event per condition.
Failure snapshots accept only typed, redactable inputs and their optional path
is associated with `CrawlRun` through an Alembic migration.

**Tech Stack:** Python 3.12, standard-library logging/HTTP, Redis, SQLAlchemy,
Alembic, Celery, Pytest, Ruff, Mypy, Docker Compose, PostgreSQL for migration
verification.

## Global Constraints

- Use Beijing civil time (`Asia/Shanghai`) for every timestamp.
- Do not log, persist, fixture, or export credentials, cookies, tokens,
  authorization headers, account data, personal data, URL query values, or
  arbitrary exception messages.
- Keep `source_id` and a fixed low-cardinality outcome/status vocabulary as
  metric labels. Never use a URL, `crawl_run_id`, business ID, or page content
  as a metric label.
- All snapshot roots must be validated external directories; do not serve them
  from the metrics HTTP process.
- Browser screenshots must be adapter-supplied redacted PNGs. Never capture or
  persist an unreviewed whole page.
- Do not access a real source or browser profile, deploy production services,
  or change P3-04 authorization state.

---

### Task 1: Safe Structured Logging (P5-01)

**Files:**
- Create: `src/multisite_crawler/observability.py`
- Create: `tests/test_observability.py`
- Modify: `src/multisite_crawler/tasks.py`
- Modify: `src/multisite_crawler/scheduler_service.py`
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Produces `RunContext(source_id: str, crawl_run_id: UUID, task_id: str)`.
- Produces `RunEvent(name, context, outcome, duration_seconds, item_count,
  exception_type)` and `configure_json_logging(settings)`.
- Consumes only JSON-compatible event fields and serializes through
  `redact_value(value)`.

- [ ] **Step 1: Write failing redaction and format tests**

```python
def test_json_log_event_contains_trace_fields_and_redacts_sensitive_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    context = RunContext("demo_api", UUID("00000000-0000-0000-0000-000000000001"), "task-1")
    logger = make_json_logger("test")

    logger.info(
        "run_finished",
        extra={"event": RunEvent.finished(context, duration_seconds=1.5, item_count=2,
                                            extra={"Authorization": "secret", "url": "https://a/?token=x"})},
    )

    payload = json.loads(caplog.records[-1].message)
    assert payload["source_id"] == "demo_api"
    assert payload["crawl_run_id"] == "00000000-0000-0000-0000-000000000001"
    assert payload["task_id"] == "task-1"
    assert "secret" not in caplog.text
    assert "token=x" not in caplog.text


def test_rotating_file_settings_reject_repository_local_log_directory(tmp_path: Path) -> None:
    with pytest.raises(ObservabilityConfigurationError, match="outside the repository"):
        LoggingSettings.from_environment({"LOG_FILE_DIR": str(tmp_path)}, repository_root=tmp_path)
```

- [ ] **Step 2: Run the focused test and observe the missing module failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_observability.py -q`

Expected: collection fails because `multisite_crawler.observability` is absent.

- [ ] **Step 3: Implement the fixed event schema and redactor**

```python
@dataclass(frozen=True)
class RunContext:
    source_id: str
    crawl_run_id: UUID
    task_id: str


class RunOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


def redact_value(value: JSONValue) -> JSONValue:
    """Return JSON-safe content with denied key values and URL queries removed."""


def emit_run_event(logger: logging.Logger, event: RunEvent) -> None:
    logger.info(event.name, extra={"run_event": event})
```

Use a JSON formatter that emits only fixed event attributes. Configure either a
console handler or `RotatingFileHandler(maxBytes, backupCount)` after external
directory validation. Retain exception class name but omit exception text.

- [ ] **Step 4: Instrument site-neutral task and scheduler boundaries**

Wrap `run_with_source_lease` and scheduler `run_cycle` with start/finish/fail
events. Use a generated UUID and Celery request ID only when it is a safe
string. Preserve the existing return values and retry behavior.

- [ ] **Step 5: Run focused tests and quality checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_observability.py tests/test_browser_tasks.py tests/test_scheduler.py -q
.\.venv\Scripts\python.exe -m ruff check src/multisite_crawler/observability.py tests/test_observability.py
.\.venv\Scripts\python.exe -m mypy src
```

Expected: all selected tests pass; logs include correlation fields and contain
no sensitive marker values.

### Task 2: Redis Metrics Store And Loopback Prometheus Exporter (P5-02)

**Files:**
- Create: `src/multisite_crawler/metrics.py`
- Create: `src/multisite_crawler/metrics_service.py`
- Create: `tests/test_metrics.py`
- Modify: `src/multisite_crawler/queueing.py`
- Modify: `src/multisite_crawler/observability.py`
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Produces `MetricsStore.record_run`, `record_http_status`, `record_items`,
  `record_lock_skip`, `record_circuit_breaker`, and `record_worker_heartbeat`.
- Produces `render_prometheus(snapshot) -> str` and `serve_metrics(host, port,
  reader)`.
- Consumes a narrow Redis protocol with `hincrby`, `hset`, `hgetall`, `llen`,
  and `get`.

- [ ] **Step 1: Write failing metric output tests**

```python
def test_prometheus_output_has_required_metrics_and_bounded_labels() -> None:
    store = MemoryMetricsStore()
    store.record_run(source_id="demo_api", run_id=RUN_ID, outcome=RunOutcome.SUCCEEDED,
                     duration_seconds=1.25, item_count=3)
    store.record_http_status("demo_api", 200)

    rendered = render_prometheus(store.snapshot(queue_depths=QueueDepths(http=2, browser=1)))

    assert 'crawler_run_total{source_id="demo_api",outcome="succeeded"} 1' in rendered
    assert "crawler_last_success_timestamp" in rendered
    assert str(RUN_ID) not in rendered
    assert "https://" not in rendered


def test_metrics_http_handler_serves_only_metrics_path() -> None:
    with metrics_test_server(MemoryMetricsStore()) as url:
        assert urlopen(f"{url}/metrics").status == 200
        assert urlopen(f"{url}/other").status == 404
```

- [ ] **Step 2: Verify the test fails before the implementation exists**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_metrics.py -q`

Expected: collection fails because the metrics modules are absent.

- [ ] **Step 3: Implement fixed Redis keys and Prometheus text rendering**

Use a stable prefix such as `crawler:metrics:`. Store only numeric counters,
fixed state strings, source IDs, and the latest safe run ID in Redis. Render
the metric names listed in P5-02 with `# HELP` and `# TYPE` lines. Validate
`source_id`, queue name, outcome, and allowed HTTP status before accepting an
update.

- [ ] **Step 4: Integrate existing queue and runtime events**

Extend `queue_depths` with metrics publication at the service boundary. Have
the structured run-event integration call the metric store once per terminal
run. Record lock skips from `run_with_source_lease`; do not turn a skip into a
failure.

- [ ] **Step 5: Verify local loopback scrape and focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_metrics.py tests/test_queueing.py tests/test_browser_tasks.py -q
```

Expected: all tests pass and the HTTP test scrapes only a local fixture server.

### Task 3: Alert Evaluation, Recovery, And Rule Configuration (P5-03)

**Files:**
- Create: `src/multisite_crawler/alerts.py`
- Create: `src/multisite_crawler/alert_service.py`
- Create: `configs/prometheus/alerts.yml`
- Create: `tests/test_alerts.py`
- Modify: `configs/sources.example.yaml`
- Modify: `README.md`

**Interfaces:**
- Produces `AlertRule`, `AlertEvent`, `AlertEvaluator.evaluate(snapshot, now)`,
  and `AlertStateStore`.
- Produces exactly one `ACTIVE` event on condition entry and one `RESOLVED`
  event on condition exit for an alert/source pair.
- Consumes validated threshold config and safe metric/health snapshots.

- [ ] **Step 1: Write parameterized failing tests for every P5-03 condition**

```python
@pytest.mark.parametrize("scenario,expected_rule", [
    (MetricScenario(consecutive_failures=3), "crawler_consecutive_failures"),
    (MetricScenario(last_success_age_seconds=720), "crawler_no_recent_success"),
    (MetricScenario(items_found=0), "crawler_items_zero"),
    (MetricScenario(item_deviation_ratio=0.9), "crawler_items_abnormal"),
    (MetricScenario(parse_error_rate=0.5), "crawler_parse_error_rate"),
    (MetricScenario(http_status=403), "crawler_access_denied"),
    (MetricScenario(queue_depth=200), "crawler_queue_backlog"),
    (MetricScenario(worker_last_heartbeat_age_seconds=120), "crawler_worker_offline"),
    (MetricScenario(redis_available=False), "crawler_redis_down"),
    (MetricScenario(disk_free_ratio=0.01), "crawler_disk_low"),
])
def test_alert_rule_emits_one_safe_active_event(scenario: MetricScenario, expected_rule: str) -> None:
    event = AlertEvaluator(DEFAULT_THRESHOLDS, MemoryAlertState()).evaluate(scenario, NOW)[0]
    assert event.rule == expected_rule
    assert event.source_id == "demo_api"
    assert event.troubleshooting_path.startswith("docs/")
    assert "token" not in json.dumps(asdict(event)).lower()
```

- [ ] **Step 2: Run the focused test before implementing the evaluator**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_alerts.py -q`

Expected: collection fails because `multisite_crawler.alerts` is absent.

- [ ] **Step 3: Implement validated thresholds and deduplicated transitions**

Use a fixed rule-id enum and per-rule Redis keys. An active condition writes
state only on its first activation; a healthy subsequent evaluation returns a
single resolved event and clears state. Use fixed safe troubleshooting document
paths. Implement separate dependency probe results for PostgreSQL and Redis,
and include a separate PostgreSQL-down scenario in the parameterized matrix.

- [ ] **Step 4: Add Prometheus-compatible rule definitions**

Write `configs/prometheus/alerts.yml` with stable alert names, `source_id`
annotations, fixed runbook paths, threshold expressions, and `for` durations.
The file is configuration only; it does not add or deploy Alertmanager.

- [ ] **Step 5: Verify alert and recovery behavior**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_alerts.py -q
```

Expected: every rule has an active test, a resolved test, and a repeated-active
test proving the evaluator does not create an alert storm.

### Task 4: Redacted Failure Snapshot Store And Cleanup (P5-04)

**Files:**
- Create: `src/multisite_crawler/failure_snapshots.py`
- Create: `tests/test_failure_snapshots.py`
- Modify: `src/multisite_crawler/browser_artifacts.py`
- Modify: `src/multisite_crawler/browser_runtime.py`
- Modify: `src/multisite_crawler/tasks.py`
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Produces `SnapshotRequest`, `SnapshotArtifact`, `RedactedPng`,
  `FailureSnapshotWriter.write`, and `cleanup_expired_snapshots`.
- `SnapshotRequest` requires safe `source_id`, UUID `crawl_run_id`, a typed
  structured body, allowlisted headers, and optional `RedactedPng`.
- Browser runtime accepts only `BrowserOperationError(..., redacted_png=...)`.

- [ ] **Step 1: Write failing snapshot, redaction, and expiry tests**

```python
def test_snapshot_uses_run_id_and_redacts_headers_body_and_url(tmp_path: Path) -> None:
    writer = FailureSnapshotWriter(tmp_path, retention_days=7, max_bytes=4096)

    artifact = writer.write(SnapshotRequest(
        source_id="demo_api", crawl_run_id=RUN_ID, headers={"ETag": "ok", "Cookie": "bad"},
        body={"name": "safe", "token": "secret", "url": "https://x/?account=1"},
    ))

    serialized = artifact.response_path.read_text(encoding="utf-8")
    assert str(RUN_ID) in artifact.response_path.name
    assert "secret" not in serialized
    assert "account=1" not in serialized
    assert '"ETag":"ok"' in serialized


def test_cleanup_only_removes_expired_files_below_snapshot_root(tmp_path: Path) -> None:
    removed = cleanup_expired_snapshots(tmp_path, cutoff=NOW - timedelta(days=7))
    assert removed == 1
```

- [ ] **Step 2: Run the focused snapshot test before the module exists**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_failure_snapshots.py -q`

Expected: collection fails because `multisite_crawler.failure_snapshots` is absent.

- [ ] **Step 3: Implement the external private snapshot boundary**

Validate the output path is absolute and outside the repository. Recursively
redact denied keys; persist only JSON bodies and the header allowlist. Reject
unstructured/binary HTTP input. Check `RedactedPng` PNG signature and byte
limit before writing it. Update `BrowserArtifactWriter` to delegate only this
safe screenshot path and leave unredacted screenshots unpersisted.

- [ ] **Step 4: Run focused browser regression tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_failure_snapshots.py tests/test_browser_artifacts.py tests/test_browser_runtime.py -q
```

Expected: snapshots are replayable JSON artifacts, no sensitive value is
written, and browser failure tests prove a screenshot is saved only when an
adapter supplied `RedactedPng`.

### Task 5: Persist Snapshot Paths With an Alembic Migration

**Files:**
- Create: `migrations/versions/20260712_03_add_crawl_run_snapshot_path.py`
- Modify: `src/multisite_crawler/models.py`
- Modify: `tests/test_database.py`
- Modify: `tests/test_failure_snapshots.py`

**Interfaces:**
- Adds nullable `CrawlRun.snapshot_path: Mapped[str | None]`.
- Migration upgrade adds `crawl_runs.snapshot_path VARCHAR(1024)`; downgrade
  removes exactly that column.
- Snapshot integration assigns the path only after artifact creation succeeds.

- [ ] **Step 1: Write failing model and migration assertions**

```python
def test_crawl_run_model_has_nullable_snapshot_path() -> None:
    column = CrawlRun.__table__.c.snapshot_path
    assert column.type.length == 1024
    assert column.nullable is True


@pytest.mark.integration
def test_snapshot_path_migration_is_reversible() -> None:
    command.upgrade(config, "head")
    assert "snapshot_path" in {column["name"] for column in inspect(engine).get_columns("crawl_runs")}
    command.downgrade(config, "-1")
    assert "snapshot_path" not in {column["name"] for column in inspect(engine).get_columns("crawl_runs")}
    command.upgrade(config, "head")
```

- [ ] **Step 2: Run the model test and observe the missing column failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_database.py::test_crawl_run_model_has_nullable_snapshot_path -q`

Expected: FAIL because `snapshot_path` does not exist.

- [ ] **Step 3: Implement model and reversible migration**

Use Alembic `op.add_column("crawl_runs", sa.Column("snapshot_path",
sa.String(length=1024), nullable=True))` in upgrade and `op.drop_column` in
downgrade. Do not run manual DDL.

- [ ] **Step 4: Verify against disposable local PostgreSQL**

Start only a disposable PostgreSQL container, set `TEST_DATABASE_URL` locally,
then run the specified migration test and exact round trip:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic downgrade -1
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest tests/test_database.py -q
```

Expected: schema upgrade, downgrade by one revision, re-upgrade, model checks,
and PostgreSQL integration tests all pass. Remove the disposable test container
and volume after the evidence is recorded.

### Task 6: P5 End-to-End Evidence, Documentation, And TODO

**Files:**
- Modify: `README.md`
- Modify: `TODO.md`
- Modify: `docs/superpowers/specs/2026-07-12-p5-observability-failure-handling-design.md`
- Modify: `docs/superpowers/plans/2026-07-12-p5-observability-failure-handling.md`
- Test: `tests/test_observability.py`, `tests/test_metrics.py`,
  `tests/test_alerts.py`, `tests/test_failure_snapshots.py`

**Interfaces:**
- Documents local startup and inspection commands without real-source URLs,
  credentials, or production deployment steps.
- Marks a P5 TODO item complete only after its exact tests and the full quality
  gate pass.

- [ ] **Step 1: Write the end-to-end local acceptance test**

```python
def test_local_observability_flow_is_traceable_and_safe(tmp_path: Path) -> None:
    context = RunContext("demo_api", RUN_ID, "task-local")
    observe_success(context, item_count=2, duration_seconds=0.5)
    metrics = scrape_loopback_metrics()
    alerts = evaluator.evaluate(healthy_snapshot(), NOW)

    assert str(RUN_ID) not in metrics
    assert alerts == []
    assert find_json_log(RUN_ID)["source_id"] == "demo_api"
```

- [ ] **Step 2: Run the P5-focused suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_observability.py tests/test_metrics.py tests/test_alerts.py tests/test_failure_snapshots.py -q
```

Expected: all P5 unit and local loopback acceptance tests pass.

- [ ] **Step 3: Run the required full quality gate**

Run:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest -q
docker compose config
```

Expected: all commands exit successfully. Report deliberate skips only when the
PostgreSQL URL is absent; P5-04 is not checked until its disposable PostgreSQL
migration evidence is successful.

- [ ] **Step 4: Update documentation and TODO after evidence**

Document JSON log rotation, loopback metrics, alert rule location, snapshot
root/retention configuration, and cleanup behavior. Check P5-01 through P5-04
and their acceptance boxes only after their evidence is recorded. Keep P3-04
unchecked and do not add a source adapter or real-site URL.

## Plan Self-Review

- P5-01 is covered by Task 1; its run correlation, redaction, rotation, and
  log-disk bounds are tested before integration.
- P5-02 is covered by Task 2; all required metric names, scrape behavior, and
  bounded labels have direct tests.
- P5-03 is covered by Task 3; every listed rule, recovery, context fields,
  and deduplication behavior has a test.
- P5-04 is covered by Tasks 4 and 5; the artifact contract, retention cleanup,
  screenshot boundary, database path, and Alembic round trip are explicit.
- Task 6 requires the final gate and prevents premature TODO changes.
- The repository has no initial commit and all project files are untracked, so
  the plan intentionally omits the skill's suggested commit commands.
