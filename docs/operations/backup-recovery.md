# Backup And Recovery

## Scope

These procedures are for disposable local PostgreSQL verification only. They
must not be used against a shared or production database without human review,
approved credentials, and an approved change window.

## Targets

The initial operating targets are RPO of 24 hours and RTO of 4 hours. They are
planning targets, not a production service-level commitment.

## Local Exercise

Set a loopback `DATABASE_URL`, choose a backup directory outside this
repository, then run `scripts/backup_local_postgres.ps1`. Restore only to a
new local disposable database with `scripts/restore_local_postgres.ps1`.
Compare record counts and change-event counts before declaring the exercise
successful.

## Rebuild

Rebuild a machine by installing Docker Desktop, Python 3.12, the repository
dependencies, and the approved secret-management integration. Restore the
database with a reviewed backup, run Alembic, validate health checks, and keep
all source adapters disabled until a human review completes.
