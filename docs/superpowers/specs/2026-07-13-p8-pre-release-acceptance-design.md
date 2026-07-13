# P8 Pre-Release Acceptance Design

## Scope

P8 turns the existing local runtime, observability, security, and release
contracts into repeatable pre-release evidence. It does not collect a real
source, create credentials, or deploy a production environment.

## Five-Minute Reliability Baseline

The accepted baseline is a five-minute disposable-local Compose exercise. It
starts the complete local stack, observes healthy services, then simulates a
Redis restart, transient PostgreSQL interruption, controlled HTTP Worker restart, and
Scheduler restart. It proves recovery of the local services and preserves
existing unit/integration coverage for overlap leases, idempotent upsert,
bounded retries, empty data, parser failures, HTTP 429/502/503, and
alert-deduplication.

Five minutes is deliberately documented as a repeatable engineering smoke test,
not a substitute for long-running real-source or production reliability data.

## Security Boundaries

The Compose runtime separates the migration owner from the application role and
keeps the local data plane on one internal Docker network. The application
image runs as an unprivileged user. CI scans dependencies, repository history,
and the locally built image; it remains read-only except for the existing image
publication workflow on `main`.

Backup validation checks an external backup directory for broad Windows access
rules before an operator uses it. Failure snapshots and operational logs remain
redacted and outside Git.

## Release Gate

P8-03 stays a human-gated release checklist. No real source is currently
eligible because `sporttery_zqspf` still requires manual robots guidance,
authorization-record, and permitted-cadence review before P3-04. A successful
P8 local exercise cannot satisfy those source-specific or production approval
requirements.
