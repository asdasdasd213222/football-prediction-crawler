# Multi-Site Crawler

Foundation repository for a production-grade multi-site data collection system.

## Observability

P5 emits structured JSON run events with `source_id`, `crawl_run_id`, and
`task_id`. Event details are recursively redacted; exception messages, URL
queries, credentials, cookies, tokens, authorization values, account data, and
personal data are not written. By default logs go to standard output. To use
rotating files, set `LOG_FILE_DIR` to an existing or creatable directory outside
this repository, then configure `LOG_MAX_BYTES` and `LOG_BACKUP_COUNT`.

P5 metrics are exposed only from `http://127.0.0.1:9464/metrics`; the service
returns `404` for every other path. Alert rule templates live in
`configs/prometheus/alerts.yml` and local runbooks in `docs/operations/`. P5
failure snapshots are redacted JSON artifacts in an external
`FAILURE_SNAPSHOT_DIR`; set their size and retention through the matching
environment variables. Snapshots are never served by the metrics endpoint.
The `configs/grafana/crawler-overview.json` template renders per-source success
rate and last-success time from the low-cardinality Prometheus metrics.
It currently provides project tooling, strict source configuration, PostgreSQL
persistence foundations, adapter contracts, Redis task queues, and local
Beijing-time scheduling. It does not implement real-site collection,
credentials, or production deployment.

## Requirements

- Python 3.12
- Docker Compose v2 for configuration validation

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Quality Checks

Run all checks before considering a change complete:

```powershell
ruff check .
ruff format --check .
mypy src
pytest -q
docker compose config
```

Compose is for local development and acceptance checks only. It must not be
used to deploy a production environment.

## Deployment Operations

P6 provides a local Compose stack for Redis, PostgreSQL, migrations, the HTTP
worker, and the scheduler. The dedicated Edge worker remains a constrained
Windows-host service and is never containerized with its local profile. See
`docs/operations/deployment.md` for CI, immutable image publishing, human
promotion approval, health-gated rollback, and host Edge recovery. See
`docs/operations/backup-recovery.md` for local backup and recovery exercises.

Start a fresh local stack, including a rebuild of the application image, with:

```powershell
docker compose up --build -d
```

## Source Configuration

Use `configs/sources.example.yaml` as a non-sensitive reference for one or more
sources. Loading validates structure and values only; it does not schedule or
collect data.

```python
from pathlib import Path

from multisite_crawler.config import load_config

config = load_config(Path("configs/sources.example.yaml"))
```

## Database Foundations

P1-02 provides SQLAlchemy models and Alembic migrations for a PostgreSQL
database. The application reads `DATABASE_URL` only when a caller requests
database access. Migration integration tests require a separate,
disposable-local `TEST_DATABASE_URL`; never point either variable at a shared
or production database during tests.

All persisted timestamps represent Beijing local time (`Asia/Shanghai`) and
use PostgreSQL `TIMESTAMP WITHOUT TIME ZONE`. Database URLs and credentials are
intentionally absent from this repository.

## Adapter Contract

Website-specific code implements `BaseAdapter` in `multisite_crawler.adapters`.
The shared runner calls `fetch`, `parse`, `normalize`, and `fingerprint` in
order, validates each normalized `CrawlItem`, and returns data without writing
to storage. Source-specific selectors and mappings stay in adapters; generic
scheduling and storage remain site-neutral.

## Task Queues

P2-01 uses Redis only as the Celery broker. The `http` and `browser` queues
have separate workers, late acknowledgement, worker-loss redelivery, bounded
retry, and queue-depth metrics. PostgreSQL remains the business system of
record; no Celery result backend is configured.

## Dedicated Edge Runtime

P4-01 adds a dedicated local Microsoft Edge runtime boundary for host-only
browser work. The host worker requires `python -m pip install -e ".[browser]"`
in addition to the normal development install. Configure it with these
non-secret variables:
`BROWSER_EDGE_EXECUTABLE_PATH`, `BROWSER_USER_DATA_DIR`,
`BROWSER_FAILURE_SNAPSHOT_DIR`, `BROWSER_PAGE_TIMEOUT_SECONDS`, and
`BROWSER_ACTION_TIMEOUT_SECONDS`. `BROWSER_WORKER_CONCURRENCY` is an
independent host-worker setting but must remain `1` while one dedicated Edge
profile is shared.
`BROWSER_MAX_MEMORY_MB` defaults to `1024` and becomes the Celery child-process
memory limit for the host browser Worker.

`BROWSER_USER_DATA_DIR` and `BROWSER_FAILURE_SNAPSHOT_DIR` must point outside
the repository. This task does not authorize login automation, cookie
inspection, or real-site collection.

