# P5 Observability And Failure Handling Design

## Goal

Complete P5-01 through P5-04 with a site-neutral, local-first observability
layer. It must make every collection attempt traceable, expose bounded
Prometheus metrics, evaluate deduplicated alerts, and retain only redacted
failure snapshots. It does not collect a real website, automate a login, add a
production deployment, or enable P3-04.

## Constraints

- All timestamps use Beijing civil time (`Asia/Shanghai`).
- Logs, metrics, alert payloads, artifacts, tests, and fixtures must not
  contain credentials, cookies, tokens, authorization headers, account data,
  or personal data.
- A `source_id` is a stable low-cardinality source key. URLs, record IDs,
  page text, request IDs, and arbitrary exception messages are never metric
  labels.
- Run identifiers are UUIDs used in JSON logs and alert payloads, never metric
  labels.
- Failure snapshot directories live outside the repository and are not served
  by the metrics endpoint or any public HTTP handler.
- The existing browser failure path may persist only an adapter-supplied,
  explicitly redacted PNG. It must not take or store an unreviewed full-page
  screenshot.

## Architecture

P5 uses Redis as the shared, non-business observability state store. Scheduler
and workers publish typed run events to a small site-neutral observation API.
The API produces a redacted JSON log event and performs fixed Redis counter,
gauge, timestamp, and heartbeat updates. A separate local metrics process
reads that state and serves Prometheus text exposition at a configured
loopback endpoint. This avoids relying on process-local counters in a
multi-worker deployment.

```text
Scheduler / Worker / Repository
        | typed run and operational events
        v
Observation service ----> rotating redacted JSON logs
        |
        v
Redis observability keys <---- Alert evaluator
        |
        +---- Metrics service: GET /metrics (loopback only by default)

Adapter-safe failure inputs
        |
        v
Failure snapshot writer ----> external redacted artifact directory
        |
        v
Optional CrawlRun.snapshot_path (PostgreSQL)
```

## P5-01 Structured Logs

`observability.py` will define a `RunContext` containing `source_id`,
`crawl_run_id`, and `task_id`, plus a fixed `RunOutcome` vocabulary. A JSON log
formatter will emit the timestamp, level, event name, context fields, status,
duration, item count, and exception type where relevant. It will not serialize
an exception message by default.

A recursive redactor will replace values associated with credential and
personal-data keys before serialization. It will also scrub URL user-info and
query values. The formatter will reject arbitrary extra objects rather than
falling back to an unsafe string representation. Logs use a rotating file
handler with a configured byte limit, backup count, and external path; the
default developer configuration remains console-only. Tests will capture log
records and assert sensitive markers cannot be emitted.

## P5-02 Prometheus Metrics

`metrics.py` will store a bounded metric snapshot in Redis and render the
Prometheus text format through `metrics_service.py`. The service defaults to
`127.0.0.1`; deployment network exposure belongs to P6.

The exported names are exactly:

- `crawler_run_total`, `crawler_run_failed_total`,
  `crawler_run_duration_seconds`
- `crawler_items_found`, `crawler_items_created`, `crawler_items_updated`
- `crawler_http_status_total`, `crawler_queue_depth`,
  `crawler_last_success_timestamp`
- `crawler_parse_error_total`, `crawler_lock_skip_total`, and
  `crawler_circuit_breaker_state`

The only labels are fixed finite fields such as `source_id`, `queue`,
`outcome`, and numeric HTTP status. `crawl_run_id`, URLs, and business record
identifiers are represented only in logs and bounded Redis latest-state keys.
Unit tests will validate the complete output and assert that high-cardinality
values cannot become labels. A local HTTP test will scrape `/metrics` without
contacting any source.

## P5-03 Alert Rules

`alerts.py` will evaluate typed metric and health snapshots against validated
threshold configuration. It covers consecutive run failures, overdue success,
zero and abnormal item count, parse-field error rate, 401/403/429/CAPTCHA,
queue backlog, worker heartbeat expiry, PostgreSQL/Redis availability, and
disk free space. Every active and resolved alert carries `source_id`, the most
recent safe run ID when one exists, a fixed troubleshooting path, severity,
and Beijing timestamp.

The evaluator stores each alert's state in Redis. It emits one active event
when a condition crosses its threshold and one resolved event when it clears;
repeated evaluation of an unchanged condition is silent. This prevents an
occasional failed run or a persistent outage from causing an alert storm.
Prometheus rule files will express the same stable conditions for later P6
integration, but P5 verification uses the typed evaluator and fake stores,
not a deployed Alertmanager or Grafana instance.

## P5-04 Failure Snapshots

`failure_snapshots.py` will accept typed, bounded failure material and write a
private artifact directory outside the repository. HTTP response headers use a
fixed allowlist. Structured JSON bodies are recursively redacted; unknown
binary or unstructured response bodies are not persisted because they cannot
be safely scrubbed. The written response artifact is the redacted replay input
for an adapter regression test, not an unredacted wire capture.

Browser failures accept only an adapter-supplied `RedactedPng` value. The
runtime will preserve no screenshot when a source adapter has not supplied a
reviewed safe-region capture. This rule prevents accidental capture of logged
in account data while providing the P5 browser screenshot pathway for adapters
with a documented redaction contract.

Artifact names use the `crawl_run_id` and safe `source_id`. Configuration sets
retention days and maximum snapshot size. A site-neutral cleanup task removes
only expired files below the configured snapshot root. A database migration
adds the nullable snapshot path to `crawl_runs`; the repository writes it only
after a successful artifact write. The migration is verified with upgrade,
downgrade-one-revision, and upgrade-again against local disposable PostgreSQL.

## Integration Boundaries

- Adapters report typed outcome, counts, HTTP status, parse errors, and safe
  snapshot inputs. They keep selectors, page text, and mapping logic local.
- Scheduler and Celery tasks add context and emit events, but remain
  site-neutral.
- Repository persistence returns typed created/updated counts instead of
  embedding observability policy in database code.
- No P5 module reads browser profile directories, credentials, cookies, or
  arbitrary source HTML.

## Verification

Each P5 subtask uses failing-first unit tests and local loopback fixtures.
P5-04 additionally runs the required Alembic round-trip against a disposable
local PostgreSQL instance. Final verification runs:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pytest -q
docker compose config
```

No P5 TODO item is checked until its own acceptance evidence and the final
quality gate pass. P3-04 remains blocked by its independent source-card
authorization, robots, and cadence prerequisites.
