# Pre-Release Acceptance

## Scope

This runbook performs disposable local evidence gathering only. It does not
authorize a production deployment, real-site collection, profile login, or
source enablement.

## Five-Minute Reliability Exercise

Run the following from a clean local Docker environment:

```powershell
.\scripts\run_p8_local_reliability.ps1
```

The script starts the local Compose stack, requires five minutes of stable
service observation, then performs a Redis restart, a short PostgreSQL stop and
start, a controlled HTTP Worker restart, and a Scheduler restart. It waits for the
services to recover after each event and removes the disposable stack and
volumes by default.

The exercise is a five-minute local baseline. It does not establish a
72-hour reliability record and does not make a source or production target
eligible for release.

## Security Evidence

Run the repository gates and inspect the CI result for `pip-audit`, `gitleaks`,
and the Trivy image scan. The Compose stack uses the `crawler_app` role for
runtime DML and a distinct local `crawler_owner` role for Alembic migrations.
The credentials are local disposable values only; no production credential is
represented in this repository.

Before using a local backup location, verify it is external to the repository
and has no broad access rule:

```powershell
.\scripts\verify_backup_security.ps1 -BackupDirectory <external-directory>
```

## Human Release Gate

Do not dispatch the `Release` workflow with `promote=true` until a human has
reviewed the real-source authorization, robots guidance, cadence, secrets,
backup evidence, alert receiver, rollback image, and protected environment
approval. P8 creates no production deployment evidence and does not replace
that review.
