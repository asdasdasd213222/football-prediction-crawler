# Observability Runbook

## Run Failures

Use the JSON `crawl_run_id` to locate related structured events. Review only
redacted failure snapshots outside the repository, then add a regression test
before changing an adapter. Do not retry access-denied or CAPTCHA outcomes as a
login action.

## Data Quality

Investigate zero, abnormal, and parse-error alerts with the safe item counts
and snapshot metadata. Do not log page text, account information, or response
credentials.

## Queue Backlog

Check the queue depth, worker heartbeat, source lease state, and Redis health.
Avoid concurrent manual task dispatch for a source with an active lease.

## Dependencies

Check the local Redis and PostgreSQL health paths. Database migrations use
Alembic only; do not apply manual production DDL.

## Snapshot Retention

Failure snapshots are private external files. Configure retention and size
limits through environment variables, and run cleanup only against the
validated snapshot root.
