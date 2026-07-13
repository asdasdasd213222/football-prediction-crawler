# P6 Deployment And Operations Design

## Goal

Complete P6-01 through P6-03 with reproducible local operations, CI checks,
and documented recovery procedures without deploying production services or
handling production credentials.

## Architecture

Docker Compose provides the local Redis, PostgreSQL, migration, HTTP worker,
scheduler, metrics, and health-check environment. The dedicated Edge Worker
remains a Windows host process launched by the existing PowerShell helper; it
is not containerized because its authorized external profile and Edge binary
must remain outside source, fixtures, and container mounts.

CI runs the same quality checks as local development, a disposable PostgreSQL
migration round trip, image builds, and dependency/secret checks. No workflow
publishes images or performs deployment. Backup and recovery helpers require
explicit local paths and disposable database URLs, and recovery documentation
states RPO/RTO targets plus human approval points.

## Security Constraints

- No production URL, credential, key, cookie, account value, or backup content
  is committed.
- Compose binds development ports to loopback and uses only non-secret example
  variables.
- Database and Redis health checks disclose no connection values.
- Backup output directories must be external to the repository; restore is
  blocked for non-local database hosts.
- CI permissions remain read-only except for optional artifact generation.
- Production deployment remains explicitly out of scope.

## Verification

P6-01 uses a disposable local Compose environment with service health and a
migration round trip. P6-02 is validated with workflow syntax plus local
equivalent commands. P6-03 uses a disposable local PostgreSQL backup and
restore exercise. Final gates remain Ruff, format, Mypy, Pytest, and Compose
configuration.