Start the host browser worker outside Compose with
`.\scripts\run_browser_worker.ps1` after setting `REDIS_URL` and the Edge
runtime variables above. `compose.yaml` no longer starts a browser worker;
Compose keeps Redis, the HTTP worker, and the scheduler only, while the Edge
runtime stays on the host so it can use the local Windows executable and
profile.

`.\scripts\verify_edge_runtime.ps1 -Run` is a local-only opt-in check. It
starts a loopback fixture on `http://127.0.0.1`, then runs the browser probe
against that fixture. This check requires an operator-supplied external Edge
executable and profile configuration plus a reachable Redis instance. It is
not a production readiness signal and does not authorize authenticated
collection.

P4-02 must land before any authenticated collection work. P4-01 only proves
the host runtime boundary and local probe path.

Browser failure artifacts accept only adapter-supplied safe fragments with
exactly one `<table>` root and no other content before or after it. Artifact
sanitization removes forms, scripts, styles, and sensitive-like attributes
such as `cookie`, `token`, `authorization`, and `password`. Screenshots are
not persisted until a future clipped-safe-region contract is defined.

## Manual Profile Refresh

P4-02 records only an opaque profile reference, a Beijing-local manual refresh
time, and a fixed session state in Redis. It does not read or export cookies,
credentials, account data, or browser storage. After any permitted manual
login in the dedicated external profile, close Edge before recording refresh:

```powershell
.\scripts\open_edge_profile.ps1 -Open
# Complete any permitted login manually, then close Edge.
.\scripts\open_edge_profile.ps1 -RecordRefresh
```

The helper only opens `about:blank`; it accepts no source URL or credentials.
It rejects a profile directory inside this repository.
An operator can update the permitted login manually and record a new refresh
without changing application code; only the refresh time is stored. Any future
approved non-interactive login must obtain credentials only from an approved
secret manager or environment variables; P4-02 does not implement it.
P4-02 does not grant source authorization or remove the P3-04 robots and
cadence review requirements.

## Scheduling

P2-02 adds a separate Redis-backed scheduler service. It loads enabled sources
from the validated configuration mounted at `SCHEDULER_CONFIG_PATH`, calculates
all schedule values as Beijing local time (`Asia/Shanghai`), and routes a
source identifier to its configured `http` or `browser` queue. The scheduler
stores the source interval, pause state, last dispatch time, and next run time
in Redis. On restart it preserves that state and dispatches at most one overdue
run per source.

`SchedulerService` exposes `manual_trigger`, `pause`, and `next_run` for
trusted operational callers. A manual trigger is site-neutral and does not
change the stored next scheduled run. P2-02 deliberately does not add source
locking or overlap prevention; those belong to P2-03.

## Task Overlap Control

P2-03 wraps each source task in a Redis lease keyed by source id. The lease is
atomically acquired, renewed while slow work runs, and released only by its
owner token. A competing task logs and returns `skipped_overlap`; a crashed
worker stops renewing, so the bounded Redis expiry permits recovery. The public
page lock-key helper is reserved for later paginated work. Retry, backoff,
rate limiting, and circuit breaking remain P2-04 concerns.

The supplied `configs/sources.example.yaml` contains two non-networked demo
sources for local scheduler acceptance: `demo_api` uses the HTTP queue and
`demo_browser` uses the browser queue. They invoke only the current queue task
stubs and do not contact `example.invalid`.

## Resilience Policy

P2-04 provides site-neutral retry policy primitives for transient connection
errors and 429/502/503 responses. Retry delays use bounded exponential backoff
with injected jitter; `Retry-After` is honored when present. Authentication
denials are not retried, while CAPTCHA or access-control content is returned
for human review without bypass attempts. Per-source rate limits and circuit
breakers are isolated; the Redis circuit state survives worker replacement and
allows one half-open recovery probe after its cooldown.

## Local Mock Server

P3-01 provides `MockCrawlerServer` for offline adapter integration tests. It
binds only to `127.0.0.1` and can deterministically serve normal JSON, ETag and
304 behavior, updated content, 429 with `Retry-After`, 500, delayed responses,
invalid JSON, missing fields, and empty results. It is test-only infrastructure
and does not make public-network requests.

## Demo Adapter

P3-02 provides `DemoApiAdapter`, exercised only against `MockCrawlerServer`.
It fetches, parses, normalizes, fingerprints, and persists demo items through
`RecordRepository`. Tests cover normal and empty responses, malformed JSON,
HTTP failure, idempotent re-collection, and a correct business update event.
